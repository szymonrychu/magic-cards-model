"""A card as it exists in a game, as opposed to the printing it was cut from."""

import re
from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import (
    ConfigDict,
    Field,
    PrivateAttr,
    RootModel,
    model_serializer,
    model_validator,
)

from ..ids import new_id
from ..snapshot import AnnouncesMutation, EngineModel, announce_mutation, mutation_landed
from .card import (
    Card,
    CardFace,
    Color,
    Layout,
    Supertype,
    Type,
    has_changeling,
    subtypes_of,
    supertypes_of,
    types_of,
    with_every_creature_type,
)
from .zone import Zone

PERMANENT_TYPES = frozenset(
    {Type.ARTIFACT, Type.CREATURE, Type.ENCHANTMENT, Type.LAND, Type.PLANESWALKER, Type.BATTLE}
)


#: The canonical line an effect that says a permanent "can't become untapped"
#: puts on it in layer 6 (Frozen in Ice's static, Spider-Woman's "for as long
#: as" one-shot) - read by `CardState.untap`, which every route to untapping
#: passes through. Not an ability the permanent has: `layers.LoseAllAbilities`
#: leaves it in place (see `RULE_EFFECT_TEXTS` there).
CANT_BECOME_UNTAPPED_TEXT = "Can't become untapped."

#: The canonical line an effect that says a permanent "can't have counters
#: put on it" (Melira's Keepers, Tatterkite, Blossombind's enchanted
#: creature) puts on it in layer 6 - read by `Game.add_counters`, the one
#: place every counter placement passes through (CR 122.6). Not an ability
#: the permanent has, the same way `CANT_BECOME_UNTAPPED_TEXT` is not: see
#: `layers.RULE_EFFECT_TEXTS`, which this joins so a later "loses all
#: abilities" effect does not end it either.
CANT_HAVE_COUNTERS_TEXT = "Can't have counters put on it."


#: The canonical line "Lethal damage dealt to creatures you control is
#: determined by their power rather than their toughness." (Zilortha) puts on
#: each creature it reaches in layer 6 - read by `CardState.lethal_threshold`.
#: An effect on the object, not an ability of it (`layers.RULE_EFFECT_TEXTS`).
#: CR 700.5, CR 604.2: "Your devotion to each color and each combination of
#: colors is increased by one." grants itself this marker; every devotion count
#: adds one per such permanent its controller controls.
DEVOTION_BONUS_TEXT = (
    "Your devotion to each color and each combination of colors is increased by one."
)
LETHAL_BY_POWER_TEXT = "Lethal damage is determined by power rather than toughness."


class TargetKind(StrEnum):
    """The two things a spell can point at (CR 115.1)."""

    CARD = "card"
    PLAYER = "player"


class TargetRef(EngineModel):
    """One target of a spell or ability: an object, or a player (CR 115.1).

    "Only permanents, spells, cards, players, and planeswalkers can be
    targeted." A card target is a `CardState.id`; a player target is a
    username, because a player is not a card and has no card id. Carrying the
    kind alongside the reference is what lets a Lightning Bolt choose between
    a creature and a face without either one pretending to be the other.

    Immutable and serializable, so a spell on the stack round-trips through
    `model_dump`/`model_validate` with its targets intact.
    """

    model_config = ConfigDict(frozen=True)

    kind: TargetKind
    card_id: UUID | None = None
    username: str | None = None
    zone_change_stamp: UUID | None = None
    """Which incarnation of `card_id` this reference names (CR 400.7),
    captured from the live `CardState.zone_change_stamp` at the moment this
    target was chosen (CR 601.2c/603.3d) - `None` when no live object was on
    hand to read one from (a bare id or username coerced with nothing else
    to go on, e.g. `magic_cards_model_api.decisions.targets_answer`'s
    client-supplied token), in which case `Game.legal_target` cannot judge
    the zone-change half of CR 608.2b and does not try to.

    Deliberately **not** part of this reference's identity: `__eq__`/
    `__hash__` below compare only `(kind, card_id, username)`, the triple
    that already made two `TargetRef`s naming the same thing equal before
    this field existed. `Game._validate_answer`'s CHOOSE_TARGETS branch and
    `machines/legal_actions.py` both compare a caller's answer against
    `decision.targets` by equality to accept it; if the stamp counted too, a
    caller supplying an unstamped reference for a target the engine already
    stamped (exactly `targets_answer`'s shape) would be refused as illegal
    even though it names the same object - the fix would make itself a
    no-op over the very API surface the bug was reported from. That branch
    also swaps the caller's reference for its canonical stamped counterpart
    from `decision.targets`, which is what actually closes that gap.
    """

    slot: int | None = None
    """Which of the spell's or ability's target requirements this target
    filled when it was announced (CR 601.2c) - an index into
    `TargetingProfile.requirements`, `None` when the announcement recorded
    none. A spell whose requirements name different roles (Allies at Last's
    "up to two target creatures you control" and its victim) reads it back at
    resolution, because the list order says only the order the caster named
    them in. Like `zone_change_stamp`, not part of this reference's identity."""

    @classmethod
    def to_card(cls, card: "CardState | UUID") -> "TargetRef":
        """Target an object by its `CardState`, or directly by its id.

        A live `CardState` hands over its current `zone_change_stamp` too
        (CR 400.7) - captured right here, at the moment something reaches
        for this object to name it as a target, which is CR 601.2c's
        announcement moment for every caller that already has the object in
        hand (every internal call site does; see the field's own docstring
        for the one that does not).
        """
        card_id = card if isinstance(card, UUID) else card.id
        stamp = None if isinstance(card, UUID) else card.zone_change_stamp
        return cls(kind=TargetKind.CARD, card_id=card_id, zone_change_stamp=stamp)

    @classmethod
    def to_player(cls, player: Any) -> "TargetRef":
        """Target a player, by username or by anything carrying one."""
        username = player if isinstance(player, str) else player.username
        return cls(kind=TargetKind.PLAYER, username=username)

    @classmethod
    def coerce(cls, value: Any) -> "TargetRef":
        """Read a target out of whatever a caller had to hand.

        A `TargetRef` passes through. A `UUID` or anything with an `id` is a
        card; a `str` or anything with a `username` is a player. This is what
        keeps `choose_targets([bears])` and `choose_targets(["bob"])` both
        meaning the obvious thing.
        """
        if isinstance(value, TargetRef):
            return value
        if isinstance(value, dict):
            return cls.model_validate(value)
        if isinstance(value, UUID | CardState):
            return cls.to_card(value)
        if isinstance(value, str) or hasattr(value, "username"):
            return cls.to_player(value)
        if hasattr(value, "id"):
            return cls.to_card(value.id)
        raise TypeError(f"cannot read a target out of {value!r}")

    @model_validator(mode="before")
    @classmethod
    def _accept_shorthand(cls, value: Any) -> Any:
        """Accept a bare id or username where a full reference is expected."""
        if isinstance(value, UUID):
            return {"kind": TargetKind.CARD, "card_id": value}
        if isinstance(value, str):
            return {"kind": TargetKind.PLAYER, "username": value}
        return value

    @model_validator(mode="after")
    def _exactly_one_reference(self) -> Self:
        if self.kind is TargetKind.CARD and (self.card_id is None or self.username is not None):
            raise ValueError("a card target needs a card_id and no username")
        if self.kind is TargetKind.PLAYER and (self.username is None or self.card_id is not None):
            raise ValueError("a player target needs a username and no card_id")
        return self

    @property
    def is_card(self) -> bool:
        return self.kind is TargetKind.CARD

    @property
    def is_player(self) -> bool:
        return self.kind is TargetKind.PLAYER

    def __str__(self) -> str:
        return str(self.username) if self.is_player else str(self.card_id)

    def __eq__(self, other: object) -> bool:
        """Identity is `(kind, card_id, username)` only - see
        `zone_change_stamp`'s own docstring for why the stamp is deliberately
        excluded here rather than compared like every other field.
        """
        if not isinstance(other, TargetRef):
            return NotImplemented
        return (self.kind, self.card_id, self.username) == (
            other.kind,
            other.card_id,
            other.username,
        )

    def __hash__(self) -> int:
        return hash((self.kind, self.card_id, self.username))


class Counter(StrEnum):
    """The counter kinds this engine names. The set itself is open (CR 122.1).

    "A counter is a marker placed on an object or player that modifies its
    characteristics and/or interacts with a rule, ability, or effect. Counters
    are not objects and have no characteristics." Any name at all is a legal
    counter kind - charge, page, rust, whatever a card invents - so counters are
    stored under plain string keys and this enum only spells out the kinds the
    rules themselves care about:

    - `+1/+1` and `-1/-1` change power and toughness (CR 122.1a) in layer 7c
      (CR 613.4c), and annihilate each other as a state-based action
      (CR 122.3, CR 704.5q).
    - `loyalty` is what a planeswalker's loyalty *is* (CR 122.1e, CR 306.5c).
    - `lore` is what a Saga's progress *is* (CR 714.3): each one placed checks
      every chapter ability's own threshold (CR 107.15a) for a fresh trigger,
      and CR 714.4/704.5s sacrifice the Saga once its count reaches its final
      chapter number.
    - `poison` is on a player, and ten of them lose the game (CR 122.1f,
      CR 704.5c).
    - `energy` is on a player and is what `{E}` pays with (CR 107.14).
    - `experience` is on a player.
    - `stun` stops the permanent untapping (CR 122.1d): "One or more stun
      counters on a permanent create a single replacement effect that stops
      the permanent from untapping. That effect is 'If a permanent with a
      stun counter on it would become untapped, instead remove a stun counter
      from it.'" `untap` is where that replacement lives, since every route
      to untapping passes through it.
    - `finality` stops the permanent reaching a graveyard (CR 122.1h): "If
      this permanent would be put into a graveyard from the battlefield, exile
      it instead." `machines/replacement.py`'s `_finality_counter_effects` is
      that replacement effect.
    - `charge` is the common named counter with no rules of its own.
    - `time` sits on a card in exile with suspend (CR 702.62a, 702.62b) or a
      permanent with vanishing/fading (CR 702.63a, 702.32a); "at the beginning
      of your upkeep, remove a time counter" and "when the last is removed"
      are read directly off the count, the same way `power`/`toughness` read
      `+1/+1`/`-1/-1` without a separate model of "how many are left".

    A keyword counter (CR 122.1b) is stored under the keyword's own name, so a
    flying counter is `counters["flying"]`. Nothing grants the keyword yet - it
    would apply in layer 6 (CR 613.1f).
    """

    PLUS_ONE = "+1/+1"
    MINUS_ONE = "-1/-1"
    LOYALTY = "loyalty"
    LORE = "lore"
    POISON = "poison"
    ENERGY = "energy"
    EXPERIENCE = "experience"
    STUN = "stun"
    FINALITY = "finality"
    TIME = "time"
    CHARGE = "charge"
    #: CR 702.24a: cumulative upkeep puts one on each upkeep and counts them.
    AGE = "age"
    #: CR 310.4c: a battle's defense on the battlefield is the number of these.
    DEFENSE = "defense"


#: A counter kind: one of the named ones, or any string a card invents.
CounterKind = Counter | str


def _counter_key(kind: CounterKind) -> str:
    """Counter kinds are compared by name, so an enum and its text are one key."""
    return str(kind)


def counters_removed_fact(kind: CounterKind) -> str:
    """`Game.turn_counts` key: counters of `kind` removed this turn from
    permanents a player controlled (`CardState.remove_counters`)."""
    return f"counters_removed:{_counter_key(kind).lower()}"


def graveyard_with_counter_fact(kind: CounterKind) -> str:
    """`Game.turn_counts` key: permanents a player owned put into a graveyard
    from the battlefield this turn with a counter of `kind` on them."""
    return f"put_into_graveyard_with_counter:{_counter_key(kind).lower()}"


#: CR 702.87a's counter: "Put a level counter on this permanent." The kind
#: a leveler's level symbols count (CR 711.2a/b). CR 702.87c: a Class's level
#: is not one.
LEVEL_COUNTER = "level"


class Counters(AnnouncesMutation, RootModel[dict[str, int]]):
    """The counters on one object or player, by kind (CR 122.1).

    A count per kind rather than a list of markers: counters have no
    characteristics and no identity of their own, so "three +1/+1 counters" is
    the whole truth about them. A kind at zero is dropped, so `"+1/+1" in
    counters` answers "does it have any".

    A root model, so it serialises as the plain `{kind: count}` object it is and
    validates back from one - a board round-trips through
    `model_dump`/`model_validate` with its counters intact, and a scenario can
    write `counters={"+1/+1": 2}` wherever one is expected.
    """

    root: dict[str, int] = Field(default_factory=dict)

    @property
    def counts(self) -> dict[str, int]:
        """The kinds and their counts, as stored."""
        return self.root

    @model_validator(mode="before")
    @classmethod
    def _normalise_kinds(cls, value: Any) -> Any:
        """A `Counter` and its own text are the same kind, so key by the text."""
        if isinstance(value, dict):
            return {_counter_key(kind): count for kind, count in value.items()}
        return value

    def __getitem__(self, kind: CounterKind) -> int:
        return self.counts.get(_counter_key(kind), 0)

    def __contains__(self, kind: object) -> bool:
        return self.counts.get(_counter_key(kind), 0) > 0  # type: ignore[arg-type]

    def __iter__(self) -> Any:
        return iter(self.counts)

    def __len__(self) -> int:
        return len(self.counts)

    def __bool__(self) -> bool:
        return bool(self.counts)

    def __eq__(self, other: object) -> bool:
        """Equal to another `Counters`, or to the plain mapping it stands for."""
        if isinstance(other, Counters):
            return self.counts == other.counts
        if isinstance(other, dict):
            return self.counts == {_counter_key(k): v for k, v in other.items()}
        return NotImplemented

    def __hash__(self) -> int:
        return hash(tuple(sorted(self.counts.items())))

    def __repr__(self) -> str:
        return f"Counters({self.counts!r})"

    __str__ = __repr__

    def items(self) -> Any:
        return self.counts.items()

    def as_dict(self) -> dict[str, int]:
        """A plain copy, for anything that wants a mapping it can keep."""
        return dict(self.counts)

    def add(self, kind: CounterKind, amount: int = 1) -> int:
        """Put counters on, returning the new count. Zero is a no-op."""
        if amount < 0:
            raise ValueError("cannot put a negative number of counters on")
        if amount:
            key = _counter_key(kind)
            announce_mutation(self)
            self.counts[key] = self.counts.get(key, 0) + amount
            mutation_landed(self, structural=False)
        return self[kind]

    def remove(self, kind: CounterKind, amount: int = 1) -> int:
        """Take counters off, returning the new count.

        Refuses to remove more than are there: CR 118.3 says a player cannot pay
        a cost without the resources to pay it fully, and every way of removing
        counters in the rules is either a cost or an effect that removes what is
        there.
        """
        if amount < 0:
            raise ValueError("cannot remove a negative number of counters")
        key = _counter_key(kind)
        present = self.counts.get(key, 0)
        if amount > present:
            raise ValueError(f"cannot remove {amount} {key} counters from {present}")
        remaining = present - amount
        announce_mutation(self)
        if remaining:
            self.counts[key] = remaining
        else:
            self.counts.pop(key, None)
        mutation_landed(self, structural=False)
        return remaining

    def set(self, kind: CounterKind, amount: int) -> int:
        """Put the count of one kind at exactly `amount`."""
        if amount < 0:
            raise ValueError("a permanent cannot have a negative number of counters")
        key = _counter_key(kind)
        announce_mutation(self)
        if amount:
            self.counts[key] = amount
        else:
            self.counts.pop(key, None)
        mutation_landed(self, structural=False)
        return amount

    def clear(self) -> None:
        self.root = {}

    def annihilate(self) -> int:
        """CR 704.5q, the state-based action CR 122.3 also states.

        "If a permanent has both a +1/+1 counter and a -1/-1 counter on it, N
        +1/+1 and N -1/-1 counters are removed from it, where N is the smaller
        of the number of +1/+1 and -1/-1 counters on it." Returns N.
        """
        pairs = min(self[Counter.PLUS_ONE], self[Counter.MINUS_ONE])
        if pairs:
            self.remove(Counter.PLUS_ONE, pairs)
            self.remove(Counter.MINUS_ONE, pairs)
        return pairs

    @property
    def power_toughness_modifier(self) -> int:
        """What +1/+1 and -1/-1 counters add to power and toughness (CR 122.1a)."""
        return self[Counter.PLUS_ONE] - self[Counter.MINUS_ONE]


class ExileMarker(StrEnum):
    """Why a card is in exile, when that changes what may be done with it.

    CR 406.4: "Face-down cards in exile should be kept in separate piles based
    on when they were exiled and how they were exiled." The rules track *how* a
    card got to exile because several keywords hand out permission to cast it
    from there afterwards, and each names its own pile:

    - `PLOTTED` - CR 702.170c, a card that became plotted. CR 702.170d lets its
      owner cast it from exile without paying its mana cost, on a later turn.
    - `FORETOLD` - CR 702.143c, "a card put into exile as the result of its
      foretell ability". CR 702.143a exiles it face down.
    - `WARPED` - CR 702.185b, "a warped card in exile is one that was exiled by
      the delayed triggered ability created by a warp ability".
    - `ADVENTURED` - CR 715.3d, the card an Adventure spell became on
      resolution. Not a keyword marker in the rules - the rule simply says its
      controller "may play it" for as long as it remains exiled - but it is the
      same pile-of-its-own shape, so it is tracked the same way.
    - `SUSPENDED` - CR 702.62b, "a card ... is 'suspended' if it's in the
      exile zone, has suspend, and has a time counter on it." The pile a card
      lands in when CR 116.2f's special action exiles it; CR 702.62a's third
      ability reads this marker (alongside a zero `Counter.TIME` count) to
      know the free cast it grants is about this exact card and not merely
      anything that ever had suspend.
    """

    PLOTTED = "plotted"
    FORETOLD = "foretold"
    WARPED = "warped"
    ADVENTURED = "adventured"
    HIDEAWAY = "hideaway"
    """CR 702.75a: the one card a hideaway permanent exiled face down when it
    entered. Its `linked_permanent_id` is that permanent, so a later ability
    printed on the same object (Fight Rigging's own beginning-of-combat
    trigger) can find its card back without a name-keyed table - the same
    link `ExileMarker.IMPRINTED` already uses for the same reason."""
    SUSPENDED = "suspended"
    CASCADE = "cascade"
    """CR 702.85a: the hit cascade found, once its controller has said "yes"
    to casting it without paying its mana cost. `Game.grant_play_permission`
    hands out the actual permission (`machines/keywords.cascade`); this marker
    is what a caller reads back to confirm which pile a card in exile is in,
    the same "which pile" question every other exile marker here answers."""
    MADNESS = "madness"
    """CR 702.35a's first ability: "If a player would discard this card, that
    player discards it, but exiles it instead of putting it into their
    graveyard." The card sits in its own pile of exile until the triggered
    ability that follows is resolved, and CR 702.35b casts it from there."""
    AIRBENT = "airbent"
    """CR 701.65a: "Certain spells and abilities instruct a player to airbend
    one or more permanents and/or spells. To do so, that player exiles those
    objects. For each card exiled this way, for as long as it remains exiled,
    its owner may cast it for {2} rather than its mana cost."

    A CR 701 keyword *action*, not a CR 702 keyword ability, so - like
    `ADVENTURED` - nothing is printed on the exiled card to read the permission
    off; the pile it lands in is the whole record. `ExileAnnotation.owner` is
    load-bearing here in a way it is not for most of the markers above: the
    permission is the **owner's**, and the player who airbent the object is
    usually somebody else."""
    HAUNTING = "haunting"
    """CR 702.55b: "Cards that are in the exile zone as the result of a haunt ability
    'haunt' the creature targeted by that ability." `ExileAnnotation.linked_permanent_id`
    is that creature, which the card's own "When the creature this card haunts dies"
    trigger (CR 702.55c, it triggers from exile) reads back."""
    LINKED = "linked"
    """CR 607.2a / CR 406.6: a card exiled by an ability of an object that also
    has an ability referring to "the exiled card(s)" - Skyclave Apparition's
    enters-the-battlefield exile, read back by its leaves-the-battlefield
    token. "The second ability refers only to cards in the exile zone that were
    put there as a result of an instruction to exile them in the first
    ability", so the card carries `linked_permanent_id` the way an imprinted
    card does, and `Game.cards_imprinted_on` finds it the same way."""
    IMPRINTED = "imprinted"
    """"Imprint" is an ability word (CR 207.2c): it "has no special rules
    meaning" of its own, so the rule is whatever the card's own sentence says -
    Ugin's Labyrinth's "you may exile a colorless card with mana value 7 or
    greater from your hand". What every printing sharing the word has in
    common is the shape this marker exists for: the exiled card is not just in
    exile, it is *exiled with* a specific permanent, and a later ability reads
    that back ("If a card is exiled with this land, add {C}{C} instead.").
    `ExileAnnotation.linked_permanent_id` is that link; see its own docstring
    for what "with this permanent" means once the permanent itself is gone."""


#: The markers that mean "exiled *with* a specific permanent" (CR 607.2a) -
#: the set `Game.cards_imprinted_on` has always read, shared with
#: `ExileAnnotation.links_to`.
_LINKED_EXILE_MARKERS = frozenset({ExileMarker.IMPRINTED, ExileMarker.HIDEAWAY, ExileMarker.LINKED})


