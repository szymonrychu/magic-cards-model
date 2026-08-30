"""Lifelink: damage that also gains life (CR 702.15).

CR 702.15b: "Damage dealt by a source with lifelink causes that source's
controller, or its owner if it has no controller, to gain that much life (in
addition to any other results that damage causes)." CR 120.3f says the same
thing from the damage rules' side.

Three things follow, and they are what the corner cases here are about:

- it is *damage dealt*, so damage that was prevented gains nothing (CR 615.1a);
- the amount is the damage, not the power, so a blocker that only takes part of
  an attacker's damage only gains that part;
- CR 702.15e keeps each source's gain a separate event: "If multiple sources
  with lifelink deal damage at the same time, they cause separate life gain
  events."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def duel(*alice: str, bob: tuple[str, ...] = (), life: int = 20) -> Scenario:
    return (
        Scenario()
        .player("alice", life=life, battlefield=list(alice))
        .player("bob", life=life, battlefield=list(bob))
    )


def test_unblocked_lifelink_damage_gains_that_much_life():
    """CR 702.15b, the happy path: six through, six gained, six lost."""
    scenario = duel("Wurmcoil Engine").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    wurm = scenario.creature("Wurmcoil Engine")
    scenario.attack_with(wurm)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("alice").life == 26
    assert scenario.player("bob").life == 14


def test_lifelink_gains_only_the_damage_that_was_assigned():
    """The gain follows the assignment, not the power.

    A 6/6 blocked by a 2/2 assigns two to the blocker and nothing anywhere else
    without trample (CR 510.1c) - but Wurmcoil Engine also has deathtouch, so
    CR 702.2c makes one lethal and the leftover five still land on the blocker
    (CR 510.1c has nowhere else to put them). Six damage dealt, six life gained.
    """
    scenario = duel("Wurmcoil Engine", bob=("Grizzly Bears",)).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    wurm = scenario.creature("Wurmcoil Engine")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(wurm)
    scenario.block(wurm, bears)
    scenario.combat_damage()

    assert scenario.player("alice").life == 26
    assert scenario.player("bob").life == 20


def test_prevented_damage_gains_no_life():
    """CR 615.1a: a prevented event deals zero damage, and zero is not "dealt".

    Fog Bank prevents all combat damage that would be dealt to and dealt by it,
    so Ocelot Pride's lifelink has nothing to work from. This is the case a
    "gain life equal to its power" shortcut would get wrong.
    """
    scenario = duel("Ocelot Pride", bob=("Fog Bank",)).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    ocelot = scenario.creature("Ocelot Pride")
    bank = scenario.creature("Fog Bank", "bob")
    scenario.attack_with(ocelot)
    scenario.block(ocelot, bank)
    scenario.combat_damage()

    assert scenario.player("alice").life == 20
    assert bank.damage == 0


def test_a_lifelink_blocker_gains_life_for_its_controller():
    """Lifelink is not an attacking ability - the blocker's controller gains."""
    scenario = duel("Colossal Dreadmaw", bob=("Wurmcoil Engine",)).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    dreadmaw = scenario.creature("Colossal Dreadmaw")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.attack_with(dreadmaw)
    scenario.block(dreadmaw, wurm)
    scenario.combat_damage()

    assert scenario.player("bob").life == 26
    assert scenario.player("alice").life == 20
    assert dreadmaw.zone is Zone.GRAVEYARD  # deathtouch, CR 704.5h


def test_two_lifelink_sources_gain_separately():
    """CR 702.15e: two sources, two life gain events, and both land."""
    scenario = duel("Wurmcoil Engine", "Ocelot Pride").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    wurm = scenario.creature("Wurmcoil Engine")
    ocelot = scenario.creature("Ocelot Pride")
    scenario.attack_with(wurm, ocelot)
    scenario.no_blocks()
    scenario.combat_damage()

    # Ocelot Pride has first strike, so this is two damage steps (CR 510.4):
    # one for the Ocelot's 1, one for the Wurm's 6.
    assert scenario.player("alice").life == 27
    assert scenario.player("bob").life == 13


def test_lifelink_life_gain_can_outrun_the_damage_being_taken():
    """A trade where both die still gains the life, because the damage was dealt."""
    scenario = duel("Wurmcoil Engine", bob=("Sheoldred, the Apocalypse",), life=5).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    wurm = scenario.creature("Wurmcoil Engine")
    sheoldred = scenario.creature("Sheoldred, the Apocalypse", "bob")
    scenario.attack_with(wurm)
    scenario.block(wurm, sheoldred)
    scenario.combat_damage()

    assert wurm.zone is Zone.GRAVEYARD
    assert sheoldred.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 11
