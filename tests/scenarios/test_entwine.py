"""Entwine: paying to choose every mode (CR 702.42).

CR 702.42a: "Entwine is a static ability of modal spells (see rule 700.2) that
functions while the spell is on the stack. 'Entwine [cost]' means "You may choose
all modes of this spell instead of just the number specified. **If you do, you
pay an additional [cost].**" Using the entwine ability follows the rules for
choosing modes and paying additional costs in rules 601.2b and 601.2f-h."

Two halves in one sentence, and it is the second that used to be missing: the
cost is an *additional* one (CR 118.8a), so the printed mana cost is still paid
on top of it. That is the difference from an alternative cost, and it is why an
entwined Tooth and Nail is {7}{G}{G} rather than {2}.

CR 702.42b is the resolution half: "If the entwine cost was paid, follow the text
of each of the modes in the order written on the card when the spell resolves."
Tooth and Nail has no entry in `machines/effects.py`, so nothing follows either
mode - the xfail at the bottom of this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.modes import modal_profile
from magic_cards_model.models import Zone
from magic_cards_model.models.mana import ManaCost
from tests.cards import card
from tests.scenarios.harness import Scenario, mana_from


def board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Tooth and Nail", "Colossal Dreadmaw"],
            library=["Craw Wurm"],
            battlefield=["Forest"] * 9,
        )
        .player("bob")
    )


def test_the_entwine_cost_is_read_off_the_printing():
    """CR 702.1a: `Entwine {2}` on Tooth and Nail."""
    profile = modal_profile(card("Tooth and Nail"))
    assert profile is not None
    assert profile.entwine_cost == "{2}"


def test_choosing_one_mode_charges_only_the_printed_cost():
    """The control: entwine is optional (CR 702.42a says "you may")."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Tooth and Nail")
    casting.choose_modes([1])

    assert casting.total_cost.mana == ManaCost.parse("{5}{G}{G}")


def test_entwining_opens_every_mode_and_charges_the_extra_cost():
    """CR 702.42a: both halves, in one call.

    An additional cost (CR 118.8a), so {2} goes *on top of* {5}{G}{G}.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Tooth and Nail")
    casting.choose_modes([1, 2], entwined=True)

    assert casting.entwined
    assert casting.chosen_mode_numbers == [1, 2]
    assert casting.total_cost.mana == ManaCost.parse("{7}{G}{G}")


def test_the_entwined_spell_really_has_to_be_paid_for():
    """CR 118.3: nine lands is exactly enough, and eight is not."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Tooth and Nail")
    casting.choose_modes([1, 2], entwined=True)
    payment = casting.begin_paying()

    for source in scenario.untapped_sources(*["Forest"] * 8):
        payment.tap_for_mana(source, mana_from(source))
    with pytest.raises(ValueError):
        payment.pay()

    (last,) = scenario.untapped_sources("Forest")
    payment.tap_for_mana(last, mana_from(last))
    payment.pay()

    assert casting.cast().zone is Zone.STACK


def test_a_spell_without_entwine_refuses_the_announcement():
    """CR 702.42a is a static ability of the card; a card without it has none."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Kozilek's Command"], battlefield=["Forest"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Kozilek's Command")
    with pytest.raises(ValueError, match="no entwine cost"):
        casting.choose_modes([1, 2, 3, 4], entwined=True)


@pytest.mark.xfail(
    reason=(
        "CR 702.42b: 'If the entwine cost was paid, follow the text of each of the "
        "modes in the order written on the card when the spell resolves.' "
        "machines/effects.py is keyed by card name and has no Tooth and Nail entry, "
        "and CR 700.2's 'what a mode does on resolution' is unmodelled in general. "
        "See docs/engine-coverage.md."
    ),
    strict=True,
)
def test_an_entwined_tooth_and_nail_does_both_modes():
    """CR 702.42b, in printed order (CR 608.2c)."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Tooth and Nail")
    casting.choose_modes([1, 2], entwined=True)
    payment = casting.begin_paying()
    for source in scenario.untapped_sources(*["Forest"] * 9):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert "Craw Wurm" in scenario.battlefield_names()
    assert "Colossal Dreadmaw" in scenario.battlefield_names()
