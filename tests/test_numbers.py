"""The shared count reader every oracle-text parser delegates to.

A pure function over printed words, so it is unit tested here with no card
data, the same way `tests/test_phrases.py` tests the article builder. What a
count *does* on a real card is proven in
`tests/scenarios/test_number_words_beyond_ten.py`.

CR 107.1: "The only numbers the Magic game uses are integers." CR 107.1c: "If
a rule or ability instructs a player to choose 'any number,' that player may
choose any positive number or zero." CR 107.3: "Many objects use the letter X
as a placeholder for a number that needs to be determined." All three looked
up with `mise run rules:find` in the session that wrote this file.
"""

import re

import pytest

from magic_cards_model.numbers import (
    AMOUNT,
    COUNT,
    MULTIPLIER,
    ORDINAL,
    Quantity,
    QuantitySource,
    VariableX,
    count_pattern,
    parse_amount,
    parse_count,
    parse_multiplier,
    parse_ordinal,
    parse_quantity,
    quantity_pattern,
    where_x_pattern,
)


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("a", 1),
        ("an", 1),
        ("one", 1),
        ("zero", 0),
        ("two", 2),
        ("ten", 10),
        ("eleven", 11),
        ("twelve", 12),
        ("thirteen", 13),
        ("seventeen", 17),
        ("twenty", 20),
        ("thirty", 30),
        ("forty", 40),
        ("fifty", 50),
        ("Seven", 7),
        (" three ", 3),
        ("0", 0),
        ("7", 7),
        ("108", 108),
        ("1,000", 1000),
    ],
)
def test_every_count_form_reads_as_its_integer(word, expected):
    assert parse_count(word) == expected


@pytest.mark.parametrize("word", ["x", "X", "that", "many", "your", "twice", "first", "", "1,00"])
def test_a_word_that_is_not_a_count_is_none_never_an_error(word):
    assert parse_count(word) is None


def test_an_article_can_be_refused_where_it_is_not_a_count():
    """ "Choose a color" is not "choose one": a reader whose capture can land on
    an article asks for numbers only."""
    assert parse_count("a", article=False) is None
    assert parse_count("an", article=False) is None
    assert parse_count("one", article=False) == 1


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("four", 4),
        ("x", VariableX()),
        ("X", VariableX()),
        (
            "X, where X is the number of Elves you control",
            VariableX("the number of Elves you control"),
        ),
        ("x, where x is its power", VariableX("its power")),
        ("that", None),
    ],
)
def test_an_amount_is_a_count_or_a_structured_x(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("once", 1),
        ("twice", 2),
        ("thrice", 3),
        ("three times", 3),
        ("four times", 4),
        ("10 times", 10),
        ("Twice", 2),
        ("a time", None),
        ("times", None),
        ("two", None),
    ],
)
def test_a_multiplier_reads_once_twice_and_n_times(text, expected):
    assert parse_multiplier(text) == expected


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("first", 1),
        ("second", 2),
        ("third", 3),
        ("fifth", 5),
        ("sixth", 6),
        ("tenth", 10),
        ("twelfth", 12),
        ("twentieth", 20),
        ("Second", 2),
        ("one", None),
        ("last", None),
    ],
)
def test_an_ordinal_reads_first_through_twentieth(word, expected):
    assert parse_ordinal(word) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("three", Quantity(amount=3, minimum=3, source=QuantitySource.FIXED)),
        ("a", Quantity(amount=1, minimum=1, source=QuantitySource.FIXED)),
        ("up to two", Quantity(amount=2, minimum=0, source=QuantitySource.FIXED)),
        ("up to X", Quantity(amount=None, minimum=0, source=QuantitySource.X)),
        ("X", Quantity(amount=None, minimum=None, source=QuantitySource.X)),
        ("any number of", Quantity(amount=None, minimum=0, source=QuantitySource.ANY_NUMBER)),
        ("one or more", Quantity(amount=None, minimum=1, source=QuantitySource.ONE_OR_MORE)),
        ("that many", Quantity(amount=None, minimum=None, source=QuantitySource.THAT_MANY)),
        ("up to that many", Quantity(amount=None, minimum=0, source=QuantitySource.THAT_MANY)),
        ("some", None),
        ("up to", None),
    ],
)
def test_a_quantity_says_how_many_and_how_exact(text, expected):
    assert parse_quantity(text) == expected


