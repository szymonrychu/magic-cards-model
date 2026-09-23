"""A copy of a permanent spell becomes a token as it resolves.

CR 707.10f: "Some effects copy a permanent spell. As that copy resolves, it
ceases being a copy of a spell and becomes a token permanent. (See rule
608.3f.)"

CR 111.13: "A copy of a permanent spell becomes a token as it resolves. The
token has the characteristics of the spell that became that token."

CR 111.7: "A token that's in a zone other than the battlefield ceases to
exist." CR 111.8: "A token that has left the battlefield can't move to another
zone or come back onto the battlefield."

Drafna, Founder of Lat-Nam ("{3}, {T}: Copy target artifact spell you control.
(The copy becomes a token.)") is the listed card: an activated ability that
copies a spell it targets, restricted by type ("artifact spell") and by
controller ("you control", CR 115.1c, checked as the ability is activated, CR
602.2b). Jin-Gitaxias, Progress Tyrant ("Whenever you cast an artifact,
instant, or sorcery spell, copy that spell. ... (A copy of a permanent spell
becomes a token.)") is the second printing: a different copy path (a cast
trigger's "that spell") reaching the same CR 707.10f resolution.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file (CR 707.10, 707.10f, 608.3f, 111.13, 111.7, 111.8,
115.1c, 602.2b, 608.2b).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from magic_cards_model.models.card_state import CardState
from magic_cards_model.models.token import is_token
from tests.scenarios.harness import Scenario

_DRAFNA_BOUNCE = 0
_DRAFNA_COPY = 1


def _board(alice_hand: list[str], bob_hand: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=alice_hand,
            battlefield=["Drafna, Founder of Lat-Nam"] + ["Island"] * 6,
            library=["Island"] * 10,
        )
        .player(
            "bob",
            hand=bob_hand or [],
            battlefield=["Mountain", "Mountain"],
            library=["Mountain"] * 10,
        )
    )


def _copy_with_drafna(scenario, target: CardState):
    drafna = scenario.creature("Drafna, Founder of Lat-Nam", "alice")
    mana = scenario.untapped_sources("Island", "Island", "Island", username="alice")
    return scenario.activate(drafna, *mana, index=_DRAFNA_COPY, username="alice", targets=[target])


def _tokens(scenario, name: str, controller: str = "alice") -> list[CardState]:
    return [
        state
        for state in scenario.game.battlefield
        if state.name == name and state.controller == controller and is_token(state)
    ]


def _nontokens(scenario, name: str, controller: str = "alice") -> list[CardState]:
    return [
        state
        for state in scenario.game.battlefield
        if state.name == name and state.controller == controller and not is_token(state)
    ]


def test_drafna_copy_of_an_artifact_spell_resolves_as_a_token():
    """CR 707.10f/111.13: the copy of Sol Ring resolves first as a token Sol
    Ring, then the original resolves as the card. Alice has one of each."""
    scenario = _board(["Sol Ring"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (one,) = scenario.untapped_sources("Island", username="alice")
    sol_ring = scenario.cast_onto_stack("Sol Ring", one, username="alice")

    _copy_with_drafna(scenario, sol_ring)
    scenario.resolve_top()  # Drafna's ability
    assert scenario.stack_names() == ["Sol Ring", "Sol Ring"]
    (copy,) = [item for item in scenario.game.stack if item.id != sol_ring.id]
    assert copy.is_copy
    assert not is_token(copy), "CR 707.10f: a token only as it resolves"

    scenario.resolve_top()  # the copy
    assert len(_tokens(scenario, "Sol Ring")) == 1
    scenario.resolve_top()  # the original
    assert len(_nontokens(scenario, "Sol Ring")) == 1
    assert sol_ring.zone is Zone.BATTLEFIELD


def test_drafna_copy_of_an_artifact_creature_spell_is_a_creature_token():
    """CR 111.13: "The token has the characteristics of the spell that became
    that token" - a copy of Memnite is a 1/1 artifact creature token."""
    scenario = _board(["Memnite"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.cast_onto_stack("Memnite", username="alice")

    _copy_with_drafna(scenario, memnite)
    scenario.resolve_top()  # Drafna's ability
    scenario.resolve_top()  # the copy

    (token,) = _tokens(scenario, "Memnite")
    characteristics = scenario.game.characteristics_of(token)
    assert Type.ARTIFACT in characteristics.types
    assert Type.CREATURE in characteristics.types
    assert (characteristics.power, characteristics.toughness) == (1, 1)


def test_drafna_cannot_target_an_opponents_artifact_spell():
    """ "Artifact spell you control": on bob's own turn, bob's Memnite is
    refused as the target of alice's Drafna (CR 115.1c)."""
    scenario = (
        Scenario()
        .player("bob", hand=["Memnite"], battlefield=["Mountain"], library=["Mountain"] * 10)
        .player(
            "alice",
            battlefield=["Drafna, Founder of Lat-Nam"] + ["Island"] * 3,
            library=["Island"] * 10,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.cast_onto_stack("Memnite", username="bob")
    scenario.pass_priority("bob")

    with pytest.raises(ValueError):
        _copy_with_drafna(scenario, memnite)
    assert scenario.stack_names() == ["Memnite"]


def test_drafna_cannot_target_a_nonartifact_spell():
    """ "Artifact spell": alice's own Opt is the wrong type and is refused."""
    scenario = _board(["Opt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (blue,) = scenario.untapped_sources("Island", username="alice")
    opt = scenario.cast_onto_stack("Opt", blue, username="alice")

    with pytest.raises(ValueError):
        _copy_with_drafna(scenario, opt)
    assert scenario.stack_names() == ["Opt"]


def test_drafna_ability_does_nothing_when_the_artifact_spell_is_gone():
    """CR 608.2b: bob counters the Sol Ring in response; the ability's only
    target is illegal, it is removed, and no token is made."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sol Ring"],
            battlefield=["Drafna, Founder of Lat-Nam"] + ["Island"] * 4,
        )
        .player("bob", hand=["Counterspell"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (one,) = scenario.untapped_sources("Island", username="alice")
    sol_ring = scenario.cast_onto_stack("Sol Ring", one, username="alice")
    ability = _copy_with_drafna(scenario, sol_ring)

    scenario.pass_priority("alice")
    counters = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Counterspell", *counters, username="bob", targets=[sol_ring])
    scenario.resolve_top()  # Counterspell
    scenario.resolve_top()  # Drafna's ability

    assert ability.id in scenario.game.fizzled
    assert _tokens(scenario, "Sol Ring") == []


def test_bounced_token_copy_ceases_to_exist():
    """CR 111.7/111.8: Drafna's own "{1}{U}: Return target artifact you
    control to its owner's hand" sends the token Sol Ring to a hand, where it
    ceases to exist at the next state-based action check; it never becomes a
    card alice can recast."""
    scenario = _board(["Sol Ring"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (one,) = scenario.untapped_sources("Island", username="alice")
    sol_ring = scenario.cast_onto_stack("Sol Ring", one, username="alice")
    _copy_with_drafna(scenario, sol_ring)
    scenario.resolve_top()  # Drafna's ability
    scenario.resolve_top()  # the copy
    scenario.resolve_top()  # the original
    (token,) = _tokens(scenario, "Sol Ring")

    drafna = scenario.creature("Drafna, Founder of Lat-Nam", "alice")
    mana = scenario.untapped_sources("Island", "Island", username="alice")
    scenario.activate(drafna, *mana, index=_DRAFNA_BOUNCE, username="alice", targets=[token])
    scenario.resolve_top()
    scenario.state_based_actions()

    assert _tokens(scenario, "Sol Ring") == []
    assert [state.name for state in scenario.player("alice").hand] == []
    assert len(_nontokens(scenario, "Sol Ring")) == 1


def test_second_printing_cast_trigger_copy_of_an_artifact_spell_is_a_token():
    """Jin-Gitaxias, Progress Tyrant's cast trigger copies Sol Ring; the copy
    resolves as a token Sol Ring by the same CR 707.10f rule Drafna's copy
    reaches through an activated ability."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sol Ring"],
            battlefield=["Jin-Gitaxias, Progress Tyrant", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (one,) = scenario.untapped_sources("Island", username="alice")
    scenario.cast_onto_stack("Sol Ring", one, username="alice")
    while scenario.game.stack:
        scenario.resolve_top()

    assert len(_tokens(scenario, "Sol Ring")) == 1
    assert len(_nontokens(scenario, "Sol Ring")) == 1
