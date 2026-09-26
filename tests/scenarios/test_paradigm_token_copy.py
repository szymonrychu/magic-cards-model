"""Scenario: Echocasting Symposium - a Paradigm spell whose body is "Target
player creates a token that's a copy of target creature you control."

CR 702.192a: "Paradigm represents two spell abilities, one of which creates a
delayed triggered ability. Paradigm means 'If this is the first time a spell
you control with this spell's name has resolved this game, at the beginning
of each of your precombat main phases for the rest of the game, create a copy
of this object in exile. You may cast the copy without paying its mana cost'
and 'Exile this spell.'" `test_paradigm.py` proves the keyword's machine;
this file proves the body resolves - on the cast and on every free copy.

CR 111.2: the player the instruction names creates the token, so that player
owns and controls it. CR 707.2: the token takes the copiable values of the
targeted creature - not its counters. CR 608.2b: with the creature target
gone the spell still resolves for the player target, and nothing is
created, since the token's copiable values come from the illegal target.

Generality: "a token that's a copy of target creature you control" is read
by the same `token_copy_of` path as Cackling Counterpart (Modern) - "Create
a token that's a copy of target creature you control." - proven here side by
side. "Target player creates a token that's a copy of ..." itself is printed
on Echocasting Symposium alone in Modern, Pioneer and Standard (a Scryfall
search for the phrase returns only it), so its player target is proven on
both kinds of player it can name: the caster and an opponent.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import is_token
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

SYMPOSIUM = "Echocasting Symposium"


def run_to_next_precombat_main(scenario: PlayedScenario, username: str) -> None:
    turns = scenario.turn.turns_taken
    while not (
        scenario.turn.turns_taken > turns
        and scenario.step is Step.PRECOMBAT_MAIN
        and scenario.game.active_player.username == username
    ):
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
        scenario.advance()


def _board(alice_creatures: list[str], bob_creatures: list[str] | None = None) -> PlayedScenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[SYMPOSIUM],
            battlefield=["Island"] * 6 + alice_creatures,
            library=["Island"] * 10,
        )
        .player("bob", battlefield=bob_creatures or [], library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _copies(scenario: PlayedScenario, name: str, username: str) -> list:
    return [
        state
        for state in scenario.game.permanents_controlled_by(username)
        if is_token(state) and state.name == name
    ]


def test_you_create_a_token_copy_of_your_creature():
    scenario = _board(["Serra Angel"])
    angel = scenario.creature("Serra Angel")

    symposium = scenario.cast_and_resolve(
        SYMPOSIUM, *scenario.untapped_sources(*["Island"] * 6), targets=["alice", angel]
    )

    (token,) = _copies(scenario, "Serra Angel", "alice")
    computed = scenario.game.characteristics_of(token)
    assert (computed.power, computed.toughness) == (4, 4)
    assert token.owner == "alice"
    assert symposium.zone is Zone.EXILE, "CR 702.192a: Exile this spell."


def test_the_opponent_can_be_the_player_who_creates_the_copy():
    """CR 111.2: the named player creates, owns and controls it."""
    scenario = _board(["Serra Angel"])
    angel = scenario.creature("Serra Angel")

    scenario.cast_and_resolve(
        SYMPOSIUM, *scenario.untapped_sources(*["Island"] * 6), targets=["bob", angel]
    )

    assert _copies(scenario, "Serra Angel", "alice") == []
    (token,) = _copies(scenario, "Serra Angel", "bob")
    assert token.owner == "bob"


def test_an_opponents_creature_is_not_a_legal_target():
    scenario = _board([], ["Serra Angel"])
    angel = scenario.creature("Serra Angel", "bob")

    casting = scenario.cast(SYMPOSIUM, "alice")
    with pytest.raises(ValueError):
        casting.choose_targets(["alice", angel])


def test_the_copy_does_not_take_the_originals_counters():
    """CR 707.2: counters are not copied."""
    scenario = _board(["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 2)

    scenario.cast_and_resolve(
        SYMPOSIUM, *scenario.untapped_sources(*["Island"] * 6), targets=["alice", bears]
    )

    (token,) = _copies(scenario, "Grizzly Bears", "alice")
    assert token.counters[Counter.PLUS_ONE] == 0
    assert scenario.game.characteristics_of(token).power == 2


def test_with_the_creature_gone_nothing_is_created():
    """CR 608.2b: the player target is still legal, so the spell resolves -
    and is still exiled - but the illegal creature gives nothing to copy."""
    scenario = _board(["Serra Angel"])
    angel = scenario.creature("Serra Angel")

    symposium = scenario.cast_onto_stack(
        SYMPOSIUM, *scenario.untapped_sources(*["Island"] * 6), targets=["alice", angel]
    )
    scenario.game.destroy(angel)
    scenario.resolve_top()

    assert _copies(scenario, "Serra Angel", "alice") == []
    assert symposium.zone is Zone.EXILE


def test_the_free_paradigm_copy_makes_another_token():
    """CR 702.192a: the copy cast at the next precombat main resolves the same
    body, with new targets."""
    scenario = _board(["Serra Angel", "Grizzly Bears"])
    angel = scenario.creature("Serra Angel")
    bears = scenario.creature("Grizzly Bears")
    scenario.cast_and_resolve(
        SYMPOSIUM, *scenario.untapped_sources(*["Island"] * 6), targets=["alice", angel]
    )
    scenario.will_take_the_may(True, username="alice", times=None)
    scenario.will_choose_targets("alice", bears, username="alice", times=None)

    run_to_next_precombat_main(scenario, "alice")
    scenario.pass_until_resolved()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert len(_copies(scenario, "Serra Angel", "alice")) == 1
    assert len(_copies(scenario, "Grizzly Bears", "alice")) == 1


def test_cackling_counterpart_reads_the_subjectless_twin():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Cackling Counterpart"], battlefield=["Island"] * 3 + ["Serra Angel"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel")

    scenario.cast_and_resolve(
        "Cackling Counterpart", *scenario.untapped_sources(*["Island"] * 3), targets=[angel]
    )

    assert len(_copies(scenario, "Serra Angel", "alice")) == 1
