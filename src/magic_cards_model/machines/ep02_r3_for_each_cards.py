"""EP-02 R3: the one reader of the R3 count terms - "for each <thing>", "the
number of <things>" and "equal to <expr>" counts read off the players, the
turn's history, a cast record, or what is attached to an object or a player.

Three entry points, each a `functools.cache`d pure function of the phrase that
returns `None` for a phrase it does not read:

- `count_term(phrase)`: a `(game, controller) -> int` count that needs no
  source object, the first rung `amounts.count_expression` asks;
- `amount_term(phrase)`: a `(game, controller, source, x) -> int` term, the
  last rung of `amounts._amount_term` - every `count_term` count plus the terms
  that read the object the ability is on;
- `for_each_count(phrase)`: a `(game, controller, source_id) -> int` "for each
  <phrase>" tail, the last rung of `amounts._for_each_multiplier` - the
  for-each-only wordings, else the phrase read as "the number of <phrase>"
  through `amounts.amount_expression`.

Every sub-reader below returns a `_Term` (the reader and whether it needs the
source), so one parse of a wording serves all three entry points. Each count is
taken once, when the instruction is applied (CR 608.2h).
"""

import re
from collections.abc import Callable
from functools import cache
from typing import TYPE_CHECKING, Any, NamedTuple
from uuid import UUID

from ..models.card import Type
from ..models.card_state import CardState
from ..models.player import Player
from ..models.zone import Zone
from ..numbers import COUNT, ORDINAL, parse_count, parse_ordinal
from .effects._chains import FORWARD, MIXED_CLAUSE, MIXED_CLAUSES

if TYPE_CHECKING:
    from ..models.game import Game

#: `(game, controller, source_id) -> int`: `amounts._for_each_multiplier`'s form.
ForEach = Callable[["Game", str, "str | None"], int]
#: `(game, controller) -> int`: `amounts.count_expression`'s form.
NumberOf = Callable[["Game", str], int]
#: `(game, controller, source, x) -> int`: `amounts._amount_term`'s form.
TermReader = Callable[["Game", str, "CardState | None", int], int]


class _Term(NamedTuple):
    read: TermReader
    needs_source: bool


def _sourceless(count: NumberOf) -> _Term:
    return _Term(lambda game, controller, _source, _x: count(game, controller), False)


#: "the number of" / "the amount of", optional: a "for each" tail is the bare noun phrase.
_N = r"^(?:the )?(?:(?:number|amount) of )?"


def _norm(phrase: str) -> str:
    return " ".join(phrase.strip().rstrip(".").split())


# --------------------------------------------------------------------------
# Who "that player" names while a trigger resolves
# --------------------------------------------------------------------------


def _event_player(game: "Game") -> str | None:
    """The player the resolving trigger's event concerns (CR 603.2): "that
    player" of "At the beginning of enchanted player's upkeep ... that player"
    or "deals combat damage to a player ... that player controls"."""
    event = getattr(game.resolving, "event", None)
    return None if event is None else event.player


def _targeted_player(game: "Game", controller: str) -> str:
    """The first player the resolving object targets, else the controller."""
    from .ep02_r1_graveyard_counts import _referent_player

    return _referent_player(game, controller)


# --------------------------------------------------------------------------
# The players: life total, speed, opponents, players (CR 119.1, 702.179f, 102.1, 102.2)
# --------------------------------------------------------------------------

_PLAYERS_RE = re.compile(
    r"^(?:the )?number of (?:(?P<opponents>opponents)(?: you have)?|players)$", re.IGNORECASE
)
_OPPONENTS_WHO_CONTROL_RE = re.compile(
    r"^(?:the )?(?:number|amount) of opponents who control (?:an? |)(?P<what>.+)$", re.IGNORECASE
)


def _player_level(text: str) -> _Term | None:
    lowered = text.lower()
    if lowered == "your life total":
        return _sourceless(lambda game, controller: game.player(controller).life)
    if lowered == "your speed":
        # CR 702.179f: a player with no speed has speed 0 for an effect that refers to it.
        return _sourceless(lambda game, controller: game.player(controller).speed or 0)
    if (players := _PLAYERS_RE.fullmatch(text)) is not None:
        opponents_only = players.group("opponents") is not None
        return _sourceless(
            lambda game, controller: sum(
                1
                for player in game.players_in_game
                if not opponents_only or player.username != controller
            )
        )
    if "opponents who control" in lowered and (who := _OPPONENTS_WHO_CONTROL_RE.fullmatch(text)):
        return _opponents_who_control(who.group("what").strip())
    return None


def _opponents_who_control(what: str) -> _Term | None:
    """Each opponent who controls at least one permanent matching the description
    counts once (CR 102.2)."""
    from .targeting import permanent_description

    requirement = permanent_description(what)
    if requirement is None:
        return None

    def count(game: "Game", controller: str) -> int:
        board = game.computed_board()
        return sum(
            1
            for opponent in game.players_in_game
            if opponent.username != controller
            and any(
                board.of(permanent).controller == opponent.username
                and not requirement.rejects(permanent, controller, game)
                for permanent in game.battlefield
            )
        )

    return _sourceless(count)


# --------------------------------------------------------------------------
# The turn's history: died (CR 700.4), entered (CR 603.6a), discarded (CR 701.9a)
# --------------------------------------------------------------------------

_DIED_RE = re.compile(_N + r"(?P<what>.+?) that died this turn$", re.IGNORECASE)
_ENTERED_RE = re.compile(
    _N + r"(?P<what>.+?) that entered the battlefield under your control this turn$",
    re.IGNORECASE,
)
_DISCARDED_RE = re.compile(
    _N + r"cards? (?P<who>target opponent|target player|that player|an opponent"
    r"|each opponent|they) (?:has |have )?discarded this turn$",
    re.IGNORECASE,
)


def _ledger(text: str) -> _Term | None:
    """The turn ledger's "to_graveyard" (a creature that died, CR 700.4, whoever
    controlled it) or "entered" (under the controller's control, CR 603.6a)
    entries whose object, as it last existed (CR 603.10a), matches the
    description; one that has since left still counts. "Nontoken" is read off
    the entry's characteristics (CR 111.1)."""
    lowered = text.lower()
    if not lowered.endswith("this turn"):
        return None
    if (entered := _ENTERED_RE.fullmatch(text)) is not None:
        return _ledger_count("entered", entered.group("what"), yours_only=True)
    if (died := _DIED_RE.fullmatch(text)) is not None:
        return _ledger_count("to_graveyard", died.group("what"), yours_only=False)
    return None


