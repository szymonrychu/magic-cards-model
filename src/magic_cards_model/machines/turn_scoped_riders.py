"""Riders that last the turn, printed after a resolving spell's or ability's
own mass pump or -X/-X (CR 611.2): the sentences `machines/effects.
_compose_layer_effect_with_remainder` (and its ability and mode twins) hand
over as the remainder beside the layer sentence.

- A turn-long replacement (CR 614.1a, CR 611.2a): "If a creature [an
  opponent controls] would die this turn, exile it instead." (Malicious
  Malfunction, Flaying Tendrils, Malicious Eclipse, Cry of the Carnarium),
  stored as a `Game.created_replacements` record - `machines/replacement.
  created_replacement_spec` reads the shape (`DieToExileReplacement`).
- A turn-long delayed triggered ability (CR 603.7, CR 603.7b): "Whenever a
  creature dies this turn, you gain 1 life." (Death Frenzy), Gnawing
  Crescendo's nontoken Rat, Noxious Assault's "Whenever a creature blocks
  this turn, its controller gets a poison counter." - the `machines/effects`
  created-trigger template (`CreatedTriggeredAbility`).
- Gated on kicker (CR 702.33d): "If this spell was kicked, `<rider>`"
  (Warhost's Frenzy).
- Cry of the Carnarium's "Exile all creature cards in all graveyards that
  were put there from the battlefield this turn."
- Turn-long combat requirements (CR 508.1d, CR 509.1c): "Each creature your
  opponents control blocks this turn if able." (Predatory Rampage) - CR
  611.2c: it modifies no characteristics, so it binds every creature that
  group holds at any time this turn - and "Those creatures attack this turn
  if able." (Suicidal Charge), whose "those creatures" is the set the layer
  sentence beside it locked on resolution (CR 611.2c again).

Every requirement is carried as the ability line `machines/combat.py`
already counts ("This creature attacks/blocks each combat if able."),
granted until end of turn: CR 508.1d/509.1c read a turn-long requirement at
each declare step of that turn, which is what a line held until end of turn
is. No shape here is new to the persisted model except
`DieToExileReplacement` (`machines/replacement.py`).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any
from uuid import UUID

from ..models.card import Type
from ..models.card_state import CardState, Counter
from ..models.zone import Zone
from ..numbers import COUNT, parse_count
from .layers import (
    ContinuousEffect,
    CreaturesControlledBy,
    CreaturesControlledByOpponentsOf,
    Duration,
    EveryCreature,
    Layer,
    OnlyThisIncarnation,
    Selector,
    grant_ability,
)

if TYPE_CHECKING:
    from ..models.game import Game

#: What a rider does at resolution - the `machines/effects.TargetedClause`
#: shape, `(game, spell or ability on the stack)`.
Rider = Callable[["Game", Any], None]

#: The objects the layer sentence beside the rider locked on resolution
#: (CR 611.2c) - `(card id, zone-change stamp)` per object, so a creature
#: that has since become a new object (CR 400.7) is not "those creatures".
#: Set only for the length of one rider's run by `run_layer_then_rider`.
_LAYER_ANTECEDENT: ContextVar[tuple[tuple[UUID, UUID], ...] | None] = ContextVar(
    "turn_scoped_layer_antecedent", default=None
)

_BLOCK_LINE = "This creature blocks each combat if able."
_ATTACK_LINE = "This creature attacks each combat if able."


def _controller(game: Game, stack_object: Any) -> str:
    return game.controller_of(stack_object).username


def _source_name(stack_object: Any) -> str:
    return stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name


def _source_id(stack_object: Any) -> UUID | None:
    return stack_object.id if isinstance(stack_object, CardState) else stack_object.source_id


def _source_card(game: Game, stack_object: Any) -> CardState | None:
    if isinstance(stack_object, CardState):
        return stack_object
    if stack_object.source_id is None:
        return None
    found = game.find_by_id(stack_object.source_id)
    return found if isinstance(found, CardState) else None


# -- the layer sentence's locked set ----------------------------------------


@contextmanager
def _antecedent(objects: tuple[tuple[UUID, UUID], ...]) -> Iterator[None]:
    token = _LAYER_ANTECEDENT.set(objects)
    try:
        yield
    finally:
        _LAYER_ANTECEDENT.reset(token)


def run_with_antecedent(
    game: Game, stack_object: Any, rider: Rider, affected: Iterable[CardState]
) -> None:
    """Run `rider` with `affected` - the objects the layer sentence beside it
    just changed - as its "those creatures" (CR 611.2c's locked set)."""
    locked = tuple((card.id, card.zone_change_stamp) for card in affected)
    with _antecedent(locked):
        rider(game, stack_object)


def run_layer_then_rider(game: Game, stack_object: Any, layer: Rider, rider: Rider) -> None:
    """Run the layer sentence, then the rider, with the objects the layer
    sentence's own new continuous effects lock (CR 611.2c) available to a
    "those creatures" rider (`_those_creatures_requirement`)."""
    from .effects import continuous_effects

    store = continuous_effects(game)
    before = {effect.id for effect in store.effects}
    layer(game, stack_object)
    locked: list[tuple[UUID, UUID]] = []
    for effect in store.effects:
        if effect.id in before or not isinstance(effect.selector, OnlyThisIncarnation):
            continue
        pair = (effect.selector.card_id, effect.selector.stamp)
        if pair not in locked:
            locked.append(pair)
    with _antecedent(tuple(locked)):
        rider(game, stack_object)


# -- "If this spell was kicked, <rider>" -------------------------------------

_KICKED_RE = re.compile(r"^if this spell was kicked, (?P<rest>\S.*)$", re.IGNORECASE | re.DOTALL)


def _kicked_rider(sentence: str, *, for_spell: bool) -> Rider | None:
    """CR 702.33d: the rider happens only when the spell was kicked, read off
    `Game.cast_record(spell).kicked` the way every other kicker clause is."""
    match = _KICKED_RE.fullmatch(sentence)
    if match is None or not for_spell:
        return None
    rest = match.group("rest")
    inner = _rider_sentence(rest[0].upper() + rest[1:], for_spell=for_spell)
    if inner is None:
        return None

    def kicked(game: Game, spell: Any) -> None:
        if isinstance(spell, CardState) and game.cast_record(spell).kicked > 0:
            inner(game, spell)

    return kicked


# -- the turn-long replacement ------------------------------------------------


def _created_replacement_rider(sentence: str) -> Rider | None:
    """A "this turn" replacement `created_replacement_spec` reads that needs
    no target - the die-to-exile shape above all."""
    from .effects import _created_replacement_record
    from .replacement import DieToExileReplacement, created_replacement_spec

    if not isinstance(created_replacement_spec(sentence), DieToExileReplacement):
        return None

    def replacement(game: Game, stack_object: Any) -> None:
        record = _created_replacement_record(
            sentence,
            controller=_controller(game, stack_object),
            source_id=_source_id(stack_object),
            source_name=_source_name(stack_object),
            target_player=None,
        )
        if record is not None:
            game.created_replacements.append(record)

    return replacement


# -- the turn-long delayed trigger --------------------------------------------


def _created_trigger_rider(sentence: str) -> Rider | None:
    """ "Whenever `<condition>` this turn, `<effect>`." read by the created-
    trigger template, the whole sentence being the trigger (no trailing
    instruction of the spell's own)."""
    from .effects import _create_turn_scoped_trigger, _split_created_trigger_paragraph

    split = _split_created_trigger_paragraph(sentence)
    if split is None:
        return None
    line, ability, rest = split
    if rest or ability.event is None:
        return None
    event = ability.event

    def trigger(game: Game, stack_object: Any) -> None:
        _create_turn_scoped_trigger(
            game,
            line,
            event,
            controller=_controller(game, stack_object),
            source=_source_card(game, stack_object),
            source_id=_source_id(stack_object),
            source_name=_source_name(stack_object),
        )

    return trigger


# -- Cry of the Carnarium's graveyard exile ----------------------------------

_EXILE_CARDS_THAT_DIED_THIS_TURN_RE = re.compile(
    r"^exile all (?P<quality>creature|artifact|enchantment|planeswalker|permanent) cards in "
    r"(?P<whose>your|your opponents['’]|all) graveyards? "
    r"that were put there from the battlefield this turn\.?$",
    re.IGNORECASE,
)

_QUALITY_TYPES: dict[str, frozenset[Type]] = {
    "creature": frozenset({Type.CREATURE}),
    "artifact": frozenset({Type.ARTIFACT}),
    "enchantment": frozenset({Type.ENCHANTMENT}),
    "planeswalker": frozenset({Type.PLANESWALKER}),
    "permanent": frozenset(
        {
            Type.ARTIFACT,
            Type.BATTLE,
            Type.CREATURE,
            Type.ENCHANTMENT,
            Type.LAND,
            Type.PLANESWALKER,
        }
    ),
}


def _exile_cards_that_died_this_turn_rider(sentence: str) -> Rider | None:
    """The history is `Game.cards_put_into_graveyard_from_battlefield_this_
    turn` (still in that graveyard, latest arrival off the battlefield, CR
    400.7). One instruction, one simultaneous exile (`Game.exile_cards`)."""
    match = _EXILE_CARDS_THAT_DIED_THIS_TURN_RE.fullmatch(sentence)
    if match is None:
        return None
    wanted = _QUALITY_TYPES[match.group("quality").lower()]
    whose = match.group("whose").lower()

    def exile(game: Game, stack_object: Any) -> None:
        controller = _controller(game, stack_object)
        owners = [
            player.username
            for player in game.players_in_game
            if whose == "all" or (whose == "your") == (player.username == controller)
        ]
        cards = [
            card
            for owner in owners
            for card in game.cards_put_into_graveyard_from_battlefield_this_turn(owner)
            if wanted & set(card.types)
        ]
        if cards:
            game.exile_cards(cards)

    return exile


# -- turn-long combat requirements ------------------------------------------

_GROUP_REQUIREMENT_RE = re.compile(
    r"^(?:each creature|all creatures|creatures)"
    r"(?: (?P<whose>your opponents control|an opponent controls|you control))? "
    r"(?P<verb>attacks?|blocks?) this turn if able\.?$",
    re.IGNORECASE,
)
_THOSE_CREATURES_REQUIREMENT_RE = re.compile(
    r"^(?:those creatures|they) (?P<verb>attack|block) this turn if able\.?$", re.IGNORECASE
)


def _requirement_line(verb: str) -> str:
    return _BLOCK_LINE if verb.lower().startswith("block") else _ATTACK_LINE


def _grant_until_end_of_turn(game: Game, selector: Selector, line: str, description: str) -> None:
    from .effects import continuous_effects

    store = continuous_effects(game)
    store.add(
        ContinuousEffect(
            description=description,
            layer=Layer.ABILITY,
            timestamp=store.tick(),
            duration=Duration.UNTIL_END_OF_TURN,
            selector=selector,
            modification=grant_ability(line),
        )
    )


def _group_requirement_rider(sentence: str) -> Rider | None:
    """ "Each creature your opponents control blocks this turn if able." - CR
    611.2c: a rules-modifying effect, so the group is read live (a creature
    entering, or changing control, later this turn is bound too - Predatory
    Rampage's ruling), never locked on resolution."""
    match = _GROUP_REQUIREMENT_RE.fullmatch(sentence)
    if match is None:
        return None
    whose = (match.group("whose") or "").lower()
    line = _requirement_line(match.group("verb"))

    def requirement(game: Game, stack_object: Any) -> None:
        controller = _controller(game, stack_object)
        selector: Selector
        if whose == "you control":
            selector = CreaturesControlledBy(username=controller)
        elif whose:
            selector = CreaturesControlledByOpponentsOf(username=controller)
        else:
            selector = EveryCreature()
        _grant_until_end_of_turn(
            game, selector, line, f"{_source_name(stack_object)}: {sentence.rstrip('.')}"
        )

    return requirement


def _those_creatures_requirement(sentence: str) -> Rider | None:
    """ "Those creatures attack this turn if able." - the creatures the layer
    sentence beside it affected (CR 611.2c's locked set, Suicidal Charge's
    ruling: a creature that comes under an opponent's control later is not
    one of them)."""
    match = _THOSE_CREATURES_REQUIREMENT_RE.fullmatch(sentence)
    if match is None:
        return None
    line = _requirement_line(match.group("verb"))

    def requirement(game: Game, stack_object: Any) -> None:
        for card_id, stamp in _LAYER_ANTECEDENT.get() or ():
            found = game.find_by_id(card_id)
            if not isinstance(found, CardState) or found.zone is not Zone.BATTLEFIELD:
                continue
            if found.zone_change_stamp != stamp:
                continue
            _grant_until_end_of_turn(
                game,
                OnlyThisIncarnation(card_id=card_id, stamp=stamp),
                line,
                f"{_source_name(stack_object)}: {found.name} {line[len('This creature ') :]}",
            )

    return requirement


# -- the readers, in order ----------------------------------------------------


def _rider_sentence(sentence: str, *, for_spell: bool) -> Rider | None:
    text = " ".join(sentence.strip().split())
    for reader in (
        _created_replacement_rider,
        _created_trigger_rider,
        _exile_cards_that_died_this_turn_rider,
        _group_requirement_rider,
        _those_creatures_requirement,
    ):
        rider = reader(text)
        if rider is not None:
            return rider
    return _kicked_rider(text, for_spell=for_spell)


def turn_scoped_rider(text: str, *, for_spell: bool) -> Rider | None:
    """Every sentence of `text` read as a rider above, or `None` when one is
    not - in which case the caller's own remainder readers carry on exactly
    as before. Run in the order written (CR 608.2c)."""
    from .effects import _plain_resolution_sentences

    sentences = _plain_resolution_sentences(text)
    if not sentences:
        return None
    riders: list[Rider] = []
    for sentence in sentences:
        rider = _rider_sentence(sentence, for_spell=for_spell)
        if rider is None:
            return None
        riders.append(rider)

    def riders_in_order(game: Game, stack_object: Any) -> None:
        for rider in riders:
            rider(game, stack_object)

    return riders_in_order


# -- "its controller gets a poison counter" ----------------------------------

#: The triggering object's controller, read off the event (CR 603.10a
#: looks back for a leaves-the-battlefield event; a block is not one, so the
#: controller is the blocker's as it still is, the event's as a fallback).
_EVENT_SUBJECT_CONTROLLER_POISON_RE = re.compile(
    rf"^(?:its|that creature['’]s|that permanent['’]s) controller gets "
    rf"(?P<n>{COUNT}) poison counters?\.?$",
    re.IGNORECASE,
)


def parse_event_subject_controller_poison_clause(clause: str, *, for_spell: bool) -> Rider | None:
    """Noxious Assault's created "Whenever a creature blocks, its controller
    gets a poison counter." (CR 122.1f). Ability-only: "its" is the
    triggering event's own object."""
    if for_spell:
        return None
    match = _EVENT_SUBJECT_CONTROLLER_POISON_RE.fullmatch(" ".join(clause.strip().split()))
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None or amount <= 0:
        return None

    def poison(game: Game, ability: Any) -> None:
        event = getattr(ability, "event", None)
        if event is None:
            return
        username = event.subject_controller
        if event.subject_id is not None:
            found = game.find_by_id(event.subject_id)
            if isinstance(found, CardState) and found.zone is Zone.BATTLEFIELD:
                username = found.controller
        if username is None or not game.is_in_game(username):
            return
        game.add_player_counters(game.player(username), Counter.POISON, amount)

    return poison
