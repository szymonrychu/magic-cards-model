"""Scenario: two players taking turns.

The mechanic is the turn changing hands - who is active, what untaps, what
resets, and what carries over.
"""

from magic_cards_model.machines import Step

from .harness import Scenario


def two_players() -> Scenario:
    return (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Forest", "Mountain"])
        .player("bob", library=["Island"], battlefield=["Island"])
    )


def test_the_turn_passes_from_one_player_to_the_other():
    scenario = two_players().build()
    assert scenario.turn.active_player == "alice"

    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()

    assert scenario.step is Step.UNTAP
    assert scenario.turn.active_player == "bob"
    assert scenario.turn.turn_number == 1, "still the first round of turns"


def test_a_full_round_brings_the_turn_number_up():
    scenario = two_players().build()

    for _ in range(2):
        scenario.turn.advance_to(Step.CLEANUP)
        scenario.advance()

    assert scenario.turn.active_player == "alice"
    assert scenario.turn.turn_number == 2


def test_each_player_untaps_only_their_own_permanents():
    scenario = two_players().build()
    alice_lands = scenario.untapped_sources("Forest", "Mountain", username="alice")
    (bob_island,) = scenario.untapped_sources("Island", username="bob")
    for land in [*alice_lands, bob_island]:
        land.tap()

    # Bob's untap step.
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.game.untap_step()

    assert bob_island.untapped
    assert all(land.tapped for land in alice_lands), "alice's lands are not bob's to untap"


def test_priority_follows_the_active_player_into_the_new_turn():
    """CR 117.3a, and CR 502.4 on the step it is *not* true of.

    A turn does not begin by handing the new active player priority: it begins
    with an untap step, in which "no player receives priority" (CR 502.4). The
    new active player gets it at the beginning of the first step that grants
    any, which is upkeep.
    """
    scenario = two_players().build()
    assert scenario.priority_holder is None, "a game rests at untap (CR 502.4)"
    scenario.start_at(Step.UPKEEP)
    assert scenario.priority_holder == "alice"

    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # bob's untap step

    assert scenario.priority_holder is None
    assert scenario.turn.active_player == "bob"

    scenario.advance()  # bob's upkeep

    assert scenario.priority_holder == "bob"


def test_each_step_hands_priority_back_to_the_active_player():
    scenario = two_players().build()
    scenario.start_at(Step.UPKEEP)
    scenario.pass_priority("alice")
    assert scenario.priority_holder == "bob"

    scenario.advance()  # draw step

    assert scenario.priority_holder == "alice"


def test_the_land_drop_resets_each_turn():
    scenario = (
        Scenario()
        .player("alice", hand=["Forest"], library=["Forest"])
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.play_land("Forest")
    assert not scenario.game.can_play_land("alice")

    # Round the turn back to alice.
    for _ in range(2):
        scenario.turn.advance_to(Step.CLEANUP)
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert scenario.game.can_play_land("alice"), "a new turn is a new land drop"
