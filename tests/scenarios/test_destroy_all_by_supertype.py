"""Scenario: "Destroy all legendary creatures." / "Destroy all nonlegendary
creatures." - a mass destruction whose qualifier names a supertype, read
through the same qualifier grammar as "Destroy all creatures."

Invasion of Fiora's enters trigger: "choose one or both - Destroy all
legendary creatures. / Destroy all nonlegendary creatures." Each mode is the
generic mass-destroy clause with a CR 205.4a supertype (or its negation)
ANDed onto the card type, read off the computed board.

Every CR number here was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 205.4a** - an object can have one or more supertypes, printed before
  its card types; legendary is one.
- **CR 700.2** - modal "choose one or both"; the modes are chosen as the
  triggered ability is put on the stack (CR 603.3c).
- **CR 701.8a** - to destroy a permanent is to move it from the battlefield
  to its owner's graveyard.
- **CR 310.4b** - the Siege enters with its defense counters.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import NO_FURTHER_MODES
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

FIORA = "Invasion of Fiora"
LEGENDARY = "Destroy all legendary creatures."
NONLEGENDARY = "Destroy all nonlegendary creatures."


def _board() -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=[FIORA], battlefield=["Ragavan, Nimble Pilferer", "Grizzly Bears"])
        .player("bob", battlefield=["Thalia, Guardian of Thraben", "Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _names(scenario: Scenario) -> set[str]:
    return {card.name for card in scenario.game.battlefield if card.name != FIORA}


def _enter_choosing(scenario: Scenario, *modes: str):
    for mode in modes:
        scenario.will_choose_mode(mode, username="alice")
    if len(modes) == 1:
        scenario.will_choose_mode(NO_FURTHER_MODES, username="alice")
    siege = scenario.put_onto_battlefield(FIORA, "alice")
    scenario.pass_until_resolved()
    return siege


def test_legendary_mode_destroys_every_legendary_creature_and_nothing_else():
    scenario = _board()
    _enter_choosing(scenario, LEGENDARY)
    assert _names(scenario) == {"Grizzly Bears", "Llanowar Elves"}


def test_nonlegendary_mode_destroys_every_nonlegendary_creature_and_nothing_else():
    scenario = _board()
    _enter_choosing(scenario, NONLEGENDARY)
    assert _names(scenario) == {
        "Ragavan, Nimble Pilferer",
        "Thalia, Guardian of Thraben",
    }


def test_both_modes_destroy_every_creature_and_leave_the_siege():
    """The Siege is a battle, not a creature, so neither mode reaches it."""
    scenario = _board()
    siege = _enter_choosing(scenario, LEGENDARY, NONLEGENDARY)
    assert _names(scenario) == set()
    assert siege.zone is Zone.BATTLEFIELD
    assert siege.counter_count("defense") == 4


def test_the_supertype_is_read_off_the_battlefield_not_the_hand():
    """A legendary creature card in hand is not a permanent (CR 110.1)."""
    scenario = (
        Scenario()
        .player("alice", hand=[FIORA, "Ragavan, Nimble Pilferer"])
        .player("bob", battlefield=["Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _enter_choosing(scenario, LEGENDARY)
    assert scenario.find("Ragavan, Nimble Pilferer", Zone.HAND, "alice") is not None
    assert {card.name for card in scenario.game.battlefield} == {FIORA, "Llanowar Elves"}
