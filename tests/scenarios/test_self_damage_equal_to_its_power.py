"""Scenario: "this creature deals damage equal to its power to `<target>`" -
the source deals damage equal to its own power (CR 208.1).

CR 608.2h: an effect that needs information from a specific object,
"including the source of the ability itself", uses its current information
while it is where it was expected to be, and its last known information once
it is not; CR 113.7a: "This creature deals 1 damage to any target" is the
source doing something, and "the source can still perform the action even
though it no longer exists". So the amount is the power as the ability
resolves - a pump in response counts - and a source gone from the
battlefield deals damage equal to its power as it last existed there.

The reader was exposed by Cyclops Superconductor's reflexive consequence
(`test_reflexive_pay_energy_when_you_do.py`); this proves it on a different
printing and ability kind, not in the api deck pool:

- **Spikeshot Elder** (Modern): "{1}{R}{R}: This creature deals damage equal
  to its power to any target." An activated ability; oracle text pulled with
  `scripts/add_card.py` and verified against the pool.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

ELDER = "Spikeshot Elder"


def _board(*alice_hand: str) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=[ELDER, "Mountain", "Mountain", "Mountain", "Forest"],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Hill Giant", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _activate_at(scenario: Scenario, target) -> None:
    elder = scenario.creature(ELDER, "alice")
    mountains = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="alice")
    scenario.activate(elder, *mountains, targets=[target])


def test_spikeshot_elder_deals_its_power_to_a_player():
    scenario = _board()
    _activate_at(scenario, "bob")
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 19


def test_spikeshot_elder_deals_its_power_to_a_creature():
    scenario = _board()
    giant = scenario.creature("Hill Giant", "bob")
    _activate_at(scenario, giant)
    scenario.pass_until_resolved()

    assert giant.damage == 1


def test_a_pump_in_response_counts_because_power_is_read_on_resolution():
    """CR 608.2h: the power is determined as the effect is applied."""
    scenario = _board("Giant Growth")
    _activate_at(scenario, "bob")
    elder = scenario.creature(ELDER, "alice")
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_and_resolve("Giant Growth", forest, username="alice", targets=[elder])
    assert scenario.game.power_of(elder) == 4

    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 16


def test_the_source_killed_in_response_still_deals_its_last_known_power():
    """CR 113.7a / CR 608.2h: the Elder is gone, so its last known
    information - a 4/5 with Giant Growth - deals the damage."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Giant Growth"],
            battlefield=[ELDER, "Mountain", "Mountain", "Mountain", "Forest"],
        )
        .player(
            "bob",
            hand=["Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_at(scenario, "bob")
    elder = scenario.creature(ELDER, "alice")
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_and_resolve("Giant Growth", forest, username="alice", targets=[elder])
    assert scenario.game.power_of(elder) == 4
    for bobs_mountain in scenario.untapped_sources("Mountain", "Mountain", username="bob"):
        scenario.pass_priority("alice")
        scenario.cast_and_resolve("Lightning Bolt", bobs_mountain, username="bob", targets=[elder])
        scenario.state_based_actions()
    assert elder.zone is Zone.GRAVEYARD

    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 16


def test_the_target_gone_on_resolution_means_no_damage():
    """CR 608.2b: its only target is illegal, so the ability does not
    resolve."""
    scenario = _board()
    giant = scenario.creature("Hill Giant", "bob")
    _activate_at(scenario, giant)
    scenario.pass_priority("alice")
    (bobs_mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", bobs_mountain, username="bob", targets=[giant])
    scenario.state_based_actions()
    assert giant.zone is Zone.GRAVEYARD

    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 20
