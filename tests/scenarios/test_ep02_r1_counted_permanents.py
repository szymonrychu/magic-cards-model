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
