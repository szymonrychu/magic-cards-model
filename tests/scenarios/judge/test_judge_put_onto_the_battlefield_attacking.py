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

The engine now plays the first ruling out for real: the attack trigger puts the
creature card onto the battlefield tapped and attacking (CR 508.4) and creates
CR 603.7's delayed triggered ability for the return. The devotion half is still
missing - there is no devotion-gated type-changing static ability in
`machines/layers.LAYER_EFFECTS` - so this file's Purphoros is always a creature,
which is the episode's easy case and is recorded as such below.

Card text verified with `resolve_cards`; every CR number here was looked up
with `knowledge_search(type="rules")` in this session.
"""

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


def test_ilhargs_attack_trigger_reaches_the_stack_before_it_does_anything():
    """DDR#965's baseline: the trigger is a separate object on the stack.

    Ilharg, the Raze-Boar (verified with `resolve_cards`): "Whenever Ilharg
    attacks, you may put a creature card from your hand onto the battlefield
    tapped and attacking. Return that creature to your hand at the beginning of
    the next end step."

    CR 508.1m: "Any abilities that trigger on attackers being declared
    trigger." CR 603.3 puts the ability on the stack the next time a player
    would receive priority - so declaring the attack moves nothing by itself,
    and Purphoros is still in hand with the ability waiting to resolve.
    """
    scenario = board().build()
    ilharg = scenario.creature("Ilharg, the Raze-Boar", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(ilharg)

    assert scenario.stack_names() == ["Ilharg, the Raze-Boar's triggered ability"]
    assert scenario.battlefield_names() == ["Ilharg, the Raze-Boar"]
    assert [state.card.name for state in scenario.player("alice").hand] == [
        "Purphoros, God of the Forge"
    ]


def test_declining_ilhargs_may_leaves_the_creature_in_hand():
    """ "You may" is CR 608.2d's optional question, and a controller who
    declines it moves nothing - and creates no delayed trigger either, because
    "that creature" would name nothing (CR 101.3)."""
    scenario = board().build()
    ilharg = scenario.creature("Ilharg, the Raze-Boar", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(ilharg)
    scenario.will_take_the_may(False, username="alice")
    scenario.pass_until_resolved()

    assert scenario.battlefield_names() == ["Ilharg, the Raze-Boar"]
    assert scenario.game.delayed_triggers.triggers == []


def test_an_empty_hand_is_never_even_asked():
    """CR 101.3: "any part of an instruction that's impossible to perform is
    ignored." With no creature card in hand there is nothing to choose among,
    so no question is put at all - not a question answered "no"."""
    scenario = (
        Scenario().player("alice", battlefield=["Ilharg, the Raze-Boar"]).player("bob").build()
    )
    ilharg = scenario.creature("Ilharg, the Raze-Boar", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(ilharg)
    scenario.pass_until_resolved()

    assert scenario.questions_asked() == []


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
    (CR 603.7a: it is created during the resolution of the ability that made
    it, "and not one moment earlier") that returns "that creature" at the
    beginning of the next end step - an identifier for the object, so it
    returns whether or not Purphoros is still a creature at that point.
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


def test_the_creature_put_in_attacking_was_never_declared_as_an_attacker():
    """CR 508.4c, the episode's Propaganda note: "A creature that's put onto
    the battlefield attacking or that is stated to be attacking isn't affected
    by requirements or restrictions that apply to the declaration of
    attackers."

    It was never *declared*, so nothing that triggers on attackers being
    declared (CR 508.1m) sees it - here, Ilharg's own attack trigger does not
    fire a second time off the creature it just put into combat.
    """
    scenario = board().build()
    ilharg = scenario.creature("Ilharg, the Raze-Boar", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(ilharg)
    scenario.pass_until_resolved()

    purphoros = scenario.find("Purphoros, God of the Forge", Zone.BATTLEFIELD, "alice")
    assert purphoros in scenario.attackers()
    assert scenario.stack_names() == [], "no second attack trigger"


def test_the_return_is_of_the_object_not_of_a_creature_that_is_still_one():
    """DDR#965's "that creature" ruling, from the delayed trigger's own side.

    CR 603.7c ties the delayed ability to the object it was created about, and
    the pronoun is an identifier rather than a recheck. The trigger records the
    permanent it is waiting for, and it is Purphoros itself.
    """
    scenario = board().build()
    ilharg = scenario.creature("Ilharg, the Raze-Boar", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(ilharg)
    scenario.pass_until_resolved()

    purphoros = scenario.find("Purphoros, God of the Forge", Zone.BATTLEFIELD, "alice")
    (trigger,) = scenario.game.delayed_triggers.triggers
    assert trigger.subject_id == purphoros.id
    assert trigger.source_name == "Ilharg, the Raze-Boar"


def test_purphoros_deals_its_combat_damage_alongside_ilharg():
    """DDR#965's first question, answered by playing it out: yes, it does.

    A creature put onto the battlefield attacking is an attacking creature for
    the rest of the combat, so CR 510.1 assigns its combat damage like any
    other unblocked attacker. The step it needs has to exist first, which is
    CR 508.8: "If no creatures are declared as attackers or put onto the
    battlefield attacking, skip the declare blockers and combat damage steps."
    Purphoros is the second half of that union - CR 508.4c says it was never
    declared - and Ilharg is the first.

    The steps are walked with `Game.advance` rather than by moving the turn
    pointer, because CR 508.8's skip lives on that path and nowhere else: a
    scenario that jumps straight to the combat damage step cannot tell whether
    the game would have skipped it.
    """
    scenario = board().build()
    ilharg = scenario.creature("Ilharg, the Raze-Boar", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(ilharg)
    scenario.pass_until_resolved()
    purphoros = scenario.find("Purphoros, God of the Forge", Zone.BATTLEFIELD, "alice")
    assert purphoros in scenario.attackers()

    while scenario.step is not Step.END_STEP:
        scenario.advance()

    board_state = scenario.game.computed_board()
    expected = board_state.of(ilharg).power + board_state.of(purphoros).power
    assert scenario.player("bob").life == 20 - expected, (
        "both attackers connected, Purphoros included"
    )
