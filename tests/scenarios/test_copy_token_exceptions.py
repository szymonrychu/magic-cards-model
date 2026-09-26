"""Scenario: "Create a token that's a copy of target `<permanent>`, except
it's `<characteristics>`." - CR 707.9b's copy exceptions become the token's
copiable values (`machines/effects._CREATE_TOKEN_COPIES_EXCEPT_RE`,
`_read_token_copy_except`, `models.token.token_copy_of`).

Applied Geometry is the reported card: "Create a token that's a copy of
target non-Aura permanent you control, except it's a 0/0 Fractal creature in
addition to its other types. Put six +1/+1 counters on it." - an additive
type exception (CR 205.1b's "in addition to"), a set base P/T, and a
follow-up sentence that puts counters on the token just created.

Croaking Counterpart is the second printing (the CR 707 copy-exception
example card): "Create a token that's a copy of target non-Frog creature,
except it's a 1/1 green Frog." - a *replacing* exception: the colour becomes
green and the creature type becomes Frog alone, with no "in addition to".
Legal in Modern and Pioneer (Scryfall legalities, 2026-09-26) and in no deck
under `magic-cards-model-api/decks/`.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 707.2** - a copy acquires the copiable values of the original; other
  effects, counters and status are not copied.
- **CR 707.9b** - a copy effect that modifies a characteristic as part of
  copying makes the final value part of the copy's copiable values.
- **CR 613.1a** - layer 1: rules and effects that modify copiable values.
- **CR 205.1a** - setting a subtype replaces the old subtypes of that kind.
- **CR 205.1b** - "in addition to its other types" keeps them.
- **CR 122.1a** - a +1/+1 counter adds to power and toughness.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color, Type
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def computed(scenario):
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


def _tokens(scenario, name: str):
    return [s for s in scenario.game.battlefield if s.name == name and s.token]


def _board(*, alice=(), bob=("Grizzly Bears",), hand=("Applied Geometry",)):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=[*alice, "Forest", "Forest", "Island", "Island"],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _geometry(scenario, target) -> None:
    sources = scenario.untapped_sources("Forest", "Forest", "Island", "Island")
    scenario.cast_and_resolve("Applied Geometry", *sources, targets=[target])


def test_both_cards_are_handled() -> None:
    for name in ("Applied Geometry", "Croaking Counterpart"):
        clauses = [c for c in classify_clauses(card(name)) if c.text]
        assert {c.category for c in clauses} == {HANDLED}, name


def test_copying_a_creature_makes_a_6_6_fractal_in_addition_to_its_types() -> None:
    scenario = _board(alice=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")

    _geometry(scenario, bears)

    (token,) = _tokens(scenario, "Grizzly Bears")
    board = computed(scenario).of(token)
    assert (board.power, board.toughness) == (6, 6)
    assert token.counters.counts.get("+1/+1") == 6
    assert set(board.subtypes) == {"Bear", "Fractal"}
    assert Type.CREATURE in board.types
    assert set(board.colors) == {Color.GREEN}


def test_the_exception_is_a_copiable_value() -> None:
    """CR 707.9b: the 0/0 Fractal is printed on the token's own copiable
    card, not a layer effect sitting on top of it."""
    scenario = _board(alice=["Grizzly Bears"])
    _geometry(scenario, scenario.creature("Grizzly Bears", "alice"))

    (token,) = _tokens(scenario, "Grizzly Bears")

    assert (token.card.power, token.card.toughness) == ("0", "0")
    assert "Fractal" in token.card.type_line
    assert "Bear" in token.card.type_line


def test_copying_a_noncreature_artifact_makes_it_an_artifact_creature() -> None:
    """CR 205.1b: Sol Ring stays an artifact and also becomes a creature."""
    scenario = _board(alice=["Sol Ring"])
    ring = scenario.creature("Sol Ring", "alice")

    _geometry(scenario, ring)

    (token,) = _tokens(scenario, "Sol Ring")
    board = computed(scenario).of(token)
    assert {Type.ARTIFACT, Type.CREATURE} <= set(board.types)
    assert tuple(board.subtypes) == ("Fractal",)
    assert (board.power, board.toughness) == (6, 6)


def test_counters_and_pumps_on_the_original_are_not_copied() -> None:
    """CR 707.2: counters and other effects are not copiable values."""
    scenario = _board(alice=["Grizzly Bears"], hand=("Applied Geometry", "Giant Growth"))
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.counters.add("+1/+1", 2)
    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_and_resolve("Giant Growth", forest, targets=[bears])
    scenario.game.player("alice").mana_pool.add(Color.GREEN)

    sources = scenario.untapped_sources("Forest", "Island", "Island")
    scenario.cast_and_resolve("Applied Geometry", *sources, targets=[bears])

    (token,) = _tokens(scenario, "Grizzly Bears")
    board = computed(scenario).of(token)
    assert (board.power, board.toughness) == (6, 6)
    assert token.counters.counts.get("+1/+1") == 6


def test_an_opponents_permanent_is_not_a_legal_target() -> None:
    """ "target non-Aura permanent you control"."""
    scenario = _board()
    theirs = scenario.creature("Grizzly Bears", "bob")

    with pytest.raises(ValueError):
        scenario.cast("Applied Geometry", targets=[theirs])


def test_an_aura_is_not_a_legal_target() -> None:
    scenario = _board(alice=["Grizzly Bears", "Rancor"])
    rancor = scenario.creature("Rancor", "alice")

    with pytest.raises(ValueError):
        scenario.cast("Applied Geometry", targets=[rancor])


def test_nothing_is_created_if_the_target_left() -> None:
    scenario = _board(alice=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Island", "Island")
    scenario.cast_onto_stack("Applied Geometry", *sources, targets=[bears])
    scenario.game.put_into_graveyard(bears)

    scenario.resolve_top()

    assert _tokens(scenario, "Grizzly Bears") == []


# -- Croaking Counterpart: a replacing exception ---------------------------


def _croak(scenario, target) -> None:
    sources = scenario.untapped_sources("Forest", "Island", "Island")
    scenario.cast_and_resolve("Croaking Counterpart", *sources, targets=[target])


def test_croaking_counterpart_makes_a_1_1_green_frog_copy() -> None:
    scenario = _board(bob=["Serra Angel"], hand=("Croaking Counterpart",))
    angel = scenario.creature("Serra Angel", "bob")

    _croak(scenario, angel)

    (token,) = _tokens(scenario, "Serra Angel")
    board = computed(scenario).of(token)
    assert token.controller == "alice"
    assert (board.power, board.toughness) == (1, 1)
    assert set(board.colors) == {Color.GREEN}
    assert tuple(board.subtypes) == ("Frog",)
    assert Type.CREATURE in board.types


def test_croaking_counterpart_keeps_the_copied_abilities() -> None:
    """Only P/T, colour and creature type are excepted: flying and
    vigilance are copied (CR 707.2)."""
    scenario = _board(bob=["Serra Angel"], hand=("Croaking Counterpart",))
    _croak(scenario, scenario.creature("Serra Angel", "bob"))

    (token,) = _tokens(scenario, "Serra Angel")

    assert {"Flying", "Vigilance"} <= set(token.card.keywords)
    assert token.card.colors == [Color.GREEN]


def test_croaking_counterpart_cannot_target_a_frog() -> None:
    """ "target non-Frog creature" - its own Frog token is not a legal target."""
    scenario = _board(bob=["Serra Angel"], hand=("Croaking Counterpart",))
    _croak(scenario, scenario.creature("Serra Angel", "bob"))
    (frog,) = _tokens(scenario, "Serra Angel")
    scenario.game.return_to_hand(scenario.find("Croaking Counterpart", Zone.GRAVEYARD, "alice"))
    for land in scenario.game.battlefield:
        land.tapped = False

    with pytest.raises(ValueError):
        scenario.cast("Croaking Counterpart", targets=[frog])
