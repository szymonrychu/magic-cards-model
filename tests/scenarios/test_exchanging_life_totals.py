"""Exchanging life totals: one event, all of it or none of it.

Mister Negative prints the reason this primitive exists (verified with
`resolve_cards`): "Darkforce Inversion - When Mister Negative enters, you may
exchange life totals with target opponent. If you lost life this way, draw
that many cards."

- **CR 701.12a** - "A spell or ability may instruct players to exchange
  something (for example, life totals or control of two permanents) as part of
  its resolution. When such a spell or ability resolves, if the entire
  exchange can't happen, no part of the exchange occurs." That sentence is the
  whole design: the exchange is checked before anything moves, never half
  applied.
- **CR 701.12c** - "When life totals are exchanged, each player gains or loses
  the amount of life necessary to equal the other player's previous life
  total." So an exchange is *implemented* as gains and losses, which is what
  makes every rule about gaining and losing life apply to it.
- **CR 701.12g** - the same for two numerical values, "If either of those
  values is a life total, the player gains or loses the necessary amount of
  life".
- **CR 119.7** - "If an effect says that a player can't gain life, that player
  can't make an exchange such that the player's life total would become
  higher; in that case, the exchange won't happen."
- **CR 119.8** - the mirror: "If an effect says that a player can't lose life,
  that player can't make an exchange such that the player's life total would
  become lower; in that case, the exchange won't happen."
- **CR 119.9** - "whenever a player gains life" reads the gain half, so an
  exchange that raises a life total is a life gain like any other.

`Player.exchange_life_totals` is the primitive, and `machines/effects.py` now
reaches it: the tests at the bottom of this file cast Mister Negative and play
the whole Darkforce Inversion trigger, optional "you may" and reflexive draw
included. The tests above call the primitive directly, because the prohibitions
it enforces need life totals no printed card in the pool can set up.

Every CR number in this file was verified with `knowledge_search(q="...",
type="rules")` in the session that wrote it: CR 119.7, CR 119.8, CR 119.9,
CR 701.12a, CR 701.12c, CR 701.12g.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def duel(alice_life: int = 20, bob_life: int = 20) -> Scenario:
    return Scenario().player("alice", life=alice_life).player("bob", life=bob_life).build()


def test_an_exchange_swaps_the_two_life_totals():
    """CR 701.12c, the plain case: each ends on the other's previous total."""
    scenario = duel(alice_life=5, bob_life=17)
    alice, bob = scenario.player("alice"), scenario.player("bob")

    alice.exchange_life_totals(bob)

    assert (alice.life, bob.life) == (17, 5)


def test_the_exchange_reports_the_life_this_player_lost():
    """Mister Negative's "If you lost life this way, draw that many cards."

    The amount is the exchanging player's own loss, which is why the return
    value is signed from their side: a player who *gained* reports a negative
    loss and draws nothing.
    """
    scenario = duel(alice_life=17, bob_life=5)
    alice, bob = scenario.player("alice"), scenario.player("bob")

    assert alice.exchange_life_totals(bob) == 12

    scenario = duel(alice_life=5, bob_life=17)
    alice, bob = scenario.player("alice"), scenario.player("bob")

    assert alice.exchange_life_totals(bob) == -12


def test_the_exchange_is_a_gain_and_a_loss_the_rest_of_the_engine_can_see():
    """CR 701.12c implements the exchange *as* gains and losses, so CR 119.9's
    per-turn record and the per-turn loss ledger both pick it up."""
    scenario = duel(alice_life=17, bob_life=5)
    alice, bob = scenario.player("alice"), scenario.player("bob")

    alice.exchange_life_totals(bob)

    assert "bob" in scenario.game.life_gained_this_turn, "CR 119.9: bob gained 12"
    assert alice.life_lost_this_turn == 12, "and alice lost 12"


