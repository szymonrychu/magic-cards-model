"""Scenario: "As long as this creature has three or more `<kind>` counters on
it, it can attack as though it didn't have defender." - CR 604.2's static
ability gated on the source's own counters, overriding CR 702.3b ("A
creature with defender can't attack").

- Faithbound Judge (the listed disturb card's front face), judgment counters;
- Thoughtbound Phantasm (Modern and Pioneer, not a listed card and in no api
  deck), +1/+1 counters - the second printing of the same reader.
"""

import pytest

from magic_cards_model.machines import Step

from .harness import Scenario


def _board(name: str):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[name], library=["Island"] * 10)
        .player("bob", library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    creature = scenario.creature(name)
    creature.summoning_sick = False
    return scenario, creature


@pytest.mark.parametrize(
    ("name", "kind"), [("Faithbound Judge", "judgment"), ("Thoughtbound Phantasm", "+1/+1")]
)
def test_three_counters_let_it_attack(name, kind):
    scenario, creature = _board(name)
    creature.add_counters(kind, 3)

    assert scenario.can_attack(creature)
    scenario.attack_with(creature)
    assert scenario.attackers() == [creature]


@pytest.mark.parametrize(
    ("name", "kind"), [("Faithbound Judge", "judgment"), ("Thoughtbound Phantasm", "+1/+1")]
)
def test_two_counters_leave_it_a_defender(name, kind):
    scenario, creature = _board(name)
    creature.add_counters(kind, 2)

    assert not scenario.can_attack(creature)
    with pytest.raises(ValueError, match="(?i)defender"):
        scenario.attack_with(creature)


def test_counters_of_another_kind_do_not_count():
    """The condition names judgment counters: three +1/+1 counters on
    Faithbound Judge leave it unable to attack."""
    scenario, judge = _board("Faithbound Judge")
    judge.add_counters("+1/+1", 3)

    assert not scenario.can_attack(judge)


def test_an_it_subject_with_another_condition_is_left_to_its_own_reader():
    """The counter gate accepts "it" as the subject; a sibling sentence whose
    condition is not a counter count (Fleecemane Lion's "As long as this
    creature is monstrous, it has hexproof and indestructible.", CR 701.37b)
    must still reach the reader that grants it."""
    from magic_cards_model.support import card_support
    from tests.cards import card

    scenario, lion = _board("Fleecemane Lion")
    assert scenario.game.hexproof_abilities(lion)[0] is False

    lion.monstrous = True

    assert scenario.game.hexproof_abilities(lion)[0] is True
    assert "indestructible" in {
        line.lower() for line in scenario.game.characteristics_of(lion).abilities
    }
    assert card_support(card("Fleecemane Lion")).status == "handled"
