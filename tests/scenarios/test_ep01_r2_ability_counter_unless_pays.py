"""An activated ability that counters "unless its controller pays {N}".

Malevolent Hermit: "{U}, Sacrifice this creature: Counter target noncreature
spell unless its controller pays {3}." CR 118.12a: the question goes to the
targeted spell's controller; CR 701.6a counters it if they do not pay. The
"noncreature" restriction is CR 601.2c's target legality (CR 115.1).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(bob_lands: int):  # the caster's (alice's) Mountains
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Raging Goblin"],
            battlefield=["Mountain"] * bob_lands,
            library=["Island"] * 5,
        )
        .player("bob", battlefield=["Malevolent Hermit", "Island"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _bob_casts_bolt(scenario):
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")[:1]
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])
    scenario.pass_priority("alice")
    return scenario.find("Lightning Bolt", Zone.STACK, "alice")


def _hermit_counters(scenario, bolt):
    hermit = scenario.find("Malevolent Hermit", Zone.BATTLEFIELD, "bob")
    scenario.activate(
        hermit,
        *scenario.untapped_sources("Island", username="bob"),
        username="bob",
        sacrificing=[hermit],
        targets=[bolt],
    )
    scenario.resolve_top()


def test_the_spell_is_countered_when_its_controller_cannot_pay():
    scenario = _board(bob_lands=1)
    bolt = _bob_casts_bolt(scenario)
    _hermit_counters(scenario, bolt)
    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 20


def test_the_spell_survives_when_its_controller_pays():
    scenario = _board(bob_lands=4)
    bolt = _bob_casts_bolt(scenario)
    scenario.will_pay_the_mana_cost(True, username="alice")
    _hermit_counters(scenario, bolt)
    assert bolt.zone is Zone.STACK


def test_a_creature_spell_is_not_a_legal_target():
    scenario = _board(bob_lands=1)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")[:1]
    scenario.cast_onto_stack("Raging Goblin", mountain, username="alice")
    scenario.pass_priority("alice")
    goblin = scenario.find("Raging Goblin", Zone.STACK, "alice")
    hermit = scenario.find("Malevolent Hermit", Zone.BATTLEFIELD, "bob")
    with pytest.raises(ValueError):
        scenario.activate(
            hermit,
            *scenario.untapped_sources("Island", username="bob"),
            username="bob",
            sacrificing=[hermit],
            targets=[goblin],
        )
