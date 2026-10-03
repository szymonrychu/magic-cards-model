"""Way of the Mind Sculptor's "Whenever you activate a loyalty ability, if you
removed two or more loyalty counters to activate it, draw a card."

Read out of the Comprehensive Rules on disk this session with `mise run
rules:find`:

- **CR 606.4** - the cost of a loyalty ability is a loyalty symbol, paid by
  putting counters on or removing them from the permanent; "this cost may be
  modified by other effects" (so the amount removed is the cost *actually
  paid*, not the printed number).
- **CR 603.4** - an intervening "if" is checked when the trigger event
  happens and again on resolution; the second check reads the activation's
  recorded cost (`GameEvent.loyalty_removed`), never the board, which the
  activation itself has already changed.
- **CR 606.2/606.3** - loyalty abilities and their activation.
- **CR 701.71a** - empower Jace, which gives the Way its Jace token.

Way of the Mind Sculptor is the only legal printing of the "removed N or more
loyalty counters" condition (checked against the Scryfall oracle bulk);
Ajani Unrelenting's `-2` and Jace, Reality Sculptor's `+1` are the second
printings that exercise the widened `LOYALTY_ABILITY_ACTIVATED` event.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _way_with_jace(extra_alice: list[str] | None = None, hand: int = 0):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Way of the Mind Sculptor"],
            library=["Island"] * 10,
            battlefield=extra_alice or [],
        )
        .player("bob", library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Way of the Mind Sculptor")
    scenario.pass_until_resolved()  # empower Jace 5
    jace = scenario.find("Jace", Zone.BATTLEFIELD, "alice")
    assert jace.loyalty == 5
    return scenario, jace


def _resolve_all(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def test_minus_one_removes_one_counter_so_the_way_does_not_draw():
    scenario, jace = _way_with_jace()
    hand = len(scenario.player("alice").hand)

    scenario.activate(jace, index=0)  # [-1]: Surveil 1
    _resolve_all(scenario)

    assert jace.loyalty == 4
    assert len(scenario.player("alice").hand) == hand, "one counter removed is below two"


def test_minus_three_removed_three_counters_so_the_way_draws_in_addition_to_the_ability():
    scenario, jace = _way_with_jace()
    hand = len(scenario.player("alice").hand)

    scenario.activate(jace, index=1)  # [-3]: Draw a card.
    _resolve_all(scenario)

    assert jace.loyalty == 2
    assert len(scenario.player("alice").hand) == hand + 2, "the Way's draw plus the [-3]'s own"


def test_a_minus_two_on_another_planeswalker_counts_too():
    scenario, _jace = _way_with_jace(extra_alice=["Ajani Unrelenting"])
    ajani = scenario.find("Ajani Unrelenting", Zone.BATTLEFIELD, "alice")
    scenario.player("alice").hand.clear()

    scenario.activate(ajani, index=1)  # -2: discard hand, then draw per creature
    scenario.game.put_triggers_on_stack()
    names = scenario.stack_names()

    assert "Way of the Mind Sculptor's triggered ability" in names
    assert "Ajani Unrelenting's triggered ability" in names


def test_a_plus_one_never_draws():
    scenario, _jace = _way_with_jace(extra_alice=["Ajani Unrelenting"])
    ajani = scenario.find("Ajani Unrelenting", Zone.BATTLEFIELD, "alice")

    scenario.activate(ajani, index=0)  # +1
    scenario.game.put_triggers_on_stack()

    assert "Way of the Mind Sculptor's triggered ability" not in scenario.stack_names()


def _activated_events(scenario):
    return {
        trigger.event.subject_name: trigger.event.loyalty_removed
        for trigger in scenario.game.stack
        if trigger.event is not None and trigger.event.event.value == "loyalty_ability_activated"
    }


def test_the_event_carries_the_loyalty_actually_removed():
    """Read off the event a trigger persists (`AbilityOnStack.event`), on two
    printings: the Way's own trigger for a [-3], Ajani Unrelenting's for a +1."""
    scenario, jace = _way_with_jace(extra_alice=["Ajani Unrelenting"])
    ajani = scenario.find("Ajani Unrelenting", Zone.BATTLEFIELD, "alice")

    scenario.activate(jace, index=1)  # [-3]
    scenario.game.put_triggers_on_stack()
    assert _activated_events(scenario) == {"Jace": 3}
    _resolve_all(scenario)

    scenario.activate(ajani, index=0)  # +1, a different permanent's own once-per-turn
    scenario.game.put_triggers_on_stack()
    assert _activated_events(scenario) == {"Ajani Unrelenting": 0}


def test_the_resolution_check_reads_the_recorded_cost_not_the_board():
    """CR 603.4: the Jace is back at five loyalty by the time the trigger
    resolves, but the activation removed three - the draw still happens."""
    scenario, jace = _way_with_jace()
    hand = len(scenario.player("alice").hand)

    scenario.activate(jace, index=1)  # [-3]
    scenario.game.put_triggers_on_stack()
    scenario.game.add_counters(jace, "loyalty", 3)  # board no longer shows any removal
    way_trigger = scenario.game.stack[-1]
    assert way_trigger.source_name == "Way of the Mind Sculptor"
    scenario.resolve_top()

    assert len(scenario.player("alice").hand) == hand + 1


def test_an_opponents_activation_does_not_trigger_the_way():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Way of the Mind Sculptor"],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=["Ajani Unrelenting"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.CLEANUP)
    scenario.advance()
    while scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()
    ajani = scenario.find("Ajani Unrelenting", Zone.BATTLEFIELD, "bob")

    scenario.activate(ajani, index=1, username="bob")  # -2
    scenario.game.put_triggers_on_stack()

    assert "Way of the Mind Sculptor's triggered ability" not in scenario.stack_names()
