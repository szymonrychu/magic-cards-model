"""EP-02 R3 T5: life-total amounts - amounts read off the players and the board that a
life change, a token count, a pump or a draw spends.

One mechanic: a variable amount whose source is a player-level number.

- `for_each_count` reads the "for each <count>" tails `amount_sentences.parse_life_clause`
  hands over that no earlier reader knew: "player" (CR 102.1), "creature attacking
  you" (CR 506.2, 508.1k), "<quality> that player controls" (the trigger event's
  player), "<creature> that died this turn" (CR 700.4) and "time it was kicked"
  (CR 702.33d).
- `amount_term` reads the "equal to <expr>" terms: "your speed" (CR 702.179f),
  "the number of opponents you have" (CR 102.2), "the greatest power|toughness|mana
  value among other <things> you control" (CR 107.2) and "the total power|toughness
  of <things> you control".

Both are pure readers: no persisted field. `amounts.py` calls them as its last rung, so a
sentence `amount_sentences` already reads picks the new terms up without a second parser.
"""

import functools
import re
from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID

from .amount_sentences import apply_life, life_clause_amount, parse_life_clause
from .effects._chains import FORWARD, MIXED_CLAUSE

if TYPE_CHECKING:
    from ..models.card_state import CardState
    from ..models.game import Game, StackObject

#: `(game, controller, source_id) -> int`, the `_for_each_multiplier` reader shape.
ForEachReader = Callable[["Game", str, "str | None"], int]
#: `(game, controller, source, x) -> int`, the `_amount_term` reader shape.
TermReader = Callable[["Game", str, "CardState | None", int], int]

_EACH_PLAYER_RE = re.compile(r"^players?$", re.IGNORECASE)
_ATTACKING_YOU_RE = re.compile(r"^creatures? attacking you$", re.IGNORECASE)
_THAT_PLAYER_CONTROLS_RE = re.compile(r"^(?P<what>.+?) that player controls$", re.IGNORECASE)
_DIED_RE = re.compile(r"^(?P<what>[A-Za-z-]+) that died this turn$", re.IGNORECASE)
_TIMES_KICKED_RE = re.compile(
    r"^times? (?:it|this (?:spell|creature|permanent|enchantment|artifact)) was kicked$",
    re.IGNORECASE,
)


def _source_of(game: "Game", source_id: "str | None") -> "CardState | None":
    return None if source_id is None else game.find_by_id(UUID(source_id))


def _event_player(game: "Game") -> str | None:
    """The player the resolving trigger's event concerns (CR 603.2's "that player")."""
    event = getattr(game.resolving, "event", None)
    return None if event is None else event.player


@functools.cache
def for_each_count(phrase: str) -> ForEachReader | None:
    """The count of a "for each <phrase>" tail described in the module docstring."""
    text = " ".join(phrase.split()).rstrip(".")
    lowered = text.lower()
    if _EACH_PLAYER_RE.fullmatch(text):
        # CR 102.1: every person still in the game.
        return lambda game, _controller, _source: len(game.players_in_game)
    if "attacking you" in lowered and _ATTACKING_YOU_RE.fullmatch(text):
        # CR 506.2: the attacks whose defender is the controller themselves (a planeswalker
        # or battle they control is not "you").
        def attacking_you(game: "Game", controller: str, _source: "str | None") -> int:
            return sum(
                1
                for attack in game.combat.attacks
                if attack.defender.username == controller and attack.defender.card_id is None
            )

        return attacking_you
    if "that player controls" in lowered and (match := _THAT_PLAYER_CONTROLS_RE.fullmatch(text)):
        from .effects.amounts import _for_each_multiplier

        counted = _for_each_multiplier(f"{match.group('what')} you control")
        if counted is None:
            return None

        def controlled_by_that_player(game: "Game", controller: str, source: "str | None") -> int:
            player = _event_player(game)
            return 0 if player is None else counted(game, player, source)

        return controlled_by_that_player
    if "died this turn" in lowered and _DIED_RE.fullmatch(text):
        from .effects.amounts import count_expression

        counted_deaths = count_expression(f"the number of {text}")
        if counted_deaths is None:
            return None
        return lambda game, controller, _source: counted_deaths(game, controller)
    if "kicked" in lowered and _TIMES_KICKED_RE.fullmatch(text):

        def times_kicked(game: "Game", _controller: str, source_id: "str | None") -> int:
            source = _source_of(game, source_id)
            record = None if source is None else game.cast_record_of(source)
            return 0 if record is None else record.kicked

        return times_kicked
    return None


#: `(game, controller) -> int`, the `count_expression` reader shape.
CountReader = Callable[["Game", str], int]


@functools.cache
def count_term(text: str) -> CountReader | None:
    """The player-level terms - "your life total" (CR 119.1), "your speed" (CR 702.179f),
    "the number of opponents you have" / "the number of players" (CR 102.1, 102.2) - as a
    `count_expression` reader, so a sentence that reads its X through `count_expression`
    (a "create X tokens, where X is ..." or a layer pump "gets +X/+X, where X is ...")
    reads them too."""
    lowered = " ".join(text.lower().split())
    if lowered == "your life total":
        return lambda game, controller: game.player(controller).life
    if lowered == "your speed":
        # CR 702.179f: a player with no speed has speed 0 for an effect that refers to it.
        return lambda game, controller: game.player(controller).speed or 0
    if _OPPONENTS_RE.fullmatch(lowered):
        everyone = lowered.endswith("players")
        return lambda game, controller: sum(
            1 for player in game.players_in_game if everyone or player.username != controller
        )
    return None


