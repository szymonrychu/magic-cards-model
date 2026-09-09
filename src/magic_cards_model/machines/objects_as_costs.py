"""Paying a cost with objects instead of with mana.

Five keywords in this pool ask a player to tap or exile things rather than
spend mana, and they are one subsystem, not five:

- **Convoke** (CR 702.51a) - "Convoke is a static ability that functions while
  the spell with convoke is on the stack. 'Convoke' means 'For each colored
  mana in this spell's total cost, you may tap an untapped creature of that
  color ...'". The reminder text printed on Conclave Tribunal spells the
  generic half out: "Each creature you tap while casting this spell pays for
  {1} or one mana of that creature's color."
- **Delve** (CR 702.66a) - "Delve is a static ability that functions while the
  spell with delve is on the stack. 'Delve' means 'For each generic mana in
  this spell's total cost, you may exile a card from your graveyard rather than
  pay that mana.'"
- **Improvise** (CR 702.126a) - "Improvise is a static ability that functions
  while the spell with improvise is on the stack. 'Improvise' means 'For each
  generic mana in this spell's total cost, you may tap an untapped artifact you
  control rather than pay that mana.'" Word for word convoke's generic half
  with a different type filter, which is exactly how it is built here.
- **Waterbend** (CR 701.67a) - "'Waterbend [cost]' means 'Pay [cost]. For each
  generic mana in that cost, you may tap an untapped artifact **or creature**
  you control rather than pay that mana.'" One step wider than improvise, and
  the only member of the family that is an action word on an *ability's* cost
  rather than a static ability of a spell.
- **Crew** (CR 702.122a) - "Crew is an activated ability of Vehicle cards.
  'Crew N' means 'Tap any number of other untapped creatures you control with
  total power N or greater: This permanent becomes an artifact creature until
  end of turn.'"

What they share is the eligibility question - *which* objects may be spent this
way, in which zone, and what happens to them - and that is what `ObjectOffer`
is. What differs is only the accounting on the other side:

- convoke, delve, improvise and waterbend settle **per symbol**, through
  `CostPayment.substitute`;
- crew settles against **one aggregate threshold**, total power N, and produces
  an ordinary tapping cost with no mana in it at all.

Two consumers, one eligibility model. Note that CR 702.51b, CR 702.66b and
CR 702.126b all say the same thing in as many words - the ability "isn't an
additional or alternative cost and applies only after the total cost ... is
determined" - which is why none of them touches `Casting.total_cost` and all of
them act on an already-open `CostPayment`.

Every CR number in this module was looked up with
`knowledge_search(type="rules")` in the session that wrote it.
"""

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ..models.card import Card, Color, Type
from ..models.card_state import CardState
from ..models.mana import PaymentOption
from ..models.zone import Zone
from ..serialization import SortedFrozenSet
from .abilities import keyword_abilities
from .cost import CostComponent, CostPayment, CostSubstitution, exile_cost, tap_cost


class ObjectAction(StrEnum):
    """What paying with an object does to it."""

    TAP = "tap"
    EXILE = "exile"


