"""CR 601.2c: a spell with several "target" phrases has each target chosen
for its own phrase, and CR 608.2c reads each instruction for what it says -
so a sentence acts only on the target(s) announced for its own words, never
on a target another sentence of the same spell named.

Jeskai Revelation: "Return target spell or permanent to its owner's hand.
Jeskai Revelation deals 4 damage to any target. ..." - the bounce sentence
used to return the damage target too (it saw the spell's whole target list),
leaving nothing for the 4 damage.

Targets are announced in the spell's requirement order (`TargetingProfile.
requirements`), which for Jeskai Revelation is "any target" first, then
"target spell or permanent" - each test passes them in that order.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

_JESKAI_MANA = ["Plains", "Plains", "Island", "Island", "Island", "Mountain", "Mountain"]


def _board(hand, battlefield, bob_battlefield):
    scenario = (
        Scenario()
        .player("alice", hand=list(hand), battlefield=list(battlefield), library=["Island"] * 10)
        .player("bob", battlefield=list(bob_battlefield), library=["Forest"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_jeskai_revelation_bounces_only_its_bounce_target_and_burns_the_other():
    scenario = _board(["Jeskai Revelation"], _JESKAI_MANA, ["Hill Giant", "Watchwolf"])
    giant = scenario.creature("Hill Giant", "bob")
    wolf = scenario.creature("Watchwolf", "bob")

    scenario.cast_and_resolve("Jeskai Revelation", auto=True, targets=[wolf, giant])

    assert giant.zone is Zone.HAND
    assert wolf.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 24


def test_jeskai_revelation_burns_a_player_and_bounces_a_permanent():
    scenario = _board(["Jeskai Revelation"], _JESKAI_MANA, ["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")

    scenario.cast_and_resolve("Jeskai Revelation", auto=True, targets=["bob", giant])

    assert giant.zone is Zone.HAND
    assert scenario.player("bob").life == 16


def test_jeskai_revelation_damage_still_lands_when_the_bounce_target_is_gone():
    """CR 608.2b: one illegal target leaves the other sentences intact."""
    scenario = _board(["Jeskai Revelation"], _JESKAI_MANA, ["Hill Giant", "Watchwolf"])
    giant = scenario.creature("Hill Giant", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.cast_onto_stack("Jeskai Revelation", auto=True, targets=[wolf, giant])
    scenario.game.sacrifice(giant)

    scenario.pass_until_resolved()

    assert wolf.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.GRAVEYARD


def test_jeskai_revelation_one_permanent_named_for_both_phrases_is_bounced_then_missed():
    """The same object may fill both phrases (CR 115.3: one object can be
    chosen once for each instance of "target"); bounced first, it is gone
    when the damage would land."""
    scenario = _board(["Jeskai Revelation"], _JESKAI_MANA, ["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")

    scenario.cast_and_resolve("Jeskai Revelation", auto=True, targets=[giant, giant])

    assert giant.zone is Zone.HAND
    assert giant.damage == 0


def test_chandras_revolution_damage_never_reaches_the_land_target():
    scenario = _board(["Chandra's Revolution"], ["Mountain"] * 4, ["Colossal Dreadmaw", "Forest"])
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")

    scenario.cast_and_resolve("Chandra's Revolution", auto=True, targets=[dreadmaw, forest])

    assert dreadmaw.damage == 4
    assert forest.damage == 0
    assert forest.tapped and not dreadmaw.tapped


# -- the same for an activated ability -----------------------------------------
#
# Everything Pizza: "{2}{W}{U}{B}{R}{G}, {T}, Sacrifice this artifact: Target
# player gains 3 life and draws a card. Each of your opponents discards a
# card. This artifact deals 3 damage to any target. Put three +1/+1 counters
# on up to one target creature." Requirement order: "any target", "target
# player", "target creature".

_PIZZA_MANA = ["Plains", "Island", "Swamp", "Mountain", "Forest", "Forest", "Forest"]


def _pizza(bob_battlefield):
    scenario = _board([], ["Everything Pizza", *_PIZZA_MANA], bob_battlefield)
    return scenario, scenario.find("Everything Pizza", Zone.BATTLEFIELD, "alice")


def test_everything_pizza_burns_its_damage_target_and_feeds_its_life_target():
    scenario, pizza = _pizza(["Watchwolf"])
    wolf = scenario.creature("Watchwolf", "bob")

    scenario.activate(pizza, index=0, auto=True, targets=["bob", "alice", wolf])
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 23
    assert wolf.damage == 0
    assert wolf.counters["+1/+1"] == 3


def test_everything_pizza_damage_to_a_creature_leaves_the_life_target_unhurt():
    scenario, pizza = _pizza(["Watchwolf", "Hill Giant"])
    wolf = scenario.creature("Watchwolf", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    scenario.activate(pizza, index=0, auto=True, targets=[giant, "alice", wolf])
    scenario.pass_until_resolved()

    assert giant.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 23
    assert scenario.player("bob").life == 20
    assert wolf.counters["+1/+1"] == 3 and wolf.damage == 0


# -- an ability read sentence group by sentence group ---------------------------
#
# Denethor, Stone Seer: "{3}{R}, {T}, Sacrifice Denethor: Target player
# becomes the monarch. Denethor deals 3 damage to any target." Everything
# Pizza's own ability above has a whole-text reader; this one goes through
# the generic per-sentence read. Requirement order: "any target", then
# "target player".


def _denethor(bob_battlefield):
    scenario = _board(
        [],
        ["Denethor, Stone Seer", "Mountain", "Mountain", "Mountain", "Mountain"],
        bob_battlefield,
    )
    denethor = scenario.find("Denethor, Stone Seer", Zone.BATTLEFIELD, "alice")
    denethor.summoning_sick = False
    return scenario, denethor


def test_denethor_crowns_its_player_target_and_burns_only_its_damage_target():
    scenario, denethor = _denethor(["Colossal Dreadmaw"])
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.activate(
        denethor, index=0, auto=True, targets=[dreadmaw, "alice"], sacrificing=[denethor]
    )
    scenario.pass_until_resolved()

    assert scenario.game.monarch == "alice"
    assert scenario.player("alice").life == 20
    assert dreadmaw.damage == 3


def test_denethor_burns_one_player_and_crowns_the_other():
    scenario, denethor = _denethor([])

    scenario.activate(
        denethor, index=0, auto=True, targets=["bob", "alice"], sacrificing=[denethor]
    )
    scenario.pass_until_resolved()

    assert scenario.game.monarch == "alice"
    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 17
