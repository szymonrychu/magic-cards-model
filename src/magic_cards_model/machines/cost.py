"""Paying a cost, as a state machine.

Follows the shape of CR 601.2f-h: work out the total cost, activate mana
abilities to fill the pool, then pay. Tapping a permanent for mana is both the
cost of the mana ability and the thing that fills the pool, so it lives here.

    PENDING -> TAPPING -> POOLED -> PAID
                 \\_______________/
       (mana already floating skips the tapping)

A cost is not only mana. CR 601.2f calls the whole thing the *total cost*, and
it is a composite: a mana part plus any number of non-mana components -
sacrificing a permanent, discarding a card, paying life, exiling a card,
tapping a permanent. `TotalCost` is that composite and `CostComponent` is one
non-mana piece of it.

The payment's mana pool opens as a copy of the payer's floating mana: CR 202.1a
has the cost spent "from their mana pool", and CR 106.4 lets mana already
floating there pay "immediately", so it is usable without activating anything.
The mana abilities the payment activates along the way (CR 601.2g) add into
that copy. When the payment succeeds, whatever it did not spend is written back
into the player's pool (CR 106.4a); when it is cancelled, the copy is thrown
away, so the player's pre-existing floating mana is untouched while the payment's
own activations die with the copy and their sources are untapped.

Any state before PAID can be cancelled, which untaps everything tapped for
mana, discards the mana the payment's own activations produced, and undoes
every component already paid. That is CR 733.1: an action that cannot be
completed legally is reversed in full and any payments already made are
cancelled.
"""

import re
from collections.abc import Iterable, Sequence
from enum import StrEnum
from itertools import combinations, product
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from ..models.card import Card, Color, Supertype, Type
from ..models.card_state import CardState, Counter
from ..models.mana import ManaCost, ManaPayment, ManaPool
from ..models.zone import Zone
from .abilities import (
    ActivatedAbility,
    CostKind,
    ManaAbility,
    TriggerEvent,
    intrinsic_land_ability,
    parse_abilities,
)
from .combat import Keyword, has_keyword
from .triggers import GameEvent, tapped_for_mana_event


def can_tap_for_mana(source: CardState, game: Any = None) -> bool:
    """Whether this permanent's `{T}` ability may be activated (CR 302.6, 602.5a).

    Only creatures are held back, and haste turns the restriction off
    (CR 702.10c). `Game.can_activate_tap_ability` is the authority when there
    is a game; without one the same question is answered off the permanent
    itself, since summoning sickness is a flag on `CardState` and haste is
    printed on the card.
    """
    if game is not None:
        return bool(game.can_activate_tap_ability(source))
    if not source.is_creature:
        return True
    return not source.summoning_sick or has_keyword(source, Keyword.HASTE)


def is_snow_source(source: CardState) -> bool:
    """Whether mana from this permanent is snow mana (CR 106.3, 205.4g).

    Read off the printed type line, since nothing in this engine grants or
    removes a supertype yet.
    """
    return Supertype.SNOW in source.card.supertypes


# --------------------------------------------------------------------------
# Auto-tapping: solving *which* sources to tap and *which* colour a choice
# source makes, so a player is not forced to hand-pick every dual and
# shockland on every cast (CR 601.2g, CR 118.3c).
# --------------------------------------------------------------------------


def _restricted_effect(effect: str) -> bool:
    """True if a mana ability's own effect text restricts how the mana is
    spent (CR 106.6: Eldrazi Temple, Cavern of Souls).

    This engine does not model spend restrictions at all - `models/mana.py`'s
    pool carries no restriction tag once mana is in it (see
    `docs/engine-coverage.md`) - so there is no way to *check* the restriction
    was honoured later. The only safe move for an automatic assignment is to
    never produce mana this way in the first place; `free_tap_mana_ability`
    is where that exclusion happens.
    """
    return "spend this mana only" in effect.lower()


def free_tap_mana_ability(card: Card) -> ManaAbility | None:
    """The one mana ability this card may be tapped for **on the player's
    behalf**, or None if it has none safe to choose for it.

    Only an ability whose entire activation cost is a bare `{T}` qualifies.
    CR 601.2g lets a player activate mana abilities before paying a cost, and
    CR 118.3c makes doing so optional, but nothing there lets an *engine*
    spend a cost the player never agreed to - so a mana ability with anything
    else in its cost is skipped here even though `parse_mana_abilities` still
    reports it:

    - an additional cost (Sunbaked Canyon's 1 life, Tinder Farm's sacrifice,
      Arena of Glory's `{R}` and exert) is a real cost only the player may
      choose to pay;
    - an ability whose effect text carries a CR 106.6 spend restriction
      (Eldrazi Temple's `{C}{C}`, Cavern of Souls's any-colour ability) is
      skipped by `_restricted_effect`, because this engine cannot verify the
      restriction is honoured once the mana is in the pool.

    A card with more than one qualifying ability (none in this pool) uses the
    first printed, same as `parse_mana_abilities`. A card whose only tap
    ability is restricted or carries an extra cost (Eldrazi Temple's own
    `{T}: Add {C}.` is the fallback that keeps it usable at all) returns
    whichever earlier ability in printed order is both `{T}`-only and
    unrestricted; if none is, this returns None and the source is left alone.
    """
    for ability in parse_abilities(card):
        if not isinstance(ability, ActivatedAbility) or ability.mana is None:
            continue
        if [piece.kind for piece in ability.costs] != [CostKind.TAP]:
            continue
        if _restricted_effect(ability.effect):
            continue
        return ability.mana
    intrinsic = intrinsic_land_ability(card)
    return intrinsic.mana if intrinsic is not None and intrinsic.mana is not None else None


