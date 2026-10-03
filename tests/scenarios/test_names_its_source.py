"""Scenario: `effects._names_its_source` - whether a trigger's own condition
names its source by CR 700.7's "this [something]" self-reference, so a later
bare "it" (CR 608.2c) is that source.

"this turn" / "this way" / "this combat" are not self-references: the word
after "this" must be a card type, a printed subtype or the engine's other
self-reference words (the same vocabulary `triggers` already reads).

Rule checked with `mise run rules:find 700.7`: "this [something]" refers to
that particular object.
"""

import pytest

from magic_cards_model.machines.abilities import TriggeredAbility, TriggerWord
from magic_cards_model.machines.effects import _names_its_source
from magic_cards_model.machines.triggers import AbilityOnStack


def _ability(condition: str, intervening_if: str | None = None) -> AbilityOnStack:
    printed = TriggeredAbility(
        raw=condition,
        text=condition,
        face="X",
        word=TriggerWord.WHENEVER,
        condition=condition,
        intervening_if=intervening_if,
        effect="put a +1/+1 counter on it",
    )
    return AbilityOnStack(kind=printed.kind, ability=printed, source_name="X", controller="A")


@pytest.mark.parametrize(
    "condition",
    ["this creature attacks", "this Vehicle attacked or blocked", "this Time Lord dies", "this permanent enters"],
)
def test_a_type_or_subtype_self_reference_names_the_source(condition):
    assert _names_its_source(_ability(condition))


@pytest.mark.parametrize(
    "condition",
    ["a creature dies this turn", "you gain life this way", "a spell was cast this combat"],
)
def test_this_turn_and_this_way_do_not_name_the_source(condition):
    assert not _names_its_source(_ability(condition))


def test_the_intervening_if_counts_too():
    assert _names_its_source(_ability("a creature dies", "this creature dealt damage"))
    assert not _names_its_source(_ability("a creature dies", "you did so this turn"))
