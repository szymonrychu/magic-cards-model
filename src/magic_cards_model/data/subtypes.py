"""CR 205.3's subtypes, and reading a printed plural back to one of them.

A type line prints a subtype in the singular - "Creature - Elemental Shaman",
"Artifact - Equipment" (CR 205.3b, looked up this session: "Subtypes of each
card type except creature and plane are always single words and are listed
after a long dash"). Rules text does not: a sentence that talks about the
objects rather than about one card prints the plural noun, and "activate
abilities of Elementals" names the same subtype "Elemental" that the type line
prints. Nothing in the game state ever holds the plural, so a parser that keeps
the printed word matches nothing at all.

Singularising an arbitrary word is not something to guess at. English plurals
in Magic's own type list are irregular often enough to sink a suffix rule -
Elves/Elf, Dwarves/Dwarf, Mice/Mouse, Oxen/Ox, Fungi/Fungus, and Myr, Eldrazi
and Merfolk which do not change at all - so this does not singularise. It goes
the other way: every subtype WOTC has printed is bundled here (`subtypes.json`,
written from Scryfall's own catalogs by `scripts/add_subtypes.py`, the same
list CR 205.3g-q prints), each is run through the plural forms English gives a
word of its shape, and the printed word is looked up in the index that builds.
A word that lands on exactly one subtype resolves to it; a word that lands on
none, or on more than one, resolves to **nothing at all** and the caller fails
closed.

That direction matters: the morphology only ever runs on a word already known
to be a subtype, so a rule that is wrong about some word invents an unmatched
plural rather than an unintended subtype, and the fail-closed answer for a word
this cannot place keeps a restriction from being read wider than the card.
"""

import json
from functools import cache
from pathlib import Path

from .. import __file__ as _package_file

SUBTYPES_FILE = Path(_package_file).parent / "data" / "subtypes.json"

_VOWELS = frozenset("aeiou")


@cache
def creature_type_vocabulary() -> frozenset[str]:
    """CR 205.3m's own creature types alone (a "creature type" in card text
    - "choose a creature type", CR 701.6 - never means a land or artifact
    type), title-cased the way a type line and a `CHOOSE_A_QUALITY` answer
    both print one ("Elf", not "elf").
    """
    groups = json.loads(SUBTYPES_FILE.read_text())
    return frozenset(word for word in groups["creature"])


@cache
def subtype_vocabulary() -> frozenset[str]:
    """Every printed subtype, lowercased - CR 205.3's artifact, battle,
    creature, enchantment, land, planeswalker and spell types together.

    One flat set rather than seven: CR 205.3c correlates a subtype to the card
    type it belongs to, but a printed sentence that names one ("Dwarf,
    Equipment, and Saga spells") does not say which list it came from, and the
    object being checked carries its subtypes in one list too.
    """
    groups = json.loads(SUBTYPES_FILE.read_text())
    return frozenset(word.lower() for group in groups.values() for word in group)


def _plural_forms(word: str) -> set[str]:
    """The plurals English gives a word of this shape, minus the word itself.

    Deliberately generous - a form nothing ever prints costs nothing, since
    every candidate is checked against a word that was actually printed - and
    deliberately not the reverse operation: see the module docstring for why
    this runs from the known subtype outwards rather than from the printed
    word inwards.
    """
    forms = {word + "s"}
    if word.endswith("fe"):
        forms.add(word[:-2] + "ves")
    elif word.endswith("f"):
        forms.add(word[:-1] + "ves")
    if word.endswith(("s", "x", "z", "ch", "sh")):
        forms.add(word + "es")
    if len(word) > 1 and word.endswith("y") and word[-2] not in _VOWELS:
        forms.add(word[:-1] + "ies")
    if word.endswith("us"):
        forms.add(word[:-2] + "i")
    if word.endswith("ouse"):
        forms.add(word[:-4] + "ice")
    if word.endswith("ox"):
        forms.add(word + "en")
    return forms - {word}


@cache
def _plural_index() -> dict[str, str]:
    """Printed plural to the one subtype it can only be.

    A form two different subtypes could both produce is left out rather than
    resolved to either. Today's vocabulary produces no such collision at all,
    which is worth having the code say out loud: the day a set adds a subtype
    that collides, that plural stops resolving instead of quietly resolving to
    whichever word sorted first.
    """
    candidates: dict[str, set[str]] = {}
    vocabulary = subtype_vocabulary()
    for subtype in vocabulary:
        for form in _plural_forms(subtype):
            if form in vocabulary:
                continue  # a subtype in its own right; the exact match wins
            candidates.setdefault(form, set()).add(subtype)
    return {form: next(iter(found)) for form, found in candidates.items() if len(found) == 1}


def canonical_subtype(word: str) -> str | None:
    """The subtype `word` names, lowercased, or None if it names none.

    The word as printed wins ("Elemental", "Myr", "Eldrazi" - a subtype whose
    plural is itself needs nothing done to it), then the plural index
    ("Elementals", "Dragons", "Elves"), and then nothing: a word this cannot
    place is not silently kept, because a kept word matches no type line and so
    reads as a restriction that permits nothing while claiming to have been
    understood.
    """
    lowered = word.strip().lower()
    if lowered in subtype_vocabulary():
        return lowered
    return _plural_index().get(lowered)
