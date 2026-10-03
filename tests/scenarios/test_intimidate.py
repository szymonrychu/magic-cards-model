"""Scenario: intimidate (CR 702.13), printed and granted by a gated static.

Read with `mise run rules:find 702.13` this session:

- **CR 702.13a** - intimidate is an evasion ability.
- **CR 702.13b** - "A creature with intimidate can't be blocked except by
  artifact creatures and/or creatures that share a color with it."
- **CR 702.13c** - multiple instances are redundant.

Bladetusk Boar (red, printed intimidate) and Guul Draz Vampire (black; "As long
as an opponent has 10 or less life, this creature gets +2/+1 and has
intimidate.") are the printings. The refusal is the declare-blockers check
(CR 509.1b), asked through `Game.why_cannot_block`, off the computed board.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import executes
from magic_cards_model.support import ignored_keywords
from tests.cards import card
from tests.scenarios.harness import Scenario

BOAR = "Bladetusk Boar"
VAMPIRE = "Guul Draz Vampire"


def _attacking(attacker: str, blocker: str, *, bob_life: int = 20):
    scenario = (
        Scenario()
        .player("alice", battlefield=[attacker], library=["Island"] * 3)
        .player("bob", battlefield=[blocker], library=["Island"] * 3, life=bob_life)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    mine = scenario.creature(attacker, "alice")
    scenario.attack_with(mine)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    return scenario, mine, scenario.creature(blocker, "bob")


def test_intimidate_is_executed_and_not_reported_as_ignored():
    assert executes("intimidate")
    assert "Intimidate" not in ignored_keywords(card(BOAR))


def test_a_creature_sharing_no_color_cannot_block_it():
    scenario, boar, bears = _attacking(BOAR, "Grizzly Bears")
    refusal = scenario.game.why_cannot_block(bears, boar)
    assert refusal is not None and "702.13b" in refusal


def test_a_creature_sharing_a_color_can_block_it():
    scenario, boar, goblin = _attacking(BOAR, "Goblin Guide")
    assert scenario.game.why_cannot_block(goblin, boar) is None
    scenario.block(boar, goblin)


def test_an_artifact_creature_can_block_it():
    scenario, boar, golem = _attacking(BOAR, "Walking Ballista")
    assert scenario.game.why_cannot_block(golem, boar) is None


def test_granted_intimidate_applies_only_while_the_opponent_is_at_ten_or_less():
    scenario, vampire, bears = _attacking(VAMPIRE, "Grizzly Bears", bob_life=10)
    assert scenario.game.why_cannot_block(bears, vampire) is not None
    scenario.game.player("bob").life = 11
    assert scenario.game.why_cannot_block(bears, vampire) is None
    scenario.game.player("bob").life = 10
    assert scenario.game.why_cannot_block(bears, vampire) is not None


def test_granted_intimidate_still_lets_a_black_creature_block():
    scenario, vampire, zombie = _attacking(VAMPIRE, "Dark Confidant", bob_life=10)
    assert scenario.game.why_cannot_block(zombie, vampire) is None
