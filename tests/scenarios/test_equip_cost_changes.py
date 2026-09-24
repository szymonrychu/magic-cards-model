""" "Equip abilities you activate that target this creature cost `{N}` less
to activate." (a static cost reduction sourced from a different permanent
than the Equipment being activated, CR 601.2f via CR 602.2b) and
"Instant and sorcery spells you cast cost `{X}` less to cast, where X is
equipped creature's power." (a dynamic board-wide spell discount, CR 601.2f).

Dwarven Mauler: "Equip abilities you activate that target this creature cost
{2} less to activate." Glamdring, Foe-hammer: "Instant and sorcery spells you
cast cost {X} less to cast, where X is equipped creature's power."
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import ManaCost, Zone
from tests.scenarios.harness import Scenario, mana_from


def test_dwarven_mauler_discounts_an_equip_ability_that_targets_it():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Dwarven Shortsword", "Dwarven Mauler", "Grizzly Bears"] + ["Plains"] * 2,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sword = scenario.find("Dwarven Shortsword", Zone.BATTLEFIELD, "alice")
    mauler = scenario.find("Dwarven Mauler", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    activation_on_mauler = equip_activation(scenario.game, sword, mauler, "alice")
    assert activation_on_mauler.cost.mana.converted == 0

    activation_on_bears = equip_activation(scenario.game, sword, bears, "alice")
    assert activation_on_bears.cost.mana == ManaCost.parse("{2}")


def test_fervent_champion_discounts_an_equip_ability_that_targets_it():
    """Throne of Eldraine's own printing of the same "Equip abilities you
    activate that target this creature cost `{N}` less to activate."
    template, proof the reader is not fitted to Dwarven Mauler's own
    wording (a different discount amount)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Dwarven Shortsword", "Fervent Champion", "Grizzly Bears"]
            + ["Plains"] * 2,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sword = scenario.find("Dwarven Shortsword", Zone.BATTLEFIELD, "alice")
    champion = scenario.find("Fervent Champion", Zone.BATTLEFIELD, "alice")

    activation = equip_activation(scenario.game, sword, champion, "alice")
    assert activation.cost.mana.converted == 0


def _board_glamdring():
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Fiery Cannonade"],
            battlefield=["Glamdring, Foe-hammer // Gleam of Death", "Grizzly Bears"]
            + ["Mountain"] * 3,
        )
        .player("bob", battlefield=["Watchwolf"])
    )


def test_glamdring_reduces_instant_and_sorcery_cost_by_equipped_creatures_power():
    """CR 118.7a: a generic reduction only ever eats into a cost's own
    generic mana - Fiery Cannonade's {2}{R} loses its {2} to Grizzly
    Bears' power 2, leaving the {R} pip untouched rather than the total
    reducing all the way to 0."""
    scenario = _board_glamdring().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    glamdring = scenario.find("Glamdring, Foe-hammer", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    activation = equip_activation(scenario.game, glamdring, bears, "alice")
    payment = activation.begin_paying()
    for source in scenario.untapped_sources("Mountain", "Mountain", username="alice"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    scenario.pass_until_resolved()

    casting = scenario.cast("Fiery Cannonade")
    assert casting.total_cost.mana == ManaCost.parse("{R}")


def test_glamdring_gives_no_discount_when_unequipped():
    scenario = _board_glamdring().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Fiery Cannonade")
    assert casting.total_cost.mana == ManaCost.parse("{2}{R}")
