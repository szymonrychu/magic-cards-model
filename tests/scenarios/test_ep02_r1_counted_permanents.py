"""Scenario: an amount counted off the live board - "for each <permanents> you
control", "X, where X is the number of <permanents> you control", "equal to the
number of <permanents> you control" - read as the effect applies, for every
recipient and verb the listed cards print.

CR 608.2h: information an effect needs is taken once, when the effect applies
(a "for each" count or a "where X is" count is fixed as the spell or ability
resolves, then used unchanged for every recipient and every instruction).
CR 119.3 (life gained or lost adjusts the total), CR 701.9 (discard), CR 701.17
(mill), CR 121.1 (draw), CR 120.3 (damage), CR 106.4 (adding mana), CR 107.14
(energy), CR 700.8 (party), CR 700.5 (devotion), CR 107.3f (an X defined by the
text), CR 205.4 (supertypes: snow) - each looked up with `mise run rules:find`.

Every counted noun is exercised at a count of zero, one and several, with the
permanents the phrase must NOT count (the other player's, the wrong kind)
sitting on the board as well.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import create_predefined_tokens
from tests.scenarios.harness import Scenario

LIBRARY = ["Forest"] * 12


def _build(alice=(), bob=(), *, hand=(), alice_library=None, bob_library=None, graveyard=()):
    return (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=list(alice),
            library=list(LIBRARY if alice_library is None else alice_library),
            graveyard=list(graveyard),
        )
        .player(
            "bob",
            battlefield=list(bob),
            hand=["Forest"] * 5,
            library=list(LIBRARY if bob_library is None else bob_library),
        )
        .build()
    )


def _main(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario, name, *, targets=None):
    scenario.cast_and_resolve(name, auto=True, username="alice", targets=targets)


LANDS_B = ["Swamp"] * 6
ANY_COLOUR = ["Chromatic Lantern"] + ["Mountain"] * 6  # every land taps for any colour: no Swamps


# --------------------------------------------------------------------------
# Each opponent loses N life for each <creature you control> (Gruesome Fate)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("creatures", [0, 1, 4])
def test_gruesome_fate_drains_one_life_per_creature_you_control(creatures):
    """Only alice's creatures count; bob's own creature does not."""
    scenario = _main(
        _build(
            ["Swamp"] * 3 + ["Grizzly Bears"] * creatures,
            ["Grizzly Bears", "Grizzly Bears"],
            hand=["Gruesome Fate"],
        )
    )
    _cast(scenario, "Gruesome Fate")
    assert scenario.player("bob").life == 20 - creatures
    assert scenario.player("alice").life == 20


def test_gruesome_fate_hits_every_opponent_by_the_same_count():
    scenario = _main(
        Scenario()
        .player("alice", hand=["Gruesome Fate"], battlefield=["Swamp"] * 3 + ["Grizzly Bears"] * 2)
        .player("bob")
        .player("carol")
        .build()
    )
    _cast(scenario, "Gruesome Fate")
    assert scenario.player("bob").life == 18
    assert scenario.player("carol").life == 18


# --------------------------------------------------------------------------
# Target opponent loses life equal to the number of <X> you control
# (Shaman of the Pack: Elves; Tezzeret, Master of Metal: artifacts)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("extra_elves", [0, 1, 3])
def test_shaman_of_the_pack_counts_elves_including_itself(extra_elves):
    """The Shaman is an Elf Shaman, so it counts itself; a Bear does not count."""
    scenario = _main(
        _build(
            ["Swamp", "Forest", "Swamp"] + ["Llanowar Elves"] * extra_elves + ["Grizzly Bears"],
            ["Llanowar Elves"] * 2,
            hand=["Shaman of the Pack"],
        )
    )
    scenario.choose_trigger_targets("Shaman of the Pack", ["bob"])
    scenario.cast_onto_stack("Shaman of the Pack", auto=True, username="alice")
    scenario.pass_until_resolved()  # the creature spell
    scenario.pass_until_resolved()  # its enters trigger
    assert scenario.player("bob").life == 20 - (extra_elves + 1)
    assert scenario.player("alice").life == 20


@pytest.mark.parametrize("artifacts", [0, 1, 3])
def test_tezzeret_minus_three_counts_artifacts_you_control(artifacts):
    scenario = _main(
        _build(
            ["Tezzeret, Master of Metal"] + ["Sol Ring"] * artifacts + ["Grizzly Bears"],
            ["Sol Ring"],
        )
    )
    tezzeret = scenario.find("Tezzeret, Master of Metal", Zone.BATTLEFIELD, "alice")
    tezzeret.add_counters("loyalty", 5)
    scenario.activate(tezzeret, index=1, targets=["bob"])
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 20 - artifacts


# --------------------------------------------------------------------------
# You gain N life for each <tapped artifact, creature, and land you control>
# (Toil to Renown) - an and/or list of types, restricted to tapped ones
# --------------------------------------------------------------------------


def test_toil_to_renown_counts_tapped_artifacts_creatures_and_lands():
    scenario = _main(
        _build(
            ["Forest", "Forest", "Forest", "Sol Ring", "Grizzly Bears", "Llanowar Elves"],
            ["Forest", "Grizzly Bears"],
            hand=["Toil to Renown"],
        )
    )
    # Tap the Bears and the Sol Ring by hand; paying for Toil taps two Forests.
    scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice").tap()
    scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice").tap()
    forests = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.cast_and_resolve("Toil to Renown", *forests, username="alice")
    # tapped now: Bears, Sol Ring, two Forests = 4 (Elves untapped, third Forest
    # untapped, bob's tapped/untapped permanents are not alice's)
    assert scenario.player("alice").life == 24


def test_toil_to_renown_with_nothing_tapped_gains_nothing_beyond_its_cost_lands():
    scenario = _main(_build(["Forest", "Forest"], [], hand=["Toil to Renown"]))
    forests = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.cast_and_resolve("Toil to Renown", *forests, username="alice")
    assert scenario.player("alice").life == 22  # the two Forests that paid are tapped


# --------------------------------------------------------------------------
# Each opponent loses X life, where X is the number of creatures with defender
# you control (Blight Pile) and damage equal to the same count (Vent Sentinel)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("walls", [0, 1, 3])
def test_blight_pile_counts_only_creatures_with_defender(walls):
    scenario = _main(
        _build(
            ["Blight Pile", "Swamp", "Swamp", "Swamp"]
            + ["Wall of Omens"] * walls
            + ["Grizzly Bears", "Grizzly Bears"],
            ["Wall of Omens"],
        )
    )
    pile = scenario.find("Blight Pile", Zone.BATTLEFIELD, "alice")
    pile_defenders = walls + 1  # Blight Pile itself has defender
    scenario.activate(pile, auto=True)
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 20 - pile_defenders


@pytest.mark.parametrize("walls", [0, 2])
def test_vent_sentinel_damages_target_player_by_defenders_you_control(walls):
    scenario = _main(
        _build(
            ["Vent Sentinel", "Mountain", "Mountain"] + ["Axebane Guardian"] * walls,
            ["Wall of Omens"],
        )
    )
    sentinel = scenario.find("Vent Sentinel", Zone.BATTLEFIELD, "alice")
    scenario.activate(sentinel, auto=True, targets=["bob"])
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 20 - (walls + 1)  # Vent Sentinel has defender


def test_vent_sentinel_can_hit_a_planeswalker():
    scenario = _main(
        _build(["Vent Sentinel", "Mountain", "Mountain"], ["Tezzeret, Master of Metal"])
    )
    tezzeret = scenario.find("Tezzeret, Master of Metal", Zone.BATTLEFIELD, "bob")
    before = tezzeret.counters["loyalty"]
    sentinel = scenario.find("Vent Sentinel", Zone.BATTLEFIELD, "alice")
    scenario.activate(sentinel, auto=True, targets=[tezzeret])
    scenario.pass_until_resolved()
    assert tezzeret.counters["loyalty"] == before - 1


# --------------------------------------------------------------------------
# Target player mills X cards, where X is ... (Coral Colony, Doorkeeper: defenders
# you control; Dreadwaters: lands you control)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("card", ["Coral Colony", "Doorkeeper"])
@pytest.mark.parametrize("extra_defenders", [0, 1, 3])
def test_defender_mill_counts_defenders_you_control_not_the_targets(card, extra_defenders):
    scenario = _main(
        _build(
            [card, "Island", "Island", "Island"] + ["Wall of Omens"] * extra_defenders,
            ["Wall of Omens"] * 4,
        )
    )
    source = scenario.find(card, Zone.BATTLEFIELD, "alice")
    library_before = len(scenario.player("bob").library)
    scenario.activate(source, auto=True, targets=["bob"])
    scenario.pass_until_resolved()
    assert len(scenario.player("bob").library) == library_before - (extra_defenders + 1)
    assert len(scenario.player("bob").graveyard) == extra_defenders + 1


def _hand(scenario, username="alice"):
    return len(scenario.player(username).hand)


def _chars(scenario, name, username):
    return scenario.game.characteristics_of(scenario.find(name, Zone.BATTLEFIELD, username))


def _cast_with_adventure(scenario, name, *, targets=None):
    casting = scenario.cast(name, "alice", targets=targets)
    casting.cast_as_adventure()
    scenario.auto_pay(casting.begin_paying(), username="alice")
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def _upkeep(scenario):
    """Move alice's turn to her upkeep and resolve what her upkeep triggers put on the stack."""
    scenario.start_at(Step.UNTAP)
    scenario.advance()
    assert scenario.step is Step.UPKEEP
    while scenario.game.stack:
        scenario.pass_until_resolved()


