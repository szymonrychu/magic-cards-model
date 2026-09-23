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
