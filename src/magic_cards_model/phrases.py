"""Shared builders for the noun phrases the engine writes into prompts and refusals.

One place decides "a" or "an" so that every generated phrase reads the way the
printed rules text does ("an artifact card", "an Aura", "a creature"), rather
than each prompt guessing from the first letter (battle report B6-10: "reveal a
artifact card"). The article follows the *sound* the phrase starts with, which
the first letter alone gets wrong in both directions for words the rules text
really prints: "a one-mana", "a Unicorn" and "a unique" start with a vowel
letter and a consonant sound; "an X/X" and "an 8/8" start with a consonant
letter or a digit and a vowel sound.
"""

import re

__all__ = ["indefinite_article", "with_indefinite_article"]

#: Vowel letters read with a consonant sound at the start of a word: "one"/
#: "once" (w-), and the "you" sound of "unicorn", "unique", "unit", "use",
#: "usual", "utility", "eulogy", "ewe". "un-" followed by anything else keeps
#: its vowel ("an untapped creature", "an unblocked attacker").
_CONSONANT_SOUNDING_VOWEL = re.compile(
    r"^(?:one\b|one-|once\b|uni(?![nm])|us[eu]|uti|eu|ewe)", re.IGNORECASE
)

#: Consonant letters read with a vowel sound: a silent "h" ("an hour", "an
#: honor", "an heir", "an honest").
_VOWEL_SOUNDING_CONSONANT = re.compile(r"^(?:hour|honou?r|heir|honest)", re.IGNORECASE)

#: A letter standing alone (a variable such as the X of "an X/X"), whose name
#: starts with a vowel sound: A E F H I L M N O R S X.
_VOWEL_SOUNDING_LETTER_NAMES = frozenset("aefhilmnorsx")


def indefinite_article(phrase: str) -> str:
    """ "a" or "an" for `phrase`, by the sound its first word starts with."""
    word = phrase.strip()
    if not word:
        return "a"
    if word[0].isdigit():
        number = re.match(r"\d+", word)
        digits = number.group(0) if number is not None else word[0]
        # "an 8/8", "an 18/18", "an 11/11": eight, eighteen, eleven.
        return "an" if digits.startswith("8") or digits in ("11", "18") else "a"
    if len(word) == 1 or not word[1].isalpha():
        # A lone letter: "an X/X", "an X", "a Y".
        return "an" if word[0].lower() in _VOWEL_SOUNDING_LETTER_NAMES else "a"
    if _CONSONANT_SOUNDING_VOWEL.match(word):
        return "a"
    if _VOWEL_SOUNDING_CONSONANT.match(word):
        return "an"
    return "an" if word[0].lower() in "aeiou" else "a"


def with_indefinite_article(phrase: str) -> str:
    """`phrase` with its indefinite article in front: "an artifact card"."""
    stripped = phrase.strip()
    return f"{indefinite_article(stripped)} {stripped}"
