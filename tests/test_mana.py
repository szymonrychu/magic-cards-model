"""Mana costs and paying them, symbol by symbol (CR 107.4, 118.13, 202.3).

Every cost in here is a real printed cost taken off a card in
`tests/fixtures/cards`, never a string invented to exercise a branch.
"""

import pytest

from magic_cards_model.models import Color, ManaCost, ManaPool
from magic_cards_model.models.mana import SymbolKind
from tests.cards import card
from tests.cards import pool as card_pool


def cost_of(name: str) -> ManaCost:
    """The printed mana cost of a real card in the pool."""
    return ManaCost.parse(card(name).mana_cost or "")


def pool_of(**counts: int) -> ManaPool:
    """A pool by colour letter: `pool_of(G=2, C=1)`."""
    mana = ManaPool()
    for letter, amount in counts.items():
        mana.add(Color(letter), amount)
    return mana


# --------------------------------------------------------------------------
# The plain symbols, as before
# --------------------------------------------------------------------------


def test_parses_a_mixed_cost():
    cost = ManaCost.parse("{2}{U}{U}")

    assert cost.generic == 2
    assert cost.colored == {Color.BLUE: 2}
    assert cost.converted == 4
    assert str(cost) == "{2}{U}{U}"


def test_parses_an_empty_cost():
    cost = ManaCost.parse("")

    assert cost.converted == 0


def test_x_is_folded_into_generic_once_chosen():
    cost = ManaCost.parse("{X}{R}")

    assert cost.x_count == 1
    assert cost.converted == 1  # CR 202.3e: X is zero while off the stack

    resolved = cost.with_x(3)
    assert resolved.x_count == 0
    assert resolved.converted == 4
    assert str(resolved) == "{3}{R}"


def test_rejects_unsupported_symbols():
    # {Q} is the untap symbol (CR 107.6). It never appears in a mana cost.
    with pytest.raises(ValueError, match="unsupported mana symbol"):
        ManaCost.parse("{Q}")


def test_pays_colours_before_generic():
    pool = pool_of(U=2, R=1, G=1)

    overflow = pool.pay(ManaCost.parse("{2}{U}{U}"))

    assert overflow.is_empty


def test_overflow_survives_the_payment():
    pool = pool_of(R=2, G=1)

    overflow = pool.pay(ManaCost.parse("{R}"))

    assert overflow.total == 2
    assert overflow.floating == {Color.RED: 1, Color.GREEN: 1}


def test_generic_does_not_eat_a_colour_it_still_needs():
    # One blue and two red, paying {2}{U}: the blue must survive the generic.
    pool = pool_of(U=1, R=2)

    overflow = pool.pay(ManaCost.parse("{2}{U}"))

    assert overflow.is_empty


def test_a_short_pool_cannot_pay():
    pool = pool_of(R=2)

    cost = ManaCost.parse("{2}{U}")
    assert not pool.can_pay(cost)
    with pytest.raises(ValueError, match="cannot pay"):
        pool.pay(cost)


def test_x_must_be_resolved_before_paying():
    pool = pool_of(R=1)

    with pytest.raises(ValueError, match="resolve X"):
        pool.pay(ManaCost.parse("{X}{R}"))


# --------------------------------------------------------------------------
# Every printed cost in the pool round-trips (CR 202.3)
# --------------------------------------------------------------------------


def _printed_costs() -> list[tuple[str, str, float | None]]:
    """(label, mana_cost, cmc) for every printed cost in the fixture pool."""
    costs: list[tuple[str, str, float | None]] = []
    for name, printing in sorted(card_pool().items()):
        if printing.name != name:
            continue  # the front-face alias of a multifaced card
        if printing.mana_cost is not None:
            costs.append((name, printing.mana_cost, printing.cmc))
        for face in printing.card_faces or []:
            costs.append((f"{name} // {face.name}", face.mana_cost, face.cmc))
    return costs


