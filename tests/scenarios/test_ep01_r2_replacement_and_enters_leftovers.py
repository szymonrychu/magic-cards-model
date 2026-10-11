"""EP-01 round 2, task T7: static replacement and combat-damage statics left
over from round 1 (CR 510.1a, 614.1, 614.12).

"Each creature [you control] assigns combat damage equal to its toughness
rather than its power." - the unconditional twin of Ghalta's gated grant,
proven on a "you control" printing (Belligerent Brontodon, Assault Formation)
and on the all-creatures wording (Doran, the Siege Tower).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models.card_state import Choice, ChoiceKind
from tests.scenarios.harness import Scenario


def _attack_unblocked(battlefield_alice, battlefield_bob=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=list(battlefield_alice))
        .player("bob", life=20, battlefield=list(battlefield_bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _damage_to_bob(scenario, attacker):
    scenario.attack_with(attacker, defending="bob")
    scenario.no_blocks()
    dealt = scenario.combat_damage()
    bob = scenario.player("bob")
    return sum(amount for target, amount in dealt if target is bob)


def test_assault_formation_grants_toughness_damage_to_another_creature():
    scenario = _attack_unblocked(["Assault Formation", "Prudent Fateseer // Peer Review"])
    seer = scenario.creature("Prudent Fateseer", "alice")
    assert _damage_to_bob(scenario, seer) == 4


def test_belligerent_brontodon_itself_assigns_its_toughness():
    scenario = _attack_unblocked(["Belligerent Brontodon"])
    brontodon = scenario.creature("Belligerent Brontodon", "alice")
    assert _damage_to_bob(scenario, brontodon) == 6


def test_you_control_wording_does_not_reach_an_opponents_creature():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Assault Formation"])
        .player("bob", life=20, battlefield=["Wall of Omens"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chars = scenario.game.computed_board().of(scenario.creature("Wall of Omens", "bob"))
    assert not any("toughness rather than its power" in a for a in chars.abilities)


def test_doran_reaches_every_creature_including_an_opponents():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Doran, the Siege Tower"])
        .player("bob", life=20, battlefield=["Wall of Omens"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    doran = scenario.creature("Doran, the Siege Tower", "alice")
    assert _damage_to_bob(scenario, doran) == 5


# --- Haktos the Unscarred: a random number, then protection from every other
# mana value (CR 702.16a protection from a characteristic value, CR 614.12a) --


def _haktos_board(chosen: str):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt", "Lightning Helix"],
            battlefield=["Mountain", "Plains", "Mountain"],
        )
        .player("bob", battlefield=["Haktos the Unscarred"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    haktos = scenario.creature("Haktos the Unscarred", "bob")
    haktos.choice = Choice(kind=ChoiceKind.NUMBER, value=chosen)
    return scenario, haktos


def test_haktos_cannot_be_targeted_by_a_spell_of_any_other_mana_value():
    scenario, haktos = _haktos_board("2")
    with pytest.raises(ValueError, match="protection"):
        scenario.cast_onto_stack(
            "Lightning Bolt",
            *scenario.untapped_sources("Mountain")[:1],
            username="alice",
            targets=[haktos],
        )


def test_haktos_can_be_targeted_by_a_spell_with_the_chosen_mana_value():
    scenario, haktos = _haktos_board("2")
    scenario.cast_onto_stack("Lightning Helix", username="alice", targets=[haktos], auto=True)
    assert "Lightning Helix" in scenario.stack_names()


def test_the_chosen_number_decides_which_mana_value_is_let_through():
    scenario, haktos = _haktos_board("1")
    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain")[:1],
        username="alice",
        targets=[haktos],
    )
    assert "Lightning Bolt" in scenario.stack_names()


def test_haktos_enters_with_a_random_choice_of_two_three_or_four():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Haktos the Unscarred"],
            battlefield=["Plains", "Plains", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    haktos = scenario.cast_and_resolve("Haktos the Unscarred", username="alice", auto=True)
    assert haktos.choice is not None
    assert haktos.choice.kind is ChoiceKind.NUMBER
    assert haktos.choice.value in {"2", "3", "4"}
