"""Look at the top N cards and split them between two destinations, general
past `Game.scry`/`Game.surveil`'s own fixed pair - `Game.look_at_top_and_split`
in `models/game.py`, exercised through `_merge_look_top_reveal_to_hand_
clauses` in `machines/effects.py`.

Duskwatch Recruiter's `{2}{G}` ability is the vehicle: "Look at the top three
cards of your library. You may reveal a creature card from among them and
put it into your hand. Put the rest on the bottom of your library in any
order." `Game.scry` always sends its `moved` half to the *bottom* and the
rest back to the *top*; this ability sends its taken half to *hand* and the
rest to the *bottom* - neither of scry's own two destinations - which is
exactly why the general primitive takes both groups off the library and lets
the caller decide, rather than writing to `player.library` itself the way
`scry`/`surveil` do.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 701.22a** - "To 'scry N' means to look at the top N cards of your
  library, then put any number of them on the bottom of your library in any
  order and the rest on top of your library in any order" - the shape
  `look_at_top_and_split` generalises; Duskwatch Recruiter's own ability is
  not itself a scry (it has no reminder text or the word "scry"), so it asks
  the identical CR 608.2d question through `DecisionKind.SCRY` without being
  one.
- **CR 608.2d** - "The player can't choose an option that's illegal or
  impossible" - taking more than one card, or one that fails the "creature"
  restriction, is exactly such an option, and `_merge_look_top_reveal_to_
  hand_clauses` raises rather than silently allowing it.
- **CR 701.23e/701.20e** - looking at a card is not revealing it to every
  player; nothing about the two cards left unlooked-at on the library
  changes, and the card taken is the only one that actually moves.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import CardSplit, DecisionKind, ScriptedAnswer
from magic_cards_model.models import Zone

from .harness import Scenario


def _script_scry_split(scenario: Scenario, *, username: str, moved) -> None:
    """Script the next `DecisionKind.SCRY`-shaped answer with `moved` as the
    taken half - `Scenario` has no dedicated helper for this shape since it
    reuses `SCRY` for a non-scry effect (see `Game.look_at_top_and_split`)."""
    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.SCRY, value=CardSplit(moved=tuple(moved)), player=username)
    )


def test_revealing_a_creature_among_the_top_three_puts_it_in_hand():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Duskwatch Recruiter", "Forest", "Forest", "Forest"],
            library=["Grizzly Bears", "Forest", "Mountain", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    recruiter = scenario.creature("Duskwatch Recruiter")
    bears, forest, mountain = scenario.top_of_library(3)
    _script_scry_split(scenario, username="alice", moved=[bears.id])

    mana = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.activate(recruiter, *mana, index=0)
    scenario.resolve_top()

    assert bears.zone is Zone.HAND
    assert bears in alice.hand
    assert forest.zone is Zone.LIBRARY
    assert mountain.zone is Zone.LIBRARY
    assert {state.id for state in alice.library[-2:]} == {forest.id, mountain.id}


def test_declining_leaves_all_three_on_the_bottom_in_looked_at_order():
    """The default `CardSplit()` answer - nothing moved, no order named -
    keeps the three looked-at cards in their original relative order, now on
    the bottom rather than the top."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Duskwatch Recruiter", "Forest", "Forest", "Forest"],
            library=["Grizzly Bears", "Forest", "Mountain", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    recruiter = scenario.creature("Duskwatch Recruiter")
    bears, forest, mountain, swamp = alice.library[:4]

    mana = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.activate(recruiter, *mana, index=0)
    scenario.resolve_top()

    assert bears not in alice.hand
    assert alice.library[0] is swamp
    assert alice.library[1:] == [bears, forest, mountain]


def test_no_creature_among_the_top_three_still_puts_all_three_on_the_bottom():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Duskwatch Recruiter", "Forest", "Forest", "Forest"],
            library=["Forest", "Mountain", "Swamp", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    recruiter = scenario.creature("Duskwatch Recruiter")
    forest, mountain, swamp = scenario.top_of_library(3)

    mana = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.activate(recruiter, *mana, index=0)
    scenario.resolve_top()

    assert alice.hand == []
    assert alice.library[-3:] == [forest, mountain, swamp]


def test_fewer_than_three_cards_in_library_looks_at_only_what_is_there():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Duskwatch Recruiter", "Forest", "Forest", "Forest"],
            library=["Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    recruiter = scenario.creature("Duskwatch Recruiter")
    bears = alice.library[0]

    mana = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.activate(recruiter, *mana, index=0)
    scenario.resolve_top()

    assert alice.hand == []
    assert alice.library == [bears]


def test_taking_more_than_one_card_is_an_illegal_choice():
    """CR 608.2d: "at most one" is not a free-form scry split - a scripted
    answer naming two cards for the taken half is refused, the same way an
    over-large `CHOOSE_TARGETS` answer already is."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Duskwatch Recruiter", "Forest", "Forest", "Forest"],
            library=["Grizzly Bears", "Basking Rootwalla", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    recruiter = scenario.creature("Duskwatch Recruiter")
    bears, rootwalla, _mountain = scenario.top_of_library(3)
    _script_scry_split(scenario, username="alice", moved=[bears.id, rootwalla.id])

    mana = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.activate(recruiter, *mana, index=0)
    with pytest.raises(ValueError, match="CR 608.2d"):
        scenario.resolve_top()


def test_taking_a_non_creature_card_is_an_illegal_choice():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Duskwatch Recruiter", "Forest", "Forest", "Forest"],
            library=["Forest", "Mountain", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    recruiter = scenario.creature("Duskwatch Recruiter")
    forest, _mountain, _swamp = scenario.top_of_library(3)
    _script_scry_split(scenario, username="alice", moved=[forest.id])

    mana = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.activate(recruiter, *mana, index=0)
    with pytest.raises(ValueError, match="CR 608.2d"):
        scenario.resolve_top()


# --------------------------------------------------------------------------
# The same four-clause family with "in a random order" as its tail
# --------------------------------------------------------------------------
#
# Duskwatch Recruiter prints "in any order"; Monumental Henge and Narset,
# Parter of Veils print "in a random order" for the identical run of four
# clauses. Until this was accepted, the whole run was rejected and both cards
# did nothing at all.
#
# The two tails are not the same instruction and are not implemented the same
# way. "In any order" is the controller's own free choice, so the answered
# order is used as given. "In a random order" is not a choice at all - and it
# is not CR 701.24a's shuffle either ("To shuffle a library or a face-down
# pile of cards, randomize the cards within it so that no player knows their
# order"): that verb is never printed here, so nothing that triggers on a
# shuffle may fire. The randomisation reuses `Game.shuffle_seed` and the
# running `shuffles_performed` counter the way `puts_graveyard_on_bottom_of_
# library` (Endurance) and Turntimber Symbiosis already do, so a scenario
# stays reproducible.
#
# CR numbers looked up with `knowledge_search(q="...", type="rules")` in the
# session that added this section: CR 701.24a (shuffle), CR 608.2d (the split
# question), CR 401.4 ("If an effect puts two or more cards in a specific
# position in a library at the same time, the owner of those cards may arrange
# them in any order").


def henge_board(library: list[str]):
    """Monumental Henge's own `{2}{W}{W}, {T}` ability, index 2 on the card
    ({T}: Add {W} is index 1, the enters-tapped static is index 0).

    Four Plains pay the activation and keep the Henge itself untapped as it
    enters ("This land enters tapped unless you control a Plains.").
    """
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Monumental Henge", "Plains", "Plains", "Plains", "Plains"],
            library=library,
        )
        .build()
    )


def test_a_random_order_tail_is_read_as_the_same_four_clause_family():
    """Monumental Henge takes the historic card and bottoms the rest."""
    scenario = henge_board(
        ["Mishra's Bauble", "Forest", "Mountain", "Swamp", "Island", "Grizzly Bears"]
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    henge = scenario.find("Monumental Henge", Zone.BATTLEFIELD)
    looked = scenario.top_of_library(5)
    (bauble,) = [state for state in looked if state.card.name == "Mishra's Bauble"]
    rest = [state for state in looked if state is not bauble]

    _script_scry_split(scenario, username="alice", moved=[bauble.id])
    mana = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")
    scenario.activate(henge, *mana, index=1)
    scenario.resolve_top()

    assert bauble in alice.hand, "Mishra's Bauble is an artifact, so it is historic"
    assert {state.id for state in alice.library[-4:]} == {state.id for state in rest}
    assert len(alice.library) == 5


def test_a_random_order_tail_actually_randomises_rather_than_appending():
    """The distinction from "in any order": the four left over are put back in
    an order nobody chose, which is why `shuffles_performed` moves even though
    CR 701.24a's shuffle never happened.
    """
    scenario = henge_board(
        ["Mishra's Bauble", "Forest", "Mountain", "Swamp", "Island", "Grizzly Bears"]
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    henge = scenario.find("Monumental Henge", Zone.BATTLEFIELD)
    (bauble,) = [
        state for state in scenario.top_of_library(5) if state.card.name == "Mishra's Bauble"
    ]
    before = scenario.game.shuffles_performed

    _script_scry_split(scenario, username="alice", moved=[bauble.id])
    mana = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")
    scenario.activate(henge, *mana, index=1)
    scenario.resolve_top()

    assert scenario.game.shuffles_performed == before + 1


def test_the_any_order_tail_still_keeps_the_answered_order():
    """The control: Duskwatch Recruiter's "in any order" is CR 401.4's free
    arrangement and must not be randomised by this change."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Duskwatch Recruiter", "Forest", "Forest", "Forest"],
            library=["Forest", "Mountain", "Swamp", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    recruiter = scenario.creature("Duskwatch Recruiter")
    forest, mountain, swamp = scenario.top_of_library(3)
    before = scenario.game.shuffles_performed

    mana = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.activate(recruiter, *mana, index=0)
    scenario.resolve_top()

    assert alice.library[-3:] == [forest, mountain, swamp]
    assert scenario.game.shuffles_performed == before


def test_narsets_minus_two_reads_the_same_family_off_a_loyalty_ability():
    """The same four clauses, on a planeswalker's own loyalty ability, with a
    quality that is a *conjunction* of negations.

    "You may reveal a noncreature, nonland card from among them" means a card
    that is neither - reading its comma as the "or" a fetchland's "Forest or
    Plains" prints would qualify every card in the game. Opt is an instant, so
    it is the one legal choice among the top four here.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Narset, Parter of Veils", "Island"],
            library=["Opt", "Forest", "Mountain", "Swamp", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    narset = scenario.find("Narset, Parter of Veils", Zone.BATTLEFIELD)
    opt, *rest = scenario.top_of_library(4)

    _script_scry_split(scenario, username="alice", moved=[opt.id])
    scenario.activate(narset, index=0)
    scenario.resolve_top()

    assert opt in alice.hand
    assert {state.id for state in alice.library[-3:]} == {state.id for state in rest}
    assert narset.counters["loyalty"] == 3, "CR 606.5: the -2 was paid"


def test_narset_cannot_take_a_land_from_among_the_top_four():
    """The fails-open case the conjunction fix closes: a Forest is nonland's
    opposite, so choosing it is CR 608.2d's illegal option."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Narset, Parter of Veils", "Island"],
            library=["Forest", "Mountain", "Swamp", "Island", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    narset = scenario.find("Narset, Parter of Veils", Zone.BATTLEFIELD)
    (forest, *_) = scenario.top_of_library(4)

    _script_scry_split(scenario, username="alice", moved=[forest.id])
    scenario.activate(narset, index=0)

    with pytest.raises(ValueError):
        scenario.resolve_top()


# -- The quantity is read, not fixed at "a": Reality Heist ("up to two") and
# Lead the Stampede ("any number of", CR 107.1c) ----------------------------


def test_reality_heist_reveals_up_to_two_artifacts_and_takes_both():
    """Reality Heist: "Look at the top seven cards of your library. You may
    reveal up to two artifact cards from among them and put them into your
    hand. Put the rest on the bottom of your library in a random order." -
    the same four-clause family as Duskwatch Recruiter, with "up to two"
    where Duskwatch prints "a" and "them" where it prints "it"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Reality Heist"],
            library=[
                "Mishra's Bauble",
                "Vexing Bauble",
                "Forest",
                "Mountain",
                "Swamp",
                "Plains",
                "Grizzly Bears",
            ],
            battlefield=["Island"] * 7,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bauble, vexing, forest, mountain, swamp, plains, bears = scenario.top_of_library(7, "alice")
    _script_scry_split(scenario, username="alice", moved=[bauble.id, vexing.id])

    scenario.cast_and_resolve("Reality Heist", *scenario.untapped_sources(*(["Island"] * 7)))

    assert bauble.zone is Zone.HAND and bauble in alice.hand
    assert vexing.zone is Zone.HAND and vexing in alice.hand
    assert {state.id for state in alice.library[-5:]} == {
        state.id for state in (forest, mountain, swamp, plains, bears)
    }


def test_reality_heist_declining_leaves_every_artifact_on_the_bottom():
    """The default answer (nothing moved) is legal for "up to two" - CR
    608.2d never forces a take when the printed maximum is not a floor."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Reality Heist"],
            library=["Mishra's Bauble", "Forest", "Mountain", "Swamp", "Plains", "Island", "Opt"],
            battlefield=["Island"] * 7,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    looked = scenario.top_of_library(7, "alice")

    scenario.cast_and_resolve("Reality Heist", *scenario.untapped_sources(*(["Island"] * 7)))

    assert alice.hand == []
    assert {state.id for state in alice.library} == {state.id for state in looked}


def test_lead_the_stampede_takes_any_number_of_creatures():
    """Lead the Stampede: "Look at the top five cards of your library. You
    may reveal any number of creature cards from among them and put the
    revealed cards into your hand. Put the rest on the bottom of your library
    in a random order." CR 107.1c's "any number" is no fixed ceiling - taking
    three of the five looked at is as legal an answer as taking none."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lead the Stampede"],
            library=["Grizzly Bears", "Grizzly Bears", "Grizzly Bears", "Forest", "Mountain"],
            battlefield=["Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bear1, bear2, bear3, forest, mountain = scenario.top_of_library(5, "alice")
    _script_scry_split(scenario, username="alice", moved=[bear1.id, bear2.id, bear3.id])

    scenario.cast_and_resolve(
        "Lead the Stampede", *scenario.untapped_sources("Forest", "Forest", "Forest")
    )

    for bear in (bear1, bear2, bear3):
        assert bear.zone is Zone.HAND and bear in alice.hand
    assert {state.id for state in alice.library} == {forest.id, mountain.id}
