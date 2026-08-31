"""Scenario: intervening *if* clauses that count something.

CR 603.4: "A triggered ability may read 'When/Whenever/At [trigger event], if
[condition], [effect].' When the trigger event occurs, the ability checks
whether the stated condition is true. The ability triggers only if it's true";
CR 608.2a checks the same clause again on resolution.
`machines/triggers.intervening_if_holds` reads a fixed set of clause shapes and
fails closed on the rest, recording an `InterveningIfNotice`. Two counting
shapes are added here:

- **Vengevine** - "if it's the second creature spell you cast this turn". The
  ordinal twin of Alania's "the first instant spell ... you've cast this turn",
  which was the only ordinal read; every other one failed closed, so Vengevine
  never triggered even on the turn its own condition was plainly true.
- **Phoenix Fleet Airship** - "if you sacrificed a permanent this turn". Read
  now, but unanswerable: nothing records CR 701.21a's sacrifices per turn, so
  it still fails closed with its notice, and the strict `xfail` names the file
  that would have to record them.

Card text verified with `resolve_cards`. CR numbers looked up with
`knowledge_search(type="rules")` in the session that wrote this file:
CR 603.4, CR 608.2a, CR 701.21a ("To sacrifice a permanent, its controller
moves it from the battlefield directly to its owner's graveyard"), CR 601.2c.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import Scenario


def vengevine_board() -> Scenario:
    """Vengevine in the graveyard, two Grizzly Bears to cast, mana for both.

    CR 113.6m is why the ability is asked at all from a graveyard: its effect
    names the zone it moves the card out of, which `zones_ability_functions_in`
    already reads.
    """
    return (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears", "Grizzly Bears", "Lightning Bolt"],
            graveyard=["Vengevine"],
            battlefield=["Forest", "Forest", "Forest", "Forest", "Mountain"],
        )
        .player("bob")
    )


def test_the_first_creature_spell_does_not_trigger_vengevine():
    """CR 603.4's check, false: one creature spell cast this turn is not the
    second one, so the ability does not trigger at all."""
    scenario = vengevine_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest", username="alice")

    scenario.cast_onto_stack("Grizzly Bears", *forests, username="alice")

    assert scenario.stack_names() == ["Grizzly Bears"]


def test_the_second_creature_spell_triggers_vengevine():
    """CR 603.4's check, true: the second creature spell cast this turn is
    exactly what the clause names, so Vengevine's ability triggers and goes on
    the stack next to the spell that caused it."""
    scenario = vengevine_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", username="alice")

    scenario.cast_and_resolve("Grizzly Bears", *forests[:2], username="alice")
    scenario.cast_onto_stack("Grizzly Bears", *forests[2:], username="alice")

    assert "Vengevine's triggered ability" in scenario.stack_names()
    assert scenario.game.intervening_if_notices == []


def test_a_noncreature_second_spell_does_not_trigger_vengevine():
    """The negative. A Lightning Bolt cast second is the second *spell* but not
    the second *creature* spell, and the clause counts creature spells."""
    scenario = vengevine_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest", username="alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Grizzly Bears", *forests, username="alice")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])

    assert "Vengevine's triggered ability" not in scenario.stack_names()


def airship_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Phoenix Fleet Airship", "Skirk Prospector", "Raging Goblin"],
        )
        .player("bob")
    )


def test_the_airship_still_fails_closed_when_nothing_was_sacrificed():
    """The clause is read but unanswerable, and CR 603.4 only lets an ability
    trigger if the condition is *true*: on a turn with no sacrifice the answer
    is no either way, and the refusal is recorded as an `InterveningIfNotice`
    rather than passing silently for a legal reason."""
    scenario = airship_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    while scenario.step is not Step.END_STEP:
        scenario.advance()

    assert scenario.stack_names() == []
    assert [notice.source_name for notice in scenario.game.intervening_if_notices] == [
        "Phoenix Fleet Airship"
    ]


@pytest.mark.xfail(
    strict=True,
    reason="`machines/triggers._sacrificed_this_turn_holds` reads the clause now, but there is "
    "nothing to read it *from*: no per-turn record of CR 701.21a's sacrifices exists. "
    "`Game.sacrifice` in models/game.py - Task 1.5's file - is where one belongs "
    "(`Game.permanents_left_battlefield_this_turn` cannot stand in: a bounced or destroyed "
    "permanent left the battlefield without being sacrificed).",
)
def test_the_airship_triggers_once_a_permanent_really_was_sacrificed():
    """CR 603.4 on a turn where the condition is genuinely true: alice fed a
    Goblin to Skirk Prospector in her main phase, so "you sacrificed a
    permanent this turn" holds when the end step begins."""
    scenario = airship_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goblin = scenario.creature("Raging Goblin", "alice")

    scenario.activate(scenario.creature("Skirk Prospector", "alice"), sacrificing=[goblin])
    assert goblin.zone is Zone.GRAVEYARD

    while scenario.step is not Step.END_STEP:
        scenario.advance()

    assert scenario.stack_names() == ["Phoenix Fleet Airship's triggered ability"]
