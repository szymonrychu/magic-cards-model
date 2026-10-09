"""Life, poison and life-floor replacement statics (CR 614.1a, CR 119.3, CR 122.6):

- "If an opponent would gain life, that player loses that much life instead."
- "If a spell or ability would cause its controller to gain life, that player
  loses that much life instead." (lifelink is not a spell or ability)
- "If you would gain life while you have 5 or less life, you gain twice that
  much life instead."
- "If an opponent would lose life during your turn, they lose twice that much
  life instead."
- "If you control a creature, damage that would reduce your life total to less
  than 1 reduces it to 1 instead."
- "If you would get one or more poison counters, instead you get one poison
  counter and you can't get additional poison counters this turn."
"""

import re
from typing import TYPE_CHECKING

from ...models.card import Type
from ...models.card_state import CardState
from .model import CardReplacement, EventKind, ReplaceableEvent, ReplacementEffect
from .parse import _read_damage_life_floor, strip_reminder_text

if TYPE_CHECKING:
    from ...models.game import Game


def _text(effect: ReplacementEffect) -> str:
    return strip_reminder_text(effect.raw)[0].strip().rstrip(".")


_TAINTED_RE = re.compile(
    r"^if (?:an opponent|a spell or ability would cause its controller to) "
    r"(?:would gain life|gain life), that player loses that much life instead$",
    re.IGNORECASE,
)
_TWICE_GAIN_RE = re.compile(
    r"^if you would gain life while you have (?P<n>\d+) or less life, "
    r"you gain twice that much life instead$",
    re.IGNORECASE,
)
_TWICE_LOSS_RE = re.compile(
    r"^if an opponent would lose life during your turn, they lose twice that much life instead$",
    re.IGNORECASE,
)
_WORSHIP_RE = re.compile(
    r"^if you control an? (?P<type>[a-z]+), (?P<rest>damage .+)$", re.IGNORECASE
)
_POISON_RE = re.compile(
    r"^if you would get one or more poison counters, instead you get one poison counter "
    r"and you can't get additional poison counters this turn$",
    re.IGNORECASE,
)
_TYPES = {"creature": Type.CREATURE, "artifact": Type.ARTIFACT, "land": Type.LAND}


def _lose_that_much(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
    lost, event.amount = event.amount, 0
    game.lose_life(event.player, lost)


def _compile_life_event(effect: ReplacementEffect) -> CardReplacement | None:  # noqa: C901
    text = _text(effect)
    if match := re.match(
        r"^if an opponent would gain life, that player loses that much life instead$",
        text,
        re.IGNORECASE,
    ):

        def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
            return (
                event.kind is EventKind.GAIN_LIFE
                and event.amount > 0
                and event.player is not None
                and event.player.username != source.controller
            )

        return CardReplacement(label=effect.text, applies=applies, apply=_lose_that_much)
    if re.match(
        r"^if a spell or ability would cause its controller to gain life, "
        r"that player loses that much life instead$",
        text,
        re.IGNORECASE,
    ):

        def spell_or_ability(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
            return event.kind is EventKind.GAIN_LIFE and event.amount > 0 and not event.lifelink

        return CardReplacement(label=effect.text, applies=spell_or_ability, apply=_lose_that_much)
    if match := _TWICE_GAIN_RE.match(text):
        limit = int(match.group("n"))

        def gain_applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
            return (
                event.kind is EventKind.GAIN_LIFE
                and event.amount > 0
                and event.player is not None
                and event.player.username == source.controller
                and event.player.life <= limit
            )

        def double(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
            event.amount *= 2

        return CardReplacement(label=effect.text, applies=gain_applies, apply=double)
    if _TWICE_LOSS_RE.match(text):

        def loss_applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
            return (
                event.kind is EventKind.LOSE_LIFE
                and event.amount > 0
                and event.player is not None
                and event.player.username != source.controller
                and game.active_player.username == source.controller
            )

        def double_loss(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
            event.amount *= 2

        return CardReplacement(label=effect.text, applies=loss_applies, apply=double_loss)
    return None


def _compile_conditional_life_floor(effect: ReplacementEffect) -> CardReplacement | None:
    match = _WORSHIP_RE.match(_text(effect))
    if match is None or match.group("type").lower() not in _TYPES:
        return None
    floor = _read_damage_life_floor(match.group("rest"))
    wanted = _TYPES[match.group("type").lower()]
    if floor is None:
        return None

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        if event.kind is not EventKind.DAMAGE or event.player is None or event.amount <= 0:
            return False
        if event.player.username != source.controller:
            return False
        controls = any(
            p.controller == source.controller and wanted in game.characteristics_of(p).types
            for p in game.battlefield
        )
        return controls and event.player.life - event.amount < floor

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        event.amount = max(event.player.life - floor, 0)

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


def _compile_poison_cap(effect: ReplacementEffect) -> CardReplacement | None:
    if _POISON_RE.match(_text(effect)) is None:
        return None

    def lock_fact(source: CardState) -> str:
        return f"poison_capped:{source.id}"

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        return (
            event.kind is EventKind.ADD_COUNTERS
            and event.card is None
            and event.player is not None
            and event.player.username == source.controller
            and str(event.counter_kind).lower() == "poison"
            and event.amount > 0
        )

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        if game.turn_fact_holds(lock_fact(source), source.controller):
            event.amount = 0  # CR 614.1a: "can't get additional poison counters this turn"
            return
        event.amount = 1
        game.record_turn_fact(lock_fact(source), source.controller)

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


def _compile_skip_extra_turn(effect: ReplacementEffect) -> CardReplacement | None:
    """ "If a player would begin an extra turn, that player skips that turn
    instead." (CR 614.10, CR 500.7)"""
    if (effect.event or "").strip().lower() != "a player would begin an extra turn":
        return None
    if _text_of(effect.replacement) != "that player skips that turn":
        return None

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        return event.kind is EventKind.BEGIN_EXTRA_TURN and not event.replaced

    def skip(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        event.replaced = True

    return CardReplacement(label=effect.text, applies=applies, apply=skip)


def _text_of(clause: str | None) -> str:
    return strip_reminder_text(clause or "")[0].strip().rstrip(".").lower()


EVENT_COMPILERS = (
    _compile_life_event,
    _compile_conditional_life_floor,
    _compile_poison_cap,
    _compile_skip_extra_turn,
)
