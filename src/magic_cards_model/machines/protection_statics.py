"""Static hexproof / shroud / protection grants and "can't be the target"
restrictions (CR 702.11, CR 702.18, CR 702.16, CR 115.2).

Two shapes of static line live here, both read one way and performed by the
engine's existing targeting, damage, enchant and block readers:

**Grant lines** - "<subject> have <hexproof | shroud | protection from
<quality> | ...>" with an optional board condition ("During your turn,",
"As long as you control four or more artifacts,", "... as long as it's
untapped", "Metalcraft -"). `parse_static_grant` reads the sentence into a
`StaticGrant`; the *permanent* half is a layer 6 effect
(`grant_builder`, CR 613.1f, selector `layers.StaticGroupGrant`) that puts the
keyword on the computed board, where `Game.hexproof_abilities`,
`Game.shroud_refusal` and `Game._effective_protection_qualities` already read
it; the *player* half ("You and Humans you control have hexproof",
"You have protection from each of your opponents") is read fresh off the
controller's permanents by `player_grants`, so it ends with its source
(CR 604.2).

**Restriction lines** - "<this creature | enchanted creature | cards in
graveyards> can't be the target of [<quality>] spells [your opponents control]
or abilities [from <quality> sources] [your opponents control]". Unlike
hexproof there is no controller exception unless the line says "your
opponents". `parse_target_restriction` reads it, `static_target_refusal` is
the one question every targeting path asks (it is called from
`Game.hexproof_refusal`, which announcement, the live candidate lists and the
CR 608.2b recheck all share).

"Creatures your opponents control lose hexproof and can't have or gain
hexproof" is a layer 6 removal (`LoseKeyword`) plus `hexproof_suppressed`,
which `Game.hexproof_abilities` consults so a later grant cannot give it back.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING, Any

from ..models.card import Color, Type
from ..models.card_state import CardState, ChoiceKind
from .abilities import _strip_reminder, self_normalized_effect_text
from .layers import (
    ContinuousEffect,
    ControlledCountRequirement,
    EffectBuilder,
    Layer,
    LayerContext,
    StaticGroupGrant,
    _source_line_for,
    _split_and_validate_keywords,
    grant_ability,
    lose_keyword,
)

if TYPE_CHECKING:
    from ..models.game import Game

_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
}

_COLOR_NAMES = ("white", "blue", "black", "red", "green")

# -- data ---------------------------------------------------------------------


@dataclass(frozen=True)
class Group:
    """One group of permanents a grant reaches."""

    self_only: bool = False
    attached: bool = False
    scope: str = "you"
    other: bool = False
    card_types: tuple[str, ...] = ()
    subtypes: tuple[str, ...] = ()
    chosen_subtype: str | None = None
    legendary: bool = False
    tokens: bool = False
    tapped: str | None = None
    enchanted: bool = False
    greatest_mana_value: bool = False


@dataclass(frozen=True)
class Gate:
    """The line's condition. `turn`, `source_tapped` and `entered_this_turn`
    are facts about the moment; `requirements`, `lore_counters_min` and
    `paired` are asked of the board."""

    turn: str | None = None
    source_tapped: bool | None = None
    entered_this_turn: bool = False
    requirements: tuple[ControlledCountRequirement, ...] = ()
    lore_counters_min: int = 0
    paired: bool = False


@dataclass(frozen=True)
class Item:
    """One thing granted: `kind` is hexproof, shroud, hexproof_from,
    protection, lose_hexproof or keyword; `qualities` the protection or
    hexproof-from qualities (possibly a chosen-quality placeholder)."""

    kind: str
    qualities: tuple[str, ...] = ()
    keyword: str = ""


@dataclass(frozen=True)
class StaticGrant:
    player: bool
    groups: tuple[Group, ...]
    items: tuple[Item, ...]
    gate: Gate


_CHOSEN_QUALITY_PLACEHOLDERS = {
    "the chosen color": "<chosen color>",
    "the chosen colour": "<chosen color>",
    "the chosen card type": "<chosen card type>",
    "the chosen card name": "<chosen card name>",
    "creatures of the chosen type": "<chosen creature type>",
}

# -- sentence reading -------------------------------------------------------

_DURING_YOUR_TURN_RE = re.compile(r"^during your turn, (?P<rest>.+)$", re.IGNORECASE)
_DURING_OTHER_TURNS_RE = re.compile(r"^during turns other than yours, (?P<rest>.+)$", re.IGNORECASE)
_LEADING_AS_LONG_AS_RE = re.compile(
    r"^as long as (?P<cond>.+?), (?P<rest>[A-Za-z].+)$", re.IGNORECASE
)
_TRAILING_AS_LONG_AS_RE = re.compile(r"^(?P<rest>.+?) as long as (?P<cond>[^,]+)$", re.IGNORECASE)
_MAIN_RE = re.compile(
    r"^(?P<subject>.+?) (?P<verb>has|have|loses|lose) (?P<items>.+)$", re.IGNORECASE | re.DOTALL
)
_ABILITY_WORD_RE = re.compile(r"^[A-Z][A-Za-z' ]{2,30} — ")

_CONTROLS_COUNT_RE = re.compile(
    r"^you control (?P<n>\w+) or more (?P<noun>[a-z ]+)$", re.IGNORECASE
)
_LORE_RE = re.compile(
    r"^there are (?P<n>\w+) or more lore counters among sagas you control$", re.IGNORECASE
)
_SELF_TAPPED_RE = re.compile(
    r"^(?:this (?:creature|permanent|artifact|enchantment|land)|it) (?:is|'s) (?P<status>un)?tapped$",
    re.IGNORECASE,
)
_ENTERED_RE = re.compile(
    r"^(?:it|this (?:creature|permanent|artifact|enchantment|land|aura|equipment)) "
    r"entered(?: the battlefield)? this turn$",
    re.IGNORECASE,
)
_PAIRED_RE = re.compile(
    r"^this (?:creature|permanent) is paired with another creature$", re.IGNORECASE
)

_TYPE_NOUNS = {
    "creatures": "creature",
    "artifacts": "artifact",
    "enchantments": "enchantment",
    "lands": "land",
    "planeswalkers": "planeswalker",
    "battles": "battle",
}


def _number(word: str) -> int | None:
    word = word.lower()
    return int(word) if word.isdigit() else _NUMBER_WORDS.get(word)


def _singular_subtype(word: str) -> str | None:
    from .counter_effects import singular_subtype

    return singular_subtype(word)


def _parse_condition(condition: str) -> Gate | None:
    """The board/moment condition `condition` states, or `None` if unread."""
    condition = condition.strip().rstrip(".")
    if (match := _SELF_TAPPED_RE.match(condition)) is not None:
        return Gate(source_tapped=match.group("status") is None)
    if _ENTERED_RE.match(condition):
        return Gate(entered_this_turn=True)
    if _PAIRED_RE.match(condition):
        return Gate(paired=True)
    if (match := _LORE_RE.match(condition)) is not None:
        count = _number(match.group("n"))
        return None if count is None else Gate(lore_counters_min=count)
    if (match := _CONTROLS_COUNT_RE.match(condition)) is not None:
        count = _number(match.group("n"))
        noun = match.group("noun").strip().lower()
        if count is None:
            return None
        if noun in _TYPE_NOUNS:
            requirement = ControlledCountRequirement(
                card_type=Type(_TYPE_NOUNS[noun]), threshold=count
            )
        elif (subtype := _singular_subtype(noun)) is not None:
            requirement = ControlledCountRequirement(subtype=subtype, threshold=count)
        else:
            return None
        return Gate(requirements=(requirement,))
    return None


def _merge_gates(first: Gate, second: Gate) -> Gate | None:
    """Both conditions at once, or `None` when both set the same fact."""
    if (
        (first.turn and second.turn)
        or (first.source_tapped is not None and second.source_tapped is not None)
        or (first.lore_counters_min and second.lore_counters_min)
    ):
        return None
    return Gate(
        turn=first.turn or second.turn,
        source_tapped=first.source_tapped
        if first.source_tapped is not None
        else second.source_tapped,
        entered_this_turn=first.entered_this_turn or second.entered_this_turn,
        requirements=first.requirements + second.requirements,
        lore_counters_min=first.lore_counters_min or second.lore_counters_min,
        paired=first.paired or second.paired,
    )


def _split_gate(sentence: str) -> tuple[str, Gate] | None:
    """`sentence` without its leading/trailing condition, and that condition."""
    gate = Gate()
    text = sentence.strip()
    for _ in range(2):
        if (match := _DURING_YOUR_TURN_RE.match(text)) is not None:
            merged = _merge_gates(gate, Gate(turn="your"))
            text = match.group("rest")
        elif (match := _DURING_OTHER_TURNS_RE.match(text)) is not None:
            merged = _merge_gates(gate, Gate(turn="other"))
            text = match.group("rest")
        elif (match := _LEADING_AS_LONG_AS_RE.match(text)) is not None:
            parsed = _parse_condition(match.group("cond"))
            merged = None if parsed is None else _merge_gates(gate, parsed)
            text = match.group("rest")
        else:
            break
        if merged is None:
            return None
        gate = merged
    if (match := _TRAILING_AS_LONG_AS_RE.match(text)) is not None:
        parsed = _parse_condition(match.group("cond"))
        if parsed is None:
            return None
        merged = _merge_gates(gate, parsed)
        if merged is None:
            return None
        gate, text = merged, match.group("rest")
    return text, gate


def _parse_noun(noun: str) -> tuple[tuple[str, ...], tuple[str, ...], bool] | None:
    """(card types, subtypes, tokens) for a group's noun phrase."""
    tokens = False
    phrase = noun.strip()
    low = phrase.lower()
    if low.endswith(" tokens"):
        tokens = True
        phrase = phrase[: -len(" tokens")].strip()
        low = phrase.lower()
    elif low == "tokens":
        return (), (), True
    if low == "permanents":
        return (), (), tokens
    if low in _TYPE_NOUNS:
        return (_TYPE_NOUNS[low],), (), tokens
    if low == "creature":
        return ("creature",), (), tokens
    # "<Subtype> creatures" / "<Subtype>s" / "<Subtype> and <Subtype>s"
    low_words = low.split()
    if len(low_words) >= 2 and low_words[-1] == "creatures":
        phrase = " ".join(phrase.split()[:-1])
        words = [phrase]
        creature = True
    else:
        words = re.split(r"\s+(?:and|or)\s+", phrase)
        creature = False
    subtypes: list[str] = []
    for word in words:
        if not word[:1].isupper():
            return None
        subtype = _singular_subtype(word)
        if subtype is None:
            return None
        subtypes.append(subtype)
    return (("creature",) if creature else ()), tuple(subtypes), tokens


