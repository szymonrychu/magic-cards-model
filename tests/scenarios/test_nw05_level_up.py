"""Level up (CR 702.87) and the level symbols of a leveler card (CR 711).

Every rule below was read whole with `mise run rules:find` in the session
that wrote this file:

- **CR 702.87a** - "Level up is an activated ability. 'Level up [cost]'
  means '[Cost]: Put a level counter on this permanent. Activate only as a
  sorcery.'"
- **CR 711.2a** - "'{LEVEL N1-N2} [Abilities] [P/T]' means 'As long as this
  creature has at least N1 level counters on it, but no more than N2 level
  counters on it, it has base power and toughness [P/T] and has
  [abilities].'"
- **CR 711.2b** - "'{LEVEL N3+} [Abilities] [P/T]' means 'As long as this
  creature has N3 or more level counters on it, it has base power and
  toughness [P/T] and has [abilities].'"
- **CR 711.4** - each leveler permanent has its level up ability at all
  times, whatever its level.
- **CR 711.5** - below N1 it has its uppermost power/toughness box.
- **CR 711.6** - in every zone other than the battlefield, a leveler card has
  the power and toughness of its uppermost box.
- **CR 613.4b** - a base power/toughness setting effect is layer 7b, so a
  +1/+1 counter (layer 7c, CR 613.4c) still applies on top of the band.

Proved on Lord of Shatterskull Pass (the listed card: a level-gated attack
trigger), Student of Warfare (keywords that move from one band to the next)
and Coralhelm Commander (a static anthem printed only in its top band) -
the latter two are not listed cards and not in any deck list, and print a
different level-up cost shape ({W} and {1}) from the Lord's {1}{R}.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.keywords import executes
from magic_cards_model.machines.level_up import (
    LEVEL_COUNTER,
    level_bands,
    level_up_activation,
)
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario, mana_from


def board(*permanents: str, hand: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", library=["Plains"] * 3, hand=list(hand or []), battlefield=list(permanents)
        )
        .player("bob", library=["Plains"] * 3, battlefield=["Grizzly Bears"])
    )


def level_up(scenario, permanent, *sources, username="alice"):
    activation = level_up_activation(scenario.game, permanent, username)
    payment = activation.begin_paying()
    for source in sources:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    activation.resolve()
    return activation


def pt(scenario, permanent) -> tuple[int, int]:
    chars = scenario.game.characteristics_of(permanent)
    return chars.power, chars.toughness


def with_levels(scenario, name: str, levels: int):
    permanent = scenario.creature(name)
    if levels:
        permanent.counters.add(LEVEL_COUNTER, levels)
    permanent.summoning_sick = False
    return permanent


# --------------------------------------------------------------------------
# Reading the leveler's striations (CR 711.2)
# --------------------------------------------------------------------------


def test_the_bands_are_read_off_the_printed_striations():
    bands = level_bands(card("Student of Warfare").oracle_text or "")
    assert [(b.low, b.high, b.power, b.toughness, b.lines) for b in bands] == [
        (2, 6, 3, 3, ("First strike",)),
        (7, None, 4, 4, ("Double strike",)),
    ]


def test_a_band_with_no_abilities_still_carries_its_power_toughness_box():
    bands = level_bands(card("Lord of Shatterskull Pass").oracle_text or "")
    assert [(b.low, b.high, b.power, b.toughness) for b in bands] == [(1, 5, 6, 6), (6, None, 6, 6)]
    assert bands[0].lines == ()
    assert bands[1].lines == (
        "Whenever this creature attacks, it deals 6 damage to each creature defending "
        "player controls.",
    )


def test_a_card_without_level_symbols_has_no_bands():
    assert level_bands(card("Grizzly Bears").oracle_text or "") == []


# --------------------------------------------------------------------------
# The level up ability itself (CR 702.87a, CR 711.4)
# --------------------------------------------------------------------------


def test_level_up_puts_a_level_counter_on_the_permanent():
    scenario = board("Student of Warfare", "Plains").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    student = with_levels(scenario, "Student of Warfare", 0)

    level_up(scenario, student, *scenario.untapped_sources("Plains"))

    assert student.counter_count(LEVEL_COUNTER) == 1
    assert student.counter_count("+1/+1") == 0


def test_level_up_costs_the_printed_cost():
    scenario = board("Lord of Shatterskull Pass", "Mountain", "Mountain").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lord = with_levels(scenario, "Lord of Shatterskull Pass", 0)

    activation = level_up_activation(scenario.game, lord, "alice")

    assert str(activation.cost.mana) == "{1}{R}"
    assert activation.rule == "CR 702.87a"


def test_level_up_only_as_a_sorcery():
    scenario = board("Student of Warfare", "Plains").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    student = with_levels(scenario, "Student of Warfare", 0)

    activation = level_up_activation(scenario.game, student, "alice")

    assert "only be activated as a sorcery" in (activation.why_not() or "")
    with pytest.raises(ValueError, match="only be activated as a sorcery"):
        activation.begin_paying()


def test_level_up_is_not_refused_while_summoning_sick():
    """No {T} in the cost (CR 702.87a), so CR 602.5a never applies: a
    leveler cast this turn levels up at once."""
    scenario = board("Plains", "Plains", hand=["Student of Warfare"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plains = scenario.untapped_sources("Plains", "Plains")
    student = scenario.cast_and_resolve("Student of Warfare", plains[0])

    assert student.summoning_sick
    level_up(scenario, student, plains[1])

    assert student.counter_count(LEVEL_COUNTER) == 1


def test_level_up_can_be_activated_at_any_level():
    """CR 711.4: the level up ability is there at all times, past the top
    band's N3 too."""
    scenario = board("Student of Warfare", "Plains").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    student = with_levels(scenario, "Student of Warfare", 9)

    level_up(scenario, student, *scenario.untapped_sources("Plains"))

    assert student.counter_count(LEVEL_COUNTER) == 10


