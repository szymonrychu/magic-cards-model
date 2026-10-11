"""Shadrix Silverquill: "At the beginning of combat on your turn, you may
choose two. Each mode must target a different player." (EP-01 R2, T2
residual clause).

CR numbers verified with `mise run rules:find`:

- CR 700.2b: the controller of a modal triggered ability chooses the modes as
  the ability is put on the stack; if no mode is chosen it is removed.
- CR 700.2d: the same mode can't be chosen twice unless the card says so.
- CR 115.3: the same target can't be chosen several times for one
  instance of the word "target" - here the rider goes further, a different
  player per mode, so a second mode can't aim at the player the first did.
- CR 608.2c: the chosen modes run in printed order.

The instruction is optional ("you may choose two"): choosing no modes is
legal and removes the ability; choosing exactly one is not.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import NO_FURTHER_MODES
from magic_cards_model.machines.effects.modal import modal_trigger_profile
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario

TOKEN = "Target player creates a 2/1 white and black Inkling creature token with flying."
DRAW = "Target player draws a card and loses 1 life."
COUNTERS = "Target player puts a +1/+1 counter on each creature they control."


def _board(alice_creatures=("Grizzly Bears",), bob_creatures=("Hill Giant",)):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Shadrix Silverquill", *alice_creatures],
            library=["Plains"] * 4,
        )
        .player("bob", battlefield=list(bob_creatures), library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _into_combat(scenario) -> None:
    scenario.advance()
    assert scenario.step is Step.BEGINNING_OF_COMBAT


def _resolve_all(scenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def test_shadrix_is_fully_handled():
    bad = [c for c in card_support(card("Shadrix Silverquill")).clauses if c.outcome != "handled"]
    assert not bad, bad


def test_the_instruction_reads_as_an_optional_two_with_a_different_player_rider():
    effect = card("Shadrix Silverquill").oracle_text.split("\n", 1)[1]
    effect = effect.split(", ", 1)[1].replace("\n", " ")
    profile = modal_trigger_profile(effect)
    assert profile is not None
    assert [mode.text for mode in profile.modes] == [TOKEN, DRAW, COUNTERS]
    assert (profile.minimum, profile.maximum) == (2, 2)
    assert profile.optional is True
    assert profile.distinct_targets is True


def test_two_modes_aimed_at_two_different_players_both_happen():
    scenario = _board()
    scenario.will_choose_mode(TOKEN, username="alice")
    scenario.will_choose_mode(DRAW, username="alice")
    scenario.will_choose_targets("alice", username="alice")
    scenario.will_choose_targets("bob", username="alice")
    _into_combat(scenario)
    _resolve_all(scenario)

    inklings = [p for p in scenario.game.battlefield if p.name == "Inkling Token"]
    assert len(inklings) == 1 and inklings[0].controller == "alice"
    assert scenario.player("bob").life == 19
    assert len(scenario.player("bob").hand) == 1
    assert scenario.player("alice").life == 20
    assert not scenario.player("alice").hand


def test_counters_mode_goes_on_every_creature_the_target_player_controls():
    scenario = _board(alice_creatures=("Grizzly Bears", "Runeclaw Bear"))
    scenario.will_choose_mode(COUNTERS, username="alice")
    scenario.will_choose_mode(DRAW, username="alice")
    scenario.will_choose_targets("alice", username="alice")
    scenario.will_choose_targets("bob", username="alice")
    _into_combat(scenario)
    _resolve_all(scenario)

    for name in ("Grizzly Bears", "Runeclaw Bear", "Shadrix Silverquill"):
        creature = scenario.creature(name, "alice")
        assert creature.counters["+1/+1"] == 1, name
    assert scenario.creature("Hill Giant", "bob").counters["+1/+1"] == 0


def test_the_second_mode_cannot_target_the_player_the_first_mode_targeted():
    scenario = _board()
    scenario.will_choose_mode(TOKEN, username="alice")
    scenario.will_choose_mode(DRAW, username="alice")
    scenario.will_choose_targets("alice", username="alice")
    scenario.will_choose_targets("alice", username="alice")
    with pytest.raises(ValueError):
        _into_combat(scenario)


def test_choosing_no_modes_removes_the_ability():
    scenario = _board()
    scenario.will_choose_mode(NO_FURTHER_MODES, username="alice")
    _into_combat(scenario)
    _resolve_all(scenario)

    assert not [p for p in scenario.game.battlefield if p.name == "Inkling Token"]
    assert scenario.player("bob").life == 20


def test_it_does_not_trigger_at_the_beginning_of_the_opponents_combat():
    scenario = _board()
    scenario.start_at(Step.CLEANUP)
    scenario.advance()
    while scenario.step is not Step.BEGINNING_OF_COMBAT:
        scenario.advance()
    assert scenario.player().username == "bob"
    assert scenario.game.stack_is_empty
