"""Teamwork N: an optional additional cost (`machines/teamwork.py`) printed
"Teamwork N (As an additional cost to cast this spell, you may tap any
number of creatures you control with total power N or more.)" - CR 601.2b's
announcement, CR 118.8a/b's optional additional cost, and CR 701.26a's tap
action, the same machinery kicker's own `pay_kicker` already goes through
(`machines/casting.Casting.pay_teamwork`).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file (a fresh worktree, so `mise run rules:pull`
ran first).

- **CR 601.2b** - the announcement step where an optional additional cost is
  declared, kicker's own precedent for Teamwork's identical shape.
- **CR 118.8a/118.8b** - an additional cost, and that some additional costs
  are optional.
- **CR 701.26a** - tapping a permanent as a cost. Convoke (CR 702.51a) is
  this engine's own precedent for tapping a summoning-sick creature to pay
  a cost; Teamwork's own printed reminder text asks for nothing about
  summoning sickness either, so the same reading applies.
- **CR 109.1** - one object cannot pay a cost twice.
- **CR 208.1** - power, read off the computed board (CR 613.5) so an
  already-pumped creature's power counts.

Repulsor Blast (Teamwork 2, non-modal) is the proof card for actually
paying the cost end to end; HULK SMASH! (Teamwork 4) is used for the
refusal cases, which never reach a full resolution. Go Nuts! (Teamwork 3)
is used for the summoning-sickness case.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import Scenario, mana_from


def board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["HULK SMASH!"],
            battlefield=["Mountain", "Mountain", "Grizzly Bears", "Hill Giant"],
        )
        .player("bob", battlefield=["Elvish Mystic"])
    )


def test_paying_teamwork_taps_the_offered_creatures():
    """CR 118.8a: an additional cost, paid alongside the printed mana cost -
    the creatures are tapped, not sacrificed or consumed - all the way
    through to CR 601.2h's actual payment, not merely announced."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Repulsor Blast"],
            battlefield=["Mountain", "Mountain", "Mountain", "Mountain", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    target = scenario.creature("Hill Giant", "bob")

    casting = scenario.cast("Repulsor Blast")
    casting.pay_teamwork([bears])  # Grizzly Bears' own 2 power, Teamwork 2
    assert casting.teamwork_paid
    casting.choose_targets([target])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()

    assert bears.tapped
    assert bears.zone is Zone.BATTLEFIELD  # tapped, not sacrificed


def test_declining_teamwork_leaves_creatures_untapped():
    """CR 118.8b: the cost is optional - simply never calling `pay_teamwork`
    is what declining it looks like, same as kicker."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    casting = scenario.cast("HULK SMASH!")
    assert not casting.teamwork_paid
    assert not bears.tapped


def test_teamwork_refuses_a_total_power_below_the_threshold():
    """Teamwork 4, offered only Grizzly Bears' 2 power - CR 118.3's
    resources-to-pay-it-fully requirement is not met."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    casting = scenario.cast("HULK SMASH!")
    with pytest.raises(ValueError, match="total power"):
        casting.pay_teamwork([bears])


def test_teamwork_refuses_an_already_tapped_creature():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    bears.tap()

    casting = scenario.cast("HULK SMASH!")
    with pytest.raises(ValueError, match="already tapped"):
        casting.pay_teamwork([bears, giant])


def test_teamwork_refuses_a_creature_offered_twice():
    """CR 109.1: one object cannot pay a cost by naming it twice."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "alice")

    casting = scenario.cast("HULK SMASH!")
    with pytest.raises(ValueError, match="twice"):
        casting.pay_teamwork([giant, giant])


def test_teamwork_refuses_a_creature_the_caster_does_not_control():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "alice")
    mystic = scenario.creature("Elvish Mystic", "bob")

    casting = scenario.cast("HULK SMASH!")
    with pytest.raises(ValueError, match="does not control"):
        casting.pay_teamwork([giant, mystic])


def test_teamwork_refuses_with_no_creature_offered_at_all():
    """CR 118.8b's own "may" needs at least one object, or the cost was
    simply never paid - the same shape `pay_kicker` refuses zero times for."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("HULK SMASH!")
    with pytest.raises(ValueError, match="at least one"):
        casting.pay_teamwork([])


def test_a_summoning_sick_creature_may_still_pay_teamwork():
    """CR 701.26a - the reminder text says only "creatures you control",
    with no summoning-sickness carve-out, the same convoke (CR 702.51a)
    already allows a summoning-sick creature to tap for."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Go Nuts!", "Hill Giant"],
            battlefield=["Forest", "Mountain", "Mountain", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    # A creature cast this same turn is summoning sick (CR 302.6).
    giant = scenario.cast_and_resolve(
        "Hill Giant",
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain"),
    )
    assert giant.summoning_sick

    casting = scenario.cast("Go Nuts!")
    casting.pay_teamwork([giant])  # Hill Giant is 3 power, exactly Teamwork 3
    assert casting.teamwork_paid
