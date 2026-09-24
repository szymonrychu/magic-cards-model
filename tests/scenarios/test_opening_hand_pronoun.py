"""CR 103.6a's own template, printed with the card's own name and a
gendered pronoun instead of "this card"/"it" - Quicksilver, Brash Blur's
own "If Quicksilver, Brash Blur is in your opening hand, you may begin the
game with him on the battlefield."

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 103.6a** - "If a card allows a player to begin the game with that
  card on the battlefield, the player taking this action puts that card
  onto the battlefield."
- **CR 201.5c** - a legendary card's own shortened self-reference, the
  same rule `machines/abilities.py::self_normalized_effect_text` already
  reads for every other self-named effect in the pool.

`machines/opening_hand.py::_BEGIN_ON_BATTLEFIELD` only ever read the
literal "If this card is in your opening hand, ..." - `test_opening_hand_
begin_on_battlefield.py`'s own Leyline of Sanctity ("If this card is in
your opening hand, you may begin the game with it on the battlefield.")
and Gemstone Caverns both use that exact wording. Quicksilver's own
printing names itself instead, the same CR 201.5c self-reference every
other reader in this codebase already handles by rewriting a card's own
name to CR 700.7's "this permanent" - `read_opening_hand_line` (widened
this task) now tries `self_normalized_effect_text` as a fallback once the
unnormalized line has already failed to match, the same "raw first,
normalized fallback" order `machines/effects.py`'s own `activated_effect_
for`/`trigger_effect_for` already use for the identical CR 201.5 gap.

No off-pool proof printing exists for this exact pronoun/name-referenced
CR 103.6a shape: a full sweep of the Scryfall bulk data in the session that
wrote this file (`oracle-cards.jsonl`, "begin the game with" minus "this
card") turned up nothing else printed this way, legal or not - recorded in
a dated MEMORY.md line per this campaign's own rule (k). The widening
itself rests on `self_normalized_effect_text`, general machinery already
proven against dozens of other cards throughout this codebase, not new to
this task.
"""

from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from magic_cards_model.machines.opening_hand import (
    OpeningHandActionKind,
    OpeningHandNotice,
    read_opening_hand_actions,
    read_opening_hand_line,
)
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card

from .harness import PlayedScenario, Scenario


def will_take(scenario: PlayedScenario, player: str, source: str) -> None:
    scenario.game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.OPENING_HAND_ACTION, value=True, player=player, source=source
        )
    )


# ---------------------------------------------------------------------------
# The template, read off the printing (CR 103.6a, CR 201.5c)
# ---------------------------------------------------------------------------


def test_quicksilvers_own_line_is_read_with_no_notice():
    actions, notices = read_opening_hand_actions(card("Quicksilver, Brash Blur"))

    assert notices == []
    (action,) = actions
    assert action.kind is OpeningHandActionKind.BEGIN_ON_BATTLEFIELD
    assert action.requires_not_starting_player is False
    assert action.counter is None
    assert action.rider == ""


def test_the_sweep_counts_quicksilvers_opening_hand_line_as_handled():
    (clause,) = [
        c for c in classify_clauses(card("Quicksilver, Brash Blur")) if "opening hand" in c.text
    ]

    assert clause.category == HANDLED


def test_a_card_that_genuinely_says_this_card_is_unaffected_by_the_widening():
    """The widening is a fallback tried only once the unnormalized line has
    already failed - a printing that already says "this card" (Leyline of
    Sanctity, `test_opening_hand_begin_on_battlefield.py`'s own subject)
    still reads on its first, unnormalized attempt."""
    actions, notices = read_opening_hand_actions(card("Leyline of Sanctity"))

    assert notices == []
    (action,) = actions
    assert action.kind is OpeningHandActionKind.BEGIN_ON_BATTLEFIELD


def test_a_line_that_is_not_the_template_at_all_still_gets_a_notice():
    """The widening is not a blanket "opening hand" catch-all - a paragraph
    that mentions an opening hand but matches neither shape, whole or
    self-normalized, is still refused with a notice."""
    read = read_opening_hand_line(
        "Quicksilver, Brash Blur", "If Quicksilver is in your opening hand, discard it."
    )
    assert isinstance(read, OpeningHandNotice)
    assert "matches neither" in read.reason


# ---------------------------------------------------------------------------
# Taking it (CR 103.6, CR 103.8)
# ---------------------------------------------------------------------------


def test_a_taken_quicksilver_begins_the_game_on_the_battlefield():
    scenario = (
        Scenario()
        .player("alice", hand=["Quicksilver, Brash Blur", "Mountain"], library=["Forest"] * 3)
        .player("bob", library=["Mountain"] * 3)
        .build()
    )
    will_take(scenario, "alice", "Quicksilver, Brash Blur")

    scenario.game.take_opening_hand_actions()

    alice = scenario.player("alice")
    assert [state.name for state in scenario.game.battlefield] == ["Quicksilver, Brash Blur"]
    assert [state.name for state in alice.hand] == ["Mountain"]


def test_declining_leaves_quicksilver_in_hand():
    """CR 103.6's "may" - an unscripted player declines."""
    scenario = (
        Scenario()
        .player("alice", hand=["Quicksilver, Brash Blur"], library=["Forest"] * 3)
        .player("bob", library=["Mountain"] * 3)
        .build()
    )

    scenario.game.take_opening_hand_actions()

    assert scenario.game.battlefield == []
    assert [state.name for state in scenario.player("alice").hand] == ["Quicksilver, Brash Blur"]


def test_a_quicksilver_begun_on_the_battlefield_has_haste_at_once():
    """A permanent begun on the battlefield before the first turn (CR
    103.8) - its own printed haste (a separate keyword line, unaffected by
    the opening-hand widening) is already live."""
    scenario = (
        Scenario()
        .player("alice", hand=["Quicksilver, Brash Blur"], library=["Forest"] * 3)
        .player("bob", library=["Mountain"] * 3)
        .build()
    )
    will_take(scenario, "alice", "Quicksilver, Brash Blur")

    scenario.game.take_opening_hand_actions()

    quicksilver = next(
        state for state in scenario.game.battlefield if state.name == "Quicksilver, Brash Blur"
    )
    assert has_keyword(quicksilver, "haste", scenario.game) is True
