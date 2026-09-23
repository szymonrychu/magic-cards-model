"""CR 724.1c-f: the cleanup step an "end the turn" effect owes, and CR 514.3a's
"another cleanup step" once something happens during it.

`tests/scenarios/judge/test_judge_ending_the_turn.py` covers CR 724.1a/b/d's
stack-exiling procedure and DDR#957's judge ruling on top of it. This file
covers what that procedure leaves *owed*: the cleanup step's own CR 514.1
(discard) and CR 514.2 (damage/"until end of turn" wipe) turn-based actions,
which `Game.end_the_turn` defers rather than skips (`Game.cleanup_owed`), and
CR 724.1c/f's own state-based-action check and trigger-stacking, paid off by
`Game._before_priority` once CR 608.2m lets the resolving spell or ability
finish.

Every CR number here was looked up with `mise run rules:find <n>` in the
session that wrote this file: CR 514.1, 514.2, 514.3, 514.3a, 608.2m, 704.3,
724.1a-f.

CR 514.3a, quoted in full, is the rule `Game._before_priority`'s own
recursion implements: "At this point, the game checks to see if any
state-based actions would be performed and/or any triggered abilities are
waiting to be put onto the stack (including those that trigger 'at the
beginning of the next cleanup step'). If so, those state-based actions are
performed, then those triggered abilities are put on the stack, then the
active player gets priority. Players may cast spells and activate abilities.
Once the stack is empty and all players pass in succession, another cleanup
step begins."

CR 724.1, quoted in full for c/d/e/f:

- **CR 724.1c** - "Check state-based actions. No player gets priority, and no
  triggered abilities are put onto the stack."
- **CR 724.1d** - "The current phase and/or step ends. If this happens during
  combat, remove all creatures and planeswalkers from combat. The game skips
  straight to the cleanup step; skip any phases or steps between this phase or
  step and the cleanup step. If an effect ends the turn during the cleanup
  step, a new cleanup step begins."
- **CR 724.1e** - "Even though the turn ends, 'at the beginning of the end
  step' triggered abilities don't trigger because the end step is skipped."
- **CR 724.1f** - "No player gets priority during this process, so triggered
  abilities are not put onto the stack. If any triggered abilities have
  triggered since this process began, those abilities are put onto the stack
  during the cleanup step, then the active player gets priority and players
  can cast spells and activate abilities. Then there will be another cleanup
  step before the turn finally ends. If no triggered abilities have triggered
  during this process, no player gets priority during the cleanup step."
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import end_the_turn_if_your_turn_effect
from magic_cards_model.models import Game, Zone
from tests.scenarios.harness import Scenario

# -- (a): the probe - the owed cleanup actually runs -------------------------


def test_the_owed_cleanup_wipes_damage_and_the_pump_before_the_next_turn():
    """The probe: Giant Growth on a Grizzly Bears with 1 damage marked, then
    Time Stop. Before this wave, the game sat in `Step.CLEANUP` forever with
    the damage and the pump both still there - `end_the_turn` dropped the
    pointer into cleanup but never ran its CR 514.1/514.2 turn-based actions.
    Now `Game._before_priority`, reached as Time Stop's own resolution
    finishes, pays that debt: by the time the next turn could begin, CR 514.2
    has already removed the damage and let the "until end of turn" pump
    expire (CR 512.2's own reading of "until end of turn" duration).
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Giant Growth", "Time Stop"],
            battlefield=["Grizzly Bears", "Forest"] + ["Island"] * 6,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.mark_damage(1)
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_and_resolve("Giant Growth", forest, username="alice", targets=[bears])

    assert bears.power == 5 and bears.toughness == 5, "Giant Growth resolved: +3/+3"
    assert bears.damage == 1

    scenario.cast_and_resolve(
        "Time Stop", *scenario.untapped_sources(*["Island"] * 6, username="alice"), username="alice"
    )

    assert scenario.step is Step.CLEANUP
    assert scenario.game.cleanup_owed is False, "the debt was paid, not left outstanding"
    assert bears.damage == 0, "CR 514.2's wipe has already run"
    assert bears.power == 2 and bears.toughness == 2, (
        "Giant Growth's until-end-of-turn pump has already expired"
    )


# -- (b): CR 514.1 - the discard actually runs --------------------------------


def test_the_owed_cleanup_discards_the_active_player_to_maximum_hand_size():
    """CR 514.1: the active player discards down to seven. Time Stop itself
    is cast from the nine-card hand, so alice holds eight as it resolves -
    still over the limit, and the owed cleanup's own discard is what brings
    her back to seven, not anything CR 724.1 itself performs.
    """
    filler = ["Mountain"] * 8
    scenario = (
        Scenario()
        .player("alice", hand=["Time Stop", *filler], battlefield=["Island"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert len(scenario.player("alice").hand) == 9

    scenario.cast_and_resolve(
        "Time Stop", *scenario.untapped_sources(*["Island"] * 6, username="alice"), username="alice"
    )

    assert scenario.step is Step.CLEANUP
    assert len(scenario.player("alice").hand) == 7, "CR 514.1's discard ran in the owed cleanup"


# -- (c): CR 724.1c - state-based actions checked with no priority -----------


def test_724_1c_checks_state_based_actions_with_no_priority_and_no_stacked_trigger():
    """CR 724.1c, driven directly the way the judge file's own CR 724.1
    tests are: a creature already dealt lethal damage, with nothing having
    checked state-based actions since, dies from `end_the_turn`'s own check -
    and its "dies" trigger is left waiting, not put on the stack, matching
    "No player gets priority, and no triggered abilities are put onto the
    stack."
    """
    scenario = Scenario().player("alice", battlefield=["Kitchen Finks"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    finks = scenario.creature("Kitchen Finks", "alice")
    finks.mark_damage(2)  # lethal on a 2-toughness Finks - nothing has checked yet

    scenario.game.end_the_turn()

    assert finks.zone is Zone.GRAVEYARD, "CR 724.1c's own state-based check killed it"
    assert scenario.game.pending_triggers, "Persist triggered"
    assert scenario.game.stack == [], "CR 724.1c: not put onto the stack"
    assert scenario.step is Step.CLEANUP
    assert scenario.game.priority is None or scenario.game.priority.holder is None


# -- (d): CR 724.1e - the end step's own trigger never fires -----------------


def test_724_1e_the_end_step_trigger_never_fires():
    """CR 724.1e: ending the turn from the postcombat main phase skips the
    end step entirely, so Throne of the God-Pharaoh's "at the beginning of
    your end step" never has a moment to trigger - contrast with an ordinary
    turn, where the same board reliably stacks it (see the sanity check
    inline below, via a fresh scenario, before the real one runs).
    """

    def board() -> Scenario:
        return (
            Scenario()
            .player(
                "alice",
                hand=["Time Stop"],
                battlefield=["Throne of the God-Pharaoh", "Grizzly Bears"] + ["Island"] * 6,
            )
            .player("bob")
            .build()
        )

    # Sanity: the same board, reaching the end step normally, does trigger it.
    control = board()
    control.start_at(Step.POSTCOMBAT_MAIN)
    control.creature("Grizzly Bears", "alice").tapped = True
    control.pass_priority("alice")
    control.pass_priority("bob")
    assert control.step is Step.END_STEP
    assert control.stack_names() == ["Throne of the God-Pharaoh's triggered ability"]

    scenario = board()
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.creature("Grizzly Bears", "alice").tapped = True

    scenario.cast_and_resolve(
        "Time Stop", *scenario.untapped_sources(*["Island"] * 6, username="alice"), username="alice"
    )

    assert scenario.step is Step.CLEANUP, "the end step was skipped, not merely passed through"
    assert scenario.game.pending_triggers == []
    assert scenario.game.stack == []
    assert scenario.player("bob").life == 20, "Throne's end-step trigger never triggered"


# -- (e)/(f): CR 724.1f/514.3a - the stacked process trigger, then another
# cleanup step ----------------------------------------------------------------


def _time_stop_catching_a_lethal_kitchen_finks(scenario: "Scenario"):
    """Cast Time Stop, then mark Kitchen Finks lethal *after* it is on the
    stack (so `retain_priority`'s own CR 704.3 check has already passed with
    it healthy), then resolve - CR 724.1c's own check is the first thing to
    find it dead, exactly like the standalone test above, but this time as
    part of a genuinely resolving spell whose own owed cleanup follows."""
    finks = scenario.creature("Kitchen Finks", "alice")
    casting = scenario.cast("Time Stop", "alice")
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    scenario.put_on_stack(casting)
    assert finks.zone is Zone.BATTLEFIELD, "no state-based check has run since the mark below"
    finks.mark_damage(2)
    scenario.resolve_top()
    return finks


def test_724_1f_stacks_the_process_trigger_then_grants_the_active_player_priority():
    """CR 724.1f's first half: Persist triggered during the process (CR
    724.1c's own check, inside the owed cleanup this time rather than a
    direct `end_the_turn` call), goes onto the stack *during the cleanup
    step*, and the active player - not merely whoever last acted - gets
    priority. alice is both here, so this test alone would not distinguish
    them; the companion test below puts them on different players.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Time Stop"], battlefield=["Kitchen Finks"] + ["Island"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _time_stop_catching_a_lethal_kitchen_finks(scenario)

    assert scenario.step is Step.CLEANUP
    assert scenario.game.cleanup_owed is False, "the first owed cleanup already ran"
    assert scenario.stack_names() == ["Kitchen Finks's triggered ability"]
    assert scenario.game.priority_holder == "alice"


def test_724_1f_grants_priority_to_the_active_player_not_whoever_last_acted():
    """The same shape, with bob as the active player and alice - who casts
    Time Stop as an instant during bob's turn and would keep priority under
    the ordinary CR 117.3c rule - controlling Kitchen Finks. CR 514.3a is
    explicit that it is "the active player" who gets priority once something
    is stacked, which is bob here, not alice.
    """
    scenario = (
        Scenario()
        .player("bob", battlefield=["Island"])
        .player("alice", hand=["Time Stop"], battlefield=["Kitchen Finks"] + ["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.turn.active_player == "bob"
    scenario.pass_priority("bob")  # bob passes; alice, non-active, now holds priority

    finks = scenario.creature("Kitchen Finks", "alice")
    casting = scenario.cast("Time Stop", "alice")
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    scenario.put_on_stack(casting)
    finks.mark_damage(2)  # staged after CR 704.3's own check, same as the helper above
    scenario.resolve_top()

    assert scenario.step is Step.CLEANUP
    assert scenario.stack_names() == ["Kitchen Finks's triggered ability"]
    assert scenario.game.priority_holder == "bob", (
        "CR 514.3a: the active player, not alice who cast Time Stop"
    )


def test_724_1f_then_724_1d_another_cleanup_step_runs_before_the_turn_ends():
    """CR 724.1f's second half and CR 514.3a's own closing sentence: once
    Persist resolves, its own "when this creature enters" trigger (Kitchen
    Finks has both) is what keeps the round alive for one more object - and
    once *that* resolves too with nothing left pending, `_before_priority`'s
    own recursion pays off "another cleanup step" (CR 514.3a's exact words)
    by running `cleanup_step` a second time, rather than the game silently
    rolling into the next turn with a second, never-run cleanup owed.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Time Stop"], battlefield=["Kitchen Finks"] + ["Island"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice_life_before = scenario.player("alice").life
    _time_stop_catching_a_lethal_kitchen_finks(scenario)

    scenario.pass_until_resolved()  # Persist resolves: Finks returns with a -1/-1 counter
    assert scenario.stack_names() == ["Kitchen Finks's triggered ability"], (
        "the ETB gain-life trigger, off Persist's own return"
    )
    new_finks = scenario.find("Kitchen Finks", Zone.BATTLEFIELD, "alice")
    assert new_finks.counters["-1/-1"] == 1

    scenario.pass_until_resolved()  # the gain-life trigger resolves

    assert scenario.player("alice").life == alice_life_before + 2
    assert scenario.game.stack == []
    assert scenario.game.pending_triggers == []
    assert scenario.step is Step.CLEANUP, "still resting in the (now closed) reopened cleanup"
    assert scenario.game.priority is None or scenario.game.priority.holder is None, (
        "CR 514.3a: nothing left pending, so this cleanup step grants no more priority"
    )
    assert scenario.game.cleanup_owed is False


def test_724_1d_ending_the_turn_again_during_a_reopened_cleanup_begins_a_new_one():
    """CR 724.1d's second sentence: "If an effect ends the turn during the
    cleanup step, a new cleanup step begins." A second Time Stop, cast while
    Persist's ability still sits on the reopened cleanup step's stack (CR
    724.1c's earlier trigger), exiles that ability under CR 724.1b before it
    ever resolves - so Kitchen Finks never returns - and CR 724.1d's own
    "a new cleanup step begins" is `cleanup_owed` set once again and paid off
    by the same `_before_priority` machinery.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Time Stop", "Time Stop"],
            battlefield=["Kitchen Finks"] + ["Island"] * 12,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _time_stop_catching_a_lethal_kitchen_finks(scenario)

    assert scenario.stack_names() == ["Kitchen Finks's triggered ability"]
    assert scenario.step is Step.CLEANUP

    scenario.cast_and_resolve(
        "Time Stop", *scenario.untapped_sources(*["Island"] * 6, username="alice"), username="alice"
    )

    assert scenario.step is Step.CLEANUP, "a new cleanup step - the pointer never had to move"
    assert scenario.game.stack == [], (
        "CR 724.1b exiled Persist's own ability too - it never resolved"
    )
    assert scenario.game.pending_triggers == []
    assert scenario.game.cleanup_owed is False
    assert [state.name for state in scenario.player("alice").graveyard].count(
        "Kitchen Finks"
    ) == 1, "Persist never got to return it - its ability ceased to exist under CR 724.1b"


# -- (g): the ability path - Sundial of the Infinite --------------------------


def test_sundial_of_the_infinites_activated_ability_ends_the_turn_the_same_way():
    """Sundial of the Infinite: "{1}, {T}: End the turn." Read no differently
    from Time Stop's own sentence: `_PLAIN_END_THE_TURN_RE` lives in
    `_parse_targeted_clause`, already tried by `activated_effect_for`'s
    fallback for any activated ability with no `ACTIVATED_EFFECTS` row (see
    `machines/effects.py`'s `parse_mixed_effect`), and `end_the_turn_effect`
    itself never reads its second argument - so no row or extension was
    needed for the ability path; this is the regression test that keeps it
    that way. Its own "Activate only during your turn." is a separate CR
    602.5 timing restriction, stripped from the effect text before dispatch
    (`ActivatedAbility.instructions`), not part of what this test drives.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Sundial of the Infinite", "Grizzly Bears"] + ["Island"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.mark_damage(1)
    sundial = scenario.find("Sundial of the Infinite", Zone.BATTLEFIELD, "alice")

    scenario.activate(sundial, *scenario.untapped_sources("Island", username="alice"), auto=True)
    scenario.pass_until_resolved()

    assert scenario.step is Step.CLEANUP
    assert scenario.game.cleanup_owed is False
    assert bears.damage == 0, "the owed cleanup ran off the ability path too"


# -- (h): the second printing - Day's Undoing's conditional form -------------


def test_days_undoing_ends_the_turn_only_on_the_casters_own_turn():
    """Day's Undoing: "Each player shuffles their hand and graveyard into
    their library, then draws seven cards. If it's your turn, end the turn."
    - CR 608.2c's second instruction is a plain conditional, gated on CR
    102.1's active player being this resolving spell's own controller.

    Cast on alice's own turn (sorcery timing already requires this in the
    ordinary case, so this is the only branch a real cast can reach): both
    sentences run, and the second one ends the turn.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"] * 7,
            hand=["Day's Undoing", "Lightning Bolt", "Lightning Bolt", "Lightning Bolt"],
            battlefield=["Island"] * 3,
        )
        .player("bob", library=["Mountain"] * 7)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve(
        "Day's Undoing",
        *scenario.untapped_sources(*["Island"] * 3, username="alice"),
        username="alice",
    )

    assert len(scenario.player("alice").hand) == 7, "the first sentence still ran"
    assert scenario.step is Step.CLEANUP, "the second sentence ended the turn"
    assert scenario.game.cleanup_owed is False


def test_end_the_turn_if_your_turn_effect_does_nothing_on_someone_elses_turn():
    """The gate itself, driven directly the way this file's other CR 724.1
    tests are (`Scenario.start_at`, no full cast): a resolving object whose
    controller is not the active player leaves the turn alone entirely - the
    branch a real cast of a sorcery can never reach (sorcery timing already
    requires the caster's own turn), but the one CR 118's "if it's your turn"
    plainly reads for, and the reason this is not a bare CR 608.2a intervening
    *if*.
    """
    scenario = Scenario().player("alice", hand=["Day's Undoing"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.turn.active_player == "alice"
    undoing = scenario.find("Day's Undoing", Zone.HAND, "alice")
    undoing.controller = "bob"  # staged: alice's card, bob's hypothetical control of it

    end_the_turn_if_your_turn_effect(scenario.game, undoing)

    assert scenario.step is Step.PRECOMBAT_MAIN, "not bob's turn, so nothing ended it"
    assert scenario.game.cleanup_owed is False


# -- (j): a paused game with the debt still owed round-trips -----------------


def test_a_paused_game_with_the_cleanup_owed_round_trips():
    """`Game.cleanup_owed` is a plain persisted field, not transient
    bookkeeping: a game snapshotted between `end_the_turn` setting it and the
    resolution that set it finishing (a real `DecisionPending` pause could
    land exactly here) must decode back with the debt intact, or a resumed
    game would silently skip the cleanup step it owes.
    """
    scenario = Scenario().player("alice", battlefield=["Grizzly Bears"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.end_the_turn()

    assert scenario.game.cleanup_owed is True
    assert scenario.step is Step.CLEANUP

    decoded = Game.model_validate(scenario.game.model_dump())

    assert decoded.cleanup_owed is True
    assert decoded.turn is not None and decoded.turn.step is Step.CLEANUP
