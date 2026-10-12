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

import re
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import ConfigDict

from ..models.card import Card, Color, Supertype, Type
from ..models.card_state import CardState
from ..models.mana import PaymentOption
from ..models.zone import Zone
from ..serialization import SortedFrozenSet
from ..snapshot import EngineModel
from .abilities import keyword_abilities
from .cost import CostComponent, CostPayment, CostSubstitution, exile_cost, tap_cost


class ObjectAction(StrEnum):
    """What paying with an object does to it."""

    TAP = "tap"
    EXILE = "exile"


class ObjectOffer(EngineModel):
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
            return self._not_yours(card, payer, game)
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

    def _not_yours(self, card: CardState, payer: str, game: Any = None) -> str:
        """The refusal for another player's object, naming the rule that bars it.

        On the battlefield the keyword's own "you control" is the rule, unless
        the object's controller is deciding for `payer` right now: then it is
        CR 723.5a, "can use only that player's resources ... to pay costs for
        that player", that the seat is running into. Off the battlefield the
        question is whose zone the card is in ("**your** graveyard").
        """
        if card.zone is not Zone.BATTLEFIELD:
            return (
                f"{card.name} is in {card.owner}'s {card.zone.value}, not {payer}'s, "
                f"so it cannot pay for {self.keyword} ({self.rule})"
            )
        controller = card.controller
        if game is not None:
            try:
                controller = game.controller_of(card).username
                if game.is_controlling_player(controller, payer):
                    return (
                        f"{card.name} is {controller}'s, and {controller} is deciding "
                        f"for {payer}: the controller of another player can use only "
                        f"that player's resources to pay their costs, so it cannot pay "
                        f"for {self.keyword} (CR 723.5a)"
                    )
            except (KeyError, AttributeError, AssertionError):
                pass
        return (
            f"{payer} does not control {card.name}, so it cannot pay for "
            f"{self.keyword} ({self.rule})"
        )

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
STATION_RULE = "CR 702.184a"
IMPROVISE_RULE = "CR 702.126a"
WATERBEND_RULE = "CR 701.67a"
WATERBEND_RULE_B = "CR 701.67b"


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


#: Heart of Kiran: "You may remove a loyalty counter from a planeswalker you
#: control rather than pay Heart of Kiran's crew cost." (CR 118.9: another way
#: to pay the same cost; the printed name is normalised to "this Vehicle").
_CREW_LOYALTY_ALTERNATIVE_RE = re.compile(
    r"^you may remove a loyalty counter from a planeswalker you control rather than pay "
    r"(?:this \w+'s|its) crew cost\.?$",
    re.IGNORECASE,
)


def reads_crew_loyalty_alternative_line(name: str, text: str, *, legendary: bool = True) -> bool:
    """Whether one printed line is Heart of Kiran's crew alternative."""
    from .abilities import self_normalized_effect_text

    return bool(
        _CREW_LOYALTY_ALTERNATIVE_RE.match(
            self_normalized_effect_text(name, text.strip(), legendary=legendary)
        )
    )


def has_crew_loyalty_alternative(card: Card) -> bool:
    """Whether `card` prints Heart of Kiran's alternative way to pay its crew
    cost (a planeswalker's loyalty counter instead of tapped creatures)."""
    legendary = Supertype.LEGENDARY in card.supertypes
    return any(
        reads_crew_loyalty_alternative_line(card.name, line, legendary=legendary)
        for line in (card.oracle_text or "").splitlines()
    )


def station_offer(permanent: CardState) -> ObjectOffer:
    """CR 702.184a: "Tap another untapped creature you control" - one
    creature, its power the number of charge counters put on."""
    return ObjectOffer(
        keyword="station",
        rule=STATION_RULE,
        action=ObjectAction.TAP,
        zone=Zone.BATTLEFIELD,
        permitted_types=frozenset({Type.CREATURE}),
        untapped_only=True,
        excluding=permanent.id,
    )


def has_station(card: Card) -> bool:
    """CR 702.184b: a station card is one printed with a station ability."""
    return _has(card, "station")


# --------------------------------------------------------------------------
# Reading the keywords off a card
# --------------------------------------------------------------------------


def has_convoke(card: Card) -> bool:
    """CR 702.51d: multiple instances are redundant, so this is a yes/no."""
    return _has(card, "convoke")


