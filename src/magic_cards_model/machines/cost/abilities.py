"""Ability cost modifiers: a permanent's static line that changes what other
abilities (or keyword actions) cost to activate (CR 601.2f via CR 602.2b).

    Equip abilities you activate cost {1} less to activate.
    Equip costs you pay cost {1} less.
    Boast abilities you activate cost {1} less to activate for each Dragon you
    control.
    Activated abilities of creatures you control cost {X} less to activate,
    where X is this creature's power. This effect can't reduce the mana in
    that cost to less than one mana.
    Activated abilities cost {2} more to activate unless they're mana abilities.
    The first activated ability of an artifact you activate each turn costs {2}
    less to activate.

One grammar reads the whole family: a subject (which activations - a keyword
action kind, a source quality, a zone, whose activation, an optional "that
target ..." clause, an optional "the first ... each turn" ordinal), an amount,
a direction and an optional tail (", where X is ...", "for each ...",
"unless they're mana abilities", the "can't reduce ... to less than one mana"
floor). `ability_cost_adjustment` applies every such line in play to one
activation's mana cost, increases before reductions (CR 601.2f), and is asked
afresh at every activation - nothing is locked in early.
"""

import re
from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING, Any

from ...models.card_state import ChoiceKind
from ...models.mana import ManaCost
from ...models.zone import Zone
from .components import increase
from .statics import CostContext, Quality, Reader, cost_count, cost_expression, object_quality
from .text import activated_ability_group_discount_effect

if TYPE_CHECKING:
    from ...models.card_state import CardState
    from ...models.game import Game

#: The keyword actions whose cost a line can name, by the word it prints.
_KIND_WORDS = {
    "equip": "equip",
    "boast": "boast",
    "exhaust": "exhaust",
    "ninjutsu": "ninjutsu",
    "dash": "dash",
    "unlock": "unlock",
    "foretelling": "foretell",
    "plotting": "plot",
}
#: Keyword actions that are special actions or alternative costs, not activated
#: abilities: "abilities you activate" does not name them (CR 116.2, CR 118.9).
_NOT_ABILITIES = frozenset({"dash", "unlock", "foretell", "plot"})
#: The keyword actions an activation can be priced as (the words `_KIND_WORDS` maps).
KEYWORD_KINDS = frozenset(_KIND_WORDS.values())
_LINE = re.compile(
    r"^(?P<subject>.+?) costs? (?P<amount>(?:\{[^{}]+\})+) (?P<direction>less|more)"
    r"(?: to (?:activate|pay))?(?P<tail>.*)$"
)
_FLOOR = re.compile(r"\s*this effect can't reduce the mana in that cost to less than one mana$")
_UNLESS_MANA = " unless they're mana abilities"
_EACH = re.compile(r"^ for each (?P<count>.+)$")
_WHERE = re.compile(r"^, where x is (?P<expr>.+)$")
_THAT_TARGET = re.compile(r"^(?P<head>.*?) ?that targets? (?P<what>.+)$")
_IF_IT_TARGETS = re.compile(r"^ if it targets (?P<what>.+)$")
_KIND_COSTS = re.compile(r"^(?P<kind>[a-z]+) costs you pay$")
_KIND_ABILITIES = re.compile(
    r"^(?P<kind>[a-z]+) abilities (?P<who>you activate|your opponents activate)"
    r"(?P<of> of other (?P<ofq>[a-z ]+))?$"
)
_KIND_OF_OTHER = re.compile(r"^(?P<kind>[a-z]+) abilities of other (?P<q>[a-z ]+?) you control$")
_ACTIVATED_OF = re.compile(
    r"^activated abilities of (?P<q>.+?) (?P<where>you control|in your graveyard)$"
)
_FIRST = re.compile(r"^the first activated ability of an? (?P<q>[a-z ]+?) you activate each turn$")
_NAMED_PLAYER_SPELLS = re.compile(r"^(?P<kind>foretelling|plotting) cards from your hand$")


@dataclass(frozen=True)
class AbilityContext:
    """One activation being priced: who activates, the ability's source, the
    kind of keyword action it is (`""` for an ordinary ability), whether it is
    a mana or loyalty ability, and the announced targets."""

    game: "Game"
    activator: str
    source: "CardState"
    kind: str = ""
    is_mana: bool = False
    is_loyalty: bool = False
    targets: tuple[Any, ...] = ()
    from_zone: Zone = Zone.BATTLEFIELD


