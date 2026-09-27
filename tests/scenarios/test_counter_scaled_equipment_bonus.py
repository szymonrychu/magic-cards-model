"""An Equipment's bonus scaled by the counters on the Equipment itself.

Chainsaw: "Equipped creature gets +X/+0, where X is the number of rev counters
on this Equipment." with "Whenever one or more creatures die, put a rev
counter on this Equipment." feeding it. Opaline Bracers (Modern, in no deck
list) is the second printing: "Equipped creature gets +X/+X, where X is the
number of charge counters on this Equipment." - a different counter kind and a
toughness bonus too.

Rules, each read with `mise run rules:find` in the session that wrote this:

- **CR 613.4c** - the bonus is a sublayer 7c modification.
- **CR 611.3a** - a static ability's effect is not locked in: X is recounted
  every time the board is, so a counter added later grows the bonus at once.
- **CR 122.1** - counters are markers on the Equipment; only the named kind
  counts.
- **CR 301.5a** - "equipped creature" is whatever the Equipment is attached
  to; unattached, it pumps nothing, and moving it moves the bonus.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import Zone
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario, mana_from


def _board(equipment: str, *alice: str, bob=(), hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[equipment, "Grizzly Bears", *alice, *["Mountain"] * 6],
            hand=list(hand),
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _equip(scenario, equipment_name, target, mana: int):
    equipment = scenario.find(equipment_name, Zone.BATTLEFIELD, "alice")
    activation = equip_activation(scenario.game, equipment, target, "alice")
    payment = activation.begin_paying()
    for source in scenario.untapped_sources(*["Mountain"] * mana, username="alice"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    scenario.pass_until_resolved()
    return equipment


def _pt(scenario, state):
    return scenario.game.power_of(state), scenario.game.toughness_of(state)


def test_with_no_rev_counters_the_chainsaw_adds_nothing():
    scenario = _board("Chainsaw")
    bears = scenario.creature("Grizzly Bears", "alice")
    _equip(scenario, "Chainsaw", bears, 3)
    assert _pt(scenario, bears) == (2, 2)


def test_each_rev_counter_adds_one_power_and_no_toughness():
    scenario = _board("Chainsaw")
    bears = scenario.creature("Grizzly Bears", "alice")
    chainsaw = _equip(scenario, "Chainsaw", bears, 3)
    scenario.game.add_counters(chainsaw, "rev", 3)
    assert _pt(scenario, bears) == (5, 2)


def test_a_creature_dying_adds_a_rev_counter_and_the_bonus_grows_at_once():
    """CR 611.3a: the trigger's counter is counted on the next computation."""
    scenario = _board("Chainsaw", "Llanowar Elves", bob=["Mountain"], hand=[])
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    chainsaw = _equip(scenario, "Chainsaw", bears, 3)
    scenario.game.destroy(elves)
    scenario.state_based_actions()
    scenario.pass_until_resolved()
    assert chainsaw.counters["rev"] == 1
    assert _pt(scenario, bears) == (3, 2)


def test_other_counter_kinds_on_the_chainsaw_do_not_count():
    """CR 122.1: only rev counters."""
    scenario = _board("Chainsaw")
    bears = scenario.creature("Grizzly Bears", "alice")
    chainsaw = _equip(scenario, "Chainsaw", bears, 3)
    scenario.game.add_counters(chainsaw, "charge", 4)
    assert _pt(scenario, bears) == (2, 2)


def test_an_unattached_chainsaw_with_counters_pumps_nothing():
    scenario = _board("Chainsaw")
    bears = scenario.creature("Grizzly Bears", "alice")
    chainsaw = scenario.find("Chainsaw", Zone.BATTLEFIELD, "alice")
    scenario.game.add_counters(chainsaw, "rev", 2)
    assert _pt(scenario, bears) == (2, 2)


def test_moving_the_chainsaw_moves_the_bonus():
    """CR 301.5a."""
    scenario = _board("Chainsaw", "Serra Angel")
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "alice")
    chainsaw = _equip(scenario, "Chainsaw", bears, 3)
    scenario.game.add_counters(chainsaw, "rev", 2)
    _equip(scenario, "Chainsaw", angel, 3)
    assert _pt(scenario, bears) == (2, 2)
    assert _pt(scenario, angel) == (6, 4)


def test_chainsaw_classifies_as_handled():
    clauses = [c for c in classify_clauses(card("Chainsaw")) if c.text]
    assert {c.category for c in clauses} == {HANDLED}


# -- Opaline Bracers: charge counters, +X/+X ---------------------------------


def test_opaline_bracers_gives_plus_x_plus_x_for_its_charge_counters():
    scenario = _board("Opaline Bracers")
    bears = scenario.creature("Grizzly Bears", "alice")
    bracers = _equip(scenario, "Opaline Bracers", bears, 2)
    assert _pt(scenario, bears) == (2, 2)
    scenario.game.add_counters(bracers, "charge", 2)
    assert _pt(scenario, bears) == (4, 4)


def test_removing_a_charge_counter_shrinks_the_bonus():
    scenario = _board("Opaline Bracers")
    bears = scenario.creature("Grizzly Bears", "alice")
    bracers = _equip(scenario, "Opaline Bracers", bears, 2)
    scenario.game.add_counters(bracers, "charge", 3)
    bracers.remove_counters("charge", 1)
    assert _pt(scenario, bears) == (4, 4)


def test_opaline_bracers_classifies_as_handled():
    clauses = [c for c in classify_clauses(card("Opaline Bracers")) if c.text]
    assert {c.category for c in clauses} == {HANDLED}
