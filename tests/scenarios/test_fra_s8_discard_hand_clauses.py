"""FRA stream S8: "Discard your hand[, then draw ...]." (CR 701.9a's
whole-hand shape, as opposed to a printed count).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 701.9a** - "To discard a card, move it from its owner's hand to that
  player's graveyard."
- **CR 608.2d** - an instruction with nothing left to choose among (every
  card in hand goes) asks no question.
- **CR 606.3/307.5** - a loyalty ability's own timing.

Ajani Unrelenting's `−2` ("Discard your hand, then draw a card for each
creature you control.") is the reported card. Anje's Ravager ("Whenever this
creature attacks, discard your hand, then draw three cards.") is the off-set
proof: a real, non-FRA, non-pool printing of the identical "discard your
hand, then draw ..." shape, with a fixed draw count instead of Ajani's own
"for each", and fired by an attack trigger instead of a loyalty ability.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_ajani_unrelentings_minus_two_discards_the_hand_then_draws_per_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears", "Lightning Bolt", "Mountain"],
            battlefield=["Ajani Unrelenting", "Elvish Mystic", "Goblin Guide"],
            library=["Forest"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ajani = scenario.find("Ajani Unrelenting", Zone.BATTLEFIELD, "alice")
    alice = scenario.player("alice")

    scenario.activate(ajani, index=1)
    scenario.pass_until_resolved()

    assert len(alice.hand) == 2, "one card drawn per creature alice controls (2)"
    assert alice.graveyard and {state.name for state in alice.graveyard} == {
        "Grizzly Bears",
        "Lightning Bolt",
        "Mountain",
    }


def test_anjes_ravager_discards_the_hand_then_draws_a_fixed_count():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears", "Lightning Bolt"],
            battlefield=["Anje's Ravager"],
            library=["Forest"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    alice = scenario.player("alice")
    ravager = scenario.creature("Anje's Ravager", "alice")

    scenario.attack_with(ravager)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert len(alice.hand) == 3
    assert alice.graveyard and {state.name for state in alice.graveyard} == {
        "Grizzly Bears",
        "Lightning Bolt",
    }
