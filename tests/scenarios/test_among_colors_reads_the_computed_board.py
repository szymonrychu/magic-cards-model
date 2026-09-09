"""`among_colors` (CR 106.5's "add one mana of any color among ... you
control") surveys the computed board (CR 613.5), not the printed type line.

Mox Amber: "{T}: Add one mana of any color among legendary creatures and
planeswalkers you control." The colour is undefined - and the ability
produces nothing - unless some permanent alice controls is both legendary
(CR 205.4a) and a creature or planeswalker (CR 205.2a) right now.
`test_cost_payment_restrictions.py` already covers that survey against the
printed board (an ordinary legendary creature, present or absent, defines the
colour or does not). This file is the one case that board can never put in
front of it: a permanent whose *card types* differ from what is printed.

Parhelion II is a white "Legendary Artifact — Vehicle" with Crew 4
(CR 702.122a: "This permanent becomes an artifact creature until end of
turn"). Printed, it is legendary but never a creature - `CardState.types`
says so before and after crewing, since crew is a runtime continuous effect
(layer 4, CR 613.1d) with nothing on the type line to show for it. Computed,
it is a legendary creature for exactly as long as the crew effect lasts. Mox
Amber's survey has to track that transition, not the permanent's printed
shape, or it either offers white a turn early (before crewing) or refuses it
a turn late (after crewing, if the read were pinned to the printed board
instead).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import crew_activation
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from tests.scenarios.harness import Scenario


def _board():
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Swords to Plowshares"],
            battlefield=["Mox Amber", "Parhelion II", "Grizzly Bears", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def _crew_parhelion(scenario):
    vehicle = scenario.find("Parhelion II", Zone.BATTLEFIELD, "alice")
    crewing = scenario.game.permanents_controlled_by("alice")
    bears = [state for state in crewing if state.name == "Grizzly Bears"]
    activation = crew_activation(scenario.game, vehicle, bears, "alice")
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()
    activation.resolve()
    return vehicle


def test_an_uncrewed_vehicle_does_not_define_a_colour_for_mox_amber():
    """Printed and computed agree here: Parhelion II is not a creature yet,
    so it is not a legendary creature either, and nothing else alice controls
    is legendary. Mox Amber has no colour to add (CR 106.5), so paying
    Swords to Plowshares' {W} out of it fails.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vehicle = scenario.find("Parhelion II", Zone.BATTLEFIELD, "alice")
    assert Type.CREATURE not in scenario.game.characteristics_of(vehicle).types

    target = scenario.creature("Grizzly Bears", "bob")
    casting = scenario.cast("Swords to Plowshares", targets=[target])
    payment = casting.begin_paying()
    amber = scenario.find("Mox Amber", Zone.BATTLEFIELD, "alice")

    with pytest.raises(ValueError):
        scenario.auto_pay(payment, "alice")

    assert not amber.tapped
    casting.cancel()


def test_a_crewed_vehicle_defines_its_colour_for_mox_amber():
    """Once crewed, Parhelion II is a legendary creature by the computed board
    (CR 613.1d, layer 4) - `CardState.types` still says otherwise - and it is
    white, so Mox Amber can now pay Swords to Plowshares' {W}.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vehicle = _crew_parhelion(scenario)
    assert scenario.game.characteristics_of(vehicle).is_creature
    assert Type.CREATURE not in vehicle.types, "the printed type line still says Vehicle only"

    target = scenario.creature("Grizzly Bears", "bob")
    casting = scenario.cast("Swords to Plowshares", targets=[target])
    payment = casting.begin_paying()
    amber = scenario.find("Mox Amber", Zone.BATTLEFIELD, "alice")
    scenario.auto_pay(payment, "alice")
    spell = scenario.put_on_stack(casting)

    assert amber.tapped
    assert spell.zone is Zone.STACK