def _flexibility(options: list[list[Color]], any_color: bool) -> int:
    """How much of a real choice this ability is, least flexible first.

    Used only to order which sources an equally-small automatic assignment
    prefers to spend: a fixed source (a basic, a colourless rock) before a
    dual or shockland, and a dual before an any-colour source - so a flexible
    source is the one left untapped for whatever the player does next.

    Takes `options`/`any_color` already resolved against the board
    (`ManaAbility.effective`), not the ability's own unconditional shape, so a
    Tron piece is ranked on what it can actually make right now rather than
    its printed-alone `{T}: Add {C}.` line.
    """
    if any_color:
        return 2
    if len(options) > 1:
        return 1
    return 0


def _mana_context(
    payment: "CostPayment", source: CardState
) -> tuple[frozenset[str], frozenset[str], bool]:
    """The board state `source`'s mana ability needs to resolve a CR 605.1a
    conditional "add X instead" clause right now: the land types its
    controller controls (Urza's Tower), the counters on `source` itself
    (Gemstone Caverns), and whether a card is exiled with it (Ugin's
    Labyrinth).

    Tapping a source changes nothing about who controls what, what counters
    are on a permanent, or what is exiled with it, so this is safe to compute
    once per candidate before any combination of sources is tried, rather than
    recomputed per combination - `Game._controlled_land_types` only reads
    control, not tapped status, and neither `source.counters` nor the exile
    zone is affected by tapping anything.
    """
    own_counters = frozenset(source.counters.counts)
    if payment.game is None:
        return frozenset(), own_counters, False
    has_imprinted_card = payment.game.card_imprinted_on(source.id) is not None
    controller = source.controller or payment.payer
    if controller is None:
        return frozenset(), own_counters, has_imprinted_card
    return payment.game._controlled_land_types(controller), own_counters, has_imprinted_card


def _auto_tap_candidates(
    payment: "CostPayment", sources: Iterable[CardState]
) -> list[tuple[CardState, list[list[Color]]]]:
    """Every source `auto_tap` may consider, paired with what it would
    actually add right now (conditional clauses resolved against the board -
    see `_mana_context`), least flexible first."""
    candidates: list[tuple[CardState, list[list[Color]], bool]] = []
    for source in sources:
        if source.zone is not Zone.BATTLEFIELD or source.tapped:
            continue
        if payment.payer is not None and source.controller not in (None, payment.payer):
            continue
        if not can_tap_for_mana(source, payment.game):
            continue
        ability = free_tap_mana_ability(source.card)
        if ability is None:
            continue
        land_types, own_counters, has_imprinted_card = _mana_context(payment, source)
        options, any_color = ability.effective(land_types, own_counters, has_imprinted_card)
        candidates.append((source, options, any_color))
    candidates.sort(key=lambda item: _flexibility(item[1], item[2]))
    return [(source, options) for source, options, _any_color in candidates]


def _solve_colours(
    combo: Sequence[tuple[CardState, list[list[Color]]]],
    base_floating: dict[Color, int],
    base_snow: dict[Color, int],
    cost: ManaCost,
    life_available: int,
) -> list[tuple[CardState, list[Color]]] | None:
    """The first colour assignment for this exact set of sources that pays
    `cost`, or None if none of them do.

    Only the *set* of sources is fixed by the caller; this tries every colour
    a choice source in it could make - `combo`'s options are already resolved
    against the board by `_auto_tap_candidates` (`ManaAbility.effective`), so
    a Tron piece here is tried at what it actually produces right now, not
    its unconditional `{T}: Add {C}.` alone - until the resulting pool can
    pay the cost (`ManaPool.can_pay`, which already knows generic, hybrid,
    Phyrexian, and snow symbols), or exhausts them.
    """
    option_lists = [options for _source, options in combo]
    for chosen in product(*option_lists):
        trial = ManaPool(floating=dict(base_floating), snow=dict(base_snow))
        for (source, _options), colors in zip(combo, chosen, strict=True):
            trial.add_all(colors, snow=is_snow_source(source))
        if trial.can_pay(cost, life_available=life_available):
            return [
                (source, list(colors))
                for (source, _options), colors in zip(combo, chosen, strict=True)
            ]
    return None


class CostStep(StrEnum):
    PENDING = "pending"
    TAPPING = "tapping"
    POOLED = "pooled"
    PAID = "paid"
    CANCELLED = "cancelled"


_ALLOWED: dict[CostStep, frozenset[CostStep]] = {
    CostStep.PENDING: frozenset({CostStep.TAPPING, CostStep.POOLED, CostStep.CANCELLED}),
    CostStep.TAPPING: frozenset({CostStep.TAPPING, CostStep.POOLED, CostStep.CANCELLED}),
    CostStep.POOLED: frozenset({CostStep.TAPPING, CostStep.PAID, CostStep.CANCELLED}),
    CostStep.PAID: frozenset(),
    CostStep.CANCELLED: frozenset(),
}


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


_OBJECT_KINDS = frozenset(
    {
        ComponentKind.TAP,
        ComponentKind.SACRIFICE,
        ComponentKind.DISCARD,
        ComponentKind.EXILE,
        ComponentKind.REMOVE_COUNTERS,
        ComponentKind.EXERT,
    }
)


