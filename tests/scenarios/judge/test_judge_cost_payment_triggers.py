"""Judge scenarios: a trigger caused by paying an activation cost resolves first.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#1004** - Limited RCQ Tournament Report

The episode's two rules questions are both the same shape: everything before the
colon is a cost, paid while the ability is being activated (CR 602.2a-b), and
anything that triggers *from paying that cost* has therefore triggered before
any player would receive priority. CR 603.3 then puts it on the stack "the next
time a player would receive priority" - which is after the activated ability is
already there, so the trigger sits on top of it and resolves first (CR 608.1).

The episode's own cards are a Lorwyn Eclipsed limited pool (Gristle Glutton,
"Heirloom Antie", "Ward Eye Witch", "Drown to Sulka") whose spoken names do not
all resolve - `resolve_cards` finds Gristle Glutton but not the others - so the
scenario is built from two real printings in the pool with exactly the shape the
ruling is about: Vampiric Rites ("{1}{B}, Sacrifice a creature: You gain 1 life
and draw a card.") and Blood Artist ("Whenever this creature or another creature
dies, target player loses 1 life and you gain 1 life."). Both texts confirmed
with `resolve_cards`.

Every CR number here was looked up with `knowledge_search(type="rules")` in the
session that wrote the file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board():
    return (
        Scenario()
        .player(
            "alice",
            life=20,
            library=["Grizzly Bears"],
            battlefield=[
                "Vampiric Rites",
                "Blood Artist",
                "Grizzly Bears",
                "Swamp",
                "Swamp",
            ],
        )
        .player("bob", life=20)
    )


def _activate_the_rites(scenario):
    """Pay {1}{B} and sacrifice the Bears - the whole cost, before the ability
    is on the stack (CR 602.2b)."""
    scenario.choose_trigger_targets("Blood Artist", ["bob"])
    rites = scenario.find("Vampiric Rites", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Swamp", "Swamp", username="alice")
    scenario.activate(rites, *sources, sacrificing=[bears])
    return bears


def test_paying_the_cost_happens_before_the_ability_is_on_the_stack():
    """CR 602.2a-b: the ability is activated by announcing it, choosing targets,
    determining and then paying its costs; only when all of that is done is it
    "activated" and on the stack.

    So the sacrificed creature is already in the graveyard while the ability
    waits there - which is what makes the trigger below possible at all.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bears = _activate_the_rites(scenario)

    assert bears.zone is Zone.GRAVEYARD


def test_the_dies_trigger_goes_on_the_stack_above_the_ability_it_paid_for():
    """CR 603.3: "Once an ability has triggered, its controller puts it on the
    stack as an object that's not a card the next time a player would receive
    priority."

    No player receives priority during CR 602.2's activation, so the Blood
    Artist trigger lands on the stack afterwards - on top of the Vampiric Rites
    ability that was put there first.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _activate_the_rites(scenario)

    assert scenario.stack_names() == [
        "Vampiric Rites's activated ability",
        "Blood Artist's triggered ability",
    ]


def test_the_trigger_resolves_before_the_ability_that_caused_it():
    """CR 608.1: "the spell or ability that's on top of the stack is the object
    that resolves" - so the answer to the episode's question is that the trigger
    happens first, and the ability's own effect second.

    Blood Artist drains bob for one and gains alice one; only then does Vampiric
    Rites gain its life and draw its card. alice is at 21 with an empty hand at
    the halfway point, which is the assertion that pins the *order* rather than
    just the totals.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_the_rites(scenario)

    scenario.resolve_top()

    assert scenario.player("alice").life == 21
    assert scenario.player("bob").life == 19
    assert scenario.player("alice").hand == []

    scenario.resolve_top()

    assert scenario.player("alice").life == 22
    assert [state.name for state in scenario.player("alice").hand] == ["Grizzly Bears"]


def test_nothing_is_left_on_the_stack_once_both_have_resolved():
    """The tidy-up assertion: two objects went on, two came off (CR 608.1)."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_the_rites(scenario)

    scenario.resolve_top()
    scenario.resolve_top()

    assert scenario.stack_names() == []
