"""Scenario: Summoner's Pact - a free tutor with a delayed cost (CR 603.7):
"At the beginning of your next upkeep, pay {2}{G}{G}. If you don't, you lose
the game."

The rules this file asserts, every one looked up with `knowledge_search(q=...,
type="rules")` in the session that wrote it:

- **CR 603.7** - an effect may create a delayed triggered ability that does
  something later.
- **CR 603.7a** - the ability exists only from the moment it is created.
- **CR 603.7d/e** - the delayed ability's controller is the controller of the
  spell or ability that created it, taken as it resolved.
- **CR 118.12a** - "[Effect] unless [a player does something else]" means
  "[a player] may [do something else]. If [they] don't, [effect]."
- **CR 104.3e** - an effect may state that a player loses the game.
- **CR 104.5** - a player who loses the game leaves the game.
- **CR 104.2a** - in a two-player game, the last player remaining wins once
  the other has left.
- **CR 701.23a/701.23b** - Summoner's Pact's own search is for a stated
  quality (a green creature card), so failing to find remains legal.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from tests.scenarios.harness import Scenario


def pact_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Summoner's Pact"],
            library=["Primeval Titan", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest"] * 6)
    )


def advance_to_next_upkeep_of(scenario, username: str) -> None:
    """Walk the turn forward, resolving whatever is on the stack, until it is
    `username`'s own upkeep step again - CR 503.1's own untap-then-upkeep
    order, driven turn by turn rather than jumped to, since `start_at` never
    performs the turn-based actions or emits the events a delayed trigger
    needs to see.
    """
    seen_other_step = False
    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == username):
        scenario.advance()
        seen_other_step = True
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
    assert seen_other_step


def advance_to_just_before_next_upkeep_of(scenario, username: str) -> None:
    """Stop at the untap step immediately before `username`'s own next
    upkeep - CR 500.4 empties a player's mana pool at the end of every step
    and phase, so a scenario staging floating mana for the delayed trigger's
    own payment has to add it here, not any earlier."""
    while not (scenario.step is Step.UNTAP and scenario.turn.active_player == username):
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


def test_summoners_pact_tutors_for_free():
    scenario = pact_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pact = scenario.cast_and_resolve("Summoner's Pact")

    assert pact.zone is Zone.GRAVEYARD
    alice = scenario.player("alice")
    assert [c.name for c in alice.hand] == ["Primeval Titan"]
    assert alice.mana_pool.total == 0, "cast for {0} - nothing was ever paid up front"


def test_summoners_pact_paid_at_next_upkeep_keeps_the_player_in_the_game():
    scenario = pact_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Summoner's Pact")

    advance_to_just_before_next_upkeep_of(scenario, "alice")
    alice = scenario.player("alice")
    scenario.will_pay_the_mana_cost(True, username="alice", source="Summoner's Pact")
    scenario.advance()  # untap -> upkeep: CR 500.4 empties the pool right here
    alice.mana_pool.add(Color.GREEN, 4)  # staged for the trigger about to resolve
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert scenario.step is Step.UPKEEP
    assert scenario.game.is_in_game("alice")
    assert alice.mana_pool.total == 0, "{2}{G}{G} was spent"
    assert scenario.game.winner is None


def test_summoners_pact_unpaid_loses_the_game():
    scenario = pact_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Summoner's Pact")

    scenario.will_pay_the_mana_cost(False, username="alice", source="Summoner's Pact")
    advance_to_next_upkeep_of(scenario, "alice")

    assert not scenario.game.is_in_game("alice"), "CR 104.3e/104.5"
    assert "alice" in scenario.game.losers
    assert scenario.game.winner == "bob", "CR 104.2a: the last player remaining wins"


def test_summoners_pact_cannot_pay_loses_the_game():
    """An unscripted upkeep, with no mana floating at all: `may_pay_mana_cost`
    refuses the payment as illegal (CR 118.3), same as declining."""
    scenario = pact_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Summoner's Pact")

    advance_to_next_upkeep_of(scenario, "alice")

    assert not scenario.game.is_in_game("alice")
    assert scenario.game.winner == "bob"


def test_summoners_pact_only_watches_its_own_casters_upkeep():
    """ "Your next upkeep" is Summoner's Pact's controller's own next upkeep,
    not the very next upkeep step in the game - bob's own upkeep (the one
    that comes first, in a two-player game) must not fire it."""
    from magic_cards_model.machines.decisions import DecisionKind

    scenario = pact_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Summoner's Pact")

    while scenario.turn.active_player != "bob" or scenario.step is not Step.UPKEEP:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()

    assert scenario.game.is_in_game("alice"), "not alice's own upkeep yet"
    pay_mana_asks = [q for q in scenario.game.decisions.asked if q.kind is DecisionKind.PAY_MANA]
    assert pay_mana_asks == [], "the delayed trigger has not fired yet - bob's upkeep isn't alice's"
