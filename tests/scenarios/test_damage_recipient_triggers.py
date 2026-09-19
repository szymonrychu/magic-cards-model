"""Trigger conditions read off the *recipient* of damage, not the dealer
(CR 120.1, 120.2a): Master of Barbs' "Whenever one or more opponents are
dealt noncombat damage, ...", Massacre Girl, Most Wanted's singular "Whenever
an opponent is dealt noncombat damage, ...", Fblthp, Impossibly Lost's "When
one or more of your opponents are dealt combat damage during your turn, ...",
and Hexhaven Invigorator's self-referential "Whenever this creature is dealt
damage, ...".

`condition_matches`'s DEALS_DAMAGE branch used to read only the dealing end
(`subject_id`/`subject_controller`) - a passive-voice "is/are dealt" clause,
naming the *target*, matched nothing. `GameEvent.target_id`/`target_
controller`/`target_types` are the new recipient-side fields `Game.
deal_damage` now populates alongside the existing dealer-side ones.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def test_master_of_barbs_pumps_the_team_when_an_opponent_takes_noncombat_damage():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Master of Barbs", "Grizzly Bears"], life=20)
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")

    scenario.game.deal_damage(bob, 3)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Master of Barbs's triggered ability"]


def test_master_of_barbs_does_not_fire_for_combat_damage():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Master of Barbs"], life=20)
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.COMBAT_DAMAGE)
    bob = scenario.player("bob")

    scenario.game._dealing_combat_damage = True
    try:
        scenario.game.deal_damage(bob, 3)
    finally:
        scenario.game._dealing_combat_damage = False
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_master_of_barbs_does_not_fire_for_damage_to_its_own_controller():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Master of Barbs"], life=20)
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")

    scenario.game.deal_damage(alice, 3)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_wildfire_elemental_off_pool_proof_pumps_the_team_too():
    """Off-pool generality proof: Wildfire Elemental prints the identical
    "Whenever an opponent is dealt noncombat damage" condition, singular
    rather than Master of Barbs' "one or more opponents"."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Wildfire Elemental"], life=20)
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")

    scenario.game.deal_damage(bob, 1)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Wildfire Elemental's triggered ability"]


def test_hexhaven_invigorator_triggers_when_it_is_dealt_damage_itself():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hexhaven Invigorator"], library=["Mountain", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    invigorator = scenario.creature("Hexhaven Invigorator", "alice")

    scenario.game.deal_damage(invigorator, 2)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Hexhaven Invigorator's triggered ability"]


def test_hexhaven_invigorator_does_not_trigger_for_another_creature_being_damaged():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hexhaven Invigorator", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.deal_damage(bears, 2)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_bellowing_aegisaur_off_pool_proof_triggers_when_damaged():
    """Off-pool generality proof: Bellowing Aegisaur prints the identical
    "Whenever this creature is dealt damage" condition with a differently
    shaped effect (a team-wide counter grant, not a search)."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Bellowing Aegisaur", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    aegisaur = scenario.creature("Bellowing Aegisaur", "alice")

    scenario.game.deal_damage(aegisaur, 1)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Bellowing Aegisaur's triggered ability"]


def test_fblthp_draws_two_when_an_opponent_takes_combat_damage_on_alices_turn():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Fblthp, Impossibly Lost"], library=["Mountain", "Forest"])
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.COMBAT_DAMAGE)
    bob = scenario.player("bob")

    scenario.game._dealing_combat_damage = True
    try:
        scenario.game.deal_damage(bob, 3)
    finally:
        scenario.game._dealing_combat_damage = False
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Fblthp, Impossibly Lost's triggered ability"]


def test_fblthp_does_not_fire_for_combat_damage_on_the_opponents_own_turn():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Fblthp, Impossibly Lost"], library=["Mountain", "Forest"])
        .player("bob", battlefield=["Grizzly Bears"], life=20)
        .build()
    )
    scenario.start_at(Step.CLEANUP)
    scenario.advance()  # into bob's turn
    bob = scenario.player("bob")

    scenario.game._dealing_combat_damage = True
    try:
        scenario.game.deal_damage(bob, 2)
    finally:
        scenario.game._dealing_combat_damage = False
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
