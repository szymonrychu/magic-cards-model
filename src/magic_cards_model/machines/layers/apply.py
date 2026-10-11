from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, cast
from uuid import UUID

from pydantic import ConfigDict, Field, PrivateAttr

from ...models.card import Color, Layout
from ...models.card_state import (
    CardState,
)
from ...models.zone import Zone
from ...snapshot import EngineModel
from ..designations import ENDURING_STORY

if TYPE_CHECKING:
    from ...models.game import Game
from .model import Characteristics, ContinuousEffect, LayerNotice

# --------------------------------------------------------------------------
# The engine
# --------------------------------------------------------------------------


class Journal(EngineModel):
    """What the engine did, in order, so a test can assert on the ordering.

    The characteristics alone cannot tell you whether dependency or timestamp
    decided an outcome, and that is the part of CR 613 most likely to be wrong.
    """

    #: Effect descriptions in the order they were applied.
    applied: list[str] = Field(default_factory=list)
    #: Effects that did not apply because layer 6 had removed the ability
    #: generating them before they ever started (CR 613.6 read the other way).
    skipped: list[str] = Field(default_factory=list)
    #: Each dependency loop found, as the descriptions of the effects in it
    #: (CR 613.8b). A non-empty list means timestamp order broke a tie that
    #: dependency could not.
    cycles: list[list[str]] = Field(default_factory=list)


class NotOnBoard(KeyError):
    """`ComputedBoard.of` was asked about a card the board was not computed
    with - for a board served from a snapshot, a permanent put onto the
    battlefield in place after the board was cached. Still a `KeyError`, so
    every caller that already handles one is unchanged."""


class ComputedBoard(EngineModel):
    """Every permanent's characteristics, plus how the engine got there."""

    characteristics: dict[UUID, Characteristics]
    journal: Journal = Field(default_factory=Journal)

    def of(self, card: CardState | UUID) -> Characteristics:
        """The computed characteristics of one permanent."""
        card_id = card if isinstance(card, UUID) else card.id
        try:
            return self.characteristics[card_id]
        except KeyError:
            raise NotOnBoard(f"{card_id} is not on this board") from None

    def __getitem__(self, card: CardState | UUID) -> Characteristics:
        return self.of(card)


def compute_board(
    permanents: Iterable[CardState],
    effects: Iterable[ContinuousEffect] = (),
    counters: Mapping[UUID, Mapping[str, int]] | None = None,
    *,
    base_power_toughness: bool = False,
) -> ComputedBoard:
    """Apply every continuous effect to every permanent, in layer order (CR 613).

    Pure: the `CardState`s are read and never written, and `effects` is taken
    as given - CR 611.2b's "for as long as" filtering happens upstream, in
    `ContinuousEffects.active`, which is the one place that actually has a
    `Game` to check a condition against. This function never sees one, by
    design: it is what makes `Game.model_dump(mode="json")` able to decode a
    game back into something that computes the same board without this
    function ever touching a live object. Ask again after the board changes
    and you get a fresh answer, which is what CR 613.5 requires.

    Counters come off the permanents themselves (`CardState.counters`, CR 122.1).
    `+1/+1` and `-1/-1` counters become 7c effects (CR 613.4c); other counters
    are carried on the result without changing anything.

    `counters` overrides what a permanent carries, one permanent at a time: a
    permanent named there is computed with exactly those counters and one that
    is not keeps its own. That is for asking hypotheticals, not for running the
    board - a real board needs no argument at all.

    `base_power_toughness` asks CR 208.4b's question instead: "Some effects
    check a creature's base power and/or toughness. These effects see that
    creature's characteristics after applying any characteristic-defining
    abilities and abilities that set power and/or toughness, ignoring any
    effects and counters that modify power and/or toughness without setting
    them." Sublayers 7c (counters included, CR 613.4c) and 7d are skipped;
    everything else applies as usual.
    """
    counters = counters or {}
    board: dict[UUID, Characteristics] = {}
    attachments: dict[UUID, UUID] = {}
    for state in permanents:
        board[state.id] = printed_characteristics(state, counters.get(state.id))
        if state.attached_to is not None:
            attachments[state.id] = state.attached_to

    all_effects = (
        list(effects) + _counter_effects(board) + _hone_counter_effects(board, attachments)
    )
    journal = Journal()
    started: set[object] = set()

    for layer in Layer:
        if layer is Layer.TYPE:
            # Asked of the board as layers 1-3 left it: a copy or text effect
            # decides whether an object has changeling by now (CR 604.3a).
            all_effects += _changeling_effects(board)
        for sublayer in _sublayers_of(layer):
            if (
                base_power_toughness
                and layer is Layer.POWER_TOUGHNESS
                and sublayer in (Sublayer.MODIFY, Sublayer.SWITCH)
            ):
                continue
            group = [e for e in all_effects if e.layer is layer and e.sublayer is sublayer]
            if not group:
                continue
            # CR 613.3: in layers 2-6, characteristic-defining abilities apply
            # before everything else. Layer 7 does the same thing with 7a, and
            # layer 1's own sublayers (CR 613.2a, CR 613.2b) are likewise the
            # whole of its ordering - CR 613.3 does not reach either of them.
            if layer in _SUBLAYERED:
                phases = [group]
            else:
                phases = [
                    [e for e in group if e.characteristic_defining],
                    [e for e in group if not e.characteristic_defining],
                ]
            for phase in phases:
                if phase:
                    board = _apply_group(phase, board, started, journal)

    return ComputedBoard(characteristics=board, journal=journal)


def copiable_characteristics(
    state: CardState, effects: Iterable[ContinuousEffect] = ()
) -> Characteristics:
    """An object's copiable values (CR 707.2): what is printed on it, "as
    modified by other copy effects" - layer 1 (CR 613.2) and nothing after it.

    `effects` is every continuous effect that may apply; only layer 1 ones are
    applied, so a type-changing effect, an anthem or a counter never reaches
    the answer (CR 707.2: "Other effects (including type-changing and
    text-changing effects), status, counters, and stickers are not copied").
    An object no copy effect touches answers with its printed values, exactly
    as `printed_characteristics` would, less its counters.
    """
    board: dict[UUID, Characteristics] = {state.id: printed_characteristics(state, {})}
    copy_effects = [effect for effect in effects if effect.layer is Layer.COPY]
    started: set[object] = set()
    journal = Journal()
    for sublayer in _sublayers_of(Layer.COPY):
        group = [effect for effect in copy_effects if effect.sublayer is sublayer]
        if group:
            board = _apply_group(group, board, started, journal)
    return board[state.id]


def _changeling_effects(board: Board) -> list[ContinuousEffect]:
    """Changeling as the layer 4 characteristic-defining ability it is.

    CR 702.73a: "Changeling is a characteristic-defining ability.
    'Changeling' means 'This object is every creature type.'" CR 613.1d puts
    it in layer 4 and CR 613.3 applies it ahead of every other layer 4 effect,
    so a later "becomes a white Rabbit" (CR 205.1a) replaces the creature types
    it gave. `board` is the board as layers 1-3 left it, so an object that a
    copy effect gave changeling has it and one a copy effect took it from does
    not (CR 604.3a item 2); a board with no changeling gets no effect at all.
    """
    if not any(WithChangeling()(chars, board) for chars in board.values()):
        return []
    return [
        ContinuousEffect(
            description="Changeling: every creature type (CR 702.73a)",
            layer=Layer.TYPE,
            characteristic_defining=True,
            selector=WithChangeling(),
            modification=AddEveryCreatureType(),
        )
    ]


