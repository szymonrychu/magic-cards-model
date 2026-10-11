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
from magic_cards_model.models.card_state import Choice, ChoiceKind, Counter
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


# -- "lose all abilities and have base power and toughness N/N" -------------


def test_creature_tokens_you_control_lose_abilities_and_are_3_3():
    """Poppet Stitcher: layer 6 removal (CR 613.1f) and a 7b set (CR 613.4b),
    only for tokens its controller owns."""
    from magic_cards_model.models.token import token_copy_of

    scenario = board("Poppet Stitcher", "Serra Angel", bob=["Serra Angel"])
    scenario.creature("Poppet Stitcher").transform()  # the static line is Poppet Factory's
    angel = scenario.creature("Serra Angel")
    (token,) = token_copy_of(scenario.game, angel, "alice")
    theirs = scenario.creature("Serra Angel", "bob")
    (their_token,) = token_copy_of(scenario.game, theirs, "bob")

    found = chars(scenario, token)
    assert found.power_toughness == (3, 3)
    assert not any("flying" in line.lower() for line in found.abilities)
    assert pt(scenario, angel) == (4, 4), "a nontoken creature is outside the group"
    assert pt(scenario, their_token) == (4, 4), "the opponent's token is outside the group"


def test_non_horror_creatures_with_slime_counters_lose_abilities_and_are_2_2():
    """Sludge Monster: a counter-qualified group, "non-Horror" excluding the
    Monster itself even when it carries a slime counter."""
    scenario = board("Sludge Monster", "Serra Angel", "Grizzly Bears", bob=["Serra Angel"])
    marked = scenario.creature("Serra Angel")
    marked.add_counters("slime", 1)
    theirs = scenario.creature("Serra Angel", "bob")
    theirs.add_counters("slime", 1)
    monster = scenario.creature("Sludge Monster")
    monster.add_counters("slime", 1)
    bears = scenario.creature("Grizzly Bears")

    assert pt(scenario, marked) == (2, 2)
    assert not any("flying" in line.lower() for line in chars(scenario, marked).abilities)
    assert pt(scenario, theirs) == (2, 2), "no 'you control': both players' creatures"
    assert pt(scenario, monster) == (int(monster.card.power), int(monster.card.toughness))
    assert pt(scenario, bears) == (int(bears.card.power), int(bears.card.toughness))


# -- type and colour sets that also reach cards off the battlefield ----------

from magic_cards_model.models.card import Color  # noqa: E402


def zone_board(alice, bob=None):
    scenario = Scenario().player("alice", **alice).player("bob", **(bob or {})).build()
    return scenario


def subtypes_of(scenario, state):
    return set(scenario.game.characteristics_of(state).subtypes)


def test_maskwood_nexus_makes_your_creatures_every_creature_type():
    """CR 613.1d / CR 205.3d: the Nexus' controller's creatures, not the opponent's."""
    scenario = zone_board(
        {"battlefield": ["Maskwood Nexus", "Grizzly Bears"]},
        {"battlefield": ["Grizzly Bears"]},
    )
    mine = scenario.creature("Grizzly Bears")
    theirs = scenario.creature("Grizzly Bears", "bob")

    assert {"Elf", "Goblin", "Bear"} <= subtypes_of(scenario, mine)
    assert "Elf" not in subtypes_of(scenario, theirs)


def test_maskwood_nexus_reaches_creature_cards_you_own_off_the_battlefield():
    scenario = zone_board(
        {
            "battlefield": ["Maskwood Nexus"],
            "hand": ["Grizzly Bears", "Divination"],
            "graveyard": ["Llanowar Elves"],
        },
        {"hand": ["Grizzly Bears"]},
    )
    in_hand = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    spell = scenario.find("Divination", Zone.HAND, "alice")
    in_graveyard = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")
    theirs = scenario.find("Grizzly Bears", Zone.HAND, "bob")

    assert "Goblin" in subtypes_of(scenario, in_hand)
    assert "Goblin" in subtypes_of(scenario, in_graveyard)
    assert "Goblin" not in subtypes_of(scenario, spell), "not a creature card"
    assert "Goblin" not in subtypes_of(scenario, theirs), "someone else's card"


def test_maskwood_nexus_ends_with_its_source():
    scenario = zone_board({"battlefield": ["Maskwood Nexus"], "hand": ["Grizzly Bears"]})
    in_hand = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    scenario.game.put_into_graveyard(scenario.find("Maskwood Nexus", Zone.BATTLEFIELD))

    assert "Goblin" not in subtypes_of(scenario, in_hand)


def test_conspiracy_sets_the_chosen_type_and_drops_the_old_ones():
    """CR 205.1a: "are the chosen type" replaces the creature types."""
    scenario = zone_board(
        {"battlefield": ["Conspiracy", "Grizzly Bears"], "hand": ["Llanowar Elves"]},
    )
    scenario.find("Conspiracy", Zone.BATTLEFIELD).choice = Choice(
        kind=ChoiceKind.CREATURE_TYPE, value="Goblin"
    )
    bears = scenario.creature("Grizzly Bears")
    elves = scenario.find("Llanowar Elves", Zone.HAND, "alice")

    assert subtypes_of(scenario, bears) == {"Goblin"}
    assert subtypes_of(scenario, elves) == {"Goblin"}


def test_celestial_dawn_makes_your_lands_plains_and_nonland_cards_white():
    scenario = zone_board(
        {
            "battlefield": ["Celestial Dawn", "Forest", "Grizzly Bears"],
            "hand": ["Divination", "Island"],
        },
        {"battlefield": ["Forest"]},
    )
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    theirs = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    bears = scenario.creature("Grizzly Bears")
    divination = scenario.find("Divination", Zone.HAND, "alice")
    island = scenario.find("Island", Zone.HAND, "alice")

    assert subtypes_of(scenario, forest) == {"Plains"}
    assert subtypes_of(scenario, theirs) == {"Forest"}
    assert scenario.game.characteristics_of(bears).colors == (Color.WHITE,)
    assert scenario.game.characteristics_of(divination).colors == (Color.WHITE,)
    assert scenario.game.characteristics_of(island).colors == ()


def test_mycosynth_lattice_makes_everything_colorless_everywhere():
    scenario = zone_board(
        {"battlefield": ["Mycosynth Lattice", "Grizzly Bears"], "hand": ["Divination"]},
        {"hand": ["Lightning Bolt"], "battlefield": ["Llanowar Elves"]},
    )
    bears = scenario.creature("Grizzly Bears")
    elves = scenario.creature("Llanowar Elves", "bob")
    divination = scenario.find("Divination", Zone.HAND, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")

    for state in (bears, elves, divination, bolt):
        assert scenario.game.characteristics_of(state).colors == (), state.name
