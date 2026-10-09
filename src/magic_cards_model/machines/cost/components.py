import re
from collections.abc import Iterable, Sequence
from enum import StrEnum
from itertools import combinations_with_replacement
from typing import Any
from uuid import UUID

from pydantic import ConfigDict, Field, PrivateAttr

from magic_cards_model.phrases import with_indefinite_article

from ...data.subtypes import canonical_subtype
from ...models.card import Color, Supertype, Type
from ...models.card_state import (
    CardState,
    Counter,
    CounterKind,
    ExileAnnotation,
    ExileMarker,
)
from ...models.mana import (
    ManaCost,
    ManaSymbol,
    PaymentOption,
    SymbolKind,
)
from ...models.token import is_token
from ...models.zone import Zone
from ...numbers import (
    QuantitySource,
    parse_quantity,
)
from ...snapshot import EngineModel


class MixedProduction(list[Color]):
    """One activation of "Add N mana in any combination of <colours>" as an
    auto-tap candidate: N mana, each of its own colour among `palette`
    (CR 106.1a's five for "colors", the printed ones for "{U} and/or {R}").

    The solver's other alternatives are whole productions - "two mana of any
    one color" is five of them, `[[W, W], [U, U], ...]` - but a mixture's
    productions are every multiset of N over the palette, which is 126 at
    five mana and unbounded for a count the board decides. So it is carried
    as one alternative the flow network can express directly: a provider of
    capacity N with an edge of capacity N to every palette colour, which is
    exactly "N mana, each its own colour" (`_bucket_map`), and the split is
    read back off the flow (`_chosen_alternative`). The list itself holds N
    mana of the palette's first colour, so a caller that only reads it as a
    production (`_flexibility`, the life-loss replay) still sees a legal one.
    """

    palette: tuple[Color, ...]

    def __init__(self, palette: Sequence[Color], count: int) -> None:
        super().__init__([palette[0]] * count)
        self.palette = tuple(palette)

    def __eq__(self, other: object) -> bool:
        # Two mixtures are the same alternative only over the same palette;
        # the list content alone (N of the first colour) cannot tell "{U}
        # and/or {R}" from "{U} and/or {B}".
        if isinstance(other, MixedProduction):
            return self.palette == other.palette and len(self) == len(other)
        if isinstance(other, list):
            return False
        return NotImplemented

    def splits(self) -> list[list[Color]]:
        """Every production this mixture offers, spelled out - for a caller
        that must see each one (the brute-force oracle, a replacement or
        triggered mana ability that depends on what was produced)."""
        return [list(split) for split in combinations_with_replacement(self.palette, len(self))]

    def split_from(self, used: dict[Color, int]) -> list[Color]:
        """The production a flow solution's per-colour use names: what it
        spent of each colour, the rest of the N padded with the first
        palette colour (unspent mana floats, CR 106.4a)."""
        colors = [color for color in self.palette for _ in range(used.get(color, 0))]
        return colors + [self.palette[0]] * (len(self) - len(colors))


class CostStep(StrEnum):
    PENDING = "pending"
    TAPPING = "tapping"
    POOLED = "pooled"
    PAID = "paid"
    CANCELLED = "cancelled"


# --------------------------------------------------------------------------
# The non-mana half of a cost
# --------------------------------------------------------------------------


class ComponentKind(StrEnum):
    """The non-mana things a cost can ask for."""

    TAP = "tap"
    SACRIFICE = "sacrifice"
    DISCARD = "discard"
    EXILE = "exile"
    PAY_LIFE = "pay_life"
    REMOVE_COUNTERS = "remove_counters"
    #: "Put a -1/-1 counter on this creature:" (Devoted Druid), the templated
    #: twin of `REMOVE_COUNTERS` (CR 118.3, 122.1, 122.6). Unlike a loyalty
    #: cost's counters, which live on the ability's own source by definition
    #: (CR 606.4), this kind carries an explicit `counter_kind` because a
    #: printed cost can put on any named kind (Devoted Druid's -1/-1, a
    #: hypothetical +1/+1 or keyword counter).
    PLACE_COUNTERS = "place_counters"
    #: CR 606.4: "The cost to activate a loyalty ability of a permanent is to
    #: put on or remove from that permanent a certain number of loyalty
    #: counters, as shown by the loyalty symbol in the ability's cost." The
    #: amount is signed: positive puts counters on, negative removes them, and
    #: zero puts zero - `[0]` is a real cost whose payment is no event
    #: (CR 107.7). Not in `_OBJECT_KINDS`: the counters go on the ability's own
    #: source, so there is nothing to choose.
    LOYALTY = "loyalty"
    #: CR 701.43a, "to exert a permanent, you choose to have it not untap during
    #: your next untap step". Arena of Glory prints it inside an activation cost,
    #: `{R}, {T}, Exert this land:`.
    EXERT = "exert"
    #: CR 701.17a, "for a player to mill a number of cards, that player puts
    #: that many cards from the top of their library into their graveyard".
    #: Millikin prints it inside an activation cost, `{T}, Mill a card:`. Not
    #: in `_OBJECT_KINDS`: nothing is chosen, the cards are whichever ones are
    #: on top, so the count lives in `amount` the way paying life does.
    MILL = "mill"
    #: CR 107.6, "The untap symbol is {Q}. The untap symbol in an activation
    #: cost means 'Untap this permanent.'" The twin of `TAP`, and refused for
    #: the mirrored reason: "a permanent that's already untapped can't be
    #: untapped again to pay the cost". Umbral Mantle's granted `{3}, {Q}:` is
    #: the pool's printing.
    UNTAP = "untap"
    #: CR 701.59a, "to 'collect evidence N' means to exile any number of cards
    #: from your graveyard with total mana value N or greater." Detective's
    #: Phoenix prints it inside a bestow cost, `Bestow-{R}, Collect evidence
    #: 6.`. Not in `_OBJECT_KINDS`: "any number of cards" fixes no count at
    #: all, only the total mana value in `amount`, so the cards chosen are
    #: checked against that threshold rather than against a `required` count.
    COLLECT_EVIDENCE = "collect_evidence"
    #: CR 702.49a's own cost clause: "Return an unblocked attacking creature
    #: you control to its owner's hand." Ninjutsu's cost, and sneak's
    #: (CR 702.190a, "returning an unblocked creature you control to its
    #: owner's hand") - `_why_not_return_to_hand` checks "unblocked", the one
    #: restriction no existing object cost (SACRIFICE, DISCARD, EXILE) reads.
    RETURN_TO_HAND = "return_to_hand"
    #: CR 701.20a's reveal, as a cost (CR 118.1): "Reveal X white cards from
    #: your hand" (Martyr of Sands), "reveal a creature card from your hand"
    #: (Living Destiny's additional cost). Nothing moves (CR 701.20b); paying
    #: records the reveal on the game, and `variable_count` marks CR 107.3a's
    #: X, where `required` is the number the payer chose to reveal.
    REVEAL = "reveal"
    #: CR 701.4a's own keyword action, "to behold a [quality]": "Reveal a
    #: [quality] card from your hand or choose a [quality] permanent you
    #: control on the battlefield." Two zones satisfy one component - the
    #: chosen card is a `REVEAL` if it came from hand (CR 701.20a-b: shown,
    #: nothing moves) and untouched if it came from the battlefield (CR
    #: 701.4b: it is simply noted, not tapped, sacrificed, or exiled).
    BEHOLD = "behold"


_OBJECT_KINDS = frozenset(
    {
        ComponentKind.TAP,
        ComponentKind.UNTAP,
        ComponentKind.SACRIFICE,
        ComponentKind.DISCARD,
        ComponentKind.EXILE,
        ComponentKind.REMOVE_COUNTERS,
        ComponentKind.PLACE_COUNTERS,
        ComponentKind.EXERT,
        ComponentKind.RETURN_TO_HAND,
        ComponentKind.REVEAL,
        ComponentKind.BEHOLD,
    }
)


class CardRequirement(EngineModel):
    """What a cost demands of the cards chosen to pay it.

    CR 118.3 is the rule this serves: a player cannot pay a cost without the
    resources to pay it fully, and "a black card from your hand" is not paid by
    a red one. Every field is a disjunction and an empty field asks for nothing,
    so a bare `CardRequirement()` matches any card.
    """

    colors: list[Color] = Field(default_factory=list)
    """The card must be at least one of these colours."""
    types: list[Type] = Field(default_factory=list)
    """The card must have at least one of these card types."""
    excluded_types: list[Type] = Field(default_factory=list)
    """The card must have **none** of these card types - Rottenmouth Viper's
    own "sacrifice any number of nonland permanents" (CR 118.7a's own
    "nonland" restriction, read the same negated-type way `machines.
    targeting.permanent_description` already reads it for a targeted
    restriction). Unlike `types`, which is a choice among several, this is
    every one of them excluded at once - "nonland" alone has only ever
    printed the one card type in this pool, but a future "non-artifact,
    non-creature" would exclude both."""
    subtypes: list[str] = Field(default_factory=list)
    """The card must have at least one of these subtypes, as printed."""
    supertypes: list[Supertype] = Field(default_factory=list)
    """The card must have **all** of these supertypes (CR 205.4a: "The
    supertypes are basic, legendary, ongoing, snow, and world"). Unlike the
    other three fields this is a conjunction, because a supertype in a cost
    phrase qualifies the noun after it - "a legendary card" is one demand, not
    a choice between several."""
    same_name_as: "CardRequirement | None" = None
    """Key to the Side-Door's "with the same name as a legendary permanent you
    control": the chosen card must share its name (CR 201.2a) with a permanent
    the payer controls that meets *this* requirement."""
    mana_value: int | None = None
    """Disrupting Shoal's "a blue card with mana value X from your hand": the
    chosen card's mana value (CR 202.3) must be exactly this.

    An exact number, not a ceiling - the printed phrase this reads is "with
    mana value N", and the X-keyed printing is the same sentence with
    CR 107.3a's announced X already substituted in. A "N or less" phrase is a
    different demand and is deliberately not read as this one."""
    description: str = ""
    """The phrase this was read from, for the message when it is not met."""
    excludes_source: bool = False
    """Gallia, Tragic Host's own "exile *another* creature card from your
    graveyard" - CR 601.2c calls this reading "another"/"other" already,
    `machines/targeting.py`'s own `TargetRequirement.excludes_source` is the
    identical concept on the targeting side, not a second name for a
    different one. `source_id` is what this checks against; set together,
    by `Game.activation_cost`, which is the one place that already knows
    which permanent this cost is being paid to activate."""
    source_id: UUID | None = None
    """The permanent `excludes_source` excludes, filled in by `Game.
    activation_cost` rather than by the reader that builds this
    `CardRequirement` - the reader never sees a live board, only the
    printed phrase."""
    tapped: bool | None = None
    """Web-slinging's "return a *tapped* creature you control" (CR
    702.188a): True asks for a tapped permanent, False an untapped one, None
    either (CR 110.5's status)."""
    token: bool | None = None
    """Fountainport's "Sacrifice a token" (CR 111.1): True asks for a token,
    False ("a nontoken creature") for a card, None either."""

    @property
    def is_empty(self) -> bool:
        return not (
            self.colors
            or self.types
            or self.excluded_types
            or self.subtypes
            or self.supertypes
            or self.same_name_as
            or self.mana_value is not None
            or self.tapped is not None
            or self.token is not None
        )

    def why_not(self, card: CardState, game: Any = None, payer: str | None = None) -> str | None:
        """Why this card cannot pay, or None if it can.

        `game` and `payer` are needed only by `same_name_as`, which asks about
        the board rather than about the card alone. Without either there is no
        board to ask, and that half is skipped - a `CostPayment` with no game
        behind it cannot check any board-dependent requirement, the same
        limitation `_among_colors` documents on the mana side.

        The colour/type/subtype/mana-value checks below used to read
        `card.card` - the raw printing - unconditionally. That is CR 613.1's
        *starting point*, "the values of the characteristics printed on that
        card", never CR 613.5's "the application of continuous effects ... is
        continually and automatically performed": a card on the battlefield
        (`sacrifice a creature`, `tap an untapped creature you control`,
        CR 118.8a's additional costs) has to answer for what it *is*, and an
        animated land by earthbend (CR 701.66a) is a creature (CR 613.1d,
        layer 4; CR 205.1b's "in addition to its other types") that
        `card.card.types` would say is only ever a land. With a `game` and the
        card on the battlefield, `game.characteristics_of` is that answer.
        Off the battlefield there is no layer system to ask (CR 613.5 is about
        objects on the battlefield), so `CardState`'s own properties are read
        instead of the raw printing: they already resolve which face is up
        (CR 712.8d) the way `card.card`'s front face alone does not.
        """
        if self.excludes_source and self.source_id is not None and card.id == self.source_id:
            return f"{self.description or 'this cost'} excludes the ability's own source"
        if self.tapped is not None and card.tapped != self.tapped:
            return f"{card.name} is not {'tapped' if self.tapped else 'untapped'}"
        if self.token is not None and is_token(card) != self.token:
            return f"{card.name} is {'not ' if self.token else ''}a token"
        if game is not None and card.zone is Zone.BATTLEFIELD:
            try:
                characteristics = game.characteristics_of(card)
            except (AttributeError, KeyError):
                characteristics = None
        else:
            characteristics = None
        if characteristics is not None:
            colors = set(characteristics.colors)
            supertypes = set(characteristics.supertypes)
            types = set(characteristics.types)
            subtypes = {subtype.lower() for subtype in characteristics.subtypes}
            mana_value = characteristics.mana_value
        else:
            colors = set(card.colors)
            supertypes = set(card.supertypes)
            types = set(card.types)
            subtypes = {subtype.lower() for subtype in card.subtypes}
            mana_value = card.mana_value

        if self.colors and not colors & set(self.colors):
            wanted = "/".join(color.value for color in self.colors)
            return f"{card.name} is not {wanted}"
        if self.supertypes and not set(self.supertypes) <= supertypes:
            wanted = " ".join(supertype.value for supertype in self.supertypes)
            return f"{card.name} is not {wanted}"
        if self.types and not types & set(self.types):
            wanted = "/".join(type_.value for type_ in self.types)
            return f"{card.name} is not {with_indefinite_article(wanted)}"
        if self.excluded_types and types & set(self.excluded_types):
            unwanted = "/".join(type_.value for type_ in self.excluded_types)
            return f"{card.name} is {with_indefinite_article(unwanted)}"
        if self.subtypes and not subtypes & self._wanted_subtypes():
            return f"{card.name} is not {with_indefinite_article('/'.join(self.subtypes))}"
        if self.mana_value is not None and mana_value != self.mana_value:
            # CR 202.3: the mana value is read off the object, not off the
            # printed front face - computed when there is a board to compute
            # it against, `CardState.mana_value`'s own up-face read otherwise.
            return (
                f"{card.name} has mana value {mana_value:g}, not the "
                f"{self.mana_value} this cost asks for"
            )
        if self.same_name_as is not None and game is not None and payer is not None:
            # CR 201.2a: "Two or more objects have the same name if they have
            # at least one name in common." Compared on `CardState.name`, which
            # is the name of the face that is up (CR 712.8d), rather than on
            # the printed front face.
            match = any(
                state.name == card.name and self.same_name_as.why_not(state) is None
                for state in game.permanents_controlled_by(payer)
            )
            if not match:
                return (
                    f"{payer} controls no {self.same_name_as.description or 'permanent'} "
                    f"named {card.name}"
                )
        return None

    def _wanted_subtypes(self) -> set[str]:
        """The subtypes this accepts, lowercased, plural forms included.

        A cost phrase names its subtype the way the sentence needs it, and
        Fireblast's "Sacrifice two Mountains" is plural while CR 205.3 prints
        the subtype itself as `Mountain`. Both spellings are accepted rather
        than the plural being stripped off the requirement, because CR 205.3i's
        own list of land types includes `Plains` and `Locus` - both genuinely
        end in *s*, and blind singularising would break them.
        """
        wanted = set()
        for subtype in self.subtypes:
            lowered = subtype.lower()
            wanted.add(lowered)
            if lowered.endswith("s"):
                wanted.add(lowered[:-1])
            # An irregular plural ("Elves" for `Elf`, CR 205.3m) that trimming
            # an "s" never reaches - the subtype pool's own plural index.
            canonical = canonical_subtype(subtype)
            if canonical is not None:
                wanted.add(canonical)
        return wanted


