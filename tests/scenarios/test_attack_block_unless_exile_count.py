"""A creature's own "can't attack or block unless there are N or more cards in
<zone>" restriction: Ketramose, the New Dawn's "Ketramose can't attack or block
unless there are seven or more cards in exile.", and Deep-Sea Terror's "This
creature can't attack unless there are seven or more cards in your graveyard."
(the second printing - attack only, a different zone and "your"; legal in
Modern and Pioneer, in no deck in the api's pool).

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 508.1c** - "The active player checks each creature they control to see
  whether it's affected by any restrictions (effects that say a creature can't
  attack, or that it can't attack unless some condition is met). If any
  restrictions are being disobeyed, the declaration of attackers is illegal."
- **CR 509.1b** - the same for blockers: "effects that say a creature can't
  block, or that it can't block unless some condition is met".
- **CR 400.1** - exile is one zone shared by all players; each graveyard is
  its own player's.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import PlayedScenario, Scenario

KETRAMOSE = "Ketramose, the New Dawn"
TERROR = "Deep-Sea Terror"


def board(
    alice: list[str],
    *,
    alice_exile: int = 0,
    bob_exile: int = 0,
    alice_graveyard: int = 0,
    bob_graveyard: int = 0,
    bob: list[str] | None = None,
) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=alice,
            exile=["Plains"] * alice_exile,
            graveyard=["Plains"] * alice_graveyard,
            library=["Plains"] * 5,
        )
        .player(
            "bob",
            battlefield=bob or [],
            exile=["Swamp"] * bob_exile,
            graveyard=["Swamp"] * bob_graveyard,
            library=["Swamp"] * 5,
        )
        .build()
    )
    for state in scenario.game.battlefield:
        state.summoning_sick = False
    return scenario


@pytest.mark.parametrize("name", [KETRAMOSE, TERROR])
def test_the_restriction_line_is_handled(name: str) -> None:
    (clause,) = [c for c in classify_clauses(card(name)) if "unless" in c.text]

    assert clause.category == HANDLED


# -- Ketramose: attack and block, cards in exile -------------------------------


def test_it_cannot_attack_with_six_cards_in_exile() -> None:
    scenario = board([KETRAMOSE], alice_exile=6)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ketramose = scenario.creature(KETRAMOSE, "alice")

    assert not scenario.can_attack(ketramose)
    with pytest.raises(ValueError, match=r"CR 508\.1c"):
        scenario.attack_with(ketramose)


def test_it_can_attack_with_seven_cards_in_exile() -> None:
    """ "seven or more" - exactly seven is enough."""
    scenario = board([KETRAMOSE], alice_exile=7)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ketramose = scenario.creature(KETRAMOSE, "alice")

    scenario.attack_with(ketramose)

    assert scenario.attackers() == [ketramose]


def test_exile_is_one_zone_so_everyone_s_exiled_cards_count() -> None:
    """CR 400.1: four of alice's and three of bob's are seven cards in exile."""
    scenario = board([KETRAMOSE], alice_exile=4, bob_exile=3)
    scenario.start_at(Step.DECLARE_ATTACKERS)

    assert scenario.can_attack(scenario.creature(KETRAMOSE, "alice"))


def test_graveyard_cards_are_not_cards_in_exile() -> None:
    scenario = board([KETRAMOSE], alice_exile=3, alice_graveyard=10)
    scenario.start_at(Step.DECLARE_ATTACKERS)

    assert not scenario.can_attack(scenario.creature(KETRAMOSE, "alice"))


def test_it_cannot_block_with_six_cards_in_exile() -> None:
    scenario = board(["Grizzly Bears"], bob=[KETRAMOSE], bob_exile=6)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.advance()
    ketramose = scenario.creature(KETRAMOSE, "bob")

    assert not scenario.game.can_block(ketramose, bears)
    with pytest.raises(ValueError, match=r"CR 509\.1b"):
        scenario.block(bears, ketramose)


def test_it_can_block_with_seven_cards_in_exile() -> None:
    scenario = board(["Grizzly Bears"], bob=[KETRAMOSE], bob_exile=7)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.advance()
    ketramose = scenario.creature(KETRAMOSE, "bob")

    scenario.block(bears, ketramose)

    assert scenario.blockers() == [ketramose]


def test_the_count_is_read_when_attackers_are_declared() -> None:
    """CR 611.3a: a card exiled during the turn counts from then on."""
    scenario = board([KETRAMOSE], alice_exile=6, alice_graveyard=1)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ketramose = scenario.creature(KETRAMOSE, "alice")
    scenario.game.exile_cards(list(scenario.player("alice").graveyard))
    scenario.start_at(Step.DECLARE_ATTACKERS)

    assert scenario.can_attack(ketramose)


# -- Deep-Sea Terror: attack only, cards in your graveyard ---------------------


def test_six_cards_in_your_graveyard_is_not_enough_to_attack() -> None:
    scenario = board([TERROR], alice_graveyard=6)
    scenario.start_at(Step.DECLARE_ATTACKERS)

    assert not scenario.can_attack(scenario.creature(TERROR, "alice"))


def test_seven_cards_in_your_graveyard_lets_it_attack() -> None:
    scenario = board([TERROR], alice_graveyard=7)
    scenario.start_at(Step.DECLARE_ATTACKERS)

    assert scenario.can_attack(scenario.creature(TERROR, "alice"))


def test_an_opponent_s_graveyard_does_not_count() -> None:
    """ "your graveyard" - bob's ten cards are not alice's."""
    scenario = board([TERROR], alice_graveyard=2, bob_graveyard=10)
    scenario.start_at(Step.DECLARE_ATTACKERS)

    assert not scenario.can_attack(scenario.creature(TERROR, "alice"))


def test_an_attack_only_restriction_does_not_stop_it_blocking() -> None:
    scenario = board(["Grizzly Bears"], bob=[TERROR])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.advance()
    terror = scenario.creature(TERROR, "bob")

    scenario.block(bears, terror)

    assert scenario.blockers() == [terror]
