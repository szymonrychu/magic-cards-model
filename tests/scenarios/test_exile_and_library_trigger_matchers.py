"""Scenario: two more conditions the parser left with no trigger event.

Both are printed as "whenever one or more cards are put into [a zone]", and
both parsed with `event=None`, so `triggered_abilities_of` dropped them:

- **Ketramose, the New Dawn** - "Whenever one or more cards are put into exile
  from graveyards and/or the battlefield during your turn, you draw a card and
  lose 1 life." One printed condition naming two origins (CR 603.1b), and the
  battlefield origin is one the engine already emits - `Game.exile_permanent`
  raises it - so Ketramose fires for real here, no staging.
- **Wan Shi Tong, All-Knowing** - "Whenever one or more cards are put into a
  library from anywhere, create two 1/1 colorless Spirit creature tokens ...".
  Nothing anywhere raises a put-into-a-library event, so the matcher is proven
  against a staged event and the real path is the strict `xfail`.

Card text verified with `resolve_cards`. CR numbers looked up with
`knowledge_search(type="rules")` in the session that wrote this file:

- **CR 406.2** - "To exile an object is to put it into the exile zone from
  whatever zone it's currently in."
- **CR 401.1** - "When a game begins, each player's deck becomes their
  library" - the zone Wan Shi Tong watches as a destination.
- **CR 603.1b** - a triggered ability may have more than one trigger condition.
- **CR 603.2c** - "one or more cards" moved by one instruction is one event
  with a count, so one trigger.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.triggers import ExtraTriggerEvent, GameEvent
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import Scenario


def ketramose_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Island", "Island"],
            graveyard=["Brainstorm"],
            battlefield=["Ketramose, the New Dawn", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Hill Giant"])
    )


def test_a_permanent_exiled_during_your_turn_triggers_ketramose():
    """The battlefield origin, played for real: `Game.exile_permanent` moves
    alice's Bears to exile on alice's own turn (CR 406.2), and Ketramose's
    ability triggers.
    """
    scenario = ketramose_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.exile_permanent(bears)

    assert bears.zone is Zone.EXILE
    assert [trigger.source_name for trigger in scenario.pending_triggers] == [
        "Ketramose, the New Dawn"
    ]


def test_an_opponents_permanent_exiled_during_your_turn_triggers_it_too():
    """The condition names no controller - any card put into exile from the
    battlefield counts, as long as it happens during your turn."""
    scenario = ketramose_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.exile_permanent(scenario.creature("Hill Giant", "bob"))

    assert [trigger.source_name for trigger in scenario.pending_triggers] == [
        "Ketramose, the New Dawn"
    ]


def test_ketramose_does_not_trigger_during_someone_elses_turn():
    """The negative on "during your turn". The same exile on bob's turn is the
    same CR 406.2 event and is not Ketramose's trigger."""
    scenario = ketramose_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while scenario.game.turn.active_player != "bob":
        scenario.advance()
    scenario.pending_triggers.clear()

    scenario.game.exile_permanent(scenario.creature("Hill Giant", "bob"))

    assert scenario.pending_triggers == []


def test_a_card_exiled_from_a_graveyard_triggers_ketramose():
    """The other origin the same printed condition names. The event is staged,
    because no call site raises a graveyard-to-exile event yet; the matcher
    reads both origins off the one condition (CR 603.1b)."""
    scenario = ketramose_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    brainstorm = scenario.find("Brainstorm", Zone.GRAVEYARD, "alice")

    scenario.game.emit(
        GameEvent(
            event=ExtraTriggerEvent.EXILED_FROM_GRAVEYARD,
            subject_id=brainstorm.id,
            subject_name=brainstorm.name,
            subject_card=brainstorm.card,
            subject_types=brainstorm.types,
            player="alice",
            amount=1,
        )
    )

    assert [trigger.source_name for trigger in scenario.pending_triggers] == [
        "Ketramose, the New Dawn"
    ]


def wan_shi_tong_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Brainstorm"],
            library=["Grizzly Bears", "Grizzly Bears", "Grizzly Bears"],
            battlefield=["Island", "Wan Shi Tong, All-Knowing"],
        )
        .player("bob")
    )


def test_cards_put_into_a_library_trigger_wan_shi_tong():
    """CR 401.1's library as a destination, matched against the printed
    condition. One event, one trigger, however many cards moved
    (CR 603.2c)."""
    scenario = wan_shi_tong_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.emit(
        GameEvent(event=ExtraTriggerEvent.PUT_INTO_LIBRARY, player="alice", amount=2)
    )

    assert [trigger.source_name for trigger in scenario.pending_triggers] == [
        "Wan Shi Tong, All-Knowing"
    ]


def test_wan_shi_tong_does_not_fire_on_an_unrelated_zone_change():
    """The negative: a permanent going to a graveyard is not a card being put
    into a library, and the widened matcher must not confuse the two."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Grizzly Bears"],
            battlefield=["Wan Shi Tong, All-Knowing", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.put_into_graveyard(scenario.creature("Grizzly Bears", "alice"))

    assert scenario.pending_triggers == []


@pytest.mark.xfail(
    strict=True,
    reason="the matcher is here and works (the two tests above), but nothing emits a "
    "put-into-a-library event: Brainstorm's own 'put two cards from your hand on top of your "
    "library' moves them through models/game.py and machines/effects.py, neither of which "
    "raises one. models/game.py is Task 1.5's file.",
)
def test_a_brainstorm_puts_two_cards_into_the_library_and_triggers_wan_shi_tong():
    """DDR#999's Brainstorm ruling, played for real: two cards genuinely leave
    the hand for the library, so cards are *put into* a library and the ability
    triggers once (CR 603.2c)."""
    scenario = wan_shi_tong_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island", username="alice")

    scenario.cast_and_resolve("Brainstorm", island, username="alice")

    assert [trigger.source_name for trigger in scenario.pending_triggers] == [
        "Wan Shi Tong, All-Knowing"
    ]
