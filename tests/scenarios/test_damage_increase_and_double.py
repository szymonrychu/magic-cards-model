"""Scenario: static replacement effects that increase or double damage.

Two printed templates, each read off oracle text by `machines/replacement.py`
rather than keyed by card:

- "If a source you control would deal [noncombat] damage to `<recipients>`,
  it deals that much damage plus N / double that damage [to that player or
  permanent] instead." - Artist's Talent's level 3 (CR 716.2a), Tomik,
  Izzet Sparkmage's "plus 1", and the proof printing Solphim, Mayhem Dominus
  ("double that damage to that player or permanent").
- "Double all damage `<subject>` would deal." - Mjolnir, Hammer of Thor's
  "equipped creature" (CR 301.5a), and the proof printing Collective
  Inferno's "that sources you control of the chosen type" (CR 614.12a's
  as-enters choice).

CR 614.1a: "Effects that use the word 'instead' are replacement effects." The
doubling sentence carries no "instead" but modifies how the damage event
happens all the same; CR 614.2 ("Some replacement effects apply to damage from
a source") and CR 609.7b (the source's properties are checked when the damage
would be dealt) are why every source check below reads the source as it is at
that moment. CR 120.1: the object dealing damage is its source. CR 510.2 marks
combat damage, which a "noncombat" template leaves untouched.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file: 614.1a, 614.2, 609.7b, 120.1, 510.2, 716.2a, 301.5a,
614.12a, 614.5.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Choice, ChoiceKind
from tests.scenarios.harness import Scenario

# -- Solphim, Mayhem Dominus: "double that damage to that player or permanent"


def _solphim_board(**alice) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=alice.get("hand", ["Lightning Bolt"]),
            battlefield=["Solphim, Mayhem Dominus", "Mountain", *alice.get("battlefield", [])],
        )
        .player(
            "bob",
            library=["Forest"],
            hand=["Lightning Bolt"],
            battlefield=["Serra Angel", "Mountain"],
        )
    )


def test_solphim_doubles_noncombat_damage_to_an_opponent():
    scenario = _solphim_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=["bob"])

    assert scenario.player("bob").life == 14


def test_solphim_doubles_noncombat_damage_to_a_permanent_an_opponent_controls():
    scenario = _solphim_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[angel])

    assert angel.zone is Zone.GRAVEYARD  # 6 damage to a 4/4


def test_solphim_leaves_damage_to_its_own_controller_alone():
    scenario = _solphim_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=["alice"])

    assert scenario.player("alice").life == 17


def test_solphim_leaves_an_opponents_source_alone():
    """ "a source *you* control" - Bob's Bolt at Alice is not doubled."""
    scenario = _solphim_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")

    dealt = scenario.game.deal_damage(scenario.player("alice"), 3, source=bolt)

    assert dealt == 3


def test_solphim_leaves_combat_damage_alone():
    scenario = _solphim_board(battlefield=["Goblin Guide"]).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    guide = scenario.creature("Goblin Guide", "alice")
    scenario.attack_with(guide)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 18


