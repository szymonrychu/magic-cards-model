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
from random import Random
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ..models.card import Color, Supertype, Type
from ..models.card_state import CardState, ChoiceKind, Counter, ExileAnnotation, ExileMarker
from ..models.player import Player
from ..models.token import MONSTER_ROLE, PREDEFINED, TokenDefinition, create_tokens
from ..models.zone import Zone
from .abilities import TriggerEvent
from .decisions import Decision, DecisionKind
from .delayed import (
    DelayedTrigger,
    draw_a_card_for_controller,
    return_subject_to_battlefield_under_owner,
    return_subject_to_hand,
)
from .layers import (
    ContinuousEffect,
    ContinuousEffects,
    Duration,
    Layer,
    LayerContext,
    Sublayer,
    add_type,
    count_card_types,
    grant_ability,
    is_resolution_layer_effect_text,
    only_this_incarnation,
    set_power_toughness,
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


def each_player_exiles_sacrifices_and_returns_creatures(game: "Game", spell: CardState) -> None:
    """Living End: "Each player exiles all creature cards from their graveyard,
    then sacrifices all creatures they control, then puts all cards they
    exiled this way onto the battlefield."

    Three CR 608.2c instructions, each performed for every player before the
    next one starts, rather than one player's whole sequence before the next
    player's: CR 101.4's APNAP order only orders *choices*, and nothing here
    is a choice, so there is no rules reason to interleave them by player
    instead of by step - and doing it by step is what keeps "sacrifices all
    creatures they control" from ever seeing a creature this same effect just
    exiled from a graveyard onto nobody's battlefield yet.

    - **CR 701.13a / 406.2** - exile is "move it to the exile zone from
      wherever it is"; a graveyard is as good a wherever as any.
      `Game.exile_permanent` takes any `CardState` regardless of its current
      zone, so it exiles a graveyard card exactly the way it exiles a
      permanent.
    - **CR 701.21a** - "To sacrifice a permanent, its controller moves it from
      the battlefield directly to its owner's graveyard" - `Game.sacrifice`.
    - **CR 400.7, CR 110.2a** - a card put onto the battlefield this way is a
      new object, not the graveyard card come back to life; `Game.
      put_onto_battlefield` is the Tooth and Nail path this effect reuses.

    Only *cards* were exiled, so a creature token that got sacrificed at the
    second step is simply gone (CR 111.7) - it was never eligible for the
    first step and has nothing to return at the third.
    """
    exiled_by_player: dict[str, list[CardState]] = {}
    for player in game.players_in_game:
        creatures = [state for state in list(player.graveyard) if state.card.is_creature]
        exiled_by_player[player.username] = [game.exile_permanent(state) for state in creatures]

    for player in game.players_in_game:
        controlled = [
            permanent
            for permanent in list(game.battlefield)
            if permanent.controller == player.username
            and game.characteristics_of(permanent).is_creature
        ]
        for permanent in controlled:
            game.sacrifice(permanent)

    for player in game.players_in_game:
        for state in exiled_by_player[player.username]:
            game.put_onto_battlefield(state, player.username)


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


def _prevent_next_damage_from_target(*, gains_life: bool) -> TargetedClause:
    """ "The next time target creature would deal damage this turn, prevent
    that damage[. You gain life equal to the damage prevented this way.]" -
    Awe Strike, read off the card's own text by `_merge_prevent_damage_from_
    target_clauses` rather than a table row.

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
    equal to the damage prevented this way" is such an effect, so `gains_life`
    - set only when the card's own second sentence says so - becomes the
    shield's `gains_life_when_prevented`, and `Game.apply_prevention_shield`
    performs it as the damage event is prevented.
    """

    def effect(game: "Game", stack_object: "StackObject") -> None:
        from ..models.game import PreventionShield, ShieldKind

        for target in game.resolve_card_targets(stack_object):
            game.create_prevention_shield(
                PreventionShield(
                    kind=ShieldKind.NEXT_INSTANCE,
                    label=f"prevent the next damage {target.name} would deal this turn",
                    controller=game.controller_of(stack_object).username,
                    source_id=target.id,
                    gains_life_when_prevented=gains_life,
                )
            )

    return effect


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
    # "Electrolyze deals 2 damage divided as you choose among one or two
    # targets. Draw a card." is not entered here any more: `_DIVIDED_DAMAGE_RE`
    # reads the first clause off the card's own printed text (CR 601.2d), the
    # draw is `parse_clause_effect`'s ordinary player clause, and
    # `effect_for`'s fallback reaches both in printed order. See
    # `test_registry_is_minimal.py`.
    # CR 608.2c: the switch first, then the draw, in the order printed.
    "Twisted Image": sequence(create_continuous_effect, draw_cards(1)),
    # "Giant Growth" and "Dismember" are not entered here any more (W5): both
    # are exactly `_CONTINUOUS_PUMP_OR_KEYWORD_RE`'s shape, read off the
    # card's own printed text (Dismember's Phyrexian-mana reminder line
    # stripped like any other), so `effect_for`'s fallback reaches them. See
    # `test_registry_is_minimal.py`.
    # "Lava Dart deals 1 damage to any target." is exactly `_DAMAGE_TARGET_RE`'s
    # shape (Lightning Bolt's own) - but unlike Lightning Bolt, `Card.oracle_text`
    # here is two lines, the second being "Flashback-Sacrifice a Mountain."
    # (CR 702.34). That second line is not a resolution instruction at all -
    # it is a way to *cast* the card, `machines/casting.py`'s business - but
    # `_prepare_effect_clauses` has no way to know that and refuses the whole
    # text as one unreadable clause among the effect's own, so the fallback
    # cannot reach the first line either. The row stays until a wave teaches
    # the clause splitter to strip a flashback line the way it already strips
    # an additional-cost line. See `tests/test_targeted_effects.py::
    # test_a_flashback_line_takes_the_whole_effect_down`.
    "Lava Dart": deal_damage(1),
    "Unholy Heat": delirium_damage(2, 6),
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
    # "Fog"/"Angelsong": "Prevent all combat damage that would be dealt this
    # turn." are not entered here any more: `_PREVENT_ALL_COMBAT_DAMAGE_RE`
    # reads the sentence verbatim off the card's own printed text, so
    # `effect_for`'s fallback reaches both (Angelsong's cycling is a way to
    # discard it rather than cast it, CR 702.29a, and never reaches this
    # parser at all). See `test_registry_is_minimal.py`.
    #
    # "Bandage": "Prevent the next 1 damage that would be dealt to any target
    # this turn. Draw a card." is not entered here any more either:
    # `_PREVENT_NEXT_DAMAGE_TO_TARGET_RE` reads the first clause, the draw is
    # the ordinary player clause, and `effect_for`'s fallback runs both in
    # printed order (CR 608.2c). See `test_registry_is_minimal.py`.
    #
    # "Awe Strike": "The next time target creature would deal damage this
    # turn, prevent that damage. You gain life equal to the damage prevented
    # this way." is not entered here any more either:
    # `_merge_prevent_damage_from_target_clauses` reads both sentences as one
    # CR 608.2c instruction (the second is CR 615.5's rider, not independent
    # of the first), so `effect_for`'s fallback reaches it. See
    # `test_registry_is_minimal.py`.
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

    Both halves now, in printed order (CR 608.2c) - `models/token.py`'s
    `create_tokens`/`THOPTER` are the same machinery `hangarback_dies` already
    uses elsewhere in this file, so there was never a modelling gap here, only
    a stale one: this function used to return to hand and stop, which is
    exactly the kind of row-masked bug this wave's deletions are meant to
    surface, found while auditing this row rather than by deleting it (the
    "return this creature" self-reference has no generic clause parser yet,
    so the row itself stays - see the docstring at the top of this module).

    **The intervening *if* - "if you control no Thopters other than this
    creature" (CR 603.4) - is still not modelled**, so the trigger always goes
    on the stack and this always runs, which is wrong the turn after the first
    (five new Thopters plus this one both count). Left as a documented gap,
    not attempted here.
    """
    source = ability.source(game)
    if source is None or source.zone is not Zone.BATTLEFIELD:
        return
    game.return_to_hand(source)
    create_tokens(game, THOPTER, ability.controller, 5)


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
    check silently skips it - that shape is `exile_target_players_graveyard`
    below instead, a separate clause the parser routes to on sight of the
    "player's graveyard" phrase rather than this function ever seeing it.
    Kozilek's Command's "Exile up to X target cards from graveyards" is one
    mode of a modal spell and *does* reach this function now, through
    `resolve_modal_spell` (`parse_mode_effect` falls back to
    `parse_mixed_effect_for_spell`, which reads this shape the same way any
    non-modal card's text would).
    """
    for target in game.resolve_targets(ability):
        if isinstance(target, CardState):
            game.exile_permanent(target)


def exile_target_players_graveyard(game: "Game", stack_object: "StackObject") -> None:
    """Bojuka Bog / Tormod's Crypt: "exile target player's graveyard."

    CR 115.1: "The targets are object(s) and/or player(s) the spell or ability
    will affect" - here the *target* is the player, not a card, which is why
    `exile_ability_targets`'s `isinstance(target, CardState)` check can never
    reach this shape (`_targets_understood`'s `allow_player_targets` gate is
    what tells the two apart while parsing). `game.resolve_targets` already
    reruns CR 608.2b for a player target - gone from the game is illegal,
    still in it is not - so by the time this runs the player is a real,
    current `Player`.

    CR 404.1: "A player's graveyard is their discard pile", one of the
    per-player zones on `Player`, not the target itself. Once the player is
    confirmed legal, every card sitting in *their* graveyard right now - full
    or empty, the caster's own or an opponent's - is exiled one by one through
    `Game.exile_permanent` (CR 406.2/701.13a: exile moves an object "from
    whatever zone it's currently in", so a graveyard card is as reachable as a
    permanent). An empty graveyard is exactly as legal a target as a full one:
    nothing in CR 115 or CR 608.2b conditions targeting a player on what is in
    their zones, only on whether they are still in the game.
    """
    for target in game.resolve_targets(stack_object):
        if isinstance(target, Player):
            for card_state in list(target.graveyard):
                game.exile_permanent(card_state)


def exile_all_graveyards(game: "Game", stack_object: "StackObject") -> None:
    """Rest in Peace: "exile all graveyards."

    No target at all - every player's graveyard, own included (CR 404.1), is
    emptied into the shared exile zone (CR 406.2/701.13a). `game.players_in_game`
    is CR 104.3a's still-playing set, so a player who has already conceded or
    lost contributes nothing (there is no graveyard left to read a rule about).

    Rest in Peace's second sentence - "If a card or token would be put into a
    graveyard from anywhere, exile it instead" - is a static replacement
    effect (CR 614), a different ability entirely from this one's ETB trigger,
    and is not attempted here: `machines/effects.py` has no home for a
    graveyard-redirecting replacement effect the way `machines/replacement.py`
    already does for "enters tapped". It is not counted by this file's own
    sweep either, the same way a shockland's own replacement text is not -
    see `docs/mcp-tools.md`/`scripts/sweep_pool.py`'s own scope note.
    """
    for player in game.players_in_game:
        for card_state in list(player.graveyard):
            game.exile_permanent(card_state)


#: Reused by `_exile_matching_from_all_graveyards`, defined lower in this file
#: next to `_HAND_EXILE_COLOR_WORDS` - forward reference is fine, since this is
#: only ever called once the whole module has finished importing.
def _graveyard_exile_quality_matcher(quality: str) -> Callable[[CardState], bool] | None:
    """A predicate for "cards that are `<quality>`" - Sanctifier en-Vec's
    "black or red" - or `None` if this wave cannot read every word of it.

    Reuses `_hand_exile_quality_matcher`'s single-word colour/type reading
    (CR 105.2c's five colours, CR 205.2a's card types) rather than duplicating
    it, splitting on "or"/comma the same way `_quality_matcher` does for a
    search's stated quality. Fail-closed per word: a quality this wave cannot
    read - a supertype, a subtype - refuses the whole clause (CR 608.2c)
    rather than exiling the wrong, narrower set of cards silently.
    """
    words = [
        word.strip() for word in re.split(r",\s*|\s+or\s+", quality.strip().lower()) if word.strip()
    ]
    if not words:
        return None
    matchers = []
    for word in words:
        matcher = _hand_exile_quality_matcher(word)
        if matcher is None:
            return None
        matchers.append(matcher)

    def matches(state: CardState) -> bool:
        return any(matcher(state) for matcher in matchers)

    return matches


def _exile_matching_from_all_graveyards(
    matches: Callable[[CardState], bool],
) -> TargetedClause:
    """Sanctifier en-Vec: "exile all cards that are black or red from all
    graveyards" - the filtered twin of `exile_all_graveyards`, keeping only
    the cards `matches` accepts (CR 404.1's graveyards, CR 406.2/701.13a's
    exile). No target either; every player's graveyard is read, the caster's
    own included, the same as the unfiltered shape.

    Sanctifier en-Vec's own second sentence is the same kind of static
    replacement effect Rest in Peace's is, and is left unattempted for the
    same reason - see `exile_all_graveyards`.
    """

    def effect(game: "Game", stack_object: "StackObject") -> None:
        for player in game.players_in_game:
            for card_state in list(player.graveyard):
                if matches(card_state):
                    game.exile_permanent(card_state)

    return effect


def puts_graveyard_on_bottom_of_library(game: "Game", stack_object: "StackObject") -> None:
    """Endurance: "up to one target player puts all the cards from their
    graveyard on the bottom of their library in a random order."

    CR 115.6: "up to one target" may legally choose zero, in which case
    `game.resolve_targets` returns nothing and this does nothing - a real
    answer to "nobody was chosen," not a fizzle. When a player was chosen and
    is still in the game (CR 608.2b), every card in *their* graveyard (CR
    404.1) moves to the bottom of *their* library (CR 401.2: a library stays
    face-down and in whatever order it is put) - own graveyard included, an
    empty one just as legal a target as a full one, the same as
    `exile_target_players_graveyard`.

    "In a random order" is not CR 701.24's shuffle - that verb is reserved for
    "shuffle" itself (CR 701.24a), and this text never says it - so no shuffle
    trigger fires here, the same distinction `machines/keywords.cascade`
    already draws for "put the exiled cards on the bottom in a random order."
    The randomisation reuses `Game.shuffle_library`'s own reproducible seed
    (`shuffle_seed` plus a running counter) rather than a bare, unseeded
    `Random()`, so a scenario asserting on the resulting library order stays
    deterministic.
    """
    for target in game.resolve_targets(stack_object):
        if not isinstance(target, Player):
            continue
        cards = list(target.graveyard)
        if not cards:
            continue
        rng = Random(f"{game.shuffle_seed}:{game.shuffles_performed}:graveyard-bottom")  # noqa: S311
        rng.shuffle(cards)
        for card_state in cards:
            target.move(card_state, Zone.LIBRARY)
        game.shuffles_performed += 1


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


def _quality_word_matcher(word: str) -> Callable[[CardState], bool]:
    """One space-separated word of a search's stated quality - `_named_type_
    matcher`'s bare type or land type, or that same type qualified by a color
    adjective: "a colorless creature card" (Sanctum of Ugin) names a color
    *and* a type together, not two alternatives the way "artifact or creature"
    does, so `_named_type_matcher("colorless creature")` alone would try to
    read the whole two-word phrase as one type name, fail, and match nothing
    at all - a search that silently never finds anything is exactly the kind
    of quiet gap this wave is closing, not a new one to open. `_HAND_EXILE_
    COLOR_WORDS` is reused rather than duplicated - CR 105.2c's five colors
    plus colorless mean the same thing here as they do for Ugin's Labyrinth's
    own imprint quality.
    """
    parts = word.split()
    if len(parts) == 2 and parts[0] in _HAND_EXILE_COLOR_WORDS:
        color = _HAND_EXILE_COLOR_WORDS[parts[0]]
        type_matches = _named_type_matcher(parts[1])
        if color is None:
            return lambda state: not state.card.colors and type_matches(state)
        return lambda state: color in (state.card.colors or []) and type_matches(state)
    return _named_type_matcher(word)


def _quality_matcher(quality: str) -> Callable[[CardState], bool]:
    """A predicate for "a `<quality>` card" out of a search sentence.

    "Basic land" adds CR 205.4c's supertype check on top of whatever the rest
    of the phrase already means. Anything else is one or more type/subtype
    words (each optionally qualified by a color, see `_quality_word_matcher`)
    joined by "or" or a comma - fetchlands print two, Flagstones one - and
    matching any one of them is enough, the same "or" the card prints.
    """
    lowered = quality.strip().lower()
    if lowered.startswith("basic "):
        rest = _quality_matcher(lowered.removeprefix("basic "))

        def basic_matches(state: CardState) -> bool:
            return rest(state) and Supertype.BASIC in state.card.supertypes

        return basic_matches
    words = [word.strip() for word in re.split(r",\s*|\s+or\s+", lowered) if word.strip()]
    matchers = [_quality_word_matcher(word) for word in words]

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

#: Suspend's own line (CR 702.62a: "Suspend is a keyword that represents three
#: abilities" - none of them the spell's own CR 608.2c resolution instruction,
#: which is why Living End's "Suspend 3—{2}{B}{B}" has to come off before its
#: "Each player exiles ..." sentence is read as the whole effect. General to
#: the keyword's printed shape (a name, a number, an em dash, a cost), not to
#: this one card - any "Suspend N—[cost]" line strips the same way.
_SUSPEND_LINE_RE = re.compile(r"^Suspend \d+—[^\n]+\n+", re.MULTILINE | re.IGNORECASE)

#: Cascade's own line, reminder text and all (CR 702.85a). Printed as "Cascade
#: (reminder...)" ahead of whatever the spell also does - Violent Outburst's
#: "Creatures you control get +1/+0 until end of turn." - so without this, the
#: periods inside the reminder text get read by `_CLAUSE_SEPARATOR` as
#: sentence boundaries of their own and the real effect is lost along with the
#: garbage around it. General to the keyword, not to Violent Outburst: any
#: card pairing bare "Cascade" with its own resolution text hits the same bug.
_CASCADE_LINE_RE = re.compile(r"^Cascade(?:\s*\([^()]*\))?[ \t]*\n+", re.MULTILINE | re.IGNORECASE)

#: Rebound's own line (CR 702.88a), reminder text and all - Ephemerate prints
#: it *after* its one resolution sentence ("Exile target creature you
#: control, then return it to the battlefield under its owner's control.
#: \nRebound (...)"), unlike Suspend/Cascade's own lines above, which lead.
#: CR 702.88a is explicit that rebound "represents a static ability that
#: functions while the spell is on the stack" - it is never itself a CR
#: 608.2c resolution instruction, so leaving it in would hand `split_effect_
#: clauses` a bare "Rebound" clause with nothing this wave reads, taking the
#: real effect down with it (see `test_rebound.py`'s parser-level check).
_REBOUND_LINE_RE = re.compile(
    r"^[ \t]*Rebound(?:\s*\([^()]*\))?[ \t]*\n?", re.MULTILINE | re.IGNORECASE
)


def _strip_non_effect_preamble(text: str) -> str:
    """Sentences that describe the spell but are not part of resolving it."""
    text = _ADDITIONAL_COST_LINE_RE.sub("", text)
    text = _CANT_BE_COUNTERED_LINE_RE.sub("", text)
    text = _SUSPEND_LINE_RE.sub("", text)
    text = _CASCADE_LINE_RE.sub("", text)
    text = _REBOUND_LINE_RE.sub("", text)
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
#: "Exile target player's graveyard." (Bojuka Bog, Tormod's Crypt) - checked
#: ahead of `_EXILE_TARGET_RE` below, which would otherwise match the same
#: text (its `.*target.+` phrase is a superset), read `_targets_understood`
#: with `allow_player_targets` left at its default `False`, refuse the whole
#: clause on the player-target it cannot see, and `return None` before this
#: pattern ever got a turn - `_parse_targeted_clause` commits to the first
#: regex that fullmatches, not the first that also parses successfully.
_EXILE_TARGET_PLAYERS_GRAVEYARD_RE = re.compile(
    r"^exile (?P<phrase>.*target player's graveyard)\.?$", re.IGNORECASE
)
#: "Exile all graveyards." (Rest in Peace) and "Exile all cards that are
#: `<quality>` from all graveyards." (Sanctifier en-Vec) - no "target" at all
#: (CR 115.1 has nothing to target here), so neither collides with
#: `_EXILE_TARGET_RE`'s "target" requirement.
_EXILE_ALL_GRAVEYARDS_RE = re.compile(r"^exile all graveyards\.?$", re.IGNORECASE)
_EXILE_QUALITY_FROM_ALL_GRAVEYARDS_RE = re.compile(
    r"^exile all cards that are (?P<quality>.+?) from all graveyards\.?$", re.IGNORECASE
)
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
#: "Return target card from your graveyard to your hand." (Eternal Witness,
#: wrapped in "you may") and "Return target creature card from your graveyard
#: to your hand." (Raise Dead) - the same verb as `_RETURN_TARGET_RE` but "to
#: your hand" rather than "to its owner's hand", so the two patterns never
#: collide. `phrase` keeps "from your graveyard" inside it so
#: `_targets_understood` can see the zone the way it already reads "target
#: creature card in your graveyard" for `return_ability_targets_to_hand`
#: elsewhere in this file.
_RETURN_FROM_YOUR_GRAVEYARD_TO_HAND_RE = re.compile(
    r"return (?P<phrase>.*target.+from your graveyard) to your hand\.?$", re.IGNORECASE
)
#: "Up to one target player puts all the cards from their graveyard on the
#: bottom of their library in a random order." (Endurance) - CR 115.6's "up
#: to one" prefix sits before "target player", which is why `phrase` starts
#: with a greedy `.+` rather than anchoring on the word "target" itself.
_GRAVEYARD_TO_BOTTOM_OF_LIBRARY_RE = re.compile(
    r"^(?P<phrase>.*target player) puts all the cards from (?:their|his or her) graveyard "
    r"on the bottom of (?:their|his or her) library in a random order\.?$",
    re.IGNORECASE,
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
#: "<Source> deals N damage divided as you choose among one or two targets."
#: (Electrolyze) - CR 601.2d's division, read by `deal_divided_damage`, which
#: already does its own count-agnostic split at resolution rather than
#: needing `_targets_understood` to vet a restriction: the phrase is always
#: the fixed "one or two targets", never a printed restriction like "target
#: creature" this wave would otherwise have to read.
_DIVIDED_DAMAGE_RE = re.compile(
    rf".*\bdeals? (?P<n>{_COUNT}) damage divided as you choose among one or two targets\.?$",
    re.IGNORECASE,
)
#: "<Source> deals N damage to each opponent." (Guttersnipe) - CR 119.3, with
#: no target at all: "each opponent" is CR 102.2's "the other player" (in a
#: two-player game), not something chosen.
#: Ability-side only: `damage_each_opponent` reads `ability.controller`
#: directly rather than through `Game.controller_of`, which is only ever
#: handed a triggered or activated ability here (no spell in the pool prints
#: this shape).
_DAMAGE_EACH_OPPONENT_RE = re.compile(
    rf".*\bdeals? (?P<n>{_COUNT}) damage to each opponent\.?$", re.IGNORECASE
)
#: "Prevent all combat damage that would be dealt this turn." (Fog, Angelsong)
#: - CR 615.1a's prevention effect naming neither a permanent nor a player, so
#: the shield protects the whole board; see `prevent_all_combat_damage`.
_PREVENT_ALL_COMBAT_DAMAGE_RE = re.compile(
    r"^prevent all combat damage that would be dealt this turn\.?$", re.IGNORECASE
)
#: "Prevent the next N damage that would be dealt to any target this turn."
#: (Bandage) - CR 615.7's counting shield around whichever kind of target CR
#: 115.1 hands back; see `prevent_next_damage_to_target`.
_PREVENT_NEXT_DAMAGE_TO_TARGET_RE = re.compile(
    rf"prevent the next (?P<n>{_COUNT}) damage that would be dealt to "
    r"(?P<phrase>any target|.*target.+) this turn\.?$",
    re.IGNORECASE,
)
#: "Each player exiles all creature cards from their graveyard, then
#: sacrifices all creatures they control, then puts all cards they exiled
#: this way onto the battlefield." (Living End) - three CR 608.2c instructions
#: joined by "then" inside one sentence, so `_spell_effect_or_notice` matches
#: this against the whole (preamble-stripped) text before `_CLAUSE_SEPARATOR`
#: ever gets to cut it into three fragments on its own "then"s; see
#: `each_player_exiles_sacrifices_and_returns_creatures`.
_EACH_PLAYER_EXILE_SACRIFICE_RETURN_RE = re.compile(
    r"^each player exiles all creature cards from (?:their|his or her) graveyard, "
    r"then sacrifices all creatures they control, then puts all cards they "
    r"exiled this way onto the battlefield\.?$",
    re.IGNORECASE,
)
#: "The next time target creature would deal damage this turn, prevent that
#: damage." (Awe Strike) - CR 615.8's next-instance shield naming a *source*,
#: not a shielded object; see `_prevent_next_damage_from_target` and
#: `_merge_prevent_damage_from_target_clauses` for the optional CR 615.5
#: life-gain rider on the sentence after it.
_PREVENT_NEXT_TIME_TARGET_WOULD_DEAL_DAMAGE_RE = re.compile(
    r"^the next time (?P<phrase>target creature) would deal damage this turn, "
    r"prevent that damage\.?$",
    re.IGNORECASE,
)
#: The optional CR 615.5 rider naming the amount by its own effect rather
#: than a fixed number - "You gain life equal to the damage prevented this
#: way."
_GAIN_LIFE_EQUAL_TO_DAMAGE_PREVENTED_RE = re.compile(
    r"^you gains? life equal to the damage prevented this way\.?$", re.IGNORECASE
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


def _merge_prevent_damage_from_target_clauses(
    clauses: list[str], index: int
) -> tuple[int, TargetedClause] | None:
    """ "The next time target creature would deal damage this turn, prevent
    that damage." (Awe Strike), plus its optional CR 615.5 rider on the
    sentence right after it - "You gain life equal to the damage prevented
    this way."

    Not `for_spell`-gated: `_prevent_next_damage_from_target`'s effect reads
    the resolving object generically through `Game.resolve_card_targets`/
    `Game.controller_of`, the same as `create_continuous_effect_of_ability`
    does, so there is no reason to refuse an ability printing this shape.

    Returns how many clauses starting at `index` belong to this one
    instruction, and the effect to run for both, or `None` if `index` is not
    the start of this shape at all.
    """
    match = _PREVENT_NEXT_TIME_TARGET_WOULD_DEAL_DAMAGE_RE.fullmatch(clauses[index])
    if match is None:
        return None
    if not _targets_understood(match.group("phrase")):
        return None
    gains_life = index + 1 < len(clauses) and bool(
        _GAIN_LIFE_EQUAL_TO_DAMAGE_PREVENTED_RE.fullmatch(clauses[index + 1])
    )
    consumed = 2 if gains_life else 1
    return consumed, _prevent_next_damage_from_target(gains_life=gains_life)


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

    if match := _EXILE_TARGET_PLAYERS_GRAVEYARD_RE.fullmatch(clause):
        # Ahead of `_EXILE_TARGET_RE`: that pattern's phrase is a superset of
        # this one's and would otherwise commit first, read the player target
        # with `allow_player_targets` left `False`, and refuse the clause.
        if not _targets_understood(match.group("phrase"), allow_player_targets=True):
            return None
        return exile_target_players_graveyard

    if _EXILE_ALL_GRAVEYARDS_RE.fullmatch(clause):
        return exile_all_graveyards  # type: ignore[return-value]

    if match := _EXILE_QUALITY_FROM_ALL_GRAVEYARDS_RE.fullmatch(clause):
        matches = _graveyard_exile_quality_matcher(match.group("quality"))
        if matches is None:
            return None
        return _exile_matching_from_all_graveyards(matches)

    if match := _EXILE_TARGET_RE.fullmatch(clause):
        if not _targets_understood(
            match.group("phrase"), count_agnostic=True, battlefield_only=False
        ):
            return None
        return exile_ability_targets

    if match := _RETURN_FROM_YOUR_GRAVEYARD_TO_HAND_RE.fullmatch(clause):
        if not _targets_understood(
            match.group("phrase"), count_agnostic=True, battlefield_only=False
        ):
            return None
        return return_ability_targets_to_hand

    if match := _RETURN_TARGET_RE.fullmatch(clause):
        if not _targets_understood(
            match.group("phrase"), count_agnostic=True, battlefield_only=False
        ):
            return None
        return return_ability_targets_to_hand

    if match := _GRAVEYARD_TO_BOTTOM_OF_LIBRARY_RE.fullmatch(clause):
        if not _targets_understood(
            match.group("phrase"), count_agnostic=True, allow_player_targets=True
        ):
            return None
        return puts_graveyard_on_bottom_of_library

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

    if match := _DIVIDED_DAMAGE_RE.fullmatch(clause):
        # "one or two targets" is fixed by the sentence itself (CR 601.2d),
        # never a printed restriction to vet through `_targets_understood`.
        amount = _count(match.group("n"))
        return deal_divided_damage(amount)  # type: ignore[return-value]

    if match := _DAMAGE_EACH_OPPONENT_RE.fullmatch(clause):
        # No target at all (CR 102.2's "each opponent"), so nothing to check
        # through `_targets_understood` - and `damage_each_opponent` reads
        # `ability.controller` directly, which only an `AbilityOnStack` has.
        if for_spell:
            return None
        amount = _count(match.group("n"))
        return damage_each_opponent(amount)  # type: ignore[return-value]

    if _PREVENT_ALL_COMBAT_DAMAGE_RE.fullmatch(clause):
        return prevent_all_combat_damage  # type: ignore[return-value]

    if match := _PREVENT_NEXT_DAMAGE_TO_TARGET_RE.fullmatch(clause):
        if not _targets_understood(match.group("phrase"), allow_player_targets=True):
            return None
        amount = _count(match.group("n"))
        return prevent_next_damage_to_target(amount)  # type: ignore[return-value]

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
        second_stripped = second.strip()
        if _ANAPHORIC_SUBJECT_RE.fullmatch(second_stripped):
            if _parse_anaphoric_clause_pair(first, second, for_spell=for_spell) is None:
                return second
            continue
        if (
            _LOOKS_LIKE_RETURN_TO_BATTLEFIELD_RE.match(second_stripped)
            and _parse_exile_then_return_clause_pair(first, second, for_spell=for_spell) is None
        ):
            return second
    return None


class ImprintNotice(BaseModel):
    """One "you may exile a `<quality>` card ... from your hand" effect (CR
    207.2c's "Imprint" ability word, and its plain-English relatives) whose
    stated quality this wave could not read.

    This is the shape Ugin's Labyrinth's own defect was found in: a card whose
    ETB trigger offered no decision at all and simply resolved doing nothing,
    with nothing anywhere recording that a choice had gone unoffered. Once the
    shape itself is read (`_parse_imprint_clause`), the only way this can
    still happen is a quality word this wave does not recognise - and that gap
    gets this notice instead of the same silence, the same "unreadable is not
    the same as no effect" record `TargetingNotice`, `InterveningIfNotice`,
    `ModeNotice`, `AnaphoricClauseNotice`, `LayerNotice`, and
    `CostModifierNotice` already keep for their own.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    """The unreadable clause itself, as printed."""


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


#: "[its controller ]add[s] an additional <mana>." - the resolution half of
#: CR 605.1b's triggered mana ability: "an ability that triggers whenever a
#: permanent 'is tapped for mana' ... triggers whenever such a mana ability
#: resolves and produces mana" (CR 106.12a), and this is what that trigger
#: itself does when it resolves. Three pool cards share exactly this
#: template - Utopia Sprawl's "its controller adds an additional one mana of
#: the chosen color", Leyline of Abundance's and Badgermole Cub's "add an
#: additional {G}" - and this is a text-template parser reached through
#: `_ability_effect_or_notice`'s fallback, not a per-card row: keying this on
#: card name would make Utopia Sprawl's own defect report pass while Leyline
#: and Badgermole stayed silent, which is exactly the shadowing
#: `test_registry_is_minimal.py` exists to catch elsewhere in this file.
#:
#: "its controller" is **not** this ability's own controller - it is the
#: *enchanted permanent's* controller (CR 303.4e lets an Aura's controller and
#: the enchanted permanent's controller differ), read off `attached_to` on the
#: ability's source. An implicit subject ("add an additional {G}.") means the
#: ability's own controller instead, which is what Leyline of Abundance and
#: Badgermole Cub - creatures with no "enchanted" anything to point at - both
#: rely on.
_MANA_ADD_RE = re.compile(
    r"^(?:(?P<subject>its controller)\s+)?adds? an additional (?P<mana>.+?)\.?$",
    re.IGNORECASE,
)
#: "one mana of the chosen color" - CR 614.12a's choice, read back by name
#: (Utopia Sprawl). Distinct from a literal mana symbol, which names its color
#: outright and needs no choice recorded anywhere.
_CHOSEN_COLOR_MANA_RE = re.compile(r"^one mana of the chosen color$", re.IGNORECASE)
#: A literal mana symbol or run of them - "{G}" (Leyline of Abundance,
#: Badgermole Cub). `findall` plus a round-trip check (rather than trusting
#: `findall` alone) is what refuses "{G} or {U}" - a choice this template does
#: not carry - instead of silently reading it as both colors at once.
_MANA_SYMBOL_RE = re.compile(r"\{([WUBRGC])\}", re.IGNORECASE)


def _parse_mana_adding_trigger(text: str) -> AbilityEffect | None:
    """CR 605.1b's mana-adding trigger, read off its own printed text.

    Returns `None` for anything that is not exactly this template, so a card
    this does not cover (a variable amount, a choice of colors rather than one
    chosen ahead of time) falls through to the ordinary clause parsers below
    rather than being half-read.
    """
    match = _MANA_ADD_RE.fullmatch(text.strip())
    if match is None:
        return None
    mana_spec = match.group("mana").strip()
    from_enchanted = match.group("subject") is not None

    chosen_color = bool(_CHOSEN_COLOR_MANA_RE.fullmatch(mana_spec))
    literal_colors: list[Color] | None = None
    if not chosen_color:
        symbols = _MANA_SYMBOL_RE.findall(mana_spec)
        round_trip = "".join(f"{{{symbol}}}" for symbol in symbols)
        if not symbols or round_trip.lower() != mana_spec.lower().replace(" ", ""):
            return None
        literal_colors = [Color(symbol.upper()) for symbol in symbols]

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None:
            return
        if from_enchanted:
            enchanted = (
                game.find_by_id(source.attached_to) if source.attached_to is not None else None
            )
            controller = enchanted.controller if enchanted is not None else None
        else:
            controller = ability.controller
        if controller is None:
            return

        if chosen_color:
            choice = source.choice
            if choice is None or choice.kind is not ChoiceKind.COLOR:
                return
            try:
                produced = [Color(choice.value)]
            except ValueError:
                return
        else:
            assert literal_colors is not None
            produced = literal_colors

        pool = game.player(controller).mana_pool
        for color in produced:
            pool.add(color)

    return effect


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

    Tried ahead of everything else: `_parse_conditional_sacrifice_clause`'s
    "you may sacrifice ... If you do, ..." shape (CR 118.12) has to be read
    off the *whole*, unsplit text the same way `_EACH_PLAYER_EXILE_SACRIFICE_
    RETURN_RE` is in `_spell_effect_or_notice` below - Disciple of Freyalise's
    own "you gain X life and draw X cards, where X is that creature's power"
    is one CR 608.2c instruction that `split_effect_clauses`'s bare "and" cut
    would otherwise slice into fragments none of `parse_mixed_effect`'s
    per-clause parsers read.

    Also tried ahead of everything else: `_parse_mana_adding_trigger`'s
    "[its controller ]adds an additional <mana>" shape (CR 605.1b, CR
    106.12a) - Utopia Sprawl, Leyline of Abundance, Badgermole Cub. None of
    `parse_clause_effect`'s player-clause shapes read "add mana" at all, so
    without this the whole ability would fall through every check below and
    come back `None`, exactly the reported defect.
    """
    conditional_sacrifice = _parse_conditional_sacrifice_clause(effect_text, for_spell=False)
    if conditional_sacrifice is not None:
        return conditional_sacrifice
    mana_adding = _parse_mana_adding_trigger(effect_text)
    if mana_adding is not None:
        return mana_adding
    parsed = parse_mixed_effect(effect_text)
    if parsed is not None:
        return parsed
    if _is_layer_effect_text(effect_text):
        return create_continuous_effect_of_ability
    unread_conditional = _unreadable_conditional_clause(effect_text, for_spell=False)
    if unread_conditional is not None:

        def conditional_notice_only(game: "Game", ability: AbilityOnStack) -> None:
            game.conditional_clause_notices.append(
                ConditionalClauseNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=unread_conditional,
                )
            )

        return conditional_notice_only

    unread_anaphoric = _unreadable_anaphoric_clause(effect_text, for_spell=False)
    if unread_anaphoric is not None:

        def anaphoric_notice_only(game: "Game", ability: AbilityOnStack) -> None:
            game.anaphoric_clause_notices.append(
                AnaphoricClauseNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=unread_anaphoric,
                )
            )

        return anaphoric_notice_only

    unread_delayed = _unreadable_delayed_clause(effect_text, for_spell=False)
    if unread_delayed is not None:

        def delayed_notice_only(game: "Game", ability: AbilityOnStack) -> None:
            game.delayed_clause_notices.append(
                DelayedClauseNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=unread_delayed,
                )
            )

        return delayed_notice_only

    unread_imprint = _unreadable_imprint_quality(effect_text)
    if unread_imprint is not None:

        def imprint_notice_only(game: "Game", ability: AbilityOnStack) -> None:
            game.imprint_notices.append(
                ImprintNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=unread_imprint,
                )
            )

        return imprint_notice_only

    unread_cast_permission = _unreadable_cast_permission_clause(effect_text, for_spell=False)
    if unread_cast_permission is not None:

        def cast_permission_notice_only(game: "Game", ability: AbilityOnStack) -> None:
            game.unmodeled_trigger_effect_notices.append(
                UnmodeledTriggerEffectNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=unread_cast_permission,
                )
            )

        return cast_permission_notice_only

    unread_hand_choice = _unreadable_unbounded_hand_choice_clause(effect_text, for_spell=False)
    if unread_hand_choice is not None:

        def unbounded_hand_choice_notice_only(game: "Game", ability: AbilityOnStack) -> None:
            game.unmodeled_trigger_effect_notices.append(
                UnmodeledTriggerEffectNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=unread_hand_choice,
                )
            )

        return unbounded_hand_choice_notice_only

    unread_event_player_target = _unreadable_event_player_target_clause(
        effect_text, for_spell=False
    )
    if unread_event_player_target is not None:

        def event_player_target_notice_only(game: "Game", ability: AbilityOnStack) -> None:
            game.unmodeled_trigger_effect_notices.append(
                UnmodeledTriggerEffectNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=unread_event_player_target,
                )
            )

        return event_player_target_notice_only

    return None


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
    whole = _strip_non_effect_preamble(effect_text).strip()
    if _EACH_PLAYER_EXILE_SACRIFICE_RETURN_RE.fullmatch(whole):
        # Read whole, ahead of `parse_mixed_effect_for_spell`: the sentence's
        # own ", then " joins are CR 608.2c instructions in one breath, not
        # three clauses `_CLAUSE_SEPARATOR` may cut apart and fail separately.
        return each_player_exiles_sacrifices_and_returns_creatures
    conditional_sacrifice = _parse_conditional_sacrifice_clause(effect_text, for_spell=True)
    if conditional_sacrifice is not None:
        return conditional_sacrifice
    parsed = parse_mixed_effect_for_spell(effect_text)
    if parsed is not None:
        return parsed
    if _is_layer_effect_text(effect_text):
        return create_continuous_effect
    unread_conditional = _unreadable_conditional_clause(effect_text, for_spell=True)
    if unread_conditional is not None:

        def conditional_notice_only(game: "Game", spell: CardState) -> None:
            game.conditional_clause_notices.append(
                ConditionalClauseNotice(
                    source_id=spell.id, source_name=spell.card.name, text=unread_conditional
                )
            )

        return conditional_notice_only

    unread = _unreadable_anaphoric_clause(effect_text, for_spell=True)
    if unread is not None:

        def anaphoric_notice_only(game: "Game", spell: CardState) -> None:
            game.anaphoric_clause_notices.append(
                AnaphoricClauseNotice(source_id=spell.id, source_name=spell.card.name, text=unread)
            )

        return anaphoric_notice_only
    unread_delayed = _unreadable_delayed_clause(effect_text, for_spell=True)
    if unread_delayed is None:
        return None

    def delayed_notice_only(game: "Game", spell: CardState) -> None:
        game.delayed_clause_notices.append(
            DelayedClauseNotice(
                source_id=spell.id, source_name=spell.card.name, text=unread_delayed
            )
        )

    return delayed_notice_only


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


