"""Scenario: "when you draw your third card in a turn".

Tamiyo, Inquisitive Student flips on her own third draw of a turn. The
condition parsed with `event=None` - `machines/abilities._trigger_event` has no
member for it - so `triggered_abilities_of` dropped the ability entirely and it
could not even be asked. `machines/triggers.py` now reads it and matches it
against CR 121.2's individual card draws, which the engine already emits one at
a time.

What is missing is the **count**: `Game.draw_cards` (`models/game.py`, Task
1.5's file) emits one `DRAWS_A_CARD` event per card and keeps no running
per-turn total for any player, so "your third" cannot be answered. An unknown
answer does not trigger (the same fail-closed direction CR 603.4 takes for an
unreadable intervening *if*), which is what the strict `xfail` below measures.

Card text verified with `resolve_cards`. CR numbers looked up with
`knowledge_search(type="rules")` in the session that wrote this file:

- **CR 121.2** - "Cards may only be drawn one at a time. If a player is
  instructed to draw multiple cards, that player performs that many individual
  card draws."
- **CR 121.2c** - the active player performs all of their draws first, which is
  why a per-turn count is per player rather than global.
- **CR 603.2g** - an ability triggers only if its trigger event actually
  occurs.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.triggers import triggered_abilities_of
from tests.cards import card
from tests.scenarios.harness import Scenario


def tamiyo_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Grizzly Bears", "Grizzly Bears", "Grizzly Bears", "Grizzly Bears"],
            battlefield=["Tamiyo, Inquisitive Student", "Island"],
        )
        .player("bob", library=["Island", "Island", "Island", "Island"])
    )


def test_tamiyos_draw_trigger_survives_the_parse():
    """The ability is kept now rather than dropped: `triggered_abilities_of`
    holds both of Tamiyo's front-face triggers, the attack one the parser could
    read and the draw one it could not."""
    tamiyo = card("Tamiyo, Inquisitive Student")
    conditions = [ability.condition for ability in triggered_abilities_of(tamiyo)]

    assert "you draw your third card in a turn" in conditions


def test_a_single_draw_does_not_trigger_tamiyo():
    """The negative, and the one that matters most for a condition matched off
    text: one draw is CR 121.2's own event, and it is not the third."""
    scenario = tamiyo_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.draw(1, username="alice")

    assert scenario.pending_triggers == []


def test_an_opponents_draws_do_not_trigger_tamiyo():
    """The other negative: the condition says "**you** draw", so bob drawing
    three cards is three CR 121.2 events that are none of Tamiyo's."""
    scenario = tamiyo_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.draw(3, username="bob")

    assert scenario.pending_triggers == []


@pytest.mark.xfail(
    strict=True,
    reason="the matcher reads 'you draw your third card in a turn' and is handed every "
    "CR 121.2 draw event, but nothing counts them: `Game.draw_cards` in models/game.py - Task "
    "1.5's file - keeps no per-turn, per-player draw total, so the ordinal cannot be answered "
    "and the ability fails closed.",
)
def test_the_third_draw_of_a_turn_triggers_tamiyo():
    """CR 121.2's third individual draw of alice's turn is the event, and
    Tamiyo's ability triggers on it."""
    scenario = tamiyo_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.draw(3, username="alice")

    assert [trigger.source_name for trigger in scenario.pending_triggers] == [
        "Tamiyo, Inquisitive Student // Tamiyo, Seasoned Scholar"
    ]
