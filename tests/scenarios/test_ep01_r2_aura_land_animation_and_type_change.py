"""Scenario: an Aura or Equipment that rewrites what the permanent it is
attached to *is* (EP-01 round 2, task T5).

- Land animation (Zendikons, Emergences, Living Terrain, Awaken the Ancient):
  "Enchanted land is a 2/2 blue Elemental creature with flying. It's still a
  land." - the land keeps its land type, land subtypes and mana ability and
  adds the creature type (CR 613.1d, CR 205.1b), the colour is set (CR 613.1e),
  the keyword is granted (CR 613.1f) and the base power and toughness is set in
  sublayer 7b (CR 613.4b).
- Loses all abilities plus a base power and toughness (Kasmina's
  Transmutation, Utter Insignificance), optionally with a new name, colours and
  creature types (Honest Work, Witness Protection): a +1/+1 counter still adds
  on top of the set (CR 613.4c after CR 613.4b).
- A permanent turned into another kind of thing (Imprisoned in the Moon, Sugar
  Coat, Minimus Containment): its card types and subtypes are replaced
  (CR 205.1a) and the quoted ability granted is a real one.
- Smaller rewrites: "is snow", "is legendary", "is a Demon Spirit", "loses
  flying", "has indestructible", "has ward {1}", "has nonbasic landwalk",
  "loses all land types and abilities and has ..." (Lithoform Blight).

Each family has a positive, a negative (a permanent the Aura is not on is
untouched) and an unattach (everything comes back off, CR 604.2).
"""

import pytest

from magic_cards_model.machines import Step, keywords
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color, Supertype, Type
from tests.scenarios.harness import Scenario


def attach(scenario: Scenario, name: str, target, username: str = "alice"):
    permanent = scenario.find(name, Zone.BATTLEFIELD, username)
    permanent.attach_to(target)
    return permanent


def chars(scenario: Scenario, permanent):
    return scenario.game.characteristics_of(permanent)


