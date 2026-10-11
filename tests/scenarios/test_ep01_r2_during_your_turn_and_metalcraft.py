"""Scenario: conditional statics gated on whose turn it is, metalcraft, or a
spell's own cast-time condition (EP-01 round 2, task 3).

Snowmelt Stag ("During your turn, this creature has base power and toughness
5/2.") and Circle of the Moon Druid ("Bear Form - During your turn, this
creature is a Bear with base power and toughness 4/2.") for the turn gate;
Rusted Relic ("Metalcraft - This artifact is a 5/5 Golem artifact creature as
long as you control three or more artifacts.") and Puresteel Paladin
("Metalcraft - Equipment you control have equip {0} ...") with Ardent Recruit
for the artifact count; Supernatural Rescue ("This spell has flash as long as
you control a Spirit.") for a spell's own timing.

Verified with `mise run rules:find`: CR 611.3a (a static ability's effect is
not locked in), CR 604.2, CR 613.1d (type change), CR 613.4b (base P/T),
CR 207.2c (an ability word has no rules meaning), CR 702.6a (equip).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(alice, bob=(), *, hand=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=list(alice), hand=list(hand), library=["Island"] * 5)
        .player("bob", battlefield=list(bob), library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _next_turn(scenario) -> None:
    """Run this turn out and begin the next player's upkeep."""
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.advance()


def _chars(scenario, name, username="alice"):
    return scenario.game.characteristics_of(scenario.find(name, Zone.BATTLEFIELD, username))


def _notices(scenario):
    return list(scenario.game.continuous_effects.layer_notices)


def _types(scenario, name, username="alice"):
    return {t.value for t in _chars(scenario, name, username).types}


def _has(chars, text):
    return any(line.lower() == text.lower() for line in chars.abilities)


# -- Snowmelt Stag: base P/T during your turn ----------------------------------


def test_snowmelt_stag_has_base_5_2_on_its_controllers_turn():
    scenario = _board(["Snowmelt Stag"])
    chars = _chars(scenario, "Snowmelt Stag")
    assert chars.power_toughness == (5, 2)
    assert _notices(scenario) == []


def test_snowmelt_stag_flips_back_when_the_turn_passes_to_the_opponent():
    scenario = _board(["Snowmelt Stag"])
    assert _chars(scenario, "Snowmelt Stag").power_toughness == (5, 2)
    _next_turn(scenario)
    assert scenario.game.active_player.username == "bob"
    assert _chars(scenario, "Snowmelt Stag").power_toughness == (2, 5)


def test_snowmelt_stag_keeps_the_vigilance_it_prints_in_both_turns():
    scenario = _board(["Snowmelt Stag"])
    assert _has(_chars(scenario, "Snowmelt Stag"), "Vigilance")
    _next_turn(scenario)
    assert _has(_chars(scenario, "Snowmelt Stag"), "Vigilance")


def test_an_opponents_snowmelt_stag_is_not_5_2_on_my_turn():
    scenario = _board(["Grizzly Bears"], ["Snowmelt Stag"])
    assert _chars(scenario, "Snowmelt Stag", "bob").power_toughness == (2, 5)


def test_snowmelt_stag_counters_still_apply_on_top_of_the_base():
    scenario = _board(["Snowmelt Stag"])
    scenario.find("Snowmelt Stag", Zone.BATTLEFIELD, "alice").add_counters("+1/+1")
    assert _chars(scenario, "Snowmelt Stag").power_toughness == (6, 3)


# -- Circle of the Moon Druid: becomes a Bear during your turn -------------------


def test_circle_of_the_moon_druid_is_a_4_2_bear_on_its_controllers_turn():
    scenario = _board(["Circle of the Moon Druid"])
    chars = _chars(scenario, "Circle of the Moon Druid")
    assert chars.power_toughness == (4, 2)
    assert set(chars.subtypes) == {"Bear"}
    assert _notices(scenario) == []


def test_circle_of_the_moon_druid_is_a_human_elf_druid_on_the_opponents_turn():
    scenario = _board(["Circle of the Moon Druid"])
    _next_turn(scenario)
    chars = _chars(scenario, "Circle of the Moon Druid")
    assert set(chars.subtypes) == {"Human", "Elf", "Druid"}
    assert chars.power_toughness == (2, 4)


# -- Blood Burglar: the keyword shape of the same turn gate ----------------------


def test_blood_burglar_has_lifelink_only_during_its_controllers_turn():
    scenario = _board(["Blood Burglar"])
    assert _has(_chars(scenario, "Blood Burglar"), "Lifelink")
    _next_turn(scenario)
    assert not _has(_chars(scenario, "Blood Burglar"), "Lifelink")


# -- Rusted Relic: metalcraft makes it a 5/5 Golem artifact creature ---------------