class CostComponent(EngineModel):
    """One non-mana piece of a cost, with the objects chosen to pay it.

    The choice of *which* permanent to sacrifice is made while announcing the
    spell (CR 601.2b) and the sacrifice itself happens when the total cost is
    paid (CR 601.2h), so a component carries its chosen objects from the moment
    it is built and only acts on them at payment time.

    CR 118.3: a player cannot pay a cost without the resources to pay it fully,
    and `why_not` is where that is decided - before anything has been spent.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    kind: ComponentKind
    payer: str | None = None
    amount: int = 0
    """Life to pay, or counters to place/remove."""

    counter_kind: str = Counter.PLUS_ONE.value
    """Which kind of counter `PLACE_COUNTERS`/`REMOVE_COUNTERS` acts on - a
    named `Counter` or any string a card invents (CR 122.1). Unused by every
    other component kind."""

    required: int = 0
    """How many objects this component needs chosen. Zero for paying life."""

    cards: list[CardState] = Field(default_factory=list)
    """The objects chosen to pay this component, held by reference rather than
    by id. Kept as `CardState` rather than `list[UUID]` (unlike `CostPayment.
    tapped_for_mana`) because `why_not`/`pay` read a dozen of this object's own
    fields (`.zone`, `.tapped`, `.controller`, `.counters`, `.mana_value`,
    `.name`) throughout this class, several of them from call sites that pass
    no `game` at all (a unit test paying a bare component); reducing this to
    ids would mean every one of those reads needs a `game` to resolve through,
    which does not exist everywhere this class is used. `unpay` is the one
    place that both mutates through a captured reference *and* can run after a
    dump/decode round trip (a payment resumed from `AbilityOnStack.
    keyword_activation.payment`/`.unless_payment`), so that is where the
    re-resolve lives instead - see its own docstring's `_live` helper."""
    description: str = ""
    paid: bool = False

    requirement: CardRequirement | None = None
    """What the chosen cards have to be, when the cost says (CR 118.3)."""

    minimum_total_power: int | None = None
    """`ComponentKind.TAP` only: the combined power `cards` must reach or
    beat (CR 208.1) - Teamwork N's own "tap any number of creatures you
    control with total power N or more" (`machines/teamwork.py`). `None` for
    every ordinary tap cost, which asks nothing about power at all - convoke
    and crew tap a fixed count of objects, never a power total, so this is
    read only when it is set."""

    pay_mana_cost_of_chosen: bool = False
    """`ComponentKind.EXILE` only: Back from the Brink's own "... and pay its
    mana cost" shape (CR 118.9's "rather than pay [an alternative cost]" is
    not this - this is the *whole* cost, not an alternative to a printed
    one). The mana amount depends on which card is chosen, which is not
    known until the card is, so this only flags that the amount still needs
    adding once it is - `Game.activation_cost` is what reads the flag and
    folds `ManaCost.parse(card.mana_cost)` into the activation's mana cost
    for each chosen card, since a bare `CostComponent` has nowhere else to
    carry a mana requirement of its own."""

    zone: Zone = Zone.HAND
    """Where an `ComponentKind.EXILE` card must presently be (CR 406.2).

    Nothing in CR 406 ties exiling to the hand - a card can be exiled "from
    your graveyard" (Seasoned Pyromancer), "from your hand" (Force of Will), or
    from wherever it already is (a self-referential "Exile this card"). Only
    `EXILE` reads this; `DISCARD` is hand-only by definition (CR 701.9a: "To
    discard a card, move it from its owner's hand to that player's graveyard")
    and stays hardcoded.
    """

    link_to_permanent_id: UUID | None = None
    """`ComponentKind.EXILE`, and `ComponentKind.BEHOLD` when `exile_after` is
    set: the id of the permanent-to-be this exile cost's cards should be
    recorded as "exiled with" (CR 607.2q: "If a permanent spell has an
    ability printed on it that allows one or more cards to be exiled while
    paying a cost to cast it and the permanent that spell becomes has an
    ability that refers to cards 'exiled with [this object],' those
    abilities are linked. The second ability refers only to cards exiled to
    pay the cost of the spell that became that permanent.")

    Set by `machines/objects_as_costs.delve` to the delving spell's own
    `CardState.id` - which stays the same across the stack-to-battlefield
    zone change in this engine (`CardState.move_to`'s own docstring) - so
    Murktide Regent's own "a +1/+1 counter on it for each instant and sorcery
    card exiled with it" can find them again once it resolves. `None` for
    every other exile cost (Force of Will's hand exile, Seasoned Pyromancer's
    graveyard exile), which links nothing and changes nothing about how they
    pay.

    `Game.activation_cost`/the cast-cost builder set it the same way for a
    `BEHOLD` component whose printed text ends "... and exile it" (Champion
    of the Clachan: "behold a Kithkin and exile it") - CR 607.2q draws no
    distinction between an object exiled outright and one first beheld
    (CR 701.4a) and then exiled by the same sentence, so the permanent this
    spell becomes reads "the exiled card" back through the identical link
    `card_imprinted_on`/`cards_exiled_with` already resolve for delve."""

    exile_after: bool = False
    """`ComponentKind.BEHOLD` only: the printed cost does not stop at
    beholding (CR 701.4a's "reveal ... or choose ..."), it goes on to exile
    the same object - "behold a Kithkin **and exile it**" (Champion of the
    Clachan, Champions of the Perfect/Shoal, Champion of the Path/Weird),
    CR 118.8/601.2f's additional cost applying two verbs to one chosen
    object in the printed sentence.

    Whichever half of CR 701.4a's disjunction the payer chose - a card shown
    from hand (CR 701.20a-b's reveal, nothing moves) or a permanent they
    already control - is exiled once the choice is made: `pay` moves it with
    `Game.exile_cards` the same way a plain `EXILE` component does, and
    tags it `ExileMarker.LINKED` against `link_to_permanent_id` so the
    permanent this spell becomes can read "the exiled card" back
    (`_parse_return_imprinted_clause`, `machines/effects.py`). `False` for
    every ordinary behold cost (Silvergill Mentor's own "behold a Merfolk or
    pay {2}"), which leaves the beheld object exactly where CR 701.4a found
    it."""

    from_among: bool = False
    """`ComponentKind.REMOVE_COUNTERS` only: "Remove N counters from among
    creatures you control" (Dawnhand Dissident's cast permission, Quilled
    Greatwurm, Hopeful Initiate) - `amount` is the total taken across every
    chosen permanent (`cards`), not a count taken from each (CR 118.3: the
    counters have to be there, summed over the chosen permanents)."""
    every_matching: bool = False
    """`ComponentKind.SACRIFICE` only: "sacrifice all creatures you control"
    (Soulblast's additional cost), "Sacrifice all lands you control" (Tomb of
    Urami's activation cost). Nobody chooses: CR 601.2h pays it with every
    permanent the payer controls that meets `requirement` at the moment the
    cost is paid, so `cards` is filled by `pay` itself and an empty board
    pays it with nothing (CR 701.21a: only permanents the payer controls)."""
    variable_count: bool = False
    """The printed count is CR 107.3a's X or "one or more", so the number is
    whatever the payer announced or chose rather than one the text fixes. For
    `ComponentKind.REVEAL` ("Reveal X white cards from your hand") that is
    `required`, the number of cards they chose to reveal; for
    `ComponentKind.PAY_LIFE` ("Pay X life") and `REMOVE_COUNTERS` ("Remove X
    +1/+1 counters") it is `amount`; for the other object kinds it is
    `required`, which the reader leaves at the fewest that pays - 0 for X, 1
    for "one or more" - until `announce_count` fixes it."""

    source: str | None = None
    """The card whose cost this is, by name - the `Reveal.source` a paid
    `ComponentKind.REVEAL` records (CR 701.20a)."""

    _undo: list[tuple[CardState, dict[str, Any]]] = PrivateAttr(default_factory=list)
    """What `pay` changed, so `unpay` can put it back (CR 733.1). A
    `PrivateAttr`, so - unlike every `Field` above it - it does not survive a
    dump/decode round trip at all: a decoded `CostComponent` with `paid=True`
    always comes back with `_undo == []`. `unpay` refuses loudly rather than
    silently restoring nothing when that state was needed and is gone; see its
    own docstring."""

    _reveals_recorded: list[Any] = PrivateAttr(default_factory=list)
    """The `Reveal` records a paid `ComponentKind.REVEAL` wrote, so `unpay` can
    take exactly those back (CR 733.1). Private for the same reason `_undo` is."""

    def __str__(self) -> str:
        if self.description:
            return self.description
        if self.kind is ComponentKind.PAY_LIFE:
            return f"pay {self.amount} life"
        return f"{self.kind.value} {', '.join(card.name for card in self.cards) or self.required}"

    # -- legality ---------------------------------------------------------

    def why_not(self, game: Any) -> str | None:
        """Why this component cannot be paid, or None if it can (CR 118.3)."""
        if self.kind in _OBJECT_KINDS and len(self.cards) != self.required:
            return (
                f"{self.kind.value} needs {self.required} card(s) chosen, {len(self.cards)} given"
            )

        if self.requirement is not None:
            for card in self.cards:
                mismatch = self.requirement.why_not(card, game, self.payer)
                if mismatch is not None:
                    return mismatch

        checks = {
            ComponentKind.TAP: self._why_not_tap,
            ComponentKind.SACRIFICE: self._why_not_sacrifice,
            ComponentKind.DISCARD: lambda _: self._why_not_in_zone(Zone.HAND),
            ComponentKind.EXILE: lambda _: (
                self._why_not_in_zone(self.zone)
                or (self._why_not_controlled() if self.zone is Zone.BATTLEFIELD else None)
            ),
            ComponentKind.PAY_LIFE: self._why_not_life,
            ComponentKind.REMOVE_COUNTERS: self._why_not_remove_counters,
            ComponentKind.PLACE_COUNTERS: self._why_not_place_counters,
            ComponentKind.LOYALTY: self._why_not_loyalty,
            ComponentKind.EXERT: self._why_not_exert,
            ComponentKind.MILL: self._why_not_mill,
            ComponentKind.UNTAP: self._why_not_untap,
            ComponentKind.COLLECT_EVIDENCE: self._why_not_collect_evidence,
            ComponentKind.RETURN_TO_HAND: self._why_not_return_to_hand,
            ComponentKind.REVEAL: self._why_not_reveal,
            ComponentKind.BEHOLD: self._why_not_behold,
        }
        return checks[self.kind](game)

    def _why_not_behold(self, _game: Any) -> str | None:
        """CR 701.4a: "Reveal a [quality] card from your hand or choose a
        [quality] permanent you control on the battlefield." Each chosen
        object has to be in one of those two places - owned in hand, or
        controlled on the battlefield - the same ownership/control check
        `_why_not_reveal`/`_why_not_controlled` already make for each half."""
        seen: set[UUID] = set()
        for card in self.cards:
            if card.id in seen:
                return (
                    f"{card.name} is named more than once, but one object is beheld only "
                    "once to pay a cost (CR 109.1, CR 118.3)"
                )
            seen.add(card.id)
            if card.zone is Zone.HAND:
                if self.payer is not None and card.owner is not None and card.owner != self.payer:
                    return f"{card.name} is not in {self.payer}'s hand"
            elif card.zone is Zone.BATTLEFIELD:
                if (
                    self.payer is not None
                    and card.controller is not None
                    and card.controller != self.payer
                ):
                    return f"{self.payer} does not control {card.name}"
            else:
                return (
                    f"{card.name} is neither in {self.payer or 'the payer'}'s hand nor a "
                    "permanent they control, so it cannot be beheld (CR 701.4a)"
                )
        return None

    def _why_not_reveal(self, _game: Any) -> str | None:
        """CR 118.3 for a reveal cost: every card named has to be in the
        payer's own hand ("from your hand"), and a card is one object
        (CR 109.1) - naming it twice reveals one card, not two."""
        seen: set[UUID] = set()
        for card in self.cards:
            if card.id in seen:
                return (
                    f"{card.name} is named more than once, but one card is revealed only "
                    "once to pay a cost (CR 109.1, CR 118.3)"
                )
            seen.add(card.id)
        in_hand = self._why_not_in_zone(Zone.HAND)
        if in_hand is not None:
            return in_hand
        if self.payer is not None:
            for card in self.cards:
                if card.owner is not None and card.owner != self.payer:
                    return f"{card.name} is not in {self.payer}'s hand"
        return None

    def _why_not_untap(self, _game: Any) -> str | None:
        """CR 107.6: "A permanent that's already untapped can't be untapped
        again to pay the cost" - the exact mirror of CR 107.5's already-tapped
        refusal, and CR 701.26b says the same from the other side ("Only tapped
        permanents can be untapped").

        CR 602.5a's summoning-sickness half - "a creature's activated ability
        with the tap symbol ({T}) or the untap symbol ({Q}) in its activation
        cost can't be activated unless the creature has been under its
        controller's control since their most recent turn began" - is a
        restriction on *activating*, not on paying, and lives where the
        `{T}` half of the same sentence already does (`can_tap_for_mana`,
        `Game.activate_ability`), not here.
        """
        for card in self.cards:
            if card.zone is not Zone.BATTLEFIELD:
                return f"{card.name} is not on the battlefield, so it cannot be untapped"
            if not card.tapped:
                return f"{card.name} is already untapped, so it cannot be untapped to pay a cost"
        return self._why_not_controlled()

    def _why_not_collect_evidence(self, game: Any) -> str | None:
        """CR 701.59a-b: enough total mana value has to be there to exile.

        CR 701.59a fixes what the cost asks for - "exile any number of cards
        from your graveyard with total mana value N or greater" - and CR 701.59b
        is the "if unable" case: "if a player is given the choice to collect
        evidence but is unable to exile cards with total mana value N or greater
        from their graveyard ... they can't choose to do so." Choosing to pay a
        cost is such a choice, so a graveyard that cannot reach N refuses the
        payment outright rather than exiling what it can (CR 118.3).

        Cards already chosen are checked against the same threshold; an
        unchosen component is checked against the whole graveyard, because
        `pay` is what picks in that case.
        """
        if self.amount <= 0:
            # CR 118.5: a cost of nothing is paid by acknowledging it, and
            # "total mana value 0 or greater" is met by exiling nothing.
            return None
        if self.cards:
            for card in self.cards:
                if card.zone is not Zone.GRAVEYARD:
                    return f"{card.name} is in the {card.zone.value}, not the graveyard"
            controlled = self._why_not_controlled()
            if controlled is not None:
                return controlled
            total = sum(card.mana_value for card in self.cards)
            if total < self.amount:
                return (
                    f"the cards chosen have total mana value {total:g}, not the "
                    f"{self.amount} collect evidence {self.amount} asks for (CR 701.59a)"
                )
            return None
        if game is None or self.payer is None:
            return "collecting evidence needs a game and a player whose graveyard to exile from"
        graveyard = game.player(self.payer).cards_in(Zone.GRAVEYARD)
        available = sum(card.mana_value for card in graveyard)
        if available < self.amount:
            return (
                f"{self.payer}'s graveyard holds total mana value {available:g}, not the "
                f"{self.amount} collect evidence {self.amount} asks for (CR 701.59b)"
            )
        return None

    def _why_not_return_to_hand(self, game: Any) -> str | None:
        """ "Return an unblocked [attacking] creature you control to its
        owner's hand" - ninjutsu's cost (CR 702.49a) and sneak's (CR 702.190a).

        CR 509.1h is what "unblocked" means: "An attacking creature with one
        or more creatures declared as blockers for it becomes a blocked
        creature; one with no creatures declared as blockers for it becomes
        an unblocked creature" - so nothing is unblocked before blockers are
        declared, and a creature "remains blocked even if all the creatures
        blocking it are removed from combat" (`Attack.blocked`). Checked
        against the live combat, since nothing prints "unblocked" on a card.

        A component carrying a `requirement` is the other shape, read off a
        printed activation cost by `cost_component_for_phrase` - Tameshi,
        Reality Architect's "Return a land you control to its owner's hand":
        a permanent the payer controls that meets the requirement (checked by
        `why_not` itself), and nothing about combat.
        """
        if self.requirement is not None:
            for card in self.cards:
                if card.zone is not Zone.BATTLEFIELD:
                    return f"{card.name} is not on the battlefield, so it cannot be returned"
            return self._why_not_controlled()
        for card in self.cards:
            if card.zone is not Zone.BATTLEFIELD:
                return f"{card.name} is not on the battlefield, so it is not attacking"
            controlled = self._why_not_controlled()
            if controlled is not None:
                return controlled
            if game is None:
                return "returning an attacking creature needs a game to check combat"
            reason = why_not_unblocked(game, card)
            if reason is not None:
                return reason
        return None

    def _evidence_to_exile(self, game: Any) -> list[CardState]:
        """Which graveyard cards this collect-evidence cost exiles.

        CR 701.59a's "any number of cards" is a choice, and nothing in the
        engine makes it, so the cards are taken highest mana value first -
        the fewest cards that reach the threshold. A component whose cards
        were chosen already keeps them.
        """
        if self.cards:
            return list(self.cards)
        graveyard = sorted(
            game.player(self.payer).cards_in(Zone.GRAVEYARD),
            key=lambda card: card.mana_value,
            reverse=True,
        )
        chosen: list[CardState] = []
        total = 0.0
        for card in graveyard:
            if total >= self.amount:
                break
            chosen.append(card)
            total += card.mana_value
        return chosen

    def _why_not_mill(self, game: Any) -> str | None:
        """CR 701.17b: a player can't mill more cards than their library holds,
        and "if given the choice to do so, they can't choose to take that
        action" - choosing to pay a cost is such a choice, so a short library
        refuses the payment outright rather than milling fewer (CR 118.3)."""
        if self.amount < 0:
            return "a cost cannot ask for a negative number of cards to be milled"
        if self.amount == 0:
            return None
        if game is None or self.payer is None:
            return "milling as a cost needs a game and a player to mill"
        library = game.player(self.payer).cards_in(Zone.LIBRARY)
        if len(library) < self.amount:
            return (
                f"{self.payer} cannot mill {self.amount} card(s) from a library of "
                f"{len(library)} (CR 701.17b)"
            )
        return None

    def _why_not_remove_counters(self, _game: Any) -> str | None:
        """CR 118.3: the counters removed by a cost have to be there already.

        Same principle CR 118.3 states for a tapped permanent and CR 606.6
        states for a loyalty ability's negative cost - "a permanent that's
        already tapped can't [pay a cost that taps it]" generalises to any
        resource a cost spends, counters included, and the whole cost is
        checked before anything is spent.
        """
        if self.from_among:
            total = 0
            for card in self.cards:
                if card.zone is not Zone.BATTLEFIELD:
                    return (
                        f"{card.name} is not on the battlefield, so its counters cannot be removed"
                    )
                total += _removable_counters(card, self.counter_kind)
            if total < self.amount:
                return (
                    f"the chosen permanents have {total} counter(s) between them, not the "
                    f"{self.amount} this cost removes from among them (CR 118.3)"
                )
            return self._why_not_controlled()
        for card in self.cards:
            if card.zone is not Zone.BATTLEFIELD:
                return f"{card.name} is not on the battlefield, so its counters cannot be removed"
            if self.counter_kind == ANY_COUNTER_KIND:
                have = sum(count for _kind, count in card.counters.items())
                if have < self.amount:
                    return (
                        f"{card.name} has {have} counter(s), not the {self.amount} its "
                        "cost removes (CR 118.3)"
                    )
                continue
            if not card.can_remove_counters(self.counter_kind, self.amount):
                have = card.counter_count(self.counter_kind)
                return (
                    f"{card.name} has {have} {self.counter_kind} counter(s), not the "
                    f"{self.amount} its cost removes (CR 118.3)"
                )
        return self._why_not_controlled()

    def _why_not_place_counters(self, _game: Any) -> str | None:
        """Putting a counter on as a cost needs only a permanent to put it on.

        CR 122.6: "putting counters on an object" refers to it while it's on
        the battlefield, so a permanent that has already left has nothing to
        put a counter on. Unlike removing counters, there is no further
        resource requirement (CR 118.3) - a cost that puts a counter on is
        always payable once the permanent exists to receive it.
        """
        for card in self.cards:
            if card.zone is not Zone.BATTLEFIELD:
                return f"{card.name} is not on the battlefield, so a counter cannot be put on it"
        return self._why_not_controlled()

    def _why_not_loyalty(self, _game: Any) -> str | None:
        """CR 606.4 and 606.6: the counters go on or come off the source itself.

        CR 606.6: "A loyalty ability with a negative loyalty cost, taking into
        account any additional costs, can't be activated unless the permanent
        has at least that many loyalty counters on it." The counters must be
        there right now, because CR 118.3 has the whole cost checked before
        anything is spent.
        """
        for card in self.cards:
            if card.zone is not Zone.BATTLEFIELD:
                return f"{card.name} is not on the battlefield, so its loyalty cost cannot be paid"
            if self.amount < 0 and card.counters[Counter.LOYALTY] < -self.amount:
                return (
                    f"{card.name} has {card.counters[Counter.LOYALTY]} loyalty, not the "
                    f"{-self.amount} its cost removes (CR 606.6)"
                )
        return None

    def _why_not_exert(self, _game: Any) -> str | None:
        """CR 701.43b-c: only a permanent, and being tapped is no obstacle.

        "A permanent can be exerted even if it's not tapped or has already been
        exerted in a turn", so the only thing that can refuse this is CR 701.43c:
        "An object that isn't on the battlefield can't be exerted."
        """
        for card in self.cards:
            if card.zone is not Zone.BATTLEFIELD:
                return f"{card.name} is not on the battlefield, so it cannot be exerted"
        return self._why_not_controlled()

    def _why_not_tap(self, game: Any) -> str | None:
        for card in self.cards:
            if card.zone is not Zone.BATTLEFIELD:
                return f"{card.name} is not on the battlefield, so it cannot be tapped"
            if card.tapped:
                return f"{card.name} is already tapped, so it cannot be tapped to pay a cost"
        controlled = self._why_not_controlled()
        if controlled is not None:
            return controlled
        if self.minimum_total_power is not None:
            total = 0
            for card in self.cards:
                power = None
                if game is not None:
                    try:
                        power = game.characteristics_of(card).power
                    except KeyError:
                        power = None
                total += (power if power is not None else card.power) or 0
            if total < self.minimum_total_power:
                return (
                    f"total power {self.minimum_total_power} or more is needed, "
                    f"{total} offered (CR 208.1)"
                )
        return None

    def _every_matching_permanent(self, game: Any) -> list[CardState]:
        """`every_matching`'s objects: each permanent the payer controls that
        meets `requirement`, read off the computed board (CR 613.5)."""
        if self.payer is None:
            return []
        return [
            permanent
            for permanent in game.permanents_controlled_by(self.payer)
            if self.requirement is None
            or self.requirement.why_not(permanent, game, self.payer) is None
        ]

    def _why_not_sacrifice(self, game: Any) -> str | None:
        from .. import attacking_statics

        for card in self.cards:
            if card.zone is not Zone.BATTLEFIELD:
                return f"{card.name} is not a permanent, so it cannot be sacrificed"
            if game is not None and (why := attacking_statics.cant_be_sacrificed(game, card)):
                return why
        return self._why_not_controlled()

    def _why_not_controlled(self) -> str | None:
        """CR 701.21a: you can only sacrifice something you control."""
        if self.payer is None:
            return None
        for card in self.cards:
            if card.controller is not None and card.controller != self.payer:
                return f"{self.payer} does not control {card.name}"
        return None

    def _why_not_in_zone(self, zone: Zone) -> str | None:
        for card in self.cards:
            if card.zone is not zone:
                return f"{card.name} is in the {card.zone.value}, not the {zone.value}"
        return None

    def _why_not_life(self, game: Any) -> str | None:
        """CR 119.4: life can only be paid down to zero, and 0 is always payable."""
        if self.amount < 0:
            return "a cost cannot ask for a negative amount of life"
        if self.amount == 0:
            return None
        if game is None or self.payer is None:
            return "paying life needs a game and a player to pay it"
        life = game.player(self.payer).life
        if life < self.amount:
            return f"{self.payer} cannot pay {self.amount} life from a life total of {life}"
        return None

    # -- paying and rewinding ---------------------------------------------

    def pay(self, game: Any) -> None:
        if self.every_matching and game is not None and not self.paid:
            self.cards = self._every_matching_permanent(game)
            self.required = len(self.cards)
        reason = self.why_not(game)
        if reason is not None:
            raise ValueError(reason)
        if self.paid:
            raise ValueError(f"{self} has already been paid")

        if self.kind is ComponentKind.EXERT:
            for card in self.cards:
                self._remember(card)
                card.exerted = True  # CR 701.43a
        elif self.kind is ComponentKind.TAP:
            for card in self.cards:
                self._remember(card)
                card.tap()  # CR 701.26a: only untapped permanents can be tapped
                if game is not None:
                    # Tapping the permanent is the event (CR 701.26a); a unit
                    # test paying a component without a game emits nothing.
                    # Agent Maria Hill's own "becomes tapped to pay a
                    # teamwork cost" (`machines/triggers.GameEvent.
                    # tapped_for_teamwork`) - `minimum_total_power` is set
                    # only by `machines/teamwork.py`'s own component, never
                    # by an ordinary tap cost.
                    game.emit_became_tapped(
                        card, tapped_for_teamwork=self.minimum_total_power is not None
                    )
        elif self.kind is ComponentKind.SACRIFICE:
            for card in self.cards:
                self._remember(card)
                # A sacrifice cost is a sacrifice (CR 702.48b: "you sacrifice
                # that permanent as you pay the total cost"), and sacrificing
                # is CR 701.21a's move to the graveyard, not a destruction -
                # CR 701.8b destroys only from "destroy" effects or SBAs, and
                # an indestructible permanent is sacrificed all the same.
                game.sacrifice(card)
        elif self.kind is ComponentKind.DISCARD:
            # CR 701.9a's discard, through `Game.discard_cards` rather than
            # straight to the graveyard: madness (CR 702.35a) replaces where a
            # discarded card lands, and CR 603.2c's "whenever you discard one
            # or more cards" (Captain Howler, Sea Scourge) has to see every
            # card this one cost discarded as a single batch, cost-paid
            # discards included.
            for card in self.cards:
                self._remember(card)
            if self.cards:
                game.discard_cards(self.payer, list(self.cards), source=None)
        elif self.kind is ComponentKind.EXILE:
            for card in self.cards:
                self._remember(card)
            if self.cards:
                # `Game.exile_cards`, not `exile_permanent` per card: one cost
                # is one instruction, and CR 603.2c says "an ability triggers
                # only once each time its trigger event occurs. However, it can
                # trigger repeatedly if one event contains multiple
                # occurrences." A delve payment (CR 702.66a: "For each generic
                # mana in this spell's total cost, you may exile a card from
                # your graveyard rather than pay that mana") that exiles five
                # cards is one occurrence of "one or more cards leave your
                # graveyard", so Hardened Academic triggers once with a count
                # of five, not five times. Exiling card by card raised five
                # events and triggered it five times.
                #
                # CR 406.2: exile moves an object "from whatever zone it's
                # currently in" - not only a per-player zone the way the old
                # `game.player(self.payer).cards_in(card.zone).remove(card)`
                # assumed. Every exile-as-a-cost example before The Stone
                # Brain (Force of Will's hand, Seasoned Pyromancer's
                # graveyard) happened to be one of `self.payer`'s own
                # zones, so that assumption went untested until a cost
                # exiling a permanent straight off the shared battlefield
                # (`zone=Zone.BATTLEFIELD`) tried to remove it from a list
                # that was never holding it and raised `ValueError:
                # list.remove(x): x not in list` - Abstergo Entertainment's
                # own "Exile Abstergo Entertainment" cost hits the same gap.
                # `Game.exile_cards` already handles every zone generically -
                # battlefield departure events, token refusal (CR 111.8),
                # combat clean-up - so this delegates outright rather than
                # special-casing one more zone by hand.
                game.exile_cards(list(self.cards))
                self._link_exiled_cards(game)
        elif self.kind is ComponentKind.REVEAL:
            # CR 701.20a: showing the cards is the whole payment, and CR
            # 701.20b keeps them where they are. The record is what
            # `Game.known_to` reads, and it ends when the card leaves the hand
            # (CR 400.7). A component paid with no game has nobody to show.
            for card in self.cards:
                self._remember(card)
                if game is not None:
                    before = len(game.reveals)
                    game.reveal(card, source=self.source)
                    self._reveals_recorded.extend(game.reveals[before:])
        elif self.kind is ComponentKind.BEHOLD:
            # CR 701.4a's two halves: a hand card is revealed exactly like
            # `REVEAL` (nothing moves, CR 701.20b); a battlefield permanent is
            # simply chosen (CR 701.4b) and nothing happens to it at all -
            # not tapped, not sacrificed, not exiled - *unless* the printed
            # cost goes on to say "... and exile it" (`exile_after`), in
            # which case whichever half the payer satisfied it with is
            # exiled too, the same CR 607.2q link an ordinary `EXILE`
            # component's own cast-cost exile already carries.
            for card in self.cards:
                self._remember(card)
                if game is not None and card.zone is Zone.HAND and not self.exile_after:
                    before = len(game.reveals)
                    game.reveal(card, source=self.source)
                    self._reveals_recorded.extend(game.reveals[before:])
            if self.exile_after and self.cards and game is not None:
                # CR 701.20a's `game.reveal` record is for a card that stays
                # in a hidden zone after being shown; this one is about to
                # leave the hand for exile - a public zone, CR 400.2 - so the
                # move itself is what makes it visible, and recording a
                # separate reveal first would only track a fact no reader
                # needs once the card is sitting in the open anyway.
                game.exile_cards(list(self.cards))
                self._link_exiled_cards(game)
        elif self.kind is ComponentKind.RETURN_TO_HAND:
            # CR 702.49a's own cost: the creature leaves combat as it leaves
            # the battlefield (the zone change is what ends its being an
            # attacker), through `Game.return_to_hand` rather than a bare
            # zone move so a leaves-the-battlefield trigger still sees it.
            if game is not None:
                # One cost returning several permanents is one event (CR
                # 603.2c), so they leave together.
                with game.returning_together():
                    for card in self.cards:
                        self._remember(card)
                        game.return_to_hand(card)
            else:
                for card in self.cards:
                    self._remember(card)
        elif self.kind is ComponentKind.UNTAP:
            for card in self.cards:
                self._remember(card)
                # CR 107.6's "Untap this permanent", with `exert_applies=False`
                # because CR 701.43a delays one thing only - "it doesn't untap
                # during your next untap step" - and a cost is not that step.
                # The exert stays on for the step it was aimed at.
                card.untap(exert_applies=False)
        elif self.kind is ComponentKind.COLLECT_EVIDENCE and self.amount:
            # CR 701.59a's exile, through `Game.exile_cards` for the same
            # reason the `EXILE` branch above uses it: one cost is one
            # instruction, so a "one or more cards leave your graveyard"
            # trigger (CR 603.2c) sees a single batch however many cards the
            # threshold needed.
            chosen = self._evidence_to_exile(game)
            for card in chosen:
                self._remember(card)
            if chosen:
                game.exile_cards(list(chosen))
        elif self.kind is ComponentKind.MILL and self.amount:
            # CR 701.17a's move, routed through `Game.put_into_graveyard` so a
            # replacement effect watching a card enter a graveyard (Rest in
            # Peace) still gets its say - the same route `machines/effects._mill`
            # takes for a mill an *effect* performs.
            library = game.player(self.payer).cards_in(Zone.LIBRARY)
            for card in list(library[: self.amount]):
                self._remember(card)
                game.put_into_graveyard(card)
        elif self.kind is ComponentKind.PAY_LIFE and self.amount:
            game.lose_life(game.player(self.payer), self.amount)
        elif self.kind is ComponentKind.REMOVE_COUNTERS:
            # The counters come off at payment time (CR 601.2h/602.2b: the
            # cost is paid before the ability resolves), not when the
            # ability's effect resolves - Walking Ballista's damage and its
            # cost are two different things, and the counter is already gone
            # even if the ability is later countered on the stack.
            left = self.amount
            for card in self.cards:
                self._remember_counters(card)
                take = (
                    min(left, _removable_counters(card, self.counter_kind))
                    if self.from_among
                    else self.amount
                )
                left -= take
                if self.counter_kind == ANY_COUNTER_KIND:
                    for kind, count in any_counters_to_remove(card, take):
                        card.remove_counters(kind, count)
                    continue
                if take:
                    card.remove_counters(self.counter_kind, take)
        elif self.kind is ComponentKind.PLACE_COUNTERS:
            # Same timing as above, the other direction (Devoted Druid): the
            # counter lands on the permanent as the cost is paid, so a
            # toughness drop from a -1/-1 counter is visible immediately,
            # before the ability that untapped it has even resolved.
            #
            # CR 614.16: "if an effect would put one or more counters on a
            # permanent" replacement effects (Vizier of Remedies) "apply if
            # the effect of a resolving spell or ability ... [does so], and
            # they also apply if another replacement or prevention effect
            # does so, even if the original event being modified wasn't
            # itself an effect" - that last clause is written for exactly
            # this case, a cost's own counter (CR 118.1: a cost is an action,
            # not an effect). CR 118.11 backs it from the cost side: "the
            # actions performed when paying a cost may be modified by
            # effects [and] the cost has still been paid" either way. So this
            # routes through `Game.add_counters` - the same replacement path
            # a resolving effect's counters already use - rather than
            # mutating the permanent directly. A unit test that pays a
            # component with no `game` has no replacement machinery to ask,
            # so it falls back to placing the counters unmodified.
            for card in self.cards:
                self._remember_counters(card)
                if game is not None:
                    game.add_counters(card, self.counter_kind, self.amount)
                else:
                    card.add_counters(self.counter_kind, self.amount)
        elif self.kind is ComponentKind.LOYALTY:
            # CR 606.4: the counter change *is* the cost, so it happens at
            # payment time - on activation, before the ability is on the stack
            # doing anything (CR 602.2). CR 107.7: `[+N]` puts N loyalty
            # counters on, `[−N]` removes N, and `[0]` puts zero, which is a
            # payment with no event at all.
            #
            # The plus half goes through `Game.add_counters`, the same door
            # `PLACE_COUNTERS` uses, so a loyalty counter put on as a cost
            # raises the counters-put event and can be replaced (CR 614.16,
            # CR 118.11) exactly like any other counter a cost places. A
            # component paid with no `game` behind it - a unit test - has
            # nothing to ask and mutates the permanent directly.
            for card in self.cards:
                self._remember_counters(card)
                if self.amount > 0:
                    if game is not None:
                        game.add_counters(card, Counter.LOYALTY, self.amount)
                    else:
                        card.counters.add(Counter.LOYALTY, self.amount)
                elif self.amount < 0:
                    card.remove_counters(Counter.LOYALTY, -self.amount)

        self.paid = True

    def unpay(self, game: Any) -> None:
        """Put back exactly what paying took, in reverse order (CR 733.1).

        Two hazards, both about what a decode leaves behind:

        - `self._undo` is a `PrivateAttr` (see its own docstring) and does not
          survive a dump/decode round trip at all. A paid component whose
          `_undo` came back empty cannot be rewound - not "rewound to no
          effect", genuinely cannot, because the prior state it needs is gone -
          so this refuses loudly rather than silently doing nothing, the same
          choice `CostPayment._restore_payer_pool` makes for `_preexisting`.
          `PAY_LIFE` is exempt: its rewind only ever reads `self.amount` and
          `self.payer`, both plain fields that do survive.
        - Even when `_undo` did survive (the ordinary, non-decoded case), the
          `CardState`s it captured are the ones `self.cards` already held, and
          those are real, live objects only until the *next* round trip -
          `self.cards: list[CardState]` is not `Any`/excluded and would decode
          to copies with the same id as, but not the same identity as, the
          battlefield object, the identical hazard `_equip_effect`/`_crew_
          effect` had for `activation.card`. `_live` below re-resolves each
          one through `game.find_by_id` before mutating it; `game` is `None`
          only for a component paid outside a `Game` (a unit test), where the
          captured object is the only real one there is.
        """
        if not self.paid:
            return
        if (
            not self._undo
            and self.kind is not ComponentKind.PAY_LIFE
            and (self.cards or self.amount)
        ):
            raise RuntimeError(
                f"{self} was paid but its undo history (CostComponent._undo) "
                "did not survive a dump/decode round trip, so there is "
                "nothing left to rewind it from"
            )

        def _live(card: CardState) -> CardState:
            if game is None:
                return card
            found = game.find_by_id(card.id)
            return found if isinstance(found, CardState) else card

        if self.kind is ComponentKind.PAY_LIFE:
            if self.amount:
                game.player(self.payer).gain_life(self.amount)
        elif self.kind is ComponentKind.REVEAL:
            # Revealing moved nothing (CR 701.20b), so neither does the
            # rewind; it takes back the records the payment wrote, so an
            # attempt rewound under CR 733.1 leaves nobody knowing the cards.
            if game is not None:
                for record in self._reveals_recorded:
                    if record in game.reveals:
                        game.reveals.remove(record)
            self._reveals_recorded = []
        elif self.kind is ComponentKind.BEHOLD:
            if self.exile_after:
                # "... and exile it" actually moved the beheld object, the
                # same as a plain `EXILE` component, so the rewind is that
                # branch's own field-by-field restore (`self._return`) rather
                # than the no-op below.
                for card, snapshot in reversed(self._undo):
                    self._return(game, _live(card), snapshot)
            else:
                # Neither half moved anything (CR 701.4a/b), so the rewind is
                # the same as REVEAL's: only the reveal record a hand-half
                # payment wrote needs taking back.
                if game is not None:
                    for record in self._reveals_recorded:
                        if record in game.reveals:
                            game.reveals.remove(record)
                self._reveals_recorded = []
        elif self.kind is ComponentKind.EXERT:
            # Exerting moves nothing either, and CR 701.43b lets it be exerted
            # more than once, so the rewind is simply putting the flag back.
            for card, _ in reversed(self._undo):
                _live(card).exerted = False
        elif self.kind is ComponentKind.TAP:
            # Tapping moves nothing, so untapping is the whole rewind.
            for card, _ in reversed(self._undo):
                _live(card).untap(exert_applies=False)
        elif self.kind is ComponentKind.UNTAP:
            # Untapping moves nothing either, so re-tapping is the whole
            # rewind - the mirror of `TAP`'s above.
            for card, _ in reversed(self._undo):
                _live(card).tap()
        elif self.kind is ComponentKind.MILL:
            # CR 733.1: the rewind has to put the cards back *on top*, in the
            # order they were milled in - `_return` appends, which would leave
            # them on the bottom of the library. Walking `self._undo` backwards
            # and inserting each at index 0 restores the original order.
            for card, snapshot in reversed(self._undo):
                live = _live(card)
                self._return(game, live, snapshot)
                library = game.player(self.payer).cards_in(Zone.LIBRARY)
                if library and library[-1] is live:
                    library.pop()
                library.insert(0, live)
        elif self.kind in (
            ComponentKind.LOYALTY,
            ComponentKind.REMOVE_COUNTERS,
            ComponentKind.PLACE_COUNTERS,
        ):
            # The counters were mutated in place, and the permanent never left
            # the battlefield, so the rewind puts the snapshotted `Counters`
            # model back wholesale. Not `_return`, which removes the card from
            # its zone list and re-appends it - reordering the battlefield for
            # a payment that moved nothing.
            for card, snapshot in reversed(self._undo):
                _live(card).counters = snapshot["counters"]
        else:
            for card, snapshot in reversed(self._undo):
                self._return(game, _live(card), snapshot)

        self._undo = []
        self.paid = False

    def _link_exiled_cards(self, game: Any) -> None:
        """CR 607.2q: once `self.cards` are sitting in exile, tag each with
        `self.link_to_permanent_id` if this component carries one - the
        `EXILE` cost's own linking step, shared with `BEHOLD`'s
        `exile_after` shape (Champion of the Clachan's "behold a Kithkin and
        exile it") since both are the identical cast-cost exile CR 607.2q
        describes, just reached through a different keyword action.

        `linked_permanent_stamp` is left `None`: the id names the spell that
        is still on the stack right now, and its own stamp changes the
        moment it resolves onto the battlefield (`CardState.move_to`), so no
        stamp fixed here would ever equal the one the entering permanent
        reads it back with. `ExileAnnotation.links_to` already matches on
        the id alone whenever either side's stamp is `None`.
        """
        if self.link_to_permanent_id is None:
            return
        for card in self.cards:
            if card.zone is Zone.EXILE:
                card.exile_annotation = ExileAnnotation(
                    marker=ExileMarker.LINKED,
                    owner=card.owner,
                    turn_exiled=(game.turn.turns_taken if game.turn is not None else None),
                    linked_permanent_id=self.link_to_permanent_id,
                    linked_permanent_stamp=None,
                )

    def _remember(self, card: CardState) -> None:
        """Snapshot everything about a card except which printing it is.

        Taken field by field rather than by name, so a rewind still restores
        state that other parts of the model add to `CardState` later.
        """
        snapshot = {
            name: getattr(card, name)
            for name in type(card).model_fields
            if name not in {"id", "card"}
        }
        self._undo.append((card, snapshot))

    def _remember_counters(self, card: CardState) -> None:
        """Snapshot a card's counters for the rewind of a counter-based cost
        (loyalty, `PLACE_COUNTERS`, `REMOVE_COUNTERS`).

        Not `_remember`: that snapshots every field *by reference*, and paying
        one of these costs mutates `counters` in place (CR 122.1e - a loyalty
        counter *is* the planeswalker's loyalty, and the same in-place
        `Counters.add`/`.remove` backs every other counter kind), so a
        by-reference snapshot would record the payment as if it had already
        happened and the rewind would rewind nothing. A deep copy of the
        `Counters` model is what unpay restores.
        """
        self._undo.append((card, {"counters": card.counters.model_copy(deep=True)}))

    def _return(self, game: Any, card: CardState, snapshot: dict[str, Any]) -> None:
        """Take the card out of wherever paying put it and restore its old state."""
        for zone_cards in game.shared_zones.values():
            if card in zone_cards:
                zone_cards.remove(card)
        for player in game.players:
            for zone_cards in player.zones.values():
                if card in zone_cards:
                    zone_cards.remove(card)

        for name, value in snapshot.items():
            setattr(card, name, value)

        zone = card.zone
        if zone.is_shared:
            game.shared_zones[zone].append(card)
        else:
            owner = card.controller or self.payer
            game.player(owner).cards_in(zone).append(card)
            if zone is Zone.LIBRARY:
                game.player(owner).note_library_changed()  # CR 701.20d


