"""EP-02 R3 T7: "for each <thing>" and "equal to the number of <things>" counts
that are not a permanent or card in a zone: a per-turn history, a cast record,
the Curses attached to a player, the distinct mana values on a board.

`for_each_cards_counts` is the one reader `amounts._for_each_multiplier` asks
first; `number_of_cards_counts` is the `(game, controller) -> int` twin
`amounts.count_expression` asks first. Both only chain the sub-readers listed
in `_FOR_EACH` / `_NUMBER_OF`, each a `functools.cache`d pure function of the
phrase that returns `None` for a phrase it does not read - so a phrase
travels the chain once and the answer is remembered (the classify budget).
"""

import re
from collections.abc import Callable
from functools import cache
from typing import TYPE_CHECKING
from uuid import UUID

from ..models.card_state import CardState
from ..models.player import Player

if TYPE_CHECKING:
    from ..models.game import Game

#: `(game, controller, source_id) -> int`: `amounts._for_each_multiplier`'s form.
ForEach = Callable[["Game", str, "str | None"], int]
#: `(game, controller) -> int`: `amounts.count_expression`'s form.
NumberOf = Callable[["Game", str], int]


_DIED_SUFFIX = " that died this turn"


def _died_this_turn_each(phrase: str) -> ForEach | None:
    """ "for each creature that died this turn" / "for each Zubera that died
    this turn": the same count as "the number of creatures that died this
    turn" (`amounts._COUNT_DIED_THIS_TURN_RE`, read off the turn's
    "to_graveyard" history, CR 700.4), taken once as the effect applies
    (CR 608.2h)."""
    if not phrase.lower().endswith(_DIED_SUFFIX):
        return None
    from .effects.amounts import count_expression

    head = phrase[: -len(_DIED_SUFFIX)]
    counted = count_expression(f"the number of {head}{_DIED_SUFFIX}") or count_expression(
        f"the number of {head}s{_DIED_SUFFIX}"
    )
    if counted is None:
        return None
    return lambda game, controller, _source_id: counted(game, controller)


# --------------------------------------------------------------------------
# Who "target opponent" / "that player" / "they" names while it resolves
# --------------------------------------------------------------------------


def _event_player(game: "Game", controller: str) -> str:
    """The player the resolving trigger's event concerns (CR 603.2): "that
    player" of "At the beginning of enchanted player's upkeep ... that player",
    else the controller (CR 109.5)."""
    event = getattr(game.resolving, "event", None)
    if event is not None and event.player is not None:
        return event.player
    return controller


def _targeted_player(game: "Game", controller: str) -> str:
    """The first player the resolving object targets, else the controller."""
    from .ep02_r1_graveyard_counts import _referent_player

    return _referent_player(game, controller)


# --------------------------------------------------------------------------
# "cards target opponent discarded this turn" (CR 701.9a)
# --------------------------------------------------------------------------

_DISCARDED_RE = re.compile(
    r"^(?:the )?(?:number of )?cards? (?P<who>target opponent|target player|that player|an opponent"
    r"|each opponent|they) (?:has |have )?discarded this turn$",
    re.IGNORECASE,
)


def _cards_discarded_this_turn(phrase: str) -> NumberOf | None:
    """The cards a player other than "you" discarded this turn
    (`Game.cards_discarded_this_turn`, cycling counted: CR 702.29a), the
    player the printed words name; "each opponent" is the sum over them."""
    if "discarded this turn" not in phrase.lower() or (
        match := _DISCARDED_RE.fullmatch(phrase)
    ) is None:
        return None
    who = match.group("who").lower()

    def count(game: "Game", controller: str) -> int:
        ledger = game.cards_discarded_this_turn
        if who in ("each opponent", "an opponent"):
            return sum(
                ledger.get(p.username, 0) for p in game.players_in_game if p.username != controller
            )
        if who in ("that player", "they"):
            return ledger.get(_event_player(game, controller), 0)
        return ledger.get(_targeted_player(game, controller), 0)

    return count