_GROUP_RE = re.compile(
    r"^(?P<other>(?:each )?other )?(?P<each>each )?(?P<state>tapped |untapped )?"
    r"(?P<legendary>legendary )?(?P<nontoken>nontoken )?(?P<noun>.+?) "
    r"(?P<ctrl>you control|your opponents control)(?P<chosen> of the chosen type)?$",
    re.IGNORECASE,
)


def _parse_group(text: str) -> Group | None:
    text = text.strip()
    low = text.lower()
    if low in (
        "this creature",
        "this permanent",
        "this artifact",
        "this enchantment",
        "this land",
        "it",
    ):
        return Group(self_only=True)
    if low in ("enchanted creature", "enchanted land", "enchanted permanent", "enchanted artifact"):
        return Group(attached=True)
    if low == "enchanted creatures you control":
        return Group(card_types=("creature",), enchanted=True)
    if low == "each creature with the greatest mana value":
        return Group(scope="any", card_types=("creature",), greatest_mana_value=True)
    match = _GROUP_RE.match(text)
    if match is None:
        return None
    parsed = _parse_noun(match.group("noun"))
    if parsed is None or match.group("nontoken"):
        return None
    card_types, subtypes, tokens = parsed
    chosen = None
    if match.group("chosen"):
        chosen = "planeswalker_type" if card_types == ("planeswalker",) else "creature_type"
        if subtypes:
            return None
    return Group(
        scope="you" if match.group("ctrl").lower() == "you control" else "opponents",
        other=match.group("other") is not None,
        card_types=card_types,
        subtypes=tuple(subtype.lower() for subtype in subtypes),
        chosen_subtype=chosen,
        legendary=match.group("legendary") is not None,
        tokens=tokens,
        tapped=(match.group("state") or "").strip().lower() or None,
    )


