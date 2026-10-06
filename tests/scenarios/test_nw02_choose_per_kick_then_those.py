"""Temporal Firestorm ({3}{R}{R}, Kicker {1}{W} and/or {1}{U}): "Choose up to
X creatures and/or planeswalkers you control, where X is the number of times
this spell was kicked. Those permanents phase out. Temporal Firestorm deals 5
damage to each creature and each planeswalker."

CR 702.33d: a spell with two kicker costs paid both has been kicked twice, so
X is how many were paid. The "choose" is made as the spell resolves (CR
608.2d) - these permanents are chosen, not targeted (CR 115.1), so a creature
with shroud or protection can still be chosen. "Those permanents" is the
chosen set (CR 608.2c: later text refers back to earlier text) and phasing out
(CR 702.26a) takes them out of the damage that follows, which only hits
permanents that are phased in (CR 702.26d).


Per-kick targets (Comet Storm, Strength of the Tajuru) - the same file, since
both are "choose, as many as the kicker allows":

Targets fixed by the number of times a spell was kicked (CR 601.2c, CR 702.33d).

Comet Storm ({X}{R}{R}, Multikicker {1}): "Choose any target, then choose
another target for each time this spell was kicked. Comet Storm deals X damage
to each of them." The kicker is paid while the spell is announced (CR 601.2b),
so by the time targets are chosen (CR 601.2c) the number of them is known: one,
plus one more per kick, each a different object ("another"). Each target takes
the full X as the spell resolves, and one that is no longer legal is simply not
affected (CR 608.2b).

Strength of the Tajuru ({X}{G}{G}, Multikicker {1}) is the same template over
"target creature": "Choose target creature, then choose another target creature
for each time this spell was kicked. Put X +1/+1 counters on each of them."
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

_LANDS = ["Mountain"] * 5 + ["Plains"] * 2 + ["Island"] * 2


def _board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Temporal Firestorm"],
            battlefield=_LANDS + ["Grizzly Bears", "Serra Angel", "Gideon of the Trials"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Wind Drake"])
    )


def _cast(scenario, *, kicks: list[str], phase_out: list, spend: list[str]):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Temporal Firestorm")
    for cost in kicks:
        casting.pay_kicker(which=cost)
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*spend))
    scenario.put_on_stack(casting)
    scenario.will_choose_cards(*phase_out, source="Temporal Firestorm")
    scenario.resolve_top()


def _survivors(scenario) -> set[str]:
    return {state.name for state in scenario.game.battlefield if state.card.name not in _BASICS}


_BASICS = {"Mountain", "Plains", "Island"}


def test_unkicked_it_is_a_plain_five_damage_sweep():
    scenario = _board().build()
    _cast(scenario, kicks=[], phase_out=[], spend=["Mountain"] * 5)
    assert _survivors(scenario) == set()


def test_kicked_once_one_permanent_phases_out_and_survives():
    scenario = _board().build()
    angel = scenario.creature("Serra Angel", "alice")
    _cast(
        scenario,
        kicks=["{1}{W}"],
        phase_out=[angel],
        spend=["Mountain"] * 5 + ["Plains"] * 2,
    )
    assert angel.phased_out
    assert angel.zone.name == "BATTLEFIELD"
    assert _survivors(scenario) == set()  # phased-out permanents are not on the board


def test_kicked_twice_two_permanents_phase_out_the_planeswalker_among_them():
    scenario = _board().build()
    angel = scenario.creature("Serra Angel", "alice")
    gideon = scenario.find("Gideon of the Trials", angel.zone, "alice")
    _cast(
        scenario,
        kicks=["{1}{W}", "{1}{U}"],
        phase_out=[angel, gideon],
        spend=_LANDS,
    )
    assert angel.phased_out and gideon.phased_out
    assert [s.name for s in scenario.game.battlefield if s.name == "Grizzly Bears"] == []


def test_the_choice_is_capped_at_the_number_of_kicks():
    """Kicked once: choosing two is refused by the decision machinery."""
    scenario = _board().build()
    angel = scenario.creature("Serra Angel", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    with pytest.raises(ValueError):
        _cast(
            scenario,
            kicks=["{1}{W}"],
            phase_out=[angel, bears],
            spend=["Mountain"] * 5 + ["Plains"] * 2,
        )


def test_unchosen_permanents_take_the_five_damage():
    scenario = _board().build()
    angel = scenario.creature("Serra Angel", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast(
        scenario,
        kicks=["{1}{W}"],
        phase_out=[angel],
        spend=["Mountain"] * 5 + ["Plains"] * 2,
    )
    assert bears.zone.name == "GRAVEYARD"
    assert angel.zone.name == "BATTLEFIELD"


def _storm_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Comet Storm"], battlefield=["Mountain"] * 8)
        .player("bob", battlefield=["Serra Angel", "Grizzly Bears", "Wind Drake"])
    )


def _announce_storm(scenario, *, x: int, kicks: int):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Comet Storm")
    casting.x_value = x
    if kicks:
        casting.pay_kicker(times=kicks)
    return casting


def _finish(scenario, casting, targets, lands: int):
    casting.choose_targets(targets)
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Mountain"] * lands))
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def test_unkicked_it_takes_exactly_one_target_and_deals_x():
    scenario = _storm_board().build()
    casting = _announce_storm(scenario, x=3, kicks=0)
    _finish(scenario, casting, ["bob"], lands=5)
    assert scenario.player("bob").life == 17


def test_kicked_twice_it_takes_three_different_targets_each_dealt_x():
    scenario = _storm_board().build()
    angel = scenario.creature("Serra Angel", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    casting = _announce_storm(scenario, x=4, kicks=2)
    _finish(scenario, casting, ["bob", angel, bears], lands=8)
    assert scenario.player("bob").life == 16
    assert angel.zone is Zone.GRAVEYARD  # 4 damage on a 4/4
    assert bears.zone is Zone.GRAVEYARD


def test_kicked_once_asking_for_one_target_too_few_is_refused():
    scenario = _storm_board().build()
    casting = _announce_storm(scenario, x=2, kicks=1)
    with pytest.raises(ValueError):
        casting.choose_targets(["bob"])


def test_kicked_once_asking_for_one_target_too_many_is_refused():
    scenario = _storm_board().build()
    angel = scenario.creature("Serra Angel", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    casting = _announce_storm(scenario, x=2, kicks=1)
    with pytest.raises(ValueError):
        casting.choose_targets(["bob", angel, bears])


def test_another_target_cannot_repeat_an_earlier_one():
    scenario = _storm_board().build()
    casting = _announce_storm(scenario, x=2, kicks=1)
    with pytest.raises(ValueError):
        casting.choose_targets(["bob", "bob"])


def test_a_target_that_left_before_resolution_is_skipped_and_the_rest_still_take_x():
    scenario = _storm_board().build()
    angel = scenario.creature("Serra Angel", "bob")
    drake = scenario.creature("Wind Drake", "bob")
    casting = _announce_storm(scenario, x=2, kicks=2)
    casting.choose_targets(["bob", angel, drake])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Mountain"] * 6))
    scenario.put_on_stack(casting)
    scenario.game.destroy(drake)
    scenario.resolve_top()
    assert scenario.player("bob").life == 18
    assert angel.damage == 2


def test_strength_of_the_tajuru_puts_x_counters_on_each_chosen_creature():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Strength of the Tajuru"],
            battlefield=["Forest"] * 5 + ["Grizzly Bears", "Serra Angel"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "alice")
    casting = scenario.cast("Strength of the Tajuru")
    casting.x_value = 2
    casting.pay_kicker(times=1)
    casting.choose_targets([bears, angel])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Forest"] * 5))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert bears.counter_count(Counter.PLUS_ONE) == 2
    assert angel.counter_count(Counter.PLUS_ONE) == 2
