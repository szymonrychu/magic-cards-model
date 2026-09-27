"""Scenario: Promising Stairs' upkeep trigger - "At the beginning of your
upkeep, surveil 1. You win the game if there are eight or more different
names among unlocked doors of Rooms you control."

Two readers close it, each general over its template:

1. **"You win the game if `<condition>`."** (CR 104.2b: "An effect may state
   that a player wins the game.") - the trailing-"if" twin of the leading
   "If `<condition>`, you win the game." Fblthp already reads
   (`machines/effects._parse_if_condition_you_win_the_game_clause`), with the
   same `Game.condition_holds` condition and the same resolution-time check.
   An unreadable condition is refused at parse time rather than silently
   never winning.
2. **"there are N or more different names among unlocked doors of Rooms you
   control"** (`machines/conditions/board.py`). CR 709.5c: a half is
   "unlocked" if the permanent has that half's unlocked designation; CR
   709.5j: a door is a half of a Room. CR 709.5: a locked half has no name on
   the battlefield, so only unlocked doors contribute a name. CR 201.2b: names
   are different only when no two share a name, so two copies of one door
   count once.

Oracle text, verified against the printings pool (every card Modern-legal):

- **Central Elevator // Promising Stairs** - "Promising Stairs - At the
  beginning of your upkeep, surveil 1. You win the game if there are eight
  or more different names among unlocked doors of Rooms you control."
- **Unholy Annex // Ritual Chamber**, **Derelict Attic // Widow's Walk**,
  **Glassworks // Shattered Yard** - the other Rooms whose doors are counted.

A Room put onto the battlefield by the harness was not cast, so it enters
locked (CR 709.5d); each test gives the doors it needs through `Game.
unlock_door` (CR 709.5f) before the turn begins, and discards the door-unlock
triggers that staging raised - they are not what is under test.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import CardState, Zone

from .harness import Scenario

CENTRAL_ELEVATOR = "Central Elevator // Promising Stairs"
UNHOLY_ANNEX = "Unholy Annex // Ritual Chamber"
DERELICT_ATTIC = "Derelict Attic // Widow's Walk"
GLASSWORKS = "Glassworks // Shattered Yard"

DOORS = {
    CENTRAL_ELEVATOR: ("Central Elevator", "Promising Stairs"),
    UNHOLY_ANNEX: ("Unholy Annex", "Ritual Chamber"),
    DERELICT_ATTIC: ("Derelict Attic", "Widow's Walk"),
    GLASSWORKS: ("Glassworks", "Shattered Yard"),
}


def _rooms(scenario, card_name: str, username: str = "alice") -> list[CardState]:
    return [
        state
        for state in scenario.game.permanents_controlled_by(username)
        if state.card.name == card_name
    ]


def _unlock(scenario, room: CardState, *doors: str) -> None:
    for door in doors:
        assert scenario.game.unlock_door(room, door)


def _board(alice_rooms: list[str], bob_rooms: list[str] | None = None):
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island", "Forest", "Mountain"],
            battlefield=alice_rooms,
        )
        .player("bob", library=["Plains"], battlefield=bob_rooms or [])
        .build()
    )
    return scenario


def _to_upkeep(scenario) -> None:
    """Drop the staging's door-unlock triggers, then enter alice's upkeep,
    where Promising Stairs triggers."""
    scenario.game.pending_triggers.clear()
    scenario.advance()  # untap -> upkeep
    assert scenario.step is Step.UPKEEP
    # The stack names the source by its current name (CR 709.5: only its
    # unlocked doors' names).
    (name,) = scenario.stack_names()
    assert "Promising Stairs" in name and name.endswith("triggered ability")


def _unlock_all(scenario, username: str = "alice") -> None:
    for card_name, doors in DOORS.items():
        for room in _rooms(scenario, card_name, username):
            _unlock(scenario, room, *doors)


def test_promising_stairs_surveils_one_each_upkeep():
    scenario = _board([CENTRAL_ELEVATOR])
    (room,) = _rooms(scenario, CENTRAL_ELEVATOR)
    _unlock(scenario, room, "Promising Stairs")
    _to_upkeep(scenario)
    island = scenario.find("Island", Zone.LIBRARY, "alice")
    scenario.surveil_to_graveyard(island)

    scenario.pass_until_resolved()

    assert island.zone is Zone.GRAVEYARD
    assert [card.name for card in scenario.player("alice").library][:1] == ["Forest"]
    assert scenario.game.winner is None


def test_eight_different_unlocked_door_names_win_the_game():
    scenario = _board([CENTRAL_ELEVATOR, UNHOLY_ANNEX, DERELICT_ATTIC, GLASSWORKS])
    _unlock_all(scenario)
    _to_upkeep(scenario)

    scenario.pass_until_resolved()

    assert scenario.game.winner == "alice"


def test_seven_different_unlocked_door_names_do_not_win():
    scenario = _board([CENTRAL_ELEVATOR, UNHOLY_ANNEX, DERELICT_ATTIC, GLASSWORKS])
    (glassworks,) = _rooms(scenario, GLASSWORKS)
    for card_name, doors in DOORS.items():
        if card_name != GLASSWORKS:
            _unlock(scenario, _rooms(scenario, card_name)[0], *doors)
    # CR 709.5: the locked Shattered Yard has no name to count.
    _unlock(scenario, glassworks, "Glassworks")
    _to_upkeep(scenario)

    scenario.pass_until_resolved()

    assert scenario.game.winner is None


def test_duplicate_door_names_count_once():
    """CR 201.2b: a second Glassworks' two doors add no new names - seven
    different names across nine unlocked doors is still seven."""
    scenario = _board([CENTRAL_ELEVATOR, UNHOLY_ANNEX, DERELICT_ATTIC, GLASSWORKS, GLASSWORKS])
    for card_name, doors in DOORS.items():
        if card_name != GLASSWORKS:
            _unlock(scenario, _rooms(scenario, card_name)[0], *doors)
    first, second = _rooms(scenario, GLASSWORKS)
    _unlock(scenario, first, "Glassworks")
    _unlock(scenario, second, "Glassworks")
    _to_upkeep(scenario)

    scenario.pass_until_resolved()

    assert scenario.game.winner is None


def test_opponents_unlocked_doors_do_not_count():
    scenario = _board([CENTRAL_ELEVATOR, UNHOLY_ANNEX, DERELICT_ATTIC], [GLASSWORKS])
    _unlock_all(scenario, "alice")
    _unlock_all(scenario, "bob")
    _to_upkeep(scenario)

    scenario.pass_until_resolved()

    assert scenario.game.winner is None


# ---------------------------------------------------------------------------
# Generality: the trailing "You win the game if <condition>." on a spell,
# with an unrelated condition. Coalition Victory (off the api deck pool,
# Modern-legal): "You win the game if you control a land of each basic land
# type and a creature of each color."
# ---------------------------------------------------------------------------

COALITION_LANDS = ["Plains", "Island", "Swamp", "Mountain", "Forest", "Forest", "Forest", "Plains"]


def _cast_coalition_victory(creatures: list[str]):
    scenario = (
        Scenario()
        .player("alice", hand=["Coalition Victory"], battlefield=[*COALITION_LANDS, *creatures])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources(*COALITION_LANDS)
    scenario.cast_and_resolve("Coalition Victory", *lands)
    return scenario


def test_coalition_victory_wins_with_every_basic_land_type_and_color():
    scenario = _cast_coalition_victory(
        ["Savannah Lions", "Delver of Secrets", "Dark Confidant", "Goblin Guide", "Grizzly Bears"]
    )

    assert scenario.game.winner == "alice"


def test_coalition_victory_does_not_win_missing_a_color():
    scenario = _cast_coalition_victory(
        ["Savannah Lions", "Delver of Secrets", "Goblin Guide", "Grizzly Bears"]
    )

    assert scenario.game.winner is None
    assert scenario.find("Coalition Victory", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
