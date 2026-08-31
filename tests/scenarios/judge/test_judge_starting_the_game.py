"""Judge scenarios: what a permanent that was there before turn one may do.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#1002** - How Does Starting the Game Work?

The episode walks the whole pregame procedure - who plays first, presenting,
mulligans, then the opening-hand-effect step where Leylines, Chancellors and
Gemstone Caverns are used. All of that is modelled: `machines/opening_hand.py`
implements CR 103.6 and `Match.start_game` walks the rest. A scenario built
board-first skips straight past it, so the last test here asks for the
opening-hand-effect step explicitly.

What *is* testable is the episode's most-quoted consequence: a creature that
began the game on the battlefield can attack on turn one without haste, because
CR 508.1a asks whether the creature "has been controlled by the active player
continuously since their most recent turn began" - and a permanent put in before
the game started has been. The same rule is what lets a Karn-restarted board
attack immediately, and it is why a token *created during upkeep* still needs
haste.

Every CR number here was looked up with `knowledge_search(type="rules")` in the
session that wrote the file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_a_creature_that_started_on_the_battlefield_attacks_on_turn_one():
    """CR 508.1a: the chosen attackers "must be untapped, they can't also be
    battles, and each one must either have haste or have been controlled by the
    active player continuously since their most recent turn began".

    CR 302.6 and CR 702.10b say the same thing from the other side: haste is
    only needed by a creature that has *not* been there since the turn began.
    Grizzly Bears has no haste and does not need any.
    """
    scenario = Scenario().player("alice", battlefield=["Grizzly Bears"]).player("bob").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")

    assert scenario.can_attack(bears)

    scenario.attack_with(bears)

    assert scenario.attackers() == [bears]
    assert bears.tapped


def test_a_creature_that_arrived_this_turn_still_needs_haste():
    """The contrast the episode draws with Chancellor of the Forge's upkeep
    token: a creature that entered *during* the turn was not there when the turn
    began, so CR 508.1a refuses it.

    Cast rather than declared onto the battlefield, so the arrival really
    happens inside the turn.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", username="alice")
    bears = scenario.cast_and_resolve("Grizzly Bears", *sources, username="alice")
    scenario.advance()  # begin combat
    scenario.advance()  # declare attackers

    assert not scenario.can_attack(bears)
    with pytest.raises(ValueError):
        scenario.attack_with(bears)
    assert not bears.tapped


def test_the_legend_rule_waits_for_the_first_state_based_action_check():
    """The episode's two-Leyline question, reduced to the rule it turns on.

    CR 704.5j puts the extra legendary permanent into its owner's graveyard, and
    CR 704.3 checks state-based actions "whenever a player would receive
    priority" - never during the pregame procedure. So two copies coexist on a
    board that has not been checked yet, and the second one leaves at the first
    check.
    """
    scenario = Scenario().player("alice", battlefield=["Mox Opal", "Mox Opal"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.creatures("Mox Opal", "Mox Opal", username="alice")

    assert first.zone is Zone.BATTLEFIELD
    assert second.zone is Zone.BATTLEFIELD

    scenario.state_based_actions()

    assert second.zone is Zone.GRAVEYARD


def test_gemstone_caverns_can_start_the_game_on_the_battlefield():
    """CR 103.6a: "If a card allows a player to begin the game with that card on
    the battlefield, the player taking this action puts that card onto the
    battlefield."

    CR 103.6 makes the action optional - "may take any such actions" - so an
    unscripted player declines it (see `machines/decisions.py`). Scripting the
    yes is what the episode's player does out loud, and the engine then performs
    the whole of CR 103.6a: the Caverns leaves the opening hand for the
    battlefield.

    A board-first scenario has no pregame to walk, so the opening-hand-effect
    step has to be asked for explicitly; `Game.take_opening_hand_actions` has a
    branch for exactly that case.
    """
    scenario = Scenario().player("alice").player("bob", hand=["Gemstone Caverns"]).build()
    scenario.start_at(Step.UPKEEP)
    scenario.game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.OPENING_HAND_ACTION,
            value=True,
            player="bob",
            source="Gemstone Caverns",
        )
    )

    scenario.game.take_opening_hand_actions()

    assert scenario.find("Gemstone Caverns", Zone.BATTLEFIELD, "bob")
