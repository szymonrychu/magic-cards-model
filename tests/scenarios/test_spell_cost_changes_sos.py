"""A spell that costs less if it targets a spell of some quality (CR 601.2f).

Brush Off: "This spell costs {1}{U} less to cast if it targets an instant or
sorcery spell. Counter target spell." Out of Air, the off-pool proof with a
generic amount and a card-type quality: "This spell costs {2} less to cast if
it targets a creature spell." Mystical Dispute's colour quality ("if it
targets a blue spell") is the same reader.

The condition is not a fact about the board: it is about the spell's own
announced target. CR 601.2c announces targets before CR 601.2f determines the
total cost - read whole with `mise run rules:find` in the session that wrote
this file: "The total cost is the mana cost or alternative cost ..., plus all
additional costs and cost increases, and minus all cost reductions." A
reduction written in coloured mana lands on the cost by CR 118.7: "If a cost
is reduced by an amount of colored or colorless mana, but the cost doesn't
require mana of that type, the cost is reduced by that amount of generic
mana" (118.7b).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import ManaCost, Zone
from magic_cards_model.models.game import reads_self_cost_reduction_line
from tests.scenarios.harness import PlayedScenario, Scenario


def board(*alice_hand: str) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=["Island"] * 4 + ["Mountain", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def cost_against(scenario: PlayedScenario, name: str, target) -> ManaCost:
    casting = scenario.cast(name, targets=[target])
    cost = casting.total_cost.mana
    casting.cancel()
    return cost


def test_the_reduction_line_is_read():
    assert reads_self_cost_reduction_line(
        "This spell costs {1}{U} less to cast if it targets an instant or sorcery spell."
    )
    assert reads_self_cost_reduction_line(
        "This spell costs {2} less to cast if it targets a creature spell."
    )


def test_brush_off_targeting_an_instant_costs_1u():
    scenario = board("Brush Off", "Lightning Bolt")
    (mountain,) = scenario.untapped_sources("Mountain")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    assert cost_against(scenario, "Brush Off", bolt) == ManaCost.parse("{1}{U}")


def test_brush_off_targeting_a_sorcery_costs_1u():
    scenario = board("Brush Off", "Divination")
    divination = scenario.cast_onto_stack(
        "Divination", *scenario.untapped_sources("Island", "Island", "Island")
    )
    casting = scenario.cast("Brush Off", targets=[divination])
    assert casting.total_cost.mana == ManaCost.parse("{1}{U}")


def test_brush_off_targeting_a_creature_spell_costs_full_price():
    scenario = board("Brush Off", "Grizzly Bears")
    bears = scenario.cast_onto_stack(
        "Grizzly Bears", *scenario.untapped_sources("Forest", "Forest")
    )
    assert cost_against(scenario, "Brush Off", bears) == ManaCost.parse("{2}{U}{U}")


def test_brush_off_really_counters_for_two_mana():
    scenario = board("Brush Off", "Lightning Bolt")
    (mountain,) = scenario.untapped_sources("Mountain")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    islands = scenario.untapped_sources("Island", "Island")
    scenario.cast_and_resolve("Brush Off", *islands, targets=[bolt])
    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 20
    assert len(scenario.untapped_sources("Island", "Island")) == 2


def test_the_reduction_is_read_off_the_target_when_the_cost_is_determined():
    """A spell that targets something other than a spell never qualifies:
    the reduction reads CR 601.2c's announcement, not the stack's contents."""
    scenario = board("Brush Off", "Lightning Bolt", "Grizzly Bears")
    bears = scenario.cast_onto_stack(
        "Grizzly Bears", *scenario.untapped_sources("Forest", "Forest")
    )
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    # A Bolt is on the stack, but Brush Off targets the Bears.
    assert cost_against(scenario, "Brush Off", bears) == ManaCost.parse("{2}{U}{U}")


def test_out_of_air_targeting_a_creature_spell_costs_uu():
    scenario = board("Out of Air", "Grizzly Bears")
    bears = scenario.cast_onto_stack(
        "Grizzly Bears", *scenario.untapped_sources("Forest", "Forest")
    )
    assert cost_against(scenario, "Out of Air", bears) == ManaCost.parse("{U}{U}")


def test_out_of_air_targeting_an_instant_costs_full_price():
    scenario = board("Out of Air", "Lightning Bolt")
    (mountain,) = scenario.untapped_sources("Mountain")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    assert cost_against(scenario, "Out of Air", bolt) == ManaCost.parse("{2}{U}{U}")


def test_out_of_air_really_counters_the_creature_for_two_islands():
    scenario = board("Out of Air", "Grizzly Bears")
    bears = scenario.cast_onto_stack(
        "Grizzly Bears", *scenario.untapped_sources("Forest", "Forest")
    )
    scenario.cast_and_resolve(
        "Out of Air", *scenario.untapped_sources("Island", "Island"), targets=[bears]
    )
    assert bears.zone is Zone.GRAVEYARD


def test_mystical_disputes_colour_quality_still_reads():
    scenario = board("Mystical Dispute", "Opt")
    (island,) = scenario.untapped_sources("Island")
    opt = scenario.cast_onto_stack("Opt", island)
    assert cost_against(scenario, "Mystical Dispute", opt) == ManaCost.parse("{U}")
