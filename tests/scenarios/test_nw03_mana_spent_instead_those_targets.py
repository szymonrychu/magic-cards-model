"""A mana-spent gate whose "instead" names the spell's own targets.

Sundering Stroke ({6}{R}): "Sundering Stroke deals 7 damage divided as you
choose among one, two, or three targets. If at least seven red mana was spent
to cast this spell, instead Sundering Stroke deals 7 damage to each of those
permanents and/or players."

- CR 601.2d: the division is announced as the spell is cast, one to three
  targets each receiving at least one.
- CR 601.2h / CR 207.2c: the mana actually spent is what the gate reads, when
  the instruction is followed (CR 608.2c), never at cast time.
- CR 614.1a: "instead" replaces the base instruction whole, so when the gate
  holds the announced division no longer matters and every target takes 7.
- CR 608.2b: a target that became illegal is simply not affected; the others
  still are.

Proof printing on the same "instead" ladder: Slaying Fire (Adamant, "at least
three red mana", a plain amount swap).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(lands, bob_battlefield=("Serra Angel", "Hill Giant"), bob_hand=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Sundering Stroke", "Slaying Fire"], battlefield=list(lands))
        .player("bob", hand=list(bob_hand), battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _stroke(scenario, lands, targets, division):
    scenario.cast_and_resolve(
        "Sundering Stroke",
        *scenario.untapped_sources(*lands),
        targets=targets,
        division=division,
    )


def test_seven_red_mana_deals_seven_to_each_target():
    lands = ["Mountain"] * 7
    scenario = _board(lands)
    angel = scenario.creature("Serra Angel", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    _stroke(scenario, lands, [angel, giant, "bob"], [3, 2, 2])
    assert angel.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 13


def test_seven_red_mana_with_a_single_target_is_still_seven():
    lands = ["Mountain"] * 7
    scenario = _board(lands)
    _stroke(scenario, lands, ["bob"], [7])
    assert scenario.player("bob").life == 13


def test_six_red_and_one_other_mana_keeps_the_announced_division():
    lands = ["Mountain"] * 6 + ["Forest"]
    scenario = _board(lands)
    angel = scenario.creature("Serra Angel", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    _stroke(scenario, lands, [angel, giant, "bob"], [4, 2, 1])
    assert angel.zone is Zone.GRAVEYARD  # 4 damage on a 4/4
    assert giant.damage == 2
    assert scenario.player("bob").life == 19


def test_an_illegal_target_is_skipped_and_the_rest_still_take_seven():
    lands = ["Mountain"] * 7
    scenario = _board(
        lands, bob_battlefield=["Serra Angel", "Hill Giant", "Island"], bob_hand=["Unsummon"]
    )
    angel = scenario.creature("Serra Angel", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_onto_stack(
        "Sundering Stroke",
        *scenario.untapped_sources(*lands),
        targets=[angel, giant],
        division=[4, 3],
    )
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Unsummon",
        *scenario.untapped_sources("Island", username="bob"),
        username="bob",
        targets=[giant],
    )
    scenario.resolve_top()
    assert angel.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.HAND


# -- Slaying Fire: the adamant "instead" on the same ladder -----------------------


def _slaying_fire(lands):
    scenario = _board(lands)
    scenario.cast_and_resolve("Slaying Fire", *scenario.untapped_sources(*lands), targets=["bob"])
    return scenario.player("bob").life


def test_slaying_fire_adamant_deals_four_instead():
    assert _slaying_fire(["Mountain"] * 3 + ["Forest"]) == 16


def test_slaying_fire_without_adamant_deals_three():
    assert _slaying_fire(["Mountain"] * 2 + ["Forest"] * 2) == 17
