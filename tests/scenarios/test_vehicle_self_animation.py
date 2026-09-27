"""A Vehicle that animates itself without crewing, and a Vehicle whose power
is a characteristic-defining ability.

- Bladewheel Chariot (the back face of Spring-Loaded Sawblades): "Tap two
  other untapped artifacts you control: This Vehicle becomes an artifact
  creature until end of turn." Honeymoon Hearse ("Tap two untapped creatures
  you control: This Vehicle becomes an artifact creature until end of
  turn.") is the second printing of the effect, on a creature-tapping cost.
- Lumbering Worldwagon: "This Vehicle's power is equal to the number of lands
  you control." Zendikar Incarnate ("... power is equal to the number of
  lands you control.") is the same count on a creature.

Rules, each read with `mise run rules:find` in the session that wrote this:

- **CR 613.1d** - "becomes an artifact creature" is a layer 4 type change,
  and it adds: the Vehicle stays an artifact and a Vehicle.
- **CR 301.7a / 301.7b** - a Vehicle has its printed power and toughness only
  while it is a creature, and immediately has them once it becomes one: no
  layer 7b set is involved, so a CR 613.4c pump stacks on top.
- **CR 208.3 / 208.3a** - a noncreature permanent has no power or toughness,
  and an effect that sets or modifies it does nothing until it is one.
- **CR 613.4a / 604.3** - a power-defining characteristic-defining ability
  applies in layer 7a, recomputed whenever the board is (CR 611.3a).
- **CR 118.3** - a permanent that is already tapped can't be tapped to pay a
  cost; "other" keeps the Vehicle itself out of its own cost.
- **CR 514.2** - "until end of turn" effects end in the cleanup step.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import craft_activation, crew_activation
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario

CHARIOT = "Bladewheel Chariot"


def _chariot_board(*others: str, bob=()) -> object:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Spring-Loaded Sawblades", "Ornithopter", *["Plains"] * 4, *others],
            library=["Plains"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sawblades = scenario.find("Spring-Loaded Sawblades", Zone.BATTLEFIELD, "alice")
    ornithopter = scenario.creature("Ornithopter", "alice")
    activation = craft_activation(scenario.game, sawblades, "alice", [ornithopter])
    payment = activation.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Plains"] * 4, username="alice"))
    activation.activate()
    while scenario.game.stack:
        scenario.pass_until_resolved()
    return scenario


def _chariot(scenario):
    chariot = scenario.find(CHARIOT, Zone.BATTLEFIELD, "alice")
    assert chariot.transformed
    return chariot


def _animate_chariot(scenario, *tapped: str):
    chariot = _chariot(scenario)
    artifacts = [scenario.find(name, Zone.BATTLEFIELD, "alice") for name in tapped]
    scenario.activate(chariot, index=0, tapping_for_cost=artifacts)
    scenario.pass_until_resolved()
    return chariot


def test_the_crafted_chariot_is_a_noncreature_vehicle():
    """CR 301.7a: a Vehicle that is not a creature."""
    scenario = _chariot_board("Sol Ring", "Mind Stone")
    computed = scenario.game.computed_board().of(_chariot(scenario))
    assert not computed.is_creature
    assert "Vehicle" in computed.subtypes


def test_tapping_two_other_artifacts_makes_it_a_five_five_artifact_creature():
    scenario = _chariot_board("Sol Ring", "Mind Stone")
    chariot = _animate_chariot(scenario, "Sol Ring", "Mind Stone")

    computed = scenario.game.computed_board().of(chariot)
    assert computed.is_creature
    assert Type.ARTIFACT in computed.types, "CR 613.1d adds, it keeps artifact"
    assert "Vehicle" in computed.subtypes
    assert (computed.power, computed.toughness) == (5, 5), "CR 301.7b: printed P/T"
    assert scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice").tapped
    assert scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice").tapped
    assert not chariot.tapped


def test_the_chariot_cannot_tap_itself_for_its_own_cost():
    """ "other": with only one other artifact the cost cannot be paid."""
    scenario = _chariot_board("Sol Ring")
    chariot = _chariot(scenario)
    with pytest.raises(ValueError):
        scenario.activate(
            chariot,
            index=0,
            tapping_for_cost=[scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice"), chariot],
        )
    assert not scenario.game.computed_board().of(chariot).is_creature


def test_an_already_tapped_artifact_cannot_pay_the_cost():
    """CR 118.3."""
    scenario = _chariot_board("Sol Ring", "Mind Stone")
    chariot = _chariot(scenario)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    ring.tapped = True
    with pytest.raises(ValueError):
        scenario.activate(
            chariot,
            index=0,
            tapping_for_cost=[ring, scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")],
        )


def test_a_pump_stacks_on_the_printed_power_and_toughness():
    """CR 301.7b / 613.4c: no layer 7b set overwrites Glorious Anthem."""
    scenario = _chariot_board("Sol Ring", "Mind Stone", "Glorious Anthem")
    chariot = _animate_chariot(scenario, "Sol Ring", "Mind Stone")
    computed = scenario.game.computed_board().of(chariot)
    assert (computed.power, computed.toughness) == (6, 6)


def test_the_animation_ends_in_the_cleanup_step():
    scenario = _chariot_board("Sol Ring", "Mind Stone")
    chariot = _animate_chariot(scenario, "Sol Ring", "Mind Stone")
    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    assert not scenario.game.computed_board().of(chariot).is_creature


def test_the_chariot_classifies_as_handled_in_both_forms():
    for name in ("Spring-Loaded Sawblades // Bladewheel Chariot", "Honeymoon Hearse"):
        clauses = [c for c in classify_clauses(card(name)) if c.text]
        assert {c.category for c in clauses} == {HANDLED}, name


# -- Honeymoon Hearse: the same effect on a creature-tapping cost -------------


def _hearse_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Honeymoon Hearse", "Grizzly Bears", "Llanowar Elves"],
            library=["Plains"] * 5,
        )
        .player("bob", library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_hearse_becomes_a_five_five_artifact_creature_with_trample():
    scenario = _hearse_board()
    hearse = scenario.find("Honeymoon Hearse", Zone.BATTLEFIELD, "alice")
    scenario.activate(
        hearse,
        index=0,
        tapping_for_cost=scenario.creatures("Grizzly Bears", "Llanowar Elves", username="alice"),
    )
    scenario.pass_until_resolved()
    computed = scenario.game.computed_board().of(hearse)
    assert computed.is_creature and Type.ARTIFACT in computed.types
    assert (computed.power, computed.toughness) == (5, 5)
    assert computed.has_ability("Trample")


# -- Lumbering Worldwagon: "This Vehicle's power is equal to ..." -------------


def _wagon_board(lands: int):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Lumbering Worldwagon", "Serra Angel", *["Forest"] * lands],
            hand=["Forest"],
            library=["Plains"] * 5,
        )
        .player("bob", battlefield=["Mountain"] * 5, library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _crew(scenario, vehicle, *crew):
    activation = crew_activation(scenario.game, vehicle, list(crew), "alice")
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()
    activation.resolve()


def test_an_uncrewed_worldwagon_is_not_a_creature_and_cannot_attack():
    """CR 208.3a: the CDA exists but does nothing until it is a creature."""
    scenario = _wagon_board(3)
    wagon = scenario.find("Lumbering Worldwagon", Zone.BATTLEFIELD, "alice")
    assert not scenario.game.computed_board().of(wagon).is_creature
    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers
    assert not scenario.can_attack(wagon)


def test_a_crewed_worldwagon_has_power_equal_to_its_controllers_lands():
    """CR 613.4a: 7a sets power to 3 lands; toughness stays the printed 4."""
    scenario = _wagon_board(3)
    wagon = scenario.find("Lumbering Worldwagon", Zone.BATTLEFIELD, "alice")
    _crew(scenario, wagon, scenario.creature("Serra Angel", "alice"))
    computed = scenario.game.computed_board().of(wagon)
    assert computed.is_creature
    assert (computed.power, computed.toughness) == (3, 4)


def test_the_worldwagon_count_follows_a_land_entering():
    """CR 611.3a: recomputed, not locked in."""
    scenario = _wagon_board(3)
    wagon = scenario.find("Lumbering Worldwagon", Zone.BATTLEFIELD, "alice")
    _crew(scenario, wagon, scenario.creature("Serra Angel", "alice"))
    scenario.play_land("Forest")
    assert scenario.game.power_of(wagon) == 4


def test_the_worldwagon_counts_no_opponents_lands():
    scenario = _wagon_board(0)
    wagon = scenario.find("Lumbering Worldwagon", Zone.BATTLEFIELD, "alice")
    _crew(scenario, wagon, scenario.creature("Serra Angel", "alice"))
    assert scenario.game.power_of(wagon) == 0


def test_zendikar_incarnate_reads_the_same_count():
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Zendikar Incarnate", *["Forest"] * 5], library=["Plains"] * 5
        )
        .player("bob", library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    incarnate = scenario.creature("Zendikar Incarnate", "alice")
    assert (scenario.game.power_of(incarnate), scenario.game.toughness_of(incarnate)) == (5, 4)


def test_the_worldwagon_classifies_as_handled():
    clauses = [c for c in classify_clauses(card("Lumbering Worldwagon")) if c.text]
    assert {c.category for c in clauses} == {HANDLED}
