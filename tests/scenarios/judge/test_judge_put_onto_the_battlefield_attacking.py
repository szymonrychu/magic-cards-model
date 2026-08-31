"""Judge scenarios: a creature card put onto the battlefield tapped and
attacking, and what "that creature" still refers to afterwards.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#965** - Ilharg, the Raze-Boar + Purphoros, God of the Forge. Amy
  attacks with Ilharg and puts Purphoros onto the battlefield. Does Purphoros
  deal combat damage? Is it returned to Amy's hand at end of turn?

Two rulings. With devotion to red of five or more Purphoros is a creature, so
it attacks and deals damage like any other (CR 508.4: "If a creature is put
onto the battlefield attacking, its controller chooses which defending player
... it's attacking", and CR 508.4c exempts it from attack requirements and
restrictions such as Propaganda). And the return happens either way: "that
creature" in Ilharg's delayed trigger is an identifier for the object, so
Purphoros comes back to hand even if devotion has fallen and it is no longer a
creature by the end step.

The engine puts Ilharg's attack trigger on the stack correctly and then does
nothing with it, and has no devotion-driven type-changing static ability at
all - so the rulings themselves are `xfail`.

Card text verified with `resolve_cards`; every CR number here was looked up
with `knowledge_search(type="rules")` in this session.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import AbilityKind, parse_abilities
from magic_cards_model.machines.layers import LAYER_EFFECTS
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    """Alice attacking with Ilharg, Purphoros waiting in hand."""
    return (
        Scenario()
        .player(
            "alice",
            hand=["Purphoros, God of the Forge"],
            battlefield=["Ilharg, the Raze-Boar"],
        )
        .player("bob")
    )


def test_ilhargs_attack_trigger_reaches_the_stack_and_does_nothing():
    """DDR#965's baseline: the trigger is real, its effect is not.

    Ilharg, the Raze-Boar (verified with `resolve_cards`): "Whenever Ilharg
    attacks, you may put a creature card from your hand onto the battlefield
    tapped and attacking. Return that creature to your hand at the beginning of
    the next end step."

    CR 508.1m: "Any abilities that trigger on attackers being declared
    trigger." The engine gets that far - `TriggerEvent.ATTACKS` matches and the
    ability goes on the stack (CR 603.3). Resolving it performs nothing:
    `machines/effects.py` has no reader for "put a creature card from your hand
    onto the battlefield tapped and attacking", so Purphoros stays in hand.

    (Contrast `models/token._put_onto_the_battlefield_attacking`, which handles
    the *token* half of CR 508.4 and is exercised by
    `tests/scenarios/test_tokens.py`. The primitive exists; nothing routes a
    card from hand into it.)
    """
    scenario = board().build()
    ilharg = scenario.creature("Ilharg, the Raze-Boar", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(ilharg)

    assert scenario.stack_names() == ["Ilharg, the Raze-Boar's triggered ability"]

    scenario.pass_until_resolved()

    assert scenario.battlefield_names() == ["Ilharg, the Raze-Boar"]
    assert [state.card.name for state in scenario.player("alice").hand] == [
        "Purphoros, God of the Forge"
    ]


def test_ilhargs_return_clause_is_part_of_the_same_trigger_paragraph():
    """DDR#965's "that creature" point, read off the parse.

    CR 603.1 templates a triggered ability as "[When/Whenever/At] [trigger
    condition or event], [effect]. [Instructions (if any).]" - the trailing
    return sentence is part of the same ability, not a separate one, which is
    why "that creature" can refer back to whatever the first sentence put onto
    the battlefield.

    That reference is an identifier for the object, not a check that it is
    still a creature, which is the whole reason Purphoros comes back even when
    devotion has dropped below five.
    """
    abilities = parse_abilities(card("Ilharg, the Raze-Boar"))
    attacks = [
        ability
        for ability in abilities
        if ability.kind is AbilityKind.TRIGGERED and ability.condition == "Ilharg attacks"
    ]

    (attack_trigger,) = attacks
    assert "onto the battlefield tapped and attacking" in attack_trigger.effect
    assert "Return that creature to your hand" in attack_trigger.effect


def test_purphoros_has_no_devotion_gated_type_change():
    """DDR#965's other premise: whether Purphoros is a creature at all.

    Purphoros, God of the Forge (verified with `resolve_cards`): "As long as
    your devotion to red is less than five, Purphoros isn't a creature."

    That is a continuous effect in CR 613's layer 4 (type-changing), and there
    is no row for it in `machines/layers.LAYER_EFFECTS` - the same hand-written
    registry gap DDR#982, DDR#801 and DDR#1010 already record in this package.
    So the engine treats Purphoros as a creature on the battlefield regardless
    of devotion, which happens to match the episode's *easy* case (devotion of
    five or more) and silently mismatches the interesting one.

    Devotion itself is not missing - `machines/effects.py` counts CR 700.5's
    "your devotion to `<color>`" for Gray Merchant of Asphodel. It is the
    static ability keyed off it that has no home.
    """
    assert "Purphoros, God of the Forge" not in LAYER_EFFECTS

    scenario = (
        Scenario()
        .player("alice", battlefield=["Purphoros, God of the Forge"])
        .player("bob")
        .build()
    )
    purphoros = scenario.find("Purphoros, God of the Forge", Zone.BATTLEFIELD, "alice")

    assert purphoros.is_creature, "devotion is never consulted"


@pytest.mark.xfail(
    reason="Ilharg's 'put a creature card from your hand onto the battlefield "
    "tapped and attacking' has no reader in machines/effects.py, so the "
    "trigger resolves and moves nothing; the delayed return trigger "
    "(CR 603.7) is never created either",
    strict=True,
)
def test_purphoros_is_put_in_attacking_and_returns_to_hand_at_end_of_turn():
    """DDR#965's ruling, written out.

    CR 508.4 puts Purphoros onto the battlefield attacking, tapped, with its
    controller choosing what it attacks - which need not be what Ilharg is
    attacking. CR 508.4c: "A creature that's put onto the battlefield attacking
    or that is stated to be attacking isn't affected by requirements or
    restrictions that apply to the declaration of attackers", the episode's
    Propaganda note. It was never *declared* as an attacker, so nothing that
    triggers on attackers being declared (CR 508.1m) sees it.

    Then Ilharg's second sentence sets up a delayed triggered ability
    (CR 603.7) that returns "that creature" at the beginning of the next end
    step - an identifier for the object, so it returns whether or not Purphoros
    is still a creature at that point.

    Not runnable: the first sentence does nothing at all, so there is no
    permanent to return.
    """
    scenario = board().build()
    ilharg = scenario.creature("Ilharg, the Raze-Boar", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(ilharg)
    scenario.pass_until_resolved()

    purphoros = scenario.find("Purphoros, God of the Forge", Zone.BATTLEFIELD, "alice")
    assert purphoros.tapped
    assert purphoros in scenario.attackers()

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert purphoros.zone is Zone.HAND