def _parse_subject(text: str) -> tuple[bool, tuple[Group, ...]] | None:
    text = text.strip()
    if text.lower() == "you":
        return True, ()
    if (match := re.match(r"^you(?:, | and )(?P<rest>.+)$", text, re.IGNORECASE)) is not None:
        parts = re.split(r",\s*and\s+|,\s*|\s+and\s+(?=other\b)", match.group("rest"))
        if len(parts) == 1:
            parts = [match.group("rest")]
        groups = [_parse_group(part) for part in parts]
        if any(group is None for group in groups):
            return None
        return True, tuple(group for group in groups if group is not None)
    group = _parse_group(text)
    return None if group is None else (False, (group,))


def _parse_qualities(text: str) -> tuple[str, ...] | None:
    qualities: list[str] = []
    for part in re.split(r",?\s+and\s+from\s+|,\s+from\s+", text.strip().rstrip(".")):
        part = part.strip().lower()
        if not part:
            return None
        if part == "each color":
            qualities.extend(_COLOR_NAMES)
        else:
            qualities.append(_CHOSEN_QUALITY_PLACEHOLDERS.get(part, part))
    return tuple(qualities)


def _parse_items(text: str, verb: str) -> tuple[Item, ...] | None:
    text = text.strip().rstrip(".")
    low = text.lower()
    if verb.lower().startswith("lose"):
        if low == "hexproof and can't have or gain hexproof":
            return (Item("lose_hexproof"),)
        return None
    items: list[Item] = []
    head, _, protection = low.partition("protection from ")
    if protection:
        qualities = _parse_qualities(protection)
        if qualities is None:
            return None
        protection_item = Item("protection", qualities)
    else:
        protection_item = None
    head = head.strip().rstrip(",").strip()
    head = re.sub(r"\s+and$", "", head)
    for token in re.split(r",\s*(?:and\s+)?|\s+and\s+", head) if head else []:
        token = token.strip()
        if not token:
            continue
        if token == "hexproof":
            items.append(Item("hexproof"))
        elif token == "shroud":
            items.append(Item("shroud"))
        elif token.startswith("hexproof from "):
            qualities = _parse_qualities(token[len("hexproof from ") :])
            if qualities is None:
                return None
            items.append(Item("hexproof_from", qualities))
        else:
            keywords = _split_and_validate_keywords(token)
            if keywords is None or len(keywords) != 1:
                return None
            items.append(Item("keyword", keyword=keywords[0]))
    if protection_item is not None:
        items.append(protection_item)
    return tuple(items) or None


