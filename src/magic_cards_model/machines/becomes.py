"""Resolution instructions that change what an object *is* - its abilities,
types, colours and base power/toughness - read whole, ahead of
`machines/effects.py`'s clause split, because each is one CR 608.2c
instruction the splitter would otherwise cut at its commas and "and"s.

Every CR number here was read whole with `mise run rules:find` in the session
that wrote this file.

- **CR 613.1** the layers: 4 type (613.1d), 5 colour (613.1e), 6 abilities
  and keyword counters (613.1f), 7b base power/toughness (613.4b).
- **CR 613.7b** a resolving effect is timestamped as it is created; **CR
  613.7c** a counter as it is put on.
- **CR 611.2a** a resolving effect lasts as long as stated, or until the end
  of the game when nothing is stated; **CR 611.2c** the set of objects it
  changes is fixed as it begins.
- **CR 122.1b** a keyword counter makes its object gain that keyword.
- **CR 105.3** a new colour replaces every previous colour; **CR 105.2c**
  colorless is no colour.
- **CR 205.3m** creature types; **CR 702.73a** changeling is every creature
  type.

Entry points: `becomes_ability_effect` / `becomes_spell_effect`, tried by
`machines/effects.py` near the top of its whole-text readers, and
`counter_list_on_anaphor`, tried by `_layer_remainder_or_composed` on the
sentence a layer composition leaves over.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..models.card_state import CardState
from ..models.zone import Zone
from ..numbers import parse_count
from .keyword_counters import KEYWORD_COUNTER_KEYWORDS

if TYPE_CHECKING:
    from ..models.game import Game, StackObject
    from .effects import AbilityEffect, Effect

StackEffect = Callable[["Game", "StackObject"], None]


# ---------------------------------------------------------------------------
# "Put a flying counter, a first strike counter, and a lifelink counter on
# that creature."
# ---------------------------------------------------------------------------

#: One "a/an/N <kind> counter(s)" item. A kind is "+1/+1", "-1/-1", or one or
#: two lowercase words - CR 122.1's counter kinds are an open set, and CR
#: 122.1b's keyword counters include two-word ones ("first strike", "double
#: strike"), which `_counter_kind` checks against the rule's own list.
_COUNTER_ITEM = (
    r"(?:a|an|one|two|three|four|five|\d+) (?:\+1/\+1|-1/-1|[a-z]+(?: [a-z]+)?) counters?"
)

#: Abigale, Eloquent First-Year's second sentence - several kinds of counter
#: put on the object the sentence before it acted on, in one instruction
#: (CR 608.2c). A single item is the ordinary rider `machines/effects.py`
#: already reads (`_RIDER_PUT_COUNTERS_RE`), so two or more are required here.
_PUT_COUNTER_LIST_ON_ANAPHOR_RE = re.compile(
    rf"^put (?P<items>{_COUNTER_ITEM}(?:(?:,? and|,) {_COUNTER_ITEM})+) on "
    r"(?:that creature|that permanent|it|them|those creatures)\.?$",
    re.IGNORECASE,
)
_COUNTER_ITEM_RE = re.compile(
    r"(?P<n>a|an|one|two|three|four|five|\d+) (?P<kind>\+1/\+1|-1/-1|[a-z]+(?: [a-z]+)?) "
    r"counters?",
    re.IGNORECASE,
)


def _counter_kind(raw: str) -> str | None:
    """A counter kind as `CardState.counters` keys it, or `None` when a
    two-word kind is not one of CR 122.1b's keyword counters (a two-word
    phrase that is not a keyword is not a counter kind this reads)."""
    kind = raw.strip().lower()
    if " " in kind and kind not in KEYWORD_COUNTER_KEYWORDS:
        return None
    return kind


def _counter_items(raw: str) -> list[tuple[str, int]] | None:
    items: list[tuple[str, int]] = []
    for match in _COUNTER_ITEM_RE.finditer(raw):
        amount = parse_count(match.group("n"))
        kind = _counter_kind(match.group("kind"))
        if amount is None or kind is None:
            return None
        items.append((kind, amount))
    return items or None


def counter_list_on_anaphor(text: str) -> StackEffect | None:
    """`_PUT_COUNTER_LIST_ON_ANAPHOR_RE`'s shape, as a clause run after the
    sentence it refers back to: "that creature" is the resolving spell's or
    ability's own target, rechecked for legality now (CR 608.2b) - an
    illegal or gone target gets nothing."""
    match = _PUT_COUNTER_LIST_ON_ANAPHOR_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    items = _counter_items(match.group("items"))
    if items is None:
        return None

    def effect(game: Game, stack_object: StackObject) -> None:
        for target in game.resolve_card_targets(stack_object):
            if target.zone is not Zone.BATTLEFIELD:
                continue
            for kind, amount in items:
                game.add_counters(target, kind, amount)

    return effect


# ---------------------------------------------------------------------------
# A layer sentence about a target chosen in the sentence before it, or gated
# on the source's own creature type.
# ---------------------------------------------------------------------------


def _apply_layer_text(
    game: Game, stack_object: StackObject, text: str, targets: list[CardState]
) -> None:
    """Create `text`'s continuous effect (CR 611.2) for `targets`, read by the
    same `machines/layers.py` shapes a printed layer sentence is, and
    timestamped now (CR 613.7b)."""
    from .effects import continuous_effects, layer_context_for
    from .triggers import AbilityOnStack

    source = stack_object.source(game) if isinstance(stack_object, AbilityOnStack) else stack_object
    if not isinstance(source, CardState) or not targets:
        return
    continuous_effects(game).create(
        source,
        targets=targets,
        context=layer_context_for(game, game.controller_of(stack_object)),
        ability_text=text,
        game=game,
    )


def _reads_as_layer_text(text: str) -> bool:
    from .layers import is_genuine_resolution_layer_sentence

    return is_genuine_resolution_layer_sentence(text)


#: Glamer Gifter's "choose up to one other target creature. Until end of
#: turn, that creature has base power and toughness 4/4 and gains all
#: creature types." - the target is announced in a sentence of its own (CR
#: 115.1: "choose" a target is how the targeting instruction is phrased
#: here) and the next sentence acts on "that creature". Read by writing the
#: target phrase back in place of the anaphor and handing the result to the
#: layer shapes, which then apply it to whatever `resolve_card_targets` left
#: legal (CR 608.2b).
_CHOOSE_TARGET_THEN_THAT_RE = re.compile(
    r"^choose (?P<target>(?:up to (?:one|two|three|\d+) )?(?:other |another )?target [^.]+?)\.\s+"
    r"(?P<rest>.*\bthat (?:creature|permanent)\b.*)$",
    re.IGNORECASE,
)


def _choose_target_then_that(text: str) -> StackEffect | None:
    match = _CHOOSE_TARGET_THEN_THAT_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    rewritten = re.sub(
        r"\bthat (?:creature|permanent)\b",
        match.group("target"),
        match.group("rest"),
        count=1,
        flags=re.IGNORECASE,
    )
    rewritten = rewritten[0].upper() + rewritten[1:]
    if not _reads_as_layer_text(rewritten):
        return None

    def effect(game: Game, stack_object: StackObject) -> None:
        _apply_layer_text(game, stack_object, rewritten, game.resolve_card_targets(stack_object))

    return effect


#: Figure of Fable's, Figure of Destiny's and Warden of the First Tree's
#: later steps: "If this creature is a Scout, it becomes a Kithkin Soldier
#: with base power and toughness 4/5." The creature type is checked as the
#: ability resolves, not as it is activated (the card's own ruling) - off
#: the computed board (CR 613.5), so a Scout the first step made counts - and
#: when it is not one, the ability does nothing. The instruction itself is
#: the ordinary self-referential layer sentence.
_IF_SELF_IS_A_TYPE_THEN_BECOMES_RE = re.compile(
    r"^if (?:this creature|this permanent) is an? (?P<quality>[A-Z][\w'-]*), "
    r"it (?P<rest>becomes .+)$",
    re.IGNORECASE,
)


def _if_self_is_a_type_then_becomes(text: str) -> StackEffect | None:
    match = _IF_SELF_IS_A_TYPE_THEN_BECOMES_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    rewritten = f"This creature {match.group('rest')}"
    if not rewritten.endswith("."):
        rewritten += "."
    if not _reads_as_layer_text(rewritten):
        return None
    quality = match.group("quality").lower()

    def effect(game: Game, stack_object: StackObject) -> None:
        from .triggers import AbilityOnStack

        if not isinstance(stack_object, AbilityOnStack):
            return
        source = stack_object.source(game)
        if (
            source is None
            or source.zone is not Zone.BATTLEFIELD
            or stack_object.source_stamp not in (None, source.zone_change_stamp)
        ):
            return
        subtypes = {kind.lower() for kind in game.characteristics_of(source).subtypes}
        if quality not in subtypes:
            return
        _apply_layer_text(game, stack_object, rewritten, [source])

    return effect


#: Puca's Eye's "draw a card, then choose a color. This artifact becomes the
#: chosen color." - two instructions in order (CR 608.2c): whatever comes
#: before ", then", read the ordinary way, then the colour choice and the
#: colour it sets (`machines/effects._parse_becomes_chosen_color_clause`).
_THEN_CHOOSE_A_COLOR_RE = re.compile(
    r"^(?P<first>[^.]+?),? then (?P<rest>choose a colou?r\. .+)$", re.IGNORECASE
)


def _then_choose_a_color(text: str) -> StackEffect | None:
    from .effects import _ability_effect_or_notice, _parse_becomes_chosen_color_clause

    match = _THEN_CHOOSE_A_COLOR_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    rest = _parse_becomes_chosen_color_clause(match.group("rest"))
    if rest is None:
        return None
    first = _ability_effect_or_notice(f"{match.group('first')}.")
    if first is None or getattr(first, "__name__", "").endswith("notice_only"):
        return None

    def effect(game: Game, stack_object: StackObject) -> None:
        from .triggers import AbilityOnStack

        if not isinstance(stack_object, AbilityOnStack):
            return
        first(game, stack_object)
        rest(game, stack_object)

    return effect


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def _mass_lose_all_abilities_whole(text: str) -> StackEffect | None:
    """`machines/effects._parse_mass_lose_all_abilities_clause` on the whole,
    unsplit text: Curious Colossus's "each creature target opponent controls
    loses all abilities, becomes a Coward in addition to its other types, and
    has base power and toughness 1/1." is one instruction whose commas the
    clause splitter would cut."""
    from .effects import _parse_mass_lose_all_abilities_clause

    return _parse_mass_lose_all_abilities_clause(" ".join(text.split()), for_spell=False)


def _mass_lose_all_abilities_whole_spell(text: str) -> StackEffect | None:
    from .effects import _parse_mass_lose_all_abilities_clause

    return _parse_mass_lose_all_abilities_clause(" ".join(text.split()), for_spell=True)


_ABILITY_READERS: tuple[Callable[[str], StackEffect | None], ...] = (
    _mass_lose_all_abilities_whole,
    _choose_target_then_that,
    _if_self_is_a_type_then_becomes,
    _then_choose_a_color,
)
_SPELL_READERS: tuple[Callable[[str], StackEffect | None], ...] = (
    _mass_lose_all_abilities_whole_spell,
    _choose_target_then_that,
)


def becomes_ability_effect(effect_text: str) -> AbilityEffect | None:
    """This module's whole-text reading of an activated or triggered
    ability's effect, or `None`."""
    for reader in _ABILITY_READERS:
        effect = reader(effect_text)
        if effect is not None:
            return effect
    return None


def becomes_spell_effect(effect_text: str) -> Effect | None:
    """This module's whole-text reading of a resolving spell, or `None`."""
    for reader in _SPELL_READERS:
        effect = reader(effect_text)
        if effect is not None:
            return effect
    return None


__all__ = [
    "becomes_ability_effect",
    "becomes_spell_effect",
    "counter_list_on_anaphor",
]
