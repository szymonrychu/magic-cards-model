"""Equip's own "costs [N] less to activate for each [quality] ... it
targets" reduction (CR 601.2f via CR 602.2b).

Warrior's Blades: "Equip {3}. This ability costs {1} less to activate for
each +1/+1 counter on the creature it targets." Dragonfire Blade (Tarkir:
Dragonstorm, off-set): "Equip {4}. This ability costs {1} less to activate
for each color of the creature it targets." Two real cards, two different
counted quantities (a counter kind, a colour count), proving
`target_cost_reduction_amount` reads the sentence rather than either card by
name.

CR 602.2b's own order - targets (CR 601.2c) before cost (CR 601.2f) - is what
makes this readable at all: the amount is not known until the target is,
so `equip_activation` announces and checks the target (as it already did)
*before* computing this reduction, unlike the quality-scoped "... you
control" shape (Otawara's Channel, `test_off_battlefield_activation.py`),
which needs no target and is priced the same way it always was.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import ManaCost, Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario, mana_from


def test_warriors_blades_costs_one_less_per_plus_one_counter_on_its_target():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Warrior's Blades", "Grizzly Bears", "Mountain", "Mountain", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    blades = scenario.find("Warrior's Blades", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 2)

    activation = equip_activation(scenario.game, blades, bears, "alice")

    assert activation.cost.mana == ManaCost.parse("{1}")
    assert scenario.game.cost_modifier_notices == []

    payment = activation.begin_paying()
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    payment.tap_for_mana(mountain, mana_from(mountain))
    payment.pay()
    activation.activate()
    assert activation.resolve() is bears


def test_warriors_blades_costs_its_full_price_with_no_counters_on_its_target():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Warrior's Blades", "Grizzly Bears", "Mountain", "Mountain", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    blades = scenario.find("Warrior's Blades", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    activation = equip_activation(scenario.game, blades, bears, "alice")

    assert activation.cost.mana == ManaCost.parse("{3}")


def test_dragonfire_blade_costs_one_less_per_color_of_its_target():
    """Kitchen Finks is green and white - two colors, {4} down to {2}."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[
                "Dragonfire Blade",
                "Kitchen Finks",
                "Forest",
                "Forest",
                "Plains",
                "Plains",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    blade = scenario.find("Dragonfire Blade", Zone.BATTLEFIELD, "alice")
    finks = scenario.creature("Kitchen Finks", "alice")

    activation = equip_activation(scenario.game, blade, finks, "alice")

    assert activation.cost.mana == ManaCost.parse("{2}")
    assert scenario.game.cost_modifier_notices == []

    payment = activation.begin_paying()
    sources = scenario.untapped_sources("Forest", "Forest", username="alice")
    for source in sources:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    assert activation.resolve() is finks


def test_dragonfire_blade_costs_its_full_price_against_a_colorless_target():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Dragonfire Blade", "Ornithopter", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    blade = scenario.find("Dragonfire Blade", Zone.BATTLEFIELD, "alice")
    thopter = scenario.creature("Ornithopter", "alice")

    activation = equip_activation(scenario.game, blade, thopter, "alice")

    assert activation.cost.mana == ManaCost.parse("{4}")
