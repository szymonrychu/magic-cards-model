"""EP-02 R3 T8 part: "+X/+X / -X/-X until end of turn, where X is ..." amounts.

Extends the shared where-X pump reader (`effects.amounts._parse_where_x_is_continuous_effect`
and its spell-side twin) additively:

- `controller_amount`: an extremum or a difference the controller alone fixes
  ("the greatest mana value among permanents you control", CR 202.3;
  "7 minus the number of cards in your hand", CR 107.1b for a negative result).
- `object_amount`: an amount that reads the resolving object (CR 608.2h, taken once
  as the effect applies): "the greatest power and/or toughness among other creatures
  you control" (the source is not "other"), "7 minus the number of cards in that
  creature's controller's hand" (the target's controller), "the power of the exiled
  card" (the card the source exiled, CR 607.2a).
- `x_literal`: the sentence with its X written out, a negative X flipping the sign
  of a "-X" the way arithmetic does (CR 107.3a defines X; "-X/-X" with X = -1 is +1/+1).
- `may_have_pump`: "you may have target creature get +X/+X until end of turn, where X is ..."
  is the optional (CR 608.2d) form of the plain pump.
"""

import functools
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..models.card import Type
from .decisions import source_id_of
from .effects._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE

if TYPE_CHECKING:
    from ..models.game import Game

_X_RE = re.compile(r"(?P<sign>[+-]?)\bX\b")

_GROUP_TYPES = {
    "permanents": None,
    "creatures": Type.CREATURE,
    "artifacts": Type.ARTIFACT,
    "enchantments": Type.ENCHANTMENT,
    "lands": Type.LAND,
    "planeswalkers": Type.PLANESWALKER,
}
_GREATEST_RE = re.compile(
    r"^(?:the )?greatest (?P<stat>power and/or toughness|power|toughness|mana value) among "
    r"(?P<other>other )?(?P<group>permanents|creatures|artifacts|enchantments|lands|planeswalkers)"
    r" you control$",
    re.IGNORECASE,
)
_MINUS_RE = re.compile(r"^(?P<n>\d+) minus (?P<rest>.+)$", re.IGNORECASE)
_HAND_OF_RE = re.compile(
    r"^(?:the )?number of cards in (?P<who>that (?:creature|permanent|player)'s controller's|"
    r"that player's|its controller's|its owner's) hand$",
    re.IGNORECASE,
)
_EXILED_STAT_RE = re.compile(
    r"^(?:the )?(?P<stat>power|toughness|mana value) of the exiled card$", re.IGNORECASE
)


def x_literal(sentence: str, magnitude: int) -> str:
    """`sentence` with every X replaced by `magnitude`; a sign in front of X is
    multiplied in ("-X" with X = -1 reads "+1")."""

    def one(match: re.Match[str]) -> str:
        sign = match.group("sign")
        if not sign:
            return str(magnitude)
        value = -magnitude if sign == "-" else magnitude
        return f"{value:+d}"

    return _X_RE.sub(one, sentence)


def _stat_of(game: "Game", permanent: Any, stat: str) -> int:
    chars = game.computed_board().of(permanent)
    if stat == "mana value":
        return int(permanent.mana_value)  # CR 202.3
    if stat == "power":
        return chars.numeric_power
    if stat == "toughness":
        return chars.numeric_toughness
    return max(chars.numeric_power, chars.numeric_toughness)


def _greatest(
    stat: str, group: str, *, other: bool
) -> Callable[["Game", str, Any], int]:
    card_type = _GROUP_TYPES[group.lower()]

    def read(game: "Game", controller: str, excluded: Any) -> int:
        board = game.computed_board()
        values = [
            _stat_of(game, permanent, stat)
            for permanent in game.battlefield
            if board.of(permanent).controller == controller
            and (card_type is None or card_type in board.of(permanent).types)
            and not (other and excluded is not None and permanent.id == excluded)
        ]
        return max(values, default=0)  # CR 107.2: no value to find is 0

    return read


