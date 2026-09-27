"""Scenario: "When you cast this spell, you gain half X life and draw half X
cards. Round down each time." - Hydroid Krasis.

X here is CR 107.3a's value announced for the *spell itself* while it was
cast - never the triggered ability's own, since a triggered ability
announces no X at all (the same read `_parse_cast_trigger_look_top_x_take_
one_clause` already gives Geometer's Arthropod's "look at the top X cards of
your library").

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 117.2a / 603.3** - the trigger resolves above its own spell.
- **CR 107.3a** - the caster chooses and announces X as part of casting; it
  is fixed on the stack from that point on.
- **CR 107.1a** - a spell or ability that could generate a fractional number
  always states the rounding direction; here it is a single trailing
  sentence governing both halves rather than one "rounded down" per half.
- **CR 107.1b** - a negative result is treated as zero, so X=0 gains no life
  and draws no cards, not a negative amount of either.
- **CR 118.4 / CR 121.1** - life gain and drawing are ordinary game actions,
  simply sized by the halved X here.

The effect is `_parse_half_x_life_and_draw_half_x_cards_clause` in
`machines/effects.py`, tried by `_ability_effect_or_notice`.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def _cast_hydroid_krasis(x: int) -> Scenario:
    # {X}{G}{U}: X generic plus one green and one blue mana.
    forests = x
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Hydroid Krasis"],
            battlefield=["Forest"] * (forests + 1) + ["Island"],
            library=["Mountain"] * 10,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Hydroid Krasis", "alice")
    payment = casting.determine_cost(x_value=x)
    scenario.pay_with(
        payment, *scenario.untapped_sources(*(["Forest"] * (forests + 1) + ["Island"]))
    )
    scenario.put_on_stack(casting)
    return scenario


def test_the_cast_trigger_sits_above_its_own_spell_on_the_stack():
    scenario = _cast_hydroid_krasis(4)
    assert scenario.stack_names() == [
        "Hydroid Krasis",
        "Hydroid Krasis's triggered ability",
    ]


def test_x_of_four_rounds_the_half_down_to_two():
    scenario = _cast_hydroid_krasis(4)
    alice = scenario.player("alice")
    life_before = alice.life
    hand_before = len(alice.hand)

    scenario.pass_until_resolved()  # the trigger only

    assert alice.life == life_before + 2
    assert len(alice.hand) == hand_before + 2
    assert "Hydroid Krasis" in scenario.stack_names(), "the creature has not resolved yet"


def test_x_of_five_rounds_the_half_down_to_two_not_up_to_three():
    """CR 107.1a: the card prints "round down", so 5 halves to 2, never 3 -
    the corner case that would catch a reader defaulting to round-up."""
    scenario = _cast_hydroid_krasis(5)
    alice = scenario.player("alice")
    life_before = alice.life
    hand_before = len(alice.hand)

    scenario.pass_until_resolved()

    assert alice.life == life_before + 2
    assert len(alice.hand) == hand_before + 2


def test_x_of_zero_gains_no_life_and_draws_no_cards():
    scenario = _cast_hydroid_krasis(0)
    alice = scenario.player("alice")
    life_before = alice.life
    hand_before = len(alice.hand)

    scenario.pass_until_resolved()

    assert alice.life == life_before
    assert len(alice.hand) == hand_before


def test_x_of_one_halves_down_to_zero_not_a_negative_amount():
    """CR 107.1b's floor-at-zero would only bite a *negative* total, which
    "half X" can never produce - but 1 still halves down to 0, not up to 1,
    the plainest possible round-down check."""
    scenario = _cast_hydroid_krasis(1)
    alice = scenario.player("alice")
    life_before = alice.life
    hand_before = len(alice.hand)

    scenario.pass_until_resolved()

    assert alice.life == life_before
    assert len(alice.hand) == hand_before


def test_the_counters_static_still_gives_the_resolved_creature_x_plus_one_plus_one_counters():
    """Not the cast trigger itself, but proves the two abilities are read
    independently: "This creature enters with X +1/+1 counters on it." is a
    *static* ability read once Hydroid Krasis is a permanent, unaffected by
    the halving the cast trigger already applied to life and cards."""
    from magic_cards_model.models.card_state import Counter

    scenario = _cast_hydroid_krasis(4)
    scenario.pass_until_resolved()  # the trigger
    scenario.pass_until_resolved()  # Hydroid Krasis itself

    krasis = scenario.creature("Hydroid Krasis")
    assert krasis.counters[Counter.PLUS_ONE] == 4


def test_generalises_off_a_differently_named_halved_quantity():
    """Not literally "X": the backreferenced `<of>` in
    `_HALF_X_LIFE_AND_DRAW_HALF_X_CARDS_RE` requires the identical printed
    expression on both sides but never assumes it spells "X" - proved by
    parsing a variant that halves something else, the same direct-parse
    proof `test_cast_triggers.py`'s own `test_the_mass_untap_reads_
    generically_off_untap_all_creatures_you_control` uses for a differently
    worded untap sentence.
    """
    from magic_cards_model.machines.effects import (
        _parse_half_x_life_and_draw_half_x_cards_clause,
    )

    assert (
        _parse_half_x_life_and_draw_half_x_cards_clause(
            "You gain half three life and draw half three cards. Round up each time."
        )
        is not None
    )
    # The two halves must still name the *same* expression - a card that
    # halved two different things this way would not be this shape.
    assert (
        _parse_half_x_life_and_draw_half_x_cards_clause(
            "You gain half X life and draw half Y cards. Round down each time."
        )
        is None
    )