#: "`<quality>` spells you cast have convoke." (Eirdu, Carrier of Dawn's own
#: "Creature spells you cast have convoke.") - `machines/spell_grants.py`'s
#: own `_SPELLS_YOU_CAST_HAVE_RE` shape, reused read-only rather than
#: duplicated: that module's own docstring says outright that convoke is
#: "not a grant it reads at all" (`SPELL_GRANT_KEYWORDS` only ever lists a
#: keyword some *other* machine already executes, and until now nothing
#: executed a granted convoke), so this is a new, narrow reader for the one
#: keyword that module deliberately excludes - kept in its own function here
#: rather than widening `SPELL_GRANT_KEYWORDS` itself.
def has_convoke_now(spell: CardState) -> bool:
    """CR 702.51a: whether `spell`, on the stack, has convoke - printed
    (`has_convoke`) or granted by a static ability of a permanent its
    controller controls right now (CR 611.3a: continuous, never locked in).

    `spell._board_source` is the bound `Game` (the same private back-
    reference `CardState.untap`/`tap` already read for their own game-facing
    notes), so this needs no new parameter threaded through `convoke`'s own
    signature - every existing caller of that function is unaffected.
    """
    if has_convoke(spell.card):
        return True
    return _has_granted_cost_keyword_now(spell, "convoke")


def offers_delve(card: CardState) -> bool:
    """Whether `card` - on the stack or still in hand, being offered its cost
    methods - has delve, printed or granted (`has_delve_now`)."""
    return has_delve(card.card) or _has_granted_cost_keyword_now(card, "delve", anywhere=True)


def has_delve_now(spell: CardState) -> bool:
    """CR 702.66a: whether `spell`, on the stack, has delve - printed or granted
    by a static ability of a permanent its controller controls (Teval, Arbiter
    of Virtue's "Spells you cast have delve."; CR 113.6, CR 611.3a)."""
    return has_delve(spell.card) or _has_granted_cost_keyword_now(spell, "delve")


def _has_granted_cost_keyword_now(spell: CardState, keyword: str, *, anywhere: bool = False) -> bool:
    """Whether a static \"`<quality>` spells you cast have `<keyword>`\" line of a
    permanent `spell`'s controller controls applies to `spell` right now."""
    if spell.zone is not Zone.STACK and not anywhere:
        return False
    game = getattr(spell, "_board_source", None)
    if game is None:
        return False
    controller = game.controller_of(spell).username
    from .spell_grants import (
        _SPELLS_YOU_CAST_HAVE_RE,
        _TRAILING_REMINDER_RE,
        _normalized_quality,
        _object_has_quality,
    )

    record = game.cast_record_of(spell)
    # CR 601.2a: before the cast is complete (CR 601.2i writes the record) the
    # announcement's own origin is the only answer.
    origin_zone = record.origin_zone if record is not None else spell._announced_from
    board = game.computed_board()
    for permanent in game.permanents_controlled_by(controller):
        for line in board.of(permanent).abilities:
            stripped = _TRAILING_REMINDER_RE.sub("", line.strip()).strip()
            match = _SPELLS_YOU_CAST_HAVE_RE.fullmatch(stripped)
            if match is None or match.group("keyword").strip().lower() != keyword:
                continue
            zone_word = match.groupdict().get("zone")
            if zone_word is not None and (
                origin_zone is None or _ZONE_WORDS_FOR_CONVOKE[zone_word.lower()] != origin_zone
            ):
                continue
            quality = _normalized_quality(match.group("what"))
            if _object_has_quality(spell, quality):
                return True
    return False


_ZONE_WORDS_FOR_CONVOKE = {"hand": Zone.HAND, "graveyard": Zone.GRAVEYARD, "exile": Zone.EXILE}


def granted_convoke_line_is_readable(text: str) -> bool:
    return granted_cost_keyword_line_is_readable(text, "convoke")


def granted_delve_line_is_readable(text: str) -> bool:
    """Whether `text` is a "`<quality>` spells you cast have delve." line
    `has_delve_now` reads at a real cast (Teval, Arbiter of Virtue)."""
    return granted_cost_keyword_line_is_readable(text, "delve")


