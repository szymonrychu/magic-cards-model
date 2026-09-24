"""`support.card_support` credits C02's static lines the engine enforces.

C02's tasks proved each of these by scenario, yet the sweep still reported the
line `static_unaudited`: `_static_ability_category` had no reader to ask.
Each credit asks the enforcing reader's own shape:

- look at the top card any time, play lands from the top, a granted
  improvise, a power-scaled instant/sorcery reduction, the power-up discount
  and extra activation, a legendary-count power - `Game.
  reads_enforced_static_line`, over the regexes `Game`'s battlefield readers
  match with;
- "[As long as `<condition>`, ]you may cast spells as though they had flash."
  - `Game.flash_grant_condition_of_line`, credited only when the condition
  is one `condition_holds` can read;
- "`<this>` enters with a `<kind>` counter on him/her." -
  `keyword_counters.enters_with_counters_pronoun_fallback`;
- "As long as `<this>` has a `<kind>` counter on him, you and other
  `<subtype>` you control have `<keyword>`." - `keyword_counters.
  conditional_group_keyword_grant_of_line`;
- "As an additional cost to cast this spell, `<cost>` or pay `<mana>`." on a
  permanent - `casting.reads_or_pay_additional_cost_line`.
"""

import pytest

from magic_cards_model.models.game import Game
from magic_cards_model.support import card_support
from tests.cards import card

C02_CARDS = (
    "Hulk, Gamma Goliath",
    "Wonder Man, Hollywood Hero",
    "Captain America, Super-Soldier",
    "Super-Adaptoid",
    "Daredevil, Man Without Fear",
    "Ka-Zar of the Savage Land",
    "Iron Lad, Diverging Destiny",
    "Captain Mar-Vell, Space-Born",
    "Ironheart, Clever Champion",
    "The Scarlet Witch",
    "Titania, Rugged Rumbler",
)


@pytest.mark.parametrize("name", C02_CARDS)
def test_every_clause_of_the_card_is_handled(name: str) -> None:
    for clause in card_support(card(name)).clauses:
        assert clause.outcome == "handled", (name, clause.text, clause.outcome)


#: A printing outside C02 per shape, and the start of the line it carries.
OFF_ROUND = (
    ("Bayou Groff", "As an additional cost to cast this spell, sacrifice a creature or pay"),
    ("Inspiring Statuary", "Nonartifact spells you cast have improvise."),
    ("High Fae Trickster", "You may cast spells as though they had flash."),
)


@pytest.mark.parametrize(("name", "start"), OFF_ROUND)
def test_the_reader_credits_a_printing_outside_the_round(name: str, start: str) -> None:
    clauses = [c for c in card_support(card(name)).clauses if c.text.startswith(start)]
    assert clauses, (name, start)
    assert all(clause.outcome == "handled" for clause in clauses), clauses


def test_a_flash_grant_keeps_its_condition_for_the_credit_to_judge() -> None:
    line = (
        "Cosmic Awareness — As long as an opponent has cast a spell this turn, "
        "you may cast spells as though they had flash."
    )
    assert Game.flash_grant_condition_of_line(line) == "an opponent has cast a spell this turn"
    unconditional = "You may cast spells as though they had flash."
    assert Game.flash_grant_condition_of_line(unconditional) == ""
    narrower = "You may cast sorcery spells as though they had flash."
    assert Game.flash_grant_condition_of_line(narrower) is None


def test_a_power_up_discount_for_the_source_itself_is_not_read() -> None:
    """The reader is "other creatures" only; a line that discounts every
    power-up ability, the source's own included, is a different shape."""
    line = "Power-up abilities of creatures you control cost {3} less to activate."
    assert not Game.reads_enforced_static_line(line, "Hulk, Gamma Goliath")
