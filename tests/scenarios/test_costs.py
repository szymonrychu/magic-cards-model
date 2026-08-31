"""Scenario: costs that are not mana (CR 118.3, 601.2b, 601.2f-h).

Every cost here is the one the real card prints. `additional_cost_phrases` and
`alternative_cost_phrases` read the sentence off the Scryfall oracle text, and
the tests assert on that text before building the cost, so a scenario cannot
quietly invent a cost the card does not have.

The thread running through the file is CR 733.1: an action that cannot be
completed legally is reversed in full and any payment already made is
cancelled. A sacrifice that happened must un-happen; life paid must come back.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import Casting
from magic_cards_model.machines.cost import (
    CostPayment,
    TotalCost,
    additional_cost_phrases,
    alternative_cost_phrases,
    discard_cost,
    exile_cost,
    pay_life_cost,
    sacrifice_cost,
    tap_cost,
)
from magic_cards_model.models import Color, ManaCost, Zone

from .harness import PlayedScenario, Scenario, mana_from


def announce(scenario: PlayedScenario, name: str, username: str = "alice") -> Casting:
    """Begin casting, with the game attached so non-mana costs can be paid."""
    casting = scenario.cast(name, username=username)
    casting.game = scenario.game
    return casting


# -- additional costs (CR 118.8a, 601.2b) ----------------------------------


def fling_board(creatures: int = 1) -> Scenario:
    """Alice holds Fling, with lands for it and creatures to throw."""
    return (
        Scenario()
        .player(
            "alice",
            hand=["Fling"],
            battlefield=["Mountain", "Mountain", *["Grizzly Bears"] * creatures],
        )
        .player("bob")
    )


def test_an_additional_cost_of_sacrificing_a_creature_is_paid_on_the_way_to_the_stack():
    """Fling: "As an additional cost to cast this spell, sacrifice a creature."

    CR 702.48b-style timing: the permanent is chosen while announcing the spell
    (CR 601.2b) and sacrificed as the total cost is paid (CR 601.2h).
    """
    scenario = fling_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert additional_cost_phrases(scenario.find("Fling", Zone.HAND).card) == [
        "sacrifice a creature"
    ]

    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)
    casting = announce(scenario, "Fling")
    casting.add_additional_cost(TotalCost.of(None, sacrifice_cost(bears)))
    casting.choose_targets(["bob"])

    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain"))
    spell = scenario.put_on_stack(casting)

    assert bears.zone is Zone.GRAVEYARD
    assert spell.zone is Zone.STACK


def test_an_additional_cost_with_nothing_to_pay_it_rewinds_the_whole_cast():
    """CR 118.3: a cost cannot be paid without the resources to pay it fully.

    Fling with no creature on the battlefield is not a cheaper Fling; it is a
    spell that was never cast. The lands untap and the card is back in hand.
    """
    scenario = fling_board(creatures=0).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = announce(scenario, "Fling")
    casting.add_additional_cost(TotalCost.of(None, sacrifice_cost(required=1)))
    casting.choose_targets(["bob"])

    payment = casting.begin_paying()
    mountains = scenario.untapped_sources("Mountain", "Mountain")

    with pytest.raises(ValueError, match="needs 1"):
        scenario.pay_with(payment, *mountains)

    casting.cancel()

    assert scenario.find("Fling", Zone.HAND).zone is Zone.HAND
    assert all(mountain.untapped for mountain in mountains)
    assert scenario.game.stack_is_empty


def test_a_paid_sacrifice_comes_back_when_the_cast_is_rewound():
    """CR 733.1: payments already made are cancelled when the action reverses."""
    scenario = fling_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)
    mountains = scenario.untapped_sources("Mountain", "Mountain")

    casting = announce(scenario, "Fling")
    casting.add_additional_cost(TotalCost.of(None, sacrifice_cost(bears)))
    payment = casting.begin_paying()
    scenario.pay_with(payment, *mountains)
    assert bears.zone is Zone.GRAVEYARD

    casting.cancel()

    assert bears.zone is Zone.BATTLEFIELD
    assert "Grizzly Bears" in scenario.battlefield_names()
    assert all(mountain.untapped for mountain in mountains)
    assert scenario.find("Fling", Zone.HAND).zone is Zone.HAND


def test_discarding_as_an_additional_cost_puts_the_cards_in_the_graveyard():
    """Cathartic Reunion: "discard two cards"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cathartic Reunion", "Grizzly Bears", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert additional_cost_phrases(scenario.find("Cathartic Reunion", Zone.HAND).card) == [
        "discard two cards"
    ]

    fodder = [
        scenario.find("Grizzly Bears", Zone.HAND),
        scenario.find("Lightning Bolt", Zone.HAND),
    ]
    casting = announce(scenario, "Cathartic Reunion")
    casting.add_additional_cost(TotalCost.of(None, discard_cost(*fodder)))
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.put_on_stack(casting)

    assert all(card.zone is Zone.GRAVEYARD for card in fodder)
    assert [card.name for card in scenario.player("alice").graveyard] == [
        "Grizzly Bears",
        "Lightning Bolt",
    ]