def _sublayers_of(layer: Layer) -> tuple[Sublayer | CopySublayer | None, ...]:
    """The sublayers `compute_board` walks for one layer, in rules order.

    Layer 1 (CR 613.2) and layer 7 (CR 613.4) each have their own ordered set;
    every other layer is one undivided pass, spelled `(None,)` so the caller
    has a single loop.
    """
    return _SUBLAYERS_BY_LAYER.get(layer, (None,))


#: A counter kind spelled as its own printed bonus - "+1/+1", "-1/-1", or
#: Clockwork Steed's own asymmetric "+1/+0" (CR 122.1a: "A +X/+Y counter on a
#: creature or on a creature card in a zone other than the battlefield, where
#: X and Y are numbers, adds X to that object's power and Y to that object's
#: toughness. Similarly, -X/-Y counters subtract from power and toughness.").
#: Read off the kind's own name rather than a fixed pair of enum members -
#: CR 122.1's kinds are an open set, and CR 122.1a's own rule is not limited
#: to the ±1/±1 pair; a named kind with no numbers at all ("charge", "hone" -
#: the latter has its own separate CR 122.1j effect, `_hone_counter_effects`,
#: since its bonus lands on what the counter's *permanent* is attached to,
#: never on itself) simply carries no bonus here.
_PT_COUNTER_KIND_RE = re.compile(r"^([+-])(\d+)/([+-])(\d+)$")


def _pt_counter_delta(kind: str) -> tuple[int, int] | None:
    """`kind`'s own (power, toughness) bonus (CR 122.1a), or `None` when it is
    not a "+X/+Y"/"-X/-Y"-shaped kind at all."""
    match = _PT_COUNTER_KIND_RE.fullmatch(kind)
    if match is None:
        return None
    power_sign, power_digits, toughness_sign, toughness_digits = match.groups()
    power = int(power_digits) * (1 if power_sign == "+" else -1)
    toughness = int(toughness_digits) * (1 if toughness_sign == "+" else -1)
    return power, toughness


def _counter_effects(board: Board) -> list[ContinuousEffect]:
    """Every "+X/+Y"/"-X/-Y"-named counter kind, summed per permanent, as the
    7c effects CR 613.4c/CR 122.1a say they are - +1/+1 and -1/-1 read the
    same general way as any other such kind (`_pt_counter_delta`), rather
    than as the two special-cased enum members CR 122.1 merely happens to
    name as examples.

    They carry timestamp 0 because counters have no timestamp of their own; 7c
    is addition, so their order among the other 7c effects cannot matter.
    """
    effects: list[ContinuousEffect] = []
    for card_id, chars in board.items():
        power = 0
        toughness = 0
        for kind, count in chars.counters.items():
            if not count:
                continue
            delta = _pt_counter_delta(kind)
            if delta is None:
                continue
            power += delta[0] * count
            toughness += delta[1] * count
        if power == 0 and toughness == 0:
            continue
        effects.append(
            ContinuousEffect(
                description=f"{chars.name}: {power:+d}/{toughness:+d} from counters",
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=0,
                from_counters=True,
                selector=_only(card_id),
                modification=modify_power_toughness(power, toughness),
            )
        )
    return effects


def _hone_counter_effects(board: Board, attachments: dict[UUID, UUID]) -> list[ContinuousEffect]:
    """CR 122.1j: "A hone counter on an Equipment gives +1/+0 to any
    creature that Equipment is attached to." - Sting, Bilbo's Sword's own
    counter kind.

    A 7c effect (CR 613.4c), the same sublayer `_counter_effects` above puts
    a permanent's own `+1/+1`/`-1/-1` count in - the difference is only the
    *selector*: a hone counter's bonus applies to what the Equipment carrying
    it is attached to, never to the Equipment itself, so this reads
    `attachments` (`CardState.attached_to`, not itself a computed
    characteristic - `board` alone has nowhere to keep it) rather than
    `board`'s own id. An Equipment with hone counters but nothing attached
    (CR 704.5n's own gap, or one that simply hasn't been equipped yet)
    contributes nothing, the same way an unattached Equipment's ordinary
    "Equipped creature gets ..." static already does.
    """
    effects: list[ContinuousEffect] = []
    for card_id, chars in board.items():
        amount = chars.counters.get("hone", 0)
        if amount <= 0 or "Equipment" not in chars.subtypes:
            continue
        host_id = attachments.get(card_id)
        if host_id is None or host_id not in board:
            continue
        effects.append(
            ContinuousEffect(
                description=f"{chars.name}: {amount:+}/+0 to equipped creature from hone counters",
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=0,
                from_counters=True,
                selector=_only(host_id),
                modification=modify_power_toughness(amount, 0),
            )
        )
    return effects


def _apply_group(
    group: Sequence[ContinuousEffect],
    board: Board,
    started: set[object],
    journal: Journal,
) -> dict[UUID, Characteristics]:
    """Apply one layer or sublayer's worth of effects (CR 613.7, CR 613.8).

    Timestamp order unless dependency says otherwise, and the order is worked
    out again after each application because applying one effect can create or
    destroy a dependency between two that have not applied yet (CR 613.8c).

    The tie-break after timestamp is `source_id` then `order` - both a pure
    function of where the effect came from (see `ContinuousEffect.order`),
    never `id`. `id` is freshly randomised on every rebuild of a static
    effect (CR 613.5 recomputes the board from scratch, `effects_for` mints a
    new `ContinuousEffect` each time), so sorting by it gave two same-timestamp
    effects - Scion of Draco's five colour grants, Elesh Norn, Grand
    Cenobite's two anthem lines - a different relative order on every
    computation, which CR 613.7 does not allow: `Journal.applied` order is a
    rules question, not an implementation detail. `source_id` is included
    ahead of `order` only as defence in depth against two different sources
    ever sharing one timestamp (nothing in this engine currently produces
    that: every permanent and every resolution batch gets its own tick from
    `ContinuousEffects.tick`) - it is stable across rebuilds and across a
    dump/decode cycle either way, since a permanent's id is minted once, when
    it enters play, and never changes after that.
    """
    pending = sorted(
        group,
        key=lambda effect: (
            effect.timestamp,
            str(effect.source_id) if effect.source_id is not None else "",
            effect.order,
        ),
    )
    current = dict(board)
    seen_cycles: set[frozenset[UUID]] = set()

    while pending:
        ready = [
            effect
            for effect in pending
            if not any(
                _depends_on(effect, other, current, started)
                for other in pending
                if other is not effect
            )
        ]
        if ready:
            # `pending` is in timestamp order, so the first ready effect is the
            # oldest one with nothing left to wait for (CR 613.8b).
            chosen = ready[0]
        else:
            # Every remaining effect is waiting on another remaining effect, so
            # they form a loop. CR 613.8b: ignore the dependency and fall back
            # to timestamp order.
            loop = frozenset(effect.id for effect in pending)
            if loop not in seen_cycles:
                seen_cycles.add(loop)
                journal.cycles.append([effect.description for effect in pending])
            chosen = pending[0]

        pending.remove(chosen)
        current = _apply_one(chosen, current, started, journal)

    return current


def _apply_one(
    effect: ContinuousEffect,
    board: Board,
    started: set[object],
    journal: Journal,
) -> dict[UUID, Characteristics]:
    if not _still_exists(effect, board, started):
        journal.skipped.append(effect.description)
        return dict(board)
    started.add(effect.ability_key)
    journal.applied.append(effect.description)
    return _project(effect, board, started)


def _project(
    effect: ContinuousEffect, board: Board, started: set[object]
) -> dict[UUID, Characteristics]:
    """Apply an effect to a board and hand back the result, changing nothing else.

    Used both to apply an effect for real and to ask "what would the board look
    like if this had applied", which is how dependency is detected.
    """
    if not _still_exists(effect, board, started):
        return dict(board)
    result = dict(board)
    for card_id, chars in board.items():
        if effect.selector(chars, board):
            result[card_id] = effect.modification(chars, board)
    return result


