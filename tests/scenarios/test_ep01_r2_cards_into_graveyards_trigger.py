"""Scenario: "Whenever one or more creature cards are put into graveyards
from anywhere, investigate. This ability triggers only once each turn."
(Dennick, Pious Apparition - the back face of the listed disturb card Dennick,
Pious Apprentice).

The batched CR 603.2c event the engine already raises for Robot Domination's
"... put into your graveyard from anywhere" (`ExtraTriggerEvent.
PUT_INTO_GRAVEYARD`), with the plural "graveyards": a creature card arriving
in *any* player's graveyard counts, not only the controller's. A token is not
a card (CR 108.2), and a noncreature card does not match. The once-each-turn
budget is the general one every "This ability triggers only once each turn."
ability already shares (`Game.once_per_turn_triggers`), reset each turn.
CR 701.16a: investigate is "Create a Clue token".

Dennick is the only Modern/Pioneer/Standard printing whose batched condition
says "graveyards" (oracle-wide search, 2026-10-11); the widened regex keeps
Robot Domination's "your graveyard" reading, proven by the last test here.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

DENNICK = "Dennick, Pious Apprentice"
TRIGGER = "Dennick, Pious Apparition's triggered ability"


def _board(alice_extra: dict | None = None, bob: dict | None = None):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            **{
                "graveyard": [DENNICK],
                "battlefield": ["Plains", "Plains", "Island", "Island"],
                "library": ["Island"] * 10,
                **(alice_extra or {}),
            },
        )
        .player("bob", **{"library": ["Island"] * 10, **(bob or {})})
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains", "Island", "Island")
    casting = scenario.cast(DENNICK, from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Disturb")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    dennick = scenario.resolve_top()
    assert dennick.name == "Dennick, Pious Apparition"
    return scenario


def _clues(scenario, username="alice"):
    return [
        state
        for state in scenario.game.permanents_controlled_by(username)
        if state.token and "Clue" in state.subtypes
    ]


def _bin(scenario, *states):
    for state in states:
        scenario.game.put_into_graveyard(state)
    scenario.game.announce_batched_events()
    scenario.game.put_triggers_on_stack()


def test_a_creature_card_put_into_an_opponents_graveyard_investigates():
    scenario = _board(bob={"battlefield": ["Grizzly Bears"]})

    _bin(scenario, scenario.creature("Grizzly Bears", "bob"))

    assert scenario.stack_names() == [TRIGGER]
    scenario.resolve_top()
    assert len(_clues(scenario)) == 1


def test_a_creature_card_milled_into_its_owners_graveyard_counts_from_anywhere():
    scenario = _board({"library": ["Grizzly Bears"] + ["Island"] * 9})

    _bin(scenario, scenario.find("Grizzly Bears", Zone.LIBRARY, "alice"))

    assert scenario.stack_names() == [TRIGGER]


def test_two_creature_cards_at_once_are_one_event():
    """CR 603.2c: one batched event, one trigger."""
    scenario = _board(bob={"battlefield": ["Grizzly Bears", "Hill Giant"]})

    _bin(
        scenario,
        scenario.creature("Grizzly Bears", "bob"),
        scenario.creature("Hill Giant", "bob"),
    )

    assert scenario.stack_names() == [TRIGGER]


def test_it_triggers_only_once_each_turn():
    scenario = _board(bob={"battlefield": ["Grizzly Bears", "Hill Giant"]})
    _bin(scenario, scenario.creature("Grizzly Bears", "bob"))
    scenario.resolve_top()

    _bin(scenario, scenario.creature("Hill Giant", "bob"))

    assert scenario.stack_names() == []
    assert len(_clues(scenario)) == 1


def test_a_noncreature_card_does_not_trigger_it():
    scenario = _board({"library": ["Island"] * 10})

    _bin(scenario, scenario.find("Island", Zone.LIBRARY, "alice"))

    assert scenario.stack_names() == []


def test_the_front_face_has_no_such_trigger():
    """CR 712.8a: Dennick, Pious Apprentice on the battlefield front face up
    has only its front face's abilities."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[DENNICK], library=["Grizzly Bears"] + ["Island"] * 9)
        .player("bob", library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _bin(scenario, scenario.find("Grizzly Bears", Zone.LIBRARY, "alice"))

    assert scenario.stack_names() == []


def test_robot_dominations_your_graveyard_still_ignores_an_opponents_graveyard():
    """The widening is the plural only: "your graveyard" still names the
    controller's own."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Robot Domination"], library=["Island"] * 10)
        .player("bob", battlefield=["Grizzly Bears"], library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _bin(scenario, scenario.creature("Grizzly Bears", "bob"))

    assert scenario.stack_names() == []
