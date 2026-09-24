"""Casting a modal double-faced card as its instant or sorcery back face
(CR 712.11b).

CR 712.11: "A double-faced spell is cast with its front face up by default."
CR 712.11b: "A player casting a modal double-faced card or a copy of a modal
double-faced card as a spell chooses which face they are casting before
putting it onto the stack." CR 712.11c: "Only the face that will be face up
on the stack is evaluated to determine if it can be cast. Only that face is
considered to be put onto the stack."

CR 712.8f: "While a modal double-faced spell is on the stack or a modal
double-faced permanent is on the battlefield, it has only the characteristics
of the face that's up." CR 712.8a: "While a double-faced card is outside the
game or in a zone other than the battlefield or stack, it has only the
characteristics of its front face."

Before this, `machines/casting.castable_faces` offered a modal double-faced
card nothing but its front face, so Flamescroll Celebrant // Revel in
Silence's instant half could never be cast at all. Every other legal
Modern/Pioneer/Standard modal double-faced card with a creature or artifact
front and an instant or sorcery back (Torrent Sculptor, Selfless
Glyphweaver, Pestilent Cauldron, Blex, Augmenter Pugilist, Wandering Archaic,
Extus, Jadzi) carries a back-face spell this engine does not yet read, so
the rule is proven on the listed card's corner cases instead.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote it.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from magic_cards_model.models.card import Type
from tests.scenarios.harness import Scenario

CELEBRANT = "Flamescroll Celebrant"
CELEBRANT_CARD = "Flamescroll Celebrant // Revel in Silence"
REVEL = "Revel in Silence"


def board():
    return (
        Scenario()
        .player("bob", battlefield=["Mountain"])
        .player("alice", hand=[CELEBRANT_CARD], battlefield=["Plains", "Plains", "Mountain"])
        .build()
    )


def test_the_back_face_is_cast_at_instant_speed_for_its_own_cost() -> None:
    """On Bob's turn Alice may cast the instant face (CR 712.11c evaluates
    only it), paying {W}{W} - not the creature's {1}{R}."""
    scenario = board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("bob")

    casting = scenario.cast(CELEBRANT, "alice")
    casting.cast_as_split_half(REVEL)
    assert str(casting.base_cost) == "{W}{W}"
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains", "Plains", username="alice"))
    spell = scenario.put_on_stack(casting)

    assert spell.zone is Zone.STACK
    assert spell.name == REVEL
    assert spell.types == (Type.INSTANT,)


def test_the_front_face_is_still_refused_at_instant_speed() -> None:
    """The creature face keeps its own timing (CR 117.1a): naming no face
    on Bob's turn is refused even though the instant face is not."""
    scenario = board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("bob")

    casting = scenario.cast(CELEBRANT, "alice")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains", "Mountain", username="alice"))
    with pytest.raises(ValueError, match="main phase"):
        casting.cast()


def test_the_front_face_is_the_default_cast() -> None:
    """CR 712.11: naming no face casts the creature, which resolves onto the
    battlefield as Flamescroll Celebrant."""
    scenario = (
        Scenario()
        .player("alice", hand=[CELEBRANT_CARD], battlefield=["Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    celebrant = scenario.cast_and_resolve(
        CELEBRANT, *scenario.untapped_sources("Mountain", "Mountain")
    )

    assert celebrant.zone is Zone.BATTLEFIELD
    assert celebrant.name == CELEBRANT


def test_a_land_face_is_never_offered_as_a_cast() -> None:
    """CR 712.12: a land face is played, never cast - Valakut Awakening's
    back face is not a cast option."""
    from magic_cards_model.machines.casting import castable_faces
    from tests.cards import card

    assert castable_faces(card("Valakut Awakening // Valakut Stoneforge")) == (None,)
    assert castable_faces(card(CELEBRANT_CARD)) == (None, REVEL)


def test_legal_actions_offer_only_the_back_face_at_instant_speed() -> None:
    scenario = board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("bob")
    celebrant = scenario.find(CELEBRANT, Zone.HAND, "alice")

    faces = {
        action.spell_face
        for action in scenario.game.legal_actions("alice")
        if action.kind is ActionKind.CAST and action.card_id == celebrant.id
    }

    assert faces == {REVEL}


def test_legal_actions_offer_both_faces_in_a_main_phase() -> None:
    scenario = (
        Scenario()
        .player("alice", hand=[CELEBRANT_CARD], battlefield=["Plains", "Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    celebrant = scenario.find(CELEBRANT, Zone.HAND, "alice")

    faces = {
        action.spell_face
        for action in scenario.game.legal_actions("alice")
        if action.kind is ActionKind.CAST and action.card_id == celebrant.id
    }

    assert faces == {None, REVEL}
