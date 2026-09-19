"""`machines/abilities.self_reference_names`/`self_normalized_effect_text`:
CR 201.5/201.5c's shortened self-reference, read generally rather than for
"the"-epithets alone.

Every card here is a real Scryfall printing from `tests/cards.card`. The
corner cases are the point of the file: an "of"-epithet legend (Kiora of Fire
and Ashes, Koth of the Homestead, Kiora of Salt and Sand), a bare two-word
legend with no epithet word at all (Ajani Resolute), the two regressions a
naive "shorten the first word" rule would reintroduce - Hanweir Battlements'
own first word colliding with two *other* cards' names inside its own text,
and The Millennium Calendar's own leading word being the article "the"
itself - and a third regression discovered after those: a *possessive*
followed by a longer, unrelated proper noun.

**The possessive-continuation regression.** Ajani Resolute's own `-4` -
"Create a 2/2 white Cat Soldier creature token named Ajani's Pridemate ..." -
used to normalize to "... token named this permanent's Pridemate ...":
`_LONGER_NAME_CONTINUATION_LOOKAHEAD` already refused a candidate followed by
a space-then-capital continuation ("Hanweir Garrison") or a comma-then-
capital one ("Hanweir, the Writhing Township"), but nothing refused one
followed by `'s` then a capitalized continuation - "Ajani's Pridemate" is the
*token's own* fixed name (CR 111.3), not this card naming itself, yet
"Ajani" still matched and "'s Pridemate" rode along for free. An *ordinary*
possessive self-reference must still normalize - Fblthp, Impossibly Lost's
own "Fblthp's owner shuffles him into their library" is exactly CR 201.5c's
short name owning something of its own, not a longer name - so the fix reads
what follows the apostrophe: a lowercase continuation ("owner") is this card
possessing something, a capitalized one ("Pridemate") is a different, longer
proper noun that merely starts with this card's own short name.

CR numbers looked up with `knowledge_search(type="rules")` in the session
that wrote this file:

- **CR 201.5** - "Text that refers to the object it's on by name means just
  that particular object."
- **CR 201.5c** - "Text printed on some cards refers to that card by a
  shortened version of its name. Instances of a card's shortened name used in
  this manner are treated as though they used the card's full name."
- **CR 111.3** - "The spell or ability that creates a token may define the
  values of any number of characteristics for the token. This becomes the
  token's copiable values" - true of a token's own name too, which is why
  "Ajani's Pridemate"/"Selenia's Curse" name the *token*, never the card
  printing the ability.
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


def test_a_tokens_own_possessive_name_is_not_rewritten():
    """The reported defect: Ajani Resolute's own `-4` creates a token named
    "Ajani's Pridemate" - the token's own fixed name (CR 111.3), not this
    card naming itself. "Ajani's" must stay "Ajani's"; only the genuine
    self-reference earlier in the same sentence ("Whenever you gain life,
    put a loyalty counter on Ajani.") normalizes."""
    ajani = card("Ajani Resolute")

    normalized = self_normalized_effect_text(ajani.name, ajani.oracle_text)

    assert "put a loyalty counter on this permanent." in normalized
    assert "Ajani's Pridemate" in normalized
    assert "this permanent's Pridemate" not in normalized


def test_selenias_curse_token_name_is_not_rewritten_off_pool():
    """Off-pool generality proof: Selenia, the Cursed Heart's own dies
    trigger creates a token named "Selenia's Curse" - a comma-shortened name
    (not Ajani Resolute's own bare two-word shape), proving the fix is not
    fitted to one card's own short-name derivation."""
    selenia = card("Selenia, the Cursed Heart")

    normalized = self_normalized_effect_text(selenia.name, selenia.oracle_text)

    assert "When this permanent dies" in normalized
    assert "Selenia's Curse" in normalized
    assert "this permanent's Curse" not in normalized


def test_an_ordinary_possessive_self_reference_still_normalizes():
    """The case the fix must not break: Fblthp, Impossibly Lost's own
    "Fblthp's owner shuffles him into their library" is CR 201.5c's short
    name genuinely possessing something of its own (a lowercase common noun,
    not a longer capitalized proper noun) - it still normalizes."""
    fblthp = card("Fblthp, Impossibly Lost")

    normalized = self_normalized_effect_text(
        fblthp.name, "Fblthp's owner shuffles him into their library."
    )

    assert normalized == "this permanent's owner shuffles him into their library."
