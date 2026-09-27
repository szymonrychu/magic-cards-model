"""Scenario: a mass bounce paired with an optional per-player wheel, then
self-exile.

Turtles in Time: "Return all creatures to their owners' hands. Each player
may shuffle their hand and graveyard into their library, then each player
who does draws seven cards. Exile Turtles in Time."

Three CR 608.2c instructions, read in printed order:

- **CR 701.3a** - "return" moves an object to a zone from a different one;
  every creature on the battlefield goes to its owner's hand
  (`_parse_mass_return_to_hand_clause`, already generic across any mass
  "return all `<description>` to their owners' hands" printing - not new in
  this file).
- **CR 608.2d** - the "may" is asked once per player still in the game, in
  seating order; a player who declines leaves their own hand and graveyard
  untouched and draws nothing. "Each player who does" (CR 400.7 anaphora) ties
  the draw to that same player's own answer, never to anyone else's.
- **CR 701.24a** - the shuffle is the library alone, once the hand and
  graveyard have been moved into it (CR 400.7: each becomes a new library
  object).
- **CR 201.5/`_strip_self_exile_sentence`** - "Exile Turtles in Time" is the
  spell's own self-reference, read generically off the printed name for any
  spell that ends this way, not new in this file either.

Step Between Worlds is the second, non-pool printing that proves the wheel
generalizes: the identical mechanic, printed as two full sentences ("... into
their library. Each player who does draws seven cards.") rather than one
comma-"then" join, with no mass bounce at all in front of it. Verified legal
in Modern, Pioneer, and Standard (`resolve_cards`-equivalent: its own fetched
Scryfall printing's `legalities`).

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_turtles_in_time_bounces_creatures_and_runs_the_wheel_for_whoever_takes_it():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Turtles in Time"],
            battlefield=[
                "Grizzly Bears",
                "Island",
                "Island",
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
            ],
            graveyard=["Lightning Bolt"],
            library=["Forest"] * 10,
        )
        .player(
            "bob",
            battlefield=["Llanowar Elves"],
            hand=["Counterspell"],
            graveyard=["Opt"],
            library=["Island"] * 10,
        )
        .build()
    )
    scenario.will_take_the_may(True, username="alice")
    scenario.will_take_the_may(False, username="bob")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(
        "Island", "Island", "Swamp", "Swamp", "Swamp", "Swamp", "Swamp"
    )

    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    turtles = scenario.cast_and_resolve("Turtles in Time", *sources, username="alice")

    # CR 701.3a's bounce happened first, so the bounced Grizzly Bears was
    # still in alice's hand when the wheel moved everything into her library;
    # CR 701.24a's shuffle then scattered it (and Lightning Bolt) somewhere in
    # there, never left behind in hand or graveyard.
    assert bears.zone is Zone.LIBRARY
    assert bolt.zone is Zone.LIBRARY
    assert scenario.player("alice").graveyard == []
    assert len(scenario.player("alice").hand) == 7

    # Bob declined: his own bounced Llanowar Elves sits in his hand, his
    # graveyard is untouched, and he drew nothing extra.
    bob_hand_names = [state.name for state in scenario.player("bob").hand]
    assert bob_hand_names.count("Llanowar Elves") == 1
    assert bob_hand_names.count("Counterspell") == 1
    assert len(bob_hand_names) == 2
    assert [state.name for state in scenario.player("bob").graveyard] == ["Opt"]

    # CR 201.5's self-exile: the spell never reaches the graveyard.
    assert turtles.zone is Zone.EXILE


def test_declining_the_wheel_leaves_hand_and_graveyard_untouched():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Turtles in Time"],
            battlefield=[
                "Grizzly Bears",
                "Island",
                "Island",
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
            ],
            graveyard=["Lightning Bolt"],
            library=["Forest"] * 10,
        )
        .player("bob", battlefield=[], library=["Island"] * 10)
        .build()
    )
    scenario.will_take_the_may(False, username="alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(
        "Island", "Island", "Swamp", "Swamp", "Swamp", "Swamp", "Swamp"
    )

    scenario.cast_and_resolve("Turtles in Time", *sources, username="alice")

    alice_hand_names = [state.name for state in scenario.player("alice").hand]
    assert alice_hand_names == ["Grizzly Bears"]
    assert [state.name for state in scenario.player("alice").graveyard] == ["Lightning Bolt"]


def test_an_empty_battlefield_still_runs_the_wheel_on_its_own():
    """CR 608.2d's own "may" never depends on the mass bounce having done
    anything - a board with nothing to bounce still offers, and runs, the
    wheel for whoever wants it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Turtles in Time", "Opt", "Lightning Bolt"],
            battlefield=["Island", "Island", "Swamp", "Swamp", "Swamp", "Swamp", "Swamp"],
            graveyard=["Counterspell"],
            library=["Forest"] * 10,
        )
        .player("bob", battlefield=[], library=["Island"] * 10)
        .build()
    )
    scenario.will_take_the_may(True, username="alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(
        "Island", "Island", "Swamp", "Swamp", "Swamp", "Swamp", "Swamp"
    )

    scenario.cast_and_resolve("Turtles in Time", *sources, username="alice")

    assert scenario.player("alice").graveyard == []
    assert len(scenario.player("alice").hand) == 7


def test_step_between_worlds_proves_the_wheel_generalizes_off_two_full_sentences():
    """Step Between Worlds: "Each player may shuffle their hand and graveyard
    into their library. Each player who does draws seven cards. Exile Step
    Between Worlds." - the identical wheel, with no mass bounce and printed as
    two full sentences rather than one comma-"then" join, proving `merge_
    each_player_may_shuffle_hand_graveyard_then_draw_clauses` reads the shape
    and not just Turtles in Time's own exact punctuation.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Step Between Worlds", "Opt"],
            graveyard=["Lightning Bolt"],
            battlefield=["Island", "Island", "Island", "Island", "Island"],
            library=["Forest"] * 10,
        )
        .player("bob", battlefield=[], library=["Island"] * 10)
        .build()
    )
    scenario.will_take_the_may(True, username="alice")
    scenario.will_take_the_may(False, username="bob")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island", "Island", "Island", "Island", "Island")

    step = scenario.cast_and_resolve("Step Between Worlds", *sources, username="alice")

    assert scenario.player("alice").graveyard == []
    assert len(scenario.player("alice").hand) == 7
    assert step.zone is Zone.EXILE
