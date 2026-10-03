"""Scenario: Rampaging Geoderm's own "Whenever you attack, target attacking
creature gets +1/+1 until end of turn. If it's attacking a battle, put a
+1/+1 counter on it instead." - `_parse_layer_counter_instead_upgrade`'s
existing "if `<condition>`, put N counters on it instead" shape, with two
things this session added: a condition reader for CR 508.1's declared
defender (`_attacking_defender_quality`, `machines/conditions/objects.py`),
and a fix to `layer_or_counter_instead` itself, which used to ask the
condition about the *ability's own source* (Rampaging Geoderm) rather than
the object its own pump names ("target attacking creature") - for every
existing card in the "instead" family the condition never named an object at
all, so nothing had caught this until a condition that does ("it's attacking
a battle") existed.

The battle is alice's own Siege, with bob chosen as its protector (CR
310.9a, 310.12a): a Siege can be attacked by its own controller (CR 310.9b),
so alice's Geoderm attacks it with bob defending. The read is off the
declared defender alone: false when attacking a player, true only when the
declared defender is a real `Type.BATTLE` permanent right now.

Rules verified with `mise run rules:find` (on-disk CR effective 2026-09-25):

- **CR 508.1a** - a creature is declared attacking a player, planeswalker,
  or battle.
- **CR 508.1b** - a battle is one of the eligible defenders when the
  defending player is the protector of any battles.
- **CR 310.9b** - a battle can be attacked by any attacking player for whom
  its protector is a defending player; a Siege by its own controller.
- **CR 614.1a** - "instead" replaces the whole preceding sentence's effect.
- **CR 608.2h** - a resolving instruction uses current information about the
  object it names - what the target's attack looks like *now*, not as it was
  declared, though nothing changes it here.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def computed(scenario: Scenario):
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


def _board():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Rampaging Geoderm"], hand=["Invasion of Amonkhet"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("bob", username="alice", source="Invasion of Amonkhet")
    scenario.put_onto_battlefield("Invasion of Amonkhet", "alice")
    return scenario


def test_attacking_a_player_pumps_without_a_counter():
    scenario = _board()
    geoderm = scenario.creature("Rampaging Geoderm", "alice")
    scenario.advance()
    scenario.attack_with(geoderm)  # the default defender: bob, a player
    scenario.choose_trigger_targets("Rampaging Geoderm", [geoderm])
    scenario.pass_until_resolved()

    assert geoderm.counter_count(Counter.PLUS_ONE) == 0
    assert computed(scenario).of(geoderm).power_toughness == (4, 4), "a 3/3 plus a temporary +1/+1"


def test_attacking_a_battle_upgrades_to_a_counter():
    from magic_cards_model.models.card import Type

    scenario = _board()
    geoderm = scenario.creature("Rampaging Geoderm", "alice")
    (battle,) = [
        permanent
        for permanent in scenario.game.permanents_controlled_by("alice")
        if Type.BATTLE in scenario.game.characteristics_of(permanent).types
    ]
    scenario.advance()
    scenario.attack_with(geoderm, defending=battle)
    scenario.choose_trigger_targets("Rampaging Geoderm", [geoderm])
    scenario.pass_until_resolved()

    assert geoderm.counter_count(Counter.PLUS_ONE) == 1, "the counter, not the temporary pump"
    assert computed(scenario).of(geoderm).power_toughness == (4, 4), (
        "the same +1/+1, now a lasting counter"
    )