def tap_cost(*cards: CardState, payer: str | None = None, description: str = "") -> CostComponent:
    """Tap permanents as a cost. Already-tapped permanents cannot pay (CR 118.3)."""
    return CostComponent(
        kind=ComponentKind.TAP,
        cards=list(cards),
        required=len(cards),
        payer=payer,
        description=description,
    )


def untap_cost(*cards: CardState, payer: str | None = None, description: str = "") -> CostComponent:
    """Untap permanents as a cost (CR 107.6's `{Q}`).

    "The untap symbol in an activation cost means 'Untap this permanent.' A
    permanent that's already untapped can't be untapped again to pay the cost"
    - the exact mirror of `tap_cost`, refused by `_why_not_untap` for the
    mirrored reason (CR 118.3).

    Built empty by `cost_component_for_phrase`, because `{Q}` is a
    self-reference (CR 107.6's "this permanent") and only the caller knows
    which permanent that is - the same shape `exert_cost` uses for
    "Exert this land".
    """
    return CostComponent(
        kind=ComponentKind.UNTAP,
        cards=list(cards),
        required=len(cards) or 1,
        payer=payer,
        description=description,
    )


def collect_evidence_cost(
    amount: int, payer: str | None = None, description: str = ""
) -> CostComponent:
    """Collect evidence N as a cost (CR 701.59a).

    "To 'collect evidence N' means to exile any number of cards from your
    graveyard with total mana value N or greater." The N rides in `amount`,
    because "any number of cards" fixes no count - the threshold is the whole
    demand, and `_why_not_collect_evidence` is what checks it against
    CR 701.59b's "if unable ... they can't choose to do so".
    """
    return CostComponent(
        kind=ComponentKind.COLLECT_EVIDENCE,
        amount=amount,
        payer=payer,
        description=description,
        zone=Zone.GRAVEYARD,
    )


