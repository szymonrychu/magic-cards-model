"""G14-2: card-name registry rows with hardcoded counts, replaced by whole-
text parsers that read every count through `numbers.py`.

Unit-test file, the same discipline `test_effects.py` and
`test_g14_whole_card_count_regexes.py` use: real printed text only, no
hand-typed sentence anywhere (`CLAUDE.md`'s no-mocks rule covers any text
standing in for a card's own printed words, not only a full `CardState`). A
full-text Scryfall search for each of these four shapes turned up no second
real printing with a different count - see `docs/engine-coverage.md`'s "G14:
card-name rows and whole-card literal parsers" section for the search queries
and single-hit results - so each parser here is proven only on the one real
card whose shape it reads.

Full behavioural regression for the real cards (Seasoned Pyromancer's
discard/draw/token decision, Twisted Image's switch-then-draw, Unholy Heat's
delirium branch) is already carried by
`tests/scenarios/test_cost_reduction_shapes.py`,
`tests/scenarios/test_decisions_during_resolution.py`,
`tests/scenarios/test_continuous_effects_with_a_duration.py`,
`tests/scenarios/test_layer_effects_round_trip.py`, and
`tests/scenarios/test_delirium.py`; Thopter Assembly's own return-then-create
resolution had no scenario test before this wave, so
`tests/scenarios/test_thopter_assembly.py` is new.

Every CR number here was already verified this session with `mise run
rules:find` (CR 608.2c, CR 701.9b, CR 401, CR 111.9, CR 613.4d, CR 207.2c).
"""

from magic_cards_model.machines import AbilityKind, TriggerEvent, abilities_of_kind
from magic_cards_model.machines.effects import effect_for, trigger_effect_for
from tests.cards import card

# --------------------------------------------------------------------------
# Seasoned Pyromancer - discard N, draw N, a token per nonland discarded
# --------------------------------------------------------------------------


def test_seasoned_pyromancer_enters_trigger_parses():
    (ability,) = abilities_of_kind(card("Seasoned Pyromancer"), AbilityKind.TRIGGERED)
    assert (
        trigger_effect_for(
            "Seasoned Pyromancer", TriggerEvent.ENTERS_THE_BATTLEFIELD, ability.effect
        )
        is not None
    )


# --------------------------------------------------------------------------
# Thopter Assembly - return this creature, then create N tokens
# --------------------------------------------------------------------------


def test_thopter_assembly_upkeep_trigger_parses():
    (ability,) = abilities_of_kind(card("Thopter Assembly"), AbilityKind.TRIGGERED)
    assert (
        trigger_effect_for("Thopter Assembly", TriggerEvent.BEGINNING_OF_STEP, ability.effect)
        is not None
    )


# --------------------------------------------------------------------------
# Twisted Image - switch power/toughness, then draw N
# --------------------------------------------------------------------------


def test_twisted_image_parses():
    assert effect_for("Twisted Image", card("Twisted Image").oracle_text) is not None


# --------------------------------------------------------------------------
# Unholy Heat - delirium damage instead
# --------------------------------------------------------------------------


def test_unholy_heat_parses():
    assert effect_for("Unholy Heat", card("Unholy Heat").oracle_text) is not None
