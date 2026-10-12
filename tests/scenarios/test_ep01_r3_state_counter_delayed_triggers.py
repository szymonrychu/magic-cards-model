"""EP-01-R3 T7: state triggers, counter-event triggers and delayed returns.

Cards: Bog Serpent, Dandan, Pirate Ship, Ronom Serpent, Slipstream Serpent
(CR 603.8 "When you control no <land type>, sacrifice this creature."),
Phylactery Lich ("no permanents with phylactery counters on them"), Immortal
Coil ("When there are no cards in your graveyard, you lose the game."),
Slumbering Dragon, Hollowmurk Siege, Protean Hydra, Soulcipher Board,
Sab-Sunen, Nacatl War-Pride, Nine-Lives Familiar. Second printings proving the
readers: Emperor Crocodile, Synod Centurion (state trigger "no other ...").

CR numbers below were read with `mise run rules:find`: 603.8 (state triggers
and the latch), 603.2c (one event, several occurrences), 122.6 (counters put on
an object), 603.7 (delayed triggered abilities).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import PlayedScenario, Scenario


def _board(alice=(), bob=(), alice_graveyard=(), alice_hand=()) -> PlayedScenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=list(alice),
            graveyard=list(alice_graveyard),
            hand=list(alice_hand),
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _resolve_all(scenario: PlayedScenario) -> None:
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


# -- CR 603.8: "When you control no <land type>, sacrifice this creature." -------


def _lands_matter(creature: str, land: str):
    scenario = _board(alice=[creature, land])
    serpent = scenario.creature(creature, "alice")
    assert scenario.game.put_triggers_on_stack() == []
    scenario.game.destroy(scenario.find(land, Zone.BATTLEFIELD, "alice"))
    assert scenario.game.put_triggers_on_stack() != []
    scenario.resolve_top()
    assert serpent.zone is Zone.GRAVEYARD


def test_bog_serpent_is_sacrificed_when_its_last_swamp_leaves():
    _lands_matter("Bog Serpent", "Swamp")


def test_dandan_is_sacrificed_when_its_last_island_leaves():
    _lands_matter("Dandân", "Island")


def test_pirate_ship_is_sacrificed_when_its_last_island_leaves():
    _lands_matter("Pirate Ship", "Island")


def test_slipstream_serpent_is_sacrificed_when_its_last_island_leaves():
    _lands_matter("Slipstream Serpent", "Island")


def test_ronom_serpent_is_sacrificed_when_its_last_snow_land_leaves():
    _lands_matter("Ronom Serpent", "Snow-Covered Island")


def test_the_serpent_with_no_swamp_at_all_triggers_the_moment_it_is_there():
    scenario = _board(alice=["Bog Serpent"])
    (trigger,) = scenario.game.put_triggers_on_stack()
    assert trigger.source_name == "Bog Serpent"


def test_a_land_of_another_type_does_not_keep_the_serpent():
    scenario = _board(alice=["Bog Serpent", "Forest", "Island"])
    assert [t.source_name for t in scenario.game.put_triggers_on_stack()] == ["Bog Serpent"]


def test_an_opponents_swamp_does_not_keep_the_serpent():
    scenario = _board(alice=["Bog Serpent"], bob=["Swamp"])
    assert len(scenario.game.put_triggers_on_stack()) == 1


def test_a_non_snow_island_does_not_keep_ronom_serpent():
    scenario = _board(alice=["Ronom Serpent", "Island"])
    assert len(scenario.game.put_triggers_on_stack()) == 1


def test_one_of_two_islands_leaving_does_not_trigger():
    scenario = _board(alice=["Dandân", "Island", "Island"])
    scenario.game.destroy(scenario.find("Island", Zone.BATTLEFIELD, "alice"))
    assert scenario.game.put_triggers_on_stack() == []


def test_the_latch_holds_the_trigger_while_it_is_on_the_stack():
    """CR 603.8: it does not trigger again until it has left the stack."""
    scenario = _board(alice=["Bog Serpent"])
    assert len(scenario.game.put_triggers_on_stack()) == 1
    assert scenario.game.put_triggers_on_stack() == []


def test_a_land_arriving_in_response_leaves_the_sacrifice_on_the_stack_anyway():
    """The ability is already on the stack (CR 113.7a); the serpent is still
    sacrificed when it resolves."""
    scenario = _board(alice=["Bog Serpent"], alice_hand=["Swamp"])
    scenario.game.put_triggers_on_stack()
    scenario.put_onto_battlefield("Swamp", "alice")
    scenario.resolve_top()
    assert scenario.find("Bog Serpent", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD


def test_a_snow_land_animated_or_not_only_snow_counts_for_ronom():
    scenario = _board(alice=["Ronom Serpent", "Snow-Covered Island"])
    assert scenario.game.put_triggers_on_stack() == []


# -- Phylactery Lich ---------------------------------------------------------------


def test_phylactery_lich_is_sacrificed_when_the_marked_artifact_leaves():
    scenario = _board(alice=["Sol Ring"], alice_hand=["Phylactery Lich"])
    lich = scenario.put_onto_battlefield("Phylactery Lich", "alice")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    assert ring.counters["phylactery"] == 1
    assert scenario.game.put_triggers_on_stack() == []
    scenario.game.destroy(ring)
    assert len(scenario.game.put_triggers_on_stack()) == 1
    scenario.resolve_top()
    assert lich.zone is Zone.GRAVEYARD


def test_phylactery_lich_with_no_artifact_goes_at_once():
    scenario = _board(alice_hand=["Phylactery Lich"])
    lich = scenario.put_onto_battlefield("Phylactery Lich", "alice")
    _resolve_all(scenario)
    assert lich.zone is Zone.GRAVEYARD


# -- Immortal Coil -----------------------------------------------------------------


def test_immortal_coil_loses_the_game_when_its_own_cost_empties_the_graveyard():
    """Exiling the last two cards to pay Coil's own ability is how the state
    becomes true in a real game; the draw still happens, then alice loses."""
    scenario = _board(alice=["Immortal Coil"], alice_graveyard=["Island", "Island"])
    coil = scenario.find("Immortal Coil", Zone.BATTLEFIELD, "alice")
    assert scenario.game.put_triggers_on_stack() == []
    scenario.activate(coil, exiling=list(scenario.player("alice").graveyard))
    scenario.game.put_triggers_on_stack()
    assert "alice" not in scenario.game.losers
    _resolve_all(scenario)
    assert "alice" in scenario.game.losers


def test_immortal_coil_with_an_empty_graveyard_triggers_and_alice_loses():
    scenario = _board(alice=["Immortal Coil"])
    _resolve_all(scenario)
    assert "alice" in scenario.game.losers


def test_immortal_coil_with_a_card_in_the_graveyard_is_quiet():
    scenario = _board(alice=["Immortal Coil"], alice_graveyard=["Island"])
    assert scenario.game.put_triggers_on_stack() == []
    assert "alice" not in scenario.game.losers


# -- second printings: "no other ..." ----------------------------------------------


def test_emperor_crocodile_is_sacrificed_when_alone():
    scenario = _board(alice=["Emperor Crocodile"])
    croc = scenario.creature("Emperor Crocodile", "alice")
    _resolve_all(scenario)
    assert croc.zone is Zone.GRAVEYARD


def test_emperor_crocodile_stays_with_another_creature():
    scenario = _board(alice=["Emperor Crocodile", "Grizzly Bears"])
    assert scenario.game.put_triggers_on_stack() == []


def test_emperor_crocodile_ignores_an_opponents_creature():
    scenario = _board(alice=["Emperor Crocodile"], bob=["Grizzly Bears"])
    assert len(scenario.game.put_triggers_on_stack()) == 1


def test_synod_centurion_is_sacrificed_without_another_artifact():
    scenario = _board(alice=["Synod Centurion", "Sol Ring"])
    centurion = scenario.creature("Synod Centurion", "alice")
    assert scenario.game.put_triggers_on_stack() == []
    scenario.game.destroy(scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice"))
    _resolve_all(scenario)
    assert centurion.zone is Zone.GRAVEYARD


# -- helpers for the turn-structure tests --------------------------------------------


def _advance_to(scenario: PlayedScenario, step: Step, active: str = "alice") -> None:
    """Advance, putting triggers on the stack and resolving them, until `step`
    of `active`'s turn is reached."""
    for _ in range(80):
        if scenario.step is step and scenario.turn.active_player == active:
            return
        scenario.advance()
        _resolve_all(scenario)
    raise AssertionError(f"never reached {step} of {active}'s turn")


