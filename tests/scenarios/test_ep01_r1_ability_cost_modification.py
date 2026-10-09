"""CR 601.2f via CR 602.2b: a permanent's static line that changes what other
abilities, and keyword actions, cost to activate (EP-01 round 1, task T7).

    Equip abilities you activate cost {1} less to activate.
    Activated abilities cost {2} more to activate unless they're mana abilities.
    Abilities you activate that aren't mana abilities cost {2} less to
    activate. This effect can't reduce the mana in that cost to less than one
    mana.

Every case is a real activation through the engine with the determined mana
asserted; each family has an activation the line does NOT name.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation, ninjutsu_activation
from magic_cards_model.models import ManaCost, Zone
from tests.scenarios.harness import Scenario


def _main(**players) -> Scenario:
    builder = Scenario().manual_turn_based_actions()
    for username, kwargs in players.items():
        builder = builder.player(username, **kwargs)
    scenario = builder.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _equip_cost(scenario, equipment, target, username="alice") -> str:
    return str(equip_activation(scenario.game, equipment, target, username).cost.mana)


def _ability_cost(scenario, permanent, index=0, username="alice", targets=None) -> str:
    return str(scenario.game.activation_cost(permanent, index, username, targets=targets).mana)


# -- equip -----------------------------------------------------------------------


def test_bureau_headmaster_makes_equip_cost_one_less():
    scenario = _main(
        alice={"battlefield": ["Bureau Headmaster", "Embercleave", "Grizzly Bears"]},
    )
    cleave = scenario.find("Embercleave", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    assert _equip_cost(scenario, cleave, bears) == "{2}"


def test_equip_cost_is_full_price_without_the_static_line():
    scenario = _main(alice={"battlefield": ["Bonesplitter", "Grizzly Bears"]})
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    assert _equip_cost(scenario, splitter, bears) == "{1}"


def test_bureau_headmaster_reduces_only_the_generic_part_and_only_its_controllers():
    scenario = _main(
        alice={"battlefield": ["Bonesplitter", "Grizzly Bears"]},
        bob={"battlefield": ["Bureau Headmaster"]},
    )
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    assert _equip_cost(scenario, splitter, bears) == "{1}"
    mine = _main(alice={"battlefield": ["Bureau Headmaster", "Bonesplitter", "Grizzly Bears"]})
    splitter = mine.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    bears = mine.creature("Grizzly Bears", "alice")
    assert _equip_cost(mine, splitter, bears) == ""


def test_auriok_steelshaper_equip_costs_you_pay():
    scenario = _main(
        alice={"battlefield": ["Auriok Steelshaper", "Bonesplitter", "Grizzly Bears"]},
    )
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    assert _equip_cost(scenario, splitter, bears) == ""


def test_bladegraft_aspirant_discounts_equipment_that_targets_it_only():
    scenario = _main(
        alice={"battlefield": ["Bladegraft Aspirant", "Embercleave", "Grizzly Bears"]},
    )
    cleave = scenario.find("Embercleave", Zone.BATTLEFIELD, "alice")
    aspirant = scenario.creature("Bladegraft Aspirant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    assert _equip_cost(scenario, cleave, bears) == "{3}"
    assert _equip_cost(scenario, cleave, aspirant) == "{2}"


def test_ghostfire_blade_costs_two_less_only_for_a_colorless_creature():
    scenario = _main(
        alice={"battlefield": ["Ghostfire Blade", "Grizzly Bears", "Ornithopter"]},
    )
    blade = scenario.find("Ghostfire Blade", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    ornithopter = scenario.creature("Ornithopter", "alice")
    assert _equip_cost(scenario, blade, bears) == "{3}"
    assert _equip_cost(scenario, blade, ornithopter) == "{1}"


# -- every activated ability ----------------------------------------------------


def test_suppression_field_taxes_every_players_non_mana_abilities():
    scenario = _main(
        alice={"battlefield": ["Suppression Field", "Walking Ballista"]},
        bob={"battlefield": ["Walking Ballista"]},
    )
    mine = scenario.find("Walking Ballista", Zone.BATTLEFIELD, "alice")
    theirs = scenario.find("Walking Ballista", Zone.BATTLEFIELD, "bob")
    assert _ability_cost(scenario, mine, 0, "alice") == "{6}"
    assert _ability_cost(scenario, theirs, 0, "bob") == "{6}"


def test_zirda_takes_two_off_but_never_below_one_mana():
    scenario = _main(
        alice={"battlefield": ["Zirda, the Dawnwaker", "Agatha of the Vile Cauldron"]},
    )
    zirda = scenario.creature("Zirda, the Dawnwaker", "alice")
    agatha = scenario.creature("Agatha of the Vile Cauldron", "alice")
    assert _ability_cost(scenario, zirda) == "{1}"
    # {4}{R}{G} less {2} (Zirda) less {1} (Agatha's power)
    assert _ability_cost(scenario, agatha) == "{1}{R}{G}"


def test_agatha_discounts_by_her_power_and_only_her_controllers_creatures():
    scenario = _main(
        alice={"battlefield": ["Agatha of the Vile Cauldron"]},
        bob={"battlefield": ["Zirda, the Dawnwaker"]},
    )
    agatha = scenario.creature("Agatha of the Vile Cauldron", "alice")
    zirda = scenario.creature("Zirda, the Dawnwaker", "bob")
    assert _ability_cost(scenario, agatha) == "{3}{R}{G}"
    assert _ability_cost(scenario, zirda, 0, "bob") == "{1}"


def test_embalmers_tools_discounts_only_creature_cards_in_your_graveyard():
    scenario = _main(
        alice={"battlefield": ["Embalmer's Tools", "Zirda, the Dawnwaker"]},
    )
    zirda = scenario.creature("Zirda, the Dawnwaker", "alice")
    assert _ability_cost(scenario, zirda) == "{1}"


def test_embalmers_tools_discounts_a_graveyard_creatures_unearth():
    from magic_cards_model.machines.keywords import unearth_activation

    with_tools = _main(
        alice={"battlefield": ["Embalmer's Tools"], "graveyard": ["Cityscape Leveler"]},
    )
    leveler = with_tools.find("Cityscape Leveler", Zone.GRAVEYARD, "alice")
    assert str(unearth_activation(with_tools.game, leveler, "alice").cost.mana) == "{7}"
    without = _main(alice={"graveyard": ["Cityscape Leveler"]})
    leveler = without.find("Cityscape Leveler", Zone.GRAVEYARD, "alice")
    assert str(unearth_activation(without.game, leveler, "alice").cost.mana) == "{8}"


def test_kopala_taxes_opponents_abilities_that_target_its_merfolk():
    scenario = _main(
        alice={"battlefield": ["Kopala, Warden of Waves", "Grizzly Bears"]},
        bob={"battlefield": ["Walking Ballista"]},
    )
    kopala = scenario.creature("Kopala, Warden of Waves", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    ballista = scenario.creature("Walking Ballista", "bob")
    assert _ability_cost(scenario, ballista, 0, "bob", targets=[kopala]) == "{6}"
    assert _ability_cost(scenario, ballista, 0, "bob", targets=[bears]) == "{4}"


def test_eidolon_of_obstruction_taxes_opposing_loyalty_abilities_only():
    scenario = _main(
        alice={"battlefield": ["Tezzeret, Betrayer of Flesh"]},
        bob={"battlefield": ["Eidolon of Obstruction"]},
    )
    tezzeret = scenario.find("Tezzeret, Betrayer of Flesh", Zone.BATTLEFIELD, "alice")
    assert _ability_cost(scenario, tezzeret, 0, "alice") == "{1}"
    mine = _main(
        alice={"battlefield": ["Tezzeret, Betrayer of Flesh", "Eidolon of Obstruction"]},
    )
    tezzeret = mine.find("Tezzeret, Betrayer of Flesh", Zone.BATTLEFIELD, "alice")
    assert _ability_cost(mine, tezzeret, 0, "alice") == ""


def test_skyseer_chariot_taxes_sources_with_the_chosen_name():
    from magic_cards_model.models.card_state import Choice, ChoiceKind

    scenario = _main(
        alice={"battlefield": ["Skyseer's Chariot", "Walking Ballista"]},
    )
    chariot = scenario.find("Skyseer's Chariot", Zone.BATTLEFIELD, "alice")
    ballista = scenario.creature("Walking Ballista", "alice")
    assert _ability_cost(scenario, ballista) == "{4}"
    chariot.choice = Choice(kind=ChoiceKind.CARD_NAME, value="Walking Ballista")
    assert _ability_cost(scenario, ballista) == "{6}"


def test_tezzeret_discounts_only_the_first_artifact_ability_each_turn():
    scenario = _main(
        alice={
            "battlefield": ["Tezzeret, Betrayer of Flesh", "Embalmer's Tools", "Mountain"],
        },
    )
    scenario = _main(
        alice={
            "battlefield": ["Tezzeret, Betrayer of Flesh", "Walking Ballista", "Mountain"]
            + ["Mountain"]
        },
    )
    ballista = scenario.creature("Walking Ballista", "alice")
    assert _ability_cost(scenario, ballista) == "{2}"
    scenario.activate(ballista, index=0, username="alice", auto=True)
    assert _ability_cost(scenario, ballista) == "{4}"


# -- keyword actions --------------------------------------------------------------


def test_silver_fur_master_discounts_ninjutsu_abilities():
    scenario = Scenario().manual_turn_based_actions()
    scenario = (
        scenario.player(
            "alice",
            hand=["Kaito, Bane of Nightmares"],
            battlefield=["Silver-Fur Master", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    kaito = scenario.find("Kaito, Bane of Nightmares", Zone.HAND, "alice")
    activation = ninjutsu_activation(scenario.game, kaito, bears, "alice")
    assert activation.cost.mana == ManaCost.parse("{U}{B}")


def test_warbringer_discounts_dash_costs():
    scenario = _main(
        alice={
            "hand": ["Ragavan, Nimble Pilferer"],
            "battlefield": ["Warbringer", "Mountain", "Mountain"],
        },
    )
    casting = scenario.cast("Ragavan, Nimble Pilferer", "alice")
    casting.use_alternative_cost("dash")
    scenario.game.determine_total_cost(casting)
    assert str(casting.total_cost.mana) == "{R}"


def test_dash_is_full_price_without_warbringer():
    scenario = _main(
        alice={
            "hand": ["Ragavan, Nimble Pilferer"],
            "battlefield": ["Mountain", "Mountain"],
        },
    )
    casting = scenario.cast("Ragavan, Nimble Pilferer", "alice")
    casting.use_alternative_cost("dash")
    scenario.game.determine_total_cost(casting)
    assert str(casting.total_cost.mana) == "{1}{R}"


def test_dragonkin_berserker_boast_costs_one_less_per_dragon():
    scenario = _main(
        alice={"battlefield": ["Dragonkin Berserker", "Archive Dragon"]},
    )
    berserker = scenario.creature("Dragonkin Berserker", "alice")
    assert _ability_cost(scenario, berserker) == "{3}{R}"


def test_boom_scholar_discounts_exhaust_of_other_permanents_only():
    scenario = _main(
        alice={"battlefield": ["Boom Scholar", "Pacesetter Paragon"]},
    )
    scholar = scenario.creature("Boom Scholar", "alice")
    paragon = scenario.creature("Pacesetter Paragon", "alice")
    assert _ability_cost(scenario, paragon) == "{R}"
    assert _ability_cost(scenario, scholar) == "{4}{R}{G}"
