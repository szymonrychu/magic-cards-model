"""Ward: a trigger that counters what targeted you unless it is paid (CR 702.21).

CR 702.21a: "Ward is a triggered ability. Ward [cost] means "Whenever this
permanent becomes the target of a spell or ability an opponent controls, counter
that spell or ability unless that player pays [cost].""

Ward being a *triggered* ability rather than a targeting restriction is the
whole shape of it, and each corner case here turns on that:

- the spell is legally cast and really is on the stack while ward waits above it
  (unlike hexproof, CR 702.11b, which refuses the announcement);
- an unpaid ward counters, and CR 701.6a puts the countered spell in its owner's
  graveyard having done nothing;
- CR 701.6b: "The player who cast a countered spell or activated a countered
  ability doesn't get a 'refund' of any costs that were paid" - the mana is
  spent either way;
- ward does not trigger off its own controller's spells, because CR 702.21a says
  *an opponent controls*.

Two halves are tested separately, because they are two different questions.

**Does the trigger happen at all?** It does, without a scenario driving it:
`machines/keywords.keyword_triggered_abilities` writes CR 702.21a's expansion
out as a `TriggeredAbility`, `machines/triggers.triggered_abilities_of` hands it
to the trigger matcher alongside the printed ones, and `Casting.cast` raises the
`BECOMES_TARGET` event as the announcement finishes (CR 601.2c). So casting a
Bolt at a warded creature puts a ward trigger on the stack above it.

**What does it do when it resolves?** `Game._effect_of` asks
`machines/keywords.keyword_effect_for`, which reaches `_ward_effect` through
`TriggeredAbility.keyword`, so the game resolves ward by itself: it counters the
targeting spell unless the cost was paid.

**Where does the payment live?** On the ability on the stack. CR 702.21a's cost
is paid as the trigger *resolves*, so the object that is paid has to be the
object that resolves. `WardTrigger` is a view onto that `AbilityOnStack` and
`begin_paying` writes onto `AbilityOnStack.unless_payment`, which `_ward_effect`
reads back. There is deliberately no second ward object to fall out of step with
it, and no way to pay a ward the game will not honour - so every test below
resolves the trigger through `resolve_top` rather than by hand.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.keywords import (
    keyword_triggered_abilities,
    ward_cost,
    ward_triggers,
)
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario, mana_from


def board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Mountain", "Mountain"],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Archive Dragon", "Mountain"])
    )


def test_the_ward_cost_is_read_off_the_printing():
    """CR 702.21a's `[cost]`, as printed: Archive Dragon says Ward {2}."""
    cost = ward_cost(card("Archive Dragon"), "alice")
    assert cost is not None
    assert str(cost.mana) == "{2}"


def test_ward_is_a_triggered_ability_the_engine_can_produce():
    """CR 702.21a: "Ward is a triggered ability", not a targeting restriction.

    The card prints one word, so the ability has to come from the rule. This is
    the expansion, and it is what `machines/triggers.py` matches events against.
    """
    (ability,) = keyword_triggered_abilities(card("Archive Dragon"))
    assert ability.keyword == "ward"
    assert ability.event is TriggerEvent.BECOMES_TARGET
    assert ability.condition == (
        "this permanent becomes the target of a spell or ability an opponent controls"
    )
    assert ability.effect == "counter that spell or ability unless that player pays {2}"


def test_targeting_a_ward_creature_puts_the_trigger_on_the_stack():
    """CR 603.2, 603.3: it triggers on its own and waits above the spell.

    Nothing in this test drives ward. The Bolt is cast, the Dragon becomes a
    target (CR 601.2c), and the trigger is on the stack the next time a player
    would receive priority.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dragon = scenario.creature("Archive Dragon", "bob")

    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[dragon]
    )

    assert bolt.zone is Zone.STACK
    assert scenario.stack_names() == ["Lightning Bolt", "Archive Dragon's triggered ability"]
    trigger = scenario.game.stack[-1]
    assert trigger.controller == "bob"  # CR 702.21a: the *permanent's* controller
    assert trigger.event is not None
    assert trigger.event.targeted_by == bolt.id


def test_a_spell_targeting_its_own_controllers_creature_triggers_nothing():
    """CR 702.21a: "a spell or ability **an opponent controls**"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dragon = scenario.creature("Archive Dragon", "bob")
    scenario.pass_priority("alice")

    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[dragon],
    )
    assert scenario.stack_names() == ["Lightning Bolt"]