def _advance_into_end_step(scenario: PlayedScenario) -> None:
    """Advance to the end step with its triggers still on the stack."""
    while scenario.step is not Step.END_STEP:
        _resolve_all(scenario)
        scenario.advance()


# -- Slumbering Dragon: "attacks you or a planeswalker you control" ------------------


def _dragon_board(**bob) -> PlayedScenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears", "Grizzly Bears"], library=["Island"] * 5)
        .player("bob", library=["Island"] * 5, **bob)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def test_slumbering_dragon_grows_when_a_creature_attacks_its_controller():
    scenario = _dragon_board(battlefield=["Slumbering Dragon"])
    dragon = scenario.creature("Slumbering Dragon", "bob")
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")
    scenario.attack_with(bears[0])
    _resolve_all(scenario)
    assert dragon.counters[Counter.PLUS_ONE] == 1


def test_slumbering_dragon_triggers_once_per_attacking_creature():
    scenario = _dragon_board(battlefield=["Slumbering Dragon"])
    dragon = scenario.creature("Slumbering Dragon", "bob")
    scenario.attack_with(*scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice"))
    _resolve_all(scenario)
    assert dragon.counters[Counter.PLUS_ONE] == 2


def test_slumbering_dragon_grows_when_its_controllers_planeswalker_is_attacked():
    scenario = _dragon_board(battlefield=["Slumbering Dragon", "Chandra, Torch of Defiance"])
    dragon = scenario.creature("Slumbering Dragon", "bob")
    walker = scenario.find("Chandra, Torch of Defiance", Zone.BATTLEFIELD, "bob")
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"), defending=walker)
    _resolve_all(scenario)
    assert dragon.counters[Counter.PLUS_ONE] == 1


def test_slumbering_dragon_ignores_attacks_on_its_controllers_opponent():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears", "Slumbering Dragon"], library=["Island"] * 5)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    dragon = scenario.creature("Slumbering Dragon", "alice")
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))
    _resolve_all(scenario)
    assert dragon.counters[Counter.PLUS_ONE] == 0


