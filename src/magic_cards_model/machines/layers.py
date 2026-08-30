"""The layer system: what a permanent's characteristics actually are (CR 613).

A permanent's printed characteristics are only the starting point. Every
continuous effect in play is applied on top of them, in a fixed order of seven
layers (CR 613.1a-613.1g), and the answer to "what is this creature's power" is
whatever falls out at the end. The order is the whole rule: apply the same
effects in a different order and you get a different creature.

    613.1a  Layer 1: rules and effects that modify copiable values (CR 707)
    613.1b  Layer 2: control-changing effects
    613.1c  Layer 3: text-changing effects (CR 612)
    613.1d  Layer 4: type-changing effects
    613.1e  Layer 5: color-changing effects
    613.1f  Layer 6: ability-adding and ability-removing effects
    613.1g  Layer 7: power- and/or toughness-changing effects

Layer 7 has sublayers of its own (CR 613.4):

    613.4a  7a: characteristic-defining abilities that define P/T (CR 604.3)
    613.4b  7b: effects that set P/T to a specific number or value
    613.4c  7c: effects *and counters* that modify P/T without setting it
    613.4d  7d: effects that switch power and toughness

Note the sublayer count. Older writing about the layer system - and a lot of
folklore - splits 7c into "effects" and a separate 7d for counters, pushing the
switch out to 7e. The current rules do not: `knowledge_search` returns 613.4c as
"Effects **and counters** that modify power and/or toughness" and 613.4d as the
switch, with no 613.4e. Counters are modelled here as 7c effects for that
reason, flagged `from_counters` so a caller can still tell them apart.

Ordering inside a layer:

- **Timestamp order** (CR 613.7). Oldest first. In layers 2-6, effects from
  characteristic-defining abilities apply before everything else (CR 613.3);
  in layer 7 the CDAs get their own sublayer instead.
- **Dependency** (CR 613.8), which overrides timestamps. An effect depends on
  another when they share a layer and applying the other would change this
  one's existence, what it applies to, or what it does to the things it applies
  to (CR 613.8a). A dependent effect waits until everything it depends on has
  applied (CR 613.8b), and the order is re-derived after every application
  (CR 613.8c). If the dependencies form a loop, the loop is broken and
  timestamp order takes over (CR 613.8b).

The engine is pure. `compute_board` takes the permanents and the effects and
hands back a `Characteristics` per permanent; nothing on `CardState` is touched,
so there is no cached value to go stale (CR 613.5: "the application of
continuous effects ... is continually and automatically performed by the game").

`LAYER_EFFECTS` at the bottom is a scripted registry keyed by card name, the
same shape `machines/effects.py` uses for spells, kept only for shapes
`parsed_layer_effects` cannot read. `parsed_layer_effects` itself is driven by
`machines/abilities.py`'s own ability parser - `layer_readable_sentences` hands
it every `StaticAbility` and every `ActivatedAbility.effect` `parse_abilities`
found, rather than re-deriving reminder-stripped, cost-stripped sentences from
raw oracle text a second time. A card whose shape neither the parser nor the
registry reads still generates nothing, silently - see `LayerNotice`.

A static ability's effect exists exactly while its source does (CR 611.3b), so
it is rebuilt from the battlefield each time and never stored. An effect created
by a *resolving* spell or ability is different: CR 611.2a has it last "as long
as stated by the spell or ability creating it", which outlives the resolution
that made it, so it has to be written down. `ContinuousEffects` at the very
bottom is where, and `Duration` is how long.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from enum import IntEnum, StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models.card import Color, Supertype, Type
from ..models.card_state import CardState, Counter
from ..models.zone import Zone
from .abilities import layer_readable_sentences
from .combat import Keyword

# --------------------------------------------------------------------------
# Layers
# --------------------------------------------------------------------------


class Layer(IntEnum):
    """The seven layers, in the order they are applied (CR 613.1a-613.1g)."""

    COPY = 1
    CONTROL = 2
    TEXT = 3
    TYPE = 4
    COLOR = 5
    ABILITY = 6
    POWER_TOUGHNESS = 7


class Sublayer(IntEnum):
    """The sublayers of layer 7, in order (CR 613.4).

    `MODIFY` is 7c and covers counters as well as effects; `SWITCH` is 7d.
    There is no 7e in the current rules.
    """

    CHARACTERISTIC_DEFINING = 1  # 7a
    SET = 2  # 7b
    MODIFY = 3  # 7c
    SWITCH = 4  # 7d


#: Layer 7 is the only layer this engine splits into sublayers. Layer 1 has
#: sublayers too (CR 613.2), but copy effects are not modelled beyond the layer.
_SUBLAYERED = (Layer.POWER_TOUGHNESS,)


class Duration(StrEnum):
    """How long a continuous effect lasts (CR 611.2a, CR 611.2b).

    CR 611.2a: "A continuous effect generated by the resolution of a spell or
    ability lasts as long as stated by the spell or ability creating it (such as
    'until end of turn')."

    Three forms are modelled:

    - `UNTIL_END_OF_TURN` - Giant Growth's, Dismember's, Twisted Image's. It
      ends in the cleanup step, not at the end step: CR 500.5b sends "until end
      of turn" to CR 514.2, and CR 514.2 ends every such effect at the same
      moment marked damage is wiped, as the turn-based action CR 703.4p
      describes. `ContinuousEffects.end_the_turn` is that moment.
    - `FOR_AS_LONG_AS` - Tishana's Tidebinder's. The effect carries a
      `condition`, checked every time the board is computed, and CR 611.2b
      adds the corner case: "If the 'for as long as' duration never starts, the
      effect does nothing", so an effect whose condition is already false when
      it would be created is never stored at all.
    - `UNTIL_YOUR_NEXT_TURN` - Karn, the Great Creator's +1: "Until your next
      turn, up to one target noncreature artifact becomes an artifact creature
      ...". CR 800.4m confirms this is a real named duration category distinct
      from "until end of turn" ("continuous effects with durations that last
      until that player's next turn ... will last until that turn would have
      begun"), so the effect outlives the turn it was created in and the
      opponent's turn(s) after it, ending only when its own controller's next
      turn begins. `Game.begin_turn_for` - already the hook CR 302.6 uses to
      clear summoning sickness at the start of a player's turn - calls
      `ContinuousEffects.end_for_next_turn` for exactly this reason. The
      `until_next_turn_of` field carries whose turn ends it.
    - `INDEFINITE` - the default. A static ability's effect (CR 611.3) has no
      duration of this kind, and CR 611.1 has continuous effects lasting "for a
      fixed or indefinite period".
    """

    UNTIL_END_OF_TURN = "until end of turn"
    FOR_AS_LONG_AS = "for as long as"
    UNTIL_YOUR_NEXT_TURN = "until your next turn"
    INDEFINITE = "indefinite"


#: Whether a "for as long as" duration is still running (CR 611.2b). Reads the
#: game, not the layer engine's board: "for as long as this creature remains on
#: the battlefield" is a question about a zone.
Condition = Callable[[], bool]


# --------------------------------------------------------------------------
# Characteristics
# --------------------------------------------------------------------------


class Characteristics(BaseModel):
    """One permanent's characteristics with every continuous effect applied.

    This is the answer, not the state: it is recomputed from the printing plus
    the effects in play every time it is asked for, which is what CR 613.5
    describes. Frozen, so a modification returns a new one rather than editing
    the board underneath another effect.

    `abilities` is a list of ability text, one entry per line of oracle text.
    Nothing in this project parses static or triggered abilities yet, so text is
    the honest representation: layer 6 removal empties the list and a grant
    appends to it, and a caller can ask whether an ability survived.
    """

    model_config = ConfigDict(frozen=True)

    card_id: UUID
    name: str
    mana_value: float = 0.0
    controller: str | None = None
    supertypes: tuple[Supertype, ...] = ()
    types: tuple[Type, ...] = ()
    subtypes: tuple[str, ...] = ()
    colors: tuple[Color, ...] = ()
    abilities: tuple[str, ...] = ()
    power: int | None = None
    toughness: int | None = None
    #: Counters on the permanent. Not a characteristic - it is state the layer
    #: system reads (CR 613.4c) - but it has to travel with the object.
    counters: dict[str, int] = Field(default_factory=dict)

    @property
    def is_creature(self) -> bool:
        return Type.CREATURE in self.types

    @property
    def is_land(self) -> bool:
        return Type.LAND in self.types

    @property
    def is_basic(self) -> bool:
        """Basic is a supertype, not a land type (CR 205.4c, CR 305.8)."""
        return Supertype.BASIC in self.supertypes

    @property
    def power_toughness(self) -> tuple[int | None, int | None]:
        return self.power, self.toughness

    @property
    def numeric_power_toughness(self) -> tuple[int, int]:
        """Power and toughness as numbers, with CR 208.5 filling the gaps.

        "If a creature somehow has no value for its power, its power is 0. The
        same is true for toughness." A `*` in the power box (CR 208.2) is None
        here until a characteristic-defining ability defines it in sublayer 7a
        (CR 613.4a), so a Tarmogoyf whose CDA has been removed in layer 6
        (CR 613.1f) is a 0/0 rather than a creature with no power at all.

        `power_toughness` keeps the raw None, because a noncreature permanent
        genuinely has no power or toughness (CR 208.3) and that is worth being
        able to see.
        """
        return self.power or 0, self.toughness or 0

    @property
    def numeric_power(self) -> int:
        """Power with CR 208.5 filling a missing value, as one number."""
        return self.power or 0

    @property
    def numeric_toughness(self) -> int:
        """Toughness with CR 208.5 filling a missing value, as one number.

        CR 704.5f asks whether a creature's toughness "is 0 or less", so the
        state-based action needs a number and not a None. CR 208.5 supplies it:
        "If a creature somehow has no value for its power, its power is 0. The
        same is true for toughness."
        """
        return self.toughness or 0

    def has_ability(self, text: str) -> bool:
        return text in self.abilities

    def with_(self, **changes: object) -> Characteristics:
        """A copy with some characteristics replaced. The only way to change one."""
        return self.model_copy(update=changes)


#: The whole battlefield as the layer system sees it, mid-computation.
Board = Mapping[UUID, Characteristics]

#: Does this effect apply to that object? Judged against characteristics as
#: computed so far, with the rest of the board available for effects that count
#: things or say "each other" (CR 613.5).
Selector = Callable[[Characteristics, Board], bool]

#: What the effect does to one object it applies to. Pure: returns a new
#: `Characteristics`, never edits the one it was handed.
Modification = Callable[[Characteristics, Board], Characteristics]


def printed_characteristics(
    state: CardState, counters: Mapping[str, int] | None = None
) -> Characteristics:
    """A permanent's characteristics before any continuous effect applies.

    Straight off the Scryfall printing. For an ordinary permanent the copiable
    values layer 1 works on (CR 613.1a, CR 707.2) are just what is printed on
    the card, so this is where layer 2 onwards starts from.

    `counters` defaults to the counters on the permanent itself (CR 122.1); pass
    a mapping to override them, which is what lets a caller ask "what would this
    be with two more +1/+1 counters" without touching the board.

    A face-down permanent is the exception, and it belongs here rather than in a
    later layer: CR 613.2b makes layer 1b "face-down spells and permanents have
    their characteristics modified as defined in rule 708.2", and CR 708.2 makes
    the listed characteristics *copiable* values. So a face-down permanent starts
    from its listed set, not from the printing, and everything layer 2 onwards
    does applies on top of that.
    """
    card = state.card
    on_the_permanent = state.counters.as_dict() if counters is None else dict(counters)
    face_down = state.face_down_characteristics
    if face_down is not None:
        return Characteristics(
            card_id=state.id,
            name=face_down.name,
            # CR 202.3a: no mana cost means a mana value of 0. The card's own
            # cmc is not it - that is the printing, which CR 708.2 says this
            # object does not have while it is face down.
            mana_value=0,
            controller=state.controller,
            # CR 708.2 leaves it with *no* characteristics beyond those listed,
            # so there are no supertypes and no colors to carry over either.
            supertypes=(),
            types=tuple(face_down.types),
            subtypes=tuple(face_down.subtypes),
            colors=(),
            # Disguise lists ward {2} (CR 702.168b) where morph lists nothing
            # (CR 702.37c). It is a listed characteristic like any other, so it
            # has to reach the board as an ability line, not be dropped because
            # the model happens to keep it in a separate field.
            abilities=(tuple(_ability_lines(face_down.oracle_text)) + tuple(face_down.keywords)),
            power=face_down.power,
            toughness=face_down.toughness,
            counters=on_the_permanent,
        )
    return Characteristics(
        card_id=state.id,
        name=card.name,
        mana_value=card.cmc,
        controller=state.controller,
        supertypes=tuple(card.supertypes),
        types=tuple(card.types),
        subtypes=tuple(card.subtypes),
        colors=tuple(card.colors or ()),
        abilities=tuple(_ability_lines(card.oracle_text)),
        power=_as_number(card.power),
        toughness=_as_number(card.toughness),
        counters=on_the_permanent,
    )


def _ability_lines(oracle_text: str | None) -> list[str]:
    return [line.strip() for line in (oracle_text or "").splitlines() if line.strip()]


def _as_number(value: str | None) -> int | None:
    """Printed P/T as a number. `*` and `1+*` are None - they need a CDA in 7a."""
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Continuous effects
# --------------------------------------------------------------------------


class ContinuousEffect(BaseModel):
    """One continuous effect waiting to be applied in its layer (CR 611.1).

    Four things decide where it lands and what it does:

    - `layer` and `sublayer`: where in CR 613.1a-613.1g and CR 613.4a-613.4d it
      applies.
    - `timestamp`: its place in CR 613.7 order. For a static ability this is the
      timestamp of the permanent generating it (CR 613.7a), so a caller can just
      number the battlefield in the order things entered; an effect from a
      resolving spell is timestamped when it is created (CR 613.7b).
    - `selector`: which objects it applies to.
    - `modification`: what it does to one of them.

    `source_id` and `source_ability` are what let layer 6 turn an effect off.
    An effect whose source no longer has the ability that generates it does not
    apply - unless it has already started applying in an earlier layer, in which
    case it keeps going (CR 613.6). Blood Moon shutting off Urborg is exactly
    this, and so is Humility keeping its own 7b after removing its own ability
    in layer 6.

    A parser producing these should emit one `ContinuousEffect` per (layer,
    sublayer) an ability touches - Humility is three effects sharing one
    `source_ability` - and set `source_ability` to the exact oracle line, since
    that is the key ability removal is matched on.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    id: UUID = Field(default_factory=uuid4)
    #: Human-readable, and what the application journal reports.
    description: str
    layer: Layer
    sublayer: Sublayer | None = None
    timestamp: int = 0
    source_id: UUID | None = None
    source_ability: str | None = None
    #: True for an effect from a characteristic-defining ability (CR 604.3).
    #: CDAs go first in layers 2-6 (CR 613.3) and get sublayer 7a in layer 7,
    #: and they never form a dependency with a non-CDA effect (CR 613.8a).
    characteristic_defining: bool = False
    #: True when the effect is the P/T change from counters rather than from an
    #: effect. Both apply in 7c (CR 613.4c); the flag is only for reporting.
    from_counters: bool = False
    #: How long this effect lasts (CR 611.2a). A static ability's effect is
    #: `INDEFINITE` - it is switched off by the source losing the ability
    #: (CR 613.6), not by a duration running out.
    duration: Duration = Duration.INDEFINITE
    #: Only for `FOR_AS_LONG_AS`: whether the duration is still running.
    condition: Condition | None = None
    #: Only for `UNTIL_YOUR_NEXT_TURN`: whose next turn ends it (CR 800.4m).
    until_next_turn_of: str | None = None
    selector: Selector
    modification: Modification

    @property
    def holds(self) -> bool:
        """Is this effect's duration still running (CR 611.2b)?

        Always true for an effect with no `condition`. `UNTIL_END_OF_TURN` is
        not asked here - it is removed outright by `ContinuousEffects.end_the_turn`
        (CR 514.2), because CR 514.2 ends the effect rather than suspending it.
        """
        return self.condition is None or self.condition()

    @model_validator(mode="after")
    def _duration_matches_condition(self) -> ContinuousEffect:
        if self.duration is Duration.FOR_AS_LONG_AS and self.condition is None:
            raise ValueError('a "for as long as" effect needs a condition (CR 611.2b)')
        if self.duration is not Duration.FOR_AS_LONG_AS and self.condition is not None:
            raise ValueError(f"a {self.duration} effect has no condition to check")
        if self.duration is Duration.UNTIL_YOUR_NEXT_TURN and self.until_next_turn_of is None:
            raise ValueError('an "until your next turn" effect needs to say whose (CR 800.4m)')
        not_next_turn = self.duration is not Duration.UNTIL_YOUR_NEXT_TURN
        if not_next_turn and self.until_next_turn_of is not None:
            raise ValueError(f"a {self.duration} effect has no next-turn owner to check")
        return self

    @model_validator(mode="after")
    def _sublayer_matches_layer(self) -> ContinuousEffect:
        if self.layer in _SUBLAYERED and self.sublayer is None:
            raise ValueError(f"an effect in layer {self.layer} needs a sublayer")
        if self.layer not in _SUBLAYERED and self.sublayer is not None:
            raise ValueError(f"layer {self.layer} has no sublayers")
        if self.layer is Layer.POWER_TOUGHNESS:
            is_seven_a = self.sublayer is Sublayer.CHARACTERISTIC_DEFINING
            if is_seven_a != self.characteristic_defining:
                raise ValueError("sublayer 7a is exactly the characteristic-defining effects")
        return self

    @property
    def ability_key(self) -> tuple[UUID | None, str | None] | UUID:
        """What "this effect" means for CR 613.6.

        One ability generating parts in several layers is one effect, so the
        parts share a key: once any part has started applying, none of them can
        be switched off by later ability removal.
        """
        if self.source_id is None or self.source_ability is None:
            return self.id
        return (self.source_id, self.source_ability)


# --------------------------------------------------------------------------
# The engine
# --------------------------------------------------------------------------


class Journal(BaseModel):
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


class ComputedBoard(BaseModel):
    """Every permanent's characteristics, plus how the engine got there."""

    characteristics: dict[UUID, Characteristics]
    journal: Journal = Field(default_factory=Journal)

    def of(self, card: CardState | UUID) -> Characteristics:
        """The computed characteristics of one permanent."""
        card_id = card if isinstance(card, UUID) else card.id
        try:
            return self.characteristics[card_id]
        except KeyError:
            raise KeyError(f"{card_id} is not on this board") from None

    def __getitem__(self, card: CardState | UUID) -> Characteristics:
        return self.of(card)


def compute_board(
    permanents: Iterable[CardState],
    effects: Iterable[ContinuousEffect] = (),
    counters: Mapping[UUID, Mapping[str, int]] | None = None,
) -> ComputedBoard:
    """Apply every continuous effect to every permanent, in layer order (CR 613).

    Pure: the `CardState`s are read and never written. Ask again after the board
    changes and you get a fresh answer, which is what CR 613.5 requires.

    Counters come off the permanents themselves (`CardState.counters`, CR 122.1).
    `+1/+1` and `-1/-1` counters become 7c effects (CR 613.4c); other counters
    are carried on the result without changing anything.

    `counters` overrides what a permanent carries, one permanent at a time: a
    permanent named there is computed with exactly those counters and one that
    is not keeps its own. That is for asking hypotheticals, not for running the
    board - a real board needs no argument at all.
    """
    counters = counters or {}
    board: dict[UUID, Characteristics] = {}
    for state in permanents:
        board[state.id] = printed_characteristics(state, counters.get(state.id))

    # CR 611.2b: an effect whose "for as long as" duration has stopped running
    # is no longer applied. This is not CR 613.6's "already started applying"
    # carve-out - that one is about layer 6 removing the source's ability, and
    # a duration that has expired takes the effect away outright.
    all_effects = [effect for effect in effects if effect.holds] + _counter_effects(board)
    journal = Journal()
    started: set[object] = set()

    for layer in Layer:
        for sublayer in _sublayers_of(layer):
            group = [e for e in all_effects if e.layer is layer and e.sublayer is sublayer]
            if not group:
                continue
            # CR 613.3: in layers 2-6, characteristic-defining abilities apply
            # before everything else. Layer 7 does the same thing with 7a.
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


def _sublayers_of(layer: Layer) -> tuple[Sublayer | None, ...]:
    return tuple(Sublayer) if layer in _SUBLAYERED else (None,)


def _counter_effects(board: Board) -> list[ContinuousEffect]:
    """+1/+1 and -1/-1 counters, as the 7c effects CR 613.4c says they are.

    They carry timestamp 0 because counters have no timestamp of their own; 7c
    is addition, so their order among the other 7c effects cannot matter.
    """
    effects: list[ContinuousEffect] = []
    for card_id, chars in board.items():
        amount = chars.counters.get(Counter.PLUS_ONE, 0) - chars.counters.get(Counter.MINUS_ONE, 0)
        if amount == 0:
            continue
        effects.append(
            ContinuousEffect(
                description=f"{chars.name}: {amount:+}/{amount:+} from counters",
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=0,
                from_counters=True,
                selector=_only(card_id),
                modification=modify_power_toughness(amount, amount),
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
    """
    pending = sorted(group, key=lambda effect: (effect.timestamp, str(effect.id)))
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
    """
    written = _changed_fields(was, before_result) | _changed_fields(now, after_result)
    return any(getattr(before_result, field) != getattr(after_result, field) for field in written)


def _changed_fields(before: Characteristics, after: Characteristics) -> frozenset[str]:
    """Which characteristics an effect alters - "what it does", field by field."""
    return frozenset(
        field
        for field in type(before).model_fields
        if getattr(before, field) != getattr(after, field)
    )


# --------------------------------------------------------------------------
# Selectors and modifications: the vocabulary the registry is written in
# --------------------------------------------------------------------------


def _only(card_id: UUID) -> Selector:
    def selector(chars: Characteristics, board: Board) -> bool:
        return chars.card_id == card_id

    return selector


def every_creature(chars: Characteristics, board: Board) -> bool:
    return chars.is_creature


def creatures_controlled_by(username: str | None) -> Selector:
    def selector(chars: Characteristics, board: Board) -> bool:
        return chars.is_creature and chars.controller == username

    return selector


def other_creatures_controlled_by(source_id: UUID, username: str | None) -> Selector:
    """ "Other creatures you control" - the source itself is excluded."""

    def selector(chars: Characteristics, board: Board) -> bool:
        return chars.is_creature and chars.controller == username and chars.card_id != source_id

    return selector


def creatures_controlled_by_opponents_of(username: str | None) -> Selector:
    """ "Creatures your opponents control" - every creature someone else controls.

    A permanent with no controller at all is nobody's, so it is not caught.
    """

    def selector(chars: Characteristics, board: Board) -> bool:
        return chars.is_creature and chars.controller is not None and chars.controller != username

    return selector


def lands_controlled_by(username: str | None) -> Selector:
    def selector(chars: Characteristics, board: Board) -> bool:
        return chars.is_land and chars.controller == username

    return selector


def nonbasic_lands(chars: Characteristics, board: Board) -> bool:
    """Every land without the basic supertype (CR 205.4c)."""
    return chars.is_land and not chars.is_basic


def every_land(chars: Characteristics, board: Board) -> bool:
    return chars.is_land


def other_non_aura_enchantments(source_id: UUID) -> Selector:
    def selector(chars: Characteristics, board: Board) -> bool:
        return (
            chars.card_id != source_id
            and Type.ENCHANTMENT in chars.types
            and "Aura" not in chars.subtypes
        )

    return selector


def lose_all_abilities(chars: Characteristics, board: Board) -> Characteristics:
    """Layer 6 removal (CR 613.1f)."""
    return chars.with_(abilities=())


def grant_ability(text: str) -> Modification:
    """Layer 6 addition (CR 613.1f)."""

    def modification(chars: Characteristics, board: Board) -> Characteristics:
        if chars.has_ability(text):
            return chars
        return chars.with_(abilities=chars.abilities + (text,))

    return modification


def add_type(card_type: Type) -> Modification:
    """Layer 4: gain a card type on top of the ones already there (CR 205.1b)."""

    def modification(chars: Characteristics, board: Board) -> Characteristics:
        if card_type in chars.types:
            return chars
        return chars.with_(types=chars.types + (card_type,))

    return modification


def add_subtype(subtype: str, mana_ability: str | None = None) -> Modification:
    """Layer 4: gain a land type "in addition to" the ones already there.

    A land with a basic land type has the matching mana ability intrinsically
    (CR 305.6), so the ability comes along with the type. This is what makes
    Urborg turn everything into a black source.
    """

    def modification(chars: Characteristics, board: Board) -> Characteristics:
        if subtype in chars.subtypes:
            return chars
        changes: dict[str, object] = {"subtypes": chars.subtypes + (subtype,)}
        if mana_ability is not None and not chars.has_ability(mana_ability):
            changes["abilities"] = chars.abilities + (mana_ability,)
        return chars.with_(**changes)

    return modification


#: The five basic land types (CR 305.6) and the mana ability each one carries.
#: "An object with the land card type and a basic land type has the intrinsic
#: ability '{T}: Add [mana symbol]'", so gaining the type gains the ability.
BASIC_LAND_TYPES: dict[str, str] = {
    "Plains": "{T}: Add {W}.",
    "Island": "{T}: Add {U}.",
    "Swamp": "{T}: Add {B}.",
    "Mountain": "{T}: Add {R}.",
    "Forest": "{T}: Add {G}.",
}


def add_basic_land_types(chars: Characteristics, board: Board) -> Characteristics:
    """Layer 4: become every basic land type in addition to the others (CR 613.1d).

    Dryad of the Ilysian Grove. "In addition to" keeps whatever land types were
    already there, and each basic type gained brings its intrinsic mana ability
    with it (CR 305.6) - which is why a Dryad turns every land into a source of
    all five colours. It is *not* CR 305.7's "sets a land's subtype", so nothing
    is stripped.
    """
    subtypes = list(chars.subtypes)
    abilities = list(chars.abilities)
    for subtype, mana_ability in BASIC_LAND_TYPES.items():
        if subtype not in subtypes:
            subtypes.append(subtype)
        if mana_ability not in abilities:
            abilities.append(mana_ability)
    return chars.with_(subtypes=tuple(subtypes), abilities=tuple(abilities))


def set_basic_land_type(subtype: str, mana_ability: str) -> Modification:
    """Layer 4: become a basic land type, losing the old ones (CR 305.7).

    "If an effect sets a land's subtype to one or more of the basic land types,
    the land no longer has its old land type. It loses all abilities generated
    from its rules text, its old land types, and any copy effects..." - which is
    why Blood Moon is removal as much as it is a type change.

    Limitation: every subtype is replaced, which is right for a plain land and
    wrong for a land creature, whose creature types should survive.
    """

    def modification(chars: Characteristics, board: Board) -> Characteristics:
        return chars.with_(subtypes=(subtype,), abilities=(mana_ability,))

    return modification


def set_colors(*colors: Color) -> Modification:
    """Layer 5 (CR 613.1e)."""

    def modification(chars: Characteristics, board: Board) -> Characteristics:
        return chars.with_(colors=tuple(colors))

    return modification


def set_controller(username: str) -> Modification:
    """Layer 2 (CR 613.1b)."""

    def modification(chars: Characteristics, board: Board) -> Characteristics:
        return chars.with_(controller=username)

    return modification


def replace_text(old: str, new: str) -> Modification:
    """Layer 3, word for word (CR 612.1, CR 612.2)."""

    def modification(chars: Characteristics, board: Board) -> Characteristics:
        return chars.with_(abilities=tuple(line.replace(old, new) for line in chars.abilities))

    return modification


def set_power_toughness(power: int, toughness: int) -> Modification:
    """Sublayer 7b (CR 613.4b)."""

    def modification(chars: Characteristics, board: Board) -> Characteristics:
        return chars.with_(power=power, toughness=toughness)

    return modification


def set_power_toughness_to_mana_value(chars: Characteristics, board: Board) -> Characteristics:
    """Sublayer 7b, where the value is read off the object (CR 613.4b)."""
    value = int(chars.mana_value)
    return chars.with_(power=value, toughness=value)


#: How many of something an effect counts, judged against one object and the
#: board as it stands in that sublayer (CR 613.5).
Count = Callable[[Characteristics, Board], int]


def define_power_toughness(count: Count, power: int = 0, toughness: int = 0) -> Modification:
    """Sublayer 7a: a characteristic-defining ability that defines P/T.

    CR 613.4a: "Layer 7a: Effects from characteristic-defining abilities that
    define power and/or toughness are applied." CR 604.3a's first criterion is
    that the ability "defines an object's colors, subtypes, power, or
    toughness", and CR 208.2a is the printed side of it: a card whose power box
    reads `*` carries an ability worded "[This creature's] [power or toughness]
    is equal to ...".

    `count` is the number the card names and `power`/`toughness` are the
    constants added to it, so Tarmogoyf is `(types, 0, 1)` and Allosaurus Rider
    is `(lands, 1, 1)`. Both halves are *set*, never added to: a CDA defines the
    value rather than modifying one (CR 613.4a against CR 613.4c).
    """

    def modification(chars: Characteristics, board: Board) -> Characteristics:
        amount = count(chars, board)
        return chars.with_(power=amount + power, toughness=amount + toughness)

    return modification


def define_power(count: Count, power: int = 0) -> Modification:
    """Sublayer 7a, power only (CR 613.4a).

    Some CDAs define only one half - Nighthawk Scavenger's printed toughness is
    a plain `3` (CR 208.1), not a `*`, so only its power box carries the ability
    (CR 208.2a). `define_power_toughness` cannot express that: it always
    overwrites both halves, which would erase a real printed toughness that no
    ability ever named. This leaves toughness exactly as layers 1-6 left it.
    """

    def modification(chars: Characteristics, board: Board) -> Characteristics:
        return chars.with_(power=count(chars, board) + power)

    return modification


def modify_power_toughness(power: int, toughness: int) -> Modification:
    """Sublayer 7c (CR 613.4c). Adds; never sets.

    A creature with no value yet for its power counts as 0 (CR 208.5), which is
    what lets a pump land on a `*` whose CDA has been removed.
    """

    def modification(chars: Characteristics, board: Board) -> Characteristics:
        return chars.with_(
            power=(chars.power or 0) + power,
            toughness=(chars.toughness or 0) + toughness,
        )

    return modification


def modify_power_toughness_per(count: Count, power: int, toughness: int) -> Modification:
    """Sublayer 7c where the size of the pump is counted on the board (CR 613.4c).

    Relentless Rats: "+1/+1 for each other creature on the battlefield named
    Relentless Rats". Counted against the board as it stands in 7c, so a Rat
    that stopped being a creature earlier in the layers is not counted.
    """

    def modification(chars: Characteristics, board: Board) -> Characteristics:
        amount = count(chars, board)
        return chars.with_(
            power=(chars.power or 0) + power * amount,
            toughness=(chars.toughness or 0) + toughness * amount,
        )

    return modification


def count_other_creatures_named(name: str) -> Count:
    """How many *other* creatures on the board have this name."""

    def count(chars: Characteristics, board: Board) -> int:
        return sum(
            1
            for other in board.values()
            if other.card_id != chars.card_id and other.is_creature and other.name == name
        )

    return count


def count_lands_controlled_by(username: str | None) -> Count:
    def count(chars: Characteristics, board: Board) -> int:
        return sum(1 for other in board.values() if other.is_land and other.controller == username)

    return count


def count_card_types(cards: Iterable[CardState]) -> int:
    """How many distinct card types are among these cards (CR 300.1).

    Tarmogoyf's number. The card types are the fifteen CR 300.1 lists; a card
    with two of them - an artifact creature - counts for both, and duplicates
    across cards count once.
    """
    types: set[Type] = set()
    for state in cards:
        types.update(state.card.types)
    return len(types)


def switch_power_toughness(chars: Characteristics, board: Board) -> Characteristics:
    """Sublayer 7d (CR 613.4d).

    "Such effects take the value of power and apply it to the creature's
    toughness, and take the value of toughness and apply it to the creature's
    power" - the values as they stand at 7d, after 7a through 7c.
    """
    return chars.with_(power=chars.toughness, toughness=chars.power)


# --------------------------------------------------------------------------
# Parsed from oracle text: pump, keyword-grant, type-change and P/T-set
# shapes (W5, W6, W7)
# --------------------------------------------------------------------------
#
# `LAYER_EFFECTS` below is a per-card registry, kept only for shapes this
# section's parser does not generalise. The sentences it runs against come from
# `machines/abilities.py`'s own ability parser (`layer_readable_sentences`),
# not a second, independent reading of raw oracle text - see `_effect_sentences`.
#
#     "Target creature gets +N/+N until end of turn."                     (CR 613.4c)
#     "Target creature gets +N/+N and gains <keyword> until end of turn." (CR 613.4c, CR 613.1f)
#     "Target creature gains <keyword> until end of turn."                (CR 613.1f, CR 113.10)
#     "Creatures you control get +N/+N."                                  (CR 613.4c, static)
#     "Creatures you control have <keyword>[, <keyword> and <keyword>]."  (CR 613.1f, static)
#     "This creature has base power and toughness N/N until end of turn." (CR 613.4b)
#     "Until your next turn, up to one target ... becomes a[n] <type>
#      creature with power and toughness each equal to its mana value."   (CR 613.1d, 613.4b, 613.6)
#
# each also read for a permanent's own "this creature" (an activated
# ability's own source, `_basking_rootwalla`'s old shape) and, for the anthem
# and indefinite-keyword-grant ones, the "other creatures you control" /
# "creatures your opponents control" variants Elesh Norn and Elesh Norn's
# keyword-granting cousins print as separate lines. The type-change/P/T-set
# pair (W6) is Karn, the Great Creator's +1 and Flexible Waterbender's
# waterbend ability - a type change plus a P/T *set* (not a modifier) is a
# different rules shape from the pump/anthem ones, which is why sublayer 7b
# (`Sublayer.SET`) rather than 7c (`Sublayer.MODIFY`) is what tells "gets
# +N/+N" and "has base power and toughness N/N" apart once both apply to the
# same creature (CR 613.4).
#
# `effects_for` tries `LAYER_EFFECTS` first and only falls back to
# `parsed_layer_effects` on a miss, so a future printing that needs an
# exception can still get an explicit row that shadows the parser.
#
# **Fail-closed.** A sentence that opens the same way one of these shapes does -
# "target creature gets", "this creature gets", "creatures you control get",
# "creatures you control have", "creatures your opponents control get/have" -
# but does not fully match is never silently dropped: `looks_like_unparsed_
# layer_effect` catches it and `effects_for` records a `LayerNotice` instead of
# producing nothing that looks identical to a card with no effect at all. Fiend
# Artisan's "for each creature card in your graveyard" and Violent Outburst's
# "... until end of turn" team-wide pump are real pool cards this parser cannot
# read, and both are exactly this case; Mosswort Bridge's "if creatures you
# control have total power 10 or greater" is not - it is an activated
# ability's own intervening condition, not the sentence's own opening words
# (see `_indefinite_keyword_grant_builder`'s own remarks), so it is correctly
# never even offered to `_LOOKS_LIKE_LAYER_EFFECT_RE`. Any other sentence -
# "Whenever ...", "Delirium — ...", a bare "Vigilance" line, Dryad of the
# Ilysian Grove's land-drop grant - is not this wave's territory at all and
# produces no notice, the same way `_dryad_of_the_ilysian_grove`'s own
# docstring already documents leaving that
# line to nobody.

#: The subjects this wave's parser reads: a spell's own target, an activated
#: or triggered ability's own source (`create_continuous_effect_of_ability`
#: calls in with `targets=[source]` when the ability names no target of its
#: own), or a triggered ability's own target - "another target creature you
#: control" (Oliphaunt's attack trigger) - which reaches here the same way a
#: spell's "target creature" does, through whatever `targets` the caller
#: resolved.
_SUBJECT = r"(?:target creature|this creature|another target creature(?: you control)?)"

_PUMP_RE = re.compile(
    rf"^{_SUBJECT} gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)"
    rf"(?: and gains (?P<keyword>[a-z ]+))? until end of turn\.?$",
    re.IGNORECASE,
)

_KEYWORD_GRANT_RE = re.compile(
    rf"^{_SUBJECT} gains (?P<keyword>[a-z ]+) until end of turn\.?$",
    re.IGNORECASE,
)

_ANTHEM_RE = re.compile(
    r"^(?P<other>other )?creatures (?P<whose>you control|your opponents control) get "
    r"(?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)\.?$",
    re.IGNORECASE,
)

#: "[Other] creatures [you control|your opponents control] have <keyword>[,
#: <keyword>, ... and <keyword>]." (True Conviction: "Creatures you control
#: have double strike and lifelink.") - the anthem shape's keyword-granting
#: twin: no "until end of turn" (CR 611.3's static effect lasts exactly as
#: long as its source does, CR 611.3b), so it lands in layer 6 (CR 613.1f)
#: rather than the temporary layer-6 grant `_KEYWORD_GRANT_RE` reads for a
#: single targeted or self-referential creature. Anything printed after
#: "have"/"has" is checked keyword-by-keyword against `_KNOWN_KEYWORDS` by
#: `_split_and_validate_keywords`, so a card naming something outside that
#: whitelist - or a non-keyword clause "have total power 10 or greater"
#: (Mosswort Bridge) - fails the match and falls to
#: `looks_like_unparsed_layer_effect` instead of granting the wrong thing.
_INDEFINITE_KEYWORD_GRANT_RE = re.compile(
    r"^(?P<other>other )?creatures (?P<whose>you control|your opponents control) "
    r"(?:have|has) (?P<keywords>[a-z]+(?: [a-z]+)?(?:(?:,\s*| and )[a-z]+(?: [a-z]+)?)*)\.?$",
    re.IGNORECASE,
)

#: "[Subject] has/have base power and toughness N/N until end of turn."
#: (Flexible Waterbender). Sublayer 7b (CR 613.4b: "Effects that refer to the
#: base power and/or toughness of a creature apply in this layer") - a *set*,
#: unlike `_PUMP_RE`'s 7c modifier, which is the whole reason this is a
#: separate shape rather than folded into the pump regex: "gets +N/+N" and
#: "has base power and toughness N/N" land in different sublayers and produce
#: different answers once another effect of the other kind is on the same
#: creature (CR 613.4).
_BASE_PT_SET_RE = re.compile(
    rf"^{_SUBJECT} has base power and toughness (?P<power>\d+)/(?P<toughness>\d+)"
    r" until end of turn\.?$",
    re.IGNORECASE,
)

#: The card types a "becomes a[n] <type> creature" sentence can name besides
#: creature itself - CR 300.1's other permanent types, since only a permanent
#: sits on a battlefield to be targeted this way. Read the same way
#: `machines/targeting.py`'s `_TYPE_NOUNS` reads them, kept separate rather
#: than imported so this module's parser does not reach across into another
#: one's private table for a four-entry set.
_OTHER_PERMANENT_TYPE_WORDS: dict[str, Type] = {
    "artifact": Type.ARTIFACT,
    "enchantment": Type.ENCHANTMENT,
    "land": Type.LAND,
    "planeswalker": Type.PLANESWALKER,
    "battle": Type.BATTLE,
}

#: "Until your next turn, up to one target <restriction> becomes a[n] <type>
#: creature with power and toughness each equal to its mana value." (Karn, the
#: Great Creator's +1). Layer 4 for the type (CR 613.1d) and sublayer 7b for
#: the P/T (CR 613.4b: "Effects that refer to the base power and/or toughness
#: of a creature apply in this layer"), one effect applying in two layers
#: (CR 613.6). The target noun phrase itself ("up to one target noncreature
#: artifact") is not re-parsed here - `targets` already carries whatever the
#: caller resolved, the same contract `_SUBJECT`'s shapes already rely on -
#: only the duration and the type named after "becomes a[n]" matter to the
#: builder.
_BECOMES_CREATURE_WITH_MANA_VALUE_PT_RE = re.compile(
    r"^Until your next turn, up to \S+ target [a-z]+(?: [a-z]+)* becomes an? "
    r"(?P<extra_type>[a-z]+) creature with power and toughness each equal to "
    r"its mana value\.?$",
    re.IGNORECASE,
)

#: The pump/keyword-grant/base-P/T-set/becomes-creature shapes' opening words
#: - everything `_LOOKS_LIKE_LAYER_EFFECT_RE` matches **except** the anthem
#: shape - so a caller can ask "does this look like a one-shot *resolution*
#: effect (CR 611.2)" without the static-only anthem shape (CR 611.3)
#: answering yes. `machines/effects.py`'s routing needs exactly that
#: distinction: see `is_resolution_layer_effect_text`.
_LOOKS_LIKE_RESOLUTION_LAYER_EFFECT_RE = re.compile(
    rf"^{_SUBJECT} (?:gets?|gains?|has|have)\b|^Until your next turn, up to \S+ target\b",
    re.IGNORECASE,
)

#: "[Other] creatures [you control|your opponents control] get +N/+N." /
#: "... have/has <keyword>[, <keyword> ...]." - `_ANTHEM_RE`'s and
#: `_INDEFINITE_KEYWORD_GRANT_RE`'s shared opening words, loosened the same
#: way `_LOOKS_LIKE_RESOLUTION_LAYER_EFFECT_RE` loosens the other four
#: shapes - Asceticism's "Creatures you control have hexproof." needs the
#: "have" branch to be caught as a failed parse (hexproof is outside
#: `_KNOWN_KEYWORDS`) rather than silently doing nothing. Kept apart from
#: `_LOOKS_LIKE_RESOLUTION_LAYER_EFFECT_RE` (see `is_resolution_layer_effect_text`)
#: because CR 611.3 makes both of these group shapes a permanent's own static
#: ability, never a spell's or ability's one-shot resolution effect (CR
#: 611.2) - Glorious Anthem's *cast* does not create a second, permanent copy
#: of its own anthem, and the same is true of a keyword granted to a group
#: this way.
_LOOKS_LIKE_ANTHEM_RE = re.compile(
    r"^(?:other )?creatures (?:you control|your opponents control) (?:get|have|has)\b",
    re.IGNORECASE,
)

#: The same shapes, loosened to just their opening words, so a sentence that
#: starts like one of them but does not fully match is caught instead of
#: silently producing nothing (see `looks_like_unparsed_layer_effect`).
#:
#: Matched against the *normalised* sentence (`_normalize_duration_first`),
#: so a card that leads with its duration - "Until end of turn, target
#: creature gets ..." (Tower Above) - is read the same way as one that
#: trails it, rather than falling outside every one of these patterns and
#: producing neither an effect nor a notice (CR 611.2a: the duration is
#: "as stated by the spell or ability", with no rule pinning it to one end
#: of the sentence).
_LOOKS_LIKE_LAYER_EFFECT_RE = re.compile(
    _LOOKS_LIKE_RESOLUTION_LAYER_EFFECT_RE.pattern + "|" + _LOOKS_LIKE_ANTHEM_RE.pattern,
    re.IGNORECASE,
)

#: "Until end of turn, <rest>." - the duration named up front rather than
#: trailing the sentence (Tower Above: "Until end of turn, target creature
#: gets +4/+4 and gains trample, wither, and ..."). CR 611.2a states the
#: duration "as stated by the spell or ability" with no rule that fixes its
#: position in the sentence, so this is a phrasing this wave's shapes must
#: read regardless of where "until end of turn" sits.
_DURATION_FIRST_RE = re.compile(r"^until end of turn,\s*(?P<rest>.+)$", re.IGNORECASE)


def _normalize_duration_first(sentence: str) -> str:
    """Rewrite "Until end of turn, X" to "X until end of turn." so a
    duration-first sentence reaches `_parse_layer_sentence` and
    `_LOOKS_LIKE_LAYER_EFFECT_RE` the same way the ordinary trailing-duration
    phrasing already does. A sentence that does not open this way is returned
    unchanged.
    """
    match = _DURATION_FIRST_RE.match(sentence.strip())
    if match is None:
        return sentence
    rest = match.group("rest").strip().rstrip(".")
    return f"{rest} until end of turn."


def _effect_sentences(oracle_text: str | None) -> list[str]:
    """Every sentence a continuous effect could come from, off a card's own
    printed text.

    This used to re-derive its sentences from raw oracle text: strip a line's
    trailing reminder text, strip an activation cost or a triggered ability's
    own trigger condition ahead of it, then split what is left on ". "
    boundaries. That duplicated `machines/abilities.py`'s own line classifier -
    which already tells a `StaticAbility` line from an `ActivatedAbility`'s
    cost-and-effect from a `TriggeredAbility`'s condition-and-effect, and
    already strips reminder text (CR 207.2a) anywhere in the line, not only at
    its end - without ever consulting it, so `StaticAbility` was parsed
    upstream and thrown away. `layer_readable_sentences` is that classifier,
    read for exactly the three kinds of line a continuous effect's own
    sentence can be (CR 604.1 static, CR 602.1 activated with its cost split
    off, or CR 603.1 triggered with its condition split off); see its
    docstring for why a keyword or unparsed line is not one of them, and for
    why reading a triggered ability's own effect body here is safe even
    though this same function also feeds the battlefield sweep
    (`static_effects`) for every permanent on the board, not only a resolving
    ability's own effect (`create_continuous_effect_of_ability`) - Oliphaunt's
    attack trigger among them: `static_effects` always calls with an empty
    `targets` sequence, and every shape below produces nothing for an empty
    target set, so the sentence being readable here only ever creates a real
    effect when the ability actually resolves and supplies its targets.
    """
    return layer_readable_sentences(oracle_text)


def _pump_and_keyword_builder(power: int, toughness: int, keyword: str | None) -> EffectBuilder:
    """ "[Subject] gets +N/+N [and gains <keyword>] until end of turn."

    Sublayer 7c for the pump (CR 613.4c: "modify power and/or toughness ...
    don't set"), layer 6 for the keyword (CR 613.1f, CR 113.10). Applies to
    whatever `targets` the caller hands in - a spell's resolved targets
    (`create_continuous_effect`), or an ability's own source
    (`create_continuous_effect_of_ability`, called with `targets=[source]`).
    Called with none at all - what a static sweep of the battlefield does for
    every permanent - correctly produces nothing: this is never a static
    ability's own effect.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        effects: list[ContinuousEffect] = []
        for target in targets:
            effects.append(
                ContinuousEffect(
                    description=f"{source.name}: {target.name} gets {power:+d}/{toughness:+d}",
                    layer=Layer.POWER_TOUGHNESS,
                    sublayer=Sublayer.MODIFY,
                    timestamp=timestamp,
                    duration=Duration.UNTIL_END_OF_TURN,
                    selector=_only(target.id),
                    modification=modify_power_toughness(power, toughness),
                )
            )
            if keyword is not None:
                effects.append(
                    ContinuousEffect(
                        description=f"{source.name}: {target.name} gains {keyword}",
                        layer=Layer.ABILITY,
                        timestamp=timestamp,
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=_only(target.id),
                        modification=grant_ability(keyword),
                    )
                )
        return effects

    return builder


def _keyword_grant_builder(keyword: str) -> EffectBuilder:
    """ ""[Subject] gains <keyword> until end of turn." (CR 613.1f, CR 113.10)."""

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=f"{source.name}: {target.name} gains {keyword}",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                duration=Duration.UNTIL_END_OF_TURN,
                selector=_only(target.id),
                modification=grant_ability(keyword),
            )
            for target in targets
        ]

    return builder


def _anthem_builder(
    power: int, toughness: int, *, other: bool, whose: str, line: str
) -> EffectBuilder:
    """ "[Other] creatures [you control|your opponents control] get +N/+N." (CR 613.4c).

    A static ability's effect (CR 611.3), so it is timestamped off the source
    permanent (CR 613.7a) and switched off the moment the source loses the
    ability (CR 613.6) - `source_ability` is the exact printed sentence,
    matching what layer 6 removal matches on.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        selector, subject = _creature_group(source, other=other, whose=whose)
        return [
            ContinuousEffect(
                description=f"{source.name}: {subject} get {power:+d}/{toughness:+d}",
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=line,
                selector=selector,
                modification=modify_power_toughness(power, toughness),
            )
        ]

    return builder


def _creature_group(source: CardState, *, other: bool, whose: str) -> tuple[Selector, str]:
    """The selector and printed subject `_anthem_builder` and
    `_indefinite_keyword_grant_builder` share: "[other] creatures [you
    control|your opponents control]", read off the same three regex groups
    both shapes parse.
    """
    if whose == "you control":
        selector = (
            other_creatures_controlled_by(source.id, source.controller)
            if other
            else creatures_controlled_by(source.controller)
        )
        subject = "other creatures you control" if other else "creatures you control"
        return selector, subject
    return (
        creatures_controlled_by_opponents_of(source.controller),
        "creatures your opponents control",
    )


def _indefinite_keyword_grant_builder(
    keywords: list[str], *, other: bool, whose: str, line: str
) -> EffectBuilder:
    """ "[Other] creatures [you control|your opponents control] have <keyword(s)>."
    (True Conviction) - layer 6 (CR 613.1f), one grant per keyword.

    A static ability's effect (CR 611.3), so - like `_anthem_builder` - it is
    timestamped off the source permanent (CR 613.7a) and stops the moment the
    source loses the ability (CR 613.6): `source_ability` is the exact printed
    sentence, matching what layer 6 removal matches on.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        selector, subject = _creature_group(source, other=other, whose=whose)
        return [
            ContinuousEffect(
                description=f"{source.name}: {subject} have {keyword}",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=line,
                selector=selector,
                modification=grant_ability(keyword),
            )
            for keyword in keywords
        ]

    return builder