@pytest.mark.parametrize(("label", "mana_cost", "cmc"), _printed_costs())
def test_every_printed_cost_round_trips(label: str, mana_cost: str, cmc: float | None):
    """`str(ManaCost.parse(s))` reproduces the card's own `mana_cost`."""
    assert str(ManaCost.parse(mana_cost)) == mana_cost, label


@pytest.mark.parametrize(("label", "mana_cost", "cmc"), _printed_costs())
def test_every_printed_cost_has_scryfalls_mana_value(label: str, mana_cost: str, cmc: float | None):
    """CR 202.3: our mana value agrees with Scryfall's `cmc` on every card."""
    if cmc is None:
        pytest.skip(f"{label} has no face cmc")
    if " // " in mana_cost:
        pytest.skip(f"{label} is a two-part cost; see the whole-card tests below")
    assert ManaCost.parse(mana_cost).converted == int(cmc), label


def _two_part_cards():
    """Every card in the pool whose printed cost has two halves."""
    return [
        printing
        for name, printing in sorted(card_pool().items())
        if printing.name == name and " // " in (printing.mana_cost or "")
    ]


@pytest.mark.parametrize("printing", _two_part_cards(), ids=lambda c: c.name)
def test_a_two_part_cards_mana_value_follows_its_layout(printing):
    """Only a split card costs both halves.

    CR 709.4b combines them for a split card; CR 715.4 gives an adventurer card
    only its normal characteristics and CR 712.8a a double-faced card only its
    front face. Scryfall's own `cmc` is the check: it is 5 for the split
    Repudiate // Replicate and 3 for the adventurer Bonecrusher Giant, whose
    halves are {2}{R} and {1}{R}.
    """
    assert ManaCost.for_card(printing).converted == int(printing.cmc), printing.name


@pytest.mark.parametrize("printing", _two_part_cards(), ids=lambda c: c.name)
def test_a_split_cards_printed_string_round_trips(printing):
    """A split card keeps its separator; the others drop the half they do not use."""
    from magic_cards_model.models.card import Layout

    rendered = str(ManaCost.for_card(printing))
    if printing.layout is Layout.SPLIT:
        assert rendered == printing.mana_cost
    else:
        assert rendered == (printing.mana_cost or "").split(" // ")[0]


# --------------------------------------------------------------------------
# {C} - CR 107.4c
# --------------------------------------------------------------------------


def test_colourless_symbol_parses_as_its_own_requirement():
    cost = cost_of("Thought-Knot Seer")  # {3}{C}

    assert str(cost) == "{3}{C}"
    assert cost.generic == 3
    assert cost.colored == {Color.COLORLESS: 1}
    assert cost.converted == 4


def test_colourless_symbol_refuses_coloured_mana():
    """CR 107.4c: {C} can be paid only with one colourless mana."""
    cost = cost_of("Thought-Knot Seer")

    assert not pool_of(R=4).can_pay(cost)
    assert pool_of(R=3, C=1).can_pay(cost)


def test_colourless_symbol_is_not_spent_on_the_generic_part():
    # The single {C} in the pool has to survive the {3}, which is paid in red.
    pool = pool_of(R=3, C=1)

    assert pool.pay(cost_of("Thought-Knot Seer")).is_empty


# --------------------------------------------------------------------------
# Hybrid - CR 107.4e, 202.3f
# --------------------------------------------------------------------------


def test_hybrid_parses_and_round_trips():
    cost = cost_of("Kitchen Finks")  # {1}{G/W}{G/W}

    assert str(cost) == "{1}{G/W}{G/W}"
    assert [symbol.kind for symbol in cost.symbols] == [
        SymbolKind.GENERIC,
        SymbolKind.HYBRID,
        SymbolKind.HYBRID,
    ]
    assert cost.is_payable_in_multiple_ways


def test_hybrid_mana_value_uses_the_larger_half():
    """CR 202.3f: {G/W} is worth 1, so Kitchen Finks is 3."""
    assert cost_of("Kitchen Finks").converted == 3
    # A hybrid symbol is not a fixed colour requirement.
    assert cost_of("Kitchen Finks").colored == {}


