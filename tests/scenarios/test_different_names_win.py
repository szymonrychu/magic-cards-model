"""Scenario: "you control N or more <quality> with different names" wins.

Liliana's Contract - "At the beginning of your upkeep, if you control four
or more Demons with different names, you win the game." The condition is
CR 603.4's intervening *if*: checked when the trigger event occurs and again
as the ability resolves (CR 608.2a). The effect left behind is the bare
statement "you win the game." (CR 104.2b: "An effect may state that a player
wins the game."), read on its own by `machines/effects.
_parse_if_condition_you_win_the_game_clause` with no condition of its own.

The condition is read by `machines/conditions/board.py`'s general
"<who> control(s) <amount> <quality> with different names" grouping, not a
Demon-shaped reader. CR 201.2b: "Those objects have different names only if
each of them has at least one name and no two objects in that group have a
name in common." - so two Demons sharing a name (two tokens named "Demon
Token", or two copies of one card) count as one name.

Maze's End is the second printing with the same count - "If you control ten
or more Gates with different names, you win the game." - an activated
ability's resolving "If ..., you win the game." rather than an intervening
*if*, over Gates rather than Demons.

Oracle text verified against the printings pool (all Modern-legal):
Liliana's Contract; Archfiend of Ifnir, Miasma Demon, Rafter Demon,
Curse-Marred Demon (Demons); Maze's End and the ten Guildgates (Gates).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.token import TokenDefinition, create_tokens

from .harness import Scenario

CONTRACT = "Liliana's Contract"
DEMONS = ["Archfiend of Ifnir", "Miasma Demon", "Rafter Demon", "Curse-Marred Demon"]
DEMON_TOKEN = TokenDefinition(
    subtypes=("Demon",), colors=(Color.BLACK,), power=5, toughness=5, keywords=("Flying",)
)


def _board(battlefield: list[str]):
    return (
        Scenario()
        .player("alice", library=["Swamp", "Swamp"], battlefield=[CONTRACT, *battlefield])
        .player("bob", library=["Plains"])
        .build()
    )


def _to_upkeep(scenario) -> None:
    scenario.advance()  # untap -> upkeep
    assert scenario.step is Step.UPKEEP


def test_four_demons_with_different_names_win_at_upkeep():
    scenario = _board(DEMONS)
    _to_upkeep(scenario)
    assert any(CONTRACT in name for name in scenario.stack_names())

    scenario.pass_until_resolved()

    assert scenario.game.winner == "alice"


def test_three_demons_with_different_names_do_not_trigger():
    scenario = _board(DEMONS[:3])
    _to_upkeep(scenario)

    assert not any(CONTRACT in name for name in scenario.stack_names())
    assert scenario.game.winner is None


def test_four_demons_sharing_names_are_fewer_than_four_different_names():
    """CR 201.2b: two Demon tokens share their name - four Demons, three names."""
    scenario = _board(DEMONS[:2])
    create_tokens(scenario.game, DEMON_TOKEN, "alice", count=2)
    scenario.game.pending_triggers.clear()
    demons = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if "Demon" in scenario.game.computed_board().of(state).subtypes
    ]
    assert len(demons) == 4
    _to_upkeep(scenario)

    assert not any(CONTRACT in name for name in scenario.stack_names())
    assert scenario.game.winner is None


def test_two_copies_of_one_demon_count_once():
    scenario = _board([*DEMONS[:3], DEMONS[0]])
    _to_upkeep(scenario)

    assert not any(CONTRACT in name for name in scenario.stack_names())
    assert scenario.game.winner is None


def test_condition_is_rechecked_on_resolution():
    """CR 603.4 / 608.2a: a Demon leaving in response leaves three names, so
    the ability does nothing as it resolves."""
    scenario = _board(DEMONS)
    _to_upkeep(scenario)
    assert any(CONTRACT in name for name in scenario.stack_names())

    scenario.game.destroy(scenario.creature("Miasma Demon", "alice"))

    scenario.pass_until_resolved()

    assert scenario.find("Miasma Demon", Zone.GRAVEYARD, "alice")
    assert scenario.game.winner is None


GATES = [
    "Azorius Guildgate",
    "Boros Guildgate",
    "Dimir Guildgate",
    "Golgari Guildgate",
    "Gruul Guildgate",
    "Izzet Guildgate",
    "Orzhov Guildgate",
    "Rakdos Guildgate",
    "Selesnya Guildgate",
    "Simic Guildgate",
]


def _maze(battlefield: list[str], library: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice",
            library=library,
            battlefield=["Maze's End", "Swamp", "Swamp", "Swamp", *battlefield],
        )
        .player("bob", library=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _activate_maze(scenario, fetched: str) -> None:
    maze = scenario.find("Maze's End", Zone.BATTLEFIELD, "alice")
    payers = scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice")
    target = scenario.find(fetched, Zone.LIBRARY, "alice")
    scenario.will_choose_cards(target, source="Maze's End", times=None)
    scenario.activate(maze, *payers, index=1)
    scenario.pass_until_resolved()


def test_mazes_end_wins_with_ten_gates_with_different_names():
    scenario = _maze(GATES[:9], [GATES[9], "Swamp"])

    _activate_maze(scenario, GATES[9])

    assert scenario.find(GATES[9], Zone.BATTLEFIELD, "alice")
    assert scenario.game.winner == "alice"


def test_mazes_end_ten_gates_sharing_a_name_do_not_win():
    scenario = _maze(GATES[:9], [GATES[0], "Swamp"])

    _activate_maze(scenario, GATES[0])

    assert scenario.game.winner is None
