"""Static "can't cast" / "can't play" / "can't activate" prohibitions of a
permanent (CR 601.3, CR 101.2, CR 602.5, CR 305.1, CR 604.2, CR 611.3a).

One grammar for the whole family, read off a battlefield permanent's static
line every time the question is asked (a static ability's effect is not "locked
in", CR 611.3a, and ends with its source, CR 604.2):

    [During your turn, | As long as this creature is attacking, ]
    <who> [who <condition>] can't <cast SPELLS | play lands | activate ...>
    <SPELLS> can't be cast

- <who>: "your opponents", "each opponent", "players", "each player", "you",
  "defending player".
- <SPELLS>: a type phrase ("creature", "noncreature", "permanent",
  "nonartifact", "additional nonartifact") followed by "spells" and an optional
  property: "with the chosen name", "with the same name as the exiled card" /
  "... as a card exiled with this permanent", "with mana value 3 or less" /
  "4 or greater" / "equal to the chosen number" / "greater than the number of
  lands that player controls", "with even/odd mana value(s)", "with {X} in
  their mana costs", "of the chosen color", "from anywhere other than their
  hands" / "from graveyards".
- "The same is true for artifacts and enchantments." repeats the previous
  sentence with each type in turn (Ward of Bones).

`parse_static_ban` is a pure, memoised reader of one sentence; the evaluators
(`spell_ban_reason`, `land_play_ban_reason`, `activation_ban_reason`,
`attack_ban_reason`) put a parsed ban to the live game.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import cache
from typing import Any

from ..models.card import Type
from ..models.card_state import ChoiceKind
from ..models.zone import Zone
from .abilities import AbilityKind, parse_abilities, self_normalized_effect_text

_PERMANENT_TYPES = frozenset(
    {Type.ARTIFACT, Type.BATTLE, Type.CREATURE, Type.ENCHANTMENT, Type.LAND, Type.PLANESWALKER}
)
_COLOR_LETTERS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}

_PARENTHETICAL_RE = re.compile(r"\s*\([^)]*\)")
_SAME_TRUE_RE = re.compile(
    r"^the same is true for (?P<types>[a-z, ]+?)(?: and (?P<last>[a-z]+))?$", re.IGNORECASE
)
_SENTENCE_RE = re.compile(
    r"^(?:(?P<when>during your turn|as long as this (?:creature|permanent|artifact|enchantment) "
    r"is attacking), )?"
    r"(?P<who>your opponents|each opponent|players|each player|you|defending player)"
    r"(?: who (?P<whocond>(?:(?:has |have )?(?:cast|attacked with|controls? more)\b)[^,]*?))?"
    r" can't (?P<verb>cast|play|activate|attack) (?P<rest>.+)$",
    re.IGNORECASE,
)
_PASSIVE_RE = re.compile(r"^(?P<rest>.+?) can't be cast$", re.IGNORECASE)
_SPELLS_RE = re.compile(
    r"^(?P<additional>additional )?(?P<types>(?:[a-z-]+ )*?)spells?"
    r"(?P<tail>(?: with | of | from ).+)?$",
    re.IGNORECASE,
)
_ACTIVATE_TAIL_RE = re.compile(
    r"^(?P<head>.+?) or activate abilities of (?P<what>.+)$",
    re.IGNORECASE,
)
_MV_COMPARE_RE = re.compile(
    r"^with mana values? (?P<n>\d+) or (?P<dir>less|greater)$", re.IGNORECASE
)
_WHOCOND_TYPE_RE = re.compile(
    r"^(?:has |have )?cast an? (?P<type>non[a-z]+|[a-z]+)? ?spell this turn$"
)
_WHOCOND_MORE_RE = re.compile(r"^controls? more (?P<what>[a-z]+) than you$")


@dataclass(frozen=True)
class StaticBan:
    """One parsed prohibition (see the module docstring for the grammar)."""

    sentence: str
    who: str  # opponents | players | you | defending
    verb: str  # cast | play | activate | attack
    when: str | None = None  # "your turn" | "attacking"
    whocond: tuple[str, str] | None = None  # (kind, argument)
    # spells
    types: tuple[str, ...] = ()  # type words, e.g. ("noncreature",)
    additional: bool = False
    prop: tuple[str, Any] | None = None  # (kind, argument)
    from_other_than_hand: bool = False
    zones: frozenset[Zone] = frozenset()
    # "or activate abilities of <types>" riders and activation bans
    activate_types: tuple[Type, ...] | None = None  # None: no activation clause
    activate_cards_in_graveyards: bool = False
    loyalty_only: bool = False


def _type_predicate(word: str) -> Callable[[tuple[Type, ...]], bool] | None:
    lowered = word.lower()
    if lowered == "permanent":
        return lambda types: bool(_PERMANENT_TYPES & set(types))
    negated = lowered.startswith("non")
    core = lowered[3:].lstrip("-") if negated else lowered
    card_type = next((each for each in Type if each.value == core), None)
    if card_type is None:
        return None
    return lambda types: (card_type in types) != negated


def _plural_type(word: str) -> Type | None:
    singular = word.strip().lower().rstrip("s")
    return next((each for each in Type if each.value == singular), None)


@cache
def parse_static_ban(sentence: str) -> StaticBan | None:
    """Read one static sentence as a prohibition, or None."""
    text = _PARENTHETICAL_RE.sub("", sentence).strip().rstrip(".").strip()
    lowered = text.lower()
    if "can't" not in lowered:
        return None
    match = _SENTENCE_RE.match(text)
    if match is not None:
        who = {
            "your opponents": "opponents",
            "each opponent": "opponents",
            "players": "players",
            "each player": "players",
            "you": "you",
            "defending player": "defending",
        }[match["who"].lower()]
        when = None
        if match["when"]:
            when = "your turn" if match["when"].lower().startswith("during") else "attacking"
        whocond = None
        if match["whocond"]:
            whocond = _parse_whocond(match["whocond"].strip().lower())
            if whocond is None:
                return None
        verb = match["verb"].lower()
        rest = match["rest"].strip()
        base = StaticBan(sentence=text, who=who, verb=verb, when=when, whocond=whocond)
        if verb == "activate":
            return _parse_activation(base, rest)
        if verb == "attack":
            return base if rest.lower() == "with creatures" else None
        if verb == "play":
            return base if rest.lower() == "lands" else None
        return _parse_spell_phrase(base, rest)
    passive = _PASSIVE_RE.match(text)
    if passive is not None:
        base = StaticBan(sentence=text, who="players", verb="cast")
        return _parse_spell_phrase(base, passive["rest"].strip())
    return None


def _parse_whocond(text: str) -> tuple[str, str] | None:
    if text in ("cast a spell this turn",):
        return ("cast", "")
    typed = _WHOCOND_TYPE_RE.match(text)
    if typed is not None:
        return ("cast", typed["type"] or "")
    if text == "attacked with a creature this turn":
        return ("attacked", "")
    more = _WHOCOND_MORE_RE.match(text)
    if more is not None:
        return ("more", more["what"])
    return None


def _parse_activation(base: StaticBan, rest: str) -> StaticBan | None:
    lowered = rest.lower()
    if lowered == "planeswalkers' loyalty abilities":
        return replace(base, activate_types=(Type.PLANESWALKER,), loyalty_only=True)
    return None


def _parse_spell_phrase(base: StaticBan, rest: str) -> StaticBan | None:
    activate = None
    graveyard_abilities = False
    tail_match = _ACTIVATE_TAIL_RE.match(rest)
    if tail_match is not None:
        rest = tail_match["head"].strip()
        what = tail_match["what"].strip().lower()
        if what == "cards in graveyards":
            graveyard_abilities = True
        else:
            words = [w.strip() for w in re.split(r",|\band\b|\bor\b", what) if w.strip()]
            parsed = [_plural_type(word) for word in words]
            if not parsed or any(each is None for each in parsed):
                return None
            activate = tuple(each for each in parsed if each is not None)
    match = _SPELLS_RE.match(rest)
    if match is None:
        return None
    types = tuple(match["types"].split())
    if any(_type_predicate(word) is None for word in types):
        return None
    ban = replace(
        base,
        types=types,
        additional=match["additional"] is not None,
        activate_types=activate,
        activate_cards_in_graveyards=graveyard_abilities,
    )
    tail = (match["tail"] or "").strip()
    if not tail:
        return ban
    return _parse_tail(ban, tail)


def _parse_tail(ban: StaticBan, tail: str) -> StaticBan | None:
    lowered = tail.lower()
    if lowered == "with the chosen name":
        return replace(ban, prop=("chosen_name", None))
    if lowered == "with the same name as the exiled card":
        return replace(ban, prop=("exiled_name", None))
    if re.fullmatch(r"with the same name as a card exiled with (?:this \w+|[\w' ,-]+)", lowered):
        return replace(ban, prop=("exiled_name", None))
    compare = _MV_COMPARE_RE.match(tail)
    if compare is not None:
        return replace(ban, prop=("mv_" + compare["dir"], int(compare["n"])))
    if lowered in ("with even mana values", "with even mana value"):
        return replace(ban, prop=("mv_parity", 0))
    if lowered in ("with odd mana values", "with odd mana value"):
        return replace(ban, prop=("mv_parity", 1))
    if lowered == "with mana value equal to the chosen number":
        return replace(ban, prop=("mv_chosen", None))
    if lowered == "with mana value greater than the number of lands that player controls":
        return replace(ban, prop=("mv_lands", None))
    if re.fullmatch(r"with \{x\} in (?:their|its) mana costs?", lowered):
        return replace(ban, prop=("has_x", None))
    if lowered == "of the chosen color" or lowered == "of the chosen colour":
        return replace(ban, prop=("chosen_color", None))
    if lowered == "from anywhere other than their hands":
        return replace(ban, from_other_than_hand=True)
    zones = re.fullmatch(r"from (?P<zones>graveyards?)", lowered)
    if zones is not None:
        return replace(ban, zones=frozenset({Zone.GRAVEYARD}))
    return None


def parse_static_bans(text: str, *, card_name: str | None = None, legendary: bool = False):
    """Every ban the sentences of one static line state, "the same is true for"
    expansions included; None when any sentence of the line is not a ban."""
    line = text
    if card_name is not None:
        line = self_normalized_effect_text(card_name, line, legendary=legendary)
    sentences = [s.strip() for s in re.split(r"(?<=\.)\s+", line.strip()) if s.strip()]
    if not sentences:
        return None
    bans: list[StaticBan] = []
    for sentence in sentences:
        same = _SAME_TRUE_RE.match(_PARENTHETICAL_RE.sub("", sentence).strip().rstrip("."))
        if same is not None and bans:
            previous = bans[-1]
            words = [w.strip() for w in re.split(r",|\band\b", same["types"]) if w.strip()]
            if same["last"]:
                words.append(same["last"])
            for word in words:
                card_type = _plural_type(word)
                if card_type is None or previous.types != ("creature",):
                    return None
                whocond = previous.whocond
                if whocond is not None and whocond[0] == "more":
                    whocond = ("more", word.lower())
                bans.append(replace(previous, types=(card_type.value,), whocond=whocond))
            continue
        ban = parse_static_ban(sentence)
        if ban is None:
            return None
        bans.append(ban)
    return tuple(bans)


def reads_static_ban_line(printing, text: str, *, card_name: str | None = None) -> bool:
    """Whether every sentence of this static line is a prohibition this module
    enforces - the audit's question (`static_audit`)."""
    lowered = text.lower()
    if "can't" not in lowered:
        return False
    from ..models.card import Supertype

    legendary = Supertype.LEGENDARY in printing.supertypes
    return (
        parse_static_bans(text, card_name=card_name or printing.name, legendary=legendary)
        is not None
    )


