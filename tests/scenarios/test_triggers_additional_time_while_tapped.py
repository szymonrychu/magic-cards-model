"""Scenario: "{2}, {T}: Choose another target creature you control. For as long
as Lwaxana Troi remains tapped, if a triggered ability of that creature
triggers, that ability triggers an additional time." (Lwaxana Troi, Charming
Guest), with "You may choose not to untap Lwaxana Troi during your untap step."

CR 603.2d: a trigger that triggers additional times is put on the stack that
many times; CR 611.2b: the duration ends the moment the source is untapped (or
leaves); CR 502.3: the untap-step choice keeps it tapped, and the doubling,
into the next turn. No other legal printing grants one creature's triggers an
extra time for a duration (Scryfall, in the writing session).

CR rules cited here were looked up with `mise run rules:find` in the writing
session.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario

LWAXANA = "Lwaxana Troi, Charming Guest"


def board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Raging Goblin", "Raging Goblin"],
            battlefield=[LWAXANA, "Soul Warden", "Grizzly Bears"] + ["Mountain"] * 4,
            library=["Island"] * 6,
        )
        .player("bob", library=["Island"] * 6)
    )


def activate(scenario, target):
    lwaxana = scenario.creature(LWAXANA, "alice")
    scenario.activate(lwaxana, *scenario.untapped_sources("Mountain", "Mountain"), targets=[target])
    scenario.pass_until_resolved()
    return lwaxana


def goblin_enters(scenario):
    scenario.cast_and_resolve("Raging Goblin", *scenario.untapped_sources("Mountain"))


def test_the_chosen_creatures_trigger_triggers_twice():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    activate(scenario, scenario.creature("Soul Warden", "alice"))
    goblin_enters(scenario)
    assert scenario.stack_names() == ["Soul Warden's triggered ability"] * 2
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 22


def test_another_creature_is_not_doubled():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    activate(scenario, scenario.creature("Grizzly Bears", "alice"))
    goblin_enters(scenario)
    assert scenario.stack_names() == ["Soul Warden's triggered ability"]


def test_the_doubling_ends_when_lwaxana_untaps():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lwaxana = activate(scenario, scenario.creature("Soul Warden", "alice"))
    lwaxana.untap()
    goblin_enters(scenario)
    assert scenario.stack_names() == ["Soul Warden's triggered ability"]


def test_lwaxana_troi_charming_guest_stays_tapped_and_keeps_doubling():
    """Her controller chooses not to untap her: next turn the chosen Soul
    Warden still triggers twice."""
    scenario = board().automatic_turn_based_actions().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lwaxana = activate(scenario, scenario.creature("Soul Warden", "alice"))
    scenario.will_take_the_may(True, source=LWAXANA)
    while scenario.turn.active_player != "bob":
        scenario.advance()
    while not (scenario.turn.active_player == "alice" and scenario.step is Step.PRECOMBAT_MAIN):
        scenario.advance()
    assert lwaxana.tapped
    goblin_enters(scenario)
    assert scenario.stack_names() == ["Soul Warden's triggered ability"] * 2
