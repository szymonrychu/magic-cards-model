"""CR 103.6b: "You may reveal this card from your opening hand. If you do, at the
beginning of your first upkeep, ..." - and the "the first upkeep" wording.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 103.6b** - "If a card allows a player to reveal it from their opening
  hand, the player taking this action does so. The card remains revealed until
  the first turn begins. Each card may be revealed this way only once."
- **CR 603.7** / **CR 603.7b** - "A delayed triggered ability will trigger only
  once - the next time its trigger event occurs - unless it has a stated
  duration". The rider creates one.
- **CR 701.13a** - "To exile an object, move it to the exile zone from
  wherever it is." Devourer of Destiny's "Exile the rest."

Devourer of Destiny says "your first upkeep": only its holder's own upkeep
fires it. Chancellor of the Forge - the second printing, legal in Modern and
in no deck in the api's pool - says "the first upkeep": the game's first
upkeep, whoever's turn it is. Both are read by one parser (`read_rider`) and
their effects by the same `trigger_effect_for` every printed trigger uses; no
card name is looked up anywhere.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import CardSplit, DecisionKind, ScriptedAnswer
from magic_cards_model.machines.opening_hand import (
    OpeningHandActionKind,
    read_opening_hand_actions,
    read_rider,
)
from magic_cards_model.models import Zone
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import PlayedScenario, Scenario

LIBRARY = ["Forest", "Island", "Swamp", "Mountain", "Plains", "Forest", "Island"]


def will_reveal(scenario: PlayedScenario, player: str, source: str, times: int = 1) -> None:
    scenario.game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.OPENING_HAND_ACTION,
            value=True,
            player=player,
            source=source,
            uses=times,
        )
    )


def to_first_upkeep(scenario: PlayedScenario) -> None:
    """Take the opening-hand actions, then walk untap -> upkeep of turn one."""
    scenario.game.take_opening_hand_actions()
    scenario.advance()
    assert scenario.step is Step.UPKEEP


# -- reading ------------------------------------------------------------------


@pytest.mark.parametrize("name", ["Devourer of Destiny", "Chancellor of the Forge"])
def test_the_reveal_line_is_read_with_no_notice(name: str) -> None:
    actions, notices = read_opening_hand_actions(card(name))

    assert notices == []
    (action,) = actions
    assert action.kind is OpeningHandActionKind.REVEAL


@pytest.mark.parametrize("name", ["Devourer of Destiny", "Chancellor of the Forge"])
def test_the_sweep_counts_the_reveal_line_as_handled(name: str) -> None:
    (clause,) = [c for c in classify_clauses(card(name)) if "opening hand" in c.text]

    assert clause.category == HANDLED


def test_your_first_upkeep_is_the_holders_own() -> None:
    (action,) = read_opening_hand_actions(card("Devourer of Destiny"))[0]
    rider = read_rider("Devourer of Destiny", action.rider)

    assert rider is not None
    assert rider.step is Step.UPKEEP
    assert rider.yours is True
    assert rider.effect.startswith("look at the top four cards of your library")


def test_the_first_upkeep_is_whoever_s_comes_first() -> None:
    (action,) = read_opening_hand_actions(card("Chancellor of the Forge"))[0]
    rider = read_rider("Chancellor of the Forge", action.rider)

    assert rider is not None
    assert rider.step is Step.UPKEEP
    assert rider.yours is False
    assert rider.effect == "create a 1/1 red Phyrexian Goblin creature token with haste."


def test_a_rider_with_no_timing_and_no_readable_effect_is_refused() -> None:
    """The fail-closed path: a rider whose effect no reader performs is None,
    so the action carrying it is never offered."""
    assert read_rider("Devourer of Destiny", "If you do, gibber at the moon.") is None
    assert read_rider("Devourer of Destiny", "Then draw a card.") is None


# -- Devourer of Destiny: "your first upkeep" --------------------------------


def test_revealing_leaves_the_card_in_hand_and_creates_one_delayed_trigger() -> None:
    scenario = (
        Scenario()
        .player("alice", hand=["Devourer of Destiny"], library=list(LIBRARY))
        .player("bob", library=list(LIBRARY))
        .build()
    )
    will_reveal(scenario, "alice", "Devourer of Destiny")

    scenario.game.take_opening_hand_actions()

    devourer = scenario.find("Devourer of Destiny", Zone.HAND, "alice")
    assert devourer.zone is Zone.HAND
    assert scenario.game.opening_hand_reveals == [devourer.id]
    (trigger,) = scenario.game.delayed_triggers.triggers
    assert trigger.step is Step.UPKEEP
    assert trigger.only_when_active == "alice"
    assert trigger.remaining == 1


def test_declining_the_reveal_creates_nothing() -> None:
    scenario = (
        Scenario()
        .player("alice", hand=["Devourer of Destiny"], library=list(LIBRARY))
        .player("bob", library=list(LIBRARY))
        .build()
    )

    scenario.game.take_opening_hand_actions()

    assert scenario.game.opening_hand_reveals == []
    assert scenario.game.delayed_triggers.triggers == []


def test_at_the_first_upkeep_one_card_is_kept_on_top_and_the_rest_exiled() -> None:
    scenario = (
        Scenario()
        .player("alice", hand=["Devourer of Destiny"], library=list(LIBRARY))
        .player("bob", library=list(LIBRARY))
        .build()
    )
    will_reveal(scenario, "alice", "Devourer of Destiny")
    alice = scenario.player("alice")
    top_four = list(alice.library[:4])
    kept = top_four[2]
    scenario.game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.SCRY,
            value=CardSplit(moved=(kept.id,)),
            player="alice",
            source="Devourer of Destiny",
        )
    )

    to_first_upkeep(scenario)
    scenario.pass_until_resolved()

    assert alice.library[0] is kept
    assert len(alice.library) == len(LIBRARY) - 3
    assert sorted(state.id for state in scenario.game.exile) == sorted(
        state.id for state in top_four if state is not kept
    )
    (asked,) = [d for d in scenario.game.decisions.asked if d.kind is DecisionKind.SCRY]
    assert asked.moved_label == "top of your library"
    assert asked.kept_label == "exiled"
    assert asked.amount == 1


def test_putting_nothing_back_exiles_all_four() -> None:
    scenario = (
        Scenario()
        .player("alice", hand=["Devourer of Destiny"], library=list(LIBRARY))
        .player("bob", library=list(LIBRARY))
        .build()
    )
    will_reveal(scenario, "alice", "Devourer of Destiny")
    top_four = list(scenario.player("alice").library[:4])

    to_first_upkeep(scenario)
    scenario.pass_until_resolved()

    assert all(state.zone is Zone.EXILE for state in top_four)
    assert len(scenario.player("alice").library) == len(LIBRARY) - 4


def test_a_short_library_looks_at_what_is_there() -> None:
    scenario = (
        Scenario()
        .player("alice", hand=["Devourer of Destiny"], library=["Forest", "Island"])
        .player("bob", library=list(LIBRARY))
        .build()
    )
    will_reveal(scenario, "alice", "Devourer of Destiny")

    to_first_upkeep(scenario)
    scenario.pass_until_resolved()

    assert [state.name for state in scenario.game.exile] == ["Forest", "Island"]


def test_the_opponent_s_upkeep_does_not_spend_it() -> None:
    """Bob starts; alice's Devourer waits past bob's upkeep for hers."""
    scenario = (
        Scenario()
        .player("bob", library=list(LIBRARY))
        .player("alice", hand=["Devourer of Destiny"], library=list(LIBRARY))
        .build()
    )
    assert scenario.turn.starting_player == "bob"
    will_reveal(scenario, "alice", "Devourer of Destiny")

    to_first_upkeep(scenario)

    assert scenario.turn.active_player == "bob"
    assert scenario.game.stack_is_empty
    assert scenario.game.pending_triggers == []
    assert len(scenario.game.delayed_triggers.triggers) == 1


def test_two_revealed_devourers_each_fire_once() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Devourer of Destiny", "Devourer of Destiny"],
            library=list(LIBRARY) * 2,
        )
        .player("bob", library=list(LIBRARY))
        .build()
    )
    will_reveal(scenario, "alice", "Devourer of Destiny", times=2)

    to_first_upkeep(scenario)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert len(scenario.game.exile) == 8
    assert scenario.game.delayed_triggers.triggers == []


# -- Chancellor of the Forge: "the first upkeep" -----------------------------


def test_the_first_upkeep_of_the_game_fires_it_even_when_it_is_the_opponent_s() -> None:
    """Bob starts, so the first upkeep is bob's - and alice's Chancellor
    creates her Goblin then, not on her own turn."""
    scenario = (
        Scenario()
        .player("bob", library=list(LIBRARY))
        .player("alice", hand=["Chancellor of the Forge"], library=list(LIBRARY))
        .build()
    )
    will_reveal(scenario, "alice", "Chancellor of the Forge")

    to_first_upkeep(scenario)
    assert scenario.turn.active_player == "bob"
    scenario.pass_until_resolved()

    (goblin,) = [state for state in scenario.game.battlefield if state.controller == "alice"]
    chars = scenario.game.characteristics_of(goblin)
    assert chars.subtypes == ("Phyrexian", "Goblin")
    assert (chars.power, chars.toughness) == (1, 1)
    assert chars.abilities == ("Haste",)
    assert scenario.game.delayed_triggers.triggers == []


def test_it_fires_only_once() -> None:
    """CR 603.7b: the next upkeep - alice's own - creates nothing more."""
    scenario = (
        Scenario()
        .player("bob", library=list(LIBRARY))
        .player("alice", hand=["Chancellor of the Forge"], library=list(LIBRARY))
        .build()
    )
    will_reveal(scenario, "alice", "Chancellor of the Forge")

    to_first_upkeep(scenario)
    scenario.pass_until_resolved()
    tokens = len(scenario.game.battlefield)
    while not (scenario.turn.active_player == "alice" and scenario.step is Step.UPKEEP):
        scenario.advance()
    assert scenario.game.pending_triggers == []
    assert scenario.game.stack_is_empty
    assert len(scenario.game.battlefield) == tokens


def test_the_chancellor_stays_in_hand_after_revealing() -> None:
    scenario = (
        Scenario()
        .player("alice", hand=["Chancellor of the Forge"], library=list(LIBRARY))
        .player("bob", library=list(LIBRARY))
        .build()
    )
    will_reveal(scenario, "alice", "Chancellor of the Forge")

    to_first_upkeep(scenario)
    scenario.pass_until_resolved()

    assert [state.name for state in scenario.player("alice").hand] == ["Chancellor of the Forge"]