class CardRequirement(BaseModel):
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
    subtypes: list[str] = Field(default_factory=list)
    """The card must have at least one of these subtypes, as printed."""
    description: str = ""
    """The phrase this was read from, for the message when it is not met."""

    @property
    def is_empty(self) -> bool:
        return not (self.colors or self.types or self.subtypes)

    def why_not(self, card: CardState) -> str | None:
        """Why this card cannot pay, or None if it can."""
        printed = card.card
        if self.colors and not set(printed.colors or []) & set(self.colors):
            wanted = "/".join(color.value for color in self.colors)
            return f"{card.name} is not {wanted}"
        if self.types and not set(printed.types) & set(self.types):
            wanted = "/".join(type_.value for type_ in self.types)
            return f"{card.name} is not a {wanted}"
        if self.subtypes:
            printed_subtypes = {subtype.lower() for subtype in printed.subtypes}
            if not printed_subtypes & {subtype.lower() for subtype in self.subtypes}:
                return f"{card.name} is not a {'/'.join(self.subtypes)}"
        return None


class CostComponent(BaseModel):
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
    """Life to pay, or counters to remove."""

    required: int = 0
    """How many objects this component needs chosen. Zero for paying life."""

    cards: list[CardState] = Field(default_factory=list)
    description: str = ""
    paid: bool = False

    requirement: CardRequirement | None = None
    """What the chosen cards have to be, when the cost says (CR 118.3)."""

    zone: Zone = Zone.HAND
    """Where an `ComponentKind.EXILE` card must presently be (CR 406.2).

    Nothing in CR 406 ties exiling to the hand - a card can be exiled "from
    your graveyard" (Seasoned Pyromancer), "from your hand" (Force of Will), or
    from wherever it already is (a self-referential "Exile this card"). Only
    `EXILE` reads this; `DISCARD` is hand-only by definition (CR 701.9a: "To
    discard a card, move it from its owner's hand to that player's graveyard")
    and stays hardcoded.
    """

    _undo: list[tuple[CardState, dict[str, Any]]] = PrivateAttr(default_factory=list)

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
                mismatch = self.requirement.why_not(card)
                if mismatch is not None:
                    return mismatch

        checks = {
            ComponentKind.TAP: self._why_not_tap,
            ComponentKind.SACRIFICE: self._why_not_sacrifice,
            ComponentKind.DISCARD: lambda _: self._why_not_in_zone(Zone.HAND),
            ComponentKind.EXILE: lambda _: self._why_not_in_zone(self.zone),
            ComponentKind.PAY_LIFE: self._why_not_life,
            ComponentKind.REMOVE_COUNTERS: lambda _: (
                "counters are not modelled, so a cost that removes them cannot be paid"
            ),
            ComponentKind.LOYALTY: self._why_not_loyalty,
            ComponentKind.EXERT: self._why_not_exert,
        }
        return checks[self.kind](game)

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

    def _why_not_tap(self, _game: Any) -> str | None:
        for card in self.cards:
            if card.zone is not Zone.BATTLEFIELD:
                return f"{card.name} is not on the battlefield, so it cannot be tapped"
            if card.tapped:
                return f"{card.name} is already tapped, so it cannot be tapped to pay a cost"
        return self._why_not_controlled()

    def _why_not_sacrifice(self, _game: Any) -> str | None:
        for card in self.cards:
            if card.zone is not Zone.BATTLEFIELD:
                return f"{card.name} is not a permanent, so it cannot be sacrificed"
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
                    game.emit(
                        GameEvent(
                            event=TriggerEvent.BECOMES_TAPPED,
                            subject_id=card.id,
                            subject_name=card.name,
                            subject_controller=card.controller,
                            subject_card=card.card,
                            player=card.controller,
                        )
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
            # CR 701.9a's discard, through the keyword machinery rather than
            # straight to the graveyard: madness (CR 702.35a) replaces where a
            # discarded card lands, and a cost is one of the ways a card gets
            # discarded. Imported here because `machines/keywords.py` builds its
            # costs out of this module.
            from .keywords import discard as discard_one

            for card in self.cards:
                self._remember(card)
                discard_one(game, card, self.payer)
        elif self.kind is ComponentKind.EXILE:
            for card in self.cards:
                self._remember(card)
                game.player(self.payer).cards_in(card.zone).remove(card)
                card.move_to(Zone.EXILE)
                game.exile.append(card)
        elif self.kind is ComponentKind.PAY_LIFE and self.amount:
            game.player(self.payer).lose_life(self.amount)
        elif self.kind is ComponentKind.LOYALTY:
            # CR 606.4: the counter change *is* the cost, so it happens at
            # payment time - on activation, before the ability is on the stack
            # doing anything (CR 602.2). CR 107.7: `[+N]` puts N loyalty
            # counters on, `[−N]` removes N, and `[0]` puts zero, which is a
            # payment with no event at all.
            for card in self.cards:
                self._remember_counters(card)
                if self.amount > 0:
                    card.counters.add(Counter.LOYALTY, self.amount)
                elif self.amount < 0:
                    card.counters.remove(Counter.LOYALTY, -self.amount)

        self.paid = True

    def unpay(self, game: Any) -> None:
        """Put back exactly what paying took, in reverse order (CR 733.1)."""
        if not self.paid:
            return

        if self.kind is ComponentKind.PAY_LIFE:
            if self.amount:
                game.player(self.payer).gain_life(self.amount)
        elif self.kind is ComponentKind.EXERT:
            # Exerting moves nothing either, and CR 701.43b lets it be exerted
            # more than once, so the rewind is simply putting the flag back.
            for card, _ in reversed(self._undo):
                card.exerted = False
        elif self.kind is ComponentKind.TAP:
            # Tapping moves nothing, so untapping is the whole rewind.
            for card, _ in reversed(self._undo):
                card.untap(exert_applies=False)
        elif self.kind is ComponentKind.LOYALTY:
            # The counters were mutated in place, and the permanent never left
            # the battlefield, so the rewind puts the snapshotted `Counters`
            # model back wholesale. Not `_return`, which removes the card from
            # its zone list and re-appends it - reordering the battlefield for
            # a payment that moved nothing.
            for card, snapshot in reversed(self._undo):
                card.counters = snapshot["counters"]
        else:
            for card, snapshot in reversed(self._undo):
                self._return(game, card, snapshot)

        self._undo = []
        self.paid = False

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
        """Snapshot a card's counters for the rewind of a loyalty cost.

        Not `_remember`: that snapshots every field *by reference*, and paying
        a loyalty cost mutates `counters` in place (CR 122.1e - the counters
        are the planeswalker's loyalty), so a by-reference snapshot would
        record the payment as if it had already happened and the rewind would
        rewind nothing. A deep copy of the `Counters` model is what unpay
        restores.
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


def tap_cost(*cards: CardState, payer: str | None = None, description: str = "") -> CostComponent:
    """Tap permanents as a cost. Already-tapped permanents cannot pay (CR 118.3)."""
    return CostComponent(
        kind=ComponentKind.TAP,
        cards=list(cards),
        required=len(cards),
        payer=payer,
        description=description,
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


def remove_counters_cost(
    card: CardState, amount: int, payer: str | None = None, description: str = ""
) -> CostComponent:
    """Remove counters from a permanent as a cost.

    Counter kinds other than loyalty are not modelled in this engine, so this
    component exists to be refused rather than paid. Loyalty counters have
    their own component: `loyalty_cost`, where the counter change is the whole
    cost of a loyalty ability (CR 606.4).
    """
    return CostComponent(
        kind=ComponentKind.REMOVE_COUNTERS,
        cards=[card],
        required=1,
        amount=amount,
        payer=payer,
        description=description,
    )


# --------------------------------------------------------------------------
# The composite: mana plus components
# --------------------------------------------------------------------------


class TotalCost(BaseModel):
    """What casting a spell actually costs: a mana part and everything else.

    CR 601.2f calls this the total cost. It is what an alternative cost
    replaces and what an additional cost is added to.
    """

    mana: ManaCost = Field(default_factory=ManaCost)
    components: list[CostComponent] = Field(default_factory=list)

    @classmethod
    def of(cls, mana: "ManaCost | str | None" = None, *components: CostComponent) -> "TotalCost":
        parsed = ManaCost.parse(mana) if isinstance(mana, str) else (mana or ManaCost())
        return cls(mana=parsed, components=list(components))

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

    FLOOR = "floor"
    """"Each spell that would cost less than [N] mana to cast costs [N] mana
    to cast." - Trinisphere."""


class CostModifierEffect(BaseModel):
    """One static cost-modifying ability, read off a permanent's oracle text."""

    model_config = ConfigDict(frozen=True)

    kind: CostModifierKind
    amount: int
    """The flat/per-spell surcharge, or the floor's minimum mana value."""

    excludes_type: Type | None = None
    """`FLAT_INCREASE` only: the printed type the qualifier excludes -
    `Type.CREATURE` for "Noncreature spells", `Type.ARTIFACT` for "Nonartifact
    spells". `None` means the increase is unconditional, like Sphere of
    Resistance's own "Spells cost {1} more to cast."."""

    requires_untapped: bool = False
    """`FLOOR` only: Trinisphere's "As long as this artifact is untapped,"
    condition (CR 611.3b keeps a static ability live only while its source
    carries it, and being tapped turns this one off)."""


_QUALIFIER_EXCLUDES: dict[str, Type] = {
    "Noncreature": Type.CREATURE,
    "Nonartifact": Type.ARTIFACT,
    "Nonland": Type.LAND,
    "Noninstant": Type.INSTANT,
    "Nonsorcery": Type.SORCERY,
    "Nonenchantment": Type.ENCHANTMENT,
    "Nonplaneswalker": Type.PLANESWALKER,
}

_FLAT_COST_INCREASE = re.compile(
    r"(?:(?P<qualifier>Noncreature|Nonartifact|Nonland|Noninstant|Nonsorcery|"
    r"Nonenchantment|Nonplaneswalker) )?[Ss]pells? cost \{(?P<amount>\d+)\} more to cast\."
)
_PER_SPELL_COST_INCREASE = re.compile(
    r"Each spell a player casts costs \{(?P<amount>\d+)\} more to cast for each "
    r"other spell that player has cast this turn\."
)
_SPELL_COST_FLOOR = re.compile(
    r"(?P<condition>As long as this \w+ is untapped, )?"
    r"[Ee]ach spell that would cost less than (?P<threshold>\w+) mana to cast "
    r"costs (?P<total>\w+) mana to cast\."
)
#: Anything that talks about a spell costing more, or a floor on what a spell
#: would cost, whether or not the shapes above could read it - Grand Arbiter
#: Augustin IV's "Spells your opponents cast cost {1} more to cast" mentions
#: an increase but is controller-relative, a shape none of the above parse.
_COST_MODIFIER_SIGNAL = re.compile(r"more to cast|would cost .* mana to cast")


def cost_modifier_effect(text: str) -> CostModifierEffect | None:
    """Read one static cost-modifying sentence off a permanent's oracle text.

    Returns `None` if nothing here matches a recognised shape - which is not
    the same as "this text has nothing to say about costs"; that distinction
    is `looks_like_unparsed_cost_modifier`'s job, kept separate so a numeral
    this engine cannot read (an out-of-range word, say) is reported rather
    than silently treated as "no effect here".
    """
    match = _FLAT_COST_INCREASE.search(text)
    if match is not None:
        qualifier = match.group("qualifier")
        return CostModifierEffect(
            kind=CostModifierKind.FLAT_INCREASE,
            amount=int(match.group("amount")),
            excludes_type=_QUALIFIER_EXCLUDES.get(qualifier) if qualifier else None,
        )
    match = _PER_SPELL_COST_INCREASE.search(text)
    if match is not None:
        return CostModifierEffect(
            kind=CostModifierKind.PER_SPELL_INCREASE, amount=int(match.group("amount"))
        )
    match = _SPELL_COST_FLOOR.search(text)
    if match is not None:
        threshold = _count(match.group("threshold"))
        total = _count(match.group("total"))
        if threshold is None or total is None:
            return None
        return CostModifierEffect(
            kind=CostModifierKind.FLOOR,
            amount=total,
            requires_untapped=match.group("condition") is not None,
        )
    return None


class CostModifierNotice(BaseModel):
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


def looks_like_unparsed_cost_modifier(text: str) -> bool:
    """True if `text` reads like a cost-increase/floor effect this cannot
    turn into a `CostModifierEffect` - the fail-closed signal a caller records
    as a notice rather than silently skipping (the exact shape of DDR#978:
    a cost increase that fails to apply looks identical to ordinary play)."""
    if cost_modifier_effect(text) is not None:
        return False
    return bool(_COST_MODIFIER_SIGNAL.search(text))


# --------------------------------------------------------------------------
# Reading a card's own additional and alternative costs
# --------------------------------------------------------------------------

_ADDITIONAL = re.compile(
    r"^As an additional cost to cast this spell, (?P<what>[^.]+)\.", re.MULTILINE
)
_ALTERNATIVE = re.compile(
    r"^You may (?P<what>[^.]+?) rather than pay this spell's mana cost\.", re.MULTILINE
)


def additional_cost_phrases(card: Card) -> list[str]:
    """The "as an additional cost" sentences printed on the card (CR 118.8a)."""
    return [match.group("what") for match in _ADDITIONAL.finditer(card.oracle_text or "")]


def alternative_cost_phrases(card: Card) -> list[str]:
    """The "rather than pay this spell's mana cost" offers on the card (CR 118.9)."""
    return [match.group("what") for match in _ALTERNATIVE.finditer(card.oracle_text or "")]


# --------------------------------------------------------------------------
# Reading a printed cost phrase into something payable
# --------------------------------------------------------------------------

_COUNT_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}