def test_hybrid_is_payable_from_either_half():
    finks = cost_of("Kitchen Finks")

    assert pool_of(G=2, C=1).pay(finks).is_empty
    assert pool_of(W=2, C=1).pay(finks).is_empty
    assert pool_of(G=1, W=1, C=1).pay(finks).is_empty


def test_hybrid_needs_a_colour_for_each_half():
    # Three mana, but only one of them can pay a {G/W}.
    assert not pool_of(G=1, C=2).can_pay(cost_of("Kitchen Finks"))


def test_the_payer_can_pin_which_half_a_hybrid_uses():
    """CR 118.13a: the choice of how to pay belongs to the caster."""
    finks = cost_of("Kitchen Finks")
    pool = pool_of(G=2, W=2, C=1)

    # options for {G/W} are (green, white), in the symbol's printed order.
    payment = pool.payment_for(finks, choices=[None, 1, 1])

    assert payment is not None
    assert payment.spend[Color.WHITE] == 2  # both hybrids, as pinned
    assert payment.mana_spent == 3  # the {1} came out of the green


def test_a_pinned_half_the_pool_cannot_cover_is_unpayable():
    finks = cost_of("Kitchen Finks")
    pool = pool_of(G=2, C=1)

    assert pool.payment_for(finks, choices=[None, 0, 0]) is not None
    assert pool.payment_for(finks, choices=[None, 1, 1]) is None


# --------------------------------------------------------------------------
# The greedy trap
# --------------------------------------------------------------------------


def test_hybrid_is_paid_from_the_half_the_fixed_colours_do_not_need():
    """Tamiyo is {2}{G}{G/U/P}{U} and this pool has one blue.

    A greedy payment that settles the hybrid first can take the blue and then
    find nothing left for the printed {U}. The only assignment that works pays
    the hybrid green, so this is exactly the case a greedy solver fails.
    """
    tamiyo = cost_of("Tamiyo, Compleated Sage")
    pool = pool_of(G=2, U=1, C=2)

    assert pool.can_pay(tamiyo)
    payment = pool.payment_for(tamiyo)
    assert payment is not None
    assert payment.life_paid == 0
    assert pool.pay(tamiyo, payment=payment).is_empty


def test_generic_is_not_paid_from_mana_a_colour_still_needs():
    """The mirror: five mana, and only one assignment of the generic works."""
    tamiyo = cost_of("Tamiyo, Compleated Sage")
    # {2} must come from the two colourless; {G}, {G/U/P} and {U} take the rest.
    pool = pool_of(G=1, U=2, C=2)

    assert pool.pay(tamiyo).is_empty


# --------------------------------------------------------------------------
# Monocoloured hybrid - CR 107.4e, 202.3f
# --------------------------------------------------------------------------


def test_monocoloured_hybrid_parses_and_round_trips():
    cost = cost_of("Spectral Procession")  # {2/W}{2/W}{2/W}

    assert str(cost) == "{2/W}{2/W}{2/W}"
    assert all(symbol.kind is SymbolKind.MONOCOLORED_HYBRID for symbol in cost.symbols)
    assert cost.generic == 0  # it is not generic mana until the payer chooses


def test_monocoloured_hybrid_mana_value_is_the_generic_half():
    """CR 202.3f: the largest component of {2/W} is 2, so the cost is 6."""
    assert cost_of("Spectral Procession").converted == 6
    assert cost_of("Beseech the Queen").converted == 6


def test_monocoloured_hybrid_takes_three_white_or_six_of_anything():
    procession = cost_of("Spectral Procession")

    assert pool_of(W=3).can_pay(procession)
    assert pool_of(C=6).can_pay(procession)
    assert not pool_of(C=5).can_pay(procession)
    assert not pool_of(W=2).can_pay(procession)


