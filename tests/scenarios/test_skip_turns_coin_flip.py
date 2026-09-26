"""CR 705's coin flip (counted, not won/lost) and CR 614.10's "skip your
next turn" replacement effect - Ral Zarek, Guest Lecturer's own "−7": "Flip
five coins. Target opponent skips their next X turns, where X is the number
of coins that came up heads."

Rules verified with `mise run rules:find` in the session that wrote this
file:

- **CR 705.1** - a coin flip, two equally likely outcomes.
- **CR 705.2** - some effects "care only about whether the coin comes up
  heads or tails" - no player wins or loses the flip for this kind.
- **CR 614.10** - "skip [something]" is a replacement effect: "Instead of
  doing [something], do nothing." Once a turn has begun it can no longer be
  skipped - a skip waits for the next occurrence.
- **CR 614.10a** - "If two effects each cause a player to skip their next
  occurrence, that player must skip the next two."
- **CR 500.7** - an extra turn is inserted directly after the turn in
  progress; it does not move the round-the-table rotation on its own.

`Game.flip_coin` is seeded from `shuffle_seed` and a running counter
(`coin_flips_performed`), documented as reproducible - the exact five
outcomes for a fresh scenario's default `shuffle_seed=0`, flips 0-4, are
computed inline below the same way `flip_coin`'s own docstring says any
scenario asserting on a flip's result must.
"""

from random import Random

from magic_cards_model.machines import Step
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _board():
    scenario = (
        Scenario()
        .player("alice", library=["Plains"] * 8, battlefield=["Ral Zarek, Guest Lecturer"])
        .player("bob", library=["Plains"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _heads_count(shuffle_seed: int, start: int, flips: int) -> int:
    """The exact CR 705.1 outcome `Game.flip_coin` will produce for the next
    `flips` calls, replicated by its own documented seeding formula - not a
    guess, the identical computation `flip_coin` itself runs."""
    return sum(
        1
        for n in range(start, start + flips)
        if Random(f"{shuffle_seed}:{n}:coin").random() < 0.5  # noqa: S311
    )


def test_ral_zarek_minus_seven_skips_the_opponents_next_turns_by_coins_that_came_up_heads():
    scenario = _board()
    ral = scenario.creature("Ral Zarek, Guest Lecturer", "alice")
    ral.add_counters(Counter.LOYALTY, 4)  # printed 3 + 4 = 7, enough for CR 606.6's "−7"
    expected_heads = _heads_count(scenario.game.shuffle_seed, scenario.game.coin_flips_performed, 5)
    scenario.will_choose_targets("bob")
    scenario.activate(ral, index=3)
    scenario.pass_until_resolved()
    assert scenario.game.coin_flips_performed == 5
    assert scenario.game.turn.skipped_turns.get("bob", 0) == expected_heads
    assert expected_heads > 0  # this build's seed/counter actually exercises a skip


def test_a_skipped_turn_is_spent_without_anything_happening_in_it():
    """CR 614.10: "Instead of doing [something], do nothing." - bob's next
    turn never begins at all; the turn passes straight back to alice, and
    bob's own per-turn counter (`TurnMachine.own_turns_taken`) does not go
    up for the skipped occurrence."""
    scenario = _board()
    scenario.game.skip_next_turns("bob", 1)
    bob_turns_before = scenario.turn.own_turns_taken("bob")
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # would be bob's untap step - skipped outright
    assert scenario.turn.active_player == "alice"
    assert scenario.turn.own_turns_taken("bob") == bob_turns_before
    assert scenario.turn.skipped_turns.get("bob", 0) == 0


def test_two_skip_effects_on_the_same_player_stack_cr_614_10a():
    """ "If two effects each cause a player to skip their next occurrence,
    that player must skip the next two" - two separate `skip_next_turns`
    calls owe two skipped turns, not one collapsed into the other.

    Two players seated: every one of bob's skipped turns bounces the active
    seat straight back to alice (there is nobody else between them), so both
    charges are spent across two of alice's own turns before bob ever plays
    again - never three, which is what one skip getting silently reused
    twice would look like from the outside."""
    scenario = _board()
    scenario.game.skip_next_turns("bob", 1)
    scenario.game.skip_next_turns("bob", 1)
    assert scenario.turn.skipped_turns["bob"] == 2
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # bob's turn skipped (1st charge spent) - back to alice
    assert scenario.turn.active_player == "alice"
    assert scenario.turn.skipped_turns["bob"] == 1
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # bob's turn skipped again (2nd charge spent) - alice again
    assert scenario.turn.active_player == "alice"
    assert "bob" not in scenario.turn.skipped_turns
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # no charge left - bob finally takes a turn
    assert scenario.turn.active_player == "bob"


def test_a_skip_owed_to_a_player_is_spent_on_an_extra_turn_too():
    """CR 500.7's extra turn is still CR 614.10's "turn" - a skip owed to the
    player waiting on one is spent on it rather than let through."""
    scenario = _board()
    scenario.game.grant_extra_turn("alice")
    scenario.game.skip_next_turns("alice", 1)
    alice_turns_before = scenario.turn.own_turns_taken("alice")
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # the queued extra turn for alice - skipped
    assert scenario.turn.active_player == "bob"
    assert scenario.turn.own_turns_taken("alice") == alice_turns_before
    assert "alice" not in scenario.turn.skipped_turns


def test_a_departed_players_owed_skip_is_dropped():
    """`TurnMachine.leave` drops a departed player's queued extra turns
    (CR 800.4); their owed skips go with them for the same reason - nobody
    is left to take, or skip, a turn on their behalf."""
    scenario = _board()
    scenario.game.skip_next_turns("bob", 3)
    scenario.turn.leave("bob")
    assert "bob" not in scenario.turn.skipped_turns