_COLOR_WORDS = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
    "colorless": Color.COLORLESS,
}

_PHRASE_PAY_LIFE = re.compile(r"^pay (?P<amount>\d+) life$", re.IGNORECASE)
#: `Exile a black card from your hand` (Force of Will) and the self-referential
#: `Exile this card from your graveyard` (Seasoned Pyromancer). CR 406.2 never
#: restricts exiling to the hand, so the zone is read off the sentence rather
#: than assumed - `exile_cost`'s default is only ever a fallback for a
#: sentence that names none.
_PHRASE_EXILE = re.compile(
    r"^exile (?:this card|(?P<count>\w+) (?P<quality>[\w ]*?)cards?)"
    r"(?: from (?:your|their) (?P<zone>hand|graveyard|library|battlefield))?$",
    re.IGNORECASE,
)
_ZONE_WORDS: dict[str, Zone] = {
    "hand": Zone.HAND,
    "graveyard": Zone.GRAVEYARD,
    "library": Zone.LIBRARY,
    "battlefield": Zone.BATTLEFIELD,
}
_PHRASE_SACRIFICE = re.compile(r"^sacrifice (?P<count>\w+) (?P<quality>[\w ]+)$", re.IGNORECASE)
_PHRASE_DISCARD = re.compile(r"^discard (?P<count>\w+) (?P<quality>[\w ]*?)cards?$", re.IGNORECASE)
#: `Exert this land`, `Exert this creature` (CR 701.43a). Only the self-
#: referential form, which is the only one printed inside a cost.
_PHRASE_EXERT_SELF = re.compile(
    r"^exert this (?:land|creature|permanent|artifact|enchantment)$", re.IGNORECASE
)


