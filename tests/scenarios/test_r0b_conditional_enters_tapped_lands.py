"""Lands whose "enters tapped unless ..." line is a replacement effect on how
the land enters (CR 614.1d, CR 614.12), proven per printing:

- fast lands (Blooming Marsh, Inspiring Vantage, Concealed Courtyard): untapped
  with two or fewer other lands, tapped with three or more.
- slow lands (Shattered Sanctum, Stormcarved Coast, Sundown Pass): tapped with
  zero or one other lands, untapped with two or more.
- Castle Locthwain: untapped only with a Swamp (a nonbasic Swamp counts), and
  its {1}{B}{B},{T} draws and then loses life equal to the hand size.
- The Lonely Mountain: untapped only with an Equipment; its Dwarf ability costs
  {1} less per Equipment (CR 601.2f, never below the coloured part, CR 601.2f
  reduces only generic) and is sorcery-speed only (CR 602.5d).

A land never counts itself among its "other lands" (CR 614.12).
CR numbers were looked up with `mise run rules:find <n>`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario

FOUR = ["Forest", "Island", "Swamp", "Mountain"]


def _board(land, battlefield=(), bob_battlefield=(), library=("Forest", "Island")):
    scenario = (
        Scenario()
        .player("alice", hand=[land], battlefield=list(battlefield), library=list(library))
        .player("bob", battlefield=list(bob_battlefield), library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


FAST = ["Blooming Marsh", "Inspiring Vantage", "Concealed Courtyard"]
SLOW = ["Shattered Sanctum", "Stormcarved Coast", "Sundown Pass"]


@pytest.mark.parametrize("land", FAST)
@pytest.mark.parametrize(
    ("others", "tapped"),
    [(0, False), (1, False), (2, False), (3, True), (4, True)],
)
def test_fast_land_enters_tapped_from_three_other_lands(land, others, tapped):
    scenario = _board(land, FOUR[:others])

    placed = scenario.play_land(land)

    assert placed.zone is Zone.BATTLEFIELD
    assert placed.tapped is tapped


@pytest.mark.parametrize("land", FAST)
def test_fast_land_ignores_opponents_lands_and_nonlands(land):
    scenario = _board(
        land,
        ["Forest", "Grizzly Bears", "Bonesplitter"],
        bob_battlefield=["Swamp", "Mountain", "Plains", "Plains"],
    )

    assert scenario.play_land(land).tapped is False


@pytest.mark.parametrize("land", SLOW)
@pytest.mark.parametrize(
    ("others", "tapped"),
    [(0, True), (1, True), (2, False), (3, False), (4, False)],
)
def test_slow_land_enters_untapped_from_two_other_lands(land, others, tapped):
    scenario = _board(land, FOUR[:others])

    placed = scenario.play_land(land)

    assert placed.zone is Zone.BATTLEFIELD
    assert placed.tapped is tapped


@pytest.mark.parametrize("land", SLOW)
def test_slow_land_does_not_count_itself_or_opponents_lands(land):
    scenario = _board(land, ["Forest"], bob_battlefield=["Swamp", "Mountain", "Plains"])

    assert scenario.play_land(land).tapped is True


# -- Castle Locthwain ---------------------------------------------------------


@pytest.mark.parametrize(
    ("others", "tapped"),
    [
        ([], True),
        (["Forest", "Island", "Mountain"], True),
        (["Swamp"], False),
        (["Forest", "Swamp"], False),
        (["Watery Grave"], False),  # a nonbasic land with the Swamp type counts
    ],
)
def test_castle_locthwain_needs_a_swamp(others, tapped):
    scenario = _board("Castle Locthwain", others)

    castle = scenario.play_land("Castle Locthwain")

    assert castle.tapped is tapped


def test_castle_locthwain_ignores_an_opponents_swamp():
    scenario = _board("Castle Locthwain", ["Forest"], bob_battlefield=["Swamp"])

    assert scenario.play_land("Castle Locthwain").tapped is True


def test_castle_locthwain_draws_then_loses_life_for_the_hand_after_the_draw():
    """Hand is 0 before the draw, so the loss is 1 (the drawn card), not 0."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Castle Locthwain", "Swamp", "Swamp", "Swamp"],
            library=["Forest", "Island"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    castle = scenario.find("Castle Locthwain", Zone.BATTLEFIELD)

    scenario.activate(castle, *scenario.untapped_sources("Swamp", "Swamp", "Swamp"), index=1)
    scenario.resolve_top()

    assert len(scenario.player("alice").hand) == 1
    assert scenario.player("alice").life == 19
    assert castle.tapped


def test_castle_locthwain_life_loss_counts_the_whole_hand():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Shock", "Shock"],
            battlefield=["Castle Locthwain", "Swamp", "Swamp", "Swamp"],
            library=["Forest", "Island"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    castle = scenario.find("Castle Locthwain", Zone.BATTLEFIELD)

    scenario.activate(castle, *scenario.untapped_sources("Swamp", "Swamp", "Swamp"), index=1)
    scenario.resolve_top()

    assert len(scenario.player("alice").hand) == 3
    assert scenario.player("alice").life == 17


# -- The Lonely Mountain ------------------------------------------------------


@pytest.mark.parametrize(
    ("others", "tapped"),
    [
        ([], True),
        (["Forest", "Grizzly Bears"], True),
        (["Bonesplitter"], False),
        (["Sword of Fire and Ice", "Forest"], False),
    ],
)
def test_the_lonely_mountain_needs_an_equipment(others, tapped):
    scenario = _board("The Lonely Mountain", others)

    mountain = scenario.play_land("The Lonely Mountain")

    assert mountain.tapped is tapped


def test_the_lonely_mountain_ignores_an_opponents_equipment():
    scenario = _board("The Lonely Mountain", [], bob_battlefield=["Bonesplitter"])

    assert scenario.play_land("The Lonely Mountain").tapped is True


def test_the_lonely_mountain_is_a_mountain_that_taps_for_red():
    scenario = _board("The Lonely Mountain", ["Bonesplitter"])
    mountain = scenario.play_land("The Lonely Mountain")

    assert "Mountain" in mountain.card.type_line
    scenario.activate(mountain, index=1)
    assert scenario.player("alice").mana_pool.floating == {Color.RED: 1}


def _dwarf_board(equipment, lands=5):
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Lonely Mountain", *equipment, *["Mountain"] * lands])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _make_dwarf(scenario, paying):
    mountain = scenario.find("The Lonely Mountain", Zone.BATTLEFIELD)
    scenario.activate(
        mountain, *scenario.untapped_sources("Mountain", *["Mountain"] * (paying - 1)), index=0
    )
    scenario.resolve_top()


def test_the_lonely_mountain_makes_a_two_two_dwarf_for_five_with_no_equipment():
    scenario = _dwarf_board([], lands=5)
    _make_dwarf(scenario, 5)
    dwarf = scenario.creature("Dwarf Token")
    assert (dwarf.power, dwarf.toughness) == (2, 2)


@pytest.mark.parametrize(
    ("equipment", "mana_needed"),
    [
        ([], 5),
        (["Bonesplitter"], 4),
        (["Bonesplitter", "Sword of Fire and Ice"], 3),
        (["Bonesplitter", "Sword of Fire and Ice", "Sword of Feast and Famine"], 2),
    ],
)
def test_the_lonely_mountain_costs_one_less_per_equipment(equipment, mana_needed):
    scenario = _dwarf_board(equipment, lands=mana_needed)
    mountain = scenario.find("The Lonely Mountain", Zone.BATTLEFIELD)
    sources = scenario.untapped_sources(*["Mountain"] * mana_needed)

    scenario.activate(mountain, *sources, index=0)
    scenario.resolve_top()

    dwarf = scenario.creature("Dwarf Token")
    assert (dwarf.power, dwarf.toughness) == (2, 2)
    assert mountain.tapped


def test_the_lonely_mountain_reduction_never_eats_the_coloured_part():
    """Five Equipment cannot reduce {4}{R} below {R}: a single red mana pays."""
    equipment = ["Bonesplitter"] * 5
    scenario = _dwarf_board(equipment, lands=1)
    mountain = scenario.find("The Lonely Mountain", Zone.BATTLEFIELD)

    scenario.activate(mountain, *scenario.untapped_sources("Mountain"), index=0)
    scenario.resolve_top()

    assert scenario.creature("Dwarf Token").power == 2


def test_the_lonely_mountain_cannot_pay_a_reduced_cost_with_too_little_mana():
    scenario = _dwarf_board(["Bonesplitter"], lands=3)
    mountain = scenario.find("The Lonely Mountain", Zone.BATTLEFIELD)

    with pytest.raises(ValueError):
        scenario.activate(
            mountain, *scenario.untapped_sources("Mountain", "Mountain", "Mountain"), index=0
        )


def test_the_lonely_mountain_is_sorcery_speed_only():
    scenario = _dwarf_board([], lands=5)
    mountain = scenario.find("The Lonely Mountain", Zone.BATTLEFIELD)
    assert scenario.why_cannot_activate(mountain, 0) is None

    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    assert scenario.why_cannot_activate(mountain, 0) is not None


def test_the_lonely_mountain_is_refused_while_the_stack_is_not_empty():
    scenario = (
        Scenario()
        .player("alice", hand=["Shock"], battlefield=["The Lonely Mountain", *["Mountain"] * 6])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack("Shock", scenario.untapped_sources("Mountain")[0], targets=["bob"])
    mountain = scenario.find("The Lonely Mountain", Zone.BATTLEFIELD)

    assert scenario.why_cannot_activate(mountain, 0) is not None


# -- the widened reader: a subtype quality ("for each Equipment/Island/Shrine
# you control") on second and third printings (CR 601.2f via CR 602.2b, CR 205.3) --


def test_waterbending_scroll_costs_one_less_per_island_you_control():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Waterbending Scroll", "Island", "Island", "Forest", *["Island"] * 4],
            library=["Forest", "Island"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scroll = scenario.find("Waterbending Scroll", Zone.BATTLEFIELD)
    # {6} less one per Island (6 Islands) = {0}; the Forest is not an Island.
    scenario.activate(scroll)
    scenario.resolve_top()

    assert len(scenario.player("alice").hand) == 1
    assert scroll.tapped


def test_waterbending_scroll_pays_the_remainder_when_fewer_islands():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Waterbending Scroll", "Island", "Island", *["Forest"] * 4],
            library=["Forest", "Island"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scroll = scenario.find("Waterbending Scroll", Zone.BATTLEFIELD)

    scenario.activate(scroll, *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest"))
    scenario.resolve_top()

    assert len(scenario.player("alice").hand) == 1


def test_sanctum_of_tranquil_light_counts_shrines_it_controls_including_itself():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Sanctum of Tranquil Light", *["Plains"] * 5])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sanctum = scenario.find("Sanctum of Tranquil Light", Zone.BATTLEFIELD)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")

    # {5}{W} less {1} for the one Shrine (itself) = {4}{W}: five Plains.
    scenario.activate(sanctum, *scenario.untapped_sources(*["Plains"] * 5), targets=[bears])
    scenario.resolve_top()

    assert bears.tapped