def life_board(life: int = 20) -> Scenario:
    """Alice holds Fumarole, whose additional cost is 3 life."""
    return Scenario().player(
        "alice",
        life=life,
        hand=["Fumarole"],
        battlefield=["Swamp", "Mountain", "Mountain", "Mountain", "Mountain"],
    )


def test_paying_life_as_an_additional_cost_comes_off_the_life_total():
    """Fumarole: "pay 3 life" (CR 118.3b)."""
    scenario = life_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert additional_cost_phrases(scenario.find("Fumarole", Zone.HAND).card) == ["pay 3 life"]

    casting = announce(scenario, "Fumarole")
    casting.add_additional_cost(TotalCost.of(None, pay_life_cost(3)))
    payment = casting.begin_paying()
    scenario.pay_with(
        payment, *scenario.untapped_sources("Swamp", "Mountain", "Mountain", "Mountain", "Mountain")
    )
    scenario.put_on_stack(casting)

    assert scenario.player("alice").life == 17


def test_life_cannot_be_paid_below_zero():
    """CR 119.4: life may only be paid if the life total is at least the amount."""
    scenario = life_board(life=2).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = announce(scenario, "Fumarole")
    casting.add_additional_cost(TotalCost.of(None, pay_life_cost(3)))
    payment = casting.begin_paying()
    sources = scenario.untapped_sources("Swamp", "Mountain", "Mountain", "Mountain", "Mountain")

    with pytest.raises(ValueError, match="cannot pay 3 life"):
        scenario.pay_with(payment, *sources)

    casting.cancel()

    assert scenario.player("alice").life == 2
    assert scenario.find("Fumarole", Zone.HAND).zone is Zone.HAND
    assert all(source.untapped for source in sources)


def test_paid_life_comes_back_when_the_cast_is_rewound():
    scenario = life_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = announce(scenario, "Fumarole")
    casting.add_additional_cost(TotalCost.of(None, pay_life_cost(3)))
    payment = casting.begin_paying()
    scenario.pay_with(
        payment, *scenario.untapped_sources("Swamp", "Mountain", "Mountain", "Mountain", "Mountain")
    )
    assert scenario.player("alice").life == 17

    casting.cancel()

    assert scenario.player("alice").life == 20