def _still_exists(effect: ContinuousEffect, board: Board, started: set[object]) -> bool:
    """Does this effect exist, given what layer 6 has done so far?

    CR 613.6: an effect that has already started applying keeps applying even
    once the ability generating it is gone. One that has not started and whose
    ability has been removed never applies at all.
    """
    if effect.ability_key in started:
        return True
    if effect.source_id is None or effect.source_ability is None:
        return True
    source = board.get(effect.source_id)
    if source is None:
        return False
    return source.has_ability(effect.source_ability)


def _depends_on(
    effect: ContinuousEffect,
    other: ContinuousEffect,
    board: Board,
    started: set[object],
) -> bool:
    """Does `effect` depend on `other` (CR 613.8a)?

    They are already known to share a layer and sublayer, which is clause (a).
    Clause (c) rules out a dependency between a characteristic-defining ability
    and a non-CDA effect. Clause (b) is the interesting one: apply `other` to a
    copy of the board and see whether `effect` changed - whether it still
    exists, what it applies to, or what it does to the objects it applies to.

    "What it does" deliberately ignores differences that are just `other`'s own
    handiwork on the object. Humility and Opalescence both set P/T in 7b and
    both change the same field on the same permanent, but neither changes what
    the other *does*, so they are independent and timestamps decide - which is
    the whole reason that pair is decided by timestamp and not by dependency.
    """
    if effect.characteristic_defining != other.characteristic_defining:
        return False

    after = _project(other, board, started)

    if _still_exists(effect, board, started) != _still_exists(effect, after, started):
        return True

    before_targets = {card_id for card_id, chars in board.items() if effect.selector(chars, board)}
    after_targets = {card_id for card_id, chars in after.items() if effect.selector(chars, after)}
    if before_targets != after_targets:
        return True

    for card_id in before_targets:
        was, now = board[card_id], after[card_id]
        before_result = effect.modification(was, board)
        after_result = effect.modification(now, after)
        if was == now:
            # `other` left this object alone, so any difference in the outcome
            # is `effect` reading the rest of the board and reading it
            # differently. That is a dependency.
            if before_result != after_result:
                return True
        elif _writes_differently(was, before_result, now, after_result):
            return True
    return False


def _writes_differently(
    was: Characteristics,
    before_result: Characteristics,
    now: Characteristics,
    after_result: Characteristics,
) -> bool:
    """Did applying `other` change *what this effect writes* (CR 613.8a)?

    Compare the outcomes, not the deltas. Two effects in one sublayer that set
    a permanent to the same value do not depend on each other just because the
    second one finds its work already done - the delta collapses to nothing
    while the value written is identical, and timestamps decide between them
    (CR 613.7). Comparing changed-field sets instead reads that collapse as a
    dependency, which wrongly lets a later effect jump the queue.

    A field holding a *collection* - subtypes, abilities, types, colors - needs
    one refinement on top of that. CR 613.8a asks whether applying `other`
    changes "what it does to any objects", which is a question about this
    effect's own contribution, not about the value it happens to land on. An
    additive effect meeting a setting effect in the same layer lands on
    different absolute values in the two orders purely because of the setting
    effect's own handiwork, and reading that as a dependency is what collapsed
    Blood Moon against Dryad of the Ilysian Grove into a single order.

    Dryad's "Lands you control are every basic land type in addition to their
    other types" and Blood Moon's "Nonbasic lands are Mountains" are exactly
    that pair. Neither changes the other's text, existence, or subject set -
    "nonbasic" is a supertype question (CR 205.4c, CR 305.8) that adding a
    basic land type cannot answer differently - so CR 613.8 finds no dependency
    and CR 613.7's timestamps decide, and the two orders genuinely differ:
    Blood Moon last leaves a nonbasic land a Mountain and nothing else, Dryad
    last leaves it all five basic types. So for a collection field this
    compares the elements the effect *adds and removes*, discounting whatever
    `other` itself added or removed on that object - which is the "ignores
    differences that are just `other`'s own handiwork" the caller's docstring
    promises. Order within the collection is not a characteristic and is
    ignored too.
    """
    written = _changed_fields(was, before_result) | _changed_fields(now, after_result)
    for field in written:
        before_value = getattr(before_result, field)
        after_value = getattr(after_result, field)
        if before_value == after_value:
            continue
        was_value, now_value = getattr(was, field), getattr(now, field)
        if not all(
            isinstance(value, tuple) for value in (before_value, after_value, was_value, now_value)
        ):
            # A scalar - power, toughness, controller. The value written is the
            # whole of what the effect does, so comparing outcomes is exact,
            # and it is what keeps Humility and Opalescence independent in 7b.
            return True
        # What `other` alone did to this object, which this effect is not
        # responsible for and must not be judged on.
        others_doing = set(now_value) ^ set(was_value)
        contribution_before = (set(before_value) ^ set(was_value)) - others_doing
        contribution_after = (set(after_value) ^ set(now_value)) - others_doing
        if contribution_before != contribution_after:
            return True
    return False


def _changed_fields(before: Characteristics, after: Characteristics) -> frozenset[str]:
    """Which characteristics an effect alters - "what it does", field by field."""
    return frozenset(
        field
        for field in type(before).model_fields
        if getattr(before, field) != getattr(after, field)
    )


def _every_card_state_in(game: Game) -> list[CardState]:
    """Every `CardState` a permanent could actually depart the battlefield to
    - not literally every zone `game` holds.

    `sync_granted_ability_texts`'s `search_pool`: a source that has left the
    battlefield still exists as a `CardState` somewhere else in the same
    game (a graveyard, most often), with its printed text unchanged, so this
    is what lets that source's grant still be recognised for removal with no
    memory of its own - on a cold-decoded game exactly as on a live one.

    `game.shared_zones`'s stack can hold an `AbilityOnStack`, which is not a
    `CardState` and has no quoted text of its own to read; everything else in
    `shared_zones` (battlefield, exile, command, ante - all small) is kept.

    `player.zones` drops `Zone.LIBRARY` alone, and that is the one exclusion
    that matters: a real board's two 60-card libraries are the dominant cost
    of this search (`Game.computed_board` measured it a 2.2x regression, and
    unlike the battlefield or a graveyard, a library's size scales with deck
    construction, not with anything that happened in the game), while a
    permanent this engine actually puts on the battlefield never legitimately
    lands there.

    That is a claim about this engine's registered effects today, not a CR
    one - CR 400.7 lets *any* zone change happen to *any* object, given the
    right effect - so it is checked, not assumed: `Game.put_cards_into_
    library`'s own battlefield branch is real but has exactly one registered
    caller, Brainstorm's "put two cards from your hand" clause
    (`machines/effects.py`), which only ever passes it cards from `player.
    hand`. The other library-bound path, `Game.put_into_graveyard`'s
    Green Sun's Zenith-shaped "shuffle it into its owner's library" redirect
    (`machines/replacement.py`'s `_stack_replacements`), is gated on
    `event.resolving`, which `put_into_graveyard`'s own docstring says is
    true only for "a spell's own successful CR 608 resolution" - never for a
    permanent already on the battlefield being destroyed. So nothing this
    engine can currently do sends a battlefield permanent to a library, and
    if a future card effect changes that (a "put target permanent into its
    owner's library" clause, say), this exclusion has to be revisited before
    that card's own static quoted grants can be trusted to reconcile away
    correctly once it leaves.
    """
    found: list[CardState] = [
        state
        for zone_cards in game.shared_zones.values()
        for state in zone_cards
        if isinstance(state, CardState)
    ]
    for player in game.players:
        for zone, zone_cards in player.zones.items():
            if zone is Zone.LIBRARY:
                continue
            found.extend(zone_cards)
    return found


