"""Static bans on turning a face-down permanent face up: Unable to Scream's "As
long as enchanted creature is face down, it can't be turned face up.", and
Karlov Watchdog's "Permanents your opponents control can't be turned face up
during your turn." (the second printing - a board-wide subject, an opponents
scope and a turn condition; legal in Modern, Pioneer and Standard, in no deck
in the api's pool).

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 702.37e** - "Any time you have priority, you may turn a face-down
  permanent you control with a morph ability face up. This is a special
  action ..." The action these abilities forbid.
- **CR 708.2** - a face-down permanent has no characteristics but those the
  rules give it, so it cannot carry the ban itself; the ban lives on the
  Aura or the Watchdog.
- **CR 611.3a** - a static ability's effect "isn't 'locked in'".
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models.action import ActionKind
from magic_cards_model.models.card_state import CardState
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import PlayedScenario, Scenario

MORPH = "Aquamorph Entity"


def face_down(scenario: PlayedScenario, username: str) -> CardState:
    (state,) = [
        s for s in scenario.game.battlefield if s.card.name == MORPH and s.controller == username
    ]
    state.turn_face_down()
    return state


def may_turn_up(scenario: PlayedScenario, state: CardState) -> bool:
    return scenario.game.why_cannot_turn_face_up(state) is None


def offered(scenario: PlayedScenario, state: CardState, username: str) -> bool:
    return any(
        action.kind is ActionKind.TURN_FACE_UP and action.card_id == state.id
        for action in legal_actions(scenario.game, username)
    )


@pytest.mark.parametrize("name", ["Unable to Scream", "Karlov Watchdog"])
def test_the_ban_line_is_handled(name: str) -> None:
    (clause,) = [c for c in classify_clauses(card(name)) if "turned face up" in c.text]

    assert clause.category == HANDLED


# -- Unable to Scream: the enchanted creature ----------------------------------


def aura_board() -> PlayedScenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[MORPH, "Unable to Scream", *["Island"] * 3])
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_an_unenchanted_face_down_morph_may_be_turned_face_up() -> None:
    scenario = aura_board()
    morph = face_down(scenario, "alice")

    assert may_turn_up(scenario, morph)
    assert offered(scenario, morph, "alice")


def test_the_enchanted_face_down_creature_cannot_be_turned_face_up() -> None:
    scenario = aura_board()
    morph = face_down(scenario, "alice")
    aura = next(s for s in scenario.game.battlefield if s.name == "Unable to Scream")
    aura.attach_to(morph)

    refusal = scenario.game.why_cannot_turn_face_up(morph)

    assert refusal is not None
    assert "Unable to Scream" in refusal
    assert not offered(scenario, morph, "alice")
    with pytest.raises(ValueError, match="can't be turned face up"):
        scenario.turn_face_up(morph, *scenario.untapped_sources("Island", "Island", "Island"))
    assert morph.face_down


def test_the_ban_ends_when_the_aura_leaves() -> None:
    scenario = aura_board()
    morph = face_down(scenario, "alice")
    aura = next(s for s in scenario.game.battlefield if s.name == "Unable to Scream")
    aura.attach_to(morph)
    assert not may_turn_up(scenario, morph)

    scenario.game.put_into_graveyard(aura)

    assert may_turn_up(scenario, morph)
    scenario.turn_face_up(morph, *scenario.untapped_sources("Island", "Island", "Island"))
    assert not morph.face_down


def test_only_the_enchanted_creature_is_banned() -> None:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[MORPH, MORPH, "Unable to Scream", *["Island"] * 3])
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = [s for s in scenario.game.battlefield if s.card.name == MORPH]
    first.turn_face_down()
    second.turn_face_down()
    aura = next(s for s in scenario.game.battlefield if s.name == "Unable to Scream")
    aura.attach_to(first)

    assert not may_turn_up(scenario, first)
    assert may_turn_up(scenario, second)


# -- Karlov Watchdog: opponents' permanents, during your turn -------------------


def watchdog_board(*, first: str) -> PlayedScenario:
    """Alice controls the Watchdog; each player has a face-down morph.
    `first` is the starting player, whose turn it is."""
    players = {
        "alice": ["Karlov Watchdog", MORPH, *["Island"] * 3],
        "bob": [MORPH, *["Island"] * 3],
    }
    order = [first, *(name for name in players if name != first)]
    builder = Scenario().manual_turn_based_actions()
    for name in order:
        builder = builder.player(name, battlefield=players[name], library=["Island"] * 3)
    scenario = builder.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_an_opponent_s_face_down_permanent_cannot_turn_up_during_my_turn() -> None:
    scenario = watchdog_board(first="alice")
    bobs = face_down(scenario, "bob")

    refusal = scenario.game.why_cannot_turn_face_up(bobs)

    assert refusal is not None
    assert "Karlov Watchdog" in refusal
    assert not offered(scenario, bobs, "bob")


def test_my_own_face_down_permanent_is_not_an_opponent_s() -> None:
    scenario = watchdog_board(first="alice")
    alices = face_down(scenario, "alice")

    assert may_turn_up(scenario, alices)


def test_on_the_opponent_s_own_turn_it_may_turn_up() -> None:
    """ "during your turn" - bob's turn is not the Watchdog controller's."""
    scenario = watchdog_board(first="bob")
    bobs = face_down(scenario, "bob")

    assert may_turn_up(scenario, bobs)
    scenario.turn_face_up(bobs, *scenario.untapped_sources("Island", "Island", "Island"))
    assert not bobs.face_down


def test_the_ban_ends_when_the_watchdog_leaves() -> None:
    scenario = watchdog_board(first="alice")
    bobs = face_down(scenario, "bob")
    watchdog = scenario.creature("Karlov Watchdog", "alice")

    scenario.game.put_into_graveyard(watchdog)

    assert may_turn_up(scenario, bobs)