_GATE_WORDS = ("hexproof", "shroud", "protection from")


@cache
def parse_static_grant(sentence: str) -> StaticGrant | None:
    """The static hexproof/shroud/protection grant `sentence` states, or `None`.

    A grant that names a keyword outside this family beside hexproof
    ("hexproof and menace") is read whole; a sentence whose subject, condition
    or keyword list this cannot read is `None`, never a partial grant.
    """
    lowered = sentence.lower()
    if not any(word in lowered for word in _GATE_WORDS):
        return None
    text = _strip_reminder(sentence)[0].strip()
    text = _ABILITY_WORD_RE.sub("", text)
    text = text.rstrip(".").strip()
    # "This effect doesn't remove this Aura." rides after the grant (CR 702.16n).
    text = re.sub(r"\.\s+This effect doesn't remove (?:this Aura|[^.]+)$", "", text)
    split = _split_gate(text)
    if split is None:
        return None
    body, gate = split
    match = _MAIN_RE.match(body)
    if match is None:
        return None
    subject = _parse_subject(match.group("subject"))
    items = _parse_items(match.group("items"), match.group("verb"))
    if subject is None or items is None:
        return None
    player, groups = subject
    if match.group("verb").lower().startswith("lose") and player:
        return None
    if player and not groups and not any(item.kind == "protection" for item in items):
        # "You have hexproof." is `player_keyword_grant_of_line`'s own shape.
        return None
    return StaticGrant(player=player, groups=groups, items=items, gate=gate)