# --------------------------------------------------------------------------
# Target player mills X cards, where X is the number of lands you control
# (Dreadwaters) - the casting player's lands, not the target's
# --------------------------------------------------------------------------


@pytest.mark.parametrize("extra_lands", [0, 1, 3])
def test_dreadwaters_mills_by_the_lands_you_control(extra_lands):
    scenario = _main(
        _build(
            ["Island"] * 4 + ["Mountain"] * extra_lands + ["Grizzly Bears", "Sol Ring"],
            ["Forest"] * 7,
            hand=["Dreadwaters"],
        )
    )
    _cast(scenario, "Dreadwaters", targets=["bob"])
    assert len(scenario.player("bob").library) == 12 - (4 + extra_lands)
    assert len(scenario.player("alice").library) == 12


# --------------------------------------------------------------------------
# At the beginning of your upkeep, you draw X cards and lose X life, where X is
# the number of Zombies you control (Graveborn Muse; it is a Zombie itself)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("extra_zombies", [0, 1, 3])
def test_graveborn_muse_draws_and_loses_by_zombies(extra_zombies):
    scenario = _build(
        ["Graveborn Muse"] + ["Walking Corpse"] * extra_zombies + ["Grizzly Bears"],
        ["Walking Corpse"] * 2,
    )
    _upkeep(scenario)
    assert _hand(scenario) == extra_zombies + 1
    assert scenario.player("alice").life == 20 - (extra_zombies + 1)
    assert scenario.player("bob").life == 20


