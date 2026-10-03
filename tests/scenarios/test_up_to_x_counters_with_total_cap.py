"""Scenario: an activated ability that puts up to X of a counter kind on
itself, with a printed ceiling on the *total* the permanent may ever carry.

Clockwork Steed: "{X}, {T}: Put up to X +1/+0 counters on this creature.
This ability can't cause the total number of +1/+0 counters on this
creature to be greater than four. Activate only during your upkeep."

CR 107.3a: while the ability is on the stack, X is the announced value.
"Up to X" (CR 608.2d) always permits choosing fewer than X, including none -
a real choice for the controller, per Clockwork Steed's own Scryfall ruling
(2008-10-01): "When Clockwork Steed's last ability resolves, you can choose
to put fewer than X +1/+0 counters on it." Asked through `Game.choose_an_
amount` (`DecisionKind.CHOOSE_AN_AMOUNT`), never defaulted to the maximum -
unlike "remove up to N counters" (`machines/effects._parse_remove_up_to_n_
counters_from_target_clause`), where nothing on the card ever makes fewer
counters removed better and the engine keeps taking the maximum there - the
ceiling below (whichever is smaller of the printed "up to X" and the room
left under the printed total cap) only bounds how *high* the chosen amount
may legally go.

The trailing "Activate only during your turn"-style timing restriction is
read (or not) by a separate workstream; these scenarios activate the
ability directly through the harness rather than through the turn structure,
so that restriction never enters into what is being proven here.

Every CR number was looked up with `mise run rules:find <n>` in this session.
"""

import pytest

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def steed_scenario(counters: int) -> tuple[Scenario, object]:
    """A Clockwork Steed with its +1/+0 counter count set to `counters`.
    Placed directly on the battlefield (never cast), so the "enters with
    four" replacement never runs and it starts at zero - `test_counters.py`'s
    own generic +X/+Y-counter test already proves that replacement and CR
    122.1a's own power/toughness bonus separately."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Clockwork Steed", "Forest", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    steed = scenario.creature("Clockwork Steed")
    if counters:
        steed.add_counters("+1/+0", counters)
    return scenario, steed


def test_choosing_the_maximum_below_the_cap_adds_up_to_x_counters():
    """One counter already on it, X=2: room for three more, but only two are
    asked for, so choosing the full two lands all of it."""
    scenario, steed = steed_scenario(1)
    scenario.start_at(Step.UPKEEP)
    scenario.will_choose_an_amount(2, source="Clockwork Steed")

    scenario.activate(steed, x_value=2, auto=True)
    scenario.resolve_top()

    assert steed.counter_count("+1/+0") == 3
    assert scenario.game.characteristics_of(steed).power == 3


def test_choosing_fewer_than_the_maximum_adds_only_that_many():
    """CR 608.2d / the card's own Oracle ruling: the controller may choose
    fewer than X - one counter already on it, X=3 announced, but only one
    of the three legal counters is actually chosen."""
    scenario, steed = steed_scenario(1)
    scenario.start_at(Step.UPKEEP)
    scenario.will_choose_an_amount(1, source="Clockwork Steed")

    scenario.activate(steed, x_value=3, auto=True)
    scenario.resolve_top()

    assert steed.counter_count("+1/+0") == 2
    assert scenario.game.characteristics_of(steed).power == 2


def test_declining_the_choice_adds_nothing():
    """Choosing zero is always legal (CR 608.2d's "up to" never forces a
    minimum), the same way an unscripted answer defaults to it."""
    scenario, steed = steed_scenario(1)
    scenario.start_at(Step.UPKEEP)
    scenario.will_choose_an_amount(0, source="Clockwork Steed")

    scenario.activate(steed, x_value=2, auto=True)
    scenario.resolve_top()

    assert steed.counter_count("+1/+0") == 1


def test_activating_at_the_cap_asks_nothing_and_adds_nothing():
    """Already at the printed ceiling of four: the ability still resolves,
    but "can't cause the total ... to be greater than four" leaves no room
    for any of the announced X, so there is nothing left to even ask about."""
    scenario, steed = steed_scenario(4)
    scenario.start_at(Step.UPKEEP)

    scenario.activate(steed, x_value=3, auto=True)
    scenario.resolve_top()

    assert steed.counter_count("+1/+0") == 4
    assert [q for q in scenario.questions_asked() if q.source == "Clockwork Steed"] == []


def test_choosing_the_partial_room_left_adds_that_many():
    """Three on it, X=5: only one more fits under the ceiling of four, so
    the legal ceiling actually offered is one, not the announced five."""
    scenario, steed = steed_scenario(3)
    scenario.start_at(Step.UPKEEP)
    scenario.will_choose_an_amount(1, source="Clockwork Steed")

    scenario.activate(steed, x_value=5, auto=True)
    scenario.resolve_top()

    assert steed.counter_count("+1/+0") == 4


def test_choosing_more_than_the_partial_room_is_refused():
    """Three on it, X=5: choosing five outright - more than the room left
    under the printed cap - is not a legal answer at all (CR 608.2d); `Game.
    ask` refuses it rather than silently capping it to what fits."""
    scenario, steed = steed_scenario(3)
    scenario.start_at(Step.UPKEEP)
    scenario.will_choose_an_amount(5, source="Clockwork Steed")

    scenario.activate(steed, x_value=5, auto=True)
    with pytest.raises(ValueError, match="CR 608.2d"):
        scenario.resolve_top()


def test_activating_for_x_equal_zero_asks_nothing_and_adds_nothing():
    """CR 107.3b: X can be announced as 0, a legal activation that leaves no
    room to choose any amount at all, so nothing is even asked."""
    scenario, steed = steed_scenario(1)
    scenario.start_at(Step.UPKEEP)

    scenario.activate(steed, x_value=0, auto=True)
    scenario.resolve_top()

    assert steed.counter_count("+1/+0") == 1
    assert [q for q in scenario.questions_asked() if q.source == "Clockwork Steed"] == []
