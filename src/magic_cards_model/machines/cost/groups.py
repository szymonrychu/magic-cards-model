"""Group spell cost modifiers: a permanent's static line that changes what
other spells cost (CR 601.2f, CR 604.2).

    Creature spells with flying you cast cost {1} less to cast.
    The second spell you cast each turn costs {1} less to cast.
    Each instant and sorcery spell you cast costs {1} less to cast for each
    creature it targets.
    Spells your opponents cast that target a Merfolk you control cost {2} more.

One grammar reads the whole family: a subject (an optional ordinal, a quality
of spell, whose spells it is, an optional "that target ..." / "from ..."
clause), an amount in mana symbols, a direction and an optional tail ("for
each <count>", ", where X is <expression>", "if <condition>"). The quality,
the counts, the expressions and the conditions are `machines/cost/statics.py`'s
shared readers. `static_cost_modifiers_for` asks `group_spell_modifier` after
`cost_modifier_effect` (whose older, narrower shapes keep their meaning) and
applies the result while the total cost is determined, so it is read afresh at
every cast and never locked in early (CR 601.2f).
"""

import re
from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING, Any

from ...models.card_state import ChoiceKind, TargetKind
from ...models.mana import ColoredOnlyReduction, ManaCost
from ...models.zone import Zone
from .statics import (
    CostContext,
    Quality,
    Reader,
    cost_condition,
    cost_count,
    cost_expression,
    object_quality,
)

if TYPE_CHECKING:
    from ...models.card_state import CardState
    from ...models.game import Game

_LINE = re.compile(
    r"^(?P<subject>.+?) costs? (?P<amount>(?:\{[^{}]+\})+) (?P<direction>less|more) to cast"
    r"(?P<tail>.*)$"
)
_ORDINAL = re.compile(r"^the (?P<ordinal>first|second) (?P<rest>.+?) each turn$")
_SPELL_WORD = re.compile(r"^(?:(?P<head>.*?) )?spells?(?: (?P<after>.*))?$")
_EACH = re.compile(r"^ for each (?P<count>.+)$")
_WHERE = re.compile(r"^, where x is (?P<expr>.+)$")
_IF = re.compile(r"^ if (?P<cond>.+)$")
_UNCOUNTERABLE = " and can't be countered"
_ZONES = {
    "your graveyard": Zone.GRAVEYARD,
    "exile": Zone.EXILE,
    "your hand": Zone.HAND,
    "your library": Zone.LIBRARY,
}
_TARGET_CLAUSE = re.compile(r"(?:^| )that targets? (?P<what>.+)$")
_FROM_CLAUSE = re.compile(r" ?from (?P<zones>.+?)$")
_SHARES_TYPE = " that share a card type with the exiled card"
#: "...of the chosen type" / "...with the chosen name": the quality is the
#: choice the source recorded as it entered (CR 614.12a), read at pricing time.
_CHOSEN = re.compile(r"^(?:of the chosen (?P<type>type)|with the chosen (?P<name>name))$")
#: Bard Class's and Morophon's rider: the reduction takes only coloured mana off
#: the cost and never spills into generic (CR 118.7a, `ColoredOnlyReduction`).
_COLORED_ONLY = " this effect reduces only the amount of colored mana you pay"


