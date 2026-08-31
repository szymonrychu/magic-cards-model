"""Crew, and the Vehicles it turns into creatures (CR 702.122, CR 301.7).

CR 702.122a: "Crew is an activated ability of Vehicle cards. 'Crew N' means
'Tap any number of other untapped creatures you control with total power N or
greater: This permanent becomes an artifact creature until end of turn.'"

CR 301.7: "Some artifacts have the subtype 'Vehicle.' Most Vehicles have a crew
ability which allows them to become artifact creatures."

The corner cases are where the rule earns its wording:

- **"total power N or greater"** - an aggregate, not one creature per point, so
  exactly enough works and one short is not a cost that can be paid at all.
- **"other untapped creatures you control"** - three separate restrictions, and
  the "other" is the one that stops a Vehicle crewing itself once something
  else has already made it a creature.
- **No `{T}` in the cost.** Crew is the *Vehicle's* ability and the Vehicle is
  not what taps, so CR 302.6/CR 602.5a - which are about a creature's own `{T}`
  abilities - restrict neither the Vehicle nor the creatures crewing it. A
  Vehicle that entered this turn can be crewed by a creature that entered this
  turn. What that Vehicle still cannot do is attack, because CR 508.1a asks
  about continuous control of the permanent, not about how long it has been a
  creature.
- **CR 301.7b**: "If a Vehicle becomes a creature, it immediately has its
  printed power and toughness."
- **"until end of turn"**, which CR 500.5b sends to CR 514.2 and CR 703.4p:
  the cleanup step, not the end step.

Every CR number here was looked up with `knowledge_search(type="rules")` in the
session that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import crew_activation
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from tests.scenarios.harness import Scenario


def board(*extra: str) -> Scenario:
    """Consulate Dreadnought is Crew 6 and prints nothing else at all, so every
    assertion below is about crew and never about the Vehicle's own text."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[
                "Consulate Dreadnought",
                "Grizzly Bears",
                "Grizzly Bears",
                "Grizzly Bears",
                *extra,
            ],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def crew(scenario, vehicle, *creatures, username="alice"):
    """Activate a Vehicle's crew ability, pay it, and let it resolve."""
    activation = crew_activation(scenario.game, vehicle, list(creatures), username)
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()
    activation.resolve()
    return activation


def types_of(scenario, permanent):
    return scenario.game.characteristics_of(permanent).types


def test_crewing_with_exactly_enough_power_makes_it_an_artifact_creature():
    """CR 702.122a: total power 6 for Crew 6 - three 2/2s is exactly enough."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD)
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", "Grizzly Bears", username="alice")

    assert Type.CREATURE not in types_of(scenario, vehicle)

    crew(scenario, vehicle, *bears)

    types = types_of(scenario, vehicle)
    assert Type.CREATURE in types
    assert Type.ARTIFACT in types
    assert all(bear.tapped for bear in bears)


def test_one_short_of_the_crew_number_refuses_and_taps_nothing():
    """CR 702.122a's "total power N **or greater**": two 2/2s make 4, not 6, so
    the activation is illegal and CR 733.1 leaves the board untouched."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD)
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")

    with pytest.raises(ValueError, match="total power 6"):
        crew(scenario, vehicle, *bears)

    assert Type.CREATURE not in types_of(scenario, vehicle)
    assert not any(bear.tapped for bear in bears)


def test_more_power_than_the_crew_number_is_still_legal():
    """ "N or greater" - there is no waste rule and no refund."""
    scenario = board("Serra Angel").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD)
    angel = scenario.creature("Serra Angel", "alice")
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", "Grizzly Bears", username="alice")

    crew(scenario, vehicle, angel, *bears)  # 4 + 2 + 2 + 2 = 10 for Crew 6

    assert Type.CREATURE in types_of(scenario, vehicle)