def _count(word: str) -> int | None:
    if word.isdigit():
        return int(word)
    return _COUNT_WORDS.get(word.lower())


def _requirement(quality: str) -> CardRequirement | None:
    """Turn `black`, `creature`, or `Mountain` into what the cards must be.

    Unrecognised wording returns None, which the caller reads as "this phrase
    was not understood" rather than as "anything will do" - a cost that silently
    accepts the wrong card is worse than one that refuses to be built.
    """
    words = [word for word in quality.strip().split() if word]
    if not words:
        return CardRequirement(description=quality.strip())

    colors: list[Color] = []
    types: list[Type] = []
    subtypes: list[str] = []
    for word in words:
        lowered = word.lower().rstrip("s")
        if lowered in _COLOR_WORDS:
            colors.append(_COLOR_WORDS[lowered])
        elif lowered in {type_.value for type_ in Type}:
            types.append(Type(lowered))
        elif word[:1].isupper():
            # A capitalised noun in a cost phrase is a subtype: `Sacrifice a
            # Mountain`, `Sacrifice a Goblin`.
            subtypes.append(word)
        else:
            return None
    return CardRequirement(
        colors=colors, types=types, subtypes=subtypes, description=quality.strip()
    )


def cost_component_for_phrase(phrase: str, payer: str | None = None) -> CostComponent | None:
    """Read one printed cost sentence into a payable `CostComponent`.

    This is what makes `Evoke—Exile a black card from your hand.` more than a
    string: CR 118.9 calls it an alternative cost, and an alternative cost has
    to be *paid*, which means knowing that it exiles one black card out of the
    caster's hand.

    Returns None for a phrase it cannot read, so the caller can leave the
    keyword unexecuted rather than charge the wrong thing.
    """
    text = phrase.strip().rstrip(".")

    life = _PHRASE_PAY_LIFE.match(text)
    if life is not None:
        return pay_life_cost(int(life.group("amount")), payer, description=text)

    if _PHRASE_EXERT_SELF.match(text):
        # The permanent exerted is the one whose ability this is, and only the
        # caller knows which that is, so the component is built empty and
        # correctly refuses to be paid until the card is filled in (CR 118.3).
        return exert_cost(payer=payer, required=1, description=text)

    exile = _PHRASE_EXILE.match(text)
    if exile is not None:
        zone = _ZONE_WORDS.get((exile.group("zone") or "hand").lower(), Zone.HAND)
        if exile.group("count") is None:
            # "Exile this card [from your graveyard]": CR 700.7's self-
            # reference, so there is nothing to choose - only the caller
            # knows which permanent this is, same as `_PHRASE_EXERT_SELF`.
            return exile_cost(payer=payer, required=1, description=text, zone=zone)
        count = _count(exile.group("count"))
        requirement = _requirement(exile.group("quality"))
        if count is None or requirement is None:
            return None
        component = exile_cost(payer=payer, required=count, description=text, zone=zone)
        component.requirement = requirement
        return component

    discard = _PHRASE_DISCARD.match(text)
    if discard is not None:
        count = _count(discard.group("count"))
        requirement = _requirement(discard.group("quality"))
        if count is None or requirement is None:
            return None
        component = discard_cost(payer=payer, required=count, description=text)
        component.requirement = requirement
        return component

    sacrifice = _PHRASE_SACRIFICE.match(text)
    if sacrifice is not None:
        count = _count(sacrifice.group("count"))
        requirement = _requirement(sacrifice.group("quality"))
        if count is None or requirement is None:
            return None
        component = sacrifice_cost(payer=payer, required=count, description=text)
        component.requirement = requirement
        return component

    return None


