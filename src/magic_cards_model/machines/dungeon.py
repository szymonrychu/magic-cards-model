"""Dungeons and venturing into them (CR 309, CR 701.49).

A dungeon card begins outside the game (CR 309.2) and is brought in only by
venturing into the dungeon (CR 701.49a): it goes to the command zone with its
owner's venture marker on its topmost room, each venture moves the marker
along an arrow to the next room (CR 309.5a, CR 701.49b), and every room the
marker enters triggers that room's ability (CR 309.4c: "When you move your
venture marker into this room, [effect.]"). A dungeon whose marker is on its
bottommost room, with no room ability of it still waiting to leave the stack,
is removed from the game (CR 309.6, a state-based action), and "a player
completes a dungeon as that dungeon card is removed from the game" (CR 309.7).

The rooms are read off the dungeon's own printed text: each line is "<room
name> - <effect>. (Leads to: <room>[, <room>])", the bottommost room being
the one with no "Leads to". Nothing here names a dungeon: every dungeon card
in the printing pool is one to choose from (`dungeon_printings`).

Where things live:

- the dungeon in the command zone is a `CardState` in `Game.shared_zones
  [Zone.COMMAND]` owned by the venturing player, its marker the room name in
  `CardState.venture_room`;
- a completed dungeon is removed from the game - kept outside it (CR
  400.11a, the owner's `Zone.SIDEBOARD` group, where every "from outside the
  game" card is kept) with `CardState.dungeon_completions` counting how many
  times its owner completed it, which is what "you've completed a dungeon" and
  "you haven't completed Tomb of Annihilation" read.

Rules verified with `mise run rules:find`:

- CR 309.2, 309.2a-d; 309.3; 309.4, 309.4a, 309.4c; 309.5a, 309.5b; 309.6;
  309.7 - dungeons.
- CR 701.49a-d - venture into the dungeon.
- CR 603.12 - a reflexive triggered ability (the room ability is queued the
  same way: its trigger event has just happened).
- CR 400.11a - outside the game.
"""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..models.zone import Zone

if TYPE_CHECKING:
    from ..models.card import Card
    from ..models.card_state import CardState
    from ..models.game import Game


def is_dungeon(card: "Card") -> bool:
    """CR 309.1: "Dungeon is a card type" - read off the type line."""
    front = (card.type_line or "").split("—")[0]
    return "Dungeon" in front.split()


@dataclass(frozen=True)
class Room:
    """One room of a dungeon (CR 309.4): its name, its room ability's effect,
    and the rooms its arrows lead to (empty for the bottommost room)."""

    name: str
    effect: str
    leads_to: tuple[str, ...]


_ROOM_LINE = re.compile(
    r"^(?P<name>[^—\n]+?)\s+—\s+(?P<effect>.+?)"
    r"(?:\s*\(Leads to:\s*(?P<leads>[^)]*)\))?\s*$"
)


def rooms_of(card: "Card") -> tuple[Room, ...]:
    """The rooms printed on a dungeon card, topmost first (CR 309.4)."""
    rooms = []
    for line in (card.oracle_text or "").splitlines():
        match = _ROOM_LINE.match(line.strip())
        if match is None:
            continue
        leads = match.group("leads")
        rooms.append(
            Room(
                name=match.group("name").strip(),
                effect=match.group("effect").strip(),
                leads_to=tuple(part.strip() for part in leads.split(",")) if leads else (),
            )
        )
    return tuple(rooms)


def room_named(card: "Card", name: str | None) -> Room | None:
    return next((room for room in rooms_of(card) if room.name == name), None)


def is_bottommost(card: "Card", name: str | None) -> bool:
    """CR 309.5b's "bottommost room": the room no arrow leads away from."""
    room = room_named(card, name)
    return room is not None and not room.leads_to


def dungeon_in_command_zone(game: "Game", player: str) -> "CardState | None":
    """The dungeon card `player` owns in the command zone, or None (CR 309.3:
    at most one)."""
    from ..models.card_state import CardState

    for state in game.shared_zones[Zone.COMMAND]:
        if isinstance(state, CardState) and state.owner == player and is_dungeon(state.card):
            return state
    return None


def _room_ability_pending(game: "Game", dungeon: "CardState") -> bool:
    """CR 309.6's exception: a room ability of `dungeon` that has triggered
    but not yet left the stack."""
    return any(
        item.source_id == dungeon.id for item in (*game.pending_triggers, *game.abilities_on_stack)
    )


def finished(game: "Game", dungeon: "CardState") -> bool:
    """Whether CR 309.6 removes `dungeon` now: its marker is on the
    bottommost room and no room ability of it is still waiting."""
    return is_bottommost(dungeon.card, dungeon.venture_room) and not _room_ability_pending(
        game, dungeon
    )


def completed_dungeon_names(game: "Game", player: str) -> list[str]:
    """Every dungeon `player` has completed, by name, once per completion (CR
    309.7) - including one CR 309.6 is about to remove, since a state-based
    action has always been performed before anybody asks."""
    from ..models.card_state import CardState

    names: list[str] = []
    for state in game.player(player).sideboard:
        if isinstance(state, CardState) and is_dungeon(state.card):
            names.extend([state.name] * state.dungeon_completions)
    current = dungeon_in_command_zone(game, player)
    if current is not None:
        names.extend([current.name] * current.dungeon_completions)
        if finished(game, current):
            names.append(current.name)
    return names


# -- choosing and entering ----------------------------------------------------------


