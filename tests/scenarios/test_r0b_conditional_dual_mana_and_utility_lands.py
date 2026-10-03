"""Utility lands around a mana ability or an enters-the-battlefield choice:

- Temple of Enlightenment: enters tapped (CR 614.1d), scry 1 trigger (CR
  701.22a), taps for {W} or {U} (CR 605.1a).
- Selesnya Sanctuary: bounce land - enters tapped, its ETB returns a land you
  control to hand (itself is a legal choice, CR 608.2d: no target), taps for
  {G}{W}.
- Hidden Lair / Gleaming Bastion: the coloured mana ability is legal only if
  the land entered this turn OR you control a basic land; {C} is always
  available (CR 602.5b's "Activate only if" restriction on a mana ability).
- Fell the Profane // Fell Mire: the instant destroys a creature or planeswalker
  from hand; the land face asks to pay 3 life or enter tapped (CR 712.12,
  CR 614.12a), and below 3 life paying is not a legal choice (CR 119.4).

CR numbers were looked up with `mise run rules:find <n>`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Type, Zone
from tests.scenarios.harness import Scenario


def _board(hand=(), battlefield=(), library=("Forest", "Island", "Swamp"), bob=()):
    scenario = (
        Scenario()
        .player("alice", hand=list(hand), battlefield=list(battlefield), library=list(library))
        .player("bob", battlefield=list(bob), library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- Temple of Enlightenment --------------------------------------------------


def test_temple_of_enlightenment_enters_tapped():
    scenario = _board(["Temple of Enlightenment"], ["Forest", "Island", "Swamp", "Mountain"])

    assert scenario.play_land("Temple of Enlightenment").tapped is True


def test_temple_of_enlightenment_scry_one_can_bottom_the_top_card():
    scenario = _board(["Temple of Enlightenment"], library=["Forest", "Island", "Swamp"])
    top = scenario.top_of_library()[0]
    scenario.play_land("Temple of Enlightenment")
    scenario.game.put_triggers_on_stack()
    scenario.scry_bottoming(top)
    scenario.resolve_top()

    library = scenario.player("alice").library
    assert library[-1] is top
    assert library[0] is not top


def test_temple_of_enlightenment_scry_one_can_keep_the_top_card():
    scenario = _board(["Temple of Enlightenment"], library=["Forest", "Island", "Swamp"])
    top = scenario.top_of_library()[0]
    scenario.play_land("Temple of Enlightenment")
    scenario.game.put_triggers_on_stack()
    scenario.scry_keeping_everything_on_top()
    scenario.resolve_top()

    assert scenario.player("alice").library[0] is top


def test_temple_of_enlightenment_scry_with_an_empty_library_is_harmless():
    scenario = _board(["Temple of Enlightenment"], library=[])
    scenario.play_land("Temple of Enlightenment")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert scenario.player("alice").library == []


@pytest.mark.parametrize("color", [Color.WHITE, Color.BLUE])
def test_temple_of_enlightenment_taps_for_white_or_blue(color):
    scenario = _board(battlefield=["Temple of Enlightenment"])
    temple = scenario.find("Temple of Enlightenment", Zone.BATTLEFIELD)

    scenario.activate(temple, color=color)

    assert scenario.player("alice").mana_pool.floating == {color: 1}


def test_temple_of_enlightenment_refuses_a_colour_it_does_not_make():
    scenario = _board(battlefield=["Temple of Enlightenment"])
    temple = scenario.find("Temple of Enlightenment", Zone.BATTLEFIELD)

    with pytest.raises(ValueError):
        scenario.activate(temple, color=Color.RED)


# -- Selesnya Sanctuary -------------------------------------------------------


def test_selesnya_sanctuary_enters_tapped_and_returns_another_land():
    scenario = _board(["Selesnya Sanctuary"], ["Forest", "Plains"])
    sanctuary = scenario.play_land("Selesnya Sanctuary")
    scenario.game.put_triggers_on_stack()
    forest = scenario.find("Forest", Zone.BATTLEFIELD)
    scenario.will_choose_cards(forest, source="Selesnya Sanctuary")
    scenario.resolve_top()

    assert sanctuary.tapped
    assert sanctuary.zone is Zone.BATTLEFIELD
    assert forest.zone is Zone.HAND


def test_selesnya_sanctuary_may_return_itself():
    scenario = _board(["Selesnya Sanctuary"], ["Forest"])
    sanctuary = scenario.play_land("Selesnya Sanctuary")
    scenario.game.put_triggers_on_stack()
    scenario.will_choose_cards(sanctuary, source="Selesnya Sanctuary")
    scenario.resolve_top()

    assert sanctuary.zone is Zone.HAND
    assert scenario.find("Forest", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD


def test_selesnya_sanctuary_cannot_return_an_opponents_land():
    scenario = _board(["Selesnya Sanctuary"], bob=["Swamp"])
    scenario.play_land("Selesnya Sanctuary")
    scenario.game.put_triggers_on_stack()
    swamp = scenario.find("Swamp", Zone.BATTLEFIELD, "bob")
    scenario.will_choose_cards(swamp, source="Selesnya Sanctuary")
    with pytest.raises(ValueError):
        scenario.resolve_top()

    assert swamp.zone is Zone.BATTLEFIELD


def test_selesnya_sanctuary_taps_for_green_and_white_together():
    scenario = _board(battlefield=["Selesnya Sanctuary"])
    sanctuary = scenario.find("Selesnya Sanctuary", Zone.BATTLEFIELD)

    scenario.activate(sanctuary)

    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 1, Color.WHITE: 1}


# -- Hidden Lair / Gleaming Bastion -------------------------------------------

DUALS = [
    ("Hidden Lair", {Color.BLUE, Color.BLACK}),
    ("Gleaming Bastion", {Color.WHITE, Color.BLUE}),
]


def _refusal(scenario, land, index):
    return scenario.why_cannot_activate(scenario.find(land, Zone.BATTLEFIELD), index)


def _coloured_index(scenario, land):
    permanent = scenario.find(land, Zone.BATTLEFIELD)
    for index, ability in enumerate(scenario.game.activated_abilities(permanent)):
        if "Activate only" in ability.raw:
            return index
    raise AssertionError("no conditional mana ability")


@pytest.mark.parametrize(("land", "colors"), DUALS)
def test_colourless_mana_is_always_available(land, colors):
    scenario = _board(battlefield=[land, "Grizzly Bears"])
    permanent = scenario.find(land, Zone.BATTLEFIELD)
    coloured = _coloured_index(scenario, land)
    colourless = 1 - coloured

    assert _refusal(scenario, land, coloured) is not None
    assert _refusal(scenario, land, colourless) is None
    scenario.activate(permanent, index=colourless)
    assert scenario.player("alice").mana_pool.floating == {Color.COLORLESS: 1}


@pytest.mark.parametrize(("land", "colors"), DUALS)
def test_coloured_mana_is_refused_with_no_basic_land_and_not_entered_this_turn(land, colors):
    scenario = _board(battlefield=[land, "Watery Grave"])
    reason = _refusal(scenario, land, _coloured_index(scenario, land))

    assert reason is not None


@pytest.mark.parametrize(("land", "colors"), DUALS)
def test_coloured_mana_is_available_with_a_basic_land(land, colors):
    scenario = _board(battlefield=[land, "Mountain"])
    index = _coloured_index(scenario, land)
    permanent = scenario.find(land, Zone.BATTLEFIELD)

    assert _refusal(scenario, land, index) is None
    color = sorted(colors, key=lambda c: c.value)[0]
    scenario.activate(permanent, index=index, color=color)
    assert scenario.player("alice").mana_pool.floating == {color: 1}


@pytest.mark.parametrize(("land", "colors"), DUALS)
def test_coloured_mana_is_available_the_turn_the_land_entered(land, colors):
    scenario = _board(hand=[land], battlefield=["Watery Grave"])
    permanent = scenario.play_land(land)
    index = _coloured_index(scenario, land)

    assert _refusal(scenario, land, index) is None
    color = sorted(colors, key=lambda c: c.value)[0]
    scenario.activate(permanent, index=index, color=color)
    assert scenario.player("alice").mana_pool.floating == {color: 1}


@pytest.mark.parametrize(("land", "colors"), DUALS)
def test_coloured_mana_is_lost_again_next_turn_without_a_basic(land, colors):
    scenario = _board(hand=[land], battlefield=["Watery Grave"])
    scenario.play_land(land)
    index = _coloured_index(scenario, land)
    assert _refusal(scenario, land, index) is None

    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # bob's untap step
    scenario.advance()  # his upkeep
    assert _refusal(scenario, land, index) is not None


@pytest.mark.parametrize(("land", "colors"), DUALS)
def test_an_opponents_basic_land_does_not_count(land, colors):
    scenario = _board(battlefield=[land], bob=["Mountain"])

    assert _refusal(scenario, land, _coloured_index(scenario, land)) is not None


@pytest.mark.parametrize(("land", "colors"), DUALS)
def test_coloured_mana_rejects_a_colour_the_land_does_not_make(land, colors):
    scenario = _board(battlefield=[land, "Mountain"])
    index = _coloured_index(scenario, land)
    permanent = scenario.find(land, Zone.BATTLEFIELD)

    with pytest.raises(ValueError):
        scenario.activate(permanent, index=index, color=Color.RED)


# -- Fell the Profane // Fell Mire ---------------------------------------------


def test_fell_the_profane_destroys_a_creature():
    scenario = _board(
        hand=["Fell the Profane"],
        battlefield=["Swamp", "Swamp", "Swamp", "Swamp"],
        bob=["Grizzly Bears"],
    )
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")

    scenario.cast_and_resolve(
        "Fell the Profane",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp"),
        targets=[bears],
    )

    assert bears.zone is Zone.GRAVEYARD


def test_fell_the_profane_destroys_a_planeswalker():
    scenario = _board(
        hand=["Fell the Profane"],
        battlefield=["Swamp", "Swamp", "Swamp", "Swamp"],
        bob=["Chandra, Torch of Defiance"],
    )
    chandra = scenario.find("Chandra, Torch of Defiance", Zone.BATTLEFIELD, "bob")

    scenario.cast_and_resolve(
        "Fell the Profane",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp"),
        targets=[chandra],
    )

    assert chandra.zone is Zone.GRAVEYARD


def test_fell_the_profane_is_an_instant_castable_on_the_opponents_turn():
    scenario = _board(
        hand=["Fell the Profane"],
        battlefield=["Swamp", "Swamp", "Swamp", "Swamp"],
        bob=["Grizzly Bears"],
    )
    scenario.advance()
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")

    scenario.cast_and_resolve(
        "Fell the Profane",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp"),
        targets=[bears],
    )

    assert bears.zone is Zone.GRAVEYARD


def test_fell_the_profane_cannot_target_a_land_or_artifact():
    scenario = _board(
        hand=["Fell the Profane"],
        battlefield=["Swamp", "Swamp", "Swamp", "Swamp"],
        bob=["Bonesplitter"],
    )
    sword = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "bob")

    with pytest.raises(ValueError):
        scenario.cast_and_resolve(
            "Fell the Profane",
            *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp"),
            targets=[sword],
        )


def test_fell_mire_enters_untapped_for_three_life_by_default():
    scenario = _board(hand=["Fell the Profane"])

    mire = scenario.play_land("Fell the Profane")

    assert mire.name == "Fell Mire"
    assert mire.untapped
    assert scenario.player("alice").life == 17


def test_fell_mire_enters_tapped_when_the_life_is_refused():
    scenario = _board(hand=["Fell the Profane"])
    scenario.will_pay_the_life(False)

    mire = scenario.play_land("Fell the Profane")

    assert mire.tapped
    assert scenario.player("alice").life == 20


def test_fell_mire_at_exactly_three_life_may_pay_down_to_zero():
    """CR 119.4: a life total equal to the payment may pay it - to 0 life."""
    scenario = _board(hand=["Fell the Profane"])
    scenario.player("alice").life = 3

    mire = scenario.play_land("Fell the Profane")
    scenario.state_based_actions()

    assert mire.untapped
    assert scenario.player("alice").life == 0


def test_fell_mire_at_two_life_cannot_pay_and_is_never_asked():
    scenario = _board(hand=["Fell the Profane"])
    scenario.player("alice").life = 2

    mire = scenario.play_land("Fell the Profane")

    assert mire.tapped
    assert scenario.player("alice").life == 2


def test_fell_mire_taps_for_black_and_is_not_the_instant():
    scenario = _board(hand=["Fell the Profane"])
    mire = scenario.play_land("Fell the Profane")

    scenario.activate(mire)

    assert scenario.player("alice").mana_pool.floating == {Color.BLACK: 1}
    types = scenario.game.computed_board().of(mire).types
    assert Type.LAND in types
    assert Type.INSTANT not in types