@functools.cache
def controller_amount(phrase: str) -> Callable[["Game", str], int] | None:
    """`(game, controller) -> int` for the amounts the controller alone fixes, or None."""
    text = phrase.strip().rstrip(".")
    lowered = text.lower()
    if "greatest" in lowered and (match := _GREATEST_RE.fullmatch(text)) is not None:
        if match.group("other"):
            return None  # needs the source: `object_amount`
        read = _greatest(match.group("stat").lower(), match.group("group"), other=False)
        return lambda game, controller: read(game, controller, None)
    if " minus " in lowered and (match := _MINUS_RE.fullmatch(text)) is not None:
        from .effects.amounts import count_expression

        inner = count_expression(match.group("rest"))
        if inner is None:
            return None
        base = int(match.group("n"))
        return lambda game, controller: base - inner(game, controller)
    return None


def _source_of(game: "Game", obj: Any) -> Any:
    getter = getattr(obj, "source_or_last_known", None)
    return getter(game) if getter is not None else obj


@functools.cache
def object_amount(phrase: str) -> Callable[["Game", Any], int] | None:
    """`(game, resolving spell or ability) -> int`, or None."""
    text = phrase.strip().rstrip(".")
    lowered = text.lower()
    if "greatest" in lowered and (match := _GREATEST_RE.fullmatch(text)) is not None:
        if not match.group("other"):
            return None
        read = _greatest(match.group("stat").lower(), match.group("group"), other=True)

        def greatest_of_others(game: "Game", obj: Any) -> int:
            source = _source_of(game, obj)
            return read(game, game.controller_of(obj).username, getattr(source, "id", None))

        return greatest_of_others
    if " minus " in lowered and (match := _MINUS_RE.fullmatch(text)) is not None:
        inner = _hand_of_target(match.group("rest"))
        if inner is None:
            return None
        base = int(match.group("n"))
        return lambda game, obj: base - inner(game, obj)
    if lowered.startswith("the number of cards in ") and (hand := _hand_of_target(text)):
        return hand
    if lowered.startswith("this ") and (own := _OWN_STAT_RE.fullmatch(lowered)) is not None:
        return _own_stat(own.group("stat"))
    if "times" in lowered and (times := _times_reader(lowered)) is not None:
        return times
    if " of the exiled card" in lowered and (match := _EXILED_STAT_RE.fullmatch(text)):
        return _exiled_stat(match.group("stat").lower())
    return None


_TIMES_RE = re.compile(
    r"^(?:the )?number of times (?:this (?P<ability>ability) has resolved this turn|"
    r"this (?:creature|permanent|spell) (?:(?P<kicked>was kicked)|(?P<mutated>has mutated)))$"
)


def _times_reader(lowered: str) -> Callable[["Game", Any], int] | None:
    """"The number of times this ability has resolved this turn" (CR 608.2h: the
    resolution in progress counts), "... this creature was kicked" (CR 702.33d: a
    multikicker spell is kicked once per payment) and "... has mutated" (CR 702.140c:
    each spell merged into it)."""
    match = _TIMES_RE.fullmatch(lowered)
    if match is None:
        return None
    if match.group("ability"):
        from .triggers.events import resolution_key

        return lambda game, obj: game.ability_resolutions_this_turn.get(resolution_key(obj), 0)
    if match.group("kicked"):

        def kicked(game: "Game", obj: Any) -> int:
            record = game.cast_record_of(_source_of(game, obj))
            return record.kicked if record is not None else 0

        return kicked
    return lambda game, obj: len(game.merged_components.get(_source_of(game, obj).id, []))


_OWN_STAT_RE = re.compile(r"^this (?:creature|permanent)'s (?P<stat>power|toughness|mana value)$")