# --------------------------------------------------------------------------
# "Goblins that entered the battlefield under your control this turn"
# --------------------------------------------------------------------------

_ENTERED_RE = re.compile(
    r"^(?:the )?(?:number of )?(?P<quality>[a-z][a-z ,'-]*?) that entered the battlefield "
    r"under your control this turn$",
    re.IGNORECASE,
)


def _entered_under_your_control(phrase: str) -> NumberOf | None:
    """The permanents of a description that entered the battlefield under the
    controller's control this turn (CR 603.6a: entering is a fact of the turn,
    the turn's "entered" history keeps the object as it entered), counting the
    ones that have since left."""
    if " that entered the battlefield under your control this turn" not in phrase.lower():
        return None
    match = _ENTERED_RE.fullmatch(phrase)
    if match is None:
        return None
    from .conditions.history import _quality

    quality = _quality(match.group("quality"))
    if quality is None:
        return None
    return lambda game, controller: sum(
        1
        for entry in game.turn_history
        if entry.kind == "entered" and entry.player == controller and quality(entry)
    )


# --------------------------------------------------------------------------
# "different mana value among nonland permanents you control" (CR 202.3)
# --------------------------------------------------------------------------

_DIFFERENT_MV_RE = re.compile(
    r"^(?:the )?(?:number of )?different mana values? among (?P<quality>[a-z][a-z ,'-]*?) "
    r"you control$",
    re.IGNORECASE,
)


def _different_mana_values_among_permanents(phrase: str) -> NumberOf | None:
    """How many distinct mana values the permanents of a description the
    controller controls have, off the computed board (CR 613.5); a permanent
    with no mana cost is mana value 0 (CR 202.3a)."""
    if "different mana value" not in phrase.lower() or (
        match := _DIFFERENT_MV_RE.fullmatch(phrase)
    ) is None:
        return None
    from ..models.game import _permanent_quality

    quality = _permanent_quality(match.group("quality"))
    if quality is None:
        return None

    def count(game: "Game", controller: str) -> int:
        board = game.computed_board()
        values = set()
        for permanent in game.battlefield:
            chars = board.of(permanent)
            if chars.controller == controller and quality(chars):
                values.add(int(chars.mana_value))
        return len(values)

    return count


# --------------------------------------------------------------------------
# Multikicker: "each time it was kicked", "the number of times that spell was kicked"
# --------------------------------------------------------------------------


def _times_kicked_each(phrase: str) -> ForEach | None:
    """ "for each time it was kicked" (Bloodhusk Ritualist): CR 702.33d's count
    off the cast record of the source permanent, which CR 400.7d lets an
    ability of the permanent read."""
    if phrase.lower() not in ("time it was kicked", "time this creature was kicked"):
        return None

    def count(game: "Game", _controller: str, source_id: str | None) -> int:
        source = None if source_id is None else game.find_by_id(UUID(source_id))
        record = game.cast_record_of(source) if isinstance(source, CardState) else None
        return record.kicked if record is not None else 0

    return count


_SPELL_KICKED_RE = re.compile(r"^(?:the )?number of times that spell was kicked$", re.IGNORECASE)


def _times_that_spell_was_kicked(phrase: str) -> NumberOf | None:
    """ "the number of times that spell was kicked" (a cast trigger's spell,
    CR 702.33d), off the record of the spell the cast event names - kept for a
    spell that has since resolved or been countered (CR 608.2h)."""
    if "was kicked" not in phrase.lower() or _SPELL_KICKED_RE.fullmatch(phrase) is None:
        return None

    def count(game: "Game", _controller: str) -> int:
        event = getattr(game.resolving, "event", None)
        if event is None or event.subject_id is None:
            return 0
        spell = game.find_by_id(event.subject_id)
        record = game.cast_record_of(spell) if isinstance(spell, CardState) else None
        if record is None and event.subject_stamp is not None:
            record = game.cast_record_as_last_known(event.subject_stamp)
        return record.kicked if record is not None else 0

    return count


