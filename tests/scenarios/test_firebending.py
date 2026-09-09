"""Firebending: CR 702.189a, crediting the sweep for work already done.

`machines/keywords._firebending_ability` (the triggered-ability expansion)
and `machines/effects._parse_firebending_add_mana` (the "add N {R}" effect)
both already existed and are proved end to end in
`tests/scenarios/judge/test_judge_mana_abilities.py`. The only real gap was
`machines/keywords.executes()` never crediting the keyword at all. Proved
here on Boiling Rock Rioter - "Firebending 1", a fixed count rather than
Firebending Student's own self-defined X - outside the deck pool and outside
this wave's brief.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.card import Color
from tests.scenarios.harness import Scenario


def test_boiling_rock_rioter_adds_mana_when_it_attacks():
    """Boiling Rock Rioter: "Firebending 1 (Whenever this creature attacks,
    add {R}. This mana lasts until end of combat.)"
    """
    scenario = Scenario().player("alice", battlefield=["Boiling Rock Rioter"]).player("bob").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    rioter = scenario.creature("Boiling Rock Rioter", "alice")

    scenario.attack_with(rioter)
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    assert scenario.player("alice").mana_pool.floating.get(Color.RED) == 1
