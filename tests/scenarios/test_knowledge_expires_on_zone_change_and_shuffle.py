"""What a player knows about a hidden card stops being true when the card
stops being that card, or the library it sits in stops being in that order.

A reveal shows a card to all players (CR 701.20a) and a look shows it to one
(CR 701.20e: "Looking at a card follows the same rules as revealing a card,
except that the card is shown only to the specified player"). Neither moves
the card (CR 701.20b). `Game.known_to(viewer)` answers "which hidden cards
does this player still know", and this file is about the ways that knowledge
ends:

- **CR 400.7** - "An object that moves from one zone to another becomes a new
  object with no memory of, or relation to, its previous existence." A card
  that left and came back to the very same zone is not the card that was
  shown, so a record of the old object says nothing about the new one.
- **CR 701.20d** - "If cards in a player's library are shuffled or otherwise
  reordered, any revealed cards that are reordered stop being revealed and
  become new objects." And CR 701.24a's shuffle is exactly that: "randomize
  the cards within it so that no player knows their order." A library record
  is kept against the owner's `Player.library_epoch`, which every shuffle and
  every insertion into or reordering of that library moves on; a put that
  leaves a card's order untouched (onto the bottom) re-pins that card's record
  to the new epoch - see `test_bottom_put_keeps_untouched_library_knowledge.py`.
- **CR 401.2** - "Players can't look at or change the order of cards in a
  library", which is why a library card's position is the thing a library
  record knows, and why anything that reorders it, or puts a card above it,
  ends it.

Every CR number above was read in full with `mise run rules:find` in the
session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Game, Zone
from tests.scenarios.harness import Scenario
from tests.scenarios.test_opening_hand_actions import (
    broodscale,
    dealt,
    devoted,
    series,
    will_take,
)


def known(game: Game, viewer: str) -> list[tuple[str, Zone, int | None, bool]]:
    return [
        (entry.card_name, entry.zone, entry.index_from_top, entry.carried)
        for entry in game.known_to(viewer)
    ]


def _goblin_guide_board(*, bob_library: list[str], guides: int = 1) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Goblin Guide"] * guides)
        .player("bob", library=bob_library, battlefield=["Flooded Strand", "Island"])
    )


def _devourer_revealed_from_alices_opening_hand() -> tuple[Game, object]:
    """CR 103.6b's reveal: a record of a card in a *hand*, which no library
    epoch can end - only CR 400.7's zone change can."""
    match = series(broodscale(), devoted())
    game = dealt(match, {"alice": "Devourer of Destiny"})
    devourer = next(s for s in game.player("alice").hand if s.name == "Devourer of Destiny")
    will_take(game, "alice", "Devourer of Destiny")
    match.run_mulligans(game)
    assert devourer.zone is Zone.HAND
    return game, devourer


# -- a shuffle (CR 701.24a, CR 701.20d) ---------------------------------------


def test_a_revealed_top_card_stops_being_known_when_a_fetchland_shuffles_the_library():
    scenario = _goblin_guide_board(bob_library=["Lightning Bolt", "Plains", "Island"]).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Goblin Guide", "alice"))
    scenario.resolve_top()

    bob = scenario.player("bob")
    bolt = scenario.find("Lightning Bolt", Zone.LIBRARY, "bob")
    assert bob.library[0] is bolt
    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.LIBRARY, 0, False)]
    assert known(scenario.game, "bob") == [("Lightning Bolt", Zone.LIBRARY, 0, False)]
    epoch_before = bob.library_epoch

    scenario.pass_priority()
    strand = scenario.find("Flooded Strand", Zone.BATTLEFIELD)
    scenario.activate(strand, username="bob")
    scenario.pass_until_resolved()

    assert bolt.zone is Zone.LIBRARY, "the Bolt never moved - only the order did"
    assert bob.library_epoch > epoch_before
    assert known(scenario.game, "alice") == []
    assert known(scenario.game, "bob") == []


def test_revealing_the_same_card_again_after_a_shuffle_makes_it_known_again():
    """CR 701.20c: "A card that is currently revealed may be revealed again."
    Two Goblin Guides reveal the same top card either side of a fetch; the
    second showing is a fresh record against the new order, and the viewer
    knows the card once - not twice."""
    scenario = _goblin_guide_board(bob_library=["Lightning Bolt", "Plains"], guides=2).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*scenario.creatures("Goblin Guide", "Goblin Guide", username="alice"))
    scenario.resolve_top()
    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.LIBRARY, 0, False)]

    scenario.pass_priority()
    strand = scenario.find("Flooded Strand", Zone.BATTLEFIELD)
    scenario.activate(strand, username="bob")
    scenario.pass_until_resolved()  # the fetch: Plains found, library shuffled
    assert [state.name for state in scenario.player("bob").library] == ["Lightning Bolt"]
    assert known(scenario.game, "alice") == []

    scenario.pass_until_resolved()  # the second Goblin Guide trigger
    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.LIBRARY, 0, False)]
    assert known(scenario.game, "bob") == [("Lightning Bolt", Zone.LIBRARY, 0, False)]
    epochs = [reveal.library_epoch for reveal in scenario.game.reveals]
    assert len(epochs) == 2 and epochs[0] != epochs[1]


