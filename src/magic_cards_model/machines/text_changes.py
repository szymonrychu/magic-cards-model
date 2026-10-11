"""EP-01 round 2, task T1: text-changing effects on color words (CR 612,
CR 613.1c) - Swirl the Mists's "All instances of color words in the text of
spells and permanents are changed to the chosen color word."

CR 613.1c makes a text change the *first* layer to apply after copy effects,
so an object with changed text has that text for everything after it: every
reader of rules text (static, triggered and activated abilities, a spell's
instructions and targets) sees the changed words. This engine reads rules text
off `CardState.card`, so the change is made there, on the objects it reaches
(permanents on the battlefield and spells on the stack, CR 612.1), and undone
from the originals `Game.text_change_originals` keeps when the effect stops
applying (CR 611.3a: a static ability's effect is not "locked in").

CR 612.2: only words used as color words change - a card's own name never
does, even when it holds a color word ("Black Knight") - and CR 612.3 keeps
abilities granted by other effects out of reach (those are not on the card's
text, so nothing here touches them).
"""

from __future__ import annotations

import functools
import re
import uuid
from typing import TYPE_CHECKING

from ..models.card import Card
from ..models.card_state import CardState, ChoiceKind
from ..models.zone import Zone

if TYPE_CHECKING:
    from ..models.game import Game

_MARKER = "all instances of color words in the text of spells and permanents are changed"
_COLOR_WORD_RE = re.compile(r"(?<![A-Za-z])(non)?(white|blue|black|red|green)(?![A-Za-z])", re.I)
_NAME_HOLE = "\u0000"


@functools.cache
def _is_changer(oracle_text: str) -> bool:
    return _MARKER in oracle_text.lower()


def active_color_word(game: Game) -> str | None:
    """The color word every color word is changed to right now, or None (CR
    612.1). With several such permanents the latest timestamp applies last, so
    its word is the one that remains (CR 613.7a)."""
    word = None
    for permanent in game.battlefield:
        text = permanent.card.oracle_text
        if not text or not _is_changer(text):
            continue
        choice = permanent.choice
        if choice is not None and choice.kind is ChoiceKind.COLOR_WORD:
            word = choice.value.lower()
    return word


def change_color_words(text: str, word: str, name: str = "") -> str:
    """`text` with every color word (and the color inside "nonred") changed to
    `word`, keeping its capitalisation and leaving `name` alone (CR 612.2)."""

    def swap(match: re.Match[str]) -> str:
        found = match.group(2)
        new = word.capitalize() if found[:1].isupper() else word.lower()
        if found.isupper() and len(found) > 1:
            new = word.upper()
        return (match.group(1) or "") + new

    if name and name in text:
        pieces = text.split(name)
        return name.join(_COLOR_WORD_RE.sub(swap, piece) for piece in pieces)
    return _COLOR_WORD_RE.sub(swap, text)


_CHANGED: dict[tuple[uuid.UUID, str], Card] = {}


def changed_card(card: Card, word: str) -> Card:
    """`card` with its rules text changed (a distinct id, so nothing memoised on
    the printed card's id is read for it)."""
    key = (card.id, word)
    if key not in _CHANGED:
        _CHANGED[key] = _changed_card(card, word)
    return _CHANGED[key]


def _changed_card(card: Card, word: str) -> Card:
    update: dict[str, object] = {"id": uuid.uuid5(card.id, f"color-word|{word}")}
    if card.oracle_text is not None:
        update["oracle_text"] = change_color_words(card.oracle_text, word, card.name)
    if card.card_faces:
        update["card_faces"] = [
            face.model_copy(
                update={"oracle_text": change_color_words(face.oracle_text, word, face.name)}
            )
            if face.oracle_text
            else face
            for face in card.card_faces
        ]
    return card.model_copy(update=update)


def sync_text_changes(game: Game) -> None:
    """Make every spell and permanent carry the text the active color-word
    change gives it, and every other object its own printed text again."""
    word = active_color_word(game)
    originals = game.text_change_originals
    if word is None and not originals:
        return
    reached = (
        [*game.battlefield, *(state for state in game.stack if isinstance(state, CardState))]
        if word is not None
        else []
    )
    reached_ids = {str(state.id) for state in reached}
    for key in [key for key in originals if key not in reached_ids]:
        state = game.find_by_id(uuid.UUID(key))
        if isinstance(state, CardState):
            state.card = originals[key]
        del originals[key]
    if word is None:
        return
    for state in reached:
        key = str(state.id)
        printed = originals.get(key, state.card)
        changed = changed_card(printed, word)
        if state.card is changed or state.card.id == changed.id:
            continue
        originals[key] = printed
        state.card = changed
