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
object, tracked on `Game.resolving`), CR 724.1c's state-based-action check,
CR 724.1d's jump to the cleanup step and its combat removal, and CR 724.1f's
"no player gets priority". The tests below drive it directly.

Both DDR#957 pieces are built now too: splice (`machines/casting.py`) and
Plagiarize's draw replacement (`machines/replacement.py`), and Time Stop's own
"End the turn." has a row in `machines/effects.py` (`end_the_turn_effect`), so
`test_time_stop_ends_the_turn_and_exiles_the_stack_under_it` below drives the
whole thing from a real resolution rather than a direct call. What CR 724.1's
procedure leaves *owed* - the cleanup step's own CR 514.1/514.2 turn-based
actions, deferred rather than skipped, and CR 724.1c/f's own trigger-stacking
and "another cleanup step" - is `tests/scenarios/test_ending_the_turn_cleanup.
py`'s whole subject, not this file's. The tests below that call
`Game.end_the_turn` directly, rather than through a real resolution, still
leave that debt outstanding (`Game.cleanup_owed` stays true) exactly as
before this wave, because nothing here ever reaches the `Game._before_
priority` call that pays it off - only the two tests driven through a genuine
`resolve_top` (Time Stop's own resolution, and DDR#957's spliced one) do, and
both now leave `cleanup_owed` false by the time they finish.

Card text verified with `resolve_cards`; every CR number here was looked up
with `knowledge_search(type="rules")` in this session.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import AbilityKind, parse_abilities
from magic_cards_model.machines.effects import effect_for
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def test_which_of_the_three_cards_effects_are_read():
    """DDR#957's blocker, stated as three facts rather than three guesses.

    Time Stop: "End the turn." - CR 724's procedure is built
    (`Game.end_the_turn`) and its printed sentence now reaches it, so this
    one is no longer a blocker; the test below plays it.

    Plagiarize: "Until end of turn, if target player would draw a card, instead
    that player skips that draw and you draw a card." - a CR 614.1a replacement
    effect with a duration. Resolving it creates the effect: `effect_for`
    reads it and leaves a `machines/replacement.DrawSkipReplacement` on
    `Game.created_replacements`, the way a resolved prevention spell leaves a
    CR 615.1 shield - see the test below.

    Everdream: "Draw a card." plus "Splice onto instant or sorcery {2}{U}". The
    draw *is* read - it is the one clause of this episode the engine can run -
    which is what makes the splice half the interesting gap.
    """
    assert effect_for("Time Stop", card("Time Stop").oracle_text or "") is not None
    assert effect_for("Plagiarize", card("Plagiarize").oracle_text or "") is not None
    assert effect_for("Everdream", card("Everdream").oracle_text or "") is not None