def sacrifice_cost(
    *cards: CardState,
    payer: str | None = None,
    required: int | None = None,
    description: str = "",
) -> CostComponent:
    """Sacrifice permanents as a cost (CR 701.21a).

    `required` says how many the cost asks for, so a cost with nothing to
    sacrifice can be built and then correctly refuse to be paid.
    """
    return CostComponent(
        kind=ComponentKind.SACRIFICE,
        cards=list(cards),
        required=len(cards) if required is None else required,
        payer=payer,
        description=description,
    )


def exert_cost(
    *cards: CardState,
    payer: str | None = None,
    required: int | None = None,
    description: str = "",
) -> CostComponent:
    """Exert permanents as a cost (CR 701.43a).

    "To exert a permanent, you choose to have it not untap during your next
    untap step." Arena of Glory is the printing in this pool, and it exerts
    itself: `{R}, {T}, Exert this land: Add {R}{R}.`
    """
    return CostComponent(
        kind=ComponentKind.EXERT,
        cards=list(cards),
        required=len(cards) if required is None else required,
        payer=payer,
        description=description,
    )


def discard_cost(
    *cards: CardState,
    payer: str | None = None,
    required: int | None = None,
    description: str = "",
) -> CostComponent:
    """Discard cards from hand as a cost."""
    return CostComponent(
        kind=ComponentKind.DISCARD,
        cards=list(cards),
        required=len(cards) if required is None else required,
        payer=payer,
        description=description,
    )


