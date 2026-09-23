"""Scenario: "Whenever you attack with one or more creatures, ... that many"
(CR 508.3d) - the count a batched attack trigger's "that many" reads.

CR 508.3d: "An ability that reads 'Whenever [a player] attacks, . . .'
triggers if one or more creatures that player controls are declared as
attackers" - once for the declaration. Its "that many" is how many were
declared, which the declaration's own event never carried, so Screaming
Swarm's mill failed closed with a notice. Found by the behavioural sweep.

Rules verified with `mise run rules:find`: CR 508.3d, CR 701.17a (mill).
"""

import pytest

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


@pytest.mark.parametrize("attackers", [1, 3])
def test_screaming_swarm_mills_one_card_per_attacking_creature(attackers):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Screaming Swarm"] + ["Grizzly Bears"] * attackers)
        .player("bob", library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.choose_trigger_targets("Screaming Swarm", ["bob"])

    bears = [s for s in scenario.game.battlefield if s.name == "Grizzly Bears"]
    scenario.attack_with(*bears)
    scenario.pass_until_resolved()

    assert len(scenario.player("bob").graveyard) == attackers
    assert scenario.game.unmodeled_trigger_effect_notices == []