def total_cost_for_phrase(phrase: str, payer: str | None = None) -> TotalCost | None:
    """A whole printed cost, mana or otherwise, as a `TotalCost`.

    `Flashback {2}{R}` is mana; `Evoke—Exile a black card from your hand.` is a
    component; a comma-separated phrase can be both.
    """
    mana = ManaCost()
    components: list[CostComponent] = []
    for part in _split_cost_phrase(phrase):
        if _ONLY_MANA.match(part):
            mana = mana.plus(ManaCost.parse(part))
            continue
        component = cost_component_for_phrase(part, payer)
        if component is None:
            return None
        components.append(component)
    return TotalCost(mana=mana, components=components)


_ONLY_MANA = re.compile(r"^(?:\{[^{}]+\}|\s)+$")


def _split_cost_phrase(phrase: str) -> list[str]:
    """Split a printed cost on its commas, keeping a run of mana symbols whole."""
    return [part.strip() for part in phrase.strip().rstrip(".").split(",") if part.strip()]


# --------------------------------------------------------------------------
# The payment machine
# --------------------------------------------------------------------------


class CostPayment(BaseModel):
    """Paying one total cost, from tapping sources through to the leftover mana."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    cost: ManaCost
    components: list[CostComponent] = Field(default_factory=list)
    game: Any = Field(default=None, exclude=True, repr=False)
    payer: str | None = None
    pool: ManaPool = Field(default_factory=ManaPool)
    step: CostStep = CostStep.PENDING
    tapped_for_mana: list[CardState] = Field(default_factory=list)
    overflow: ManaPool | None = None

    choices: list[int | None] | None = None
    """CR 118.13a: one pinned option per symbol of `cost`, or None to leave the
    choice to the engine. Set it to insist that Dismember's `{B/P}` is paid
    with black mana rather than with life."""

    mana_payment: ManaPayment | None = None
    """How the mana part was settled, once it has been (CR 118.13)."""

    _preexisting: ManaPool | None = PrivateAttr(default=None)
    """The payer's floating mana as it stood when the payment opened, so a
    rewind (CR 733.1) can put it back after `pay` spent part of it."""

    @classmethod
    def for_total(
        cls, total: TotalCost, game: Any = None, payer: str | None = None
    ) -> "CostPayment":
        """Open a payment for a composite cost.

        `payer` is who is paying. It is what makes a Phyrexian symbol payable
        with life, since the life has to come from a real life total, and it
        falls back to whoever the components already name.

        The payment's pool opens as a copy of that player's floating mana, so
        mana already in their pool can pay this cost (see `_seed_payer_pool`).
        """
        components = list(total.components)
        if payer is None:
            payer = next((c.payer for c in components if c.payer is not None), None)
        payment = cls(cost=total.mana, components=components, game=game, payer=payer)
        payment._seed_payer_pool()
        return payment

    @property
    def total_cost(self) -> TotalCost:
        return TotalCost(mana=self.cost, components=self.components)

    @property
    def is_settled(self) -> bool:
        return self.step in {CostStep.PAID, CostStep.CANCELLED}

    @property
    def life_available(self) -> int:
        """What the payer may put towards a Phyrexian symbol (CR 107.4f, 119.4).

        Their whole life total: CR 119.4 lets life be paid down to zero, and
        losing the game for it is a state-based action afterwards, not a reason
        the cost could not be paid.
        """
        if self.game is None or self.payer is None:
            return 0
        try:
            return int(self.game.player(self.payer).life)
        except (KeyError, ValueError, AttributeError):
            return 0

    @property
    def shortfall(self) -> bool:
        """True if the pool still cannot cover the mana part of the cost."""
        return not self.pool.can_pay(self.cost, life_available=self.life_available)

    @property
    def unpayable(self) -> str | None:
        """Why the non-mana components cannot be paid, or None (CR 118.3)."""
        for component in self.components:
            reason = component.why_not(self.game)
            if reason is not None:
                return reason
        return None

    def choose(self, choices: list[int | None]) -> "CostPayment":
        """Pin how each symbol of the cost is paid (CR 118.13a)."""
        if len(choices) != len(self.cost.symbols):
            raise ValueError(f"expected {len(self.cost.symbols)} choices, got {len(choices)}")
        self.choices = list(choices)
        return self

    def tap_for_mana(self, source: CardState, produces: list[Color]) -> ManaPool:
        """Tap a permanent for mana and put what it makes into the pool.

        `produces` is what this activation makes, so a dual land is called with
        the single colour chosen, not with everything it could make.

        A creature that has not been under its controller's control since their
        most recent turn began cannot be tapped for mana (CR 302.6, 602.5a)
        unless it has haste (CR 702.10c); see `can_tap_for_mana`.

        Mana from a snow permanent (CR 205.4g) is marked as such, because `{S}`
        can only be paid with mana produced by a snow source (CR 107.4h, 106.3).

        CR 106.12a: an ability that triggers "whenever a permanent is tapped
        for mana" triggers when this mana ability resolves and produces mana -
        emitted here, the only place the engine taps a permanent for mana.
        """
        self._require_open()
        if not can_tap_for_mana(source, self.game):
            raise ValueError(
                f"{source.name} has not been under {source.controller or 'its controller'}'s "
                "control since their most recent turn began, so its {T} ability "
                "cannot be activated"
            )
        self._transition(CostStep.TAPPING)

        source.tap()
        self.tapped_for_mana.append(source)
        self.pool.add_all(produces, snow=is_snow_source(source))
        if self.game is not None:
            self.game.emit(tapped_for_mana_event(source))
        return self.pool

    def auto_tap(self, sources: Iterable[CardState]) -> list[CardState]:
        """Solve which of `sources` to tap, and which colour each makes, to
        cover this payment's mana part - and do it.

        A dual land, a shockland, and an any-colour source all offer a choice
        of colour (CR 605.1a's mana abilities do not require the choice to be
        made until the ability resolves), but once the cost to pay is fixed,
        which colour makes it payable is deterministic bookkeeping in the
        overwhelming majority of cases, not a strategic decision - this finds
        a legal assignment the same way a player filling in a dual land's
        colour to make their spell work would, rather than making the player
        name it for every cast. CR 601.2g: mana abilities are activated
        before the cost is paid; CR 118.3c: activating any of them, or all of
        them, is never mandatory, so this stops as soon as the pool can pay
        and never taps more than that.

        What this will not choose on the player's behalf: a source with any
        cost beyond `{T}` (life, a sacrifice, an exert, more mana), or a
        source whose only free ability carries a CR 106.6 spend restriction
        this engine cannot verify was honoured - both are filtered out before
        the search even starts, by `free_tap_mana_ability`.

        Prefers the fewest sources, and among equally-small choices prefers
        spending the least flexible ones (a basic over a dual, a dual over an
        any-colour source) so a flexible source stays untapped - see
        `_flexibility`. Raises a `ValueError` naming the cost if no legal
        assignment of `sources` exists; nothing is tapped when that happens.
        """
        self._require_open()
        if not self.shortfall:
            return []

        candidates = _auto_tap_candidates(self, sources)
        base_floating = dict(self.pool.floating)
        base_snow = dict(self.pool.snow)
        max_size = min(len(candidates), max(1, self.cost.converted))

        for size in range(1, max_size + 1):
            for combo in combinations(candidates, size):
                plan = _solve_colours(
                    combo, base_floating, base_snow, self.cost, self.life_available
                )
                if plan is not None:
                    for source, colors in plan:
                        self.tap_for_mana(source, colors)
                    return [source for source, _ in plan]

        raise ValueError(f"no combination of the available mana sources can pay {self.cost}")

    def add_mana(self, color: Color, amount: int = 1, snow: bool = False) -> ManaPool:
        """Add mana that came from somewhere other than tapping a permanent."""
        self._require_open()
        self.pool.add(color, amount, snow=snow)
        return self.pool

    def finish_tapping(self) -> CostStep:
        """Declare the pool filled and ready to pay from."""
        self._require_open()
        self._transition(CostStep.POOLED)
        return self.step

    def settle_mana(self) -> ManaPayment:
        """Work out how the mana part would be paid, or raise if it cannot.

        The search lives on `ManaPool`; this is where the payer's life total
        joins it, which is the only thing that makes a Phyrexian symbol payable
        with life through the engine (CR 107.4f).
        """
        payment = self.pool.payment_for(
            self.cost, life_available=self.life_available, choices=self.choices
        )
        if payment is None:
            raise ValueError(f"pool {self.pool.floating} cannot pay {self.cost}")
        return payment

    def pay(self) -> ManaPool:
        """Pay the whole total cost and return the mana still floating after.

        Everything is checked before anything is spent, so a cost that cannot
        be paid in full leaves the machine exactly as it was and the caller can
        tap another source or cancel outright (CR 118.3, 601.2h).

        Life owed for a Phyrexian symbol is paid as one more component of the
        total cost, so it leaves the life total through the same machinery as
        "pay 2 life" printed on a card, and rewinds with it (CR 733.1).

        That overflow does not vanish here. The remainder is written back into
        the payer's mana pool, where it stays until the current step or phase
        ends, and can pay for something else first (CR 106.4a).
        """
        self._require_open()
        if self.step in {CostStep.PENDING, CostStep.TAPPING}:
            self.finish_tapping()

        unpayable = self.unpayable
        if unpayable is not None:
            raise ValueError(unpayable)

        mana_payment = self.settle_mana()
        life = (
            pay_life_cost(
                mana_payment.life_paid,
                self.payer,
                description=f"pay {mana_payment.life_paid} life for {self.cost}",
            )
            if mana_payment.life_paid
            else None
        )
        components = [*self.components, *([life] if life is not None else [])]
        if life is not None:
            owed = life.why_not(self.game)
            if owed is not None:
                raise ValueError(owed)

        # Pay first: a pool that falls short leaves the machine untouched, so the
        # caller can tap another source and try again.
        floating = dict(self.pool.floating)
        snow = dict(self.pool.snow)
        self.pool.pay(self.cost, payment=mana_payment)

        paid: list[CostComponent] = []
        try:
            for component in components:
                component.pay(self.game)
                paid.append(component)
        except Exception:
            for component in reversed(paid):
                component.unpay(self.game)
            self.pool.floating = floating
            self.pool.snow = snow
            raise

        if life is not None:
            self.components.append(life)
        self.mana_payment = mana_payment
        self._transition(CostStep.PAID)
        self._write_back_remainder()
        self.overflow = self.pool
        return self.overflow

    def cancel(self) -> None:
        """Rewind: undo every component paid, untap the mana sources, empty the pool.

        The payer's own floating mana needs no restoring here: the payment
        worked on a copy, so their pool was never touched (see
        `_seed_payer_pool`).
        """
        self._require_open()
        self._undo_everything()
        self._transition(CostStep.CANCELLED)

    def rewind(self) -> None:
        """Undo the payment even if it was already made in full.

        CR 601.6: if the casting turns out to be illegal after the proposal was
        completed, the game returns to the moment before it began, and CR 733.1
        cancels any payments already made. A finished payment is otherwise
        closed, so this is the one door out of PAID.

        From PAID the reversal is total: `pay` already replaced the payer's
        pool with the remainder, so the pre-existing floating mana the payment
        spent is put back (CR 733.1 reverses "any payments already made"). The
        mana the payment's own activations produced does not come back - those
        activations are undone, their sources untapped by `_undo_everything`,
        and their mana died with the copy.
        """
        if self.step is CostStep.CANCELLED:
            return
        if self.step is not CostStep.PAID:
            self.cancel()
            return

        self._undo_everything()
        self._restore_payer_pool()
        self.overflow = None
        self.step = CostStep.CANCELLED

    def _seed_payer_pool(self) -> None:
        """Start the pool from the payer's floating mana, on a copy.

        CR 202.1a: "The mana cost of an object represents what a player must
        spend from their mana pool to cast that card", and CR 106.4 lets mana
        already floating there pay "immediately", so a payment opens on what
        its payer already has. It works on a copy so that a cancelled payment
        (CR 733.1) throws away only what the payment itself produced: the
        player's pre-existing floating mana never leaves their pool, while the
        mana abilities activated along the way (CR 601.2g) add into the copy
        and die with it when the payment is undone. `pay` writes the remainder
        back, and `rewind` restores this snapshot.
        """
        if self.game is None or self.payer is None:
            return
        try:
            floating = self.game.player(self.payer).mana_pool
        except (KeyError, ValueError, AttributeError):
            return
        self.pool = ManaPool(floating=dict(floating.floating), snow=dict(floating.snow))
        self._preexisting = ManaPool(floating=dict(floating.floating), snow=dict(floating.snow))

    def _write_back_remainder(self) -> None:
        """Leave what the payment did not spend floating in the payer's pool.

        CR 106.4a: "If any mana remains in a player's mana pool after mana is
        spent to pay a cost, that player announces what mana is still there" -
        the engine has no announcement to read, but the remainder belongs in
        the player's pool, where it stays until the step ends (CR 703.4q) and
        can pay for something else first (CR 106.4). The payment's pool is a
        working copy, so the player's pool is given the remainder's contents,
        never aliased to it.
        """
        if self.game is None or self.payer is None:
            return
        try:
            pool = self.game.player(self.payer).mana_pool
        except (KeyError, ValueError, AttributeError):
            return
        pool.floating = dict(self.pool.floating)
        pool.snow = dict(self.pool.snow)

    def _restore_payer_pool(self) -> None:
        """Put the payer's floating mana back the way it was before payment.

        The PAID half of CR 733.1's reversal: `pay` replaced the pool with the
        remainder, which spent whatever pre-existing mana the payment used, so
        undoing the whole action puts that mana back.
        """
        if self._preexisting is None or self.game is None or self.payer is None:
            return
        try:
            pool = self.game.player(self.payer).mana_pool
        except (KeyError, ValueError, AttributeError):
            return
        pool.floating = dict(self._preexisting.floating)
        pool.snow = dict(self._preexisting.snow)

    def _undo_everything(self) -> None:
        for component in reversed(self.components):
            component.unpay(self.game)
        for source in self.tapped_for_mana:
            source.untap()
        self.tapped_for_mana = []
        self.pool.empty()
        self.mana_payment = None

    def _require_open(self) -> None:
        if self.is_settled:
            raise ValueError(f"payment is already {self.step}")

    def _transition(self, target: CostStep) -> None:
        if target not in _ALLOWED[self.step]:
            raise ValueError(f"cannot go from {self.step} to {target}")
        self.step = target