def reveal_cost(
    *cards: CardState,
    payer: str | None = None,
    required: int | None = None,
    description: str = "",
    variable_count: bool = False,
) -> CostComponent:
    """Reveal cards from the payer's hand as a cost (CR 118.1, CR 701.20a).
    `CostComponent._why_not_reveal` is the check."""
    return CostComponent(
        kind=ComponentKind.REVEAL,
        cards=list(cards),
        required=len(cards) if required is None else required,
        payer=payer,
        description=description,
        variable_count=variable_count,
    )


def behold_cost(
    *cards: CardState,
    payer: str | None = None,
    required: int | None = None,
    description: str = "",
    exile_after: bool = False,
) -> CostComponent:
    """Behold a quality as a cost (CR 701.4a, CR 118.1): reveal a card from
    the payer's hand, or choose a permanent they control on the battlefield.
    `CostComponent._why_not_behold` is the check. `exile_after` is CR
    118.8/601.2f's "behold a [quality] and exile it" (Champion of the Weird),
    the second verb `pay` applies once the object is beheld."""
    return CostComponent(
        kind=ComponentKind.BEHOLD,
        cards=list(cards),
        required=len(cards) if required is None else required,
        payer=payer,
        description=description,
        exile_after=exile_after,
    )


def announce_reveal(
    component: CostComponent,
    revealing: Sequence[CardState] | None,
    x_value: int,
    source: str,
) -> CostComponent:
    """A reveal cost with the cards its payer named filled in (CR 601.2b).

    For a fixed count the count stands and the named cards must match it
    (`_why_not_reveal`, CR 118.3). For CR 107.3a's X the number revealed is
    the X announced: naming the cards fixes it, and an `x_value` announced as
    well has to agree. Nothing named leaves `required` at the announced
    `x_value` (0 when none was), which is a cost `legal_actions` can price and
    `Game.choose_cards_to_reveal` can ask about.

    `revealing=None` keeps whatever `component.cards` already held rather
    than wiping it to empty - CR 702.57a's own "Reveal this card from your
    hand" (`_PHRASE_REVEAL`'s `self_noun` branch) is filled in before this
    ever runs, by `Game.activation_cost`'s generic self-reference fill
    (`_cost_refers_to_self`), the same way "Exile this card" fills its own
    `ComponentKind.EXILE` component; nobody ever calls this with `revealing`
    for that shape; there is nothing to choose.
    """
    cards = list(revealing) if revealing is not None else list(component.cards)
    required = component.required
    if component.variable_count:
        if revealing is not None:
            if x_value and x_value != len(cards):
                raise ValueError(
                    f"X was announced as {x_value}, but {len(cards)} card(s) were named to "
                    f"pay {component.description!r} (CR 107.3a)"
                )
            required = len(cards)
        else:
            required = x_value
    return component.model_copy(update={"cards": cards, "required": required, "source": source})


def take_from_pool(component: CostComponent, pool: list[CardState]) -> None:
    """Fill a printed additional cost's object component from the objects the
    caster nominated for its kind (CR 601.2b), taking them off `pool`.

    A fixed count takes that many, in order. CR 107.1c's "any number of" and
    "one or more" (`variable_count` - CR 107.3a's X is already substituted
    into the phrase by now, so it reads as a fixed count) take every
    nominated object: the number is whatever the caster chose, zero included
    for "any number", and `required` becomes it. A component that already
    holds its objects, or is paid by `every_matching`, is left alone.
    """
    if component.cards or component.every_matching:
        return
    take = len(pool) if component.variable_count else component.required
    if not take:
        return
    component.cards = pool[:take]
    del pool[:take]
    if component.variable_count:
        component.required = max(component.required, len(component.cards))