def land_board(aura: str, land: str = "Forest"):
    scenario = Scenario().player("alice", battlefield=[aura, land, land]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.creatures(land, land, username="alice") if False else (None, None)
    lands = [s for s in scenario.game.battlefield if s.name == land]
    return scenario, lands[0], lands[1]


def mana_ability_index(scenario: Scenario, permanent, text: str) -> int:
    assert text in chars(scenario, permanent).abilities, chars(scenario, permanent).abilities
    (index,) = [
        i
        for i, ability in enumerate(scenario.game.activated_abilities(permanent))
        if f"{ability.cost}: {ability.effect}" == text
    ]
    return index


# --------------------------------------------------------------------------
# Land animation
# --------------------------------------------------------------------------

ANIMATIONS = [
    # card, land, (power, toughness), colours, creature type, keywords
    ("Awaken the Ancient", "Mountain", (7, 7), {Color.RED}, "Giant", {"Haste"}),
    ("Wind Zendikon", "Forest", (2, 2), {Color.BLUE}, "Elemental", {"Flying"}),
    ("Guardian Zendikon", "Forest", (2, 6), {Color.WHITE}, "Wall", {"Defender"}),
    ("Corrupted Zendikon", "Forest", (3, 3), {Color.BLACK}, "Ooze", set()),
    ("Crusher Zendikon", "Forest", (4, 2), {Color.RED}, "Beast", {"Trample"}),
    ("Vastwood Zendikon", "Forest", (6, 4), {Color.GREEN}, "Elemental", set()),
    ("Nissa's Zendikon", "Forest", (4, 4), set(), "Elemental", {"Reach", "Haste"}),
    ("Crackling Emergence", "Forest", (3, 3), {Color.RED}, "Spirit", {"Haste"}),
    (
        "Harmonious Emergence",
        "Forest",
        (4, 5),
        {Color.GREEN},
        "Spirit",
        {"Vigilance", "Haste"},
    ),
    ("Living Terrain", "Forest", (5, 6), {Color.GREEN}, "Treefolk", set()),
]


@pytest.mark.parametrize(("aura", "land", "pt", "colors", "creature_type", "keywords"), ANIMATIONS)
def test_the_enchanted_land_is_a_creature_that_is_still_a_land(
    aura, land, pt, colors, creature_type, keywords
):
    scenario, enchanted, other = land_board(aura, land)
    attach(scenario, aura, enchanted)

    animated = chars(scenario, enchanted)
    assert Type.CREATURE in animated.types
    assert Type.LAND in animated.types, "'It's still a land'"
    assert land in animated.subtypes, "the land types stay (CR 205.1b)"
    assert creature_type in animated.subtypes
    assert animated.power_toughness == pt
    assert set(animated.colors) == colors
    for keyword in keywords:
        assert animated.has_ability(keyword), keyword

    untouched = chars(scenario, other)
    assert Type.CREATURE not in untouched.types, "the other land is not enchanted"
    assert untouched.power_toughness == (None, None)


def test_the_animated_land_still_taps_for_mana():
    scenario, forest, _ = land_board("Wind Zendikon")
    attach(scenario, "Wind Zendikon", forest)
    scenario.activate(forest, index=0, color=Color.GREEN)
    assert forest.tapped
    assert scenario.player().mana_pool.floating == {Color.GREEN: 1}


def test_an_unattached_animation_aura_changes_nothing():
    scenario, forest, _ = land_board("Living Terrain")
    aura = attach(scenario, "Living Terrain", forest)
    assert chars(scenario, forest).power_toughness == (5, 6)
    aura.unattach()
    plain = chars(scenario, forest)
    assert Type.CREATURE not in plain.types
    assert plain.power_toughness == (None, None)
    assert plain.colors == ()


def test_a_counter_still_adds_on_top_of_the_animated_base():
    scenario, forest, _ = land_board("Wind Zendikon")
    attach(scenario, "Wind Zendikon", forest)
    forest.add_counters("+1/+1", 2)
    assert chars(scenario, forest).power_toughness == (4, 4), "7b sets 2/2, then 7c adds +2/+2"


# --------------------------------------------------------------------------
# Glittering Frost / Lithoform Blight
# --------------------------------------------------------------------------


def test_glittering_frost_makes_the_land_snow_and_keeps_it_a_basic_land():
    scenario, forest, other = land_board("Glittering Frost")
    aura = attach(scenario, "Glittering Frost", forest)
    snowy = chars(scenario, forest)
    assert Supertype.SNOW in snowy.supertypes
    assert Supertype.BASIC in snowy.supertypes, "CR 205.4b: other supertypes are retained"
    assert Supertype.SNOW not in chars(scenario, other).supertypes
    aura.unattach()
    assert Supertype.SNOW not in chars(scenario, forest).supertypes


def test_lithoform_blight_replaces_the_lands_mana_with_the_two_quoted_abilities():
    scenario, forest, other = land_board("Lithoform Blight")
    aura = attach(scenario, "Lithoform Blight", forest)
    blighted = chars(scenario, forest)
    assert "Forest" not in blighted.subtypes, "loses all land types"
    assert Type.LAND in blighted.types
    assert "{T}: Add {C}" in blighted.abilities
    assert "{T}, Pay 1 life: Add one mana of any color." in blighted.abilities

    index = mana_ability_index(scenario, forest, "{T}: Add {C}")
    scenario.activate(forest, index=index)
    assert scenario.player().mana_pool.floating == {Color.COLORLESS: 1}, "no green any more"

    assert "Forest" in chars(scenario, other).subtypes
    aura.unattach()
    assert "Forest" in chars(scenario, forest).subtypes


def test_lithoform_blight_second_ability_pays_a_life_for_any_color():
    scenario, forest, _ = land_board("Lithoform Blight")
    attach(scenario, "Lithoform Blight", forest)
    life = scenario.player().life
    index = mana_ability_index(scenario, forest, "{T}, Pay 1 life: Add one mana of any color.")
    scenario.activate(forest, index=index, color=Color.BLUE)
    assert scenario.player().mana_pool.floating == {Color.BLUE: 1}
    assert scenario.player().life == life - 1


# --------------------------------------------------------------------------
# Loses all abilities and has base power and toughness
# --------------------------------------------------------------------------


def creature_board(aura: str, *, aura_owner: str = "alice", creature_owner: str = "alice"):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[aura] if aura_owner == "alice" else [],
        )
        .player("bob", battlefield=[aura] if aura_owner == "bob" else [])
        .build()
    )
    return scenario


