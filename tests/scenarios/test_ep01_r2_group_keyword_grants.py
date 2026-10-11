"""Scenario: a keyword granted to a group of permanents - "All Rats have
fear." (Marrow-Gnawer), "Artifacts you control have indestructible."
(Darksteel Forge), "Legendary Humans you control have indestructible."
(General's Enforcer), "Other permanents you control have indestructible."
(Avacyn, Angel of Hope), "Sliver creatures you control have indestructible."
(Sliver Hivelord).

CR 613.1f: a keyword-granting effect is a layer 6 effect, and CR 611.3a: it
applies at any given moment to whatever its text indicates. The group word
decides the scope - "All" reaches both players, "you control" only the
source's controller - and the effect ends with its source (CR 604.2).
"""

from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board(*alice, bob=()):
    return (
        Scenario()
        .player("alice", battlefield=list(alice))
        .player("bob", battlefield=list(bob))
        .build()
    )


def keywords(scenario, state):
    return {line.lower() for line in scenario.game.characteristics_of(state).abilities}


def test_all_rats_have_fear_for_both_players():
    scenario = board("Marrow-Gnawer", "Grizzly Bears", bob=["Marrow-Gnawer"])
    ours = scenario.creature("Marrow-Gnawer")
    bears = scenario.creature("Grizzly Bears")

    assert has_keyword(ours, "fear", scenario.game)
    assert not has_keyword(bears, "fear", scenario.game)
    assert has_keyword(scenario.creature("Marrow-Gnawer", "bob"), "fear", scenario.game)


def test_all_rats_includes_the_source_itself():
    scenario = board("Marrow-Gnawer")
    gnawer = scenario.creature("Marrow-Gnawer")

    assert has_keyword(gnawer, "fear", scenario.game)


def test_the_grant_ends_when_the_source_leaves():
    """CR 604.2: the opponent's Rat keeps fear only through its own grant."""
    scenario = board("Marrow-Gnawer", bob=["Marrow-Gnawer"])
    ours = scenario.creature("Marrow-Gnawer")
    theirs = scenario.creature("Marrow-Gnawer", "bob")
    scenario.game.put_into_graveyard(ours)

    assert ours.zone is Zone.GRAVEYARD
    assert has_keyword(theirs, "fear", scenario.game), "its own grant"
    scenario.game.put_into_graveyard(theirs)
    assert theirs.zone is Zone.GRAVEYARD


def test_artifacts_you_control_are_indestructible_and_the_opponents_are_not():
    scenario = board("Darksteel Forge", "Grizzly Bears", bob=["Sol Ring"])
    forge = scenario.find("Darksteel Forge", Zone.BATTLEFIELD)
    theirs = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    bears = scenario.creature("Grizzly Bears")

    assert "indestructible" in keywords(scenario, forge)
    assert "indestructible" not in keywords(scenario, theirs)
    assert "indestructible" not in keywords(scenario, bears)


def test_legendary_humans_you_control_only():
    """Kalain is a legendary Human, the Enforcer a nonlegendary Human, and
    Avacyn's player has no Enforcer here: only the legendary Human gets it."""
    scenario = board("General's Enforcer", "Kalain, Reclusive Painter", "Grizzly Bears")
    enforcer = scenario.creature("General's Enforcer")
    kalain = scenario.creature("Kalain, Reclusive Painter")
    bears = scenario.creature("Grizzly Bears")

    assert "indestructible" in keywords(scenario, kalain)
    assert "indestructible" not in keywords(scenario, enforcer), "nonlegendary Human"
    assert "indestructible" not in keywords(scenario, bears)


def test_other_permanents_you_control_reaches_noncreatures_but_not_the_source():
    scenario = board("Avacyn, Angel of Hope", "Forest", "Grizzly Bears", bob=["Grizzly Bears"])
    forest = scenario.find("Forest", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears")
    theirs = scenario.creature("Grizzly Bears", "bob")

    assert "indestructible" in keywords(scenario, forest)
    assert "indestructible" in keywords(scenario, bears)
    assert "indestructible" not in keywords(scenario, theirs)


def test_a_legend_that_starts_with_a_creature_type_still_reads_the_type():
    """Sliver Hivelord's bare first word "Sliver" is the legend's own short
    name (CR 201.5c) but here names the creature type (CR 205.3m): another
    Sliver you control is in the group, a Bear is not."""
    scenario = board("Sliver Hivelord", "Muscle Sliver", "Grizzly Bears")
    sliver = scenario.creature("Muscle Sliver")
    bears = scenario.creature("Grizzly Bears")
    hivelord = scenario.creature("Sliver Hivelord")

    assert "indestructible" in keywords(scenario, sliver)
    assert "indestructible" in keywords(scenario, hivelord)
    assert "indestructible" not in keywords(scenario, bears)
