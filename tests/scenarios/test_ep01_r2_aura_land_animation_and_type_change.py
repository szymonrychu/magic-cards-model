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
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.mana import ManaCost
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


# --------------------------------------------------------------------------
# One-shot rewrites: an activated or triggered ability that makes a permanent
# something else for a while (CR 611.2, CR 613.1d/e/f)
# --------------------------------------------------------------------------


def one_shot_board(alice: list[str], bob: list[str] | None = None, **zones):
    scenario = (
        Scenario().player("alice", battlefield=alice, **zones).player("bob", battlefield=bob or [])
    )
    built = scenario.build()
    built.start_at(Step.PRECOMBAT_MAIN)
    return built


def on_battlefield(scenario: Scenario, name: str, username: str = "alice"):
    return [s for s in scenario.game.battlefield if s.name == name and s.controller == username]


def past_cleanup(scenario: Scenario) -> None:
    """Run the turn through its cleanup step (CR 514.2: "until end of turn"
    effects end there)."""
    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup


def test_floodchaser_turns_a_target_land_into_an_island_until_end_of_turn():
    """CR 305.7: setting a land's subtype to a basic land type replaces its old
    land types and rules-text abilities, and the new type brings its mana
    ability (CR 305.6)."""
    scenario = one_shot_board(["Floodchaser", "Island", "Forest", "Forest"])
    floodchaser = on_battlefield(scenario, "Floodchaser")[0]
    floodchaser.add_counters("+1/+1", 6)
    island = on_battlefield(scenario, "Island")[0]
    forest, other = on_battlefield(scenario, "Forest")
    scenario.activate(floodchaser, island, targets=[forest])
    scenario.pass_until_resolved()
    assert floodchaser.counter_count("+1/+1") == 5, "the counter is a cost"

    changed = chars(scenario, forest)
    assert changed.subtypes == ("Island",)
    assert changed.has_ability("{T}: Add {U}.")
    assert not changed.has_ability("{T}: Add {G}.")
    assert chars(scenario, other).subtypes == ("Forest",), "only the target changes"

    past_cleanup(scenario)
    assert chars(scenario, forest).subtypes == ("Forest",), "it ends with the turn"
    assert not chars(scenario, forest).has_ability("{T}: Add {U}.")


def test_sealock_monster_makes_a_target_land_an_island_in_addition_when_monstrous():
    """CR 305.7 does not apply: "in addition to its other types" adds the
    Island type (CR 205.1b) and its mana ability, and no duration is stated, so
    the land stays an Island (CR 611.2a)."""
    scenario = one_shot_board(["Sealock Monster"] + ["Island"] * 7 + ["Forest", "Forest"])
    monster = on_battlefield(scenario, "Sealock Monster")[0]
    forest, other = on_battlefield(scenario, "Forest")
    islands = scenario.untapped_sources(*["Island"] * 7, username="alice")
    scenario.choose_trigger_targets("Sealock Monster", [forest])
    scenario.activate(monster, *islands[:7])
    scenario.pass_until_resolved()
    assert monster.counter_count("+1/+1") == 3
    scenario.pass_until_resolved()

    changed = chars(scenario, forest)
    assert set(changed.subtypes) == {"Forest", "Island"}
    assert changed.has_ability("{T}: Add {U}.")
    assert chars(scenario, other).subtypes == ("Forest",)

    past_cleanup(scenario)
    assert "Island" in chars(scenario, forest).subtypes, "no duration: it lasts"


def test_pixie_illusionist_makes_a_land_the_basic_land_type_of_your_choice():
    scenario = one_shot_board(["Pixie Illusionist", "Forest", "Forest"])
    pixie = on_battlefield(scenario, "Pixie Illusionist")[0]
    forest, other = on_battlefield(scenario, "Forest")
    scenario.will_choose("Swamp", source="Pixie Illusionist")
    scenario.activate(pixie, targets=[forest])
    scenario.pass_until_resolved()

    changed = chars(scenario, forest)
    assert changed.subtypes == ("Swamp",)
    assert changed.has_ability("{T}: Add {B}.")
    assert chars(scenario, other).subtypes == ("Forest",)

    past_cleanup(scenario)
    assert chars(scenario, forest).subtypes == ("Forest",)


