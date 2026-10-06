"""Scenario: "You can't lose the game and your opponents can't win the game."

Two forms of one rule-of-the-game effect (CR 611.1's "affects players or the
rules of the game"), read by one predicate - `Game.why_cant_lose_the_game` /
`Game.why_cant_win_the_game`:

- the turn-scoped spell form, Angel's Grace: "Split second. You can't lose the
  game this turn and your opponents can't win the game this turn. Until end of
  turn, damage that would reduce your life total to less than 1 reduces it to
  1 instead." - recorded on `Game.casting_rule_effects` when it resolves and
  ended by CR 514.2 in the cleanup step;
- the static form, Platinum Angel and Herald of Eternal Dawn: "You can't lose
  the game and your opponents can't win the game." - read fresh off the
  battlefield's computed abilities every time it is asked (CR 604.2, 611.3a).

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 101.2** - a "can't" effect takes precedence over a rule or effect that
  directs something to happen.
- **CR 104.2a** - a player still in the game wins once every opponent has
  left; "this happens immediately and overrides all effects that would
  preclude that player from winning the game".
- **CR 104.2b** - an effect may state that a player wins the game.
- **CR 104.3a** - a player can concede at any time, and loses.
- **CR 104.3b** - a player at 0 or less life loses the next time a player
  would receive priority (a state-based action).
- **CR 104.3e** - an effect may state that a player loses the game.
- **CR 514.2** - in cleanup, all "until end of turn" and "this turn" effects end.
- **CR 514.3a** - state-based actions are then checked in the cleanup step.
- **CR 611.2a** - a resolved spell's continuous effect lasts as long as stated.
- **CR 614.1a** - "instead" effects are replacement effects.
- **CR 702.61a** - split second.
- **CR 704.3** - state-based actions are checked whenever a player would get
  priority.
- **CR 704.5a / 704.5b / 704.5c** - 0 or less life, a draw from an empty
  library since the last check, ten or more poison counters.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers.parse import read_cant_lose_cant_win
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.game import Game
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario


def _main_phase(alice: dict, bob: dict | None = None):
    scenario = Scenario().player("alice", **alice).player("bob", **(bob or {})).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _grace_board(**alice):
    alice.setdefault("hand", ["Angel's Grace"])
    alice.setdefault("battlefield", ["Plains"])
    alice.setdefault("library", ["Plains"] * 5)
    return _main_phase(
        alice,
        {"hand": ["Lightning Bolt"], "battlefield": ["Mountain"], "library": ["Mountain"] * 5},
    )


def _cast_grace(scenario):
    (plains,) = scenario.untapped_sources("Plains", username="alice")
    return scenario.cast_and_resolve("Angel's Grace", plains, username="alice")


def _to_next_turn(scenario) -> None:
    active = scenario.turn.active_player
    while scenario.game.is_in_game(active) and scenario.turn.active_player == active:
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
        scenario.advance()


def _to_upkeep_of(scenario, username: str) -> None:
    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == username):
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


# -- support oracle ------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["Angel's Grace", "Platinum Angel", "Herald of Eternal Dawn", "Angel of Grace"]
)
def test_every_clause_is_handled(name):
    for clause in card_support(card(name)).clauses:
        assert clause.outcome == "handled", (name, clause.text, clause.outcome)


# -- the reader ------------------------------------------------------------------


def test_reader_reads_the_static_and_the_turn_scoped_forms():
    static = read_cant_lose_cant_win(
        "You can't lose the game and your opponents can't win the game."
    )
    assert static is not None
    assert (static.you_cant_lose, static.opponents_cant_win, static.this_turn) == (
        True,
        True,
        False,
    )
    turn = read_cant_lose_cant_win(
        "You can't lose the game this turn and your opponents can't win the game this turn."
    )
    assert turn is not None
    assert (turn.you_cant_lose, turn.opponents_cant_win, turn.this_turn) == (True, True, True)
    alone = read_cant_lose_cant_win("You can't lose the game.")
    assert alone is not None
    assert (alone.you_cant_lose, alone.opponents_cant_win) == (True, False)


@pytest.mark.parametrize(
    "text",
    [
        # Abyssal Persecutor's reversed sentence is a different effect.
        "You can't win the game and your opponents can't lose the game.",
        # A mixed duration is not one effect.
        "You can't lose the game this turn and your opponents can't win the game.",
        "You can't lose the game and you can't lose the game.",
        "As long as you control a Gideon planeswalker, you can't lose the game.",
        "Flying",
    ],
)
def test_reader_refuses_near_misses(text):
    assert read_cant_lose_cant_win(text) is None


# -- Angel's Grace: the turn-scoped spell form ----------------------------------


def test_split_second_keeps_the_opponent_from_responding():
    scenario = _grace_board()
    (plains,) = scenario.untapped_sources("Plains", username="alice")
    scenario.cast_onto_stack("Angel's Grace", plains, username="alice")
    scenario.pass_priority("alice")

    with pytest.raises(ValueError, match="CR 702.61a"):
        scenario.cast("Lightning Bolt", username="bob")


def test_resolving_records_the_turn_scoped_effect_for_the_caster():
    scenario = _grace_board()
    _cast_grace(scenario)

    assert scenario.game.why_cant_lose_the_game("alice") is not None
    assert scenario.game.why_cant_lose_the_game("bob") is None
    assert scenario.game.why_cant_win_the_game("bob") is not None
    assert scenario.game.why_cant_win_the_game("alice") is None


def test_damage_is_floored_at_one_by_the_third_sentence():
    scenario = _grace_board(life=2)
    _cast_grace(scenario)
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.pass_priority("alice")

    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.state_based_actions()

    assert scenario.player("alice").life == 1
    assert scenario.game.is_in_game("alice")


def test_life_loss_that_is_not_damage_is_not_floored_but_the_player_stays_in():
    """Night's Whisper's "you lose 2 life" is not damage, so the third sentence
    does not floor it - but CR 704.5a's loss can't happen (CR 101.2)."""
    scenario = _grace_board(
        life=2,
        hand=["Angel's Grace", "Night's Whisper"],
        battlefield=["Plains", "Swamp", "Swamp"],
    )
    _cast_grace(scenario)
    swamps = scenario.untapped_sources("Swamp", "Swamp", username="alice")
    scenario.cast_and_resolve("Night's Whisper", *swamps, username="alice")
    scenario.state_based_actions()

    assert scenario.player("alice").life == 0
    assert scenario.game.is_in_game("alice")
    assert not scenario.game.is_over


def test_a_player_at_zero_life_loses_once_the_turn_ends():
    """CR 514.2 ends the effect in cleanup and CR 514.3a's check removes her."""
    scenario = _grace_board(life=2)
    _cast_grace(scenario)
    scenario.game.lose_life("alice", 5)
    scenario.state_based_actions()
    assert scenario.game.is_in_game("alice")

    _to_next_turn(scenario)

    assert not scenario.game.is_in_game("alice")
    assert scenario.game.winner == "bob"
    assert scenario.game.casting_rule_effects == []


