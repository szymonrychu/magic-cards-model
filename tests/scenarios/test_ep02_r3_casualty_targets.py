"""EP-02 R3: keyword reminder text never adds a target.

Cut Your Losses ("Casualty 2 (As you cast this spell, you may sacrifice a
creature with power 2 or greater. When you do, copy this spell and you may
choose a new target for the copy.) Target player mills half their library,
rounded down.") has exactly one target; the reminder's "a new target" is not
a second one (CR 115.1, CR 702.153a).
"""

import pytest

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario

CUT = "Cut Your Losses"


def _board(creatures=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[CUT],
            battlefield=["Island"] * 6 + list(creatures),
        )
        .player("bob", library=["Mountain"] * 20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _bob_library(scenario):
    return len(scenario.player("bob").library)


def _pay(scenario, casting):
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Island"] * 6))
    return scenario.put_on_stack(casting)


def test_one_target_player_mills_half_their_library_rounded_down():
    scenario = _board()
    casting = scenario.cast(CUT, targets=["bob"])
    _pay(scenario, casting)
    scenario.resolve_top()
    assert _bob_library(scenario) == 10


def test_odd_library_rounds_down():
    scenario = _board()
    scenario.player("bob").library.pop()
    casting = scenario.cast(CUT, targets=["bob"])
    _pay(scenario, casting)
    scenario.resolve_top()
    # 19 cards: half rounded down is 9 milled.
    assert _bob_library(scenario) == 10


def test_casualty_paid_copy_also_mills_with_a_new_target():
    scenario = _board(["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    casting = scenario.cast(CUT)
    casting.pay_casualty(bears)
    casting.choose_targets(["bob"])
    _pay(scenario, casting)
    scenario.resolve_top()  # casualty trigger: the copy goes on the stack
    while scenario.game.stack:
        scenario.resolve_top()
    # 20 -> 10 (original or copy) -> 5 (the other).
    assert _bob_library(scenario) == 5


def test_two_targets_are_refused():
    scenario = _board()
    with pytest.raises(ValueError):
        scenario.cast(CUT, targets=["bob", "alice"])