# -- layer builder ------------------------------------------------------------


def resolve_qualities(qualities: Sequence[str], source: CardState) -> tuple[str, ...] | None:
    """`qualities` with a "the chosen ..." placeholder replaced by what `source`
    chose as it entered (CR 614.12a), or `None` while nothing is chosen."""
    resolved: list[str] = []
    choice = source.choice
    for quality in qualities:
        if not quality.startswith("<chosen"):
            resolved.append(quality)
            continue
        if choice is None:
            return None
        if quality == "<chosen color>" and choice.kind is ChoiceKind.COLOR:
            resolved.append(Color(choice.value).name.lower())
        elif (
            quality == "<chosen card type>"
            and choice.kind is ChoiceKind.CARD_TYPE
            or quality == "<chosen creature type>"
            and choice.kind is ChoiceKind.CREATURE_TYPE
        ):
            resolved.append(choice.value.lower())
        else:
            return None
    return tuple(resolved)


def _item_modification(item: Item, source: CardState):
    """The layer 6 modification for one granted item, or `None` while a chosen
    quality is not chosen yet."""
    if item.kind == "lose_hexproof":
        return lose_keyword("hexproof")
    if item.kind == "keyword":
        return grant_ability(item.keyword)
    if item.kind in ("hexproof", "shroud"):
        return grant_ability(item.kind)
    qualities = resolve_qualities(item.qualities, source)
    if qualities is None:
        return None
    if item.kind == "hexproof_from":
        return grant_ability("hexproof from " + " and from ".join(qualities))
    return grant_ability("protection from " + " and from ".join(qualities))


def immediate_gate_holds(
    gate: Gate, *, source_tapped: bool, active_is_controller: bool, entered_this_turn: bool
) -> bool:
    """The part of the condition that is a fact about this moment."""
    if gate.turn == "your" and not active_is_controller:
        return False
    if gate.turn == "other" and active_is_controller:
        return False
    if gate.source_tapped is not None and source_tapped != gate.source_tapped:
        return False
    return not (gate.entered_this_turn and not entered_this_turn)


def _selector(group: Group, grant: StaticGrant, source: CardState, context: LayerContext):
    chosen_subtypes: tuple[str, ...] = ()
    if group.chosen_subtype is not None:
        choice = source.choice
        wanted = (
            ChoiceKind.PLANESWALKER_TYPE
            if group.chosen_subtype == "planeswalker_type"
            else ChoiceKind.CREATURE_TYPE
        )
        if choice is None or choice.kind is not wanted:
            return None
        chosen_subtypes = (choice.value.lower(),)
    return StaticGroupGrant(
        source_id=source.id,
        username=source.controller,
        scope=group.scope,
        self_only=group.self_only,
        attached=group.attached,
        other=group.other,
        card_types=tuple(Type(each) for each in group.card_types),
        subtypes=group.subtypes + chosen_subtypes,
        legendary=group.legendary,
        tokens=group.tokens,
        tapped_filter=group.tapped,
        tapped_ids=tuple(sorted(context.tapped_ids, key=str)) if group.tapped else (),
        enchanted=group.enchanted,
        greatest_mana_value=group.greatest_mana_value,
        requirements=grant.gate.requirements,
        lore_counters_min=grant.gate.lore_counters_min,
        paired=grant.gate.paired,
    )