# --------------------------------------------------------------------------
# Evaluation against the live game
# --------------------------------------------------------------------------


def _live_bans(game: Any):
    """(source, controller, ban) for every prohibition a battlefield permanent
    states right now (CR 604.2, CR 611.3a)."""
    for source in list(game.battlefield):
        printed = source.oracle_text or ""
        if "can't" not in printed.lower():
            continue
        from ..models.card import Supertype

        legendary = Supertype.LEGENDARY in source.card.supertypes
        controller = game.controller_of(source).username
        for line in parse_abilities(source.card):
            if line.kind is not AbilityKind.STATIC:
                continue
            text = (line.text or "").strip()
            if "can't" not in text.lower():
                continue
            bans = parse_static_bans(text, card_name=source.card.name, legendary=legendary)
            if bans is None:
                continue
            if not _still_has_line(game, source, text):
                continue
            for ban in bans:
                yield source, controller, ban


def _plain(text: str) -> str:
    return _PARENTHETICAL_RE.sub("", text).replace(" .", ".").strip().rstrip(".").strip()


def _still_has_line(game: Any, source: Any, text: str) -> bool:
    """Whether the computed board still shows this static line on `source`
    (CR 613.1f: a permanent that lost all abilities states no prohibition),
    compared with reminder text and spacing ignored."""
    try:
        computed = game.characteristics_of(source).abilities
    except KeyError:
        return True
    if not computed:
        return not (source.oracle_text or "").strip()
    wanted = _plain(text)
    return any(wanted in _plain(line) or _plain(line) in wanted for line in computed)


