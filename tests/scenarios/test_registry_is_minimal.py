"""Guard: nothing in `EFFECTS` / `TRIGGER_EFFECTS` / `ACTIVATED_EFFECTS` should
be reachable through the parser fallback chain `effect_for` / `trigger_effect_for`
/ `activated_effect_for` would use on a registry miss.

`machines/effects.py` keeps a card here only when no existing parser reads its
shape. A row for a shape a parser already covers is dead weight at best - see
W0, which deleted four such rows (Preordain, Solemn Simulacrum's two triggers,
Devourer of Destiny) once this test proved each was reachable without its row -
and a silent trap at worst: an explicit row always wins over the parser
(`effect_for` and friends check the table first), so a re-added row would
*shadow* the parser rather than merely duplicate it, and nobody would notice
until the row drifted out of sync with the card's real printed text.

For every row this test re-derives the exact text the dispatcher would have
handed the parser - `Card.oracle_text` for a spell, the matching
`TriggeredAbility.effect` / `ActivatedAbility.effect` for an ability - runs the
same fallback chain the dispatcher runs on a miss, and asserts it comes back
`None`. A row that fails this test is telling you which parser already
understands it; delete the row.

T10's round-trip/replay invariant does not apply here: this file never builds
a `Game`, only reads a static registry against parser output, so `tests/
scenarios/conftest.py`'s hook has nothing to checkpoint.
"""

import pytest

from magic_cards_model.machines.abilities import (
    ActivatedAbility,
    TriggeredAbility,
    TriggerEvent,
    parse_abilities,
)
from magic_cards_model.machines.effects import (
    ACTIVATED_EFFECTS,
    EFFECTS,
    TRIGGER_EFFECTS,
    _is_layer_effect_text,
    create_continuous_effect_of_ability,
    parse_mixed_effect,
    parse_mixed_effect_for_spell,
)
from tests.cards import card


def _spell_fallback(text: str) -> object | None:
    """What `effect_for` tries on a registry miss (`machines/effects.py`).

    `parse_mixed_effect_for_spell` (W1) is a per-clause dispatcher that tries
    the targeted parser and then the player parser on each clause, so it
    subsumes the old "whole effect is targeted, or whole effect is player"
    two-call fallback this test used before.
    """
    return parse_mixed_effect_for_spell(text)


def _ability_fallback(text: str) -> object | None:
    """What `trigger_effect_for`/`activated_effect_for` try on a registry miss.

    `parse_mixed_effect` (W3) is the ability-side per-clause dispatcher that
    tries a targeted clause, then a search clause, then a player clause on
    each clause of the text, so it subsumes the old three-call fallback
    (`parse_search_and_put_effect` or `parse_targeted_effect` or
    `parse_player_effect`) this test used before. `_is_layer_effect_text`
    (added when ability-side routing to `create_continuous_effect_of_ability`
    became text-driven) is the second half of `_ability_effect_or_notice`'s
    fallback: a continuous-effect shape `parse_mixed_effect`'s clause splitter
    cannot read whole - Basking Rootwalla's and Karn, the Great Creator's own
    rows were retired exactly because this reaches them without one.
    """
    parsed = parse_mixed_effect(text)
    if parsed is not None:
        return parsed
    return create_continuous_effect_of_ability if _is_layer_effect_text(text) else None


def _triggered_effect_text(card_name: str, event: TriggerEvent, marker: str) -> str:
    """The `TriggeredAbility.effect` text a `TRIGGER_EFFECTS` key would resolve to.

    Mirrors `trigger_effect_for`'s own matching: every `TriggeredAbility` on
    `event`, picked by `marker` the way `_dispatch_by_printed_text` picks it
    when a card has more than one - an empty marker only works when there is
    exactly one candidate, the same assumption `trigger_effect_for` makes when
    it hands back that entry directly instead of a dispatcher.
    """
    candidates = [
        ability
        for ability in parse_abilities(card(card_name))
        if isinstance(ability, TriggeredAbility) and ability.event is event
    ]
    if not marker:
        assert len(candidates) == 1, (
            f"{card_name!r} has {len(candidates)} triggered abilities on {event!r}, "
            "so an empty marker cannot pick one - this key needs a real marker."
        )
        return candidates[0].effect
    matching = [a for a in candidates if marker in a.text.lower()]
    assert matching, (
        f"no triggered ability on {card_name!r} for event {event!r} has "
        f"{marker!r} in its printed text - candidates were {[a.text for a in candidates]}"
    )
    return matching[0].effect


def _activated_effect_text(card_name: str, index: int) -> str:
    """The `ActivatedAbility.effect` text an `ACTIVATED_EFFECTS` key resolves to."""
    activated = [a for a in parse_abilities(card(card_name)) if isinstance(a, ActivatedAbility)]
    assert index < len(activated), (
        f"{card_name!r} only has {len(activated)} activated abilities, there is no index {index}"
    )
    return activated[index].effect


@pytest.mark.parametrize("card_name", sorted(EFFECTS))
def test_effects_row_is_not_reachable_through_the_spell_parsers(card_name: str) -> None:
    """A row in `EFFECTS` must not be a shape `parse_targeted_effect_for_spell`
    or `parse_player_effect_for_spell` already reads off the card's own oracle
    text - `effect_for` would reach the parser for free, and the explicit row
    only serves to shadow it.
    """
    text = card(card_name).oracle_text or ""
    result = _spell_fallback(text)
    assert result is None, (
        f"EFFECTS[{card_name!r}] is dead weight: the spell parser fallback "
        f"already reads {card_name!r}'s oracle text into a working effect "
        f"({text!r}). Delete the row - see W0 in this file's docstring."
    )


@pytest.mark.parametrize("key", sorted(TRIGGER_EFFECTS, key=lambda key: (key[0], key[1], key[2])))
def test_trigger_effects_row_is_not_reachable_through_the_ability_parsers(
    key: tuple[str, TriggerEvent, str],
) -> None:
    """A row in `TRIGGER_EFFECTS` must not be a shape `parse_search_and_put_effect`,
    `parse_targeted_effect`, or `parse_player_effect` already reads off the
    triggered ability's own printed text.
    """
    card_name, event, marker = key
    text = _triggered_effect_text(card_name, event, marker)
    result = _ability_fallback(text)
    assert result is None, (
        f"TRIGGER_EFFECTS[{key!r}] is dead weight: the ability parser fallback "
        f"already reads its printed effect into a working effect ({text!r}). "
        f"Delete the row - see W0 in this file's docstring."
    )


@pytest.mark.parametrize("key", sorted(ACTIVATED_EFFECTS))
def test_activated_effects_row_is_not_reachable_through_the_ability_parsers(
    key: tuple[str, int],
) -> None:
    """A row in `ACTIVATED_EFFECTS` must not be a shape `parse_search_and_put_effect`,
    `parse_targeted_effect`, or `parse_player_effect` already reads off the
    activated ability's own printed text.
    """
    card_name, index = key
    text = _activated_effect_text(card_name, index)
    result = _ability_fallback(text)
    assert result is None, (
        f"ACTIVATED_EFFECTS[{key!r}] is dead weight: the ability parser fallback "
        f"already reads its printed effect into a working effect ({text!r}). "
        f"Delete the row - see W0 in this file's docstring."
    )
