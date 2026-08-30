"""Deathtouch: what counts as lethal, and the state-based action (CR 702.2).

CR 702.2a: "Deathtouch is a static ability." It does two separate things, and
the corner cases are all about telling them apart:

- **CR 702.2c** changes the *assignment*: "Any nonzero amount of combat damage
  assigned to a creature by a source with deathtouch is considered to be lethal
  damage for the purposes of determining if excess damage is being dealt." That
  is arithmetic during CR 510.1c, before any damage is dealt.
- **CR 702.2b / CR 704.5h** destroy the creature afterwards: "If a creature has
  toughness greater than 0, and it's been dealt damage by a source with
  deathtouch since the last time state-based actions were checked, that creature
  is destroyed." No amount of toughness saves it.

CR 702.2d adds that "the deathtouch rules function no matter what zone an object
with deathtouch deals damage from" - which this engine cannot show, because
`Game.deal_damage` carries no source (see `docs/engine-coverage.md`).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import lethal_for
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def duel(attacker: str, *blockers: str) -> Scenario:
    return (
        Scenario().player("alice", battlefield=[attacker]).player("bob", battlefield=list(blockers))
    )


def test_one_damage_from_a_deathtoucher_destroys_a_bigger_creature():
    """CR 704.5h: toughness 6 is no defence against one point of deathtouch damage."""
    scenario = duel("Questing Beast", "Wurmcoil Engine").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    beast = scenario.creature("Questing Beast")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.attack_with(beast)
    scenario.block(beast, wurm)
    scenario.combat_damage()

    # Four damage on a 6/6 is not lethal by CR 704.5g, so 704.5h is the only
    # rule that can have killed it.
    assert wurm.zone is Zone.GRAVEYARD


def test_a_creature_that_takes_no_deathtouch_damage_survives():
    """The other side of CR 704.5h: it is *dealt damage* that destroys, not blocking.

    Fog Bank prevents all combat damage dealt to and by it (CR 615.1a), so the
    deathtouch damage event deals nothing - and a creature that was dealt no
    damage was not dealt damage by a source with deathtouch.
    """
    scenario = duel("Questing Beast", "Fog Bank").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    beast = scenario.creature("Questing Beast")
    bank = scenario.creature("Fog Bank", "bob")
    scenario.attack_with(beast)
    scenario.block(beast, bank)
    scenario.combat_damage()

    assert bank.zone is Zone.BATTLEFIELD
    assert bank.damage == 0
    assert not bank.dealt_deathtouch_damage


def test_a_deathtouch_blocker_kills_the_attacker_it_could_not_have_killed():
    """Deathtouch works blocking as well as attacking - it is not an evasion ability."""
    scenario = duel("Wurmcoil Engine", "Sheoldred, the Apocalypse").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    wurm = scenario.creature("Wurmcoil Engine")
    sheoldred = scenario.creature("Sheoldred, the Apocalypse", "bob")
    scenario.attack_with(wurm)
    scenario.block(wurm, sheoldred)
    scenario.combat_damage()

    # Sheoldred is a 4/5 and the Wurm a 6/6: four damage is not lethal by
    # CR 704.5g, and both creatures have deathtouch, so both die by CR 704.5h.
    assert wurm.zone is Zone.GRAVEYARD
    assert sheoldred.zone is Zone.GRAVEYARD


def test_a_deathtoucher_assigns_only_one_to_each_blocker():
    """CR 702.2c: one is a nonzero amount, so one is lethal for the assignment.

    Without deathtouch a 4/4 divides two and two across a pair of 2/2s. With it,
    each blocker only needs one before the next may be assigned any, so the
    first blocker takes one and the leftover falls on the last - which is where
    CR 510.1c puts damage that has nowhere else to go without trample.
    """
    scenario = duel("Questing Beast", "Grizzly Bears", "Watchwolf").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    beast = scenario.creature("Questing Beast")
    bears = scenario.creature("Grizzly Bears", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.attack_with(beast)
    scenario.block(beast, bears, wolf)
    assignment = scenario.combat_damage()

    assert (bears, 1) in assignment
    assert (wolf, 3) in assignment
    assert bears.zone is Zone.GRAVEYARD
    assert wolf.zone is Zone.GRAVEYARD


def test_lethal_damage_is_one_for_a_deathtoucher_whatever_the_toughness():
    """CR 702.2c, asserted on the arithmetic itself.

    Trample's excess (CR 702.19b) is computed from the same number, so a
    creature with both would send everything past the first point through. No
    printing in `tests/fixtures/cards/` has deathtouch *and* trample, and
    hand-writing one is banned in this project, so the shared function is what
    the assertion can reach.
    """
    scenario = duel("Questing Beast", "Wurmcoil Engine", "Grizzly Bears").build()
    beast = scenario.creature("Questing Beast")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")

    assert lethal_for(beast, wurm) == 1
    assert lethal_for(beast, bears) == 1
    # A creature without deathtouch still needs the whole toughness.
    assert lethal_for(bears, wurm) == 6


def test_deathtouch_damage_is_forgotten_when_the_creature_changes_zones():
    """CR 400.7: the card in the graveyard is a new object, marked with nothing."""
    scenario = duel("Questing Beast", "Wurmcoil Engine").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    beast = scenario.creature("Questing Beast")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.attack_with(beast)
    scenario.block(beast, wurm)
    scenario.combat_damage()

    assert wurm.zone is Zone.GRAVEYARD
    assert not wurm.dealt_deathtouch_damage
    assert wurm.damage == 0