def test_rusted_relic_is_a_5_5_golem_creature_with_three_artifacts():
    scenario = _board(["Rusted Relic", "Ornithopter", "Sol Ring"])
    chars = _chars(scenario, "Rusted Relic")
    assert chars.power_toughness == (5, 5)
    assert "Golem" in chars.subtypes
    assert _types(scenario, "Rusted Relic") == {"artifact", "creature"}
    assert _notices(scenario) == []


def test_rusted_relic_is_only_an_artifact_with_two_artifacts():
    scenario = _board(["Rusted Relic", "Ornithopter"])
    assert _types(scenario, "Rusted Relic") == {"artifact"}


def test_rusted_relic_flips_when_the_third_artifact_arrives_and_leaves():
    scenario = _board(["Rusted Relic", "Ornithopter", "Sol Ring"])
    assert "creature" in _types(scenario, "Rusted Relic")
    scenario.game.destroy(scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice"))
    assert "creature" not in _types(scenario, "Rusted Relic")


def test_rusted_relic_ignores_the_opponents_artifacts():
    scenario = _board(["Rusted Relic", "Ornithopter"], ["Sol Ring", "Ornithopter"])
    assert "creature" not in _types(scenario, "Rusted Relic")


# -- Ardent Recruit: the same ability word, a pump ---------------------------------


def test_ardent_recruit_gets_plus_two_with_three_artifacts_only():
    with_three = _board(["Ardent Recruit", "Ornithopter", "Sol Ring", "Bonesplitter"])
    assert _chars(with_three, "Ardent Recruit").power_toughness == (3, 3)
    with_two = _board(["Ardent Recruit", "Ornithopter", "Sol Ring"])
    assert _chars(with_two, "Ardent Recruit").power_toughness == (1, 1)
    assert _notices(with_three) == []


def test_ardent_recruit_flips_when_an_artifact_leaves():
    scenario = _board(["Ardent Recruit", "Ornithopter", "Sol Ring", "Bonesplitter"])
    assert _chars(scenario, "Ardent Recruit").power_toughness == (3, 3)
    scenario.game.destroy(scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice"))
    assert _chars(scenario, "Ardent Recruit").power_toughness == (1, 1)


# -- Puresteel Paladin: metalcraft gives Equipment equip {0} ------------------------


def _equip_cost(scenario, equipment, creature):
    activation = equip_activation(
        scenario.game,
        scenario.find(equipment, Zone.BATTLEFIELD, "alice"),
        scenario.find(creature, Zone.BATTLEFIELD, "alice"),
        "alice",
    )
    return str(activation.cost.mana)


def test_puresteel_paladin_makes_equip_free_with_three_artifacts():
    scenario = _board(["Puresteel Paladin", "Bonesplitter", "Ornithopter", "Sol Ring"])
    assert _equip_cost(scenario, "Bonesplitter", "Puresteel Paladin") in ("{0}", "")
    assert _notices(scenario) == []


def test_puresteel_paladin_without_metalcraft_leaves_the_printed_equip_cost():
    scenario = _board(["Puresteel Paladin", "Bonesplitter", "Ornithopter"])
    assert _equip_cost(scenario, "Bonesplitter", "Puresteel Paladin") == "{1}"


def test_puresteel_paladin_equip_cost_flips_when_an_artifact_leaves():
    scenario = _board(["Puresteel Paladin", "Bonesplitter", "Ornithopter", "Sol Ring"])
    assert _equip_cost(scenario, "Bonesplitter", "Puresteel Paladin") in ("{0}", "")
    scenario.game.destroy(scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice"))
    assert _equip_cost(scenario, "Bonesplitter", "Puresteel Paladin") == "{1}"


def test_puresteel_paladin_does_not_discount_an_opponents_equipment():
    scenario = _board(
        ["Puresteel Paladin", "Ornithopter", "Sol Ring"], ["Bonesplitter", "Grizzly Bears"]
    )
    activation = equip_activation(
        scenario.game,
        scenario.find("Bonesplitter", Zone.BATTLEFIELD, "bob"),
        scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob"),
        "bob",
    )
    assert str(activation.cost.mana) == "{1}"


def test_puresteel_paladin_free_equip_actually_attaches():
    scenario = _board(["Puresteel Paladin", "Bonesplitter", "Ornithopter", "Sol Ring"])
    bonesplitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    paladin = scenario.find("Puresteel Paladin", Zone.BATTLEFIELD, "alice")
    activation = equip_activation(scenario.game, bonesplitter, paladin, "alice")
    payment = activation.begin_paying()
    payment.pay()
    activation.activate()
    scenario.resolve_top()
    assert scenario.game.characteristics_of(paladin).power_toughness == (4, 2)
