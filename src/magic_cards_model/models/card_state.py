"""A card as it exists in a game, as opposed to the printing it was cut from."""

from collections.abc import Iterable
from enum import StrEnum
from typing import Any, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

from .card import Card, Color, Layout, Supertype, Type, subtypes_of, supertypes_of, types_of
from .zone import Zone

PERMANENT_TYPES = frozenset(
    {Type.ARTIFACT, Type.CREATURE, Type.ENCHANTMENT, Type.LAND, Type.PLANESWALKER, Type.BATTLE}
)


class TargetKind(StrEnum):
    """The two things a spell can point at (CR 115.1)."""

    CARD = "card"
    PLAYER = "player"


class TargetRef(BaseModel):
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

    @classmethod
    def to_card(cls, card: "CardState | UUID") -> "TargetRef":
        """Target an object by its `CardState`, or directly by its id."""
        card_id = card if isinstance(card, UUID) else card.id
        return cls(kind=TargetKind.CARD, card_id=card_id)

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
    - `poison` is on a player, and ten of them lose the game (CR 122.1f,
      CR 704.5c).
    - `energy` is on a player and is what `{E}` pays with (CR 107.14).
    - `experience` is on a player.
    - `charge` is the common named counter with no rules of its own.

    A keyword counter (CR 122.1b) is stored under the keyword's own name, so a
    flying counter is `counters["flying"]`. Nothing grants the keyword yet - it
    would apply in layer 6 (CR 613.1f).
    """

    PLUS_ONE = "+1/+1"
    MINUS_ONE = "-1/-1"
    LOYALTY = "loyalty"
    POISON = "poison"
    ENERGY = "energy"
    EXPERIENCE = "experience"
    CHARGE = "charge"


#: A counter kind: one of the named ones, or any string a card invents.
CounterKind = Counter | str


def _counter_key(kind: CounterKind) -> str:
    """Counter kinds are compared by name, so an enum and its text are one key."""
    return str(kind)


class Counters(RootModel[dict[str, int]]):
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
            self.counts[key] = self.counts.get(key, 0) + amount
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
        if remaining:
            self.counts[key] = remaining
        else:
            self.counts.pop(key, None)
        return remaining

    def set(self, kind: CounterKind, amount: int) -> int:
        """Put the count of one kind at exactly `amount`."""
        if amount < 0:
            raise ValueError("a permanent cannot have a negative number of counters")
        key = _counter_key(kind)
        if amount:
            self.counts[key] = amount
        else:
            self.counts.pop(key, None)
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
    """

    PLOTTED = "plotted"
    FORETOLD = "foretold"
    WARPED = "warped"
    ADVENTURED = "adventured"
    MADNESS = "madness"
    """CR 702.35a's first ability: "If a player would discard this card, that
    player discards it, but exiles it instead of putting it into their
    graveyard." The card sits in its own pile of exile until the triggered
    ability that follows is resolved, and CR 702.35b casts it from there."""
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


class Choice(BaseModel):
    """One "as [this] enters, choose ..." answer, recorded on the object that
    asked (CR 614.12a).

    `value` is the chosen color's letter code (`Color.value`, e.g. `"G"`) for
    `ChoiceKind.COLOR`, or the plain named string for the other two kinds - a
    card name or a creature type. Read back later by whatever clause says "the
    chosen color"/"the chosen card name"/"the chosen creature type".
    """

    kind: ChoiceKind
    value: str


class FaceDownCharacteristics(BaseModel):
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


class ExileAnnotation(BaseModel):
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


