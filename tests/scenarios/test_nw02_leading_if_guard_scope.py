"""The damage reader's leading-"If <condition>," guard (NW02-T3) intercepts only
the condition families a conditional damage sentence needs; "If you do" (a
reflexive follow-up, CR 603.12 / CR 608.2c) and "If the gift was promised,
instead ..." (CR 702.174k, CR 614.1a) still reach the damage reader.

Clockwork Hydra: "Whenever this creature attacks or blocks, remove a +1/+1
counter from it. If you do, it deals 1 damage to any target."
Wildfire Howl (Gift a card): "Wildfire Howl deals 2 damage to each creature.
If the gift was promised, instead Wildfire Howl deals 1 damage to any target
and 2 damage to each creature."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _attack_with_hydra(counters: int):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Clockwork Hydra"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hydra = scenario.creature("Clockwork Hydra", "alice")
    if counters:
        hydra.add_counters(Counter.PLUS_ONE, counters - hydra.counters[Counter.PLUS_ONE])
    scenario.advance()
    if scenario.stack_names():
        scenario.pass_until_resolved()
    if scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
    scenario.choose_trigger_targets("Clockwork Hydra", ["bob"])
    scenario.attack_with(hydra)
    scenario.pass_until_resolved()
    return scenario, hydra


def test_hydra_removes_a_counter_then_pings_for_one():
    scenario, hydra = _attack_with_hydra(4)
    assert hydra.counters[Counter.PLUS_ONE] == 3
    assert scenario.player("bob").life == 19


def test_hydra_with_no_counter_to_remove_deals_no_damage():
    scenario, hydra = _attack_with_hydra(0)
    assert hydra.counters[Counter.PLUS_ONE] == 0
    assert scenario.player("bob").life == 20


def _howl(gift: str | None):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Mountain"],
            hand=["Wildfire Howl"],
            battlefield=["Mountain"] * 3 + ["Grizzly Bears"],
        )
        .player("bob", library=["Mountain"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spell = scenario.find("Wildfire Howl", Zone.HAND, "alice")
    sources = scenario.untapped_sources(*["Mountain"] * 3, username="alice")
    targets = ["bob"] if gift else []
    scenario.game.cast(spell, "alice", targets=targets, mana_sources=sources, gift=gift)
    scenario.pass_until_resolved()
    return scenario


def test_howl_without_the_gift_sweeps_creatures_only():
    scenario = _howl(None)
    assert scenario.player("bob").life == 20
    assert "Grizzly Bears" not in scenario.battlefield_names()


def test_howl_with_the_gift_also_pings_any_target_for_one():
    scenario = _howl("bob")
    assert scenario.player("bob").life == 19
    assert "Grizzly Bears" not in scenario.battlefield_names()
