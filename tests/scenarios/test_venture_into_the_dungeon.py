"""Scenario: venture into the dungeon (CR 701.49), dungeons (CR 309), and
completing one (CR 309.7).

Rules read whole with `mise run rules:find` in the session that wrote this:

- **CR 309.2 / 309.2a-c** - dungeon cards begin outside the game and come in
  only by venturing, into the command zone, and never leave it except by
  leaving the game.
- **CR 309.3** - one dungeon card per player in the command zone.
- **CR 309.4a / 309.4c** - the venture marker starts on the topmost room;
  each room's ability is "When you move your venture marker into this room,
  [effect.]", controlled by the dungeon's owner.
- **CR 309.5a / 309.5b** - the marker follows an arrow of the player's
  choice; from the bottommost room the dungeon is removed and a new one
  begun.
- **CR 309.6** - a dungeon whose marker is on its bottommost room is removed
  (a state-based action) once no room ability of it is waiting to leave the
  stack.
- **CR 309.7** - "A player completes a dungeon as that dungeon card is
  removed from the game."
- **CR 701.49a-c** - venture into the dungeon.
- **CR 603.4** / **CR 608.2a** - "if you've completed a dungeon", "if you
  haven't completed Tomb of Annihilation".

Lost Mine of Phandelver, Tomb of Annihilation and Dungeon of the Mad Mage
are the three dungeons in the printing pool; Veteran Dungeoneer (an enters
trigger), Dungeon Map (an activated ability), Bar the Gate (a spell),
Eccentric Apprentice and Acererak the Archlich (the two conditions) venture
and read them.
"""

import pytest

from magic_cards_model.machines import Step, conditions
from magic_cards_model.machines.conditions import ConditionContext
from magic_cards_model.machines.dungeon import (
    dungeon_in_command_zone,
    dungeon_printings,
    rooms_of,
    venture,
)
from magic_cards_model.machines.triggers import GameEvent, TriggerEvent
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario

LOST_MINE = "Lost Mine of Phandelver"
TOMB = "Tomb of Annihilation"
MAD_MAGE = "Dungeon of the Mad Mage"


