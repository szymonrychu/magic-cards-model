"""Captain Howler, Sea Scourge's discard trigger (CR 701.9a, CR 603.7).

"Whenever you discard one or more cards, target creature gets +2/+0 until
end of turn for each card discarded this way. Whenever that creature deals
combat damage to a player this turn, you draw a card."

The DDR#886 half of this mechanic (the trigger event itself, and Mind Rot
triggering it once for two cards) is `tests/scenarios/judge/
test_judge_triggers.py`'s business. This file is about what the *resolved*
ability does: the magnitude scales with how many cards were actually
discarded, and the second sentence is a CR 603.7 delayed trigger that
watches only *this turn*'s combat damage from the pumped creature.

Mind Rot targets alice herself here: CR 109.5's "you"/"your" on an object's
text refers to that object's controller, so Captain Howler's own "whenever
you discard" watches its controller's own discards - see the note in
`test_judge_triggers.py::test_mind_rot_causes_captain_howlers_discard_trigger_to_fire_once`.

CR numbers looked up with `knowledge_search(type="rules")` in this session:
CR 701.9a, CR 603.7, CR 603.7b, CR 120.2a, CR 121.1, CR 109.5.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Mind Rot", "Lava Dart", "Forest"],
            battlefield=["Captain Howler, Sea Scourge", "Grizzly Bears", "Swamp", "Swamp", "Swamp"],
            library=["Island"] * 5,
        )
        .player("bob")
    )


def resolve_all(scenario: Scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def test_discarding_two_cards_pumps_by_plus_four():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")

    scenario.choose_trigger_targets("Captain Howler, Sea Scourge", [bears])
    scenario.cast_and_resolve("Mind Rot", *sources, targets=["alice"])
    resolve_all(scenario)

    assert scenario.player("alice").hand == []
    board_state = scenario.game.computed_board().of(bears)
    assert (board_state.power, board_state.toughness) == (6, 2)


def test_combat_damage_from_the_pumped_creature_draws_a_card():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")

    scenario.choose_trigger_targets("Captain Howler, Sea Scourge", [bears])
    scenario.cast_and_resolve("Mind Rot", *sources, targets=["alice"])
    resolve_all(scenario)
    hand_before = len(scenario.player("alice").hand)

    scenario.attack_with(bears)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    resolve_all(scenario)

    assert len(scenario.player("alice").hand) == hand_before + 1


def test_the_pump_and_the_delayed_draw_both_end_with_the_turn():
    """CR 514.2 ends every "until end of turn"/"this turn" effect in the
    cleanup step - the pump and the delayed draw-on-damage trigger both stop
    existing once alice's turn is over, so bob's next attack with the same
    creature (now under his control, hypothetically) gets nothing from a
    trigger that should have expired. This scenario checks the simpler half:
    the delayed trigger is gone from `Game`'s bookkeeping after cleanup.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")

    scenario.choose_trigger_targets("Captain Howler, Sea Scourge", [bears])
    scenario.cast_and_resolve("Mind Rot", *sources, targets=["alice"])
    resolve_all(scenario)
    assert scenario.game.delayed_triggers.triggers != []

    scenario.game.cleanup_step()  # CR 514.2's own expiry, run directly

    assert scenario.game.delayed_triggers.triggers == []
    assert (bears.power, bears.toughness) == (2, 2)
