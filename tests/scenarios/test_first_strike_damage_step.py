"""CR 510.4's first-strike damage step, driven through the automatic
turn-based-action path (`Game.advance`), not the manual `combat_damage()`/
`combat_damage_step()` helpers `tests/scenarios/test_first_strike.py` uses.

Every rule cited here was looked up this session with `mise run rules:find`
(the on-disk CR effective 2026-09-25; `knowledge_search` was not reachable):

- **CR 510.4** - "If at least one attacking or blocking creature has first
  strike (see rule 702.7) or double strike (see rule 702.4) as the combat
  damage step begins, the only creatures that assign combat damage in that
  step are those with first strike or double strike. After that step, instead
  of proceeding to the end of combat step, the phase gets a second combat
  damage step. The only creatures that assign combat damage in that step are
  the remaining attackers and blockers that had neither first strike nor
  double strike as the first combat damage step began, as well as the
  remaining attackers and blockers that currently have double strike. After
  that step, the phase proceeds to the end of combat step."
- **CR 506.1** - "... There are two combat damage steps if any attacking or
  blocking creature has first strike (see rule 702.7) or double strike (see
  rule 702.4)."
- **CR 510.3** - "Third, the active player gets priority."
- **CR 510.3a** - "Any abilities that triggered on damage being dealt or
  while state-based actions are performed afterward are put onto the stack
  before the active player gets priority; the order in which they triggered
  doesn't matter."
- **CR 702.7c** - "Giving first strike to a creature without it after combat
  damage has already been dealt in the first combat damage step won't
  preclude that creature from assigning combat damage in the second combat
  damage step. Removing first strike from a creature after it has already
  dealt combat damage in the first combat damage step won't allow it to also
  assign combat damage in the second combat damage step (unless the creature
  has double strike)."
- **CR 702.4c** - "Removing double strike from a creature during the first
  combat damage step will stop it from assigning combat damage in the second
  combat damage step."
- **CR 702.4d** - "Giving double strike to a creature with first strike after
  it has already dealt combat damage in the first combat damage step will
  allow the creature to assign combat damage in the second combat damage
  step."
- **CR 508.8** - "If no creatures are declared as attackers or put onto the
  battlefield attacking, skip the declare blockers and combat damage steps."

CR 500.6's "at the beginning of" wiring already fires the beginning-of-step
event for every occurrence of `Step.COMBAT_DAMAGE` this file drives through
(`Game._advance_past_checks`'s `TriggerEvent.BEGINNING_OF_STEP` emit runs
once per step *reached*, with no special-casing for a repeated `Step`), which
is what CR 506.1's "two combat damage steps" implies a beginning-of-step
reader should see twice. No pool printing has a genuine "at the beginning of
the combat damage step" triggered ability to assert it on - the two mentions
`grep` turns up in the pool (Command the Stage, Jolrael) are about
noncombat/combat damage dealt, not that trigger condition - so this is noted
rather than asserted.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from magic_cards_model.models import Game, Zone
from tests.scenarios.harness import Scenario


def duel(attacker: str, blocker: str | None = None, bob_life: int = 20) -> Scenario:
    battlefield = [blocker] if blocker else []
    return (
        Scenario()
        .player("alice", battlefield=[attacker])
        .player("bob", life=bob_life, battlefield=battlefield)
    )


def queue_declaration(
    scenario: Scenario, kind: DecisionKind, value: object, player: str | None = None
) -> None:
    """Script one combat declaration, the way `test_combat_turn_based_actions.py` does."""
    scenario.game.decisions.add(ScriptedAnswer(kind=kind, value=value, player=player))


def attack_unblocked_to_first_strike_step(scenario: Scenario, attacker_name: str) -> Step:
    """Declare `attacker_name` unblocked and advance to the first COMBAT_DAMAGE
    step, all through the automatic turn-based-action path.

    Returns with the game paused in that step's priority round - nobody has
    passed yet.
    """
    attacker = scenario.creature(attacker_name)
    queue_declaration(scenario, DecisionKind.DECLARE_ATTACKERS, [(attacker, "bob")])
    queue_declaration(scenario, DecisionKind.DECLARE_BLOCKERS, [], "bob")
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()  # -> DECLARE_ATTACKERS
    scenario.advance()  # -> DECLARE_BLOCKERS
    return scenario.advance()  # -> COMBAT_DAMAGE, the first-strike step


# -- (a), (j): two steps, a priority round between them, triggers first -----


def test_two_combat_damage_steps_with_a_priority_round_between_them():
    """CR 510.4/506.1/510.3/510.3a, all at once: the automatic path gives a
    first striker its own step, with the active player holding priority and
    its combat-damage trigger already on the stack (CR 510.3a) - not put there
    only once everybody has passed."""
    scenario = duel("Precinct Captain", "Watchwolf").build()
    step = attack_unblocked_to_first_strike_step(scenario, "Precinct Captain")

    assert step is Step.COMBAT_DAMAGE
    assert scenario.game.is_first_strike_damage_step
    assert scenario.priority_holder == "alice", "CR 510.3: the active player"
    assert scenario.player("bob").life == 18, "the first-strike step already dealt its 2"
    assert scenario.stack_names() == ["Precinct Captain's triggered ability"], (
        "CR 510.3a: the damage trigger is on the stack before anyone gets priority"
    )

    scenario.resolve_top()
    assert scenario.find("Soldier Token", Zone.BATTLEFIELD, "alice") is not None

    scenario.pass_until_resolved()
    assert scenario.step is Step.COMBAT_DAMAGE, "CR 510.4's second combat damage step"
    assert not scenario.game.is_first_strike_damage_step
    # `pass_until_resolved` moves the pointer with `Game.advance`, which runs
    # the *new* step's own turn-based action as it enters it (the same way
    # `attack_unblocked_to_first_strike_step` above left the first step
    # already run) - so the second step has already happened too by the time
    # this returns, and `damage_steps_done` reads 2, not 1.
    assert scenario.game.combat.damage_steps_done == 2, "the second step already ran too"
    assert scenario.player("bob").life == 18, "Precinct Captain already struck; no more damage"

    scenario.pass_until_resolved()
    assert scenario.step is Step.END_OF_COMBAT
    assert scenario.game.combat.damage_steps_done == 2


# -- (e): no first/double striker at all -------------------------------------


def test_one_damage_step_when_nothing_in_combat_has_first_or_double_strike():
    """CR 510.4 only splits the step when something in combat qualifies -
    `is_first_strike_damage_step` never reads True for a plain trade."""
    scenario = duel("Grizzly Bears", "Watchwolf").build()
    step = attack_unblocked_to_first_strike_step(scenario, "Grizzly Bears")

    assert step is Step.COMBAT_DAMAGE
    assert not scenario.game.is_first_strike_damage_step
    assert scenario.player("bob").life == 18

    scenario.pass_until_resolved()
    assert scenario.step is Step.END_OF_COMBAT, "no second occurrence of the step"
    assert scenario.game.combat.damage_steps_done == 1


# -- (h): CR 508.8, no attackers at all --------------------------------------


def test_no_attackers_means_neither_damage_step_happens():
    """CR 508.8 skips the declare blockers and combat damage steps outright -
    `is_first_strike_damage_step` stays False and no damage is dealt."""
    scenario = duel("Grizzly Bears", "Watchwolf").build()
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()  # -> DECLARE_ATTACKERS, nobody scripted: attacks nobody

    step = scenario.advance()

    assert step is Step.END_OF_COMBAT
    assert not scenario.game.is_first_strike_damage_step
    assert scenario.game.combat.damage_steps_done == 0
    assert scenario.player("bob").life == 20


# -- (c): a double striker deals damage in both steps ------------------------


def test_a_double_striker_deals_damage_in_both_steps():
    """CR 702.4b/510.4: Fencing Ace's double strike makes it assign damage in
    the first step *and* the second, unblocked."""
    scenario = duel("Fencing Ace", "Watchwolf").build()
    step = attack_unblocked_to_first_strike_step(scenario, "Fencing Ace")

    assert step is Step.COMBAT_DAMAGE
    assert scenario.game.is_first_strike_damage_step
    assert scenario.player("bob").life == 19, "the first of Fencing Ace's two points"

    scenario.pass_until_resolved()
    assert scenario.step is Step.COMBAT_DAMAGE
    assert not scenario.game.is_first_strike_damage_step
    assert scenario.player("bob").life == 18, "the second point, CR 510.4's double-strike clause"

    scenario.pass_until_resolved()
    assert scenario.step is Step.END_OF_COMBAT


# -- (b): an instant in the priority window changes regular damage ----------


def test_an_instant_in_the_window_kills_the_non_first_striking_attacker():
    """Bob removes the non-first-striking attacker before it ever reaches the
    second step - the whole reason CR 510.3's priority round exists between
    the two steps."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Precinct Captain", "Grizzly Bears"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    captain = scenario.creature("Precinct Captain")
    bears = scenario.creature("Grizzly Bears")
    queue_declaration(scenario, DecisionKind.DECLARE_ATTACKERS, [(captain, "bob"), (bears, "bob")])
    queue_declaration(scenario, DecisionKind.DECLARE_BLOCKERS, [], "bob")
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()
    scenario.advance()
    step = scenario.advance()

    assert step is Step.COMBAT_DAMAGE
    assert scenario.game.is_first_strike_damage_step
    assert scenario.player("bob").life == 18, "only the first striker has hit so far"

    scenario.resolve_top()  # Precinct Captain's token trigger
    scenario.pass_priority("alice")  # CR 117.3b: priority passes to bob
    mountain = scenario.untapped_sources("Mountain", username="bob")[0]
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=[bears])
    assert bears.zone is Zone.GRAVEYARD

    scenario.pass_until_resolved()
    assert scenario.step is Step.COMBAT_DAMAGE
    assert not scenario.game.is_first_strike_damage_step
    assert scenario.player("bob").life == 18, "the Bears never got to swing back"

    scenario.pass_until_resolved()
    assert scenario.step is Step.END_OF_COMBAT