def _own_stat(stat: str) -> Callable[["Game", Any], int]:
    """"This creature's power" as the object resolves (CR 608.2h): the source's value
    now, or its last known value once it has left the battlefield (CR 603.10a)."""

    def read(game: "Game", obj: Any) -> int:
        from .effects.draw_discard import _source_characteristic

        source = _source_of(game, obj)
        if source is None:
            return 0
        if stat == "mana value":
            return int(source.mana_value)
        return _source_characteristic(game, source, stat)

    return read


def _hand_of_target(phrase: str) -> Callable[["Game", Any], int] | None:
    match = _HAND_OF_RE.fullmatch(phrase.strip())
    if match is None:
        return None
    who = match.group("who").lower()

    def cards_in_hand(game: "Game", obj: Any) -> int:
        targets = game.resolve_card_targets(obj)
        subject = targets[0] if targets else None
        if subject is None:
            return 0
        if "owner" in who:
            return len(game.player(subject.owner).hand)
        return len(game.player(game.controller_of(subject).username).hand)

    return cards_in_hand


def _exiled_stat(stat: str) -> Callable[["Game", Any], int]:
    def read(game: "Game", obj: Any) -> int:
        from .exiled_with_peek import _pile

        pile = _pile(game, obj)
        if not pile:
            return 0
        card = pile[-1]
        if stat == "mana value":
            return int(card.mana_value)  # CR 202.3, 608.2h: read as it is in exile
        value = card.card.power if stat == "power" else card.card.toughness
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    return read


_MAY_HAVE_PUMP_RE = re.compile(
    r"^you may have (?P<subject>(?:up to \w+ )?target [\w -]+?) (?P<verb>get|gain|lose) "
    r"(?P<rest>.+, where X is .+)$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36", before=["amounts._parse_where_x_is_continuous_effect"])
def may_have_pump(text: str) -> Any:
    """"You may have target creature get +X/+X until end of turn, where X is ...": asked
    at resolution (CR 608.2d), then the plain pump."""
    stripped = " ".join(text.split())
    if not stripped.lower().startswith("you may have ") or "where x is" not in stripped.lower():
        return None
    match = _MAY_HAVE_PUMP_RE.fullmatch(stripped)
    if match is None:
        return None
    from .effects.amounts import _parse_where_x_is_continuous_effect

    plain = f"{match.group('subject')} {match.group('verb')}s {match.group('rest')}"
    inner = _parse_where_x_is_continuous_effect(plain)
    if inner is None:
        return None
    prompt = f"have {match.group('subject')} {match.group('verb')} {match.group('rest')}?"

    def effect(game: "Game", ability: Any) -> None:
        if game.may(
            ability.controller, prompt, source=ability.source_name, source_id=source_id_of(ability)
        ):
            inner(game, ability)

    return effect


_IT_PUMP_RE = re.compile(
    r"^(?P<lead>until end of turn, )?(?P<subject>it|equipped creature|enchanted creature) gets "
    r"(?P<pump>[+-](?:X|\d+)/[+-](?:X|\d+))(?P<tail> until end of turn)?, where X is (?P<expr>[^.]+?)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36", before=["amounts._parse_where_x_is_continuous_effect"])
