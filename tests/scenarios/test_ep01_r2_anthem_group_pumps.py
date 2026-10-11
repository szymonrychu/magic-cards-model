"""Scenario: a coloured or typed group pump - "Other green creatures you
control get +1/+1." (Wilt-Leaf Liege, Murkfiend Liege).

CR 611.3a: a static ability's effect "isn't 'locked in'; it applies at any
given moment to whatever its text indicates", so the group is re-read on every
computation. The pump lands in layer 7c (CR 613.4c). "Other" excludes the
source by identity, "you control" excludes the opponent's creatures, and a
creature of two listed colours is in the group once per sentence that names a
colour it has.
"""

from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import token_copy_of
from tests.scenarios.harness import Scenario


def pt(scenario, state):
    chars = scenario.game.characteristics_of(state)
    return chars.power, chars.toughness


def printed(state):
    return int(state.card.power), int(state.card.toughness)


def plus(state, n):
    power, toughness = printed(state)
    return power + n, toughness + n


def board(*alice, bob=()):
    return (
        Scenario()
        .player("alice", battlefield=list(alice))
        .player("bob", battlefield=list(bob))
        .build()
    )


def test_green_and_white_creatures_get_it_and_a_blue_one_does_not():
    scenario = board("Wilt-Leaf Liege", "Grizzly Bears", "Savannah Lions", "Wind Drake")
    bears = scenario.creature("Grizzly Bears")
    lions = scenario.creature("Savannah Lions")
    drake = scenario.creature("Wind Drake")

    assert pt(scenario, bears) == plus(bears, 1)
    assert pt(scenario, lions) == plus(lions, 1)
    assert pt(scenario, drake) == printed(drake)


def test_the_liege_does_not_pump_itself():
    """ "Other": the Liege is green and white and is excluded by identity."""
    scenario = board("Wilt-Leaf Liege")
    liege = scenario.creature("Wilt-Leaf Liege")

    assert pt(scenario, liege) == printed(liege)


def test_two_lieges_pump_each_other_once_per_colour_sentence():
    """Each Liege is green and white: the other's two sentences give +2/+2."""
    scenario = board("Wilt-Leaf Liege", "Wilt-Leaf Liege")
    first, second = scenario.creatures("Wilt-Leaf Liege", "Wilt-Leaf Liege")

    assert pt(scenario, first) == plus(first, 2)
    assert pt(scenario, second) == plus(second, 2)


def test_an_opponents_green_creature_is_outside_the_group():
    scenario = board("Wilt-Leaf Liege", bob=["Grizzly Bears"])
    theirs = scenario.creature("Grizzly Bears", "bob")

    assert pt(scenario, theirs) == printed(theirs)


def test_a_green_token_that_arrives_later_is_pumped():
    """CR 611.3a: the group is whatever the text indicates now."""
    scenario = board("Wilt-Leaf Liege", "Grizzly Bears")
    bears = scenario.creature("Grizzly Bears")
    (token,) = token_copy_of(scenario.game, bears, "alice")

    assert pt(scenario, token) == plus(bears, 1)


def test_the_pump_stops_when_the_liege_leaves():
    """CR 604.2: active only as long as the permanent with the ability is on
    the battlefield."""
    scenario = board("Wilt-Leaf Liege", "Grizzly Bears")
    liege = scenario.creature("Wilt-Leaf Liege")
    bears = scenario.creature("Grizzly Bears")
    assert pt(scenario, bears) == plus(bears, 1)

    scenario.game.put_into_graveyard(liege)

    assert liege.zone is Zone.GRAVEYARD
    assert pt(scenario, bears) == printed(bears)


def test_murkfiend_liege_pumps_green_and_blue_but_not_white():
    scenario = board("Murkfiend Liege", "Grizzly Bears", "Wind Drake", "Savannah Lions")
    bears = scenario.creature("Grizzly Bears")
    drake = scenario.creature("Wind Drake")
    lions = scenario.creature("Savannah Lions")
    liege = scenario.creature("Murkfiend Liege")

    assert pt(scenario, bears) == plus(bears, 1)
    assert pt(scenario, drake) == plus(drake, 1)
    assert pt(scenario, lions) == printed(lions)
    assert pt(scenario, liege) == printed(liege)


def test_the_pump_stacks_with_a_plus_one_counter():
    """CR 613.4c: the Liege's +1/+1 and a +1/+1 counter both modify the
    printed value in layer 7c."""
    scenario = board("Wilt-Leaf Liege", "Grizzly Bears")
    bears = scenario.creature("Grizzly Bears")
    bears.add_counters(Counter.PLUS_ONE, 1)

    assert pt(scenario, bears) == plus(bears, 2)
