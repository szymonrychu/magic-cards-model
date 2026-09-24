"""`support.card_support` credits a creature's own combat restriction and an
equip discount on the creature it targets - lines the engine enforces in full.

C01's tasks proved these by scenario (Duskwatch Hunter, Old Fat Spider,
Gollum the Abandoned, Bilbo, Luckwearer, Dwarven Mauler), yet the sweep still
reported each line `static_unaudited`: `_static_ability_category` had no
reader to ask. Each credit calls the enforcing reader's own shapes:

- "`<this>` can't be blocked [by tokens / by creatures with power N or less /
  by creatures with greater power]" - `combat.evasion_restriction_refusal`
  (CR 509.1a);
- "`<this>` can't block [`<description>`]" - `combat.
  self_block_restriction_refusal` (CR 509.1b);
- "Equip abilities you activate that target this creature cost {N} less to
  activate." - `keywords._equip_cost_reduction_for_target` (CR 601.2f via
  CR 602.2b).
"""

import pytest

from magic_cards_model.machines.combat import reads_self_combat_restriction_line
from magic_cards_model.machines.keywords import is_equip_discount_for_this_line
from magic_cards_model.support import card_support
from tests.cards import card

C01_CARDS = (
    "Duskwatch Hunter",
    "Old Fat Spider",
    "Gollum the Abandoned",
    "Bilbo, Luckwearer // Burglar's Plot",
    "Dwarven Mauler",
)


@pytest.mark.parametrize("name", C01_CARDS)
def test_every_clause_of_the_card_is_handled(name: str) -> None:
    for clause in card_support(card(name)).clauses:
        assert clause.outcome == "handled", (name, clause.text, clause.outcome)


#: A printing outside C01 per shape, and the start of the line it carries.
OFF_ROUND = (
    ("Questing Beast", "Questing Beast can't be blocked by creatures with power 2"),
    ("The Mindskinner", "The Mindskinner can't be blocked."),
    ("Bloodghast", "This creature can't block."),
    ("Zurgo Bellstriker", "Zurgo can't block creatures with power 2 or greater."),
    ("Changeling Outcast", "This creature can't block and can't be blocked."),
    ("Fervent Champion", "Equip abilities you activate that target this creature"),
)


@pytest.mark.parametrize(("name", "start"), OFF_ROUND)
def test_the_reader_credits_a_printing_outside_the_round(name: str, start: str) -> None:
    clauses = [c for c in card_support(card(name)).clauses if c.text.startswith(start)]
    assert clauses, (name, start)
    assert all(clause.outcome == "handled" for clause in clauses), clauses


def test_a_restriction_on_other_creatures_is_not_credited() -> None:
    """Only the creature's own restriction is enforced; a group subject or a
    condition in front of it is left to its own reader."""
    assert not reads_self_combat_restriction_line(
        "This creature and other Zombies you control can't be blocked.", "Some Zombie"
    )
    assert not reads_self_combat_restriction_line(
        "As long as you control a Swamp, this creature can't be blocked.", "Some Zombie"
    )
    assert not reads_self_combat_restriction_line(
        "This creature can't be blocked by creatures with flying.", "Some Zombie"
    )
    assert not reads_self_combat_restriction_line(
        "This creature can't block unless you pay {2}.", "Some Zombie"
    )
    assert reads_self_combat_restriction_line("Some can't be blocked by tokens.", "Some Zombie")


def test_an_equip_discount_for_another_object_is_not_credited_here() -> None:
    assert is_equip_discount_for_this_line(
        "Equip abilities you activate that target this creature cost {2} less to activate."
    )
    assert not is_equip_discount_for_this_line(
        "Equip abilities you activate cost {1} less to activate."
    )