def test_tapping_a_creature_as_an_additional_cost():
    """Swallow Whole: "tap an untapped creature you control"."""
    scenario = (
        Scenario()
        .player("alice", hand=["Swallow Whole"], battlefield=["Plains", "Grizzly Bears"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert additional_cost_phrases(scenario.find("Swallow Whole", Zone.HAND).card) == [
        "tap an untapped creature you control"
    ]

    mine = scenario.untapped_sources("Grizzly Bears", username="alice")[0]
    theirs = scenario.untapped_sources("Grizzly Bears", username="bob")[0]
    theirs.tap()  # Swallow Whole exiles a *tapped* creature

    casting = announce(scenario, "Swallow Whole")
    casting.add_additional_cost(TotalCost.of(None, tap_cost(mine)))
    casting.choose_targets([theirs])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains"))
    scenario.put_on_stack(casting)

    assert mine.tapped


def test_a_creature_that_is_already_tapped_cannot_pay_a_tap_cost():
    """CR 118.3 spells this out: an already-tapped permanent cannot be tapped."""
    scenario = (
        Scenario()
        .player("alice", hand=["Swallow Whole"], battlefield=["Plains", "Grizzly Bears"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)
    mine.tap()

    casting = announce(scenario, "Swallow Whole")
    casting.add_additional_cost(TotalCost.of(None, tap_cost(mine)))
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="already tapped"):
        scenario.pay_with(payment, *scenario.untapped_sources("Plains"))


# -- alternative costs (CR 118.9) ------------------------------------------


def fireblast_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Fireblast"],
            battlefield=["Mountain", "Mountain"],
        )
        .player("bob")
    )


def test_an_alternative_cost_replaces_the_mana_cost_entirely():
    """Fireblast: "You may sacrifice two Mountains rather than pay this spell's
    mana cost." Two lands go, and not one mana is spent on a {4}{R}{R} spell.
    """
    scenario = fireblast_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fireblast = scenario.find("Fireblast", Zone.HAND)
    assert alternative_cost_phrases(fireblast.card) == ["sacrifice two Mountains"]
    assert fireblast.card.mana_cost == "{4}{R}{R}"

    mountains = scenario.untapped_sources("Mountain", "Mountain")
    casting = announce(scenario, "Fireblast")
    casting.choose_alternative_cost(TotalCost.of(None, sacrifice_cost(*mountains)))
    casting.choose_targets(["bob"])

    assert casting.total_cost.mana == ManaCost()
    assert casting.base_cost == ManaCost.parse("{4}{R}{R}")  # CR 118.9c

    payment = casting.begin_paying()
    payment.pay()
    spell = scenario.put_on_stack(casting)

    assert all(mountain.zone is Zone.GRAVEYARD for mountain in mountains)
    assert spell.zone is Zone.STACK


def test_declining_the_alternative_cost_means_paying_the_printed_one():
    """The alternative cost is optional (CR 118.9b), so the mana cost still works."""
    scenario = (
        Scenario()
        .player("alice", hand=["Fireblast"], battlefield=["Mountain"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = announce(scenario, "Fireblast")
    casting.choose_targets(["bob"])
    assert casting.total_cost.mana == ManaCost.parse("{4}{R}{R}")

    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Mountain"] * 6))
    scenario.put_on_stack(casting)

    assert scenario.battlefield_names().count("Mountain") == 6
    assert all(state.tapped for state in scenario.game.battlefield)


def test_force_of_will_pays_life_and_exiles_a_card_instead_of_mana():
    """Force of Will: "pay 1 life and exile a blue card from your hand"."""
    scenario = (
        Scenario()
        # Bob is the active player, because Grizzly Bears is a creature and
        # CR 117.1a only lets a noninstant spell be cast in its controller's own
        # main phase. Force of Will is an instant, so alice can answer it from
        # across the table (CR 304.1).
        .player("bob", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player("alice", hand=["Force of Will", "Counterspell"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    force = scenario.find("Force of Will", Zone.HAND, "alice")
    assert alternative_cost_phrases(force.card) == [
        "pay 1 life and exile a blue card from your hand"
    ]

    bears = scenario.cast_onto_stack(
        "Grizzly Bears",
        *scenario.untapped_sources("Forest", "Forest", username="bob"),
        username="bob",
    )
    scenario.pass_priority("bob")
    blue_card = scenario.find("Counterspell", Zone.HAND, "alice")

    casting = announce(scenario, "Force of Will")
    casting.choose_alternative_cost(
        TotalCost.of(None, pay_life_cost(1), exile_cost(blue_card)),
    )
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    payment.pay()
    scenario.put_on_stack(casting)

    assert scenario.player("alice").life == 19
    assert blue_card.zone is Zone.EXILE
    assert blue_card in scenario.game.exile


def test_rewinding_an_alternative_cost_returns_the_exiled_card_and_the_life():
    scenario = (
        Scenario().player("alice", hand=["Force of Will", "Counterspell"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    blue_card = scenario.find("Counterspell", Zone.HAND, "alice")

    casting = announce(scenario, "Force of Will")
    casting.choose_alternative_cost(TotalCost.of(None, pay_life_cost(1), exile_cost(blue_card)))
    payment = casting.begin_paying()
    payment.pay()

    casting.cancel()

    assert scenario.player("alice").life == 20
    assert blue_card.zone is Zone.HAND
    assert blue_card in scenario.player("alice").hand
    assert blue_card not in scenario.game.exile


# -- cost modification (CR 601.2f, 118.7) ----------------------------------


def test_a_generic_reduction_leaves_the_coloured_pips_alone():
    """CR 118.7a, on Fumarole's {3}{B}{R}: {4} off leaves {B}{R}, not {0}."""
    scenario = life_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = announce(scenario, "Fumarole")
    casting.reduce_cost("{4}")
    casting.add_additional_cost(TotalCost.of(None, pay_life_cost(3)))

    assert casting.total_cost.mana == ManaCost.parse("{B}{R}")

    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Mountain"))
    scenario.put_on_stack(casting)

    assert scenario.player("alice").life == 17


def test_an_increase_and_a_reduction_both_apply():
    scenario = life_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = announce(scenario, "Fumarole")
    casting.increase_cost("{2}")
    casting.reduce_cost("{1}")

    assert casting.total_cost.mana == ManaCost.parse("{4}{B}{R}")


# -- Phyrexian mana (CR 107.4f, 118.13a, 119.4) ----------------------------


def phyrexian_board(life: int = 20, lands: list[str] | None = None) -> Scenario:
    """Alice holds Dismember, {1}{B/P}{B/P}, and Gitaxian Probe, {U/P}."""
    return (
        Scenario()
        .player(
            "alice",
            life=life,
            hand=["Dismember", "Gitaxian Probe"],
            battlefield=list(lands or []),
        )
        .player("bob")
    )


def test_a_phyrexian_symbol_is_paid_with_life_when_there_is_no_mana():
    """CR 107.4f: Gitaxian Probe's {U/P} is one blue mana or 2 life."""
    scenario = phyrexian_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = announce(scenario, "Gitaxian Probe")
    payment = casting.begin_paying()
    payment.pay()
    spell = scenario.put_on_stack(casting)

    assert spell.zone is Zone.STACK
    assert scenario.player("alice").life == 18
    assert payment.mana_payment is not None
    assert payment.mana_payment.life_paid == 2
    assert payment.mana_payment.mana_spent == 0


def test_both_phyrexian_symbols_of_one_cost_can_take_life():
    """Dismember off a single Swamp: {1} in mana, 4 life for the two {B/P}."""
    scenario = phyrexian_board(lands=["Swamp"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = announce(scenario, "Dismember")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp"))

    assert scenario.player("alice").life == 16
    assert payment.mana_payment is not None
    assert payment.mana_payment.life_paid == 4


def test_life_is_only_spent_on_a_phyrexian_symbol_when_the_mana_is_short():
    """Three Swamps pay Dismember outright, so no life is lost."""
    scenario = phyrexian_board(lands=["Swamp", "Swamp", "Swamp"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = announce(scenario, "Dismember")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Swamp", "Swamp"))

    assert scenario.player("alice").life == 20
    assert payment.mana_payment is not None
    assert payment.mana_payment.life_paid == 0


def test_the_payer_can_insist_on_paying_life_with_the_mana_still_up():
    """CR 118.13a: the choice of how to pay a Phyrexian symbol is the payer's.

    Index 1 of a {B/P}'s options is the life half, so pinning both leaves two
    Swamps untapped and takes 4 life anyway.
    """
    scenario = phyrexian_board(lands=["Swamp", "Swamp", "Swamp"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = announce(scenario, "Dismember")
    payment = casting.begin_paying(choices=[None, 1, 1])
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp"))

    assert scenario.player("alice").life == 16
    assert len(scenario.untapped_sources("Swamp", "Swamp")) == 2


def test_a_phyrexian_cost_cannot_be_paid_with_life_the_player_does_not_have():
    """CR 119.4: life can only be paid down to zero, never past it."""
    scenario = phyrexian_board(life=3, lands=["Swamp"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = announce(scenario, "Dismember")
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="cannot pay"):
        scenario.pay_with(payment, *scenario.untapped_sources("Swamp"))

    assert scenario.player("alice").life == 3


def test_cancelling_gives_back_life_paid_for_a_phyrexian_symbol():
    """CR 733.1: the whole payment is reversed, life included."""
    scenario = phyrexian_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = announce(scenario, "Gitaxian Probe")
    payment = casting.begin_paying()
    payment.pay()
    assert scenario.player("alice").life == 18

    casting.cancel()

    assert scenario.player("alice").life == 20
    assert scenario.find("Gitaxian Probe", Zone.HAND, "alice")


# -- snow mana (CR 107.4h, 106.3, 205.4g) ----------------------------------


def test_a_snow_cost_is_paid_with_mana_from_a_snow_source():
    """Icehide Golem costs {S}; a Snow-Covered Forest is a snow permanent."""
    scenario = (
        Scenario()
        .player("alice", hand=["Icehide Golem"], battlefield=["Snow-Covered Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (forest,) = scenario.untapped_sources("Snow-Covered Forest")
    golem = scenario.cast_and_resolve("Icehide Golem", forest)

    assert golem.zone is Zone.BATTLEFIELD


def test_a_snow_cost_refuses_mana_from_an_ordinary_source():
    """CR 107.4h: {S} wants mana produced by a snow source, and a Forest is not one."""
    scenario = (
        Scenario()
        .player("alice", hand=["Icehide Golem"], battlefield=["Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = announce(scenario, "Icehide Golem")
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="cannot pay"):
        scenario.pay_with(payment, *scenario.untapped_sources("Forest"))


def test_snow_mana_still_pays_an_ordinary_cost():
    """A Snow-Covered Forest's green is green like any other (CR 106.3)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Llanowar Elves"], battlefield=["Snow-Covered Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (forest,) = scenario.untapped_sources("Snow-Covered Forest")
    elves = scenario.cast_and_resolve("Llanowar Elves", forest)

    assert elves.zone is Zone.BATTLEFIELD


# -- floating mana (CR 106.4, 202.1a, 601.2g, 106.4a, 733.1) ----------------


def elves_board(elves: int) -> Scenario:
    """Alice with that many Llanowar Elves and a Grizzly Bears to cast.

    The floating mana the scenarios need is staged the way a real turn makes
    it: each Elf's `{T}: Add {G}.` is activated through the engine's mana
    ability, which leaves the green floating in her pool (CR 106.4).
    """
    return (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Llanowar Elves"] * elves,
        )
        .player("bob")
    )


def float_green(scenario: PlayedScenario, amount: int) -> None:
    """Tap `amount` Elves so that much green is floating."""
    for _ in range(amount):
        (source,) = scenario.untapped_sources("Llanowar Elves")
        scenario.activate(source)
    assert scenario.player("alice").mana_pool.floating.get(Color.GREEN) == amount


def test_floating_mana_casts_a_spell_with_no_sources_tapped():
    """CR 202.1a: the mana cost is what a player spends from their mana pool,
    and CR 106.4 says mana already floating there "can be used to pay costs
    immediately". Two floating green cast Grizzly Bears with nothing tapped
    for the spell itself.
    """
    scenario = elves_board(2).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    float_green(scenario, 2)

    bears = scenario.cast_and_resolve("Grizzly Bears")

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").mana_pool.floating == {}
    elves = [
        state
        for state in scenario.player("alice").cards_in(Zone.BATTLEFIELD)
        if state.name == "Llanowar Elves"
    ]
    assert all(state.tapped for state in elves), (
        "the only taps were the staged activations, none for the spell"
    )


def test_mana_left_after_a_payment_stays_floating():
    """CR 106.4a: "If any mana remains in a player's mana pool after mana is
    spent to pay a cost, that player announces what mana is still there."
    Nothing in the engine announces, but the remainder stays in her pool,
    where it can pay for something else first (CR 106.4).
    """
    scenario = elves_board(3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    float_green(scenario, 3)

    scenario.cast_and_resolve("Grizzly Bears")  # {1}{G} from {G}{G}{G}

    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 1}


def test_rewinding_a_cast_puts_the_floating_mana_it_spent_back():
    """CR 733.1 reverses "any payments already made": a cast paid partly with
    pre-existing floating mana, then cancelled, gives that mana back. The
    staged activations themselves are not part of the cast, so their taps
    stand and their mana returns.
    """
    scenario = elves_board(2).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    float_green(scenario, 2)

    casting = announce(scenario, "Grizzly Bears")
    payment = casting.begin_paying()
    scenario.pay_with(payment)  # nothing new to tap; the floating copy pays
    casting.cancel()

    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 2}
    assert scenario.find("Grizzly Bears", Zone.HAND, "alice")


def test_mana_tapped_for_a_cancelled_payment_does_not_stay_in_the_pool():
    """The mana a payment's own activations produced dies with the payment
    (CR 733.1): the activations are undone, their sources untapped, and the
    mana - which lived in the payment's working copy, never in the player's
    pool - is gone. Pre-existing floating mana was never touched, because the
    payment worked on a copy of it.
    """
    scenario = elves_board(1).player("alice", battlefield=["Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    float_green(scenario, 1)
    (forest,) = scenario.untapped_sources("Forest")

    casting = announce(scenario, "Grizzly Bears")  # {1}{G}; only {G} floating
    payment = casting.begin_paying()
    payment.tap_for_mana(forest, mana_from(forest))
    payment.cancel()

    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 1}, (
        "the Forest's green went into the payment's copy and died with it"
    )
    assert not forest.tapped


def utopia_board() -> Scenario:
    """Alice holds Utopia Sprawl and a Forest to enchant, plus a payer land."""
    return (
        Scenario()
        .player("alice", hand=["Utopia Sprawl"], battlefield=["Forest", "Forest"])
        .player("bob")
    )


def enchant_a_forest(scenario: PlayedScenario):
    """Cast Utopia Sprawl for real, attached to a real Forest, choosing green.

    Returns the enchanted Forest. `_parse_mana_adding_trigger` (machines/
    effects.py) reads "its controller adds an additional one mana of the
    chosen color" off Utopia Sprawl's own printed text (CR 605.1b, CR
    106.12a); `CardState.choice` is what CR 614.12a's "as this Aura enters,
    choose a color" recorded.
    """
    scenario.start_at(Step.PRECOMBAT_MAIN)
    payer, forest = scenario.untapped_sources("Forest", "Forest")
    scenario.will_choose(Color.GREEN.value, source="Utopia Sprawl")
    sprawl = scenario.cast_and_resolve("Utopia Sprawl", payer, targets=[forest])
    assert sprawl.attached_to == forest.id
    return forest


def test_tapping_the_enchanted_land_once_adds_exactly_one_bonus_mana():
    """CR 106.12a: Utopia Sprawl's trigger fires once for the one real tap,
    and resolving it is the only thing that adds its bonus mana - passing
    priority afterwards, with nothing further tapped, adds nothing more.
    """
    scenario = utopia_board().build()
    forest = enchant_a_forest(scenario)

    scenario.activate(forest)
    assert scenario.stack_names() == ["Utopia Sprawl's triggered ability"]
    scenario.pass_priority("alice")
    scenario.pass_priority("bob")

    assert scenario.stack_names() == []
    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 2}

    # Further priority passes, with nothing new tapped, must never re-fire the
    # trigger - even once the stack-empty step boundary (CR 500.4) empties the
    # pool for an unrelated reason, what refills it is never more than {}.
    for _ in range(6):
        holder = scenario.priority_holder
        scenario.pass_priority(holder)
        assert scenario.stack_names() == []
        pool = scenario.player("alice").mana_pool.floating
        assert pool in ({Color.GREEN: 2}, {}), (
            f"no further tap happened, so the pool can only still hold the "
            f"original bonus mana or have emptied at a step boundary - not {pool}"
        )


def test_a_cancelled_payments_tap_does_not_leave_its_trigger_behind():
    """CR 733.1: "the entire action is reversed and any payments already made
    are canceled. No abilities trigger and no effects are applied due to any
    part of the illegal action." `CostPayment.tap_for_mana` queues Utopia
    Sprawl's CR 106.12a trigger the moment it taps the enchanted Forest
    (`Game.emit`, straight onto `pending_triggers`); before this fix,
    `cancel`/`rewind` untapped the Forest and emptied the payment's own pool
    but never withdrew that queued trigger. A solver that tries a combination
    including the enchanted land, finds it does not pay some other cost, and
    cancels - then retries, tapping the same now-untapped land again - used to
    leave one more stale trigger behind on every cancelled attempt, all of
    which still resolved and added their bonus mana once a payment finally
    went through: the reported symptom, mana funded far beyond what was
    really tapped.
    """
    scenario = utopia_board().build()
    forest = enchant_a_forest(scenario)

    for _ in range(9):
        payment = CostPayment(cost=ManaCost.parse("{7}"), game=scenario.game, payer="alice")
        payment.tap_for_mana(forest, [Color.GREEN])
        assert forest.tapped
        payment.cancel()
        assert not forest.tapped, "a cancelled payment must untap what it tapped"

    assert scenario.pending_triggers == [], (
        "nine cancelled attempts must leave nine fewer queued triggers, not nine more"
    )
    scenario.pass_priority("alice")
    scenario.pass_priority("bob")
    assert scenario.stack_names() == []
    assert scenario.player("alice").mana_pool.floating == {}, (
        "no real tap ever happened, so no bonus mana should exist"
    )

    # The land is still fully functional: a real, uncancelled tap still
    # queues and resolves the trigger exactly once.
    scenario.activate(forest)
    scenario.pass_priority("alice")
    scenario.pass_priority("bob")
    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 2}


def test_rewinding_a_completed_payment_also_withdraws_its_trigger():
    """The `PAID` half of CR 733.1's reversal (`rewind`, not `cancel`): a cast
    proposed with the enchanted Forest tapped, then found illegal and rewound
    after payment finished, must withdraw the trigger the same way a payment
    cancelled mid-tap does. Giant Growth is a plain {G} instant, so the one
    tap on the enchanted Forest is enough to finish paying in full.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Utopia Sprawl", "Giant Growth"], battlefield=["Forest", "Forest"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    forest = enchant_a_forest(scenario)

    casting = announce(scenario, "Giant Growth")
    payment = casting.begin_paying()
    payment.tap_for_mana(forest, [Color.GREEN])
    payment.pay()
    assert len(scenario.pending_triggers) == 1
    casting.cancel()

    assert scenario.pending_triggers == []
    assert not forest.tapped
    scenario.pass_priority("alice")
    scenario.pass_priority("bob")
    assert scenario.stack_names() == []
    assert scenario.player("alice").mana_pool.floating == {}


# -- static cost-increase effects (CR 601.2f, DDR#978) ----------------------
#
# `Game.cost_reduction_for` only ever reduced a spell's own cost (Emrakul-style
# self-discounts); nothing on the ordinary casting path applied a cost increase
# printed on a *different* permanent, so Sphere of Resistance, Trinisphere, and
# Damping Sphere all silently did nothing. `Casting.total_cost` now folds in
# `Game.static_cost_modifiers_for` whenever a game is attached, which is the
# path every ordinary cast already goes through (`begin_paying` ->
# `determine_cost` -> `total_cost`) - no opt-in call required, unlike the
# self-reduction case in test_dynamic_cost_reduction.py.
#
# Ordering: `apply_modifications` applies every increase before any reduction,
# and the floor (Trinisphere's shape) after both. This session's
# `knowledge_search` for CR 601.2f kept returning the sentence truncated right
# before the ordering clause ("...may pro..."), so that exact wording is NOT
# independently verified here - it matches the ordering `apply_modifications`
# already had (see its docstring's own citation caveat), which this file's
# `test_increase_applies_before_a_generic_reduction_can_touch_it` exercises
# directly rather than asserting the CR number.


def bolt_board(
    *battlefield: str, bob_battlefield: tuple[str, ...] = ("Grizzly Bears",)
) -> Scenario:
    """Alice holds Lightning Bolt, `battlefield` is hers, bob gets a blocker."""
    return (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=list(battlefield))
        .player("bob", battlefield=list(bob_battlefield))
    )


def test_sphere_of_resistance_taxes_lightning_bolt_by_one_generic_mana():
    """Sphere of Resistance: "Spells cost {1} more to cast." Lightning Bolt's
    {R} becomes {1}{R} while it is out - the DDR#978 repro."""
    scenario = bolt_board("Mountain", "Mountain", "Sphere of Resistance").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = announce(scenario, "Lightning Bolt")

    assert casting.total_cost.mana == ManaCost.parse("{1}{R}")


def test_sphere_of_resistance_makes_a_single_mountain_unable_to_pay():
    """The exact DDR#978 repro: one Mountain paid the untaxed {R}, but not the
    taxed {1}{R} - `pay_with` (a manual, non-auto payment) refuses to settle."""
    scenario = bolt_board("Mountain", "Sphere of Resistance").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    with pytest.raises(ValueError, match="cannot pay"):
        scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])


def test_sphere_of_resistance_taxes_the_second_mountain_pays_it():
    """Two Mountains cover the taxed {1}{R} - the fix, not just the failure."""
    scenario = bolt_board("Mountain", "Mountain", "Sphere of Resistance").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")

    bolt = scenario.cast_and_resolve(
        "Lightning Bolt", *mountains, username="alice", targets=[bears]
    )

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.game.permanents_controlled_by("bob") == []


def test_sphere_of_resistance_taxes_its_own_controllers_spells_too():
    """Sphere of Resistance is unconditional - "Spells cost {1} more to cast"
    names no player, so it taxes its own controller exactly as much as anyone
    else's spells."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Sphere of Resistance"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = announce(scenario, "Lightning Bolt", username="alice")

    assert casting.total_cost.mana == ManaCost.parse("{1}{R}")


def test_sphere_of_resistance_taxes_an_opponents_spell_too():
    """The Sphere sits on alice's side; bob's spell is taxed all the same,
    because CR 601.2f cost increases are not scoped to their source's
    controller unless the card's own text says so."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Sphere of Resistance"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = announce(scenario, "Lightning Bolt", username="bob")

    assert casting.total_cost.mana == ManaCost.parse("{1}{R}")


def test_a_qualified_increase_only_taxes_the_right_spell_types():
    """Thorn of Amethyst: "Noncreature spells cost {1} more to cast." Lightning
    Bolt (instant) is taxed; Grizzly Bears (creature) is not."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Grizzly Bears"],
            battlefield=["Mountain", "Forest", "Thorn of Amethyst"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bolt = announce(scenario, "Lightning Bolt")
    bears = announce(scenario, "Grizzly Bears")

    assert bolt.total_cost.mana == ManaCost.parse("{1}{R}")
    assert bears.total_cost.mana == ManaCost.parse("{1}{G}"), "a creature spell, untaxed"


def test_damping_sphere_taxes_the_second_spell_a_player_casts_this_turn():
    """Damping Sphere: "Each spell a player casts costs {1} more to cast for
    each other spell that player has cast this turn." The first Lightning
    Bolt this turn is untaxed; the second - one prior spell already cast -
    costs {1} more."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain"] * 4 + ["Damping Sphere"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first_bear, second_bear = scenario.game.permanents_controlled_by("bob")

    first_cast = announce(scenario, "Lightning Bolt")
    assert first_cast.total_cost.mana == ManaCost.parse("{R}"), "no prior spell this turn yet"
    mountains = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve(
        "Lightning Bolt", mountains[0], username="alice", targets=[first_bear]
    )

    second_cast = announce(scenario, "Lightning Bolt")
    assert second_cast.total_cost.mana == ManaCost.parse("{1}{R}"), (
        "one Lightning Bolt already cast this turn"
    )
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", *mountains, username="alice", targets=[second_bear])


def test_an_unreadable_cost_increase_fails_closed_and_leaves_a_notice():
    """Grand Arbiter Augustin IV: "Spells your opponents cast cost {1} more to
    cast." - a controller-relative increase this parser does not read, since
    it is not the unconditional "Spells cost {N} more" shape. It must neither
    silently apply the tax nor silently skip it: `Game.cost_modifier_notices`
    records the gap instead."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grand Arbiter Augustin IV"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = announce(scenario, "Lightning Bolt", username="bob")

    assert casting.total_cost.mana == ManaCost.parse("{R}"), "unread, so not applied - fail closed"
    assert len(scenario.game.cost_modifier_notices) == 1
    notice = scenario.game.cost_modifier_notices[0]
    assert notice.source_name == "Grand Arbiter Augustin IV"


def test_auto_tap_refuses_a_spell_the_increase_makes_unaffordable():
    """`CostPayment.auto_tap` must see the increased cost too, not just manual
    `pay_with` - the same solver the API's default `--sources`-less cast uses."""
    scenario = bolt_board("Mountain", "Sphere of Resistance").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = announce(scenario, "Lightning Bolt")
    casting.choose_targets([bears])
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="no combination of the available mana sources can pay"):
        payment.auto_tap(scenario.game.permanents_controlled_by("alice"))


# -- Trinisphere's floor (CR 601.2f) -----------------------------------------


def test_trinisphere_raises_a_one_mana_spell_to_three():
    """Trinisphere: "each spell that would cost less than three mana to cast
    costs three mana to cast." Lightning Bolt is {R} (mana value 1); the
    reminder text ("a spell that would cost {1}{B} to cast costs {2}{B} to
    cast instead") says the shortfall is made up in generic mana, so {R}
    becomes {2}{R} - not a flat "{3}" that would drop the red pip."""
    scenario = bolt_board("Mountain", "Mountain", "Mountain", "Trinisphere").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = announce(scenario, "Lightning Bolt")

    assert casting.total_cost.mana == ManaCost.parse("{2}{R}")
    assert casting.total_cost.mana.converted == 3


def test_trinisphere_does_not_touch_a_spell_already_at_three_or_more():
    """Fumarole is {3}{B}{R}, mana value 5 - already at or above the floor, so
    Trinisphere changes nothing."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fumarole"],
            battlefield=["Swamp", "Mountain", "Mountain", "Mountain", "Mountain", "Trinisphere"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = announce(scenario, "Fumarole")

    assert casting.total_cost.mana == ManaCost.parse("{3}{B}{R}")


def test_a_tapped_trinisphere_does_not_raise_the_floor():
    """ "As long as this artifact is untapped" is a condition on the ability
    itself (CR 611.3b keeps a static ability live only while its source is on
    the battlefield with the ability - being tapped turns this one off)."""
    scenario = bolt_board("Mountain", "Trinisphere").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (trinisphere,) = scenario.untapped_sources("Trinisphere", username="alice")
    trinisphere.tap()

    casting = announce(scenario, "Lightning Bolt")

    assert casting.total_cost.mana == ManaCost.parse("{R}")


def test_increase_applies_before_a_generic_reduction_can_touch_it():
    """The order matters: Lightning Bolt's {R} has no generic component to
    reduce (CR 118.7a) until an increase gives it one. Applying the increase
    first - `apply_modifications`'s documented order - lets a matching
    generic reduction cancel it straight back to {R}; reducing first would
    find nothing to touch and leave {1}{R} instead. Manual `increase_cost`/
    `reduce_cost` stand in for two real static abilities here because the
    fixture pool has no board-wide generic-cost-reducer to pair with Sphere
    of Resistance at a mana value low enough to make the order visible."""
    scenario = bolt_board("Mountain").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = announce(scenario, "Lightning Bolt")
    casting.increase_cost("{1}")
    casting.reduce_cost("{1}")

    assert casting.total_cost.mana == ManaCost.parse("{R}")
