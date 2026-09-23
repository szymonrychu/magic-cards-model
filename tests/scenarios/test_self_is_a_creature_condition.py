"""Scenario: "if `<this object>` is a creature" - a condition about the ability's
own source being a creature right now (CR 613.5's computed type, not the
printed one).

Hydro-Man, Fluid Felon: "Whenever you cast a blue spell, if Hydro-Man is a
creature, he gets +1/+1 until end of turn." - an intervening if (CR 603.4):
checked when the spell is cast, so while his own end-step ability has made
him a land ("Until your next turn, he becomes a land ... (He's not a creature
during that time.)") the trigger does not trigger at all, and records no
engine gap either. "He" is the legendary card's own pronoun for itself.

Flywheel Racer's "{T}: Add one mana of any color. Activate only if this
permanent is a creature." is the second printing: the same condition as an
activation restriction (CR 602.5), with CR 700.7's "this permanent" as the
subject instead of a name - a Vehicle is a creature only while crewed
(CR 301.7).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import crew_activation
from magic_cards_model.models import Color, Type, Zone
from tests.scenarios.harness import Scenario


def _hydro_board(*hand: str) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=["Hydro-Man, Fluid Felon", "Island", "Island", "Mountain"],
            library=["Island"] * 6,
        )
        .player("bob", library=["Island"] * 6)
        .build()
    )


def _hydro(scenario: Scenario):
    return scenario.creature("Hydro-Man, Fluid Felon", "alice")


def test_casting_a_blue_spell_pumps_him():
    scenario = _hydro_board("Opt")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island", username="alice")[:1]
    scenario.cast_onto_stack("Opt", island, username="alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names()[-1] == "Hydro-Man, Fluid Felon's triggered ability"

    scenario.resolve_top()

    board = scenario.game.computed_board()
    assert board.of(_hydro(scenario)).power_toughness == (3, 3)
    assert scenario.game.intervening_if_notices == []


def test_two_blue_spells_pump_him_twice():
    scenario = _hydro_board("Opt", "Opt")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for _ in range(2):
        (island,) = scenario.untapped_sources("Island", username="alice")[:1]
        scenario.cast_onto_stack("Opt", island, username="alice")
        scenario.game.put_triggers_on_stack()
        scenario.resolve_top()
        scenario.resolve_top()

    assert scenario.game.computed_board().of(_hydro(scenario)).power_toughness == (4, 4)


def test_a_non_blue_spell_does_not_trigger():
    scenario = _hydro_board("Lightning Bolt")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Lightning Bolt"]


def test_the_pump_ends_at_end_of_turn():
    scenario = _hydro_board("Opt")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island", username="alice")[:1]
    scenario.cast_onto_stack("Opt", island, username="alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    scenario.resolve_top()

    while scenario.turn.active_player != "bob":
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
    hydro = _hydro(scenario)
    # His own end-step ability made him a land until Alice's next turn.
    assert not scenario.game.computed_board().of(hydro).is_creature
    assert Type.LAND in scenario.game.computed_board().of(hydro).types


def _to_bobs_turn(scenario: Scenario) -> None:
    """Walk through Alice's end step (resolving Hydro-Man's own land ability)
    into Bob's main phase."""
    while not (scenario.turn.active_player == "bob" and scenario.step is Step.PRECOMBAT_MAIN):
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


def test_while_he_is_a_land_a_blue_spell_does_not_trigger():
    """CR 603.4: the condition is false as the event occurs, so the ability
    does not trigger - and that is a legal "nothing happened", not an engine
    gap (no `InterveningIfNotice`)."""
    scenario = _hydro_board("Opt")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _to_bobs_turn(scenario)
    hydro = _hydro(scenario)
    assert not scenario.game.computed_board().of(hydro).is_creature
    assert not hydro.tapped, "his end-step ability untapped him"

    scenario.pass_priority("bob")
    (island,) = scenario.untapped_sources("Island", username="alice")[:1]
    scenario.cast_onto_stack("Opt", island, username="alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Opt"]
    assert scenario.game.intervening_if_notices == []


def test_while_he_is_a_land_he_taps_for_blue():
    scenario = _hydro_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _to_bobs_turn(scenario)
    hydro = _hydro(scenario)
    scenario.pass_priority("bob")

    scenario.activate(hydro, username="alice")

    assert scenario.player("alice").mana_pool.floating == {Color.BLUE: 1}


def test_on_his_controllers_next_turn_he_is_a_creature_again_and_pumps():
    scenario = _hydro_board("Opt")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while not (scenario.turn.active_player == "alice" and scenario.turn.turn_number > 1):
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
    while scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()
    hydro = _hydro(scenario)
    assert scenario.game.computed_board().of(hydro).is_creature

    (island,) = scenario.untapped_sources("Island", username="alice")[:1]
    scenario.cast_onto_stack("Opt", island, username="alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert scenario.game.computed_board().of(hydro).power_toughness == (3, 3)


# -- Flywheel Racer: "Activate only if this permanent is a creature." -------


def _racer_board() -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Flywheel Racer", "Grizzly Bears"], library=["Island"] * 3)
        .player("bob", library=["Island"] * 3)
        .build()
    )


def test_an_uncrewed_vehicle_cannot_tap_for_mana():
    scenario = _racer_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    racer = scenario.find("Flywheel Racer", Zone.BATTLEFIELD)

    assert scenario.why_cannot_activate(racer, 0) is not None
    with pytest.raises(ValueError):
        scenario.activate(racer, color=Color.RED)


def test_a_crewed_vehicle_taps_for_mana():
    scenario = _racer_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    racer = scenario.find("Flywheel Racer", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "alice")
    activation = crew_activation(scenario.game, racer, [bears], "alice")
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()
    activation.resolve()
    assert scenario.game.computed_board().of(racer).is_creature

    assert scenario.why_cannot_activate(racer, 0) is None
    scenario.activate(racer, color=Color.RED)

    assert scenario.player("alice").mana_pool.floating == {Color.RED: 1}