def _ledger_count(kind: str, what: str, *, yours_only: bool) -> _Term | None:
    from .conditions.history import _quality

    token_filter = None
    words = [word for word in what.split() if word]
    for index, word in enumerate(words):
        if word.lower() in ("nontoken", "non-token"):
            token_filter, words = False, words[:index] + words[index + 1 :]
            break
    quality = _quality(" ".join(words))
    if quality is None:
        return None

    def count(game: "Game", controller: str) -> int:
        return sum(
            1
            for entry in game.turn_history
            if entry.kind == kind
            and (not yours_only or entry.player == controller)
            and quality(entry)
            and (
                token_filter is None
                or (entry.characteristics is not None)
                and entry.characteristics.is_token is token_filter
            )
        )

    return _sourceless(count)


def _cards_discarded_this_turn(text: str) -> _Term | None:
    """The cards a player other than "you" discarded this turn
    (`Game.cards_discarded_this_turn`, cycling counted: CR 702.29a), the
    player the printed words name; "each opponent" is the sum over them."""
    if (
        "discarded this turn" not in text.lower()
        or (match := _DISCARDED_RE.fullmatch(text)) is None
    ):
        return None
    who = match.group("who").lower()

    def count(game: "Game", controller: str) -> int:
        ledger = game.cards_discarded_this_turn
        if who in ("each opponent", "an opponent"):
            return sum(
                ledger.get(p.username, 0) for p in game.players_in_game if p.username != controller
            )
        if who in ("that player", "they"):
            return ledger.get(_event_player(game) or controller, 0)
        return ledger.get(_targeted_player(game, controller), 0)

    return _sourceless(count)


# --------------------------------------------------------------------------
# The board: distinct mana values (CR 202.3), names (CR 201.2), unlocked doors (CR 709.5c)
# --------------------------------------------------------------------------

_DIFFERENT_MV_RE = re.compile(
    _N + r"different mana values? among (?P<quality>[a-z][a-z ,'-]*?) you control$",
    re.IGNORECASE,
)
_DIFFERENTLY_NAMED_RE = re.compile(
    r"^(?:the )?(?:number|amount) of differently named creature tokens? you control$",
    re.IGNORECASE,
)
_UNLOCKED_DOORS_RE = re.compile(
    r"^(?:the )?(?:number|amount) of unlocked doors among Rooms you control$", re.IGNORECASE
)


def _board(text: str) -> _Term | None:
    lowered = text.lower()
    if "different mana value" in lowered and (mv := _DIFFERENT_MV_RE.fullmatch(text)):
        return _different_mana_values(mv.group("quality"))
    if "differently named" in lowered and _DIFFERENTLY_NAMED_RE.fullmatch(text):
        return _sourceless(_differently_named_tokens)
    if "unlocked doors" in lowered and _UNLOCKED_DOORS_RE.fullmatch(text):
        return _sourceless(_unlocked_doors)
    return None


def _different_mana_values(description: str) -> _Term | None:
    """How many distinct mana values the permanents of a description the
    controller controls have, off the computed board (CR 613.5); a permanent
    with no mana cost is mana value 0 (CR 202.3a)."""
    from ..models.game import _permanent_quality

    quality = _permanent_quality(description)
    if quality is None:
        return None

    def count(game: "Game", controller: str) -> int:
        board = game.computed_board()
        return len(
            {
                int(chars.mana_value)
                for permanent in game.battlefield
                if (chars := board.of(permanent)).controller == controller and quality(chars)
            }
        )

    return _sourceless(count)


def _differently_named_tokens(game: "Game", controller: str) -> int:
    board = game.computed_board()
    return len(
        {
            chars.name
            for permanent in game.battlefield
            if (chars := board.of(permanent)).controller == controller
            and chars.is_token
            and Type.CREATURE in chars.types
        }
    )


def _unlocked_doors(game: "Game", controller: str) -> int:
    """CR 709.5c: each half of a Room permanent you control that is unlocked."""
    board = game.computed_board()
    return sum(
        len(permanent.unlocked_doors)
        for permanent in game.battlefield
        if board.of(permanent).controller == controller
        and "room" in {subtype.lower() for subtype in board.of(permanent).subtypes}
    )


# --------------------------------------------------------------------------
# A cast record: times kicked (CR 702.33d), mana spent (CR 601.2h)
# --------------------------------------------------------------------------

_TIMES_KICKED_RE = re.compile(
    _N + r"times? (?P<whose>it|this (?:creature|permanent|artifact|enchantment|spell)|that spell) "
    r"was kicked$",
    re.IGNORECASE,
)
_MANA_SPENT_THAT_SPELL_RE = re.compile(
    r"^(?:the )?(?:number|amount) of mana spent to cast (?:that|the) spell$", re.IGNORECASE
)


def _triggering_spell_record(game: "Game") -> Any:
    """The cast record of the spell a resolving cast trigger names, kept for a
    spell that has since resolved or been countered (CR 608.2h)."""
    event = getattr(game.resolving, "event", None)
    if event is None or event.subject_id is None:
        return None
    spell = game.find_by_id(event.subject_id)
    record = game.cast_record_of(spell) if isinstance(spell, CardState) else None
    if record is None and event.subject_stamp is not None:
        record = game.cast_record_as_last_known(event.subject_stamp)
    return record


