"""Life, poison, life-floor and one-event replacement statics (CR 614.1a,
CR 119.3, CR 122.6) - plus the search, mill, coin, proliferate, explore, life
payment, dice and noncombat-damage ones at the bottom:

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

from ...models.card import Color, Type
from ...models.card_state import CardState
from ...models.token import is_token
from ...models.zone import Zone
from .model import (
    CardReplacement,
    EventKind,
    ReplaceableEvent,
    ReplacementEffect,
    ReplacementKind,
)
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


# --------------------------------------------------------------------------
# One-event shapes: "If <who> would <do X>, <do X differently> instead."
# --------------------------------------------------------------------------

_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
_WHO = r"(?P<who>you|an opponent|a player)"


def _number(word: str) -> int | None:
    return int(word) if word.isdigit() else _NUMBER_WORDS.get(word.lower())


def _who_applies(who: str, source: CardState, player) -> bool:
    if player is None:
        return False
    if who == "you":
        return player.username == source.controller
    if who == "an opponent":
        return player.username != source.controller
    return True


def _clauses(effect: ReplacementEffect) -> tuple[str, str] | None:
    if not effect.event or not effect.replacement:
        return None
    return _text_of(effect.event), _text_of(effect.replacement)


def _compile_search_limit(effect: ReplacementEffect) -> CardReplacement | None:
    """Aven Mindcensor: "If an opponent would search a library, that player
    searches the top four cards of that library instead." (CR 701.23a)"""
    clauses = _clauses(effect)
    if clauses is None or clauses[0] != "an opponent would search a library":
        return None
    match = re.fullmatch(r"that player searches the top (\w+) cards of that library", clauses[1])
    if match is None or (limit := _number(match.group(1))) is None:
        return None

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        return event.kind is EventKind.SEARCH and _who_applies("an opponent", source, event.player)

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        event.search_limit = limit if event.search_limit is None else min(event.search_limit, limit)

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


def _compile_mill_more(effect: ReplacementEffect) -> CardReplacement | None:
    """The Water Crystal: "If an opponent would mill one or more cards, they
    mill that many cards plus four instead." (CR 701.17a)"""
    clauses = _clauses(effect)
    if clauses is None:
        return None
    head = re.fullmatch(rf"{_WHO} would mill one or more cards", clauses[0])
    tail = re.fullmatch(r"(?:you|they) mill that many cards plus (\w+)", clauses[1])
    if head is None or tail is None or (extra := _number(tail.group(1))) is None:
        return None
    who = head.group("who")

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        return (
            event.kind is EventKind.MILL
            and event.amount > 0
            and _who_applies(who, source, event.player)
        )

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        event.amount += extra

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


def _compile_extra_coin(effect: ReplacementEffect) -> CardReplacement | None:
    """Krark's Thumb: "If you would flip a coin, instead flip two coins and
    ignore one." (CR 705.1)"""
    clauses = _clauses(effect)
    if clauses != ("you would flip a coin", "flip two coins and ignore one"):
        return None

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        return event.kind is EventKind.FLIP_COIN and _who_applies("you", source, event.player)

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        event.amount += 1
        event.ignore += 1

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


def _compile_proliferate_twice(effect: ReplacementEffect) -> CardReplacement | None:
    """Tekuthal: "If you would proliferate, proliferate twice instead." (CR 701.34a)"""
    if _clauses(effect) != ("you would proliferate", "proliferate twice"):
        return None

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        return event.kind is EventKind.PROLIFERATE and _who_applies("you", source, event.player)

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        event.amount *= 2

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


def _compile_scry_before_explore(effect: ReplacementEffect) -> CardReplacement | None:
    """Twists and Turns: "If a creature you control would explore, instead you
    scry 1, then that creature explores." (CR 701.44a, 701.22a)"""
    clauses = _clauses(effect)
    if clauses is None or clauses[0] != "a creature you control would explore":
        return None
    match = re.fullmatch(r"you scry (\w+), then that creature explores", clauses[1])
    if match is None or (count := _number(match.group(1))) is None:
        return None

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        return (
            event.kind is EventKind.EXPLORE
            and event.card is not None
            and event.card.controller == source.controller
        )

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        # The explore still happens afterwards (CR 614.6: the modified event);
        # this effect has used its one opportunity (CR 614.5).
        game.scry(source.controller, count, source=source.name, source_id=str(source.id))

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


def _compile_exile_instead_of_paying_life(effect: ReplacementEffect) -> CardReplacement | None:
    """Ashiok, Wicked Manipulator: "If you would pay life while your library has
    at least that many cards in it, exile that many cards from the top of your
    library instead." (CR 118.3b, 119.4)"""
    if _clauses(effect) != (
        "you would pay life while your library has at least that many cards in it",
        "exile that many cards from the top of your library",
    ):
        return None

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        return (
            event.kind is EventKind.LOSE_LIFE
            and event.payment
            and event.amount > 0
            and _who_applies("you", source, event.player)
            and len(event.player.library) >= event.amount
        )

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        owner = event.player
        game.exile_cards(list(owner.library[: event.amount]))
        event.amount = 0  # the cost is paid with cards; no life is lost

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


