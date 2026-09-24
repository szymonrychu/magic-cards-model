"""`support.card_support` credits a static line the engine enforces in full.

C00's tasks proved each of these lines by scenario (the test files named in
`docs/engine-coverage.md`), yet the sweep still reported them
`static_unaudited`: `_static_ability_category` had no reader to ask. Each
credit below calls the enforcing reader itself, so a line is `handled` only
when that reader reads all of it:

- casting, draw and search rules - `casting_restrictions.
  reads_player_rule_static_line` (CR 601.3, CR 121.2b);
- "<type> cards in <zones> can't enter the battlefield" -
  `replacement.reads_cant_enter_line` (CR 614.17d);
- a card's own "enters ..." line whose gate the empty sweep board cannot
  stage - a condition read as it enters (CR 614.1d), CR 107.3m's X, a counted
  amount, an MDFC back face's "you may pay 3 life" (CR 614.12a) -
  `replacement.self_enters_effects_read`;
- "This spell costs {N} less to cast for each ..." - `game.
  reads_self_cost_reduction_line` (CR 601.2f);
- a mandatory "As an additional cost to cast this spell, ..." -
  `casting.reads_mandatory_additional_cost_line` (CR 118.8a);
- "You may cast this card from your graveyard using its bestow ability." -
  `casting.reads_printed_zone_permission_line` (CR 604.6);
- "Companion - <condition>" - `companion.reads_companion_line` (CR 702.139a).

Every reader is also proven on a printing outside C00 (the second table).
"""

import pytest

from magic_cards_model.machines.casting import reads_mandatory_additional_cost_line
from magic_cards_model.machines.casting_restrictions import reads_player_rule_static_line
from magic_cards_model.models.game import reads_self_cost_reduction_line
from magic_cards_model.support import card_support
from tests.cards import card

C00_CARDS = (
    "High Noon",
    "Teferi, Time Raveler",
    "Voice of Victory",
    "Grafdigger's Cage",
    "Soulless Jailer",
    "Narset, Parter of Veils",
    "Ashiok, Dream Render",
    "Chalice of the Void",
    "Walking Ballista",
    "Ral, Monsoon Mage",
    "Slumbering Trudge",
    "Darkslick Shores",
    "Spirebluff Canal",
    "Hall of Storm Giants",
    "Boggart Trawler",
    "Disciple of Freyalise",
    "Hydroelectric Specimen",
    "Witch Enchanter",
    "Abhorrent Oculus",
    "Emrakul, the Promised End",
    "Hollow One",
    "Leyline Binding",
    "Scion of Draco",
    "Obsidian Charmaw",
    "Detective's Phoenix",
    "Kaheera, the Orphanguard",
)


@pytest.mark.parametrize("name", C00_CARDS)
def test_every_clause_of_the_card_is_handled(name: str) -> None:
    for clause in card_support(card(name)).clauses:
        assert clause.outcome == "handled", (name, clause.text, clause.outcome)


#: A printing outside C00 per reader, and the start of the line it carries.
OFF_ROUND = (
    ("Rule of Law", "Each player can't cast more than one spell"),
    ("Deafening Silence", "Each player can't cast more than one noncreature"),
    ("Fires of Invention", "You can cast spells only during your turn"),
    ("Spirit of the Labyrinth", "Each player can't draw more than one card"),
    ("Weathered Runestone", "Nonland permanent cards in graveyards"),
    ("Hangarback Walker", "This creature enters with X +1/+1 counters"),
    ("Lurrus of the Dream-Den", "Companion"),
    ("Yorion, Sky Nomad", "Companion"),
)


@pytest.mark.parametrize(("name", "start"), OFF_ROUND)
def test_the_reader_credits_a_printing_outside_the_round(name: str, start: str) -> None:
    clauses = [c for c in card_support(card(name)).clauses if c.text.startswith(start)]
    assert clauses, (name, start)
    assert all(clause.outcome == "handled" for clause in clauses), clauses


def test_a_cast_rule_with_an_unread_clause_is_not_credited() -> None:
    """Fail closed: every conjoined clause must be one a reader enforces."""
    assert not reads_player_rule_static_line(
        "Each player can't cast more than one spell each turn and you can't gain life."
    )


def test_a_reduction_with_an_unread_tail_is_not_credited() -> None:
    assert not reads_self_cost_reduction_line(
        "This spell costs {1} less to cast for each basic land type among lands you "
        "control and each Wizard you control."
    )
    # A condition `condition_holds` may not read is left to its own reader.
    assert not reads_self_cost_reduction_line(
        "This spell costs {1} less to cast if you control a Wizard."
    )


def test_an_optional_additional_cost_is_not_credited_here() -> None:
    assert reads_mandatory_additional_cost_line(
        "As an additional cost to cast this spell, exile six cards from your graveyard."
    )
    assert not reads_mandatory_additional_cost_line(
        "As an additional cost to cast this spell, you may sacrifice a creature."
    )
