"""What a spell or an ability does when it resolves.

This is a scripted registry, not a rules engine: each card is looked up by name
and its effect is a small function. Cards without an entry resolve with no
effect, which is right for a vanilla creature and wrong for anything else.

Adding a card to `tests/fixtures/cards` does not teach the model what it does.
If a scenario needs a card's text to actually happen, add it here too.

Three registries live here:

- `EFFECTS` - what a **spell** does on resolution, keyed by card name.
- `TRIGGER_EFFECTS` - what a **triggered ability** does, keyed by
  `(card name, TriggerEvent, marker)`. A card with two triggers on different
  events - White Orchid Phantom enters, Wurmcoil Engine dies - gets one entry
  each, and a card with two triggers on the *same* event tells them apart with
  `marker`.
- `ACTIVATED_EFFECTS` - what an **activated ability** does, keyed by
  `(card name, index)`, where the index is the ability's position among the
  card's activated abilities as `parse_abilities` reads them.

## The marker, and why the key has three parts

`(card name, TriggerEvent)` cannot hold two triggers on one event, and there are
cards in the pool with exactly that: Ugin, Eye of the Storms has two `CAST_SPELL`
triggers. The old registry handed its single entry *both* of them as they
resolved, so a card like this needed a guard reading the resolving ability's own
printed text to refuse the one it was not written for. That was a workaround for
the key, not a fix.

The third part of the key is a lowercase fragment of the trigger's printed text -
`"whenever you cast a colorless spell"` was Ugin's second trigger's marker before
its two rows were deleted; both are `parse_targeted_effect`'s count-agnostic
exile shape now (see `_targets_understood`) and Ugin no longer has an entry at
all, joining Sowing Mycospawn below as proof the dispatcher's fallback matters
even with no entries. The mechanism stays for the next card that needs it.
`trigger_effect_for` still takes only `(card name, event)`, because
`Game._effect_of` calls it with those two and `models/game.py` is owned
elsewhere; when a card has more than one entry for an event it returns a
**dispatcher** that reads the resolving ability's text and picks. The card that
fires the whole card's one trigger keeps an empty marker, which matches
anything. Sowing Mycospawn is the reason the dispatcher's fallback matters even
with no entries at all: its two `CAST_SPELL` triggers have different printed
text and neither has a row here any more - one is `parse_search_and_put_effect`'s
shape and reached through the fallback, the other's intervening *if* (CR 603.4)
is not modelled and is deliberately left with no effect, and the two are told
apart because `Game._effect_of` always hands `trigger_effect_for` the
*resolving* ability's own text, not a hardcoded one.

An ability with no entry still goes on the stack, is still responded to, and is
still removed from the stack by CR 608.2n - it simply has no effect when it gets
there. `docs/engine-coverage.md` lists which abilities execute and which only
travel.
"""

import re
from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ..models.card import Color, Supertype, Type
from ..models.card_state import CardState, Counter
from ..models.player import Player
from ..models.token import MONSTER_ROLE, PREDEFINED, TokenDefinition, create_tokens
from ..models.zone import Zone
from .abilities import TriggerEvent
from .decisions import Decision, DecisionKind
from .delayed import DelayedTrigger
from .layers import (
    ContinuousEffects,
    LayerContext,
    count_card_types,
    is_resolution_layer_effect_text,
)
from .modes import Mode, is_modal_text, modal_profile, substitute_x
from .targeting import profile_for_text
from .triggers import AbilityOnStack, is_ability
from .turn import Step

if TYPE_CHECKING:
    from ..models.game import Game, StackObject

Effect = Callable[["Game", CardState], None]
AbilityEffect = Callable[["Game", AbilityOnStack], None]
#: One clause of a targeted effect, generic over what is resolving: a spell
#: names itself, a triggered or activated ability names the `AbilityOnStack` -
#: `Game.resolve_targets`/`Game.controller_of` already take either, so one
#: function serves both `Effect` and `AbilityEffect`.
TargetedClause = Callable[["Game", "StackObject"], None]


def deal_damage(amount: int) -> Effect:
    """Deal `amount` damage to each target, permanent or player (CR 119.3).

    "Any target" means what it says: the same Bolt hits a creature or a face
    depending only on what was chosen when it was cast.

    The **source** is the spell itself. CR 120.1: "An object that deals damage is
    the source of that damage", and CR 120.2b: "the spell or ability will specify
    which object deals that damage" - Lightning Bolt's text is "Lightning Bolt
    deals 3 damage", so the resolving `CardState` on the stack is the source.
    Naming it is what lets CR 702.16e's protection, CR 615.8's next-instance
    shield and CR 609.7b's source-quality recheck see spell damage at all.
    """

    def effect(game: "Game", spell: CardState) -> None:
        for target in game.resolve_targets(spell):
            game.deal_damage(target, amount, source=spell)

    return effect


def gain_life(amount: int) -> Effect:
    """The spell's controller gains `amount` life (CR 118.3)."""

    def effect(game: "Game", spell: CardState) -> None:
        game.controller_of(spell).gain_life(amount)

    return effect


def deal_divided_damage(total: int) -> Effect:
    """Damage "divided as you choose among one or two targets" (CR 601.2d).

    "The player announces the division. Each of these targets must receive at
    least one of whatever is being divided." There is nobody here to announce
    it, so the division is as even as it goes and the remainder lands on the
    first target chosen - which for Electrolyze's 2 damage is the whole of it on
    one target, or 1 each on two.

    Only targets that are still legal on resolution are paid out (CR 608.2b),
    and the share the illegal ones would have had is simply not dealt: the
    division is locked in at announcement and cannot be re-divided.
    """

    def effect(game: "Game", spell: CardState) -> None:
        chosen = len(spell.targets)
        if chosen == 0:
            return
        shares = [total // chosen] * chosen
        for index in range(total % chosen):
            shares[index] += 1
        for reference, share in zip(spell.targets, shares, strict=True):
            target = game.legal_target(spell, reference)
            if target is not None and share > 0:
                game.deal_damage(target, share, source=spell)

    return effect


def draw_cards(count: int) -> Effect:
    """The spell's controller draws `count` cards (CR 121.1, CR 121.2).

    Routed through `Game.draw_cards`, so each card is its own individual draw
    (CR 121.2: "that player performs that many individual card draws") and its
    own trigger event - a Sheoldred watching "whenever you draw a card" sees
    one event per card, not one with a count.
    """

    def effect(game: "Game", spell: CardState) -> None:
        game.draw_cards(game.controller_of(spell).username, count)

    return effect


def sequence(*effects: Effect) -> Effect:
    """Do several things in the order the card lists them (CR 608.2c)."""

    def effect(game: "Game", spell: CardState) -> None:
        for step in effects:
            step(game, spell)

    return effect


def counter_targets(game: "Game", spell: CardState) -> None:
    """Counter each targeted spell, putting it into its owner's graveyard.

    A counterspell whose target has already left the stack does nothing, which
    is what happens when the target was itself countered first (CR 608.2b).
    """
    for reference in spell.targets:
        if not reference.is_card:
            continue
        target = next((item for item in game.stack if item.id == reference.card_id), None)
        if target is not None:
            game.counter(target)


def continuous_effects(game: "Game") -> ContinuousEffects:
    """The game's store of continuous effects with a duration (CR 611.2).

    `Game` holds the store now and ends its "until end of turn" effects in the
    cleanup step (CR 514.2, CR 703.4p), so a spell whose whole effect is a
    continuous one - Giant Growth, Mutagenic Growth, Twisted Image, Monstrous
    Rage's pump - reaches the layer engine and actually changes the board.
    """
    return game.continuous_effects


def create_continuous_effect(game: "Game", spell: CardState) -> None:
    """The spell's effect is a continuous one, so record it (CR 611.2, CR 611.2a).

    What the spell generates, and how long it lasts, comes from `LAYER_EFFECTS`
    in `machines/layers.py`. The objects it applies to are the targets that are
    still legal now, and they are fixed here for good (CR 611.2c); the effect is
    timestamped now (CR 613.7b).

    The `LayerContext` carries what the builder cannot see from the battlefield:
    every graveyard, and separately the *controller's* graveyard, which is what
    a card printing "cards in your graveyard" means (Violent Urge's delirium).
    Both are read now, as the spell resolves, which is the moment the effect's
    one-off conditions are locked in (CR 611.2c).
    """
    continuous_effects(game).create(
        spell,
        targets=game.resolve_card_targets(spell),
        context=layer_context_for(game, game.controller_of(spell)),
    )


def layer_context_for(game: "Game", controller: Player) -> LayerContext:
    """The graveyards a resolving effect may need to count (CR 205.2a card types)."""
    everyone: list[CardState] = []
    for player in game.players_in_game:
        everyone.extend(player.graveyard)
    return LayerContext(
        graveyards=tuple(everyone),
        your_graveyard=tuple(controller.graveyard),
    )


def create_continuous_effect_of_ability(game: "Game", ability: AbilityOnStack) -> None:
    """The same for a resolving ability (CR 611.2 covers spells and abilities alike).

    Two shapes share this one function. When the ability names no target -
    Basking Rootwalla's "{1}{G}: This creature gets +2/+2 until end of turn." -
    the affected object is the ability's own source. When it does - Karn, the
    Great Creator's "+1: ... up to one target noncreature artifact becomes an
    artifact creature ..." - the affected object is whatever it targeted,
    rechecked for legality now exactly as a spell's targets are (CR 608.2b):
    `game.resolve_card_targets` is the same call `create_continuous_effect`
    makes for a spell, so a loyalty ability reaches the layer engine through
    the ordinary activated-ability path rather than a planeswalker-specific
    one. "Up to one" legally choosing zero leaves `targets` empty and the
    ability resolves doing nothing, which is CR 608.2's ordinary answer for a
    modal/optional clause that picked nothing rather than a fizzle.
    """
    source = ability.source(game)
    if source is None or source.zone is not Zone.BATTLEFIELD:
        return
    targets = game.resolve_card_targets(ability) if ability.targets else [source]
    if not targets:
        return
    continuous_effects(game).create(
        source,
        targets=targets,
        context=layer_context_for(game, game.controller_of(ability)),
    )


def delirium_damage(normal: int, with_delirium: int) -> Effect:
    """Unholy Heat: 2 damage, or 6 with delirium.

    "Unholy Heat deals 2 damage to target creature or planeswalker. *Delirium* -
    Unholy Heat deals 6 damage instead if there are four or more card types
    among cards in your graveyard."

    *Delirium* is an ability word, and CR 207.2c says an ability word has "no
    special rules meaning" - it only ties similar cards together. So there is no
    delirium machinery to build: the whole condition is the sentence after the
    word, counting card types (CR 205.2a) among the cards in the controller's
    graveyard. `count_card_types` in `machines/layers.py` already does that
    count for Tarmogoyf, and it is the same count here.

    Nothing about this is a choice, so unlike a scry or a "you may", this entry
    is the card's whole effect and not a policy standing in for a player.
    """

    def effect(game: "Game", spell: CardState) -> None:
        graveyard = game.controller_of(spell).graveyard
        amount = with_delirium if count_card_types(graveyard) >= 4 else normal
        for target in game.resolve_targets(spell):
            game.deal_damage(target, amount, source=spell)

    return effect


# --------------------------------------------------------------------------
# Tokens (CR 111, CR 701.7)
# --------------------------------------------------------------------------
#
# `models/token.py` holds what a token *is* and how one is created. What lives
# here is the other half: the printed text of each card that says "create ...",
# turned into a `TokenDefinition`. CR 111.3 is why that is a faithful reading and
# not a hand-written card - "the spell or ability that creates a token may define
# the values of any number of characteristics for the token. This becomes the
# token's 'text.'" The definition below each card *is* that sentence.

#: "0/1 colorless Eldrazi Spawn creature token with 'Sacrifice this token: Add
#: {C}.'" - Malevolent Rumble, Drowner of Truth, Kozilek's Command.
ELDRAZI_SPAWN = TokenDefinition(
    subtypes=("Eldrazi", "Spawn"),
    power=0,
    toughness=1,
    rules_text="Sacrifice this token: Add {C}.",
)

#: "1/1 white Cat creature token" - Ocelot Pride. Ajani, Nacatl Pariah's "2/1
#: white Cat Warrior creature token" and Spectral Procession's "1/1 white
#: Spirit creature tokens with flying" are not hand-written constants any more
#: (W4): both are `_parse_token_clause`'s shape, read off the card's own
#: printed text with no table row. `CAT` stays because `ocelot_pride_end_step`
#: keeps its row - Ocelot Pride's second sentence needs a token *copy*
#: (CR 707.2), which this wave's parser fails closed on, and CR 608.2c has no
#: notion of running half a trigger's text.
CAT = TokenDefinition(subtypes=("Cat",), colors=(Color.WHITE,), power=1, toughness=1)

#: "1/1 red Elemental creature token" - Seasoned Pyromancer.
ELEMENTAL = TokenDefinition(subtypes=("Elemental",), colors=(Color.RED,), power=1, toughness=1)

#: "1/1 white Monk creature token with prowess" - Cori-Steel Cutter. Prowess is
#: CR 702.108a, "Whenever you cast a noncreature spell, this creature gets +1/+1
#: until end of turn", and is printed on the token as the keyword it is.
MONK = TokenDefinition(
    subtypes=("Monk",), colors=(Color.WHITE,), power=1, toughness=1, keywords=("Prowess",)
)

#: "1/1 red Warrior creature token" - Dalkovan Encampment's, created tapped and
#: attacking (CR 508.4).
WARRIOR = TokenDefinition(subtypes=("Warrior",), colors=(Color.RED,), power=1, toughness=1)

#: "1/1 colorless Thopter artifact creature token with flying" - Hangarback
#: Walker, Thopter Assembly.
THOPTER = TokenDefinition(
    types=(Type.ARTIFACT, Type.CREATURE),
    subtypes=("Thopter",),
    power=1,
    toughness=1,
    keywords=("Flying",),
)


def ocelot_pride_end_step(game: "Game", ability: AbilityOnStack) -> None:
    """Ocelot Pride: "At the beginning of your end step, if you gained life this
    turn, create a 1/1 white Cat creature token. Then if you have the city's
    blessing, for each token you control that entered this turn, create a token
    that's a copy of it."

    Only the first sentence executes, and it executes **unconditionally**. Two
    deviations, both recorded in `docs/engine-coverage.md`:

    - "if you gained life this turn" is an intervening *if* (CR 603.4). Nothing
      tracks life gained during a turn, so `intervening_if_holds` reads the
      clause as true and the trigger always fires.
    - the second sentence needs the city's blessing (*ascend*, CR 702.131a: "If
      you control ten or more permanents and you don't have the city's blessing,
      you get the city's blessing for the rest of the game"), which is not
      modelled, and needs to know which tokens entered this turn, which nothing
      records. It is not attempted.
    """
    create_tokens(game, CAT, ability.controller)


def seasoned_pyromancer(game: "Game", ability: AbilityOnStack) -> None:
    """Seasoned Pyromancer: "When this creature enters, discard two cards, then
    draw two cards. For each nonland card discarded this way, create a 1/1 red
    Elemental creature token."

    In printed order (CR 608.2c): the discard, then the draw, then the tokens.
    "Discard this way" is a linked count over exactly the cards this discard put
    into the graveyard, which is why they are counted as they go rather than by
    looking at the graveyard afterwards.

    **Which two cards are discarded is the discarding player's own choice**
    (CR 701.9b: "By default, effects that cause a player to discard a card allow
    the affected player to choose which card to discard"), so this is a
    `CHOOSE_CARDS` question through `Game.ask`, the same CR 608.2d machinery as
    the cleanup discard. The candidates are offered in *reverse* hand order so
    that the unscripted default - `default_answer`'s "back of the offered
    cards" - lands on the *front* of the hand, reproducing the old hardcoded
    `hand[:2]` byte for byte when nobody answers.
    """
    player = game.player(ability.controller)
    hand = list(player.hand)
    amount = min(2, len(hand))
    decision = Decision(
        kind=DecisionKind.CHOOSE_CARDS,
        player=player.username,
        prompt=f"choose {amount} card(s) to discard",
        source=ability.source_name,
        amount=amount,
        cards=tuple(state.id for state in reversed(hand)),
    )
    chosen_ids = game.ask(decision)
    by_id = {state.id: state for state in hand}
    discarded = [by_id[card_id] for card_id in chosen_ids]
    for state in discarded:
        player.discard(state)
    player.draw(2)
    nonlands = sum(1 for state in discarded if not state.card.is_land)
    create_tokens(game, ELEMENTAL, ability.controller, nonlands)


def malevolent_rumble(game: "Game", spell: CardState) -> None:
    """Malevolent Rumble: "Reveal the top four cards of your library. You may put
    a permanent card from among them into your hand. Put the rest into your
    graveyard. Create a 0/1 colorless Eldrazi Spawn creature token with
    'Sacrifice this token: Add {C}.'"

    Revealing changes no game state and is not modelled. The optional "you may
    put a permanent card into your hand" is CR 608.2d's plain "you may" (there is
    no more specific numbered rule for choosing among a group of revealed cards)
    - asked with `Game.may`, whose default is to take it, matching the old
    hardcoded behaviour when nobody answers. *Which* permanent card is then a
    `CHOOSE_CARDS` question; the candidates are offered in reverse library order
    so the unscripted default - "back of the offered cards" - lands on the
    first permanent in library order, reproducing the old
    `next(... in revealed if state.is_permanent)` byte for byte. In printed
    order (CR 608.2c) the token is created last.
    """
    player = game.controller_of(spell)
    revealed = list(player.library[:4])
    permanents = [state for state in revealed if state.is_permanent]
    kept = None
    if permanents and game.may(player, "put a permanent card into your hand", source=spell.name):
        decision = Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=player.username,
            prompt="choose a permanent card to put into your hand",
            source=spell.name,
            amount=1,
            cards=tuple(state.id for state in reversed(permanents)),
        )
        chosen_ids = game.ask(decision)
        by_id = {state.id: state for state in permanents}
        kept = by_id[chosen_ids[0]]
    for state in revealed:
        player.zones[Zone.LIBRARY].remove(state)
        if state is kept:
            player.add(state, Zone.HAND)
        else:
            game.put_into_graveyard(state)
    create_tokens(game, ELDRAZI_SPAWN, player.username)