def test_monocoloured_hybrid_mixes_the_two_halves():
    """One black and four generic pays {2/B}{2/B}{2/B}: B + 2 + 2."""
    beseech = cost_of("Beseech the Queen")
    pool = pool_of(B=1, C=4)

    payment = pool.payment_for(beseech)

    assert payment is not None
    assert payment.mana_spent == 5
    assert pool.pay(beseech, payment=payment).is_empty


def test_monocoloured_hybrid_prefers_the_cheaper_half():
    """With plenty of both, paying the colour spends three mana, not six."""
    procession = cost_of("Spectral Procession")
    pool = pool_of(W=3, C=6)

    payment = pool.payment_for(procession)

    assert payment is not None
    assert payment.mana_spent == 3
    assert payment.spend == {Color.WHITE: 3}


# --------------------------------------------------------------------------
# Phyrexian - CR 107.4f, 202.3g, 119.4
# --------------------------------------------------------------------------


def test_phyrexian_parses_and_round_trips():
    probe = cost_of("Gitaxian Probe")  # {U/P}
    dismember = cost_of("Dismember")  # {1}{B/P}{B/P}

    assert str(probe) == "{U/P}"
    assert str(dismember) == "{1}{B/P}{B/P}"
    assert probe.symbols[0].kind is SymbolKind.PHYREXIAN


def test_phyrexian_mana_value_is_one_per_symbol():
    """CR 202.3g: each Phyrexian symbol contributes 1."""
    assert cost_of("Gitaxian Probe").converted == 1
    assert cost_of("Dismember").converted == 3


def test_phyrexian_is_paid_with_mana_when_the_pool_has_it():
    probe = cost_of("Gitaxian Probe")
    pool = pool_of(U=1)

    payment = pool.payment_for(probe, life_available=20)

    assert payment is not None
    assert payment.life_paid == 0
    assert payment.spend == {Color.BLUE: 1}


def test_phyrexian_is_unpayable_from_an_empty_pool_unless_life_is_offered():
    """The pool cannot reach a life total, so life has to be handed to it."""
    probe = cost_of("Gitaxian Probe")

    assert not ManaPool().can_pay(probe)
    assert ManaPool().can_pay(probe, life_available=2)


def test_phyrexian_can_be_paid_at_exactly_two_life_but_not_at_one():
    """CR 119.4: a player may pay life only down to zero, not past it."""
    probe = cost_of("Gitaxian Probe")

    payment = ManaPool().payment_for(probe, life_available=2)
    assert payment is not None
    assert payment.life_paid == 2

    assert ManaPool().payment_for(probe, life_available=1) is None


def test_two_phyrexian_symbols_cost_two_life_each():
    dismember = cost_of("Dismember")
    pool = pool_of(C=1)

    payment = pool.payment_for(dismember, life_available=20)

    assert payment is not None
    assert payment.life_paid == 4
    assert payment.mana_spent == 1  # the printed {1} is still mana


def test_life_short_of_both_phyrexian_symbols_is_unpayable():
    dismember = cost_of("Dismember")
    pool = pool_of(C=1)

    assert pool.payment_for(dismember, life_available=3) is None
    assert pool.payment_for(dismember, life_available=4) is not None


def test_the_payer_can_choose_life_over_mana():
    """Black in the pool, but the caster may still pay 4 life (CR 118.13a)."""
    dismember = cost_of("Dismember")
    pool = pool_of(B=3)

    # {B/P} options are (black, 2 life); index 1 pins the life payment.
    payment = pool.payment_for(dismember, life_available=20, choices=[None, 1, 1])

    assert payment is not None
    assert payment.life_paid == 4
    assert payment.mana_spent == 1

    assert pool.pay(dismember, payment=payment).total == 2


def test_paying_never_touches_a_life_total_by_itself():
    """`pay` spends mana only; the caller applies `life_paid`."""
    dismember = cost_of("Dismember")
    pool = pool_of(C=1)

    payment = pool.payment_for(dismember, life_available=20)
    assert payment is not None

    pool.pay(dismember, payment=payment)
    assert pool.is_empty
    assert payment.life_paid == 4  # still owed by the player


