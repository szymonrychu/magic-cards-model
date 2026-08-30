"""Scenario: `Game.advance` moving the turn marker forward.

Two defects, reported together from the same live playtest:

1. `advance` moved the turn to the next step **while the stack was
   non-empty**, stranding whatever was on it forever - an ability whose costs
   had already been paid (a life total spent, a land sacrificed) simply
   vanished, resolving nothing. CR 500.2: "A phase or step in which players
   receive priority ends when the stack is empty and all players pass in
   succession. Simply having the stack become empty doesn't cause such a
   phase or step to end - all players have to pass in succession with the
   stack empty." CR 117.4 / CR 405.5 say the same thing from the passing
   side: everyone passing resolves the stack's top, or, only once the stack
   is empty, ends the step. Nothing in the rules lets a step end while
   something still waits on the stack, by any route.

2. A player who was **not** the active player (and not that player's
   controller, CR 723.5) was allowed to call `advance` and move somebody
   else's turn forward. CR 117.3a hands the active player priority "at the
   beginning of most steps and phases" - advancing is modelled here as that
   same player's own decision.

Every CR number in this file was looked up with `knowledge_search(type="rules")`
in the session that wrote it.

- **CR 500.2** - a phase or step with priority ends only on an empty stack
  and a full round of passes; an empty stack alone does not end it.
- **CR 117.4 / CR 405.5** - the same rule, read from `pass_priority`'s side.
- **CR 500.3** - "the only such steps [where no player receives priority] are
  the untap step ... and certain cleanup steps" - the sole exception to the
  rule above, because nothing can reach the stack there to begin with.
- **CR 502.4** - no player receives priority during the untap step.
- **CR 514.3** - normally no player receives priority during the cleanup
  step either; CR 514.3a's exception (a cleanup trigger reopening the step)
  is not modelled - see `Game.advance`'s docstring.
- **CR 117.3a** - the active player receives priority first, at the start of
  most steps and phases.
- **CR 723.5** - while controlling another player, a controller makes that
  player's choices instead of them.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def fetch_board() -> Scenario:
    return (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Forest"])
        .player("bob", life=20, library=["Plains"], battlefield=["Flooded Strand"])
    )


# -- the minimal reproduction -------------------------------------------------


def test_advance_is_refused_while_an_ability_sits_on_the_stack():
    """The exact bug: activate an ability, then try to walk the turn past it.

    Before the fix this succeeded and stranded the ability. Now it is
    refused, the step does not move, the stack still holds the ability, and
    passing priority afterwards resolves it normally - the ability was never
    lost, just correctly blocked from being skipped past.
    """
    scenario = fetch_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    strand = scenario.find("Flooded Strand", Zone.BATTLEFIELD)

    scenario.pass_priority()  # alice passes; bob (non-active) now holds priority
    scenario.activate(strand, username="bob")  # {T}, pay 1 life, sacrifice this land

    assert scenario.stack_names() == ["Flooded Strand's activated ability"]
    assert scenario.player("bob").life == 19
    assert strand.zone is Zone.GRAVEYARD

    with pytest.raises(ValueError, match="pass priority instead"):
        scenario.advance(username="alice")

    # Refused, not silently performed: still the same step, still on the stack.
    assert scenario.step is Step.PRECOMBAT_MAIN
    assert scenario.stack_names() == ["Flooded Strand's activated ability"]

    # The way out the refusal names actually works, and nothing was lost.
    scenario.pass_until_resolved()
    assert scenario.find("Plains", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD
    assert scenario.stack_names() == []


def test_the_refusal_names_the_stack_as_the_reason():
    scenario = fetch_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    strand = scenario.find("Flooded Strand", Zone.BATTLEFIELD)
    scenario.pass_priority()
    scenario.activate(strand, username="bob")

    with pytest.raises(ValueError) as excinfo:
        scenario.advance(username="alice")

    message = str(excinfo.value)
    assert "precombat_main" in message
    assert "non-empty" in message
    assert "pass priority" in message


def test_advance_never_silently_resolves_the_stack():
    """A regression test for the tempting wrong fix: `advance` must refuse,
    never quietly resolve the stack and move on anyway. If someone
    reintroduces that shape, this fails loudly: the ability would resolve
    (fetching a Plains) despite `advance` raising.
    """
    scenario = fetch_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    strand = scenario.find("Flooded Strand", Zone.BATTLEFIELD)
    scenario.pass_priority()
    scenario.activate(strand, username="bob")

    with pytest.raises(ValueError):
        scenario.advance(username="alice")

    assert scenario.stack_names() == ["Flooded Strand's activated ability"]
    assert "Plains" not in scenario.battlefield_names()


def test_advancing_through_several_steps_with_a_stack_is_refused_at_each_one():
    """The reported log walked declare_attackers -> end_of_combat ->
    postcombat_main -> end_step, all with the ability still on the stack.
    Every one of those must refuse."""
    scenario = fetch_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    strand = scenario.find("Flooded Strand", Zone.BATTLEFIELD)
    scenario.pass_priority()
    scenario.activate(strand, username="bob")

    for _ in range(4):
        with pytest.raises(ValueError, match="non-empty"):
            scenario.advance(username="alice")
        assert scenario.step is Step.DECLARE_ATTACKERS

    scenario.pass_until_resolved()
    assert scenario.stack_names() == []


# -- the full Flooded Strand sequence, uninterrupted -------------------------


def test_flooded_strand_resolves_end_to_end_when_both_players_pass():
    """The outcome bob was denied: activate, both players pass, the ability
    RESOLVES, the land is fetched, and the library is shuffled."""
    scenario = fetch_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    strand = scenario.find("Flooded Strand", Zone.BATTLEFIELD)
    library_before = [state.card.name for state in scenario.player("bob").library]

    scenario.pass_priority()
    scenario.activate(strand, username="bob")
    outcome = scenario.pass_until_resolved()

    from magic_cards_model.machines import PriorityOutcome

    assert outcome is PriorityOutcome.RESOLVE_TOP
    assert scenario.stack_names() == []
    plains = scenario.find("Plains", Zone.BATTLEFIELD)
    assert plains.zone is Zone.BATTLEFIELD
    assert strand.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 19
    remaining = [state.card.name for state in scenario.player("bob").library]
    assert remaining != library_before  # shuffled, and one card shorter (or equal-length noop)
    assert "Plains" not in remaining


# -- advancing with an empty stack is untouched -------------------------------


def test_advancing_with_an_empty_stack_still_works_through_a_whole_turn_cycle():
    scenario = fetch_board().build()
    assert scenario.turn.active_player == "alice"

    for _ in range(2):
        scenario.turn.advance_to(Step.CLEANUP)
        scenario.advance()

    assert scenario.turn.active_player == "alice"
    assert scenario.turn.turn_number == 2


def test_untap_and_cleanup_grant_no_priority_and_advance_freely_with_an_empty_stack():
    scenario = fetch_board().build()
    scenario.turn.advance_to(Step.CLEANUP)
    assert scenario.stack_names() == []

    step = scenario.advance()  # cleanup -> untap, nobody ever had priority in either

    assert step is Step.UNTAP
    assert scenario.turn.active_player == "bob"


# -- who may advance -----------------------------------------------------------


def test_a_non_active_player_may_not_advance_the_turn():
    scenario = fetch_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.turn.active_player == "alice"

    with pytest.raises(ValueError, match="may not advance the turn"):
        scenario.advance(username="bob")

    assert scenario.step is Step.PRECOMBAT_MAIN
    assert scenario.turn.active_player == "alice"


def test_the_active_player_may_advance_untap_and_cleanup_on_their_own_turn():
    scenario = fetch_board().build()
    scenario.turn.advance_to(Step.CLEANUP)

    step = scenario.advance(username="alice")

    assert step is Step.UNTAP


def test_a_player_controlling_the_active_player_may_advance_for_them():
    """CR 723.5: while controlling another player, the controller makes all
    of that player's choices - advancing their untap/cleanup included.

    CR 723.1 scopes the effect to the controlled player's *next* turn, so
    this cycles the table around once (alice -> bob -> alice) before the
    control actually takes hold, the same way
    `test_controlling_another_player.py` establishes it."""
    scenario = fetch_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_control_of_player("bob", "alice")  # bob controls alice's *next* turn

    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # bob's turn now; alice's control has not begun yet
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # alice's turn again - now bob-controlled

    assert scenario.turn.active_player == "alice"
    assert scenario.game.controller_of_player("alice") == "bob"

    scenario.turn.advance_to(Step.CLEANUP)
    step = scenario.advance(username="bob")

    assert step is Step.UNTAP