def grant_builder(grant: StaticGrant, *, line: str) -> EffectBuilder:
    """The layer 6 effects of `grant`'s permanent groups (CR 613.1f, CR 611.3)."""

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        if not immediate_gate_holds(
            grant.gate,
            source_tapped=source.tapped,
            active_is_controller=context.active_player == source.controller,
            entered_this_turn=source.id in context.entered_this_turn_ids,
        ):
            return []
        modifications = []
        for item in grant.items:
            modification = _item_modification(item, source)
            if modification is not None:
                modifications.append((item, modification))
        effects: list[ContinuousEffect] = []
        for group in grant.groups:
            selector = _selector(group, grant, source, context)
            if selector is None:
                continue
            for item, modification in modifications:
                effects.append(
                    ContinuousEffect(
                        description=f"{source.name}: {item.kind.replace('_', ' ')}",
                        layer=Layer.ABILITY,
                        timestamp=timestamp,
                        source_id=source.id,
                        source_ability=_source_line_for(source, line),
                        selector=selector,
                        modification=modification,
                    )
                )
        return effects

    return builder


def parse_protection_grant(sentence: str) -> EffectBuilder | None:
    """The layer builder for a static grant sentence, or `None`.
    Tried by `machines/layers._parse_layer_sentence` after its own shapes."""
    grant = parse_static_grant(sentence)
    if grant is None:
        return None
    # The line the effect came from, as `_source_line_for` matches it: without
    # its ability word (CR 207.2c), exactly as every sibling shape passes it.
    return grant_builder(grant, line=_ABILITY_WORD_RE.sub("", sentence.strip()))


# -- player half ---------------------------------------------------------------


def _lines_of(game: "Game", permanent: CardState, board: Any) -> tuple[str, ...]:
    try:
        return tuple(board.of(permanent).abilities)
    except KeyError:
        return tuple(permanent.oracle_text.splitlines())


def _player_grants_of(game: "Game", permanent: CardState, board: Any, owner: str):
    """The grants on `permanent`'s lines that reach its controller `owner`
    (the "you" of the line) and whose condition holds right now."""
    for line in _lines_of(game, permanent, board):
        if "you" not in line.lower():
            continue
        normalized = self_normalized_effect_text(
            permanent.name, line, legendary="Legendary" in str(permanent.supertypes)
        )
        grant = parse_static_grant(normalized)
        if grant is None or not grant.player:
            continue
        turn = game.turn
        if not immediate_gate_holds(
            grant.gate,
            source_tapped=permanent.tapped,
            active_is_controller=turn is not None and turn.active_player == owner,
            entered_this_turn=turn is not None and permanent.turn_entered == turn.turns_taken,
        ):
            continue
        gate_selector = StaticGroupGrant(
            source_id=permanent.id,
            username=owner,
            requirements=grant.gate.requirements,
            lore_counters_min=grant.gate.lore_counters_min,
            paired=grant.gate.paired,
        )
        if not gate_selector.gate_holds(board.characteristics):
            continue
        yield permanent, grant


def player_keyword_grants(
    game: "Game", permanent: CardState, board: Any, owner: str
) -> list[tuple[str, list[str]]]:
    """`(keyword, qualities)` hexproof/shroud grants the line gives its
    controller as a *player* (CR 702.11c, CR 702.18a)."""
    found: list[tuple[str, list[str]]] = []
    for source, grant in _player_grants_of(game, permanent, board, owner):
        for item in grant.items:
            if item.kind in ("hexproof", "shroud"):
                found.append((item.kind, []))
            elif item.kind == "hexproof_from":
                qualities = resolve_qualities(item.qualities, source)
                if qualities is not None:
                    found.append(("hexproof", list(qualities)))
    return found


def player_protection_qualities_of(
    game: "Game", permanent: CardState, board: Any, owner: str
) -> list[str]:
    """Qualities the line gives its controller protection from (CR 702.16a)."""
    found: list[str] = []
    for source, grant in _player_grants_of(game, permanent, board, owner):
        for item in grant.items:
            if item.kind != "protection":
                continue
            qualities = resolve_qualities(item.qualities, source)
            if qualities is not None:
                found.extend(quality for quality in qualities if quality not in found)
    return found