class ChoiceKind(StrEnum):
    """What kind of thing an "as [this] enters, choose ..." effect names.

    CR 614.1c: "Effects that read '... As [this permanent] enters ...' are
    replacement effects", and CR 614.12a: "If a replacement effect that
    modifies how a permanent enters the battlefield requires a choice, that
    choice is made before the permanent enters the battlefield." The pool has
    three shapes of that choice - Utopia Sprawl/Voice of All/Forsaken
    Crossroads choose a color, Runed Halo/Pithing Needle/Disruptor Flute
    choose a card name, Cavern of Souls chooses a creature type - so a single
    color-only field on `CardState` would silently miss two of the three.
    `Choice` below is generic over which kind was asked for.
    """

    COLOR = "color"
    CARD_NAME = "card_name"
    CREATURE_TYPE = "creature_type"
    ODD_OR_EVEN = "odd_or_even"
    #: "choose two colors" (Tablet of the Guilds): `Choice.value` is every
    #: chosen color's letter code, in the order chosen ("WU").
    COLORS = "colors"
    """Gollum, Riddle Master's own "As Gollum enters, choose odd or even.
    (Zero is even.)" - a fourth "as [this] enters, choose ..." shape,
    `Choice.value` "odd" or "even". The parenthetical is the card's own
    reminder text, not a separate numbered rule."""
    #: "As this enters, choose Khans or Dragons" (the Siege cycle) and the other
    #: printed either/or lists: `Choice.value` is the chosen word as printed.
    MODE = "mode"
    #: "choose a card type [other than creature]" (Serra's Emissary, Umori,
    #: Stenn, Arachne, Cloud Key): `Choice.value` one of CR 300.1's types.
    CARD_TYPE = "card_type"
    #: "choose a number [between 1 and 10]" (Sanctum Prelate, Talion):
    #: `Choice.value` the decimal digits.
    NUMBER = "number"
    #: "choose a planeswalker type" (Deification), `Choice.value` the type.
    PLANESWALKER_TYPE = "planeswalker_type"
    #: "choose a color word" (Swirl the Mists), `Choice.value` the color's name.
    COLOR_WORD = "color_word"
    #: "choose a creature" / "choose another creature you control" / "you may
    #: choose a nonland permanent" (Metamorphic Alteration, Dauntless Bodyguard,
    #: Scheming Fence): `Choice.value` the chosen permanent's id.
    OBJECT = "object"
    #: "it becomes your choice of a 3/3 creature with flying, a 2/5 ..." (Corrupted
    #: Shapeshifter, Primal Plasma, Aquamorph Entity): `Choice.value` the chosen
    #: option as printed, without its article ("3/3 creature with flying").
    BODY = "body"
    #: "As this enters, flip a coin" (Molten Sentry): `Choice.value` "heads" or
    #: "tails" (CR 705.1: a win is heads by this engine's convention).
    COIN = "coin"
    #: "you may choose another creature on the battlefield. If you do, ... it
    #: becomes a copy of that creature" (Vesuvan Shapeshifter): `Choice.value`
    #: the chosen creature's copiable values (CR 707.2), frozen as a
    #: `Characteristics` JSON snapshot taken as the choice was made (CR 707.2b).
    COPY_OF = "copy_of"
    BASIC_LAND_TYPE = "basic_land_type"
    """Multiversal Passage's own "As this land enters, choose a basic land
    type." - CR 305.6's five (`Choice.value` one of "Plains"/"Island"/
    "Swamp"/"Mountain"/"Forest"), read back by "This land is the chosen
    type." (`machines/layers.py`'s own CR 305.7 type-setting reader)."""


class Choice(EngineModel):
    """One "as [this] enters, choose ..." answer, recorded on the object that
    asked (CR 614.12a).

    `value` is the chosen color's letter code (`Color.value`, e.g. `"G"`) for
    `ChoiceKind.COLOR`, or the plain named string for the other two kinds - a
    card name or a creature type. Read back later by whatever clause says "the
    chosen color"/"the chosen card name"/"the chosen creature type".
    """

    kind: ChoiceKind
    value: str


class DevouredObject(EngineModel):
    """One permanent a devour ability sacrificed (CR 702.82b), as it last
    existed on the battlefield: its card types and subtypes, which is all
    "the number of Goblins it devoured" / "for each creature it devoured"
    ever asks of it."""

    types: tuple[Type, ...] = ()
    subtypes: tuple[str, ...] = ()


class FaceDownCharacteristics(EngineModel):
    """What a face-down object *is*, in place of what its card says (CR 708.2).

    "Face-down spells and face-down permanents have no characteristics other
    than those listed by the ability or rules that allowed the spell or permanent
    to be face down. **Any listed characteristics are the copiable values of that
    object's characteristics.**"

    So this is not a modifier: it replaces the printing wholesale for as long as
    the object is face down. CR 702.37c lists morph's set - "a 2/2 face-down
    creature card with no text, no name, no subtypes, and no mana cost" - and
    CR 702.168b lists disguise's, which is the same set plus ward {2}. CR 708.2a
    is the default for anything turned face down without a list.

    It lives on `CardState` rather than on `Card` because `Card` is the immutable
    Scryfall printing: the same printing is a 3/5 Brine Elemental in one game and
    a nameless 2/2 in another, and only the object in the game can say which.

    Being *copiable* values, the rules' home for this is layer 1 (CR 613.2), so
    `machines/layers.printed_characteristics` is where the layer engine should
    read it - see `docs/engine-coverage.md`.
    """

    model_config = ConfigDict(frozen=True)

    name: str = ""
    power: int = 2
    toughness: int = 2
    types: tuple[Type, ...] = (Type.CREATURE,)
    subtypes: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    """Ward {2} for disguise (CR 702.168b), nothing for morph (CR 702.37c)."""
    oracle_text: str = ""
    mana_cost: str | None = None
    rule: str = "CR 708.2a"
    """The rule that listed these characteristics, for an error message."""


class ExileAnnotation(EngineModel):
    """The note that travels with a card into exile (CR 406.4).

    Exile is a public zone (CR 400.2) holding cards that are otherwise
    identical, so "which of these may I cast" cannot be answered by looking at
    the cards. This is that answer: which pile the card is in, whose it is, and
    which turn it landed there, because every keyword that casts from exile is
    gated on "a later turn" than the one it was exiled on.
    """

    model_config = ConfigDict(frozen=True)

    marker: ExileMarker
    owner: str | None = None
    """Who may cast it. CR 702.170d says a plotted card's *owner*."""
    turn_exiled: int | None = None
    """The turn number it was exiled on, or None if nothing was counting."""
    linked_permanent_id: UUID | None = None
    """`ExileMarker.IMPRINTED` only: the id of the permanent this card was
    exiled *with*, so a later ability printed on that permanent - Ugin's
    Labyrinth's own mana ability, its own return-to-hand ability - can find
    its card again without a name-keyed table.

    Nothing clears this if the linked permanent later leaves the battlefield.
    CR 406.1: exile is "a holding area" that some effects exile into "without
    any way to return" a card from - there is no rule that unlinks the two, so
    the exiled card is simply "exiled with" an id nothing on the battlefield
    answers to any more, and every reader of this field (`Game.
    card_imprinted_on`) is a lookup by id that then finds nothing rather than
    a dangling reference to chase. The id is not reused: `CardState.move_to`
    only clears an object's *own* `exile_annotation`, never another object's
    pointer at it, and a card that changes zones keeps the same `id` in this
    engine (see `move_to`'s own docstring) - so the one way this could go
    stale is the same land leaving and returning to the battlefield while its
    old exiled card is still sitting there unclaimed, which is the same
    "same id, new object" approximation the rest of this model already makes."""
    linked_permanent_stamp: UUID | None = None
    """The linked permanent's `CardState.zone_change_stamp` at the time it
    exiled this card - which *object* `linked_permanent_id` names (CR 400.7).

    CR 607.2a's reader "refers only to cards in the exile zone that were put
    there as a result of an instruction to exile them in the first ability",
    and the first ability belonged to one object: a permanent that left the
    battlefield and came back is "a new object with no memory of, or relation
    to, its previous existence" (CR 400.7), so its own linked ability finds
    none of the cards its earlier self exiled. `None` for a link written
    without an object to read one from; `links_to` then matches on the id
    alone, the approximation the docstring above describes."""

    def links_to(self, permanent_id: UUID, stamp: UUID | None) -> bool:
        """Whether this is a CR 607.2a "exiled with" link to the object
        `permanent_id`/`stamp` names. A `None` on either side cannot tell two
        incarnations apart, so it matches on the id alone."""
        if self.marker not in _LINKED_EXILE_MARKERS or self.linked_permanent_id != permanent_id:
            return False
        return (
            self.linked_permanent_stamp is None
            or stamp is None
            or self.linked_permanent_stamp == stamp
        )


class SpellSnapshot(EngineModel):
    """A spell as it last existed on the stack (CR 608.2h's last known
    information): the stamp its stack incarnation carried, which keys its
    `Game.cast_records` entry, and the targets and division it had as it
    left. A "copy that spell" trigger that resolves after the spell was
    countered still copies it (CR 707.10) from this."""

    model_config = ConfigDict(frozen=True)

    stamp: UUID
    targets: tuple[TargetRef, ...] = ()
    division: tuple[int, ...] | None = None
    cast_record: dict[str, Any] | None = None
    """The spell's `Game.cast_records` entry, dumped as JSON by
    `Game.forget_cast_record` before it drops the live one: the modes, X,
    face and cost decisions CR 707.10 copies. A plain dict because
    `CastRecord` lives in `models/game.py`, which builds on this module."""


class AttachmentSnapshot(EngineModel):
    """One Aura or Equipment attached to a permanent as that permanent left
    the battlefield (CR 603.10a, CR 608.2h) - who controlled it and what it
    was, read off the computed board while it still applied (CR 613.5)."""

    model_config = ConfigDict(frozen=True)

    card_id: UUID
    controller: str | None = None
    types: tuple[Type, ...] = ()
    subtypes: tuple[str, ...] = ()


_LOCKED_ROOM_FACES: dict[UUID, CardFace] = {}


def locked_room_face(card: Card) -> CardFace:
    """A Room permanent with neither unlocked designation (CR 709.5c-d), as
    one face: CR 709.5's two statics strip "the name, mana cost, or rules
    text" of both halves, leaving only the shared type line (CR 709.5a) -
    no name (CR 201.2a: it shares a name with nothing), no mana cost (so no
    color, CR 202.2b), no rules text and so no abilities. Memoised per
    printing; `Card` is immutable."""
    cached = _LOCKED_ROOM_FACES.get(card.id)
    if cached is None:
        front = card.front_face
        cached = CardFace(
            name="",
            mana_cost="",
            type_line=front.type_line if front is not None else card.type_line,
            oracle_text="",
            colors=[],
        )
        _LOCKED_ROOM_FACES[card.id] = cached
    return cached


