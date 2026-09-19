"""Denzilore Fatehold's and Matoya, Archon Elder's own "Whenever you scry or
surveil, ..." (CR 701.22a's scry, CR 701.25a's surveil).

`TriggerEvent` carried nothing that watched either action - CR 701.22d/
701.25's own trigger had no event to emit at all (see `Game.scry`'s own
docstring before this change). `Game.scry`/`Game.surveil` now emit
`TriggerEvent.SCRY_OR_SURVEIL` once per action, and only when `count > 0` -
CR 701.22b/701.25c both say a scry or surveil for 0 "is not a ... event".
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def test_matoya_draws_a_card_when_her_controller_scries():
    """Off-pool generality proof: Matoya, Archon Elder prints "Whenever you
    scry or surveil, draw a card" - a differently shaped effect (a plain
    draw, not a counter-put) than Denzilore Fatehold's, and not the reported
    card."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Matoya, Archon Elder"], library=["Mountain", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.scry_keeping_everything_on_top(username="alice")

    scenario.game.scry("alice", 2, source="Matoya, Archon Elder")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Matoya, Archon Elder's triggered ability"]
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == 1


def test_denzilore_fatehold_puts_a_counter_on_each_creature_when_surveilling():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Denzilore Fatehold", "Grizzly Bears"],
            library=["Mountain", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.surveil_keeping_everything_on_top(username="alice")

    scenario.game.surveil("alice", 1, source="Denzilore Fatehold")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Denzilore Fatehold's triggered ability"]
    scenario.pass_until_resolved()
    assert bears.counter_count("+1/+1") == 1


def test_scrying_zero_raises_no_event_at_all():
    """CR 701.22b: "If a player is instructed to scry 0, no scry event
    occurs." """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Matoya, Archon Elder"], library=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.scry("alice", 0, source="Matoya, Archon Elder")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_an_opponents_scry_does_not_trigger_a_controllers_own_ability():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Matoya, Archon Elder"], library=["Mountain"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.scry_keeping_everything_on_top(username="bob")

    scenario.game.scry("bob", 1, source=None)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
