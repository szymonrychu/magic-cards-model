"""Judge scenario: starting a game action you cannot legally finish (DDR#968).

"Winning the Game with an Illegal Play." Amy controls Laboratory Maniac and
Future Sight, has one very expensive card left in her library, and announces
that she is casting it from the top of her library. Announcing moves the card
to the stack, which empties her library; she then activates a mana ability that
makes every player draw; her own draw is replaced by Laboratory Maniac and she
wins - having started a cast she knew she could never pay for.

The episode is mostly policy: is that cheating, what infraction, what fix. Its
answer is that no rule was broken, so nothing is. The IPG half is recorded in
the ledger rather than tested. What *is* testable is the chain of rules the
setup rides on:

- **CR 601.2a** - "To propose the casting of a spell, a player first moves that
  card (or that copy of a card) from where it is to the stack." That is the
  step that empties the library, and it happens before any cost is calculated
  (CR 601.2f) or paid (CR 601.2h).
- **CR 605.1a** - an activated ability is a mana ability if "it doesn't require
  a target ..., it could add mana to a player's mana pool when it resolves,
  it's not a loyalty ability, and it isn't a mana ability with a target" - the
  criteria Salvala's parlay ability meets on a technicality.
- **CR 121.4 / CR 704.5b** - "A player who attempts to draw a card from a
  library with no cards in it loses the game the next time a player would
  receive priority", as a state-based action.
- **CR 733.1** - "If a player takes an illegal action or starts to take an
  action but can't legally complete it, the entire action is reversed and any
  payments already made are canceled", and CR 733.2 hands priority back.

The engine models the loss and the rewind. It does not model CR 601.2a's
ordering: `Casting.cast` leaves the card in its origin zone until the cost is
paid and `put_on_stack` is called, so the library is never emptied *by*
announcing - the exact hinge of the episode. That is the `xfail`.

Every CR number in this file was verified with `knowledge_search(q="...",
type="rules")` in the session that wrote it: CR 121.4, CR 405.1, CR 601.2,
CR 601.2a, CR 605.1a, CR 605.2, CR 704.5b, CR 733.1, CR 733.2.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from


def test_drawing_from_an_empty_library_loses_the_game_at_the_next_check():
    """CR 121.4 and CR 704.5b, which is what Laboratory Maniac replaces.

    The attempt is what matters, not the card: no card is drawn, the attempt is
    remembered, and the state-based action removes the player the next time one
    is checked.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Colossal Dreadmaw"], battlefield=["Forest"])
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.player("alice").library == []

    drawn = scenario.game.draw_cards("alice", 1)

    assert drawn == []
    assert scenario.player("alice").tried_to_draw_from_empty_library
    scenario.game.check_state_based_actions()
    assert scenario.game.losers == ["alice"]


def test_a_cast_that_cannot_be_paid_for_is_refused_rather_than_half_done():
    """CR 733.1: an action a player can't legally complete is reversed.

    One Forest is five mana short of Colossal Dreadmaw. The engine refuses to
    finish the cast rather than putting an unpaid spell on the stack, which is
    the "can't legally complete it" branch of the rule.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Colossal Dreadmaw"], battlefield=["Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Colossal Dreadmaw")
    payment = casting.begin_paying()
    (forest,) = scenario.untapped_sources("Forest")
    payment.tap_for_mana(forest, mana_from(forest))

    with pytest.raises(ValueError, match="before the cost is paid"):
        scenario.put_on_stack(casting)


def test_the_reversal_puts_everything_back_including_the_mana_sources():
    """CR 733.1's second half - "any payments already made are canceled" - and
    CR 733.2's "the player who had priority retains it".

    The Forest is untapped again and alice still holds priority, so she may
    "redo the reversed action in a legal way or take any other action".
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Colossal Dreadmaw"], battlefield=["Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.find("Colossal Dreadmaw", Zone.HAND)
    casting = scenario.cast("Colossal Dreadmaw")
    payment = casting.begin_paying()
    (forest,) = scenario.untapped_sources("Forest")
    payment.tap_for_mana(forest, mana_from(forest))

    casting.cancel()

    assert dreadmaw.zone is Zone.HAND
    assert not forest.tapped
    assert scenario.game.stack_is_empty
    assert scenario.priority_holder == "alice"


def test_announcing_a_cast_moves_the_card_to_the_stack_immediately():
    """CR 601.2a, and CR 405.1: "When a spell is cast, the physical card is put
    on the stack".

    Amy's library is empty from the moment she announces, long before she finds
    out she cannot pay - which is why her draw is a draw from an empty library.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Colossal Dreadmaw"], battlefield=["Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.find("Colossal Dreadmaw", Zone.HAND)

    scenario.cast("Colossal Dreadmaw")

    assert dreadmaw.zone is Zone.STACK
