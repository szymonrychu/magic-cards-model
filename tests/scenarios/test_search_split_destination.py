"""A fifth `_SEARCH_AND_PUT_RE` destination: "Search your library for [up
to] two `<quality>` cards[, reveal them,] put one `<dest>` and the other
`<dest>`[, then shuffle]." - Troop of Ponies' own activated ability: "{2},
{T}, Sacrifice this creature: Search your library for up to two basic land
cards, reveal them, put one onto the battlefield tapped and the other into
your hand, then shuffle."

`_SEARCH_AND_PUT_RE` only ever names one destination for the whole find.
This shape is the identical CR 701.23a search - one instruction, finding
`count` cards at once - with the two found cards split across two named
destinations rather than sent to the same one. `_parse_search_split_
destination_clause`/`_SEARCH_SPLIT_DESTINATION_RE` is a new reader built
with the same quality/basic-land-type/mana-value/mana-cost/having/reveal
group names `_SEARCH_AND_PUT_RE` already uses, so `_search_descriptions`
(unchanged) reads this match exactly the way it reads that one - the only
new code is what happens to the two found cards, not how the quality is
read.

`_CLAUSE_SEPARATOR`'s bare " and " between "put one ... tapped" and "the
other ... hand" would otherwise cut this into a verbless fragment neither
`_parse_mixed_clause` nor any earlier reader could parse alone, so the
reader is registered as a whole-text special case in `_parse_mixed_clauses`
(ahead of the ordinary per-clause split) the same way `_parse_search_
reveal_shuffle_top_clause` already is for its own bare-"and".

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 701.23a** - "To search for a card in a zone ... find a card that
  matches the given description" - one search, one choice over every
  candidate at once.
- **CR 701.23b** - a stated-quality search is declinable; finding fewer than
  the ceiling is a legal answer.
- **CR 701.20a** - "reveal them" records both finds without moving either.
- **CR 701.24a** - the shuffle happens to the remaining library once both
  finds are already out of it.
- **CR 305.1** - a land put onto the battlefield this way is not played, so
  it does not count against the turn's own land drop.

Proof printing: **Cultivate** (real Scryfall data, added with `scripts/
add_card.py`, not a listed card, not in any `magic-cards-model-api/decks/
*.txt` list, Modern and Pioneer both `legal`) - a spell rather than an
activated ability, over "up to two basic land cards" with no quantity limit
narrower than Troop of Ponies' own, and a different reveal pronoun ("reveal
those cards" rather than "reveal them") the shared `_SEARCH_AND_PUT_RE`
reveal group already accepts either way.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_troop_of_ponies_splits_two_basic_lands_across_battlefield_and_hand():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Troop of Ponies", "Forest", "Forest"],
            library=["Mountain", "Forest", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    pony = scenario.creature("Troop of Ponies", "alice")
    mountain = next(state for state in alice.library if state.name == "Mountain")
    forest = next(state for state in alice.library if state.name == "Forest")
    sources = scenario.untapped_sources("Forest", "Forest")

    # CR 701.23b's own declinable search asks first (find both lands, decline
    # none), then the split itself asks which of the two found lands goes
    # onto the battlefield - the other falls to hand. Both questions share
    # the same printed source, so each gets its own queued answer, taken in
    # order.
    scenario.will_choose_cards(mountain, forest, username="alice", source="Troop of Ponies")
    scenario.will_choose_cards(mountain, username="alice", source="Troop of Ponies")
    scenario.activate(pony, *sources, sacrificing=[pony])
    scenario.pass_until_resolved()

    assert mountain.zone is Zone.BATTLEFIELD
    assert mountain.tapped
    assert mountain.controller == "alice"
    assert forest.zone is Zone.HAND
    assert pony.zone is Zone.GRAVEYARD


def test_cultivate_reads_the_same_split_destination_template():
    """Proof card: a spell rather than an activated ability, "reveal those
    cards" rather than "reveal them"."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Cultivate"],
            battlefield=["Forest", "Forest", "Forest"],
            library=["Mountain", "Island", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    mountain = next(state for state in alice.library if state.name == "Mountain")
    island = next(state for state in alice.library if state.name == "Island")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")

    scenario.will_choose_cards(mountain, island, username="alice", source="Cultivate")
    scenario.will_choose_cards(island, username="alice", source="Cultivate")
    scenario.cast_and_resolve("Cultivate", *sources)

    assert island.zone is Zone.BATTLEFIELD
    assert island.tapped
    assert mountain.zone is Zone.HAND