def test_an_already_tapped_creature_cannot_crew():
    """CR 702.122a taps "other **untapped** creatures you control"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD)
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", "Grizzly Bears", username="alice")
    bears[0].tap()

    with pytest.raises(ValueError, match="already tapped"):
        crew(scenario, vehicle, *bears)

    assert Type.CREATURE not in types_of(scenario, vehicle)
    assert not bears[1].tapped and not bears[2].tapped


def test_the_same_creature_cannot_be_chosen_twice():
    """One creature has one untap to spend (CR 118.3), so naming it twice does
    not add its power twice."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD)
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", "Grizzly Bears", username="alice")

    with pytest.raises(ValueError, match="chosen twice"):
        crew(scenario, vehicle, bears[0], bears[0], bears[1], bears[1])


def test_a_vehicle_cannot_crew_itself():
    """CR 702.122a: "**other** untapped creatures you control". Once one crew
    has made the Dreadnought a creature, it is still not eligible to help crew
    a second Vehicle it happens to be - or itself."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD)
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", "Grizzly Bears", username="alice")
    crew(scenario, vehicle, *bears)

    with pytest.raises(ValueError, match="cannot crew itself"):
        crew_activation(scenario.game, vehicle, [vehicle], "alice")


def test_an_opponents_creature_cannot_crew_your_vehicle():
    """CR 702.122a: "creatures **you control**"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD)
    mine = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")
    theirs = scenario.creature("Grizzly Bears", "bob")

    with pytest.raises(ValueError, match="does not control"):
        crew(scenario, vehicle, *mine, theirs)

    assert not theirs.tapped


def test_crewing_twice_in_a_turn_is_legal_and_taps_a_second_crew():
    """Crew carries no "activate only once each turn" (CR 602.5b), so a player
    with enough creatures may do it again. The second activation is redundant
    on a Vehicle that is already a creature, but it is not illegal."""
    scenario = board("Serra Angel", "Serra Angel").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD)
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", "Grizzly Bears", username="alice")
    angels = scenario.creatures("Serra Angel", "Serra Angel", username="alice")

    crew(scenario, vehicle, *bears)
    crew(scenario, vehicle, *angels)  # 4 + 4 = 8

    assert Type.CREATURE in types_of(scenario, vehicle)
    assert all(angel.tapped for angel in angels)


def test_a_crewed_vehicle_keeps_its_printed_power_and_toughness():
    """CR 301.7a/CR 301.7b: a Vehicle has its printed P/T only while it is a
    creature, and gets them the moment it becomes one."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD)
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", "Grizzly Bears", username="alice")

    crew(scenario, vehicle, *bears)

    assert scenario.game.characteristics_of(vehicle).power_toughness == (7, 11)


def test_an_uncrewed_vehicle_cannot_attack():
    """CR 508.1a declares *creatures* as attackers, and CR 301.7 leaves an
    uncrewed Vehicle a noncreature artifact."""
    scenario = board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD)

    assert not scenario.can_attack(vehicle)


def test_a_crewed_vehicle_attacks_and_deals_its_printed_damage():
    """The whole point of the keyword: crew in the main phase, attack with it."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD)
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", "Grizzly Bears", username="alice")
    crew(scenario, vehicle, *bears)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(vehicle)
    scenario.no_blocks()
    scenario.combat_damage()

    assert vehicle.tapped
    assert scenario.player("bob").life == 13