def granted_cost_keyword_line_is_readable(text: str, keyword: str) -> bool:
    """Whether `text` is a "`<quality>` spells you cast[ from your hand/
    graveyard] have convoke." line `has_convoke_now` genuinely reads at a
    real cast (Eirdu, Carrier of Dawn's "Creature spells you cast have
    convoke.", Invasion of Segovia // Caetus, Sea Tyrant of Segovia's
    "Noncreature spells you cast have convoke.") - the audit-facing sibling
    of that function's own live board read, for a caller (`support.py`'s
    static-ability sweep) with no `CardState` on a stack to ask.

    `has_convoke_now` and this reader are kept in sync structurally rather
    than by construction - both match `_SPELLS_YOU_CAST_HAVE_RE`, both check
    `keyword == "convoke"` - because `machines/spell_grants.py`'s own
    `SPELL_GRANT_KEYWORDS` deliberately excludes convoke (see this module's
    own docstring above `has_convoke_now`), so nothing there can audit for
    it and this module is where the grant is actually read.
    """
    from .spell_grants import (
        _SPELLS_YOU_CAST_HAVE_RE,
        _TRAILING_REMINDER_RE,
        _normalized_quality,
        _quality_is_readable,
    )

    line = _TRAILING_REMINDER_RE.sub("", text.strip()).strip()
    match = _SPELLS_YOU_CAST_HAVE_RE.fullmatch(line)
    if match is None or match.group("keyword").strip().lower() != keyword:
        return False
    return _quality_is_readable(_normalized_quality(match.group("what")))


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
    numbers: list[int] = []
    for ability in keyword_abilities(card):
        if ability.canonical.lower() != "crew":
            continue
        printed = (ability.cost or ability.parameter or "").strip()
        try:
            numbers.append(int(printed))
        except ValueError:
            return None
    # CR 702.122a: a Vehicle with a granted second Crew N lets its controller
    # activate whichever it likes, so the smaller N is the one that matters.
    return min(numbers, default=None)


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
    if not has_convoke_now(spell):
        raise ValueError(f"{spell.name} does not have convoke ({CONVOKE_RULE})")
    return _substitute(payment, convoke_offer(), creature, color)


def delve(payment: CostPayment, spell: CardState, *cards: CardState) -> list[CostSubstitution]:
    """Exile `cards` from the payer's graveyard, one per generic symbol.

    CR 702.66a's "for each generic mana in this spell's total cost" is the
    whole bound: an empty graveyard delves for nothing, and offering more cards
    than the cost has generic mana is refused by `CostPayment.substitute`
    rather than quietly exiling a card for no benefit.

    CR 607.2q links every card this exiles to `spell` itself: "the permanent
    that spell becomes" is what a card like Murktide Regent's own "a +1/+1
    counter on it for each instant and sorcery card exiled with it" reads
    back, so each substitution's component carries `spell.id` in
    `link_to_permanent_id` regardless of whether this particular printing
    ever asks for it back - nothing reads an unclaimed link, the same way an
    unclaimed `ExileAnnotation.linked_permanent_id` already sits harmlessly
    on every other exiled card in this engine.
    """
    if not has_delve_now(spell):
        raise ValueError(f"{spell.name} does not have delve ({DELVE_RULE})")
    offer = delve_offer()
    substitutions = [_substitute(payment, offer, card, None) for card in cards]
    for substitution in substitutions:
        substitution.component.link_to_permanent_id = spell.id
    return substitutions


def improvise(
    payment: CostPayment, spell: CardState, *artifacts: CardState, granted: bool = False
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

    `granted=True` is CR 113.6's "an effect can grant a permanent an ability
    it doesn't have" (Ironheart, Clever Champion's own "Noncreature spells
    you cast have improvise.") - the spell then genuinely has the ability by
    the rules even though `spell.card`, the immutable printing, never carries
    it (`CLAUDE.md`: "do not add game state to `Card`"). The caller
    (`Game.has_granted_improvise`) is what actually reads that static grant;
    this function only trusts the flag it is handed, the same division
    `_offer_free_casts_from_among` already keeps between "is this legal" and
    "do it".
    """
    if not granted and not has_improvise(spell.card):
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

    CR 701.67b: "If a waterbend cost is part of the total cost to cast a
    spell or activate an ability ..., the alternate method to pay for mana
    described in rule 701.67a may be used only to pay for the amount of
    generic mana in the waterbend cost, even if the total cost ... includes
    other generic mana components." Unlike convoke/delve/improvise, which
    CR 702.51b/702.66b/702.126b all bind to the *whole* spell's total cost,
    waterbend's own rule narrows the bound to `payment.waterbend_generic`
    when that is set - `_substitute`'s ordinary `payment.mana_owed` check
    still applies underneath it and is what bounds every other case (nothing
    printed yet narrows the two), but this is the check that would catch a
    cost like "Waterbend {3}, {1}" tapping past the {3}.
    """
    offer = waterbend_offer()
    results = []
    for permanent in permanents:
        if payment.waterbend_generic is not None:
            already = sum(
                entry.option.generic
                for entry in payment.substitutions
                if entry.keyword == "waterbend"
            )
            if already + 1 > payment.waterbend_generic:
                raise ValueError(
                    f"{permanent.name} cannot pay for the waterbend cost: only "
                    f"{payment.waterbend_generic} generic mana is in the waterbend "
                    f"cost itself, and the alternate tap method reaches no further "
                    f"even though the total cost has other generic mana in it "
                    f"({WATERBEND_RULE_B})"
                )
        results.append(_substitute(payment, offer, permanent, None))
    return results


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
