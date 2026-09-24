"""Scenario: "Destroy target `<permanent>`. `<This>` deals N damage to that
`<permanent>`'s controller."

Two instructions in order (CR 608.2c), the second naming the first one's
target by anaphora (CR 400.7's "that artifact"). The destroyed permanent is in
its owner's graveyard by the time the damage is dealt, so "that artifact's
controller" is the controller it had when it was last on the battlefield -
last known information (CR 608.2h, CR 113.7a). The damage happens whether or
not the destroy did (an indestructible artifact still has a controller to
hit); if the target is illegal on resolution, CR 608.2b's "if part of the
effect requires information about an illegal target, it fails to determine
any such information" means no damage either.

Cards: Smash to Smithereens; proof printings Destructive Revelry ("target
artifact or enchantment ... that permanent's controller") and Consign to the
Pit ("target creature ... that creature's controller").

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file: 608.2c, 400.7, 608.2h, 113.7a, 608.2b, 120.1.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _smash_board(bob_battlefield: list[str], *, alice_battlefield=None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Smash to Smithereens"],
            battlefield=["Mountain", "Mountain", *(alice_battlefield or [])],
        )
        .player("bob", library=["Forest"], battlefield=bob_battlefield)
    )


def _smash(scenario, target) -> None:
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve(
        "Smash to Smithereens", *mountains, username="alice", targets=[target]
    )


def test_smash_destroys_the_artifact_and_hits_its_controller():
    scenario = _smash_board(["Ornithopter"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thopter = scenario.find("Ornithopter", Zone.BATTLEFIELD, "bob")

    _smash(scenario, thopter)

    assert thopter.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 20


def test_smash_on_your_own_artifact_hits_you():
    """ "that artifact's controller" - not "target opponent"."""
    scenario = _smash_board([], alice_battlefield=["Ornithopter"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thopter = scenario.find("Ornithopter", Zone.BATTLEFIELD, "alice")

    _smash(scenario, thopter)

    assert thopter.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 17
    assert scenario.player("bob").life == 20


def test_an_indestructible_artifact_survives_but_its_controller_is_still_hit():
    scenario = _smash_board(["Darksteel Relic"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    relic = scenario.find("Darksteel Relic", Zone.BATTLEFIELD, "bob")

    _smash(scenario, relic)

    assert relic.zone is Zone.BATTLEFIELD
    assert scenario.player("bob").life == 17


def test_the_controller_is_read_as_it_last_was_not_the_owner():
    """CR 608.2h: the controller it had on the battlefield - Alice has taken
    control of Bob's Ornithopter, so Alice is hit though Bob owns it."""
    scenario = _smash_board(["Ornithopter"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thopter = scenario.find("Ornithopter", Zone.BATTLEFIELD, "bob")
    thopter.controller = "alice"  # staging a control change

    _smash(scenario, thopter)

    assert thopter.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 17
    assert scenario.player("bob").life == 20


def test_no_damage_when_the_target_is_gone_before_resolution():
    """CR 608.2b: an illegal target - the spell does not resolve at all."""
    scenario = _smash_board(["Ornithopter"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thopter = scenario.find("Ornithopter", Zone.BATTLEFIELD, "bob")
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_onto_stack(
        "Smash to Smithereens", *mountains, username="alice", targets=[thopter]
    )
    scenario.game.destroy(thopter)
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 20


def test_the_spell_is_the_source_of_the_damage():
    """CR 120.1 - Artist's Talent's +2 sees Smash, a source Alice controls."""
    scenario = _smash_board(["Ornithopter"], alice_battlefield=["Artist's Talent"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.find("Artist's Talent", Zone.BATTLEFIELD, "alice").class_level = 3
    scenario.will_take_the_may(False, times=None)
    thopter = scenario.find("Ornithopter", Zone.BATTLEFIELD, "bob")
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_onto_stack(
        "Smash to Smithereens", *mountains, username="alice", targets=[thopter]
    )
    while scenario.stack_names() or scenario.pending_triggers:
        scenario.game.put_triggers_on_stack()
        scenario.pass_until_resolved()

    assert scenario.player("bob").life == 15


# -- proof printings --------------------------------------------------------


def test_destructive_revelry_hits_an_enchantments_controller():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Destructive Revelry"],
            battlefield=["Mountain", "Forest"],
        )
        .player("bob", library=["Forest"], battlefield=["Rest in Peace"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rip = scenario.find("Rest in Peace", Zone.BATTLEFIELD, "bob")
    sources = scenario.untapped_sources("Mountain", "Forest", username="alice")

    scenario.cast_and_resolve("Destructive Revelry", *sources, username="alice", targets=[rip])

    assert rip.zone is not Zone.BATTLEFIELD
    assert scenario.player("bob").life == 18


def test_consign_to_the_pit_hits_a_creatures_controller():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Consign to the Pit"],
            battlefield=["Swamp"] * 6,
        )
        .player("bob", library=["Forest"], battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    swamps = scenario.untapped_sources(*["Swamp"] * 6, username="alice")

    scenario.cast_and_resolve("Consign to the Pit", *swamps, username="alice", targets=[angel])

    assert angel.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 18
