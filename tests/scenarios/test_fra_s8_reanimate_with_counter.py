"""FRA stream S8: "Return target `<X>` card [with mana value N or less]
from your graveyard to the battlefield with an additional `<n>` `<kind>`
counter(s) on it." (CR 110.2a, CR 122.1).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 110.2a** - "If an effect instructs a player to put an object onto the
  battlefield, that object enters the battlefield under that player's
  control unless the effect states otherwise."
- **CR 122.1** - a counter modifies a permanent's characteristics; placed as
  the permanent arrives, the same order Neoform's own untargeted rider
  already reads through `_RETURN_CARDS_FROM_YOUR_GRAVEYARD_RE`.

Generous Revival is the reported card, its own "mana value 3 or less" bound
narrowing the target. Prison Break (Spider-Man, real, non-FRA, non-pool) is
the off-set proof: the identical rider with no mana-value bound at all,
exercising the clause with `max_mv` absent rather than present.

Rewrite Regrets' own targeted reanimation clause ("Return target creature or
planeswalker card with mana value 6 or less from your graveyard to the
battlefield.") already reads correctly with the *pre-existing*
`_RETURN_FROM_YOUR_GRAVEYARD_TO_BATTLEFIELD_RE` - no counter rider, no new
code - proven directly below; its own second sentence, Empower Jace 2, is
FRA stream S1's clause and is not on this branch, so the whole two-clause
card still fails closed as a unit until S1 merges, the same "no ordering
dependency" shape every other Empower-paired card in this stream shares.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_generous_revival_returns_a_bounded_creature_with_a_counter():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Generous Revival"],
            battlefield=["Plains", "Plains", "Plains"],
            graveyard=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    casting = scenario.cast("Generous Revival", username="alice")
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.controller == "alice"
    assert bears.counter_count(Counter.PLUS_ONE) == 1


def test_prison_break_reads_the_rider_with_no_mana_value_bound():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Prison Break"],
            battlefield=["Swamp"] * 5,
            graveyard=["Goblin Guide"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", "Swamp")
    goblin = scenario.find("Goblin Guide", Zone.GRAVEYARD, "alice")

    casting = scenario.cast("Prison Break", username="alice")
    casting.choose_targets([goblin])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert goblin.zone is Zone.BATTLEFIELD
    assert goblin.counter_count(Counter.PLUS_ONE) == 1


def test_rewrite_regrets_own_bare_return_clause_reads_with_no_new_code():
    """Proven at the clause level: Empower Jace 2 keeps the whole two-clause
    spell from resolving on this branch (see module docstring)."""
    from magic_cards_model.machines.effects import parse_mixed_effect_for_spell

    effect = parse_mixed_effect_for_spell(
        "Return target creature or planeswalker card with mana value 6 or less "
        "from your graveyard to the battlefield."
    )
    assert effect is not None
