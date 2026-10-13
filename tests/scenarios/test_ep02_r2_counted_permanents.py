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
from magic_cards_model.models import Zone
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
    """"Whenever this creature or another Ally you control enters": both Clerics
    trigger when the second enters, each counting both Allies (two Allies = 2 life
    each); the non-Ally Bears entering afterwards triggers nothing."""
    scenario = _main(
        _build(["Plains"] * 2 + ["Forest"] * 3 + ["Ondu Cleric"], [], hand=["Ondu Cleric", "Grizzly Bears"])
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
    scenario = _main(
        _build(["Benalish Honor Guard", "Isamaru, Hound of Konda"], [], hand=[])
    )
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
