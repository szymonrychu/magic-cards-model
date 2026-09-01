"""Judge scenarios: "whenever one or more cards are put into a library".

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#999** - How Does Wan Shi Tong, All-Knowing Work?

Wan Shi Tong's real oracle text, confirmed with `resolve_cards`, ends: "Whenever
one or more cards are put into a library from anywhere, create two 1/1 colorless
Spirit creature tokens with 'This token can't block or be blocked by non-Spirit
creatures.'"

The episode's rulings all hang on reading that condition literally. *Put* is not
a keyworded action, so anything matching its plain English meaning counts; *into*
means the card has to start somewhere else, so scrying (CR 701.22a: "look at the
top N cards of your library, then put any number of them on the bottom ... and
the rest on top") never triggers it, because those cards were in the library the
whole time; and a Brainstorm does trigger it, once, because two cards genuinely
leave the hand for the library at the same time.

The condition is now matched by `ExtraTriggerEvent.PUT_INTO_LIBRARY`, which
`Game.put_cards_into_library` raises once per instruction with a count, and
Brainstorm's second sentence routes through it - so the episode's Brainstorm
ruling is playable here rather than asserted about the parser. The first test
below still records the half that has not moved: the *printed* condition is not
one of the shapes `TriggeredAbility.event` recognises, so the ability's own
`event` field stays None and the match is made elsewhere.
Every CR number here was looked up with `knowledge_search(type="rules")` in the
session that wrote the file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggeredAbility, parse_abilities
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def test_the_library_trigger_parses_with_no_trigger_event():
    """The gap, asserted rather than assumed.

    The ability is recognised as a triggered ability (CR 603.1: "Triggered
    abilities have a trigger condition and an effect"), but its condition is not
    one of the shapes `TriggerEvent` knows, so `event` is None and the printed
    condition is all that survives. Nothing emits such an event either.
    """
    abilities = parse_abilities(card("Wan Shi Tong, All-Knowing"))
    library_trigger = [
        ability
        for ability in abilities
        if isinstance(ability, TriggeredAbility) and "put into a library" in ability.text
    ]

    assert len(library_trigger) == 1
    assert library_trigger[0].event is None


def brainstorm_board() -> Scenario:
    """Alice with Brainstorm, three cards to draw, and Wan Shi Tong watching."""
    return (
        Scenario()
        .player(
            "alice",
            hand=["Brainstorm"],
            library=["Grizzly Bears", "Hill Giant", "Mountain"],
            battlefield=["Island", "Wan Shi Tong, All-Knowing"],
        )
        .player("bob")
    )


def test_a_brainstorm_puts_two_cards_into_the_library_and_triggers_once():
    """The episode's Brainstorm ruling.

    Brainstorm draws three, which really does move those cards out of the
    library (CR 121.1: "a player draws a card by putting the top card of their
    library into their hand"; CR 121.2 makes three draws of one, not one of
    three), and then puts two cards from hand back - so cards are *put into* a
    library, and CR 603.2c's "an ability triggers only once each time its trigger
    event occurs" makes that a single trigger even though two cards move, because
    they move as one event.

    The assertion is on the stack, not on `pending_triggers`: CR 603.3 drains
    the queue onto the stack "the next time a player would receive priority",
    which `resolve_top` reaches before returning.
    """
    scenario = brainstorm_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island", username="alice")

    scenario.cast_and_resolve("Brainstorm", island, username="alice")

    assert [item.source_name for item in scenario.game.stack] == ["Wan Shi Tong, All-Knowing"]


def test_the_two_cards_the_caster_names_are_the_ones_that_go_back():
    """CR 608.2d: "the player announces their choice" as the spell resolves.

    Which two of the four cards now in hand go back on the library is
    Brainstorm's controller's choice, and "in any order" is the same choice
    again - the first card named ends up on top. Nothing is asked about the
    two that stay.
    """
    scenario = brainstorm_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island", username="alice")
    brainstorm = scenario.cast_onto_stack("Brainstorm", island, username="alice")
    assert brainstorm.zone is Zone.STACK

    giant = scenario.find("Hill Giant", Zone.LIBRARY, "alice")
    mountain = scenario.find("Mountain", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(mountain, giant, username="alice", source="Brainstorm")
    scenario.pass_until_resolved()

    assert [state.name for state in scenario.player("alice").hand] == ["Grizzly Bears"]
    assert [state.name for state in scenario.player("alice").library] == [
        "Mountain",
        "Hill Giant",
    ]


def test_scrying_does_not_move_a_card_into_the_library():
    """The other half of the episode, and the half the engine can show.

    CR 701.22a's scry only reorders cards that are already in the library, so
    nothing is *put into* one and CR 603.2g's "an ability triggers only if its
    trigger event actually occurs" is never satisfied. The assertion is on the
    zones rather than on a trigger, since the trigger does not exist here: every
    card the scry touched was in the library before and is in the library after.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Preordain"],
            library=["Grizzly Bears", "Hill Giant", "Mountain"],
            battlefield=["Island", "Wan Shi Tong, All-Knowing"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    before = {state.id for state in scenario.player("alice").library}
    (island,) = scenario.untapped_sources("Island", username="alice")
    scenario.scry_keeping_everything_on_top(username="alice")

    scenario.cast_and_resolve("Preordain", island, username="alice")

    after = {state.id for state in scenario.player("alice").library}
    assert after <= before, "a scry adds nothing to the library"
    assert scenario.pending_triggers == []