def _compile_extra_die(effect: ReplacementEffect) -> CardReplacement | None:
    """Pixie Guide, Barbarian Class: "If you would roll one or more dice,
    instead roll that many dice plus one and ignore the lowest roll." (CR 706.2)"""
    if _clauses(effect) != (
        "you would roll one or more dice",
        "roll that many dice plus one and ignore the lowest roll",
    ):
        return None

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        return (
            event.kind is EventKind.ROLL_DICE
            and event.amount > 0
            and _who_applies("you", source, event.player)
        )

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        event.amount += 1
        event.ignore += 1

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


def _compile_assemble_twice(effect: ReplacementEffect) -> CardReplacement | None:
    """Steamflogger Boss: "If a Rigger you control would assemble a Contraption, it
    assembles two Contraptions instead." (CR 701.45a, 614.1a)"""
    if _clauses(effect) != (
        "a rigger you control would assemble a contraption",
        "it assembles two contraptions",
    ):
        return None

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        return (
            event.kind is EventKind.ASSEMBLE
            and event.card is not None
            and event.card.zone is Zone.BATTLEFIELD
            and event.card.controller == source.controller
            and "rigger" in {s.lower() for s in game.characteristics_of(event.card).subtypes}
        )

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        event.amount *= 2

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


_DAMAGE_FLOOR_HEAD_RE = re.compile(
    r"^a (?P<color>white|blue|black|red|green) source you control would deal an amount of "
    r"noncombat damage less than (?P<name>.+?)'s power to an opponent$"
)
_DAMAGE_FLOOR_TAIL_RE = re.compile(r"^that source deals damage equal to (?P<name>.+?)'s power$")


def _compile_noncombat_damage_floor(effect: ReplacementEffect) -> CardReplacement | None:
    """Ojer Axonil, Deepest Might: "If a red source you control would deal an
    amount of noncombat damage less than Ojer Axonil's power to an opponent,
    that source deals damage equal to Ojer Axonil's power instead." (CR 614.1a, 120.1)"""
    clauses = _clauses(effect)
    if clauses is None:
        return None
    head = _DAMAGE_FLOOR_HEAD_RE.fullmatch(_text_of(effect.event))
    tail = _DAMAGE_FLOOR_TAIL_RE.fullmatch(clauses[1])
    if head is None or tail is None or head.group("name") != tail.group("name"):
        return None
    wanted = Color[head.group("color").upper()]

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        if (
            event.kind is not EventKind.DAMAGE
            or event.combat
            or event.player is None
            or event.source is None
            or event.amount <= 0
            or event.source.controller != source.controller
            or event.player.username == source.controller
        ):
            return False
        power = game.characteristics_of(source).power
        return (
            wanted in game.characteristics_of(event.source).colors
            and power is not None
            and event.amount < power
        )

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        event.amount = game.characteristics_of(source).power

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


EVENT_COMPILERS = (
    _compile_life_event,
    _compile_conditional_life_floor,
    _compile_poison_cap,
    _compile_skip_extra_turn,
    _compile_search_limit,
    _compile_mill_more,
    _compile_extra_coin,
    _compile_proliferate_twice,
    _compile_scry_before_explore,
    _compile_exile_instead_of_paying_life,
    _compile_extra_die,
    _compile_noncombat_damage_floor,
    _compile_assemble_twice,
)


# -- "If a creature you control would enter[ while <condition>], instead it --
# -- enters tapped and attacking." (CR 614.1c, CR 508.4) ----------------------

#: Kira Nerys, Firebrand's own group replacement. The condition is read by
#: `Game.condition_holds` about the replacement's controller as the creature
#: would enter; the "attacking" half is CR 508.4's put-onto-the-battlefield-
#: attacking, its defender the one its controller is already attacking.
_GROUP_ENTERS_ATTACKING_EVENT_RE = re.compile(
    r"^an? (?P<type>creature|nontoken creature) you control would enter"
    r"(?: while (?P<condition>.+))?$",
    re.IGNORECASE,
)
_ENTERS_TAPPED_AND_ATTACKING_RE = re.compile(
    r"^(?:it|that creature) enters tapped and attacking$", re.IGNORECASE
)


def _compile_group_enters_tapped_and_attacking(
    effect: ReplacementEffect,
) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD or effect.condition is not None:
        return None
    event_match = _GROUP_ENTERS_ATTACKING_EVENT_RE.fullmatch((effect.event or "").strip())
    replacement = (effect.replacement or "").strip().rstrip(".")
    if event_match is None or not _ENTERS_TAPPED_AND_ATTACKING_RE.fullmatch(replacement):
        return None
    condition = event_match.group("condition")
    from ...models.game._conditions import condition_is_readable

    if condition is not None and not condition_is_readable(condition):
        return None
    nontoken = event_match.group("type").lower().startswith("nontoken")

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        card = event.card
        if event.kind is not EventKind.ENTERS_BATTLEFIELD or card is None or event.attacking:
            return False
        if card.controller is None or card.controller != source.controller:
            return False
        if Type.CREATURE not in card.types or (nontoken and is_token(card)):
            return False
        return condition is None or game.condition_holds(card.controller, condition, source) is True

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        event.tapped = True
        event.attacking = True

    return CardReplacement(label=effect.text, applies=applies, apply=apply)
