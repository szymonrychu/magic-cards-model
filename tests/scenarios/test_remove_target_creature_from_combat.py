"""Remove target attacking and/or blocking creature from combat.

CR 506.4: a creature "that's removed from combat stops being an attacking,
blocking, blocked, and/or unblocked creature", and "an effect specifically
removes it from combat" is one way that happens. CR 509.1h: an attacker stays
blocked "even if all the creatures blocking it are removed from combat", so
removing a blocker leaves its attacker blocked (and dealing no damage to the
player), while removing an attacker removes it from the fight altogether.

Cards: Hollowhenge Spirit (enters trigger, "attacking or blocking creature"),
Labyrinth of Skophos (same phrase on an activated ability), Reconnaissance
("attacking creature you control ... from combat and untap it").
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.targeting import profile_for_text
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import TargetRef

from .harness import Scenario

SPIRIT_LANDS = ["Forest", "Forest", "Forest", "Plains", "Plains"]


def board(bob_extra=(), alice_extra=()) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", *alice_extra])
        .player(
            "bob",
            hand=["Hollowhenge Spirit"],
            battlefield=[*SPIRIT_LANDS, *bob_extra],
        )
        .build()
    )


def flash_in_spirit(scenario, target):
    """Bob flashes in the Spirit and aims its trigger at `target`."""
    scenario.pass_priority("alice")
    lands = scenario.untapped_sources(*SPIRIT_LANDS, username="bob")
    scenario.will_choose_targets(target, source="Hollowhenge Spirit")
    scenario.cast_onto_stack("Hollowhenge Spirit", *lands, username="bob")
    scenario.pass_until_resolved()  # the creature spell
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()  # the enters trigger


def test_a_removed_attacker_is_no_longer_attacking_and_deals_no_damage():
    scenario = board()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    flash_in_spirit(scenario, bears)
    assert scenario.attackers() == []
    scenario.no_blocks()
    scenario.combat_damage()
    assert scenario.player("bob").life == 20


def test_a_removed_attacker_that_was_blocked_deals_and_receives_no_damage():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", hand=["Hollowhenge Spirit"], battlefield=[*SPIRIT_LANDS, "Grizzly Bears"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    blocker = scenario.creature("Grizzly Bears", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.block(bears, blocker)
    flash_in_spirit(scenario, bears)
    assert scenario.attackers() == []
    assert scenario.blockers() == []
    scenario.combat_damage()
    assert blocker.damage == 0
    assert bears.damage == 0
    assert scenario.player("bob").life == 20


def test_a_removed_blocker_leaves_its_attacker_blocked_and_deals_no_damage():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", hand=["Hollowhenge Spirit"], battlefield=[*SPIRIT_LANDS, "Grizzly Bears"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    blocker = scenario.creature("Grizzly Bears", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.block(bears, blocker)
    flash_in_spirit(scenario, blocker)
    assert scenario.blockers() == []
    assert scenario.attackers() == [bears]
    attack = scenario.game.combat.attack_by(bears.id)
    assert attack.blocked is True
    scenario.combat_damage()
    assert scenario.player("bob").life == 20  # CR 509.1h: still blocked
    assert bears.damage == 0
    assert blocker.damage == 0


def test_a_removed_blocker_takes_no_damage_and_deals_none():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", hand=["Hollowhenge Spirit"], battlefield=[*SPIRIT_LANDS, "Grizzly Bears"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    blocker = scenario.creature("Grizzly Bears", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.block(bears, blocker)
    flash_in_spirit(scenario, blocker)
    scenario.combat_damage()
    assert blocker.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.BATTLEFIELD


def test_a_creature_that_is_not_in_combat_is_not_a_legal_target():
    scenario = board()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    (requirement,) = profile_for_text("target attacking or blocking creature").requirements
    assert requirement.rejects(bears, "bob", scenario.game) is not None
    scenario.attack_with(bears)
    assert requirement.rejects(bears, "bob", scenario.game) is None


def test_the_target_leaving_combat_before_resolution_is_a_harmless_fizzle():
    scenario = board()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.pass_priority("alice")
    lands = scenario.untapped_sources(*SPIRIT_LANDS, username="bob")
    scenario.will_choose_targets(bears, source="Hollowhenge Spirit")
    scenario.cast_onto_stack("Hollowhenge Spirit", *lands, username="bob")
    scenario.pass_until_resolved()
    scenario.game.put_triggers_on_stack()
    scenario.game.combat.remove(bears.id)  # removed in response
    scenario.pass_until_resolved()
    assert scenario.attackers() == []
    assert scenario.find("Hollowhenge Spirit", Zone.BATTLEFIELD, "bob") is not None


def test_removing_after_blockers_still_works_in_the_declare_blockers_step():
    scenario = board()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.no_blocks()
    flash_in_spirit(scenario, bears)
    assert scenario.attackers() == []
    scenario.combat_damage()
    assert scenario.player("bob").life == 20


def test_labyrinth_of_skophos_removes_a_blocker_with_the_same_phrase():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player(
            "bob",
            battlefield=[
                "Labyrinth of Skophos",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Grizzly Bears",
            ],
        )
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    blocker = scenario.creature("Grizzly Bears", "bob")
    labyrinth = scenario.find("Labyrinth of Skophos", Zone.BATTLEFIELD, "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.block(bears, blocker)
    scenario.pass_priority("alice")
    mountains = scenario.untapped_sources(
        "Mountain", "Mountain", "Mountain", "Mountain", username="bob"
    )
    scenario.activate(
        labyrinth, *mountains, index=1, username="bob", targets=[TargetRef.coerce(blocker)]
    )
    scenario.resolve_top()
    assert scenario.blockers() == []
    scenario.combat_damage()
    assert scenario.player("bob").life == 20


def test_reconnaissance_removes_your_own_attacker_and_untaps_it():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Reconnaissance"])
        .player("bob")
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    recon = scenario.find("Reconnaissance", Zone.BATTLEFIELD, "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    assert bears.tapped
    scenario.activate(recon, targets=[TargetRef.coerce(bears)])
    scenario.resolve_top()
    assert scenario.attackers() == []
    assert not bears.tapped
    scenario.no_blocks()
    scenario.combat_damage()
    assert scenario.player("bob").life == 20
