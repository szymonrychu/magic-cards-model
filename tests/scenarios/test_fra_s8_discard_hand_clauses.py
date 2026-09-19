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

Ajani Unrelenting's own first ability ("Whenever you activate a loyalty
ability, create a 2/2 colorless Wizard Soldier creature token named Cadet.",
`tests/scenarios/test_loyalty_ability_activated_trigger.py`'s own mechanic)
fires off the very activation of the `−2` and is put on the stack above it
(CR 603.3, LIFO), so it resolves *first* - the Cadet is already on the
battlefield, one more creature Alice controls, by the time "draw a card for
each creature you control" counts. The `−2` test below accounts for it
rather than for the two pre-existing creatures alone.
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
    scenario.pass_until_resolved()

    assert len(alice.hand) == 3, (
        "one card drawn per creature alice controls: Elvish Mystic, Goblin Guide, and the "
        "Cadet token Ajani's own first ability creates before the -2 resolves (CR 603.3)"
    )
    assert alice.graveyard and {state.name for state in alice.graveyard} == {
        "Grizzly Bears",
        "Lightning Bolt",
        "Mountain",
    }
    assert any(
        state.token and state.name == "Cadet" and state.controller == "alice"
        for state in scenario.game.battlefield
    )


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