def test_slumbering_dragon_cannot_attack_or_block_until_it_has_five_counters():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Slumbering Dragon"], library=["Island"] * 5)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    dragon = scenario.creature("Slumbering Dragon", "alice")
    assert not scenario.can_attack(dragon)
    scenario.game.add_counters(dragon, Counter.PLUS_ONE, 5)
    assert scenario.can_attack(dragon)


def test_search_the_premises_investigates_for_each_attacking_creature():
    """A second printing of the same condition: Modern-legal, off the pool decks."""
    scenario = _dragon_board(battlefield=["Search the Premises"])
    scenario.attack_with(*scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice"))
    _resolve_all(scenario)
    clues = [s for s in scenario.game.permanents_controlled_by("bob") if s.name.startswith("Clue")]
    assert len(clues) == 2


# -- Hollowmurk Siege: "Whenever a counter is put on a creature you control" ----------


def _siege_board(mode: str) -> PlayedScenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Hollowmurk Siege"],
            battlefield=["Grizzly Bears", "Grizzly Bears"],
            library=["Island"] * 8,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose(mode, source="Hollowmurk Siege")
    scenario.put_onto_battlefield("Hollowmurk Siege")
    return scenario


def _hand(scenario: PlayedScenario, username: str = "alice") -> int:
    return len(scenario.player(username).hand)


def test_hollowmurk_siege_sultai_draws_when_a_counter_lands_on_your_creature():
    scenario = _siege_board("Sultai")
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")[0]
    before = _hand(scenario)
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)
    _resolve_all(scenario)
    assert _hand(scenario) == before + 1