# --------------------------------------------------------------------------
# Target player loses X life and mills X cards, where X is the number of
# Zombies you control (Lich Lord of Unx)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("extra_zombies", [0, 1, 3])
def test_lich_lord_of_unx_drains_and_mills_by_zombies(extra_zombies):
    scenario = _main(
        _build(
            ["Lich Lord of Unx", "Island", "Island", "Swamp", "Swamp", "Grizzly Bears"]
            + ["Walking Corpse"] * extra_zombies,
            ["Walking Corpse"] * 2,
        )
    )
    lich = scenario.find("Lich Lord of Unx", Zone.BATTLEFIELD, "alice")
    scenario.activate(lich, index=1, auto=True, targets=["bob"])
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 20 - (extra_zombies + 1)
    assert len(scenario.player("bob").library) == 12 - (extra_zombies + 1)
    assert scenario.player("alice").life == 20


# --------------------------------------------------------------------------
# You draw X cards and you lose X life, where X is the number of creatures you
# control (Minions' Murmurs)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("creatures", [0, 1, 3])
def test_minions_murmurs_draws_and_loses_by_creatures(creatures):
    scenario = _main(
        _build(
            ["Swamp"] * 4 + ["Grizzly Bears"] * creatures + ["Sol Ring"],
            ["Grizzly Bears"] * 2,
            hand=["Minions' Murmurs"],
        )
    )
    _cast(scenario, "Minions' Murmurs")
    assert _hand(scenario) == creatures
    assert scenario.player("alice").life == 20 - creatures


# --------------------------------------------------------------------------
# Target player discards a card for each Swamp you control (Mind Sludge)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("swamps", [1, 3, 5])
def test_mind_sludge_discards_per_swamp_you_control(swamps):
    scenario = _main(
        _build(
            ["Swamp"] * swamps + ["Mountain"] * (5 - swamps),
            ["Swamp"] * 3,
            hand=["Mind Sludge"],
        )
    )
    bob = scenario.player("bob")
    scenario.will_discard(*bob.hand[:swamps], username="bob")
    _cast(scenario, "Mind Sludge", targets=["bob"])
    assert len(bob.graveyard) == swamps
    assert len(bob.hand) == 5 - swamps


# --------------------------------------------------------------------------
# All creatures get -1/-1 until end of turn for each Swamp you control
# (Mutilate) - every creature, whoever controls it
# --------------------------------------------------------------------------


