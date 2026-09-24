"""Putting onto the battlefield the cards that were put into a graveyard
*from the battlefield this turn* - a per-turn zone-change history - and
Supper for Spiders' rider on what they are when they arrive:

"Put onto the battlefield under your control all creature cards in your
opponents' graveyards that were put there from the battlefield this turn.
They are Food artifacts with "{2}, {T}, Sacrifice this artifact: You gain 3
life." (They lose all other types and subtypes.)"

- CR 110.2a: put onto the battlefield by the spell's controller, they enter
  under that player's control.
- "They are Food artifacts" sets their card type and subtype (CR 205.1a: the
  new types replace the old ones) - layer 4 (CR 613.1d) - and grants the
  quoted ability, layer 6 (CR 613.1f), with no duration (CR 611.2a). They
  keep their other abilities. The effect is in place as they arrive, so
  they never enter as creatures.
- A card that left the graveyard and came back, or that reached it from
  anywhere but the battlefield, or on an earlier turn, is not one of them
  (CR 400.7: it is a new object each time it changes zones).

Faith's Reward (the off-set proof, not in any deck list): "Return to the
battlefield all permanent cards in your graveyard that were put there from
the battlefield this turn." - the same history, "permanent cards", your own
graveyard, and no type rider.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import discard
from magic_cards_model.models import Type, Zone

from .harness import Scenario

SUPPER = "Supper for Spiders"


def _cast_supper(scenario):
    scenario.cast_and_resolve(
        SUPPER, *scenario.untapped_sources("Swamp", "Swamp", username="alice")
    )
    scenario.pass_until_resolved()  # anything that triggered on the way in


def _chars(scenario, permanent):
    return scenario.game.computed_board().of(permanent)


def test_a_creature_that_died_this_turn_comes_back_as_a_food_artifact_under_your_control():
    scenario = (
        Scenario()
        .player("alice", hand=[SUPPER], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.destroy(bears)
    assert bears.zone is Zone.GRAVEYARD

    _cast_supper(scenario)

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(bears).username == "alice"
    chars = _chars(scenario, bears)
    assert chars.types == (Type.ARTIFACT,)
    assert chars.subtypes == ("Food",)
    assert "{2}, {T}, Sacrifice this artifact: You gain 3 life." in chars.abilities


def test_the_food_can_be_sacrificed_for_three_life():
    scenario = (
        Scenario()
        .player("alice", hand=[SUPPER], battlefield=["Swamp", "Swamp", "Swamp", "Swamp"], life=10)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.destroy(bears)
    _cast_supper(scenario)

    scenario.activate(bears, *scenario.untapped_sources("Swamp", "Swamp", username="alice"))
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 13
    assert bears.zone is Zone.GRAVEYARD  # its owner's graveyard, bob's


def test_it_keeps_its_own_abilities_and_they_still_trigger():
    """Wall of Omens' "When this creature enters, draw a card." is still its
    ability, and it did enter - alice, who controls it, draws."""
    scenario = (
        Scenario()
        .player("alice", hand=[SUPPER], battlefield=["Swamp", "Swamp"], library=["Island"])
        .player("bob", battlefield=["Wall of Omens"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wall = scenario.creature("Wall of Omens", "bob")
    scenario.game.destroy(wall)
    hand_before = len(scenario.player("alice").hand)

    _cast_supper(scenario)

    assert wall.zone is Zone.BATTLEFIELD
    assert Type.CREATURE not in _chars(scenario, wall).types
    assert len(scenario.player("alice").hand) == hand_before - 1 + 1


def test_they_never_enter_as_creatures():
    """Soul Warden's "Whenever another creature enters" does not fire - the
    Food is what entered."""
    scenario = (
        Scenario()
        .player("alice", hand=[SUPPER], battlefield=["Swamp", "Swamp", "Soul Warden"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.destroy(bears)

    _cast_supper(scenario)

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 20


def test_a_creature_card_discarded_this_turn_is_not_taken():
    scenario = (
        Scenario()
        .player("alice", hand=[SUPPER], battlefield=["Swamp", "Swamp"])
        .player("bob", hand=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.HAND, "bob")
    discard(scenario.game, bears, "bob")
    assert bears.zone is Zone.GRAVEYARD

    _cast_supper(scenario)

    assert bears.zone is Zone.GRAVEYARD


def test_a_creature_card_already_in_the_graveyard_before_this_turn_is_not_taken():
    scenario = (
        Scenario()
        .player("alice", hand=[SUPPER], battlefield=["Swamp", "Swamp"])
        .player("bob", graveyard=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")

    _cast_supper(scenario)

    assert bears.zone is Zone.GRAVEYARD


def test_its_own_controllers_creatures_are_not_taken():
    scenario = (
        Scenario()
        .player("alice", hand=[SUPPER], battlefield=["Swamp", "Swamp", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.destroy(bears)

    _cast_supper(scenario)

    assert bears.zone is Zone.GRAVEYARD


def test_a_noncreature_card_that_died_this_turn_is_not_taken():
    scenario = (
        Scenario()
        .player("alice", hand=[SUPPER], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    scenario.game.destroy(ring)

    _cast_supper(scenario)

    assert ring.zone is Zone.GRAVEYARD


def test_a_card_that_left_the_graveyard_and_came_back_is_a_new_object():
    """The Bears died this turn, went back to bob's hand, then were
    discarded - its latest arrival was not from the battlefield."""
    scenario = (
        Scenario()
        .player("alice", hand=[SUPPER], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.destroy(bears)
    scenario.game.return_to_hand(bears)
    assert bears.zone is Zone.HAND
    discard(scenario.game, bears, "bob")
    assert bears.zone is Zone.GRAVEYARD

    _cast_supper(scenario)

    assert bears.zone is Zone.GRAVEYARD


def test_every_qualifying_card_comes_back_together():
    scenario = (
        Scenario()
        .player("alice", hand=[SUPPER], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.game.destroy(bears)
    scenario.game.destroy(giant)

    _cast_supper(scenario)

    assert bears.zone is Zone.BATTLEFIELD
    assert giant.zone is Zone.BATTLEFIELD
    assert _chars(scenario, giant).types == (Type.ARTIFACT,)


# -- Faith's Reward (off-set proof) -----------------------------------------


def test_faiths_reward_returns_your_permanents_that_died_this_turn_unchanged():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Faith's Reward"],
            battlefield=["Plains", "Plains", "Plains", "Plains", "Grizzly Bears", "Sol Ring"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    giant = scenario.creature("Hill Giant", "bob")
    for permanent in (bears, ring, giant):
        scenario.game.destroy(permanent)

    scenario.cast_and_resolve(
        "Faith's Reward", *scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")
    )

    assert bears.zone is Zone.BATTLEFIELD
    assert ring.zone is Zone.BATTLEFIELD
    assert Type.CREATURE in _chars(scenario, bears).types  # no type rider
    assert giant.zone is Zone.GRAVEYARD  # bob's graveyard is not "your graveyard"