@dataclass(frozen=True)
class AbilityModifier:
    """One parsed line. `sign` is -1 for "less", +1 for "more"."""

    scope: str  # "you", "opponents" or "anyone": who activates
    sign: int
    unit: ManaCost
    kind: str | None
    source_quality: Quality | None
    source_other: bool  # "of other <quality>": never the line's own permanent
    source_yours: bool  # "<quality> you control"
    source_zone: Zone | None
    only_loyalty: bool
    excluding_mana: bool
    target_what: str | None  # the "that target <what>" phrase, resolved at pricing
    target_quality: Quality | None
    target_yours: bool
    first_of_quality: Quality | None
    chosen_name: bool
    count: Reader | None
    expr: Reader | None
    floor_one: bool
    any_turn: bool = False
    self_only: bool = False

    def modification(self, ctx: AbilityContext, holder: "CardState") -> ManaCost | None:
        """What this line adds to (or takes off) `ctx`'s cost, or `None` when
        the activation is not one the line names."""
        game = ctx.game
        controller = holder.controller_or_owner
        if self.scope == "you" and ctx.activator != controller:
            return None
        if self.scope == "opponents" and ctx.activator == controller:
            return None
        if self.kind is not None and ctx.kind != self.kind:
            return None
        if self.kind is None and not self._ordinary_ability_matches(ctx):
            return None
        if self.only_loyalty and not ctx.is_loyalty:
            return None
        if self.source_zone is not None and ctx.from_zone is not self.source_zone:
            return None
        if self.self_only and ctx.source.id != holder.id:
            return None
        if self.source_other and ctx.source.id == holder.id:
            return None
        if self.chosen_name and not _has_chosen_name(holder, ctx.source):
            return None
        if self.source_quality is not None and not self.source_quality(game, ctx.source):
            return None
        if self.source_yours and ctx.source.controller_or_owner != controller:
            return None
        if self.only_loyalty and ctx.source.controller_or_owner == controller:
            return None  # "planeswalkers your opponents control"
        if self.target_what is not None and not self._targets_ok(ctx, holder):
            return None
        if self.first_of_quality is not None and not self._first_this_turn(ctx):
            return None
        scoped = CostContext(game=game, owner=controller, spell=None, source=holder)
        units = 1
        if self.count is not None:
            units = self.count(scoped)
        elif self.expr is not None:
            units = self.expr(scoped)
        if units <= 0:
            return None
        return ManaCost.parse(str(self.unit) * units)

    def _ordinary_ability_matches(self, ctx: AbilityContext) -> bool:
        """A line with no keyword kind names activated abilities only, never
        a keyword action's cost (a mana ability only when it says so)."""
        if ctx.kind in _NOT_ABILITIES:
            return False
        return not (ctx.is_mana and self.excluding_mana)

    def _targets_ok(self, ctx: AbilityContext, holder: "CardState") -> bool:
        what = self.target_what or ""
        game = ctx.game
        found = []
        for target in ctx.targets:
            card_id = getattr(target, "card_id", None)
            state = target if hasattr(target, "zone") else None
            if state is None:
                state = game.find_by_id(card_id if card_id is not None else target)
            if state is not None:
                found.append(state)
        if self.target_quality is None:
            return any(state.id == holder.id for state in found) and _is_self_phrase(what, holder)
        for state in found:
            if not self.target_quality(game, state):
                continue
            if self.target_yours and state.controller_or_owner != holder.controller_or_owner:
                continue
            return True
        return False

    def _first_this_turn(self, ctx: AbilityContext) -> bool:
        """ "The first activated ability of an artifact you activate each
        turn": no earlier activation of one this turn (the ability being
        priced has not been activated yet, CR 601.2f precedes CR 601.2h)."""
        game = ctx.game
        if self.first_of_quality is None or not self.first_of_quality(game, ctx.source):
            return False
        for entry in game.turn_history:
            if entry.kind != "activated" or entry.player != ctx.activator:
                continue
            chars = entry.characteristics
            if chars is not None and _chars_match(self.first_of_quality, game, chars):
                return False
        return True


class _Recorded:
    """A recorded activation's source as it was (`Characteristics`), shaped
    like the card state a `Quality` reads."""

    #: Not the battlefield: a `Quality` reads a battlefield object's computed
    #: board, and this record already holds the characteristics as they were.
    zone = Zone.GRAVEYARD

    def __init__(self, chars: Any) -> None:
        self.types = chars.types
        self.subtypes = chars.subtypes
        self.supertypes = chars.supertypes
        self.colors = chars.colors
        self.mana_value = chars.mana_value


def _chars_match(quality: Quality, game: "Game", chars: Any) -> bool:
    return bool(quality(game, _Recorded(chars)))


def _is_self_phrase(what: str, holder: "CardState") -> bool:
    """ "that target this creature" / "that target Cloud": the line's own
    permanent, spelled "this <type>" or by its short name (CR 201.5)."""
    text = what.strip().lower()
    if text.startswith("this "):
        return True
    name = holder.card.name.lower()
    short = name.split(",")[0].strip()
    return text in {name, short, short.split()[0]}


