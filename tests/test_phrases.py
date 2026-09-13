"""The shared indefinite-article builder for generated noun phrases (battle report
B6-10: Karn, the Great Creator's -2 prompted "reveal a artifact card").

Every case below is a sound the printed rules text actually uses, checked
against Scryfall full-text search in the session that wrote this file:
"an Aura", "an Elf", "an untapped", "an X/X", "an 8/8", "an Urza's",
"a one-", "a Unicorn", "a unique".
"""

import pytest

from magic_cards_model.phrases import indefinite_article, with_indefinite_article


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("artifact card", "an artifact card"),
        ("Aura", "an Aura"),
        ("creature", "a creature"),
        ("enchantment card", "an enchantment card"),
        ("instant or sorcery card", "an instant or sorcery card"),
        ("Equipment", "an Equipment"),
        ("Elf", "an Elf"),
        ("Island", "an Island"),
        ("Ox", "an Ox"),
        ("untapped creature", "an untapped creature"),
        ("Urza's land", "an Urza's land"),
        ("X/X", "an X/X"),
        ("8/8", "an 8/8"),
        ("1/1", "a 1/1"),
        ("one-mana spell", "a one-mana spell"),
        ("Unicorn", "a Unicorn"),
        ("unique card", "a unique card"),
        ("Human", "a Human"),
        ("noncreature artifact", "a noncreature artifact"),
        ("basic land card", "a basic land card"),
        ("green creature card", "a green creature card"),
    ],
)
def test_the_article_follows_the_sound_of_the_first_word(phrase, expected):
    assert with_indefinite_article(phrase) == expected
    assert indefinite_article(phrase) == expected.split(" ", 1)[0]