def hangarback_dies(game: "Game", ability: AbilityOnStack) -> None:
    """Hangarback Walker: "When this creature dies, create a 1/1 colorless Thopter
    artifact creature token with flying for each +1/+1 counter on this creature."

    The count is read off the counters the permanent had **as it last existed on
    the battlefield**. CR 122.2 destroys counters on a zone change and CR 603.10a
    makes a dies trigger look back in time at the object as it was, which is what
    `CardState.last_known_counters` (CR 704.8) is holding by the time this runs.
    """
    source = ability.source(game)
    if source is None:
        return
    counters = source.counters if source.zone is Zone.BATTLEFIELD else source.last_known_counters
    create_tokens(game, THOPTER, ability.controller, counters[Counter.PLUS_ONE])


def monstrous_rage(game: "Game", spell: CardState) -> None:
    """Monstrous Rage: "Target creature gets +2/+0 until end of turn. Create a
    Monster Role token attached to it."

    Both halves, in printed order (CR 608.2c).

    The +2/+0 is a continuous effect from a resolving spell (CR 611.2) in
    sublayer 7c (CR 613.4c), read off the card's own text by `machines/layers.py`'s
    `parsed_layer_effects` - the second sentence here, token creation, is not a
    continuous effect at all and is not something that parser reads.

    The Role is CR 111.10k's predefined token: "a colorless Aura Role enchantment
    token named Monster with enchant creature and 'Enchanted creature gets +1/+1
    and has trample.'" It is created **attached** to the target (CR 701.3a), so
    it never spends a moment unattached and CR 704.5m's state-based action -
    "if an Aura is attached to an illegal object or player, or is not attached to
    an object or player, that Aura is put into its owner's graveyard" - has
    nothing to do. What the Role grants is a static ability of the token, so it
    is a `LAYER_EFFECTS` entry keyed on the token's name, `"Monster"`.

    CR 303.7a and CR 704.5z are the reminder text in parentheses on the card:
    "If a permanent has more than one Role controlled by the same player attached
    to it, each of those Roles except the one with the most recent timestamp is
    put into its owner's graveyard." That state-based action is **not**
    dispatched by `Game.check_state_based_actions`; see `docs/engine-coverage.md`.
    """
    create_continuous_effect(game, spell)
    for target in game.resolve_card_targets(spell):
        if target.zone is Zone.BATTLEFIELD:
            create_tokens(
                game, MONSTER_ROLE, game.controller_of(spell).username, attached_to=target
            )


def take_an_extra_turn(game: "Game", spell: CardState) -> None:
    """Savor the Moment: "Take an extra turn after this one. Skip the untap step
    of that turn." (CR 500.7.)

    Only the first sentence. Skipping a step is a rules-modifying continuous
    effect (CR 611.3) with no home in this engine, so the extra turn untaps
    normally - recorded in `docs/engine-coverage.md`.
    """
    game.grant_extra_turn(game.controller_of(spell).username)


# --------------------------------------------------------------------------
# Looking at the top of your library (CR 701.22, CR 701.25)
# --------------------------------------------------------------------------


def scry(count: int) -> Effect:
    """ "Scry N" (CR 701.22a).

    "To 'scry N' means to look at the top N cards of your library, then put any
    number of them on the bottom of your library in any order and the rest on top
    of your library in any order."

    A decision, and `Game.scry` is what puts it to the player (CR 608.2d). Its
    default is to keep everything on top, which is a real answer - "any number"
    includes none - rather than a refusal to answer.

    CR 701.22b is why `Game.scry` is called even for 0: "If a player is
    instructed to scry 0, no scry event occurs", and the only way a scenario can
    tell "scried 0" from "did not scry" is that no question was asked. That
    distinction is `Game.scry`'s to make, not this function's.
    """

    def effect(game: "Game", spell: CardState) -> None:
        game.scry(game.controller_of(spell), count, source=spell.name)

    return effect


# --------------------------------------------------------------------------
# Prevention effects (CR 615)
# --------------------------------------------------------------------------


def prevent_all_combat_damage(game: "Game", spell: CardState) -> None:
    """Fog and Angelsong: "Prevent all combat damage that would be dealt this turn."

    CR 615.1a: "Effects that use the word 'prevent' are prevention effects.
    Prevention effects use 'prevent' to indicate what damage will not be dealt."

    Named neither a permanent nor a player, so the shield protects everything -
    `card_id` and `player` both left None. It is a `ShieldKind.ALL`, which
    CR 615.3 distinguishes from the other two by how it ends: "Such effects last
    until they're used up or their duration has expired." This one is never used
    up. It expires, in the cleanup step (CR 514.2), which is what
    `until_end_of_turn` means.

    CR 615.4 is the reason this is all the spell does: "Prevention effects must
    exist before the appropriate damage event occurs - they can't 'go back in
    time'." A Fog cast after combat damage has been dealt prevents nothing, and
    that falls out of creating the shield now rather than needing a check.

    Angelsong's cycling is a way to *not* cast it (CR 702.29a) and is
    `machines/casting.py`'s business, not this function's.
    """
    from ..models.game import PreventionShield, ShieldKind

    game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.ALL,
            label="prevent all combat damage that would be dealt this turn",
            controller=game.controller_of(spell).username,
            combat_only=True,
        )
    )


def prevent_next_damage_to_target(amount: int) -> Effect:
    """Bandage: "Prevent the next 1 damage that would be dealt to any target this
    turn." Then "Draw a card", which the registry sequences separately.

    CR 615.7 is this shield exactly: "Some prevention effects generated by the
    resolution of a spell or ability refer to a specific amount of damage - for
    example, 'Prevent the next 3 damage that would be dealt to any target this
    turn.' These work like shields. Each 1 damage that would be dealt to the
    'shielded' permanent or player is prevented. Preventing 1 damage reduces the
    remaining shield by 1 ... Once the shield has been reduced to 0, any
    remaining damage is dealt normally. Such effects count only the amount of
    damage; the number of events or sources dealing it doesn't matter."

    "Any target" is a permanent or a player (CR 115.1), which is why the shield
    is built with whichever of `card_id` and `player` the target turned out to be.
    A target that is no longer legal is skipped by CR 608.2b before this runs.
    """

    def effect(game: "Game", spell: CardState) -> None:
        from ..models.game import PreventionShield, ShieldKind

        controller = game.controller_of(spell).username
        for target in game.resolve_targets(spell):
            shielded = target if isinstance(target, CardState) else None
            game.create_prevention_shield(
                PreventionShield(
                    kind=ShieldKind.AMOUNT,
                    label=f"prevent the next {amount} damage that would be dealt "
                    f"to {getattr(target, 'name', None) or target.username} this turn",
                    controller=controller,
                    amount=amount,
                    card_id=None if shielded is None else shielded.id,
                    player=None if shielded is not None else target.username,
                )
            )

    return effect


def prevent_the_next_damage_from_target(game: "Game", spell: CardState) -> None:
    """Awe Strike: "The next time target creature would deal damage this turn,
    prevent that damage. You gain life equal to the damage prevented this way."

    CR 615.8: "Some prevention effects generated by the resolution of a spell or
    ability refer to the next time a specific source would deal damage. These
    effects prevent the next instance of damage from that source, regardless of
    how much damage that is. Once an instance of damage from that source has been
    prevented, any subsequent instances of damage that would be dealt by that
    source are dealt normally."

    So the shield names a *source*, not a shielded object: `source_id` is the
    targeted creature and `card_id`/`player` stay None, because the damage is
    prevented wherever it was going.

    The rider is CR 615.5: "Some prevention effects also include an additional
    effect, which may refer to the amount of damage that was prevented. The
    prevention takes place at the time the original event would have happened;
    the rest of the effect takes place immediately afterward." "You gain life
    equal to the damage prevented this way" is such an effect, so the shield
    carries `gains_life_when_prevented=True` and `Game.apply_prevention_shield`
    performs it as the damage event is prevented.
    """
    from ..models.game import PreventionShield, ShieldKind

    for target in game.resolve_card_targets(spell):
        game.create_prevention_shield(
            PreventionShield(
                kind=ShieldKind.NEXT_INSTANCE,
                label=f"prevent the next damage {target.name} would deal this turn",
                controller=game.controller_of(spell).username,
                source_id=target.id,
                gains_life_when_prevented=True,
            )
        )


#: Effects by card name. Everything absent resolves without doing anything.
#
# "Lightning Bolt": "Lightning Bolt deals 3 damage to any target." is not
# entered here any more - a single clause of exactly the shape
# `parse_targeted_effect_for_spell` reads off the card's own printed text, so
# `effect_for`'s fallback reaches it (and any future card with the same
# shape, for free). Re-adding a row here would silently shadow the parser
# again; see `test_no_card_has_a_registry_entry_that_would_shadow_the_targeted_effect_parser`.
#
# "Lightning Helix": "Lightning Helix deals 3 damage to any target and you
# gain 3 life." is not entered here any more either - it mixes a targeted
# clause and a player clause, which `parse_mixed_effect_for_spell` now reads
# clause by clause, trying the targeted parser and then the player parser on
# each one. See `test_registry_is_minimal.py`.
#
# "Counterspell": "Counter target spell." is not entered here any more
# either (this wave): `_COUNTER_TARGET_SPELL_RE`, added for a modal card's
# own unconditional "Counter target spell." mode (Cryptic Command), is read
# by `_parse_targeted_clause` off the card's own text with no row needed, so
# `effect_for`'s fallback reaches it too. See `test_registry_is_minimal.py`.
EFFECTS: dict[str, Effect] = {
    # "Swords to Plowshares": "Exile target creature. Its controller gains
    # life equal to its power." is not entered here any more (this wave):
    # `_parse_anaphoric_clause_pair` reads both sentences as one CR 608.2c
    # instruction off the card's own printed text, so `effect_for`'s fallback
    # reaches it - and reads the life gain the old `exile_targets` row never
    # did. See `test_registry_is_minimal.py`.
    "Electrolyze": sequence(deal_divided_damage(2), draw_cards(1)),
    # CR 608.2c: the switch first, then the draw, in the order printed.
    "Twisted Image": sequence(create_continuous_effect, draw_cards(1)),
    # "Giant Growth" and "Dismember" are not entered here any more (W5): both
    # are exactly `_CONTINUOUS_PUMP_OR_KEYWORD_RE`'s shape, read off the
    # card's own printed text (Dismember's Phyrexian-mana reminder line
    # stripped like any other), so `effect_for`'s fallback reaches them. See
    # `test_registry_is_minimal.py`.
    # "Lava Dart deals 1 damage to any target." The flashback half of the card
    # (CR 702.34) is a way to cast it, not part of what it does on resolution,
    # so it belongs to machines/casting.py and not here.
    "Lava Dart": deal_damage(1),
    "Unholy Heat": delirium_damage(2, 6),
    # "Mutagenic Growth" and "Assault Strobe" are not entered here any more
    # (W5) either, for the same reason as Giant Growth and Dismember above.
    # +1/+0 and first strike, plus double strike with delirium. Layers 6 and 7c.
    "Violent Urge": create_continuous_effect,
    # -- tokens (CR 111, CR 701.7a) -------------------------------------
    # Spectral Procession's "Create three 1/1 white Spirit creature tokens
    # with flying." is not entered here any more (W4): the whole spell is one
    # clause of `_parse_token_clause`'s shape, read off the card's own printed
    # text, so `effect_for`'s fallback reaches it. See
    # `tests/scenarios/test_registry_is_minimal.py`.
    "Malevolent Rumble": malevolent_rumble,
    "Monstrous Rage": monstrous_rage,
    # "Take an extra turn after this one" (CR 500.7).
    "Savor the Moment": take_an_extra_turn,
    # Preordain's "Scry 2, then draw a card." is not entered here any more:
    # it is two clauses of exactly the shape `parse_player_effect_for_spell`
    # reads off the card's own printed text (`scry N`, then `draw a card`),
    # so `effect_for`'s fallback reaches it. See
    # `tests/scenarios/test_registry_is_minimal.py`.
    # -- decisions during resolution (CR 608.2d) ------------------------
    # -- prevention (CR 615) --------------------------------------------
    "Fog": prevent_all_combat_damage,
    # Angelsong is Fog with cycling bolted on; the cycling is a way to discard
    # it rather than cast it (CR 702.29a) and never reaches this table.
    "Angelsong": prevent_all_combat_damage,
    # "Prevent the next 1 damage that would be dealt to any target this turn.
    # Draw a card." Printed order again (CR 608.2c).
    "Bandage": sequence(prevent_next_damage_to_target(1), draw_cards(1)),
    "Awe Strike": prevent_the_next_damage_from_target,
}


def effect_for(card_name: str, effect_text: str | None = None) -> Effect | None:
    """A spell's effect: an explicit `EFFECTS` row if there is one, otherwise
    `parse_mixed_effect_for_spell` on the card's own oracle text - one
    per-clause dispatcher that tries each clause as a targeted clause and then
    as a player clause, so a card mixing both kinds (Lightning Helix) parses
    without needing a row. An explicit row always wins, so nothing already
    scripted changes behaviour.

    A modal card (CR 700.2's bulleted "Choose one/two/...") is dispatched to
    `resolve_modal_spell` instead: `_prepare_effect_clauses` refuses modal text
    outright (a bulleted list is not a linear sequence of clauses), so nothing
    would otherwise reach it. `resolve_modal_spell` reads which modes were
    chosen off `Game.cast_record` and runs each one's own clause, keyed by
    nothing but the card's own printed text - no per-card row needed here
    either.
    """
    explicit = EFFECTS.get(card_name)
    if explicit is not None:
        return explicit
    if effect_text is None:
        return None
    if is_modal_text(effect_text):
        return resolve_modal_spell
    return _spell_effect_or_notice(effect_text)


# --------------------------------------------------------------------------
# What abilities do (CR 608.2 resolution, for objects that are not cards)
# --------------------------------------------------------------------------


def _opponents(game: "Game", username: str) -> list:
    return [player for player in game.players_in_game if player.username != username]


def damage_each_opponent(amount: int) -> AbilityEffect:
    """Guttersnipe: "this creature deals 2 damage to each opponent" (CR 119.3).

    "This creature" is the source (CR 120.2b), and CR 113.7a lets it be gone by
    the time the ability resolves - the damage is then dealt by nothing this
    engine can point at, which `Game.deal_damage` accepts as `source=None`.
    """

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        for opponent in _opponents(game, ability.controller):
            game.deal_damage(opponent, amount, source=source)

    return effect


def damage_the_attacked_player(amount: int) -> AbilityEffect:
    """Hellrider: "deals 1 damage to the player or planeswalker it's attacking".

    "It" is the creature that attacked, so the damage follows the *triggering*
    creature's defender rather than the source's - which is the whole point of
    Hellrider triggering once per attacker. Only a player defender is dealt
    damage; damage to a planeswalker needs loyalty counters, which are not
    modelled.
    """

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        if event is None or event.defender is None or not event.defender.is_player:
            return
        target = game.resolve_target(event.defender)
        if target is not None:
            game.deal_damage(target, amount, source=ability.source(game))

    return effect


def damage_the_other_combatant(amount: int) -> AbilityEffect:
    """Ashmouth Hound: "deals 1 damage to that creature".

    "That creature" is the other half of the blocking pair: the attacker when the
    source blocked, the blocker when the source became blocked (CR 509.1a).
    """

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        if event is None:
            return
        other_id = event.related_id if event.subject_id == ability.source_id else event.subject_id
        other = game.find_by_id(other_id) if other_id is not None else None
        if other is not None and other.zone is Zone.BATTLEFIELD:
            game.deal_damage(other, amount, source=ability.source(game))

    return effect


def delver_upkeep(game: "Game", ability: AbilityOnStack) -> None:
    """Delver of Secrets: "look at the top card of your library. You may reveal
    that card. If an instant or sorcery card is revealed this way, transform this
    creature."

    Not an intervening *if* (CR 603.4) - the condition is inside the effect, so
    the ability triggers and goes on the stack whatever is on top of the library,
    and only the transform is conditional. The optional reveal is always taken.
    """
    player = game.player(ability.controller)
    if not player.library:
        return
    top = player.library[0]
    if not set(top.card.types) & {Type.INSTANT, Type.SORCERY}:
        return
    source = ability.source(game)
    if source is not None and source.zone is Zone.BATTLEFIELD:
        source.transform()  # CR 701.27a


def thopter_assembly_upkeep(game: "Game", ability: AbilityOnStack) -> None:
    """Thopter Assembly: "return this creature to its owner's hand and create five
    1/1 colorless Thopter artifact creature tokens with flying."

    Only the first half happens. Tokens are not modelled anywhere in this engine
    (`CardState` has no token flag), so the five Thopters are not created - which
    is why this card's intervening *if* keeps being true turn after turn here.
    """
    source = ability.source(game)
    if source is None or source.zone is not Zone.BATTLEFIELD:
        return
    game.return_to_hand(source)


def exile_ability_targets(game: "Game", ability: AbilityOnStack) -> None:
    """Exile every card this ability still legally targets (CR 608.2b).

    Not battlefield-only: CR 406.2/701.13a exile "from whatever zone it's
    currently in", and Faerie Macabre's "Exile up to two target cards from
    graveyards" and Keen-Eyed Curator's "Exile target card from a graveyard"
    both name one - measured working end to end this session
    (`tests/scenarios/test_targeted_effect_parser.py`). `game.resolve_targets`
    already rechecks each target against the printed restriction's own zones
    (CR 608.2b), and `Game.exile_permanent` is zone-agnostic (see its
    docstring), so nothing else here needs to filter by zone - doing so used
    to silently drop every graveyard-exile card's whole effect.

    One look-alike stays unreached by this: Tormod's Crypt and Bojuka Bog's
    "exile target player's graveyard" *targets the player*, not a card
    (`allows_cards=False`), so this function's `isinstance(target, CardState)`
    check silently skips it - exiling one player's whole graveyard is a
    different effect shape this wave does not build. Kozilek's Command's
    "Exile up to X target cards from graveyards" is one mode of a modal
    spell and *does* reach this function now, through `resolve_modal_spell`
    (`parse_mode_effect` falls back to `parse_mixed_effect_for_spell`, which
    reads this shape the same way any non-modal card's text would).
    """
    for target in game.resolve_targets(ability):
        if isinstance(target, CardState):
            game.exile_permanent(target)