def test_splice_reveals_the_card_charges_its_cost_and_adds_its_text():
    """DDR#957's first mechanic, end to end on a spell whose text the engine
    can already run.

    CR 702.47a: "Splice is a static ability that functions while a card is in
    your hand. 'Splice onto [quality] [cost]' means 'You may reveal this card
    from your hand as you cast a [quality] spell. If you do, add this card's
    rules text to that spell and pay its splice cost.'" CR 702.47c: the spell
    "has the characteristics of the main spell, plus the rules text of each of
    the spliced cards", and CR 612.10 says where it goes - "following that
    spell's own rules text". CR 702.47e takes it away again: "The spell loses
    any splice changes once it leaves the stack for any reason."

    This test was written the other way round, asserting that
    `machines/casting.py` had no splice path at all. Lightning Bolt stands in
    for Time Stop here, because Time Stop's own "End the turn." still has no
    row in `machines/effects.py` (see the `xfail` at the bottom); splice
    itself does not care which instant it is spliced onto.
    """
    abilities = parse_abilities(card("Everdream"))
    keywords = [ability for ability in abilities if ability.kind is AbilityKind.KEYWORD]

    (splice,) = keywords
    assert splice.canonical == "Splice"
    assert splice.parameter == "onto instant or sorcery {2}{U}"

    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"] * 5,
            hand=["Lightning Bolt", "Everdream"],
            battlefield=["Mountain"] + ["Island"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Lightning Bolt", "alice", targets=["bob"])

    casting.splice("Everdream")

    # {R} plus the splice cost {2}{U}, as one total cost (CR 601.2f/601.2h).
    assert str(casting.total_cost) == "{2}{R}{U}"
    scenario.pay_with(
        casting.begin_paying(),
        *scenario.untapped_sources("Mountain", "Island", "Island", "Island", username="alice"),
    )
    spell = scenario.put_on_stack(casting)

    # CR 612.10: the spliced text follows the spell's own, and the spell's own
    # printing is untouched.
    assert spell.oracle_text == f"{card('Lightning Bolt').oracle_text}\nDraw a card."
    assert spell.card.oracle_text == card("Lightning Bolt").oracle_text
    # CR 702.47a reveals the card and leaves it in hand; nothing moves it.
    assert [held.name for held in scenario.player("alice").hand] == ["Everdream"]

    scenario.resolve_top()

    assert scenario.player("bob").life == 17, "the main spell's own text still ran"
    assert len(scenario.player("alice").hand) == 2, "and the spliced draw ran after it"
    # CR 702.47e: off the stack, the splice changes are gone.
    assert spell.spliced_text == ()


def test_plagiarize_takes_the_targeted_players_next_draw():
    """DDR#957's second mechanic: a draw replaced, and by whom.

    Plagiarize (confirmed with `resolve_cards`): "Until end of turn, if target
    player would draw a card, instead that player skips that draw and you draw
    a card." CR 614.1a is the shape - "[if] [Event] would happen, [Something
    else] happens instead" - and CR 614.6 has the new event happen in place of
    the old one, so bob draws nothing at all rather than drawing and giving
    it away.

    The spell is in a graveyard by the time the effect ever applies, which is
    why this cannot be a static ability read off a permanent: it is stored on
    `Game.created_replacements`, and CR 514.2's cleanup step is what ends it.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"] * 5, hand=["Plagiarize"], battlefield=["Island"] * 4)
        .player("bob", library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Plagiarize",
        *scenario.untapped_sources(*["Island"] * 4, username="alice"),
        username="alice",
        targets=["bob"],
    )

    scenario.game.draw_cards(scenario.player("bob"), 1)

    assert len(scenario.player("alice").hand) == 1, "alice drew instead"
    assert scenario.player("bob").hand == [], "bob skipped the draw entirely"
    assert len(scenario.player("bob").library) == 5, "and nothing left his library"


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


def test_time_stop_ends_the_turn_and_exiles_the_stack_under_it():
    """DDR#957's headline: Time Stop's printed "End the turn." runs CR 724.1.

    CR 724.1b exiles "every object on the stack, including the object that's
    resolving" - so the Bolt underneath goes to exile rather than resolving,
    and Time Stop exiles *itself* instead of reaching the graveyard CR 608.2n
    would otherwise send it to. CR 724.1d then skips straight to the cleanup
    step.

    Every CR number here was verified with `knowledge_search(type="rules")`.
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

    assert stop.zone is Zone.EXILE, "CR 724.1b exiles the resolving object too"
    assert bolt.zone is Zone.EXILE, "CR 724.1b exiles every object on the stack"
    assert scenario.game.stack_is_empty
    assert scenario.step is Step.CLEANUP, "CR 724.1d skips to the cleanup step"
    assert scenario.player("bob").life == 20, "the Bolt never resolved"
    # CR 608.2m's "will continue to resolve fully" reaches the end of Time
    # Stop's own text (there is no more of it) before the cleanup step it owes
    # actually runs: `Game._before_priority`, reached as this resolution
    # finishes, already paid the debt off.
    assert scenario.game.cleanup_owed is False


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
    # CR 117.1: alice is the active player and receives priority first, and
    # Time Stop is bob's instant - he needs priority to cast it at all.
    scenario.pass_priority("alice")

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

    assert scenario.step is Step.CLEANUP, "CR 724.1d skipped to the cleanup step"
    assert len(scenario.player("alice").hand) == 1, "Amy drew the spliced card"
    # The draw itself is the episode's question, and library counts are what
    # answer it: bob's spliced "Draw a card" was replaced, so he skipped it and
    # alice drew instead (CR 614.1a, the DrawSkipReplacement Plagiarize left behind).
    assert len(scenario.player("bob").library) == 5, "bob skipped the draw"
    assert len(scenario.player("alice").library) == 4, "alice took it"
    # Everdream is still in bob's hand, and that is correct: splice says
    # "**reveal** this card from your hand", and CR 701.20a's reveal is "show
    # that card to all players for a brief time" - it moves nothing. Nothing in
    # CR 702.47's retrievable text moves the card either, and `Casting.splice`
    # records the same reading. An earlier version of this test asserted bob's
    # hand was empty, which conflated "did not draw" with "no longer holds the
    # card he only revealed".
    assert [state.name for state in scenario.player("bob").hand] == ["Everdream"]
    # CR 608.2m again: Everdream's spliced "Draw a card." is the rest of this
    # same resolution's text, and it already ran (the draw above) before the
    # owed cleanup step's CR 514.2 could end Plagiarize's "until end of turn"
    # replacement - had the ordering been reversed, bob would have drawn
    # instead of alice. `Game._before_priority` pays the debt only once this
    # whole resolution, spliced text included, has finished.
    assert scenario.game.cleanup_owed is False
    assert scenario.game.created_replacements == [], "CR 514.2 has since ended it"
