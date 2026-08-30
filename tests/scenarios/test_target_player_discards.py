"""A plain "target player discards N cards" clause (CR 701.9a), CR 701.9b's
*default* chooser left untouched - `_parse_target_player_discards_clause` in
`machines/effects.py`.

Go Blank is the vehicle: "Target player discards two cards. Then exile that
player's graveyard." Two clauses, one target, read in printed order
(CR 608.2c) - the exile has to happen *after* the discard, so the two cards
just discarded are themselves exiled along with whatever else was already in
the graveyard. Getting that order backwards would leave the discarded pair
sitting in the graveyard, unexiled, and the board would still look
plausible.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 701.9a** - "To discard a card, move it from its owner's hand to that
  player's graveyard."
- **CR 701.9b** - "By default, effects that cause a player to discard a card
  allow the affected player to choose which card to discard" - unlike
  Thoughtseize's own overridden chooser (`test_reveal_hand_and_choose.py`),
  Go Blank names no other chooser, so the discarding player picks their own
  two cards.
- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written" - the reason the exile clause sees the
  cards the discard clause just put into the graveyard.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def test_the_target_discards_their_own_choice_of_two_cards():
    """CR 701.9b's default chooser (the discarding player) picks which two,
    unlike Thoughtseize's overridden chooser. Go Blank's own second clause
    then exiles the graveyard unconditionally, so the discarded pair ends up
    in exile rather than sitting in the graveyard - see the ordering test
    below for that half asserted on its own."""
    scenario = (
        Scenario()
        .player("alice", hand=["Go Blank"], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("bob", hand=["Lightning Bolt", "Forest", "Mountain", "Giant Growth"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    forest = scenario.find("Forest", Zone.HAND, "bob")

    scenario.will_discard(bolt, forest, username="bob")

    scenario.cast_and_resolve("Go Blank", *sources, targets=["bob"])

    assert bolt.zone is Zone.EXILE
    assert forest.zone is Zone.EXILE
    assert len(bob.hand) == 2


def test_discards_are_exiled_after_landing_in_the_graveyard():
    """CR 608.2c's printed order: the discard clause runs first, the exile
    clause runs second and catches what the discard just put there - the
    ordering trap this file exists to prove."""
    scenario = (
        Scenario()
        .player("alice", hand=["Go Blank"], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("bob", hand=["Lightning Bolt", "Forest"], graveyard=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    forest = scenario.find("Forest", Zone.HAND, "bob")
    mountain = scenario.find("Mountain", Zone.GRAVEYARD, "bob")

    scenario.will_discard(bolt, forest, username="bob")

    scenario.cast_and_resolve("Go Blank", *sources, targets=["bob"])

    assert bolt.zone is Zone.EXILE
    assert forest.zone is Zone.EXILE
    assert mountain.zone is Zone.EXILE
    assert bob.graveyard == []


def test_fewer_cards_than_the_discard_count_discards_the_whole_hand():
    """CR 701.9a names no floor the way CR 119.4's life payment does: a hand
    smaller than the printed count simply empties, one card at a time, and
    every one of them still gets exiled."""
    scenario = (
        Scenario()
        .player("alice", hand=["Go Blank"], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("bob", hand=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")

    scenario.will_discard(bolt, username="bob")

    scenario.cast_and_resolve("Go Blank", *sources, targets=["bob"])

    assert bolt.zone is Zone.EXILE
    assert bob.hand == []


def test_an_empty_hand_discards_nothing_and_the_graveyard_is_still_exiled():
    """CHOOSE_CARDS is never asked for zero cards, and the graveyard's own
    exile still runs regardless (CR 608.2c: it is a separate instruction)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Go Blank"], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("bob", graveyard=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    mountain = scenario.find("Mountain", Zone.GRAVEYARD, "bob")

    scenario.cast_and_resolve("Go Blank", *sources, targets=["bob"])

    assert bob.hand == []
    assert mountain.zone is Zone.EXILE