@pytest.mark.parametrize("swamps", [2, 3, 4])
def test_mutilate_shrinks_all_creatures_per_swamp_you_control(swamps):
    scenario = _main(
        _build(
            ["Swamp"] * swamps + ["Mountain"] * (4 - swamps) + ["Wall of Omens"],
            ["Swamp"] * 3 + ["Grizzly Bears"],
            hand=["Mutilate"],
        )
    )
    _cast(scenario, "Mutilate")
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob") is not None
    if swamps < 4:
        assert _chars(scenario, "Wall of Omens", "alice").toughness == 4 - swamps
    else:
        assert scenario.find("Wall of Omens", Zone.GRAVEYARD, "alice") is not None


# --------------------------------------------------------------------------
# Nissa, Voice of Zendikar -7: You gain X life and draw X cards, where X is the
# number of lands you control
# --------------------------------------------------------------------------


@pytest.mark.parametrize("lands", [0, 1, 4])
def test_nissa_minus_seven_gains_and_draws_by_lands(lands):
    scenario = _main(
        _build(
            ["Nissa, Voice of Zendikar", "Grizzly Bears", "Sol Ring"] + ["Forest"] * lands,
            ["Forest"] * 3,
        )
    )
    nissa = scenario.find("Nissa, Voice of Zendikar", Zone.BATTLEFIELD, "alice")
    nissa.add_counters("loyalty", 5)
    scenario.activate(nissa, index=2)
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 20 + lands
    assert _hand(scenario) == lands


# --------------------------------------------------------------------------
# You gain X life and each opponent loses X life, where X is the number of
# Knights you control (Curry Favor, the Adventure half of Smitten Swordmaster)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("knights", [0, 1, 3])
def test_curry_favor_drains_by_knights(knights):
    scenario = _main(
        _build(
            ["Swamp"] + ["Black Knight"] * knights + ["Grizzly Bears"],
            ["Black Knight", "Black Knight"],
            hand=["Smitten Swordmaster // Curry Favor"],
        )
    )
    _cast_with_adventure(scenario, "Smitten Swordmaster // Curry Favor")
    assert scenario.player("alice").life == 20 + knights
    assert scenario.player("bob").life == 20 - knights


# --------------------------------------------------------------------------
# Whenever this creature attacks, each opponent loses X life and you gain X
# life, where X is the number of other Squirrels, Bats, Lizards, and Rats you
# control (Valley Rotcaller)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "others",
    [
        [],
        ["Graf Rats"],
        ["Graf Rats", "Deep-Cavern Bat", "Basking Rootwalla", "Prairie Dog", "Valley Rotcaller"],
    ],
)
def test_valley_rotcaller_counts_other_squirrels_bats_lizards_and_rats(others):
    scenario = _build(
        ["Valley Rotcaller", "Grizzly Bears", "Sol Ring"] + others,
        ["Graf Rats", "Deep-Cavern Bat"],
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    rotcaller = scenario.creatures("Valley Rotcaller", username="alice")[0]
    scenario.attack_with(rotcaller)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 20 - len(others)
    assert scenario.player("alice").life == 20 + len(others)


# --------------------------------------------------------------------------
# Domain - Target player discards a card for each basic land type among lands
# you control (Voices from the Void)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "lands,types",
    [
        (["Swamp"] * 5, 1),
        (["Swamp", "Swamp", "Swamp", "Forest", "Mountain"], 3),
        (["Swamp", "Forest", "Mountain", "Island", "Plains"], 5),
    ],
)
def test_voices_from_the_void_discards_per_basic_land_type(lands, types):
    scenario = _main(_build(lands, ["Plains", "Island", "Forest"], hand=["Voices from the Void"]))
    bob = scenario.player("bob")
    scenario.will_discard(*bob.hand[:types], username="bob")
    _cast(scenario, "Voices from the Void", targets=["bob"])
    assert len(bob.graveyard) == types


# --------------------------------------------------------------------------
# At the beginning of your upkeep, target opponent discards a card for each
# Shrine you control (Honden of Night's Reach); Honden of Cleansing Fire is a
# second Shrine whose own upkeep gains 2 life for each Shrine
# --------------------------------------------------------------------------


def test_honden_of_nights_reach_counts_only_your_shrines():
    scenario = _build(
        ["Honden of Night's Reach", "Treasure Map", "Grizzly Bears"],
        ["Honden of Seeing Winds"],
    )
    bob = scenario.player("bob")
    scenario.will_discard(*bob.hand[:1], username="bob")
    _upkeep(scenario)
    assert len(bob.graveyard) == 1


