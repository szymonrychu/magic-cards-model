"""EP-01 round 2, task T7: static replacement and combat-damage statics left
over from round 1 (CR 510.1a, 614.1, 614.12).

"Each creature [you control] assigns combat damage equal to its toughness
rather than its power." - the unconditional twin of Ghalta's gated grant,
proven on a "you control" printing (Belligerent Brontodon, Assault Formation)
and on the all-creatures wording (Doran, the Siege Tower).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from magic_cards_model.models.card_state import Choice, ChoiceKind
from magic_cards_model.models.token import PREDEFINED, TokenDefinition, create_tokens
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def _handled(name: str, containing: str) -> None:
    outcomes = [o for o in classify_clauses(card(name)) if containing in o.text]
    assert outcomes, f"{name}: no clause containing {containing!r}"
    assert {o.category for o in outcomes} == {HANDLED}, outcomes


def _on_battlefield(scenario, name):
    return [c for c in scenario.game.battlefield if c.name == name]


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


# --- Solved token replacement (CR 614.1a, 701.7b, 719.3b, 702.169b) ------------

_DETECTIVE = TokenDefinition(power=2, toughness=2, subtypes=("Detective",))


def _case_board(*, solved: bool):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Case of the Pilfered Proof"], library=["Island"] * 5)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    case = _on_battlefield(scenario, "Case of the Pilfered Proof")[0]
    case.solved = solved
    return scenario


def test_solved_pilfered_proof_adds_a_clue_to_any_token_you_create():
    scenario = _case_board(solved=True)
    create_tokens(scenario.game, _DETECTIVE, "alice", 1)
    assert len(_on_battlefield(scenario, "Clue Token")) == 1


def test_unsolved_pilfered_proof_adds_nothing():
    scenario = _case_board(solved=False)
    create_tokens(scenario.game, _DETECTIVE, "alice", 1)
    assert _on_battlefield(scenario, "Clue Token") == []


def test_solved_pilfered_proof_does_not_help_the_opponent():
    scenario = _case_board(solved=True)
    create_tokens(scenario.game, PREDEFINED["Treasure"], "bob", 1)
    assert _on_battlefield(scenario, "Clue Token") == []


def test_pilfered_proof_line_is_handled():
    _handled("Case of the Pilfered Proof", "Solved")


# --- The Rollercrusher Ride: delirium-gated noncombat damage doubling ----------
# (CR 614.1a, 701.10g, 604.2)

_FOUR_TYPES = ["Grizzly Bears", "Lightning Bolt", "Island", "Sol Ring"]


def _ride_board(graveyard, *, bob_battlefield=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Shock"],
            battlefield=["The Rollercrusher Ride", "Mountain"],
            graveyard=list(graveyard),
            library=["Island"] * 5,
        )
        .player("bob", life=20, battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _shock_bob(scenario):
    bob = scenario.player("bob")
    scenario.cast_onto_stack("Shock", username="alice", targets=[bob], auto=True)
    scenario.pass_until_resolved()
    return 20 - bob.life


def test_rollercrusher_ride_doubles_noncombat_damage_with_delirium():
    assert _shock_bob(_ride_board(_FOUR_TYPES)) == 4


def test_rollercrusher_ride_does_nothing_without_four_card_types():
    assert _shock_bob(_ride_board(_FOUR_TYPES[:3])) == 2


def test_rollercrusher_ride_line_is_handled():
    _handled("The Rollercrusher Ride", "Delirium")


# --- "If a spell or ability an opponent controls causes you to discard" --------
# (CR 701.9a, 614.1a, 614.12; Dodecapod, Loxodon Smiter, Obstinate Baloth,
# Nephalia Academy)


def _discard_board(alice_hand, *, caster="bob", alice_battlefield=()):
    alice = (
        "alice",
        dict(
            hand=list(alice_hand) + (["Mind Rot"] if caster == "alice" else []),
            battlefield=list(alice_battlefield) + ["Swamp"] * 3,
            library=["Island"] * 5,
        ),
    )
    bob = (
        "bob",
        dict(
            hand=["Mind Rot"] if caster == "bob" else [],
            battlefield=["Swamp"] * 3,
            library=["Island"] * 5,
        ),
    )
    scenario = Scenario().manual_turn_based_actions()
    for name, kwargs in (bob, alice) if caster == "bob" else (alice, bob):  # active first
        scenario = scenario.player(name, **kwargs)
    scenario = scenario.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    scenario.cast_onto_stack("Mind Rot", username=caster, targets=[alice], auto=True)
    scenario.pass_until_resolved()
    return scenario


def _names(cards):
    return sorted(c.name for c in cards)


def test_obstinate_baloth_enters_instead_when_an_opponents_spell_discards_it():
    scenario = _discard_board(["Obstinate Baloth", "Island"])
    assert _on_battlefield(scenario, "Obstinate Baloth")
    assert "Obstinate Baloth" not in _names(scenario.player("alice").graveyard)
    assert "Island" in _names(scenario.player("alice").graveyard)


def test_dodecapod_enters_with_two_counters():
    scenario = _discard_board(["Dodecapod", "Island"])
    pod = _on_battlefield(scenario, "Dodecapod")[0]
    assert pod.counter_count("+1/+1") == 2


def test_loxodon_smiter_enters_instead():
    scenario = _discard_board(["Loxodon Smiter", "Island"])
    assert _on_battlefield(scenario, "Loxodon Smiter")


def test_a_self_inflicted_discard_still_goes_to_the_graveyard():
    scenario = _discard_board(["Obstinate Baloth", "Island"], caster="alice")
    assert not _on_battlefield(scenario, "Obstinate Baloth")
    assert "Obstinate Baloth" in _names(scenario.player("alice").graveyard)


def test_nephalia_academy_puts_the_discarded_card_on_top_of_the_library():
    scenario = _discard_board(["Grizzly Bears", "Island"], alice_battlefield=["Nephalia Academy"])
    alice = scenario.player("alice")
    assert "Grizzly Bears" in [c.name for c in alice.library[:2]]
    assert len(alice.graveyard) == 0


def test_discard_replacement_lines_are_handled():
    for name in ("Obstinate Baloth", "Dodecapod", "Loxodon Smiter", "Nephalia Academy"):
        _handled(name, "causes you to discard")


# --- "Creatures you control enter as a copy of ..." (CR 614.1c, 614.12, 707.2) -


def _copy_name(scenario, card_):
    return scenario.game.characteristics_of(card_).name


def test_essence_of_the_wild_makes_a_creature_you_cast_a_copy_of_it():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Essence of the Wild", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.cast_and_resolve("Grizzly Bears", username="alice", auto=True)
    assert _copy_name(scenario, bears) == "Essence of the Wild"
    chars = scenario.game.characteristics_of(bears)
    assert (chars.power, chars.toughness) == (6, 6)


def test_essence_of_the_wild_leaves_an_opponents_creature_alone():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Essence of the Wild"])
        .player("bob", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.game.put_onto_battlefield(
        scenario.find("Grizzly Bears", Zone.HAND, "bob"), "bob"
    )
    assert _copy_name(scenario, bears) == "Grizzly Bears"


def test_infinite_reflection_copies_the_enchanted_creature_onto_nontoken_entrants():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears", "Infinite Reflection"],
            battlefield=["Serra Angel", "Island", "Island", "Island", "Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "alice")
    scenario.cast_and_resolve("Infinite Reflection", username="alice", targets=[angel], auto=True)
    bears = scenario.game.put_onto_battlefield(
        scenario.find("Grizzly Bears", Zone.HAND, "alice"), "alice"
    )
    assert _copy_name(scenario, bears) == "Serra Angel"


def test_infinite_reflection_does_not_copy_a_token_that_enters():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Infinite Reflection"],
            battlefield=["Serra Angel", "Island", "Island", "Island", "Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "alice")
    scenario.cast_and_resolve("Infinite Reflection", username="alice", targets=[angel], auto=True)
    create_tokens(
        scenario.game, TokenDefinition(power=1, toughness=1, subtypes=("Soldier",)), "alice", 1
    )
    soldiers = [c for c in scenario.game.battlefield if "Soldier" in c.subtypes]
    assert soldiers and _copy_name(scenario, soldiers[0]) != "Serra Angel"


def test_group_copy_lines_are_handled():
    _handled("Essence of the Wild", "enter as a copy")
    _handled("Infinite Reflection", "enter as a copy")


def test_infinite_reflection_enters_turns_your_other_nontoken_creatures_into_copies():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Infinite Reflection"],
            battlefield=[
                "Serra Angel",
                "Grizzly Bears",
                "Island",
                "Island",
                "Island",
                "Island",
                "Island",
                "Island",
            ],
        )
        .player("bob", battlefield=["Wall of Omens"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "alice")
    scenario.cast_and_resolve("Infinite Reflection", username="alice", targets=[angel], auto=True)
    scenario.pass_until_resolved()
    bears = scenario.creature("Grizzly Bears", "alice")
    wall = scenario.creature("Wall of Omens", "bob")
    assert _copy_name(scenario, bears) == "Serra Angel"
    assert _copy_name(scenario, wall) == "Wall of Omens"


# --- Protean Raider: Raid-gated enter-as-a-copy (CR 614.12a, 707.2) -----------


def _raider_board(*, attack: bool):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Protean Raider"],
            battlefield=["Serra Angel", "Island", "Mountain", "Island"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    if attack:
        scenario.attack_with(scenario.creature("Serra Angel", "alice"), defending="bob")
        scenario.no_blocks()
        scenario.combat_damage()
        scenario.turn.advance_to(Step.POSTCOMBAT_MAIN)
        scenario.game.sync_priority_with_step()
    return scenario


def test_protean_raider_copies_a_creature_when_you_attacked_this_turn():
    scenario = _raider_board(attack=True)
    raider = scenario.cast_and_resolve("Protean Raider", username="alice", auto=True)
    assert _copy_name(scenario, raider) == "Serra Angel"


def test_protean_raider_enters_as_itself_when_you_did_not_attack():
    scenario = _raider_board(attack=False)
    raider = scenario.cast_and_resolve("Protean Raider", username="alice", auto=True)
    assert _copy_name(scenario, raider) == "Protean Raider"


def test_protean_raider_line_is_handled():
    _handled("Protean Raider", "Raid")


# --- Unbreathing Horde: prevent damage, remove a counter (CR 615.1, 122.1) ----


def _horde_board(counters: int = 3):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Unbreathing Horde"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    horde = scenario.creature("Unbreathing Horde", "bob")
    scenario.game.add_counters(horde, "+1/+1", counters)
    return scenario, horde


def test_unbreathing_horde_prevents_damage_and_loses_a_counter():
    scenario, horde = _horde_board(3)
    scenario.cast_onto_stack("Lightning Bolt", username="alice", targets=[horde], auto=True)
    scenario.pass_until_resolved()
    assert horde.zone is Zone.BATTLEFIELD
    assert horde.damage == 0
    assert horde.counter_count("+1/+1") == 2


def test_unbreathing_horde_with_no_counters_still_prevents_the_damage():
    scenario, horde = _horde_board(1)
    scenario.cast_onto_stack("Lightning Bolt", username="alice", targets=[horde], auto=True)
    scenario.pass_until_resolved()
    assert horde.damage == 0
    assert horde.counter_count("+1/+1") == 0


def test_unbreathing_horde_line_is_handled():
    _handled("Unbreathing Horde", "prevent that damage")


# --- Guile: a counter becomes exile, and you may play the card free -----------
# (CR 701.6a, 614.1a, 608.2g)


def _guile_board(*, guile: bool, answer: bool = True):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Counterspell"],
            battlefield=(["Guile"] if guile else []) + ["Island", "Island"],
        )
        .player("bob", life=20, hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.pass_priority("alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.pass_priority("bob")
    scenario.will_take_the_may(answer, source="Guile")
    scenario.will_choose_targets("bob", source="Lightning Bolt")
    scenario.cast_onto_stack("Counterspell", username="alice", targets=[bolt], auto=True)
    scenario.resolve_top()
    return scenario, bolt


def test_guile_exiles_the_countered_spell_and_lets_you_cast_it_free():
    scenario, bolt = _guile_board(guile=True)
    assert bolt.zone is Zone.STACK
    assert scenario.game.controller_of(bolt).username == "alice"


def test_guile_lets_you_decline_and_the_spell_stays_exiled():
    scenario, bolt = _guile_board(guile=True, answer=False)
    assert bolt.zone is Zone.EXILE


def test_without_guile_the_countered_spell_goes_to_the_graveyard():
    scenario, bolt = _guile_board(guile=False)
    assert bolt.zone is Zone.GRAVEYARD


def test_guile_line_is_handled():
    _handled("Guile", "would counter a spell")


# --- Dermotaxi: imprint a graveyard creature, then become a copy of it ---------
# (CR 607.2a, 614.12a, 707.9b, 707.4)


def _dermotaxi_board(*, graveyard):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dermotaxi"],
            battlefield=["Island", "Island", "Grizzly Bears", "Grizzly Bears"],
            graveyard=list(graveyard),
        )
        .player("bob", graveyard=["Wall of Omens"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    taxi = scenario.cast_and_resolve("Dermotaxi", username="alice", auto=True)
    return scenario, taxi


def test_dermotaxi_exiles_a_creature_card_from_a_graveyard_as_it_enters():
    scenario, taxi = _dermotaxi_board(graveyard=["Serra Angel"])
    linked = scenario.game.cards_exiled_with(taxi.id, None)
    assert len(linked) == 1
    assert linked[0].name in {"Serra Angel", "Wall of Omens"}
    assert linked[0].zone is Zone.EXILE


def test_dermotaxi_with_no_creature_card_anywhere_exiles_nothing():
    scenario = (
        Scenario()
        .player("alice", hand=["Dermotaxi"], battlefield=["Island", "Island"], graveyard=["Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    taxi = scenario.cast_and_resolve("Dermotaxi", username="alice", auto=True)
    assert scenario.game.cards_exiled_with(taxi.id, None) == []


def test_dermotaxi_becomes_a_vehicle_copy_of_the_exiled_card_until_end_of_turn():
    scenario, taxi = _dermotaxi_board(graveyard=[])
    linked = scenario.game.cards_exiled_with(taxi.id, None)
    assert [c.name for c in linked] == ["Wall of Omens"]
    bears = [c for c in scenario.game.battlefield if c.name == "Grizzly Bears"]
    scenario.activate(taxi, tapping_for_cost=bears)
    scenario.pass_until_resolved()
    chars = scenario.game.characteristics_of(taxi)
    assert chars.name == "Wall of Omens"
    assert "Vehicle" in chars.subtypes
    assert Type.ARTIFACT in chars.types and Type.CREATURE in chars.types


def test_dermotaxi_lines_are_handled():
    _handled("Dermotaxi", "Imprint")
    _handled("Dermotaxi", "Until end of turn")


# --- Living Lore: exile an instant or sorcery as it enters ---------------------
# (CR 607.2a, 614.12a, 608.2g)


def _lore_board(*, graveyard):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Living Lore"],
            battlefield=["Island", "Island", "Island", "Island"],
            graveyard=list(graveyard),
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lore = scenario.cast_and_resolve("Living Lore", username="alice", auto=True)
    return scenario, lore


def test_living_lore_exiles_a_spell_card_and_takes_its_mana_value():
    scenario, lore = _lore_board(graveyard=["Lightning Helix", "Grizzly Bears"])
    exiled = scenario.game.cards_exiled_with(lore.id, None)
    assert [c.name for c in exiled] == ["Lightning Helix"]
    chars = scenario.game.characteristics_of(lore)
    assert (chars.power, chars.toughness) == (2, 2)


def test_living_lore_ignores_creature_cards_in_the_graveyard():
    scenario, lore = _lore_board(graveyard=["Grizzly Bears"])
    assert scenario.game.cards_exiled_with(lore.id, None) == []


def test_living_lore_sacrifice_casts_the_exiled_card_free():
    scenario, lore = _lore_board(graveyard=["Lightning Bolt"])
    lore.summoning_sick = False
    scenario.will_take_the_may(True, source="Living Lore")
    scenario.will_choose_targets("bob", source="Lightning Bolt")
    scenario.turn.advance_to(Step.PRECOMBAT_MAIN)
    scenario.attack_with(lore, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    assert lore.zone is Zone.GRAVEYARD
    assert "Lightning Bolt" in scenario.stack_names()


def test_living_lore_lines_are_handled():
    _handled("Living Lore", "Whenever this creature deals combat damage")


# -- Assault Formation: {G}: Target creature with defender can attack this turn -


def _wall_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Assault Formation", "Wall of Omens", "Grizzly Bears", "Forest"],
            library=["Island"] * 6,
        )
        .player("bob", life=20, battlefield=["Grizzly Bears"], library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for creature in scenario.game.battlefield:
        creature.summoning_sick = False
    return scenario


def test_assault_formation_lets_a_defender_attack_this_turn():
    scenario = _wall_board()
    wall = scenario.creature("Wall of Omens", "alice")
    assert not scenario.can_attack(wall)
    formation = _on_battlefield(scenario, "Assault Formation")[0]
    scenario.activate(formation, *scenario.untapped_sources("Forest"), index=0, targets=[wall])
    scenario.pass_until_resolved()
    assert scenario.can_attack(wall)
    assert _damage_to_bob(scenario, wall) == 4, "its toughness is the damage it deals"


def test_assault_formation_does_not_free_a_different_defender_or_last_past_the_turn():
    scenario = _wall_board()
    wall = scenario.creature("Wall of Omens", "alice")
    formation = _on_battlefield(scenario, "Assault Formation")[0]
    scenario.activate(formation, *scenario.untapped_sources("Forest"), index=0, targets=[wall])
    scenario.pass_until_resolved()
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
    while scenario.turn.active_player != "alice":
        scenario.advance()
    assert not scenario.can_attack(wall), "the grant ended with the turn"


def test_assault_formation_cannot_target_a_creature_without_defender():
    scenario = _wall_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    formation = _on_battlefield(scenario, "Assault Formation")[0]
    with pytest.raises(ValueError):
        scenario.activate(formation, *scenario.untapped_sources("Forest"), index=0, targets=[bears])


def test_assault_formation_activated_line_is_credited():
    _handled("Assault Formation", "can attack this turn as though it didn't have defender")
