"""Deck construction: what a decklist may contain (CR 100.2, 100.4, 100.5).

Every count here is checked against a real printing from the pool, because the
two interesting rules - basic lands are exempt from the four-copy limit, and a
card can lift the limit in its own text - are properties of the card, not of
the name.

T10's round-trip/replay invariant does not apply here: nothing in this file
ever builds a `Game` (only `Deck`, checked in isolation), so `tests/scenarios/
conftest.py`'s hook has nothing to checkpoint and the pytest_pyfunc_call
returns before it reaches the assertions - not a silent exclusion, a genuine
absence of the state the invariant is about.
"""

import pytest

from magic_cards_model.models import Deck, DeckIllegal, DeckLimits
from tests.cards import card

# A legal constructed deck, built out of the cards the pool actually has.
LEGAL_SIXTY = {
    "Mountain": 24,
    "Plains": 12,
    "Lightning Bolt": 4,
    "Grizzly Bears": 4,
    "Sol Ring": 4,
    "Questing Beast": 4,
    "Swords to Plowshares": 4,
    "Counterspell": 4,
}


def deck(mainboard: dict[str, int] | None = None, **kwargs) -> Deck:
    return Deck(mainboard=mainboard if mainboard is not None else dict(LEGAL_SIXTY), **kwargs)


def test_a_sixty_card_constructed_deck_is_legal():
    """CR 100.2a: sixty cards, no more than four of anything but a basic land."""
    constructed = deck()

    assert constructed.mainboard_size == 60
    assert constructed.problems(card) == []
    assert constructed.is_legal(card)


def test_fifty_nine_cards_is_not_a_deck():
    """CR 100.2a: the minimum deck size, which needs no card data to check."""
    short = dict(LEGAL_SIXTY)
    short["Mountain"] = 23

    with pytest.raises(DeckIllegal, match="at least 60 cards"):
        deck(short).check_legality(card)


def test_a_fifth_copy_of_a_spell_is_illegal():
    """CR 100.2a: four copies of any card that is not a basic land."""
    greedy = dict(LEGAL_SIXTY)
    greedy["Lightning Bolt"] = 5
    greedy["Mountain"] = 23

    with pytest.raises(DeckIllegal, match="5 copies of Lightning Bolt, which is limited to 4"):
        deck(greedy).check_legality(card)


def test_any_number_of_basic_lands_is_legal():
    """CR 100.2a: a deck may contain any number of basic land cards.

    Twenty-four Mountains is the case the copy limit must not catch, and the
    only thing that separates it from twenty-four Grizzly Bears is the `basic`
    supertype on the printing.
    """
    basics = {"Mountain": 40, "Plains": 20}

    assert deck(basics).problems(card) == []
    assert card("Mountain").supertypes and card("Grizzly Bears").supertypes == []


def test_forty_grizzly_bears_is_still_illegal():
    """The counterpart to the basics case: an ordinary card gets no exemption."""
    problems = deck({"Grizzly Bears": 40, "Mountain": 20}).problems(card)

    assert problems == ["40 copies of Grizzly Bears, which is limited to 4"]


def test_a_card_that_lifts_the_limit_in_its_own_text_is_exempt():
    """Relentless Rats: "A deck can have any number of cards named Relentless Rats."

    The four-card limit is a default the card itself overrides (CR 100.2a), so
    this has to be read off the oracle text rather than hard-coded.
    """
    swarm = deck({"Relentless Rats": 40, "Mountain": 20})

    assert "any number of cards named" in (card("Relentless Rats").oracle_text or "")
    assert swarm.problems(card) == []


def test_a_sideboard_of_sixteen_is_illegal():
    """CR 100.4a: a constructed sideboard is at most fifteen cards."""
    with pytest.raises(DeckIllegal, match="sideboard may have at most 15 cards"):
        deck(sideboard={"Relentless Rats": 16}).check_legality(card)


