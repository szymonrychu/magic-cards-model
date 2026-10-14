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


# -- Herald of Leshrac: cumulative upkeep-gain control of a land you don't control, and
# "when this creature leaves the battlefield, each player gains control of each land
# they own that you control"


def _herald_board(bob=("Mountain", "Swamp"), alice=("Forest",)):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Herald of Leshrac", *alice], library=["Island"] * 10)
        .player("bob", battlefield=list(bob), library=["Forest"] * 10)
        .build()
    )
    scenario.start_at(Step.UNTAP)
    return scenario


def _controller(scenario, card):
    return scenario.game.controller_of(card).username


def _alices_upkeep(scenario):
    scenario.advance()
    assert scenario.step is Step.UPKEEP


def _age(scenario, herald):
    return herald.counter_count("age")


def test_herald_upkeep_cost_takes_a_land_from_an_opponent():
    scenario = _herald_board()
    herald = scenario.creature("Herald of Leshrac", "alice")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "bob")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(mountain, username="alice")
    _alices_upkeep(scenario)
    _resolve_stack(scenario)
    assert _age(scenario, herald) == 1
    assert herald.zone is Zone.BATTLEFIELD
    assert _controller(scenario, mountain) == "alice"
    assert scenario.find("Mountain", Zone.BATTLEFIELD, "alice") is mountain
    # CR 108.3: the owner does not change; the +1/+1 for a land you control but don't own.
    assert mountain.owner == "bob"
    assert _pt(scenario, herald) == (3, 5)


def test_herald_is_sacrificed_when_the_upkeep_is_not_paid():
    scenario = _herald_board()
    herald = scenario.creature("Herald of Leshrac", "alice")
    scenario.will_take_the_may(False, username="alice")
    _alices_upkeep(scenario)
    _resolve_stack(scenario)
    assert herald.zone is Zone.GRAVEYARD


def test_herald_is_sacrificed_when_no_opponent_land_can_be_taken():
    scenario = _herald_board(bob=())
    herald = scenario.creature("Herald of Leshrac", "alice")
    _alices_upkeep(scenario)
    _resolve_stack(scenario)
    assert herald.zone is Zone.GRAVEYARD


def test_herald_leaving_returns_the_land_to_its_owner():
    scenario = _herald_board()
    herald = scenario.creature("Herald of Leshrac", "alice")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "bob")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(mountain, username="alice")
    _alices_upkeep(scenario)
    _resolve_stack(scenario)
    assert _controller(scenario, mountain) == "alice"
    scenario.game.destroy(herald)
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)
    assert _controller(scenario, mountain) == "bob"


def test_herald_leaving_returns_only_lands_its_controller_controls():
    scenario = _herald_board(bob=("Mountain", "Swamp"), alice=("Forest", "Island"))
    herald = scenario.creature("Herald of Leshrac", "alice")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "bob")
    swamp = scenario.find("Swamp", Zone.BATTLEFIELD, "bob")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(mountain, username="alice")
    _alices_upkeep(scenario)
    _resolve_stack(scenario)
    scenario.game.destroy(herald)
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)
    assert _controller(scenario, mountain) == "bob"
    # Lands that never changed hands stay with their owner.
    assert (_controller(scenario, swamp), _controller(scenario, forest)) == ("bob", "alice")


def test_herald_second_upkeep_costs_one_land_per_age_counter():
    scenario = _herald_board(bob=("Mountain", "Swamp", "Plains"))
    herald = scenario.creature("Herald of Leshrac", "alice")
    mountain, swamp, plains = (
        scenario.find(name, Zone.BATTLEFIELD, "bob") for name in ("Mountain", "Swamp", "Plains")
    )
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(mountain, username="alice")
    _alices_upkeep(scenario)
    _resolve_stack(scenario)
    _advance_until(scenario, lambda s: s.turn.active_player == "bob")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(swamp, plains, username="alice")
    _advance_until(scenario, lambda s: s.turn.active_player == "alice" and s.step is Step.UPKEEP)
    _resolve_stack(scenario)
    assert _age(scenario, herald) == 2
    assert herald.zone is Zone.BATTLEFIELD
    assert [_controller(scenario, land) for land in (mountain, swamp, plains)] == ["alice"] * 3


