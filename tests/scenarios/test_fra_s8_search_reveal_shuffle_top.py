"""FRA stream S8: the "Search your library for `<quality>` card, reveal it,
then shuffle and put that card on top." tutor family (CR 701.23, CR 701.24a,
CR 701.20d).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 701.23a** - "find a card that matches the given description."
- **CR 701.23b** - a stated-quality search is declinable.
- **CR 701.20a/701.20b** - revealing shows the card without moving it.
- **CR 701.24a** - the library is shuffled after the search.
- **CR 701.20d/CR 401.2** - a card put on top sits above every card already
  there.

Loyal Tutor is the reported card. Enlightened Tutor is the off-set proof: a
real, iconic, non-FRA, non-pool printing of the identical shape, naming a
disjunctive quality ("an artifact or enchantment card") rather than Loyal
Tutor's single "planeswalker", exercising `_search_descriptions`'s own "or"
join through this new destination.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_loyal_tutor_puts_the_found_planeswalker_on_top_of_a_shuffled_library():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Loyal Tutor"],
            battlefield=["Plains"],
            library=["Ajani Unrelenting", "Forest", "Mountain", "Swamp", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    (plains,) = scenario.untapped_sources("Plains")
    ajani = next(state for state in alice.library if state.name == "Ajani Unrelenting")

    scenario.will_choose_cards(ajani, username="alice")
    scenario.cast_and_resolve("Loyal Tutor", plains)

    assert alice.library[0] is ajani
    assert len(alice.library) == 5
    (reveal,) = [r for r in scenario.game.reveals if r.card_name == "Ajani Unrelenting"]
    assert reveal.zone is Zone.LIBRARY


def test_enlightened_tutor_reads_the_disjunctive_quality():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Enlightened Tutor"],
            battlefield=["Plains"],
            library=["Sol Ring", "Forest", "Mountain", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    (plains,) = scenario.untapped_sources("Plains")
    sol_ring = next(state for state in alice.library if state.name == "Sol Ring")

    scenario.will_choose_cards(sol_ring, username="alice")
    scenario.cast_and_resolve("Enlightened Tutor", plains)

    assert alice.library[0] is sol_ring
    assert len(alice.library) == 4