class CardState(BaseModel):
    """One physical card in a game: which printing it is, where it is, how it sits.

    `Card` stays the immutable Scryfall printing. Four copies of the same card in
    a deck are four `CardState`s sharing one `Card`, each with its own `id`.
    """

    id: UUID = Field(default_factory=uuid4)
    card: Card
    zone: Zone = Zone.LIBRARY
    controller: str | None = None
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
    land_face_played: str | None = None
    """The name of the face this permanent entered as, when it was played as
    the land face of a modal double-faced card (CR 712.12).

    Set only by `Game.play_land`, and only when it chose the back face -
    Witch-Blessed Meadow rather than Witch Enchanter. CR 712.8f: "While a
    modal double-faced ... permanent is on the battlefield, it has only the
    characteristics of the face that's up," so `types`, `subtypes`,
    `oracle_text`, `mana_cost` and `name` below read this face instead of the
    card's front once it is set. Unlike `transformed` (CR 701.27a), the
    choice is made once, when the card is played, and never changes after -
    an MDFC does not transform back and forth.
    """
    face_played: str | None = None
    """The name of the half chosen for a **split card** (CR 709.3) on the
    stack - Wear // Tear's "Tear" when that half, not Wear, was cast.

    Set only by `Casting.cast`, and only for a card whose `Card.layout` is
    `Layout.SPLIT`: CR 709.3b, "While on the stack, only the characteristics
    of the half being cast exist. The other half's characteristics are
    treated as though they didn't exist" - so `up_face` below reads this
    face, ahead of the front-face fallback every other layout still uses.
    Deliberately scoped to split cards alone and not shared with Adventure's
    own chosen face (`Casting.face`/`chosen_face`): CR 715.3b names the same
    idea for an Adventure spell, but that gap is separately documented and
    intentionally still open (`docs/engine-coverage.md`'s "Alternative
    characteristics on the stack" row) - widening this field to cover it too
    would silently change already-`xfail`ed behaviour this wave does not
    touch. Fuse (CR 702.102) - casting *both* halves as one spell - is not
    modelled: this only ever names one half.
    """
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
    later - plot (CR 702.170c), foretell (CR 702.143c), warp (CR 702.185b), and
    the Adventure exile of CR 715.3d. `move_to` drops it on the way out of
    exile, because a card that leaves exile is a new object (CR 400.7) and its
    pile no longer means anything.
    """

    turn_entered: int | None = None
    """The turn number this permanent arrived on the battlefield, or `None` if
    nothing was counting (built outside a game, or before a turn existed).

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

    last_known_counters: Counters = Field(default_factory=Counters)
    """The counters this object had the last time it changed zones (CR 704.8).

    CR 122.2 destroys the counters on a zone change, and CR 603.10a lets a dies
    trigger look back in time at the object as it last existed. Persist's
    intervening *if* - "if it had no -1/-1 counters on it" (CR 702.79a) - is
    exactly that question, and there is nothing else left to ask.
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

    zone_change_stamp: UUID = Field(default_factory=uuid4)
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
        - A **split card's own chosen half** (CR 709.3b), while `face_played`
          names one and the object is still on the stack - see `face_played`'s
          own docstring for why this is scoped to `Layout.SPLIT` alone.
        - The **front face** otherwise: CR 712.8a makes it the only face this
          card has anywhere but the battlefield or stack, and CR 712.8d makes
          it the same on the battlefield while the front face is up.

        `None` for an ordinary single-faced card, whose own top-level fields
        already *are* the up face - every caller must keep that fallback, or a
        single-faced permanent ends up with no characteristics at all.
        """
        land_face = self._land_face
        if land_face is not None:
            return land_face
        if self.transformed:
            back_face = self.card.back_face
            if back_face is not None:
                return back_face
        if (
            self.face_played is not None
            and self.card.layout is Layout.SPLIT
            and self.zone is Zone.STACK
        ):
            # CR 709.2: off the stack, a split card is "only one card" again -
            # both halves, not the one that was last cast. Scoped to the
            # stack the way CR 709.3b itself is worded ("while on the
            # stack"), so a resolved and graveyard-bound Wear // Tear is read
            # as the whole card once more, the same as before it was cast.
            for face in self.card.card_faces or []:
                if face.name == self.face_played:
                    return face
        return self.card.front_face

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
    def types(self) -> tuple[Type, ...]:
        """This object's card types (CR 205.2a, CR 708.2).

        Read off `up_face`'s own type line when there is a face (CR 712.8d,
        712.8e, 712.8f), so a transformed Delver of Secrets is a Human Insect
        and a transformed Ajani, Nacatl Pariah is a Planeswalker rather than
        the Cat Warrior his front face prints. `Card.types` parses
        `front_type_line` only, which is the right answer for every
        single-faced card and the wrong one for a permanent showing any other
        face.
        """
        if self.face_down_characteristics is not None:
            return self.face_down_characteristics.types
        up_face = self.up_face
        if up_face is not None:
            return tuple(types_of(up_face.type_line or ""))
        return tuple(self.card.types)

    @property
    def subtypes(self) -> tuple[str, ...]:
        """This object's subtypes (CR 205.3, CR 708.2). Face down, there are none.

        The same `up_face` read as `types` - a transformed Ajani is an Ajani
        planeswalker and no longer a Cat, which is exactly what his own back
        face's "+1/+1 counter on each Cat you control" has to be counted
        against.
        """
        if self.face_down_characteristics is not None:
            return self.face_down_characteristics.subtypes
        up_face = self.up_face
        if up_face is not None:
            return tuple(subtypes_of(up_face.type_line or ""))
        return tuple(self.card.subtypes)

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
        if self.face_down_characteristics is not None:
            return ()
        up_face = self.up_face
        if up_face is not None:
            return tuple(supertypes_of(up_face.type_line or ""))
        return tuple(self.card.supertypes)

    @property
    def colors(self) -> tuple[Color, ...]:
        """This object's colors (CR 105.2, CR 202.2, CR 708.2).

        A back face prints no mana cost, so its colour comes from its colour
        indicator (CR 202.2f, CR 204.1) - Scryfall reports both `colors` and
        `color_indicator` on the face, and `colors` is already the answer.
        Face down, CR 708.2 leaves it colorless along with everything else it
        does not list.
        """
        if self.face_down_characteristics is not None:
            return ()
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
        if self.face_down_characteristics is not None:
            return self.face_down_characteristics.keywords
        if not self.card.card_faces:
            return tuple(self.card.keywords)
        # Imported here: `machines/` imports `models/`, so the reverse import
        # only resolves at call time.
        from ..machines.abilities import keywords_in_lines

        on_this_face = keywords_in_lines(self.oracle_text.split("\n"), list(self.card.keywords))
        return tuple(keyword for keyword in self.card.keywords if keyword.lower() in on_this_face)

    @property
    def oracle_text(self) -> str:
        """This object's rules text (CR 708.2). Face down, it is empty."""
        if self.face_down_characteristics is not None:
            return self.face_down_characteristics.oracle_text
        up_face = self.up_face
        if up_face is not None:
            return up_face.oracle_text or ""
        return self.card.oracle_text or ""

    @property
    def mana_cost(self) -> str | None:
        """This object's mana cost (CR 202.1, CR 708.2). Face down, there is none."""
        if self.face_down_characteristics is not None:
            return self.face_down_characteristics.mana_cost
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
        if self.face_down_characteristics is not None:
            return 0.0
        land_face = self._land_face
        if land_face is not None:
            from .mana import ManaCost

            return float(ManaCost.parse(land_face.mana_cost or "").converted)
        return self.card.cmc

    @property
    def is_permanent(self) -> bool:
        """True if this card stays on the battlefield once it resolves."""
        return bool(set(self.types) & PERMANENT_TYPES)

    @property
    def is_creature(self) -> bool:
        return Type.CREATURE in self.types

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
        """
        if game is not None:
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
        """
        if self.face_down_characteristics is not None:
            # CR 708.2: face down, 2 is what its toughness *is*; the counters
            # still apply on top, in sublayer 7c (CR 613.4c).
            base = self.face_down_characteristics.toughness
            return base + self.counters.power_toughness_modifier
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
        `toughness`. Combat damage is assigned equal to power (CR 510.1a), so
        this is what an attacking or blocking creature deals.
        """
        if self.face_down_characteristics is not None:
            base = self.face_down_characteristics.power
            return base + self.counters.power_toughness_modifier
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
        toughness = self.toughness
        return None if toughness is None else toughness - self.damage

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
        return self.damage >= toughness or self.dealt_deathtouch_damage

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
        """
        self.attachment = None

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

    def untap(self, *, exert_applies: bool = True) -> None:
        """Untap this card, unless it was exerted (CR 701.43a-b).

        CR 701.43a is about one moment only: an exerted permanent "does not
        untap during your next untap step". The flag expires as that step
        happens (CR 701.43b), so it is cleared here whether or not the untap
        went through - which is what stops one exert skipping two untap steps.

        `exert_applies=False` is for a caller that is *not* the untap step: an
        effect or a `{Q}` cost that untaps a permanent does so regardless of
        exert, and leaves the exert in place for the step it was aimed at.
        """
        if exert_applies and self.exerted:
            self.exerted = False
            return
        self.tapped = False

    def transform(self) -> None:
        """Turn this permanent over so its other face is up (CR 701.27a).

        Only a double-faced card can transform (CR 712.9); asking anything else
        to does nothing, which is what CR 701.28c says for the sibling action.
        """
        if not self.card.card_faces:
            return
        self.transformed = not self.transformed

    def turn_face_up(self) -> None:
        """Turn this object face up, restoring the card's own characteristics.

        CR 702.37e: "The morph effect on it ends, and it regains its normal
        characteristics." CR 708.8 says the same generally: "As a face-down
        permanent is turned face up, its copiable values revert to its normal
        copiable values."

        Turning something face up that already is does nothing - the rules have
        no such action, and there is nothing to undo.
        """
        self.face_up = True
        self.face_down_characteristics = None

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

    def move_to(self, zone: Zone) -> None:
        """Move to another zone, resetting the state a card loses on the way.

        A card leaving the battlefield becomes a new object, so it arrives
        untapped and face up.

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
        self.zone_change_stamp = uuid4()
        self.zone = zone
        # CR 704.8 / CR 603.10a: an ability that looks back in time needs the
        # counters the object had as it left, and CR 122.2 has just taken them
        # away. Persist is the card in the pool that asks (CR 702.79a).
        self.last_known_counters = self.counters
        self.counters = Counters()
        # A permanent that leaves the battlefield is no longer attached to
        # anything (CR 400.7 - it is a new object), and the deathtouch damage
        # CR 704.5h remembers went with the object it was marked on.
        self.attachment = None
        self.dealt_deathtouch_damage = False
        # CR 701.43a exerts a *permanent*; the object that leaves the
        # battlefield is not the one that comes back (CR 400.7).
        self.exerted = False
        if zone is not Zone.EXILE:
            # CR 400.7: it is a new object now, so which pile of exile it used
            # to sit in means nothing. Kept when the destination *is* exile, so
            # a caller can annotate the card either side of the move.
            self.exile_annotation = None
        if zone is Zone.BATTLEFIELD:
            # It has only just arrived, so it has not been here since the turn
            # began (CR 302.6).
            self.summoning_sick = True
            self._enter_with_loyalty()
        else:
            self.tapped = False
            self.transformed = False
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
        """Put counters on this object, returning the new count (CR 122.1)."""
        return self.counters.add(kind, amount)

    def remove_counters(self, kind: CounterKind, amount: int = 1) -> int:
        """Take counters off, returning what is left. Raises if there are too few."""
        return self.counters.remove(kind, amount)

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
        return Type.PLANESWALKER in self.types

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

    def _enter_with_loyalty(self) -> None:
        """CR 306.5b: a planeswalker enters with its printed loyalty in counters.

        An intrinsic ability creating a replacement effect, which is why it is
        applied as the permanent arrives rather than afterwards. Nothing models
        replacement effects yet (CR 614), so it is done here.
        """
        if not self.is_planeswalker:
            return
        printed = _as_number(self._printed_loyalty)
        if printed is not None:
            self.counters.add(Counter.LOYALTY, printed)

    @model_validator(mode="after")
    def _planeswalkers_start_loyal(self) -> Self:
        """A planeswalker built straight onto the battlefield has its loyalty.

        The same intrinsic ability as `_enter_with_loyalty` (CR 306.5b), applied
        where a `CardState` is constructed in place rather than moved. Guarded
        on having no counters at all, so a permanent whose counters are already
        known - one being deserialised, or one that has been ticked down - is
        left exactly as it was.
        """
        if self.zone is Zone.BATTLEFIELD and self.is_planeswalker and not self.counters:
            self._enter_with_loyalty()
        return self


def annihilate_counters_on(permanents: Iterable[CardState]) -> list[CardState]:
    """Run CR 704.5q over a battlefield, returning the permanents it changed.

    "If a permanent has both a +1/+1 counter and a -1/-1 counter on it, N +1/+1
    and N -1/-1 counters are removed from it, where N is the smaller of the
    number of +1/+1 and -1/-1 counters on it." CR 122.3 states the same rule
    from the counters' side.

    A state-based action, so a game performs it as part of CR 704.3 rather than
    at the moment the counters meet. Nothing in `Game` dispatches it yet - see
    `docs/engine-coverage.md`.
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

    Annihilation first (CR 704.5q), then the planeswalkers left at zero loyalty
    (CR 704.5i), which is what the caller should put into graveyards. The
    remaining counter-driven action, a creature whose -1/-1 counters take its
    toughness to 0 or less (CR 704.5f), needs no help here: `CardState.toughness`
    already counts them, so `Game.check_state_based_actions` sees it.
    """
    annihilate_counters_on(permanents)
    return planeswalkers_with_zero_loyalty(permanents)


def _as_number(printed: str | None) -> int | None:
    """A printed power or toughness as an int, or None if it is not a plain number."""
    if printed is None:
        return None
    try:
        return int(printed)
    except ValueError:
        return None
