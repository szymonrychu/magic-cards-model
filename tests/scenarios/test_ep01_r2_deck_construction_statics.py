"""Deck-construction statics: lines that work before the game begins.

CR 100.2a: "A constructed deck may contain any number of basic land cards and
no more than four of any card with a particular English name other than basic
land cards." A card can override that default in its own text, which
`DeckLimits.copies_allowed` reads:

- "A deck can have any number of cards named ~." (Persistent Petitioners,
  Rat Colony, Relentless Rats, Shadowborn Apostle, Templar Knight);
- "A deck can have up to N cards named ~." (Nazgul's nine, Seven Dwarves'
  seven).

CR 702.139a: "Companion is a keyword ability that functions outside the
game. It's written as "Companion-[Condition]."" - `Deck.companion_problems`
checks the condition against the starting deck through
`machines/companion.companion_condition_satisfied`, which now also reads:

- "Each nonland card in your starting deck has a different name." (Lutri,
  the Spellchaser; a name is its English name, CR 201.2);
- "Each nonland card in your starting deck shares a card type." (Umori, the
  Collector; CR 205.2a's card types);
- "Each permanent card in your starting deck has an activated ability."
  (Zirda, the Dawnwaker; CR 602.1's "[Cost]: [Effect.]");
- "No card in your starting deck has more than one of the same mana symbol
  in its mana cost." (Jegantha, the Wellspring; CR 107.4's symbols, a split
  card's combined cost by CR 709.4, a double-faced card's front face by CR
  712.8a).

Every CR number here was looked up with `mise run rules:find`.
"""

import pytest

from magic_cards_model.models import Deck
from magic_cards_model.support import card_support
from tests.cards import card


def deck(main: dict[str, int], companion: str | None = None) -> Deck:
    filler = 60 - sum(main.values())
    mainboard = dict(main)
    if filler > 0:
        mainboard["Island"] = mainboard.get("Island", 0) + filler
    sideboard = {companion: 1} if companion else {}
    return Deck(mainboard=mainboard, sideboard=sideboard, companion=companion)


def handled(name: str, line: str) -> None:
    clauses = [c for c in card_support(card(name)).clauses if c.text == line]
    assert clauses, (name, line)
    for clause in clauses:
        assert clause.outcome == "handled", (name, clause.text, clause.outcome)


# -- copy-limit overrides (CR 100.2a) -----------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "Persistent Petitioners",
        "Rat Colony",
        "Relentless Rats",
        "Shadowborn Apostle",
        "Templar Knight",
    ],
)
def test_any_number_of_copies_is_legal(name):
    assert deck({name: 30}).problems(card) == []
    handled(name, f"A deck can have any number of cards named {name}.")


def test_an_ordinary_card_is_still_limited_to_four():
    assert deck({"Grizzly Bears": 5}).problems(card) == [
        "5 copies of Grizzly Bears, which is limited to 4"
    ]


def test_the_override_is_only_for_the_named_card():
    """Persistent Petitioners' line does not lift the limit off another card."""
    problems = deck({"Persistent Petitioners": 20, "Grizzly Bears": 5}).problems(card)
    assert problems == ["5 copies of Grizzly Bears, which is limited to 4"]


@pytest.mark.parametrize(("name", "limit"), [("Nazgûl", 9), ("Seven Dwarves", 7)])
def test_up_to_n_copies(name, limit):
    assert deck({name: limit}).problems(card) == []
    assert deck({name: limit + 1}).problems(card) == [
        f"{limit + 1} copies of {name}, which is limited to {limit}"
    ]


@pytest.mark.parametrize(
    ("name", "line"),
    [
        ("Nazgûl", "A deck can have up to nine cards named Nazgûl."),
        ("Seven Dwarves", "A deck can have up to seven cards named Seven Dwarves."),
    ],
)
def test_up_to_n_lines_are_handled(name, line):
    handled(name, line)


# -- companion conditions (CR 702.139a) ---------------------------------------


def test_lutri_accepts_singleton_nonland_cards_and_repeated_lands():
    main = {"Lightning Bolt": 1, "Counterspell": 1, "Grizzly Bears": 1}
    assert deck(main, "Lutri, the Spellchaser").problems(card) == []


def test_lutri_refuses_a_repeated_nonland_card():
    problems = deck({"Lightning Bolt": 2}, "Lutri, the Spellchaser").problems(card)
    assert len(problems) == 1 and "Lightning Bolt" in problems[0]


def test_umori_accepts_a_deck_whose_nonland_cards_share_a_type():
    main = {"Grizzly Bears": 4, "Llanowar Elves": 4, "Craw Wurm": 4}
    assert deck(main, "Umori, the Collector").problems(card) == []


def test_umori_refuses_a_deck_mixing_card_types():
    main = {"Grizzly Bears": 4, "Lightning Bolt": 4}
    assert deck(main, "Umori, the Collector").problems(card) != []


def test_zirda_accepts_permanents_with_activated_abilities():
    """Llanowar Elves' mana ability, a basic land's, a planeswalker's loyalty
    abilities - and an instant is no permanent card, so it is not asked."""
    main = {"Llanowar Elves": 4, "Jace, the Mind Sculptor": 1, "Lightning Bolt": 4}
    assert deck(main, "Zirda, the Dawnwaker").problems(card) == []


def test_zirda_refuses_a_permanent_with_no_activated_ability():
    problems = deck({"Grizzly Bears": 4}, "Zirda, the Dawnwaker").problems(card)
    assert len(problems) == 1 and "Grizzly Bears" in problems[0]


def test_jegantha_accepts_costs_without_a_repeated_symbol():
    main = {"Grizzly Bears": 4, "Lightning Bolt": 4}
    assert deck(main, "Jegantha, the Wellspring").problems(card) == []


def test_jegantha_refuses_a_repeated_mana_symbol():
    problems = deck({"Counterspell": 4, "Craw Wurm": 1}, "Jegantha, the Wellspring").problems(card)
    assert len(problems) == 1
    assert "Counterspell" in problems[0] and "Craw Wurm" in problems[0]


@pytest.mark.parametrize(
    ("name", "line"),
    [
        (
            "Lutri, the Spellchaser",
            "Companion — Each nonland card in your starting deck has a different name.",
        ),
        (
            "Umori, the Collector",
            "Companion — Each nonland card in your starting deck shares a card type.",
        ),
        (
            "Zirda, the Dawnwaker",
            "Companion — Each permanent card in your starting deck has an activated ability.",
        ),
        (
            "Jegantha, the Wellspring",
            "Companion — No card in your starting deck has more than one of the same mana "
            "symbol in its mana cost.",
        ),
    ],
)
def test_companion_lines_are_handled(name, line):
    handled(name, line)