def test_herald_second_upkeep_is_sacrificed_when_too_few_lands_are_left():
    scenario = _herald_board(bob=("Mountain", "Swamp"))
    herald = scenario.creature("Herald of Leshrac", "alice")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "bob")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(mountain, username="alice")
    _alices_upkeep(scenario)
    _resolve_stack(scenario)
    _advance_until(scenario, lambda s: s.turn.active_player == "bob")
    _advance_until(scenario, lambda s: s.turn.active_player == "alice" and s.step is Step.UPKEEP)
    _resolve_stack(scenario)
    # Two age counters need two lands; Bob controls only the Swamp (CR 118.3).
    assert herald.zone is Zone.GRAVEYARD


# -- Lumbering Battlement: exile any number of other nontoken creatures you control until it
# leaves the battlefield; +2/+2 for each card exiled with it


def _battlement_board(extra=("Grizzly Bears", "Llanowar Elves")):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lumbering Battlement", "Raise the Alarm"],
            battlefield=["Plains"] * 7 + list(extra),
            library=["Island"] * 4,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_battlement(scenario, *chosen):
    scenario.will_choose_cards(*chosen, username="alice")
    scenario.cast_and_resolve(
        "Lumbering Battlement", *scenario.untapped_sources(*["Plains"] * 5, username="alice")
    )
    _resolve_stack(scenario)
    return scenario.find("Lumbering Battlement", Zone.BATTLEFIELD, "alice")


def test_battlement_exiles_the_chosen_creatures_and_grows_for_each():
    scenario = _battlement_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    battlement = _cast_battlement(scenario, bears, elves)
    assert bears.zone is Zone.EXILE and elves.zone is Zone.EXILE
    assert _pt(scenario, battlement) == (8, 9)


def test_battlement_exiling_nothing_leaves_it_unpumped():
    scenario = _battlement_board()
    battlement = _cast_battlement(scenario)
    assert _pt(scenario, battlement) == (4, 5)


def test_battlement_returns_the_creatures_when_it_leaves():
    scenario = _battlement_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    battlement = _cast_battlement(scenario, bears)
    assert bears.zone is Zone.EXILE
    scenario.game.destroy(battlement)
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)
    returned = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    assert returned.zone is Zone.BATTLEFIELD


def test_battlement_cannot_exile_tokens_other_players_creatures_or_itself():
    scenario = _battlement_board()
    scenario.cast_and_resolve(
        "Raise the Alarm", *scenario.untapped_sources(*["Plains"] * 2, username="alice")
    )
    _resolve_stack(scenario)
    scenario.will_choose_cards(username="alice")
    scenario.cast_and_resolve(
        "Lumbering Battlement", *scenario.untapped_sources(*["Plains"] * 5, username="alice")
    )
    _resolve_stack(scenario)
    offered = [d for d in scenario.questions_asked() if d.kind.name == "CHOOSE_CARDS"][-1].cards
    names = sorted(scenario.game.find_by_id(card_id).name for card_id in offered)
    assert names == ["Grizzly Bears", "Llanowar Elves"]
    bob_bears = scenario.creature("Grizzly Bears", "bob")
    assert bob_bears.id not in offered


# -- Moraug, Fury of Akoum: landfall in a main phase -> additional combat phase, creatures untap
# at the beginning of that combat; +1/+0 for each time a creature has attacked this turn


def _moraug_board(hand=("Forest",), bob=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Moraug, Fury of Akoum", "Grizzly Bears"],
            hand=list(hand),
            library=["Island"] * 4,
        )
        .player("bob", battlefield=list(bob), library=["Forest"] * 4)
        .build()
    )
    return scenario


def _advance_to(scenario, step, *, occurrence=1):
    seen = 0
    while True:
        scenario.advance()
        _resolve_stack(scenario)
        if scenario.step is step:
            seen += 1
            if seen == occurrence:
                return


def test_moraug_landfall_in_main_phase_adds_a_combat_that_untaps_creatures():
    scenario = _moraug_board()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears, defending="bob")
    assert bears.tapped
    assert _pt(scenario, bears) == (3, 2)  # attacked once this turn
    _advance_to(scenario, Step.POSTCOMBAT_MAIN)
    scenario.play_land("Forest", "alice")
    _resolve_stack(scenario)
    _advance_to(scenario, Step.BEGINNING_OF_COMBAT)
    assert scenario.step is Step.BEGINNING_OF_COMBAT
    _resolve_stack(scenario)
    assert not bears.tapped
    _advance_to(scenario, Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, defending="bob")
    # Attacked twice this turn: +2/+0 (CR 613.4c, sublayer 7c).
    assert _pt(scenario, bears) == (4, 2)