# -- (d): CR 702.7c/702.4c-d, the snapshot semantics -------------------------


def test_first_strike_granted_in_the_window_still_strikes_in_the_second_step():
    """CR 702.7c, the permissive half: a creature with no first strike or
    double strike as the first step began is not in the snapshot, so it
    strikes in the second step regardless of what it has by then - reading
    live keywords instead (as `double or not first` alone would) gets this
    wrong the moment the granted first strike makes `not first` false."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Precinct Captain", "Grizzly Bears", "Plains", "Plains"],
            hand=["Aerial Maneuver"],
        )
        .player("bob")
        .build()
    )
    captain = scenario.creature("Precinct Captain")
    bears = scenario.creature("Grizzly Bears")
    queue_declaration(scenario, DecisionKind.DECLARE_ATTACKERS, [(captain, "bob"), (bears, "bob")])
    queue_declaration(scenario, DecisionKind.DECLARE_BLOCKERS, [], "bob")
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()
    scenario.advance()
    step = scenario.advance()

    assert step is Step.COMBAT_DAMAGE
    assert bears.id not in scenario.game.combat.first_strike_step_ids
    scenario.resolve_top()  # Precinct Captain's token trigger
    plains = scenario.untapped_sources("Plains", "Plains")
    scenario.cast_and_resolve("Aerial Maneuver", *plains, targets=[bears])

    scenario.pass_until_resolved()
    assert scenario.step is Step.COMBAT_DAMAGE
    assert not scenario.game.is_first_strike_damage_step
    assert scenario.player("bob").life == 15, (
        "Precinct Captain's 2, then Bears' pumped 3 (Aerial Maneuver's +1/+1 too) "
        "in the second step - granted first strike notwithstanding"
    )


def test_a_first_striker_that_already_struck_does_not_strike_again_once_stripped():
    """CR 702.7c, the restrictive half: Reflexes' granted first strike lets
    Grizzly Bears strike in the snapshot's step; destroying the aura in the
    window (losing first strike, gaining no double strike) must not let it
    assign again in the second step."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Grizzly Bears", "Mountain", "Plains"],
            hand=["Reflexes", "Demystify"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    mountain = scenario.untapped_sources("Mountain")[0]
    scenario.cast_and_resolve("Reflexes", mountain, targets=[bears])

    queue_declaration(scenario, DecisionKind.DECLARE_ATTACKERS, [(bears, "bob")])
    queue_declaration(scenario, DecisionKind.DECLARE_BLOCKERS, [], "bob")
    scenario.advance()  # -> BEGINNING_OF_COMBAT
    scenario.advance()  # -> DECLARE_ATTACKERS
    scenario.advance()  # -> DECLARE_BLOCKERS
    step = scenario.advance()  # -> COMBAT_DAMAGE

    assert step is Step.COMBAT_DAMAGE
    assert bears.id in scenario.game.combat.first_strike_step_ids
    assert scenario.player("bob").life == 18, "Bears' first-strike point, granted by Reflexes"

    plains = scenario.untapped_sources("Plains")[0]
    reflexes = scenario.find("Reflexes", Zone.BATTLEFIELD, "alice")
    scenario.cast_and_resolve("Demystify", plains, targets=[reflexes])
    assert reflexes.zone is Zone.GRAVEYARD, "first strike is gone with the aura that granted it"

    scenario.pass_until_resolved()
    assert scenario.step is Step.COMBAT_DAMAGE
    assert not scenario.game.is_first_strike_damage_step
    assert scenario.player("bob").life == 18, (
        "no second strike: it already struck, and lost first strike"
    )


def test_removing_double_strike_in_the_window_stops_the_second_strike():
    """CR 702.4c: Battle Mastery's granted double strike, stripped mid-window
    by destroying the aura, stops the second-step damage the same creature
    would otherwise get."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Grizzly Bears"] + ["Plains"] * 4,
            hand=["Battle Mastery", "Demystify"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    plains = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.cast_and_resolve("Battle Mastery", *plains, targets=[bears])

    queue_declaration(scenario, DecisionKind.DECLARE_ATTACKERS, [(bears, "bob")])
    queue_declaration(scenario, DecisionKind.DECLARE_BLOCKERS, [], "bob")
    scenario.advance()  # -> BEGINNING_OF_COMBAT
    scenario.advance()  # -> DECLARE_ATTACKERS
    scenario.advance()  # -> DECLARE_BLOCKERS
    step = scenario.advance()  # -> COMBAT_DAMAGE

    assert step is Step.COMBAT_DAMAGE
    assert bears.id in scenario.game.combat.first_strike_step_ids
    assert scenario.player("bob").life == 18, "Bears' first point, as a double striker"

    remaining_plains = scenario.untapped_sources("Plains")[0]
    mastery = scenario.find("Battle Mastery", Zone.BATTLEFIELD, "alice")
    scenario.cast_and_resolve("Demystify", remaining_plains, targets=[mastery])

    scenario.pass_until_resolved()
    assert scenario.step is Step.COMBAT_DAMAGE
    assert not scenario.game.is_first_strike_damage_step
    assert scenario.player("bob").life == 18, "double strike gone with the aura: no second point"


def test_granting_double_strike_after_the_first_strike_lets_it_strike_again():
    """CR 702.4d: Flamehold Grappler (first strike only, multicolored so
    Psychotic Fury can target it) already dealt its first-strike point;
    granting it double strike mid-window lets it assign a second time, on top
    of the first."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Flamehold Grappler", "Mountain", "Mountain"],
            hand=["Psychotic Fury"],
            library=["Forest"],  # Psychotic Fury's own "Draw a card."
        )
        .player("bob")
        .build()
    )
    grappler = scenario.creature("Flamehold Grappler")
    queue_declaration(scenario, DecisionKind.DECLARE_ATTACKERS, [(grappler, "bob")])
    queue_declaration(scenario, DecisionKind.DECLARE_BLOCKERS, [], "bob")
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()
    scenario.advance()
    step = scenario.advance()

    assert step is Step.COMBAT_DAMAGE
    assert grappler.id in scenario.game.combat.first_strike_step_ids
    assert scenario.player("bob").life == 17, "Flamehold Grappler's 3, first-strike step"

    mountains = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Psychotic Fury", *mountains, targets=[grappler])

    scenario.pass_until_resolved()
    assert scenario.step is Step.COMBAT_DAMAGE
    assert not scenario.game.is_first_strike_damage_step
    assert scenario.player("bob").life == 14, (
        "double strike granted after already striking: a second 3 lands"
    )

    scenario.pass_until_resolved()
    assert scenario.step is Step.END_OF_COMBAT