def _cast_record(text: str) -> _Term | None:
    """ "time it was kicked" / "the number of times this creature was kicked":
    CR 702.33d's count off the cast record of the spell the source was (an
    ability of the permanent reads it, CR 400.7d), none when it was never cast;
    "... that spell was kicked" and "the amount of mana spent to cast that
    spell" (CR 601.2h) read the spell a cast trigger names."""
    lowered = text.lower()
    if "kicked" in lowered and (kicked := _TIMES_KICKED_RE.fullmatch(text)) is not None:
        if kicked.group("whose").lower() == "that spell":
            return _sourceless(
                lambda game, _controller: getattr(_triggering_spell_record(game), "kicked", 0)
            )

        def times_kicked(game: "Game", _controller: str, source: CardState | None, _x: int) -> int:
            record = None if source is None else game.cast_record_of(source)
            return 0 if record is None else record.kicked

        return _Term(times_kicked, True)
    if "mana spent" in lowered and _MANA_SPENT_THAT_SPELL_RE.fullmatch(text):
        return _sourceless(
            lambda game, _controller: getattr(_triggering_spell_record(game), "total_mana_spent", 0)
        )
    return None


# --------------------------------------------------------------------------
# What is attached to an object or a player (CR 301.5a, CR 303.4m)
# --------------------------------------------------------------------------

_ATTACHED_RE = re.compile(
    _N + r"(?P<kinds>[a-z ,/]+?)(?P<past> you controlled that (?:was|were))? attached to "
    r"(?P<host>.+)$",
    re.IGNORECASE,
)
_KIND_SPLIT_RE = re.compile(
    r"\s*(?:,\s*(?:and/or\s+|or\s+|and\s+)?|\s+and/or\s+|\s+or\s+|\s+and\s+)", re.IGNORECASE
)
#: The player words of a host: "them" is the player the count is asked for.
_PLAYER_HOSTS = ("them", "that player", "you", "enchanted player")
_OBJECT_HOST_RE = re.compile(r"^(?:it|him|her|this [a-z]+|[A-Z][\w',-]*(?: [A-Z][\w',-]*)*)$")


class Attached(NamedTuple):
    """A parsed "<subtypes> [you controlled that was] attached to <host>"."""

    subtypes: tuple[str, ...]
    """The subtypes counted, lowercased and singular ("aura", "equipment", "curse")."""
    host: str
    """The host words as printed ("it", "this creature", "Kellan", "that player")."""
    past: bool
    """ "you controlled that was attached to it": the attachments the host had as it
    last existed (CR 603.10a)."""


def attached_phrase(text: str) -> Attached | None:
    """The one reading of the attached-count wording, shared by the static pump's
    layer `Count` (`ep02_r3_static_pumps`) and the resolution-time reader below.
    `None` unless every counted word is a subtype (Aura, Equipment, Curse, ...)."""
    from ..data.subtypes import subtype_vocabulary

    match = _ATTACHED_RE.fullmatch(_norm(text))
    if match is None:
        return None
    words = [word.lower() for word in _KIND_SPLIT_RE.split(match.group("kinds").strip()) if word]
    vocabulary = subtype_vocabulary()
    subtypes = []
    for word in words:
        singular = word if word in vocabulary else word.removesuffix("s")
        if singular not in vocabulary:
            return None
        subtypes.append(singular)
    if not subtypes:
        return None
    return Attached(tuple(sorted(set(subtypes))), match.group("host").strip(), bool(match["past"]))


def _attached(text: str) -> _Term | None:
    """How many permanents with one of the subtypes are attached to the host:
    the object the ability is on (CR 301.5a), a player an Aura enchants
    (CR 303.4m), or - "you controlled that was attached to it" - the dying
    permanent as it last existed (CR 603.10a), `CardState.last_known_attachments`."""
    if " attached to " not in text.lower() or (phrase := attached_phrase(text)) is None:
        return None
    wanted = set(phrase.subtypes)
    host = phrase.host

    def matches(subtypes: Any) -> bool:
        return any(subtype.lower() in wanted for subtype in subtypes)

    if phrase.past:
        if host.lower() != "it":
            return None

        def had(game: "Game", controller: str) -> int:
            event = getattr(game.resolving, "event", None)
            dead = (
                None
                if event is None or event.subject_id is None
                else game.find_by_id(event.subject_id)
            )
            if not isinstance(dead, CardState):
                return 0
            return sum(
                1
                for snapshot in dead.last_known_attachments
                if snapshot.controller == controller and matches(snapshot.subtypes)
            )

        return _sourceless(had)
    if host.lower() in _PLAYER_HOSTS:
        that_player = host.lower() == "that player"

        def on_player(game: "Game", controller: str) -> int:
            player = (_event_player(game) or controller) if that_player else controller
            board = game.computed_board()
            return sum(
                1
                for permanent in game.battlefield
                if permanent.attachment is not None
                and permanent.attachment.username == player
                and matches(board.of(permanent).subtypes)
            )

        return _sourceless(on_player)
    if _OBJECT_HOST_RE.fullmatch(host) is None:
        return None

    def on_object(game: "Game", _controller: str, source: CardState | None, _x: int) -> int:
        if source is None:
            return 0
        board = game.computed_board()
        return sum(
            1
            for permanent in game.battlefield
            if permanent.attached_to == source.id and matches(board.of(permanent).subtypes)
        )

    return _Term(on_object, True)


# --------------------------------------------------------------------------
# Mana symbols in a sacrificed card's cost (CR 107.4e), other attackers (CR 508.4)
# --------------------------------------------------------------------------

_SACRIFICED_SYMBOLS_RE = re.compile(
    _N + r"(?P<color>white|blue|black|red|green) mana symbols? in "
    r"the sacrificed (?:creature|permanent)'s mana cost$",
    re.IGNORECASE,
)
_OTHER_ATTACKERS_RE = re.compile(
    r"^(?:the )?(?:number|amount) of other attacking creatures$", re.IGNORECASE
)


def _mana_symbols_in_sacrificed_cost(text: str) -> _Term | None:
    """How many mana symbols of one color the mana cost of what the resolving
    object's cost sacrificed has (Fiery Bombardment's Chroma ability). A
    hybrid symbol is also a symbol of each of its colors (CR 107.4e). The
    sacrificed card is read where the cost left it (CR 608.2h); a token has no
    mana cost to count."""
    if "mana cost" not in text.lower() or (match := _SACRIFICED_SYMBOLS_RE.fullmatch(text)) is None:
        return None
    from ..models.card import Color
    from ..models.mana import ManaCost

    color = Color[match.group("color").upper()]

    def count(game: "Game", _controller: str) -> int:
        resolving = game.resolving
        ids = getattr(resolving, "cost_sacrificed_card_ids", ())
        if not ids and isinstance(resolving, CardState):
            record = game.cast_record_of(resolving)
            ids = tuple(record.additional_cost_cards) if record is not None else ()
        total = 0
        for card_id in ids[:1]:
            card = game.find_by_id(card_id)
            if card is not None and card.mana_cost:
                total += sum(
                    1 for symbol in ManaCost.parse(card.mana_cost).symbols if color in symbol.colors
                )
        return total

    return _sourceless(count)


