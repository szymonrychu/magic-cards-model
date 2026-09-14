"""A trigger on untapping during your own untap step, with the count carried
into its effect: "Whenever you untap one or more permanents during your untap
step, put that many time counters on this artifact" (The Millennium Calendar).

CR 502.3: "the active player determines which permanents they control will
untap. Then they untap them all simultaneously." One untap step is one event,
so a "one or more" condition triggers once for it, and "that many" is the
number of permanents that event actually untapped.

CR 502.4: "No player receives priority during the untap step, so no spells can
be cast or resolved and no abilities can be activated or resolved. Any ability
that triggers during this step will be held until the next time a player would
receive priority" - the upkeep.

CR 603.2g: "An ability triggers only if its trigger event actually occurs." An
untap step that untaps nothing did not untap one or more permanents.

The same event count reaches "put that many ... counters on this creature"
from a different event: Marauding Mako's "Whenever you discard one or more
cards" (CR 701.9a), whose discard event already carries its count.

Every CR number here was read with `mise run rules:find` in the session that
wrote this file: 502.3, 502.4, 603.2g, 122.1, 701.9a. The Millennium Calendar
is the only printing with this trigger condition (Scryfall search for "untap
one or more" with "untap step" returns it alone).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

CALENDAR = "The Millennium Calendar"
LIBRARY = ["Island"] * 10


def resolve_stack(scenario: PlayedScenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def walk_to_untap_step(scenario: PlayedScenario, active: str) -> None:
    scenario.advance()
    while not (scenario.step is Step.UNTAP and scenario.turn.active_player == active):
        resolve_stack(scenario)
        scenario.advance()


def calendar_board(*alice_extra: str, bob: list[str] | None = None) -> PlayedScenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=[CALENDAR, *alice_extra], library=list(LIBRARY))
        .player("bob", battlefield=list(bob or []), library=list(LIBRARY))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def time_counters(scenario: PlayedScenario) -> int:
    return scenario.find(CALENDAR, Zone.BATTLEFIELD, "alice").counter_count("time")


def test_three_permanents_untapped_put_three_time_counters():
    scenario = calendar_board("Forest", "Island", "Grizzly Bears")
    for name in ("Forest", "Island", "Grizzly Bears"):
        scenario.find(name, Zone.BATTLEFIELD, "alice").tap()

    walk_to_untap_step(scenario, "alice")
    assert [item.source_name for item in scenario.pending_triggers] == [CALENDAR]

    scenario.advance()  # upkeep: CR 502.4's held trigger goes on the stack
    assert scenario.stack_names() == [f"{CALENDAR}'s triggered ability"]
    resolve_stack(scenario)

    assert time_counters(scenario) == 3


def test_an_untap_step_that_untaps_nothing_does_not_trigger():
    """CR 603.2g: nothing untapped, so the trigger event never occurred."""
    scenario = calendar_board("Forest", "Island")

    walk_to_untap_step(scenario, "alice")
    assert scenario.pending_triggers == []

    scenario.advance()
    assert scenario.game.stack_is_empty
    assert time_counters(scenario) == 0


def test_the_calendar_untapping_itself_is_one_of_the_permanents_counted():
    scenario = calendar_board("Forest")
    scenario.find(CALENDAR, Zone.BATTLEFIELD, "alice").tap()
    scenario.find("Forest", Zone.BATTLEFIELD, "alice").tap()

    walk_to_untap_step(scenario, "alice")
    scenario.advance()
    resolve_stack(scenario)

    assert time_counters(scenario) == 2


def test_an_opponents_untap_step_is_not_your_untap_step():
    """ "During your untap step": bob untapping his own permanents in his own
    untap step is not alice untapping anything."""
    scenario = calendar_board(bob=["Mountain", "Mountain"])
    for mountain in [c for c in scenario.game.battlefield if c.controller == "bob"]:
        mountain.tap()

    walk_to_untap_step(scenario, "bob")
    assert scenario.pending_triggers == []

    scenario.advance()
    assert scenario.game.stack_is_empty
    assert time_counters(scenario) == 0


def test_marauding_mako_gets_that_many_counters_from_a_discard_of_two():
    """The same "put that many ... counters on this <type>" read against
    another event's count: Cathartic Reunion discards two cards as its cost."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cathartic Reunion", "Lightning Bolt", "Lightning Bolt"],
            battlefield=["Marauding Mako", "Mountain", "Mountain"],
            library=list(LIBRARY),
        )
        .player("bob", library=list(LIBRARY))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolts = [c for c in scenario.player("alice").hand if c.name == "Lightning Bolt"]

    scenario.cast_onto_stack(
        "Cathartic Reunion",
        *scenario.untapped_sources("Mountain", "Mountain"),
        discarding=bolts,
    )
    resolve_stack(scenario)

    mako = scenario.creature("Marauding Mako", "alice")
    assert mako.counter_count("+1/+1") == 2