# -- (f): an additional combat phase gets its own two damage steps ----------


def test_an_additional_combat_phase_gets_its_own_two_damage_steps():
    """CR 500.8's additional combat phase (Aggravated Assault) is a full
    combat phase of its own: a first striker in it takes two damage steps,
    and the turn's own real combat phase still runs afterward."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Aggravated Assault", "Precinct Captain"] + ["Mountain"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assault = scenario.find("Aggravated Assault", Zone.BATTLEFIELD, "alice")
    captain = scenario.creature("Precinct Captain")

    scenario.activate(
        assault,
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain", "Mountain"),
    )
    scenario.resolve_top()

    queue_declaration(scenario, DecisionKind.DECLARE_ATTACKERS, [(captain, "bob")])
    queue_declaration(scenario, DecisionKind.DECLARE_BLOCKERS, [], "bob")

    first_strike_flags: list[bool] = []
    steps: list[Step] = [scenario.step]
    while steps[-1] is not Step.END_STEP:
        step = scenario.advance()
        steps.append(step)
        if step is Step.COMBAT_DAMAGE:
            first_strike_flags.append(scenario.game.is_first_strike_damage_step)
            if scenario.stack_names():
                scenario.resolve_top()

    assert first_strike_flags == [True, False], "the additional combat's own two damage steps"
    assert steps.count(Step.COMBAT_DAMAGE) == 2, (
        "no damage step in the turn's own real combat: no attacker declared there"
    )
    assert steps.count(Step.BEGINNING_OF_COMBAT) == 2, (
        "the additional combat phase, and the turn's own real one afterward"
    )
    assert scenario.player("bob").life == 18
    assert scenario.turn.extra_phase_queue == []
    assert scenario.turn.resume_index is None


# -- (g): ending the turn in the window drops the queued second step --------


def test_ending_the_turn_in_the_window_leaves_no_second_step_queued():
    """CR 724.1d: Time Stop ends the turn while the first-strike step's
    priority round is still open. No second combat damage step is queued -
    the turn skips straight to cleanup, and nothing is left in the extra-phase
    queue for a future combat to trip over."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Precinct Captain"] + ["Island"] * 6,
            hand=["Time Stop"],
        )
        .player("bob")
        .build()
    )
    captain = scenario.creature("Precinct Captain")
    queue_declaration(scenario, DecisionKind.DECLARE_ATTACKERS, [(captain, "bob")])
    queue_declaration(scenario, DecisionKind.DECLARE_BLOCKERS, [], "bob")
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()
    scenario.advance()
    step = scenario.advance()

    assert step is Step.COMBAT_DAMAGE
    assert scenario.game.is_first_strike_damage_step
    scenario.resolve_top()  # Precinct Captain's token trigger

    islands = scenario.untapped_sources(*(["Island"] * 6))
    scenario.cast_and_resolve("Time Stop", *islands)

    assert scenario.step is Step.CLEANUP
    assert scenario.turn.extra_phase_queue == []
    assert scenario.turn.resume_index is None


# -- (i): a paused game round-trips with the flag and ids intact ------------


def test_a_paused_game_in_the_first_strike_step_round_trips():
    """A game snapshotted mid the first-strike step's priority round decodes
    back to the same `is_first_strike_damage_step` read and the same recorded
    first-strike ids - the persisted state a paused game relies on."""
    scenario = duel("Precinct Captain", "Watchwolf").build()
    step = attack_unblocked_to_first_strike_step(scenario, "Precinct Captain")

    assert step is Step.COMBAT_DAMAGE
    assert scenario.game.is_first_strike_damage_step
    captain = scenario.creature("Precinct Captain")
    assert scenario.game.combat.first_strike_step_ids == [captain.id]

    decoded = Game.model_validate(scenario.game.model_dump())

    assert decoded.is_first_strike_damage_step
    assert decoded.combat.first_strike_damage_step is True
    assert decoded.combat.first_strike_step_ids == [captain.id]
    assert decoded.turn is not None and decoded.turn.step is Step.COMBAT_DAMAGE