def _base_pt_set_builder(power: int, toughness: int) -> EffectBuilder:
    """ "[Subject] has base power and toughness N/N until end of turn." (Flexible
    Waterbender). Sublayer 7b (CR 613.4b), not 7c: this *sets* the value rather
    than modifying it, so it lands ahead of any pump on the same creature
    regardless of which was created first (CR 613.4's sublayer order overrides
    CR 613.7's timestamp order between different sublayers).
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=f"{source.name}: {target.name} has base P/T {power}/{toughness}",
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.SET,
                timestamp=timestamp,
                duration=Duration.UNTIL_END_OF_TURN,
                selector=_only(target.id),
                modification=set_power_toughness(power, toughness),
            )
            for target in targets
        ]

    return builder


def _becomes_creature_with_mana_value_pt_builder(extra_type: Type) -> EffectBuilder:
    """ "Until your next turn, up to one target ... becomes a[n] <type> creature
    with power and toughness each equal to its mana value." (Karn, the Great
    Creator's +1).

    Two layers from one ability (CR 613.6): `extra_type` plus creature in
    layer 4 (CR 613.1d - CR 205.1a's "new card type(s) replaces any existing
    card types" happens to keep the target's old type here only because the
    ability names it explicitly, "artifact creature", not because this is an
    "in addition to" grant), and the mana-value P/T in sublayer 7b
    (CR 613.4b). The P/T half reuses `set_power_toughness_to_mana_value`,
    which reads `chars.mana_value` fresh every time the board is computed
    (CR 613.5) rather than a number fixed once at resolution - the same
    choice Opalescence's identical clause already makes, and the conservative
    one: a card whose own mana value can change (double-faced, X spells
    already on the battlefield notwithstanding) stays continuously correct
    rather than freezing a snapshot CR 613.5 says should not exist.

    `until_next_turn_of` is `source.controller` - Karn's controller, the "your"
    of "until your next turn" (CR 606.4's activation is always the loyalty
    ability's controller's).
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        effects: list[ContinuousEffect] = []
        for target in targets:
            effects.append(
                ContinuousEffect(
                    description=f"{source.name}: {target.name} becomes a "
                    f"{extra_type.value} creature",
                    layer=Layer.TYPE,
                    timestamp=timestamp,
                    duration=Duration.UNTIL_YOUR_NEXT_TURN,
                    until_next_turn_of=source.controller,
                    selector=_only(target.id),
                    modification=add_type(Type.CREATURE),
                )
            )
            effects.append(
                ContinuousEffect(
                    description=f"{source.name}: {target.name} has power and "
                    "toughness each equal to its mana value",
                    layer=Layer.POWER_TOUGHNESS,
                    sublayer=Sublayer.SET,
                    timestamp=timestamp,
                    duration=Duration.UNTIL_YOUR_NEXT_TURN,
                    until_next_turn_of=source.controller,
                    selector=_only(target.id),
                    modification=set_power_toughness_to_mana_value,
                )
            )
        return effects

    return builder


