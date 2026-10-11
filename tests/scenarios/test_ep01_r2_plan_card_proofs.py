"""Scenario proofs for the plan cards whose family reader is exercised by other
files but whose own printing needs a game played with it: the four creatures
that "may assign combat damage as though it weren't blocked" (Lone Wolf,
Spinebiter, Thorn Elemental, Tornado Elemental), the three indestructible
granters (Terra Eternal, That Which Was Taken, The Walls of Ba Sing Se) and
Gold-Forged Thopteryx's ward grant.

CR 510.1b/510.1c (an unblocked creature assigns damage to the player it
attacks; a blocked one to its blockers), CR 702.12a (indestructible), CR 611.3a
(a static ability's group is re-asked every computation), CR 702.21a (ward).
"""

import pytest

from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def attack_into_a_blocker(name):
    scenario = (
        Scenario()
        .player("alice", battlefield=[name])
        .player("bob", battlefield=["Grizzly Bears"], life=20)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    attacker = scenario.creature(name, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(attacker)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.block(attacker, bears)
    return scenario, attacker, bears


@pytest.mark.parametrize(
    "name,power,infect",
    [
        ("Lone Wolf", 2, False),
        ("Spinebiter", 3, True),
        ("Thorn Elemental", 7, False),
        ("Tornado Elemental", 6, False),
    ],
)
def test_the_creature_may_send_all_its_damage_past_its_blocker(name, power, infect):
    scenario, attacker, bears = attack_into_a_blocker(name)
    scenario.will_take_the_may(True, username="alice", source=name)

    scenario.combat_damage()

    bob = scenario.player("bob")
    if infect:
        assert bob.poison == power and bob.life == 20
    else:
        assert bob.life == 20 - power
    assert bears.zone is Zone.BATTLEFIELD
    assert bears.damage == 0 and bears.counter_count("-1/-1") == 0


@pytest.mark.parametrize("name", ["Lone Wolf", "Spinebiter", "Thorn Elemental", "Tornado Elemental"])
def test_declining_assigns_to_the_blocker_as_usual(name):
    scenario, attacker, bears = attack_into_a_blocker(name)
    scenario.will_take_the_may(False, username="alice", source=name)

    scenario.combat_damage()

    bob = scenario.player("bob")
    assert bob.life == 20 and bob.poison == 0
    assert bears.zone is Zone.GRAVEYARD


def test_tornado_elemental_deals_six_to_each_creature_with_flying_when_it_enters():
    scenario = (
        Scenario()
        .player("alice", hand=["Tornado Elemental"], battlefield=["Grizzly Bears", "Wind Drake"])
        .player("bob", battlefield=["Wind Drake", "Savannah Lions"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Tornado Elemental", "alice")
    scenario.pass_until_resolved()

    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD
    assert scenario.creature("Savannah Lions", "bob").zone is Zone.BATTLEFIELD
    assert [p.name for p in scenario.game.battlefield if p.name == "Wind Drake"] == []


def test_terra_eternal_makes_every_land_indestructible():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Terra Eternal", "Forest"])
        .player("bob", battlefield=["Island", "Grizzly Bears"])
        .build()
    )
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    island = scenario.find("Island", Zone.BATTLEFIELD, "bob")
    bears = scenario.creature("Grizzly Bears", "bob")

    assert has_keyword(forest, "indestructible", scenario.game)
    assert has_keyword(island, "indestructible", scenario.game)
    assert not has_keyword(bears, "indestructible", scenario.game)


def test_walls_of_ba_sing_se_makes_other_permanents_you_control_indestructible():
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Walls of Ba Sing Se", "Grizzly Bears", "Forest"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    walls = scenario.find("The Walls of Ba Sing Se", Zone.BATTLEFIELD, "alice")

    assert not has_keyword(walls, "indestructible", scenario.game)
    assert has_keyword(scenario.creature("Grizzly Bears", "alice"), "indestructible", scenario.game)
    assert has_keyword(scenario.find("Forest", Zone.BATTLEFIELD, "alice"), "indestructible", scenario.game)
    assert not has_keyword(scenario.creature("Grizzly Bears", "bob"), "indestructible", scenario.game)


def test_that_which_was_taken_gives_indestructible_to_a_permanent_with_a_divinity_counter():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["That Which Was Taken", "Grizzly Bears", "Mountain", "Mountain", "Mountain", "Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    taken = scenario.find("That Which Was Taken", Zone.BATTLEFIELD, "alice")
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")
    assert not has_keyword(mine, "indestructible", scenario.game)

    scenario.activate(
        taken, *scenario.untapped_sources(*["Mountain"] * 4), index=0, username="alice", targets=[mine]
    )
    scenario.resolve_top()

    assert mine.counter_count("divinity") == 1
    assert has_keyword(mine, "indestructible", scenario.game)
    assert not has_keyword(theirs, "indestructible", scenario.game)


def test_gold_forged_thopteryx_gives_your_legendary_permanents_ward_two():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Gold-Forged Thopteryx", "The Walls of Ba Sing Se", "Grizzly Bears"])
        .player("bob", battlefield=["The Walls of Ba Sing Se"])
        .build()
    )

    def lines(name, owner):
        return scenario.game.characteristics_of(scenario.find(name, Zone.BATTLEFIELD, owner)).abilities

    assert "Ward {2}" in lines("The Walls of Ba Sing Se", "alice")
    assert "Ward {2}" not in lines("Grizzly Bears", "alice")
    assert "Ward {2}" not in lines("The Walls of Ba Sing Se", "bob")
    assert "Ward {2}" not in lines("Gold-Forged Thopteryx", "alice")
