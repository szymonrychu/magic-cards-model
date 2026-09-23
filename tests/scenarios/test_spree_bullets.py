"""Scenario: Spree's own bullet (CR 702.172b), a plus sign rather than the
ordinary `•` `machines/modes.py` already read. Before this fix, `_parse`'s
own `bullets` detection matched only `•`, so a Spree card's `+`-prefixed
modes were never even found - the card read as not modal at all, and its
whole text fell through to a plain-clause parser that had no channel for a
mode's own additional cost (CR 700.2h), meaning it could not be cast for any
of its modes at all.

The fix widens bullet detection to `•` or `+` followed by whitespace, told
apart from a loyalty ability's own "+1:"/"+2:" line (CR 606.4) by that
whitespace - a loyalty symbol is always followed immediately by a digit, a
Spree bullet always by a space before its cost. Once a Spree card's modes
are found at all, every other piece - `Mode.cost` (CR 700.2h, already read
generally for Tiered), the parenthetical "Choose one or more" instruction
(already read generally for the same reason), and `machines/casting.py`'s
own per-mode cost charging - was already general and needed no change.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 702.172a** - "Spree is a static ability ... Spree means 'Choose one
  or more modes. As an additional cost to cast this spell, pay the costs
  associated with those modes.'"
- **CR 702.172b** - the `+` bullet, "a visual reminder ... do not have
  additional rules meaning" - it changes nothing about how the modes
  themselves work, only how the choice is printed.
- **CR 700.2a** - modes are chosen as the spell is cast, and (CR 702.42b's
  general statement of it) each chosen mode resolves in the order printed.
- **CR 118.8a** - each mode's own cost is an additional cost, paid together
  with the spell's own printed mana cost, not instead of it.
- **CR 101.3** - "any part of an instruction that's impossible to perform is
  ignored" does not licence dropping a *readable* mode because a different
  mode on the same spell is not yet modelled - `resolve_modal_spell`'s own
  per-mode fail-closed `ModeNotice` is what keeps the readable mode running.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.modes import modal_profile
from magic_cards_model.models import Zone
from magic_cards_model.models.mana import ManaCost
from tests.scenarios.harness import Scenario


def test_smugglers_surprise_is_read_as_modal_with_all_three_plus_bulleted_modes():
    """The parsing half on its own: three modes, their own costs read, "one
    or more" widened to (1, 3) - none of this existed before the bullet fix,
    since the card was not recognised as modal at all.
    """
    from tests.cards import card

    profile = modal_profile(card("Smuggler's Surprise"))
    assert profile is not None
    assert profile.understood
    assert profile.minimum == 1
    assert profile.maximum == 3
    assert [mode.cost for mode in profile.modes] == ["{2}", "{4}{G}", "{1}"]


def test_smugglers_surprise_charges_the_sum_of_every_chosen_modes_cost():
    """CR 118.8a: the base {G} plus every chosen mode's own cost, all three
    this time - {G} + {2} + {4}{G} + {1} = {7}{G}{G}."""
    scenario = (
        Scenario()
        .player("alice", hand=["Smuggler's Surprise", "Grizzly Bears"], library=["Mountain"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Smuggler's Surprise")
    casting.choose_modes([1, 2, 3])

    assert casting.total_cost.mana == ManaCost.parse("{7}{G}{G}")


def test_smugglers_surprise_all_three_modes_resolve_together():
    """All three modes are read (T16 closed the last two): mode 1's own
    "mill four. You may put up to two creature and/or land cards from among
    the milled cards into your hand" (`_mill_then_may_take_from_milled_
    runner`, widened for the "and/or" quality), mode 2's own "put up to two
    creature cards from your hand onto the battlefield", and mode 3's own
    "creatures you control with power 4 or greater gain hexproof and
    indestructible until end of turn" (the power-filtered mass-pump group
    grant) - no `ModeNotice` left for any of them.

    The queued `will_choose_cards` answers are matched in resolution order
    (CR 700.2a: modes run in the order printed) - mode 1's own mill-choice
    decision first (declined, so the milled Mountains stay in the
    graveyard), then mode 2's own battlefield-choice decision.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Smuggler's Surprise", "Grizzly Bears"],
            battlefield=["Forest"] * 9,
            library=["Mountain"] * 4,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Forest"] * 9))
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    scenario.will_choose_cards(username="alice", source="Smuggler's Surprise")
    scenario.will_choose_cards(bears, username="alice", source="Smuggler's Surprise")

    casting = scenario.cast("Smuggler's Surprise")
    casting.choose_modes([1, 2, 3])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    alice = scenario.player("alice")
    assert any(state.name == "Grizzly Bears" for state in scenario.game.battlefield), (
        "mode 2's own put-onto-the-battlefield ran"
    )
    assert bears not in alice.hand
    assert len(alice.library) == 0, "mode 1's own mill ran (CR 701.17a)"
    assert len([c for c in alice.graveyard if c.name == "Mountain"]) == 4, (
        "the milled Mountains stayed in the graveyard - the mill-choice decision was declined"
    )
    assert not scenario.game.mode_notices, "every mode now reads; none is left unread"


def test_three_steps_ahead_counters_a_spell_and_loots_in_the_same_cast():
    """Three Steps Ahead (off-pool, modern-legal): "+ {1}{U} — Counter
    target spell." and "+ {2} — Draw two cards, then discard a card."
    chosen together - a different card, a different mode count (three
    printed, two chosen), a targeted mode alongside an untargeted one, and a
    counterspell rather than a battlefield-changing effect, proving the
    bullet fix generally rather than confirming Smuggler's Surprise's own
    sentence alone.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player(
            "alice",
            hand=["Three Steps Ahead", "Mountain"],
            battlefield=["Island"] * 5,
            library=["Mountain", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (bob_mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", bob_mountain, username="bob", targets=["alice"]
    )
    scenario.pass_priority("bob")

    islands = scenario.untapped_sources(*(["Island"] * 5), username="alice")
    mountain = scenario.find("Mountain", Zone.HAND, "alice")
    casting = scenario.cast("Three Steps Ahead", username="alice")
    casting.choose_modes([1, 3])
    casting.choose_targets([bolt])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *islands)
    scenario.put_on_stack(casting)
    scenario.will_choose_cards(mountain, username="alice", source="Three Steps Ahead")

    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD, "CR 701.6a: countered"
    alice = scenario.player("alice")
    assert alice.life == 20, "Lightning Bolt never resolved"
    # Hand before the draw: one Mountain. Draw two (CR 121.1), discard one
    # (CR 701.9a): three Mountains in hand, minus the discarded one, is two.
    assert len(alice.hand) == 2 and all(c.name == "Mountain" for c in alice.hand)
    assert {c.name for c in alice.graveyard} == {"Three Steps Ahead", "Mountain"}


# -- Final Showdown (off-set): choosing 1, 2, or all 3 modes; zero refused; --
# -- printed order, not announcement order ------------------------------- --


def test_final_showdown_is_read_with_all_three_plus_bulleted_modes():
    from tests.cards import card

    profile = modal_profile(card("Final Showdown"))
    assert profile is not None
    assert profile.understood
    assert profile.minimum == 1
    assert profile.maximum == 3
    assert [mode.cost for mode in profile.modes] == ["{1}", "{1}", "{3}{W}{W}"]


def _final_showdown_board(*, alice_battlefield: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice", hand=["Final Showdown"], battlefield=["Plains"] * 8 + (alice_battlefield or [])
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_choosing_one_mode_charges_only_that_modes_own_cost():
    """Mode 3, "Destroy all creatures" - {3}{W}{W} on top of the printed {W}
    (CR 118.8a) is {3}{W}{W}{W}."""
    scenario = _final_showdown_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Final Showdown")
    casting.choose_modes([3])

    assert casting.total_cost.mana == ManaCost.parse("{3}{W}{W}{W}")


def test_choosing_two_modes_sums_both_their_costs():
    """Modes 1 and 2, {1} each - CR 702.172a charges a chosen mode's own
    additional cost whether or not this wave can also read its effect (modes
    1 and 2's own clauses are not read yet; the mechanism this file proves is
    the cost summing and the choice count, not every mode's own resolution -
    see this file's own module docstring)."""
    scenario = _final_showdown_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Final Showdown")
    casting.choose_modes([1, 2])

    assert casting.total_cost.mana == ManaCost.parse("{2}{W}")


def test_choosing_all_three_modes_sums_every_cost():
    scenario = _final_showdown_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Final Showdown")
    casting.choose_modes([1, 2, 3])

    assert casting.total_cost.mana == ManaCost.parse("{5}{W}{W}{W}")


def test_choosing_zero_modes_is_refused():
    """CR 702.172a: "Choose one or more modes" - a minimum of one, same as
    every other Spree card in this file."""
    scenario = _final_showdown_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Final Showdown")
    with pytest.raises(ValueError, match="too few modes"):
        casting.choose_modes([])


def test_modes_are_recorded_in_printed_order_regardless_of_choice_order():
    """CR 702.42b's general statement (this file's own module docstring):
    each chosen mode resolves in the order printed on the card, not the
    order it was named in. Choosing "3, 1" still records "1, 3" - the fix
    lives in `ModalProfile.resolve` (`machines/modes.py`), general to every
    modal card, not special-cased to Spree or to this one printing."""
    scenario = _final_showdown_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Final Showdown")
    casting.choose_modes([3, 1])

    assert casting.chosen_mode_numbers == [1, 3]


def test_the_destroy_mode_still_runs_however_it_was_ordered_among_the_choice():
    """Mode 3 ("Destroy all creatures") is the one mode this wave reads
    (this file's own module docstring); choosing it alongside an unread mode,
    named *first*, proves the unread mode's own `ModeNotice` does not stop
    the readable one from running (CR 101.3 does not excuse a mode that
    parses fine because a different mode on the same spell does not)."""
    scenario = _final_showdown_board(alice_battlefield=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    own_bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    their_bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")

    casting = scenario.cast("Final Showdown")
    casting.choose_modes([3, 1])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*(["Plains"] * 8)))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert own_bears.zone is Zone.GRAVEYARD
    assert their_bears.zone is Zone.GRAVEYARD
    notice_modes = {notice.mode_number for notice in scenario.game.mode_notices}
    assert notice_modes == {1}, "mode 1 fails closed with a notice, not silence"
