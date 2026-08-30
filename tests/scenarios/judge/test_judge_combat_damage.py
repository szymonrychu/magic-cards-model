"""Judge scenarios: assigning combat damage when the board moved underneath it.

Sourced from the DDR judge transcripts. Episodes covered:

- **DDR#699** - Colossal Dreadmaw vs. Spike-Tailed Ceratops (trample, and damage
  that is already marked on the blocker)
- **DDR#857** - Combat Damage after Killing a Blocker (CR 510.1c, and the second
  strike of a double striker)
- **DDR#410** - Blightsteel Colossus + Fog Bank (prevention beats the damage
  event, so nothing downstream of the damage happens either)

The thread running through all of them is that CR 510.1 asks the board *at the
moment damage is assigned*, not the board as it stood when blockers were
declared. Every CR number here was looked up with `knowledge_search(type="rules")`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def bolt(scenario, victim):
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    return scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[victim])


def test_trample_counts_damage_already_marked_on_the_blocker_as_lethal():
    """DDR#699: three damage already on a 4/4 means only one more is "lethal".

    CR 702.19b: the attacker's controller assigns damage to the blockers first,
    and only "once all those blocking creatures are assigned lethal damage" does
    the excess go to the defending player. Lethal is measured against what the
    creature still needs, so the Bolt earlier in the turn is worth four extra
    points of trample damage, not three.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain", "Colossal Dreadmaw"])
        .player("bob", battlefield=["Spike-Tailed Ceratops"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "alice")
    ceratops = scenario.creature("Spike-Tailed Ceratops", "bob")

    scenario.attack_with(dreadmaw)
    scenario.block(dreadmaw, ceratops)
    bolt(scenario, ceratops)
    assert ceratops.damage == 3, "still alive: a 4/4 survives three"

    assignment = scenario.combat_damage()

    assert assignment == [(ceratops, 1), (scenario.player("bob"), 5), (dreadmaw, 4)]
    assert ceratops.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 15


def test_without_trample_the_whole_six_is_wasted_on_the_blocker():
    """The control for the case above (CR 510.1c).

    A blocked creature without trample assigns all of its damage to the
    creatures blocking it; there is nowhere else for it to go. Six damage lands
    on a 4/4 that only needed one more, and the defending player takes nothing.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Craw Wurm"])
        .player("bob", battlefield=["Spike-Tailed Ceratops"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    wurm = scenario.creature("Craw Wurm", "alice")
    ceratops = scenario.creature("Spike-Tailed Ceratops", "bob")

    scenario.attack_with(wurm)
    scenario.block(wurm, ceratops)
    assignment = scenario.combat_damage()

    assert assignment == [(ceratops, 6), (wurm, 4)]
    assert scenario.player("bob").life == 20


def test_a_blocked_creature_whose_blocker_died_assigns_no_damage_at_all():
    """DDR#857: killing the blocker before damage does not unblock the attacker.

    CR 509.1h: once blockers are declared the attacker "becomes a blocked
    creature ... this remains unchanged" even if every blocker leaves. CR 510.1c
    then says a blocked creature with no creatures blocking it assigns no combat
    damage. Removing the blocker is a way to take zero, not a way to get through.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain", "Watchwolf"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    wolf = scenario.creature("Watchwolf", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.attack_with(wolf)
    scenario.block(wolf, bears)
    bolt(scenario, bears)
    assert bears.zone is Zone.GRAVEYARD

    assignment = scenario.combat_damage()

    assert assignment == []
    assert scenario.player("bob").life == 20
    assert scenario.game.is_blocked(wolf), "still blocked, with nothing blocking it"


def test_trample_is_the_exception_that_still_gets_through():
    """DDR#857 with trample bolted on (CR 702.19d).

    "If an attacking creature with trample ... is blocked, but there are no
    creatures blocking it when damage is assigned, its damage is assigned to the
    defending player." Same board as above, different keyword, opposite answer.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain", "Colossal Dreadmaw"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.attack_with(dreadmaw)
    scenario.block(dreadmaw, bears)
    bolt(scenario, bears)

    assignment = scenario.combat_damage()

    assert assignment == [(scenario.player("bob"), 6)]
    assert scenario.player("bob").life == 14


def test_a_double_striker_assigns_nothing_the_second_time_if_it_killed_its_blocker():
    """DDR#857 (27:29): the second strike still belongs to a blocked creature.

    Fencing Ace is a 1/1 with double strike, so CR 510.4 gives combat two damage
    steps. Its blocker dies to the first one - state-based actions run between
    the steps (CR 704.3) - and by the regular damage step the Ace is a blocked
    creature with no blockers, so CR 510.1c gives it nothing to assign.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Fencing Ace"])
        .player("bob", battlefield=["Memnite"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ace = scenario.creature("Fencing Ace", "alice")
    memnite = scenario.creature("Memnite", "bob")

    scenario.attack_with(ace)
    scenario.block(ace, memnite)
    assignment = scenario.combat_damage()

    assert scenario.game.combat.damage_steps_done == 2
    assert memnite.zone is Zone.GRAVEYARD
    assert assignment == [(memnite, 1)], "only the first strike assigned anything"
    assert scenario.player("bob").life == 20


@pytest.mark.xfail(
    strict=True,
    reason="prevention effects are not modelled (CR 615): machines/replacement.py parses "
    "'prevent all combat damage' but Game.combat_damage deals it regardless",
)
def test_fog_bank_prevents_the_combat_damage_in_both_directions():
    """DDR#410: prevention removes the damage event, not just its result.

    CR 615.1 makes a prevention effect a continuous effect that watches for the
    damage event and stops it happening. Fog Bank prevents all combat damage
    dealt to *and* by itself, so a 6/6 trampler bounces off it entirely - and
    because the damage never happens, nothing that keys off damage happens
    either (the episode's point about infect and poison counters).
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Colossal Dreadmaw"])
        .player("bob", battlefield=["Fog Bank"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "alice")
    bank = scenario.creature("Fog Bank", "bob")

    scenario.attack_with(dreadmaw)
    scenario.block(dreadmaw, bank)
    scenario.combat_damage()

    assert bank.damage == 0
    assert bank.zone is Zone.BATTLEFIELD
    assert scenario.player("bob").life == 20, "trample cannot spill past prevented damage"
