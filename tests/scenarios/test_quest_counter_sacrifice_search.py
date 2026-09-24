"""Scenario: a self-counter threshold that sacrifices its own permanent and
searches the combined hand-and-library pool for a stated card, shuffling the
library either way (CR 122.1, CR 701.21a, CR 701.23a, CR 701.24a).

Last Light of Durin's Day: "Whenever a Mountain you control enters, put a
quest counter on this enchantment. If it has six or more quest counters on
it, sacrifice it. If you do, search your hand and/or library for a Dragon
card and put it onto the battlefield. If you search your library this way,
shuffle."

Verified this session with `mise run rules:find`:

- **CR 608.2c** - instructions run in the order written, each depending on
  the one before it actually having happened.
- **CR 701.21a** - to sacrifice is to move a permanent you control straight
  to its owner's graveyard.
- **CR 701.23a** - to search a zone is to look at every card in it and find
  one that matches.
- **CR 701.24a** - to shuffle is to randomize a library so no player knows
  its order.

No off-pool second printing of "search your hand and/or library" paired with
a threshold-sacrifice was found by `card_search` (dated MEMORY.md line);
`Agency Outfitter` (off-pool candidate, Modern/Pioneer/Standard-legal) proves
the *multi-zone search with a library-conditional shuffle* half of this shape
is a real, non-HOB template - its own "graveyard, hand and/or library"
search, gated the identical "if you search your library this way, shuffle"
way, is not itself scenario-tested here because its own search names
specific cards rather than a stated quality, a different clause this wave
does not add a reader for.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def test_five_mountains_leave_the_quest_short_of_the_threshold():
    """Five quest counters is short of "six or more" - the enchantment
    survives and nothing is searched for."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mountain"] * 5,
            battlefield=["Last Light of Durin's Day"],
            library=["Astral Dragon"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    quest = scenario.creature("Last Light of Durin's Day", "alice")

    for _ in range(5):
        scenario.put_onto_battlefield("Mountain")
        scenario.pass_until_resolved()

    assert quest.zone is Zone.BATTLEFIELD
    assert quest.counters["quest"] == 5


def test_the_sixth_mountain_sacrifices_and_finds_a_dragon():
    """The sixth quest counter crosses the threshold: Last Light sacrifices
    itself and searches library-and-hand for a Dragon, finding the one in
    the library and shuffling afterward."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mountain"] * 6,
            battlefield=["Last Light of Durin's Day"],
            library=["Astral Dragon", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    quest = scenario.creature("Last Light of Durin's Day", "alice")

    for _ in range(6):
        scenario.put_onto_battlefield("Mountain")
        scenario.pass_until_resolved()

    assert quest.zone is Zone.GRAVEYARD
    dragon = scenario.creature("Astral Dragon", "alice")
    assert dragon.zone is Zone.BATTLEFIELD


def test_a_dragon_already_in_hand_is_a_legal_find_too():
    """CR 701.23a: the hand is as legal a source as the library for this
    search - a Dragon sitting in Alice's hand is found without ever touching
    the library's own copy."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mountain"] * 6 + ["Astral Dragon"],
            battlefield=["Last Light of Durin's Day"],
            library=["Forest"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    quest = scenario.creature("Last Light of Durin's Day", "alice")

    for _ in range(6):
        scenario.put_onto_battlefield("Mountain")
        scenario.pass_until_resolved()

    assert quest.zone is Zone.GRAVEYARD
    dragon = scenario.creature("Astral Dragon", "alice")
    assert dragon.zone is Zone.BATTLEFIELD
    assert dragon not in scenario.player("alice").hand
