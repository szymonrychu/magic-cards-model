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

Player shroud (CR 702.18a also names a player) is
`test_player_hexproof_shroud.py`'s.

Every CR number here was verified with `mise run rules:find 702.18` in the
session that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation
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


# -- Deft Duelist (off-set): a second printed-shroud proof ------------------


def test_deft_duelist_refuses_an_opponents_spell_too():
    """A second printed-shroud card, with a keyword line (first strike) in
    front of its shroud line - proving the reader is not thrown by other
    text sharing the same keyword paragraph."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Deft Duelist"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    duelist = scenario.creature("Deft Duelist", "alice")

    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError, match="has shroud"):
        casting.choose_targets([duelist])


def test_deft_duelist_also_refuses_its_own_controllers_spell():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Deft Duelist", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    duelist = scenario.creature("Deft Duelist", "alice")

    casting = scenario.cast("Lightning Bolt", username="alice")
    with pytest.raises(ValueError, match="has shroud"):
        casting.choose_targets([duelist])


# -- Lightning Greaves: shroud granted by an Equipment, not by a spell ------


def _greaves_board() -> Scenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[
                "Lightning Greaves",
                "Grizzly Bears",
                "Goblin Bombardment",
                "Runeclaw Bear",
            ],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _equip_greaves(scenario: Scenario, target):
    """Equip {0}: nothing to tap, so `pay()` alone settles it."""
    greaves = scenario.find("Lightning Greaves", Zone.BATTLEFIELD, "alice")
    activation = equip_activation(scenario.game, greaves, target, "alice")
    activation.begin_paying().pay()
    activation.activate()
    activation.resolve()
    return activation


def test_lightning_greaves_grants_shroud_on_equip():
    """ "Equipped creature has haste and shroud." - a keyword grant reaching
    the computed board (CR 613.1f) exactly the way Mage's Guile's own timed
    grant does, proving the enforcement is not keyed to a spell's grant
    versus an Equipment's."""
    scenario = _greaves_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    assert not scenario.game.characteristics_of(bears).has_ability("Shroud")

    _equip_greaves(scenario, bears)

    assert scenario.game.characteristics_of(bears).has_ability("Shroud")
    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError, match="has shroud"):
        casting.choose_targets([bears])


def test_a_greaves_equipped_creature_refuses_its_controllers_own_activated_ability():
    """The same activated-ability proof as Elvish Lookout's, on a granted
    shroud this time - Goblin Bombardment's own "any target" cannot reach the
    creature Greaves is equipped to, its controller's own ability or not."""
    scenario = _greaves_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    fodder = scenario.creature("Runeclaw Bear", "alice")
    bombardment = scenario.find("Goblin Bombardment", Zone.BATTLEFIELD, "alice")
    _equip_greaves(scenario, bears)

    with pytest.raises(ValueError, match="has shroud"):
        scenario.activate(bombardment, sacrificing=[fodder], targets=[bears])


def test_re_equipping_greaves_onto_its_own_shrouded_creature_is_refused():
    """Equip is itself an activated ability targeting "target creature you
    control" (CR 702.6a) - once Greaves has granted Bears shroud, equip's own
    target check (`equip_activation`'s own `TargetingProfile.check`, the same
    one every other activated ability's target goes through) refuses
    re-equipping Greaves onto the very creature its own grant is shrouding,
    with no special case needed for "the Equipment's own target" versus any
    other ability's."""
    scenario = _greaves_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    _equip_greaves(scenario, bears)
    assert scenario.game.characteristics_of(bears).has_ability("Shroud")

    greaves = scenario.find("Lightning Greaves", Zone.BATTLEFIELD, "alice")
    with pytest.raises(ValueError, match="has shroud"):
        equip_activation(scenario.game, greaves, bears, "alice")


def test_equipping_a_second_creature_still_grants_it_shroud():
    """The newly-equipped creature gains shroud exactly the same way - the
    grant tracks whatever Greaves is currently attached to (CR 613.1f), not
    the specific creature first equipped."""
    scenario = _greaves_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    fodder = scenario.creature("Runeclaw Bear", "alice")
    _equip_greaves(scenario, bears)
    assert scenario.game.characteristics_of(bears).has_ability("Shroud")

    _equip_greaves(scenario, fodder)

    assert scenario.game.characteristics_of(fodder).has_ability("Shroud")
    assert not scenario.game.characteristics_of(bears).has_ability("Shroud")


# -- CR 608.2b: shroud granted in response makes an already-announced target
# -- illegal at resolution, not merely at a future announcement -------------


def test_shroud_granted_in_response_fizzles_the_spell_at_resolution():
    """CR 608.2b: "If the object or player that's the target of a spell or
    ability is illegal, that object or player is removed from the spell or
    ability. ... If all its targets, for every instance of the word "target,"
    are removed this way, the spell or ability doesn't resolve." Lightning
    Bolt's own target is legal the moment bob announces it (CR 601.2c) - the
    refusal every other test in this file exercises never fires - and only
    becomes illegal afterward, which is a different rule (CR 608.2b) checked
    at a different time, and `Game.spell_fizzles` is what reads it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Mage's Guile"], battlefield=["Grizzly Bears", "Island", "Island"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.pass_priority("alice")

    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=[bears])
    scenario.pass_priority("bob")

    islands = scenario.untapped_sources("Island", "Island", username="alice")
    scenario.cast_and_resolve("Mage's Guile", *islands, username="alice", targets=[bears])

    assert scenario.game.characteristics_of(bears).has_ability("Shroud")
    assert scenario.game.spell_fizzles(bolt)

    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert bears.damage == 0
