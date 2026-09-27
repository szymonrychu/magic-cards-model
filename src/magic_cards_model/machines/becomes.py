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
)
_SPELL_READERS: tuple[Callable[[str], StackEffect | None], ...] = (
    _mass_lose_all_abilities_whole_spell,
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
