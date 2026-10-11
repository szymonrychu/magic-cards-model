"""EP-01 round 2, task T7: characteristic-defining abilities (CR 604.3,
CR 613.4a) read off hands and life totals, and "snow" made by an ice counter.

Aeon Chronicler counts cards in its controller's hand, Malignus reads half the
highest life total among its controller's opponents (rounded up), Roiling
Horror subtracts the life total of the opponent with the most life from its
controller's (so it can go negative), and Rimefeather Owl counts every snow
permanent, including the ones an ice counter makes snow.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import AbilityKind
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Choice, ChoiceKind
from tests.scenarios.harness import Scenario


def build(**players):
    scenario = Scenario()
    for username, spec in players.items():
        scenario = scenario.player(username, **spec)
    played = scenario.build()
    played.start_at(Step.PRECOMBAT_MAIN)
    return played


def pt(scenario, name: str, username: str = "alice"):
    chars = scenario.game.computed_board().of(scenario.creature(name, username))
    return chars.power, chars.toughness


# --- Aeon Chronicler: cards in your hand -----------------------------------


def test_aeon_chronicler_counts_the_cards_in_its_controllers_hand():
    scenario = build(
        alice={"battlefield": ["Aeon Chronicler"], "hand": ["Shock", "Divination", "Forest"]},
        bob={"hand": ["Shock", "Shock", "Shock", "Shock"]},
    )
    assert pt(scenario, "Aeon Chronicler") == (3, 3)


def test_aeon_chronicler_is_zero_with_an_empty_hand_and_grows_on_draw():
    scenario = build(alice={"battlefield": ["Aeon Chronicler"], "library": ["Forest"] * 3}, bob={})
    assert pt(scenario, "Aeon Chronicler") == (0, 0)
    scenario.draw(2)
    assert pt(scenario, "Aeon Chronicler") == (2, 2)


# --- Malignus: half the highest opponent life total, rounded up ------------


def test_malignus_is_half_the_highest_life_total_among_opponents_rounded_up():
    scenario = build(alice={"battlefield": ["Malignus"], "life": 3}, bob={"life": 15})
    assert pt(scenario, "Malignus") == (8, 8)


def test_malignus_even_life_halves_exactly_and_ignores_its_controllers_life():
    scenario = build(alice={"battlefield": ["Malignus"], "life": 40}, bob={"life": 12})
    assert pt(scenario, "Malignus") == (6, 6)


def test_malignus_takes_the_highest_of_several_opponents():
    scenario = build(
        alice={"battlefield": ["Malignus"]},
        bob={"life": 6},
        carol={"life": 9},
    )
    assert pt(scenario, "Malignus") == (5, 5)


# --- Roiling Horror: your life total minus the life of the opponent with most


def test_roiling_horror_is_the_life_difference():
    scenario = build(alice={"battlefield": ["Roiling Horror"], "life": 20}, bob={"life": 12})
    assert pt(scenario, "Roiling Horror") == (8, 8)


def test_roiling_horror_goes_negative_when_behind():
    scenario = build(alice={"battlefield": ["Roiling Horror"], "life": 5}, bob={"life": 12})
    assert pt(scenario, "Roiling Horror") == (-7, -7)


def test_roiling_horror_subtracts_only_the_opponent_with_the_most_life():
    scenario = build(
        alice={"battlefield": ["Roiling Horror"], "life": 20}, bob={"life": 4}, carol={"life": 11}
    )
    assert pt(scenario, "Roiling Horror") == (9, 9)


# --- Rimefeather Owl: snow permanents on the battlefield -------------------


def test_owl_counts_itself_and_every_snow_permanent_of_any_controller():
    scenario = build(
        alice={"battlefield": ["Rimefeather Owl", "Snow-Covered Forest", "Forest"]},
        bob={"battlefield": ["Snow-Covered Island"]},
    )
    assert pt(scenario, "Rimefeather Owl") == (3, 3)


def test_an_ice_counter_makes_any_permanent_snow():
    scenario = build(
        alice={"battlefield": ["Rimefeather Owl", "Grizzly Bears"]},
        bob={"battlefield": ["Forest"]},
    )
    assert pt(scenario, "Rimefeather Owl") == (1, 1)
    scenario.game.add_counters(scenario.find("Forest", Zone.BATTLEFIELD, "bob"), "ice", 1)
    assert pt(scenario, "Rimefeather Owl") == (2, 2)


# --- "is the chosen type in addition to its other types" -------------------


def _cast(scenario, name: str, chosen: str, lands: int):
    scenario.will_choose(chosen, source=name)
    sources = scenario.untapped_sources(*(["Plains"] * lands))
    scenario.cast_and_resolve(name, *sources, username="alice")
    return scenario.creature(name, "alice")


def test_metallic_mimic_becomes_the_chosen_type_and_keeps_its_own():
    scenario = build(
        alice={"hand": ["Metallic Mimic"], "battlefield": ["Plains", "Plains"]}, bob={}
    )
    mimic = _cast(scenario, "Metallic Mimic", "Goblin", 2)
    assert set(scenario.game.computed_board().of(mimic).subtypes) == {"Shapeshifter", "Goblin"}


def test_roaming_throne_is_the_chosen_type_too():
    scenario = build(alice={"hand": ["Roaming Throne"], "battlefield": ["Plains"] * 5}, bob={})
    throne = _cast(scenario, "Roaming Throne", "Elf", 5)
    assert set(scenario.game.computed_board().of(throne).subtypes) == {"Golem", "Elf"}


def test_a_different_choice_gives_a_different_type_and_the_other_choice_is_absent():
    scenario = build(
        alice={"hand": ["Metallic Mimic"], "battlefield": ["Plains", "Plains"]}, bob={}
    )
    mimic = _cast(scenario, "Metallic Mimic", "Merfolk", 2)
    subtypes = scenario.game.computed_board().of(mimic).subtypes
    assert "Merfolk" in subtypes and "Goblin" not in subtypes


def test_thran_portal_is_the_chosen_basic_land_type_and_taps_for_its_mana():
    scenario = build(alice={"hand": ["Thran Portal"]}, bob={})
    scenario.will_choose("Forest", source="Thran Portal")
    portal = scenario.play_land("Thran Portal")
    chars = scenario.game.computed_board().of(portal)
    assert set(chars.subtypes) == {"Gate", "Forest"}
    assert "{T}: Add {G}." in chars.abilities


# --- Roaming Throne: triggered abilities of the chosen type trigger twice ---
# (CR 603.2d)


def _prowess_triggers(scenario, source):
    scenario_game = scenario.game
    return [
        item
        for item in [*scenario.pending_triggers, *scenario_game.stack]
        if getattr(item, "kind", None) is AbilityKind.TRIGGERED
        and getattr(item, "source_id", None) == source.id
    ]


def _bolt_bob(scenario):
    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="alice")[:1],
        username="alice",
        targets=["bob"],
    )


def _throne_board(chosen: str, *extra: str):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Roaming Throne", "Monastery Swiftspear", "Mountain", *extra],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    throne = scenario.creature("Roaming Throne", "alice")
    throne.choice = Choice(kind=ChoiceKind.CREATURE_TYPE, value=chosen)
    return scenario


def test_roaming_throne_doubles_a_triggered_ability_of_another_creature_of_the_chosen_type():
    scenario = _throne_board("Monk")
    _bolt_bob(scenario)
    assert len(_prowess_triggers(scenario, scenario.creature("Monastery Swiftspear"))) == 2


def test_roaming_throne_leaves_a_creature_of_another_type_alone():
    scenario = _throne_board("Elf")
    _bolt_bob(scenario)
    assert len(_prowess_triggers(scenario, scenario.creature("Monastery Swiftspear"))) == 1


def test_roaming_throne_does_not_double_its_own_triggers_even_if_it_is_the_chosen_type():
    scenario = _throne_board("Golem")
    _bolt_bob(scenario)
    assert len(_prowess_triggers(scenario, scenario.creature("Monastery Swiftspear"))) == 1


# --- Thran Portal: its mana abilities cost an additional 1 life ------------
# (CR 605.3a, CR 118.4)


def test_thran_portal_mana_costs_one_life_each_time_it_is_tapped():
    scenario = build(alice={"hand": ["Thran Portal", "Llanowar Elves"]}, bob={})
    scenario.will_choose("Forest", source="Thran Portal")
    scenario.play_land("Thran Portal")
    assert scenario.player("alice").life == 20
    scenario.cast_and_resolve("Llanowar Elves", username="alice", auto=True)
    assert scenario.player("alice").life == 19


def test_a_land_without_the_clause_costs_no_life_to_tap():
    scenario = build(alice={"hand": ["Llanowar Elves"], "battlefield": ["Forest"]}, bob={})
    scenario.cast_and_resolve("Llanowar Elves", username="alice", auto=True)
    assert scenario.player("alice").life == 20


# --- "gets +1/+1 for each <thing>" over a count the engine already reads ---
# (CR 613.4c, recomputed continuously, CR 611.3a)


def test_aura_gnarlid_grows_for_every_aura_on_the_battlefield_whoever_controls_it():
    scenario = build(
        alice={"battlefield": ["Aura Gnarlid", "Grizzly Bears"]},
        bob={"battlefield": ["Grizzly Bears"]},
    )
    assert pt(scenario, "Aura Gnarlid") == (2, 2)


def test_aura_gnarlid_counts_auras_of_both_players():
    scenario = build(
        alice={"battlefield": ["Aura Gnarlid", "Pacifism"]},
        bob={"battlefield": ["Arrest"]},
    )
    scenario.find("Pacifism", Zone.BATTLEFIELD, "alice").attach_to(
        scenario.creature("Aura Gnarlid", "alice")
    )
    assert pt(scenario, "Aura Gnarlid") == (4, 4)


def test_joraga_warcaller_pumps_other_elves_by_its_own_counters_only():
    scenario = build(
        alice={"battlefield": ["Joraga Warcaller", "Llanowar Elves", "Grizzly Bears"]},
        bob={"battlefield": ["Llanowar Elves"]},
    )
    joraga = scenario.creature("Joraga Warcaller", "alice")
    scenario.game.add_counters(joraga, "+1/+1", 3)
    assert pt(scenario, "Llanowar Elves", "alice") == (4, 4)
    assert pt(scenario, "Llanowar Elves", "bob") == (1, 1), "an opponent's Elf is not yours"
    assert pt(scenario, "Grizzly Bears") == (2, 2), "a Bear is not an Elf"
    assert pt(scenario, "Joraga Warcaller") == (4, 4), "only OTHER Elves, Joraga has its counters"


def test_joraga_warcaller_without_counters_pumps_nobody():
    scenario = build(alice={"battlefield": ["Joraga Warcaller", "Llanowar Elves"]}, bob={})
    assert pt(scenario, "Llanowar Elves") == (1, 1)


def test_banner_of_kinship_counts_a_fellowship_counter_per_chosen_type_creature():
    scenario = build(
        alice={
            "hand": ["Banner of Kinship"],
            "battlefield": ["Raging Goblin", "Raging Goblin", "Grizzly Bears", "Plains", "Plains"]
            + ["Plains", "Plains", "Plains"],
        },
        bob={},
    )
    scenario.will_choose("Goblin", source="Banner of Kinship")
    sources = scenario.untapped_sources(*(["Plains"] * 5))
    banner = scenario.cast_and_resolve("Banner of Kinship", *sources, username="alice")
    assert banner.counters["fellowship"] == 2
    goblin = scenario.game.computed_board().of(
        scenario.creatures("Raging Goblin", "Raging Goblin")[0]
    )
    assert (goblin.power, goblin.toughness) == (3, 3)
    assert pt(scenario, "Grizzly Bears") == (2, 2)


def test_banner_of_kinship_grows_when_a_counter_is_added():
    scenario = build(alice={"battlefield": ["Banner of Kinship", "Raging Goblin"]}, bob={})
    banner = scenario.find("Banner of Kinship", Zone.BATTLEFIELD, "alice")
    banner.choice = Choice(kind=ChoiceKind.CREATURE_TYPE, value="Goblin")
    assert pt(scenario, "Raging Goblin") == (1, 1)
    scenario.game.add_counters(banner, "fellowship", 4)
    assert pt(scenario, "Raging Goblin") == (5, 5)


def test_cid_pumps_artifact_creatures_by_artificers_on_the_board_and_in_the_graveyard():
    scenario = build(
        alice={
            "battlefield": [
                "Cid, Timeless Artificer",
                "Memnite",
                "Heartwood Crafter",
                "Grizzly Bears",
            ],
            "graveyard": ["Konstrari Improviser"],
        },
        bob={"battlefield": ["Memnite"]},
    )
    # Artificers: Cid + Heartwood Crafter on the board, one in the graveyard.
    assert pt(scenario, "Memnite", "alice") == (4, 4)
    assert pt(scenario, "Memnite", "bob") == (1, 1), "an opponent's artifact creature is not yours"
    assert pt(scenario, "Grizzly Bears") == (2, 2), "a Bear is neither an artifact nor a Hero"


def test_cid_pumps_a_hero_that_is_not_an_artifact():
    bare = build(alice={"battlefield": ["Jennifer Walters"]}, bob={})
    pumped = build(alice={"battlefield": ["Cid, Timeless Artificer", "Jennifer Walters"]}, bob={})
    plain = pt(bare, "Jennifer Walters")
    assert pt(pumped, "Jennifer Walters") == (plain[0] + 1, plain[1] + 1)
