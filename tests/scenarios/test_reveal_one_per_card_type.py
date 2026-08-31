"""Scenario: Atraxa, Grand Unifier's enters trigger.

"When Atraxa enters, reveal the top ten cards of your library. For each card
type, you may put a card of that type from among the revealed cards into your
hand. Put the rest on the bottom of your library in a random order."

The middle sentence is a loop over card types rather than a fixed number of
picks, which is why nothing else in the engine's vocabulary read it and the
trigger resolved doing nothing at all.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 701.20a** - "To reveal a card, show that card to all players for a
  brief time", which changes nothing this model tracks; where the cards end up
  is the whole effect.
- **CR 205.2a / CR 300.1** - the card types the loop runs over.
- **CR 608.2d** - each pick is a "you may", so a player is never forced.
- **CR 608.2c** - the three sentences run in the order printed.
- **CR 701.24a** - shuffling randomises a library. This card never prints
  "shuffle", so the bottomed cards are randomised without one.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario

#: Five card types among the top ten, plus filler. Order is top-first.
TOP_TEN = [
    "Lightning Bolt",  # instant
    "Grizzly Bears",  # creature
    "Sol Ring",  # artifact
    "Forest",  # land
    "Rancor",  # enchantment
    "Island",
    "Island",
    "Island",
    "Island",
    "Island",
]


def _resolve_atraxa(scenario):
    atraxa = scenario.put_onto_battlefield("Atraxa, Grand Unifier", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    return atraxa


def test_one_card_of_each_type_among_the_top_ten_goes_to_hand():
    """Five distinct card types are revealed, so five cards are kept - one per
    type, not five of any one type."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Atraxa, Grand Unifier"],
            library=[*TOP_TEN, *["Swamp"] * 10],
            battlefield=["Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _resolve_atraxa(scenario)

    hand = {state.name for state in scenario.player("alice").hand}
    assert hand == {"Lightning Bolt", "Grizzly Bears", "Sol Ring", "Rancor", "Island"}, (
        "one instant, one creature, one artifact, one enchantment, one land"
    )


def test_the_rest_go_to_the_bottom_and_the_untouched_library_stays_put():
    """The ten cards leave the top; the five not kept land underneath
    everything that was already below them."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Atraxa, Grand Unifier"],
            library=[*TOP_TEN, *["Swamp"] * 10],
            battlefield=["Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _resolve_atraxa(scenario)

    library = [state.name for state in scenario.player("alice").library]
    assert len(library) == 15, "twenty minus the five kept"
    assert library[:10] == ["Swamp"] * 10, "what was under the top ten never moved"
    assert sorted(library[10:]) == sorted(["Forest", "Island", "Island", "Island", "Island"])


def test_a_card_kept_for_one_type_is_not_available_for_another():
    """An artifact creature satisfies either type, and only one of them - once
    it is in hand it is no longer "from among the revealed cards"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Atraxa, Grand Unifier"],
            library=["Memnite", *["Swamp"] * 12],
            battlefield=["Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _resolve_atraxa(scenario)

    hand = [state.name for state in scenario.player("alice").hand]
    assert hand.count("Memnite") == 1, "an artifact creature is kept once, not twice"
    assert "Swamp" in hand, "the land pick is unaffected"


def test_a_library_shallower_than_ten_reveals_what_is_there():
    """CR 701.20a has nothing to say about a short library: the effect reveals
    the cards that exist and carries on."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Atraxa, Grand Unifier"],
            library=["Lightning Bolt", "Grizzly Bears"],
            battlefield=["Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _resolve_atraxa(scenario)

    hand = {state.name for state in scenario.player("alice").hand}
    assert hand == {"Lightning Bolt", "Grizzly Bears"}
    assert scenario.player("alice").library == []
