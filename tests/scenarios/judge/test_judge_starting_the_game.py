"""Judge scenarios: what a permanent that was there before turn one may do.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#1002** - How Does Starting the Game Work?

The episode walks the whole pregame procedure - who plays first, presenting,
mulligans, then the opening-hand-effect step where Leylines, Chancellors and
Gemstone Caverns are used. Almost none of that is modelled here: this engine
starts from a board a scenario declares, with no pregame phase, no mulligans and
no opening-hand effects.

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


@pytest.mark.xfail(
    strict=True,
    reason="There is no pregame procedure in this engine: `Scenario` declares a "
    "board directly, with no starting-player step, no mulligans and no "
    "opening-hand-effect step, so Gemstone Caverns' 'you may begin the game with "
    "this on the battlefield' has nothing to hook into.",
)
def test_gemstone_caverns_can_start_the_game_on_the_battlefield():
    """CR 103.1-103.3's pregame procedure, and the last of its steps.

    The episode's ruling is that a player on the draw whose only card is
    Gemstone Caverns may still put it in - the instruction to exile a card is
    not optional, but nothing says the Caverns stays in hand when it cannot be
    performed. Nothing here models any of that; the Caverns simply starts in
    hand and stays there.
    """
    scenario = Scenario().player("alice").player("bob", hand=["Gemstone Caverns"]).build()
    scenario.start_at(Step.UPKEEP)

    assert scenario.find("Gemstone Caverns", Zone.BATTLEFIELD, "bob")