def static_control_change_in_play(game: Game | None) -> bool:
    """Whether some permanent's own static ability changes another's
    controller right now - `_YOU_CONTROL_ATTACHED_RE` on an attached Aura or
    Equipment. The battlefield-sweep half of `ContinuousEffects.
    has_control_effect`, kept to a text check so the question stays cheaper
    than the board it saves computing."""
    if game is None:
        return False
    for permanent in getattr(game, "battlefield", ()):
        if permanent.attachment is None:
            continue
        text = permanent.oracle_text or ""
        if ("control enchanted" in text or "control equipped" in text) and any(
            _YOU_CONTROL_ATTACHED_RE.fullmatch(line.strip()) for line in text.split("\n")
        ):
            return True
    return False


# --------------------------------------------------------------------------
# The registry: real cards, and the effects they generate
# --------------------------------------------------------------------------


class LayerContext(EngineModel):
    """What an effect needs to know that is not standing on the battlefield.

    Almost every continuous effect reads only the board, which is what
    `Selector` and `Modification` are handed. A few read somewhere else:
    Tarmogoyf's characteristic-defining ability counts card types "among cards
    in all graveyards", and the layer engine never sees a graveyard.

    Anything read from here is read when the effects are *built*, not when they
    are applied, so a caller rebuilds them whenever it recomputes the board -
    which is what CR 613.5 asks for anyway ("continually and automatically
    performed by the game").

    `graveyards`, `your_graveyard`, and `graveyard_by_controller` below are the
    only `CardState`-typed fields anywhere in this module - every other layer
    field is an id, a `Selector`, or a `Modification`. This class is built
    fresh on every `compute_board`/`static_effects` call and is never stored on
    a serialized model (`Game`, `CardState`, or anything else that gets
    `model_dump`ed); nothing here should change that. Doing so would put a
    battlefield snapshot's `CardState`s into a second serialized location -
    exactly the stale-copy-by-reference hazard `_equip_effect`/`_crew_effect`
    hit for `KeywordActivation.card` (`machines/keywords.py`) - for a value
    that is already meant to be rebuilt every time, not carried across a round
    trip at all.
    """

    model_config = ConfigDict(frozen=True)

    #: Every card in every graveyard, all players' together.
    graveyards: tuple[CardState, ...] = ()

    #: The graveyard of the player who controls the spell or ability creating
    #: the effect. Kept apart from `graveyards` because the two are different
    #: questions: Tarmogoyf counts "cards in all graveyards", while Violent
    #: Urge's *delirium* counts "cards in **your** graveyard". Filling one with
    #: the other is the kind of plausible-and-wrong that only shows up in a
    #: two-player game where the opponent has a card type you do not.
    #:
    #: A resolving spell or ability has exactly one controller to ask, which is
    #: why this is a single tuple rather than a mapping.
    your_graveyard: tuple[CardState, ...] = ()

    #: Every graveyard, keyed by the username of the player it belongs to.
    #: A static ability's "your graveyard" (Boneyard Wurm) has no single
    #: controller the way a resolving spell does - `static_effects` shares one
    #: `LayerContext` across every permanent on the battlefield, each with its
    #: own controller - so the per-source answer has to be looked up rather
    #: than handed in directly the way `your_graveyard` is.
    graveyard_by_controller: Mapping[str, tuple[CardState, ...]] = Field(default_factory=dict)

    #: CR 500.1's active player (`Game.turn.active_player`) - the third thing
    #: the layer engine never sees standing on the battlefield. Sorin,
    #: Vengeful Bloodlord's own "During your turn, creatures and
    #: planeswalkers you control have lifelink." and Skilled Battlecarver's
    #: "During your turn, this creature has first strike." both read it: a
    #: condition checked once, at build time, the same way
    #: `_graveyard_count_gated_self_static_builder`'s graveyard count is -
    #: `effects_for` is rebuilt on every `computed_board()` call (CR 613.5),
    #: so an effect gated on this stops applying the instant the turn passes,
    #: with nothing to store or clear.
    active_player: str | None = None

    #: The current step's `Step` value (`Game.turn.step`): "During your end
    #: step, ..." (Zurgo, Thunder's Decree) reads it at build time, the same way
    #: `active_player` is read, so the effect is on only in that step.
    current_step: str | None = None

    #: The unspent mana in each player's mana pool, keyed by the username
    #: whose pool it is. A second thing the layer engine never sees, and for
    #: the same reason as a graveyard: it is not on the battlefield. Omnath,
    #: Locus of Mana's "Omnath gets +1/+1 for each unspent green mana you
    #: have" is the only reader, and like every other count here it is read
    #: when the effects are *built* - the board is rebuilt on every call
    #: (CR 613.5), so Omnath grows and shrinks with the pool rather than
    #: freezing at whatever was floating when it entered.
    unspent_mana_by_controller: Mapping[str, Mapping[Color, int]] = Field(default_factory=dict)

    def unspent_mana_of(self, controller: str | None, color: Color) -> int:
        """How much unspent mana of one colour a player has, or 0 for a player
        this context knows nothing about."""
        if controller is None:
            return 0
        return self.unspent_mana_by_controller.get(controller, {}).get(color, 0)

    #: Reads a printed "if <condition>" rider on a resolving spell's or
    #: ability's own layer sentence against the game as it is *now*, for the
    #: `source` the builder was handed (`Game.condition_holds`, so the cast
    #: record readers of `machines/conditions/cast_record.py` apply: "if you
    #: controlled a Faerie as you cast this spell" is the fact `CastRecord`
    #: locked at cast time, CR 601.2i, never the board as the spell resolves).
    #: A builder only ever asks it as the effects are *created* - `None` (a
    #: context nobody gave a game to) answers every rider unread, which
    #: builds nothing. Excluded from serialisation like the rest of this
    #: transient context.
    condition_holds: Callable[[str, CardState], bool | None] | None = Field(
        default=None, exclude=True
    )

    #: The shared exile zone (CR 406.1) - a fourth thing the layer engine
    #: never sees on the battlefield. Keen-Eyed Curator's "As long as there
    #: are four or more card types among cards exiled with this creature"
    #: counts only the cards linked to that one object (CR 607.2a), read
    #: through `cards_exiled_with`.
    exile: tuple[CardState, ...] = ()

    #: How many permanents on the battlefield are face down (CR 708.2) - a
    #: face-down permanent is a creature, so Ixidron's "the number of
    #: face-down creatures on the battlefield" is this count.
    face_down_creatures: int = 0

    #: Cards in each player's hand and each player's life total, keyed by
    #: username - two more things the layer engine never sees on the
    #: battlefield, read by the characteristic-defining abilities that count
    #: "the number of cards in your hand" (Aeon Chronicler) or compare life
    #: totals (Malignus, Roiling Horror). Like every field here they are read
    #: when the effects are built, and the board is rebuilt on every
    #: computation (CR 613.5), so the P/T tracks them live.
    hand_size_by_controller: Mapping[str, int] = Field(default_factory=dict)
    life_by_controller: Mapping[str, int] = Field(default_factory=dict)

    def opponents_life_totals(self, controller: str | None) -> tuple[int, ...]:
        """The life total of every player this context knows who is not
        `controller` (CR 102.2: in a two-player game the opponent; in a
        multiplayer game, each player not on `controller`'s team)."""
        return tuple(
            life for username, life in self.life_by_controller.items() if username != controller
        )

    def cards_exiled_with(self, source: CardState) -> tuple[CardState, ...]:
        """The cards exiled with `source` - this incarnation of it (CR 607.2a,
        CR 400.7; `ExileAnnotation.links_to`)."""
        return tuple(
            card
            for card in self.exile
            if card.exile_annotation is not None
            and card.exile_annotation.links_to(source.id, source.zone_change_stamp)
        )

    #: The top card of each player's library (CR 401.1), keyed by username and
    #: absent for an empty library - Mul Daya Channelers' "As long as the top
    #: card of your library is a creature card, ..." reads it. A card in a
    #: library is no permanent, so the layer engine never sees it standing on
    #: the battlefield; like every field here it is read when the effects are
    #: built, which is every CR 613.5 computation, so the effect follows the
    #: top card as it changes (CR 611.3a).
    top_card_by_player: Mapping[str, CardState] = Field(default_factory=dict)

    def top_card_of(self, controller: str | None) -> CardState | None:
        """The top card of `controller`'s library, or None for an empty library
        or a player this context knows nothing about."""
        if controller is None:
            return None
        return self.top_card_by_player.get(controller)

    def graveyard_of(self, controller: str | None) -> tuple[CardState, ...]:
        """The graveyard a static ability's own controller sees, or none if
        `controller` is not one this context knows about."""
        if controller is None:
            return ()
        return self.graveyard_by_controller.get(controller, ())

    def opponents_graveyard_of(self, controller: str | None) -> tuple[CardState, ...]:
        """Every card in a graveyard that is not `controller`'s own (Nighthawk
        Scavenger's "your opponents' graveyards") - `graveyards` minus
        `graveyard_of(controller)`, by identity rather than by owner, since a
        card's owner is not tracked here and two players can never share a
        `CardState`."""
        own = {card.id for card in self.graveyard_of(controller)}
        return tuple(card for card in self.graveyards if card.id not in own)

    #: `Game.turn_facts`, carried over so a static ability can read what has
    #: happened *this turn* (CR 603.9c's precedent: a "this turn" fact, not a
    #: game-state characteristic) the same way `Game.turn_fact_holds` does for
    #: an "Activate only if ..." restriction. Whiplash Wordsmith's "As long as
    #: an opponent was dealt noncombat damage this turn, ..." and Surveillance
    #: Phantasm's "As long as you've scried or surveilled this turn, ..." both
    #: read this rather than a stored flag, for the same live-recompute reason
    #: every other `LayerContext` field is.
    turn_facts: Mapping[str, frozenset[str]] = Field(default_factory=dict)

    #: Which players have gained life this turn (`Game.life_gained_this_turn`)
    #: - Infusion's own ability word (CR 207.2c), Tenured Concocter's "This
    #: creature gets +2/+0 as long as you gained life this turn." and
    #: Thornfist Striker's "Creatures you control get +1/+0 and have trample
    #: as long as you gained life this turn." A dedicated field rather than
    #: folded into `turn_facts` above: `Game.life_gained_this_turn` is its
    #: own top-level ledger (Ocelot Pride's intervening *if* already reads it
    #: directly, not through the generic `turn_facts`/`record_turn_fact`
    #: dictionary), so this mirrors that ledger by name instead of asking
    #: every caller to also write a `"life_gained"` `turn_facts` entry nobody
    #: else keeps.
    life_gained_this_turn: frozenset[str] = Field(default_factory=frozenset)

    def gained_life_this_turn(self, player: str | None) -> bool:
        """Whether `player` gained life this turn - `False` for a player this
        context knows nothing about, the same empty-is-false default
        `has_turn_fact` already uses."""
        if player is None:
            return False
        return player in self.life_gained_this_turn

    #: The ids of every creature that has dealt combat damage this turn
    #: (`Game.combat_damage_dealt_this_turn_by`) - a per-object "this turn"
    #: fact rather than a per-player one, so it is its own field instead of
    #: living in `turn_facts`. Ruric Thar's "hexproof as long as they haven't
    #: dealt combat damage yet" is the reader.
    combat_damage_dealt_this_turn: frozenset[UUID] = frozenset()

    #: `Game.counters_put_this_turn` as `(putter, permanent id, kind, zone
    #: change stamp)` - CR 122.6's per-turn placement history, read by "as long
    #: as you've put one or more +1/+1 counters on `<this>` this turn" and
    #: "each creature you control that you've put ... on this turn"
    #: (`machines/counter_effects`). The stamp is CR 400.7's incarnation.
    counters_put_this_turn: tuple[tuple[str, UUID, str, UUID | None], ...] = ()

    #: Each player's Ring-bearer designation (CR 701.54a/b), as `(id,
    #: zone_change_stamp)` keyed by username - `Game.ring_bearer_designations`.
    #: The Ring's "Your Ring-bearer is legendary and ..." (CR 701.54c) is an
    #: emblem's static ability, and the emblem cannot see which permanent
    #: carries the designation any more than Tarmogoyf can see a graveyard.
    ring_bearers: Mapping[str, tuple[UUID, UUID]] = Field(default_factory=dict)

    #: Each player's life total (CR 119.1), keyed by username - Serra
    #: Ascendant's "As long as you have 30 or more life, ..." reads its own
    #: controller's, which is not on the battlefield any more than a
    #: graveyard is. Read when the effects are built, like every field here.
    life_by_player: Mapping[str, int] = Field(default_factory=dict)

    #: The counters on each player (CR 122.1), keyed by username and kind -
    #: Mycosynth Fiend's "gets +1/+1 for each poison counter your opponents
    #: have" reads them, and they are not on the battlefield either. Read
    #: when the effects are built, like `life_by_player`.
    counters_by_player: Mapping[str, Mapping[str, int]] = Field(default_factory=dict)

    def player_counters(self, kind: str, players: Iterable[str]) -> int:
        """The total of `kind` counters on these players (0 for one this
        context knows nothing about)."""
        return sum(self.counters_by_player.get(player, {}).get(kind, 0) for player in players)

    #: Each player's starting life total (CR 103.4, `Player.starting_life`),
    #: keyed by username - Path of Bravery's "As long as your life total is
    #: greater than or equal to your starting life total, ..." compares the
    #: two. Read when the effects are built, like `life_by_player`.
    starting_life_by_player: Mapping[str, int] = Field(default_factory=dict)

    #: Every battlefield permanent's mana cost, keyed by its id - what CR
    #: 700.5's devotion counts ("the number of mana symbols ... among the mana
    #: costs of permanents that player controls"). Keyed by object rather than
    #: by player so whose permanent each is can be read off the board as the
    #: layers left it (CR 700.5a: after control-changing effects) by
    #: `SelfIfDevotionBelow`.
    mana_cost_by_id: Mapping[UUID, str] = Field(default_factory=dict)

    #: The players holding CR 702.195b's enduring story (`Player.
    #: has_enduring_story`) - what "As long as you have an enduring story, ..."
    #: asks of its own controller, a designation that no more stands on the
    #: battlefield than a life total does.
    enduring_story_players: frozenset[str] = frozenset()

    #: The creatures attacking right now (CR 508.1k), by id - `Game.combat`'s
    #: attackers. Attacking status does not stand on the battlefield as a
    #: characteristic, so "attacking tokens you control have first strike"
    #: (`AttackingTokensControlledBy`) reads it from here.
    attacking: frozenset[UUID] = frozenset()

    #: The creatures blocking right now (CR 509.1g), by id - the twin of
    #: `attacking` for "hexproof unless it's attacking or blocking".
    blocking: frozenset[UUID] = frozenset()

    #: The players holding the city's blessing (CR 702.131c, `Player.
    #: has_citys_blessing`) - what "As long as you have the city's blessing,
    #: ..." asks of its controller.
    citys_blessing_players: frozenset[str] = frozenset()

    #: Every tapped permanent on the battlefield right now (CR 110.5), by id -
    #: `TappedCreaturesControlledBy`'s own reader (Adept Watershaper's "Other
    #: tapped creatures you control have indestructible."), the identical
    #: physical-state-not-characteristic reasoning `attacking` is carried for.
    tapped_ids: frozenset[UUID] = frozenset()

    #: A per-turn, per-player *count* ledger - `Game.turn_counts`, carried the
    #: same way `turn_facts` already is, for a static ability that counts
    #: "how many" rather than asking "did you": Kinbinding's "Creatures you
    #: control get +X/+X, where X is the number of creatures that entered the
    #: battlefield under your control this turn."
    turn_counts: Mapping[str, Mapping[str, int]] = Field(default_factory=dict)

    #: How many creatures died under each player's control this turn (CR
    #: 700.4: put into a graveyard from the battlefield), judged as each last
    #: existed - Gimli, Mournful Avenger's "as long as two or more creatures
    #: died under your control this turn", off `Game.turn_history`.
    creatures_died_under_control: Mapping[str, int] = Field(default_factory=dict)

    def turn_count(self, fact: str, player: str | None) -> int:
        """How many times `fact` has happened for `player` this turn, or 0
        for a player or fact this context knows nothing about - the same
        empty-is-zero default `hand_size_of` already uses."""
        if player is None:
            return 0
        return self.turn_counts.get(fact, {}).get(player, 0)

    #: The ids of every creature currently on the battlefield whose own
    #: `CardState.turn_entered` is this turn (`Game._compute_board`'s own
    #: read of `CardState.turn_entered` against `Game.turn.turn_number`) -
    #: Bristlebane Outrider's own "As long as **another** creature entered
    #: the battlefield under your control this turn, this creature gets
    #: +2/+0.": the plain per-player `turn_facts`/`turn_counts` ledgers can
    #: only say *whether* or *how many* creatures entered, never whether the
    #: asking object was itself one of them, and "another" is exactly that
    #: per-object exclusion. A creature that already left again this turn is
    #: not in this set (it is not "currently on the battlefield" any more),
    #: which is the correct reading too - it still counts toward `turn_
    #: counts`'s own running total, just not toward this identity check.
    entered_this_turn_ids: frozenset[UUID] = frozenset()

    def designation_holds(self, condition: str, player: str | None) -> bool:
        """Whether `player` has the designation `condition` names
        (`machines/designations.py`) - `False` for a player or a condition
        this context knows nothing about."""
        if player is None:
            return False
        if condition == ENDURING_STORY:
            return player in self.enduring_story_players
        return False

    def life_of(self, player: str | None) -> int | None:
        """`player`'s life total, or None for a player this context does not know."""
        if player is None:
            return None
        return self.life_by_player.get(player)

    def starting_life_of(self, player: str | None) -> int | None:
        """`player`'s starting life total (CR 103.4), or None for a player this
        context does not know."""
        if player is None:
            return None
        return self.starting_life_by_player.get(player)

    #: Each player's hand size (CR 402.2), keyed by username - a seventh
    #: thing the layer engine never sees standing on the battlefield. Ms.
    #: Marvel, Kamala Khan's own granted CDA ("Ms. Marvel's base power is
    #: equal to the number of cards in your hand.", CR 613.1f grants it
    #: onto her own computed abilities) is the reader: read when the
    #: effects are built, like every other field here, so it moves with the
    #: hand as cards are drawn or discarded for the rest of the turn rather
    #: than freezing at whatever it was the moment the granting trigger
    #: resolved.
    hand_size_by_player: Mapping[str, int] = Field(default_factory=dict)

    #: Each player's library size (CR 401.1), keyed by username - Living
    #: Conundrum's "As long as there are no cards in your library, ..." reads
    #: its controller's, which is not on the battlefield either. Read when the
    #: effects are built, like `hand_size_by_player`.
    library_size_by_player: Mapping[str, int] = Field(default_factory=dict)

    def library_size_of(self, player: str | None) -> int | None:
        """How many cards `player`'s library holds, or `None` for a player
        this context knows nothing about."""
        if player is None:
            return None
        return self.library_size_by_player.get(player)

    #: `Game.cards_drawn_this_turn` - how many cards each player has drawn this
    #: turn (CR 121.2), the number Duelist of the Mind's characteristic-defining
    #: "power is equal to the number of cards you've drawn this turn" reads. A
    #: per-turn history fact the battlefield does not show; the board is rebuilt
    #: on every computation (CR 613.5), so the power tracks each draw.
    cards_drawn_this_turn: Mapping[str, int] = Field(default_factory=dict)

    def hand_size_of(self, player: str | None) -> int:
        """How many cards `player` holds, or 0 for a player this context
        knows nothing about - the same empty-is-zero default `unspent_mana_of`
        already uses."""
        if player is None:
            return 0
        return self.hand_size_by_player.get(player, 0)

    def has_turn_fact(self, fact: str, player: str | None) -> bool:
        """Whether `player` is on this turn's ledger for `fact` - `False` for
        a player this context knows nothing about, the same empty-is-false
        default every other `LayerContext` reader uses."""
        if player is None:
            return False
        return player in self.turn_facts.get(fact, frozenset())

    def has_turn_fact_for_opponent(self, fact: str, controller: str | None) -> bool:
        """Whiplash Wordsmith's "an opponent was dealt noncombat damage this
        turn" - true if anyone but `controller` is on this turn's ledger for
        `fact`. `turn_facts` records who a thing happened *to* or *by*, never
        who is an opponent of whom, so "any other recorded player" is the
        question, not a roster this context does not carry.
        """
        return any(player != controller for player in self.turn_facts.get(fact, frozenset()))


