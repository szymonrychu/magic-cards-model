"""Scenario: a group named by card name - "Equipment named Sword of Kaldra,
Shield of Kaldra, and Helm of Kaldra have indestructible." (Shield of Kaldra,
CR 201.2, CR 613.1f).
"""

from magic_cards_model.machines.combat import has_keyword
from tests.scenarios.harness import Scenario


def board(alice, bob=()):
    return (
        Scenario()
        .player("alice", battlefield=list(alice))
        .player("bob", battlefield=list(bob))
        .build()
    )


def find(scenario, name, username="alice"):
    return next(
        c for c in scenario.game.battlefield if c.name == name and c.controller == username
    )


def test_the_named_equipment_is_indestructible_including_itself():
    scenario = board(["Shield of Kaldra"])
    assert has_keyword(find(scenario, "Shield of Kaldra"), "indestructible", scenario.game)


def test_unnamed_equipment_is_not():
    scenario = board(["Shield of Kaldra", "Bonesplitter"])
    assert not has_keyword(find(scenario, "Bonesplitter"), "indestructible", scenario.game)


def test_it_reaches_the_opponents_named_equipment_too():
    """The sentence names no controller."""
    scenario = board(["Shield of Kaldra"], ["Shield of Kaldra"])
    assert has_keyword(find(scenario, "Shield of Kaldra", "bob"), "indestructible", scenario.game)