class ObjectOffer(BaseModel):
    """Which objects a keyword lets a player spend, and what it does to them.

    One of these per keyword instance. It answers `why_not` for a candidate and
    builds the `CostComponent` that spends it; the caller decides what the
    spending is worth (a symbol, or a share of a power threshold).
    """

    model_config = ConfigDict(frozen=True)

    keyword: str
    rule: str
    action: ObjectAction
    zone: Zone
    """Where an eligible object has to be. CR 702.51a's creatures are on the
    battlefield; CR 702.66a's cards are in a graveyard."""

    permitted_types: SortedFrozenSet[Type] = frozenset()
    """The card types an object has to have one of, or empty for "any object".

    Convoke and crew take "an untapped **creature**" (CR 702.51a, CR 702.122a),
    improvise takes "an untapped **artifact** you control" (CR 702.126a), and
    waterbend takes "an untapped **artifact or creature** you control"
    (CR 701.67a). One field, because those are the same question asked of
    different type lines - and the type line is read off the computed board
    (CR 613.5), so a crewed Vehicle improvises *and* convokes."""

    untapped_only: bool = False
    yours_only: bool = True
    """"creature**s you control**" (CR 702.51a, CR 702.122a) and "**your**
    graveyard" (CR 702.66a) - every offer in this module is restricted to the
    payer, but the flag is read rather than assumed."""

    excluding: UUID | None = None
    """Crew's "**other** untapped creatures" (CR 702.122a): the Vehicle itself
    never crews itself, even on the turn something else made it a creature."""

    pays_generic: bool = False
    """Whether an object may cover a generic symbol."""

    pays_own_colors: bool = False
    """Whether an object may cover a coloured symbol of one of *its own*
    colours - CR 702.51a's "an untapped creature of that color"."""

    def why_not(self, card: CardState, payer: str, game: Any = None) -> str | None:
        """Why `card` may not be spent on this offer, or None."""
        if card.zone is not self.zone:
            return (
                f"{card.name} is in {card.zone.value}, but {self.keyword} spends "
                f"objects in the {self.zone.value} ({self.rule})"
            )
        if self.yours_only and not _belongs_to(card, payer, game):
            return f"{payer} does not control {card.name}, so it cannot pay for {self.keyword}"
        if self.excluding is not None and card.id == self.excluding:
            return (
                f"{card.name} cannot crew itself: {self.rule} taps "
                f"*other* untapped creatures you control"
            )
        if self.permitted_types and not (self.permitted_types & _types_of(card, game)):
            return (
                f"{card.name} is not {self.noun}, so it cannot pay for {self.keyword} ({self.rule})"
            )
        if self.untapped_only and card.tapped:
            return (
                f"{card.name} is already tapped, and {self.rule} taps an "
                f"untapped {self.noun.removeprefix('a ').removeprefix('an ')}"
            )
        return None

    @property
    def noun(self) -> str:
        """What this offer calls an eligible object, for the refusal messages."""
        if not self.permitted_types:
            return "a permanent"
        printed = [kind.value.lower() for kind in sorted(self.permitted_types)]
        article = "an" if printed[0][0] in "aeiou" else "a"
        return f"{article} {' or '.join(printed)}"

    def component(self, card: CardState, payer: str) -> CostComponent:
        """The cost component that spends `card` (CR 601.2h)."""
        if self.action is ObjectAction.TAP:
            return tap_cost(card, payer=payer, description=f"Tap {card.name} ({self.keyword})")
        return exile_cost(
            card,
            payer=payer,
            zone=self.zone,
            required=1,
            description=f"Exile {card.name} from your graveyard ({self.keyword})",
        )

    def option_for(self, card: CardState, color: Color | None, game: Any = None) -> PaymentOption:
        """Which symbol `card` is being offered against (CR 702.51a).

        `color` names a coloured symbol; None asks for a generic one. Refusing
        here rather than at the arithmetic keeps delve's "for each **generic**
        mana" honest: a delved card offered against `{U}` is turned away
        because the rule never offered it, not because the cost happened to
        have no generic left.
        """
        if color is None:
            if not self.pays_generic:
                return _refuse(f"{self.keyword} does not pay generic mana ({self.rule})")
            return PaymentOption(generic=1)
        if not self.pays_own_colors:
            return _refuse(f"{self.keyword} does not pay coloured mana ({self.rule})")
        colors = _colors_of(card, game)
        if color not in colors:
            printed = "".join(f"{{{c.value}}}" for c in sorted(colors)) or "colourless"
            return _refuse(
                f"{card.name} is {printed}, so it cannot pay {{{color.value}}}: {self.rule} "
                f"taps an untapped creature *of that color*"
            )
        return PaymentOption(color=color)


def _refuse(message: str) -> PaymentOption:
    raise ValueError(message)


def _belongs_to(card: CardState, payer: str, game: Any = None) -> bool:
    """Whether `card` is the payer's for this offer's purposes.

    On the battlefield that is control (CR 702.51a, CR 702.122a's "creatures
    you control"); anywhere else it is ownership, since a graveyard is a
    per-player zone and CR 702.66a says "**your** graveyard".
    """
    if card.zone is Zone.BATTLEFIELD:
        if game is not None:
            try:
                return game.controller_of(card).username == payer
            except (KeyError, AttributeError):
                pass
        return card.controller in (None, payer)
    return card.owner in (None, payer)