def _who_applies(game: Any, source: Any, controller: str, ban: StaticBan, player: str) -> bool:
    if ban.who == "opponents" and player == controller:
        return False
    if ban.who == "you" and player != controller:
        return False
    if ban.when == "your turn" and game.turn.active_player != controller:
        return False
    if ban.who == "defending" or ban.when == "attacking":
        if not game.is_attacking(source):
            return False
        from .combat import defending_player

        defenders = {
            defending_player(game, attack.defender)
            for attack in game.combat.attacks
            if attack.attacker_id == source.id
        }
        if player not in defenders:
            return False
    return ban.whocond is None or _whocond_holds(game, controller, ban, player)


def _whocond_holds(game: Any, controller: str, ban: StaticBan, player: str) -> bool:
    kind, arg = ban.whocond  # type: ignore[misc]
    if kind == "cast":
        predicate = _type_predicate(arg) if arg else None
        return any(
            predicate is None or predicate(tuple(spell.types))
            for spell in game.spells_cast_this_turn.get(player, [])
        )
    if kind == "attacked":
        return game.turn_fact_holds("attacked", player)
    # "controls more <things> than you"
    card_type = _plural_type(arg)
    if card_type is None:
        return False

    def count(username: str) -> int:
        return sum(
            1
            for permanent in game.permanents_controlled_by(username)
            if game._has_computed_type(permanent, card_type)
        )

    return count(player) > count(controller)