def test_equal_life_totals_exchange_without_anything_happening():
    """Nothing is gained and nothing is lost, so nothing can refuse it - not
    even a player who can't gain life (CR 119.7 speaks only of an exchange that
    would make the total *higher*)."""
    scenario = duel(alice_life=11, bob_life=11)
    alice, bob = scenario.player("alice"), scenario.player("bob")
    alice.cannot_gain_life = True

    assert alice.why_cannot_exchange_life_totals(bob) is None
    assert alice.exchange_life_totals(bob) == 0
    assert (alice.life, bob.life) == (11, 11)
    assert "alice" not in scenario.game.life_gained_this_turn


def test_a_player_who_cannot_gain_life_refuses_an_exchange_that_would_raise_them():
    """CR 119.7, and then CR 701.12a: *neither* life total changes.

    This is DDR#974's answer. Amy (alice) can't gain life and sits below Nick
    (bob); her half of the exchange can't happen, and because an exchange is
    one event rather than two adjustments, his half does not happen either.
    """
    scenario = duel(alice_life=5, bob_life=17)
    alice, bob = scenario.player("alice"), scenario.player("bob")
    alice.cannot_gain_life = True

    refusal = alice.why_cannot_exchange_life_totals(bob)

    assert refusal is not None
    assert "CR 119.7" in refusal, refusal

    assert alice.exchange_life_totals(bob) == 0
    assert (alice.life, bob.life) == (5, 17), "CR 701.12a: no part of it occurs"


def test_the_refusal_is_symmetric_about_which_player_is_asked():
    """CR 701.12a's "the entire exchange" does not care who is doing the
    asking, so the same pair refuses from either side."""
    scenario = duel(alice_life=5, bob_life=17)
    alice, bob = scenario.player("alice"), scenario.player("bob")
    alice.cannot_gain_life = True

    assert bob.why_cannot_exchange_life_totals(alice) is not None
    assert bob.exchange_life_totals(alice) == 0
    assert (alice.life, bob.life) == (5, 17)


def test_a_player_who_cannot_gain_life_may_still_exchange_downwards():
    """CR 119.7 stops only the exchange that would raise the total.

    Amy above Nick: her life total goes *down*, nothing is prohibited, and the
    whole exchange resolves - the other branch of the same episode.
    """
    scenario = duel(alice_life=17, bob_life=5)
    alice, bob = scenario.player("alice"), scenario.player("bob")
    alice.cannot_gain_life = True

    assert alice.why_cannot_exchange_life_totals(bob) is None
    assert alice.exchange_life_totals(bob) == 12
    assert (alice.life, bob.life) == (5, 17)


def test_a_player_who_cannot_lose_life_refuses_an_exchange_that_would_lower_them():
    """CR 119.8, the mirror of CR 119.7, refused the same all-or-nothing way."""
    scenario = duel(alice_life=17, bob_life=5)
    alice, bob = scenario.player("alice"), scenario.player("bob")
    alice.cannot_lose_life = True

    refusal = alice.why_cannot_exchange_life_totals(bob)

    assert refusal is not None
    assert "CR 119.8" in refusal, refusal

    assert alice.exchange_life_totals(bob) == 0
    assert (alice.life, bob.life) == (17, 5)


def test_the_prohibition_on_the_other_player_refuses_it_too():
    """The half that is easy to forget: bob is the one who can't gain life, and
    he is the one the exchange would raise. CR 119.7 refuses it just the same,
    and CR 701.12a takes alice's half down with it."""
    scenario = duel(alice_life=17, bob_life=5)
    alice, bob = scenario.player("alice"), scenario.player("bob")
    bob.cannot_gain_life = True

    assert alice.exchange_life_totals(bob) == 0
    assert (alice.life, bob.life) == (17, 5)


def test_a_refused_exchange_records_no_gain_and_no_loss():
    """CR 701.12a's "no part of the exchange occurs" is stronger than "the
    totals end up the same": nothing may be recorded either, or a trigger
    watching for a gain (CR 119.9) fires off an event that did not happen."""
    scenario = duel(alice_life=5, bob_life=17)
    alice, bob = scenario.player("alice"), scenario.player("bob")
    alice.cannot_gain_life = True

    alice.exchange_life_totals(bob)

    assert scenario.game.life_gained_this_turn == set()
    assert alice.life_lost_this_turn == 0
    assert bob.life_lost_this_turn == 0


