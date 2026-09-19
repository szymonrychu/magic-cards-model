"""`machines/abilities.self_reference_names`/`self_normalized_effect_text`:
CR 201.5/201.5c's shortened self-reference, read generally rather than for
"the"-epithets alone.

Every card here is a real Scryfall printing from `tests/cards.card`. The
corner cases are the point of the file: an "of"-epithet legend (Kiora of Fire
and Ashes, Koth of the Homestead, Kiora of Salt and Sand), a bare two-word
legend with no epithet word at all (Ajani Resolute), and the two regressions
a naive "shorten the first word" rule would reintroduce - Hanweir
Battlements' own first word colliding with two *other* cards' names inside
its own text, and The Millennium Calendar's own leading word being the
article "the" itself.

CR numbers looked up with `knowledge_search(type="rules")` in the session
that wrote this file:

- **CR 201.5** - "Text that refers to the object it's on by name means just
  that particular object."
- **CR 201.5c** - "Text printed on some cards refers to that card by a
  shortened version of its name. Instances of a card's shortened name used in
  this manner are treated as though they used the card's full name."
"""

from magic_cards_model.machines.abilities import self_normalized_effect_text, self_reference_names
from tests.cards import card


def test_an_of_epithet_legend_shortens_to_its_first_word():
    """ "Kiora of Fire and Ashes" -> "Kiora", the same way an existing "the"
    epithet already shortens "Liliana the Repentant" -> "Liliana"."""
    names = self_reference_names("Kiora of Fire and Ashes")

    assert "Kiora" in names
    assert self_normalized_effect_text("Kiora of Fire and Ashes", "When Kiora enters, ...") == (
        "When this permanent enters, ..."
    )


def test_koth_of_the_homestead_shortens_to_koth():
    names = self_reference_names(card("Koth of the Homestead").name)

    assert "Koth" in names


def test_kiora_of_salt_and_sand_shortens_to_kiora():
    names = self_reference_names(card("Kiora of Salt and Sand").name)

    assert "Kiora" in names


def test_a_bare_two_word_legend_shortens_to_its_first_word():
    """ "Ajani Resolute" has no comma and no "the"/"of" epithet word at all -
    CR 201.5c's own bare short form is just the first word."""
    names = self_reference_names("Ajani Resolute")

    assert "Ajani" in names
    assert (
        self_normalized_effect_text("Ajani Resolute", "put a loyalty counter on Ajani.")
        == "put a loyalty counter on this permanent."
    )


def test_hanweir_battlements_does_not_shorten_to_its_first_word():
    """The regression a naive "shorten the first word" rule would
    reintroduce: Hanweir Battlements' own text names two *other* cards
    sharing its first word ("a creature named Hanweir Garrison", "meld them
    into Hanweir, the Writhing Township") - neither is this card naming
    itself, and normalizing either would corrupt an unrelated reference."""
    battlements = card("Hanweir Battlements")

    normalized = self_normalized_effect_text(battlements.name, battlements.oracle_text)

    assert "Hanweir Garrison" in normalized
    assert "Hanweir, the Writhing Township" in normalized
    assert "this permanent" not in normalized


def test_a_name_beginning_with_the_article_never_shortens_to_it():
    """The Millennium Calendar's own leading word is the article "the"
    itself - never a valid CR 201.5c short form on its own."""
    calendar = card("The Millennium Calendar")

    names = self_reference_names(calendar.name)
    assert "The" not in names

    normalized = self_normalized_effect_text(calendar.name, calendar.oracle_text)
    # Every full repetition of the card's own name normalizes...
    assert "The Millennium Calendar" not in normalized
    # ...but an ordinary "the" elsewhere in its own text is untouched.
    assert "Double the number of time counters" in normalized


def test_liliana_the_repentant_still_shortens_to_liliana():
    """The pre-existing "the"-epithet case, kept green as a regression guard
    alongside the new "of" and bare-short shapes."""
    liliana = card("Liliana the Repentant")

    normalized = self_normalized_effect_text(liliana.name, liliana.oracle_text)

    assert "Put a +1/+1 counter on this permanent." in normalized
