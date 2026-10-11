"""Scenario: Swirl the Mists - "As this enchantment enters, choose a color
word. All instances of color words in the text of spells and permanents are
changed to the chosen color word."

CR 612.1 and CR 613.1c (layer 3: text-changing effects), CR 612.2 (only words
used as color words change: a card's own name never does), CR 611.3a (the
effect applies while the enchantment is on the battlefield and stops the
moment it leaves).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

SWIRL = "Swirl the Mists"


def board(*, alice_battlefield=(), bob_battlefield=(), alice_hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[SWIRL, *alice_hand],
            battlefield=list(alice_battlefield),
            library=["Island"] * 4,
        )
        .player("bob", battlefield=list(bob_battlefield), library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def enter_swirl(scenario, color):
    scenario.will_choose(color, source=SWIRL)
    return scenario.put_onto_battlefield(SWIRL, "alice")


def sunlance_can_target(scenario, name, owner="bob"):
    casting = scenario.cast("Sunlance", "alice", targets=[scenario.creature(name, owner)])
    casting.cancel()


def test_a_permanents_protection_colour_word_is_changed():
    scenario = board(bob_battlefield=["Kor Firewalker"])
    firewalker = scenario.creature("Kor Firewalker", "bob")
    assert "protection from red" in " ".join(
        scenario.game.characteristics_of(firewalker).abilities
    ).lower()

    enter_swirl(scenario, "blue")

    lines = " ".join(scenario.game.characteristics_of(firewalker).abilities).lower()
    assert "protection from blue" in lines and "protection from red" not in lines


def test_a_spells_target_restriction_is_changed():
    """Sunlance ("target nonwhite creature") reads "nonblue" under Swirl: a
    white creature becomes a legal target and a blue one an illegal target."""
    scenario = board(
        alice_hand=["Sunlance"],
        alice_battlefield=["Plains"],
        bob_battlefield=["Savannah Lions", "Wind Drake"],
    )
    with pytest.raises(ValueError):
        sunlance_can_target(scenario, "Savannah Lions")
    sunlance_can_target(scenario, "Wind Drake")

    enter_swirl(scenario, "blue")

    sunlance_can_target(scenario, "Savannah Lions")
    with pytest.raises(ValueError):
        sunlance_can_target(scenario, "Wind Drake")


def test_a_cards_name_is_not_changed():
    scenario = board(bob_battlefield=["Black Knight"])
    knight = scenario.creature("Black Knight", "bob")

    enter_swirl(scenario, "red")

    assert knight.name == "Black Knight"
    lines = " ".join(scenario.game.characteristics_of(knight).abilities).lower()
    assert "protection from red" in lines and "protection from white" not in lines


def test_the_change_ends_when_the_enchantment_leaves():
    scenario = board(bob_battlefield=["Kor Firewalker"])
    firewalker = scenario.creature("Kor Firewalker", "bob")
    swirl = enter_swirl(scenario, "blue")
    assert "protection from blue" in " ".join(
        scenario.game.characteristics_of(firewalker).abilities
    ).lower()

    scenario.game.put_into_graveyard(swirl)

    lines = " ".join(scenario.game.characteristics_of(firewalker).abilities).lower()
    assert "protection from red" in lines and "protection from blue" not in lines
    assert swirl.zone is Zone.GRAVEYARD


def test_a_card_that_arrives_later_is_changed_too():
    scenario = board(alice_hand=["Kor Firewalker"])
    enter_swirl(scenario, "green")
    firewalker = scenario.put_onto_battlefield("Kor Firewalker", "alice")

    lines = " ".join(scenario.game.characteristics_of(firewalker).abilities).lower()
    assert "protection from green" in lines