@pytest.mark.parametrize("aura", ["Kasmina's Transmutation", "Utter Insignificance"])
def test_loses_all_abilities_and_becomes_a_one_one(aura):
    scenario = (
        Scenario()
        .player("alice", battlefield=[aura])
        .player("bob", battlefield=["Birds of Paradise", "Birds of Paradise"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    birds, other = scenario.creatures("Birds of Paradise", "Birds of Paradise", username="bob")
    birds.add_counters("+1/+1", 1)
    attach(scenario, aura, birds)

    changed = chars(scenario, birds)
    assert not changed.has_ability("Flying")
    assert not any("Add" in line for line in changed.abilities), "the mana ability is gone"
    assert changed.power_toughness == (2, 2), "base 1/1 (7b) plus the counter (7c)"
    assert chars(scenario, other).has_ability("Flying"), "the other Birds is untouched"
    assert chars(scenario, other).power_toughness == (0, 1)


def test_kasmina_unattached_restores_the_creature():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Kasmina's Transmutation"])
        .player("bob", battlefield=["Birds of Paradise"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    birds = scenario.creature("Birds of Paradise", "bob")
    aura = attach(scenario, "Kasmina's Transmutation", birds)
    assert not chars(scenario, birds).has_ability("Flying")
    aura.unattach()
    assert chars(scenario, birds).has_ability("Flying")
    assert chars(scenario, birds).power_toughness == (0, 1)


def test_honest_work_makes_a_named_citizen_merchant_with_a_mana_ability():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Honest Work"])
        .player("bob", battlefield=["Birds of Paradise"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    birds = scenario.creature("Birds of Paradise", "bob")
    attach(scenario, "Honest Work", birds)

    merchant = chars(scenario, birds)
    assert merchant.name == "Humble Merchant"
    assert [s for s in merchant.subtypes if s != "Citizen"] == [], "loses all other creature types"
    assert "Citizen" in merchant.subtypes
    assert merchant.power_toughness == (1, 1)
    assert not merchant.has_ability("Flying")
    assert "{T}: Add {C}" in merchant.abilities or "{T}: Add {C}." in merchant.abilities
    assert Type.CREATURE in merchant.types


def test_witness_protection_sets_colours_types_name_and_base_pt():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Witness Protection"])
        .player("bob", battlefield=["Birds of Paradise"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    birds = scenario.creature("Birds of Paradise", "bob")
    aura = attach(scenario, "Witness Protection", birds)

    citizen = chars(scenario, birds)
    assert citizen.name == "Legitimate Businessperson"
    assert set(citizen.colors) == {Color.GREEN, Color.WHITE}
    assert citizen.types == (Type.CREATURE,)
    assert citizen.subtypes == ("Citizen",)
    assert citizen.power_toughness == (1, 1)
    assert not citizen.has_ability("Flying")

    aura.unattach()
    assert chars(scenario, birds).name == "Birds of Paradise"


def test_withercrown_sets_only_base_power_and_grants_an_upkeep_trigger():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Withercrown", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    aura = attach(scenario, "Withercrown", bears)

    changed = chars(scenario, bears)
    assert changed.power_toughness == (0, 2), "base power 0, toughness untouched"
    assert any("At the beginning of your upkeep" in line for line in changed.abilities)
    aura.unattach()
    assert chars(scenario, bears).power_toughness == (2, 2)


def test_oni_possession_makes_the_creature_a_demon_spirit():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Oni Possession", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    aura = attach(scenario, "Oni Possession", bears)
    changed = chars(scenario, bears)
    assert set(changed.subtypes) == {"Demon", "Spirit"}, "CR 205.1a: Bear is replaced"
    assert changed.power_toughness == (5, 5)
    aura.unattach()
    assert chars(scenario, bears).subtypes == ("Bear",)


def test_grounded_takes_flying_away_and_only_flying():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grounded"])
        .player("bob", battlefield=["Birds of Paradise"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    birds = scenario.creature("Birds of Paradise", "bob")
    aura = attach(scenario, "Grounded", birds)
    assert not chars(scenario, birds).has_ability("Flying")
    assert any("Add" in line for line in chars(scenario, birds).abilities), "mana ability stays"
    aura.unattach()
    assert chars(scenario, birds).has_ability("Flying")


# --------------------------------------------------------------------------
# Permanent subjects: indestructible, ward, legendary
# --------------------------------------------------------------------------


def test_indestructibility_gives_any_permanent_indestructible():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Indestructibility", "Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = [s for s in scenario.game.battlefield if s.name == "Forest"]
    aura = attach(scenario, "Indestructibility", first)
    assert chars(scenario, first).has_ability("Indestructible")
    assert not chars(scenario, second).has_ability("Indestructible")
    aura.unattach()
    assert not chars(scenario, first).has_ability("Indestructible")


def test_in_bolass_clutches_makes_the_permanent_legendary_and_gives_control():
    scenario = (
        Scenario()
        .player("alice", battlefield=["In Bolas's Clutches"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    aura = attach(scenario, "In Bolas's Clutches", bears)
    taken = chars(scenario, bears)
    assert Supertype.LEGENDARY in taken.supertypes
    assert taken.controller == "alice"
    aura.unattach()
    assert Supertype.LEGENDARY not in chars(scenario, bears).supertypes
    assert chars(scenario, bears).controller == "bob"


# --------------------------------------------------------------------------
# Imprisoned in the Moon / Sugar Coat / Minimus Containment
# --------------------------------------------------------------------------


def test_imprisoned_in_the_moon_turns_a_creature_into_a_colourless_land():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Imprisoned in the Moon"])
        .player("bob", battlefield=["Birds of Paradise"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    birds = scenario.creature("Birds of Paradise", "bob")
    aura = attach(scenario, "Imprisoned in the Moon", birds)

    land = chars(scenario, birds)
    assert land.types == (Type.LAND,)
    assert land.subtypes == ()
    assert land.colors == ()
    assert land.abilities == ("{T}: Add {C}",) or land.abilities == ("{T}: Add {C}.",)
    assert land.power_toughness == (None, None) or not land.is_creature

    aura.unattach()
    assert chars(scenario, birds).is_creature


def test_imprisoned_in_the_moon_on_a_land_replaces_its_mana_with_colourless():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Imprisoned in the Moon", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    attach(scenario, "Imprisoned in the Moon", forest)
    land = chars(scenario, forest)
    assert land.subtypes == (), "the Forest type is a land type correlated... and it is lost"
    index = mana_ability_index(scenario, forest, "{T}: Add {C}")
    scenario.activate(forest, index=index)
    assert scenario.player().mana_pool.floating == {Color.COLORLESS: 1}


def test_sugar_coat_makes_the_creature_a_colourless_food_artifact():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Sugar Coat"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    aura = attach(scenario, "Sugar Coat", bears)

    food = chars(scenario, bears)
    assert food.types == (Type.ARTIFACT,)
    assert food.subtypes == ("Food",)
    assert food.colors == ()
    assert "{2}, {T}, Sacrifice this artifact: You gain 3 life" in food.abilities
    aura.unattach()
    assert chars(scenario, bears).is_creature


def test_minimus_containment_makes_the_permanent_a_treasure_that_loses_other_abilities():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Minimus Containment"])
        .player("bob", battlefield=["Birds of Paradise"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    birds = scenario.creature("Birds of Paradise", "bob") if False else None
    birds = [s for s in scenario.game.battlefield if s.name == "Birds of Paradise"][0]
    aura = attach(scenario, "Minimus Containment", birds)

    treasure = chars(scenario, birds)
    assert treasure.types == (Type.ARTIFACT,)
    assert treasure.subtypes == ("Treasure",)
    assert not treasure.has_ability("Flying")
    assert "{T}, Sacrifice this artifact: Add one mana of any color" in " ".join(treasure.abilities)
    aura.unattach()
    assert chars(scenario, birds).is_creature


# --------------------------------------------------------------------------
# Hardlight Containment / Trailblazer's Boots
# --------------------------------------------------------------------------


def test_hardlight_containment_gives_the_enchanted_artifact_ward():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hardlight Containment", "Bonesplitter"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    aura = attach(scenario, "Hardlight Containment", splitter)
    assert chars(scenario, splitter).has_ability("Ward {1}")
    aura.unattach()
    assert not chars(scenario, splitter).has_ability("Ward {1}")


def test_trailblazers_boots_make_the_creature_unblockable_against_a_nonbasic_land():
    def board(defender_lands):
        scenario = (
            Scenario()
            .player("alice", battlefield=["Trailblazer's Boots", "Grizzly Bears"])
            .player("bob", battlefield=["Grizzly Bears", *defender_lands])
            .build()
        )
        scenario.start_at(Step.BEGINNING_OF_COMBAT)
        bears = scenario.creature("Grizzly Bears", "alice")
        attach(scenario, "Trailblazer's Boots", bears)
        scenario.advance()
        return scenario, bears

    scenario, bears = board(["Llanowar Wastes"])
    assert chars(scenario, bears).has_ability("Nonbasic landwalk")
    scenario.attack_with(bears, defending="bob")
    blocker = scenario.creature("Grizzly Bears", "bob")
    with pytest.raises(Exception, match="landwalk"):
        scenario.block(bears, blocker)

    scenario, bears = board(["Forest"])
    scenario.attack_with(bears, defending="bob")
    blocker = scenario.creature("Grizzly Bears", "bob")
    scenario.block(bears, blocker)


# --------------------------------------------------------------------------
# Consecrate Land: indestructible and "can't be enchanted by other Auras"
# --------------------------------------------------------------------------


def consecrate_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Consecrate Land", "Wind Zendikon", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = [s for s in scenario.game.battlefield if s.name == "Forest"]
    return scenario, first, second


def test_consecrate_land_makes_the_land_indestructible():
    scenario, forest, other = consecrate_board()
    aura = attach(scenario, "Consecrate Land", forest)
    assert chars(scenario, forest).has_ability("Indestructible")
    assert not chars(scenario, other).has_ability("Indestructible")
    aura.unattach()
    assert not chars(scenario, forest).has_ability("Indestructible")


def test_consecrate_land_refuses_another_aura_on_the_same_land():
    """CR 303.4: "Other effects can limit what a permanent can be enchanted
    by." - the refusal comes from the announcement's own legality check."""
    scenario, forest, other = consecrate_board()
    attach(scenario, "Consecrate Land", forest)
    zendikon = scenario.find("Wind Zendikon", Zone.BATTLEFIELD, "alice")
    assert "can't be enchanted by other Auras" in keywords.why_cannot_enchant(
        zendikon, forest, "alice", scenario.game
    )
    assert keywords.why_cannot_enchant(zendikon, other, "alice", scenario.game) is None


def test_an_aura_already_on_the_land_falls_off_when_consecrate_land_arrives():
    """CR 303.4c: an Aura enchanting an illegal object is put into the
    graveyard - 'other applicable effects' include Consecrate Land's."""
    scenario, forest, _ = consecrate_board()
    zendikon = attach(scenario, "Wind Zendikon", forest)
    consecrate = attach(scenario, "Consecrate Land", forest)
    scenario.state_based_actions()
    assert zendikon.zone is Zone.GRAVEYARD
    assert consecrate.zone is Zone.BATTLEFIELD, "Consecrate Land is not 'other' than itself"
    assert consecrate.attached_to == forest.id


# --------------------------------------------------------------------------
# Metamorphic Alteration: "Enchanted creature is a copy of the chosen creature."
# --------------------------------------------------------------------------


def test_metamorphic_alteration_copies_the_creature_chosen_as_it_entered():
    """CR 614.12a records the choice as the Aura enters; the copy effect is
    layer 1 (CR 613.1a) and keeps the copied creature's name, types, colours,
    abilities and power and toughness (CR 707.2) while counters stay."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Metamorphic Alteration"],
            battlefield=["Island", "Island", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Birds of Paradise"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    birds = scenario.creature("Birds of Paradise", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters("+1/+1", 1)
    islands = scenario.untapped_sources("Island", "Island", username="alice")
    scenario.will_choose_cards(birds, source="Metamorphic Alteration")
    aura = scenario.cast_and_resolve("Metamorphic Alteration", *islands, targets=[bears])
    assert aura.attached_to == bears.id

    copy = chars(scenario, bears)
    assert copy.name == "Birds of Paradise"
    assert copy.has_ability("Flying")
    assert copy.power_toughness == (1, 2), "a 0/1 Bird copy keeps its +1/+1 counter"
    assert chars(scenario, birds).name == "Birds of Paradise"
    aura.unattach()
    assert chars(scenario, bears).name == "Grizzly Bears"
