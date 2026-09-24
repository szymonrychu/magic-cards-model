"""Through the Forest Gate: "Look at the top twenty cards of your library,
put any number of land cards from among them onto the battlefield tapped,
then shuffle. You gain 8 life."

`_SELECT_FROM_TOP_RE`'s own "look at the top N ... put ... cards from among
them onto the battlefield" family already existed, but that regex requires
the look and the put to be two full sentences ("Look at the top N cards of
your library. Put ..."). Through the Forest Gate prints the identical CR
608.2c instruction as one comma-joined sentence instead
("Look at the top twenty cards of your library, put any number of land
cards from among them onto the battlefield tapped, then shuffle."), and
`_CLAUSE_SEPARATOR`'s bare " then " inside it cuts the trailing "then
shuffle" into its own bare fragment neither reader could reattach - the
identical bare-"shuffle" artifact `_rejoin_search_clauses` already
reattaches for a *search* clause, just never for a *look*.
`_merge_look_top_n_put_kind_battlefield_then_shuffle_clauses`, a new
two-clause merge, reads the comma-joined shape whole and reattaches the
bare "shuffle" itself rather than widening `_rejoin_search_clauses` (which
is scoped to search clauses specifically, via `_MENTIONS_SEARCH_RE`).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 701.20a** - "look at" the top twenty records nothing and moves
  nothing; it is a private look, not a reveal.
- **CR 107.1c** - "any number of" land cards is zero to every qualifying
  one, no separate "may" needed.
- **CR 110.2a** - a land put onto the battlefield this way is not played,
  so it does not use up the turn's own land drop (CR 305.1).
- **CR 701.24a** - the remaining, un-taken cards are shuffled back in.
- **CR 119.3** - the trailing "you gain 8 life."

No second printing on Scryfall pairs "look at the top N cards of your
library" with "put any number of land cards from among them onto the
battlefield tapped, then shuffle" as one comma-joined sentence and a literal
printed count (Famished Worldsire prints the closest relative, but counts
its own top N off a self-defined X - "where X is this creature's power" -
rather than a literal number, a shape this reader was not built to read;
checked in the session that wrote this file) - see the dated `MEMORY.md`
line.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_looking_at_the_top_twenty_puts_every_land_onto_the_battlefield_tapped():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Through the Forest Gate"],
            battlefield=["Forest"] * 8,
            library=["Mountain", "Grizzly Bears", "Island", "Lightning Bolt", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    mountain, bears, island, bolt, forest = alice.library
    life_before = alice.life
    sources = scenario.untapped_sources(*(["Forest"] * 8))

    scenario.will_choose_cards(
        mountain, island, forest, username="alice", source="Through the Forest Gate"
    )
    scenario.cast_and_resolve("Through the Forest Gate", *sources)

    for land in (mountain, island, forest):
        assert land.zone is Zone.BATTLEFIELD
        assert land.tapped
        assert land.controller == "alice"
    assert bears.zone is Zone.LIBRARY
    assert bolt.zone is Zone.LIBRARY
    assert alice.life == life_before + 8


def test_declining_every_land_still_gains_the_life_and_shuffles():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Through the Forest Gate"],
            battlefield=["Forest"] * 8,
            library=["Mountain", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    mountain, bears = alice.library
    life_before = alice.life
    sources = scenario.untapped_sources(*(["Forest"] * 8))

    scenario.will_choose_cards(username="alice", source="Through the Forest Gate")
    scenario.cast_and_resolve("Through the Forest Gate", *sources)

    assert mountain.zone is Zone.LIBRARY
    assert bears.zone is Zone.LIBRARY
    assert alice.life == life_before + 8
