"""Orim's Chant: "Kicker {W} (You may pay an additional {W} as you cast this
spell.) Target player can't cast spells this turn. If this spell was kicked,
creatures can't attack this turn."

Two restrictions, read as one CR 608.2c instruction chain:

- **"Target player can't cast spells this turn"** is a targeted cousin of
  Ranger-Captain of Eos's own "your opponents can't cast noncreature spells
  this turn" (`test_activated_ability_effects.py`'s own coverage,
  `machines.casting_restrictions.CastingRuleKind.NONCREATURE_RESTRICTION`) -
  a new `TARGETED_CANT_CAST` row on the same `CastingRuleEffect` store, keyed
  by the target itself rather than by "everyone but the controller".
- **"If this spell was kicked, creatures can't attack this turn"** is
  CR 702.33d/g's kicker-conditional clause (`Game.cast_record(spell).kicked`,
  the same reader Burst Lightning's own kicked-damage clause already uses),
  gating a blanket CR 508.1c restriction over every creature any player
  controls - `Game.creatures_cant_attack_until_turns_taken`, read by
  `machines.combat.attack_refusal`.

CR numbers looked up with `knowledge_search(q="...", type="rules")` in the
session that wrote this file: CR 611.1, CR 702.33a, CR 702.33d, CR 508.1c.
"""

import pytest

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Orim's Chant"],
            battlefield=["Plains", "Plains", "Grizzly Bears"],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain", "Grizzly Bears"])
    )


def test_the_targeted_player_cannot_cast_a_spell_this_turn():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (plains,) = scenario.untapped_sources("Plains")

    scenario.cast_and_resolve("Orim's Chant", plains, targets=["bob"])

    with pytest.raises(ValueError, match="can't cast spells this turn"):
        scenario.cast("Lightning Bolt", username="bob", targets=["alice"])


def test_the_casters_own_spells_are_untouched():
    """The restriction follows the target, not "your opponents" - alice, who
    cast Orim's Chant, may still cast her own spells this turn."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Orim's Chant", "Lightning Bolt"],
            battlefield=["Plains", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (plains,) = scenario.untapped_sources("Plains")

    scenario.cast_and_resolve("Orim's Chant", plains, targets=["bob"])

    casting = scenario.cast("Lightning Bolt", targets=["bob"])
    assert casting.step is not None


def test_unkicked_creatures_can_still_attack():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (plains,) = scenario.untapped_sources("Plains")
    scenario.cast_and_resolve("Orim's Chant", plains, targets=["bob"])

    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers
    bears = scenario.creature("Grizzly Bears", "alice")
    assert scenario.can_attack(bears) is True


def test_a_kicked_chant_stops_every_creature_from_attacking():
    """The attack restriction is blanket - it catches bob's own Grizzly
    Bears too, not only alice's."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plains_sources = scenario.untapped_sources("Plains", "Plains")
    casting = scenario.cast("Orim's Chant")
    casting.pay_kicker()
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *plains_sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers
    alice_bears = scenario.creature("Grizzly Bears", "alice")
    bob_bears = scenario.creature("Grizzly Bears", "bob")

    assert scenario.can_attack(alice_bears) is False
    assert scenario.can_attack(bob_bears, defending="alice") is False
    assert "can't attack this turn" in (scenario.game.why_cannot_attack(alice_bears, "bob") or "")


def test_the_kicked_restriction_does_not_carry_into_the_next_turn():
    scenario = (
        Scenario()
        .automatic_turn_based_actions()
        .player(
            "alice",
            hand=["Orim's Chant"],
            library=["Plains"] * 10,
            battlefield=["Plains", "Plains", "Grizzly Bears"],
        )
        .player(
            "bob",
            hand=["Lightning Bolt"],
            library=["Mountain"] * 10,
            battlefield=["Mountain", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plains_sources = scenario.untapped_sources("Plains", "Plains")
    casting = scenario.cast("Orim's Chant")
    casting.pay_kicker()
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *plains_sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    scenario.advance()  # crosses into bob's turn
    while scenario.turn.active_player != "alice":
        scenario.advance()
    scenario.advance()  # alice's precombat main
    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers

    alice_bears = scenario.creature("Grizzly Bears", "alice")
    assert scenario.can_attack(alice_bears) is True
