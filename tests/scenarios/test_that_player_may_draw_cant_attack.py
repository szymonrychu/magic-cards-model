"""Scenario: "That player may `<action>`. If they do, they can't attack this turn
and you put a `<kind>` counter on this enchantment." (T-136 b1) - Peace in Our
Time.

Three separate pieces of one trigger:

- "that player" is the player whose turn the beginning-of-combat trigger fired
  on (the event's player), and *they* answer the "may", not the enchantment's
  controller (`modal._parse_that_player_may_if_they_do_clause`).
- CR 118.12: "If [a player] does" checks whether the player chose to, so the
  consequences hang on the answer, not on what the draw did.
- The consequence list has two subjects: "they can't attack this turn" is the
  chooser, "you put a peace counter ..." is the enchantment's controller. The
  first is a player-wide CR 508.1c restriction, `Game.players_cant_attack_turns`
  read by `combat.attack_refusal` and stale the turn after.

No other printing has this shape (Scryfall checked 2026-11-12; Cheering Crowd's
"That player may put a +1/+1 counter ... If they do, they add" is the nearest
and has its own reader), so the corner cases vary the board: whose turn it is,
who answers, how many creatures, the counter count and the turn after.

Every CR number was looked up with `mise run rules:find`:

- **CR 118.12** - "[A player] may [do something]. If [that player] does, ..."
  checks whether the player chose to, regardless of what actually occurred.
- **CR 508.1c** - the active player checks each creature they control against
  restrictions (effects that say a creature can't attack).
- **CR 104.2b** - an effect may state that a player wins the game.
- **CR 122.1** - counters of one name are interchangeable.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import PlayedScenario, Scenario

PEACE = "Peace in Our Time"


def _board(*, alice_library: int = 6, bob_library: int = 6) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[PEACE, "Grizzly Bears", "Hill Giant"],
            hand=["Goblin Guide"],
            library=["Plains"] * alice_library,
        )
        .player("bob", battlefield=["Watchwolf"], library=["Island"] * bob_library)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _combat_trigger(scenario: PlayedScenario, *, takes: bool, chooser: str = "alice") -> None:
    """Move into the beginning of combat and resolve Peace's trigger, with
    `chooser` answering its "may"."""
    scenario.advance()
    assert scenario.step is Step.BEGINNING_OF_COMBAT
    scenario.will_take_the_may(takes, username=chooser, source=PEACE)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


def _walk_to(
    scenario: PlayedScenario,
    active: str,
    step: Step,
    *,
    skip_first: bool = False,
    decline: tuple[str, ...] = ("alice", "bob"),
) -> None:
    """Advance, resolving every trigger on the way with the "may" declined,
    until `active`'s turn reaches `step`; stops *before* resolving that step's
    own triggers. `skip_first` insists on leaving the current step first."""
    for username in decline:
        scenario.will_take_the_may(False, username=username, source=PEACE, times=None)
    for _ in range(80):
        if not skip_first and scenario.turn.active_player == active and scenario.step is step:
            return
        skip_first = False
        scenario.game.put_triggers_on_stack()
        while scenario.game.stack:
            scenario.resolve_top()
        scenario.advance()
    raise AssertionError(f"never reached {active}'s {step}")


def _drawn(scenario: PlayedScenario, username: str) -> int:
    """Cards drawn so far, off the six every library starts with."""
    return 6 - len(scenario.player(username).library)


def _peace_counters(scenario: PlayedScenario) -> int:
    return scenario.find(PEACE, Zone.BATTLEFIELD, "alice").counter_count("peace")


def test_taking_the_draw_draws_counts_and_forbids_attacking():
    scenario = _board()
    _combat_trigger(scenario, takes=True)

    assert _drawn(scenario, "alice") == 1
    assert _peace_counters(scenario) == 1
    scenario.advance()
    assert scenario.step is Step.DECLARE_ATTACKERS
    bears = scenario.creature("Grizzly Bears", "alice")
    with pytest.raises(ValueError, match="can't attack this turn"):
        scenario.attack_with(bears, defending="bob")
    assert not bears.tapped


def test_every_creature_of_the_chooser_is_forbidden_not_just_one():
    scenario = _board()
    _combat_trigger(scenario, takes=True)
    scenario.advance()
    for name in ("Grizzly Bears", "Hill Giant"):
        creature = scenario.creature(name, "alice")
        with pytest.raises(ValueError):
            scenario.attack_with(creature, defending="bob")


def test_declining_the_draw_changes_nothing():
    scenario = _board()
    _combat_trigger(scenario, takes=False)

    assert _drawn(scenario, "alice") == 0
    assert _peace_counters(scenario) == 0
    scenario.advance()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears, defending="bob")
    assert scenario.attackers() == [bears]


def test_a_creature_that_arrives_after_the_trigger_is_forbidden_too():
    """The restriction names the player (CR 508.1c), so a hasty creature
    that enters later in the turn cannot attack either."""
    scenario = _board()
    _combat_trigger(scenario, takes=True)
    scenario.advance()
    raider = scenario.put_onto_battlefield("Goblin Guide", "alice")
    with pytest.raises(ValueError, match="can't attack this turn"):
        scenario.attack_with(raider, defending="bob")


def test_the_opponents_turn_is_asked_of_the_opponent_and_counted_for_the_controller():
    """On Bob's turn "that player" is Bob: Bob answers, Bob draws and can't
    attack, and Alice - who controls the enchantment - puts the counter."""
    scenario = _board()
    _walk_to(scenario, "bob", Step.BEGINNING_OF_COMBAT, skip_first=True, decline=("alice",))
    bob_library = len(scenario.player("bob").library)
    scenario.will_take_the_may(True, username="bob", source=PEACE)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    assert len(scenario.player("bob").library) == bob_library - 1
    assert _drawn(scenario, "alice") == 0
    assert _peace_counters(scenario) == 1
    scenario.advance()
    wolf = scenario.creature("Watchwolf", "bob")
    wolf.summoning_sick = False
    with pytest.raises(ValueError, match="can't attack this turn"):
        scenario.attack_with(wolf, defending="alice")
    asked = [q for q in scenario.questions_asked() if q.source == PEACE and q.player == "bob"]
    assert len(asked) == 1


def test_the_restriction_is_gone_by_the_choosers_next_turn():
    scenario = _board()
    _combat_trigger(scenario, takes=True)
    assert scenario.game.players_cant_attack_turns["alice"] == scenario.turn.turns_taken
    _walk_to(scenario, "alice", Step.BEGINNING_OF_COMBAT, skip_first=True)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()  # the next trigger: declined
    scenario.advance()
    assert scenario.step is Step.DECLARE_ATTACKERS
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears, defending="bob")
    assert scenario.attackers() == [bears]


def _to_alices_next_upkeep(scenario: PlayedScenario) -> None:
    _walk_to(scenario, "bob", Step.UPKEEP, skip_first=True)
    _walk_to(scenario, "alice", Step.UPKEEP, skip_first=True)


def test_twelve_counters_win_the_game_at_the_upkeep():
    scenario = _board()
    scenario.game.add_counters(scenario.find(PEACE, Zone.BATTLEFIELD, "alice"), "peace", 12)
    _to_alices_next_upkeep(scenario)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack and not scenario.game.is_over:
        scenario.resolve_top()
    assert scenario.game.winner == "alice"


def test_eleven_counters_do_not_win():
    scenario = _board()
    scenario.game.add_counters(scenario.find(PEACE, Zone.BATTLEFIELD, "alice"), "peace", 11)
    _to_alices_next_upkeep(scenario)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []
    assert scenario.game.winner is None


def test_twelve_counters_do_not_win_on_the_opponents_upkeep():
    """ "At the beginning of your upkeep": Bob's upkeep is not Alice's."""
    scenario = _board()
    scenario.game.add_counters(scenario.find(PEACE, Zone.BATTLEFIELD, "alice"), "peace", 12)
    _walk_to(scenario, "bob", Step.UPKEEP, skip_first=True)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []
    assert scenario.game.winner is None