@dataclass(frozen=True)
class _SpellFacts:
    names: frozenset[str]
    types: tuple[Type, ...]
    colors: frozenset[str]
    mana_value: int
    has_x: bool
    zone: Zone


def _all_names(card: Any) -> set[str]:
    """Every name a card answers to: its own and, for a split or adventurer
    card, each half's (CR 201.4b)."""
    full = card.card.name
    return {card.name, full, *(part.strip() for part in full.split("//"))}


def _spell_facts(spell: Any, face: str | None, types: tuple[Type, ...]) -> _SpellFacts:
    from ..models.mana import ManaCost

    names = _all_names(spell)
    cost = spell.mana_cost or ""
    colors = {color.value for color in spell.colors}
    value = int(spell.mana_value)
    for each in spell.card.card_faces or []:
        if face is not None and each.name == face:
            names = {each.name}
            cost = each.mana_cost or ""
            colors = {color.value for color in (each.colors or [])}
            value = int(ManaCost.parse(cost).converted) if cost else 0
    return _SpellFacts(
        names=frozenset(names),
        types=types,
        colors=frozenset(colors),
        mana_value=value,
        has_x="{X}" in cost,
        zone=spell.zone,
    )


def _spell_matches(game: Any, source: Any, ban: StaticBan, facts: _SpellFacts, caster: str) -> bool:
    for word in ban.types:
        predicate = _type_predicate(word)
        if predicate is None or not predicate(facts.types):
            return False
    if ban.additional and not game.spells_cast_this_turn.get(caster):
        return False
    if ban.from_other_than_hand and facts.zone is Zone.HAND:
        return False
    if ban.zones and facts.zone not in ban.zones:
        return False
    if ban.prop is None:
        return True
    kind, arg = ban.prop
    choice = source.choice
    if kind == "chosen_name":
        return (
            choice is not None
            and choice.kind is ChoiceKind.CARD_NAME
            and choice.value in facts.names
        )
    if kind == "exiled_name":
        exiled = game.cards_exiled_with(source.id, source.zone_change_stamp)
        return any(facts.names & _all_names(card) for card in exiled)
    if kind == "mv_less":
        return facts.mana_value <= arg
    if kind == "mv_greater":
        return facts.mana_value >= arg
    if kind == "mv_parity":
        return facts.mana_value % 2 == arg
    if kind == "mv_chosen":
        return (
            choice is not None
            and choice.kind is ChoiceKind.NUMBER
            and facts.mana_value == int(choice.value)
        )
    if kind == "mv_lands":
        lands = sum(
            1
            for permanent in game.permanents_controlled_by(caster)
            if game._has_computed_type(permanent, Type.LAND)
        )
        return facts.mana_value > lands
    if kind == "has_x":
        return facts.has_x
    if kind == "chosen_color":
        return (
            choice is not None
            and choice.kind in (ChoiceKind.COLOR, ChoiceKind.COLOR_WORD)
            and (
                choice.value in facts.colors
                or _COLOR_LETTERS.get(choice.value.lower()) in facts.colors
            )
        )
    return False