def test_hollowmurk_siege_triggers_only_once_each_turn():
    scenario = _siege_board("Sultai")
    first, second = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")
    before = _hand(scenario)
    scenario.game.add_counters(first, Counter.PLUS_ONE, 1)
    scenario.game.add_counters(second, Counter.PLUS_ONE, 1)
    scenario.game.add_counters(first, "charge", 1)
    _resolve_all(scenario)
    assert _hand(scenario) == before + 1


def test_hollowmurk_siege_two_counters_at_once_are_still_one_draw():
    """Each counter is an occurrence (CR 603.2c) but the ability triggers only
    once each turn, so the second occurrence does not stack."""
    scenario = _siege_board("Sultai")
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")[0]
    before = _hand(scenario)
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 2)
    _resolve_all(scenario)
    assert _hand(scenario) == before + 1


def test_hollowmurk_siege_counts_a_counter_of_any_kind():
    scenario = _siege_board("Sultai")
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")[0]
    before = _hand(scenario)
    scenario.game.add_counters(bears, "charge", 1)
    _resolve_all(scenario)
    assert _hand(scenario) == before + 1


def test_hollowmurk_siege_ignores_an_opponents_creature():
    scenario = _siege_board("Sultai")
    theirs = scenario.creature("Grizzly Bears", "bob")
    before = _hand(scenario)
    scenario.game.add_counters(theirs, Counter.PLUS_ONE, 1)
    _resolve_all(scenario)
    assert _hand(scenario) == before


def test_hollowmurk_siege_abzan_half_does_not_draw():
    scenario = _siege_board("Abzan")
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")[0]
    before = _hand(scenario)
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)
    _resolve_all(scenario)
    assert _hand(scenario) == before


def test_hollowmurk_siege_draws_again_on_the_next_turn():
    scenario = _siege_board("Sultai")
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")[0]
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)
    _resolve_all(scenario)
    _advance_to(scenario, Step.PRECOMBAT_MAIN, "bob")
    before = _hand(scenario)
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)
    _resolve_all(scenario)
    assert _hand(scenario) == before + 1


