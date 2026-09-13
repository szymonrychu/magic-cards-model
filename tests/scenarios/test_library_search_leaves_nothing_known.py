"""A library search looks at every card and leaves nobody knowing any of them.

- **CR 701.23a** - "To search for a card in a zone, look at all cards in that
  zone (even if it's a hidden zone) and find a card that matches the given
  description."
- **CR 701.23e** - "If the effect that contains the search instruction doesn't
  also contain instructions to reveal the found card(s), then they're not
  revealed."
- **CR 701.24a** - "To shuffle a library or a face-down pile of cards,
  randomize the cards within it so that no player knows their order."

Everything the searcher saw is shuffled straight away, so `Game.search_library`
records no look: nothing known about any other card changes, and the found
card's only trace is its own public move.

Every CR number above was read in full with `mise run rules:find` in the
session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Game, Zone
from tests.scenarios.harness import Scenario


def known(game: Game, viewer: str) -> list[tuple[str, Zone, int | None, bool]]:
    return [
        (entry.card_name, entry.zone, entry.index_from_top, entry.carried)
        for entry in game.known_to(viewer)
    ]


def test_a_fetchland_search_records_nothing_and_changes_no_one_s_knowledge():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Goblin Guide"])
        .player("bob", library=["Forest", "Plains", "Island"], battlefield=["Flooded Strand"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Goblin Guide", "alice"))
    scenario.resolve_top()
    game = scenario.game
    reveals_before = list(game.reveals)
    alice_before = known(game, "alice")
    bob_before = known(game, "bob")
    assert alice_before == [("Forest", Zone.HAND, None, True)]

    scenario.pass_priority()
    strand = scenario.find("Flooded Strand", Zone.BATTLEFIELD)
    scenario.activate(strand, username="bob")
    scenario.pass_until_resolved()

    plains = scenario.find("Plains", Zone.BATTLEFIELD)
    assert plains.zone is Zone.BATTLEFIELD, "the found card's public move"
    assert game.reveals == reveals_before, "CR 701.23e: the search revealed nothing"
    assert known(game, "alice") == alice_before
    assert known(game, "bob") == bob_before
