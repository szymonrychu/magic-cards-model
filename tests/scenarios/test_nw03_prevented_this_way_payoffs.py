"""Scenario: CR 615.5 payoffs on a prevention shield - "If damage is
prevented this way, <self> deals that much damage to <target>", "you may have
<self> deal that much damage to target creature", "For each 1 damage
prevented this way, put a +1/+1 counter on that creature", "You gain life
equal to the damage prevented this way" - and the "Prevent all damage target
spell would deal this turn." shield Hallow's payoff hangs off.

Rules, each read in full with `mise run rules:find`:

- CR 615.5 - "Some prevention effects also include an additional effect,
  which may refer to the amount of damage that was prevented. The prevention
  takes place at the time the original event would have happened; the rest of
  the effect takes place immediately afterward."
- CR 615.7 - the next-N shield, used up 1 per 1 damage prevented.
- CR 601.2c - every target, the rider's included, is chosen as the spell is
  cast.
- CR 608.2b - an illegal target is not affected by the parts of the effect
  that need it; the other parts still happen.
- CR 608.2d - "you may" is chosen as the effect is applied.
- CR 609.7a - "If the player chooses a permanent spell, the effect will apply
  to any damage dealt by that spell and any damage dealt by the permanent that
  spell becomes when it resolves."
- CR 400.7c - "Prevention effects that apply to damage from a permanent spell
  on the stack continue to apply to damage from the permanent that spell
  becomes."
- CR 105.2b - "A multicolored object is two or more of the five colors."

Listed printings: Acolyte's Reward, Brace for Impact, Test of Faith, Channel
Harm, Hallow. Proof printings, none listed, none in an api deck, all legal in
Modern: Vengeful Archon (an activated "{X}: Prevent the next X damage that
would be dealt to you this turn. If damage is prevented this way, this
creature deals that much damage to target player or planeswalker."), Candles'
Glow ("Prevent the next 3 damage that would be dealt to any target this turn.
You gain life equal to the damage prevented this way."), Dromoka's Command
(its "Prevent all damage target instant or sorcery spell would deal this
turn." mode), and Divine Deflection (regression proof of the NW-02 shape).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario


@pytest.mark.parametrize(
    "name",
    [
        "Acolyte's Reward",
        "Brace for Impact",
        "Test of Faith",
        "Channel Harm",
        "Hallow",
        "Vengeful Archon",
        "Candles' Glow",
        "Dromoka's Command",
        "Divine Deflection",
    ],
)
def test_every_listed_and_proof_card_reads_handled(name):
    outcomes = {clause.outcome for clause in card_support(card(name)).clauses}
    assert outcomes == {"handled"}, name


def _board(
    *,
    alice_battlefield=(),
    bob_battlefield=(),
    alice_hand=(),
    bob_hand=(),
    bob_first=False,
):
    alice = {
        "hand": list(alice_hand),
        "battlefield": [*["Plains"] * 6, "Forest", *alice_battlefield],
        "library": ["Plains"] * 8,
    }
    bob = {
        "hand": list(bob_hand),
        "battlefield": [*["Mountain"] * 6, *bob_battlefield],
        "library": ["Mountain"] * 8,
    }
    builder = Scenario()
    order = [("bob", bob), ("alice", alice)] if bob_first else [("alice", alice), ("bob", bob)]
    for name, seat in order:
        builder = builder.player(name, **seat)
    scenario = builder.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _alice_casts(scenario, name, targets):
    if scenario.priority_holder != "alice":
        scenario.pass_priority(scenario.priority_holder)
    return scenario.cast_and_resolve(name, username="alice", targets=targets, auto=True)


def _bob_casts(scenario, name, target):
    if scenario.priority_holder != "bob":
        scenario.pass_priority(scenario.priority_holder)
    return scenario.cast_and_resolve(name, username="bob", targets=[target], auto=True)


# -- "If damage is prevented this way, <self> deals that much damage to ..." -


def test_acolytes_reward_deals_the_prevented_amount_to_its_other_target():
    # Serra Angel {3}{W}{W}: devotion to white 2.
    scenario = _board(
        alice_hand=["Acolyte's Reward"],
        alice_battlefield=["Serra Angel"],
        bob_hand=["Lightning Bolt"],
    )
    angel = scenario.creature("Serra Angel", "alice")
    _alice_casts(scenario, "Acolyte's Reward", [angel, "bob"])

    _bob_casts(scenario, "Lightning Bolt", angel)

    assert angel.damage == 1
    assert scenario.player("bob").life == 18


def test_acolytes_reward_can_send_the_damage_to_a_creature():
    scenario = _board(
        alice_hand=["Acolyte's Reward"],
        alice_battlefield=["Serra Angel"],
        bob_battlefield=["Grizzly Bears"],
        bob_hand=["Lightning Bolt"],
    )
    angel = scenario.creature("Serra Angel", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    _alice_casts(scenario, "Acolyte's Reward", [angel, bears])

    _bob_casts(scenario, "Lightning Bolt", angel)

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 20


def test_acolytes_reward_with_its_rider_target_gone_still_shields():
    scenario = _board(
        alice_hand=["Acolyte's Reward"],
        alice_battlefield=["Serra Angel"],
        bob_battlefield=["Grizzly Bears"],
        bob_hand=["Lightning Bolt"],
    )
    angel = scenario.creature("Serra Angel", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    casting = scenario.cast("Acolyte's Reward", username="alice")
    casting.choose_targets([angel, bears])
    scenario.auto_pay(casting.begin_paying(), username="alice")
    scenario.put_on_stack(casting)
    scenario.game.return_to_hand(bears)  # CR 608.2b: the rider's target is gone
    scenario.resolve_top()

    _bob_casts(scenario, "Lightning Bolt", angel)

    assert angel.damage == 1  # the shield still took 2
    assert scenario.player("bob").life == 20


def test_acolytes_reward_with_nothing_prevented_deals_nothing():
    scenario = _board(
        alice_hand=["Acolyte's Reward"],
        alice_battlefield=["Serra Angel", "Grizzly Bears"],
        bob_hand=["Lightning Bolt"],
    )
    angel = scenario.creature("Serra Angel", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    _alice_casts(scenario, "Acolyte's Reward", [angel, "bob"])

    _bob_casts(scenario, "Lightning Bolt", bears)

    assert scenario.player("bob").life == 20


def test_vengeful_archon_turns_prevented_damage_to_you_on_a_player():
    scenario = _board(alice_battlefield=["Vengeful Archon"], bob_hand=["Lightning Bolt"])
    archon = scenario.find("Vengeful Archon", Zone.BATTLEFIELD, "alice")
    scenario.activate(archon, username="alice", targets=["bob"], x_value=2, auto=True)
    scenario.resolve_top()

    _bob_casts(scenario, "Lightning Bolt", "alice")

    assert scenario.player("alice").life == 19
    assert scenario.player("bob").life == 18


# -- "you may have <self> deal that much damage" (Channel Harm) --------------


def _channel_harm_board(**kwargs):
    return _board(
        alice_hand=["Channel Harm"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Hill Giant"],
        bob_first=True,
        **kwargs,
    )


def _attack_and_channel(scenario, *, take):
    giant = scenario.creature("Hill Giant", "bob")
    scenario.attack_with(giant, defending="alice")
    scenario.no_blocks()
    scenario.will_take_the_may(take, username="alice")
    _alice_casts(scenario, "Channel Harm", [giant])
    scenario.combat_damage()
    return giant


def test_channel_harm_prevents_and_may_send_the_damage_back():
    scenario = _channel_harm_board()

    giant = _attack_and_channel(scenario, take=True)

    assert scenario.player("alice").life == 20
    assert giant.zone is Zone.GRAVEYARD


def test_channel_harm_declined_still_prevents():
    scenario = _channel_harm_board()

    giant = _attack_and_channel(scenario, take=False)

    assert scenario.player("alice").life == 20
    assert giant.damage == 0


def test_channel_harm_does_not_prevent_damage_from_your_own_sources():
    scenario = _board(
        alice_hand=["Channel Harm", "Shock"],
        alice_battlefield=["Mountain", "Hill Giant"],
        bob_battlefield=["Grizzly Bears"],
    )
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_and_resolve(
        "Channel Harm",
        *scenario.untapped_sources(*["Plains"] * 6, username="alice"),
        username="alice",
        targets=[bears],
    )

    _alice_casts(scenario, "Shock", [giant])

    assert giant.damage == 2
    assert bears.damage == 0


# -- "For each 1 damage prevented this way, put a +1/+1 counter on ..." -----


def test_test_of_faith_turns_prevented_damage_into_counters():
    scenario = _board(
        alice_hand=["Test of Faith"],
        alice_battlefield=["Grizzly Bears"],
        bob_hand=["Lightning Bolt"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    _alice_casts(scenario, "Test of Faith", [bears])

    _bob_casts(scenario, "Lightning Bolt", bears)

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.damage == 0
    assert bears.counters["+1/+1"] == 3


def test_test_of_faith_counts_only_what_its_three_shield_prevented():
    scenario = _board(
        alice_hand=["Test of Faith"],
        alice_battlefield=["Grizzly Bears"],
        bob_hand=["Shock", "Shock"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    _alice_casts(scenario, "Test of Faith", [bears])

    _bob_casts(scenario, "Shock", bears)
    _bob_casts(scenario, "Shock", bears)

    assert bears.counters["+1/+1"] == 3
    assert bears.damage == 1
    assert bears.zone is Zone.BATTLEFIELD


def test_test_of_faith_on_a_creature_that_takes_no_damage_adds_nothing():
    scenario = _board(
        alice_hand=["Test of Faith"],
        alice_battlefield=["Grizzly Bears"],
        bob_hand=["Lightning Bolt"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    _alice_casts(scenario, "Test of Faith", [bears])

    _bob_casts(scenario, "Lightning Bolt", "alice")

    assert bears.counters["+1/+1"] == 0


def test_brace_for_impact_prevents_everything_into_counters():
    scenario = _board(
        alice_hand=["Brace for Impact"],
        alice_battlefield=["Watchwolf"],
        bob_hand=["Lightning Bolt", "Shock"],
    )
    wolf = scenario.creature("Watchwolf", "alice")
    _alice_casts(scenario, "Brace for Impact", [wolf])

    _bob_casts(scenario, "Lightning Bolt", wolf)
    _bob_casts(scenario, "Shock", wolf)

    assert wolf.damage == 0
    assert wolf.counters["+1/+1"] == 5


def test_brace_for_impact_cannot_target_a_monocolored_creature():
    scenario = _board(alice_hand=["Brace for Impact"], alice_battlefield=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    casting = scenario.cast("Brace for Impact", username="alice")

    with pytest.raises(ValueError):  # CR 105.2b: not multicolored
        casting.choose_targets([bears])


def test_brace_for_impact_counts_combat_damage_from_several_blockers():
    scenario = _board(
        alice_hand=["Brace for Impact"],
        alice_battlefield=["Watchwolf"],
        bob_battlefield=["Grizzly Bears", "Hill Giant"],
    )
    wolf = scenario.creature("Watchwolf", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.attack_with(wolf, defending="bob")
    scenario.block(wolf, bears, giant)
    _alice_casts(scenario, "Brace for Impact", [wolf])
    scenario.will_assign_combat_damage((bears, 2), (giant, 1), username="alice")
    scenario.combat_damage()

    assert wolf.zone is Zone.BATTLEFIELD
    assert wolf.counters["+1/+1"] == 5


# -- "You gain life equal to the damage prevented this way." ----------------


def test_candles_glow_gains_the_prevented_amount():
    scenario = _board(
        alice_hand=["Candles' Glow"],
        alice_battlefield=["Grizzly Bears"],
        bob_hand=["Lightning Bolt"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    _alice_casts(scenario, "Candles' Glow", [bears])

    _bob_casts(scenario, "Lightning Bolt", bears)

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 23


def test_candles_glow_gains_only_what_was_prevented():
    scenario = _board(alice_hand=["Candles' Glow"], bob_hand=["Shock"])
    _alice_casts(scenario, "Candles' Glow", ["alice"])

    _bob_casts(scenario, "Shock", "alice")

    assert scenario.player("alice").life == 22


def test_hallow_prevents_the_target_spells_damage_and_gains_that_much():
    scenario = _board(alice_hand=["Hallow"], bob_hand=["Lightning Bolt"], bob_first=True)
    bolt = scenario.cast_onto_stack("Lightning Bolt", username="bob", targets=["alice"], auto=True)
    scenario.pass_priority("bob")
    scenario.cast_and_resolve("Hallow", username="alice", targets=[bolt], auto=True)

    scenario.resolve_top()

    assert scenario.player("alice").life == 23


def test_hallow_does_not_prevent_another_spells_damage():
    scenario = _board(alice_hand=["Hallow"], bob_hand=["Lightning Bolt", "Shock"], bob_first=True)
    bolt = scenario.cast_onto_stack("Lightning Bolt", username="bob", targets=["alice"], auto=True)
    scenario.pass_priority("bob")
    scenario.cast_and_resolve("Hallow", username="alice", targets=[bolt], auto=True)
    scenario.resolve_top()

    _bob_casts(scenario, "Shock", "alice")

    assert scenario.player("alice").life == 21


def test_hallow_on_a_creature_spell_covers_the_permanent_it_becomes():
    scenario = _board(alice_hand=["Hallow"], bob_hand=["Raging Goblin"], bob_first=True)
    goblin_spell = scenario.cast_onto_stack("Raging Goblin", username="bob", auto=True)
    scenario.pass_priority("bob")
    scenario.cast_and_resolve("Hallow", username="alice", targets=[goblin_spell], auto=True)
    scenario.resolve_top()
    goblin = scenario.creature("Raging Goblin", "bob")

    scenario.attack_with(goblin, defending="alice")
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("alice").life == 21


def test_dromokas_command_prevents_the_target_instants_damage():
    scenario = _board(
        alice_hand=["Dromoka's Command"],
        alice_battlefield=["Grizzly Bears"],
        bob_hand=["Lightning Bolt"],
        bob_first=True,
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", username="bob", targets=[bears], auto=True)
    scenario.pass_priority("bob")
    casting = scenario.cast("Dromoka's Command", username="alice")
    casting.choose_modes([1, 3])
    casting.choose_targets([bolt, bears])
    scenario.auto_pay(casting.begin_paying(), username="alice")
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    scenario.resolve_top()

    assert bears.damage == 0
    assert bears.counters["+1/+1"] == 1
    assert scenario.player("alice").life == 20  # no life rider on this one