#: The keyword grant shapes only ever grant one bare keyword - `machines/
#: combat.py`'s own vocabulary, since that is what a grant needs to be able to
#: do anything (`combat.has_keyword` is the only reader). Aerial Maneuver's
#: "gains flying **and first strike**" is exactly why this is a whitelist and
#: not `[a-z ]+` on its own: without it, "flying and first strike" would be
#: accepted and granted as one bogus ability instead of two real ones. A
#: keyword outside this set - or a conjunction the pool does not use single
#: keywords with - fails the match and falls to `looks_like_unparsed_layer_effect`
#: instead of silently granting the wrong thing.
_KNOWN_KEYWORDS = frozenset(keyword.value for keyword in Keyword)


def _split_and_validate_keywords(raw: str) -> list[str] | None:
    """ "double strike and lifelink" / "menace, deathtouch and first strike" ->
    each keyword, capitalised - or `None` if any of them is not on
    `_KNOWN_KEYWORDS`'s whitelist, the same fail-closed rule the single-keyword
    shapes already enforce.
    """
    parts = [part.strip() for part in re.split(r",\s*|\s+and\s+", raw) if part.strip()]
    if not parts or any(part.lower() not in _KNOWN_KEYWORDS for part in parts):
        return None
    return [part.capitalize() for part in parts]


