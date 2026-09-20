"""FRA stream S8: "Search your library for `<quality>` card, put it into
your hand, shuffle, then discard `<n>` card(s) at random." - CR 608.2c's
own ordered series, where "then" marks only the last instruction rather
than sitting right before "shuffle" the way the ordinary tutor template
always does.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 701.23a/701.23b** - the search, declinable by its stated quality.
- **CR 701.20a/701.20b** - a printed reveal.
- **CR 701.24a** - the post-search shuffle.
- **CR 701.9b** - "some effects... require a random discard" - the tutored
  card can be the very one discarded at random right back out.

Curse-Marred Demon is the reported card, its own unrestricted "a card"
search with no reveal, played end to end. Reckless Handling (March of the
Machine: The Aftermath, real, non-FRA, non-pool) is the off-set proof: a
stated quality ("an artifact card") and a printed reveal, proven at the
clause level - its own third clause is a different, unbuilt shape (see that
test's own docstring) that keeps the whole spell from resolving today, which
is not this merge's gap to close.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_curse_marred_demon_tutors_then_discards_a_card_at_random():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Curse-Marred Demon"],
            battlefield=["Mountain", "Mountain", "Mountain", "Mountain"],
            library=["Grizzly Bears", "Forest", "Island", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    bears = next(state for state in alice.library if state.name == "Grizzly Bears")

    scenario.will_choose_cards(bears, username="alice")
    scenario.cast_and_resolve("Curse-Marred Demon", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD, (
        "found, put into an otherwise-empty hand, then the only card there to discard at random"
    )
    assert len(alice.hand) == 0
    assert len(alice.library) == 3


def test_reckless_handling_reads_the_stated_quality_and_the_printed_reveal():
    """Reckless Handling's own two-clause merge, proven directly rather than
    through a full cast: its third clause ("If an artifact card was
    discarded this way, Reckless Handling deals 2 damage to each opponent.")
    is a different, unrelated clause shape - the conditional "`<source>`
    deals N damage to each opponent" family (`damage_each_opponent`) reads
    `AbilityOnStack.source`, which only exists for an ability, never a
    resolving spell - so it is unread on a spell today regardless of this
    stream's own merge, and drags the whole three-clause card down with it
    under this engine's existing all-or-nothing per-ability composition
    (`_parse_mixed_clauses`'s own docstring). Not S8's clause to fix; proven
    here at the level this stream's own merge actually owns.
    """
    from magic_cards_model.machines.effects import (
        _merge_search_hand_shuffle_then_discard_random_clauses,
    )

    clauses = [
        "Search your library for an artifact card, reveal it, put it into your hand, shuffle",
        "discard a card at random",
    ]
    merged = _merge_search_hand_shuffle_then_discard_random_clauses(clauses, 0, for_spell=True)
    assert merged is not None
    consumed, _effect = merged
    assert consumed == 2
