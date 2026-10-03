"""Protection from a quality, read off oracle text that carries reminder text
(CR 702.16a: the quality "can be any characteristic value or information").

Black Knight prints "Protection from white (This creature can't be blocked,
targeted, dealt damage, enchanted, or equipped by anything white.)" - the CR
reminder in parentheses is not part of the quality, and the quality must be one
every protection reader (CR 702.16b-f) understands. Pinned for the whole family
this covers: plain colours, a colour count, creature-type plurals, a subtype,
a supertype, a mana-value comparator and "God creatures".
"""

import pytest

from magic_cards_model.models.game import protection_qualities, protection_quality_readable
from magic_cards_model.support import card_support
from tests.cards import card

EXPECTED = {
    "Apostle of Purifying Light": ["black"],
    "Baneslayer Angel": ["Demons", "Dragons"],
    "Black Knight": ["white"],
    "Cerulean Drake": ["red"],
    "Grave Bramble": ["Zombies"],
    "Great Sable Stag": ["blue", "black"],
    "Kitsune Riftwalker": ["Spirits", "Arcane"],
    "Midnight Duelist": ["Vampires"],
    "Mistmeadow Skulk": ["mana value 3 or greater"],
    "Nath's Buffoon": ["Elves"],
    "Paladin en-Vec": ["black", "red"],
    "Ronom Hulk": ["snow"],
    "Shifting Ceratops": ["blue"],
    "Sigrid, God-Favored": ["God creatures"],
    "Spectrum Sentinel": ["multicolored"],
    "Warren-Scourge Elf": ["Goblins"],
    "White Knight": ["black"],
    "Yawgmoth, Thran Physician": ["Humans"],
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_the_quality_is_read_without_the_reminder_text(name):
    assert protection_qualities(card(name)) == EXPECTED[name]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_every_quality_of_the_family_is_readable(name):
    assert all(protection_quality_readable(quality) for quality in EXPECTED[name])


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_the_card_is_handled_by_the_support_oracle(name):
    assert card_support(card(name)).status == "handled"
