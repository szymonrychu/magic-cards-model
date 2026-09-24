"""CR 103.6a: "If this card is in your opening hand, you may begin the game with
it on the battlefield" - and Gemstone Caverns' non-starting-player,
luck-counter variant with its "If you do, exile a card from your hand." rider.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 103.6** - "Some cards allow a player to take actions with them from
  their opening hand. Once the mulligan process (see rule 103.5) is complete,
  the starting player may take any such actions in any order. Then each other
  player in turn order may do the same."
- **CR 103.6a** - "If a card allows a player to begin the game with that card
  on the battlefield, the player taking this action puts that card onto the
  battlefield."
- **CR 701.13a** - "To exile an object, move it to the exile zone from
  wherever it is." The Caverns' rider.
- **CR 608.2d** - the rider's choice of which card is the holder's.

The rider is read, never looked up by card name: `read_rider` splits "If you
do, ..." off and hands the rest to the same `trigger_effect_for` every printed
trigger goes through. Leyline of Sanctity is the second printing of the plain
template (legal in Modern and Pioneer, in no deck in the api's pool).
"""

import pytest

from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from magic_cards_model.machines.opening_hand import (
    OpeningHandActionKind,
    read_opening_hand_actions,
    read_rider,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import PlayedScenario, Scenario

LEYLINES = ["Leyline of Abundance", "Leyline of the Guildpact", "Leyline of Sanctity"]


def will_take(scenario: PlayedScenario, player: str, source: str) -> None:
    scenario.game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.OPENING_HAND_ACTION, value=True, player=player, source=source
        )
    )


def offered(scenario: PlayedScenario, player: str) -> list[str]:
    return [
        decision.source or ""
        for decision in scenario.game.decisions.asked
        if decision.kind is DecisionKind.OPENING_HAND_ACTION and decision.player == player
    ]


# -- the template, read off the printing (CR 103.6a) -----------------------


@pytest.mark.parametrize("name", [*LEYLINES, "Gemstone Caverns"])
def test_the_begin_on_the_battlefield_line_is_read_with_no_notice(name: str) -> None:
    actions, notices = read_opening_hand_actions(card(name))

    assert notices == []
    (action,) = actions
    assert action.kind is OpeningHandActionKind.BEGIN_ON_BATTLEFIELD


@pytest.mark.parametrize("name", [*LEYLINES, "Gemstone Caverns"])
def test_the_sweep_counts_the_opening_hand_line_as_handled(name: str) -> None:
    (clause,) = [c for c in classify_clauses(card(name)) if "opening hand" in c.text]

    assert clause.category == HANDLED


def test_the_plain_leyline_template_carries_no_restriction_counter_or_rider() -> None:
    (action,) = read_opening_hand_actions(card("Leyline of Sanctity"))[0]

    assert action.requires_not_starting_player is False
    assert action.counter is None
    assert action.rider == ""


def test_the_caverns_variant_carries_the_restriction_the_counter_and_a_parsed_rider() -> None:
    (action,) = read_opening_hand_actions(card("Gemstone Caverns"))[0]

    assert action.requires_not_starting_player is True
    assert action.counter == "luck"
    rider = read_rider("Gemstone Caverns", action.rider)
    assert rider is not None
    assert rider.step is None  # performed at once, as part of the action
    assert rider.effect == "exile a card from your hand."


# -- taking it --------------------------------------------------------------


def test_a_taken_leyline_starts_the_game_on_the_battlefield_and_works() -> None:
    """Leyline of Sanctity begins on the battlefield, and its "You have
    hexproof." is live before the first turn."""
    scenario = (
        Scenario()
        .player("alice", hand=["Leyline of Sanctity", "Forest"], library=["Forest"] * 3)
        .player("bob", library=["Mountain"] * 3)
        .build()
    )
    will_take(scenario, "alice", "Leyline of Sanctity")

    scenario.game.take_opening_hand_actions()

    alice = scenario.player("alice")
    assert [state.name for state in scenario.game.battlefield] == ["Leyline of Sanctity"]
    assert [state.name for state in alice.hand] == ["Forest"]
    assert len(alice.library) == 3
    hexproof, _ = scenario.game.player_hexproof(alice)
    assert hexproof


def test_declining_leaves_the_leyline_in_hand() -> None:
    """CR 103.6's "may" - an unscripted player declines."""
    scenario = (
        Scenario()
        .player("alice", hand=["Leyline of the Guildpact"], library=["Forest"] * 3)
        .player("bob", library=["Mountain"] * 3)
        .build()
    )

    scenario.game.take_opening_hand_actions()

    assert offered(scenario, "alice") == ["Leyline of the Guildpact"]
    assert scenario.game.battlefield == []
    assert [state.name for state in scenario.player("alice").hand] == ["Leyline of the Guildpact"]