def dungeon_printings(quality: str | None = None) -> list["Card"]:
    """Every dungeon card a player can choose from outside the game (CR
    309.2a) - each dungeon printing the engine carries, one per name. A
    dungeon with a dungeon type (CR 205.3p's Undercity) is chosen only by
    venturing into that quality (CR 701.49d), and one without by plain
    venturing."""
    from ..data.printing_pool import printing_pool

    found: dict[str, Card] = {}
    for printing in printing_pool().values():
        if not is_dungeon(printing) or printing.name in found:
            continue
        dungeon_types = tuple(printing.subtypes)
        if quality is None and dungeon_types:
            continue
        if quality is not None and quality not in dungeon_types:
            continue
        found[printing.name] = printing
    return sorted(found.values(), key=lambda printing: printing.name)


def _ask(
    game: "Game",
    player: str,
    prompt: str,
    options: tuple[str, ...],
    source: str,
    source_id: str | None,
) -> str:
    """One CR 608.2d choice among named options, asked through `Game.ask`."""
    from .decisions import Decision, DecisionKind

    if len(options) == 1:
        return options[0]
    answer = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_A_MODE,
            player=player,
            prompt=prompt,
            source=source,
            source_id=source_id,
            options=options,
        )
    )
    if answer not in options:
        raise ValueError(f"{answer!r} is not one of {', '.join(options)} (CR 309.5a)")
    return str(answer)


def _bring_in(
    game: "Game", player: str, source_name: str, source_id: str | None, quality: str | None
) -> "CardState":
    """CR 309.2a / 701.49a: choose a dungeon card from outside the game and put
    it into the command zone, the venture marker on its topmost room (CR
    309.4a). A dungeon this player completed before is the same card, back
    from outside the game; any other is a new object."""
    from ..models.card_state import CardState

    printings = {printing.name: printing for printing in dungeon_printings(quality)}
    if not printings:
        raise ValueError("there is no dungeon card to venture into (CR 309.2a)")
    name = _ask(game, player, "choose a dungeon", tuple(printings), source_name, source_id)
    outside = game.player(player).sideboard
    dungeon = next(
        (state for state in outside if isinstance(state, CardState) and state.name == name), None
    )
    if dungeon is not None:
        outside.remove(dungeon)
        dungeon.move_to(Zone.COMMAND)
    else:
        dungeon = CardState(
            card=printings[name], zone=Zone.COMMAND, controller=player, owner=player
        )
    dungeon.controller = player
    dungeon.bind_to_game(game)
    game.shared_zones[Zone.COMMAND].append(dungeon)
    dungeon.venture_room = rooms_of(dungeon.card)[0].name
    return dungeon


def _enter_room(game: "Game", dungeon: "CardState", player: str) -> None:
    """CR 309.4c: moving the marker into a room triggers its room ability -
    "When you move your venture marker into this room, [effect.]" - controlled
    by the dungeon's owner, queued for the stack the way every trigger is (CR
    603.3)."""
    from .delayed import DungeonRoomAbility

    room = room_named(dungeon.card, dungeon.venture_room)
    if room is None:
        return
    game.create_reflexive_trigger(
        text=room.effect,
        controller=player,
        source_id=dungeon.id,
        source_name=dungeon.name,
        callback=DungeonRoomAbility(room=room.name),
    )


def complete(game: "Game", dungeon: "CardState") -> None:
    """CR 309.7: its owner completes the dungeon as it is removed from the
    game - kept outside the game (CR 400.11a) with the completion counted."""
    owner = dungeon.owner or dungeon.controller or ""
    zone = game.shared_zones[Zone.COMMAND]
    if dungeon in zone:
        zone.remove(dungeon)
    dungeon.venture_room = None
    dungeon.dungeon_completions += 1
    dungeon.move_to(Zone.SIDEBOARD)
    game.player(owner).sideboard.append(dungeon)


def complete_finished_dungeons(game: "Game", *, resolving_id: object = None) -> None:
    """CR 309.6's state-based action, performed wherever this engine can:
    every dungeon whose marker is on its bottommost room, with no room
    ability of it still waiting (the one resolving now aside), is removed."""
    from ..models.card_state import CardState

    for state in list(game.shared_zones[Zone.COMMAND]):
        if not isinstance(state, CardState) or not is_dungeon(state.card):
            continue
        if not is_bottommost(state.card, state.venture_room):
            continue
        waiting = any(
            item.source_id == state.id and item.id != resolving_id
            for item in (*game.pending_triggers, *game.abilities_on_stack)
        )
        if not waiting:
            complete(game, state)


def venture(
    game: "Game",
    player: str,
    *,
    source_name: str,
    source_id: str | None = None,
    quality: str | None = None,
) -> "CardState":
    """CR 701.49a-d: venture into the dungeon (or into `quality`, CR
    701.49d). Returns the dungeon the marker is now in.

    - No dungeon in the command zone: bring one in (CR 701.49a).
    - The marker on the bottommost room: that dungeon is completed and removed
      (CR 701.49c, CR 309.7), and another brought in.
    - Otherwise: the marker moves along an arrow of the player's choice (CR
      701.49b).

    Every room entered triggers its room ability (CR 309.4c)."""
    with game._id_allocator_scope():  # noqa: SLF001 - ids minted here are persisted
        complete_finished_dungeons(game)
        dungeon = dungeon_in_command_zone(game, player)
        if dungeon is not None and is_bottommost(dungeon.card, dungeon.venture_room):
            complete(game, dungeon)
            dungeon = None
        if dungeon is None:
            dungeon = _bring_in(game, player, source_name, source_id, quality)
        else:
            room = room_named(dungeon.card, dungeon.venture_room)
            leads = room.leads_to if room is not None else ()
            if not leads:
                raise ValueError(f"{dungeon.name}'s marker has nowhere to go (CR 309.5a)")
            dungeon.venture_room = _ask(
                game, player, "choose the next room", tuple(leads), dungeon.name, str(dungeon.id)
            )
        _enter_room(game, dungeon, player)
        return dungeon
