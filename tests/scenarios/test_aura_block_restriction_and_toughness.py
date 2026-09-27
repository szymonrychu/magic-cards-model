"""An attachment that pumps and caps blockers in one sentence.

Meltstrider's Resolve: "Enchanted creature gets +0/+2 and can't be blocked by
more than one creature." Wolfrider's Saddle (Pioneer/Modern, in no deck list)
prints the same sentence on an Equipment ("Equipped creature gets +1/+1 and
can't be blocked by more than one creature."), and Rope (Standard) the
comma-list form ("Equipped creature gets +1/+2, has reach, and can't be
blocked by more than one creature.").

Rules, each read with `mise run rules:find` in the session that wrote this:

- **CR 613.4c** - the pump is a sublayer 7c modification.
- **CR 613.1f** - the blocker cap is an ability the attached creature has,
  added in layer 6, so it goes when the attachment does.
- **CR 509.1b** - a restriction on blocking: a declaration that puts two
  creatures on the capped attacker is illegal; one is fine.
- **CR 303.4b / 301.5a** - "enchanted"/"equipped" creature is the object the
  Aura or Equipment is attached to.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import Zone
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario, mana_from


def _board(alice_battlefield, alice_hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Grizzly Bears", *alice_battlefield],
            hand=list(alice_hand),
            library=["Island"] * 5,
        )
        .player("bob", battlefield=["Watchwolf", "Hill Giant"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _enchant_bears(scenario):
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_onto_stack(
        "Meltstrider's Resolve",
        *scenario.untapped_sources("Forest", username="alice"),
        targets=[bears],
    )
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()
    return bears


def _to_attack(scenario, attacker):
    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers
    scenario.attack_with(attacker)
    scenario.advance()  # declare blockers


def test_the_enchanted_creature_gets_plus_zero_plus_two():
    scenario = _board(["Forest"], ["Meltstrider's Resolve"])
    bears = _enchant_bears(scenario)
    assert (scenario.game.power_of(bears), scenario.game.toughness_of(bears)) == (2, 4)


def test_two_blockers_on_the_enchanted_creature_are_illegal():
    """CR 509.1b."""
    scenario = _board(["Forest"], ["Meltstrider's Resolve"])
    bears = _enchant_bears(scenario)
    _to_attack(scenario, bears)
    wolf = scenario.creature("Watchwolf", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    with pytest.raises(ValueError, match="can't be blocked by more than one creature"):
        scenario.block(bears, wolf, giant)
    assert scenario.blockers() == []


def test_one_blocker_on_the_enchanted_creature_is_legal():
    scenario = _board(["Forest"], ["Meltstrider's Resolve"])
    bears = _enchant_bears(scenario)
    _to_attack(scenario, bears)
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.block(bears, wolf)
    assert scenario.blockers() == [wolf]


def test_an_unenchanted_creature_can_be_double_blocked():
    scenario = _board(["Forest", "Llanowar Elves"], ["Meltstrider's Resolve"])
    _enchant_bears(scenario)
    elves = scenario.creature("Llanowar Elves", "alice")
    _to_attack(scenario, elves)
    wolf = scenario.creature("Watchwolf", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.block(elves, wolf, giant)
    assert scenario.blockers() == [wolf, giant]


def test_once_the_aura_is_gone_the_cap_and_the_pump_go_with_it():
    """CR 613.1f: the granted restriction exists only while attached."""
    scenario = _board(["Forest"], ["Meltstrider's Resolve"])
    bears = _enchant_bears(scenario)
    aura = scenario.find("Meltstrider's Resolve", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(aura)
    assert (scenario.game.power_of(bears), scenario.game.toughness_of(bears)) == (2, 2)
    _to_attack(scenario, bears)
    wolf = scenario.creature("Watchwolf", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.block(bears, wolf, giant)
    assert scenario.blockers() == [wolf, giant]


def test_meltstriders_resolve_classifies_as_handled():
    for name in ("Meltstrider's Resolve", "Wolfrider's Saddle", "Rope"):
        clauses = [c for c in classify_clauses(card(name)) if c.text]
        assert {c.category for c in clauses} == {HANDLED}, name


# -- the Equipment printings of the same sentence ------------------------------


def _equip(scenario, name, target, mana: int):
    equipment = scenario.find(name, Zone.BATTLEFIELD, "alice")
    activation = equip_activation(scenario.game, equipment, target, "alice")
    payment = activation.begin_paying()
    for source in scenario.untapped_sources(*["Forest"] * mana, username="alice"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    scenario.pass_until_resolved()


def test_wolfriders_saddle_pumps_and_caps_blockers():
    scenario = _board(["Wolfrider's Saddle", *["Forest"] * 3])
    bears = scenario.creature("Grizzly Bears", "alice")
    _equip(scenario, "Wolfrider's Saddle", bears, 3)
    assert (scenario.game.power_of(bears), scenario.game.toughness_of(bears)) == (3, 3)
    _to_attack(scenario, bears)
    wolf = scenario.creature("Watchwolf", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    with pytest.raises(ValueError, match="can't be blocked by more than one creature"):
        scenario.block(bears, wolf, giant)


def test_rope_pumps_grants_reach_and_caps_blockers():
    scenario = _board(["Rope", *["Forest"] * 3])
    bears = scenario.creature("Grizzly Bears", "alice")
    _equip(scenario, "Rope", bears, 3)
    computed = scenario.game.computed_board().of(bears)
    assert (computed.power, computed.toughness) == (3, 4)
    assert computed.has_ability("Reach")
    _to_attack(scenario, bears)
    wolf = scenario.creature("Watchwolf", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    with pytest.raises(ValueError, match="can't be blocked by more than one creature"):
        scenario.block(bears, wolf, giant)
