"""Scenario: a search naming more than one card at once - "up to N `<quality>`
cards" (CR 701.23a, 701.23b) and CR 115.6's "up to N" read onto a search
rather than a target.

Primeval Titan's own trigger and Scapeshift both search for more than one
land in a single instruction, and Scapeshift's own count is not printed at
all - it is however many lands the player actually chose to sacrifice, a real
CR 608.2c choice this file drives explicitly rather than assuming.

The rules this file asserts, every one looked up with `knowledge_search(q=...,
type="rules")` in the session that wrote it:

- **CR 603.6a** - "Enters-the-battlefield abilities trigger when a permanent
  enters the battlefield."
- **CR 508.3a** - "Whenever [a creature] attacks, ..." triggers when that
  creature is declared as an attacker.
- **CR 701.23a** - to search a zone, look at every card in it and find one
  matching the description.
- **CR 701.23b** - a stated-quality search in a hidden zone need not find
  everything present, even when it is there.
- **CR 701.24a/701.24b** - the searched zone is shuffled afterward, and the
  found cards are not part of that shuffle.
- **CR 115.6** - "up to N" targets/counts may legally choose fewer than N,
  including zero.
- **CR 107.1c** - "any number" means "the highest number of them permitted by
  the effect", zero upward.
- **CR 701.21a** - to sacrifice a permanent, its controller moves it from the
  battlefield directly to its owner's graveyard.
- **CR 110.5b** - permanents enter the battlefield untapped unless a spell or
  ability says otherwise.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import effect_for
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_primeval_titan_enters_and_searches_two_lands_tapped():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Primeval Titan"],
            library=["Forest", "Mountain", "Swamp"],
            battlefield=["Forest", "Forest", "Forest", "Forest", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Forest"] * 6))
    titan = scenario.cast_and_resolve("Primeval Titan", *sources)
    scenario.pass_until_resolved()  # the enters trigger, put on the stack separately

    assert titan.zone is Zone.BATTLEFIELD
    tapped_new = [card for card in scenario.game.battlefield if card.name == "Mountain"]
    assert len(tapped_new) == 1, "the second library card (Mountain) was found"
    assert all(card.tapped for card in tapped_new), "CR 614.1c: the sentence says tapped"
    assert "Swamp" in [c.name for c in scenario.player("alice").library], (
        "up to two: only the top two library cards were taken"
    )


def test_primeval_titan_also_searches_when_it_attacks():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest", "Mountain"],
            battlefield=["Primeval Titan", "Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    titan = scenario.find("Primeval Titan", Zone.BATTLEFIELD)
    scenario.attack_with(titan)
    scenario.pass_until_resolved()

    battlefield_names = scenario.battlefield_names()
    assert battlefield_names.count("Forest") == 2, "one Forest was already there, one was found"
    assert "Mountain" in battlefield_names


def test_primeval_titan_search_may_be_declined():
    """CR 115.6/CR 608.2d: "you may search" is a real choice, not a formality."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Primeval Titan"],
            library=["Forest", "Mountain"],
            battlefield=["Forest", "Forest", "Forest", "Forest", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, username="alice", source="Primeval Titan")
    sources = scenario.untapped_sources(*(["Forest"] * 6))
    scenario.cast_and_resolve("Primeval Titan", *sources)
    scenario.pass_until_resolved()  # the enters trigger, put on the stack separately

    library_names = [card.name for card in scenario.player("alice").library]
    assert set(library_names) == {"Forest", "Mountain"}, "declined: nothing left the library"


def scapeshift_board() -> Scenario:
    return Scenario().player(
        "alice",
        hand=["Scapeshift"],
        library=["Mountain", "Swamp", "Island", "Plains"],
        battlefield=["Forest", "Forest", "Forest", "Forest"],
    )


def test_scapeshift_sacrifices_chosen_lands_and_finds_that_many_tapped():
    scenario = scapeshift_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    sacrificed = forests[:3]
    scenario.will_choose_cards(*sacrificed, username="alice", source="Scapeshift")
    scapeshift = scenario.cast_and_resolve("Scapeshift", *forests)

    assert scapeshift.zone is Zone.GRAVEYARD
    for land in sacrificed:
        assert land.zone is Zone.GRAVEYARD, "CR 701.21a: sacrificed lands go to the graveyard"
    remaining_forest = [
        card for card in scenario.game.permanents_controlled_by("alice") if card.name == "Forest"
    ]
    assert len(remaining_forest) == 1, "one Forest was never offered up"
    found = [
        card
        for card in scenario.game.permanents_controlled_by("alice")
        if card.name in ("Mountain", "Swamp", "Island")
    ]
    assert len(found) == 3, "up to that many: exactly the three sacrificed"
    assert all(card.tapped for card in found), "CR 614.1c: the sentence says tapped"


def test_scapeshift_sacrificing_no_lands_finds_none():
    """CR 107.1c: "any number" legally includes zero - declining changes
    nothing about the board beyond the spell itself resolving."""
    scenario = scapeshift_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    forests = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    scenario.will_choose_cards(username="alice", source="Scapeshift")
    scenario.cast_and_resolve("Scapeshift", *forests)

    assert (
        len(
            [
                card
                for card in scenario.game.permanents_controlled_by("alice")
                if card.name == "Forest"
            ]
        )
        == 4
    )
    assert len(alice.library) == 4, "nothing was searched for or removed"


