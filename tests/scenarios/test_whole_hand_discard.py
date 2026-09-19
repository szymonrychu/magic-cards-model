"""Scenario: whole-hand discard - "Discard your hand." (a second-person
imperative addressed to the caster) and "discards their hand" (the same verb,
third person, inside an "each player ..." sentence) - as opposed to the
counted "discard N cards" shape `_DISCARD_A_CARD_RE` already reads.

Behold the Beyond's own "Discard your hand. Search your library for three
cards, put them into your hand, then shuffle." used to leave the first
sentence unread by anything: no parser anywhere matched a bare "discard your
hand"/"discards their hand", as opposed to a counted "discard N cards" -
`tests/scenarios/test_search_multiple_lands.py` drove Behold's own search
clause directly through `effect_for` to route around it, documented there as
"a separate, pre-existing gap this wave does not own". This file closes that
gap generally and proves it two ways: Behold the Beyond's own second-person
"Discard your hand." run through the ordinary two-clause `cast_and_resolve`
path, and Reforge the Soul's off-pool, differently-worded third-person
"Each player discards their hand, then draws seven cards." - a different
subject (every player, not just the caster), a different pronoun, and a
second, chained instruction after the discard.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 701.9a** - "To discard a card, move it from its owner's hand to that
  player's graveyard." A whole-hand discard is this same move, once per card
  in the hand - CR 701 has no separate "Discard your hand" keyword action.
- **CR 701.9b** - "By default, effects that cause a player to discard a card
  allow the affected player to choose which card to discard" - moot for a
  mandatory whole-hand discard (there is only one legal answer: every card),
  but it is why `_discard_cards`'s own `CHOOSE_CARDS` question is still asked
  rather than the engine picking for the player.
- **CR 701.23a/701.23d** - searching a library for a stated quantity, finding
  as many as the zone actually holds.
- **CR 701.24a** - the searched library is shuffled afterward.
- **CR 121.1** - drawing a card, one at a time.
- **CR 101.4/CR 608.2e** - "each player" resolves in APNAP order, one player
  finishing a step before the next starts it.
- **CR 608.2c** - a resolving spell follows its own printed instructions in
  the order written - Reforge the Soul's discard happens before its draw.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_behold_the_beyond_discards_the_whole_hand_then_searches():
    """Alice holds two cards besides Behold the Beyond itself (Plains,
    Island); both go to the graveyard as the first sentence resolves, then
    the second sentence finds the three library cards it names."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Behold the Beyond", "Plains", "Island"],
            library=["Forest", "Mountain", "Swamp"],
            battlefield=["Swamp"] * 7,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plains = scenario.find("Plains", Zone.HAND, "alice")
    island = scenario.find("Island", Zone.HAND, "alice")
    forest = scenario.find("Forest", Zone.LIBRARY, "alice")
    mountain = scenario.find("Mountain", Zone.LIBRARY, "alice")
    swamp = scenario.find("Swamp", Zone.LIBRARY, "alice")
    sources = scenario.untapped_sources(*(["Swamp"] * 7))

    # `will_discard` is not source-narrowed (CR 701.9b default chooser is
    # moot here - the whole hand is the only legal answer), so it matches
    # whichever `CHOOSE_CARDS` question comes first: the discard, resolved
    # before the search per CR 608.2c's printed order.
    scenario.will_discard(plains, island, username="alice")
    scenario.will_choose_cards(
        forest, mountain, swamp, username="alice", source="Behold the Beyond"
    )

    behold = scenario.cast_and_resolve("Behold the Beyond", *sources)

    alice = scenario.player("alice")
    assert behold.zone is Zone.GRAVEYARD
    assert {c.name for c in alice.graveyard} == {"Behold the Beyond", "Plains", "Island"}
    assert {c.name for c in alice.hand} == {"Forest", "Mountain", "Swamp"}
    assert alice.library == []


def test_reforge_the_soul_each_player_discards_hand_then_draws_seven():
    """Reforge the Soul (off-pool, modern-legal): "Each player discards their
    hand, then draws seven cards." Third person ("their hand"), a different
    subject (both players, not just the caster), and a chained second
    instruction, none of which `_DISCARD_HAND_RE` is written tightly around -
    proving the parser reads the mechanic, not Behold the Beyond's exact
    sentence.
    """
    twenty_islands = ["Island"] * 20
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Reforge the Soul", "Forest", "Mountain"],
            battlefield=["Mountain"] * 5,
            library=list(twenty_islands),
        )
        .player("bob", hand=["Plains", "Swamp", "Forest"], library=list(twenty_islands))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Mountain"] * 5))

    scenario.cast_and_resolve("Reforge the Soul", *sources)

    alice = scenario.player("alice")
    bob = scenario.player("bob")
    # Alice's whole pre-cast hand (Reforge the Soul, Forest, Mountain) is in
    # her graveyard; her new hand is seven freshly drawn Islands.
    assert {c.name for c in alice.graveyard} == {"Reforge the Soul", "Forest", "Mountain"}
    assert len(alice.hand) == 7
    assert all(c.name == "Island" for c in alice.hand)
    assert len(alice.library) == 13
    # Bob was never targeted - "each player" reached him all the same, with
    # nobody choosing which of his three cards to discard (CR 701.9b is moot:
    # discarding the whole hand has one legal answer).
    assert {c.name for c in bob.graveyard} == {"Plains", "Swamp", "Forest"}
    assert len(bob.hand) == 7
    assert all(c.name == "Island" for c in bob.hand)
    assert len(bob.library) == 13
