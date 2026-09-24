"""Turn-history conditions: what happened this turn (or last turn) - attacks,
deaths, zone changes, life gained and lost, damage dealt, spells cast.

Each reader here is a `ConditionReader` registered through `READERS`; see
`machines/conditions/__init__.py` for the contract every reader keeps.

`record(game, event)` is called by `Game.emit` for every event the game raises,
before any trigger is looked for, so a fact this family needs that no existing
ledger keeps is written from the event that carries it - into
`Game.turn_counts` (`Game.note_turn_count`) or a ledger of its own
(`Game.damage_dealt_this_turn`).

Rules verified with `mise run rules:find`:

- CR 119.3 (an effect makes a player lose life) and CR 120.3a (damage dealt
  to a player causes that much life loss) - `Player.life_lost_this_turn`
  counts both.
- CR 120.1: "An object that deals damage is the source of that damage."
- CR 109.2b: a description with the word "spell" means a spell on the stack.
- CR 603.10a: a card leaving a graveyard is a look-back event
  (`ExtraTriggerEvent.LEAVES_GRAVEYARD`, one per graveyard, with the count).
- CR 205.2a: the card types a "<type> spells" count names; CR 601.2i: a spell
  becomes cast, and is counted in `Game.spells_cast_this_turn`.
"""

import re
from typing import TYPE_CHECKING

from ...data.subtypes import canonical_subtype
from ...models.card import Type
from ...models.zone import Zone
from ...numbers import COUNT, parse_count
from . import ConditionReader

if TYPE_CHECKING:
    from ...models.game import Game
    from ..triggers import GameEvent
    from . import ConditionContext

#: `Game.turn_counts` key for CR 603.10a's cards leaving a graveyard, per the
#: graveyard's owner.
CARDS_LEFT_GRAVEYARD = "cards_left_graveyard"


def record(game: "Game", event: "GameEvent") -> None:
    """Note what this family reads later off `event`, as it happens."""
    from ...models.game import DamageDealt
    from ..triggers import ExtraTriggerEvent, TriggerEvent

    if event.event is ExtraTriggerEvent.LEAVES_GRAVEYARD and event.player is not None:
        game.note_turn_count(CARDS_LEFT_GRAVEYARD, event.player, event.amount or 1)
    elif event.event is TriggerEvent.DEALS_DAMAGE:
        source = game.find_by_id(event.subject_id) if event.subject_id is not None else None
        types = tuple(event.subject_types or ())
        # CR 109.2b: a spell is a card on the stack. An instant or sorcery
        # deals damage only as a spell resolving (CR 608.2), whether or not
        # it is still on the stack at that instant; any other source is one
        # only while it is on the stack itself.
        was_spell = getattr(source, "zone", None) is Zone.STACK or any(
            each in (Type.INSTANT, Type.SORCERY) for each in types
        )
        game.damage_dealt_this_turn.append(
            DamageDealt(
                source_id=event.subject_id,
                source_controller=event.subject_controller,
                source_types=types,
                source_subtypes=tuple(event.subject_subtypes or ()),
                source_was_spell=was_spell,
                recipient_id=event.target_id,
                recipient_player=event.player if event.target_id is None else None,
                amount=event.amount or 0,
                combat=event.combat,
            )
        )


def _opponent_lost_life(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "an opponent lost life this turn" (CR 119.3, CR 120.3a)."""
    return any(
        player.username != context.controller and player.life_lost_this_turn > 0
        for player in context.game.players_in_game
    )


def _cards_left_your_graveyard(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "[N or more cards | a card] left your graveyard this turn" (CR 603.10a),
    counted as each departure's event was raised."""
    needed = parse_count(match.group("count")) if match.group("count") else 1
    if needed is None:
        return False
    return context.game.turn_count(CARDS_LEFT_GRAVEYARD, context.controller) >= needed


def _source_quality(item: str) -> tuple[str, str] | None:
    """One item of a damage source's description: `("spell", "")` for CR
    109.2b's spell, `("type", <Type value>)` or `("subtype", <subtype>)`."""
    word = item.strip()
    for article in ("a ", "an "):
        word = word.removeprefix(article)
    if word in ("spell", "spells"):
        return "spell", ""
    for card_type in Type:
        if card_type.value == word.removesuffix("s"):
            return "type", card_type.value
    subtype = canonical_subtype(word)
    if subtype is not None:
        return "subtype", subtype
    return None


def _source_you_controlled_dealt_damage(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "a Giant, Wizard, or spell you controlled dealt damage to it this turn"
    (Aegar, the Freezing Flame): some damage this turn to "it" - the trigger
    event's own subject - came from a source that, as it dealt the damage,
    was under your control and matched any item of the list. A list item
    this does not read makes the whole clause false rather than guessed."""
    qualities = []
    for item in re.split(r",\s*(?:or\s+)?|\s+or\s+", match.group("list")):
        if not item.strip():
            continue
        quality = _source_quality(item)
        if quality is None:
            return False
        qualities.append(quality)
    event = context.event
    if event is None:
        return False
    recipient = event.target_id if event.target_id is not None else event.subject_id
    if recipient is None:
        return False

    def matches(record) -> bool:
        for kind, value in qualities:
            if kind == "spell" and record.source_was_spell:
                return True
            if kind == "type" and any(each.value == value for each in record.source_types):
                return True
            if kind == "subtype" and value in {each.lower() for each in record.source_subtypes}:
                return True
        return False

    return any(
        record.recipient_id == recipient
        and record.source_controller == context.controller
        and matches(record)
        for record in context.game.damage_dealt_this_turn
    )


def _spells_of_types_cast(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you've cast N or more <type list> spells this turn" (Urabrask's
    "three or more instant and/or sorcery spells"): each spell counted once
    if it has any of the listed card types (CR 205.2a), off
    `Game.spells_cast_this_turn` (CR 601.2i). A type word this does not read
    makes the clause false rather than guessed."""
    needed = parse_count(match.group("count"))
    if needed is None:
        return False
    wanted: set[Type] = set()
    for word in re.split(r",|\band/or\b|\band\b|\bor\b", match.group("types")):
        word = word.strip()
        if not word:
            continue
        card_type = next((each for each in Type if each.value == word.removesuffix("s")), None)
        if card_type is None:
            return False
        wanted.add(card_type)
    if not wanted:
        return False
    cast = context.game.spells_cast_this_turn.get(context.controller, [])
    return (
        sum(1 for state in cast if wanted & set(state.types_as_a_spell(state.card.types))) >= needed
    )


READERS: tuple[ConditionReader, ...] = (
    ConditionReader(
        re.compile(
            rf"you(?:'ve| have) cast (?P<count>{COUNT}) or more (?P<types>[a-z/, ]+?) spells "
            r"this turn"
        ),
        _spells_of_types_cast,
    ),
    ConditionReader(re.compile(r"an opponent lost life this turn"), _opponent_lost_life),
    ConditionReader(
        re.compile(
            rf"(?:(?P<count>{COUNT}) or more cards|(?:a|one) card) left your graveyard this turn"
        ),
        _cards_left_your_graveyard,
    ),
    ConditionReader(
        re.compile(
            r"(?P<list>[a-z' ,-]+?) you controlled dealt damage to "
            r"(?:it|that creature|that permanent) this turn"
        ),
        _source_you_controlled_dealt_damage,
    ),
)