def _other_attackers(text: str) -> _Term | None:
    """Every attacking creature but the source (CR 508.4: a creature put onto
    the battlefield attacking is one as well)."""
    if "other attacking" not in text.lower() or _OTHER_ATTACKERS_RE.fullmatch(text) is None:
        return None

    def count(game: "Game", _controller: str, source: CardState | None, _x: int) -> int:
        found = (game.find_by_id(attack.attacker_id) for attack in game.combat.attacks)
        return sum(
            1
            for creature in found
            if isinstance(creature, CardState)
            and creature.zone is Zone.BATTLEFIELD
            and (source is None or creature.id != source.id)
        )

    return _Term(count, True)


_TERMS = (
    _player_level,
    _ledger,
    _cards_discarded_this_turn,
    _board,
    _cast_record,
    _attached,
    _mana_symbols_in_sacrificed_cost,
    _other_attackers,
)


@cache
def _term(phrase: str) -> _Term | None:
    text = _norm(phrase)
    for reader in _TERMS:
        if (term := reader(text)) is not None:
            return term
    return None


@cache
def count_term(phrase: str) -> NumberOf | None:
    """The count of "the number of <phrase>" / "equal to <phrase>" that needs no
    source object, or `None`."""
    term = _term(phrase)
    if term is None or term.needs_source:
        return None
    read = term.read
    return lambda game, controller: read(game, controller, None, 0)


@cache
def amount_term(phrase: str) -> TermReader | None:
    """One `amounts.amount_expression` term this module reads, or `None`."""
    term = _term(phrase)
    return None if term is None else term.read


# --------------------------------------------------------------------------
# "for each <phrase>"
# --------------------------------------------------------------------------

_EACH_PLAYER_RE = re.compile(r"^players?$", re.IGNORECASE)
_ATTACKING_YOU_RE = re.compile(r"^creatures? attacking you$", re.IGNORECASE)
_THAT_PLAYER_CONTROLS_RE = re.compile(r"^(?P<what>.+?) that player controls$", re.IGNORECASE)


def _for_each_only(text: str) -> ForEach | None:
    """The wordings only a "for each" tail prints: "player" (CR 102.1), "creature
    attacking you" (CR 506.2: the attacks whose defender is the controller, not a
    planeswalker or battle they control) and "<quality> that player controls"
    (the trigger event's player, CR 603.2)."""
    lowered = text.lower()
    if _EACH_PLAYER_RE.fullmatch(text):
        return lambda game, _controller, _source: len(game.players_in_game)
    if "attacking you" in lowered and _ATTACKING_YOU_RE.fullmatch(text):
        return lambda game, controller, _source: sum(
            1
            for attack in game.combat.attacks
            if attack.defender.username == controller and attack.defender.card_id is None
        )
    if "that player controls" in lowered and (match := _THAT_PLAYER_CONTROLS_RE.fullmatch(text)):
        from .effects.amounts import _for_each_multiplier

        counted = _for_each_multiplier(f"{match.group('what')} you control")
        if counted is None:
            return None

        def controlled_by_that_player(game: "Game", _controller: str, source: str | None) -> int:
            player = _event_player(game)
            return 0 if player is None else counted(game, player, source)

        return controlled_by_that_player
    return None


@cache
def for_each_count(phrase: str) -> ForEach | None:
    """The count of a "for each <phrase>" tail: a for-each-only wording, else the
    phrase as "the number of <phrase>" with the ability's source as the object."""
    text = _norm(phrase)
    if (each := _for_each_only(text)) is not None:
        return each
    from .effects.amounts import amount_expression

    reader = amount_expression(f"the number of {text}")
    if reader is None:
        return None

    def count(game: "Game", controller: str, source_id: str | None) -> int:
        found = None if source_id is None else game.find_by_id(UUID(str(source_id)))
        source = found if isinstance(found, CardState) else None
        return int(reader(game, controller, source, 0))

    return count


# --------------------------------------------------------------------------
# "any number of target players other than that player each draw cards equal to ..."
# --------------------------------------------------------------------------