def test_a_quantity_is_exact_only_when_its_minimum_is_its_amount():
    assert parse_quantity("three").exact
    assert not parse_quantity("up to three").exact
    assert not parse_quantity("any number of").exact


@pytest.mark.parametrize(
    "word",
    [
        "a",
        "an",
        "one",
        "nine",
        "eleven",
        "thirteen",
        "seventeen",
        "nineteen",
        "twenty",
        "fifty",
        "7",
        "1,000",
    ],
)
def test_the_count_fragment_matches_every_count_form_whole(word):
    assert re.fullmatch(COUNT, word, re.IGNORECASE)
    assert re.fullmatch(AMOUNT, word, re.IGNORECASE)


def test_the_count_fragment_never_matches_x_but_the_amount_fragment_does():
    assert re.fullmatch(COUNT, "x", re.IGNORECASE) is None
    assert re.fullmatch(AMOUNT, "x", re.IGNORECASE)


def test_a_longer_word_is_never_matched_short():
    """ "seventeen" must not be read as "seven" with "teen" left over, and
    "1,000" not as "1" - the alternation is longest-first."""
    pattern = re.compile(rf"create (?P<n>{COUNT})", re.IGNORECASE)
    assert pattern.match("create seventeen tokens").group("n") == "seventeen"
    assert pattern.match("create 1,000 tokens").group("n") == "1,000"
    assert pattern.match("create an Elf token").group("n") == "an"


def test_the_fragment_builder_names_the_group_and_adds_x_on_request():
    named = re.compile(rf"^mill {count_pattern('n')} cards$", re.IGNORECASE)
    assert named.match("mill thirteen cards").group("n") == "thirteen"
    assert named.match("mill x cards") is None
    with_x = re.compile(rf"^mill {count_pattern('n', x=True)} cards$", re.IGNORECASE)
    assert with_x.match("mill X cards").group("n") == "X"
    no_article = re.compile(rf"^choose {count_pattern('n', article=False)}\b", re.IGNORECASE)
    assert no_article.match("choose a color") is None
    assert no_article.match("choose two").group("n") == "two"


def test_the_where_x_tail_is_read_after_the_counted_noun():
    pattern = re.compile(
        rf"^draw {count_pattern('n', x=True)} cards?{where_x_pattern('expr')}$", re.IGNORECASE
    )
    match = pattern.match("draw X cards, where X is the number of lands you control")
    assert match is not None
    assert match.group("n") == "X"
    assert match.group("expr") == "the number of lands you control"
    assert pattern.match("draw two cards").group("expr") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("up to three", Quantity(amount=3, minimum=0, source=QuantitySource.FIXED)),
        ("any number of", Quantity(amount=None, minimum=0, source=QuantitySource.ANY_NUMBER)),
        ("one or more", Quantity(amount=None, minimum=1, source=QuantitySource.ONE_OR_MORE)),
        ("up to that many", Quantity(amount=None, minimum=0, source=QuantitySource.THAT_MANY)),
        ("thirteen", Quantity(amount=13, minimum=13, source=QuantitySource.FIXED)),
    ],
)
def test_the_quantity_fragment_matches_what_parse_quantity_reads(text, expected):
    match = re.fullmatch(quantity_pattern("q"), text, re.IGNORECASE)
    assert match is not None
    assert parse_quantity(match.group("q")) == expected


@pytest.mark.parametrize(
    ("text", "value"),
    [("twice", 2), ("thrice", 3), ("three times", 3), ("eleven times", 11), ("once", 1)],
)
def test_the_multiplier_fragment_matches_what_parse_multiplier_reads(text, value):
    assert re.fullmatch(MULTIPLIER, text, re.IGNORECASE)
    assert parse_multiplier(text) == value


@pytest.mark.parametrize("word", ["first", "second", "tenth", "nineteenth", "twentieth"])
def test_the_ordinal_fragment_matches_every_ordinal(word):
    assert re.fullmatch(ORDINAL, word, re.IGNORECASE)
    assert parse_ordinal(word) is not None
