"""'If you control no <subtype>s, <self> deals N damage to you.'

Sarkhan's Rage ({4}{R}): "Sarkhan's Rage deals 5 damage to any target. If you
control no Dragons, Sarkhan's Rage deals 2 damage to you."

CR 608.2c: the second sentence is followed after the first, and its condition
is checked as it is followed - on resolution, never at cast time. CR 120.3a /
CR 109.5: "you" is the spell's controller, the damage's source is the spell
(CR 120.1) and it is dealt to the controller whatever the first sentence hit.
No other printing in Modern, Pioneer or Standard carries this sentence, so the
generic reader is proven here with a second subtype run through the same
resolver (`effect_for`) on the real spell.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import effect_for
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

LANDS = ["Mountain"] * 5


def _board(alice_extra=(), bob_battlefield=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Sarkhan's Rage"], battlefield=LANDS + list(alice_extra))
        .player("bob", battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _rage(scenario, target="bob"):
    scenario.cast_and_resolve(
        "Sarkhan's Rage", *scenario.untapped_sources(*LANDS), targets=[target]
    )
    return scenario.player("alice").life, scenario.player("bob").life


def test_no_dragons_deals_two_to_you_as_well():
    assert _rage(_board()) == (18, 15)


def test_a_dragon_you_control_spares_you():
    assert _rage(_board(alice_extra=["Shivan Dragon"])) == (20, 15)


def test_a_creature_that_is_not_a_dragon_does_not_spare_you():
    assert _rage(_board(alice_extra=["Grizzly Bears"])) == (18, 15)


def test_only_a_dragon_you_control_counts():
    assert _rage(_board(bob_battlefield=["Shivan Dragon"])) == (18, 15)


def test_the_self_damage_follows_a_creature_target_too():
    scenario = _board(bob_battlefield=["Serra Angel"])
    angel = scenario.creature("Serra Angel", "bob")
    assert _rage(scenario, angel) == (18, 20)
    assert angel.zone is Zone.GRAVEYARD


# -- A second subtype through the same reader -----------------------------------


def _resolve_text(text, alice_extra=()):
    scenario = _board(alice_extra=alice_extra)
    spell = scenario.cast_onto_stack(
        "Sarkhan's Rage", *scenario.untapped_sources(*LANDS), targets=["bob"]
    )
    effect = effect_for("Sarkhan's Rage", text)
    effect(scenario.game, spell)
    return scenario.player("alice").life, scenario.player("bob").life


def test_a_second_subtype_reads_the_same_way():
    text = (
        "Sarkhan's Rage deals 5 damage to any target. "
        "If you control no Goblins, Sarkhan's Rage deals 3 damage to you."
    )
    assert _resolve_text(text) == (17, 15)
    assert _resolve_text(text, alice_extra=["Goblin Guide"]) == (20, 15)