def test_unctus_makes_a_creature_a_blue_artifact_in_addition_to_what_it_is():
    scenario = one_shot_board(["Unctus, Grand Metatect", "Island", "Grizzly Bears", "Typhoid Rats"])
    unctus = on_battlefield(scenario, "Unctus, Grand Metatect")[0]
    bears = on_battlefield(scenario, "Grizzly Bears")[0]
    rats = on_battlefield(scenario, "Typhoid Rats")[0]
    island = on_battlefield(scenario, "Island")[0]
    scenario.activate(unctus, island, targets=[bears])
    scenario.pass_until_resolved()

    changed = chars(scenario, bears)
    assert Type.ARTIFACT in changed.types and Type.CREATURE in changed.types
    assert set(changed.colors) == {Color.GREEN, Color.BLUE}, "in addition to its other colors"
    assert "Bear" in changed.subtypes
    assert Type.ARTIFACT not in chars(scenario, rats).types

    past_cleanup(scenario)
    after = chars(scenario, bears)
    assert Type.ARTIFACT not in after.types
    assert set(after.colors) == {Color.GREEN}


def test_boldwyr_intimidator_turns_a_creature_into_a_coward_or_a_warrior():
    """CR 205.1a: setting a creature type replaces the old creature types."""
    scenario = one_shot_board(
        ["Boldwyr Intimidator", "Mountain", "Mountain", "Mountain", "Mountain"],
        ["Grizzly Bears", "Typhoid Rats"],
    )
    intimidator = on_battlefield(scenario, "Boldwyr Intimidator")[0]
    mountains = scenario.untapped_sources(*["Mountain"] * 4, username="alice")
    bears = on_battlefield(scenario, "Grizzly Bears", "bob")[0]
    rats = on_battlefield(scenario, "Typhoid Rats", "bob")[0]
    scenario.activate(intimidator, mountains[0], index=0, targets=[bears])
    scenario.pass_until_resolved()
    assert chars(scenario, bears).subtypes == ("Coward",)
    scenario.activate(intimidator, *mountains[1:], index=1, targets=[rats])
    scenario.pass_until_resolved()
    assert chars(scenario, rats).subtypes == ("Warrior",)
    assert chars(scenario, intimidator).subtypes != ("Coward",)

    past_cleanup(scenario)
    assert chars(scenario, bears).subtypes == ("Bear",)
    assert chars(scenario, rats).subtypes == ("Rat",)


def test_nullhide_ferox_loses_all_abilities_until_end_of_turn():
    scenario = one_shot_board(["Nullhide Ferox", "Forest", "Forest"])
    ferox = on_battlefield(scenario, "Nullhide Ferox")[0]
    forests = scenario.untapped_sources("Forest", "Forest", username="alice")
    assert chars(scenario, ferox).has_ability("Hexproof")
    scenario.activate(ferox, *forests, index=0)
    scenario.pass_until_resolved()
    assert not chars(scenario, ferox).has_ability("Hexproof")
    assert chars(scenario, ferox).abilities == ()

    past_cleanup(scenario)
    assert chars(scenario, ferox).has_ability("Hexproof")


def test_tezzeret_makes_a_target_artifact_a_4_4_creature_unless_it_is_a_vehicle():
    """Durationless, so it lasts (CR 611.2a). A Vehicle keeps the power and
    toughness it printed (the second sentence's "if it isn't a Vehicle")."""
    scenario = one_shot_board(["Tezzeret, Betrayer of Flesh", "Bonesplitter", "Smuggler's Copter"])
    tezzeret = on_battlefield(scenario, "Tezzeret, Betrayer of Flesh")[0]
    sword = on_battlefield(scenario, "Bonesplitter")[0]
    copter = on_battlefield(scenario, "Smuggler's Copter")[0]
    scenario.activate(tezzeret, index=1, targets=[sword])
    scenario.pass_until_resolved()
    animated = chars(scenario, sword)
    assert Type.ARTIFACT in animated.types and Type.CREATURE in animated.types
    assert "Equipment" in animated.subtypes
    assert animated.power_toughness == (4, 4)

    other = one_shot_board(["Tezzeret, Betrayer of Flesh", "Smuggler's Copter"])
    their_copter = on_battlefield(other, "Smuggler's Copter")[0]
    other.activate(
        on_battlefield(other, "Tezzeret, Betrayer of Flesh")[0], index=1, targets=[their_copter]
    )
    other.pass_until_resolved()
    vehicle = chars(other, their_copter)
    assert Type.CREATURE in vehicle.types
    assert vehicle.power_toughness == (3, 3), "a Vehicle keeps its printed 3/3"
    assert Type.CREATURE not in chars(scenario, copter).types, "only the target"


