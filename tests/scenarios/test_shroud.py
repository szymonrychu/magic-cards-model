"""Shroud: nobody's spells or abilities can target this permanent (CR 702.18).

CR 702.18a: "Shroud is a static ability. 'Shroud' means 'This permanent or
player can't be the target of spells or abilities.'" CR 702.18b: "Multiple
instances of shroud on the same permanent or player are redundant."

Shroud is not hexproof (`test_hexproof.py`, CR 702.11b's "your opponents"):
there is no controller exception here at all, printed or granted. The
refusal is checked in the one place both a spell's announced targets
(`Casting._check_targets`, CR 601.2c) and an activated or triggered
ability's announced targets (`Game.activate_ability`,
`Game.put_triggers_on_stack`) already share -
`TargetingProfile.check`/`Game.shroud_refusal` - the same shared entry point
`_check_protection`/`Game.protection_refusal` already use for CR 702.16b, so
shroud reaches an ability's targets exactly the way protection already does
without a second copy of the check anywhere.

Two shapes, each a real printing:

- **Elvish Lookout** (off-set), printed shroud, CR 702.18a's plain sentence
  with nothing else on the card - proves the reader is not fitted to any one
  card's other text.
- **Mage's Guile** (off-set), "Target creature gains shroud until end of
  turn." - a granted shroud, read the same way any other keyword grant
  reaches the computed board (CR 613.1f), and enforced by the same
  `shroud_refusal` check as the printed line, proving the enforcement is not
  keyed to "printed" vs "granted" at all.

Player shroud (CR 702.18a also names a player) is not modelled, the same
documented gap `test_hexproof.py`/`docs/engine-coverage.md` already leaves
for CR 702.11c's hexproof on a player - `Player` has no ability text to read
it off.

Every CR number here was verified with `mise run rules:find 702.18` in the
session that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_an_opponent_cannot_target_a_shrouded_creature():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Elvish Lookout"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lookout = scenario.creature("Elvish Lookout", "alice")

    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError, match="has shroud"):
        casting.choose_targets([lookout])


def test_its_own_controller_cannot_target_it_either():
    """The corner case hexproof does not have: shroud refuses the
    controller's own spell too (CR 702.18a says "spells or abilities", full
    stop, unlike CR 702.11b's "your opponents")."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Elvish Lookout", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lookout = scenario.creature("Elvish Lookout", "alice")

    casting = scenario.cast("Lightning Bolt", username="alice")
    with pytest.raises(ValueError, match="has shroud"):
        casting.choose_targets([lookout])


def test_a_refused_target_leaves_the_spell_in_hand():
    """CR 601.2c is an announcement step: a refusal is not a cast."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Elvish Lookout"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lookout = scenario.creature("Elvish Lookout", "alice")

    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError):
        casting.choose_targets([lookout])

    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    assert bolt.zone is Zone.HAND
    assert scenario.game.stack_is_empty


def test_a_non_shrouded_creature_is_unaffected():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Wall of Omens"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    wall = scenario.creature("Wall of Omens", "alice")

    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[wall],
    )
    assert wall.damage == 3


def test_shroud_in_the_graveyard_protects_nothing():
    """CR 702.18a speaks of a *permanent*; a permanent is on the battlefield."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Elvish Lookout"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lookout = scenario.creature("Elvish Lookout", "alice")
    scenario.game.put_into_graveyard(lookout)

    casting = scenario.cast("Lightning Bolt", username="bob")
    assert casting.game.shroud_refusal(lookout) is None


# -- A granted shroud, not a printed one ------------------------------------


def test_a_granted_shroud_refuses_a_spell_exactly_like_a_printed_one():
    """Mage's Guile: "Target creature gains shroud until end of turn." - the
    grant reaches layer 6 (CR 613.1f) and `shroud_refusal` reads the computed
    board (`has_keyword`), not the printed card, so this refuses the very
    next spell that tries to target the same creature."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Mage's Guile"],
            battlefield=["Grizzly Bears", "Island", "Island"],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    assert not scenario.game.characteristics_of(bears).has_ability("Shroud")

    scenario.cast_and_resolve(
        "Mage's Guile", *scenario.untapped_sources("Island", "Island"), targets=[bears]
    )

    assert scenario.game.characteristics_of(bears).has_ability("Shroud")

    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError, match="has shroud"):
        casting.choose_targets([bears])


def test_a_granted_shroud_also_refuses_its_own_controllers_spell():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Mage's Guile", "Lightning Bolt"],
            battlefield=["Grizzly Bears", "Island", "Island", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve(
        "Mage's Guile", *scenario.untapped_sources("Island", "Island"), targets=[bears]
    )
    assert scenario.game.characteristics_of(bears).has_ability("Shroud")

    casting = scenario.cast("Lightning Bolt", username="alice")
    with pytest.raises(ValueError, match="has shroud"):
        casting.choose_targets([bears])


# -- Shroud also reaches an activated ability's target, not only a spell's --


def test_a_shrouded_creature_also_refuses_an_activated_abilitys_target():
    """Goblin Bombardment: "Sacrifice a creature: This enchantment deals 1
    damage to any target." - proof that `TargetingProfile.check` (which
    `Game.begin_activating` calls exactly as `Casting.choose_targets` does)
    enforces shroud for an ability the same way it does for a spell, with no
    second copy of the check."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Goblin Bombardment", "Runeclaw Bear", "Elvish Lookout"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bombardment = scenario.find("Goblin Bombardment", Zone.BATTLEFIELD, "alice")
    fodder = scenario.creature("Runeclaw Bear", "alice")
    lookout = scenario.creature("Elvish Lookout", "alice")

    with pytest.raises(ValueError, match="has shroud"):
        scenario.activate(bombardment, sacrificing=[fodder], targets=[lookout])