def tishanas_tidebinder(game: "Game", ability: AbilityOnStack) -> None:
    """ "Counter up to one target activated or triggered ability."

    CR 113.9: "Activated and triggered abilities on the stack aren't spells, and
    therefore can't be countered by anything that counters only spells.
    Activated and triggered abilities on the stack can be countered by spells
    and abilities that specifically counter abilities." `Game.counter` handles
    both, removing the ability from the stack and putting it nowhere (CR 405.1).

    The target is looked for on the stack by id rather than through
    `Game.resolve_target`, which only ever finds `CardState`s - the same reason
    `counter_targets` walks the stack itself.

    **The second sentence** - "If an ability of an artifact, creature, or
    planeswalker is countered this way, that permanent loses all abilities for
    as long as this creature remains on the battlefield" - is a layer 6
    continuous effect (CR 613.1f) created by this resolving ability (CR 611.2),
    with the "for as long as" duration of CR 611.2b. It is recorded in the
    game's `ContinuousEffects` store, and CR 611.2b's corner case is handled
    there: a Tidebinder that has already left the battlefield when this trigger
    resolves creates nothing, because the duration never starts.

    The countered ability's *source* is the permanent that loses its abilities,
    which is why the source is read off the ability before it is countered - by
    then the ability object is gone from the stack (CR 405.1).

    None of this is reachable yet. `Game.resolve_target` only ever finds a
    `CardState`, so the trigger's target resolves to nothing and CR 608.2b
    removes the trigger before this runs at all - see `docs/engine-coverage.md`
    and the xfails in `tests/scenarios/test_countering_an_ability.py`.
    """
    store: ContinuousEffects | None = continuous_effects(game)
    tidebinder = ability.source(game)
    for reference in ability.targets:
        if not reference.is_card:
            continue
        target = next(
            (item for item in game.stack if is_ability(item) and item.id == reference.card_id),
            None,
        )
        if target is None:
            continue
        permanent = game.find_by_id(target.source_id) if target.source_id else None
        game.counter(target)
        if store is None or tidebinder is None:
            continue
        if permanent is not None and permanent.zone is Zone.BATTLEFIELD:
            store.create(tidebinder, targets=[permanent])


def damage_ability_targets(amount: int) -> AbilityEffect:
    """An activated or triggered ability that deals damage to what it targets.

    Goblin Bombardment's "This enchantment deals 1 damage to any target". The
    source is the permanent, and CR 120.7 says "the source of damage is the
    object that dealt it" - which matters for lifelink and for protection, both
    of which `Game.deal_damage` reads off the source. The sacrifice is part of
    the *cost* (CR 602.1a), paid before the ability is ever put on the stack, so
    nothing about it belongs in the resolution.

    Damage does not destroy anything by itself (CR 120.5): a creature dies to
    the state-based action that follows.
    """

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        for target in game.resolve_targets(ability):
            game.deal_damage(target, amount, source=source)

    return effect


def destroy_ability_targets(game: "Game", ability: AbilityOnStack) -> None:
    """Destroy each permanent this ability still legally targets (CR 701.8a).

    "To destroy a permanent, move it from the battlefield to its owner's
    graveyard." Ghost Quarter's half of the deal. The other half - "Its
    controller may search their library for a basic land card, put it onto the
    battlefield" - is `_parse_search_clause`'s "its controller may" shape (see
    `_build_search_clause`), a separate clause because it is the *opponent's*
    optional choice and not the activator's.
    """
    for target in game.resolve_targets(ability):
        if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
            game.destroy(target)


def _search_library(
    game: "Game",
    player: Player,
    matches: Callable[[CardState], bool],
    *,
    source: str | None = None,
) -> CardState | None:
    """Find and remove one matching card from a player's library, then shuffle.

    CR 701.23a: "To search for a card in a zone, look at all cards in that zone
    (even if it's a hidden zone) and find a card that matches the given
    description." The whole library is looked at, not just the top.

    `optional=True` is CR 701.23b and is right for every card that reaches here:
    "If a player is searching a hidden zone for cards with a **stated quality**,
    such as a card with a certain card type or color, that player isn't required
    to find some or all of those cards even if they're present in that zone."
    Every search in this registry names a quality - a basic land, a Mountain or
    Plains card, a creature card with mana value 1 or less - so failing to find
    is always a legal answer. It is *not* CR 701.23d's "simply a quantity of
    cards", which must find what is there.

    **The shuffle happens now.** CR 701.24a randomizes the library and CR 701.24b
    keeps the found card out of it: "the found cards aren't included in the
    shuffle ... all the cards in that library except those are shuffled." Taking
    the card out first and shuffling the rest is the same event. `Game` seeds the
    shuffle from `shuffle_seed`, so a scenario stays reproducible while the
    library really is randomized - which is what a scenario asserting on library
    order after a fetch has to reckon with.

    The card is taken from the library here; the caller decides where it goes.
    """
    found = game.search_library(player, matches, count=1, optional=True, source=source)
    return found[0] if found else None


def has_land_type(*subtypes: str) -> Callable[[CardState], bool]:
    """A card with any of these land subtypes, basic or not (CR 305.6).

    The fetchlands say "Search your library for a Mountain or Plains card" -
    the *land types*, not the card names - which is exactly why a shockland
    (`Land - Mountain Plains`) is a legal find and a Wastes is not.
    """
    wanted = {subtype.lower() for subtype in subtypes}

    def matches(state: CardState) -> bool:
        return bool(wanted & {subtype.lower() for subtype in state.card.subtypes})

    return matches


#: "[You may|Its controller may] search your[/their] library for a[n]
#: <quality> card[ with mana value N or less][, reveal it], put it/that card
#: into your hand OR onto the battlefield [tapped][, then shuffle]." - the
#: shape shared by every fetchland, Flagstones of Trokair's death trigger,
#: Expedition Map, Ghost Quarter and White Orchid Phantom's second half (the
#: *subject* is "its controller", not "you" - CR 701.23g's search is offered
#: to whichever player the sentence names), and Ranger-Captain of Eos (the
#: mana-value bound). `fullmatch` is deliberate: a card whose search is
#: followed by more text of its own - Nahiri, the Harbinger's -8 goes on to
#: grant haste and bounce the card it found - does not match, and falls
#: through to no scripted effect rather than a half-right one. The trailing
#: "then shuffle" is optional here because a clause reaching this regex from
#: the multi-clause dispatcher has already had its "then shuffle" tail
#: reattached by `_rejoin_search_clauses` - the group still has to be
#: *readable*, just not mandatory at the regex level.
_SEARCH_AND_PUT_RE = re.compile(
    # "Its controller may search ..." is deliberately not an alternative here
    # any more - that subject names a different player than whoever controls
    # the resolving spell or ability, and `_parse_anaphoric_clause_pair` reads
    # it off the *previous* clause's target instead of off this one's own
    # "subject" group (see that function and `_search_and_place_for`).
    r"(?P<subject>you may )?"
    r"search (?:your|their) library for (?:a|an) (?P<quality>.+?) card"
    r"(?: with mana value (?P<max_mv>\d+) or less)?"
    r"(?:, reveal it)?"
    r", put (?:it|that card) (?P<dest>into your hand|onto the battlefield(?P<tapped> tapped)?)"
    r"(?:, then shuffle)?\.?",
    re.IGNORECASE,
)


def _named_type_matcher(word: str) -> Callable[[CardState], bool]:
    """One word of a search's stated quality: a land type or a card type.

    "Mountain or Plains" names land *types* (CR 305.6, CR 205.3i), which is why
    a shockland is a legal find under its own name; a search naming a card type
    instead ("artifact or creature card") is CR 205.2a's list. Trying both and
    taking either is exactly what a one-word quality needs, since a word is
    never both at once.
    """
    land_type = has_land_type(word)
    try:
        card_type: Type | None = Type(word.lower())
    except ValueError:
        card_type = None

    def matches(state: CardState) -> bool:
        return land_type(state) or (card_type is not None and card_type in state.card.types)

    return matches


def _quality_matcher(quality: str) -> Callable[[CardState], bool]:
    """A predicate for "a `<quality>` card" out of a search sentence.

    "Basic land" adds CR 205.4c's supertype check on top of whatever the rest
    of the phrase already means. Anything else is one or more type/subtype
    words joined by "or" or a comma - fetchlands print two, Flagstones one -
    and matching any one of them is enough, the same "or" the card prints.
    """
    lowered = quality.strip().lower()
    if lowered.startswith("basic "):
        rest = _quality_matcher(lowered.removeprefix("basic "))

        def basic_matches(state: CardState) -> bool:
            return rest(state) and Supertype.BASIC in state.card.supertypes

        return basic_matches
    words = [word.strip() for word in re.split(r",\s*|\s+or\s+", lowered) if word.strip()]
    matchers = [_named_type_matcher(word) for word in words]

    def matches(state: CardState) -> bool:
        return any(matcher(state) for matcher in matchers)

    return matches


def _quality_description(quality: str, max_mv: str | None) -> str:
    """The stated quality, for a `Game.may`/`Game.ask` prompt - "basic land",
    "creature with mana value 1 or less".
    """
    if max_mv is None:
        return quality
    return f"{quality} with mana value {max_mv} or less"


def _bounded_quality_matcher(quality: str, max_mv: str | None) -> Callable[[CardState], bool]:
    """`_quality_matcher`, ANDed with a mana value ceiling when the sentence
    names one - Ranger-Captain of Eos's "with mana value 1 or less".

    Mana value is CR 202.3's number, `Card.cmc` here. An **X** in this spot
    (Green Sun's Zenith, Fiend Artisan) never reaches this function at all:
    `_SEARCH_AND_PUT_RE`'s `max_mv` group is `\\d+` and does not match the
    letter X, so the whole clause fails to match and the search-clause parser
    returns `None` for it - the engine does not model the X binding (CR 107.3),
    and failing closed here is that gap staying closed rather than silently
    treating X as unbounded or as zero.
    """
    base = _quality_matcher(quality)
    if max_mv is None:
        return base
    ceiling = int(max_mv)

    def matches(state: CardState) -> bool:
        return base(state) and (state.card.cmc or 0) <= ceiling

    return matches


def _search_and_place_for(
    match: re.Match[str], *, optional: bool
) -> Callable[["Game", Player, str], None]:
    """The core of one search-and-put match - search, then place the find -
    as a function of **whichever player is doing it**, independent of who
    controls the resolving spell or ability.

    Read off the match's own quality/mana-value/tapped/destination groups
    once, the same way `_build_search_clause` always has; only *who* the
    player is, and whether the search is optional, have moved out to the
    caller. `_build_search_clause` supplies the resolving spell or ability's
    own controller and reads "you may" off its own match for `optional`;
    `_parse_referent_clause`'s search branch (`_REFERENT_SEARCH_RE`) matches
    against text with no subject of its own left in it at all (the "its
    controller"/"that player" was already consumed by
    `_ANAPHORIC_SUBJECT_RE`) and is always the printed "may" - the resolution
    of *which player* has moved out of the search parser entirely and into
    `_parse_anaphoric_clause_pair`, which reads it off the previous clause's
    target rather than off this one's own text.
    """
    quality = match.group("quality")
    max_mv = match.group("max_mv")
    matches = _bounded_quality_matcher(quality, max_mv)
    description = _quality_description(quality, max_mv)
    tapped = bool(match.group("tapped"))
    to_hand = match.group("dest").startswith("into your hand")

    def run(game: "Game", player: Player, source: str) -> None:
        if optional and not game.may(
            player, f"search your library for a {description} card", source=source
        ):
            return
        found = _search_library(game, player, matches, source=source)
        if found is None:
            return
        if to_hand:
            player.add(found, Zone.HAND)
        else:
            game.put_onto_battlefield(found, player.username, tapped=tapped)

    return run


def _build_search_clause(match: re.Match[str], *, for_spell: bool) -> TargetedClause:
    """The effect for one `_SEARCH_AND_PUT_RE` match, as a `TargetedClause` -
    usable directly by `parse_search_and_put_effect`'s whole-text callers and
    by `_parse_mixed_clause`'s per-clause dispatch alike.

    Always the resolving spell or ability's own controller (CR 701.23g's "you
    may" is that player's choice). "Its controller may search ..." - Ghost
    Quarter's and White Orchid Phantom's own half of the deal - is a different
    sentence naming a different player and is read by
    `_parse_anaphoric_clause_pair` instead, paired with the destroy clause
    ahead of it; `_SEARCH_AND_PUT_RE`'s subject group no longer offers that
    alternative at all (see the regex's own comment).
    """
    optional = bool((match.group("subject") or "").strip())
    run = _search_and_place_for(match, optional=optional)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        run(game, game.controller_of(stack_object), source)

    return effect


def _parse_search_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """One clause of a search, fed either the whole ability text (a fetchland
    with nothing else on it) or one clause a multi-clause dispatcher split out
    and rejoined - see `_rejoin_search_clauses`.
    """
    match = _SEARCH_AND_PUT_RE.fullmatch(clause.strip())
    if match is None:
        return None
    return _build_search_clause(match, for_spell=for_spell)


def parse_search_and_put_effect(text: str) -> AbilityEffect | None:
    """Recognise a plain library search off the ability's own printed text,
    instead of a per-card table entry - see `_SEARCH_AND_PUT_RE`.

    A fetchland's cost (CR 602.1a: everything before the colon - {T}, pay 1
    life, sacrifice the land) is `machines/cost.py`'s business; this is only
    the effect after it, and the same function reads Flagstones of Trokair's
    trigger and Expedition Map's activated ability, because all three are one
    sentence of this shape with nothing else in it.

    The found card arrives **untapped** unless the sentence says "tapped"
    (CR 110.5b's default for anything entering the battlefield) - a shockland
    found this way then asks its own "as this land enters, you may pay 2 life"
    question, a replacement effect (CR 614.12) `Game.enter_the_battlefield`
    already consults. `put_onto_battlefield` is used and not a land drop:
    CR 305.1's one-land-per-turn restriction applies to *playing* a land, and
    this is an effect putting one there.

    "Reveal it" changes no state this model tracks (CR 701.23e: an effect that
    does not print "reveal" does not reveal, and the ones that do have nothing
    else to show for it here). The printed "you may" is asked as CR 701.23g;
    either way, CR 701.23b makes "find nothing" a legal answer for a search
    naming a stated quality, so an empty or exhausted library just does
    nothing. The first match in library order is taken unless a scenario rigs
    it - and the library is genuinely shuffled afterwards (CR 701.24a), so the
    rig only survives until the search happens.
    """
    return _parse_search_clause(text, for_spell=False)


# --------------------------------------------------------------------------
# Single-clause player effects, read off the ability's own printed text
# --------------------------------------------------------------------------

#: Spelled-out numbers small enough that a real card prints them this way -
#: Griselbrand's "Draw seven cards" is the reason this exists at all.
_NUMBER_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_COUNT = r"(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)"


def _count(word: str) -> int:
    return int(word) if word.isdigit() else _NUMBER_WORDS[word.lower()]


#: A clause's effect on one player, once the controller has been worked out -
#: the same shape whether that controller came from a spell (CR 608.2c) or
#: from a triggered or activated ability (CR 603.3a, CR 602.2). `source` is a
#: display name only, passed through to `Game.scry`/`Game.surveil` for their
#: decision prompts.
ClauseEffect = Callable[["Game", Player, str], None]

# CR 119.3: "If an effect causes a player to gain life or lose life, that
# player's life total is adjusted accordingly." No card in the pool phrases
# this on anyone but "you" without also naming a target ("target player
# loses 1 life" - Blood Artist) or being a cost ("Pay 7 life" is CR 118, not
# an effect) - so only "you" is recognised; a targeted or "each"/"opponent"
# phrasing is deliberately left to the targeted-effects wave.
_GAIN_LIFE_RE = re.compile(rf"you gains? (?P<n>{_COUNT}) life", re.IGNORECASE)
_LOSE_LIFE_RE = re.compile(rf"you loses? (?P<n>{_COUNT}) life", re.IGNORECASE)
# CR 107.14: "The energy symbol is {E}. It represents one energy counter."
_ENERGY_RE = re.compile(r"(?:you )?gets? (?P<e>(?:\{e\})+)", re.IGNORECASE)
# CR 121.1/121.2: drawing, one card at a time. The "you" is often left
# implicit - a triggered or activated ability's effect just says "Draw a
# card."
_DRAW_RE = re.compile(rf"(?:you )?draws? (?:a card|(?P<n>{_COUNT}) cards?)", re.IGNORECASE)
# CR 701.17a: "puts that many cards from the top of their library into their
# graveyard."
_MILL_RE = re.compile(rf"(?:you )?mills? (?:a card|(?P<n>{_COUNT}) cards?)", re.IGNORECASE)
# CR 701.25a / CR 701.22a.
_SURVEIL_RE = re.compile(r"surveils? (?P<n>\d+)", re.IGNORECASE)
#: "Scry N" (Preordain, most spells) and "Target player scries N" (Kozilek's
#: Command's third-person mode) - `scr(?:y|ies)` reads both conjugations.
_SCRY_RE = re.compile(r"scr(?:y|ies) (?P<n>\d+)", re.IGNORECASE)


def _mill(game: "Game", player: Player, count: int) -> None:
    """CR 701.17a, routed through `Game.put_into_graveyard` the way
    `Game.surveil` moves its own graveyard-bound cards - so a replacement
    effect watching a card enter a graveyard (Rest in Peace) still gets its
    say (CR 614.1a).
    """
    for card in player.library[:count]:
        game.put_into_graveyard(card)


