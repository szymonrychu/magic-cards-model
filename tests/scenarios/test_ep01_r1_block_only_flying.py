"""Scenario: "`<this>` can block only creatures with flying." (CR 509.1b), in
its self, enchanted-creature and group forms.

CR 509.1b: "The defending player checks each creature they control to see
whether it's affected by any restrictions (effects that say a creature can't
block, or that it can't block unless some condition is met). If any
restrictions are being disobeyed, the declaration of blockers is illegal."
"Can block only creatures with flying" is that restriction read the other way
round: a blocker may block exactly the attackers the description names and no
others. Reach does not widen it - the restriction is on what the creature may
block, not on what can block a flyer.

Proof printings (all real Modern/Pioneer legal printings; every legal printing
of the template is a listed card, so two different-wording listed cards stand
in for the "second printing" - Brazen Borrower and Cloud Sprite state the same
sentence with and without a flying reminder, Gloomwidow pairs it with reach):

- self: Brazen Borrower, Cloud Sprite, Gloomwidow, Soulcipher Board's back
  face (Cipherbound Spirit)
- enchanted creature: Stratus Walk
- group (all creatures with flying, either controller): Dense Canopy
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card

from .harness import Scenario

_LISTED = [
    "Brazen Borrower",
    "Cloud Elemental",
    "Cloud Sprite",
    "Dreamcaller Siren",
    "Etherium Pteramander",
    "Gloomwidow",
    "Hoverguard Observer",
    "Long-Finned Skywhale",
    "Scrapskin Drake",
    "Shacklegeist",
    "Skywinder Drake",
    "Soulcipher Board",
    "Stormbound Geist",
    "Stormcloud Djinn",
    "Stratozeppelid",
    "Tattered Haunter",
    "Vaporkin",
    "Wanderlight Spirit",
    "Welkin Tern",
    "Dense Canopy",
    "Stratus Walk",
]


def duel(attackers: list[str], blockers: list[str]) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=attackers)
        .player("bob", battlefield=blockers)
    )


def _attack(scenario, attacker_name: str):
    scenario.start_at(Step.DECLARE_ATTACKERS)
    attacker = scenario.creature(attacker_name)
    scenario.attack_with(attacker)
    return attacker


@pytest.mark.parametrize("name", _LISTED)
def test_every_listed_card_reads_its_block_only_line_as_handled(name):
    clauses = [
        clause
        for clause in classify_clauses(card(name))
        if "can block only creatures with flying" in clause.text
    ]
    assert clauses, f"{name}: no clause carries the block-only line"
    assert all(clause.category == HANDLED for clause in clauses), clauses


# -- self form ---------------------------------------------------------------


def test_brazen_borrower_cannot_block_a_ground_attacker():
    scenario = duel(["Hill Giant"], ["Brazen Borrower"]).build()
    giant = _attack(scenario, "Hill Giant")
    borrower = scenario.creature("Brazen Borrower", "bob")

    reason = scenario.game.why_cannot_block(borrower, giant)
    assert reason is not None and "can block only creatures with flying" in reason
    assert "CR 509.1b" in reason
    with pytest.raises(ValueError, match="can block only creatures with flying"):
        scenario.block(giant, borrower)
    assert scenario.blockers() == []


def test_brazen_borrower_can_block_a_flyer():
    scenario = duel(["Serra Angel"], ["Brazen Borrower"]).build()
    angel = _attack(scenario, "Serra Angel")
    borrower = scenario.creature("Brazen Borrower", "bob")

    assert scenario.game.can_block(borrower, angel)
    scenario.block(angel, borrower)
    assert scenario.blockers() == [borrower]


def test_cloud_sprite_is_refused_on_the_ground_and_allowed_in_the_air():
    scenario = duel(["Hill Giant", "Serra Angel"], ["Cloud Sprite"]).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant")
    angel = scenario.creature("Serra Angel")
    scenario.attack_with(giant, angel)
    sprite = scenario.creature("Cloud Sprite", "bob")

    assert not scenario.game.can_block(sprite, giant)
    assert scenario.game.can_block(sprite, angel)
    with pytest.raises(ValueError, match="can block only creatures with flying"):
        scenario.block(giant, sprite)
    scenario.block(angel, sprite)
    assert scenario.blockers() == [sprite]


def test_reach_does_not_widen_the_restriction():
    """Gloomwidow has reach and the restriction: it blocks flyers only, so a
    ground attacker is still refused."""
    scenario = duel(["Hill Giant", "Serra Angel"], ["Gloomwidow"]).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant")
    angel = scenario.creature("Serra Angel")
    scenario.attack_with(giant, angel)
    widow = scenario.creature("Gloomwidow", "bob")

    assert not scenario.game.can_block(widow, giant)
    assert scenario.game.can_block(widow, angel)


def test_a_flying_blocker_with_the_restriction_still_cannot_block_the_ground():
    """Flying on the blocker is irrelevant: the attacker has to have it."""
    scenario = duel(["Grizzly Bears"], ["Cloud Elemental"]).build()
    bears = _attack(scenario, "Grizzly Bears")
    elemental = scenario.creature("Cloud Elemental", "bob")

    assert not scenario.game.can_block(elemental, bears)


def test_an_unrestricted_blocker_beside_it_still_blocks_the_ground():
    scenario = duel(["Hill Giant"], ["Cloud Elemental", "Grizzly Bears"]).build()
    giant = _attack(scenario, "Hill Giant")
    elemental = scenario.creature("Cloud Elemental", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.block(giant, bears)
    assert scenario.blockers() == [bears]
    assert not scenario.game.can_block(elemental, giant)


def test_an_attacker_that_gains_flying_can_be_blocked_by_the_restricted_creature():
    """The description is read against the attacker's computed abilities
    (CR 613.5): Stratus Walk gives a ground attacker flying."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Stratus Walk", "Hill Giant"])
        .player("bob", battlefield=["Cloud Elemental"])
        .build()
    )
    giant = scenario.creature("Hill Giant")
    walk = scenario.find("Stratus Walk", Zone.BATTLEFIELD, "alice")
    walk.attach_to(giant)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(giant)
    elemental = scenario.creature("Cloud Elemental", "bob")

    assert scenario.game.can_block(elemental, giant)