def test_the_copy_limit_spans_the_deck_and_the_sideboard():
    """CR 100.4a: the four-card limit applies to the combined deck and sideboard."""
    split = dict(LEGAL_SIXTY)
    split["Counterspell"] = 3
    split["Mountain"] = 25

    legal = deck(split, sideboard={"Counterspell": 1})
    over = deck(split, sideboard={"Counterspell": 2})

    assert legal.problems(card) == []
    assert over.problems(card) == ["5 copies of Counterspell, which is limited to 4"]


def test_a_format_that_keeps_the_boards_separate_counts_them_separately():
    """The rule is a limit, not a law of nature: formats override it."""
    separate = DeckLimits(copy_limit_spans_sideboard=False)
    four_and_four = deck(LEGAL_SIXTY, sideboard={"Counterspell": 4}, limits=separate)

    assert four_and_four.total_copies("Counterspell") == 4
    assert four_and_four.problems(card) == []


def test_limited_wants_forty_cards_and_no_copy_limit():
    """CR 100.2b: limited decks are forty cards, and the four-card limit does not apply."""
    sealed = Deck(
        mainboard={"Grizzly Bears": 20, "Forest": 20},
        sideboard={"Llanowar Elves": 30},
        limits=DeckLimits.limited(),
    )

    assert sealed.mainboard_size == 40
    assert sealed.problems(card) == []


def test_forty_cards_is_not_enough_for_constructed():
    with pytest.raises(DeckIllegal, match="at least 60 cards"):
        Deck(mainboard={"Grizzly Bears": 20, "Forest": 20}).check_legality(card)


def test_a_deck_has_no_maximum_size():
    """CR 100.5: there is no maximum deck size outside Commander."""
    huge = deck({"Mountain": 250})

    assert huge.mainboard_size == 250
    assert huge.problems(card) == []


def test_a_maximum_can_be_imposed_by_a_format():
    hundred_card = Deck(
        mainboard={"Mountain": 101},
        limits=DeckLimits(min_mainboard=100, max_mainboard=100),
    )

    with pytest.raises(DeckIllegal, match="at most 100 cards"):
        hundred_card.check_legality(card)


def test_a_count_of_zero_is_not_a_decklist_entry():
    with pytest.raises(DeckIllegal, match="not a sane count"):
        Deck(
            mainboard=dict(LEGAL_SIXTY) | {"Island": 0},
            limits=DeckLimits.unlimited(),
        ).check_legality(card)


def test_a_name_that_is_not_a_card_is_a_construction_problem():
    """The resolver decides what exists. A typo is reported, not raised."""
    problems = deck({"Mountain": 56, "Lightnign Bolt": 4}).problems(card)

    assert len(problems) == 1
    assert "Lightnign Bolt is not a real card" in problems[0]


def test_every_problem_is_reported_at_once():
    """A decklist is fixed all at once, so all of its problems are useful."""
    bad = deck({"Mountain": 56, "Lightning Bolt": 5, "Nonesuch": 1}, sideboard={"Counterspell": 15})

    problems = bad.problems(card)

    assert len(problems) == 3
    assert any("5 copies of Lightning Bolt" in problem for problem in problems)
    assert any("Nonesuch is not a real card" in problem for problem in problems)
    assert any("15 copies of Counterspell" in problem for problem in problems)


def test_check_legality_raises_carrying_every_problem():
    bad = deck({"Mountain": 52, "Lightning Bolt": 5, "Grizzly Bears": 5})

    with pytest.raises(DeckIllegal) as raised:
        bad.check_legality(card)

    assert len(raised.value.problems) == 2


def test_a_decklist_expands_to_one_name_per_physical_copy():
    """Counts on the list, cards in the library: sixty of them."""
    constructed = deck(sideboard={"Relentless Rats": 15})

    assert len(list(constructed.mainboard_names())) == 60
    assert list(constructed.mainboard_names()).count("Mountain") == 24
    assert len(list(constructed.sideboard_names())) == 15
    assert constructed.size == 75