def it_gets_pump(text: str) -> Any:
    """"It / equipped creature gets +X/+X until end of turn, where X is ...": the
    subject is the object the ability is about - the event's subject (else the source)
    for "it", the permanent the source is attached to for "equipped creature" and
    "enchanted creature" (CR 301.5, 303.4); X is taken once as the effect applies
    (CR 608.2h) and the pump is a one-shot continuous effect (CR 611.2a)."""
    stripped = " ".join(text.split())
    lowered = stripped.lower()
    if "where x is" not in lowered or not lowered.startswith(("it get", "until end", "equipped")):
        return None
    match = _IT_PUMP_RE.fullmatch(stripped)
    if match is None or not (match.group("lead") or match.group("tail")):
        return None
    from .effects import amounts

    expr = match.group("expr")
    controller_expr = amounts.count_expression(expr)
    object_expr = (
        None
        if controller_expr is not None
        else amounts._source_characteristic_expr(expr, "this creature gets")
        or amounts._event_subject_characteristic_expr(expr)
        or object_amount(expr)
    )
    if controller_expr is None and object_expr is None:
        return None
    pump = match.group("pump") + " until end of turn"
    subject_word = match.group("subject").lower()
    if amounts.parsed_layer_effects(f"This creature gets {x_literal(pump, 1)}.") is None:
        return None

    def effect(game: "Game", ability: Any) -> None:
        source = ability.source_or_last_known(game)
        if source is None:
            return
        if subject_word == "it":
            event = getattr(ability, "event", None)
            subject_id = getattr(event, "subject_id", None)
            subject = game.find_by_id(subject_id) if subject_id is not None else source
        else:
            attached_id = source.attached_to
            subject = game.find_by_id(attached_id) if attached_id is not None else None
        if subject is None or getattr(subject, "zone", None) is None:
            return
        magnitude = (
            controller_expr(game, ability.controller)
            if controller_expr is not None
            else object_expr(game, ability)  # type: ignore[misc]
        )
        builder = amounts.parsed_layer_effects(f"This creature gets {x_literal(pump, magnitude)}.")
        if builder is None:
            return
        store = amounts.continuous_effects(game)
        timestamp = store.tick()
        context = amounts.layer_context_for(game, game.controller_of(ability))
        for built in builder(source, timestamp, [subject], context):
            if built.holds(game):
                store.add(built)

    return effect


_UNTAP_IT_RE = re.compile(r"^untap it\.?$", re.IGNORECASE)


@MIXED_CLAUSE.rung("s32", for_spell=FORWARD)
def untap_the_target(text: str, *, for_spell: bool) -> Any:
    """"Untap it." closing a sentence that targeted the permanent (Boon of Boseiju): the
    target is untapped as the object resolves (CR 701.26b)."""
    if _UNTAP_IT_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", spell: Any) -> None:
        for target in game.resolve_card_targets(spell):
            if target.zone.value == "battlefield":
                target.untap(exert_applies=False)

    return effect


# --------------------------------------------------------------------------
# "Target <permanent> you control becomes a creature in addition to its other types and
# has base power and base toughness each equal to its mana value." (no duration:
# CR 611.2a lets the text state none, so it lasts for the rest of the game)
# --------------------------------------------------------------------------

_BECOMES_CREATURE_RE = re.compile(
    r"^(?P<target>target [a-z -]+?) becomes an? creature in addition to its other types and "
    r"has base power and (?:base )?toughness each equal to its mana value\.?$",
    re.IGNORECASE,
)


def _becomes_creature_effect(text: str) -> Any:
    flat = " ".join(text.split())
    if "becomes a" not in flat.lower() or "mana value" not in flat.lower():
        return None
    match = _BECOMES_CREATURE_RE.fullmatch(flat)
    if match is None:
        return None
    from ..models.card_state import CardState
    from ..models.zone import Zone
    from .effects._common import _targets_understood
    from .effects.continuous import continuous_effects
    from .layers import (
        ContinuousEffect,
        Duration,
        Layer,
        Sublayer,
        add_type,
        only_this_incarnation,
        set_power_toughness,
    )

    if not _targets_understood(match.group("target")):
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        name = stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name
        for target in game.resolve_card_targets(stack_object):
            if target.zone is not Zone.BATTLEFIELD:
                continue
            value = int(target.mana_value)  # CR 202.3, read once as it applies (CR 608.2h)
            store = continuous_effects(game)
            for layer, sublayer, modification, what in (
                (Layer.TYPE, None, add_type(Type.CREATURE), "becomes a creature"),
                (
                    Layer.POWER_TOUGHNESS,
                    Sublayer.SET,
                    set_power_toughness(value, value),
                    f"has base power and toughness {value}",
                ),
            ):
                fields: dict[str, Any] = {} if sublayer is None else {"sublayer": sublayer}
                store.add(
                    ContinuousEffect(
                        description=f"{name}: {target.name} {what}",
                        layer=layer,
                        timestamp=store.tick(),
                        duration=Duration.INDEFINITE,
                        selector=only_this_incarnation(target, target.zone_change_stamp),
                        modification=modification,
                        **fields,
                    ),
                    game,
                )

    return effect


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def becomes_creature_with_mana_value_stats(text: str) -> Any:
    """`_becomes_creature_effect` as an ability's whole text."""
    return _becomes_creature_effect(text)


