"""EP-01 round 2, task T7: characteristic-defining abilities (CR 604.3,
CR 613.4a) read off hands and life totals, and "snow" made by an ice counter.

Aeon Chronicler counts cards in its controller's hand, Malignus reads half the
highest life total among its controller's opponents (rounded up), Roiling
Horror subtracts the life total of the opponent with the most life from its
controller's (so it can go negative), and Rimefeather Owl counts every snow
permanent, including the ones an ice counter makes snow.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
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
