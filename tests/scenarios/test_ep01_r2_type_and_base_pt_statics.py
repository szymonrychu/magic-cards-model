"""Scenario: static type changes and base power/toughness sets over a group.

- "~ is also a Cleric, Rogue, Warrior, and Wizard." (Stonework Packbeast,
  Veteran Adventurer): layer 4 (CR 613.1d), additive (CR 205.1b).
- "All lands are Islands in addition to their other types." (Stormtide
  Leviathan): layer 4, and the basic land type brings its mana ability
  (CR 305.6), the opponent's lands included.
- "All nonland permanents are legendary." (Leyline of Singularity): layer 4
  supertype change.
- "Non-Archon creatures have base power and toughness 3/3." (Harmonious
  Archon) and "Other creatures have base power and toughness 1/1." (Godhead
  of Awe): sublayer 7b (CR 613.4b); +1/+1 counters still modify the new base
  in 7c (CR 613.4c).
"""

from magic_cards_model.models import Zone
from magic_cards_model.models.card import Supertype, Type
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def board(*alice, bob=()):
    return (
        Scenario()
        .player("alice", battlefield=list(alice))
        .player("bob", battlefield=list(bob))
        .build()
    )


def chars(scenario, state):
    return scenario.game.characteristics_of(state)


def pt(scenario, state):
    return chars(scenario, state).power_toughness


# -- "is also a Cleric, Rogue, Warrior, and Wizard" --------------------------


def test_the_source_gains_every_listed_type_and_keeps_its_own():
    scenario = board("Stonework Packbeast", "Veteran Adventurer")
    for name, own in (("Stonework Packbeast", "Beast"), ("Veteran Adventurer", "Human")):
        subtypes = set(chars(scenario, scenario.creature(name)).subtypes)
        assert {own, "Cleric", "Rogue", "Warrior", "Wizard"} <= subtypes


def test_the_type_change_is_only_on_the_source():
    scenario = board("Stonework Packbeast", "Grizzly Bears")

    assert "Cleric" not in chars(scenario, scenario.creature("Grizzly Bears")).subtypes


def test_the_type_is_not_there_once_the_source_is_off_the_battlefield():
    """CR 604.2: a static ability works only on the battlefield."""
    scenario = board("Stonework Packbeast")
    beast = scenario.creature("Stonework Packbeast")
    scenario.game.put_into_graveyard(beast)

    assert beast.zone is Zone.GRAVEYARD
    assert "Cleric" not in chars(scenario, beast).subtypes


# -- "All lands are Islands in addition to their other types" ----------------


def test_every_land_of_both_players_is_an_island_with_its_mana_ability():
    scenario = board("Stormtide Leviathan", "Forest", bob=["Mountain"])
    forest = scenario.find("Forest", Zone.BATTLEFIELD)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "bob")

    for land, own in ((forest, "Forest"), (mountain, "Mountain")):
        found = chars(scenario, land)
        assert {own, "Island"} <= set(found.subtypes)
        assert "{T}: Add {U}." in found.abilities


def test_a_nonland_permanent_is_not_an_island():
    scenario = board("Stormtide Leviathan", "Grizzly Bears")

    assert "Island" not in chars(scenario, scenario.creature("Grizzly Bears")).subtypes


# -- "All nonland permanents are legendary" ---------------------------------


def test_nonland_permanents_are_legendary_for_everyone_and_lands_are_not():
    scenario = board("Leyline of Singularity", "Grizzly Bears", "Forest", bob=["Grizzly Bears"])
    mine = scenario.creature("Grizzly Bears")
    theirs = scenario.creature("Grizzly Bears", "bob")
    forest = scenario.find("Forest", Zone.BATTLEFIELD)

    assert Supertype.LEGENDARY in chars(scenario, mine).supertypes
    assert Supertype.LEGENDARY in chars(scenario, theirs).supertypes
    assert Supertype.LEGENDARY not in chars(scenario, forest).supertypes


# -- base power and toughness ----------------------------------------------


def test_non_archon_creatures_have_base_3_3_and_the_archon_keeps_its_own():
    scenario = board("Harmonious Archon", "Grizzly Bears", bob=["Wind Drake"])
    archon = scenario.creature("Harmonious Archon")
    drake = scenario.creature("Wind Drake", "bob")

    assert pt(scenario, scenario.creature("Grizzly Bears")) == (3, 3)
    assert pt(scenario, drake) == (3, 3)
    assert pt(scenario, archon) == (int(archon.card.power), int(archon.card.toughness))


def test_a_counter_modifies_the_new_base_in_layer_7c():
    scenario = board("Harmonious Archon", "Grizzly Bears")
    bears = scenario.creature("Grizzly Bears")
    bears.add_counters(Counter.PLUS_ONE, 2)

    assert pt(scenario, bears) == (5, 5)


def test_other_creatures_have_base_1_1_whoever_controls_them():
    scenario = board("Godhead of Awe", "Serra Angel", bob=["Serra Angel"])
    godhead = scenario.creature("Godhead of Awe")
    mine = scenario.creature("Serra Angel")
    theirs = scenario.creature("Serra Angel", "bob")

    assert pt(scenario, mine) == (1, 1)
    assert pt(scenario, theirs) == (1, 1)
    assert pt(scenario, godhead) == (int(godhead.card.power), int(godhead.card.toughness))
    assert Type.CREATURE in chars(scenario, mine).types


def test_the_base_set_ends_when_the_source_leaves():
    scenario = board("Godhead of Awe", "Serra Angel")
    godhead = scenario.creature("Godhead of Awe")
    angel = scenario.creature("Serra Angel")
    scenario.game.put_into_graveyard(godhead)

    assert pt(scenario, angel) == (4, 4)
