"""Scenario: "Flip a coin. If you lose the flip, <consequence>." (CR 705.1,
705.2) with only a losing branch printed - nothing at all happens on a win.

The four-clause shape Ral, Monsoon Mage prints (a losing branch, a winning
branch, and an "if you do") already has its own merger
(`_merge_flip_coin_damage_or_exile_transform_clauses`, see
`tests/scenarios/test_ral_monsoon_mage.py`). This file is the shorter,
two-clause twin: `_merge_flip_coin_lose_consequence_clauses` reads
"flip a coin. If you lose the flip, <consequence>." as one CR 608.2c
instruction pair, with `<consequence>` read through the ordinary per-clause
dispatcher (`parse_mixed_effect`) rather than a shape fitted to any one
card - Goblin Kaboomist's own "this creature deals 2 damage to itself" and
off-set Mana Crypt's own "this artifact deals 3 damage to you" are two
different consequences, neither hand-written for this merger.

`Game.flip_coin` is CR 705.1's own primitive, seeded from `shuffle_seed` and
a running count the same way `Game.shuffle` is - `scenario.game.shuffle_seed`
is set explicitly in every test below so both outcomes are pinned
deterministically (seed 0's first flip is a win, seed 2's is a loss - the
same two values `test_ral_monsoon_mage.py` already established) rather than
asserted on a live coin.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 705.1** - "flip a coin... a two-sided object with easily distinguished
  sides and equal likelihood that either side lands face up."
- **CR 705.2** - "the player that flips the coin calls 'heads' or 'tails.' If
  the call matches the result, the player wins the flip. Otherwise, the
  player loses the flip."
- **CR 119.3** - "If an effect causes a player to gain life or lose life,
  that player's life total is adjusted accordingly" (damage is CR 120.3a's
  special case of this).
- **CR 120.2b** - a permanent's own ability specifies which object deals its
  damage, here "this creature"/"this artifact" - the ability's own source.
"""

from magic_cards_model.machines.abilities import TriggerEvent, parse_abilities
from magic_cards_model.machines.effects import parse_mixed_effect
from magic_cards_model.machines.triggers import AbilityKind, AbilityOnStack
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def _run_upkeep_trigger(scenario: Scenario, card_name: str):
    """Build the real `AbilityOnStack` for `card_name`'s own "beginning of
    step" trigger and resolve it directly - the same direct-call pattern
    `tests/scenarios/test_token_effect_parser.py` already uses for an
    upkeep trigger, since `start_at` moves the turn's own pointer without
    running the event-driven machinery that would otherwise put a
    beginning-of-step trigger on the stack for us.
    """
    source = scenario.creature(card_name, "alice")
    triggered_ability = next(
        a
        for a in parse_abilities(card(card_name))
        if hasattr(a, "event") and a.event is TriggerEvent.BEGINNING_OF_STEP
    )
    effect = parse_mixed_effect(triggered_ability.effect)
    assert effect is not None
    ability = AbilityOnStack(
        kind=AbilityKind.TRIGGERED,
        ability=triggered_ability,
        source_id=source.id,
        source_name=source.name,
        controller="alice",
    )
    effect(scenario.game, ability)
    return source


def test_goblin_kaboomist_damages_itself_on_a_loss():
    """On-set: Goblin Kaboomist loses the flip and deals 2 damage to
    itself - a 1/2 creature takes lethal damage."""
    scenario = Scenario().player("alice", battlefield=["Goblin Kaboomist"]).player("bob").build()
    scenario.game.shuffle_seed = 2  # the first flip at this seed is a loss

    kaboomist = _run_upkeep_trigger(scenario, "Goblin Kaboomist")

    assert kaboomist.damage == 2
    assert (kaboomist.power, kaboomist.toughness) == (1, 2)


def test_goblin_kaboomist_takes_no_damage_on_a_win():
    """The same trigger, winning the flip this time - CR 705.2's "otherwise"
    half: nothing at all is printed for a win, so nothing happens."""
    scenario = Scenario().player("alice", battlefield=["Goblin Kaboomist"]).player("bob").build()
    scenario.game.shuffle_seed = 0  # the first flip at this seed is a win

    kaboomist = _run_upkeep_trigger(scenario, "Goblin Kaboomist")

    assert kaboomist.damage == 0


def test_mana_crypt_deals_three_to_its_controller_on_a_loss():
    """Off-set: Mana Crypt: "At the beginning of your upkeep, flip a coin.
    If you lose the flip, this artifact deals 3 damage to you." Differently
    worded from Goblin Kaboomist (an artifact rather than a creature, and
    "to you" - the ability's own controller - rather than "to itself") -
    proof `_merge_flip_coin_lose_consequence_clauses` is not fitted to
    either card's own consequence clause.
    """
    scenario = Scenario().player("alice", battlefield=["Mana Crypt"]).player("bob").build()
    scenario.game.shuffle_seed = 2  # the first flip at this seed is a loss
    life_before = scenario.player("alice").life

    _run_upkeep_trigger(scenario, "Mana Crypt")

    assert scenario.player("alice").life == life_before - 3


def test_mana_crypt_loses_no_life_on_a_win():
    scenario = Scenario().player("alice", battlefield=["Mana Crypt"]).player("bob").build()
    scenario.game.shuffle_seed = 0  # the first flip at this seed is a win
    life_before = scenario.player("alice").life

    _run_upkeep_trigger(scenario, "Mana Crypt")

    assert scenario.player("alice").life == life_before


def test_goblin_kaboomists_full_upkeep_trigger_also_creates_the_land_mine_token():
    """Both instructions in the one sentence: the token-creation clause (a
    predefined-shape token with a quoted ability, `_parse_token_clause`) and
    the flip-coin-lose clause resolve together, in order (CR 608.2c), from
    one un-split `TriggeredAbility.effect` - proof the coin-flip merger
    composes with the ordinary per-clause dispatch rather than needing the
    token clause split off first.
    """
    scenario = Scenario().player("alice", battlefield=["Goblin Kaboomist"]).player("bob").build()
    scenario.game.shuffle_seed = 0  # a win: no self-damage, only the token

    kaboomist = _run_upkeep_trigger(scenario, "Goblin Kaboomist")

    land_mine = scenario.find("Land Mine", Zone.BATTLEFIELD)
    assert land_mine.card.oracle_text == (
        "{R}, Sacrifice this token: This token deals 2 damage to target "
        "attacking creature without flying."
    )
    assert kaboomist.damage == 0
