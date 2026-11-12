"""Scenario: "Create a tapped token that's a copy of target `<token>`" - the
tapped slot of `_CREATE_TOKEN_COPY_OF_TARGET_RE` (`machines/effects/tokens.py`),
which hands `tapped=True` to `token_copy_of` (`models/token.py`).

Replicator is the reported card: "{2}, {T}: Create a tapped token that's a copy
of target token you control." The untapped sentence ("Create a token that's a
copy of target token you control.") was already read; the only new word is the
one between "a" and "token".

No non-trk printing says "create a tapped token that's a copy of target" (a
Scryfall search for the phrase found only Replicator), so generality is shown
inside the set, by varying the board the way the T-110 batches did: a Food
token, a Treasure token (its own sacrifice ability must work on the copy), a
creature token, a token that is itself a copy of a creature, and a token
carrying a counter. The untapped neighbours, Esika's Chariot (a triggered
"copy of target token you control") and Kambal (the for-each copy with its own
tapped slot), stay green as regression proofs of the shared machinery.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 707.2** - a copy gets the copiable values of the original; "Other
  effects ..., status, counters, and stickers are not copied".
- **CR 701.7a** - to create a token, put it onto the battlefield with the
  stated characteristics.
- **CR 111.3** - a token's stated characteristics are its copiable values, so
  a copy of a token works.
- **CR 602.2** - the activation: the cost ({2} and {T}) is paid, and the
  target must be a token you control.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import (
    PREDEFINED,
    TokenDefinition,
    create_tokens,
    token_copy_of,
)
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario

GOBLIN = TokenDefinition(subtypes=("Goblin",), colors=(Color.RED,), power=1, toughness=1)


def _board(*, alice_extra=(), bob=(), hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=["Replicator", "Mountain", "Mountain", *alice_extra],
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _activate(scenario, target):
    replicator = scenario.find("Replicator", Zone.BATTLEFIELD, "alice")
    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.activate(replicator, *sources, targets=[target])
    scenario.resolve_top()
    return replicator


def _tokens(scenario, name, controller="alice"):
    return [
        s
        for s in scenario.game.battlefield
        if s.token and s.name == name and s.controller == controller
    ]


def test_replicator_ability_is_handled():
    clauses = [c for c in classify_clauses(card("Replicator")) if "copy of target" in c.text]
    assert [c.category for c in clauses] == [HANDLED], clauses


def test_replicator_copies_a_food_token_and_the_copy_enters_tapped():
    scenario = _board()
    (food,) = create_tokens(scenario.game, PREDEFINED["Food"], "alice")
    replicator = _activate(scenario, food)

    foods = _tokens(scenario, "Food Token")
    assert len(foods) == 2
    (copy,) = [f for f in foods if f.id != food.id]
    assert copy.tapped, "the copy enters tapped"
    assert not food.tapped, "the original token is untouched"
    assert replicator.tapped, "the {T} in the cost"
    assert copy.card.oracle_text == food.card.oracle_text, "CR 707.2: same copiable values"


def test_the_copy_of_a_treasure_token_keeps_its_ability_but_enters_tapped():
    """CR 707.2: the abilities come with the copiable values, so the copy is a
    Treasure whose ability needs {T}; it entered tapped, so it cannot be
    sacrificed for mana yet, while the untapped original still can."""
    scenario = _board()
    (treasure,) = create_tokens(scenario.game, PREDEFINED["Treasure"], "alice")
    _activate(scenario, treasure)

    (copy,) = [t for t in _tokens(scenario, treasure.name) if t.id != treasure.id]
    assert copy.tapped
    assert copy.card.oracle_text == treasure.card.oracle_text
    with pytest.raises(ValueError, match="already tapped"):
        scenario.activate(copy, color=Color.RED)
    scenario.activate(treasure, color=Color.RED)
    assert treasure.zone is Zone.GRAVEYARD or treasure not in scenario.game.battlefield


def test_the_copy_of_a_creature_token_is_a_tapped_creature_with_the_same_stats():
    scenario = _board()
    (goblin,) = create_tokens(scenario.game, GOBLIN, "alice")
    _activate(scenario, goblin)

    goblins = _tokens(scenario, goblin.name)
    assert len(goblins) == 2
    (copy,) = [g for g in goblins if g.id != goblin.id]
    assert copy.tapped
    assert (copy.power, copy.toughness) == (1, 1)


def test_counters_and_other_status_of_the_original_are_not_copied():
    """CR 707.2: "status, counters ... are not copied" - only the copy's
    tapped status is the effect's own."""
    scenario = _board()
    (goblin,) = create_tokens(scenario.game, GOBLIN, "alice")
    scenario.game.add_counters(goblin, Counter.PLUS_ONE, 2)
    assert (goblin.power, goblin.toughness) == (3, 3)
    _activate(scenario, goblin)

    (copy,) = [g for g in _tokens(scenario, goblin.name) if g.id != goblin.id]
    assert (copy.power, copy.toughness) == (1, 1)
    assert Counter.PLUS_ONE not in copy.counters


def test_a_token_that_is_a_copy_of_a_creature_copies_as_that_creature():
    """CR 111.4 / 707.2: a token copy of Grizzly Bears is named Grizzly Bears;
    copying it again gives a second tapped Grizzly Bears token."""
    scenario = _board(alice_extra=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    (first,) = token_copy_of(scenario.game, bears, "alice")
    assert first.token
    _activate(scenario, first)

    tokens = _tokens(scenario, "Grizzly Bears")
    assert len(tokens) == 2
    (second,) = [t for t in tokens if t.id != first.id]
    assert second.tapped
    assert not first.tapped


def test_the_target_must_be_a_token():
    """A nontoken permanent is not a legal target (CR 115.1 / 602.2b)."""
    scenario = _board(alice_extra=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    replicator = scenario.find("Replicator", Zone.BATTLEFIELD, "alice")
    sources = scenario.untapped_sources("Mountain", "Mountain")
    with pytest.raises(ValueError, match="needs a token"):
        scenario.activate(replicator, *sources, targets=[bears])
    assert not _tokens(scenario, "Grizzly Bears")


def test_the_target_must_be_a_token_you_control():
    scenario = _board()
    (theirs,) = create_tokens(scenario.game, GOBLIN, "bob")
    replicator = scenario.find("Replicator", Zone.BATTLEFIELD, "alice")
    sources = scenario.untapped_sources("Mountain", "Mountain")
    with pytest.raises(ValueError, match="needs a permanent alice controls"):
        scenario.activate(replicator, *sources, targets=[theirs])
    assert not _tokens(scenario, theirs.name, "alice")


def test_the_whole_card_cast_then_copy_its_own_food():
    """Cast Replicator, its enters trigger makes a Food token, and the ability
    (a noncreature artifact has no summoning sickness, CR 302.6 is about
    creatures) copies that Food tapped."""
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Replicator"], battlefield=["Mountain"] * 4, library=["Mountain"] * 5
        )
        .player("bob", library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Replicator", *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.resolve_top()  # the enters trigger: a Food token
    (food,) = _tokens(scenario, "Food Token")
    _activate(scenario, food)

    foods = _tokens(scenario, "Food Token")
    assert len(foods) == 2
    assert sorted(f.tapped for f in foods) == [False, True]
