"""Scenario: "`<this>` must be blocked if able" (CR 509.1c) - a requirement
stated from the attacker's own side rather than a blocker's.

CR 509.1c: "The defending player checks each creature they control to see
whether it's affected by any requirements (effects that say a creature must
block, or that it must block if some condition is met). If the number of
requirements that are being obeyed is fewer than the maximum possible number
of requirements that could be obeyed without disobeying any restrictions, the
declaration of blockers is illegal." Looked up this session with `mise run
rules:find 509.1`.

"Must be blocked if able" carries no rule of its own by that exact wording -
it is read the way Gaea's Protector's own Wizards rulings spell it out:

- "Only one creature is required to block Gaea's Protector. Other creatures
  may also block it, and are free to block other creatures or not block at
  all." - the requirement is satisfied by *any single* legal blocker, unlike
  a named "blocks `<attacker>`" requirement that binds one specific creature.
- "If each creature the defending player controls can't block for any reason
  ... then Gaea's Protector isn't blocked. If there's a cost associated with
  blocking Gaea's Protector, the defending player isn't forced to pay that
  cost, so it doesn't have to be blocked in that case either." - CR 509.1c's
  own "maximum obeyable" and unpaid-cost language, read from this side.

Two printings: Raphael, Ninja Destroyer (the listed card, whose own Enrage
trigger is proved separately in `test_persistent_mana_enrage.py`) and Gaea's
Protector (the proof printing, Modern/Pioneer legal, not a listed card, not in
any deck list - verified with `resolve_cards`/Scryfall this session,
2026-09-27).
"""

import pytest

from magic_cards_model.machines import Step

from .harness import Scenario


def test_gaeas_protector_declaration_illegal_when_a_legal_blocker_is_left_home():
    """A legal blocker exists (Grizzly Bears, untapped, no restriction of its
    own) but the defending player declares no blocks at all - CR 509.1c's
    maximum-obeyed comparison refuses the declaration."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Gaea's Protector"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    protector = scenario.creature("Gaea's Protector")
    scenario.attack_with(protector)

    with pytest.raises(ValueError, match="must be blocked"):
        scenario.no_blocks()
    assert scenario.blockers() == []


def test_gaeas_protector_one_blocker_satisfies_the_requirement():
    """Gaea's Protector's own ruling: only one creature is required - a
    second, untapped creature left home does not make the declaration
    illegal."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Gaea's Protector"])
        .player("bob", battlefield=["Grizzly Bears", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    protector = scenario.creature("Gaea's Protector")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(protector)
    scenario.block(protector, bears)

    assert scenario.blockers() == [bears]


def test_gaeas_protector_unblocked_when_every_creature_cannot_block():
    """Gaea's Protector's own ruling: a tapped creature is not a legal
    blocker, so a declaration leaving the attacker unblocked is legal when
    every creature the defending player controls is tapped."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Gaea's Protector"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    protector = scenario.creature("Gaea's Protector")
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.tapped = True
    scenario.attack_with(protector)
    scenario.no_blocks()

    assert scenario.blockers() == []


def test_raphael_ninja_destroyer_declaration_illegal_when_left_unblocked():
    """The listed card's own printing of the identical requirement."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Raphael, Ninja Destroyer"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    raphael = scenario.creature("Raphael, Ninja Destroyer")
    scenario.attack_with(raphael)

    with pytest.raises(ValueError, match="must be blocked"):
        scenario.no_blocks()
    assert scenario.blockers() == []