def test_a_leyline_begun_on_the_battlefield_applies_its_static_at_once() -> None:
    """Leyline of the Guildpact's "Each nonland permanent you control is all
    colors." reaches a permanent already there when the game begins."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Leyline of the Guildpact"],
            library=["Forest"] * 3,
            battlefield=["Grizzly Bears"],
        )
        .player("bob", library=["Mountain"] * 3)
        .build()
    )
    will_take(scenario, "alice", "Leyline of the Guildpact")

    scenario.game.take_opening_hand_actions()

    bears = scenario.creature("Grizzly Bears", "alice")
    colors = set(scenario.game.characteristics_of(bears).colors)
    assert colors == {Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN}


def test_two_leylines_in_one_hand_may_both_begin_on_the_battlefield() -> None:
    """CR 103.6: "any such actions in any order" - one per card."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Leyline of Abundance", "Leyline of Sanctity"],
            library=["Forest"] * 3,
        )
        .player("bob", library=["Mountain"] * 3)
        .build()
    )
    will_take(scenario, "alice", "Leyline of Abundance")
    will_take(scenario, "alice", "Leyline of Sanctity")

    scenario.game.take_opening_hand_actions()

    assert sorted(state.name for state in scenario.game.battlefield) == [
        "Leyline of Abundance",
        "Leyline of Sanctity",
    ]
    assert scenario.player("alice").hand == []


def test_each_player_may_take_their_own_leyline() -> None:
    """CR 103.6: the starting player first, "then each other player"."""
    scenario = (
        Scenario()
        .player("alice", hand=["Leyline of Sanctity"], library=["Forest"] * 3)
        .player("bob", hand=["Leyline of Abundance"], library=["Forest"] * 3)
        .build()
    )
    will_take(scenario, "alice", "Leyline of Sanctity")
    will_take(scenario, "bob", "Leyline of Abundance")

    scenario.game.take_opening_hand_actions()

    controllers = {state.name: state.controller for state in scenario.game.battlefield}
    assert controllers == {"Leyline of Sanctity": "alice", "Leyline of Abundance": "bob"}


# -- the non-starting-player, luck-counter variant ---------------------------


def test_the_starting_player_is_not_offered_the_caverns() -> None:
    """ "and you're not the starting player" - no question at all."""
    scenario = (
        Scenario()
        .player("alice", hand=["Gemstone Caverns", "Forest"], library=["Forest"] * 3)
        .player("bob", library=["Mountain"] * 3)
        .build()
    )
    assert scenario.turn.starting_player == "alice"

    scenario.game.take_opening_hand_actions()

    assert offered(scenario, "alice") == []
    assert scenario.game.battlefield == []


def test_the_other_player_begins_with_the_caverns_and_a_luck_counter() -> None:
    scenario = (
        Scenario()
        .player("alice", library=["Forest"] * 3)
        .player("bob", hand=["Gemstone Caverns", "Mountain"], library=["Mountain"] * 3)
        .build()
    )
    will_take(scenario, "bob", "Gemstone Caverns")

    scenario.game.take_opening_hand_actions()

    (caverns,) = scenario.game.battlefield
    assert caverns.name == "Gemstone Caverns"
    assert caverns.controller == "bob"
    assert caverns.counters["luck"] == 1


def test_the_rider_exiles_the_card_its_holder_chooses() -> None:
    """ "If you do, exile a card from your hand." - the holder picks (CR 608.2d)
    and the card goes to the one shared exile zone (CR 701.13a)."""
    scenario = (
        Scenario()
        .player("alice", library=["Forest"] * 3)
        .player(
            "bob",
            hand=["Gemstone Caverns", "Mountain", "Lightning Bolt"],
            library=["Mountain"] * 3,
        )
        .build()
    )
    will_take(scenario, "bob", "Gemstone Caverns")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    scenario.will_choose_cards(bolt, username="bob", source="Gemstone Caverns")

    scenario.game.take_opening_hand_actions()

    bob = scenario.player("bob")
    assert [state.name for state in bob.hand] == ["Mountain"]
    assert [state.name for state in scenario.game.exile] == ["Lightning Bolt"]
    (asked,) = [d for d in scenario.game.decisions.asked if d.kind is DecisionKind.CHOOSE_CARDS]
    assert asked.amount == 1
    assert set(asked.cards) == {state.id for state in bob.hand} | {bolt.id}


def test_the_rider_exiles_nothing_from_an_empty_hand() -> None:
    """The Caverns was the whole hand: there is nothing left to choose."""
    scenario = (
        Scenario()
        .player("alice", library=["Forest"] * 3)
        .player("bob", hand=["Gemstone Caverns"], library=["Mountain"] * 3)
        .build()
    )
    will_take(scenario, "bob", "Gemstone Caverns")

    scenario.game.take_opening_hand_actions()

    assert [state.name for state in scenario.game.battlefield] == ["Gemstone Caverns"]
    assert scenario.game.exile == []
    assert not [d for d in scenario.game.decisions.asked if d.kind is DecisionKind.CHOOSE_CARDS]


def test_declining_the_caverns_exiles_nothing() -> None:
    scenario = (
        Scenario()
        .player("alice", library=["Forest"] * 3)
        .player("bob", hand=["Gemstone Caverns", "Mountain"], library=["Mountain"] * 3)
        .build()
    )

    scenario.game.take_opening_hand_actions()

    assert offered(scenario, "bob") == ["Gemstone Caverns"]
    assert scenario.game.battlefield == []
    assert scenario.game.exile == []
    assert len(scenario.player("bob").hand) == 2
