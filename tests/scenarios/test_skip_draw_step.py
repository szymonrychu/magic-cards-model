"""A permanent's static "Skip your draw step." (CR 614.10, 614.10a, 500.11).

CR 614.10: "An effect that causes a player to skip an event, step, phase, or
turn is a replacement effect. 'Skip [something]' is the same as 'Instead of
doing [something], do nothing.' Once a step, phase, or turn has started, it can
no longer be skipped - any skip effects will wait until the next occurrence."
CR 614.10a: "Anything scheduled for a skipped step, phase, or turn won't
happen." CR 500.11: "To skip a step, phase, or turn is to proceed past it as
though it didn't exist."

Necrodominance is the card that exposed it; Psychic Possession (an "Enchant
opponent" Aura, Modern-legal, not in any deck) is the second printing that
proves the reader reads the sentence, not the card. The static belongs to the
permanent's *controller*: "your" draw step.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _next_turn(scenario) -> None:
    """Run the rest of this turn out and begin the next one's upkeep."""
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # the new turn's untap step
    scenario.advance()  # its upkeep


def _board(skipper: str = "Necrodominance") -> Scenario:
    return (
        Scenario()
        .player("alice", library=["Plains"] * 10)
        .player("bob", battlefield=[skipper], library=["Island"] * 10)
    )


def test_the_controller_skips_their_draw_step():
    """CR 614.10: bob's draw step is replaced by nothing - no card drawn."""
    scenario = _board().build()
    _next_turn(scenario)  # bob's upkeep
    assert scenario.turn.active_player == "bob"
    hand_before = len(scenario.player("bob").hand)

    scenario.advance()

    assert len(scenario.player("bob").hand) == hand_before
    assert len(scenario.player("bob").library) == 10


def test_the_skipped_step_does_not_happen_at_all():
    """CR 500.11: proceed past it as though it didn't exist - the turn walks
    from upkeep straight into the precombat main phase."""
    scenario = _board().build()
    _next_turn(scenario)

    reached = scenario.advance()

    assert reached is Step.PRECOMBAT_MAIN


def test_the_opponent_still_draws():
    """ "Your draw step" - only the controller's own. Alice draws on her turn."""
    scenario = _board().build()
    _next_turn(scenario)  # bob's upkeep
    _next_turn(scenario)  # alice's upkeep, turn 2 for her
    assert scenario.turn.active_player == "alice"
    before = len(scenario.player("alice").hand)

    scenario.advance()

    assert scenario.step is Step.DRAW
    assert len(scenario.player("alice").hand) == before + 1


def test_the_draw_step_returns_once_the_permanent_is_gone():
    """A static ability only applies while its permanent is on the battlefield
    (CR 611.3a): destroy it and the next draw step is drawn."""
    scenario = _board().build()
    necro = scenario.find("Necrodominance", Zone.BATTLEFIELD)
    scenario.game.destroy(necro)
    _next_turn(scenario)
    before = len(scenario.player("bob").hand)

    scenario.advance()

    assert scenario.step is Step.DRAW
    assert len(scenario.player("bob").hand) == before + 1


def test_the_draw_step_direct_turn_based_action_is_also_skipped():
    """`Game.draw_step`, the turn-based action itself (CR 504.1), refuses to
    draw for a player whose draw step is skipped - a caller walking the pointer
    in by hand gets no card either."""
    scenario = _board().build()
    _next_turn(scenario)
    scenario.turn.advance_to(Step.DRAW)

    drawn = scenario.game.draw_step()

    assert drawn == []


def test_a_second_printing_psychic_possession_skips_its_controllers_draw():
    """Psychic Possession: "Enchant opponent / Skip your draw step. / ..." -
    the same sentence on a different card, so the reader is the template."""
    scenario = _board(skipper="Psychic Possession").build()
    possession = scenario.find("Psychic Possession", Zone.BATTLEFIELD)
    possession.attach_to(scenario.player("alice"))  # enchant opponent
    _next_turn(scenario)
    before = len(scenario.player("bob").hand)

    reached = scenario.advance()

    assert reached is Step.PRECOMBAT_MAIN
    assert len(scenario.player("bob").hand) == before


def test_dragon_appeasement_skips_its_controllers_draw_too():
    """Dragon Appeasement prints the same "Skip your draw step." - a third
    printing the static reader now credits, proven on the board as well."""
    scenario = _board(skipper="Dragon Appeasement").build()
    _next_turn(scenario)
    before = len(scenario.player("bob").hand)

    reached = scenario.advance()

    assert reached is Step.PRECOMBAT_MAIN
    assert len(scenario.player("bob").hand) == before


def test_other_draws_are_untouched():
    """Only the step is skipped; a draw from any other source still happens
    (CR 614.10 replaces the step, not every draw)."""
    scenario = _board().build()
    _next_turn(scenario)
    scenario.advance()  # past the skipped draw step into main
    before = len(scenario.player("bob").hand)

    scenario.draw(1, username="bob")

    assert len(scenario.player("bob").hand) == before + 1


def test_necrodominance_end_step_pays_life_and_draws_that_many():
    """Necrodominance's own replacement for the draw: "At the beginning of your
    end step, you may pay any amount of life. If you do, draw that many
    cards." Paying 3 draws 3."""
    scenario = _board().build()
    _next_turn(scenario)
    scenario.advance()  # main
    scenario.will_pay_life_amount(3)
    scenario.turn.advance_to(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # end step: the trigger
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 17
    assert len(scenario.player("bob").hand) == 3


def test_necrodominance_exiles_what_would_hit_its_controllers_graveyard():
    """ "If a card or token would be put into your graveyard from anywhere,
    exile it instead." - a discard goes to exile."""
    scenario = (
        Scenario()
        .player("alice", library=["Plains"] * 5)
        .player("bob", battlefield=["Necrodominance"], hand=["Island"], library=["Island"] * 5)
    )
    scenario = scenario.build()
    island = scenario.find("Island", Zone.HAND, username="bob")

    scenario.game.discard_cards("bob", [island])

    assert island.zone is Zone.EXILE
