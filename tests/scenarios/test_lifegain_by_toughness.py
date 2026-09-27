"""Scenario: a dies trigger reading its own dying subject's last-known
toughness (CR 603.10a, CR 608.2h).

South Wind Avatar: "Whenever another creature you control dies, you gain
life equal to its toughness."

- **CR 603.10a** - a dies trigger looks back in time: "its" reads the
  toughness the creature had the instant before it died, off `AbilityOnStack.
  event`'s own subject, the same last-known-information primitive
  `event_subject_power` already reads for Gruff Triplets' own dies trigger.
- **CR 119.9** - the gain runs through `Game.gain_life`, which is what lets
  South Wind Avatar's own *second* ability ("Whenever you gain life, each
  opponent loses 1 life.") see it too.
- **CR 122.1a** - toughness read here is the printed box plus any +1/+1 or
  -1/-1 counters the creature carried; a continuous effect's own pump is
  already gone once the creature has left the battlefield.

Paladin of Atonement is the second, non-pool printing that proves the reader
is not gated on "another creature": its own version fires off *itself*
dying ("When this creature dies, you gain life equal to its toughness."),
the opposite condition, read by the identical effect text. Verified legal in
Modern and Pioneer.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_another_creature_dying_gains_life_equal_to_its_toughness():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["South Wind Avatar", "Grizzly Bears"],
            hand=["Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    life_before = scenario.player("alice").life

    scenario.game.deal_damage(bears, 2, source=None)
    scenario.state_based_actions()
    scenario.game.put_triggers_on_stack()

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == ["South Wind Avatar's triggered ability"]
    scenario.pass_until_resolved()

    # Grizzly Bears is a 2/2: its last-known toughness (CR 603.10a) is 2.
    assert scenario.player("alice").life == life_before + 2


def test_a_zero_toughness_creature_gains_no_life():
    scenario = (
        Scenario()
        .player("alice", battlefield=["South Wind Avatar", "Walking Ballista"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ballista = scenario.creature("Walking Ballista", "alice")
    life_before = scenario.player("alice").life

    # Walking Ballista enters with no counters, so it is a 0/0 that dies to
    # CR 704.5f the moment it resolves - already dead by the time this scenario
    # inspects it, which is exactly the toughness-0 case under test.
    scenario.state_based_actions()
    assert ballista.zone is Zone.GRAVEYARD
    if scenario.stack_names():
        scenario.pass_until_resolved()

    assert scenario.player("alice").life == life_before


def test_south_wind_avatars_own_second_ability_sees_the_gain_too():
    """CR 119.9: the life gain runs through `Game.gain_life`, so South Wind
    Avatar's own "Whenever you gain life, each opponent loses 1 life."
    fires off its *own* dies trigger's gain."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["South Wind Avatar", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bob_life_before = scenario.player("bob").life

    scenario.game.deal_damage(bears, 2, source=None)
    scenario.state_based_actions()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()  # the dies trigger: gain 2 life
    if scenario.stack_names():
        scenario.pass_until_resolved()  # the gain-life trigger: bob loses 1

    assert scenario.player("bob").life == bob_life_before - 1


def test_paladin_of_atonement_proves_the_reader_reads_a_self_dies_trigger_too():
    scenario = (
        Scenario().player("alice", battlefield=["Paladin of Atonement"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    paladin = scenario.creature("Paladin of Atonement", "alice")
    life_before = scenario.player("alice").life

    scenario.game.deal_damage(paladin, 2, source=None)
    scenario.state_based_actions()
    scenario.game.put_triggers_on_stack()
    assert paladin.zone is Zone.GRAVEYARD

    dies_triggers = [name for name in scenario.stack_names() if "Paladin of Atonement" in name]
    assert dies_triggers
    scenario.pass_until_resolved()

    # Paladin of Atonement is a 1/1: its own last-known toughness is 1.
    assert scenario.player("alice").life == life_before + 1