class CardState(EngineModel):
    """One physical card in a game: which printing it is, where it is, how it sits.

    `Card` stays the immutable Scryfall printing. Four copies of the same card in
    a deck are four `CardState`s sharing one `Card`, each with its own `id`.
    """

    #: `populate_by_name` so `stored_controller` answers to both its own name
    #: and to `controller`, which is the alias every caller writes and every
    #: `model_dump`/`model_validate` round trip carries.
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=new_id)
    card: Card
    zone: Zone = Zone.LIBRARY
    stored_controller: str | None = Field(default=None, alias="controller")
    """Who controls this object before any continuous effect is applied.

    Read through the `controller` property, never directly - CR 613.1b puts
    control-changing effects in layer 2, so the answer to "who controls this
    permanent" is a computed one (CR 613.5) and this is only its base. Written
    directly by exactly the two places that hand a permanent to a player
    outside the layer system: `Game.put_onto_battlefield` and
    `Game.change_control`, both of which are stating the base rather than
    applying an effect.
    """

    owner: str | None = None
    """Who owns this card (CR 108.3).

    "The owner of a card in the game is the player who started the game with it
    in their deck." Separate from `controller` because CR 109.4 says "only
    objects on the stack or on the battlefield have a controller. Objects that
    are neither on the stack nor on the battlefield aren't controlled by any
    player", and CR 108.4 says the same from the card's side: "A card doesn't
    have a controller unless that card represents a permanent or spell."

    So a card in a graveyard has an owner and no controller, and CR 108.4a is
    what anything asking the wrong question should fall back to: "If anything
    asks for the controller of a card that doesn't have one (because it's not a
    permanent or spell), use its owner instead." That fallback is
    `controller_or_owner`.
    """
    token: bool = False
    """Whether this permanent is a token (CR 111.1).

    "A token is a marker used to represent any permanent that isn't represented
    by a card." A `CardState` is built around a `Card`, so this flag is the only
    thing that can say so, and CR 108.2b is why it matters: "Tokens aren't
    considered cards." `machines/targeting.py` reads it to enforce "target token
    you control".

    A minimal hook, not a token system: a token's characteristics come from the
    effect that created it (CR 111.3), and nothing here provides them.

    **Not** which Python class built this object - see `state_class` just
    below for that genuinely different question. `Game.copy_spell` builds a
    `TokenState` with `token=False` (a copy of a permanent spell on the stack
    is not yet a token, CR 707.10f), so this flag being false says nothing
    about whether the object needs `TokenState`'s own CR 111.8 override on
    decode.
    """
    state_class: Literal["CardState"] = "CardState"
    """Which concrete Python class built this object - decode-time identity,
    not a rules concept, and never to be confused with `token` above.

    `TokenState` is `CardState`'s only subclass, and every field typed
    `CardState` (`Player.zones`, `Game`'s stack) erases that at decode time
    unless something in the data says otherwise (`_resolve_token_subclass`'s
    own docstring has the full story). The obvious signal to read back was
    `token`, and that was the defect: `Game.copy_spell` builds a `TokenState`
    for a copy of a permanent spell while it sits on the stack, with
    `token=False` on purpose (CR 707.10f - it becomes a token only as it
    resolves, CR 111.13), so a game dumped mid-priority with that copy on the
    stack decoded it back as a plain `CardState`, silently losing CR 111.8's
    protection the moment it later did become a token. `state_class` is a
    plain field with no meaning beyond "which class am I" - `TokenState`
    overrides its default to `"TokenState"` - so it says the same thing
    whether or not the object also happens to be a token, and
    `_resolve_token_subclass` reads this instead of `token` to choose which
    class rebuilds a decoded dict.
    """
    epic_suppressed: bool = False
    """CR 702.50a: this spell is the copy an epic delayed trigger made "except
    for its epic ability", so resolving it neither stops its controller casting
    spells nor creates another delayed trigger. A copy of such a copy keeps it
    (CR 707.2: copiable values include copy-effect exceptions)."""

    is_copy: bool = False
    """CR 112.1a: "A copy of a spell is also a spell, even if it has no card
    associated with it." Built around the same `Card` its original was (this
    project's copy machinery, `Game.copy_spell`, does not yet extend to a
    copy whose copiable values were themselves modified, CR 707.3), but not
    cast (CR 707.10: "a copy of a spell isn't cast"), so nothing should ever
    treat one as coming from a player's hand or library. CR 704.5e/707.10a:
    "If a copy of a spell is in a zone other than the stack, it ceases to
    exist" - the one other place this flag is read, by the state-based
    action of the same name.
    """
    tapped: bool = False
    face_up: bool = True
    transformed: bool = False
    """True while this double-faced permanent has its back face up (CR 701.27g).

    CR 701.27a: "To transform a permanent, turn it over so that its other face is
    up." CR 712.18 adds that it does not become a new object, so this is a flag
    on the same `CardState` rather than a swap for a different one.

    It feeds characteristics: `up_face` returns `Card.back_face` while this is
    set, so CR 712.8e's "while a nonmodal double-faced permanent has its back
    face up, it has only the characteristics of its back face" is what `name`,
    `types`, `subtypes`, `supertypes`, `colors`, `oracle_text`, `keywords`,
    `mana_cost`, `power`, `toughness` and `loyalty` all report - a transformed
    Delver of Secrets is a 3/2 flying Human Insect. Mana value is the one
    characteristic that does *not* move (CR 202.3b, CR 712.8e: "its mana value
    is calculated using the mana cost of its front face"), which `mana_value`
    below is careful about.

    Only ever true on the battlefield: CR 712.8a gives a double-faced card in
    every other zone its front face's characteristics only, and `move_to`
    clears the flag on the way out.
    """
    flipped: bool = False
    """True once this flip-card permanent has flipped (CR 710).

    CR 710.1b: the bottom half's "alternative name, text box, type line,
    power, and toughness" are "used only if the permanent is on the
    battlefield and only if the permanent is flipped", so `up_face` reads
    `Card.back_face` while this is set. CR 710.1c keeps colour and mana cost
    unchanged, which `mana_cost` honours (the bottom half prints none).
    CR 710.4: one-way - `flip` never clears it - and a flipped permanent that
    leaves the battlefield "retains no memory of its status", which is why
    `move_to` clears it on the way out.
    """
    times_transformed: int = 0
    """How many times `transform` has actually turned this object over - the
    count CR 701.27f compares: "If a delayed triggered ability of a permanent
    tries to transform that permanent, the permanent does so only if it
    hasn't transformed or converted since that delayed triggered ability was
    created." A delayed trigger records this number as it is created
    (`machines/delayed.TransformSubject`) and transforms only while it is
    unchanged, so two "transform this at the beginning of the next upkeep"
    triggers from one board wipe turn the permanent over once, not back.
    Only ever incremented; a zone change is caught by the delayed trigger's
    own `expected_stamp` (CR 400.7), not by resetting this."""
    land_face_played: str | None = None
    """The name of the face this permanent entered as, when it was played as
    the land face of a modal double-faced card (CR 712.12).

    Set by `Game.play_land` when it chose the back face - Witch-Blessed
    Meadow rather than Witch Enchanter - and by `move_to` when a modal spell
    cast as its nonland back face (CR 712.11b) resolves onto the battlefield
    with that face up (CR 712.13): The Prismatic Bridge rather than Esika.
    Cleared by `move_to` on any move off the battlefield (CR 712.8a). CR 712.8f: "While a
    modal double-faced ... permanent is on the battlefield, it has only the
    characteristics of the face that's up," so `types`, `subtypes`,
    `oracle_text`, `mana_cost` and `name` below read this face instead of the
    card's front once it is set. Unlike `transformed` (CR 701.27a), the
    choice is made once, when the card is played, and never changes after -
    an MDFC does not transform back and forth.
    """
    face_played: str | None = None
    """The name of the half chosen for a **split card** (CR 709.3) or an
    **adventurer card** (CR 715) on the stack - Wear // Tear's "Tear" when that
    half, not Wear, was cast; Bonecrusher Giant // Stomp's "Stomp" when the
    Adventure was.

    Two rules, one field, because they say the same thing about the same
    moment. CR 709.3b: "While on the stack, only the characteristics of the
    half being cast exist. The other half's characteristics are treated as
    though they didn't exist." CR 715.3b: "While on the stack as an Adventure,
    the spell has only its alternative characteristics." Both are undone in
    every other zone - CR 709.2 makes a split card "only one card" again off
    the stack, CR 715.4 says "in every zone except the stack, and while on the
    stack not as an Adventure, an adventurer card has only its normal
    characteristics" - which is why `up_face` reads this field only while
    `zone is Zone.STACK`.

    Set by `Casting.cast`, which knows which half was announced
    (`Casting.face`/`chosen_face`), for `Layout.SPLIT` and `Layout.ADVENTURE`
    alike, and set *unconditionally* - an announcement that named no face
    clears it, which is CR 715.4's answer for an adventurer card recast as its
    creature half after CR 715.3d exiled it. When `fused` (below) is set,
    this still names the **left** half (CR 702.102d's own resolution order),
    for every reader that only ever expected one name here.
    """
    fused: bool = False
    """True while this fused split spell (CR 702.102) is on the stack as
    *both* halves cast together, rather than the ordinary one CR 709.3
    names.

    CR 702.102a: "If a player casts a split card with fuse from their hand,
    the player may choose to cast both halves of that split card rather than
    choose one half." Set by `Casting.cast_fused`/`cast`, alongside
    `face_played` (which keeps naming the left half so a caller reading only
    that still gets a real, on-card name rather than `None`). CR 702.102b/d:
    while this is set, `CardState.up_face`'s single-face reads are no longer
    the whole truth of the spell's cost or effect - `Casting.base_cost`/
    `.targeting` and `Game._resolve_top` read both faces directly instead
    of going through this flag, the same way a modal spell's chosen bullets
    are read directly rather than forced through `up_face`. Never explicitly
    cleared, the same as `face_played` itself is not - both are simply
    ignored by every reader once the card leaves the stack (CR 709.2: "only
    one card" everywhere else), since nothing reads either field there.
    """
    prepared: bool = False
    """CR 722.3a's "prepared" designation on a permanent with a prepare spell.

    "Prepared is a designation that acts as a marker which rules and effects
    can identify. A permanent can't gain this designation unless it has a
    prepare spell. Additionally, a permanent can't gain this designation if
    the permanent already has it." `Game.become_prepared`/`become_unprepared`
    are the only writers, and both are idempotent for exactly that second
    sentence's reason. Meaningless off the battlefield - nothing here clears
    it on its own when a permanent leaves, since `Game.become_unprepared` is
    what a permanent leaving the battlefield calls, alongside removing the
    linked exile copy `prepared_copy_id` names (CR 722.3c: the copy persists
    "for as long as the prepared permanent remains on the battlefield and has
    the prepared designation").
    """
    prepared_copy_id: UUID | None = None
    """The id of this permanent's own CR 722.3c exile copy, while `prepared`
    is set - `None` otherwise. Sits on the *permanent*, not on the copy: the
    copy is a `CardState` of its own in `Game.exile`, found by this id, whose
    `prepare_spell_face` (below) is what gives it the prepare spell's own
    characteristics rather than the permanent's."""
    prepare_spell_face: bool = False
    """True only on a CR 722.3c exile copy: its `up_face` (and therefore
    `name`/`types`/`oracle_text`/`mana_cost`/`power`/`toughness`) reads
    `Card.back_face` - the inset "prepare spell" - rather than the front
    face's own characteristics, matching 722.3c's "Those characteristics
    become the copy's normal characteristics." Also the flag `TriggerEvent`
    reading checks for CR 722.3d's "cast a prepared spell": "If a prepare
    spell is copied, the copy is also a prepare spell" is why `Game.copy_spell`
    carries this flag onto any further copy of one of these, rather than
    only setting it where the exile copy is first minted."""
    protector: str | None = None
    """CR 310.9: the player designated as this battle's protector - chosen by
    its controller as it enters (CR 310.9a, 310.12a), replaced by CR
    704.5x/704.5y, and the "defending player" for a creature attacking it
    (CR 310.9d, 508.5). `Game.enter_the_battlefield` is the one place it is
    reset, so a battle that has left the battlefield still answers who it was
    protected by (CR 508.5's "before it was removed from combat"); CR 310.9g
    keeps it when the permanent stops being a battle."""
    monstrous: bool = False
    """CR 701.37b's "monstrous" designation, put there by the Monstrosity
    keyword action (CR 701.37a): "'Monstrosity N' means 'If this permanent
    isn't monstrous, put N +1/+1 counters on it and it becomes monstrous.'"

    "Monstrous is a designation that has no rules meaning other than to act
    as a marker that the monstrosity action and other spells and abilities
    can identify. Only permanents can be or become monstrous. Once a
    permanent becomes monstrous, it stays monstrous until it leaves the
    battlefield. Monstrous is neither an ability nor part of the permanent's
    copiable values." The "neither an ability nor copiable" half is why this
    lives here as a plain designation field, the same as `prepared` below,
    rather than as a granted ability or a `Card`-level characteristic: a
    fresh `CardState` built by a copy effect (`token_copy_of`, a "becomes a
    copy of target" continuous effect) never sets this field, so a copy of a
    monstrous permanent is simply not monstrous, with no exclusion logic
    anywhere needed to make that true. `Game.become_monstrous` is the only
    writer; `Game._note_left_battlefield` clears it (and `monstrous_x`) for
    every route a permanent leaves the battlefield by, which is CR 701.37b's
    "stays monstrous until it leaves the battlefield" - there is no
    "becomes unmonstrous" effect anywhere in the rules to call a separate
    unsetter for, unlike `prepared`'s own `become_unprepared`."""
    monstrous_x: int | None = None
    """CR 701.37c: "If a permanent's ability instructs a player to
    'monstrosity X,' other abilities of that permanent may also refer to X.
    The value of X in those abilities is equal to the value of X as that
    permanent became monstrous." The N (or X) `Game.become_monstrous` put
    counters on this permanent with, kept so a later reader - a triggered
    ability's own "X" - can answer without re-deriving it from the counter
    count, which a static ability's own +1/+1 grant could otherwise have
    changed since. `None` while `monstrous` is `False`; both are cleared
    together."""
    saddled: bool = False
    """CR 702.171b's "saddled" designation: "Once a permanent has become
    saddled, it stays saddled until the end of the turn or it leaves the
    battlefield. Being saddled is not a part of the permanent's copiable
    values." Set by the saddle ability's own effect (CR 702.171a,
    `machines/keywords.saddle`); `machines/layers.ContinuousEffects.
    end_the_turn` ends it with every other "until end of turn" effect (CR
    514.2) and `move_to` off the battlefield ends it (CR 400.7)."""
    saddled_by: tuple[UUID, ...] = ()
    """CR 702.171c: "A creature 'saddles' a permanent as it's tapped to pay
    the cost to activate a permanent's saddle ability." The creatures that
    saddled this permanent this turn - what "a creature that saddled it this
    turn" names - cleared with `saddled`."""
    suspected: bool = False
    """CR 701.60a/b's "suspected" designation: a permanent is suspected "until
    it leaves the battlefield or until a spell or ability causes it to no
    longer be suspected", and "Suspected is neither an ability nor part of the
    permanent's copiable values". CR 701.60c's menace and "This creature
    can't block" are layer 6 effects `machines/layers.py` builds off this
    field while it is set (`_suspected_abilities`)."""
    solved: bool = False
    """CR 719.3b's "solved" designation on a Case: "Once a permanent becomes
    solved, it stays solved until it leaves the battlefield. The solved
    designation is neither an ability nor part of the permanent's copiable
    values." Set by the "To solve" trigger (CR 719.3a), read by "Solved"
    abilities (CR 702.169b-d), cleared by `move_to` off the battlefield."""
    renowned: bool = False
    """CR 702.112b's "renowned" designation: "Once a permanent becomes
    renowned, it stays renowned until it leaves the battlefield. Renowned is
    neither an ability nor part of the permanent's copiable values." Set by
    renown's own trigger (CR 702.112a, `machines/effects.py`'s "it becomes
    renowned"), cleared by `move_to` off the battlefield."""
    has_dealt_damage: bool = False
    """Whether this permanent has dealt damage since it came to the battlefield
    ("hasn't dealt damage yet", Karakyk Guardian, Ratonhnhake): written by
    `machines/conditions/history.record` from each damage event it is the
    source of, cleared by `move_to` off the battlefield (CR 400.7)."""
    paired_with: UUID | None = None
    """CR 702.95a's pairing: the `id` of the creature this one is paired with,
    or `None`. Only `machines/soulbond.py` writes it, and it reads it lazily
    (CR 702.95e: a pair that no longer holds is simply not a pair), so a stale
    pointer is harmless. Cleared by `move_to` (CR 702.95e, CR 400.7)."""
    venture_room: str | None = None
    """For a dungeon card in the command zone (CR 309.4): the name of the
    room its owner's venture marker is on. `machines/dungeon.py` is the only
    writer. `None` for every other object."""
    dungeon_completions: int = 0
    """For a dungeon card: how many times its owner has completed it (CR
    309.7: "A player completes a dungeon as that dungeon card is removed from
    the game"). A completed dungeon is kept outside the game (CR 400.11a) with
    this count, so "you've completed a dungeon" and "you haven't completed
    Tomb of Annihilation" have something to read after it has gone."""
    unlocked_doors: tuple[str, ...] = ()
    """CR 709.5c's "unlocked designations" of a Room permanent with a shared
    type line (Unholy Annex // Ritual Chamber) - each door (a half, CR
    709.5j) that has one, named by that face's own printed name. A door not
    in this tuple is "locked" (CR 709.5c). Set to the cast face as the
    permanent enters (CR 709.5d, `Game.enter_the_battlefield`, off `face_
    played` while it is still the incarnation that was cast), and by `Game.
    unlock_door` afterwards (CR 709.5e's special action, CR 709.5f's
    "unlock" instruction) - both append-only; nothing in this pool locks a
    door back (CR 709.5g), so there is no remover yet. Empty for every card
    that is not a Room, and for a Room that entered without being cast at
    all (CR 709.5d's own "if it's entering the battlefield and neither half
    was cast as a spell, it enters with neither unlocked designation")."""
    last_known_spell: SpellSnapshot | None = None
    """This card as it last left the stack (`SpellSnapshot`), taken by
    `move_to` and overwritten only by its next departure from the stack."""
    last_known_attachments: tuple["AttachmentSnapshot", ...] = ()
    """The Auras and Equipment attached to this object the last time it left
    the battlefield (CR 603.10a's look-back, CR 608.2h's last known
    information): Koll, the Forgemaster's "if it was enchanted or equipped"
    and Dawn Evangel's "if an Aura you controlled was attached to it" ask
    about a creature that has died, whose attachments are no longer
    attached to anything that exists. Taken with `last_known_power`, cleared
    by any move that does not start on the battlefield."""
    goaded_by: list[str] = Field(default_factory=list)
    """CR 701.15b's "goaded" designation: the players who goaded this
    permanent, in the order they did, each at most once (CR 701.15d: "the
    same player goading it again has no effect"). Each entry is also its own
    expiry: CR 701.15a's "until the next turn of the controller of that spell
    or ability" is that player's next turn, so `Game.begin_turn_for` drops
    exactly that player's entry and leaves the others (CR 701.15c). Not a
    copiable value (CR 701.15b), so nothing copies it; `Game.goad` is the one
    writer and `Game._note_left_battlefield` clears it, since the object that
    comes back is a new one (CR 400.7)."""
    phased_out_under: str | None = None
    """Who controlled this permanent when it phased out, or `None` while it
    is phased in (CR 702.26b's "phased out" status).

    CR 502.1: "all phased-out permanents that the active player controlled
    when they phased out phase in" - so the phase-in reads this, not the
    permanent's current controller. CR 702.26d: phasing changes neither zone
    nor control, so `zone` stays `Zone.BATTLEFIELD` throughout; what makes
    the permanent "treated as though it does not exist" (CR 702.26b) is that
    `Game.phase_out` moves it out of `Game.battlefield` into
    `Game.phased_out`, where no reader of the battlefield looks."""
    phased_out_indirectly: bool = False
    """CR 702.26g: an Aura, Equipment, or Fortification that phased out
    because the permanent it is attached to did. It "won't phase in by
    itself, but instead phases in along with the permanent it's attached
    to" - `Game.phase_in` brings it back with its host, and CR 502.1's
    untap-step phase-in never picks it up on its own."""
    meld_result: Card | None = None
    """The combined back face's printed characteristics (CR 712.8g), while
    this `CardState` is one half of a melded permanent - the surviving,
    "primary" half; its partner lives in `Game.melded_pairs`, keyed by this
    object's own `id`.

    CR 712.8g: "While the two cards of a meld pair are on the battlefield as
    a melded permanent, the object represented by those cards has only the
    characteristics of the combined back face." `Card` (not `CardFace`) on
    purpose: `Card` already carries every field `up_face` callers read
    (`name`, `type_line`, `oracle_text`, `mana_cost`, `colors`, `power`,
    `toughness`, `loyalty`) with the same names a `CardFace` has, so
    `CardState.up_face` can hand this straight back and every existing
    reader - `types`, `subtypes`, `oracle_text`, `power`, `toughness`,
    `name`, and `machines/layers.printed_characteristics` through them - gets
    the melded permanent's characteristics for free, the same way `up_face`
    already gives a transformed permanent its back face's. This is the
    combined-back-face printing itself (Hanweir, the Writhing Township, say),
    resolved by name off `Card.all_parts`'s own `meld_result` component
    (`machines/meld.py`), not a hand-built stand-in.

    `None` for every card that has never been melded, and for the "held"
    partner half too - only the primary carries this, which is what makes
    "one object represented by two cards" (CR 712.4a) collapse to one
    `CardState` on `Game.battlefield` rather than two independent ones combat,
    legal_actions and every state-based action would otherwise have to be
    taught to treat as a single permanent by hand.
    """

    melded_partner_id: UUID | None = None
    """The `id` of this permanent's other card, while melded - an id, not a
    live reference, for the same reason `Player.companion_id` is: the actual
    `CardState` lives in `Game.melded_pairs`, so nothing embeds a second,
    independently-mutable copy of it (see `memory/keyword-activation-round-
    trip-identity.md` for the shape of bug that class of embedding causes)."""

    meld_combined_mana_value: float | None = None
    """CR 202.3c/712.8g: "the mana value of a melded permanent is calculated
    as though it had the combined mana cost of the front faces of each card
    that represents it" - computed once, when `Game.meld` forms the pair
    (both front-face mana values are immutable printed data, so this never
    needs recomputing), and read by `CardState.mana_value` in place of
    `self.card.cmc` while `meld_result` is set."""

    merged_order: list[UUID] = Field(default_factory=list)
    """The `id`s of a merged permanent's components, topmost first, this
    object's own among them (CR 730.2: "place that object on top of or under
    that permanent"), while this `CardState` is the battlefield object of a
    merged permanent; the other components live in `Game.merged_components`,
    keyed by this object's `id` (the `melded_pairs` shape). Its
    characteristics are CR 730.2a's copiable effect, a layer 1 copy effect
    `Game.merge` registers: the topmost component's characteristics with
    every component's abilities (CR 702.140e). Empty when nothing has merged
    with it."""

    exerted: bool = False
    """True while this permanent will not untap during its controller's next
    untap step (CR 701.43a).

    "To exert a permanent, you choose to have it not untap during your next
    untap step." A flag rather than a count, because CR 701.43b has every
    instance expire in the same untap step: "If you exert a permanent more than
    once before your next untap step, each effect causing it not to untap
    expires during the same untap step."

    `untap` is what clears it, since that is the moment the effect expires.
    """
    regeneration_shields: int = 0
    """How many CR 701.19a regeneration shields are standing on this permanent.

    "If the effect of a resolving spell or ability regenerates a permanent, it
    creates a replacement effect that protects the permanent the next time it
    would be destroyed this turn." A count rather than a flag, because CR
    701.19a's effect is "the **next** time" - each regeneration is its own
    one-shot shield, and two of them survive two destructions.

    `machines/replacement._regeneration_effects` is what spends one, through
    the same CR 616.1 ordering every other destruction-replacement goes
    through. Cleared by `move_to` (CR 400.7: what comes back is a new object
    with no memory of this one) and by the cleanup step (CR 514.2: "this
    turn").
    """
    assigns_no_combat_damage_this_combat: bool = False
    """True while a resolved effect says this creature "assigns no combat
    damage this combat" (Master of Cruelties' own attack trigger).

    A flag scoped to the combat under way right now, not "this turn" - a
    creature that attacks again in a second combat phase (CR 500.4) assigns
    damage normally there. `machines.combat._assignment_power_of` reads it
    ahead of CR 510.1a's ordinary power-based assignment; `Game.
    declare_attackers_step` clears it for every permanent as the next combat's
    attackers are about to be declared, the same boundary `exerted`'s own
    "next untap step" expiry sits at for untapping.
    """
    damage: int = 0
    dealt_deathtouch_damage: bool = False
    """True if a source with deathtouch has dealt damage to this creature
    (CR 702.2b, CR 704.5h).

    "If a creature has toughness greater than 0, and it's been dealt damage by a
    source with deathtouch since the last time state-based actions were checked,
    that creature is destroyed" (CR 704.5h). That is a *separate* state-based
    action from lethal damage (CR 704.5g), and `Game.check_state_based_actions`
    dispatches only the second one - so `has_lethal_damage`, which is what it
    reads, answers for both. See `docs/engine-coverage.md` for the hook that
    would separate them again.

    Only set when damage was actually dealt, so damage that was prevented
    (CR 615.1a) never sets it. `machines/combat.py` is what sets it.
    """
    attachment: TargetRef | None = None
    """What this Equipment or Aura is attached to (CR 301.5a, 701.3a).

    CR 701.3a: "To attach an Aura, Equipment, or Fortification to an object **or
    player** means to take it from where it currently is and put it onto that
    object or player." The "or player" is why this is a `TargetRef` and not a
    card id: CR 702.5d lets an Aura's enchant ability name a player, and
    CR 704.5m's "attached to an illegal object **or player**" branch is
    unreachable if the model can only name a card.

    `None` means it is attached to nothing, which is the state every Equipment
    enters the battlefield in (CR 301.5b). `attached_to` below is the narrower
    read for the common case.
    """
    targets: list[TargetRef] = Field(default_factory=list)
    division: list[int] | None = None
    """CR 601.2d's announced division, one share per entry of `targets` in the
    same order - `None` when this spell divides nothing, or when it does but
    the caster's announcement was never recorded (kept `None` rather than
    defaulted to an even split here, so `machines/effects.py`'s divided-damage
    effect can tell "nothing was announced, split as evenly as it goes" apart
    from "1 and 1 was announced on purpose"). Set once, by
    `Casting.announce_division`, at the same CR 601.2c/d moment `targets`
    itself is fixed - CR 115.7f then keeps it unchanged even if a target is
    later removed and the spell's targets are changed, since a removed
    target's own share is dropped rather than handed to whoever is left
    (CR 608.2b already reads targets that way; this mirrors it for shares).
    """
    target_amounts: list[int] | None = None
    """One entry per entry of `targets`, in the same order, for a "`<source>`
    deals `<n>` damage to `<phrase1>` and `<m>` damage to `<phrase2>`"
    instruction whose two halves name *different* amounts
    (`machines/effects._merge_split_damage_clauses`) -
    `AbilityOnStack.target_amounts`'s own twin mirrored here for the
    identical CR 602.2b reason `division` already is. Unlike `division`, this
    is never a player announcement: the amounts are fixed on the printed
    card, so it is computed and stamped on as resolution begins rather than
    carried from CR 601.2c/d announcement. `None` for the ordinary
    single-amount case and for the equal-amount case, which never needed a
    per-target answer."""
    summoning_sick: bool = True
    """True until its controller's turn begins with it already there.

    "Summoning sickness" is not one rule: a creature must have been under its
    controller's control continuously since their most recent turn began
    before it can be declared as an attacker (CR 508.1a) or activate an
    ability with `{T}` or `{Q}` in its cost (CR 302.6, 602.5a). Haste turns
    both off (CR 702.10b, 702.10c).

    That is a fact about how long the card has been here, so it is set when the
    card arrives on the battlefield and cleared by `Game.begin_turn_for` for
    the player whose turn is starting.
    """

    exile_annotation: ExileAnnotation | None = None
    """Which pile of exile this card is in, when that matters (CR 406.4).

    Set as the card is exiled by a keyword that hands out permission to cast it
    later - plot (CR 702.170c), foretell (CR 702.143c), warp (CR 702.185a-b), and
    the Adventure exile of CR 715.3d. `move_to` drops it on the way out of
    exile, because a card that leaves exile is a new object (CR 400.7) and its
    pile no longer means anything.
    """

    turn_entered: int | None = None
    """The `TurnMachine.turns_taken` ordinal of the turn this permanent arrived
    on the battlefield, or `None` if nothing was counting (built outside a
    game, or before a turn existed). `turns_taken`, not `turn_number`: the
    round counter stays put when the next player's turn begins (CR 500.7), so
    it cannot tell "this turn" from the opponent's turn of the same round.

    Stamped once, in `Game.enter_the_battlefield` - the single choke point
    every route onto the battlefield runs through (CR 110.2a, CR 111.7,
    CR 603.6a) - so a card put onto the battlefield without being cast, a
    resolving permanent spell, and a token all get one the same way. This is
    the same shape as `ExileAnnotation.turn_exiled`, a turn-number stamp rather
    than a boolean, because "entered this turn" (Ocelot Pride, CR 702.131) has
    to stop being true once the next turn begins, not just once - unlike
    `summoning_sick`, which is cleared by `Game.begin_turn_for` and so cannot
    itself answer "did this arrive on the *current* turn specifically" once a
    permanent has stopped being sick without a real turn boundary having
    passed (a mid-turn effect that removes summoning sickness).
    """

    counters: Counters = Field(default_factory=Counters)
    """The counters on this object (CR 122.1).

    Counters are not retained when the object changes zones - they "simply
    cease to exist" (CR 122.2) - so `move_to` drops them. What they do is
    read where the rule that cares about them lives: +1/+1 and -1/-1 reach
    power and toughness through layer 7c (CR 613.4c), and loyalty counters
    are a planeswalker's loyalty (CR 306.5c).
    """

    class_level: int = 1
    """CR 716.2b's "level" - a Class enchantment's own progression, not a
    counter: "Class levels do not interact with level counters" (CR 702.87c,
    711.7), so this lives here instead of on `counters`. CR 716.2d: "If a
    rule or effect refers to a permanent's level and that permanent doesn't
    have a level, it is treated as though its level is 1" - which is also
    every non-Class permanent's value, harmlessly unread."""

    face_down_characteristics: FaceDownCharacteristics | None = None
    """What this object is while it is face down (CR 708.2).

    Set by `turn_face_down` and cleared by `turn_face_up`, which is CR 702.37e's
    "the morph effect on it ends, and it regains its normal characteristics".
    Everything on this model that reports a characteristic - `name`, `power`,
    `toughness`, `types`, `subtypes`, `keywords`, `oracle_text`, `mana_cost` -
    reads this first, so a face-down Brine Elemental is a nameless 2/2 to
    anything that asks the object rather than the printing.

    `self.card` is deliberately untouched: it is the printing, and CR 708.9 has
    the owner reveal it as it leaves the battlefield.
    """

    manifested: bool = False
    """Whether this object is a manifested permanent (CR 701.40a), for as
    long as it remains face down.

    Set by `machines/effects.manifest` and cleared by `turn_face_up` (CR
    701.40a: "That permanent is a manifested permanent for as long as it
    remains face down"). Distinct from `face_down_characteristics`, which a
    face-down morph or disguise spell sets to the identical empty
    `FaceDownCharacteristics()` shape - the two mechanisms make an object
    face down the same way, but only a manifested (or, once printed in this
    pool, cloaked - CR 701.58a) permanent may be turned face up by paying its
    own mana cost (CR 701.40b, CR 701.58b), rather than a morph ability's own
    cost (CR 702.37e). Without this flag nothing could tell the two apart:
    `machines/keywords.why_cannot_turn_up_manifested`/`.manifest_turn_up_cost`
    read it, through `machines/special_actions.py`'s seat-facing checks.
    """

    last_known_power: int | None = None
    """The power this object had the last time it left the battlefield (CR 608.2h).

    `last_known_counters`' sibling, and there for the same reason: an effect
    that has to look at a permanent which is no longer a permanent has nothing
    left to read. Counters are only half the answer - CR 122.2 destroys them
    on a zone change, which `last_known_counters` records - because a
    continuous effect stops applying too, and no snapshot recorded that.
    Omnath, Locus of Mana is the card that makes the difference visible: its
    "+1/+1 for each unspent green mana you have" is a continuous effect from a
    static ability (CR 604.2), so a sacrificed Omnath's printing says 1 and
    the answer CR 608.2h wants is 5.

    `None` for an object that has never left the battlefield, which is also
    every object that has never been on it.
    """

    last_known_toughness: int | None = None
    """The toughness this object had the last time it left the battlefield
    (CR 608.2h). `last_known_power`'s other half, taken at the same instant."""

    last_known_mana_value: float | None = None
    """The mana value this object had the last time it left the battlefield
    (CR 608.2h), when that differed from the card's own - a Clone that
    entered as a copy of Memnite had Memnite's mana cost (CR 707.2), so a
    sacrificed Clone's "sacrificed creature's mana value" is 0, not the 4 its
    own card prints. `None` when the card's own `mana_value` already is the
    answer, taken with `last_known_power`."""

    last_known_copiable: Card | None = None
    """This object's copiable values (CR 707.2) the last time it left the
    battlefield, when a copy effect made them differ from its own card - a
    Clone that entered as a copy of Ochre Jelly *was* Ochre Jelly there, so
    Split's "create a token that's a copy of it" (CR 603.10a's look-back,
    CR 608.2h) copies Ochre Jelly, not the Clone card in the graveyard.
    Stamped by `Game._note_left_battlefield` (the layer engine is gone by
    `move_to`) on every departure from the battlefield, and kept across later
    moves exactly as `last_known_counters` is, so a dies trigger still on the
    stack reads the same answer after the card was exiled from the graveyard
    in response. Only a look-back reads it; a card in a graveyard copied as
    a card is its own printing. `None` when the card is the answer."""

    last_known_colors: tuple[Color, ...] | None = None
    """The colours this object had the last time it left the battlefield
    (CR 608.2h), when a continuous effect made them differ from the printing.

    `last_known_power`'s sibling for the question CR 702.11d and CR 702.16b ask
    of an ability's *source*: "abilities ... from [quality] sources". CR 608.2b
    has an ability whose source "has left the zone it was in" use "its last
    known information", so the quality is read here rather than off the
    printing. `None` when the printing already is the answer."""

    last_known_types: tuple[Type, ...] | None = None
    """The card types this object had the last time it left the battlefield
    (CR 608.2h) - `last_known_colors`' other half, taken at the same instant."""

    last_known_subtypes: tuple[str, ...] | None = None
    """The subtypes this object had the last time it left the battlefield
    (CR 608.2h) - taken with `last_known_colors`."""

    last_known_attacking: bool = False
    """Whether this object was an attacking creature (CR 508.1k) the last
    time it left the battlefield (CR 608.2h). CR 506.4 removes it from combat
    as it goes, so "damage attacking creatures would deal" (Harmless
    Assault's shield, CR 609.7b) asks this of a source sacrificed mid-combat
    to its own ability. Stamped by `Game._note_left_battlefield`, reset by
    `move_to` on any move that does not start there (CR 400.7)."""

    last_known_keywords: tuple[str, ...] | None = None
    """The keywords this object had, lowercased, the last time it left the
    battlefield (CR 702.90d, CR 702.80b). `last_known_power`'s sibling for
    abilities: "If an object is no longer in the zone it's expected to be in
    as an effect causes it to deal damage, its last known information is used
    to determine whether it had infect" - and wither the same. A Mogg Fanatic
    given infect by Tainted Strike and sacrificed to its own ability is a
    card in a graveyard with no infect printed by the time the ability
    resolves; the layer-6 grant is only remembered here.

    `None` for an object that has never left the battlefield, and reset by
    `move_to` on any move that does not start there, as the P/T snapshot is.
    """

    last_known_counters: Counters = Field(default_factory=Counters)
    """The counters this object had the last time it changed zones (CR 704.8).

    CR 122.2 destroys the counters on a zone change, and CR 603.10a lets a dies
    trigger look back in time at the object as it last existed. Persist's
    intervening *if* - "if it had no -1/-1 counters on it" (CR 702.79a) - is
    exactly that question, and there is nothing else left to ask.
    """

    last_known_attached_to: UUID | None = None
    """The card this object was attached to as it last left the battlefield
    (CR 608.2h's last known information), `None` if it was attached to no
    card or its last move did not start on the battlefield.

    CR 113.7a has an Aura's enters trigger exist independently of the Aura,
    so answering Enchanted River's Grasp's "tap enchanted creature and remove
    all counters from it" by removing the Grasp itself still leaves the
    trigger to find the creature it enchanted - which it can only read here,
    since leaving the battlefield unattaches it (CR 400.7).
    """

    choice: Choice | None = None
    """An "as [this] enters, choose ..." answer, made before this object
    entered the battlefield (CR 614.1c, CR 614.12a).

    `None` until such a choice is made, and until then, until asked. Not
    reset by `move_to` - CR 614.12a's choice is made once, as the permanent
    that carries it enters, and nothing in the pool this generalizes for
    (Utopia Sprawl's chosen color, Runed Halo's chosen card name, Cavern of
    Souls' chosen creature type) ever asks again for the same object's
    lifetime on the battlefield, so there is no rule that says it should be
    dropped on some other zone change either.
    """

    chosen_player: str | None = None
    """The player an "as [this] enters, choose a player/an opponent" answer
    named (CR 614.12a), read back by "the chosen player" (Stuffy Doll's
    "deals that much damage to the chosen player", Booby Trap's "The chosen
    player reveals each card they draw", Nyxathid's "card in the chosen
    player's hand"). Kept apart from `choice` because one sentence can ask
    for a player *and* a card name at once (Booby Trap: "choose an opponent
    and a card name"), and `choice` holds one answer. Set afresh every time
    the permanent enters, the same as `choice`."""

    devoured: tuple["DevouredObject", ...] = ()
    """What this permanent's devour ability sacrificed as it entered (CR
    702.82b: "'It devoured' means 'sacrificed as a result of its devour
    ability as it entered the battlefield.'"), each as it last existed on the
    battlefield - Voracious Dragon's "the number of Goblins it devoured" asks
    a subtype the sacrificed creature had, not one its card has now. Written
    by `machines/replacement._sacrifice_any_number_then_enter_with_counters`
    on every devour entry (empty when nothing was sacrificed), so a permanent
    that re-enters never carries an old object's record (CR 400.7)."""

    crafted_with: tuple[UUID, ...] = ()
    """CR 702.167c: "the exiled cards used to craft" this permanent - the
    materials its craft ability exiled, by id. Written when the card returns
    transformed (`machines/keywords._craft_effect`); Mastercraft Raptor's "total
    power of the exiled cards used to craft it" reads them from exile."""

    controlled_since_upkeep: tuple[str, int] | None = None
    """`(controller, upkeeps)`: who controlled this permanent when it was last
    seen to come under someone's control, and how many upkeeps that player had
    begun by then (`Game.upkeeps_begun`). Echo's "if this permanent came under
    your control since the beginning of your last upkeep" (CR 702.30a) is true
    when the controller is still that player and `upkeeps` is at least their
    current count minus one. `None` for a permanent that was on the
    battlefield before anything recorded it (a game set up in place), read as
    having come under its controller's control before any upkeep began."""

    chosen_modal_options: tuple[str, ...] = ()
    """Every mode text this object's own "choose one that hasn't been
    chosen -" triggered ability has already picked (Gollum, Riddle Master's
    own three-bullet trigger), oldest first. Not a `Choice` - CR 614.12a's
    choice is made once, as this permanent enters, while this is a running
    memory a *triggered ability of the permanent* extends every time it
    resolves and picks a fresh mode, the same "modes tracked per object" the
    printed "that hasn't been chosen" clause asks for. Kept on the object
    itself, not on the ability, so it survives from one triggering to the
    next the way `counters` does. Never reset by `move_to`: nothing in the
    pool says a permanent that left and returned forgets which of its own
    modes it already used, and Gollum's own three-mode trigger has no
    reset clause at all.
    """

    chosen_modal_options_this_turn: tuple[str, ...] = ()
    """The same "modes tracked per object" memory as `chosen_modal_options`,
    for the printed clause's other wording - The Vision's "choose one that
    hasn't been chosen **this turn** -". A card printed with the "this turn"
    qualifier resets every cleanup step (`Game.cleanup_step`, CR 514.2's
    "'until end of turn' and 'this turn' effects end"); Gollum's own
    unqualified "hasn't been chosen" never resets, which is why that memory
    stays a separate field rather than sharing this one under a duration
    flag - clearing this field at cleanup must never touch Gollum's.
    """

    spliced_text: tuple[str, ...] = ()
    """Rules text added to this *spell* by a splice ability (CR 702.47c).

    "The spell has the characteristics of the main spell, plus the rules text
    of each of the spliced cards. This is a text-changing effect (see rule
    612)." CR 612.10 fixes where it goes: "A splice ability changes a spell's
    text by adding the rules text of the card with splice to the spell,
    following that spell's own rules text. It doesn't modify or replace any of
    that spell's own text." So it is appended by `oracle_text`, never merged
    into the printing - `Card` stays the immutable Scryfall object.

    Cleared by `move_to`, which is CR 702.47e: "The spell loses any splice
    changes once it leaves the stack for any reason."
    """

    granted_rebound: bool = False
    """Whether an effect gave *this spell* rebound (CR 702.88, CR 702.88a)
    for this cast, printed on a different card than the one being cast -
    Ojer Pakpatiq, Deepest Epoch's own "Whenever you cast an instant spell
    from your hand, it gains rebound." Rebound is normally a static ability
    printed on the spell itself, which `machines.keywords.has_rebound` reads
    straight off `Card.keywords` - a spell it was never printed on has
    nothing there for that to find, so `Game._has_rebound_now` reads this
    flag as well, wherever `has_rebound` alone used to be asked about a
    spell on the stack (CR 614.12: a granted static ability "functions" the
    same as a printed one for as long as it applies).

    Cleared by `move_to`, the same "a spell's own additions don't survive
    leaving the stack" rule `spliced_text` already follows (CR 702.47e's
    reasoning generalises: nothing keeps a one-shot grant once the object it
    was granted to stops being this stack visit's object)."""

    granted_ability_texts: tuple[str, ...] = ()
    """Ability lines given to *this object specifically*, printed exactly as
    the granting effect's own quoted text - "This Saga gains '{T}: Add
    {C}.'" (Urza's Saga, chapter I). CR 611.1: a continuous effect lasts "for
    a fixed or indefinite period", and CR 611.2a's own default for a
    resolution effect that states no duration is indefinite rather than
    until end of turn - modelled by keeping the line here, not by a
    continuous effect that has to be reapplied every board computation,
    until CR 400.7 ends the object: `move_to` empties it on every zone
    change except a permanent spell becoming a permanent (CR 400.7a).

    Kept apart from `Card.oracle_text` (the printing, which never changes)
    and from the layer engine's own `Characteristics.
    abilities` (a *computed*, per-recompute view for text-driven checks like
    `has_ability`): this tuple is what `machines/abilities.granted_abilities_
    of` parses back into real `Ability` objects, and what `Game.
    activated_abilities`/`machines/cost.py`'s mana-source lookup both fold in
    alongside a card's own printed abilities, so a granted ability is not
    just visible but actually usable - activatable, tappable for mana - the
    same as one printed on the card."""

    cast_with_keyword: str | None = None
    """The keyword whose alternative cost was paid to cast the spell this
    permanent became (CR 118.9, 601.2b), for this object only.

    CR 702.176a asks "if this permanent's impending cost was paid" of the
    *permanent*, on every later end step, and `Game.cast_records` cannot answer
    that on its own: `CardState.id` survives a zone change, so a blinked
    permanent would still find the record its earlier incarnation left. CR
    400.7 makes the returning object a new one that nobody cast, which is why
    `move_to` clears this on every move and `Game.enter_the_battlefield` sets
    it only for a permanent entering as a spell that was cast."""

    bestowed: bool = False
    """True while this object was cast bestowed and is still an Aura (CR 702.103).

    CR 702.103a makes bestow "a static ability that functions in any zone from
    which you could play the card it's on"; CR 702.103b is what this flag
    represents: "As a spell cast bestowed is put onto the stack, it becomes an
    Aura enchantment and gains enchant creature. It is a bestowed Aura spell,
    and the permanent it becomes as it resolves will be a bestowed Aura
    permanent."

    So it is not a fact about the printing - the same Detective's Phoenix is a
    creature when hardcast and an Aura when bestowed - which is exactly why it
    lives here and not on `Card`. `types`, `subtypes` and `keywords` all read it
    while the object is on the stack or the battlefield, the two zones CR
    702.103b names; everywhere else the card is the enchantment creature it
    prints.

    Cleared by `unattach` (CR 702.103f: "If a bestowed Aura becomes unattached,
    it ceases to be bestowed") and by `move_to` for any zone change, since
    CR 400.7 makes what leaves a new object that was never cast bestowed at
    all. `Casting.cast` is what sets it (CR 601.2b's announcement is where
    "you may choose to cast it bestowed" is answered)."""

    prototyped: bool = False
    """True while this object was cast prototyped (CR 702.160a, CR 718.3).

    CR 718.3b: "Both a prototyped spell and the permanent it becomes have only
    its alternative set of power, toughness, and mana cost characteristics",
    and the colour of that cost. `mana_cost`, `mana_value`, `colors`,
    `printed_power` and `printed_toughness` read the alternative set (the
    printed "Prototype {cost} - P/T" line, `prototype_characteristics`) while
    this is set. Carried across exactly one zone change, the spell becoming
    its permanent, like `bestowed`; any other move is CR 400.7's new object
    (CR 718.4). `Casting` sets it as the spell goes on the stack."""

    discarded_by: str | None = None
    """Who discarded this card (CR 701.9a), for as long as it stays where the
    discard put it. `None` for a card that reached its zone any other way.

    Mayhem is why this exists. CR 702.187b: "'Mayhem [cost]' means 'As long as
    you discarded this card this turn, you may cast it from your graveyard by
    paying [cost] rather than paying its mana cost.'" That is a fact about one
    specific card and about who discarded it - `Game.cards_discarded_this_turn`
    counts a player's discards and cannot answer either half.

    Written by `machines/keywords.discard`, the one place a discard actually
    happens with a game to hand, and cleared by `move_to` for any destination
    but the graveyard, because CR 400.7 makes a card that moves on a new object
    that was never discarded. It is *not* cleared on the way into the graveyard,
    which is where the discard puts it - the same asymmetry `exile_annotation`
    already draws for a card annotated as it is exiled."""
    discarded_on_turn: int | None = None
    """The turn number this card was discarded on (CR 701.9a), or `None`.

    Mayhem's "this turn" (CR 702.187b) read against `Turn.turn_number`, and the
    reason this is a turn number rather than a flag: nothing sweeps the
    graveyard at end of turn, so "was it discarded this turn" is answered by
    comparing to the turn it is being asked on, exactly the way
    `ExileAnnotation.turn_exiled` answers plot's and foretell's "a later turn"
    (CR 702.170d, CR 702.143a)."""

    zone_change_stamp: UUID = Field(default_factory=new_id)
    """Which incarnation of this object we are on (CR 400.7).

    "An object that moves from one zone to another becomes a new object with
    no memory of, or relation to, its previous existence." This engine keeps
    one `CardState` and mutates it in place across a zone change rather than
    replacing it, so `id` alone cannot tell a card that has always been in
    exile apart from a card that left exile and came back to it by some other
    route - and CR 603.7c's parenthetical is explicit that the second one
    "is a new object and thus won't be affected." `move_to` reassigns this on
    every call, so a delayed trigger that captured it at creation
    (`DelayedTrigger.expected_stamp`) can tell a round trip from a card that
    simply never moved.
    """

    _announced_from: Any = PrivateAttr(default=None)
    """The zone this card was in when its casting was announced (CR 601.2a): the
    cast record that says so is only written once the spell is cast (CR 601.2i),
    but a granted convoke ("Spells you cast from exile have convoke") is read
    while the total cost is being paid, in between. Private, never serialised."""

    _board_source: Any = PrivateAttr(default=None)
    """The `Game` this object asks for its computed characteristics (CR 613.5).

    A private attribute, so it is neither a field nor serialised: a board that
    round-trips through `model_dump`/`model_validate` carries no reference to
    the game it came from, and this one is re-established by whoever rebuilt
    the game. `None` means "nothing to ask", and every characteristic that
    consults it falls back to the printed value plus counters, which is
    exactly what this model did before the hook existed.

    Set by `bind_to_game`. CR 613.5 is why it is a live reference rather than
    a cached answer: "The application of continuous effects as described by
    the layer system is continually and automatically performed by the game.
    All resulting changes to an object's characteristics are instantaneous" -
    so the question has to be asked again every time, not answered once.
    """

    _asking_the_board: bool = PrivateAttr(default=False)
    """Re-entrancy guard for `computed_characteristics`.

    Computing the board reads the permanents on it, and one of those reads -
    `Game`'s own "creature with power N or greater" sweep for a static
    ability - goes back through `CardState.power`. Without this flag that is
    an unbounded recursion; with it, the inner read takes the printed branch,
    which is the value layer 7a itself starts from (CR 613.4a).
    """
    _entering_battlefield: bool = PrivateAttr(default=False)
    """Set by `Game.put_onto_battlefield` while it asks CR 614.12's
    replacement effects about this object: "check the characteristics of the
    permanent as it would exist on the battlefield". While it is set the
    object answers as it will on the battlefield, so CR 113.6c's
    off-battlefield grant (`off_battlefield_characteristics`) is already
    gone - a Grist coming in from exile is not a "creature [that] would
    enter". Never persisted: it only spans one call."""
    _granted_as_it_left: tuple[str, ...] = PrivateAttr(default=())
    """`granted_ability_texts` as this object last left the battlefield,
    which `move_to` has just emptied (CR 400.7). CR 603.10a: a
    leaves-the-battlefield ability looks back in time, so a granted one -
    Thief of Existence's own rider - still triggers on the move that ended
    it; `machines/triggers.triggered_abilities_on` reads this for a source
    off the battlefield. Reset on every move, so it only ever describes the
    move just made. Never persisted: the departure event is raised and its
    triggers found within that same move."""

    _left_in_epoch: int | None = PrivateAttr(default=None)
    """`Game._departure_epoch` as this object last left the battlefield -
    see `left_battlefield_in`. Never persisted."""

    _abilities_as_it_left: tuple[str, ...] | None = PrivateAttr(default=None)
    """The computed ability lines this object had as it last left the
    battlefield (CR 603.10a's look-back), taken by
    `remember_last_known_power_toughness` while the layer engine still
    answered for it; `None` when no board was bound. A leaves-the-battlefield
    trigger it had *lost* by then (Hellcat returned with no abilities, a
    creature under Humility) does not trigger - read by `machines/triggers.
    triggered_abilities_on`. Never persisted: the departure's triggers are
    collected within that same move, and any later move clears it."""

    def bind_to_game(self, game: Any) -> None:
        """Tell this object which game computes its characteristics (CR 613.5).

        `power` and `toughness` are the two characteristics the rest of the
        engine reads straight off a `CardState` - `machines/combat.py` for
        CR 510.1a's combat damage assignment, `has_lethal_damage` for
        CR 704.5g - and on their own they are only the printed value plus
        counters (CR 122.1a). That is the wrong answer for anything a
        continuous effect touches: a characteristic-defining ability in layer
        7a (CR 604.3, CR 613.4a) gives Tarmogoyf a power at all, where the
        printing has `*` and this model has `None`, and an anthem in layer 7d
        makes a Grizzly Bears a 3/3.

        Once bound, those two properties ask `Game.characteristics_of` for a
        permanent on the battlefield and fall back to the printed value
        everywhere else, so the answer a caller gets is the same one
        `Game.power_of` and `Game.toughness_of` already give.

        Binding is a pure addition: an unbound `CardState` behaves exactly as
        it did before, which is what keeps this safe to call from one place
        rather than needing every construction site to know about it.
        """
        self._board_source = game

    @property
    def computed_characteristics(self) -> Any:
        """This permanent's characteristics with every layer applied, or None.

        `None` - meaning "ask the printing instead" - in four cases, each of
        which is a case where the layer engine has no answer to give:

        - nothing has bound a game (`bind_to_game`), which is every
          `CardState` built outside a game;
        - this object is not on the battlefield, because CR 613.5's layer
          system is applied to permanents and `Game.characteristics_of`
          refuses anything else;
        - the board is already being computed on this object, which the
          `_asking_the_board` guard catches;
        - the bound game does not have this object on its battlefield - a
          stale binding, which raises `KeyError` out of `ComputedBoard.of`
          rather than answering with another game's board.
        """
        game = self._board_source
        if game is None or self.zone is not Zone.BATTLEFIELD or self._asking_the_board:
            return None
        self._asking_the_board = True
        try:
            return game.characteristics_of(self)
        except KeyError:
            return None
        finally:
            self._asking_the_board = False

    @property
    def controller(self) -> str | None:
        """Who controls this object right now, layer 2 included (CR 613.1b).

        `stored_controller` is the base; a control-changing effect - Threaten's
        "gain control of it until end of turn", Act of Treason's, an Aura's -
        is a continuous effect in layer 2, and CR 613.5 has the layer system
        "continually and automatically" applied, so the answer has to be
        computed rather than stored. Exactly the shape `power` and `toughness`
        already have, and for exactly the same reason: everything that asks -
        combat, the state-based actions, a delayed trigger, a test - asks this
        attribute, and none of them should have to know the layer system
        exists.

        Falls back to the base whenever the layer engine has nothing to say:
        an unbound `CardState`, or an object that is not on the battlefield -
        which is right twice over, since CR 109.4 gives only objects on the
        stack or the battlefield a controller at all, and the stack is not a
        zone CR 613.5 computes.
        """
        effects = getattr(self._board_source, "continuous_effects", None)
        if effects is not None and not effects.has_control_effect(self._board_source):
            # Nothing in play changes control, so the board would hand back
            # this very value - and computing it is not free. See
            # `ContinuousEffects.has_control_effect` for why that is sound.
            return self.stored_controller
        computed = self.computed_characteristics
        if computed is not None and computed.controller is not None:
            return computed.controller
        return self.stored_controller

    @controller.setter
    def controller(self, value: str | None) -> None:
        """Set the *base* controller (CR 613.1b's layer 2 is not written here).

        A caller stating who controls a permanent - `Game.put_onto_battlefield`
        as it enters, `Game.change_control` for a permanent handed over with no
        duration - is stating the base the layers are then applied to.
        """
        self.stored_controller = value

    @property
    def controller_or_owner(self) -> str | None:
        """CR 108.4a's fallback: the controller, or the owner when there is none.

        "If anything asks for the controller of a card that doesn't have one
        (because it's not a permanent or spell), use its owner instead." A card
        in a graveyard, a hand, or a library has no controller (CR 109.4), so
        "target card in your graveyard" is a question about ownership.
        """
        return self.controller if self.controller is not None else self.owner

    # -- characteristics (CR 109.3, CR 708.2) ------------------------------
    #
    # Each of these is the printing's value unless the object is face down, in
    # which case CR 708.2 says the listed characteristics are all it has. They
    # are *not* the whole of CR 613: `Game.characteristics_of` is the authority
    # once other continuous effects are in play.

    @property
    def has_no_characteristics(self) -> bool:
        """CR 406.3a: a card exiled face down has no characteristics at all.

        "A card exiled face down has no characteristics, but the spell or
        ability that exiled it may allow it to be played from exile. Unless
        that card is being cast face down (see rule 708.4), the card is turned
        face up before the player announces they are playing it."

        A stronger statement than CR 708.2, which lists a *replacement* set for
        a face-down spell or permanent (a 2/2 with no name, CR 708.2a): a card
        in exile is neither a spell nor a permanent, so nothing lists anything
        for it and it is left with nothing. That is DDR#956's ruling - an
        Emrakul, the Promised End exiled face down by Pyxis of Pandemonium has
        no mana cost, so CR 202.3a gives it a mana value of 0 rather than 13,
        and "the greatest mana value among cards in exile" gets nothing from
        it even though the whole table watched it go there.

        Scoped to a card in **no pile that grants permission to play it** -
        `exile_annotation is None`, or only CR 607.2a's bare `ExileMarker.
        LINKED` "exiled with" link, which grants nothing - and that is an
        approximation the rule's
        own second sentence is what would replace. CR 601.3f: "Some effects
        allow a player to cast a spell with certain qualities from among
        face-down cards in exile. A player may begin to cast such a spell only
        if they can look at the face-down card in exile", and CR 406.3a then
        turns that card face up *before* its controller announces they are
        playing it. So a foretold (CR 702.143a), hideaway (CR 702.75a),
        plotted, madness (CR 702.35a) or suspended card is one the engine still
        has to be able to read a name, a type line and a cost off in order to
        offer the cast at all, and it will be face up by the time the cast is
        announced anyway. Turning it face up at announcement, which would let
        this drop the annotation clause entirely, is a `machines/casting.py`
        change - see `docs/engine-coverage.md`.

        Nothing is undone by hand on the way out: `move_to` turns a card face
        up as it leaves exile for anywhere but the stack-as-a-face-down-spell,
        so a card exiled face down with no pile of its own has its
        characteristics again the moment something moves it.
        """
        if self.zone is not Zone.EXILE or not self.face_down:
            return False
        # CR 607.2a's bare link (`ExileMarker.LINKED`) is not a pile that
        # grants a play: Pyxis of Pandemonium's face-down cards are "exiled
        # with" it and still have no characteristics until it turns them
        # face up (CR 406.3).
        annotation = self.exile_annotation
        return annotation is None or annotation.marker is ExileMarker.LINKED

    @property
    def _land_face(self) -> Any:
        """The `CardFace` named by `land_face_played`, or None."""
        if self.land_face_played is None:
            return None
        for face in self.card.card_faces or []:
            if face.name == self.land_face_played:
                return face
        return None

    @property
    def up_face(self) -> Any:
        """The face this object's characteristics come from, or None for a
        single-faced card whose own top-level fields already are the up face
        (CR 712.8a, 712.8d, 712.8f, 712.12).

        Four cases, and the discriminator differs for each:

        - The **land face**, when this was an MDFC played for its land side.
          CR 712.8f gives a modal double-faced permanent "only the
          characteristics of the face that's up" and `land_face_played` is how
          that choice is recorded (CR 712.12). It is chosen once, as the card
          is played, and never changes.
        - The **back face**, while `transformed` is set. CR 701.27a turns the
          permanent over, CR 701.27g calls the result a transformed permanent,
          and CR 712.8e gives it "only the characteristics of its back face".
          Unlike the modal case this changes during the game, in both
          directions, and it is a property of the permanent rather than of a
          choice made on the way in.
        - A **split card's own chosen half** (CR 709.3b) or an **adventurer
          card's Adventure half** (CR 715.3b), while `face_played` names one
          and the object is still on the stack - see `face_played`'s own
          docstring for why one field carries both.
        - The **front face** otherwise: CR 712.8a makes it the only face this
          card has anywhere but the battlefield or stack, and CR 712.8d makes
          it the same on the battlefield while the front face is up.

        `None` for an ordinary single-faced card, whose own top-level fields
        already *are* the up face - every caller must keep that fallback, or a
        single-faced permanent ends up with no characteristics at all.
        """
        if self.meld_result is not None:
            # CR 712.8g, CR 712.4c: meld cards "cannot be transformed or
            # converted", so this never competes with the `transformed`/
            # land-face branches below - it is checked first only for
            # clarity, not because of an ordering hazard. `Card` mirrors a
            # `CardFace`'s own fields (see `meld_result`'s docstring), so it
            # is handed back exactly as a real face would be.
            return self.meld_result
        if self.prepare_spell_face:
            # CR 722.3c: "Those characteristics become the copy's normal
            # characteristics" - this copy's own `Card.back_face` (the inset
            # "prepare spell") is read the same as any other face everywhere
            # off it, not only on the battlefield or stack, since the copy has
            # no other object to fall back to the way a transformed permanent
            # falls back to its front face off the battlefield.
            back_face = self.card.back_face
            if back_face is not None:
                return back_face
        land_face = self._land_face
        if land_face is not None:
            return land_face
        if self.transformed or (self.flipped and self.zone is Zone.BATTLEFIELD):
            back_face = self.card.back_face
            if back_face is not None:
                return back_face
        if (
            self.face_played is not None
            and self.card.layout in (Layout.SPLIT, Layout.ADVENTURE, Layout.MODAL_DFC)
            and self.zone is Zone.STACK
        ):
            # CR 712.8f: "While a modal double-faced spell is on the stack
            # ... it has only the characteristics of the face that's up" -
            # the face CR 712.11b let its caster choose; off the stack it is
            # its front face again (CR 712.8a).
            # CR 709.2: off the stack, a split card is "only one card" again -
            # both halves, not the one that was last cast. CR 715.4 says the
            # same for an adventurer card: "in every zone except the stack,
            # and while on the stack not as an Adventure, an adventurer card
            # has only its normal characteristics." Scoped to the stack the
            # way CR 709.3b and CR 715.3b are both worded ("while on the
            # stack"), so a resolved and graveyard-bound Wear // Tear is read
            # as the whole card once more, the same as before it was cast,
            # and a Bonecrusher Giant that resolved as a creature is a Giant.
            for face in self.card.card_faces or []:
                if face.name == self.face_played:
                    return face
        if self.card.layout is Layout.SPLIT and "Room" in self.card.subtypes:
            return self._room_face
        return self.card.front_face

    @property
    def _room_face(self) -> Any:
        """`up_face` for a permanent split card with a shared type line (a
        Room, "Unholy Annex // Ritual Chamber") anywhere but the stack.

        Off the battlefield, CR 709.4's combining default: `None`, which
        falls through to this object's own top-level fields - Scryfall's
        combined "Front // Back" values for a split card's `name`/`type_
        line` - and leaves every ability printed on either half unfiltered
        (`machines/triggers.triggered_abilities_on`'s `up_face_name` filter
        was built for a transform/MDFC's single active face and would
        otherwise drop every line not on the front half).

        On the battlefield (or entering it, CR 614.12's "as it would exist on
        the battlefield"), CR 709.5's two statics apply: "As long as this
        permanent doesn't have the 'left half unlocked' designation, it
        doesn't have the name, mana cost, or rules text of this object's left
        half" - and the same for the right. So:

        - one door unlocked (`unlocked_doors`, CR 709.5c): that half's own
          face, exactly as a single up face - its name, mana cost, rules text
          and abilities only (Ritual Chamber alone has no end-step trigger);
        - both unlocked: `None`, the combined card again (CR 709.4);
        - neither (CR 709.5d's "enters with neither unlocked designation"):
          `locked_room_face`, a face with only the shared type line (CR
          709.5a) and no name, mana cost or rules text - so no ability
          either, and an empty `up_face_name` every face filter matches
          nothing against.

        A Room entering from the stack is its cast half: `face_played` names
        it (the stack branch of `up_face` above already answered), or is
        `None` for the front half cast with CR 709.3's choice left at its
        default - CR 709.5d gives exactly that half its designation as it
        enters, so the front face is the answer here too.
        """
        if self.zone is not Zone.BATTLEFIELD and not self._entering_battlefield:
            return None
        faces = self.card.card_faces or []
        if self._entering_battlefield and self.zone is Zone.STACK:
            return self.card.front_face
        unlocked = [face for face in faces if face.name in self.unlocked_doors]
        if len(unlocked) == 1:
            return unlocked[0]
        if unlocked:
            return None
        return locked_room_face(self.card)

    @property
    def up_face_name(self) -> str | None:
        """The name of the face that is up, or None for a single-faced card.

        The key an ability is matched to its face by (`BaseAbility.face`):
        CR 712.8d/712.8e give a double-faced permanent only the characteristics
        of whichever face is up, and CR 109.3 lists abilities among an object's
        characteristics, so a line printed on the other face is not one this
        object has. `machines/triggers.py` and `Game.activated_abilities` both
        filter on it; `None` means "do not filter", since a single-faced card's
        every line is on the only face it has.
        """
        up_face = self.up_face
        return up_face.name if up_face is not None else None

    @property
    def off_battlefield_characteristics(self) -> Any:
        """CR 113.6c's "As long as `<this>` isn't on the battlefield, it's a
        ..." grant (`machines/layers.OffBattlefieldCharacteristics`), or
        `None` - on the battlefield, while entering it (CR 614.12, see
        `_entering_battlefield`), face down (CR 708.2) or with no
        characteristics at all (CR 406.3a), and for every object that prints
        no such ability."""
        if (
            self.zone is Zone.BATTLEFIELD
            or self._entering_battlefield
            or self.face_down_characteristics is not None
            or self.has_no_characteristics
        ):
            return None
        return self._off_battlefield_grant

    @property
    def _off_battlefield_grant(self) -> Any:
        """`off_battlefield_characteristics` whatever zone this is in."""
        from ..machines.layers import off_battlefield_characteristics

        return off_battlefield_characteristics(
            self.oracle_text, self.name, Supertype.LEGENDARY in self.supertypes
        )

    def types_as_a_spell(self, types: Iterable[Type]) -> tuple[Type, ...]:
        """`types` - a spell's own card types, read off `Card` or a cast face
        (CR 601.3e) by the caller - plus what CR 113.6c's off-battlefield
        grant adds. A spell is never on the battlefield, so the grant always
        applies to one, including when a caller asks about a spell after it
        has resolved into a permanent ("creature spells cast this turn")."""
        base = tuple(types)
        if self.face_down_characteristics is not None:
            return base
        grant = self._off_battlefield_grant
        return base if grant is None else _with_granted(base, grant.types)

    @property
    def types(self) -> tuple[Type, ...]:
        """`printed_types` plus, anywhere but the battlefield, CR 113.6c's
        off-battlefield grant (`off_battlefield_characteristics`, CR 205.1b's
        "in addition to its other types") - Grist, the Hunger Tide is a
        creature card in a graveyard and a creature spell on the stack."""
        return self._types_with(self.off_battlefield_characteristics)

    def _types_with(self, grant: Any) -> tuple[Type, ...]:
        printed = self.printed_types
        return printed if grant is None else _with_granted(printed, grant.types)

    @property
    def printed_types(self) -> tuple[Type, ...]:
        """This object's card types (CR 205.2a, CR 708.2).

        Read off `up_face`'s own type line when there is a face (CR 712.8d,
        712.8e, 712.8f), so a transformed Delver of Secrets is a Human Insect
        and a transformed Ajani, Nacatl Pariah is a Planeswalker rather than
        the Cat Warrior his front face prints. `Card.types` parses
        `front_type_line` only, which is the right answer for every
        single-faced card and the wrong one for a permanent showing any other
        face.
        """
        if self.has_no_characteristics:
            return ()  # CR 406.3a
        if self.face_down_characteristics is not None:
            return self.face_down_characteristics.types
        up_face = self.up_face
        printed = (
            tuple(types_of(up_face.type_line or ""))
            if up_face is not None
            else tuple(self.card.types)
        )
        if self._is_bestowed_object:
            # CR 702.103b: "it becomes an Aura enchantment". An Aura
            # enchantment is not a creature, which is the whole reason bestow
            # exists - the same card is a creature spell when hardcast and an
            # Aura spell when bestowed.
            without_creature = tuple(kind for kind in printed if kind is not Type.CREATURE)
            return without_creature + (
                (Type.ENCHANTMENT,) if Type.ENCHANTMENT not in printed else ()
            )
        return printed

    @property
    def subtypes(self) -> tuple[str, ...]:
        """This object's subtypes (CR 205.3, CR 708.2), changeling included.

        `printed_subtypes` plus, for an object with changeling, every creature
        type (CR 702.73a: "This ability works everywhere, even outside the
        game"; CR 604.3: a characteristic-defining ability functions in all
        zones). This is the reader for a card in a hand, library, graveyard,
        exile, on the stack or outside the game - a Goblin-spell cost
        reduction, "reveal an Elf card", "behold a Kithkin" - where no layer
        system runs. On the battlefield the same CDA is applied in layer 4
        instead (`machines/layers._changeling_effect`), which is where a later
        type-setting effect can override it (CR 613.3); a battlefield reader
        asks the computed board, never this.
        """
        return self._subtypes_with(self.off_battlefield_characteristics)

    def _subtypes_with(self, grant: Any) -> tuple[str, ...]:
        printed = self.printed_subtypes
        if grant is not None:
            printed = _with_granted(printed, grant.subtypes)
        if self.face_down_characteristics is None and has_changeling(self.oracle_text):
            return with_every_creature_type(self._types_with(grant), printed)
        return printed

    @property
    def printed_subtypes(self) -> tuple[str, ...]:
        """The subtypes on the type line (CR 205.3, CR 708.2). Face down, none.

        The same `up_face` read as `types` - a transformed Ajani is an Ajani
        planeswalker and no longer a Cat, which is exactly what his own back
        face's "+1/+1 counter on each Cat you control" has to be counted
        against. `machines/layers.printed_characteristics` starts layer 1 from
        this, so changeling's creature types arrive in layer 4, not here.
        """
        if self.has_no_characteristics:
            return ()  # CR 406.3a
        if self.face_down_characteristics is not None:
            return self.face_down_characteristics.subtypes
        up_face = self.up_face
        printed = (
            tuple(subtypes_of(up_face.type_line or ""))
            if up_face is not None
            else tuple(self.card.subtypes)
        )
        if self._is_bestowed_object and "Aura" not in printed:
            # CR 702.103b again: an *Aura* enchantment. CR 303.4 is what makes
            # that subtype mean anything - "Aura" is the enchantment subtype
            # the attachment rules are written against.
            return printed + ("Aura",)
        return printed

    @property
    def supertypes(self) -> tuple[Supertype, ...]:
        """This object's supertypes (CR 205.4, CR 708.2).

        Face down, CR 708.2 leaves it with no supertypes at all - "a 2/2
        creature with no text, no name, no subtypes, and no mana cost" is the
        whole of what it has, and CR 205.4 supertypes are not on that list.
        Otherwise the same `up_face` read as `types`: a back face may be
        legendary where the front is not (CR 712.8e), and the legend rule
        (CR 704.5j) has to see that.
        """
        if self.has_no_characteristics:
            return ()  # CR 406.3a
        if self.face_down_characteristics is not None:
            return ()
        up_face = self.up_face
        if up_face is not None:
            return tuple(supertypes_of(up_face.type_line or ""))
        return tuple(self.card.supertypes)

    @property
    def prototype_characteristics(self) -> "PrototypeCharacteristics | None":
        """The alternative mana cost, power and toughness this object has right
        now (CR 718.3b), or None when it was not cast prototyped or is face
        down (CR 708.2)."""
        if not self.prototyped or self.face_down_characteristics is not None:
            return None
        return prototype_of(self.oracle_text)

    @property
    def colors(self) -> tuple[Color, ...]:
        """This object's colors (CR 105.2, CR 202.2, CR 708.2).

        A back face prints no mana cost, so its colour comes from its colour
        indicator (CR 202.2f, CR 204.1) - Scryfall reports both `colors` and
        `color_indicator` on the face, and `colors` is already the answer.
        Face down, CR 708.2 leaves it colorless along with everything else it
        does not list.
        """
        if self.has_no_characteristics:
            return ()  # CR 406.3a
        if self.face_down_characteristics is not None:
            return ()
        prototype = self.prototype_characteristics
        if prototype is not None:
            return prototype.colors  # CR 718.3b
        up_face = self.up_face
        if up_face is not None and up_face.colors is not None:
            return tuple(up_face.colors)
        return tuple(self.card.colors or ())

    @property
    def keywords(self) -> tuple[str, ...]:
        """The keyword abilities this object has (CR 702, CR 708.2).

        A face-down permanent has "no text" (CR 702.37c), so it has none - which
        is what stops a face-down creature with flying flying. Disguise lists
        ward {2} (CR 702.168b), so that one keyword survives.

        `Card.keywords` is not per-face - Scryfall reports the whole card's
        keyword abilities regardless of which face prints one, so Delver of
        Secrets' printing lists Flying even though only Insectile Aberration,
        its back face, has it. CR 109.3 counts abilities among an object's
        characteristics and CR 712.8d/712.8e give a double-faced permanent only
        the characteristics of the face that is up, so on a card that *has*
        faces the printing's list is filtered down to the keywords actually
        printed on the up face - by the same line classifier that parses them
        anywhere else, rather than a second spelling of it. A single-faced card
        has one face and is left exactly as the printing reports it.
        """
        if self.has_no_characteristics:
            return ()  # CR 406.3a
        if self.face_down_characteristics is not None:
            return self.face_down_characteristics.keywords
        if self.meld_result is not None:
            # CR 712.8g: the melded permanent's own keywords, not this card's
            # printed ones - Hanweir Battlements prints only Meld, and the
            # permanent it becomes has Trample and Haste instead. A meld
            # result is a whole `Card`, not a `CardFace`, with no faces of
            # its own to filter by, so this is the "no faces" branch below,
            # just read off `meld_result` instead of `self.card`.
            return self._with_bestowed_enchant(tuple(self.meld_result.keywords))
        if not self.card.card_faces:
            if self.is_leveler:
                # CR 711.2a/b: a keyword printed in a level striation is one
                # the leveler has only within that band of level counters.
                from ..machines.abilities import keywords_in_lines, leveler_lines

                live = keywords_in_lines(
                    leveler_lines(self.oracle_text, self.counter_count(LEVEL_COUNTER)),
                    list(self.card.keywords),
                )
                return self._with_bestowed_enchant(
                    tuple(keyword for keyword in self.card.keywords if keyword.lower() in live)
                )
            return self._with_bestowed_enchant(tuple(self.card.keywords))
        # Imported here: `machines/` imports `models/`, so the reverse import
        # only resolves at call time.
        from ..machines.abilities import keywords_in_lines

        on_this_face = keywords_in_lines(self.oracle_text.split("\n"), list(self.card.keywords))
        return self._with_bestowed_enchant(
            tuple(keyword for keyword in self.card.keywords if keyword.lower() in on_this_face)
        )

    @property
    def _is_bestowed_object(self) -> bool:
        """CR 702.103b's window: bestowed, and on the stack or the battlefield.

        "As a spell cast bestowed is put onto the stack, it becomes an Aura
        enchantment ... and the permanent it becomes as it resolves will be a
        bestowed Aura permanent." Those are the only two zones the rule speaks
        about; `bestowed` is cleared on any other move anyway (`move_to`), so
        this is belt and braces rather than a second rule.
        """
        return self.bestowed and self.zone in (Zone.STACK, Zone.BATTLEFIELD)

    def _with_bestowed_enchant(self, keywords: tuple[str, ...]) -> tuple[str, ...]:
        """CR 702.103b's "and gains enchant creature", as a keyword (CR 702.5a)."""
        if not self._is_bestowed_object or "Enchant" in keywords:
            return keywords
        return keywords + ("Enchant",)

    @property
    def oracle_text(self) -> str:
        """This object's rules text (CR 708.2, CR 612.10). Face down, it is empty.

        Spliced text (CR 702.47c) is appended after the object's own, which is
        the order CR 612.10 states: "adding the rules text of the card with
        splice to the spell, **following** that spell's own rules text". That
        order is the whole of DDR#957 - Time Stop ends the turn first, and the
        spliced draw happens afterwards, in the cleanup step it lands in.
        """
        if self.has_no_characteristics:
            return ""  # CR 406.3a
        if self.face_down_characteristics is not None:
            return self.face_down_characteristics.oracle_text
        up_face = self.up_face
        own = up_face.oracle_text if up_face is not None else self.card.oracle_text
        if (
            up_face is None
            and own is None
            and self.card.layout is Layout.SPLIT
            and "Room" in self.card.subtypes
        ):
            # CR 709.4c: "A split card has ... each ability in the text box of
            # each half" - Scryfall prints a split card's text only per face.
            # Scoped to Rooms (a both-doors-unlocked Room on the battlefield,
            # CR 709.5), the same scope `_room_face` keeps.
            own = "\n".join(face.oracle_text or "" for face in self.card.card_faces or [])
        return "\n".join([own or "", *self.spliced_text]).strip("\n")

    @property
    def mana_cost(self) -> str | None:
        """This object's mana cost (CR 202.1, CR 708.2). Face down, there is none."""
        if self.has_no_characteristics:
            return None  # CR 406.3a
        if self.face_down_characteristics is not None:
            return self.face_down_characteristics.mana_cost
        prototype = self.prototype_characteristics
        if prototype is not None:
            return prototype.mana_cost  # CR 718.3b
        if self.flipped:
            front_face = self.card.front_face
            return front_face.mana_cost if front_face is not None else None  # CR 710.1c
        up_face = self.up_face
        if up_face is not None:
            return up_face.mana_cost or None
        return self.card.mana_cost

    @property
    def mana_value(self) -> float:
        """This object's mana value (CR 202.3, CR 708.2).

        Not simply the mana cost that is up. CR 202.3b: "the mana value of the
        back face of a nonmodal double-faced permanent or spell's back face is
        calculated as though it had the mana cost of its front face", and
        CR 712.8e repeats it as the one exception to a transformed permanent
        having only its back face's characteristics - Insectile Aberration
        prints no mana cost but its mana value is still 1, not 0. Scryfall's
        top-level `cmc` is already the front face's for a `transform` card, so
        it is what a transformed permanent reports.

        A modal double-faced permanent played for its land face is the other
        way round (CR 712.8f, CR 202.3a): that face's own mana cost - none - is
        what counts, giving 0 rather than the spell face's `cmc`. CR 708.2
        gives a face-down permanent no mana cost at all, so 0 by CR 202.3a.
        """
        if self.has_no_characteristics or self.face_down_characteristics is not None:
            # CR 406.3a / CR 708.2: no mana cost, so CR 202.3a says 0.
            return 0.0
        prototype = self.prototype_characteristics
        if prototype is not None:
            from .mana import ManaCost

            return float(ManaCost.parse(prototype.mana_cost).converted)  # CR 718.3b
        if self.meld_result is not None and self.meld_combined_mana_value is not None:
            # CR 202.3c/712.8g: the *sum* of both cards' own front-face mana
            # values - not `self.meld_result.cmc`, which is the combined back
            # face's own printed value and, per CR 712.8b, means nothing off
            # the battlefield to begin with.
            return self.meld_combined_mana_value
        land_face = self._land_face
        if land_face is not None:
            from .mana import ManaCost

            return float(ManaCost.parse(land_face.mana_cost or "").converted)
        if self.prepare_spell_face:
            # Unlike a transformed back face (CR 202.3b's stated exception),
            # CR 722.3c gives this copy the prepare spell's characteristics as
            # its *normal* characteristics outright, with no "calculated as
            # though" carve-back to the front face's cost - so this reads the
            # inset face's own mana cost, the same as `mana_cost` above does.
            back_face = self.card.back_face
            if back_face is not None:
                from .mana import ManaCost

                return float(ManaCost.parse(back_face.mana_cost or "").converted)
        return self.card.cmc

    @property
    def is_permanent(self) -> bool:
        """True if this card stays on the battlefield once it resolves."""
        return bool(set(self.types) & PERMANENT_TYPES)

    @property
    def is_creature(self) -> bool:
        return Type.CREATURE in self.types

    @property
    def is_suspended(self) -> bool:
        """CR 702.62b: "A card is 'suspended' if it's in the exile zone, has
        suspend, and has a time counter on it."

        Kept as one predicate on `CardState` itself, not the machine that
        marks it (`machines.casting.MarkedExile.suspend`) or the one that
        reads it back (`machines.keywords`), so both - and any future
        ability that prints its own "Activate only if this card is
        suspended" restriction (CR 602.5b), Greater Gargadon's own second
        ability being the pool's example - ask the identical question rather
        than re-deriving it.

        **Three clauses, and `ExileMarker.SUSPENDED` is not one of them.**
        This used to read the marker instead of "has suspend", which is
        narrower than the rule: CR 702.62b asks what the card *is* and where
        it *is*, not which action put it there. Suspended Sentence's own last
        line - "Exile Suspended Sentence with three time counters on it" -
        makes a suspended card with no suspend special action anywhere in
        sight, and so would any future effect that puts a time counter on an
        exiled card with suspend. Reading the marker also made the whole
        keyword's second ability unreachable for such a card, since
        `Game.emit` offers a source on this predicate.

        "Has suspend" is read off Scryfall's own `keywords` list, the same
        way `machines/keywords.has_rebound` and `has_persist` read theirs,
        rather than by searching the oracle text - Lotus Bloom's only
        matching string is the reminder text in parentheses, which is not an
        ability at all.
        """
        if self.zone is not Zone.EXILE:
            return False
        if not self.has_suspend:
            return False
        return self.counter_count(Counter.TIME) > 0

    @property
    def has_suspend(self) -> bool:
        """CR 702.62b's middle clause, "has suspend": printed on the card
        (Scryfall's `keywords`, the same read `machines/keywords.has_suspend`
        makes) or granted to this object by a resolved effect - Delay's and
        Suspend's own "If it doesn't have suspend, it gains suspend." -
        which `machines/effects.grant_suspend` writes onto
        `granted_ability_texts` as the bare keyword line, the same place a
        granted evoke lives, so `machines/keywords.
        granted_keyword_triggered_abilities` writes out CR 702.62a's two
        exile-zone triggers for it exactly as it does for a printed one."""
        if any(keyword.lower() == "suspend" for keyword in self.card.keywords):
            return True
        return any(_is_suspend_line(line) for line in self.granted_ability_texts)

    def is_summoning_sick(self, game: Any = None) -> bool:
        """Whether the summoning-sickness restriction actually applies here.

        `summoning_sick` is the raw fact - this object has not been under its
        controller's control continuously since their most recent turn began
        (CR 508.1a) - and it is set on every permanent, creature or not. The
        restriction it feeds binds creatures only: CR 302.6 stops "a creature's
        activated ability with the tap symbol or the untap symbol in its
        activation cost" from being activated, and CR 602.5a and CR 508.1a
        apply the same control-duration test to a creature's attacking and to
        its {T}/{Q} abilities (haste lifts it, CR 702.10b). A land reports
        False here even the turn it arrives, but it keeps the raw flag, because
        a non-creature permanent that becomes a creature later in the turn is
        restricted from the moment it entered - CR 302.6 asks how long the
        permanent has been controlled, not how long it has been a creature.

        Whether it *is* a creature right now has to be read off the computed
        board (CR 613.5), not the printed type line - `self.is_creature` only
        knows the card's own text, so an artifact a continuous effect turned
        into a creature this turn (The Filigree Sylex after Karn, the Great
        Creator's +1) would otherwise report `is_creature` False and this
        property would wrongly clear the restriction. Pass the `Game` so this
        can ask `characteristics_of`; without one, this falls back to the
        printed type line, matching `machines/cost.py`'s `can_tap_for_mana`.

        Only a battlefield permanent has computed characteristics to ask about
        (CR 613.5 applies to permanents), and `Game.characteristics_of` refuses
        a card that is not on the board, so a card in any other zone takes the
        printed-text branch even when a `Game` is passed.
        """
        if game is not None and self.zone is Zone.BATTLEFIELD:
            is_creature = game.characteristics_of(self).is_creature
        else:
            is_creature = self.is_creature
        return self.summoning_sick and is_creature

    @property
    def toughness(self) -> int | None:
        """Toughness as a number, or None for `*` and other non-numeric values.

        Printed toughness plus what its own counters do to it (CR 122.1a). That
        is not the whole of CR 613 - `machines/layers.py` is the authority once
        other continuous effects are in play - but it is what makes a creature
        with enough -1/-1 counters die to CR 704.5f without the state-based
        action check having to compute the board.

        A `transform` or `modal_dfc` card leaves the top-level `toughness`
        null and puts each face's own value on `card_faces` instead, so
        `up_face` is read first (CR 712.8a, 712.8d, 712.8f) - without it, a
        double-faced creature would have no toughness at all rather than its
        printed one, and CR 704.5g's lethal-damage check would never fire.

        Bound to a game (`bind_to_game`), a permanent on the battlefield
        answers with the computed toughness instead - the whole of CR 613,
        including the characteristic-defining ability in layer 7a that is the
        only thing giving a printed `*` a number at all (CR 604.3, CR 613.4a).
        """
        computed = self.computed_characteristics
        if computed is not None and computed.toughness is not None:
            return computed.toughness
        if self.zone is not Zone.BATTLEFIELD and self.last_known_toughness is not None:
            return self.last_known_toughness  # CR 608.2h, as for `power`
        return self.printed_toughness

    @property
    def printed_toughness(self) -> int | None:
        """`toughness` with neither the layer engine nor CR 608.2h's snapshot
        consulted - the printing plus counters, and nothing else."""
        if self.has_no_characteristics:
            return None  # CR 406.3a
        if self.face_down_characteristics is not None:
            # CR 708.2: face down, 2 is what its toughness *is*; the counters
            # still apply on top, in sublayer 7c (CR 613.4c).
            base = self.face_down_characteristics.toughness
            return base + self.counters.power_toughness_modifier
        grant = self.off_battlefield_characteristics
        if grant is not None and grant.toughness is not None:
            return grant.toughness + self.counters.power_toughness_modifier  # CR 113.6c
        prototype = self.prototype_characteristics
        if prototype is not None:
            return prototype.toughness + self.counters.power_toughness_modifier  # CR 718.3b
        up_face = self.up_face
        printed = _as_number(up_face.toughness if up_face is not None else self.card.toughness)
        return None if printed is None else printed + self.counters.power_toughness_modifier

    @property
    def power(self) -> int | None:
        """Power as a number, or None for `*` and other non-numeric values.

        A `transform` or `modal_dfc` card leaves the top-level `power` null
        and puts each face's own value on `card_faces` instead, so `up_face`
        is read first for the same reason as `toughness`.

        Printed power plus its counters (CR 122.1a), for the same reason as
        `toughness` - and the computed power (CR 613.5) instead, once
        `bind_to_game` has given this object a board to ask. Combat damage is
        assigned equal to power (CR 510.1a), so this is what an attacking or
        blocking creature deals.
        """
        computed = self.computed_characteristics
        if computed is not None and computed.power is not None:
            return computed.power
        if self.zone is not Zone.BATTLEFIELD and self.last_known_power is not None:
            # CR 608.2h's last known information, for an effect that has to
            # ask about a permanent which is no longer one. See
            # `_remember_last_known_power_toughness`: the snapshot exists only
            # for an object that has actually left the battlefield, so nothing
            # that never was a permanent is affected.
            return self.last_known_power
        return self.printed_power

    @property
    def printed_power(self) -> int | None:
        """`power` with neither the layer engine nor CR 608.2h's snapshot
        consulted - the printing plus counters, and nothing else."""
        if self.has_no_characteristics:
            return None  # CR 406.3a
        if self.face_down_characteristics is not None:
            base = self.face_down_characteristics.power
            return base + self.counters.power_toughness_modifier
        grant = self.off_battlefield_characteristics
        if grant is not None and grant.power is not None:
            return grant.power + self.counters.power_toughness_modifier  # CR 113.6c
        prototype = self.prototype_characteristics
        if prototype is not None:
            return prototype.power + self.counters.power_toughness_modifier  # CR 718.3b
        up_face = self.up_face
        printed = _as_number(up_face.power if up_face is not None else self.card.power)
        return None if printed is None else printed + self.counters.power_toughness_modifier

    @property
    def lethal_damage_remaining(self) -> int | None:
        """How much more damage it takes to be lethal (CR 510.1c).

        Damage already marked counts, which is what makes the second combat
        damage step assign correctly after first strike has landed. None when
        toughness is not a number.
        """
        threshold = self.lethal_threshold
        return None if threshold is None else threshold - self.damage

    @property
    def lethal_threshold(self) -> int | None:
        """The number damage is measured against to be lethal: toughness
        (CR 120.6), or power while an effect says lethal damage is determined
        by power instead (`LETHAL_BY_POWER_TEXT`)."""
        computed = self.computed_characteristics
        if computed is not None and LETHAL_BY_POWER_TEXT in computed.abilities:
            return self.power
        return self.toughness

    @property
    def has_lethal_damage(self) -> bool:
        """True if a state-based action destroys this creature (CR 704.5g, 704.5h).

        CR 704.5g is the arithmetic one: toughness greater than 0 and marked
        damage at least equal to it. CR 704.5h is deathtouch's, and needs no
        arithmetic at all - "if a creature has toughness greater than 0, and
        it's been dealt damage by a source with deathtouch since the last time
        state-based actions were checked, that creature is destroyed."

        Both are answered here because `Game.check_state_based_actions` reads
        this one property and dispatches nothing else - see
        `docs/engine-coverage.md`.
        """
        toughness = self.toughness
        if toughness is None or toughness <= 0:
            return False
        threshold = self.lethal_threshold
        if threshold is None:
            return self.dealt_deathtouch_damage
        if threshold != toughness and self.damage <= 0:
            # CR 704.5g needs damage marked on it: a power-measured 0 is no
            # exception.
            return self.dealt_deathtouch_damage
        return self.damage >= threshold or self.dealt_deathtouch_damage

    # -- attaching (CR 701.3) ----------------------------------------------

    @property
    def attached_to(self) -> UUID | None:
        """The card this is attached to, or None (CR 301.5a).

        The narrow read of `attachment` for the common case: the id when the
        attachment names a card, None when it is attached to nothing. An Aura
        attached to a player is still attached - `is_attached` - but names no
        card, so this returns None for it.
        """
        if self.attachment is not None and self.attachment.is_card:
            return self.attachment.card_id
        return None

    @property
    def phased_out(self) -> bool:
        """Whether this permanent is phased out (CR 702.26b)."""
        return self.phased_out_under is not None

    @property
    def is_attached(self) -> bool:
        """Whether this permanent is attached to something (CR 301.5a)."""
        return self.attachment is not None

    def attach_to(self, target: "CardState | Any") -> None:
        """Attach this permanent to another object or player (CR 701.3a).

        "To attach an Aura, Equipment, or Fortification to an object or player
        means to take it from where it currently is and put it onto that object
        or player. If something is attached to a permanent on the battlefield,
        it becomes attached to the new object or player and becomes unattached
        from the previous one" - which is why this overwrites rather than adds.

        `target` is a `CardState` for the common case, or anything
        `TargetRef.coerce` reads as a player (a `Player`, or a bare username) -
        an "Enchant player" Aura needs the latter, and `attachment` is already
        typed to carry either (CR 115.1).
        """
        if isinstance(target, CardState) and target.id == self.id:
            raise ValueError(f"{self.name} cannot be attached to itself")
        self.attachment = TargetRef.coerce(target)

    def unattach(self) -> None:
        """Move this permanent away from whatever it was on (CR 701.3d).

        "To 'unattach' an Equipment from a creature means to move it away from
        that creature so the Equipment is on the battlefield but is not
        equipping anything."

        CR 702.103f: "If a bestowed Aura becomes unattached, it ceases to be
        bestowed." So a bestowed permanent that comes off its creature stops
        being an Aura here and is the creature its card prints again - which is
        the whole point of bestow, and why this is the one place `bestowed` is
        cleared while the object stays on the battlefield.
        """
        self.attachment = None
        self.bestowed = False

    def mark_damage(self, amount: int) -> int:
        """Mark damage on this creature. It stays until cleanup."""
        if amount < 0:
            raise ValueError("cannot mark negative damage")
        self.damage += amount
        return self.damage

    @property
    def name(self) -> str:
        """This object's name (CR 201.1, CR 708.2).

        A face-down permanent has "no name" (CR 702.37c), which is the empty
        string here - it is not the card's name kept quiet, and CR 704.5j's
        legend rule and every "another creature named ..." depend on the
        difference.

        Reads `up_face` - the same face `oracle_text`, `power`, `toughness`
        and `mana_cost` already read - rather than `card.name`, Scryfall's
        combined "Front // Back" string. CR 201.1 puts a name on each face
        individually, and CR 712.8a/712.8d/712.8f are unanimous that a
        double-faced object - in every zone, not just the battlefield - has
        only the characteristics of whichever face is up; the combined string
        is a database convenience for referring to the physical card, never a
        characteristic the rules hand out. An earlier pass at this exact fix
        was reverted because it broke roughly a dozen scenario assertions that
        had keyed lookups (`scenario.creature`, `scenario.find`,
        `scenario.stack_names`) off the combined name for a double-faced card
        sitting on its front face - those assertions were encoding the bug,
        not the rule, and have been corrected to name the front face alone.
        """
        if self.has_no_characteristics:
            return ""  # CR 406.3a
        if self.face_down_characteristics is not None:
            return self.face_down_characteristics.name
        land_face = self._land_face
        if land_face is not None:
            return land_face.name
        up_face = self.up_face
        if up_face is not None:
            return up_face.name
        return self.card.name

    @property
    def untapped(self) -> bool:
        return not self.tapped

    @property
    def face_down(self) -> bool:
        return not self.face_up

    def tap(self) -> None:
        """Tap this card. Tapping something already tapped is not a legal cost."""
        if self.zone is not Zone.BATTLEFIELD:
            raise ValueError(f"only battlefield cards tap, {self.name} is in {self.zone}")
        if self.tapped:
            raise ValueError(f"{self.name} is already tapped")
        self.tapped = True
        self._note_tapped()

    def _note_tapped(self) -> None:
        """Tell the bound game this permanent became tapped (CR 701.26a), for
        CR 603.2c's "one or more ... become tapped" batch
        (`Game.note_permanent_tapped`). Unbound, there is nobody to tell."""
        note = getattr(self._board_source, "note_permanent_tapped", None)
        if note is not None:
            note(self)

    def tap_if_untapped(self) -> bool:
        """Tap this card if it is not already tapped; otherwise leave it be.

        CR 701.26a: "To tap a permanent, turn it sideways from an upright
        position. Only untapped permanents can be tapped." That is the whole
        of it - a resolving spell or ability that says "tap" a permanent
        already tapped simply does nothing to its tap status, with no error
        and no event, and the rest of the sentence still applies (Frost
        Breath's "doesn't untap" and a stun counter both still land on an
        already-tapped target). `tap` stays strict for a cost (CR 118.3) and
        for declaring an attacker (CR 508.1f), where an already-tapped
        permanent is illegal rather than silently skipped.

        Battlefield-only, like `tap`. Returns whether it actually tapped.
        """
        if self.zone is not Zone.BATTLEFIELD:
            raise ValueError(f"only battlefield cards tap, {self.name} is in {self.zone}")
        if self.tapped:
            return False
        self.tapped = True
        self._note_tapped()
        return True

    @property
    def cant_become_untapped(self) -> bool:
        """Whether an effect says this permanent "can't become untapped"
        (Frozen in Ice, Spider-Woman, Secret Agent) - read off the computed
        board (CR 613.5), where the layer-6 effect puts
        `CANT_BECOME_UNTAPPED_TEXT`. False for an object no game has bound."""
        computed = self.computed_characteristics
        return computed is not None and CANT_BECOME_UNTAPPED_TEXT in computed.abilities

    @property
    def cant_have_counters_put_on_it(self) -> bool:
        """Whether an effect says this permanent "can't have counters put on
        it" (Melira's Keepers, Tatterkite, an enchanted creature under
        Blossombind) - read off the computed board (CR 613.5) the identical
        way `cant_become_untapped` is, where the layer-6 effect puts
        `CANT_HAVE_COUNTERS_TEXT`. False for an object no game has bound, or
        one not on the battlefield (a card the effect no longer reaches)."""
        computed = self.computed_characteristics
        return computed is not None and CANT_HAVE_COUNTERS_TEXT in computed.abilities

    def untap(self, *, exert_applies: bool = True) -> None:
        """Untap this card, unless it was exerted (CR 701.43a-b).

        CR 701.43a is about one moment only: an exerted permanent "does not
        untap during your next untap step". The flag expires as that step
        happens (CR 701.43b), so it is cleared here whether or not the untap
        went through - which is what stops one exert skipping two untap steps.

        `exert_applies=False` is for a caller that is *not* the untap step: an
        effect or a `{Q}` cost that untaps a permanent does so regardless of
        exert, and leaves the exert in place for the step it was aimed at.

        A stun counter is checked here and **not** through `exert_applies`,
        because CR 122.1d is not the untap step's business at all: "One or
        more stun counters on a permanent create a single replacement effect
        that stops the permanent from untapping. That effect is 'If a
        permanent with a stun counter on it would become untapped, instead
        remove a stun counter from it.'" Every route to untapping is "would
        become untapped" - the untap step, an effect, a `{Q}` cost - so the
        check sits at the one place all of them pass through, and one counter
        is spent per attempt rather than per turn.

        It is checked *after* exert for the same reason exert is checked
        first at all: an exerted permanent's untap never happens, so there is
        no "would become untapped" event for a stun counter to replace, and
        spending one there would burn a counter on an untap that was already
        called off.

        It is also checked *after* an "already untapped" no-op, for the same
        reason: CR 701.26b, "Only tapped permanents can be untapped." A
        permanent that is not tapped was never going to untap, so - exactly
        like the exerted case just above - there is no "would become
        untapped" event for CR 122.1d to replace, and no counter is spent
        finding that out.
        """
        if exert_applies and self.exerted:
            self.exerted = False
            return
        if not self.tapped:
            return  # CR 701.26b: nothing to untap, so nothing "would become untapped"
        if self.cant_become_untapped:
            # Frozen in Ice's "can't become untapped": every route to
            # untapping is refused, the untap step's and an effect's alike -
            # and ahead of a stun counter, which only replaces an untap that
            # could have happened (CR 122.1d).
            return
        if self.counters[Counter.STUN] > 0:
            self.remove_counters(Counter.STUN, 1)  # CR 122.1d
            return
        self.tapped = False

    @property
    def face_it_would_transform_into(self) -> Any:
        """The face `transform` would turn this permanent onto, or None.

        The back face while the front is up, the front face while
        `transformed` is set - CR 701.27a is "turn it over so that its other
        face is up", and "the other face" is the whole of the choice. `None`
        for anything with fewer than two faces, which CR 701.27c and CR 712.9
        both refuse for.
        """
        faces = self.card.card_faces or []
        if len(faces) < 2:
            return None
        # A modal permanent that entered with its back face up (CR 712.12,
        # CR 712.13) turns over onto its front.
        return faces[0] if self.transformed or self.land_face_played else faces[1]

    def transform(self, *, day_night: bool = False) -> None:
        """Turn this permanent over so its other face is up (CR 701.27a).

        `day_night` marks the transform daybound or nightbound itself performs
        (`machines/keywords.transform_for_day_night`). Every other transform of
        a permanent with either keyword does nothing: CR 702.145b and CR
        702.145e each include "This permanent can't transform except due to its
        daybound [nightbound] ability."

        Only a double-faced card can transform (CR 712.9: "Only permanents
        represented by double-faced tokens and double-faced cards that are not
        meld cards can transform or convert"); asking anything else to does
        nothing, which is what CR 701.27c says - "If a spell or ability
        instructs a player to transform a permanent that isn't represented by
        a double-faced token or a double-faced card, nothing happens."

        The second refusal is about the face on the *other* side.
        CR 701.27d: "If a spell or ability instructs a player to transform a
        permanent, and the face that permanent would transform into is an
        instant or sorcery face nothing happens." CR 712.10 states the same
        for transform and convert together. A modal double-faced permanent
        whose back face is an instant - Flamescroll Celebrant // Revel in
        Silence - is the shape that needs it: it has two faces, so the
        card-faces check above lets it through, and without this it would end
        up an Instant sitting on the battlefield.

        Both are "nothing happens", not an error: that is what lets Moonmist
        say "transform all Humans" and sweep a board of mixed permanents
        without the caller having to filter it first.
        """
        if not day_night and self.zone is Zone.BATTLEFIELD:
            from ..machines.keywords import is_day_night_bound

            if is_day_night_bound(self, self._board_source):
                return  # CR 702.145b, CR 702.145e
            from ..machines.attached_restrictions import attached_transform_refusal

            if (
                self._board_source is not None
                and attached_transform_refusal(self._board_source, self) is not None
            ):
                return  # CR 101.2: "can't transform" beats the instruction to
        if self.zone is Zone.BATTLEFIELD and self._board_source is not None:
            from ..machines.transform_prohibitions import transform_is_prevented

            if transform_is_prevented(self._board_source, self):
                return  # a "can't transform" static (CR 701.27a, CR 701.28f)
        target = self.face_it_would_transform_into
        if target is None:
            return  # CR 701.27c, CR 712.9
        target_types = types_of(target.type_line or "")
        if Type.INSTANT in target_types or Type.SORCERY in target_types:
            return  # CR 701.27d, CR 712.10
        if self.land_face_played is not None:
            self.land_face_played = None
        else:
            self.transformed = not self.transformed
        self.times_transformed += 1

    def flip(self) -> None:
        """Flip this permanent (CR 710): its bottom half's characteristics
        apply from now on (CR 710.1b, CR 710.2).

        Only a flip card on the battlefield can flip; anything else, or a
        permanent already flipped (CR 710.4: one-way), is left alone - the
        same "nothing happens" CR 701.27c gives a transform of a card that
        cannot.
        """
        if self.zone is Zone.BATTLEFIELD and self.card.layout is Layout.FLIP:
            self.flipped = True

    def turn_face_up(self) -> None:
        """Turn this object face up, restoring the card's own characteristics.

        CR 702.37e: "The morph effect on it ends, and it regains its normal
        characteristics." CR 708.8 says the same generally: "As a face-down
        permanent is turned face up, its copiable values revert to its normal
        copiable values."

        Turning something face up that already is does nothing - the rules have
        no such action, and there is nothing to undo.

        CR 701.40a: a manifested permanent is one "for as long as it remains
        face down" - `manifested` ends here too, the same way `701.58a` will
        for a cloaked one once that keyword action exists.
        """
        self.face_up = True
        self.face_down_characteristics = None
        self.manifested = False

    def turn_face_down(self, characteristics: "FaceDownCharacteristics | None" = None) -> None:
        """Turn this object face down (CR 708.2, CR 708.2a).

        `characteristics` is what the ability or rule that allowed this listed -
        CR 702.37c's set for morph, CR 702.168b's for disguise.

        Passing none applies CR 708.2a's default *only on the stack or the
        battlefield*: "If a face-up permanent is turned face down by a spell or
        ability that doesn't list any characteristics for that object, it becomes
        a 2/2 face-down creature with no text, no name, no subtypes, and no mana
        cost." CR 708.2 is about "face-down spells and face-down permanents", and
        a card turned face down in another zone is neither - a foretold card
        (CR 702.143a) or a hideaway card (CR 702.75a) is face down in exile as
        hidden information and keeps every characteristic it has.

        CR 708.2b: "A face-down permanent can't be turned face down. If a spell
        or ability attempts to turn a face-down permanent face down, nothing
        happens and that effect doesn't change any of its characteristics or
        their copiable values."
        """
        if self.zone is Zone.BATTLEFIELD and self.face_down:
            return  # CR 708.2b
        self.face_up = False
        if characteristics is not None:
            self.face_down_characteristics = characteristics
        elif self.zone in (Zone.BATTLEFIELD, Zone.STACK):
            self.face_down_characteristics = FaceDownCharacteristics()  # CR 708.2a

    def remember_last_known_power_toughness(self) -> None:
        """Take CR 608.2h's snapshot while this object is still a permanent.

        Called by `Game._note_left_battlefield`, at the one moment every route
        off the battlefield already agrees on: the permanent is still in
        `Game.battlefield`, so the layer engine still answers for it. It
        cannot be taken from `move_to`, which runs after the permanent has
        been taken out of the zone and where CR 613.5 therefore has nothing
        left to say about it.

        Only the battlefield is snapshotted: it is the one zone where the
        answer can be anything other than the printing, and the one an effect
        looking back at a creature that "was sacrificed" or "died" is looking
        back at. `move_to` clears the snapshot on any move that does *not*
        start on the battlefield - CR 400.7 makes what arrives a new object
        with "no memory of, or relation to, its previous existence", so a card
        that has moved on from the graveyard, or has come back, must not still
        be answering with what it was on the battlefield two zones ago.

        Only what a *continuous effect* was contributing is recorded, which is
        why each half is compared against `printed_power`/`printed_toughness`
        and left `None` when they agree. The printing does not change on a
        zone change, so it needs no snapshot to survive one; the
        counters deliberately do not survive it (CR 122.2: "counters on an
        object are not retained if that object moves from one zone to another
        ... they simply cease to exist"), and a card in a graveyard reading
        back the +1/+1 counters it died with would be wrong. What is left is
        exactly the gap: an effect from a static ability (CR 604.2) or a
        resolved one (CR 611.2) stops applying the instant the permanent is
        not a permanent, and nothing else remembers it.

        `computed_characteristics` is the whole of CR 613, and answers `None`
        for an unbound `CardState` - which then has no continuous effect on it
        to record.
        """
        computed = self.computed_characteristics
        self._abilities_as_it_left = None if computed is None else tuple(computed.abilities)
        power = None if computed is None else computed.power
        toughness = None if computed is None else computed.toughness
        self.last_known_power = None if power == self.printed_power else power
        self.last_known_toughness = None if toughness == self.printed_toughness else toughness
        # The same snapshot for the qualities an ability's source is judged by
        # once it has gone (CR 608.2b, CR 702.11d) - recorded only where a
        # continuous effect made them differ from the printing.
        colors = None if computed is None else tuple(computed.colors)
        types = None if computed is None else tuple(computed.types)
        subtypes = None if computed is None else tuple(computed.subtypes)
        self.last_known_colors = None if colors == self.colors else colors
        # Compared against what the object will answer *off* the battlefield,
        # CR 113.6c's grant included: a Grist that was only a planeswalker
        # here is a creature card in the graveyard, and CR 603.10a's look-back
        # has to see the planeswalker.
        grant = self._off_battlefield_grant
        self.last_known_types = None if types == self._types_with(grant) else types
        self.last_known_subtypes = None if subtypes == self._subtypes_with(grant) else subtypes
        # CR 608.2h for "the sacrificed creature's mana value": a copy effect
        # (CR 707.2) is the one thing that makes it differ from the card's own.
        mana_value = None if computed is None else computed.mana_value
        self.last_known_mana_value = None if mana_value == self.mana_value else mana_value
        self.last_known_attachments = self._attachments_now()

    def last_known_power_toughness(self) -> tuple[int | None, int | None]:
        """Power and toughness as CR 608.2h reads them for an effect that
        looks at this object after it left the battlefield (CR 113.7a).

        The `last_known_*` snapshot keeps only what a continuous effect
        contributed (see `remember_last_known_power_toughness`), and CR 122.2
        ended the counters, which `last_known_counters` recorded. Neither
        alone is the answer: the snapshot when one was taken (it already
        includes the counters, being the computed value), otherwise the
        printing plus the counters it left with. `power`/`toughness` stay
        counter-free off the battlefield on purpose - a card in the graveyard
        is a 0/0 Hangarback Walker, not a 4/4 one (CR 122.2).

        On the battlefield, or for an object that never left it, this is just
        `power`/`toughness`.
        """
        if self.zone is Zone.BATTLEFIELD or not self.last_left_the_battlefield:
            return self.power, self.toughness
        modifier = self.last_known_counters.power_toughness_modifier
        power = self.last_known_power
        if power is None and self.printed_power is not None:
            power = self.printed_power + modifier
        toughness = self.last_known_toughness
        if toughness is None and self.printed_toughness is not None:
            toughness = self.printed_toughness + modifier
        return power, toughness

    def _attachments_now(self) -> tuple[AttachmentSnapshot, ...]:
        """Every permanent attached to this one right now, as the computed
        board sees it (CR 613.5) - `last_known_attachments`' snapshot."""
        game = self._board_source
        if game is None:
            return ()
        snapshots = []
        for permanent in getattr(game, "battlefield", ()):
            if permanent.attached_to != self.id or permanent is self:
                continue
            chars = permanent.computed_characteristics
            snapshots.append(
                AttachmentSnapshot(
                    card_id=permanent.id,
                    controller=permanent.controller,
                    types=tuple(permanent.types if chars is None else chars.types),
                    subtypes=tuple(permanent.subtypes if chars is None else chars.subtypes),
                )
            )
        return tuple(snapshots)

    @property
    def granted_as_it_left(self) -> tuple[str, ...]:
        """See `_granted_as_it_left`."""
        return self._granted_as_it_left

    def note_departure_epoch(self, epoch: int) -> None:
        """Stamp the batch of simultaneous events this object left the
        battlefield in (`Game._note_left_battlefield`)."""
        self._left_in_epoch = epoch

    def left_battlefield_in(self, epoch: int) -> bool:
        """Whether this object left the battlefield in batch `epoch` - for CR
        603.10a, whether it is looking back at an event it was part of."""
        return self._left_in_epoch is not None and self._left_in_epoch == epoch

    @property
    def last_left_the_battlefield(self) -> bool:
        """Whether this object's last zone change started on the battlefield,
        so the `last_known_*` snapshot describes it as a permanent (CR
        608.2h, CR 113.7a). `last_known_keywords` is that marker: always a
        tuple once `Game._note_left_battlefield` stamps it, and cleared by
        `move_to` on any move that does not start there (CR 400.7). False for
        a card that never was a permanent - a creature card discarded to pay
        its own cost was a creature card, never a creature (CR 109.2)."""
        return self.zone is not Zone.BATTLEFIELD and self.last_known_keywords is not None

    @property
    def abilities_as_it_left(self) -> tuple[str, ...] | None:
        """See `_abilities_as_it_left`."""
        return self._abilities_as_it_left

    def move_to(self, zone: Zone, *, place_intrinsic_counters: bool = True) -> None:
        """Move to another zone, resetting the state a card loses on the way.

        A card leaving the battlefield becomes a new object, so it arrives
        untapped and face up.

        `place_intrinsic_counters=False` is `Game.enter_the_battlefield`'s
        route: the intrinsic entering counters (`intrinsic_entering_counters`)
        are replacement effects (CR 614.1c) whose counters are put on through
        `Game.add_counters` instead (CR 122.6, CR 616.1g), so Doubling Season,
        Vorinclex and Solemnity see them. Every other caller has no `Game`
        to ask and writes them directly.

        Counters go either way (CR 122.2): "counters on an object are not
        retained if that object moves from one zone to another. The counters
        are not 'removed'; they simply cease to exist." A Walking Ballista that
        dies with four +1/+1 counters comes back off a Raise Dead as a 0/0.
        The counters are dropped by rebinding rather than by emptying the
        object, so anything holding the old `Counters` - a cost rewind, say -
        still holds what was there.
        """
        # CR 400.7: every zone change is a new object, whatever the previous
        # one carried. `id` stays put (this engine mutates rather than
        # replaces), so this is what tells a round trip apart from a card
        # that simply stayed put - see `DelayedTrigger.expected_stamp`.
        origin = self.zone
        if origin is not Zone.BATTLEFIELD:
            # CR 400.7: a move that did not start on the battlefield is a new
            # object with "no memory of, or relation to, its previous
            # existence", so CR 608.2h's snapshot of what continuous effects
            # were doing to it as a permanent stops being about this object.
            # The battlefield case is stamped by `Game._note_left_battlefield`
            # instead - see `remember_last_known_power_toughness` for why it
            # cannot be taken from here.
            self.last_known_power = None
            self.last_known_toughness = None
            self.last_known_mana_value = None
            self.last_known_colors = None
            self.last_known_types = None
            self.last_known_subtypes = None
            self.last_known_keywords = None
            self.last_known_attacking = False
            self.last_known_attachments = ()
            self._abilities_as_it_left = None
        elif zone is not Zone.BATTLEFIELD:
            # CR 702.171b, CR 701.60a, CR 702.112b: saddled, suspected and
            # renowned each last until the permanent leaves the battlefield,
            # and what arrives anywhere else is a new object (CR 400.7).
            self.saddled = False
            self.saddled_by = ()
            self.suspected = False
            self.renowned = False
            self.paired_with = None  # CR 702.95e
            self.has_dealt_damage = False  # CR 400.7
            self.solved = False  # CR 719.3b
            if zone is Zone.GRAVEYARD:
                self._note_put_into_graveyard_with_counters()
        if origin is Zone.STACK and zone is not Zone.STACK and not self.is_copy:
            self.last_known_spell = SpellSnapshot(
                stamp=self.zone_change_stamp,
                targets=tuple(self.targets),
                division=tuple(self.division) if self.division is not None else None,
            )
        self.zone_change_stamp = new_id()
        self.zone = zone
        self._granted_as_it_left = ()
        if origin is not zone and not (origin is Zone.STACK and zone is Zone.BATTLEFIELD):
            if origin is Zone.BATTLEFIELD:
                self._granted_as_it_left = self.granted_ability_texts
            # CR 400.7: a grant was given to *that* object, and the card that
            # moves is a new one - a bounced or blinked Thief of Existence
            # comes back without its cast trigger's rider, and a suspend
            # granted in exile (Delay, Suspend) does not survive leaving
            # exile, so a card later exiled with time counters by something
            # else does not wrongly still "have suspend" (CR 702.62b). The
            # one move that keeps them is CR 400.7a/400.7b's permanent spell
            # becoming a permanent. A static grant is re-stated by the next
            # `machines/layers.sync_granted_ability_texts` sweep, and a
            # leaves-the-battlefield trigger has already been collected by
            # the time this runs (CR 603.10a looks back).
            self.granted_ability_texts = ()
        if zone is not origin and not (origin is Zone.STACK and zone is Zone.BATTLEFIELD):
            # CR 702.103b carries bestowed across exactly one zone change:
            # "the permanent it becomes as it resolves will be a bestowed Aura
            # permanent". Every other *actual* move is CR 400.7's new object,
            # which nobody cast bestowed.
            #
            # `zone is not origin` excludes `Game.put_on_stack` re-stating the
            # zone of a spell already on the stack (see the identical
            # `spliced_text` guard just below): CR 400.7's "new object" is
            # about a card that actually changes zones, and restating the
            # zone it is already in is not that - a bestowed spell cast with
            # `use_keyword("Bestow")` used to lose the flag the instant
            # `Game._put_on_stack` ran its own `move_to(Zone.STACK)`, before
            # CR 601.2f's cost was even paid, so it could never resolve as
            # the Aura CR 702.103b promises. Detective's Phoenix (hardcast
            # and cast from the graveyard alike) is the proof this was wrong.
            self.bestowed = False
            self.prototyped = False  # CR 718.4
        # CR 400.7: see `cast_with_keyword` - set again by `Game.enter_the_
        # battlefield` for the one move that carries a cast spell's choice.
        self.cast_with_keyword = None
        if origin is Zone.STACK and zone is not Zone.STACK:
            # CR 702.47e: "The spell loses any splice changes once it leaves
            # the stack for any reason." *Leaves* - so the move that puts it
            # there (CR 601.2a, hand to stack) keeps what a splice
            # announcement added, and so does `Game.put_on_stack` re-stating
            # the zone of a spell already on the stack; every move off it, to
            # any zone, takes the text away.
            self.spliced_text = ()
            # CR 702.47e's own reasoning generalises to any one-shot grant a
            # spell picked up only for this stack visit.
            self.granted_rebound = False
        # CR 704.8 / CR 603.10a: an ability that looks back in time needs the
        # counters the object had as it left, and CR 122.2 has just taken them
        # away. Persist is the card in the pool that asks (CR 702.79a). Only a
        # move off the battlefield takes that snapshot: a look-back is about
        # the permanent as it last existed there, so a dies trigger still on
        # the stack reads the same answer after the card has been exiled from
        # the graveyard in response (Promising Duskmage's "if it had a +1/+1
        # counter on it").
        if origin is Zone.BATTLEFIELD:
            self.last_known_counters = self.counters
        self.counters = Counters()
        self.last_known_attached_to = self.attached_to if origin is Zone.BATTLEFIELD else None
        # A permanent that leaves the battlefield is no longer attached to
        # anything (CR 400.7 - it is a new object), and the deathtouch damage
        # CR 704.5h remembers went with the object it was marked on.
        self.attachment = None
        self.dealt_deathtouch_damage = False
        # CR 701.43a exerts a *permanent*; the object that leaves the
        # battlefield is not the one that comes back (CR 400.7).
        self.exerted = False
        # CR 701.19a's shield protects *this* permanent, and CR 400.7 makes
        # what comes back a different object with no memory of it - so a
        # creature regenerated, then bounced and recast, is not still shielded.
        self.regeneration_shields = 0
        if zone is not Zone.EXILE:
            # CR 400.7: it is a new object now, so which pile of exile it used
            # to sit in means nothing. Kept when the destination *is* exile, so
            # a caller can annotate the card either side of the move.
            self.exile_annotation = None
        if zone is not Zone.GRAVEYARD:
            # CR 400.7 again, for CR 701.9a's discard: the object that leaves
            # the graveyard is not the card anybody discarded, so mayhem's "as
            # long as you discarded this card this turn" (CR 702.187b) stops
            # being true of it. Kept when the destination *is* the graveyard,
            # because that is the move the discard itself makes -
            # `machines/keywords.discard` annotates the card the far side of it.
            self.discarded_by = None
            self.discarded_on_turn = None
        if zone is Zone.BATTLEFIELD:
            # It has only just arrived, so it has not been here since the turn
            # began (CR 302.6).
            self.summoning_sick = True
            if (
                origin is Zone.STACK
                and self.card.layout is Layout.MODAL_DFC
                and self.face_played is not None
            ):
                # CR 712.13: "a resolving double-faced spell that becomes a
                # permanent is put onto the battlefield with the same face up
                # that was face up on the stack" - a modal back face cast
                # under CR 712.11b stays up, read through `land_face_played`.
                self.land_face_played = self.face_played
            if place_intrinsic_counters:
                self._enter_with_intrinsic_counters()
        else:
            self.tapped = False
            self.transformed = False
            # CR 712.8a: off the battlefield and stack a double-faced card
            # has only its front face's characteristics again.
            self.land_face_played = None
            self.flipped = False  # CR 710.4
            self.damage = 0
            if not (zone is Zone.STACK and self.face_down_characteristics is not None):
                # CR 708.9: a face-down object leaving the stack or the
                # battlefield for anywhere else is revealed as it goes, and
                # CR 400.7 makes it a new object with the card's own
                # characteristics again. So does a foretold or hideaway card
                # that was face down in exile only as hidden information and is
                # now being cast face up.
                #
                # The one exception is a card *cast face down*: CR 708.4 turns it
                # face down "before they are put onto the stack", and CR 702.37c
                # has the permanent enter "with the same characteristics the
                # spell had". That is exactly the case where CR 708.2's listed
                # characteristics are already set.
                self.face_up = True
                self.face_down_characteristics = None
        if zone is not Zone.STACK:
            self.targets = []

    # -- counters (CR 122) -------------------------------------------------

    def counter_count(self, kind: CounterKind) -> int:
        """How many counters of one kind are on this object."""
        return self.counters[kind]

    def add_counters(self, kind: CounterKind, amount: int = 1) -> int:
        """Put counters on this object, returning the new count (CR 122.1).

        A keyword counter put on a permanent takes a timestamp (CR 613.7c) -
        `Game.stamp_keyword_counter`, which `machines/layers.py` orders it by
        against the other layer 6 effects (CR 613.1f)."""
        total = self.counters.add(kind, amount)
        game = self._board_source
        stamp = getattr(game, "stamp_keyword_counter", None)
        if amount > 0 and stamp is not None and self.zone is Zone.BATTLEFIELD:
            stamp(self, str(kind))
        return total

    def remove_counters(self, kind: CounterKind, amount: int = 1) -> int:
        """Take counters off, returning what is left. Raises if there are too few."""
        before = self.counters[kind]
        left = self.counters.remove(kind, amount)
        self._note_counters_removed(kind, amount)
        if amount > 0 and self.zone is Zone.BATTLEFIELD:
            note_removed = getattr(self._board_source, "note_counters_removed", None)
            if note_removed is not None:
                note_removed(self, str(kind), amount)
        if before > 0 and left == 0 and self.zone is Zone.BATTLEFIELD:
            note_last = getattr(self._board_source, "note_last_counter_removed", None)
            if note_last is not None:
                note_last(self, str(kind))
        return left

    def _note_counters_removed(self, kind: CounterKind, amount: int) -> None:
        """Count counters removed from this permanent this turn, for its
        controller - "an oil counter was removed from a permanent you
        controlled this turn" (Churning Reservoir). CR 122.2's counters that
        "cease to exist" on a zone change are not removed, and never reach
        here."""
        game = self._board_source
        if amount <= 0 or self.zone is not Zone.BATTLEFIELD or game is None:
            return
        note = getattr(game, "note_turn_count", None)
        if note is not None and self.controller is not None:
            note(counters_removed_fact(kind), self.controller, amount)

    def _note_put_into_graveyard_with_counters(self) -> None:
        """Count, for its owner, a permanent put into a graveyard from the
        battlefield with counters on it, one fact per kind - "a permanent with
        an oil counter on it was put into a graveyard this turn". Asked of the
        permanent as it last existed (CR 603.10a), so before CR 122.2 takes
        the counters away."""
        game = self._board_source
        note = getattr(game, "note_turn_count", None)
        if note is None or self.owner is None:
            return
        for kind in self.counters:
            note(graveyard_with_counter_fact(kind), self.owner, 1)

    def can_remove_counters(self, kind: CounterKind, amount: int = 1) -> bool:
        """Whether a cost that removes this many counters could be paid (CR 118.3)."""
        return amount >= 0 and self.counters[kind] >= amount

    def annihilate_counters(self) -> int:
        """Cancel +1/+1 against -1/-1 in pairs (CR 704.5q, CR 122.3).

        A state-based action, so the game performs it; this is only where the
        arithmetic lives. Returns how many pairs came off.
        """
        return self.counters.annihilate()

    @property
    def is_planeswalker(self) -> bool:
        """CR 205.2a: this object has the planeswalker card type.

        Layer-aware (CR 613.5, CR 613.1d), the same shape `is_saga` uses: the
        type is asked of the *computed* characteristics on the battlefield and
        of the printing everywhere else. A permanent a layer-4 effect made a
        planeswalker (or made not one) has to answer this the same way
        everything else that reads `is_planeswalker` does - `loyalty`,
        `has_zero_loyalty`, `intrinsic_entering_counters` below all gate on it.
        """
        computed = self.computed_characteristics
        types = self.types if computed is None else computed.types
        return Type.PLANESWALKER in types

    @property
    def is_saga(self) -> bool:
        """CR 303.5: an enchantment with the Saga subtype.

        Layer-aware (CR 613.5, CR 613.1d), the same shape `controller`,
        `power` and `toughness` already have: the subtype is asked of the
        *computed* characteristics on the battlefield and of the printing
        everywhere else. Urza's Saga under Blood Moon is the case that needs
        it - CR 305.7 sets its subtype to Mountain, so it stops being a Saga
        at all, and every rule that reads this has to agree: CR 505.4 /
        CR 714.3c stop giving it lore counters, and CR 704.5s stops putting it
        into its owner's graveyard.
        """
        computed = self.computed_characteristics
        subtypes = self.subtypes if computed is None else computed.subtypes
        return "Saga" in subtypes

    @property
    def is_class(self) -> bool:
        """CR 303.6, 716: an enchantment with the Class subtype.

        NOT made layer-aware, unlike `is_saga` right above it, even though the
        same CR 613.5 argument applies to it in principle. `class_ability_text`
        below reads `self.is_class`, and `class_ability_text` is itself read
        from *inside* board computation: `machines/layers.py`'s
        `ContinuousEffects.all_effects` calls `effects_for` for every
        permanent on the battlefield while building the effect list
        `compute_board` is about to apply, and `effects_for`
        (`machines/layers.py:6356`) and `quoted_ability_grants`
        (`machines/layers.py:4510`) both call `source.class_ability_text` as
        part of that same pass. Making `is_class` ask `computed_characteristics`
        would make it ask `Game.characteristics_of`, which recomputes the
        *entire* board (`Game.computed_board` is never cached) - and unlike
        `is_saga`'s callers, this one is called while a board computation for
        every permanent on the battlefield is already in flight. The
        re-entrancy guard (`_asking_the_board`) only protects the one object
        currently being asked about; a second, unflagged permanent's
        `class_ability_text` on the same sweep would kick off a fresh full
        recompute of its own, which reads every permanent's `class_ability_
        text` again, which starts another recompute, unbounded - the
        exponential blowup `CardState.computed_characteristics`'s own
        docstring warns a call-site-only fix must not reintroduce.

        Left printed. A permanent whose Class-ness a layer-4 effect changed
        (there is no such printed card in Magic today) would misread here;
        nothing in the current pool exercises that gap.
        """
        return "Class" in self.subtypes

    @property
    def class_ability_text(self) -> str:
        """CR 716.2a: only the abilities gated at or below `class_level` are
        "in effect" right now - a level-3 paragraph on a level-1 Class is
        printed, but not live. For anything that is not a Class, this is
        exactly `oracle_text`, so it is a safe drop-in for any consumer that
        currently reads `oracle_text` off a live permanent to find a static
        ability (`Game.static_cost_modifiers_for`, `machines.replacement`'s
        battlefield sweep).

        Built from `machines.abilities.parse_abilities`, which already tags
        each ability with the `BaseAbility.class_level` it belongs to - the
        same single parse `machines.triggers` gates triggered abilities on,
        so a Class's level structure is read once, off the printed level
        bars, and every consumer of it agrees.

        NOT made layer-aware (CR 613.5), unlike the handful of other
        `CardState` properties this defect class fixed. `machines/layers.py`'s
        `effects_for` (`:6356`) and `quoted_ability_grants` (`:4510`) both call
        this property, directly on `source`, as part of `ContinuousEffects.
        all_effects` - the pass that builds the effect list *for*
        `compute_board`, run once per permanent on the battlefield before a
        single layer has been applied. Reading `computed_characteristics` from
        here would call back into `Game.characteristics_of` - a full,
        uncached board recompute - while a board computation is already
        running, for a permanent other than (necessarily) the one the
        `_asking_the_board` guard is watching. That is exactly the
        "branching n deep" exponential case `computed_characteristics`'s own
        docstring and this defect's own hard constraint warn against, not a
        hypothetical: this property has two verified call sites inside that
        exact pass. Left printed, with the same gap `is_class` above notes -
        a Class whose level-gated text a layer-4/6 effect changed independent
        of its own level counter would misread; no printed card does that.
        """
        text = self.oracle_text
        if self.is_leveler:
            # CR 711.2a/b: the striation its level counters are in, and CR
            # 711.4's unstriated lines - the same narrowing a Class's level
            # and a station's charge counters get.
            from ..machines.abilities import leveler_lines

            return "\n".join(leveler_lines(text, self.counter_count(LEVEL_COUNTER)))
        if not self.is_class:
            return self.station_live_text(text)
        from ..machines.abilities import ActivatedAbility, parse_abilities

        up_face_name = self.up_face_name or self.card.name
        lines = [
            ability.raw
            for ability in parse_abilities(self.card)
            if ability.face == up_face_name
            and not (
                isinstance(ability, ActivatedAbility) and ability.class_level_target is not None
            )
            and (ability.class_level is None or ability.class_level <= self.class_level)
        ]
        return "\n".join(lines)

    @property
    def is_leveler(self) -> bool:
        """Whether this object's text box carries a level symbol (CR 711.1)."""
        from ..machines.abilities import is_leveler_text

        return is_leveler_text(self.oracle_text)

    def station_threshold_met(self, threshold: int | None) -> bool:
        """CR 721.2a: "As long as this permanent has N or more charge counters
        on it" - True for an ability printed outside every striation."""
        return threshold is None or self.counter_count("charge") >= threshold

    def station_live_text(self, text: str | None) -> str:
        """`text` with each station striation (CR 721.2) narrowed to what this
        permanent has right now: a striation whose N its charge counters
        reach keeps its abilities, symbol taken off; one they do not reach is
        left out, the same way `class_ability_text` leaves out a level the
        Class has not reached. Text with no station symbol comes back as is.
        """
        from ..machines.abilities import STATION_SYMBOL_RE, station_striations

        if not text or not any(STATION_SYMBOL_RE.match(line.strip()) for line in text.splitlines()):
            return text or ""
        from ..machines.abilities import self_reference_names
        from ..machines.ep02_r1_counter_amounts import counters_self_reference_normalised

        live = "\n".join(
            line
            for line, threshold in station_striations(text.splitlines())
            if self.station_threshold_met(threshold)
        )
        # CR 201.5: "counters on The Eternity Elevator" is "counters on this permanent".
        return counters_self_reference_normalised(
            live,
            self_reference_names(self.card.name, legendary=Supertype.LEGENDARY in self.supertypes),
        )

    @property
    def chapter_numbers(self) -> tuple[int, ...]:
        """Every CR 107.15 threshold this Saga's own chapter symbols name,
        lowest first - `(1, 2, 3)` for History of Benalia's `I, II —`/`III —`.

        Late import, the same reason `keywords` reaches into
        `machines/abilities.py` from here: `machines/` imports `models/`, so
        the reverse import only resolves once this is actually called.  Empty
        for anything that is not a Saga, or a Saga with no chapter line at
        all - CR 714.3c's own gate, "one or more chapter abilities", reads
        this the same way.
        """
        if not self.is_saga:
            return ()
        from ..machines.abilities import TriggeredAbility, TriggerEvent, parse_abilities

        # CR 613.1f: layer 6 can remove an ability, and CR 305.7 removes every
        # ability generated from a land's rules text when an effect sets its
        # subtype to a basic land type. A chapter ability the Saga no longer
        # *has* is not counted - CR 714.2d ("A Saga's final chapter number is
        # the greatest value among chapter abilities it has") says "has", and
        # CR 714.4 / CR 704.5s / CR 505.4 / CR 714.3c all gate on "a Saga
        # permanent with one or more chapter abilities". So the computed
        # ability list, not the printing, decides.
        computed = self.computed_characteristics
        up_face_name = self.up_face_name or self.card.name
        return tuple(
            sorted(
                ability.chapter
                for ability in parse_abilities(self.card)
                if ability.face == up_face_name
                and isinstance(ability, TriggeredAbility)
                and ability.event is TriggerEvent.LORE_COUNTERS_ADDED
                and ability.chapter is not None
                and (computed is None or computed.has_ability(ability.raw))
            )
        )

    @property
    def final_chapter_number(self) -> int | None:
        """CR 714.2e: "A Saga's final chapter ability is the chapter ability
        which has its final chapter number in its chapter symbol." `None` for
        a non-Saga or one with no chapter line to read a number off.
        """
        numbers = self.chapter_numbers
        return max(numbers) if numbers else None

    @property
    def lore_counters(self) -> int:
        """How many lore counters (CR 714.3) are on this Saga right now."""
        return self.counters[Counter.LORE]

    @property
    def lore_counters_exhausted(self) -> bool:
        """CR 714.4, CR 704.5s: the lore-counter half of the state-based
        action's condition - "greater than or equal to its final chapter
        number" - minus the "and it isn't the source of a chapter ability
        that has triggered but not yet left the stack" half. CR 704.5s does
        not use the word "sacrifice" at all: it is a plain SBA move to the
        graveyard, like CR 704.5f's zero-toughness creature, not CR 701.21's
        player-chosen action. The caller (`Game._sagas_to_put_into_graveyard`)
        is the one that knows what is still on the stack, so it checks that
        half itself and only asks this for the lore-counter comparison.
        """
        if not self.is_saga or self.zone is not Zone.BATTLEFIELD:
            return False
        final = self.final_chapter_number
        return final is not None and self.lore_counters >= final

    @property
    def _printed_loyalty(self) -> str | None:
        """The loyalty number printed on the face that is up (CR 209.1).

        Scryfall leaves the top-level `loyalty` null on a `transform` card and
        prints the number on the face that carries it - Ajani, Nacatl Pariah's
        3 is on Ajani, Nacatl Avenger, his back face. CR 712.8e gives a
        transformed permanent only that face's characteristics, and CR 109.3
        counts loyalty among them, so this reads `up_face` like every other
        characteristic and falls back to the top-level field for a single-faced
        planeswalker.
        """
        up_face = self.up_face
        if up_face is not None and up_face.loyalty is not None:
            return up_face.loyalty
        return self.card.loyalty

    @property
    def loyalty(self) -> int | None:
        """This planeswalker's loyalty, or None if it is not one (CR 306.5).

        CR 306.5c: "the loyalty of a planeswalker on the battlefield is equal
        to the number of loyalty counters on it." Off the battlefield it is the
        printed number (CR 306.5a), which is also what it enters with
        (CR 306.5b, CR 209.1).
        """
        if not self.is_planeswalker:
            return None
        if self.zone is Zone.BATTLEFIELD:
            return self.counters[Counter.LOYALTY]
        return _as_number(self.card.loyalty)

    @property
    def has_zero_loyalty(self) -> bool:
        """True if this planeswalker is at 0 loyalty (CR 704.5i, CR 306.9)."""
        if not self.is_planeswalker or self.zone is not Zone.BATTLEFIELD:
            return False
        return self.counters[Counter.LOYALTY] <= 0

    def intrinsic_entering_counters(self) -> dict[str, int]:
        """The counters this permanent's intrinsic "enters with" abilities put
        on it as it enters, by kind: CR 306.5b's printed loyalty for a
        planeswalker, CR 714.3a's one lore counter for a Saga, and CR 310.4b's
        printed defense for a battle - each read off the face that is up.

        Each is a replacement effect (CR 614.1c) and the counters it gives are
        counters put on the object (CR 122.6), so `Game.enter_the_battlefield`
        places these through `Game.add_counters` like any other "enters with"
        counters. Only a `CardState` built in place with no game to ask
        (`_enter_with_intrinsic_counters`) writes them directly.
        """
        counters: dict[str, int] = {}
        if self.is_planeswalker:
            printed = self.printed_loyalty
            if printed:
                counters[str(Counter.LOYALTY)] = printed
        if self.is_saga and self.chapter_numbers:
            counters[str(Counter.LORE)] = 1
        if Type.BATTLE in self.types:
            defense = self.printed_defense
            if defense:
                counters[str(Counter.DEFENSE)] = defense
        return counters

    def _enter_with_intrinsic_counters(self) -> None:
        """`intrinsic_entering_counters`, written straight onto the object -
        for a move or a construction with no `Game` whose replacement
        effects could apply."""
        for kind, amount in self.intrinsic_entering_counters().items():
            self.counters.add(kind, amount)

    @property
    def printed_loyalty(self) -> int | None:
        """The loyalty number printed on the face that is up (CR 209.1), or None."""
        return _as_number(self._printed_loyalty)

    @property
    def printed_defense(self) -> int | None:
        """The defense printed on the face that is up (CR 310.4a), or None."""
        up_face = self.up_face
        printed = up_face.defense if up_face is not None else self.card.defense
        return _as_number(printed)

    @model_validator(mode="wrap")
    @classmethod
    def _resolve_token_subclass(cls, data: Any, handler: Any) -> "CardState":
        """A token survives as a `TokenState` across a round trip (CR 111.1).

        `token.TokenState` is `CardState`'s only subclass, and its whole
        reason to exist - `move_to`'s CR 111.8 override - depends on staying a
        `TokenState` instance. Every field that stores one is typed plainly as
        `CardState` (`Player.zones`, `Game`'s `StackObject`), which is fine for
        an in-memory game: pydantic leaves an instance that already is the
        right class alone. It is not fine for a `dict` - the shape a game is
        in right after a `model_dump`/JSON round trip, with no Python type
        information left in it anywhere - because there `CardState` is all the
        field annotation has ever named, and building one throws
        `TokenState`'s override away even though the dict itself still says
        `token: true`.

        So `CardState` reads its own subclass off `state_class` rather than
        trusting the field annotation: a dict payload with `state_class ==
        "TokenState"` is handed to `TokenState` instead. `cls is CardState`
        keeps this from firing again once it has - `TokenState.model_validate`
        reaches this same validator through inheritance, with `cls` bound to
        `TokenState`, and must fall straight through to `handler`. Anything
        that is not such a dict (an in-memory instance, a plain permanent, a
        `TokenState` dict already being validated as `TokenState`) also falls
        straight through, unchanged.

        Not `token`: that flag is CR 111.1's own "is this a token", a
        genuinely different question from "which Python class built this" -
        `state_class`'s own docstring is the defect that conflating the two
        caused (`Game.copy_spell` builds a `TokenState` with `token=False`
        while a copy of a permanent spell sits on the stack, not yet a token
        under CR 707.10f, and used to decode back as a plain `CardState`
        because `token` was the only signal read here).
        """
        if cls is CardState and isinstance(data, dict) and data.get("state_class") == "TokenState":
            from .token import TokenState  # deferred: token.py imports CardState

            return TokenState.model_validate(data)
        return handler(data)

    @model_serializer(mode="wrap")
    def _dump_with_subclass_fields(self, handler: Any) -> dict[str, Any]:
        """A `TokenState`'s own fields survive a dump through a `CardState`-typed
        container, alongside `_resolve_token_subclass`'s other half of CR 111.1.

        Every field that stores a permanent is typed plainly as `CardState`
        (`Player.zones`, `Game`'s `StackObject`), so `model_dump` builds each
        item from *that* schema - `TokenState`'s own fields are simply not
        part of it. Pydantic's default there is to serialize by the
        container's declared type rather than the object's actual one, which
        silently dropped `TokenState.left_the_battlefield` from a dumped
        token: not merely a class the decoder could not have rebuilt, but a
        flag CR 111.8 needs that never made it into the dict to rebuild from
        in the first place.

        `handler(self)` is that default - correct and complete whenever `self`
        really is a plain `CardState`, and already correct for a subclass
        serialized under its *own* type (its schema already knows its own
        fields, so this is then a harmless no-op). It only needs help for the
        one case in between: a subclass instance reached through a schema
        built for `CardState`. `type(self).model_fields` there names every
        field the object actually has; the ones `CardState` itself does not
        declare are read straight off `self` and added on top, which keeps
        this correct for any future field `TokenState` (or another
        `CardState` subclass) adds without needing a matching change here.
        """
        data = handler(self)
        if type(self) is not CardState:
            own_only = set(type(self).model_fields) - set(CardState.model_fields)
            for name in own_only:
                data[name] = getattr(self, name)
        return data

    @model_validator(mode="wrap")
    @classmethod
    def _built_on_the_battlefield_starts_with_its_counters(
        cls, data: Any, handler: Any
    ) -> "CardState":
        """A planeswalker or Saga *built* straight onto the battlefield gets
        the counters it would have entered with; one being *decoded* does not.

        The intrinsic abilities of `intrinsic_entering_counters` (CR 306.5b,
        CR 714.3a, CR 310.4b), applied where a `CardState`
        is constructed in place rather than moved onto the battlefield.

        The guard is what makes the engine able to decode any game state. "It
        has no counters yet" cannot tell the two apart: a planeswalker
        legitimately sits on the battlefield with zero loyalty (it is about to
        die to CR 704.5i, or a test transformed a card into one without CR
        306.5b's entry replacement), and re-seeding those counters on decode
        silently invents state the dumped game never had. A payload that
        carries a `counters` key already states what its counters are - zero
        included - so it is taken at its word and nothing is seeded. Only
        construction that never mentioned counters at all is treated as an
        object arriving on the battlefield for the first time.
        """
        state = handler(data)
        if isinstance(data, Mapping) and "counters" in data:
            return state
        if state.zone is Zone.BATTLEFIELD and not state.counters:
            state._enter_with_intrinsic_counters()
        return state


