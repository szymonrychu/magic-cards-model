"""Judge scenario: Orim's Chant against suspending a card (DDR#972).

Amy suspends a Lotus Bloom. Nick wants to stop her with an Orim's Chant. The
episode gives two reasons he cannot, and a third case where he can:

- **Suspending is a special action, so there is nothing to respond to.**
  CR 116.2f: "A player who has a card with suspend in their hand may exile that
  card. This is a special action." CR 116.1: special actions "don't use the
  stack", and CR 405.6d: "Special actions don't use the stack; they happen
  immediately." By the time Nick could have priority the Bloom is already
  exiled with its time counters.

- **Orim's Chant would not have stopped a *cast* anyway** - it is not what is
  happening. Orim's Chant reads "Target player can't cast spells this turn",
  and suspending is not casting.

- **But an Orim's Chant that has *already* resolved does stop it.** CR 116.2f
  permits the special action "only if they could begin to cast that card from
  their hand", and CR 702.62c: "While determining if you could begin to cast a
  card with suspend, take into consideration any effects that would prohibit
  that card from being cast." A player who can't cast spells can't begin to
  cast the Bloom, so the special action is refused - the ruling the episode
  calls "impossible if you don't happen to know this rule".

The engine already carries both halves: `MarkedExile.suspend` is CR 116.2f's
special action and gates itself on `why_cannot_cast_restriction`, and
`machines/casting_restrictions.CastingRuleKind.TARGETED_CANT_CAST` is Orim's
Chant's own recorded effect. This file is the interaction of the two, which
neither `tests/scenarios/test_suspend.py` nor `tests/scenarios/
test_orims_chant.py` covers.

Every CR number in this file was verified with `knowledge_search(q="...",
type="rules")` in the session that wrote it: CR 116.1, CR 116.2f, CR 405.6d,
CR 702.62a, CR 702.62b, CR 702.62c.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import MarkedExile
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    """alice holding a Lotus Bloom (Suspend 3-{0}), bob holding an Orim's Chant."""
    return (
        Scenario()
        .player("alice", hand=["Lotus Bloom"], battlefield=["Plains"])
        .player("bob", hand=["Orim's Chant"], battlefield=["Plains"])
    )


def _suspend(scenario, username: str = "alice"):
    bloom = scenario.find("Lotus Bloom", Zone.HAND, username)
    action = MarkedExile.suspend(scenario.game, bloom, username)
    action.begin_paying().pay()  # Suspend 3-{0}: CR 118.5's acknowledgement
    action.take()
    return bloom


def test_suspending_puts_nothing_on_the_stack_to_respond_to():
    """CR 116.1 / CR 405.6d: a special action happens immediately.

    The Bloom is in exile with three time counters and the stack never held
    anything, so there was no window in which Nick's Orim's Chant could have
    been cast "in response" - the episode's first reason.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bloom = _suspend(scenario)

    assert bloom.zone is Zone.EXILE
    assert bloom.counter_count("time") == 3
    assert scenario.stack_names() == []
    assert scenario.game.stack_is_empty


def test_the_active_player_still_holds_priority_afterwards():
    """A special action is taken *while holding priority* and does not pass it.

    CR 116.1: "Special actions are actions a player may take when they have
    priority that don't use the stack." Nothing changed hands, which is the
    mechanical form of "it is not possible to respond to suspending a card at
    all".
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.priority_holder == "alice"

    _suspend(scenario)

    assert scenario.priority_holder == "alice"


def test_a_resolved_orims_chant_stops_the_suspend_too():
    """DDR#972's real ruling, via CR 702.62c.

    Orim's Chant does not mention suspend; CR 116.2f's "only if they could
    begin to cast that card from their hand" is what reaches it, and CR 702.62c
    says a casting prohibition counts when answering that question. The Bloom
    stays in hand, untouched.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    (plains,) = scenario.untapped_sources("Plains", username="bob")
    scenario.cast_and_resolve("Orim's Chant", plains, username="bob", targets=["alice"])

    bloom = scenario.find("Lotus Bloom", Zone.HAND)
    with pytest.raises(ValueError, match="could not begin to be cast"):
        MarkedExile.suspend(scenario.game, bloom, "alice")

    assert bloom.zone is Zone.HAND
    assert bloom.counter_count("time") == 0


def test_orims_chant_on_the_other_player_leaves_the_suspend_alone():
    """CR 611.1's effect names *a target player*, not everybody.

    Orim's Chant aimed at bob restricts bob. alice suspends normally - which is
    what keeps the test above from passing for the wrong reason (a blanket
    "anything on the battlefield stops suspend").
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    (plains,) = scenario.untapped_sources("Plains", username="bob")
    scenario.cast_and_resolve("Orim's Chant", plains, username="bob", targets=["bob"])

    bloom = _suspend(scenario)

    assert bloom.zone is Zone.EXILE
    assert bloom.counter_count("time") == 3
