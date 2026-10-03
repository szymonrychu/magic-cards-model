"""Scenario: "creatures you control gain <kw> until end of turn if a creature
(card in your graveyard | you control) has <kw>. The same is true for <list>."

Bleeding Effect (graveyard, beginning of combat on your turn), Concerted Effort
(each upkeep) and Odric, Lunarch Marshal (each combat). Each keyword in the
list is its own check against the board as the ability resolves (CR 608.2c),
the group is fixed once (CR 611.2c), and "landwalk"/"protection" copy the
exact instances present (CR 702.14: swampwalk is not islandwalk; CR 702.16:
protection from black is not protection from red).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from tests.scenarios.harness import Scenario


def has(scenario: Scenario, creature, keyword: str) -> bool:
    return has_keyword(creature, keyword, scenario.game)


def protections(scenario: Scenario, creature) -> list[str]:
    return scenario.game._effective_protection_qualities(creature)


def resolve_all_triggers(scenario: Scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


# -- Bleeding Effect -----------------------------------------------------------


def bleeding_effect(graveyard: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Bleeding Effect", "Grizzly Bears"],
            graveyard=graveyard,
        )
        .player("bob", graveyard=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.advance()  # beginning of combat
    resolve_all_triggers(scenario)
    return scenario, bears


def test_bleeding_effect_grants_each_keyword_found_in_a_graveyard_creature_card():
    scenario, bears = bleeding_effect(["Serra Angel", "Shock"])
    assert has(scenario, bears, "flying")
    assert has(scenario, bears, "vigilance")


def test_bleeding_effect_grants_only_the_keywords_present_not_the_whole_list():
    scenario, bears = bleeding_effect(["Serra Angel"])
    for absent in ("first strike", "double strike", "deathtouch", "lifelink", "trample", "reach"):
        assert not has(scenario, bears, absent), absent


def test_bleeding_effect_ignores_noncreature_cards_and_the_opponents_graveyard():
    scenario, bears = bleeding_effect(["Shock"])
    assert not has(scenario, bears, "flying")
    assert not has(scenario, bears, "vigilance")


# -- Concerted Effort ----------------------------------------------------------


def concerted_effort(battlefield: list[str]):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Concerted Effort", "Grizzly Bears", *battlefield])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.UNTAP)
    scenario.advance()  # upkeep
    resolve_all_triggers(scenario)
    return scenario, scenario.creature("Grizzly Bears", "alice")


def test_concerted_effort_shares_flying_and_vigilance_from_a_creature_you_control():
    scenario, bears = concerted_effort(["Serra Angel"])
    assert has(scenario, bears, "flying")
    assert has(scenario, bears, "vigilance")
    assert not has(scenario, bears, "trample")


def test_concerted_effort_copies_the_exact_landwalk_instance():
    scenario, bears = concerted_effort(["Street Wraith"])
    assert has(scenario, bears, "swampwalk")
    assert not has(scenario, bears, "islandwalk")
    assert not has(scenario, bears, "flying")


def test_concerted_effort_copies_the_exact_protection_instance():
    scenario, bears = concerted_effort(["Whirling Dervish"])
    assert protections(scenario, bears) == ["black"]


def test_concerted_effort_evaluates_every_keyword_independently():
    scenario, bears = concerted_effort(["Serra Angel", "Street Wraith", "Whirling Dervish"])
    assert has(scenario, bears, "flying")
    assert has(scenario, bears, "vigilance")
    assert has(scenario, bears, "swampwalk")
    assert protections(scenario, bears) == ["black"]
    assert not has(scenario, bears, "first strike")


def test_concerted_effort_with_nothing_to_share_grants_nothing():
    scenario, bears = concerted_effort([])
    assert not has(scenario, bears, "flying")
    assert not has(scenario, bears, "vigilance")
    assert protections(scenario, bears) == []


# -- Odric, Lunarch Marshal ----------------------------------------------------


def odric(battlefield: list[str]):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Odric, Lunarch Marshal", "Grizzly Bears", *battlefield])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.advance()  # beginning of combat
    resolve_all_triggers(scenario)
    return scenario, scenario.creature("Grizzly Bears", "alice")


def test_odric_shares_each_keyword_a_creature_you_control_has():
    scenario, bears = odric(["Serra Angel"])
    assert has(scenario, bears, "flying")
    assert has(scenario, bears, "vigilance")
    assert not has(scenario, bears, "first strike")
    assert not has(scenario, bears, "haste")


def test_odric_shares_first_strike_the_leading_keyword():
    scenario, bears = odric(["Youthful Knight"])
    assert has(scenario, bears, "first strike")
    assert not has(scenario, bears, "flying")


def test_odric_alone_grants_nothing():
    scenario, bears = odric([])
    for keyword in ("first strike", "flying", "vigilance", "trample", "haste"):
        assert not has(scenario, bears, keyword), keyword


def test_odric_shares_skulk():
    scenario, bears = odric(["Wharf Infiltrator"])
    assert has(scenario, bears, "skulk")
    assert not has(scenario, bears, "fear")


# -- Fear (CR 702.36): shared by Concerted Effort, and enforced when blocking ------


def fear_combat(blocker: str):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Concerted Effort", "Grizzly Bears", "Severed Legion"],
            library=["Forest"] * 3,
        )
        .player("bob", battlefield=[blocker], library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.UNTAP)
    scenario.game.untap_step()  # the creatures have been under alice's control since her last turn
    scenario.advance()  # upkeep
    resolve_all_triggers(scenario)
    bears = scenario.creature("Grizzly Bears", "alice")
    assert has(scenario, bears, "fear"), "Concerted Effort shares fear from Severed Legion"
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    return scenario, bears, scenario.creature(blocker, "bob")


def test_a_creature_given_fear_cannot_be_blocked_by_a_nonblack_nonartifact_creature():
    scenario, bears, blocker = fear_combat("Serra Angel")
    with pytest.raises(ValueError, match="fear"):
        scenario.block(bears, blocker)


def test_a_creature_given_fear_can_be_blocked_by_a_black_creature():
    scenario, bears, blocker = fear_combat("Severed Legion")
    scenario.block(bears, blocker)


def test_a_creature_given_fear_can_be_blocked_by_an_artifact_creature():
    scenario, bears, blocker = fear_combat("Adaptive Automaton")
    scenario.block(bears, blocker)