# -- a card put on top, and other reorderings (CR 701.20d, CR 401.2) ----------


def test_a_looked_at_top_card_stops_being_known_when_a_spell_is_put_on_top_of_that_library():
    """Subtlety puts bob's Grizzly Bears spell on top of his library. The
    looked-at Bolt never moved, but it is no longer the top card, and no
    record of "the top card" survives an insertion above it."""
    scenario = (
        Scenario()
        .player(
            "bob",
            hand=["Grizzly Bears"],
            library=["Lightning Bolt", "Island"],
            battlefield=["Forest", "Forest"],
        )
        .player("alice", hand=["Subtlety"], battlefield=["Island"] * 4 + ["Mishra's Bauble"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("bob")
    bauble = scenario.find("Mishra's Bauble", Zone.BATTLEFIELD)
    scenario.activate(bauble, username="alice", targets=["bob"])
    scenario.pass_until_resolved()
    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.LIBRARY, 0, False)]

    forests = scenario.untapped_sources("Forest", "Forest", username="bob")
    islands = scenario.untapped_sources(*(["Island"] * 4), username="alice")
    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="bob")
    scenario.pass_priority("bob")
    scenario.choose_trigger_targets("Subtlety", [bears])
    scenario.will_choose_top(True, username="bob")
    scenario.cast_onto_stack("Subtlety", *islands, username="alice")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    bob = scenario.player("bob")
    assert bob.library[0] is bears
    assert bob.library[1].name == "Lightning Bolt"
    assert known(scenario.game, "alice") == []


def test_a_scry_that_keeps_the_card_on_top_still_ends_the_record():
    """CR 701.20d's "otherwise reordered": the scry's put-back is a
    reordering whether or not the order came out the same, and the card Opt
    then draws is not carried either."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Goblin Guide"])
        .player("bob", hand=["Opt"], library=["Lightning Bolt", "Plains"], battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Goblin Guide", "alice"))
    scenario.resolve_top()
    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.LIBRARY, 0, False)]

    scenario.pass_priority()
    (island,) = scenario.untapped_sources("Island", username="bob")
    scenario.scry_keeping_everything_on_top(username="bob")
    scenario.cast_and_resolve("Opt", island, username="bob")

    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    assert bolt.zone is Zone.HAND
    assert known(scenario.game, "alice") == []


# -- a look is for its viewer (CR 701.20e) -------------------------------------


def test_a_look_is_known_only_to_the_player_who_looked():
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Mishra's Bauble", "Mishra's Bauble"])
        .player("bob", library=["Lightning Bolt", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = [s for s in scenario.game.battlefield if s.name == "Mishra's Bauble"]

    scenario.activate(first, targets=["bob"])
    scenario.pass_until_resolved()

    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.LIBRARY, 0, False)]
    assert known(scenario.game, "bob") == []
    (look,) = scenario.game.reveals
    assert look.viewers == ["alice"]
    assert look.card_name == "Lightning Bolt"
    assert look.zone is Zone.LIBRARY

    scenario.activate(second, targets=["alice"])
    scenario.pass_until_resolved()

    assert known(scenario.game, "bob") == [], "alice looking at her own library shows bob nothing"
    assert [entry.card_name for entry in scenario.game.known_to("alice")] == [
        "Lightning Bolt",
        "Forest",
    ]


# -- a zone change is a new object (CR 400.7) ----------------------------------


def test_a_revealed_card_that_is_exiled_and_returned_to_the_same_zone_is_not_known():
    game, devourer = _devourer_revealed_from_alices_opening_hand()
    assert known(game, "bob") == [("Devourer of Destiny", Zone.HAND, None, False)]

    game.exile_cards([devourer])
    assert known(game, "bob") == []
    game.return_to_hand(devourer)

    assert devourer.zone is Zone.HAND
    assert known(game, "bob") == []
    assert known(game, "alice") == []


def test_a_battlefield_card_bounced_to_hand_is_a_new_object_and_not_known():
    game, devourer = _devourer_revealed_from_alices_opening_hand()
    assert known(game, "bob") == [("Devourer of Destiny", Zone.HAND, None, False)]

    game.put_onto_battlefield(devourer, "alice")
    assert devourer.zone is Zone.BATTLEFIELD
    assert known(game, "bob") == []

    game.return_to_hand(devourer)

    assert devourer.zone is Zone.HAND
    assert known(game, "bob") == []