def test_moraug_landfall_outside_a_main_phase_adds_no_combat():
    scenario = _moraug_board()
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    land = scenario.put_onto_battlefield("Forest", "alice")
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)
    assert land.zone is Zone.BATTLEFIELD
    _advance_to(scenario, Step.DECLARE_ATTACKERS)
    _advance_to(scenario, Step.END_OF_COMBAT)
    _advance_to(scenario, Step.POSTCOMBAT_MAIN)
    assert scenario.step is Step.POSTCOMBAT_MAIN


def test_moraug_precombat_landfall_gives_a_combat_before_the_regular_one():
    scenario = _moraug_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.play_land("Forest", "alice")
    _resolve_stack(scenario)
    steps = []
    while scenario.step is not Step.POSTCOMBAT_MAIN:
        scenario.advance()
        _resolve_stack(scenario)
        steps.append(scenario.step)
    assert steps.count(Step.BEGINNING_OF_COMBAT) == 2


def test_moraug_each_land_adds_its_own_combat():
    scenario = _moraug_board(hand=("Forest", "Forest"))
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.put_onto_battlefield(scenario.find("Forest", Zone.HAND, "alice"), "alice")
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)
    scenario.game.put_onto_battlefield(scenario.find("Forest", Zone.HAND, "alice"), "alice")
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)
    steps = []
    while scenario.step is not Step.POSTCOMBAT_MAIN:
        scenario.advance()
        _resolve_stack(scenario)
        steps.append(scenario.step)
    assert steps.count(Step.BEGINNING_OF_COMBAT) == 3


# -- Sunbird Effigy: {T}: for each color among the exiled cards used to craft this creature,
# add one mana of that color (CR 702.167c, CR 105.1)


def _effigy(materials_in_play=("Grizzly Bears",), graveyard=("Lightning Bolt",), bob_exile=()):
    from magic_cards_model.machines.keywords import craft_activation

    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Sunbird Standard", *materials_in_play, *["Plains"] * 5],
            graveyard=list(graveyard),
            library=["Plains"] * 4,
        )
        .player("bob", battlefield=[], exile=list(bob_exile), library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sunbird = scenario.find("Sunbird Standard", Zone.BATTLEFIELD, "alice")
    chosen = [
        *(scenario.find(name, Zone.BATTLEFIELD, "alice") for name in materials_in_play),
        *(scenario.find(name, Zone.GRAVEYARD, "alice") for name in graveyard),
    ]
    activation = craft_activation(scenario.game, sunbird, "alice", chosen)
    payment = activation.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Plains"] * 5, username="alice"))
    activation.activate()
    _resolve_stack(scenario)
    on_battlefield = [c for c in scenario.game.battlefield if c.id == sunbird.id]
    return scenario, (on_battlefield[0] if on_battlefield else None)


def _floating(scenario):
    return {c.name: n for c, n in scenario.player("alice").mana_pool.floating.items()}


def test_sunbird_effigy_adds_one_mana_of_each_color_among_the_exiled_cards():
    scenario, effigy = _effigy()
    scenario.activate(effigy)
    assert _floating(scenario) == {"RED": 1, "GREEN": 1}


def test_sunbird_effigy_counts_a_color_once_however_many_exiled_cards_have_it():
    scenario, effigy = _effigy(materials_in_play=("Grizzly Bears", "Llanowar Elves"), graveyard=())
    scenario.activate(effigy)
    assert _floating(scenario) == {"GREEN": 1}
    assert _pt(scenario, effigy) == (1, 1)


def test_sunbird_effigy_made_only_from_colorless_cards_is_a_0_0_and_dies():
    # CR 704.5f: P/T equal to the (zero) colors among colorless cards.
    scenario, effigy = _effigy(materials_in_play=("Sol Ring",), graveyard=())
    assert effigy is None
    assert scenario.find("Sunbird Standard", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD


def test_sunbird_effigy_ignores_exiled_cards_it_was_not_crafted_with():
    scenario, effigy = _effigy(
        materials_in_play=("Llanowar Elves",), graveyard=(), bob_exile=("Lightning Bolt",)
    )
    scenario.activate(effigy)
    assert _floating(scenario) == {"GREEN": 1}
