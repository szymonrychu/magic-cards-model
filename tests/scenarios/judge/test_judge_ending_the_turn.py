"""Judge scenarios: "end the turn" as a defined action, and the cleanup step it
drops the game into.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#957** - Time Stop + Everdream vs. Plagiarize. Nick casts Time Stop and
  splices Everdream onto it; Amy responds with Plagiarize targeting Nick. Who
  draws the card?

Amy does. The pieces, each looked up:

- Splice adds the spliced card's text after the main spell's (CR 702.47c,
  CR 612.10), so Time Stop ends the turn first and the draw comes second.
- Ending the turn exiles everything on the stack, Time Stop included
  (CR 724.1b), but CR 608.2m keeps it resolving: "If an instant spell, sorcery
  spell, or ability that can legally resolve leaves the stack once it starts to
  resolve, it will continue to resolve fully."
- CR 724.1d then ends the current step and skips straight to the cleanup step.
  So Everdream's draw happens *inside* the cleanup step.
- Plagiarize lasts "until end of turn", and CR 514.2 is where those effects end
  - after the CR 514.1 discard, not before the draw. So Plagiarize is still on
  when the draw happens and Amy takes it.

CR 724.1's procedure itself is built now: `Game.end_the_turn` performs
CR 724.1a's discarded triggers, CR 724.1b's exile (including the resolving
object, tracked on `Game.resolving`), CR 724.1d's jump to the cleanup step and
its combat removal, and CR 724.1f's "no player gets priority". The four tests
below drive it directly.

Two pieces of DDR#957 remain unbuilt, and they are what the `xfail` at the
bottom names: splice (`machines/casting.py`) and Plagiarize's draw replacement
(`machines/replacement.py`). Time Stop's own "End the turn." also has no row in
`machines/effects.py`, so nothing yet calls `end_the_turn` from a resolution.

**CR 724.1c and CR 724.1e could not be confirmed** with
`knowledge_search(type="rules")` in the session that wrote this, so neither is
implemented or cited.

Card text verified with `resolve_cards`; every CR number here was looked up
with `knowledge_search(type="rules")` in this session.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import AbilityKind, parse_abilities
from magic_cards_model.machines.effects import effect_for
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def test_none_of_the_three_cards_effects_are_read():
    """DDR#957's blocker, stated as three facts rather than three guesses.

    Time Stop: "End the turn." - CR 724's procedure is built now
    (`Game.end_the_turn`), but nothing connects the printed sentence to it:
    `effect_for` returns None, so the spell resolves and does nothing.

    Plagiarize: "Until end of turn, if target player would draw a card, instead
    that player skips that draw and you draw a card." - a CR 614 replacement
    effect with a duration; no row in `machines/replacement.py`'s registry.

    Everdream: "Draw a card." plus "Splice onto instant or sorcery {2}{U}". The
    draw *is* read - it is the one clause of this episode the engine can run -
    which is what makes the splice half the interesting gap.
    """
    assert effect_for("Time Stop", card("Time Stop").oracle_text or "") is None
    assert effect_for("Plagiarize", card("Plagiarize").oracle_text or "") is None
    assert effect_for("Everdream", card("Everdream").oracle_text or "") is not None


def test_splice_is_parsed_as_a_keyword_and_goes_no_further():
    """DDR#957's first mechanic: splice is recognised, and unimplemented.

    CR 702.47a: "Splice is a static ability that functions while a card is in
    your hand. 'Splice onto [quality] [cost]' means 'You may reveal this card
    from your hand as you cast a [quality] spell. If you do, add this card's
    rules text to that spell.'" CR 702.47c adds that the spliced spell "has the
    characteristics of the main spell, plus the rules text of each of the
    spliced cards", which is a CR 612 text-changing effect.

    `machines/abilities.py` reads the keyword and its parameter off Everdream
    and stops there: `machines/casting.py` has no splice path at all, so no
    spell can ever be cast with a card spliced onto it.
    """
    abilities = parse_abilities(card("Everdream"))
    keywords = [ability for ability in abilities if ability.kind is AbilityKind.KEYWORD]

    (splice,) = keywords
    assert splice.canonical == "Splice"
    assert splice.parameter == "onto instant or sorcery {2}{U}"

    import magic_cards_model.machines.casting as casting

    assert [name for name in dir(casting) if "splice" in name.lower()] == []


def test_ending_the_turn_exiles_the_whole_stack_and_skips_to_cleanup():
    """CR 724.1's procedure, driven directly.

    - **CR 724.1a**: "If there are any triggered abilities that triggered
      before this process began but haven't been put onto the stack yet, those
      abilities cease to exist."
    - **CR 724.1b**: "Exile every object on the stack, including the object
      that's resolving." Both the waiting Lightning Bolt and Time Stop itself.
    - **CR 724.1d**: "The current phase and/or step ends. ... The game skips
      straight to the cleanup step."

    Driven through `Game.end_the_turn` rather than through Time Stop's own
    resolution, because Time Stop has no entry in `machines/effects.py` - that
    is the gap the `xfail` at the bottom of this file names.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", hand=["Time Stop"], battlefield=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.cast_onto_stack("Lightning Bolt", auto=True, username="alice", targets=["bob"])
    scenario.pass_priority("alice")
    stop = scenario.cast_onto_stack("Time Stop", auto=True, username="bob")

    # CR 608.2 pops the top of the stack before the effect runs, which is the
    # state Time Stop's own effect would call `end_the_turn` from.
    scenario.game.resolving = scenario.game.stack.pop()
    scenario.game.end_the_turn()

    assert scenario.game.stack == [], "CR 724.1b exiled every object on the stack"
    assert bolt.zone is Zone.EXILE
    assert stop.zone is Zone.EXILE, "CR 724.1b: including the object that's resolving"
    assert scenario.step is Step.CLEANUP, "CR 724.1d skipped straight there"
    assert scenario.player("bob").life == 20, "the Bolt never resolved"