def test_a_spell_that_targets_a_player_triggers_no_ward():
    """Ward is a permanent's ability: a face is not a permanent it protects."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    assert scenario.stack_names() == ["Lightning Bolt"]


def test_an_unpaid_ward_counters_the_spell():
    """CR 701.6a: it never resolves, and goes to its owner's graveyard.

    Nothing here drives ward. The trigger the cast put on the stack is resolved
    by the game, finds no payment on itself, and counters.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dragon = scenario.creature("Archive Dragon", "bob")

    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[dragon]
    )

    scenario.resolve_top()  # the ward trigger

    assert bolt.zone is Zone.GRAVEYARD
    assert dragon.damage == 0
    # CR 608.2n took the ability off the stack, and CR 701.6a took the Bolt off
    # with it, so nothing is left waiting.
    assert scenario.game.stack_is_empty


def test_paying_the_ward_cost_lets_the_spell_through():
    """The cost is optional, and paying it is what stops the counter.

    The payment is opened on the ward ability that is *on the stack*, so the
    trigger the game resolves is the trigger that was paid.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dragon = scenario.creature("Archive Dragon", "bob")

    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[dragon]
    )
    (trigger,) = ward_triggers(scenario.game, bolt)

    payment = trigger.begin_paying()
    for source in scenario.untapped_sources("Mountain", "Mountain"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    assert trigger.paid

    scenario.resolve_top()  # the ward trigger, which counters nothing
    assert bolt in scenario.game.stack

    scenario.resolve_top()  # the Bolt
    assert dragon.damage == 3


def test_the_payment_lands_on_the_ability_the_game_will_resolve():
    """The view and the stack object are one thing, not two (CR 702.21a).

    This is the case a duplicate ward object got wrong: paying a standalone
    helper told the ability on the stack nothing, and the spell was countered
    anyway. `WardTrigger.begin_paying` writes onto the ability itself.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dragon = scenario.creature("Archive Dragon", "bob")

    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[dragon]
    )
    (trigger,) = ward_triggers(scenario.game, bolt)
    (stacked,) = [item for item in scenario.game.stack if item is not bolt]

    assert trigger.ability is stacked
    assert stacked.unless_payment is None

    payment = trigger.begin_paying()
    assert stacked.unless_payment is payment

    # Asking again finds the same view over the same ability and the same
    # part-made payment, rather than opening a second one.
    (again,) = ward_triggers(scenario.game, bolt)
    assert again.begin_paying() is payment


def test_the_mana_spent_on_a_countered_spell_is_not_refunded():
    """CR 701.6b: no refund. The Mountain stays tapped and the Bolt is gone."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dragon = scenario.creature("Archive Dragon", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[dragon])

    scenario.resolve_top()  # the ward trigger

    assert mountain.tapped
    assert bolt.zone is Zone.GRAVEYARD


def test_a_half_paid_ward_still_counters():
    """CR 702.21a's "unless" is satisfied by paying, not by starting to pay.

    Tapping one Mountain toward a {2} ward and never calling `pay` leaves the
    payment open, and an open payment is not a payment.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dragon = scenario.creature("Archive Dragon", "bob")

    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[dragon]
    )
    (trigger,) = ward_triggers(scenario.game, bolt)

    payment = trigger.begin_paying()
    (mountain,) = scenario.untapped_sources("Mountain")
    payment.tap_for_mana(mountain, mana_from(mountain))
    assert not trigger.paid

    scenario.resolve_top()  # the ward trigger

    assert bolt.zone is Zone.GRAVEYARD
    assert dragon.damage == 0


def test_ward_does_not_trigger_off_its_own_controllers_spell():
    """CR 702.21a: "a spell or ability an opponent controls", and bob is not one."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dragon = scenario.creature("Archive Dragon", "bob")
    scenario.pass_priority("alice")

    bolt = scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[dragon],
    )
    assert ward_triggers(scenario.game, bolt) == []


def test_the_ward_trigger_counters_the_spell_when_it_resolves():
    """CR 702.21a's effect half, resolved by the game rather than by the test.

    Nobody can be asked whether they want to pay {2}, so the cost goes unpaid
    and the spell is countered - which is the correct default, because
    CR 702.21a makes countering what happens *unless* something is done.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dragon = scenario.creature("Archive Dragon", "bob")

    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[dragon]
    )
    scenario.resolve_top()  # the ward trigger

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.game.stack_is_empty
    assert dragon.damage == 0
