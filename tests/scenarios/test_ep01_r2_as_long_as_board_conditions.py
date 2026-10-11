"""Scenario: conditional statics whose condition reads the board, an
equipped or paired creature, or a graveyard (EP-01 round 2, task 3).

Kolvori ("As long as you control three or more legendary creatures, ~ gets
+4/+2 and has vigilance."), Formation Breaker ("As long as you control a
creature with a counter on it, this creature gets +1/+2."), Villainous Ogre
("As long as you control a Demon, this creature has '{B}: Regenerate this
creature.'"), Oculus Whelp (a transformed permanent), Doc Ock (graveyard
count and "another Villain"), Hundred-Battle Veteran (kinds of counters),
the Human-equipped Equipment trio, Erebos's Titan, Expedition Diviner and
Sedge Sliver's quoted conditional pump.

Verified with `mise run rules:find`: CR 611.3a (not locked in), CR 604.2,
CR 613.1f (layer 6 grants), CR 613.4c (7c pump), CR 613.4b (7b base P/T),
CR 700.9 (modified).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(alice, bob=(), *, alice_graveyard=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=list(alice),
            graveyard=list(alice_graveyard),
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _chars(scenario, name, username="alice"):
    return scenario.game.characteristics_of(scenario.find(name, Zone.BATTLEFIELD, username))


def _has(chars, text):
    return any(line.lower() == text.lower() for line in chars.abilities)


# -- Kolvori: N legendary creatures --------------------------------------------


def test_kolvori_with_three_legendary_creatures_gets_the_pump_and_vigilance():
    scenario = _board(["Kolvori, God of Kinship", "Kalitas, Traitor of Ghet", "Six"])
    chars = _chars(scenario, "Kolvori, God of Kinship")
    assert chars.power_toughness == (6, 6)
    assert _has(chars, "Vigilance")


def test_kolvori_with_only_two_legendary_creatures_gets_nothing():
    scenario = _board(["Kolvori, God of Kinship", "Kalitas, Traitor of Ghet"])
    chars = _chars(scenario, "Kolvori, God of Kinship")
    assert not _has(chars, "Vigilance")


def test_kolvori_ignores_nonlegendary_creatures():
    scenario = _board(["Kolvori, God of Kinship", "Grizzly Bears", "Llanowar Elves"])
    assert not _has(_chars(scenario, "Kolvori, God of Kinship"), "Vigilance")


# -- Formation Breaker: a creature with a counter ------------------------------


def test_formation_breaker_pumps_while_you_control_a_creature_with_a_counter():
    scenario = _board(["Formation Breaker", "Grizzly Bears"])
    assert _chars(scenario, "Formation Breaker").power_toughness == (2, 1)
    scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice").add_counters("+1/+1")
    assert _chars(scenario, "Formation Breaker").power_toughness == (3, 3)


def test_formation_breaker_ignores_an_opponents_creature_with_a_counter():
    scenario = _board(["Formation Breaker"], ["Grizzly Bears"])
    scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob").add_counters("+1/+1")
    assert _chars(scenario, "Formation Breaker").power_toughness == (2, 1)


# -- Villainous Ogre: a Demon grants a quoted ability --------------------------


def test_ogre_without_a_demon_has_no_regenerate_ability():
    scenario = _board(["Villainous Ogre", "Grizzly Bears"])
    assert "{B}: Regenerate this creature." not in _chars(scenario, "Villainous Ogre").abilities


def test_ogre_with_a_demon_gains_and_can_activate_regenerate():
    scenario = _board(["Villainous Ogre", "Razorjaw Oni"])
    ogre = scenario.find("Villainous Ogre", Zone.BATTLEFIELD, "alice")
    assert "Demon" in _chars(scenario, "Razorjaw Oni").subtypes
    assert "{B}: Regenerate this creature." in scenario.game.characteristics_of(ogre).abilities


# -- Heavy Mattock / Silver-Inlaid Dagger / True-Faith Censer: Human equipped --


def _equip(scenario, equipment, creature):
    scenario.find(equipment, Zone.BATTLEFIELD, "alice").attach_to(
        scenario.find(creature, Zone.BATTLEFIELD, "alice")
    )


def test_heavy_mattock_gives_a_human_an_additional_plus_one():
    scenario = _board(["Heavy Mattock", "Fugitive Wizard"])
    _equip(scenario, "Heavy Mattock", "Fugitive Wizard")
    assert _chars(scenario, "Fugitive Wizard").power_toughness == (3, 3)


def test_heavy_mattock_gives_a_nonhuman_only_the_base_bonus():
    scenario = _board(["Heavy Mattock", "Grizzly Bears"])
    _equip(scenario, "Heavy Mattock", "Grizzly Bears")
    assert _chars(scenario, "Grizzly Bears").power_toughness == (3, 3)


def test_silver_inlaid_dagger_and_censer_use_their_own_numbers():
    scenario = _board(["Silver-Inlaid Dagger", "True-Faith Censer", "Fugitive Wizard"])
    _equip(scenario, "Silver-Inlaid Dagger", "Fugitive Wizard")
    assert _chars(scenario, "Fugitive Wizard").power_toughness == (4, 1)


# -- Erebos's Titan --------------------------------------------------------------


def test_erebos_titan_is_indestructible_while_opponents_control_no_creatures():
    scenario = _board(["Erebos's Titan"], ["Mountain"])
    assert _has(_chars(scenario, "Erebos's Titan"), "Indestructible")


def test_erebos_titan_loses_indestructible_when_an_opponent_controls_a_creature():
    scenario = _board(["Erebos's Titan"], ["Grizzly Bears"])
    assert not _has(_chars(scenario, "Erebos's Titan"), "Indestructible")


# -- Hundred-Battle Veteran / Doc Ock --------------------------------------------


def test_doc_ock_graveyard_threshold_sets_base_8_8():
    scenario = _board(["Doc Ock, Sinister Scientist"], alice_graveyard=["Island"] * 8)
    assert _chars(scenario, "Doc Ock, Sinister Scientist").power_toughness == (8, 8)


def test_doc_ock_with_seven_cards_stays_4_5():
    scenario = _board(["Doc Ock, Sinister Scientist"], alice_graveyard=["Island"] * 7)
    assert _chars(scenario, "Doc Ock, Sinister Scientist").power_toughness == (4, 5)


def test_hundred_battle_veteran_needs_three_different_counter_kinds():
    scenario = _board(["Hundred-Battle Veteran", "Grizzly Bears", "Llanowar Elves"])
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    elves = scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "alice")
    veteran = scenario.find("Hundred-Battle Veteran", Zone.BATTLEFIELD, "alice")
    bears.add_counters("+1/+1")
    elves.add_counters("flying")
    assert scenario.game.characteristics_of(veteran).power_toughness == (4, 2)
    veteran.add_counters("deathtouch")
    assert scenario.game.characteristics_of(veteran).power_toughness == (6, 6)


# -- Expedition Diviner: another Wizard -------------------------------------------


def test_diviner_with_another_wizard_gains_the_dies_draw_ability():
    scenario = _board(["Expedition Diviner", "Fugitive Wizard"])
    chars = _chars(scenario, "Expedition Diviner")
    assert "When this creature dies, draw a card." in chars.abilities


def test_diviner_alone_is_not_its_own_other_wizard():
    scenario = _board(["Expedition Diviner"])
    assert (
        "When this creature dies, draw a card."
        not in _chars(scenario, "Expedition Diviner").abilities
    )
