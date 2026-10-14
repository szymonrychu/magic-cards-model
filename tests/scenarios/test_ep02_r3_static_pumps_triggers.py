"""Scenario: the non-static clauses of the static-for-each-pump cards (EP-02 R3 T1).

Readers under test live in `machines/ep02_r3_static_pumps_triggers.py` and
`machines/ep02_r3_static_pumps_events.py`. CR numbers below were read with
`mise run rules:find` in the session that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _resolve_stack(scenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def _advance_until(scenario, predicate) -> None:
    while not predicate(scenario):
        scenario.advance()
        _resolve_stack(scenario)


def _pt(scenario, card):
    chars = scenario.game.computed_board().of(card)
    return chars.power, chars.toughness


# -- Behold the Unspeakable, chapter I: "Creatures you don't control get -2/-0 until your next turn."


def _behold_board(bob=("Grizzly Bears", "Grizzly Bears"), alice=(), bob_hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Behold the Unspeakable"],
            battlefield=["Island"] * 5 + list(alice),
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), hand=list(bob_hand), library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_behold(scenario):
    scenario.cast_and_resolve(
        "Behold the Unspeakable", *scenario.untapped_sources(*["Island"] * 5, username="alice")
    )
    _resolve_stack(scenario)


def test_behold_chapter_one_shrinks_only_creatures_alice_does_not_control():
    scenario = _behold_board(alice=["Grizzly Bears"])
    _cast_behold(scenario)
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="bob")
    assert _pt(scenario, mine) == (2, 2)
    assert [_pt(scenario, c) for c in theirs] == [(0, 2), (0, 2)]


def test_behold_chapter_one_lasts_through_bobs_turn_and_ends_on_alices_next_turn():
    scenario = _behold_board()
    _cast_behold(scenario)
    bears = scenario.creature("Grizzly Bears", "bob")
    _advance_until(scenario, lambda s: s.turn.active_player == "bob" and s.step is Step.UPKEEP)
    assert _pt(scenario, bears) == (0, 2)
    _advance_until(scenario, lambda s: s.turn.active_player == "alice" and s.step is Step.UPKEEP)
    assert _pt(scenario, bears) == (2, 2)


def test_behold_chapter_one_does_not_reach_a_creature_that_enters_later():
    # CR 611.2c: the set of affected objects is fixed when the effect begins.
    scenario = _behold_board(bob=("Grizzly Bears",), bob_hand=["Grizzly Bears"])
    _cast_behold(scenario)
    late = scenario.put_onto_battlefield("Grizzly Bears", "bob")
    assert _pt(scenario, late) == (2, 2)


def test_behold_chapter_one_makes_a_negative_power_when_power_is_below_two():
    scenario = _behold_board(bob=("Llanowar Elves",))
    _cast_behold(scenario)
    assert _pt(scenario, scenario.creature("Llanowar Elves", "bob")) == (-1, 1)


# -- Silverwing Squadron: a number of 2/2 Knight tokens equal to the number of opponents you have


def _squadron_board(opponents):
    scenario = Scenario().player("alice", battlefield=["Silverwing Squadron"])
    for name in opponents:
        scenario.player(name, battlefield=[])
    built = scenario.build()
    built.start_at(Step.DECLARE_ATTACKERS)
    return built


def _knights(scenario):
    return [
        c
        for c in scenario.game.permanents_controlled_by("alice")
        if c.card.name != "Silverwing Squadron"
        and "Knight" in scenario.game.computed_board().of(c).subtypes
    ]


def test_silverwing_squadron_makes_one_knight_per_opponent():
    for opponents, expected in ((["bob"], 1), (["bob", "carol"], 2), (["bob", "carol", "dave"], 3)):
        scenario = _squadron_board(opponents)
        squadron = scenario.creature("Silverwing Squadron", "alice")
        scenario.attack_with(squadron, defending="bob")
        scenario.pass_until_resolved()
        knights = _knights(scenario)
        assert len(knights) == expected
        for knight in knights:
            chars = scenario.game.computed_board().of(knight)
            assert (chars.power, chars.toughness) == (2, 2)
            assert "Vigilance" in chars.abilities


def test_silverwing_squadron_counts_only_opponents_still_in_the_game():
    scenario = _squadron_board(["bob", "carol"])
    scenario.game.concede("carol")
    squadron = scenario.creature("Silverwing Squadron", "alice")
    scenario.attack_with(squadron, defending="bob")
    scenario.pass_until_resolved()
    assert len(_knights(scenario)) == 1


def test_silverwing_squadron_attack_trigger_does_not_fire_when_it_does_not_attack():
    scenario = _squadron_board(["bob"])
    scenario.attack_with()
    assert _knights(scenario) == []


# -- Sage's Reverie: draw a card for each Aura you control that's attached to a creature


def _reverie_board(alice=(), bob=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sage's Reverie"],
            battlefield=["Plains"] * 4 + ["Grizzly Bears", *alice],
            library=["Island"] * 8,
        )
        .player("bob", battlefield=list(bob), library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_reverie(scenario):
    bears = scenario.creature("Grizzly Bears", "alice")
    before = len(scenario.player("alice").hand)
    scenario.cast_and_resolve(
        "Sage's Reverie",
        *scenario.untapped_sources(*["Plains"] * 4, username="alice"),
        targets=[bears],
    )
    _resolve_stack(scenario)
    # one card left the hand to cast it
    return len(scenario.player("alice").hand) - (before - 1)


def test_sages_reverie_draws_for_itself_when_it_is_the_only_aura():
    scenario = _reverie_board()
    assert _cast_reverie(scenario) == 1


def test_sages_reverie_counts_each_aura_alice_controls_on_a_creature():
    scenario = _reverie_board(alice=["Pacifism"], bob=["Grizzly Bears"])
    pacifism = scenario.find("Pacifism", Zone.BATTLEFIELD, "alice")
    pacifism.attach_to(scenario.creature("Grizzly Bears", "bob"))
    assert _cast_reverie(scenario) == 2


def test_sages_reverie_ignores_auras_other_players_control():
    scenario = _reverie_board(bob=["Grizzly Bears", "Pacifism"])
    pacifism = scenario.find("Pacifism", Zone.BATTLEFIELD, "bob")
    pacifism.attach_to(scenario.creature("Grizzly Bears", "alice"))
    assert _cast_reverie(scenario) == 1


# -- Desmond Miles: surveil X, where X is the amount of damage it dealt to that player


def _desmond_board(alice_extra=(), graveyard=(), blockers=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Desmond Miles", *alice_extra],
            graveyard=list(graveyard),
            library=["Island", "Swamp", "Forest", "Mountain", "Plains", "Island"],
        )
        .player("bob", battlefield=list(blockers), library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def test_desmond_miles_surveils_for_the_damage_it_dealt():
    scenario = _desmond_board()
    desmond = scenario.creature("Desmond Miles", "alice")
    top = scenario.top_of_library(3, "alice")
    scenario.surveil_to_graveyard(top[0], username="alice")
    scenario.attack_with(desmond, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 19
    # one damage -> surveil 1: only the top card was offered
    assert [c.name for c in scenario.player("alice").graveyard] == [top[0].name]
    assert len(scenario.player("alice").library) == 5


def test_desmond_miles_surveil_is_as_large_as_the_pumped_damage():
    # +1/+0 for each other Assassin (CR 613.4c) and each Assassin card in the graveyard.
    scenario = _desmond_board(
        alice_extra=["Silumgar Assassin"], graveyard=["Silumgar Assassin", "Silumgar Assassin"]
    )
    desmond = scenario.creature("Desmond Miles", "alice")
    assert scenario.game.computed_board().of(desmond).power == 4
    top = scenario.top_of_library(4, "alice")
    scenario.surveil_to_graveyard(*top, username="alice")
    scenario.attack_with(desmond, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 16
    graveyard = [c.name for c in scenario.player("alice").graveyard]
    assert len(graveyard) == 2 + 4
    assert len(scenario.player("alice").library) == 2


def test_desmond_miles_does_not_surveil_when_blocked():
    scenario = _desmond_board(blockers=["Grizzly Bears", "Grizzly Bears"])
    desmond = scenario.creature("Desmond Miles", "alice")
    scenario.attack_with(desmond, defending="bob")
    scenario.block(desmond, *scenario.creatures("Grizzly Bears", "Grizzly Bears", username="bob"))
    scenario.combat_damage()
    scenario.pass_until_resolved()
    # Desmond died to the blockers; nothing was surveiled.
    assert [c.name for c in scenario.player("alice").graveyard] == ["Desmond Miles"]
    assert len(scenario.player("alice").library) == 6


# -- Exuberant Wolfbear: base P/T of target Human you control becomes equal to this creature's P/T


def _wolfbear_board(extra=(), bob=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Exuberant Wolfbear", *extra], library=["Island"] * 4)
        .player("bob", battlefield=list(bob), library=["Forest"] * 4)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def test_wolfbear_sets_the_humans_base_power_and_toughness_to_its_own():
    scenario = _wolfbear_board(extra=["Elite Vanguard"])
    wolf = scenario.creature("Exuberant Wolfbear", "alice")
    human = scenario.creature("Elite Vanguard", "alice")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_targets(human, username="alice")
    scenario.attack_with(wolf, defending="bob")
    scenario.pass_until_resolved()
    assert _pt(scenario, human) == (4, 4)


def test_wolfbear_copies_its_current_pumped_size_and_later_modifiers_still_apply():
    # CR 613.4b: the set is sublayer 7b, so a +1/+1 counter (7d) still adds on top.
    scenario = _wolfbear_board(extra=["Elite Vanguard"])
    wolf = scenario.creature("Exuberant Wolfbear", "alice")
    human = scenario.creature("Elite Vanguard", "alice")
    scenario.game.add_counters(human, "+1/+1", 1)
    scenario.game.add_counters(wolf, "+1/+1", 2)
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_targets(human, username="alice")
    scenario.attack_with(wolf, defending="bob")
    scenario.pass_until_resolved()
    assert _pt(scenario, wolf) == (6, 6)
    assert _pt(scenario, human) == (7, 7)


def test_wolfbear_may_decline():
    scenario = _wolfbear_board(extra=["Elite Vanguard"])
    wolf = scenario.creature("Exuberant Wolfbear", "alice")
    human = scenario.creature("Elite Vanguard", "alice")
    scenario.will_take_the_may(False, username="alice")
    scenario.will_choose_targets(human, username="alice")
    scenario.attack_with(wolf, defending="bob")
    scenario.pass_until_resolved()
    assert _pt(scenario, human) == (2, 1)


def test_wolfbear_effect_ends_at_end_of_turn():
    scenario = _wolfbear_board(extra=["Elite Vanguard"])
    wolf = scenario.creature("Exuberant Wolfbear", "alice")
    human = scenario.creature("Elite Vanguard", "alice")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_targets(human, username="alice")
    scenario.attack_with(wolf, defending="bob")
    scenario.pass_until_resolved()
    _advance_until(scenario, lambda s: s.turn.active_player == "bob")
    assert _pt(scenario, human) == (2, 1)


@pytest.mark.parametrize("bad", ["Savannah Lions", "bobs Elite Vanguard"])
def test_wolfbear_cannot_target_a_non_human_or_an_opponents_human(bad):
    scenario = _wolfbear_board(extra=["Savannah Lions"], bob=["Elite Vanguard"])
    wolf = scenario.creature("Exuberant Wolfbear", "alice")
    target = (
        scenario.creature("Savannah Lions", "alice")
        if bad == "Savannah Lions"
        else scenario.creature("Elite Vanguard", "bob")
    )
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_targets(target, username="alice")
    before = _pt(scenario, target)
    scenario.attack_with(wolf, defending="bob")
    scenario.pass_until_resolved()
    assert _pt(scenario, target) == before