def test_honden_of_nights_reach_and_cleansing_fire_count_each_shrine_you_control():
    scenario = _build(["Honden of Night's Reach", "Honden of Cleansing Fire"], [])
    bob = scenario.player("bob")
    scenario.will_discard(*bob.hand[:2], username="bob")
    _upkeep(scenario)
    assert len(bob.graveyard) == 2
    assert scenario.player("alice").life == 20 + 2 * 2


# --------------------------------------------------------------------------
# Add {R} for each creature you control (Battle Hymn) and for each tapped land
# your opponents control (Mana Geyser); Ardent Electromancer adds {R} for each
# creature in your party
# --------------------------------------------------------------------------


@pytest.mark.parametrize("creatures", [0, 1, 3])
def test_battle_hymn_adds_red_per_creature_you_control(creatures):
    scenario = _main(
        _build(
            ["Mountain", "Mountain"] + ["Grizzly Bears"] * creatures + ["Sol Ring"],
            ["Grizzly Bears"] * 2,
            hand=["Battle Hymn"],
        )
    )
    _cast(scenario, "Battle Hymn")
    assert scenario.player("alice").mana_pool.floating.get(Color.RED, 0) == creatures


@pytest.mark.parametrize("tapped", [0, 1, 3])
def test_mana_geyser_adds_red_per_tapped_land_your_opponents_control(tapped):
    scenario = _main(
        _build(
            ["Mountain"] * 5 + ["Grizzly Bears"],
            ["Forest"] * 4 + ["Grizzly Bears"],
            hand=["Mana Geyser"],
        )
    )
    for forest in scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", username="bob")[
        :tapped
    ]:
        forest.tap()
    scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob").tap()  # not a land
    _cast(scenario, "Mana Geyser")
    assert scenario.player("alice").mana_pool.floating.get(Color.RED, 0) == tapped


@pytest.mark.parametrize(
    "party,expected",
    [
        ([], 1),
        (["Black Market Tycoon"], 2),
        (["Black Market Tycoon", "Shepherd of Heroes"], 3),
        (["Black Market Tycoon", "Black Market Tycoon"], 2),  # two Rogues are one party member
    ],
)
def test_ardent_electromancer_adds_red_per_creature_in_your_party(party, expected):
    """The Electromancer is the party's Wizard; each further role adds one."""
    scenario = _main(
        _build(["Mountain"] * 4 + party + ["Grizzly Bears"], [], hand=["Ardent Electromancer"])
    )
    scenario.cast_onto_stack("Ardent Electromancer", auto=True, username="alice")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert scenario.player("alice").mana_pool.floating.get(Color.RED, 0) == expected


# --------------------------------------------------------------------------
# You get {E} for each creature you control (Aetherwind Basker, on entering and
# on attacking); an amount of {E} equal to the number of creatures you control
# (Scurry of Gremlins, after its two Gremlins exist); Peema Aether-Seer gets
# {E} equal to the greatest power among creatures you control
# --------------------------------------------------------------------------


def _energy(scenario, username="alice"):
    return scenario.player(username).counter_count(Counter.ENERGY)


@pytest.mark.parametrize("extra", [0, 1, 3])
def test_aetherwind_basker_enters_for_each_creature_you_control(extra):
    scenario = _main(
        _build(
            ["Forest"] * 7 + ["Grizzly Bears"] * extra + ["Sol Ring"],
            ["Grizzly Bears"] * 2,
            hand=["Aetherwind Basker"],
        )
    )
    scenario.cast_onto_stack("Aetherwind Basker", auto=True, username="alice")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert _energy(scenario) == extra + 1
    assert _energy(scenario, "bob") == 0


@pytest.mark.parametrize("extra", [0, 1, 3])
def test_aetherwind_basker_attacks_for_each_creature_you_control(extra):
    scenario = _build(
        ["Aetherwind Basker", "Sol Ring"] + ["Grizzly Bears"] * extra, ["Grizzly Bears"] * 2
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creatures("Aetherwind Basker", username="alice")[0])
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert _energy(scenario) == extra + 1


@pytest.mark.parametrize("extra", [0, 1, 3])
def test_scurry_of_gremlins_counts_the_gremlins_it_just_made(extra):
    scenario = _main(
        _build(
            ["Mountain", "Mountain", "Plains", "Plains"] + ["Grizzly Bears"] * extra + ["Sol Ring"],
            ["Grizzly Bears"] * 3,
            hand=["Scurry of Gremlins"],
        )
    )
    scenario.cast_onto_stack("Scurry of Gremlins", auto=True, username="alice")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert _energy(scenario) == 2 + extra