def test_an_opponent_cannot_level_up_your_permanent():
    scenario = board("Student of Warfare").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    student = with_levels(scenario, "Student of Warfare", 0)

    activation = level_up_activation(scenario.game, student, "bob")

    assert "does not control" in (activation.why_not() or "")


def test_a_leveler_on_the_stack_cannot_level_up():
    scenario = board("Plains", "Plains", hand=["Student of Warfare"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    student = scenario.cast_onto_stack("Student of Warfare", *scenario.untapped_sources("Plains"))

    activation = level_up_activation(scenario.game, student, "alice")

    assert "battlefield" in (activation.why_not() or "")


def test_a_card_without_level_up_has_no_level_up_activation():
    scenario = board("Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    with pytest.raises(ValueError, match="no level up ability"):
        level_up_activation(scenario.game, scenario.creature("Grizzly Bears", "alice"), "alice")


# --------------------------------------------------------------------------
# Base power/toughness per band (CR 711.2a/b, CR 711.5, CR 613.4b)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("levels", "expected"),
    [(0, (1, 1)), (1, (1, 1)), (2, (3, 3)), (6, (3, 3)), (7, (4, 4)), (12, (4, 4))],
)
def test_student_of_warfare_takes_the_power_toughness_of_its_band(levels, expected):
    scenario = board("Student of Warfare").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    student = with_levels(scenario, "Student of Warfare", levels)

    assert pt(scenario, student) == expected


@pytest.mark.parametrize(
    ("levels", "expected"), [(0, (3, 3)), (1, (6, 6)), (5, (6, 6)), (6, (6, 6))]
)
def test_lord_of_shatterskull_pass_is_six_six_from_level_one(levels, expected):
    scenario = board("Lord of Shatterskull Pass").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lord = with_levels(scenario, "Lord of Shatterskull Pass", levels)

    assert pt(scenario, lord) == expected


def test_a_plus_one_counter_applies_on_top_of_the_band():
    """CR 613.4b then 613.4c: the band sets base P/T in 7b, the +1/+1 counter
    adds in 7c."""
    scenario = board("Student of Warfare").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    student = with_levels(scenario, "Student of Warfare", 2)
    student.counters.add("+1/+1", 1)

    assert pt(scenario, student) == (4, 4)


def test_leveling_up_into_a_band_changes_power_toughness_at_once():
    scenario = board("Student of Warfare", "Plains").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    student = with_levels(scenario, "Student of Warfare", 1)
    assert pt(scenario, student) == (1, 1)

    level_up(scenario, student, *scenario.untapped_sources("Plains"))

    assert pt(scenario, student) == (3, 3)


def test_off_the_battlefield_a_leveler_has_its_uppermost_box():
    """CR 711.6: in a hand it is its printed 1/1, with neither band keyword."""
    scenario = board(hand=["Student of Warfare"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    student = scenario.find("Student of Warfare", Zone.HAND)

    assert (student.power, student.toughness) == (1, 1)
    assert not has_keyword(student, Keyword.FIRST_STRIKE)
    assert not has_keyword(student, Keyword.DOUBLE_STRIKE)
    assert not has_keyword(student, Keyword.FIRST_STRIKE, scenario.game)


def test_a_leveler_that_leaves_and_returns_starts_over():
    """CR 400.7: the level counters stay with the old object."""
    scenario = board("Student of Warfare").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    student = with_levels(scenario, "Student of Warfare", 7)
    scenario.game.return_to_hand(student)
    returned = scenario.put_onto_battlefield("Student of Warfare")

    assert returned.counter_count(LEVEL_COUNTER) == 0
    assert pt(scenario, returned) == (1, 1)


# --------------------------------------------------------------------------
# Abilities per band (CR 711.2a/b)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("levels", "first", "double"),
    [(0, False, False), (1, False, False), (2, True, False), (6, True, False), (7, False, True)],
)
def test_student_of_warfare_has_each_bands_keyword_only_in_that_band(levels, first, double):
    scenario = board("Student of Warfare").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    student = with_levels(scenario, "Student of Warfare", levels)

    assert has_keyword(student, Keyword.FIRST_STRIKE, scenario.game) is first
    assert has_keyword(student, Keyword.DOUBLE_STRIKE, scenario.game) is double


def test_student_below_its_first_band_deals_ordinary_damage_after_first_strike():
    """With no level counters Student of Warfare has no first strike, so a
    2/2 blocker trades damage with it in the regular damage step."""
    scenario = board("Student of Warfare").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    student = with_levels(scenario, "Student of Warfare", 0)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.attack_with(student)
    scenario.block(student, bears)
    scenario.combat_damage()

    assert student.zone is Zone.GRAVEYARD
    assert bears.damage == 1


def test_student_in_its_first_band_kills_a_blocker_first():
    scenario = board("Student of Warfare").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    student = with_levels(scenario, "Student of Warfare", 2)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.attack_with(student)
    scenario.block(student, bears)
    scenario.combat_damage()

    assert bears.zone is Zone.GRAVEYARD
    assert student.zone is Zone.BATTLEFIELD
    assert student.damage == 0


@pytest.mark.parametrize(("levels", "flying"), [(0, False), (1, False), (2, True), (4, True)])
def test_coralhelm_commander_flies_only_from_level_two(levels, flying):
    scenario = board("Coralhelm Commander").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    commander = with_levels(scenario, "Coralhelm Commander", levels)

    assert has_keyword(commander, Keyword.FLYING, scenario.game) is flying


@pytest.mark.parametrize(("levels", "augur"), [(0, (1, 3)), (3, (1, 3)), (4, (2, 4))])
def test_coralhelm_commanders_anthem_is_only_in_its_top_band(levels, augur):
    """ "Other Merfolk creatures you control get +1/+1." is printed under
    LEVEL 4+, so it is a static ability the Commander has only from four
    level counters on (CR 711.2b)."""
    scenario = board("Coralhelm Commander", "Augur of Bolas").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    commander = with_levels(scenario, "Coralhelm Commander", levels)
    augur_of_bolas = scenario.creature("Augur of Bolas", "alice")

    assert pt(scenario, augur_of_bolas) == augur
    assert pt(scenario, commander) == {0: (2, 2), 3: (3, 3), 4: (4, 4)}[levels]


# --------------------------------------------------------------------------
# An activated ability printed in a band (Brimstone Mage)
# --------------------------------------------------------------------------


def _activated_texts(scenario, permanent) -> list[str]:
    return [ability.text for ability in scenario.game.activated_abilities(permanent)]


@pytest.mark.parametrize(
    ("levels", "expected"),
    [
        (0, []),
        (1, ["{T}: This creature deals 1 damage to any target."]),
        (2, ["{T}: This creature deals 1 damage to any target."]),
        (3, ["{T}: This creature deals 3 damage to any target."]),
    ],
)
def test_brimstone_mage_has_each_bands_activated_ability_only_in_that_band(levels, expected):
    """Brimstone Mage: "LEVEL 1-2 / 2/3 / {T}: ... deals 1 damage ..." and
    "LEVEL 3+ / 2/4 / {T}: ... deals 3 damage ..." - neither is an ability it
    has below level 1, and only one of them at a time."""
    scenario = board("Brimstone Mage").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mage = with_levels(scenario, "Brimstone Mage", levels)

    assert _activated_texts(scenario, mage) == expected


def test_brimstone_mage_at_level_three_pings_for_three():
    scenario = board("Brimstone Mage").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mage = with_levels(scenario, "Brimstone Mage", 3)

    scenario.activate(mage, targets=["bob"])
    scenario.resolve_top()

    assert scenario.player("bob").life == 17
    assert pt(scenario, mage) == (2, 4)


def test_brimstone_mage_at_level_one_pings_for_one():
    scenario = board("Brimstone Mage").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mage = with_levels(scenario, "Brimstone Mage", 1)

    scenario.activate(mage, targets=["bob"])
    scenario.resolve_top()

    assert scenario.player("bob").life == 19


# --------------------------------------------------------------------------
# A triggered ability printed in a band (Lord of Shatterskull Pass)
# --------------------------------------------------------------------------


def _attack(scenario, lord):
    scenario.attack_with(lord)
    return [
        trigger
        for trigger in [*scenario.pending_triggers, *scenario.game.stack]
        if trigger.source_name == "Lord of Shatterskull Pass"
    ]


def test_the_level_six_trigger_does_not_trigger_at_five():
    scenario = board("Lord of Shatterskull Pass").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    lord = with_levels(scenario, "Lord of Shatterskull Pass", 5)

    assert _attack(scenario, lord) == []


def test_the_level_six_trigger_triggers_at_six():
    scenario = board("Lord of Shatterskull Pass").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    lord = with_levels(scenario, "Lord of Shatterskull Pass", 6)

    (trigger,) = _attack(scenario, lord)
    assert "deals 6 damage" in trigger.ability.text


def test_the_level_six_trigger_never_triggers_with_no_counters():
    scenario = board("Lord of Shatterskull Pass").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    lord = with_levels(scenario, "Lord of Shatterskull Pass", 0)

    assert _attack(scenario, lord) == []


# --------------------------------------------------------------------------
# Support audit (machines/keywords.executes)
# --------------------------------------------------------------------------


def test_level_up_is_an_executed_keyword():
    assert executes("Level Up")


@pytest.mark.parametrize(
    "name",
    ["Student of Warfare", "Coralhelm Commander", "Brimstone Mage", "Lord of Shatterskull Pass"],
)
def test_the_level_up_keyword_clause_reads_handled(name):
    support = card_support(card(name))
    (clause,) = [c for c in support.clauses if c.kind == "keyword" and c.text == "Level Up"]
    assert clause.outcome == "handled"


@pytest.mark.parametrize("name", ["Student of Warfare", "Coralhelm Commander", "Brimstone Mage"])
def test_the_proof_levelers_read_handled_on_every_clause(name):
    support = card_support(card(name))
    assert support.status == "handled", [
        (c.text, c.outcome) for c in support.clauses if c.outcome != "handled"
    ]
