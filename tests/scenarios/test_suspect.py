"""Scenario: Suspect (CR 701.60) - the keyword action, the suspected
designation, and its menace and "can't block".

Rules read whole with `mise run rules:find` in the session that wrote this:

- **CR 701.60a** - "Certain spells and abilities instruct a player to
  suspect a creature. That creature becomes suspected until it leaves the
  battlefield or until a spell or ability causes it to no longer be
  suspected."
- **CR 701.60b** - "Suspected is a designation a permanent can have. Only
  permanents can have the suspected designation. Suspected is neither an
  ability nor part of the permanent's copiable values."
- **CR 701.60c** - "A suspected permanent has menace and 'This creature
  can't block' for as long as it's suspected."
- **CR 702.111b** - menace: "can't be blocked except by two or more
  creatures."
- **CR 613.1f** - layer 6, abilities.
- **CR 603.4** / **CR 608.2a** - the "if it's not suspected" clause.

Barbed Servitor and Person of Interest ("When this creature enters, suspect
it"), Convenient Target ("suspect enchanted creature"), Clandestine Meddler
("suspect up to one other target creature you control") and Absolving
Lammasu ("all suspected creatures are no longer suspected") are the
printings; Rubblebelt Braggart and Frantic Scapegoat the conditions.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(alice=(), *, bob=(), hand=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=list(alice), hand=list(hand), library=["Plains"] * 5)
        .player("bob", battlefield=list(bob), library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _enter(scenario, name):
    permanent = scenario.put_onto_battlefield(name, "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    return permanent


def test_barbed_servitor_suspects_itself_as_it_enters():
    scenario = _board(hand=["Barbed Servitor"])
    servitor = _enter(scenario, "Barbed Servitor")
    assert servitor.suspected


def test_a_suspected_creature_has_menace_and_cant_block():
    scenario = _board(hand=["Barbed Servitor"], bob=["Grizzly Bears"])
    servitor = _enter(scenario, "Barbed Servitor")
    assert has_keyword(servitor, "menace", scenario.game)
    abilities = scenario.game.characteristics_of(servitor).abilities
    assert "This creature can't block." in abilities


def test_a_suspected_creature_cannot_block():
    scenario = _board(["Grizzly Bears"], bob=["Grizzly Bears"])
    blocker = scenario.creature("Grizzly Bears", "bob")
    blocker.suspected = True
    scenario.start_at(Step.DECLARE_ATTACKERS)
    attacker = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(attacker)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    assert scenario.game.why_cannot_block(blocker, attacker) is not None


def test_a_suspected_attacker_cannot_be_blocked_by_one_creature():
    """CR 702.111b's menace, granted by CR 701.60c."""
    scenario = _board(["Grizzly Bears"], bob=["Memnite", "Ornithopter"])
    attacker = scenario.creature("Grizzly Bears", "alice")
    attacker.suspected = True
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacker)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    with pytest.raises(ValueError):
        scenario.block(attacker, scenario.creature("Memnite", "bob"))


def test_the_designation_and_its_abilities_end_as_it_leaves():
    scenario = _board(hand=["Barbed Servitor"])
    servitor = _enter(scenario, "Barbed Servitor")
    scenario.game.exile_permanent(servitor)
    assert not servitor.suspected


def test_person_of_interest_second_printing():
    scenario = _board(hand=["Person of Interest"])
    person = _enter(scenario, "Person of Interest")
    assert person.suspected


def test_convenient_target_suspects_the_enchanted_creature():
    scenario = _board(["Convenient Target"], bob=["Grizzly Bears"])
    aura = scenario.find("Convenient Target", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "bob")
    aura.attach_to(bears)
    from magic_cards_model.machines.triggers import GameEvent, TriggerEvent

    scenario.game.emit(
        GameEvent(event=TriggerEvent.ENTERS_THE_BATTLEFIELD, subject_id=aura.id, player="alice")
    )
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert bears.suspected


def test_clandestine_meddler_suspects_another_target_creature_you_control():
    scenario = _board(["Grizzly Bears"], hand=["Clandestine Meddler"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Clandestine Meddler", [bears])
    meddler = _enter(scenario, "Clandestine Meddler")
    assert bears.suspected
    assert not meddler.suspected


def test_absolving_lammasu_ends_every_suspicion():
    scenario = _board(["Grizzly Bears"], bob=["Memnite"], hand=["Absolving Lammasu"])
    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "bob")
    bears.suspected = True
    memnite.suspected = True
    _enter(scenario, "Absolving Lammasu")
    assert not bears.suspected
    assert not memnite.suspected
    assert not has_keyword(bears, "menace", scenario.game)


# -- the conditions ---------------------------------------------------------------


def test_rubblebelt_braggart_may_suspect_itself_when_not_suspected():
    scenario = _board(["Rubblebelt Braggart"])
    braggart = scenario.creature("Rubblebelt Braggart", "alice")
    scenario.will_take_the_may(True)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(braggart)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Rubblebelt Braggart's triggered ability"]
    scenario.pass_until_resolved()
    assert braggart.suspected


def test_rubblebelt_braggart_already_suspected_does_not_trigger():
    scenario = _board(["Rubblebelt Braggart"])
    braggart = scenario.creature("Rubblebelt Braggart", "alice")
    braggart.suspected = True
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(braggart)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []


def test_frantic_scapegoat_suspects_itself_and_triggers_while_suspected():
    scenario = _board(hand=["Frantic Scapegoat", "Grizzly Bears"])
    scapegoat = _enter(scenario, "Frantic Scapegoat")
    assert scapegoat.suspected
    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    scenario.game.put_triggers_on_stack()
    assert "Frantic Scapegoat's triggered ability" in scenario.stack_names()


def test_frantic_scapegoat_not_suspected_does_not_trigger():
    scenario = _board(["Frantic Scapegoat"], hand=["Grizzly Bears"])
    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    scenario.game.put_triggers_on_stack()
    assert "Frantic Scapegoat's triggered ability" not in scenario.stack_names()