def _board(alice=(), *, bob=(), hand=(), library=None):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=list(alice),
            hand=list(hand),
            library=list(library or ["Plains"] * 10),
        )
        .player("bob", battlefield=list(bob), library=["Plains"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _venture(scenario, *, player="alice", dungeon=None, room=None, resolve=True):
    if dungeon is not None:
        scenario.will_choose_mode(dungeon, username=player)
    if room is not None:
        scenario.will_choose_mode(room, username=player)
    venture(scenario.game, player, source_name="test")
    scenario.game.put_triggers_on_stack()
    if resolve and scenario.game.stack:
        scenario.pass_until_resolved()


def _completed(scenario, player="alice") -> bool | None:
    return conditions.read_condition(
        ConditionContext(scenario.game, player), "you've completed a dungeon"
    )


# -- the dungeons and their rooms -------------------------------------------------


def test_the_rooms_are_read_off_the_printed_dungeon():
    rooms = rooms_of(card(LOST_MINE))
    assert [room.name for room in rooms] == [
        "Cave Entrance",
        "Goblin Lair",
        "Mine Tunnels",
        "Storeroom",
        "Dark Pool",
        "Fungi Cavern",
        "Temple of Dumathoin",
    ]
    assert rooms[0].leads_to == ("Goblin Lair", "Mine Tunnels")
    assert rooms[-1].leads_to == ()
    assert rooms[0].effect == "Scry 1."


def test_every_dungeon_in_the_pool_can_be_chosen():
    assert {printing.name for printing in dungeon_printings()} >= {LOST_MINE, TOMB, MAD_MAGE}


# -- venturing ------------------------------------------------------------------------


def test_the_first_venture_brings_the_chosen_dungeon_in_at_its_topmost_room():
    scenario = _board()
    _venture(scenario, dungeon=LOST_MINE, resolve=False)
    dungeon = dungeon_in_command_zone(scenario.game, "alice")
    assert dungeon is not None and dungeon.name == LOST_MINE
    assert dungeon.zone is Zone.COMMAND
    assert dungeon.owner == "alice"
    assert dungeon.venture_room == "Cave Entrance"
    assert len(scenario.game.stack) == 1
    (room_ability,) = scenario.game.stack
    assert room_ability.controller == "alice"
    assert room_ability.source_id == dungeon.id


def test_the_room_ability_resolves():
    """Cave Entrance: "Scry 1." - the scry is asked."""
    scenario = _board()
    _venture(scenario, dungeon=LOST_MINE)
    assert any(question.kind.value == "scry" for question in scenario.questions_asked())


def test_the_marker_follows_the_arrow_the_player_chooses():
    scenario = _board()
    _venture(scenario, dungeon=LOST_MINE)
    _venture(scenario, room="Mine Tunnels")
    dungeon = dungeon_in_command_zone(scenario.game, "alice")
    assert dungeon.venture_room == "Mine Tunnels"
    assert "Treasure Token" in [s.name for s in scenario.game.permanents_controlled_by("alice")]


def test_the_other_arrow():
    scenario = _board()
    _venture(scenario, dungeon=LOST_MINE)
    _venture(scenario, room="Goblin Lair")
    assert "Goblin Token" in [s.name for s in scenario.game.permanents_controlled_by("alice")]


def test_a_room_not_an_arrow_away_is_refused():
    scenario = _board()
    _venture(scenario, dungeon=LOST_MINE)
    with pytest.raises(ValueError):
        _venture(scenario, room="Temple of Dumathoin")


def test_one_dungeon_at_a_time():
    """CR 309.3: venturing again moves the marker; no second dungeon comes in."""
    scenario = _board()
    _venture(scenario, dungeon=LOST_MINE)
    _venture(scenario, room="Mine Tunnels")
    alices = [
        state
        for state in scenario.game.shared_zones[Zone.COMMAND]
        if getattr(state, "owner", None) == "alice"
    ]
    assert len(alices) == 1


def test_each_player_ventures_into_their_own_dungeon():
    scenario = _board()
    _venture(scenario, dungeon=LOST_MINE)
    _venture(scenario, player="bob", dungeon=MAD_MAGE)
    assert dungeon_in_command_zone(scenario.game, "alice").name == LOST_MINE
    assert dungeon_in_command_zone(scenario.game, "bob").name == MAD_MAGE
    assert dungeon_in_command_zone(scenario.game, "bob").venture_room == "Yawning Portal"
    assert scenario.player("bob").life == 21


# -- completing ---------------------------------------------------------------------


def _to_the_bottom_of_lost_mine(scenario, *, resolve_last=True):
    _venture(scenario, dungeon=LOST_MINE)
    _venture(scenario, room="Mine Tunnels")
    _venture(scenario, room="Dark Pool")
    _venture(scenario, resolve=resolve_last)


def test_the_bottommost_room_completes_the_dungeon_once_its_ability_resolves():
    scenario = _board()
    hand = len(scenario.player("alice").hand)
    _to_the_bottom_of_lost_mine(scenario)
    assert len(scenario.player("alice").hand) == hand + 1  # Temple of Dumathoin
    assert dungeon_in_command_zone(scenario.game, "alice") is None
    (completed,) = [s for s in scenario.player("alice").sideboard if s.name == LOST_MINE]
    assert completed.dungeon_completions == 1
    assert _completed(scenario) is True
    assert _completed(scenario, "bob") is False


def test_not_completed_while_the_last_room_ability_is_on_the_stack():
    """CR 309.6's exception."""
    scenario = _board()
    _to_the_bottom_of_lost_mine(scenario, resolve_last=False)
    assert dungeon_in_command_zone(scenario.game, "alice") is not None
    assert _completed(scenario) is False


def test_venturing_from_the_bottommost_room_starts_a_new_dungeon():
    """CR 309.5b / CR 701.49c: with the marker already on the bottommost room,
    the dungeon is completed and another begun."""
    scenario = _board()
    _to_the_bottom_of_lost_mine(scenario, resolve_last=False)
    scenario.game.stack.clear()  # the last room ability is gone without resolving
    _venture(scenario, dungeon=MAD_MAGE)
    assert dungeon_in_command_zone(scenario.game, "alice").name == MAD_MAGE
    assert _completed(scenario) is True


def test_a_completed_dungeon_can_be_ventured_into_again():
    scenario = _board()
    _to_the_bottom_of_lost_mine(scenario)
    _venture(scenario, dungeon=LOST_MINE)
    dungeon = dungeon_in_command_zone(scenario.game, "alice")
    assert dungeon.name == LOST_MINE and dungeon.venture_room == "Cave Entrance"
    assert dungeon.dungeon_completions == 1
    assert _completed(scenario) is True


# -- the Tomb of Annihilation and the Mad Mage's rooms ---------------------------------


def test_trapped_entry_each_player_loses_one_life():
    scenario = _board()
    _venture(scenario, dungeon=TOMB)
    assert scenario.player("alice").life == 19
    assert scenario.player("bob").life == 19


def test_cradle_of_the_death_god_creates_the_atropal_and_completes_tomb():
    scenario = _board(["Grizzly Bears", "Memnite", "Plains"], hand=["Island"])
    _venture(scenario, dungeon=TOMB)
    _venture(scenario, room="Oubliette")
    _venture(scenario)
    assert "The Atropal" in [s.name for s in scenario.game.permanents_controlled_by("alice")]
    assert TOMB in [s.name for s in scenario.player("alice").sideboard]
    acererak_clause = "you haven't completed Tomb of Annihilation"
    assert (
        conditions.read_condition(ConditionContext(scenario.game, "alice"), acererak_clause)
        is False
    )
    assert (
        conditions.read_condition(ConditionContext(scenario.game, "bob"), acererak_clause) is True
    )


def test_oubliette_discards_and_sacrifices_one_of_each():
    """One creature, one artifact, one land - each its controller's choice,
    none twice (CR 701.21a): the Bears as the creature leaves Memnite (an
    artifact creature) to be the artifact."""
    scenario = _board(["Grizzly Bears", "Memnite", "Plains"], hand=["Island"])
    _venture(scenario, dungeon=TOMB)
    scenario.will_choose_cards(scenario.find("Island", Zone.HAND, "alice"))
    scenario.will_choose_cards(scenario.creature("Grizzly Bears", "alice"))
    _venture(scenario, room="Oubliette")
    graveyard = [s.name for s in scenario.player("alice").graveyard]
    assert {"Island", "Grizzly Bears", "Memnite", "Plains"} <= set(graveyard)


def test_oubliette_an_artifact_creature_counts_once():
    """Memnite chosen as the creature cannot also be the artifact: with no
    other artifact, none is sacrificed for that item."""
    scenario = _board(["Grizzly Bears", "Memnite", "Plains"], hand=["Island"])
    _venture(scenario, dungeon=TOMB)
    scenario.will_choose_cards(scenario.find("Island", Zone.HAND, "alice"))
    scenario.will_choose_cards(scenario.creature("Memnite", "alice"))
    _venture(scenario, room="Oubliette")
    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD


def test_veils_of_fear_each_player_discards_or_loses_life():
    scenario = _board(hand=["Island"])
    _venture(scenario, dungeon=TOMB)
    scenario.will_take_the_may(True, username="alice")
    _venture(scenario, room="Veils of Fear")
    assert "Island" in [s.name for s in scenario.player("alice").graveyard]
    assert scenario.player("alice").life == 19
    assert scenario.player("bob").life == 17  # no card in hand: loses 2


def test_twisted_caverns_target_creature_cant_attack_until_your_next_turn():
    scenario = _board(bob=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    _venture(scenario, dungeon=MAD_MAGE)
    _venture(scenario)
    scenario.choose_trigger_targets(MAD_MAGE, [bears])
    _venture(scenario, room="Twisted Caverns")
    assert "This creature can't attack." in scenario.game.characteristics_of(bears).abilities


def test_the_whole_mad_mage_dungeon():
    scenario = _board(library=["Plains"] * 12 + ["Memnite"] * 3)
    _venture(scenario, dungeon=MAD_MAGE)
    _venture(scenario)
    _venture(scenario, room="Goblin Bazaar")
    _venture(scenario)
    _venture(scenario, room="Muiral's Graveyard")
    _venture(scenario)
    _venture(scenario)
    assert dungeon_in_command_zone(scenario.game, "alice") is None
    assert _completed(scenario) is True


# -- cards that venture ---------------------------------------------------------------


def test_veteran_dungeoneer_ventures_as_it_enters():
    scenario = _board(hand=["Veteran Dungeoneer"])
    scenario.will_choose_mode(LOST_MINE)
    scenario.put_onto_battlefield("Veteran Dungeoneer", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    scenario.game.put_triggers_on_stack()
    assert dungeon_in_command_zone(scenario.game, "alice").name == LOST_MINE


def test_dungeon_map_ventures_as_a_sorcery():
    scenario = _board(["Dungeon Map", "Plains", "Plains", "Plains"])
    dungeon_map = scenario.find("Dungeon Map", Zone.BATTLEFIELD)
    scenario.will_choose_mode(LOST_MINE)
    scenario.activate(
        dungeon_map, *scenario.untapped_sources("Plains", "Plains", "Plains"), index=1
    )
    scenario.pass_until_resolved()
    assert dungeon_in_command_zone(scenario.game, "alice").name == LOST_MINE


def test_eccentric_apprentice_after_completing_a_dungeon():
    scenario = _board(["Eccentric Apprentice"], bob=[])
    apprentice = scenario.creature("Eccentric Apprentice", "alice")
    del apprentice
    scenario.game.emit(
        GameEvent(
            event=TriggerEvent.BEGINNING_OF_STEP, step=Step.BEGINNING_OF_COMBAT, player="alice"
        )
    )
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []
    _to_the_bottom_of_lost_mine(scenario)
    scenario.game.emit(
        GameEvent(
            event=TriggerEvent.BEGINNING_OF_STEP, step=Step.BEGINNING_OF_COMBAT, player="alice"
        )
    )
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Eccentric Apprentice's triggered ability"]


def test_sandfall_cell_sacrifice_or_lose_life():
    """ "Each player loses 2 life unless they sacrifice a creature, artifact,
    or land of their choice." - alice sacrifices, bob has nothing to
    sacrifice and loses 2 (CR 608.2d: no impossible choice)."""
    scenario = _board(["Memnite"], hand=["Island"])
    _venture(scenario, dungeon=TOMB)
    scenario.will_take_the_may(False, username="alice")
    _venture(scenario, room="Veils of Fear")
    scenario.will_take_the_may(True, username="alice")
    _venture(scenario)
    assert "Memnite" in [card.name for card in scenario.player("alice").graveyard]
    assert scenario.player("alice").life == 19 - 2
    assert scenario.player("bob").life == 19 - 2 - 2


def test_a_creature_that_cant_attack_is_refused():
    scenario = _board(["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    _venture(scenario, dungeon=MAD_MAGE)
    _venture(scenario)
    scenario.choose_trigger_targets(MAD_MAGE, [bears])
    _venture(scenario, room="Twisted Caverns")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    with pytest.raises(ValueError, match="can't attack"):
        scenario.attack_with(bears)


def test_runestone_caverns_exiles_two_you_may_play():
    scenario = _board(library=["Mountain", "Lightning Bolt"] + ["Plains"] * 10)
    _venture(scenario, dungeon=MAD_MAGE)
    _venture(scenario)
    _venture(scenario, room="Twisted Caverns")
    _venture(scenario)
    _venture(scenario, room="Runestone Caverns")
    exiled = [card for card in scenario.game.exile if card.name in ("Mountain", "Lightning Bolt")]
    assert len(exiled) == 2
    mountain = next(card for card in exiled if card.name == "Mountain")
    scenario.play_land("Mountain", from_zone=Zone.EXILE)
    assert mountain.zone is Zone.BATTLEFIELD


def test_mad_wizards_lair_draws_three_and_casts_one_free():
    """Draw three, reveal them, and cast one without paying its mana cost
    during the resolution (CR 608.2g) - Grizzly Bears, a creature, at no
    sorcery timing."""
    scenario = _board(library=["Grizzly Bears", "Plains", "Plains"] + ["Plains"] * 9)
    _venture(scenario, dungeon=MAD_MAGE)
    _venture(scenario)
    _venture(scenario, room="Goblin Bazaar")
    _venture(scenario)
    _venture(scenario, room="Muiral's Graveyard")
    _venture(scenario)
    scenario.will_take_the_may(True)
    _venture(scenario)
    scenario.pass_until_resolved()
    assert "Grizzly Bears" in [s.name for s in scenario.game.permanents_controlled_by("alice")]
    assert dungeon_in_command_zone(scenario.game, "alice") is None
