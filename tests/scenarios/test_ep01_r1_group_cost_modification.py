"""CR 601.2f / 604.2: a permanent's static line that changes what other
spells cost - qualities of spell, ordinals ("the second spell you cast each
turn"), "that target ..." clauses, "for each", "where X is" and the "and can't
be countered" rider (EP-01 round 1, task T7).

Every case is a real cast through the engine with the determined total cost
asserted; each family has a spell the line does NOT name.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _main(**players) -> Scenario:
    builder = Scenario()
    for username, kwargs in players.items():
        builder = builder.player(username, **kwargs)
    scenario = builder.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cost(scenario, name, *, targets=None, username="alice", from_zone=Zone.HAND) -> str:
    casting = scenario.cast(name, username, from_zone=from_zone, targets=targets)
    scenario.game.determine_total_cost(casting)
    mana = str(casting.total_cost.mana)
    casting.cancel()
    return mana


# -- quality of spell ----------------------------------------------------------


def test_warden_of_evos_isle_discounts_only_flying_creature_spells():
    scenario = _main(
        alice={
            "hand": ["Serra Angel", "Grizzly Bears", "Lightning Bolt"],
            "battlefield": ["Warden of Evos Isle"],
        }
    )
    assert _cost(scenario, "Serra Angel") == "{2}{W}{W}"
    assert _cost(scenario, "Grizzly Bears") == "{1}{G}"
    assert _cost(scenario, "Lightning Bolt") == "{R}"


def test_goblin_anarchomancer_discounts_red_or_green_spells_of_any_type():
    scenario = _main(
        alice={
            "hand": ["Concussive Bolt", "Grizzly Bears", "Serra Angel"],
            "battlefield": ["Goblin Anarchomancer"],
        }
    )
    assert _cost(scenario, "Concussive Bolt") == "{2}{R}{R}"
    assert _cost(scenario, "Grizzly Bears") == "{G}"
    assert _cost(scenario, "Serra Angel") == "{3}{W}{W}"


def test_arcane_melee_discounts_instants_and_sorceries_but_not_creatures():
    scenario = _main(
        alice={"hand": ["Concussive Bolt", "Grizzly Bears"], "battlefield": ["Arcane Melee"]}
    )
    assert _cost(scenario, "Concussive Bolt") == "{1}{R}{R}"
    assert _cost(scenario, "Grizzly Bears") == "{1}{G}"


def test_arcane_melee_reduces_only_the_generic_component():
    """CR 118.7a: {2} off {R} leaves {R}."""
    scenario = _main(alice={"hand": ["Lightning Bolt"], "battlefield": ["Arcane Melee"]})
    assert _cost(scenario, "Lightning Bolt") == "{R}"


def test_spectacle_mage_discounts_only_instants_and_sorceries_with_mana_value_five():
    scenario = _main(
        alice={
            "hand": ["Lacerate Flesh", "Concussive Bolt"],
            "battlefield": ["Spectacle Mage"],
        }
    )
    assert _cost(scenario, "Lacerate Flesh", targets=None) == "{3}{R}"
    assert _cost(scenario, "Concussive Bolt") == "{2}{R}{R}"


def test_spectacle_mage_ignores_a_cheaper_instant():
    scenario = _main(alice={"hand": ["Divination"], "battlefield": ["Spectacle Mage"]})
    assert _cost(scenario, "Divination") == "{2}{U}"


def test_goreclaw_discounts_creature_spells_with_power_four_or_greater():
    scenario = _main(
        alice={
            "hand": ["Serra Angel", "Grizzly Bears"],
            "battlefield": ["Goreclaw, Terror of Qal Sisma"],
        }
    )
    assert _cost(scenario, "Grizzly Bears") == "{1}{G}"
    assert _cost(scenario, "Serra Angel") == "{1}{W}{W}"


def test_it_that_heralds_the_end_discounts_colorless_spells_with_mana_value_seven():
    scenario = _main(
        alice={
            "hand": ["Sea Gate Colossus", "Sol Ring"],
            "battlefield": ["It That Heralds the End"],
        }
    )
    assert _cost(scenario, "Sea Gate Colossus") == "{6}"
    assert _cost(scenario, "Sol Ring") == "{1}"


# -- ordinals -----------------------------------------------------------------


def test_the_second_spell_each_turn_is_discounted_not_the_first_or_third():
    scenario = _main(
        alice={
            "hand": ["Lightning Bolt", "Grizzly Bears", "Grizzly Bears"],
            "battlefield": ["Raging Battle Mouse", "Mountain", "Forest", "Forest"],
        },
        bob={},
    )
    assert _cost(scenario, "Grizzly Bears") == "{1}{G}"
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=["bob"])
    assert _cost(scenario, "Grizzly Bears") == "{G}"
    forests = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.cast_and_resolve("Grizzly Bears", forests[0])
    assert _cost(scenario, "Grizzly Bears") == "{1}{G}"


def test_uthros_psionicist_discounts_two():
    scenario = _main(
        alice={
            "hand": ["Lightning Bolt", "Serra Angel"],
            "battlefield": ["Uthros Psionicist", "Mountain"],
        },
        bob={},
    )
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=["bob"])
    assert _cost(scenario, "Serra Angel") == "{1}{W}{W}"


def test_the_first_legendary_creature_spell_each_turn():
    scenario = _main(
        alice={
            "hand": ["Grizzly Bears", "Thrasta, Tempest's Roar"],
            "battlefield": ["Serah Farron // Crystallized Serah"],
        }
    )
    assert _cost(scenario, "Grizzly Bears") == "{1}{G}"
    assert _cost(scenario, "Thrasta, Tempest's Roar") == "{8}{G}{G}"


# -- "that target ..." -----------------------------------------------------------


def test_killian_discounts_spells_that_target_a_creature():
    scenario = _main(
        alice={
            "hand": ["Swampsnare Trap", "Concussive Bolt"],
            "battlefield": ["Killian, Ink Duelist"],
        },
        bob={"battlefield": ["Grizzly Bears"]},
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    assert _cost(scenario, "Swampsnare Trap", targets=[bears]) == "{B}"
    assert _cost(scenario, "Concussive Bolt", targets=["bob"]) == "{3}{R}{R}"


def test_spellwild_ouphe_discounts_only_spells_that_target_it():
    scenario = _main(
        alice={"hand": ["Swampsnare Trap"], "battlefield": ["Spellwild Ouphe", "Grizzly Bears"]},
    )
    ouphe = scenario.creature("Spellwild Ouphe", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    assert _cost(scenario, "Swampsnare Trap", targets=[ouphe]) == "{B}"
    assert _cost(scenario, "Swampsnare Trap", targets=[bears]) == "{2}{B}"


def test_infectious_curse_discounts_only_spells_that_target_the_enchanted_player():
    """CR 303.4m: "enchanted player" is whoever the Curse is attached to; a
    spell aimed at anyone else, or at nobody, pays full price."""
    scenario = _main(
        alice={
            "hand": ["Mind Rot"],
            "battlefield": ["Accursed Witch // Infectious Curse"],
        },
        bob={},
        carol={},
    )
    curse = scenario.find("Accursed Witch // Infectious Curse", Zone.BATTLEFIELD, "alice")
    curse.transformed = True
    curse.attach_to(scenario.player("bob"))
    assert _cost(scenario, "Mind Rot", targets=["bob"]) == "{1}{B}"
    assert _cost(scenario, "Mind Rot", targets=["carol"]) == "{2}{B}"
    assert _cost(scenario, "Mind Rot", targets=["alice"]) == "{2}{B}"


def test_battlefield_thaumaturge_discounts_per_creature_targeted():
    scenario = _main(
        alice={"hand": ["Lacerate Flesh"], "battlefield": ["Battlefield Thaumaturge"]},
        bob={"battlefield": ["Grizzly Bears"]},
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    assert _cost(scenario, "Lacerate Flesh", targets=[bears]) == "{3}{R}"


# -- the "can't be countered" rider -------------------------------------------------


def test_cunning_nightbonder_discounts_flash_spells_and_makes_them_uncounterable():
    from magic_cards_model.machines.casting_restrictions import static_uncounterable_source

    scenario = _main(
        alice={
            "hand": ["High Fae Trickster", "Grizzly Bears"],
            "battlefield": [
                "Cunning Nightbonder",
                "Island",
                "Island",
                "Island",
                "Island",
                "Forest",
                "Forest",
            ],
        }
    )
    assert _cost(scenario, "High Fae Trickster") == "{2}{U}"
    assert _cost(scenario, "Grizzly Bears") == "{1}{G}"
    bears = scenario.cast_onto_stack(
        "Grizzly Bears", *scenario.untapped_sources("Forest", "Forest")
    )
    trickster = scenario.cast_onto_stack(
        "High Fae Trickster", *scenario.untapped_sources("Island", "Island", "Island")
    )
    assert static_uncounterable_source(scenario.game, trickster) is not None
    assert static_uncounterable_source(scenario.game, bears) is None