def bind_all_to_game(states: Iterable[CardState], game: Any) -> None:
    """`bind_to_game` (CR 613.5), over every `CardState` `game` holds.

    `Game.model_post_init` already stamps `player.game = self` on every
    player so `Player.discard` has a rules engine to ask, but it does not
    call this - and `bind_to_game` has exactly one production call site,
    `Game.put_onto_battlefield`. That covers a card *entering* the
    battlefield during play. It does nothing for a permanent that is already
    there the moment a `Game` is built from a dict: a cold `model_validate`
    never routes a single card through `put_onto_battlefield`, so every one
    of its permanents answers `power`/`toughness` with the printed value plus
    counters (CR 122.1a) instead of the layer engine's (CR 613.5) - silently
    different from the same game played continuously, for as long as nothing
    re-enters the battlefield to get bound.

    This is the loop that closes that gap: hand it every `CardState` the
    game holds - `Game.shared_zones` and every `Player.zones`, the same two
    collections `Game`'s own target-candidate sweeps already walk - and
    `game`, once, from `Game.model_post_init`, right alongside the `player.
    game = self` loop it already runs. It does not live in `Game` itself
    only because nothing in this module is allowed to import it.
    """
    for state in states:
        state.bind_to_game(game)


def annihilate_counters_on(permanents: Iterable[CardState]) -> list[CardState]:
    """Run CR 704.5q over a battlefield, returning the permanents it changed.

    "If a permanent has both a +1/+1 counter and a -1/-1 counter on it, N +1/+1
    and N -1/-1 counters are removed from it, where N is the smaller of the
    number of +1/+1 and -1/-1 counters on it." CR 122.3 states the same rule
    from the counters' side.

    A state-based action, so a game performs it as part of CR 704.3 rather than
    at the moment the counters meet. `Game._state_based_actions_once`
    (`models/game.py`) is the caller, on every battlefield-wide check.
    """
    return [state for state in permanents if state.annihilate_counters()]