def _parse_layer_sentence(sentence: str) -> EffectBuilder | None:
    """One of the generalised shapes below, or `None` if this is not one of them.

    `sentence` is normalised for a duration-first opening
    (`_normalize_duration_first`) before any shape is tried, so "Until end of
    turn, target creature gets +4/+4" reads the same as "Target creature gets
    +4/+4 until end of turn."
    """
    sentence = _normalize_duration_first(sentence)
    if match := _PUMP_RE.fullmatch(sentence):
        power, toughness = int(match.group("power")), int(match.group("toughness"))
        keyword = match.group("keyword")
        if keyword is not None:
            if keyword.strip().lower() not in _KNOWN_KEYWORDS:
                return None
            keyword = keyword.strip().capitalize()
        return _pump_and_keyword_builder(power, toughness, keyword)
    if match := _KEYWORD_GRANT_RE.fullmatch(sentence):
        keyword = match.group("keyword").strip()
        if keyword.lower() not in _KNOWN_KEYWORDS:
            return None
        return _keyword_grant_builder(keyword.capitalize())
    if match := _ANTHEM_RE.fullmatch(sentence):
        return _anthem_builder(
            int(match.group("power")),
            int(match.group("toughness")),
            other=match.group("other") is not None,
            whose=match.group("whose").lower(),
            line=sentence,
        )
    if match := _INDEFINITE_KEYWORD_GRANT_RE.fullmatch(sentence):
        keywords = _split_and_validate_keywords(match.group("keywords"))
        if keywords is None:
            return None
        return _indefinite_keyword_grant_builder(
            keywords,
            other=match.group("other") is not None,
            whose=match.group("whose").lower(),
            line=sentence,
        )
    if match := _BASE_PT_SET_RE.fullmatch(sentence):
        return _base_pt_set_builder(int(match.group("power")), int(match.group("toughness")))
    if match := _BECOMES_CREATURE_WITH_MANA_VALUE_PT_RE.fullmatch(sentence):
        extra_type = _OTHER_PERMANENT_TYPE_WORDS.get(match.group("extra_type").lower())
        if extra_type is None:
            return None
        return _becomes_creature_with_mana_value_pt_builder(extra_type)
    return None