def parse_clause_effect(clause: str) -> ClauseEffect | None:
    """One clause of an effect with nobody to ask a question of: a plain life
    total change, an energy grant, a draw, a mill, a surveil or a scry.

    `fullmatch` throughout, on purpose - the same discipline
    `parse_search_and_put_effect` uses. A clause with anything else in it
    (a target, a "you may", a number this parser cannot read) matches nothing
    and comes back `None`, which `parse_player_effect` below treats as reason
    to run *none* of the effect rather than part of it.
    """
    clause = clause.strip()
    # CR 207.2a: reminder text in parentheses is not rules text - "get {E}
    # (an energy counter)" and "surveil 1 (Look at ...)" both carry one.
    clause = re.sub(r"\s*\([^()]*\)\s*$", "", clause).strip().rstrip(".").strip()

    if match := _GAIN_LIFE_RE.fullmatch(clause):
        amount = _count(match.group("n"))
        return lambda game, player, source: player.gain_life(amount)

    if match := _LOSE_LIFE_RE.fullmatch(clause):
        amount = _count(match.group("n"))
        return lambda game, player, source: player.lose_life(amount)

    if match := _ENERGY_RE.fullmatch(clause):
        amount = len(re.findall(r"\{e\}", match.group("e"), re.IGNORECASE))
        return lambda game, player, source: player.add_counters(Counter.ENERGY, amount)

    if match := _DRAW_RE.fullmatch(clause):
        amount = _count(match.group("n")) if match.group("n") else 1
        return lambda game, player, source: game.draw_cards(player.username, amount)

    if match := _MILL_RE.fullmatch(clause):
        amount = _count(match.group("n")) if match.group("n") else 1
        return lambda game, player, source: _mill(game, player, amount)

    if match := _SURVEIL_RE.fullmatch(clause):
        amount = int(match.group("n"))
        return lambda game, player, source: game.surveil(player, amount, source=source)

    if match := _SCRY_RE.fullmatch(clause):
        amount = int(match.group("n"))
        return lambda game, player, source: game.scry(player, amount, source=source)

    return None


#: "You may <clause>." (CR 608.2d turned into an optional wave-1 clause). This
#: is checked ahead of the plain shapes above, on the clause *before* the
#: optional wrapper is peeled off - `parse_clause_effect` itself never sees
#: the words "you may", so a bare "you may draw a card" still comes back
#: `None` from it, unchanged.
_YOU_MAY_RE = re.compile(r"^you may (?P<clause>.+)$", re.IGNORECASE | re.DOTALL)


def _optional_clause(inner: ClauseEffect, prompt: str) -> ClauseEffect:
    """Wrap an already-parsed clause so it only runs if `Game.may` says yes.

    CR 608.2d: "if a cost or effect allows a player to choose to do something
    ... that player is not required to make that choice unless the effect
    specifically says the player must." `Game.may`'s own default is to take
    the option, which is the engine-wide convention this reuses rather than
    reargues.
    """

    def effect(game: "Game", player: Player, source: str) -> None:
        if game.may(player, prompt, source=source):
            inner(game, player, source)

    return effect


def _parse_optional_player_clause(clause: str) -> ClauseEffect | None:
    """`clause`, or its `"you may "` prefix peeled off and wrapped optional.

    Wrapping only ever happens over a clause `parse_clause_effect` already
    understands - fail-closed stays in force: "you may <something this wave
    cannot read>" comes back `None` here exactly as it would un-wrapped, so
    the caller throws away the whole effect instead of asking a question it
    could not carry out.
    """
    if match := _YOU_MAY_RE.match(clause):
        inner_text = match.group("clause").strip()
        # "You may gain 1 life" drops the "you" the way "you may draw a
        # card" drops "you" before "draw" - `_DRAW_RE` reads past an absent
        # "you" with `(?:you )?`, but `_GAIN_LIFE_RE`/`_LOSE_LIFE_RE` require
        # it, so a clause that fails without it is retried with it restored
        # before being given up on.
        inner = parse_clause_effect(inner_text) or parse_clause_effect(f"you {inner_text}")
        if inner is None:
            return None
        return _optional_clause(inner, inner_text)
    return parse_clause_effect(clause)


#: Sentence boundaries, and the two joining words CR 608.2c's "in the order
#: written" has to step across: "you gain 1 life and get {E}" (Guide of
#: Souls) and "Scry 2, then draw a card" (Preordain).
_CLAUSE_SEPARATOR = re.compile(r"\.\s+|\n+|,?\s+\bthen\b\s+|\s+\band\b\s+", re.IGNORECASE)


def split_effect_clauses(text: str) -> list[str]:
    """Break an effect into the clauses CR 608.2c executes in order.

    "The controller of the spell or ability follows its instructions in the
    order written" - so a multi-clause effect is not one opaque blob, it is a
    sequence, and each piece is checked and run on its own.
    """
    text = text.strip()
    # CR 207.2a: a spell's own printed text is not run through
    # `machines/abilities.py`'s reminder stripping the way an ability's
    # `effect` field is, so Preordain's trailing "(To scry 2, look at ...)"
    # is still here and would otherwise be split into clauses of its own.
    while True:
        stripped = re.sub(r"\s*\([^()]*\)\s*$", "", text).strip()
        if stripped == text:
            break
        text = stripped
    text = text.rstrip(".")
    return [clause.strip() for clause in _CLAUSE_SEPARATOR.split(text) if clause.strip()]


#: A cost paid before the spell is cast (CR 118.8a) - never part of what the
#: spell does on resolution, but printed on the same line block Bone
#: Splinters, Fumarole, and Cathartic Reunion put ahead of their effect.
_ADDITIONAL_COST_LINE_RE = re.compile(
    r"^As an additional cost to cast this spell, [^.]+\.\s*", re.IGNORECASE | re.MULTILINE
)
#: A static quality of the spell itself, not an instruction it carries out -
#: Abrupt Decay prints this ahead of its "Destroy target nonland permanent
#: with mana value 3 or less."
_CANT_BE_COUNTERED_LINE_RE = re.compile(
    r"^This spell can't be countered\.\s*", re.IGNORECASE | re.MULTILINE
)
#: A genuinely modal card (CR 700.2 - a bulleted list preceded by a "Choose
#: ..." instruction) needs a registry keyed by mode, not by card - a later
#: wave's job. Bailing here keeps a modal card's one parseable mode from being
#: read as the card's one and only effect - true whether that mode happens to
#: be a targeted clause (Abrade's "Destroy target artifact.") or a plain
#: player clause, which is exactly the fails-open shape a modal card with
#: every mode player-parseable would hit if this check lived only on the
#: targeted side.
#:
#: `is_modal_text` (backed by `machines/modes.py`'s real CR 700.2 parser) is
#: used rather than a prefix match on "Choose", because plenty of cards read
#: "Choose target creature ..." or "Choose a creature type" as ordinary
#: instruction text with no bulleted list at all - Galvanic Discharge and
#: Surgical Extraction, among this pool's fixtures, were losing their entire
#: effect to that over-broad match before this fix.


#: A whole line that is nothing but reminder text (CR 207.2a: "Reminder text
#: is italicized text within parentheses that summarizes a rule that applies
#: to that card"). `split_effect_clauses` already strips one trailing at the
#: very end of the text; Dismember and Mutagenic Growth print theirs *first*
#: instead - "({G/P} can be paid with either {G} or 2 life.)\nTarget creature
#: gets +2/+2 until end of turn." - so a line-anywhere strip is needed too.
#: Reminder text is never rules text regardless of where it sits, so this is
#: safe wherever it matches.
_REMINDER_LINE_RE = re.compile(r"^[ \t]*\([^()]*\)[ \t]*\n+", re.MULTILINE)


def _strip_non_effect_preamble(text: str) -> str:
    """Sentences that describe the spell but are not part of resolving it."""
    text = _ADDITIONAL_COST_LINE_RE.sub("", text)
    text = _CANT_BE_COUNTERED_LINE_RE.sub("", text)
    text = _REMINDER_LINE_RE.sub("", text)
    return text


#: A bare "shuffle" left over once `split_effect_clauses` has cut across the
#: "then" inside a search's own "..., then shuffle." - CR 608.2c's clause
#: split has no notion that this particular "then" is the tail of the
#: sentence before it (CR 701.24a) rather than a separate instruction, the
#: same way it does not know "scry 2, then draw a card" (Preordain) *is* two
#: real instructions. `_rejoin_search_clauses` tells the two apart the only
#: way available here: a bare "shuffle" clause is reattached to whatever
#: clause precedes it if and only if that clause is itself a search.
_BARE_SHUFFLE_RE = re.compile(r"shuffle", re.IGNORECASE)
_MENTIONS_SEARCH_RE = re.compile(r"\bsearch(?:es)?\b", re.IGNORECASE)


def _rejoin_search_clauses(clauses: list[str]) -> list[str]:
    """Reattach a split-off "shuffle" to the search clause it belongs to.

    "Its controller may search their library for a basic land card, put it
    onto the battlefield, then shuffle." splits into three raw clauses -
    "destroy target land", "Its controller may search ... battlefield", and
    "shuffle" - because `_CLAUSE_SEPARATOR` treats every "then" alike. Only the
    last two are one CR 608.2c instruction; put back together, the merged
    clause is exactly what `_SEARCH_AND_PUT_RE` (with its own trailing "then
    shuffle" optional) expects to read as one clause among several.
    """
    merged: list[str] = []
    for clause in clauses:
        if (
            merged
            and _BARE_SHUFFLE_RE.fullmatch(clause.strip())
            and _MENTIONS_SEARCH_RE.search(merged[-1])
        ):
            merged[-1] = f"{merged[-1]}, then {clause.strip()}"
        else:
            merged.append(clause)
    return merged


def _prepare_effect_clauses(text: str) -> list[str] | None:
    """`text`, refused outright if modal (CR 700.2) and otherwise stripped of
    its non-effect preamble (CR 118.8a's additional cost line, "This spell
    can't be countered"), split into CR 608.2c clauses, and rejoined where a
    search's own "then shuffle" was cut apart from it - see
    `_rejoin_search_clauses`.

    Shared by the targeted clause parser, the player clause parser, and the
    mixed dispatcher below so all three refuse and strip and rejoin the same
    way. Before this was shared, only the targeted path bailed on a modal card
    - a modal card whose every mode happened to be a plain player clause
    (gain life, draw, ...) would have `split_effect_clauses` cut straight
    across the bullet points and run every mode as if it were one linear
    effect, which is a fails-open bug, not merely a missed one. Cathartic
    Reunion is the other half of the fix: its additional-cost line was being
    read as an unparseable effect clause and taking the whole thing down, when
    the cost is not part of resolution at all (CR 118.8a).
    """
    if is_modal_text(text):
        return None
    clauses = _rejoin_search_clauses(split_effect_clauses(_strip_non_effect_preamble(text)))
    return clauses or None


def _parse_player_clauses(text: str) -> list[ClauseEffect] | None:
    """Every clause of `text`, or `None` the moment one of them fails to parse.

    Fail-closed on purpose: CR 608.2c has no notion of running half an effect,
    and a half-executed spell - the mana paid, one clause resolved, the next
    silently skipped - is a wrong game state that looks like a right one. A
    single unparseable clause (a target, a choice, anything this wave does not
    cover) throws away every clause around it too, even the ones that would
    have parsed fine alone.
    """
    clauses = _prepare_effect_clauses(text)
    if clauses is None:
        return None
    parsed = [_parse_optional_player_clause(clause) for clause in clauses]
    if any(effect is None for effect in parsed):
        return None
    return parsed  # type: ignore[return-value]


def parse_player_effect(text: str) -> AbilityEffect | None:
    """A triggered or activated ability's effect, read off its own printed
    text instead of a per-card table entry - see `parse_clause_effect` and
    `split_effect_clauses`.

    This is what fixes Guide of Souls: "Whenever another creature you control
    enters, you gain 1 life and get {E}" used to go on the stack, resolve, and
    change nothing, because no table row taught the model either half of it.
    """
    clauses = _parse_player_clauses(text)
    if clauses is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.player(ability.controller)
        for clause in clauses:
            clause(game, player, ability.source_name)

    return effect


def parse_player_effect_for_spell(text: str) -> Effect | None:
    """The spell-resolution twin of `parse_player_effect`, for an instant or
    sorcery with no table row - Mishra's Bauble aside, a plain "gain life /
    draw / mill / surveil / scry" spell has no cost or target to complicate
    it, so the same clause parser reads it off `Card.oracle_text` directly.
    """
    clauses = _parse_player_clauses(text)
    if clauses is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        player = game.controller_of(spell)
        for clause in clauses:
            clause(game, player, spell.card.name)

    return effect


# --------------------------------------------------------------------------
# Single-clause TARGETED effects, read off the ability's own printed text
# --------------------------------------------------------------------------
#
# The targeted twin of the parser above: "Destroy target creature.", "Exile
# target artifact.", "<Source> deals N damage to target X." (and "to any
# target"), "Return target X to its owner's hand.", "Tap"/"Untap target X.",
# and "Put N +1/+1 (or -1/-1) counters on target X." One restriction ("target
# X") per clause. Destroy, exile, return, tap/untap, and put-counters accept
# CR 115.6's "up to N"/"N or M target ..." too, because the verb repeats
# itself once per legal target regardless of how many there are - `deal_damage`
# is the one exception, kept to exactly one mandatory target, because multiple
# damage targets divide a total at announcement (CR 601.2d) rather than
# repeating the verb, and that division is `deal_divided_damage`'s job, not
# this parser's. See `_targets_understood`'s `count_agnostic`.
#
# The restriction is read through `machines/targeting.py`'s own parser
# (`profile_for_text`) rather than a second regex here, and the same parser
# is what `Game.legal_target` rechecks on resolution (CR 608.2b) - so this
# module can never disagree with it about what a card targets.

#: This guard used to refuse *any* clause mentioning mana value, converted
#: mana cost, power, toughness, or "if" outright, because
#: `machines/targeting.py` used to read past a "with mana value N or less" /
#: "if it has mana value N or less" comparison without enforcing it -
#: `understood=True` with the comparison silently dropped. That is fixed now:
#: `TargetRequirement` carries `comparison_attribute` / `comparison_operator`
#: / `comparison_value`, read by `_read_phrase` and enforced for real by
#: `TargetRequirement.rejects` (`_rejects_comparison`), which `Game.legal_target`
#: consults on resolution (CR 608.2b) - verified this session:
#: `profile_for_text("target nonland permanent with mana value 3 or less")`
#: (Abrupt Decay) and `profile_for_text("target creature if it has mana value
#: 2 or less")` (Fatal Push) both now come back with `comparison_attribute`
#: set, and `_rejects_comparison` fails closed ("Fails closed, never open")
#: when the value cannot be pinned down. So the mana-value/power/toughness
#: half of the old blanket refusal is stale and is not carried forward.
#:
#: "if" on its own is not the same thing. `_read_phrase` only strips a
#: recognised comparison out of the leftover text after the noun; an
#: unrelated conditional - "target creature if it's your turn", or a second
#: "if" the parser does not tie to a comparison - is simply dropped as
#: unexamined leftover, with `understood` still left `True`. Trusting that
#: would still destroy or exile something broader than the card allows, so
#: `_targets_understood` refuses a phrase with "if" that is *not* accounted
#: for by an actual `comparison_attribute` it read out of that same phrase -
#: which is precisely what keeps Fatal Push working (its "if" *is* the
#: comparison) while still refusing a hypothetical unrelated conditional.
_UNENFORCED_CONDITIONAL_RE = re.compile(r"\bif\b", re.IGNORECASE)

#: A trailing duration on the clause itself - "exile target ... **until this
#: enchantment leaves the battlefield**" (Static Prison), "... **until end of
#: turn**". CR 611.2a: "A continuous effect generated by the resolution of a
#: spell or ability lasts as long as stated by the spell or ability creating
#: it (such as 'until end of turn'). If no duration is stated, it lasts
#: indefinitely." `destroy_ability_targets`/`exile_ability_targets`/etc. state
#: no duration at all - they act once and never reverse it - so they are only
#: a correct reading of a clause that likewise states none. A clause that
#: names one needs the reversal this wave does not build, and running the
#: verb without it would create a permanent effect out of a temporary one:
#: exiling "until this enchantment leaves the battlefield" for good. Refused
#: here, so the whole clause list comes back `None` (fail-closed) rather than
#: quietly dropping the duration.
_TRAILING_DURATION_RE = re.compile(r"\buntil\b|\bfor as long as\b", re.IGNORECASE)