def test_drawing_from_an_empty_library_does_not_lose_and_is_not_held_over():
    """CR 704.5b looks only at draws "since the last time state-based actions
    were checked": the check that could not remove her has looked, so once the
    effect ends there is nothing left to lose to."""
    scenario = _grace_board(library=[])
    _cast_grace(scenario)
    scenario.draw(1, username="alice")
    scenario.state_based_actions()
    assert scenario.game.is_in_game("alice")

    _to_next_turn(scenario)

    assert scenario.game.is_in_game("alice")
    assert scenario.game.winner is None


def test_ten_poison_counters_do_not_lose_this_turn_but_do_after():
    scenario = _grace_board()
    _cast_grace(scenario)
    scenario.player("alice").add_counters(Counter.POISON, 10)
    scenario.state_based_actions()
    assert scenario.game.is_in_game("alice")

    _to_next_turn(scenario)

    assert not scenario.game.is_in_game("alice"), "CR 704.5c once the effect ends"
    assert scenario.game.winner == "bob"


def test_only_the_caster_is_protected():
    scenario = _grace_board()
    _cast_grace(scenario)
    scenario.game.lose_life("bob", 20)
    scenario.state_based_actions()

    assert not scenario.game.is_in_game("bob")
    assert scenario.game.winner == "alice"