def _types_of(card: CardState, game: Any = None) -> frozenset[Type]:
    """An object's card types off the computed board when there is one.

    CR 613.5 puts type-changing effects in layer 4, so a crewed Vehicle is a
    creature and can crew another Vehicle, a creature that lost the type in
    layer 4 cannot, and an animated artifact is still an artifact and still
    improvises (CR 702.126a). None of that is visible on the printed type line,
    which is why this asks the layer engine when it can.
    """
    if game is not None and card.zone is Zone.BATTLEFIELD:
        try:
            return frozenset(game.characteristics_of(card).types)
        except (KeyError, AttributeError):
            pass
    return frozenset(card.types)


def _colors_of(card: CardState, game: Any = None) -> frozenset[Color]:
    """A permanent's colours as they are now (CR 105.2, CR 613.1e's layer 5)."""
    if game is not None and card.zone is Zone.BATTLEFIELD:
        try:
            return frozenset(game.characteristics_of(card).colors)
        except (KeyError, AttributeError):
            pass
    return frozenset(card.colors)


def _subtypes_of(card: CardState, game: Any = None) -> frozenset[str]:
    """An object's subtypes off the computed board when there is one - the
    same shape `_types_of` and `_colors_of` use for their own characteristics
    (CR 613.1d puts subtype-changing effects in layer 4 alongside type)."""
    if game is not None and card.zone is Zone.BATTLEFIELD:
        try:
            return frozenset(game.characteristics_of(card).subtypes)
        except (KeyError, AttributeError):
            pass
    return frozenset(card.subtypes)


def power_of(card: CardState, game: Any = None) -> int:
    """One creature's power as the crew threshold counts it (CR 702.122a).

    Read off the computed board so a pump spell, an anthem, or a +1/+1 counter
    counts (CR 613.5); CR 208.5 fills in a missing value with 0.
    """
    if game is not None and card.zone is Zone.BATTLEFIELD:
        try:
            return game.characteristics_of(card).numeric_power
        except (KeyError, AttributeError):
            pass
    return card.power or 0


def total_power(cards: list[CardState], game: Any = None) -> int:
    """The "total power" CR 702.122a's crew cost is measured against."""
    return sum(power_of(card, game) for card in cards)


# --------------------------------------------------------------------------
# The offers
# --------------------------------------------------------------------------

CONVOKE_RULE = "CR 702.51a"
DELVE_RULE = "CR 702.66a"
CREW_RULE = "CR 702.122a"
IMPROVISE_RULE = "CR 702.126a"
WATERBEND_RULE = "CR 701.67a"


def convoke_offer() -> ObjectOffer:
    """CR 702.51a: tap an untapped creature you control for {1} or one mana of
    that creature's colour."""
    return ObjectOffer(
        keyword="convoke",
        rule=CONVOKE_RULE,
        action=ObjectAction.TAP,
        zone=Zone.BATTLEFIELD,
        permitted_types=frozenset({Type.CREATURE}),
        untapped_only=True,
        pays_generic=True,
        pays_own_colors=True,
    )


def delve_offer() -> ObjectOffer:
    """CR 702.66a: exile a card from your graveyard for one generic mana."""
    return ObjectOffer(
        keyword="delve",
        rule=DELVE_RULE,
        action=ObjectAction.EXILE,
        zone=Zone.GRAVEYARD,
        pays_generic=True,
    )


def improvise_offer() -> ObjectOffer:
    """CR 702.126a: tap an untapped artifact you control for one generic mana.

    No `pays_own_colors`: unlike convoke, improvise says "for each **generic**
    mana in this spell's total cost" and nothing else, so a blue artifact
    offered against Metallic Rebuke's `{U}` is refused by the rule rather than
    by the arithmetic. An artifact *creature* is an artifact and improvises;
    a creature that is not an artifact does not.
    """
    return ObjectOffer(
        keyword="improvise",
        rule=IMPROVISE_RULE,
        action=ObjectAction.TAP,
        zone=Zone.BATTLEFIELD,
        permitted_types=frozenset({Type.ARTIFACT}),
        untapped_only=True,
        pays_generic=True,
    )