def hexproof_suppressed(game: "Game", target: CardState) -> bool:
    """Whether a "lose hexproof and can't have or gain hexproof" static on the
    battlefield currently covers `target` (CR 702.11e: an effect that makes an
    object lose hexproof makes it lose every "hexproof from" ability too)."""
    if "hexproof" not in "".join(permanent.oracle_text.lower() for permanent in game.battlefield):
        return False
    board = game.computed_board()
    for permanent in game.battlefield:
        if "can't have or gain hexproof" not in permanent.oracle_text.lower():
            continue
        for line in _lines_of(game, permanent, board):
            grant = parse_static_grant(
                self_normalized_effect_text(permanent.name, line, legendary=False)
            )
            if grant is None or not any(item.kind == "lose_hexproof" for item in grant.items):
                continue
            owner = game.controller_of(permanent).username
            for group in grant.groups:
                selector = StaticGroupGrant(
                    source_id=permanent.id,
                    username=owner,
                    scope=group.scope,
                    card_types=tuple(Type(each) for each in group.card_types),
                )
                if selector(board.of(target), board.characteristics):
                    return True
    return False


# -- "can't be the target" restrictions ---------------------------------------


@dataclass(frozen=True)
class Clause:
    """One half of a restriction: the qualities a spell or ability source must
    have to be refused (empty = any), and whether only the restricting
    permanent's opponents are refused."""

    qualities: tuple[str, ...] = ()
    opponents_only: bool = False


@dataclass(frozen=True)
class TargetRestriction:
    """subject: self | attached | zone; for a zone subject `zone_parts` are
    `(zone, card type or None)` pairs."""

    subject: str
    spell: Clause | None
    ability: Clause | None
    zone_parts: tuple[tuple[str, str | None], ...] = ()


_QUAL = r"[a-z]+(?: or [a-z]+)*"
_BODY_RE = re.compile(
    rf"^(?:(?P<sq>{_QUAL}) )?spells(?P<so> your opponents control)?"
    rf"(?: or abilities(?: from (?P<aq>{_QUAL}) sources)?(?P<ao> your opponents control)?)?$",
    re.IGNORECASE,
)
_ABILITY_BODY_RE = re.compile(
    rf"^abilities(?: from (?P<aq>{_QUAL}) sources)?(?P<ao> your opponents control)?$",
    re.IGNORECASE,
)
_RESTRICTION_RE = re.compile(
    r"^(?P<subject>.+?) can't be the targets? of (?P<body>.+?)\.?$", re.IGNORECASE
)
_ZONE_PART_RE = re.compile(
    r"^(?:(?P<type>[a-z]+) )?(?:cards?|(?P<plural>[a-z]+s)) (?P<where>on the battlefield|in graveyards)$",
    re.IGNORECASE,
)


def _quals(text: str | None) -> tuple[str, ...]:
    return tuple(part.strip().lower() for part in text.split(" or ")) if text else ()


def _zone_parts(text: str) -> tuple[tuple[str, str | None], ...] | None:
    parts: list[tuple[str, str | None]] = []
    for piece in re.split(r"\s+and\s+", text.strip()):
        match = _ZONE_PART_RE.match(piece)
        if match is None:
            return None
        zone = (
            "battlefield" if match.group("where").lower() == "on the battlefield" else "graveyard"
        )
        noun = (match.group("type") or match.group("plural") or "").lower()
        if noun == "cards" or noun == "":
            card_type = None
        elif noun in _TYPE_NOUNS:
            card_type = _TYPE_NOUNS[noun]
        elif noun in {each.value for each in Type}:
            card_type = noun
        elif noun.endswith("s") and noun[:-1] in {each.value for each in Type}:
            card_type = noun[:-1]
        else:
            return None
        parts.append((zone, card_type))
    return tuple(parts)


