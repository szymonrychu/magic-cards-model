"""Scenario: "Take <N> extra turn(s) after this one." (CR 500.7).

CR 500.7, read whole with `mise run rules:find 500.7` this session: "Some
effects can give a player extra turns. They do this by adding the turns
directly after the specified turn. If a player is given multiple extra turns,
the extra turns are added one at a time. If multiple players are given extra
turns, the extra turns are added one at a time, in APNAP order (see rule
101.4). The most recently created turn will be taken first."

Teferi, Master of Time's "-10: Take two extra turns after this one." is the
reported card. The reader is the clause, not the card: Teferi, Timebender's
"-9: Take an extra turn after this one." (a count of one, a different
loyalty cost) and Savor the Moment's "Take an extra turn after this one. Skip
the untap step of that turn." (a spell, with a second clause) resolve through
the same clause parser - Savor's old card-name row in `EFFECTS` is gone.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import EFFECTS, parse_clause_effect
from magic_cards_model.models import Zone

from .harness import Scenario

MASTER = "Teferi, Master of Time"
TIMEBENDER = "Teferi, Timebender"


def _to_turn_of_next(scenario) -> str:
    """Advance into the next turn, and say whose it is."""
    scenario.advance()
    while scenario.step is not Step.UPKEEP:
        scenario.advance()
    return scenario.turn.active_player


def _board(*alice_battlefield: str, hand: tuple[str, ...] = ()) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Island"] * 10,
            hand=list(hand),
            battlefield=list(alice_battlefield),
        )
        .player("bob", library=["Forest"] * 10)
    )


def _ultimate(scenario, source, index: int) -> None:
    scenario.activate(source, index=index, username="alice")
    scenario.resolve_top()


def test_teferi_takes_two_extra_turns_one_after_the_other():
    scenario = _board(MASTER).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    teferi = scenario.creature(MASTER, "alice")
    scenario.game.add_counters(teferi, "loyalty", 7)
    assert teferi.loyalty == 10

    _ultimate(scenario, teferi, 2)

    assert scenario.turn.extra_turns == ["alice", "alice"]
    assert teferi.zone is Zone.GRAVEYARD, "0 loyalty: CR 704.5i"

    assert _to_turn_of_next(scenario) == "alice"
    assert scenario.turn.taking_extra_turn
    assert _to_turn_of_next(scenario) == "alice"
    assert scenario.turn.taking_extra_turn
    assert _to_turn_of_next(scenario) == "bob"
    assert not scenario.turn.taking_extra_turn
    assert _to_turn_of_next(scenario) == "alice"
    assert not scenario.turn.taking_extra_turn


def test_the_extra_turns_come_after_the_turn_they_were_created_in():
    """Activated on bob's turn through Teferi's own any-turn static, "after
    this one" is after *bob's* turn: bob finishes, alice takes her two extra
    turns, then her own ordinary turn, then bob's - an extra turn is an
    insertion and leaves the rotation untouched (CR 500.7)."""
    scenario = _board(MASTER).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    teferi = scenario.creature(MASTER, "alice")
    scenario.game.add_counters(teferi, "loyalty", 7)
    assert _to_turn_of_next(scenario) == "bob"
    scenario.pass_priority("bob")

    _ultimate(scenario, teferi, 2)

    assert scenario.turn.active_player == "bob"
    order = [_to_turn_of_next(scenario) for _ in range(4)]
    assert order == ["alice", "alice", "alice", "bob"]


def test_an_extra_turn_already_queued_is_taken_after_the_two_new_ones():
    """CR 500.7: "The most recently created turn will be taken first" - a
    Timebender turn created first sits under Master's two."""
    scenario = _board(MASTER, TIMEBENDER).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    master = scenario.creature(MASTER, "alice")
    timebender = scenario.creature(TIMEBENDER, "alice")
    scenario.game.add_counters(master, "loyalty", 7)
    scenario.game.add_counters(timebender, "loyalty", 5)

    _ultimate(scenario, timebender, 2)
    assert scenario.turn.extra_turns == ["alice"]
    _ultimate(scenario, master, 2)
    assert scenario.turn.extra_turns == ["alice", "alice", "alice"]

    order = [_to_turn_of_next(scenario) for _ in range(4)]
    assert order == ["alice", "alice", "alice", "bob"]


def test_teferi_timebender_takes_exactly_one():
    """The second printing: a count of one, read by the same clause."""
    scenario = _board(TIMEBENDER).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    timebender = scenario.creature(TIMEBENDER, "alice")
    scenario.game.add_counters(timebender, "loyalty", 5)

    _ultimate(scenario, timebender, 2)

    assert scenario.turn.extra_turns == ["alice"]
    assert _to_turn_of_next(scenario) == "alice"
    assert _to_turn_of_next(scenario) == "bob"


def test_savor_the_moment_is_read_by_the_clause_parser_not_a_name_row():
    assert "Savor the Moment" not in EFFECTS
    assert parse_clause_effect("Take an extra turn after this one") is not None
    assert parse_clause_effect("Take two extra turns after this one") is not None
    assert parse_clause_effect("Skip the untap step of that turn") is not None


def test_savor_the_moment_still_grants_the_turn_and_skips_its_untap_step():
    scenario = _board("Island", "Island", "Island", "Forest", hand=("Savor the Moment",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    islands = scenario.untapped_sources("Island", "Island", "Island", username="alice")
    scenario.cast_and_resolve("Savor the Moment", *islands)

    assert scenario.turn.extra_turns == ["alice"]
    assert scenario.game.players_skipping_next_untap["alice"] == 1

    assert _to_turn_of_next(scenario) == "alice"
    assert all(island.tapped for island in islands), "CR 614.10: the untap step was skipped"
    assert _to_turn_of_next(scenario) == "bob"


def test_a_player_who_leaves_takes_none_of_their_queued_extra_turns():
    scenario = (
        Scenario()
        .player("alice", library=["Island"] * 10, battlefield=[MASTER])
        .player("bob", library=["Forest"] * 10)
        .player("carol", library=["Swamp"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    teferi = scenario.creature(MASTER, "alice")
    scenario.game.add_counters(teferi, "loyalty", 7)
    _ultimate(scenario, teferi, 2)
    assert scenario.turn.extra_turns == ["alice", "alice"]

    scenario.game.concede("alice")

    assert scenario.turn.extra_turns == []