def test_an_effect_saying_she_loses_does_nothing_this_turn():
    """CR 104.3e: Summoner's Pact's unpaid upkeep trigger, answered by Angel's
    Grace on the stack above it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Summoner's Pact", "Angel's Grace"],
            battlefield=["Plains"],
            library=["Forest"] * 6,
        )
        .player("bob", library=["Forest"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Summoner's Pact", username="alice")
    scenario.will_pay_the_mana_cost(False, username="alice", source="Summoner's Pact")
    scenario.advance()
    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == "alice"):
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
        scenario.advance()
    assert scenario.stack_names(), "the pact's delayed trigger is waiting on the stack"

    _cast_grace(scenario)
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
    scenario.state_based_actions()

    assert scenario.game.is_in_game("alice")
    assert "alice" not in scenario.game.losers
    assert scenario.game.winner is None


def test_an_opponent_cannot_win_by_an_effect_this_turn():
    """CR 104.2b: Helix Pinnacle's upkeep trigger, answered by Angel's Grace."""
    scenario = (
        Scenario()
        .player("alice", hand=["Angel's Grace"], battlefield=["Plains"], library=["Plains"] * 6)
        .player("bob", battlefield=["Helix Pinnacle"], library=["Forest"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.find("Helix Pinnacle", Zone.BATTLEFIELD).add_counters("tower", 100)
    scenario.advance()
    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == "bob"):
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
        scenario.advance()
    assert scenario.stack_names(), "Helix Pinnacle's trigger is on the stack"

    scenario.pass_priority("bob")
    _cast_grace(scenario)
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert scenario.game.winner is None
    assert not scenario.game.is_over


def test_conceding_still_works_and_the_opponent_still_wins():
    """CR 104.3a: conceding is always possible. CR 104.2a: bob, the last player
    left, wins even though "your opponents can't win the game" applies."""
    scenario = _grace_board()
    _cast_grace(scenario)

    scenario.game.concede("alice")

    assert not scenario.game.is_in_game("alice")
    assert scenario.game.winner == "bob"


def test_the_effect_round_trips():
    scenario = _grace_board()
    _cast_grace(scenario)
    scenario.game.lose_life("alice", 25)

    decoded = Game.model_validate(scenario.game.model_dump())
    decoded.check_state_based_actions()

    assert decoded.is_in_game("alice")
    assert decoded.why_cant_lose_the_game("alice") is not None
    assert decoded.why_cant_win_the_game("bob") is not None


# -- Platinum Angel / Herald of Eternal Dawn: the static form -------------------


@pytest.mark.parametrize("angel", ["Platinum Angel", "Herald of Eternal Dawn"])
def test_static_keeps_its_controller_in_at_zero_life(angel):
    scenario = _main_phase({"battlefield": [angel], "life": 1}, {"battlefield": ["Mountain"]})
    scenario.game.lose_life("alice", 6)
    scenario.state_based_actions()

    assert scenario.player("alice").life == -5
    assert scenario.game.is_in_game("alice")
    assert not scenario.game.is_over


@pytest.mark.parametrize("angel", ["Platinum Angel", "Herald of Eternal Dawn"])
def test_static_does_not_protect_the_opponent(angel):
    scenario = _main_phase({"battlefield": [angel]}, {})
    scenario.game.lose_life("bob", 20)
    scenario.state_based_actions()

    assert not scenario.game.is_in_game("bob")
    assert scenario.game.winner == "alice"


def test_static_covers_poison_and_an_empty_library_too():
    scenario = _main_phase({"battlefield": ["Herald of Eternal Dawn"], "library": []}, {})
    scenario.player("alice").add_counters(Counter.POISON, 12)
    scenario.draw(1, username="alice")
    scenario.state_based_actions()

    assert scenario.game.is_in_game("alice")


def test_the_angel_leaving_lets_the_loss_happen():
    """CR 604.2: the static applies only while its source is on the
    battlefield. Path to Exile removes the Herald; the next check removes
    alice, who has been at 0 life all along."""
    scenario = _main_phase(
        {"battlefield": ["Herald of Eternal Dawn"], "life": 3},
        {"hand": ["Path to Exile"], "battlefield": ["Plains"]},
    )
    scenario.game.lose_life("alice", 3)
    scenario.state_based_actions()
    assert scenario.game.is_in_game("alice")

    herald = scenario.creature("Herald of Eternal Dawn", "alice")
    (plains,) = scenario.untapped_sources("Plains", username="bob")
    scenario.will_take_the_may(False)
    scenario.pass_priority("alice")
    scenario.cast_and_resolve("Path to Exile", plains, username="bob", targets=[herald])
    scenario.state_based_actions()

    assert not scenario.game.is_in_game("alice")
    assert scenario.game.winner == "bob"


def test_losing_all_abilities_ends_the_protection():
    """CR 613 layer 6: Dress Down's "Creatures lose all abilities." strips the
    Angel's static, so nothing stops CR 704.5a any more."""
    scenario = _main_phase(
        {"battlefield": ["Platinum Angel"], "life": 1},
        {"hand": ["Dress Down"], "battlefield": ["Island", "Island"], "library": ["Island"] * 3},
    )
    scenario.game.lose_life("alice", 1)
    scenario.state_based_actions()
    assert scenario.game.is_in_game("alice")

    islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.pass_priority("alice")
    scenario.cast_and_resolve("Dress Down", *islands, username="bob")
    scenario.state_based_actions()

    assert not scenario.game.is_in_game("alice")