@pytest.mark.parametrize("creatures,greatest", [([], 3), (["Craw Wurm"], 6)])
def test_peema_aether_seer_energy_equals_the_greatest_power_you_control(creatures, greatest):
    """A second legal printing for the energy-equal-to reader; Peema is a 3/3,
    the opponent's bigger creature does not count."""
    scenario = _main(
        _build(["Forest"] * 4 + creatures, ["Craw Wurm", "Craw Wurm"], hand=["Peema Aether-Seer"])
    )
    scenario.cast_onto_stack("Peema Aether-Seer", auto=True, username="alice")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert _energy(scenario) == greatest


# --------------------------------------------------------------------------
# At the beginning of your upkeep, this creature deals 2 damage to you for each
# Treasure you control (Black Market Tycoon)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("treasures", [0, 1, 3])
def test_black_market_tycoon_hurts_you_per_treasure_you_control(treasures):
    scenario = _build(["Black Market Tycoon", "Sol Ring"], ["Grizzly Bears"])
    for _ in range(treasures):
        create_predefined_tokens(scenario.game, "Treasure", "alice")
    create_predefined_tokens(scenario.game, "Treasure", "bob")  # the opponent's do not count
    _upkeep(scenario)
    assert scenario.player("alice").life == 20 - 2 * treasures
    assert scenario.player("bob").life == 20


# --------------------------------------------------------------------------
# Create a Treasure token. Until end of turn, up to one target creature gets +2/+2
# for each Treasure you control (Gold Rush) - the token it just made counts
# --------------------------------------------------------------------------


@pytest.mark.parametrize("treasures", [0, 1, 3])
def test_gold_rush_pumps_by_the_treasures_including_the_new_one(treasures):
    scenario = _main(
        _build(
            ["Forest", "Forest", "Grizzly Bears", "Sol Ring"], ["Grizzly Bears"], hand=["Gold Rush"]
        )
    )
    for _ in range(treasures):
        create_predefined_tokens(scenario.game, "Treasure", "alice")
    create_predefined_tokens(scenario.game, "Treasure", "bob")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    base = scenario.game.characteristics_of(bears).numeric_power
    _cast(scenario, "Gold Rush", targets=[bears])
    assert scenario.game.characteristics_of(bears).numeric_power == base + 2 * (treasures + 1)
    other = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    assert scenario.game.characteristics_of(other).numeric_power == base


def test_gold_rush_with_no_target_still_makes_the_treasure():
    scenario = _main(_build(["Forest", "Forest"], [], hand=["Gold Rush"]))
    _cast(scenario, "Gold Rush")
    assert len([c for c in scenario.game.battlefield if c.name == "Treasure Token"]) == 1


# --------------------------------------------------------------------------
# All nonsnow creatures get -X/-X until end of turn, where X is the number of
# snow permanents you control (Dead of Winter)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("snow_lands", [0, 1, 2])
def test_dead_of_winter_counts_snow_permanents_and_spares_snow_creatures(snow_lands):
    scenario = _main(
        _build(
            ["Swamp", "Swamp", "Swamp"]
            + ["Snow-Covered Forest"] * snow_lands
            + ["Wall of Omens", "Priest of the Haunted Edge", "Sol Ring"],
            ["Snow-Covered Island"] * 3 + ["Grizzly Bears"],
            hand=["Dead of Winter"],
        )
    )
    # Priest of the Haunted Edge is itself a snow permanent: it counts, and is spared.
    expected = snow_lands + 1
    _cast(scenario, "Dead of Winter")
    assert _chars(scenario, "Priest of the Haunted Edge", "alice").toughness == 4
    assert _chars(scenario, "Wall of Omens", "alice").toughness == max(4 - expected, 0) or (
        scenario.find("Wall of Omens", Zone.GRAVEYARD, "alice") is not None
    )
    if expected >= 2:
        assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob") is not None
    else:
        assert _chars(scenario, "Grizzly Bears", "bob").toughness == 2 - expected


# --------------------------------------------------------------------------
# Snow creatures you control get +1/+1 until end of turn (Diamond Faerie): the
# second printing of the snow-supertype mass subject, CR 205.4
# --------------------------------------------------------------------------