def test_flourishing_defenses_makes_a_token_for_each_minus_counter():
    """A second printing of the singular put-condition: two -1/-1 counters
    landing together are two occurrences (CR 603.2c) and so two Elf Warriors."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", battlefield=["Flourishing Defenses", "Serra Angel"], library=["Island"] * 5
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "alice")
    scenario.will_take_the_may(True, times=None)
    scenario.game.add_counters(angel, Counter.MINUS_ONE, 2)
    _resolve_all(scenario)
    elves = [
        s
        for s in scenario.game.permanents_controlled_by("alice")
        if s.name.startswith("Elf Warrior")
    ]
    assert len(elves) == 2


def test_bloodcrazed_hoplite_reacts_to_its_own_counter_only():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", battlefield=["Bloodcrazed Hoplite", "Grizzly Bears"], library=["Island"] * 5
        )
        .player("bob", battlefield=["Serra Angel"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hoplite = scenario.creature("Bloodcrazed Hoplite", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)
    assert scenario.pending_triggers == []
    scenario.game.add_counters(hoplite, Counter.PLUS_ONE, 1)
    assert [t.source_name for t in scenario.pending_triggers] == ["Bloodcrazed Hoplite"]


# -- Protean Hydra: "Whenever a +1/+1 counter is removed" + a delayed payoff ------------


def _hydra_board(counters: int = 3) -> PlayedScenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Protean Hydra"], library=["Island"] * 8)
        .player("bob", battlefield=["Grizzly Bears"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hydra = scenario.creature("Protean Hydra", "alice")
    scenario.game.add_counters(hydra, Counter.PLUS_ONE, counters)
    _resolve_all(scenario)
    return scenario


def _plus_ones(permanent) -> int:
    return permanent.counters[Counter.PLUS_ONE]


def test_protean_hydra_gets_two_counters_at_the_end_step_for_a_removed_counter():
    scenario = _hydra_board(3)
    hydra = scenario.creature("Protean Hydra", "alice")
    hydra.remove_counters(Counter.PLUS_ONE, 1)
    assert len(scenario.pending_triggers) == 1
    _resolve_all(scenario)
    assert _plus_ones(hydra) == 2
    _advance_into_end_step(scenario)
    _resolve_all(scenario)
    assert _plus_ones(hydra) == 4


def test_each_removed_counter_is_its_own_occurrence():
    """CR 603.2c: three counters leaving in one removal are three triggers and
    so three delayed payoffs of two counters each."""
    scenario = _hydra_board(4)
    hydra = scenario.creature("Protean Hydra", "alice")
    hydra.remove_counters(Counter.PLUS_ONE, 3)
    assert len(scenario.pending_triggers) == 3
    _resolve_all(scenario)
    assert _plus_ones(hydra) == 1
    _advance_into_end_step(scenario)
    _resolve_all(scenario)
    assert _plus_ones(hydra) == 7


def test_damage_to_the_hydra_removes_counters_and_pays_off_later():
    scenario = _hydra_board(3)
    hydra = scenario.creature("Protean Hydra", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.deal_damage(hydra, 2, source=bears)
    _resolve_all(scenario)
    assert hydra.damage == 0
    assert _plus_ones(hydra) == 1
    _advance_into_end_step(scenario)
    _resolve_all(scenario)
    assert _plus_ones(hydra) == 5


def test_a_counter_of_another_kind_leaving_the_hydra_is_quiet():
    scenario = _hydra_board(2)
    hydra = scenario.creature("Protean Hydra", "alice")
    scenario.game.add_counters(hydra, "charge", 1)
    _resolve_all(scenario)
    hydra.remove_counters("charge", 1)
    assert scenario.pending_triggers == []


def test_a_counter_leaving_another_creature_is_quiet():
    scenario = _hydra_board(2)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)
    _resolve_all(scenario)
    bears.remove_counters(Counter.PLUS_ONE, 1)
    assert scenario.pending_triggers == []


def test_a_hydra_that_dies_before_the_end_step_gets_nothing():
    """CR 603.7c: the delayed ability only affects the object it was made about."""
    scenario = _hydra_board(1)
    hydra = scenario.creature("Protean Hydra", "alice")
    hydra.remove_counters(Counter.PLUS_ONE, 1)
    _resolve_all(scenario)
    scenario.game.destroy(hydra)
    _advance_into_end_step(scenario)
    _resolve_all(scenario)
    assert hydra.zone is Zone.GRAVEYARD
    assert _plus_ones(hydra) == 0


# -- Soulcipher Board // Cipherbound Spirit ----------------------------------------


def _soulcipher_board(
    creature_cards: int = 3, library: list[str] | None = None, extra_hand: tuple[str, ...] = ()
) -> PlayedScenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Soulcipher Board", *["Grizzly Bears"] * creature_cards, "Island", *extra_hand],
            battlefield=["Island", "Island"],
            library=library or ["Forest", "Mountain", "Plains", "Swamp"],
        )
        .player("bob", battlefield=["Serra Angel"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Soulcipher Board", "alice")
    return scenario


def _board_of(scenario: PlayedScenario):
    return scenario.find("Soulcipher Board", Zone.BATTLEFIELD, "alice")


def _discard_a_creature_card(scenario: PlayedScenario) -> None:
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    scenario.game.put_into_graveyard(bears)
    _resolve_all(scenario)


def test_soulcipher_board_enters_with_three_omen_counters():
    assert _board_of(_soulcipher_board()).counters["omen"] == 3


def test_a_creature_card_into_your_graveyard_removes_an_omen_counter():
    scenario = _soulcipher_board()
    _discard_a_creature_card(scenario)
    assert _board_of(scenario).counters["omen"] == 2


def test_a_noncreature_card_into_your_graveyard_does_not_count():
    scenario = _soulcipher_board()
    scenario.game.put_into_graveyard(scenario.find("Island", Zone.HAND, "alice"))
    _resolve_all(scenario)
    assert _board_of(scenario).counters["omen"] == 3


def test_a_creature_card_in_an_opponents_graveyard_does_not_count():
    scenario = _soulcipher_board()
    scenario.game.destroy(scenario.creature("Serra Angel", "bob"))
    _resolve_all(scenario)
    assert _board_of(scenario).counters["omen"] == 3


def test_the_third_creature_card_transforms_the_board_into_the_spirit():
    scenario = _soulcipher_board()
    board = _board_of(scenario)
    _discard_a_creature_card(scenario)
    _discard_a_creature_card(scenario)
    assert board.up_face_name != "Cipherbound Spirit"
    _discard_a_creature_card(scenario)
    assert board.up_face_name == "Cipherbound Spirit"
    assert board.counters["omen"] == 0


def test_two_creature_cards_milled_at_once_are_two_occurrences():
    """CR 603.2c: the singular "a creature card is put" counts each card."""
    scenario = _soulcipher_board(
        creature_cards=0,
        library=["Grizzly Bears", "Serra Angel", "Forest", "Forest"],
        extra_hand=("Thought Scour",),
    )
    scenario.cast_and_resolve(
        "Thought Scour", *scenario.untapped_sources("Island")[:1], targets=["alice"]
    )
    _resolve_all(scenario)
    assert _board_of(scenario).counters["omen"] == 1


def test_soulcipher_board_puts_one_of_the_top_two_cards_into_the_graveyard():
    scenario = _soulcipher_board()
    board = _board_of(scenario)
    top, second = scenario.top_of_library(2, "alice")
    scenario.scry_bottoming(top)
    scenario.activate(board, *scenario.untapped_sources("Island", "Island"))
    scenario.resolve_top()
    assert top.zone is Zone.GRAVEYARD
    assert scenario.top_of_library(1, "alice") == [second]
    assert second.zone is Zone.LIBRARY


# -- Sab-Sunen, Luxa Embodied: an odd number of counters -----------------------------


def _sab_board() -> PlayedScenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Sab-Sunen, Luxa Embodied"], library=["Island"] * 12)
        .player("bob", library=["Island"] * 12)
        .build()
    )
    scenario.start_at(Step.UPKEEP)
    return scenario


def test_sab_sunen_draws_two_when_the_new_counter_makes_the_count_odd():
    scenario = _sab_board()
    sab = scenario.creature("Sab-Sunen, Luxa Embodied", "alice")
    before = _hand(scenario)
    _advance_to(scenario, Step.PRECOMBAT_MAIN)
    assert _plus_ones(sab) == 1
    assert _hand(scenario) == before + 2  # the starting player skips the first draw


def test_sab_sunen_draws_nothing_when_the_count_is_even():
    scenario = _sab_board()
    sab = scenario.creature("Sab-Sunen, Luxa Embodied", "alice")
    scenario.game.add_counters(sab, "charge", 1)  # any counters count, not only +1/+1
    before = _hand(scenario)
    _advance_to(scenario, Step.PRECOMBAT_MAIN)
    assert _plus_ones(sab) == 1
    assert _hand(scenario) == before


def test_sab_sunen_counts_counters_of_every_kind():
    scenario = _sab_board()
    sab = scenario.creature("Sab-Sunen, Luxa Embodied", "alice")
    scenario.game.add_counters(sab, "charge", 2)
    before = _hand(scenario)
    _advance_to(scenario, Step.PRECOMBAT_MAIN)
    assert _hand(scenario) == before + 2  # 2 charge + 1 +1/+1 is odd


def test_sab_sunen_can_attack_only_with_an_even_number_of_counters():
    scenario = _sab_board()
    sab = scenario.creature("Sab-Sunen, Luxa Embodied", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert scenario.can_attack(sab)  # zero is even
    scenario.game.add_counters(sab, Counter.PLUS_ONE, 1)
    assert not scenario.can_attack(sab)
    scenario.game.add_counters(sab, Counter.PLUS_ONE, 1)
    assert scenario.can_attack(sab)


# -- Nacatl War-Pride: copies tapped and attacking, exiled at the end step -----------


def _nacatl_board(defenders=("Grizzly Bears", "Grizzly Bears")) -> PlayedScenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Nacatl War-Pride"], library=["Island"] * 5)
        .player("bob", battlefield=list(defenders), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def _copies(scenario: PlayedScenario) -> list:
    return [
        s
        for s in scenario.game.permanents_controlled_by("alice")
        if s.name == "Nacatl War-Pride" and s.token
    ]


def test_nacatl_war_pride_makes_a_copy_per_creature_the_defender_controls():
    scenario = _nacatl_board()
    scenario.attack_with(scenario.creature("Nacatl War-Pride", "alice"))
    _resolve_all(scenario)
    copies = _copies(scenario)
    assert len(copies) == 2
    assert all(copy.tapped for copy in copies)
    assert all(copy in scenario.attackers() for copy in copies)


def test_nacatl_war_pride_copies_are_exiled_at_the_next_end_step():
    scenario = _nacatl_board()
    scenario.attack_with(scenario.creature("Nacatl War-Pride", "alice"))
    _resolve_all(scenario)
    assert len(_copies(scenario)) == 2
    _advance_into_end_step(scenario)
    _resolve_all(scenario)
    assert _copies(scenario) == []
    assert scenario.creature("Nacatl War-Pride", "alice").zone is Zone.BATTLEFIELD


def test_nacatl_war_pride_against_an_empty_board_makes_nothing():
    scenario = _nacatl_board(defenders=())
    scenario.attack_with(scenario.creature("Nacatl War-Pride", "alice"))
    _resolve_all(scenario)
    assert _copies(scenario) == []


def test_nacatl_war_pride_counts_creatures_only():
    scenario = _nacatl_board(defenders=("Grizzly Bears", "Island", "Sol Ring"))
    scenario.attack_with(scenario.creature("Nacatl War-Pride", "alice"))
    _resolve_all(scenario)
    assert len(_copies(scenario)) == 1


def test_nacatl_war_pride_copies_are_not_declared_attackers():
    """CR 508.4c: a creature put onto the battlefield attacking was never
    declared, so its own "whenever this creature attacks" does not trigger -
    two defenders' creatures give exactly two copies, not a cascade."""
    scenario = _nacatl_board()
    scenario.attack_with(scenario.creature("Nacatl War-Pride", "alice"))
    _resolve_all(scenario)
    assert len(_copies(scenario)) == 2
    assert scenario.pending_triggers == []


