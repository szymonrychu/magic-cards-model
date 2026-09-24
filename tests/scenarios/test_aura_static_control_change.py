""" "You control enchanted creature." - an Aura's own static control change.

CR 613.1b: "Layer 2: Control-changing effects are applied." CR 611.3a: a
static ability's continuous effect "applies at all times" while its source is
on the battlefield, and stops the moment it is not - there is no duration to
run out. So the enchanted creature's controller is the Aura controller's for
exactly as long as the Aura stays on it.

Ghastly Haunting (Soul Seizer's back face, legal in Modern, in no deck list
here): "Enchant creature / You control enchanted creature." It gets onto a
creature through Soul Seizer's own transform-and-attach trigger, so every test
here plays that through rather than staging the attachment.

Every CR number here was read whole with `mise run rules:find`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _stolen(bob_extra: list[str] | None = None, alice_hand: list[str] | None = None):
    """Soul Seizer connects, transforms, and takes bob's Runeclaw Bear."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Island"] * 5,
            hand=alice_hand or [],
            battlefield=["Soul Seizer", "Forest", "Island"],
        )
        .player(
            "bob",
            library=["Island"] * 5,
            battlefield=["Runeclaw Bear", *(bob_extra or [])],
        )
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    seizer = scenario.creature("Soul Seizer", "alice")
    bear = scenario.creature("Runeclaw Bear", "bob")
    scenario.attack_with(seizer)
    scenario.advance()
    scenario.no_blocks()
    scenario.advance()
    scenario.will_choose_targets(bear)
    scenario.will_take_the_may(True)
    scenario.combat_damage()
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()
    assert seizer.name == "Ghastly Haunting"
    return scenario, seizer, bear


def test_the_enchanted_creature_changes_controller():
    scenario, _, bear = _stolen()
    assert bear.controller == "alice"
    assert bear in scenario.game.permanents_controlled_by("alice")
    assert bear not in scenario.game.permanents_controlled_by("bob")


def test_the_owner_does_not_change():
    """CR 108.3: control changes, ownership never does."""
    _, _, bear = _stolen()
    assert bear.owner == "bob"


def test_control_returns_when_the_aura_leaves():
    """CR 611.3a: no Aura on the battlefield, no effect - the Bear is bob's
    again the moment Nature's Claim destroys Ghastly Haunting."""
    scenario, haunting, bear = _stolen(alice_hand=["Nature's Claim"])
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Nature's Claim", *scenario.untapped_sources("Forest"), targets=[haunting]
    )

    assert haunting.zone is Zone.GRAVEYARD
    assert bear.controller == "bob"


def test_the_creature_leaving_ends_it_and_the_aura_goes_to_the_graveyard():
    """The stolen creature bounced: it goes to its owner's hand, and the Aura,
    attached to nothing, is put into its owner's graveyard (CR 704.5m)."""
    scenario, haunting, bear = _stolen(alice_hand=["Unsummon"])
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.cast_and_resolve("Unsummon", *scenario.untapped_sources("Island"), targets=[bear])
    scenario.state_based_actions()

    assert bear.zone is Zone.HAND
    assert bear in scenario.player("bob").hand
    assert haunting.zone is Zone.GRAVEYARD


def test_an_unattached_aura_changes_nothing():
    """Nothing attached, nothing to control: bob's other creature is untouched."""
    scenario, _, _ = _stolen(bob_extra=["Memnite"])
    assert scenario.creature("Memnite", "bob").controller == "bob"
