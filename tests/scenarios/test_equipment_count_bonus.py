"""An Equipment's pump counted off its controller's board - Improvised
Arsenal: "Equipped creature gets +1/+0 for each artifact you control."

- Sublayer 7c (CR 613.4c): the bonus modifies, never sets.
- CR 611.3a / CR 613.5: a static ability's effect is recomputed every time
  the board is - an artifact entering or leaving changes the bonus at once.
- CR 109.5: "you" is the Equipment's controller, so only that player's
  artifacts count, the Equipment itself among them (it is an artifact).
- CR 301.5a: "equipped creature" is whatever the Equipment is attached to;
  an unattached Equipment pumps nothing, and moving it moves the bonus.

Off-set proof (legal in Modern, in no deck list): Cranial Plating -
"Equipped creature gets +1/+0 for each artifact you control." - the only
other in-format printing of the template, on a different cost and equip
shape (a second, "{B}{B}: Attach" ability beside Equip {1}).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from

ARSENAL = "Improvised Arsenal"


def _equip(scenario, equipment, target, *mana_sources, username="alice"):
    activation = equip_activation(scenario.game, equipment, target, username)
    payment = activation.begin_paying()
    for source in mana_sources:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    scenario.pass_until_resolved()


def _pt(scenario, state):
    return scenario.game.power_of(state), scenario.game.toughness_of(state)


def _board(*alice, bob=(), hand=()):
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=list(alice), hand=list(hand), library=["Island"] * 5)
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )


def test_arsenal_counts_every_artifact_its_controller_controls():
    """Arsenal + Sol Ring + Mind Stone: three artifacts, +3/+0."""
    scenario = _board(ARSENAL, "Grizzly Bears", "Sol Ring", "Mind Stone", "Mountain")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    arsenal = scenario.find(ARSENAL, Zone.BATTLEFIELD, "alice")

    _equip(scenario, arsenal, bears, *scenario.untapped_sources("Mountain", username="alice"))

    assert _pt(scenario, bears) == (5, 2)


def test_an_unattached_arsenal_pumps_nothing():
    scenario = _board(ARSENAL, "Grizzly Bears", "Sol Ring")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    assert _pt(scenario, bears) == (2, 2)


def test_the_count_follows_an_artifact_entering():
    """CR 613.5: recounted the moment the board is next computed."""
    scenario = _board(ARSENAL, "Grizzly Bears", "Mountain", hand=["Sol Ring"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    arsenal = scenario.find(ARSENAL, Zone.BATTLEFIELD, "alice")
    _equip(scenario, arsenal, bears, *scenario.untapped_sources("Mountain", username="alice"))
    assert _pt(scenario, bears) == (3, 2)

    scenario.put_onto_battlefield("Sol Ring", "alice")

    assert _pt(scenario, bears) == (4, 2)


def test_the_count_follows_an_artifact_leaving():
    scenario = _board(ARSENAL, "Grizzly Bears", "Sol Ring", "Mountain")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    arsenal = scenario.find(ARSENAL, Zone.BATTLEFIELD, "alice")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    _equip(scenario, arsenal, bears, *scenario.untapped_sources("Mountain", username="alice"))

    scenario.game.destroy(ring)

    assert _pt(scenario, bears) == (3, 2)


def test_opponents_artifacts_do_not_count():
    """CR 109.5: "you" is the Equipment's controller."""
    scenario = _board(ARSENAL, "Grizzly Bears", "Mountain", bob=["Sol Ring", "Mind Stone"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    arsenal = scenario.find(ARSENAL, Zone.BATTLEFIELD, "alice")

    _equip(scenario, arsenal, bears, *scenario.untapped_sources("Mountain", username="alice"))

    assert _pt(scenario, bears) == (3, 2)


def test_an_artifact_creature_counts_itself():
    """Ornithopter is an artifact alice controls: Arsenal + Ornithopter."""
    scenario = _board(ARSENAL, "Ornithopter", "Mountain")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thopter = scenario.creature("Ornithopter", "alice")
    arsenal = scenario.find(ARSENAL, Zone.BATTLEFIELD, "alice")

    _equip(scenario, arsenal, thopter, *scenario.untapped_sources("Mountain", username="alice"))

    assert _pt(scenario, thopter) == (2, 2)


def test_moving_the_equipment_moves_the_bonus():
    scenario = _board(ARSENAL, "Grizzly Bears", "Hill Giant", "Sol Ring", "Mountain", "Mountain")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    arsenal = scenario.find(ARSENAL, Zone.BATTLEFIELD, "alice")
    first, second = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    _equip(scenario, arsenal, bears, first)

    _equip(scenario, arsenal, giant, second)

    assert _pt(scenario, bears) == (2, 2)
    assert _pt(scenario, giant) == (5, 3)


def test_the_bonus_stacks_on_counters_in_the_same_sublayer():
    scenario = _board(ARSENAL, "Grizzly Bears", "Mountain")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    arsenal = scenario.find(ARSENAL, Zone.BATTLEFIELD, "alice")
    _equip(scenario, arsenal, bears, *scenario.untapped_sources("Mountain", username="alice"))

    bears.add_counters("+1/+1", 1)

    assert _pt(scenario, bears) == (4, 3)


# -- Cranial Plating ----------------------------------------------------------


def test_cranial_plating_counts_artifacts_the_same_way():
    scenario = _board("Cranial Plating", "Grizzly Bears", "Sol Ring", "Mind Stone", "Swamp")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    plating = scenario.find("Cranial Plating", Zone.BATTLEFIELD, "alice")

    _equip(scenario, plating, bears, *scenario.untapped_sources("Swamp", username="alice"))

    assert _pt(scenario, bears) == (5, 2)