def test_static_stops_an_effect_saying_she_loses():
    """CR 104.3e: Summoner's Pact's unpaid trigger with Platinum Angel out."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Summoner's Pact"],
            battlefield=["Platinum Angel"],
            library=["Forest"] * 6,
        )
        .player("bob", library=["Forest"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Summoner's Pact", username="alice")
    scenario.will_pay_the_mana_cost(False, username="alice", source="Summoner's Pact")

    _to_next_turn(scenario)  # bob's turn
    _to_next_turn(scenario)  # alice's turn: the pact trigger resolves in upkeep
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert scenario.game.is_in_game("alice")
    assert "alice" not in scenario.game.losers


def test_static_stops_an_opponent_winning_by_an_effect():
    """CR 104.2b: bob's Helix Pinnacle resolves, but alice's Herald says her
    opponents can't win."""
    scenario = _main_phase(
        {"battlefield": ["Herald of Eternal Dawn"], "library": ["Plains"] * 6},
        {"battlefield": ["Helix Pinnacle"], "library": ["Forest"] * 6},
    )
    scenario.find("Helix Pinnacle", Zone.BATTLEFIELD).add_counters("tower", 100)

    _to_upkeep_of(scenario, "bob")
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert scenario.game.winner is None
    assert not scenario.game.is_over


def test_the_last_player_left_still_wins_against_the_static():
    """CR 104.2a overrides "your opponents can't win the game": alice controls
    the Herald and concedes, and bob wins."""
    scenario = _main_phase({"battlefield": ["Herald of Eternal Dawn"]}, {})

    scenario.game.concede("alice")

    assert scenario.game.winner == "bob"


def test_an_opponent_of_a_static_still_wins_by_an_effect_when_it_is_their_own():
    """The Herald on bob's side does not stop bob's own Helix Pinnacle."""
    scenario = _main_phase(
        {"library": ["Plains"] * 6},
        {"battlefield": ["Helix Pinnacle", "Herald of Eternal Dawn"], "library": ["Forest"] * 6},
    )
    scenario.find("Helix Pinnacle", Zone.BATTLEFIELD).add_counters("tower", 100)

    _to_upkeep_of(scenario, "bob")
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert scenario.game.winner == "bob"


def test_the_lone_cant_lose_half_reads_on_a_second_printing():
    """Lich's Mastery's "You can't lose the game." - the first half alone, no
    "your opponents can't win": she survives ten poison counters, and bob's
    own loss is untouched."""
    scenario = _main_phase({"battlefield": ["Lich's Mastery"]}, {})
    scenario.player("alice").add_counters(Counter.POISON, 10)
    scenario.state_based_actions()

    assert scenario.game.is_in_game("alice")
    assert scenario.game.why_cant_win_the_game("bob") is None

    scenario.player("bob").add_counters(Counter.POISON, 10)
    scenario.state_based_actions()

    assert scenario.game.winner == "alice"
