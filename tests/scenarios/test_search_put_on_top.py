"""Scenario: a general "search your library for a `<card description>`[,
reveal it,] then shuffle and put that card on top [of your library]" reader
(CR 701.23, CR 701.24a, CR 701.20d), widened from the mandatory-reveal
`_SEARCH_REVEAL_SHUFFLE_TOP_RE` shape the FRA tutor family
(`test_fra_s8_search_reveal_shuffle_top.py`) already reads.

Insatiable Avarice's own first Spree mode - "Search your library for a card,
then shuffle and put that card on top." - prints **no** reveal at all
(CR 701.20a's reveal is its own instruction, not implied by a search), which
the mandatory-reveal regex could not match: the whole mode fell through as
unread, and choosing it left a `ModeNotice` behind instead of running.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 702.172a** - Spree: "Choose one or more modes. As an additional cost
  to cast this spell, pay the costs associated with those modes."
- **CR 701.23a/701.23d** - "search your library for a card" with no stated
  quality means every card qualifies.
- **CR 701.20a** - revealing shows a card without moving it; it only happens
  when the instruction actually names it.
- **CR 701.24a** - the library is shuffled after the search.
- **CR 701.20d/CR 401.2** - a card put on top sits above every card already
  there.

Ainok Guide (off-pool, confirmed with `scripts/add_card.py`) is the proof
that the mandatory-reveal branch still works: its own second "choose one"
mode - "Search your library for a basic land card, reveal it, then shuffle
and put that card on top." - is a triggered ability, not a spell, and does
print the reveal Insatiable Avarice's own mode omits.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_insatiable_avarice_mode_one_alone_puts_the_found_card_on_top_unrevealed():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Insatiable Avarice"],
            battlefield=["Swamp"] * 3,
            library=["Mountain", "Forest", "Island", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    forest = next(state for state in alice.library if state.name == "Forest")
    scenario.will_choose_cards(forest, username="alice")

    casting = scenario.cast("Insatiable Avarice")
    casting.choose_modes([1])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*(["Swamp"] * 3)))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert alice.library[0] is forest
    assert len(alice.library) == 4
    # CR 701.20a: no printed reveal, no real reveal - unlike Ainok Guide's
    # own mode below, which does print one.
    assert not [r for r in scenario.game.reveals if r.card_name == "Forest"]


def test_insatiable_avarice_both_modes_drain_and_put_the_found_card_on_top():
    """Modes 1 and 2 chosen together - CR 118.8a charges both modes' own
    additional costs, and CR 700.2a runs both effects, in the order printed:
    the search first, the targeted drain second."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Insatiable Avarice"],
            battlefield=["Swamp"] * 5,
            library=["Mountain", "Forest", "Island", "Plains"],
        )
        .player("bob", library=["Mountain"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    forest = next(state for state in alice.library if state.name == "Forest")
    scenario.will_choose_cards(forest, username="alice")
    life_before = bob.life
    hand_before = len(bob.hand)

    casting = scenario.cast("Insatiable Avarice")
    casting.choose_modes([1, 2])
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*(["Swamp"] * 5)))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert alice.library[0] is forest
    assert len(alice.library) == 4
    assert bob.life == life_before - 3
    assert len(bob.hand) == hand_before + 3


def test_ainok_guide_mode_two_finds_a_basic_land_and_reveals_it():
    """Ainok Guide's own ETB "choose one -" (CR 603.3c, CR 700.2): a
    *triggered ability*, not a spell, and mode 2's own search prints
    "reveal it" - the mandatory-reveal branch the widened regex must still
    honour."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ainok Guide"],
            battlefield=["Forest", "Forest"],
            library=["Mountain", "Grizzly Bears", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    mountain = next(state for state in alice.library if state.name == "Mountain")
    scenario.will_choose_mode(
        "Search your library for a basic land card, reveal it, then shuffle and put that "
        "card on top.",
        username="alice",
    )
    scenario.will_choose_cards(mountain, username="alice")

    forests = scenario.untapped_sources("Forest", "Forest")
    casting = scenario.cast("Ainok Guide", username="alice")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *forests)
    scenario.put_on_stack(casting)
    scenario.resolve_top()  # Ainok Guide enters; its ETB trigger goes on the stack
    scenario.resolve_top()  # the ETB trigger itself resolves

    assert alice.library[0] is mountain
    assert len(alice.library) == 3
    (reveal,) = [r for r in scenario.game.reveals if r.card_name == "Mountain"]
    assert reveal.zone is Zone.LIBRARY


# -- Old Thrush: the same reader, reached through a two-clause split -------
#
# Old Thrush: "When this creature enters, you gain 2 life. You may search
# your library for a basic land card, reveal it, then shuffle and put that
# card on top." `_parse_search_reveal_shuffle_top_clause`/`_SEARCH_REVEAL_
# SHUFFLE_TOP_RE` (proven above on Insatiable Avarice and Ainok Guide)
# already read this exact sentence on its own - the gap was upstream of it,
# in how the sentence reaches a dispatcher at all. `_parse_mixed_clauses`'
# own whole-text special case for this shape only fires when the search
# sentence *is* the whole effect text (Campus Guide's own "When this
# creature enters, you may search your library for a basic land card,
# reveal it, then shuffle and put that card on top." has nothing else in
# it); Old Thrush prints a life-gain sentence first, so the whole-text
# `fullmatch` never even tries. The ordinary per-clause split then cuts the
# search sentence itself in two, because `_CLAUSE_SEPARATOR`'s bare " and "
# (inside "... then shuffle and put that card on top") has no way to tell
# that particular "and" apart from a genuine second instruction - the same
# shape `_rejoin_search_clauses` already reattaches for a bare "shuffle"
# split off a `_SEARCH_AND_PUT_RE` clause, just one step later in the same
# sentence.
#
# The fix widens `_rejoin_search_clauses` with a second reattachment rule: a
# clause matching `_BARE_PUT_ON_TOP_RE` ("put that card on top[ of your
# library]") is folded back into the clause before it whenever that clause
# mentions a search and already ends in "shuffle".
#
# No second printing on Scryfall pairs this exact search-reveal-shuffle-top
# sentence with a *preceding*, unrelated sentence the way Old Thrush's own
# "you gain 2 life." does - every other printing of the shape has the search
# as its entire trigger text (checked in the session that wrote this
# addition); see the dated `MEMORY.md` line.


def _old_thrush_board(*, library):
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Old Thrush"], battlefield=["Forest", "Forest"], library=library)
        .player("bob")
    )


def test_old_thrush_gains_2_life_and_puts_a_found_basic_land_on_top():
    scenario = _old_thrush_board(library=["Grizzly Bears", "Mountain", "Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    mountain = next(state for state in alice.library if state.name == "Mountain")
    life_before = alice.life
    sources = scenario.untapped_sources("Forest", "Forest")

    scenario.will_take_the_may(True, username="alice", source="Old Thrush")
    scenario.cast_and_resolve("Old Thrush", *sources)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    assert alice.life == life_before + 2
    assert alice.library[0] is mountain, "the found land goes on top, above everything else"
    assert mountain.zone is Zone.LIBRARY


def test_old_thrush_declining_the_search_still_gains_the_life():
    scenario = _old_thrush_board(library=["Grizzly Bears", "Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    original_top = alice.library[0]
    life_before = alice.life
    sources = scenario.untapped_sources("Forest", "Forest")

    scenario.will_take_the_may(False, username="alice", source="Old Thrush")
    scenario.cast_and_resolve("Old Thrush", *sources)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    assert alice.life == life_before + 2
    assert alice.library[0] is original_top, "declining the search leaves the library untouched"
