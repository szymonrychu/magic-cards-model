"""The anaphoric delayed triggered ability (CR 603.7), on `machines/delayed.py`
alone.

A delayed trigger whose subject is a pronoun - "Exile **it** at the beginning
of the next end step", "Sacrifice **that token** at the beginning of the next
end step" - cannot name its object from its own text. The object is whatever
the paragraph's earlier sentence just moved or created, and only the caller
running that sentence knows which one it was. These tests drive
`parse_anaphoric_delayed_clause` and `anaphoric_delayed_trigger` with real
printed clauses and a real board state, and check the CR 603.7c zone and
incarnation guards the resulting trigger carries.

No card json is hand-written: every board state below is built by `Scenario`
from the real Scryfall printings in `tests/fixtures/cards/`.
"""

import pytest

from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.delayed import (
    anaphoric_delayed_trigger,
    parse_anaphoric_delayed_clause,
)
from magic_cards_model.machines.triggers import GameEvent
from magic_cards_model.machines.turn import Step
from magic_cards_model.models.zone import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board():
    """One real creature on the battlefield and a real spell alongside it."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Mountain"], hand=["Lightning Bolt"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_a_delayed_trigger_can_name_the_object_the_effect_just_moved():
    """The named test of Task 1.12: "Exile it at the beginning of the next end
    step" builds a real `DelayedTrigger` once the caller hands over the object
    its own earlier sentence just moved (CR 603.7, CR 603.7c)."""
    scenario = _board()
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")

    trigger = anaphoric_delayed_trigger(
        "Exile it at the beginning of the next end step.",
        subject=bears,
        controller="alice",
        source_id=None,
        source_name="Goryo's Vengeance",
    )

    assert trigger is not None
    assert trigger.event is TriggerEvent.BEGINNING_OF_STEP
    assert trigger.step is Step.END_STEP
    assert trigger.controller == "alice"
    assert trigger.source_name == "Goryo's Vengeance"
    # CR 603.7c: the particular object, plus where it is expected to be and
    # which incarnation of it this is.
    assert trigger.subject_id == bears.id
    assert trigger.expected_zone is Zone.BATTLEFIELD
    assert trigger.expected_stamp == bears.zone_change_stamp
    assert trigger.remaining == 1


def test_the_anaphoric_trigger_actually_exiles_the_object_when_it_fires():
    """End to end on `delayed.py`'s own store: create, fire on the end step,
    resolve the callback, and the object is gone (CR 701.13a)."""
    scenario = _board()
    game = scenario.game
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")

    trigger = anaphoric_delayed_trigger(
        "Exile it at the beginning of the next end step.",
        subject=bears,
        controller="alice",
        source_id=None,
        source_name="Goryo's Vengeance",
    )
    assert trigger is not None
    game.create_delayed_trigger(trigger)

    fired = game.delayed_triggers.fire(
        GameEvent(event=TriggerEvent.BEGINNING_OF_STEP, step=Step.END_STEP, player="alice")
    )
    assert len(fired) == 1
    effect = game.delayed_triggers.effect_for(fired[0])
    assert effect is not None
    effect(game, fired[0], trigger)

    assert bears.zone is Zone.EXILE


def test_the_object_that_left_the_expected_zone_is_not_affected():
    """CR 603.7c: "if that object is no longer in the zone it's expected to be
    in at the time the delayed triggered ability resolves, the ability won't
    affect it." Killed in response, the exile finds nothing."""
    scenario = _board()
    game = scenario.game
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")

    trigger = anaphoric_delayed_trigger(
        "Exile it at the beginning of the next end step.",
        subject=bears,
        controller="alice",
        source_id=None,
        source_name="Goryo's Vengeance",
    )
    assert trigger is not None
    game.create_delayed_trigger(trigger)
    game.put_into_graveyard(bears)

    fired = game.delayed_triggers.fire(
        GameEvent(event=TriggerEvent.BEGINNING_OF_STEP, step=Step.END_STEP, player="alice")
    )
    effect = game.delayed_triggers.effect_for(fired[0])
    assert effect is not None
    effect(game, fired[0], trigger)

    assert bears.zone is Zone.GRAVEYARD


