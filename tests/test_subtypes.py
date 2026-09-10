"""CR 205.3's subtype vocabulary, and the printed plural read back to it.

Rules text names the objects ("activate abilities of Elementals") where a type
line names one card ("Creature - Elemental Shaman"), so a CR 106.6 restriction
that quotes a subtype has to be matched against a printed type line through the
plural. English does not make that a suffix rule: Magic's own type list holds
Elves/Elf, Dwarves/Dwarf, Mice/Mouse, Oxen/Ox and Fungi/Fungus alongside Myr
and Eldrazi, which do not change at all.

`magic_cards_model/data/subtypes.json` is the whole list - every subtype WOTC
has printed, fetched from Scryfall's own catalogs by `scripts/add_subtypes.py`,
the same list CR 205.3g-q prints - so nothing here is hand-written data, and
the resolution runs from a known subtype outwards rather than guessing a
singular for an arbitrary word.
"""

import pytest

from magic_cards_model.data.subtypes import canonical_subtype, subtype_vocabulary

# --------------------------------------------------------------------------
# The vocabulary itself
# --------------------------------------------------------------------------


def test_the_vocabulary_covers_every_card_type_that_has_subtypes():
    """CR 205.3g-q: artifact, battle, creature, enchantment, land, planeswalker
    and spell types are seven separate lists, and a printed sentence never says
    which of them it is quoting - so all seven are loaded, not just creature
    types."""
    vocabulary = subtype_vocabulary()

    assert "equipment" in vocabulary  # CR 205.3g, artifact
    assert "siege" in vocabulary  # CR 205.3q, battle
    assert "elemental" in vocabulary  # CR 205.3m, creature
    assert "saga" in vocabulary  # CR 205.3h, enchantment
    assert "cave" in vocabulary  # CR 205.3i, land
    assert "chandra" in vocabulary  # CR 205.3j, planeswalker
    assert "lesson" in vocabulary  # CR 205.3k, spell


# --------------------------------------------------------------------------
# Reading a printed plural
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("printed", "subtype"),
    [
        ("Elementals", "elemental"),  # Smokebraider
        ("Dragons", "dragon"),  # Orb of Dragonkind, Crucible of the Spirit Dragon
        ("Myr", "myr"),  # Myr Reservoir - a plural that is the singular
        ("Eldrazi", "eldrazi"),  # Eldrazi Temple - the same, on a second card
        ("Elves", "elf"),  # -f to -ves
        ("Dwarves", "dwarf"),
        ("Wolves", "wolf"),
        ("Allies", "ally"),  # -y to -ies
        ("Foxes", "fox"),  # -x to -xes
        ("Leeches", "leech"),  # -ch to -ches
        ("Mice", "mouse"),  # and the three English refuses to regularise
        ("Oxen", "ox"),
        ("Fungi", "fungus"),
        ("elemental", "elemental"),  # case is not the signal; the word is
    ],
)
def test_a_printed_plural_resolves_to_the_subtype_it_names(printed: str, subtype: str):
    assert canonical_subtype(printed) == subtype


@pytest.mark.parametrize(
    "printed",
    [
        "Outlaws",  # CR 700.12's defined term, not a subtype - it names five
        "Time",  # half of "Time Lord", the one two-word creature type
        "Permanents",
        "Sources",
        "Elementalses",
    ],
)
def test_a_word_that_names_no_subtype_resolves_to_nothing(printed: str):
    """The fail-closed direction. A word kept as printed would match no type
    line at all, which is a restriction that permits nothing while reporting
    that it was understood - the exact shape of the defect this replaces."""
    assert canonical_subtype(printed) is None