def test_birgi_adds_red_that_survives_steps_and_phases_until_end_of_turn():
    """CR 500.5: mana empties as each step and phase ends, except mana an
    effect says you do not lose (Birgi, God of Storytelling), which empties in
    the cleanup step instead (CR 500.5b, CR 514.2)."""
    scenario = one_shot_board(
        ["Birgi, God of Storytelling", "Mountain"], hand=["Shock"], library=["Mountain"] * 3
    )
    mountain = on_battlefield(scenario, "Mountain")[0]
    scenario.cast_and_resolve("Shock", mountain, targets=["bob"])
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert scenario.player().mana_pool.floating == {Color.RED: 1}

    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert scenario.player().mana_pool.floating == {Color.RED: 1}, "survives the phase ending"

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup
    assert scenario.player().mana_pool.floating == {}, "gone at cleanup"


def test_birgi_does_not_trigger_on_a_land_ability():
    """Only casting a spell triggers it: tapping a land for mana does not."""
    scenario = one_shot_board(["Birgi, God of Storytelling", "Mountain"], library=["Mountain"] * 3)
    mountain = on_battlefield(scenario, "Mountain")[0]
    scenario.activate(mountain, color=Color.RED)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []
    assert scenario.player().mana_pool.floating == {Color.RED: 1}, "just the land's own mana"


