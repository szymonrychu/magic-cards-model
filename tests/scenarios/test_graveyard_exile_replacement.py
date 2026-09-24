""" "If [a quality of card] would be put into [whose] graveyard [from
anywhere], exile it instead" (CR 614.1a, 700.4, 603.2g).

Rest in Peace: "If a card or token would be put into a graveyard from
anywhere, exile it instead." Sanctifier en-Vec, the colour-filtered variant:
"If a black or red permanent, spell, or card not on the battlefield would be
put into a graveyard, exile it instead." Leyline of the Void (the proof
printing - neither a listed card nor in any api deck, and worded differently:
"a card", "an opponent's graveyard"): "If a card would be put into an
opponent's graveyard from anywhere, exile it instead."

Every CR number here was read in full with `mise run rules:find`:

- **CR 614.1a** - effects that use the word "instead" are replacement effects.
- **CR 700.4** - "dies" means "is put into a graveyard from the battlefield".
- **CR 603.2g** - an event that's replaced won't trigger anything, so a
  creature exiled instead of dying never "dies".
- **CR 701.17a** - to mill is to put cards from the top of the library into
  the graveyard; **CR 702.52a** - dredge mills in place of a draw.
- **CR 103.6** - opening-hand actions, Leyline's other line.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import dredge
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(alice: list[str], bob: list[str], *, hand=None, bob_hand=None, bob_library=None):
    scenario = (
        Scenario()
        .player("alice", battlefield=alice, hand=hand or [], library=["Island"] * 5)
        .player(
            "bob",
            battlefield=bob,
            hand=bob_hand or [],
            library=bob_library if bob_library is not None else ["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- Rest in Peace ------------------------------------------------------------


def test_rip_exiles_a_dying_creature_of_either_player():
    scenario = _board(["Rest in Peace", "Grizzly Bears"], ["Grizzly Bears"])
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")

    scenario.game.destroy(mine)
    scenario.game.destroy(theirs)

    assert mine.zone is Zone.EXILE
    assert theirs.zone is Zone.EXILE


def test_rip_exiles_a_resolving_spell():
    """ "From anywhere": an instant resolving off the stack is exiled."""
    scenario = _board(["Rest in Peace", "Mountain"], ["Grizzly Bears"], hand=["Lightning Bolt"])
    bears = scenario.creature("Grizzly Bears", "bob")

    bolt = scenario.cast_and_resolve("Lightning Bolt", auto=True, targets=[bears])
    scenario.state_based_actions()

    assert bolt.zone is Zone.EXILE
    assert bears.zone is Zone.EXILE


def test_rip_exiles_discarded_and_milled_cards():
    scenario = _board(
        ["Rest in Peace", "Island"],
        [],
        hand=["Thought Scour"],
        bob_hand=["Bloodghast"],
        bob_library=["Forest", "Swamp", "Island"],
    )
    bloodghast = scenario.find("Bloodghast", Zone.HAND, "bob")
    scenario.game.discard_cards("bob", [bloodghast])

    scenario.cast_and_resolve("Thought Scour", auto=True, targets=["bob"])

    assert bloodghast.zone is Zone.EXILE
    assert scenario.player("bob").graveyard == []
    assert {state.name for state in scenario.game.exile} >= {"Forest", "Swamp"}


def test_rip_means_nothing_dies_so_no_dies_trigger():
    """CR 603.2g: Hangarback Walker is exiled instead of dying - no Thopters."""
    scenario = _board(["Rest in Peace", "Hangarback Walker"], [])
    walker = scenario.creature("Hangarback Walker", "alice")
    scenario.game.add_counters(walker, Counter.PLUS_ONE, 2)

    scenario.game.destroy(walker)

    assert walker.zone is Zone.EXILE
    assert scenario.pending_triggers == []


# -- Sanctifier en-Vec: the colour-filtered variant -----------------------------


def test_sanctifier_exiles_a_red_spell_resolving():
    scenario = _board(["Sanctifier en-Vec", "Mountain"], ["Grizzly Bears"], hand=["Lightning Bolt"])
    bears = scenario.creature("Grizzly Bears", "bob")

    bolt = scenario.cast_and_resolve("Lightning Bolt", auto=True, targets=[bears])
    scenario.state_based_actions()

    assert bolt.zone is Zone.EXILE
    # A green creature is not black or red: it goes to the graveyard.
    assert bears.zone is Zone.GRAVEYARD


def test_sanctifier_exiles_a_black_permanent_and_a_black_card():
    scenario = _board(["Sanctifier en-Vec"], ["Dark Confidant"], bob_hand=["Bloodghast"])
    confidant = scenario.creature("Dark Confidant", "bob")
    bloodghast = scenario.find("Bloodghast", Zone.HAND, "bob")

    scenario.game.destroy(confidant)
    scenario.game.discard_cards("bob", [bloodghast])

    assert confidant.zone is Zone.EXILE
    assert bloodghast.zone is Zone.EXILE


def test_sanctifier_lets_a_white_creature_die_normally():
    scenario = _board(["Sanctifier en-Vec", "Sanctifier en-Vec"], [])
    first, _second = scenario.creatures("Sanctifier en-Vec", "Sanctifier en-Vec")

    scenario.game.destroy(first)

    assert first.zone is Zone.GRAVEYARD


# -- Leyline of the Void (the proof printing) -----------------------------------


def test_leyline_exiles_an_opponents_card_from_anywhere():
    scenario = _board(["Leyline of the Void"], ["Grizzly Bears"], bob_hand=["Bloodghast"])
    bears = scenario.creature("Grizzly Bears", "bob")
    bloodghast = scenario.find("Bloodghast", Zone.HAND, "bob")

    scenario.game.destroy(bears)
    scenario.game.discard_cards("bob", [bloodghast])

    assert bears.zone is Zone.EXILE
    assert bloodghast.zone is Zone.EXILE


def test_leyline_exiles_cards_an_opponent_mills_with_dredge():
    """CR 702.52a's dredge mills in place of a draw (CR 701.17a); the milled
    cards would be put into bob's graveyard, an opponent's graveyard to
    alice's Leyline, so they are exiled - and Dakmor Salvage still returns."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Leyline of the Void"])
        .player("bob", library=["Forest", "Swamp", "Island"], graveyard=["Dakmor Salvage"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    salvage = scenario.find("Dakmor Salvage", Zone.GRAVEYARD, "bob")

    milled = dredge(scenario.game, salvage, "bob")

    assert [state.zone for state in milled] == [Zone.EXILE, Zone.EXILE]
    assert salvage.zone is Zone.HAND
    assert scenario.player("bob").graveyard == []


def test_leyline_leaves_its_controllers_own_cards_alone():
    """ "An opponent's graveyard": alice's own dying creature is not caught."""
    scenario = _board(["Leyline of the Void", "Grizzly Bears"], [])
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.destroy(bears)

    assert bears.zone is Zone.GRAVEYARD


# -- the audit ----------------------------------------------------------------


@pytest.mark.parametrize("name", ["Rest in Peace", "Sanctifier en-Vec"])
def test_every_clause_is_handled(name):
    outcomes = classify_clauses(card(name))
    assert outcomes
    assert {outcome.category for outcome in outcomes} == {HANDLED}, outcomes


def test_leylines_graveyard_line_is_handled():
    """Its opening-hand line is CR 103.6's start-of-game action, owned by
    `machines/opening_hand.py`, not a replacement effect - only the graveyard
    line is this reader's."""
    outcomes = classify_clauses(card("Leyline of the Void"))
    graveyard = [outcome for outcome in outcomes if "graveyard" in outcome.text]
    assert [outcome.category for outcome in graveyard] == [HANDLED]
