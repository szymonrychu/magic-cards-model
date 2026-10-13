"""EP-02 R3 T2: counter and X amounts read off the source or a referenced object.

Rabble-Rouser: "Attacking creatures get +X/+0 until end of turn, where X is
this creature's power." The mass pump's "+X" slot may sit in either stat
(CR 608.2h: X is taken once as the ability resolves; CR 611.2c: the set of
affected creatures is fixed when the effect begins).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _characteristics(scenario, card):
    return scenario.game.characteristics_of(card).power_toughness


def _rabble_scenario(extra=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Rabble-Rouser", "Grizzly Bears", "Savannah Lions", "Mountain", *extra],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def test_rabble_rouser_pumps_attackers_by_its_own_power():
    scenario = _rabble_scenario()
    rouser = scenario.find("Rabble-Rouser", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.activate(rouser, *scenario.untapped_sources("Mountain"), index=0)
    scenario.resolve_top()
    # Rabble-Rouser is a 1/1; the Bears (2/2) attack and get +1/+0.
    assert _characteristics(scenario, bears) == (3, 2)


def test_rabble_rouser_leaves_non_attackers_alone():
    scenario = _rabble_scenario()
    rouser = scenario.find("Rabble-Rouser", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "alice")
    scenario.attack_with(bears)
    scenario.activate(rouser, *scenario.untapped_sources("Mountain"), index=0)
    scenario.resolve_top()
    assert _characteristics(scenario, lions) == (2, 1)


def test_rabble_rouser_x_counts_its_plus_one_counters():
    scenario = _rabble_scenario()
    rouser = scenario.find("Rabble-Rouser", Zone.BATTLEFIELD, "alice")
    rouser.add_counters(Counter.PLUS_ONE, 2)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.activate(rouser, *scenario.untapped_sources("Mountain"), index=0)
    scenario.resolve_top()
    assert _characteristics(scenario, bears) == (5, 2)


def test_rabble_rouser_pumps_only_creatures_attacking_when_it_resolves():
    scenario = _rabble_scenario()
    rouser = scenario.find("Rabble-Rouser", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "alice")
    scenario.attack_with(bears, lions)
    scenario.activate(rouser, *scenario.untapped_sources("Mountain"), index=0)
    scenario.resolve_top()
    assert _characteristics(scenario, bears) == (3, 2)
    assert _characteristics(scenario, lions) == (3, 1)


def _settle(scenario, limit=16):
    """Put triggers on the stack and resolve until the stack is empty."""
    for _ in range(limit):
        scenario.game.put_triggers_on_stack()
        if not scenario.stack_names():
            return
        scenario.pass_until_resolved()
    raise AssertionError(f"stack never emptied: {scenario.stack_names()}")


def _main_board(*battlefield, hand=(), opponent=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=list(battlefield), hand=list(hand), library=["Forest"] * 8)
        .player("bob", battlefield=list(opponent), library=["Forest"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _named(scenario, name):
    return [c for c in scenario.game.permanents_controlled_by("alice") if c.name == name]


# -- Fabricate N (CR 702.123a): counters on it, or N Servo tokens if you do not


def test_fabricate_taken_puts_the_counters_on_the_creature():
    scenario = _main_board(hand=["Cultivator of Blades"])
    scenario.will_take_the_may(True)
    cultivator = scenario.put_onto_battlefield("Cultivator of Blades")
    _settle(scenario)
    assert cultivator.counter_count(Counter.PLUS_ONE) == 2
    assert _named(scenario, "Servo Token") == []


def test_fabricate_declined_makes_that_many_servos_instead():
    scenario = _main_board(hand=["Cultivator of Blades"])
    scenario.will_take_the_may(False)
    cultivator = scenario.put_onto_battlefield("Cultivator of Blades")
    _settle(scenario)
    assert cultivator.counter_count(Counter.PLUS_ONE) == 0
    assert len(_named(scenario, "Servo Token")) == 2


def test_fabricate_one_scales_down_to_a_single_counter_or_servo():
    scenario = _main_board(hand=["Maulfist Squad"])
    scenario.will_take_the_may(False)
    scenario.put_onto_battlefield("Maulfist Squad")
    _settle(scenario)
    assert len(_named(scenario, "Servo Token")) == 1


def test_fabricate_two_on_a_second_printing_with_counters():
    scenario = _main_board(hand=["Angel of Invention"])
    scenario.will_take_the_may(True)
    angel = scenario.put_onto_battlefield("Angel of Invention")
    _settle(scenario)
    assert angel.counter_count(Counter.PLUS_ONE) == 2


# -- Cultivator of Blades: "you may have other attacking creatures get +X/+X"


def _cultivator_attack(take_the_may=True, extra=("Savannah Lions",), counters=0, bystanders=()):
    scenario = _main_board("Cultivator of Blades", "Grizzly Bears", *extra, *bystanders)
    cultivator = scenario.creature("Cultivator of Blades", "alice")
    if counters:
        cultivator.add_counters(Counter.PLUS_ONE, counters)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_take_the_may(take_the_may)
    scenario.attack_with(cultivator, bears)
    _settle(scenario)
    return scenario, cultivator, bears


def test_cultivator_pumps_other_attackers_by_its_power():
    scenario, cultivator, bears = _cultivator_attack()
    # Cultivator is a 1/1: the attacking Bears get +1/+1, Cultivator itself nothing.
    assert _characteristics(scenario, bears) == (3, 3)
    assert _characteristics(scenario, cultivator) == (1, 1)


def test_cultivator_x_includes_its_own_counters():
    scenario, cultivator, bears = _cultivator_attack(counters=2)
    assert _characteristics(scenario, bears) == (5, 5)


def test_cultivator_declined_pumps_nothing():
    scenario, _cultivator, bears = _cultivator_attack(take_the_may=False)
    assert _characteristics(scenario, bears) == (2, 2)


def test_cultivator_does_not_pump_creatures_that_are_not_attacking():
    scenario, _cultivator, _bears = _cultivator_attack()
    lions = scenario.creature("Savannah Lions", "alice")
    assert _characteristics(scenario, lions) == (2, 1)


# -- Unleash (CR 702.98a): may enter with a +1/+1 counter; can't block with one


def _blocker_scenario(counter_choice):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Grizzly Bears"],
            hand=["Hellhole Flailer"],
            library=["Forest"] * 8,
        )
        .player("bob", battlefield=["Grizzly Bears"], hand=["Rakdos Drake"], library=["Forest"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(counter_choice)
    return scenario


def test_unleash_taken_enters_with_a_counter():
    scenario = _blocker_scenario(True)
    flailer = scenario.put_onto_battlefield("Hellhole Flailer")
    assert flailer.counter_count(Counter.PLUS_ONE) == 1


def test_unleash_declined_enters_without_a_counter():
    scenario = _blocker_scenario(False)
    flailer = scenario.put_onto_battlefield("Hellhole Flailer")
    assert flailer.counter_count(Counter.PLUS_ONE) == 0


def test_unleashed_creature_with_a_counter_cannot_block():
    from magic_cards_model.machines.combat import block_refusal

    scenario = _blocker_scenario(True)
    drake = scenario.put_onto_battlefield("Rakdos Drake", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    attack = scenario.game.combat.attack_by(bears.id)
    reason = block_refusal(scenario.game, drake, attack)
    assert reason is not None and "unleash" in reason.lower()


def test_unleashed_creature_without_a_counter_can_block():
    from magic_cards_model.machines.combat import block_refusal

    scenario = _blocker_scenario(False)
    drake = scenario.put_onto_battlefield("Rakdos Drake", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    attack = scenario.game.combat.attack_by(bears.id)
    assert block_refusal(scenario.game, drake, attack) is None


def test_unleashed_creature_blocks_again_once_the_counter_is_gone():
    from magic_cards_model.machines.combat import block_refusal

    scenario = _blocker_scenario(True)
    drake = scenario.put_onto_battlefield("Rakdos Drake", "bob")
    drake.remove_counters(Counter.PLUS_ONE, 1)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    attack = scenario.game.combat.attack_by(bears.id)
    assert block_refusal(scenario.game, drake, attack) is None


# -- "target creature you control with the greatest power" (Triumph of Gerrard)
# and its mana-value twin (Culling Scales): a target restriction that compares
# the target to the rest of its group, ties all legal.


def _requirement(text):
    from magic_cards_model.machines.targeting import profile_for_text

    profile = profile_for_text(text)
    assert profile.understood
    return profile.requirements[0]


def _ruling_board():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Hill Giant", "Serra Angel"])
        .player("bob", battlefield=["Hill Giant", "Culling Scales"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_only_a_creature_with_the_greatest_power_among_yours_is_a_legal_target():
    scenario = _ruling_board()
    requirement = _requirement(
        "Put a +1/+1 counter on target creature you control with the greatest power."
    )
    angel = scenario.creature("Serra Angel", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    assert requirement.rejects(angel, "alice", scenario.game) is None
    assert requirement.rejects(giant, "alice", scenario.game) is not None
    assert requirement.rejects(bears, "alice", scenario.game) is not None


def test_greatest_power_ignores_the_opponents_bigger_creature():
    scenario = _ruling_board()
    scenario.creature("Hill Giant", "bob").add_counters(Counter.PLUS_ONE, 5)
    requirement = _requirement(
        "Put a +1/+1 counter on target creature you control with the greatest power."
    )
    assert (
        requirement.rejects(scenario.creature("Serra Angel", "alice"), "alice", scenario.game)
        is None
    )


def test_ties_for_greatest_power_are_all_legal():
    scenario = _ruling_board()
    scenario.creature("Hill Giant", "alice").add_counters(Counter.PLUS_ONE, 1)
    requirement = _requirement(
        "Put a +1/+1 counter on target creature you control with the greatest power."
    )
    assert (
        requirement.rejects(scenario.creature("Hill Giant", "alice"), "alice", scenario.game)
        is None
    )
    assert (
        requirement.rejects(scenario.creature("Serra Angel", "alice"), "alice", scenario.game)
        is None
    )
    assert (
        requirement.rejects(scenario.creature("Grizzly Bears", "alice"), "alice", scenario.game)
        is not None
    )


def test_greatest_power_follows_a_pump_in_response():
    scenario = _ruling_board()
    requirement = _requirement(
        "Put a +1/+1 counter on target creature you control with the greatest power."
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 3)
    assert requirement.rejects(bears, "alice", scenario.game) is None


def test_lowest_mana_value_target_restriction():
    scenario = _ruling_board()
    requirement = _requirement("Destroy target nonland permanent with the lowest mana value.")
    scales = scenario.find("Culling Scales", Zone.BATTLEFIELD, "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    # Grizzly Bears (2) is the cheapest nonland permanent; Culling Scales (3) is not.
    assert requirement.rejects(bears, "alice", scenario.game) is None
    assert requirement.rejects(scales, "alice", scenario.game) is not None


def _advance_saga(scenario, saga):
    scenario.game.add_counters(saga, Counter.LORE, 1)
    _settle(scenario)


def test_triumph_of_gerrard_chapters_go_to_the_greatest_power_creature():
    from magic_cards_model.machines.combat import Keyword, has_keyword

    scenario = (
        Scenario()
        .player("alice", battlefield=["Triumph of Gerrard", "Grizzly Bears", "Hill Giant"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = scenario.find("Triumph of Gerrard", Zone.BATTLEFIELD, "alice")
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    # The scenario builds the Saga with its first lore counter already on it
    # (chapter I not run), so the next two counters are chapters II and III.
    _advance_saga(scenario, saga)
    assert giant.counter_count(Counter.PLUS_ONE) == 1
    assert bears.counter_count(Counter.PLUS_ONE) == 0
    _advance_saga(scenario, saga)
    for keyword in (Keyword.FLYING, Keyword.FIRST_STRIKE, Keyword.LIFELINK):
        assert has_keyword(giant, keyword, scenario.game)
        assert not has_keyword(bears, keyword, scenario.game)


# -- Fall of the Impostor III: "Exile a creature with the greatest power among
# creatures target opponent controls." (not targeted at the creature)


def _fall_board(bob=("Hill Giant", "Grizzly Bears")):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Fall of the Impostor", "Serra Angel"])
        .player("bob", battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = scenario.find("Fall of the Impostor", Zone.BATTLEFIELD, "alice")
    # The scenario builds the Saga with its first lore counter on it, so the
    # next two counters are chapters II and III.
    return scenario, saga


def test_fall_of_the_impostor_exiles_the_opponents_greatest_power_creature():
    scenario, saga = _fall_board()
    scenario.game.add_counters(saga, Counter.LORE, 1)
    _settle(scenario)
    scenario.game.add_counters(saga, Counter.LORE, 1)
    _settle(scenario)
    assert [c.name for c in scenario.game.permanents_controlled_by("bob")] == ["Grizzly Bears"]
    assert any(c.name == "Hill Giant" for c in scenario.game.exile)
    # My own bigger creature is not in the opponent's group.
    assert scenario.creature("Serra Angel", "alice").zone is Zone.BATTLEFIELD


def test_fall_of_the_impostor_tie_is_the_controllers_choice():
    scenario, saga = _fall_board(("Hill Giant", "Hill Giant"))
    giants = [c for c in scenario.game.permanents_controlled_by("bob")]
    scenario.game.add_counters(saga, Counter.LORE, 1)
    _settle(scenario)
    scenario.will_choose_cards(giants[1], username="alice")
    scenario.game.add_counters(saga, Counter.LORE, 1)
    _settle(scenario)
    assert giants[1].zone is Zone.EXILE
    assert giants[0].zone is Zone.BATTLEFIELD


def test_fall_of_the_impostor_does_nothing_against_an_empty_board():
    scenario, saga = _fall_board(())
    scenario.game.add_counters(saga, Counter.LORE, 1)
    _settle(scenario)
    scenario.game.add_counters(saga, Counter.LORE, 1)
    _settle(scenario)
    assert saga.zone is Zone.GRAVEYARD


# -- Outlaw Stitcher: "two +1/+1 counters ... for each spell you've cast this
# turn other than the first"


def _cast_stitcher(prior_spells):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Outlaw Stitcher", *(["Shock"] * prior_spells)],
            battlefield=["Island"] * 4 + ["Mountain"] * (prior_spells + 1),
            library=["Forest"] * 8,
        )
        .player("bob", library=["Forest"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for _ in range(prior_spells):
        scenario.cast_and_resolve("Shock", *scenario.untapped_sources("Mountain"), targets=["bob"])
    scenario.cast_and_resolve(
        "Outlaw Stitcher", *scenario.untapped_sources("Island", "Island", "Island", "Island")
    )
    _settle(scenario)
    return scenario


def _zombie(scenario):
    return [c for c in scenario.game.permanents_controlled_by("alice") if "Zombie" in c.name][0]


def test_outlaw_stitcher_as_the_first_spell_adds_no_counters():
    scenario = _cast_stitcher(0)
    assert _zombie(scenario).counter_count(Counter.PLUS_ONE) == 0


def test_outlaw_stitcher_as_the_second_spell_adds_two_counters():
    scenario = _cast_stitcher(1)
    assert _zombie(scenario).counter_count(Counter.PLUS_ONE) == 2


def test_outlaw_stitcher_as_the_third_spell_adds_four_counters():
    scenario = _cast_stitcher(2)
    assert _zombie(scenario).counter_count(Counter.PLUS_ONE) == 4


# -- Geralf, the Fleshwright: "put a +1/+1 counter on it for each other Zombie
# that entered the battlefield under your control this turn"


def _geralf_after_spells(spells):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Shock"] * spells,
            battlefield=["Geralf, the Fleshwright"] + ["Mountain"] * spells,
            library=["Forest"] * 8,
        )
        .player("bob", library=["Forest"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for _ in range(spells):
        scenario.cast_and_resolve("Shock", *scenario.untapped_sources("Mountain"), targets=["bob"])
        _settle(scenario)
    return scenario


def _zombies(scenario):
    return [c for c in scenario.game.permanents_controlled_by("alice") if "Zombie" in c.name]


def test_geralf_first_zombie_has_no_other_zombie_so_no_counter():
    scenario = _geralf_after_spells(2)
    zombies = _zombies(scenario)
    assert len(zombies) == 1
    assert zombies[0].counter_count(Counter.PLUS_ONE) == 0


def test_geralf_second_zombie_counts_the_first_one():
    scenario = _geralf_after_spells(3)
    zombies = _zombies(scenario)
    assert len(zombies) == 2
    assert sorted(z.counter_count(Counter.PLUS_ONE) for z in zombies) == [0, 1]


def test_geralf_third_zombie_counts_both_earlier_ones():
    scenario = _geralf_after_spells(4)
    zombies = _zombies(scenario)
    assert len(zombies) == 3
    assert sorted(z.counter_count(Counter.PLUS_ONE) for z in zombies) == [0, 1, 2]


# -- "during your turn other than your first spell that turn" (Geralf's token
# trigger): the cast trigger condition reads "other than your first spell"


def test_geralf_makes_no_zombie_for_the_first_spell_of_the_turn():
    scenario = _geralf_after_spells(1)
    assert _zombies(scenario) == []


def test_geralf_makes_a_zombie_for_each_later_spell_of_the_turn():
    scenario = _geralf_after_spells(3)
    assert len(_zombies(scenario)) == 2
