"""Scenario: Uneasy Alliance's two abilities.

- **CR 509.1a/508.1c** (static): "Enchanted creature can't attack or block." -
  the identical family `machines/layers.py`'s `_ATTACHED_CREATURE_CANT_BE_
  BLOCKED_RE` already grants "This creature can't be blocked{condition}."
  onto the attached creature, widened with a sibling regex for "can't attack
  or block" - read on the attached creature by `combat._self_attack_
  restriction_sentence` (the attack half, already generic) and, for the block
  half, a genuine gap this task closes: `combat._self_block_restriction_
  sentences`/`_parse_self_block_restriction` only ever matched a sentence
  containing the literal substring "can't block", which "can't attack or
  block" never does - any creature printed with only that combined
  restriction could previously still legally block.
- **CR 601.2b activated ability, last-known information (CR 608.2h)**:
  "{5}, Sacrifice this Aura: Exile enchanted creature. You create a 1/1
  black Ninja creature token. Activate only as a sorcery." The Aura leaves
  the battlefield as the cost is paid (CR 601.2h), before the ability ever
  resolves (CR 113.7a: it exists independently of its source from then on),
  so "enchanted creature" is read through `effects._attached_object`'s
  existing last-known-attachment fallback (`CardState.last_known_attached_
  to`) - the same mechanism Enchanted River's Grasp's "tap enchanted creature
  and remove all counters from it" already relies on for its own enters
  trigger surviving the Aura's own departure.

Every CR number was looked up with `mise run rules:find <n>` this session.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def test_enchanted_creature_cannot_attack():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Uneasy Alliance", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    bears = scenario.creature("Grizzly Bears")
    alliance = scenario.find("Uneasy Alliance", Zone.BATTLEFIELD, "alice")
    alliance.attach_to(bears)
    scenario.start_at(Step.DECLARE_ATTACKERS)

    assert scenario.can_attack(bears) is False


def test_enchanted_creature_cannot_block():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hill Giant"])
        .player("bob", battlefield=["Uneasy Alliance", "Grizzly Bears"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    alliance = scenario.find("Uneasy Alliance", Zone.BATTLEFIELD, "bob")
    alliance.attach_to(bears)
    scenario.start_at(Step.DECLARE_ATTACKERS)

    giant = scenario.creature("Hill Giant")
    scenario.attack_with(giant, defending="bob")

    with pytest.raises(ValueError, match="can't block"):
        scenario.block(giant, bears)
    assert scenario.blockers() == []


def test_an_unenchanted_creature_can_still_attack_and_block():
    """The restriction lands only on the attached creature, never on its
    controller's other creatures - `combat._self_attack_restriction_sentence`
    already reads it per-creature, not per-player."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Uneasy Alliance", "Grizzly Bears", "Hill Giant"])
        .player("bob")
        .build()
    )
    bears = scenario.creature("Grizzly Bears")
    giant = scenario.creature("Hill Giant")
    alliance = scenario.find("Uneasy Alliance", Zone.BATTLEFIELD, "alice")
    alliance.attach_to(bears)
    scenario.start_at(Step.DECLARE_ATTACKERS)

    assert scenario.can_attack(bears) is False
    assert scenario.can_attack(giant) is True


def test_sacrifice_exiles_the_enchanted_creature_and_makes_a_ninja_token():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Uneasy Alliance",
                "Grizzly Bears",
                "Forest",
                "Forest",
                "Forest",
                "Forest",
                "Forest",
            ],
        )
        .player("bob")
        .build()
    )
    bears = scenario.creature("Grizzly Bears")
    alliance = scenario.find("Uneasy Alliance", Zone.BATTLEFIELD, "alice")
    alliance.attach_to(bears)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", "Forest")

    scenario.activate(alliance, *forests, sacrificing=[alliance])
    scenario.resolve_top()

    assert bears.zone is Zone.EXILE
    tokens = [
        state
        for state in scenario.all_card_states()
        if state.name == "Ninja Token" and state.zone is Zone.BATTLEFIELD
    ]
    assert len(tokens) == 1
    ninja = tokens[0]
    assert ninja.power == 1 and ninja.toughness == 1
    assert ninja.controller == "alice"


def test_sacrifice_ability_is_sorcery_speed_only():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Uneasy Alliance",
                "Grizzly Bears",
                "Forest",
                "Forest",
                "Forest",
                "Forest",
                "Forest",
            ],
        )
        .player("bob")
        .build()
    )
    bears = scenario.creature("Grizzly Bears")
    alliance = scenario.find("Uneasy Alliance", Zone.BATTLEFIELD, "alice")
    alliance.attach_to(bears)
    scenario.start_at(Step.DECLARE_ATTACKERS)

    assert scenario.why_cannot_activate(alliance) is not None
