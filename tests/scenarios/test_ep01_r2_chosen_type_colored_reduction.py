"""Scenario: "Spells of the chosen type you cast cost {W}{U}{B}{R}{G} less to
cast. This effect reduces only the amount of colored mana you pay." (CR 601.2f
determines the total cost; CR 118.7a-d say a colored reduction takes only
matching colored symbols, here with no spill into generic mana because the
card says so; CR 614.12a: the type was chosen as the permanent entered.)
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def _board(chosen, hand):
    scenario = (
        Scenario()
        .player("alice", hand=["Morophon, the Boundless", *hand], battlefield=["Forest"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose(chosen, source="Morophon, the Boundless")
    scenario.put_onto_battlefield("Morophon, the Boundless")
    return scenario


def _cost(scenario, name):
    return str(scenario.cast(name).total_cost.mana)


def test_a_chosen_type_spell_loses_its_colored_symbol():
    scenario = _board("Bear", ["Grizzly Bears"])
    assert _cost(scenario, "Grizzly Bears") == "{1}"


def test_a_spell_of_another_type_pays_in_full():
    scenario = _board("Elf", ["Grizzly Bears"])
    assert _cost(scenario, "Grizzly Bears") == "{1}{G}"


def test_the_reduction_never_spills_into_generic_mana():
    scenario = _board("Wolf", ["Lupine Prototype"])
    assert _cost(scenario, "Lupine Prototype") == "{2}"


def test_only_the_colored_symbols_present_are_removed():
    scenario = _board("Bear", ["Grizzly Bears"])
    casting = scenario.cast("Grizzly Bears")
    assert casting.total_cost.mana.converted == 1


def test_the_reduction_is_for_its_controller_only():
    scenario = (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], battlefield=["Forest"] * 4)
        .player("bob", hand=["Morophon, the Boundless"], battlefield=["Forest"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("Bear", source="Morophon, the Boundless")
    scenario.put_onto_battlefield("Morophon, the Boundless", "bob")
    assert _cost(scenario, "Grizzly Bears") == "{1}{G}"


def test_a_differently_worded_source_reduces_generic_mana_of_the_chosen_type():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Urza's Incubator", "Lupine Prototype", "Grizzly Bears"],
            battlefield=["Forest"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("Wolf", source="Urza's Incubator")
    scenario.put_onto_battlefield("Urza's Incubator")
    assert _cost(scenario, "Lupine Prototype") == "{0}"
    assert _cost(scenario, "Grizzly Bears") == "{1}{G}"
