"""Scenario: extra turns (CR 500.7).

The whole rule, read this session:

    "Some effects can give a player extra turns. They do this by adding the
    turns directly after the specified turn. If a player is given multiple extra
    turns, the extra turns are added one at a time. If multiple players are
    given extra turns, the extra turns are added one at a time, in APNAP order
    (see rule 101.4). The most recently created turn will be taken first."

So an extra turn is an insertion, not a reshuffle: whoever's seat was next is
still next once the extra turn is over, and several of them come off
last-created-first.

Emrakul, the Promised End needs this half of the card as much as the control
half - "After that turn, that player takes an extra turn" is the compensation
for the turn it took away. `Savor the Moment` is the plain version of the same
effect and is in the pool, which is why it appears here.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.turn import TurnMachine
from magic_cards_model.models import Zone

from .harness import Scenario


def two_players() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Forest"], battlefield=["Forest", "Mountain"])
        .player("bob", library=["Island"], battlefield=["Island"])
    )


def three_players() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Forest"], battlefield=["Forest"])
        .player("bob", library=["Island"], battlefield=["Island"])
        .player("carol", library=["Swamp"], battlefield=["Swamp"])
    )


def next_turn(scenario) -> None:
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()


def test_an_extra_turn_is_taken_directly_after_the_current_one():
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.grant_extra_turn("alice")

    next_turn(scenario)

    assert scenario.turn.active_player == "alice", "alice again, not bob"
    assert scenario.turn.taking_extra_turn


def test_the_ordinary_order_resumes_once_the_extra_turn_is_over():
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.grant_extra_turn("alice")

    next_turn(scenario)  # alice's extra turn
    next_turn(scenario)  # bob's turn, as it would have been

    assert scenario.turn.active_player == "bob"
    assert not scenario.turn.taking_extra_turn


def test_an_extra_turn_does_not_advance_the_round_of_the_table():
    """`turn_number` counts rounds, and an extra turn completes none of one."""
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.grant_extra_turn("alice")

    assert scenario.turn.turn_number == 1
    next_turn(scenario)
    assert scenario.turn.turn_number == 1, "still alice, still round one"
    assert scenario.turn.turns_taken == 2, "but a second turn has begun"


def test_the_extra_turn_untaps_and_resets_the_land_drop():
    """It is a whole turn, not a phase: everything a new turn does happens."""
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.grant_extra_turn("alice")

    lands = scenario.untapped_sources("Forest", "Mountain", username="alice")
    for land in lands:
        land.tap()
    scenario.game.lands_played["alice"] = 1
    assert not scenario.game.can_play_land("alice")

    next_turn(scenario)
    scenario.game.untap_step()
    scenario.turn.advance_to(Step.PRECOMBAT_MAIN)

    assert all(land.untapped for land in lands)
    assert scenario.game.can_play_land("alice")


def test_the_most_recently_created_extra_turn_is_taken_first():
    """CR 500.7: "The most recently created turn will be taken first"."""
    scenario = three_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.grant_extra_turn("bob")
    scenario.game.grant_extra_turn("carol")

    next_turn(scenario)
    assert scenario.turn.active_player == "carol", "the last one created"

    next_turn(scenario)
    assert scenario.turn.active_player == "bob", "then the earlier one"

    next_turn(scenario)
    assert scenario.turn.active_player == "bob", "and then the seat that was next anyway"


def test_two_extra_turns_for_one_player_are_both_taken():
    """CR 500.7: they are "added one at a time", so two of them is two turns."""
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.grant_extra_turn("alice")
    scenario.game.grant_extra_turn("alice")

    next_turn(scenario)
    assert scenario.turn.active_player == "alice"
    next_turn(scenario)
    assert scenario.turn.active_player == "alice"
    next_turn(scenario)
    assert scenario.turn.active_player == "bob"


def test_an_extra_turn_for_a_player_who_has_left_is_skipped():
    """CR 800.4: they are not at the table any more, so the turn is not taken."""
    scenario = three_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.grant_extra_turn("carol")

    scenario.game.concede("carol")

    next_turn(scenario)
    assert scenario.turn.active_player == "bob", "carol's extra turn left with her"


def test_granting_an_extra_turn_to_a_stranger_is_an_error():
    scenario = two_players().build()

    with pytest.raises(KeyError):
        scenario.game.grant_extra_turn("mallory")


def test_the_extra_turn_and_the_control_effect_stack_up_the_way_emrakul_reads():
    """Emrakul's trigger in full: bob's next turn is alice's to play, then bob
    takes an extra turn of his own (CR 723.1, CR 500.7).

    The two halves are created at different moments, and CR 500.7's "directly
    after the specified turn" is why that matters. "You gain control of target
    opponent during that player's next turn" is created when the trigger
    resolves; "After that turn, that player takes an extra turn" names the
    controlled turn, so the extra turn is added *after* that turn, not after the
    one Emrakul was cast on. Granting it early would put bob's extra turn before
    the turn alice was going to steal, and hand it to alice.

    Nothing fires the second half on its own: it is a delayed triggered ability
    (CR 603.7), which is not modelled, so the scenario grants it at the right
    moment - the same way scenarios drive the combat turn-based actions.
    """
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.gain_control_of_player("alice", "bob")

    next_turn(scenario)
    assert scenario.turn.active_player == "bob"
    assert scenario.game.controller_of_player("bob") == "alice", "the turn alice steals"

    scenario.game.grant_extra_turn("bob")  # "After that turn"

    next_turn(scenario)
    assert scenario.turn.active_player == "bob", "the extra turn that gives it back"
    assert scenario.game.controller_of_player("bob") == "bob", "and bob plays this one"

    next_turn(scenario)
    assert scenario.turn.active_player == "alice", "the table picks up where it left off"


# -- the machine on its own -------------------------------------------------


def test_the_queue_is_taken_from_the_end():
    machine = TurnMachine(players=["alice", "bob"])
    machine.grant_extra_turn("alice")
    machine.grant_extra_turn("bob")

    machine.begin_next_turn()
    assert machine.active_player == "bob"
    machine.begin_next_turn()
    assert machine.active_player == "alice"
    assert machine.extra_turns == []


# -- what the card itself still cannot do -----------------------------------


def test_savor_the_moment_grants_its_extra_turn_when_it_resolves():
    """CR 500.7 through a real card: "Take an extra turn after this one".

    The second sentence, "Skip the untap step of that turn", is a replacement
    effect (CR 614.10) and is covered by the test below.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Savor the Moment"],
            battlefield=["Island", "Island", "Island"],
        )
        .player("bob", library=["Island"], battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island", "Island", "Island")
    spell = scenario.cast_and_resolve("Savor the Moment", *sources)

    assert spell.zone is Zone.GRAVEYARD
    assert scenario.turn.extra_turns == ["alice"]


def test_an_extra_turn_can_come_with_its_untap_step_skipped():
    """Savor the Moment's second sentence, through the real card and the real
    untap step.

    CR 614.10: "An effect that causes a player to skip an event, step, phase,
    or turn is a replacement effect. 'Skip [something]' is the same as 'Instead
    of doing [something], do nothing.'" CR 500.11: "To skip a step, phase, or
    turn is to proceed past it as though it didn't exist."

    The earlier version of this test asserted `scenario.turn.skips_untap = True`,
    an attribute nothing has ever written, and reached the next turn without
    ever running an untap step - so it would have passed however the engine
    behaved. `Game.players_skipping_next_untap` is the real API, and
    `Game.untap_step` is what has to be called for the skip to mean anything.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Forest"],
            hand=["Savor the Moment"],
            battlefield=["Forest", "Mountain", "Island", "Island", "Island"],
        )
        .player("bob", library=["Island"], battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    islands = scenario.untapped_sources("Island", "Island", "Island", username="alice")
    scenario.cast_and_resolve("Savor the Moment", *islands)

    assert scenario.turn.extra_turns == ["alice"]
    assert scenario.game.players_skipping_next_untap["alice"] == 1

    lands = scenario.untapped_sources("Forest", "Mountain", username="alice")
    for land in lands:
        land.tap()

    next_turn(scenario)  # alice's extra turn begins
    assert scenario.turn.active_player == "alice"
    scenario.game.untap_step()

    assert all(land.tapped for land in lands), "CR 614.10: the untap step did nothing"
    assert "alice" not in scenario.game.players_skipping_next_untap, "the skip was one turn only"

    # And the turn after it untaps normally - CR 614.10a's skip is spent.
    next_turn(scenario)  # bob's turn
    next_turn(scenario)  # alice again, no skip pending
    scenario.game.untap_step()
    assert all(not land.tapped for land in lands)