def planeswalkers_with_zero_loyalty(permanents: Iterable[CardState]) -> list[CardState]:
    """The planeswalkers CR 704.5i puts into their owners' graveyards.

    "If a planeswalker has loyalty 0, it's put into its owner's graveyard."
    CR 306.9 says the same from the planeswalker's side. Loyalty is the number
    of loyalty counters on it (CR 306.5c), so this is a counters rule.
    """
    return [state for state in permanents if state.has_zero_loyalty]


def counter_state_based_actions(permanents: Iterable[CardState]) -> list[CardState]:
    """The counter-driven state-based actions, in one pass (CR 704.3).

    Kept for `magic_cards_model_api.engine_api`, which imports it at module
    load: `Game._state_based_actions_once` performs these itself now, through
    the same two helpers. Annihilation first (CR 704.5q), then the
    planeswalkers left at zero loyalty (CR 704.5i), which is what the caller
    should put into graveyards.
    """
    permanents = list(permanents)
    annihilate_counters_on(permanents)
    return planeswalkers_with_zero_loyalty(permanents)


def _is_suspend_line(line: str) -> bool:
    """Whether a granted ability line is the bare suspend keyword - the line
    `machines/effects.grant_suspend` writes."""
    return line.strip().rstrip(".").lower() == "suspend"


