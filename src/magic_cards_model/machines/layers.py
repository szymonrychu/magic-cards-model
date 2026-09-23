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

Layer 1 has sublayers of its own (CR 613.2):

    613.2a  1a: copiable effects - copy effects (CR 707) and merge effects
    613.2b  1b: face-down spells and permanents, modified as CR 708.2 says

and CR 613.2c is what makes the pair matter: "After all rules and effects in
layer 1 have been applied, the object's characteristics are its copiable
values." A face-down 2/2 with an *earlier* timestamp than a copy effect still
applies after it, because CR 613.2 puts the sublayer ahead of the timestamp.

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
  in layer 7 the CDAs get their own sublayer instead. Layers 1 and 7 sort by
  sublayer first and only then by timestamp (CR 613.2, CR 613.4).
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

import functools
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from enum import IntEnum, StrEnum
from typing import TYPE_CHECKING, Annotated, ClassVar, Literal, NamedTuple, cast
from uuid import UUID

from pydantic import ConfigDict, Field, PrivateAttr, model_validator

from magic_cards_model.phrases import with_indefinite_article

from ..data.creature_types import creature_types
from ..data.subtypes import canonical_subtype, subtype_vocabulary
from ..ids import new_id
from ..models.card import Color, Layout, Supertype, Type, has_changeling, with_every_creature_type
from ..models.card_state import CardState, ChoiceKind, Counter
from ..models.zone import Zone
from ..numbers import COUNT, parse_count, where_x_pattern
from ..snapshot import EngineModel
from .abilities import layer_readable_sentences, self_normalized_effect_text
from .combat import (
    ASSIGNS_DAMAGE_AS_THOUGH_POSITIVE_TEXT,
    ASSIGNS_DAMAGE_AS_TOUGHNESS_TEXT,
    ATTACK_WITHOUT_DEFENDER_TEXT,
    KEYWORDS_OUTSIDE_COMBAT,
    Keyword,
)

if TYPE_CHECKING:
    from ..models.game import Game

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


class CopySublayer(IntEnum):
    """The sublayers of layer 1, in order (CR 613.2).

    CR 613.2a is 1a: "Copiable effects are applied. This includes copy effects
    (see rule 707, 'Copying Objects') and changes to an object's
    characteristics determined by merging an object with a permanent".
    CR 613.2b is 1b: "Face-down spells and permanents have their
    characteristics modified as defined in rule 708.2."

    A separate enum from `Sublayer` rather than more members on it: the two
    layers' sublayers are different sets that never mix, and one enum holding
    both would let a layer-7 effect be given a layer-1 sublayer and vice
    versa. `_sublayer_matches_layer` enforces the pairing.

    The values deliberately do not start at 1: `ContinuousEffect.sublayer`'s
    type is the untagged `Sublayer | CopySublayer | None`, and pydantic
    resolves an untagged union by trying each member in declared order and
    keeping the first one a bare integer validates against. `Sublayer.
    CHARACTERISTIC_DEFINING` is also `1`, declared first, so a `CopySublayer.
    COPIABLE` serialized to `1` silently decoded back as `Sublayer.
    CHARACTERISTIC_DEFINING` instead - the whole layer-1 copy effect a
    `BecomeACopy` produces would then sit in the wrong layer's sublayer set,
    caught by round-tripping a real "becomes a copy" card. Numbering these
    5 and 6 instead makes every raw value unique across both enums, which is
    all an untagged union needs to resolve unambiguously; nothing compares a
    `CopySublayer` against a `Sublayer` by numeric value; both stay compared
    only within their own layer's tuple in `_SUBLAYERS_BY_LAYER`.
    """

    COPIABLE = 5  # 1a
    FACE_DOWN = 6  # 1b


#: The two layers CR 613 splits into sublayers, each with its own ordered
#: sublayer enum: layer 1 by CR 613.2 (CR 613.2a then CR 613.2b) and layer 7
#: by CR 613.4 (7a through 7d). CR 613.2 and CR 613.4 word the ordering
#: identically - "apply effects in a series of sublayers in the order
#: described below. Within each sublayer, apply effects in timestamp order" -
#: so the sublayer decides first and CR 613.7's timestamp only breaks ties
#: *inside* one sublayer.
_SUBLAYERS_BY_LAYER: dict[Layer, tuple[Sublayer | CopySublayer, ...]] = {
    Layer.COPY: tuple(CopySublayer),
    Layer.POWER_TOUGHNESS: tuple(Sublayer),
}

#: The layers that have sublayers at all, for the validator and the loop.
_SUBLAYERED = tuple(_SUBLAYERS_BY_LAYER)


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
      ...". CR 611.2a is what makes this a real, distinct duration rather than
      a synonym for "until end of turn": a continuous effect "lasts as long as
      stated by the spell or ability creating it", and this one is stated as
      "your next turn", not "end of turn" - so the effect outlives the turn it
      was created in and the opponent's turn(s) after it, ending only when its
      own controller's next turn begins, plainly what the printed duration
      says. `Game.begin_turn_for` - already the hook CR 302.6 uses to clear
      summoning sickness at the start of a player's turn - calls
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


# `Condition` - whether a "for as long as" duration is still running
# (CR 611.2b) - is defined below, after `Characteristics`/`Board`, alongside
# `Selector`/`Modification`/`Count`: all four used to be plain callables and
# are now frozen pydantic models so `ContinuousEffect.model_dump(mode="json")`
# can serialize them.


# --------------------------------------------------------------------------
# Characteristics
# --------------------------------------------------------------------------


class Characteristics(EngineModel):
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
    #: Whether this object is a token. Not a characteristic either - CR 205
    #: lists none of it - but a `Selector` never sees the `CardState` it would
    #: otherwise have to ask, and a real printed shape filters on exactly this:
    #: Toph, the First Metalbender's "**Nontoken** artifacts you control are
    #: lands in addition to their other types". Carried alongside `counters`,
    #: which is here for the same reason.
    is_token: bool = False
    #: `CardState.zone_change_stamp` as of this computation. Not a
    #: characteristic (CR 400.7 identity, not one of CR 613's seven layers'
    #: business) - carried for the same reason `counters` and `is_token` are:
    #: so a `Selector` can ask "is this the same incarnation of the permanent
    #: the effect was built for" without holding a live `CardState` reference,
    #: which is what makes the effect (and the selector inside it) safe to
    #: serialize. `only_this_incarnation` is the reader.
    zone_change_stamp: UUID | None = None

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


# --------------------------------------------------------------------------
# Selectors, modifications, counts, and conditions: frozen pydantic models
# instead of the closures every one of these used to be.
# --------------------------------------------------------------------------
#
# `ContinuousEffect.selector`/`.modification`/`.condition`, and `Modification`'s
# own `count` argument, used to be plain Python closures. A closure cannot be
# serialized - `Game.model_dump(mode="json")` raises `PydanticSerializationError:
# Unable to serialize unknown type: <class 'function'>` the moment any of these
# is stored - so each is now a frozen, `kind`-discriminated pydantic model
# instead, with `__call__` (or, for `Condition`, `holds_in`) carrying the exact
# body the closure used to run, moved rather than rewritten. Every factory
# function below this point (`only_this_incarnation`, `grant_ability`,
# `modify_power_toughness`, ...) is now a thin constructor returning one of
# these models, so none of the ~76 call sites across the codebase, and neither
# consumer (`_project`, `_depends_on`/`_writes_differently`), had to change.
#
# The union membership is the reachable set read off this module's own factory
# list - every function that returns `Selector`/`Modification`/`Count`, plus
# the handful of builder-local closures inline in a builder's own body
# (`_become_a_copy_builder`'s `modification`; `_self_becomes_type_until_next_
# turn_builder`/`_target_animation_builder`/`_self_animation_builder`'s shared
# `become`; `_other_creatures_are_type_builder`'s inline `selector`) - not from
# what the test suite happens to exercise, which is a smaller set:
# `parsed_layer_effects` with `static_only=False` can build anthem- and
# animation-shaped effects the suite never runs.


class CountBase(EngineModel):
    """How many of something an effect counts (CR 613.5) - the `Count` union's
    common shape. Judged against one object and the board as it stands in
    whichever sublayer asks.
    """

    model_config = ConfigDict(frozen=True)

    def __call__(self, chars: Characteristics, board: Board) -> int:
        raise NotImplementedError


class FixedCount(CountBase):
    """A count already worked out once, at build time, and never recomputed.

    Tarmogoyf's, Boneyard Wurm's and Nighthawk Scavenger's own characteristic-
    defining abilities each count a graveyard the layer engine cannot see once
    the board is being computed - `context.graveyards`/`context.graveyard_of`/
    `context.opponents_graveyard_of` - so each reads its number once, when its
    row builds the effect. This is where that fixed number lives now, in place
    of the `lambda chars, board: types`-shaped closure that used to hold it.
    """

    kind: Literal["fixed"] = "fixed"
    value: int

    def __call__(self, chars: Characteristics, board: Board) -> int:
        return self.value


class CountOtherCreaturesNamed(CountBase):
    """How many *other* creatures on the board have this name.

    `controlled_by_source` is Seven Dwarves' own "you control" qualifier -
    Relentless Rats' "on the battlefield" leaves it `False` (every match
    anywhere counts). Read against `chars.controller` rather than a
    `username` baked in when the effect was built: CR 611.3a's "isn't
    'locked in'" applies to who controls the *source* too, so a source whose
    own control changes (a Threaten effect, an Act of Treason) is asked fresh
    every time the board is computed (CR 613.5), the same live-recompute
    trick every other `Count` in this module already relies on.
    """

    kind: Literal["other_creatures_named"] = "other_creatures_named"
    name: str
    controlled_by_source: bool = False

    def __call__(self, chars: Characteristics, board: Board) -> int:
        return sum(
            1
            for other in board.values()
            if other.card_id != chars.card_id
            and other.is_creature
            and other.name == self.name
            and (not self.controlled_by_source or other.controller == chars.controller)
        )


class CountLandsControlledBy(CountBase):
    kind: Literal["lands_controlled_by"] = "lands_controlled_by"
    username: str | None = None

    def __call__(self, chars: Characteristics, board: Board) -> int:
        return sum(
            1 for other in board.values() if other.is_land and other.controller == self.username
        )


class CountPermanentsControlledBy(CountBase):
    """How many permanents of `card_type` a player controls (CR 205.2a)."""

    kind: Literal["permanents_controlled_by"] = "permanents_controlled_by"
    username: str | None = None
    card_type: Type

    def __call__(self, chars: Characteristics, board: Board) -> int:
        return sum(
            1
            for other in board.values()
            if self.card_type in other.types and other.controller == self.username
        )


class CountCreaturesWithSubtypesControlledBy(CountBase):
    """How many creatures a player controls that have *any* of a set of
    subtypes (CR 205.3) - The Mycotyrant's own "the number of creatures you
    control that are Fungi and/or Saprolings", a CR 604.3a characteristic-
    defining ability's count, not `CreaturesControlledByWithSubtype`'s own
    boolean `Selector` answer for one specific creature."""

    kind: Literal["creatures_with_subtypes_controlled_by"] = "creatures_with_subtypes_controlled_by"
    username: str | None = None
    subtypes: tuple[str, ...] = ()

    def __call__(self, chars: Characteristics, board: Board) -> int:
        wanted = {subtype.lower() for subtype in self.subtypes}
        return sum(
            1
            for other in board.values()
            if other.is_creature
            and other.controller == self.username
            and any(subtype.lower() in wanted for subtype in other.subtypes)
        )


class CountBasicLandTypesAmongLandsControlledBy(CountBase):
    """How many of the five basic land types (CR 305.6) are among the lands
    one player controls - *domain*'s number.
    """

    kind: Literal["basic_land_types_among_lands_controlled_by"] = (
        "basic_land_types_among_lands_controlled_by"
    )
    username: str | None = None

    def __call__(self, chars: Characteristics, board: Board) -> int:
        found = {
            subtype
            for other in board.values()
            if other.is_land and other.controller == self.username
            for subtype in other.subtypes
            if subtype in BASIC_LAND_TYPES
        }
        return len(found)


class CountOtherCreaturesLikeThatOne(CountBase):
    """ "... for each other [legendary] creature you control [with the same
    name as that creature]" - a count taken **per object**: "that creature"
    is whichever creature the effect is being applied to (`chars`), so each
    one counts the creatures other than itself.

    Mirror Box's same-name clause is `same_name=True`: CR 201.2a, "Two or
    more objects have the same name if they have at least one name in common
    ... An object with no name doesn't have the same name as any other
    object", so a nameless (face-down) creature counts nothing and is counted
    by nothing. Heroes' Podium's "for each other legendary creature you
    control" is `legendary=True` (CR 205.4d's supertype). "You control" is the
    source's controller, `username`, read off the board each time the board
    is computed (CR 611.3a), not a list fixed when the source entered.
    """

    kind: Literal["other_creatures_like_that_one"] = "other_creatures_like_that_one"
    username: str | None = None
    same_name: bool = False
    legendary: bool = False

    def __call__(self, chars: Characteristics, board: Board) -> int:
        if self.same_name and not chars.name:
            return 0
        return sum(
            1
            for other in board.values()
            if other.card_id != chars.card_id
            and other.is_creature
            and other.controller == self.username
            and (not self.same_name or other.name == chars.name)
            and (not self.legendary or Supertype.LEGENDARY in other.supertypes)
        )


class CountPermanentsWithSubtypeControlledBy(CountBase):
    """How many permanents with one subtype (CR 205.3) a player controls -
    Outcaster Greenblade's "for each Desert you control", Hold the Gates'
    "for each Gate you control", Eluge, the Shoreless Sea's "the number of
    Islands you control". Read off the board as the asking sublayer sees it
    (CR 613.5), so a land that became an Island in layer 4 (CR 613.1d) - a
    flooded land, a Blood Moon'd one - already counts by 7a/7c.
    `subtype` is stored lowercased.
    """

    kind: Literal["permanents_with_subtype_controlled_by"] = "permanents_with_subtype_controlled_by"
    username: str | None = None
    subtype: str

    def __call__(self, chars: Characteristics, board: Board) -> int:
        return sum(
            1
            for other in board.values()
            if other.controller == self.username
            and any(word.lower() == self.subtype for word in other.subtypes)
        )


class CountColorsAmongControlledBy(CountBase):
    """How many colors (CR 105.1) are among a group of permanents a player
    controls - Sisay, Weatherlight Captain's "for each color among other
    legendary permanents you control", Earthen Ally's "for each color among
    Allies you control". CR 105.2: a color counts once however many of the
    permanents share it. `excludes_self` is "other": the object being
    modified (`chars`) is left out. `card_type`/`subtype`/`supertype` narrow
    the group; all `None` is every permanent.
    """

    kind: Literal["colors_among_controlled_by"] = "colors_among_controlled_by"
    username: str | None = None
    excludes_self: bool = False
    card_type: Type | None = None
    subtype: str | None = None
    supertype: Supertype | None = None

    def __call__(self, chars: Characteristics, board: Board) -> int:
        colors: set[Color] = set()
        for other in board.values():
            if other.controller != self.username:
                continue
            if self.excludes_self and other.card_id == chars.card_id:
                continue
            if self.card_type is not None and self.card_type not in other.types:
                continue
            if self.supertype is not None and self.supertype not in other.supertypes:
                continue
            if self.subtype is not None and not any(
                word.lower() == self.subtype for word in other.subtypes
            ):
                continue
            colors.update(other.colors)
        return len(colors)


#: How many of something an effect counts, judged against one object and the
#: board as it stands in that sublayer (CR 613.5).
Count = Annotated[
    FixedCount
    | CountOtherCreaturesLikeThatOne
    | CountOtherCreaturesNamed
    | CountLandsControlledBy
    | CountPermanentsControlledBy
    | CountCreaturesWithSubtypesControlledBy
    | CountBasicLandTypesAmongLandsControlledBy
    | CountPermanentsWithSubtypeControlledBy
    | CountColorsAmongControlledBy,
    Field(discriminator="kind"),
]


class SelectorBase(EngineModel):
    """Does this effect apply to that object? Judged against characteristics as
    computed so far, with the rest of the board available for effects that
    count things or say "each other" (CR 613.5).
    """

    model_config = ConfigDict(frozen=True)

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        raise NotImplementedError


class Only(SelectorBase):
    """Exactly one permanent, by id."""

    kind: Literal["only"] = "only"
    card_id: UUID

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        return chars.card_id == self.card_id


class OnlyThisIncarnation(SelectorBase):
    """Like `Only`, but also refuses CR 400.7's "new object" - same `id`, but a
    permanent that left its zone and came back since `stamp` was taken. See
    `only_this_incarnation`'s own docstring for the full CR 400.7/CR 611.2c
    argument; `chars.zone_change_stamp` is what lets this be a value rather
    than a closure over a live `CardState`.
    """

    kind: Literal["only_this_incarnation"] = "only_this_incarnation"
    card_id: UUID
    stamp: UUID

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        return chars.card_id == self.card_id and chars.zone_change_stamp == self.stamp


class EveryCreature(SelectorBase):
    kind: Literal["every_creature"] = "every_creature"

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        return chars.is_creature


class SameNameAs(SelectorBase):
    """Every creature whose name is `name` (CR 201.2a)."""

    kind: Literal["same_name_as"] = "same_name_as"
    name: str

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        return bool(self.name) and chars.is_creature and chars.name == self.name


class CreaturesControlledBy(SelectorBase):
    kind: Literal["creatures_controlled_by"] = "creatures_controlled_by"
    username: str | None = None

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        return chars.is_creature and chars.controller == self.username


class OtherCreaturesControlledBy(SelectorBase):
    """ "Other creatures you control" - the source itself is excluded."""

    kind: Literal["other_creatures_controlled_by"] = "other_creatures_controlled_by"
    source_id: UUID
    username: str | None = None

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        return (
            chars.is_creature
            and chars.controller == self.username
            and chars.card_id != self.source_id
        )


class OtherCreatures(SelectorBase):
    """Every creature except this one, whoever controls it - Ygra, Eater of
    All's "Other creatures are Food artifacts ..." reaches every creature on
    the battlefield, not only its controller's, which is what tells this apart
    from `OtherCreaturesControlledBy`.
    """

    kind: Literal["other_creatures"] = "other_creatures"
    source_id: UUID

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        return chars.is_creature and chars.card_id != self.source_id


class CreaturesControlledByOpponentsOf(SelectorBase):
    """ "Creatures your opponents control" - every creature someone else
    controls. A permanent with no controller at all is nobody's, so it is not
    caught.
    """

    kind: Literal["creatures_controlled_by_opponents_of"] = "creatures_controlled_by_opponents_of"
    username: str | None = None

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        return (
            chars.is_creature and chars.controller is not None and chars.controller != self.username
        )


class LandsControlledBy(SelectorBase):
    kind: Literal["lands_controlled_by"] = "lands_controlled_by"
    username: str | None = None

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        return chars.is_land and chars.controller == self.username


class NonbasicLands(SelectorBase):
    """Every land without the basic supertype (CR 205.4c)."""

    kind: Literal["nonbasic_lands"] = "nonbasic_lands"

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        return chars.is_land and not chars.is_basic


class EveryLand(SelectorBase):
    kind: Literal["every_land"] = "every_land"

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        return chars.is_land


class OtherNonAuraEnchantments(SelectorBase):
    kind: Literal["other_non_aura_enchantments"] = "other_non_aura_enchantments"
    source_id: UUID

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        return (
            chars.card_id != self.source_id
            and Type.ENCHANTMENT in chars.types
            and "Aura" not in chars.subtypes
        )


class QualifiedCreatures(SelectorBase):
    """ "[Other] [non<colour>] [land] creature[ token]s [you control|your
    opponents control]" - the anthem subject with the qualifiers the pool
    actually prints, composed one predicate at a time. See `qualified_
    creatures`'s own docstring for what each qualifier means.

    `gate_card_type`/`gate_threshold` replace what used to be a `board_gate:
    Callable[[Board], bool]` parameter - CR 611.3a's "isn't 'locked in'" board
    condition, stored as the two scalars `CreatureQualifiers` already carries
    rather than a closure over them, for the same reason every other field
    here is a value and not a callable.
    """

    kind: Literal["qualified_creatures"] = "qualified_creatures"
    source_id: UUID
    username: str | None = None
    other: bool = False
    opponents: bool = False
    without_color: Color | None = None
    land: bool = False
    also_artifact: bool = False
    tokens: bool = False
    gate_card_type: Type | None = None
    gate_threshold: int = 0
    nontoken: bool = False
    legendary: bool | None = None
    """`True` for "legendary creatures", `False` for "nonlegendary creatures"
    (CR 205.4d's supertype), `None` when the subject names neither."""
    of_chosen_color: bool = False
    """ "... of the chosen color" (Caged Sun): the colour the source chose as
    it entered (CR 614.12a), carried in `chosen_color`. With no colour chosen
    the group is empty rather than every creature."""
    chosen_color: Color | None = None

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        if not chars.is_creature:
            return False
        if self.of_chosen_color and (
            self.chosen_color is None or self.chosen_color not in chars.colors
        ):
            return False
        if self.nontoken and chars.is_token:
            return False
        if self.legendary is not None and self.legendary != (
            Supertype.LEGENDARY in chars.supertypes
        ):
            return False
        if self.opponents:
            if chars.controller is None or chars.controller == self.username:
                return False
        elif self.username is not None and chars.controller != self.username:
            return False
        if self.other and chars.card_id == self.source_id:
            return False
        if self.without_color is not None and self.without_color in chars.colors:
            return False
        if self.land and not chars.is_land:
            return False
        if self.also_artifact and Type.ARTIFACT not in chars.types:
            return False
        if self.tokens and not chars.is_token:
            return False
        if self.gate_card_type is not None:
            count = sum(
                1
                for other in board.values()
                if self.gate_card_type in other.types and other.controller == self.username
            )
            if count < self.gate_threshold:
                return False
        return True


class SelfIfControls(SelectorBase):
    """ "This creature has vigilance as long as you control a Jace
    planeswalker." (Mind Meanderer) - `Only`'s identity test plus CR 611.3a's
    live board condition: the source's own controller must also control a
    permanent matching `card_type`/`subtype`, re-asked on every CR 613.5
    computation rather than locked in at build time.
    """

    kind: Literal["self_if_controls"] = "self_if_controls"
    card_id: UUID
    username: str | None = None
    card_type: Type | None = None
    subtype: str | None = None
    color: Color | None = None
    """Knight of Grace's "a black permanent": the matching permanent's
    computed colour (CR 105.2)."""
    controlled_by: Literal["you", "any", "opponent"] = "you"
    """Whose permanents are looked at: "you control" (the default), "any
    player controls" (Knight of Grace) or "an opponent controls"."""

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        if chars.card_id != self.card_id:
            return False
        return any(
            self._controller_matches(other.controller)
            and (self.card_type is None or self.card_type in other.types)
            and (self.subtype is None or self.subtype in other.subtypes)
            and (self.color is None or self.color in other.colors)
            for other in board.values()
        )

    def _controller_matches(self, controller: str | None) -> bool:
        if self.controlled_by == "any":
            return True
        if self.controlled_by == "opponent":
            return controller is not None and controller != self.username
        return controller == self.username


class ControlledCountRequirement(EngineModel):
    """One "you control N or more `<quality>`" test on the board: permanents
    the source's controller controls with this `name` (CR 201.2), card type
    or subtype, at least `threshold` of them."""

    model_config = ConfigDict(frozen=True)

    name: str | None = None
    card_type: Type | None = None
    subtype: str | None = None
    threshold: int = 1

    def holds(self, username: str | None, board: Board) -> bool:
        count = sum(
            1
            for other in board.values()
            if other.controller == username
            and (self.name is None or other.name == self.name)
            and (self.card_type is None or self.card_type in other.types)
            and (
                self.subtype is None
                or any(each.lower() == self.subtype.lower() for each in other.subtypes)
            )
        )
        return count >= self.threshold


class SelfIfControlsCounted(SelectorBase):
    """ "As long as you control eight or more permanents named Phoenix Fleet
    Airship, this Vehicle is ..." / "... and you control an Army, Grond is
    ..." - `Only`'s identity test plus every `ControlledCountRequirement`,
    re-asked on every CR 613.5 computation (CR 611.3a)."""

    kind: Literal["self_if_controls_counted"] = "self_if_controls_counted"
    card_id: UUID
    username: str | None = None
    requirements: tuple[ControlledCountRequirement, ...] = ()

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        return chars.card_id == self.card_id and all(
            requirement.holds(self.username, board) for requirement in self.requirements
        )


class CreaturesControlledByWhereToughnessExceedsPower(SelectorBase):
    """ "Each creature you control with toughness greater than its power
    assigns combat damage equal to its toughness rather than its power."
    (Ghalta the Immovable) - the condition lives here so
    `machines/combat.py`'s `_assignment_power_of` only has to ask whether the
    grant text is present at all, not re-derive the comparison; CR 611.3a's
    live re-ask means a creature whose toughness stops exceeding its power
    drops out of the grant on the very next CR 613.5 computation.
    """

    kind: Literal["creatures_controlled_by_toughness_exceeds_power"] = (
        "creatures_controlled_by_toughness_exceeds_power"
    )
    username: str | None = None

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        return (
            chars.is_creature
            and chars.controller == self.username
            and chars.power is not None
            and chars.toughness is not None
            and chars.toughness > chars.power
        )


class CreaturesControlledByWherePowerOrToughnessAtMost(SelectorBase):
    """ "Creatures you control with power or toughness 1 or less can't be
    blocked." (Tetsuko Umezawa, Fugitive) - the group grant's own condition,
    re-asked on every CR 613.5 computation the same way every other gated
    grant in this module is.
    """

    kind: Literal["creatures_controlled_by_power_or_toughness_at_most"] = (
        "creatures_controlled_by_power_or_toughness_at_most"
    )
    username: str | None = None
    threshold: int = 0

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        return (
            chars.is_creature
            and chars.controller == self.username
            and (
                (chars.power is not None and chars.power <= self.threshold)
                or (chars.toughness is not None and chars.toughness <= self.threshold)
            )
        )


class SelfIfPowerNegative(SelectorBase):
    """ "If Loot's power is negative, he assigns combat damage as though his
    power were positive." (Loot, the Anomaly) - `Only`'s identity test plus a
    live power check, the self-only twin of `CreaturesControlledByWhereToughnessExceedsPower`.
    """

    kind: Literal["self_if_power_negative"] = "self_if_power_negative"
    card_id: UUID

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        return chars.card_id == self.card_id and chars.power is not None and chars.power < 0


class AllPermanentsControlledBy(SelectorBase):
    """ "Each [nonland] permanent you control"."""

    kind: Literal["all_permanents_controlled_by"] = "all_permanents_controlled_by"
    username: str | None = None
    nonland: bool = False

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        return chars.controller == self.username and not (self.nonland and chars.is_land)


class PermanentsControlledBy(SelectorBase):
    """ "[Nontoken] <card type>s you control" (CR 205.2a)."""

    kind: Literal["permanents_controlled_by"] = "permanents_controlled_by"
    username: str | None = None
    card_type: Type
    nontoken: bool = False

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        if self.nontoken and chars.is_token:
            return False
        return self.card_type in chars.types and chars.controller == self.username


class CreaturesControlledByWithSubtype(SelectorBase):
    """ "[Other] <subtype>s you control"."""

    kind: Literal["creatures_controlled_by_with_subtype"] = "creatures_controlled_by_with_subtype"
    username: str | None = None
    subtypes: tuple[str, ...] = ()
    other_than: UUID | None = None

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        wanted = {subtype.lower() for subtype in self.subtypes}
        return (
            chars.is_creature
            and chars.controller == self.username
            and chars.card_id != self.other_than
            and any(subtype.lower() in wanted for subtype in chars.subtypes)
        )


class CreaturesControlledByWithColor(SelectorBase):
    kind: Literal["creatures_controlled_by_with_color"] = "creatures_controlled_by_with_color"
    username: str | None = None
    color: Color

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        return (
            chars.is_creature and chars.controller == self.username and self.color in chars.colors
        )


class PermanentsOfTypesControlledBy(SelectorBase):
    """ "<type> and <type> you control" (CR 205.2a) - `PermanentsControlledBy`'s
    own multi-type sibling, for a compound subject naming more than one card
    type at once (Sorin, Vengeful Bloodlord's own "creatures and
    planeswalkers you control"): any permanent whose computed types
    intersect the named set, not only one specific type."""

    kind: Literal["permanents_of_types_controlled_by"] = "permanents_of_types_controlled_by"
    username: str | None = None
    card_types: tuple[Type, ...] = ()

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        return chars.controller == self.username and any(
            card_type in chars.types for card_type in self.card_types
        )


class PermanentsControlledByWithCounters(SelectorBase):
    """ "[Each other] [creature] you control with [a/an <counter kind>] counter
    on it/them" (Innkeeper's Talent's bare "permanents ... with counters", and
    Gallia the Merrymaker / Vigorbloom Vanguard's "each other creature you
    control with a +1/+1 counter on it").

    `counter_kind` narrows the plain "has any counter" test to one named kind
    (CR 122.1's counter kinds are compared by name); `creatures_only`/
    `other_than` narrow the subject to a creature clause the way `other`/
    `source_id` narrow `QualifiedCreatures`.
    """

    kind: Literal["permanents_controlled_by_with_counters"] = (
        "permanents_controlled_by_with_counters"
    )
    username: str | None = None
    counter_kind: str | None = None
    creatures_only: bool = False
    other_than: UUID | None = None

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        if chars.controller != self.username:
            return False
        if self.creatures_only and not chars.is_creature:
            return False
        if self.other_than is not None and chars.card_id == self.other_than:
            return False
        if self.counter_kind is not None:
            return chars.counters.get(self.counter_kind, 0) > 0
        return any(count > 0 for count in chars.counters.values())


class WithChangeling(SelectorBase):
    """Every object that has changeling as layer 4 finds it (CR 702.73a).

    Read off the characteristics as layers 1-3 left them, so a copy effect
    that gave an object changeling (CR 604.3a item 2: "acquired ... as the
    result of a copy effect") is included and one that took it away is not.
    Layer 6's ability-removing effects come later (CR 613.1f), so Humility does
    not reach back and undo it.
    """

    kind: Literal["with_changeling"] = "with_changeling"

    def __call__(self, chars: Characteristics, board: Board) -> bool:
        return has_changeling("\n".join(chars.abilities))


#: Does this effect apply to that object? Judged against characteristics as
#: computed so far, with the rest of the board available for effects that
#: count things or say "each other" (CR 613.5).
Selector = Annotated[
    Only
    | OnlyThisIncarnation
    | EveryCreature
    | SameNameAs
    | CreaturesControlledBy
    | OtherCreaturesControlledBy
    | OtherCreatures
    | CreaturesControlledByOpponentsOf
    | LandsControlledBy
    | NonbasicLands
    | EveryLand
    | OtherNonAuraEnchantments
    | QualifiedCreatures
    | SelfIfControls
    | SelfIfControlsCounted
    | CreaturesControlledByWhereToughnessExceedsPower
    | CreaturesControlledByWherePowerOrToughnessAtMost
    | SelfIfPowerNegative
    | AllPermanentsControlledBy
    | PermanentsControlledBy
    | PermanentsOfTypesControlledBy
    | CreaturesControlledByWithSubtype
    | CreaturesControlledByWithColor
    | PermanentsControlledByWithCounters
    | WithChangeling,
    Field(discriminator="kind"),
]


class ModificationBase(EngineModel):
    """What the effect does to one object it applies to. Pure: returns a new
    `Characteristics`, never edits the one it was handed.
    """

    model_config = ConfigDict(frozen=True)

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        raise NotImplementedError


class LoseAllAbilities(ModificationBase):
    """Layer 6 removal (CR 613.1f)."""

    kind: Literal["lose_all_abilities"] = "lose_all_abilities"

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        return chars.with_(abilities=())


class GrantAbility(ModificationBase):
    """Layer 6 addition (CR 613.1f), deduplicated."""

    kind: Literal["grant_ability"] = "grant_ability"
    text: str

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        if chars.has_ability(self.text):
            return chars
        return chars.with_(abilities=chars.abilities + (self.text,))


class GrantAbilityInstance(ModificationBase):
    """Layer 6 addition (CR 613.1f) that does *not* deduplicate - see
    `grant_ability_instance`'s own docstring (ward, CR 702.21a, CR 113.2c).
    """

    kind: Literal["grant_ability_instance"] = "grant_ability_instance"
    text: str

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        return chars.with_(abilities=chars.abilities + (self.text,))


class AddType(ModificationBase):
    """Layer 4: gain a card type on top of the ones already there (CR 205.1b)."""

    kind: Literal["add_type"] = "add_type"
    card_type: Type

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        if self.card_type in chars.types:
            return chars
        return chars.with_(types=chars.types + (self.card_type,))


#: The card types whose subtypes are a closed list of their own: artifact
#: types (CR 205.3g), enchantment types (CR 205.3h), land types (CR 205.3i),
#: the spell types instants and sorceries share (CR 205.3k), and the battle
#: type (CR 205.3q). Creature types are shared with kindred (CR 205.3m) and
#: planeswalker types are their own long list (CR 205.3j); neither is spelled
#: out here, which `RemoveType` accounts for.
_ARTIFACT_TYPES = frozenset(
    {
        "Attraction", "Blood", "Bobblehead", "Book", "Clue", "Contraption", "Equipment",
        "Food", "Fortification", "Gold", "Incubator", "Infinity", "Junk", "Lander", "Map",
        "Mutagen", "Powerstone", "Spacecraft", "Stone", "Treasure", "Vehicle", "Vibranium",
    }
)  # fmt: skip
_SPELL_TYPES = frozenset({"Adventure", "Arcane", "Lesson", "Omen", "Trap"})
CLOSED_SUBTYPE_LISTS: dict[Type, frozenset[str]] = {
    Type.ARTIFACT: _ARTIFACT_TYPES,
    Type.ENCHANTMENT: frozenset(
        {
            "Aura",
            "Background",
            "Cartouche",
            "Case",
            "Class",
            "Curse",
            "Plan",
            "Role",
            "Room",
            "Rune",
            "Saga",
            "Shard",
            "Shrine",
        }
    ),  # fmt: skip
    Type.LAND: frozenset(
        {
            "Cave",
            "Desert",
            "Forest",
            "Gate",
            "Island",
            "Lair",
            "Locus",
            "Mine",
            "Mountain",
            "Plains",
            "Planet",
            "Power-Plant",
            "Sphere",
            "Swamp",
            "Tower",
            "Town",
            "Urza's",
            "Urza\u2019s",
        }
    ),  # fmt: skip
    Type.INSTANT: _SPELL_TYPES,
    Type.SORCERY: _SPELL_TYPES,
    Type.BATTLE: frozenset({"Siege"}),
}


class RemoveType(ModificationBase):
    """Layer 4 (CR 613.1d): stop having one card type - impending's "it's not a
    creature" (CR 702.176a).

    CR 205.1a: "If an object's card type is removed, the subtypes correlated
    with that card type will remain if they are also the subtypes of a card
    type the object currently has; otherwise, they are also removed for the
    entire time the object's card type is removed." So an Enchantment Creature
    - Avatar Horror that stops being a creature is an Enchantment with no
    subtypes: Avatar and Horror are creature types, and no enchantment type.

    A subtype is kept when some type the object still has lists it. A remaining
    type whose list is not spelled out in `CLOSED_SUBTYPE_LISTS` - a kindred,
    which shares creature types (CR 205.3m), or a planeswalker - keeps every
    subtype rather than guessing which of them it correlates with.
    """

    kind: Literal["remove_type"] = "remove_type"
    card_type: Type

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        if self.card_type not in chars.types:
            return chars
        remaining = tuple(kind for kind in chars.types if kind is not self.card_type)
        removed_list = CLOSED_SUBTYPE_LISTS.get(self.card_type)

        def kept(subtype: str) -> bool:
            for kind in remaining:
                listed = CLOSED_SUBTYPE_LISTS.get(kind)
                if listed is None or subtype in listed:
                    return True
            return removed_list is not None and subtype not in removed_list

        return chars.with_(
            types=remaining,
            subtypes=tuple(subtype for subtype in chars.subtypes if kept(subtype)),
        )


class AddSubtype(ModificationBase):
    """Layer 4: gain a land type "in addition to" the ones already there.

    A land with a basic land type has the matching mana ability intrinsically
    (CR 305.6), so the ability comes along with the type.
    """

    kind: Literal["add_subtype"] = "add_subtype"
    subtype: str
    mana_ability: str | None = None

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        if self.subtype in chars.subtypes:
            return chars
        changes: dict[str, object] = {"subtypes": chars.subtypes + (self.subtype,)}
        if self.mana_ability is not None and not chars.has_ability(self.mana_ability):
            changes["abilities"] = chars.abilities + (self.mana_ability,)
        return chars.with_(**changes)


class AddEveryCreatureType(ModificationBase):
    """Layer 4: changeling's "This object is every creature type" (CR 702.73a).

    Additive, and creature types only - `with_every_creature_type` holds the
    CR 205.3d gate (a creature or kindred object only).
    """

    kind: Literal["add_every_creature_type"] = "add_every_creature_type"

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        subtypes = with_every_creature_type(chars.types, chars.subtypes)
        return chars if subtypes == chars.subtypes else chars.with_(subtypes=subtypes)


class AddBasicLandTypes(ModificationBase):
    """Layer 4: become every basic land type in addition to the others (CR 613.1d)."""

    kind: Literal["add_basic_land_types"] = "add_basic_land_types"

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        subtypes = list(chars.subtypes)
        abilities = list(chars.abilities)
        for subtype, mana_ability in BASIC_LAND_TYPES.items():
            if subtype not in subtypes:
                subtypes.append(subtype)
            if mana_ability not in abilities:
                abilities.append(mana_ability)
        return chars.with_(subtypes=tuple(subtypes), abilities=tuple(abilities))


class SetBasicLandType(ModificationBase):
    """Layer 4: become a basic land type, losing the old ones (CR 305.7)."""

    kind: Literal["set_basic_land_type"] = "set_basic_land_type"
    subtype: str
    mana_ability: str

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        return chars.with_(subtypes=(self.subtype,), abilities=(self.mana_ability,))


class SetColors(ModificationBase):
    """Layer 5 (CR 613.1e)."""

    kind: Literal["set_colors"] = "set_colors"
    colors: tuple[Color, ...] = ()

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        return chars.with_(colors=self.colors)


class SetController(ModificationBase):
    """Layer 2 (CR 613.1b)."""

    kind: Literal["set_controller"] = "set_controller"
    username: str

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        return chars.with_(controller=self.username)


class ReplaceText(ModificationBase):
    """Layer 3, word for word (CR 612.1, CR 612.2)."""

    kind: Literal["replace_text"] = "replace_text"
    old: str
    new: str

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        return chars.with_(
            abilities=tuple(line.replace(self.old, self.new) for line in chars.abilities)
        )


class SetPowerToughness(ModificationBase):
    """Sublayer 7b (CR 613.4b)."""

    kind: Literal["set_power_toughness"] = "set_power_toughness"
    power: int
    toughness: int

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        return chars.with_(power=self.power, toughness=self.toughness)


class SetPowerToughnessToManaValue(ModificationBase):
    """Sublayer 7b, where the value is read off the object (CR 613.4b)."""

    kind: Literal["set_power_toughness_to_mana_value"] = "set_power_toughness_to_mana_value"

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        value = int(chars.mana_value)
        return chars.with_(power=value, toughness=value)


class DefinePowerToughness(ModificationBase):
    """Sublayer 7a: a characteristic-defining ability that defines P/T."""

    kind: Literal["define_power_toughness"] = "define_power_toughness"
    count: Count
    power: int = 0
    toughness: int = 0

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        amount = self.count(chars, board)
        return chars.with_(power=amount + self.power, toughness=amount + self.toughness)


class DefinePower(ModificationBase):
    """Sublayer 7a, power only (CR 613.4a)."""

    kind: Literal["define_power"] = "define_power"
    count: Count
    power: int = 0

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        return chars.with_(power=self.count(chars, board) + self.power)


class ModifyPowerToughness(ModificationBase):
    """Sublayer 7c (CR 613.4c). Adds; never sets."""

    kind: Literal["modify_power_toughness"] = "modify_power_toughness"
    power: int
    toughness: int

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        return chars.with_(
            power=(chars.power or 0) + self.power,
            toughness=(chars.toughness or 0) + self.toughness,
        )


class ModifyPowerToughnessPer(ModificationBase):
    """Sublayer 7c where the size of the pump is counted on the board (CR 613.4c)."""

    kind: Literal["modify_power_toughness_per"] = "modify_power_toughness_per"
    count: Count
    power: int
    toughness: int

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        amount = self.count(chars, board)
        return chars.with_(
            power=(chars.power or 0) + self.power * amount,
            toughness=(chars.toughness or 0) + self.toughness * amount,
        )


class SwitchPowerToughness(ModificationBase):
    """Sublayer 7d (CR 613.4d)."""

    kind: Literal["switch_power_toughness"] = "switch_power_toughness"

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        return chars.with_(power=chars.toughness, toughness=chars.power)


class BecomeACopy(ModificationBase):
    """CR 707.2/CR 707.4: a permanent already on the battlefield copies a
    different object's copiable values while remaining itself. See
    `_become_a_copy_builder`'s own docstring for the whole argument; every
    field here is a *resolved* value, fixed at the moment the effect was
    built, never re-derived from a live target.
    """

    kind: Literal["become_a_copy"] = "become_a_copy"
    name: str
    mana_value: float
    supertypes: tuple[Supertype, ...] = ()
    types: tuple[Type, ...] = ()
    subtypes: tuple[str, ...] = ()
    colors: tuple[Color, ...] = ()
    abilities: tuple[str, ...] = ()
    power: int | None = None
    toughness: int | None = None

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        return chars.with_(
            name=self.name,
            mana_value=self.mana_value,
            supertypes=self.supertypes,
            types=self.types,
            subtypes=self.subtypes,
            colors=self.colors,
            abilities=self.abilities,
            power=self.power,
            toughness=self.toughness,
        )


class SetCreatureTypes(ModificationBase):
    """Layer 4: the object's creature types become exactly these (CR 205.1a).

    "When an effect sets one or more of an object's subtypes, the new
    subtype(s) replaces any existing subtypes from the appropriate set" - so
    "becomes a white Rabbit" replaces every creature type (a changeling's
    included, CR 613.3 having applied its CDA first) and leaves the card types
    and any other set's subtypes alone.
    """

    kind: Literal["set_creature_types"] = "set_creature_types"
    subtypes: tuple[str, ...] = ()

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        creature = set(creature_types())
        kept = tuple(subtype for subtype in chars.subtypes if subtype not in creature)
        return chars.with_(subtypes=kept + self.subtypes)


class SetTypesAndSubtypes(ModificationBase):
    """Layer 4: replace the object's types and subtypes outright (CR 205.1a).

    Shared by `_self_becomes_type_until_next_turn_builder`, `_target_
    animation_builder` and `_self_animation_builder` - three different printed
    shapes ("becomes a land", Jolrael's animation, Mishra's Factory's own) that
    all do the identical thing to the board once their own regex has picked the
    types and the optional subtype apart.
    """

    kind: Literal["set_types_and_subtypes"] = "set_types_and_subtypes"
    types: tuple[Type, ...] = ()
    subtypes: tuple[str, ...] = ()

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        return chars.with_(types=self.types, subtypes=self.subtypes)


class AddTypesAndSubtype(ModificationBase):
    """Layer 4 (CR 613.1d): gain each card type and the creature type named,
    keeping everything already there (CR 205.1b).
    """

    kind: Literal["add_types_and_subtype"] = "add_types_and_subtype"
    types: tuple[Type, ...] = ()
    subtype: str

    def __call__(self, chars: Characteristics, board: Board) -> Characteristics:
        for card_type in self.types:
            chars = AddType(card_type=card_type)(chars, board)
        return AddSubtype(subtype=self.subtype)(chars, board)


#: What the effect does to one object it applies to. Pure: returns a new
#: `Characteristics`, never edits the one it was handed.
Modification = Annotated[
    LoseAllAbilities
    | GrantAbility
    | GrantAbilityInstance
    | AddType
    | RemoveType
    | AddSubtype
    | AddEveryCreatureType
    | AddBasicLandTypes
    | SetBasicLandType
    | SetColors
    | SetController
    | ReplaceText
    | SetPowerToughness
    | SetPowerToughnessToManaValue
    | DefinePowerToughness
    | DefinePower
    | ModifyPowerToughness
    | ModifyPowerToughnessPer
    | SwitchPowerToughness
    | BecomeACopy
    | SetTypesAndSubtypes
    | SetCreatureTypes
    | AddTypesAndSubtype,
    Field(discriminator="kind"),
]


class ConditionBase(EngineModel):
    """Whether a "for as long as" duration is still running (CR 611.2b).

    Takes the `Game`, not the layer engine's board: "for as long as this
    creature remains on the battlefield" is a question about a zone, and the
    layer engine never sees one. `ContinuousEffect.holds` is what calls this.
    """

    model_config = ConfigDict(frozen=True)

    #: Whether the condition could turn true again after turning false.
    can_restart: ClassVar[bool] = False

    def holds_in(self, game: Game) -> bool:
        raise NotImplementedError


class RemainsOnBattlefield(ConditionBase):
    """ "For as long as this creature remains on the battlefield" (CR 611.2b).

    Looks the permanent up by id every time, rather than closing over a live
    `CardState` - the same `zone_change_stamp` trick `OnlyThisIncarnation` uses,
    and for the same reason (CR 400.7: a permanent that leaves and returns is a
    new object, so the condition must stay false for the returning one, not
    read as true just because the id is unchanged).
    """

    kind: Literal["remains_on_battlefield"] = "remains_on_battlefield"
    card_id: UUID
    stamp: UUID

    def holds_in(self, game: Game) -> bool:
        permanent = game.find_by_id(self.card_id)
        if permanent is None:
            return False
        return permanent.zone is Zone.BATTLEFIELD and permanent.zone_change_stamp == self.stamp


class HasCounter(ConditionBase):
    """ "For as long as it has a `<kind>` counter on it" (CR 611.2b) - Eluge,
    the Shoreless Sea's and Aquitect's Will's flooded land. The same
    `zone_change_stamp` guard as `RemainsOnBattlefield`: a land that left and
    came back is a new object (CR 400.7) the duration never covered. Once
    false the duration has ended for good - `ContinuousEffects.active` drops
    the effect then, so a counter put back later does not restart it.
    """

    #: Unlike a zone stamp, a counter can come back - so once false this
    #: duration is dropped at once (`ContinuousEffects.active`), not left to
    #: be re-asked.
    can_restart: ClassVar[bool] = True

    kind: Literal["has_counter"] = "has_counter"
    card_id: UUID
    stamp: UUID
    counter: str

    def holds_in(self, game: Game) -> bool:
        permanent = game.find_by_id(self.card_id)
        if permanent is None or permanent.zone is not Zone.BATTLEFIELD:
            return False
        if permanent.zone_change_stamp != self.stamp:
            return False
        return permanent.counters[self.counter] > 0


#: Whether a "for as long as" duration is still running (CR 611.2b).
Condition = Annotated[RemainsOnBattlefield | HasCounter, Field(discriminator="kind")]


class OffBattlefieldCharacteristics(NamedTuple):
    """What "As long as `<this>` isn't on the battlefield, it's a `<P/T>`
    `<subtype...>` `<type...>` in addition to its other types" adds to the
    object it is printed on - Grist, the Hunger Tide's "it's a 1/1 Insect
    creature".

    CR 113.6c: "An ability that states which zones it doesn't function in
    functions everywhere except for the specified zones, even outside the game
    and before the game begins." CR 205.1b: "in addition to its other types"
    keeps every prior card type and subtype. It is not a characteristic-
    defining ability - CR 604.3a's fifth criterion excludes one that sets a
    value "only if certain conditions" are met - so it is never a copiable
    value either (CR 707.2): `printed_characteristics` leaves it out, and
    `off_battlefield_characteristics_of` puts it back for the object itself.
    """

    types: tuple[Type, ...]
    subtypes: tuple[str, ...]
    power: int | None
    toughness: int | None


_OFF_BATTLEFIELD_CHARACTERISTICS_RE = re.compile(
    r"^as long as this [a-z]+ (?:isn't|is not) on the battlefield, "
    r"(?:it's|it is) (?:an? )?(?:(?P<power>\d+)/(?P<toughness>\d+) )?"
    r"(?P<words>[a-z][a-z -]*?) in addition to its other types\.?$",
    re.IGNORECASE,
)


@functools.cache
def off_battlefield_characteristics(
    oracle_text: str, card_name: str, legendary: bool = True
) -> OffBattlefieldCharacteristics | None:
    """`OffBattlefieldCharacteristics` read off `oracle_text`, or `None`.

    The self-reference is normalised first (`self_normalized_effect_text`,
    CR 201.5/201.5c: "Grist" is Grist, the Hunger Tide's own short name), so
    the shape is read as CR 700.7's "this `<object>`" whatever name it prints.
    Every word of the granted type phrase must be a CR 205.2a card type or a
    CR 205.3 subtype, or nothing is read at all - an unrecognised word is a
    different sentence, not a narrower grant. Memoised on the text: it is
    asked on every type read of every card outside the battlefield.
    """
    if (
        "on the battlefield" not in oracle_text
        or "in addition to its other types" not in oracle_text
    ):
        return None
    for line in _ability_lines(oracle_text):
        normalized = self_normalized_effect_text(
            card_name, re.sub(r"\s*\([^)]*\)", "", line).strip(), legendary=legendary
        )
        match = _OFF_BATTLEFIELD_CHARACTERISTICS_RE.fullmatch(normalized)
        if match is None:
            continue
        types: list[Type] = []
        subtypes: list[str] = []
        for word in match.group("words").split():
            lowered = word.lower()
            if lowered in {card_type.value for card_type in Type}:
                types.append(Type(lowered))
            elif lowered in subtype_vocabulary():
                subtypes.append(word)
            else:
                return None
        power = match.group("power")
        toughness = match.group("toughness")
        return OffBattlefieldCharacteristics(
            types=tuple(types),
            subtypes=tuple(subtypes),
            power=int(power) if power is not None else None,
            toughness=int(toughness) if toughness is not None else None,
        )
    return None


def off_battlefield_characteristics_of(state: CardState) -> Characteristics:
    """An object's characteristics anywhere but the battlefield:
    `printed_characteristics` plus CR 113.6c's off-battlefield grant
    (`CardState.off_battlefield_characteristics`) where it carries one.

    `Game.characteristics_of`'s answer for an object off the battlefield. The
    grant is layered on here rather than inside `printed_characteristics`
    because that function is also CR 707.2's copiable values, which the grant
    is not part of.
    """
    printed = printed_characteristics(state)
    grant = state.off_battlefield_characteristics
    if grant is None:
        return printed
    return printed.model_copy(
        update={
            "types": printed.types + tuple(t for t in grant.types if t not in printed.types),
            "subtypes": printed.subtypes
            + tuple(s for s in grant.subtypes if s not in printed.subtypes),
            "power": grant.power if grant.power is not None else printed.power,
            "toughness": grant.toughness if grant.toughness is not None else printed.toughness,
        }
    )


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
            controller=state.stored_controller,
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
            is_token=state.token,
            zone_change_stamp=state.zone_change_stamp,
        )
    # CR 712.8d/712.8e/712.8f: a double-faced permanent has only the
    # characteristics of the face that is up - the front face by default
    # (CR 712.8a, 712.8d), the back face while it is transformed (CR 712.8e),
    # the land face when an MDFC was played as one (CR 712.8f, CR 712.12).
    # `CardState.up_face` is the one place that choice is made, and every
    # characteristic here is read through the `CardState` property that
    # consults it rather than off the raw `Card`, whose top-level `power`,
    # `toughness`, `oracle_text`, `colors` and `name` are null (or the
    # combined "Front // Back" string) for a `transform` or `modal_dfc` card.
    #
    # CR 202.3b/712.8e is the single exception: mana value is "calculated using
    # the mana cost of its front face" even while the back face is up, which is
    # exactly what `CardState.mana_value` encodes.
    #
    # Power and toughness are read off the face directly rather than through
    # `CardState.power`/`.toughness`, which already fold counters in (CR 122.1a)
    # - these are the *printed* values layer 7a starts from, and CR 613.4c
    # applies the counters again in sublayer 7c.
    up_face = state.up_face
    power = _as_number(up_face.power) if up_face is not None else _as_number(card.power)
    toughness = _as_number(up_face.toughness) if up_face is not None else _as_number(card.toughness)
    return Characteristics(
        card_id=state.id,
        name=state.name,
        mana_value=state.mana_value,
        controller=state.stored_controller,
        supertypes=tuple(state.supertypes),
        # `printed_types`, not `types`: CR 113.6c's off-battlefield grant is
        # not a copiable value (CR 707.2) - see `off_battlefield_characteristics_of`.
        types=tuple(state.printed_types),
        # The type line only: changeling's creature types are its CDA's
        # layer 4 contribution (`_changeling_effects`), not a printed value.
        subtypes=tuple(state.printed_subtypes),
        colors=tuple(state.colors),
        abilities=tuple(_ability_lines(state.oracle_text))
        + _keyword_counter_lines(on_the_permanent),
        power=power,
        toughness=toughness,
        counters=on_the_permanent,
        is_token=state.token,
        zone_change_stamp=state.zone_change_stamp,
    )


def _ability_lines(oracle_text: str | None) -> list[str]:
    return [line.strip() for line in (oracle_text or "").splitlines() if line.strip()]


def _keyword_counter_lines(counters: Mapping[str, int]) -> tuple[str, ...]:
    """CR 122.1b: "A keyword counter on a permanent ... causes that object to
    gain that keyword" - Guide of Souls' own reflexive consequence puts a
    flying counter on a creature that may print no flying anywhere.

    Read as ordinary ability lines feeding straight into the same
    `keywords_in_lines` vocabulary `machines/combat.py::has_keyword` already
    reads off `Characteristics.abilities` for a static or layer-6-granted
    keyword - a keyword counter is neither of those (CR 122.1 counters are
    not continuous effects and have no layer of their own), but the reader on
    the other end cannot tell the difference and does not need to. Only a
    name `machines/combat.py`'s own `Keyword` vocabulary recognises is turned
    into a line; an invented counter name ("charge", "fate") is a counter
    CR 122.1 leaves alone and never becomes an ability.
    """
    return tuple(
        keyword.value.replace("_", " ").title()
        for keyword in Keyword
        if counters.get(keyword.value, 0) > 0
    )


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


class ContinuousEffect(EngineModel):
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

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=new_id)
    #: Human-readable, and what the application journal reports.
    description: str
    layer: Layer
    sublayer: Sublayer | CopySublayer | None = None
    timestamp: int = 0
    #: This effect's position among the other effects `effects_for` returned
    #: for the same source in the same call (CR 613.7a: a static ability's
    #: whole set of effects shares one timestamp - the permanent's - and
    #: CR 611.2c/613.7b does the same for one resolving ability's whole batch).
    #: Neither CR 613.7 nor CR 613.8 (dependency) says which of two same-source,
    #: same-timestamp, independent effects goes first - Scion of Draco's five
    #: colour-conditioned grants and Elesh Norn, Grand Cenobite's two anthem
    #: lines are both this shape, and the result happens to be commutative for
    #: both. Lacking a rule, the engine's own tie-break is the order the
    #: abilities are written on the source: `effects_for` enumerates its
    #: builder's output 0, 1, 2, ... in the order `parsed_layer_effects` (or a
    #: `LAYER_EFFECTS` row) produced it, which is a pure function of the
    #: source's own oracle text - never of `id`, which is freshly randomised
    #: every time a static effect is rebuilt (CR 613.5) and so cannot be used
    #: for this at all. Only breaks a tie; effects at different timestamps
    #: order by timestamp regardless of `order`.
    order: int = 0
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
    #: Only for `UNTIL_YOUR_NEXT_TURN`: whose next turn ends it (CR 611.2a).
    until_next_turn_of: str | None = None
    selector: Selector
    modification: Modification

    def holds(self, game: Game | None = None) -> bool:
        """Is this effect's duration still running (CR 611.2b)?

        Always true for an effect with no `condition`. `UNTIL_END_OF_TURN` is
        not asked here - it is removed outright by `ContinuousEffects.end_the_turn`
        (CR 514.2), because CR 514.2 ends the effect rather than suspending it.

        `game` is only ever dereferenced when there *is* a condition to check -
        every effect with no `condition` returns `True` without touching it, so
        the huge majority of callers that have no `Game` handy (a bare
        `compute_board` call, most of `ContinuousEffects`' own callers) can
        pass nothing at all. A `condition` with no `game` to check it against is
        a caller that forgot to plumb one through, and that fails loudly rather
        than guessing - see `memory/silent-default-dispatch-tables.md`.
        """
        if self.condition is None:
            return True
        if game is None:
            raise ValueError(
                f'{self.description!r} has a "for as long as" condition but no '
                "game was given to check it against"
            )
        return self.condition.holds_in(game)

    @model_validator(mode="after")
    def _duration_matches_condition(self) -> ContinuousEffect:
        if self.duration is Duration.FOR_AS_LONG_AS and self.condition is None:
            raise ValueError('a "for as long as" effect needs a condition (CR 611.2b)')
        if self.duration is not Duration.FOR_AS_LONG_AS and self.condition is not None:
            raise ValueError(
                f"{with_indefinite_article(str(self.duration))} effect has no condition to check"
            )
        if self.duration is Duration.UNTIL_YOUR_NEXT_TURN and self.until_next_turn_of is None:
            raise ValueError('an "until your next turn" effect needs to say whose (CR 611.2a)')
        not_next_turn = self.duration is not Duration.UNTIL_YOUR_NEXT_TURN
        if not_next_turn and self.until_next_turn_of is not None:
            raise ValueError(
                f"{with_indefinite_article(str(self.duration))} effect "
                "has no next-turn owner to check"
            )
        return self

    @model_validator(mode="after")
    def _sublayer_matches_layer(self) -> ContinuousEffect:
        if self.layer in _SUBLAYERED and self.sublayer is None:
            raise ValueError(f"an effect in layer {self.layer} needs a sublayer")
        if self.layer not in _SUBLAYERED and self.sublayer is not None:
            raise ValueError(f"layer {self.layer} has no sublayers")
        if self.sublayer is not None and self.sublayer not in _SUBLAYERS_BY_LAYER[self.layer]:
            raise ValueError(f"{self.sublayer!r} is not one of layer {self.layer}'s sublayers")
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
    """
    counters = counters or {}
    board: dict[UUID, Characteristics] = {}
    for state in permanents:
        board[state.id] = printed_characteristics(state, counters.get(state.id))

    all_effects = list(effects) + _counter_effects(board)
    journal = Journal()
    started: set[object] = set()

    for layer in Layer:
        if layer is Layer.TYPE:
            # Asked of the board as layers 1-3 left it: a copy or text effect
            # decides whether an object has changeling by now (CR 604.3a).
            all_effects += _changeling_effects(board)
        for sublayer in _sublayers_of(layer):
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


# --------------------------------------------------------------------------
# Selectors and modifications: the vocabulary the registry is written in
# --------------------------------------------------------------------------


def _only(card_id: UUID) -> Selector:
    return Only(card_id=card_id)


def only_this_incarnation(permanent: CardState, stamp: UUID) -> Selector:
    """Like `_only`, but also refuses CR 400.7's "new object" - same `id`, but
    a permanent that left its zone and came back since `stamp` was taken.

    CR 611.2c fixes "the set of objects it affects ... when that continuous
    effect begins", and CR 400.7 says the thing that comes back from the
    graveyard is not in that set: "An object that moves from one zone to
    another becomes a new object with no memory of, or relation to, its
    previous existence." A Giant Growth on a Bear that then dies and is
    returned this turn was pumping the returned Bear while these builders used
    `_only`, because `CardState.id` is stable across the move and nothing else
    was being asked. See `OnlyThisIncarnation` for why the comparison can now
    be made against `Characteristics.zone_change_stamp` rather than a live
    `CardState`.

    It is the selector *every* target-fixed builder in this module uses, not
    only the indefinite ones - an effect with `Duration.INDEFINITE` is never
    swept away by `ContinuousEffects.end_the_turn`, so an effect scoped only to
    `card_id` would keep re-applying to whatever the same id becomes forever,
    including a permanent CR 603.7's own delayed return already sent back to
    the battlefield as a plain, unanimated land. Earthbend (CR 701.66a) is the
    first user; nothing before it created an indefinite effect on an object
    that could round-trip through another zone.
    """
    return OnlyThisIncarnation(card_id=permanent.id, stamp=stamp)


every_creature: Selector = EveryCreature()


def same_name_as(name: str) -> Selector:
    """Every creature whose name is `name` (CR 201.2a).

    "Two or more objects have the same name if they have at least one name in
    common, even if one or more of those objects have additional names. An
    object with no name doesn't have the same name as any other object" - so
    an empty name never matches, and that is the one clause worth writing out
    here, since `Characteristics.name` carries exactly one name in this model
    (nothing melded or merged exists yet) and "at least one in common" reduces
    to equality until something does.

    A *name*, not a creature type: the difference is the whole of DDR#249's
    Echoing Courage ruling. A token created by an Assembly-Worker's ability is
    named "Assembly-Worker Token" (CR 111.4 - the ability states no name, so
    the name is "its subtype(s) plus the word 'token'"), and an animated
    Mishra's Factory has gained the Assembly-Worker creature *type* while
    keeping its own name. Neither shares a name with the Assembly-Worker card,
    so neither is selected.
    """
    return SameNameAs(name=name)


def creatures_controlled_by(username: str | None) -> Selector:
    return CreaturesControlledBy(username=username)


def other_creatures_controlled_by(source_id: UUID, username: str | None) -> Selector:
    """ "Other creatures you control" - the source itself is excluded."""
    return OtherCreaturesControlledBy(source_id=source_id, username=username)


def creatures_controlled_by_opponents_of(username: str | None) -> Selector:
    """ "Creatures your opponents control" - every creature someone else controls.

    A permanent with no controller at all is nobody's, so it is not caught.
    """
    return CreaturesControlledByOpponentsOf(username=username)


def lands_controlled_by(username: str | None) -> Selector:
    return LandsControlledBy(username=username)


#: Every land without the basic supertype (CR 205.4c).
nonbasic_lands: Selector = NonbasicLands()

every_land: Selector = EveryLand()


def other_non_aura_enchantments(source_id: UUID) -> Selector:
    return OtherNonAuraEnchantments(source_id=source_id)


def qualified_creatures(
    source_id: UUID,
    username: str | None,
    *,
    other: bool = False,
    opponents: bool = False,
    without_color: Color | None = None,
    land: bool = False,
    also_artifact: bool = False,
    tokens: bool = False,
    gate_card_type: Type | None = None,
    gate_threshold: int = 0,
    nontoken: bool = False,
    legendary: bool | None = None,
    of_chosen_color: bool = False,
    chosen_color: Color | None = None,
) -> Selector:
    """ "[Other] [non<colour>] [[non]legendary] [nontoken] [land|artifact]
    creature[ token]s [you control|your opponents control] [of the chosen
    color]" - the anthem subject with the qualifiers the pool actually prints,
    composed one predicate at a time.

    Each qualifier is a plain question about the *computed* characteristics,
    which is what makes it correct rather than merely convenient:

    - `other` excludes the source itself. Angel of Jubilation's "Other nonblack
      creatures you control" leaves the white Angel out of its own anthem by
      identity, not by colour.
    - `without_color` is the printed "nonblack" (CR 105.2: "An object can be
      one or more of the five colors, or it can be no color at all"), so a
      colourless creature is nonblack too, and a creature that *became* black
      in layer 5 (CR 613.1e) is excluded when layer 6 or layer 7 asks - the
      board this selector reads has already had layer 5 applied.
    - `land` is the "land creatures" of Aang, Destined Savior: both card types
      at once (CR 205.2b: "Some objects have more than one card type ... Such
      objects satisfy the criteria for any effect that applies to any of their
      card types"), read off the board so a land animated in layer 4 counts.
    - `tokens` is Caretaker's Talent's "Creature tokens you control"
      (CR 111.1: "A token is a marker used to represent any permanent that
      isn't represented by a card"), which rides on `Characteristics.is_token`
      for the same reason `permanents_controlled_by`'s `nontoken` does.
      `nontoken` is its negation (Always Watching's "Nontoken creatures you
      control"; Mirror Box's "Each nontoken creature you control").
    - `legendary` is the supertype (CR 205.4d): Mirror Box's "Each legendary
      creature you control", Arvad the Cursed's "Other legendary creatures
      you control", and `False` for a printed "nonlegendary".
    - `of_chosen_color` is Caged Sun's "Creatures you control of the chosen
      color": `chosen_color` is the colour recorded on the source as it
      entered (CR 614.12a), fixed for as long as that object stays on the
      battlefield, while the creature's own colour is asked of the computed
      board (CR 105.2) exactly as `without_color` is.

    `gate_card_type`/`gate_threshold` are the whole-board "as long as you
    control N or more <card type>s" condition a printed "as long as ..."
    clause puts in front of the anthem (Fecund Greenshell's ten lands). They
    belong here rather than in a `Duration`: a static ability's effect "isn't
    'locked in'; it applies at any given moment to whatever its text
    indicates" (CR 611.3a), so the count is taken from the board every time
    CR 613.5 recomputes it and the anthem switches itself off the moment a
    land leaves.
    """
    return QualifiedCreatures(
        source_id=source_id,
        username=username,
        other=other,
        opponents=opponents,
        without_color=without_color,
        land=land,
        also_artifact=also_artifact,
        tokens=tokens,
        gate_card_type=gate_card_type,
        gate_threshold=gate_threshold,
        nontoken=nontoken,
        legendary=legendary,
        of_chosen_color=of_chosen_color,
        chosen_color=chosen_color,
    )


def self_if_controls(
    card_id: UUID,
    username: str | None,
    *,
    card_type: Type | None = None,
    subtype: str | None = None,
    color: Color | None = None,
    controlled_by: Literal["you", "any", "opponent"] = "you",
) -> Selector:
    """ "This creature has vigilance as long as you control a Jace
    planeswalker." - see `SelfIfControls` for the board condition."""
    return SelfIfControls(
        card_id=card_id,
        username=username,
        card_type=card_type,
        subtype=subtype,
        color=color,
        controlled_by=controlled_by,
    )


def creatures_controlled_by_toughness_exceeds_power(username: str | None) -> Selector:
    """Ghalta the Immovable's "with toughness greater than its power" gate -
    see `CreaturesControlledByWhereToughnessExceedsPower`."""
    return CreaturesControlledByWhereToughnessExceedsPower(username=username)


def creatures_controlled_by_power_or_toughness_at_most(
    username: str | None, threshold: int
) -> Selector:
    """Tetsuko Umezawa, Fugitive's "with power or toughness N or less" gate -
    see `CreaturesControlledByWherePowerOrToughnessAtMost`."""
    return CreaturesControlledByWherePowerOrToughnessAtMost(username=username, threshold=threshold)


def self_if_power_negative(card_id: UUID) -> Selector:
    """Loot, the Anomaly's "if [its] power is negative" gate - see
    `SelfIfPowerNegative`."""
    return SelfIfPowerNegative(card_id=card_id)


def all_permanents_controlled_by(username: str | None, *, nonland: bool = False) -> Selector:
    """ "Each [nonland] permanent you control" - Leyline of the Guildpact's
    subject. Every object on the battlefield is a permanent (CR 403.3), so the
    only question left is CR 205.2a's land card type, asked of the computed
    board so a permanent that became a land in layer 4 (CR 613.1d) drops out
    before layer 5 (CR 613.1e) reads this.
    """
    return AllPermanentsControlledBy(username=username, nonland=nonland)


def permanents_controlled_by(
    username: str | None, card_type: Type, *, nontoken: bool = False
) -> Selector:
    """ "[Nontoken] <card type>s you control" (CR 205.2a) - Toph, the First
    Metalbender's board-wide layer 4 grant picks its subject this way.

    `nontoken` reads `Characteristics.is_token`, which is why that field
    travels on the board at all: CR 111.1's token/card distinction is not a
    characteristic, and a `Selector` is handed nothing else.
    """
    return PermanentsControlledBy(username=username, card_type=card_type, nontoken=nontoken)


def creatures_controlled_by_with_subtype(
    username: str | None, subtypes: Sequence[str], *, other_than: UUID | None = None
) -> Selector:
    """ "[Other] <subtype>s you control" / "each other creature you control
    that's a Cat, Elemental, ... " - an anthem over a filtered subset of the
    team (CR 611.3's static ability, applied in whichever layer its own effect
    belongs to).

    Any one of `subtypes` is enough: Kaheera's five-way list is an "or", and a
    single-subtype anthem (Stormscale Scion's Dragons) is the same shape with a
    one-item list. Read against the subtypes on the *computed* board, so a
    creature that gained the subtype in layer 4 is included (CR 613.5).
    """
    return CreaturesControlledByWithSubtype(
        username=username, subtypes=tuple(subtypes), other_than=other_than
    )


def creatures_controlled_by_with_color(username: str | None, color: Color) -> Selector:
    """ "Each creature you control ... if it's <colour>" - Scion of Draco's
    per-object condition, judged against the colours the board says the
    creature has when layer 6 runs, which is after layer 5 (CR 613.1e, CR
    613.1f) and so already includes any colour-changing effect.
    """
    return CreaturesControlledByWithColor(username=username, color=color)


def permanents_controlled_by_with_counters(username: str | None) -> Selector:
    """ "Permanents you control with counters on them" (Innkeeper's Talent's
    level-2 chapter). CR 122.1's counters are state, not characteristics, and
    ride on `Characteristics.counters` for exactly this kind of read; a counter
    recorded with a count of zero is no counter at all.
    """
    return PermanentsControlledByWithCounters(username=username)


def creatures_controlled_by_with_counter(
    username: str | None,
    counter_kind: str,
    *,
    other_than: UUID | None = None,
) -> Selector:
    """ "Each [other] creature you control with a[n] <counter kind> counter on
    it" (Gallia, the Merrymaker; Vigorbloom Vanguard) - the counter-gated twin
    of `creatures_controlled_by_with_subtype`, narrowed to one named counter
    kind and to creatures only.
    """
    return PermanentsControlledByWithCounters(
        username=username,
        counter_kind=counter_kind,
        creatures_only=True,
        other_than=other_than,
    )


#: Layer 6 removal (CR 613.1f).
lose_all_abilities: Modification = LoseAllAbilities()


def grant_ability(text: str) -> Modification:
    """Layer 6 addition (CR 613.1f)."""
    return GrantAbility(text=text)


def grant_ability_instance(text: str) -> Modification:
    """Layer 6 addition (CR 613.1f) that does *not* deduplicate.

    `grant_ability`'s dedupe is right for the keywords whose rules say multiple
    instances are redundant - CR 702.3c for defender, CR 702.18b for shroud -
    and wrong for the ones whose rules say the opposite or say nothing at all.
    Ward is the second kind: CR 702.21a makes it a triggered ability and prints
    no redundancy clause, and CR 113.2c's "An object may have multiple
    abilities" is then the whole of it, so two sources granting ward {1} give
    the permanent two independent triggers rather than one.
    """
    return GrantAbilityInstance(text=text)


def add_type(card_type: Type) -> Modification:
    """Layer 4: gain a card type on top of the ones already there (CR 205.1b)."""
    return AddType(card_type=card_type)


def add_subtype(subtype: str, mana_ability: str | None = None) -> Modification:
    """Layer 4: gain a land type "in addition to" the ones already there.

    A land with a basic land type has the matching mana ability intrinsically
    (CR 305.6), so the ability comes along with the type. This is what makes
    Urborg turn everything into a black source.
    """
    return AddSubtype(subtype=subtype, mana_ability=mana_ability)


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


#: Layer 4: become every basic land type in addition to the others (CR 613.1d).
#:
#: Dryad of the Ilysian Grove. "In addition to" keeps whatever land types were
#: already there, and each basic type gained brings its intrinsic mana ability
#: with it (CR 305.6) - which is why a Dryad turns every land into a source of
#: all five colours. It is *not* CR 305.7's "sets a land's subtype", so nothing
#: is stripped.
add_basic_land_types: Modification = AddBasicLandTypes()


def set_basic_land_type(subtype: str, mana_ability: str) -> Modification:
    """Layer 4: become a basic land type, losing the old ones (CR 305.7).

    "If an effect sets a land's subtype to one or more of the basic land types,
    the land no longer has its old land type. It loses all abilities generated
    from its rules text, its old land types, and any copy effects..." - which is
    why Blood Moon is removal as much as it is a type change.

    Limitation: every subtype is replaced, which is right for a plain land and
    wrong for a land creature, whose creature types should survive.
    """
    return SetBasicLandType(subtype=subtype, mana_ability=mana_ability)


def set_colors(*colors: Color) -> Modification:
    """Layer 5 (CR 613.1e)."""
    return SetColors(colors=tuple(colors))


def set_controller(username: str) -> Modification:
    """Layer 2 (CR 613.1b)."""
    return SetController(username=username)


def replace_text(old: str, new: str) -> Modification:
    """Layer 3, word for word (CR 612.1, CR 612.2)."""
    return ReplaceText(old=old, new=new)


def set_power_toughness(power: int, toughness: int) -> Modification:
    """Sublayer 7b (CR 613.4b)."""
    return SetPowerToughness(power=power, toughness=toughness)


#: Sublayer 7b, where the value is read off the object (CR 613.4b).
set_power_toughness_to_mana_value: Modification = SetPowerToughnessToManaValue()


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
    return DefinePowerToughness(count=count, power=power, toughness=toughness)


def define_power(count: Count, power: int = 0) -> Modification:
    """Sublayer 7a, power only (CR 613.4a).

    Some CDAs define only one half - Nighthawk Scavenger's printed toughness is
    a plain `3` (CR 208.1), not a `*`, so only its power box carries the ability
    (CR 208.2a). `define_power_toughness` cannot express that: it always
    overwrites both halves, which would erase a real printed toughness that no
    ability ever named. This leaves toughness exactly as layers 1-6 left it.
    """
    return DefinePower(count=count, power=power)


def modify_power_toughness(power: int, toughness: int) -> Modification:
    """Sublayer 7c (CR 613.4c). Adds; never sets.

    A creature with no value yet for its power counts as 0 (CR 208.5), which is
    what lets a pump land on a `*` whose CDA has been removed.
    """
    return ModifyPowerToughness(power=power, toughness=toughness)


def modify_power_toughness_per(count: Count, power: int, toughness: int) -> Modification:
    """Sublayer 7c where the size of the pump is counted on the board (CR 613.4c).

    Relentless Rats: "+1/+1 for each other creature on the battlefield named
    Relentless Rats". Counted against the board as it stands in 7c, so a Rat
    that stopped being a creature earlier in the layers is not counted.
    """
    return ModifyPowerToughnessPer(count=count, power=power, toughness=toughness)


def count_other_creatures_named(name: str, *, controlled_by_source: bool = False) -> Count:
    """How many *other* creatures on the board have this name.

    `controlled_by_source=True` for Seven Dwarves' own "you control" -
    Relentless Rats' "on the battlefield" leaves the default, unscoped.
    """
    return CountOtherCreaturesNamed(name=name, controlled_by_source=controlled_by_source)


def count_lands_controlled_by(username: str | None) -> Count:
    return CountLandsControlledBy(username=username)


def count_permanents_controlled_by(username: str | None, card_type: Type) -> Count:
    """How many permanents of `card_type` a player controls (CR 205.2a).

    The Urza's Saga Construct token's own "gets +1/+1 for each artifact you
    control" is what this exists for - `count_lands_controlled_by`'s sibling,
    generalised past lands to any of the fifteen card types.
    """
    return CountPermanentsControlledBy(username=username, card_type=card_type)


def count_card_types(cards: Iterable[CardState]) -> int:
    """How many distinct card types are among these cards (CR 300.1).

    Tarmogoyf's number. The card types are the fifteen CR 300.1 lists; a card
    with two of them - an artifact creature - counts for both, and duplicates
    across cards count once.
    """
    types: set[Type] = set()
    for state in cards:
        types.update(state.types)
    return len(types)


#: CR 110.4a: "The term 'permanent card' is used to refer to a card that could
#: be put onto the battlefield. Specifically, it means an artifact, battle,
#: creature, enchantment, land, or planeswalker card." Descend's own count
#: (CR 700.11, and the "descend 4"/"descend 8" ability words, CR 207.2c).
_PERMANENT_CARD_TYPES = frozenset(
    {Type.ARTIFACT, Type.BATTLE, Type.CREATURE, Type.ENCHANTMENT, Type.LAND, Type.PLANESWALKER}
)


def count_permanent_cards(cards: Iterable[CardState]) -> int:
    """How many of `cards` are permanent cards (CR 110.4a).

    Descend's own count: "the number of permanent cards put into [a player's]
    graveyard" (CR 700.11) is a *per-turn event* count (`Game.descend_count`),
    but the "descend 4"/"descend 8" ability words (Basking Capybara, Akawalli,
    the Seething Tower) ask a different, simpler question - "there are N or
    more permanent cards in your graveyard" *right now* - a live count of the
    graveyard's current contents, the same "no stored state, recomputed every
    time the board is computed" shape `count_card_types` already answers for
    delirium.
    """
    return sum(1 for state in cards if _PERMANENT_CARD_TYPES.intersection(state.types))


#: Sublayer 7d (CR 613.4d).
#:
#: "Such effects take the value of power and apply it to the creature's
#: toughness, and take the value of toughness and apply it to the creature's
#: power" - the values as they stand at 7d, after 7a through 7c.
switch_power_toughness: Modification = SwitchPowerToughness()


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
#: resolved. "target `<adjective>` creature" (Psychotic Fury's own "target
#: **multicolored** creature") takes one optional qualifying word between
#: "target" and "creature" the same way `machines/effects.py`'s own
#: `_CONTINUOUS_PUMP_OR_KEYWORD_RE` does - this parser never re-derives who
#: was legally targeted (that already happened at CR 601.2c announcement,
#: `machines/targeting.py`'s job), it only has to recognise which *shape* of
#: sentence this is, so admitting the adjective costs nothing. "this
#: permanent" (CR 700.7) is `effects._self_normalized_effect_text`'s own
#: stand-in for a self-reference spelled out as the card's literal printed
#: name - Ruby, Daring Tracker's "Ruby gets +2/+2 until end of turn." - which
#: is why it is read here interchangeably with "this creature" rather than as
#: a separate, narrower case.
#: The noun a "target"/"another target" subject may carry - a bare
#: "creature"/"permanent", or the "creature or planeswalker" compound this
#: pool's own post-War-of-the-Spark cards print as often as the bare noun
#: (Liliana the Faultless's "another target creature or planeswalker you
#: control gains hexproof until end of turn.").
_SUBJECT_NOUN = r"(?:creature or planeswalker|creature|permanent)"
#: "Up to one target `<noun>`" (CR 115.6a: choosing zero or one of the
#: targets an instruction offers) - Liliana, the Last Hope's own "Up to one
#: target creature gets -2/-1 until your next turn." and Garruk, Veiled
#: Butcher's identically shaped "+2". `resolve_targets` has already reduced
#: this to whatever CR 601.2c/602.2b legally left, exactly as the plain
#: "target `<noun>`" case does - the prefix costs this parser nothing beyond
#: recognising the sentence, same reasoning as the adjective slot below.
_UP_TO_ONE_PREFIX = r"(?:up to one )?"
#: The qualifier a "target"/"another target"/plural-target subject may carry
#: between "target" and its noun - a single bare word (Psychotic Fury's own
#: "target **multicolored** creature"), a hyphenated one-word creature type
#: (CR 205.3m, looked up this session: "Assembly-Worker" is one word, not
#: two, and hyphenated), or the rule's one genuine two-word creature type,
#: "Time Lord" (Tegan Jovanka's own "target **attacking historic** creature"
#: is two adjectives, not a creature type, but the same shape). Lazy, so it
#: never reaches past the qualifier into the noun, "you control", or a verb
#: that happens to also be lowercase words.
_QUALIFIER = r"(?: [a-z][a-z-]*)*?"
#: The controller clause a "target"/"another target" subject may carry after
#: its noun - "you control" (Liliana the Faultless's own shape above) or "an
#: opponent controls" (Deepwater Hypnotist's own Inspired trigger: "target
#: creature an opponent controls gets -3/-0 until end of turn."). Same
#: reasoning as `_QUALIFIER`: this parser never re-derives who was legally
#: targeted, it only has to recognise the shape, so admitting the second
#: possessive costs nothing.
_CONTROLLER_CLAUSE = r"(?: you control| an opponent controls)?"
_SUBJECT = (
    rf"(?:{_UP_TO_ONE_PREFIX}target{_QUALIFIER} {_SUBJECT_NOUN}{_CONTROLLER_CLAUSE}"
    rf"|this creature|this permanent"
    rf"|another target{_QUALIFIER} {_SUBJECT_NOUN}{_CONTROLLER_CLAUSE})"
)

#: A plural target subject - "up to two target creatures" (Dauntless
#: Onslaught's own CR 115.6 shape), "up to 2 target attacking creatures" (a
#: reflexive ability's count written in as a digit, Swashbuckler
#: Extraordinaire, Campsite Cuisine), or "any number of target creatures"
#: (CR 107.1c's own "any positive number or zero", Aerial Formation's and
#: Launch the Fleet's shared strive template) - read with the plural verb
#: ("get", "each get", "gain"). CR 601.2c/603.3d already fixed how many and
#: which were targeted; the builders below apply to every resolved target.
_PLURAL_TARGET_SUBJECT = (
    rf"(?:(?:up to )?(?:\d+|{COUNT})|any number of) target{_QUALIFIER} creatures"
)
_PLURAL_PUMP_SUBJECT = rf"{_PLURAL_TARGET_SUBJECT}(?: each)?"

#: Xenagos, God of Revels' own reversed order: "another target creature you
#: control **gains haste and gets** +X/+X until end of turn" - the keyword
#: comes first, not last, so the two verb phrases need their own branch
#: rather than the forward "gets ... and gains ..." shape's trailing
#: optional keyword. Both branches feed the same builder either way.
#: `power`/`toughness` (or the reversed order's own `power2`/`toughness2`)
#: read `x` as well as a literal number - CR 107.3a's X, evaluated through
#: `where_x_pattern`'s tail rather than a fixed digit, for Xenagos' own
#: "where X is that creature's power". The forward shape's keyword may be a
#: list ("gains trample and indestructible"), split by
#: `_split_and_validate_keywords`.
_PUMP_RE = re.compile(
    rf"^(?:{_SUBJECT}|{_PLURAL_PUMP_SUBJECT}) (?:"
    rf"gets? (?P<power>[+-](?:{COUNT}|x))/(?P<toughness>[+-](?:{COUNT}|x))"
    rf"(?: and gains? (?P<keyword>[a-z ,]+?))?"
    rf"|gains (?P<keyword2>[a-z ]+) and gets? "
    rf"(?P<power2>[+-](?:{COUNT}|x))/(?P<toughness2>[+-](?:{COUNT}|x))"
    # "until your next turn" is CR 611.2a's same "lasts as long as stated"
    # duration as the ordinary "until end of turn", just a longer stated
    # span - Liliana, the Last Hope's own "Up to one target creature gets
    # -2/-1 until your next turn." is the identical pump shape with the
    # longer duration, not a different sentence.
    rf") (?P<duration>until end of turn|until your next turn){where_x_pattern()}\.?$",
    re.IGNORECASE,
)

#: "that creature's power" - Xenagos, God of Revels' own X definition, read
#: per target off `CardState.power` (CR 613.5's computed value) at the
#: moment this ability resolves (CR 611.2c fixes the magnitude then, so this
#: is a one-time snapshot, not a live recompute that would let the pump
#: retroactively inflate what defined it).
_THAT_CREATURES_POWER_RE = re.compile(r"^that creature'?s power$", re.IGNORECASE)

#: "Target creature or planeswalker an opponent controls that's red or white
#: loses all abilities until end of turn." (Flourishing Grapple) - CR 613.1f's
#: ability-removing effect, targeted rather than the "Enchanted/Equipped
#: creature" or "All creatures"/"Other creatures" shapes already read above.
#: `_SUBJECT` itself is not reused: it admits only a single adjective in
#: front of one noun, and this subject is a full "target ..." phrase (a type
#: list, a controller clause, a colour clause) the same grammar a spell's own
#: `_targets_understood` already vets independently - re-deriving that
#: grammar here would only be able to disagree with it, never improve on it.
_TARGETED_LOSES_ALL_ABILITIES_RE = re.compile(
    r"^target .+? loses all abilities until end of turn\.?$", re.IGNORECASE
)

#: Echoing Courage: "Target creature and all other creatures with the same name
#: as that creature get +2/+2 until end of turn." A sibling of `_PUMP_RE` and
#: not a widening of it, because the *subject* is two groups joined by a bare
#: "and" - the target, plus a set defined by CR 201.2a's "the same name" - and
#: `_SUBJECT` deliberately describes only the first of them. The optional
#: adjective ("target **legendary** creature") is admitted for the same reason
#: `_SUBJECT` admits it: this parser recognises the shape, it does not
#: re-derive what was legally targeted.
_TARGET_AND_SAME_NAME_PUMP_RE = re.compile(
    rf"^target{_QUALIFIER} creature and all other creatures with the same name as "
    r"that creature get (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) until end of turn\.?$",
    re.IGNORECASE,
)

#: Fiend Artisan: "This creature gets +1/+1 for each creature card in your
#: graveyard." No duration (CR 611.3: a static ability's own effect, unlike
#: `_PUMP_RE`'s "until end of turn" one-shot), and the magnitude is a live
#: graveyard count rather than a fixed number - `_self_pump_per_graveyard_
#: card_builder` reads `context.graveyard_of` at build time, which
#: `effects_for` recomputes every time the board is (CR 613.5), so this stays
#: current rather than freezing at whatever the graveyard held when the
#: permanent entered.
_SELF_PUMP_PER_GRAVEYARD_CARD_RE = re.compile(
    r"^this (?:creature|permanent|token) gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) "
    r"for each (?P<qualifier>[a-z]+(?:(?:,\s*| and )[a-z]+)*) cards? in your graveyard\.?$",
    re.IGNORECASE,
)

#: Dark Matter Manipulator: "This creature gets +2/+0 for every seven cards
#: in your graveyard." - the unfiltered, batched twin of the shape above:
#: "every" instead of "each", no card-type qualifier, and a batch size
#: instead of a 1:1 multiplier.
_SELF_PUMP_PER_GRAVEYARD_CARD_BATCH_RE = re.compile(
    r"^this (?:creature|permanent|token) gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) "
    r"for every (?P<batch>[a-z]+) cards? in your graveyard\.?$",
    re.IGNORECASE,
)


def _card_type_word(word: str) -> Type | None:
    """ "creature[s]" -> `Type.CREATURE` (CR 205.2a), or `None` for anything
    not one of the fifteen printed card types. The same singularisation
    `machines/effects.py::_singular_card_type` does for `count_expression`'s
    identical phrase, kept local rather than imported - `machines/effects.py`
    already imports from this module, so the reverse import would be
    circular.
    """
    singular = word[:-1] if word.lower().endswith("s") else word
    try:
        return Type(singular.lower())
    except ValueError:
        return None


#: The one Latin-plural subtype irregularity in CR 205.3's creature-subtype
#: list that no suffix rule covers - "Fungus" (singular) / "Fungi" (plural),
#: the way it is genuinely printed (The Mycotyrant: "... Fungi and/or
#: Saprolings"). Everything else in the subtype vocabulary pluralises with a
#: bare trailing "s" ("Saproling" -> "Saprolings"), which `_singular_subtype_
#: word` strips directly.
_IRREGULAR_SUBTYPE_PLURALS = {"fungi": "fungus"}


def _singular_subtype_word(word: str) -> str | None:
    """A printed subtype word, singular and lower-cased, or `None` if it
    names no subtype `subtype_vocabulary` recognises - the same fail-closed
    shape `_card_type_word` holds itself to for card types.

    `machines/effects.py::_singular_subtype_for_count_expression` reads the
    identical phrase for a resolving effect's own "number of `<subtype>` you
    control"; kept local rather than imported for the same reverse-import
    reason `_card_type_word`'s own docstring gives.
    """
    lowered = word.lower()
    vocabulary = subtype_vocabulary()
    candidates = [
        _IRREGULAR_SUBTYPE_PLURALS.get(lowered, lowered),
        lowered.removesuffix("s"),
    ]
    if lowered.endswith("ies"):
        # "Allies" -> "ally" (Earthen Ally's "each color among Allies").
        candidates.append(lowered.removesuffix("ies") + "y")
    return next((candidate for candidate in candidates if candidate in vocabulary), None)


#: A controller-relative board count's factory: the controller is only known
#: when the effect is built, so a reader hands back how to make the `Count`.
ControlledCountFactory = Callable[[str | None], "Count"]


def _controlled_count_factory(qualifier: str) -> ControlledCountFactory | None:
    """ "artifacts" / "Deserts" / "Islands" - the `<qualifier>` of "for each
    `<qualifier>` you control" or "the number of `<qualifier>` you control" -
    as a factory for the `Count` of that many permanents a player controls: a
    CR 205.2a card type first, else a CR 205.3 subtype `subtype_vocabulary`
    knows. `None` for anything else, so the caller fails closed.
    """
    card_type = _card_type_word(qualifier)
    if card_type is not None:
        return lambda username: count_permanents_controlled_by(username, card_type)
    subtype = _singular_subtype_word(qualifier)
    if subtype is None:
        return None
    return lambda username: CountPermanentsWithSubtypeControlledBy(
        username=username, subtype=subtype
    )


def _self_pump_per_graveyard_card_builder(
    power: int, toughness: int, card_types: Sequence[Type]
) -> EffectBuilder:
    """Fiend Artisan: "This creature gets +1/+1 for each creature card in
    your graveyard." Winter, Tormented Loner's and-joined list, "+1/+0 for
    each creature and planeswalker card in your graveyard", is the same
    count with more than one card type qualifying a graveyard card for it
    (CR 205.2b: an object satisfies a criterion that applies to any one of
    its card types, so a card counts once even if it is more than one of
    the named types).

    Sublayer 7c (CR 613.4c: "modify power and/or toughness ... don't set") -
    unlike Tarmogoyf's or Boneyard Wurm's characteristic-defining "power and
    toughness are equal to" shape (sublayer 7a, CR 613.4a), this *adds* to the
    printed 1/1 rather than replacing it. No duration (CR 611.3: a static
    ability's effect lasts exactly as long as its source has it), so a
    permanent with an empty graveyard correctly reads as its own printed 1/1,
    not 0/0. The count is read off `context.graveyard_of` at build time, the
    same live-recompute trick Boneyard Wurm's row uses: `effects_for` rebuilds
    this every time the board is computed (CR 613.5), so the bonus tracks the
    controller's graveyard as it grows and shrinks rather than freezing it.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        count = sum(
            1
            for state in context.graveyard_of(source.controller)
            if any(card_type in state.types for card_type in card_types)
        )
        if count == 0:
            return []
        amount_power, amount_toughness = power * count, toughness * count
        kinds = "/".join(card_type.value for card_type in card_types)
        return [
            ContinuousEffect(
                description=(
                    f"{source.name}: {amount_power:+d}/{amount_toughness:+d} from "
                    f"{count} {kinds} card(s) in graveyard"
                ),
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=timestamp,
                source_id=source.id,
                selector=_only(source.id),
                modification=modify_power_toughness(amount_power, amount_toughness),
            )
        ]

    return builder


def _self_pump_per_graveyard_card_batch_builder(
    power: int, toughness: int, batch_size: int
) -> EffectBuilder:
    """Dark Matter Manipulator: "This creature gets +2/+0 for every seven
    cards in your graveyard." - `_self_pump_per_graveyard_card_builder`'s
    "for every N cards" twin: unfiltered by card type, and the count is a
    whole batch of `batch_size` (integer floor division: seven cards is one
    batch, thirteen is still one, fourteen is two) rather than a 1:1
    multiplier.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        batches = len(context.graveyard_of(source.controller)) // batch_size
        if batches == 0:
            return []
        amount_power, amount_toughness = power * batches, toughness * batches
        return [
            ContinuousEffect(
                description=(
                    f"{source.name}: {amount_power:+d}/{amount_toughness:+d} from "
                    f"{batches} batch(es) of {batch_size} cards in graveyard"
                ),
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=timestamp,
                source_id=source.id,
                selector=_only(source.id),
                modification=modify_power_toughness(amount_power, amount_toughness),
            )
        ]

    return builder


#: The Construct token Urza's Saga's chapter II grants: "This token gets
#: +1/+1 for each artifact you control." A live board count, not a
#: graveyard one (`_SELF_PUMP_PER_GRAVEYARD_CARD_RE`'s own sibling) - the
#: subject is "this token" rather than "this creature", since that is what
#: `TokenDefinition.rules_text` prints verbatim (CR 111.3) onto the token's
#: own synthesised `Card.oracle_text`, read by this module's ordinary static-
#: ability sweep the same as any printed creature's would be.
_SELF_PUMP_PER_CONTROLLED_PERMANENT_RE = re.compile(
    r"^this (?:creature|token|permanent) gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) for each "
    r"(?P<qualifier>[a-z]+) you control\.?$",
    re.IGNORECASE,
)

#: "This creature gets +1/+1 for each color among other legendary permanents
#: you control." (Sisay, Weatherlight Captain, her name already rewritten to
#: "this permanent"), "This creature gets +1/+0 for each color among Allies you
#: control." (Earthen Ally) - a count of CR 105.1's colors among a group of the
#: controller's permanents rather than of the permanents themselves.
_SELF_PUMP_PER_COLOR_AMONG_RE = re.compile(
    r"^this (?:creature|token|permanent) gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) for each "
    r"colou?r among (?P<other>other )?(?P<qualifier>[a-z]+(?: [a-z]+)?) you control\.?$",
    re.IGNORECASE,
)

#: The supertype words a color-among group may open with (CR 205.4a).
_SUPERTYPE_WORDS: dict[str, Supertype] = {member.value.lower(): member for member in Supertype}


def _colors_among_count_factory(
    qualifier: str, *, excludes_self: bool
) -> ControlledCountFactory | None:
    """ "legendary permanents" / "permanents" / "Allies" / "creatures" - the
    group `_SELF_PUMP_PER_COLOR_AMONG_RE` counts colors among, as a
    `CountColorsAmongControlledBy` factory: an optional supertype word, then
    "permanents" (every permanent), a card type, or a subtype. `None` for
    anything else."""
    words = qualifier.lower().split()
    supertype = _SUPERTYPE_WORDS.get(words[0]) if len(words) == 2 else None
    if len(words) == 2 and supertype is None:
        return None
    noun = words[-1]
    card_type: Type | None = None
    subtype: str | None = None
    if noun != "permanents":
        card_type = _card_type_word(noun)
        if card_type is None:
            subtype = _singular_subtype_word(noun)
            if subtype is None:
                return None
    return lambda username: CountColorsAmongControlledBy(
        username=username,
        excludes_self=excludes_self,
        card_type=card_type,
        subtype=subtype,
        supertype=supertype,
    )


def _self_pump_per_controlled_permanent_builder(
    power: int, toughness: int, qualifier: str, count: ControlledCountFactory
) -> EffectBuilder:
    """`_SELF_PUMP_PER_CONTROLLED_PERMANENT_RE`'s shape - the Urza's Saga
    Construct token's own pump.

    Sublayer 7c (CR 613.4c), the same "modify, don't set" choice `_self_pump_
    per_graveyard_card_builder` makes for its own graveyard count, just read
    live off the board through `modify_power_toughness_per`/`count_
    permanents_controlled_by` instead of baked in at build time - either
    works for CR 613.5's "continually and automatically" recomputation, but
    reusing the live-count `Modification` here needs no `LayerContext`
    plumbing at all, since the count only ever needs the board the layer
    engine is already threading through every other `Selector`/`Modification`
    in this module.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=(
                    f"{source.name}: {power:+d}/{toughness:+d} for each {qualifier} controlled"
                ),
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=timestamp,
                source_id=source.id,
                selector=_only(source.id),
                modification=modify_power_toughness_per(count(source.controller), power, toughness),
            )
        ]

    return builder


#: "This creature gets +1/+1 for each other creature on the battlefield named
#: Relentless Rats." (Relentless Rats) and "This creature gets +1/+1 for each
#: other creature named Seven Dwarves you control." (Seven Dwarves) - the same
#: self-counting-by-name shape `count_other_creatures_named` already reads
#: generally; only the card-name-keyed `LAYER_EFFECTS` row this replaces
#: pinned it to "Relentless Rats" specifically. By the time this dispatcher
#: sees the sentence, `self_normalized_effect_text` (CR 201.5) has already
#: rewritten the card's own printed name to "this permanent" wherever it
#: appears in its own text - both cards name only themselves, so `name` reads
#: literally as "this permanent" for both, resolved back to the *source's own
#: live name* inside `builder` (a DFC or copy effect can change it after this
#: sentence was parsed, so this reads it at build time, not parse time) rather
#: than the captured string itself. A future card whose template somehow named
#: a *different* creature is still covered: only a captured "this permanent"
#: gets the live-name treatment. "on the battlefield" and "you control" are
#: both optional - Relentless Rats prints the first, Seven Dwarves the
#: second, neither prints both.
_SELF_PUMP_PER_OTHER_CREATURE_NAMED_RE = re.compile(
    r"^this creature gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) for each other creature "
    r"(?:on the battlefield )?named (?P<name>.+?)(?P<you_control> you control)?\.?$",
    re.IGNORECASE,
)


def _self_pump_per_other_creature_named_builder(
    power: int, toughness: int, name: str, controlled_by_source: bool, line: str
) -> EffectBuilder:
    """`_SELF_PUMP_PER_OTHER_CREATURE_NAMED_RE`'s shape - Relentless Rats and
    Seven Dwarves both print this self-counting pump.

    Sublayer 7c (CR 613.4c), the same "modify, don't set" choice `_self_pump_
    per_controlled_permanent_builder` makes for its own live board count -
    `count_other_creatures_named` is `modify_power_toughness_per`'s same
    `Count` machinery, counting by printed name (CR 201.4) instead of by card
    type, scoped to the source's own controller when the sentence prints "you
    control" (Seven Dwarves) and left unscoped when it prints "on the
    battlefield" (Relentless Rats) instead. A static ability's effect (CR
    611.3), switched off the moment the source loses the ability (CR 613.6) -
    `source_ability` is the printed sentence layer 6 removal matches on,
    `_source_line_for` because `line` may already have had its ability word
    or self-normalized name taken off.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        resolved_name = source.name if name.strip().lower() == "this permanent" else name
        return [
            ContinuousEffect(
                description=(
                    f"{source.name}: {power:+d}/{toughness:+d} for each other creature named "
                    f"{resolved_name}"
                ),
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=_only(source.id),
                modification=modify_power_toughness_per(
                    count_other_creatures_named(
                        resolved_name, controlled_by_source=controlled_by_source
                    ),
                    power,
                    toughness,
                ),
            )
        ]

    return builder


#: "This land becomes a copy of target nontoken artifact you control with
#: mana value X." (The Mycosynth Gardens, indefinite) and "This land becomes
#: a copy of target permanent card in your graveyard until end of turn."
#: (Shifting Woodland) - CR 707.4: "Some effects cause a permanent that's
#: copying a permanent to copy a different object while remaining on the
#: battlefield" is exactly this shape, an already-on-the-battlefield object
#: turning into a copy rather than one entering as one (CR 614.1c's
#: `ENTERS_AS_COPY`, a different, still-unbuilt shape - see `docs/engine-
#: coverage.md`). `quality` is read but not used to build the effect - the
#: target has already been checked against it by `machines/targeting.py`
#: before `create_continuous_effect_of_ability` ever calls this builder - so
#: the group only has to be *present*, wide enough to swallow whatever
#: restriction the card prints ("nontoken artifact you control with mana
#: value X", "permanent card in your graveyard") without this shape needing
#: to parse it a second time.
_BECOME_A_COPY_RE = re.compile(
    r"^this (?:land|permanent|artifact|creature) becomes a copy of target "
    r"(?P<quality>.+?)(?P<until_eot> until end of turn)?\.?$",
    re.IGNORECASE,
)


def _become_a_copy_builder(
    *,
    until_eot: bool,
    name_override: str | None = None,
    power_override: int | None = None,
    toughness_override: int | None = None,
    added_types: Sequence[Type] = (),
    added_subtypes: Sequence[str] = (),
    added_abilities: Sequence[str] = (),
    copiable_values: Characteristics | None = None,
) -> EffectBuilder:
    """`_BECOME_A_COPY_RE`'s shape.

    CR 707.2: "the copy acquires the copiable values of the original
    object's characteristics" - name, mana value, supertypes, card types,
    subtypes, colors, abilities (CR 707.2a: color and abilities are
    themselves derived from mana cost/color indicator and rules text, so
    copying those is copying this), and power/toughness. Read once, off
    `targets[0]` at the moment this builder runs (CR 613.7b: a resolution
    effect is built once, when it is created) via `printed_characteristics` -
    the same "printed, pre-layer-1" values that function already gives a
    permanent's own layer 2 a starting point from, which is the ordinary
    case's copiable values (CR 707.2b: once copied, a later change to the
    *original* does not change the copy, so a frozen snapshot rather than a
    live read is correct, not merely convenient). **Known gap**: a target
    itself modified by a characteristic-defining ability or an earlier copy
    effect would have copiable values `printed_characteristics` cannot
    reconstruct (CR 707.2's "as modified by other copy effects") unless the
    caller passes `copiable_values` - the enter-as-a-copy path
    (`replacement._enters_as_copy`) does, from `copiable_characteristics`;
    the "becomes a copy of target creature" path still reads printed values.

    CR 707.4's own "remaining on the battlefield" clause is why this is not
    routed through `ENTERS_AS_COPY`'s enters-the-battlefield machinery: the
    copying object is already on the battlefield and stays there, so no
    enters/leaves trigger fires from the change (a plain continuous effect
    at layer 1 is the whole of it).

    `card_id` is deliberately left off the replacement: it is the copying
    permanent's own board identity (`CardState.id`), not one of CR 707.2's
    copiable values, and every `Selector` in this module keys off it.

    The `*_override` and `added_*` arguments are CR 707.9b's "except ..."
    modifications - Superior Spider-Man's "except his name is Superior
    Spider-Man and he's a 4/4 Spider Human Hero in addition to his other
    types", read by `machines/replacement._parse_copy_exception`. CR 707.9b:
    "Some copy effects modify a characteristic as part of the copying process.
    The final set of values for that characteristic becomes part of the
    copiable values of the copy." They are therefore written *here*, inside the
    one layer 1a effect, and not as separate effects in layers 4 and 7 - which
    would be applied after CR 613.2c had already fixed the copiable values and
    would not be copiable in turn.

    The added types and subtypes are additive (CR 205.1b: "all the object's
    prior card types, supertypes, or subtypes are retained"), which is what
    the printed "in addition to his other types" says. `added_abilities` is
    CR 707.9a's gained ability ("This ability becomes part of the copiable
    values for the copy, along with any other abilities that were copied") -
    Mockingbird's flying, Phantasmal Image's quoted trigger - appended to the
    copied ability lines, once.

    `copiable_values`, when a caller has them, replaces the printed read of
    `targets[0]`: CR 707.2's copiable values are the printed ones "as modified
    by other copy effects", which `copiable_characteristics` computes and
    `printed_characteristics` alone cannot - a Clone copying a
    Mockingbird-as-Grizzly-Bears must copy the Bird and flying too.
    """
    added_types = tuple(added_types)
    added_subtypes = tuple(added_subtypes)
    added_abilities = tuple(added_abilities)

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        if not targets:
            return []
        copied = (
            copiable_values if copiable_values is not None else printed_characteristics(targets[0])
        )
        types = copied.types + tuple(
            card_type for card_type in added_types if card_type not in copied.types
        )
        subtypes = copied.subtypes + tuple(
            subtype for subtype in added_subtypes if subtype not in copied.subtypes
        )
        modification = BecomeACopy(
            name=name_override if name_override is not None else copied.name,
            mana_value=copied.mana_value,
            supertypes=copied.supertypes,
            types=types,
            subtypes=subtypes,
            colors=copied.colors,
            abilities=copied.abilities
            + tuple(ability for ability in added_abilities if ability not in copied.abilities),
            power=power_override if power_override is not None else copied.power,
            toughness=toughness_override if toughness_override is not None else copied.toughness,
        )

        return [
            ContinuousEffect(
                description=f"{source.name} becomes a copy of {copied.name}",
                layer=Layer.COPY,
                # CR 613.2a: a copy effect is a 1a effect, applied ahead of
                # every CR 613.2b face-down modification whatever the
                # timestamps say.
                sublayer=CopySublayer.COPIABLE,
                timestamp=timestamp,
                source_id=source.id,
                selector=_only(source.id),
                modification=modification,
                duration=Duration.UNTIL_END_OF_TURN if until_eot else Duration.INDEFINITE,
            )
        ]

    return builder


#: `keywords` reads one *or more* keyword names, comma/"and"-joined the same
#: way `_INDEFINITE_KEYWORD_GRANT_RE`'s own list does (Fateshaper Aspirant's
#: "It gains vigilance and indestructible until end of turn.") - each is
#: validated separately against `_KNOWN_KEYWORDS` by `_split_and_validate_
#: keywords`, not looked up as one compound string.
_KEYWORD_GRANT_RE = re.compile(
    rf"^(?:{_SUBJECT} gains|{_PLURAL_TARGET_SUBJECT} gain) "
    r"(?P<keywords>[a-z]+(?: [a-z]+)?(?:(?:,\s*| and )[a-z]+(?: [a-z]+)?)*) "
    r"until end of turn\.?$",
    re.IGNORECASE,
)

#: The qualifier words an anthem's subject may carry, ahead of the noun:
#: "other" (the source itself excluded), a colour negation ("nonblack",
#: CR 105.2), and "land" (both card types at once, CR 205.2b). The noun itself
#: is either "creatures" or CR 111.1's "creature tokens". Every one of them is
#: optional, so the plain "creatures you control" of Glorious Anthem reads
#: through this fragment exactly as it did before it existed.
#:
#: Written as one fragment because `_ANTHEM_RE` and `_INDEFINITE_KEYWORD_GRANT_
#: RE` are the same subject with two different predicates - Angel of
#: Jubilation's "Other nonblack creatures you control get +1/+1" and Aang,
#: Destined Savior's "Land creatures you control have vigilance" would
#: otherwise need the qualifiers spelled out twice and kept in step by hand.
_SUBJECT_QUALIFIERS = (
    r"(?P<other>other )?"
    r"(?:non(?P<noncolor>white|blue|black|red|green) )?"
    r"(?P<legendary>(?:non)?legendary )?"
    r"(?P<nontoken>nontoken )?"
    r"(?:(?P<land>land )|(?P<artifact>artifact ))?"
)
#: "... of the chosen color" after the controller clause - Caged Sun's,
#: Heraldic Banner's and Hall of Triumph's subject, the colour being the one
#: the source chose as it entered (CR 614.12a).
_CHOSEN_COLOR_SUFFIX = r"(?P<chosen> of the chosen colou?r)?"
_QUALIFIED_CREATURE_SUBJECT = (
    _SUBJECT_QUALIFIERS + r"(?P<noun>creature tokens|creatures) "
    r"(?P<whose>you control|your opponents control)" + _CHOSEN_COLOR_SUFFIX
)
#: The singular twin, after "each": Mirror Box's "Each legendary creature you
#: control gets +1/+1." The same qualifier groups, so `qualifiers_from_subject`
#: reads either shape.
_EACH_QUALIFIED_CREATURE_SUBJECT = (
    r"each " + _SUBJECT_QUALIFIERS + r"(?P<noun>creature token|creature) "
    r"(?P<whose>you control|your opponents control)" + _CHOSEN_COLOR_SUFFIX
)

#: "As long as you control <number word> or more <card type>s, " - the printed
#: board condition Fecund Greenshell puts in front of its anthem. CR 604.2:
#: a static ability's effects "are active as long as the permanent with the
#: ability remains on the battlefield and has the ability", and this clause
#: narrows that further to a count taken off the board, so the anthem is asked
#: afresh on every CR 613.5 computation rather than stored with a duration.
_BOARD_COUNT_GATE_RE = re.compile(
    r"^as long as you control (?P<count>[a-z]+) or more (?P<subject>[a-z]+), (?P<rest>.+)$",
    re.IGNORECASE,
)

_ANTHEM_RE = re.compile(
    rf"^{_QUALIFIED_CREATURE_SUBJECT} get "
    r"(?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)\.?$",
    re.IGNORECASE,
)

#: `_EACH_ANTHEM_RE` with a per-object count after it - Mirror Box's "Each
#: nontoken creature you control gets +1/+1 for each other creature you
#: control with the same name as that creature." and Heroes' Podium's "Each
#: legendary creature you control gets +1/+1 for each other legendary creature
#: you control." The counted group is always "other ... creature[s] you
#: control", judged against the creature being pumped (`CountOtherCreatures
#: LikeThatOne`); layer 7c (CR 613.4c).
_EACH_ANTHEM_PER_OTHER_CREATURE_RE = re.compile(
    rf"^{_EACH_QUALIFIED_CREATURE_SUBJECT} gets "
    r"(?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) for each other "
    r"(?P<count_legendary>legendary )?creature you control"
    r"(?P<same_name> with the same name as that creature)?\.?$",
    re.IGNORECASE,
)

#: "This creature has protection from the chosen color." (Voice of All, Order
#: of the Stars) - a self grant (CR 613.1f) whose quality is the colour the
#: permanent chose as it entered (CR 614.12a), read off `CardState.choice` by
#: `_self_protection_from_chosen_color_builder`.
_SELF_PROTECTION_FROM_CHOSEN_COLOR_RE = re.compile(
    r"^this (?:creature|permanent|token) has protection from the chosen colou?r\.?$",
    re.IGNORECASE,
)

#: `_ANTHEM_RE`'s singular "each" form - Mirror Box's "Each legendary
#: creature you control gets +1/+1." Read by the same builder.
_EACH_ANTHEM_RE = re.compile(
    rf"^{_EACH_QUALIFIED_CREATURE_SUBJECT} gets "
    r"(?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)\.?$",
    re.IGNORECASE,
)

#: "Creatures you control get +0/+1 for each Gate you control and have
#: vigilance." (Hold the Gates) - `_ANTHEM_RE`'s pump scaled by a live count of
#: a card type or subtype the controller controls (CR 611.3a: counted afresh
#: on every CR 613.5 computation), with `_ANTHEM_AND_KEYWORD_GRANT_RE`'s
#: optional keyword grant riding along.
_ANTHEM_PER_COUNT_RE = re.compile(
    rf"^{_QUALIFIED_CREATURE_SUBJECT} get "
    r"(?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) for each (?P<each>[a-z]+) you control"
    r"(?: and (?:have|has) "
    r"(?P<keywords>[a-z]+(?: [a-z]+)?(?:(?:,\s*| and )[a-z]+(?: [a-z]+)?)*))?\.?$",
    re.IGNORECASE,
)

#: "Creature tokens you control get +1/+0 and have vigilance." (Gideon's
#: Memorial) - `_ANTHEM_RE` and `_INDEFINITE_KEYWORD_GRANT_RE`'s two
#: predicates on the same qualified subject in one sentence, tried as its own
#: shape rather than splitting the sentence in two, since either half missing
#: means the "and" join was something else entirely.
_ANTHEM_AND_KEYWORD_GRANT_RE = re.compile(
    rf"^{_QUALIFIED_CREATURE_SUBJECT} get "
    r"(?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) and "
    r"(?:have|has) (?P<keywords>[a-z]+(?: [a-z]+)?(?:(?:,\s*| and )[a-z]+(?: [a-z]+)?)*)\.?$",
    re.IGNORECASE,
)

#: "[Other] creatures [you control|your opponents control] [gain <keyword(s)>
#: and ]get +N/+N until end of turn." (Violent Outburst's own "Creatures you
#: control get +1/+0 until end of turn."; Craterhoof Behemoth's "creatures you
#: control gain trample and get +X/+X until end of turn" once
#: `machines/effects.py` has already substituted a literal number for "X" -
#: see `_mass_pump_ability_effect`/`_mass_pump_spell_effect` there, which read
#: the "where X is ..." magnitude off the *live* board before this regex ever
#: sees the sentence, since this module has no `Game` to ask). CR 611.2's
#: one-shot group pump, told apart from `_ANTHEM_RE`'s CR 611.3 anthem by its
#: explicit duration (`is_resolution_layer_effect_text`'s docstring already
#: documents why an explicit duration can never be the anthem's forever-lasting
#: shape). The row `docs/engine-coverage.md` used to carry for this - "the
#: actual continuous effect for a team-wide temporary pump is still not built" -
#: is closed by this shape plus `_mass_pump_until_eot_builder` below.
#: "all creatures" (Toxic Deluge's own "-X/-X", X already substituted by the
#: caller) is added as a third subject alongside the two controller-scoped
#: ones - no `other`/`whose` group at all, since neither is read for this
#: shape (`machines/effects.py`'s `_run_mass_pump` already resolved the
#: concrete `targets` before this ever runs; see `_mass_creature_group_
#: targets`'s own "all creatures" branch).
#: A keyword list may stand alone too - "Creatures you control gain first
#: strike until end of turn." (Artifist Acumen), "creatures you control gain
#: haste until end of turn." (Ingris Stingerquill's trailing rider) - CR
#: 611.2's one-shot group *ability* grant with no power/toughness change at
#: all. `power`/`toughness` capture the pump when it follows "and get ...";
#: `power_only`/`toughness_only` capture it when there is no keyword grant in
#: front of it at all - two names for the same magnitude because `re` refuses
#: a group name used twice, and `_parse_layer_sentence` reads whichever pair
#: matched.
#: "Permanents you control" (Veil of Summer's own group half, once its
#: compound "You and permanents you control" subject is split - CR 403.3:
#: every object on the battlefield is a permanent, so this is CR 611.2's
#: mass grant over the *whole* board a player controls, not only their
#: creatures) joins the two creature-scoped subjects and "all creatures" as
#: a fourth alternative. It carries no `other`/`whose` capture of its own -
#: neither is read for it downstream, the same way neither is for "all
#: creatures" (see the note above).
#:
#: `keywords` used to be a bare comma/"and"-joined list of one- or two-word
#: items - never wide enough for CR 702.11f's "hexproof from [quality A]
#: and from [quality B]" (Veil's own "gain hexproof from blue and from
#: black"), whose "and from" is not a second keyword at all. Widened to a
#: non-greedy run of letters/commas/apostrophes/hyphens/spaces, bounded by
#: whatever the rest of the pattern needs next (an "and get ..." pump or the
#: closing "until end of turn") the same way `_split_and_validate_keywords`
#: below is already the one place a raw keyword-list string is actually
#: validated - this capture only has to find where the list *ends*, not
#: parse what is in it.
_MASS_PUMP_UNTIL_EOT_RE = re.compile(
    r"^(?:(?P<other>other )?creatures (?P<whose>you control|your opponents control)|"
    r"all creatures|permanents you control) "
    # Dawn's Truce's gift sentence: "permanents you control also gain
    # indestructible" - "also" only says it adds to what came before.
    r"(?:also )?"
    r"(?:"
    r"gain (?P<keywords>[a-z][a-z,'\- ]*?)"
    r"(?: and get (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+))?"
    # Aerie Mystics: "Creatures you control gain shroud until end of turn." -
    # the keyword-only shape, with no "get +N/+N" at all (CR 611.2's mass
    # grant is not required to carry a pump). Ingris Stingerquill's own
    # "Then creatures you control gain haste until end of turn." is the same
    # shape, one clause among several rather than the whole effect.
    # Take to the Streets' / Glistening Deluge's own second sentence: "an
    # additional" names no new rule - sublayer 7c modifications simply add
    # (CR 613.4c) - and a keyword grant may follow the pump ("get an
    # additional +1/+1 and gain vigilance").
    r"|get (?:an additional )?(?P<power_only>[+-]\d+)/(?P<toughness_only>[+-]\d+)"
    r"(?: and gain (?P<keywords_after>[a-z][a-z,'\- ]*?))?"
    r") until end of turn\.?$",
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
    rf"^{_QUALIFIED_CREATURE_SUBJECT} "
    r"(?:have|has) (?P<keywords>[a-z]+(?: [a-z]+)?(?:(?:,\s*| and )[a-z]+(?: [a-z]+)?)*)\.?$",
    re.IGNORECASE,
)

#: "During your turn, `<type> and <type>` you control have `<keyword(s)>`."
#: (Sorin, Vengeful Bloodlord: "During your turn, creatures and planeswalkers
#: you control have lifelink.") - `_QUALIFIED_CREATURE_SUBJECT`'s own noun
#: slot only ever reads "creatures"/"creature tokens", never a compound of
#: two different card types, so this is a separate shape rather than a
#: widening of it - the same reasoning that already keeps `_INDEFINITE_
#: KEYWORD_AND_PROTECTION_GRANT_RE` apart from the plain keyword grant.
_DURING_YOUR_TURN_MULTI_TYPE_KEYWORD_GRANT_RE = re.compile(
    r"^during your turn, (?P<type1>[a-z]+) and (?P<type2>[a-z]+) you control "
    r"(?:have|has) (?P<keywords>[a-z]+(?: [a-z]+)?(?:(?:,\s*| and )[a-z]+(?: [a-z]+)?)*)\.?$",
    re.IGNORECASE,
)

#: The same indefinite grant, with the list's last item being "protection from
#: <quality>[ and from <quality>]" instead of another bare keyword (Akroma's
#: Memorial: "Creatures you control have flying, first strike, vigilance,
#: trample, haste, and protection from black and from red."). CR 702.16a's
#: protection ability has no keyword name of its own - `_KNOWN_KEYWORDS` only
#: lists `machines/combat.py`'s `Keyword` vocabulary - so `_INDEFINITE_
#: KEYWORD_GRANT_RE`'s per-item cap of two words can never match the
#: multi-word "protection from black and from red" tail, and this is a
#: separate shape rather than a widening of that one. The leading keyword list
#: is optional, so "Creatures you control have protection from red." alone
#: also matches. CR 702.16g makes "protection from A and from B" two separate
#: abilities, split the same way `models/game.py`'s `protection_qualities`
#: splits an ordinary printed protection line.
_INDEFINITE_KEYWORD_AND_PROTECTION_GRANT_RE = re.compile(
    r"^(?P<other>other )?creatures (?P<whose>you control|your opponents control) "
    r"(?:have|has) (?:(?P<keywords>[a-z]+(?: [a-z]+)?(?:,\s*[a-z]+(?: [a-z]+)?)*)"
    r"(?:,)?\s+and\s+)?protection from (?P<qualities>[a-z]+(?: [a-z]+)?(?:\s+and from\s+"
    r"[a-z]+(?: [a-z]+)?)*)\.?$",
    re.IGNORECASE,
)

#: "Each creature you control with toughness greater than its power assigns
#: combat damage equal to its toughness rather than its power." (Ghalta the
#: Immovable) - a fixed sentence, since the condition it names is exactly what
#: `CreaturesControlledByWhereToughnessExceedsPower` already checks; nothing
#: here is a variable to capture.
_GROUP_ASSIGNS_DAMAGE_AS_TOUGHNESS_RE = re.compile(
    r"^each creature you control with toughness greater than its power assigns combat "
    r"damage equal to its toughness rather than its power\.?$",
    re.IGNORECASE,
)

#: "Creatures you control with power or toughness 1 or less can't be
#: blocked." (Tetsuko Umezawa, Fugitive) - a per-object threshold on either
#: characteristic, granting `machines/combat.py`'s own self-referential
#: "can't be blocked" phrasing.
_GROUP_POWER_OR_TOUGHNESS_UNBLOCKABLE_RE = re.compile(
    r"^creatures you control with power or toughness (?P<threshold>\d+) or less can'?t be "
    r"blocked\.?$",
    re.IGNORECASE,
)

#: "Planeswalkers you control have "`<ability>`"." - Tomik, Orzhov Lawmage's
#: own attack-restriction grant, Sanctum Lurker's and every "Way of the
#: `<name>`" enchantment's own loyalty-ability grant, Avatar of Burgeoning
#: Echoes' `[-10]`. CR 113.10a's quoted-ability grant (already read for a
#: single attached or self-referential permanent by `_ATTACHED_CREATURE_
#: STATIC_RE`/`_GAINS_ABILITY_RE`), widened to CR 611.3's ordinary group
#: subject - a planeswalker is CR 300.1's own card type, so `permanents_
#: controlled_by(..., Type.PLANESWALKER)` is the identical selector every
#: other "`<card type>`s you control" static already reads with, not a new
#: kind of subject. Scoped to "you control" only: nothing in the pool grants
#: an ability to an *opponent's* planeswalkers, and building an untested
#: selector for a shape no card needs would be guessing, not reading.
_GROUP_QUOTED_ABILITY_GRANT_RE = re.compile(
    r'^planeswalkers you control have "(?P<ability>.+)"\.?$', re.IGNORECASE | re.DOTALL
)

#: "If Loot's power is negative, he assigns combat damage as though his power
#: were positive." (Loot, the Anomaly) - the card's own name is already
#: rewritten to "this permanent" by `self_normalized_effect_text`; the pronoun
#: that follows is whichever this set's card uses and is not itself read.
_SELF_ASSIGNS_DAMAGE_AS_THOUGH_POSITIVE_RE = re.compile(
    r"^if this (?:creature|permanent|token)'s power is negative, (?:he|she|it|they) "
    r"assigns? combat damage as though (?:his|her|its|their) power (?:were|was) "
    r"positive\.?$",
    re.IGNORECASE,
)

#: "Creatures you control can attack as though they didn't have defender."
#: (Ghalta the Immovable) - `_QUALIFIED_CREATURE_SUBJECT`'s group again,
#: granting the fixed `ATTACK_WITHOUT_DEFENDER_TEXT` rather than a bare
#: keyword, the way `_indefinite_keyword_grant_builder` already accepts any
#: ability text (Akroma's Memorial's "protection from ..." rows are the same
#: trick).
_GROUP_ATTACK_WITHOUT_DEFENDER_RE = re.compile(
    rf"^{_QUALIFIED_CREATURE_SUBJECT} can attack as though (?:it|they) didn'?t have "
    r"defender\.?$",
    re.IGNORECASE,
)

#: "Each [other] creature you control with a[n] <counter kind> counter on it
#: has/have <keyword(s)>." (Gallia, the Merrymaker; Vigorbloom Vanguard) - the
#: `permanents_controlled_by_with_counters` gate named for one counter kind
#: rather than "any counter" (Innkeeper's Talent's own shape).
_CREATURE_WITH_COUNTER_KEYWORD_GRANT_RE = re.compile(
    r"^each (?P<other>other )?creature you control with (?:an? )?"
    r"(?P<counter>[+-]1/[+-]1|[a-z]+) counter on it "
    r"(?:have|has) (?P<keywords>[a-z]+(?: [a-z]+)?(?:(?:,\s*| and )[a-z]+(?: [a-z]+)?)*)\.?$",
    re.IGNORECASE,
)

#: "Lands you control have <keyword(s)>." (Marwyn, the Preserver's hexproof) -
#: the land-subject twin of `_INDEFINITE_KEYWORD_GRANT_RE`, which only ever
#: matches a creature subject.
_LANDS_KEYWORD_GRANT_RE = re.compile(
    r"^lands you control (?:have|has) "
    r"(?P<keywords>[a-z]+(?: [a-z]+)?(?:(?:,\s*| and )[a-z]+(?: [a-z]+)?)*)\.?$",
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

#: "Until end of turn, target creature becomes a white Rabbit with base power
#: and toughness 0/1." (Metamorphic Blast's first mode) and "Until end of
#: turn, target creature loses all abilities and becomes a blue Frog with base
#: power and toughness 1/1." (Turn to Frog) - one template, the colour and the
#: "loses all abilities" optional. Read after `_normalize_duration_first` has
#: moved the duration to the end. Four layers from one effect (CR 613.6):
#: layer 4 sets the creature type (CR 205.1a: it replaces the creature types
#: and nothing else), layer 5 the colour (CR 613.1e), layer 6 removes the
#: abilities (CR 613.1f), sublayer 7b sets the base P/T (CR 613.4b).
_BECOMES_CREATURE_TYPE_WITH_BASE_PT_RE = re.compile(
    r"^target creature (?P<loses>loses all abilities and )?becomes an? "
    r"(?:(?P<color>white|blue|black|red|green) )?(?P<subtype>[a-z']+) with base power and "
    r"toughness (?P<power>\d+)/(?P<toughness>\d+) until end of turn\.?$",
    re.IGNORECASE,
)

#: "Target permanent becomes an artifact in addition to its other types until
#: end of turn." (Liquimetal Coating) - layer 4 (CR 613.1d), and "in addition
#: to" rather than a replacement: `add_type` keeps whatever types the
#: permanent already had, unlike `set_basic_land_type`'s CR 305.7 path (used
#: nowhere near this shape) which would strip them. `extra_type` is read
#: through the same `_OTHER_PERMANENT_TYPE_WORDS` map Karn's own "becomes a[n]
#: <type> creature" shape above uses.
_BECOMES_TYPE_IN_ADDITION_RE = re.compile(
    r"^target permanent becomes an? (?P<extra_type>[a-z]+) in addition to its "
    r"other types until end of turn\.?$",
    re.IGNORECASE,
)

#: "<subject> becomes a[n] <creature type(s)> in addition to its other types
#: [and gains <keyword>[, <keyword>, ... and <keyword>]] until end of turn." -
#: Enter the Avatar State's "Until end of turn, target creature you control
#: becomes an Avatar in addition to its other types and gains flying, first
#: strike, lifelink, and hexproof." (duration-first, normalised before this is
#: tried) and Archangel Elspeth's -2 rider "It becomes an Angel in addition to
#: its other types and gains flying." (the anaphor rewritten to "target
#: creature" by `machines/effects.py`'s referent rider, and no duration at
#: all: CR 611.2a, "If no duration is stated, it lasts until the end of the
#: game"). The words are CR 205.3m creature
#: types, checked against the real list rather than accepted blind; a card
#: type in this slot is `_BECOMES_TYPE_IN_ADDITION_RE`'s own sentence instead.
_BECOMES_SUBTYPE_IN_ADDITION_RE = re.compile(
    rf"^{_SUBJECT} becomes an? (?P<subtypes>[A-Za-z][A-Za-z' ]*?) in addition to "
    r"its other types(?: and gains (?P<keywords>[a-z][a-z ,]*?))?"
    r"(?P<until_eot> until end of turn)?\.?$",
    re.IGNORECASE,
)

#: "Gain control of target creature until end of turn." - the control half of
#: Threaten and every card templated after it ("Untap target creature and gain
#: control of it until end of turn.", confirmed with `resolve_cards`), and of
#: Act of Treason's and Mark of Mutiny's identical clause.
#:
#: Layer 2 (CR 613.1b: "Layer 2: Control-changing effects are applied"), and a
#: duration this shape *requires*: an untimed "gain control of target
#: creature" (Mind Control, Control Magic) is an Aura's or enchantment's own
#: static ability (CR 611.3), which lasts as long as its source is on the
#: battlefield rather than until a cleanup step, and lands on this module's
#: static path instead. Requiring "until end of turn" is what keeps the two
#: apart, exactly as `_ANTHEM_RE` and `_MASS_PUMP_UNTIL_EOT_RE` are kept apart.
#:
#: "it" and "that creature" are admitted alongside `_SUBJECT` because the
#: printed clause is anaphoric - Threaten names its target in the *untap* half
#: of the same sentence and refers back to it here. Nothing is re-derived from
#: the pronoun: `targets` already carries what `machines/targeting.py`
#: legalised at CR 601.2c, the same contract every other shape here relies on.
_GAIN_CONTROL_UNTIL_EOT_RE = re.compile(
    rf"^(?:you )?gain control of (?:{_SUBJECT}|it|that creature|that permanent) "
    r"until end of turn\.?$",
    re.IGNORECASE,
)

#: "Target spell or permanent becomes white." (Purelace, confirmed with
#: `resolve_cards`) - layer 5, the colour-changing layer (CR 613.1e), and the
#: first shape this module reads into it that names a single object rather
#: than a board-wide class the way `_ALL_COLORS_RE` does.
#:
#: The subject alternation is deliberately wider than `_SUBJECT`: Purelace's
#: "target spell or permanent" reaches onto the stack, which none of the
#: pump/keyword shapes ever do (CR 609.2: "Effects apply only to permanents
#: unless the instruction's text states otherwise", and this instruction does
#: state otherwise). Nothing is re-derived from the phrase - `targets` already
#: carries whatever `machines/targeting.py` legalised at CR 601.2c - so the
#: alternation only has to *recognise* the shape.
#:
#: The duration group is optional because CR 611.2a takes the duration from
#: what the card states and Purelace states none: a colour laced on is
#: permanent. "becomes `<colour>` until end of turn" is admitted in the same
#: shape rather than as a second one, since the two differ only in `Duration`.
_BECOMES_COLOR_RE = re.compile(
    r"^(?:target spell or permanent|target permanent|target spell"
    rf"|{_SUBJECT}) becomes (?P<color>white|blue|black|red|green)"
    r"(?P<until_eot> until end of turn)?\.?$",
    re.IGNORECASE,
)

#: "Until your next turn, he becomes a land and gains "{T}: Add {U}"."
#: (Hydro-Man, Fluid Felon's end step trigger, confirmed with `resolve_cards`).
#: Layer 4 for the type (CR 613.1d) and layer 6 for the granted ability
#: (CR 613.1f), one ability in two layers (CR 613.6), lasting the "until
#: that player's next turn" duration CR 611.2a names.
#:
#: CR 205.1a - "the new card type(s) replaces any existing card types" - is
#: what the card's own reminder text spells out as "He's not a creature during
#: that time", and CR 205.3d ("An object can't gain a subtype that doesn't
#: correspond to one of that object's types") is why the creature types go with
#: it. The pronoun is read as a subject alongside "this permanent": the card
#: prints "he", and `self_normalized_effect_text` only rewrites the literal
#: printed name.
_SELF_BECOMES_TYPE_UNTIL_NEXT_TURN_RE = re.compile(
    r"^until your next turn, (?:he|she|it|they|this permanent|this creature) becomes an? "
    r'(?P<extra_type>[a-z]+)(?: and gains "(?P<ability>[^"]+)")?\.?$',
    re.IGNORECASE,
)


def _self_becomes_type_until_next_turn_builder(
    extra_type: Type, ability: str | None
) -> EffectBuilder:
    """`_SELF_BECOMES_TYPE_UNTIL_NEXT_TURN_RE`'s shape.

    The type change *replaces* (CR 205.1a), unlike `_becomes_type_in_addition_
    builder`'s CR 205.1b form - which is the whole difference between "becomes
    a land" and "becomes a land in addition to its other types", and the reason
    Blood Moon can then see it as a nonbasic land at all (CR 613.8a's
    dependency: making it a land changes the set of objects Blood Moon applies
    to).

    `until_next_turn_of` is the source's controller - the "your" of "until your
    next turn" (CR 611.2a: the continuous effect "lasts as long as stated by
    the spell or ability creating it").
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        become = SetTypesAndSubtypes(types=(extra_type,), subtypes=())

        effects: list[ContinuousEffect] = []
        for target in targets:
            effects.append(
                ContinuousEffect(
                    description=f"{source.name}: {target.name} becomes "
                    f"{with_indefinite_article(extra_type.value)}",
                    layer=Layer.TYPE,
                    timestamp=timestamp,
                    duration=Duration.UNTIL_YOUR_NEXT_TURN,
                    until_next_turn_of=source.controller,
                    selector=only_this_incarnation(target, target.zone_change_stamp),
                    modification=become,
                )
            )
            if ability is not None:
                effects.append(
                    ContinuousEffect(
                        description=f"{source.name}: {target.name} gains {ability}",
                        layer=Layer.ABILITY,
                        timestamp=timestamp,
                        duration=Duration.UNTIL_YOUR_NEXT_TURN,
                        until_next_turn_of=source.controller,
                        selector=only_this_incarnation(target, target.zone_change_stamp),
                        modification=grant_ability(ability),
                    )
                )
        return effects

    return builder


#: A retention clause on its own - "It's still a land." - which
#: `_RETENTION_CLAUSE_RE` folds back into the sentence in front of it before
#: any shape is tried, so an animation and its retention are read as the one
#: ability they are (CR 205.1b: "Some effects change an object's card type ...
#: but specify that the object retains a prior card type").
#:
#: Folded rather than parsed separately on purpose. Parsed on its own it would
#: make *any* card carrying the clause look partly readable - Jolrael, Voice of
#: Zhalfir's "becomes an X/X green and blue Bird creature with flying and haste
#: ... where X is the number of cards in your hand. It's still a land." would
#: have produced the retention and nothing else, which is half an ability
#: (CR 608.2c has no notion of running half an instruction).
_RETENTION_CLAUSE_RE = re.compile(r"^[Ii]t's still an? [a-z]+\.?$")


def is_retention_clause(sentence: str) -> bool:
    """`_RETENTION_CLAUSE_RE`'s shape, public: "It's still a `<type>`." (CR
    205.1b) never stands as an ability of its own - it only ever qualifies
    the type-changing sentence in front of it. `machines/effects.py` uses
    this to keep such a clause from being misread as an unread sibling
    instruction (`_plain_resolution_sentences`) the way any other trailing
    sentence would be.
    """
    return bool(_RETENTION_CLAUSE_RE.match(sentence.strip()))


def _fold_retention_clauses(sentences: list[str]) -> list[str]:
    """Join every bare "It's still a `<type>`." onto the sentence before it.

    The clause qualifies the type change in front of it (CR 205.1b) and is
    never an ability of its own, so it has to reach a shape as one sentence or
    the shape would read half of one.
    """
    folded: list[str] = []
    for sentence in sentences:
        if folded and _RETENTION_CLAUSE_RE.match(sentence.strip()):
            folded[-1] = f"{folded[-1].rstrip()} {sentence.strip()}"
            continue
        folded.append(sentence)
    return folded


#: A permanent becoming a creature with a stated P/T - the "animation"
#: template, one shape whoever the subject is and however long it lasts:
#:
#: - **itself**, trailing duration: "This land becomes a 2/2 Assembly-Worker
#:   artifact creature until end of turn. It's still a land." (Mishra's
#:   Factory);
#: - **itself**, duration first, with colours and keywords: "Until end of
#:   turn, this land becomes a 7/7 blue Giant creature with ward {3}. It's
#:   still a land." (Hall of Storm Giants; Celestial Colonnade's "4/4 white and
#:   blue Elemental creature with flying and vigilance") - `_normalize_duration_
#:   first` has already moved the duration to the end, ahead of the folded
#:   retention sentence;
#: - **itself, for the rest of the game**: "This land becomes a 3/3 Elemental
#:   artifact creature that's still a land." (Stalking Stones);
#: - **a target**: "Up to one target land you control becomes an X/X green and
#:   blue Bird creature with flying and haste until end of turn ... It's still
#:   a land." (Jolrael, Voice of Zhalfir, X already substituted by
#:   `machines/effects.py`'s `_WHERE_X_IS_RE`);
#: - **an earlier target, by anaphora**: "It becomes a 0/0 Elemental creature
#:   with vigilance and haste that's still a land." (Nissa, Who Shakes the
#:   World's +1, after "Put three +1/+1 counters on up to one target
#:   noncreature land you control. Untap it."), "that land becomes a 0/0
#:   Elemental creature with haste that's still a land." (Wall of
#:   Resurgence).
#:
#: One ability in up to four layers (CR 613.6): layer 4 for the card types
#: and creature type (CR 613.1d), layer 5 for the colours (CR 613.1e), layer 6
#: for the keywords (CR 613.1f), sublayer 7b for the P/T (CR 613.4b), all on
#: one timestamp so nothing reorders against itself.
#:
#: CR 611.2a: "If no duration is stated, it lasts until the end of the game" -
#: so the absent "until end of turn" is `Duration.INDEFINITE`, not an error.
#:
#: CR 205.1b decides what happens to the old types: "It's still a land." /
#: "that's still a land" retains "all the object's prior card types,
#: supertypes, and subtypes" - a Forest Nissa animates is still a Forest, and
#: still taps for her extra {G}; "[creature type] artifact creature" retains
#: every prior type and subtype "other than creature types". Neither phrase
#: printed is CR 205.1a's plain replacement.
#:
#: The keyword slot is read lazily and then validated by
#: `_split_and_validate_keywords`, so "flying and vigilance", "vigilance and
#: haste" and "ward {3}" all read, and a quoted granted ability (Hive of the
#: Eye Tyrant's `"Whenever this creature attacks, ..."`) fails the whole
#: sentence rather than granting half of it.
_ANIMATION_RE = re.compile(
    r"^(?P<subject>[Tt]his (?:land|permanent|artifact|creature|enchantment)"
    r"|(?:[Uu]p to (?:one|two|three) )?(?:target|another target) [a-z]+(?: [a-z]+)*?"
    r"|[Ii]t|[Tt]hat (?:land|permanent|creature|artifact))"
    r" becomes an? (?P<power>\d+)/(?P<toughness>\d+) "
    r"(?P<colors>(?:white|blue|black|red|green)(?:(?:,| and|, and) "
    r"(?:white|blue|black|red|green))* )?"
    r"(?P<subtype>[A-Z][A-Za-z'-]*(?: [A-Z][A-Za-z'-]*)? )?"
    r"(?P<types>(?:artifact |enchantment |land )*creature)"
    r"(?: with (?P<keywords>[^\"]+?))?"
    r"(?: that's still an? (?P<retained_inline>[a-z]+))?"
    r"(?P<until_eot> until end of turn)?\.?"
    r"(?:\s+[Ii]t's still an? (?P<retained>[a-z]+)\.?)?$"
)


def _animation_type_modifications(
    types: Sequence[Type], subtype: str | None, retained: Type | None
) -> list[Modification]:
    """What layer 4 does for one `_ANIMATION_RE` match (CR 613.1d).

    - retained ("still a land"): CR 205.1b keeps every prior card type and
      subtype, so the new types and the creature type are *added*;
    - "[creature type] artifact creature" with nothing retained: CR 205.1b's
      last sentence keeps every prior type and subtype except the creature
      types, which the new one replaces;
    - neither: CR 205.1a's replacement - the new types and the one subtype
      are all that is left (CR 205.3d takes the old subtypes with their
      types).
    """
    if retained is not None:
        added: list[Modification] = [add_type(card_type) for card_type in types]
        added.append(add_type(retained))
        if subtype is not None:
            added.append(AddSubtype(subtype=subtype))
        return added
    if Type.ARTIFACT in types:
        added = [add_type(card_type) for card_type in types]
        added.append(SetCreatureTypes(subtypes=(subtype,) if subtype is not None else ()))
        return added
    return [SetTypesAndSubtypes(types=tuple(types), subtypes=(subtype,) if subtype else ())]


def _animation_builder(
    power: int,
    toughness: int,
    colors: list[Color],
    subtype: str | None,
    types: list[Type],
    keywords: list[str],
    *,
    retained: Type | None,
    anaphoric: bool,
    duration: Duration,
) -> EffectBuilder:
    """`_ANIMATION_RE`'s shape.

    The subject is `targets`, which `create_continuous_effect_of_ability`
    fills with what the ability targeted when its text names a target, and
    with the ability's own source when it does not - "this land" needs
    nothing more. "Up to one target ..." legally choosing zero (CR 115.6)
    leaves `targets` empty and animates nothing.

    An anaphoric subject ("it", "that land") refers back to an object an
    earlier instruction of the same ability named, never to the ability's own
    source - the source always calls itself "this". So the source is skipped
    when it is all `targets` holds: an ability whose target is gone
    (CR 608.2b) must animate nothing, not fall back to animating itself.

    The colour list is a *set* (CR 613.1e), not an addition: "becomes a 4/4
    white and blue Elemental creature" states the colours the object has.
    Ward is granted as its own instance (`grant_ability_instance`, CR 702.21a
    has no redundancy clause), every other keyword through `grant_ability`.
    """
    type_modifications = _animation_type_modifications(types, subtype, retained)

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        effects: list[ContinuousEffect] = []
        for target in targets:
            if anaphoric and target.id == source.id:
                continue
            stamp = only_this_incarnation(target, target.zone_change_stamp)
            named = f"{subtype} " if subtype is not None else ""
            description = f"{source.name}: {target.name} becomes " + with_indefinite_article(
                f"{power}/{toughness} {named}" + " ".join(card_type.value for card_type in types)
            )
            for modification in type_modifications:
                effects.append(
                    ContinuousEffect(
                        description=description,
                        layer=Layer.TYPE,
                        timestamp=timestamp,
                        duration=duration,
                        selector=stamp,
                        modification=modification,
                    )
                )
            if colors:
                effects.append(
                    ContinuousEffect(
                        description=(
                            f"{source.name}: {target.name} becomes "
                            f"{' and '.join(color.value for color in colors)}"
                        ),
                        layer=Layer.COLOR,
                        timestamp=timestamp,
                        duration=duration,
                        selector=stamp,
                        modification=set_colors(*colors),
                    )
                )
            for keyword in keywords:
                effects.append(
                    ContinuousEffect(
                        description=f"{source.name}: {target.name} gains {keyword}",
                        layer=Layer.ABILITY,
                        timestamp=timestamp,
                        duration=duration,
                        selector=stamp,
                        modification=(
                            grant_ability_instance(keyword)
                            if keyword.lower().startswith("ward ")
                            else grant_ability(keyword)
                        ),
                    )
                )
            effects.append(
                ContinuousEffect(
                    description=f"{source.name}: {target.name} has base P/T {power}/{toughness}",
                    layer=Layer.POWER_TOUGHNESS,
                    sublayer=Sublayer.SET,
                    timestamp=timestamp,
                    duration=duration,
                    selector=stamp,
                    modification=set_power_toughness(power, toughness),
                )
            )
        return effects

    return builder


def _parse_animation_sentence(sentence: str) -> EffectBuilder | None:
    """`_ANIMATION_RE`'s match turned into its builder, or `None`."""
    match = _ANIMATION_RE.fullmatch(sentence)
    if match is None:
        return None
    types = [_card_type_word(word) for word in match.group("types").split()]
    if any(card_type is None for card_type in types):
        return None
    retained_word = match.group("retained") or match.group("retained_inline")
    retained = _card_type_word(retained_word) if retained_word is not None else None
    if retained_word is not None and retained is None:
        return None
    keywords: list[str] = []
    if match.group("keywords") is not None:
        validated = _split_and_validate_keywords(match.group("keywords"))
        if validated is None:
            return None
        keywords = validated
    raw_colors = match.group("colors")
    colors = (
        [_COLOR_WORDS[word] for word in re.findall(r"[a-z]+", raw_colors) if word in _COLOR_WORDS]
        if raw_colors
        else []
    )
    subtype = match.group("subtype")
    subject = match.group("subject").lower()
    return _animation_builder(
        int(match.group("power")),
        int(match.group("toughness")),
        colors,
        subtype.strip() if subtype else None,
        [card_type for card_type in types if card_type is not None],
        keywords,
        retained=retained,
        anaphoric=subject == "it" or subject.startswith("that "),
        duration=(Duration.UNTIL_END_OF_TURN if match.group("until_eot") else Duration.INDEFINITE),
    )


# --------------------------------------------------------------------------
# Board-wide static shapes, keyed by the printed sentence rather than the name
# --------------------------------------------------------------------------
#
# CR 604.2: "Static abilities create continuous effects ... These effects are
# active as long as the permanent with the ability remains on the battlefield",
# and CR 611.3b: "The effect applies at all times that the permanent generating
# it is on the battlefield". Neither rule mentions the card's name, and that is
# the whole point of this section: a sentence, not a name, is what generates the
# effect. Blood Moon and Harbinger of the Seas print the same sentence with a
# different basic land type in it; Dryad of the Ilysian Grove and Leyline of the
# Guildpact print the same sentence verbatim. Keyed by name, the second card of
# each pair silently did nothing - not even a `LayerNotice`, since these shapes
# do not open the way `_LOOKS_LIKE_LAYER_EFFECT_RE`'s pump/anthem ones do.

#: "Nonbasic lands are Mountains." (Blood Moon, Magus of the Moon) / "Nonbasic
#: lands are Islands." (Harbinger of the Seas, confirmed with `resolve_cards`).
#: Layer 4 (CR 613.1d), and CR 305.7 is what makes it removal as much as a type
#: change: "If an effect sets a land's subtype to one or more of the basic land
#: types, the land no longer has its old land type. It loses all abilities
#: generated from its rules text, its old land types, and any copy effects".
#: Only the five basic land types (CR 305.6) are admitted, since CR 305.7 is
#: written about exactly those.
_NONBASIC_LANDS_ARE_RE = re.compile(
    r"^nonbasic lands are (?P<subtype>plains|islands|swamps|mountains|forests)\.?$",
    re.IGNORECASE,
)

#: "Lands you control are every basic land type in addition to their other
#: types." (Dryad of the Ilysian Grove, Leyline of the Guildpact - both
#: confirmed with `resolve_cards`). Layer 4 (CR 613.1d); "in addition to" is
#: CR 205.1b's retaining form, not CR 305.7's setting one, so nothing is lost,
#: and each basic type gained brings its intrinsic mana ability along
#: (CR 305.6).
_LANDS_ARE_EVERY_BASIC_TYPE_RE = re.compile(
    r"^lands you control are every basic land type in addition to their other types\.?$",
    re.IGNORECASE,
)

#: "Each land is a Swamp in addition to its other land types." (Urborg, Tomb of
#: Yawgmoth) / "Each land is a Forest ..." (Yavimaya, Cradle of Growth). Layer 4
#: (CR 613.1d), CR 205.1b again, CR 305.6 for the mana ability that comes with
#: the type.
_EACH_LAND_IS_RE = re.compile(
    r"^each land is an? (?P<subtype>plains|island|swamp|mountain|forest) in addition to "
    r"its other land types\.?$",
    re.IGNORECASE,
)

#: "Nontoken artifacts you control are lands in addition to their other types."
#: (Toph, the First Metalbender). Layer 4 (CR 613.1d) and CR 205.1b's "retains
#: a prior card type" wording - the board-wide, card-type twin of the land-type
#: grants above. Both nouns are read through `_card_type_word`, so anything
#: outside CR 300.1's card types fails the match rather than granting a
#: made-up type.
_BOARD_WIDE_TYPE_GRANT_RE = re.compile(
    r"^(?P<nontoken>nontoken )?(?P<subject>[a-z]+) you control are (?P<granted>[a-z]+) "
    r"in addition to their other types\.?$",
    re.IGNORECASE,
)

#: The five basic land types as a sentence spells them, singular or plural, to
#: the stored subtype - `add_subtype`/`set_basic_land_type` both want "Island",
#: never "Islands" (CR 205.3i's land types are stored singular).
_BASIC_LAND_TYPE_WORDS: dict[str, str] = {
    word: subtype
    for subtype in BASIC_LAND_TYPES
    for word in (subtype.lower(), f"{subtype.lower()}s")
}


def _nonbasic_lands_are_builder(subtype: str) -> EffectBuilder:
    """`_NONBASIC_LANDS_ARE_RE`'s shape - Blood Moon's, and every printing that
    says the same thing about a different basic land type.

    Layer 4 (CR 613.1d). CR 305.7 makes this a *setting* effect rather than an
    additive one, so `set_basic_land_type` replaces the land's subtypes and its
    rules-text abilities with the one basic type and the intrinsic mana ability
    that comes with it (CR 305.6). "Nonbasic" is the supertype question
    (CR 205.4c, CR 305.8: "Any land that doesn't have this supertype is a
    nonbasic land, even if it has a basic land type"), which is exactly what
    `nonbasic_lands` asks.
    """
    # "Plains" is already plural (CR 205.3i spells the land type that way), so
    # the printed sentence never doubles the "s".
    plural = subtype if subtype == "Plains" else f"{subtype}s"
    sentence = f"Nonbasic lands are {plural}."

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=f"{source.name}: nonbasic lands are {plural}",
                layer=Layer.TYPE,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, sentence),
                selector=nonbasic_lands,
                modification=set_basic_land_type(subtype, BASIC_LAND_TYPES[subtype]),
            )
        ]

    return builder


def _lands_are_every_basic_type_builder(line: str) -> EffectBuilder:
    """`_LANDS_ARE_EVERY_BASIC_TYPE_RE`'s shape - Dryad of the Ilysian Grove's
    and Leyline of the Guildpact's identical sentence.

    Layer 4 (CR 613.1d). "In addition to their other types" is CR 205.1b, so
    nothing is stripped - this is not CR 305.7's setting form - and every basic
    type gained carries its intrinsic "{T}: Add [mana symbol]" with it
    (CR 305.6), which is why one of these turns every land into a five-colour
    source.

    Neither card's *other* lines are this shape's business: Dryad's extra land
    drop is CR 611.3d's rule-modifying grant (`ADDITIONAL_LAND_PLAYS`), and
    Leyline of the Guildpact's "Each nonland permanent you control is all
    colors" is a layer 5 effect (CR 613.1e) no shape here reads yet.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=f"{source.name}: your lands are every basic land type",
                layer=Layer.TYPE,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=lands_controlled_by(source.controller),
                modification=add_basic_land_types,
            )
        ]

    return builder


def _each_land_is_builder(subtype: str, line: str) -> EffectBuilder:
    """`_EACH_LAND_IS_RE`'s shape - Urborg, Tomb of Yawgmoth's and Yavimaya,
    Cradle of Growth's. Layer 4 (CR 613.1d), additive (CR 205.1b), with the
    intrinsic mana ability the type carries (CR 305.6).
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=f"{source.name}: each land is {with_indefinite_article(subtype)}",
                layer=Layer.TYPE,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=every_land,
                modification=add_subtype(subtype, BASIC_LAND_TYPES[subtype]),
            )
        ]

    return builder


def _board_wide_type_grant_builder(
    subject: Type, granted: Type, *, nontoken: bool, line: str
) -> EffectBuilder:
    """`_BOARD_WIDE_TYPE_GRANT_RE`'s shape - Toph, the First Metalbender's
    "Nontoken artifacts you control are lands in addition to their other
    types."

    Layer 4 (CR 613.1d), additive by CR 205.1b: "Some effects change an
    object's card type ... but specify that the object retains a prior card
    type ... In such cases, all the object's prior card types ... are
    retained." An artifact caught by this stays an artifact and becomes a land
    as well, which is what makes it a legal subject for a "nonbasic lands are
    ..." effect in the same layer - CR 613.8's dependency, since applying this
    one changes the set of objects the other applies to.

    The parenthetical Toph prints ("They don't gain the ability to {T} for
    mana") is reminder text (CR 207.2a), already stripped before the sentence
    reaches here, and states no rule of its own: CR 305.6 hands out an
    intrinsic mana ability for a *basic land type*, and this grants the land
    card type with no subtype at all.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=(
                    f"{source.name}: {'nontoken ' if nontoken else ''}{subject.value}s you "
                    f"control are {granted.value}s in addition to their other types"
                ),
                layer=Layer.TYPE,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=permanents_controlled_by(source.controller, subject, nontoken=nontoken),
                modification=add_type(granted),
            )
        ]

    return builder


#: The pump/keyword-grant/base-P/T-set/becomes-creature shapes' opening words
#: - everything `_LOOKS_LIKE_LAYER_EFFECT_RE` matches **except** the anthem
#: shape - so a caller can ask "does this look like a one-shot *resolution*
#: effect (CR 611.2)" without the static-only anthem shape (CR 611.3)
#: answering yes. `machines/effects.py`'s routing needs exactly that
#: distinction: see `is_resolution_layer_effect_text`.
_LOOKS_LIKE_RESOLUTION_LAYER_EFFECT_RE = re.compile(
    rf"^(?:{_SUBJECT}|{_PLURAL_TARGET_SUBJECT}) (?:(?:each )?gets?|gains?|has|have)\b"
    r"|^Until your next turn, up to \S+ target\b"
    r"|^target permanent becomes\b",
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
#:
#: The qualifier words are `_SUBJECT_QUALIFIERS`' - the supertype, "nontoken",
#: "each"'s singular noun and "of the chosen color" included - so Mirror Box's
#: "Each legendary creature you control gets +1/+1." and Caged Sun's
#: "Creatures you control of the chosen color get +1/+1." are excluded from
#: resolution routing as the static abilities they are.
_LOOKS_LIKE_ANTHEM_RE = re.compile(
    r"^(?:as long as [^,]+, )?(?:each )?(?:other )?(?:non(?:white|blue|black|red|green) )?"
    r"(?:(?:non)?legendary )?(?:nontoken )?(?:land |artifact )?"
    r"(?:creature tokens?|creatures?) (?:you control|your opponents control)"
    r"(?: of the chosen colou?r)? (?:get|gets|have|has)\b",
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

#: A sentence-initial sequencing word (CR 608.2c: "the controller ... follows
#: its instructions in the order written") - "Then creatures you control gain
#: haste until end of turn." (Ingris Stingerquill, after an earlier token
#: creation in the same ability). `machines/effects.split_effect_clauses`
#: already strips this same word from an ordinary clause for the identical
#: reason; a layer sentence that happens to follow another instruction in the
#: same paragraph must read the same as if it opened the sentence itself.
_LEADING_THEN_RE = re.compile(r"^then,?\s+", re.IGNORECASE)

#: A folded "It's still a `<type>`" (CR 205.1b) at the very end of a
#: duration-first sentence's remainder - see `_normalize_duration_first`.
_TRAILING_RETENTION_RE = re.compile(r"\.\s+(?P<clause>[Ii]t's still an? [a-z]+)$")


def _normalize_duration_first(sentence: str) -> str:
    """Rewrite "Until end of turn, X" to "X until end of turn." so a
    duration-first sentence reaches `_parse_layer_sentence` and
    `_LOOKS_LIKE_LAYER_EFFECT_RE` the same way the ordinary trailing-duration
    phrasing already does. A sentence that does not open this way is returned
    unchanged. A leading "Then " (`_LEADING_THEN_RE`) is stripped first,
    always, so both the duration check and the shapes read afterward see the
    sentence as it would look on its own.
    """
    sentence = _LEADING_THEN_RE.sub("", sentence.strip())
    match = _DURATION_FIRST_RE.match(sentence)
    if match is None:
        return sentence
    rest = match.group("rest").strip().rstrip(".")
    # A folded CR 205.1b retention sentence ("... with ward {3}. It's still a
    # land.", `_fold_retention_clauses`) qualifies the type change, not the
    # duration: the duration goes back on the type-changing sentence and the
    # retention stays behind it, exactly as a trailing-duration manland
    # (Mishra's Factory) prints the two.
    retention = _TRAILING_RETENTION_RE.search(rest)
    if retention is not None:
        body = rest[: retention.start()].rstrip().rstrip(".")
        return f"{body} until end of turn. {retention.group('clause')}."
    return f"{rest} until end of turn."


#: An ability word and the em dash that follows it - "Domain — ", "Delirium — "
#: - at the very start of a sentence. CR 207.2c: "An ability word appears in
#: italics at the beginning of some abilities. Ability words are similar to
#: keywords in that they tie together cards that have similar functionality,
#: but they have no special rules meaning", so the words in front of the dash
#: are decoration and the ability is everything after it. Capped at two words
#: and required to start with a capital, which is how Oracle prints them -
#: except CR 207.2c's own "descend 4"/"descend 8", whose second word is a
#: bare number rather than another capitalised word, so the second slot
#: accepts one too.
_ABILITY_WORD_RE = re.compile(r"^[A-Z][a-z']*(?: (?:[A-Za-z][a-z']*|\d+))? — (?P<rest>.+)$")


def _strip_ability_word(sentence: str) -> str:
    """A sentence with any leading ability word (CR 207.2c) removed, or
    unchanged if it has none.

    Applied only on the parsing path, never to the notice question: a sentence
    behind an ability word never opened the way `_LOOKS_LIKE_LAYER_EFFECT_RE`
    watches for, so it never produced a notice, and stripping here can only
    turn "silently nothing" into a real effect.
    """
    match = _ABILITY_WORD_RE.match(sentence.strip())
    return match.group("rest").strip() if match else sentence


def _effect_sentences(
    oracle_text: str | None,
    *,
    static_only: bool = False,
    card_name: str | None = None,
    legendary: bool = True,
) -> list[str]:
    """`_effect_sentences_uncached`, memoised on every argument - the battlefield
    sweep asks it for every permanent on every board computation, and the answer
    depends on nothing but the printed text and these flags. Each caller gets a
    list of its own, so nobody can edit what the next caller reads.
    """
    return list(_effect_sentences_memo(oracle_text, static_only, card_name, legendary))


def resolution_effect_sentences(text: str | None) -> list[str]:
    """The public entry point onto `_effect_sentences`: every sentence of a
    resolving spell's or ability's own effect text, split the same way
    `is_resolution_layer_effect_text` itself splits it before asking each one
    whether it is a CR 611.2 layer shape.

    `machines/effects.py` uses this to separate a layer-effect sentence from
    a sibling one-shot instruction it must compose rather than drop
    (`_compose_layer_effect_with_remainder`), and to see a compound antecedent
    ("Target creature gets +2/+2 and gains reach until end of turn.") whole,
    ahead of the finer comma/and clause split that would otherwise cut it into
    fragments no anaphoric-pair parser can read back together
    (`_parse_object_anaphor_clause_pair`'s own whole-text pre-check).
    """
    return _effect_sentences(text)


@functools.lru_cache(maxsize=16384)
def _effect_sentences_memo(
    oracle_text: str | None, static_only: bool, card_name: str | None, legendary: bool
) -> tuple[str, ...]:
    return tuple(
        _effect_sentences_uncached(
            oracle_text, static_only=static_only, card_name=card_name, legendary=legendary
        )
    )


def _effect_sentences_uncached(
    oracle_text: str | None,
    *,
    static_only: bool = False,
    card_name: str | None = None,
    legendary: bool = True,
) -> list[str]:
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

    `static_only=True` narrows this to `StaticAbility` bodies alone - see
    `layer_readable_sentences`'s own docstring for why `effects_for`'s
    `looks_like_unparsed_layer_effect` call needs exactly that restriction
    and the effect-building call does not strictly need it but takes it too,
    for symmetry: a triggered/activated ability's own effect body should
    never be treated as this permanent's *static* (CR 611.3) contribution,
    whether or not it happens to parse.
    """
    return _fold_retention_clauses(
        layer_readable_sentences(
            oracle_text, static_only=static_only, card_name=card_name, legendary=legendary
        )
    )


def _targeted_loses_all_abilities_builder() -> EffectBuilder:
    """ "Target `<X>` loses all abilities until end of turn." - CR 613.1f,
    layer 6, one `target`'s incarnation at a time (`only_this_incarnation`,
    the same per-target selector `_pump_and_keyword_builder` uses just
    below), timed to expire at CR 514.2's cleanup step like any other
    "until end of turn" effect (`Duration.UNTIL_END_OF_TURN`).
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=f"{source.name}: {target.name} loses all abilities",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                duration=Duration.UNTIL_END_OF_TURN,
                selector=only_this_incarnation(target, target.zone_change_stamp),
                modification=lose_all_abilities,
            )
            for target in targets
        ]

    return builder


def _pump_and_keyword_builder(
    power: int, toughness: int, keywords: Sequence[str] = (), *, until_next_turn: bool = False
) -> EffectBuilder:
    """ "[Subject] gets +N/+N [and gains <keyword>[ and <keyword>]] until end
    of turn[/until your next turn]."

    Sublayer 7c for the pump (CR 613.4c: "modify power and/or toughness ...
    don't set"), layer 6 for the keyword (CR 613.1f, CR 113.10). Applies to
    whatever `targets` the caller hands in - a spell's resolved targets
    (`create_continuous_effect`), or an ability's own source
    (`create_continuous_effect_of_ability`, called with `targets=[source]`).
    Called with none at all - what a static sweep of the battlefield does for
    every permanent - correctly produces nothing: this is never a static
    ability's own effect.

    `until_next_turn` is CR 611.2a's longer duration - Liliana, the Last
    Hope's own "Up to one target creature gets -2/-1 until your next turn."
    and Garruk, Veiled Butcher's identically shaped "+2" - which needs
    `until_next_turn_of` naming whose turn (the resolving source's own
    controller, the only player a printed "your" here means), not just the
    longer `Duration` member on its own.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        duration = Duration.UNTIL_YOUR_NEXT_TURN if until_next_turn else Duration.UNTIL_END_OF_TURN
        until_next_turn_of = source.controller if until_next_turn else None
        effects: list[ContinuousEffect] = []
        for target in targets:
            effects.append(
                ContinuousEffect(
                    description=f"{source.name}: {target.name} gets {power:+d}/{toughness:+d}",
                    layer=Layer.POWER_TOUGHNESS,
                    sublayer=Sublayer.MODIFY,
                    timestamp=timestamp,
                    duration=duration,
                    until_next_turn_of=until_next_turn_of,
                    selector=only_this_incarnation(target, target.zone_change_stamp),
                    modification=modify_power_toughness(power, toughness),
                )
            )
            for keyword in keywords:
                effects.append(
                    ContinuousEffect(
                        description=f"{source.name}: {target.name} gains {keyword}",
                        layer=Layer.ABILITY,
                        timestamp=timestamp,
                        duration=duration,
                        until_next_turn_of=until_next_turn_of,
                        selector=only_this_incarnation(target, target.zone_change_stamp),
                        modification=grant_ability(keyword),
                    )
                )
        return effects

    return builder


def _pump_and_keyword_per_target_power_builder(
    power_sign: int, toughness_sign: int, keywords: Sequence[str] = ()
) -> EffectBuilder:
    """Xenagos, God of Revels' own shape: "[Subject] gets +X/+X [and gains
    <keyword>] until end of turn, where X is that creature's power."

    `power_sign`/`toughness_sign` are `+1`/`-1` off the printed sign in front
    of each X (both `+1` for Xenagos' own "+X/+X"; nothing in the pool prints
    "-X/-X" here, but the mechanism is the same one `_PUMP_RE` already reads
    generally rather than something special-cased to this one card). X is
    read once **per target**, off that target's own `CardState.power` - the
    CR 613.5 computed value, already what `power` gives - at the moment this
    builder runs, which `ContinuousEffects.create` only ever calls once, as
    the ability resolves (CR 611.2c fixes the magnitude then). A target
    without a numeric power (`*`, or gone before this runs) contributes X = 0
    rather than guessing (CR 107.2).
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        effects: list[ContinuousEffect] = []
        for target in targets:
            x = target.power if target.power is not None else 0
            power, toughness = power_sign * x, toughness_sign * x
            effects.append(
                ContinuousEffect(
                    description=f"{source.name}: {target.name} gets {power:+d}/{toughness:+d}",
                    layer=Layer.POWER_TOUGHNESS,
                    sublayer=Sublayer.MODIFY,
                    timestamp=timestamp,
                    duration=Duration.UNTIL_END_OF_TURN,
                    selector=only_this_incarnation(target, target.zone_change_stamp),
                    modification=modify_power_toughness(power, toughness),
                )
            )
            for keyword in keywords:
                effects.append(
                    ContinuousEffect(
                        description=f"{source.name}: {target.name} gains {keyword}",
                        layer=Layer.ABILITY,
                        timestamp=timestamp,
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=only_this_incarnation(target, target.zone_change_stamp),
                        modification=grant_ability(keyword),
                    )
                )
        return effects

    return builder


def _target_and_same_name_pump_builder(power: int, toughness: int) -> EffectBuilder:
    """ "Target creature and all other creatures with the same name as that
    creature get +N/+N until end of turn." (Echoing Courage.)

    Sublayer 7c, like `_pump_and_keyword_builder` (CR 613.4c: "modify power
    and/or toughness ... don't set"), but with a `Selector` that is *not*
    fixed to the target's identity. The set of objects an effect affects is
    settled when it begins (CR 611.2c), and here that set is "every creature
    with this name" - which is what `same_name_as` asks the board, so a
    creature that shares the name is pumped and one that merely shares a
    creature type is not (CR 201.2a).

    The target itself has the name, so one effect covers both halves of the
    sentence; the name is read off the target once, at build time, because
    that is the moment the effect begins.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=(
                    f"{source.name}: creatures named {target.name} get {power:+d}/{toughness:+d}"
                ),
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=timestamp,
                duration=Duration.UNTIL_END_OF_TURN,
                selector=same_name_as(target.name),
                modification=modify_power_toughness(power, toughness),
            )
            for target in targets
        ]

    return builder


#: CR 106.6's additional-effect clause, as a mana ability prints it: "If that
#: mana is spent on a creature spell, it gains haste until end of turn."
#: (Arena of Glory). The subject is the *spell* the mana was spent on, so the
#: card type it names is checked against that spell, and the grant lands on
#: the permanent the spell becomes (CR 400.7b: "if a spell is countered or
#: resolves, the card that represents it ... becomes a new object" - the
#: permanent a resolving permanent spell becomes is the same object it was on
#: the stack, which is why "it gains haste" reaches the creature at all).
_MANA_SPEND_EFFECT_RE = re.compile(
    r"^if that mana is spent on an? (?P<what>[a-z]+) spell, "
    r"it gains (?P<keyword>[a-z ]+) until end of turn\.?$",
    re.IGNORECASE,
)


def spend_effect_grant(text: str) -> tuple[Type, str] | None:
    """Read a CR 106.6 spend-effect sentence into (card type, keyword).

    `None` for a sentence this module does not recognise, and that is not
    fail-closed on purpose: unlike a spend *restriction*, this clause never
    narrows what the mana may pay for, so an unread one costs the game an
    extra grant and nothing else. Refusing to spend the mana would be strictly
    worse - the land would stop making usable mana over a sentence that only
    ever gives something away.

    Only a known keyword is returned (`_KNOWN_KEYWORDS`), for the same reason
    `_pump_and_keyword_builder`'s own grant checks: `grant_ability` writes the
    word into the object's abilities and something has to be able to read it
    back.
    """
    match = _MANA_SPEND_EFFECT_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    card_type = _card_type_word(match.group("what"))
    keyword = match.group("keyword").strip().lower()
    if card_type is None or keyword not in _KNOWN_KEYWORDS:
        return None
    return card_type, keyword.capitalize()


def spend_effect_effects(text: str, permanent: CardState, timestamp: int) -> list[ContinuousEffect]:
    """The continuous effects one spend-effect sentence puts on `permanent`.

    Empty when the sentence is unreadable, or when the spell it was spent on
    was not of the card type the sentence names - "if that mana is spent on a
    **creature** spell" says nothing about the instant it also paid for.
    """
    grant = spend_effect_grant(text)
    if grant is None:
        return []
    card_type, keyword = grant
    if card_type not in permanent.types:
        return []
    return [
        ContinuousEffect(
            description=f"{permanent.name} gains {keyword} (CR 106.6, mana spent on it)",
            layer=Layer.ABILITY,
            timestamp=timestamp,
            duration=Duration.UNTIL_END_OF_TURN,
            selector=only_this_incarnation(permanent, permanent.zone_change_stamp),
            modification=grant_ability(keyword),
        )
    ]


#: "`<Name>` has annihilator X, where X is the number of +1/+1 counters on
#: it." (Ulamog, the Defiler; CR 201.5's own name already rewritten to "this
#: permanent" by `layer_readable_sentences`) - a static ability granting its
#: own object a keyword that takes a number (CR 702.86a's "Annihilator N"),
#: printed or X with its definition. Only a keyword `machines/keywords.py`
#: writes out as a triggered ability is read (`writes_triggered_ability`):
#: the granted line has to become a real ability, not a word on the board.
_SELF_HAS_COUNTED_TRIGGER_KEYWORD_RE = re.compile(
    r"^this (?:creature|permanent) has (?P<keyword>[a-z]+(?: [a-z]+)?) (?P<n>\d+|x)"
    r"(?P<where>,\s*where x is [^.]+)?\.?$",
    re.IGNORECASE,
)


def _self_has_counted_trigger_keyword_builder(
    match: re.Match[str], sentence: str
) -> EffectBuilder | None:
    """`_SELF_HAS_COUNTED_TRIGGER_KEYWORD_RE`'s shape: a layer 6 grant (CR
    613.1f) of "`<Keyword>` `<N>`[, where X is `<expr>`]" to the source itself.

    A static ability's effect (CR 611.3, CR 604.2): timestamped off the
    source (CR 613.7a), and keyed to the printed line (`_source_line_for`) so
    a source that loses the ability grants nothing (CR 613.6). The granted
    line keeps its "where X is ..." definition, so the triggered ability it
    becomes counts X itself as it resolves (CR 608.2h), with "it" still the
    same object.
    """
    from .keywords import writes_triggered_ability

    keyword = match.group("keyword")
    if not writes_triggered_ability(keyword):
        return None
    count = match.group("n").upper()
    where = match.group("where")
    if count == "X" and where is None:
        return None
    granted = f"{keyword.capitalize()} {count}"
    if where is not None:
        definition = re.sub(r"^,\s*where x is\s+", "", where.strip(), flags=re.IGNORECASE)
        granted = f"{granted}, where X is {definition}"

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=f"{source.name} has {granted}",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, sentence),
                selector=_only(source.id),
                modification=grant_ability(granted),
            )
        ]

    return builder


def _keyword_grant_builder(keywords: Sequence[str]) -> EffectBuilder:
    """ "[Subject] gains <keyword>[, <keyword>, and <keyword>] until end of
    turn." (CR 613.1f, CR 113.10) - one or more keywords, each its own layer
    6 grant."""

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
                selector=only_this_incarnation(target, target.zone_change_stamp),
                modification=grant_ability(keyword),
            )
            for target in targets
            for keyword in keywords
        ]

    return builder


def _anthem_builder(
    power: int,
    toughness: int,
    *,
    other: bool,
    whose: str,
    line: str,
    qualifiers: CreatureQualifiers | None = None,
) -> EffectBuilder:
    """ "[As long as <board condition>, ][other] [non<colour>] [land]
    creature[ token]s [you control|your opponents control] get +N/+N."
    (CR 613.4c).

    A static ability's effect (CR 611.3), so it is timestamped off the source
    permanent (CR 613.7a) and switched off the moment the source loses the
    ability (CR 613.6) - `source_ability` is the exact printed sentence,
    matching what layer 6 removal matches on.

    Every qualifier lives in the `Selector` rather than in the effect, because
    CR 611.3a says a static ability's effect "isn't 'locked in'; it applies at
    any given moment to whatever its text indicates". That is what makes the
    board condition and the colour test re-asked on each CR 613.5 computation
    rather than frozen when the permanent entered.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        selector, subject = _creature_group(source, other=other, whose=whose, qualifiers=qualifiers)
        gate = qualifiers.gate_words if qualifiers is not None else ""
        return [
            ContinuousEffect(
                description=f"{source.name}: {gate}{subject} get {power:+d}/{toughness:+d}",
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


def _self_protection_from_chosen_color_builder(*, line: str) -> EffectBuilder:
    """`_SELF_PROTECTION_FROM_CHOSEN_COLOR_RE`'s shape: layer 6 (CR 613.1f)
    grants the source "Protection from <colour>" for the colour recorded on it
    as it entered (CR 614.12a). CR 702.16a: "Protection is a static ability,
    written 'Protection from [quality].'" - once the line is in
    `Characteristics.abilities`, every protection reader (targeting CR
    702.16b, enchant CR 702.16c, equip CR 702.16d, damage CR 702.16e, blocking
    CR 702.16f) reads it like a printed one.

    No colour recorded - a permanent that somehow entered without the choice -
    grants nothing rather than guessing one. Keyed to the printed line
    (`source_ability`), so an ability-removing effect (CR 613.1f) takes the
    protection with it.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        color = chosen_color_of(source)
        if color is None:
            return []
        ability = f"Protection from {color.name.lower()}"
        return [
            ContinuousEffect(
                description=f"{source.name}: has {ability} (the chosen color)",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=_only(source.id),
                modification=grant_ability(ability),
            )
        ]

    return builder


def _per_other_creature_anthem_builder(
    power: int,
    toughness: int,
    *,
    other: bool,
    same_name: bool,
    count_legendary: bool,
    line: str,
    qualifiers: CreatureQualifiers,
) -> EffectBuilder:
    """`_EACH_ANTHEM_PER_OTHER_CREATURE_RE`'s shape: `_anthem_builder`'s live
    qualified group (CR 611.3a), pumped in layer 7c (CR 613.4c) by a count
    taken separately for each creature in it (`CountOtherCreaturesLikeThatOne`)
    rather than once for the whole group.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        selector, subject = _creature_group(
            source, other=other, whose="you control", qualifiers=qualifiers
        )
        counted = (
            f"other {'legendary ' if count_legendary else ''}creature you control"
            f"{' with the same name as that creature' if same_name else ''}"
        )
        return [
            ContinuousEffect(
                description=f"{source.name}: {subject} each get "
                f"{power:+d}/{toughness:+d} for each {counted}",
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=selector,
                modification=modify_power_toughness_per(
                    CountOtherCreaturesLikeThatOne(
                        username=source.controller,
                        same_name=same_name,
                        legendary=count_legendary,
                    ),
                    power,
                    toughness,
                ),
            )
        ]

    return builder


def _anthem_and_keyword_grant_builder(
    power: int,
    toughness: int,
    keywords: list[str],
    *,
    other: bool,
    whose: str,
    line: str,
    qualifiers: CreatureQualifiers | None = None,
    per: tuple[str, ControlledCountFactory] | None = None,
) -> EffectBuilder:
    """ "[Qualified subject] get +N/+N and have <keyword(s)>." - `_anthem_
    builder`'s pump plus `_indefinite_keyword_grant_builder`'s keywords, one
    ability landing in both sublayer 7c (CR 613.4c) and layer 6 (CR 613.1f)
    over the same live selector (CR 611.3a).

    `per` is `_ANTHEM_PER_COUNT_RE`'s "for each `<qualifier>` you control":
    the printed word and the factory of the count the pump is multiplied by,
    built for the source's controller and counted live off the board.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        selector, subject = _creature_group(source, other=other, whose=whose, qualifiers=qualifiers)
        gate = qualifiers.gate_words if qualifiers is not None else ""
        pump = f"{power:+d}/{toughness:+d}"
        modification: Modification = modify_power_toughness(power, toughness)
        if per is not None:
            word, count = per
            pump = f"{pump} for each {word} you control"
            modification = modify_power_toughness_per(count(source.controller), power, toughness)
        effects = [
            ContinuousEffect(
                description=f"{source.name}: {gate}{subject} get {pump}",
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=line,
                selector=selector,
                modification=modification,
            )
        ]
        effects.extend(
            ContinuousEffect(
                description=f"{source.name}: {gate}{subject} have {keyword}",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=line,
                selector=selector,
                modification=grant_ability(keyword),
            )
            for keyword in keywords
        )
        return effects

    return builder


def _mass_pump_until_eot_builder(
    power: int | None, toughness: int | None, keywords: list[str]
) -> EffectBuilder:
    """ "[Other] creatures [you control|your opponents control] [gain <keyword(s)>
    and ]get +N/+N until end of turn." (CR 611.2) - or, with `power`/
    `toughness` both `None`, the keyword-only twin with no power/toughness
    change at all ("Creatures you control gain first strike until end of
    turn."): no sublayer 7c modifier is built for that shape, only the
    layer 6 grant(s) below.

    Unlike `_anthem_builder`'s live `Selector` - right because a *static*
    ability's group (CR 611.3) has to keep re-including whoever is on the
    battlefield the moment CR 613.5 recomputes it - this is CR 611.2c's
    fixed-at-resolution shape: "the set of objects it affects is determined
    when the effect begins ... any objects that come under [that] control
    later aren't affected." The caller (`machines/effects.py`'s
    `_run_mass_pump`) resolves `targets` to the concrete creatures this
    affects once, before calling, the same way `_pump_and_keyword_builder`
    already fixes a single subject's id rather than re-selecting it - a
    creature that enters afterward is never swept in, and the sublayer 7c
    modifier plus each layer 6 grant are set-once, not recomputed.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        effects: list[ContinuousEffect] = []
        for target in targets:
            if power is not None and toughness is not None:
                effects.append(
                    ContinuousEffect(
                        description=f"{source.name}: {target.name} gets {power:+d}/{toughness:+d}",
                        layer=Layer.POWER_TOUGHNESS,
                        sublayer=Sublayer.MODIFY,
                        timestamp=timestamp,
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=only_this_incarnation(target, target.zone_change_stamp),
                        modification=modify_power_toughness(power, toughness),
                    )
                )
            for keyword in keywords:
                effects.append(
                    ContinuousEffect(
                        description=f"{source.name}: {target.name} gains {keyword}",
                        layer=Layer.ABILITY,
                        timestamp=timestamp,
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=only_this_incarnation(target, target.zone_change_stamp),
                        modification=grant_ability(keyword),
                    )
                )
        return effects

    return builder


def _creature_group(
    source: CardState,
    *,
    other: bool,
    whose: str,
    qualifiers: CreatureQualifiers | None = None,
) -> tuple[Selector, str]:
    """The selector and printed subject `_anthem_builder` and
    `_indefinite_keyword_grant_builder` share: "[other] [non<colour>] [land]
    creature[ token]s [you control|your opponents control]", read off the same
    regex groups both shapes parse.

    With no qualifiers this is exactly the three plain shapes it always was,
    and the named selectors are kept for those so `machines/effects.py`'s
    imports and every existing journal line read the same. A qualified subject
    composes `qualified_creatures` instead.
    """
    qualifiers = qualifiers or CreatureQualifiers()
    opponents = whose != "you control"
    if qualifiers.is_empty:
        if opponents:
            return (
                creatures_controlled_by_opponents_of(source.controller),
                "creatures your opponents control",
            )
        selector = (
            other_creatures_controlled_by(source.id, source.controller)
            if other
            else creatures_controlled_by(source.controller)
        )
        return selector, "other creatures you control" if other else "creatures you control"
    return (
        qualified_creatures(
            source.id,
            source.controller,
            other=other,
            opponents=opponents,
            without_color=qualifiers.without_color,
            land=qualifiers.land,
            also_artifact=qualifiers.also_artifact,
            tokens=qualifiers.tokens,
            gate_card_type=qualifiers.gate_card_type,
            gate_threshold=qualifiers.gate_threshold,
            nontoken=qualifiers.nontoken,
            legendary=qualifiers.legendary,
            of_chosen_color=qualifiers.of_chosen_color,
            chosen_color=chosen_color_of(source) if qualifiers.of_chosen_color else None,
        ),
        f"{'other ' if other else ''}{qualifiers.words}"
        f"{'creature tokens' if qualifiers.tokens else 'creatures'} "
        f"{'your opponents control' if opponents else 'you control'}"
        f"{_chosen_color_words(source) if qualifiers.of_chosen_color else ''}",
    )


def chosen_color_of(source: CardState) -> Color | None:
    """The colour `source` chose as it entered (CR 614.12a), or `None` if it
    recorded no colour choice - read off `CardState.choice`, where
    `machines/replacement.py` stores every "as [this] enters, choose ..."
    answer."""
    chosen = source.choice
    if chosen is None or chosen.kind is not ChoiceKind.COLOR:
        return None
    try:
        return Color(chosen.value)
    except ValueError:
        return None


def _chosen_color_words(source: CardState) -> str:
    """ " of the chosen color (green)" for a journal line."""
    color = chosen_color_of(source)
    word = color.name.lower() if color is not None else "none chosen"
    return f" of the chosen color ({word})"


class CreatureQualifiers(EngineModel):
    """The qualifier words a printed anthem subject may carry, parsed once and
    handed to `_creature_group`.

    `without_color` is the colour a "non<colour>" prefix rules out (CR 105.2),
    `land` and `tokens` are the "land creatures" and "creature tokens" nouns,
    and `gate_card_type`/`gate_threshold` are the whole-board "as long as you
    control N or more <card type>s" condition printed in front of the sentence.

    The gate is stored as a count, not as a closure, because the player it
    counts for is the *source's* controller and nothing at parse time knows
    who that is - `_creature_group` passes `gate_card_type`/`gate_threshold`
    straight through to `qualified_creatures` once it has the permanent, and
    `QualifiedCreatures.__call__` (the `Selector` that produces) does the
    counting itself rather than closing over a board-checking function.
    `words` and `gate_words` are only the printed prefixes, for the journal
    line.
    """

    model_config = ConfigDict(frozen=True)

    without_color: Color | None = None
    color_word: str | None = None
    land: bool = False
    also_artifact: bool = False
    tokens: bool = False
    gate_card_type: Type | None = None
    gate_threshold: int = 0
    gate_words: str = ""
    nontoken: bool = False
    legendary: bool | None = None
    of_chosen_color: bool = False

    @property
    def is_empty(self) -> bool:
        return (
            self.without_color is None
            and not self.land
            and not self.also_artifact
            and not self.tokens
            and self.gate_card_type is None
            and not self.nontoken
            and self.legendary is None
            and not self.of_chosen_color
        )

    @property
    def words(self) -> str:
        prefix = ""
        if self.color_word is not None:
            prefix += f"non{self.color_word} "
        if self.legendary is not None:
            prefix += "legendary " if self.legendary else "nonlegendary "
        if self.nontoken:
            prefix += "nontoken "
        if self.land:
            prefix += "land "
        if self.also_artifact:
            prefix += "artifact "
        return prefix


def qualifiers_from_subject(
    match: re.Match[str], gate: CreatureQualifiers | None = None
) -> CreatureQualifiers:
    """The `_QUALIFIED_CREATURE_SUBJECT` groups of a match, as qualifiers.

    `gate` carries the board condition parsed off the sentence in front of the
    subject, when there was one; everything else comes off the subject itself.
    """
    color_word = match.group("noncolor")
    legendary = match.group("legendary")
    base = gate or CreatureQualifiers()
    return base.model_copy(
        update={
            "without_color": _COLOR_WORDS[color_word.lower()] if color_word else None,
            "color_word": color_word.lower() if color_word else None,
            "land": match.group("land") is not None,
            "also_artifact": match.group("artifact") is not None,
            "tokens": match.group("noun").lower() in ("creature tokens", "creature token"),
            "nontoken": match.group("nontoken") is not None,
            "legendary": None if legendary is None else not legendary.lower().startswith("non"),
            "of_chosen_color": match.group("chosen") is not None,
        }
    )


def _indefinite_keyword_grant_builder(
    abilities: list[str],
    *,
    other: bool,
    whose: str,
    line: str,
    qualifiers: CreatureQualifiers | None = None,
) -> EffectBuilder:
    """ "[Other] [non<colour>] [land] creature[ token]s [you control|your
    opponents control] have <keyword(s)>." (True Conviction's plain form; Aang,
    Destined Savior's "Land creatures you control have vigilance.") - layer 6
    (CR 613.1f), one grant per ability.

    `abilities` is not only bare keywords: Akroma's Memorial's own "... and
    protection from black and from red" reaches here too, as "Protection from
    black" and "Protection from red" - CR 702.16a's protection ability is
    still an ability-adding effect in layer 6, it just has no name of its own
    in `_KNOWN_KEYWORDS`. Either way `grant_ability` only ever adds a line of
    text to `Characteristics.abilities`; nothing here cares which kind it is.

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
        selector, subject = _creature_group(source, other=other, whose=whose, qualifiers=qualifiers)
        gate = qualifiers.gate_words if qualifiers is not None else ""
        return [
            ContinuousEffect(
                description=f"{source.name}: {gate}{subject} have {ability}",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=line,
                selector=selector,
                modification=grant_ability(ability),
            )
            for ability in abilities
        ]

    return builder


def _during_your_turn_multi_type_keyword_grant_builder(
    card_types: tuple[Type, ...], abilities: list[str], *, line: str
) -> EffectBuilder:
    """ "During your turn, `<type> and <type>` you control have `<keyword(s)>`."
    - Sorin, Vengeful Bloodlord's own "During your turn, creatures and
    planeswalkers you control have lifelink." Two things set this apart from
    the plain `_indefinite_keyword_grant_builder` above: the subject names
    more than one card type at once (`PermanentsOfTypesControlledBy`, not
    `CreaturesControlledBy`), and the whole grant only applies during the
    source's own controller's turn (`LayerContext.active_player`), checked
    once at build time the same way `_graveyard_count_gated_self_static_
    builder`'s graveyard count is - `effects_for` reruns on every `computed_
    board()` (CR 613.5), so the grant disappears the instant the turn passes
    with nothing to store or clear.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        if context.active_player != source.controller:
            return []
        selector = PermanentsOfTypesControlledBy(username=source.controller, card_types=card_types)
        types_text = " and ".join(f"{card_type.value}s" for card_type in card_types)
        return [
            ContinuousEffect(
                description=(
                    f"{source.name}: {types_text} you control have {ability} during your turn"
                ),
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=line,
                selector=selector,
                modification=grant_ability(ability),
            )
            for ability in abilities
        ]

    return builder


def _counter_gated_keyword_grant_builder(
    counter_kind: str, keywords: list[str], *, other: bool, line: str
) -> EffectBuilder:
    """ "Each [other] creature you control with a[n] <counter kind> counter on
    it has <keyword(s)>." (Gallia, the Merrymaker's haste; Vigorbloom
    Vanguard's vigilance) - `_indefinite_keyword_grant_builder`'s twin over
    `creatures_controlled_by_with_counter` instead of the plain team, since
    CR 611.3a's "isn't 'locked in'" applies here too: a creature that loses
    its last counter of that kind drops out of the grant immediately.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        selector = creatures_controlled_by_with_counter(
            source.controller, counter_kind, other_than=source.id if other else None
        )
        subject = (
            f"each {'other ' if other else ''}creature you control with a "
            f"{counter_kind} counter on it"
        )
        return [
            ContinuousEffect(
                description=f"{source.name}: {subject} has {keyword}",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=selector,
                modification=grant_ability(keyword),
            )
            for keyword in keywords
        ]

    return builder


def _lands_keyword_grant_builder(keywords: list[str], *, line: str) -> EffectBuilder:
    """ "Lands you control have <keyword(s)>." (Marwyn, the Preserver's
    hexproof) - the land-subject twin of `_indefinite_keyword_grant_builder`,
    over `lands_controlled_by` instead of a creature selector.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        selector = lands_controlled_by(source.controller)
        return [
            ContinuousEffect(
                description=f"{source.name}: lands you control have {keyword}",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
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
                selector=only_this_incarnation(target, target.zone_change_stamp),
                modification=set_power_toughness(power, toughness),
            )
            for target in targets
        ]

    return builder


def _becomes_creature_type_with_base_pt_builder(
    subtype: str,
    color: Color | None,
    power: int,
    toughness: int,
    *,
    loses_abilities: bool,
) -> EffectBuilder:
    """`_BECOMES_CREATURE_TYPE_WITH_BASE_PT_RE`'s shape: one resolving effect
    applied in each layer it names (CR 613.6), until end of turn, to each
    target's current incarnation (CR 400.7)."""

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        effects: list[ContinuousEffect] = []
        for target in targets:
            selector = only_this_incarnation(target, target.zone_change_stamp)
            parts: list[tuple[str, Layer, Sublayer | None, Modification]] = [
                (f"is a {subtype}", Layer.TYPE, None, SetCreatureTypes(subtypes=(subtype,)))
            ]
            if color is not None:
                parts.append((f"is {color.name.lower()}", Layer.COLOR, None, set_colors(color)))
            if loses_abilities:
                parts.append(("loses all abilities", Layer.ABILITY, None, lose_all_abilities))
            parts.append(
                (
                    f"has base P/T {power}/{toughness}",
                    Layer.POWER_TOUGHNESS,
                    Sublayer.SET,
                    set_power_toughness(power, toughness),
                )
            )
            effects.extend(
                ContinuousEffect(
                    description=f"{source.name}: {target.name} {what}",
                    layer=layer,
                    sublayer=sublayer,
                    timestamp=timestamp,
                    duration=Duration.UNTIL_END_OF_TURN,
                    selector=selector,
                    modification=modification,
                )
                for what, layer, sublayer, modification in parts
            )
        return effects

    return builder


def _becomes_type_in_addition_builder(extra_type: Type) -> EffectBuilder:
    """ "Target permanent becomes an artifact in addition to its other types
    until end of turn." (Liquimetal Coating) - layer 4 only (CR 613.1d),
    additive: `add_type` keeps every type the permanent already had, which is
    the whole difference from Karn's "becomes a[n] <type> creature" shape
    above (that one *replaces* the target's types with the ones it names,
    CR 205.1a - it just happens to name the old type again alongside the
    new one). One-shot and temporary (CR 611.2), unlike a static ability's
    indefinite grant, so it is timestamped and fixed to `targets` here the
    same way `_pump_and_keyword_builder` fixes its own single subject.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=f"{source.name}: {target.name} becomes a "
                f"{extra_type.value} in addition to its other types",
                layer=Layer.TYPE,
                timestamp=timestamp,
                duration=Duration.UNTIL_END_OF_TURN,
                selector=only_this_incarnation(target, target.zone_change_stamp),
                modification=add_type(extra_type),
            )
            for target in targets
        ]

    return builder


def _becomes_subtype_in_addition_builder(
    subtypes: Sequence[str], keywords: Sequence[str], duration: Duration
) -> EffectBuilder:
    """`_BECOMES_SUBTYPE_IN_ADDITION_RE`'s shape: one layer 4 subtype
    addition per creature type (CR 613.1d; CR 205.1b keeps every prior type)
    and one layer 6 grant per keyword (CR 613.1f), all built from the one
    resolution and so sharing its one timestamp (CR 613.7b), fixed to the
    objects the caller resolved (CR 611.2c)."""

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        effects: list[ContinuousEffect] = []
        for target in targets:
            selector = only_this_incarnation(target, target.zone_change_stamp)
            effects.extend(
                ContinuousEffect(
                    description=f"{source.name}: {target.name} becomes a {subtype} "
                    "in addition to its other types",
                    layer=Layer.TYPE,
                    timestamp=timestamp,
                    duration=duration,
                    selector=selector,
                    modification=add_subtype(subtype),
                )
                for subtype in subtypes
            )
            effects.extend(
                ContinuousEffect(
                    description=f"{source.name}: {target.name} gains {keyword}",
                    layer=Layer.ABILITY,
                    timestamp=timestamp,
                    duration=duration,
                    selector=selector,
                    modification=grant_ability(keyword),
                )
                for keyword in keywords
            )
        return effects

    return builder


def _creature_type_words(raw: str) -> list[str] | None:
    """ "Avatar" / "Monk Avatar" -> each CR 205.3m creature type as the
    official list spells it, or `None` if any word is not one."""
    known = {kind.lower(): kind for kind in creature_types()}
    words = raw.split()
    found = [known.get(word.lower()) for word in words]
    if not words or any(word is None for word in found):
        return None
    return [word for word in found if word is not None]


def _gain_control_until_eot_builder() -> EffectBuilder:
    """`_GAIN_CONTROL_UNTIL_EOT_RE`'s shape - Threaten's control half.

    Layer 2 (CR 613.1b), lasting until end of turn (CR 611.2a: "as long as
    stated by the spell or ability"), and the new controller is the resolving
    spell's or ability's own controller - "*you* gain control", CR 611.2's
    effect belongs to whoever controlled the object that created it.

    `only_this_incarnation` rather than `_only`: a creature that leaves the
    battlefield and comes back is a new object with no relation to the one
    this effect was applied to (CR 400.7), and CR 400.7a's carry-over is
    written about a permanent *spell* on the stack becoming a permanent, not
    about a permanent that died. DDR#989 turns on exactly that: the stolen
    land is sacrificed and returns under the earthbender's control, not the
    thief's.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        if source.controller is None:
            return []
        return [
            ContinuousEffect(
                description=f"{source.name}: {source.controller} gains control of {target.name}",
                layer=Layer.CONTROL,
                timestamp=timestamp,
                duration=Duration.UNTIL_END_OF_TURN,
                selector=only_this_incarnation(target, target.zone_change_stamp),
                modification=set_controller(source.controller),
            )
            for target in targets
        ]

    return builder


def _becomes_color_builder(color: Color, *, until_eot: bool) -> EffectBuilder:
    """ "[Subject] becomes `<colour>`." - Purelace's "Target spell or permanent
    becomes white." (confirmed with `resolve_cards`).

    Layer 5 (CR 613.1e: "Layer 5: Color-changing effects are applied"), and a
    *set* rather than an addition: CR 105.2 has no "in addition to its other
    colors" wording on this template, so `set_colors` replaces whatever the
    object had. Purelace's own reminder text - "(Mana symbols on that permanent
    remain unchanged.)" - is the rules consequence of that, not an exception to
    it: the mana cost is untouched, and only the *derived* colour (CR 202.2)
    is overwritten here.

    **No duration** unless the sentence prints one. CR 611.2a fixes a
    resolution effect's duration at "as long as stated by the spell or
    ability", and Purelace states none, so the change is permanent - which is
    what makes DDR#32 a question about layers at all rather than about the
    turn ending.

    The selector keys on the **`CardState.id`** rather than on
    `only_this_incarnation`'s zone-change stamp, and that is the whole of
    CR 400.7a: "Effects from spells, activated abilities, and triggered
    abilities that change the characteristics or controller of a permanent
    spell on the stack continue to apply to the permanent that spell becomes."
    Purelace is cast at a Clone still on the stack; the stamp is reissued when
    that spell resolves onto the battlefield, and a stamped selector would
    quietly drop the effect at exactly the moment CR 400.7a says it must
    survive. The id does not change, so keying on it carries the colour over
    for free.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=f"{source.name}: {target.name} becomes {color.value}",
                layer=Layer.COLOR,
                timestamp=timestamp,
                duration=Duration.UNTIL_END_OF_TURN if until_eot else Duration.INDEFINITE,
                selector=_only(target.id),
                modification=set_colors(color),
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
                    selector=only_this_incarnation(target, target.zone_change_stamp),
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
                    selector=only_this_incarnation(target, target.zone_change_stamp),
                    modification=set_power_toughness_to_mana_value,
                )
            )
        return effects

    return builder


# --------------------------------------------------------------------------
# Filtered subsets, per-object conditions, and gated self-statics
# --------------------------------------------------------------------------
#
# Every shape below is CR 611.3's static ability again, differing only in who
# it picks out: a creature subtype rather than the whole team, one colour at a
# time, the equipped creature (CR 301.5a/301.5f), or the source itself behind a
# condition. None of them was expressible before, so each of these cards
# generated nothing at all.

#: "Other Dragons you control get +1/+1." (Stormscale Scion) - CR 205.3m's
#: bare creature-type plural standing in for "creatures", the static twin of
#: `machines/effects.py`'s `_MASS_SUBTYPE_SUBJECT_RE`. Deliberately
#: case-sensitive on the subtype: Oracle text only ever capitalizes a creature
#: type, and `_ANTHEM_RE`'s literal "creatures" is tried first, so this never
#: intercepts the plain anthem.
#:
#: `subtypes` is one capitalised plural or several joined by "and"/"or"/commas
#: - Nightpack Ambusher's "Other Wolves and Werewolves you control get +1/+1."
#: and Warg Rider's "Other Orcs and Goblins you control have menace." print the
#: same group as a two-item list. Each item is read back to its type-line
#: singular by `_subtype_list_words` (`data/subtypes.canonical_subtype`, so
#: "Wolves" is "Wolf", not "Wolve"), and the group is any one of them.
_SUBTYPE_LIST = r"(?P<subtypes>[A-Z][a-z-]+(?:(?:,| and|, and| or|, or) [A-Z][a-z-]+)*)"
_SUBTYPE_ANTHEM_RE = re.compile(
    rf"^(?P<other>[Oo]ther )?{_SUBTYPE_LIST} you control get "
    r"(?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)\.?$"
)

#: "Thopters you control have haste." (Saheeli, Jewel of Avishkar) - the same
#: bare creature-type subject as `_SUBTYPE_ANTHEM_RE`, granting a keyword
#: instead of (or, "Vigorbloom Vanguard" style, this shape stays keyword-only;
#: the pump-and-keyword combination has no printed example yet) modifying
#: power/toughness. Case-sensitive on the subtype for the same reason
#: `_SUBTYPE_ANTHEM_RE` is: Oracle text only ever capitalizes a creature type.
_SUBTYPE_KEYWORD_GRANT_RE = re.compile(
    rf"^(?P<other>[Oo]ther )?{_SUBTYPE_LIST} you control "
    r"(?:have|has) (?P<keywords>[a-z]+(?: [a-z]+)?(?:(?:,\s*| and )[a-z]+(?: [a-z]+)?)*)\.?$"
)

#: "Each other creature you control that's a Cat, Elemental, Nightmare,
#: Dinosaur, or Beast gets +1/+1 and has vigilance." (Kaheera, the Orphanguard,
#: confirmed with `resolve_cards`) - the same filtered subset written out as a
#: subtype list, with a keyword grant riding along. Sublayer 7c for the pump
#: (CR 613.4c) and layer 6 for the keyword (CR 613.1f), one ability applying in
#: two layers (CR 613.6).
_FILTERED_CREATURE_ANTHEM_RE = re.compile(
    r"^each (?P<other>other )?creature you control that's an? "
    r"(?P<subtypes>[A-Za-z][A-Za-z, ]*?) gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)"
    r"(?: and has (?P<keywords>[a-z]+(?: [a-z]+)?(?:(?:,\s*| and )[a-z]+(?: [a-z]+)?)*))?\.?$",
    re.IGNORECASE,
)

#: "This permanent's power and toughness are each equal to the number of basic
#: land types among lands you control." - Territorial Kavu's *domain* ability,
#: with its own name already rewritten to "this permanent" by
#: `self_normalized_effect_text` and the ability word stripped (CR 207.2c:
#: "Ability words ... have no special rules meaning").
#:
#: A characteristic-defining ability (CR 604.3a: "(1) It defines an object's
#: colors, subtypes, power, or toughness; (2) it is printed on the card it
#: affects"), which is why it lands in sublayer 7a (CR 613.4a) rather than 7c -
#: CR 208.2a is the printed side of it, the `*` in the power box.
_BASIC_LAND_TYPE_COUNT_CDA_RE = re.compile(
    r"^this (?:creature|permanent|token)'s power and toughness are each equal to the "
    r"number of basic land types among lands you control\.?$",
    re.IGNORECASE,
)

#: "This permanent's power and toughness are each equal to the number of
#: creatures you control that are `<subtype>`[ and/or `<subtype>`...]." - The
#: Mycotyrant's own CDA ("... Fungi and/or Saprolings"), read generally
#: rather than as a `Boneyard Wurm`-shaped hardcoded row: any number of
#: subtypes, joined by "and/or", plain "or", or a comma list, counts a
#: creature that has *any* of them (CR 205.3's own "and/or" reads as an
#: inclusive "or" - a Fungus Saproling counts once, not twice).
_CREATURE_SUBTYPE_COUNT_CDA_RE = re.compile(
    r"^this (?:creature|permanent|token)'s power and toughness are each equal to the "
    r"number of creatures you control that are "
    r"(?P<subtypes>[a-z]+(?:(?:,\s*| and/or | and | or )[a-z]+)*)\.?$",
    re.IGNORECASE,
)


def _creature_subtype_count_cda_builder(subtypes: tuple[str, ...], *, line: str) -> EffectBuilder:
    """`_CREATURE_SUBTYPE_COUNT_CDA_RE`'s shape - see its own docstring.

    Sublayer 7a (CR 613.4a), the same choice `_basic_land_type_count_cda_
    builder` makes - a CDA defines the value, it never modifies one
    (CR 613.4a against CR 613.4c) - counted live off the board through
    `CountCreaturesWithSubtypesControlledBy` rather than baked in at build
    time, since (unlike Boneyard Wurm's graveyard count) the battlefield is
    already the board the layer engine threads through every `Count` here.

    `source_ability` is `_source_line_for(source, line)`, not `line` itself -
    The Mycotyrant's own printed name is rewritten to "this permanent" by
    `self_normalized_effect_text` on the way to `_parse_layer_sentence`
    (Territorial Kavu's own defect, `_source_line_for`'s docstring), and
    `_still_exists` matches `source_ability` against `Characteristics.
    abilities`, which is the card's lines verbatim - the normalized sentence
    is never one of them, so without this the effect would look, to CR
    613.6's own "has this ability been removed" question, like it already had
    been, and never apply at all.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=(
                    f"{source.name}: power/toughness equal to the number of creatures "
                    f"you control that are {' and/or '.join(subtypes)}"
                ),
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.CHARACTERISTIC_DEFINING,
                characteristic_defining=True,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=_only(source.id),
                modification=define_power_toughness(
                    CountCreaturesWithSubtypesControlledBy(
                        username=source.controller, subtypes=subtypes
                    )
                ),
            )
        ]

    return builder


#: "This permanent's power is equal to the number of basic land types among
#: lands you control." (Fblthp, Knows the Way; Nishoba Brawler,
#: `resolve_cards`-confirmed identical wording) - *domain*'s power-only twin:
#: only the power box is `*` (CR 208.2a), the printed toughness is an ordinary
#: number (CR 208.1) that no ability names, so `define_power` is used in place
#: of `_basic_land_type_count_cda_builder`'s `define_power_toughness`, the same
#: split Nighthawk Scavenger's own power-only CDA already draws.
_BASIC_LAND_TYPE_COUNT_POWER_ONLY_CDA_RE = re.compile(
    r"^this (?:creature|permanent|token)'s power is equal to the "
    r"number of basic land types among lands you control\.?$",
    re.IGNORECASE,
)

#: "Equipped creature gets +1/+1 and has trample and haste." (Cori-Steel
#: Cutter); "Enchanted creature gets +2/+0 and has trample." (Rancor);
#: `Equipped creature has "{3}, {Q}: This creature gets +2/+2 until end of
#: turn."` (Umbral Mantle). One shape, three phrasings.
#:
#: CR 301.5a: "The creature an Equipment is attached to is called the
#: 'equipped creature'", and CR 301.5f extends the phrase to any permanent that
#: uses it. CR 303.4b is the Aura's identical sentence: "The object or player
#: an Aura is attached to is called enchanted." Both words name the same fact -
#: `CardState.attached_to` - so both belong to one regex rather than to two
#: kept in step by hand. The subject is read off the source's own `attached_to`
#: link rather than the board, since attachment is not a characteristic.
#:
#: The quoted branch is CR 113.10a's ability-adding grant with the granted
#: ability written out in full: "An effect that adds an activated ability may
#: include activation instructions for that ability. These instructions become
#: part of the ability that's added to the object." It is tried before the bare
#: keyword branch, because the quoted text is not a keyword list and must never
#: be read as one.
#: "Equipped creature gets +2/+0 and has "Whenever this creature attacks, it
#: gains your choice of trample or deathtouch until end of turn."" (Hunter's
#: Axe); "Equipped creature gets +1/+0 and has flying and "Whenever this
#: creature attacks, you gain 1 life."" (Medic's Kitesail) -
#: `_ATTACHED_CREATURE_STATIC_RE`'s "gets P/T[ and has <keywords>]" branch
#: extended with an optional trailing quoted ability, tried first since it is
#: the more specific shape. Both a bare keyword list and a quoted grant can
#: ride the same "and has" the pool already prints separately for each.
_ATTACHED_CREATURE_PUMP_AND_QUOTED_RE = re.compile(
    r"^(?P<attachment>equipped|enchanted) creature gets (?P<power>[+-]\d+)/"
    r"(?P<toughness>[+-]\d+) and has "
    r"(?:(?P<keywords>[a-z]+(?: [a-z]+)?(?:(?:,\s*| and )[a-z]+(?: [a-z]+)?)*) and )?"
    r'"(?P<granted>.+)"\.?$',
    re.IGNORECASE | re.DOTALL,
)

_ATTACHED_CREATURE_STATIC_RE = re.compile(
    r"^(?P<attachment>equipped|enchanted) creature "
    r"(?:gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)"
    # Non-greedy: a greedy `.+` swallows the sentence's own trailing period
    # into the captured keyword list itself ("hexproof from monocolored."),
    # which then fails `_split_and_validate_keywords`'s tokenizer outright -
    # not just on the new "from <quality>" shape but on the plain
    # "trample and haste." case too. Non-greedy backtracks down to the
    # shortest match that still lets the trailing `\.?$` consume the period.
    r"(?: and has (?P<keywords>[a-z].+?))?"
    r'|has "(?P<granted>.+)"'
    # CR 111.10j's Cursed Role: "Enchanted creature has base power and
    # toughness 1/1." - a *set* (sublayer 7b, CR 613.4b), not the `gets`
    # branch's *modify* (7c). No "until end of turn": the Role's grant is a
    # static ability with no stated duration, unlike `_BASE_PT_SET_RE`'s
    # temporary shape above.
    r"|has base power and toughness (?P<base_power>\d+)/(?P<base_toughness>\d+)"
    r"|has (?P<only_keywords>[a-z].+?))\.?$",
    re.IGNORECASE | re.DOTALL,
)

#: "Enchanted creature loses all abilities and is a Toy artifact creature with
#: base power and toughness 0/2 in addition to its other types." (Unable to
#: Scream, read with `resolve_cards`) - one Aura sentence that lands in three
#: layers at once (CR 613.6): layer 6 removes every ability (CR 613.1f), layer
#: 4 adds the card types and the creature type (CR 613.1d, CR 205.1b's "in
#: addition to its other types"), and sublayer 7b sets the base power and
#: toughness (CR 613.4b: "Effects that ... refer to the base power and/or
#: toughness of a creature apply in this layer").
#:
#: Written as its own shape rather than folded into
#: `_ATTACHED_CREATURE_STATIC_RE` because none of that regex's branches is a
#: type change, and a half-read sentence would be worse than an unread one.
_ATTACHED_CREATURE_LOSES_AND_BECOMES_RE = re.compile(
    r"^(?P<attachment>[Ee]quipped|[Ee]nchanted) creature loses all abilities and is an? "
    r"(?P<subtype>[A-Z][a-z]+) (?P<types>[a-z]+(?: [a-z]+)*) with base power and toughness "
    r"(?P<power>\d+)/(?P<toughness>\d+) in addition to its other types\.?$"
)

#: "Enchanted permanent is a Construct creature with base power and
#: toughness 5/5 in addition to its other types." (Puppet Crafting);
#: "Enchanted artifact is a creature with base power and toughness 5/5 in
#: addition to its other types." (Ensoul Artifact, no subtype at all);
#: "Enchanted artifact is a Golem creature with base power and toughness
#: 5/4 in addition to its other types." (Zoetic Glyph) - one shape, an
#: optional subtype. `_ATTACHED_CREATURE_LOSES_AND_BECOMES_RE`'s twin with no
#: "loses all abilities" and a bare "permanent"/"artifact" subject rather
#: than "creature", since the whole point is animating something that was
#: not a creature yet.
_ATTACHED_PERMANENT_BECOMES_CREATURE_RE = re.compile(
    r"^(?P<attachment>[Ee]quipped|[Ee]nchanted) (?P<subject>permanent|artifact|enchantment) is "
    r"an? (?:(?P<subtype>[A-Z][a-z]+) )?creature with base power and toughness "
    r"(?P<power>\d+)/(?P<toughness>\d+) in addition to its other types\.?$"
)

#: "Creatures entering don't cause abilities to trigger." (Torpor Orb);
#: "Artifacts and creatures entering the battlefield don't cause abilities to
#: trigger." (Karn, Argent Defender) - an and-joined card-type list, "the
#: battlefield" optional (Torpor Orb's own Oracle wording drops it).
_DONT_CAUSE_TRIGGERS_RE = re.compile(
    r"^(?P<types>[a-z]+(?:,\s*[a-z]+)*(?:\s+and\s+[a-z]+)?) entering(?: the battlefield)? "
    r"don'?t cause abilities to trigger\.?$",
    re.IGNORECASE,
)

#: "Traxos, Scourge Eternal doesn't untap during your untap step." - the
#: card's own name is already rewritten to "this permanent" by `self_
#: normalized_effect_text`. Basalt Monolith's identical shape on an artifact
#: proves this is the mechanic, not the creature type.
_SELF_DOESNT_UNTAP_RE = re.compile(
    r"^this (?:creature|artifact|permanent|token) doesn'?t untap during your "
    r"untap step\.?$",
    re.IGNORECASE,
)

#: "Enchanted creature [loses all abilities and ]doesn't untap during its
#: controller's untap step." (Infinite Coursework and Enchanted River's Grasp
#: share the combined form; Apathy and Bind the Monster print the plain one).
_ATTACHED_DOESNT_UNTAP_RE = re.compile(
    r"^(?P<attachment>equipped|enchanted) (?P<subject>creature|permanent|artifact) "
    r"(?:(?P<loses>loses all abilities) and )?doesn'?t untap during its "
    r"controller'?s untap step\.?$",
    re.IGNORECASE,
)

#: "Other creatures are Food artifacts in addition to their other types and
#: have "{2}, {T}, Sacrifice this permanent: You gain 3 life."" (Ygra, Eater of
#: All, read out of the pool fixture) - a board-wide type grant that reaches
#: *every* other creature, not only its controller's, with a quoted ability
#: riding along.
#:
#: Not `_BOARD_WIDE_TYPE_GRANT_RE`'s shape: that one is scoped by "you control"
#: and names no subtype. Layer 4 for the card type and the subtype (CR 613.1d),
#: layer 6 for the quoted ability (CR 613.1f, CR 113.10a).
_OTHER_CREATURES_ARE_TYPE_RE = re.compile(
    r"^(?P<other>[Oo]ther )?[Cc]reatures are (?P<subtype>[A-Z][a-z]+) (?P<granted>[a-z]+) "
    r"in addition to their other types"
    r'(?: and have "(?P<ability>.+)")?\.?$',
    re.DOTALL,
)

#: "Each nonland permanent you control is all colors." (Leyline of the
#: Guildpact) - layer 5 (CR 613.1e: "Layer 5: Color-changing effects are
#: applied"), setting the object to all five (CR 105.1's colours; CR 105.2's
#: "An object can be one or more of the five colors").
_ALL_COLORS_RE = re.compile(
    r"^each (?P<nonland>nonland )?permanent you control is all colors\.?$",
    re.IGNORECASE,
)

#: "As long as there are four or more card types among cards in your graveyard,
#: this creature gets +2/+2, has flying, and attacks each combat if able."
#: (Dragon's Rage Channeler's *delirium* ability, the ability word stripped -
#: CR 207.2c). A static ability whose effect exists only while its condition
#: holds (CR 604.2: "These effects are active as long as the permanent with the
#: ability remains on the battlefield and has the ability"), rebuilt from the
#: graveyard every time the board is computed (CR 613.5), so no stored
#: `Duration` is involved at all: when the condition is false the sweep simply
#: produces no effect.
#:
#: The pile counted is the only thing the two printings of this shape differ
#: in: delirium's "cards in your graveyard", or Keen-Eyed Curator's "cards
#: exiled with this creature" - CR 607.2a's linked pile, the cards this very
#: object's own exile ability put there ("As long as there are four or more
#: card types among cards exiled with this creature, it gets +4/+4 and has
#: trample."), where the subject is the pronoun "it" rather than "this
#: creature" again.
_GRAVEYARD_CARD_TYPES_GATED_SELF_STATIC_RE = re.compile(
    r"^as long as there are (?P<count>[a-z]+) or more card types among cards "
    r"(?:in your graveyard|(?P<linked>exiled with this \w+)), "
    r"(?:this (?:creature|permanent|token)|it) gets (?P<power>[+-]\d+)/"
    r"(?P<toughness>[+-]\d+)(?P<rest>.*?)\.?$",
    re.IGNORECASE,
)

#: "descend 4"/"descend 8" (CR 207.2c's own ability-word list) - the same
#: gated-self-static shape as delirium above, printed both ways round in the
#: pool: condition-leading (Akawalli, the Seething Tower's own "As long as
#: there are four or more permanent cards in your graveyard, Akawalli gets
#: +2/+2 and has trample.") and condition-trailing (Basking Capybara's "This
#: creature gets +3/+0 as long as there are four or more permanent cards in
#: your graveyard."). CR 700.11's own "permanent card" - artifact, battle,
#: creature, enchantment, land, planeswalker (CR 110.4a) - is `count_
#: permanent_cards`, not `count_card_types`: the two ability words happen to
#: share delirium's gated-static template, not its count.
#: Read after `self_normalized_effect_text` has already rewritten Akawalli's
#: own literal name to "this permanent" (`_layer_readable_sentences_
#: uncached`'s own call), the same normalisation every self-referential
#: static sentence in this module already relies on - so no literal-name
#: branch is needed here, only "this creature/permanent/token".
#:
#: Akawalli's own Descend 8 ("... gets an additional +2/+2 and can't be
#: blocked by more than one creature.") is the same template stacked on top
#: of its own Descend 4: "an additional" is an optional word ahead of the
#: pump delta (CR 613.4c's sublayer 7c applies every static's own +2/+2
#: independently regardless of the printed adjective - it is there only so
#: the two pumps read as additive English, not as a rules instruction), and
#: the trailing grant is `_split_gated_grants`' plain "not `has ...`, so
#: granted verbatim" branch: CR 509.1b's own evasion-restriction shape, read
#: at the combat layer by `machines/combat.py`'s `blocked_by_at_most_one_
#: refusal`, the same way that module already reads Ghalta's/Loot's own
#: literal-text grants rather than a `Keyword` member, because "can't be
#: blocked by more than one creature" has no keyword name of its own.
_DESCEND_GATED_SELF_STATIC_LEADING_RE = re.compile(
    r"^as long as there are (?P<count>[a-z]+) or more permanent cards in your "
    r"graveyard, this (?:creature|permanent|token) "
    r"(?:gets (?:an additional )?(?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)(?P<rest>.*?)"
    r"|(?P<grant_only>has .+?))\.?$",
    re.IGNORECASE,
)
_DESCEND_GATED_SELF_STATIC_TRAILING_RE = re.compile(
    r"^this (?:creature|permanent|token) "
    r"(?:gets (?:an additional )?(?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)(?P<rest>.*?)"
    r"|(?P<grant_only>has .+?))"
    r" as long as there are (?P<count>[a-z]+) or more permanent cards in your graveyard\.?$",
    re.IGNORECASE,
)

#: Threshold's own trailing form (CR 207.2c: an ability word, no rules meaning
#: of its own - "Threshold — " is stripped before this is ever reached):
#: "This creature gets +1/+0 and has flying as long as there are seven or more
#: cards in your graveyard." (Theorix Metamage) - the condition trails instead
#: of leading, and counts plain cards rather than card types.
_GRAVEYARD_CARD_COUNT_GATED_SELF_STATIC_RE = re.compile(
    r"^this (?:creature|permanent|token) gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)"
    r"(?P<rest>.*?) as long as there (?:is|are) (?P<count>[a-z]+) or more cards? in your "
    r"graveyard\.?$",
    re.IGNORECASE,
)

#: "During your turn, this creature has first strike." (Skilled Battlecarver) -
#: a whole-turn condition (whose turn it is), not something a `Selector` can
#: judge from the board, so it is checked at build time off
#: `LayerContext.active_player` the same way the graveyard-count gates above
#: are checked off `LayerContext.graveyard_of`.
_SELF_DURING_YOUR_TURN_KEYWORD_GRANT_RE = re.compile(
    r"^during your turn, this (?:creature|permanent|token) (?:has|have) "
    r"(?P<keywords>[a-z]+(?: [a-z]+)?(?:(?:,\s*| and )[a-z]+(?: [a-z]+)?)*)\.?$",
    re.IGNORECASE,
)

#: "This creature has vigilance as long as you control a Jace planeswalker."
#: (Mind Meanderer) - a board-only condition (does the controller control a
#: permanent of this type/subtype), so it lives in `SelfIfControls` rather
#: than being checked at build time.
_SELF_CONTROLS_KEYWORD_GRANT_RE = re.compile(
    r"^this (?:creature|permanent|token) (?:has|have) "
    r"(?P<keywords>[a-z]+(?: [a-z]+)?(?:(?:,\s*| and )[a-z]+(?: [a-z]+)?)*) as long as you "
    r"control an? (?:(?P<subtype>(?-i:[A-Z][a-zA-Z']*)) )?(?P<cardtype>[a-z]+)\.?$",
    re.IGNORECASE,
)

#: "This creature gets +1/+0 as long as any player controls a black
#: permanent." (Knight of Grace; Knight of Malice's "a white permanent") - a
#: self pump (CR 613.4c) behind CR 611.3a's live board condition, asked of
#: every player's permanents ("any player"), the controller's ("you") or the
#: opponents' ("an opponent"), matched by computed colour and/or card type.
_SELF_PUMP_WHILE_CONTROLS_RE = re.compile(
    r"^this (?:creature|permanent) gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) "
    r"as long as (?P<who>any player|you|an opponent) controls? an? "
    r"(?:(?P<color>white|blue|black|red|green) )?(?P<noun>[a-z]+)\.?$",
    re.IGNORECASE,
)

#: The two turn-fact conditions this shape recognises, each already tracked by
#: `Game.record_turn_fact`/`turn_fact_holds` (`models/game.py`) for the
#: identical "Activate only if ..." restriction - reused here rather than
#: re-derived, since the fact vocabulary is the engine's own, not a per-card
#: invention. `"you"` reads `LayerContext.has_turn_fact` for the source's own
#: controller; `"opponent"` reads `has_turn_fact_for_opponent`.
_TURN_FACT_CONDITION_PHRASES: dict[str, tuple[str, str]] = {
    "you've scried or surveilled this turn": ("scried_or_surveilled", "you"),
    "you have scried or surveilled this turn": ("scried_or_surveilled", "you"),
    "an opponent was dealt noncombat damage this turn": ("dealt_noncombat_damage", "opponent"),
    "an opponent has been dealt noncombat damage this turn": (
        "dealt_noncombat_damage",
        "opponent",
    ),
    # CR 701.21a, recorded by `Game.sacrifice` (Goblin Blast-Runner).
    "you sacrificed a permanent this turn": ("sacrificed_permanent", "you"),
}

#: "As long as `<condition>`, this `<object>` is an artifact creature." -
#: Phoenix Fleet Airship ("you control eight or more permanents named Phoenix
#: Fleet Airship") and Grond, the Gatebreaker ("it's your turn and you control
#: an Army"), each self-reference already rewritten to "this permanent" by
#: `self_normalized_effect_text` (CR 201.5). The type phrase is added in layer
#: 4 (CR 613.1d), keeping every type already there (CR 205.1b).
_CONDITIONAL_SELF_TYPE_CHANGE_RE = re.compile(
    r"^as long as (?P<condition>[^,]+), this [a-z]+ is an? "
    r"(?P<types>(?:[a-z]+ )*creature)\.?$",
    re.IGNORECASE,
)
_ITS_YOUR_TURN_RE = re.compile(r"it(?:'s| is) your turn", re.IGNORECASE)
_YOU_CONTROL_N_NAMED_RE = re.compile(
    rf"you control (?P<count>{COUNT}) or more permanents named (?P<name>.+)",
    re.IGNORECASE,
)
_YOU_CONTROL_AN_RE = re.compile(r"you control an? (?P<word>[a-z'-]+)", re.IGNORECASE)


#: "This creature gets +2/+0 and has menace as long as you sacrificed a
#: permanent this turn." (Goblin Blast-Runner) - the trailing order of
#: `_TURN_FACT_GATED_SELF_RE`, with a pump (CR 613.4c) and optional keywords,
#: behind one of `_TURN_FACT_CONDITION_PHRASES`.
_TURN_FACT_GATED_SELF_PUMP_RE = re.compile(
    r"^this (?:creature|permanent|token) gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)"
    r"(?P<rest>(?: and has [^.]+?)?) as long as (?P<condition>[^,.]+?)\.?$",
    re.IGNORECASE,
)

#: "As long as you've scried or surveilled this turn, this creature can
#: attack as though it didn't have defender." (Surveillance Phantasm); "As
#: long as an opponent was dealt noncombat damage this turn, this creature has
#: flying and haste." (Whiplash Wordsmith) - one shape, two predicates: the
#: fixed "can attack as though it didn't have defender" text, or an ordinary
#: keyword list.
_TURN_FACT_GATED_SELF_RE = re.compile(
    r"^as long as (?P<condition>.+?), this (?:creature|permanent|token) "
    r"(?:(?P<no_defender>can attack as though it didn'?t have defender)"
    r"|(?:has|have) (?P<keywords>[a-z]+(?: [a-z]+)?(?:(?:,\s*| and )[a-z]+(?: [a-z]+)?)*))\.?$",
    re.IGNORECASE,
)

#: "As long as this creature is monstrous, it has hexproof and
#: indestructible." (Fleecemane Lion) - CR 701.37b's own designation, read
#: directly off `CardState.monstrous` rather than through `LayerContext`:
#: unlike the turn-fact conditions above, this one already lives on the
#: object itself, so the condition callable below just reads `source.
#: monstrous` and needs no context lookup at all. CR 611.3a's live
#: reevaluation applies the same way it does to every static ability here -
#: `effects_for` reruns on every CR 613.5 computation, so the grant is on
#: exactly while the designation holds and switches off the instant CR
#: 701.37b's own "until it leaves the battlefield" clears it, with no stored
#: `Duration` needed.
_SELF_MONSTROUS_GATED_RE = re.compile(
    r"^as long as this (?:creature|permanent) is monstrous, "
    r"it (?:has|have) (?P<keywords>[a-z]+(?: [a-z]+)?(?:(?:,\s*| and )[a-z]+(?: [a-z]+)?)*)\.?$",
    re.IGNORECASE,
)


#: "Ruric Thar has hexproof as long as they haven't dealt combat damage yet."
#: - the card's own name is already rewritten to "this permanent" by
#: `self_normalized_effect_text` before this is reached, and "they" is this
#: set's pronoun for a single permanent. A per-object "this turn" fact
#: (`LayerContext.combat_damage_dealt_this_turn`), not a per-player one, so it
#: is its own shape rather than folding into `_TURN_FACT_GATED_SELF_RE`.
_SELF_HASNT_DEALT_COMBAT_DAMAGE_RE = re.compile(
    r"^this (?:creature|permanent|token) (?:has|have) "
    r"(?P<keywords>[a-z]+(?: [a-z]+)?(?:(?:,\s*| and )[a-z]+(?: [a-z]+)?)*) as long as "
    r"(?:it|they|he|she) haven'?t dealt combat damage(?: this turn)? yet\.?$",
    re.IGNORECASE,
)

#: "Each creature you control has vigilance if it's white, hexproof if it's
#: blue, lifelink if it's black, first strike if it's red, and trample if it's
#: green." (Scion of Draco, confirmed with `resolve_cards`) - one layer 6 grant
#: (CR 613.1f) per clause, each with its own per-object colour condition, which
#: is a `Selector` question and not a `Duration` one. Colour is judged on the
#: computed board, so layer 5 (CR 613.1e) has already run when layer 6 asks.
_PER_COLOR_KEYWORD_GRANT_RE = re.compile(
    r"^each creature you control has (?P<clauses>.+ if it's .+?)\.?$",
    re.IGNORECASE,
)

_ONE_COLOR_KEYWORD_CLAUSE_RE = re.compile(
    r"^(?P<keyword>[a-z]+(?: [a-z]+)?) if it's (?P<color>white|blue|black|red|green)$",
    re.IGNORECASE,
)

#: The five colour words, as a printed condition spells them (CR 105.1).
_COLOR_WORDS: dict[str, Color] = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}

#: "Permanents you control with counters on them have ward {1}." (Innkeeper's
#: Talent's level-2 chapter). CR 702.21a: "Ward is a triggered ability. Ward
#: [cost] means 'Whenever this permanent becomes the target of a spell or
#: ability an opponent controls, counter that spell or ability unless that
#: player pays [cost]'" - so this is an ability-adding effect in layer 6
#: (CR 613.1f) like any other grant, and the cost travels in the granted text.
#:
#: Ward has no redundancy clause of its own - compare CR 702.3c for defender or
#: CR 702.18b for shroud, both of which say multiple instances are redundant -
#: so two of these grant two abilities (CR 113.2c: "An object may have multiple
#: abilities"), which is why this one shape grants through
#: `grant_ability_instance` rather than the deduplicating `grant_ability`.
_PERMANENTS_WITH_COUNTERS_WARD_RE = re.compile(
    r"^permanents you control with counters on them have ward (?P<cost>\{[^}]+\})\.?$",
    re.IGNORECASE,
)


#: Reminder text, anywhere in a line (CR 207.2a: "Reminder text ... appears in
#: italics within parentheses" and "has no game function"). Stripped only for
#: the purpose of matching a parsed sentence back to the line it came from.
_REMINDER_TEXT_RE = re.compile(r"\s*\([^)]*\)")


def _source_line_for(source: CardState, sentence: str) -> str:
    """The permanent's own printed oracle *line* that `sentence` was parsed
    out of, or `sentence` unchanged if no line matches.

    `ContinuousEffect.source_ability` is matched against
    `Characteristics.abilities` - which is the card's lines verbatim - every
    time `_still_exists` asks CR 613.6's question ("an effect that has already
    started applying keeps applying even once the ability generating it is
    gone"). A sentence that reached the parser through
    `layer_readable_sentences` may have had its reminder text (CR 207.2a), its
    ability word (CR 207.2c) or its own printed name (rewritten to "this
    permanent") taken off it on the way, and none of those forms is what layer
    6 removal will be matching on. Territorial Kavu is the card that makes this
    visible: every one of the three happens to its *domain* line at once, and
    without this the effect it generates would look, to `_still_exists`, like
    an effect whose ability had already been removed.
    """
    for raw in (source.oracle_text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line == sentence:
            return line
        source_card = getattr(source, "card", None)
        legendary = source_card is not None and Supertype.LEGENDARY in source_card.supertypes
        normalized = _strip_ability_word(
            self_normalized_effect_text(
                source.name, _REMINDER_TEXT_RE.sub("", line).strip(), legendary=legendary
            )
        )
        if normalized == sentence or normalized.startswith(sentence):
            return line
    return sentence


def _subtype_word(word: str) -> str | None:
    """ "Dragons" -> "Dragon" (CR 205.3m's plural), or `None` if the word names
    one of CR 300.1's card types instead - "Artifacts you control are ..." is
    the board-wide *type* shape's sentence, never a subtype anthem's.
    """
    singular = word[:-1] if word.lower().endswith("s") else word
    if _card_type_word(singular) is not None:
        return None
    return singular.capitalize()


def _subtype_list_words(raw: str) -> list[str] | None:
    """ "Wolves and Werewolves" -> ["Wolf", "Werewolf"] (CR 205.3m), or `None`
    if any item is not a printed subtype's plural.

    Each item goes through `data/subtypes.canonical_subtype`, which reads a
    printed plural back to the one subtype it can only be ("Wolves" is "Wolf",
    "Elves" is "Elf", "Merfolk" is itself). A word it cannot place - a card
    type ("Creatures", "Artifacts": a different sentence entirely) or anything
    else - fails the whole list closed rather than granting a narrower group
    than the card prints.
    """
    words = [part.strip() for part in re.split(r",\s*(?:and\s+|or\s+)?|\s+and\s+|\s+or\s+", raw)]
    subtypes: list[str] = []
    for word in words:
        if not word or _card_type_word(word) is not None:
            return None
        subtype = canonical_subtype(word)
        if subtype is None:
            return None
        subtypes.append(subtype.capitalize())
    return subtypes or None


def _filtered_anthem_builder(
    subtypes: list[str],
    power: int,
    toughness: int,
    keywords: list[str],
    *,
    other: bool,
    line: str,
) -> EffectBuilder:
    """An anthem over a filtered subset of the team - Stormscale Scion's "Other
    Dragons you control get +1/+1", Kaheera's five-subtype list with a keyword
    riding along.

    Sublayer 7c for the pump (CR 613.4c: effects that "modify power and/or
    toughness (but don't set ...)") and layer 6 for each keyword (CR 613.1f),
    one ability applying in more than one layer (CR 613.6). A static ability's
    effect (CR 611.3), so it is timestamped off the source permanent
    (CR 613.7a), its selector stays live rather than fixed at resolution
    (CR 611.3a: "isn't 'locked in'; it applies at any given moment to whatever
    its text indicates"), and `source_ability` is the printed sentence so layer
    6 removal has something to match on.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        selector = creatures_controlled_by_with_subtype(
            source.controller, subtypes, other_than=source.id if other else None
        )
        subject = f"{'other ' if other else ''}{'/'.join(subtypes)}s you control"
        effects: list[ContinuousEffect] = []
        if power != 0 or toughness != 0:
            effects.append(
                ContinuousEffect(
                    description=f"{source.name}: {subject} get {power:+d}/{toughness:+d}",
                    layer=Layer.POWER_TOUGHNESS,
                    sublayer=Sublayer.MODIFY,
                    timestamp=timestamp,
                    source_id=source.id,
                    source_ability=_source_line_for(source, line),
                    selector=selector,
                    modification=modify_power_toughness(power, toughness),
                )
            )
        effects.extend(
            ContinuousEffect(
                description=f"{source.name}: {subject} have {keyword}",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=selector,
                modification=grant_ability(keyword),
            )
            for keyword in keywords
        )
        return effects

    return builder


def count_basic_land_types_among_lands_controlled_by(username: str | None) -> Count:
    """How many of the five basic land types (CR 305.6) are among the lands one
    player controls - *domain*'s number (CR 207.2c: an ability word with no
    rules meaning of its own, so the counting is spelled out on each card).

    Counted off the board as it stands in the sublayer that asks, so a land
    that gained a basic land type in layer 4 (CR 613.1d) counts - which is the
    whole reason Territorial Kavu grows next to a Dryad of the Ilysian Grove.
    """
    return CountBasicLandTypesAmongLandsControlledBy(username=username)


def _basic_land_type_count_cda_builder(line: str) -> EffectBuilder:
    """`_BASIC_LAND_TYPE_COUNT_CDA_RE`'s shape - Territorial Kavu's *domain*
    characteristic-defining ability.

    Sublayer 7a (CR 613.4a: "Effects from characteristic-defining abilities
    that define power and/or toughness are applied"), and `define_power_
    toughness` *sets* both halves rather than adding to them, since a CDA
    defines the value (CR 604.3). The printed box is `*`, which
    `printed_characteristics` reads as no value at all until this runs
    (CR 208.2a), and CR 208.5 covers the gap if layer 6 ever strips the ability.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=f"{source.name}: P/T equal to its controller's domain",
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.CHARACTERISTIC_DEFINING,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                characteristic_defining=True,
                selector=_only(source.id),
                modification=define_power_toughness(
                    count_basic_land_types_among_lands_controlled_by(source.controller)
                ),
            )
        ]

    return builder


def _basic_land_type_count_power_only_cda_builder(line: str) -> EffectBuilder:
    """`_BASIC_LAND_TYPE_COUNT_POWER_ONLY_CDA_RE`'s shape - Fblthp, Knows the
    Way's and Nishoba Brawler's power-only *domain* characteristic-defining
    ability.

    Still sublayer 7a (CR 613.4a), still `characteristic_defining=True`, but
    `define_power` rather than `define_power_toughness`: the printed
    toughness box is an ordinary number (CR 208.1), not a `*`, so nothing here
    should ever touch it (CR 208.2a names power alone).
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=f"{source.name}: power equal to its controller's domain",
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.CHARACTERISTIC_DEFINING,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                characteristic_defining=True,
                selector=_only(source.id),
                modification=define_power(
                    count_basic_land_types_among_lands_controlled_by(source.controller)
                ),
            )
        ]

    return builder


#: "This creature's/permanent's/token's power and toughness are each equal
#: to the number of `<type>` you control." - a real, heavily templated
#: "lands matter" archetype (Molimo, Maro-Sorcerer; Old Man Willow; Titania,
#: Gaea Incarnate; Ulvenwald Hydra; Cultivator Colossus; Ashaya, Soul of the
#: Wild - a card search on the exact sentence turns up over a dozen real
#: printings) as well as Wrenn and Seven's own -3 token, which grants the
#: identical sentence in quotes rather than printing it directly - CR 111.3
#: puts the quoted text verbatim onto `TokenDefinition.rules_text`, read by
#: this module's ordinary static-ability sweep the same as a printed card's
#: oracle text (see `_self_pump_per_controlled_permanent_builder`'s own
#: docstring, built for the Urza's Saga Construct token the same way).
#:
#: `<type>` is any of CR 205.2a's fifteen card types, not only "lands" -
#: `_card_type_word` reads whichever one is printed, the same singularisation
#: `_BASIC_LAND_TYPE_COUNT_CDA_RE`'s own domain sibling and `machines/
#: effects.py::count_expression` already use. A subtype ("Zombies you
#: control") is not read here: no real printing in this shape needs one, and
#: guessing at the vocabulary check `count_expression`'s own subtype branch
#: uses would be new, unverified scope.
_QUALIFIER_COUNT_CDA_RE = re.compile(
    r"^this (?:creature|permanent|token)'s power and toughness are each equal to "
    r"the number of (?P<qualifier>[a-z]+) you control\.?$",
    re.IGNORECASE,
)


def _qualifier_count_cda_builder(
    line: str, qualifier: str, count: ControlledCountFactory
) -> EffectBuilder:
    """`_QUALIFIER_COUNT_CDA_RE`'s shape - CR 604.3a's characteristic-
    defining ability, sublayer 7a (CR 613.4a), the same "set, not add" shape
    `_basic_land_type_count_cda_builder` right above already is. `qualifier`
    is a card type (Crusader of Odric's "creatures") or a subtype (Eluge, the
    Shoreless Sea's "Islands", Dungrove Elder's "Forests"), counted live off
    the board, so a land that became an Island in layer 4 counts in 7a.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=(
                    f"{source.name}: P/T equal to the number of {qualifier} its controller controls"
                ),
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.CHARACTERISTIC_DEFINING,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                characteristic_defining=True,
                selector=_only(source.id),
                modification=define_power_toughness(count(source.controller)),
            )
        ]

    return builder


#: "This permanent's power and toughness are each equal to twice the number
#: of instant and sorcery cards in your graveyard." (Melek, Reforged
#: Researcher) - a CR 604.3a characteristic-defining ability counting card
#: types in the controller's own graveyard (a card with any of the named types
#: counts once), optionally doubled ("twice", CR 107.1's plain arithmetic).
_GRAVEYARD_CARD_COUNT_CDA_RE = re.compile(
    r"^this (?:creature|permanent|token)'s power and toughness are each equal to "
    r"(?P<twice>twice )?the number of "
    r"(?P<types>[a-z]+(?:(?:,\s*| and | or | and/or )[a-z]+)*) cards in your graveyard\.?$",
    re.IGNORECASE,
)


def _graveyard_card_count_cda_builder(
    line: str, card_types: tuple[Type, ...], multiplier: int
) -> EffectBuilder:
    """`_GRAVEYARD_CARD_COUNT_CDA_RE`'s shape. The graveyard is not on the
    board the layer engine threads through, so the count is read off
    `context.graveyard_of` when the effect is built - which `effects_for` does
    on every CR 613.5 computation, the same live-recompute a `FixedCount`
    already gives Tarmogoyf."""

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        counted = multiplier * sum(
            1
            for card in context.graveyard_of(source.controller)
            if any(card_type in card.types for card_type in card_types)
        )
        return [
            ContinuousEffect(
                description=f"{source.name}: {counted}/{counted} from cards in your graveyard",
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.CHARACTERISTIC_DEFINING,
                characteristic_defining=True,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=_only(source.id),
                modification=define_power_toughness(FixedCount(value=counted)),
            )
        ]

    return builder


def _attached_creature_static_builder(
    power: int,
    toughness: int,
    keywords: list[str],
    *,
    subject: str,
    granted: str | None = None,
    base_power: int | None = None,
    base_toughness: int | None = None,
    line: str,
) -> EffectBuilder:
    """`_ATTACHED_CREATURE_STATIC_RE`'s shape - Cori-Steel Cutter's "Equipped
    creature gets +1/+1 and has trample and haste.", Rancor's "Enchanted
    creature gets +2/+0 and has trample.", Umbral Mantle's quoted grant.

    CR 301.5a: "The creature an Equipment is attached to is called the
    'equipped creature'"; CR 301.5f extends the phrase to a permanent that is
    not itself an Equipment. CR 303.4b says the same thing for an Aura: "The
    object or player an Aura is attached to is called enchanted." Attachment is
    not a characteristic and never reaches the board, so the subject is read
    off the source's own `attached_to` link either way - and an unattached
    Equipment or Aura produces no effect at all, which is exactly what those
    rules leave it with: no attached creature to talk about. (An Aura is only
    ever unattached briefly; CR 704.5m is the state-based action that bins it.)

    Sublayer 7c (CR 613.4c) for the pump, layer 6 (CR 613.1f) for each keyword
    and for a quoted granted ability, one ability in two layers (CR 613.6).

    `granted` is the quoted ability of Umbral Mantle's `Equipped creature has
    "{3}, {Q}: This creature gets +2/+2 until end of turn."` - CR 113.10a: "An
    effect that adds an activated ability may include activation instructions
    for that ability. These instructions become part of the ability that's
    added to the object." The layer-6 grant here puts the line on the
    creature's *characteristics*; making the ability actually activatable needs
    it on `CardState.granted_ability_texts` as well, which is what
    `sync_granted_ability_texts` does on each battlefield sweep.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        attached = source.attached_to
        if attached is None:
            return []
        effects: list[ContinuousEffect] = []
        if base_power is not None and base_toughness is not None:
            effects.append(
                ContinuousEffect(
                    description=(
                        f"{source.name}: {subject} creature has base power and "
                        f"toughness {base_power}/{base_toughness}"
                    ),
                    layer=Layer.POWER_TOUGHNESS,
                    sublayer=Sublayer.SET,
                    timestamp=timestamp,
                    source_id=source.id,
                    source_ability=_source_line_for(source, line),
                    selector=_only(attached),
                    modification=set_power_toughness(base_power, base_toughness),
                )
            )
        if power or toughness:
            effects.append(
                ContinuousEffect(
                    description=(
                        f"{source.name}: {subject} creature gets {power:+d}/{toughness:+d}"
                    ),
                    layer=Layer.POWER_TOUGHNESS,
                    sublayer=Sublayer.MODIFY,
                    timestamp=timestamp,
                    source_id=source.id,
                    source_ability=_source_line_for(source, line),
                    selector=_only(attached),
                    modification=modify_power_toughness(power, toughness),
                )
            )
        effects.extend(
            ContinuousEffect(
                description=f"{source.name}: {subject} creature has {keyword}",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=_only(attached),
                modification=grant_ability(keyword),
            )
            for keyword in keywords
        )
        if granted is not None:
            effects.append(
                ContinuousEffect(
                    description=f'{source.name}: {subject} creature has "{granted}"',
                    layer=Layer.ABILITY,
                    timestamp=timestamp,
                    source_id=source.id,
                    source_ability=_source_line_for(source, line),
                    selector=_only(attached),
                    modification=grant_ability(granted),
                )
            )
        return effects

    return builder


#: Canonical granted-ability text for "doesn't untap during its controller's
#: untap step" - Traxos, Scourge Eternal's self grant ("during your untap
#: step", the printed first-person form) and Infinite Coursework's attached
#: one ("during its controller's untap step") both normalise to this one
#: string, so `Game._untap_step_impl` checks a single literal rather than
#: pattern-matching either printed pronoun.
DOESNT_UNTAP_TEXT = "Doesn't untap during its controller's untap step."

#: Canonical granted-ability text for "<Type>s entering [the battlefield]
#: don't cause abilities to trigger" - Torpor Orb's "Creatures entering
#: don't cause abilities to trigger." and Karn, Argent Defender's "Artifacts
#: and creatures entering the battlefield don't cause abilities to trigger."
#: both normalise to one of these two fixed strings per type named, so
#: `Game.emit` checks a literal rather than pattern-matching either printed
#: wording. Two constants, not one parametrised on a type list, because the
#: check site asks "is *this* card type suppressed" one type at a time.
CREATURES_DONT_CAUSE_TRIGGERS_TEXT = "Creatures entering don't cause abilities to trigger."
ARTIFACTS_DONT_CAUSE_TRIGGERS_TEXT = "Artifacts entering don't cause abilities to trigger."

#: The card types this shape can name, and the canonical text each grants.
_DONT_CAUSE_TRIGGERS_TEXT_BY_TYPE: dict[Type, str] = {
    Type.CREATURE: CREATURES_DONT_CAUSE_TRIGGERS_TEXT,
    Type.ARTIFACT: ARTIFACTS_DONT_CAUSE_TRIGGERS_TEXT,
}


def _self_suppresses_etb_triggers_builder(card_types: list[Type], *, line: str) -> EffectBuilder:
    """Torpor Orb's "Creatures entering don't cause abilities to trigger.";
    Karn, Argent Defender's "Artifacts and creatures entering the battlefield
    don't cause abilities to trigger." - one grant per named type, all
    landing on the source itself. `Game.emit` is the reader: CR 603.2's
    trigger check for an ENTERS_THE_BATTLEFIELD event asks whether any
    permanent on the battlefield carries the matching text before adding
    anything caused by that entrance to `pending_triggers`.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=f"{source.name}: {card_type.value}s entering don't cause triggers",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=_only(source.id),
                modification=grant_ability(_DONT_CAUSE_TRIGGERS_TEXT_BY_TYPE[card_type]),
            )
            for card_type in card_types
        ]

    return builder


#: Canonical granted-ability text for "the legend rule doesn't apply to
#: permanents you control" (Mirror Box, Sakashima of a Thousand Faces' own
#: permanent static; Hall of Echoes' "... this turn" one-shot temporal
#: version). `Game._legend_rule_losers` is the reader: CR 704.5j's legend
#: rule is a state-based action over the whole battlefield, not a
#: characteristic a `Selector`/`Modification` changes, so a permanent that
#: carries this text exempts *its own controller* rather than itself.
LEGEND_RULE_EXEMPT_TEXT = "The legend rule doesn't apply to permanents you control."

#: "The 'legend rule' doesn't apply to permanents you control." (Mirror Box;
#: Sakashima of a Thousand Faces) - CR 611.3's ordinary static ability, no
#: duration: exempt for as long as the permanent has the ability (CR 604.2).
_LEGEND_RULE_EXEMPT_RE = re.compile(
    r"^the [\"“]legend rule[\"”] doesn'?t apply to permanents you control\.?$",
    re.IGNORECASE,
)

#: "The 'legend rule' doesn't apply to permanents you control this turn."
#: (Hall of Echoes' own `{5}` ability, riding alongside its "becomes a copy"
#: sentence) - CR 611.2's one-shot temporal version instead: `Duration.
#: UNTIL_END_OF_TURN` on the same grant, landing on the resolving ability's
#: own source the same way any other self-only "until end of turn" grant
#: here does.
_LEGEND_RULE_EXEMPT_THIS_TURN_RE = re.compile(
    r"^the [\"“]legend rule[\"”] doesn'?t apply to permanents you control this "
    r"turn\.?$",
    re.IGNORECASE,
)


def _self_legend_rule_exempt_builder(*, until_end_of_turn: bool, line: str) -> EffectBuilder:
    """Both `_LEGEND_RULE_EXEMPT_RE`'s and `_LEGEND_RULE_EXEMPT_THIS_TURN_RE`'s
    shapes - see either regex's own docstring for the card each reads.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        kwargs: dict[str, object] = {}
        if until_end_of_turn:
            kwargs["duration"] = Duration.UNTIL_END_OF_TURN
        return [
            ContinuousEffect(
                description=f"{source.name}: the legend rule doesn't apply to its "
                "controller's permanents",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=_only(source.id),
                modification=grant_ability(LEGEND_RULE_EXEMPT_TEXT),
                **kwargs,
            )
        ]

    return builder


#: Canonical granted-ability text for "instant and sorcery spells you
#: control have split second" (Samut, Tyrant of Naktamun) - CR 702.61a's
#: split second is a property of a *spell*, not a battlefield permanent, so
#: nothing in this module's board ever carries it directly; this is the
#: group-grant half only (see `_self_grants_split_second_builder`'s own
#: docstring for the reader this hands off to).
SPELLS_HAVE_SPLIT_SECOND_TEXT = "Instant and sorcery spells you control have split second."

#: "Instant and sorcery spells you control have split second." (Samut,
#: Tyrant of Naktamun).
_SPELLS_HAVE_SPLIT_SECOND_RE = re.compile(
    r"^instant and sorcery spells you control have split second\.?$", re.IGNORECASE
)


def _self_grants_split_second_builder(*, line: str) -> EffectBuilder:
    """Samut, Tyrant of Naktamun's static grant - the *reader* is
    `Game.controls_split_second_grant`, since CR 702.61a's split second only
    ever matters while a spell is on the stack, which this module's board
    never sees (`Selector`/`ContinuousEffect` are battlefield-only). The
    grant itself still lands on Samut's own characteristics, the same
    self-only pattern `_self_suppresses_etb_triggers_builder` and `_self_
    doesnt_untap_builder` already use for a board-wide question with one
    watcher: whoever checks a spell for split second asks the battlefield
    for this text rather than the spell for a keyword it was never printed
    with. The base split second keyword itself - what it *does* while the
    spell is on the stack - is FRA stream S10's own build.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=f"{source.name}: instant and sorcery spells you control have "
                "split second",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=_only(source.id),
                modification=grant_ability(SPELLS_HAVE_SPLIT_SECOND_TEXT),
            )
        ]

    return builder


def _self_doesnt_untap_builder(*, line: str) -> EffectBuilder:
    """Traxos, Scourge Eternal: "Traxos doesn't untap during your untap
    step." (self-normalised to "This permanent doesn't untap during your
    untap step." before this is reached) - Basalt Monolith's identical shape,
    read the same way any other self static grant here is.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=f"{source.name}: doesn't untap during its controller's untap step",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=_only(source.id),
                modification=grant_ability(DOESNT_UNTAP_TEXT),
            )
        ]

    return builder


def _attached_doesnt_untap_builder(
    *, subject: str, loses_abilities: bool, line: str
) -> EffectBuilder:
    """ "Enchanted creature [loses all abilities and ]doesn't untap during
    its controller's untap step." (Infinite Coursework; Enchanted River's
    Grasp's identical combined shape; Apathy's/Bind the Monster's plain one
    with no ability loss) - CR 613.1f for the removal (when printed) and for
    the grant, both landing on whatever `attached_to` points at.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        attached = source.attached_to
        if attached is None:
            return []
        effects: list[ContinuousEffect] = []
        if loses_abilities:
            effects.append(
                ContinuousEffect(
                    description=f"{source.name}: {subject} creature loses all abilities",
                    layer=Layer.ABILITY,
                    timestamp=timestamp,
                    source_id=source.id,
                    source_ability=_source_line_for(source, line),
                    selector=_only(attached),
                    modification=lose_all_abilities,
                )
            )
        effects.append(
            ContinuousEffect(
                description=(
                    f"{source.name}: {subject} creature doesn't untap during its "
                    "controller's untap step"
                ),
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=_only(attached),
                modification=grant_ability(DOESNT_UNTAP_TEXT),
            )
        )
        return effects

    return builder


def quoted_ability_grants(
    source: CardState, permanents: Sequence[CardState]
) -> tuple[set[str], dict[UUID, set[str]]]:
    """What quoted abilities this permanent's static text could grant, and who
    it is granting them to right now.

    Two shapes in the pool put a whole activated ability in quotes:
    `Equipped creature has "..."` (Umbral Mantle), which reaches whatever
    `attached_to` points at (CR 301.5a, CR 303.4b), and `Other creatures are
    ... and have "..."` (Ygra, Eater of All), which reaches every other
    creature on the battlefield.

    Both halves are returned because `sync_granted_ability_texts` needs the
    "could" as well as the "is": an Equipment that has just been unequipped
    grants nothing and must still be able to take its own line back off the
    creature it used to be on.
    """
    grantable: set[str] = set()
    wanted: dict[UUID, set[str]] = {}
    text_to_read = source.class_ability_text
    # Both shapes put the granted ability in double quotes, so a permanent
    # whose text has none cannot be one of them. The board is recomputed
    # continually (CR 613.5), which makes this the difference between
    # re-parsing every permanent's sentences on every sweep and re-parsing the
    # handful that could possibly matter.
    if not text_to_read or '"' not in text_to_read:
        return grantable, wanted
    for sentence in _effect_sentences(
        text_to_read,
        static_only=True,
        card_name=source.name,
        legendary=Supertype.LEGENDARY in source.card.supertypes,
    ):
        normalized = _strip_ability_word(_normalize_duration_first(sentence))
        if match := _ATTACHED_CREATURE_STATIC_RE.fullmatch(normalized):
            text = (match.group("granted") or "").strip()
            if not text:
                continue
            grantable.add(text)
            if source.attached_to is not None:
                wanted.setdefault(source.attached_to, set()).add(text)
            continue
        if match := _OTHER_CREATURES_ARE_TYPE_RE.fullmatch(normalized):
            text = (match.group("ability") or "").strip()
            if not text:
                continue
            grantable.add(text)
            other = match.group("other") is not None
            for permanent in permanents:
                if other and permanent.id == source.id:
                    continue
                if printed_characteristics(permanent).is_creature:
                    wanted.setdefault(permanent.id, set()).add(text)
            continue
        if match := _GROUP_QUOTED_ABILITY_GRANT_RE.fullmatch(normalized):
            text = (match.group("ability") or "").strip()
            if not text:
                continue
            grantable.add(text)
            for permanent in permanents:
                chars = printed_characteristics(permanent)
                if Type.PLANESWALKER in chars.types and chars.controller == source.controller:
                    wanted.setdefault(permanent.id, set()).add(text)
    return grantable, wanted


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


def sync_granted_ability_texts(
    permanents: Sequence[CardState], search_pool: Sequence[CardState] | None = None
) -> None:
    """Keep `CardState.granted_ability_texts` in step with the quoted abilities
    the battlefield's static abilities are granting right now.

    The layer-6 effect already puts the quoted line into the creature's
    computed `Characteristics.abilities`, which is where CR 613.1f wants it.
    It is not where `Game.activated_abilities` looks: that reads the printed
    card plus `CardState.granted_ability_texts`, and `granted_activated_
    abilities_of` parses the stored line back into a real `ActivatedAbility`
    exactly as a printed one. So a permanent's stored list is reconciled here,
    once per battlefield sweep, against what is actually being granted.

    Reconciled rather than appended, which is what makes an unequip take the
    ability away again (CR 604.2: a static ability's effects are active only
    "as long as the permanent with the ability remains on the battlefield and
    has the ability"). Only texts this mechanism is known to grant are ever
    removed, so a line put there by something else - Urza's Saga's chapter II
    grant, which is a resolved one-shot and not a static ability at all - is
    left alone. That is also why the vocabulary of "texts this mechanism is
    known to grant" is never read off `CardState.granted_ability_texts`
    itself: that list mixes both kinds of grant together, and folding it in
    once made a Construct-making Saga lose its own one-shot line the moment
    this function next ran.

    So the vocabulary is `source_grantable` alone (below), read fresh off
    every source's own printed text - which answers "what could this source
    grant" without needing to remember anything, for as long as the source is
    still one of `permanents`. It is not, once a source has actually left the
    battlefield (CR 604.2's own trigger for taking a grant back off): nothing
    in `permanents` prints that quoted line any more, so a sweep scoped to it
    alone has no way to tell "nobody is granting this" from "nothing here has
    ever granted anything", and the still-departed source's own grant would
    never come off. `search_pool` is where that source is found instead -
    every zone a permanent can actually leave the battlefield to, not just
    the battlefield itself (`_every_card_state_in`'s own docstring has the
    one deliberate exclusion, a library, and the evidence behind it) -
    because a card's own text does not change when it changes zones: a
    destroyed Ygra still prints her quoted ability sitting in the graveyard,
    cold-decoded or not, which is what lets this need no process- or
    game-lifetime memory of its own. Defaults to `permanents`, which is what
    a bare battlefield sweep with no
    wider game behind it (`static_effects`, used only by tests) can do.
    """
    wanted: dict[UUID, set[str]] = {}
    grantable: set[str] = set()
    on_board = {permanent.id for permanent in permanents}
    seen: set[UUID] = set()
    for source in (*permanents, *(search_pool or ())):
        if source.id in seen:
            continue
        seen.add(source.id)
        source_grantable, source_wanted = quoted_ability_grants(source, permanents)
        grantable.update(source_grantable)
        if source.id in on_board:
            for subject, texts in source_wanted.items():
                wanted.setdefault(subject, set()).update(texts)
    if not grantable:
        return
    for permanent in permanents:
        mine = wanted.get(permanent.id, set())
        kept = tuple(
            text
            for text in permanent.granted_ability_texts
            if text not in grantable or text in mine
        )
        updated = kept + tuple(text for text in sorted(mine) if text not in kept)
        if updated != permanent.granted_ability_texts:
            permanent.granted_ability_texts = updated


def _attached_creature_loses_and_becomes_builder(
    subtype: str,
    types: list[Type],
    power: int,
    toughness: int,
    *,
    subject: str,
    line: str,
) -> EffectBuilder:
    """`_ATTACHED_CREATURE_LOSES_AND_BECOMES_RE`'s shape - Unable to Scream.

    Three effects from one ability, in three layers (CR 613.6). They are
    deliberately not one:

    - Layer 6 (CR 613.1f) removes the abilities. It is timestamped with the
      Aura, so an ability granted by an *older* effect goes too and one granted
      by a newer effect survives, which is the whole of CR 613.7's ordering.
    - Layer 4 (CR 613.1d) adds the card types and the creature type. "In
      addition to its other types" is CR 205.1b, so nothing printed is lost -
      the enchanted creature is still whatever it was, plus an artifact.
    - Sublayer 7b (CR 613.4b) sets the base power and toughness, so a +1/+1
      counter or an anthem in 7c still lands on top of the 0/2.

    The subject is `attached_to` for the same reason
    `_attached_creature_static_builder`'s is (CR 303.4b), and an Aura attached
    to nothing produces nothing.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        attached = source.attached_to
        if attached is None:
            return []
        selector = _only(attached)
        ability = _source_line_for(source, line)
        named = " ".join(card_type.value for card_type in types)
        effects = [
            ContinuousEffect(
                description=f"{source.name}: {subject} creature loses all abilities",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=ability,
                selector=selector,
                modification=lose_all_abilities,
            ),
            ContinuousEffect(
                description=f"{source.name}: {subject} creature is "
                f"{with_indefinite_article(subtype)} {named}",
                layer=Layer.TYPE,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=ability,
                selector=selector,
                modification=_add_types_and_subtype(types, subtype),
            ),
            ContinuousEffect(
                description=(f"{source.name}: {subject} creature has base P/T {power}/{toughness}"),
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.SET,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=ability,
                selector=selector,
                modification=set_power_toughness(power, toughness),
            ),
        ]
        return effects

    return builder


def _attached_permanent_becomes_creature_builder(
    subtype: str | None, power: int, toughness: int, *, subject: str, line: str
) -> EffectBuilder:
    """ "Enchanted [permanent/artifact] is a[n ][<Subtype> ]creature with base
    power and toughness N/N in addition to its other types." (Puppet
    Crafting's Construct; Ensoul Artifact's bare "a creature", no subtype at
    all; Zoetic Glyph's Golem) - Unable to Scream's shape
    (`_attached_creature_loses_and_becomes_builder`) minus the ability
    removal, since none of these prints "loses all abilities": the enchanted
    permanent keeps whatever it could already do and gains a body on top.

    Layer 4 (CR 613.1d) for the creature type and the optional subtype, "in
    addition to" (CR 205.1b) so nothing printed is lost; sublayer 7b
    (CR 613.4b) sets the base power and toughness.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        attached = source.attached_to
        if attached is None:
            return []
        selector = _only(attached)
        ability = _source_line_for(source, line)
        named = f"{with_indefinite_article(subtype)} " if subtype else "a "
        effects = [
            ContinuousEffect(
                description=f"{source.name}: {subject} is {named}creature",
                layer=Layer.TYPE,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=ability,
                selector=selector,
                modification=(
                    _add_types_and_subtype([Type.CREATURE], subtype)
                    if subtype
                    else add_type(Type.CREATURE)
                ),
            ),
            ContinuousEffect(
                description=(f"{source.name}: {subject} has base P/T {power}/{toughness}"),
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.SET,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=ability,
                selector=selector,
                modification=set_power_toughness(power, toughness),
            ),
        ]
        return effects

    return builder


def _add_types_and_subtype(types: Sequence[Type], subtype: str) -> Modification:
    """Layer 4 (CR 613.1d): gain each card type and the creature type named,
    keeping everything already there (CR 205.1b).
    """
    return AddTypesAndSubtype(types=tuple(types), subtype=subtype)


def _other_creatures_are_type_builder(
    subtype: str,
    granted: Type,
    ability: str | None,
    *,
    other: bool,
    line: str,
) -> EffectBuilder:
    """`_OTHER_CREATURES_ARE_TYPE_RE`'s shape - Ygra, Eater of All's "Other
    creatures are Food artifacts in addition to their other types and have
    "{2}, {T}, Sacrifice this permanent: You gain 3 life.""

    Every other creature on the battlefield, not only the controller's: the
    printed sentence names no controller, and `every_creature` is what "other
    creatures" means with the source excluded. Layer 4 for the card type and
    the subtype (CR 613.1d, CR 205.1b), layer 6 for the quoted ability
    (CR 613.1f, CR 113.10a). A static ability's effect (CR 611.3), so it is
    timestamped off the source (CR 613.7a) and its selector stays live
    (CR 611.3a).

    The quoted ability is put into the computed characteristics here; it is
    put where `Game.activated_abilities` can find it by
    `sync_granted_ability_texts`.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        selector = OtherCreatures(source_id=source.id) if other else every_creature

        subject = "other creatures" if other else "creatures"
        printed = _source_line_for(source, line)
        effects = [
            ContinuousEffect(
                description=f"{source.name}: {subject} are {subtype} {granted.value}s",
                layer=Layer.TYPE,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=printed,
                selector=selector,
                modification=_add_types_and_subtype([granted], subtype),
            )
        ]
        if ability is not None:
            effects.append(
                ContinuousEffect(
                    description=f'{source.name}: {subject} have "{ability}"',
                    layer=Layer.ABILITY,
                    timestamp=timestamp,
                    source_id=source.id,
                    source_ability=printed,
                    selector=selector,
                    modification=grant_ability(ability),
                )
            )
        return effects

    return builder


def _all_colors_builder(*, nonland: bool, line: str) -> EffectBuilder:
    """`_ALL_COLORS_RE`'s shape - Leyline of the Guildpact's "Each nonland
    permanent you control is all colors."

    Layer 5 (CR 613.1e), setting the object's colours to all five (CR 105.1).
    A static ability's effect (CR 611.3), so it is timestamped off the source
    (CR 613.7a) and re-asked on every computation (CR 613.5) - a permanent that
    stops being a land in layer 4 is caught by this on the same pass, because a
    `Selector` reads the board as layer 5 finds it.
    """
    colors = (Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN)

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        selector = all_permanents_controlled_by(source.controller, nonland=nonland)
        subject = "nonland permanents you control" if nonland else "permanents you control"
        return [
            ContinuousEffect(
                description=f"{source.name}: {subject} are all colors",
                layer=Layer.COLOR,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=selector,
                modification=set_colors(*colors),
            )
        ]

    return builder


def _graveyard_card_types_gated_self_static_builder(
    threshold: int, power: int, toughness: int, granted: list[str], *, line: str
) -> EffectBuilder:
    """`_GRAVEYARD_CARD_TYPES_GATED_SELF_STATIC_RE`'s shape - Dragon's Rage
    Channeler's *delirium* ability. A thin alias of `_graveyard_count_gated_
    self_static_builder` over `count_card_types`, kept under its old name
    since every existing call site already spells it out."""
    return _graveyard_count_gated_self_static_builder(
        threshold, power, toughness, granted, line=line, count_fn=count_card_types
    )


def _linked_exile_card_types_gated_self_static_builder(
    threshold: int, power: int, toughness: int, granted: list[str], *, line: str
) -> EffectBuilder:
    """`_GRAVEYARD_CARD_TYPES_GATED_SELF_STATIC_RE`'s linked-exile pile -
    Keen-Eyed Curator. The same gated pump and grant as delirium, counted over
    the cards exiled with this object (CR 607.2a, `LayerContext.cards_
    exiled_with`) rather than a graveyard. CR 205.2a's card types, so an
    artifact creature counts for two; a face-down card has none (CR 406.3a)."""
    return _graveyard_count_gated_self_static_builder(
        threshold,
        power,
        toughness,
        granted,
        line=line,
        count_fn=count_card_types,
        pile=lambda source, context: context.cards_exiled_with(source),
    )


def _graveyard_count_gated_self_static_builder(
    threshold: int,
    power: int,
    toughness: int,
    granted: list[str],
    *,
    line: str,
    count_fn: Callable[[Iterable[CardState]], int],
    pile: Callable[[CardState, LayerContext], Iterable[CardState]] | None = None,
) -> EffectBuilder:
    """A static pump/grant whose condition is some count over the controller's
    own graveyard - Dragon's Rage Channeler's *delirium* (`count_card_types`)
    and the "descend 4"/"descend 8" ability words (`count_permanent_cards`,
    CR 700.11, CR 207.2c) share this same shape and differ only in what they
    count.

    The condition is counted over the controller's own graveyard through
    `LayerContext.graveyard_of`, and it is checked here, at build time, rather
    than stored: CR 604.2 has a static ability's effect active exactly while
    the ability is there and its condition holds, and `effects_for` is
    re-run every time the board is computed (CR 613.5), so a graveyard that
    stops meeting the threshold simply stops producing the effect on the next
    computation.

    Sublayer 7c for the pump (CR 613.4c) and layer 6 for everything granted
    (CR 613.1f). "Attacks each combat if able" is granted as an ability line
    like any other - `Characteristics.abilities` is ability *text*, and nothing
    in this module needs to know which of the granted lines is a keyword.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        cards = context.graveyard_of(source.controller) if pile is None else pile(source, context)
        if count_fn(cards) < threshold:
            return []
        effects: list[ContinuousEffect] = []
        if power or toughness:
            effects.append(
                ContinuousEffect(
                    description=f"{source.name}: {power:+d}/{toughness:+d} while delirious",
                    layer=Layer.POWER_TOUGHNESS,
                    sublayer=Sublayer.MODIFY,
                    timestamp=timestamp,
                    source_id=source.id,
                    source_ability=_source_line_for(source, line),
                    selector=_only(source.id),
                    modification=modify_power_toughness(power, toughness),
                )
            )
        effects.extend(
            ContinuousEffect(
                description=f"{source.name}: has {ability} while delirious",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=_only(source.id),
                modification=grant_ability(ability),
            )
            for ability in granted
        )
        return effects

    return builder


def _graveyard_card_count_gated_self_static_builder(
    threshold: int, power: int, toughness: int, granted: list[str], *, line: str
) -> EffectBuilder:
    """ "This creature gets +1/+0 and has flying as long as there are seven or
    more cards in your graveyard." (Theorix Metamage; Void Extrapolator's
    +1/+1 with no keyword) - Threshold's own ability word (CR 207.2c, stripped
    before this is reached) has no rules meaning of its own; the whole of the
    ability is this trailing condition, counted the same way `_graveyard_
    card_types_gated_self_static_builder`'s delirium counts card *types*,
    except this counts plain cards (CR 110.4's "a card" - no type filter).

    The count is read from `LayerContext.graveyard_of` at build time and the
    condition is not "locked in" (CR 604.2, CR 611.3a): `effects_for` reruns
    on every CR 613.5 computation, so crossing back under the threshold
    (a `bounce`, a `Threshold`-granted line being ignored) removes the effect
    on the very next computation rather than leaving it stuck on.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        if len(context.graveyard_of(source.controller)) < threshold:
            return []
        effects: list[ContinuousEffect] = []
        if power or toughness:
            effects.append(
                ContinuousEffect(
                    description=f"{source.name}: {power:+d}/{toughness:+d} at threshold",
                    layer=Layer.POWER_TOUGHNESS,
                    sublayer=Sublayer.MODIFY,
                    timestamp=timestamp,
                    source_id=source.id,
                    source_ability=_source_line_for(source, line),
                    selector=_only(source.id),
                    modification=modify_power_toughness(power, toughness),
                )
            )
        effects.extend(
            ContinuousEffect(
                description=f"{source.name}: has {ability} at threshold",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=_only(source.id),
                modification=grant_ability(ability),
            )
            for ability in granted
        )
        return effects

    return builder


def _conditional_self_type_change_builder(
    types: tuple[Type, ...],
    your_turn_only: bool,
    requirements: tuple[tuple[str, object, int], ...],
    *,
    line: str,
) -> EffectBuilder:
    """`_CONDITIONAL_SELF_TYPE_CHANGE_RE`'s shape. "It's your turn" is read
    off `LayerContext.active_player` at build time; every "you control"
    count lives in `SelfIfControlsCounted`, re-asked against the board being
    computed. A name of "this permanent" is the card's own (CR 201.5), taken
    from the source as the effect is built."""

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        if your_turn_only and context.active_player != source.controller:
            return []
        built: list[ControlledCountRequirement] = []
        for kind, value, threshold in requirements:
            if kind == "name":
                name = source.name if value == "this permanent" else str(value)
                built.append(ControlledCountRequirement(name=name, threshold=threshold))
            elif kind == "type":
                assert isinstance(value, Type)
                built.append(ControlledCountRequirement(card_type=value, threshold=threshold))
            else:
                built.append(ControlledCountRequirement(subtype=str(value), threshold=threshold))
        selector = SelfIfControlsCounted(
            card_id=source.id, username=source.controller, requirements=tuple(built)
        )
        return [
            ContinuousEffect(
                description=f"{source.name}: is {card_type.value} as long as its condition holds",
                layer=Layer.TYPE,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=selector,
                modification=AddType(card_type=card_type),
            )
            for card_type in types
        ]

    return builder


def _conditional_self_type_change(sentence: str) -> EffectBuilder | None:
    """`_CONDITIONAL_SELF_TYPE_CHANGE_RE` read whole, or `None`: every part
    of the condition (joined by "and") and every type word must read."""
    match = _CONDITIONAL_SELF_TYPE_CHANGE_RE.fullmatch(sentence.strip())
    if match is None:
        return None
    types: list[Type] = []
    for word in match.group("types").split():
        card_type = _card_type_word(word)
        if card_type is None:
            return None
        types.append(card_type)
    your_turn_only = False
    requirements: list[tuple[str, object, int]] = []
    for part in re.split(r"\s+and\s+", match.group("condition").strip()):
        if _ITS_YOUR_TURN_RE.fullmatch(part):
            your_turn_only = True
        elif named := _YOU_CONTROL_N_NAMED_RE.fullmatch(part):
            threshold = parse_count(named.group("count"), article=False)
            if threshold is None:
                return None
            requirements.append(("name", named.group("name").strip(), threshold))
        elif control_a := _YOU_CONTROL_AN_RE.fullmatch(part):
            word = control_a.group("word")
            card_type = _card_type_word(word)
            if card_type is not None:
                requirements.append(("type", card_type, 1))
            elif word.lower() in {each.lower() for each in subtype_vocabulary()}:
                requirements.append(("subtype", word, 1))
            else:
                return None
        else:
            return None
    return _conditional_self_type_change_builder(
        tuple(types), your_turn_only, tuple(requirements), line=sentence
    )


def _turn_fact_gated_self_pump_builder(
    fact: tuple[str, str], power: int, toughness: int, granted: list[str], *, line: str
) -> EffectBuilder:
    """`_TURN_FACT_GATED_SELF_PUMP_RE`'s shape - Goblin Blast-Runner's "+2/+0
    and has menace as long as you sacrificed a permanent this turn".

    The fact is read off `LayerContext.turn_facts` at build time, the choice
    `_graveyard_card_count_gated_self_static_builder` makes for its own
    trailing condition: `effects_for` reruns on every CR 613.5 computation,
    so the pump is on exactly while the fact holds (CR 604.2, CR 611.3a) and
    gone once a new turn clears it.
    """
    fact_name, subject = fact
    pump = _graveyard_card_count_gated_self_static_builder(0, power, toughness, granted, line=line)

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        holds = (
            context.has_turn_fact(fact_name, source.controller)
            if subject == "you"
            else context.has_turn_fact_for_opponent(fact_name, source.controller)
        )
        if not holds:
            return []
        return [
            effect.model_copy(
                update={
                    "description": effect.description.replace("at threshold", "(turn condition)")
                }
            )
            for effect in pump(source, timestamp, targets, context)
        ]

    return builder


def _self_gated_by_controlling_keyword_grant_builder(
    keywords: list[str], *, card_type: Type | None, subtype: str | None, line: str
) -> EffectBuilder:
    """ "This creature has vigilance as long as you control a Jace
    planeswalker." (Mind Meanderer) - a board-only condition, so it lives in
    `SelfIfControls` rather than being checked at build time: CR 611.3a's
    "isn't 'locked in'" live re-ask happens for free every time the layer
    engine asks the `Selector` a question, since the board it is handed is the
    live one.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        selector = self_if_controls(
            source.id, source.controller, card_type=card_type, subtype=subtype
        )
        return [
            ContinuousEffect(
                description=f"{source.name}: has {keyword}",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=selector,
                modification=grant_ability(keyword),
            )
            for keyword in keywords
        ]

    return builder


def _self_pump_while_controls_builder(
    power: int,
    toughness: int,
    *,
    card_type: Type | None,
    color: Color | None,
    controlled_by: Literal["you", "any", "opponent"],
    line: str,
) -> EffectBuilder:
    """`_SELF_PUMP_WHILE_CONTROLS_RE`'s pump: sublayer 7c (CR 613.4c), gated
    by `SelfIfControls` so the board condition is re-asked on every CR 613.5
    computation (CR 611.3a) - the pump ends the moment the last matching
    permanent leaves."""

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=f"{source.name}: {power:+d}/{toughness:+d} while a permanent matches",
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=self_if_controls(
                    source.id,
                    source.controller,
                    card_type=card_type,
                    color=color,
                    controlled_by=controlled_by,
                ),
                modification=modify_power_toughness(power, toughness),
            )
        ]

    return builder


def _group_assigns_damage_as_toughness_builder(*, line: str) -> EffectBuilder:
    """Ghalta the Immovable's "Each creature you control with toughness
    greater than its power assigns combat damage equal to its toughness
    rather than its power." - the group twin of Loot, the Anomaly's self
    grant, over `creatures_controlled_by_toughness_exceeds_power` instead of
    `SelfIfPowerNegative`.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=(
                    f"{source.name}: creatures you control with toughness greater than "
                    "power assign damage equal to toughness"
                ),
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=creatures_controlled_by_toughness_exceeds_power(source.controller),
                modification=grant_ability(ASSIGNS_DAMAGE_AS_TOUGHNESS_TEXT),
            )
        ]

    return builder


def _group_power_or_toughness_unblockable_builder(threshold: int, *, line: str) -> EffectBuilder:
    """Tetsuko Umezawa, Fugitive: "Creatures you control with power or
    toughness 1 or less can't be blocked." - granted as the self-referential
    "This creature can't be blocked." line `machines/combat.py`'s
    `_evasion_restriction_sentences` already reads off a computed ability
    (CR 613.5), so no change to that reader is needed: it does not care which
    permanent's static ability put the line there.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=(
                    f"{source.name}: creatures you control with power or toughness "
                    f"{threshold} or less can't be blocked"
                ),
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=creatures_controlled_by_power_or_toughness_at_most(
                    source.controller, threshold
                ),
                modification=grant_ability("This creature can't be blocked."),
            )
        ]

    return builder


def _group_quoted_ability_grant_builder(granted: str, *, line: str) -> EffectBuilder:
    """ "Planeswalkers you control have "`<ability>`"." - see
    `_GROUP_QUOTED_ABILITY_GRANT_RE` above.

    Layer 6 (CR 613.1f, CR 113.10a), over `permanents_controlled_by(...,
    Type.PLANESWALKER)` - the same board-wide subject `_board_wide_type_
    grant_builder` and every other "`<card type>`s you control" static
    already read with, just handing `grant_ability` a whole quoted line
    instead of a bare keyword. Making the granted line actually activatable
    (not merely present in `Characteristics.abilities`) is `quoted_ability_
    grants`' own job, reconciled onto `CardState.granted_ability_texts` by
    `sync_granted_ability_texts` every sweep - this builder only has to put
    it on the computed board, the same division of labour `_attached_
    creature_static_builder`'s own `granted` parameter already draws.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=f'{source.name}: planeswalkers you control have "{granted}"',
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=permanents_controlled_by(source.controller, Type.PLANESWALKER),
                modification=grant_ability(granted),
            )
        ]

    return builder


def _self_assigns_damage_as_though_positive_builder(*, line: str) -> EffectBuilder:
    """Loot, the Anomaly: "If Loot's power is negative, he assigns combat
    damage as though his power were positive." - the condition lives in
    `SelfIfPowerNegative` rather than being checked at build time, the same
    choice the group grant above makes.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=f"{source.name}: assigns damage as though power were positive",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=self_if_power_negative(source.id),
                modification=grant_ability(ASSIGNS_DAMAGE_AS_THOUGH_POSITIVE_TEXT),
            )
        ]

    return builder


def _context_gated_self_static_builder(
    condition: Callable[[CardState, LayerContext], bool],
    granted: list[str],
    *,
    line: str,
    description: str,
) -> EffectBuilder:
    """A self keyword/ability grant gated by something `LayerContext` carries
    rather than the board itself - whose turn it is (Skilled Battlecarver's
    "During your turn, ..."), a per-turn fact (Whiplash Wordsmith's "As long
    as an opponent was dealt noncombat damage this turn, ..."; Surveillance
    Phantasm's "As long as you've scried or surveilled this turn, ..."), or a
    per-object one (Ruric Thar's "... as long as they haven't dealt combat
    damage yet").

    Checked at build time, the same choice `_graveyard_card_count_gated_
    self_static_builder` makes and for the identical reason: CR 604.2 has the
    effect active exactly while the ability's condition holds, and
    `effects_for` reruns on every CR 613.5 computation - built from a fresh
    `LayerContext` each time - so the grant switches off the moment the
    condition stops holding rather than needing a stored `Duration`.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        if not condition(source, context):
            return []
        return [
            ContinuousEffect(
                description=f"{source.name}: has {ability} {description}",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=_only(source.id),
                modification=grant_ability(ability),
            )
            for ability in granted
        ]

    return builder


def _per_color_keyword_grant_builder(
    grants: list[tuple[str, Color]], *, line: str
) -> EffectBuilder:
    """`_PER_COLOR_KEYWORD_GRANT_RE`'s shape - Scion of Draco's five
    colour-conditioned grants.

    One layer 6 effect (CR 613.1f) per clause, each selecting only the
    creatures of that colour. The condition is part of *what the effect applies
    to*, not a duration: CR 611.3a says a static ability's effect "isn't
    'locked in'; it applies at any given moment to whatever its text
    indicates", so a creature that becomes blue later is warded by the hexproof
    clause from that moment, with no new effect created.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=f"{source.name}: your {color.value} creatures have {keyword}",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=creatures_controlled_by_with_color(source.controller, color),
                modification=grant_ability(keyword),
            )
            for keyword, color in grants
        ]

    return builder


def _permanents_with_counters_ward_builder(cost: str, *, line: str) -> EffectBuilder:
    """`_PERMANENTS_WITH_COUNTERS_WARD_RE`'s shape - Innkeeper's Talent at
    level 2.

    Layer 6 (CR 613.1f). Granted through `grant_ability_instance`, not
    `grant_ability`: ward is a triggered ability (CR 702.21a) with no
    redundancy clause of its own, so two sources granting it give the permanent
    two of them (CR 113.2c), each triggering separately.

    Whether this ability is live at all is the Class's own question, not this
    shape's - `effects_for` reads `CardState.class_ability_text` (CR 716.2a),
    so a level-1 Innkeeper's Talent never offers this sentence here.
    """

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=f"{source.name}: your permanents with counters have ward {cost}",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=permanents_controlled_by_with_counters(source.controller),
                modification=grant_ability_instance(f"Ward {cost}"),
            )
        ]

    return builder


#: The keyword grant shapes grant bare keywords from `machines/combat.py`'s
#: own vocabulary, since that is what a grant needs to be able to do anything
#: (`combat.has_keyword` is the only reader). Aerial Maneuver's "gains flying
#: **and first strike**" is why this is a whitelist and not `[a-z ]+` on its
#: own: "flying and first strike" is split into its keywords
#: (`_split_and_validate_keywords`) and granted as two real ones, never one
#: bogus ability. A keyword outside this set fails the match and falls to
#: `looks_like_unparsed_layer_effect` instead of silently granting the wrong
#: thing.
# Keywords no combat rule reads, and so absent from `machines/combat.py`'s own
# `Keyword` vocabulary, that a grant still has to be able to name -
# CR 702.12a's indestructible ("Indestructible is a static ability"; before it
# was here, "gains flying until end of turn" parsed and "gains indestructible
# until end of turn" did not, so a real grant silently did nothing) and
# CR 702.11a's hexproof, which Scion of Draco's colour-conditioned grant names.
# Named once, in `machines/combat.py`, because the reading vocabulary there
# needs the same two words.
#
# What a granted line is *read* with is a separate question, and the assumption
# that used to be written here - that `combat.has_keyword` adding the word it
# is asked about to the vocabulary is enough for a granted line to be found by
# whoever asks - was wrong wherever a line holds more than one keyword. It held
# only for a line that is nothing but the single keyword being asked about;
# `machines/combat.py::_reading_vocabulary` is what makes a shared line work,
# and `KeywordLineNotice` is what records a line it still cannot read whole.
_KNOWN_KEYWORDS = frozenset(keyword.value for keyword in Keyword) | KEYWORDS_OUTSIDE_COMBAT
#: The public name for the same whitelist, for a caller outside this module
#: that needs to validate a keyword name the identical way every shape here
#: does - `machines/effects.py`'s own keyword-*choice* riders ("gains your
#: choice of trample, hexproof, or haste"), whose "or"-joined list is not
#: the "and"/comma grammar `_split_and_validate_keywords` reads.
KNOWN_KEYWORDS = _KNOWN_KEYWORDS


#: CR 702.11d / CR 702.16a: "hexproof from [quality]" and "protection from
#: [quality]" are their own variants of an already-known keyword, not a
#: keyword of their own on `_KNOWN_KEYWORDS`'s bare whitelist - the whole
#: reason `Dragonfire Blade` ("Equipped creature gets +2/+2 and has hexproof
#: from monocolored.") and the Sword cycle ("Equipped creature gets +2/+2
#: and has protection from red and from blue.", Sword of Fire and Ice) went
#: unread: neither "hexproof from monocolored" nor "protection from red and
#: from blue" is ever going to equal a bare keyword string.
#:
#: CR 702.16g: "'Protection from [quality A] and from [quality B]' is
#: shorthand for 'protection from [quality A]' and 'protection from
#: [quality B]'; it behaves as two separate protection abilities." CR
#: 702.11f says the identical thing for hexproof. So a multi-quality list is
#: split into that many separate result entries here, the same way
#: `_INDEFINITE_KEYWORD_AND_PROTECTION_GRANT_RE`'s own builder already
#: splits Akroma's Memorial's "protection from black and from red" into two
#: granted ability strings via `_split_protection_qualities` rather than
#: granting one combined line - this reuses that same split so both grant
#: shapes agree on what "two separate abilities" produces.
#:
#: The quality word itself (a colour here, but CR 702.16a/CR 702.11d both
#: allow "any characteristic value or information") is read only at
#: enforcement time (`Game._effective_protection_qualities`,
#: `Game.hexproof_abilities`) and is not validated here - the same
#: fail-open choice this project already makes for a printed protection/
#: hexproof line whose quality it cannot read, rather than refusing the
#: whole grant over one word neither of those functions will recognise
#: anyway.
_QUALIFIED_KEYWORD_RE = re.compile(
    r"^(?P<keyword>hexproof|protection) from (?P<qualities>[a-z]+(?:\s+and\s+from\s+[a-z]+)*)",
    re.IGNORECASE,
)
#: A bare keyword item, one or two words (CR 700.7's "first strike", "double
#: strike") - `_split_and_validate_keywords`'s own tokenizer tries
#: `_QUALIFIED_KEYWORD_RE` first at each position, so an "and" inside a
#: qualified keyword's own "[quality A] and from [quality B]" list is never
#: mistaken for the separator between two different keywords the way a
#: single upfront `re.split` on "and" already was.
_BARE_KEYWORD_ITEM_RE = re.compile(r"^([a-z]+(?: [a-z]+)?)(?:,\s*|\s+and\s+|$)", re.IGNORECASE)
#: A keyword written with its number (CR 702.164a: "It is written 'toxic N,'
#: where N is a number") - Prosthetic Injector's "has toxic 1", Necrogen
#: Communion's "has toxic 2". Tried before `_BARE_KEYWORD_ITEM_RE`, whose one-
#: or-two-word item has no room for a digit. Granted as "Toxic 1", the same
#: line a printed instance is, so `combat.total_toxic_value` sums the two.
_NUMBERED_KEYWORD_ITEM_RE = re.compile(
    r"^(?P<keyword>[a-z]+) (?P<n>\d+)(?:,\s*|\s+and\s+|$)", re.IGNORECASE
)
#: The keywords `_NUMBERED_KEYWORD_ITEM_RE` may grant: the ones written with
#: an N that some machine reads the N of.
_KNOWN_NUMBERED_KEYWORDS = frozenset({Keyword.TOXIC.value})
#: A keyword written with its cost - CR 702.21a's "Ward [cost]" ("with ward
#: {3}", Hall of Storm Giants). Granted as "Ward {3}", the same line a printed
#: instance is, so `machines/keywords.py`'s ward expansion reads its cost.
_COSTED_KEYWORD_ITEM_RE = re.compile(
    r"^(?P<keyword>ward) (?P<cost>(?:\{[^}]+\})+)(?:,\s*|,?\s+and\s+|$)", re.IGNORECASE
)


def _split_and_validate_keywords(raw: str) -> list[str] | None:
    """ "double strike and lifelink" / "menace, deathtouch and first strike" /
    "hexproof from monocolored" / "protection from red and from blue" -> each
    keyword, capitalised, with a multi-quality "from A and from B" item split
    into that many separate "<Keyword> from <quality>" entries (CR 702.16g/
    CR 702.11f) - or `None` if a bare item is not on `_KNOWN_KEYWORDS`'s
    whitelist, the same fail-closed rule the single-keyword shapes already
    enforce. A left-to-right tokenizer rather than one upfront split, since a
    qualified keyword's own "and from" would otherwise be cut apart by the
    same comma/"and" separator that splits two different keywords from each
    other.
    """
    result: list[str] = []
    remaining = raw.strip()
    while remaining:
        # An Oxford-comma list ("trample, lifelink, and indestructible") ends
        # a middle item on its own comma (`,\s*`, not `\s+and\s+`), leaving
        # "and " dangling in front of the *next* item rather than consumed as
        # part of the item that just matched. Stripped here, once per item,
        # so the following match always starts on the bare word - otherwise
        # `_BARE_KEYWORD_ITEM_RE`'s own optional second-word group happily
        # captures "and indestructible" as one two-word candidate (its tail
        # alternation is satisfied by end-of-string), which is not a keyword
        # `_KNOWN_KEYWORDS` has ever heard of, and the whole list failed
        # closed instead of reading its own last item.
        remaining = re.sub(r"^(?:,\s*|and\s+)", "", remaining, flags=re.IGNORECASE).strip()
        if not remaining:
            break
        qualified = _QUALIFIED_KEYWORD_RE.match(remaining)
        if qualified is not None:
            keyword = qualified.group("keyword").capitalize()
            for quality in _split_protection_qualities(qualified.group("qualities")):
                result.append(f"{keyword} from {quality}")
            remaining = remaining[qualified.end() :].strip()
            continue
        costed = _COSTED_KEYWORD_ITEM_RE.match(remaining)
        if costed is not None:
            result.append(f"{costed.group('keyword').capitalize()} {costed.group('cost')}")
            remaining = remaining[costed.end() :].strip()
            continue
        numbered = _NUMBERED_KEYWORD_ITEM_RE.match(remaining)
        if numbered is not None and numbered.group("keyword").lower() in _KNOWN_NUMBERED_KEYWORDS:
            result.append(f"{numbered.group('keyword').capitalize()} {numbered.group('n')}")
            remaining = remaining[numbered.end() :].strip()
            continue
        bare = _BARE_KEYWORD_ITEM_RE.match(remaining)
        if bare is None:
            return None
        word = bare.group(1).strip()
        if word.lower() not in _KNOWN_KEYWORDS:
            return None
        result.append(word.capitalize())
        remaining = remaining[bare.end() :].strip()
    return result or None


#: The public name for the same reader, for `machines/effects.py`'s own
#: direct (non-layer-shaped-subject) keyword-grant clauses - Tomik, Orzhov
#: Lawmage's "Target creature with a +1/+1 counter on it gains flying until
#: end of turn.", whose target phrase `machines/layers.py`'s own narrow
#: `_SUBJECT` pattern was never meant to grow a comparison/counter grammar
#: to match, when `machines/targeting.py` already reads it in full.
split_and_validate_keywords = _split_and_validate_keywords


def _split_protection_qualities(raw: str) -> list[str]:
    """ "black and from red" -> ["black", "red"] (CR 702.16g).

    The same split `models/game.py`'s `protection_qualities` runs on an
    ordinary printed "protection from A and from B" line - kept as its own
    small copy here rather than imported, since `models/game.py` already
    imports this module and a reverse import would cycle.
    """
    return [part.strip() for part in re.split(r"\s+and from\s+", raw, flags=re.IGNORECASE)]


def _parse_board_gated_group_sentence(sentence: str) -> EffectBuilder | None:
    """ "As long as you control ten or more lands, creatures you control get
    +2/+2." (Fecund Greenshell, read with `resolve_cards`) - a group shape with
    a whole-board condition printed in front of it.

    The condition is not a `Duration`. CR 604.2: a static ability's continuous
    effects "are active as long as the permanent with the ability remains on
    the battlefield and has the ability", and CR 611.3a adds that such an
    effect "isn't 'locked in'; it applies at any given moment to whatever its
    text indicates" - so the count is taken off the computed board every time
    CR 613.5 recomputes it, and the anthem is simply absent while the count is
    short. `_graveyard_card_types_gated_self_static_builder` makes the same
    choice for delirium; this one can go further and keep the test inside the
    `Selector`, because the board a `Selector` is handed is the whole board.

    Only the two group shapes are gated here. A gate in front of anything else
    fails the parse and falls through to `looks_like_unparsed_layer_effect`
    rather than being quietly dropped.
    """
    match = _BOARD_COUNT_GATE_RE.fullmatch(sentence)
    if match is None:
        return None
    threshold = parse_count(match.group("count"), article=False)
    card_type = _card_type_word(match.group("subject"))
    if threshold is None or card_type is None:
        return None
    gate = CreatureQualifiers(
        gate_card_type=card_type,
        gate_threshold=threshold,
        gate_words=f"as long as you control {match.group('count').lower()} or more "
        f"{match.group('subject').lower()}, ",
    )
    rest = match.group("rest").strip()
    if anthem := _ANTHEM_RE.fullmatch(rest):
        return _anthem_builder(
            int(anthem.group("power")),
            int(anthem.group("toughness")),
            other=anthem.group("other") is not None,
            whose=anthem.group("whose").lower(),
            line=sentence,
            qualifiers=qualifiers_from_subject(anthem, gate),
        )
    if grant := _INDEFINITE_KEYWORD_GRANT_RE.fullmatch(rest):
        keywords = _split_and_validate_keywords(grant.group("keywords"))
        if keywords is None:
            return None
        return _indefinite_keyword_grant_builder(
            keywords,
            other=grant.group("other") is not None,
            whose=grant.group("whose").lower(),
            line=sentence,
            qualifiers=qualifiers_from_subject(grant, gate),
        )
    return None


def _parse_layer_sentence(sentence: str) -> EffectBuilder | None:
    """One of the generalised shapes below, or `None` if this is not one of them.

    `sentence` is normalised for a duration-first opening
    (`_normalize_duration_first`) before any shape is tried, so "Until end of
    turn, target creature gets +4/+4" reads the same as "Target creature gets
    +4/+4 until end of turn."
    """
    sentence = _strip_ability_word(_normalize_duration_first(sentence))
    if _BOARD_COUNT_GATE_RE.fullmatch(sentence):
        return _parse_board_gated_group_sentence(sentence)
    if match := _TARGET_AND_SAME_NAME_PUMP_RE.fullmatch(sentence):
        return _target_and_same_name_pump_builder(
            int(match.group("power")), int(match.group("toughness"))
        )
    if _TARGETED_LOSES_ALL_ABILITIES_RE.fullmatch(sentence):
        return _targeted_loses_all_abilities_builder()
    if match := _PUMP_RE.fullmatch(sentence):
        power_raw = match.group("power") or match.group("power2")
        toughness_raw = match.group("toughness") or match.group("toughness2")
        keyword_text = match.group("keyword") or match.group("keyword2")
        granted: list[str] = []
        if keyword_text is not None:
            validated = _split_and_validate_keywords(keyword_text)
            if validated is None:
                return None
            granted = validated
        until_next_turn = match.group("duration").strip().lower() == "until your next turn"
        if power_raw.lstrip("+-").lower() == "x" or toughness_raw.lstrip("+-").lower() == "x":
            where_x = match.group("where_x")
            if where_x is None or not _THAT_CREATURES_POWER_RE.fullmatch(where_x.strip()):
                return None
            power_sign = -1 if power_raw.startswith("-") else 1
            toughness_sign = -1 if toughness_raw.startswith("-") else 1
            return _pump_and_keyword_per_target_power_builder(power_sign, toughness_sign, granted)
        power, toughness = int(power_raw), int(toughness_raw)
        return _pump_and_keyword_builder(power, toughness, granted, until_next_turn=until_next_turn)
    if match := _SELF_PUMP_PER_GRAVEYARD_CARD_RE.fullmatch(sentence):
        words = re.split(r",\s*|\s+and\s+", match.group("qualifier"))
        card_types = [_card_type_word(word) for word in words]
        if any(card_type is None for card_type in card_types):
            return None
        return _self_pump_per_graveyard_card_builder(
            int(match.group("power")),
            int(match.group("toughness")),
            [card_type for card_type in card_types if card_type is not None],
        )
    if match := _SELF_PUMP_PER_GRAVEYARD_CARD_BATCH_RE.fullmatch(sentence):
        batch_size = parse_count(match.group("batch"), article=False)
        if not batch_size:
            return None
        return _self_pump_per_graveyard_card_batch_builder(
            int(match.group("power")), int(match.group("toughness")), batch_size
        )
    if match := _SELF_PUMP_PER_CONTROLLED_PERMANENT_RE.fullmatch(sentence):
        # A card type (the Urza's Saga Construct's "artifact") or a subtype
        # (Outcaster Greenblade's "Desert").
        count = _controlled_count_factory(match.group("qualifier"))
        if count is None:
            return None
        return _self_pump_per_controlled_permanent_builder(
            int(match.group("power")),
            int(match.group("toughness")),
            match.group("qualifier").lower(),
            count,
        )
    if match := _SELF_PUMP_PER_COLOR_AMONG_RE.fullmatch(sentence):
        count_colors = _colors_among_count_factory(
            match.group("qualifier"), excludes_self=match.group("other") is not None
        )
        if count_colors is None:
            return None
        return _self_pump_per_controlled_permanent_builder(
            int(match.group("power")),
            int(match.group("toughness")),
            f"color among {match.group('other') or ''}{match.group('qualifier').lower()}",
            count_colors,
        )
    if match := _SELF_PUMP_PER_OTHER_CREATURE_NAMED_RE.fullmatch(sentence):
        return _self_pump_per_other_creature_named_builder(
            int(match.group("power")),
            int(match.group("toughness")),
            match.group("name").strip(),
            match.group("you_control") is not None,
            sentence,
        )
    if match := _BECOME_A_COPY_RE.fullmatch(sentence):
        return _become_a_copy_builder(until_eot=bool(match.group("until_eot")))
    if match := _SELF_HAS_COUNTED_TRIGGER_KEYWORD_RE.fullmatch(sentence):
        return _self_has_counted_trigger_keyword_builder(match, sentence)
    if match := _KEYWORD_GRANT_RE.fullmatch(sentence):
        keywords = _split_and_validate_keywords(match.group("keywords"))
        if keywords is None:
            return None
        return _keyword_grant_builder(keywords)
    if match := _ANTHEM_PER_COUNT_RE.fullmatch(sentence):
        count = _controlled_count_factory(match.group("each"))
        keywords = (
            _split_and_validate_keywords(match.group("keywords"))
            if match.group("keywords") is not None
            else []
        )
        if count is None or keywords is None:
            return None
        return _anthem_and_keyword_grant_builder(
            int(match.group("power")),
            int(match.group("toughness")),
            keywords,
            other=match.group("other") is not None,
            whose=match.group("whose").lower(),
            line=sentence,
            qualifiers=qualifiers_from_subject(match),
            per=(match.group("each").lower(), count),
        )
    if match := _ANTHEM_AND_KEYWORD_GRANT_RE.fullmatch(sentence):
        keywords = _split_and_validate_keywords(match.group("keywords"))
        if keywords is None:
            return None
        return _anthem_and_keyword_grant_builder(
            int(match.group("power")),
            int(match.group("toughness")),
            keywords,
            other=match.group("other") is not None,
            whose=match.group("whose").lower(),
            line=sentence,
            qualifiers=qualifiers_from_subject(match),
        )
    if match := (_ANTHEM_RE.fullmatch(sentence) or _EACH_ANTHEM_RE.fullmatch(sentence)):
        return _anthem_builder(
            int(match.group("power")),
            int(match.group("toughness")),
            other=match.group("other") is not None,
            whose=match.group("whose").lower(),
            line=sentence,
            qualifiers=qualifiers_from_subject(match),
        )
    if match := _MASS_PUMP_UNTIL_EOT_RE.fullmatch(sentence):
        keywords: list[str] = []
        keyword_text = match.group("keywords") or match.group("keywords_after")
        if keyword_text is not None:
            validated = _split_and_validate_keywords(keyword_text)
            if validated is None:
                return None
            keywords = validated
        power_text = match.group("power") or match.group("power_only")
        toughness_text = match.group("toughness") or match.group("toughness_only")
        if power_text is None and not keywords:
            return None
        power = int(power_text) if power_text is not None else None
        toughness = int(toughness_text) if toughness_text is not None else None
        return _mass_pump_until_eot_builder(power, toughness, keywords)
    if match := _DURING_YOUR_TURN_MULTI_TYPE_KEYWORD_GRANT_RE.fullmatch(sentence):
        card_type1 = _card_type_word(match.group("type1"))
        card_type2 = _card_type_word(match.group("type2"))
        keywords = _split_and_validate_keywords(match.group("keywords"))
        if card_type1 is None or card_type2 is None or keywords is None:
            return None
        return _during_your_turn_multi_type_keyword_grant_builder(
            (card_type1, card_type2), keywords, line=sentence
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
            qualifiers=qualifiers_from_subject(match),
        )
    if match := _GROUP_ATTACK_WITHOUT_DEFENDER_RE.fullmatch(sentence):
        return _indefinite_keyword_grant_builder(
            [ATTACK_WITHOUT_DEFENDER_TEXT],
            other=match.group("other") is not None,
            whose=match.group("whose").lower(),
            line=sentence,
            qualifiers=qualifiers_from_subject(match),
        )
    if match := _INDEFINITE_KEYWORD_AND_PROTECTION_GRANT_RE.fullmatch(sentence):
        keywords: list[str] = []
        if match.group("keywords") is not None:
            validated = _split_and_validate_keywords(match.group("keywords"))
            if validated is None:
                return None
            keywords = validated
        qualities = _split_protection_qualities(match.group("qualities"))
        abilities = keywords + [f"Protection from {quality}" for quality in qualities]
        return _indefinite_keyword_grant_builder(
            abilities,
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
    if _GAIN_CONTROL_UNTIL_EOT_RE.fullmatch(sentence):
        return _gain_control_until_eot_builder()
    if match := _BECOMES_COLOR_RE.fullmatch(sentence):
        return _becomes_color_builder(
            _COLOR_WORDS[match.group("color").lower()],
            until_eot=bool(match.group("until_eot")),
        )
    if match := _BECOMES_CREATURE_TYPE_WITH_BASE_PT_RE.fullmatch(sentence):
        subtype = next(
            (kind for kind in creature_types() if kind.lower() == match.group("subtype").lower()),
            None,
        )
        if subtype is None:
            return None
        color = match.group("color")
        return _becomes_creature_type_with_base_pt_builder(
            subtype,
            _COLOR_WORDS[color.lower()] if color else None,
            int(match.group("power")),
            int(match.group("toughness")),
            loses_abilities=match.group("loses") is not None,
        )
    if match := _BECOMES_TYPE_IN_ADDITION_RE.fullmatch(sentence):
        extra_type = _OTHER_PERMANENT_TYPE_WORDS.get(match.group("extra_type").lower())
        if extra_type is None:
            return None
        return _becomes_type_in_addition_builder(extra_type)
    if match := _BECOMES_SUBTYPE_IN_ADDITION_RE.fullmatch(sentence):
        subtypes = _creature_type_words(match.group("subtypes"))
        keywords = (
            _split_and_validate_keywords(match.group("keywords"))
            if match.group("keywords") is not None
            else []
        )
        if subtypes is None or keywords is None:
            return None
        duration = Duration.UNTIL_END_OF_TURN if match.group("until_eot") else Duration.INDEFINITE
        return _becomes_subtype_in_addition_builder(subtypes, keywords, duration)
    if match := _SELF_BECOMES_TYPE_UNTIL_NEXT_TURN_RE.fullmatch(sentence):
        extra_type = _card_type_word(match.group("extra_type"))
        if extra_type is None:
            return None
        return _self_becomes_type_until_next_turn_builder(extra_type, match.group("ability"))
    if (animation := _parse_animation_sentence(sentence)) is not None:
        return animation
    return _parse_static_layer_sentence(sentence)


def _parse_static_layer_sentence(sentence: str) -> EffectBuilder | None:
    """The board-wide and filtered *static* shapes (CR 611.3), split out of
    `_parse_layer_sentence` only to keep either function readable - the two are
    one lookup, tried in this order.

    Every shape here reads a permanent's own printed sentence rather than its
    name, which is the whole of Blood Moon, Harbinger of the Seas, Dryad of the
    Ilysian Grove, Leyline of the Guildpact, Urborg, Yavimaya and Toph.
    """
    if _SELF_PROTECTION_FROM_CHOSEN_COLOR_RE.fullmatch(sentence):
        return _self_protection_from_chosen_color_builder(line=sentence)
    if match := _EACH_ANTHEM_PER_OTHER_CREATURE_RE.fullmatch(sentence):
        if match.group("whose").lower() != "you control":
            return None
        return _per_other_creature_anthem_builder(
            int(match.group("power")),
            int(match.group("toughness")),
            other=match.group("other") is not None,
            same_name=match.group("same_name") is not None,
            count_legendary=match.group("count_legendary") is not None,
            line=sentence,
            qualifiers=qualifiers_from_subject(match),
        )
    if match := _NONBASIC_LANDS_ARE_RE.fullmatch(sentence):
        subtype = _BASIC_LAND_TYPE_WORDS[match.group("subtype").lower()]
        return _nonbasic_lands_are_builder(subtype)
    if _LANDS_ARE_EVERY_BASIC_TYPE_RE.fullmatch(sentence):
        return _lands_are_every_basic_type_builder(sentence)
    if match := _EACH_LAND_IS_RE.fullmatch(sentence):
        subtype = _BASIC_LAND_TYPE_WORDS[match.group("subtype").lower()]
        return _each_land_is_builder(subtype, sentence)
    if match := _BOARD_WIDE_TYPE_GRANT_RE.fullmatch(sentence):
        subject = _card_type_word(match.group("subject"))
        granted = _card_type_word(match.group("granted"))
        if subject is None or granted is None:
            return None
        return _board_wide_type_grant_builder(
            subject,
            granted,
            nontoken=match.group("nontoken") is not None,
            line=sentence,
        )
    if match := _CREATURE_WITH_COUNTER_KEYWORD_GRANT_RE.fullmatch(sentence):
        keywords = _split_and_validate_keywords(match.group("keywords"))
        if keywords is None:
            return None
        return _counter_gated_keyword_grant_builder(
            match.group("counter"),
            keywords,
            other=match.group("other") is not None,
            line=sentence,
        )
    if match := _LANDS_KEYWORD_GRANT_RE.fullmatch(sentence):
        keywords = _split_and_validate_keywords(match.group("keywords"))
        if keywords is None:
            return None
        return _lands_keyword_grant_builder(keywords, line=sentence)
    if match := _SUBTYPE_ANTHEM_RE.fullmatch(sentence):
        subtypes = _subtype_list_words(match.group("subtypes"))
        if subtypes is None:
            return None
        return _filtered_anthem_builder(
            subtypes,
            int(match.group("power")),
            int(match.group("toughness")),
            [],
            other=match.group("other") is not None,
            line=sentence,
        )
    if match := _SUBTYPE_KEYWORD_GRANT_RE.fullmatch(sentence):
        subtypes = _subtype_list_words(match.group("subtypes"))
        keywords = _split_and_validate_keywords(match.group("keywords"))
        if subtypes is None or keywords is None:
            return None
        return _filtered_anthem_builder(
            subtypes,
            0,
            0,
            keywords,
            other=match.group("other") is not None,
            line=sentence,
        )
    if match := _FILTERED_CREATURE_ANTHEM_RE.fullmatch(sentence):
        subtypes = _split_subtype_list(match.group("subtypes"))
        if subtypes is None:
            return None
        keywords: list[str] = []
        if match.group("keywords") is not None:
            validated = _split_and_validate_keywords(match.group("keywords"))
            if validated is None:
                return None
            keywords = validated
        return _filtered_anthem_builder(
            subtypes,
            int(match.group("power")),
            int(match.group("toughness")),
            keywords,
            other=match.group("other") is not None,
            line=sentence,
        )
    if _BASIC_LAND_TYPE_COUNT_CDA_RE.fullmatch(sentence):
        return _basic_land_type_count_cda_builder(sentence)
    if _BASIC_LAND_TYPE_COUNT_POWER_ONLY_CDA_RE.fullmatch(sentence):
        return _basic_land_type_count_power_only_cda_builder(sentence)
    if match := _QUALIFIER_COUNT_CDA_RE.fullmatch(sentence):
        count = _controlled_count_factory(match.group("qualifier"))
        if count is not None:
            return _qualifier_count_cda_builder(sentence, match.group("qualifier").lower(), count)
    if match := _GRAVEYARD_CARD_COUNT_CDA_RE.fullmatch(sentence):
        words = re.split(r",\s*|\s+and/or\s+|\s+and\s+|\s+or\s+", match.group("types"))
        card_types = [_card_type_word(word) for word in words if word]
        if card_types and all(card_type is not None for card_type in card_types):
            return _graveyard_card_count_cda_builder(
                sentence,
                tuple(card_type for card_type in card_types if card_type is not None),
                2 if match.group("twice") else 1,
            )
    if match := _CREATURE_SUBTYPE_COUNT_CDA_RE.fullmatch(sentence):
        words = re.split(r",\s*|\s+and/or\s+|\s+and\s+|\s+or\s+", match.group("subtypes"))
        subtypes = [_singular_subtype_word(word) for word in words if word]
        if not subtypes or any(subtype is None for subtype in subtypes):
            return None
        return _creature_subtype_count_cda_builder(tuple(subtypes), line=sentence)
    if match := _ATTACHED_CREATURE_PUMP_AND_QUOTED_RE.fullmatch(sentence):
        keywords = []
        if match.group("keywords") is not None:
            validated = _split_and_validate_keywords(match.group("keywords"))
            if validated is None:
                return None
            keywords = validated
        return _attached_creature_static_builder(
            int(match.group("power")),
            int(match.group("toughness")),
            keywords,
            subject=match.group("attachment").lower(),
            granted=match.group("granted").strip() or None,
            line=sentence,
        )
    if match := _ATTACHED_CREATURE_STATIC_RE.fullmatch(sentence):
        raw_keywords = match.group("keywords") or match.group("only_keywords")
        keywords = []
        if raw_keywords is not None:
            validated = _split_and_validate_keywords(raw_keywords)
            if validated is None:
                return None
            keywords = validated
        base_power = match.group("base_power")
        base_toughness = match.group("base_toughness")
        return _attached_creature_static_builder(
            int(match.group("power") or 0),
            int(match.group("toughness") or 0),
            keywords,
            subject=match.group("attachment").lower(),
            granted=(match.group("granted") or "").strip() or None,
            base_power=int(base_power) if base_power is not None else None,
            base_toughness=int(base_toughness) if base_toughness is not None else None,
            line=sentence,
        )
    if match := _ATTACHED_CREATURE_LOSES_AND_BECOMES_RE.fullmatch(sentence):
        types = [_card_type_word(word) for word in match.group("types").split()]
        if any(card_type is None for card_type in types):
            return None
        return _attached_creature_loses_and_becomes_builder(
            match.group("subtype"),
            [card_type for card_type in types if card_type is not None],
            int(match.group("power")),
            int(match.group("toughness")),
            subject=match.group("attachment").lower(),
            line=sentence,
        )
    if match := _ATTACHED_PERMANENT_BECOMES_CREATURE_RE.fullmatch(sentence):
        return _attached_permanent_becomes_creature_builder(
            match.group("subtype"),
            int(match.group("power")),
            int(match.group("toughness")),
            subject=match.group("subject").lower(),
            line=sentence,
        )
    if match := _DONT_CAUSE_TRIGGERS_RE.fullmatch(sentence):
        words = re.split(r",\s*|\s+and\s+", match.group("types"))
        card_types = [_card_type_word(word.rstrip("sS")) for word in words]
        if any(
            card_type is None or card_type not in _DONT_CAUSE_TRIGGERS_TEXT_BY_TYPE
            for card_type in card_types
        ):
            return None
        return _self_suppresses_etb_triggers_builder(
            [card_type for card_type in card_types if card_type is not None], line=sentence
        )
    if _SPELLS_HAVE_SPLIT_SECOND_RE.fullmatch(sentence):
        return _self_grants_split_second_builder(line=sentence)
    if _LEGEND_RULE_EXEMPT_THIS_TURN_RE.fullmatch(sentence):
        return _self_legend_rule_exempt_builder(until_end_of_turn=True, line=sentence)
    if _LEGEND_RULE_EXEMPT_RE.fullmatch(sentence):
        return _self_legend_rule_exempt_builder(until_end_of_turn=False, line=sentence)
    if _SELF_DOESNT_UNTAP_RE.fullmatch(sentence):
        return _self_doesnt_untap_builder(line=sentence)
    if match := _ATTACHED_DOESNT_UNTAP_RE.fullmatch(sentence):
        return _attached_doesnt_untap_builder(
            subject=match.group("attachment").lower(),
            loses_abilities=match.group("loses") is not None,
            line=sentence,
        )
    if match := _OTHER_CREATURES_ARE_TYPE_RE.fullmatch(sentence):
        granted_type = _card_type_word(match.group("granted"))
        if granted_type is None:
            return None
        ability = (match.group("ability") or "").strip() or None
        return _other_creatures_are_type_builder(
            match.group("subtype"),
            granted_type,
            ability,
            other=match.group("other") is not None,
            line=sentence,
        )
    if match := _ALL_COLORS_RE.fullmatch(sentence):
        return _all_colors_builder(nonland=match.group("nonland") is not None, line=sentence)
    if match := _GRAVEYARD_CARD_TYPES_GATED_SELF_STATIC_RE.fullmatch(sentence):
        threshold = parse_count(match.group("count"), article=False)
        if threshold is None:
            return None
        granted = _split_gated_grants(match.group("rest"))
        if granted is None:
            return None
        if match.group("linked") is not None:
            return _linked_exile_card_types_gated_self_static_builder(
                threshold,
                int(match.group("power")),
                int(match.group("toughness")),
                granted,
                line=sentence,
            )
        return _graveyard_card_types_gated_self_static_builder(
            threshold,
            int(match.group("power")),
            int(match.group("toughness")),
            granted,
            line=sentence,
        )
    if match := _GRAVEYARD_CARD_COUNT_GATED_SELF_STATIC_RE.fullmatch(sentence):
        threshold = parse_count(match.group("count"), article=False)
        if threshold is None:
            return None
        rest = re.sub(r"^\s*and\s+", ", ", match.group("rest"))
        granted = _split_gated_grants(rest)
        if granted is None:
            return None
        return _graveyard_card_count_gated_self_static_builder(
            threshold,
            int(match.group("power")),
            int(match.group("toughness")),
            granted,
            line=sentence,
        )
    for descend_re in (
        _DESCEND_GATED_SELF_STATIC_LEADING_RE,
        _DESCEND_GATED_SELF_STATIC_TRAILING_RE,
    ):
        if match := descend_re.fullmatch(sentence):
            threshold = parse_count(match.group("count"), article=False)
            if threshold is None:
                return None
            grant_only = match.group("grant_only")
            if grant_only is not None:
                granted = _split_gated_grants(grant_only)
                power = toughness = 0
            else:
                granted = _split_gated_grants(match.group("rest") or "")
                power = int(match.group("power"))
                toughness = int(match.group("toughness"))
            if granted is None:
                return None
            return _graveyard_count_gated_self_static_builder(
                threshold,
                power,
                toughness,
                granted,
                line=sentence,
                count_fn=count_permanent_cards,
            )
    if match := _PER_COLOR_KEYWORD_GRANT_RE.fullmatch(sentence):
        grants = _split_per_color_grants(match.group("clauses"))
        if grants is None:
            return None
        return _per_color_keyword_grant_builder(grants, line=sentence)
    if match := _PERMANENTS_WITH_COUNTERS_WARD_RE.fullmatch(sentence):
        return _permanents_with_counters_ward_builder(match.group("cost"), line=sentence)
    if match := _SELF_DURING_YOUR_TURN_KEYWORD_GRANT_RE.fullmatch(sentence):
        keywords = _split_and_validate_keywords(match.group("keywords"))
        if keywords is None:
            return None
        return _context_gated_self_static_builder(
            lambda source, context: context.active_player == source.controller,
            keywords,
            line=sentence,
            description="during your turn",
        )
    if match := _SELF_PUMP_WHILE_CONTROLS_RE.fullmatch(sentence):
        noun = match.group("noun").lower()
        pumped_type = None if noun == "permanent" else _card_type_word(noun)
        color_word = match.group("color")
        if (noun != "permanent" and pumped_type is None) or (
            pumped_type is None and color_word is None
        ):
            return None
        who = match.group("who").lower()
        return _self_pump_while_controls_builder(
            int(match.group("power")),
            int(match.group("toughness")),
            card_type=pumped_type,
            color=_COLOR_WORDS[color_word.lower()] if color_word else None,
            controlled_by="any" if who == "any player" else "you" if who == "you" else "opponent",
            line=sentence,
        )
    if match := _SELF_CONTROLS_KEYWORD_GRANT_RE.fullmatch(sentence):
        keywords = _split_and_validate_keywords(match.group("keywords"))
        card_type = _card_type_word(match.group("cardtype"))
        if keywords is None or card_type is None:
            return None
        return _self_gated_by_controlling_keyword_grant_builder(
            keywords, card_type=card_type, subtype=match.group("subtype"), line=sentence
        )
    conditional_type_change = _conditional_self_type_change(sentence)
    if conditional_type_change is not None:
        return conditional_type_change
    if match := _TURN_FACT_GATED_SELF_PUMP_RE.fullmatch(sentence):
        fact = _TURN_FACT_CONDITION_PHRASES.get(match.group("condition").strip().lower())
        granted = _split_gated_grants(re.sub(r"^\s*and\s+", ", ", match.group("rest")))
        if fact is not None and granted is not None:
            return _turn_fact_gated_self_pump_builder(
                fact,
                int(match.group("power")),
                int(match.group("toughness")),
                granted,
                line=sentence,
            )
    if match := _TURN_FACT_GATED_SELF_RE.fullmatch(sentence):
        fact = _TURN_FACT_CONDITION_PHRASES.get(match.group("condition").strip().lower())
        if fact is None:
            return None
        fact_name, subject = fact
        if match.group("no_defender"):
            granted = [ATTACK_WITHOUT_DEFENDER_TEXT]
        else:
            keywords = _split_and_validate_keywords(match.group("keywords"))
            if keywords is None:
                return None
            granted = keywords

        def turn_fact_condition(
            source: CardState,
            context: LayerContext,
            fact_name: str = fact_name,
            subject: str = subject,
        ) -> bool:
            if subject == "you":
                return context.has_turn_fact(fact_name, source.controller)
            return context.has_turn_fact_for_opponent(fact_name, source.controller)

        return _context_gated_self_static_builder(
            turn_fact_condition, granted, line=sentence, description="(turn condition)"
        )
    if match := _SELF_HASNT_DEALT_COMBAT_DAMAGE_RE.fullmatch(sentence):
        keywords = _split_and_validate_keywords(match.group("keywords"))
        if keywords is None:
            return None
        return _context_gated_self_static_builder(
            lambda source, context: source.id not in context.combat_damage_dealt_this_turn,
            keywords,
            line=sentence,
            description="before it deals combat damage",
        )
    if match := _SELF_MONSTROUS_GATED_RE.fullmatch(sentence):
        keywords = _split_and_validate_keywords(match.group("keywords"))
        if keywords is None:
            return None
        return _context_gated_self_static_builder(
            lambda source, context: source.monstrous,
            keywords,
            line=sentence,
            description="while monstrous",
        )
    if _GROUP_ASSIGNS_DAMAGE_AS_TOUGHNESS_RE.fullmatch(sentence):
        return _group_assigns_damage_as_toughness_builder(line=sentence)
    if _SELF_ASSIGNS_DAMAGE_AS_THOUGH_POSITIVE_RE.fullmatch(sentence):
        return _self_assigns_damage_as_though_positive_builder(line=sentence)
    if match := _GROUP_POWER_OR_TOUGHNESS_UNBLOCKABLE_RE.fullmatch(sentence):
        return _group_power_or_toughness_unblockable_builder(
            int(match.group("threshold")), line=sentence
        )
    if match := _GROUP_QUOTED_ABILITY_GRANT_RE.fullmatch(sentence):
        granted = match.group("ability").strip()
        if not granted:
            return None
        return _group_quoted_ability_grant_builder(granted, line=sentence)
    return None


def _split_subtype_list(raw: str) -> list[str] | None:
    """ "Cat, Elemental, Nightmare, Dinosaur, or Beast" -> each subtype,
    capitalised (CR 205.3m), or `None` if any item names one of CR 300.1's card
    types instead - a card type in this position is a different sentence
    entirely, and guessing at it would grant the wrong group.
    """
    parts = [part.strip() for part in re.split(r",\s*|\s+or\s+", raw) if part.strip()]
    subtypes = [_subtype_word(part) for part in parts]
    if not subtypes or any(subtype is None for subtype in subtypes):
        return None
    return [subtype for subtype in subtypes if subtype is not None]


def _split_gated_grants(rest: str) -> list[str] | None:
    """The tail of a gated self-static - ", has flying, and attacks each combat
    if able" or (Akawalli's own single-grant shape, no comma at all) " and has
    trample" - as the ability lines it grants.

    A "has <keyword(s)>" clause is validated against `_KNOWN_KEYWORDS` the same
    way every other grant here is; any other clause is granted verbatim, since
    `Characteristics.abilities` is ability *text* (CR 613.1f adds the ability,
    it does not say the reader must recognise it). An empty tail grants
    nothing, which is a plain conditional pump.
    """
    tail = rest.strip().lstrip(",").strip()
    tail = re.sub(r"^and\s+", "", tail, flags=re.IGNORECASE)
    if not tail:
        return []
    granted: list[str] = []
    for clause in re.split(r",\s*(?:and\s+)?|\s+and\s+", tail):
        clause = clause.strip()
        if not clause:
            continue
        if clause.lower().startswith("has "):
            validated = _split_and_validate_keywords(clause[4:])
            if validated is None:
                return None
            granted.extend(validated)
            continue
        granted.append(clause[0].upper() + clause[1:])
    return granted


def _split_per_color_grants(clauses: str) -> list[tuple[str, Color]] | None:
    """ "vigilance if it's white, hexproof if it's blue, ... and trample if
    it's green" -> each (ability, colour) pair, or `None` if any clause is not
    that shape or names a keyword outside `_KNOWN_KEYWORDS` - the same
    fail-closed rule the other keyword shapes enforce.
    """
    grants: list[tuple[str, Color]] = []
    for clause in re.split(r",\s*(?:and\s+)?", clauses):
        match = _ONE_COLOR_KEYWORD_CLAUSE_RE.fullmatch(clause.strip())
        if match is None:
            return None
        keyword = match.group("keyword").strip().lower()
        if keyword not in _KNOWN_KEYWORDS:
            return None
        grants.append((keyword.capitalize(), _COLOR_WORDS[match.group("color").lower()]))
    return grants or None


def parsed_layer_effects(
    oracle_text: str | None,
    *,
    static_only: bool = False,
    card_name: str | None = None,
    legendary: bool = True,
) -> EffectBuilder | None:
    """Every sentence of `oracle_text` that is one of the generalised shapes
    above, combined into one builder - or `None` if none of them matched at all.

    Sentences outside this wave's territory (a triggered ability, an
    intervening *if*, a bare keyword line, a token-creation instruction) are
    silently skipped rather than failing the whole card: they belong to a
    different registry or mechanism, not to a continuous effect at all.

    `static_only=True` restricts the sentences considered to `StaticAbility`
    bodies (see `_effect_sentences`) - `effects_for`'s battlefield sweep uses
    it so a triggered/activated ability's own effect text is never read as
    this permanent's static contribution.
    """
    builders = [
        builder
        for sentence in _effect_sentences(
            oracle_text, static_only=static_only, card_name=card_name, legendary=legendary
        )
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
        # CR 613.6's "already started applying" tracking (`_still_exists`) is
        # keyed by `(source_id, source_ability)` - right for a permanent's own
        # *ongoing* static ability, whose printed line a later effect can
        # genuinely remove out from under it, but wrong here: a "becomes a
        # copy" sentence (Hall of Echoes' own `{5}` ability) overwrites the
        # source's abilities in layer 1, which erases the *other* sentence's
        # printed line before layer 6 ever asks whether it is still there -
        # even though both sentences are one CR 608.2c instruction, resolved
        # together, at the same moment (CR 611.2c). Once any part of a
        # multi-sentence one-shot effect on the same source starts applying,
        # every part of it is "started" together, so every other effect this
        # sweep just built for the same source is re-keyed onto the copy
        # effect's own `source_ability` - the one whose text layer 1 is about
        # to erase.
        has_copy_effect = any(
            effect.source_id == source.id and effect.modification.kind == "become_a_copy"
            for effect in result
        )
        if has_copy_effect:
            copy_ability = next(
                effect.source_ability
                for effect in result
                if effect.source_id == source.id and effect.modification.kind == "become_a_copy"
            )
            result = [
                effect.model_copy(update={"source_ability": copy_ability})
                if effect.source_id == source.id
                else effect
                for effect in result
            ]
        return result

    return combined


def looks_like_unparsed_layer_effect(
    oracle_text: str | None,
    *,
    static_only: bool = False,
    card_name: str | None = None,
    legendary: bool = True,
) -> bool:
    """True if some sentence of `oracle_text` reads like one of the
    pump/keyword-grant/anthem shapes above but did not fully match - the
    fail-closed signal a caller records as a `LayerNotice` instead of
    silently producing nothing, mirroring `looks_like_unparsed_cost_modifier`
    (`machines/cost.py`) and the effect `TargetingNotice`/`InterveningIfNotice`
    (`machines/triggers.py`) already record for targets and intervening *if*.

    `static_only=True` is what `effects_for`'s battlefield sweep passes: see
    `layer_readable_sentences`'s docstring for why an unrestricted call here
    would fire a false notice on a permanent whose triggered ability (Kraul
    Harpooner's undergrowth pump) already resolves correctly through its own
    dedicated parser and never touches this function's answer at all.
    """
    return any(
        _LOOKS_LIKE_LAYER_EFFECT_RE.match(_normalize_duration_first(sentence))
        and _parse_layer_sentence(sentence) is None
        for sentence in _effect_sentences(
            oracle_text, static_only=static_only, card_name=card_name, legendary=legendary
        )
    )


def is_resolution_layer_effect_text(text: str | None) -> bool:
    """True if some sentence of `text` is - or looks like a failed attempt at -
    a one-shot **resolution** effect (CR 611.2) this wave reads: a pump, a
    keyword grant, a base P/T set, or "becomes a[n] <type> creature ...".
    The anthem shape is deliberately excluded (CR 611.3: "creatures you
    control get +N/+N" is always a permanent's own static ability), even
    when it fully parses - and so is Fiend Artisan's durationless "this
    creature gets +N/+N for each ... in your graveyard" self-pump, for the
    identical reason: it opens like `_PUMP_RE`'s one-shot shape but carries no
    "until end of turn", so it is CR 611.3's own static ability, never a
    resolving spell's or ability's effect.

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
        genuine, loose = _classify_resolution_layer_sentence(sentence)
        if genuine or loose:
            return True
    return False


def _classify_resolution_layer_sentence(sentence: str) -> tuple[bool, bool]:
    """`(genuine, loose)` for one sentence alone - the shared classification
    both `is_resolution_layer_effect_text` and `genuine_resolution_layer_
    text`/`is_genuine_resolution_layer_sentence` build on, so the CR 611.3
    exclusions (a static line, a durationless anthem or self-graveyard-pump)
    are written in exactly one place.

    `genuine` is true only for a sentence `create_continuous_effect`/
    `create_continuous_effect_of_ability` would actually turn into a real
    continuous effect (`_parse_layer_sentence` itself succeeds) and that is
    not one of the excluded CR 611.3 shapes. `loose` is true only when
    nothing here fully parses but the sentence still resembles a failed
    attempt (`_LOOKS_LIKE_RESOLUTION_LAYER_EFFECT_RE`, or an anthem-looking
    opening with an explicit duration that no specific shape below actually
    reads) - the signal `LayerNotice`/`ModeNotice` exist for. The two are
    mutually exclusive by construction: a sentence is never both.

    `_parse_layer_sentence` is tried **before** the anthem-with-duration
    check below, not after: an explicitly-durationed anthem-looking sentence
    ("Creatures you control get +1/+0 until end of turn.", Violent Outburst)
    is exactly `_MASS_PUMP_UNTIL_EOT_RE`'s own shape and genuinely parses,
    even though `_ANTHEM_RE` itself has no duration group to match it -
    checking order here only changes which branch a genuine match is
    attributed to, never `is_resolution_layer_effect_text`'s own `genuine or
    loose` answer, so its behaviour is unchanged.

    One `_parse_static_layer_sentence` shape is deliberately *not* excluded
    by the blanket check below: `_LEGEND_RULE_EXEMPT_THIS_TURN_RE`'s "this
    turn" wording (Hall of Echoes' `{5}` ability) can only ever be CR 611.2's
    one-shot resolution grant - a permanent's own forever CR 611.3 static
    ability (Mirror Box's, Sakashima's plain "... permanents you control.",
    no duration) never carries "this turn" at all, since a static ability
    already applies for as long as its source has it (CR 604.2) and needs no
    turn bound. Excluding it here the same way the durationless shapes are
    excluded left `create_continuous_effect_of_ability`'s own genuine read of
    this exact sentence (`_parse_layer_sentence`'s identical fallback)
    unrecorded as "handled", so the composer logged a `LayerRemainderNotice`
    for a sentence it had already applied.
    """
    normalized = _normalize_duration_first(sentence)
    if _LEGEND_RULE_EXEMPT_THIS_TURN_RE.fullmatch(_strip_ability_word(normalized)):
        return _parse_layer_sentence(sentence) is not None, False
    if _parse_static_layer_sentence(_strip_ability_word(normalized)) is not None:
        # CR 611.3's static shapes: "Nonbasic lands are Mountains", "Lands
        # you control are every basic land type ...", "Other Dragons you
        # control get +1/+1" and their siblings are a *permanent's* own
        # static ability, and the battlefield sweep already reapplies each
        # of them every time the board is computed (CR 613.5). Routing the
        # permanent spell's resolution here as well would create a second,
        # permanent copy of the same effect - doubling an anthem, and
        # leaving a stored effect behind that CR 611.3b says should stop the
        # moment its source leaves the battlefield.
        return False, False
    anthem_opening = _LOOKS_LIKE_ANTHEM_RE.match(normalized)
    self_graveyard_pump_opening = _SELF_PUMP_PER_GRAVEYARD_CARD_RE.match(normalized)
    has_duration = Duration.UNTIL_END_OF_TURN in normalized
    if (anthem_opening or self_graveyard_pump_opening) and not has_duration:
        # CR 611.3's own static shape: "lasts for as long as the object with
        # that static ability remains on the battlefield", i.e. never
        # expires on its own - the two shapes excluded on purpose.
        return False, False
    if _parse_layer_sentence(sentence) is not None:
        return True, False
    if anthem_opening and has_duration:
        # An explicit duration is never CR 611.3's forever-lasting anthem -
        # it can only be CR 611.2's one-shot group pump - but nothing above
        # read this particular sentence into one, so it counts as a failed
        # attempt.
        return False, True
    if _LOOKS_LIKE_RESOLUTION_LAYER_EFFECT_RE.match(normalized):
        return False, True
    return False, False


def is_genuine_resolution_layer_sentence(sentence: str) -> bool:
    """Whether `sentence` alone is genuinely, safely one of `machines.
    layers`'s CR 611.2 one-shot resolution shapes - `_classify_resolution_
    layer_sentence`'s own `genuine` half.

    `machines/effects.py`'s composition wave (`_compose_layer_effect_with_
    remainder` and its three siblings) uses this to decide, sentence by
    sentence, which parts of a multi-sentence resolution `create_continuous_
    effect`/`_of_ability` already covers on its own and which are left over
    to compose - never `is_resolution_layer_effect_text` for that per-
    sentence question, since its looser "or looks like one" half would
    wrongly treat a CR 611.3 static/anthem/self-pump sentence sitting beside
    a genuine one as "already handled", when in fact `create_continuous_
    effect` never applies that excluded sentence at all.
    """
    genuine, _ = _classify_resolution_layer_sentence(sentence)
    return genuine


def genuine_resolution_layer_text(text: str | None) -> bool:
    """Whether some sentence of `text` is genuinely, safely a CR 611.2
    layer shape - `is_resolution_layer_effect_text` narrowed to just its
    `genuine` half, with the "or looks like a failed attempt" signal left
    out.

    `machines/effects.py`'s composition wave uses this as its own entry
    gate: `create_continuous_effect` already answers a loose-only match
    correctly on its own, through `effects_for`'s own `LayerNotice` channel,
    and gating composition on the looser test too would treat Glorious
    Anthem's own durationless "Creatures you control get +1/+1." - or Fiend
    Artisan's own durationless self-pump - as something to compose a
    remainder around, when CR 611.3 excludes both from ever being a
    resolution effect at all (CR 608.3a: a permanent spell has nothing to
    resolve).
    """
    return any(
        is_genuine_resolution_layer_sentence(sentence) for sentence in _effect_sentences(text)
    )


class LayerNotice(EngineModel):
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

    #: The shared exile zone (CR 406.1) - a fourth thing the layer engine
    #: never sees on the battlefield. Keen-Eyed Curator's "As long as there
    #: are four or more card types among cards exiled with this creature"
    #: counts only the cards linked to that one object (CR 607.2a), read
    #: through `cards_exiled_with`.
    exile: tuple[CardState, ...] = ()

    def cards_exiled_with(self, source: CardState) -> tuple[CardState, ...]:
        """The cards exiled with `source` - this incarnation of it (CR 607.2a,
        CR 400.7; `ExileAnnotation.links_to`)."""
        return tuple(
            card
            for card in self.exile
            if card.exile_annotation is not None
            and card.exile_annotation.links_to(source.id, source.zone_change_stamp)
        )

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

    #: The ids of every creature that has dealt combat damage this turn
    #: (`Game.combat_damage_dealt_this_turn_by`) - a per-object "this turn"
    #: fact rather than a per-player one, so it is its own field instead of
    #: living in `turn_facts`. Ruric Thar's "hexproof as long as they haven't
    #: dealt combat damage yet" is the reader.
    combat_damage_dealt_this_turn: frozenset[UUID] = frozenset()

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


#: "Nonbasic lands are Mountains." (Blood Moon) and "Each land is a Swamp in
#: addition to its other land types." (Urborg, Tomb of Yawgmoth) are no longer
#: hand-written here - both are `_parse_static_layer_sentence`'s generalised
#: shapes now, read off whichever card prints them. Harbinger of the Seas
#: ("Nonbasic lands are Islands.") and Yavimaya, Cradle of Growth ("Each land
#: is a Forest ...") are the cards that were silently doing nothing while the
#: shape was keyed by name.


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
            selector=only_this_incarnation(target, target.zone_change_stamp),
            modification=switch_power_toughness,
        )
        for target in targets
    ]


#: "Lands you control are every basic land type in addition to their other
#: types." (Dryad of the Ilysian Grove) is no longer hand-written here either -
#: it is `_lands_are_every_basic_type_builder`'s shape, which is what lets
#: Leyline of the Guildpact, printing the identical sentence, generate it too.
#: The Dryad's other line, "You may play an additional land on each of your
#: turns", is CR 611.3d's rule-modifying grant rather than a continuous effect
#: in any of the seven layers, and lives in `ADDITIONAL_LAND_PLAYS`.


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
            modification=define_power_toughness(FixedCount(value=types), 0, 1),
        )
    ]


def _omnath_locus_of_mana(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "Omnath gets +1/+1 for each unspent green mana you have."

    Sublayer 7c (CR 613.4c: "modify power and/or toughness ... don't set"),
    not the characteristic-defining 7a of Tarmogoyf or Boneyard Wurm - Omnath
    is a printed 1/1 and this *adds* to that, so an empty pool leaves a 1/1
    rather than a 0/0. There is no duration: CR 611.3 gives a static ability's
    own continuous effect exactly the life of the ability.

    The count is read off `context.unspent_mana_of` at build time, and the
    board is rebuilt on every call (CR 613.5), so this tracks the pool live.
    That is the whole of DDR#955: with four green floating during CR 601.2h's
    payment, Omnath really is a 5/5 at the moment it is sacrificed, and it is
    a 1/1 again once that mana is spent.

    "You" is CR 109.5's - the object's controller - which is also whose pool
    `unspent_mana_of` is asked for.
    """
    green = context.unspent_mana_of(source.controller, Color.GREEN)
    if green == 0:
        return []
    return [
        ContinuousEffect(
            description=f"Omnath, Locus of Mana: +{green}/+{green} from unspent green mana",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.MODIFY,
            timestamp=timestamp,
            source_id=source.id,
            selector=_only(source.id),
            modification=modify_power_toughness(green, green),
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
    creatures = sum(1 for card in context.graveyard_of(source.controller) if card.is_creature)
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
            modification=define_power_toughness(FixedCount(value=creatures), 0, 0),
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
            modification=define_power(FixedCount(value=types), 1),
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
            selector=only_this_incarnation(target, target.zone_change_stamp),
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


def _remains_on_the_battlefield(permanent: CardState) -> Condition:
    """ "For as long as this creature remains on the battlefield" (CR 611.2b).

    The zone is asked each time the board is computed, so the effect ends the
    moment the permanent leaves - and CR 400.7 means a permanent that leaves and
    comes back is a new object, so the stamp is what keeps the condition false
    for the returning one rather than reading the id alone and getting it
    wrong the same way a bare `_only` selector would (see `only_this_
    incarnation`'s own docstring for the identical argument).
    """
    return RemainsOnBattlefield(card_id=permanent.id, stamp=permanent.zone_change_stamp)


#: Continuous effects by card name, for the shapes `parsed_layer_effects`
#: cannot read. `effects_for`
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
#:
#: Blood Moon, Urborg, Tomb of Yawgmoth and Dryad of the Ilysian Grove are gone
#: for the same reason and a sharper one: a *name* key is not what CR 604.2 or
#: CR 611.3b says generates a static ability's continuous effect. Every one of
#: those three sentences is printed on some other card too - Harbinger of the
#: Seas, Yavimaya, Cradle of Growth, Leyline of the Guildpact - and each of
#: those cards silently generated nothing, without even a `LayerNotice`,
#: because a board-wide sentence does not open the way the pump and anthem
#: shapes `_LOOKS_LIKE_LAYER_EFFECT_RE` watches for do. Keying by the sentence
#: closes the class rather than the two cards.
LAYER_EFFECTS: dict[str, EffectBuilder] = {
    "Humility": _humility,
    "Opalescence": _opalescence,
    "Twisted Image": _twisted_image,
    "Dress Down": _dress_down,
    # Relentless Rats' own "This creature gets +1/+1 for each other creature
    # on the battlefield named Relentless Rats." is not entered here any
    # more: `_SELF_PUMP_PER_OTHER_CREATURE_NAMED_RE` reads the shape off the
    # card's own printed text with no card-name check at all, so a future
    # card sharing the template with a different name or magnitude - Seven
    # Dwarves among them - is covered for free.
    "Tarmogoyf": _tarmogoyf,
    "Boneyard Wurm": _boneyard_wurm,
    # "Omnath gets +1/+1 for each unspent green mana you have." A live count
    # of something that is not on the battlefield and not in a graveyard
    # either - the controller's own mana pool - so no generalised shape reads
    # it and the row is not dead weight.
    "Omnath, Locus of Mana": _omnath_locus_of_mana,
    "Nighthawk Scavenger": _nighthawk_scavenger,
    "Allosaurus Rider": _allosaurus_rider,
    "Tishana's Tidebinder": _tishanas_tidebinder,
    # "Violent Urge" has no row: its pump and first strike are the
    # generalised shapes, and its *Delirium* rider is read off the template
    # by `machines/effects.py`'s conditional referent rider
    # (`_parse_conditional_referent_clause`).
    # "Monstrous Rage" has no row: its pump is the generalised shape, read off
    # its own oracle text by the parser fallback; its token creation is
    # `machines/effects.py`'s job (CR 111.10k, CR 701.7a).
    # The Monster Role token of CR 111.10k had a row here until "Enchanted
    # creature ..." joined "Equipped creature ..." in
    # `_ATTACHED_CREATURE_STATIC_RE`. The rule states the token's whole text -
    # "enchant creature and 'Enchanted creature gets +1/+1 and has trample.'" -
    # and `machines/tokens.py` synthesises it onto the token's `Card`
    # (CR 111.3), so the parser now reads it off the token exactly as it reads
    # Rancor off a card, through the same `attached_to` link. The row is gone
    # because `test_layer_effects_registry_is_minimal.py` is right that a row
    # the parser can reach is dead weight.
}


def _granted_ability_effects(source: CardState) -> EffectBuilder | None:
    """A builder read off an ability *granted* to this permanent (CR 613.1f).

    `CardState.granted_ability_texts` holds the quoted lines another
    permanent's layer-6 grant is putting on this one, printed exactly as the
    granting card quotes them - Umbral Mantle's "{3}, {Q}: This creature gets
    +2/+2 until end of turn." on an equipped Llanowar Elves. `LAYER_EFFECTS`
    is keyed by card name and the parser fallback reads the source's own
    printing, so neither can reach such a line: "Llanowar Elves" has no row
    and never will, because that pump was never printed on it.

    Only consulted on the resolution path (`static_only=False`), never on the
    battlefield sweep - the line is an *activated* ability, and applying its
    body as though it were this permanent's static contribution (CR 611.3)
    would leave the Elves permanently +2/+2 without anybody paying {3}.
    `layer_readable_sentences`' own `static_only` gate refuses an activated
    ability's body anyway, so this is belt and braces.

    The first granted line that parses wins. A caller that knows *which*
    granted ability is resolving should say so with `effects_for`'s
    `ability_text` instead, which is checked first and is exact; this fallback
    exists because the resolution path currently hands `effects_for` only the
    permanent, and a permanent carrying two different granted quoted layer
    abilities at once would need it.
    """
    legendary = Supertype.LEGENDARY in source.card.supertypes
    for text in source.granted_ability_texts:
        builder = parsed_layer_effects(
            text, static_only=False, card_name=source.name, legendary=legendary
        )
        if builder is not None:
            return builder
    return None


def effects_for(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState] = (),
    context: LayerContext | None = None,
    notices: list[LayerNotice] | None = None,
    *,
    static_only: bool = False,
    ability_text: str | None = None,
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

    This one function serves two different callers with two different
    questions, which is what `static_only` tells apart:

    - `static_effects` (the battlefield sweep, called for every permanent
      every time the board is computed, CR 613.5) asks "does this
      permanent's own *static* ability (CR 611.3) generate a continuous
      effect" - `static_only=True`, since a triggered or activated ability's
      own effect body is never this permanent's static contribution, whether
      or not it happens to parse. Without this, Kraul Harpooner's undergrowth
      pump - "This creature gets +X/+0 ... where X is the number of creature
      cards in your graveyard", fully handled by its own dedicated
      `_parse_undergrowth_pump_and_fight_clause` when the trigger actually
      resolves - used to record a false `LayerNotice` here, because the sweep
      read that triggered ability's own sentence and it looks like (but is
      not) one of this module's generalised pump shapes.
    - `ContinuousEffects.create` (a spell or ability that has just resolved,
      CR 611.2) asks "what does *this resolving ability's own effect* say" -
      `static_only=False` (the default), because the resolving ability may
      well be the `TriggeredAbility`/`ActivatedAbility` whose body this
      builds the effect from (Oliphaunt's attack trigger, Basking Rootwalla's
      activated pump): restricting to `StaticAbility` bodies there would make
      `create_continuous_effect_of_ability` blind to the exact text it exists
      to read.

    `ability_text` is the resolving ability's *own* text, when there is one -
    `machines/effects.create_continuous_effect_of_ability` passes it. Without
    it, both routes into a builder key off the source permanent: its name in
    `LAYER_EFFECTS`, or its own oracle text in the parser. Neither can ever
    reach an ability **granted** to that permanent by something else
    (CR 613.1f: "Layer 6: Ability-adding effects, keyword counters,
    ability-removing effects ... are applied"). Umbral Mantle's quoted "{3},
    {Q}: This creature gets +2/+2 until end of turn." is on Llanowar Elves,
    and "Llanowar Elves" has no `LAYER_EFFECTS` row and never will, because
    the pump was never printed on it - so the ability resolved and did
    nothing.

    It is tried *after* the name row and *before* the source's own text, which
    is the order that changes nothing already working: a card with a row keeps
    it, and a card whose own text carries the ability reaches the same builder
    either way (the ability text is a subset of that text). The only new
    outcome is the granted one.
    """
    legendary = Supertype.LEGENDARY in source.card.supertypes
    builder = LAYER_EFFECTS.get(source.name)
    if builder is None and ability_text:
        builder = parsed_layer_effects(
            ability_text, static_only=static_only, card_name=source.name, legendary=legendary
        )
    if builder is None and not static_only:
        builder = _granted_ability_effects(source)
    # `oracle_text` reads the up face (CR 712.8d/712.8f); `card.oracle_text`
    # is the raw Scryfall field, null for a modal-DFC/transform permanent -
    # same family as `effect_for`'s fix in `Game.resolve_top`. Without this,
    # every layer-computed static/pump/anthem ability on such a permanent's
    # face-up side went unread.
    #
    # `class_ability_text` is `oracle_text` for everything that is not a Class
    # (CR 303.6), and for a Class it drops the paragraphs above its current
    # level - CR 716.2a's own gate. Without that, Innkeeper's Talent's level-2
    # "Permanents you control with counters on them have ward {1}" would be
    # read off a level-1 Class that does not have the ability yet.
    text = source.class_ability_text
    # A keyword's own static ability has no printed sentence for the parser to
    # read, so it is added beside whatever the text produced.
    keyword_statics = _impending_not_a_creature(source, timestamp) if static_only else []
    if builder is None:
        builder = parsed_layer_effects(
            text, static_only=static_only, card_name=source.name, legendary=legendary
        )
    if builder is None:
        if (
            notices is not None
            and looks_like_unparsed_layer_effect(
                text, static_only=static_only, card_name=source.name, legendary=legendary
            )
            # The board is recomputed continually (CR 613.5), so the same
            # unreadable permanent is asked about over and over - record it
            # once, not once per computation.
            and not any(notice.source_id == source.id for notice in notices)
        ):
            notices.append(
                LayerNotice(source_id=source.id, source_name=source.name, text=text or "")
            )
        return keyword_statics
    built = [*builder(source, timestamp, targets, context or LayerContext()), *keyword_statics]
    # `order` is this call's own answer to "which of these came first" - set
    # here, once, on the builder's actual output order, rather than trusting
    # every builder (a `LAYER_EFFECTS` row, the generic parser's per-sentence
    # `combined`, a granted-ability grant) to have stamped it itself. See
    # `ContinuousEffect.order`.
    return [effect.model_copy(update={"order": index}) for index, effect in enumerate(built)]


def _impending_not_a_creature(source: CardState, timestamp: int) -> list[ContinuousEffect]:
    """CR 702.176a's third ability: "As long as this permanent's impending cost
    was paid and it has a time counter on it, it's not a creature."

    A static ability that functions on the battlefield, so a type-changing
    effect in layer 4 (CR 613.1d) with the permanent's own timestamp (CR
    613.7a). The "as long as" needs no stored condition: static effects are
    rebuilt every time the board is computed (CR 613.5), so the moment the
    last time counter comes off - the end step trigger, or anything else that
    removes it - this is simply not built any more. The paid half is
    `CardState.cast_with_keyword`, which belongs to this object only (CR
    400.7), so a blinked Overlord is a creature again.

    The keyword is read off the printing, not off the computed abilities: an
    ability-removing effect is layer 6, and CR 613.6 keeps a layer 4 effect
    that has already started applying from being switched off by it.
    """
    from .abilities import keyword_abilities  # imported here: kept beside its one use

    if source.zone is not Zone.BATTLEFIELD:
        return []
    if (source.cast_with_keyword or "").lower() != "impending":
        return []
    if source.counter_count(Counter.TIME) <= 0:
        return []
    if not any(
        ability.canonical.lower() == "impending" for ability in keyword_abilities(source.card)
    ):
        return []
    return [
        ContinuousEffect(
            description=f"{source.name}: not a creature while it has a time counter (CR 702.176a)",
            layer=Layer.TYPE,
            timestamp=timestamp,
            source_id=source.id,
            selector=_only(source.id),
            modification=RemoveType(card_type=Type.CREATURE),
        )
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
    sync_granted_ability_texts(permanents)
    effects: list[ContinuousEffect] = []
    for timestamp, permanent in enumerate(permanents, start=1):
        effects.extend(effects_for(permanent, timestamp, (), shared, notices, static_only=True))
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

    def has_control_effect(self, game: Game | None = None) -> bool:
        """Whether any stored effect is a layer 2 control change (CR 613.1b).

        Asked by `CardState.controller` before it recomputes the whole board
        to answer a question the board would answer with the base controller
        anyway. Sound because `set_controller` is reachable from exactly one
        builder, `_gain_control_until_eot_builder`, and that builder only ever
        runs from `create` - a resolving spell or ability - so a control
        change is always a *stored* effect and never one the battlefield sweep
        rebuilds. A static ability that changed control (an Aura's "You control
        enchanted creature") would have to be added here as well as there.
        """
        return any(effect.layer is Layer.CONTROL for effect in self.active(game))

    def active(self, game: Game | None = None) -> list[ContinuousEffect]:
        """The stored effects whose duration is still running (CR 611.2b).

        A "for as long as" effect whose condition could turn true again
        (`HasCounter`) is dropped here and now rather than at cleanup
        (`end_the_turn`): CR 611.2b's duration does not begin again, so a
        counter put back must not revive it.
        """
        running = [effect for effect in self.effects if effect.holds(game)]
        if game is not None and len(running) != len(self.effects):
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
            if effect.duration is Duration.UNTIL_END_OF_TURN or not effect.holds(game)
        ]
        gone = {effect.id for effect in ended}
        self.effects = [effect for effect in self.effects if effect.id not in gone]
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
        self.effects = [effect for effect in self.effects if effect.id not in gone]
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
        sync_granted_ability_texts(permanents, _every_card_state_in(game) if game else None)
        # CR 114.4: an emblem's static abilities function in the command zone
        # (Kaito, Bane of Nightmares' "Ninjas you control get +1/+1."), and
        # CR 613.7d stamps it as it entered that zone.
        emblems = _emblems_in(game)
        self.note(emblems)
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
        return effects + self.active(game)

    def board(
        self,
        permanents: Sequence[CardState],
        context: LayerContext | None = None,
        game: Game | None = None,
    ) -> ComputedBoard:
        """What the board is, with everything applied (CR 613.5). Emblems are
        on it too - they have no types, so no permanent-reading question sees
        them - because an effect's source must be on the board for CR 613.6's
        "does its ability still exist" check (`_still_exists`)."""
        effects = self.all_effects(permanents, context, game)
        return compute_board([*permanents, *_emblems_in(game)], effects)
