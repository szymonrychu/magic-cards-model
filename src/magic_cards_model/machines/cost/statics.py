"""Readers shared by every static cost-modification sentence (CR 601.2f,
118.7, 602.2b): which objects a printed quality names, what a "for each"
count or a "where X is" expression is worth, and when an "if" condition holds.

A self reduction ("This spell costs {1} less to cast for each ..."), a group
spell modifier ("Creature spells with flying you cast cost {1} less") and an
activated-ability modifier ("Equip abilities you activate cost {1} less") all
price the same few things, so each is read once here and the three sentence
shapes only choose which primitive they need. Everything is recomputed each
time a cost is determined (CR 601.2f, CR 611.3a) - nothing is locked in early.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING, Any

from ...data.creature_types import creature_types
from ...data.subtypes import canonical_subtype
from ...models.card import Color, Supertype, Type
from ...numbers import parse_count

if TYPE_CHECKING:
    from ...models.card_state import CardState
    from ...models.game import Game


@dataclass(frozen=True)
class CostContext:
    """What a count, an expression or a condition is evaluated against: the
    game, the player whose cost it is (`owner`), the spell (or the ability's
    source) being priced, the permanent carrying a static line (`source`),
    the targets announced at CR 601.2c, and the `Casting` when there is one
    (its record carries "bargained")."""

    game: "Game"
    owner: str
    spell: "CardState | None" = None
    source: "CardState | None" = None
    targets: tuple[Any, ...] = ()
    casting: Any = None


# --------------------------------------------------------------------------
# Object quality: "creature spells with flying", "noncreature artifacts"
# --------------------------------------------------------------------------

_TYPE_NOUNS: dict[str, Type] = {t.value: t for t in Type}
_COLOR_NOUNS: dict[str, Color] = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}
_NUMERIC = re.compile(
    r" with (?P<stat>mana value|power|toughness) (?P<n>\w+) or (?P<cmp>greater|less)$"
)
_KEYWORD_TAIL = re.compile(r" with (?P<keyword>[a-z]+)$")
_ADVENTURE_TAIL = re.compile(r" (?:that|which) (?:has|have) an adventure$")
_COLOR_TAIL = re.compile(
    r" that(?:'s| is) (?P<colors>(?:white|blue|black|red|green)"
    r"(?: or (?:white|blue|black|red|green))*)$"
)
_MUTATE_TAIL = re.compile(r" if it has (?P<keyword>[a-z]+)$")
_FILLER = {
    "spell",
    "spells",
    "card",
    "cards",
    "permanents",
    "each",
    "other",
    "another",
    "a",
    "an",
    "the",
}

#: A predicate over `(game, object, view)`: `view` is the object's computed
#: characteristics on the battlefield, or the object itself off it.
Quality = Callable[["Game", "CardState"], bool]


def _view(game: "Game", state: "CardState") -> Any:
    from ...models.zone import Zone

    return game.characteristics_of(state) if state.zone is Zone.BATTLEFIELD else state


def _stat(view: Any, stat: str) -> float | None:
    if stat == "mana value":
        return view.mana_value
    return getattr(view, stat)


@cache
def object_quality(phrase: str) -> Quality | None:
    """A predicate for a printed object quality, or `None` when any word of it
    is unread (the caller then leaves the whole sentence unread rather than
    pricing on a guess)."""
    text = phrase.strip().lower().rstrip(".")
    tests: list[Quality] = []
    for _ in range(3):
        numeric = _NUMERIC.search(text)
        if numeric is not None:
            bound = parse_count(numeric.group("n"))
            if bound is None:
                return None
            stat, greater = numeric.group("stat"), numeric.group("cmp") == "greater"

            def stat_test(game, state, stat=stat, bound=bound, greater=greater) -> bool:
                value = _stat(_view(game, state), stat)
                return value is not None and ((value >= bound) if greater else (value <= bound))

            tests.append(stat_test)
            text = text[: numeric.start()]
            continue
        if _ADVENTURE_TAIL.search(text):
            tests.append(lambda game, state: getattr(state.card.layout, "value", "") == "adventure")
            text = _ADVENTURE_TAIL.sub("", text)
            continue
        colors = _COLOR_TAIL.search(text)
        if colors is not None:
            wanted = {_COLOR_NOUNS[w] for w in colors.group("colors").split(" or ")}
            tests.append(
                lambda game, state, wanted=wanted: bool(wanted & set(_view(game, state).colors))
            )
            text = text[: colors.start()]
            continue
        keyword = _KEYWORD_TAIL.search(text)
        if keyword is not None:
            word = keyword.group("keyword")

            def keyword_test(game, state, word=word) -> bool:
                from ..combat import has_keyword

                return has_keyword(state, word, game)

            tests.append(keyword_test)
            text = text[: keyword.start()]
            continue
        break
    adjectives: list[Quality] = []
    nouns: list[Quality] = []
    colors_any: list[Color] = []
    for raw in re.split(r"[\s,]+", text.replace("and/or", "or")):
        word = raw.strip()
        if not word or word in _FILLER or word in {"and", "or"}:
            continue
        singular = word[:-1] if word.endswith("s") and word[:-1] in _TYPE_NOUNS else word
        if singular.startswith("non") and singular[3:] in _TYPE_NOUNS:
            banned = _TYPE_NOUNS[singular[3:]]
            adjectives.append(
                lambda game, state, banned=banned: banned not in _view(game, state).types
            )
        elif word in _COLOR_NOUNS:
            colors_any.append(_COLOR_NOUNS[word])
        elif word == "colorless":
            adjectives.append(lambda game, state: not _view(game, state).colors)
        elif word in {s.value for s in Supertype}:
            sup = Supertype(word)
            adjectives.append(lambda game, state, sup=sup: sup in _view(game, state).supertypes)
        elif word == "historic":
            adjectives.append(lambda game, state: _is_historic(_view(game, state)))
        elif word == "permanent":
            nouns.append(
                lambda game, state: bool(
                    set(_view(game, state).types)
                    & {Type.ARTIFACT, Type.CREATURE, Type.ENCHANTMENT, Type.LAND, Type.PLANESWALKER}
                )
            )
        elif singular in _TYPE_NOUNS:
            kind = _TYPE_NOUNS[singular]
            nouns.append(lambda game, state, kind=kind: kind in _view(game, state).types)
        elif (sub := canonical_subtype(word)) is not None:
            nouns.append(
                lambda game, state, sub=sub: sub in {s.lower() for s in _view(game, state).subtypes}
            )
        else:
            return None
    if colors_any:
        wanted_colors = set(colors_any)
        adjectives.append(lambda game, state: bool(wanted_colors & set(_view(game, state).colors)))
    parts = [*adjectives, *tests]

    def quality(game: "Game", state: "CardState") -> bool:
        if not all(test(game, state) for test in parts):
            return False
        return not nouns or any(test(game, state) for test in nouns)

    return quality


def _is_historic(view: Any) -> bool:
    """CR 700.6: legendary, an artifact, or a Saga."""
    return (
        Supertype.LEGENDARY in view.supertypes
        or Type.ARTIFACT in view.types
        or "saga" in {s.lower() for s in view.subtypes}
    )


def permanents_matching(
    ctx: CostContext, quality: Quality, *, controlled: bool = True
) -> list["CardState"]:
    game = ctx.game
    pool = game.permanents_controlled_by(ctx.owner) if controlled else list(game.battlefield)
    return [state for state in pool if quality(game, state)]


# --------------------------------------------------------------------------
# "for each <count>"
# --------------------------------------------------------------------------

Reader = Callable[[CostContext], int]

_GRAVEYARD_AND_EXILE = re.compile(r"^(?P<q>.+?) cards? you own in exile and in your graveyard$")
_GRAVEYARD_CARDS = re.compile(r"^(?P<q>.+?) cards? in your graveyard$")
_COUNTERS_ON_PERMANENTS = re.compile(
    r"^permanents? you control with (?P<kind>[a-z+/0-9-]+) counters? on (?:it|them)$"
)
_PERMANENTS_YOU_CONTROL = re.compile(r"^(?P<q>.+?) you control$")


def _counter_amount(state: "CardState", kind_word: str) -> int:
    from .text import _counter_kind_word

    return state.counters[_counter_kind_word(kind_word)]


def cost_count(phrase: str) -> Reader | None:
    """A "for each `<phrase>`" count as a reader, or `None` when unread."""
    text = phrase.strip().lower().rstrip(".")
    text = re.sub(r"^(?:the number of )", "", text)
    if text in {"creature that died this turn", "creatures that died this turn"}:
        return lambda ctx: ctx.game.creatures_died_this_turn
    if text in {"creature in your party", "creatures in your party"}:
        from ..designations import party_size

        return lambda ctx: party_size(ctx.game, ctx.owner)
    if text in {"creature you attacked with this turn", "creatures you attacked with this turn"}:

        def attacked(ctx: CostContext) -> int:
            count = 0
            for card_id in ctx.game.attacked_this_turn:
                state = ctx.game.find_by_id(card_id)
                if state is not None and state.controller_or_owner == ctx.owner:
                    count += 1
            return count

        return attacked
    if text in {
        "creature type among creatures you control",
        "creature types among creatures you control",
    }:
        return _creature_type_count
    if text in {"modified creature you control", "modified creatures you control"}:
        from ..conditions.board import permanent_is_modified

        def modified(ctx: CostContext) -> int:
            game = ctx.game
            return sum(
                1
                for state in game.permanents_controlled_by(ctx.owner)
                if game.characteristics_of(state).is_creature
                and permanent_is_modified(game, state, game.characteristics_of(state))
            )

        return modified
    if text in {"other spell cast this turn", "other spells cast this turn"}:
        return lambda ctx: sum(len(spells) for spells in ctx.game.spells_cast_this_turn.values())
    if text in {"creature it targets", "creatures it targets"}:

        def targeted(ctx: CostContext) -> int:
            game = ctx.game
            count = 0
            for target in ctx.targets:
                state = (
                    game.find_by_id(target.card_id) if getattr(target, "card_id", None) else None
                )
                if state is not None and game.characteristics_of(state).is_creature:
                    count += 1
            return count

        return targeted
    both = _GRAVEYARD_AND_EXILE.match(text)
    if both is not None:
        quality = object_quality(both.group("q"))
        if quality is None:
            return None

        def graveyard_and_exile(ctx: CostContext) -> int:
            game = ctx.game
            cards = [*game.player(ctx.owner).graveyard, *game.face_up_cards_in_exile(ctx.owner)]
            return sum(1 for card in cards if quality(game, card))

        return graveyard_and_exile
    counters = _COUNTERS_ON_PERMANENTS.match(text)
    if counters is not None:
        kind = counters.group("kind")
        return lambda ctx: sum(
            1
            for state in ctx.game.permanents_controlled_by(ctx.owner)
            if _counter_amount(state, kind) > 0
        )
    yours = _PERMANENTS_YOU_CONTROL.match(text)
    if yours is not None:
        quality = object_quality(yours.group("q"))
        if quality is not None and "creature type" not in text:
            return lambda ctx: len(permanents_matching(ctx, quality))
    from ..effects import _for_each_multiplier

    existing = _for_each_multiplier(phrase)
    if existing is None:
        return None
    return lambda ctx: existing(
        ctx.game,
        ctx.owner,
        str(ctx.source.id) if ctx.source else (str(ctx.spell.id) if ctx.spell else None),
    )


def _creature_type_count(ctx: CostContext) -> int:
    """CR 205.3m's creature types among the creatures `owner` controls; a
    changeling is every one of them (CR 702.73a)."""
    known = set(creature_types())
    found: set[str] = set()
    for state in ctx.game.permanents_controlled_by(ctx.owner):
        chars = ctx.game.characteristics_of(state)
        if chars.is_creature:
            found.update(s for s in chars.subtypes if s in known)
    return len(found)


# --------------------------------------------------------------------------
# "where X is <expression>"
# --------------------------------------------------------------------------

_TOTAL_STAT = re.compile(
    r"^the total (?P<stat>power|toughness|mana value) of (?P<q>.+?) you control$"
)
_SOURCE_POWER = re.compile(r"^(?:this (?:creature|permanent)|[a-z' ,-]+?)'s power$")


def cost_expression(expression: str) -> Reader | None:
    """A "where X is `<expression>`" amount as a reader, or `None`."""
    text = expression.strip().lower().rstrip(".")
    total = _TOTAL_STAT.match(text)
    if total is not None:
        quality = object_quality(total.group("q"))
        if quality is None:
            return None
        stat = total.group("stat")

        def total_stat(ctx: CostContext) -> int:
            return sum(
                int(_stat(ctx.game.characteristics_of(state), stat) or 0)
                for state in permanents_matching(ctx, quality)
            )

        return total_stat
    if text == "your speed":
        return lambda ctx: ctx.game.player(ctx.owner).speed or 0
    if text == "the total amount of noncombat damage dealt to your opponents this turn":
        return lambda ctx: sum(
            amount
            for player, amount in ctx.game.noncombat_damage_to_players_this_turn.items()
            if player != ctx.owner
        )
    if _SOURCE_POWER.match(text):

        def source_power(ctx: CostContext) -> int:
            source = ctx.source
            return max(ctx.game.power_of(source) or 0, 0) if source is not None else 0

        return source_power
    from ..effects import amount_expression

    existing = amount_expression(expression)
    if existing is None:
        return None
    return lambda ctx: existing(ctx.game, ctx.owner, ctx.source or ctx.spell, 0)


# --------------------------------------------------------------------------
# "if <condition>"
# --------------------------------------------------------------------------

_MORE_CREATURES = re.compile(r"^an opponent controls at least (?P<n>\w+) more creatures than you$")
_TOTAL_IN_GRAVEYARDS = re.compile(
    r"^there are (?P<n>\w+) or more (?P<q>.+?) cards? total in all graveyards$"
)
_BARGAINED = re.compile(r"^it(?:'s| is| was) bargained$")


def cost_condition(condition: str) -> Callable[[CostContext], bool] | None:
    """An "if `<condition>`" gate as a predicate, or `None` when unread."""
    text = condition.strip().lower().rstrip(".")
    more = _MORE_CREATURES.match(text)
    if more is not None:
        bound = parse_count(more.group("n"))
        if bound is None:
            return None

        def opponent_has_more(ctx: CostContext) -> bool:
            game = ctx.game

            def creatures(player: str) -> int:
                return sum(
                    1
                    for s in game.permanents_controlled_by(player)
                    if game.characteristics_of(s).is_creature
                )

            mine = creatures(ctx.owner)
            return any(
                creatures(other.username) - mine >= bound
                for other in game.players
                if other.username != ctx.owner
            )

        return opponent_has_more
    total = _TOTAL_IN_GRAVEYARDS.match(text)
    if total is not None:
        bound = parse_count(total.group("n"))
        quality = object_quality(total.group("q"))
        if bound is None or quality is None:
            return None
        return lambda ctx: (
            sum(1 for p in ctx.game.players for card in p.graveyard if quality(ctx.game, card))
            >= bound
        )
    if _BARGAINED.match(text):
        return lambda ctx: bool(getattr(ctx.casting, "bargained", False))
    from ...models.game import condition_is_readable

    if not condition_is_readable(condition):
        return None
    return lambda ctx: bool(ctx.game.condition_holds(ctx.owner, condition, source=ctx.spell))
