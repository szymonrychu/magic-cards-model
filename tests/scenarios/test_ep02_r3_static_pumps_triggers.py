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
