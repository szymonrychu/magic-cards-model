"""Amount terms behind damage and life loss (NW-04, task T3).

Every gap here is an amount term, not a damage reader - the surrounding
"deals N damage" / "loses life equal to" sentences were already read:

- Thunder Salvo: "X is 2 plus the number of other spells you've cast this
  turn" (CR 601.2i's spells cast; "other" leaves the resolving spell out).
- Triumphant Chomp: "2 or the greatest power among Dinosaurs you control,
  whichever is greater" (CR 107.1: the greatest of an empty set is 0).
- Weight of Spires: "the number of nonbasic lands that creature's controller
  controls" (CR 205.4a's basic supertype; the target's controller, CR 608.2h).
- Final Punishment: "the damage already dealt to that player this turn"
  (CR 120.3a counts the damage dealt, CR 615.6: prevented damage is not).
- Cerebral Vortex: "the number of cards they've drawn this turn", counted for
  the targeted player after the draw (CR 608.2c, CR 121.1).

CR numbers checked with `mise run rules:find` (rules effective 2026-09-25).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects.amounts import count_expression
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# -- Thunder Salvo: 2 plus the number of other spells you've cast this turn ----


def _salvo_board(*alice_hand: str, bob_hand: tuple[str, ...] = ()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Thunder Salvo", *alice_hand],
            battlefield=["Mountain"] * 4,
        )
        .player("bob", hand=list(bob_hand), battlefield=["Elder Gargaroth", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature("Elder Gargaroth", "bob")


def test_thunder_salvo_cast_first_deals_only_the_base_two():
    scenario, gargaroth = _salvo_board()
    scenario.cast_and_resolve(
        "Thunder Salvo", *scenario.untapped_sources("Mountain", "Mountain"), targets=[gargaroth]
    )
    assert gargaroth.damage == 2


def test_thunder_salvo_adds_one_per_other_spell_cast_this_turn():
    scenario, gargaroth = _salvo_board("Lightning Bolt")
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    scenario.cast_and_resolve(
        "Thunder Salvo", *scenario.untapped_sources("Mountain", "Mountain"), targets=[gargaroth]
    )
    assert gargaroth.damage == 3


def test_thunder_salvo_counts_each_spell_alice_cast():
    scenario, gargaroth = _salvo_board("Lightning Bolt", "Shock")
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    scenario.cast_and_resolve("Shock", *scenario.untapped_sources("Mountain"), targets=["bob"])
    scenario.cast_and_resolve("Thunder Salvo", auto=True, targets=[gargaroth])
    assert gargaroth.damage == 4


def test_thunder_salvo_ignores_spells_an_opponent_cast():
    scenario, gargaroth = _salvo_board("Lightning Bolt", bob_hand=("Lightning Bolt",))
    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    scenario.pass_priority("alice")
    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=["alice"],
    )
    scenario.resolve_top()
    scenario.resolve_top()
    scenario.cast_and_resolve(
        "Thunder Salvo", *scenario.untapped_sources("Mountain", "Mountain"), targets=[gargaroth]
    )
    assert gargaroth.damage == 3, "alice's own Bolt counts, bob's does not"


def test_the_spells_term_without_other_counts_every_spell_cast_this_turn():
    """The mechanic, not the card: with no "other" the resolving spell counts
    too, and a type list narrows it (the same count `_amount_term` reads)."""
    scenario, gargaroth = _salvo_board("Lightning Bolt")
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    everything = count_expression("the number of spells you've cast this turn")
    others = count_expression("the number of other spells you've cast this turn")
    instants = count_expression("the number of instant spells you've cast this turn")
    creatures = count_expression("the number of creature spells you've cast this turn")
    assert everything is not None and others is not None
    assert instants is not None and creatures is not None
    assert everything(scenario.game, "alice") == 1
    assert others(scenario.game, "alice") == 1  # nothing is resolving, so nothing to leave out
    assert instants(scenario.game, "alice") == 1
    assert creatures(scenario.game, "alice") == 0
    assert everything(scenario.game, "bob") == 0


# -- Triumphant Chomp: 2 or the greatest power among Dinosaurs ---------------


def _chomp_board(alice_battlefield=(), bob_battlefield=("Rampaging Brontodon",)):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Triumphant Chomp"],
            battlefield=["Mountain", *alice_battlefield],
        )
        .player("bob", battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature(bob_battlefield[0], "bob")


def _chomp(scenario, target):
    scenario.cast_and_resolve(
        "Triumphant Chomp", *scenario.untapped_sources("Mountain"), targets=[target]
    )


def test_chomp_with_no_dinosaur_deals_two():
    scenario, target = _chomp_board()
    _chomp(scenario, target)
    assert target.damage == 2


def test_chomp_with_a_weak_dinosaur_still_deals_two():
    scenario, target = _chomp_board(["Sun-Collared Raptor"])
    _chomp(scenario, target)
    assert target.damage == 2


def test_chomp_deals_the_greatest_dinosaur_power_when_it_is_larger():
    scenario, target = _chomp_board(["Rampaging Brontodon"])
    _chomp(scenario, target)
    assert target.zone is Zone.GRAVEYARD, "7 damage kills the 7/7"


def test_chomp_reads_the_greatest_power_not_the_sum():
    scenario, target = _chomp_board(["Sun-Collared Raptor", "Sun-Collared Raptor"])
    _chomp(scenario, target)
    assert target.damage == 2


def test_chomp_ignores_a_larger_creature_that_is_not_a_dinosaur():
    scenario, target = _chomp_board(["Elder Gargaroth"])
    _chomp(scenario, target)
    assert target.damage == 2


def test_chomp_ignores_an_opponents_dinosaur():
    scenario, target = _chomp_board()
    assert scenario.creature("Rampaging Brontodon", "bob") is target
    _chomp(scenario, target)
    assert target.damage == 2


# -- Weight of Spires: nonbasic lands that creature's controller controls ----


def _spires_board(alice_lands=(), bob_lands=(), bob_creature="Elder Gargaroth"):
    scenario = (
        Scenario()
        .player("alice", hand=["Weight of Spires"], battlefield=["Mountain", *alice_lands])
        .player("bob", battlefield=[bob_creature, *bob_lands])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature(bob_creature, "bob")


def _spires(scenario, target):
    scenario.cast_and_resolve(
        "Weight of Spires", *scenario.untapped_sources("Mountain"), targets=[target]
    )


def test_spires_counts_the_targets_controllers_nonbasic_lands():
    scenario, target = _spires_board(bob_lands=["Command Tower", "Temple of Epiphany"])
    _spires(scenario, target)
    assert target.damage == 2


def test_spires_does_not_count_basic_lands():
    scenario, target = _spires_board(bob_lands=["Command Tower", "Island", "Mountain", "Island"])
    _spires(scenario, target)
    assert target.damage == 1


def test_spires_with_no_nonbasic_lands_deals_nothing():
    scenario, target = _spires_board(bob_lands=["Island"])
    _spires(scenario, target)
    assert target.damage == 0


def test_spires_does_not_count_the_casters_nonbasic_lands():
    scenario, target = _spires_board(alice_lands=["Command Tower", "Temple of Epiphany"])
    _spires(scenario, target)
    assert target.damage == 0


def test_spires_aimed_at_the_casters_own_creature_counts_the_casters_lands():
    """ "That creature's controller" is whoever controls the target, not the
    spell's controller."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Weight of Spires"],
            battlefield=[
                "Mountain",
                "Elder Gargaroth",
                "Command Tower",
                "Stomping Ground",
                "Temple of Epiphany",
            ],
        )
        .player("bob", battlefield=["Command Tower"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    own = scenario.creature("Elder Gargaroth", "alice")
    scenario.cast_and_resolve(
        "Weight of Spires", *scenario.untapped_sources("Mountain"), targets=[own]
    )
    assert own.damage == 3


def test_spires_with_its_target_gone_deals_no_damage():
    """CR 608.2b: the only target is illegal, so the spell does nothing."""
    scenario, target = _spires_board(bob_lands=["Command Tower"], bob_creature="Grizzly Bears")
    scenario.cast_onto_stack(
        "Weight of Spires", *scenario.untapped_sources("Mountain"), targets=[target]
    )
    scenario.game.destroy(target)
    scenario.resolve_top()
    assert target.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 20


def test_nonbasic_counts_read_for_you_and_for_a_named_player_alike():
    scenario, _target = _spires_board(
        alice_lands=["Command Tower"], bob_lands=["Command Tower", "Temple of Epiphany"]
    )
    yours = count_expression("the number of nonbasic lands you control")
    assert yours is not None
    assert yours(scenario.game, "alice") == 1
    assert yours(scenario.game, "bob") == 2


# -- Final Punishment: the damage already dealt to that player this turn ------


def _punishment_board(*alice_hand: str, alice_battlefield=(), bob_battlefield=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Final Punishment", *alice_hand],
            battlefield=["Swamp"] * 5 + ["Mountain"] * 3 + list(alice_battlefield),
            library=["Island"] * 3,
        )
        .player("bob", battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _bolt(scenario, target):
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[target]
    )


def _punish(scenario, target):
    scenario.cast_and_resolve(
        "Final Punishment", *scenario.untapped_sources(*["Swamp"] * 5), targets=[target]
    )


def test_final_punishment_with_no_damage_dealt_loses_nothing():
    scenario = _punishment_board()
    _punish(scenario, "bob")
    assert scenario.player("bob").life == 20


def test_final_punishment_repeats_the_damage_the_player_took():
    scenario = _punishment_board("Lightning Bolt")
    _bolt(scenario, "bob")
    assert scenario.player("bob").life == 17
    _punish(scenario, "bob")
    assert scenario.player("bob").life == 14


def test_final_punishment_sums_every_damage_event_this_turn():
    scenario = _punishment_board("Lightning Bolt", "Shock")
    _bolt(scenario, "bob")
    scenario.cast_and_resolve("Shock", *scenario.untapped_sources("Mountain"), targets=["bob"])
    _punish(scenario, "bob")
    assert scenario.player("bob").life == 20 - 3 - 2 - 5


def test_final_punishment_ignores_damage_dealt_to_another_player():
    scenario = _punishment_board("Lightning Bolt")
    _bolt(scenario, "alice")
    _punish(scenario, "bob")
    assert scenario.player("bob").life == 20


def test_final_punishment_ignores_damage_dealt_to_creatures():
    scenario = _punishment_board("Lightning Bolt", bob_battlefield=["Elder Gargaroth"])
    _bolt(scenario, scenario.creature("Elder Gargaroth", "bob"))
    _punish(scenario, "bob")
    assert scenario.player("bob").life == 20


def test_final_punishment_aimed_at_its_caster_counts_the_casters_damage():
    scenario = _punishment_board("Lightning Bolt")
    _bolt(scenario, "alice")
    _punish(scenario, "alice")
    assert scenario.player("alice").life == 20 - 3 - 3


def test_final_punishment_counts_combat_damage():
    """CR 120.3a: combat damage is damage dealt to the player like any other."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Final Punishment"],
            battlefield=["Grizzly Bears", *["Swamp"] * 5],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))
    scenario.no_blocks()
    scenario.combat_damage()
    assert scenario.player("bob").life == 18
    scenario.turn.advance_to(Step.POSTCOMBAT_MAIN)
    scenario.game.sync_priority_with_step()
    _punish(scenario, "bob")
    assert scenario.player("bob").life == 16


def test_final_punishment_does_not_count_prevented_damage():
    """CR 615.6: prevented damage is never dealt, so Bandage's prevented point
    is not part of what Final Punishment repeats."""
    scenario = _punishment_board("Lightning Bolt", "Bandage", alice_battlefield=["Plains"])
    scenario.cast_and_resolve("Bandage", *scenario.untapped_sources("Plains"), targets=["bob"])
    _bolt(scenario, "bob")
    assert scenario.player("bob").life == 18
    _punish(scenario, "bob")
    assert scenario.player("bob").life == 16


# -- Cerebral Vortex: the number of cards they've drawn this turn ------------


def _vortex_board(extra_hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cerebral Vortex", "Cerebral Vortex", *extra_hand],
            battlefield=["Island", "Island", "Mountain", "Island", "Island", "Mountain"],
            library=["Island"] * 10,
        )
        .player("bob", library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _vortex(scenario, target):
    scenario.cast_and_resolve(
        "Cerebral Vortex",
        *scenario.untapped_sources("Island", "Island", "Mountain"),
        targets=[target],
    )


def test_vortex_draws_two_then_deals_the_cards_drawn_this_turn():
    scenario = _vortex_board()
    _vortex(scenario, "bob")
    assert len(scenario.player("bob").hand) == 2
    assert scenario.player("bob").life == 18


def test_vortex_counts_cards_drawn_earlier_this_turn():
    scenario = _vortex_board()
    _vortex(scenario, "bob")
    _vortex(scenario, "bob")
    assert scenario.player("bob").life == 20 - 2 - 4


def test_vortex_counts_the_targets_draws_not_the_casters():
    scenario = _vortex_board()
    _vortex(scenario, "alice")
    assert scenario.player("alice").life == 18
    _vortex(scenario, "bob")
    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 18


def test_vortex_aimed_at_its_caster_counts_the_casters_draws():
    scenario = _vortex_board()
    _vortex(scenario, "alice")
    assert scenario.player("alice").life == 18
    assert len(scenario.player("alice").hand) == 3  # one Vortex left, plus two drawn


def test_a_library_that_runs_short_counts_only_the_cards_actually_drawn():
    """CR 121.1: only cards that were drawn count - a one-card library gives
    one draw, so the damage is one."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cerebral Vortex"],
            battlefield=["Island", "Island", "Mountain"],
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _vortex(scenario, "bob")
    assert scenario.player("bob").life == 19


# -- Proof printings: the same terms read on other cards ----------------------


def test_anathemancer_enters_for_the_number_of_nonbasic_lands_that_player_controls():
    scenario = (
        Scenario()
        .player("alice", hand=["Anathemancer"], battlefield=["Swamp", "Mountain", "Mountain"])
        .player("bob", battlefield=["Command Tower", "Temple of Epiphany", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Anathemancer", [scenario.player("bob")])
    scenario.cast_onto_stack(
        "Anathemancer", *scenario.untapped_sources("Swamp", "Mountain", "Mountain")
    )
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    assert scenario.player("bob").life == 18


def test_sunspine_lynx_deals_each_player_their_own_nonbasic_land_count():
    scenario = (
        Scenario()
        .player("alice", hand=["Sunspine Lynx"], battlefield=["Mountain"] * 4)
        .player("bob", battlefield=["Command Tower", "Temple of Epiphany", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack("Sunspine Lynx", *scenario.untapped_sources(*["Mountain"] * 4))
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 20


def test_each_player_term_counts_each_players_own_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sunspine Lynx"],
            battlefield=["Mountain"] * 4 + ["Command Tower", "Stomping Ground"],
        )
        .player("bob", battlefield=["Command Tower"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack("Sunspine Lynx", *scenario.untapped_sources(*["Mountain"] * 4))
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    assert scenario.player("alice").life == 18
    assert scenario.player("bob").life == 19