_PLAYERS_EACH_DRAW_RE = re.compile(
    rf"^(?P<players>any number of|up to {COUNT}|{COUNT}) target players"
    r"(?P<other> other than that player)? each draws? cards equal to (?P<expr>.+)$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_target_players_each_draw_equal_clause(clause: str, *, for_spell: bool) -> Any:
    """ "Any number of target players other than that player each draw cards
    equal to the number of Curses attached to that player." (Curse of
    Surveillance): each chosen player draws the one amount, counted once as the
    ability resolves (CR 608.2h) - for the controller (CR 109.5), whose "that
    player" is the enchanted player of the trigger's event. A target no longer
    legal draws nothing (CR 608.2b); "any number" may choose no one (CR 107.1c).
    """
    text = " ".join(clause.split()).rstrip(".")
    if " each draw" not in text.lower() or "target players" not in text.lower():
        return None
    match = _PLAYERS_EACH_DRAW_RE.fullmatch(text)
    if match is None:
        return None
    from .effects._common import _targets_understood
    from .effects.amounts import count_expression

    phrase = f"{match.group('players')} target players{match.group('other') or ''}"
    if not _targets_understood(phrase, allow_player_targets=True, count_agnostic=True):
        return None
    amount_of = count_expression(match.group("expr"))
    if amount_of is None:
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        amount = amount_of(game, game.controller_of(stack_object).username)
        for target in game.resolve_targets(stack_object):
            if isinstance(target, Player) and amount > 0:
                game.draw_cards(target.username, amount)

    return effect


# --------------------------------------------------------------------------
# "<verb> target X if its mana value is less than or equal to the number of <Y>"
# --------------------------------------------------------------------------

_IF_MV_AT_MOST_COUNT = r"if its mana value is less than or equal to (?P<expr>the number of [^.]+)"
_DESTROY_IF_MV_RE = re.compile(
    rf"^destroy (?P<phrase>target [^.]+?) {_IF_MV_AT_MOST_COUNT}$", re.IGNORECASE
)
_PUT_ONTO_BATTLEFIELD_IF_MV_RE = re.compile(
    r"^put (?P<phrase>target [^.]+? card from [^.]+?graveyard) onto the battlefield"
    rf"(?P<yours> under your control)? {_IF_MV_AT_MOST_COUNT}$",
    re.IGNORECASE,
)


def _target_within_count(
    match: "re.Match[str]", *, battlefield_only: bool
) -> tuple[Callable[["Game", str], int], str] | None:
    """The count and the target phrase of a `_IF_MV_AT_MOST_COUNT` clause, or
    `None` when either is not one the engine reads."""
    from .effects._common import _targets_understood
    from .effects.amounts import count_expression

    phrase = match.group("phrase")
    counted = count_expression(match.group("expr"))
    if counted is None or not _targets_understood(phrase, battlefield_only=battlefield_only):
        return None
    return counted, phrase


def _targets_within_count(game: "Game", stack_object: Any, counted: Callable[..., int]) -> list:
    """The resolving object's legal card targets (CR 608.2b) whose mana value
    (CR 202.3) is within the count, taken once as the instruction is followed
    (CR 608.2c, CR 608.2h)."""
    limit = counted(game, game.controller_of(stack_object).username)
    return [
        target
        for target in game.resolve_targets(stack_object)
        if isinstance(target, CardState) and game.characteristics_of(target).mana_value <= limit
    ]


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_destroy_target_if_mana_value_within_count(clause: str, *, for_spell: bool) -> Any:
    """ "Destroy target artifact or enchantment if its mana value is less than
    or equal to the number of cards in your hand." (Rending Vines): the target
    is any artifact or enchantment (CR 115.1); the "if" gates the destruction
    (CR 701.8a) as it is followed, so a permanent above the count is left
    alone."""
    if " if its mana value is less than or equal to the number of " not in clause.lower():
        return None
    match = _DESTROY_IF_MV_RE.fullmatch(" ".join(clause.split()).rstrip("."))
    read = None if match is None else _target_within_count(match, battlefield_only=True)
    if read is None:
        return None
    counted, _phrase = read

    def effect(game: "Game", stack_object: Any) -> None:
        for target in _targets_within_count(game, stack_object, counted):
            if target.zone is Zone.BATTLEFIELD:
                game.destroy(target)

    return effect


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_put_graveyard_card_if_mana_value_within_count(clause: str, *, for_spell: bool) -> Any:
    """ "Put target creature card from an opponent's graveyard onto the
    battlefield under your control if its mana value is less than or equal to
    the number of Allies you control." (Agadeem Occultist): the card enters
    under the controller's control when the printed words say so (CR 110.2a),
    else under its owner's."""
    if " if its mana value is less than or equal to the number of " not in clause.lower():
        return None
    match = _PUT_ONTO_BATTLEFIELD_IF_MV_RE.fullmatch(" ".join(clause.split()).rstrip("."))
    read = None if match is None else _target_within_count(match, battlefield_only=False)
    if read is None:
        return None
    counted, _phrase = read
    yours = match.group("yours") is not None

    def effect(game: "Game", stack_object: Any) -> None:
        controller = game.controller_of(stack_object).username
        for target in _targets_within_count(game, stack_object, counted):
            if target.zone is Zone.GRAVEYARD:
                game.put_onto_battlefield(target, controller if yours else target.owner)

    return effect


_RETURN_TO_BATTLEFIELD_FRONTED_RE = re.compile(
    r"^(?:[a-z][a-z '-]* — |[a-z][a-z '-]* - )?return to the battlefield "
    r"(?P<phrase>target [^.]+? card in your graveyard(?: with [^.]+)?)$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_return_to_the_battlefield_target_in_your_graveyard(
    clause: str, *, for_spell: bool
) -> Any:
    """ "Return to the battlefield target nonland permanent card in your
    graveyard with mana value less than or equal to the number of permanent
    cards in your graveyard." (Squirming Emergence): `_RETURN_FROM_YOUR_
    GRAVEYARD_TO_BATTLEFIELD_RE`'s verb with the destination fronted. The mana
    value bound is a targeting restriction (CR 115.1, CR 601.2c) that
    `targeting.py` enforces, and is checked again as the spell resolves (CR
    608.2b); the card returns under its owner's control (CR 110.2)."""
    match = _RETURN_TO_BATTLEFIELD_FRONTED_RE.fullmatch(" ".join(clause.split()).rstrip("."))
    if match is None:
        return None
    from .effects._common import _targets_understood

    if not _targets_understood(match.group("phrase"), battlefield_only=False):
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState) and target.zone is Zone.GRAVEYARD:
                game.put_onto_battlefield(target, target.owner)

    return effect


# --------------------------------------------------------------------------
# One-shot "gets +P/+T until end of turn" over a count taken as it applies
# --------------------------------------------------------------------------


def _pump_until_end_of_turn(
    game: "Game", stack_object: Any, subject: CardState, power: int, toughness: int
) -> None:
    """A CR 611.2 one-shot effect: `subject` (this incarnation of it only, CR
    400.7) gets `power`/`toughness` until end of turn, in layer 7c (CR 613.4c,
    so it adds to any other pump)."""
    from .effects.continuous import continuous_effects
    from .layers import (
        ContinuousEffect,
        Duration,
        Layer,
        Sublayer,
        modify_power_toughness,
        only_this_incarnation,
    )

    if subject.zone is not Zone.BATTLEFIELD or (power == 0 and toughness == 0):
        return
    store = continuous_effects(game)
    store.add(
        ContinuousEffect(
            description=f"{subject.name}: gets {power:+d}/{toughness:+d} until end of turn",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.MODIFY,
            timestamp=store.tick(),
            duration=Duration.UNTIL_END_OF_TURN,
            source_id=getattr(stack_object, "source_id", None),
            selector=only_this_incarnation(subject, subject.zone_change_stamp),
            modification=modify_power_toughness(power, toughness),
        )
    )


