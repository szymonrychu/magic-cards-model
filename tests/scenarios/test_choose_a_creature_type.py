""" "As [this] enters, choose a creature type." accepts only a creature type.

Every CR number below was read in full with `mise run rules:find` in the
session that wrote this file:

- **CR 205.3m** - "Creatures and kindreds share their lists of subtypes; these
  subtypes are called creature types. One creature type is two words long:
  Time Lord. All other creature types are one word long: Advisor, ..." - the
  whole list of legal answers. "Island" is not on it (it is a land type).
- **CR 614.12a** - "If a replacement effect that modifies how a permanent
  enters the battlefield requires a choice, that choice is made before the
  permanent enters the battlefield." The choice is mandatory, so an empty
  answer is no answer.
- **CR 608.2d** - "The player can't choose an option that's illegal or
  impossible."

Cavern of Souls is the reported card; Unclaimed Territory is the off-pool proof
that the check belongs to the template, not to one card.
"""

import pytest

from magic_cards_model.data.creature_types import RULES_FILE, creature_types, rules_creature_types
from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Choice, ChoiceKind
from tests.scenarios.harness import Scenario


def _cavern_board():
    scenario = Scenario().player("alice", hand=["Cavern of Souls"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _territory_board():
    scenario = Scenario().player("alice", hand=["Unclaimed Territory"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _quality_questions(scenario, source: str):
    return [
        decision
        for decision in scenario.questions_asked()
        if decision.kind is DecisionKind.CHOOSE_A_QUALITY and decision.source == source
    ]


def test_the_bundled_list_is_the_rules_list():
    """The accepted set is CR 205.3m's own text, bundled because `.rules/` is
    not committed. When the rules file is on disk the two must agree word for
    word, so a stale bundle fails here rather than refusing a new type."""
    if not RULES_FILE.exists():
        pytest.skip("run `mise run rules:pull` to compare against the rules text")
    assert creature_types() == rules_creature_types(RULES_FILE.read_text())


def test_the_list_holds_the_two_word_type_and_no_land_type():
    types = creature_types()
    assert "Time Lord" in types
    assert "Eldrazi" in types
    assert "Zombie" in types
    assert "Island" not in types
    assert "" not in types


def test_cavern_of_souls_offers_every_creature_type():
    scenario = _cavern_board()
    scenario.will_choose("Eldrazi", source="Cavern of Souls")

    scenario.play_land("Cavern of Souls")

    (question,) = _quality_questions(scenario, "Cavern of Souls")
    assert question.options == creature_types()


def test_cavern_of_souls_refuses_a_land_type():
    scenario = _cavern_board()
    scenario.will_choose("Island", source="Cavern of Souls")

    with pytest.raises(ValueError, match=r"'Island' is not a creature type \(CR 205\.3m\)"):
        scenario.play_land("Cavern of Souls")


def test_cavern_of_souls_refuses_an_empty_answer():
    scenario = _cavern_board()
    scenario.will_choose("", source="Cavern of Souls")

    with pytest.raises(ValueError, match=r"CR 614\.12a"):
        scenario.play_land("Cavern of Souls")


def test_the_two_word_creature_type_is_accepted():
    scenario = _cavern_board()
    scenario.will_choose("Time Lord", source="Cavern of Souls")

    cavern = scenario.play_land("Cavern of Souls")

    assert cavern.choice == Choice(kind=ChoiceKind.CREATURE_TYPE, value="Time Lord")


def test_an_unanswered_creature_type_choice_still_names_a_creature_type():
    scenario = _cavern_board()

    cavern = scenario.play_land("Cavern of Souls")

    assert cavern.zone is Zone.BATTLEFIELD
    assert cavern.choice is not None
    assert cavern.choice.kind is ChoiceKind.CREATURE_TYPE
    assert cavern.choice.value in creature_types()


def test_unclaimed_territory_refuses_a_card_name():
    scenario = _territory_board()
    scenario.will_choose("Lightning Bolt", source="Unclaimed Territory")

    with pytest.raises(ValueError, match=r"'Lightning Bolt' is not a creature type"):
        scenario.play_land("Unclaimed Territory")


def test_unclaimed_territory_records_a_real_creature_type():
    scenario = _territory_board()
    scenario.will_choose("Elf", source="Unclaimed Territory")

    territory = scenario.play_land("Unclaimed Territory")

    assert territory.zone is Zone.BATTLEFIELD
    assert territory.choice == Choice(kind=ChoiceKind.CREATURE_TYPE, value="Elf")
    (question,) = _quality_questions(scenario, "Unclaimed Territory")
    assert question.options == creature_types()