def test_diamond_faerie_pumps_only_snow_creatures_you_control():
    scenario = _main(
        _build(
            ["Snow-Covered Forest", "Snow-Covered Island", "Diamond Faerie"]
            + ["Priest of the Haunted Edge", "Grizzly Bears"],
            ["Priest of the Haunted Edge"],
        )
    )
    faerie = scenario.find("Diamond Faerie", Zone.BATTLEFIELD, "alice")
    scenario.activate(faerie, auto=True)
    scenario.resolve_top()
    # Priest of the Haunted Edge is a snow creature: pumped. Bears and the
    # opponent's snow creature are not.
    assert _chars(scenario, "Priest of the Haunted Edge", "alice").toughness == 5
    assert _chars(scenario, "Grizzly Bears", "alice").toughness == 2
    assert _chars(scenario, "Priest of the Haunted Edge", "bob").toughness == 4
    # Diamond Faerie is itself a Snow Creature, so it is pumped too (3/3 -> 4/4).
    assert _chars(scenario, "Diamond Faerie", "alice").toughness == 4


# --------------------------------------------------------------------------
# Domain - this creature gets +1/+0 until end of turn for each basic land type
# among lands you control (Wandering Goblins); +1/+1 for each enchantment you
# control (Slumbering Keepguard)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "lands,types",
    [
        (["Mountain", "Mountain", "Mountain"], 1),
        (["Mountain", "Forest", "Island"], 3),
        (["Mountain", "Forest", "Island", "Swamp", "Plains"], 5),
    ],
)
def test_wandering_goblins_pumps_per_basic_land_type(lands, types):
    scenario = _main(_build(["Wandering Goblins", "Sol Ring"] + lands, ["Plains", "Swamp"]))
    goblins = scenario.find("Wandering Goblins", Zone.BATTLEFIELD, "alice")
    base = scenario.game.characteristics_of(goblins).numeric_power
    scenario.activate(goblins, auto=True)
    scenario.pass_until_resolved()
    assert scenario.game.characteristics_of(goblins).numeric_power == base + types


@pytest.mark.parametrize(
    "enchantments",
    [[], ["Honden of Cleansing Fire"], ["Honden of Cleansing Fire", "Honden of Seeing Winds"]],
)
def test_slumbering_keepguard_pumps_per_enchantment_you_control(enchantments):
    scenario = _main(
        _build(
            ["Slumbering Keepguard", "Plains", "Plains", "Plains", "Sol Ring", "Grizzly Bears"]
            + enchantments,
            ["Honden of Night's Reach"],
        )
    )
    keepguard = scenario.find("Slumbering Keepguard", Zone.BATTLEFIELD, "alice")
    base = scenario.game.characteristics_of(keepguard)
    scenario.activate(keepguard, auto=True)
    scenario.pass_until_resolved()
    after = scenario.game.characteristics_of(keepguard)
    assert after.numeric_power == base.numeric_power + len(enchantments)
    assert after.numeric_toughness == base.numeric_toughness + len(enchantments)


# --------------------------------------------------------------------------
# Party: gets +1/+1 for each creature in your party (Kabira Outrider); you gain
# 2 life for each creature in your party (Shepherd of Heroes). Outrider is a
# Warrior, Shepherd a Cleric; a second creature of a role adds nothing.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "others,party",
    [
        ([], 1),
        (["Black Market Tycoon"], 2),
        (["Black Market Tycoon", "Shepherd of Heroes", "Lich Lord of Unx"], 4),
        (["Black Market Tycoon", "Black Market Tycoon"], 2),
    ],
)
def test_kabira_outrider_pumps_by_party_size(others, party):
    scenario = _main(
        _build(
            ["Plains"] * 4 + others + ["Grizzly Bears"],
            ["Black Market Tycoon", "Shepherd of Heroes", "Lich Lord of Unx"],
            hand=["Kabira Outrider"],
        )
    )
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    scenario.choose_trigger_targets("Kabira Outrider", [bears])
    scenario.cast_onto_stack("Kabira Outrider", auto=True, username="alice")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert scenario.game.characteristics_of(bears).numeric_power == 2 + party


@pytest.mark.parametrize(
    "others,party",
    [
        ([], 1),
        (["Black Market Tycoon", "Kabira Outrider"], 3),
        (["Black Market Tycoon", "Kabira Outrider", "Lich Lord of Unx"], 4),
        (["Shepherd of Heroes"], 1),  # another Cleric
    ],
)
def test_shepherd_of_heroes_gains_two_life_per_party_member(others, party):
    scenario = _main(
        _build(
            ["Plains"] * 5 + others,
            ["Black Market Tycoon", "Kabira Outrider"],
            hand=["Shepherd of Heroes"],
        )
    )
    scenario.cast_onto_stack("Shepherd of Heroes", auto=True, username="alice")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 20 + 2 * party


