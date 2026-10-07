"""Reconfigure (CR 702.151): an Equipment creature that attaches itself and
stops being a creature while attached.

Read whole with `mise run rules:find` in the session that wrote this file:

- **CR 702.151a** - "Reconfigure represents two activated abilities.
  Reconfigure [cost] means '[Cost]: Attach this permanent to another target
  creature you control. Activate only as a sorcery' and '[Cost]: Unattach
  this permanent. Activate only if this permanent is attached to a creature
  and only as a sorcery.'"
- **CR 702.151b** - "Attaching an Equipment with reconfigure to another
  creature causes the Equipment to stop being a creature until it becomes
  unattached from that creature."
- **CR 301.5c** - "An Equipment that's also a creature can't equip a creature
  unless that Equipment has reconfigure ... An Equipment can't equip itself.
  An Equipment that equips an illegal or nonexistent permanent becomes
  unattached from that permanent but remains on the battlefield."
- **CR 704.5n** - the state-based action that unattaches it.
- **CR 613.1d** - type-changing effects are layer 4.

Proved on Simian Sling (the listed card), Lizard Blades and Bronzeplate Boar
- Modern/Pioneer-legal printings in no deck list, with a different
  reconfigure cost ({2} and {5}) and a different equipped bonus each.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.keywords import executes
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.machines.reconfigure import (
    reconfigure_attach_activation,
    reconfigure_unattach_activation,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind, Affordability
from magic_cards_model.models.card import Type
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario, mana_from


def board(equipment: str, lands: int = 2, *more: str) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Plains"] * 3,
            battlefield=[equipment, "Grizzly Bears", *more, *(["Mountain"] * lands)],
        )
        .player("bob", library=["Plains"] * 3, battlefield=["Llanowar Elves"])
    )


def _pay(scenario, activation, lands: int):
    payment = activation.begin_paying()
    for source in scenario.untapped_sources(*(["Mountain"] * lands)):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    activation.resolve()
    scenario.state_based_actions()
    return activation


def attach(scenario, equipment, target, lands: int = 2):
    activation = reconfigure_attach_activation(scenario.game, equipment, target, "alice")
    return _pay(scenario, activation, lands)


def unattach(scenario, equipment, lands: int = 2):
    activation = reconfigure_unattach_activation(scenario.game, equipment, "alice")
    return _pay(scenario, activation, lands)


def is_creature(scenario, permanent) -> bool:
    return scenario.game.characteristics_of(permanent).is_creature


def pt(scenario, permanent) -> tuple[int, int]:
    chars = scenario.game.characteristics_of(permanent)
    return chars.power, chars.toughness


def setup(equipment: str, lands: int = 2, *more: str):
    scenario = board(equipment, lands, *more).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature(equipment, "alice"), scenario.creature("Grizzly Bears")


# --------------------------------------------------------------------------
# Attach (CR 702.151a's first ability) and not-a-creature (CR 702.151b)
# --------------------------------------------------------------------------


def test_reconfigure_attaches_to_another_creature_you_control():
    scenario, blades, bears = setup("Lizard Blades")

    attach(scenario, blades, bears)

    assert blades.attached_to == bears.id


def test_attached_it_is_not_a_creature_but_still_an_equipment_artifact():
    scenario, blades, bears = setup("Lizard Blades")

    attach(scenario, blades, bears)

    types = scenario.game.characteristics_of(blades).types
    assert Type.CREATURE not in types
    assert Type.ARTIFACT in types
    assert "Equipment" in scenario.game.characteristics_of(blades).subtypes


def test_attached_it_stays_attached_through_state_based_actions():
    """CR 301.5c lets an Equipment with reconfigure equip, and attached it is
    no creature anyway - so CR 704.5n finds nothing to unattach."""
    scenario, blades, bears = setup("Lizard Blades")

    attach(scenario, blades, bears)
    scenario.state_based_actions()

    assert blades.attached_to == bears.id


def test_the_equipped_creature_gets_the_equipment_bonus():
    scenario, blades, bears = setup("Lizard Blades")
    assert not has_keyword(bears, Keyword.DOUBLE_STRIKE, scenario.game)

    attach(scenario, blades, bears)

    assert has_keyword(bears, Keyword.DOUBLE_STRIKE, scenario.game)


def test_bronzeplate_boar_attached_gives_plus_three_plus_two_and_trample():
    scenario, boar, bears = setup("Bronzeplate Boar", 5)

    attach(scenario, boar, bears, 5)

    assert pt(scenario, bears) == (5, 4)
    assert has_keyword(bears, Keyword.TRAMPLE, scenario.game)
    assert not is_creature(scenario, boar)


def test_simian_sling_attached_gives_plus_one_plus_one():
    scenario, sling, bears = setup("Simian Sling")

    attach(scenario, sling, bears)

    assert pt(scenario, bears) == (3, 3)
    assert not is_creature(scenario, sling)


def test_unattached_it_is_a_creature_with_its_own_keyword():
    scenario, blades, _bears = setup("Lizard Blades")

    assert is_creature(scenario, blades)
    assert pt(scenario, blades) == (1, 1)
    assert has_keyword(blades, Keyword.DOUBLE_STRIKE, scenario.game)


def test_attached_it_cannot_attack():
    scenario, blades, bears = setup("Lizard Blades")
    attach(scenario, blades, bears)
    blades.summoning_sick = False
    bears.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)

    assert not scenario.can_attack(blades)
    assert scenario.can_attack(bears)


def test_it_cannot_attach_to_itself():
    scenario, blades, _bears = setup("Lizard Blades")
    with pytest.raises(ValueError, match="another"):
        reconfigure_attach_activation(scenario.game, blades, blades, "alice")


def test_it_cannot_attach_to_an_opponents_creature():
    scenario, blades, _bears = setup("Lizard Blades")
    elves = scenario.creature("Llanowar Elves", "bob")
    with pytest.raises(ValueError):
        reconfigure_attach_activation(scenario.game, blades, elves, "alice")


def test_it_cannot_attach_to_a_noncreature():
    scenario, blades, _bears = setup("Lizard Blades")
    (mountain, *_rest) = scenario.untapped_sources("Mountain", "Mountain")
    with pytest.raises(ValueError):
        reconfigure_attach_activation(scenario.game, blades, mountain, "alice")


def test_attach_only_as_a_sorcery():
    scenario, blades, bears = setup("Lizard Blades")
    scenario.start_at(Step.DECLARE_ATTACKERS)

    activation = reconfigure_attach_activation(scenario.game, blades, bears, "alice")

    assert "only be activated as a sorcery" in (activation.why_not() or "")


def test_the_attach_costs_the_printed_reconfigure_cost():
    scenario, boar, bears = setup("Bronzeplate Boar", 5)

    activation = reconfigure_attach_activation(scenario.game, boar, bears, "alice")

    assert str(activation.cost.mana) == "{5}"
    assert activation.rule == "CR 702.151a"


def test_a_target_that_left_before_resolution_leaves_it_unattached():
    """CR 608.2b: the target is illegal on resolution, so nothing moves."""
    scenario, blades, bears = setup("Lizard Blades")
    activation = reconfigure_attach_activation(scenario.game, blades, bears, "alice")
    payment = activation.begin_paying()
    for source in scenario.untapped_sources("Mountain", "Mountain"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    scenario.game.destroy(bears)
    activation.resolve()

    assert blades.attached_to is None
    assert is_creature(scenario, blades)


def test_reattaching_moves_it_to_the_new_creature():
    scenario, blades, bears = setup("Lizard Blades", 4, "Llanowar Elves")
    elves = scenario.creature("Llanowar Elves", "alice")
    attach(scenario, blades, bears)

    attach(scenario, blades, elves)

    assert blades.attached_to == elves.id
    assert has_keyword(elves, Keyword.DOUBLE_STRIKE, scenario.game)
    assert not has_keyword(bears, Keyword.DOUBLE_STRIKE, scenario.game)
    assert not is_creature(scenario, blades)


# --------------------------------------------------------------------------
# Unattach (CR 702.151a's second ability) and leaving the host
# --------------------------------------------------------------------------


def test_unattach_makes_it_a_creature_again():
    scenario, blades, bears = setup("Lizard Blades", 4)
    attach(scenario, blades, bears)

    unattach(scenario, blades)

    assert blades.attached_to is None
    assert is_creature(scenario, blades)
    assert not has_keyword(bears, Keyword.DOUBLE_STRIKE, scenario.game)


def test_unattach_only_while_attached():
    scenario, blades, _bears = setup("Lizard Blades")

    activation = reconfigure_unattach_activation(scenario.game, blades, "alice")

    assert "attached to a creature" in (activation.why_not() or "")


def test_unattach_only_as_a_sorcery():
    scenario, blades, bears = setup("Lizard Blades", 4)
    attach(scenario, blades, bears)
    scenario.start_at(Step.DECLARE_ATTACKERS)

    activation = reconfigure_unattach_activation(scenario.game, blades, "alice")

    assert "only be activated as a sorcery" in (activation.why_not() or "")


def test_when_the_equipped_creature_dies_it_falls_off_and_is_a_creature_again():
    """CR 704.5n unattaches it; CR 702.151b's "until it becomes unattached"
    then ends."""
    scenario, blades, bears = setup("Lizard Blades")
    attach(scenario, blades, bears)

    scenario.game.destroy(bears)
    scenario.state_based_actions()

    assert blades.zone is Zone.BATTLEFIELD
    assert blades.attached_to is None
    assert is_creature(scenario, blades)


# --------------------------------------------------------------------------
# Support audit
# --------------------------------------------------------------------------


def test_reconfigure_is_an_executed_keyword():
    assert executes("Reconfigure")


@pytest.mark.parametrize("name", ["Simian Sling", "Lizard Blades", "Bronzeplate Boar"])
def test_the_reconfigure_keyword_clause_reads_handled(name):
    (clause,) = [
        c
        for c in card_support(card(name)).clauses
        if c.kind == "keyword" and c.text == "Reconfigure"
    ]
    assert clause.outcome == "handled"


@pytest.mark.parametrize("name", ["Lizard Blades", "Bronzeplate Boar"])
def test_the_proof_reconfigure_printings_read_handled_on_every_clause(name):
    support = card_support(card(name))
    assert support.status == "handled", [
        (c.text, c.outcome) for c in support.clauses if c.outcome != "handled"
    ]


# --------------------------------------------------------------------------
# Simian Sling's "this creature or equipped creature becomes blocked"
# --------------------------------------------------------------------------


def _sling_triggers(scenario) -> list:
    scenario.game.put_triggers_on_stack()
    return [
        item
        for item in [*scenario.pending_triggers, *scenario.game.stack]
        if getattr(item, "source_name", None) == "Simian Sling"
    ]


def test_simian_slings_trigger_fires_when_the_sling_itself_becomes_blocked():
    scenario, sling, _bears = setup("Simian Sling")
    sling.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(sling)
    scenario.game.put_triggers_on_stack()

    scenario.block(sling, scenario.creature("Llanowar Elves", "bob"))

    (trigger,) = _sling_triggers(scenario)
    assert trigger.source_id == sling.id


def test_simian_slings_trigger_fires_when_the_equipped_creature_becomes_blocked():
    """Attached, the Sling is no creature and is not in combat - the trigger
    is its own (its source is the Sling, CR 113.7) off the equipped
    creature's block (CR 301.5a's "equipped creature")."""
    scenario, sling, bears = setup("Simian Sling")
    attach(scenario, sling, bears)
    bears.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.game.put_triggers_on_stack()

    scenario.block(bears, scenario.creature("Llanowar Elves", "bob"))

    (trigger,) = _sling_triggers(scenario)
    assert trigger.source_id == sling.id


def test_simian_slings_trigger_ignores_an_unequipped_creatures_block():
    scenario, sling, bears = setup("Simian Sling")
    bears.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.game.put_triggers_on_stack()

    scenario.block(bears, scenario.creature("Llanowar Elves", "bob"))

    assert _sling_triggers(scenario) == []


# --------------------------------------------------------------------------
# legal_actions offers both reconfigure abilities (CR 702.151a), so a seat
# can take them: the attach row carries its target slot, the unattach row
# none (the shape `_reconfigure_effect` resolves by).
# --------------------------------------------------------------------------


def reconfigure_rows(scenario, username: str, permanent):
    return [
        action
        for action in legal_actions(scenario.game, username)
        if action.kind is ActionKind.ACTIVATE
        and action.card_id == permanent.id
        and action.keyword == "Reconfigure"
    ]


def test_legal_actions_offers_the_attach_with_another_creature_you_control_slot():
    scenario, blades, bears = setup("Lizard Blades")

    (row,) = reconfigure_rows(scenario, "alice", blades)

    assert row.rule == "CR 702.151a"
    assert row.ability_index is None
    assert row.mana_cost == "{2}"
    assert row.affordable is Affordability.YES
    (slot,) = row.target_slots
    assert (slot.minimum, slot.maximum) == (1, 1)
    assert bears.id in slot.candidates
    assert blades.id not in slot.candidates, "another target creature (CR 702.151a)"
    elves = scenario.creature("Llanowar Elves", "bob")
    assert elves.id not in slot.candidates, "a creature you control (CR 702.151a)"


def test_legal_actions_offers_the_unattach_only_while_attached():
    scenario, blades, bears = setup("Lizard Blades", 4)
    attach(scenario, blades, bears)

    rows = reconfigure_rows(scenario, "alice", blades)

    unattach_rows = [row for row in rows if not row.target_slots]
    attach_rows = [row for row in rows if row.target_slots]
    assert len(unattach_rows) == 1
    assert unattach_rows[0].rule == "CR 702.151a"
    assert unattach_rows[0].mana_cost == "{2}"
    assert unattach_rows[0].affordable is Affordability.YES
    assert len(attach_rows) == 1


def test_legal_actions_omits_reconfigure_outside_the_sorcery_window():
    scenario, blades, bears = setup("Lizard Blades", 4)
    attach(scenario, blades, bears)
    scenario.start_at(Step.DECLARE_ATTACKERS)

    assert reconfigure_rows(scenario, "alice", blades) == []


def test_legal_actions_never_offers_an_opponent_your_reconfigure():
    scenario, blades, _bears = setup("Lizard Blades")

    assert reconfigure_rows(scenario, "bob", blades) == []


def test_the_offered_attach_row_resolves_through_the_attach_activation():
    """The row's own candidate, handed back to `reconfigure_attach_
    activation`, attaches it: what the seat sees is what the engine takes."""
    scenario, blades, bears = setup("Lizard Blades")
    (row,) = reconfigure_rows(scenario, "alice", blades)
    (target_id,) = row.target_slots[0].candidates

    attach(scenario, blades, scenario.game.find_by_id(target_id))

    assert blades.attached_to == bears.id
