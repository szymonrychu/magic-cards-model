"""Bark of Doran: "As long as equipped creature's toughness is greater than
its power, it assigns combat damage equal to its toughness rather than its
power."

The singular, Equipment-scoped twin of the already-proven group grant ("Each
creature you control with toughness greater than its power assigns combat
damage equal to its toughness rather than its power.", Ghalta the Immovable /
Ancient Lumberknot, `tests/scenarios/test_combat_static_grants.py`).
`EquippedCreatureIfToughnessExceedsPower` (`machines/layers.py`) is the new
selector: CR 301.5a's "equipped creature" is whichever one permanent this
specific Equipment (`equipment_id`) is attached to right now, read straight
off the board's own `attached_to` link rather than a controller-wide scan.
`machines/combat.py`'s `_assignment_power_of` needed no change at all: both
selectors grant the identical `ASSIGNS_DAMAGE_AS_TOUGHNESS_TEXT`, which that
function already reads off the computed board regardless of which permanent's
static put it there.

No second Modern/Pioneer/Standard-legal printing of this exact "equipped
creature's toughness is greater than its power" sentence was found this
session (Scryfall search, dated MEMORY.md line) - Ancient Lumberknot proves
only the pre-existing *group* shape, over every creature the controller has,
never a single equipped one.

CR numbers verified this session with `mise run rules:find`:

- **CR 301.5a** - "The creature an Equipment is attached to is called the
  'equipped creature.'"
- **CR 510.1a** - "Each attacking creature and each blocking creature assigns
  combat damage equal to its power" - the baseline this grant replaces.
- **CR 611.3a** - a static ability's effect "isn't 'locked in'" - re-asked
  live as power and toughness change.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import ASSIGNS_DAMAGE_AS_TOUGHNESS_TEXT
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_bark_of_doran_grants_toughness_assignment_when_toughness_exceeds_power():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Bark of Doran", "Wall of Omens"])
        .player("bob")
        .build()
    )
    doran = scenario.find("Bark of Doran", Zone.BATTLEFIELD, "alice")
    wall = scenario.creature("Wall of Omens", "alice")
    doran.attach_to(wall)

    # Wall of Omens is printed 0/4; Bark of Doran's own +0/+1 makes it 0/5 -
    # toughness (5) is still greater than power (0).
    assert scenario.game.characteristics_of(wall).has_ability(ASSIGNS_DAMAGE_AS_TOUGHNESS_TEXT)


def test_bark_of_doran_withholds_it_when_toughness_does_not_exceed_power():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Bark of Doran", "Goblin Piker"])
        .player("bob")
        .build()
    )
    doran = scenario.find("Bark of Doran", Zone.BATTLEFIELD, "alice")
    piker = scenario.creature("Goblin Piker", "alice")
    doran.attach_to(piker)

    # Goblin Piker is printed 2/1; Bark of Doran's own +0/+1 makes it 2/2 -
    # toughness (2) equals power (2), never *greater* than it.
    assert (
        scenario.game.power_of(piker),
        scenario.game.toughness_of(piker),
    ) == (2, 2)
    assert not scenario.game.characteristics_of(piker).has_ability(ASSIGNS_DAMAGE_AS_TOUGHNESS_TEXT)


def test_bark_of_doran_withholds_it_from_an_unattached_creature():
    """No `attached_to` link at all - the selector never selects anything,
    exactly the way `AttackingGroupControlledBy` grants nothing to a creature
    that never attacked."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Bark of Doran", "Wall of Omens"])
        .player("bob")
        .build()
    )
    wall = scenario.creature("Wall of Omens", "alice")

    assert not scenario.game.characteristics_of(wall).has_ability(ASSIGNS_DAMAGE_AS_TOUGHNESS_TEXT)


def test_bark_of_doran_actually_changes_the_damage_a_blocker_deals():
    """Functional proof, not just the computed ability text: a 0/5 Wall of
    Omens (0 power) assigning toughness instead deals 5, not 0 - CR 510.1a's
    own "creatures that would assign 0 or less damage this way don't assign
    combat damage at all" is exactly what this grant is designed to escape.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hill Giant"])
        .player("bob", battlefield=["Bark of Doran", "Wall of Omens"])
        .build()
    )
    giant = scenario.creature("Hill Giant", "alice")
    doran = scenario.find("Bark of Doran", Zone.BATTLEFIELD, "bob")
    wall = scenario.creature("Wall of Omens", "bob")
    doran.attach_to(wall)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(giant)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.block(giant, wall)
    scenario.combat_damage()

    assert giant.zone is Zone.GRAVEYARD, "5 toughness-as-damage kills the 3/3 Hill Giant"


def test_bark_of_doran_stops_applying_the_instant_it_is_unattached():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Bark of Doran", "Wall of Omens"])
        .player("bob")
        .build()
    )
    doran = scenario.find("Bark of Doran", Zone.BATTLEFIELD, "alice")
    wall = scenario.creature("Wall of Omens", "alice")
    doran.attach_to(wall)
    assert scenario.game.characteristics_of(wall).has_ability(ASSIGNS_DAMAGE_AS_TOUGHNESS_TEXT)

    doran.unattach()

    assert not scenario.game.characteristics_of(wall).has_ability(ASSIGNS_DAMAGE_AS_TOUGHNESS_TEXT)