def announce_count(component: CostComponent, x_value: int, nominated: int) -> CostComponent:
    """A variable-count component with its number fixed as the cost is paid.

    CR 107.3a: an X in the cost is the `x_value` announced - life paid,
    counters removed, or objects chosen. "One or more" is every one of the
    `nominated` objects, and never fewer than one (CR 118.3 then refuses a
    choice of none). A fixed count, and a reveal (`announce_reveal`), come
    back unchanged.
    """
    if not component.variable_count or component.kind is ComponentKind.REVEAL:
        return component
    if component.kind in {
        ComponentKind.PAY_LIFE,
        ComponentKind.REMOVE_COUNTERS,
        ComponentKind.PLACE_COUNTERS,
    }:
        return component.model_copy(update={"amount": x_value})
    if component.required:
        return component.model_copy(update={"required": max(component.required, nominated)})
    return component.model_copy(update={"required": x_value})


def cost_announces_x(cost_text: str) -> bool:
    """Whether a printed cost has an X in it (CR 107.3a: "a mana cost,
    alternative cost, additional cost, and/or activation cost with an {X},
    [-X], or X in it") - `{X}` and Martyr of Sands's bare "Reveal X white
    cards" alike - and "Remove any number of `<kind>` counters", whose number
    is announced the same way (The Astonishing Ant-Man)."""
    return (
        re.search(r"\bX\b", cost_text or "") is not None
        or _REMOVE_ANY_NUMBER_OF_COUNTERS.search(cost_text or "") is not None
    )


#: "Remove any number of `<kind>` counters" inside a printed cost.
_REMOVE_ANY_NUMBER_OF_COUNTERS = re.compile(
    r"\bremove any number of [\w+/−-]+ counters\b", re.IGNORECASE
)


def removes_announced_number_of_counters(cost_text: str) -> bool:
    """Whether a printed activation cost removes a number of counters the
    activator announced (CR 107.3a) - "Remove X ..." or "Remove any number of
    ..." - which "that many"/"that much" in the effect then counts."""
    return (
        _REMOVE_ANY_NUMBER_OF_COUNTERS.search(cost_text or "") is not None
        or re.search(r"\bremove x [\w+/−-]+ counters\b", cost_text or "", re.IGNORECASE) is not None
    )


def why_not_unblocked(game: Any, card: CardState) -> str | None:
    """Why `card` is not an unblocked creature right now, or None (CR 509.1h).

    Shared by the return-to-hand cost check and by sneak's own availability
    (`machines/casting.KeywordCastOption.why_not`), so both ask the one
    question the same way.
    """
    combat = getattr(game, "combat", None)
    attack = combat.attack_by(card.id) if combat is not None else None
    if attack is None:
        return f"{card.name} is not attacking, so it is not an unblocked creature (CR 509.1h)"
    if attack.blocked or attack.blockers:
        return f"{card.name} is blocked, so it is not an unblocked creature (CR 509.1h)"
    if not combat.blockers_declared:
        return (
            f"blockers have not been declared yet, so {card.name} is not an unblocked "
            f"creature (CR 509.1h)"
        )
    return None


def return_to_hand_cost(
    *cards: CardState,
    payer: str | None = None,
    required: int | None = None,
    description: str = "",
) -> CostComponent:
    """Return an unblocked attacking creature to its owner's hand as a cost
    (CR 702.49a's ninjutsu, CR 702.190a's sneak). `_why_not_return_to_hand`
    is the check."""
    return CostComponent(
        kind=ComponentKind.RETURN_TO_HAND,
        cards=list(cards),
        required=len(cards) if required is None else required,
        payer=payer,
        description=description,
    )


def exile_cost(
    *cards: CardState,
    payer: str | None = None,
    required: int | None = None,
    description: str = "",
    zone: Zone = Zone.HAND,
) -> CostComponent:
    """Exile cards as a cost (CR 406.2).

    `zone` is where the card has to presently be - `Zone.HAND` for Force of
    Will's "exile a blue card from your hand", `Zone.GRAVEYARD` for Seasoned
    Pyromancer's "Exile this card from your graveyard". Nothing in CR 406 ties
    exiling to the hand; only the printed cost does, so the reader is what
    decides it, not this builder's default.
    """
    return CostComponent(
        kind=ComponentKind.EXILE,
        cards=list(cards),
        required=len(cards) if required is None else required,
        payer=payer,
        description=description,
        zone=zone,
    )


def exile_and_pay_mana_cost_cost(
    *cards: CardState,
    payer: str | None = None,
    required: int | None = None,
    description: str = "",
    zone: Zone = Zone.GRAVEYARD,
    requirement: CardRequirement | None = None,
) -> CostComponent:
    """Back from the Brink: "Exile a creature card from your graveyard and
    pay its mana cost" (CR 406.2, CR 118.9's shape of naming a card's own
    mana cost as a cost - Emerge and Delve's own "pay [a card's] mana cost"
    templates read the identical way, just not in this pool). The mana
    amount itself is not known here - only once a card is chosen - so
    `pay_mana_cost_of_chosen` flags it for `Game.activation_cost` to add.
    """
    return CostComponent(
        kind=ComponentKind.EXILE,
        cards=list(cards),
        required=len(cards) if required is None else required,
        payer=payer,
        description=description,
        zone=zone,
        requirement=requirement,
        pay_mana_cost_of_chosen=True,
    )


def mill_cost(amount: int, payer: str | None = None, description: str = "") -> CostComponent:
    """Mill cards as a cost (CR 701.17a).

    "For a player to mill a number of cards, that player puts that many cards
    from the top of their library into their graveyard." Nothing is chosen, so
    the count rides in `amount` exactly as paying life does.

    CR 701.17b is what makes a short library refuse the payment rather than
    mill fewer: "A player can't mill a number of cards greater than the number
    of cards in their library. **If given the choice to do so, they can't
    choose to take that action.**" Paying a cost is a choice, so CR 118.3's
    "a player can't pay a cost without the resources to pay it fully" and
    CR 701.17b agree - the second sentence's "if instructed to do so, they mill
    as many as possible" is for an *effect* that mills, never for a cost.
    """
    return CostComponent(
        kind=ComponentKind.MILL,
        amount=amount,
        payer=payer,
        description=description,
    )


def pay_life_cost(amount: int, payer: str | None = None, description: str = "") -> CostComponent:
    """Pay life as a cost (CR 118.3b, 119.4)."""
    return CostComponent(
        kind=ComponentKind.PAY_LIFE,
        amount=amount,
        payer=payer,
        description=description,
    )


def loyalty_cost(
    card: CardState, amount: int, payer: str | None = None, description: str = ""
) -> CostComponent:
    """A loyalty symbol as a cost (CR 606.4, CR 107.7).

    `amount` is signed: positive puts that many loyalty counters on the
    permanent, negative removes them, and zero puts zero - `[0]` is still a
    cost, paid by putting zero counters, which is no event at all. The
    permanent is the ability's own source (CR 606.4), so there is nothing to
    choose, and CR 606.6 gates a negative amount on the counters being there.
    """
    return CostComponent(
        kind=ComponentKind.LOYALTY,
        cards=[card],
        amount=amount,
        payer=payer,
        description=description,
    )


#: The order `any_counters_to_remove` takes kinds in when the payer has not
#: said which: -1/-1 first (the one whose removal only ever helps the
#: permanent), then every other kind alphabetically - a documented default,
#: the same way `decisions.default_answer` documents its own.
_ANY_COUNTER_PREFERENCE = (Counter.MINUS_ONE.value,)


def _removable_counters(card: CardState, counter_kind: str) -> int:
    """How many counters of `counter_kind` (any kind, for `ANY_COUNTER_KIND`)
    `card` has to give."""
    if counter_kind == ANY_COUNTER_KIND:
        return sum(count for _kind, count in card.counters.items())
    return card.counter_count(counter_kind)


def fill_from_among(
    component: "CostComponent", game: Any, payer: str, chosen: list[CardState] | None
) -> None:
    """Choose the permanents a `from_among` counter-removal cost takes its
    counters from (CR 601.2b's choice, CR 601.2h's payment): the ones the
    payer named, in order, or - named none - every permanent the payer
    controls that meets the requirement and has such a counter, in
    battlefield order, until the total is reached."""
    if not component.from_among or component.cards:
        return
    if chosen:
        component.cards = list(chosen)
    elif game is not None:
        picked: list[CardState] = []
        total = 0
        for permanent in game.permanents_controlled_by(payer):
            if total >= component.amount:
                break
            if component.requirement is not None and (
                component.requirement.why_not(permanent, game, payer) is not None
            ):
                continue
            have = _removable_counters(permanent, component.counter_kind)
            if have:
                picked.append(permanent)
                total += have
        component.cards = picked
    component.required = len(component.cards)


def any_counters_to_remove(card: CardState, amount: int) -> list[tuple[str, int]]:
    """`(kind, count)` pairs taking `amount` counters of any kind off `card`
    - see `_ANY_COUNTER_PREFERENCE` for the order. Fewer than `amount` when
    the card has fewer; `_why_not_remove_counters` refuses that first."""
    present = dict(card.counters.items())
    order = [kind for kind in _ANY_COUNTER_PREFERENCE if present.get(kind)] + sorted(
        kind for kind in present if kind not in _ANY_COUNTER_PREFERENCE
    )
    removals: list[tuple[str, int]] = []
    left = amount
    for kind in order:
        if left <= 0:
            break
        take = min(left, present[kind])
        if take > 0:
            removals.append((kind, take))
            left -= take
    return removals


def remove_counters_cost(
    card: CardState | None,
    amount: int,
    counter_kind: CounterKind = Counter.PLUS_ONE,
    payer: str | None = None,
    description: str = "",
) -> CostComponent:
    """Remove counters from a permanent as a cost (CR 118.3, CR 122.1).

    Walking Ballista's "Remove a +1/+1 counter from this creature: It deals 1
    damage to any target" is the printing this reads (`cost_component_for_phrase`
    builds it from the sentence). Loyalty counters have their own component,
    `loyalty_cost`, where the counter change is the whole cost of a loyalty
    ability (CR 606.4) rather than a chosen amount of a chosen kind.

    `card` may be left `None` when the caller does not yet know which
    permanent this is - the self-referential "this creature" shape a printed
    cost sentence reads into, filled in by whoever resolves the self-reference
    (`Game.activation_cost`), the same way `exert_cost`/`exile_cost` do.
    """
    return CostComponent(
        kind=ComponentKind.REMOVE_COUNTERS,
        cards=[card] if card is not None else [],
        required=1,
        amount=amount,
        counter_kind=str(counter_kind),
        payer=payer,
        description=description,
    )


def place_counters_cost(
    card: CardState | None,
    amount: int,
    counter_kind: CounterKind = Counter.PLUS_ONE,
    payer: str | None = None,
    description: str = "",
) -> CostComponent:
    """Put counters on a permanent as a cost (CR 118.3, CR 122.1, CR 122.6).

    Devoted Druid's "Put a -1/-1 counter on this creature: Untap this
    creature." is the printing this reads. Unlike `remove_counters_cost`,
    nothing about the permanent's current counters can make this unpayable -
    only whether it is still there to receive one (`_why_not_place_counters`).

    `card` may be left `None` for the same self-referential reason
    `remove_counters_cost` allows it.
    """
    return CostComponent(
        kind=ComponentKind.PLACE_COUNTERS,
        cards=[card] if card is not None else [],
        required=1,
        amount=amount,
        counter_kind=str(counter_kind),
        payer=payer,
        description=description,
    )


# --------------------------------------------------------------------------
# The composite: mana plus components
# --------------------------------------------------------------------------


class TotalCost(EngineModel):
    """What casting a spell actually costs: a mana part and everything else.

    CR 601.2f calls this the total cost. It is what an alternative cost
    replaces and what an additional cost is added to.
    """

    mana: ManaCost = Field(default_factory=ManaCost)
    components: list[CostComponent] = Field(default_factory=list)

    waterbend_generic: int | None = None
    """CR 701.67b: when this total cost includes a waterbend cost, how much
    of `mana`'s generic is specifically the waterbend's own - the bound the
    alternate tap method (`machines/objects_as_costs.waterbend`) may not
    reach past, "even if the total cost ... includes other generic mana
    components." `None` for the ordinary case (no waterbend cost at all, or
    the whole of `mana`'s generic *is* the waterbend's own, which is every
    printing in the pool today - nothing prints a waterbend cost alongside
    another generic mana component in the same total cost yet). Set by
    `total_cost_for_phrase` when it folds in a `waterbend_mana_cost` piece,
    and carried onto the open `CostPayment` by `CostPayment.for_total`."""

    @classmethod
    def of(
        cls,
        mana: "ManaCost | str | None" = None,
        *components: CostComponent,
        waterbend_generic: int | None = None,
    ) -> "TotalCost":
        parsed = ManaCost.parse(mana) if isinstance(mana, str) else (mana or ManaCost())
        return cls(mana=parsed, components=list(components), waterbend_generic=waterbend_generic)

    @property
    def is_free(self) -> bool:
        """True if nothing at all has to be paid - not even {0} acknowledgement."""
        return self.mana.converted == 0 and not self.mana.x_count and not self.components

    def assign_payer(self, payer: str) -> "TotalCost":
        """Fill in who is paying on every component that did not say."""
        for component in self.components:
            if component.payer is None:
                component.payer = payer
        return self

    def __str__(self) -> str:
        parts = [str(self.mana)] if self.mana.converted or self.mana.x_count else []
        parts.extend(str(component) for component in self.components)
        return ", ".join(parts) or "{0}"


