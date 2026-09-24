""" "Distribute N +1/+1 counters among up to N target creatures. They gain
<keyword> until end of turn."

- **Ajani, Sleeper Agent**'s `-3`: three counters among up to three target
  creatures, then vigilance.
- **Vivien, Arkbow Ranger**'s `+1` (the second printing: not a listed card,
  not in any api deck): two counters among up to two target creatures, then
  trample.

"They" is the anaphor for the creatures the first sentence targeted (CR
608.2c: later text refers back to the earlier instruction), so only the
chosen targets gain the keyword - never every creature on the board.

The division is announced as the ability is activated, one share per target,
each at least one, adding up to the whole amount (CR 601.2d, which CR 602.2b
imports for activated abilities). "Up to N" lets the controller choose any
number of targets from zero to N (CR 601.2c); with zero targets the loyalty
cost is still paid and nothing else happens.

A target that is illegal on resolution gets nothing - neither its share nor
the keyword - and its share is not handed to the others (CR 608.2b; CR 115.7f
keeps the division fixed).

"Until end of turn" effects end in the cleanup step (CR 514.2).

CR numbers read with `mise run rules:find` in the session that wrote this
file: 514.2, 601.2c, 601.2d, 602.2b, 608.2b, 608.2c, 115.7f.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import PlayedScenario, Scenario

AJANI = "Ajani, Sleeper Agent"
VIVIEN = "Vivien, Arkbow Ranger"
CREATURES = ["Grizzly Bears", "Llanowar Elves", "Memnite", "Elvish Mystic"]


def _board(walker: str) -> tuple[PlayedScenario, object]:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[walker], battlefield=list(CREATURES), library=["Forest"] * 3)
        .player("bob", battlefield=["Tarmogoyf"], library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    planeswalker = scenario.put_onto_battlefield(walker, "alice")
    if walker == AJANI:
        # Staged loyalty for the -3; the printed starting loyalty is 4.
        assert planeswalker.counter_count(Counter.LOYALTY) >= 3
    return scenario, planeswalker


def _creature(scenario: PlayedScenario, name: str, username: str = "alice"):
    return scenario.find(name, Zone.BATTLEFIELD, username)


def _plus(state) -> int:
    return state.counter_count(Counter.PLUS_ONE)


def test_three_targets_get_one_counter_each_and_vigilance():
    scenario, ajani = _board(AJANI)
    bears, elves, memnite, mystic = (_creature(scenario, n) for n in CREATURES)
    loyalty = ajani.counter_count(Counter.LOYALTY)

    scenario.activate(ajani, index=1, username="alice", targets=[bears, elves, memnite])
    scenario.pass_until_resolved()

    assert [_plus(c) for c in (bears, elves, memnite, mystic)] == [1, 1, 1, 0]
    assert all(has_keyword(c, Keyword.VIGILANCE, scenario.game) for c in (bears, elves, memnite))
    assert not has_keyword(mystic, Keyword.VIGILANCE, scenario.game)
    assert ajani.counter_count(Counter.LOYALTY) == loyalty - 3


def test_one_target_gets_all_three_counters():
    scenario, ajani = _board(AJANI)
    bears = _creature(scenario, "Grizzly Bears")

    scenario.activate(ajani, index=1, username="alice", targets=[bears])
    scenario.pass_until_resolved()

    assert _plus(bears) == 3
    assert has_keyword(bears, Keyword.VIGILANCE, scenario.game)


def test_two_targets_split_as_announced():
    scenario, ajani = _board(AJANI)
    bears, elves = _creature(scenario, "Grizzly Bears"), _creature(scenario, "Llanowar Elves")

    scenario.activate(ajani, index=1, username="alice", targets=[bears, elves], division=[1, 2])
    scenario.pass_until_resolved()

    assert (_plus(bears), _plus(elves)) == (1, 2)
    assert has_keyword(bears, Keyword.VIGILANCE, scenario.game)
    assert has_keyword(elves, Keyword.VIGILANCE, scenario.game)


def test_an_opponents_creature_is_a_legal_target():
    scenario, ajani = _board(AJANI)
    goyf = _creature(scenario, "Tarmogoyf", "bob")

    scenario.activate(ajani, index=1, username="alice", targets=[goyf])
    scenario.pass_until_resolved()

    assert _plus(goyf) == 3
    assert has_keyword(goyf, Keyword.VIGILANCE, scenario.game)


def test_zero_targets_still_pays_the_loyalty():
    scenario, ajani = _board(AJANI)
    loyalty = ajani.counter_count(Counter.LOYALTY)

    scenario.activate(ajani, index=1, username="alice", targets=[])
    scenario.pass_until_resolved()

    assert ajani.counter_count(Counter.LOYALTY) == loyalty - 3
    assert all(_plus(_creature(scenario, n)) == 0 for n in CREATURES)
    assert not any(
        has_keyword(_creature(scenario, n), Keyword.VIGILANCE, scenario.game) for n in CREATURES
    )


@pytest.mark.parametrize("division", [[1, 1], [0, 3], [2, 2], [3]])
def test_an_illegal_division_is_refused(division):
    """CR 601.2d: one share per target, each at least one, summing to three."""
    scenario, ajani = _board(AJANI)
    bears, elves = _creature(scenario, "Grizzly Bears"), _creature(scenario, "Llanowar Elves")

    with pytest.raises(ValueError, match="601.2d"):
        scenario.activate(
            ajani, index=1, username="alice", targets=[bears, elves], division=division
        )


def test_a_target_gone_on_resolution_gets_nothing_and_its_share_is_not_moved():
    scenario, ajani = _board(AJANI)
    bears, elves = _creature(scenario, "Grizzly Bears"), _creature(scenario, "Llanowar Elves")

    scenario.activate(ajani, index=1, username="alice", targets=[bears, elves], division=[2, 1])
    scenario.game.destroy(bears)
    scenario.pass_until_resolved()

    assert bears.zone is not Zone.BATTLEFIELD
    assert _plus(elves) == 1
    assert has_keyword(elves, Keyword.VIGILANCE, scenario.game)


def test_vigilance_ends_at_cleanup_but_the_counters_stay():
    scenario, ajani = _board(AJANI)
    bears = _creature(scenario, "Grizzly Bears")

    scenario.activate(ajani, index=1, username="alice", targets=[bears])
    scenario.pass_until_resolved()
    scenario.game.cleanup_step()

    assert not has_keyword(bears, Keyword.VIGILANCE, scenario.game)
    assert _plus(bears) == 3


def test_a_vigilant_attacker_does_not_tap():
    scenario, ajani = _board(AJANI)
    bears = _creature(scenario, "Grizzly Bears")
    bears.summoning_sick = False

    scenario.activate(ajani, index=1, username="alice", targets=[bears])
    scenario.pass_until_resolved()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)

    assert not bears.tapped


# -- Vivien, Arkbow Ranger: two counters, trample ---------------------------


def test_vivien_splits_two_counters_and_grants_trample():
    scenario, vivien = _board(VIVIEN)
    bears, elves, memnite = (_creature(scenario, n) for n in CREATURES[:3])

    scenario.activate(vivien, index=0, username="alice", targets=[bears, elves])
    scenario.pass_until_resolved()

    assert (_plus(bears), _plus(elves), _plus(memnite)) == (1, 1, 0)
    assert has_keyword(bears, Keyword.TRAMPLE, scenario.game)
    assert has_keyword(elves, Keyword.TRAMPLE, scenario.game)
    assert not has_keyword(memnite, Keyword.TRAMPLE, scenario.game)
    assert not has_keyword(bears, Keyword.VIGILANCE, scenario.game)


def test_vivien_one_target_takes_both_counters():
    scenario, vivien = _board(VIVIEN)
    memnite = _creature(scenario, "Memnite")

    scenario.activate(vivien, index=0, username="alice", targets=[memnite])
    scenario.pass_until_resolved()

    assert _plus(memnite) == 2
    assert has_keyword(memnite, Keyword.TRAMPLE, scenario.game)


def test_vivien_cannot_take_three_targets():
    """CR 601.2c: "up to two" caps the number of targets."""
    scenario, vivien = _board(VIVIEN)
    bears, elves, memnite = (_creature(scenario, n) for n in CREATURES[:3])

    with pytest.raises(ValueError):
        scenario.activate(vivien, index=0, username="alice", targets=[bears, elves, memnite])