def test_solphim_and_artists_talent_both_apply_once_each():
    """CR 614.5: each replacement effect gets one opportunity at the event.
    Doubling and +2 both apply; whichever order the affected player picks,
    3 damage becomes more than either effect alone would make it."""
    scenario = _solphim_board(battlefield=["Artist's Talent"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.find("Artist's Talent", Zone.BATTLEFIELD, "alice").class_level = 3
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")

    dealt = scenario.game.deal_damage(scenario.player("bob"), 3, source=bolt)

    assert dealt in (8, 10)


# -- Artist's Talent level 3 and Tomik: "that much damage plus N" -------------


def test_artists_talent_level_3_adds_two_to_a_cast_bolt():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Lightning Bolt"],
            battlefield=["Artist's Talent", "Mountain"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.find("Artist's Talent", Zone.BATTLEFIELD, "alice").class_level = 3
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.will_take_the_may(False, times=None)  # the level 1 loot trigger

    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    while scenario.stack_names() or scenario.pending_triggers:
        scenario.game.put_triggers_on_stack()
        scenario.pass_until_resolved()

    assert scenario.player("bob").life == 15


def test_artists_talent_below_level_3_adds_nothing():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Lightning Bolt"],
            battlefield=["Artist's Talent", "Mountain"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.find("Artist's Talent", Zone.BATTLEFIELD, "alice").class_level = 2
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.will_take_the_may(False, times=None)  # the level 1 loot trigger

    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    while scenario.stack_names() or scenario.pending_triggers:
        scenario.game.put_triggers_on_stack()
        scenario.pass_until_resolved()

    assert scenario.player("bob").life == 17


def test_tomik_adds_one():
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Tomik, Izzet Sparkmage"])
        .player("bob", library=["Forest"], battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tomik = scenario.creature("Tomik, Izzet Sparkmage", "alice")
    angel = scenario.creature("Serra Angel", "bob")

    assert scenario.game.deal_damage(angel, 2, source=tomik) == 3
    assert scenario.game.deal_damage(scenario.player("alice"), 2, source=tomik) == 2


# -- Mjolnir, Hammer of Thor: "Double all damage equipped creature would deal."


def _mjolnir_board(attach: bool = True) -> tuple:
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            battlefield=["Mjölnir, Hammer of Thor", "Isamaru, Hound of Konda", "Goblin Guide"],
        )
        .player("bob", library=["Forest"], battlefield=["Serra Angel"])
        .build()
    )
    hammer = scenario.find("Mjölnir, Hammer of Thor", Zone.BATTLEFIELD, "alice")
    isamaru = scenario.creature("Isamaru, Hound of Konda", "alice")
    if attach:
        hammer.attach_to(isamaru)  # staging: CR 301.5b, attached by an effect
    return scenario, hammer, isamaru


def test_mjolnir_doubles_the_equipped_creatures_combat_damage():
    scenario, _hammer, isamaru = _mjolnir_board()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(isamaru)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 16


def test_mjolnir_doubles_the_equipped_creatures_noncombat_damage():
    scenario, _hammer, isamaru = _mjolnir_board()
    angel = scenario.creature("Serra Angel", "bob")

    assert scenario.game.deal_damage(angel, 2, source=isamaru) == 4


def test_mjolnir_does_not_double_another_creature():
    scenario, _hammer, _isamaru = _mjolnir_board()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    guide = scenario.creature("Goblin Guide", "alice")
    scenario.attack_with(guide)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 18


def test_mjolnir_unattached_doubles_nothing():
    scenario, _hammer, isamaru = _mjolnir_board(attach=False)

    assert scenario.game.deal_damage(scenario.player("bob"), 2, source=isamaru) == 2


def test_mjolnir_does_not_double_its_own_damage():
    """The Equipment is not the equipped creature, so its own "It deals 2
    damage to each creature" is not doubled."""
    scenario, hammer, _isamaru = _mjolnir_board()
    angel = scenario.creature("Serra Angel", "bob")

    assert scenario.game.deal_damage(angel, 2, source=hammer) == 2


def test_mjolnir_doubles_damage_to_its_own_side_too():
    """ "all damage" - no recipient restriction."""
    scenario, _hammer, isamaru = _mjolnir_board()

    assert scenario.game.deal_damage(scenario.player("alice"), 2, source=isamaru) == 4


# -- Collective Inferno: "that sources you control of the chosen type" ------


def _inferno_board(chosen: str) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            battlefield=["Collective Inferno", "Goblin Guide", "Isamaru, Hound of Konda"],
        )
        .player("bob", library=["Forest"], battlefield=["Boggart Brute"])
        .build()
    )
    inferno = scenario.find("Collective Inferno", Zone.BATTLEFIELD, "alice")
    inferno.choice = Choice(kind=ChoiceKind.CREATURE_TYPE, value=chosen)  # CR 614.12a
    return scenario


def test_collective_inferno_doubles_a_source_of_the_chosen_type():
    scenario = _inferno_board("Goblin")
    guide = scenario.creature("Goblin Guide", "alice")

    assert scenario.game.deal_damage(scenario.player("bob"), 2, source=guide) == 4


def test_collective_inferno_ignores_another_type():
    scenario = _inferno_board("Goblin")
    isamaru = scenario.creature("Isamaru, Hound of Konda", "alice")

    assert scenario.game.deal_damage(scenario.player("bob"), 2, source=isamaru) == 2


def test_collective_inferno_ignores_an_opponents_source_of_that_type():
    scenario = _inferno_board("Goblin")
    brute = scenario.creature("Boggart Brute", "bob")

    assert scenario.game.deal_damage(scenario.player("alice"), 3, source=brute) == 3


def test_collective_inferno_doubles_combat_damage():
    scenario = _inferno_board("Dog")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    isamaru = scenario.creature("Isamaru, Hound of Konda", "alice")
    scenario.attack_with(isamaru)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 16