# --------------------------------------------------------------------------
# "it gets +1/+0 until end of turn for each other attacking creature that shares
# a creature type with it" (Shared Animosity, CR 508.1, CR 205.3m)
# --------------------------------------------------------------------------

_ATTACKER_SHARING_PUMP_RE = re.compile(
    r"^it gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) until end of turn for each other "
    r"attacking creature that shares a creature type with it$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_attacker_pump_per_other_attacker_sharing_a_type(clause: str, *, for_spell: bool) -> Any:
    """Shared Animosity: "Whenever a creature you control attacks, it gets
    +1/+0 until end of turn for each other attacking creature that shares a
    creature type with it." "It" is the creature the trigger's event names
    (CR 603.2); the other attackers are counted once as the ability resolves
    (CR 608.2h), a changeling sharing every type (CR 702.73a)."""
    match = _ATTACKER_SHARING_PUMP_RE.fullmatch(" ".join(clause.split()).rstrip("."))
    if match is None:
        return None
    power = int(match.group("power"))
    toughness = int(match.group("toughness"))

    def effect(game: "Game", stack_object: Any) -> None:
        from .targeting import _creature_types_overlap, _shareable_creature_types

        event = getattr(stack_object, "event", None)
        subject = (
            None if event is None or event.subject_id is None else game.find_by_id(event.subject_id)
        )
        if not isinstance(subject, CardState) or subject.zone is not Zone.BATTLEFIELD:
            return
        own = _shareable_creature_types(subject, game)
        if own is None:
            return
        count = 0
        for other in game.attacking_creatures():
            if other.id == subject.id:
                continue
            types = _shareable_creature_types(other, game)
            if types is not None and _creature_types_overlap(own, types):
                count += 1
        _pump_until_end_of_turn(game, stack_object, subject, power * count, toughness * count)

    return effect


# --------------------------------------------------------------------------
# "<source> deals damage to each of those creatures equal to the number of
# attacking creatures" (Lightmine Field, CR 120.3, CR 508.1)
# --------------------------------------------------------------------------

_DAMAGE_EACH_OF_THOSE_ATTACKERS_RE = re.compile(
    r"^(?P<source>this [a-z]+) deals damage to each of those creatures equal to "
    r"(?P<expr>the number of attacking creatures)$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_damage_to_each_batched_attacker_by_attacker_count(
    clause: str, *, for_spell: bool
) -> Any:
    """Lightmine Field: "Whenever one or more creatures attack, this
    enchantment deals damage to each of those creatures equal to the number of
    attacking creatures." "Those creatures" are the attackers the trigger's
    own condition counts (CR 508.3d); the amount is taken once (CR 608.2h) and
    dealt by the source to each at the same time (CR 120.1)."""
    match = _DAMAGE_EACH_OF_THOSE_ATTACKERS_RE.fullmatch(" ".join(clause.split()).rstrip("."))
    if match is None or for_spell:
        return None
    from .effects.amounts import count_expression

    counted = count_expression(match.group("expr"))
    if counted is None:
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        from .effects.damage import _deal_all, _resolving_source
        from .triggers.collect import batched_attackers

        source = _resolving_source(game, stack_object)
        ability = getattr(stack_object, "ability", None)
        if source is None or ability is None:
            return
        controller = game.controller_of(stack_object).username
        attackers = batched_attackers(game, ability.condition, controller)
        if not attackers:
            return
        amount = counted(game, controller)
        _deal_all(game, [(source, attacker, amount) for attacker in attackers])

    return effect


# --------------------------------------------------------------------------
# "Target creature gets -2/-2 until end of turn. It gets an additional -1/-1
# until end of turn for each Desert you control." (Desert's Due, CR 613.4c)
# --------------------------------------------------------------------------

_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=\.)\s+(?=[A-Z])|\n+")
_ADDITIONAL_PUMP_FOR_EACH_RE = re.compile(
    r"^(?:it|that creature) gets an additional (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) "
    r"until end of turn for each (?P<each>.+?)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_target_pump_then_additional_pump_for_each(text: str, *, for_spell: bool) -> Any:
    """A pump sentence, then "It gets an additional P/T until end of turn for
    each <thing>": "it" is the creature the first sentence pumped. The first
    sentence is read by the ordinary clause reader; the second is a second
    layer 7c modification (CR 613.4c, "an additional" names no new rule) whose
    count is taken once as it applies (CR 608.2h). A target no longer legal
    (CR 608.2b) gets neither."""
    sentences = [part for part in _SENTENCE_BOUNDARY_RE.split(text.strip()) if part.strip()]
    if len(sentences) != 2 or " an additional " not in sentences[1].lower():
        return None
    match = _ADDITIONAL_PUMP_FOR_EACH_RE.fullmatch(sentences[1].strip())
    if match is None:
        return None
    from .effects.amounts import _for_each_multiplier
    from .effects.dispatch import _parse_mixed_clauses

    multiplier = _for_each_multiplier(match.group("each"))
    first = _parse_mixed_clauses(sentences[0], for_spell=for_spell)
    if multiplier is None or first is None:
        return None
    power = int(match.group("power"))
    toughness = int(match.group("toughness"))

    def effect(game: "Game", stack_object: Any) -> None:
        for clause in first:
            clause(game, stack_object)
            game.announce_batched_events()  # CR 603.2c: one event per instruction
        count = multiplier(game, game.controller_of(stack_object).username, None)
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState):
                _pump_until_end_of_turn(
                    game, stack_object, target, power * count, toughness * count
                )

    return [effect]


# --------------------------------------------------------------------------
# "Target player creates X 2/2 black Zombie creature tokens, then up to one
# target creature gets -1/-1 until end of turn for each Zombie that player
# controls." (Dark Salvation, CR 111.2, CR 608.2c)
# --------------------------------------------------------------------------

