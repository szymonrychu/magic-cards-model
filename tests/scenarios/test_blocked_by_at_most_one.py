"""Scenario: "can't be blocked by more than one creature" (CR 509.1b) - the
mirror image of menace (CR 702.111b), and just as much a restriction on the
whole finished block declaration rather than on any single (blocker,
attacker) pair: a lone blocker is fine, but a second one on the same attacker
makes the declaration illegal.

CR 509.1b: "The defending player checks each creature they control to see
whether it's affected by any restrictions (effects that say a creature can't
block, or that it can't block unless some condition is met). If any
restrictions are being disobeyed, the declaration of blockers is illegal. A
restriction may be created by an evasion ability (a static ability an
attacking creature has that restricts what can block it)." Looked up in this
session with `mise run rules:find 509.1`.

Two shapes are read, both by `combat.blocked_by_at_most_one_refusal` /
`combat.declaration_refusal`:

- **Charging Rhino**: "This creature can't be blocked by more than one
  creature." - printed, unconditional.
- **Akawalli, the Seething Tower**: "Descend 8 — As long as there are eight
  or more permanent cards in your graveyard, Akawalli gets an additional
  +2/+2 and can't be blocked by more than one creature." - conditional,
  granted only once the descend-8 threshold is met (`test_descend_ability_
  word.py` carries the graveyard-count half of this proof; the graveyard
  scaffolding for that card lives there, not here).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def duel(attacker: str, *blockers: str, bob_life: int = 20) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=[attacker])
        .player("bob", life=bob_life, battlefield=list(blockers))
    )


def test_charging_rhino_cannot_be_blocked_by_two_creatures():
    """CR 509.1b: two blockers on an attacker printed with this restriction
    is an illegal declaration - Charging Rhino carries no keyword of its own
    for it, only the plain sentence."""
    scenario = duel("Charging Rhino", "Watchwolf", "Hill Giant").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    rhino = scenario.creature("Charging Rhino")
    wolf = scenario.creature("Watchwolf", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.attack_with(rhino)

    with pytest.raises(ValueError, match="can't be blocked by more than one creature"):
        scenario.block(rhino, wolf, giant)
    assert scenario.blockers() == []


def test_charging_rhino_can_be_blocked_by_exactly_one_creature():
    scenario = duel("Charging Rhino", "Watchwolf").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    rhino = scenario.creature("Charging Rhino")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.attack_with(rhino)
    scenario.block(rhino, wolf)
    scenario.combat_damage()

    assert wolf.zone is Zone.GRAVEYARD, "the Rhino's 4 power is lethal for a 3/3"
    assert rhino.damage == 3
    assert rhino.zone is Zone.BATTLEFIELD, "the Wolf's 3 damage is not lethal for a 4/4"


def test_charging_rhino_unblocked_gets_through():
    scenario = duel("Charging Rhino", "Watchwolf").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    rhino = scenario.creature("Charging Rhino")
    scenario.attack_with(rhino)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 16


def test_akawalli_descended_eight_cannot_be_blocked_by_two_creatures():
    """The conditional shape, proven end to end in combat: eight permanent
    cards in alice's graveyard turns on both the +2/+2 and the block cap
    (`test_descend_ability_word.py` proves the pump and the raw condition
    gating in isolation)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Akawalli, the Seething Tower"],
            graveyard=[
                "Grizzly Bears",
                "Mountain",
                "Sol Ring",
                "Elvish Mystic",
                "Watchwolf",
                "Hill Giant",
                "Llanowar Elves",
                "Forest",
            ],
        )
        .player("bob", life=20, battlefield=["Serra Angel", "Colossal Dreadmaw"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    akawalli = scenario.creature("Akawalli, the Seething Tower")
    angel = scenario.creature("Serra Angel", "bob")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.attack_with(akawalli)

    with pytest.raises(ValueError, match="can't be blocked by more than one creature"):
        scenario.block(akawalli, angel, dreadmaw)
    assert scenario.blockers() == []


def test_akawalli_descended_four_only_can_be_blocked_by_two_creatures():
    """Below the descend-8 threshold the block cap is not granted at all -
    only the descend-4 pump and trample are active, so two blockers are a
    perfectly legal declaration."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Akawalli, the Seething Tower"],
            graveyard=["Grizzly Bears", "Mountain", "Sol Ring", "Elvish Mystic"],
        )
        .player("bob", life=20, battlefield=["Serra Angel", "Colossal Dreadmaw"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    akawalli = scenario.creature("Akawalli, the Seething Tower")
    angel = scenario.creature("Serra Angel", "bob")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.attack_with(akawalli)
    scenario.block(akawalli, angel, dreadmaw)

    assert scenario.blockers() == [angel, dreadmaw]


def test_a_single_block_leaves_no_evasion_notice_behind():
    """The restriction is read and enforced, so a legal single block must not
    also record an `EvasionNotice` claiming the sentence went unread."""
    scenario = duel("Charging Rhino", "Watchwolf").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    rhino = scenario.creature("Charging Rhino")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.attack_with(rhino)
    scenario.block(rhino, wolf)

    assert scenario.game.is_blocked(rhino)
    assert scenario.game.evasion_notices == []