#: "return it/that card/that permanent/that creature to the battlefield[
#: tapped][ transformed][ under its owner's/your control]." - the return half
#: of Ephemerate's own "Exile target creature you control, then return it to
#: the battlefield under its owner's control." (CR 608.2c: one instruction in
#: two sentences), and of the same "blink" idiom wherever else a card states
#: it as a direct instruction rather than through a delayed trigger -
#: `machines/delayed.return_subject_to_battlefield_under_owner` already
#: covers Phelia's own "at the beginning of the next end step" variant, and
#: `machines/keywords.persist_return`/`earthbend` cover the two keyworded
#: shapes; none of the three reach this regex, and this one does not reach
#: them. `fullmatch` only, and no bare "return it to the battlefield." with
#: none of the three optional groups - that shape names no controller at all
#: and CR 110.2a leaves it to whoever the effect names elsewhere, which is
#: not something a lone regex on this one sentence can decide, so it is left
#: unread (see `_UNREAD_RETURN_TO_BATTLEFIELD_RE` below) rather than guessed.
_RETURN_TO_BATTLEFIELD_RE = re.compile(
    r"^return (?:it|that (?:card|permanent|creature))"
    r" to the battlefield"
    r"(?P<tapped> tapped)?"
    r"(?P<transformed> transformed)?"
    r"(?: under (?P<control>its owner's|your) control)?\.?$",
    re.IGNORECASE,
)