_PLAYER_TOKENS_THEN_PUMP_RE = re.compile(
    rf"^(?P<who>target player) creates (?P<n>x|\d+|{COUNT}) (?P<desc>.+?) tokens?, "
    r"then (?P<victim>up to one target creature) gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) "
    r"until end of turn for each (?P<each>[A-Za-z]+) that player controls$",
    re.IGNORECASE,
)


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_player_creates_tokens_then_pump_per_their_kind(text: str, *, for_spell: bool) -> Any:
    """Dark Salvation. The player target creates the tokens and controls them
    (CR 111.2); the creature target - the second target in the text's order
    (CR 601.2c) - then gets the pump, counted once, after the tokens exist, on
    that player's board (CR 608.2c, CR 608.2h). No creature chosen ("up to
    one", CR 115.6) is a legal announcement that only makes the tokens."""
    match = _PLAYER_TOKENS_THEN_PUMP_RE.fullmatch(" ".join(text.split()).rstrip("."))
    if match is None:
        return None
    from .effects._common import _targets_understood
    from .effects.amounts import count_expression
    from .effects.tokens import _token_definition_from_words

    if not _targets_understood(match.group("who"), allow_player_targets=True):
        return None
    if not _targets_understood(match.group("victim"), count_agnostic=True):
        return None
    definition = _token_definition_from_words(match.group("desc"), None)
    counted = count_expression(f"the number of {match.group('each')}s you control")
    if definition is None or counted is None:
        return None
    x_count = match.group("n").lower() == "x"
    fixed = None if x_count else parse_count(match.group("n"))
    if not x_count and fixed is None:
        return None
    power = int(match.group("power"))
    toughness = int(match.group("toughness"))

    def effect(game: "Game", stack_object: Any) -> None:
        from ..models.token import create_tokens
        from .effects.damage import _announced_x

        players = [t for t in game.resolve_targets(stack_object) if isinstance(t, Player)]
        if not players:
            return
        player = players[0]
        amount = _announced_x(game, stack_object) if x_count else fixed
        if amount:
            create_tokens(game, definition, player.username, amount)
        count = counted(game, player.username)
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState):
                _pump_until_end_of_turn(
                    game, stack_object, target, power * count, toughness * count
                )

    return [effect]


# --------------------------------------------------------------------------
# "Draw a card for each creature target player controls, then draw a card for each
# creature another target player controls." (Biomantic Mastery, CR 608.2c)
# --------------------------------------------------------------------------

_DRAW_FOR_EACH_TARGET_PLAYERS_RE = re.compile(
    r"^draw a card for each (?P<first>[a-z][a-z ]*?) (?P<one>target player) controls, "
    r"then draw a card for each (?P<second>[a-z][a-z ]*?) "
    r"(?P<other>another target player) controls$",
    re.IGNORECASE,
)


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_draw_for_each_thing_two_target_players_control(text: str, *, for_spell: bool) -> Any:
    """Biomantic Mastery. Two different player targets (CR 115.3: "another"),
    in the order the text names them (CR 601.2c). The controller draws, one
    card for each thing the first player controls, then one for each thing the
    second controls - each count taken as that draw is performed (CR 608.2c,
    CR 608.2h). A player no longer a legal target contributes nothing (CR
    608.2b)."""
    match = _DRAW_FOR_EACH_TARGET_PLAYERS_RE.fullmatch(" ".join(text.split()).rstrip("."))
    if match is None:
        return None
    from .effects._common import _targets_understood
    from .effects.amounts import count_expression

    if not (
        _targets_understood("target player", allow_player_targets=True)
        and _targets_understood("another target player", allow_player_targets=True)
    ):
        return None
    counts = [
        count_expression(f"the number of {match.group(group)}s you control")
        for group in ("first", "second")
    ]
    if any(counted is None for counted in counts):
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        drawer = game.controller_of(stack_object).username
        for counted, reference in zip(counts, stack_object.targets, strict=False):
            player = game.legal_target(stack_object, reference)
            if isinstance(player, Player):
                game.draw_cards(drawer, counted(game, player.username))
                game.announce_batched_events()  # CR 603.2c: one event per instruction

    return [effect]


# --------------------------------------------------------------------------
# "For each attacking creature, its owner puts it on their choice of the top or
# bottom of their library." (Aetherspouts, CR 401.1, CR 608.2d)
# --------------------------------------------------------------------------

_FOR_EACH_OWNER_PUTS_IT_RE = re.compile(
    r"^for each (?P<what>[a-z][a-z ]*?), its owner puts it on their choice of the top or "
    r"bottom of their library$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_for_each_permanent_its_owner_puts_it_top_or_bottom(
    clause: str, *, for_spell: bool
) -> Any:
    """Aetherspouts. The group is fixed as the instruction begins (CR 608.2f);
    each one's owner - not the controller - makes their own top-or-bottom
    choice for it (CR 108.3, CR 608.2d), and it moves from the battlefield to
    that library (CR 401.1)."""
    match = _FOR_EACH_OWNER_PUTS_IT_RE.fullmatch(" ".join(clause.split()).rstrip("."))
    if match is None:
        return None
    from .targeting import permanent_description

    requirement = permanent_description(match.group("what"))
    if requirement is None:
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        from .decisions import Decision, DecisionKind, source_id_of

        controller = game.controller_of(stack_object).username
        source = stack_object.name if for_spell else stack_object.source_name
        group = [
            permanent
            for permanent in list(game.battlefield)
            if requirement.rejects(permanent, controller, game) is None
        ]
        for permanent in group:
            if permanent.zone is not Zone.BATTLEFIELD or permanent.owner is None:
                continue
            top = game.ask(
                Decision(
                    kind=DecisionKind.PUT_ON_TOP_OR_BOTTOM,
                    player=permanent.owner,
                    prompt=(
                        f"put {permanent.name} on the top or bottom of {permanent.owner}'s library"
                    ),
                    source=source,
                    source_id=source_id_of(stack_object),
                )
            )
            assert isinstance(top, bool)
            game.put_cards_into_library([permanent], to_bottom=not top)

    return effect


# --------------------------------------------------------------------------
# "for each opponent, put up to one target <X> that player controls into its
# owner's library third from the top" (Riptide Gearhulk, CR 401.1, CR 115.6)
# --------------------------------------------------------------------------