def _with_granted[T](have: tuple[T, ...], granted: Iterable[T]) -> tuple[T, ...]:
    """`have` plus every `granted` value not already in it (CR 205.1b)."""
    return have + tuple(value for value in granted if value not in have)


def _as_number(printed: str | None) -> int | None:
    """A printed power or toughness as an int, or None if it is not a plain number."""
    if printed is None:
        return None
    try:
        return int(printed)
    except ValueError:
        return None


class PrototypeCharacteristics(EngineModel):
    """CR 718.2's alternative mana cost, power and toughness, with the colours
    that cost gives (CR 718.3b, CR 105.2)."""

    mana_cost: str
    power: int
    toughness: int
    colors: tuple[Color, ...]


_PROTOTYPE_LINE_RE = re.compile(
    r"^Prototype (?P<cost>(?:\{[^}]+\})+) \u2014 (?P<p>\d+)/(?P<t>\d+)", re.M
)
_COLOR_LETTERS = "WUBRG"


def prototype_of(oracle_text: str | None) -> PrototypeCharacteristics | None:
    """Read a printed "Prototype {cost} - P/T" line (CR 702.160a, CR 718.1)."""
    match = _PROTOTYPE_LINE_RE.search(oracle_text or "")
    if match is None:
        return None
    cost = match.group("cost")
    symbols = {part for symbol in re.findall(r"\{([^}]+)\}", cost) for part in symbol.split("/")}
    return PrototypeCharacteristics(
        mana_cost=cost,
        power=int(match.group("p")),
        toughness=int(match.group("t")),
        colors=tuple(Color(letter) for letter in _COLOR_LETTERS if letter in symbols),
    )
