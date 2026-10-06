"""Scenario: "A creature dealt damage this way can't be regenerated this turn."

Listed: Incinerate (one target, "a creature dealt damage this way") and
Flamebreak ("Creatures dealt damage this way", a mass spell). Second
printing: Jaya Ballard, Task Mage's second ability (an activated ability with
the same sentence after "any target").

Verified this session with `mise run rules:find`:

- **CR 701.19c** - effects that say a permanent can't be regenerated don't
  stop regeneration abilities from being activated; they cause regeneration
  shields to not be applied. An unspent shield is still standing afterwards.
- **CR 701.19a** - regenerating creates a shield that replaces the next
  destruction this turn (tap it, remove all damage, remove it from combat).
- **CR 608.2c** - the rider's later text modifies the meaning of the earlier
  damage instruction for exactly the creatures that damage reached.
- **CR 704.5g** - lethal damage destroys the creature (a destruction that a
  regeneration shield would otherwise replace).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _board(*, alice_hand=(), alice_battlefield=(), bob_battlefield=(), bob_hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            hand=list(alice_hand),
            battlefield=list(alice_battlefield),
            library=["Mountain"] * 5,
        )
        .player(
            "bob",
            life=20,
            hand=list(bob_hand),
            battlefield=list(bob_battlefield),
            library=["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _regenerate(scenario, skeleton, swamp):
    scenario.activate(skeleton, swamp)
    scenario.pass_until_resolved()
    assert skeleton.regeneration_shields == 1


# -- baseline: damage alone does not stop a regeneration shield ---------------------


def test_a_regeneration_shield_saves_a_creature_from_plain_lethal_damage():
    scenario = _board(
        alice_hand=["Lightning Bolt"],
        alice_battlefield=["Mountain", "Marang River Skeleton", "Swamp", "Swamp"],
    )
    skeleton = scenario.find("Marang River Skeleton", Zone.BATTLEFIELD, "alice")
    swamp, _ = scenario.untapped_sources("Swamp", "Swamp")
    _regenerate(scenario, skeleton, swamp)
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[skeleton]
    )
    scenario.state_based_actions()

    assert skeleton.zone is Zone.BATTLEFIELD, "Bolt has no can't-be-regenerated rider"
    assert skeleton.tapped and skeleton.damage == 0


# -- Incinerate ---------------------------------------------------------------------


def test_incinerate_kills_a_creature_through_its_regeneration_shield():
    scenario = _board(
        alice_hand=["Incinerate"],
        alice_battlefield=["Mountain", "Mountain", "Marang River Skeleton", "Swamp"],
    )
    skeleton = scenario.find("Marang River Skeleton", Zone.BATTLEFIELD, "alice")
    (swamp,) = scenario.untapped_sources("Swamp")
    _regenerate(scenario, skeleton, swamp)
    scenario.cast_and_resolve(
        "Incinerate", *scenario.untapped_sources("Mountain", "Mountain"), targets=[skeleton]
    )
    scenario.state_based_actions()

    assert skeleton.zone is Zone.GRAVEYARD, "CR 701.19c: the shield is not applied"


def test_incinerate_to_a_player_leaves_every_creature_regenerable():
    scenario = _board(
        alice_hand=["Incinerate"],
        alice_battlefield=["Mountain", "Mountain", "Marang River Skeleton", "Swamp"],
    )
    skeleton = scenario.find("Marang River Skeleton", Zone.BATTLEFIELD, "alice")
    (swamp,) = scenario.untapped_sources("Swamp")
    _regenerate(scenario, skeleton, swamp)
    scenario.cast_and_resolve(
        "Incinerate", *scenario.untapped_sources("Mountain", "Mountain"), targets=["bob"]
    )
    assert scenario.player("bob").life == 17
    assert skeleton.regeneration_shields == 1, "nothing was dealt damage this way"


def test_incinerate_on_a_creature_that_survives_still_makes_it_unregenerable_this_turn():
    """A 6/6 takes 3 and lives; a later lethal damage source cannot be
    regenerated through either (the rider covers the whole turn)."""
    scenario = _board(
        alice_hand=["Incinerate", "Lightning Bolt", "Lightning Bolt"],
        alice_battlefield=["Mountain"] * 6 + ["Swamp"],
        bob_battlefield=["Ancient Silverback", "Forest"],
    )
    silverback = scenario.find("Ancient Silverback", Zone.BATTLEFIELD, "bob")
    scenario.cast_and_resolve(
        "Incinerate", *scenario.untapped_sources("Mountain", "Mountain"), targets=[silverback]
    )
    assert silverback.zone is Zone.BATTLEFIELD and silverback.damage == 3
    scenario.pass_priority("alice")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    scenario.activate(silverback, forest, username="bob")
    scenario.pass_until_resolved()
    assert silverback.regeneration_shields == 1, "bob may still regenerate (CR 701.19c)"
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[silverback]
    )
    scenario.state_based_actions()
    assert silverback.zone is Zone.GRAVEYARD, "3 + 3 damage is lethal and the shield is not applied"


def test_the_rider_does_not_reach_a_creature_that_was_not_dealt_damage():
    """The shield on a bystander still works against the later Bolt."""
    scenario = _board(
        alice_hand=["Incinerate", "Lightning Bolt"],
        alice_battlefield=["Mountain", "Mountain", "Mountain", "Marang River Skeleton", "Swamp"],
        bob_battlefield=["Grizzly Bears"],
    )
    skeleton = scenario.find("Marang River Skeleton", Zone.BATTLEFIELD, "alice")
    (swamp,) = scenario.untapped_sources("Swamp")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    _regenerate(scenario, skeleton, swamp)
    scenario.cast_and_resolve(
        "Incinerate", *scenario.untapped_sources("Mountain", "Mountain"), targets=[bears]
    )
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[skeleton]
    )
    scenario.state_based_actions()
    assert bears.zone is Zone.GRAVEYARD
    assert skeleton.zone is Zone.BATTLEFIELD, "never dealt Incinerate's damage"


# -- Flamebreak: the mass spell ------------------------------------------------------


def test_flamebreak_damages_ground_creatures_and_players_and_blocks_their_regeneration():
    scenario = _board(
        alice_hand=["Flamebreak"],
        alice_battlefield=["Mountain", "Mountain", "Mountain", "Marang River Skeleton", "Swamp"],
        bob_battlefield=["Grizzly Bears", "Birds of Paradise"],
    )
    skeleton = scenario.find("Marang River Skeleton", Zone.BATTLEFIELD, "alice")
    (swamp,) = scenario.untapped_sources("Swamp")
    _regenerate(scenario, skeleton, swamp)
    scenario.cast_and_resolve(
        "Flamebreak", *scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    )
    scenario.state_based_actions()

    assert skeleton.zone is Zone.GRAVEYARD, "regeneration shield not applied (CR 701.19c)"
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob") is not None
    assert scenario.find("Birds of Paradise", Zone.BATTLEFIELD, "bob").damage == 0
    assert scenario.player("alice").life == 17 and scenario.player("bob").life == 17


# -- Jaya Ballard: the same sentence on an activated ability -----------------------


def test_jaya_ballard_damage_ability_prevents_regeneration_of_the_damaged_creature():
    scenario = _board(
        alice_hand=["Lightning Bolt"],
        alice_battlefield=[
            "Jaya Ballard, Task Mage",
            "Mountain",
            "Mountain",
            "Marang River Skeleton",
            "Swamp",
        ],
    )
    jaya = scenario.find("Jaya Ballard, Task Mage", Zone.BATTLEFIELD, "alice")
    jaya.summoning_sick = False
    skeleton = scenario.find("Marang River Skeleton", Zone.BATTLEFIELD, "alice")
    (swamp,) = scenario.untapped_sources("Swamp")
    _regenerate(scenario, skeleton, swamp)
    scenario.activate(
        jaya,
        *scenario.untapped_sources("Mountain", "Mountain"),
        index=1,
        discarding=[scenario.find("Lightning Bolt", Zone.HAND, "alice")],
        targets=[skeleton],
    )
    scenario.pass_until_resolved()
    scenario.state_based_actions()

    assert skeleton.zone is Zone.GRAVEYARD