def test_a_vehicle_that_entered_this_turn_can_be_crewed_but_cannot_attack():
    """Two different rules, and they answer differently.

    Crew has no `{T}` symbol in its cost, so CR 302.6/CR 602.5a - a *creature's*
    activated ability with `{T}` or `{Q}` - never bear on it, and a Vehicle
    played this turn crews fine. Attacking is CR 508.1a's own question, "must
    either have haste or have been controlled by the active player continuously
    since their most recent turn began", and that one it fails.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Consulate Dreadnought"],
            battlefield=["Grizzly Bears", "Grizzly Bears", "Grizzly Bears", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island")
    vehicle = scenario.cast_and_resolve("Consulate Dreadnought", island)
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", "Grizzly Bears", username="alice")

    crew(scenario, vehicle, *bears)
    assert Type.CREATURE in types_of(scenario, vehicle)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert not scenario.can_attack(vehicle)


def test_a_summoning_sick_creature_can_still_crew():
    """CR 302.6 restricts *the creature's own* `{T}` abilities. Crew is the
    Vehicle's ability and tapping the creature is a cost of it, so a creature
    that arrived this turn crews perfectly well."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Serra Angel"],
            battlefield=[
                "Consulate Dreadnought",
                "Grizzly Bears",
                "Plains",
                "Plains",
                "Plains",
                "Plains",
                "Plains",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains", "Plains")
    angel = scenario.cast_and_resolve("Serra Angel", *sources)
    assert angel.is_summoning_sick(scenario.game)

    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "alice")
    crew(scenario, vehicle, angel, bears)  # 4 + 2 = 6

    assert Type.CREATURE in types_of(scenario, vehicle)
    assert angel.tapped


def test_the_vehicle_stops_being_a_creature_in_the_cleanup_step():
    """CR 500.5b sends "until end of turn" to CR 514.2, and CR 703.4p performs
    it in the cleanup step - not at the end step."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD)
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", "Grizzly Bears", username="alice")
    crew(scenario, vehicle, *bears)

    scenario.start_at(Step.END_STEP)
    assert Type.CREATURE in types_of(scenario, vehicle), "the end step is not the cleanup step"

    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()

    assert Type.CREATURE not in types_of(scenario, vehicle)
    assert Type.ARTIFACT in types_of(scenario, vehicle), "it was always an artifact"


def test_the_crew_ability_uses_the_stack_and_can_be_responded_to():
    """Crew is an ordinary activated ability (CR 702.122a, CR 602.2): not a
    mana ability, so it waits on the stack, and the Vehicle is not a creature
    until it resolves."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD)
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", "Grizzly Bears", username="alice")

    activation = crew_activation(scenario.game, vehicle, bears, "alice")
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()

    assert scenario.stack_names() == ["Consulate Dreadnought's activated ability"]
    assert all(bear.tapped for bear in bears), "the cost is paid on activation (CR 602.2b)"
    assert Type.CREATURE not in types_of(scenario, vehicle)

    activation.resolve()
    assert Type.CREATURE in types_of(scenario, vehicle)


def test_cancelling_the_activation_untaps_the_crew():
    """CR 733.1: an action that cannot be completed is reversed in full and any
    payments already made are cancelled."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD)
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", "Grizzly Bears", username="alice")

    activation = crew_activation(scenario.game, vehicle, bears, "alice")
    activation.begin_paying()
    activation.payment.pay()
    assert all(bear.tapped for bear in bears)

    activation.cancel()

    assert not any(bear.tapped for bear in bears)
    assert Type.CREATURE not in types_of(scenario, vehicle)


def test_crew_reads_power_off_the_board_not_off_the_printing():
    """CR 613.5: characteristics are what the layer system currently says they
    are, so a pumped 2/2 crews for more than 2. Giant Growth's +3/+3 makes two
    bears reach Crew 6 where three were needed before."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Giant Growth"],
            battlefield=[
                "Consulate Dreadnought",
                "Grizzly Bears",
                "Grizzly Bears",
                "Forest",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")
    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_and_resolve("Giant Growth", forest, targets=[bears[0]])

    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD)
    crew(scenario, vehicle, *bears)  # 5 + 2 = 7

    assert Type.CREATURE in types_of(scenario, vehicle)


def test_a_vehicle_that_left_the_battlefield_is_not_made_a_creature():
    """CR 400.7: an object that changes zones is a new object, so the ability
    resolving after its Vehicle has gone does nothing to what came back."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD)
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", "Grizzly Bears", username="alice")

    activation = crew_activation(scenario.game, vehicle, bears, "alice")
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()

    scenario.game.destroy(vehicle)
    activation.resolve()

    assert vehicle.zone is Zone.GRAVEYARD
