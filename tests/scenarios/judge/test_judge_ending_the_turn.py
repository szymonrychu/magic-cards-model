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

None of this is modelled: `Game` has no "end the turn" action at all, splice is
not implemented, and Plagiarize's draw-replacement is unread.

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

    Time Stop: "End the turn." - CR 724's whole procedure, which `Game`
    implements nowhere (there is no `end_the_turn`; `Game.cleanup_step` only
    performs CR 514.2's wipe).

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


def test_time_stop_resolves_and_the_turn_carries_on():
    """DDR#957's baseline: Time Stop is a real spell that does nothing here.

    CR 608.2n puts a resolved instant into its owner's graveyard, and that much
    happens. What does not happen is any part of CR 724.1 - the stack is not
    exiled, the phase does not end, and the game does not skip to cleanup.

    Recorded so that the day something implements "end the turn" this test
    fails loudly rather than the `xfail` below quietly starting to pass for
    half the right reasons.
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
    reason="three separate gaps: CR 724's 'end the turn' action does not exist "
    "in Game, splice (CR 702.47) is parsed but never castable, and "
    "Plagiarize's draw replacement has no entry in machines/replacement.py",
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