# --------------------------------------------------------------------------
# "Until end of turn, target creature with defender gains haste, can attack as though it
# didn't have defender, and assigns combat damage equal to its toughness rather than its
# power." One continuous effect per listed grant (CR 611.2a), on the chosen creature (CR 611.2c).
# --------------------------------------------------------------------------

_GRANT_LIST_RE = re.compile(
    r"^until end of turn, (?P<target>target creature(?: with defender)?) (?P<grants>gains? .+)$",
    re.IGNORECASE,
)
_NO_DEFENDER = "can attack as though it didn't have defender"
_TOUGHNESS_DAMAGE = "assigns combat damage equal to its toughness rather than its power"


def _grant_items(grants: str) -> list[str] | None:
    body = re.sub(r"^gains? ", "", grants.strip().rstrip("."), flags=re.IGNORECASE)
    items = [i.strip() for i in re.split(r",\s*(?:and\s+)?|\s+and\s+", body) if i.strip()]
    items = [re.sub(r"^and ", "", i) for i in items]
    # "can attack as though it didn't have defender" and the damage clause hold "and"-free words.
    return items or None


def _grant_list_effect(text: str) -> Any:
    flat = " ".join(text.split())
    lowered = flat.lower()
    if not lowered.startswith("until end of turn, target creature") or not (
        _NO_DEFENDER in lowered or _TOUGHNESS_DAMAGE in lowered
    ):
        return None
    match = _GRANT_LIST_RE.fullmatch(flat)
    if match is None:
        return None
    items = _grant_items(match.group("grants"))
    from .combat import ASSIGNS_DAMAGE_AS_TOUGHNESS_TEXT, ATTACK_WITHOUT_DEFENDER_TEXT
    from .effects._common import _targets_understood
    from .layers import grant_ability

    if items is None or not _targets_understood(match.group("target")):
        return None
    grants = []
    for item in items:
        lowered_item = item.lower()
        if lowered_item == _NO_DEFENDER:
            grants.append(ATTACK_WITHOUT_DEFENDER_TEXT)
        elif lowered_item == _TOUGHNESS_DAMAGE:
            grants.append(ASSIGNS_DAMAGE_AS_TOUGHNESS_TEXT)
        elif re.fullmatch(r"[a-z]+(?: [a-z]+)?", lowered_item) and lowered_item in _KEYWORDS:
            grants.append(item[:1].upper() + item[1:])
        else:
            return None
    from ..models.card_state import CardState
    from ..models.zone import Zone
    from .effects.continuous import continuous_effects
    from .layers import ContinuousEffect, Duration, Layer, only_this_incarnation

    def effect(game: "Game", stack_object: Any) -> None:
        name = stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name
        for target in game.resolve_card_targets(stack_object):
            if target.zone is not Zone.BATTLEFIELD:
                continue
            store = continuous_effects(game)
            for granted in grants:
                store.add(
                    ContinuousEffect(
                        description=f"{name}: {target.name} gains {granted.rstrip('.').lower()}",
                        layer=Layer.ABILITY,
                        timestamp=store.tick(),
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=only_this_incarnation(target, target.zone_change_stamp),
                        modification=grant_ability(granted),
                    ),
                    game,
                )

    return effect


_KEYWORDS = frozenset(
    {"haste", "flying", "trample", "vigilance", "menace", "reach", "lifelink", "deathtouch"}
)


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def target_gains_grant_list(text: str) -> Any:
    """`_grant_list_effect` as an ability's whole text."""
    return _grant_list_effect(text)