# --------------------------------------------------------------------------
# Hybrid Phyrexian - CR 107.4f
# --------------------------------------------------------------------------


def test_hybrid_phyrexian_takes_either_colour_or_life():
    tamiyo = cost_of("Tamiyo, Compleated Sage")  # {2}{G}{G/U/P}{U}

    assert str(tamiyo) == "{2}{G}{G/U/P}{U}"
    assert tamiyo.converted == 5
    assert tamiyo.symbols[2].kind is SymbolKind.PHYREXIAN
    assert [str(option) for option in tamiyo.symbols[2].options] == ["{G}", "{U}", "2 life"]


def test_hybrid_phyrexian_falls_back_to_life_when_neither_colour_is_left():
    tamiyo = cost_of("Tamiyo, Compleated Sage")
    pool = pool_of(G=1, U=1, C=3)  # {G} and {U} take the only coloured mana

    assert not pool.can_pay(tamiyo)

    payment = pool.payment_for(tamiyo, life_available=20)
    assert payment is not None
    assert payment.life_paid == 2
    assert payment.mana_spent == 4


# --------------------------------------------------------------------------
# Snow - CR 107.4h, 106.3
# --------------------------------------------------------------------------


def test_snow_symbol_parses_and_round_trips():
    golem = cost_of("Icehide Golem")  # {S}

    assert str(golem) == "{S}"
    assert golem.converted == 1
    assert golem.symbols[0].kind is SymbolKind.SNOW


def test_snow_is_paid_with_mana_from_a_snow_source():
    """CR 107.4h: any type of mana, as long as a snow source made it."""
    golem = cost_of("Icehide Golem")
    assert card("Snow-Covered Forest").type_line.lower().startswith("basic snow land")

    pool = ManaPool()
    pool.add(Color.GREEN, snow=True)  # tapped a Snow-Covered Forest

    assert pool.can_pay(golem)
    assert pool.pay(golem).is_empty


def test_snow_refuses_mana_from_an_ordinary_source():
    golem = cost_of("Icehide Golem")

    assert not pool_of(G=1).can_pay(golem)
    assert not pool_of(C=5).can_pay(golem)


def test_snow_mana_is_still_ordinary_mana_for_everything_else():
    """A Snow-Covered Forest's green pays {G} like any other green."""
    pool = ManaPool()
    pool.add(Color.GREEN, snow=True)

    assert pool.pay(ManaCost.parse("{G}")).is_empty


def test_the_generic_part_does_not_eat_the_only_snow_mana():
    """Two real printed costs combined: Sol Ring's {1} plus Icehide Golem's {S}.

    One snow mana and one ordinary one. The generic has to take the ordinary
    mana, because the {S} cannot.
    """
    cost = ManaCost(symbols=cost_of("Sol Ring").symbols + cost_of("Icehide Golem").symbols)
    assert str(cost) == "{1}{S}"

    pool = ManaPool()
    pool.add(Color.GREEN, snow=True)
    pool.add(Color.RED)

    assert pool.pay(cost).is_empty


def test_snow_mana_is_tracked_out_of_the_pool_when_it_is_spent():
    pool = ManaPool()
    pool.add(Color.GREEN, 2, snow=True)
    pool.add(Color.GREEN, 1)

    pool.pay(cost_of("Icehide Golem"))

    assert pool.floating == {Color.GREEN: 2}
    assert pool.snow == {Color.GREEN: 1}


def test_emptying_the_pool_forgets_snow_too():
    pool = ManaPool()
    pool.add(Color.BLUE, 3, snow=True)

    pool.empty()

    assert pool.is_empty
    assert pool.snow == {}


# --------------------------------------------------------------------------
# Housekeeping
# --------------------------------------------------------------------------


def test_a_choice_list_must_match_the_symbols():
    with pytest.raises(ValueError, match="expected 3 choices"):
        pool_of(G=3).payment_for(cost_of("Kitchen Finks"), choices=[0])


