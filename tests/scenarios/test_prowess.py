"""Prowess: a trigger on casting a noncreature spell (CR 702.108).

CR 702.108a: "Prowess is a triggered ability. 'Prowess' means "Whenever you cast
a noncreature spell, this creature gets +1/+1 until end of turn.""

Two halves, and they fail in different places, so they are tested separately.

The **trigger** is a cast trigger (CR 601.2a), and it now happens on its own:
`machines/keywords.keyword_triggered_abilities` writes CR 702.108a's expansion
out as a `TriggeredAbility` and `machines/triggers.triggered_abilities_of` hands
it to the matcher with the printed ones, so casting a Bolt puts a prowess trigger
on the stack without anything in this file driving it. Countering the spell
afterwards does not undo it - CR 603.2g only stops an ability triggering when
its event never happened, and this one did.

The **effect** is a continuous effect with a duration (CR 611.2a) in sublayer 7c
(CR 613.4c), lasting until the cleanup step (CR 500.5b, CR 514.2). `Game` holds a
`ContinuousEffects` store now and ends durational effects there, and
`machines/keywords._prowess_effect` builds the +1/+1 - but nothing runs it, for
the one reason at the bottom of this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.keywords import (
    keyword_triggered_abilities,
    prowess_bonus,
    prowess_triggers,
)
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario

NO_KEYWORD_EFFECT_DISPATCH = (
    "The prowess trigger is generated, ordered and put on the stack correctly, and "
    "then resolves doing nothing: Game._effect_of looks an ability's effect up by "
    "(card name, event) in machines/effects.TRIGGER_EFFECTS, and a keyword ability "
    "belongs to no card name. machines/keywords.keyword_effect_for answers for both "
    "kinds of keyword ability and nothing consults it. See docs/engine-coverage.md."
)


def board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt", "Watchwolf", "Counterspell"],
            battlefield=[
                "Monastery Swiftspear",
                "Mountain",
                "Island",
                "Island",
                "Plains",
                "Forest",
            ],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
    )


def test_prowess_is_a_triggered_ability_the_engine_can_produce():
    """CR 702.108a: "Prowess is a triggered ability", printed as one word."""
    (ability,) = keyword_triggered_abilities(card("Monastery Swiftspear"))
    assert ability.keyword == "prowess"
    assert ability.event is TriggerEvent.CAST_SPELL
    assert ability.condition == "you cast a noncreature spell"
    assert ability.effect == "this creature gets +1/+1 until end of turn"


def test_a_noncreature_spell_puts_the_prowess_trigger_on_the_stack():
    """CR 603.2, 603.3: it triggers on its own, above the spell that caused it."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )

    assert scenario.stack_names() == [
        "Lightning Bolt",
        "Monastery Swiftspear's triggered ability",
    ]


def test_a_noncreature_spell_triggers_prowess():
    """CR 702.108a, the happy path, asked of the keyword machinery directly."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swiftspear = scenario.creature("Monastery Swiftspear")

    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    assert prowess_triggers(scenario.game, bolt) == [swiftspear]


def test_a_creature_spell_does_not_trigger_prowess():
    """ "Noncreature spell" is the whole condition."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    wolf = scenario.cast_onto_stack("Watchwolf", *scenario.untapped_sources("Forest", "Plains"))
    assert prowess_triggers(scenario.game, wolf) == []
    assert scenario.stack_names() == ["Watchwolf"]


def test_countering_the_spell_afterwards_does_not_undo_the_trigger():
    """The trigger condition is *casting*, and the spell really was cast.

    CR 603.2g only stops an ability triggering when its event never happened.
    This one did: the Bolt reached the stack, so prowess triggered, and
    countering it later removes the spell and nothing else.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swiftspear = scenario.creature("Monastery Swiftspear")

    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    triggered = prowess_triggers(scenario.game, bolt)
    assert triggered == [swiftspear]

    scenario.cast_onto_stack(
        "Counterspell", *scenario.untapped_sources("Island", "Island"), targets=[bolt]
    )
    # Counterspell is a noncreature spell too, so prowess triggers again and
    # CR 603.3 puts that trigger on the stack *above* it (CR 117.3c hands
    # priority back to the caster first). The trigger resolves, then the
    # Counterspell.
    scenario.resolve_top()
    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert triggered == [swiftspear]


def test_an_opponents_noncreature_spell_triggers_nothing():
    """CR 702.108a says "whenever *you* cast", so the controller has to match."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")

    bolt = scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=["alice"],
    )
    assert prowess_triggers(scenario.game, bolt) == []
    assert scenario.stack_names() == ["Lightning Bolt"]


def test_prowess_needs_the_creature_to_be_on_the_battlefield():
    """A creature in hand has no prowess to trigger - it is not a creature yet."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt", "Monastery Swiftspear"],
            battlefield=["Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    assert prowess_triggers(scenario.game, bolt) == []


def test_prowess_makes_the_creature_bigger_until_end_of_turn():
    """CR 702.108a's effect half, applied by the game rather than by the test."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swiftspear = scenario.creature("Monastery Swiftspear")
    assert (swiftspear.power, swiftspear.toughness) == (1, 2)

    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    scenario.resolve_top()  # the prowess trigger

    assert scenario.game.power_of(swiftspear) == 1 + prowess_bonus[0]
    assert scenario.game.toughness_of(swiftspear) == 2 + prowess_bonus[1]


def test_the_pump_ends_in_the_cleanup_step_and_not_at_the_end_step():
    """CR 500.5b sends "until end of turn" to CR 514.2, which is cleanup.

    A creature pumped during the end step is still pumped when the end step is
    over; the effect ends in the cleanup step, at the same moment marked damage
    is wiped (CR 703.4p).
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swiftspear = scenario.creature("Monastery Swiftspear")

    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    scenario.resolve_top()
    assert scenario.game.power_of(swiftspear) == 2

    scenario.start_at(Step.END_STEP)
    assert scenario.game.power_of(swiftspear) == 2  # still pumped

    scenario.game.cleanup_step()
    assert scenario.game.power_of(swiftspear) == 1
