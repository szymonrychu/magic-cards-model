"""Scenario: "Activate only if [condition]" restrictions that read this
turn's history or the source's own counters (CR 602.5b).

`Game.why_cannot_activate` refuses a restriction `condition_holds` cannot
read rather than letting it through unchecked - which left three cards'
abilities unusable in any game. Found by the behavioural sweep:

- "five or more creatures died this turn" (Lagomos, Hand of Hatred) - CR
  700.4's "dies", counted per turn by `Game.creatures_died_this_turn`;
- "you attacked with three or more creatures this turn" (Temple of
  Civilization; Minas Tirith, not in any deck, with two) - the attackers
  CR 508.1 declared this turn, `Game.attacked_this_turn`;
- "it has no time counters on it" (Temple of Cyclical Time) - the source's
  own counters (CR 122.1).

Rules verified with `mise run rules:find`: CR 602.5b, CR 700.4, CR 508.1,
CR 122.1.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _refusal(scenario, name: str, index: int) -> str | None:
    permanent = scenario.find(name, Zone.BATTLEFIELD, "alice")
    return scenario.game.why_cannot_activate(permanent, index, "alice")


# -- creatures died this turn -------------------------------------------------


def _lagomos_after(deaths: int):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Lagomos, Hand of Hatred"] + ["Grizzly Bears"] * deaths,
            library=["Forest", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for bears in [s for s in scenario.game.battlefield if s.name == "Grizzly Bears"]:
        scenario.game.destroy(bears)
    return scenario


def test_lagomos_searches_once_five_creatures_died_this_turn():
    scenario = _lagomos_after(5)
    assert scenario.game.creatures_died_this_turn == 5
    assert _refusal(scenario, "Lagomos, Hand of Hatred", 0) is None

    lagomos = scenario.find("Lagomos, Hand of Hatred", Zone.BATTLEFIELD, "alice")
    scenario.activate(lagomos)
    scenario.resolve_top()

    assert len(scenario.player("alice").hand) == 1


def test_lagomos_is_refused_after_only_four_deaths():
    scenario = _lagomos_after(4)
    refusal = _refusal(scenario, "Lagomos, Hand of Hatred", 0)
    assert refusal is not None and "not met" in refusal


# -- attacked with N or more creatures this turn ------------------------------


def _attacked_with(card: str, attackers: int):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[card, "Plains", "Plains"] + ["Grizzly Bears"] * attackers,
            library=["Forest"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = [s for s in scenario.game.battlefield if s.name == "Grizzly Bears"]
    scenario.attack_with(*bears)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.turn.advance_to(Step.POSTCOMBAT_MAIN)
    scenario.game.sync_priority_with_step()
    return scenario


@pytest.mark.parametrize(("card", "needed"), [("Minas Tirith", 2)])
def test_a_land_draws_once_enough_creatures_attacked(card, needed):
    scenario = _attacked_with(card, needed)
    assert _refusal(scenario, card, 1) is None

    hand = len(scenario.player("alice").hand)
    tirith = scenario.find(card, Zone.BATTLEFIELD, "alice")
    scenario.activate(tirith, *scenario.untapped_sources("Plains", "Plains"), index=1)
    scenario.resolve_top()
    assert len(scenario.player("alice").hand) == hand + 1


def test_one_attacker_short_is_refused():
    scenario = _attacked_with("Minas Tirith", 1)
    refusal = _refusal(scenario, "Minas Tirith", 1)
    assert refusal is not None and "not met" in refusal


def test_temple_of_civilization_reads_three_attackers():
    scenario = _attacked_with("Ojer Taq, Deepest Foundation // Temple of Civilization", 3)
    temple = scenario.find("Ojer Taq, Deepest Foundation", Zone.BATTLEFIELD, "alice")
    temple.transformed = True
    assert scenario.game.why_cannot_activate(temple, 1, "alice") is None


# -- no counters of a kind on the source --------------------------------------


def _temple_with_time_counters(count: int):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ojer Pakpatiq, Deepest Epoch // Temple of Cyclical Time"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    temple = scenario.game.battlefield[0]
    temple.transformed = True
    if count:
        scenario.game.add_counters(temple, "time", count)
    return scenario, temple


def test_temple_of_cyclical_time_transforms_with_no_time_counters():
    scenario, temple = _temple_with_time_counters(0)
    assert scenario.game.why_cannot_activate(temple, 1, "alice") is None


def test_temple_of_cyclical_time_is_refused_with_a_time_counter_left():
    scenario, temple = _temple_with_time_counters(1)
    refusal = scenario.game.why_cannot_activate(temple, 1, "alice")
    assert refusal is not None and "not met" in refusal
