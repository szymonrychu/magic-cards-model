"""Scenario: "when you draw your third card in a turn".

Tamiyo, Inquisitive Student flips on her own third draw of a turn. The
condition parsed with `event=None` - `machines/abilities._trigger_event` has no
member for it - so `triggered_abilities_of` dropped the ability entirely and it
could not even be asked. `machines/triggers.py` now reads it and matches it
against CR 121.2's individual card draws, which the engine already emits one at
a time.

`Game.draw_cards` (`models/game.py`) now keeps the count as well as emitting
the events: `Game.cards_drawn_this_turn` is incremented once per card that was
really drawn, inside the same loop and immediately *before* the event is
dispatched, because the matcher reads the running total while the event is
being matched.

Every draw here goes through `Game.draw_cards` rather than the harness's
`scenario.draw`, which calls `Player.draw` directly and raises no CR 121.2
event at all - so a test written against it would assert silence for the wrong
reason.

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

from magic_cards_model.machines import Step
from magic_cards_model.machines.triggers import triggered_abilities_of
from magic_cards_model.models import Zone
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

    scenario.game.draw_cards("alice", 1)

    assert scenario.pending_triggers == []


def test_an_opponents_draws_do_not_trigger_tamiyo():
    """The other negative: the condition says "**you** draw", so bob drawing
    three cards is three CR 121.2 events that are none of Tamiyo's."""
    scenario = tamiyo_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.draw_cards("bob", 3)

    assert scenario.pending_triggers == []


def test_the_third_draw_of_a_turn_triggers_tamiyo():
    """CR 121.2's third individual draw of alice's turn is the event, and
    Tamiyo's ability triggers on it."""
    scenario = tamiyo_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.draw_cards("alice", 3)

    assert [trigger.source_name for trigger in scenario.pending_triggers] == [
        "Tamiyo, Inquisitive Student"
    ]


# -- "each turn": the same ordinal, the other printed suffix -----------------
#
# Faerie Vandal (verified off its Scryfall printing): "Whenever you draw your
# second card each turn, put a +1/+1 counter on this creature." Tamiyo prints
# "in a turn"; the 34 other Modern cards with this trigger print "each turn",
# and the matcher read only the first suffix, so their condition parsed with
# `event=None` and was dropped. Second, not third: a different ordinal than
# Tamiyo's, so the count is read off the card rather than off one printing.


def vandal_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Grizzly Bears", "Grizzly Bears", "Grizzly Bears", "Grizzly Bears"],
            battlefield=["Faerie Vandal", "Island"],
        )
        .player("bob", library=["Island", "Island", "Island", "Island"])
    )


def test_faerie_vandals_each_turn_trigger_survives_the_parse():
    vandal = card("Faerie Vandal")
    conditions = [ability.condition for ability in triggered_abilities_of(vandal)]

    assert "you draw your second card each turn" in conditions


def test_the_first_draw_of_a_turn_does_not_trigger_faerie_vandal():
    scenario = vandal_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.draw_cards("alice", 1)

    assert scenario.pending_triggers == []


def test_the_second_draw_of_a_turn_triggers_faerie_vandal_once():
    """CR 121.2: two cards are two draws, and only the second is the event -
    the third is not the second, so it triggers nothing further."""
    scenario = vandal_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.draw_cards("alice", 3)

    assert [trigger.source_name for trigger in scenario.pending_triggers] == ["Faerie Vandal"]


def test_an_opponents_second_draw_does_not_trigger_faerie_vandal():
    scenario = vandal_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.draw_cards("bob", 2)

    assert scenario.pending_triggers == []


def test_faerie_vandals_trigger_puts_a_counter_on_it():
    scenario = vandal_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vandal = scenario.find("Faerie Vandal", Zone.BATTLEFIELD, "alice")

    scenario.game.draw_cards("alice", 2)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert vandal.counter_count("+1/+1") == 1