#: A card name to the continuous effects a copy of it generates. `source` is the
#: permanent (or the resolving spell); `timestamp` is its place in CR 613.7
#: order; `targets` is for the effects that have one; `context` is for the few
#: that read outside the battlefield.
EffectBuilder = Callable[
    [CardState, int, Sequence[CardState], LayerContext], list[ContinuousEffect]
]


def _emblems_in(game: Game | None) -> list[CardState]:
    """The emblems in the command zone (CR 114.1), in the order created."""
    if game is None:
        return []
    return [
        state
        for state in game.shared_zones[Zone.COMMAND]
        if isinstance(state, CardState) and state.card.layout is Layout.EMBLEM
    ]


# --------------------------------------------------------------------------
# Effects with a duration, and where a game keeps them (CR 611.2)
# --------------------------------------------------------------------------


class ContinuousEffects(EngineModel):
    """Every continuous effect a resolving spell or ability has created (CR 611.2).

    CR 611.2: "A continuous effect may be generated by the resolution of a spell
    or ability." Unlike a static ability's effect (CR 611.3), which exists only
    while its source is on the battlefield with the ability, this kind outlives
    the object that made it and has to be written down somewhere. This is that
    somewhere.

    A `Game` is meant to hold one::

        continuous_effects: ContinuousEffects = Field(default_factory=ContinuousEffects)

    and to call `end_the_turn()` from its cleanup step (CR 514.2, CR 703.4p).
    Until that field exists, a caller keeps a store of its own and hands the
    board to `board()` directly.

    **Timestamps.** One clock serves both kinds of effect, because CR 613.7
    orders them against each other:

    - CR 613.7a - a static ability's effect has the timestamp of the object it
      is on, so a permanent is stamped when this store first sees it.
    - CR 613.7b - "A continuous effect generated by the resolution of a spell or
      ability receives a timestamp at the time it's created", so `create` takes
      the next tick.

    `note` therefore has to be called as the board changes - `board()` does it
    every time - so that a permanent entering after a spell resolved is stamped
    later than that spell's effect, which is what CR 613.7 means by order.
    """

    _game: object = PrivateAttr(default=None)

    effects: list[ContinuousEffect] = Field(default_factory=list)
    """Effects created by resolution, oldest first. Static abilities are not
    stored: they are rebuilt from the battlefield every time (CR 611.3b)."""

    clock: int = 0
    """The last timestamp handed out (CR 613.7). Monotonic for the game."""

    entered: dict[UUID, int] = Field(default_factory=dict)
    """When each permanent was first seen, for CR 613.7a."""

    layer_notices: list[LayerNotice] = Field(default_factory=list)
    """Every card whose static/pump text `effects_for` could not read into a
    continuous effect - see `LayerNotice`."""

    keyword_counter_stamps: dict[str, int] = Field(default_factory=dict)
    """When each kind of keyword counter was last put on each permanent,
    keyed `"<permanent id>:<kind>"` - CR 613.7c: "Each counter receives a
    timestamp as it's put on an object or player. If that object or player
    already has a counter of that kind on it, each counter of that kind
    receives a new timestamp identical to that of the new counter." CR 613.1f
    applies keyword counters in layer 6 alongside ability-removing effects,
    so the order between them is this timestamp's: a flying counter put on
    *after* "loses all abilities" (Abigale, Eloquent First-Year's own
    sentence order) still grants flying, and one put on before it does not
    (`keyword_counter_grants`)."""

    def tick(self) -> int:
        """The next timestamp (CR 613.7)."""
        self.clock += 1
        return self.clock

    def stamp_keyword_counter(self, permanent_id: UUID, kind: str) -> None:
        """A keyword counter of `kind` was just put on the permanent: every
        counter of that kind on it takes the new timestamp (CR 613.7c)."""
        self.keyword_counter_stamps[f"{permanent_id}:{kind}"] = self.tick()

    def keyword_counter_grants(self, permanents: Iterable[CardState]) -> list[ContinuousEffect]:
        """CR 122.1b's keyword counters as the layer 6 grants CR 613.1f says
        they are, each at its own CR 613.7c timestamp
        (`keyword_counter_stamps`; a counter this store never saw put on -
        one a permanent entered with, say - is as old as the permanent's own
        entry, CR 613.7d).

        `printed_characteristics` already starts a permanent off with its
        combat keyword counters' lines, which is right until a layer 6
        "loses all abilities" or a layer 1 copy effect wipes the ability
        list: this re-grants each keyword after exactly the removals older
        than its counter, and a removal newer than the counter still takes
        it away, because `_apply_group` walks layer 6 in timestamp order.
        """
        from ..keyword_counters import KEYWORD_COUNTER_KEYWORDS

        grants: list[ContinuousEffect] = []
        for permanent in permanents:
            for kind in sorted(KEYWORD_COUNTER_KEYWORDS):
                if permanent.counters[kind] <= 0:
                    continue
                stamp = self.keyword_counter_stamps.get(
                    f"{permanent.id}:{kind}", self.entered.get(permanent.id, 0)
                )
                grants.append(
                    ContinuousEffect(
                        description=f"{permanent.name}: {kind} counter (CR 122.1b)",
                        layer=Layer.ABILITY,
                        timestamp=stamp,
                        from_counters=True,
                        selector=_only(permanent.id),
                        modification=grant_ability(kind.replace("_", " ").title()),
                    )
                )
        return grants

    def note(self, permanents: Iterable[CardState]) -> None:
        """Stamp any permanent this store has not seen yet (CR 613.7a).

        In the order given, which for a real battlefield is the order things
        entered it. A permanent already known keeps its stamp, so calling this
        again as the board changes is what keeps the ordering honest.
        """
        for permanent in permanents:
            if permanent.id not in self.entered:
                self.entered[permanent.id] = self.tick()

    def create(
        self,
        source: CardState,
        targets: Sequence[CardState] = (),
        context: LayerContext | None = None,
        ability_text: str | None = None,
        game: Game | None = None,
    ) -> list[ContinuousEffect]:
        """A spell or ability has resolved: create and keep its continuous effects.

        The effects come from `LAYER_EFFECTS`, so a card with no entry there
        creates nothing - the same silent gap `machines/effects.py` has for
        spells. `targets` is the set of objects the effect applies to, fixed now
        and never recomputed (CR 611.2c), and the whole batch is timestamped now
        (CR 613.7b).

        CR 611.2b is applied here: "If the 'for as long as' duration never
        starts, the effect does nothing." An effect whose condition is already
        false is dropped rather than stored, so it can never start later if the
        condition becomes true again. `game` is what `holds` checks that
        condition against - only ever needed when `source` is the one row in
        `LAYER_EFFECTS` that carries one (Tishana's Tidebinder).

        `ability_text` is the resolving ability's own text, when the caller is
        an ability rather than a spell - the only route by which an ability
        *granted* to `source` by another permanent (CR 613.1f) can be read at
        all. See `effects_for`.

        Returns the effects that were kept.
        """
        built = effects_for(
            source,
            self.tick(),
            targets,
            context,
            self.layer_notices,
            ability_text=ability_text,
        )
        kept = [effect for effect in built if effect.holds(game)]
        self.effects.extend(kept)
        self._note_control_change(kept, game)
        return kept

    def add(self, effect: ContinuousEffect, game: Game | None = None) -> ContinuousEffect:
        """Keep one hand-built effect, for a caller that is not going through
        the registry. Subject to CR 611.2b just the same."""
        if effect.holds(game):
            self.effects.append(effect)
            self._note_control_change([effect], game)
        return effect

    def bind_to_game(self, game: Game) -> None:
        """Remember the `Game` holding this store, so a stored control effect
        can reach it even from a caller that did not pass `game`.

        Excluded from serialisation, the same back-reference shape as
        `CardState.bind_to_game`; `Game.model_post_init` binds it.
        """
        self._game = game

    def _note_control_change(self, stored: Sequence[ContinuousEffect], game: Game | None) -> None:
        """A layer 2 control effect was stored (CR 613.1b): a new controller of
        a hideaway permanent may look at its face-down card (CR 702.75a)."""
        if not any(effect.layer is Layer.CONTROL for effect in stored):
            return
        bound = game if game is not None else cast("Game | None", self._game)
        if bound is not None:
            bound.note_hideaway_viewers()
            # CR 701.54a: a Ring-bearer another player gains control of stops
            # being its player's Ring-bearer, for good.
            bound.drop_ring_bearers_controlled_by_others()

    def has_control_effect(self, game: Game | None = None) -> bool:
        """Whether any stored effect is a layer 2 control change (CR 613.1b).

        Asked by `CardState.controller` before it recomputes the whole board
        to answer a question the board would answer with the base controller
        anyway. `set_controller` is reachable from two builders:
        `_gain_control_until_eot_builder`, which only ever runs from `create`
        (a *stored* effect), and `_you_control_attached_builder`, an Aura's
        own static "You control enchanted creature" that the battlefield sweep
        rebuilds - `static_control_change_in_play` answers for that one.
        """
        if any(effect.layer is Layer.CONTROL for effect in self.active(game)):
            return True
        bound = game if game is not None else cast("Game | None", self._game)
        return static_control_change_in_play(bound)

    def active(self, game: Game | None = None) -> list[ContinuousEffect]:
        """The stored effects whose duration is still running (CR 611.2b).

        A "for as long as" effect whose condition could turn true again
        (`HasCounter`) is dropped here and now rather than at cleanup
        (`end_the_turn`): CR 611.2b's duration does not begin again, so a
        counter put back must not revive it.
        """
        running = [effect for effect in self.effects if effect.holds(game)]
        if game is not None and len(running) != len(self.effects):
            # A "for as long as" grant of a quoted ability whose duration has
            # stopped (CR 611.2b) takes its line back off the permanent now,
            # not at cleanup: `_sync_stored_grant_ability_texts` only
            # reconciles texts some *running* grant still names.
            _ungrant_ended_stored_texts(
                [effect for effect in self.effects if effect not in running], running, game
            )
            self.effects = [
                effect
                for effect in self.effects
                if effect in running or effect.condition is None or not effect.condition.can_restart
            ]
        return running

    def end_the_turn(self, game: Game | None = None) -> list[ContinuousEffect]:
        """End every "until end of turn" effect (CR 514.2, CR 703.4p).

        CR 500.5b sends "until end of turn" to CR 514.2, and CR 514.2 is
        explicit about the moment: "all damage marked on permanents ... is
        removed and all 'until end of turn' and 'this turn' effects end." Both
        halves happen simultaneously, as the cleanup step's turn-based action
        CR 703.4p - **not** at the end step, which is a common misreading and
        is why a creature pumped in the end step is still pumped when the end
        step is over.

        Also drops the "for as long as" effects whose duration has stopped
        running, since nothing will ever bring them back. Returns what ended.
        """
        ended = [
            effect
            for effect in self.effects
            if effect.duration in (Duration.UNTIL_END_OF_TURN, Duration.UNTIL_END_OF_COMBAT)
            or not effect.holds(game)
        ]
        gone = {effect.id for effect in ended}
        self.effects = [effect for effect in self.effects if effect.id not in gone]
        if game is not None:
            _ungrant_ended_stored_texts(ended, self.effects, game)
            # CR 702.171a/b: a permanent "becomes saddled until end of turn" -
            # a designation, not a characteristic, so no stored effect carries
            # it, but it ends in the same CR 514.2 sentence.
            for permanent in game.battlefield:
                if permanent.saddled or permanent.saddled_by:
                    permanent.saddled = False
                    permanent.saddled_by = ()
        return ended

    def end_the_combat(self, game: Game | None = None) -> list[ContinuousEffect]:
        """End every "until end of combat" / "this combat" effect as the
        combat phase ends (CR 500.5a, CR 511.2: "at the end of the combat
        phase", not at the beginning of the end of combat step). Called from
        `Game.end_of_combat`, the moment CR 511.3 removes everything from
        combat. Returns what ended."""
        ended = [
            effect for effect in self.effects if effect.duration is Duration.UNTIL_END_OF_COMBAT
        ]
        if not ended:
            return []
        gone = {effect.id for effect in ended}
        self.effects = [effect for effect in self.effects if effect.id not in gone]
        if game is not None:
            _ungrant_ended_stored_texts(ended, self.effects, game)
        return ended

    def end_for_next_turn(self, username: str) -> list[ContinuousEffect]:
        """End every "until [username]'s next turn" effect as that turn begins.

        CR 611.2a: the effect "lasts as long as stated by the spell or
        ability creating it", and "until [a player's] next turn" ends the
        moment that turn begins, so this is called from `Game.begin_turn_for`
        - the same moment CR 302.6 clears summoning sickness for the player
        whose turn it now is. Unlike `end_the_turn`, this does not fire for
        every player's cleanup step: only the one named in
        `until_next_turn_of` loses the effect, so it survives an opponent's
        intervening turn untouched. Returns what ended.
        """
        ended = [
            effect
            for effect in self.effects
            if effect.duration is Duration.UNTIL_YOUR_NEXT_TURN
            and effect.until_next_turn_of == username
        ]
        gone = {effect.id for effect in ended}
        # "Until the end of your next turn": that turn has now begun, so the
        # effect is an ordinary "until end of turn" one for it (CR 514.2).
        self.effects = [
            effect.model_copy(
                update={"duration": Duration.UNTIL_END_OF_TURN, "until_next_turn_of": None}
            )
            if effect.duration is Duration.UNTIL_END_OF_YOUR_NEXT_TURN
            and effect.until_next_turn_of == username
            else effect
            for effect in self.effects
            if effect.id not in gone
        ]
        return ended

    def all_effects(
        self,
        permanents: Sequence[CardState],
        context: LayerContext | None = None,
        game: Game | None = None,
    ) -> list[ContinuousEffect]:
        """Static-ability effects and stored durational ones, in one list.

        Both are handed to `compute_board` together, because CR 613 applies
        every continuous effect in play in one pass and CR 613.7 orders them
        against each other by timestamp regardless of where they came from.
        """
        self.note(permanents)
        shared = context or LayerContext()
        if game is not None:
            from ..text_changes import sync_text_changes

            sync_text_changes(game)  # CR 613.1c: layer 3 comes before any ability is read
        sync_granted_ability_texts(permanents, _every_card_state_in(game) if game else None)
        # Quoted abilities a conditional static grants (`conditional_statics`).
        from .conditional_statics import sync_conditional_grant_texts

        sync_conditional_grant_texts(permanents, shared)
        # CR 114.4: an emblem's static abilities function in the command zone
        # (Kaito, Bane of Nightmares' "Ninjas you control get +1/+1."), and
        # CR 613.7d stamps it as it entered that zone.
        emblems = _emblems_in(game)
        self.note(emblems)
        stored = self.active(game)
        # The stored-effect twin of the printed-text sync just above: a
        # self-granted static/CDA line (Ms. Marvel, Kamala Khan's own) has to
        # be on `CardState.granted_ability_texts` *before* the sweep below
        # asks `effects_for` for this permanent's static contribution, or the
        # granted CDA would never be read until the computation after this
        # one - a turn late, and never at all once the grant itself expires
        # within the same computation that first sees it.
        _sync_stored_grant_ability_texts([*permanents, *emblems], stored)
        effects: list[ContinuousEffect] = []
        for permanent in [*permanents, *emblems]:
            effects.extend(
                effects_for(
                    permanent,
                    self.entered[permanent.id],
                    (),
                    shared,
                    self.layer_notices,
                    static_only=True,
                )
            )
        return effects + stored + self.keyword_counter_grants(permanents)

    def board(
        self,
        permanents: Sequence[CardState],
        context: LayerContext | None = None,
        game: Game | None = None,
        *,
        base_power_toughness: bool = False,
    ) -> ComputedBoard:
        """What the board is, with everything applied (CR 613.5). Emblems are
        on it too - they have no types, so no permanent-reading question sees
        them - because an effect's source must be on the board for CR 613.6's
        "does its ability still exist" check (`_still_exists`).

        `base_power_toughness` is `compute_board`'s own flag: CR 208.4b's base
        power and toughness rather than the full board."""
        effects = self.all_effects(permanents, context, game)
        return compute_board(
            [*permanents, *_emblems_in(game)],
            effects,
            base_power_toughness=base_power_toughness,
        )


from ._common import _YOU_CONTROL_ATTACHED_RE  # noqa: E402
from .model import (  # noqa: E402
    _SUBLAYERED,
    _SUBLAYERS_BY_LAYER,
    AddEveryCreatureType,
    Board,
    CopySublayer,
    Duration,
    Layer,
    Sublayer,
    WithChangeling,
    _only,
    grant_ability,
    modify_power_toughness,
)
from .parse import (  # noqa: E402
    _sync_stored_grant_ability_texts,
    _ungrant_ended_stored_texts,
    printed_characteristics,
    sync_granted_ability_texts,
)
from .registry import effects_for  # noqa: E402
