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
from ..models.card_state import (
    CardState,
    ChoiceKind,
    Counter,
    ExileAnnotation,
    ExileMarker,
    TargetRef,
)
from ..models.mana import ManaCost
from ..models.player import Player
from ..models.token import (
    MONSTER_ROLE,
    PREDEFINED,
    TokenDefinition,
    create_tokens,
    is_token,
    token_copy_of,
)
from ..models.zone import Zone
from . import combat as combat_rules
from .abilities import TriggerEvent, self_normalized_effect_text
from .casting import PlayAction, finish_suspend, remove_suspend_time_counter
from .casting_restrictions import parse_casting_rule_clause
from .decisions import Decision, DecisionKind
from .delayed import (
    DelayedEffect,
    DelayedTrigger,
    draw_a_card_for_controller,
    exile_subject_at_next_end_step,
    return_subject_to_battlefield_under_owner,
    return_subject_to_hand,
)
from .layers import (
    Characteristics,
    ContinuousEffect,
    ContinuousEffects,
    Duration,
    Layer,
    LayerContext,
    LayerNotice,
    Sublayer,
    add_subtype,
    add_type,
    count_card_types,
    creatures_controlled_by,
    creatures_controlled_by_opponents_of,
    every_creature,
    grant_ability,
    is_resolution_layer_effect_text,
    modify_power_toughness,
    only_this_incarnation,
    other_creatures_controlled_by,
    parsed_layer_effects,
    set_colors,
    set_power_toughness,
)
from .modes import Mode, is_modal_text, modal_profile, modal_profile_from_text, substitute_x
from .targeting import TargetRequirement, profile_for_text
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


def _deal_damage_equal_to_sacrificed_creature_power(game: "Game", spell: CardState) -> None:
    """Fling: "deals damage equal to the sacrificed creature's power to any
    target" (CR 119.3). The creature is long gone from the battlefield by
    resolution (CR 118.8a's additional cost is paid before the spell is even
    put on the stack), so its power has to be read off whichever card
    `Game.cast_record(spell).additional_cost_cards` says paid the additional
    cost, wherever paying it left that card - `Game.find_by_id` still finds
    it in the graveyard. A `None`/absent power (no card recorded, or the
    printed power is `*`, which this engine cannot resolve off a card no
    longer on the battlefield to compute) deals zero rather than guessing;
    CR 107.1b already floors damage at not-negative, so a negative printed
    power (there is no such thing in practice) would floor the same way.
    """
    record = game.cast_record(spell)
    power = 0
    if record.additional_cost_cards:
        sacrificed = game.find_by_id(record.additional_cost_cards[0])
        if sacrificed is not None and sacrificed.power is not None:
            power = max(sacrificed.power, 0)
    for target in game.resolve_targets(spell):
        game.deal_damage(target, power, source=spell)


def gain_life(amount: int) -> Effect:
    """The spell's controller gains `amount` life (CR 118.3)."""

    def effect(game: "Game", spell: CardState) -> None:
        game.controller_of(spell).gain_life(amount)

    return effect


def deal_divided_damage(total: int) -> Effect:
    """Damage "divided as you choose among one or two targets" (CR 601.2d).

    "The player announces the division. Each of these targets must receive at
    least one of whatever is being divided." W13 gives that announcement
    somewhere to live - `spell.division`, set by `Casting.announce_division`
    - and `_deal_divided_damage_shares` reads it when it is there. A caster
    who never announces one (every scenario that predates this mechanism)
    still gets the old fallback: split as evenly as it goes with the
    remainder on the first target, which for Electrolyze's 2 damage is the
    whole of it on one target, or 1 each on two either way.

    Only targets that are still legal on resolution are paid out (CR 608.2b),
    and the share the illegal ones would have had is simply not dealt: the
    division is locked in at announcement and cannot be re-divided.
    """

    def effect(game: "Game", spell: CardState) -> None:
        _deal_divided_damage_shares(game, spell, total)

    return effect


def _divided_damage_shares(total: int, chosen: int, announced: list[int] | None) -> list[int]:
    """The per-target shares a divided-damage effect pays out (CR 601.2d).

    `announced` is `spell.division` - the caster's real CR 601.2c/d
    announcement, recorded by `Casting.announce_division` and carried on the
    spell. When it is there and matches the target count, it is used exactly
    as announced. When it is not (no caller ever announced one - every
    scenario that predates this mechanism, and any that still does not use
    it), the total is split as evenly as it goes with the remainder on the
    first target, exactly `deal_divided_damage`'s original behaviour.
    """
    if announced is not None and len(announced) == chosen:
        return list(announced)
    shares = [total // chosen] * chosen
    for index in range(total % chosen):
        shares[index] += 1
    return shares


def _deal_divided_damage_shares(game: "Game", spell: CardState, total: int) -> None:
    """Pay out `total` damage divided among `spell.targets` (CR 601.2d, CR
    608.2b). Shared by `deal_divided_damage` (a fixed printed amount) and
    Shatterskull Smashing's own X-based, conditionally doubled version.
    """
    chosen = len(spell.targets)
    if chosen == 0 or total <= 0:
        return
    shares = _divided_damage_shares(total, chosen, spell.division)
    for reference, share in zip(spell.targets, shares, strict=True):
        target = game.legal_target(spell, reference)
        if target is not None and share > 0:
            game.deal_damage(target, share, source=spell)


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


def _counter_unless_pays_effect(amount: int) -> Effect:
    """ "Counter target spell unless its controller pays {N}." (CR 118.12a).

    Read as one CR 608.2c instruction, not two: the question is put to the
    *targeted* spell's controller (`Game.may_pay_mana`'s `player`, not this
    counterspell's caster), because CR 118.12a's "[a player] may [do
    something else]" names whoever the "unless" clause names. A target that
    has already left the stack (CR 608.2b: countered first, resolved, or
    otherwise gone) is simply skipped, the same as plain `counter_targets`.
    """

    def effect(game: "Game", spell: CardState) -> None:
        for reference in spell.targets:
            if not reference.is_card:
                continue
            target = next((item for item in game.stack if item.id == reference.card_id), None)
            if target is None:
                continue
            paid = game.may_pay_mana(target.controller, amount, source=spell.name)
            if not paid:
                game.counter(target)

    return effect


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

    Two shapes share this one function, told apart by whether the ability's
    *own printed text* names a target at all - not by whether `ability.targets`
    happens to be empty, which is ambiguous between them. When the ability
    names no target - Basking Rootwalla's "{1}{G}: This creature gets +2/+2
    until end of turn." - the affected object is the ability's own source.
    When it does - Karn, the Great Creator's "+1: ... up to one target
    noncreature artifact becomes an artifact creature ..." - the affected
    object is whatever it targeted, rechecked for legality now exactly as a
    spell's targets are (CR 608.2b): `game.resolve_card_targets` is the same
    call `create_continuous_effect` makes for a spell, so a loyalty ability
    reaches the layer engine through the ordinary activated-ability path
    rather than a planeswalker-specific one.

    `profile_for_text(ability.ability.text)` (the same call `Game.
    activate_ability` already made to check the announced targets' legality,
    CR 601.2c/602.2b) is what answers "does this ability's text require a
    target at all" - `ability.targets` being empty cannot answer that on its
    own, because CR 115.6 makes "up to one target ..." legally choosing zero a
    *different reason* for the same empty list. Reported defect: Karn's +1,
    activated with zero targets chosen (CR 115.6), used to fall through to
    `[source]` here and animate **Karn himself** into a 4/4 - wrong twice
    over, since a legendary planeswalker was never a legal "target noncreature
    artifact" to begin with (CR 601.2c) and CR 115.6's zero-targets case is
    required to leave the ability targeted at nothing, not silently
    redirected to its own source (CR 608.2, no target chosen affects nothing).
    "Up to one" legally choosing zero, or every chosen target having since
    become illegal (CR 608.2b), both leave `targets` empty and the ability
    resolves doing nothing - never a fallback to `source`.
    """
    source = ability.source(game)
    if source is None or source.zone is not Zone.BATTLEFIELD:
        return
    profile = profile_for_text(ability.ability.text)
    requires_target = profile.understood and bool(profile.requirements)
    targets = game.resolve_card_targets(ability) if requires_target else [source]
    if not targets:
        return
    continuous_effects(game).create(
        source,
        targets=targets,
        context=layer_context_for(game, game.controller_of(ability)),
    )


#: "Discard a card: This creature gets +1/+1 and becomes the color of your
#: choice until end of turn." (Wild Mongrel) and "{T}: Target creature you
#: control gains protection from the color of your choice until end of turn."
#: (Mother of Runes) both name a colour CR 608.2d leaves to the resolving
#: ability's controller, not the printed text - `parsed_layer_effects`' own
#: `LAYER_EFFECTS`/text-driven builders have no channel for a choice made at
#: resolution, so these two are built by hand through `ContinuousEffects.add`
#: (the escape hatch its own docstring names for "a caller that is not going
#: through the registry") rather than routed through `create_continuous_
#: effect_of_ability`.
_PUMP_AND_BECOMES_CHOSEN_COLOR_RE = re.compile(
    r"^this creature gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) and becomes the color of "
    r"your choice until end of turn\.?$",
    re.IGNORECASE,
)
_COLOR_LETTERS: tuple[str, ...] = ("W", "U", "B", "R", "G")


def _choose_a_color(game: "Game", player: Player, source_name: str, prompt: str) -> Color:
    """CR 608.2d's "of your choice", asked with `DecisionKind.CHOOSE_A_
    QUALITY` narrowed to CR 105's five colours - the same kind and the same
    narrowing `_parse_destroy_each_then_add_mana_per_destroyed` already uses
    for Culling Ritual's own per-unit colour choice.
    """
    decision = Decision(
        kind=DecisionKind.CHOOSE_A_QUALITY,
        player=player.username,
        prompt=prompt,
        source=source_name,
        options=_COLOR_LETTERS,
    )
    value = game.ask(decision)
    assert isinstance(value, str)
    return Color(value)


def _parse_pump_and_becomes_chosen_color_clause(text: str) -> AbilityEffect | None:
    """Wild Mongrel's own shape - see `_PUMP_AND_BECOMES_CHOSEN_COLOR_RE`.

    CR 613.1e is layer 5, colour-changing; the pump is layer 7c (CR 613.4c).
    Both are timestamped and stored as one "until end of turn" batch
    (CR 611.2a), same as any other resolving ability's continuous effect,
    just built directly rather than parsed a second time off printed text.
    """
    match = _PUMP_AND_BECOMES_CHOSEN_COLOR_RE.fullmatch(text.strip())
    if match is None:
        return None
    power = int(match.group("power"))
    toughness = int(match.group("toughness"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        controller = game.controller_of(ability)
        color = _choose_a_color(game, controller, source.name, f"choose a color for {source.name}")
        store = continuous_effects(game)
        timestamp = store.tick()
        store.add(
            ContinuousEffect(
                description=f"{source.name}: gets {power:+d}/{toughness:+d}",
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=timestamp,
                duration=Duration.UNTIL_END_OF_TURN,
                selector=_selects_id(source.id),
                modification=modify_power_toughness(power, toughness),
            )
        )
        store.add(
            ContinuousEffect(
                description=f"{source.name}: becomes {color.value}",
                layer=Layer.COLOR,
                timestamp=timestamp,
                duration=Duration.UNTIL_END_OF_TURN,
                selector=_selects_id(source.id),
                modification=set_colors(color),
            )
        )

    return effect


#: "Target creature you control gains protection from the color of your
#: choice until end of turn." (Mother of Runes). The phrase itself is checked
#: through `_targets_understood` the same as every other targeted clause;
#: `_MOTHER_OF_RUNES_PROTECTION_RE` only reads past "target creature you
#: control" to confirm the rest is this exact chosen-colour protection shape.
_PROTECTION_FROM_CHOSEN_COLOR_RE = re.compile(
    r"^(?P<phrase>target .+) gains protection from the color of your choice "
    r"until end of turn\.?$",
    re.IGNORECASE,
)


def _selects_id(card_id: UUID) -> Callable[[Characteristics, object], bool]:
    """One permanent, by id - the hand-built twin of `machines.layers`'s own
    private `_only`, needed here because that helper is not exported and this
    module builds `ContinuousEffect`s outside the text-driven registry.
    """

    def selector(chars: Characteristics, board: object) -> bool:
        return chars.card_id == card_id

    return selector


def _parse_protection_from_chosen_color_clause(text: str) -> AbilityEffect | None:
    """Mother of Runes' own shape - see `_PROTECTION_FROM_CHOSEN_COLOR_RE`.

    CR 702.16a: "Protection is a static ability, written 'Protection from
    [quality].'" Granting one line of that text in layer 6 (CR 613.1f) is
    exactly what `machines/layers._indefinite_keyword_grant_builder` already
    does for Akroma's Memorial's *un*-chosen "protection from black and from
    red" - this is the same `grant_ability("Protection from <color>")` shape,
    just aimed at whichever target was chosen and whichever colour the
    activating player names, so it is built by hand rather than read off
    static printed text a second time. `docs/engine-coverage.md` already
    records that a *granted* colour quality is read on the damage side
    (`Game._effective_protection_qualities`, consulted by both `protection_
    from_damage` and `protection_refusal`) but not yet on the targeting side
    for a card-type quality's own reason - unrelated to this card, and not
    widened here.
    """
    match = _PROTECTION_FROM_CHOSEN_COLOR_RE.fullmatch(text.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=False):
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        targets = [
            target
            for target in game.resolve_targets(ability)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        target = targets[0]
        source = ability.source(game)
        source_name = source.name if source is not None else ability.source_name
        controller = game.controller_of(ability)
        color = _choose_a_color(
            game, controller, source_name, f"choose a color for {source_name}'s protection"
        )
        store = continuous_effects(game)
        store.add(
            ContinuousEffect(
                description=f"{source_name}: {target.name} has protection from {color.value}",
                layer=Layer.ABILITY,
                timestamp=store.tick(),
                duration=Duration.UNTIL_END_OF_TURN,
                selector=_selects_id(target.id),
                modification=grant_ability(f"Protection from {_COLOR_NAME[color]}"),
            )
        )

    return effect


_COLOR_NAME: dict[Color, str] = {
    Color.WHITE: "white",
    Color.BLUE: "blue",
    Color.BLACK: "black",
    Color.RED: "red",
    Color.GREEN: "green",
}


# --------------------------------------------------------------------------
# A shared count expression: "the number of <type> you control" / "... cards
# in your graveyard" (CR 205.2a's card types)
# --------------------------------------------------------------------------
#
# Several cards define a variable magnitude this way - Craterhoof Behemoth's
# own pump ("where X is the number of creatures you control") and Grist, the
# Hunger Tide's -5 ("equal to the number of creature cards in your
# graveyard") are the two in this wave's pool - and each used to need its own
# one-off reader (`_read_referent_power_expression`'s "its power",
# `_parse_mass_mv_rhs`'s counters-on-self, `LayerContext.graveyard_of`'s own
# graveyard slice). `count_expression` is the shared one: given the phrase
# after "the number of", it returns a function of `(game, controller)` - not
# a value - because CR 611.2c only fixes the *result* at the moment a caller
# actually evaluates it, not the expression itself; Craterhoof's own
# docstring on `_run_mass_pump` is where that one evaluation happens.
_COUNT_YOU_CONTROL_RE = re.compile(
    r"^(?:the )?number of (?P<qualifier>[a-z]+) you control$", re.IGNORECASE
)
_COUNT_CARDS_IN_YOUR_GRAVEYARD_RE = re.compile(
    r"^(?:the )?number of (?P<qualifier>[a-z]+) cards? in your graveyard$", re.IGNORECASE
)


def _singular_card_type(word: str) -> Type | None:
    """ "creatures" / "creature" -> `Type.CREATURE` (CR 205.2a), or `None` for
    anything not one of the fifteen printed card types - a coloured, named, or
    compound qualifier ("green creatures", "Human creatures") is deliberately
    left unread rather than guessed at.
    """
    singular = word[:-1] if word.lower().endswith("s") else word
    try:
        return Type(singular.lower())
    except ValueError:
        return None


def count_expression(phrase: str) -> Callable[["Game", str], int] | None:
    """Parse "the number of <type>[s] you control" or "... card(s) in your
    graveyard" into `(game, controller) -> int`, or `None` if `phrase` is not
    one of those two shapes.

    "You control" is read off the *computed* board (CR 613.5) - a creature
    that only became one through a continuous effect still counts, the same
    correction this wave's Ajani/Leyline reading of "each Cat you control"
    needs (CR 613.4, CR 205.3). "In your graveyard" is a zone question, not a
    layers one, so it reads `CardState.types` directly (CR 205.2a) - already
    the front-face-safe read `Card.types` gives a double-faced card outside
    the battlefield, per `models/card_state.py`'s `types` property.

    The returned function re-reads the board or graveyard every time it is
    called; it is the caller's job to call it exactly once, at the moment
    CR 611.2c fixes the magnitude, and keep the resulting `int` rather than
    the function itself.
    """
    stripped = phrase.strip().rstrip(".")
    if match := _COUNT_YOU_CONTROL_RE.fullmatch(stripped):
        card_type = _singular_card_type(match.group("qualifier"))
        if card_type is None:
            return None

        def count_on_board(game: "Game", controller: str) -> int:
            board = game.computed_board()
            return sum(
                1
                for permanent in game.battlefield
                if board.of(permanent).controller == controller
                and card_type in board.of(permanent).types
            )

        return count_on_board

    if match := _COUNT_CARDS_IN_YOUR_GRAVEYARD_RE.fullmatch(stripped):
        card_type = _singular_card_type(match.group("qualifier"))
        if card_type is None:
            return None

        def count_in_graveyard(game: "Game", controller: str) -> int:
            return sum(1 for state in game.player(controller).graveyard if card_type in state.types)

        return count_in_graveyard

    return None


#: "your devotion to <color>" (CR 700.5) - Gray Merchant of Asphodel's own
#: magnitude. Read separately from `count_expression`'s "number of <type>
#: you control"/"<type> cards in your graveyard" family above: a genuinely
#: different expression shape (a color, not a card type; every permanent's
#: mana cost, not a filtered count of permanents), not a wider qualifier
#: grammar bolted onto that one.
_DEVOTION_RE = re.compile(
    r"^your devotion to (?P<color>white|blue|black|red|green)$", re.IGNORECASE
)
#: CR 105.1's five colors, spelled the way "your devotion to `<color>`" prints
#: them, to `Color`'s own single-letter enum value.
_COLOR_WORD_TO_COLOR: dict[str, Color] = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}


def _devotion_count(phrase: str) -> Callable[["Game", str], int] | None:
    """ "your devotion to `<color>`" -> `(game, controller) -> int` (CR 700.5):
    the number of mana symbols of that color among the mana costs of
    permanents `controller` controls.

    CR 107.4e: "A hybrid mana symbol is also a colored mana symbol" of each
    color it carries, and `ManaSymbol.colors` (`models/mana.py`) already
    carries every symbol kind's colors uniformly - plain colored, hybrid,
    monocolored hybrid, and Phyrexian alike - so this reads that field
    directly rather than special-casing hybrid or Phyrexian mana itself.

    CR 700.5a's "face-down spells and permanents are considered to lack a
    mana cost" is not read here: nothing in the pool needs a face-down
    permanent's devotion, and `CardState.mana_cost` (already up-face-aware,
    per `models/card_state.py`) is what this reads instead.
    """
    match = _DEVOTION_RE.fullmatch(phrase.strip().rstrip("."))
    if match is None:
        return None
    color = _COLOR_WORD_TO_COLOR[match.group("color").lower()]

    def count_devotion(game: "Game", controller: str) -> int:
        total = 0
        for permanent in game.permanents_controlled_by(controller):
            cost = permanent.mana_cost
            if not cost:
                continue
            for symbol in ManaCost.parse(cost).symbols:
                if color in symbol.colors:
                    total += 1
        return total

    return count_devotion


#: "each opponent loses X life, where X is your devotion to `<color>`." -
#: Gray Merchant of Asphodel's and Erebos, God of the Dead's shared "devotion
#: drain" template. Distinct from `_EACH_OPPONENT_LOSES_LIFE_EQUAL_TO_RE`'s
#: "loses life equal to `<expr>`" shape just above (Grist's own, with no X in
#: it at all) - this one names X explicitly and then defines it separately.
_OPPONENT_LOSES_X_LIFE_WHERE_X_IS_RE = re.compile(
    r"^each opponent loses x life, where x is (?P<expr>.+?)\.?$", re.IGNORECASE
)
#: "You gain life equal to the life lost this way." - the paired second
#: sentence, CR 119.3's *actual* amount lost (after any floor or prevention),
#: not a second evaluation of the first sentence's X.
_GAIN_LIFE_EQUAL_TO_LIFE_LOST_RE = re.compile(
    r"^you gain life equal to the life lost this way$", re.IGNORECASE
)


def _parse_devotion_drain_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Gray Merchant of Asphodel's whole paragraph: "each opponent loses X
    life, where X is your devotion to black. You gain life equal to the life
    lost this way." Read as one CR 608.2c instruction pair - the life gained
    is what each opponent's `Player.lose_life` actually took off, summed
    across every opponent, not a recomputed devotion total, so this evaluates
    devotion once and then measures the real life-total delta.
    """
    if index + 1 >= len(clauses):
        return None
    first_match = _OPPONENT_LOSES_X_LIFE_WHERE_X_IS_RE.fullmatch(clauses[index].strip())
    if first_match is None:
        return None
    counter = _devotion_count(first_match.group("expr"))
    if counter is None:
        return None
    if _GAIN_LIFE_EQUAL_TO_LIFE_LOST_RE.fullmatch(clauses[index + 1].strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        amount = counter(game, controller.username)
        if amount <= 0:
            return
        total_lost = 0
        for opponent in _opponents(game, controller.username):
            before = opponent.life
            opponent.lose_life(amount)
            total_lost += before - opponent.life
        if total_lost > 0:
            controller.gain_life(total_lost)

    return 2, effect


#: "Scry N." - the default half of Forsaken Crossroads' own paragraph, read
#: with the same `_SCRY_RE` `parse_clause_effect` already uses for a plain
#: "scry N" clause elsewhere, so a future card sharing this shape but a
#: different N still reads.
_SCRY_N_ONLY_RE = re.compile(r"^scry (?P<n>\d+)$", re.IGNORECASE)
#: "If you weren't the starting player, you may untap `<name>` instead."
#: (Forsaken Crossroads) - CR 103.8's starting player, and CR 608.2d's "you
#: may" over what the previous clause would otherwise do.
_IF_NOT_STARTING_PLAYER_MAY_UNTAP_INSTEAD_RE = re.compile(
    r"^if you weren'?t the starting player, you may untap (?P<name>[^.]+) instead$",
    re.IGNORECASE,
)


def _parse_scry_or_untap_if_not_starting_player_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Forsaken Crossroads' whole trigger: "Scry 1. If you weren't the
    starting player, you may untap Forsaken Crossroads instead." Read as one
    CR 608.2c instruction, not two independent ones: "instead" makes the
    second sentence's "you may untap" a substitute for the first sentence's
    scry, not an addition to it, so whether the scry happens at all depends
    on the answer to a question the first clause alone never asks.

    CR 103.8: "The starting player takes their first turn" - `TurnMachine.
    starting_player` is `players[0]`, fixed for the whole game. A player who
    was not dealt that seat (CR 103.4's "on the draw") is who this offers the
    substitution to; the starting player never sees the choice at all and
    simply scries.

    Ability-only (`for_spell=False`): nothing in the pool prints this shape
    on a spell, and `AbilityOnStack.source` is what finds the land to untap.
    """
    if for_spell or index + 1 >= len(clauses):
        return None
    scry_match = _SCRY_N_ONLY_RE.fullmatch(clauses[index].strip())
    if scry_match is None:
        return None
    count = int(scry_match.group("n"))
    untap_match = _IF_NOT_STARTING_PLAYER_MAY_UNTAP_INSTEAD_RE.fullmatch(clauses[index + 1].strip())
    if untap_match is None:
        return None
    named = untap_match.group("name").strip()

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        controller = game.controller_of(ability)
        source = ability.source(game)
        eligible = (
            source is not None
            and source.zone is Zone.BATTLEFIELD
            and named.lower() in (source.name or "").lower()
            and controller.username != game.turn.starting_player
        )
        if eligible:
            assert source is not None
            decision = game.ask(
                Decision(
                    kind=DecisionKind.MAY,
                    player=controller.username,
                    prompt=f"untap {source.name} instead of scrying",
                    source=ability.source_name,
                    affirmative_is_legal=True,
                )
            )
            if decision:
                # CR 701.43b's exert never applies to an effect's own untap,
                # only to the untap step itself - `Player.untap` is the one
                # normal turn-based-action caller that leaves `exert_applies`
                # at its default `True`.
                source.untap(exert_applies=False)
                return
        game.scry(controller, count, source=ability.source_name)

    return 2, effect


# --------------------------------------------------------------------------
# P5: a duration-bearing team-wide pump with no target, magnitude fixed at
# resolution (CR 611.2, CR 611.2c)
# --------------------------------------------------------------------------
#
# `create_continuous_effect`/`create_continuous_effect_of_ability` above
# default an untargeted ability's affected object to its own source ("this
# creature gets +2/+2"), which is right for Basking Rootwalla and wrong for
# "creatures you control get +N/+N until end of turn." - Violent Outburst's
# own pump, and Craterhoof Behemoth's "creatures you control gain trample and
# get +X/+X until end of turn, where X is the number of creatures you
# control." `docs/engine-coverage.md` used to carry this row as a recorded
# gap ("the actual continuous effect for a team-wide temporary pump is still
# not built"); `machines/layers.py`'s `_MASS_PUMP_UNTIL_EOT_RE`/
# `_mass_pump_until_eot_builder` build the effect once handed the concrete,
# already-resolved group, and everything below computes that group and (when
# the card prints one) the "where X is ..." magnitude.
_MASS_SUBJECT_RE = re.compile(
    r"^(?:other )?creatures (?:you control|your opponents control)\b", re.IGNORECASE
)
#: History of Benalia's own chapter III: "Knights you control get +2/+1
#: until end of turn." - CR 205.3m's bare creature-type word standing in for
#: the elided "creatures", the mass-pump twin of `machines/targeting.
#: _is_bare_subtype_word`'s reading of the same shape for a *target*.
#: Deliberately case-sensitive (no `re.IGNORECASE`) rather than folded into
#: `_MASS_SUBJECT_RE` above: Oracle text only ever capitalizes a subtype, so
#: requiring the capital is what tells a genuine "Knights you control" apart
#: from a sentence merely starting with some other lowercase-elsewhere noun -
#: `_MASS_SUBJECT_RE`'s own literal "creatures" is tried first and always
#: wins when it matches, so this never intercepts "Creatures you control ..."
#: (Violent Outburst), capitalized only because it opens the sentence.
_MASS_SUBTYPE_SUBJECT_RE = re.compile(
    r"^(?![Cc]reatures?\b)(?P<subtype>[A-Z][a-z]+) (?P<whose>you control|your opponents control)\b"
)
#: The trailing computed-magnitude clause - "..., where X is <expr>." - split
#: off so the rest of the sentence can be handed to `machines/layers.py`'s
#: parser once "X" is replaced by a literal number.
_WHERE_X_IS_RE = re.compile(r",?\s*where x is (?P<expr>.+?)\.?$", re.IGNORECASE)


def _mass_creature_group_targets(
    game: "Game", controller: str, source_id: UUID, text: str
) -> list[CardState] | None:
    """The concrete creatures a mass, untargeted "creatures you control" /
    "other creatures you control" / "creatures your opponents control"
    resolution effect affects, fixed **now** (CR 611.2c: "the set of objects
    it affects is determined when that continuous effect begins ... any
    objects that come under [that] control later aren't affected") rather
    than a live `Selector` that would keep re-including whoever is on the
    battlefield the next time CR 613.5 recomputes it - which is exactly right
    for a *static* ability's own anthem (`_anthem_builder`) and exactly wrong
    here. `None` if `text`'s subject is none of the three - the caller's
    ordinary target resolution stays in charge for everything else.
    """
    subtype_match = _MASS_SUBTYPE_SUBJECT_RE.match(text.strip())
    if subtype_match is not None:
        # History of Benalia's "Knights you control" - CR 205.3m's subtype
        # narrows the ordinary "creatures [you|opponents] control" selectors
        # above by one more check, added on top rather than a fifth selector
        # function in `machines/layers.py` since the subtype word is only
        # known here, off the literal sentence text.
        # "Knights" (CR 205.3m plurals with a bare "s") against the subtype as
        # it is actually stored, singular - `board.of(...).subtypes` holds
        # "Knight", never "Knights".
        subtype = subtype_match.group("subtype").lower().removesuffix("s")
        base_selector = (
            creatures_controlled_by(controller)
            if subtype_match.group("whose") == "you control"
            else creatures_controlled_by_opponents_of(controller)
        )
        board = game.computed_board()
        return [
            permanent
            for permanent in game.battlefield
            if base_selector(board.of(permanent), board.characteristics)
            and any(word.lower() == subtype for word in board.of(permanent).subtypes)
        ]
    opening = text.strip().lower()
    if opening.startswith("other creatures you control"):
        selector = other_creatures_controlled_by(source_id, controller)
    elif opening.startswith("creatures you control"):
        selector = creatures_controlled_by(controller)
    elif opening.startswith("creatures your opponents control"):
        selector = creatures_controlled_by_opponents_of(controller)
    elif opening.startswith("all creatures"):
        # Toxic Deluge's own "All creatures get -X/-X until end of turn." -
        # no controller restriction at all, unlike the three shapes above.
        selector = every_creature
    else:
        return None
    board = game.computed_board()
    return [
        permanent
        for permanent in game.battlefield
        if selector(board.of(permanent), board.characteristics)
    ]


def _parse_mass_pump_clause(
    effect_text: str,
) -> tuple[str, Callable[["Game", str], int] | None] | None:
    """The mass-pump sentence, as a template with a literal "+N/+N" already in
    it (`magnitude_expr` is `None`) or with "+X/+X" still in it and a
    `count_expression` to resolve it later (`magnitude_expr` is not `None`) -
    or `None` if `effect_text` is not this shape at all, or names a "where X
    is ..." expression `count_expression` cannot read.

    Requires an explicit "until end of turn": without it, "Creatures you
    control get +1/+1." is Glorious Anthem's own CR 611.3 anthem - a
    permanent's forever-lasting static ability, not a CR 611.2 one-shot
    effect - and `Game.resolve_top` calls `effect_for` for *every* resolving
    spell, permanents included, so returning an effect here for that shape
    would store a second, durational copy of the same anthem on top of the
    one `effects_for`'s per-permanent battlefield sweep already reapplies on
    its own every time the board is computed (CR 613.5), doubling the bonus -
    exactly the trap `is_resolution_layer_effect_text`'s own docstring
    documents for why it excludes the anthem shape.
    """
    text = effect_text.strip()
    if _MASS_SUBJECT_RE.match(text) is None and _MASS_SUBTYPE_SUBJECT_RE.match(text) is None:
        return None
    if Duration.UNTIL_END_OF_TURN not in text.lower():
        return None
    where_match = _WHERE_X_IS_RE.search(text)
    if where_match is None:
        return text, None
    magnitude_expr = count_expression(where_match.group("expr"))
    if magnitude_expr is None:
        return None
    template = text[: where_match.start()].rstrip(", ").rstrip(".") + "."
    if "+x/+x" not in template.lower():
        return None
    return template, magnitude_expr


def _run_mass_pump(
    game: "Game",
    source: CardState,
    controller: str,
    template: str,
    magnitude_expr: Callable[["Game", str], int] | None,
) -> None:
    """Resolve one mass-pump clause: substitute its magnitude (if it has one),
    fix the group of creatures it affects, and hand the literal sentence to
    `machines/layers.py`'s own parser - the same `parsed_layer_effects` every
    other continuous effect in this file goes through, not a second
    ContinuousEffect-building path (Craterhoof's trample grant still lives or
    dies by `_KNOWN_KEYWORDS`'s whitelist there).

    Trap: the magnitude is read **once**, right here, into a plain `int` -
    never carried forward as `magnitude_expr` itself - so a creature that
    enters after this resolves cannot retroactively grow Craterhoof's own
    pump the way `set_power_toughness_to_mana_value`'s live re-read
    deliberately does for Karn's ability (CR 611.2c fixes both the group and
    the number the moment the effect begins).
    """
    literal = template
    if magnitude_expr is not None:
        magnitude = magnitude_expr(game, controller)
        literal = re.sub(r"\+x/\+x", f"{magnitude:+d}/{magnitude:+d}", literal, flags=re.IGNORECASE)
    targets = _mass_creature_group_targets(game, controller, source.id, literal)
    if not targets:
        return
    # `targets` is already the concrete, subtype-filtered group (CR 611.2c) -
    # `machines/layers.py`'s own parser only needs to recognise the *shape*
    # of what follows ("get +N/+N ... until end of turn"), which is templated
    # on the literal "creatures" subject. A bare CR 205.3m subtype standing
    # in for it (History of Benalia's "Knights you control") is rewritten to
    # that literal subject here, once, rather than teaching `machines/
    # layers.py` a second subject grammar it would then have to keep in step
    # with `_MASS_SUBTYPE_SUBJECT_RE` above.
    subtype_match = _MASS_SUBTYPE_SUBJECT_RE.match(literal.strip())
    parseable = (
        "creatures " + literal.strip()[subtype_match.start("whose") :]
        if subtype_match is not None
        else literal
    )
    builder = parsed_layer_effects(parseable)
    if builder is None:
        # A keyword outside `_KNOWN_KEYWORDS`'s whitelist, or some other shape
        # this wave's parser cannot read - fail closed rather than silently
        # doing nothing (the same "unreadable is not the same as no effect"
        # rule every other `LayerNotice` site in this file already keeps).
        continuous_effects(game).layer_notices.append(
            LayerNotice(source_id=source.id, source_name=source.name, text=literal)
        )
        return
    store = continuous_effects(game)
    timestamp = store.tick()
    context = layer_context_for(game, game.player(controller))
    for built in builder(source, timestamp, targets, context):
        if built.holds:
            store.add(built)


def _mass_pump_ability_effect(effect_text: str) -> AbilityEffect | None:
    """Craterhoof Behemoth's own ETB shape: a mass pump read whole off a
    resolving *ability's* text, with `ability.controller` and its own source.
    """
    parsed = _parse_mass_pump_clause(effect_text)
    if parsed is None:
        return None
    template, magnitude_expr = parsed

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None:
            return
        _run_mass_pump(game, source, ability.controller, template, magnitude_expr)

    return effect


def _mass_pump_spell_effect(effect_text: str) -> Effect | None:
    """Violent Outburst's own pump line, the spell-side twin of
    `_mass_pump_ability_effect` above - its cascade half is unaffected (CR
    702.85a's exile-hit-free-cast pipeline reads no part of this sentence).
    """
    parsed = _parse_mass_pump_clause(effect_text)
    if parsed is None:
        return None
    template, magnitude_expr = parsed

    def effect(game: "Game", spell: CardState) -> None:
        _run_mass_pump(game, spell, game.controller_of(spell).username, template, magnitude_expr)

    return effect


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


#: "Shuffle <card's own name> into its owner's library" (Green Sun's Zenith).
#: CR 304.2/307.2's "the actions stated in its rules text are followed" runs
#: this sentence during resolution the same as any other, but the *result* -
#: the spell leaving the stack for the library instead of the graveyard - is
#: applied by `machines/replacement.py`'s `_stack_replacements` off the same
#: sentence (see its own docstring): the destination is not something a
#: spell-resolution clause *runs*, it is what CR 608.2n/CR 304.2/CR 307.2's own
#: final "put into its owner's graveyard" step is replaced by, the same split
#: `_REBOUND_LINE_RE` already draws for CR 702.88a's rebound. Left in the text,
#: this sentence matches no clause shape `_parse_mixed_clause` reads and fails
#: the whole effect closed (CR 608.2c has no half-effect) - which is exactly
#: the bug this exists to fix: Green Sun's Zenith's search never ran because
#: its second sentence poisoned the first (`_parse_mixed_clauses`' fail-closed
#: policy, working as intended, on a clause nothing yet read). Stripping it
#: here by the resolving card's own name, not a name table, keeps this generic
#: for any future card of the same shape.
def _strip_self_shuffle_clause(card_name: str, text: str) -> str:
    pattern = re.compile(
        rf"(?:^|(?<=[.\s]))Shuffle {re.escape(card_name)} into its owner's library\.?\s*",
        re.IGNORECASE,
    )
    return pattern.sub("", text)


def effect_for(
    card_name: str, effect_text: str | None = None, *, x_value: int | None = None
) -> Effect | None:
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

    `x_value` is CR 107.3a's X as the caster announced it, read by the caller
    off `Game.cast_record` - `None` for a spell with no `{X}` in its own mana
    cost, which leaves every bare "X" in the text alone. That matters: a card
    that defines its own X in its rules text instead (Craterhoof Behemoth's
    "get +X/+X ... where X is the number of creatures you control") is CR
    107.3f's X, not CR 107.3a's, and substituting the cast X into it would be
    wrong, not merely unhelpful - `None` keeps this function out of that
    card's way entirely.

    Given a real value, the *unsubstituted* text is still tried first:
    Wrath of the Skies's `_parse_x_energy_pay_destroy_by_mana_value` and
    Galvanic Discharge's `_parse_target_get_energy_pay_damage` already read
    `Game.cast_record` for themselves at resolution and match the literal
    word "X" in their own regex - substituting it away first would silently
    turn a working parser into a non-match. Only if that first pass reads
    nothing is the text substituted (the same way `machines/modes.py`'s
    `substitute_x` already does for a modal spell's own mode text) and tried
    again, which is what makes a search's "mana value X or less" readable by
    `_SEARCH_AND_PUT_RE`'s `\\d+` group.
    """
    explicit = EFFECTS.get(card_name)
    if explicit is not None:
        return explicit
    if effect_text is None:
        return None
    effect_text = _strip_self_shuffle_clause(card_name, effect_text)
    if is_modal_text(effect_text):
        return resolve_modal_spell
    effect = _spell_effect_or_notice(effect_text)
    if effect is not None or x_value is None:
        return effect
    return _spell_effect_or_notice(substitute_x(effect_text, x_value))


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


#: "Each opponent skips their next untap step." - Brine Elemental's own
#: "turned face up" trigger (CR 702.37e, CR 614.10, CR 502.3).
_EACH_OPPONENT_SKIPS_NEXT_UNTAP_RE = re.compile(
    r"^each opponent skips their next untap step\.?$", re.IGNORECASE
)


def _parse_each_opponent_skips_next_untap_clause(text: str) -> AbilityEffect | None:
    """`_EACH_OPPONENT_SKIPS_NEXT_UNTAP_RE`'s shape - Brine Elemental's whole
    trigger. `Game.untap_step` is what actually consumes
    `players_skipping_next_untap` (CR 614.10a: the skip waits for the first
    occurrence that isn't itself skipped)."""
    if _EACH_OPPONENT_SKIPS_NEXT_UNTAP_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        for opponent in _opponents(game, ability.controller):
            game.players_skipping_next_untap[opponent.username] = (
                game.players_skipping_next_untap.get(opponent.username, 0) + 1
            )

    return effect


def damage_each_creature(amount: int) -> AbilityEffect:
    """Extinguisher Battleship: "this Spacecraft deals 4 damage to each
    creature" (CR 119.3) - CR 102.2 has nothing to say here, since "each
    creature" names every creature on the battlefield, not a player group.

    Read off the *computed* board (CR 613.5): a noncreature permanent that
    became a creature only through a continuous effect still takes the
    damage, and one that stopped being a creature does not - the same
    correction `count_expression`'s "you control" reading already applies.
    """

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        board = game.computed_board()
        for creature in list(game.battlefield):
            if Type.CREATURE in board.of(creature).types:
                game.deal_damage(creature, amount, source=source)

    return effect


#: "Each opponent loses life equal to the number of creature cards in your
#: graveyard." (Grist, the Hunger Tide's -5) - CR 119.3's life loss, dealt to
#: CR 102.2's "each opponent" rather than a target, with the amount read
#: through the shared `count_expression` (P6) below rather than a one-off
#: reader of its own.
_EACH_OPPONENT_LOSES_LIFE_EQUAL_TO_RE = re.compile(
    r"^each opponent loses life equal to (?P<expr>.+?)\.?$", re.IGNORECASE
)


def _parse_each_opponent_loses_life_equal_to(text: str) -> AbilityEffect | None:
    """Grist, the Hunger Tide's -5, see `_EACH_OPPONENT_LOSES_LIFE_EQUAL_TO_RE`.

    `None` if `count_expression` cannot read the "equal to" phrase - there is
    no fail-closed notice for this one shape specifically, matching this
    file's existing convention that only a few clause shapes (conditional
    sacrifice, mana adding, the reflexive/anaphoric/delayed/imprint families)
    have a dedicated notice; everything else still silently returns `None`
    from `_ability_effect_or_notice`, unchanged from before this wave.
    """
    match = _EACH_OPPONENT_LOSES_LIFE_EQUAL_TO_RE.fullmatch(text.strip())
    if match is None:
        return None
    counter = count_expression(match.group("expr"))
    if counter is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = ability.controller
        amount = counter(game, controller)
        if amount <= 0:
            return
        for opponent in _opponents(game, controller):
            opponent.lose_life(amount)

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


#: "Look at the top N cards of your library. Exile one of them face down
#: and put the rest on the bottom of your library in a random order." -
#: `machines/keywords._hideaway_ability`'s own expansion of "Hideaway N"
#: (CR 702.75a), read here off that generated text with no per-card row -
#: any future card printing hideaway is covered the same way.
_HIDEAWAY_LOOK_EXILE_ONE_RE = re.compile(
    r"^look at the top (?P<n>\d+) cards of your library\. "
    r"exile one of them face down and put the rest on the bottom of your "
    r"library in a random order\.?$",
    re.IGNORECASE,
)


def _parse_hideaway_clause(text: str) -> AbilityEffect | None:
    """`_HIDEAWAY_LOOK_EXILE_ONE_RE`'s shape (CR 702.75a).

    The exiled card is tagged `ExileMarker.HIDEAWAY`, linked back to this
    permanent's own id (`ExileAnnotation.linked_permanent_id`), so a later
    ability printed on the same card (Fight Rigging's own beginning-of-combat
    trigger) can find it again by source rather than by name. Left face down
    (`CardState.face_up = False`, CR 406.3) with no `FaceDownCharacteristics`
    of its own - hideaway is not morph, and nothing in this pool casts a
    hidden-away card face down the way CR 708 lets a morphed one be.
    """
    match = _HIDEAWAY_LOOK_EXILE_ONE_RE.fullmatch(text.strip())
    if match is None:
        return None
    n = int(match.group("n"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.player(ability.controller)
        looked = list(player.library[:n])
        if not looked:
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt="choose a card to exile face down",
                source=ability.source_name,
                amount=1,
                cards=tuple(state.id for state in looked),
            )
        )
        assert isinstance(chosen_ids, tuple)
        by_id = {state.id: state for state in looked}
        chosen = by_id[chosen_ids[0]]
        rest = [state for state in looked if state is not chosen]

        player.cards_in(Zone.LIBRARY).remove(chosen)
        chosen.move_to(Zone.EXILE)
        chosen.face_up = False
        chosen.exile_annotation = ExileAnnotation(
            marker=ExileMarker.HIDEAWAY, owner=chosen.owner, linked_permanent_id=ability.source_id
        )
        game.exile.append(chosen)

        rng = Random(f"{game.shuffle_seed}:{game.shuffles_performed}:hideaway")  # noqa: S311
        rng.shuffle(rest)
        for state in rest:
            player.move(state, Zone.LIBRARY)
        if rest:
            game.shuffles_performed += 1

    return effect


#: "Put a +1/+1 counter on target creature you control. Then if you control
#: a creature with power 7 or greater, you may play the exiled card without
#: paying its mana cost." - Fight Rigging's own beginning-of-combat trigger,
#: read as one CR 608.2c instruction: the counter always happens, and only
#: then is the board rechecked (CR 608.2c's "then" orders the two parts, and
#: CR 608.2b/608.2c evaluates a mid-effect condition against the game state
#: as it exists at that point in resolution - after the counter was placed,
#: not before) for whether the free-cast permission is on offer at all.
_HIDEAWAY_COUNTER_THEN_CONDITIONAL_FREE_CAST_RE = re.compile(
    r"^put a \+1/\+1 counter on target creature you control\. "
    r"then if you control a creature with power (?P<threshold>\d+) or greater, "
    r"you may play the exiled card without paying its mana cost\.?$",
    re.IGNORECASE,
)


def _parse_hideaway_counter_then_conditional_free_cast_clause(text: str) -> AbilityEffect | None:
    """`_HIDEAWAY_COUNTER_THEN_CONDITIONAL_FREE_CAST_RE`'s shape - Fight
    Rigging's whole beginning-of-combat trigger (CR 122.1a's counter;
    CR 601.3's permission to play a specific card, granted here rather than
    with `Game.grant_play_permission` because the text names no duration -
    the permission exists only as this ability itself resolves).

    "The exiled card" is CR 400.7 anaphora back to hideaway's own exile
    (`ExileMarker.HIDEAWAY`, `ExileAnnotation.linked_permanent_id` pointing
    at this same source) - the *only* card this permanent could mean, since
    it is the one card hideaway ever hid.
    """
    match = _HIDEAWAY_COUNTER_THEN_CONDITIONAL_FREE_CAST_RE.fullmatch(text.strip())
    if match is None:
        return None
    threshold = int(match.group("threshold"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        for target in game.resolve_targets(ability):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                game.add_counters(target, Counter.PLUS_ONE, 1)

        board = game.computed_board()
        controls_big_creature = any(
            Type.CREATURE in board.of(permanent).types
            and (board.of(permanent).power or 0) >= threshold
            for permanent in game.permanents_controlled_by(ability.controller)
        )
        if not controls_big_creature:
            return

        hidden = next(
            (
                card
                for card in game.exile
                if card.exile_annotation is not None
                and card.exile_annotation.marker == ExileMarker.HIDEAWAY
                and card.exile_annotation.linked_permanent_id == ability.source_id
            ),
            None,
        )
        if hidden is None:
            return
        if not game.may(
            game.player(ability.controller),
            "play the exiled card without paying its mana cost",
            source=ability.source_name,
        ):
            return
        game.cast_free_from_exile(hidden, ability.controller)

    return effect


#: "You may pay any amount of life. If you do, draw that many cards." -
#: Necrodominance's own end-step trigger (CR 119.4, CR 118.12's "if you do").
_PAY_ANY_LIFE_THEN_DRAW_THAT_MANY_RE = re.compile(
    r"^you may pay any amount of life\. if you do, draw that many cards\.?$", re.IGNORECASE
)


def _parse_pay_any_life_then_draw_that_many_clause(text: str) -> AbilityEffect | None:
    """`_PAY_ANY_LIFE_THEN_DRAW_THAT_MANY_RE`'s shape - Necrodominance's
    whole end-step trigger, via `Game.pay_any_amount_of_life`
    (`DecisionKind.PAY_LIFE_AMOUNT`, new this wave - see the report)."""
    if _PAY_ANY_LIFE_THEN_DRAW_THAT_MANY_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.player(ability.controller)
        paid = game.pay_any_amount_of_life(player, source=ability.source_name)
        if paid > 0:
            game.draw_cards(player.username, paid)

    return effect


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
        return bool(wanted & {subtype.lower() for subtype in state.subtypes})

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
    r"(?P<basic_land_type> with a basic land type)?"
    r"(?: with mana value (?P<max_mv>\d+) or less)?"
    r"(?:, reveal it)?"
    r", put (?:it|that card) (?P<dest>into your hand|onto the battlefield(?P<tapped> tapped)?)"
    r"(?:, then shuffle)?\.?",
    re.IGNORECASE,
)

#: CR 305.6: "The basic land types are Plains, Island, Swamp, Mountain, and
#: Forest. If an object uses the words 'basic land type,' it's referring to
#: one of these subtypes." A *subtype* question, independent of the "basic"
#: supertype - CR 305.8: "Any land that doesn't have this supertype is a
#: nonbasic land, even if it has a basic land type" - so a shockland or a
#: Ravnica dual (Steam Vents, Breeding Pool: `Land — Island Mountain`,
#: `Land — Forest Island`) genuinely qualifies for "a land card with a basic
#: land type" even though it is not itself a basic land. Folding this
#: wording into `_quality_matcher`'s existing "basic land" branch (which
#: requires the *supertype*, for "a basic land card") would be the wrong,
#: narrower rule.
_BASIC_LAND_TYPE_NAMES = frozenset({"Plains", "Island", "Swamp", "Mountain", "Forest"})


def _has_a_basic_land_type(state: CardState) -> bool:
    return any(subtype in _BASIC_LAND_TYPE_NAMES for subtype in state.card.subtypes)


def _named_type_matcher(word: str) -> Callable[[CardState], bool]:
    """One word of a search's stated quality: a land type or a card type.

    "Mountain or Plains" names land *types* (CR 305.6, CR 205.3i), which is why
    a shockland is a legal find under its own name; a search naming a card type
    instead ("artifact or creature card") is CR 205.2a's list. Trying both and
    taking either is exactly what a one-word quality needs, since a word is
    never both at once.

    A **"non<type>"** word is CR 109.2's negation of one of CR 205.2a's card
    types - Ugin, Eye of the Storms' "colorless nonland cards". Only a card
    *type* is negated here, never a land subtype or a supertype: "nonbasic"
    reads as a supertype (CR 205.4a) this function has no access to, and
    answering "everything" for it would be a fails-open guess, so it comes back
    matching nothing, exactly as it did before this branch existed.
    `_search_quality_is_readable` is what stops such a word ever reaching a
    resolving effect in the first place.
    """
    if word.lower().startswith("non"):
        try:
            excluded = Type(word[3:].lower())
        except ValueError:
            return lambda state: False
        return lambda state: excluded not in state.types
    land_type = has_land_type(word)
    try:
        card_type: Type | None = Type(word.lower())
    except ValueError:
        card_type = None

    def matches(state: CardState) -> bool:
        return land_type(state) or (card_type is not None and card_type in state.types)

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
            return lambda state: not state.colors and type_matches(state)
        return lambda state: color in state.colors and type_matches(state)
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
            return rest(state) and Supertype.BASIC in state.supertypes

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
        return base(state) and state.mana_value <= ceiling

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
    if match.groupdict().get("basic_land_type"):
        # CR 305.6/305.8: "a land card with a basic land type" is a *subtype*
        # question, not the "basic" supertype `_quality_matcher`'s own "basic
        # land" branch checks - see `_has_a_basic_land_type`'s own docstring.
        base_matches = matches

        def matches(state: CardState, _base: Callable[[CardState], bool] = base_matches) -> bool:
            return _base(state) and _has_a_basic_land_type(state)

        description = f"{description} with a basic land type"
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


#: Beseech the Queen's own shape: "Search your library for a card with mana
#: value less than or equal to <the number of lands you control>, reveal it,
#: put it into your hand, then shuffle." `_SEARCH_AND_PUT_RE`'s own `max_mv`
#: group is `\d+` only - a literal printed digit, Ranger-Captain of Eos's
#: "mana value 1 or less" - so a search bounded by a live board count instead
#: never matches it and the whole clause was falling through to nothing. CR
#: 701.23a/701.23b: still a plain search with a stated quality (failing to
#: find remains legal); CR 701.24a/701.24b: `_search_library` already folds
#: the shuffle in. No quality beyond the mana-value ceiling is printed ("a
#: card", not "a creature card"), so `_quality_matcher` plays no part here.
_SEARCH_MV_LTE_COUNT_RE = re.compile(
    r"^search (?:your|their) library for a card with mana value less than or "
    r"equal to (?P<expr>.+?), reveal it, put it into your hand, then shuffle\.?$",
    re.IGNORECASE,
)


def _parse_search_mv_lte_count_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_SEARCH_MV_LTE_COUNT_RE`'s shape, or `None` if this is not it."""
    match = _SEARCH_MV_LTE_COUNT_RE.fullmatch(clause.strip())
    if match is None:
        return None
    counter = count_expression(match.group("expr"))
    if counter is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        ceiling = counter(game, controller.username)

        def matches(state: CardState) -> bool:
            return state.mana_value <= ceiling

        found = _search_library(game, controller, matches, source=source)
        if found is not None:
            controller.add(found, Zone.HAND)

    return effect


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
#: Griselbrand's "Draw seven cards" is the reason this exists at all. "Twenty"
#: is Ulamog, the Ceaseless Hunger's own "exiles the top twenty cards of their
#: library" - the largest spelled-out count anywhere in the pool.
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
    "twenty": 20,
}
_COUNT = r"(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|twenty)"


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
# CR 701.9a: "To discard a card, move it from its owner's hand to that
# player's graveyard." CR 701.9b: absent an override, the discarding player
# chooses which - Wistfulness's own "draw two cards, then discard a card" is
# exactly this default, unlike Thoughtseize's/Go Blank's own "target player
# discards ..." (`_TARGET_PLAYER_DISCARDS_RE`), which name a *different*
# player than whoever this clause's own `player` argument is. Deliberately
# does not read "you " ahead of "discard" the way `_DRAW_RE` optionally does:
# every printed shape in the pool either says "discard a card" bare (an
# ability's own effect, spoken as an instruction) or "you may discard a
# card" (peeled off by `_parse_optional_player_clause` before this ever
# runs), so there is no "you discard a card" shape left to also match.
_DISCARD_A_CARD_RE = re.compile(rf"^discards? (?:a card|(?P<n>{_COUNT}) cards?)$", re.IGNORECASE)
# CR 701.17a: "puts that many cards from the top of their library into their
# graveyard."
_MILL_RE = re.compile(rf"(?:you )?mills? (?:a card|(?P<n>{_COUNT}) cards?)", re.IGNORECASE)
# CR 701.25a / CR 701.22a.
_SURVEIL_RE = re.compile(r"surveils? (?P<n>\d+)", re.IGNORECASE)
#: "Scry N" (Preordain, most spells) and "Target player scries N" (Kozilek's
#: Command's third-person mode) - `scr(?:y|ies)` reads both conjugations.
_SCRY_RE = re.compile(r"scr(?:y|ies) (?P<n>\d+)", re.IGNORECASE)


def _discard_cards(game: "Game", player: Player, count: int, source: str) -> None:
    """CR 701.9a/701.9b: `player` discards `count` cards of their own choice.

    A hand shorter than `count` is not a violation - the player discards
    their whole hand, one card at a time, the same floor
    `_parse_target_player_discards_clause` already applies to a discard the
    resolving spell aims at someone else.
    """
    needed = min(count, len(player.hand))
    if needed <= 0:
        return
    chosen_ids = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=player.username,
            prompt=f"discard {needed} card(s)",
            source=source,
            amount=needed,
            cards=tuple(state.id for state in player.hand),
        )
    )
    assert isinstance(chosen_ids, tuple)
    by_id = {state.id: state for state in player.hand}
    game.discard_cards(player.username, [by_id[card_id] for card_id in chosen_ids], source=source)


def _mill(game: "Game", player: Player, count: int) -> list[CardState]:
    """CR 701.17a, routed through `Game.put_into_graveyard` the way
    `Game.surveil` moves its own graveyard-bound cards - so a replacement
    effect watching a card enter a graveyard (Rest in Peace) still gets its
    say (CR 614.1a).

    Returns the cards actually milled (fewer than `count` at an empty
    library, CR 701.17a's own "as many of those cards as possible") - Grist,
    the Hunger Tide's `+1` and Tyvar, Jubilant Brawler's `-2` both act on
    *which* cards this specific mill moved, not the graveyard generally.
    """
    milled = list(player.library[:count])
    for card in milled:
        game.put_into_graveyard(card)
    return milled


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

    if match := _DISCARD_A_CARD_RE.fullmatch(clause):
        amount = _count(match.group("n")) if match.group("n") else 1
        return lambda game, player, source: _discard_cards(game, player, amount, source)

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

#: Reminder text that sits mid-sentence rather than on its own line
#: (`_REMINDER_LINE_RE`'s shape) or at the very end of the whole text
#: (`split_effect_clauses`'s own trailing strip) - Opt's "Scry 1. (Look at
#: the top card of your library. You may put that card on the bottom.)\nDraw
#: a card." prints its reminder text right after the first clause's period,
#: mid-line. Left alone, the periods *inside* the parenthetical get read by
#: `_CLAUSE_SEPARATOR` as clause boundaries of their own, producing
#: unparseable fragments ("(Look at the top card of your library", "You may
#: put that card on the bottom.)") that took the whole spell down to no
#: effect (CR 608.2c's fail-closed-per-clause-run has no notion of a clause
#: that is really reminder text wearing a period). CR 207.2a: reminder text
#: is never rules text wherever it sits, so stripping it anywhere is safe.
_INLINE_REMINDER_RE = re.compile(r"[ \t]*\([^()]*\)")

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

#: Kicker's own line (CR 702.33a: "a static ability that functions while the
#: spell with kicker is on the stack", never itself a CR 608.2c resolution
#: instruction), reminder text and all - Burst Lightning prints "Kicker {4}
#: (...)" ahead of its own "deals 2 damage to any target. If this spell was
#: kicked, it deals 4 damage instead.", the same leading shape
#: `_SUSPEND_LINE_RE`/`_CASCADE_LINE_RE` already strip theirs from. Left
#: unstripped, `split_effect_clauses` reads "Kicker {4}" as an unreadable
#: clause of its own and `_parse_mixed_clauses`'s fail-closed-per-clause rule
#: takes the whole damage sentence down with it - the same bug already fixed
#: for Suspend, Cascade, Replicate, Cycling, Flashback, and Harmonize's own
#: lines. Paying kicker (`Casting.pay_kicker`) and reading whether it was
#: paid (`Game.cast_record(spell).kicked`, CR 702.33d) are both already built
#: elsewhere; only this line's poisoning effect on an unrelated sentence is
#: fixed here.
_KICKER_LINE_RE = re.compile(
    r"^Kicker [^\n(]+(?:\([^()]*\))?[ \t]*\n+", re.MULTILINE | re.IGNORECASE
)

#: Replicate's own line (CR 702.56a), reminder text and all - Consign to
#: Memory prints "Replicate {1} (...)" ahead of its own "Counter target
#: triggered ability or colorless spell.", the same lead-in shape Suspend's
#: line already strips. Replicate itself (an additional cost paid as the
#: spell is cast, copying it once per time paid) is not read anywhere in this
#: engine - `scripts/sweep_pool.py --keywords` reports it as ignored, and
#: `docs/engine-coverage.md` records the gap - so a card printing it counters
#: its one real target correctly and creates no copies, rather than losing
#: its whole effect to a line nothing here executes.
_REPLICATE_LINE_RE = re.compile(
    r"^Replicate [^\n(]+(?:\([^()]*\))?[ \t]*\n+", re.MULTILINE | re.IGNORECASE
)

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

#: Cycling's own line (CR 702.29a), reminder text and all - Censor prints
#: "Cycling {U} (...)" *after* its own resolution sentence. Cycling is a
#: separate activated ability (discard this card, draw a card), never an
#: instruction the counter effect itself carries out, so without this strip
#: `split_effect_clauses` reads "Cycling {U}" as a second, unreadable clause
#: of the *same* effect and `_parse_mixed_clauses`'s fail-closed-per-clause
#: rule takes the real "Counter target spell unless ..." sentence down with
#: it - exactly the Suspend/Cascade/Replicate bug this file already
#: documents for those three lines.
_CYCLING_LINE_RE = re.compile(
    r"[ \t]*\n?[ \t]*Cycling [^\n(]+(?:\([^()]*\))?[ \t]*\n?", re.MULTILINE | re.IGNORECASE
)

#: Flashback's own line (CR 702.34a - "two static abilities: one that
#: functions while the card is in a player's graveyard and another that
#: functions while the card is on the stack", neither a CR 608.2c resolution
#: instruction), reminder text and all - Faithless Looting prints "Flashback
#: {2}{R} (...)" on its own line *after* its one resolution sentence, exactly
#: the trailing shape `_CYCLING_LINE_RE`'s own docstring already describes.
#: Left unstripped, `split_effect_clauses` reads "Flashback {2}{R}" as a
#: second, unreadable clause of the same effect and `_parse_mixed_clauses`'s
#: fail-closed-per-clause rule takes "Draw two cards, then discard two
#: cards." down with it - the same bug already fixed for Suspend, Cascade,
#: Replicate, Cycling, and Harmonize's own lines. **Anchored on a mana cost
#: immediately after the word**, unlike `_CYCLING_LINE_RE`'s bare `[^\n(]+`:
#: the "Flashback" spell (distinct from the keyword) prints "... gains
#: flashback until end of turn" as ordinary prose with no cost symbol
#: following it, and an unanchored copy of `_CYCLING_LINE_RE`'s shape ate
#: that whole sentence and everything after it as if it were this line -
#: found and fixed in the same session this regex was added, by testing the
#: "Flashback" spell itself. Flashback the *keyword* - actually casting the
#: card from the graveyard - is built separately in `machines/casting.py`
#: (`keyword_cast_options`/`ADDITIONAL_COST_KEYWORDS` territory); only this
#: line's poisoning effect on an unrelated sentence is fixed here.
_FLASHBACK_LINE_RE = re.compile(
    r"[ \t]*\n?[ \t]*Flashback (?:\{[^{}]+\})+[ \t]*(?:\([^()]*\))?[ \t]*\n?",
    re.MULTILINE | re.IGNORECASE,
)

#: Harmonize's own line (CR 702.180/702.180a - "three static abilities: one
#: that functions while the card is in a player's graveyard and two that
#: function while the spell with harmonize is on the stack", none of them a
#: CR 608.2c resolution instruction, and none built by this engine), reminder
#: text and all - Nature's
#: Rhythm prints "Harmonize {X}{G}{G}{G}{G} (...)" on its own line *after* its
#: one resolution sentence, the same trailing position `_REBOUND_LINE_RE` and
#: `_CYCLING_LINE_RE` strip theirs from. Left unstripped, this line is not a
#: CR 608.2c resolution instruction at all - it is a static permission to cast
#: the card from the graveyard for an alternative cost - but `split_effect_
#: clauses` cannot tell that from an ordinary second clause, so it poisons the
#: whole effect (`_parse_mixed_clauses`'s fail-closed policy) the same way
#: Suspend's, Cascade's, Replicate's, and Cycling's own lines used to before
#: each got this exact treatment. Harmonize the *keyword* - casting from the
#: graveyard, tapping a creature to discount it - is not built anywhere by
#: this; only the line's poisoning effect on an unrelated sentence is fixed.
_HARMONIZE_LINE_RE = re.compile(
    r"[ \t]*\n?[ \t]*Harmonize [^\n(]+(?:\([^()]*\))?[ \t]*\n?", re.MULTILINE | re.IGNORECASE
)

#: Force of Will's and Force of Negation's own CR 118.9 pitch line - "You may
#: pay 1 life and exile a blue card from your hand rather than pay this
#: spell's mana cost." or, gated on a plain timing condition rather than a
#: numbered rule, "If it's not your turn, you may exile a blue card from your
#: hand rather than pay this spell's mana cost."
#: Read (and paid) by `machines/cost.alternative_cost_offers`/`machines/
#: casting.Casting.use_pitch_cost` - never part of what the *spell* does on
#: resolution, so it is stripped here the same way `_ADDITIONAL_COST_LINE_RE`
#: strips CR 118.8a's "As an additional cost to cast this spell, ...".
_PITCH_ALTERNATIVE_COST_LINE_RE = re.compile(
    r"^(?:If it's not your turn, )?You may [^.]+? rather than pay this spell's mana cost\.\s*",
    re.IGNORECASE | re.MULTILINE,
)

#: "This spell costs {N} less to cast if [condition]." (Mystical Dispute) - a
#: static ability about *announcing* the spell (CR 601.2f), never part of
#: what it does on resolution. This self-referential reduction (as opposed to
#: `machines/cost.cost_modifier_effect`'s board-static "Spells cost {N} more
#: to cast", read off a *different* permanent) is now computed by
#: `Game.cost_reduction_for`/`_COSTS_LESS_IF_TARGETS_COLOR_SPELL_RE`, opted
#: into by calling `Game.determine_total_cost(casting)` instead of
#: `casting.determine_cost()` directly - the same opt-in shape Emrakul, the
#: Promised End's own graveyard-count reduction already uses. Stripping the
#: sentence here still matters regardless: it keeps this line from being
#: misread as an unparseable resolution clause and taking "Counter target
#: spell unless its controller pays ..." down with it, since this dispatcher
#: only ever reads what a spell *does*, not what it costs.
_SELF_COST_REDUCTION_LINE_RE = re.compile(
    r"^This spell costs \{\d+\} less to cast if [^.]+\.\s*", re.IGNORECASE | re.MULTILINE
)

#: The other self-discount template, tied to an additional cost rather than a
#: condition - March of Otherworldly Light's "This spell costs {2} less to
#: cast for each card exiled this way." (following its own "As an additional
#: cost to cast this spell, you may exile any number of white cards from your
#: hand." sentence, which `_ADDITIONAL_COST_LINE_RE` already strips). Left
#: unstripped, `split_effect_clauses` reads it as a clause of its own that no
#: shape in this file matches, taking "Exile target artifact, creature, or
#: enchantment with mana value X or less." down with it - the same
#: preamble-poisoning bug `_SELF_COST_REDUCTION_LINE_RE` already fixes for
#: the conditional discount shape. The discount itself is not computed
#: anywhere in this engine (CR 118.8a's additional cost and CR 601.2f's cost
#: reduction are both about *paying*, not resolving) - only this line's
#: effect on an unrelated resolution sentence is fixed here.
_PER_COUNT_COST_REDUCTION_LINE_RE = re.compile(
    r"^This spell costs \{\d+\} less to cast for each [^.]+\.\s*", re.IGNORECASE | re.MULTILINE
)

#: Fuse's own line (CR 702.102a), reminder text and all - Wear // Tear prints
#: "Fuse (You may cast one or both halves of this card from your hand.)"
#: *after* each half's own resolution sentence, the same trailing position
#: Rebound's and Cycling's lines already strip from. Fuse itself (CR 702.102d's
#: "combined characteristics" when cast as one fused spell) is not modelled by
#: this engine - `docs/engine-coverage.md` records the gap - so stripping this
#: line only keeps it from being misread as a second, unreadable clause of
#: whichever single half was actually cast, the same "reminder text is not a
#: resolution instruction" reasoning as Suspend/Cascade/Replicate above.
_FUSE_LINE_RE = re.compile(r"^[ \t]*Fuse(?:\s*\([^()]*\))?[ \t]*\n?", re.MULTILINE | re.IGNORECASE)


def _strip_non_effect_preamble(text: str) -> str:
    """Sentences that describe the spell but are not part of resolving it."""
    text = _ADDITIONAL_COST_LINE_RE.sub("", text)
    text = _CANT_BE_COUNTERED_LINE_RE.sub("", text)
    text = _SUSPEND_LINE_RE.sub("", text)
    text = _CASCADE_LINE_RE.sub("", text)
    text = _KICKER_LINE_RE.sub("", text)
    text = _REPLICATE_LINE_RE.sub("", text)
    text = _CYCLING_LINE_RE.sub("", text)
    text = _FLASHBACK_LINE_RE.sub("", text)
    text = _HARMONIZE_LINE_RE.sub("", text)
    text = _PITCH_ALTERNATIVE_COST_LINE_RE.sub("", text)
    text = _SELF_COST_REDUCTION_LINE_RE.sub("", text)
    text = _PER_COUNT_COST_REDUCTION_LINE_RE.sub("", text)
    text = _REBOUND_LINE_RE.sub("", text)
    text = _FUSE_LINE_RE.sub("", text)
    text = _REMINDER_LINE_RE.sub("", text)
    text = _INLINE_REMINDER_RE.sub("", text)
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


#: Tamiyo, Compleated Sage's `+1`: "Tap up to one target artifact or
#: creature. It doesn't untap during its controller's next untap step." Two
#: sentences, not one clause: the second's "it" is anaphoric (CR 400.7) for
#: whatever the first named, so this is read whole rather than through
#: `_parse_targeted_clauses`'s independent per-clause dispatch, the same
#: reason `_X_DAMAGE_DIVIDED_DOUBLED_RE` reads Shatterskull Smashing's own
#: two sentences together.
_TAP_TARGET_THEN_NO_UNTAP_RE = re.compile(
    r"^tap (?P<phrase>up to \S+ target .+?)\.\s*"
    r"it doesn'?t untap during its controller'?s next untap step\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_tap_target_then_no_untap_clause(text: str) -> AbilityEffect | None:
    """`_TAP_TARGET_THEN_NO_UNTAP_RE`'s shape.

    CR 701.43a's exert wording - "you choose to have it not untap during your
    controller's next untap step" - is exactly what this sentence asks for,
    just imposed on a target by another permanent's ability rather than paid
    as the target's own activation cost, so `CardState.exerted`/`.untap`'s
    existing CR 701.43a-b machinery is reused rather than duplicated: setting
    the flag directly skips only the *target's* controller's next untap step,
    whoever that is, exactly as the printed "its controller's" reads.
    """
    whole = _strip_non_effect_preamble(text).strip()
    match = _TAP_TARGET_THEN_NO_UNTAP_RE.fullmatch(whole)
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        for target in game.resolve_targets(ability):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                target.tap()
                target.exerted = True

    return effect


#: Diamond City: "Move a shield counter from this land onto target creature."
#: CR 122.5's "move" keyword action, self-referential source (`_COUNTER_
#: SELF_SUBJECT`'s "this `<noun>`" shape, reused from `cost.py`'s own counter
#: phrasing) and a target destination.
_MOVE_COUNTER_RE = re.compile(
    rf"^move (?P<n>{_COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? from this \w+ onto "
    r"(?P<phrase>target .+)\.?$",
    re.IGNORECASE,
)


def _parse_move_counter_clause(text: str) -> AbilityEffect | None:
    """CR 122.5: "to 'move' a counter ... means to remove that counter from
    the object it's currently on and put it onto a second object. If either
    of these actions isn't possible, it's not done at all." Both halves are
    checked before either happens - a source with too few counters, or a
    target that is no longer legal, leaves the source's counters untouched
    rather than removing them into nothing.
    """
    match = _MOVE_COUNTER_RE.fullmatch(text.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=False):
        return None
    amount = _count(match.group("n"))
    kind = _counter_kind(match.group("kind"))
    if amount is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        if not source.can_remove_counters(kind, amount):
            return
        targets = [
            target
            for target in game.resolve_targets(ability)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        source.remove_counters(kind, amount)
        game.add_counters(targets[0], kind, amount)

    return effect


#: The Darkness Crystal: "Put target creature card exiled with The Darkness
#: Crystal onto the battlefield tapped under your control with two additional
#: +1/+1 counters on it." `machines/targeting.py`'s `TargetRequirement.
#: exiled_with_source` is what makes "target ... card exiled with `<name>`" a
#: real, checked target (CR 115.1) rather than a definite reference like
#: Ugin's Labyrinth's "the exiled card" - this parser only has to read what
#: happens once a legal one is chosen.
_PUT_EXILED_TARGET_ONTO_BATTLEFIELD_RE = re.compile(
    r"^put (?P<phrase>target .+?) onto the battlefield(?P<tapped> tapped)? "
    r"under your control(?: with (?P<n>\w+) additional (?P<kind>\+1/\+1|-1/-1|[a-z]+) "
    r"counters? on it)?\.?$",
    re.IGNORECASE,
)


def _parse_put_exiled_target_onto_battlefield_clause(text: str) -> AbilityEffect | None:
    """`_PUT_EXILED_TARGET_ONTO_BATTLEFIELD_RE`'s shape.

    CR 122.6: counters an effect adds once a permanent is already on the
    battlefield are a distinct event from CR 614.12's "enters with N
    counters" replacement - added here with `Game.add_counters` after `Game.
    put_onto_battlefield` has already run, the same order `enter_the_
    battlefield`'s own docstring describes for that different case.
    """
    match = _PUT_EXILED_TARGET_ONTO_BATTLEFIELD_RE.fullmatch(text.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=False, battlefield_only=False):
        return None
    tapped = match.group("tapped") is not None
    amount = _count(match.group("n")) if match.group("n") else None
    kind = _counter_kind(match.group("kind")) if match.group("kind") else None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        targets = [
            target for target in game.resolve_targets(ability) if isinstance(target, CardState)
        ]
        if not targets:
            return
        target = targets[0]
        controller = game.controller_of(ability).username
        game.put_onto_battlefield(target, controller, tapped=tapped)
        if amount and kind is not None:
            game.add_counters(target, kind, amount)

    return effect


#: Mosswort Bridge: "You may play the exiled card without paying its mana
#: cost if creatures you control have total power 10 or greater." Not a
#: target - "the exiled card" is CR 607.1's within-one-permanent anaphora for
#: whatever `machines/keywords.py`'s own `_hideaway_effect` linked to this
#: land with `ExileMarker.IMPRINTED`, the same definite reference Ugin's
#: Labyrinth's "Return the exiled card to its owner's hand" already reads.
_HIDEAWAY_PLAY_RE = re.compile(
    r"^you may play the exiled card without paying its mana cost if creatures you control "
    r"have total power (?P<threshold>\d+) or greater\.?$",
    re.IGNORECASE,
)


def _parse_hideaway_play_clause(text: str) -> AbilityEffect | None:
    """`_HIDEAWAY_PLAY_RE`'s shape.

    CR 608.2d: "the player can't choose an option that's illegal or
    impossible" - so, like `_parse_reflexive_sacrifice_clause`'s own
    "you may" shapes, the permission is only ever granted once the printed
    condition already holds; there is nothing to grant otherwise, rather than
    a permission that would refuse to be used. Total power is read off the
    printed characteristic (`CardState.power`), the same simplification
    `Game._activation_condition_holds`'s own "Activate only if you control a
    creature with power N or greater" already makes, not the layer-computed
    board - `docs/engine-coverage.md` records this as an activated ability's
    own intervening condition rather than a layer-6 shape.
    """
    match = _HIDEAWAY_PLAY_RE.fullmatch(text.strip())
    if match is None:
        return None
    threshold = int(match.group("threshold"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None:
            return
        controller = game.controller_of(ability)
        total_power = sum(
            state.power or 0
            for state in game.permanents_controlled_by(controller.username)
            if state.is_creature
        )
        if total_power < threshold:
            return
        card = game.card_imprinted_on(source.id)
        if card is None:
            return
        game.grant_play_permission(
            card,
            controller.username,
            action=PlayAction.PLAY,
            pays_mana_cost=False,
            source_name=source.name,
            rule="CR 601.3",
        )

    return effect


#: Back from the Brink: "Exile a creature card from your graveyard and pay
#: its mana cost: Create a token that's a copy of that card." "That card" is
#: not a target (CR 115.1 - the sentence never says "target") - it is CR
#: 607.1's anaphora back to whatever `machines/cost.exile_and_pay_mana_cost_
#: cost` chose while the cost was paid, carried onto the stack as `AbilityOn
#: Stack.cost_exiled_card_id` (see that field's own docstring).
_CREATE_TOKEN_COPY_OF_THAT_CARD_RE = re.compile(
    r"^create a token that'?s a copy of that card\.?$", re.IGNORECASE
)


def _parse_create_token_copy_of_cost_exiled_card_clause(text: str) -> AbilityEffect | None:
    """`_CREATE_TOKEN_COPY_OF_THAT_CARD_RE`'s shape.

    CR 707.2's copiable values travel through `token_copy_of`, the same
    primitive Ocelot Pride's own token-copy clause already uses. Nothing to
    do if the cost was never actually paid with a card this ability
    remembers - CR 113.7a lets the ability resolve regardless, it simply has
    nothing left to copy.
    """
    if _CREATE_TOKEN_COPY_OF_THAT_CARD_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        if ability.cost_exiled_card_id is None:
            return
        original = game.find_by_id(ability.cost_exiled_card_id)
        if not isinstance(original, CardState):
            return
        controller = game.controller_of(ability).username
        token_copy_of(game, original, controller)

    return effect


def put_counters_on_ability_targets(kind: Counter | str, amount: int) -> TargetedClause:
    """Put counters on each permanent this still legally targets (CR 122.1)."""

    def effect(game: "Game", stack_object: "StackObject") -> None:
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                game.add_counters(target, kind, amount)

    return effect


# --------------------------------------------------------------------------
# P4: put N counters on each member of a group ("each Cat you control"),
# rather than on something targeted (CR 122.1)
# --------------------------------------------------------------------------
#
# "Put a +1/+1 counter on each Cat you control." (Ajani, Nacatl Pariah's
# +2) and "... on each creature you control." (Leyline of Abundance) name no
# target at all - CR 115.1 has nothing to check here, so `put_counters_on_
# ability_targets`'s `game.resolve_targets` is the wrong tool. Ouroboroid's
# own "put X +1/+1 counters on each creature you control, where X is this
# creature's power" adds a magnitude read off the source itself - not
# `count_expression`'s "the number of ..." shape, since this is a plain
# characteristic read (CR 613.4, CR 613.5), not a count of anything.
_COUNTER_EACH_GROUP_RE = re.compile(
    rf"^put (?P<n>{_COUNT}|x) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on each "
    r"(?P<group>[a-z]+) you control(?:,\s*where x is (?P<expr>.+))?\.?$",
    re.IGNORECASE,
)


def _parse_put_counters_on_group_clause(text: str) -> AbilityEffect | None:
    """ "Put N <kind> counter(s) on each <group> you control." - the group-wide
    twin of `_COUNTER_TARGET_RE`'s "on target X" below.

    `<group>` is read off the **computed** board (CR 613.5, CR 613.4): a
    creature that gained the Cat type only through a continuous effect still
    counts, and one that stops being a Cat before this resolves does not -
    the same defect class this repo's own MDFC front-face bugs already
    documented for a printed-type-line-only read. `<group>` "creature" is a
    card type (CR 205.2a); anything else is read as a creature subtype
    (CR 205.3) rather than a card type, since Ajani's own "Cat" is one.
    """
    match = _COUNTER_EACH_GROUP_RE.fullmatch(text.strip())
    if match is None:
        return None
    kind = match.group("kind").lower()
    group = match.group("group")
    n_text = match.group("n").lower()
    expr = match.group("expr")
    fixed_amount: int | None
    if n_text == "x":
        if expr is None or expr.strip().rstrip(".").lower() != "this creature's power":
            return None
        fixed_amount = None
    else:
        fixed_amount = _count(n_text)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None:
            return
        if fixed_amount is None:
            amount = 0
            if source.zone is Zone.BATTLEFIELD:
                power = game.power_of(source)
                amount = max(power, 0) if power is not None else 0
        else:
            amount = fixed_amount
        if amount <= 0:
            return
        controller = ability.controller
        board = game.computed_board()
        for permanent in game.battlefield:
            chars = board.of(permanent)
            if chars.controller != controller:
                continue
            if group.lower() == "creature":
                if not chars.is_creature:
                    continue
            elif group not in chars.subtypes:
                continue
            game.add_counters(permanent, kind, amount)

    return effect


def _counter_kind(word: str) -> Counter | str:
    """Normalise a printed counter-kind word into what `add_counters`/
    `remove_counters` key on - the two CR 122.1a power/toughness spellings as
    `Counter.PLUS_ONE`/`Counter.MINUS_ONE`, and any other bare word (`oil`,
    `charge`, `fate`, ...) as the matching `Counter` member when the rules
    name one, or the plain lower-cased string otherwise (CR 122.1's kinds are
    an open set).
    """
    lowered = word.lower()
    if lowered == "+1/+1":
        return Counter.PLUS_ONE
    if lowered == "-1/-1":
        return Counter.MINUS_ONE
    try:
        return Counter(lowered)
    except ValueError:
        return lowered


# --------------------------------------------------------------------------
# W7a: put N counters on *this* permanent, or untap it - CR 602.2's activated
# ability naming no target at all, only itself (CR 113.7a's own object).
# Walking Ballista's "{4}: Put a +1/+1 counter on this creature." and Devoted
# Druid's "Put a -1/-1 counter on this creature: Untap this creature." are
# both this shape: a plain self-reference, never a "target", so
# `_parse_targeted_clause`'s whole `TargetedClause` family (which always reads
# a target off `game.resolve_targets`) is the wrong tool - these two read
# `ability.source(game)` instead, the same self lookup `damage_each_opponent`
# and `_parse_destroy_each_clause` already use for a source-only effect with
# nothing to target.
# --------------------------------------------------------------------------

#: "Put N `<kind>` counter(s) on this `<noun>`." - the self-referential twin of
#: `_COUNTER_TARGET_RE`'s "on target X" and `_COUNTER_EACH_GROUP_RE`'s "on each
#: `<group>` you control". `<noun>` is any word ("creature", "artifact",
#: "permanent") - the source's own name has already been normalised to "this
#: permanent" by `_self_normalized_effect_text` by the time this ever runs, so
#: a card that prints its own name instead of "this" (The Filigree Sylex, and
#: Grist, the Hunger Tide's own "+1") reads exactly the same way.
_COUNTER_ON_SELF_RE = re.compile(
    rf"^put (?P<n>{_COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on this \w+\.?$",
    re.IGNORECASE,
)


def _parse_put_counters_on_self_clause(text: str) -> AbilityEffect | None:
    """`_COUNTER_ON_SELF_RE`'s shape - Walking Ballista's `{4}` ability and
    The Filigree Sylex's `{T}` ability (CR 122.1).

    CR 113.7a: an ability existing "independently of its source"'s object can
    still be found by id in whatever zone it now occupies, but only a
    permanent still on the battlefield can receive a counter (CR 122.1: a
    counter marks a permanent, and one that left the battlefield is a new
    object with no counters to add to; `CardState.move_to` already clears them
    on the way out).
    """
    match = _COUNTER_ON_SELF_RE.fullmatch(text.strip())
    if match is None:
        return None
    amount = _count(match.group("n"))
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is not None and source.zone is Zone.BATTLEFIELD:
            game.add_counters(source, kind, amount)

    return effect


#: CR 701.46a: "'Adapt N' means 'If this permanent has no +1/+1 counters on
#: it, put N +1/+1 counters on it.'" A keyword action (CR 701), not a keyword
#: ability - the printed line is just "Adapt N.", the whole conditional
#: sentence being the reminder text substituted in. Basking Broodscale's
#: "{1}{G}: Adapt 1." is the pool's only printing.
_ADAPT_RE = re.compile(r"^adapt (?P<n>\d+)\.?$", re.IGNORECASE)


def _parse_adapt_clause(text: str) -> AbilityEffect | None:
    """CR 701.46a's "Adapt N" - see `_ADAPT_RE`.

    Read off the ability's own printed text with no per-card row: any future
    "Adapt N" printing reaches this the same way. The condition is checked at
    resolution - CR 701.46a's own "if this permanent has no +1/+1 counters on
    it" - so a permanent that already carries a +1/+1 counter is untouched,
    not merely reduced by the difference.
    """
    match = _ADAPT_RE.fullmatch(text.strip())
    if match is None:
        return None
    amount = int(match.group("n"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        if source.counters[Counter.PLUS_ONE] > 0:
            return
        game.add_counters(source, Counter.PLUS_ONE, amount)

    return effect


#: "Untap this creature." (Devoted Druid) - CR 701.26b's untap with no target
#: at all, the source's own cost-side counter placement having already been
#: paid by `cost.py`'s `PLACE_COUNTERS` component by the time this runs.
_UNTAP_SELF_RE = re.compile(r"^untap this \w+\.?$", re.IGNORECASE)


def _parse_untap_self_clause(text: str) -> AbilityEffect | None:
    """`_UNTAP_SELF_RE`'s shape - Devoted Druid's "Put a -1/-1 counter on this
    creature: Untap this creature." (CR 701.26b).

    The Devoted Druid + Vizier of Remedies loop this enables terminates on its
    own: nothing here prevents the state-based action CR 704.5f already
    performs once enough -1/-1 counters bring toughness to 0 - this function
    only ever reads whether the source is *still* on the battlefield before
    untapping it, the same check `_parse_put_counters_on_self_clause` makes.
    """
    if _UNTAP_SELF_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is not None and source.zone is Zone.BATTLEFIELD:
            source.untap()

    return effect


#: "Remove a time counter from this card." - Greater Gargadon's own second
#: ability, CR 702.62a's second ability spelled out on the card itself rather
#: than left to suspend's own reminder text. Unlike `_COUNTER_ON_SELF_RE`
#: above, this source is never on the battlefield when the ability resolves -
#: `machines.abilities._activated_ability_zone` reads the card's own
#: "Activate only if this card is suspended" restriction as CR 702.62b's
#: proof the source functions from exile - so there is no battlefield gate
#: to check here.
_REMOVE_TIME_COUNTER_SELF_RE = re.compile(
    r"^remove a time counter from this (?:card|permanent)\.?$", re.IGNORECASE
)


def _parse_remove_time_counter_from_self_clause(text: str) -> AbilityEffect | None:
    """`_REMOVE_TIME_COUNTER_SELF_RE`'s shape - Greater Gargadon's suspend-
    only sacrifice ability (CR 702.62a, CR 702.62b).

    Reuses `machines.casting.remove_suspend_time_counter` rather than a
    second counter-removal path, so a card whose own printed ability takes a
    time counter off this way is read by the identical CR 702.62b "suspended"
    check the upkeep trigger already uses - a card that is not actually
    suspended (already cast, already left exile, already at zero counters) is
    left untouched rather than erroring, the same "the *if* was false" shape.

    Chains straight into `machines.casting.finish_suspend`: removing the
    *last* time counter is CR 702.62a's third ability firing, and unlike the
    upkeep route (which nothing in this engine's turn machine dispatches
    automatically, so a scenario calls it by hand once per upkeep) this
    ability's own resolution *is* the concrete event that just happened, so
    there is no reason to leave the very next question - is this now the last
    counter? - for a caller to re-ask. `finish_suspend` is a no-op (returns
    `None`) whenever a counter remains, so this costs nothing on every
    activation but the last, and on the last it hands the card's owner the
    same `PlayPermission` (recorded on `Game.play_permissions`) the upkeep
    path already grants - "you may cast it without paying its mana cost" is
    still a choice the permission's own consumer makes, never forced here.
    """
    if _REMOVE_TIME_COUNTER_SELF_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None:
            return
        remove_suspend_time_counter(game, source)
        finish_suspend(game, source)

    return effect


#: "double the number of `<kind>` counters on `<group>`" - Kalonian Hydra's
#: own attack trigger doubles them on *every* creature its controller
#: controls, not only itself, which is why this is a group shape
#: (`_parse_put_counters_on_group_clause`'s own "each creature you control"
#: vocabulary) rather than the self-only `_COUNTER_ON_SELF_RE` above. CR
#: 701.10e: "To double the number of a kind of counters on a player or
#: permanent, give that player or permanent as many of those counters as
#: that player or permanent already has" - read here as one `add_counters`
#: call per qualifying permanent, for however many it already carries (zero
#: is a legal, silent no-op: doubling zero counters gives zero more).
_DOUBLE_COUNTERS_ON_GROUP_RE = re.compile(
    r"^double the number of (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters on "
    r"(?:this \w+|each (?P<group>creature|artifact|permanent) you control)\.?$",
    re.IGNORECASE,
)


def _parse_double_counters_on_group_clause(text: str) -> AbilityEffect | None:
    """`_DOUBLE_COUNTERS_ON_GROUP_RE`'s shape - Kalonian Hydra's "double the
    number of +1/+1 counters on each creature you control" (CR 701.10e).

    Reads the group off the *computed* board (CR 613.5), the same
    "you control" reading `_parse_put_counters_on_group_clause` already
    applies, so a permanent turned into a creature this turn is doubled too
    and one that stopped being one is not. "This `<noun>`" (no group named at
    all) doubles only the source itself, since the regex's other branch
    requires the "each ... you control" wording explicitly.
    """
    match = _DOUBLE_COUNTERS_ON_GROUP_RE.fullmatch(text.strip())
    if match is None:
        return None
    kind = _counter_kind(match.group("kind"))
    group_word = match.group("group")

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        if group_word is None:
            source = ability.source(game)
            targets = [source] if source is not None and source.zone is Zone.BATTLEFIELD else []
        else:
            board = game.computed_board()
            targets = [
                permanent
                for permanent in game.permanents_controlled_by(ability.controller)
                if Type.CREATURE in board.of(permanent).types
            ]
        for permanent in targets:
            key = kind if isinstance(kind, str) else kind.value
            current = permanent.counters[key]
            if current:
                game.add_counters(permanent, kind, current)

    return effect


def _parse_whole_text_token_clause(text: str) -> AbilityEffect | None:
    """A "Create ... token ..." ability read as *one whole, unsplit clause* -
    The Legend of Roku's `{8}` ability, "Create a 4/4 red Dragon creature
    token with flying and firebending 4."

    `_ability_effect_or_notice`'s ordinary path is `parse_mixed_effect`, which
    runs `split_effect_clauses` first - and that splitter's `_CLAUSE_SEPARATOR`
    cuts on a bare "and" (built for a sentence that joins two independent
    instructions, Lightning Helix's shape), which is wrong for a *comma-free
    two-item list inside one token's own "with" tail*: "with flying and
    firebending 4" would be cut into "with flying" and "firebending 4" before
    `_parse_token_clause` ever saw the whole tail, and the leftover
    "firebending 4" clause matches no shape at all - the whole ability failed
    closed over one keyword list, not because the token itself was unreadable.
    `_parse_token_clause` is tried directly against the untouched text
    instead; its own regex only ever fullmatches a *complete* token-creation
    sentence, so a card whose token clause is one instruction among several
    still falls through to the ordinary per-clause path unaffected.
    """
    # `split_effect_clauses` always strips one trailing "." before a clause
    # ever reaches `_parse_token_clause`; going around that splitter (see the
    # docstring above) means doing the same trim here - `_TOKEN_CLAUSE_RE`'s
    # own trailing `\.?` never gets the chance to, since its greedy DOTALL
    # `tail` group is satisfied first and simply absorbs the period instead.
    return _parse_token_clause(
        _strip_non_effect_preamble(text).strip().rstrip("."), for_spell=False
    )


#: `phrase` always captures from the word "target" itself (or "any target")
#: to the end of the clause, count words and all - `_targets_understood`
#: needs the count word, if any, to see "up to two" and refuse it.
_DESTROY_TARGET_RE = re.compile(r"destroy (?P<phrase>(?:any target|.*target.+))", re.IGNORECASE)
#: "Destroy target X and target Y." (Fumarole's "Destroy target creature and
#: target land.") - two independent, simultaneously-chosen targets in one
#: sentence, not two clauses. `_CLAUSE_SEPARATOR`'s bare-"and" split cuts this
#: into "Destroy target creature" and "target land" - a fragment with no verb
#: nothing here reads - the same "and" trap `_parse_x_damage_divided_and_
#: doubled_clause` and `_parse_look_top_n_may_battlefield_creature_bonus_
#: clause` already route around by reading their own sentence whole, ahead of
#: `split_effect_clauses`. `machines/targeting.py`'s own `profile_for_text`
#: already reads "target creature and target land" as two `TargetRequirement`s
#: (verified this session), so once the whole phrase reaches
#: `_targets_understood` intact, `destroy_ability_targets` - already built to
#: destroy *every* target a spell or ability still legally has, not just the
#: first - needs nothing new.
_DESTROY_TWO_TARGETS_RE = re.compile(
    r"^destroy (?P<phrase>target [^.]+? and target [^.]+?)\.?$", re.IGNORECASE
)


def _parse_destroy_two_targets_clause(effect_text: str) -> Effect | None:
    """`_DESTROY_TWO_TARGETS_RE`'s shape, or `None` if this is not it.

    `_targets_understood` deliberately refuses a phrase with more than one
    "target" requirement (its own docstring: "two 'target' words is two
    requirements, not this shape") - right for every single-target verb
    clause elsewhere in this file, wrong here, where two requirements is
    exactly the point. This repeats `_targets_understood`'s own per-
    requirement checks (understood, no unenforced "if", battlefield-only, a
    plain mandatory single target, not a player) across *both*
    requirements instead of refusing on sight of the second one.
    """
    whole = _strip_non_effect_preamble(effect_text).strip()
    match = _DESTROY_TWO_TARGETS_RE.fullmatch(whole)
    if match is None:
        return None
    phrase = match.group("phrase")
    if _TRAILING_DURATION_RE.search(phrase):
        return None
    profile = profile_for_text(phrase)
    if not profile.understood or len(profile.requirements) != 2:
        return None
    for requirement in profile.requirements:
        if _UNENFORCED_CONDITIONAL_RE.search(requirement.phrase) and (
            requirement.comparison_attribute is None
        ):
            return None
        if requirement.zones != frozenset({Zone.BATTLEFIELD}):
            return None
        if requirement.allows_players or requirement.unbounded:
            return None
        if requirement.minimum != 1 or requirement.maximum != 1:
            return None
    return destroy_ability_targets  # type: ignore[return-value]


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
#: "exile target nonland permanent an opponent controls until this
#: enchantment leaves the battlefield" (Static Prison). Checked *ahead* of
#: `_EXILE_TARGET_RE` below: that pattern's own phrase is `.*target.+`, a
#: superset that would otherwise swallow the whole "until ... leaves the
#: battlefield" tail into its own restriction and have it refused by
#: `_TRAILING_DURATION_RE` (see that guard's own docstring) - correct for
#: every *other* trailing duration this wave still cannot reverse, but wrong
#: for this one specific shape, which now has a real reversal.
#:
#: **CR 610.2** (verified this session): "Some one-shot effects create a
#: delayed triggered ability, which instructs a player to do something later
#: in the game (usually at a specific time) rather than as the spell or
#: ability that's creating them doing it immediately." The architect's own
#: pointer, confirmed rather than assumed: the return is a *second one-shot
#: effect*, created now (CR 603.7a) and firing whenever the enchantment
#: actually leaves, not a `ContinuousEffects` duration this engine would have
#: to notice has "expired" - modelled with exactly the `DelayedTrigger`
#: machinery `machines/delayed.py` already built for warp and for earthbend's
#: own two-sibling "dies or is put into exile" shape, extended to the three
#: departure routes this pool's permanents can actually take (destroyed,
#: sacrificed - both `TriggerEvent.DIES` - exiled, or bounced to hand).
_EXILE_UNTIL_THIS_LEAVES_BATTLEFIELD_RE = re.compile(
    r"^exile (?P<phrase>target .+?) until this "
    r"(?:permanent|enchantment|artifact|creature|planeswalker) leaves the battlefield$",
    re.IGNORECASE,
)


def _static_prison_return_callback(exiled_id: UUID, expected_stamp: UUID) -> DelayedEffect:
    """The delayed trigger's own effect (CR 610.2, CR 603.7): return the one
    exiled card - not `still_affects`, which reads `DelayedTrigger.subject_id`
    for both "what event fires this" *and* "what does it affect" alike.

    Those are two different objects here: the trigger's own `subject_id` is
    the *enchantment* (CR 603.7a's event is "Static Prison leaves the
    battlefield", not "the exiled card does anything"), but the card this
    callback has to bring back is whatever was exiled - a different id
    entirely. Closing over `exiled_id`/`expected_stamp` at the moment of
    exile keeps CR 603.7c's own check (same id, same zone, same incarnation)
    without forcing the trigger's single `subject_id` field to mean two
    different things at once.
    """

    def callback(game: "Game", ability: AbilityOnStack, trigger: DelayedTrigger) -> None:
        _dismiss_other_static_prison_triggers(game, trigger)
        card = game.find_by_id(exiled_id)
        if not isinstance(card, CardState):
            return
        if card.zone is not Zone.EXILE or card.zone_change_stamp != expected_stamp:
            return  # CR 603.7c: gone, or a new incarnation - not this card any more.
        if card.owner is None:
            return
        game.put_onto_battlefield(card, card.owner, tapped=False)

    return callback


def _dismiss_other_static_prison_triggers(game: "Game", trigger: DelayedTrigger) -> None:
    """Drop the sibling delayed triggers for the other two departure routes
    once one has fired - CR 603.7b's one-shot spends the whole ability, not
    just the one event that happened to occur first, and leaving a dead
    watcher behind risks a second, wrong return if the *returned* card is
    itself later destroyed and its own id happens to be reused... which
    `CardState.id` never does (this engine mutates rather than recycles), but
    tidiness matters here the same way it does for `_dismiss_other_earthbend_
    trigger`, which this mirrors exactly.
    """
    game.delayed_triggers.triggers = [
        candidate
        for candidate in game.delayed_triggers.triggers
        if candidate.id not in trigger.sibling_ids
    ]


def _watch_for_departure_and_return_exiled_card(
    game: "Game", source: CardState, exiled: CardState, controller: str
) -> None:
    """Create the delayed triggered ability CR 610.2 describes: whenever
    `source` (the exiling enchantment) leaves the battlefield, by any of the
    three routes a permanent actually leaves it in this engine, return
    `exiled` to the battlefield under its owner's control (CR 610.3c's usual
    default for a card this text names no other destination for).

    Three sibling `DelayedTrigger`s, not one - CR 603.7a's ability watches
    for one event ("leaves the battlefield") that this engine represents as
    three distinct `TriggerEvent`s (`DIES` covers both destruction and
    sacrifice, CR 700.4/701.21a's own graveyard-arrival event for either
    verb; `LEAVES_BATTLEFIELD_TO_EXILE` and `LEAVES_BATTLEFIELD_TO_HAND`
    cover the other two), the same one-ability-many-events shape earthbend's
    "dies or is put into exile" already uses for two events.
    """
    exile_stamp = exiled.zone_change_stamp
    callback = _static_prison_return_callback(exiled.id, exile_stamp)
    text = (
        f"When {source.name} leaves the battlefield, return {exiled.name} to "
        "the battlefield under its owner's control."
    )
    siblings: list[DelayedTrigger] = []
    for event in (
        TriggerEvent.DIES,
        TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE,
        TriggerEvent.LEAVES_BATTLEFIELD_TO_HAND,
    ):
        siblings.append(
            game.create_delayed_trigger(
                DelayedTrigger(
                    text=text,
                    event=event,
                    controller=controller,
                    source_id=source.id,
                    source_name=source.name,
                    subject_id=source.id,
                    callback=callback,
                )
            )
        )
    for trigger in siblings:
        trigger.sibling_ids = tuple(other.id for other in siblings if other is not trigger)


def _parse_exile_until_leaves_battlefield_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """Ability-only (`for_spell=False`): nothing in the pool prints this
    shape on a spell, and the "this `<type>`" pronoun needs a live source
    object on the battlefield to watch (`ability.source(game)`), which only
    an ability - never a spell resolving itself off the stack - carries.
    """
    if for_spell:
        return None
    match = _EXILE_UNTIL_THIS_LEAVES_BATTLEFIELD_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase")):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        targets = [
            target for target in game.resolve_targets(ability) if isinstance(target, CardState)
        ]
        if not targets:
            return  # CR 608.2b: the target is gone, so there is nothing to exile.
        source = ability.source(game)
        if source is None:
            return  # CR 113.7a: the source is already gone; nothing left to watch leave.
        exiled = game.exile_permanent(targets[0])
        if exiled.zone is not Zone.EXILE:
            return  # CR 111.8: a token refused the move; nothing to bring back later.
        _watch_for_departure_and_return_exiled_card(game, source, exiled, ability.controller)

    return effect


_EXILE_TARGET_RE = re.compile(r"exile (?P<phrase>(?:any target|.*target.+))", re.IGNORECASE)
#: "Counter target spell." - the unconditional shape (CR 701.5a) - and its
#: qualified cousins, "Counter target `<qualifier>` spell." (Force of
#: Negation's "noncreature", a colour word, a card type). The qualifier is
#: read and thrown away: `counter_targets` walks whatever the caster actually
#: targeted, and CR 601.2c/`machines/targeting.py` is what enforces the
#: restriction at announcement, not this dispatcher. Still refused: Mystic
#: Confluence's "Counter target spell unless its controller pays {3}." and
#: Cryptic Command's own "Counter target spell or ability." - the trailing `$`
#: refuses anything printed after "spell", rather than silently dropping a
#: condition the card actually has. Those two shapes get their own regexes
#: below (`_COUNTER_UNLESS_PAYS_RE`, `_COUNTER_TARGET_ABILITY_OR_SPELL_RE`)
#: instead of being folded in here.
_SPELL_QUALIFIER_WORD = (
    r"(?:non)?(?:creature|artifact|enchantment|land|planeswalker|instant|sorcery|battle"
    r"|white|blue|black|red|green|colorless|multicolored|monocolored)"
)
_COUNTER_TARGET_SPELL_RE = re.compile(
    rf"^counter target(?: {_SPELL_QUALIFIER_WORD})? spell\.?$", re.IGNORECASE
)
#: "Counter target spell unless its controller pays {N}." (CR 118.12a) -
#: Censor and Mystical Dispute. See `_counter_unless_pays_effect`.
_COUNTER_UNLESS_PAYS_RE = re.compile(
    r"^counter target spell unless its controller pays \{(?P<n>\d+)\}\.?$", re.IGNORECASE
)
#: "Counter target triggered ability or colorless spell." (Consign to
#: Memory) and the like - a compound target rather than a single qualified
#: noun, so `_COUNTER_TARGET_SPELL_RE` does not reach it. `counter_targets`
#: does not care which half of the "or" was actually targeted - see its own
#: docstring - so this only has to recognise the shape, not re-derive it.
_COUNTER_TARGET_ABILITY_OR_SPELL_RE = re.compile(
    r"^counter target (?:(?:activated|triggered)\s+)*abilit(?:y|ies) or "
    rf"(?:{_SPELL_QUALIFIER_WORD} )?spell\.?$",
    re.IGNORECASE,
)
#: "Counter target activated or triggered ability." (Repudiate) - CR 113.9's
#: plain ability-only shape, with no "or spell" tail at all (unlike
#: `_COUNTER_TARGET_ABILITY_OR_SPELL_RE`'s Consign to Memory/Cryptic Command
#: compound). `resolve_target`/`legal_target` already resolve a `TargetRef`
#: against an `AbilityOnStack` via `Game.find_ability_by_id` when
#: `find_by_id` finds no card (Tishana's Tidebinder is what built that path),
#: and `Game.counter` already accepts either kind of `StackObject`
#: (CR 113.9) - so `counter_targets` needs nothing new, only this regex to
#: reach it, the same way `_COUNTER_TARGET_ABILITY_OR_SPELL_RE` already does
#: for the compound shape.
_COUNTER_TARGET_ABILITY_RE = re.compile(
    r"^counter target (?:activated or triggered |activated |triggered )?"
    r"abilit(?:y|ies)\.?$",
    re.IGNORECASE,
)
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
#: Fling: "<Source> deals damage equal to the sacrificed creature's power to
#: any target." An additional-cost-bound amount, not `_DAMAGE_TARGET_RE`'s
#: literal number - `_COUNT` never matches the word "equal", so this needs
#: its own regex and its own resolution-time read of `Game.cast_record`'s
#: `additional_cost_cards` (CR 118.8a's "sacrifice a creature" additional
#: cost, CR 601.2h's payment already ran by the time this clause resolves).
_DAMAGE_EQUAL_TO_SACRIFICED_CREATURE_POWER_RE = re.compile(
    r"^.*\bdeals? damage equal to the sacrificed creature'?s power to "
    r"(?P<phrase>any target|.*target.+)\.?$",
    re.IGNORECASE,
)
#: Burst Lightning: "<Source> deals N damage to any target. If this spell was
#: kicked, it deals M damage instead." CR 702.33a/d's kicker, read at
#: resolution off `Game.cast_record(spell).kicked` the same way
#: `_parse_x_life_mass_debuff` already reads its own additional-cost X - two
#: sentences read whole (ahead of `parse_mixed_effect_for_spell`, which would
#: otherwise split the second one off and find no clause shape for it,
#: refusing the *first* sentence's plain damage along with it).
_DAMAGE_TARGET_KICKED_INSTEAD_RE = re.compile(
    r"^.*\bdeals? (?P<n>\d+) damage to (?P<phrase>any target|.*target.+?)\.\s*"
    r"if this spell was kicked, it deals (?P<kicked_n>\d+) damage instead\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_damage_target_kicked_instead_clause(effect_text: str) -> Effect | None:
    """`_DAMAGE_TARGET_KICKED_INSTEAD_RE`'s shape, or `None` if this is not it."""
    whole = _strip_non_effect_preamble(effect_text).strip()
    match = _DAMAGE_TARGET_KICKED_INSTEAD_RE.fullmatch(whole)
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), allow_player_targets=True):
        return None
    base = int(match.group("n"))
    kicked_amount = int(match.group("kicked_n"))

    def effect(game: "Game", spell: CardState) -> None:
        record = game.cast_record(spell)
        amount = kicked_amount if record.kicked > 0 else base
        for target in game.resolve_targets(spell):
            game.deal_damage(target, amount, source=spell)

    return effect


#: "Put N +1/+1 (or -1/-1) counters on target X." and Anafenza's "on
#: *another* target tapped creature you control" - the same reasoning as
#: `_TAP_UNTAP_TARGET_RE`. `kind` is any single lowercase word, not only the
#: two P/T kinds: CR 122.1 leaves a counter's name open ("charge", "fate",
#: whatever a card invents), and Oblivion Stone's "Put a fate counter on
#: target permanent" is exactly that - a named counter with no rules of its
#: own, put on by a plain activated ability this shape already reads once the
#: kind word is not pinned to the two P/T spellings.
_COUNTER_TARGET_RE = re.compile(
    rf"put (?P<n>{_COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on (?P<phrase>.*target.+)",
    re.IGNORECASE,
)
#: Swallow Whole: "Put a +1/+1 counter on the creature tapped to pay this
#: spell's additional cost." Not a target of this sentence at all (CR 118.8a:
#: the additional cost - "tap an untapped creature you control" - was chosen
#: and paid before the spell was even put on the stack, CR 601.2h), so
#: `_COUNTER_TARGET_RE`'s "target ..." shape does not match and should not:
#: this reads the same `Game.cast_record(spell).additional_cost_cards`
#: `_deal_damage_equal_to_sacrificed_creature_power` already reads for Fling.
#: The creature stays on the battlefield (only tapped, not sacrificed), so
#: `CardState.add_counters` reaches it directly with no zone lookup needed.
_COUNTER_ON_ADDITIONAL_COST_CARD_RE = re.compile(
    rf"^put (?P<n>{_COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on the "
    r"(?:creature|permanent|card) (?:tapped|sacrificed|exiled|discarded) to pay "
    r"this spell'?s additional cost\.?$",
    re.IGNORECASE,
)


def _parse_counter_on_additional_cost_card_clause(clause: str) -> TargetedClause | None:
    """`_COUNTER_ON_ADDITIONAL_COST_CARD_RE`'s shape, or `None` if not it."""
    match = _COUNTER_ON_ADDITIONAL_COST_CARD_RE.fullmatch(clause.strip())
    if match is None:
        return None
    amount = _count(match.group("n"))
    if amount is None:
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        record = game.cast_record(stack_object)
        if not record.additional_cost_cards:
            return
        card_state = game.find_by_id(record.additional_cost_cards[0])
        if card_state is not None:
            card_state.add_counters(kind, amount)

    return effect


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
#: Shatterskull Smashing: "deals X damage divided as you choose among up to
#: two target creatures and/or planeswalkers. If X is 6 or more, [Name] deals
#: twice X damage divided as you choose among them instead." Read whole, like
#: `_UNDERGROWTH_PUMP_AND_FIGHT_RE` above: "them" in the second sentence is
#: anaphoric (CR 400.7) for whatever the first sentence's target phrase named,
#: one CR 608.2c instruction across two sentences rather than something
#: `split_effect_clauses` could cut apart and still read. Tried on the
#: *unsubstituted* text (the literal word "x", never a caster's chosen
#: number) - `machines/targeting.py`'s own `Division.doubled_if_x_at_least`
#: reads the identical threshold for CR 601.2d's announcement, so the two
#: stay in lockstep without either one hard-coding the other's answer.
_X_DAMAGE_DIVIDED_DOUBLED_RE = re.compile(
    r"^.*\bdeals? x damage divided as you choose among "
    r"(?P<phrase>up to \S+ target[^.]+)\.\s*"
    r"if x is (?P<threshold>\d+) or more,.*deals twice x damage divided as you choose "
    r"among them instead\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_x_damage_divided_and_doubled_clause(text: str) -> Effect | None:
    """Shatterskull Smashing's own shape - see `_X_DAMAGE_DIVIDED_DOUBLED_RE`.

    X is read at resolution off `Game.cast_record` (CR 107.3a), doubled if it
    meets the printed threshold, and the total is paid out through the same
    `_deal_divided_damage_shares` `deal_divided_damage` uses - the caster's
    real CR 601.2d announcement (`spell.division`) if there is one, an even
    split otherwise.
    """
    whole = _strip_non_effect_preamble(text).strip()
    match = _X_DAMAGE_DIVIDED_DOUBLED_RE.fullmatch(whole)
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    threshold = int(match.group("threshold"))

    def effect(game: "Game", spell: CardState) -> None:
        x_value = game.cast_record(spell).x_value
        total = 2 * x_value if x_value >= threshold else x_value
        _deal_divided_damage_shares(game, spell, total)

    return effect


#: Valakut Awakening: "Put any number of cards from your hand on the bottom
#: of your library, then draw that many cards plus one." A linked quantity
#: (CR 608.2c): the draw count is not printed, it is whatever "that many" -
#: the number actually put on the bottom - turns out to be, plus one, so the
#: two halves cannot be two independent clauses.
_BOTTOM_HAND_THEN_DRAW_PLUS_ONE_RE = re.compile(
    r"^put any number of cards from your hand on the bottom of your library, "
    r"then draw that many cards plus one\.?$",
    re.IGNORECASE,
)


def _parse_bottom_hand_then_draw_plus_one_clause(text: str) -> Effect | None:
    """Valakut Awakening - see `_BOTTOM_HAND_THEN_DRAW_PLUS_ONE_RE`.

    CR 107.1c: "any number" runs zero upward, so the caster's own `CHOOSE_
    CARDS` answer (`exact=False`) may bottom nothing at all, in which case the
    spell still draws its own "plus one" card. Which cards go is CR 608.2d's
    plain choice, offered in hand order the way `discard_two_draw_two_
    create_token`'s own `CHOOSE_CARDS` question already is; putting one on the
    bottom is `Player.move`, the same call `puts_graveyard_on_bottom_of_
    library` makes for Endurance, with no shuffle (CR 701.24a's shuffle verb
    is never printed here) and no randomised order (unlike Endurance's "in a
    random order", this text names none, so the caster's own choice order is
    what lands on the bottom).
    """
    whole = _strip_non_effect_preamble(text).strip()
    if _BOTTOM_HAND_THEN_DRAW_PLUS_ONE_RE.fullmatch(whole) is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        hand = list(controller.hand)
        if hand:
            decision = Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt="put any number of cards from your hand on the bottom of your library",
                source=spell.name,
                amount=len(hand),
                cards=tuple(state.id for state in hand),
                exact=False,
            )
            chosen_ids = game.ask(decision)
        else:
            chosen_ids = ()
        by_id = {state.id: state for state in hand}
        bottomed = [by_id[card_id] for card_id in chosen_ids]
        for state in bottomed:
            controller.move(state, Zone.LIBRARY)
        game.draw_cards(controller.username, len(bottomed) + 1)

    return effect


#: Turntimber Symbiosis: "Look at the top seven cards of your library. You may
#: put a creature card from among them onto the battlefield. If that card has
#: mana value 3 or less, it enters with three additional +1/+1 counters on
#: it. Put the rest on the bottom of your library in a random order."
_LOOK_TOP_N_MAY_BATTLEFIELD_CREATURE_BONUS_RE = re.compile(
    r"^look at the top (?P<n>[\w-]+) cards? of your library\. "
    r"you may put a creature card from among them onto the battlefield\. "
    r"if that card has mana value (?P<threshold>\d+) or less, it enters with "
    r"(?P<bonus>[\w-]+) additional \+1/\+1 counters? on it\. "
    r"put the rest on the bottom of your library in a random order\.?$",
    re.IGNORECASE,
)


def _parse_look_top_n_may_battlefield_creature_bonus_clause(text: str) -> Effect | None:
    """Turntimber Symbiosis - see `_LOOK_TOP_N_MAY_BATTLEFIELD_CREATURE_
    BONUS_RE`. An impulsive-look shape close to `malevolent_rumble`'s "reveal
    the top four ... may put a permanent card into your hand ... put the rest
    into your graveyard" (CR 608.2d's plain "you may", `CHOOSE_CARDS` for
    *which* card among several candidates), but the destination for the kept
    card is the battlefield, not the hand, and the destination for the rest is
    the bottom of the library in a random order (CR 701.24a's shuffle verb is
    never printed here, so `Game.shuffle_library` is not called - the same
    non-shuffle randomisation `puts_graveyard_on_bottom_of_library` already
    uses for Endurance) rather than the graveyard.

    Put onto the battlefield through `Game.put_onto_battlefield` (CR 110.2a:
    no casting, so no "when you cast" trigger fires), then, only for the kept
    card and only if its own mana value is at or under the printed threshold,
    `CardState.add_counters(Counter.PLUS_ONE, bonus)` (CR 122.1a).
    """
    whole = _strip_non_effect_preamble(text).strip()
    match = _LOOK_TOP_N_MAY_BATTLEFIELD_CREATURE_BONUS_RE.fullmatch(whole)
    if match is None:
        return None
    n = _count(match.group("n"))
    threshold = int(match.group("threshold"))
    bonus = _count(match.group("bonus"))
    if n is None or bonus is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        looked = list(controller.library[:n])
        creatures = [state for state in looked if state.card.is_creature]
        chosen: CardState | None = None
        if creatures and game.may(
            controller.username, "put a creature card onto the battlefield", source=spell.name
        ):
            decision = Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt="choose a creature card to put onto the battlefield",
                source=spell.name,
                amount=1,
                cards=tuple(state.id for state in reversed(creatures)),
            )
            chosen_ids = game.ask(decision)
            by_id = {state.id: state for state in creatures}
            chosen = by_id[chosen_ids[0]]
        rest = [state for state in looked if state is not chosen]
        if chosen is not None:
            put = game.put_onto_battlefield(chosen, controller.username)
            if put.mana_value <= threshold:
                put.add_counters(Counter.PLUS_ONE, bonus)
        if rest:
            rng = Random(f"{game.shuffle_seed}:{game.shuffles_performed}:top-{n}-bottom")  # noqa: S311
            rng.shuffle(rest)
            for state in rest:
                controller.move(state, Zone.LIBRARY)
            game.shuffles_performed += 1

    return effect


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
#: "<Source> deals N damage to each creature." (Extinguisher Battleship) -
#: CR 119.3, also with no target: "each creature" is every creature on the
#: battlefield, not something chosen or a player group.
_DAMAGE_EACH_CREATURE_RE = re.compile(
    rf".*\bdeals? (?P<n>{_COUNT}) damage to each creature\.?$", re.IGNORECASE
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
#: "target opponent draws a card" (Thought-Knot Seer's leaves-the-battlefield
#: trigger), "target player <does something>" more generally - the plain
#: player-clause vocabulary `parse_clause_effect` already reads (a life
#: total, a draw, a mill, a scry, ...), run against whichever player this
#: clause names rather than the resolving spell's/ability's own controller.
#: Distinct from `_parse_target_player_mode`, which only ever runs for a
#: modal spell's own mode text and never reaches a triggered ability's plain
#: effect clause the way this one, wired into `_parse_targeted_clause`, does.
_TARGET_PLAYER_OR_OPPONENT_VERB_RE = re.compile(
    r"^target (?P<who>player|opponent) (?P<rest>.+)$", re.IGNORECASE
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
#: Psychotic Fury's own qualifier, "Target **multicolored** creature gains
#: double strike until end of turn." - an adjective sitting between "target"
#: and "creature" the way `_SPELL_QUALIFIER_WORD` already lets a counterspell
#: qualify "spell". `machines/targeting.py`'s `profile_for_text` already
#: reads "target multicolored creature" as a legal, colour-restricted
#: requirement at announcement (CR 601.2c) - this regex only recognises which
#: *shape* of resolution clause the text is, so widening it to admit one
#: qualifying word costs nothing: `create_continuous_effect` still gets its
#: targets from `Game.resolve_card_targets`, the already-validated
#: announcement, never from this match.
_CONTINUOUS_PUMP_OR_KEYWORD_RE = re.compile(
    r"^target (?:[a-z]+ )?creature (?:gets [+-]\d+/[+-]\d+|gains [a-z ]+) until end of turn\.?$",
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

    if (
        _COUNTER_TARGET_SPELL_RE.fullmatch(clause)
        or _COUNTER_TARGET_ABILITY_OR_SPELL_RE.fullmatch(clause)
        or _COUNTER_TARGET_ABILITY_RE.fullmatch(clause)
    ):
        # `counter_targets` walks the stack for a targeted spell (CR 608.2b)
        # and is only meaningful for a resolving *spell* - an ability naming
        # this shape does not turn up in the pool, and guessing at one would
        # be worse than refusing it.
        return counter_targets if for_spell else None

    if match := _COUNTER_UNLESS_PAYS_RE.fullmatch(clause):
        return _counter_unless_pays_effect(int(match.group("n"))) if for_spell else None

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

    exile_until_leaves = _parse_exile_until_leaves_battlefield_clause(clause, for_spell=for_spell)
    if exile_until_leaves is not None:
        return exile_until_leaves

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
        kind = _counter_kind(match.group("kind"))
        return put_counters_on_ability_targets(kind, amount)

    if for_spell and (match := _DAMAGE_EQUAL_TO_SACRIFICED_CREATURE_POWER_RE.fullmatch(clause)):
        if not _targets_understood(match.group("phrase"), allow_player_targets=True):
            return None
        return _deal_damage_equal_to_sacrificed_creature_power

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

    if match := _DAMAGE_EACH_CREATURE_RE.fullmatch(clause):
        # No target either (every creature on the battlefield, CR 119.3), and
        # `damage_each_creature` reads `ability.source`, which only an
        # `AbilityOnStack` has - the same ability-side-only shape as the
        # each-opponent clause just above.
        if for_spell:
            return None
        amount = _count(match.group("n"))
        return damage_each_creature(amount)  # type: ignore[return-value]

    if _PREVENT_ALL_COMBAT_DAMAGE_RE.fullmatch(clause):
        return prevent_all_combat_damage  # type: ignore[return-value]

    if match := _PREVENT_NEXT_DAMAGE_TO_TARGET_RE.fullmatch(clause):
        if not _targets_understood(match.group("phrase"), allow_player_targets=True):
            return None
        amount = _count(match.group("n"))
        return prevent_next_damage_to_target(amount)  # type: ignore[return-value]

    if match := _TARGET_PLAYER_OR_OPPONENT_VERB_RE.fullmatch(clause):
        if not _targets_understood(f"target {match.group('who')}", allow_player_targets=True):
            return None
        rest = match.group("rest").strip()
        clause_effect = parse_clause_effect(rest) or parse_clause_effect(f"you {rest}")
        if clause_effect is None:
            return None

        def player_verb_effect(game: "Game", stack_object: "StackObject") -> None:
            source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
            for target in game.resolve_targets(stack_object):
                if isinstance(target, Player):
                    clause_effect(game, target, source)

        return player_verb_effect

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
#   eternalize, Caretaker's Talent, Tamiyo's -X) needs the copied object's
#   copiable values (CR 707.2), which this parser does not read off anything -
#   checked for and refused before the noun-phrase regex is even tried, so it
#   cannot be mistaken for one. Ocelot Pride's own "for each token you control
#   that entered this turn, create a token that's a copy of it" is the one
#   copy shape this file *does* read - `_parse_city_blessing_token_copy_clause`,
#   below the token-clause section, matches that exact templated shape
#   (CR 702.131's ascend / the city's blessing) and reads the copy through
#   `token_copy_of` (CR 707.2) rather than through this parser.
# - **A count this parser cannot read as a fixed number** - Hangarback
#   Walker's "for each +1/+1 counter on this creature", Seasoned Pyromancer's
#   "for each nonland card discarded this way" - is not a `_COUNT` word at
#   all, so `_TOKEN_CLAUSE_RE` simply does not match text of that shape;
#   nothing silently falls back to a count of one.
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

#: "N" keyword abilities: CR 702.189a - "Firebending is a triggered ability.
#: 'Firebending N' means 'Whenever this creature attacks, add N {R}. Until end
#: of combat, you don't lose this mana as steps and phases end.'" The Legend
#: of Roku's `{8}` ability grants exactly this on the Dragon token it creates.
#: Recorded on the token as a plain keyword string - the same shape
#: `_TOKEN_KEYWORDS` already stores a bare keyword under - rather than as a
#: real triggered ability: nothing in `machines/triggers.py` fires it, so a
#: token with "Firebending 4" attacks without ever adding the mana. That gap
#: is left open rather than guessed at (`docs/engine-coverage.md`); what this
#: wave fixes is that the token itself, and its other keyword (flying), are
#: created at all, which used to fail the whole clause and create nothing.
_LEVELED_TOKEN_KEYWORDS = {"firebending"}


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
    if not parts:
        return None
    keywords: list[str] = []
    for part in parts:
        lowered = part.lower()
        if lowered in _TOKEN_KEYWORDS:
            keywords.append(part.title())
            continue
        leveled = re.fullmatch(r"(?P<word>[a-z]+) (?P<n>\d+)", lowered)
        if leveled is not None and leveled.group("word") in _LEVELED_TOKEN_KEYWORDS:
            keywords.append(f"{leveled.group('word').title()} {leveled.group('n')}")
            continue
        return None
    return tuple(keywords), None


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


def _resolve_modal_triggered_ability_clause(text: str) -> AbilityEffect | None:
    """A modal *triggered* ability's own "choose one/two -" tail (CR 700.2,
    603.3c) - Elder Gargaroth's "attacks or blocks, choose one -" is the only
    printing in the pool.

    Unlike `resolve_modal_spell`, there is no `Casting`/`CastRecord` here:
    CR 603.3c puts the mode choice "as part of putting that ability on the
    stack", a moment this project's engine does not yet have a hook for (see
    `docs/engine-coverage.md`) - `Game.put_triggers_on_stack` chooses a
    triggered ability's *targets* at that moment (CR 603.3d) but not its
    modes. This reads the choice at **resolution** instead, one step later
    than the rule places it, which only matters if something could observe
    the ability sitting on the stack with its mode not yet chosen (nothing in
    the pool does) - `DecisionKind.CHOOSE_A_MODE` is new this wave, so the
    ability's controller may need to answer it live in a real game; see this
    wave's report.

    Only a plain "choose one" is read - `ModalProfile.allowed_range` other
    than `(1, 1)` (Spree's per-mode costs, "choose one or more", pawprint)
    leaves `profile.understood` False and this returns `None`, the same
    fail-closed default every other unreadable modal shape gets.

    `text` arrives whitespace-collapsed - `machines/abilities._strip_reminder`
    runs `re.sub(r"\\s+", " ", ...)` on every printed line, `TriggeredAbility.
    effect` included, which flattens the real newlines `_merge_modal_bullet_
    lines` had just reassembled to keep the bullets attached to this ability
    in the first place. `machines/modes._parse` reads bullets by
    `splitlines()`, one `•` per line (CR 700.2's own printed shape), so those
    newlines are put back here, right before each `•` marker, rather than
    teaching two different modules two different bullet grammars.
    """
    text = re.sub(r"\s*•\s*", "\n• ", text).strip()
    if not is_modal_text(text):
        return None
    profile = modal_profile_from_text(text)
    if profile is None or not profile.understood or not profile.modes:
        return None
    if profile.allowed_range() != (1, 1):
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        options = tuple(mode.text for mode in profile.modes)
        chosen_text = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_A_MODE,
                player=ability.controller,
                prompt="choose one",
                source=ability.source_name,
                options=options,
            )
        )
        mode = next((m for m in profile.modes if m.text == chosen_text), profile.modes[0])
        clause = parse_mixed_effect(mode.text)
        if clause is None:
            game.mode_notices.append(
                ModeNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    mode_number=mode.number,
                    text=mode.text,
                )
            )
            return
        clause(game, ability)

    return effect


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
    r"(?P<basic_land_type> with a basic land type)?"
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


#: Craterous Stomp's own shape: "<Name> deals N damage to target creature an
#: opponent controls. Each other creature that player controls becomes a
#: `<type>` in addition to its other types and gains \"`<ability text>`.\""
#: `_ANAPHORIC_SUBJECT_RE`/`_unreadable_anaphoric_clause` only recognise "that
#: player"/"its controller" as the *whole* subject of the second sentence
#: (Solitude's "That creature's controller gains life...") - here the
#: back-reference sits mid-clause ("each other creature *that player*
#: controls"), CR 400.7's same anaphora in a shape neither regex reads, so
#: the pair never even reached the notice path and the whole two-sentence
#: instruction (damage included) was silently doing nothing. Read whole,
#: ahead of `parse_mixed_effect_for_spell`: recognising the templated shape
#: is enough to record a proper `AnaphoricClauseNotice` instead. Building the
#: effect for real needs two things this engine does not have anywhere else -
#: a *group* continuous type-and-ability grant fixed off an anaphoric
#: referent's controller (CR 611.2c), and blocking-restriction enforcement
#: for a granted "can't block `<creature type>`" ability
#: (`machines/combat.py` only reads a printed attacker-side "can't be
#: blocked by ..." restriction today, see `test_evasion_restrictions.py`) -
#: so this fails the whole paragraph closed (CR 608.2c: no notion of running
#: half an instruction; the damage does not fire either) rather than
#: half-execute the damage alone. See `docs/engine-coverage.md`.
_DAMAGE_THEN_GROUP_TYPE_ABILITY_GRANT_RE = re.compile(
    r"^.*\bdeals? \d+ damage to target creature an opponent controls\.\s*"
    r"each other creature that player controls becomes an? [a-z]+ in addition to its "
    r'other types and gains "[^"]+\."\.?$',
    re.IGNORECASE | re.DOTALL,
)


#: "Flashback" (the spell, not the keyword): "Target instant or sorcery card
#: in your graveyard gains flashback until end of turn. The flashback cost
#: is equal to its mana cost." CR 702.34a's keyword is two static abilities
#: this engine builds nothing for as a *granted* ability - `machines/casting.
#: keyword_cast_options`/`_keyword` only ever read a keyword printed on the
#: `Card` itself, never one a resolving spell handed out at runtime, and
#: `Card` is deliberately immutable (see this module's own header comment on
#: `docs/` conventions) so there is nowhere on the object to stamp a granted
#: keyword even if `keyword_cast_options` did look for one.
#:
#: The *observable* effect is close enough to CR 601.3's ordinary "you may
#: cast/play [that card] this turn" permission - which **is** built, as
#: `machines/casting.PlayPermission`/`Game.grant_play_permission` - that this
#: reuses it rather than the keyword machinery: `zone=Zone.GRAVEYARD` lets
#: the permission reach a card that never left the graveyard,
#: `pays_mana_cost=True` matches "the flashback cost is equal to its mana
#: cost" exactly. **One real gap stays open**: CR 702.34a's "then exile it
#: instead of putting it anywhere else" only fires off `CastRecord.keyword ==
#: "flashback"` (`machines/casting.py`'s own exile-replacement check), which
#: a `PlayPermission`-driven cast never sets - the card resolves and goes to
#: its owner's graveyard the ordinary way rather than being exiled. Recorded
#: here rather than silently guessed away; see `docs/engine-coverage.md`.
_GRANT_FLASHBACK_RE = re.compile(
    r"^(?P<phrase>target instant or sorcery card in your graveyard) gains flashback "
    r"until end of turn\.\s*the flashback cost is equal to its mana cost\.?$",
    re.IGNORECASE,
)


def _parse_grant_flashback_clause(effect_text: str) -> Effect | None:
    """`_GRANT_FLASHBACK_RE`'s shape, or `None` if this is not it."""
    match = _GRANT_FLASHBACK_RE.fullmatch(effect_text.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), battlefield_only=False):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        for target in game.resolve_targets(spell):
            if isinstance(target, CardState) and target.zone is Zone.GRAVEYARD:
                game.grant_play_permission(
                    target,
                    controller.username,
                    action=PlayAction.CAST,
                    pays_mana_cost=True,
                    source_name=spell.name,
                    zone=Zone.GRAVEYARD,
                    rule="CR 601.3",
                )

    return effect


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


#: "Sacrifice this <type> unless you pay {E}[{E}...]." (Static Prison) - a
#: fixed-amount CR 107.14/118.3 energy cost that averts the sacrifice rather
#: than causing a bonus. Only the self-referential "this <type>" subject is
#: read, the same restriction `machines/cost.py`'s `_PHRASE_EXERT_SELF` and
#: `_COUNTER_SELF_SUBJECT` hold their own self-referential cost shapes to - a
#: printed cost naming some other permanent would need target resolution this
#: template does not have.
_SACRIFICE_UNLESS_PAY_ENERGY_RE = re.compile(
    r"^sacrifice this (?:creature|permanent|artifact|enchantment|planeswalker|land) "
    r"unless you pay (?P<e>(?:\{e\})+)\.?$",
    re.IGNORECASE,
)


def _parse_sacrifice_unless_pay_energy(text: str) -> AbilityEffect | None:
    """CR 107.14, CR 118.3: "Sacrifice this <type> unless you pay {E}...",
    read off the ability's own printed text (Static Prison's upkeep trigger).

    `Game.may_pay_energy` is the same fixed-amount question `may_pay_life`
    already asks for CR 119.4's life-total floor, turned the other way round:
    paying is what avoids the sacrifice, so a "no" - declined, or illegal for
    lack of energy - sacrifices the source instead of doing nothing.
    """
    match = _SACRIFICE_UNLESS_PAY_ENERGY_RE.fullmatch(text.strip())
    if match is None:
        return None
    amount = len(re.findall(r"\{e\}", match.group("e"), re.IGNORECASE))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        player = game.player(ability.controller)
        paid = game.may_pay_energy(player, amount, source=ability.source_name)
        if not paid:
            game.sacrifice(source)

    return effect


#: Grist, the Hunger Tide's `+1`, read whole: "Create a 1/1 black and green
#: Insect creature token, then mill a card. If an Insect card was milled this
#: way, put a loyalty counter on this permanent and repeat this process." -
#: the token descriptor is read the same way `_parse_generic_token_descriptor`
#: reads any other, so only the mill-then-repeat half is templated here.
#: Grist's own name has already become "this permanent" by the time this
#: runs (`_self_normalized_effect_text`).
_CREATE_TOKEN_MILL_REPEAT_RE = re.compile(
    r"^create (?P<n>a|one) (?P<desc>.+?) tokens?, then mill a card\. "
    r"if an? (?P<kind>[a-z]+) card was milled this way, "
    r"put a loyalty counter on this permanent and repeat this process\.?$",
    re.IGNORECASE,
)


def _parse_create_token_mill_repeat_clause(text: str) -> AbilityEffect | None:
    """`_CREATE_TOKEN_MILL_REPEAT_RE`'s shape - Grist, the Hunger Tide's `+1`.

    CR 118.4's own "repeat this process" reads here as an ordinary Python loop
    inside one resolution, not a second stack object (nothing in CR 603.12
    covers "repeat" the way it covers "when you do") - each pass creates one
    token, mills one card, and only continues if *that* card was the named
    subtype (CR 205.3, checked against the card's own printed subtypes, since
    a card in the graveyard carries no continuous effect to compute a layer 4
    change from). The loop terminates on its own: `_mill` mills nothing once
    the library is empty (CR 701.17a's "as many ... as possible"), which reads
    here as "no card was milled", never true to the "if" condition.
    """
    match = _CREATE_TOKEN_MILL_REPEAT_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    words = match.group("desc").strip().split()
    definition = _parse_generic_token_descriptor(words, None)
    if definition is None:
        return None
    kind_word = match.group("kind").strip()

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.player(ability.controller)
        while True:
            create_tokens(game, definition, player.username, 1)
            milled = _mill(game, player, 1)
            if not milled or kind_word.lower() not in {s.lower() for s in milled[0].card.subtypes}:
                return
            source = ability.source(game)
            if source is not None and source.zone is Zone.BATTLEFIELD:
                game.add_counters(source, Counter.LOYALTY, 1)

    return effect


#: Tyvar, Jubilant Brawler's `-2`, read whole: "Mill three cards, then you may
#: return a creature card with mana value 2 or less from your graveyard to
#: the battlefield." - a resolution-time choice among candidates (CR 608.2d),
#: not a "target" at all, the same shape `_bring_in_from_outside_the_game_or_
#: exile`'s `DecisionKind.CHOOSE_CARDS` already reads for Karn's `-2`.
_MILL_THEN_MAY_RETURN_CREATURE_RE = re.compile(
    rf"^mill (?P<n>{_COUNT}) cards?, then you may return a creature card "
    r"with mana value (?P<max_mv>\d+) or less from your graveyard "
    r"to the battlefield\.?$",
    re.IGNORECASE,
)


def _parse_mill_then_may_return_creature_clause(text: str) -> AbilityEffect | None:
    """`_MILL_THEN_MAY_RETURN_CREATURE_RE`'s shape - Tyvar, Jubilant
    Brawler's `-2`.

    The candidate pool is read *after* the mill, so a creature this same
    resolution just put into the graveyard is itself eligible - CR 400.2's
    graveyard has no "just arrived" exception, and the sentence names no
    other timing. `Game.may` is asked only once a legal candidate actually
    exists (CR 608.2d), matching `_bring_in_from_outside_the_game_or_exile`'s
    own guard.
    """
    match = _MILL_THEN_MAY_RETURN_CREATURE_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    count = _count(match.group("n"))
    ceiling = int(match.group("max_mv"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.player(ability.controller)
        _mill(game, player, count)
        candidates = [
            state
            for state in player.cards_in(Zone.GRAVEYARD)
            if Type.CREATURE in state.card.types and (state.card.cmc or 0) <= ceiling
        ]
        if not candidates:
            return
        if not game.may(
            player,
            f"return a creature card with mana value {ceiling} or less from your "
            f"graveyard to the battlefield",
            source=ability.source_name,
        ):
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt="choose a creature card to return to the battlefield",
                source=ability.source_name,
                amount=1,
                cards=tuple(candidate.id for candidate in candidates),
            )
        )
        assert isinstance(chosen_ids, tuple)
        by_id = {candidate.id: candidate for candidate in candidates}
        chosen = by_id[chosen_ids[0]]
        game.put_onto_battlefield(chosen, player.username)

    return effect


#: "Mill N cards. You may put a land card from among them into your hand." -
#: Six's own attack trigger. "From among them" (CR 701.17c: a milled card is
#: findable in the graveyard it moved to) narrows the candidate pool to the
#: cards *this* mill just moved - not every land already in the graveyard -
#: unlike `_MILL_THEN_MAY_RETURN_CREATURE_RE`'s "from your graveyard", which
#: reads the whole pile.
_MILL_THEN_MAY_PUT_LAND_IN_HAND_RE = re.compile(
    rf"^mill (?P<n>{_COUNT}) cards?\.\s*"
    r"you may put a land card from among them into your hand\.?$",
    re.IGNORECASE,
)


def _parse_mill_then_may_put_land_in_hand_clause(text: str) -> AbilityEffect | None:
    """`_MILL_THEN_MAY_PUT_LAND_IN_HAND_RE`'s shape - Six's whole attack
    trigger (CR 701.17a's mill, CR 701.17c's "among them", CR 608.2d's may).
    """
    match = _MILL_THEN_MAY_PUT_LAND_IN_HAND_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    count = _count(match.group("n"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.player(ability.controller)
        milled = _mill(game, player, count)
        candidates = [state for state in milled if Type.LAND in state.card.types]
        if not candidates:
            return
        if not game.may(
            player,
            "put a land card from among them into your hand",
            source=ability.source_name,
        ):
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt="choose a land card to put into your hand",
                source=ability.source_name,
                amount=1,
                cards=tuple(candidate.id for candidate in candidates),
            )
        )
        assert isinstance(chosen_ids, tuple)
        by_id = {candidate.id: candidate for candidate in candidates}
        chosen = by_id[chosen_ids[0]]
        if chosen.zone is Zone.GRAVEYARD:
            player.move(chosen, Zone.HAND)

    return effect


#: "Transform this creature." / "Transform this permanent." - CR 701.27a's
#: self-referential form, the only one the werewolves and their cousins print
#: on the ability that does it. A clause naming some *other* permanent
#: ("transform target creature") needs target resolution this template does not
#: have and is deliberately not matched, the same restriction
#: `_SACRIFICE_UNLESS_PAY_ENERGY_RE` above holds itself to.
_TRANSFORM_SELF_RE = re.compile(
    r"^transform this (?:creature|permanent|artifact|enchantment|planeswalker|land|token)\.?$",
    re.IGNORECASE,
)


#: "you may exile <this object's name>, then return him/her/it/them to the
#: battlefield[ tapped][ transformed] under his/her/its/their owner's control."
#: - Ajani, Nacatl Pariah's Cats-die trigger, and the same self-referential
#: blink idiom wherever else it is printed. The targeted twin is
#: `_RETURN_TO_BATTLEFIELD_RE` above, which reads "exile *target* X, then
#: return it ..."; this one names its own object instead (CR 201.5: "text that
#: refers to the object it's on by name means just that particular object"), so
#: there is no target and CR 608.2b's recheck has nothing to check.
#:
#: The control clause is required, exactly as it is for the targeted shape: a
#: bare "return him to the battlefield" names no controller, and CR 110.2a
#: leaves that to the effect, which one regex on one sentence cannot decide.
_MAY_EXILE_SELF_THEN_RETURN_RE = re.compile(
    r"^you may exile (?P<name>[^,]+), then return (?:it|him|her|them)"
    r" to the battlefield"
    r"(?P<tapped> tapped)?"
    r"(?P<transformed> transformed)?"
    r" under (?:its|his|her|their) owner's control\.?$",
    re.IGNORECASE,
)


def _parse_may_exile_self_then_return_clause(text: str) -> AbilityEffect | None:
    """ "You may exile <this>, then return it to the battlefield transformed
    under its owner's control." as one CR 608.2c instruction.

    Ajani, Nacatl Pariah's "Whenever one or more other Cats you control die"
    trigger, read off its own printed text with no registry row. Two rules make
    it one instruction rather than two:

    - CR 201.5 - the name is a reference to the very object the ability is on,
      so the exile needs no target and no choice of what to exile.
    - CR 712.14a - "transformed" describes how it *enters*, which is why the
      return goes through `Game.put_onto_battlefield(transformed=True)` rather
      than transforming the permanent afterwards: CR 306.5b's loyalty counters
      are put on as it enters, and read off the face that is up.

    The "you may" is `DecisionKind.MAY` (CR 608.2d), the same shape
    `_parse_conditional_sacrifice_clause` uses. Declining does nothing at all;
    accepting runs both halves or, if CR 111.8 refuses the exile for a token,
    neither - never the exile alone, which would be strictly worse than doing
    nothing (the trap `_LOOKS_LIKE_RETURN_TO_BATTLEFIELD_RE` exists for).
    """
    match = _MAY_EXILE_SELF_THEN_RETURN_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    named = match.group("name").strip()
    tapped = match.group("tapped") is not None
    transformed = match.group("transformed") is not None
    prompt = f"exile {named}, then return {'it' if not transformed else 'it transformed'}"

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        # CR 201.5: the name means *this* object. A source whose name has
        # nothing to do with the printed one is not what this sentence is
        # about, so nothing happens rather than the wrong permanent blinking.
        if named.lower() not in (source.name or "").lower():
            return
        decision = Decision(
            kind=DecisionKind.MAY,
            player=ability.controller,
            prompt=prompt,
            source=ability.source_name,
            affirmative_is_legal=True,
        )
        if not game.ask(decision):
            return
        exiled = game.exile_permanent(source)
        if exiled.zone is not Zone.EXILE:
            return  # CR 111.8: a token refused the move; nothing to return.
        owner = exiled.owner or ability.controller
        game.put_onto_battlefield(exiled, owner, tapped=tapped, transformed=transformed)

    return effect


def _parse_transform_clause(text: str) -> AbilityEffect | None:
    """CR 701.27a: "To transform a permanent, turn it over so that its other
    face is up", read off the ability's own printed text.

    Duskwatch Recruiter's "At the beginning of each upkeep, if no spells were
    cast last turn, transform this creature." and Krallenhorde Howler's mirror
    on the back face both reach this, with no per-card row: the CR 603.4
    intervening *if* is checked by `machines/triggers.py` before the ability
    ever triggers, so all this clause has to do is the turning over.

    CR 712.9 limits transforming to a permanent represented by a double-faced
    card or token, and `CardState.transform` enforces that itself - a
    single-faced permanent told to transform does nothing (CR 701.28c's
    wording for the sibling action). The source having left the battlefield is
    the other no-op: CR 701.27a turns a *permanent* over.
    """
    if _TRANSFORM_SELF_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        source.transform()

    return effect


#: Ajani, Nacatl Avenger's `−4`: "Each opponent chooses an artifact, a
#: creature, an enchantment, and a planeswalker from among the nonland
#: permanents they control, then sacrifices the rest." A "choose one of each
#: of N types, sacrifice everything else" shape, generalised on the type list
#: rather than keyed to this one card - any future ability phrasing the
#: identical sentence with a different mix of types reads the same way.
_EACH_OPPONENT_CHOOSE_ONE_OF_EACH_TYPE_THEN_SACRIFICE_RE = re.compile(
    r"^each opponent chooses (?P<phrase>.+) from among the nonland permanents "
    r"they control, then sacrifices the rest\.?$",
    re.IGNORECASE,
)
#: One item of the comma/"and"-separated list: "an artifact", "a creature".
_TYPE_ITEM_RE = re.compile(r"^an?\s+(?P<type>[a-z]+)$", re.IGNORECASE)


def _parse_each_opponent_choose_one_of_each_type_then_sacrifice(
    text: str,
) -> AbilityEffect | None:
    """See `_EACH_OPPONENT_CHOOSE_ONE_OF_EACH_TYPE_THEN_SACRIFICE_RE`.

    CR 101.4/601.7a-style "each opponent" choices are each that opponent's
    own (not Ajani's controller's) - `Decision.player=opponent.username` for
    every question this asks, one `CHOOSE_CARDS` per type per opponent, over
    that opponent's *own* nonland permanents. A permanent already claimed for
    an earlier type in the list cannot be claimed again (CR 601.2c's "the same
    target can't be chosen multiple times" logic, applied to a choice rather
    than a target): a creature that is also, say, an artifact could otherwise
    be "kept" twice and let one more permanent slip past the sacrifice.

    An opponent controls zero of a given type keeps nothing of that type
    (CR 107.1a: there is no zero-permanent "artifact" to choose) - the
    question is not even asked, rather than raising or defaulting to some
    other permanent. Everything that ends up unclaimed is then sacrificed
    (CR 701.21a), each by its own controller, in one batch per opponent -
    APNAP order (CR 101.4) is not relevant to what any one opponent's own
    sacrifice contains, only to the order the opponents are asked in, which
    this reads off `game.players_in_game`'s existing turn order.
    """
    whole = _strip_non_effect_preamble(text).strip()
    match = _EACH_OPPONENT_CHOOSE_ONE_OF_EACH_TYPE_THEN_SACRIFICE_RE.fullmatch(whole)
    if match is None:
        return None
    items = [
        item.strip()
        for item in re.split(r",\s*(?:and\s+)?|\s+and\s+", match.group("phrase"))
        if item.strip()
    ]
    if not items:
        return None
    types: list[Type] = []
    for item in items:
        item_match = _TYPE_ITEM_RE.match(item)
        if item_match is None:
            return None
        try:
            types.append(Type(item_match.group("type").lower()))
        except ValueError:
            return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        for opponent in _opponents(game, ability.controller):
            nonland = [
                permanent
                for permanent in game.permanents_controlled_by(opponent.username)
                if Type.LAND not in permanent.types
            ]
            keep: set[UUID] = set()
            for card_type in types:
                candidates = [
                    permanent
                    for permanent in nonland
                    if card_type in permanent.types and permanent.id not in keep
                ]
                if not candidates:
                    # CR 107.1a: no such permanent to choose, so none of this
                    # type is kept - not a required-but-unmet choice.
                    continue
                article = "an" if card_type.value[0] in "aeiou" else "a"
                decision = Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=opponent.username,
                    prompt=f"choose {article} {card_type.value} to keep",
                    source=ability.source_name,
                    amount=1,
                    cards=tuple(permanent.id for permanent in candidates),
                )
                chosen_ids = game.ask(decision)
                keep.add(chosen_ids[0])
            for permanent in nonland:
                if permanent.id in keep:
                    continue
                if permanent.zone is Zone.BATTLEFIELD:
                    game.sacrifice(permanent)

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
    modal_triggered = _resolve_modal_triggered_ability_clause(effect_text)
    if modal_triggered is not None:
        return modal_triggered
    outside_the_game = _parse_outside_the_game_fetch(effect_text)
    if outside_the_game is not None:
        return outside_the_game
    undergrowth_pump_and_fight = _parse_undergrowth_pump_and_fight_clause(effect_text)
    if undergrowth_pump_and_fight is not None:
        return undergrowth_pump_and_fight
    each_opponent_choose_then_sacrifice = (
        _parse_each_opponent_choose_one_of_each_type_then_sacrifice(effect_text)
    )
    if each_opponent_choose_then_sacrifice is not None:
        return each_opponent_choose_then_sacrifice
    conditional_sacrifice = _parse_conditional_sacrifice_clause(effect_text, for_spell=False)
    if conditional_sacrifice is not None:
        return conditional_sacrifice
    reflexive_sacrifice = _parse_reflexive_sacrifice_clause(effect_text)
    if reflexive_sacrifice is not None:
        return reflexive_sacrifice
    reflexive_pay_energy = _parse_reflexive_pay_energy_clause(effect_text)
    if reflexive_pay_energy is not None:
        return reflexive_pay_energy
    reflexive_mandatory_token = _parse_reflexive_mandatory_token_clause(effect_text)
    if reflexive_mandatory_token is not None:
        return reflexive_mandatory_token
    create_token_then_may_attach = _parse_create_token_then_may_attach_clause(effect_text)
    if create_token_then_may_attach is not None:
        return create_token_then_may_attach
    dalkovan_attack_tokens = _parse_attack_this_turn_create_tapped_attacking_tokens(effect_text)
    if dalkovan_attack_tokens is not None:
        return dalkovan_attack_tokens
    mana_adding = _parse_mana_adding_trigger(effect_text)
    if mana_adding is not None:
        return mana_adding
    transform_self = _parse_transform_clause(effect_text)
    if transform_self is not None:
        return transform_self
    exile_self_then_return = _parse_may_exile_self_then_return_clause(effect_text)
    if exile_self_then_return is not None:
        return exile_self_then_return
    sacrifice_unless_energy = _parse_sacrifice_unless_pay_energy(effect_text)
    if sacrifice_unless_energy is not None:
        return sacrifice_unless_energy
    destroy_each_then_remove_counters = _parse_destroy_each_then_remove_all_counters(effect_text)
    if destroy_each_then_remove_counters is not None:
        return destroy_each_then_remove_counters
    destroy_each = _parse_destroy_each_clause(_strip_non_effect_preamble(effect_text).strip())
    if destroy_each is not None:
        return destroy_each
    put_counters_on_group = _parse_put_counters_on_group_clause(effect_text)
    if put_counters_on_group is not None:
        return put_counters_on_group
    put_counters_on_self = _parse_put_counters_on_self_clause(effect_text)
    if put_counters_on_self is not None:
        return put_counters_on_self
    adapt = _parse_adapt_clause(effect_text)
    if adapt is not None:
        return adapt
    double_counters_on_group = _parse_double_counters_on_group_clause(effect_text)
    if double_counters_on_group is not None:
        return double_counters_on_group
    defending_player_reveals_top_land = _parse_defending_player_reveals_top_conditional_land_clause(
        effect_text
    )
    if defending_player_reveals_top_land is not None:
        return defending_player_reveals_top_land
    untap_self = _parse_untap_self_clause(effect_text)
    if untap_self is not None:
        return untap_self
    remove_time_counter_self = _parse_remove_time_counter_from_self_clause(effect_text)
    if remove_time_counter_self is not None:
        return remove_time_counter_self
    whole_text_token = _parse_whole_text_token_clause(effect_text)
    if whole_text_token is not None:
        return whole_text_token
    exile_reflexive_creature_counter = _parse_exile_target_card_reflexive_creature_counter(
        effect_text
    )
    if exile_reflexive_creature_counter is not None:
        return exile_reflexive_creature_counter
    create_token_mill_repeat = _parse_create_token_mill_repeat_clause(effect_text)
    if create_token_mill_repeat is not None:
        return create_token_mill_repeat
    mill_then_may_return_creature = _parse_mill_then_may_return_creature_clause(effect_text)
    if mill_then_may_return_creature is not None:
        return mill_then_may_return_creature
    mill_then_may_put_land_in_hand = _parse_mill_then_may_put_land_in_hand_clause(effect_text)
    if mill_then_may_put_land_in_hand is not None:
        return mill_then_may_put_land_in_hand
    damage_to_that_spells_controller = _parse_damage_to_that_spells_controller_clause(effect_text)
    if damage_to_that_spells_controller is not None:
        return damage_to_that_spells_controller
    pump_per_discard_then_delayed_draw = _parse_pump_per_discard_then_delayed_draw_clause(
        effect_text
    )
    if pump_per_discard_then_delayed_draw is not None:
        return pump_per_discard_then_delayed_draw
    each_opponent_skips_next_untap = _parse_each_opponent_skips_next_untap_clause(effect_text)
    if each_opponent_skips_next_untap is not None:
        return each_opponent_skips_next_untap
    hideaway = _parse_hideaway_clause(effect_text)
    if hideaway is not None:
        return hideaway
    hideaway_counter_then_free_cast = _parse_hideaway_counter_then_conditional_free_cast_clause(
        effect_text
    )
    if hideaway_counter_then_free_cast is not None:
        return hideaway_counter_then_free_cast
    target_opponent_draw_then_copy = _parse_target_opponent_draw_then_copy_that_spell_clause(
        effect_text
    )
    if target_opponent_draw_then_copy is not None:
        return target_opponent_draw_then_copy
    create_token_then_copy_spell_retargeted = _parse_create_token_then_copy_spell_retargeted_clause(
        effect_text
    )
    if create_token_then_copy_spell_retargeted is not None:
        return create_token_then_copy_spell_retargeted
    pay_any_life_then_draw = _parse_pay_any_life_then_draw_that_many_clause(effect_text)
    if pay_any_life_then_draw is not None:
        return pay_any_life_then_draw
    each_opponent_loses_life = _parse_each_opponent_loses_life_equal_to(effect_text)
    if each_opponent_loses_life is not None:
        return each_opponent_loses_life
    mass_pump = _mass_pump_ability_effect(effect_text)
    if mass_pump is not None:
        return mass_pump
    tap_then_no_untap = _parse_tap_target_then_no_untap_clause(effect_text)
    if tap_then_no_untap is not None:
        return tap_then_no_untap
    move_counter = _parse_move_counter_clause(effect_text)
    if move_counter is not None:
        return move_counter
    pump_and_becomes_chosen_color = _parse_pump_and_becomes_chosen_color_clause(effect_text)
    if pump_and_becomes_chosen_color is not None:
        return pump_and_becomes_chosen_color
    protection_from_chosen_color = _parse_protection_from_chosen_color_clause(effect_text)
    if protection_from_chosen_color is not None:
        return protection_from_chosen_color
    put_exiled_target_onto_battlefield = _parse_put_exiled_target_onto_battlefield_clause(
        effect_text
    )
    if put_exiled_target_onto_battlefield is not None:
        return put_exiled_target_onto_battlefield
    hideaway_play = _parse_hideaway_play_clause(effect_text)
    if hideaway_play is not None:
        return hideaway_play
    token_copy_of_cost_exiled_card = _parse_create_token_copy_of_cost_exiled_card_clause(
        effect_text
    )
    if token_copy_of_cost_exiled_card is not None:
        return token_copy_of_cost_exiled_card
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

    unread_reflexive = _unreadable_reflexive_clause(effect_text)
    if unread_reflexive is not None:

        def reflexive_notice_only(game: "Game", ability: AbilityOnStack) -> None:
            game.reflexive_clause_notices.append(
                ReflexiveClauseNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=unread_reflexive,
                )
            )

        return reflexive_notice_only

    return None


#: "Choose target creature or planeswalker. You get {E}{E}{E} (three energy
#: counters), then you may pay any amount of {E}. `<name>` deals that much
#: damage to that permanent." (Galvanic Discharge) - CR 107.14/118.3's
#: variable-amount energy payment, referenced downstream by a damage clause
#: none of `_parse_targeted_clause`'s fixed-number shapes can read ("that
#: much" is not a literal number). Read whole, ahead of `parse_mixed_effect_
#: for_spell`'s per-clause split, the same way `_EACH_PLAYER_EXILE_SACRIFICE_
#: RETURN_RE` reads its own "then"-joined sentence as one CR 608.2c
#: instruction below - `split_effect_clauses` would otherwise cut this into
#: three fragments none of which reads as a known clause shape on its own.
#: The card's own name is not matched literally, so any future card sharing
#: this exact template reads for free.
_TARGET_GET_ENERGY_PAY_DAMAGE_RE = re.compile(
    r"^choose (?P<phrase>target[^.]+)\.\s*"
    r"you get (?P<e>(?:\{e\})+)\s*(?:\([^()]*\))?,\s*"
    r"then you may pay any amount of \{e\}\.\s*"
    r"[^.]+ deals that much damage to that permanent\.$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_target_get_energy_pay_damage(text: str) -> Effect | None:
    """Galvanic Discharge's own shape, see `_TARGET_GET_ENERGY_PAY_DAMAGE_RE`.

    The target was already chosen at CR 601.2c announcement (`machines/
    targeting.py` reads "target creature or planeswalker" the same whether it
    sits after "Choose" or after a verb like "destroy"), so this only has to
    grant the energy, ask CR 608.2d's variable-amount question, and deal that
    much damage to whatever `game.resolve_targets` still finds legal (CR
    608.2b) - exactly `deal_damage`'s own shape, with a paid amount standing
    in for a printed number.
    """
    whole = _strip_non_effect_preamble(text).strip()
    match = _TARGET_GET_ENERGY_PAY_DAMAGE_RE.fullmatch(whole)
    if match is None:
        return None
    if not _targets_understood(match.group("phrase")):
        return None
    energy_amount = len(re.findall(r"\{e\}", match.group("e"), re.IGNORECASE))

    def effect(game: "Game", spell: CardState) -> None:
        player = game.controller_of(spell)
        if energy_amount:
            player.add_counters(Counter.ENERGY, energy_amount)
        paid = game.pay_any_amount_of_energy(player, source=spell.card.name)
        if paid <= 0:
            return
        for target in game.resolve_targets(spell):
            game.deal_damage(target, paid, source=spell)

    return effect


#: "You get X {E} (energy counters), then you may pay any amount of {E}.
#: Destroy each artifact, creature, and enchantment with mana value less than
#: or equal to the amount of {E} paid this way." (Wrath of the Skies) - the
#: same variable-amount energy payment as Galvanic Discharge, referenced by a
#: mass-destruction clause keyed off the amount paid instead of a target.
_X_ENERGY_PAY_DESTROY_BY_MANA_VALUE_RE = re.compile(
    r"^you get x \{e\}\s*(?:\([^()]*\))?,\s*then you may pay any amount of \{e\}\.\s*"
    r"destroy each artifact, creature, and enchantment with mana value less than or "
    r"equal to the amount of \{e\} paid this way\.$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_x_energy_pay_destroy_by_mana_value(text: str) -> Effect | None:
    """Wrath of the Skies's own shape, see
    `_X_ENERGY_PAY_DESTROY_BY_MANA_VALUE_RE`.

    `X` is fixed once for the whole spell at announcement (CR 107.3a) and read
    back off `Game.cast_record` the same way `parse_mode_effect` already reads
    it for a modal card's own `X` mode. `game.battlefield` is snapshotted into
    a plain list before anything is destroyed, so destroying one permanent
    (and whatever state-based or triggered consequence that causes) cannot
    change what this loop is still iterating over; each permanent's zone is
    rechecked immediately before it is destroyed for the same reason CR
    608.2b targets get rechecked - a permanent already gone by the time its
    turn comes cannot be destroyed again.
    """
    whole = _strip_non_effect_preamble(text).strip()
    if _X_ENERGY_PAY_DESTROY_BY_MANA_VALUE_RE.fullmatch(whole) is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        player = game.controller_of(spell)
        x_value = game.cast_record(spell).x_value
        if x_value > 0:
            player.add_counters(Counter.ENERGY, x_value)
        paid = game.pay_any_amount_of_energy(player, source=spell.card.name)
        if paid <= 0:
            return
        candidates = [
            permanent
            for permanent in list(game.battlefield)
            if set(permanent.types) & {Type.ARTIFACT, Type.CREATURE, Type.ENCHANTMENT}
            and permanent.mana_value <= paid
        ]
        for permanent in candidates:
            if permanent.zone is Zone.BATTLEFIELD:
                game.destroy(permanent)

    return effect


# ---------------------------------------------------------------------------
# Mass destruction and mass sacrifice: "destroy each <qualifier>" and "each
# player sacrifices all <qualifier>" - CR 701.8a's destroy and CR 701.21a's
# sacrifice, each applied to every matching permanent on the battlefield
# rather than to a target CR 601.2c would announce and CR 608.2b would
# recheck. The family: All Is Dust (sacrifice, colored), Engineered
# Explosives and Culling Ritual (destroy, mana value against a printed
# constant or a self-referential counter count), Oblivion Stone (destroy,
# absence of a named counter, then an unconditional counter sweep). Wrath of
# the Skies shares the same "destroy each <qualifier> with mana value <cmp>"
# shape but is matched by its own dedicated parser above, ahead of this one,
# for its energy-payment right-hand side.
# ---------------------------------------------------------------------------

#: "destroy each/all <qualifier>[ without a <kind> counter on it][ with mana
#: value <cmp>]." <qualifier> is `_parse_mass_type_qualifier`'s grammar.
#: "all" reads exactly like "each" here - CR 205.2a's plural qualifier names
#: no different a group than "each" does - and Brotherhood's End's "Destroy
#: all artifacts with mana value 3 or less" is the wording that needs it.
_DESTROY_EACH_RE = re.compile(r"^destroy (?:each|all) (?P<rest>.+?)\.?$", re.IGNORECASE | re.DOTALL)

#: "<qualifier> without a <kind> counter on it" - Oblivion Stone's own
#: absence-of-a-counter restriction (CR 122.1: a counter's presence or
#: absence is state the effect can read, not a characteristic).
_MASS_WITHOUT_COUNTER_RE = re.compile(
    r"^(?P<qualifier>.+?) without a (?P<kind>[a-z]+) counter on it$", re.IGNORECASE
)

#: "<qualifier> with mana value equal to <rhs>" / "<qualifier> with mana
#: value N or less"/"...or greater" - CR 202.3's number, compared against a
#: printed constant or a count read off the clause's own source.
_MASS_MANA_VALUE_RE = re.compile(
    r"^(?P<inner>.+?) with mana value (?:"
    r"equal to (?P<eq>.+)"
    r"|(?P<n>\d+) or (?P<dir>less|greater)"
    r")$",
    re.IGNORECASE,
)

#: "the number of <kind> counters on this <noun>" - Engineered Explosives's
#: own self-referential right-hand side: "Destroy each nonland permanent
#: with mana value equal to the number of charge counters on this artifact."
_MASS_COUNTERS_ON_SELF_RE = re.compile(
    r"^the number of (?P<kind>[a-z]+) counters on this \w+$", re.IGNORECASE
)

#: Normalises an Oxford-or-not "X, Y, and Z" / "X or Y" list to plain commas,
#: so a type list reads the same however it is punctuated - Wrath of the
#: Skies and a hypothetical "artifact or creature" both split the same way.
_MASS_TYPE_JOIN_RE = re.compile(r",?\s+(?:and|or)\s+", re.IGNORECASE)


def _parse_mass_type_qualifier(phrase: str) -> Callable[[Characteristics], bool] | None:
    """A predicate for the qualifier half of a mass destruction/sacrifice
    clause, read off the *computed* board (CR 613.5) rather than the raw
    printing - `game.characteristics_of` is what a layer-6 type change or a
    layer-5 colour change would otherwise be missed by.

    <qualifier> is an optional "nonland " prefix (CR 205.2a's negation) ahead
    of either:

    - the bare word "permanent"/"permanents" - no restriction at all,
    - "colored permanent"/"colorless permanent" (CR 105.2b, CR 105.2c), or
    - one or more CR 205.2a card types joined by a comma, "and", or "or",
      with no trailing "permanent" word - Wrath of the Skies's own
      "artifact, creature, and enchantment".

    Returns `None` for anything else - a subtype list, a colour name, a
    controller restriction - so an unread qualifier fails the whole clause
    rather than silently matching everything or nothing.
    """
    lowered = phrase.strip().lower()
    nonland = lowered.startswith("nonland ")
    if nonland:
        lowered = lowered.removeprefix("nonland ").strip()
    bare = re.sub(r"(?:^|\s+)permanents?$", "", lowered).strip()

    type_predicate: Callable[[Characteristics], bool]
    if bare == "":

        def type_predicate(chars: Characteristics) -> bool:
            return True

    elif bare == "colored":

        def type_predicate(chars: Characteristics) -> bool:
            return bool(chars.colors)

    elif bare == "colorless":

        def type_predicate(chars: Characteristics) -> bool:
            return not chars.colors

    else:
        words = [word for word in _MASS_TYPE_JOIN_RE.sub(", ", bare).split(",") if word.strip()]
        types: list[Type] = []
        for word in words:
            # Plural is read the same as singular here - "artifacts" (a bare
            # plural type noun, Brotherhood's End's own "Destroy all
            # artifacts with mana value 3 or less") names the same CR 205.2a
            # type as "artifact"; Wrath of the Skies's own list never needs
            # this since its own members are already singular.
            card_type = _singular_card_type(word.strip())
            if card_type is None:
                return None
            types.append(card_type)
        if not types:
            return None
        type_tuple = tuple(types)

        def type_predicate(chars: Characteristics, types: tuple[Type, ...] = type_tuple) -> bool:
            return any(one_type in chars.types for one_type in types)

    def matches(chars: Characteristics) -> bool:
        if nonland and Type.LAND in chars.types:
            return False
        return type_predicate(chars)

    return matches


def _parse_mass_mv_rhs(text: str) -> Callable[["Game", CardState | None], int | None] | None:
    """The right-hand side of a mass-destruction mana-value comparison: a
    printed constant (Culling Ritual's "2") or a count of counters on the
    clause's own source (Engineered Explosives's "the number of charge
    counters on this artifact"). Returns `None` for text neither shape reads.
    """
    stripped = text.strip()
    if stripped.isdigit():
        value = int(stripped)

        def constant(game: "Game", source: CardState | None) -> int | None:
            return value

        return constant
    match = _MASS_COUNTERS_ON_SELF_RE.fullmatch(stripped)
    if match is None:
        return None
    kind = match.group("kind").lower()

    def counters_on_source(game: "Game", source: CardState | None) -> int | None:
        if source is None:
            return None
        # CR 603.10a / CR 400.7: Engineered Explosives sacrifices itself as
        # part of this same activation's cost, so by the time this ability
        # resolves it is a fresh, empty object in the graveyard -
        # `CardState.move_to` clears `counters` and keeps what was there on
        # `last_known_counters` for exactly this "look back at what just
        # left" reference. A source that never left keeps reading its live
        # counters, which is the general case for any future card sharing
        # this shape without a self-sacrifice cost.
        counters = (
            source.counters if source.zone is Zone.BATTLEFIELD else source.last_known_counters
        )
        return counters[kind]

    return counters_on_source


def _parse_mass_mv_comparison(
    match: re.Match[str],
) -> Callable[["Game", Characteristics, CardState | None], bool] | None:
    """`_MASS_MANA_VALUE_RE`'s comparison half, as a predicate over
    (game, candidate's characteristics, this clause's own source).
    """
    eq_rhs = match.group("eq")
    if eq_rhs is not None:
        rhs = _parse_mass_mv_rhs(eq_rhs)
        if rhs is None:
            return None

        def equals(game: "Game", chars: Characteristics, source: CardState | None) -> bool:
            threshold = rhs(game, source)
            return threshold is not None and chars.mana_value == threshold

        return equals

    n_text = match.group("n")
    direction = match.group("dir")
    if n_text is None or direction is None:
        return None
    bound = int(n_text)
    if direction.lower() == "less":

        def at_most(game: "Game", chars: Characteristics, source: CardState | None) -> bool:
            return chars.mana_value <= bound

        return at_most

    def at_least(game: "Game", chars: Characteristics, source: CardState | None) -> bool:
        return chars.mana_value >= bound

    return at_least


def _parse_mass_destroy_predicate(
    rest: str,
) -> Callable[["Game", CardState, CardState | None], bool] | None:
    """The whole description behind `_DESTROY_EACH_RE`'s `rest` group - a
    type qualifier, an optional absence-of-counter restriction, and an
    optional mana-value comparison, ANDed together - as a predicate over
    (game, candidate permanent, this clause's own source).
    """
    text = rest.strip()
    mv_comparison = None
    mv_match = _MASS_MANA_VALUE_RE.fullmatch(text)
    if mv_match is not None:
        mv_comparison = _parse_mass_mv_comparison(mv_match)
        if mv_comparison is None:
            return None
        text = mv_match.group("inner").strip()
    counter_kind = None
    without_match = _MASS_WITHOUT_COUNTER_RE.fullmatch(text)
    if without_match is not None:
        counter_kind = without_match.group("kind").lower()
        text = without_match.group("qualifier").strip()
    type_matches = _parse_mass_type_qualifier(text)
    if type_matches is None:
        return None

    def predicate(game: "Game", permanent: CardState, source: CardState | None) -> bool:
        chars = game.characteristics_of(permanent)
        if not type_matches(chars):
            return False
        if counter_kind is not None and chars.counters.get(counter_kind, 0) > 0:
            return False
        return mv_comparison is None or mv_comparison(game, chars, source)

    return predicate


def _destroy_matching(
    game: "Game",
    predicate: Callable[["Game", CardState, CardState | None], bool],
    source: CardState | None,
) -> int:
    """Destroy every permanent on the battlefield right now that `predicate`
    holds for, and answer how many actually left.

    CR 608.2f: "some spells and abilities include actions taken on multiple
    ... objects. In most cases, each such action is processed simultaneously."
    The candidate set is snapshotted from `game.battlefield` once, before
    anything is destroyed, so an earlier destruction in this same loop (and
    whatever state-based or triggered consequence it causes) cannot change
    what the rest of the loop still sees; each permanent's zone is rechecked
    immediately before its own `destroy` call for the same reason CR 608.2b
    rechecks a target - a permanent an earlier step in this loop already
    removed cannot be destroyed again. `Game.destroy` itself is what enforces
    CR 702.12b's indestructible, so an indestructible candidate is identified
    here but does not count toward the returned total.
    """
    destroyed = 0
    for permanent in [p for p in list(game.battlefield) if predicate(game, p, source)]:
        if permanent.zone is Zone.BATTLEFIELD:
            game.destroy(permanent)
            if permanent.zone is not Zone.BATTLEFIELD:
                destroyed += 1
    return destroyed


def _parse_destroy_each_clause(sentence: str) -> TargetedClause | None:
    """ "Destroy each <qualifier>[ without a counter][ with mana value ...]."
    on its own, with no second instruction - Engineered Explosives's whole
    ability text. `source` is the spell itself, or the activating ability's
    own source permanent (CR 113.7a: found by id, whatever zone it is in
    now), since nothing here is targeted at all.
    """
    match = _DESTROY_EACH_RE.fullmatch(sentence.strip())
    if match is None:
        return None
    predicate = _parse_mass_destroy_predicate(match.group("rest"))
    if predicate is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object if isinstance(stack_object, CardState) else stack_object.source(game)
        _destroy_matching(game, predicate, source)

    return effect


#: "<Source> deals N damage to each <type>[ and each <type>]*." -
#: Brotherhood's End's own first mode: "Brotherhood's End deals 3 damage to
#: each creature and each planeswalker." Unlike `_DAMAGE_EACH_OPPONENT_RE`'s
#: single implicit player, this names one or more of CR 300.1's card types,
#: ORed together - a permanent counts once even if it is more than one of the
#: named types. The leading `.*` reads past the card naming itself, the same
#: way `_DAMAGE_EACH_OPPONENT_RE` does.
_DAMAGE_EACH_GROUP_RE = re.compile(
    r"^.*\bdeals? (?P<n>\d+) damage to each (?P<groups>[a-z]+(?:\s+and\s+each\s+[a-z]+)*)\.?$",
    re.IGNORECASE,
)


def _parse_damage_each_group_clause(clause: str) -> TargetedClause | None:
    """`_DAMAGE_EACH_GROUP_RE`'s shape: simultaneous, non-targeted damage
    (CR 119.1) to every permanent presently on the battlefield matching one of
    the named card types - no target at all, so CR 608.2b's legality recheck
    never applies, only the board as it stands when this runs.
    """
    match = _DAMAGE_EACH_GROUP_RE.fullmatch(clause.strip())
    if match is None:
        return None
    amount = int(match.group("n"))
    words = re.split(r"\s+and\s+each\s+", match.group("groups"))
    types: set[Type] = set()
    for word in words:
        card_type = _singular_card_type(word)
        if card_type is None:
            return None
        types.add(card_type)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object if isinstance(stack_object, CardState) else stack_object.source(game)
        board = game.computed_board()
        for permanent in list(game.battlefield):
            if types & set(board.of(permanent).types):
                game.deal_damage(permanent, amount, source=source)

    return effect


#: A bare "each `<type>`[, each `<type>`]*" continuation, split off from
#: `_DAMAGE_EACH_GROUP_RE`'s own sentence by the generic "and" clause
#: splitter - "deals 3 damage to each creature" / "each planeswalker" is
#: exactly this shape once cut in two.
_BARE_EACH_GROUP_RE = re.compile(r"^each ([a-z]+)$", re.IGNORECASE)


def _merge_damage_each_group_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Reattach `_DAMAGE_EACH_GROUP_RE`'s own sentence to a bare "each
    `<type>`" fragment the generic "and" split cut off it - Brotherhood's End's
    "deals 3 damage to each creature and each planeswalker" is one CR 608.2c
    instruction, not "deals ... to each creature" followed by a second,
    unreadable "each planeswalker" clause. Consumes clause `index` plus every
    immediately following bare "each `<type>`" clause, then hands the
    reassembled sentence to `_parse_damage_each_group_clause`.

    Deliberately clause-list-scoped rather than tried on the whole, unsplit
    text: a card with an *earlier*, unrelated clause before this one
    (Extinguisher Battleship's "destroy target noncreature permanent. Then
    this Spacecraft deals 4 damage to each creature.") must not have that
    earlier clause swallowed by a greedy `.*` match against the whole text.
    """
    first = clauses[index].strip()
    if not _DAMAGE_EACH_GROUP_RE.fullmatch(first) or _BARE_EACH_GROUP_RE.fullmatch(first):
        return None
    consumed = 1
    combined = first.rstrip(".")
    while index + consumed < len(clauses) and _BARE_EACH_GROUP_RE.fullmatch(
        clauses[index + consumed].strip()
    ):
        combined = f"{combined} and {clauses[index + consumed].strip()}"
        consumed += 1
    if consumed == 1:
        return None  # nothing to reattach; the ordinary single-clause path handles it
    effect = _parse_damage_each_group_clause(combined)
    if effect is None:
        return None
    return consumed, effect


#: Oblivion Stone's own second activated ability: "Destroy each nonland
#: permanent without a fate counter on it, then remove all fate counters
#: from all permanents." - one CR 608.2c instruction in two clauses joined
#: by "then", the second an unconditional sweep of every permanent still on
#: the battlefield, not only the ones the first clause just destroyed.
_DESTROY_EACH_THEN_REMOVE_ALL_COUNTERS_RE = re.compile(
    r"^destroy each (?P<clause>.+? without a (?P<kind>[a-z]+) counter on it), "
    r"then remove all (?P=kind) counters from all permanents\.?$",
    re.IGNORECASE,
)


def _parse_destroy_each_then_remove_all_counters(text: str) -> AbilityEffect | None:
    """`_DESTROY_EACH_THEN_REMOVE_ALL_COUNTERS_RE`'s shape: destroy every
    matching permanent, then remove every counter of the named kind from
    every permanent still on the battlefield - including ones the first half
    did not touch, and including ones that never had the counter at all
    (CR 122: removing zero of a kind that is not there is simply nothing to
    remove, not an error).
    """
    match = _DESTROY_EACH_THEN_REMOVE_ALL_COUNTERS_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    predicate = _parse_mass_destroy_predicate(match.group("clause"))
    if predicate is None:
        return None
    kind = match.group("kind").lower()

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        _destroy_matching(game, predicate, source)
        for permanent in list(game.battlefield):
            present = permanent.counters[kind]
            if present:
                permanent.remove_counters(kind, present)

    return effect


#: Culling Ritual: "Destroy each nonland permanent with mana value 2 or
#: less. Add {B} or {G} for each permanent destroyed this way." - the second
#: instruction counts the first's own result, the mirror image of Wrath of
#: the Skies (whose *first* instruction is the payment the *second* counts).
_DESTROY_EACH_THEN_ADD_MANA_PER_DESTROYED_RE = re.compile(
    r"^destroy each (?P<clause>.+?)\.\s*"
    r"add (?P<colors>\{[wubrgc]\}(?:\s+or\s+\{[wubrgc]\})+) for each permanent destroyed "
    r"this way\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_destroy_each_then_add_mana_per_destroyed(text: str) -> Effect | None:
    """`_DESTROY_EACH_THEN_ADD_MANA_PER_DESTROYED_RE`'s shape.

    The colour of each unit of mana is the controller's own choice (CR
    601.2b's kind of choice, made as the spell resolves), asked once per
    permanent destroyed rather than once for the whole batch - "for each
    permanent destroyed this way" counts mana in per-unit terms (CR 107.4),
    and nothing pins every unit to the same colour. `DecisionKind.CHOOSE_A_
    QUALITY` is the kind CR 614.12a's own "choose a color" already asks
    through; reused here with `options` narrowed to the two colours this
    card actually offers rather than all five.
    """
    match = _DESTROY_EACH_THEN_ADD_MANA_PER_DESTROYED_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    predicate = _parse_mass_destroy_predicate(match.group("clause"))
    if predicate is None:
        return None
    symbols = tuple(
        dict.fromkeys(s.upper() for s in _MANA_SYMBOL_RE.findall(match.group("colors")))
    )
    if len(symbols) < 2:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        destroyed = _destroy_matching(game, predicate, spell)
        if destroyed <= 0:
            return
        player = game.controller_of(spell)
        pool = player.mana_pool
        for _ in range(destroyed):
            decision = Decision(
                kind=DecisionKind.CHOOSE_A_QUALITY,
                player=player.username,
                prompt=f"choose a color for {spell.name}'s mana",
                source=spell.name,
                options=symbols,
            )
            value = game.ask(decision)
            assert isinstance(value, str)
            pool.add(Color(value))

    return effect


#: All Is Dust: "Each player sacrifices all permanents they control that are
#: one or more colors." CR 701.21a's sacrifice, not CR 701.8a's destroy, so
#: CR 702.12b's indestructible never enters into it - the single easiest
#: thing to get wrong about this card.
_EACH_PLAYER_SACRIFICES_COLORED_RE = re.compile(
    r"^each player sacrifices all permanents they control that are one or more colors\.?$",
    re.IGNORECASE,
)


def each_player_sacrifices_colored_permanents(game: "Game", spell: CardState) -> None:
    """`_EACH_PLAYER_SACRIFICES_COLORED_RE`'s shape.

    CR 608.2f: the action is processed for every player. Nothing about
    *which* permanents each player sacrifices is a choice - it is "all" of a
    fixed description, not "a" or "N of their choice" - so there is no
    CR 101.4 APNAP order to get right or wrong here; `game.players_in_game`
    is walked only for a stable, repeatable order, the same reasoning
    `each_player_exiles_sacrifices_and_returns_creatures` above already
    documents for its own "each player" steps. Each player's own candidates
    are snapshotted before any of them are sacrificed, so one player's
    sacrifice (and whatever it triggers) cannot change what a later player's
    own step still sees.
    """
    for player in game.players_in_game:
        controlled = [
            permanent
            for permanent in list(game.battlefield)
            if permanent.controller == player.username
            and bool(game.characteristics_of(permanent).colors)
        ]
        for permanent in controlled:
            if permanent.zone is Zone.BATTLEFIELD:
                game.sacrifice(permanent)


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
    # -- Wave W6's own whole-text additions, contiguous block -------------
    revolt_destroy = _parse_revolt_destroy_or_exile_clause(whole)
    if revolt_destroy is not None:
        return revolt_destroy
    converge_exile = _parse_converge_exile_by_colors_spent(whole)
    if converge_exile is not None:
        return converge_exile
    x_life_mass_debuff = _parse_x_life_mass_debuff(whole)
    if x_life_mass_debuff is not None:
        return x_life_mass_debuff
    # -- end Wave W6 whole-text additions -----------------------------------
    if _EACH_PLAYER_EXILE_SACRIFICE_RETURN_RE.fullmatch(whole):
        # Read whole, ahead of `parse_mixed_effect_for_spell`: the sentence's
        # own ", then " joins are CR 608.2c instructions in one breath, not
        # three clauses `_CLAUSE_SEPARATOR` may cut apart and fail separately.
        return each_player_exiles_sacrifices_and_returns_creatures
    conditional_sacrifice = _parse_conditional_sacrifice_clause(effect_text, for_spell=True)
    if conditional_sacrifice is not None:
        return conditional_sacrifice
    target_energy_damage = _parse_target_get_energy_pay_damage(effect_text)
    if target_energy_damage is not None:
        return target_energy_damage
    x_energy_destroy = _parse_x_energy_pay_destroy_by_mana_value(effect_text)
    if x_energy_destroy is not None:
        return x_energy_destroy
    x_divided_damage_doubled = _parse_x_damage_divided_and_doubled_clause(effect_text)
    if x_divided_damage_doubled is not None:
        return x_divided_damage_doubled
    damage_target_kicked_instead = _parse_damage_target_kicked_instead_clause(effect_text)
    if damage_target_kicked_instead is not None:
        return damage_target_kicked_instead
    destroy_two_targets = _parse_destroy_two_targets_clause(effect_text)
    if destroy_two_targets is not None:
        return destroy_two_targets
    if _CONTROL_REPLACEMENT_RE.fullmatch(whole):

        def control_replacement_notice_only(game: "Game", spell: CardState) -> None:
            game.control_replacement_notices.append(
                ControlReplacementNotice(
                    source_id=spell.id, source_name=spell.card.name, text=whole
                )
            )

        return control_replacement_notice_only
    bottom_hand_then_draw = _parse_bottom_hand_then_draw_plus_one_clause(effect_text)
    if bottom_hand_then_draw is not None:
        return bottom_hand_then_draw
    look_top_n_battlefield = _parse_look_top_n_may_battlefield_creature_bonus_clause(effect_text)
    if look_top_n_battlefield is not None:
        return look_top_n_battlefield
    if _EACH_PLAYER_SACRIFICES_COLORED_RE.fullmatch(whole):
        return each_player_sacrifices_colored_permanents
    destroy_each_then_add_mana = _parse_destroy_each_then_add_mana_per_destroyed(effect_text)
    if destroy_each_then_add_mana is not None:
        return destroy_each_then_add_mana
    destroy_each_for_spell = _parse_destroy_each_clause(whole)
    if destroy_each_for_spell is not None:
        return destroy_each_for_spell
    mass_pump_for_spell = _mass_pump_spell_effect(whole)
    if mass_pump_for_spell is not None:
        return mass_pump_for_spell
    if _COUNTER_THEN_SUSPEND_REDIRECT_RE.fullmatch(re.sub(r"\s*\([^()]*\)\s*$", "", whole)):

        def suspend_redirect_notice_only(game: "Game", spell: CardState) -> None:
            game.suspend_redirect_notices.append(
                SuspendRedirectNotice(source_id=spell.id, source_name=spell.card.name, text=whole)
            )

        return suspend_redirect_notice_only
    flashback_grant = _parse_grant_flashback_clause(whole)
    if flashback_grant is not None:
        return flashback_grant
    if _DAMAGE_THEN_GROUP_TYPE_ABILITY_GRANT_RE.fullmatch(whole):

        def damage_then_group_grant_notice_only(game: "Game", spell: CardState) -> None:
            game.anaphoric_clause_notices.append(
                AnaphoricClauseNotice(source_id=spell.id, source_name=spell.card.name, text=whole)
            )

        return damage_then_group_grant_notice_only
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


# --------------------------------------------------------------------------
# Wave W6: Fatal Push's Revolt line, Prismatic Ending's Converge, and Toxic
# Deluge's "pay X life" additional cost feeding a mass -X/-X
# --------------------------------------------------------------------------

#: "<Destroy/Exile> target ... if it has mana value N or less.\nRevolt —
#: <same verb> that ... if it has mana value M or less instead if a permanent
#: left the battlefield under your control this turn." Read as one CR 608.2c
#: instruction: the numbers themselves are not read here at all - Fatal
#: Push's real work already happened in `machines/targeting.py`'s own
#: `_read_revolt_mana_value_override`, which bakes both thresholds into the
#: `TargetRequirement` that `Game.legal_target` re-checks on resolution
#: (CR 608.2b) and consults live Revolt state for (an ability word, CR
#: 207.2c). All this clause has to do is recognise the two-paragraph shape so
#: the whole ability is not thrown away as an unreadable second sentence, and
#: hand back the same unconditional destroy/exile verb every other "target
#: ..." clause in this file already uses - the conditional part of "if it has
#: mana value N or less" is enforced entirely by the targeting layer, not by
#: this effect.
_REVOLT_DESTROY_OR_EXILE_RE = re.compile(
    r"^(?P<verb>destroy|exile) (?P<phrase>target .+?) if it has mana value \d+ or less\."
    r"\s*revolt\s*[—-]\s*(?P=verb) that .+? if it has mana value \d+ or less instead if a "
    r"permanent left the battlefield under your control this turn\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_revolt_destroy_or_exile_clause(effect_text: str) -> Effect | None:
    """`_REVOLT_DESTROY_OR_EXILE_RE`'s shape, or `None` if this is not it."""
    match = _REVOLT_DESTROY_OR_EXILE_RE.fullmatch(effect_text.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    return (
        destroy_ability_targets
        if match.group("verb").lower() == "destroy"
        else exile_ability_targets
    )


#: Converge (an ability word - `knowledge_search` found no numbered CR rule
#: for it this session, so none is cited): "Exile target nonland permanent if
#: its mana value is less than or equal to the number of colors of mana
#: spent to cast this spell." Deliberately its own parser rather than a
#: `machines/targeting.py` comparison: that count is not fixed until the
#: spell's cost is fully paid (CR 601.2g-i), which is *after* targets are
#: announced (CR 601.2c) - unlike Fatal Push's mana-value threshold, there is
#: no moment before resolution at which this count could restrict what may
#: legally be targeted, so the target itself is read as the plain, unrestricted
#: "target nonland permanent" `_targets_understood` already knows, and the
#: whole condition is judged once, at resolution, off `CastRecord.mana_spent`
#: (color keys only - `Color.COLORLESS` is generic mana, not one of CR 105.1's
#: five colors).
_CONVERGE_EXILE_RE = re.compile(
    r"^(?:[a-z][a-z '-]* — )?exile target nonland permanent if its mana value is less than "
    r"or equal to the number of colors of mana spent to cast this spell\.?$",
    re.IGNORECASE,
)


def _parse_converge_exile_by_colors_spent(effect_text: str) -> Effect | None:
    """`_CONVERGE_EXILE_RE`'s shape, or `None` if this is not it."""
    if _CONVERGE_EXILE_RE.fullmatch(effect_text.strip()) is None:
        return None
    if not _targets_understood("target nonland permanent", count_agnostic=False):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        record = game.cast_record(spell)
        colors_spent = len(
            {color for color, amount in record.mana_spent.items() if amount > 0} - {Color.COLORLESS}
        )
        for target in game.resolve_targets(spell):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                mana_value = game.characteristics_of(target).mana_value
                if mana_value <= colors_spent:
                    game.exile_permanent(target)

    return effect


#: Toxic Deluge: "As an additional cost to cast this spell, pay X life.\nAll
#: creatures get -X/-X until end of turn." The additional-cost line is
#: already stripped by `_strip_non_effect_preamble` (CR 118.8a: paid on the
#: way to the stack, not part of resolving the spell) before this ever sees
#: it, so only the second sentence is matched here, with its "X" still
#: literal - `effect_for`'s own X substitution only fires for a spell with
#: `{X}` in its *mana cost* (Green Sun's Zenith, Walking Ballista), and Toxic
#: Deluge's X is announced by the additional cost instead (CR 107.3f), so
#: this reads `Game.cast_record` for itself at resolution exactly the way
#: `_parse_x_energy_pay_destroy_by_mana_value` already does for its own
#: additional-cost X. `_run_mass_pump` and `_mass_creature_group_targets`'s
#: "all creatures" branch (see `machines/layers.py`'s widened
#: `_MASS_PUMP_UNTIL_EOT_RE`) are reused unchanged, with a negative magnitude
#: and no controller restriction - the shared primitive this wave was told to
#: build on rather than duplicate.
_X_LIFE_MASS_DEBUFF_RE = re.compile(
    r"^all creatures get -x/-x until end of turn\.?$", re.IGNORECASE
)


def _parse_x_life_mass_debuff(effect_text: str) -> Effect | None:
    """`_X_LIFE_MASS_DEBUFF_RE`'s shape, or `None` if this is not it."""
    if _X_LIFE_MASS_DEBUFF_RE.fullmatch(effect_text.strip()) is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        x_value = game.cast_record(spell).x_value
        if x_value <= 0:
            return
        literal = f"All creatures get -{x_value}/-{x_value} until end of turn."
        _run_mass_pump(game, spell, game.controller_of(spell).username, literal, None)

    return effect


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
            # CR 712.14a: "transformed" is how it *enters*, not something done
            # to it afterwards - the difference is CR 306.5b's loyalty
            # counters, which are put on as it enters and read off the face
            # that is up. Transforming after the fact left a planeswalker back
            # face on the battlefield at 0 loyalty, dead to CR 704.5i.
            game.put_onto_battlefield(
                exiled, new_controller, tapped=tapped, transformed=transformed
            )

    return effect


#: "Create X 1/1 colorless Thopter artifact creature tokens with flying, where
#: X is that spell's mana value." (Access Denied) - CR 107.3's X, set by the
#: very spell the paired first clause just countered, not chosen by the
#: caster. `desc`/`tail` are read exactly like `_TOKEN_CLAUSE_RE`'s own groups
#: (`_parse_generic_token_descriptor`/`_parse_token_tail`); only the leading
#: "X" and the trailing "where X is ..." are specific to this shape.
_CREATE_TOKENS_WHERE_X_IS_THAT_SPELLS_MANA_VALUE_RE = re.compile(
    r"^create x (?P<desc>.+?) \btokens?\b(?:\s+with\s+(?P<tail>.+?))?"
    r",?\s*where x is that spell'?s mana value\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_counter_then_create_tokens_by_mana_value_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "Counter target spell. Create X ... tokens ..., where X is that
    spell's mana value." as one CR 608.2c instruction pair, or `None` if this
    shape does not match.

    CR 400.7's anaphora: "that spell" in the second sentence is whatever the
    first sentence's "target spell" found, not a target of its own - the same
    reasoning `_parse_anaphoric_clause_pair` already documents for "its
    controller ...". The mana value is read off the countered spell's own
    printed card (`CardState.card.cmc`) *before* the token count is decided,
    which only matters in that both happen in the same breath here: `Game.
    counter` never changes what `.card` reports, so the order between
    countering and reading the mana value could not produce a different
    answer either way, unlike a permanent's power or toughness once it has
    left the battlefield (see `hangarback_walkers_thopters`'s own docstring
    for why *that* one has to read `last_known_counters`).

    A target that already left the stack (CR 608.2b) is neither countered nor
    read for a mana value, and no tokens are created - there is no spell left
    to have had one.
    """
    if not for_spell:
        return None
    if not _COUNTER_TARGET_SPELL_RE.fullmatch(first.strip()):
        return None
    match = _CREATE_TOKENS_WHERE_X_IS_THAT_SPELLS_MANA_VALUE_RE.fullmatch(second.strip())
    if match is None:
        return None
    words = match.group("desc").strip().split()
    if not words:
        return None
    definition = _parse_generic_token_descriptor(words, match.group("tail"))
    if definition is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell).username
        countered: CardState | None = None
        for reference in spell.targets:
            if not reference.is_card:
                continue
            target = next((item for item in game.stack if item.id == reference.card_id), None)
            if target is not None:
                countered = target
                game.counter(target)
        if countered is None:
            return
        mana_value = int(countered.card.cmc)
        create_tokens(game, definition, controller, mana_value)

    return effect


#: "If that spell is countered this way, exile it instead of putting it into
#: its owner's graveyard." (Force of Negation) - CR 701.6a's default
#: destination, overridden. `that spell` is CR 400.7 anaphora back to
#: whatever the first sentence's "target ... spell" found, the same reading
#: `_parse_counter_then_create_tokens_by_mana_value_pair` and
#: `_parse_anaphoric_clause_pair` already give a second sentence's pronoun.
_COUNTER_THEN_EXILE_INSTEAD_RE = re.compile(
    r"^if (?:that|the) spell is countered this way, exile it instead of "
    r"putting it into its owner'?s graveyard\.?$",
    re.IGNORECASE,
)


def _parse_counter_then_exile_instead_of_graveyard_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "Counter target ... spell. If that spell is countered this way, exile
    it instead of putting it into its owner's graveyard." as one CR 608.2c
    instruction pair, or `None` if this shape does not match.

    `Game.counter` always sends a countered spell to its owner's graveyard
    (CR 701.6a); `to_exile=True` is exactly this override. A target that
    already left the stack is simply not countered and nothing is exiled, the
    same as plain `counter_targets`.
    """
    if not for_spell:
        return None
    if not _COUNTER_TARGET_SPELL_RE.fullmatch(first.strip()):
        return None
    if not _COUNTER_THEN_EXILE_INSTEAD_RE.fullmatch(second.strip()):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        for reference in spell.targets:
            if not reference.is_card:
                continue
            target = next((item for item in game.stack if item.id == reference.card_id), None)
            if target is not None:
                game.counter(target, to_exile=True)

    return effect


#: "you may cast it without paying its mana cost" (Transcendent Dragon) - the
#: tail end of its own counter-then-exile-then-cast paragraph, with no
#: "until end of turn" the way Ragavan's and Ugin's own permission sentences
#: print it (`_PLAY_PERMISSION_RE`).
_CAST_IT_FREE_RE = re.compile(r"^you may cast it without paying its mana cost$", re.IGNORECASE)


def _parse_counter_exile_then_cast_free_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Transcendent Dragon's whole trigger: "counter target spell. If that
    spell is countered this way, exile it instead of putting it into its
    owner's graveyard, then you may cast it without paying its mana cost."
    read as one CR 608.2c instruction, the ability-side counterpart of
    `_parse_counter_then_exile_instead_of_graveyard_pair` (which only ever
    fires `for_spell=True` - nothing in the pool prints the plain
    counter-then-exile pair on a triggered ability until this card).

    Three clauses, not two: `split_effect_clauses` cuts the second sentence's
    trailing ", then you may cast it without paying its mana cost" away from
    the exile clause in front of it, so this reads all three together.

    CR 611.2a: a continuous effect with no stated duration lasts until the
    end of the game, and this permission prints none - unlike Ragavan's and
    Ugin's own "until end of turn" sentence (`_PLAY_PERMISSION_RE`) - so the
    grant is made with `until_end_of_turn=False`.

    A target that already left the stack (CR 608.2b) is neither countered nor
    exiled, and no permission is granted - there is no spell left to grant one
    over, the same as plain `counter_targets`.
    """
    if for_spell or index + 2 >= len(clauses):
        return None
    if not _COUNTER_TARGET_SPELL_RE.fullmatch(clauses[index].strip()):
        return None
    if not _COUNTER_THEN_EXILE_INSTEAD_RE.fullmatch(clauses[index + 1].strip()):
        return None
    if not _CAST_IT_FREE_RE.fullmatch(clauses[index + 2].strip()):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        controller = game.controller_of(ability).username
        for reference in ability.targets:
            if not reference.is_card:
                continue
            target = next((item for item in game.stack if item.id == reference.card_id), None)
            if target is None:
                continue
            game.counter(target, to_exile=True)
            game.grant_play_permission(
                target,
                controller,
                pays_mana_cost=False,
                source_name=ability.source_name,
                rule="CR 611.2a",
                until_end_of_turn=False,
            )

    return 3, effect


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
            return lambda state: not state.colors
        return lambda state: color in state.colors
    try:
        card_type = Type(lowered)
    except ValueError:
        return None
    return lambda state: card_type in state.types


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
        return lambda state: state.mana_value >= bound
    return lambda state: state.mana_value <= bound


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
    read as "this `<type>`" (the permanent bearing the ability itself,
    Sanctum of Ugin), "another `<type>`" (a second permanent the player
    controls of the stated type, Disciple of Freyalise), or a bare "a `<type>`"
    /"an `<type>`" (any permanent of the stated type the player controls, no
    self-exclusion - Grist, the Hunger Tide's "-2") - each paired with a
    function that reads the actual legal candidates off the battlefield at
    resolution time - never at parse time, since what is on the battlefield
    changes between then and resolution.

    Returns `(is_self, candidates)`: `is_self` says whether there is a real
    CR 608.2d choice of *which* permanent to sacrifice (false for "this
    `<type>`", where there is only ever one, CR 601.2c never asks a question
    with one answer) or a genuine one among however many candidates
    `candidates` finds (true only in name for "another `<type>`"/bare "a
    `<type>`" - the "false"/"true" pairing here is the reverse of confusing:
    `is_self` is true for the self-reference shape).

    Anything else - a compound restriction, a `<type>` this wave cannot read
    as a single `Type` - comes back `None`, fail-closed.
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
                and card_type in permanent.types
            ]

        return False, other_candidates

    for article in ("a ", "an "):
        if not restriction.startswith(article):
            continue
        try:
            card_type = Type(restriction.removeprefix(article).strip())
        except ValueError:
            return None

        def any_candidates(
            game: "Game", player: Player, source_id: UUID, card_type: Type = card_type
        ) -> list[CardState]:
            return [
                permanent
                for permanent in game.battlefield
                if permanent.controller == player.username and card_type in permanent.types
            ]

        return False, any_candidates

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


class SuspendRedirectNotice(BaseModel):
    """A "counter target spell. If [it] is countered this way, exile it with
    N time counters ... instead of ... graveyard. If it doesn't have suspend,
    it gains suspend." effect (Delay) - genuinely read (the shape is
    recognised), but deliberately not executed.

    CR 702.62a's suspend is three abilities, and `docs/engine-coverage.md`
    already tracks none of them as built: `ExileMarker` has no `SUSPENDED`
    entry, nothing removes a time counter at upkeep, and nothing grants the
    cast-for-free permission once the last one comes off. Half-doing this -
    countering the spell and exiling it with three time counters while never
    honouring "it gains suspend" - would be exactly the forbidden shape: a
    board that looks right (the spell is gone) and is not (it can now never
    come back, when the card says it eventually can). So the whole paragraph
    fails closed instead: no counter, no exile, no counters placed - and this
    notice is the record that something real went unread, not a silent no-op.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    """The unreadable clause itself, as printed."""


#: "Counter target `<qualifier>` spell. If [it/that spell] is countered this
#: way, exile it with `<n>` time counters on it instead of putting it into its
#: owner's graveyard. If it doesn't have suspend, it gains suspend." (Delay) -
#: recognised whole, on purpose, rather than split into `_COUNTER_TARGET_
#: SPELL_RE`'s own clause plus two unreadable ones: `_parse_mixed_clauses`
#: already fails the whole card closed the moment one clause of several does
#: not parse, but that leaves *no record* that anything was seen at all -
#: this pattern exists only to turn that silence into a `SuspendRedirectNotice`.
_COUNTER_THEN_SUSPEND_REDIRECT_RE = re.compile(
    rf"^counter target(?: {_SPELL_QUALIFIER_WORD})? spell\. "
    r"if (?:that|the) spell is countered this way, exile it with \w+ time counters? on it "
    r"instead of putting it into its owner'?s graveyard\. "
    r"if it doesn'?t have suspend, it gains suspend\.?$",
    re.IGNORECASE,
)


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
# "You may sacrifice ... When you do, ..." (CR 603.12)
# --------------------------------------------------------------------------
#
# Verified this session with `knowledge_search(q="...", type="rules")`:
#
#   CR 603.12 - "A resolving spell or ability may allow or instruct a player
#   to take an action and create a triggered ability that triggers 'when [a
#   player] [does or doesn't]' take that action or 'when [something happens]
#   this way.' These reflexive triggered abilities follow the rules for
#   delayed triggered abilities (see rule 603.7), except that they're checked
#   immediately after being created and trigger based on whether the trigger
#   event or events occurred earlier during the resolution of the spell or
#   ability that created them."
#
#   CR 405.6a - "Effects don't go on the stack; they're the result of spells
#   and abilities resolving. Effects may create delayed triggered abilities,
#   however, and these may go on the stack when they trigger."
#
# This is the shape CR 118.12's "If you do" is often confused with, and the
# two resolve completely differently. "If you do" (`_parse_conditional_
# sacrifice_clause` above) reads: the consequence is *part of the same
# resolution*, no new stack object, no priority in between (CR 118.12's own
# "regardless of what events actually occurred" is about the cost, not a
# second object). "When you do" creates a *second*, independent triggered
# ability (CR 603.12) that goes on the stack of its own accord the next time
# a player would receive priority (CR 603.3) - which is exactly what lets an
# opponent respond to Grist's "When you do, destroy target creature or
# planeswalker" before it resolves, and exactly what CR 405.6a says an
# ordinary one-shot effect could never do on its own.
#
# Grist, the Hunger Tide's "−2: You may sacrifice a creature. When you do,
# destroy target creature or planeswalker." is the vehicle: sacrifice is
# already a modelled cost with a working `MAY` decision (`_sacrifice_
# restriction` above), so this reuses that and only adds what CR 603.12 adds
# on top - a second stack object, created (not resolved) here, whose own
# target is chosen when *it* goes on the stack (CR 603.3d), not now.
#
# Two traps this shape earns, both guarded against explicitly:
#
# - **The target must not be asked for here.** `machines/targeting.py`'s
#   `profile_for_text` is what `Game._ask_trigger_targets` and `Game.
#   activate_ability` read the *outer* ability's own targeting profile from,
#   and both hand it the ability's raw printed text - which still contains
#   the reflexive clause's "target creature or planeswalker" if nothing
#   strips it. `profile_for_text` now cuts everything from "when you do"
#   onward before parsing, so the outer ability (Grist's `-2`, Guide of
#   Souls' "Whenever you attack") is never asked to announce a target that
#   belongs to an ability that may never even be created (CR 603.3d).
# - **The cost stays paid on a fizzle.** The sacrifice happens here, inside
#   the *parent's* resolution, before the reflexive ability even exists;
#   `Game.create_reflexive_trigger` only ever queues it afterward. If the
#   reflexive ability's own target later becomes illegal (CR 608.2b), only
#   the reflexive ability's effect is skipped - there is no path back to
#   un-sacrifice the creature, because nothing here ever offers one.
#
# Only the "you may sacrifice" shape is read below. A mandatory action
# ("Create a token. When you do, ...", Ajani, Nacatl Avenger's `0`) or an
# optional action that is not a sacrifice ("you may pay {E}{E}{E}", Guide of
# Souls' attack trigger - blocked on there being no general may-pay-a-cost
# primitive at all, see `docs/engine-coverage.md`) is deliberately left
# unread rather than guessed at; `_unreadable_reflexive_clause` is what turns
# that refusal into a `ReflexiveClauseNotice` instead of the silent nothing
# both cards resolved to before this wave.

#: "You may sacrifice `<restriction>`. When you do, `<consequence>`." - the
#: same restriction shape `_MAY_SACRIFICE_IF_YOU_DO_RE` reads, with "when"
#: for "if" so the two can never both match the same text.
_REFLEXIVE_MAY_SACRIFICE_RE = re.compile(
    r"^you may sacrifice (?P<restriction>[^.]+)\.\s*when you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)

#: Any "`<action>`. When you do, `<consequence>`." shape at all, read only to
#: tell "not this shape" apart from "this shape, but unreadable" for
#: `_unreadable_reflexive_clause` - the same role `_MAY_SACRIFICE_IF_YOU_DO_RE`
#: plays for `_unreadable_conditional_clause`.
_REFLEXIVE_CLAUSE_RE = re.compile(
    r"^(?P<action>.+?)\.\s*when you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


class ReflexiveClauseNotice(BaseModel):
    """One "`<action>`. When you do, `<consequence>`." effect (CR 603.12)
    whose action or consequence this wave could not read.

    Guide of Souls' "you may pay {E}{E}{E}. When you do, put two +1/+1
    counters and a flying counter on target attacking creature ..." is the
    reason this exists rather than the ability simply resolving as nothing:
    paying energy is a missing primitive (`docs/engine-coverage.md`), but a
    trigger that does nothing must still say why, the same unreadable-is-not-
    the-same-as-no-effect record `ConditionalClauseNotice` and its siblings
    already keep."""

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    """The unreadable clause itself, as printed."""


def _unreadable_reflexive_clause(text: str) -> str | None:
    """The "`<action>`. When you do, `<consequence>`." clause inside `text`,
    if it matches CR 603.12's shape but `_parse_reflexive_sacrifice_clause`
    still cannot read it - used only to decide whether a parse failure
    deserves a `ReflexiveClauseNotice`, the same way `_unreadable_conditional_
    clause` decides for its own shape.
    """
    whole = _strip_non_effect_preamble(text).strip()
    match = _REFLEXIVE_CLAUSE_RE.fullmatch(whole)
    if match is None:
        return None
    if _parse_reflexive_sacrifice_clause(text) is not None:
        return None
    if _parse_reflexive_pay_energy_clause(text) is not None:
        return None
    if _parse_reflexive_mandatory_token_clause(text) is not None:
        return None
    return whole


def _parse_reflexive_sacrifice_clause(text: str) -> AbilityEffect | None:
    """ "You may sacrifice `<restriction>`. When you do, `<consequence>`."
    (CR 603.12), read off the ability's own printed text so no registry row
    is needed - Grist, the Hunger Tide's `-2`.

    The "you may" half is exactly `_parse_conditional_sacrifice_clause`'s:
    `DecisionKind.MAY` with `affirmative_is_legal` set to whether a legal
    permanent to sacrifice exists (CR 608.2d), then `DecisionKind.CHOOSE_
    CARDS` if there is a real choice of which. What differs is what happens
    once the player says yes: CR 118.12 would run the consequence right here;
    CR 603.12 instead creates a *second* triggered ability
    (`Game.create_reflexive_trigger`) and leaves it for the stack, so
    `<consequence>` is parsed once, up front, into an ordinary `AbilityEffect`
    (`parse_mixed_effect`) that runs when *that* ability resolves - reading
    its own targets off itself (CR 608.2b's recheck included), never off the
    parent.
    """
    match = _REFLEXIVE_MAY_SACRIFICE_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    restriction = _sacrifice_restriction(match.group("restriction"))
    if restriction is None:
        return None
    is_self, candidates_of = restriction
    consequence_text = match.group("consequence").strip()
    consequence_effect = parse_mixed_effect(consequence_text)
    if consequence_effect is None:
        return None
    prompt = f"sacrifice {match.group('restriction').strip()}"

    def resolve_reflexive(
        game: "Game", reflexive_ability: AbilityOnStack, trigger: DelayedTrigger
    ) -> None:
        consequence_effect(game, reflexive_ability)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.controller_of(ability)
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
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
        game.sacrifice(chosen)
        # CR 603.12: the reflexive ability is created *now*, after the action
        # - not before it, and not offered a target of its own until it goes
        # on the stack (CR 603.3d), which `create_reflexive_trigger` defers to
        # `Game.put_triggers_on_stack`.
        game.create_reflexive_trigger(
            text=consequence_text,
            controller=player.username,
            source_id=ability.source_id,
            source_name=source_name,
            callback=resolve_reflexive,
        )

    return effect


# --------------------------------------------------------------------------
# "Exile target card from a graveyard. When a creature card is exiled this
# way, <consequence>." (CR 603.12) - Agatha's Soul Cauldron's `{T}` ability.
# --------------------------------------------------------------------------
#
# A second CR 603.12 shape, alongside `_parse_reflexive_sacrifice_clause`
# above: the action is unconditional (an ordinary "exile target card", no
# "you may"), and what makes the reflexive ability exist is not a player's
# choice but *what kind of card* the first sentence actually exiled - CR
# 603.12's own "trigger based on whether the trigger event ... occurred" reads
# here as "was the exiled card a creature card", checked against the object
# `game.exile_permanent` just moved, once, right after it moves. Reusing
# `create_reflexive_trigger` rather than building a second reflexive-ability
# primitive, per the trap this wave was warned about.
#
# `profile_for_text`'s `_REFLEXIVE_CLAUSE_TAIL` cuts this same "when ... this
# way," tail before reading the outer ability's own target, so the activation
# only ever announces the first sentence's "target card from a graveyard" -
# the second target ("target creature you control") is announced later, when
# the reflexive ability itself goes on the stack (CR 603.3d), exactly the way
# `_parse_reflexive_sacrifice_clause`'s own consequence target is.

_EXILE_TARGET_REFLEXIVE_CREATURE_RE = re.compile(
    r"^exile (?P<phrase>target card from a graveyard)\.\s*"
    r"when a creature card is exiled this way,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_exile_target_card_reflexive_creature_counter(text: str) -> AbilityEffect | None:
    """`_EXILE_TARGET_REFLEXIVE_CREATURE_RE`'s shape - Agatha's Soul
    Cauldron's `{T}` ability.

    CR 400.7/CR 700.4: whether the exiled object "is a creature card" is read
    off its own printed card type, not the battlefield's layer 6 (it never
    reaches the battlefield at all), so `Type.CREATURE in target.card.types`
    is checked on the object `game.exile_permanent` just moved.
    """
    match = _EXILE_TARGET_REFLEXIVE_CREATURE_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True, battlefield_only=False):
        return None
    consequence_text = match.group("consequence").strip()
    consequence_effect = parse_mixed_effect(consequence_text)
    if consequence_effect is None:
        return None

    def resolve_reflexive(
        game: "Game", reflexive_ability: AbilityOnStack, trigger: DelayedTrigger
    ) -> None:
        consequence_effect(game, reflexive_ability)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        exiled_a_creature = False
        for target in game.resolve_targets(ability):
            if not isinstance(target, CardState):
                continue
            is_creature = Type.CREATURE in target.card.types
            game.exile_permanent(target)
            if is_creature:
                exiled_a_creature = True
        if not exiled_a_creature:
            return
        game.create_reflexive_trigger(
            text=consequence_text,
            controller=ability.controller,
            source_id=ability.source_id,
            source_name=ability.source_name,
            callback=resolve_reflexive,
        )

    return effect


# --------------------------------------------------------------------------
# CR 603.12 generalised: a non-sacrifice paid cost, and a mandatory action
# --------------------------------------------------------------------------
#
# `_parse_reflexive_sacrifice_clause` above only reads "you may sacrifice
# ... When you do, ...". Two more CR 603.12 shapes are in the pool:
#
# - Guide of Souls' "Whenever you attack, you may pay {E}{E}{E}. When you
#   do, ..." - the "you may" half is a *cost*, not a sacrifice, and
#   `DecisionKind.PAY_ENERGY`/`Game.may_pay_energy` (built for Static
#   Prison's "unless you pay {E}") is what makes it payable at all now.
# - Ajani, Nacatl Avenger's "Create a token. When you do, if ..., he deals
#   damage ..." - a *mandatory* action, not "you may" at all (CR 603.12's
#   "allow **or instruct**"), with an intervening *if* (CR 603.4) nested in
#   the reflexive clause itself.
#
# Both still create the reflexive ability only once the action has actually
# happened (`_REFLEXIVE_MAY_PAY_ENERGY_RE`'s decline, `_REFLEXIVE_MANDATORY_
# TOKEN_RE`'s replaced-into-nothing token creation), the same trap
# `_parse_reflexive_sacrifice_clause` already guards.

#: "you may pay {E}{E}{E}. When you do, `<consequence>`." - the fixed-amount
#: energy cost `_REFLEXIVE_MAY_SACRIFICE_RE` does not cover.
_REFLEXIVE_MAY_PAY_ENERGY_RE = re.compile(
    r"^you may pay (?P<energy>(?:\{e\})+)\.\s*when you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)

#: "put `<n>` +1/+1 counters and a[n] `<keyword>` counter on `<phrase>`. It
#: becomes a[n] `<subtype>` in addition to its other types." - Guide of
#: Souls' own reflexive consequence: two keyword counters (CR 122.1a, CR
#: 122.1b) in one clause, then an anaphoric "It" (CR 400.7) naming the same
#: target for a layer 4 type change (CR 613.1d) with no stated duration, so
#: it lasts for as long as the permanent exists (CR 611.2c) rather than
#: "until end of turn" the way `_BECOMES_TYPE_IN_ADDITION_RE` above always
#: does - the whole reason this is its own reader rather than a
#: `parsed_layer_effects` sentence.
_COUNTERS_AND_BECOMES_TYPE_RE = re.compile(
    r"^put (?P<n>\w+) \+1/\+1 counters? and an? (?P<keyword>[a-z]+) counter on "
    r"(?P<phrase>target [^.]+)\.\s*it becomes an? (?P<subtype>[a-z]+) in addition to "
    r"its other types\.?$",
    re.IGNORECASE,
)


def _parse_counters_and_becomes_type_clause(text: str) -> AbilityEffect | None:
    """Guide of Souls' own consequence, see `_COUNTERS_AND_BECOMES_TYPE_RE`.

    The keyword counter is CR 122.1b: "A keyword counter on a permanent ...
    causes that object to gain that keyword" - stored under the keyword's own
    name (`CardState.counters`'s own docstring), and read back by
    `machines/combat.py::has_keyword` through `printed_characteristics`'s own
    keyword-counter lines. The type change has no target of its own to
    re-announce: it is the same object clause one just put the counters on,
    discovered here rather than asked for again (CR 608.2b's recheck already
    happened once, for the ability's one real target).
    """
    match = _COUNTERS_AND_BECOMES_TYPE_RE.fullmatch(text.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    amount = _count(match.group("n"))
    keyword = match.group("keyword").lower()
    subtype = match.group("subtype").capitalize()

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source_name = ability.source_name
        for target in game.resolve_targets(ability):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            game.add_counters(target, Counter.PLUS_ONE, amount)
            game.add_counters(target, keyword, 1)
            store = continuous_effects(game)
            store.add(
                ContinuousEffect(
                    description=(
                        f"{source_name}: {target.name} becomes a {subtype} "
                        "in addition to its other types"
                    ),
                    layer=Layer.TYPE,
                    timestamp=store.tick(),
                    duration=Duration.INDEFINITE,
                    selector=lambda chars, board, tid=target.id: chars.card_id == tid,
                    modification=add_subtype(subtype),
                )
            )

    return effect


def _parse_reflexive_pay_energy_clause(text: str) -> AbilityEffect | None:
    """ "You may pay {E}{E}{E}. When you do, `<consequence>`." (CR 603.12,
    CR 107.14, CR 118.3) - Guide of Souls' attack trigger, the fixed-amount
    energy-cost twin of `_parse_reflexive_sacrifice_clause`'s sacrifice.

    `Game.may_pay_energy` already asks CR 608.2d's question and pays exactly
    the right amount - built for Static Prison's "unless you pay {E}" - so
    this only has to ask it in the affirmative sense and, only once it comes
    back true, create the reflexive ability the same way the sacrifice
    version does. A "no" answer - unaffordable or declined - spends no energy
    and creates nothing, the same "the cost stays paid, the trigger does not
    exist otherwise" shape as the sacrifice version, just for a cost that
    cannot be un-paid because it never was.
    """
    match = _REFLEXIVE_MAY_PAY_ENERGY_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    amount = len(re.findall(r"\{e\}", match.group("energy"), re.IGNORECASE))
    consequence_text = match.group("consequence").strip()
    consequence_effect = _parse_counters_and_becomes_type_clause(
        consequence_text
    ) or parse_mixed_effect(consequence_text)
    if consequence_effect is None:
        return None

    def resolve_reflexive(
        game: "Game", reflexive_ability: AbilityOnStack, trigger: DelayedTrigger
    ) -> None:
        consequence_effect(game, reflexive_ability)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.controller_of(ability)
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        paid = game.may_pay_energy(player, amount, source=source_name)
        if not paid:
            return
        game.create_reflexive_trigger(
            text=consequence_text,
            controller=player.username,
            source_id=ability.source_id,
            source_name=source_name,
            callback=resolve_reflexive,
        )

    return effect


#: "Create `<n>` `<token description>` token[s]." with no "you may" at all -
#: CR 603.12's "allow **or instruct**" read the mandatory way. Ajani, Nacatl
#: Avenger's `0`: "Create a 2/1 white Cat Warrior creature token. When you
#: do, ...".
_REFLEXIVE_MANDATORY_TOKEN_RE = re.compile(
    r"^(?P<action>create .+? tokens?)\.\s*when you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)

#: "if you control a[n] `<color>` permanent other than `<name>`, [he|she|it|
#: they] deals damage equal to `<expr>` to any target." - the intervening
#: *if* (CR 603.4) nested inside Ajani, Nacatl Avenger's own reflexive
#: clause. `<name>` is read and thrown away: "other than Ajani" is CR 400.7's
#: self-reference (this permanent is the only "Ajani" the sentence could
#: mean), the same idiom `machines/triggers.py`'s own `_self_referential`
#: reads for an ordinary trigger's condition, so the exclusion is applied by
#: id (the ability's own source) rather than by matching the captured name.
_IF_CONTROL_COLORED_PERMANENT_DEALS_DAMAGE_RE = re.compile(
    r"^if you control an? (?P<color>white|blue|black|red|green) permanent other than "
    r"[a-z' ]+?,\s*(?:he|she|they|it) deals damage equal to (?P<expr>.+?) to any target\.?$",
    re.IGNORECASE,
)


def _parse_if_control_colored_permanent_damage_clause(
    text: str,
) -> tuple[Callable[["Game", str, UUID | None], bool], AbilityEffect] | None:
    """The condition-and-damage pair `_IF_CONTROL_COLORED_PERMANENT_DEALS_
    DAMAGE_RE` reads, split apart so a caller can check CR 603.4's condition
    once - at whatever moment it decides is "checked immediately" (CR 603.12)
    - rather than re-deriving it from the consequence text a second time.
    """
    match = _IF_CONTROL_COLORED_PERMANENT_DEALS_DAMAGE_RE.fullmatch(text.strip())
    if match is None:
        return None
    color = _TOKEN_COLOR_WORDS.get(match.group("color").lower())
    if color is None:
        return None
    count_fn = count_expression(match.group("expr"))
    if count_fn is None:
        return None

    def condition_holds(game: "Game", controller: str, excluded_id: UUID | None) -> bool:
        board = game.computed_board()
        return any(
            permanent.id != excluded_id
            and board.of(permanent).controller == controller
            and color in board.of(permanent).colors
            for permanent in game.battlefield
        )

    def deal_the_damage(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        amount = count_fn(game, controller.username)
        if amount <= 0:
            return
        source = ability.source(game)
        for target in game.resolve_targets(ability):
            game.deal_damage(target, amount, source=source)

    return condition_holds, deal_the_damage


def _parse_reflexive_mandatory_token_clause(text: str) -> AbilityEffect | None:
    """ "Create `<n>` `<token>` token[s]. When you do, if ..., `<damage>`."
    (CR 603.12, CR 603.4) - Ajani, Nacatl Avenger's `0`.

    CR 603.12 reads "allow or instruct" - this is the "instruct" half, so
    there is no `MAY` decision at all: the token is simply created, and the
    reflexive ability is created right after, exactly as the sacrifice and
    energy versions do once *their* optional action goes through. What is
    still conditional is CR 603.4's intervening *if*, nested one level in -
    checked here, immediately after the token exists (CR 603.12's own
    "checked immediately after being created"), so a controller who does not
    control a qualifying permanent gets a token and no reflexive ability at
    all, not a reflexive ability that quietly does nothing when it resolves.
    """
    match = _REFLEXIVE_MANDATORY_TOKEN_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    action_text = match.group("action").strip() + "."
    consequence_text = match.group("consequence").strip()
    token_match = _TOKEN_CLAUSE_RE.fullmatch(action_text)
    if token_match is None:
        return None
    count = _count(token_match.group("n"))
    words = token_match.group("desc").strip().split()
    tail = token_match.group("tail")
    if not words:
        return None
    predefined_name = " ".join(words)
    definition = (
        PREDEFINED[predefined_name]
        if tail is None and predefined_name in PREDEFINED
        else _parse_generic_token_descriptor(words, tail)
    )
    if definition is None:
        return None
    condition_and_damage = _parse_if_control_colored_permanent_damage_clause(consequence_text)
    if condition_and_damage is None:
        return None
    condition_holds, deal_the_damage = condition_and_damage

    def resolve_reflexive(
        game: "Game", reflexive_ability: AbilityOnStack, trigger: DelayedTrigger
    ) -> None:
        deal_the_damage(game, reflexive_ability)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        created = create_tokens(game, definition, controller.username, count)
        if not created:
            # CR 603.12: the action never actually happened (a replacement
            # effect ate it), so there is nothing to reflect.
            return
        if not condition_holds(game, controller.username, ability.source_id):
            return
        game.create_reflexive_trigger(
            text=consequence_text,
            controller=controller.username,
            source_id=ability.source_id,
            source_name=source_name,
            callback=resolve_reflexive,
        )

    return effect


#: Cori-Steel Cutter's *Flurry* trigger: "create a 1/1 white Monk creature
#: token with prowess. You may attach this Equipment to it." CR 701.3a's
#: "attach" is the general action - "take it from where it currently is and
#: put it onto that object" - not one CR 702.6a's own Equip ability alone
#: performs, so a resolving ability naming the attach directly is this same
#: action reached a different way, offered as CR 608.2d's ordinary "you may"
#: once the token exists to be attached to. Written as one shape
#: ("...token[s]. You may attach this Equipment to it/them.") rather than
#: keyed to this one card's name, so any future Equipment printed the same
#: way reaches it too.
_CREATE_TOKEN_THEN_MAY_ATTACH_RE = re.compile(
    r"^(?P<action>create .+?)\.\s*"
    r"you may attach this (?:equipment|permanent) to (?:it|them)\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_create_token_then_may_attach_clause(text: str) -> AbilityEffect | None:
    """`_CREATE_TOKEN_THEN_MAY_ATTACH_RE`'s shape.

    The token is always created (CR 603.12's "instruct" half); only the
    attachment is optional (`DecisionKind.MAY`, CR 608.2d), asked once the
    token is real so a declined attachment leaves the Equipment right where
    it was. Only the single-token case is handled - the only shape the pool
    prints - since "it" has no well-defined referent once more than one token
    was created (CR 407.4's "it" is singular).
    """
    match = _CREATE_TOKEN_THEN_MAY_ATTACH_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    # No trailing period appended, unlike the reflexive-mandatory-token
    # sibling above: `_TOKEN_CLAUSE_RE`'s own `tail` group is greedy, so a
    # period handed to it becomes part of the tail ("prowess.") and
    # `_parse_token_tail` reads that as an unknown keyword - `split_effect_
    # clauses`'s `text.rstrip(".")` is what keeps every *other* caller of
    # this regex from ever presenting one.
    action_text = match.group("action").strip()
    token_match = _TOKEN_CLAUSE_RE.fullmatch(action_text)
    if token_match is None:
        return None
    count = _count(token_match.group("n"))
    if count != 1:
        return None
    words = token_match.group("desc").strip().split()
    tail = token_match.group("tail")
    if not words:
        return None
    predefined_name = " ".join(words)
    definition = (
        PREDEFINED[predefined_name]
        if tail is None and predefined_name in PREDEFINED
        else _parse_generic_token_descriptor(words, tail)
    )
    if definition is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        created = create_tokens(game, definition, controller.username, count)
        if not created:
            return
        token = created[0]
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        decision = game.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=controller.username,
                prompt=f"attach {source.name} to {token.name}",
                source=ability.source_name,
                affirmative_is_legal=True,
            )
        )
        if decision:
            source.attach_to(token)

    return effect


# --------------------------------------------------------------------------
# Fight (CR 701.14) and Kraul Harpooner's own pump-then-fight shape
# --------------------------------------------------------------------------


def _fight(game: "Game", a: CardState, b: CardState) -> None:
    """CR 701.14a: "Each of those creatures deals damage equal to its power to
    the other creature." Simultaneous - neither call below sees the other's
    result, since state-based actions are not checked until both are done -
    and CR 701.14d: "The damage dealt when a creature fights isn't combat
    damage," so nothing here touches `machines/combat.py`.

    CR 701.14b: "If one or both creatures instructed to fight are no longer on
    the battlefield or are no longer creatures, neither of them fights or
    deals damage" - checked by every caller before this is reached, not
    re-checked here, the same division of labour `destroy_ability_targets`
    already draws between "is this still legal" and "do the thing".
    """
    power_a = game.power_of(a) or 0
    power_b = game.power_of(b) or 0
    game.deal_damage(b, power_a, source=a)
    game.deal_damage(a, power_b, source=b)


#: Kraul Harpooner's own enters trigger, read whole ahead of the per-clause
#: splitter for the same reason `_EACH_PLAYER_EXILE_SACRIFICE_RETURN_RE` is:
#: the fight clause's "that creature" is anaphoric (CR 400.7) for whatever
#: `<phrase>` names, and the pump's own magnitude is `count_expression`'s
#: "the number of creature cards in your graveyard" - both belong to one CR
#: 608.2c instruction, not three independent clauses `_CLAUSE_SEPARATOR`'s
#: "then"/"," cuts would otherwise scatter. The ability word ("Undergrowth
#: — ") is already stripped by `machines/abilities.py` before this text is
#: ever seen (CR 207.2c).
_UNDERGROWTH_PUMP_AND_FIGHT_RE = re.compile(
    r"^choose (?P<phrase>up to \S+ target [^.]+)\.\s*"
    r"this creature gets \+x/\+0 until end of turn,\s*where x is (?P<expr>[^,]+),\s*"
    r"then you may have this creature fight that creature\.?$",
    re.IGNORECASE,
)


def _parse_undergrowth_pump_and_fight_clause(text: str) -> AbilityEffect | None:
    """Kraul Harpooner: "choose up to one target creature you don't control
    with flying. This creature gets +X/+0 until end of turn, where X is the
    number of creature cards in your graveyard, then you may have this
    creature fight that creature."

    Printed order (CR 608.2c): the pump always happens - X is computed and
    applied whether or not a target was chosen (CR 115.6's "up to one"
    legally choosing zero, trap this file's own docstring calls out) - and
    only *then* does the optional fight ask its `MAY` question, and only if
    there is a "that creature" for it to name at all.
    """
    whole = _strip_non_effect_preamble(text).strip()
    match = _UNDERGROWTH_PUMP_AND_FIGHT_RE.fullmatch(whole)
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    count_fn = count_expression(match.group("expr"))
    if count_fn is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        controller = game.controller_of(ability)
        amount = count_fn(game, controller.username)
        store = continuous_effects(game)
        store.add(
            ContinuousEffect(
                description=f"{source.name} gets +{amount}/+0 until end of turn",
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=store.tick(),
                duration=Duration.UNTIL_END_OF_TURN,
                selector=lambda chars, board, sid=source.id: chars.card_id == sid,
                modification=modify_power_toughness(amount, 0),
            )
        )
        targets = [
            target for target in game.resolve_targets(ability) if isinstance(target, CardState)
        ]
        if not targets:
            # CR 115.6: "up to one" legally chose zero - nothing to fight.
            return
        opponent_creature = targets[0]
        board = game.computed_board()
        if (
            source.zone is not Zone.BATTLEFIELD
            or opponent_creature.zone is not Zone.BATTLEFIELD
            or Type.CREATURE not in board.of(source).types
            or Type.CREATURE not in board.of(opponent_creature).types
        ):
            # CR 701.14b: either is gone, or no longer a creature.
            return
        prompt = f"have {source.name} fight {opponent_creature.name}"
        if not game.may(controller.username, prompt, source=source.name):
            return
        _fight(game, source, opponent_creature)

    return effect


# --------------------------------------------------------------------------
# Dalkovan Encampment's own "whenever you attack this turn" delayed trigger
# --------------------------------------------------------------------------
#
# "{2}{W}, {T}: Whenever you attack this turn, create two 1/1 red Warrior
# creature tokens that are tapped and attacking. Sacrifice them at the
# beginning of the next end step." Activating this ability does not itself
# create any tokens - CR 603.7a: it creates a *delayed* triggered ability
# (`machines/delayed.py`) that watches for "you attack" (CR 508.3d, the same
# subjectless per-attacking-player event `machines/triggers.py` already reads
# for Guide of Souls) and fires **on every attack for the rest of this turn**,
# not once - CR 603.7b's "unless it has a stated duration, such as 'this
# turn'" is exactly Dalkovan's own words, so `remaining=None` plus
# `expires_end_of_turn=True` (swept by `DelayedTriggers.expire_this_turn` in
# `Game.cleanup_step`, CR 514.2) is what keeps it from also firing on the
# next turn's attack.
#
# Each firing creates its own two tokens tapped and attacking (CR 508.4,
# already proven directly in `tests/scenarios/test_tokens.py`), attacking
# whichever defender the activating player is already attacking - the
# tokens have no defender of their own printed anywhere, so this reads it
# off the controller's own currently-declared attack, CR 102.2's two-player
# default when more than one exists. Each token created this way gets its
# *own* one-shot delayed trigger reusing the existing `"sacrifice"` entry in
# `DELAYED_EFFECTS` (`_sacrifice_subject`) - the same "sacrifice this
# specific object at the next end step" idiom `return_subject_to_hand`'s
# siblings already use, not a new plural-subject field on `DelayedTrigger`.

_ATTACK_THIS_TURN_TAPPED_ATTACKING_TOKENS_RE = re.compile(
    r"^whenever you attack this turn,\s*create (?P<n>\w+) (?P<desc>.+?) tokens? "
    r"that are tapped and attacking\.\s*sacrifice them at the beginning of the "
    r"next end step\.?$",
    re.IGNORECASE,
)


def _parse_attack_this_turn_create_tapped_attacking_tokens(text: str) -> AbilityEffect | None:
    match = _ATTACK_THIS_TURN_TAPPED_ATTACKING_TOKENS_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    count = _count(match.group("n"))
    words = match.group("desc").strip().split()
    definition = _parse_generic_token_descriptor(words, None)
    if definition is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)

        def create_attacking_tokens(
            game: "Game", trigger_ability: AbilityOnStack, trigger: DelayedTrigger
        ) -> None:
            defender = next(
                (
                    attack.defender
                    for attack in game.combat.attacks
                    if (attacker := game.find_by_id(attack.attacker_id)) is not None
                    and game.controller_of(attacker).username == controller.username
                ),
                None,
            )
            created = create_tokens(
                game,
                definition,
                controller.username,
                count,
                tapped=True,
                attacking=defender,
            )
            for token in created:
                game.create_delayed_trigger(
                    DelayedTrigger(
                        text="Sacrifice them at the beginning of the next end step.",
                        effect="sacrifice",
                        event=TriggerEvent.BEGINNING_OF_STEP,
                        step=Step.END_STEP,
                        controller=controller.username,
                        source_id=source_id,
                        source_name=source_name,
                        subject_id=token.id,
                        expected_zone=Zone.BATTLEFIELD,
                        expected_stamp=token.zone_change_stamp,
                    )
                )

        game.create_delayed_trigger(
            DelayedTrigger(
                text=match.group(0),
                event=TriggerEvent.ATTACKS,
                controller=controller.username,
                source_id=source_id,
                source_name=source_name,
                # `only_when_active` only ever compares `event.player` against
                # this name (`DelayedTrigger.matches`) - CR 508.1a already
                # limits attack declaration to the active player, so reusing
                # it as "the event's own attacking player" rather than adding
                # a second, identical-in-effect field is exact, not a stretch.
                only_when_active=controller.username,
                subjectless_only=True,
                remaining=None,
                expires_end_of_turn=True,
                callback=create_attacking_tokens,
            )
        )

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


#: "Look at target player's hand." (Gitaxian Probe) - the same CR 701.20e
#: no-op as `_LOOK_AT_TOP_CARD_RE`, except the thing looked at is a player's
#: hand rather than a library's top card, so `machines/targeting.py` reads
#: "target player's hand" as targeting the *player* (its own module-level
#: docstring lists this exact phrase as one it reads that way).
_LOOK_AT_TARGET_HAND_RE = re.compile(r"^look at target player'?s hand$", re.IGNORECASE)


def _look_at_target_hand(game: "Game", stack_object: "StackObject") -> None:
    """No-op (CR 701.20e) - see `_look_at_top_card`. Still resolves the
    target so a player who has left the game by resolution is refused the
    ordinary way (CR 608.2b)."""
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


#: "Return target creature card [with mana value N or X] from your graveyard
#: to the battlefield." - Postmortem Lunge's own reanimation clause, read
#: generically off the shape (not off the card's name): any card printing
#: this exact template gets the same treatment. A bare "X" is accepted here
#: (unlike `_extract_comparison`'s own unbound-X refusal) because this clause
#: never reads the number itself - the actual mana-value *legality* of the
#: target is enforced entirely by `machines/targeting.py`'s `TargetRequirement.
#: comparison_value`, fed by `Casting.targeting`'s own X substitution
#: (CR 107.3a) once the caster announces X, which happens independently of
#: this parser matching at all. Matching on the very first, unsubstituted
#: pass also sidesteps `_unreadable_delayed_clause`'s own fallback: without
#: this, `effect_for`'s first pass would read nothing here, fall through to
#: that notice for the still-unmatched "exile it at the beginning of the next
#: end step" clause, and return the notice before X substitution ever ran
#: (its own docstring's "only if that first pass reads nothing" only helps a
#: caller whose *first* pass reads `None`, not one that reads a competing
#: notice instead).
_RETURN_CREATURE_CARD_FROM_GRAVEYARD_TO_BATTLEFIELD_RE = re.compile(
    r"^return (?P<phrase>target creature card(?: with mana value (?:\d+|x))? "
    r"from your graveyard) to the battlefield$",
    re.IGNORECASE,
)


def _parse_delayed_reanimate_haste_exile_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """ "Return target creature card [with mana value N] from your graveyard
    to the battlefield. It gains haste. Exile it at the beginning of the next
    end step." as one CR 608.2c instruction (Postmortem Lunge) - three
    consecutive clauses starting at `index`, or `None` if `index` is not the
    start of this shape.

    The linkage is CR 400.7 anaphora twice over, the same reasoning
    `_parse_delayed_blink_clauses` already documents for its own "that card":
    "it" in clause two and clause three both mean whatever clause one's own
    return just put onto the battlefield, discovered only as clause one
    actually runs - so this closes over the entered `CardState` rather than
    resolving either later sentence's target of its own.

    Haste is granted with `Duration.INDEFINITE` (CR 611.2a's default: "if no
    duration is stated, it lasts indefinitely") scoped to `only_this_
    incarnation` - the object is about to be exiled by the delayed trigger
    anyway, but a response that saves it from that exile should not also
    strip the haste a literal reading of the card never granted with a time
    limit.
    """
    return_match = _RETURN_CREATURE_CARD_FROM_GRAVEYARD_TO_BATTLEFIELD_RE.fullmatch(
        clauses[index].strip().rstrip(".")
    )
    if return_match is None:
        return None
    if not _targets_understood(return_match.group("phrase"), battlefield_only=False):
        return None
    if index + 2 >= len(clauses):
        return None
    if clauses[index + 1].strip().rstrip(".").lower() != "it gains haste":
        return None
    timing = _parse_delayed_timing_clause(clauses[index + 2])
    if timing is None:
        return None
    step, verb = timing
    if verb.strip().lower() != "exile it":
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source_name = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = stack_object.id if for_spell else stack_object.source_id  # type: ignore[union-attr]
        controller = game.controller_of(stack_object).username
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, CardState) or target.zone is not Zone.GRAVEYARD:
                continue
            entered = game.put_onto_battlefield(target, controller, tapped=False)
            if entered.zone is not Zone.BATTLEFIELD:
                continue  # a replacement effect sent it elsewhere (CR 614.6)
            store = continuous_effects(game)
            timestamp = store.tick()
            store.add(
                ContinuousEffect(
                    description=f"{source_name}: {entered.name} gains haste",
                    layer=Layer.ABILITY,
                    timestamp=timestamp,
                    selector=only_this_incarnation(entered, entered.zone_change_stamp),
                    modification=grant_ability("Haste"),
                )
            )
            game.create_delayed_trigger(
                DelayedTrigger(
                    text=clauses[index + 2],
                    event=TriggerEvent.BEGINNING_OF_STEP,
                    step=step,
                    controller=controller,
                    source_id=source_id,
                    source_name=source_name,
                    subject_id=entered.id,
                    expected_zone=Zone.BATTLEFIELD,
                    expected_stamp=entered.zone_change_stamp,
                    callback=exile_subject_at_next_end_step,
                )
            )

    return 3, effect


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


class ControlReplacementNotice(BaseModel):
    """A resolving spell's own "if [a permanent] would enter the battlefield
    under [a player]'s control [this turn], it enters under [another
    player]'s control instead" (CR 614.1a's `IF_WOULD_INSTEAD` shape,
    `machines/replacement.py`'s own `ReplacementKind.IF_WOULD_INSTEAD`) -
    recognised by shape, but not built.

    Two things this engine has nowhere to put, not one: `ReplaceableEvent`
    (`machines/replacement.py`) has no field a replacement could set to
    redirect an entering permanent's controller - `Game.put_onto_battlefield`
    sets `card_state.controller` *before* `apply_replacements` runs and never
    reconsiders it - and `machines/replacement.py`'s own `parse_replacement_
    effects` only ever reads a *permanent's own printed* static ability text;
    nothing here represents a temporary, "this turn"-scoped replacement rule
    conjured by a resolving instant or sorcery and watching every future
    zone change rather than one printed source. Gather Specimens needs both.
    Recorded rather than silently dropped, the same "unreadable is not the
    same as no effect" convention every other notice class here keeps.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str


#: Gather Specimens' own templated shape - see `ControlReplacementNotice`.
_CONTROL_REPLACEMENT_RE = re.compile(
    r"^if a? ?[a-z]+ would enter the battlefield under an? [a-z' ]+'?s control"
    r"(?: this turn)?, it enters under [a-z' ]+ control instead\.?$",
    re.IGNORECASE,
)


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
    a mechanism this engine has nowhere to put: a choice
    between zero and many cards with no fixed count (Nashi's "you may put any
    number of ... into your hand" - `DecisionKind.CHOOSE_CARDS` in
    `machines/decisions.py` only knows how to ask for an exact `amount`, never
    "as many as you like"), or a target chosen at CR 603.3d announcement but
    restricted to what a upstream game *event* says rather than what the
    ability's own printed text says (Questing Beast's "target planeswalker
    **that player** controls", where "that player" is whoever the trigger's
    own combat damage was dealt to - `machines/targeting.profile_for_text`
    only ever reads a targeting restriction off the ability's static text).

    Each of these is a missing primitive, not a hard-to-parse sentence, so the
    ability still triggers and goes on the stack (CR 603.3), and this is the
    "unreadable is not the same as no effect" record every other notice list
    in this module already keeps, rather than the ability silently doing
    nothing with no trace of why.

    **Ragavan, Nimble Pilferer used to be the third card here** - "until end of
    turn, you may cast that card" - and is not any more: the per-instance,
    time-boxed permission it names is built, as `machines/casting.
    PlayPermission` and `Game.grant_play_permission`. What is left of that
    shape here is `_unreadable_cast_permission_clause`, which now only fires
    for a permission sentence whose *antecedent* clause this file cannot read -
    a "you may cast that card" with no recognisable exiling clause in front of
    it to say which card - since granting a permission over nothing at all
    would be the silent half-run this notice exists to prevent.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    """The unread portion of the ability's printed effect, or the whole of it
    when none of it runs."""


#: "until end of turn, you may cast that card"/"you may cast it"/"you may cast
#: those cards" - the *orphaned* form of the sentence `_PLAY_PERMISSION_RE`
#: reads as half of `_parse_exile_then_play_permission_pair`. Reached only when
#: that pair parser refused, which for this sentence means one thing: the
#: clause in front of it is not an exiling clause this file can read, so there
#: is no antecedent for "that card" (CR 607.1) and no object to grant a
#: permission over. Granting nothing, or guessing at an object, is the silent
#: half-run the notice exists to prevent.
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


#: "defending player exiles the top twenty cards of their library" - Ulamog,
#: the Ceaseless Hunger's own attack trigger. "Defending player" is CR
#: 508.5/508.6's anaphora back to the attack the trigger's own condition
#: ("Whenever Ulamog attacks") watched: the player, or - had the attack named
#: a planeswalker or a battle - that permanent's controller, worked out by
#: `machines.combat.defending_player` off the event's own `defender`
#: (`GameEvent.defender`, CR 508.1a). Not a target: CR 601.2c never runs for a
#: triggered ability with no printed "target", so this reads `ability.event`
#: exactly as `_parse_exile_that_players_library_clause` reads "that player"
#: off a different event field just above.
_DEFENDING_PLAYER_EXILES_TOP_N_RE = re.compile(
    rf"^defending player exiles the top (?P<count>{_COUNT}) cards? of their library$",
    re.IGNORECASE,
)


def _parse_defending_player_exiles_top_n_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """Ability-only (`for_spell=False`): a spell has no `ability.event` to
    resolve "defending player" against, and no spell in the pool attacks.
    """
    if for_spell:
        return None
    match = _DEFENDING_PLAYER_EXILES_TOP_N_RE.fullmatch(clause.strip())
    if match is None:
        return None
    count = _count(match.group("count"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        event = ability.event
        if event is None or event.defender is None:
            return
        username = combat_rules.defending_player(game, event.defender)
        if username is None:
            return
        player = game.player(username)
        for card in player.library[:count]:
            game.exile_permanent(card)

    return effect


#: "defending player reveals the top card of their library. If it's a land
#: card, that player puts it into their hand." - Goblin Guide's own attack
#: trigger. Read whole (CR 608.2c: one instruction, not two independent
#: ones - the second sentence's "that player" is CR 400.7 anaphora back to
#: the "defending player" the first sentence just resolved, so this has to
#: stay one function the way `delver_upkeep`'s reveal-then-maybe-transform
#: does, rather than being split into two clauses the way an ordinary
#: "reveal ..., then ..." pair would be). "Defending player" is read exactly
#: as `_parse_defending_player_exiles_top_n_clause` reads it, off
#: `ability.event.defender` (CR 508.1a) through `machines.combat.
#: defending_player` - **the withheld or granted party is the player
#: Goblin Guide is attacking, never Goblin Guide's own controller**, which
#: is the specific "wrong player" bug this shape exists to catch.
_DEFENDING_PLAYER_REVEALS_TOP_CONDITIONAL_LAND_RE = re.compile(
    r"^defending player reveals the top card of their library\.\s*"
    r"if it'?s a land card, that player puts it into their hand\.?$",
    re.IGNORECASE,
)


def _parse_defending_player_reveals_top_conditional_land_clause(
    text: str,
) -> AbilityEffect | None:
    """`_DEFENDING_PLAYER_REVEALS_TOP_CONDITIONAL_LAND_RE`'s shape - Goblin
    Guide's whole attack trigger (CR 701.20a's reveal, CR 205.2a's land type
    check, CR 401 for the library-to-hand move).
    """
    if _DEFENDING_PLAYER_REVEALS_TOP_CONDITIONAL_LAND_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        if event is None or event.defender is None:
            return
        username = combat_rules.defending_player(game, event.defender)
        if username is None:
            return
        player = game.player(username)
        if not player.library:
            return
        top = player.library[0]
        game.reveal(top, source=ability.source_name)
        if Type.LAND in top.card.types:
            player.move(top, Zone.HAND)

    return effect


#: "Counter that spell." - Vexing Bauble's and Chalice of the Void's own
#: templated effect clause, both times following a `TriggerEvent.CAST_SPELL`
#: condition. "That spell" is **CR 607.1** linked-ability anaphora back to the
#: spell whose casting made the ability trigger, not something CR 601.2c ever
#: asked this ability's controller to choose as a target - the same
#: `ability.event`-not-`stack_object.targets` distinction
#: `_parse_exile_that_players_library_clause` right above draws for "that
#: player's library".
_COUNTER_THAT_SPELL_RE = re.compile(r"^counter that spell$", re.IGNORECASE)


def _parse_counter_that_spell_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """Ability-only (`for_spell=False`): a spell has no `ability.event` to
    resolve "that spell" against, and nothing in the pool prints this clause
    on a spell rather than a triggered ability.

    Read by shape rather than by card name, so a future card printing this
    exact clause after any `CAST_SPELL` condition is covered for free -
    unlike a `TRIGGER_EFFECTS` row keyed to one card, which cannot.
    """
    if for_spell:
        return None
    if not _COUNTER_THAT_SPELL_RE.fullmatch(clause.strip()):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        event = ability.event
        if event is None or event.subject_id is None:
            return
        spell = game.find_by_id(event.subject_id)
        # **CR 701.6a**: "A countered spell is put into its owner's
        # graveyard" - by way of `Game.counter`, which also honours a
        # rebound or flashback spell's own replaced destination rather than
        # always the graveyard. A spell that has already left the stack
        # (countered first, or resolved ahead of this ability) is simply not
        # there to counter - the ordinary CR 608.2b "the target is gone"
        # outcome, even though this was never a target to begin with.
        if spell is not None and spell in game.stack:
            game.counter(spell)

    return effect


#: "This creature deals N damage to that spell's controller." - Bonecrusher
#: Giant's own "becomes the target of a spell" trigger (CR 702.21a's own
#: event, `TriggerEvent.BECOMES_TARGET`, generic and not ward-specific -
#: `Casting._emit_becomes_target` raises it for *any* spell that targets a
#: permanent). "That spell" here is `GameEvent.targeted_by` (CR 702.21a: "the
#: spell ... that's targeting" the subject), not `event.subject_id` - the
#: subject of a BECOMES_TARGET event is the permanent that got targeted
#: (Bonecrusher Giant itself), and the spell that did the targeting is a
#: second, separate object the event carries under its own field. Reading
#: `event.subject_id` here, the way `_parse_counter_that_spell_clause` reads
#: it for a *CAST_SPELL* condition's "that spell", would ask who controls
#: Bonecrusher Giant instead of who cast the spell that targeted it.
_DAMAGE_TO_THAT_SPELLS_CONTROLLER_RE = re.compile(
    r"^this (?:creature|permanent) deals (?P<n>\d+) damage to that spell'?s controller\.?$",
    re.IGNORECASE,
)


def _parse_damage_to_that_spells_controller_clause(text: str) -> AbilityEffect | None:
    """`_DAMAGE_TO_THAT_SPELLS_CONTROLLER_RE`'s shape - Bonecrusher Giant's
    whole trigger (CR 120.1, 120.3a: damage to a player)."""
    match = _DAMAGE_TO_THAT_SPELLS_CONTROLLER_RE.fullmatch(text.strip())
    if match is None:
        return None
    amount = int(match.group("n"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        if event is None or event.targeted_by is None:
            return
        spell = game.find_by_id(event.targeted_by)
        if spell is None:
            return
        controller = game.controller_of(spell)
        game.deal_damage(controller, amount, source=ability.source(game))

    return effect


#: "Target creature gets +2/+0 until end of turn for each card discarded
#: this way. Whenever that creature deals combat damage to a player this
#: turn, you draw a card." - Captain Howler, Sea Scourge's whole discard
#: trigger, read as one CR 608.2c instruction: the pump's magnitude is "for
#: each card discarded this way" (CR 607.1 anaphora back to this ability's
#: own `TriggerEvent.DISCARDS_A_CARD` event, `GameEvent.amount` - see
#: `Game.discard_cards`), and the second sentence creates a CR 603.7 delayed
#: triggered ability watching "that creature" (CR 603.7c's `subject_id`) for
#: the rest of the turn (`expires_end_of_turn=True`).
_PUMP_PER_DISCARD_THEN_DELAYED_DRAW_RE = re.compile(
    r"^target creature gets \+(?P<power>\d+)/\+(?P<toughness>\d+) until end of turn "
    r"for each card discarded this way\.\s*"
    r"whenever that creature deals combat damage to a player this turn, "
    r"you draw a card\.?$",
    re.IGNORECASE,
)


def _parse_pump_per_discard_then_delayed_draw_clause(text: str) -> AbilityEffect | None:
    """`_PUMP_PER_DISCARD_THEN_DELAYED_DRAW_RE`'s shape - Captain Howler,
    Sea Scourge's whole trigger (CR 119.3's pump has no such rule number of
    its own beyond CR 611.2's one-shot effect; CR 603.7 for the delayed half;
    CR 120.2a for "deals combat damage to a player"; CR 121.1 for the draw).
    """
    match = _PUMP_PER_DISCARD_THEN_DELAYED_DRAW_RE.fullmatch(text.strip())
    if match is None:
        return None
    if not _targets_understood("target creature"):
        return None
    per_power = int(match.group("power"))
    per_toughness = int(match.group("toughness"))

    def combat_damage_to_player_draw(
        game: "Game", stacked: AbilityOnStack, trigger: "DelayedTrigger"
    ) -> None:
        # `matches()` only checks the event kind and the subject's id (CR
        # 603.7c); "combat damage" and "to a player" are this delayed
        # trigger's own narrower condition, the same two checks
        # `machines/triggers.condition_matches`'s DEALS_DAMAGE branch makes
        # for a printed version of this shape.
        event = stacked.event
        if event is None or not event.combat or event.player is None:
            return
        if not game.is_in_game(trigger.controller):
            return
        game.draw_cards(trigger.controller, 1)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        discard_count = event.amount if event is not None and event.amount is not None else 0
        if discard_count <= 0:
            return
        targets = [
            target for target in game.resolve_targets(ability) if isinstance(target, CardState)
        ]
        if not targets:
            return
        target = targets[0]
        magnitude = discard_count * per_power
        store = continuous_effects(game)
        store.add(
            ContinuousEffect(
                description=(
                    f"{target.name} gets +{magnitude}/+{discard_count * per_toughness} "
                    "until end of turn"
                ),
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=store.tick(),
                duration=Duration.UNTIL_END_OF_TURN,
                selector=lambda chars, board, tid=target.id: chars.card_id == tid,
                modification=modify_power_toughness(magnitude, discard_count * per_toughness),
            )
        )
        controller = game.controller_of(ability)
        game.create_delayed_trigger(
            DelayedTrigger(
                text=(
                    "Whenever that creature deals combat damage to a player "
                    "this turn, you draw a card."
                ),
                controller=controller.username,
                source_id=ability.source_id,
                source_name=ability.source_name,
                event=TriggerEvent.DEALS_DAMAGE,
                subject_id=target.id,
                remaining=None,
                expires_end_of_turn=True,
                callback=combat_damage_to_player_draw,
            )
        )

    return effect


# --------------------------------------------------------------------------
# "Until end of turn, you may cast/play [it|that card|those cards]"
# (CR 601.3, CR 601.1a, CR 514.2)
# --------------------------------------------------------------------------
#
# Two cards in the pool print this, and they differ in every way that matters:
# Ragavan, Nimble Pilferer exiles **one** card, from an **opponent's** library,
# and may cast it for its own mana cost; Ugin, Eye of the Storms' −11 exiles
# **any number** of cards, from **its own controller's** library, and casts
# them for nothing (CR 118.9's "without paying its mana cost"). Both halves are
# read off the printed sentence pair rather than keyed by card name, so a
# future card printing the same shape is covered with no registry row.
#
# The permission itself is `machines/casting.PlayPermission`, handed out by
# `Game.grant_play_permission`. This module only reads the sentence and names
# the cards; see that class for why the permission is per-object and bounded.

#: The second sentence of the pair. "Play" and "cast" are kept apart on purpose
#: (CR 601.1a, CR 701.18b: playing a card is playing it as a land *or* casting
#: it as a spell), and "without paying its/their mana cost(s)" is CR 118.9's
#: alternative cost of nothing, which CR 107.3b keeps distinct from an
#: alternative cost with something in it.
_PLAY_PERMISSION_RE = re.compile(
    r"^until end of turn, you may (?P<action>cast|play) "
    r"(?P<subject>it|that card|those cards|them)"
    r"(?P<free> without paying (?:its|their) mana costs?)?$",
    re.IGNORECASE,
)

#: The plural pronouns. CR 607.1's within-one-ability anaphora has to agree in
#: number with the clause it points back at: "that card" cannot refer to a
#: search that exiled four cards, and "those cards" cannot refer to a single
#: exiled top card. Refusing a mismatch is what keeps a future card's sentence
#: from being read as a shape it is not.
_PLURAL_PERMISSION_SUBJECTS = frozenset({"those cards", "them"})

#: "Search your library for any number of <quality> cards, exile them, then
#: shuffle" - Ugin, Eye of the Storms' −11. Distinct from `_SEARCH_AND_PUT_RE`
#: in three ways, which is why it is its own pattern rather than another
#: alternative in that one: the count is CR 107.1c's "any number" rather than
#: "a card", the destination is exile rather than the hand or the battlefield,
#: and the sentence has a second sentence bound to it (the permission above)
#: that `_SEARCH_AND_PUT_RE`'s `fullmatch` discipline would refuse anyway.
_SEARCH_AND_EXILE_ANY_NUMBER_RE = re.compile(
    r"^search your library for any number of (?P<quality>.+?) cards, "
    r"exile them, then shuffle$",
    re.IGNORECASE,
)


def _type_word_is_readable(word: str) -> bool:
    """Whether `_named_type_matcher` can really read this one quality word.

    Only CR 205.2a's card types, optionally negated with "non" (CR 109.2), are
    accepted. A land subtype (CR 205.3i) is deliberately not: `has_land_type`
    matches any string against a card's subtypes and so can never *fail*,
    which makes it useless as a readability test - a typo would validate.
    Failing closed here is what sends an unreadable quality to a notice
    instead of to a search that silently finds nothing.
    """
    lowered = word.strip().lower().removeprefix("non")
    try:
        Type(lowered)
    except ValueError:
        return False
    return True


def _search_quality_is_readable(quality: str) -> bool:
    """Whether every word of a stated quality reaches a real matcher.

    Mirrors `_quality_matcher`'s own splitting - "basic " prefix, then words
    separated by commas or "or", each optionally carrying one of
    `_HAND_EXILE_COLOR_WORDS`' color adjectives (CR 105.2c) - so the two cannot
    drift apart on what counts as readable.
    """
    lowered = quality.strip().lower()
    if lowered.startswith("basic "):
        return _search_quality_is_readable(lowered.removeprefix("basic "))
    words = [word.strip() for word in re.split(r",\s*|\s+or\s+", lowered) if word.strip()]
    if not words:
        return False
    for word in words:
        parts = word.split()
        if len(parts) == 2 and parts[0] in _HAND_EXILE_COLOR_WORDS:
            if not _type_word_is_readable(parts[1]):
                return False
        elif len(parts) != 1 or not _type_word_is_readable(word):
            return False
    return True


#: A clause that exiles cards, read as "which objects the next sentence's
#: pronoun points at" (CR 607.1). Returns the cards it exiled, in the order it
#: exiled them, so the permission clause can be granted against exactly those
#: objects and no others.
ExileAntecedent = Callable[["Game", AbilityOnStack], list[CardState]]


def _parse_exile_antecedent(clause: str) -> tuple[ExileAntecedent, bool] | None:
    """One exiling clause, plus whether it exiles more than one card.

    Two shapes, both already printed in this pool:

    - "exile the top card of that player's library" (Ragavan), where "that
      player" is CR 120.2a's damaged player read off the trigger's own event,
      exactly as `_parse_exile_that_players_library_clause` reads it. The card
      stays **owned** by that player (CR 108.3) - only the permission moves.
    - "search your library for any number of `<quality>` cards, exile them,
      then shuffle" (Ugin's −11). CR 107.1c: "if a rule or ability instructs a
      player to choose 'any number,' that player may choose any positive number
      or zero", so finding nothing is a legal answer and the permission is then
      granted to nothing at all. CR 701.23b says the same from the search's
      side, which is why `optional=True`: every card found is offered
      individually and may be declined.

    Anything else comes back `None`, and the whole two-clause instruction goes
    unread rather than half-read (CR 608.2c).
    """
    stripped = clause.strip()

    if _EXILE_TOP_OF_THAT_PLAYERS_LIBRARY_RE.fullmatch(stripped):

        def exile_top(game: "Game", ability: AbilityOnStack) -> list[CardState]:
            event = ability.event
            username = event.player if event is not None else None
            if username is None:
                return []
            player = game.player(username)
            if not player.library:
                return []
            return [game.exile_permanent(player.library[0])]

        return exile_top, False

    match = _SEARCH_AND_EXILE_ANY_NUMBER_RE.fullmatch(stripped)
    if match is not None:
        quality = match.group("quality")
        if not _search_quality_is_readable(quality):
            return None
        matches = _quality_matcher(quality)

        def search_and_exile(game: "Game", ability: AbilityOnStack) -> list[CardState]:
            player = game.controller_of(ability)
            found = game.search_library(
                player,
                matches,
                count=len(player.library),
                optional=True,
                source=ability.source_name,
            )
            return [game.exile_permanent(card) for card in found]

        return search_and_exile, True

    return None


def _parse_exile_then_play_permission_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "[exile some cards]. Until end of turn, you may cast/play them." as one
    CR 608.2c instruction.

    Read as a *pair* rather than two independent clauses because the second
    sentence has no meaning without the first: its pronoun is CR 607.1's
    within-one-ability anaphora back to whatever the first sentence just
    exiled. Splitting them would either grant a permission over nothing or -
    worse - run the exile and drop the permission, leaving cards in exile their
    controller could never legally use. CR 608.2c has no notion of running half
    an instruction, and this project's paragraph-atomic rule says the same.

    Ability-only (`for_spell=False`): both printings are triggered or loyalty
    abilities, `_parse_exile_antecedent`'s Ragavan shape needs an
    `AbilityOnStack.event` to resolve "that player" against, and a resolving
    spell has no `source_name` to name the granting effect by.
    """
    if for_spell:
        return None
    permission = _PLAY_PERMISSION_RE.fullmatch(second.strip())
    if permission is None:
        return None
    antecedent = _parse_exile_antecedent(first)
    if antecedent is None:
        return None
    exile, exiles_many = antecedent
    plural = permission.group("subject").lower() in _PLURAL_PERMISSION_SUBJECTS
    if plural != exiles_many:
        # The pronoun does not agree in number with the clause it points at, so
        # this is not the shape it looked like. Refuse rather than guess.
        return None
    action = PlayAction.PLAY if permission.group("action").lower() == "play" else PlayAction.CAST
    free = permission.group("free") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        controller = game.controller_of(ability).username
        for card in exile(game, ability):
            game.grant_play_permission(
                card,
                controller,
                action=action,
                pays_mana_cost=not free,
                source_name=ability.source_name,
                rule="CR 601.3",
            )

    return effect


#: "Add <mana>." as a *resolving* effect rather than a mana ability's fast
#: path - Ugin, Eye of the Storms' "0: Add {C}{C}{C}." CR 605.1a's third
#: criterion is "it's not a loyalty ability", and CR 606.2 makes any ability
#: with a loyalty symbol in its cost one, so this ability is not a mana ability
#: at all: CR 605.3b's "doesn't go on the stack" is false of it, it goes on the
#: stack like any other activated ability (CR 602.2, CR 113.3b), and the mana
#: arrives when it resolves. `machines/abilities.py` still parses the `Add`
#: into a `ManaAbility`, and `Game.activate_ability` already refuses it the
#: fast path; this is the resolution half, which had nothing written for it and
#: so silently added no mana at all.
#:
#: A literal run of mana symbols only - a choice of colors, or an amount that
#: depends on the board, is not read here and falls through to no effect rather
#: than to a guess.
_ADD_MANA_RE = re.compile(r"^add (?P<mana>(?:\{[wubrgc]\}\s*)+)$", re.IGNORECASE)


def _parse_add_mana_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Add {C}{C}{C}" on a resolving ability (CR 106.4, CR 605.1a).

    Ability-only (`for_spell=False`): a *spell* cannot be a mana ability
    (CR 605.5, "spells aren't mana abilities"), but no card in this pool prints
    "Add ..." as a spell's whole effect either, and a spell has no
    `AbilityOnStack` controller lookup to differ from the ability one - so this
    stays where the pool's evidence is rather than being opened speculatively.
    """
    if for_spell:
        return None
    match = _ADD_MANA_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    symbols = _MANA_SYMBOL_RE.findall(match.group("mana"))
    colors = [Color(symbol.upper()) for symbol in symbols]

    def effect(game: "Game", stack_object: "StackObject") -> None:
        # CR 106.4: "When an effect instructs a player to add mana, that mana
        # goes into a player's mana pool."
        pool = game.controller_of(stack_object).mana_pool
        for color in colors:
            pool.add(color)

    return effect


#: Replicate (the sorcery half of Repudiate // Replicate): "Create a token
#: that's a copy of target creature you control." (CR 707.2, CR 111.13's
#: "created" token, not CR 111.13's exempt copy-of-a-spell). Deliberately not
#: `_parse_token_clause`'s job - that parser bails out on any "copy of"
#: phrase by name (see `test_repudiates_copy_clause_fails_closed`, which
#: checks the *combined* split-card printing's blank top-level text and stays
#: true either way) because it has no target-resolution step at all; this one
#: does, reusing `token_copy_of` the same way `_parse_city_blessing_token_
#: copy_clause` below reuses it for Ocelot Pride's anaphoric "it" instead of
#: a real target.
_CREATE_TOKEN_COPY_OF_TARGET_RE = re.compile(
    r"^create a token that'?s a copy of (?P<phrase>target creature you control)\.?$",
    re.IGNORECASE,
)


def _parse_create_token_copy_of_target_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_CREATE_TOKEN_COPY_OF_TARGET_RE`'s shape, or `None` if this is not it."""
    match = _CREATE_TOKEN_COPY_OF_TARGET_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase")):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState):
                token_copy_of(game, target, controller.username)

    return effect


#: Ocelot Pride: "Then if you have the city's blessing, for each token you
#: control that entered this turn, create a token that's a copy of it."
#: Templated (CR 702.131 - *ascend* and the city's blessing are both reminder
#: text the rules print on more than one card), read by shape rather than by
#: card name, so a future card with this exact sentence is covered for free.
#: `split_effect_clauses`'s "then" splitting does not strip the leading
#: "Then " off the second half of a two-sentence effect - see
#: `split_effect_clauses` - so the leading word has to be tolerated here.
_CITY_BLESSING_TOKEN_COPY_RE = re.compile(
    r"^(?:then\s+)?if you have the city's blessing,\s*"
    r"for each token you control that entered this turn,\s*"
    r"create a token that's a copy of it\.?$",
    re.IGNORECASE,
)


def _parse_city_blessing_token_copy_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """Ocelot Pride's second sentence, read as one instruction (CR 608.2c).

    Two things this is *not*:

    - **Not an intervening *if*** (CR 603.4, CR 608.2a). Ocelot Pride's
      intervening *if* is "if you gained life this turn", the clause
      immediately after the trigger condition itself, already pulled off by
      `abilities._parse_triggered` into `TriggeredAbility.intervening_if`
      before this text is ever seen. "If you have the city's blessing" sits
      mid-effect instead, so it is an ordinary conditional instruction,
      checked once while this half of the ability resolves in printed order -
      CR 608.2c's "the controller ... follows its instructions in the order
      written" - not rechecked as the ability leaves the stack.
    - **Not `_parse_token_clause`'s shape.** That parser refuses any clause
      naming a copy outright (CR 707.2); this is the one place in the file
      that reads a copy, through `token_copy_of` instead.

    "For each token you control that entered this turn" is read as the set of
    such tokens *at the moment this instruction starts to resolve* - the same
    once-counted convention `hangarback_dies` already uses for "for each
    +1/+1 counter on this creature" - so a copy this instruction itself
    creates is not folded back into its own count and copied again in the
    same resolution. It is a token that entered this turn in its own right,
    for the *next* time this ability resolves.

    Ability-only (`for_spell=False`): nothing in the pool prints this shape on
    a spell, and the shape depends on `AbilityOnStack.controller` and on
    `CardState.turn_entered`, neither of which a resolving spell has reason
    to consult the same way.
    """
    if for_spell:
        return None
    if not _CITY_BLESSING_TOKEN_COPY_RE.fullmatch(clause.strip()):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        controller = game.controller_of(ability).username
        player = game.player(controller)
        if not player.has_citys_blessing:
            return
        turn_number = getattr(game.turn, "turn_number", None)
        if turn_number is None:
            return
        entered_this_turn = [
            state
            for state in game.permanents_controlled_by(controller)
            if is_token(state) and state.turn_entered == turn_number
        ]
        for state in entered_this_turn:
            token_copy_of(game, state, controller)

    return effect


# --------------------------------------------------------------------------
# Wave W1: a non-owner choosing from a revealed hand (CR 701.20a, CR 701.9b),
# "target player discards N cards" (CR 701.9a), and Formidable Speaker's
# "you may discard a card. If you do, ..." (CR 118.12's discard cousin) -
# Thoughtseize, Go Blank, and Formidable Speaker. Duskwatch Recruiter's
# "look at the top three ..." activated ability sits in its own block further
# down, next to `Game.look_at_top_and_split`, the primitive it and it alone
# needs here.
#
# Verified this session with `knowledge_search(q="...", type="rules")`:
#
#   CR 701.20a - "To reveal a card, show that card to all players for a brief
#   time."
#   CR 701.9a - "To discard a card, move it from its owner's hand to that
#   player's graveyard."
#   CR 701.9b - "By default, effects that cause a player to discard a card
#   allow the affected player to choose which card to discard. Some effects,
#   however, require a random discard or allow another player to choose
#   which card is discarded" - Thoughtseize's own "You choose a nonland card
#   from it" is exactly that override, read by naming `Decision.player` as
#   the resolving spell's controller rather than the revealing player.
# --------------------------------------------------------------------------

#: "target player reveals their hand" (Thoughtseize) / "target opponent
#: reveals their hand" (Grief, Thought-Knot Seer) - the same CR 701.20a
#: reveal, aimed at whichever player word the card prints; the actual target
#: restriction (a plain player, or specifically an opponent) is still
#: enforced by `machines/targeting.py` through `_targets_understood` below,
#: not by this regex.
_REVEAL_HAND_RE = re.compile(r"^target (?:player|opponent) reveals their hand$", re.IGNORECASE)
#: "you choose a/an <quality> card from it" - Thoughtseize's, Grief's, and
#: Thought-Knot Seer's shared second sentence, the CR 701.9b/CR 701.13a
#: override handing the choice to the resolving spell's/ability's controller
#: instead of the revealed player. Thought-Knot Seer prints its consequence
#: in the same sentence ("... from it and exile that card"), but
#: `split_effect_clauses` already cuts across that bare "and" the same way it
#: does everywhere else, so this clause and its consequence clause
#: (`_DISCARD_THAT_CARD_RE`/`_EXILE_THAT_CARD_RE`) always arrive separately.
_CHOOSE_CARD_FROM_REVEALED_RE = re.compile(
    r"^you choose (?:a|an) (?P<quality>.+?) card from it$", re.IGNORECASE
)
#: "that player discards that card" (Thoughtseize, Grief) - the anaphoric
#: tail naming the same player `_REVEAL_HAND_RE` targeted and the same card
#: `_CHOOSE_CARD_FROM_REVEALED_RE` just chose.
_DISCARD_THAT_CARD_RE = re.compile(r"^that player discards that card$", re.IGNORECASE)
#: "exile that card" (Thought-Knot Seer, when not folded into the previous
#: sentence) - CR 701.13a's move, straight from the revealed hand.
_EXILE_THAT_CARD_RE = re.compile(r"^exile that card$", re.IGNORECASE)
#: "you lose N life" - Thoughtseize's own optional fourth sentence.
_YOU_LOSE_LIFE_RE = re.compile(r"^you lose (?P<life>\d+) life$", re.IGNORECASE)


def _nonland_or_typed_card_matcher(quality: str) -> Callable[[CardState], bool] | None:
    """A predicate for "a `<quality>` card", where `<quality>` is either a
    bare type `_quality_matcher` already reads, or that type's negation,
    spelled "non`<type>`" (Thoughtseize's own "nonland"). `_quality_matcher`
    has no notion of "non" - every caller before this one only ever named
    what to *include* - so this reads the negation itself and delegates
    everything else.
    """
    quality = quality.strip().lower()
    if quality.startswith("non"):
        try:
            excluded = Type(quality.removeprefix("non").strip())
        except ValueError:
            return None

        def not_matches(state: CardState) -> bool:
            return excluded not in state.types

        return not_matches
    return _quality_matcher(quality)


#: "Choose up to one target creature spell or planeswalker spell." (Subtlety).
#: CR 115.6: "up to one" is nought or one, so choosing none is a legal answer,
#: not a fizzle - `Game.resolve_targets` already returns an empty list for a
#: legally-targeted-nothing ability, which is exactly what this reads as "do
#: nothing" rather than as an error. The phrase after "choose up to one" is
#: read the same way any other targeted clause's phrase is - through
#: `machines/targeting.py`'s own `profile_for_text`, not a second grammar
#: here - so a future card naming a different pair of spell types is covered
#: for free.
_CHOOSE_UP_TO_ONE_TARGET_RE = re.compile(r"^choose (?P<phrase>up to one target .+)$", re.IGNORECASE)

#: "Its owner puts it on their choice of the top or bottom of their library."
#: - Subtlety's own consequence. "Its owner" (CR 108.3) is deliberately not
#: "its controller": a spell on the stack is controlled by whoever cast it
#: but *owned* by whoever started the game with it, and CR 401.2's library is
#: the owner's own, not the caster's.
_OWNER_PUTS_ON_TOP_OR_BOTTOM_RE = re.compile(
    r"^its owner puts it on their choice of the top or bottom of their library$",
    re.IGNORECASE,
)


def _spell_target_requirement(phrase: str) -> TargetRequirement | None:
    """`phrase` ("target creature spell or planeswalker spell"), read as a
    requirement that targets an object *on the stack* and nothing else -
    never a player, never an ability, never an unbounded count - or `None` if
    `machines/targeting.py` cannot confidently read it as exactly that.

    Deliberately not `_targets_understood`: that helper's `battlefield_only`
    flag only ever means "skip the zone check entirely" when turned off
    (`exile`/`return` reach any zone, on purpose), which would silently accept
    a targeted *permanent* here too. A spell target is always CR 115.5's
    stack, and nothing else, so this checks that zone directly instead of
    reusing a helper with no way to ask for it.
    """
    profile = profile_for_text(phrase)
    if not profile.understood or len(profile.requirements) != 1:
        return None
    requirement = profile.requirements[0]
    if requirement.zones != frozenset({Zone.STACK}):
        return None
    if requirement.allows_players or requirement.allows_abilities:
        return None
    if requirement.unbounded:
        return None
    return requirement


def _put_spell_in_library(game: "Game", spell: CardState, *, top: bool) -> None:
    """Move a spell off the stack straight into its owner's library (CR
    401.2), instead of letting it resolve.

    Deliberately not `Game.counter`: Subtlety's own ruling (and CR 701.6a's
    own text) is that this spell was never countered - it is simply removed
    from the stack and placed in a library, so `TriggerEvent.SPELL_IS_
    COUNTERED` must never fire for it and it must never pass through
    `Game.put_into_graveyard`. The bookkeeping `counter` otherwise shares
    (removing it from `game.stack`, dropping its now-stale `CastRecord`) is
    still needed here for the same reason `counter` needs it: a `CastRecord`
    surviving past this point would misread a later intervening *if* as
    "nothing was spent" instead of correctly finding no record at all
    (`machines/triggers._cast_record_for_clause`).
    """
    if spell not in game.stack:
        return
    game.stack.remove(spell)
    game.cast_records.pop(spell.id, None)
    if spell.owner is None:
        return
    owner = game.player(spell.owner)
    spell.move_to(Zone.LIBRARY)
    if top:
        owner.library.insert(0, spell)
    else:
        owner.library.append(spell)


def _parse_choose_up_to_one_target_spell_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Subtlety's whole paragraph: "choose up to one target creature spell or
    planeswalker spell. Its owner puts it on their choice of the top or
    bottom of their library."

    Ability-only (`for_spell=False`): CR 601.2c never runs for a resolving
    spell choosing its own targets that way, and nothing in the pool prints
    this shape on a spell. A merge, not two independent single-clause
    parsers, because "its owner" in the second sentence is CR 607.1 anaphora
    back to whichever spell the first sentence's target turned out to be -
    there is nothing to resolve without both clauses read together.
    """
    if for_spell or index + 1 >= len(clauses):
        return None
    choose_match = _CHOOSE_UP_TO_ONE_TARGET_RE.fullmatch(clauses[index].strip())
    if choose_match is None:
        return None
    requirement = _spell_target_requirement(choose_match.group("phrase"))
    if requirement is None or requirement.minimum != 0 or requirement.maximum != 1:
        return None
    if _OWNER_PUTS_ON_TOP_OR_BOTTOM_RE.fullmatch(clauses[index + 1].strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        spells = [
            target
            for target in game.resolve_targets(ability)
            if isinstance(target, CardState) and target.zone is Zone.STACK
        ]
        if not spells:
            return
        spell = spells[0]
        if spell.owner is None:
            return
        top = game.ask(
            Decision(
                kind=DecisionKind.PUT_ON_TOP_OR_BOTTOM,
                player=spell.owner,
                prompt=(f"put {spell.name} on the top or bottom of {spell.owner}'s library"),
                source=ability.source_name,
            )
        )
        assert isinstance(top, bool)
        _put_spell_in_library(game, spell, top=top)

    return 2, effect


def _merge_reveal_hand_choose_discard_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Thoughtseize's, Grief's, and Thought-Knot Seer's shared paragraph,
    read as one anaphoric run of clauses rather than several independent
    ones: "it" in the second sentence is the hand `_REVEAL_HAND_RE` just
    revealed, and "that card" in the third is whichever one
    `_CHOOSE_CARD_FROM_REVEALED_RE` just chose. Neither of those can be
    resolved by a clause parsed alone, which is why this is a multi-clause
    merge (see `_parse_mixed_clauses`'s own docstring) rather than several
    entries in `_parse_mixed_clause`'s single-clause chain.

    Grief prints "target opponent" where Thoughtseize prints "target player";
    `_REVEAL_HAND_RE` reads either, and the actual restriction is enforced
    through `_targets_understood` on the clause's own matched text (not a
    literal "target player") so the two are checked for what they actually
    say. The consequence clause is either `_DISCARD_THAT_CARD_RE`'s CR 701.9a
    discard (Thoughtseize, Grief) or `_EXILE_THAT_CARD_RE`'s CR 701.13a exile
    (Thought-Knot Seer) - the same anaphoric "that card", moved a different
    place.

    The trailing "you lose N life" is genuinely optional - Thoughtseize
    prints it, Grief and Thought-Knot Seer do not - and is read
    unconditionally regardless of whether a card was actually taken
    (CR 608.2c's printed order has no "if you do" gate on it the way
    `_parse_conditional_sacrifice_clause`'s consequence does).

    A hand with no nonland (or otherwise qualifying) card is CR 608.2d's
    "impossible option": nothing is asked and the reveal simply shows an
    all-land hand for nothing, exactly as the paper cards do.
    """
    if index + 2 >= len(clauses):
        return None
    reveal_clause = clauses[index].strip()
    if _REVEAL_HAND_RE.fullmatch(reveal_clause) is None:
        return None
    if not _targets_understood(reveal_clause.split(" reveals", 1)[0], allow_player_targets=True):
        return None
    choose_match = _CHOOSE_CARD_FROM_REVEALED_RE.fullmatch(clauses[index + 1].strip())
    if choose_match is None:
        return None
    matches = _nonland_or_typed_card_matcher(choose_match.group("quality"))
    if matches is None:
        return None
    consequence_clause = clauses[index + 2].strip()
    to_exile = _EXILE_THAT_CARD_RE.fullmatch(consequence_clause) is not None
    if not to_exile and _DISCARD_THAT_CARD_RE.fullmatch(consequence_clause) is None:
        return None
    consumed = 3
    life_loss = 0
    if index + 3 < len(clauses):
        life_match = _YOU_LOSE_LIFE_RE.fullmatch(clauses[index + 3].strip())
        if life_match is not None:
            life_loss = int(life_match.group("life"))
            consumed = 4

    quality_description = choose_match.group("quality").strip()

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        revealer = next(
            (target for target in game.resolve_targets(stack_object) if isinstance(target, Player)),
            None,
        )
        if revealer is not None:
            candidates = [state for state in revealer.hand if matches(state)]
            if candidates:
                chosen_ids = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_CARDS,
                        player=controller.username,
                        prompt=(
                            f"choose a {quality_description} card from "
                            f"{revealer.username}'s revealed hand"
                        ),
                        source=source,
                        amount=1,
                        cards=tuple(state.id for state in candidates),
                    )
                )
                assert isinstance(chosen_ids, tuple)
                by_id = {state.id: state for state in candidates}
                chosen = by_id[chosen_ids[0]]
                if to_exile:
                    game.exile_permanent(chosen)
                else:
                    game.discard_cards(revealer.username, [chosen], source=source)
        if life_loss:
            controller.lose_life(life_loss)

    return consumed, effect


#: "target player discards <count> cards" - Go Blank's own first clause, and
#: P2's general vehicle: a plain CR 701.9a discard with no chooser override,
#: so CR 701.9b's default (the discarding player themselves) is left alone.
_TARGET_PLAYER_DISCARDS_RE = re.compile(
    r"^target player discards "
    r"(?P<count>a|an|one|two|three|four|five|six|seven|eight|nine|ten|\d+) cards?$",
    re.IGNORECASE,
)


def _parse_target_player_discards_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Target player discards N cards." (CR 701.9a), CR 701.9b's default
    chooser untouched - unlike Thoughtseize's own discard
    (`_merge_reveal_hand_choose_discard_clauses`), where "you choose" overrides
    it.

    A hand with fewer than N cards is not a rules violation the way CR
    119.4's life payment floor is: the player simply discards their whole
    hand, one at a time, which is why `needed` is capped at the hand's own
    size before ever asking `CHOOSE_CARDS` for it.
    """
    match = _TARGET_PLAYER_DISCARDS_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if not _targets_understood("target player", allow_player_targets=True):
        return None
    count_text = match.group("count").lower()
    count = _NUMBER_WORDS.get(count_text)
    if count is None:
        count = int(count_text)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, Player):
                continue
            needed = min(count, len(target.hand))
            if needed <= 0:
                continue
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=target.username,
                    prompt=f"discard {needed} card(s)",
                    source=source,
                    amount=needed,
                    cards=tuple(state.id for state in target.hand),
                )
            )
            assert isinstance(chosen_ids, tuple)
            by_id = {state.id: state for state in target.hand}
            game.discard_cards(
                target.username, [by_id[card_id] for card_id in chosen_ids], source=source
            )

    return effect


#: "Target player draws N cards." (Ancestral Vision) - CR 121.1's plain draw,
#: aimed at a chosen player rather than the caster (`_DRAW_RE`'s "you" or
#: implicit-"you" shapes never reach a resolving *target*). The same
#: sentence shape as `_TARGET_PLAYER_DISCARDS_RE`, one CR 701.9a verb swapped
#: for CR 121.1's.
_TARGET_PLAYER_DRAWS_RE = re.compile(
    r"^target player draws "
    r"(?P<count>a|an|one|two|three|four|five|six|seven|eight|nine|ten|\d+) cards?$",
    re.IGNORECASE,
)


def _parse_target_player_draws_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_TARGET_PLAYER_DRAWS_RE`'s shape, or `None` if this is not it."""
    match = _TARGET_PLAYER_DRAWS_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if not _targets_understood("target player", allow_player_targets=True):
        return None
    count_text = match.group("count").lower()
    count = _NUMBER_WORDS.get(count_text)
    if count is None:
        count = int(count_text)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        for target in game.resolve_targets(stack_object):
            if isinstance(target, Player):
                game.draw_cards(target.username, count)

    return effect


#: "then exile that player's graveyard" - Go Blank's own second clause,
#: anaphoric to the same target its first clause (`_TARGET_PLAYER_DISCARDS_RE`)
#: already discarded into that graveyard. Reuses `exile_target_players_
#: graveyard` outright rather than a copy of it: that function already reads
#: the player off `game.resolve_targets(stack_object)`, which is exactly the
#: same target this clause means by "that player" - Go Blank prints only one
#: target for its whole text, so both clauses resolve it to the same `Player`.
_THEN_EXILE_THAT_PLAYERS_GRAVEYARD_RE = re.compile(
    r"^then exile that player'?s graveyard$", re.IGNORECASE
)

#: "you may discard a card" - Formidable Speaker's own first clause, CR
#: 118.12's optional cost half of "[Do something]. If [a player] does, ...".
_MAY_DISCARD_A_CARD_RE = re.compile(r"^you may discard a card$", re.IGNORECASE)
#: "if you do, <consequence>" - CR 118.12's own consequence clause, split off
#: from `_MAY_DISCARD_A_CARD_RE`'s clause by `_prepare_effect_clauses`'s
#: period splitting the same way `_MAY_SACRIFICE_IF_YOU_DO_RE`'s own two
#: halves would be if that shape were not read as one whole-text regex
#: instead - this one has to be a multi-clause merge, since "you may discard
#: a card. If you do, search ..." reaches `_parse_mixed_clause` as two
#: already-split clauses.
_IF_YOU_DO_RE = re.compile(r"^if you do,\s*(?P<consequence>.+)$", re.IGNORECASE | re.DOTALL)


def _merge_may_discard_if_you_do_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Formidable Speaker's ETB trigger: "you may discard a card. If you do,
    search your library for a creature card, reveal it, put it into your
    hand, then shuffle." (CR 118.12's discard-flavoured cousin of
    `_parse_conditional_sacrifice_clause`'s sacrifice.)

    Reuses `_parse_sacrifice_consequence` outright for the "if you do" half:
    that function's own two shapes (a magnitude-threaded pair of clauses, or
    a plain mandatory search) are not sacrifice-specific in what they read,
    only in the docstring's own worked examples - Formidable Speaker's
    consequence is exactly `_SEARCH_AND_PUT_RE`'s shape, which
    `_parse_sacrifice_consequence` already tries. The `power` argument every
    consequence function takes is `None` here, since a discard produces no
    magnitude the way a sacrifice's power does, and `_search_and_place_for`'s
    own effect never reads it.
    """
    if index + 1 >= len(clauses):
        return None
    if _MAY_DISCARD_A_CARD_RE.fullmatch(clauses[index].strip()) is None:
        return None
    if_match = _IF_YOU_DO_RE.fullmatch(clauses[index + 1].strip())
    if if_match is None:
        return None
    consequence = _parse_sacrifice_consequence(if_match.group("consequence"))
    if consequence is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        decision = Decision(
            kind=DecisionKind.MAY,
            player=player.username,
            prompt="discard a card",
            source=source,
            affirmative_is_legal=bool(player.hand),
        )
        if not game.ask(decision):
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt="choose a card to discard",
                source=source,
                amount=1,
                cards=tuple(state.id for state in player.hand),
            )
        )
        assert isinstance(chosen_ids, tuple)
        by_id = {state.id: state for state in player.hand}
        game.discard_cards(player.username, [by_id[chosen_ids[0]]], source=source)
        consequence(game, player, None, source)

    return 2, effect


# --------------------------------------------------------------------------
# Wave W1's third primitive: look at the top N cards and split them between
# two destinations, general past `Game.scry`/`Game.surveil`'s own fixed
# pair - `Game.look_at_top_and_split`, next to `scry`/`surveil` themselves in
# `models/game.py`. Duskwatch Recruiter's `{2}{G}` ability is the vehicle:
# "Look at the top three cards of your library. You may reveal a creature
# card from among them and put it into your hand. Put the rest on the bottom
# of your library in any order." - a creature-only, at-most-one cousin of
# scry's "any number, any card" split, with "to hand"/"to the bottom" in
# place of scry's "to the bottom"/"back on top".
# --------------------------------------------------------------------------

#: "look at the top <count> cards of your library" - Duskwatch Recruiter's
#: own first clause.
_LOOK_AT_TOP_N_CARDS_RE = re.compile(
    r"^look at the top (?P<count>\w+) cards? of your library$", re.IGNORECASE
)
#: "you may reveal a/an <quality> card from among them" - the second clause,
#: naming which of the looked-at cards may be taken.
_MAY_REVEAL_FROM_AMONG_THEM_RE = re.compile(
    r"^you may reveal (?:a|an) (?P<quality>.+?) card from among them$", re.IGNORECASE
)
#: "put it into your hand" - `_CLAUSE_SEPARATOR`'s own "and" split of the
#: second sentence's tail.
_PUT_IT_INTO_YOUR_HAND_RE = re.compile(r"^put it into your hand$", re.IGNORECASE)
#: "put the rest on the bottom of your library in any order" - Duskwatch
#: Recruiter's own third sentence. "In any order" (not "a random order") is
#: the same CR 608.2d free choice `scry`'s own "any order" already is, which
#: is why `Game.look_at_top_and_split`'s `CardSplit.top_order` is read
#: straight through rather than randomised here.
_PUT_REST_ON_BOTTOM_ANY_ORDER_RE = re.compile(
    r"^put the rest on the bottom of your library in any order$", re.IGNORECASE
)


def _merge_look_top_reveal_to_hand_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Duskwatch Recruiter's whole `{2}{G}` ability, read as one anaphoric run
    of four clauses (`_CLAUSE_SEPARATOR` cuts the second sentence's own
    "... among them and put it into your hand" in two at "and") rather than
    four independent ones - "them" is the top `count` cards the first clause
    looked at, "it" is whichever one the second clause chose, and "the rest"
    is whatever is left of that same set.

    `Game.look_at_top_and_split` asks the generic CR 608.2d split question
    with no notion of "only a creature card" or "at most one" built in - both
    are this card's own restriction, not the primitive's - so this function
    enforces them itself once the answer comes back: a `moved` half with more
    than one card, or one that fails the quality predicate, is CR 608.2d's
    "can't choose an option that's illegal", raised the same way `Game.ask`
    already raises for an illegal `CHOOSE_TARGETS`/`CHOOSE_CARDS` answer.
    """
    if index + 3 >= len(clauses):
        return None
    look_match = _LOOK_AT_TOP_N_CARDS_RE.fullmatch(clauses[index].strip())
    if look_match is None:
        return None
    count_text = look_match.group("count").lower()
    count = _NUMBER_WORDS.get(count_text)
    if count is None:
        try:
            count = int(count_text)
        except ValueError:
            return None
    reveal_match = _MAY_REVEAL_FROM_AMONG_THEM_RE.fullmatch(clauses[index + 1].strip())
    if reveal_match is None:
        return None
    matches = _quality_matcher(reveal_match.group("quality"))
    if _PUT_IT_INTO_YOUR_HAND_RE.fullmatch(clauses[index + 2].strip()) is None:
        return None
    if _PUT_REST_ON_BOTTOM_ANY_ORDER_RE.fullmatch(clauses[index + 3].strip()) is None:
        return None
    quality_description = reveal_match.group("quality").strip()

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        moved, rest = game.look_at_top_and_split(
            player,
            count,
            source=source,
            prompt=f"reveal a {quality_description} card from the top {count}",
        )
        if len(moved) > 1 or any(not matches(state) for state in moved):
            raise ValueError(
                f"{source}: may reveal at most one {quality_description} card this way (CR 608.2d)"
            )
        for state in moved:
            player.add(state, Zone.HAND)
        for state in rest:
            player.library.append(state)

    return 4, effect


#: "put one of them into your hand" - Waker of Waves' own second sentence,
#: read plain rather than through `_MAY_REVEAL_FROM_AMONG_THEM_RE`'s "you may
#: reveal a `<quality>` card": there is no quality restriction and no "you
#: may" - the split is mandatory, and which of the two cards goes where is the
#: controller's own unstated choice (CR 608.2d), the same free choice `scry`'s
#: "any order" already is.
#: "of them" is optional: Codecracker Hound prints the shorter "Put one into
#: your hand", Waker of Waves the fuller "Put one of them into your hand" -
#: the same CR 608.2d split either way.
_PUT_ONE_OF_THEM_INTO_YOUR_HAND_RE = re.compile(
    r"^put one(?: of them)? into your hand$", re.IGNORECASE
)
#: "the other into your graveyard" - Waker of Waves' own third clause, split
#: off the second sentence's "and" by `_CLAUSE_SEPARATOR` the same way
#: Duskwatch Recruiter's own third/fourth clauses are. English ellipsis drops
#: the repeated verb ("put"), so it is optional here, unlike
#: `_PUT_REST_ON_BOTTOM_ANY_ORDER_RE`'s fully spelled-out sentence.
_THE_OTHER_INTO_YOUR_GRAVEYARD_RE = re.compile(
    r"^(?:put )?the other into your graveyard$", re.IGNORECASE
)


def _merge_look_top_split_hand_graveyard_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Waker of Waves' whole `{1}{U}` ability: "Look at the top two cards of
    your library. Put one of them into your hand and the other into your
    graveyard." - the same anaphoric-run shape `_merge_look_top_reveal_to_
    hand_clauses` reads for Duskwatch Recruiter, with a different pair of
    destinations and no quality restriction or "you may": both halves of the
    split are mandatory, one card each.

    `Game.look_at_top_and_split` asks the identical CR 608.2d question either
    way; what differs is only what this function does with the two answered
    groups, and the shape it enforces on them - CR 608.2d: "The player can't
    choose an option that's illegal or impossible", so an answer that does not
    split the looked-at cards exactly one-and-the-rest is refused rather than
    silently applied.
    """
    if index + 2 >= len(clauses):
        return None
    look_match = _LOOK_AT_TOP_N_CARDS_RE.fullmatch(clauses[index].strip())
    if look_match is None:
        return None
    count_text = look_match.group("count").lower()
    count = _NUMBER_WORDS.get(count_text)
    if count is None:
        try:
            count = int(count_text)
        except ValueError:
            return None
    if _PUT_ONE_OF_THEM_INTO_YOUR_HAND_RE.fullmatch(clauses[index + 1].strip()) is None:
        return None
    if _THE_OTHER_INTO_YOUR_GRAVEYARD_RE.fullmatch(clauses[index + 2].strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        moved, rest = game.look_at_top_and_split(
            player,
            count,
            source=source,
            prompt="put one into your hand, the other into your graveyard",
        )
        if len(moved) != 1 or len(rest) != count - 1:
            raise ValueError(
                f"{source}: exactly one of the {count} must go to hand, the rest to the "
                "graveyard (CR 608.2d)"
            )
        for state in moved:
            player.add(state, Zone.HAND)
        for state in rest:
            player.add(state, Zone.GRAVEYARD)

    return 3, effect


#: Expressive Iteration's own second sentence, split by `_CLAUSE_SEPARATOR`'s
#: single "and" into two raw clauses rather than three (no "then"/"and"
#: separates the first two destinations, only a comma) - "Put one of them
#: into your hand, put one of them on the bottom of your library," is one
#: fragment, "exile one of them" the other.
_PUT_HAND_AND_BOTTOM_RE = re.compile(
    r"^put one of them into your hand, put one of them on the bottom of your library,?$",
    re.IGNORECASE,
)
_EXILE_ONE_OF_THEM_RE = re.compile(r"^exile one of them$", re.IGNORECASE)
#: "You may play the exiled card this turn." - CR 601.3's time-boxed
#: permission, the same primitive `_parse_exile_then_play_permission_pair`
#: already uses for Ugin's -11 and Ragavan, but printed on a *spell* here
#: rather than an ability - that pairing is ability-only (see its own
#: docstring), so Expressive Iteration gets a dedicated merge instead.
_YOU_MAY_PLAY_THE_EXILED_CARD_THIS_TURN_RE = re.compile(
    r"^you may play the exiled cards? this turn$", re.IGNORECASE
)


def _merge_look_top_hand_bottom_exile_play_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Expressive Iteration's whole text: "Look at the top three cards of
    your library. Put one of them into your hand, put one of them on the
    bottom of your library, and exile one of them. You may play the exiled
    card this turn." - a three-way CR 608.2d split (`_merge_look_top_split_
    hand_graveyard_clauses`'s own two-way sibling), the third destination
    carrying a CR 601.3 play permission over whatever landed there.

    Spell-only: the pool has no ability printing this exact shape, and CR
    608.2b's "the resolving object's controller" is unambiguous for a spell
    (`game.controller_of(spell)`) in a way `_parse_exile_then_play_
    permission_pair`'s own docstring explains an `AbilityOnStack` is not.
    """
    if not for_spell or index + 3 >= len(clauses):
        return None
    look_match = _LOOK_AT_TOP_N_CARDS_RE.fullmatch(clauses[index].strip())
    if look_match is None:
        return None
    count_text = look_match.group("count").lower()
    count = _NUMBER_WORDS.get(count_text)
    if count is None:
        try:
            count = int(count_text)
        except ValueError:
            return None
    if _PUT_HAND_AND_BOTTOM_RE.fullmatch(clauses[index + 1].strip()) is None:
        return None
    if _EXILE_ONE_OF_THEM_RE.fullmatch(clauses[index + 2].strip()) is None:
        return None
    if _YOU_MAY_PLAY_THE_EXILED_CARD_THIS_TURN_RE.fullmatch(clauses[index + 3].strip()) is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        player = game.controller_of(spell)
        looked = list(player.library[:count])
        if not looked:
            return

        def choose_one(prompt: str, pool: list[CardState]) -> CardState:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player.username,
                    prompt=prompt,
                    source=spell.name,
                    amount=1,
                    cards=tuple(state.id for state in pool),
                )
            )
            by_id = {state.id: state for state in pool}
            return by_id[chosen_ids[0]]

        to_hand = choose_one("put one of the looked-at cards into your hand", looked)
        remaining = [state for state in looked if state is not to_hand]
        to_bottom = choose_one(
            "put one of the remaining looked-at cards on the bottom of your library", remaining
        )
        to_exile = [state for state in remaining if state is not to_bottom]

        player.add(to_hand, Zone.HAND)
        player.move(to_bottom, Zone.LIBRARY)
        for state in to_exile:
            exiled = game.exile_permanent(state)
            game.grant_play_permission(
                exiled,
                player.username,
                action=PlayAction.PLAY,
                pays_mana_cost=True,
                source_name=spell.name,
                rule="CR 601.3",
            )

    return 4, effect


#: "Exile the top two cards of your library. Until the end of your next turn,
#: you may play those cards." - Wrenn's Resolve and Reckless Impulse print the
#: identical sentence word for word (verified against both pool printings),
#: so one parser, generalized on the count, covers both rather than a second
#: name-keyed row. `PlayAction.PLAY` rather than `.CAST`: CR 601.1a's "playing
#: a card" covers a land found among the exiled cards, which "you may play"
#: (not "you may cast") is broad enough to reach.
_EXILE_TOP_N_CARDS_RE = re.compile(
    r"^exile the top (?P<count>\w+) cards? of your library\.?$", re.IGNORECASE
)
_UNTIL_END_OF_YOUR_NEXT_TURN_PLAY_RE = re.compile(
    r"^until the end of your next turn, you may play (?:those cards|that card)\.?$",
    re.IGNORECASE,
)


def _merge_exile_top_then_play_until_next_turn_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Wrenn's Resolve's/Reckless Impulse's whole text, as one CR 608.2c
    instruction - the second sentence's "those cards" is CR 607.1 anaphora
    back to whatever the first sentence just exiled, so splitting them would
    either grant a permission over nothing or run the exile and drop the
    permission, stranding cards in exile their controller could never
    legally use.

    Spell-only (both printings are sorceries). The permission is
    `expires_end_of_next_turn=True` (see `PlayPermission`'s own docstring) -
    a strictly longer window than the plain `until_end_of_turn` grant
    `_parse_exile_then_play_permission_pair`'s ability-side "until end of
    turn" shape uses. Nothing in either printing says what happens to a card
    left unplayed once the permission lapses (unlike cascade's own "put the
    exiled cards on the bottom" - `PlayPermission.bottom_if_unused`'s own
    docstring), so it is left exactly where CR 514.2 leaves any other expired
    grant: sitting in exile, forever.
    """
    if not for_spell or index + 1 >= len(clauses):
        return None
    exile_match = _EXILE_TOP_N_CARDS_RE.fullmatch(clauses[index].strip())
    if exile_match is None:
        return None
    if not _UNTIL_END_OF_YOUR_NEXT_TURN_PLAY_RE.fullmatch(clauses[index + 1].strip()):
        return None
    count_text = exile_match.group("count").lower()
    count = _NUMBER_WORDS.get(count_text)
    if count is None:
        try:
            count = int(count_text)
        except ValueError:
            return None

    def effect(game: "Game", spell: CardState) -> None:
        player = game.controller_of(spell)
        top = list(player.library[:count])
        for card in top:
            exiled = game.exile_permanent(card)
            game.grant_play_permission(
                exiled,
                player.username,
                action=PlayAction.PLAY,
                pays_mana_cost=True,
                source_name=spell.name,
                rule="CR 601.3",
                until_end_of_turn=False,
                expires_end_of_next_turn=True,
            )

    return 2, effect


#: "Return this card from your graveyard to your hand." - World Breaker's
#: whole graveyard-only ability (CR 113.6m, `machines/abilities.py`'s
#: `zone`/`zone_rule` reads that half of it already). A self-reference, not a
#: target: CR 115.1's "target" always names a chosen object, and this
#: sentence names the very permanent whose ability is resolving instead, the
#: same self-reference `_parse_destroy_each_clause`'s "Destroy each ..." and
#: `machines/keywords`'s `discard_cost`/`sacrifice_cost` self-fill already
#: read off "this card"/"this permanent". Zones beyond graveyard-to-hand are
#: read too, generalized off the words rather than pinned to this one card -
#: CR 400.7's zone-change vocabulary is the same whichever two zones a future
#: card names this way.
_RETURN_THIS_CARD_RE = re.compile(
    r"^return this (?:card|permanent) from (?:your|its owner's) "
    r"(?P<from_zone>graveyard|hand|exile|library|battlefield) "
    r"to (?:your|its owner's) (?P<to_zone>hand|graveyard|battlefield|exile|library)\.?$",
    re.IGNORECASE,
)

#: The zone names `_RETURN_THIS_CARD_RE` reads map straight onto `Zone`.
_ZONE_BY_NAME: dict[str, Zone] = {
    "hand": Zone.HAND,
    "graveyard": Zone.GRAVEYARD,
    "battlefield": Zone.BATTLEFIELD,
    "exile": Zone.EXILE,
    "library": Zone.LIBRARY,
}


def _parse_self_return_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Return this card from your `<zone>` to your `<zone>`." - a plain
    zone change of the ability's own source, read off the clause's own words
    (CR 400.7a: putting a card into hand from anywhere but the stack or
    battlefield is a new object with no memory of what it was).

    CR 113.7a: the ability resolves independently of its source, so a source
    that can no longer be found (already moved again, or gone) or one that
    has already left the zone the clause names does nothing rather than
    raising - the same "the target left" shape CR 608.2b already gives a
    targeted effect, applied here to a plain self-reference instead.
    """
    match = _RETURN_THIS_CARD_RE.fullmatch(clause.strip())
    if match is None:
        return None
    from_zone = _ZONE_BY_NAME[match.group("from_zone").lower()]
    to_zone = _ZONE_BY_NAME[match.group("to_zone").lower()]

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object if isinstance(stack_object, CardState) else stack_object.source(game)
        if source is None or source.zone is not from_zone:
            return
        owner = game.find_owner(source) or game.player(
            source.controller_or_owner or game.active_player.username
        )
        owner.move(source, to_zone)

    return effect


#: "Exile it" (Ancient Adamantoise's own dies trigger) - CR 603.10a's
#: look-back "it", naming the ability's own source rather than a target.
#: Distinct from `_EXILE_THAT_CARD_RE`, whose "that card" is a card an
#: earlier clause in the *same* ability chose from a revealed hand, not the
#: source itself.
_EXILE_IT_RE = re.compile(r"^exile it$", re.IGNORECASE)


def _parse_exile_dead_self_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Exile it" - moves the ability's own source to exile from wherever
    CR 700.4's move just put it (almost always the graveyard, since this only
    ever prints on a dies trigger in the pool). CR 113.7a: the ability
    resolves independently of its source, so a source that can no longer be
    found does nothing rather than raising, the same fail-soft
    `_parse_self_return_clause` already gives its own self-reference.

    Ability-only (`for_spell=False`): nothing in the pool prints this on a
    spell, and `AbilityOnStack.source` is what finds the departed object -
    a resolving spell has no equivalent lookup for "itself" once its
    resolution has already moved it elsewhere.
    """
    if for_spell:
        return None
    if not _EXILE_IT_RE.fullmatch(clause.strip()):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        source = ability.source(game)
        if source is None or source.zone is Zone.BATTLEFIELD:
            return
        game.exile_permanent(source)

    return effect


#: "return it to its owner's hand" (Rancor's own dies trigger) - CR 603.10a's
#: look-back "it", naming the ability's own source, the same self-reference
#: `_EXILE_IT_RE` reads for a different destination.
_RETURN_IT_TO_OWNERS_HAND_RE = re.compile(r"^return it to its owner'?s hand$", re.IGNORECASE)


def _parse_return_dead_self_to_hand_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "Return it to its owner's hand." - Rancor's own dies trigger, moving
    the ability's own source (CR 603.10a's look-back "it") from wherever it
    now sits (almost always the graveyard, per CR 700.4 - an Aura's own dies
    trigger fires the same way a creature's does, CR 700.4 naming "a
    permanent", not only a creature) to its owner's hand (CR 108.3, CR 401).
    CR 113.7a: a source that can no longer be found does nothing rather than
    raising, the same fail-soft shape `_parse_exile_dead_self_clause` and
    `_parse_self_return_clause` already give their own self-references.

    Ability-only (`for_spell=False`): nothing in the pool prints this on a
    spell, and `AbilityOnStack.source` is what finds the departed object.
    """
    if for_spell:
        return None
    if not _RETURN_IT_TO_OWNERS_HAND_RE.fullmatch(clause.strip()):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        source = ability.source(game)
        if source is None or source.zone is Zone.BATTLEFIELD:
            return
        game.return_to_hand(source)

    return effect


# --------------------------------------------------------------------------
# Wave W1 (revisited): "choose a card name"/"the same name as that card",
# then search a graveyard, a hand, and a library for cards with that name and
# exile them (CR 701.23a, run three times, once per zone) - The Stone Brain
# and Surgical Extraction. Matched whole, ahead of `_parse_mixed_clauses`'
# ordinary per-clause splitting: both cards' own "graveyard, hand, and
# library" and "with that name and exile them" each carry a bare "and"
# `_CLAUSE_SEPARATOR` would otherwise cut into unreadable fragments, so this
# reads the whole `text` argument `_parse_mixed_clauses` already has in
# scope, before `_prepare_effect_clauses` ever runs on it - the same
# "read it whole, then dispatch" shape `_parse_conditional_sacrifice_clause`
# uses from its own callers, reached from inside this wave's own dispatch
# surface instead of `_ability_effect_or_notice`/`_spell_effect_or_notice`.
#
# CR 701.23a: "To search for a card in a zone, look at all cards in that zone
# (even if it's a hidden zone) and find a card that matches the given
# description." Verified this session, along with the rest of the P7 zone
# widening's own citations (CR 701.23b/d, CR 701.24b/e) already recorded on
# `Game.search_library` in `models/game.py`, which both cards' own search
# reuses via its `zone` parameter - the wiring that parameter existed for.
# --------------------------------------------------------------------------


def _search_and_exile_matching_name(
    game: "Game",
    zones_owner: Player,
    name: str,
    *,
    chooser: Player,
    cap: int | None,
    source: str,
) -> tuple[list[CardState], int]:
    """Search `zones_owner`'s graveyard, hand, and library, in that printed
    order, for cards named `name`, exile every one found (capped at `cap`
    total, or every match when `cap` is `None` - Surgical Extraction's own
    "any number"), and shuffle only the library (CR 701.24b), once,
    regardless of whether the library search itself found anything
    (CR 701.24e).

    `chooser` is who decides *which* matches to take when there are more
    than `cap` of them - CR 701.23g's "you" search, not `zones_owner`, who is
    only the zones' owner and not necessarily the one doing the searching
    (The Stone Brain searches an *opponent's* zones; Surgical Extraction may
    search the caster's own, if the targeted card sat in their own
    graveyard). The choice is a real `DecisionKind.CHOOSE_CARDS` question
    over every zone's matches at once, offered before anything is removed
    from any zone - taking the cap's worth greedily out of whichever zone
    happened to search first would silently prefer that zone's matches over
    an otherwise identical one two zones later, which is not what "up to
    four" printed with no zone preference means.

    When the total is at or under `cap` (or `cap` is `None`), nothing is
    asked at all: CR 701.23d's "must find that many (or as many as
    possible)" leaves no real choice once every match is going to be taken
    anyway, the same no-question-when-there-is-no-real-choice shape
    `Player.discard_to_maximum_hand_size` already holds for a hand already
    within its maximum.

    Returns `(exiled, exiled_from_hand)` - the second is The Stone Brain's own
    "for each card exiled from their hand this way" count; Surgical
    Extraction's caller has no use for it and ignores it.
    """
    zones_in_order = (Zone.GRAVEYARD, Zone.HAND, Zone.LIBRARY)
    candidates = {
        zone: [state for state in zones_owner.cards_in(zone) if state.name == name]
        for zone in zones_in_order
    }
    total = sum(len(states) for states in candidates.values())
    if cap is not None and total > cap:
        offered = [state for zone in zones_in_order for state in candidates[zone]]
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=chooser.username,
                prompt=f"choose {cap} card(s) named {name!r} to exile",
                source=source,
                amount=cap,
                cards=tuple(state.id for state in offered),
            )
        )
        assert isinstance(chosen_ids, tuple)
        chosen = set(chosen_ids)
        candidates = {
            zone: [state for state in states if state.id in chosen]
            for zone, states in candidates.items()
        }

    exiled: list[CardState] = []
    exiled_from_hand = 0
    for zone in zones_in_order:
        wanted_ids = {state.id for state in candidates[zone]}
        found = game.search_library(
            zones_owner,
            lambda state, wanted_ids=wanted_ids: state.id in wanted_ids,
            count=max(len(wanted_ids), 0) or 1,
            optional=False,
            zone=zone,
            source=source,
        )
        for state in found:
            game.exile_permanent(state)
            exiled.append(state)
            if zone is Zone.HAND:
                exiled_from_hand += 1
    return exiled, exiled_from_hand


#: The Stone Brain: "Choose a card name. Search target opponent's graveyard,
#: hand, and library for up to four cards with that name and exile them.
#: That player shuffles, then draws a card for each card exiled from their
#: hand this way." Read off the activated ability's own `effect` field
#: (`{2}, {T}, Exile The Stone Brain:` and the trailing "Activate only as a
#: sorcery." are both already stripped by `machines/abilities.py` before this
#: text is ever seen).
_STONE_BRAIN_RE = re.compile(
    r"^choose a card name\.\s*"
    r"search target opponent's graveyard, hand, and library for up to "
    r"(?P<cap>a|an|one|two|three|four|five|six|seven|eight|nine|ten|\d+) cards? "
    r"with that name and exile them\.\s*"
    r"that player shuffles, then draws a card for each card exiled from "
    r"their hand this way\.?$",
    re.IGNORECASE,
)

#: Surgical Extraction: "Choose target card in a graveyard other than a basic
#: land card. Search its owner's graveyard, hand, and library for any number
#: of cards with the same name as that card and exile them. Then that player
#: shuffles." The leading "({B/P} can be paid with either {B} or 2 life.)"
#: reminder line is already gone by the time this runs - `_strip_non_effect_
#: preamble`'s own `_REMINDER_LINE_RE` strips a leading reminder line for
#: every spell, Dismember and Mutagenic Growth among them.
_SURGICAL_EXTRACTION_RE = re.compile(
    r"^choose target card in a graveyard other than a basic land card\.\s*"
    r"search its owner's graveyard, hand, and library for any number of cards "
    r"with the same name as that card and exile them\.\s*"
    r"then that player shuffles\.?$",
    re.IGNORECASE,
)


def _parse_stone_brain_clause(text: str, *, for_spell: bool) -> TargetedClause | None:
    """`_STONE_BRAIN_RE`'s shape. Ability-only (`for_spell=False`): nothing in
    the pool prints this shape on a spell, and the effect reads `ability.
    source_name` for its own search prompts, which a resolving spell has no
    equivalent of the same way.
    """
    if for_spell:
        return None
    match = _STONE_BRAIN_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    if not _targets_understood("target opponent", allow_player_targets=True):
        return None
    cap = _NUMBER_WORDS.get(match.group("cap").lower())
    if cap is None:
        cap = int(match.group("cap"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        controller = game.controller_of(ability)
        source = ability.source_name
        target_player = next(
            (target for target in game.resolve_targets(ability) if isinstance(target, Player)),
            None,
        )
        if target_player is None:
            return
        name = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_A_QUALITY,
                player=controller.username,
                prompt="choose a card name",
                source=source,
            )
        )
        assert isinstance(name, str)
        _exiled, exiled_from_hand = _search_and_exile_matching_name(
            game, target_player, name, chooser=controller, cap=cap, source=source
        )
        if exiled_from_hand:
            game.draw_cards(target_player.username, exiled_from_hand)

    return effect


def _parse_surgical_extraction_clause(text: str, *, for_spell: bool) -> TargetedClause | None:
    """`_SURGICAL_EXTRACTION_RE`'s shape. Spell-only (`for_spell=True`):
    Surgical Extraction is the only card in the pool printing it, and it is a
    spell (an instant); the name comes off the target itself, not off a
    `CHOOSE_A_QUALITY` question, so nothing here needs an ability's own
    `source_name`/`controller` machinery either way.
    """
    if not for_spell:
        return None
    match = _SURGICAL_EXTRACTION_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    if not _targets_understood(
        "target card in a graveyard other than a basic land card",
        count_agnostic=False,
        battlefield_only=False,
    ):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        spell = stack_object
        assert isinstance(spell, CardState)
        controller = game.controller_of(spell)
        target_card = next(
            (target for target in game.resolve_targets(spell) if isinstance(target, CardState)),
            None,
        )
        if target_card is None or target_card.owner is None:
            return
        owner = game.player(target_card.owner)
        _search_and_exile_matching_name(
            game, owner, target_card.name, chooser=controller, cap=None, source=spell.name
        )

    return effect


def _parse_choose_name_search_and_exile_whole_text(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """Try `_parse_stone_brain_clause`, then `_parse_surgical_extraction_
    clause`, against the *whole*, unsplit effect text - see this section's
    own module comment for why a per-clause dispatch cannot read either
    card's own "graveyard, hand, and library"/"with that name and exile
    them" wording.
    """
    stone_brain = _parse_stone_brain_clause(text, for_spell=for_spell)
    if stone_brain is not None:
        return stone_brain
    return _parse_surgical_extraction_clause(text, for_spell=for_spell)


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
    city_blessing_copy = _parse_city_blessing_token_copy_clause(clause, for_spell=for_spell)
    if city_blessing_copy is not None:
        return city_blessing_copy
    create_token_copy_of_target = _parse_create_token_copy_of_target_clause(
        clause, for_spell=for_spell
    )
    if create_token_copy_of_target is not None:
        return create_token_copy_of_target
    counter_on_additional_cost_card = _parse_counter_on_additional_cost_card_clause(clause)
    if counter_on_additional_cost_card is not None:
        return counter_on_additional_cost_card
    search = _parse_search_clause(clause, for_spell=for_spell)
    if search is not None:
        return search
    search_mv_lte_count = _parse_search_mv_lte_count_clause(clause, for_spell=for_spell)
    if search_mv_lte_count is not None:
        return search_mv_lte_count
    imprint = _parse_imprint_clause(clause, for_spell=for_spell)
    if imprint is not None:
        return imprint
    return_imprinted = _parse_return_imprinted_clause(clause, for_spell=for_spell)
    if return_imprinted is not None:
        return return_imprinted
    self_return = _parse_self_return_clause(clause, for_spell=for_spell)
    if self_return is not None:
        return self_return
    exile_dead_self = _parse_exile_dead_self_clause(clause, for_spell=for_spell)
    if exile_dead_self is not None:
        return exile_dead_self
    return_dead_self = _parse_return_dead_self_to_hand_clause(clause, for_spell=for_spell)
    if return_dead_self is not None:
        return return_dead_self
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
    counter_that_spell = _parse_counter_that_spell_clause(clause, for_spell=for_spell)
    if counter_that_spell is not None:
        return counter_that_spell
    defending_player_exiles = _parse_defending_player_exiles_top_n_clause(
        clause, for_spell=for_spell
    )
    if defending_player_exiles is not None:
        return defending_player_exiles
    if _LOOK_AT_TOP_CARD_RE.fullmatch(clause.strip()):
        return _look_at_top_card
    if _LOOK_AT_TARGET_HAND_RE.fullmatch(clause.strip()):
        return _look_at_target_hand
    # -- Wave W1's own single-clause additions, contiguous block ----------
    target_player_discards = _parse_target_player_discards_clause(clause, for_spell=for_spell)
    if target_player_discards is not None:
        return target_player_discards
    target_player_draws = _parse_target_player_draws_clause(clause, for_spell=for_spell)
    if target_player_draws is not None:
        return target_player_draws
    if _THEN_EXILE_THAT_PLAYERS_GRAVEYARD_RE.fullmatch(clause.strip()):
        return exile_target_players_graveyard
    # -- end Wave W1 single-clause additions -------------------------------
    # -- Wave W11's own single-clause addition (CR 106.4, CR 605.1a) ------
    add_mana = _parse_add_mana_clause(clause, for_spell=for_spell)
    if add_mana is not None:
        return add_mana
    # -- end Wave W11 single-clause addition -------------------------------
    # -- Wave W6's own single-clause additions (Brotherhood's End's modes) -
    destroy_each = _parse_destroy_each_clause(clause)
    if destroy_each is not None:
        return destroy_each
    damage_each_group = _parse_damage_each_group_clause(clause)
    if damage_each_group is not None:
        return damage_each_group
    # -- end Wave W6 single-clause additions --------------------------------
    # -- Wave W5's own single-clause addition (CR 611.1) -------------------
    casting_rule = parse_casting_rule_clause(clause, for_spell=for_spell)
    if casting_rule is not None:
        return casting_rule
    # -- end Wave W5 single-clause addition ---------------------------------
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

    Tried first, against the whole unsplit `text`: `_parse_choose_name_
    search_and_exile_whole_text` (The Stone Brain, Surgical Extraction) -
    both cards' own "graveyard, hand, and library"/"with that name and exile
    them" wording carries a bare "and" `_CLAUSE_SEPARATOR` would otherwise
    cut into fragments no per-clause parser below could ever read back
    together, so this has to see the paragraph whole before anything splits
    it.
    """
    whole_text_effect = _parse_choose_name_search_and_exile_whole_text(text, for_spell=for_spell)
    if whole_text_effect is not None:
        return [whole_text_effect]
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
        # -- Wave W1's own multi-clause merges, contiguous block -----------
        merged = _merge_reveal_hand_choose_discard_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_may_discard_if_you_do_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_look_top_reveal_to_hand_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_look_top_split_hand_graveyard_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_look_top_hand_bottom_exile_play_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_exile_top_then_play_until_next_turn_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        # -- end Wave W1 multi-clause merges --------------------------------
        merged = _parse_counter_exile_then_cast_free_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _parse_devotion_drain_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _parse_scry_or_untap_if_not_starting_player_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        # -- Wave W6's own multi-clause merges, contiguous block ------------
        merged = _parse_delayed_reanimate_haste_exile_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_damage_each_group_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        # -- end Wave W6 multi-clause merges ----------------------------------
        # -- Wave W7b's own multi-clause merge (CR 108.3, CR 115.6, CR 401.2) --
        merged = _parse_choose_up_to_one_target_spell_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        # -- end Wave W7b multi-clause merge ---------------------------------
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
            paired = _parse_counter_then_create_tokens_by_mana_value_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            paired = _parse_counter_then_exile_instead_of_graveyard_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            paired = _parse_exile_then_play_permission_pair(
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


#: "You may have target opponent draw a card. If you do, copy that spell.
#: You may choose new targets for the copy." - Alania, Divergent Storm's own
#: cast trigger, read as one CR 608.2c instruction chain: CR 707.1's copy is
#: conditional (CR 118.12's "if you do") on the draw actually happening, and
#: "that spell" is CR 607.1 anaphora back to the very spell this ability's
#: own `TriggerEvent.CAST_SPELL` watched (`ability.event.subject_id`), not a
#: target this ability announces itself.
_TARGET_OPPONENT_DRAW_THEN_COPY_THAT_SPELL_RE = re.compile(
    r"^you may have target opponent draw a card\. if you do, copy that spell\. "
    r"you may choose new targets for the copy\.?$",
    re.IGNORECASE,
)


def _parse_target_opponent_draw_then_copy_that_spell_clause(text: str) -> AbilityEffect | None:
    """`_TARGET_OPPONENT_DRAW_THEN_COPY_THAT_SPELL_RE`'s shape - Alania,
    Divergent Storm's whole cast trigger (CR 121.1's draw; CR 707.10's copy,
    via `Game.copy_spell`; CR 707.10c's retargeting, via `Game.
    offer_new_targets_for_copy`).
    """
    if _TARGET_OPPONENT_DRAW_THEN_COPY_THAT_SPELL_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        opponent = next(
            (target for target in game.resolve_targets(ability) if isinstance(target, Player)),
            None,
        )
        if opponent is None:
            return
        if not game.may(
            game.player(ability.controller),
            "have target opponent draw a card",
            source=ability.source_name,
        ):
            return
        game.draw_cards(opponent.username, 1)

        event = ability.event
        if event is None or event.subject_id is None:
            return
        spell = game.find_by_id(event.subject_id)
        if spell is None or spell not in game.stack:
            return
        copy = game.copy_spell(spell, controller=ability.controller)
        game.offer_new_targets_for_copy(copy, ability.controller, source_name=ability.source_name)

    return effect


#: Frontline Heroism's own cast trigger effect: "create a `<token>`, then
#: copy that spell. The copy targets that token." The token half is
#: `_TOKEN_CLAUSE_RE`'s ordinary shape (any generic token descriptor - this
#: is not hardcoded to "1/1 red Soldier ... with haste"), and the copy half
#: is CR 707.10's `Game.copy_spell` the same way Alania, Divergent Storm's
#: own clause above already reaches it - the difference is the retarget: "the
#: copy targets that token" is not CR 707.10c's optional "you may choose new
#: targets", it is a forced, specific new target, so `copy.targets` is set
#: directly rather than through `offer_new_targets_for_copy`.
_CREATE_TOKEN_THEN_COPY_SPELL_RETARGETED_RE = re.compile(
    r"^(?P<token_clause>.+?tokens?(?:\s+with\s+.+?)?), then copy that spell\. "
    r"the copy targets? that token\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_create_token_then_copy_spell_retargeted_clause(text: str) -> AbilityEffect | None:
    """`_CREATE_TOKEN_THEN_COPY_SPELL_RETARGETED_RE`'s shape, or `None` if
    this is not it, or if the token half is not `_TOKEN_CLAUSE_RE`'s own
    readable shape.
    """
    match = _CREATE_TOKEN_THEN_COPY_SPELL_RETARGETED_RE.fullmatch(text.strip())
    if match is None:
        return None
    token_text = match.group("token_clause").strip()
    if not token_text.lower().startswith("create"):
        token_text = "create " + token_text
    token_match = _TOKEN_CLAUSE_RE.fullmatch(token_text)
    if token_match is None:
        return None
    count = _count(token_match.group("n"))
    words = token_match.group("desc").strip().split()
    tapped = bool(words) and words[0].lower() == "tapped"
    if tapped:
        words = words[1:]
    if not words:
        return None
    definition = _parse_generic_token_descriptor(words, token_match.group("tail"))
    if definition is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = ability.controller
        tokens = create_tokens(game, definition, controller, count, tapped=tapped)
        event = ability.event
        if event is None or event.subject_id is None or not tokens:
            return
        spell = game.find_by_id(event.subject_id)
        if spell is None or spell not in game.stack:
            return
        copy = game.copy_spell(spell, controller=controller)
        # CR 707.2's copiable "targets" is overwritten here rather than left
        # to `offer_new_targets_for_copy`: "the copy targets that token" is a
        # forced instruction, not CR 707.10c's optional permission, and it
        # names a specific new target (the very token just created) rather
        # than letting the controller choose freely among legal ones.
        copy.targets = [TargetRef.coerce(tokens[0])]

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
    #
    # Ocelot Pride's end-step trigger - "if you gained life this turn, create
    # a 1/1 white Cat creature token. Then if you have the city's blessing,
    # for each token you control that entered this turn, create a token
    # that's a copy of it." - is not entered here either. Every ability in
    # this project must be read as a whole paragraph (see the design ruling in
    # `docs/engine-coverage.md`): a card-name row that ran only the first
    # sentence, unconditionally, while the second - the whole point of
    # *ascend* and the city's blessing - silently never ran, is exactly the
    # half-execution CR 608.2c forbids, and this project's history has a real
    # game where that bug went unnoticed for two whole turns. Both sentences
    # are readable now: the first is `_parse_token_clause`'s ordinary shape,
    # and the second is `_parse_city_blessing_token_copy_clause`'s (CR 702.131,
    # CR 707.2), so `trigger_effect_for`'s fallback reads the whole ability
    # with no row at all, and a future ascend card with the same "for each
    # token you control that entered this turn, create a token that's a copy
    # of it" shape is covered for free. See `tests/scenarios/test_ascend.py`.
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
    # you may cast that card" - is read too, as the second half of
    # `_parse_exile_then_play_permission_pair`: one CR 608.2c instruction with
    # the exiling clause it points back at, granting a `machines/casting.
    # PlayPermission` over exactly the card just exiled. So Ragavan's whole
    # paragraph now runs and leaves no notice. Nashi's and Questing Beast's
    # still leave one each (CR 608.2c has no notion of running half an effect -
    # see `_ability_effect_or_notice`):
    # Nashi's "you may put any number of ... into your hand" and Questing
    # Beast's "target planeswalker that player controls" are each still a
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
        raw = _ability_effect_or_notice(effect_text)
        if raw is not None:
            # The literal printed name is what some parsers are *reading
            # for* - `_parse_may_exile_self_then_return_clause`'s own CR
            # 201.5 guard on Ajani, Nacatl Pariah's "you may exile Ajani,
            # then return him ..." checks that the captured name is a
            # substring of the actual source's name, and would refuse a
            # normalized "this permanent" outright. Tried unnormalized
            # first, always, so a shape already reading the literal name
            # keeps doing so; only a miss falls through to the normalized
            # attempt below.
            return raw
        # Ruby, Daring Tracker's own "Ruby gets +2/+2 until end of turn." -
        # CR 201.5 self-reference by literal printed name (Grist and The
        # Filigree Sylex's shape, `_self_normalized_effect_text`'s own
        # docstring), on a *triggered* ability rather than the activated one
        # that function was first written for. `activated_effect_for`
        # already normalizes before parsing; a triggered ability's text
        # reached `_ability_effect_or_notice` unnormalized until now, so a
        # pump clause spelled with the card's own name instead of CR 700.7's
        # "this creature" fell through every clause parser and resolved
        # silently.
        return _ability_effect_or_notice(_self_normalized_effect_text(card_name, effect_text))
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


#: Moved to `machines/abilities.self_normalized_effect_text` so
#: `machines/layers.py` (which `machines/effects.py` itself imports from, so
#: cannot be imported *by* it without a cycle) can share the same rewrite for
#: the continuous-effect sentences it reads straight off `CardState.
#: oracle_text` - Ruby, Daring Tracker's "Ruby gets +2/+2 until end of turn."
#: needs the identical CR 201.5 self-reference handling there, not only on the
#: `effect_text` this module's own parsers see. Aliased under the old private
#: name so every existing call site below is unchanged.
_self_normalized_effect_text = self_normalized_effect_text


def activated_effect_for(
    card_name: str, index: int, effect_text: str | None = None, *, x_value: int | None = None
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

    `x_value` is CR 107.3a's X as `Game.activate_ability` recorded it on the
    `AbilityOnStack`, mirroring `effect_for`'s own handling for a spell:
    `None` for an ability whose printed cost carries no `{X}` at all, which
    leaves a bare "X" written into the effect's own rules text (CR 107.3f, not
    this one) untouched. Fiend Artisan's "Search your library for a creature
    card with mana value X or less" is unreadable by `_SEARCH_AND_PUT_RE`
    until X is substituted for a real number, so - exactly as `effect_for`
    does for a spell - the unsubstituted text is tried first and the
    substituted text only once that comes back empty.
    """
    front = card_name.split("//")[0].strip()
    explicit = ACTIVATED_EFFECTS.get((card_name, index)) or ACTIVATED_EFFECTS.get((front, index))
    if explicit is not None:
        return explicit
    if effect_text is None:
        return None
    effect_text = _self_normalized_effect_text(card_name, effect_text)
    effect = _ability_effect_or_notice(effect_text)
    if effect is not None or x_value is None:
        return effect
    return _ability_effect_or_notice(substitute_x(effect_text, x_value))


# --------------------------------------------------------------------------
# Bringing a card in from outside the game (CR 400.11b, CR 108.3b)
# --------------------------------------------------------------------------

#: Karn, the Great Creator's `−2`, read whole: "You may reveal an artifact card
#: you own from outside the game or choose a face-up artifact card you own in
#: exile. Put that card into your hand."
#:
#: One paragraph is one ability, so the two sentences are matched together and
#: never half-run: the "put that card into your hand" is the whole point of the
#: choice above it, and an engine that could read one sentence and not the other
#: would have nothing sensible to do with either.
#:
#: The card type is a group, not a hard-coded "artifact", because the shape is
#: general - the rules that make it work are CR 400.11c's narrow exception for
#: "spells and abilities that allow those cards to be brought into the game",
#: CR 108.3b's ownership gate, and CR 406.3's face-up requirement - and none of
#: those is about artifacts.
_OUTSIDE_THE_GAME_FETCH_RE = re.compile(
    r"^you may reveal an? (?P<quality>[a-z]+) card you own from outside the game "
    r"or choose a face-up (?P<exile_quality>[a-z]+) card you own in exile\.?\s*"
    r"put that card into your hand\.?$",
    re.IGNORECASE,
)

#: A sentence that reaches outside the game in some other shape. Matched only to
#: fail closed with a notice, per the paragraph-atomic rule: an ability that
#: mentions outside the game and cannot be read whole records that it went
#: unread rather than resolving as silence.
_LOOKS_LIKE_OUTSIDE_THE_GAME_RE = re.compile(r"\bfrom outside the game\b", re.IGNORECASE)


def _parse_outside_the_game_fetch(effect_text: str) -> AbilityEffect | None:
    """Karn's `−2` shape, or a notice for a near miss, or None.

    Every rule this performs was looked up in the session that wrote it:

    - **CR 400.11a** - "Cards in a player's sideboard are outside the game."
    - **CR 400.11c** - cards outside the game "can't be affected by spells or
      abilities, except ... spells and abilities that allow those cards to be
      brought into the game", which is what this ability is.
    - **CR 108.3b** - "Some spells and abilities allow a player to take cards
      **they own** from outside the game and bring them into the game."
    - **CR 400.11b** - a card brought in "remain[s] in the game until the game
      ends".
    - **CR 701.20a** - "To reveal a card, show that card to all players for a
      brief time", and CR 701.20b: it does not move the card. The reveal is the
      price of taking a card out of a group nobody may look at; the exile half
      needs none, because CR 406.3 already makes a face-up exiled card one that
      "may be examined by any player at any time".
    - **CR 406.3** - "Cards 'exiled face down' can't be examined by any player
      except when instructions allow it", so a face-down exiled card is not a
      "face-up artifact card" and cannot be chosen. CR 406.3a: it "has no
      characteristics" to be an artifact with in the first place.
    - **CR 608.2d** - the "you may" and the choice are made as the ability
      resolves, by its controller, and an option that is illegal or impossible
      cannot be chosen.
    """
    match = _OUTSIDE_THE_GAME_FETCH_RE.match(" ".join(effect_text.split()))
    if match is None:
        if _LOOKS_LIKE_OUTSIDE_THE_GAME_RE.search(effect_text):

            def outside_the_game_notice_only(game: "Game", ability: AbilityOnStack) -> None:
                game.unmodeled_trigger_effect_notices.append(
                    UnmodeledTriggerEffectNotice(
                        source_id=ability.source_id,
                        source_name=ability.source_name,
                        text=effect_text,
                    )
                )

            return outside_the_game_notice_only
        return None

    quality = _card_type_from_quality(match.group("quality"))
    exile_quality = _card_type_from_quality(match.group("exile_quality"))
    if quality is None or exile_quality is None:
        return None

    def fetch(game: "Game", ability: AbilityOnStack) -> None:
        _bring_in_from_outside_the_game_or_exile(game, ability, quality, exile_quality)

    return fetch


def _card_type_from_quality(word: str) -> Type | None:
    """ "artifact" -> `Type.ARTIFACT`; anything that is not a card type -> None."""
    try:
        return Type(word.strip().lower())
    except ValueError:
        return None


def _bring_in_from_outside_the_game_or_exile(
    game: "Game",
    ability: AbilityOnStack,
    quality: Type,
    exile_quality: Type,
) -> None:
    """Perform the ability `_parse_outside_the_game_fetch` read (CR 608.2d).

    The candidates are computed twice over, in the two places the sentence
    names, and both are filtered by CR 108.3's **owner** - not the controller.
    Exile is a shared zone, so an opponent's card sitting face up in it is
    visible, choosable-looking, and not this player's to take.

    A `DecisionKind.CHOOSE_CARDS` question puts the choice to the ability's
    controller. That kind is deliberately reused rather than grown into a new
    one - its own docstring in `machines/decisions.py` says so: "any 'choose N
    of these cards' question (a search turning up more hits than needed,
    choosing among revealed cards) is the same question with a different prompt
    and a different source zone". The candidate ids therefore travel in the
    same `Decision.cards` field a scry's do, and are subject to the same
    per-player hidden-information filtering on the way out; the one card the
    player ends up revealing is recorded publicly on `Game.reveals`, and
    nothing else about the sideboard ever becomes public.

    With nothing legal to choose, the ability resolves having done nothing:
    CR 608.2d's "The player can't choose an option that's illegal or
    impossible", and there is no "if you can't, ..." clause to fall through to.
    """
    controller = game.player(ability.controller)

    def is_wanted(state: CardState, card_type: Type) -> bool:
        return card_type in state.types

    outside = controller.owned_outside_the_game(lambda state: is_wanted(state, quality))
    in_exile = game.face_up_cards_in_exile(
        owner=controller.username, matches=lambda state: is_wanted(state, exile_quality)
    )
    candidates = outside + in_exile
    if not candidates:
        return

    # CR 608.2d's plain "you may": the whole instruction is optional.
    if not game.may(
        controller,
        f"reveal a {quality.value} card you own from outside the game, or choose a "
        f"face-up one you own in exile",
        source=ability.source_name,
    ):
        return

    chosen_ids = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=controller.username,
            prompt=f"choose a {quality.value} card you own to put into your hand",
            source=ability.source_name,
            amount=1,
            cards=tuple(state.id for state in candidates),
        )
    )
    assert isinstance(chosen_ids, tuple)
    by_id = {state.id: state for state in candidates}
    for card_id in chosen_ids:
        chosen = by_id[card_id]
        if chosen.zone.is_outside_the_game:
            # CR 701.20a: the reveal is what makes taking it from a group
            # nobody may look at public information, and CR 701.20b leaves the
            # card where it is - so it is revealed first, then brought in.
            game.reveal(chosen, source=ability.source_name)
            controller.bring_into_the_game(chosen, Zone.HAND)
        else:
            # Already face up in exile (CR 406.3), so nothing to reveal.
            game.return_to_hand(chosen)
