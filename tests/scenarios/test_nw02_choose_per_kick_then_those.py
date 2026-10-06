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
"""

from magic_cards_model.machines import Step
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
    import pytest

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