def spell_ban_reason(
    game: Any, spell: Any, caster: str, face: str | None, types: tuple[Type, ...]
) -> str | None:
    """Why a static prohibition on the battlefield stops `caster` casting
    `spell` (as `face`, with the evaluated card `types`), or None (CR 601.3,
    CR 101.2)."""
    facts = None
    for source, controller, ban in _live_bans(game):
        if ban.verb != "cast":
            continue
        if not _who_applies(game, source, controller, ban, caster):
            continue
        if facts is None:
            facts = _spell_facts(spell, face, types)
        if _spell_matches(game, source, ban, facts, caster):
            return (
                f'{source.name} says "{ban.sentence}": {caster} can\'t cast {spell.name} '
                f"(CR 601.3, CR 101.2)"
            )
    return None


def land_play_ban_reason(game: Any, player: str) -> str | None:
    """Why a static "can't play lands" stops `player` playing a land (CR 305.1,
    CR 101.2), or None."""
    for source, controller, ban in _live_bans(game):
        if ban.verb == "play" and _who_applies(game, source, controller, ban, player):
            return (
                f'{source.name} says "{ban.sentence}": {player} can\'t play lands '
                f"(CR 305.1, CR 101.2)"
            )
    return None


def activation_ban_reason(
    game: Any, obj: Any, activator: str, *, is_loyalty: bool = False
) -> str | None:
    """Why a static prohibition stops `activator` activating an ability of
    `obj`, or None (CR 602.5)."""
    for source, controller, ban in _live_bans(game):
        if ban.verb == "activate" and ban.loyalty_only:
            if not is_loyalty:
                continue
        elif ban.verb == "cast" and ban.activate_cards_in_graveyards:
            if obj.zone is not Zone.GRAVEYARD:
                continue
        elif ban.verb == "cast" and ban.activate_types is not None:
            if obj.zone is not Zone.BATTLEFIELD or not any(
                game._has_computed_type(obj, each) for each in ban.activate_types
            ):
                continue
        else:
            continue
        if not _who_applies(game, source, controller, ban, activator):
            continue
        return (
            f"{obj.name}'s abilities can't be activated by {activator}: {source.name} says "
            f'"{ban.sentence}" (CR 602.5, CR 101.2)'
        )
    return None