@dataclass(frozen=True)
class GroupModifier:
    """One parsed group line. `sign` is -1 for "less", +1 for "more"."""

    scope: str  # "you", "opponents", "enchanted" (the player a Curse enchants) or "anyone"
    sign: int
    unit: ManaCost
    quality: Quality | None
    ordinal: int | None
    kicked: bool
    target: Any  # (CostContext, game-object) -> bool, or None
    zones: tuple[Zone, ...]
    shares_type_with_imprint: bool
    count: Reader | None
    expr: Reader | None
    condition: Any  # (CostContext) -> bool, or None
    cant_be_countered: bool
    chosen: str | None = None  # "type" or "name": the source's recorded choice
    colored_only: bool = False

    def modification(self, ctx: CostContext, caster: str, cast_from: Zone) -> ManaCost | None:
        """The cost this line takes off (or adds to) `ctx.spell`, or `None`
        when the spell is not one it names."""
        game, spell, source = ctx.game, ctx.spell, ctx.source
        if spell is None or source is None:
            return None
        controller = source.controller_or_owner
        if self.scope == "you" and caster != controller:
            return None
        if self.scope == "opponents" and caster == controller:
            return None
        if self.scope == "enchanted":
            attached = source.attachment
            if (
                attached is None
                or attached.kind is not TargetKind.PLAYER
                or attached.username != caster
            ):
                return None
        if self.quality is not None and not self.quality(game, spell):
            return None
        if self.kicked and not _is_kicked(game, spell, ctx.casting):
            return None
        if self.zones and cast_from not in self.zones:
            return None
        if self.shares_type_with_imprint and not _shares_type_with_imprint(game, spell, source):
            return None
        if self.chosen is not None and not _matches_choice(game, self.chosen, spell, source):
            return None
        if self.target is not None and not self.target(ctx):
            return None
        if self.ordinal is not None and not self._ordinal_holds(ctx, caster):
            return None
        scoped = CostContext(
            game=game,
            owner=controller,
            spell=spell,
            source=source,
            targets=ctx.targets,
            casting=ctx.casting,
        )
        if self.condition is not None and not self.condition(scoped):
            return None
        units = 1
        if self.count is not None:
            units = self.count(scoped)
        elif self.expr is not None:
            units = self.expr(scoped)
        if units <= 0:
            return None
        priced = ManaCost.parse(str(self.unit) * units)
        if self.colored_only:
            return ColoredOnlyReduction(symbols=priced.symbols)
        return priced

    def _ordinal_holds(self, ctx: CostContext, caster: str) -> bool:
        """ "The first/second <quality> spell you cast each turn": the spell
        being cast is not in `spells_cast_this_turn` yet (CR 601.2f comes
        before CR 601.2i), so exactly `ordinal - 1` earlier qualifying spells
        must be there."""
        game = ctx.game
        earlier = [
            prior
            for prior in game.spells_cast_this_turn.get(caster, [])
            if (self.quality is None or self.quality(game, prior))
            and (not self.kicked or _is_kicked(game, prior, None))
        ]
        return len(earlier) == (self.ordinal or 1) - 1


def _matches_choice(
    game: "Game", chosen: str, spell: "CardState", source: "CardState"
) -> bool:
    """Whether `spell` is what `source` chose as it entered (CR 614.12a): a card
    type or creature type for "of the chosen type" (a changeling has every
    creature type, CR 702.73a), a card name for "with the chosen name". A
    source that never chose matches nothing."""
    choice = source.choice
    if choice is None:
        return False
    value = choice.value.lower()
    if chosen == "name":
        return choice.kind is ChoiceKind.CARD_NAME and value in {
            spell.name.lower(),
            spell.card.name.lower(),
        }
    if choice.kind is ChoiceKind.CARD_TYPE:
        return value in {t.value.lower() for t in spell.types_as_a_spell(spell.card.types)}
    if choice.kind is ChoiceKind.CREATURE_TYPE:
        from ..combat import has_keyword

        return has_keyword(spell, "changeling", game) or value in {
            subtype.lower() for subtype in spell.subtypes
        }
    return False


def _is_kicked(game: "Game", spell: "CardState", casting: Any) -> bool:
    if casting is not None and casting.spell.id == spell.id:
        return bool(getattr(casting, "kicked", 0))
    record = game.cast_records.get(spell.zone_change_stamp)
    return record is not None and bool(record.kicked)


def _shares_type_with_imprint(game: "Game", spell: "CardState", source: "CardState") -> bool:
    imprinted = game.card_imprinted_on(source.id)
    return imprinted is not None and bool(set(imprinted.types) & set(spell.types))


def _target_clause(what: str) -> Any:
    """ "that target <what>" as a predicate over the announced targets
    (CR 601.2c): this permanent, or any object of a printed quality
    (optionally "you control"), or the player this Curse is attached to
    (CR 303.4m: "enchanted player" is whoever the permanent is attached to)."""
    text = what.strip()
    if text == "enchanted player":

        def targets_enchanted_player(ctx: CostContext) -> bool:
            attached = ctx.source.attachment
            return (
                attached is not None
                and attached.kind is TargetKind.PLAYER
                and any(
                    getattr(t, "kind", None) is TargetKind.PLAYER
                    and t.username == attached.username
                    for t in ctx.targets
                )
            )

        return targets_enchanted_player
    if text in {"this creature", "this permanent", "this artifact", "this enchantment"}:
        return lambda ctx: any(getattr(t, "card_id", None) == ctx.source.id for t in ctx.targets)
    match = re.match(r"^(?:a|an) (?P<quality>.+?)(?P<yours> you control)?$", text)
    if match is None:
        return None
    quality = object_quality(match.group("quality"))
    if quality is None:
        return None
    yours = match.group("yours") is not None

    def targets_quality(ctx: CostContext) -> bool:
        for target in ctx.targets:
            card_id = getattr(target, "card_id", None)
            state = ctx.game.find_by_id(card_id) if card_id is not None else None
            if state is None or not quality(ctx.game, state):
                continue
            if yours and state.controller_or_owner != ctx.source.controller_or_owner:
                continue
            return True
        return False

    return targets_quality


