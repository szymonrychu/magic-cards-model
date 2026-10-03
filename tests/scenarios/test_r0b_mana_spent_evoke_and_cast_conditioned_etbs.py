"""R0b-T8 proofs: Emptiness (evoke + two mana-spent intervening ifs) and
Yathan Roadwatcher (an enters trigger gated on "if you cast it", with a
reflexive "when you do").

- CR 702.74a: evoke is an alternative cost plus an enters trigger that
  sacrifices the permanent when its evoke cost was paid.
- CR 601.2h: the mana spent to cast a spell is what the intervening if reads.
- CR 603.4: an intervening if is checked when the trigger event occurs.
- CR 603.12: a reflexive trigger ("When you do") follows the action it names.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def settle(scenario) -> None:
    """Put every waiting trigger on the stack and resolve the lot (CR 603.3)."""
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


# --------------------------------------------------------------------------
# Emptiness
# --------------------------------------------------------------------------


def _emptiness_board(*lands: str) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Emptiness"],
            battlefield=list(lands),
            graveyard=["Grizzly Bears", "Serra Angel"],
            library=["Forest"] * 5,
        )
        .player("bob", battlefield=["Serra Angel"], library=["Forest"] * 5)
        .build()
    )


def test_ww_spent_reanimates_a_small_creature_card_and_nothing_else():
    scenario = _emptiness_board("Mountain", "Mountain", "Mountain", "Mountain", "Plains", "Plains")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")
    scenario.choose_trigger_targets("Emptiness", [bears])

    emptiness = scenario.cast_and_resolve(
        "Emptiness",
        *scenario.untapped_sources(
            "Mountain", "Mountain", "Mountain", "Mountain", "Plains", "Plains"
        ),
    )
    record = scenario.game.cast_record(emptiness)
    assert record.mana_of_color_spent(Color.WHITE) == 2
    assert record.mana_of_color_spent(Color.BLACK) == 0
    settle(scenario)

    assert emptiness.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.BATTLEFIELD
    assert angel.counter_count(Counter.MINUS_ONE) == 0
    assert scenario.game.intervening_if_notices == []


def test_the_reanimation_cannot_aim_at_a_creature_card_above_mana_value_three():
    scenario = _emptiness_board("Mountain", "Mountain", "Mountain", "Mountain", "Plains", "Plains")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")
    scenario.cast_and_resolve(
        "Emptiness",
        *scenario.untapped_sources(
            "Mountain", "Mountain", "Mountain", "Mountain", "Plains", "Plains"
        ),
    )
    with pytest.raises(ValueError, match="mana value 3 or less"):
        scenario.choose_trigger_targets("Emptiness", [angel])
    assert angel.zone is Zone.GRAVEYARD


def test_bb_spent_puts_three_minus_one_counters_on_a_creature_and_does_not_reanimate():
    scenario = _emptiness_board("Mountain", "Mountain", "Mountain", "Mountain", "Swamp", "Swamp")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")
    scenario.choose_trigger_targets("Emptiness", [angel])

    emptiness = scenario.cast_and_resolve(
        "Emptiness",
        *scenario.untapped_sources(
            "Mountain", "Mountain", "Mountain", "Mountain", "Swamp", "Swamp"
        ),
    )
    settle(scenario)

    assert emptiness.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.GRAVEYARD
    assert angel.counter_count(Counter.MINUS_ONE) == 3
    assert scenario.game.characteristics_of(angel).power == 1


def test_one_of_each_colour_triggers_neither_ability():
    scenario = _emptiness_board("Mountain", "Mountain", "Mountain", "Mountain", "Plains", "Swamp")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")

    emptiness = scenario.cast_and_resolve(
        "Emptiness",
        *scenario.untapped_sources(
            "Mountain", "Mountain", "Mountain", "Mountain", "Plains", "Swamp"
        ),
    )
    assert scenario.game.pending_triggers == []
    settle(scenario)

    assert emptiness.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.GRAVEYARD
    assert angel.counter_count(Counter.MINUS_ONE) == 0


def test_both_abilities_fire_when_ww_and_bb_were_both_spent():
    scenario = _emptiness_board("Mountain", "Mountain", "Plains", "Plains", "Swamp", "Swamp")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")
    scenario.will_choose_targets(bears, username="alice", source="Emptiness")
    scenario.will_choose_targets(angel, username="alice", source="Emptiness")

    emptiness = scenario.cast_and_resolve(
        "Emptiness",
        *scenario.untapped_sources("Mountain", "Mountain", "Plains", "Plains", "Swamp", "Swamp"),
    )
    record = scenario.game.cast_record(emptiness)
    assert record.mana_of_color_spent(Color.WHITE) == 2
    assert record.mana_of_color_spent(Color.BLACK) == 2
    settle(scenario)

    assert bears.zone is Zone.BATTLEFIELD
    assert angel.counter_count(Counter.MINUS_ONE) == 3


def test_evoking_for_ww_reanimates_then_sacrifices_itself():
    scenario = _emptiness_board("Plains", "Plains")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.choose_trigger_targets("Emptiness", [bears])

    casting = scenario.cast("Emptiness")
    casting.use_keyword("Evoke")
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Plains", "Plains"))
    scenario.put_on_stack(casting)
    emptiness = scenario.resolve_top()
    record = scenario.game.cast_record(emptiness)
    assert record.keyword == "Evoke"
    assert record.mana_of_color_spent(Color.WHITE) == 2
    settle(scenario)

    assert emptiness.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD


def test_evoking_for_bb_shrinks_a_creature_then_sacrifices_itself():
    scenario = _emptiness_board("Swamp", "Swamp")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")
    scenario.choose_trigger_targets("Emptiness", [angel])

    casting = scenario.cast("Emptiness")
    casting.use_keyword("Evoke")
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Swamp", "Swamp"))
    scenario.put_on_stack(casting)
    emptiness = scenario.resolve_top()
    settle(scenario)

    assert emptiness.zone is Zone.GRAVEYARD
    assert angel.counter_count(Counter.MINUS_ONE) == 3


def test_evoking_with_one_of_each_colour_only_sacrifices():
    scenario = _emptiness_board("Plains", "Swamp")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")

    casting = scenario.cast("Emptiness")
    casting.use_keyword("Evoke")
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Plains", "Swamp"))
    scenario.put_on_stack(casting)
    emptiness = scenario.resolve_top()
    settle(scenario)

    assert emptiness.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD
    assert angel.counter_count(Counter.MINUS_ONE) == 0


def test_emptiness_put_onto_the_battlefield_without_casting_triggers_nothing():
    scenario = _emptiness_board("Plains")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    emptiness = scenario.put_onto_battlefield("Emptiness")
    settle(scenario)

    assert emptiness.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# Yathan Roadwatcher
# --------------------------------------------------------------------------


def _yathan_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Yathan Roadwatcher", "Ephemerate", "Plains"],
            battlefield=["Plains", "Swamp", "Forest", "Mountain"],
            graveyard=["Serra Angel"],
            library=["Grizzly Bears", "Forest", "Forest", "Forest", "Island"],
        )
        .player("bob")
        .build()
    )


def test_a_cast_yathan_mills_four_then_reanimates_a_milled_small_creature():
    scenario = _yathan_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")
    scenario.will_choose_targets(bears, username="alice", source="Yathan Roadwatcher")

    yathan = scenario.cast_and_resolve(
        "Yathan Roadwatcher", *scenario.untapped_sources("Plains", "Swamp", "Forest", "Mountain")
    )
    settle(scenario)

    assert yathan.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.BATTLEFIELD
    assert angel.zone is Zone.GRAVEYARD
    assert len(alice.library) == 1
    assert len([c for c in alice.graveyard]) == 4  # Angel + three Forests


def test_yathan_that_was_not_cast_does_not_mill_or_reanimate():
    scenario = _yathan_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")

    yathan = scenario.put_onto_battlefield("Yathan Roadwatcher")
    settle(scenario)

    assert yathan.zone is Zone.BATTLEFIELD
    assert len(alice.library) == 5
    assert [c.name for c in alice.graveyard] == ["Serra Angel"]


def test_a_flickered_yathan_does_not_trigger_again():
    """It re-enters without having been cast, so "if you cast it" is false."""
    scenario = _yathan_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")
    scenario.will_choose_targets(bears, username="alice", source="Yathan Roadwatcher")
    yathan = scenario.cast_and_resolve(
        "Yathan Roadwatcher", *scenario.untapped_sources("Plains", "Swamp", "Forest", "Mountain")
    )
    settle(scenario)
    library_after_cast = len(alice.library)

    plains = scenario.put_onto_battlefield("Plains")
    scenario.cast_and_resolve("Ephemerate", plains, targets=[yathan])
    settle(scenario)

    assert yathan.zone is Zone.BATTLEFIELD
    assert len(alice.library) == library_after_cast
