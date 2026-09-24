"""Scenario: a spell's own conditional flash grant, and "This spell can't be
countered."

CR 702.8a: "Flash is a static ability that functions in any zone from which
you could play the card it's on. 'Flash' means "You may play this card any
time you could cast an instant."" Bard's Company doesn't print the bare
keyword - it prints a conditional grant of the identical permission: "You may
cast this spell as though it had flash if you control a Human." Read off the
spell's own text by `casting.conditional_flash_condition` and handed to
`Game.condition_holds`, the same reader every other printed "if <condition>"
already goes through.

CR 113.6g: "An object's ability that states it can't be countered or can't be
copied functions on the stack." Enforced in exactly one place,
`Game.counter` - a counterspell aimed at an uncounterable spell still
resolves and still finds its target, it simply fails to remove the spell
from the stack.

Off-pool proof: Illusion Spinners ("You may cast this spell as though it had
flash if you control a Faerie.") for the conditional-flash template, and
Carnage Tyrant ("This spell can't be countered.") for the uncounterable
template - both real Modern/Pioneer-legal printings outside the deck pool,
added with `scripts/add_card.py`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import conditional_flash_condition, why_cannot_cast_now
from magic_cards_model.models import Zone
from tests.cards import card

from .harness import Scenario


def test_the_condition_is_read_off_the_spells_own_text():
    assert conditional_flash_condition(card("Bard's Company").oracle_text) == "you control a Human"
    assert conditional_flash_condition(card("Illusion Spinners").oracle_text) == (
        "you control a Faerie"
    )
    assert conditional_flash_condition(card("Grizzly Bears").oracle_text) is None


def test_bards_company_cannot_be_cast_at_instant_speed_with_no_human():
    """No Human on the board: ordinary sorcery-speed timing applies (CR 117.1a)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Bard's Company"], battlefield=["Plains", "Island"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    with pytest.raises(ValueError, match="only cast it during their own main phase"):
        scenario.cast("Bard's Company")


def test_bards_company_can_be_cast_at_instant_speed_with_a_human_in_play():
    """Grizzly Bears is not a Human; a Human creature is what unlocks it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Bard's Company"],
            battlefield=["Plains", "Plains", "Island", "Island", "Accorder Paladin"],
        )
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    company = scenario.cast_and_resolve(
        "Bard's Company", *scenario.untapped_sources("Plains", "Plains", "Island", "Island")
    )
    assert company.zone is Zone.BATTLEFIELD


def test_illusion_spinners_reads_the_identical_template_for_a_faerie():
    """Off-pool proof: the same reader, a different creature type and card."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Illusion Spinners"],
            battlefield=["Island", "Island", "Island", "Island", "Island", "Faerie Vandal"],
        )
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    spinners = scenario.cast_and_resolve(
        "Illusion Spinners",
        *scenario.untapped_sources("Island", "Island", "Island", "Island", "Island"),
    )
    assert spinners.zone is Zone.BATTLEFIELD


def test_a_human_who_left_before_the_cast_no_longer_grants_flash():
    """`condition_holds` is read fresh every time (CR 611.3a) - a Human that
    already died grants nothing."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Bard's Company"],
            battlefield=["Plains", "Plains", "Island", "Island", "Accorder Paladin"],
        )
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    paladin = scenario.creature("Accorder Paladin", "alice")
    scenario.game.destroy(paladin)

    spell = scenario.find("Bard's Company", Zone.HAND, "alice")
    reason = why_cannot_cast_now(spell, "alice", scenario.game)
    assert reason is not None and "only cast it during their own main phase" in reason


def test_gigantic_big_bear_cannot_be_countered():
    """CR 113.6g: the counter simply fails; the spell stays on the stack and
    resolves normally."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Gigantic Big Bear"],
            battlefield=["Forest"] * 7,
        )
        .player("bob", hand=["Counterspell"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.cast_onto_stack(
        "Gigantic Big Bear", *scenario.untapped_sources("Forest"), auto=True
    )
    scenario.pass_priority("alice")
    blue = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Counterspell", *blue, targets=[bear], username="bob")
    scenario.resolve_top()  # Counterspell resolves first (LIFO), fails to counter.
    scenario.resolve_top()  # Gigantic Big Bear resolves normally.

    assert bear.zone is Zone.BATTLEFIELD


def test_carnage_tyrant_reads_the_identical_uncounterable_template():
    """Off-pool proof: Carnage Tyrant's own "This spell can't be countered."
    (plus hexproof, so it can't be targeted at all - the counter here targets
    the spell on the stack, CR 115.1, which hexproof does not reach)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Carnage Tyrant"], battlefield=["Forest"] * 6)
        .player("bob", hand=["Counterspell"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tyrant = scenario.cast_onto_stack(
        "Carnage Tyrant", *scenario.untapped_sources("Forest"), auto=True
    )
    scenario.pass_priority("alice")
    blue = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Counterspell", *blue, targets=[tyrant], username="bob")
    scenario.resolve_top()
    scenario.resolve_top()

    assert tyrant.zone is Zone.BATTLEFIELD
