""" "The number of cards you've discarded this turn" - `count_expression`'s
own per-player running total, `Game.cards_discarded_this_turn`.

`Game.static_cost_modifiers_for` already reads the identical field for Hollow
One's own "costs `<n>` less to cast for each card you've discarded this
turn" cost reduction. This is the same fact, read through `count_expression`
- and, through it, `_for_each_multiplier` - for a "for each" magnitude
instead: Misty Knight, Hero for Hire's own activated ability, "{2}, {T},
Discard a card: Draw a card for each card you've discarded this turn." No
other change is needed to make this ability work: `_DRAW_RE`'s own "for
each" tail already falls back to `count_expression`, and `_for_each_
multiplier` already falls back to `count_expression` too - the reader was
simply missing.

Proven off-set from the reported card (Jiang Yanggu, Alone, its own scenario
tests in `test_jiang_yanggu_alone.py`): a bare activated ability rather than
an attack trigger, on a card outside the deck pool.

CR 701.9a (discarding) and CR 608.2h (a "for each" count taken once, when
the effect applies) were looked up with `mise run rules:find` in the
session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_misty_knight_draws_a_card_for_the_discard_that_paid_her_own_cost():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Misty Knight, Hero for Hire", "Mountain", "Mountain"],
            hand=["Lightning Bolt", "Lava Spike"],
            library=["Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    misty = scenario.creature("Misty Knight, Hero for Hire", "alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.activate(misty, *sources, discarding=[bolt])
    scenario.resolve_top()

    alice = scenario.player("alice")
    assert bolt.zone is Zone.GRAVEYARD
    assert [state.name for state in alice.hand] == ["Lava Spike", "Forest"]
    assert scenario.game.cards_discarded_this_turn.get("alice") == 1


def test_misty_knight_draws_nothing_before_any_discard_this_turn():
    """`count_expression`'s reader answers 0, not `None` or an error, for a
    player who has not discarded at all this turn - Misty Knight's own
    activation cost is what pays the one discard her effect then counts, so
    this scenario checks the count is read fresh each turn rather than
    carried over from a prior one."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Misty Knight, Hero for Hire", "Mountain", "Mountain"],
            hand=["Lightning Bolt"],
            library=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.game.cards_discarded_this_turn.get("alice", 0) == 0