# --------------------------------------------------------------------------
# Cost increases and reductions (CR 601.2f, 118.7)
# --------------------------------------------------------------------------


def increase(cost: ManaCost, by: ManaCost) -> ManaCost:
    """Add a cost increase to a mana cost (CR 601.2f).

    Delegated to `ManaCost.plus`, which combines the two costs symbol for
    symbol. Rebuilding a total from generic and colour alone used to drop
    every hybrid, Phyrexian, and snow symbol, so Kitchen Finks with a kicker
    silently became `{1}` plus the kicker.
    """
    return cost.plus(by)


def reduce(cost: ManaCost, by: ManaCost) -> ManaCost:
    """Apply a cost reduction, following CR 118.7a-d, 118.7f-g.

    Delegated to `ManaCost.minus`, which is where those rules are worked out
    and where reducing *by* a hybrid symbol is refused (CR 118.7e).
    """
    return cost.minus(by)


def apply_modifications(
    base: ManaCost,
    increases: "list[ManaCost] | None" = None,
    reductions: "list[ManaCost] | None" = None,
    floor: int | None = None,
) -> ManaCost:
    """The mana part of a total cost, once increases and reductions are applied.

    CR 601.2f is where the total cost is worked out, and CR 118.9d confirms
    that additional costs, increases, and reductions all apply on top of an
    alternative cost. Increases are applied first here and reductions second;
    the rules text stating that order could not be retrieved in full from the
    rules search, so treat the ordering as this engine's choice rather than as
    a cited rule. It matters: reducing first and increasing after would let a
    reduction be undone by an increase that lands on top of it.

    What each reduction may touch *is* cited, in `ManaCost.minus`: CR 118.7a-d
    and 118.7f-g.

    `floor`, if given, is Trinisphere's shape - "each spell that would cost
    less than three mana to cast costs three mana to cast" - applied last, once
    every other increase and reduction has already run, because it reads
    "would cost", i.e. the cost as everything else has already left it. It is
    not a flat surcharge: only the shortfall against the floor is added, and
    always as generic mana, per Trinisphere's own reminder text ("a spell that
    would cost {1}{B} to cast costs {2}{B} to cast instead") - so a cost
    already at or above the floor is untouched, and one below it keeps its
    coloured pips and only gains enough generic to reach the floor.
    """
    total = base
    for extra in increases or []:
        total = increase(total, extra)
    for saving in reductions or []:
        total = reduce(total, saving)
    if floor is not None and total.converted < floor:
        total = increase(total, ManaCost.parse(f"{{{floor - total.converted}}}"))
    return total


# --------------------------------------------------------------------------
# Static cost-increase text on *other* permanents (CR 601.2f, 611.3)
# --------------------------------------------------------------------------
#
# Unlike `additional_cost_phrases`/`alternative_cost_phrases` below (a spell's
# own printed cost), these read a *different* permanent's static ability -
# Sphere of Resistance taxing every spell in the game, Trinisphere flooring
# them at three mana. Three shapes are recognised; anything else that mentions
# a cost increase is reported by `looks_like_unparsed_cost_modifier` so the
# caller can fail closed and record a notice instead of silently doing
# nothing, which is the exact defect this was written to fix (DDR#978).


class CostModifierKind(StrEnum):
    FLAT_INCREASE = "flat_increase"
    """"Spells cost {1} more to cast." / "Noncreature spells cost {1} more to
    cast." - Sphere of Resistance, Thorn of Amethyst, Lodestone Golem."""

    PER_SPELL_INCREASE = "per_spell_increase"
    """"Each spell a player casts costs {1} more to cast for each other spell
    that player has cast this turn." - Damping Sphere."""

    NAMED_INCREASE = "named_increase"
    """"Spells with the chosen name cost {3} more to cast." - Disruptor Flute.

    A flat increase like `FLAT_INCREASE`, but scoped by a CR 614.12a choice
    made as the source entered (`CardState.choice`, `ChoiceKind.CARD_NAME`)
    rather than by a card type, so the amount alone cannot say who it taxes:
    `Game.static_cost_modifiers_for` reads the chosen name off the permanent
    and compares it to the spell's own name."""

    FLOOR = "floor"
    """"Each spell that would cost less than [N] mana to cast costs [N] mana
    to cast." - Trinisphere."""

    CHOSEN_TYPE_DECREASE = "chosen_type_decrease"
    """"Spells you cast of the chosen type cost `{N}` less to cast." -
    Gathering Stone; "Creature spells of the chosen type cost `{N}` less to
    cast." - Urza's Incubator (Modern-legal proof printing, `creature_only`/
    `scoped_to_caster` reading its two wording differences). `NAMED_
    INCREASE`'s own twin: a `TYPE_DECREASE`-shaped discount scoped by a
    CR 614.12a choice (`CardState.choice`, `ChoiceKind.CREATURE_TYPE`)
    rather than by a subtype fixed on the card - the amount alone cannot say
    which subtype it discounts, so `Game.static_cost_modifiers_for` reads
    the chosen type off the permanent the same way it already reads `NAMED_
    INCREASE`'s chosen name."""

    COLOR_DECREASE = "color_decrease"
    """"`<Color>` spells you cast cost `{N}` less to cast." - the Medallion
    cycle (Ruby Medallion, etc.). "You cast" makes this controller-scoped,
    unlike the increase kinds above: `Game.static_cost_modifiers_for` only
    applies it when the permanent's controller is the one casting."""

    TYPE_DECREASE = "type_decrease"
    """"`<Type[ and Type]>` spells you cast cost `{N}` less to cast." (Ral,
    Monsoon Mage's front-face static, Goblin Electromancer) or its "Non-"
    qualified opposite, "`<Nontype>` spells you cast cost `{N}` less to
    cast." (Artist's Talent's level 2). Controller-scoped the same way as
    `COLOR_DECREASE`. Exactly one of `applies_to_types`/`excludes_type` is
    set, matching which of the two shapes was printed."""

    SYMBOL_DECREASE = "symbol_decrease"
    """"Spells you cast cost `<mana symbols>` less to cast." - unqualified, and
    written in mana symbols rather than one generic number: Aang, Master of
    Elements' own "{W}{U}{B}{R}{G}", The Immortal Sun's "{1}". The symbols are
    kept whole in `reduction` and handed to CR 601.2f as a cost reduction,
    where `ManaCost.minus` applies CR 118.7a-c to each one: a coloured symbol
    takes a pip of its own colour first and generic mana where the spell has
    none of that colour. Controller-scoped ("you cast") the same way as
    `COLOR_DECREASE`/`TYPE_DECREASE`."""

    ZONE_DECREASE = "zone_decrease"
    """"Spells you cast from `<zone>` cost `{N}` less to cast." - Bilbo, Thief
    in the Night's "from anywhere other than your hand". CR 601.2f reads the
    zone the spell was cast from (CR 601.2a's "from where it is to the
    stack"), carried in by `Casting.total_cost`. Exactly one of `from_zone`/
    `not_from_zone` is set. Controller-scoped ("you cast") the same way as
    `COLOR_DECREASE`/`TYPE_DECREASE`."""

    OPPONENT_TYPE_INCREASE = "opponent_type_increase"
    """"[<Qualifier> s]pells your opponents cast cost `{N}` more to cast." -
    Thalia, the Survivor's own "Noncreature spells your opponents cast cost
    {1} more to cast.", and the unqualified "Spells your opponents cast cost
    {1} more to cast." this same shape covers with `excludes_type` left
    `None`. `FLAT_INCREASE`'s own mirror, scoped the other way round from
    `COLOR_DECREASE`/`TYPE_DECREASE`: those apply only when the permanent's
    controller *is* the caster, this only when they are not
    (`Game.static_cost_modifiers_for`)."""

    TARGETING_THIS_INCREASE = "targeting_this_increase"
    """"Spells your opponents cast that target this creature cost `{N}` more to
    cast." - Pursued Whale. Keyed on the targets announced at CR 601.2c, which
    is why it can be priced at CR 601.2f at all: it taxes a spell only when
    one of the spell's chosen targets is the permanent carrying the line, and
    only when the caster is not that permanent's controller
    (`Game.static_cost_modifiers_for`, which is handed `Casting.targets`)."""


class CostModifierEffect(EngineModel):
    """One static cost-modifying ability, read off a permanent's oracle text."""

    model_config = ConfigDict(frozen=True)

    kind: CostModifierKind
    amount: int
    """The flat/per-spell surcharge, the floor's minimum mana value, or the
    decrease amount."""

    excludes_type: Type | None = None
    """`FLAT_INCREASE`/`TYPE_DECREASE`: the printed type the qualifier
    excludes - `Type.CREATURE` for "Noncreature spells", `Type.ARTIFACT` for
    "Nonartifact spells". `None` on `FLAT_INCREASE` means the increase is
    unconditional, like Sphere of Resistance's own "Spells cost {1} more to
    cast."."""

    requires_untapped: bool = False
    """`FLOOR` only: Trinisphere's "As long as this artifact is untapped,"
    condition (CR 611.3b keeps a static ability live only while its source
    carries it, and being tapped turns this one off)."""

    applies_to_color: Color | None = None
    """`COLOR_DECREASE` only: the one color named."""

    applies_to_types: tuple[Type, ...] | None = None
    """`TYPE_DECREASE` only, when the printed shape names type(s) positively
    ("Instant and sorcery spells...") rather than by exclusion - a spell
    needs only one of these types to qualify (CR 205.2a: a multi-type card is
    checked against all its types)."""

    applies_to_subtype: str | None = None
    """`TYPE_DECREASE` only, for the subtype shape - Goblin Warchief's "Goblin
    spells you cast cost {1} less to cast." - lowercased (`canonical_subtype`).
    A spell qualifies when it has that subtype (CR 205.3), which a changeling
    spell always does for a creature type (CR 702.73a)."""

    creature_only: bool = False
    """`CHOSEN_TYPE_DECREASE` only: Urza's Incubator's own "**Creature**
    spells of the chosen type cost `{2}` less to cast" - the spell must be a
    creature spell (CR 300.1) as well as carry the chosen subtype, not any
    spell that merely carries it (Gathering Stone's own "Spells you cast of
    the chosen type" has no such extra demand, `False`)."""

    scoped_to_caster: bool = True
    """`CHOSEN_TYPE_DECREASE` only: whether the printed sentence says "you
    cast" (Gathering Stone - the discount is this permanent's own
    controller's alone) or omits it (Urza's Incubator's "Creature spells of
    the chosen type cost {2} less to cast", CR 601.2f's cost reduction
    naming no caster at all, so it discounts *whichever* player casts one -
    an unusual, genuinely symmetric effect, not a defect in reading it)."""

    condition: str | None = None
    """A trailing "as long as `<condition>`" (Gran-Gran's "... as long as
    there are three or more Lesson cards in your graveyard"): the effect
    applies only while `Game.condition_holds` answers true for the source's
    controller (CR 604.2, CR 611.3a - read each time a cost is determined,
    never locked in). `None` for an unconditional effect."""

    first_each_turn: bool = False
    """`TYPE_DECREASE` only: "The first `<type>` spell you cast each turn"
    (Eluge, the Shoreless Sea; Melek, Reforged Researcher) - the decrease
    applies only while the caster has cast no earlier spell of those types
    this turn (`Game.spells_cast_this_turn`; the spell being cast is not in
    it yet, CR 601.2f coming before CR 601.2i)."""

    colored: Color | None = None
    """`TYPE_DECREASE` only: a colored decrease, "costs {U} (or {1}) less" -
    `amount` of that color per unit (CR 118.7b-c turn it into generic when the
    cost has not enough of that color; the "(or {1})" is only that reminder).
    `None` for the ordinary generic "{N} less"."""

    reduction: str | None = None
    """`SYMBOL_DECREASE` only: the printed mana symbols, "{W}{U}{B}{R}{G}" or
    "{1}", read back with `ManaCost.parse` when the cost is determined."""

    from_zone: Zone | None = None
    """`ZONE_DECREASE` only: "from your graveyard"/"from exile"."""

    not_from_zone: Zone | None = None
    """`ZONE_DECREASE` only: "from anywhere other than your hand"."""

    per_each: str | None = None
    """`TYPE_DECREASE` only: a "for each `<count>`" tail (Eluge's "for each
    land you control with a flood counter on it", Mindsplice Apparatus's "for
    each oil counter on this artifact") - the decrease is multiplied by that
    count, read afresh each time a cost is determined."""

    per_equipped_power: bool = False
    """`TYPE_DECREASE` only: "..., where X is equipped creature's power."
    (Glamdring, Foe-hammer) - `amount` is ignored and the decrease is instead
    the permanent's own equipped creature's power (CR 301.5a), read fresh
    each time a cost is determined (CR 611.3a: a static ability's own
    magnitude is never locked in) and floored at zero the same way an
    unequipped Equipment or a negative-power creature already floors any
    other `TYPE_DECREASE`'s own `units <= 0` check."""
    grants_flash: bool = False
    """`TYPE_DECREASE`/`first_each_turn` only: Radagast of Rhosgobel's own
    trailing "and can be cast as though it had flash" - CR 702.8a's flash
    exception, granted alongside the reduction rather than as a separate
    sentence. Read by `Game.has_first_spell_flash_grant`, the activated-cost
    twin of the reduction `_counted_type_decrease` already computes for the
    same permanent."""

    requires_toughness_greater_than_power: bool = False
    """`TYPE_DECREASE` only: Doran, Besieged by Time's own "Each creature
    spell you cast with toughness greater than its power costs {1} less to
    cast." - an extra filter on the spell itself (CR 208.1), asked alongside
    `applies_to_types` rather than replacing it, since the spell still has to
    be a creature spell first. Read off the spell's own power/toughness as it
    is right now (`CardState.power`/`toughness`, CR 208.5's 0 default for one
    that cannot be determined) - a spell on the stack has no board of its own
    to compute layers against, so this is the printed value plus its own
    counters, the same "right now" every other `TYPE_DECREASE` amount reads."""

    excludes_subtype: str | None = None
    """`TYPE_DECREASE`/`first_each_turn` only: Momo, Friendly Flier's own
    "The first **non-Lemur** creature spell ... costs {1} less to cast." - a
    negative subtype filter alongside `applies_to_types`, asked of the spell
    itself (CR 205.3, `CardState.subtypes`) rather than the source. Lowercased
    the same way `applies_to_subtype` is."""

    requires_keyword: str | None = None
    """`TYPE_DECREASE`/`first_each_turn` only: Momo's own "... creature spell
    **with flying** you cast ..." - the spell itself must carry the named
    combat keyword (`combat.has_keyword`, which reads a spell's own printed
    keywords off the stack the same way `requires_toughness_greater_than_
    power` reads its printed power/toughness, since a spell has no
    battlefield to compute layers against yet)."""