def test_scapeshift_cannot_sacrifice_more_lands_than_are_there():
    """`Game.ask` refuses an answer naming more cards than were offered - a
    scenario cannot script a way around CR 601.2b's "only what is actually
    there"."""
    import pytest

    scenario = scapeshift_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    library_card = scenario.player("alice").library[0]
    scenario.will_choose_cards(*forests, library_card, username="alice", source="Scapeshift")
    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Scapeshift", *forests)


# -- Behold the Beyond: CR 701.23d's plain, un-"up to" quantity - "Search
# your library for three cards" - rather than a stated quality's "up to N".
# `_SEARCH_AND_PUT_RE` used to accept only the literal article "a"/"an", so
# this shape never matched at all; the count slot now reads any `{COUNT}`.
#
# Behold the Beyond's own first sentence, "Discard your hand.", is a
# separate, pre-existing gap this wave does not own (no parser anywhere reads
# a bare "discard your hand" - as opposed to a counted "discard N cards" -
# and it was not part of any family this sweep assigned; found here and
# reported, not fixed). Casting the whole card through the ordinary path
# would exercise that unrelated gap and fail closed on it before ever
# reaching the search sentence this file is actually about, so this drives
# the search clause directly - `effect_for` on the real printed sentence,
# run against a real board and the real `StackObject` casting the real card
# produces - rather than through the two-clause `cast_and_resolve` that gap
# currently blocks.
_BEHOLD_THE_BEYOND_SEARCH = (
    "Search your library for three cards, put them into your hand, then shuffle."
)


def test_behold_the_beyond_finds_the_printed_three_cards():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Behold the Beyond"],
            library=["Forest", "Mountain", "Swamp", "Island", "Plains"],
            battlefield=["Swamp"] * 7,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.LIBRARY, "alice")
    mountain = scenario.find("Mountain", Zone.LIBRARY, "alice")
    swamp = scenario.find("Swamp", Zone.LIBRARY, "alice")
    sources = scenario.untapped_sources(*(["Swamp"] * 7))

    scenario.will_choose_cards(
        forest, mountain, swamp, username="alice", source="Behold the Beyond"
    )
    casting = scenario.cast("Behold the Beyond")
    casting.determine_cost()
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    stack_object = scenario.put_on_stack(casting)

    effect = effect_for("Behold the Beyond", _BEHOLD_THE_BEYOND_SEARCH)
    assert effect is not None
    effect(scenario.game, stack_object)

    alice = scenario.player("alice")
    assert {c.name for c in alice.hand} == {"Forest", "Mountain", "Swamp"}
    assert {c.name for c in alice.library} == {"Island", "Plains"}, (
        "exactly three left the library - not one, and not all five"
    )


def test_behold_the_beyond_finds_fewer_than_three_when_the_library_runs_short():
    """CR 701.23d: "must find that many cards (or as many as possible, if the
    zone doesn't contain that many)" - a two-card library still finds both,
    never an error and never a third card that is not there."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Behold the Beyond"],
            library=["Forest", "Mountain"],
            battlefield=["Swamp"] * 7,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Swamp"] * 7))

    casting = scenario.cast("Behold the Beyond")
    casting.determine_cost()
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    stack_object = scenario.put_on_stack(casting)

    effect = effect_for("Behold the Beyond", _BEHOLD_THE_BEYOND_SEARCH)
    assert effect is not None
    effect(scenario.game, stack_object)

    alice = scenario.player("alice")
    assert {c.name for c in alice.hand} == {"Forest", "Mountain"}
    assert alice.library == []


# -- The Earth King: "up to that many" carries a count from an earlier
# instruction (here, how many qualifying creatures attacked) rather than
# printing one - Group 0b's own channel, not built yet. `_SEARCH_AND_PUT_RE`
# recognises the shape (so the clause is not treated as unreadable
# altogether) but `_read_search_count` refuses to guess the number, and
# `_unreadable_search_count` turns that refusal into a recorded notice
# instead of the trigger silently doing nothing.


def test_the_earth_king_records_a_notice_instead_of_guessing_that_many():
    """ "Whenever one or more creatures you control with power 4 or greater
    attack, search your library for up to that many basic land cards, put
    them onto the battlefield tapped, then shuffle." Anafenza (4/4) attacking
    fires the trigger; the search itself is left to Group 0b and is recorded
    here rather than run - the library is untouched."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Earth King", "Anafenza, the Foremost"],
            library=["Forest", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    anafenza = scenario.find("Anafenza, the Foremost", Zone.BATTLEFIELD, "alice")
    scenario.attack_with(anafenza)
    scenario.pass_until_resolved()

    assert scenario.player("alice").library == [
        scenario.find("Forest", Zone.LIBRARY, "alice"),
        scenario.find("Mountain", Zone.LIBRARY, "alice"),
    ], "the search was not run - Group 0b's own carried-count channel"
    (notice,) = scenario.game.search_description_notices
    assert notice.source_name == "The Earth King"
    assert "that many" in notice.text
