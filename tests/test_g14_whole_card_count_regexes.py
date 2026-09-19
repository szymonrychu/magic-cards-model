"""G14-1: whole-card literal regexes generalized to read their counts through
`numbers.py` instead of a literal pinned to one printing.

Unit-test file, the same discipline `test_effects.py` and `test_mixed_effects.py`
use: it checks what the parser returns against real printed text only - no
hand-typed sentence anywhere (`CLAUDE.md`'s no-mocks rule: "no hand-written
card data" is not limited to a full `CardState`/scenario board, it covers any
text standing in for a card's own printed words). A full-text Scryfall search
for each of these five shapes turned up no second real printing with a
different count - see the search queries and single-hit results recorded in
`docs/engine-coverage.md`'s "G14: card-name rows and whole-card literal
parsers" section - so each parser here is proven only on the one real card
whose shape it reads; genericity (a future card with the same template and a
different count would read for free) is a property of the regex itself
(`numbers.COUNT` in place of a literal), not something these tests can
independently demonstrate without a second printing to point at.

Every CR number here was already verified this session with `mise run
rules:find` (CR 122.1a, CR 608.2c, CR 611.2, CR 614.1c, CR 701.23a, CR 702.62a,
CR 702.62b).
"""

from magic_cards_model.machines import AbilityKind, TriggerEvent, abilities_of_kind
from magic_cards_model.machines.effects import (
    activated_effect_for,
    effect_for,
    trigger_effect_for,
)
from tests.cards import card

# --------------------------------------------------------------------------
# Fight Rigging - hideaway counter then conditional free cast
# --------------------------------------------------------------------------


def _triggered_effect_text(name: str, event: TriggerEvent | None = None) -> str:
    triggers = abilities_of_kind(card(name), AbilityKind.TRIGGERED)
    if event is not None:
        (ability,) = [ability for ability in triggers if ability.event is event]
        return ability.effect
    (ability,) = triggers
    return ability.effect


def test_fight_rigging_combat_trigger_parses():
    text = _triggered_effect_text("Fight Rigging", TriggerEvent.BEGINNING_OF_STEP)
    assert trigger_effect_for("Fight Rigging", TriggerEvent.BEGINNING_OF_STEP, text) is not None


# --------------------------------------------------------------------------
# Neoform - search for mana value equal to N plus the sacrificed creature's
# --------------------------------------------------------------------------


def test_neoform_second_paragraph_parses():
    second_paragraph = card("Neoform").oracle_text.split("\n")[-1]
    assert effect_for("Neoform", second_paragraph) is not None


# --------------------------------------------------------------------------
# Cultivator Colossus - put a land from hand, draw a card, repeat
# --------------------------------------------------------------------------


def test_cultivator_colossus_enters_trigger_parses():
    text = _triggered_effect_text("Cultivator Colossus")
    assert (
        trigger_effect_for("Cultivator Colossus", TriggerEvent.ENTERS_THE_BATTLEFIELD, text)
        is not None
    )


# --------------------------------------------------------------------------
# Spelunking - draw a card, then maybe a land, with a Cave life bonus
# --------------------------------------------------------------------------


def test_spelunking_enters_trigger_parses():
    text = _triggered_effect_text("Spelunking")
    assert trigger_effect_for("Spelunking", TriggerEvent.ENTERS_THE_BATTLEFIELD, text) is not None


# --------------------------------------------------------------------------
# Greater Gargadon - remove a time counter from this card
# --------------------------------------------------------------------------


def test_greater_gargadons_own_sacrifice_ability_parses():
    (ability,) = abilities_of_kind(card("Greater Gargadon"), AbilityKind.ACTIVATED)
    assert activated_effect_for("Greater Gargadon", 0, ability.effect) is not None