class CostModifierNotice(EngineModel):
    """One permanent whose cost-modifying text could not be read (DDR#978).

    The same "unreadable is not the same as no effect" record `TargetingNotice`
    and `InterveningIfNotice` already keep in `machines/triggers.py`: a cost
    increase that silently fails to apply is indistinguishable from ordinary
    play - nobody is refused, nothing looks wrong - which is exactly how
    Trinisphere sat on a battlefield for several playtest turns doing nothing
    and nobody noticed. `Game.static_cost_modifiers_for` appends one of these
    instead of skipping the permanent quietly.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    """The permanent's own oracle text, for whoever reads the notice later."""


# --------------------------------------------------------------------------
# "Activated abilities of <group> you control cost {N} less to activate"
# (CR 601.2f via CR 602.2b) - a board-wide static discount on *other*
# permanents' activation costs, the general template Hulk, Gamma Goliath's
# own narrower "Power-up abilities of other creatures you control cost {N}
# less to activate" (`Game._POWER_UP_GROUP_DISCOUNT_RE`) is one hardcoded
# instance of. Read here as a pure text parse - the group it names and the
# amount - the same division of labour `cost_modifier_effect` already keeps
# with `Game.static_cost_modifiers_for`'s own board-wide aggregation: this
# function answers "what does this one line say", `Game.activation_cost`
# answers "which of my permanents does it apply to, right now".
# --------------------------------------------------------------------------


class ActivatedAbilityGroupDiscount(EngineModel):
    """One "activated abilities of `<group>` you control cost `{N}` less to
    activate" static line (CR 601.2f, via CR 602.2b), read off its own text.

    `quality` is left as the printed words ("artifact tokens", "creatures",
    "Foods") for `Game`'s own board-wide reader to match against a
    permanent's computed characteristics - the identical split
    `ActivationCostReduction.quality` already keeps for a *self* discount's
    own "for each `<quality>` you control" (`Game.activation_cost_reduction_
    for`), generalised here to a *group* discount that names no "for each"
    count at all: every qualifying permanent's activation gets the flat
    `amount`, not a multiple of how many there are.
    """

    model_config = ConfigDict(frozen=True)

    quality: str
    amount: int
    floor_one: bool
    """"This effect can't reduce the mana in that cost to less than one
    mana." - Forensic Gadgeteer's, Training Grounds's, Heartstone's own
    trailing sentence (Mutagen Man's own printing carries no such sentence at
    all, `floor_one=False`). Read as a flag rather than folded into `amount`
    because it is a *cap* on the result of subtracting `amount`, not a
    further subtraction of its own - `Game._activated_ability_group_discount`
    is what actually clamps a reduction against the cost it is reducing."""


class AlternativeCostOffer(EngineModel):
    """One CR 118.9 "rather than pay this spell's mana cost" offer, read off a
    spell's own printed text rather than off a named keyword - Force of
    Will's pitch cost is inline text, not a keyword the way Evoke or
    Flashback is, so `_option_from_keyword` never sees it.
    """

    model_config = ConfigDict(frozen=True)

    phrase: str
    requires_not_your_turn: bool = False
    """Force of Negation's and Force of Vigor's own gate: the offer only
    exists "if it's not your turn"."""


class StaticFreeCastGrant(EngineModel):
    """A permanent's static ability applying CR 118.9's alternative cost of
    *nothing at all* to spells its controller casts - Omniscience.

    Distinct from `AlternativeCostOffer` in where it is read from: that one is
    the spell's own CR 604.6 static ability, functioning from the zone it is
    cast from, and this one is CR 604.2's ordinary battlefield static ability
    reaching out at somebody else's spell. Distinct from `PlayPermission` in
    what it does: this grants no permission to cast anything that could not
    already be cast (the card is in hand, where it was always castable), only
    a different thing to pay (CR 118.9c).
    """

    model_config = ConfigDict(frozen=True)

    zone: Zone
    """Where the spell has to be cast from for the grant to apply."""
    type_word: str | None = None
    """The card type the grant is narrowed to, lowercased ("creature spells
    from your hand"), or None for every spell."""
    max_mana_value: int | None = None
    """A printed literal cap ("mana value 3 or less"), or None when the grant
    prints no fixed number - either no cap at all, or `max_mana_value_quality`'s
    live one. Exactly one of the two is ever set."""
    max_mana_value_quality: str | None = None
    """Omnipresence's own live cap, as the printed quality phrase ("the
    number of creatures you control") rather than a precomputed count - this
    is a live board read at CR 601.2f, not a fact fixed when the permanent
    entered, so nothing here may cache a number. `mana_value_cap_for` counts
    it against the board when the grant is actually checked."""
    once_each_of_your_turns: bool = False
    """"Once during each of your turns, you may cast ..." (Zaffai and the
    Tempests, One with the Multiverse): one use per turn of the granting
    permanent, only while its controller is the active player."""
    also_top_of_library: bool = False
    """"from your hand or the top of your library" (One with the
    Multiverse) - the top card of the library is a second zone the grant
    reaches."""
    once_per_turn_key: str | None = None
    """The granting permanent as that object (`machines/casting.
    once_per_turn_key`, CR 400.7), filled in by `machines/casting.
    static_free_cast_grants` for a once-each-turn grant - what records the
    one use in `Game.once_per_turn_cast_permissions_used`."""


#: `Waterbend {3}` (Flexible Waterbender) - CR 701.67a: "'Waterbend [cost]'
#: means 'Pay [cost]. For each generic mana in that cost, you may tap an
#: untapped artifact or creature you control rather than pay that mana.'" The
#: cost half is plain mana and is read here; the tapping half is CR 701.67b's
#: alternate payment method, which - like convoke (CR 702.51b) - applies only
#: after the total cost is determined, and so lives on an already-open
#: `CostPayment` in `machines/objects_as_costs.waterbend`, not here.
_PHRASE_WATERBEND = re.compile(r"^waterbend (?P<cost>(?:\{[^{}]+\})+)$", re.IGNORECASE)


def waterbend_mana_cost(phrase: str) -> ManaCost | None:
    """The mana a `Waterbend [cost]` phrase asks for, or None if that is not
    what this phrase is (CR 701.67a).

    Separate from `cost_component_for_phrase` because a waterbend cost is
    *mana*, and a `CostComponent` has nowhere to carry mana - `TotalCost` is
    the shape that does, which is why `total_cost_for_phrase` is where this is
    folded in.
    """
    match = _PHRASE_WATERBEND.match(phrase.strip().rstrip("."))
    if match is None:
        return None
    return ManaCost.try_parse(match.group("cost"))


def _cost_count(word: str) -> tuple[int, bool] | None:
    """An object cost's count as (the fewest that pays it, whether the payer
    decides the number), or None when `word` is not a count.

    A printed number is exact. CR 107.3a's X is announced as the cost is paid
    and may be 0. "One or more" is every object the payer chooses, at least
    one. CR 107.1c's "any number of" is the same choice with a floor of zero
    - declining is legal, unlike "one or more" - so it shares X's own (0,
    True) answer rather than ONE_OR_MORE's floor of one. The chosen number is
    filled in by `announce_count`.
    """
    quantity = parse_quantity(word)
    if quantity is None:
        return None
    if quantity.source in (QuantitySource.X, QuantitySource.ANY_NUMBER):
        return 0, True
    if quantity.source is QuantitySource.ONE_OR_MORE:
        return 1, True
    if quantity.source is QuantitySource.FIXED and quantity.amount is not None:
        return quantity.amount, False
    return None


class CostSubstitution(EngineModel):
    """One object standing in for one mana symbol of a total cost.

    The shared shape behind convoke (CR 702.51a) and delve (CR 702.66a), and
    the reason they are one subsystem rather than two special cases: both are
    static abilities that function while the spell is on the stack, both apply
    only *after* the total cost has been determined (CR 702.51b, CR 702.66b),
    and both say the same thing about one symbol - "you may [do something to an
    object] **rather than pay that mana**".

    So a substitution is not mana, not a cost reduction, and not an alternative
    cost. It is a symbol of the already-determined cost that will be paid by
    `component` (a tap, an exile) instead of out of the pool. `option` is which
    symbol it covers - `PaymentOption(generic=1)` for a generic one, or
    `PaymentOption(color=...)` for a coloured one, which is exactly the split
    CR 702.51a draws between "for each colored mana in this spell's total cost"
    and its generic half.

    `component` is an ordinary `CostComponent`, so the tapping or exiling is
    paid by `CostPayment.pay` alongside every other component and is undone by
    `cancel`/`rewind` through the same CR 733.1 reversal. Nothing about
    substitution needs its own undo path.

    Who may be substituted, and what they may cover, is not decided here -
    `machines/objects_as_costs.py` holds the eligibility rules each keyword
    prints. This module only knows that a symbol can be paid by an object.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    keyword: str
    """What offered it - "convoke", "delve" - for the refusal messages."""

    rule: str
    """The CR number that keyword expands to, quoted in refusals."""

    card_id: UUID
    card_name: str
    """The id and name of the object paying this symbol, kept as plain data
    rather than the `CardState` itself - `component.cards` next door already
    holds the same object for the actual tap or exile, so a `card: CardState`
    field here was a second, redundant reference to it, dumping a whole extra
    copy of the same permanent on every serialization for no reader that
    needed more than its id and name (`__str__`'s message, and `entry.card.id`
    in `machines/objects_as_costs.py`'s own-object check)."""
    option: PaymentOption
    component: CostComponent

    def __str__(self) -> str:
        return f"{self.card_name} pays {self.option} ({self.keyword}, {self.rule})"


def cost_less(cost: ManaCost, options: Iterable[PaymentOption]) -> ManaCost:
    """`cost` with the symbols `options` cover taken out of it.

    Not `ManaCost.minus`, which is a cost *reduction* - this is the arithmetic
    of "that mana is not paid because an object paid it instead", and the
    difference matters for the messages and for what `converted` a caller sees.
    A generic option eats one point off a generic symbol (`{7}` becomes `{6}`,
    and disappears at zero); a coloured option removes one symbol of that
    colour.

    Symbols nothing covers are left exactly where they were, in printed order,
    so what remains still reads as a real cost.
    """
    generic = sum(option.generic for option in options)
    colored: dict[Color, int] = {}
    for option in options:
        if option.color is not None:
            colored[option.color] = colored.get(option.color, 0) + 1

    remaining: list[ManaSymbol] = []
    for symbol in cost.symbols:
        if symbol.kind is SymbolKind.GENERIC and generic:
            taken = min(generic, symbol.amount)
            generic -= taken
            if symbol.amount - taken:
                remaining.append(ManaSymbol(kind=SymbolKind.GENERIC, amount=symbol.amount - taken))
            continue
        if symbol.kind is SymbolKind.COLORED and colored.get(symbol.colors[0], 0):
            colored[symbol.colors[0]] -= 1
            continue
        remaining.append(symbol)
    return ManaCost(symbols=tuple(remaining))


from ._common import ANY_COUNTER_KIND  # noqa: E402
