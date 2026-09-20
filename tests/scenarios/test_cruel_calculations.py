"""Cruel Calculations: "Draw X cards, where X is the number of cards that
were put into target player's graveyard from their library this turn."

The magnitude is fixed against the spell's own single *target* player's
history, not the caster's - unlike every `count_expression` "you"/
`controller` reader in the pool, so this is its own dedicated whole-text
parser (`_parse_draw_x_from_target_graveyard_from_library_clause`) rather
than a new `count_expression` term. `Game.cards_put_into_graveyard_this_
turn`'s own `from_zone=Zone.LIBRARY` filter already existed (built for CR
700.11's Descend alongside its `permanent_only` half) but had no caller
reading the `from_zone` half at all until now.

Every rule below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 608.2h** - "If an effect requires information from the game ..., the
  answer is determined only once, when the effect is applied" - X is read
  once, as Cruel Calculations resolves, not when it was cast or targeted.
- **CR 400.6** - "put into a graveyard" (the ledger `graveyard_arrivals_
  this_turn` records one entry per arrival for).
- **CR 120.3** - drawing more cards than remain in a library does not lose
  the game by itself; it draws as many as there are (CR 104.3c is the
  state-based action, not this draw).
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def test_draws_a_card_for_each_card_milled_into_the_targets_graveyard_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cruel Calculations", "Mind Sculpt"],
            battlefield=["Island"] * 6,
            library=["Island"] * 10,
        )
        .player("bob", library=["Forest"] * 7)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mill_sources = scenario.untapped_sources("Island", "Island")
    scenario.cast_and_resolve("Mind Sculpt", *mill_sources, targets=["bob"])
    assert len(scenario.player("bob").graveyard) == 7

    draw_sources = scenario.untapped_sources("Island", "Island", "Island")
    scenario.cast_and_resolve("Cruel Calculations", *draw_sources, targets=["bob"])

    assert len(scenario.player("alice").hand) == 7


def test_draws_nothing_when_the_target_has_not_milled_a_library_card_this_turn():
    """Zero, not an error and not a guess - CR 107.2's "a number that can't
    be determined" default. Off-set from the milling case: bob's graveyard
    holds a discarded card, not one milled from his library, so it does not
    count toward this specific "from their library" phrase at all."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cruel Calculations"],
            battlefield=["Island"] * 3,
            library=["Island"] * 5,
        )
        .player("bob", hand=["Mountain"], library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    scenario.game.discard_cards("bob", [bob.hand[0]], source="test")
    assert len(bob.graveyard) == 1

    draw_sources = scenario.untapped_sources("Island", "Island", "Island")
    scenario.cast_and_resolve("Cruel Calculations", *draw_sources, targets=["bob"])

    assert scenario.player("alice").hand == []


def test_draws_up_to_the_targets_own_mill_count_even_past_the_casters_library():
    """CR 120.3: drawing more than a library holds draws as many as there
    are, rather than failing the spell or drawing a guessed amount."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cruel Calculations", "Mind Sculpt"],
            battlefield=["Island"] * 6,
            library=["Island", "Island"],
        )
        .player("bob", library=["Forest"] * 7)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mill_sources = scenario.untapped_sources("Island", "Island")
    scenario.cast_and_resolve("Mind Sculpt", *mill_sources, targets=["bob"])

    draw_sources = scenario.untapped_sources("Island", "Island", "Island")
    scenario.cast_and_resolve("Cruel Calculations", *draw_sources, targets=["bob"])

    assert len(scenario.player("alice").hand) == 2
