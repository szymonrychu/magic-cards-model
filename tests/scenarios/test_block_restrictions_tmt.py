"""Scenario: three CR 508.1c/509.1a/509.1b combat restrictions from Teenage
Mutant Ninja Turtles (round 271-tmt).

- **CR 509.1a** (evasion): "`<this>` can't be blocked by creatures with power
  3 or greater." - April O'Neil, Kunoichi Trainee's own printing, and the
  mirror-image sibling of the already-read "power N or less" shape
  (`combat._CANT_BE_BLOCKED_BY_POWER_OR_LESS_RE`). Proved generic on Azure
  Beastbinder, a different Modern/Pioneer/Standard-legal printing of the
  identical template (verified with `resolve_cards`/Scryfall this session,
  2026-09-27; not a listed card, not in any `code/magic-cards-model-api/
  decks/*.txt` list).
- **CR 508.1c/509.1b** (a restriction on the creature's own attacking and
  blocking): "This creature can't attack or block unless its power is 6 or
  greater." - Technodrome. `card_search` found no second Modern/Pioneer/
  Standard-legal printing of this exact power-threshold shape (checked this
  session) - see `MEMORY.md`'s dated line - so the parser is written general
  (either direction, either action alone or both) and proved on Technodrome
  itself in both directions (below 6 power refused, at or above allowed).
- **CR 509.1a** (evasion, condition-gated): "This creature can't be blocked
  if an artifact entered the battlefield under your control this turn." -
  Fugitive Droid. The condition itself is not new: `machines/conditions.
  history._counted_entered` already reads "an artifact entered the
  battlefield under your control this turn" for every other condition-gated
  reader in the pool (an "as long as"/intervening-"if"/modal condition); this
  clause only teaches `combat.evasion_restriction_refusal` to hand a generic
  "can't be blocked if `<condition>`" tail to `Game.condition_holds` instead
  of assuming every "if" is a power comparison.

Every CR number was looked up with `mise run rules:find <n>` this session.
"""

import pytest

from magic_cards_model.machines import Step

from .harness import Scenario

# --------------------------------------------------------------------------
# April O'Neil, Kunoichi Trainee - "can't be blocked by creatures with power
# 3 or greater" (CR 509.1a)
# --------------------------------------------------------------------------


def test_april_oneil_cannot_be_blocked_by_a_power_3_creature():
    scenario = (
        Scenario()
        .player("alice", battlefield=["April O'Neil, Kunoichi Trainee"])
        .player("bob", battlefield=["Watchwolf"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    april = scenario.creature("April O'Neil, Kunoichi Trainee")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.attack_with(april)

    with pytest.raises(ValueError, match="can't be blocked"):
        scenario.block(april, wolf)
    assert scenario.blockers() == []


def test_april_oneil_can_be_blocked_by_a_power_2_creature():
    scenario = (
        Scenario()
        .player("alice", battlefield=["April O'Neil, Kunoichi Trainee"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    april = scenario.creature("April O'Neil, Kunoichi Trainee")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(april)
    scenario.block(april, bears)

    assert scenario.blockers() == [bears]


def test_azure_beastbinder_proves_the_same_power_or_greater_template():
    """A second, differently-worded printing of "can't be blocked by
    creatures with power N or greater" (Azure Beastbinder also has vigilance
    and an attack trigger, unlike April O'Neil), Modern/Pioneer/Standard
    legal, not in the deck pool."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Azure Beastbinder"])
        .player("bob", battlefield=["Watchwolf", "Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    beastbinder = scenario.creature("Azure Beastbinder")
    wolf = scenario.creature("Watchwolf", "bob")
    elf = scenario.creature("Llanowar Elves", "bob")
    scenario.attack_with(beastbinder)

    with pytest.raises(ValueError, match="can't be blocked"):
        scenario.block(beastbinder, wolf)
    assert scenario.blockers() == []

    scenario.block(beastbinder, elf)
    assert scenario.blockers() == [elf]


# --------------------------------------------------------------------------
# Technodrome - "can't attack or block unless its power is 6 or greater"
# (CR 508.1c / 509.1b)
# --------------------------------------------------------------------------


def test_technodrome_below_six_power_cannot_attack():
    scenario = Scenario().player("alice", battlefield=["Technodrome"]).player("bob").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    technodrome = scenario.creature("Technodrome")
    assert technodrome.power == 3

    assert scenario.can_attack(technodrome) is False


def test_technodrome_below_six_power_cannot_block():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hill Giant"])
        .player("bob", battlefield=["Technodrome"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant")
    technodrome = scenario.creature("Technodrome", "bob")
    scenario.attack_with(giant, defending="bob")

    with pytest.raises(ValueError, match="can't block"):
        scenario.block(giant, technodrome)
    assert scenario.blockers() == []


def test_technodrome_at_six_power_can_attack_and_block():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Technodrome"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    technodrome = scenario.creature("Technodrome")
    for _ in range(3):
        technodrome.counters.add("+1/+1", 1)
    assert technodrome.power == 6

    assert scenario.can_attack(technodrome) is True
    scenario.attack_with(technodrome)
    scenario.no_blocks()
    scenario.combat_damage()
    assert scenario.player("bob").life == 14


# --------------------------------------------------------------------------
# Fugitive Droid - "can't be blocked if an artifact entered the battlefield
# under your control this turn" (CR 509.1a, condition-gated)
# --------------------------------------------------------------------------


def test_fugitive_droid_unblockable_after_an_artifact_enters():
    scenario = (
        Scenario()
        .player("alice", hand=["Ornithopter"], battlefield=["Fugitive Droid"])
        .player("bob", battlefield=["Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    droid = scenario.creature("Fugitive Droid")
    scenario.cast_and_resolve("Ornithopter")

    scenario.advance()  # precombat main -> declare attackers
    scenario.attack_with(droid)
    wolf = scenario.creature("Watchwolf", "bob")

    with pytest.raises(ValueError, match="can't be blocked"):
        scenario.block(droid, wolf)
    assert scenario.blockers() == []


def test_fugitive_droid_blockable_with_no_artifact_this_turn():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Fugitive Droid"])
        .player("bob", battlefield=["Watchwolf"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    droid = scenario.creature("Fugitive Droid")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.attack_with(droid)
    scenario.block(droid, wolf)

    assert scenario.blockers() == [wolf]