def test_the_back_face_carries_the_restriction_once_transformed():
    """Soulcipher Board // Cipherbound Spirit: the back face (a creature)
    prints the restriction."""
    scenario = duel(["Hill Giant"], ["Soulcipher Board"]).build()
    board = scenario.find("Soulcipher Board", Zone.BATTLEFIELD, "bob")
    board.transform()
    giant = _attack(scenario, "Hill Giant")

    assert not scenario.game.can_block(board, giant)


# -- enchanted creature (Stratus Walk) ----------------------------------------


def test_stratus_walk_restricts_the_enchanted_creature():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Hill Giant", "Serra Angel"])
        .player("bob", battlefield=["Stratus Walk", "Grizzly Bears"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    walk = scenario.find("Stratus Walk", Zone.BATTLEFIELD, "bob")
    walk.attach_to(bears)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant")
    angel = scenario.creature("Serra Angel")
    scenario.attack_with(giant, angel)

    reason = scenario.game.why_cannot_block(bears, giant)
    assert reason is not None and "can block only creatures with flying" in reason
    assert scenario.game.can_block(bears, angel)  # Stratus Walk gave it flying


def test_the_restriction_is_only_on_the_enchanted_creature():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Hill Giant"])
        .player("bob", battlefield=["Stratus Walk", "Grizzly Bears", "Runeclaw Bear"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    other = scenario.creature("Runeclaw Bear", "bob")
    walk = scenario.find("Stratus Walk", Zone.BATTLEFIELD, "bob")
    walk.attach_to(bears)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant")
    scenario.attack_with(giant)

    assert not scenario.game.can_block(bears, giant)
    assert scenario.game.can_block(other, giant)


def test_an_unattached_aura_restricts_nobody():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Hill Giant"])
        .player("bob", battlefield=["Stratus Walk", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant")
    scenario.attack_with(giant)
    bears = scenario.creature("Grizzly Bears", "bob")

    assert scenario.game.can_block(bears, giant)


# -- group form (Dense Canopy) -------------------------------------------------


def test_dense_canopy_stops_every_flyer_blocking_the_ground_whoever_controls_it():
    scenario = duel(["Hill Giant", "Dense Canopy"], ["Wind Drake", "Grizzly Bears"]).build()
    giant = _attack(scenario, "Hill Giant")
    drake = scenario.creature("Wind Drake", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")

    reason = scenario.game.why_cannot_block(drake, giant)
    assert reason is not None and "can block only creatures with flying" in reason
    assert scenario.game.can_block(bears, giant)  # no flying: not touched
    scenario.block(giant, bears)
    assert scenario.blockers() == [bears]


def test_dense_canopy_lets_a_flyer_block_a_flyer():
    scenario = duel(["Serra Angel", "Dense Canopy"], ["Wind Drake"]).build()
    angel = _attack(scenario, "Serra Angel")
    drake = scenario.creature("Wind Drake", "bob")

    assert scenario.game.can_block(drake, angel)


def test_without_dense_canopy_the_flyer_blocks_the_ground():
    scenario = duel(["Hill Giant"], ["Wind Drake"]).build()
    giant = _attack(scenario, "Hill Giant")
    drake = scenario.creature("Wind Drake", "bob")

    assert scenario.game.can_block(drake, giant)