def parsed_layer_effects(oracle_text: str | None) -> EffectBuilder | None:
    """Every sentence of `oracle_text` that is one of the generalised shapes
    above, combined into one builder - or `None` if none of them matched at all.

    Sentences outside this wave's territory (a triggered ability, an
    intervening *if*, a bare keyword line, a token-creation instruction) are
    silently skipped rather than failing the whole card: they belong to a
    different registry or mechanism, not to a continuous effect at all.
    """
    builders = [
        builder
        for sentence in _effect_sentences(oracle_text)
        if (builder := _parse_layer_sentence(sentence)) is not None
    ]
    if not builders:
        return None

    def combined(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        result: list[ContinuousEffect] = []
        for builder in builders:
            result.extend(builder(source, timestamp, targets, context))
        return result

    return combined


def looks_like_unparsed_layer_effect(oracle_text: str | None) -> bool:
    """True if some sentence of `oracle_text` reads like one of the
    pump/keyword-grant/anthem shapes above but did not fully match - the
    fail-closed signal a caller records as a `LayerNotice` instead of
    silently producing nothing, mirroring `looks_like_unparsed_cost_modifier`
    (`machines/cost.py`) and the effect `TargetingNotice`/`InterveningIfNotice`
    (`machines/triggers.py`) already record for targets and intervening *if*.
    """
    return any(
        _LOOKS_LIKE_LAYER_EFFECT_RE.match(_normalize_duration_first(sentence))
        and _parse_layer_sentence(sentence) is None
        for sentence in _effect_sentences(oracle_text)
    )


def is_resolution_layer_effect_text(text: str | None) -> bool:
    """True if some sentence of `text` is - or looks like a failed attempt at -
    a one-shot **resolution** effect (CR 611.2) this wave reads: a pump, a
    keyword grant, a base P/T set, or "becomes a[n] <type> creature ...".
    The anthem shape is deliberately excluded (CR 611.3: "creatures you
    control get +N/+N" is always a permanent's own static ability), even
    when it fully parses.

    `machines/effects.py` uses this - not `parsed_layer_effects` or
    `looks_like_unparsed_layer_effect` directly - to decide whether an
    ability's or spell's own effect text should route to
    `create_continuous_effect`/`create_continuous_effect_of_ability` at all.
    Reusing either of those for the routing decision would let a plain
    "Creatures you control get +N/+N." (Glorious Anthem, a permanent spell
    with no resolution effect at all) route there too, creating a *second*,
    permanent copy of the same anthem the battlefield sweep (`effects_for`,
    called for every permanent every time the board is computed, CR 613.5)
    already reapplies on its own - doubling the bonus. `parsed_layer_effects`
    itself is unchanged and still reads the anthem shape, because that sweep
    is exactly where it belongs.
    """
    for sentence in _effect_sentences(text):
        normalized = _normalize_duration_first(sentence)
        anthem_opening = _LOOKS_LIKE_ANTHEM_RE.match(normalized)
        has_duration = Duration.UNTIL_END_OF_TURN in normalized
        if anthem_opening and not has_duration:
            # CR 611.3's own static shape: "lasts for as long as the object
            # with that static ability remains on the battlefield", i.e.
            # never expires on its own - the one shape excluded on purpose.
            continue
        if anthem_opening and has_duration:
            # Same opening words, but an explicit duration ("Creatures you
            # control get +1/+0 until end of turn.", Violent Outburst) is
            # never CR 611.3's forever-lasting anthem - it can only be CR
            # 611.2's one-shot group pump, which `_ANTHEM_RE` does not parse
            # (it has no duration group at all) and nothing else here reads
            # either, so this counts as a failed-parse attempt rather than
            # routing through the anthem's durationless `continue` above.
            return True
        if _parse_layer_sentence(sentence) is not None:
            return True
        if _LOOKS_LIKE_RESOLUTION_LAYER_EFFECT_RE.match(normalized):
            return True
    return False


class LayerNotice(BaseModel):
    """One permanent or spell whose static/pump text could not be read into a
    continuous effect (W5).

    The same "unreadable is not the same as no effect" record `TargetingNotice`
    and `CostModifierNotice` already keep: a pump or anthem that silently fails
    to apply is indistinguishable from a card with no effect at all, which is
    exactly how Trinisphere sat on a battlefield unnoticed for several
    playtest turns (see `CostModifierNotice`). `effects_for` appends one of
    these instead of skipping the card quietly.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    """The card's own oracle text, for whoever reads the notice later."""


# --------------------------------------------------------------------------
# The registry: real cards, and the effects they generate
# --------------------------------------------------------------------------


class LayerContext(BaseModel):
    """What an effect needs to know that is not standing on the battlefield.

    Almost every continuous effect reads only the board, which is what
    `Selector` and `Modification` are handed. A few read somewhere else:
    Tarmogoyf's characteristic-defining ability counts card types "among cards
    in all graveyards", and the layer engine never sees a graveyard.

    Anything read from here is read when the effects are *built*, not when they
    are applied, so a caller rebuilds them whenever it recomputes the board -
    which is what CR 613.5 asks for anyway ("continually and automatically
    performed by the game").
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


#: A card name to the continuous effects a copy of it generates. `source` is the
#: permanent (or the resolving spell); `timestamp` is its place in CR 613.7
#: order; `targets` is for the effects that have one; `context` is for the few
#: that read outside the battlefield.
EffectBuilder = Callable[
    [CardState, int, Sequence[CardState], LayerContext], list[ContinuousEffect]
]


def _humility(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "All creatures lose all abilities and have base power and toughness 1/1."

    One ability, two layers: the removal is layer 6 (CR 613.1f) and the base P/T
    is 7b (CR 613.4b), because "base power and toughness" sets a value
    (CR 208.4a). Both parts share `source_ability`, so once either has started
    applying, removing Humility's own ability cannot stop the other (CR 613.6).
    """
    text = "All creatures lose all abilities and have base power and toughness 1/1."
    return [
        ContinuousEffect(
            description="Humility: creatures lose all abilities",
            layer=Layer.ABILITY,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=text,
            selector=every_creature,
            modification=lose_all_abilities,
        ),
        ContinuousEffect(
            description="Humility: creatures have base P/T 1/1",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.SET,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=text,
            selector=every_creature,
            modification=set_power_toughness(1, 1),
        ),
    ]


def _opalescence(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "Each other non-Aura enchantment is a creature ... base P/T equal to its mana value."

    Layer 4 for the type (CR 613.1d) and 7b for the P/T (CR 613.4b). Note that
    Opalescence excludes itself, so Humility - an enchantment - becomes a
    creature and falls under its own ability, while Opalescence does not.
    """
    text = (
        "Each other non-Aura enchantment is a creature in addition to its other types "
        "and has base power and base toughness each equal to its mana value."
    )
    selector = other_non_aura_enchantments(source.id)
    return [
        ContinuousEffect(
            description="Opalescence: other non-Aura enchantments are creatures",
            layer=Layer.TYPE,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=text,
            selector=selector,
            modification=add_type(Type.CREATURE),
        ),
        ContinuousEffect(
            description="Opalescence: base P/T equal to mana value",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.SET,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=text,
            selector=selector,
            modification=set_power_toughness_to_mana_value,
        ),
    ]


def _blood_moon(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "Nonbasic lands are Mountains."

    Layer 4 (CR 613.1d), and by CR 305.7 setting a land's subtype to a basic
    land type strips its old land types and every ability from its rules text.
    That is why this one line switches off half the lands in Modern.
    """
    return [
        ContinuousEffect(
            description="Blood Moon: nonbasic lands are Mountains",
            layer=Layer.TYPE,
            timestamp=timestamp,
            source_id=source.id,
            source_ability="Nonbasic lands are Mountains.",
            selector=nonbasic_lands,
            modification=set_basic_land_type("Mountain", "{T}: Add {R}."),
        )
    ]


def _urborg(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "Each land is a Swamp in addition to its other land types." (CR 613.1d)"""
    return [
        ContinuousEffect(
            description="Urborg: each land is a Swamp",
            layer=Layer.TYPE,
            timestamp=timestamp,
            source_id=source.id,
            source_ability="Each land is a Swamp in addition to its other land types.",
            selector=every_land,
            modification=add_subtype("Swamp", "{T}: Add {B}."),
        )
    ]


#: "Creatures you control get +1/+1." (Glorious Anthem) and "Target creature
#: gets +3/+3 until end of turn." (Giant Growth) are no longer hand-written
#: here - both are `parsed_layer_effects`'s generalised shapes now. See
#: `test_layer_effects_registry_is_minimal.py`.


def _twisted_image(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "Switch target creature's power and toughness until end of turn." - 7d."""
    return [
        ContinuousEffect(
            description=f"Twisted Image: switch {target.name}'s power and toughness",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.SWITCH,
            timestamp=timestamp,
            duration=Duration.UNTIL_END_OF_TURN,
            selector=_only(target.id),
            modification=switch_power_toughness,
        )
        for target in targets
    ]


def _dryad_of_the_ilysian_grove(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "Lands you control are every basic land type in addition to their other types."

    Layer 4 (CR 613.1d), and "in addition to" means nothing is lost - this is
    not CR 305.7's "sets a land's subtype", so a fetchland keeps its own text.
    Each basic type gained brings its intrinsic mana ability with it (CR 305.6),
    which is the reason a Dryad turns every land into a five-colour source.

    The card's other line, "You may play an additional land on each of your
    turns", is a static ability that modifies the rules rather than an object's
    characteristics, so it generates no continuous effect in any of the seven
    layers and is not modelled here.
    """
    text = "Lands you control are every basic land type in addition to their other types."
    return [
        ContinuousEffect(
            description="Dryad of the Ilysian Grove: your lands are every basic land type",
            layer=Layer.TYPE,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=text,
            selector=lands_controlled_by(source.controller),
            modification=add_basic_land_types,
        )
    ]


def _dress_down(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "Creatures lose all abilities." - layer 6 (CR 613.1f).

    Dress Down is an Enchantment and not a creature, so unlike Humility it does
    not strip its own ability. Its other three lines - flash, the enters-trigger
    and the end step sacrifice - are not continuous effects and are not modelled
    here.
    """
    text = "Creatures lose all abilities."
    return [
        ContinuousEffect(
            description="Dress Down: creatures lose all abilities",
            layer=Layer.ABILITY,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=text,
            selector=every_creature,
            modification=lose_all_abilities,
        )
    ]


#: "Other creatures you control get +2/+2. Creatures your opponents control
#: get -2/-2." (Elesh Norn, Grand Cenobite) is no longer hand-written here -
#: both sentences are `parsed_layer_effects`'s anthem shape. Her own
#: "Vigilance" line is a printed keyword, not a continuous effect, so it needs
#: no entry at all.


def _relentless_rats(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "This creature gets +1/+1 for each other creature named Relentless Rats."

    Sublayer 7c (CR 613.4c), not 7a: it *modifies* power and toughness rather
    than defining them, and the printed 2/2 is a real printed value rather than
    a `*` (CR 208.2). Every Rat counts every other Rat, so n of them are each
    an (n+1)/(n+1).
    """
    text = (
        "This creature gets +1/+1 for each other creature on the battlefield named Relentless Rats."
    )
    return [
        ContinuousEffect(
            description="Relentless Rats: +1/+1 for each other Relentless Rats",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.MODIFY,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=text,
            selector=_only(source.id),
            modification=modify_power_toughness_per(
                count_other_creatures_named("Relentless Rats"), 1, 1
            ),
        )
    ]


def _tarmogoyf(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "Tarmogoyf's power is equal to the number of card types among cards in all
    graveyards and its toughness is equal to that number plus 1."

    A characteristic-defining ability (CR 604.3, CR 604.3a) - it defines the
    card's own power and toughness, is printed on the card it affects, and is
    not conditional - so it applies in sublayer 7a (CR 613.4a) ahead of every
    other power/toughness effect, whatever the timestamps say.

    The number is counted off `context.graveyards` when the effect is built,
    because the layer engine only ever sees the battlefield. Card types are the
    CR 300.1 list, so a creature land in a graveyard counts twice over.

    Being an ability, it can be removed in layer 6 (CR 613.1f) - by Dress Down
    or Humility - and then there is no value for either half, which CR 208.5
    reads as 0.
    """
    text = (
        "Tarmogoyf's power is equal to the number of card types among cards in "
        "all graveyards and its toughness is equal to that number plus 1."
    )
    types = count_card_types(context.graveyards)
    return [
        ContinuousEffect(
            description=f"Tarmogoyf: {types}/{types + 1} from card types in all graveyards",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.CHARACTERISTIC_DEFINING,
            characteristic_defining=True,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=text,
            selector=_only(source.id),
            modification=define_power_toughness(lambda chars, board: types, 0, 1),
        )
    ]


def _boneyard_wurm(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "Boneyard Wurm's power and toughness are each equal to the number of
    creature cards in your graveyard."

    A characteristic-defining ability (CR 604.3, CR 604.3a) in sublayer 7a
    (CR 613.4a), like Tarmogoyf's - but it counts *creature cards*, not card
    types (CR 300.1), and only **your** graveyard, not every graveyard, so a
    stack of Bears in the opponent's bin does not grow it. `context.graveyard_of`
    looks up the caster's own graveyard by controller, because unlike Tarmogoyf
    (whose count is the same for everyone) this one is a different number for
    every player it could be printed under.
    """
    text = (
        "Boneyard Wurm's power and toughness are each equal to the number of "
        "creature cards in your graveyard."
    )
    creatures = sum(1 for card in context.graveyard_of(source.controller) if card.card.is_creature)
    return [
        ContinuousEffect(
            description=(
                f"Boneyard Wurm: {creatures}/{creatures} from creature cards in your graveyard"
            ),
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.CHARACTERISTIC_DEFINING,
            characteristic_defining=True,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=text,
            selector=_only(source.id),
            modification=define_power_toughness(lambda chars, board: creatures, 0, 0),
        )
    ]


def _nighthawk_scavenger(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "Nighthawk Scavenger's power is equal to 1 plus the number of card
    types among cards in your opponents' graveyards."

    A third graveyard-reading shape alongside Tarmogoyf's (every graveyard) and
    Boneyard Wurm's (your own): this one counts every graveyard *except* your
    own, which `context.opponents_graveyard_of` answers as the set difference
    of the other two. Its toughness box is a plain `3` (CR 208.1) - only power
    is a CDA - so this is `define_power`, not `define_power_toughness`, and the
    printed Flying/deathtouch/lifelink lines need no entry at all (CR 604.3:
    only the P/T sentence is the characteristic-defining ability).
    """
    text = (
        "Nighthawk Scavenger's power is equal to 1 plus the number of card "
        "types among cards in your opponents' graveyards."
    )
    types = count_card_types(context.opponents_graveyard_of(source.controller))
    return [
        ContinuousEffect(
            description=f"Nighthawk Scavenger: power 1+{types} from opponents' graveyards",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.CHARACTERISTIC_DEFINING,
            characteristic_defining=True,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=text,
            selector=_only(source.id),
            modification=define_power(lambda chars, board: types, 1),
        )
    ]


def _allosaurus_rider(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "Allosaurus Rider's power and toughness are each equal to 1 plus the number
    of lands you control."

    The second CDA in the registry, and the one that reads the *board* rather
    than a zone outside it: the lands are counted in sublayer 7a (CR 613.4a)
    against the board as layers 1-6 left it, so a land that stopped being a land
    in layer 4 (CR 613.1d) is not counted.

    Its alternative cost line is a cost, not a continuous effect, and lives in
    `machines/cost.py`'s world rather than this one.
    """
    text = (
        "Allosaurus Rider's power and toughness are each equal to 1 plus the "
        "number of lands you control."
    )
    return [
        ContinuousEffect(
            description="Allosaurus Rider: 1 plus the lands you control",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.CHARACTERISTIC_DEFINING,
            characteristic_defining=True,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=text,
            selector=_only(source.id),
            modification=define_power_toughness(count_lands_controlled_by(source.controller), 1, 1),
        )
    ]


#: "Target creature gets -5/-5 until end of turn." (Dismember) is no longer
#: hand-written here - `parsed_layer_effects`'s pump shape reads it, its
#: Phyrexian-mana reminder line stripped like any other reminder text.
#:
#: "{1}{G}: This creature gets +2/+2 until end of turn." (Basking Rootwalla)
#: likewise: the activation cost is stripped ahead of the sentence, and
#: `static_effects`'s untargeted call still produces nothing, exactly as this
#: hand-written version used to - the shape only ever fires with
#: `targets=[source]`, from `create_continuous_effect_of_ability`.


def _tishanas_tidebinder(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "That permanent loses all abilities for as long as this creature remains
    on the battlefield."

    Layer 6 (CR 613.1f), created by a resolving triggered ability (CR 611.2) and
    timestamped then (CR 613.7b). The duration is the "for as long as" form of
    CR 611.2b, so the effect carries a condition rather than an expiry: it holds
    while the Tidebinder is on the battlefield and stops the moment it is not.

    CR 611.2b's corner case is handled by `ContinuousEffects.create` rather than
    here - "If the 'for as long as' duration never starts, the effect does
    nothing", so a Tidebinder that is already gone when its trigger resolves
    creates nothing at all.

    `source` is the Tidebinder; `targets` is the permanent whose ability was
    countered. There is no `source_ability`, because this is not a static
    ability of the Tidebinder and CR 613.6 has nothing to switch off - the
    duration does that job instead.
    """
    return [
        ContinuousEffect(
            description=f"Tishana's Tidebinder: {target.name} loses all abilities",
            layer=Layer.ABILITY,
            timestamp=timestamp,
            duration=Duration.FOR_AS_LONG_AS,
            condition=_remains_on_the_battlefield(source),
            selector=_only(target.id),
            modification=lose_all_abilities,
        )
        for target in targets
    ]


#: "Target creature gets +2/+2 until end of turn." (Mutagenic Growth) and
#: "Target creature gains double strike until end of turn." (Assault Strobe)
#: are no longer hand-written here - the pump and keyword-grant shapes of
#: `parsed_layer_effects` read both, trailing reminder text stripped as usual.
#:
#: Monstrous Rage's first sentence, "Target creature gets +2/+0 until end of
#: turn.", is the same pump shape; its second sentence, "Create a Monster Role
#: token attached to it.", is not a continuous effect at all and is correctly
#: left to `machines/effects.py`'s `monstrous_rage` (token creation, CR 111.10k,
#: CR 701.7a) - `parsed_layer_effects` reads sentence by sentence and simply
#: has nothing to say about the second one, exactly like Dryad of the Ilysian
#: Grove's land-drop line above.


def _monster_role(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """The Monster Role token's static ability (CR 111.10k, CR 303.7).

    CR 111.10k, read in full out of the 2026-08-19 rules: "A Monster Role token
    is a colorless Aura Role enchantment token named Monster with enchant
    creature and 'Enchanted creature gets +1/+1 and has trample.'" CR 303.7 is
    what makes Role a subtype of Aura at all: "Some Aura enchantments also have
    the subtype 'Role.'"

    Keyed on the token's *name*, which is how a token reaches this registry: the
    token's characteristics are a `Card` synthesised from what the creating
    effect stated (CR 111.3), so `LAYER_EFFECTS.get(source.name)` finds it the
    same way it finds Humility.

    An Aura's grant is a static ability, so it is `INDEFINITE` (CR 611.3) and
    switches off by the Role leaving rather than by a duration expiring, and it
    applies to whatever the Role is attached to right now (CR 701.3a,
    `CardState.attached_to`). Nothing to apply if it is attached to nothing -
    CR 704.5m's state-based action would already be putting it into a graveyard.

    Two effects from one ability across two layers (CR 613.6): the +1/+1 in
    sublayer 7c (CR 613.4c) and trample (CR 702.19a) in layer 6 (CR 613.1f,
    CR 113.10). They share a `source_ability`, so CR 613.6 treats them as one
    effect for the purpose of being switched off.

    **The trample grant is recorded and nothing reads it**: `machines/combat.
    has_keyword` answers off the printed `Card.keywords` rather than off the
    computed board - the same disconnect Assault Strobe's granted double
    strike has (see `docs/engine-coverage.md`).
    """
    if source.attached_to is None:
        return []
    ability = "Enchanted creature gets +1/+1 and has trample."
    enchanted = _only(source.attached_to)
    return [
        ContinuousEffect(
            description=f"{source.name} Role: enchanted creature gets +1/+1",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.MODIFY,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=ability,
            selector=enchanted,
            modification=modify_power_toughness(1, 1),
        ),
        ContinuousEffect(
            description=f"{source.name} Role: enchanted creature has trample",
            layer=Layer.ABILITY,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=ability,
            selector=enchanted,
            modification=grant_ability("Trample"),
        ),
    ]


def _violent_urge(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "Target creature gets +1/+0 and gains first strike until end of turn.
    *Delirium* - If there are four or more card types among cards in your
    graveyard, that creature gains double strike until end of turn."

    Three effects from one resolution, in two layers - CR 613.6: "If an effect
    should be applied in different layers and/or sublayers, the parts of the
    effect each apply in their appropriate ones." The +1/+0 is sublayer 7c
    (CR 613.4c); first strike (CR 702.7a) and double strike (CR 702.4) are
    ability grants in layer 6 (CR 613.1f, CR 113.10).

    *Delirium* is an ability word with no rules meaning of its own (CR 207.2c),
    so the condition is only the sentence printed after it: four or more card
    types (CR 205.2a, CR 300.1) among cards in **your** graveyard, which is
    `context.your_graveyard` and deliberately not `context.graveyards`.

    The condition is checked once, here, as the spell resolves. It is not a
    "for as long as" duration (CR 611.2b): the creature keeps double strike for
    the turn even if the graveyard later loses a card type, because CR 611.2c
    fixes what a resolving spell's effect does at the moment it is created.

    Both grants share the caveat Assault Strobe's granted double strike has:
    combat does not read granted keywords, so they are recorded and inert.

    **Why this row still exists.** The first sentence alone - "Target creature
    gets +1/+0 and gains first strike until end of turn." - is exactly
    `parsed_layer_effects`'s pump-and-keyword shape, so this reuses
    `_pump_and_keyword_builder` rather than reimplementing it (one
    implementation per rule). Only the *Delirium* clause is genuinely
    one-of-a-kind: no generalised shape this wave reads conditions a grant on
    card types in a graveyard, so that third effect is still hand-built.
    `test_layer_effects_registry_is_minimal.py` excludes this card by name for
    exactly this reason - the row is not dead weight, it does one thing the
    parser cannot.
    """
    effects = _pump_and_keyword_builder(1, 0, "First strike")(source, timestamp, targets, context)
    if count_card_types(context.your_graveyard) >= 4:
        effects.extend(
            ContinuousEffect(
                description=f"Violent Urge: {target.name} gains double strike (delirium)",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                duration=Duration.UNTIL_END_OF_TURN,
                selector=_only(target.id),
                modification=grant_ability("Double strike"),
            )
            for target in targets
        )
    return effects


def _remains_on_the_battlefield(permanent: CardState) -> Condition:
    """ "For as long as this creature remains on the battlefield" (CR 611.2b).

    The zone is asked each time the board is computed, so the effect ends the
    moment the permanent leaves - and CR 400.7 means a permanent that leaves and
    comes back is a new object, so the condition stays false for the returning
    one.
    """

    def condition() -> bool:
        return permanent.zone is Zone.BATTLEFIELD

    return condition


#: Continuous effects by card name, for the shapes `parsed_layer_effects`
#: cannot read (or, like Violent Urge, reads only part of). `effects_for`
#: checks here first and falls back to the parser on a miss, so a card with
#: neither generates no effect, which is right for a vanilla creature and
#: silently wrong for anything with text `parsed_layer_effects` cannot read
#: either - see `LayerNotice`.
#:
#: Glorious Anthem, Giant Growth, Elesh Norn, Dismember, Basking Rootwalla,
#: Mutagenic Growth, Assault Strobe, and Monstrous Rage's pump are not here any
#: more - each was exactly one of `parsed_layer_effects`'s four generalised
#: shapes, read off the card's own oracle text instead. See
#: `test_layer_effects_registry_is_minimal.py`.
LAYER_EFFECTS: dict[str, EffectBuilder] = {
    "Humility": _humility,
    "Opalescence": _opalescence,
    "Blood Moon": _blood_moon,
    "Urborg, Tomb of Yawgmoth": _urborg,
    "Twisted Image": _twisted_image,
    "Dryad of the Ilysian Grove": _dryad_of_the_ilysian_grove,
    "Dress Down": _dress_down,
    "Relentless Rats": _relentless_rats,
    "Tarmogoyf": _tarmogoyf,
    "Boneyard Wurm": _boneyard_wurm,
    "Nighthawk Scavenger": _nighthawk_scavenger,
    "Allosaurus Rider": _allosaurus_rider,
    "Tishana's Tidebinder": _tishanas_tidebinder,
    # The pump and first strike are the generalised shapes; the *Delirium*
    # clause conditions a third grant on card types in the controller's
    # graveyard (CR 205.2a, CR 300.1), which no generalised shape this wave
    # reads accounts for - a one-of-a-kind conditional, not a fourth pattern.
    "Violent Urge": _violent_urge,
    # "Monstrous Rage" has no row: its pump is the generalised shape, read off
    # its own oracle text by the parser fallback; its token creation is
    # `machines/effects.py`'s job (CR 111.10k, CR 701.7a).
    # A *token*, not a card: the Monster Role of CR 111.10k. Its characteristics
    # are the ones the rule states (CR 111.3), and its name is the key here.
    # "Enchanted creature" is a third subject `parsed_layer_effects` does not
    # read (Hyena Umbra's Aura shares it, and is left for a later wave too) -
    # it needs the board's `attached_to` link rather than a resolved target.
    "Monster": _monster_role,
}


def effects_for(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState] = (),
    context: LayerContext | None = None,
    notices: list[LayerNotice] | None = None,
) -> list[ContinuousEffect]:
    """The continuous effects one card generates, or none if it is not registered
    and its own oracle text is not one of `parsed_layer_effects`'s shapes either.

    `context` carries what a card reads outside the battlefield - the graveyards
    Tarmogoyf counts. Leave it out for every other card.

    `LAYER_EFFECTS` is tried first, so an explicit row always wins over the
    parser. On a miss, `notices` - when a caller passes one, which
    `ContinuousEffects` always does - collects a `LayerNotice` for oracle text
    that reads like a pump/keyword/anthem shape but did not fully parse,
    rather than the card silently doing nothing.
    """
    builder = LAYER_EFFECTS.get(source.name)
    text = source.card.oracle_text
    if builder is None:
        builder = parsed_layer_effects(text)
    if builder is None:
        if (
            notices is not None
            and looks_like_unparsed_layer_effect(text)
            # The board is recomputed continually (CR 613.5), so the same
            # unreadable permanent is asked about over and over - record it
            # once, not once per computation.
            and not any(notice.source_id == source.id for notice in notices)
        ):
            notices.append(
                LayerNotice(source_id=source.id, source_name=source.name, text=text or "")
            )
        return []
    return builder(source, timestamp, targets, context or LayerContext())


def static_effects(
    permanents: Sequence[CardState],
    context: LayerContext | None = None,
    notices: list[LayerNotice] | None = None,
) -> list[ContinuousEffect]:
    """Every registered static effect on the battlefield, timestamped by order.

    CR 613.7a: a continuous effect from a static ability has the timestamp of
    the permanent it is on, so passing the permanents in the order they entered
    the battlefield gives the right timestamp order.
    """
    shared = context or LayerContext()
    effects: list[ContinuousEffect] = []
    for timestamp, permanent in enumerate(permanents, start=1):
        effects.extend(effects_for(permanent, timestamp, (), shared, notices))
    return effects


# --------------------------------------------------------------------------
# Rule-modifying grants to a player (CR 611.3d)
# --------------------------------------------------------------------------

#: CR 611.3d: "Continuous effects from static abilities may allow a player to
#: play a land or cast a permanent spell..." A grant like Azusa's is not a
#: change to any object's characteristics, so it belongs to none of the seven
#: layers - it modifies the game's rules for a player instead. Static ability
#: text is not parsed (the same trade `LAYER_EFFECTS` makes), so these grants
#: are a per-card registry keyed by name.
#:
#: Each entry is how many ADDITIONAL lands a turn the card lets its controller
#: play, on each of that player's turns. The printed "on each of your turns"
#: needs no stored condition: `Game.can_play_land` refuses any player who is
#: not the active player (CR 305.3 - "A player can't play a land, for any
#: reason, if it isn't their turn"), so a grant is only ever read for a player
#: on their own turn. The grant also reaches only its controller, because
#: `Game.permanents_controlled_by` is what feeds `additional_land_plays`.
ADDITIONAL_LAND_PLAYS: dict[str, int] = {
    # "You may play two additional lands on each of your turns."
    "Azusa, Lost but Seeking": 2,
}


def additional_land_plays(permanents: Sequence[CardState]) -> int:
    """The additional land plays a set of permanents grants (CR 305.2, 611.3d).

    Summed over the permanents passed in; the caller passes only the ones the
    player controls (`Game.permanents_controlled_by`), because a static ability
    grants its controller and nobody else. CR 611.3b applies the effect "at all
    times that the permanent generating it is on the battlefield", which reading
    the board at every question gives for free - Azusa leaving mid-turn drops
    the grant the moment she is gone.
    """
    total = 0
    for permanent in permanents:
        grant = ADDITIONAL_LAND_PLAYS.get(permanent.name)
        if grant is not None:
            total += grant
    return total


# --------------------------------------------------------------------------
# Effects with a duration, and where a game keeps them (CR 611.2)
# --------------------------------------------------------------------------


class ContinuousEffects(BaseModel):
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

    model_config = ConfigDict(arbitrary_types_allowed=True)

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

    def tick(self) -> int:
        """The next timestamp (CR 613.7)."""
        self.clock += 1
        return self.clock

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
        condition becomes true again.

        Returns the effects that were kept.
        """
        built = effects_for(source, self.tick(), targets, context, self.layer_notices)
        kept = [effect for effect in built if effect.holds]
        self.effects.extend(kept)
        return kept

    def add(self, effect: ContinuousEffect) -> ContinuousEffect:
        """Keep one hand-built effect, for a caller that is not going through
        the registry. Subject to CR 611.2b just the same."""
        if effect.holds:
            self.effects.append(effect)
        return effect

    @property
    def active(self) -> list[ContinuousEffect]:
        """The stored effects whose duration is still running (CR 611.2b)."""
        return [effect for effect in self.effects if effect.holds]

    def end_the_turn(self) -> list[ContinuousEffect]:
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
            if effect.duration is Duration.UNTIL_END_OF_TURN or not effect.holds
        ]
        gone = {effect.id for effect in ended}
        self.effects = [effect for effect in self.effects if effect.id not in gone]
        return ended

    def end_for_next_turn(self, username: str) -> list[ContinuousEffect]:
        """End every "until [username]'s next turn" effect as that turn begins.

        CR 800.4m treats "until that player's next turn" as ending when that
        turn "would have begun", so this is called from `Game.begin_turn_for`
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
        self.effects = [effect for effect in self.effects if effect.id not in gone]
        return ended

    def all_effects(
        self, permanents: Sequence[CardState], context: LayerContext | None = None
    ) -> list[ContinuousEffect]:
        """Static-ability effects and stored durational ones, in one list.

        Both are handed to `compute_board` together, because CR 613 applies
        every continuous effect in play in one pass and CR 613.7 orders them
        against each other by timestamp regardless of where they came from.
        """
        self.note(permanents)
        shared = context or LayerContext()
        effects: list[ContinuousEffect] = []
        for permanent in permanents:
            effects.extend(
                effects_for(permanent, self.entered[permanent.id], (), shared, self.layer_notices)
            )
        return effects + self.active

    def board(
        self, permanents: Sequence[CardState], context: LayerContext | None = None
    ) -> ComputedBoard:
        """What the board is, with everything applied (CR 613.5)."""
        return compute_board(permanents, self.all_effects(permanents, context))
