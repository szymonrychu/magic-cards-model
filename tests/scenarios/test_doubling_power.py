"""Doubling a creature's power (CR 701.10a, CR 701.10b) - Mightform Harmonizer.

"Landfall - Whenever a land you control enters, double the power of target
creature you control until end of turn."

CR 701.10b is the whole mechanic: "To double a creature's power, that creature
gets +X/+0, where X is that creature's power as the spell or ability that
doubles its power resolves." Two consequences drive most of this file:

- Toughness is untouched. CR 701.10a says doubling creates a continuous effect
  that *modifies* power rather than setting it, and this clause only names
  power.
- X is read once, as the ability resolves. It is not a recomputing effect, so
  a pump afterwards does not get doubled retroactively, and doubling twice in
  one turn reads the *already doubled* value the second time - a 2/2 gets +2
  and then +4, finishing at 8/2.

"Until end of turn" ends in the cleanup step (CR 514.2, CR 703.4p), which is
the only place the modification stops applying.

The target is "target creature you control", so CR 601.2c's announcement (via
CR 603.3d, which sends a trigger's targets through the same rules) refuses an
opponent's creature outright, and CR 608.2b's on-resolution check makes a
target that has since left the battlefield do nothing at all.

Azusa, Lost but Seeking is on the board wherever this file needs two land drops
in one turn - a real extra land play rather than a hand-placed permanent, so
the second landfall event is the same event as the first.

CR numbers looked up with `knowledge_search(type="rules")` in this session:
CR 701.10a, CR 701.10b, CR 701.10c, CR 603.6a, CR 603.3d, CR 601.2c, CR 115.1c,
CR 608.2b, CR 608.3b, CR 514.2, CR 703.4p.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

HARMONIZER = "Mightform Harmonizer"


def board(
    *,
    alice_battlefield: list[str],
    alice_hand: list[str] | None = None,
    bob_battlefield: list[str] | None = None,
) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=alice_battlefield, hand=alice_hand or [])
        .player("bob", battlefield=bob_battlefield or [])
    )


def power_toughness(scenario: PlayedScenario, creature) -> tuple[int | None, int | None]:
    """The computed power and toughness (CR 613.4c), not the printed ones."""
    state = scenario.game.computed_board().of(creature)
    return state.power, state.toughness


def test_landfall_doubles_the_power_of_the_targeted_creature():
    """The happy path: a Forest enters, the trigger resolves, and a 2/2 that
    alice controls becomes a 4/2 (CR 701.10b)."""
    scenario = board(
        alice_battlefield=[HARMONIZER, "Grizzly Bears"],
        alice_hand=["Forest"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets(HARMONIZER, [bears])
    scenario.play_land("Forest")

    assert scenario.stack_names() == [f"{HARMONIZER}'s triggered ability"]

    scenario.resolve_top()

    assert power_toughness(scenario, bears) == (4, 2)


def test_toughness_is_untouched():
    """CR 701.10a's effect modifies only what the clause names. Grizzly Bears'
    toughness is 2 before and 2 after, and the creature is nowhere near
    dying of it (CR 704.5g never fires)."""
    scenario = board(
        alice_battlefield=[HARMONIZER, "Grizzly Bears"],
        alice_hand=["Forest"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bears = scenario.creature("Grizzly Bears", "alice")
    assert power_toughness(scenario, bears) == (2, 2)

    scenario.choose_trigger_targets(HARMONIZER, [bears])
    scenario.play_land("Forest")
    scenario.resolve_top()

    assert power_toughness(scenario, bears)[1] == 2
    assert bears.zone is Zone.BATTLEFIELD


def test_a_later_pump_is_not_doubled_too():
    """CR 701.10b fixes X "as the spell or ability that doubles its power
    resolves". The doubling is already a flat +2/+0 by the time Giant Growth
    resolves, so the board reads 2 + 2 + 3 = 7 power, not a re-doubled 10."""
    scenario = board(
        alice_battlefield=[HARMONIZER, "Grizzly Bears", "Forest"],
        alice_hand=["Forest", "Giant Growth"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets(HARMONIZER, [bears])
    scenario.play_land("Forest")
    scenario.resolve_top()
    assert power_toughness(scenario, bears) == (4, 2)

    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_and_resolve("Giant Growth", forest, targets=[bears])

    assert power_toughness(scenario, bears) == (7, 5)


def test_doubling_twice_in_one_turn_reads_the_doubled_value_the_second_time():
    """Two landfall triggers in one turn, off two real land drops (Azusa,
    Lost but Seeking). CR 701.10b reads X at each resolution: a 2/2 gets
    +2/+0, then +4/+0 off the now-4 power, and ends the turn an 8/2."""
    scenario = board(
        alice_battlefield=[HARMONIZER, "Grizzly Bears", "Azusa, Lost but Seeking"],
        alice_hand=["Forest", "Forest"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.choose_trigger_targets(HARMONIZER, [bears])
    scenario.play_land("Forest")
    scenario.resolve_top()
    assert power_toughness(scenario, bears) == (4, 2)

    scenario.choose_trigger_targets(HARMONIZER, [bears])
    scenario.play_land("Forest")
    scenario.resolve_top()

    assert power_toughness(scenario, bears) == (8, 2)


def test_the_doubling_ends_in_the_cleanup_step():
    """CR 514.2 / CR 703.4p: all "until end of turn" effects end in the
    cleanup step. The 8/2 survives every step up to cleanup and is a 2/2
    again once the cleanup step's turn-based actions run."""
    scenario = board(
        alice_battlefield=[HARMONIZER, "Grizzly Bears", "Azusa, Lost but Seeking"],
        alice_hand=["Forest", "Forest"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets(HARMONIZER, [bears])
    scenario.play_land("Forest")
    scenario.resolve_top()
    scenario.choose_trigger_targets(HARMONIZER, [bears])
    scenario.play_land("Forest")
    scenario.resolve_top()

    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    assert power_toughness(scenario, bears) == (8, 2)

    scenario.turn_based_actions()

    assert power_toughness(scenario, bears) == (2, 2)


def test_an_opponents_creature_is_refused_at_announcement():
    """ "Target creature you control" is checked when the trigger's targets are
    announced (CR 603.3d sends them through CR 601.2c), so bob's Grizzly
    Bears is refused before the land is ever played."""
    scenario = board(
        alice_battlefield=[HARMONIZER, "Grizzly Bears"],
        alice_hand=["Forest"],
        bob_battlefield=["Grizzly Bears"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bobs_bears = scenario.creature("Grizzly Bears", "bob")

    with pytest.raises(ValueError, match="illegal target"):
        scenario.choose_trigger_targets(HARMONIZER, [bobs_bears])


def test_a_target_that_has_left_the_battlefield_does_nothing():
    """CR 608.2b: "A target that's no longer in the zone it was in when it was
    targeted is illegal." Bolting the target in response leaves the trigger
    with nothing to do - and notably it does not fall back onto some other
    creature alice controls."""
    scenario = board(
        alice_battlefield=[HARMONIZER, "Grizzly Bears", "Mountain"],
        alice_hand=["Forest", "Lightning Bolt"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bears = scenario.creature("Grizzly Bears", "alice")
    harmonizer = scenario.creature(HARMONIZER, "alice")
    scenario.choose_trigger_targets(HARMONIZER, [bears])
    scenario.play_land("Forest")
    assert scenario.stack_names() == [f"{HARMONIZER}'s triggered ability"]

    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[bears])
    assert bears.zone is Zone.GRAVEYARD

    scenario.resolve_top()

    assert scenario.stack_names() == []
    assert power_toughness(scenario, harmonizer) == (4, 4)


def test_a_creature_with_power_zero_stays_at_zero():
    """CR 701.10b's X is the creature's power, and twice nothing is nothing.
    Birds of Paradise is a 0/1 before and a 0/1 after - and CR 701.10c's
    negative-power branch is never reached, because 0 is not less than 0."""
    scenario = board(
        alice_battlefield=[HARMONIZER, "Birds of Paradise"],
        alice_hand=["Forest"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    birds = scenario.creature("Birds of Paradise", "alice")
    scenario.choose_trigger_targets(HARMONIZER, [birds])
    scenario.play_land("Forest")
    scenario.resolve_top()

    assert power_toughness(scenario, birds) == (0, 1)
    assert birds.zone is Zone.BATTLEFIELD
