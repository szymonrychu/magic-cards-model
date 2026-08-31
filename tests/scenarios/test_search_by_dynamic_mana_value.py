"""Scenario: a library search bounded by a *live board count* rather than a
printed number - Beseech the Queen's "Search your library for a card with
mana value less than or equal to the number of lands you control, reveal it,
put it into your hand, then shuffle."

`_SEARCH_AND_PUT_RE` in `machines/effects.py` already reads "with mana value
N or less" (Ranger-Captain of Eos's own bound), but only as a literal digit -
its `max_mv` group is `\\d+`. Beseech the Queen's own ceiling is not a number
printed on the card at all; it is `count_expression`'s "the number of <type>
you control" shape (already built for Craterhoof Behemoth's own team-wide
pump), read here for the first time as a search's own bound
(`_parse_search_mv_lte_count_clause`, `_SEARCH_MV_LTE_COUNT_RE`).

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 701.23a** - "To search for a card in a zone, look at all cards in that
  zone (even if it's a hidden zone) and find a card that matches the given
  description."
- **CR 701.23b** - a search for a stated quality "isn't required to find some
  or all of those cards even if they're present in that zone" - the ceiling
  is part of the stated quality here, the same as a printed mana-value bound.
- **CR 701.24a/701.24b** - the post-search shuffle, and the found card is not
  part of what gets shuffled.
- **CR 202.3** - mana value, the number being compared.
- **CR 613.5** - "you control" is read off the current board, the same
  correction `count_expression`'s other reader (Craterhoof's team pump)
  already applies.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def test_beseech_the_queen_finds_a_card_at_or_under_the_land_count():
    """Three Swamps: the ceiling is 3. Lightning Bolt (mana value 1) is a
    legal find; Doubling Season (mana value 5) is not, and is left behind.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Beseech the Queen"],
            library=["Lightning Bolt", "Doubling Season"],
            battlefield=["Swamp", "Swamp", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")

    scenario.cast_and_resolve("Beseech the Queen", *sources)

    assert [state.name for state in alice.hand] == ["Lightning Bolt"]
    assert [state.name for state in alice.library] == ["Doubling Season"]


def test_beseech_the_queen_finds_nothing_over_the_land_count():
    """Three Swamps: the ceiling is still 3, but the only card in the library
    is Doubling Season at mana value 5 - no legal find at all, so the search
    comes up empty (CR 701.23b) and the library is merely shuffled, not
    emptied by force.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Beseech the Queen"],
            library=["Doubling Season"],
            battlefield=["Swamp", "Swamp", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")

    scenario.cast_and_resolve("Beseech the Queen", *sources)

    assert alice.hand == []
    assert [state.name for state in alice.library] == ["Doubling Season"]