_OPPONENTS_RE = re.compile(r"^the number of (?:opponents(?: you have)?|players)$", re.IGNORECASE)
_GREATEST_OTHER_RE = re.compile(
    r"^(?:the )?(?P<which>greatest|total) (?P<stat>power|toughness|mana value) (?:among|of) "
    r"(?P<other>other )?(?P<what>[A-Za-z]+) you control$",
    re.IGNORECASE,
)


@functools.cache
def amount_term(text: str) -> TermReader | None:
    """The "equal to <expr>" terms described in the module docstring, or `None`."""
    if (player_level := count_term(text)) is not None:
        return lambda game, controller, _source, _x: player_level(game, controller)
    lowered = text.lower()
    if "among" in lowered or " of " in lowered:
        return _characteristic_extremum(" ".join(text.split()))
    return None


def _characteristic_extremum(text: str) -> TermReader | None:
    match = _GREATEST_OTHER_RE.fullmatch(text)
    if match is None:
        return None
    from .effects.text import _singular_card_type, _singular_subtype_for_count_expression

    what = match.group("what")
    card_type = _singular_card_type(what)
    subtype = None if card_type is not None else _singular_subtype_for_count_expression(what)
    if card_type is None and subtype is None:
        return None
    stat = match.group("stat").lower()
    greatest = match.group("which").lower() == "greatest"
    excludes_source = match.group("other") is not None

    def read(game: "Game", controller: str, source: "CardState | None", _x: int) -> int:
        board = game.computed_board()
        values: list[int] = []
        for permanent in game.battlefield:
            chars = board.of(permanent)
            if chars.controller != controller:
                continue
            if excludes_source and source is not None and permanent.id == source.id:
                continue
            if card_type is not None and card_type not in chars.types:
                continue
            if subtype is not None and not any(w.lower() == subtype for w in chars.subtypes):
                continue
            if stat == "mana value":
                values.append(int(permanent.mana_value))  # CR 202.3
            elif stat == "power":
                values.append(chars.numeric_power)  # CR 208.5
            else:
                values.append(chars.numeric_toughness)
        if not values:
            return 0  # CR 107.2: a number that can't be determined is 0
        return max(values) if greatest else sum(values)

    return read


# --------------------------------------------------------------------------
# Clauses
# --------------------------------------------------------------------------

#: Who a life clause may name: the controller, the opponent groups, everyone, or a
#: declared player target (CR 102.2, 102.3, 115.1).
_LIFE_WHO = frozenset(
    {
        "you",
        "each opponent",
        "each other player",
        "each player",
        "target opponent",
        "target player",
    }
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_life_amount_clause(clause: str, *, for_spell: bool) -> "Callable[..., None] | None":
    """ "<who> gains/loses twice X life | life equal to <expr> | N life for each <count> |
    X life, where X is <expr>" - the one life-sentence reader (`amount_sentences`) run as a
    clause, so every amount a sibling reader knows is usable in a sequence of sentences
    (CR 608.2c). X is the announced X of the spell or ability (CR 107.3a)."""
    lowered = clause.lower()
    if " life" not in lowered or not ("gain" in lowered or "lose" in lowered):
        return None
    life = parse_life_clause(clause)
    if life is None or life.who not in _LIFE_WHO:
        return None
    if life.who.startswith("target"):
        from .effects import _targets_understood

        if not _targets_understood(life.who, allow_player_targets=True):
            return None
    amount = life_clause_amount(life, spell_x=for_spell)
    if amount is None:
        return None
    who, gains = life.who, life.gains

    def effect(game: "Game", stack_object: "StackObject") -> None:
        apply_life(game, stack_object, who, gains, amount)

    return effect


_REVEAL_HAND_CLAUSE_RE = re.compile(
    r"^(?P<who>target player|target opponent|each opponent|each player) reveals their hand$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_reveal_hand_clause(clause: str, *, for_spell: bool) -> "Callable[..., None] | None":
    """ "Target player reveals their hand." on its own: every card in it is shown to all
    players and none moves (CR 701.20a, CR 701.20b); a later sentence reads it
    ("the number of cards in that player's hand")."""
    match = _REVEAL_HAND_CLAUSE_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    who = match.group("who").lower()
    if who.startswith("target"):
        from .effects import _targets_understood

        if not _targets_understood(who, allow_player_targets=True):
            return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        from .amount_sentences import controller_of, resolve_recipients, source_card

        source = source_card(game, stack_object)
        for player in resolve_recipients(game, stack_object, who, controller_of(game, stack_object)):
            for card in list(player.hand):
                game.reveal(card, source=None if source is None else source.name)

    return effect


__all__ = ["amount_term", "count_term", "for_each_count"]
