"""The player chooses which sources to tap, and the cost matches what they made.

CR 601.2g has the player activate mana abilities while announcing the spell;
which sources to activate is the player's decision, not the game's. With three
Forests and an Island in play, a {1}{G} spell can legally be paid {G}{G} from
two Forests or {U}{G} from a Forest and the Island - the Island's blue covers
the generic part either way round (CR 107.4b: generic costs may be paid with
mana of any type). Blue alone cannot pay the green pip, and a payment that
cannot be made is rewound (CR 601.2h: the spell is not cast).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import Casting
from magic_cards_model.machines.cost import CostStep
from magic_cards_model.models import Color, Zone

from .harness import PlayedScenario, Scenario, mana_from


def announce(scenario: PlayedScenario, name: str, username: str = "alice") -> Casting:
    """Begin casting, with the game attached so the payment can be made."""
    casting = scenario.cast(name, username=username)
    casting.game = scenario.game
    return casting


def mixed_board() -> Scenario:
    """The user's report: 3x Forest, 1x Island, and a {1}{G} creature in hand."""
    return (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Forest", "Forest", "Forest", "Island"],
        )
        .player("bob")
    )


def two_islands_board() -> Scenario:
    """2x Island and a Forest, for costs paid from the wrong colours."""
    return (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Island", "Island", "Forest"],
        )
        .player("bob")
    )


def tapped_names(scenario: PlayedScenario) -> list[str]:
    """What is tapped, read off the game's shared battlefield."""
    return [state.name for state in scenario.game.battlefield if state.tapped]


def test_two_forests_pay_it_as_green_green():
    scenario = mixed_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest")

    casting = announce(scenario, "Grizzly Bears")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *forests[:2])

    assert payment.step is CostStep.PAID, "the cast went through"
    assert tapped_names(scenario) == ["Forest", "Forest"]
    assert scenario.player("alice").mana_pool.floating == {}


def test_a_forest_and_the_island_pay_it_as_blue_green():
    scenario = mixed_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island")
    (forest,) = scenario.untapped_sources("Forest")

    casting = announce(scenario, "Grizzly Bears")
    payment = casting.begin_paying()
    scenario.pay_with(payment, forest, island)

    assert tapped_names(scenario) == ["Forest", "Island"]
    assert scenario.player("alice").mana_pool.floating == {}, (
        "the blue covered the generic pip exactly, so nothing is left over"
    )


def test_the_order_the_sources_are_activated_does_not_matter():
    scenario = mixed_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island")
    (forest,) = scenario.untapped_sources("Forest")

    casting = announce(scenario, "Grizzly Bears")
    payment = casting.begin_paying()
    scenario.pay_with(payment, island, forest)

    assert sorted(tapped_names(scenario)) == ["Forest", "Island"], (
        "the same two sources end up tapped whichever order they were activated in"
    )
    assert scenario.player("alice").mana_pool.floating == {}


def test_blue_alone_cannot_pay_the_green_pip():
    """The Island's blue covers the generic symbol, but {G} needs green
    (CR 107.4a: coloured costs must be paid with mana of that colour).
    """
    scenario = mixed_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island")

    casting = announce(scenario, "Grizzly Bears")
    payment = casting.begin_paying()
    payment.tap_for_mana(island, mana_from(island))
    with pytest.raises(ValueError, match="cannot pay"):
        payment.pay()

    payment.rewind()
    assert tapped_names(scenario) == [], "the refused payment untapped the Island"
    assert scenario.find("Grizzly Bears", Zone.HAND, "alice")


def test_two_islands_cannot_pay_it_either():
    """Two blue cover the generic symbol but nothing pays the green pip."""
    scenario = two_islands_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    islands = scenario.untapped_sources("Island", "Island")

    casting = announce(scenario, "Grizzly Bears")
    payment = casting.begin_paying()
    for island in islands:
        payment.tap_for_mana(island, mana_from(island))
    with pytest.raises(ValueError, match="cannot pay"):
        payment.pay()

    payment.rewind()
    assert tapped_names(scenario) == []


def test_two_islands_and_a_forest_pay_it_with_blue_spare():
    """{U}{U}{G} against {1}{G}: blue pays the generic, green pays the pip."""
    scenario = two_islands_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    islands = scenario.untapped_sources("Island", "Island")
    (forest,) = scenario.untapped_sources("Forest")

    casting = announce(scenario, "Grizzly Bears")
    payment = casting.begin_paying()
    for island in islands:
        payment.tap_for_mana(island, mana_from(island))
    payment.tap_for_mana(forest, mana_from(forest))
    payment.pay()

    assert payment.step is CostStep.PAID
    assert sorted(tapped_names(scenario)) == ["Forest", "Island", "Island"]
    assert scenario.player("alice").mana_pool.floating == {Color.BLUE: 1}, (
        "two blue and a green pay {1}{G} with one blue left over"
    )


def test_over_tapping_the_wrong_colours_leaves_the_right_remainder():
    """{1}{G} paid from one Forest and two Islands: the cost takes the green
    pip and one generic, and the spare blue stays floating (CR 106.4a).
    """
    scenario = two_islands_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    islands = scenario.untapped_sources("Island", "Island")
    (forest,) = scenario.untapped_sources("Forest")

    casting = announce(scenario, "Grizzly Bears")
    payment = casting.begin_paying()
    for island in islands:
        payment.tap_for_mana(island, mana_from(island))
    payment.tap_for_mana(forest, mana_from(forest))

    # One Island more than the cost needs: pay() takes the green pip and one
    # generic, and the last blue is the remainder.
    payment.pay()
    assert scenario.player("alice").mana_pool.floating == {Color.BLUE: 1}
