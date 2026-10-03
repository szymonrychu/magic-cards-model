"""R0b proofs: landfall payoffs, +1/+1 counter doubling, and the cost shapes
around them - Mossborn Hydra, Sapling Nursery, Sakura-Tribe Scout and Gene
Pollinator, each proven through the engine.

Every CR number below was looked up with `mise run rules:find` (on-disk CR
effective 2026-09-25) in the session that wrote this file:

- **CR 702.41a** - affinity for [text]: this spell costs {1} less to cast for
  each [text] you control (generic part only).
- **CR 614.1c** - "enters with ..." is a replacement effect, so the counter is
  on the permanent the moment it exists.
- **CR 603.6a** - "whenever a land you control enters" triggers on the entry.
- **CR 305.1** - playing a land is a special action; an effect putting a land
  onto the battlefield is not a land play.
- **CR 702.12b** - indestructible permanents are not destroyed by lethal
  damage or "destroy".
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.keywords import is_indestructible
from magic_cards_model.models import Zone
from magic_cards_model.models.mana import Color
from tests.scenarios.harness import Scenario

HYDRA = "Mossborn Hydra"
NURSERY = "Sapling Nursery"
SCOUT = "Sakura-Tribe Scout"
POLLINATOR = "Gene Pollinator"


def _pt(scenario, permanent):
    state = scenario.game.computed_board().of(permanent)
    return state.power, state.toughness


def _treefolk(scenario):
    return [c for c in scenario.game.battlefield if c.name == "Treefolk Token"]


# -- Mossborn Hydra ----------------------------------------------------------


def _hydra_on_battlefield(hand_lands=2):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[HYDRA] + ["Forest"] * hand_lands,
            battlefield=["Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    hydra = scenario.cast_and_resolve(HYDRA, *sources)
    return scenario, hydra


def test_hydra_enters_with_a_counter_as_a_1_1_trampler():
    scenario, hydra = _hydra_on_battlefield()

    assert hydra.zone is Zone.BATTLEFIELD
    assert hydra.counter_count("+1/+1") == 1, "CR 614.1c: it enters with the counter"
    assert _pt(scenario, hydra) == (1, 1), (
        "a 0/0 survives only because the counter is already there"
    )
    assert has_keyword(hydra, Keyword.TRAMPLE, scenario.game)


def test_hydra_landfall_doubles_one_two_four():
    scenario, hydra = _hydra_on_battlefield()

    scenario.play_land("Forest")
    scenario.pass_until_resolved()
    assert hydra.counter_count("+1/+1") == 2
    assert _pt(scenario, hydra) == (2, 2)


def test_hydra_doubles_again_on_the_second_land_of_a_turn():
    """Two landfall events in one turn (a land drop, then a land put in by an
    effect) double twice: 1 -> 2 -> 4."""
    scenario, hydra = _hydra_on_battlefield()

    scenario.play_land("Forest")
    scenario.pass_until_resolved()
    scenario.put_onto_battlefield("Forest", username="alice")
    scenario.pass_until_resolved()

    assert hydra.counter_count("+1/+1") == 4
    assert _pt(scenario, hydra) == (4, 4)


def test_hydra_ignores_an_opponents_land():
    scenario = (
        Scenario()
        .player("alice", hand=[HYDRA], battlefield=["Forest", "Forest", "Forest"])
        .player("bob", hand=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hydra = scenario.cast_and_resolve(
        HYDRA, *scenario.untapped_sources("Forest", "Forest", "Forest")
    )

    scenario.put_onto_battlefield("Forest", username="bob")
    scenario.pass_until_resolved()

    assert hydra.counter_count("+1/+1") == 1, "'a land you control' - bob's land does nothing"


def test_hydra_doubles_only_its_own_plus_one_counters():
    """Another kind of counter on it is left alone by the doubling."""
    scenario, hydra = _hydra_on_battlefield()
    hydra.add_counters("charge", 3)

    scenario.play_land("Forest")
    scenario.pass_until_resolved()

    assert hydra.counter_count("+1/+1") == 2
    assert hydra.counter_count("charge") == 3


# -- Sapling Nursery ---------------------------------------------------------


def test_nursery_affinity_for_forests_reduces_generic_only():
    """CR 702.41a: three Forests make {6}{G}{G} cost {3}{G}{G}; five lands
    pay exactly that and the spell resolves."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[NURSERY],
            battlefield=["Forest", "Forest", "Forest", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Mountain", "Mountain")

    nursery = scenario.cast_and_resolve(NURSERY, *sources)

    assert nursery.zone is Zone.BATTLEFIELD


def test_nursery_affinity_never_pays_the_coloured_pips():
    """Eight Forests cut the six generic to nothing - but {G}{G} stays."""
    scenario = (
        Scenario().player("alice", hand=[NURSERY], battlefield=["Forest"] * 8).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources(*["Forest"] * 8)

    nursery = scenario.cast_and_resolve(NURSERY, forests[0], forests[1])

    assert nursery.zone is Zone.BATTLEFIELD
    assert not any(f.tapped for f in forests[2:]), "only the two coloured pips were paid"


def _nursery_board(extra_battlefield=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Forest", "Forest"],
            battlefield=[NURSERY, "Forest", "Forest", *extra_battlefield],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_nursery_landfall_makes_a_3_4_reach_treefolk():
    scenario = _nursery_board()

    scenario.play_land("Forest")
    scenario.pass_until_resolved()

    (treefolk,) = _treefolk(scenario)
    assert _pt(scenario, treefolk) == (3, 4)
    assert has_keyword(treefolk, Keyword.REACH, scenario.game)


def test_nursery_makes_one_treefolk_per_land_entry():
    scenario = _nursery_board()

    scenario.play_land("Forest")
    scenario.pass_until_resolved()
    scenario.put_onto_battlefield("Forest", username="alice")
    scenario.pass_until_resolved()

    assert len(_treefolk(scenario)) == 2


def test_nursery_exile_ability_makes_treefolk_and_forests_indestructible():
    scenario = _nursery_board(extra_battlefield=["Grizzly Bears", "Mountain"])
    scenario.play_land("Forest")
    scenario.pass_until_resolved()
    (treefolk,) = _treefolk(scenario)
    nursery = scenario.find(NURSERY, Zone.BATTLEFIELD, "alice")
    forests = scenario.untapped_sources("Forest", "Forest")
    bears = scenario.creature("Grizzly Bears", "alice")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")

    scenario.activate(nursery, *forests)
    scenario.pass_until_resolved()

    assert nursery.zone is Zone.EXILE, "the exile is part of the cost"
    assert is_indestructible(treefolk, scenario.game)
    assert all(
        is_indestructible(f, scenario.game) for f in scenario.game.battlefield if f.name == "Forest"
    )
    assert not is_indestructible(bears, scenario.game), "only Treefolk and Forests"
    assert not is_indestructible(mountain, scenario.game)


def test_nursery_indestructible_wears_off_at_end_of_turn():
    scenario = _nursery_board()
    scenario.play_land("Forest")
    scenario.pass_until_resolved()
    (treefolk,) = _treefolk(scenario)
    nursery = scenario.find(NURSERY, Zone.BATTLEFIELD, "alice")
    scenario.activate(nursery, *scenario.untapped_sources("Forest", "Forest"))
    scenario.pass_until_resolved()
    assert is_indestructible(treefolk, scenario.game)

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    assert is_indestructible(treefolk, scenario.game), "still on in the end step"
    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    assert not is_indestructible(treefolk, scenario.game)


# -- Sakura-Tribe Scout ------------------------------------------------------


def test_scout_puts_a_land_from_hand_onto_the_battlefield():
    scenario = (
        Scenario().player("alice", hand=["Mountain"], battlefield=[SCOUT]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scout = scenario.creature(SCOUT, "alice")

    scenario.activate(scout)
    scenario.pass_until_resolved()

    mountain = scenario.find("Mountain", Zone.BATTLEFIELD)
    assert mountain.zone is Zone.BATTLEFIELD
    assert not mountain.tapped
    assert scout.tapped


def test_scout_is_not_a_land_play():
    """CR 305.1: the land drop is still available afterwards."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mountain", "Mountain"], battlefield=[SCOUT])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.activate(scenario.creature(SCOUT, "alice"))
    scenario.pass_until_resolved()
    assert scenario.game.lands_played.get("alice", 0) == 0

    scenario.play_land("Mountain")

    assert scenario.game.lands_played["alice"] == 1
    assert [c.name for c in scenario.game.battlefield].count("Mountain") == 2
    assert scenario.player("alice").hand == []


def test_scout_with_no_land_in_hand_only_taps():
    scenario = (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], battlefield=[SCOUT])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scout = scenario.creature(SCOUT, "alice")

    scenario.activate(scout)
    scenario.pass_until_resolved()

    assert scout.tapped
    assert scenario.find("Grizzly Bears", Zone.HAND).zone is Zone.HAND
    assert scenario.game.decisions.asked == [], "nothing legal to choose, nothing asked"


def test_scout_may_decline_the_land():
    scenario = (
        Scenario().player("alice", hand=["Mountain"], battlefield=[SCOUT]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, username="alice", source=SCOUT)

    scenario.activate(scenario.creature(SCOUT, "alice"))
    scenario.pass_until_resolved()

    assert scenario.find("Mountain", Zone.HAND).zone is Zone.HAND


def test_scout_lands_trigger_landfall():
    """The land enters the battlefield, so a landfall permanent sees it (CR 603.6a)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mountain"], battlefield=[SCOUT, NURSERY])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.activate(scenario.creature(SCOUT, "alice"))
    scenario.pass_until_resolved()  # the Scout's ability, which queues the landfall trigger
    scenario.pass_until_resolved()

    assert len(_treefolk(scenario)) == 1


# -- Gene Pollinator ---------------------------------------------------------


def test_pollinator_taps_another_permanent_for_one_mana_of_any_colour():
    scenario = (
        Scenario().player("alice", battlefield=[POLLINATOR, "Mountain"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pollinator = scenario.creature(POLLINATOR, "alice")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.activate(pollinator, color=Color.BLUE, tapping_for_cost=[mountain])

    assert scenario.player("alice").mana_pool.floating == {Color.BLUE: 1}
    assert pollinator.tapped and mountain.tapped
    assert scenario.stack_names() == [], "CR 605.3b: a mana ability never uses the stack"


def test_pollinator_cannot_pay_its_second_cost_with_itself():
    """'Tap an untapped permanent you control' is a second cost, paid with a
    permanent other than the one being activated - the {T} already tapped it."""
    scenario = Scenario().player("alice", battlefield=[POLLINATOR]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pollinator = scenario.creature(POLLINATOR, "alice")

    with pytest.raises(ValueError, match="tap"):
        scenario.activate(pollinator, color=Color.RED)
    with pytest.raises(ValueError):
        scenario.activate(pollinator, color=Color.RED, tapping_for_cost=[pollinator])
    assert not pollinator.tapped
    assert scenario.player("alice").mana_pool.floating == {}


def test_pollinator_makes_each_colour_on_request():
    for color in (Color.WHITE, Color.RED, Color.GREEN):
        scenario = (
            Scenario().player("alice", battlefield=[POLLINATOR, "Mountain"]).player("bob").build()
        )
        scenario.start_at(Step.PRECOMBAT_MAIN)
        (mountain,) = scenario.untapped_sources("Mountain")
        scenario.activate(
            scenario.creature(POLLINATOR, "alice"), color=color, tapping_for_cost=[mountain]
        )
        assert scenario.player("alice").mana_pool.floating == {color: 1}
