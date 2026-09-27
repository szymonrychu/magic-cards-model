"""Scenario: an activated ability that puts up to X of a counter kind on
itself, with a printed ceiling on the *total* the permanent may ever carry.

Clockwork Steed: "{X}, {T}: Put up to X +1/+0 counters on this creature.
This ability can't cause the total number of +1/+0 counters on this
creature to be greater than four. Activate only during your upkeep."

CR 107.3a: while the ability is on the stack, X is the announced value.
"Up to X" (CR 608.2d) always permits choosing fewer than X, including none;
nothing on the card ever makes fewer counters better, so this reads the
same "always take the maximum" simplification the engine already takes for
"remove up to N counters" (`machines/effects._parse_remove_up_to_n_counters_
from_target_clause`) - here further bounded a second time by the printed
total ceiling, whichever is smaller.

The trailing "Activate only during your turn"-style timing restriction is
read (or not) by a separate workstream; these scenarios activate the
ability directly through the harness rather than through the turn structure,
so that restriction never enters into what is being proven here.

Every CR number was looked up with `mise run rules:find <n>` in this session.
"""

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


def test_activating_below_the_cap_adds_up_to_x_counters():
    """One counter already on it, X=2: room for three more, but only two are
    asked for, so all of it lands."""
    scenario, steed = steed_scenario(1)
    scenario.start_at(Step.UPKEEP)

    scenario.activate(steed, x_value=2, auto=True)
    scenario.resolve_top()

    assert steed.counter_count("+1/+0") == 3
    assert scenario.game.characteristics_of(steed).power == 3


def test_activating_at_the_cap_adds_nothing():
    """Already at the printed ceiling of four: the ability still resolves,
    but "can't cause the total ... to be greater than four" leaves no room
    for any of the announced X."""
    scenario, steed = steed_scenario(4)
    scenario.start_at(Step.UPKEEP)

    scenario.activate(steed, x_value=3, auto=True)
    scenario.resolve_top()

    assert steed.counter_count("+1/+0") == 4


def test_activating_with_partial_room_stops_at_the_cap():
    """Three on it, X=5: only one more fits under the ceiling of four, so one
    is added even though five were announced and paid for."""
    scenario, steed = steed_scenario(3)
    scenario.start_at(Step.UPKEEP)

    scenario.activate(steed, x_value=5, auto=True)
    scenario.resolve_top()

    assert steed.counter_count("+1/+0") == 4


def test_activating_for_x_equal_zero_adds_nothing():
    """CR 107.3b: X can be announced as 0, a legal activation that simply
    asks for none."""
    scenario, steed = steed_scenario(1)
    scenario.start_at(Step.UPKEEP)

    scenario.activate(steed, x_value=0, auto=True)
    scenario.resolve_top()

    assert steed.counter_count("+1/+0") == 1