# --------------------------------------------------------------------------
# "the number of Curses attached to that player" (CR 303.4m, CR 701.3a)
# --------------------------------------------------------------------------

_CURSES_RE = re.compile(
    r"^(?:the )?number of (?P<kind>[A-Za-z]+?)s? attached to (?P<who>them|that player|you|"
    r"enchanted player)$",
    re.IGNORECASE,
)


def _auras_attached_to_player(phrase: str) -> NumberOf | None:
    """How many permanents of a subtype ("Curses") are attached to a player: an
    Aura enchanting a player is attached to it (CR 303.4m, CR 701.3a). "Them"
    is the player the reader is asked for (the one an enclosing "deals damage
    to that player" counts for); "that player" the resolving trigger's."""
    if " attached to " not in phrase.lower() or (match := _CURSES_RE.fullmatch(phrase)) is None:
        return None
    kind = match.group("kind").lower()
    who = match.group("who").lower()

    def count(game: "Game", controller: str) -> int:
        player = _event_player(game, controller) if who == "that player" else controller
        board = game.computed_board()
        return sum(
            1
            for permanent in game.battlefield
            if permanent.attachment is not None
            and permanent.attachment.username == player
            and any(subtype.lower() == kind for subtype in board.of(permanent).subtypes)
        )

    return count


# --------------------------------------------------------------------------
# "for each Aura you controlled that was attached to it" (CR 603.10a)
# --------------------------------------------------------------------------

_ATTACHED_TO_IT_EACH_RE = re.compile(
    r"^(?P<kind>[a-z]+) you controlled that was attached to it$", re.IGNORECASE
)


def _attachments_it_had_each(phrase: str) -> ForEach | None:
    """ "for each Aura you controlled that was attached to it" (a dies trigger,
    Hateful Eidolon): the Auras the dying permanent had as it last existed on
    the battlefield (CR 603.10a), `CardState.last_known_attachments`, that the
    controller controlled."""
    if " that was attached to it" not in phrase.lower() or (
        match := _ATTACHED_TO_IT_EACH_RE.fullmatch(phrase)
    ) is None:
        return None
    kind = match.group("kind").lower()

    def count(game: "Game", controller: str, _source_id: str | None) -> int:
        event = getattr(game.resolving, "event", None)
        if event is None or event.subject_id is None:
            return 0
        dead = game.find_by_id(event.subject_id)
        if not isinstance(dead, CardState):
            return 0
        return sum(
            1
            for snapshot in dead.last_known_attachments
            if snapshot.controller == controller
            and any(subtype.lower() == kind for subtype in snapshot.subtypes)
        )

    return count


_FOR_EACH_READERS = (
    _died_this_turn_each,
    _times_kicked_each,
    _attachments_it_had_each,
)
_NUMBER_OF_READERS = (
    _cards_discarded_this_turn,
    _entered_under_your_control,
    _different_mana_values_among_permanents,
    _times_that_spell_was_kicked,
    _auras_attached_to_player,
)


def _as_for_each(reader: NumberOf) -> ForEach:
    return lambda game, controller, _source_id: reader(game, controller)


@cache
def for_each_cards_counts(phrase: str) -> ForEach | None:
    """The count of "<effect> for each <phrase>", or `None`."""
    text = " ".join(phrase.split())
    for reader in _FOR_EACH_READERS:
        if (count := reader(text)) is not None:
            return count
    # The same description counted as "the number of <description>".
    for number_reader in _NUMBER_OF_READERS:
        if (counted := number_reader(text) or number_reader(f"the number of {text}")) is not None:
            return _as_for_each(counted)
    return None


@cache
def number_of_cards_counts(phrase: str) -> NumberOf | None:
    """The count of "the number of <phrase>" / "equal to <phrase>", or `None`."""
    text = " ".join(phrase.split())
    for reader in _NUMBER_OF_READERS:
        if (count := reader(text)) is not None:
            return count
    return None
