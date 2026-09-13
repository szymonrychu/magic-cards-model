"""A card a player knew on top of a library, drawn straight into its owner's
hand, is still a card that player knows.

This is **a knowledge policy, not a Comprehensive Rules rule**, and it is the
project owner's decision. CR 400.7 makes the drawn card a new object, and
CR 402.3 says "A player can't look at the cards in another player's hand" -
neither says anything about what a player who watched the card go there
remembers. At a real table, a player who saw the top card of a library and
then watched its owner draw it knows what that card in hand is. So
`Game.known_to` carries a live library record across exactly one move:

- **Directly from its owner's library to that owner's hand.** A draw
  (CR 121.1: "A player draws a card by putting the top card of their library
  into their hand") or any effect that moves a card library-to-hand, like
  Goblin Guide's or explore's land.
- **Only a record still live at the move.** A record already ended by a
  shuffle or reordering (CR 701.20d, CR 701.24a) is not carried.
- **Only for the viewers the record had.** A look (CR 701.20e) stays the
  looker's.
- **Until the card leaves that hand by any zone change** - discarded, cast,
  shuffled back for a mulligan (CR 103.5) - because every such move is
  CR 400.7's new object again.

The carry is stored as data on the game at the moment of the move - never as a
callable - so a decoded game knows exactly what the live one did.

Every CR number above was read in full with `mise run rules:find` in the
session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Game, Zone
from tests.scenarios.harness import Scenario
from tests.scenarios.test_explore import _board as amalia_board
from tests.scenarios.test_explore import _explore
from tests.scenarios.test_mulligans import match as eldrazi_ramp_match


def known(game: Game, viewer: str) -> list[tuple[str, Zone, int | None, bool]]:
    return [
        (entry.card_name, entry.zone, entry.index_from_top, entry.carried)
        for entry in game.known_to(viewer)
    ]


def _goblin_guide_reveals(*bob_library: str, bob_battlefield: list[str] | None = None) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Goblin Guide"])
        .player("bob", library=list(bob_library), battlefield=bob_battlefield or [])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Goblin Guide", "alice"))
    scenario.resolve_top()
    return scenario


def _alice_looks_at_bobs_top_card(
    *bob_library: str, bob_hand: list[str] | None = None, bob_battlefield: list[str] | None = None
) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mishra's Bauble"])
        .player(
            "bob",
            library=list(bob_library),
            hand=bob_hand or [],
            battlefield=bob_battlefield or [],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bauble = scenario.find("Mishra's Bauble", Zone.BATTLEFIELD)
    scenario.activate(bauble, username="alice", targets=["bob"])
    scenario.pass_until_resolved()
    return scenario


# -- carried -------------------------------------------------------------------


def test_a_land_goblin_guide_reveals_into_hand_stays_known_to_both_players():
    scenario = _goblin_guide_reveals("Forest", "Lightning Bolt")
    game = scenario.game
    forest = scenario.find("Forest", Zone.HAND, "bob")

    assert known(game, "alice") == [("Forest", Zone.HAND, None, True)]
    assert known(game, "bob") == [("Forest", Zone.HAND, None, True)]
    (entry,) = game.known_to("alice")
    assert entry.card_id == forest.id
    assert entry.owner == "bob"
    assert entry.source == "Goblin Guide"
    assert entry.turn == game.turn.turns_taken

    (reveal,) = game.reveals
    assert reveal.viewers is None, "CR 701.20a: shown to all players"
    assert reveal.zone is Zone.LIBRARY
    assert reveal.revealed_by == "bob"
    assert reveal.source == "Goblin Guide"
    assert reveal.turn == game.turn.turns_taken
    assert reveal.library_epoch == game.player("bob").library_epoch
    assert reveal.zone_change_stamp is not None
    assert reveal.zone_change_stamp != forest.zone_change_stamp, "CR 400.7: a new object in hand"


def test_a_nonland_goblin_guide_reveals_is_known_on_top_and_then_carried_when_drawn():
    scenario = _goblin_guide_reveals("Lightning Bolt", "Forest")
    game = scenario.game
    assert known(game, "alice") == [("Lightning Bolt", Zone.LIBRARY, 0, False)]

    scenario.draw(username="bob")

    assert known(game, "alice") == [("Lightning Bolt", Zone.HAND, None, True)]
    assert known(game, "bob") == [("Lightning Bolt", Zone.HAND, None, True)]


def test_a_looked_at_top_card_drawn_by_its_owner_stays_known_to_the_looker_only():
    scenario = _alice_looks_at_bobs_top_card("Lightning Bolt", "Island")

    scenario.draw(username="bob")

    assert scenario.find("Lightning Bolt", Zone.HAND, "bob").zone is Zone.HAND
    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.HAND, None, True)]
    assert known(scenario.game, "bob") == []


def test_explore_moving_a_revealed_land_into_hand_carries_it_too():
    """Not a draw: CR 701.44a's land branch puts the revealed card into the
    hand by an effect, which is the same library-to-hand move."""
    scenario = amalia_board("Forest", "Llanowar Elves").build()
    _explore(scenario)

    assert known(scenario.game, "bob") == [("Forest", Zone.HAND, None, True)]
    (reveal,) = scenario.game.reveals
    assert reveal.library_epoch is not None
    assert reveal.zone_change_stamp is not None


def test_the_carry_survives_a_later_shuffle_of_the_library_it_came_from():
    """A shuffle reorders a library (CR 701.24a); the card is in a hand."""
    scenario = _alice_looks_at_bobs_top_card(
        "Lightning Bolt", "Plains", "Island", bob_battlefield=["Flooded Strand"]
    )
    scenario.draw(username="bob")
    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.HAND, None, True)]

    scenario.pass_priority()
    strand = scenario.find("Flooded Strand", Zone.BATTLEFIELD)
    scenario.activate(strand, username="bob")
    scenario.pass_until_resolved()

    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.HAND, None, True)]


# -- the carry ends ------------------------------------------------------------


def test_the_carried_card_stops_being_known_when_it_is_discarded():
    scenario = _goblin_guide_reveals("Forest", "Lightning Bolt")
    forest = scenario.find("Forest", Zone.HAND, "bob")
    assert known(scenario.game, "alice") == [("Forest", Zone.HAND, None, True)]

    scenario.game.discard_cards("bob", [forest])

    assert forest.zone is Zone.GRAVEYARD
    assert known(scenario.game, "alice") == []
    assert known(scenario.game, "bob") == []


def test_the_carried_card_stops_being_known_when_it_is_cast_from_hand():
    scenario = _alice_looks_at_bobs_top_card(
        "Lightning Bolt", "Island", bob_battlefield=["Mountain"]
    )
    scenario.draw(username="bob")
    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.HAND, None, True)]

    scenario.pass_priority()
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", mountain, username="bob", targets=[scenario.player("alice")]
    )

    assert bolt.zone is Zone.STACK
    assert known(scenario.game, "alice") == []
    scenario.pass_until_resolved()
    assert known(scenario.game, "alice") == []


def test_the_carried_card_stops_being_known_when_its_owner_mulligans():
    """CR 103.5: "shuffles the cards in their hand back into their library".

    The look and the draw are engine calls during the mulligan step: nothing
    in a real pregame draws between two hands, and a carried card has to be in
    a hand for a mulligan to end its carry."""
    match = eldrazi_ramp_match()
    game = match.start_game()
    bob = game.player("bob")
    top = bob.library[0]
    game.look(top, "alice", source=None)
    game.draw_cards("bob", 1)
    assert top.zone is Zone.HAND
    assert known(game, "alice") == [(top.name, Zone.HAND, None, True)]

    game.declare_mulligan("alice", False)
    game.declare_mulligan("bob", True)

    assert bob.mulligans_taken == 1
    assert known(game, "alice") == []


def test_a_card_drawn_after_its_library_was_shuffled_is_not_carried():
    """The fetch leaves the looked-at Bolt as bob's only card, so the card
    drawn is the very card alice looked at - and still not one she knows,
    because the shuffle ended her record before the draw."""
    scenario = _alice_looks_at_bobs_top_card(
        "Lightning Bolt", "Plains", bob_battlefield=["Flooded Strand"]
    )
    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.LIBRARY, 0, False)]

    scenario.pass_priority()
    strand = scenario.find("Flooded Strand", Zone.BATTLEFIELD)
    scenario.activate(strand, username="bob")
    scenario.pass_until_resolved()
    assert [state.name for state in scenario.player("bob").library] == ["Lightning Bolt"]
    assert known(scenario.game, "alice") == []

    scenario.draw(username="bob")

    assert scenario.find("Lightning Bolt", Zone.HAND, "bob").zone is Zone.HAND
    assert known(scenario.game, "alice") == []
