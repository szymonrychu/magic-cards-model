"""Scenario: counted permanents as an amount, round 2 - "the number of Allies /
legendary creatures / Islands / Shrines / Wizards you control", "for each land you
control, create a Treasure", "for each Shrine you control, create a token", a
static "+1/+0 for each legendary creature you control", "where X is the number of
<subtype> you control as this ability resolves".

CR 608.2h: information an effect needs is taken once, when the effect applies (a
"number of" count is fixed as the spell or ability resolves, then used unchanged
for every recipient and instruction). CR 613.4c: a static "+N/+N for each ..." is
re-evaluated continuously. CR 205.3m / 205.4a / 205.4g: subtypes and supertypes.
CR 111.1 / 111.4 (tokens); CR 700.4 is not used here. Every rule number was looked
up with `mise run rules:find`.

Each counted noun is exercised at a count of zero, one and several, with the
permanents the phrase must NOT count (the other player's, the wrong kind) on the
board as well.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.token import create_predefined_tokens
from tests.scenarios.harness import Scenario

LIBRARY = ["Forest"] * 12


def _build(alice=(), bob=(), *, hand=(), bob_hand=(), alice_library=None, bob_library=None):
    return (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=list(alice),
            library=list(LIBRARY if alice_library is None else alice_library),
        )
        .player(
            "bob",
            battlefield=list(bob),
            hand=list(bob_hand),
            library=list(LIBRARY if bob_library is None else bob_library),
        )
        .build()
    )


def _main(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario, name, *, targets=None):
    scenario.cast_and_resolve(name, auto=True, username="alice", targets=targets)


def _enter(scenario, name, *, targets=None, may=None):
    """Cast a creature, let it resolve, then resolve what its enters trigger put on
    the stack."""
    if targets is not None:
        scenario.choose_trigger_targets(name, targets)
    if may is not None:
        scenario.will_take_the_may(may)
    scenario.cast_onto_stack(name, auto=True, username="alice")
    scenario.pass_until_resolved()  # the creature spell
    while scenario.game.stack:
        scenario.pass_until_resolved()  # its enters trigger(s)


def _chars(scenario, name, username):
    return scenario.game.characteristics_of(scenario.find(name, Zone.BATTLEFIELD, username))


# --------------------------------------------------------------------------
# "the number of Allies you control" (Ondu Cleric, Hagra Diabolist, Halimar
# Excavator, Murasa Pyromancer, Tajuru Archer) - Ally is a creature type, its
# plural is "Allies" (CR 205.3m)
# --------------------------------------------------------------------------

PLAINS = ["Plains"] * 3


@pytest.mark.parametrize("others", [0, 1, 3])
def test_ondu_cleric_gains_life_equal_to_allies_including_itself(others):
    scenario = _main(
        _build(
            PLAINS + ["Tajuru Archer"] * others + ["Grizzly Bears"],
            ["Tajuru Archer", "Tajuru Archer"],
            hand=["Ondu Cleric"],
        )
    )
    _enter(scenario, "Ondu Cleric", may=True)
    assert scenario.player("alice").life == 20 + others + 1
    assert scenario.player("bob").life == 20


def test_ondu_cleric_optional_life_gain_can_be_declined():
    scenario = _main(_build(PLAINS + ["Tajuru Archer"], [], hand=["Ondu Cleric"]))
    _enter(scenario, "Ondu Cleric", may=False)
    assert scenario.player("alice").life == 20


def test_another_ally_entering_triggers_the_ally_already_on_the_battlefield():
    """ "Whenever this creature or another Ally you control enters": both Clerics
    trigger when the second enters, each counting both Allies (two Allies = 2 life
    each); the non-Ally Bears entering afterwards triggers nothing."""
    scenario = _main(
        _build(
            ["Plains"] * 2 + ["Forest"] * 3 + ["Ondu Cleric"],
            [],
            hand=["Ondu Cleric", "Grizzly Bears"],
        )
    )
    scenario.will_take_the_may(True, times=None)
    scenario.cast_onto_stack("Ondu Cleric", auto=True, username="alice")
    while scenario.game.stack:
        scenario.pass_until_resolved()
    assert scenario.player("alice").life == 24
    scenario.cast_onto_stack("Grizzly Bears", auto=True, username="alice")
    while scenario.game.stack:
        scenario.pass_until_resolved()
    assert scenario.player("alice").life == 24


@pytest.mark.parametrize("others", [0, 2])
def test_hagra_diabolist_drains_target_player_by_allies(others):
    scenario = _main(
        _build(
            ["Swamp"] * 5 + ["Sea Gate Loremaster"] * others + ["Grizzly Bears"],
            ["Sea Gate Loremaster"],
            hand=["Hagra Diabolist"],
        )
    )
    _enter(scenario, "Hagra Diabolist", targets=["bob"], may=True)
    assert scenario.player("bob").life == 20 - (others + 1)
    assert scenario.player("alice").life == 20


@pytest.mark.parametrize("others", [0, 1, 3])
def test_halimar_excavator_mills_by_allies(others):
    scenario = _main(
        _build(
            ["Island"] * 2 + ["Ondu Cleric"] * others + ["Grizzly Bears"],
            ["Ondu Cleric"] * 2,
            hand=["Halimar Excavator"],
        )
    )
    _enter(scenario, "Halimar Excavator", targets=["bob"])
    assert len(scenario.player("bob").library) == 12 - (others + 1)
    assert len(scenario.player("alice").library) == 12


def test_halimar_excavator_can_mill_its_own_controller():
    scenario = _main(_build(["Island"] * 2, [], hand=["Halimar Excavator"]))
    _enter(scenario, "Halimar Excavator", targets=["alice"])
    assert len(scenario.player("alice").library) == 11


@pytest.mark.parametrize("others", [0, 1])
def test_murasa_pyromancer_deals_damage_equal_to_allies(others):
    scenario = _main(
        _build(
            ["Mountain"] * 6 + ["Ondu Cleric"] * others,
            ["Shivan Dragon"],
            hand=["Murasa Pyromancer"],
        )
    )
    dragon = scenario.find("Shivan Dragon", Zone.BATTLEFIELD, "bob")
    _enter(scenario, "Murasa Pyromancer", targets=[dragon], may=True)
    assert dragon.damage == others + 1


def test_tajuru_archer_hits_a_flyer_for_the_ally_count():
    scenario = _main(
        _build(
            ["Forest"] * 3 + ["Ondu Cleric"],
            ["Wind Drake"],
            hand=["Tajuru Archer"],
        )
    )
    drake = scenario.find("Wind Drake", Zone.BATTLEFIELD, "bob")
    _enter(scenario, "Tajuru Archer", targets=[drake], may=True)
    assert scenario.find("Wind Drake", Zone.GRAVEYARD, "bob")  # 2 Allies = 2 damage, toughness 2


# --------------------------------------------------------------------------
# Proof printings of the same count in other positions (Sea Gate Loremaster:
# "Draw a card for each Ally you control"; Harabaz Druid: "Add X mana of any one
# color, where X is the number of Allies you control")
# --------------------------------------------------------------------------


@pytest.mark.parametrize("others", [0, 2])
def test_sea_gate_loremaster_draws_per_ally(others):
    scenario = _main(
        _build(
            ["Sea Gate Loremaster"] + ["Ondu Cleric"] * others + ["Grizzly Bears"],
            ["Ondu Cleric"],
        )
    )
    loremaster = scenario.find("Sea Gate Loremaster", Zone.BATTLEFIELD, "alice")
    loremaster.summoning_sick = False
    scenario.activate(loremaster)
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == others + 1


# --------------------------------------------------------------------------
# Static pumps re-evaluated continuously (CR 613.4c): "+1/+0 for each legendary
# creature you control" (Benalish Honor Guard), "+1/+0 for each basic Island you
# control" (Tempest Djinn), "+1/+1 for each land you control named Wastes"
# (Walker of the Wastes). The qualifier is a supertype / a name, not a type.
# --------------------------------------------------------------------------

SHRINES = ["Honden of Life's Web", "Honden of Night's Reach"]  # legendary: distinct names
LEGENDS = ["Isamaru, Hound of Konda", "Thalia, Guardian of Thraben"]


@pytest.mark.parametrize("legends", [0, 1, 2])
def test_benalish_honor_guard_counts_only_legendary_creatures_you_control(legends):
    scenario = _main(
        _build(
            ["Benalish Honor Guard", "Grizzly Bears", "Heroes' Podium"] + LEGENDS[:legends],
            ["Isamaru, Hound of Konda", "Thalia, Guardian of Thraben"],
        )
    )
    chars = _chars(scenario, "Benalish Honor Guard", "alice")
    assert (chars.power, chars.toughness) == (2 + legends, 2)


def test_benalish_honor_guard_is_recounted_when_a_legend_dies():
    scenario = _main(_build(["Benalish Honor Guard", "Isamaru, Hound of Konda"], [], hand=[]))
    assert _chars(scenario, "Benalish Honor Guard", "alice").power == 3
    scenario.game.destroy(scenario.find("Isamaru, Hound of Konda", Zone.BATTLEFIELD, "alice"))
    assert _chars(scenario, "Benalish Honor Guard", "alice").power == 2


@pytest.mark.parametrize("islands", [0, 1, 3])
def test_tempest_djinn_counts_basic_islands_not_dual_lands_or_opposing_ones(islands):
    scenario = _main(
        _build(
            ["Tempest Djinn", "Watery Grave", "Swamp"] + ["Island"] * islands,
            ["Island", "Island"],
        )
    )
    chars = _chars(scenario, "Tempest Djinn", "alice")
    assert (chars.power, chars.toughness) == (islands, 4)


@pytest.mark.parametrize("wastes", [0, 1, 2])
def test_walker_of_the_wastes_counts_lands_named_wastes(wastes):
    scenario = _main(
        _build(
            ["Walker of the Wastes", "Llanowar Wastes", "Forest"] + ["Wastes"] * wastes,
            ["Wastes", "Wastes"],
        )
    )
    chars = _chars(scenario, "Walker of the Wastes", "alice")
    assert (chars.power, chars.toughness) == (4 + wastes, 4 + wastes)


# --------------------------------------------------------------------------
# "Whenever this creature attacks, it gets +X/+X until end of turn, where X is the
# number of legendary creatures you control" (Bag End Porter)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("legends", [0, 1, 2])
def test_bag_end_porter_pumps_by_legendary_creatures_when_it_attacks(legends):
    scenario = _main(
        _build(["Bag End Porter", "Grizzly Bears"] + LEGENDS[:legends], ["Isamaru, Hound of Konda"])
    )
    porter = scenario.find("Bag End Porter", Zone.BATTLEFIELD, "alice")
    porter.summoning_sick = False
    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers
    scenario.attack_with(porter)
    while scenario.game.stack:
        scenario.pass_until_resolved()
    chars = _chars(scenario, "Bag End Porter", "alice")
    assert (chars.power, chars.toughness) == (4 + legends, 4 + legends)


# --------------------------------------------------------------------------
# Proof printings of the same qualified counts in other wording
# --------------------------------------------------------------------------


@pytest.mark.parametrize("named", [0, 1, 3])
def test_cleric_of_the_forward_order_counts_creatures_named_itself(named):
    scenario = _main(
        _build(
            ["Plains"] * 3 + ["Cleric of the Forward Order"] * named + ["Grizzly Bears"],
            ["Cleric of the Forward Order"] * 2,
            hand=["Cleric of the Forward Order"],
        )
    )
    _enter(scenario, "Cleric of the Forward Order")
    assert scenario.player("alice").life == 20 + 2 * (named + 1)


@pytest.mark.parametrize("swamps", [0, 2])
def test_flow_of_knowledge_draws_per_island_you_control(swamps):
    """Eight Islands: the draw counts Islands (tapped or not), not the Swamps beside them;
    the two discards come after the draw."""
    scenario = _main(
        _build(["Island"] * 8 + ["Swamp"] * swamps, ["Island"] * 3, hand=["Flow of Knowledge"])
    )
    _cast(scenario, "Flow of Knowledge")
    assert len(scenario.player("alice").library) == 12 - 8
    assert len(scenario.player("alice").hand) == 8 - 2


def _tokens(scenario, name, username="alice"):
    return [
        permanent
        for permanent in scenario.game.permanents_controlled_by(username)
        if permanent.name in (name, f"{name} Token")
    ]


def _lands(scenario, username="alice"):
    return [
        permanent
        for permanent in scenario.game.permanents_controlled_by(username)
        if scenario.game.characteristics_of(permanent).is_land
    ]


# --------------------------------------------------------------------------
# "For each <group> you control, create <tokens>" - the leading form (Brass's
# Bounty, Crescent Island Temple, Moogles' Valor). The count is taken once, as the
# instruction is performed (CR 608.2h), and the tokens are made together.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("extra_lands", [0, 2])
def test_brass_s_bounty_makes_a_treasure_for_each_land_you_control(extra_lands):
    scenario = _main(
        _build(
            ["Mountain"] * (7 + extra_lands) + ["Grizzly Bears"],
            ["Forest"] * 4,
            hand=["Brass's Bounty"],
        )
    )
    _cast(scenario, "Brass's Bounty")
    assert len(_tokens(scenario, "Treasure")) == 7 + extra_lands
    assert len(_tokens(scenario, "Treasure", "bob")) == 0


@pytest.mark.parametrize("other_shrines", [0, 1])
def test_crescent_island_temple_makes_a_monk_for_each_shrine_you_control(other_shrines):
    scenario = _main(
        _build(
            ["Mountain"] * 4 + ["Honden of Life's Web"] * other_shrines,
            ["Honden of Life's Web"],
            hand=["Crescent Island Temple"],
        )
    )
    _enter(scenario, "Crescent Island Temple")
    assert len(_tokens(scenario, "Monk")) == 1 + other_shrines  # the Temple counts itself
    monk = _tokens(scenario, "Monk")[0]
    chars = scenario.game.characteristics_of(monk)
    assert (chars.power, chars.toughness) == (1, 1)


def test_crescent_island_temple_makes_one_more_monk_when_another_shrine_enters():
    scenario = _main(
        _build(
            ["Mountain"] * 4 + ["Forest"] * 7,
            [],
            hand=["Crescent Island Temple", "Honden of Life's Web"],
        )
    )
    _enter(scenario, "Crescent Island Temple")
    assert len(_tokens(scenario, "Monk")) == 1
    scenario.cast_onto_stack("Honden of Life's Web", auto=True, username="alice")
    while scenario.game.stack:
        scenario.pass_until_resolved()
    assert len(_tokens(scenario, "Monk")) == 2


@pytest.mark.parametrize("creatures", [0, 1, 3])
def test_moogles_valor_makes_a_lifelink_token_per_creature_then_grants_indestructible(creatures):
    scenario = _main(
        _build(
            ["Plains"] * 5 + ["Grizzly Bears"] * creatures,
            ["Grizzly Bears"] * 2,
            hand=["Moogles' Valor"],
        )
    )
    _cast(scenario, "Moogles' Valor")
    moogles = _tokens(scenario, "Moogle")
    assert len(moogles) == creatures  # counted before the tokens exist; opponent's not counted
    for moogle in moogles:
        chars = scenario.game.characteristics_of(moogle)
        assert (chars.power, chars.toughness) == (1, 2)
    for creature in [*moogles, *_tokens(scenario, "Grizzly Bears")]:
        assert has_keyword(creature, "indestructible", scenario.game)
    for bear in _tokens(scenario, "Grizzly Bears", "bob"):
        assert not has_keyword(bear, "indestructible", scenario.game)


# --------------------------------------------------------------------------
# "..., where X is the number of <group> you control" over a whole multi-sentence
# body (Kyoshi Island Plaza, Nessian Game Warden, Seismic Sense)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("other_shrines", [0, 1, 2])
def test_kyoshi_island_plaza_fetches_a_tapped_basic_per_shrine(other_shrines):
    scenario = _main(
        _build(
            ["Forest"] * 4 + SHRINES[:other_shrines],
            [],
            hand=["Kyoshi Island Plaza"],
            alice_library=["Forest"] * 6 + ["Plains"] * 4,
        )
    )
    lands_before = len(_lands(scenario))
    _enter(scenario, "Kyoshi Island Plaza")
    fetched = len(_lands(scenario)) - lands_before
    assert fetched == 1 + other_shrines
    assert len(scenario.player("alice").library) == 10 - fetched
    assert sum(1 for land in _lands(scenario) if land.tapped) >= fetched


@pytest.mark.parametrize("forests", [2, 3, 4])
def test_nessian_game_warden_looks_at_a_card_per_forest(forests):
    """The Bears are third from the top: seen with three or more Forests. The Warden is
    not a Forest and the Islands beside the Forests are not counted."""
    scenario = _main(
        _build(
            ["Forest"] * forests + ["Island"] * (5 - forests if forests < 5 else 0) + ["Island"],
            [],
            hand=["Nessian Game Warden"],
            alice_library=["Island", "Island", "Grizzly Bears", "Plains", "Plains", "Plains"],
        )
    )
    if forests >= 3:  # the Bears are third from the top: seen, and taken
        scenario.scry_bottoming(
            scenario.find("Grizzly Bears", Zone.LIBRARY, "alice"), username="alice"
        )
    scenario.cast_onto_stack("Nessian Game Warden", auto=True, username="alice")
    while scenario.game.stack:
        scenario.pass_until_resolved()
    in_hand = [card.name for card in scenario.player("alice").hand]
    assert ("Grizzly Bears" in in_hand) == (forests >= 3)
    # whatever was looked at and not taken went to the bottom
    assert len(scenario.player("alice").library) == 6 - (1 if forests >= 3 else 0)


@pytest.mark.parametrize("extra_lands", [0, 1, 3])
def test_seismic_sense_looks_at_a_card_per_land(extra_lands):
    lands = 1 + extra_lands  # the Forest that pays for it counts
    scenario = _main(
        _build(
            ["Forest"] + ["Island"] * extra_lands,
            ["Island"] * 5,
            hand=["Seismic Sense"],
            alice_library=["Island"] * 2 + ["Grizzly Bears"] + ["Plains"] * 3,
        )
    )
    if lands >= 3:  # the Bears are third from the top: seen, and taken
        scenario.scry_bottoming(
            scenario.find("Grizzly Bears", Zone.LIBRARY, "alice"), username="alice"
        )
    _cast(scenario, "Seismic Sense")
    in_hand = [card.name for card in scenario.player("alice").hand]
    # The Bears are third from the top: seen with three or more lands (bob's do not count)
    assert ("Grizzly Bears" in in_hand) == (lands >= 3)


# --------------------------------------------------------------------------
# "where X is twice the number of Blood tokens you control" (Bloodtithe Harvester)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("blood", [1, 2])
def test_bloodtithe_harvester_shrinks_by_twice_the_blood_tokens(blood):
    scenario = _main(_build(["Bloodtithe Harvester"], ["Shivan Dragon"]))
    for _ in range(blood):
        create_predefined_tokens(scenario.game, "Blood", "alice")
    create_predefined_tokens(scenario.game, "Blood", "bob")  # not counted
    harvester = scenario.find("Bloodtithe Harvester", Zone.BATTLEFIELD, "alice")
    harvester.summoning_sick = False
    dragon = scenario.find("Shivan Dragon", Zone.BATTLEFIELD, "bob")
    scenario.activate(harvester, targets=[dragon])
    scenario.pass_until_resolved()
    assert scenario.game.characteristics_of(dragon).power == 5 - 2 * blood


def test_bloodtithe_harvester_kills_a_creature_when_twice_the_blood_tokens_covers_its_toughness():
    scenario = _main(_build(["Bloodtithe Harvester"], ["Grizzly Bears"]))
    for _ in range(2):
        create_predefined_tokens(scenario.game, "Blood", "alice")
    harvester = scenario.find("Bloodtithe Harvester", Zone.BATTLEFIELD, "alice")
    harvester.summoning_sick = False
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    scenario.activate(harvester, targets=[bears])
    scenario.pass_until_resolved()
    assert bears.zone is Zone.GRAVEYARD



# --------------------------------------------------------------------------
# Counted legendary creatures / Allies as the count of a larger instruction
# (The Ring Goes South, Bala Ged Thief, Vastwood Animist)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("legends", [0, 1, 2])
def test_ring_goes_south_puts_one_land_per_legendary_creature_onto_the_battlefield_tapped(legends):
    """CR 701.54a: the Ring tempts you; then lands are revealed until X are found, X
    being the legendary creatures you control (the opponent's are not counted); the
    lands enter tapped (CR 701.20) and the rest go to the bottom of the library."""
    scenario = _main(
        _build(
            ["Forest"] * 4 + ["Isamaru, Hound of Konda", "Kaza, Roil Chaser"][:legends],
            ["Isamaru, Hound of Konda", "Kaza, Roil Chaser"],
            hand=["The Ring Goes South"],
            alice_library=["Grizzly Bears", "Island", "Grizzly Bears", "Plains", "Swamp", "Mountain"],
        )
    )
    lands_before = len(_lands(scenario))
    _cast(scenario, "The Ring Goes South")
    assert scenario.player("alice").ring_tempted_count == 1
    entered = _lands(scenario)[lands_before:]
    assert len(entered) == legends
    assert all(land.tapped for land in entered)
    library = [card.name for card in scenario.player("alice").library]
    assert len(library) == 6 - legends
    if legends == 2:  # revealed down to the second land; the two Bears went to the bottom
        assert library == ["Swamp", "Mountain", "Grizzly Bears", "Grizzly Bears"]


def _bala_ged_scenario(hand_names, allies):
    return _main(
        _build(
            ["Swamp"] * 4 + ["Tajuru Archer"] * allies,
            [],
            hand=["Bala Ged Thief"],
            bob_hand=hand_names,
        )
    )


@pytest.mark.parametrize("allies", [0, 1])
def test_bala_ged_thief_makes_the_player_discard_a_card_the_controller_picks(allies):
    """Allies counted include Bala Ged Thief itself; with a hand no bigger than the
    count, every card is revealed and the controller chooses which is discarded."""
    scenario = _bala_ged_scenario(["Forest", "Island"], allies)
    scenario.choose_trigger_targets("Bala Ged Thief", ["bob"])
    island = scenario.find("Island", Zone.HAND, "bob")
    scenario.will_choose_cards(island, source="Bala Ged Thief")
    scenario.cast_onto_stack("Bala Ged Thief", auto=True, username="alice")
    while scenario.game.stack:
        scenario.pass_until_resolved()
    assert island.zone is Zone.GRAVEYARD
    assert len(scenario.player("bob").hand) == 1


def test_bala_ged_thief_with_more_cards_than_allies_reveals_only_the_ally_count():
    """One Ally (Bala Ged itself): the opponent reveals exactly one of three cards,
    and that is the card that is discarded."""
    scenario = _bala_ged_scenario(["Forest", "Island", "Mountain"], 0)
    scenario.choose_trigger_targets("Bala Ged Thief", ["bob"])
    mountain = scenario.find("Mountain", Zone.HAND, "bob")
    scenario.will_choose_cards(mountain, username="bob", times=None)
    scenario.will_choose_cards(mountain, username="alice", times=None)
    scenario.cast_onto_stack("Bala Ged Thief", auto=True, username="alice")
    while scenario.game.stack:
        scenario.pass_until_resolved()
    assert mountain.zone is Zone.GRAVEYARD
    assert len(scenario.player("bob").hand) == 2


@pytest.mark.parametrize("allies", [0, 1, 3])
def test_vastwood_animist_makes_a_land_an_x_x_elemental_for_the_ally_count(allies):
    """X is the Allies you control (the Animist included), fixed as the ability
    resolves (CR 608.2h); it is still a land (CR 205.1b)."""
    scenario = _main(
        _build(
            ["Vastwood Animist", "Forest"] + ["Tajuru Archer"] * allies + ["Grizzly Bears"],
            ["Tajuru Archer", "Tajuru Archer"],
        )
    )
    animist = scenario.find("Vastwood Animist", Zone.BATTLEFIELD, "alice")
    animist.summoning_sick = False
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    scenario.activate(animist, targets=[forest])
    scenario.pass_until_resolved()
    chars = scenario.game.characteristics_of(forest)
    assert chars.is_land and chars.is_creature
    assert (chars.power, chars.toughness) == (allies + 1, allies + 1)
    assert "Elemental" in chars.subtypes


# --------------------------------------------------------------------------
# "reveals a number of cards from their hand equal to the number of Swamps you
# control. You choose one of them. That player discards that card." (Mire's Toll)
# CR 701.20 (reveal), CR 701.9b (the discard is chosen by someone else).
# --------------------------------------------------------------------------


@pytest.mark.parametrize("swamps", [1, 2])
def test_mire_s_toll_reveals_as_many_cards_as_swamps_and_discards_the_one_chosen(swamps):
    """Swamps counted include the one that pays; the opponent's are not counted. With
    a hand of three and fewer Swamps than that, the revealing player picks which cards
    to show, and the caster picks the one that goes."""
    scenario = _main(
        _build(
            ["Swamp"] * swamps + ["Island"] * 2,
            ["Swamp"] * 4,
            hand=["Mire's Toll"],
            bob_hand=["Forest", "Island", "Mountain"],
        )
    )
    forest = scenario.find("Forest", Zone.HAND, "bob")
    island = scenario.find("Island", Zone.HAND, "bob")
    mountain = scenario.find("Mountain", Zone.HAND, "bob")
    shown = (forest, island)[:swamps]
    scenario.will_choose_cards(*shown, username="bob", times=None)
    scenario.will_choose_cards(shown[-1], username="alice", times=None)
    _cast(scenario, "Mire's Toll", targets=["bob"])
    assert shown[-1].zone is Zone.GRAVEYARD
    assert len(scenario.player("bob").hand) == 2
    assert mountain.zone is Zone.HAND
    assert len(scenario.player("alice").hand) == 0


def test_mire_s_toll_with_a_hand_no_bigger_than_the_swamps_reveals_it_all():
    scenario = _main(
        _build(["Swamp"] * 3, [], hand=["Mire's Toll"], bob_hand=["Forest", "Island"])
    )
    island = scenario.find("Island", Zone.HAND, "bob")
    scenario.will_choose_cards(island, username="alice", times=None)
    _cast(scenario, "Mire's Toll", targets=["bob"])
    assert island.zone is Zone.GRAVEYARD
    assert len(scenario.player("bob").hand) == 1


# --------------------------------------------------------------------------
# "Search target player's library for up to X cards, where X is the number of
# Swamps you control, and exile them. Then that player shuffles." (Nightmare
# Incursion). CR 701.23a/b: the searcher is the caster, who finds up to X; CR
# 701.24b: the library's owner shuffles; CR 406.2 (exile).
# --------------------------------------------------------------------------

TARGET_LIBRARY = ["Island", "Forest", "Mountain", "Plains", "Grizzly Bears", "Craw Wurm"]


@pytest.mark.parametrize("swamps", [1, 2, 3])
def test_nightmare_incursion_exiles_up_to_the_swamp_count_from_the_targets_library(swamps):
    """The caster picks which cards (the library's owner is not asked); Swamps the
    opponent controls are not counted."""
    scenario = _main(
        _build(
            ["Swamp"] * swamps + ["Island"] * (6 - swamps),
            ["Swamp"] * 4,
            hand=["Nightmare Incursion"],
            bob_library=TARGET_LIBRARY,
        )
    )
    picked = [scenario.find(name, Zone.LIBRARY, "bob") for name in TARGET_LIBRARY[-swamps:]]
    scenario.will_choose_cards(*picked, username="alice", times=None)
    _cast(scenario, "Nightmare Incursion", targets=["bob"])
    assert len(scenario.player("bob").library) == 6 - swamps
    for card in picked:
        assert card.zone is Zone.EXILE
    assert len(scenario.player("alice").library) == 12


# --------------------------------------------------------------------------
# "return each creature your opponents control with toughness X or less to its
# owner's hand, where X is the number of Islands you control" (Scourge of
# Fleets). CR 608.2h: X is fixed as the ability resolves; CR 400.3: a card
# returned goes to its owner's hand; CR 208.1 (toughness).
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("islands", "returned"),
    [
        (2, ["Grizzly Bears"]),
        (3, ["Grizzly Bears", "Hill Giant"]),
        (4, ["Grizzly Bears", "Hill Giant", "Serra Angel"]),
    ],
)
def test_scourge_of_fleets_returns_opposing_creatures_up_to_the_island_count(islands, returned):
    """Toughness 2, 3 and 4 against 2, 3 and 4 Islands; the Swamps beside the Islands
    and the caster's own creature are not touched."""
    scenario = _main(
        _build(
            ["Island"] * islands + ["Swamp"] * (7 - islands) + ["Grizzly Bears"],
            ["Grizzly Bears", "Hill Giant", "Serra Angel", "Island"],
            hand=["Scourge of Fleets"],
        )
    )
    _enter(scenario, "Scourge of Fleets")
    assert sorted(card.name for card in scenario.player("bob").hand) == sorted(returned)
    assert len(_tokens(scenario, "Grizzly Bears", "alice")) == 1
    assert len(_lands(scenario, "bob")) == 1


# --------------------------------------------------------------------------
# "put target creature into its owner's library just beneath the top X cards of
# that library, where X is the number of Plains you control" (Quarry Colossus).
# CR 401.1/401.2 (a library's cards are in a set order), CR 608.2h (X fixed as the
# ability resolves), CR 609.3 (a library shorter than X: as much as can be done).
# --------------------------------------------------------------------------


@pytest.mark.parametrize("plains", [2, 4, 7])
def test_quarry_colossus_tucks_the_target_beneath_the_top_plains_count_cards(plains):
    """Bob's library holds 12 Forests: the Bears end up with exactly `plains` cards
    above them. The Swamps and bob's own Plains are not counted."""
    scenario = _main(
        _build(
            ["Plains"] * plains + ["Swamp"] * (7 - plains),
            ["Grizzly Bears", "Plains", "Plains"],
            hand=["Quarry Colossus"],
        )
    )
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    _enter(scenario, "Quarry Colossus", targets=[bears])
    library = scenario.player("bob").library
    assert bears.zone is Zone.LIBRARY
    assert library.index(bears) == plains


def test_quarry_colossus_in_a_shallow_library_puts_the_target_at_the_bottom():
    scenario = _main(
        _build(["Plains"] * 7, ["Grizzly Bears"], hand=["Quarry Colossus"], bob_library=["Forest"] * 3)
    )
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    _enter(scenario, "Quarry Colossus", targets=[bears])
    assert scenario.player("bob").library.index(bears) == 3