def _targets_understood(
    phrase: str,
    *,
    count_agnostic: bool = False,
    battlefield_only: bool = True,
    allow_player_targets: bool = False,
) -> bool:
    """Whether this wave may act on `phrase` - "target creature", "any
    target", "up to two target creatures", "another target permanent".

    `phrase` is the *whole* "target ..." expression, count words included -
    "up to two" and "another" both sit **before** the word "target", so a
    caller that trimmed the phrase down to only what follows "target" would
    silently throw the count away and let this wave misread "up to two target
    creatures" as a single mandatory target. Confidence means all of:
    `machines/targeting.py` understood the phrase, it is exactly one
    requirement (two "target" words is two requirements, not this shape), any
    "if" in it is accounted for by a comparison the requirement actually
    carries rather than being unexamined leftover text (see
    `_UNENFORCED_CONDITIONAL_RE`), it does not carry a trailing duration this
    wave's unconditional verbs cannot honour, and - only when
    `battlefield_only` is set - every target it takes lives on the
    battlefield.

    `battlefield_only` is `True` by default because most of this file's verbs
    are: CR 701.8a only lets destroy move something "from the battlefield",
    and CR 701.26a/701.26b define tap and untap only for "a permanent", which
    CR 110.1 puts on the battlefield. `exile_ability_targets` and
    `return_ability_targets_to_hand` pass `False` - CR 406.2/701.13a exile
    "from whatever zone it's currently in" and CR 701.19a's "return" names no
    particular origin zone either, so Faerie Macabre's "target cards from
    graveyards" and Raise Dead's "target creature card from your graveyard"
    are exactly what those two verbs are supposed to reach. Whichever zones
    the printed text names, `Game.legal_target` rechecks them again on
    resolution (CR 608.2b), so nothing here has to widen what is trusted.

    `count_agnostic=True` is CR 115.6's "up to N"/"N or M target ..." for a
    verb whose semantics genuinely do not change with the count - destroy,
    exile, tap, untap, return, and put-counters all just repeat themselves
    once per legal target, including "up to one" resolving to zero (CR 608.2b
    already skips an illegal target the same way). Damage never sets this:
    multiple targets divide a damage total at announcement (CR 601.2d,
    Electrolyze), which is a different mechanism `deal_damage` does not
    model, so damage keeps the strict single-mandatory-target rule regardless
    of what the caller asks for.
    """
    if _TRAILING_DURATION_RE.search(phrase):
        return False
    profile = profile_for_text(phrase)
    if not profile.understood or len(profile.requirements) != 1:
        return False
    requirement = profile.requirements[0]
    if _UNENFORCED_CONDITIONAL_RE.search(phrase) and requirement.comparison_attribute is None:
        return False
    if battlefield_only and requirement.zones != frozenset({Zone.BATTLEFIELD}):
        return False
    if not allow_player_targets and requirement.allows_players:
        # Destroy, exile, return, tap/untap, and put-counters all operate on a
        # `CardState` only (`isinstance` checks throughout this file) - a
        # phrase that can name a *player* (Thraben Charm's "any number of
        # target players' graveyards") would otherwise "understand" the
        # phrase and hand back a verb that silently does nothing to the
        # player it targeted. Only `deal_damage`/`damage_ability_targets`
        # pass `allow_player_targets=True`, because CR 115.1's "any target"
        # genuinely includes a player and `Game.deal_damage` accepts one.
        return False
    if requirement.unbounded:
        return False
    if count_agnostic:
        return True
    return requirement.minimum == 1 and requirement.maximum == 1


def return_ability_targets_to_hand(game: "Game", stack_object: "StackObject") -> None:
    """Return each permanent this still legally targets to its owner's hand.

    Not battlefield-only, for the same reason `exile_ability_targets` is not:
    CR 701.19a's "return" names no particular origin zone, and Raise Dead's
    "target creature card in your graveyard" is exactly this shape.
    `game.resolve_targets` already rechecks each target against the printed
    restriction's own zones (CR 608.2b), and `Game.return_to_hand` is
    zone-agnostic (see its docstring), so there is nothing left to filter
    here - a battlefield-only filter used to silently drop every
    graveyard-or-exile return card's whole effect.
    """
    for target in game.resolve_targets(stack_object):
        if isinstance(target, CardState):
            game.return_to_hand(target)


def tap_ability_targets(game: "Game", stack_object: "StackObject") -> None:
    """Tap each permanent this still legally targets (CR 701.26a)."""
    for target in game.resolve_targets(stack_object):
        if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
            target.tap()


def untap_ability_targets(game: "Game", stack_object: "StackObject") -> None:
    """Untap each permanent this still legally targets (CR 701.26b)."""
    for target in game.resolve_targets(stack_object):
        if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
            target.untap()


def put_counters_on_ability_targets(kind: Counter, amount: int) -> TargetedClause:
    """Put counters on each permanent this still legally targets (CR 122.1)."""

    def effect(game: "Game", stack_object: "StackObject") -> None:
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                game.add_counters(target, kind, amount)

    return effect


#: `phrase` always captures from the word "target" itself (or "any target")
#: to the end of the clause, count words and all - `_targets_understood`
#: needs the count word, if any, to see "up to two" and refuse it.
_DESTROY_TARGET_RE = re.compile(r"destroy (?P<phrase>(?:any target|.*target.+))", re.IGNORECASE)
_EXILE_TARGET_RE = re.compile(r"exile (?P<phrase>(?:any target|.*target.+))", re.IGNORECASE)
#: "Counter target spell." - the unconditional shape (CR 701.5a), as opposed
#: to Mystic Confluence's "Counter target spell unless its controller pays
#: {3}." or Cryptic Command's own "Counter target spell or ability.", neither
#: of which this reaches: the trailing `$` refuses anything printed after
#: "spell", rather than silently dropping a condition the card actually has.
_COUNTER_TARGET_SPELL_RE = re.compile(r"^counter target spell\.?$", re.IGNORECASE)
_RETURN_TARGET_RE = re.compile(
    r"return (?P<phrase>.*target.+?) to its owner'?s hand", re.IGNORECASE
)
#: "Tap target X." and "Untap target X." - and Kiora's Follower's "Untap
#: *another* target permanent", where "another" sits between the verb and
#: "target" and is part of the captured phrase so a count word there is not
#: silently thrown away.
_TAP_UNTAP_TARGET_RE = re.compile(r"(?P<verb>tap|untap) (?P<phrase>.*target.+)", re.IGNORECASE)
#: "<Source> deals N damage to target X." and "... to any target." The source
#: is never named here - `deal_damage`/`damage_ability_targets` already read
#: it off whichever of a spell or an ability is resolving (CR 120.2b).
_DAMAGE_TARGET_RE = re.compile(
    rf".*\bdeals? (?P<n>{_COUNT}) damage to (?P<phrase>any target|.*target.+)", re.IGNORECASE
)
#: "Put N +1/+1 (or -1/-1) counters on target X." and Anafenza's "on
#: *another* target tapped creature you control" - the same reasoning as
#: `_TAP_UNTAP_TARGET_RE`.
_COUNTER_TARGET_RE = re.compile(
    rf"put (?P<n>{_COUNT}) (?P<kind>\+1/\+1|-1/-1) counters? on (?P<phrase>.*target.+)",
    re.IGNORECASE,
)
#: "Target creature gets +N/+N until end of turn." (Giant Growth, Dismember,
#: Mutagenic Growth) and "Target creature gains <keyword> until end of turn."
#: (Assault Strobe) - a continuous effect from a resolving spell (CR 611.2),
#: sublayer 7c or layer 6 (CR 613.4c, CR 613.1f). The combined shape, "gets
#: +N/+N *and gains* <keyword>" (Give In to Violence, Violent Urge), is not
#: this regex's job any more - `split_effect_clauses` cuts it in half on its
#: own "and" separator before this ever runs, so
#: `_merge_continuous_pump_keyword_clauses` below undoes that cut first. Routes
#: to `create_continuous_effect`, which reads the card's real text through
#: `machines/layers.py`'s `parsed_layer_effects` rather than anything
#: hard-coded to these two shapes.
_CONTINUOUS_PUMP_OR_KEYWORD_RE = re.compile(
    r"^target creature (?:gets [+-]\d+/[+-]\d+|gains [a-z ]+) until end of turn\.?$",
    re.IGNORECASE,
)

#: The pump half of a combined "gets +N/+N and gains <keyword>" sentence
#: (Give In to Violence: "Target creature gets +2/+2 and gains lifelink until
#: end of turn."), once `split_effect_clauses`'s own "and" separator has cut
#: the duration and the keyword off the end of it.
_BARE_CONTINUOUS_PUMP_RE = re.compile(r"^target creature gets [+-]\d+/[+-]\d+$", re.IGNORECASE)
#: The keyword half of the *reversed* order, "gains <keyword> and gets +N/+N"
#: - a shape this pool has no real card for, but CR 608.2c does not care which
#: half a card prints first, so it is read the same way as the forward order.
_BARE_CONTINUOUS_KEYWORD_START_RE = re.compile(
    r"^target creature gains [a-z]+(?: [a-z]+)?$", re.IGNORECASE
)
#: One more keyword in a run of them (Aerial Maneuver: "gains flying and first
#: strike" splits into a "gains flying" piece and a "first strike until end of
#: turn" piece, one bare word or two-word keyword name per clause, only the
#: last one carrying "until <duration>"). This does not check the word against
#: `Keyword` - that is `machines/layers.py`'s job once the whole spell reaches
#: `create_continuous_effect`; a keyword or a conjunction it does not know
#: (Aerial Maneuver's two keywords, Tainted Strike's infect) fails closed there
#: with a `LayerNotice` rather than never reaching a parser at all.
_CONTINUOUS_KEYWORD_CONTINUATION_RE = re.compile(
    r"^(?:gains?\s+)?(?P<word>[a-z]+(?:\s[a-z]+)?)"
    r"(?:\s+until\s+(?P<duration>end of turn|your next turn))?\.?$",
    re.IGNORECASE,
)
#: The pump half of the reversed order's tail, once "and" has cut it away from
#: the keyword that opened the sentence.
_BARE_CONTINUOUS_PUMP_TAIL_RE = re.compile(
    r"^gets [+-]\d+/[+-]\d+ until (?:end of turn|your next turn)\.?$", re.IGNORECASE
)


