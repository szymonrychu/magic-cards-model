"""Extort (CR 702.101).

CR 702.101a: "Extort is a triggered ability. "Extort" means "Whenever you
cast a spell, you may pay {W/B}. If you do, each opponent loses 1 life and
you gain life equal to the total life lost this way."" CR 702.101b: "If a
permanent has multiple instances of extort, each triggers separately."

The Kingpin of Crime (the listed card) and Syndic of Tithes (the second
printing) both print the bare keyword.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.support import card_support, executed_keywords
from tests.cards import card
from tests.scenarios.harness import Scenario


def test_extort_drains_one_when_paid():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Syndic of Tithes", "Mountain", "Plains"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_pay_the_mana_cost(True)
    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[giant]
    )
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 21


def test_extort_declined_drains_nothing():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Syndic of Tithes", "Mountain", "Plains"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_pay_the_mana_cost(False)
    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[giant]
    )
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 20
    assert scenario.player("alice").life == 20


def test_each_extort_instance_triggers_separately():
    """CR 702.101b, across two permanents: The Kingpin of Crime and Syndic of
    Tithes each trigger on the one spell."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Syndic of Tithes", "The Kingpin of Crime", "Mountain", "Plains", "Swamp"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_pay_the_mana_cost(True, times=None)
    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[giant]
    )
    assert len(scenario.stack_names()) == 3, "the Bolt and two extort triggers"
    while scenario.stack_names():
        scenario.pass_until_resolved()

    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 22


def test_extort_does_not_trigger_on_casting_the_extort_creature_itself():
    """ "Whenever you cast a spell" is an ability of a permanent: the spell
    that will become Syndic of Tithes is on the stack, not the battlefield,
    as it is cast (CR 113.6)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Syndic of Tithes"], battlefield=["Plains", "Plains", "Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack("Syndic of Tithes", *scenario.untapped_sources("Plains", "Plains"))
    assert scenario.stack_names() == ["Syndic of Tithes"]


def test_extort_cannot_be_paid_without_the_mana():
    """CR 118.3: with no untapped source for {W/B}, the payment is refused and
    nothing is drained."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Syndic of Tithes", "Mountain"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[giant]
    )
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 20


@pytest.mark.parametrize("name", ["Syndic of Tithes", "The Kingpin of Crime"])
def test_extort_is_executed_and_handled(name):
    assert executed_keywords(card(name)).get("extort") not in (None, "IGNORED")
    for clause in card_support(card(name)).clauses:
        assert clause.outcome == "handled", (name, clause.text, clause.outcome)