def boast_board(*, birgi_for: str | None, extra: list[str] | None = None):
    """Axgard Braggart attacked (Boast - {1}{W}: untap, +1/+1 counter); Birgi
    sits on `birgi_for`'s side when given."""
    players = {"alice": ["Axgard Braggart", "Plains", "Plains", "Plains", "Plains", "Plains"]}
    players["bob"] = list(extra or [])
    if birgi_for:
        players[birgi_for].append("Birgi, God of Storytelling")
    scenario = (
        Scenario()
        .player("alice", library=["Plains"] * 3, battlefield=players["alice"])
        .player("bob", life=40, library=["Island"] * 3, battlefield=players["bob"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    braggart = scenario.creature("Axgard Braggart", "alice")
    scenario.attack_with(braggart)
    return scenario, braggart


def boast_once(scenario, braggart):
    scenario.activate(braggart, auto=True)
    scenario.resolve_top()


def test_birgi_lets_a_creature_boast_a_second_time_in_the_turn():
    """CR 702.142a says boast is once each turn; Birgi's static says creatures
    you control can boast twice during each of your turns rather than once."""
    scenario, braggart = boast_board(birgi_for="alice")
    boast_once(scenario, braggart)
    assert scenario.why_cannot_activate(braggart, 0) is None, "the second boast is allowed"
    boast_once(scenario, braggart)
    assert braggart.counter_count(Counter.PLUS_ONE) == 2


def test_birgi_allows_only_two_boasts_not_three():
    scenario, braggart = boast_board(birgi_for="alice")
    boast_once(scenario, braggart)
    boast_once(scenario, braggart)
    reason = scenario.why_cannot_activate(braggart, 0)
    assert reason is not None and "already been activated" in reason


def test_without_birgi_the_second_boast_is_still_refused():
    scenario, braggart = boast_board(birgi_for=None)
    boast_once(scenario, braggart)
    reason = scenario.why_cannot_activate(braggart, 0)
    assert reason is not None and "already been activated" in reason


def test_an_opponents_birgi_does_not_let_my_creature_boast_twice():
    """ "Creatures you control": Birgi under bob's control grants nothing to alice."""
    scenario, braggart = boast_board(birgi_for="bob")
    boast_once(scenario, braggart)
    reason = scenario.why_cannot_activate(braggart, 0)
    assert reason is not None and "already been activated" in reason


def test_birgi_still_needs_the_creature_to_have_attacked():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Axgard Braggart", "Birgi, God of Storytelling", "Plains", "Plains"],
        )
        .player("bob", life=40)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    reason = scenario.why_cannot_activate(scenario.creature("Axgard Braggart", "alice"), 0)
    assert reason is not None and "702.142a" in reason


def jace_board():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Grizzly Bears", "Serra Angel", "Mountain"],
            battlefield=["Jace Reawakened"],
            library=["Island"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_jace_reawakened_plots_a_cheap_nonland_card_from_your_hand():
    """ "You may exile a nonland card with mana value 3 or less from your hand.
    If you do, it becomes plotted." (CR 702.170c)."""
    scenario = jace_board()
    jace = on_battlefield(scenario, "Jace Reawakened")[0]
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    scenario.will_choose_cards(bears, source="Jace Reawakened")
    scenario.activate(jace, index=1)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.EXILE
    assert bears.exile_annotation.marker.value == "plotted"
    assert bears.exile_annotation.owner == "alice"
    assert {c.name for c in scenario.player().hand} == {"Serra Angel", "Mountain"}


def test_jace_reawakened_may_plot_nothing():
    scenario = jace_board()
    jace = on_battlefield(scenario, "Jace Reawakened")[0]
    scenario.will_choose_cards(source="Jace Reawakened")
    scenario.activate(jace, index=1)
    scenario.pass_until_resolved()
    assert {c.name for c in scenario.player().hand} == {
        "Grizzly Bears",
        "Serra Angel",
        "Mountain",
    }


def test_a_card_plotted_by_jace_is_cast_free_on_a_later_turn_only():
    """CR 702.170d: the permission belongs to the plotted card, whether or not
    it prints plot."""
    scenario = jace_board()
    jace = on_battlefield(scenario, "Jace Reawakened")[0]
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    scenario.will_choose_cards(bears, source="Jace Reawakened")
    scenario.activate(jace, index=1)
    scenario.pass_until_resolved()

    same_turn = scenario.cast("Grizzly Bears", from_zone=Zone.EXILE)
    with pytest.raises(ValueError, match="later turn"):
        same_turn.use_keyword("Plot")

    for _ in range(60):
        scenario.advance()
        if scenario.turn.active_player == "alice" and scenario.step is Step.PRECOMBAT_MAIN:
            break
    casting = scenario.cast("Grizzly Bears", from_zone=Zone.EXILE)
    casting.use_keyword("Plot")
    assert casting.total_cost.mana == ManaCost()


def boldwyr_combat():
    """Alice attacks with a Bear made a Warrior; bob has a Bear made a Coward
    and a Rat left alone."""
    scenario = one_shot_board(
        ["Boldwyr Intimidator", "Grizzly Bears"] + ["Mountain"] * 4,
        ["Grizzly Bears", "Typhoid Rats"],
    )
    boldwyr = on_battlefield(scenario, "Boldwyr Intimidator")[0]
    attacker = on_battlefield(scenario, "Grizzly Bears")[0]
    coward = on_battlefield(scenario, "Grizzly Bears", "bob")[0]
    rats = on_battlefield(scenario, "Typhoid Rats", "bob")[0]
    mountains = scenario.untapped_sources(*["Mountain"] * 4, username="alice")
    scenario.activate(boldwyr, mountains[0], index=0, targets=[coward])
    scenario.pass_until_resolved()
    scenario.activate(boldwyr, *mountains[1:], index=1, targets=[attacker])
    scenario.pass_until_resolved()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacker, defending="bob")
    return scenario, attacker, coward, rats


def test_a_coward_cannot_block_a_warrior():
    """Boldwyr Intimidator's "Cowards can't block Warriors." (CR 509.1b): the
    restriction names a blocker group and an attacker group."""
    scenario, attacker, coward, rats = boldwyr_combat()
    with pytest.raises(ValueError, match="can't block"):
        scenario.block(attacker, coward)
    assert coward.id not in scenario.game.combat.blocker_ids


def test_a_creature_that_is_not_a_coward_can_block_a_warrior():
    scenario, attacker, coward, rats = boldwyr_combat()
    scenario.block(attacker, rats)
    assert rats.id in scenario.game.combat.blocker_ids


def test_a_coward_can_block_an_attacker_that_is_not_a_warrior():
    scenario = one_shot_board(
        ["Boldwyr Intimidator", "Grizzly Bears", "Mountain"], ["Grizzly Bears"]
    )
    boldwyr = on_battlefield(scenario, "Boldwyr Intimidator")[0]
    attacker = on_battlefield(scenario, "Grizzly Bears")[0]
    coward = on_battlefield(scenario, "Grizzly Bears", "bob")[0]
    scenario.activate(
        boldwyr,
        scenario.untapped_sources("Mountain", username="alice")[0],
        index=0,
        targets=[coward],
    )
    scenario.pass_until_resolved()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacker, defending="bob")
    scenario.block(attacker, coward)
    assert coward.id in scenario.game.combat.blocker_ids


# --------------------------------------------------------------------------
# Second printings of each rewrite reader, none of them a listed card
# --------------------------------------------------------------------------


def aura_on(aura: str, target_name: str, extra=(), *, target_owner: str = "alice"):
    zones = {"alice": [aura, *extra], "bob": []}
    zones[target_owner].append(target_name)
    scenario = (
        Scenario()
        .player("alice", battlefield=zones["alice"])
        .player("bob", battlefield=zones["bob"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    target = on_battlefield(scenario, target_name, target_owner)[0]
    attached = attach(scenario, aura, target)
    return scenario, target, attached


def test_lignify_makes_a_flier_a_vanilla_treefolk_and_gives_it_back_when_it_leaves():
    """ "Enchanted creature is a Treefolk with base power and toughness 0/4 and
    loses all abilities." (CR 613.1d, CR 613.1f, CR 613.4b)."""
    scenario, angel, aura = aura_on("Lignify", "Serra Angel")
    now = chars(scenario, angel)
    assert now.subtypes == ("Treefolk",)
    assert now.power_toughness == (0, 4)
    assert not now.has_ability("Flying")
    aura.unattach()
    back = chars(scenario, angel)
    assert back.power_toughness == (4, 4)
    assert back.has_ability("Flying")


def test_lignify_leaves_another_creature_alone():
    scenario, _, _ = aura_on("Lignify", "Serra Angel", ["Serra Angel"])
    other = on_battlefield(scenario, "Serra Angel")[1]
    assert chars(scenario, other).power_toughness == (4, 4)


def test_ensoul_artifact_animates_an_artifact_that_stays_an_artifact():
    """ "Enchanted artifact is a creature with base power and toughness 5/5 in
    addition to its other types." (CR 613.1d: the types are added, not set)."""
    scenario, ring, aura = aura_on("Ensoul Artifact", "Sol Ring")
    now = chars(scenario, ring)
    assert Type.ARTIFACT in now.types and Type.CREATURE in now.types
    assert now.power_toughness == (5, 5)
    aura.unattach()
    assert chars(scenario, ring).types == (Type.ARTIFACT,)


def test_puppet_crafting_makes_a_permanent_a_construct_creature():
    scenario, ring, aura = aura_on("Puppet Crafting", "Sol Ring")
    now = chars(scenario, ring)
    assert Type.CREATURE in now.types and "Construct" in now.subtypes
    assert now.power_toughness == (5, 5)
    assert aura.attached_to == ring.id


def test_argent_mutation_adds_artifact_until_end_of_turn_only():
    """ "Target permanent becomes an artifact in addition to its other types
    until end of turn." (CR 613.1d, CR 514.2)"""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Island", "Island", "Island", "Grizzly Bears"],
            hand=["Argent Mutation"],
            library=["Island"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = on_battlefield(scenario, "Grizzly Bears")[0]
    scenario.cast_and_resolve(
        "Argent Mutation", *scenario.untapped_sources("Island", "Island", "Island"), targets=[bears]
    )
    now = chars(scenario, bears)
    assert Type.ARTIFACT in now.types and Type.CREATURE in now.types
    past_cleanup(scenario)
    assert chars(scenario, bears).types == (Type.CREATURE,)


def test_turn_to_frog_makes_the_target_a_one_one_frog_without_abilities_until_end_of_turn():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Island", "Island"], hand=["Turn to Frog"])
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = on_battlefield(scenario, "Serra Angel", "bob")[0]
    scenario.cast_and_resolve(
        "Turn to Frog", *scenario.untapped_sources("Island", "Island"), targets=[angel]
    )
    now = chars(scenario, angel)
    assert now.power_toughness == (1, 1)
    assert now.subtypes == ("Frog",)
    assert Color.BLUE in now.colors
    assert not now.has_ability("Flying")
    past_cleanup(scenario)
    assert chars(scenario, angel).power_toughness == (4, 4)
