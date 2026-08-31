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

None of that is expressible here: `machines/abilities.TriggerEvent` has no
"cards put into a library" shape at all - twenty-two conditions are recognised
and this is not one - so the ability parses with `event` unset and never fires.
Every CR number here was looked up with `knowledge_search(type="rules")` in the
session that wrote the file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggeredAbility, parse_abilities
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


@pytest.mark.xfail(
    strict=True,
    reason="No `TriggerEvent` covers 'one or more cards are put into a library', "
    "so Wan Shi Tong's ability never triggers and no Spirit tokens are created.",
)
def test_a_brainstorm_puts_two_cards_into_the_library_and_triggers_once():
    """The episode's Brainstorm ruling.

    Brainstorm draws three, which really does move those cards out of the
    library, and then puts two cards from hand back - so cards are *put into* a
    library, and CR 603.2c's "an ability triggers only once each time its trigger
    event occurs" makes that a single trigger even though two cards move, because
    they move as one event.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Brainstorm"],
            library=["Grizzly Bears", "Grizzly Bears", "Grizzly Bears"],
            battlefield=["Island", "Wan Shi Tong, All-Knowing"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island", username="alice")

    scenario.cast_and_resolve("Brainstorm", island, username="alice")

    assert len(scenario.pending_triggers) == 1


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
