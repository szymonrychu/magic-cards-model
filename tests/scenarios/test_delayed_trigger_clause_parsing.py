"""Scenario: delayed-trigger clauses read off a card's own printed text
(CR 603.7), with no per-card table row.

The live defect this fixes: Phelia, Exuberant Shepherd's attack trigger -
"exile up to one other target nonland permanent. At the beginning of the next
end step, return that card to the battlefield under its owner's control. If it
entered under your control, put a +1/+1 counter on Phelia." - used to exile a
legally-targeted permanent and never bring it back. Clause one
("exile ... permanent") is `_EXILE_TARGET_RE`'s ordinary shape and always
parsed; clauses two and three had no reader at all, so `_parse_mixed_clauses`
correctly refused the *whole* ability (CR 608.2c has no notion of running half
an instruction) - but silently, with `changed: false` and nothing anywhere
recording why.

Every rule cited below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file, except the two the tool's
excerpt truncates before the deciding clause - CR 603.7c's parenthetical and
CR 513.2's "Likewise, if" continuation - which were read out of a local CR
text dated 2026-02-27, one revision behind the CR this repo otherwise cites.

- **CR 603.7** / **603.7a** / **603.7b** - a delayed trigger is created *as the
  resolving ability runs*, not when it goes on the stack, and fires once.
- **CR 603.7c** - "if that object is no longer in the zone it's expected to be
  in ... the ability won't affect it. (Note that if that object left that zone
  and then returned, it's a new object and thus won't be affected. See rule
  400.7.)" - the identity check `CardState.zone_change_stamp` and
  `DelayedTrigger.expected_stamp` exist for.
- **CR 110.5b** - permanents enter the battlefield untapped by default.
- **CR 122.2** - counters do not survive a zone change; **CR 403.4** - the
  returned permanent is a new object, summoning sick again.
- **CR 111.7** / **704.5d** / **111.8** - a token exiled this way ceases to
  exist and can never return.
- **CR 511.2** - "at end of combat" triggers as the end of combat step begins,
  the same `BEGINNING_OF_STEP` event every other "at the beginning of ..."
  trigger uses.
- **CR 513.2** - a delayed trigger created *during* a step waits for the
  *next* occurrence of that step; the step does not "back up".
- **CR 113.7** / **603.7d** / **603.7e** - the source and controller are fixed
  at creation, so the creating permanent dying does not stop the delayed
  return; it only makes a rider that reads the source's current state (Phelia's
  own +1/+1 counter) do nothing.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import effect_for
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import TokenDefinition, create_tokens
from tests.cards import card_state
from tests.scenarios.harness import Scenario


def walk_to(scenario, step: Step) -> None:
    """Advance turn-by-turn - never jump - until `step`, resolving anything
    that fires along the way.

    CR 500.6's "a step began" event is emitted by `Game.advance`, not by
    `start_at`, which moves the turn machine directly and fires nothing - so a
    delayed trigger waiting for a step can only be proven by walking there.
    """
    while scenario.step is not step:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


# --------------------------------------------------------------------------
# Phelia, Exuberant Shepherd: "exile ... . At the beginning of the next end
# step, return that card to the battlefield under its owner's control. If it
# entered under your control, put a +1/+1 counter on Phelia."
# --------------------------------------------------------------------------


def _phelia_board() -> Scenario:
    return (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Phelia, Exuberant Shepherd"])
        .player("bob", library=["Island"], battlefield=["Watchwolf", "Island"])
    )


def test_phelia_exiles_and_returns_an_opponents_permanent_untapped_under_its_owner():
    """The happy path this defect was blocking: a legal target actually
    leaves and actually comes back, untapped (CR 110.5b), under Bob's control
    (CR 610.3c) - not Alice's, so Phelia gets no counter (the third sentence's
    own condition is false)."""
    scenario = _phelia_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    phelia = scenario.creature("Phelia, Exuberant Shepherd", "alice")
    watchwolf = scenario.creature("Watchwolf", "bob")
    watchwolf.tap()  # exiled tapped; CR 110.5b returns it untapped anyway

    scenario.choose_trigger_targets("Phelia, Exuberant Shepherd", [watchwolf])
    scenario.attack_with(phelia)
    assert scenario.stack_names() == ["Phelia, Exuberant Shepherd's triggered ability"]
    scenario.pass_until_resolved()

    assert watchwolf.zone is Zone.EXILE

    walk_to(scenario, Step.END_STEP)

    assert watchwolf.zone is Zone.BATTLEFIELD
    assert watchwolf.controller == "bob"
    assert watchwolf.untapped
    assert watchwolf.summoning_sick, "CR 403.4: a new object, sick again"
    assert phelia.counters[Counter.PLUS_ONE] == 0, "did not enter under Alice's control"


def test_phelia_gets_a_counter_when_the_exiled_permanent_returns_under_her_own_control():
    """Alice's own creature, exiled and returned, enters under her control
    again - the third sentence's condition holds, so Phelia gets the counter."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            battlefield=["Phelia, Exuberant Shepherd", "Grizzly Bears"],
        )
        .player("bob", library=["Island"], battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    phelia = scenario.creature("Phelia, Exuberant Shepherd", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.choose_trigger_targets("Phelia, Exuberant Shepherd", [bears])
    scenario.attack_with(phelia)
    scenario.pass_until_resolved()
    assert bears.zone is Zone.EXILE

    walk_to(scenario, Step.END_STEP)

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.controller == "alice"
    assert phelia.counters[Counter.PLUS_ONE] == 1


def test_phelia_never_returns_a_token():
    """CR 111.8: a token that has left the battlefield cannot come back, so
    Phelia's own delayed return is the thing refusing it, not a special case
    for tokens - and CR 111.7/704.5d then destines it to cease to exist."""
    scenario = _phelia_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    phelia = scenario.creature("Phelia, Exuberant Shepherd", "alice")
    spirit = TokenDefinition(subtypes=("Spirit",), colors=(), power=1, toughness=1, name="Spirit")
    (token,) = create_tokens(scenario.game, spirit, "bob")

    scenario.choose_trigger_targets("Phelia, Exuberant Shepherd", [token])
    scenario.attack_with(phelia)
    scenario.pass_until_resolved()
    assert token.zone is Zone.EXILE

    walk_to(scenario, Step.END_STEP)

    assert token.zone is Zone.EXILE, "CR 111.8 refused the return"
    scenario.game.check_state_based_actions()
    assert token not in scenario.game.exile, "CR 111.7/704.5d: ceases to exist off the battlefield"


def test_phelias_death_does_not_stop_the_return_but_stops_the_counter():
    """CR 113.7/603.7d/e: source and controller are fixed at creation, so
    killing Phelia before the delayed trigger resolves does not cancel the
    exile-and-return - it only leaves the third sentence's "put a +1/+1
    counter on Phelia" with no Phelia to put it on."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            battlefield=["Phelia, Exuberant Shepherd", "Grizzly Bears"],
        )
        .player("bob", library=["Island"], battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    phelia = scenario.creature("Phelia, Exuberant Shepherd", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.choose_trigger_targets("Phelia, Exuberant Shepherd", [bears])
    scenario.attack_with(phelia)
    scenario.pass_until_resolved()
    assert bears.zone is Zone.EXILE

    scenario.game.destroy(phelia)
    assert phelia.zone is Zone.GRAVEYARD

    walk_to(scenario, Step.END_STEP)

    assert bears.zone is Zone.BATTLEFIELD, "the return does not depend on Phelia surviving"
    assert bears.controller == "alice"


def test_a_round_trip_through_another_zone_change_is_a_new_object_and_is_not_returned():
    """CR 603.7c's parenthetical: "if that object left that zone and then
    returned, it's a new object and thus won't be affected."

    Before `CardState.zone_change_stamp` existed, `still_affects` matched on
    `id` and `zone` alone - so a card that left exile and came back to exile by
    some other route (staged directly here, standing in for whatever second
    effect did it) would still match and get returned a second time, which CR
    603.7c explicitly forbids.
    """
    scenario = _phelia_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    phelia = scenario.creature("Phelia, Exuberant Shepherd", "alice")
    watchwolf = scenario.creature("Watchwolf", "bob")

    scenario.choose_trigger_targets("Phelia, Exuberant Shepherd", [watchwolf])
    scenario.attack_with(phelia)
    scenario.pass_until_resolved()
    assert watchwolf.zone is Zone.EXILE
    stamp_when_delayed_trigger_was_created = watchwolf.zone_change_stamp

    # Some other effect returns it to the battlefield and exiles it again -
    # a real zone round trip through the same production API, standing in for
    # whatever card would actually do this.
    scenario.game.put_onto_battlefield(watchwolf, "bob")
    scenario.game.exile_permanent(watchwolf)
    assert watchwolf.zone_change_stamp != stamp_when_delayed_trigger_was_created

    walk_to(scenario, Step.END_STEP)

    assert watchwolf.zone is Zone.EXILE, "the stale trigger must not touch this new incarnation"


def test_a_delayed_return_created_during_the_end_step_waits_for_the_next_turns_end_step():
    """CR 513.2: "if a delayed triggered ability that triggers 'at the
    beginning of the next end step' is created during this step, that ability
    won't trigger until the next turn's end step. ... the step doesn't 'back
    up' so those abilities can go on the stack."

    Phelia is given flash-speed timing here only in the sense that her attack
    trigger is made to resolve once the end step has already begun (walked
    there for real, not jumped) - proving the *parsed* clause inherits CR
    513.2 from the generic `DelayedTrigger.matches` mechanism it is built on,
    the same way `test_an_event_that_already_happened_does_not_count` already
    proves it for the hand-written triggers.
    """
    scenario = _phelia_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    phelia = scenario.creature("Phelia, Exuberant Shepherd", "alice")
    watchwolf = scenario.creature("Watchwolf", "bob")

    scenario.choose_trigger_targets("Phelia, Exuberant Shepherd", [watchwolf])
    scenario.attack_with(phelia)
    scenario.pass_until_resolved()  # exiles Watchwolf and creates the delayed trigger, mid-combat

    walk_to(scenario, Step.END_STEP)
    assert watchwolf.zone is Zone.BATTLEFIELD, "the ordinary same-turn end step already fired it"

    # A second delayed return, created directly (the staging every other
    # `machines/delayed.py` test in this pool already uses) while the current
    # end step has already begun - CR 513.2 says it waits for the *next*
    # turn's end step, not this already-begun one.
    from magic_cards_model.machines.abilities import TriggerEvent
    from magic_cards_model.machines.delayed import DelayedTrigger

    watchwolf.tap()
    scenario.game.create_delayed_trigger(
        DelayedTrigger(
            text="At the beginning of the next end step, tap Watchwolf again's return marker.",
            effect="sacrifice",  # any registered no-op-if-absent key works; not exercised here
            event=TriggerEvent.BEGINNING_OF_STEP,
            step=Step.END_STEP,
            controller="alice",
            source_name="staged for this test",
            subject_id=None,
        )
    )
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
    assert scenario.game.delayed_triggers.triggers, "still waiting - this end step doesn't back up"

    walk_to(scenario, Step.END_STEP)
    assert not scenario.game.delayed_triggers.triggers, "fired at the *next* turn's end step"


# --------------------------------------------------------------------------
# Aether Membrane: "Whenever this creature blocks a creature, return that
# creature to its owner's hand at end of combat." - no antecedent clause of
# its own; "that creature" is the blocking pair's other half (CR 509.1a),
# read off the trigger's own event.
# --------------------------------------------------------------------------


def test_aether_membrane_returns_the_blocked_attacker_at_end_of_combat():
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Grizzly Bears"])
        .player("bob", library=["Island"], battlefield=["Aether Membrane", "Island"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    membrane = scenario.creature("Aether Membrane", "bob")

    scenario.attack_with(bears)
    scenario.block(bears, membrane)
    assert scenario.stack_names() == ["Aether Membrane's triggered ability"]
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD, "CR 511.2: waits for end of combat, not now"

    walk_to(scenario, Step.END_OF_COMBAT)

    assert bears.zone is Zone.HAND
    assert bears.owner == "alice"


# --------------------------------------------------------------------------
# Mishra's Bauble: "Draw a card at the beginning of the next turn's upkeep." -
# no object at all, and its own CR 513.2 analogue for the upkeep.
# --------------------------------------------------------------------------


def test_mishras_bauble_draws_a_card_at_the_next_turns_upkeep():
    scenario = (
        Scenario()
        .player("alice", library=["Forest", "Forest"], battlefield=["Mishra's Bauble"])
        .player("bob", library=["Island"], battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bauble = scenario.creature("Mishra's Bauble", "alice")
    hand_before = len(scenario.player("alice").hand)

    scenario.activate(bauble, targets=["bob"])
    scenario.pass_until_resolved()
    assert bauble.zone is Zone.GRAVEYARD, "the {T}, Sacrifice cost already paid"
    assert len(scenario.player("alice").hand) == hand_before, "not yet - only at the next upkeep"

    walk_to(scenario, Step.UPKEEP)
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert len(scenario.player("alice").hand) == hand_before + 1


def test_mishras_bauble_activated_during_an_upkeep_waits_for_the_next_turns_upkeep():
    """CR 513.2's "Likewise, if a delayed triggered ability ... is created
    during this step" - the same rule, for the upkeep rather than the end
    step. Activating Bauble while already sitting in an upkeep must not draw
    at that same upkeep."""
    scenario = (
        Scenario()
        .player("alice", library=["Forest", "Forest"], battlefield=["Mishra's Bauble"])
        .player("bob", library=["Island"], battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.UPKEEP)
    bauble = scenario.creature("Mishra's Bauble", "alice")
    hand_before = len(scenario.player("alice").hand)

    scenario.activate(bauble, targets=["bob"])
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == hand_before

    # Walk out of this same upkeep - the delayed trigger must not have fired.
    scenario.advance()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
    assert len(scenario.player("alice").hand) == hand_before, "this upkeep had already begun"

    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
    walk_to(scenario, Step.UPKEEP)
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert len(scenario.player("alice").hand) == hand_before + 1, "fires at the next turn's upkeep"


# --------------------------------------------------------------------------
# Fail-closed: a delayed-trigger clause whose timing this wave recognises but
# whose antecedent this wave still cannot read leaves a `DelayedClauseNotice`
# and executes nothing - CR 608.2c has no notion of running half an
# instruction, and a half-run blink is strictly worse than today's no-op (an
# opponent's permanent exiled with no guaranteed way back).
# --------------------------------------------------------------------------


def test_postmortem_lunge_no_longer_needs_a_notice():
    """Postmortem Lunge: "Return target creature card with mana value X from
    your graveyard to the battlefield. It gains haste. Exile it at the
    beginning of the next end step." Wave W6's own
    `_parse_delayed_reanimate_haste_exile_clauses` reads this shape as a real
    three-clause instruction (reanimate, grant haste, schedule the delayed
    exile) rather than leaving a `DelayedClauseNotice` - see
    `scenarios/test_postmortem_lunge.py` for the full board-level proof. This
    is only the parser-level confirmation that the notice this file used to
    assert is gone: `effect_for` now returns a real effect for this text
    (with X substituted, the same way `effect_for`'s own docstring already
    reads any other `{X}`-cost spell's rules text).
    """
    lunge = card_state("Postmortem Lunge", Zone.STACK, controller="alice", owner="alice")
    effect = effect_for(lunge.card.name, lunge.card.oracle_text, x_value=1)
    assert effect is not None

    scenario = Scenario().player("alice", library=["Forest"]).build()
    effect(scenario.game, lunge)

    assert scenario.game.delayed_clause_notices == []