# -- Nine-Lives Familiar: a revival counter fewer, back at the end step --------------


def _familiar_board(*, cast: bool = True) -> PlayedScenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Nine-Lives Familiar"],
            battlefield=["Swamp", "Swamp", "Swamp"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    if cast:
        scenario.cast_and_resolve(
            "Nine-Lives Familiar", *scenario.untapped_sources("Swamp", "Swamp", "Swamp")
        )
    else:
        scenario.put_onto_battlefield("Nine-Lives Familiar", "alice")
    return scenario


def _familiar(scenario: PlayedScenario):
    return next(
        s
        for s in scenario.game.permanents_controlled_by("alice")
        if s.name == "Nine-Lives Familiar"
    )


def test_nine_lives_familiar_enters_with_eight_revival_counters_when_cast():
    assert _familiar(_familiar_board()).counters["revival"] == 8


def test_nine_lives_familiar_comes_back_at_the_end_step_with_one_fewer_counter():
    scenario = _familiar_board()
    familiar = _familiar(scenario)
    scenario.game.destroy(familiar)
    _resolve_all(scenario)
    assert familiar.zone is Zone.GRAVEYARD
    _advance_into_end_step(scenario)
    _resolve_all(scenario)
    back = _familiar(scenario)
    assert back.counters["revival"] == 7


def test_nine_lives_familiar_put_onto_the_battlefield_has_no_revival_counter_and_stays_dead():
    """ "If it had a revival counter" is an intervening if (CR 603.4): a
    Familiar that was not cast never had one, so nothing triggers."""
    scenario = _familiar_board(cast=False)
    familiar = _familiar(scenario)
    assert familiar.counters["revival"] == 0
    scenario.game.destroy(familiar)
    assert scenario.game.put_triggers_on_stack() == []
    assert familiar.zone is Zone.GRAVEYARD


def test_the_last_revival_counter_brings_it_back_with_none_and_then_it_stays_dead():
    scenario = _familiar_board()
    familiar = _familiar(scenario)
    familiar.remove_counters("revival", 7)
    scenario.game.destroy(familiar)
    _resolve_all(scenario)
    _advance_into_end_step(scenario)
    _resolve_all(scenario)
    back = _familiar(scenario)
    assert back.counters["revival"] == 0
    scenario.game.destroy(back)
    assert scenario.game.put_triggers_on_stack() == []
    assert back.zone is Zone.GRAVEYARD


def test_a_familiar_exiled_from_the_graveyard_does_not_come_back():
    """CR 603.7c: the delayed return only affects the card where it is expected."""
    scenario = _familiar_board()
    familiar = _familiar(scenario)
    scenario.game.destroy(familiar)
    _resolve_all(scenario)
    scenario.game.exile_cards([familiar])
    _advance_into_end_step(scenario)
    _resolve_all(scenario)
    assert familiar.zone is Zone.EXILE
    assert not any(
        s.name == "Nine-Lives Familiar" for s in scenario.game.permanents_controlled_by("alice")
    )


# -- the static lines that share a card with the triggers above -----------------------


def test_dandan_cannot_attack_a_player_without_an_island():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Dandân", "Island"], library=["Island"] * 5)
        .player("bob", hand=["Island"], battlefield=["Forest"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    dandan = scenario.creature("Dandân", "alice")
    assert not scenario.can_attack(dandan)
    scenario.put_onto_battlefield("Island", "bob")
    assert scenario.can_attack(dandan)


def test_immortal_coil_exiles_a_graveyard_card_for_each_damage_it_prevents():
    scenario = _board(alice=["Immortal Coil", "Grizzly Bears"], alice_graveyard=["Island"] * 4)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.deal_damage(scenario.player("alice"), 3, source=bears)
    assert scenario.player("alice").life == 20
    assert len(scenario.player("alice").graveyard) == 1


def test_protean_hydra_enters_with_x_counters_and_prevents_damage_by_removing_them():
    scenario = _board(alice_hand=["Protean Hydra"], alice=["Forest", "Forest", "Forest"])
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    casting = scenario.cast("Protean Hydra")
    casting.determine_cost(x_value=2)
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    hydra = scenario.resolve_top()
    assert _plus_ones(hydra) == 2
    scenario.game.deal_damage(hydra, 1, source=None)
    assert hydra.damage == 0


def test_phylactery_lich_marks_an_artifact_as_it_enters():
    scenario = _board(alice=["Sol Ring", "Sol Ring"], alice_hand=["Phylactery Lich"])
    scenario.put_onto_battlefield("Phylactery Lich", "alice")
    rings = [s for s in scenario.game.permanents_controlled_by("alice") if s.name == "Sol Ring"]
    assert sorted(ring.counters["phylactery"] for ring in rings) == [0, 1]