def _has_chosen_name(holder: "CardState", source: "CardState") -> bool:
    """ "Sources with the chosen name": the holder's "as this enters, choose a
    card name" answer (CR 614.12a) is the ability source's name."""
    choice = holder.choice
    return (
        choice is not None
        and choice.kind is ChoiceKind.CARD_NAME
        and choice.value.lower() == source.card.name.lower()
    )


@cache
def ability_cost_modifier(line: str) -> AbilityModifier | None:
    """One printed line as an ability cost modifier, or `None`."""
    text = re.sub(r"\s*\([^)]*\)", "", line).strip().lower().rstrip(".")
    floor_one = False
    if (floor := re.search(r"\.\s*" + _FLOOR.pattern.removeprefix(r"\s*"), text)) is not None:
        floor_one = True
        text = text[: floor.start()]
    text = re.sub(r"\s+\.", ".", text).strip().rstrip(".")
    if " less" not in text and " more" not in text:
        return None
    if "to cast" in text:
        return None
    excluding_mana = text.endswith(_UNLESS_MANA)
    if excluding_mana:
        text = text[: -len(_UNLESS_MANA)]
    match = _LINE.match(text)
    if match is None:
        return None
    subject = match.group("subject").strip()
    kind: str | None = None
    scope = "you"
    quality: Quality | None = None
    other = yours = only_loyalty = chosen_name = False
    zone: Zone | None = None
    first: Quality | None = None
    target_what: str | None = None
    target_quality: Quality | None = None
    target_yours = False
    that = _THAT_TARGET.match(subject)
    if that is not None:
        subject, target_what = that.group("head").strip(), that.group("what").strip()
        target_match = re.match(r"^(?:a|an) (?P<q>.+?)(?P<yours> you control)?$", target_what)
        if target_match is not None:
            target_quality = object_quality(target_match.group("q"))
            if target_quality is None:
                return None
            target_yours = target_match.group("yours") is not None
    self_only = False
    tail_override: str | None = None
    if subject == "this equipment's equip ability":
        kind, self_only = "equip", True
        if (cond := _IF_IT_TARGETS.match(match.group("tail"))) is not None:
            target_what = cond.group("what").strip()
            target_match = re.match(r"^(?:a|an) (?P<q>.+)$", target_what)
            target_quality = object_quality(target_match.group("q")) if target_match else None
            if target_quality is None:
                return None
            tail_override = ""
    elif ((m := _KIND_COSTS.match(subject)) is not None and m.group("kind") in _KIND_WORDS) or (
        m := _NAMED_PLAYER_SPELLS.match(subject)
    ) is not None:
        kind = _KIND_WORDS[m.group("kind")]
    elif (m := _KIND_OF_OTHER.match(subject)) is not None and m.group("kind") in _KIND_WORDS:
        kind, other, yours = _KIND_WORDS[m.group("kind")], True, True
        zone = Zone.BATTLEFIELD
        if m.group("q") != "permanents":
            quality = object_quality(m.group("q"))
            if quality is None:
                return None
    elif (m := _KIND_ABILITIES.match(subject)) is not None and m.group("kind") in _KIND_WORDS:
        kind = _KIND_WORDS[m.group("kind")]
        scope = "you" if m.group("who") == "you activate" else "opponents"
        if m.group("of") is not None:
            other = True
            quality = object_quality(m.group("ofq"))
            if quality is None:
                return None
    elif subject == "abilities you activate that aren't mana abilities":
        excluding_mana = True
    elif subject == "abilities your opponents activate":
        scope = "opponents"
    elif subject == "activated abilities":
        scope = "anyone"
    elif subject == "activated abilities of sources with the chosen name":
        scope, chosen_name = "anyone", True
    elif (m := _ACTIVATED_OF.match(subject)) is not None:
        phrase = m.group("q")
        if m.group("where") == "in your graveyard":
            zone = Zone.GRAVEYARD
            phrase = re.sub(r" cards$", "", phrase)
        else:
            yours, zone = True, Zone.BATTLEFIELD
        quality = object_quality(phrase)
        if quality is None:
            return None
    elif subject == "loyalty abilities of planeswalkers your opponents control":
        scope, only_loyalty = "anyone", True
    elif (m := _FIRST.match(subject)) is not None:
        first = object_quality(m.group("q"))
        if first is None:
            return None
        excluding_mana = True
    else:
        return None
    tail = match.group("tail") if tail_override is None else tail_override
    count = expr = None
    any_turn = False
    if tail:
        if (each := _EACH.match(tail)) is not None:
            count = cost_count(each.group("count"))
            if count is None:
                return None
        elif (where := _WHERE.match(tail)) is not None:
            expr = cost_expression(where.group("expr"))
            if expr is None:
                return None
        elif tail.strip() == "":
            pass
        elif tail.strip() == "and can be done on any player's turn" and kind == "foretell":
            any_turn = True
        else:
            return None
    amount = match.group("amount")
    if amount.lower() == "{x}":
        unit = ManaCost.parse("{1}")
        if expr is None:
            return None
    else:
        unit = ManaCost.try_parse(amount)
        if unit is None:
            return None
    return AbilityModifier(
        scope=scope,
        sign=-1 if match.group("direction") == "less" else 1,
        unit=unit,
        kind=kind,
        source_quality=quality,
        source_other=other,
        source_yours=yours,
        source_zone=zone,
        only_loyalty=only_loyalty,
        excluding_mana=excluding_mana,
        target_what=target_what,
        target_quality=target_quality,
        target_yours=target_yours,
        first_of_quality=first,
        self_only=self_only,
        chosen_name=chosen_name,
        count=count,
        expr=expr,
        floor_one=floor_one,
        any_turn=any_turn,
    )


