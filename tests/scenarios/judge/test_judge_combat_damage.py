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


def test_fog_bank_prevents_the_damage_it_is_dealt_but_not_the_trample_past_it():
    """DDR#410: prevention removes the damage event, not just its result.

    CR 615.1 makes a prevention effect a continuous effect that watches for the
    damage event and stops it happening, so the 2 the Dreadmaw assigns to Fog
    Bank is never dealt and the Wall takes no damage at all.

    What prevention does *not* touch is the assignment. CR 510.1a has each
    creature assign combat damage equal to its power as part of the combat
    damage step, and CR 702.19b has trample send the excess past a blocker that
    has been assigned lethal damage. Only afterwards, at CR 120.4b - "damage is
    dealt, as modified by replacement and prevention effects that interact with
    damage" - does the shield get to speak, and it speaks only for the damage
    aimed at Fog Bank. The 4 that went past is dealt by the Dreadmaw to bob,
    which Fog Bank's ability does not name, so bob takes it.
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
    assignment = scenario.combat_damage()

    assert [amount for _, amount in assignment] == [2, 4], "CR 510.1a assigned all six"
    assert bank.damage == 0, "CR 120.4b prevented the two it was assigned"
    assert bank.zone is Zone.BATTLEFIELD
    assert scenario.player("bob").life == 16, "the trample damage is dealt by the Dreadmaw"