def waterbend_offer() -> ObjectOffer:
    """CR 701.67a: tap an untapped artifact *or creature* you control for one
    generic mana of the cost the waterbend action word introduces."""
    return ObjectOffer(
        keyword="waterbend",
        rule=WATERBEND_RULE,
        action=ObjectAction.TAP,
        zone=Zone.BATTLEFIELD,
        permitted_types=frozenset({Type.ARTIFACT, Type.CREATURE}),
        untapped_only=True,
        pays_generic=True,
    )


def crew_offer(vehicle: CardState) -> ObjectOffer:
    """CR 702.122a: tap other untapped creatures you control, no mana involved."""
    return ObjectOffer(
        keyword="crew",
        rule=CREW_RULE,
        action=ObjectAction.TAP,
        zone=Zone.BATTLEFIELD,
        permitted_types=frozenset({Type.CREATURE}),
        untapped_only=True,
        excluding=vehicle.id,
    )


# --------------------------------------------------------------------------
# Reading the keywords off a card
# --------------------------------------------------------------------------


def has_convoke(card: Card) -> bool:
    """CR 702.51d: multiple instances are redundant, so this is a yes/no."""
    return _has(card, "convoke")


def has_delve(card: Card) -> bool:
    """CR 702.66c: multiple instances of delve are redundant."""
    return _has(card, "delve")


def has_improvise(card: Card) -> bool:
    """CR 702.126c: multiple instances of improvise are redundant."""
    return _has(card, "improvise")


def improvise_payment(card: Card) -> ObjectOffer | None:
    """The improvise offer `card` makes while it is on the stack, or None.

    CR 702.126a's ability is static and "functions while the spell with
    improvise is on the stack", so what a card *has* is an offer, not a
    payment already made: this answers "may artifacts pay part of this spell's
    cost, and which artifacts", and `improvise` spends one of them.
    """
    return improvise_offer() if has_improvise(card) else None


def crew_number(card: Card) -> int | None:
    """The N of `Crew N`, or None if the card has no crew ability (CR 702.122a)."""
    for ability in keyword_abilities(card):
        if ability.canonical.lower() != "crew":
            continue
        printed = (ability.cost or ability.parameter or "").strip()
        try:
            return int(printed)
        except ValueError:
            return None
    return None


def is_vehicle(card: Card) -> bool:
    """CR 301.7: "Some artifacts have the subtype 'Vehicle.'"

    Reads the printed type line only - use `is_vehicle_permanent` for a
    `CardState` already on the battlefield, which reads the computed board
    (CR 613.5) instead.
    """
    return Type.ARTIFACT in card.types and "Vehicle" in card.subtypes


def is_vehicle_permanent(permanent: CardState, game: Any = None) -> bool:
    """Whether this permanent is a Vehicle right now (CR 301.7), off the
    computed board (CR 613.5) through `_types_of`/`_subtypes_of` rather than
    off `is_vehicle`'s printed type line.

    CR 613.1d puts both type- and subtype-changing effects in layer 4, so an
    artifact that has been granted the Vehicle subtype by some effect this
    engine does not yet generate would be crewable the instant it is, and a
    permanent that has lost the subtype in the same layer would stop being
    one - neither of which the printed read could ever see. Latent rather
    than live today: nothing in the pool grants or removes "Vehicle" itself,
    so every Vehicle already in `tests/fixtures/cards/` computes the same
    answer either way.
    """
    return Type.ARTIFACT in _types_of(permanent, game) and "Vehicle" in _subtypes_of(
        permanent, game
    )


def _has(card: Card, keyword: str) -> bool:
    return any(ability.canonical.lower() == keyword for ability in keyword_abilities(card))


# --------------------------------------------------------------------------
# The per-symbol consumer: convoke and delve
# --------------------------------------------------------------------------