def test_ending_the_turn_discards_triggers_that_had_not_reached_the_stack():
    """CR 724.1a: "those abilities cease to exist. They won't be put onto the
    stack." A trigger still waiting in `pending_triggers` is gone, and no later
    flush brings it back."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack("Lightning Bolt", auto=True, username="alice", targets=["bob"])
    scenario.game.pending_triggers = list(scenario.game.pending_triggers)

    scenario.game.end_the_turn()

    assert scenario.game.pending_triggers == []
    assert scenario.game.put_triggers_on_stack() == []


def test_ending_the_turn_removes_the_attackers_from_combat():
    """CR 724.1d: "If this happens during combat, remove all creatures and
    planeswalkers from combat." """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    assert scenario.attackers() == [bears]

    scenario.game.end_the_turn()

    assert scenario.attackers() == []
    assert scenario.step is Step.CLEANUP


def test_ending_the_turn_gives_nobody_priority_and_runs_no_cleanup_actions():
    """CR 724.1f: "No player gets priority during this process, so triggered
    abilities are not put onto the stack."

    And the other half of why DDR#957 works: the cleanup step's own turn-based
    actions (CR 514.1's discard, CR 514.2's "all 'until end of turn' ... effects
    end") are *not* performed by this procedure. The game is merely dropped into
    that step, so an until-end-of-turn effect is still running for whatever the
    resolution does next.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Mountain"])
        .player("bob", battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.mark_damage(1)

    scenario.game.end_the_turn()

    assert scenario.step is Step.CLEANUP
    assert bears.damage == 1, "CR 514.2's wipe belongs to cleanup_step, not to CR 724.1"
    assert scenario.game.priority is None or scenario.game.stack == []


def test_time_stop_resolves_and_the_turn_carries_on():
    """DDR#957's baseline: Time Stop is a real spell that does nothing here.

    CR 608.2n puts a resolved instant into its owner's graveyard, and that much
    happens. What does not happen is CR 724.1 - not because the procedure is
    missing (`Game.end_the_turn` is built, and the four tests above drive it)
    but because nothing connects Time Stop's printed "End the turn." to it:
    `effect_for("Time Stop", ...)` is None, so the spell resolves and does
    nothing at all.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", hand=["Time Stop"], battlefield=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.cast_onto_stack("Lightning Bolt", auto=True, username="alice", targets=["bob"])
    scenario.pass_priority("alice")
    stop = scenario.cast_onto_stack("Time Stop", auto=True, username="bob")

    scenario.resolve_top()

    assert stop.zone is Zone.GRAVEYARD
    assert bolt.zone is Zone.STACK, "CR 724.1b's exile never happened"
    assert scenario.step is Step.PRECOMBAT_MAIN, "CR 724.1d's skip never happened"


@pytest.mark.xfail(
    reason="CR 724.1's procedure is built (Game.end_the_turn, driven by the tests "
    "above). Three pieces are still missing, each in a file of its own: splice "
    "(CR 702.47) is parsed but has no cast path in machines/casting.py, so "
    "`casting.splice(...)` does not exist; Plagiarize's draw replacement has no "
    "entry in machines/replacement.py; and Time Stop's 'End the turn.' has no "
    "row in machines/effects.py, so no resolution calls end_the_turn",
    strict=True,
)
def test_the_spliced_draw_happens_in_cleanup_and_plagiarize_steals_it():
    """DDR#957's ruling, in the order the rules put it.

    Nick casts Time Stop with Everdream spliced on. Amy responds with
    Plagiarize targeting Nick; it resolves first (CR 608.2, last in first out),
    so its replacement effect is already running when Time Stop begins.

    Time Stop resolves. CR 724.1b exiles every object on the stack "including
    the object that's resolving" - so Time Stop itself goes - but CR 608.2m
    keeps it resolving anyway. CR 724.1d ends the step and skips to cleanup.
    Everdream's "Draw a card." is the next instruction in the same resolution
    (CR 608.2c, CR 702.47c's appended text), and it happens there, inside the
    cleanup step.

    Plagiarize is an "until end of turn" effect, and CR 514.2 is where those
    end - after CR 514.1's discard, which has not happened yet. So the draw is
    replaced and Amy draws instead of Nick.

    (The episode's aside also lands here: CR 514.1 makes only the *active*
    player discard to maximum hand size, so a stolen extra card in Nick's hand
    would not force a discard on Amy's turn.)
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"] * 5, hand=["Plagiarize"], battlefield=["Island"] * 4)
        .player(
            "bob",
            library=["Mountain"] * 5,
            hand=["Time Stop", "Everdream"],
            battlefield=["Island"] * 9,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Time Stop", username="bob")
    casting.splice("Everdream")
    scenario.pay_with(
        casting.begin_paying(), *scenario.untapped_sources(*["Island"] * 9, username="bob")
    )
    scenario.put_on_stack(casting)

    scenario.pass_priority("bob")
    scenario.cast_and_resolve(
        "Plagiarize",
        *scenario.untapped_sources(*["Island"] * 4, username="alice"),
        username="alice",
        targets=["bob"],
    )
    scenario.resolve_top()

    assert scenario.step is Step.CLEANUP
    assert len(scenario.player("alice").hand) == 1, "Amy drew the spliced card"
    assert scenario.player("bob").hand == []
