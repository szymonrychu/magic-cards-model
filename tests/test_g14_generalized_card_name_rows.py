"""G14-2: card-name registry rows with hardcoded counts, replaced by whole-
text parsers that read every count through `numbers.py`.

Unit-test file, the same discipline `test_effects.py` and
`test_g14_whole_card_count_regexes.py` use: real printed text for regression,
a hand-typed sentence of the identical shape with different counts for the
generalization proof, since none of these four shapes has a second real
Modern printing with a different count. Full behavioural regression for the
real cards (Seasoned Pyromancer's discard/draw/token decision, Twisted
Image's switch-then-draw, Unholy Heat's delirium branch) is already carried
by `tests/scenarios/test_cost_reduction_shapes.py`,
`tests/scenarios/test_decisions_during_resolution.py`,
`tests/scenarios/test_continuous_effects_with_a_duration.py`,
`tests/scenarios/test_layer_effects_round_trip.py`, and
`tests/scenarios/test_delirium.py`; Thopter Assembly's own return-then-create
resolution had no scenario test before this wave, so
`tests/scenarios/test_thopter_assembly.py` is new.

Every CR number here was already verified by the parsers' own docstrings
(CR 608.2c, CR 701.9b, CR 401, CR 111.9, CR 613.4d, CR 207.2c) - no new rule
is asserted here.
"""

from magic_cards_model.machines import TriggerEvent
from magic_cards_model.machines.effects import effect_for, trigger_effect_for
from tests.cards import card

# --------------------------------------------------------------------------
# Seasoned Pyromancer - discard N, draw N, a token per nonland discarded
# --------------------------------------------------------------------------


def _seasoned_pyromancer_enters_trigger_text() -> str:
    return card("Seasoned Pyromancer").oracle_text.split("\n")[0].split(", ", 1)[1]


def test_seasoned_pyromancer_enters_trigger_parses():
    assert (
        trigger_effect_for(
            "Seasoned Pyromancer",
            TriggerEvent.ENTERS_THE_BATTLEFIELD,
            _seasoned_pyromancer_enters_trigger_text(),
        )
        is not None
    )


def test_discard_then_draw_token_per_nonland_generalizes_to_different_counts_and_a_token():
    """Discard three, draw three, and a blue Faerie with flying instead of
    Seasoned Pyromancer's own two/two/red Elemental.
    """
    text = (
        "discard three cards, then draw three cards. "
        "For each nonland card discarded this way, create a 1/1 blue Faerie "
        "creature token with flying."
    )
    assert (
        trigger_effect_for("Not Seasoned Pyromancer", TriggerEvent.ENTERS_THE_BATTLEFIELD, text)
        is not None
    )


# --------------------------------------------------------------------------
# Thopter Assembly - return this creature, then create N tokens
# --------------------------------------------------------------------------


def _thopter_assembly_upkeep_trigger_text() -> str:
    from magic_cards_model.machines import AbilityKind, abilities_of_kind

    (ability,) = abilities_of_kind(card("Thopter Assembly"), AbilityKind.TRIGGERED)
    return ability.effect


def test_thopter_assembly_upkeep_trigger_parses():
    assert (
        trigger_effect_for(
            "Thopter Assembly",
            TriggerEvent.BEGINNING_OF_STEP,
            _thopter_assembly_upkeep_trigger_text(),
        )
        is not None
    )


def test_return_self_then_create_tokens_generalizes_to_a_different_token_count():
    """Three 2/2 blue Birds with flying instead of Thopter Assembly's own
    five 1/1 colorless Thopters.
    """
    text = (
        "return this creature to its owner's hand and create three 2/2 blue Bird "
        "artifact creature tokens with flying."
    )
    assert (
        trigger_effect_for("Not Thopter Assembly", TriggerEvent.BEGINNING_OF_STEP, text) is not None
    )


# --------------------------------------------------------------------------
# Twisted Image - switch power/toughness, then draw N
# --------------------------------------------------------------------------


def test_twisted_image_parses():
    assert effect_for("Twisted Image", card("Twisted Image").oracle_text) is not None


def test_switch_power_toughness_then_draw_generalizes_to_a_different_draw_count():
    """ "Draw two cards" instead of Twisted Image's own "a card"."""
    text = "Switch target creature's power and toughness until end of turn. Draw two cards."
    assert effect_for("Not Twisted Image", text) is not None


# --------------------------------------------------------------------------
# Unholy Heat - delirium damage instead
# --------------------------------------------------------------------------


def test_unholy_heat_parses():
    assert effect_for("Unholy Heat", card("Unholy Heat").oracle_text) is not None


def test_delirium_damage_instead_generalizes_to_a_different_pair_of_amounts():
    """A different name (matched by backreference, not literally), target,
    and pair of damage amounts than Unholy Heat's own 2/6.
    """
    text = (
        "Test Card deals 3 damage to target creature.\n"
        "Delirium — Test Card deals 7 damage instead if there are four or more "
        "card types among cards in your graveyard."
    )
    assert effect_for("Not Unholy Heat", text) is not None