def attack_ban_reason(game: Any, attacker: Any) -> str | None:
    """Why a static "can't attack with creatures" stops `attacker`'s controller
    attacking (Angelic Arbiter), or None (CR 508.1c)."""
    player = game.controller_of(attacker).username
    for source, controller, ban in _live_bans(game):
        if ban.verb == "attack" and _who_applies(game, source, controller, ban, player):
            return f'{source.name} says "{ban.sentence}" (CR 508.1c)'
    return None


# --------------------------------------------------------------------------
# A spell's own casting restriction (CR 601.2e, CR 601.3)
# --------------------------------------------------------------------------

_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}
_OWN_TURN_GATE_RE = re.compile(
    r"you can'?t cast (?:this \w+|[^.]+?) during your "
    r"(?P<ords>(?:first|second|third|fourth|fifth)"
    r"(?:(?:,? or|,| and) (?:first|second|third|fourth|fifth))*) "
    r"turns? of the game",
    re.IGNORECASE,
)
_SELF_UNLESS_RE = re.compile(
    r"(?:you can'?t cast this \w+ unless|cast this spell only if) (?P<condition>[^.]+)\.",
    re.IGNORECASE,
)


def self_normalized_oracle(spell: Any) -> str:
    """The spell's oracle text with its own name read as "this <type>"."""
    from ..models.card import Supertype

    return self_normalized_effect_text(
        spell.card.name,
        spell.oracle_text or "",
        legendary=Supertype.LEGENDARY in spell.card.supertypes,
    )


def self_turn_gate_reason(spell: Any, caster: str, game: Any) -> str | None:
    """ "You can't cast ~ during your first, second, or third turns of the
    game." (Serra Avenger, Spider-Man 2099): refused while the number of
    turns `caster` has begun (`TurnMachine.own_turns_taken`, CR 102.1) is one
    of the printed ordinals."""
    match = _OWN_TURN_GATE_RE.search(self_normalized_oracle(spell))
    if match is None or game.turn is None:
        return None
    banned = {
        _ORDINALS[word]
        for word in re.findall(r"first|second|third|fourth|fifth", match["ords"].lower())
    }
    taken = game.turn.own_turns_taken(caster)
    if taken in banned:
        return (
            f"{spell.name} can't be cast during {caster}'s turn number {taken} of the game "
            f'("{match.group(0)}") (CR 601.3, CR 101.2)'
        )
    return None


def reads_self_cast_restriction_line(text: str, *, card_name: str, legendary: bool) -> bool:
    """Whether a spell's own "Cast this spell only if <readable condition>" /
    "You can't cast ~ unless <readable condition>" / "... during your first
    turns of the game" line is one `Casting` enforces (the audit's question)."""
    from ..models.game._conditions import condition_is_readable

    normalized = self_normalized_effect_text(card_name, text, legendary=legendary)
    if _OWN_TURN_GATE_RE.fullmatch(normalized.strip().rstrip(".")):
        return True
    match = _SELF_UNLESS_RE.fullmatch(normalized.strip())
    return match is not None and condition_is_readable(match["condition"].strip())
