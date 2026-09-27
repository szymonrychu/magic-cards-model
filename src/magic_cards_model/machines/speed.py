"""Speed (CR 702.179a-f) and Max speed (CR 702.178a).

Every CR number here was looked up with `mise run rules:find <number>`
against the 2026-09-25 Comprehensive Rules release in the session that wrote
this file:

- **CR 702.179a** - "Start your engines! is a static ability. If a player
  controls a permanent with start your engines! and that player has no
  speed, their speed becomes 1. This is a state-based action."
- **CR 702.179b** - "Players do not have speed until a rule or effect sets
  their speed to a specific value."
- **CR 702.179c** - "If a player has no speed and they are instructed to
  increase their speed by a certain value, their speed becomes that value."
- **CR 702.179d** - "There is an inherent triggered ability associated with
  a player having 1 or more speed. This ability has no source and is
  controlled by that player. That ability is 'Whenever one or more opponents
  lose life during your turn, if your speed is less than 4, your speed
  increases by 1. This ability triggers only once each turn.'"
- **CR 702.179e** - "Rules and effects may refer to whether a player has
  'max speed.' A player has max speed if their speed is 4."
- **CR 702.179f** - "Some effects refer to a player's speed. If that player
  has no speed, their speed is 0 for the purpose of an effect that refers to
  speed."
- **CR 702.178a** - "A max speed ability is a static ability. 'Max speed —
  [Ability]' means 'As long as your speed is 4, this object has "[Ability]."'
  See rule 702.179, 'Start Your Engines!'"

`Player.speed` (`models/player.py`) is `None` for "no speed" (CR 702.179b),
never `0` - CR 702.179f's "their speed is 0 for the purpose of an effect
that refers to speed" is a *read*, not the player's own recorded state, so a
player with no speed and one with speed 0 (which no rule or effect can ever
actually produce - the lowest a set speed goes is 1, CR 702.179a/c) are kept
distinct rather than collapsed into the same stored value.

`players_starting_their_engines` / `start_engines` are CR 702.179a's own
state-based action, read and performed by `Game._state_based_actions_once`
with the rest of each CR 704.3 round, off the same layered board.

The Max speed ability's own gate (CR 702.178a) is not implemented as a
layer-6 conditional grant/removal; `Game.why_cannot_activate` refuses to
activate an ability whose `ability_word` is "Max speed" unless the activator
currently has max speed, which is the same result CR 613.1f's layer would
give (an object without an ability cannot have it activated, CR 602.5) for
every printed shape in the pool.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .combat import has_keyword

if TYPE_CHECKING:
    from ..models.game import Game
    from ..models.player import Player

#: CR 702.179e: a player has max speed once their speed reaches this value.
MAX_SPEED = 4

#: CR 702.179a/d's own keyword names, read generically off any permanent's
#: computed keywords (CR 613.5) - not gated on any one card, so a future
#: printing of either keyword is read the same way.
START_YOUR_ENGINES_KEYWORD = "start your engines!"


def effective_speed(player: Player) -> int:
    """CR 702.179f: a player with no speed answers 0 for an effect that
    refers to speed - `Player.speed` itself stays `None` (see this module's
    own docstring for why the two are kept distinct)."""
    return player.speed if player.speed is not None else 0


def has_max_speed(player: Player) -> bool:
    """CR 702.179e: true once this player's speed reaches 4."""
    return effective_speed(player) >= MAX_SPEED


def _controls_start_your_engines(game: Game, player: Player) -> bool:
    """CR 702.179a's own condition: a permanent this player controls has
    "Start your engines!" right now (CR 613.5's computed board, so a granted
    copy of the keyword counts exactly as a printed one does)."""
    for permanent in game.battlefield:
        if game.controller_of(permanent).username != player.username:
            continue
        if has_keyword(permanent, START_YOUR_ENGINES_KEYWORD, game):
            return True
    return False


def players_starting_their_engines(game: Game) -> list[Player]:
    """CR 702.179a's state-based action, the reading half: every player with
    no speed who controls a "Start your engines!" permanent.

    Read by `Game._state_based_actions_once` inside the same `snapshot.
    scan_pin` its CR 704.5 checks share, so every permanent's keywords come
    off that one layered board rather than a board per permanent; the speed
    is set afterwards by `start_engines`, with the round's other actions
    (CR 704.3: performed simultaneously).
    """
    return [
        player
        for player in game.players
        if player.speed is None and _controls_start_your_engines(game, player)
    ]


def start_engines(players: list[Player]) -> None:
    """CR 702.179a's state-based action, the acting half: each player
    `players_starting_their_engines` found has their speed become 1."""
    for player in players:
        player.speed = 1


def increase_speed(player: Player, *, by: int = 1) -> None:
    """CR 702.179c: a player with no speed instructed to increase it becomes
    that value outright, rather than an arithmetic "0 + `by`" that CR
    702.179f's read-only zero would otherwise suggest. A player who already
    has speed increases normally."""
    player.speed = by if player.speed is None else player.speed + by


def check_speed_increase_on_life_loss(game: Game, loser_username: str) -> None:
    """CR 702.179d's own inherent triggered ability, checked wherever
    `Game.emit` sees a `TriggerEvent.LOSES_LIFE` - Perilous Snare's own
    "Start your engines!" reminder text: "It increases once on each of your
    turns when an opponent loses life."

    "This ability triggers only once each turn" - `Player.
    speed_increased_on_turn` stamps the turn number (`TurnMachine.
    turns_taken`) the increase last happened, compared against the current
    turn rather than reset at a turn boundary, the same convention `Player.
    life_lost_tally_turn` already uses for an per-turn accumulator with no
    turn-start hook of its own.

    The ability exists only for a player who already has speed (CR
    702.179d: "associated with a player having 1 or more speed") - a player
    CR 702.179a has not yet given a first speed watches nothing.
    """
    turn = game.turn
    if turn is None:
        return
    active = game.active_player
    if loser_username == active.username:
        return  # CR 702.179d's "opponent" - never the watching player themself.
    if active.speed is None:
        return
    if has_max_speed(active):
        return
    if active.speed_increased_on_turn == turn.turns_taken:
        return  # Already triggered once this turn.
    increase_speed(active, by=1)
    active.speed_increased_on_turn = turn.turns_taken
