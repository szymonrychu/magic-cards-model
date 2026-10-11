"""Scenario: group pumps whose X is counted from the game and re-read on every
computation (CR 613.4c, CR 613.5, CR 611.3a) - "This creature and enchanted
creature each get +X/+X, where X is the number of creature cards in all
graveyards." (Nighthowler) and "Other creatures you control get +X/+0, where X
is your speed." (Samut, the Driving Force; CR 702.179f: no speed reads as 0).
"""

from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def pt(scenario, state):
    chars = scenario.game.characteristics_of(state)
    return chars.power, chars.toughness


def test_nighthowler_counts_creature_cards_in_all_graveyards():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Nighthowler"], graveyard=["Grizzly Bears", "Lightning Bolt"])
        .player("bob", graveyard=["Grizzly Bears", "Giant Spider"])
        .build()
    )
    howler = scenario.creature("Nighthowler")
    assert pt(scenario, howler) == (3, 3)


def test_nighthowler_follows_the_graveyards():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Nighthowler", "Grizzly Bears"], graveyard=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    howler = scenario.creature("Nighthowler")
    assert pt(scenario, howler) == (1, 1)
    scenario.game.put_into_graveyard(scenario.creature("Grizzly Bears"))
    assert pt(scenario, howler) == (2, 2)


def test_samut_pumps_other_creatures_by_speed():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Samut, the Driving Force", "Grizzly Bears"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.game.player("alice").speed = 3
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")
    samut = scenario.creature("Samut, the Driving Force")
    assert pt(scenario, mine) == (5, 2)
    assert pt(scenario, theirs) == (2, 2)
    base = (int(samut.card.power), int(samut.card.toughness))
    assert pt(scenario, samut) == base


def test_no_speed_pumps_nothing():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Samut, the Driving Force", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    assert scenario.game.player("alice").speed is None
    assert pt(scenario, scenario.creature("Grizzly Bears")) == (2, 2)