@cache
def group_spell_modifier(line: str) -> GroupModifier | None:
    """One printed line as a group modifier, or `None` when it is not one."""
    text = re.sub(r"\s*\([^)]*\)", "", line).strip().rstrip(".").lower()
    if "less to cast" not in text and "more to cast" not in text:
        return None
    if text.startswith("this spell") or text.startswith("activated abilit"):
        return None
    colored_only = text.endswith(_COLORED_ONLY)
    if colored_only:
        text = text[: -len(_COLORED_ONLY)].rstrip(". ")
    cant_be_countered = text.endswith(_UNCOUNTERABLE)
    if cant_be_countered:
        text = text[: -len(_UNCOUNTERABLE)]
    match = _LINE.match(text)
    if match is None:
        return None
    subject = match.group("subject")
    ordinal_match = _ORDINAL.match(subject)
    ordinal = None
    if ordinal_match is not None:
        ordinal = 1 if ordinal_match.group("ordinal") == "first" else 2
        subject = ordinal_match.group("rest")
    subject = re.sub(r"^each ", "", subject)
    kicked = False
    if re.match(r"^kicked spell\b", subject):
        kicked, subject = True, subject.replace("kicked ", "", 1)
    spell_word = _SPELL_WORD.match(subject)
    if spell_word is None:
        return None
    head = spell_word.group("head") or ""
    after = spell_word.group("after") or ""
    scope = "anyone"
    for phrase, owner in (
        ("your opponents cast", "opponents"),
        ("you cast", "you"),
        # CR 303.4m: a Curse's "spells ... enchanted player casts".
        ("enchanted player casts", "enchanted"),
    ):
        if phrase in after:
            scope = owner
            after = after.replace(phrase, "", 1).strip()
            break
    chosen = None
    if (chosen_match := _CHOSEN.match(after)) is not None:
        chosen = "type" if chosen_match.group("type") else "name"
        after = ""
    shares = False
    if after.startswith("that share a card type with the exiled card"):
        shares, after = True, ""
    target = None
    target_match = _TARGET_CLAUSE.search(after)
    if target_match is not None:
        target = _target_clause(target_match.group("what"))
        if target is None:
            return None
        after = after[: target_match.start()].strip()
    zones: tuple[Zone, ...] = ()
    from_match = _FROM_CLAUSE.search(after)
    if from_match is not None:
        names = [n.strip().removeprefix("from ") for n in from_match.group("zones").split(" or ")]
        if any(n not in _ZONES for n in names):
            return None
        zones = tuple(_ZONES[n] for n in names)
        after = after[: from_match.start()].strip()
    quality_text = " ".join(part for part in (head, after) if part)
    quality = object_quality(quality_text) if quality_text else None
    if quality_text and quality is None:
        return None
    tail = match.group("tail")
    count = expr = condition = None
    if tail:
        if (each := _EACH.match(tail)) is not None:
            count = cost_count(each.group("count"))
            if count is None:
                return None
        elif (where := _WHERE.match(tail)) is not None:
            expr = cost_expression(where.group("expr"))
            if expr is None:
                return None
        elif (conditional := _IF.match(tail)) is not None:
            condition = _spell_condition(conditional.group("cond"))
            if condition is None:
                return None
        else:
            return None
    amount = match.group("amount")
    if amount.lower() == "{x}":
        unit = ManaCost.parse("{1}")
        if expr is None:
            return None
    else:
        unit = ManaCost.try_parse(amount.upper())
        if unit is None:
            return None
    return GroupModifier(
        scope=scope,
        sign=-1 if match.group("direction") == "less" else 1,
        unit=unit,
        quality=quality,
        ordinal=ordinal,
        kicked=kicked,
        target=target,
        zones=zones,
        shares_type_with_imprint=shares,
        count=count,
        expr=expr,
        condition=condition,
        cant_be_countered=cant_be_countered,
        chosen=chosen,
        colored_only=colored_only,
    )


def _spell_condition(condition: str) -> Any:
    """ "if it has mutate": a fact about the spell being cast, read from its
    printed keywords; anything else goes to the shared condition reader."""
    mutate = re.match(r"^it has (?P<keyword>[a-z]+)$", condition.strip())
    if mutate is not None:
        keyword = mutate.group("keyword")
        return lambda ctx: keyword in {k.lower() for k in ctx.spell.card.keywords or ()}
    return cost_condition(condition)