def convoke(
    payment: CostPayment,
    spell: CardState,
    creature: CardState,
    color: Color | None = None,
) -> CostSubstitution:
    """Tap `creature` to pay one symbol of `spell`'s already-determined cost.

    CR 702.51b: convoke "isn't an additional or alternative cost and applies
    only after the total cost of the spell with convoke is determined" - so
    this takes an open `CostPayment` rather than reshaping the announcement,
    and `payment.cost` still reads as the spell's real total cost afterwards.

    `color` picks the coloured symbol this creature covers; leaving it None
    offers it against a generic one. The creature is tapped when the payment is
    paid, not now, and untapped again if the payment is cancelled (CR 733.1).
    """
    if not has_convoke(spell.card):
        raise ValueError(f"{spell.name} does not have convoke ({CONVOKE_RULE})")
    return _substitute(payment, convoke_offer(), creature, color)


def delve(payment: CostPayment, spell: CardState, *cards: CardState) -> list[CostSubstitution]:
    """Exile `cards` from the payer's graveyard, one per generic symbol.

    CR 702.66a's "for each generic mana in this spell's total cost" is the
    whole bound: an empty graveyard delves for nothing, and offering more cards
    than the cost has generic mana is refused by `CostPayment.substitute`
    rather than quietly exiling a card for no benefit.
    """
    if not has_delve(spell.card):
        raise ValueError(f"{spell.name} does not have delve ({DELVE_RULE})")
    offer = delve_offer()
    return [_substitute(payment, offer, card, None) for card in cards]


def improvise(
    payment: CostPayment, spell: CardState, *artifacts: CardState
) -> list[CostSubstitution]:
    """Tap `artifacts` to pay one generic symbol each of `spell`'s total cost.

    CR 702.126a: "For each generic mana in this spell's total cost, you may tap
    an untapped artifact you control rather than pay that mana." CR 702.126b
    says improvise "isn't an additional or alternative cost and applies only
    after the total cost of the spell with improvise is determined", so - as
    with convoke and delve - this takes an already-open `CostPayment` and never
    reshapes the announcement: `payment.cost` still reads `{5}{U}` for a Kappa
    Cannoneer that four artifacts helped cast.

    Offering more artifacts than the cost has generic mana is refused by
    `CostPayment.substitute` rather than quietly tapping one for nothing, and
    the artifacts are tapped when the payment is paid, not now - so a cancelled
    payment leaves them untapped (CR 733.1).
    """
    if not has_improvise(spell.card):
        raise ValueError(f"{spell.name} does not have improvise ({IMPROVISE_RULE})")
    offer = improvise_offer()
    return [_substitute(payment, offer, artifact, None) for artifact in artifacts]


def waterbend(payment: CostPayment, *permanents: CardState) -> list[CostSubstitution]:
    """Tap `permanents` to pay one generic symbol each of a waterbend cost.

    CR 701.67a: "'Waterbend [cost]' means 'Pay [cost]. For each generic mana in
    that cost, you may tap an untapped artifact or creature you control rather
    than pay that mana.'" Waterbend is an action word on an *ability's* cost,
    not a static ability of a spell, so there is no keyword to check on a card
    on the stack the way `improvise` checks `spell` - the caller has already
    established that the cost being paid is the waterbend one, and what is left
    is the same per-symbol substitution the rest of the family does.
    """
    offer = waterbend_offer()
    return [_substitute(payment, offer, permanent, None) for permanent in permanents]


def _substitute(
    payment: CostPayment, offer: ObjectOffer, card: CardState, color: Color | None
) -> CostSubstitution:
    payer = payment.payer or ""
    refusal = offer.why_not(card, payer, payment.game)
    if refusal is not None:
        raise ValueError(refusal)
    if any(entry.card_id == card.id for entry in payment.substitutions):
        # One object, one symbol: CR 702.51a taps *an* untapped creature per
        # symbol, and a creature already promised to this payment is no longer
        # untapped by the time the next symbol would want it.
        raise ValueError(f"{card.name} is already paying for this spell ({offer.rule})")
    option = offer.option_for(card, color, payment.game)
    return payment.substitute(
        keyword=offer.keyword,
        rule=offer.rule,
        card=card,
        option=option,
        component=offer.component(card, payer),
    )
