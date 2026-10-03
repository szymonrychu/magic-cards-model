"""Pursued Whale: "Spells your opponents cast that target this creature cost {3}
more to cast." (CR 601.2f, with CR 601.2c announcing targets first).

The tax is keyed on the targets actually chosen: an opponent's spell that
targets the Whale is taxed, the same spell aimed elsewhere is not, and the
Whale's own controller is never taxed.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import ManaCost

from .harness import Scenario
from .test_costs import announce


def whale_board() -> Scenario:
    return (
        Scenario()
        .player(
            "bob",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Mountain", "Mountain", "Mountain", "Grizzly Bears"],
        )
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Pursued Whale", "Grizzly Bears"],
        )
    )


def test_opponents_spell_targeting_the_whale_costs_three_more():
    scenario = whale_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    whale = scenario.creature("Pursued Whale", "alice")

    bolt = announce(scenario, "Lightning Bolt", username="bob")
    assert bolt.total_cost.mana == ManaCost.parse("{R}"), "no targets chosen yet, no tax"
    bolt.choose_targets([whale])
    assert bolt.total_cost.mana == ManaCost.parse("{3}{R}")
    assert scenario.game.cost_modifier_notices == []


def test_the_tax_is_actually_paid_in_mana():
    scenario = whale_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    whale = scenario.creature("Pursued Whale", "alice")
    bolt = announce(scenario, "Lightning Bolt", username="bob")
    bolt.choose_targets([whale])
    payment = bolt.begin_paying()
    assert payment.total_cost.mana == ManaCost.parse("{3}{R}")
    scenario.auto_pay(payment, "bob")
    scenario.put_on_stack(bolt)
    scenario.resolve_top()
    assert whale.damage == 3


def test_the_same_spell_aimed_elsewhere_is_not_taxed():
    scenario = whale_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bolt = announce(scenario, "Lightning Bolt", username="bob")
    bolt.choose_targets([bears])
    assert bolt.total_cost.mana == ManaCost.parse("{R}")
    bolt.cancel()
    face = announce(scenario, "Lightning Bolt", username="bob")
    face.choose_targets(["alice"])
    assert face.total_cost.mana == ManaCost.parse("{R}")


def test_the_whales_own_controller_is_not_taxed():
    scenario = whale_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    whale = scenario.creature("Pursued Whale", "alice")
    bolt = announce(scenario, "Lightning Bolt", username="alice")
    bolt.choose_targets([whale])
    assert bolt.total_cost.mana == ManaCost.parse("{R}")


def test_each_whale_taxes_only_spells_that_target_it():
    scenario = whale_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bobs_bears = scenario.creature("Grizzly Bears", "bob")
    bolt = announce(scenario, "Lightning Bolt", username="alice")
    bolt.choose_targets([bobs_bears])
    assert bolt.total_cost.mana == ManaCost.parse("{R}"), "bob has no Whale"


def test_a_taxed_spell_the_caster_cannot_afford_is_refused():
    scenario = (
        Scenario()
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain", "Mountain"])
        .player("alice", battlefield=["Pursued Whale"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    whale = scenario.creature("Pursued Whale", "alice")
    bolt = announce(scenario, "Lightning Bolt", username="bob")
    bolt.choose_targets([whale])
    payment = bolt.begin_paying()
    with pytest.raises(ValueError, match="no combination of the available mana sources can pay"):
        payment.auto_tap(scenario.game.permanents_controlled_by("bob"))
