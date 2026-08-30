"""Cascade: exile until something cheaper turns up (CR 702.85).

CR 702.85a: "Cascade is a triggered ability that functions only while the spell
with cascade is on the stack. 'Cascade' means "When you cast this spell, exile
cards from the top of your library until you exile a nonland card that costs
less. You may cast it without paying its mana cost. Put the exiled cards on the
bottom in a random order.""

Every clause in that sentence is a corner case:

- **nonland** - a land is never the hit, however cheap;
- **costs less** - strictly less than the cascading spell's mana value, so an
  equal-cost card is skipped;
- **until** - everything passed on the way is exiled too, and only the hit is
  kept out of the library;
- **you may** - casting the hit is optional, and there is nobody here to ask, so
  the scenario decides (the same concession every optional trigger makes);
- **on the bottom** - the misses go back, and the library is longer at the
  bottom rather than shorter.

The trigger now happens on its own: `machines/keywords.keyword_triggered_abilities`
writes CR 702.85a's expansion out as a `TriggeredAbility` and
`machines/triggers.py` matches the cast event against it. CR 702.85a's "functions
only while the spell with cascade is on the stack" is what makes the *spell* the
source, which is why `Game.emit` asking the spells on the stack matters. What it
does when it resolves is `cascade`, still driven by hand here - see the xfail at
the bottom and `docs/engine-coverage.md`.

The exiling here is checked against the current wording of CR 702.85a, which
says "a nonland card **whose mana value is less than this spell's mana value**".
Shardless Agent's printed reminder text still says "that costs less"; the rule
is the authority.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.keywords import cascade, has_cascade, keyword_triggered_abilities
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario

NO_KEYWORD_EFFECT_DISPATCH = (
    "The cascade trigger is generated and put on the stack above the spell, and then "
    "resolves doing nothing: Game._effect_of looks an ability's effect up by "
    "(card name, event) in machines/effects.TRIGGER_EFFECTS, and a keyword ability "
    "belongs to no card name. machines/keywords.keyword_effect_for answers and "
    "nothing consults it. See docs/engine-coverage.md."
)


def board(*library: str) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Shardless Agent"],
            library=list(library),
            battlefield=["Forest", "Island", "Forest"],
        )
        .player("bob")
    )


def cast_the_agent(scenario):
    return scenario.cast_onto_stack(
        "Shardless Agent", *scenario.untapped_sources("Forest", "Island", "Forest")
    )


def test_cascade_is_read_off_the_printing():
    assert has_cascade(card("Shardless Agent"))
    assert not has_cascade(card("Grizzly Bears"))


def test_cascade_stops_at_the_first_cheaper_nonland_card():
    """CR 702.85a: Lightning Bolt costs 1, Shardless Agent costs 3."""
    scenario = board("Lightning Bolt", "Counterspell").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    agent = cast_the_agent(scenario)

    result = cascade(scenario.game, agent, seed=0)

    assert result.hit is not None
    assert result.hit.name == "Lightning Bolt"
    assert result.hit.zone is Zone.EXILE


def test_lands_are_never_the_hit():
    """ "a nonland card" - a Forest has mana value 0 and is still skipped."""
    scenario = board("Forest", "Forest", "Lightning Bolt").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    agent = cast_the_agent(scenario)

    result = cascade(scenario.game, agent, seed=0)

    assert result.hit is not None
    assert result.hit.name == "Lightning Bolt"
    assert [state.name for state in result.exiled] == ["Forest", "Forest", "Lightning Bolt"]


def test_a_card_costing_the_same_is_not_cheaper():
    """ "costs less" is strict: Kitchen Finks is 3, and so is Shardless Agent."""
    scenario = board("Kitchen Finks", "Lightning Bolt").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    agent = cast_the_agent(scenario)

    result = cascade(scenario.game, agent, seed=0)

    assert result.hit is not None
    assert result.hit.name == "Lightning Bolt"


def test_everything_passed_on_the_way_goes_to_the_bottom():
    """The misses go back to the library, and only the hit stays in exile."""
    scenario = board("Forest", "Kitchen Finks", "Lightning Bolt", "Island").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    agent = cast_the_agent(scenario)

    result = cascade(scenario.game, agent, seed=1)

    library = scenario.player("alice").library
    assert result.hit is not None and result.hit.name == "Lightning Bolt"
    assert sorted(state.name for state in library) == ["Forest", "Island", "Kitchen Finks"]
    assert scenario.game.exile == [result.hit]


def test_an_empty_library_finds_nothing_and_loses_nobody_the_game():
    """ "until" runs out. Nothing is found, and cascade is not a draw (CR 704.5b)."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    agent = cast_the_agent(scenario)

    result = cascade(scenario.game, agent, seed=0)

    assert result.hit is None
    assert result.exiled == []
    assert not scenario.player("alice").tried_to_draw_from_empty_library