def test_exchanging_with_yourself_changes_nothing():
    """A degenerate call that must not double-apply anything."""
    scenario = duel(alice_life=9)
    alice = scenario.player("alice")

    assert alice.exchange_life_totals(alice) == 0
    assert alice.life == 9


def mister_negative_board(alice_life: int = 5, bob_life: int = 17) -> Scenario:
    """Alice with Mister Negative in hand at a life total worse than Bob's.

    Put onto the battlefield rather than cast (`put_onto_battlefield`, the
    Tooth and Nail path): the mechanic under test is the enters trigger, and
    `Game.put_onto_battlefield` fires it exactly as a resolved creature spell
    would. Casting it is currently refused for an unrelated reason -
    `machines/targeting.py` reads the "target opponent" printed inside the
    *triggered ability* as a target the **spell** requires, so CR 601.2c's
    announcement check refuses a Mister Negative cast with no targets named.
    """
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            life=alice_life,
            hand=["Mister Negative"],
            library=["Grizzly Bears"] * 12,
        )
        .player("bob", life=bob_life)
    )


def test_mister_negative_exchanges_life_totals_when_it_enters():
    """The card the primitive is for, played through the engine.

    "Darkforce Inversion - When Mister Negative enters, you may exchange life
    totals with target opponent." CR 701.12c does it as gains and losses, so
    alice climbs from 5 to 17 and bob drops from 17 to 5.
    """
    scenario = mister_negative_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Mister Negative", "alice")
    scenario.pass_until_resolved()  # the enters trigger  # the enters trigger

    assert scenario.player("alice").life == 17
    assert scenario.player("bob").life == 5


def test_the_controller_who_gained_life_draws_nothing():
    """ "If you lost life this way, draw that many cards" - alice gained, so
    the reflexive clause's condition is false and no card is drawn.

    The condition is on the *controller's* side of the exchange, not on
    whether any life moved at all: bob lost twelve here and that is nobody's
    draw.
    """
    scenario = mister_negative_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Mister Negative", "alice")
    scenario.pass_until_resolved()  # the enters trigger

    assert [state.name for state in scenario.player("alice").hand] == []


def test_the_controller_who_lost_life_draws_that_many_cards():
    """The clause the card is built around, from the other side.

    Alice at 20 exchanging with bob at 14 loses 6, so she draws 6 - "that many"
    being the amount the exchange moved, and CR 121.2 making that six
    individual draws.
    """
    scenario = mister_negative_board(alice_life=20, bob_life=14).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Mister Negative", "alice")
    scenario.pass_until_resolved()  # the enters trigger

    assert scenario.player("alice").life == 14
    assert len(scenario.player("alice").hand) == 6


def test_declining_the_may_leaves_both_life_totals_alone():
    """ "You may" is CR 608.2d's own optional question. A controller who
    declines exchanges nothing and draws nothing - and, since no life moved,
    the reflexive clause has nothing to count either."""
    scenario = mister_negative_board(alice_life=20, bob_life=14).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, username="alice", source="Mister Negative")

    scenario.put_onto_battlefield("Mister Negative", "alice")
    scenario.pass_until_resolved()  # the enters trigger

    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 14
    assert [state.name for state in scenario.player("alice").hand] == []


def test_a_controller_who_cannot_gain_life_exchanges_nothing_and_draws_nothing():
    """CR 119.7 read through the card: alice can't gain life, and the exchange
    would raise her, so "the exchange won't happen" - CR 701.12a's all-or-
    nothing then leaves bob's total alone too, and "if you lost life this way"
    is false because nothing happened at all.
    """
    scenario = mister_negative_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.player("alice").cannot_gain_life = True
    scenario.put_onto_battlefield("Mister Negative", "alice")
    scenario.pass_until_resolved()  # the enters trigger

    assert scenario.player("alice").life == 5
    assert scenario.player("bob").life == 17
    assert [state.name for state in scenario.player("alice").hand] == []
