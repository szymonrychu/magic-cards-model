"""A creature's own static gated on the other permanents you control:

- "This creature has `<keyword>` as long as you control another `<type>`."
  - Bolg's Company (haste, Goblin) and Dain's Company (lifelink, Dwarf), with
  Stampeding Horncrest (haste, Dinosaur) as the proof printing - not a Hobbit
  card and not in any deck;
- "This creature can't attack unless you control `<count>` other `<type>`."
  - Chief Warg's Company ("two or more other Wolves"), with Mouser Mark III
  ("another artifact") as the proof printing.

Every rule cited here was read whole with `mise run rules:find` in the
session that wrote this file:

- **CR 604.2** / **CR 611.3a** - a static ability's effect applies at any
  given moment to whatever its text indicates, so the condition is asked on
  the board as it stands.
- **CR 613.1f** - layer 6, where the keyword is granted.
- **CR 508.1c** - "The active player checks each creature they control to
  see whether it's affected by any restrictions (effects that say a creature
  can't attack, or that it can't attack unless some condition is met). If
  any restrictions are being disobeyed, the declaration of attackers is
  illegal."
- **CR 508.1a** - summoning sickness, which haste answers.
- **CR 702.15b** - lifelink's damage causing its controller to gain that
  much life.
"""

import pytest

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def _ready(scenario):
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


# --------------------------------------------------------------------------
# "has <keyword> as long as you control another <type>"
# --------------------------------------------------------------------------


def test_bolg_alone_has_no_haste():
    """ "another Goblin": Bolg's Company is itself a Goblin, and does not
    count."""
    scenario = Scenario().player("alice", hand=["Bolg's Company"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolg = scenario.put_onto_battlefield("Bolg's Company")
    assert not scenario.game.characteristics_of(bolg).has_ability("Haste")
    _ready(scenario)
    assert "summoning sickness" in (scenario.game.why_cannot_attack(bolg, "bob") or "")


def test_bolg_with_another_goblin_has_haste_and_can_attack_at_once():
    scenario = (
        Scenario()
        .player("alice", hand=["Bolg's Company"], battlefield=["Goblin Brigand"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolg = scenario.put_onto_battlefield("Bolg's Company")
    assert scenario.game.characteristics_of(bolg).has_ability("Haste")
    _ready(scenario)
    assert scenario.game.why_cannot_attack(bolg, "bob") is None


def test_an_opponents_goblin_does_not_count():
    scenario = (
        Scenario()
        .player("alice", hand=["Bolg's Company"])
        .player("bob", battlefield=["Goblin Brigand"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolg = scenario.put_onto_battlefield("Bolg's Company")
    assert not scenario.game.characteristics_of(bolg).has_ability("Haste")


def test_two_bolgs_give_each_other_haste():
    scenario = Scenario().player("alice", battlefield=["Bolg's Company", "Bolg's Company"]).build()
    for bolg in scenario.creatures("Bolg's Company", "Bolg's Company"):
        assert scenario.game.characteristics_of(bolg).has_ability("Haste")


def test_haste_goes_the_moment_the_other_goblin_leaves():
    """CR 611.3a: not locked in."""
    scenario = Scenario().player("alice", battlefield=["Bolg's Company", "Goblin Brigand"]).build()
    bolg = scenario.creature("Bolg's Company")
    assert scenario.game.characteristics_of(bolg).has_ability("Haste")
    scenario.game.sacrifice(scenario.creature("Goblin Brigand"))
    assert not scenario.game.characteristics_of(bolg).has_ability("Haste")


def test_dains_company_has_lifelink_with_another_dwarf_and_gains_life():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Dáin's Company", "Ori, Keeper of Songs"])
        .player("bob")
        .build()
    )
    company = scenario.creature("Dáin's Company")
    assert scenario.game.characteristics_of(company).has_ability("Lifelink")
    _ready(scenario)
    company.summoning_sick = False
    scenario.attack_with(company)
    scenario.game.turn.step = Step.DECLARE_BLOCKERS
    scenario.no_blocks()
    scenario.combat_damage()
    assert scenario.player("alice").life == 22
    assert scenario.player("bob").life == 18


def test_dains_company_alone_has_no_lifelink():
    scenario = Scenario().player("alice", battlefield=["Dáin's Company"]).build()
    company = scenario.creature("Dáin's Company")
    assert not scenario.game.characteristics_of(company).has_ability("Lifelink")


def test_stampeding_horncrest_needs_another_dinosaur():
    """The proof printing: the same template, a different keyword owner and
    type."""
    alone = Scenario().player("alice", battlefield=["Stampeding Horncrest"]).build()
    assert not alone.game.characteristics_of(alone.creature("Stampeding Horncrest")).has_ability(
        "Haste"
    )
    paired = (
        Scenario()
        .player("alice", battlefield=["Stampeding Horncrest", "Colossal Dreadmaw"])
        .build()
    )
    assert paired.game.characteristics_of(paired.creature("Stampeding Horncrest")).has_ability(
        "Haste"
    )


# --------------------------------------------------------------------------
# "can't attack unless you control <count> other <type>" (CR 508.1c)
# --------------------------------------------------------------------------


def _warg(*others: str, bob: tuple[str, ...] = ()) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Chief Warg's Company", *others])
        .player("bob", battlefield=list(bob))
    )


def _warg_ready(scenario):
    _ready(scenario)
    for creature in scenario.game.permanents_controlled_by("alice"):
        creature.summoning_sick = False
    return scenario.creature("Chief Warg's Company")


@pytest.mark.parametrize("others", [(), ("Watchwolf",)])
def test_chief_warg_cannot_attack_with_fewer_than_two_other_wolves(others):
    scenario = _warg(*others).build()
    warg = _warg_ready(scenario)
    reason = scenario.game.why_cannot_attack(warg, "bob")
    assert reason is not None and "CR 508.1c" in reason
    with pytest.raises(ValueError, match="CR 508.1c"):
        scenario.attack_with(warg)


def test_chief_warg_attacks_with_two_other_wolves():
    scenario = _warg("Watchwolf", "Watchwolf").build()
    warg = _warg_ready(scenario)
    assert scenario.game.why_cannot_attack(warg, "bob") is None
    scenario.attack_with(warg)
    assert scenario.attackers() == [warg]


def test_an_opponents_wolves_do_not_count():
    scenario = _warg("Watchwolf", bob=("Watchwolf", "Watchwolf")).build()
    warg = _warg_ready(scenario)
    assert scenario.game.why_cannot_attack(warg, "bob") is not None


def test_the_wolves_can_themselves_attack_alongside():
    """The count is of Wolves you control, attacking or not."""
    scenario = _warg("Watchwolf", "Watchwolf").build()
    warg = _warg_ready(scenario)
    wolves = scenario.creatures("Watchwolf", "Watchwolf")
    scenario.attack_with(warg, *wolves)
    assert len(scenario.attackers()) == 3


def test_mouser_mark_iii_needs_another_artifact():
    """The proof printing: "another artifact" - a count of one, a card type
    rather than a subtype, and "another" rather than "other"."""
    alone = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Mouser Mark III"])
        .player("bob")
        .build()
    )
    _ready(alone)
    mouser = alone.creature("Mouser Mark III")
    mouser.summoning_sick = False
    assert "CR 508.1c" in (alone.game.why_cannot_attack(mouser, "bob") or "")

    paired = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Mouser Mark III", "Darksteel Relic"])
        .player("bob")
        .build()
    )
    _ready(paired)
    mouser = paired.creature("Mouser Mark III")
    mouser.summoning_sick = False
    assert paired.game.why_cannot_attack(mouser, "bob") is None
