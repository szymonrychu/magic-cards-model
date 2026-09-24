"""Scenario: "you control target player during that player's next turn" as a
printed effect (CR 723).

The subsystem - who is controlled, from when to when, who decides - lives on
`TurnMachine`/`Game` and is proven in `test_controlling_another_player.py`.
This file proves the *reader*: the sentence, on any card, reaches it.

- **Construct a Cosmic Cube** (msh, listed): "When the seventh plan counter is
  put on this enchantment, sacrifice it. When you do, you control target
  opponent during their next turn. (You see all cards that player could see
  and make all decisions for them.)" - the effect as a CR 603.12 reflexive
  ability, "target opponent", "their".
- **Mindslaver** (off-msh proof, Modern legal): "{4}, {T}, Sacrifice
  Mindslaver: You control target player during that player's next turn." - an
  activated ability, "target player" (yourself included, CR 723.9), "that
  player's".

Rules, each read with `mise run rules:find` in the session that wrote this
file: CR 723.1 (the next turn the affected player actually takes, the whole
turn), CR 723.1a (a later effect overwrites), CR 723.3 (still the active
player; objects keep their controllers), CR 723.5 (the controller makes the
controlled player's decisions), CR 723.9 (control of yourself), CR 115.1,
CR 602.2, CR 603.12, CR 121.2.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def next_turn(scenario) -> None:
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.advance()


def _mindslaver_board():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Mindslaver", "Island", "Island", "Island", "Island"],
            library=["Island"] * 4,
        )
        .player("bob", battlefield=["Grizzly Bears", "Forest"], library=["Forest"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _activate_mindslaver(scenario, target: str) -> None:
    mindslaver = scenario.find("Mindslaver", Zone.BATTLEFIELD, "alice")
    scenario.activate(mindslaver, auto=True, targets=[target], sacrificing=[mindslaver])
    scenario.pass_until_resolved()


def test_mindslaver_changes_nothing_on_the_turn_it_resolves():
    """CR 723.1: the effect waits for bob's next turn."""
    scenario = _mindslaver_board()

    _activate_mindslaver(scenario, "bob")

    assert scenario.find("Mindslaver", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
    assert scenario.game.controller_of_player("bob") == "bob"


def test_mindslaver_gives_alice_bobs_next_turn():
    scenario = _mindslaver_board()
    _activate_mindslaver(scenario, "bob")

    next_turn(scenario)

    assert scenario.turn.active_player == "bob"  # CR 723.3
    assert scenario.game.controller_of_player("bob") == "alice"
    assert scenario.game.priority.decider == "alice"
    with pytest.raises(ValueError, match="alice is making bob's decisions"):
        scenario.pass_priority("bob")


def test_bobs_permanents_stay_bobs_while_alice_controls_him():
    """CR 723.3: only control of the player changes."""
    scenario = _mindslaver_board()
    _activate_mindslaver(scenario, "bob")
    next_turn(scenario)

    bears = scenario.creature("Grizzly Bears", "bob")
    assert scenario.game.controller_of(bears).username == "bob"


def test_the_control_ends_as_the_following_turn_begins():
    scenario = _mindslaver_board()
    _activate_mindslaver(scenario, "bob")
    next_turn(scenario)

    next_turn(scenario)

    assert scenario.turn.active_player == "alice"
    assert scenario.game.controller_of_player("bob") == "bob"


def test_mindslaver_on_yourself_changes_nothing():
    """ "Target player" includes its controller; CR 723.9 then has alice go on
    deciding for herself."""
    scenario = _mindslaver_board()
    _activate_mindslaver(scenario, "alice")

    next_turn(scenario)
    next_turn(scenario)

    assert scenario.turn.active_player == "alice"
    assert scenario.game.controller_of_player("alice") == "alice"


def test_a_target_gone_by_resolution_is_not_controlled():
    """CR 608.2b: bob conceded in response; there is nobody to control."""
    scenario = _mindslaver_board()
    mindslaver = scenario.find("Mindslaver", Zone.BATTLEFIELD, "alice")
    scenario.activate(mindslaver, auto=True, targets=["bob"], sacrificing=[mindslaver])
    scenario.game.concede("bob")

    assert scenario.game.is_over


# -- Construct a Cosmic Cube -------------------------------------------------


def _cube_board():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Construct a Cosmic Cube"], library=["Swamp"] * 6)
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _resolve_everything(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def test_the_second_draw_makes_a_villain_and_adds_a_plan_counter():
    scenario = _cube_board()
    cube = scenario.find("Construct a Cosmic Cube", Zone.BATTLEFIELD, "alice")

    scenario.game.draw_cards("alice", 2)
    _resolve_everything(scenario)

    assert cube.counters["plan"] == 1
    villains = [p for p in scenario.game.battlefield if getattr(p, "token", False)]
    assert len(villains) == 1
    chars = scenario.game.computed_board().of(villains[0])
    assert "Villain" in chars.subtypes
    assert "Menace" in chars.abilities


def test_the_seventh_counter_gives_alice_bobs_next_turn():
    scenario = _cube_board()
    cube = scenario.find("Construct a Cosmic Cube", Zone.BATTLEFIELD, "alice")
    scenario.game.add_counters(cube, "plan", 6)
    scenario.will_choose_targets("bob")

    scenario.game.draw_cards("alice", 2)
    _resolve_everything(scenario)

    assert cube.zone is Zone.GRAVEYARD
    assert scenario.game.controller_of_player("bob") == "bob"
    next_turn(scenario)
    assert scenario.game.controller_of_player("bob") == "alice"


def test_the_cube_cannot_target_its_own_controller():
    """ "Target opponent" - alice is not a legal target (CR 115.1)."""
    scenario = _cube_board()
    cube = scenario.find("Construct a Cosmic Cube", Zone.BATTLEFIELD, "alice")
    scenario.game.add_counters(cube, "plan", 7)
    scenario.will_choose_targets("alice")

    with pytest.raises(ValueError):
        _resolve_everything(scenario)


def test_a_later_cube_overwrites_an_earlier_mindslaver():
    """CR 723.1a: carol's Mindslaver, then alice's Cube, both on bob - the
    last one created works."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Construct a Cosmic Cube"], library=["Swamp"] * 6)
        .player("bob", library=["Forest"] * 6)
        .player(
            "carol",
            battlefield=["Mindslaver", "Island", "Island", "Island", "Island"],
            library=["Island"] * 6,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mindslaver = scenario.find("Mindslaver", Zone.BATTLEFIELD, "carol")
    scenario.pass_priority("alice")
    scenario.pass_priority("bob")
    scenario.activate(
        mindslaver, auto=True, username="carol", targets=["bob"], sacrificing=[mindslaver]
    )
    scenario.pass_until_resolved()
    cube = scenario.find("Construct a Cosmic Cube", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_targets("bob")

    scenario.game.add_counters(cube, "plan", 7)
    _resolve_everything(scenario)
    next_turn(scenario)

    assert scenario.turn.active_player == "bob"
    assert scenario.game.controller_of_player("bob") == "alice"