def _merge_continuous_pump_keyword_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Undo `split_effect_clauses`'s own "and" cut through "Target creature
    gets +N/+N and gains <keyword>[, and gains another, ...] until end of
    turn." (or its reverse) so the two or more clauses it left behind are
    handled as the one CR 608.2c instruction they actually are (CR 611.2), not
    several unreadable fragments.

    Spell-only: an ability's own continuous pump/keyword grant is never read
    off its printed text at all (`_CONTINUOUS_PUMP_OR_KEYWORD_RE`'s own
    docstring explains why) - it goes through `create_continuous_effect_of_ability`
    keyed by ability index instead, so this returns `None` outright when
    `for_spell` is false rather than guessing at a shape nothing here reads.

    Deliberately loose about what counts as "a keyword": this only recognises
    the *shape* the split left behind, not whether any word in it is one
    `machines/layers.py` or `machines/combat.py` actually models. Whatever gets
    merged back together is handed whole to `create_continuous_effect`, which
    reads the spell's own oracle text through `parsed_layer_effects` - the same
    parser a plain "gets +N/+N until end of turn." already goes through, and
    the one that turns a keyword it does not know, a reversed order it does not
    read, more than one keyword conjoined, or a duration other than "until end
    of turn" into a `LayerNotice` rather than a silent no-op.

    Returns how many clauses starting at `index` belong to this one
    instruction, and the effect to run for all of them, or `None` if `index`
    is not the start of this shape at all.
    """
    if not for_spell:
        return None
    first = clauses[index]
    if _BARE_CONTINUOUS_PUMP_RE.fullmatch(first):
        cursor = index + 1
        found_duration = False
        while cursor < len(clauses):
            match = _CONTINUOUS_KEYWORD_CONTINUATION_RE.fullmatch(clauses[cursor])
            if match is None:
                break
            cursor += 1
            if match.group("duration") is not None:
                found_duration = True
                break
        if found_duration:
            return cursor - index, create_continuous_effect  # type: ignore[return-value]
        return None
    if (
        _BARE_CONTINUOUS_KEYWORD_START_RE.fullmatch(first)
        and index + 1 < len(clauses)
        and _BARE_CONTINUOUS_PUMP_TAIL_RE.fullmatch(clauses[index + 1])
    ):
        return 2, create_continuous_effect  # type: ignore[return-value]
    return None


def _optional_targeted_clause(
    inner: TargetedClause, prompt: str, *, for_spell: bool
) -> TargetedClause:
    """The targeted twin of `_optional_clause`: "you may destroy target
    artifact" (Batterhorn), "you may exile target nonland permanent" (Angel of
    Sanctions), "you may return target creature to its owner's hand" (Angler
    Drake), "you may tap target creature" (Alaborn Cavalier, Angelic
    Benediction).

    `for_spell` picks how to name the asker and the source the same way
    `_parse_targeted_clause` already does: a spell's controller and its own
    name (CR 120.2b), or an ability's controller and `source_name`.
    """

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        if game.may(player, prompt, source=source):
            inner(game, stack_object)

    return effect


def _parse_targeted_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """One clause of a targeted effect, or `None` if this wave does not cover
    its shape or cannot confidently read its restriction.

    `for_spell` only changes which damage builder is used: `deal_damage`
    names the resolving spell as the source, `damage_ability_targets` names
    the permanent an ability came from - the same distinction those two
    existing functions already draw (CR 120.2b), not a new one made here.
    """
    clause = clause.strip()

    if match := _YOU_MAY_RE.match(clause):
        inner_text = match.group("clause").strip()
        inner = _parse_targeted_clause(inner_text, for_spell=for_spell)
        if inner is None:
            return None
        return _optional_targeted_clause(inner, inner_text, for_spell=for_spell)

    if for_spell and _CONTINUOUS_PUMP_OR_KEYWORD_RE.fullmatch(clause):
        # A continuous effect from a resolving spell (CR 611.2) - handing the
        # whole spell to `create_continuous_effect` rather than building
        # anything here, so the actual pump/keyword comes from
        # `machines/layers.py`'s `parsed_layer_effects` reading the card's own
        # text, not from this regex match. Ability-side text ("this creature
        # gets ...") is not read here: it reaches the same parser through
        # `create_continuous_effect_of_ability` instead, keyed by ability
        # index rather than a clause shape.
        return create_continuous_effect  # type: ignore[return-value]

    if _COUNTER_TARGET_SPELL_RE.fullmatch(clause):
        # `counter_targets` walks the stack for a targeted spell (CR 608.2b)
        # and is only meaningful for a resolving *spell* - an ability naming
        # this shape does not turn up in the pool, and guessing at one would
        # be worse than refusing it.
        return counter_targets if for_spell else None

    if match := _DESTROY_TARGET_RE.fullmatch(clause):
        if not _targets_understood(match.group("phrase"), count_agnostic=True):
            return None
        return destroy_ability_targets

    if match := _EXILE_TARGET_RE.fullmatch(clause):
        if not _targets_understood(
            match.group("phrase"), count_agnostic=True, battlefield_only=False
        ):
            return None
        return exile_ability_targets

    if match := _RETURN_TARGET_RE.fullmatch(clause):
        if not _targets_understood(
            match.group("phrase"), count_agnostic=True, battlefield_only=False
        ):
            return None
        return return_ability_targets_to_hand

    if match := _TAP_UNTAP_TARGET_RE.fullmatch(clause):
        if not _targets_understood(match.group("phrase"), count_agnostic=True):
            return None
        return (
            tap_ability_targets if match.group("verb").lower() == "tap" else untap_ability_targets
        )

    if match := _COUNTER_TARGET_RE.fullmatch(clause):
        if not _targets_understood(match.group("phrase"), count_agnostic=True):
            return None
        amount = _count(match.group("n"))
        kind = Counter.PLUS_ONE if match.group("kind") == "+1/+1" else Counter.MINUS_ONE
        return put_counters_on_ability_targets(kind, amount)

    if match := _DAMAGE_TARGET_RE.fullmatch(clause):
        # Damage never goes count-agnostic: multiple targets divide a damage
        # total at announcement (CR 601.2d), a different mechanism
        # `deal_damage`/`damage_ability_targets` do not model (see
        # `deal_divided_damage`, which is the real thing and is not reached
        # by this parser). The strict single-mandatory-target check stays.
        if not _targets_understood(match.group("phrase"), allow_player_targets=True):
            return None
        amount = _count(match.group("n"))
        return deal_damage(amount) if for_spell else damage_ability_targets(amount)

    return None


def _parse_targeted_clauses(text: str, *, for_spell: bool) -> list[TargetedClause] | None:
    """Every clause of a targeted effect, or `None` the moment one fails.

    Fail-closed for the same reason `_parse_player_clauses` is (CR 608.2c has
    no notion of running half an effect): a multi-clause card with one clause
    this wave does not cover - Assassin's Trophy's compensation, Fatal Push's
    Revolt line - throws away every clause around it too, rather than destroy
    or exile something and silently skip the rest of the sentence.
    """
    clauses = _prepare_effect_clauses(text)
    if clauses is None:
        return None
    parsed = [_parse_targeted_clause(clause, for_spell=for_spell) for clause in clauses]
    if any(effect is None for effect in parsed):
        return None
    return parsed  # type: ignore[return-value]


def parse_targeted_effect_for_spell(text: str) -> Effect | None:
    """A spell whose whole effect is one or more of this wave's targeted
    shapes, read off the card's own printed text instead of a per-card row -
    Bone Splinters, Utter End, Lightning Bolt.
    """
    clauses = _parse_targeted_clauses(text, for_spell=True)
    if clauses is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        for clause in clauses:
            clause(game, spell)

    return effect


def parse_targeted_effect(text: str) -> AbilityEffect | None:
    """The same, for a triggered or activated ability's own printed text -
    Ravenous Chupacabra, Aether Adept, Icy Manipulator, Kiora's Follower,
    Anafenza, the Foremost.
    """
    clauses = _parse_targeted_clauses(text, for_spell=False)
    if clauses is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        for clause in clauses:
            clause(game, ability)

    return effect


# --------------------------------------------------------------------------
# Single-clause TOKEN CREATION, read off the spell or ability's own text
# --------------------------------------------------------------------------
#
# CR 701.7a: "To create one or more tokens with certain characteristics, put
# the specified number of tokens with the specified characteristics onto the
# battlefield." A card names its token's characteristics in one of two shapes:
# "[create] [N] [P/T] [color(s)] [subtype(s)] [artifact] creature token[s]
# [with <keywords or a quoted ability>]" (Spectral Procession, Ajani, Nacatl
# Pariah, Wurmcoil Engine, Drowner of Truth), or CR 111.10's predefined tokens
# by name ("create a Food token"). `models/token.py` already holds what a
# token *is*; this is the other half W1-W3 built for damage, search, and
# player clauses - reading the noun phrase off the card's own printed text
# instead of a per-card `TokenDefinition` in this file.
#
# What is deliberately refused, both fail-closed for the reasons CR 707.2 and
# CR 608.2c give below:
#
# - **"a token that's a copy of ..."** (Repudiate, Fanatic of Rhonas's
#   eternalize, Caretaker's Talent, Tamiyo's -X, and Ocelot Pride's own second
#   sentence) needs the copied object's copiable values (CR 707.2), which this
#   parser does not read off anything - checked for and refused before the
#   noun-phrase regex is even tried, so it cannot be mistaken for one.
# - **A count this parser cannot read as a fixed number** - Hangarback
#   Walker's "for each +1/+1 counter on this creature", Seasoned Pyromancer's
#   "for each nonland card discarded this way", Ocelot Pride's "for each token
#   you control that entered this turn" - is not a `_COUNT` word at all, so
#   `_TOKEN_CLAUSE_RE` simply does not match text of that shape; nothing
#   silently falls back to a count of one.
# - **A tail after "with" that is not a single quoted ability or a keyword
#   from `_TOKEN_KEYWORDS`** fails the whole clause rather than dropping the
#   unread part - Hangarback Walker's "with flying for each +1/+1 counter on
#   this creature" is exactly this: `flying` alone is a known keyword, but the
#   tail as a whole is not, so `_parse_token_tail` returns nothing usable and
#   `_parse_generic_token_descriptor` refuses the whole token rather than
#   create one with the keyword and silently lose the count clause bolted onto
#   it (CR 608.2c has no notion of running half an instruction).


#: `desc` is everything between the count and the word "token(s)" - "1/1
#: white Spirit creature", "3/3 colorless Phyrexian Wurm artifact creature",
#: or a predefined token's own name ("Food", "tapped Powerstone"). `tail` is
#: whatever follows "with", read by `_parse_token_tail`. `\btokens?\b` a whole
#: word so a subtype that merely contains the letters "token" could never
#: match it - none in the pool do, but the boundary costs nothing.
_TOKEN_CLAUSE_RE = re.compile(
    rf"^(?:create )?(?P<n>{_COUNT}) (?P<desc>.+?) \btokens?\b(?:\s+with\s+(?P<tail>.+))?\.?$",
    re.IGNORECASE | re.DOTALL,
)

#: Keyword abilities simple enough to print as one bare word or two on a
#: token's tail - CR 702's list is much longer, but this is what the pool's
#: token-creating cards actually name. Read against `str.split`'s output
#: rather than the regex, so a compound like "first strike" survives the "or"
#: below untouched (`split_effect_clauses`'s own separator would otherwise cut
#: a bare "and" apart, which is why this is checked as parts, not re-split).
_TOKEN_KEYWORDS = {
    "flying",
    "deathtouch",
    "lifelink",
    "trample",
    "vigilance",
    "haste",
    "reach",
    "menace",
    "defender",
    "indestructible",
    "hexproof",
    "prowess",
    "first strike",
    "double strike",
}

_TOKEN_COLOR_WORDS = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}


def _parse_token_tail(tail: str | None) -> tuple[tuple[str, ...], str | None] | None:
    """The "with <...>" part of a token's noun phrase, or `None` if this wave
    cannot read it.

    Two shapes: a single quoted ability, printed on the token as its
    `rules_text` exactly as the card prints it - Drowner of Truth's "with
    'Sacrifice this token: Add {C}.'" - CR 111.3 makes that quoted sentence the
    token's stated text and this is a faithful transcription of it, not a
    hand-written ability. Or a comma/"and"-joined list of bare keywords from
    `_TOKEN_KEYWORDS` - Spectral Procession's "with flying", Wurmcoil Engine's
    "with deathtouch"/"with lifelink". Nothing else is read: a tail that is
    neither, or that mixes a keyword with something else (Hangarback Walker's
    "with flying for each +1/+1 counter on this creature"), returns `None` and
    takes the whole token clause with it.

    No tail at all - most of the pool's plain vanilla tokens - is the empty
    case, returned as `((), None)` rather than `None`, since "no tail" is a
    fully read clause and not a refusal.
    """
    if tail is None:
        return (), None
    tail = tail.strip()
    if quote := re.fullmatch(r'["“](?P<text>.+)["”]', tail, re.DOTALL):
        return (), quote.group("text")
    parts = [part.strip() for part in re.split(r",\s*|\s+and\s+", tail) if part.strip()]
    if not parts or any(part.lower() not in _TOKEN_KEYWORDS for part in parts):
        return None
    return tuple(part.title() for part in parts), None


def _parse_generic_token_descriptor(words: list[str], tail: str | None) -> TokenDefinition | None:
    """ "[P/T] [color(s)] subtype(s) [artifact] creature", as a `TokenDefinition`.

    Read right to left, the way the type line itself is built: "creature" -
    CR 205.2a - names the last word, an optional "artifact" ahead of it adds
    CR 205.2a's other type (Wurmcoil Engine's Wurms, Hangarback Walker's
    Thopters), an optional leading `P/T` sets power and toughness (CR 208.1),
    then zero or more colour words - or the explicit "colorless" CR 105.2
    calls out - and whatever capitalized words are left are the token's
    subtypes (CR 205.3, CR 111.4). A descriptor ending in anything but
    "creature", or with no subtype left over once the rest is stripped away,
    is not a shape this wave reads.
    """
    if not words or words[-1].lower() != "creature":
        return None
    words = words[:-1]
    types: tuple[Type, ...] = (Type.CREATURE,)
    if words and words[-1].lower() == "artifact":
        types = (Type.ARTIFACT, Type.CREATURE)
        words = words[:-1]
    power = toughness = None
    if words and re.fullmatch(r"\d+/\d+", words[0]):
        power_text, toughness_text = words[0].split("/")
        power, toughness = int(power_text), int(toughness_text)
        words = words[1:]
    colors: list[Color] = []
    while words and words[0].lower() in (*_TOKEN_COLOR_WORDS, "and"):
        if words[0].lower() != "and":
            colors.append(_TOKEN_COLOR_WORDS[words[0].lower()])
        words = words[1:]
    if words and words[0].lower() == "colorless":
        words = words[1:]
    if not words or not all(word[:1].isupper() for word in words):
        return None
    read_tail = _parse_token_tail(tail)
    if read_tail is None:
        return None
    keywords, rules_text = read_tail
    return TokenDefinition(
        types=types,
        subtypes=tuple(words),
        colors=tuple(colors),
        power=power,
        toughness=toughness,
        keywords=keywords,
        rules_text=rules_text,
    )


def _token_creation_clause(
    definition: TokenDefinition, count: int, *, tapped: bool
) -> TargetedClause:
    """ "Create [count] [definition]" (CR 701.7a), as a `TargetedClause`.

    The creating player is CR 111.2's owner and controller - whoever controls
    the resolving spell or ability - so this reads `game.controller_of` the
    same way every other clause in this dispatcher does.
    """

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        create_tokens(game, definition, controller, count, tapped=tapped)

    return effect


def _parse_token_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """One clause of "create ... token(s)" (CR 701.7a), read off the card's
    own printed text - see the section banner above for what this reads and
    what it refuses.
    """
    clause = clause.strip()

    if match := _YOU_MAY_RE.match(clause):
        inner_text = match.group("clause").strip()
        inner = _parse_token_clause(inner_text, for_spell=for_spell)
        if inner is None:
            return None
        return _optional_targeted_clause(inner, inner_text, for_spell=for_spell)

    if "copy of" in clause.lower():
        return None  # CR 707.2 copying needs copiable values this wave does not read.

    match = _TOKEN_CLAUSE_RE.fullmatch(clause)
    if match is None:
        return None
    count = _count(match.group("n"))
    words = match.group("desc").strip().split()
    tail = match.group("tail")

    tapped = bool(words) and words[0].lower() == "tapped"
    if tapped:
        words = words[1:]
    if not words:
        return None

    predefined_name = " ".join(words)
    if tail is None and predefined_name in PREDEFINED:
        return _token_creation_clause(PREDEFINED[predefined_name], count, tapped=tapped)

    definition = _parse_generic_token_descriptor(words, tail)
    if definition is None:
        return None
    return _token_creation_clause(definition, count, tapped=tapped)


# --------------------------------------------------------------------------
# Modal spells (CR 700.2): one chosen mode's own effect
# --------------------------------------------------------------------------
#
# Every parser above reads a whole card's or ability's text, on the working
# assumption that whoever controls it is the one doing everything in it -
# "you" for a player clause, the resolving spell's own controller for a
# targeted or token clause. That assumption breaks for a mode printed with a
# *player* as its own grammatical subject: Kozilek's Command's "Target player
# creates X ... tokens ..." and "Target player scries X, then draws a card."
# are not the caster's own actions at all - they belong to whichever player
# was targeted, who is very often an opponent. Nothing above reads that
# shape, so it gets its own two parsers here, tried before the ordinary
# per-clause dispatcher (`parse_mixed_effect_for_spell`) that already reads
# every mode with no player-subject of its own - Abrade's "Destroy target
# artifact.", Thraben Charm's "Destroy target enchantment.", Mystic
# Confluence's "Return target creature to its owner's hand." and "Draw a
# card.", and Kozilek's Command's own "Exile target creature with mana value
# X or less." and "Exile up to X target cards from graveyards.".

#: "Target player creates N <token descriptor> tokens[ with <tail>]." - the
#: token twin of `_TOKEN_CLAUSE_RE`, with the count and the tail read exactly
#: the same way (`_parse_generic_token_descriptor`/`_parse_token_tail`, quoted
#: granted ability included), but the *creator* is whichever player this mode
#: targets, not the caster (CR 111.2's owner-and-controller is decided by who
#: creates the token, and CR 700.2 puts that choice on the sentence's own
#: subject). `creates?` reads both "creates" (third person, as printed here)
#: and a hypothetical "create".
_TARGET_PLAYER_TOKEN_RE = re.compile(
    rf"^target player creates? (?P<n>{_COUNT}) (?P<desc>.+?) \btokens?\b"
    rf"(?:\s+with\s+(?P<tail>.+))?\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_target_player_token_mode(text: str) -> Effect | None:
    """Kozilek's Command's mode 1: "Target player creates X 0/1 colorless
    Eldrazi Spawn creature tokens with "Sacrifice this token: Add {C}.""

    X has already been substituted by the time this is called
    (`substitute_x`, not `mode_rules_text` - the quoted granted ability has to
    survive, which `mode_rules_text`'s quote-blanking would not let it), so
    "creates X ..." arrives as "creates 1 ...", a plain `_COUNT` the same
    `_parse_generic_token_descriptor`/`_parse_token_tail` already read for
    every other token-creating card - CR 111.3's "This becomes the token's
    'text'" applies exactly the same to a token a target player creates as to
    one the caster creates.
    """
    match = _TARGET_PLAYER_TOKEN_RE.fullmatch(text.strip())
    if match is None:
        return None
    if "copy of" in text.lower():
        return None  # CR 707.2 copying needs copiable values this wave does not read.
    count = _count(match.group("n"))
    words = match.group("desc").strip().split()
    if not words:
        return None
    definition = _parse_generic_token_descriptor(words, match.group("tail"))
    if definition is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        for target in game.resolve_targets(spell):
            if isinstance(target, Player):
                create_tokens(game, definition, target.username, count)

    return effect


#: "Target player <does something>[, then <does something else>]." -
#: Kozilek's Command's mode 2, "Target player scries X, then draws a card."
#: `rest` is everything after the subject, DOTALL so a card printing this
#: across more than one sentence is still read as one phrase.
_TARGET_PLAYER_CLAUSE_RE = re.compile(r"^target player (?P<rest>.+)$", re.IGNORECASE | re.DOTALL)


def _parse_target_player_mode(text: str) -> Effect | None:
    """A mode whose subject is "target player" rather than "you" - the same
    plain-clause vocabulary `parse_clause_effect` already reads (scry, draw,
    mill, surveil, a life total, energy), run against whichever player this
    mode targets instead of the resolving spell's own controller.

    Split the same way `split_effect_clauses` splits a whole card - "scries
    X, then draws a card" is two instructions carried out in the order printed
    (CR 608.2c), both by the *same* named player, which is exactly why this
    cannot simply hand the two halves to `parse_player_effect_for_spell`:
    that function's clauses each independently mean "you", the resolving
    spell's controller, and only the first of these two means "target
    player" on its own - the continuation still refers back to it.
    """
    match = _TARGET_PLAYER_CLAUSE_RE.match(text.strip())
    if match is None:
        return None
    rest = match.group("rest").strip().rstrip(".").strip()
    sub_clauses = [part.strip() for part in _CLAUSE_SEPARATOR.split(rest) if part.strip()]
    if not sub_clauses:
        return None
    parsed: list[ClauseEffect] = []
    for sub in sub_clauses:
        clause_effect = parse_clause_effect(sub) or parse_clause_effect(f"you {sub}")
        if clause_effect is None:
            return None
        parsed.append(clause_effect)

    def effect(game: "Game", spell: CardState) -> None:
        for target in game.resolve_targets(spell):
            if isinstance(target, Player):
                for clause_effect in parsed:
                    clause_effect(game, target, spell.card.name)

    return effect


def parse_mode_effect(mode: Mode, x_value: int) -> Effect | None:
    """One chosen mode's own effect (CR 700.2a), read off its printed text
    with X already substituted throughout it (CR 107.3a, CR 107.3c).

    Tries the two "target player ..." shapes first, since nothing else here
    reads a mode whose subject is a targeted player rather than the caster;
    falls back to `parse_mixed_effect_for_spell`, the same per-clause
    dispatcher a whole non-modal card's text goes through, for every other
    mode shape - a mode is exactly one card's worth of CR 608.2c instructions
    once it is standing on its own, X already substituted and no bulleted
    list left for `is_modal_text` to trip over.
    """
    text = _strip_non_effect_preamble(substitute_x(mode.text, x_value)).strip()
    if not text:
        return None
    token_for_player = _parse_target_player_token_mode(text)
    if token_for_player is not None:
        return token_for_player
    player_subject = _parse_target_player_mode(text)
    if player_subject is not None:
        return player_subject
    return parse_mixed_effect_for_spell(text)


class ModeNotice(BaseModel):
    """One chosen mode of a resolving modal spell (CR 700.2a) whose text this
    wave could not read into an effect.

    The same "unreadable is not the same as no effect" record `TargetingNotice`,
    `InterveningIfNotice`, `CostModifierNotice`, and `LayerNotice` already keep
    for their own gaps (see each's own docstring) - `resolve_modal_spell`
    appends one of these for a mode it cannot perform instead of the mode
    silently doing nothing, which would otherwise be indistinguishable from a
    mode that legitimately has no effect left to have (Mystic Confluence's
    "Draw a card." with the library empty, say).
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    mode_number: int
    """The mode's 1-based position on the card (CR 700.2), for a player or a
    log to point back at the printed bullet."""
    text: str
    """The mode's own printed text, X substituted, for whoever reads this
    notice later."""


def resolve_modal_spell(game: "Game", spell: CardState) -> None:
    """CR 700.2a: run each mode this spell was cast with, independently, in
    the order printed on the card.

    CR 702.42b, entwine's own resolution rule, generalizes past entwine
    itself: "follow the text of each of the modes in the order written on the
    card when the spell resolves" is how *any* modal spell with more than one
    chosen mode resolves, entwined or not - entwine only changes how many
    modes got chosen, never how they are carried out once chosen.

    **Fail-closed per mode, not per spell.** A mode this wave cannot read is
    skipped - recorded as a `ModeNotice` - while every other chosen mode of
    the same spell still happens. That is a deliberate choice, not the
    per-clause "one gap voids the whole card" fail-closed the rest of this
    file uses within a *single* instruction's clauses: CR 101.3 excuses only
    "any part of an instruction that's impossible to perform", and CR 700.2
    already treats each mode as its own instruction, carried out on its own
    (`700.2c`'s targets, `700.2f`'s "different targeting requirements for
    each mode", and 702.42b's "each of the modes" above all describe modes as
    separable units, not sub-clauses of one). Kozilek's Command choosing
    modes 1 and 3 with mode 1 unreadable and mode 3 fine should not throw away
    a legally-resolved exile because a different bullet on the same card is a
    parser gap - that would make the *working* half of the spell depend on an
    unrelated mode nobody chose it for, which is worse than the mode simply
    not happening and saying so.

    Each mode's own targets are `Game.cast_record(spell).mode_targets`, sliced
    per chosen mode instance by `Casting.choose_targets` (CR 700.2f) rather
    than the flat `spell.targets` a non-modal effect reads - so `spell.targets`
    is swapped to just this mode's slice for the duration of its own effect,
    and restored afterward regardless of what ran.
    """
    record = game.cast_record(spell)
    modal = modal_profile(spell.card)
    if modal is None or not modal.understood or not record.modes:
        return
    original_targets = spell.targets
    try:
        for position, mode_number in enumerate(record.modes):
            try:
                mode = modal.mode(mode_number)
            except ValueError:
                continue
            slice_targets = (
                record.mode_targets[position] if position < len(record.mode_targets) else []
            )
            spell.targets = list(slice_targets)
            clause = parse_mode_effect(mode, record.x_value)
            if clause is None:
                game.mode_notices.append(
                    ModeNotice(
                        source_id=spell.id,
                        source_name=spell.card.name,
                        mode_number=mode.number,
                        text=mode.text,
                    )
                )
                continue
            clause(game, spell)
    finally:
        spell.targets = original_targets


# --------------------------------------------------------------------------
# Mixed targeted/player clauses in one effect
# --------------------------------------------------------------------------
#
# `parse_targeted_effect_for_spell` and `parse_player_effect_for_spell` are
# each a whole-effect parser: every clause has to be their one shape or the
# whole thing is refused. A card that mixes the two kinds of clause - Lightning
# Helix's "deals 3 damage to any target and you gain 3 life" is a targeted
# clause and a player clause back to back - parses under neither, and used to
# need a table row for exactly that reason. This tries all three parsers on
# each clause independently instead of picking one parser for the whole card -
# search joined this dispatcher in W3, which is how Ghost Quarter's "Destroy
# target land. Its controller may search ..." reads as two clauses of two
# different shapes with no table row.


#: "Its controller ...", "That creature's controller ...", "That player ..." -
#: CR 400.7's plain anaphoric back-reference to whatever `_DESTROY_TARGET_RE`/
#: `_EXILE_TARGET_RE`'s clause just targeted, not a fresh target of this
#: sentence's own. Solitude prints the first form ("That creature's
#: controller gains life..."), Ghost Quarter and White Orchid Phantom the
#: second ("Its controller may search..."), Boseiju the third ("That player
#: may search...") - all three name the same thing: whoever controls the
#: permanent the previous clause just destroyed or exiled.
_ANAPHORIC_SUBJECT_RE = re.compile(
    r"^(?:its controller|that [a-z]+'s controller|that player)\s+(?P<rest>.+)$",
    re.IGNORECASE | re.DOTALL,
)

#: "Its controller/that player may search ..." with the subject already
#: stripped by `_ANAPHORIC_SUBJECT_RE` - the same tail `_SEARCH_AND_PUT_RE`
#: reads, but with no subject group of its own to match against (there is
#: nothing left in `rest` for one), because the "may" here is never optional
#: in the way `_build_search_clause`'s own "you may" prefix is: every card
#: this shape reaches prints it.
_REFERENT_SEARCH_RE = re.compile(
    r"^may search (?:your|their) library for (?:a|an) (?P<quality>.+?) card"
    r"(?: with mana value (?P<max_mv>\d+) or less)?"
    r"(?:, reveal it)?"
    r", put (?:it|that card) (?P<dest>into your hand|onto the battlefield(?P<tapped> tapped)?)"
    r"(?:, then shuffle)?\.?$",
    re.IGNORECASE,
)

#: "creates a[n] [tapped] <token descriptor> token[s]" - the referent-subject
#: twin of `_TOKEN_CLAUSE_RE`, for Cityscape Leveler's "Its controller creates
#: a tapped Powerstone token." "Create"/"creates" is not optional here the way
#: `_TOKEN_CLAUSE_RE`'s own leading "(?:create )?" is, because this text is
#: always third-person ("creates"), never the imperative "create" a spell's
#: own clause prints.
_REFERENT_TOKEN_RE = re.compile(
    rf"^creates? (?P<n>{_COUNT}) (?P<desc>.+?) \btokens?\b(?:\s+with\s+(?P<tail>.+))?\.?$",
    re.IGNORECASE | re.DOTALL,
)

#: "gains life equal to its power" - Solitude's and Swords to Plowshares' own
#: second sentence. `its power` is the only value expression this wave reads;
#: anything else (toughness, a fixed number, a modified power) is refused,
#: which is what `_read_referent_power_expression` enforces.
_REFERENT_GAIN_LIFE_RE = re.compile(r"^gains? life equal to (?P<expr>.+)$", re.IGNORECASE)


def _read_referent_power_expression(expr: str) -> bool:
    """Whether `expr` is exactly "its power" - the only value expression this
    wave reads off a referent (`its power` being the LKI snapshot
    `_parse_anaphoric_clause_pair` already took before the antecedent's verb
    moved the referent - CR 608.2i, a look-back effect uses information as it
    was, not the current game state, and CR 400.7's new object has none of
    its own left to read afterward)."""
    return expr.strip().rstrip(".").strip().lower() == "its power"


#: A second, anaphoric clause's effect, given the referent's controller and
#: LKI power (`None` if it could not be read - a `*` power CDA the layers
#: engine itself failed to resolve, not something this wave should crash or
#: silently zero on).
ReferentClause = Callable[["Game", Player, int | None, str], None]


def _referent_gain_life(game: "Game", player: Player, power: int | None, source: str) -> None:
    """ "<Referent's controller> gains life equal to its power" (CR 119.3).

    CR 107.1b: "You can't ... gain negative life" - a negative last-known
    power floors at zero rather than reducing the total. A `None` power (the
    LKI snapshot could not be read) gains nothing, which is `Game.power_of`'s
    existing "the layers engine could not answer" case, not a new one
    invented here.
    """
    if power is None:
        return
    player.gain_life(max(power, 0))


def _parse_referent_clause(rest: str) -> ReferentClause | None:
    """ "<rest>" is the tail of "its controller"/"that player" with the
    subject already stripped off by `_ANAPHORIC_SUBJECT_RE` - read as a life
    gain, a search, or a token creation, in that order, or `None` if this wave
    cannot read it (Craterous Stomp's "Each other creature that player
    controls becomes a Coward..." is none of the three and is left unscripted
    - see `docs/engine-coverage.md`).
    """
    rest = rest.strip()

    if match := _REFERENT_GAIN_LIFE_RE.fullmatch(rest):
        if not _read_referent_power_expression(match.group("expr")):
            return None
        return _referent_gain_life

    if match := _REFERENT_SEARCH_RE.fullmatch(rest):
        run = _search_and_place_for(match, optional=True)

        def search_effect(game: "Game", player: Player, power: int | None, source: str) -> None:
            run(game, player, source)

        return search_effect

    if match := _REFERENT_TOKEN_RE.fullmatch(rest):
        count = _count(match.group("n"))
        words = match.group("desc").strip().split()
        tail = match.group("tail")
        tapped = bool(words) and words[0].lower() == "tapped"
        if tapped:
            words = words[1:]
        if not words:
            return None
        predefined_name = " ".join(words)
        if tail is None and predefined_name in PREDEFINED:
            definition = PREDEFINED[predefined_name]
        else:
            definition = _parse_generic_token_descriptor(words, tail)
        if definition is None:
            return None

        def token_effect(game: "Game", player: Player, power: int | None, source: str) -> None:
            create_tokens(game, definition, player.username, count, tapped=tapped)

        return token_effect

    return None


class AnaphoricClauseNotice(BaseModel):
    """One "<verb> target X. Its/that X's controller ..." effect whose second,
    anaphoric clause (CR 400.7's back-reference to the first clause's own
    target, not a target of its own) this wave could not read.

    This is Solitude's own defect, recorded rather than repeated: "exile up to
    one other target creature. That creature's controller gains life equal to
    its power." used to have no registry row and nothing that could read its
    second sentence, so `_parse_mixed_clauses` correctly refused the whole
    effect (CR 608.2c has no notion of running half an instruction) - but
    silently, with no record anywhere that anything had gone unread, which is
    why a legally-targeted Solitude could exile nothing and gain no life with
    no trace of why. The same "unreadable is not the same as no effect"
    record `TargetingNotice`, `InterveningIfNotice`, `ModeNotice`,
    `LayerNotice`, and `CostModifierNotice` already keep for their own gaps.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    """The unreadable second sentence itself, as printed."""


def _unreadable_anaphoric_clause(text: str, *, for_spell: bool) -> str | None:
    """The second sentence of `text`'s "<verb> target X. Its/that X's
    controller ..." shape, if it has one **and this wave still cannot build
    it** - used only to decide whether a parse failure deserves an
    `AnaphoricClauseNotice`, not to parse the clause itself
    (`_parse_mixed_clauses` already tried and failed by the time this runs).

    Checking `_parse_anaphoric_clause_pair` itself, not just the two regexes'
    shape, matters: Boseiju's Channel ability fails to parse as a whole for
    two independent reasons, not one - `This ability costs {1} less to
    activate ...` is a third sentence neither this nor any other clause
    parser reads, *and* its own destroy-then-search pair does not read
    either, because `_REFERENT_SEARCH_RE` cannot match "a land card with a
    basic land type" (the "with a basic land type" tail falls into none of
    the regex's optional groups). A shape-only check would blame whichever
    sentence happens to fail the shape test first, which is the wrong
    clause exactly as often as it is the right one; checking the actual
    parse keeps the notice pointed at a sentence this wave really cannot
    read, whichever one that turns out to be.
    """
    clauses = _prepare_effect_clauses(text)
    if clauses is None:
        return None
    for first, second in zip(clauses, clauses[1:], strict=False):
        verb_match = _DESTROY_TARGET_RE.fullmatch(first) or _EXILE_TARGET_RE.fullmatch(first)
        if verb_match is None:
            continue
        if not _ANAPHORIC_SUBJECT_RE.fullmatch(second.strip()):
            continue
        if _parse_anaphoric_clause_pair(first, second, for_spell=for_spell) is None:
            return second
    return None


def _is_layer_effect_text(text: str) -> bool:
    """True if `text` - a resolving ability's or spell's own effect text - is
    one of `machines.layers`'s one-shot resolution shapes (CR 611.2), or
    looks like one that did not fully parse. The static-only anthem shape (CR
    611.3) never counts, however cleanly it parses:
    `is_resolution_layer_effect_text` is the function that draws that line,
    because a plain "Creatures you control get +N/+N." belongs to the
    permanent's own static ability and never to a spell's or ability's
    resolution - routing it here too would create a second, permanent copy
    on top of what the battlefield sweep already reapplies (CR 613.5).

    Checked on the **raw, unsplit** text rather than after `split_effect_
    clauses` has cut it into clauses: that splitter cuts on every bare " and "
    (`_CLAUSE_SEPARATOR`), which is right for "gets +N/+N and gains
    <keyword>" but wrong for an "and" that is not a clause boundary at all -
    "power **and** toughness each equal to its mana value" (Karn, the Great
    Creator's +1) splits into two unreadable halves that way. `machines.
    layers._effect_sentences` only splits on line breaks and ". ", so reading
    the whole text through `is_resolution_layer_effect_text` keeps a sentence
    like that one piece.
    """
    return is_resolution_layer_effect_text(text)


def _ability_effect_or_notice(effect_text: str) -> AbilityEffect | None:
    """`parse_mixed_effect` on `effect_text`, or - if that failed specifically
    on an unreadable anaphoric second clause - a stand-in effect that records
    an `AnaphoricClauseNotice` and otherwise does nothing (CR 608.2c: still no
    partial run of the instruction). Returns `None`, exactly as before, for
    any other kind of unreadable text - Fatal Push's Revolt line keeps its
    old, unrecorded silence; only this one specific shape has a notice built
    for it so far.

    Tried only once the ordinary clause parser has already failed on the
    whole text: `_is_layer_effect_text` is a fallback net for a continuous
    effect `parse_mixed_effect`'s per-clause splitting cannot read as printed
    (Karn, the Great Creator's +1; Oliphaunt's "another target creature you
    control gets +2/+0 and gains trample until end of turn." attack trigger),
    not a replacement for it - a card mixing a continuous-effect clause with
    some other clause (a draw, a search) still needs the ordinary path to run
    both, so this never overrides a parse that already succeeded.
    `create_continuous_effect_of_ability` is what Basking Rootwalla's own
    "{1}{G}: This creature gets +2/+2 until end of turn." (no target at all)
    and Karn's targeted "+1" both route to - no `ACTIVATED_EFFECTS` row is
    needed for either any more, and none is needed for a triggered ability
    of the same shape either, which is what lights up Oliphaunt.
    """
    parsed = parse_mixed_effect(effect_text)
    if parsed is not None:
        return parsed
    if _is_layer_effect_text(effect_text):
        return create_continuous_effect_of_ability
    unread = _unreadable_anaphoric_clause(effect_text, for_spell=False)
    if unread is None:
        return None

    def notice_only(game: "Game", ability: AbilityOnStack) -> None:
        game.anaphoric_clause_notices.append(
            AnaphoricClauseNotice(
                source_id=ability.source_id, source_name=ability.source_name, text=unread
            )
        )

    return notice_only


def _spell_effect_or_notice(effect_text: str) -> Effect | None:
    """The spell-side twin of `_ability_effect_or_notice`, for `effect_for`.

    The same `_is_layer_effect_text` fallback applies here: Tower Above's
    "Until end of turn, target creature gets +4/+4 and gains trample, wither,
    and ..." leads with its duration, which `split_effect_clauses`'s bare
    "and" cuts (twice) into fragments none of this wave's clause shapes read.
    Routing the whole text to `create_continuous_effect` instead reaches
    `parsed_layer_effects`, which reads its sentence whole (normalising the
    duration-first opening) and - since the granted keywords still are not
    all ones `_KNOWN_KEYWORDS` and a single-keyword grant can read - records a
    `LayerNotice` rather than the card doing nothing with no trace.
    """
    parsed = parse_mixed_effect_for_spell(effect_text)
    if parsed is not None:
        return parsed
    if _is_layer_effect_text(effect_text):
        return create_continuous_effect
    unread = _unreadable_anaphoric_clause(effect_text, for_spell=True)
    if unread is None:
        return None

    def notice_only(game: "Game", spell: CardState) -> None:
        game.anaphoric_clause_notices.append(
            AnaphoricClauseNotice(source_id=spell.id, source_name=spell.card.name, text=unread)
        )

    return notice_only


def _parse_anaphoric_clause_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "<Destroy/exile> target X. Its/that X's controller <player clause>."
    as one combined clause, or `None` if this shape does not match or its
    second sentence cannot be read.

    CR 608.2b's target-legality recheck belongs only to the *first*
    sentence's own target - the only thing this ability ever targets. The
    second sentence's "its controller"/"that player" is CR 400.7's plain
    anaphora back to whatever the first sentence found (see
    `_ANAPHORIC_SUBJECT_RE`), not a second target of its own, so it is never
    put through `Game.resolve_targets` again (that would apply CR 608.2b to
    an object CR 400.7 says is not even the same one any more, and reproduce
    Solitude's original bug of gaining no life whenever the exiled object
    itself would obviously no longer be a legal target of anything).

    This is the fix for Solitude's live defect: "exile up to one other target
    creature. That creature's controller gains life equal to its power." used
    to have no registry row and no clause parser that could read its second
    sentence, so `_parse_mixed_clauses` correctly refused the *whole* effect
    (CR 608.2c has no notion of running half an instruction) - but silently,
    with no record anywhere that anything had gone unread. `trigger_effect_for`
    now leaves an `AnaphoricClauseNotice` for exactly that failure mode.

    The referent's controller and power are read from the battlefield
    **before** the first sentence's verb runs it off the battlefield
    (CR 608.2i): reading them afterward would see `CardState.move_to`'s empty
    husk - counters cleared to `last_known_counters`, and
    `machines/layers.py` only computing continuous effects for a permanent
    still on the battlefield - so an anthemed, +1/+1-countered creature would
    silently gain its printed power back rather than its real one.
    """
    verb_match = _DESTROY_TARGET_RE.fullmatch(first) or _EXILE_TARGET_RE.fullmatch(first)
    if verb_match is None:
        return None
    is_destroy = first.strip().lower().startswith("destroy")
    if not _targets_understood(
        verb_match.group("phrase"), count_agnostic=True, battlefield_only=is_destroy
    ):
        return None
    subject_match = _ANAPHORIC_SUBJECT_RE.fullmatch(second.strip())
    if subject_match is None:
        return None
    second_clause = _parse_referent_clause(subject_match.group("rest"))
    if second_clause is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            # CR 115.6: "up to one" chose zero, or CR 608.2b left nothing
            # legal - either way the second sentence has nothing to refer
            # back to and does not run either (CR 608.2c: one instruction,
            # not two independent ones).
            return
        target = targets[0]
        referent = game.controller_of(target)
        power = game.power_of(target)
        if is_destroy:
            game.destroy(target)
        else:
            game.exile_permanent(target)
        if target.zone is Zone.BATTLEFIELD:
            # The move never happened, so the second sentence has nothing to
            # refer back to (CR 608.2c: one instruction, not two independent
            # ones). `target` was filtered to the battlefield above, and
            # neither verb's replacement path (`put_into_graveyard`'s
            # destination is always graveyard or exile) can land it back
            # there, so still being on the battlefield here only happens
            # when the move itself was refused outright: CR 702.12b's
            # indestructible refuses `destroy`, and CR 111.8 refuses either
            # verb for a token that has already left the battlefield once.
            return
        second_clause(game, referent, power, source)

    return effect


def _parse_mixed_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """One clause of a mixed effect: the targeted shape first, then a token
    creation, then a search, then the plain player shape (CR 608.2c does not
    care which kind of instruction a card lists first, so no parser gets
    priority for any reason beyond "try this one, then the next").
    """
    targeted = _parse_targeted_clause(clause, for_spell=for_spell)
    if targeted is not None:
        return targeted
    token = _parse_token_clause(clause, for_spell=for_spell)
    if token is not None:
        return token
    search = _parse_search_clause(clause, for_spell=for_spell)
    if search is not None:
        return search
    player_clause = _parse_optional_player_clause(clause)
    if player_clause is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        player_clause(game, player, source)

    return effect


def _parse_mixed_clauses(text: str, *, for_spell: bool) -> list[TargetedClause] | None:
    """Every clause of `text`, or `None` the moment one clause (or one
    anaphoric pair of clauses) matches nothing this wave reads.

    A run of two or more consecutive clauses is tried first, against two
    different shapes that are each one CR 608.2c instruction `split_effect_
    clauses` has cut apart on its own separators, not several independent
    ones: `_merge_continuous_pump_keyword_clauses` for "gets +N/+N and gains
    <keyword>" (Give In to Violence, CR 611.2), and `_parse_anaphoric_clause_
    pair` for "destroy/exile target X. Its/that X's controller ..." (CR
    400.7). Only when a clause opens neither does it fall back to
    `_parse_mixed_clause`'s ordinary one-clause-at-a-time dispatch - Fatal
    Push's Revolt line is still read by neither and still takes the whole
    effect down with it.

    Fail-closed **per clause (or run), not per parser**: CR 608.2c has no
    notion of running half an effect, so a card with one clause nothing here
    reads still comes back `None` for the whole thing, exactly as
    `_parse_targeted_clauses` and `_parse_player_clauses` already refuse it
    alone.
    """
    clauses = _prepare_effect_clauses(text)
    if clauses is None:
        return None
    parsed: list[TargetedClause] = []
    index = 0
    while index < len(clauses):
        merged = _merge_continuous_pump_keyword_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        if index + 1 < len(clauses):
            paired = _parse_anaphoric_clause_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
        effect = _parse_mixed_clause(clauses[index], for_spell=for_spell)
        if effect is None:
            return None
        parsed.append(effect)
        index += 1
    return parsed


def parse_mixed_effect_for_spell(text: str) -> Effect | None:
    """A spell whose clauses may be targeted, player-only, or a mix of both,
    read off the card's own printed text - Lightning Helix, with no `EFFECTS`
    row any more. Subsumes `parse_targeted_effect_for_spell` and
    `parse_player_effect_for_spell`: a wholly-targeted or wholly-player-clause
    card still parses here, since each clause simply succeeds on the first of
    the two parsers it is tried against.
    """
    clauses = _parse_mixed_clauses(text, for_spell=True)
    if clauses is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        for clause in clauses:
            clause(game, spell)

    return effect


def parse_mixed_effect(text: str) -> AbilityEffect | None:
    """The ability-resolution twin of `parse_mixed_effect_for_spell`: a
    triggered or activated ability whose clauses may be targeted, a search, a
    plain player clause, or a mix, read off the ability's own printed text
    with no table row.

    This is what lets Ghost Quarter and White Orchid Phantom drop their
    `ACTIVATED_EFFECTS`/`TRIGGER_EFFECTS` rows: "Destroy target land." is one
    clause `_parse_targeted_clause` reads, "Its controller may search their
    library for a basic land card, put it onto the battlefield, then shuffle."
    is the next, read by `_parse_search_clause` once `_rejoin_search_clauses`
    has put its "then shuffle" back where it belongs. `trigger_effect_for` and
    `activated_effect_for` call this instead of trying
    `parse_search_and_put_effect`, `parse_targeted_effect`, and
    `parse_player_effect` in turn, since a search-only or plain-player-only or
    wholly-targeted ability still parses here - each of its clauses simply
    succeeds on the first of the three parsers it is tried against.
    """
    clauses = _parse_mixed_clauses(text, for_spell=False)
    if clauses is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        for clause in clauses:
            clause(game, ability)

    return effect


def emrakul_cast_trigger(game: "Game", ability: AbilityOnStack) -> None:
    """Emrakul, the Promised End: "When you cast this spell, you gain control of
    target opponent during that player's next turn. After that turn, that player
    takes an extra turn."

    Two things happen, in the order printed (CR 608.2c), but only the first
    happens *now*.

    **The extra turn has to be a delayed triggered ability (CR 603.7), not part
    of this resolution.** CR 500.7 adds an extra turn "directly after the
    specified turn", so granting it while this trigger resolves would insert it
    directly after the current turn - which is *before* the turn Emrakul's
    controller is about to steal - and the victim would take their extra turn
    first. "After that turn" is a later moment, and CR 603.7 is what says a later
    moment is expressed as a delayed trigger: "An effect may create a delayed
    triggered ability that can do something at a later time."

    CR 603.7e gives it Emrakul's controller and Emrakul as its source, since a
    triggered ability created it. It waits for the end step of the controlled
    player's turn - `only_when_active` is how "that turn" is named, there being
    no turn object to point at - and CR 603.7b's default of triggering once is
    exactly right for a one-off extra turn.

    **The control duration is still not modelled.** The card gives control
    "during that player's next turn" and `Game.gain_control_of_player` has no
    duration argument, so control is handed over now and never returned. See
    `docs/engine-coverage.md`.

    There being no target chosen leaves this doing nothing, which is CR 608.2b's
    outcome for a trigger whose targets are all gone anyway.
    """
    for target in game.resolve_targets(ability):
        username = target.username if isinstance(target, Player) else None
        if username is None or username == ability.controller:
            continue
        game.gain_control_of_player(ability.controller, username)
        game.create_delayed_trigger(
            DelayedTrigger(
                text="After that turn, that player takes an extra turn.",
                effect="grant_extra_turn",
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=Step.END_STEP,
                controller=ability.controller,
                source_id=ability.source_id,
                source_name="Emrakul, the Promised End",
                subject_player=username,
                only_when_active=username,
            )
        )


def vexing_bauble_counter(game: "Game", ability: AbilityOnStack) -> None:
    """Vexing Bauble: "Whenever a player casts a spell, if no mana was spent to
    cast it, counter that spell."

    "That spell" is the trigger event's own subject - the spell whose casting
    triggered this, not something chosen as a target - so it is read off
    `ability.event` rather than through `Game.resolve_targets`. CR 608.2b's
    ordinary "the target is gone" outcome covers a spell that has already left
    the stack by the time this resolves (countered, or resolved first by
    something else that responded to it): nothing to counter, so nothing
    happens.

    Not read by the targeted-clause fallback because "that spell" is not a
    target at all - CR 601.2c never asks Vexing Bauble's controller to choose
    one - it is the event's own subject, the same distinction
    `tishanas_tidebinder` draws for "target activated or triggered ability"
    versus a plain event reference.
    """
    if ability.event is None or ability.event.subject_id is None:
        return
    spell = game.find_by_id(ability.event.subject_id)
    if spell is not None and spell in game.stack:
        game.counter(spell)


#: One triggered ability, identified: the card it is printed on, the event it
#: watches, and a lowercase fragment of its own printed text. The fragment is
#: empty for a card whose triggers on that event are all one entry's business.
TriggerKey = tuple[str, TriggerEvent, str]

#: What a triggered ability does, by `(card name, trigger event, marker)`.
TRIGGER_EFFECTS: dict[TriggerKey, AbilityEffect] = {
    # White Orchid Phantom's "When this creature enters, destroy up to one
    # target nonbasic land. Its controller may search their library for a
    # basic land card, put it onto the battlefield tapped, then shuffle." is
    # not entered here any more (W3): the destroy is `_parse_targeted_clause`'s
    # shape and the search is `_parse_search_clause`'s "its controller may"
    # shape (see `_build_search_clause`), two clauses `parse_mixed_effect`
    # reads in the order printed (CR 608.2c). See
    # `tests/scenarios/test_registry_is_minimal.py`.
    #
    # Solemn Simulacrum's two triggers are not entered here any more. Its
    # enters trigger - "you may search your library for a basic land card,
    # put that card onto the battlefield tapped, then shuffle." - is exactly
    # `parse_search_and_put_effect`'s shape; its dies trigger - "you may draw
    # a card." - is a single `parse_player_effect` clause. Both are reached by
    # `trigger_effect_for`'s fallback. See
    # `tests/scenarios/test_registry_is_minimal.py`.
    ("Guttersnipe", TriggerEvent.CAST_SPELL, ""): damage_each_opponent(2),
    ("Hellrider", TriggerEvent.ATTACKS, ""): damage_the_attacked_player(1),
    ("Ashmouth Hound", TriggerEvent.BLOCKS, ""): damage_the_other_combatant(1),
    ("Delver of Secrets", TriggerEvent.BEGINNING_OF_STEP, ""): delver_upkeep,
    ("Thopter Assembly", TriggerEvent.BEGINNING_OF_STEP, ""): thopter_assembly_upkeep,
    # Devourer of Destiny's cast trigger - "exile target permanent that's one
    # or more colors" - is not entered here any more: it is the single-clause
    # shape `parse_targeted_effect` reads off the ability's own printed text
    # (the "that's one or more colors" restriction is not enforced either way -
    # see `docs/engine-coverage.md`), so
    # `trigger_effect_for`'s fallback reaches it. See
    # `tests/scenarios/test_registry_is_minimal.py`.
    ("Tishana's Tidebinder", TriggerEvent.ENTERS_THE_BATTLEFIELD, ""): tishanas_tidebinder,
    # Ulamog, the Ceaseless Hunger's "When you cast this spell, exile two
    # target permanents." and both of Ugin, Eye of the Storms' CAST_SPELL
    # triggers - "exile up to one target permanent that's one or more colors"
    # on each - are not entered here any more: `_targets_understood` now
    # accepts a count-agnostic exile ("two target ...", "up to one target
    # ...") the same way it already accepted exactly one, so
    # `parse_targeted_effect` reads all three off the ability's own printed
    # text and `trigger_effect_for`'s fallback (still keyed by marker for
    # Ugin's two entries) reaches them. The "that's one or more colors"
    # restriction is still not enforced either way. See
    # `tests/scenarios/test_registry_is_minimal.py`.
    # Sowing Mycospawn's "When you cast this spell, if it was kicked, exile
    # target land" - deliberately has no entry: once its intervening *if*
    # (CR 603.4, CR 702.33d - read off `Game.cast_record(spell).kicked` by
    # `machines/triggers.intervening_if_holds`) lets it trigger at all, "exile
    # target land" is one clause of `parse_targeted_effect`'s shape, read off
    # the ability's own printed text, so `trigger_effect_for`'s fallback
    # reaches it the same way Devourer of Destiny's does above.
    #
    ("Vexing Bauble", TriggerEvent.CAST_SPELL, ""): vexing_bauble_counter,
    #
    # Ranger-Captain of Eos's "you may search your library for a creature card
    # with mana value 1 or less, reveal it, put it into your hand, then
    # shuffle." is not entered here any more either (W3): the mana-value bound
    # is `_SEARCH_AND_PUT_RE`'s own `max_mv` group now, so the whole sentence -
    # one clause - is `_parse_search_clause`'s shape and `trigger_effect_for`'s
    # fallback reaches it. See `tests/scenarios/test_registry_is_minimal.py`.
    ("Emrakul, the Promised End", TriggerEvent.CAST_SPELL, ""): emrakul_cast_trigger,
    # -- tokens (CR 111, CR 701.7a) -------------------------------------
    # Ajani, Nacatl Pariah's enters trigger - "create a 2/1 white Cat Warrior
    # creature token." - is not entered here any more (W4): one clause of
    # `_parse_token_clause`'s shape, read off the ability's own printed text,
    # so `trigger_effect_for`'s fallback reaches it.
    #
    # Drowner of Truth's cast trigger - "create two 0/1 colorless Eldrazi
    # Spawn creature tokens with 'Sacrifice this token: Add {C}.'" - is not
    # entered here any more either: the same shape, quoted rules text
    # included. Its intervening *if* ("if {C} was spent to cast it") now reads
    # `Game.cast_record(spell).mana_of_color_spent(Color.COLORLESS)` off
    # CR 601.2h's payment (`machines/triggers.intervening_if_holds`), so the
    # trigger only reaches the stack - and this fallback only runs - when
    # colorless mana genuinely paid for it.
    #
    # Wurmcoil Engine's dies trigger - two tokens, "with deathtouch and a ...
    # token with lifelink" - is not entered here any more either: CR 608.2c's
    # clause split cuts the sentence at "and" into two noun phrases, and each
    # is `_parse_token_clause`'s shape on its own. This is the entry that
    # makes a **token copy of Wurmcoil Engine** behave: CR 707.2 copies the
    # printed text, so the copy has this trigger too, and CR 111.7's
    # parenthesis - "if a token changes zones, applicable triggered abilities
    # will trigger before the token ceases to exist" - is what lets a dying
    # Wurm token fire it.
    #
    # See `tests/scenarios/test_registry_is_minimal.py` for all three.
    ("Ocelot Pride", TriggerEvent.BEGINNING_OF_STEP, ""): ocelot_pride_end_step,
    ("Seasoned Pyromancer", TriggerEvent.ENTERS_THE_BATTLEFIELD, ""): seasoned_pyromancer,
    ("Hangarback Walker", TriggerEvent.DIES, ""): hangarback_dies,
    # Soul Warden's "Whenever another creature enters, you gain 1 life." and
    # the surveil lands' (Elegant Parlor, Thundering Falls) and Dragon's Rage
    # Channeler's "surveil 1" are deliberately **not** entered here any more.
    # Each is one clause of exactly the shape `parse_player_effect` reads off
    # the ability's own printed text, so `trigger_effect_for`'s fallback
    # covers all of them - and a card added to the pool later for free. A
    # per-card entry re-added for any of them would silently shadow that
    # fallback; see `test_no_card_has_a_registry_entry_that_would_shadow_the_player_effect_parser`.
    # Dragon's Rage Channeler's *delirium* static ability - +2/+2, flying, and
    # attacks each combat if able - is a layer 6 and 7c continuous effect and
    # belongs in LAYER_EFFECTS, not here.
}

#: What an activated ability does, by `(card name, index among that card's
#: activated abilities)`.
ACTIVATED_EFFECTS: dict[tuple[str, int], AbilityEffect] = {
    # Vampiric Rites' "You gain 1 life and draw a card." is not entered here
    # any more - two clauses `parse_player_effect` reads directly, in the
    # order printed (CR 608.2c).
    # Basking Rootwalla's "{1}{G}: This creature gets +2/+2 until end of
    # turn." (index 0) and Karn, the Great Creator's "+1: Until your next
    # turn, up to one target noncreature artifact becomes an artifact
    # creature with power and toughness each equal to its mana value." (index
    # 0 - his static ability line has no cost, so +1 is the first ability
    # that does) are not entered here any more either: both rows existed only
    # to route the ability to `create_continuous_effect_of_ability`, the
    # generic resolution effect that reads the card's own oracle text through
    # `machines/layers.py`'s `parsed_layer_effects` - the actual pump, type
    # change, and mana-value P/T were never this table's business. Routing is
    # text-driven now: `_is_layer_effect_text` in `_ability_effect_or_notice`
    # recognises the ability's own effect text as one of `parsed_layer_
    # effects`'s shapes and reaches the same function with no row, which also
    # lights up a triggered ability of the same shape that never had a row at
    # all - Oliphaunt's "another target creature you control gets +2/+0 and
    # gains trample until end of turn." attack trigger. See
    # `tests/scenarios/test_registry_is_minimal.py`.
    # The Zendikar/Khans fetchlands - Arid Mesa, Flooded Strand, Bloodstained
    # Mire, Marsh Flats, Scalding Tarn, Windswept Heath, Wooded Foothills,
    # Misty Rainforest, Verdant Catacombs - are deliberately **not** entered
    # here. Each is one activated ability, index 0, of the exact shape
    # `parse_search_and_put_effect` reads off the card's own printed text, so
    # `activated_effect_for`'s fallback covers all nine without a table row
    # each - and covers a fetchland added to the pool later for free. Adding a
    # per-card entry for one of them would silently shadow that fallback; see
    # `test_fetching_a_land.py::test_the_registry_does_not_shadow_the_parser`.
    # The horizon lands' second ability - "{1}, {T}, Sacrifice this land: Draw
    # a card." - is not entered here any more either: it is one clause of the
    # same parseable shape, so `activated_effect_for`'s fallback reaches it
    # (and Mind Stone's and Nurturing Peatland's identical ability, which
    # never had a row at all).
    # Goblin Bombardment's "Sacrifice a creature: This enchantment deals 1
    # damage to any target." is not entered here any more either: the effect
    # half, on its own, is the same single-clause shape
    # `parse_targeted_effect` reads off the ability's own printed text, so
    # `activated_effect_for`'s fallback reaches it.
    # Ghost Quarter's "{T}, Sacrifice this land: Destroy target land. Its
    # controller may search their library for a basic land card, put it onto
    # the battlefield, then shuffle." (index 1, behind "{T}: Add {C}") is not
    # entered here any more either (W3): the same two-clause shape as White
    # Orchid Phantom's trigger, read by `parse_mixed_effect` with no row. See
    # `tests/scenarios/test_registry_is_minimal.py`.
}


def trigger_effect_for(
    card_name: str, event: TriggerEvent, effect_text: str | None = None
) -> AbilityEffect | None:
    """The effect of a card's trigger on `event`, or None if it is not scripted.

    A double-faced card is keyed by the face the ability is printed on, so
    Delver of Secrets is found under `"Delver of Secrets"` and not under the full
    `"Delver of Secrets // Insectile Aberration"`.

    **A card may have more than one trigger on one event**, and this is called
    with the card and the event and nothing else, because `Game._effect_of` has
    only those to hand. So when a card has several entries for an event, what
    comes back is a dispatcher: it reads the resolving ability's own printed text
    and runs the entry whose marker that text carries. A trigger matching no
    marker does nothing, which is the same silence a card with no entry gets.

    A card with **no** entry for the event falls back to `parse_mixed_effect`
    on `effect_text` - the per-clause dispatcher that reads a search, a
    targeted clause, or a plain player clause in any order or mix (W3 folded
    search into it; before that this fell back through
    `parse_search_and_put_effect`, then `parse_targeted_effect`, then
    `parse_player_effect` in turn, which could not read a card whose clauses
    mixed those shapes - Ghost Quarter's destroy-then-search among them).
    Flagstones of Trokair's death trigger is written this way rather than as a
    table row, but does not fire yet in a real game - its condition never
    reaches this function at all, because `_trigger_event` does not recognise
    it (see `docs/engine-coverage.md`).
    """
    front = card_name.split("//")[0].strip()
    entries = [
        (marker, effect)
        for (name, keyed_event, marker), effect in TRIGGER_EFFECTS.items()
        if keyed_event is event and name in (card_name, front)
    ]
    if not entries:
        if effect_text is None:
            return None
        return _ability_effect_or_notice(effect_text)
    if len(entries) == 1 and not entries[0][0]:
        return entries[0][1]
    return _dispatch_by_printed_text(entries)


def _dispatch_by_printed_text(
    entries: list[tuple[str, AbilityEffect]],
) -> AbilityEffect:
    """Pick between several triggers of one card on one event, by their text.

    The most specific marker wins, so a longer fragment is tried before a shorter
    one, and an empty marker is the catch-all a card uses when one entry really
    does cover every trigger it has on that event.
    """
    ordered = sorted(entries, key=lambda entry: -len(entry[0]))

    def dispatch(game: "Game", ability: AbilityOnStack) -> None:
        printed = (getattr(ability.ability, "text", "") or "").lower()
        for marker, effect in ordered:
            if not marker or marker in printed:
                effect(game, ability)
                return

    return dispatch


def activated_effect_for(
    card_name: str, index: int, effect_text: str | None = None
) -> AbilityEffect | None:
    """The effect of a card's activated ability at `index`, or a parsed one.

    A card with no `ACTIVATED_EFFECTS` row falls back to `parse_mixed_effect`
    on `effect_text` - every fetchland and Expedition Map reach the model
    through its search-clause path, Icy Manipulator and Kiora's Follower
    through its targeted-clause path, Vexing Bauble's "Draw a card" and the
    horizon lands' own sacrifice ability through its player-clause path, and
    Ghost Quarter's "Destroy target land. Its controller may search ..."
    through a targeted clause and a search clause together, with no row of
    its own.
    """
    front = card_name.split("//")[0].strip()
    explicit = ACTIVATED_EFFECTS.get((card_name, index)) or ACTIVATED_EFFECTS.get((front, index))
    if explicit is not None:
        return explicit
    if effect_text is None:
        return None
    return _ability_effect_or_notice(effect_text)
