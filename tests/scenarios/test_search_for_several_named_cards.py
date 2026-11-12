"""A library search for several cards sharing one name.

"When this creature enters, you may search your library for any number of cards
named Andromedan Automatons, reveal them, put them into your hand, then
shuffle." (Andromedan Automatons, Battalion Foot Soldier) and "... for up to
three cards named Squadron Hawk, reveal them, put them into your hand, then
shuffle." (Squadron Hawk) are the plural twin of Tempest Hawk's "a card named
...": the same name-bound search with a count slot ("any number of", "up to N")
and the plural reveal.

- **CR 701.23a** - "To search for a card in a zone, look at all cards in that
  zone (even if it's a hidden zone) and find a card that matches the given
  description." The description here is a name.
- **CR 701.23b** - a stated-quality search in a hidden zone never has to find
  some or all of the matching cards, even when they are there. A name is a
  stated quality, so finding fewer, or none, is always a legal answer.
- **CR 107.1c** - "any number" is zero upward, bounded only by what exists.
- **CR 701.23e** - a printed "reveal them" is a real reveal, so the finds are
  known to the opponent while they sit in the hand.
- **CR 701.24a/701.24b** - the library is shuffled afterwards, the finds not
  being part of it.
- **CR 603.6a** - the search is an enters-the-battlefield trigger.
- **CR 101.2** - Ashiok, Dream Render's "can't" beats the search.

Squadron Hawk and Battalion Foot Soldier are in no deck pool; the three
printings differ in count wording ("any number of" against "up to three"), in
type and in cost, so the parser is exercised rather than one sentence. Every CR
number above was read in full from `mise run rules:find` in the session that
wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Game, Zone
from tests.scenarios.harness import Scenario

PLAINS = ["Plains"] * 3


def _board(spell: str, library: list[str], *, hand=None, graveyard=None, bob=None) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[spell, *(hand or [])],
            battlefield=PLAINS,
            library=library,
            graveyard=graveyard or [],
        )
        .player("bob", library=bob or ["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario: Scenario, spell: str) -> None:
    scenario.cast_and_resolve(spell, *scenario.untapped_sources(*PLAINS))
    scenario.pass_until_resolved()  # the enters trigger


def _names(cards) -> list[str]:
    return sorted(card.name for card in cards)


def _known(game: Game, viewer: str) -> list[tuple[str, Zone]]:
    return sorted((entry.card_name, entry.zone) for entry in game.known_to(viewer))


# -- any number of --------------------------------------------------------------


def test_any_number_takes_every_copy_in_the_library():
    """Five more copies is more than any printed "up to" would allow: the count
    is the library itself (CR 107.1c)."""
    scenario = _board(
        "Andromedan Automatons",
        ["Andromedan Automatons"] * 5 + ["Plains", "Squadron Hawk"],
    )

    _cast(scenario, "Andromedan Automatons")

    alice = scenario.player("alice")
    assert _names(alice.hand) == ["Andromedan Automatons"] * 5
    assert _names(alice.library) == ["Plains", "Squadron Hawk"], "nothing else was taken"


def test_any_number_finds_the_finds_revealed_to_the_opponent():
    scenario = _board("Andromedan Automatons", ["Andromedan Automatons"] * 2 + ["Plains"])

    _cast(scenario, "Andromedan Automatons")

    assert _known(scenario.game, "bob") == [
        ("Andromedan Automatons", Zone.HAND),
        ("Andromedan Automatons", Zone.HAND),
    ], "CR 701.23e: the text says reveal them"
    assert {reveal.source for reveal in scenario.game.reveals} == {"Andromedan Automatons"}


def test_any_number_may_be_fewer_than_all():
    """CR 701.23b: a name is a stated quality, so the searcher may leave copies
    behind."""
    scenario = _board("Andromedan Automatons", ["Andromedan Automatons"] * 3 + ["Plains"])
    library_copies = [
        c for c in scenario.player("alice").library if c.name == "Andromedan Automatons"
    ]
    scenario.will_choose_cards(library_copies[0], username="alice", source="Andromedan Automatons")

    _cast(scenario, "Andromedan Automatons")

    alice = scenario.player("alice")
    assert _names(alice.hand) == ["Andromedan Automatons"]
    assert _names(alice.library) == ["Andromedan Automatons", "Andromedan Automatons", "Plains"]


def test_any_number_with_no_copy_left_finds_nothing_and_asks_nothing():
    scenario = _board("Andromedan Automatons", ["Plains", "Squadron Hawk"])

    _cast(scenario, "Andromedan Automatons")

    alice = scenario.player("alice")
    assert alice.hand == []
    assert _names(alice.library) == ["Plains", "Squadron Hawk"]
    assert not [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_CARDS]


def test_battalion_foot_soldier_searches_its_own_name_not_the_automatons():
    """The same sentence on a second printing: the name is the source's own,
    never a fixed one."""
    scenario = _board(
        "Battalion Foot Soldier",
        ["Battalion Foot Soldier"] * 2 + ["Andromedan Automatons", "Plains"],
    )

    _cast(scenario, "Battalion Foot Soldier")

    alice = scenario.player("alice")
    assert _names(alice.hand) == ["Battalion Foot Soldier"] * 2
    assert _names(alice.library) == ["Andromedan Automatons", "Plains"]


# -- up to N ---------------------------------------------------------------------


def test_up_to_three_takes_three_of_four():
    scenario = _board("Squadron Hawk", ["Squadron Hawk"] * 4 + ["Plains"])

    _cast(scenario, "Squadron Hawk")

    alice = scenario.player("alice")
    assert _names(alice.hand) == ["Squadron Hawk"] * 3
    assert _names(alice.library) == ["Plains", "Squadron Hawk"], "the cap is three"


def test_up_to_three_with_two_copies_takes_two():
    scenario = _board("Squadron Hawk", ["Squadron Hawk"] * 2 + ["Plains"])

    _cast(scenario, "Squadron Hawk")

    assert _names(scenario.player("alice").hand) == ["Squadron Hawk"] * 2


def test_up_to_three_may_take_none_by_choosing_none():
    """CR 701.23b: finding none even with copies present is legal. The searcher
    still shuffles."""
    scenario = _board("Squadron Hawk", ["Squadron Hawk"] * 2 + ["Plains"])
    scenario.will_choose_cards(username="alice", source="Squadron Hawk")

    _cast(scenario, "Squadron Hawk")

    alice = scenario.player("alice")
    assert alice.hand == []
    assert _names(alice.library) == ["Plains", "Squadron Hawk", "Squadron Hawk"]


def test_the_opponents_library_is_never_searched():
    scenario = _board(
        "Squadron Hawk",
        ["Squadron Hawk", "Plains"],
        bob=["Squadron Hawk", "Squadron Hawk", "Plains"],
    )

    _cast(scenario, "Squadron Hawk")

    assert _names(scenario.player("alice").hand) == ["Squadron Hawk"]
    assert _names(scenario.player("bob").library) == ["Plains", "Squadron Hawk", "Squadron Hawk"]


def test_only_the_library_is_searched_not_the_hand_or_graveyard():
    scenario = _board(
        "Squadron Hawk",
        ["Squadron Hawk", "Plains"],
        hand=["Squadron Hawk"],
        graveyard=["Squadron Hawk"],
    )

    _cast(scenario, "Squadron Hawk")

    alice = scenario.player("alice")
    assert _names(alice.hand) == ["Squadron Hawk"] * 2, "the one already held plus the one found"
    assert _names(alice.graveyard) == ["Squadron Hawk"]


# -- the "may" -------------------------------------------------------------------


def test_declining_the_may_searches_nothing():
    scenario = _board("Squadron Hawk", ["Squadron Hawk"] * 2 + ["Plains"])
    scenario.will_take_the_may(False, username="alice", source="Squadron Hawk")

    _cast(scenario, "Squadron Hawk")

    alice = scenario.player("alice")
    assert alice.hand == []
    assert len(alice.library) == 3


# -- prohibition -----------------------------------------------------------------


def test_ashiok_stops_an_opponents_named_search():
    """CR 101.2: "Spells and abilities your opponents control can't cause their
    controller to search their library" - the plural named search honours it
    as every other search does."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Squadron Hawk"],
            battlefield=PLAINS,
            library=["Squadron Hawk"] * 2 + ["Plains"],
        )
        .player("bob", battlefield=["Ashiok, Dream Render"], library=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast(scenario, "Squadron Hawk")

    alice = scenario.player("alice")
    assert alice.hand == []
    assert len(alice.library) == 3


# -- a sentence naming two cards is not one name ----------------------------------


def test_a_search_naming_two_cards_with_and_or_is_not_read_as_one_name():
    """Alpine Houndmaster's "a card named A and/or a card named B" asks for two
    different names. The named-card reader must refuse it rather than read
    "A and/or a card named B" as a single name that no card has; the sentence
    stays with the reader that knows both names."""
    from magic_cards_model.machines.effects.search import _parse_you_search_named_card_clause

    clause = (
        "you may search your library for a card named Alpine Watchdog and/or a card "
        "named Igneous Cur, reveal them, put them into your hand, then shuffle"
    )

    assert _parse_you_search_named_card_clause(clause, for_spell=False) is None