def ability_cost_adjustment(
    game: "Game",
    activator: str,
    source: "CardState",
    mana: ManaCost,
    *,
    kind: str = "",
    is_mana: bool = False,
    is_loyalty: bool = False,
    targets: tuple[Any, ...] = (),
    from_zone: Zone = Zone.BATTLEFIELD,
) -> ManaCost:
    """`mana` with every ability cost modifier in play applied (CR 601.2f:
    increases first, then reductions; a reduction never goes below the
    coloured component, CR 118.7a)."""
    ctx = AbilityContext(
        game=game,
        activator=activator,
        source=source,
        kind=kind,
        is_mana=is_mana,
        is_loyalty=is_loyalty,
        targets=targets,
        from_zone=from_zone,
    )
    increases: list[ManaCost] = []
    decreases: list[ManaCost] = []
    floor_one = False
    board = game.computed_board()
    for holder in game.battlefield:
        for line in board.of(holder).abilities:
            lowered = line.lower()
            if (
                " to activate" not in lowered
                and " costs you pay" not in lowered
                and "cards from your hand" not in lowered
            ):
                continue
            if activated_ability_group_discount_effect(line.strip()) is not None:
                continue  # `Game._activated_ability_group_discount` prices this one
            modifier = ability_cost_modifier(_self_normalized(holder, line))
            if modifier is None:
                continue
            priced = modifier.modification(ctx, holder)
            if priced is None:
                continue
            if modifier.sign < 0:
                decreases.append(priced)
                floor_one = floor_one or modifier.floor_one
            else:
                increases.append(priced)
    result = mana
    for extra in increases:
        result = increase(result, extra)
    before = result
    for cut in decreases:
        result = result.minus(cut)
    if floor_one and before.converted > 0 and result.converted < 1:
        result = before.minus(ManaCost.parse(f"{{{max(before.converted - 1, 0)}}}"))
    return result


def _self_normalized(holder: "CardState", line: str) -> str:
    """The line with the holder's own name read as "this <permanent>" (CR 201.5)."""
    from ..abilities import self_normalized_effect_text

    return self_normalized_effect_text(holder.card.name, line.strip(), legendary=True)


def foretell_any_turn(game: "Game", player: str) -> bool:
    """Whether a static ability `player` controls lets them foretell on any
    player's turn ("... and can be done on any player's turn")."""
    board = game.computed_board()
    for holder in game.battlefield:
        if holder.controller_or_owner != player:
            continue
        for line in board.of(holder).abilities:
            if "any player's turn" not in line.lower():
                continue
            modifier = ability_cost_modifier(_self_normalized(holder, line))
            if modifier is not None and modifier.any_turn:
                return True
    return False


#: New Perspectives: "As long as you have seven or more cards in hand, you may
#: pay {0} rather than pay cycling costs." (CR 118.9, CR 702.29a). Cycling
#: and typecycling alike; the player may always decline, but a cost of nothing
#: is never worse than the printed one, so the activation is simply priced so.
_CYCLING_FREE = re.compile(
    r"^as long as (?P<condition>.+?), you may pay \{0\} rather than pay cycling costs\.?$",
    re.IGNORECASE,
)


def reads_free_cycling_line(line: str) -> bool:
    """Whether `line` is New Perspectives' sentence with a condition the
    engine reads."""
    from ...models.game import condition_is_readable

    match = _CYCLING_FREE.match(line.strip())
    return match is not None and condition_is_readable(match.group("condition"))


def cycling_costs_nothing(game: "Game", player: str) -> bool:
    """Whether a permanent `player` controls lets them pay {0} rather than
    pay cycling costs right now."""
    board = game.computed_board()
    for holder in game.permanents_controlled_by(player):
        for line in board.of(holder).abilities:
            match = _CYCLING_FREE.match(line.strip())
            if match is not None and game.condition_holds(
                player, match.group("condition"), source=holder
            ):
                return True
    return False