_FOR_EACH_OPPONENT_TO_LIBRARY_RE = re.compile(
    rf"^for each opponent, put up to one target (?P<desc>.+?) that player controls into its "
    rf"owner'?s library (?P<ordinal>{ORDINAL}) from the top$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_for_each_opponent_put_into_library_nth_from_top(clause: str, *, for_spell: bool) -> Any:
    """Riptide Gearhulk. One optional target per opponent (the profile is
    `targeting._for_each_opponent_profile`'s); each permanent still on the
    battlefield goes into its *owner's* library at the printed depth (CR 401.1;
    CR 609.3: a library shorter than that takes it as deep as it goes)."""
    match = _FOR_EACH_OPPONENT_TO_LIBRARY_RE.fullmatch(" ".join(clause.split()).rstrip("."))
    if match is None:
        return None
    from .effects._common import _targets_understood
    from .effects.continuous import _for_each_opponent_target_phrase
    from .effects.returns import _reposition_in_owners_library

    depth = parse_ordinal(match.group("ordinal"))
    phrase = _for_each_opponent_target_phrase(match.group("desc"))
    if depth is None or not _targets_understood(phrase, count_agnostic=True):
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                moved = game.put_cards_into_library([target])
                for card in moved:
                    _reposition_in_owners_library(game, card, depth=depth - 1)

    return effect


# --------------------------------------------------------------------------
# "for each opponent, you may put up to one target creature card from that
# player's graveyard onto the battlefield under your control" (Sepulchral
# Primordial, CR 110.2a, CR 608.2d)
# --------------------------------------------------------------------------

_FOR_EACH_OPPONENT_REANIMATE_RE = re.compile(
    r"^for each opponent, you may put up to one target (?P<desc>.+?) from that player'?s "
    r"graveyard onto the battlefield under your control$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_for_each_opponent_may_reanimate_from_their_graveyard(
    clause: str, *, for_spell: bool
) -> Any:
    """Sepulchral Primordial. One optional target per opponent, a card in
    that opponent's graveyard (`targeting._for_each_opponent_profile`); the
    controller chooses, for each, whether to put it onto the battlefield under
    their control (CR 608.2d, CR 110.2a). A card that has left the graveyard
    is no longer a legal target (CR 608.2b)."""
    match = _FOR_EACH_OPPONENT_REANIMATE_RE.fullmatch(" ".join(clause.split()).rstrip("."))
    if match is None:
        return None
    from .effects._common import _targets_understood

    if not _targets_understood(
        f"up to one target {match.group('desc')} from an opponent's graveyard",
        count_agnostic=True,
        battlefield_only=False,
    ):
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        from .decisions import source_id_of

        controller = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, CardState) or target.zone is not Zone.GRAVEYARD:
                continue
            if game.may(
                controller,
                f"put {target.name} onto the battlefield under your control",
                source=source,
                source_id=source_id_of(stack_object),
                cards=[target],
            ):
                game.put_onto_battlefield(target, controller.username)

    return effect


# --------------------------------------------------------------------------
# "Destroy up to three other target nonland permanents. For each of those
# permanents, its controller creates a 3/3 white Angel creature token with
# flying." (Soul of Emancipation, CR 701.8a, CR 111.2)
# --------------------------------------------------------------------------

_DESTROY_THEN_CONTROLLERS_CREATE_RE = re.compile(
    rf"^destroy (?P<phrase>up to (?:{COUNT}) other target [^.]+?)\. "
    r"for each of those (?:permanents|creatures), its controller creates "
    r"(?:an?|one) (?P<desc>.+?) tokens?(?: with (?P<tail>[^.]+))?\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_destroy_targets_then_each_controller_creates_a_token(
    text: str, *, for_spell: bool
) -> Any:
    """Soul of Emancipation. The destroyed permanents' controllers are read
    before they die (CR 608.2h last-known information: the permanents are gone
    afterwards), then each of them creates the token (CR 111.2). "Each of those
    permanents" is every legal target, one token per permanent whether or not
    destruction happened (an indestructible one is still one of those
    permanents)."""
    match = _DESTROY_THEN_CONTROLLERS_CREATE_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    from .effects._common import _targets_understood
    from .effects.tokens import _token_definition_from_words

    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    tail = match.group("tail")
    definition = _token_definition_from_words(match.group("desc"), tail.strip() if tail else None)
    if definition is None:
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        from ..models.token import create_tokens

        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        controllers = [game.controller_of(target).username for target in targets]
        for target in targets:
            if target.zone is Zone.BATTLEFIELD:
                game.destroy(target)
        game.announce_batched_events()  # CR 603.2c: one event per instruction
        for username in controllers:
            create_tokens(game, definition, username, 1)

    return [effect]


# --------------------------------------------------------------------------
# "For each planeswalker you control, you may activate one of its loyalty
# abilities once this turn as though none of its loyalty abilities have been
# activated this turn." (The Chain Veil, CR 606.3)
# --------------------------------------------------------------------------

_EXTRA_LOYALTY_ACTIVATION_RE = re.compile(
    r"^for each planeswalker you control, you may activate one of its loyalty abilities once "
    r"this turn as though none of its loyalty abilities have been activated this turn$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_each_planeswalker_may_activate_a_loyalty_ability_again(
    clause: str, *, for_spell: bool
) -> Any:
    """The Chain Veil. CR 606.3 allows one loyalty activation per planeswalker
    each turn, counted on `Game.loyalty_activations`; "as though none of its
    loyalty abilities have been activated this turn" frees exactly one more
    activation (the text says "once"), for each planeswalker the controller
    controls as the ability resolves (CR 608.2h). Nothing is written for a
    planeswalker whose limit is not used up, and the "may" is the controller's
    to leave unused - the permission costs nothing to hold."""
    if (
        for_spell
        or _EXTRA_LOYALTY_ACTIVATION_RE.fullmatch(" ".join(clause.split()).rstrip(".")) is None
    ):
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        from .equip_block_statics import loyalty_activation_limit

        controller = game.controller_of(stack_object).username
        for walker in game.permanents_controlled_by(controller):
            if Type.PLANESWALKER not in game.characteristics_of(walker).types:
                continue
            limit = max(
                game._loyalty_activations_allowed(walker),  # noqa: SLF001
                loyalty_activation_limit(game, controller),
            )
            key = str(walker.id)
            used = game.loyalty_activations.get(key, 0)
            game.loyalty_activations[key] = min(used, limit - 1)

    return effect