def test_a_library_with_nothing_cheap_exiles_the_whole_thing():
    """The trigger keeps going until the library is empty, and everything comes back."""
    scenario = board("Kitchen Finks", "Forest", "Colossal Dreadmaw").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    agent = cast_the_agent(scenario)

    result = cascade(scenario.game, agent, seed=2)

    assert result.hit is None
    assert len(result.exiled) == 3
    assert scenario.game.exile == []
    assert len(scenario.player("alice").library) == 3


def test_the_hit_may_be_cast_from_exile_without_paying_its_mana_cost():
    """ "You may cast it without paying its mana cost" - the free half.

    Casting from exile is permission the cascade *effect* grants, not something
    the card's own text does, so the spell is put on the stack directly rather
    than through `Casting` - `machines/casting.keyword_cast_options` reads
    permission printed on the card, and cascade prints it on a different card.
    """
    scenario = board("Lightning Bolt").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    agent = cast_the_agent(scenario)
    result = cascade(scenario.game, agent, seed=0)

    assert result.hit is not None
    scenario.game.exile.remove(result.hit)
    scenario.game.put_on_stack(result.hit, "alice")
    result.hit.targets = []

    assert result.hit.zone is Zone.STACK
    assert all(source.tapped for source in scenario.game.battlefield)


def test_cascade_is_a_triggered_ability_the_engine_can_produce():
    """CR 702.85a: "Cascade is a triggered ability", printed as one word."""
    (ability,) = keyword_triggered_abilities(card("Shardless Agent"))
    assert ability.keyword == "cascade"
    assert ability.event is TriggerEvent.CAST_SPELL
    assert ability.condition == "you cast this spell"


def test_casting_it_puts_the_cascade_trigger_on_the_stack():
    """CR 702.85a's "functions only while the spell ... is on the stack".

    The source of the trigger is the *spell*, not a permanent, so it is only
    findable because the cast event asks the stack as well as the battlefield
    (CR 603.2). Nothing in this test drives cascade.
    """
    scenario = board("Lightning Bolt", "Counterspell").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    cast_the_agent(scenario)

    assert scenario.stack_names() == [
        "Shardless Agent",
        "Shardless Agent's triggered ability",
    ]


def test_an_instant_with_cascade_triggers_the_same_way():
    """CR 702.85a is about the spell, not about the permanent it becomes."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Violent Outburst"],
            library=["Lightning Bolt"],
            battlefield=["Mountain", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_onto_stack(
        "Violent Outburst", *scenario.untapped_sources("Mountain", "Forest", "Forest")
    )

    assert scenario.stack_names() == [
        "Violent Outburst",
        "Violent Outburst's triggered ability",
    ]


def test_the_cascade_trigger_exiles_when_it_resolves():
    """CR 702.85a's effect half, run by the game rather than by the test."""
    scenario = board("Lightning Bolt", "Counterspell").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cast_the_agent(scenario)

    scenario.resolve_top()  # the cascade trigger

    bolt = scenario.find("Lightning Bolt", Zone.EXILE)
    assert bolt.zone is Zone.EXILE
