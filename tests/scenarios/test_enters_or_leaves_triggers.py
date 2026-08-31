"""Scenario: one printed condition that names two trigger events.

Sewer-veillance Cam reads "When this artifact enters **or leaves** the
battlefield, you may tap or untap target creature."
`machines/abilities._trigger_event` reads the first event word it recognises
and stops, so this parsed as an enters-the-battlefield trigger alone and the
departure half - the half a deck actually uses, since the Cam's own
"{3}{U}, Sacrifice this artifact: Draw two cards" is how it leaves - was
silently dropped. `machines/triggers._expand_enters_or_leaves` now splits it
into the two abilities it is, the same way "attacks or blocks" and "enters or
attacks" were already split.

Card text verified with `resolve_cards`. CR numbers looked up with
`knowledge_search(type="rules")` in the session that wrote this file:

- **CR 603.1b** - "A triggered ability may have more than one trigger
  condition."
- **CR 603.6a** - enters-the-battlefield abilities "trigger when a permanent
  enters the battlefield".
- **CR 603.6c** - "Leaves-the-battlefield abilities trigger when a permanent
  moves from the battlefield to another zone."
- **CR 701.21a** - "To sacrifice a permanent, its controller moves it from the
  battlefield directly to its owner's graveyard" - one of those moves.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.triggers import triggered_abilities_of
from magic_cards_model.models.zone import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def cam_board(*extra: str) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Sewer-veillance Cam"],
            library=["Grizzly Bears", "Grizzly Bears"],
            battlefield=[
                "Island",
                "Island",
                "Island",
                "Island",
                "Island",
                "Grizzly Bears",
                *extra,
            ],
        )
        .player("bob")
    )


def test_the_one_printed_line_is_two_triggered_abilities():
    """CR 603.1b, read off the card: one paragraph, two trigger conditions, and
    so two abilities for `triggers_for` to match one at a time."""
    abilities = triggered_abilities_of(card("Sewer-veillance Cam"))

    assert [ability.event for ability in abilities] == [
        TriggerEvent.ENTERS_THE_BATTLEFIELD,
        TriggerEvent.LEAVES_THE_BATTLEFIELD,
    ]
    assert all("tap or untap target creature" in ability.effect for ability in abilities)


def test_the_cam_triggers_when_it_enters():
    """CR 603.6a's half, which already worked - kept as the regression guard
    that splitting the line did not cost the entering trigger."""
    scenario = cam_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island", username="alice")[:1]

    scenario.cast_and_resolve("Sewer-veillance Cam", island)

    assert scenario.stack_names() == ["Sewer-veillance Cam's triggered ability"]


def test_the_cam_triggers_when_it_leaves():
    """CR 603.6c's half, which used to be dropped on the floor.

    The Cam goes to the graveyard - CR 603.6c's "moves from the battlefield to
    another zone" - and the departure half of its own printed line fires.
    """
    scenario = cam_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    islands = scenario.untapped_sources("Island", username="alice")
    cam = scenario.cast_and_resolve("Sewer-veillance Cam", islands[0])
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    scenario.game.put_into_graveyard(cam)

    assert cam.zone is Zone.GRAVEYARD
    assert [trigger.source_name for trigger in scenario.pending_triggers] == ["Sewer-veillance Cam"]


def test_the_cam_triggers_when_it_is_sacrificed_to_its_own_ability():
    """The line as the deck plays it (CR 701.21a's sacrifice, which is a
    battlefield-to-graveyard move and therefore CR 603.6c's event too)."""
    scenario = cam_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    islands = scenario.untapped_sources("Island", username="alice")
    cam = scenario.cast_and_resolve("Sewer-veillance Cam", islands[0])
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()
    untapped = scenario.untapped_sources("Island", "Island", "Island", "Island", username="alice")

    scenario.activate(cam, *untapped)

    assert cam.zone is Zone.GRAVEYARD
    # The sacrifice is paid as part of activating the ability (CR 701.21a's
    # move off the battlefield), so the departure happens before the draw
    # ability is on the stack at all; the trigger it caused goes on the stack
    # alongside it (CR 603.3).
    assert "Sewer-veillance Cam's triggered ability" in scenario.stack_names()


def test_another_permanent_leaving_does_not_trigger_the_cam():
    """The negative. The condition is self-referential ("**this** artifact"),
    so the Bears dying next to it is a CR 603.6c event the Cam does not watch -
    widening the matcher must not turn one card's departure into everyone's.
    """
    scenario = cam_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    islands = scenario.untapped_sources("Island", username="alice")
    scenario.cast_and_resolve("Sewer-veillance Cam", islands[0])
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    scenario.game.put_into_graveyard(scenario.creature("Grizzly Bears", "alice"))

    assert scenario.pending_triggers == []
