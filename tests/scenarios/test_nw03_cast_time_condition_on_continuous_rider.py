"""'... gets an additional -3/-3 if you controlled a Faerie as you cast this spell'.

Faerie Fencing ({X}{B}): "Target creature gets -X/-X until end of turn.
That creature gets an additional -3/-3 until end of turn if you controlled a
Faerie as you cast this spell."

CR 601.2i: the spell becomes cast and "as you cast this spell" fixes the
question at that moment, a fact recorded on the cast
(`CastRecord.controlled_subtypes_as_cast`), not a board check once the spell
has left the stack. The rider is a continuous effect (layers path), so its
condition must read the cast record, the same as the non-layer gates.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

_LANDS = ["Swamp"] * 2


def _board(alice_battlefield=(), hand=("Faerie Fencing",)):
    scenario = (
        Scenario()
        .player("alice", hand=list(hand), battlefield=_LANDS + list(alice_battlefield))
        .player("bob", battlefield=["Colossal Dreadmaw"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature("Colossal Dreadmaw", "bob")


def _cast(scenario, target):
    casting = scenario.cast("Faerie Fencing", targets=[target])
    casting.determine_cost(x_value=1)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*_LANDS))
    return scenario.put_on_stack(casting)


def _toughness(scenario, creature):
    return scenario.game.characteristics_of(creature).toughness


def test_without_a_faerie_only_x():
    scenario, target = _board()
    _cast(scenario, target)
    scenario.resolve_top()
    assert _toughness(scenario, target) == 5


def test_a_faerie_controlled_as_cast_adds_three_more():
    scenario, target = _board(["Faerie Miscreant"])
    _cast(scenario, target)
    scenario.resolve_top()
    assert _toughness(scenario, target) == 2


def test_a_faerie_that_leaves_before_resolution_still_counts():
    scenario, target = _board(["Faerie Miscreant"])
    faerie = scenario.find("Faerie Miscreant", Zone.BATTLEFIELD, "alice")
    _cast(scenario, target)
    scenario.game.destroy(faerie)
    assert faerie.zone is Zone.GRAVEYARD
    scenario.resolve_top()
    assert _toughness(scenario, target) == 2


def test_a_faerie_arriving_after_casting_does_not_count():
    scenario, target = _board(hand=("Faerie Fencing", "Faerie Miscreant"))
    _cast(scenario, target)
    scenario.put_onto_battlefield("Faerie Miscreant", "alice", from_zone=Zone.HAND)
    scenario.resolve_top()
    assert _toughness(scenario, target) == 5


def test_an_opponents_faerie_does_not_count():
    scenario = (
        Scenario()
        .player("alice", hand=["Faerie Fencing"], battlefield=_LANDS)
        .player("bob", battlefield=["Colossal Dreadmaw", "Faerie Miscreant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    target = scenario.creature("Colossal Dreadmaw", "bob")
    _cast(scenario, target)
    scenario.resolve_top()
    assert _toughness(scenario, target) == 5


def test_any_cast_record_condition_gates_a_layer_sentence():
    """The mechanic, not the card: a kicked rider on a layer sentence parses
    too, while a board condition (not a cast fact) is left to its own readers."""
    from magic_cards_model.machines.layers.parse import _parse_layer_sentence

    assert _parse_layer_sentence(
        "Target creature gets +2/+2 until end of turn if this spell was kicked."
    )
    assert _parse_layer_sentence(
        "That creature gets an additional +1/+1 until end of turn if it was kicked."
    )
    assert (
        _parse_layer_sentence(
            "Target creature gets +2/+2 until end of turn if you control a Faerie."
        )
        is None
    )
