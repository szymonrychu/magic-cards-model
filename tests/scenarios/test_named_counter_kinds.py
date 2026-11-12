"""Scenario: a counter's kind is its name, and any name is a kind (CR 122.1).

CR 122.1 (looked up with `mise run rules:find 122.1` in the session that wrote
this file): "Counters with the same name or description are interchangeable."
The rules list a few kinds that do something of their own (CR 122.1a-j) and
leave every other name to the card that invents it, so the engine keys counters
by name and never by a closed list (`Counter | str`, `Counters`).

Cards: **Malcolm, Alluring Scoundrel** ("chorus", on itself, read back by name
in a threshold) and **Blademane Baku** ("ki", removed as X at once). Neither name
is a member of the `Counter` enum, which is the point.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

MALCOLM = "Malcolm, Alluring Scoundrel"
BAKU = "Blademane Baku"


def _malcolm_hits(*, library=("Island", "Island")):
    scenario = (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], library=list(library), battlefield=[MALCOLM])
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    malcolm = scenario.creature(MALCOLM, "alice")
    scenario.attack_with(malcolm, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    return scenario, malcolm


def test_chorus_and_ki_are_not_rules_defined_kinds():
    assert {"chorus", "ki"}.isdisjoint({kind.value for kind in Counter})


def test_a_card_can_put_a_counter_whose_name_the_rules_never_list():
    scenario, malcolm = _malcolm_hits()

    scenario.resolve_top()

    assert malcolm.counter_count("chorus") == 1
    assert dict(malcolm.counters.items()) == {"chorus": 1}
    assert "chorus" in malcolm.counters
    assert malcolm.counter_count("ki") == 0


def test_counters_of_the_same_name_are_interchangeable_across_triggers():
    scenario, malcolm = _malcolm_hits()
    scenario.resolve_top()

    malcolm.add_counters("chorus", 2)  # put by anything else: the same counters

    assert malcolm.counter_count("chorus") == 3
    assert malcolm.remove_counters("chorus", 3) == 0
    assert "chorus" not in malcolm.counters


def test_counters_of_another_name_do_not_count_toward_a_named_threshold():
    scenario = (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], library=["Island"], battlefield=[MALCOLM])
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    malcolm = scenario.creature(MALCOLM, "alice")
    malcolm.add_counters("ki", 5)
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    scenario.will_discard(bears, username="alice")
    scenario.will_take_the_may(True, source=MALCOLM)
    scenario.attack_with(malcolm, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()

    scenario.resolve_top()

    assert malcolm.counter_count("chorus") == 1
    assert malcolm.counter_count("ki") == 5
    assert bears.zone is Zone.GRAVEYARD


def test_baku_removes_x_ki_counters_as_a_cost_and_gets_two_power_for_each():
    scenario = (
        Scenario()
        .player("alice", battlefield=[BAKU, "Mountain", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    baku = scenario.creature(BAKU, "alice")
    baku.add_counters("ki", 3)

    scenario.activate(baku, *scenario.untapped_sources("Mountain"), x_value=2)
    scenario.resolve_top()

    assert baku.counter_count("ki") == 1
    assert scenario.game.characteristics_of(baku).power == 1 + 4


def test_baku_cannot_pay_for_more_ki_counters_than_it_has():
    scenario = (
        Scenario()
        .player("alice", battlefield=[BAKU, "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    baku = scenario.creature(BAKU, "alice")
    baku.add_counters("ki", 1)

    with pytest.raises(ValueError):
        scenario.activate(baku, *scenario.untapped_sources("Mountain"), x_value=2)

    assert baku.counter_count("ki") == 1
