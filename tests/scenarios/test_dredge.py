"""Dredge: replacing a draw with a mill and a return (CR 702.52).

CR 702.52a: "Dredge is a static ability that functions only while the card with
dredge is in a player's graveyard. 'Dredge N' means "As long as you have at
least N cards in your library, if you would draw a card, you may mill N cards
instead. If you do, return this card from your graveyard to your hand.""

CR 702.52b: "A player with fewer cards in their library than the number required
by a dredge ability can't mill any of them this way." Note *fewer*, so exactly N
is enough - that boundary is a test here.

It is a replacement effect on a draw (CR 614.11a), and the draw event in this
engine carries only a number: there is nowhere to put an effect that replaces a
draw with something that is not a draw. So `machines/keywords.dredge` is called
*instead of* drawing, the way a scenario calls the combat turn-based actions.
See `docs/engine-coverage.md`.

CR 701.17a is the mill: "that player puts that many cards from the top of their
library into their graveyard."
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import dredge, dredge_count, why_cannot_dredge
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def board(*library: str, graveyard: tuple[str, ...] = ("Dakmor Salvage",)) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=list(library), graveyard=list(graveyard))
        .player("bob")
    )


def test_the_count_is_read_off_the_printed_line():
    """CR 702.52a's N: Dakmor Salvage says Dredge 2."""
    assert dredge_count(card("Dakmor Salvage")) == 2
    assert dredge_count(card("Grizzly Bears")) is None


def test_dredging_mills_two_and_returns_the_card_to_hand():
    """CR 702.52a, the whole ability."""
    scenario = board("Lightning Bolt", "Forest", "Island").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    salvage = scenario.find("Dakmor Salvage", Zone.GRAVEYARD, "alice")

    milled = dredge(scenario.game, salvage, "alice")

    assert [state.name for state in milled] == ["Lightning Bolt", "Forest"]
    assert all(state.zone is Zone.GRAVEYARD for state in milled)
    assert salvage.zone is Zone.HAND
    assert [state.name for state in scenario.player("alice").library] == ["Island"]


def test_exactly_n_cards_in_the_library_is_enough():
    """CR 702.52b says *fewer*, so two cards is a legal dredge for Dredge 2."""
    scenario = board("Lightning Bolt", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    salvage = scenario.find("Dakmor Salvage", Zone.GRAVEYARD, "alice")

    assert why_cannot_dredge(scenario.game, salvage, "alice") is None
    dredge(scenario.game, salvage, "alice")
    assert scenario.player("alice").library == []


def test_one_card_short_cannot_dredge_at_all():
    """CR 702.52b: "can't mill any of them this way" - not "mills what is there"."""
    scenario = board("Lightning Bolt").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    salvage = scenario.find("Dakmor Salvage", Zone.GRAVEYARD, "alice")

    assert "dredge 2 needs 2" in (why_cannot_dredge(scenario.game, salvage, "alice") or "")
    with pytest.raises(ValueError, match="dredge 2 needs 2"):
        dredge(scenario.game, salvage, "alice")

    assert salvage.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").library) == 1


def test_dredge_only_functions_from_a_graveyard():
    """CR 702.52a: "functions only while the card with dredge is in a player's graveyard"."""
    scenario = board("Lightning Bolt", "Forest", graveyard=()).build()
    scenario.player("alice").add(scenario.game.player("alice").library.pop(), Zone.HAND)
    hand_card = scenario.player("alice").hand[0]

    assert why_cannot_dredge(scenario.game, hand_card, "alice") is not None


def test_a_card_on_the_battlefield_cannot_dredge():
    """Dakmor Salvage is a land: on the battlefield it makes mana, not dredges."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Dakmor Salvage"], library=["Forest", "Island"])
        .player("bob")
        .build()
    )
    salvage = scenario.find("Dakmor Salvage", Zone.BATTLEFIELD, "alice")

    assert "functions in a graveyard" in (why_cannot_dredge(scenario.game, salvage, "alice") or "")


def test_dredging_does_not_draw_a_card():
    """The replacement is a mill, not a draw - the hand gains the dredger only."""
    scenario = board("Lightning Bolt", "Forest", "Island").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    salvage = scenario.find("Dakmor Salvage", Zone.GRAVEYARD, "alice")

    dredge(scenario.game, salvage, "alice")

    assert [state.name for state in scenario.player("alice").hand] == ["Dakmor Salvage"]


def test_dredging_twice_needs_the_library_to_hold_out():
    """The card is back in hand, so a second dredge needs it in the graveyard again."""
    scenario = board("Lightning Bolt", "Forest", "Island", "Swamp").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    salvage = scenario.find("Dakmor Salvage", Zone.GRAVEYARD, "alice")

    dredge(scenario.game, salvage, "alice")
    assert why_cannot_dredge(scenario.game, salvage, "alice") is not None

    scenario.player("alice").move(salvage, Zone.GRAVEYARD)
    assert why_cannot_dredge(scenario.game, salvage, "alice") is None
    dredge(scenario.game, salvage, "alice")
    assert scenario.player("alice").library == []