# --------------------------------------------------------------------------
# The same readers on second legal printings that are not in the 30-card list
# and not in the api decks (added with scripts/add_card.py)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("creatures", [0, 1, 3])
def test_camaraderie_gain_and_draw_by_creatures_then_pumps_the_team(creatures):
    """ "You gain X life and draw X cards, where X is ..." followed by a second
    sentence that is read by the ordinary clause readers."""
    scenario = _main(
        _build(
            ["Forest", "Forest", "Forest", "Plains"] + ["Grizzly Bears"] * creatures + ["Sol Ring"],
            ["Grizzly Bears"] * 2,
            hand=["Camaraderie"],
        )
    )
    _cast(scenario, "Camaraderie")
    assert scenario.player("alice").life == 20 + creatures
    assert _hand(scenario) == creatures
    for bears in scenario.creatures(*(["Grizzly Bears"] * creatures), username="alice"):
        assert scenario.game.characteristics_of(bears).numeric_power == 3
    for bears in scenario.creatures("Grizzly Bears", "Grizzly Bears", username="bob"):
        assert scenario.game.characteristics_of(bears).numeric_power == 2


@pytest.mark.parametrize("others", [0, 1, 3])
def test_bishop_of_the_bloodstained_counts_vampires_you_control(others):
    scenario = _main(
        _build(
            ["Swamp"] * 5 + ["Bloodghast"] * others + ["Grizzly Bears"],
            ["Bloodghast"] * 2,
            hand=["Bishop of the Bloodstained"],
        )
    )
    scenario.choose_trigger_targets("Bishop of the Bloodstained", ["bob"])
    scenario.cast_onto_stack("Bishop of the Bloodstained", auto=True, username="alice")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 20 - (others + 1)  # the Bishop is a Vampire


@pytest.mark.parametrize(
    "party,size",
    [
        ([], 1),
        (["Black Market Tycoon"], 2),
        (["Black Market Tycoon", "Kabira Outrider", "Lich Lord of Unx"], 4),
        (["Black Market Tycoon", "Black Market Tycoon"], 2),  # one party slot per role
    ],
)
def test_malakir_blood_priest_drains_by_party_size(party, size):
    """ "each opponent loses X life and you gain X life, where X is the number of
    creatures in your party" - the Blood-Priest is the Cleric."""
    scenario = _main(
        _build(
            ["Swamp"] * 4 + party,
            ["Black Market Tycoon", "Kabira Outrider", "Lich Lord of Unx"],
            hand=["Malakir Blood-Priest"],
        )
    )
    scenario.cast_onto_stack("Malakir Blood-Priest", auto=True, username="alice")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 20 - size
    assert scenario.player("alice").life == 20 + size


@pytest.mark.parametrize("walls", [0, 1, 3])
def test_wingmantle_chaplain_counts_creatures_with_defender_you_control(walls):
    """ "for each creature with defender you control" - the Chaplain has defender
    itself; a Bear and the opponent's Wall do not count."""
    scenario = _main(
        _build(
            ["Plains"] * 4 + ["Wall of Omens"] * walls + ["Grizzly Bears"],
            ["Wall of Omens", "Wall of Omens"],
            hand=["Wingmantle Chaplain"],
        )
    )
    scenario.cast_onto_stack("Wingmantle Chaplain", auto=True, username="alice")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    birds = [c for c in scenario.game.battlefield if c.name == "Bird Token"]
    assert len(birds) == walls + 1


@pytest.mark.parametrize(
    "lands,types",
    [(["Mountain", "Mountain", "Mountain"], 2), (["Mountain", "Swamp", "Island"], 4)],
)
def test_might_of_alara_pumps_per_basic_land_type(lands, types):
    scenario = _main(
        _build(
            lands + ["Forest", "Grizzly Bears", "Sol Ring"],
            ["Plains", "Swamp"],
            hand=["Might of Alara"],
        )
    )
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    _cast(scenario, "Might of Alara", targets=[bears])
    assert scenario.game.characteristics_of(bears).numeric_power == 2 + types


def test_honden_of_seeing_winds_draws_for_each_shrine_you_control():
    scenario = _build(
        ["Honden of Seeing Winds", "Honden of Cleansing Fire"], ["Honden of Night's Reach"]
    )
    _upkeep(scenario)
    assert _hand(scenario) == 2  # two Shrines of yours, the opponent's does not count
    assert scenario.player("alice").life == 20 + 2 * 2