def test_the_legacy_constructor_still_builds_a_cost():
    """The generic/coloured shape is still a way to say a plain cost."""
    cost = ManaCost(generic=2, colored={Color.BLUE: 2})

    assert str(cost) == "{2}{U}{U}"
    assert cost == ManaCost.parse("{2}{U}{U}")


def test_the_legacy_constructor_cannot_express_an_exotic_cost():
    """Why `plus`/`minus` work on symbols: this shape loses {G/W} entirely."""
    finks = cost_of("Kitchen Finks")

    assert ManaCost(generic=finks.generic, colored=finks.colored) != finks


# --------------------------------------------------------------------------
# Combining and reducing costs, symbol for symbol - CR 601.2f, 118.7
# --------------------------------------------------------------------------


def test_adding_an_additional_cost_keeps_hybrid_symbols():
    """CR 601.2f: a kicker on Kitchen Finks is {3}{G/W}{G/W}, not {3}."""
    finks = cost_of("Kitchen Finks")

    assert finks.plus(ManaCost.parse("{2}")) == ManaCost.parse("{3}{G/W}{G/W}")


def test_adding_a_cost_keeps_phyrexian_and_snow_symbols():
    assert cost_of("Dismember").plus(ManaCost.parse("{1}")) == ManaCost.parse("{2}{B/P}{B/P}")
    assert cost_of("Icehide Golem").plus(ManaCost.parse("{2}")) == ManaCost.parse("{2}{S}")


def test_adding_merges_generic_and_appends_the_rest_in_printed_order():
    assert ManaCost.parse("{1}{G}").plus(ManaCost.parse("{2}{G}")) == ManaCost.parse("{3}{G}{G}")
    assert ManaCost.parse("{G}").plus(ManaCost.parse("{2}")) == ManaCost.parse("{2}{G}")
    assert ManaCost.parse("{X}{R}").plus(ManaCost.parse("{2}")) == ManaCost.parse("{X}{2}{R}")


def test_a_generic_reduction_leaves_exotic_symbols_alone():
    """CR 118.7a: only the generic component is touched."""
    assert cost_of("Dismember").minus(ManaCost.parse("{1}")) == ManaCost.parse("{B/P}{B/P}")
    assert cost_of("Icehide Golem").minus(ManaCost.parse("{9}")) == ManaCost.parse("{S}")


def test_reducing_by_a_hybrid_symbol_needs_a_choice_nobody_can_make():
    """CR 118.7e: the payer picks a half when the reduction is applied."""
    with pytest.raises(ValueError, match="nobody to ask"):
        ManaCost.parse("{2}{G}").minus(cost_of("Kitchen Finks"))


# --------------------------------------------------------------------------
# Split cards - CR 709.4b
# --------------------------------------------------------------------------


def test_a_split_cards_cost_is_both_halves_combined():
    """CR 709.4b: the mana cost of a split card is its two halves combined.

    Scryfall writes it with a ` // ` between them, and CR 202.3d takes the mana
    value from that combined cost while the card is not on the stack.
    """
    repudiate = card("Repudiate // Replicate")
    cost = ManaCost.for_card(repudiate)

    assert str(cost) == repudiate.mana_cost, "the printed string round-trips"
    assert cost.converted == int(repudiate.cmc)
    assert cost.split_after is not None


def test_an_adventurer_card_costs_only_its_creature_half():
    """CR 715.4: outside the stack it has only its normal characteristics.

    The trap is that Scryfall prints `{2}{R} // {1}{R}` for Bonecrusher Giant
    exactly as it prints a split card's cost, but the Adventure half is not
    part of the card's cost and its mana value is 3, not 5.
    """
    giant = card("Bonecrusher Giant")
    cost = ManaCost.for_card(giant)

    assert str(cost) == "{2}{R}"
    assert cost.converted == int(giant.cmc) == 3
    assert cost.split_after is None


def test_an_ordinary_cost_has_no_split():
    assert ManaCost.parse("{2}{U}{U}").split_after is None