#: A looser prefix match for the same shape, used only by
#: `_unreadable_anaphoric_clause` to tell "this is recognisably a return-to-
#: battlefield sentence this wave cannot fully read" apart from "this is some
#: other second sentence entirely" - CR 608.2c has no notion of running half
#: of "exile ..., then return ...", so a card whose own wording falls outside
#: `_RETURN_TO_BATTLEFIELD_RE`'s three optional groups must still take the
#: whole effect down with it rather than silently keep only the exile half
#: (trap: an exile with nothing to return it is strictly worse than doing
#: nothing at all).
_LOOKS_LIKE_RETURN_TO_BATTLEFIELD_RE = re.compile(
    r"^return (?:it|that \w+) to the battlefield", re.IGNORECASE
)


def _parse_exile_then_return_clause_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "Exile target X, then return it to the battlefield ..." as one CR
    608.2c instruction, or `None` if this shape does not match.

    The exile half is `_EXILE_TARGET_RE`, exactly the shape `exile_ability_
    targets` reads alone - CR 608.2b's target-legality recheck belongs only
    to it, since "it" in the second sentence is CR 400.7's anaphora back to
    whatever the first sentence found, not a target of its own (the same
    reasoning `_parse_anaphoric_clause_pair` already documents for "its
    controller ...").

    `Game.exile_permanent` then `Game.put_onto_battlefield` are the same two
    primitives `each_player_exiles_sacrifices_and_returns_creatures` already
    uses for Living End, so what comes back is CR 400.7's genuine new object:
    a fresh `zone_change_stamp`, no memory of its counters (CR 122.2), and
    summoning-sick again (CR 302.6, 508.1a) - `move_to`'s battlefield branch
    sets that unconditionally and this function never touches it.

    CR 110.2a is why the controller is read off the card's own words rather
    than defaulted to whoever controls the resolving spell or ability: "If an
    effect instructs a player to put an object onto the battlefield, that
    object enters the battlefield under that player's control unless the
    effect states otherwise" - Ephemerate states otherwise ("under its
    owner's control"), so `exiled.owner`, not the caster, is who `Game.
    put_onto_battlefield` is called with. Owner and controller are never
    collapsed into one question: a creature blinked out from under an
    opponent's control returns to the *opponent*, not to whoever cast
    Ephemerate, exactly when the card says "its owner's control", and to the
    caster only when it says "your control" instead.
    """
    return_match = _RETURN_TO_BATTLEFIELD_RE.fullmatch(second.strip())
    if return_match is None:
        return None
    exile_match = _EXILE_TARGET_RE.fullmatch(first.strip())
    if exile_match is None:
        return None
    if not _targets_understood(exile_match.group("phrase"), count_agnostic=True):
        return None

    tapped = return_match.group("tapped") is not None
    transformed = return_match.group("transformed") is not None
    control = return_match.group("control")

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            exiled = game.exile_permanent(target)
            if exiled.zone is not Zone.EXILE:
                continue  # CR 111.8: a token refused the move; nothing to return.
            owner = exiled.owner or controller
            new_controller = owner if control == "its owner's" else controller
            returned = game.put_onto_battlefield(exiled, new_controller, tapped=tapped)
            if transformed and returned.zone is Zone.BATTLEFIELD:
                returned.transform()

    return effect


#: "Imprint" and its plain-English relatives - "you may exile a `<quality>`
#: card [with mana value N or greater/less] from your hand" (Ugin's
#: Labyrinth). CR 207.2c: "Imprint" is an ability word and "[has] no special
#: rules meaning" of its own, so nothing here reads the word itself - only the
#: sentence that follows it, the same CR 608.2d "you may" shape
#: `_parse_optional_player_clause` reads for a plain player clause, with a
#: quality restriction on top the way `_SEARCH_AND_PUT_RE` restricts a search.
_HAND_EXILE_RE = re.compile(
    r"you may exile (?:a|an) (?P<quality>.+?) card"
    r"(?: with mana value (?P<mv>\d+) or (?P<cmp>greater|less))?"
    r" from your hand",
    re.IGNORECASE,
)

#: CR 105.2c: "A colorless object has no color" - colorless is not one of CR
#: 105.1's five colours, so it is not `Color.COLORLESS` matched against
#: `Card.colors` (never populated with it), it is the absence check itself.
_HAND_EXILE_COLOR_WORDS: dict[str, Color | None] = {
    "colorless": None,
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}


def _hand_exile_quality_matcher(quality: str) -> Callable[[CardState], bool] | None:
    """A predicate for `_HAND_EXILE_RE`'s "a `<quality>` card", or `None` if
    this wave cannot read it.

    Fail-closed on purpose: an unrecognised quality refuses the whole clause
    (`_parse_imprint_clause`) rather than asking "you may exile a card from
    your hand" about the wrong cards - see `_unreadable_imprint_quality` for
    what happens to a quality this refuses, which is not silence.
    """
    lowered = quality.strip().lower()
    if lowered in _HAND_EXILE_COLOR_WORDS:
        color = _HAND_EXILE_COLOR_WORDS[lowered]
        if color is None:
            return lambda state: not state.card.colors
        return lambda state: color in (state.card.colors or [])
    try:
        card_type = Type(lowered)
    except ValueError:
        return None
    return lambda state: card_type in state.card.types


def _hand_exile_mv_matcher(mv: str | None, cmp: str | None) -> Callable[[CardState], bool]:
    """CR 202.3's mana value, bounded by `_HAND_EXILE_RE`'s optional "with mana
    value N or greater/less" - both directions, unlike `_bounded_quality_
    matcher`'s search-only ceiling, because Ugin's Labyrinth's own restriction
    is a floor ("or greater").
    """
    if mv is None:
        return lambda state: True
    bound = int(mv)
    if cmp == "greater":
        return lambda state: (state.card.cmc or 0) >= bound
    return lambda state: (state.card.cmc or 0) <= bound


def _hand_exile_description(match: re.Match[str]) -> str:
    description = match.group("quality").strip()
    if match.group("mv"):
        description = f"{description} with mana value {match.group('mv')} or {match.group('cmp')}"
    return description


def _permanent_id_and_name(stack_object: "StackObject", *, for_spell: bool) -> tuple[UUID, str]:
    """The id and display name of whatever ability this clause is printed on -
    the spell's own id and name if it resolves as a permanent (a spell keeps
    its `id` once it becomes the battlefield object, see `CardState.move_to`),
    or the resolving ability's `source_id`/`source_name` (CR 113.7a: the
    source may already be gone, which is why the name travels separately).
    """
    if for_spell:
        assert isinstance(stack_object, CardState)
        return stack_object.id, stack_object.card.name
    assert isinstance(stack_object, AbilityOnStack)
    source_id = stack_object.source_id
    assert source_id is not None
    return source_id, stack_object.source_name


def _parse_imprint_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Imprint — When this land enters, you may exile a colorless card with
    mana value 7 or greater from your hand." (Ugin's Labyrinth), read off the
    ability's own printed text so no registry row is needed.

    CR 608.2d: nobody is *made* to exile anything, so this is a plain "you
    may" - `DecisionKind.MAY` - with `affirmative_is_legal` set to whether a
    legal card exists in hand at all: if none does, the choice is not merely a
    bad idea, it is impossible, and CR 608.2d forbids choosing it (the same
    `affirmative_is_legal` shape `may_pay_life` already uses for CR 119.4).
    *Which* card, once "yes" is legal and chosen, is `DecisionKind.CHOOSE_
    CARDS`, the same CR 608.2d machinery `seasoned_pyromancer`'s discard and
    `malevolent_rumble`'s "put a permanent card into your hand" both use.

    The exiled card is annotated `ExileMarker.IMPRINTED`, pointing back at the
    resolving permanent's own id - the only thing a later "exiled with this
    land" ability (`ManaCondition.imprinted`, `Game.card_imprinted_on`) can
    mean, since "imprint" itself carries no rules meaning of its own
    (CR 207.2c).
    """
    match = _HAND_EXILE_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    quality_matches = _hand_exile_quality_matcher(match.group("quality"))
    if quality_matches is None:
        return None
    mv_matches = _hand_exile_mv_matcher(match.group("mv"), match.group("cmp"))
    description = _hand_exile_description(match)

    def matches(state: CardState) -> bool:
        return quality_matches(state) and mv_matches(state)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source_id, source_name = _permanent_id_and_name(stack_object, for_spell=for_spell)
        candidates = [state for state in player.hand if matches(state)]
        decision = Decision(
            kind=DecisionKind.MAY,
            player=player.username,
            prompt=f"exile a {description} card from your hand",
            source=source_name,
            affirmative_is_legal=bool(candidates),
        )
        if not game.ask(decision):
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt=f"choose a {description} card to exile",
                source=source_name,
                amount=1,
                cards=tuple(state.id for state in candidates),
            )
        )
        assert isinstance(chosen_ids, tuple)
        by_id = {state.id: state for state in candidates}
        chosen = by_id[chosen_ids[0]]
        player.cards_in(Zone.HAND).remove(chosen)
        chosen.move_to(Zone.EXILE)
        chosen.exile_annotation = ExileAnnotation(
            marker=ExileMarker.IMPRINTED, owner=chosen.owner, linked_permanent_id=source_id
        )
        game.exile.append(chosen)

    return effect


def _unreadable_imprint_quality(text: str) -> str | None:
    """The `_HAND_EXILE_RE` clause inside `text`, if it matches CR 608.2d's
    "you may exile a `<quality>` card ... from your hand" shape but this
    wave's `_hand_exile_quality_matcher` cannot read the stated quality -
    used only to decide whether a parse failure deserves an `ImprintNotice`,
    the same way `_unreadable_anaphoric_clause` decides for its own shape.
    """
    clauses = _prepare_effect_clauses(text)
    if clauses is None:
        return None
    for clause in clauses:
        match = _HAND_EXILE_RE.fullmatch(clause.strip().rstrip("."))
        if match is None:
            continue
        if _hand_exile_quality_matcher(match.group("quality")) is None:
            return clause
    return None


#: Ugin's Labyrinth's third ability: "{T}: Return the exiled card to its
#: owner's hand." "The exiled card" is a definite reference to whichever card
#: `_parse_imprint_clause` linked to this permanent, not a target - CR 601.2c
#: never has this ability's activation choose one.
_RETURN_IMPRINTED_RE = re.compile(
    r"^return the exiled card to (?:its|their) owner's hand$", re.IGNORECASE
)


def _parse_return_imprinted_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """The other half of the imprint shape: giving the linked card back.

    Found by `Game.card_imprinted_on` rather than kept as a pointer of its
    own, so it survives however the card got there. CR 608.2b's "the effect
    does as much as possible" covers the two ways there is nothing to
    return - no card was ever exiled, or the link has gone stale (see
    `ExileAnnotation.linked_permanent_id`'s own docstring) - both leave this a
    no-op rather than an error.
    """
    if not _RETURN_IMPRINTED_RE.fullmatch(clause.strip().rstrip(".")):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source_id, _ = _permanent_id_and_name(stack_object, for_spell=for_spell)
        card = game.card_imprinted_on(source_id)
        if card is None:
            return
        owner_name = card.owner or game.controller_of(stack_object).username
        game.exile.remove(card)
        game.player(owner_name).add(card, Zone.HAND)

    return effect


# --------------------------------------------------------------------------
# "You may sacrifice ... If you do, ..." (CR 118.12)
# --------------------------------------------------------------------------
#
# Verified this session with `knowledge_search(q="...", type="rules")`, then
# read in full off the local CR mirror at the tail `knowledge_search`'s own
# 180-character truncation cut off, at CR 118.12 (the search's own excerpt
# confirmed that number and no other):
#
#   "Some spells, activated abilities, and triggered abilities read, '[Do
#   something]. If [a player] [does, doesn't, or can't], [effect].' Or '[A
#   player] may [do something]. If [that player] [does, doesn't, or can't],
#   [effect].' The action [do something] is a cost, paid when the spell or
#   ability resolves. The 'If [a player] [does, doesn't, or can't]' clause
#   checks whether the player chose to pay an optional cost or started to pay
#   a mandatory cost, regardless of what events actually occurred."
#
# Two consequences of that last sentence drive everything below:
#
# - "If you do" is not a check on the *board* after the sacrifice - it is a
#   check on the *choice*. Once CR 608.2d's "you may" comes back yes, the
#   sacrifice always succeeds (CR 701.21a has no failure mode for sacrificing
#   a permanent you control - unlike `destroy`, nothing refuses it), so this
#   never has to ask "did it actually happen"; it only has to ask "did the
#   player say yes", exactly the `Game.may`/`Game.ask(MAY)` question
#   `_optional_clause` and `_optional_targeted_clause` already put for every
#   other "you may".
# - CR 608.2d then forbids offering a choice with no legal way to pay it: a
#   "you may sacrifice another creature" with no other creature to sacrifice
#   is not merely a bad idea, it is impossible, the same `affirmative_is_
#   legal` shape `may_pay_life` (CR 119.4) and `_parse_imprint_clause`
#   (CR 608.2d generally) already use. Disciple of Freyalise with no other
#   creature on the battlefield is never asked the question at all.
#
# The sacrificed permanent's power is read **before** `Game.sacrifice` moves
# it to the graveyard, the same CR 608.2i snapshot `_parse_anaphoric_clause_
# pair` already takes for "its controller gains life equal to its power" -
# reading it afterward would see the empty post-`move_to` husk instead of the
# real, possibly anthemed or +1/+1-countered, value.

#: The whole shape, read off the ability's own printed text with the clause
#: splitter never touched: `split_effect_clauses`'s bare `\band\b` cut would
#: otherwise slice Disciple of Freyalise's own "you gain X life and draw X
#: cards, where X is that creature's power" into three unrelated fragments,
#: the same reason `_EACH_PLAYER_EXILE_SACRIFICE_RETURN_RE` is read whole
#: ahead of the ordinary dispatcher rather than through it.
_MAY_SACRIFICE_IF_YOU_DO_RE = re.compile(
    r"^you may sacrifice (?P<restriction>[^.]+)\.\s*if you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)

#: Every noun `_sacrifice_restriction` accepts after "this " - a card type
#: (CR 205.2a) or the bare word "permanent" itself. Slayer of the Wicked's
#: "target Vampire, Werewolf, or Zombie" kind of compound restriction is not
#: read here any more than it is by `_targets_understood` - a restriction
#: this wave cannot pin down to a single `Type` fails the whole clause
#: (see `_sacrifice_restriction`), which is what earns it a `ConditionalClause
#: Notice` instead of silently offering to sacrifice anything at all.
_SACRIFICE_SELF_NOUNS: frozenset[str] = frozenset({member.value for member in Type}) | {"permanent"}

#: "you gain X life" / "draw X cards" - the two `_parse_x_magnitude_body`
#: clauses this wave reads with the sacrificed permanent's power substituted
#: in for X. Anything else in the "where X is ..." body (a token count, a
#: counter placed, a fixed-number clause `parse_clause_effect` already reads
#: on its own) is refused rather than guessed at.
_GAIN_X_LIFE_RE = re.compile(r"^(?:you )?gains? X life$", re.IGNORECASE)
_DRAW_X_CARDS_RE = re.compile(r"^draws? X cards?$", re.IGNORECASE)


def _sacrifice_restriction(
    restriction: str,
) -> tuple[bool, Callable[["Game", Player, UUID], list[CardState]]] | None:
    """`restriction` - the text between "sacrifice" and the following period -
    read as either "this `<type>`" (the permanent bearing the ability itself,
    Sanctum of Ugin) or "another `<type>`" (a second permanent the player
    controls of the stated type, Disciple of Freyalise), paired with a
    function that reads the actual legal candidates off the battlefield at
    resolution time - never at parse time, since what is on the battlefield
    changes between then and resolution.

    Returns `(is_self, candidates)`: `is_self` says whether there is a real
    CR 608.2d choice of *which* permanent to sacrifice (false for "this
    `<type>`", where there is only ever one, CR 601.2c never asks a question
    with one answer) or a genuine one among however many candidates
    `candidates` finds (true only in name for "another `<type>`" - the
    "false"/"true" pairing here is the reverse of confusing: `is_self` is
    true for the self-reference shape).

    Anything else - "a `<type>`" with no "this"/"another", a compound
    restriction, a `<type>` this wave cannot read as a single `Type` - comes
    back `None`, fail-closed.
    """
    restriction = restriction.strip().lower()
    if restriction.startswith("this "):
        noun = restriction.removeprefix("this ").strip()
        if noun not in _SACRIFICE_SELF_NOUNS:
            return None

        def self_candidates(game: "Game", player: Player, source_id: UUID) -> list[CardState]:
            permanent = game.find_by_id(source_id)
            if permanent is None or permanent.zone is not Zone.BATTLEFIELD:
                return []
            return [permanent]

        return True, self_candidates

    if restriction.startswith("another "):
        noun = restriction.removeprefix("another ").strip()
        try:
            card_type = Type(noun)
        except ValueError:
            return None

        def other_candidates(game: "Game", player: Player, source_id: UUID) -> list[CardState]:
            return [
                permanent
                for permanent in game.battlefield
                if permanent.controller == player.username
                and permanent.id != source_id
                and card_type in permanent.card.types
            ]

        return False, other_candidates

    return None


def _is_referent_power_expression(expr: str) -> bool:
    """Whether `expr` - the tail of a "where X is `<expr>`" clause - is
    exactly a sacrificed permanent's power, read the same two ways CR 400.7's
    anaphora prints it: "its power" and "that `<type>`'s power" (Disciple of
    Freyalise's own wording). The only value expression this wave reads off a
    sacrificed permanent, the same narrow scope `_read_referent_power_
    expression` already draws for a destroyed or exiled one.
    """
    lowered = expr.strip().rstrip(".").strip().lower()
    return lowered == "its power" or bool(re.fullmatch(r"that [a-z]+'s power", lowered))


def _parse_x_magnitude_body(body: str) -> Callable[["Game", Player, int], None] | None:
    """ "you gain X life and draw X cards" - the pre-"where X is" half of a
    magnitude-threaded consequence - split on the same bare " and " CR 608.2c
    treats as joining two instructions, with each half read by `_GAIN_X_LIFE_
    RE` or `_DRAW_X_CARDS_RE`. Fail-closed on any clause neither reads, the
    same discipline `_parse_player_clauses` already holds to for a plain
    (non-X) player clause.
    """
    parts = [part.strip() for part in re.split(r"\s+and\s+", body.strip()) if part.strip()]
    if not parts:
        return None
    steps: list[Callable[[Game, Player, int], None]] = []
    for part in parts:
        if _GAIN_X_LIFE_RE.fullmatch(part):
            steps.append(lambda game, player, amount: player.gain_life(amount))
        elif _DRAW_X_CARDS_RE.fullmatch(part):
            steps.append(lambda game, player, amount: game.draw_cards(player.username, amount))
        else:
            return None

    def run(game: "Game", player: Player, amount: int) -> None:
        for step in steps:
            step(game, player, amount)

    return run


#: The "if you do" consequence's signature once the optional cost has been
#: paid: the resolving object's controller, the sacrificed permanent's power
#: read before it left the battlefield (`None` only the way `Game.power_of`
#: is already `None` - an unresolved `*` characteristic-defining ability, not
#: a magnitude-free consequence, which never calls this argument at all), and
#: the source name for `Game.may`/`Game.ask` prompts a nested search still
#: needs.
_SacrificeConsequence = Callable[["Game", Player, int | None, str], None]


def _parse_sacrifice_consequence(consequence: str) -> _SacrificeConsequence | None:
    """The "If you do, `<consequence>`" half, read as either a magnitude-
    threaded pair of clauses ("you gain X life and draw X cards, where X is
    that creature's power", Disciple of Freyalise) or a plain mandatory
    search ("search your library for a colorless creature card, reveal it,
    put it into your hand, then shuffle", Sanctum of Ugin - mandatory because
    CR 118.12's own "you may" already gated the sacrifice; nothing asks a
    second "you may" for the consequence itself, which is why this reaches
    `_search_and_place_for` with `optional=False` rather than going through
    `_parse_search_clause`'s "you may " subject group).
    """
    consequence = consequence.strip().rstrip(".").strip()

    magnitude_match = re.fullmatch(
        r"(?P<body>.+?),\s*where X is (?P<expr>.+)", consequence, re.IGNORECASE | re.DOTALL
    )
    if magnitude_match is not None:
        if not _is_referent_power_expression(magnitude_match.group("expr")):
            return None
        run = _parse_x_magnitude_body(magnitude_match.group("body"))
        if run is None:
            return None

        def magnitude_effect(game: "Game", player: Player, power: int | None, source: str) -> None:
            run(game, player, max(power, 0) if power is not None else 0)

        return magnitude_effect

    search_match = _SEARCH_AND_PUT_RE.fullmatch(consequence)
    if search_match is not None:
        search_run = _search_and_place_for(search_match, optional=False)

        def search_effect(game: "Game", player: Player, power: int | None, source: str) -> None:
            search_run(game, player, source)

        return search_effect

    return None


class ConditionalClauseNotice(BaseModel):
    """One "you may sacrifice `<restriction>`. If you do, `<consequence>`."
    effect (CR 118.12) whose restriction or consequence this wave could not
    read.

    The same unreadable-is-not-the-same-as-no-effect record `TargetingNotice`,
    `InterveningIfNotice`, `ModeNotice`, `AnaphoricClauseNotice`, `ImprintNotice`,
    `LayerNotice`, and `CostModifierNotice` already keep for their own gaps -
    this shape's own defect, before this wave, was every card printing it
    (Disciple of Freyalise, Sanctum of Ugin, and Necrodominance's variable-life
    cousin) resolving with no effect and no trace of why.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    """The unreadable clause itself, as printed."""


def _unreadable_conditional_clause(text: str, *, for_spell: bool) -> str | None:
    """The "you may sacrifice ... If you do, ..." clause inside `text`, if it
    matches CR 118.12's shape but `_parse_conditional_sacrifice_clause` still
    cannot read its restriction or consequence - used only to decide whether
    a parse failure deserves a `ConditionalClauseNotice`, the same way
    `_unreadable_imprint_quality` decides for its own shape.
    """
    whole = _strip_non_effect_preamble(text).strip()
    match = _MAY_SACRIFICE_IF_YOU_DO_RE.fullmatch(whole)
    if match is None:
        return None
    if _parse_conditional_sacrifice_clause(text, for_spell=for_spell) is not None:
        return None
    return whole


def _parse_conditional_sacrifice_clause(text: str, *, for_spell: bool) -> TargetedClause | None:
    """ "You may sacrifice `<restriction>`. If you do, `<consequence>`." (CR
    118.12), read off the ability's own printed text so no registry row is
    needed - Disciple of Freyalise's and Sanctum of Ugin's own defect before
    this wave: both used to resolve doing nothing, with nothing anywhere
    recording that a choice had gone unoffered.

    The "you may" is `DecisionKind.MAY` with `affirmative_is_legal` set to
    whether a legal permanent to sacrifice actually exists right now (see
    `_sacrifice_restriction`) - the same shape `_parse_imprint_clause` and
    `may_pay_life` already use for their own CR 608.2d/CR 119.4 impossible-
    option cases. Once "yes" is chosen, CR 118.12 says the consequence runs
    regardless of anything downstream - CR 701.21a's sacrifice has no failure
    mode for a permanent the player controls, so "did you do it" is only ever
    "did you say yes", never a second check on the board afterward.
    """
    match = _MAY_SACRIFICE_IF_YOU_DO_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    restriction = _sacrifice_restriction(match.group("restriction"))
    if restriction is None:
        return None
    is_self, candidates_of = restriction
    consequence = _parse_sacrifice_consequence(match.group("consequence"))
    if consequence is None:
        return None
    prompt = f"sacrifice {match.group('restriction').strip()}"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source_id, source_name = _permanent_id_and_name(stack_object, for_spell=for_spell)
        candidates = candidates_of(game, player, source_id)
        decision = Decision(
            kind=DecisionKind.MAY,
            player=player.username,
            prompt=prompt,
            source=source_name,
            affirmative_is_legal=bool(candidates),
        )
        if not game.ask(decision):
            return
        if is_self:
            chosen = candidates[0]
        else:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player.username,
                    prompt="choose a permanent to sacrifice",
                    source=source_name,
                    amount=1,
                    cards=tuple(candidate.id for candidate in candidates),
                )
            )
            assert isinstance(chosen_ids, tuple)
            by_id = {candidate.id: candidate for candidate in candidates}
            chosen = by_id[chosen_ids[0]]
        power = game.power_of(chosen)
        game.sacrifice(chosen)
        consequence(game, player, power, source_name)

    return effect


# --------------------------------------------------------------------------
# Delayed-trigger clauses (CR 603.7)
# --------------------------------------------------------------------------
#
# "At the beginning of the next end step, return that card to the battlefield
# under its owner's control" is not something that happens *now* - it is an
# instruction to create a delayed triggered ability (`machines/delayed.py`)
# that fires later. Phelia, Exuberant Shepherd's attack trigger used to resolve
# and do nothing: its first clause ("exile up to one other target nonland
# permanent") is `_EXILE_TARGET_RE`'s ordinary shape, but its second and third
# clauses had no reader, so `parse_mixed_effect` correctly refused the *whole*
# ability (CR 608.2c has no notion of running half an instruction) - silently.
#
# The linkage this needs that no other clause pair does: clause two's "that
# card" is not a target of its own (CR 400.7's anaphora, same idea as
# `_ANAPHORIC_SUBJECT_RE`), it is whichever object clause one's own verb just
# moved - discovered only once clause one actually runs, at resolution. So the
# combined effect below runs clause one itself (rather than delegating to
# `exile_ability_targets`, which throws the moved object away) and closes over
# the result when it builds the `DelayedTrigger`.

#: The timing phrases this wave reads, mapped to the `Step` a `BEGINNING_OF_
#: STEP` event carries for them. CR 511.2: "abilities that trigger 'at end of
#: combat' trigger as the end of combat step begins" - the same event shape
#: every other "at the beginning of ..." trigger already uses, just a
#: different step. CR 513.2 (and its "likewise" for the upkeep) is why waiting
#: for the *next* occurrence is always correct with no extra bookkeeping: an
#: event already emitted for the current occurrence of a step never fires
#: `DelayedTrigger.matches` a second time, so a trigger created during that
#: step's own beginning is already waiting for the next turn's, not this
#: turn's - exactly what CR 513.2 asks for.
_DELAYED_TIMING_STEPS: dict[str, Step] = {
    "the beginning of the next end step": Step.END_STEP,
    "the beginning of the next turn's upkeep": Step.UPKEEP,
    "end of combat": Step.END_OF_COMBAT,
}

_DELAYED_TIMING_PATTERN = "|".join(re.escape(phrase) for phrase in _DELAYED_TIMING_STEPS)

#: "At <timing>, <verb>." - Phelia's own word order.
_DELAYED_TIMING_LEADING_RE = re.compile(
    rf"^at (?P<timing>{_DELAYED_TIMING_PATTERN}),\s*(?P<verb>.+)$", re.IGNORECASE
)
#: "<Verb> at <timing>." - Postmortem Lunge's, Nahiri's, Aether Membrane's,
#: Mishra's Bauble's, and dash's reminder text's word order.
_DELAYED_TIMING_TRAILING_RE = re.compile(
    rf"^(?P<verb>.+?)\s+at (?P<timing>{_DELAYED_TIMING_PATTERN})$", re.IGNORECASE
)


def _parse_delayed_timing_clause(clause: str) -> tuple[Step, str] | None:
    """Split `clause` into the step it waits for and the verb phrase left
    over, in whichever of the two word orders `_DELAYED_TIMING_STEPS` prints
    it in - or `None` if it names no timing phrase this wave reads at all."""
    clause = clause.strip().rstrip(".")
    match = _DELAYED_TIMING_LEADING_RE.fullmatch(clause) or _DELAYED_TIMING_TRAILING_RE.fullmatch(
        clause
    )
    if match is None:
        return None
    step = _DELAYED_TIMING_STEPS.get(match.group("timing").lower())
    if step is None:
        return None
    return step, match.group("verb").strip()


#: "look at the top card of target player's/your/their library" - Mishra's
#: Bauble's first clause, ahead of its own delayed-trigger second clause.
#: CR 701.20e: "looking at a card follows the same rules as revealing a card,
#: except that the card is shown only to the specified player" - purely
#: informational, so there is nothing for this engine's board state to do.
_LOOK_AT_TOP_CARD_RE = re.compile(
    r"^look at the top card of (?:target player's|your|their) library$", re.IGNORECASE
)


def _look_at_top_card(game: "Game", stack_object: "StackObject") -> None:
    """No-op (CR 701.20e): hidden information this engine does not model a
    player "seeing" beyond what `Game.find_by_id` already lets any test read
    directly. `Game.resolve_targets` still runs, so a target that is gone by
    resolution is refused the ordinary way (CR 608.2b) even though nothing
    here reads what came back."""
    game.resolve_targets(stack_object)


#: "return that card/it/that creature/that permanent to the battlefield under
#: its/their owner's control" - the blink idiom (Phelia, Blizzard Strix, Angel
#: of Condemnation, Astral Drift all print it verbatim).
_RETURN_TO_BATTLEFIELD_OWNER_RE = re.compile(
    r"^return (?:it|that card|that creature|that permanent) to the battlefield "
    r"under (?:its|their) owner'?s control$",
    re.IGNORECASE,
)

#: "draw a card" - Mishra's Bauble's second half, with no object at all.
_DRAW_A_CARD_RE = re.compile(r"^draw a card$", re.IGNORECASE)


# --------------------------------------------------------------------------
# Earthbend (CR 701.66a)
# --------------------------------------------------------------------------
#
# "Earthbend N" is a CR 701 keyword *action*, not a CR 702 keyword ability, so
# it is written out here rather than in `machines/keywords.py` - it is never
# the whole of an ability the way cycling or equip are; it is embedded in
# another ability's effect text (Badgermole Cub's "When this creature enters,
# earthbend 1."). `machines/keywords.executes` is still told about it, so the
# pool sweeper does not report it as silently ignored.
#
# Not keyed on reminder text: Bumi, Unleashed prints "earthbend 4." with no
# reminder at all, and this module's callers already strip reminder text
# before a clause ever reaches here.

#: "Earthbend N." - never printed with the word "target" (that is CR 701.66a's
#: own wording, not the card's); `targeting.profile_for_text` is taught the
#: keyword's implied target so this only has to read the number.
_EARTHBEND_RE = re.compile(r"^earthbend (?P<n>\d+)$", re.IGNORECASE)


def earthbend(
    game: "Game",
    land: CardState,
    amount: int,
    controller: str,
    source_id: UUID | None,
    source_name: str,
) -> None:
    """CR 701.66a: "Earthbend N" means "Target land you control becomes a 0/0
    land creature with haste in addition to its other types. Put N +1/+1
    counters on it. When that land dies or is put into exile, return it to
    the battlefield tapped under your control."

    Three simultaneous changes, all created now (CR 608.2c has no notion of
    running half an instruction) and all scoped to *this* incarnation of
    `land` (`layers.only_this_incarnation`) rather than its bare id:

    - Layer 4: the creature type is *added* (CR 205.1b's "in addition to its
      other types") with `layers.add_type` - never `layers.set_basic_land_type`,
      which is CR 305.7's "sets a land's subtype" path and would strip the
      land's own mana ability along with its old types.
    - Sublayer 7b: power and toughness are *set* to 0/0 (CR 613.4b) with
      `layers.set_power_toughness`. The `amount` +1/+1 counters that follow
      land in sublayer 7c (CR 613.4c) through `Game.add_counters` instead of a
      second continuous effect - `layers._counter_effects` already turns real
      counters into that sublayer's effect, and CR 613.4 fixes 7b-before-7c
      regardless of timestamp, so a freshly set 0/0 plus one counter is
      unconditionally a 1/1. CR 704.3/117.5 only check state-based actions
      when a player would receive priority, never mid-resolution, so the land
      is never briefly a legal-to-die 0/0 between the two.
    - Layer 6: haste, granted with the ordinary `layers.grant_ability`.

    `Duration.INDEFINITE` (CR 611.2a) is correct - earthbend states no
    end - and is exactly why the scoping matters: `ContinuousEffects.
    end_the_turn` never removes an `INDEFINITE` effect, so one scoped only to
    `land.id` would still match after CR 603.7's own delayed return sent this
    same id back as a plain, unanimated land (CR 400.7's "new object"),
    silently re-animating it for free and forever.

    The delayed return is created twice, once per half of "dies or is put
    into exile" - `TriggerEvent.DIES` and `TriggerEvent.LEAVES_BATTLEFIELD_
    TO_EXILE` are two different events, so CR 603.7a's one ability needs one
    `DelayedTrigger` per event it watches. Whichever fires first consumes its
    own one-shot `remaining` (CR 603.7b) and returns the land; the other is
    dropped by `_dismiss_other_earthbend_trigger` rather than left to spend
    itself uselessly (harmlessly, since its `expected_stamp` can never match
    again once the land has moved on - but tidiness, not correctness, is why
    it is dropped). Both watch `still_affects` at *resolution* (CR 603.7c),
    which is what stops a land that was, say, bounced to hand instead from
    being affected at all.
    """
    stamp = land.zone_change_stamp
    effects = game.continuous_effects
    for description, layer, sublayer, modification in (
        (
            f"earthbend: {land.name} becomes a land creature",
            Layer.TYPE,
            None,
            add_type(Type.CREATURE),
        ),
        (
            f"earthbend: {land.name} is 0/0",
            Layer.POWER_TOUGHNESS,
            Sublayer.SET,
            set_power_toughness(0, 0),
        ),
        (f"earthbend: {land.name} has haste", Layer.ABILITY, None, grant_ability("Haste")),
    ):
        effects.add(
            ContinuousEffect(
                description=description,
                layer=layer,
                sublayer=sublayer,
                timestamp=effects.tick(),
                duration=Duration.INDEFINITE,
                selector=only_this_incarnation(land, stamp),
                modification=modification,
            )
        )
    game.add_counters(land, Counter.PLUS_ONE, amount)

    siblings: list[DelayedTrigger] = []
    for event, zone in (
        (TriggerEvent.DIES, Zone.GRAVEYARD),
        (TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE, Zone.EXILE),
    ):
        siblings.append(
            game.create_delayed_trigger(
                DelayedTrigger(
                    text=(
                        "When that land dies or is put into exile, return it "
                        "to the battlefield tapped under your control."
                    ),
                    event=event,
                    controller=controller,
                    source_id=source_id,
                    source_name=source_name,
                    subject_id=land.id,
                    expected_zone=zone,
                    # No `expected_stamp` here, unlike the blink idiom's use of
                    # this same field: those triggers are created *after* the
                    # object has already arrived in `expected_zone`, so the
                    # stamp they capture is that arrival's own stamp, and it
                    # only changes if the object leaves and comes back before
                    # the trigger resolves (CR 603.7c's parenthetical). This
                    # trigger is created *before* the land has died or been
                    # exiled - CR 603.7a fires it the moment earthbend
                    # resolves - so `land.zone_change_stamp` right now is its
                    # *battlefield* incarnation's stamp, and CR 400.7 always
                    # reassigns a new one the instant it actually dies or is
                    # exiled. Capturing it here would make `still_affects`
                    # compare against a stamp the object can never wear again,
                    # so the return would never fire at all. `expected_zone`
                    # plus `subject_id` alone already give CR 603.7c's real
                    # guarantee for this shape: if something else moves the
                    # land out of that zone again first, `still_affects`
                    # correctly stops affecting it.
                    callback=_return_earthbent_land,
                )
            )
        )
    for trigger in siblings:
        trigger.sibling_ids = tuple(other.id for other in siblings if other is not trigger)


def _return_earthbent_land(game: "Game", ability: AbilityOnStack, trigger: DelayedTrigger) -> None:
    """CR 701.66a's own return: tapped, and under the earthbend ability's
    *controller* - not `delayed.return_subject_to_battlefield_under_owner`'s
    owner-and-untapped default, which is CR 610.3c's default for a blink
    effect that says nothing more specific. Earthbend overrides both halves
    of that default explicitly, so it needs its own callback rather than the
    shared one.
    """
    permanent = trigger.still_affects(game)
    _dismiss_other_earthbend_trigger(game, trigger)
    if permanent is None:
        return
    game.put_onto_battlefield(permanent, trigger.controller, tapped=True)


def _dismiss_other_earthbend_trigger(game: "Game", trigger: DelayedTrigger) -> None:
    """Drop the sibling delayed trigger for "dies **or** is put into exile"
    once either half has fired - CR 603.7a describes one ability watching for
    either event, and this engine represents that as two `DelayedTrigger`s
    sharing one subject because each watches one event. Not load-bearing for
    correctness (the sibling's `expected_stamp` can never match again once
    the land has moved on), only for not leaving a dead watcher behind.
    """
    game.delayed_triggers.triggers = [
        candidate
        for candidate in game.delayed_triggers.triggers
        if candidate.id not in trigger.sibling_ids
    ]


def _parse_earthbend_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Earthbend N." - the whole of an ability's effect text once its
    trigger condition ("When this creature enters, ") has been split off.

    Reads only the target the *ability* chose (CR 601.2c/603.3d already ran
    by the time this resolves, using the restriction `targeting.profile_for_
    text` supplies for any text containing the word "earthbend") - there is
    nothing left for this clause to parse out of the card's own words beyond
    the number.
    """
    if for_spell:
        return None  # no card in the pool prints earthbend on a spell.
    match = _EARTHBEND_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    amount = int(match.group("n"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        targets = [
            target for target in game.resolve_targets(ability) if isinstance(target, CardState)
        ]
        if not targets:
            return  # CR 608.2b: no legal target left, earthbend does nothing.
        earthbend(
            game, targets[0], amount, ability.controller, ability.source_id, ability.source_name
        )

    return effect


def _parse_delayed_single_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """A whole ability whose *only* clause is a delayed-trigger creation, with
    no antecedent clause of its own to supply "it": either there is no object
    at all (Mishra's Bauble's "draw a card"), or the object is the trigger's
    own event subject rather than anything targeted (Aether Membrane's "return
    that creature to its owner's hand at end of combat" - CR 509.1a's "the
    other creature in a blocking pair", read off `ability.event.related_id`
    the same way `damage_the_other_combatant` already does).

    Ability-only (`for_spell=False`): a spell has no `ability.event` to read a
    bare pronoun off, and neither shape appears on a spell in this pool.
    """
    if for_spell:
        return None
    timing = _parse_delayed_timing_clause(clause)
    if timing is None:
        return None
    step, verb = timing

    if _DRAW_A_CARD_RE.fullmatch(verb):

        def draw_effect(game: "Game", stack_object: "StackObject") -> None:
            ability = stack_object
            assert isinstance(ability, AbilityOnStack)
            game.create_delayed_trigger(
                DelayedTrigger(
                    text=clause,
                    event=TriggerEvent.BEGINNING_OF_STEP,
                    step=step,
                    controller=ability.controller,
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    callback=draw_a_card_for_controller,
                )
            )

        return draw_effect

    if _RETURN_TO_HAND_RE.fullmatch(verb):

        def return_to_hand_effect(game: "Game", stack_object: "StackObject") -> None:
            ability = stack_object
            assert isinstance(ability, AbilityOnStack)
            event = ability.event
            subject_id = event.related_id if event is not None else None
            if subject_id is None and event is not None:
                subject_id = event.subject_id
            if subject_id is None:
                return
            subject = game.find_by_id(subject_id)
            if not isinstance(subject, CardState):
                return
            game.create_delayed_trigger(
                DelayedTrigger(
                    text=clause,
                    event=TriggerEvent.BEGINNING_OF_STEP,
                    step=step,
                    controller=ability.controller,
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    subject_id=subject.id,
                    expected_zone=Zone.BATTLEFIELD,
                    expected_stamp=subject.zone_change_stamp,
                    callback=return_subject_to_hand,
                )
            )

        return return_to_hand_effect

    return None


#: "return it/that card/that creature/that permanent to its owner's/your/
#: their owner's/their hand" - Aether Membrane's own shape.
_RETURN_TO_HAND_RE = re.compile(
    r"^return (?:it|that card|that creature|that permanent) to "
    r"(?:its owner's|your|their owner's|their) hand$",
    re.IGNORECASE,
)

#: "if it entered under your control, put N +1/+1 counter(s) on <recipient>" -
#: Phelia's own rider, generalised: `<recipient>` is read and checked against
#: the *resolving* source's own name at run time (its short form, "Phelia",
#: included), never hardcoded, so this reads any card printing the same shape
#: rather than being one more name-keyed table row.
_RETURN_RIDER_COUNTER_RE = re.compile(
    r"^if it entered under your control, "
    r"put (?P<n>a|one|two|three|four|five) \+1/\+1 counters? on (?P<who>.+)$",
    re.IGNORECASE,
)

#: What the rider does once the delayed return has happened: `Callable[[Game,
#: the returned card, the creating ability's controller username, the
#: creating source's id, the creating source's name], None]`.
_ReturnRider = Callable[["Game", CardState, str, UUID | None, str], None]


def _parse_return_rider_clause(clause: str) -> _ReturnRider | None:
    """Phelia's third sentence: "If it entered under your control, put a
    +1/+1 counter on Phelia." Conditional on the delayed return itself (not on
    anything true when the outer ability resolved), so it has to run as part
    of the delayed trigger's own resolution, not the attack trigger's.
    """
    match = _RETURN_RIDER_COUNTER_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    amount = _count(match.group("n"))
    who = match.group("who").strip().lower()

    def rider(
        game: "Game",
        returned: CardState,
        controller: str,
        source_id: UUID | None,
        source_name: str,
    ) -> None:
        if returned.controller != controller:
            return  # "if it entered under your control"
        recipient = game.find_by_id(source_id) if source_id is not None else None
        if recipient is None or recipient.zone is not Zone.BATTLEFIELD:
            return  # the source is gone; CR 608.2b's outcome for no legal target
        short_name = source_name.split(",")[0].strip().lower()
        if who not in ("this creature", "this permanent", source_name.lower(), short_name):
            return
        game.add_counters(recipient, Counter.PLUS_ONE, amount)

    return rider


def _parse_delayed_blink_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """ "Exile up to one other target nonland permanent. At the beginning of
    the next end step, return that card to the battlefield under its owner's
    control[. If it entered under your control, put a +1/+1 counter on
    <recipient>.]" as one combined instruction (CR 608.2c) - two or three
    consecutive clauses starting at `index`, or `None` if `index` is not the
    start of this shape.

    The linkage: clause two's "that card" is CR 400.7's anaphora back to
    whatever clause one's own exile just moved, discovered only as clause one
    actually runs - so the combined effect below exiles the target itself
    (not `exile_ability_targets`, which has nowhere to hand the result back
    to) and closes over the exiled `CardState` when it builds the
    `DelayedTrigger`, the same way `_parse_anaphoric_clause_pair` closes over
    its own first clause's target.
    """
    exile_match = _EXILE_TARGET_RE.fullmatch(clauses[index])
    if exile_match is None:
        return None
    if not _targets_understood(
        exile_match.group("phrase"), count_agnostic=True, battlefield_only=False
    ):
        return None
    if index + 1 >= len(clauses):
        return None
    timing = _parse_delayed_timing_clause(clauses[index + 1])
    if timing is None:
        return None
    step, verb = timing
    if not _RETURN_TO_BATTLEFIELD_OWNER_RE.fullmatch(verb):
        return None

    consumed = 2
    rider: _ReturnRider | None = None
    if index + 2 < len(clauses):
        maybe_rider = _parse_return_rider_clause(clauses[index + 2])
        if maybe_rider is not None:
            rider = maybe_rider
            consumed = 3

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source_name = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = stack_object.id if for_spell else stack_object.source_id  # type: ignore[union-attr]
        controller = game.controller_of(stack_object).username
        targets = [
            target for target in game.resolve_targets(stack_object) if isinstance(target, CardState)
        ]
        if not targets:
            # CR 115.6: "up to one" chose zero, or CR 608.2b left nothing
            # legal - nothing to exile, so nothing to delay either.
            return
        target = targets[0]
        game.exile_permanent(target)
        if target.zone is not Zone.EXILE:
            # CR 111.8 refused it (a token that already left the battlefield
            # once) - no delayed return for something that never left.
            return

        if rider is None:
            callback = return_subject_to_battlefield_under_owner
        else:

            def callback(game: "Game", ability: AbilityOnStack, trigger: DelayedTrigger) -> None:
                returned = trigger.still_affects(game)
                if returned is None or returned.owner is None:
                    return
                game.put_onto_battlefield(returned, returned.owner, tapped=False)
                if returned.zone is Zone.BATTLEFIELD:
                    rider(game, returned, controller, source_id, source_name)

        game.create_delayed_trigger(
            DelayedTrigger(
                text=clauses[index + 1],
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=step,
                controller=controller,
                source_id=source_id,
                source_name=source_name,
                subject_id=target.id,
                expected_zone=Zone.EXILE,
                expected_stamp=target.zone_change_stamp,
                callback=callback,
            )
        )

    return consumed, effect


class DelayedClauseNotice(BaseModel):
    """One delayed-trigger clause (CR 603.7) whose timing this wave recognised
    - "at the beginning of the next end step", "at end of combat", "at the
    beginning of the next turn's upkeep" - but whose antecedent or verb it
    still could not read, so `parse_mixed_effect`/`parse_mixed_effect_for_
    spell` refused the whole ability rather than exiling (say) a permanent it
    could never guarantee returning. Postmortem Lunge's "Exile it at the
    beginning of the next end step" (the antecedent is a reanimation target
    with a variable mana value, not this wave's shape) and Nahiri, the
    Harbinger's -8 (the antecedent is a search result, not a target or an
    event subject) are both this: the same "unreadable is not the same as no
    effect" record `AnaphoricClauseNotice` and its siblings already keep.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str


def _unreadable_delayed_clause(text: str, *, for_spell: bool) -> str | None:
    """The first clause of `text` that names one of `_DELAYED_TIMING_STEPS`'s
    phrases, if `_prepare_effect_clauses` can split it out at all - used only
    to decide whether an effect this wave already failed to parse deserves a
    `DelayedClauseNotice`, not to parse it (the caller already tried and
    failed by the time this runs, exactly as `_unreadable_anaphoric_clause`'s
    caller does).
    """
    clauses = _prepare_effect_clauses(text)
    if clauses is None:
        return None
    for clause in clauses:
        if _parse_delayed_timing_clause(clause) is not None:
            return clause
    return None


class UnmodeledTriggerEffectNotice(BaseModel):
    """One triggered ability whose *condition* this engine reads and fires
    for real - CR 120.2a's "deals combat damage to a player"/"to an opponent",
    matched generically off any card's printed text by
    `machines/triggers.condition_matches` - but whose resolution clause names
    a mechanism this engine has nowhere to put: a per-instance, time-boxed
    permission to cast one specific exiled card (Ragavan's "until end of turn,
    you may cast that card" - the engine's whole cast-from-exile machinery in
    `machines/casting.py` is a static grant read off a card's own printed
    keyword, not a dynamic one handed out by a resolving ability), a choice
    between zero and many cards with no fixed count (Nashi's "you may put any
    number of ... into your hand" - `DecisionKind.CHOOSE_CARDS` in
    `machines/decisions.py` only knows how to ask for an exact `amount`, never
    "as many as you like"), or a target chosen at CR 603.3d announcement but
    restricted to what a upstream game *event* says rather than what the
    ability's own printed text says (Questing Beast's "target planeswalker
    **that player** controls", where "that player" is whoever the trigger's
    own combat damage was dealt to - `machines/targeting.profile_for_text`
    only ever reads a targeting restriction off the ability's static text).

    Each of these is a missing primitive, not a hard-to-parse sentence -
    building any of them is a feature this wave did not attempt - so the
    ability still triggers and goes on the stack (CR 603.3), and this is the
    "unreadable is not the same as no effect" record every other notice list
    in this module already keeps, rather than the ability silently doing
    nothing with no trace of why.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    """The unread portion of the ability's printed effect, or the whole of it
    when none of it runs."""


#: "until end of turn, you may cast that card"/"you may cast it"/"you may cast
#: those cards" - Ragavan, Nimble Pilferer's own third sentence, generalised
#: to whatever future card prints the same shape rather than matched by name.
#: A per-instance, time-boxed permission to cast a *specific* exiled object is
#: a missing primitive: `machines/casting.keyword_cast_options` only ever
#: reads a *static* grant off a card's own printed keyword line, read once per
#: printing, never a dynamic one a resolving ability hands out to one
#: particular card in exile.
_CAST_PERMISSION_CLAUSE_RE = re.compile(
    r"^(?:until end of turn, )?you may cast (?:it|that card|those cards)$",
    re.IGNORECASE,
)

#: "you may put any number of ... into your hand" - Nashi, Searcher in the
#: Dark's own second sentence. `DecisionKind.CHOOSE_CARDS` in
#: `machines/decisions.py` only ever asks for an exact `amount`
#: (`Game.ask`'s own check: "needs {amount} card(s) chosen"), never an
#: unbounded "as many as you like" - CR 608.2d's choice, with no decision
#: shape built for it yet.
_UNBOUNDED_HAND_CHOICE_RE = re.compile(
    r"^you may put any number of .+ into your hand$", re.IGNORECASE
)

#: "target <type> that player controls" - Questing Beast's own tail, where
#: "that player" is whoever the trigger's own combat damage was dealt to
#: (CR 120.2a), not the ability's controller. `machines/targeting.
#: profile_for_text` only ever reads a targeting restriction off the
#: ability's own static printed text - "you control"/"an opponent controls"
#: against the *controller* - and has no way to restrict a target by what an
#: upstream game event says instead.
_EVENT_PLAYER_TARGET_RE = re.compile(r"target \w+(?:\s\w+)? that player controls", re.IGNORECASE)


def _unreadable_cast_permission_clause(text: str, *, for_spell: bool) -> str | None:
    """The clause of `text` matching `_CAST_PERMISSION_CLAUSE_RE`, if any -
    used only to decide whether an effect this wave already failed to parse
    (via `parse_mixed_effect`) deserves an `UnmodeledTriggerEffectNotice`, the
    same "caller already tried and failed" contract every other `_unreadable_
    *_clause` function here keeps.

    Ability-only: nothing in the pool prints this shape on a spell, and a
    spell has no `AbilityOnStack` to have handed out a time-boxed permission
    in the first place.
    """
    if for_spell:
        return None
    clauses = _prepare_effect_clauses(text)
    if clauses is None:
        return None
    for clause in clauses:
        if _CAST_PERMISSION_CLAUSE_RE.fullmatch(clause.strip()):
            return clause
    return None


def _unreadable_unbounded_hand_choice_clause(text: str, *, for_spell: bool) -> str | None:
    """The clause of `text` matching `_UNBOUNDED_HAND_CHOICE_RE`, if any - see
    `_unreadable_cast_permission_clause`'s docstring for the "already tried
    and failed" contract this shares.
    """
    if for_spell:
        return None
    clauses = _prepare_effect_clauses(text)
    if clauses is None:
        return None
    for clause in clauses:
        if _UNBOUNDED_HAND_CHOICE_RE.fullmatch(clause.strip()):
            return clause
    return None


def _unreadable_event_player_target_clause(text: str, *, for_spell: bool) -> str | None:
    """The clause of `text` containing `_EVENT_PLAYER_TARGET_RE`'s shape, if
    any - see `_unreadable_cast_permission_clause`'s docstring for the
    "already tried and failed" contract this shares. A `search`, not a
    `fullmatch`: the restriction is a tail of a larger sentence ("it deals
    that much damage to target planeswalker that player controls"), not a
    clause of its own.
    """
    if for_spell:
        return None
    clauses = _prepare_effect_clauses(text)
    if clauses is None:
        return None
    for clause in clauses:
        if _EVENT_PLAYER_TARGET_RE.search(clause):
            return clause
    return None


#: "exile the top card of that player's library" - Ragavan, Nimble Pilferer's
#: own second clause. "That player" is CR 607.1's within-one-ability anaphora
#: back to a combat-damage-to-a-player trigger's own event (CR 120.2a) - the
#: player the damage landed on - not a target the ability ever announces
#: (CR 601.2c never runs for it), so this reads `ability.event.player` rather
#: than `stack_object.targets` the way `_LOOK_AT_TOP_CARD_RE`'s "target
#: player's library" reads an actual target.
_EXILE_TOP_OF_THAT_PLAYERS_LIBRARY_RE = re.compile(
    r"^exile the top card of that player's library$", re.IGNORECASE
)


def _parse_exile_that_players_library_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """Ability-only (`for_spell=False`): a spell has no `ability.event` to
    resolve "that player" against, and nothing in the pool prints this shape
    on a spell.
    """
    if for_spell:
        return None
    if not _EXILE_TOP_OF_THAT_PLAYERS_LIBRARY_RE.fullmatch(clause.strip()):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        event = ability.event
        username = event.player if event is not None else None
        if username is None:
            return
        player = game.player(username)
        if player.library:
            game.exile_permanent(player.library[0])

    return effect


def _parse_mixed_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """One clause of a mixed effect: the targeted shape first, then a token
    creation, then a search, then the imprint shape, then a delayed-trigger
    creation, then the plain player shape (CR 608.2c does not care which kind
    of instruction a card lists first, so no parser gets priority for any
    reason beyond "try this one, then the next").
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
    imprint = _parse_imprint_clause(clause, for_spell=for_spell)
    if imprint is not None:
        return imprint
    return_imprinted = _parse_return_imprinted_clause(clause, for_spell=for_spell)
    if return_imprinted is not None:
        return return_imprinted
    delayed = _parse_delayed_single_clause(clause, for_spell=for_spell)
    if delayed is not None:
        return delayed
    earthbend_clause = _parse_earthbend_clause(clause, for_spell=for_spell)
    if earthbend_clause is not None:
        return earthbend_clause
    exile_that_players_library = _parse_exile_that_players_library_clause(
        clause, for_spell=for_spell
    )
    if exile_that_players_library is not None:
        return exile_that_players_library
    if _LOOK_AT_TOP_CARD_RE.fullmatch(clause.strip()):
        return _look_at_top_card
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

    A run of two or more consecutive clauses is tried first, against several
    different shapes that are each one CR 608.2c instruction `split_effect_
    clauses` has cut apart on its own separators, not several independent
    ones: `_merge_continuous_pump_keyword_clauses` for "gets +N/+N and gains
    <keyword>" (Give In to Violence, CR 611.2), `_parse_anaphoric_clause_
    pair` for "destroy/exile target X. Its/that X's controller ..." (CR
    400.7), and `_parse_exile_then_return_clause_pair` for "exile target X,
    then return it to the battlefield ..." (Ephemerate). Only when a clause
    run opens none of these does it fall back to
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
        merged = _merge_prevent_damage_from_target_clauses(clauses, index)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _parse_delayed_blink_clauses(clauses, index, for_spell=for_spell)
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
            paired = _parse_exile_then_return_clause_pair(
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
    # Guttersnipe's "this creature deals 2 damage to each opponent" is not
    # entered here any more: `_DAMAGE_EACH_OPPONENT_RE` reads it off the
    # ability's own printed text, so `trigger_effect_for`'s fallback reaches
    # it. See `tests/scenarios/test_registry_is_minimal.py`.
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
    # Ragavan, Nimble Pilferer's, Nashi, Searcher in the Dark's, and Questing
    # Beast's combat-damage-to-a-player triggers are not entered here at all
    # (CR 120.2a): the condition - "whenever [this creature] deals combat
    # damage to a player"/"to an opponent" - is read generically off any
    # card's own printed text by `TriggerEvent.DEALS_DAMAGE` and
    # `machines/triggers.condition_matches`, and the *resolution* is now
    # `parse_mixed_effect`'s business too. "Create a Treasure token" is
    # `_parse_token_clause`'s shape; "exile the top card of that player's
    # library" is `_parse_exile_that_players_library_clause`'s, reading "that
    # player" off `ability.event.player` (CR 607.1's within-one-ability
    # anaphora back to the trigger's own object) rather than a target the
    # ability ever announces. Ragavan's third sentence - "Until end of turn,
    # you may cast that card" - is a missing primitive (a per-instance,
    # time-boxed cast permission), so `_unreadable_cast_permission_clause`
    # voids the *whole* ability with an `UnmodeledTriggerEffectNotice` rather
    # than run the first two sentences and drop the third (CR 608.2c has no
    # notion of running half an effect - see `_ability_effect_or_notice`).
    # Nashi's "you may put any number of ... into your hand" and Questing
    # Beast's "target planeswalker that player controls" are the same
    # missing-primitive shape, read by `_unreadable_unbounded_hand_choice_
    # clause` and `_unreadable_event_player_target_clause` respectively - see
    # `tests/scenarios/test_trigger_events.py` for the trigger firing and
    # `tests/scenarios/test_combat_damage_to_player_effects.py` for the
    # resolution.
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
