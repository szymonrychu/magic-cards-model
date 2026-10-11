"""R0b-T8 proofs: Snapcaster Mage (granted flashback), Professor of Symbology
(learn), Jadzi (enters prepared, Oracle's Gift), Jennifer Walters (can't-cast
static, sorcery-speed transform, once-per-turn damage redirect), Fear of
Missing Out (delirium extra combat) and Nova Hellkite (warp).

- CR 702.34a: flashback lets a card be cast from the graveyard, then exiled.
- CR 701.48a: learn - discard to draw, or fetch a Lesson from outside the game.
- CR 722.3a: a permanent can enter prepared; the prepared spell is cast as a copy.
- CR 101.2: a "can't" effect beats a "can" effect.
- CR 500.8: an additional combat phase follows the phase it is added after.
- CR 702.185a: warp, an alternative cost from hand plus an exile at the next end step.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import keyword_cast_options
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def settle(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


# --------------------------------------------------------------------------
# Snapcaster Mage
# --------------------------------------------------------------------------


def _snapcaster_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Snapcaster Mage"],
            battlefield=["Island", "Island", "Mountain", "Mountain"],
            graveyard=["Lightning Bolt", "Grizzly Bears", "Divination"],
        )
        .player("bob", library=["Forest"] * 3)
        .build()
    )


def _cast_snapcaster(scenario, target):
    scenario.choose_trigger_targets("Snapcaster Mage", [target])
    scenario.cast_and_resolve("Snapcaster Mage", *scenario.untapped_sources("Island", "Island"))
    settle(scenario)


def test_snapcaster_mage_grants_flashback_for_the_cards_own_mana_cost():
    scenario = _snapcaster_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    _cast_snapcaster(scenario, bolt)

    casting = scenario.cast("Lightning Bolt", from_zone=Zone.GRAVEYARD)
    casting.use_permission()
    casting.choose_targets(["bob"])
    assert str(casting.total_cost.mana) == "{R}"
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.player("bob").life == 17
    assert bolt.zone is Zone.EXILE, "CR 702.34a: a flashed-back card is exiled"


def test_snapcaster_mage_flashback_cost_follows_a_bigger_mana_cost():
    scenario = _snapcaster_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    divination = scenario.find("Divination", Zone.GRAVEYARD, "alice")
    _cast_snapcaster(scenario, divination)

    casting = scenario.cast("Divination", from_zone=Zone.GRAVEYARD)
    casting.use_permission()
    assert str(casting.total_cost.mana) == "{2}{U}"


def test_a_graveyard_card_without_the_grant_cannot_be_flashed_back():
    scenario = _snapcaster_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    divination = scenario.find("Divination", Zone.GRAVEYARD, "alice")
    _cast_snapcaster(scenario, bolt)

    casting = scenario.cast("Divination", from_zone=Zone.GRAVEYARD)
    with pytest.raises(ValueError):
        casting.use_permission()
    assert divination.zone is not Zone.EXILE


def test_snapcaster_cannot_target_a_creature_card():
    scenario = _snapcaster_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.cast_and_resolve("Snapcaster Mage", *scenario.untapped_sources("Island", "Island"))
    with pytest.raises(ValueError):
        scenario.choose_trigger_targets("Snapcaster Mage", [bears])


def test_the_granted_flashback_ends_with_the_turn():
    scenario = _snapcaster_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    _cast_snapcaster(scenario, bolt)

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2)
    scenario.turn_based_actions()

    casting = scenario.cast("Lightning Bolt", from_zone=Zone.GRAVEYARD)
    with pytest.raises(ValueError):
        casting.use_permission()


def test_snapcaster_mage_has_flash():
    scenario = _snapcaster_board()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    scenario.choose_trigger_targets("Snapcaster Mage", [bolt])

    mage = scenario.cast_and_resolve(
        "Snapcaster Mage", *scenario.untapped_sources("Island", "Island")
    )

    assert mage.zone is Zone.BATTLEFIELD


# --------------------------------------------------------------------------
# Professor of Symbology (learn)
# --------------------------------------------------------------------------


def _professor_board(hand=(), sideboard=()) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Professor of Symbology", *hand],
            battlefield=["Plains", "Plains"],
            library=["Forest", "Island", "Mountain"],
            sideboard=list(sideboard),
        )
        .player("bob")
        .build()
    )


def _cast_professor(scenario):
    scenario.cast_and_resolve(
        "Professor of Symbology", *scenario.untapped_sources("Plains", "Plains")
    )
    settle(scenario)


def test_learn_can_discard_a_card_to_draw_a_card():
    scenario = _professor_board(hand=["Lightning Bolt"], sideboard=["Environmental Sciences"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    top = scenario.top_of_library(1)[0]
    scenario.will_take_the_may(True, username="alice", source="Professor of Symbology")
    scenario.will_discard(bolt, username="alice")

    _cast_professor(scenario)

    assert bolt.zone is Zone.GRAVEYARD
    assert top.zone is Zone.HAND
    assert [s.name for s in alice.outside_the_game] == ["Environmental Sciences"]
    assert scenario.game.reveals == []


def test_learn_can_fetch_a_lesson_from_outside_the_game():
    scenario = _professor_board(
        hand=["Lightning Bolt"], sideboard=["Environmental Sciences", "Preordain"]
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    (lesson,) = [s for s in alice.outside_the_game if s.name == "Environmental Sciences"]
    scenario.will_take_the_may(False, username="alice", source="Professor of Symbology")
    scenario.will_take_the_may(True, username="alice", source="Professor of Symbology")
    scenario.will_choose_cards(lesson, username="alice", source="Professor of Symbology")

    _cast_professor(scenario)

    assert lesson.zone is Zone.HAND
    assert [s.name for s in alice.outside_the_game] == ["Preordain"]
    assert len(scenario.game.reveals) == 1


def test_learn_can_be_declined_entirely():
    scenario = _professor_board(hand=["Lightning Bolt"], sideboard=["Environmental Sciences"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    scenario.will_take_the_may(False, username="alice", source="Professor of Symbology")
    scenario.will_take_the_may(False, username="alice", source="Professor of Symbology")

    _cast_professor(scenario)

    assert bolt.zone is Zone.HAND
    assert len(alice.library) == 3
    assert [s.name for s in alice.outside_the_game] == ["Environmental Sciences"]


def test_learn_with_nothing_to_fetch_or_discard_does_nothing():
    scenario = _professor_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")

    _cast_professor(scenario)

    assert len(alice.library) == 3
    assert alice.hand == []


# --------------------------------------------------------------------------
# Nova Hellkite (warp)
# --------------------------------------------------------------------------


def _nova_board(lands: int = 5) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Nova Hellkite"], battlefield=["Mountain"] * lands)
        .player("bob", battlefield=["Grizzly Bears", "Serra Angel"])
    )


def test_nova_hellkite_hard_cast_has_flying_haste_and_pings_a_creature():
    scenario = _nova_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Nova Hellkite", [bears])

    nova = scenario.cast_and_resolve("Nova Hellkite", *scenario.untapped_sources(*["Mountain"] * 5))
    settle(scenario)

    abilities = [a.lower() for a in scenario.game.characteristics_of(nova).abilities]
    assert "flying, haste" in abilities
    assert bears.damage == 1
    assert scenario.game.cast_record(nova).keyword is None


def test_nova_hellkite_cannot_ping_its_own_controllers_creature():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Nova Hellkite"], battlefield=["Mountain"] * 5 + ["Memnite"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    own = scenario.creature("Memnite", "alice")
    scenario.cast_and_resolve("Nova Hellkite", *scenario.untapped_sources(*["Mountain"] * 5))
    with pytest.raises(ValueError):
        scenario.choose_trigger_targets("Nova Hellkite", [own])


def test_a_warped_nova_hellkite_costs_three_pings_and_is_exiled_at_the_end_step():
    scenario = _nova_board(lands=5).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Nova Hellkite", [bears])

    casting = scenario.cast("Nova Hellkite")
    casting.use_keyword("Warp")
    assert str(casting.total_cost.mana) == "{2}{R}"
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Mountain"] * 3))
    scenario.put_on_stack(casting)
    nova = scenario.resolve_top()
    settle(scenario)

    assert nova.zone is Zone.BATTLEFIELD
    assert bears.damage == 1
    assert casting.keyword_used == "Warp"

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert nova.zone is Zone.EXILE, "CR 702.185a: exiled at the beginning of the next end step"


def test_a_warped_nova_hellkite_can_be_cast_from_exile_on_a_later_turn_for_full_cost():
    scenario = _nova_board(lands=5).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Nova Hellkite", [scenario.creature("Grizzly Bears", "bob")])
    casting = scenario.cast("Nova Hellkite")
    casting.use_keyword("Warp")
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Mountain"] * 3))
    scenario.put_on_stack(casting)
    nova = scenario.resolve_top()
    settle(scenario)
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert nova.zone is Zone.EXILE

    # Still the turn it was exiled on: warp's exile cast waits for a later
    # turn (CR 702.185a), and a creature is not cast in the end step anyway
    # (CR 117.1a - the exile permission changes the zone, not the timing).
    (warp_exile,) = [
        option
        for option in keyword_cast_options(nova.card)
        if option.keyword == "Warp" and option.zone is Zone.EXILE
    ]
    assert "later turn" in (warp_exile.why_not(nova, "alice", scenario.game) or "")
    with pytest.raises(ValueError, match="main phase"):
        scenario.cast("Nova Hellkite", from_zone=Zone.EXILE)

    for _ in range(60):
        scenario.advance()
        if scenario.step is Step.UNTAP:
            scenario.game.untap_step()
        if scenario.turn.active_player == "alice" and scenario.step is Step.PRECOMBAT_MAIN:
            break
    else:
        raise AssertionError("never got back to alice's main phase")
    scenario.choose_trigger_targets("Nova Hellkite", [scenario.creature("Serra Angel", "bob")])
    later = scenario.cast("Nova Hellkite", from_zone=Zone.EXILE)
    later.use_keyword("Warp")
    assert str(later.total_cost.mana) == "{3}{R}{R}"


# --------------------------------------------------------------------------
# Jadzi, Steward of Fate // Oracle's Gift (prepare)
# --------------------------------------------------------------------------


def _jadzi_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Jadzi, Steward of Fate // Oracle's Gift", "Lightning Bolt", "Forest"],
            battlefield=["Island"] * 8,
            library=["Memnite", "Grizzly Bears", "Mountain", "Plains"],
        )
        .player("bob")
        .build()
    )


def _cast_jadzi(scenario):
    scenario.cast_and_resolve(
        "Jadzi, Steward of Fate // Oracle's Gift", *scenario.untapped_sources(*["Island"] * 3)
    )


def test_jadzi_enters_prepared_and_draws_two_then_discards_two():
    scenario = _jadzi_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    drawn = scenario.top_of_library(2)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    forest = scenario.find("Forest", Zone.HAND, "alice")
    scenario.will_discard(bolt, forest, username="alice")

    _cast_jadzi(scenario)
    settle(scenario)

    jadzi = scenario.creature("Jadzi, Steward of Fate", "alice")
    assert jadzi.prepared is True
    assert jadzi.prepared_copy_id is not None
    assert bolt.zone is Zone.GRAVEYARD
    assert forest.zone is Zone.GRAVEYARD
    assert all(card.zone is Zone.HAND for card in drawn)
    assert len(alice.hand) == 2


def test_the_prepared_copy_is_oracles_gift_and_makes_x_fractals_with_x_counters():
    scenario = _jadzi_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    forest = scenario.find("Forest", Zone.HAND, "alice")
    scenario.will_discard(bolt, forest, username="alice")
    _cast_jadzi(scenario)
    settle(scenario)
    jadzi = scenario.creature("Jadzi, Steward of Fate", "alice")
    copy = scenario.game.find_by_id(jadzi.prepared_copy_id)
    assert copy.name == "Oracle's Gift"

    casting = scenario.cast(copy.name, from_zone=Zone.EXILE)
    casting.use_permission()
    casting.determine_cost(x_value=2)
    assert casting.total_cost.mana.converted == 5
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Island"] * 5))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    fractals = [s for s in scenario.game.battlefield if s.token and "Fractal" in s.name]
    assert len(fractals) == 2
    for fractal in fractals:
        assert fractal.counter_count(Counter.PLUS_ONE) == 2
        characteristics = scenario.game.characteristics_of(fractal)
        assert (characteristics.power, characteristics.toughness) == (2, 2)
    assert jadzi.prepared is False, "CR 601.2i: casting the copy unprepares it"


def test_oracles_gift_with_x_one_makes_one_fractal_with_one_counter():
    scenario = _jadzi_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_discard(
        scenario.find("Lightning Bolt", Zone.HAND, "alice"),
        scenario.find("Forest", Zone.HAND, "alice"),
        username="alice",
    )
    _cast_jadzi(scenario)
    settle(scenario)
    jadzi = scenario.creature("Jadzi, Steward of Fate", "alice")
    copy = scenario.game.find_by_id(jadzi.prepared_copy_id)
    casting = scenario.cast(copy.name, from_zone=Zone.EXILE)
    casting.use_permission()
    casting.determine_cost(x_value=1)
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Island"] * 3))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    (fractal,) = [s for s in scenario.game.battlefield if s.token and "Fractal" in s.name]
    assert fractal.counter_count(Counter.PLUS_ONE) == 1


# --------------------------------------------------------------------------
# Jennifer Walters // The Sensational She-Hulk
# --------------------------------------------------------------------------

JENNIFER = "Jennifer Walters // The Sensational She-Hulk"


def _jennifer_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[
                "Jennifer Walters // The Sensational She-Hulk",
                "Forest",
                "Plains",
                "Plains",
                "Mountain",
                "Mountain",
                "Mountain",
                "Grizzly Bears",
            ],
            library=["Forest"] * 5,
        )
        .player(
            "bob",
            hand=["Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain"],
            library=["Forest"] * 5,
        )
        .build()
    )


def _jennifer(scenario):
    return scenario.creature("Jennifer Walters", "alice")


def _bobs_main_phase(scenario) -> None:
    for _ in range(60):
        scenario.advance()
        if scenario.step is Step.UNTAP:
            scenario.game.untap_step()
        if scenario.turn.active_player == "bob" and scenario.step is Step.PRECOMBAT_MAIN:
            return
    raise AssertionError("never reached bob's main phase")


def test_opponents_cannot_cast_spells_during_jennifers_controllers_turn():
    scenario = _jennifer_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    bob_mountain = scenario.untapped_sources("Mountain", username="bob")[0]

    with pytest.raises(ValueError, match="cast"):
        scenario.cast_onto_stack("Lightning Bolt", bob_mountain, username="bob", targets=["alice"])


def test_opponents_can_cast_spells_during_their_own_turn():
    scenario = _jennifer_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bobs_main_phase(scenario)
    mountain = scenario.untapped_sources("Mountain", username="bob")[0]

    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 17


def test_the_controller_is_not_restricted_on_their_own_turn():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Jennifer Walters // The Sensational She-Hulk"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    assert scenario.player("bob").life == 17


def test_jennifer_transforms_at_sorcery_speed_into_she_hulk():
    scenario = _jennifer_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jennifer = _jennifer(scenario)
    lands = scenario.untapped_sources(
        "Forest", "Plains", "Plains", "Mountain", "Mountain", "Mountain"
    )

    scenario.activate(jennifer, *lands)
    scenario.resolve_top()

    characteristics = scenario.game.characteristics_of(jennifer)
    assert characteristics.name == "The Sensational She-Hulk"
    assert (characteristics.power, characteristics.toughness) == (6, 6)
    abilities = " ".join(characteristics.abilities).lower()
    assert "reach, trample" in abilities
    assert jennifer.transformed is True or jennifer.face_down is False


def test_jennifer_cannot_transform_at_instant_speed():
    scenario = _jennifer_board()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    jennifer = _jennifer(scenario)
    lands = scenario.untapped_sources(
        "Forest", "Plains", "Plains", "Mountain", "Mountain", "Mountain"
    )

    with pytest.raises(ValueError, match="sorcery"):
        scenario.activate(jennifer, *lands)


def test_she_hulk_still_stops_opponents_casting_during_her_controllers_turn():
    scenario = _jennifer_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jennifer = _jennifer(scenario)
    lands = scenario.untapped_sources(
        "Forest", "Plains", "Plains", "Mountain", "Mountain", "Mountain"
    )
    scenario.activate(jennifer, *lands)
    scenario.resolve_top()
    scenario.pass_priority("alice")

    with pytest.raises(ValueError, match="cast"):
        scenario.cast_onto_stack(
            "Lightning Bolt",
            scenario.untapped_sources("Mountain", username="bob")[0],
            username="bob",
            targets=["alice"],
        )


def _transformed_she_hulk_on_bobs_turn():
    scenario = _jennifer_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jennifer = _jennifer(scenario)
    lands = scenario.untapped_sources(
        "Forest", "Plains", "Plains", "Mountain", "Mountain", "Mountain"
    )
    scenario.activate(jennifer, *lands)
    scenario.resolve_top()
    _bobs_main_phase(scenario)
    return scenario, jennifer


def test_she_hulk_may_redirect_damage_dealt_to_your_creature_once_each_turn():
    scenario, she_hulk = _transformed_she_hulk_on_bobs_turn()
    bears = scenario.creature("Grizzly Bears", "alice")
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="bob")
    scenario.will_take_the_may(True, username="alice", times=None)
    scenario.will_choose_targets("bob", username="alice", times=None)

    scenario.cast_onto_stack("Lightning Bolt", mountains[0], username="bob", targets=[she_hulk])
    scenario.resolve_top()
    settle(scenario)
    assert scenario.player("bob").life == 17, "3 damage dealt to She-Hulk is dealt to bob"

    scenario.cast_onto_stack("Lightning Bolt", mountains[1], username="bob", targets=[bears])
    scenario.resolve_top()
    settle(scenario)

    assert scenario.player("bob").life == 17, "only once each turn"


def test_she_hulk_redirect_can_be_declined():
    scenario, she_hulk = _transformed_she_hulk_on_bobs_turn()
    mountain = scenario.untapped_sources("Mountain", username="bob")[0]
    scenario.will_take_the_may(False, username="alice", times=None)

    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=[she_hulk])
    scenario.resolve_top()
    settle(scenario)

    assert scenario.player("bob").life == 20


# Second printing of the widened passive-voice reader ("Whenever a creature you
# control is dealt damage", CR 120.1 recipient with a controller clause).


def _rite_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Shock"], battlefield=["Rite of Passage", "Serra Angel", "Mountain"])
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )


def test_rite_of_passage_counts_damage_to_any_creature_you_control():
    scenario = _rite_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Serra Angel", "alice")

    scenario.cast_and_resolve("Shock", *scenario.untapped_sources("Mountain"), targets=[bears])
    settle(scenario)

    assert bears.counter_count(Counter.PLUS_ONE) == 1


def test_rite_of_passage_ignores_damage_to_an_opponents_creature():
    scenario = _rite_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")

    scenario.cast_and_resolve("Shock", *scenario.untapped_sources("Mountain"), targets=[angel])
    settle(scenario)

    assert angel.counter_count(Counter.PLUS_ONE) == 0
    assert scenario.creature("Serra Angel", "alice").counter_count(Counter.PLUS_ONE) == 0


# --------------------------------------------------------------------------
# Fear of Missing Out
# --------------------------------------------------------------------------


def test_fear_of_missing_out_discards_then_draws_when_it_enters():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Fear of Missing Out", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain"],
            library=["Memnite", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    top = scenario.top_of_library(1)[0]
    scenario.will_discard(bolt, username="alice")

    scenario.cast_and_resolve(
        "Fear of Missing Out", *scenario.untapped_sources("Mountain", "Mountain")
    )
    settle(scenario)

    assert bolt.zone is Zone.GRAVEYARD
    assert top.zone is Zone.HAND


def test_fear_of_missing_out_with_an_empty_hand_still_draws():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Fear of Missing Out"],
            battlefield=["Mountain", "Mountain"],
            library=["Memnite", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    top = scenario.top_of_library(1)[0]

    scenario.cast_and_resolve(
        "Fear of Missing Out", *scenario.untapped_sources("Mountain", "Mountain")
    )
    settle(scenario)

    assert top.zone is Zone.HAND


def _fomo_board(graveyard) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Fear of Missing Out", "Grizzly Bears"],
            graveyard=list(graveyard),
            library=["Forest"] * 3,
        )
        .player("bob", library=["Forest"] * 3)
        .build()
    )


FOUR_TYPES = [
    "Lightning Bolt",
    "Forest",
    "Aether Spellbomb",
    "Memnite",
]  # instant, land, artifact, artifact creature


def _phases(scenario):
    steps = [scenario.step]
    while steps[-1] is not Step.END_STEP:
        steps.append(scenario.advance())
    return steps


def test_delirium_attack_untaps_the_creature_and_adds_a_combat_phase():
    scenario = _fomo_board(["Lightning Bolt", "Forest", "Aether Spellbomb", "Grizzly Bears"])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    fomo = scenario.creature("Fear of Missing Out", "alice")
    fomo.summoning_sick = False
    scenario.choose_trigger_targets("Fear of Missing Out", [fomo])

    scenario.attack_with(fomo)
    assert fomo.tapped
    settle(scenario)

    assert not fomo.tapped, "untap target creature"
    steps = _phases(scenario)
    assert steps.count(Step.BEGINNING_OF_COMBAT) == 1, "one extra combat phase after this one"


def test_the_extra_combat_does_not_trigger_again_it_is_the_first_attack_each_turn():
    scenario = _fomo_board(["Lightning Bolt", "Forest", "Aether Spellbomb", "Grizzly Bears"])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    fomo = scenario.creature("Fear of Missing Out", "alice")
    fomo.summoning_sick = False
    scenario.choose_trigger_targets("Fear of Missing Out", [fomo])
    scenario.attack_with(fomo)
    settle(scenario)
    seen_end_of_combat = False
    while not (seen_end_of_combat and scenario.step is Step.DECLARE_ATTACKERS):
        scenario.advance()
        if scenario.step is Step.END_OF_COMBAT:
            scenario.turn_based_actions()  # attackers leave combat
            seen_end_of_combat = True

    scenario.attack_with(fomo)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    steps = _phases(scenario)
    assert Step.BEGINNING_OF_COMBAT not in steps, "no second additional combat"


def test_without_four_card_types_in_the_graveyard_nothing_happens():
    scenario = _fomo_board(["Lightning Bolt", "Forest", "Aether Spellbomb"])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    fomo = scenario.creature("Fear of Missing Out", "alice")
    fomo.summoning_sick = False

    scenario.attack_with(fomo)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert fomo.tapped
    assert Step.BEGINNING_OF_COMBAT not in _phases(scenario)


def test_an_artifact_creature_card_counts_as_both_of_its_types():
    """Delirium counts card types (CR 205.2a): Memnite is two."""
    scenario = _fomo_board(["Lightning Bolt", "Forest", "Memnite"])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    fomo = scenario.creature("Fear of Missing Out", "alice")
    fomo.summoning_sick = False
    scenario.choose_trigger_targets("Fear of Missing Out", [fomo])

    scenario.attack_with(fomo)
    settle(scenario)

    assert not fomo.tapped


def test_the_extra_combat_comes_after_the_current_combat_phase_finishes():
    """CR 500.8: "directly after the specified phase" - the attack that
    triggered it still gets its declare blockers, combat damage and end of
    combat steps before the additional phase begins."""
    scenario = _fomo_board(["Lightning Bolt", "Forest", "Aether Spellbomb", "Grizzly Bears"])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    fomo = scenario.creature("Fear of Missing Out", "alice")
    fomo.summoning_sick = False
    scenario.choose_trigger_targets("Fear of Missing Out", [fomo])
    scenario.attack_with(fomo)
    settle(scenario)

    steps = [scenario.step]
    while steps[-1] is not Step.POSTCOMBAT_MAIN:
        steps.append(scenario.advance())

    assert steps == [
        Step.DECLARE_ATTACKERS,
        Step.DECLARE_BLOCKERS,
        Step.COMBAT_DAMAGE,
        Step.END_OF_COMBAT,
        Step.BEGINNING_OF_COMBAT,
        Step.DECLARE_ATTACKERS,
        Step.DECLARE_BLOCKERS,
        Step.COMBAT_DAMAGE,
        Step.END_OF_COMBAT,
        Step.POSTCOMBAT_MAIN,
    ]


def test_desert_were_worm_extra_combat_also_waits_for_the_current_combat_to_finish():
    """Second printing of the CR 500.8 "after this phase" reader."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Desert Were-Worm"] + ["Mountain"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    worm = scenario.creature("Desert Were-Worm", "alice")
    worm.summoning_sick = False

    scenario.attack_with(worm)
    settle(scenario)
    steps = [scenario.step]
    while steps[-1] is not Step.POSTCOMBAT_MAIN:
        steps.append(scenario.advance())

    assert steps == [
        Step.DECLARE_ATTACKERS,
        Step.DECLARE_BLOCKERS,
        Step.COMBAT_DAMAGE,
        Step.END_OF_COMBAT,
        Step.BEGINNING_OF_COMBAT,
        Step.DECLARE_ATTACKERS,
        Step.DECLARE_BLOCKERS,
        Step.COMBAT_DAMAGE,
        Step.END_OF_COMBAT,
        Step.POSTCOMBAT_MAIN,
    ]