@cache
def parse_target_restriction(line: str) -> TargetRestriction | None:
    """The "can't be the target of ..." restriction `line` states, or `None`."""
    if "can't be the target" not in line.lower():
        return None
    text = _strip_reminder(line)[0].strip()
    match = _RESTRICTION_RE.match(text)
    if match is None:
        return None
    subject_text = match.group("subject").strip()
    body = match.group("body").strip().rstrip(".")
    low = subject_text.lower()
    subject = None
    zone_parts: tuple[tuple[str, str | None], ...] = ()
    if low in ("this creature", "this permanent", "this artifact", "this enchantment", "this land"):
        subject = "self"
    elif low in (
        "enchanted creature",
        "enchanted permanent",
        "enchanted land",
        "enchanted artifact",
    ):
        subject = "attached"
    else:
        parts = _zone_parts(subject_text)
        if parts is not None:
            subject, zone_parts = "zone", parts
    if subject is None:
        return None
    spell = ability = None
    if (both := _BODY_RE.match(body)) is not None:
        sq, aq = _quals(both.group("sq")), _quals(both.group("aq"))
        shared = (
            both.group("ao") is not None
            and both.group("so") is None
            and not sq
            and not aq
            and "abilities" in body.lower()
        )
        spell = Clause(sq, both.group("so") is not None or shared)
        if "abilities" in body.lower():
            ability = Clause(aq, both.group("ao") is not None)
    elif (only := _ABILITY_BODY_RE.match(body)) is not None:
        ability = Clause(_quals(only.group("aq")), only.group("ao") is not None)
    else:
        return None
    return TargetRestriction(subject, spell, ability, zone_parts)


def _quality_matches(quality: str, characteristics: tuple) -> bool:
    from .casting.permissions import has_quality

    colors, types, subtypes, supertypes, _name = characteristics
    if quality.startswith("non") and quality[3:] in (*_COLOR_NAMES, "colorless"):
        return not _quality_matches(quality[3:], characteristics)
    if quality == "colorless":
        return not colors
    return has_quality(
        quality, colors=colors, types=types, subtypes=subtypes, supertypes=supertypes
    )


def _target_in_zone_parts(target: CardState, parts: tuple[tuple[str, str | None], ...]) -> bool:
    from ..models.zone import Zone

    for zone, card_type in parts:
        wanted = Zone.BATTLEFIELD if zone == "battlefield" else Zone.GRAVEYARD
        if target.zone is not wanted:
            continue
        if card_type is None or Type(card_type) in target.types:
            return True
    return False


def static_target_refusal(game: "Game", target: Any, caster: str, source: Any) -> str | None:
    """Why a static "can't be the target of ..." line stops `caster`'s spell or
    ability (whose source object is `source`) from targeting `target`, or `None`.

    A restricting permanent's line applies to its own object (`this creature`),
    to the permanent it is attached to (`enchanted creature`) or to every
    object in a named zone. "Your opponents" is the restricting permanent's
    controller's opponents (the Aura's, for an enchanted subject).
    """
    if not isinstance(target, CardState):
        return None
    from ..models.zone import Zone
    from .triggers import AbilityOnStack

    board = None
    for permanent in game.battlefield:
        text = permanent.oracle_text
        if "can't be the target" not in text.lower():
            continue
        if board is None:
            board = game.computed_board()
        for line in _lines_of(game, permanent, board):
            restriction = parse_target_restriction(
                self_normalized_effect_text(permanent.name, line, legendary=False)
            )
            if restriction is None:
                continue
            if restriction.subject == "self":
                applies = target.id == permanent.id
            elif restriction.subject == "attached":
                applies = permanent.attached_to == target.id
            else:
                applies = _target_in_zone_parts(target, restriction.zone_parts)
            if not applies:
                continue
            is_ability = isinstance(source, AbilityOnStack) or (
                isinstance(source, CardState) and source.zone is not Zone.STACK
            )
            clause = restriction.ability if is_ability else restriction.spell
            if clause is None:
                continue
            owner = game.controller_of(permanent).username
            if clause.opponents_only and caster == owner:
                continue
            if clause.qualities:
                characteristics = game._quality_characteristics_of(source)
                if characteristics is None or not any(
                    _quality_matches(quality, characteristics) for quality in clause.qualities
                ):
                    continue
            what = "abilities" if is_ability else "spells"
            return (
                f"{target.name} can't be the target of {what} ({permanent.name}: "
                f'"{line.strip()}"; CR 101.2, CR 115.2)'
            )
    return None
