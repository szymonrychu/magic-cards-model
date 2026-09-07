import pytest
from pydantic import ValidationError

from magic_cards_model.models.card import Layout, Legality, Rarity, Supertype, Type
from tests.cards import card


def test_parses_a_single_faced_card():
    printing = card("Ragavan, Nimble Pilferer")

    assert printing.name == "Ragavan, Nimble Pilferer"
    assert printing.rarity is Rarity.MYTHIC
    assert printing.layout is Layout.NORMAL
    assert printing.supertypes == [Supertype.LEGENDARY]
    assert printing.types == [Type.CREATURE]
    assert printing.subtypes == ["Monkey", "Pirate"]
    assert printing.power == "2"
    assert printing.legalities.modern is Legality.LEGAL


def test_parses_a_double_faced_card():
    printing = card("Delver of Secrets")

    assert printing.layout is Layout.TRANSFORM
    assert printing.card_faces is not None
    assert [face.name for face in printing.card_faces] == [
        "Delver of Secrets",
        "Insectile Aberration",
    ]
    # Type parsing reads the front face only, never the back half of the `//`.
    assert printing.subtypes == ["Human", "Wizard"]


def test_legalities_are_clamped_to_three_formats():
    printing = card("Ragavan, Nimble Pilferer")

    assert set(printing.legalities.model_dump()) == {"standard", "pioneer", "modern"}
    assert printing.legalities.modern is Legality.LEGAL


def test_parses_a_pre_modern_card():
    """Nothing filters by frame any more, so old printings parse like any other."""
    printing = card("Tinder Farm")

    assert printing.name == "Tinder Farm"
    assert printing.types == [Type.LAND]


def test_card_is_immutable():
    """`Card` is the immutable Scryfall printing - a printing does not change
    once loaded - `frozen=True` in `models/card.py` makes that a pydantic
    guarantee, not just a convention in a docstring nobody checks.

    This is the whole reason `machines/abilities.parse_abilities` and
    `machines/triggers.activated_abilities_of` are safe to memoise on
    `Card.id`: if a `Card` could still be mutated after construction, either
    cache would go stale silently the moment something did, and nothing would
    notice. If this test ever starts failing, both of those caches need to be
    reconsidered before `Card` is allowed to become mutable again.
    """
    printing = card("Ragavan, Nimble Pilferer")

    with pytest.raises(ValidationError, match="frozen"):
        printing.name = "Mutated Pilferer"
    with pytest.raises(ValidationError, match="frozen"):
        printing.oracle_text = "This card now does something else."
    with pytest.raises(ValidationError, match="frozen"):
        printing.type_line = "Sorcery"