def test_an_object_that_left_and_came_back_is_a_new_object():
    """CR 603.7c's parenthetical, via `expected_stamp`: bounced and recast, the
    same `id` in the same zone is still not the object the ability named."""
    scenario = _board()
    game = scenario.game
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")

    trigger = anaphoric_delayed_trigger(
        "Exile it at the beginning of the next end step.",
        subject=bears,
        controller="alice",
        source_id=None,
        source_name="Goryo's Vengeance",
    )
    assert trigger is not None
    game.create_delayed_trigger(trigger)

    game.return_to_hand(bears)
    game.put_onto_battlefield(bears, "alice")
    assert bears.zone is Zone.BATTLEFIELD

    fired = game.delayed_triggers.fire(
        GameEvent(event=TriggerEvent.BEGINNING_OF_STEP, step=Step.END_STEP, player="alice")
    )
    effect = game.delayed_triggers.effect_for(fired[0])
    assert effect is not None
    effect(game, fired[0], trigger)

    assert bears.zone is Zone.BATTLEFIELD


def test_goryos_vengeance_third_sentence_end_to_end_through_the_real_end_step():
    """Goryo's Vengeance's own printed third sentence, driven through the
    engine rather than called by hand: reanimate (what `effects.py`'s first
    sentence does), install the anaphoric trigger, then let the turn actually
    reach its end step so `Game.emit` fires it, `put_triggers_on_stack` stacks
    it and `resolve_top` runs it.

    This is the half of Goryo's Vengeance that `machines/delayed.py` owns. The
    other half - splitting the paragraph and running sentence one - is
    `machines/effects.py`'s, and is Task 2.11.
    """
    scenario = (
        Scenario()
        .player("alice", graveyard=["Griselbrand"], battlefield=["Swamp"])
        .player("bob", battlefield=["Swamp"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game

    griselbrand = scenario.find("Griselbrand", Zone.GRAVEYARD, "alice")
    entered = game.put_onto_battlefield(griselbrand, "alice")
    assert entered.zone is Zone.BATTLEFIELD

    # The card's own third sentence, verbatim from the fixture printing.
    (vengeance,) = [
        line
        for line in (card("Goryo's Vengeance").oracle_text or "").split("\n")[0].split(". ")
        if line.lower().startswith("exile it")
    ]
    trigger = anaphoric_delayed_trigger(
        vengeance,
        subject=entered,
        controller="alice",
        source_id=None,
        source_name="Goryo's Vengeance",
    )
    assert trigger is not None
    game.create_delayed_trigger(trigger)

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.pass_until_resolved()

    assert entered.zone is Zone.EXILE


@pytest.mark.parametrize(
    ("clause", "step", "verb"),
    [
        ("Exile it at the beginning of the next end step.", Step.END_STEP, "exile"),
        (
            "Sacrifice that token at the beginning of the next end step.",
            Step.END_STEP,
            "sacrifice",
        ),
        (
            "At the beginning of the next end step, sacrifice it.",
            Step.END_STEP,
            "sacrifice",
        ),
        (
            "Return it to its owner's hand at the beginning of the next end step.",
            Step.END_STEP,
            "return_to_hand",
        ),
        (
            "At the beginning of the next end step, return that card to the battlefield "
            "under its owner's control.",
            Step.END_STEP,
            "return_to_battlefield",
        ),
        ("Destroy that creature at end of combat.", Step.END_OF_COMBAT, "destroy"),
        (
            "Tap it at the beginning of the next turn's upkeep.",
            Step.UPKEEP,
            "tap",
        ),
    ],
)
def test_the_printed_shapes_this_primitive_reads(clause, step, verb):
    """Both word orders CR 603.7 prints ("at <timing>, <verb>" and "<verb> at
    <timing>"), across the verbs and pronouns the shape uses."""
    parsed = parse_anaphoric_delayed_clause(clause)
    assert parsed is not None
    assert parsed.step is step
    assert parsed.verb == verb


@pytest.mark.parametrize(
    "clause",
    [
        # No timing phrase at all - an ordinary instruction, not a delayed one.
        "Exile it.",
        # A timing phrase this primitive does not read.
        "Exile it at the beginning of your next end step.",
        # A verb this primitive does not read: refusing is the point, so the
        # caller keeps failing closed rather than doing half the paragraph.
        "Shuffle it into its owner's library at the beginning of the next end step.",
        # Not anaphoric: a named subject the caller does not have to supply.
        "Exile that creature card at the beginning of the next end step.",
        # Anaphoric but with no verb.
        "At the beginning of the next end step, it.",
    ],
)
def test_what_this_primitive_refuses(clause):
    assert parse_anaphoric_delayed_clause(clause) is None


def test_that_token_refuses_a_nontoken_subject():
    """CR 108.2b: "Tokens aren't considered cards." Fire Navy Trebuchet's
    "Sacrifice that token" names the token it just created, so handing it a
    real card is a caller bug and the primitive refuses rather than sacrificing
    the wrong permanent."""
    scenario = _board()
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    assert bears.token is False

    assert (
        anaphoric_delayed_trigger(
            "Sacrifice that token at the beginning of the next end step.",
            subject=bears,
            controller="alice",
            source_id=None,
            source_name="Fire Navy Trebuchet",
        )
        is None
    )


def test_that_card_refuses_a_token_subject():
    """The mirror of the above, and CR 111.8's reason for caring: a token that
    has left the battlefield cannot come back, so a blink clause reading "that
    card" was never about one."""
    scenario = _board()
    game = scenario.game
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    bears.token = True
    game.exile_permanent(bears)

    assert (
        anaphoric_delayed_trigger(
            "At the beginning of the next end step, return that card to the battlefield "
            "under its owner's control.",
            subject=bears,
            controller="alice",
            source_id=None,
            source_name="Phelia, Exuberant Shepherd",
        )
        is None
    )


def test_return_to_the_battlefield_expects_the_object_in_exile():
    """The expected zone (CR 603.7c) is the one the verb implies, not always
    the battlefield: a blink's returned card is waited for in exile."""
    scenario = _board()
    game = scenario.game
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    game.exile_permanent(bears)

    trigger = anaphoric_delayed_trigger(
        "At the beginning of the next end step, return it to the battlefield under its "
        "owner's control.",
        subject=bears,
        controller="alice",
        source_id=None,
        source_name="Phelia, Exuberant Shepherd",
    )
    assert trigger is not None
    assert trigger.expected_zone is Zone.EXILE
    assert trigger.expected_stamp == bears.zone_change_stamp


def test_that_creature_refuses_a_noncreature_subject():
    """CR 603.7c lets the object change characteristics after the fact, but the
    pronoun still has to agree with it when the ability is created."""
    scenario = _board()
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")

    assert (
        anaphoric_delayed_trigger(
            "Exile that creature at the beginning of the next end step.",
            subject=mountain,
            controller="alice",
            source_id=None,
            source_name="Goryo's Vengeance",
        )
        is None
    )


def test_the_trigger_text_is_the_clause_as_printed():
    """CR 603.7: the ability contains "when"/"whenever"/"at" somewhere, and the
    stack listing should read as the card does."""
    scenario = _board()
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    clause = "Exile it at the beginning of the next end step."

    trigger = anaphoric_delayed_trigger(
        clause,
        subject=bears,
        controller="alice",
        source_id=None,
        source_name="Goryo's Vengeance",
    )
    assert trigger is not None
    assert trigger.text == clause
    assert trigger.as_ability().text == clause
