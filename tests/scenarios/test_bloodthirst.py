"""Bloodthirst: a creature that arrives bigger once an opponent has been hurt
this turn (CR 702.54).

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 702.54a** - "Bloodthirst is a static ability. 'Bloodthirst N' means 'If
  an opponent was dealt damage this turn, this permanent enters with N +1/+1
  counters on it.'"
- **CR 614.1c** - "[This permanent] enters with ..." is a replacement effect,
  so the counters are on it as it arrives, however it arrives.
- **CR 120.3a** - damage dealt to a player causes that player to lose life;
  life lost some other way (CR 119.3) is not damage dealt.

The condition is the H4 turn-history clause "an opponent was dealt damage
this turn" (`machines/conditions/history.py`), read for the entering
permanent's controller. Skarrgan Firebird is the printing that brought the
keyword into the pool; Gorehorn Minotaurs (Bloodthirst 2) is a second printing
in no deck, the proof the keyword's N is read rather than the card.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(hand: str):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[hand], battlefield=["Mountain"] * 6, library=["Mountain"] * 6)
        .player("bob", library=["Plains"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario, name: str, lands: int):
    scenario.cast_and_resolve(name, *scenario.untapped_sources(*["Mountain"] * lands))
    return scenario.find(name, Zone.BATTLEFIELD, "alice")


def test_firebird_enters_with_three_counters_after_an_opponent_was_dealt_damage():
    scenario = _board("Skarrgan Firebird")
    scenario.game.deal_damage(scenario.player("bob"), 1)
    firebird = _cast(scenario, "Skarrgan Firebird", 6)
    assert firebird.counter_count("+1/+1") == 3


def test_firebird_enters_with_nothing_on_a_turn_without_damage():
    scenario = _board("Skarrgan Firebird")
    firebird = _cast(scenario, "Skarrgan Firebird", 6)
    assert firebird.counter_count("+1/+1") == 0


def test_life_lost_without_damage_is_not_bloodthirst():
    """CR 702.54a says "dealt damage": life lost to an effect is not."""
    scenario = _board("Skarrgan Firebird")
    scenario.game.lose_life("bob", 3)
    firebird = _cast(scenario, "Skarrgan Firebird", 6)
    assert firebird.counter_count("+1/+1") == 0


def test_damage_to_its_own_controller_is_not_an_opponent():
    scenario = _board("Skarrgan Firebird")
    scenario.game.deal_damage(scenario.player("alice"), 2)
    firebird = _cast(scenario, "Skarrgan Firebird", 6)
    assert firebird.counter_count("+1/+1") == 0


def test_a_second_printing_reads_its_own_n():
    """Gorehorn Minotaurs: "Bloodthirst 2"."""
    scenario = _board("Gorehorn Minotaurs")
    scenario.game.deal_damage(scenario.player("bob"), 1)
    minotaurs = _cast(scenario, "Gorehorn Minotaurs", 4)
    assert minotaurs.counter_count("+1/+1") == 2


def test_it_applies_to_a_permanent_put_onto_the_battlefield_too():
    """CR 614.1c: the replacement modifies the entering itself, cast or not."""
    scenario = _board("Gorehorn Minotaurs")
    scenario.game.deal_damage(scenario.player("bob"), 1)
    scenario.put_onto_battlefield("Gorehorn Minotaurs", "alice")
    minotaurs = scenario.find("Gorehorn Minotaurs", Zone.BATTLEFIELD, "alice")
    assert minotaurs.counter_count("+1/+1") == 2
