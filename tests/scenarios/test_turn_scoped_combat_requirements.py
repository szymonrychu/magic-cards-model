"""Turn-long combat requirements a resolving spell or ability creates for a
group: Predatory Rampage's "Each creature your opponents control blocks this
turn if able." and Suicidal Charge's "Creatures your opponents control get
-1/-1 until end of turn. Those creatures attack this turn if able."

Every CR number here was read in full with `mise run rules:find` in the
session that wrote this file:

- **CR 508.1d** - an attack declaration must obey as many attack
  requirements as it can.
- **CR 509.1c** - the same for a block declaration and block requirements.
- **CR 611.2c** - an effect that does not modify characteristics modifies
  the rules of the game and can affect objects that were not there when it
  began (Predatory Rampage's ruling: every creature an opponent controls
  blocks, even one that entered later); "those creatures" are the set the
  -1/-1 locked on resolution (Suicidal Charge's ruling: a creature that
  comes under an opponent's control later does not have to attack).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _settle(scenario) -> None:
    for _ in range(20):
        scenario.state_based_actions()
        if scenario.game.stack_is_empty and not scenario.pending_triggers:
            return
        scenario.pass_until_resolved()
    raise AssertionError("the stack never emptied")


def _next_turn(scenario) -> None:
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
        _settle(scenario)


# -- Predatory Rampage ------------------------------------------------------


def _rampage_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Predatory Rampage"],
            battlefield=["Forest"] * 5 + ["Grizzly Bears"],
            library=["Forest"] * 10,
        )
        .player(
            "bob",
            hand=["Llanowar Elves"],
            battlefield=["Hill Giant"],
            library=["Forest"] * 10,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.creature("Grizzly Bears", "alice").summoning_sick = False
    scenario.cast_onto_stack("Predatory Rampage", *scenario.untapped_sources(*["Forest"] * 5))
    scenario.pass_until_resolved()
    _settle(scenario)
    return scenario


def test_rampage_refuses_a_declaration_where_an_able_opponents_creature_does_not_block():
    scenario = _rampage_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    assert scenario.game.characteristics_of(bears).power == 5
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)

    with pytest.raises(ValueError, match=r"CR 509\.1c"):
        scenario.no_blocks()

    scenario.block(bears, scenario.creature("Hill Giant", "bob"))
    assert scenario.blockers() == [scenario.creature("Hill Giant", "bob")]


def test_rampage_also_binds_a_creature_that_entered_after_it_resolved():
    scenario = _rampage_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.put_onto_battlefield("Llanowar Elves", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)

    with pytest.raises(ValueError, match=r"CR 509\.1c"):
        scenario.block(bears, scenario.creature("Hill Giant", "bob"))

    scenario.block(bears, scenario.creature("Hill Giant", "bob"), elves)
    assert {c.id for c in scenario.blockers()} == {
        scenario.creature("Hill Giant", "bob").id,
        elves.id,
    }


def test_rampage_does_not_force_the_casters_own_creatures_to_do_anything():
    scenario = _rampage_board()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with()
    assert scenario.attackers() == []


def test_rampage_requirement_is_gone_on_a_later_turn():
    scenario = _rampage_board()
    _next_turn(scenario)
    _next_turn(scenario)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)

    scenario.no_blocks()
    assert scenario.blockers() == []


# -- Suicidal Charge --------------------------------------------------------


def _charge_board():
    """Bob is the active player; Alice sacrifices Suicidal Charge in his
    precombat main phase."""
    scenario = (
        Scenario()
        .player(
            "bob",
            hand=["Grizzly Bears"],
            battlefield=["Hill Giant", "Llanowar Elves", "Craw Wurm"],
            library=["Forest"] * 10,
        )
        .player("alice", battlefield=["Suicidal Charge", "Memnite"], library=["Swamp"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for creature in scenario.game.permanents_controlled_by("bob"):
        creature.summoning_sick = False
    charge = scenario.find("Suicidal Charge", Zone.BATTLEFIELD, "alice")
    scenario.pass_priority("bob")
    scenario.activate(charge, index=0, username="alice")
    scenario.pass_until_resolved()
    _settle(scenario)
    return scenario


def test_charge_shrinks_and_kills_and_forces_the_survivors_to_attack():
    scenario = _charge_board()
    giant = scenario.creature("Hill Giant", "bob")
    wurm = scenario.creature("Craw Wurm", "bob")
    assert scenario.find("Llanowar Elves", Zone.GRAVEYARD, "bob") is not None
    assert scenario.game.characteristics_of(giant).power == 2
    scenario.start_at(Step.DECLARE_ATTACKERS)

    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with(giant)

    scenario.attack_with(giant, wurm)
    assert {c.id for c in scenario.attackers()} == {giant.id, wurm.id}


def test_charge_does_not_bind_its_controllers_own_creatures():
    scenario = _charge_board()
    memnite = scenario.creature("Memnite", "alice")
    assert scenario.game.characteristics_of(memnite).toughness == 1


def test_charge_does_not_bind_a_creature_that_arrived_after_it_resolved():
    """Suicidal Charge's ruling: only the creatures the -1/-1 affected."""
    scenario = _charge_board()
    late = scenario.put_onto_battlefield("Grizzly Bears", "bob")
    late.summoning_sick = False
    giant = scenario.creature("Hill Giant", "bob")
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)

    scenario.attack_with(giant, wurm)
    assert late not in scenario.attackers()


def test_charge_requirement_is_gone_next_turn():
    scenario = _charge_board()
    _next_turn(scenario)
    _next_turn(scenario)
    scenario.start_at(Step.DECLARE_ATTACKERS)

    scenario.attack_with()
    assert scenario.attackers() == []
