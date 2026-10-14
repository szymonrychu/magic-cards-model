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


# -- Kutzil's Flanker: "a +1/+1 counter ... for each creature that left the
# battlefield under your control this turn" (mode 1)


def _flanker_after(departures):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Kutzil's Flanker", "Shock", "Shock"][: 1 + departures],
            battlefield=["Plains"] * 3 + ["Mountain"] * 2 + ["Grizzly Bears", "Savannah Lions"],
            library=["Forest"] * 8,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    victims = ["Grizzly Bears", "Savannah Lions"][:departures]
    for victim in victims:
        scenario.cast_and_resolve(
            "Shock",
            *scenario.untapped_sources("Mountain"),
            targets=[scenario.creature(victim, "alice")],
        )
    scenario.will_choose_mode(
        "Put a +1/+1 counter on this creature for each creature that left the battlefield "
        "under your control this turn."
    )
    scenario.cast_and_resolve(
        "Kutzil's Flanker", *scenario.untapped_sources("Plains", "Plains", "Plains")
    )
    _settle(scenario)
    return scenario


def test_kutzils_flanker_counts_creatures_that_left_under_your_control():
    scenario = _flanker_after(2)
    (flanker,) = _named(scenario, "Kutzil's Flanker")
    assert flanker.counter_count(Counter.PLUS_ONE) == 2


def test_kutzils_flanker_counts_one_departure():
    scenario = _flanker_after(1)
    (flanker,) = _named(scenario, "Kutzil's Flanker")
    assert flanker.counter_count(Counter.PLUS_ONE) == 1


def test_kutzils_flanker_with_no_departures_gets_nothing():
    scenario = _flanker_after(0)
    (flanker,) = _named(scenario, "Kutzil's Flanker")
    assert flanker.counter_count(Counter.PLUS_ONE) == 0


def test_kutzils_flanker_ignores_an_opponents_creature_leaving():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Kutzil's Flanker", "Shock"],
            battlefield=["Plains"] * 3 + ["Mountain"],
            library=["Forest"] * 8,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Shock",
        *scenario.untapped_sources("Mountain"),
        targets=[scenario.creature("Grizzly Bears", "bob")],
    )
    scenario.will_choose_mode(
        "Put a +1/+1 counter on this creature for each creature that left the battlefield "
        "under your control this turn."
    )
    scenario.cast_and_resolve(
        "Kutzil's Flanker", *scenario.untapped_sources("Plains", "Plains", "Plains")
    )
    _settle(scenario)
    (flanker,) = _named(scenario, "Kutzil's Flanker")
    assert flanker.counter_count(Counter.PLUS_ONE) == 0


# -- Emergent Sequence: a land becomes a 0/0 Fractal; a counter per land that
# entered under your control this turn


def _emergent(lands_played):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Emergent Sequence", *["Forest"] * lands_played],
            battlefield=["Forest", "Island"],
            library=["Forest", "Island", "Forest", "Forest"],
        )
        .player("bob", library=["Forest"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for _ in range(lands_played):
        scenario.put_onto_battlefield("Forest", "alice")
    scenario.cast_and_resolve("Emergent Sequence", *scenario.untapped_sources("Forest", "Island"))
    _settle(scenario)
    return scenario


def _fractal_land(scenario):
    found = [
        c
        for c in scenario.game.permanents_controlled_by("alice")
        if c.counter_count(Counter.PLUS_ONE)
        or "Fractal" in str(scenario.game.characteristics_of(c).subtypes)
    ]
    assert len(found) == 1
    return found[0]


def test_emergent_sequence_land_enters_alone_is_a_one_one_fractal_land():
    scenario = _emergent(0)
    land = _fractal_land(scenario)
    chars = scenario.game.characteristics_of(land)
    assert chars.is_creature and chars.is_land
    assert land.tapped
    assert scenario.game.power_of(land) == 1
    assert land.counter_count(Counter.PLUS_ONE) == 1


def test_emergent_sequence_counts_a_land_played_earlier_this_turn():
    scenario = _emergent(2)
    land = _fractal_land(scenario)
    assert land.counter_count(Counter.PLUS_ONE) == 3
    assert scenario.game.power_of(land) == 3


# -- Sovereign Okinec Ahau: counters equal to power minus base power, for each
# creature you control


def _okinec_attack(*extra, pump=None, opponent=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Giant Growth"] if pump else [],
            battlefield=["Sovereign Okinec Ahau", "Forest", *extra],
            library=["Forest"] * 8,
        )
        .player("bob", battlefield=list(opponent), library=["Forest"] * 8)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def test_okinec_trigger_adds_the_difference_to_each_pumped_creature():
    scenario = _okinec_attack("Grizzly Bears", "Savannah Lions")
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "alice")
    bears.add_counters(Counter.PLUS_ONE, 2)
    okinec = scenario.creature("Sovereign Okinec Ahau", "alice")
    scenario.attack_with(okinec)
    _settle(scenario)
    assert bears.counter_count(Counter.PLUS_ONE) == 4
    assert lions.counter_count(Counter.PLUS_ONE) == 0
    assert okinec.counter_count(Counter.PLUS_ONE) == 0


def test_okinec_counts_itself_when_it_is_bigger_than_its_base_power():
    scenario = _okinec_attack()
    okinec = scenario.creature("Sovereign Okinec Ahau", "alice")
    okinec.add_counters(Counter.PLUS_ONE, 1)
    scenario.attack_with(okinec)
    _settle(scenario)
    assert okinec.counter_count(Counter.PLUS_ONE) == 2


def test_okinec_counts_a_temporary_pump_too():
    scenario = _okinec_attack("Grizzly Bears", pump=True)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Giant Growth", *scenario.untapped_sources("Forest"), targets=[bears])
    okinec = scenario.creature("Sovereign Okinec Ahau", "alice")
    scenario.attack_with(okinec)
    _settle(scenario)
    assert bears.counter_count(Counter.PLUS_ONE) == 3


def test_okinec_ignores_the_opponents_creatures():
    scenario = _okinec_attack(opponent=["Grizzly Bears"])
    theirs = scenario.creature("Grizzly Bears", "bob")
    theirs.add_counters(Counter.PLUS_ONE, 2)
    scenario.attack_with(scenario.creature("Sovereign Okinec Ahau", "alice"))
    _settle(scenario)
    assert theirs.counter_count(Counter.PLUS_ONE) == 2


# -- Bounding Felidar: "attacks while saddled": a counter on each other creature,
# 1 life per creature


def _saddle_felidar(scenario, *saddlers):
    from magic_cards_model.machines.keywords import saddle_activation

    mount = scenario.creature("Bounding Felidar", "alice")
    activation = saddle_activation(scenario.game, mount, list(saddlers), "alice")
    assert activation.why_not() is None
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()
    scenario.pass_until_resolved()
    return mount


def _felidar_board():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Bounding Felidar", "Grizzly Bears", "Savannah Lions", "Memnite"],
            library=["Plains"] * 5,
        )
        .player("bob", library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_bounding_felidar_saddled_attack_pumps_each_other_creature_and_gains_life():
    scenario = _felidar_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    mount = _saddle_felidar(scenario, bears)
    life = scenario.player("alice").life
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(mount)
    _settle(scenario)
    others = [c for c in scenario.game.permanents_controlled_by("alice") if c is not mount]
    assert len(others) == 3
    assert all(c.counter_count(Counter.PLUS_ONE) == 1 for c in others)
    assert mount.counter_count(Counter.PLUS_ONE) == 0
    assert scenario.player("alice").life == life + 3


def test_bounding_felidar_unsaddled_attack_does_nothing():
    scenario = _felidar_board()
    mount = scenario.creature("Bounding Felidar", "alice")
    life = scenario.player("alice").life
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(mount)
    _settle(scenario)
    assert scenario.player("alice").life == life
    assert scenario.creature("Memnite", "alice").counter_count(Counter.PLUS_ONE) == 0


# -- Spire Mechcycle: exhaust, a counter per other Mount/Vehicle you control


def test_spire_mechcycle_exhaust_counts_other_mounts_and_vehicles():
    scenario = _main_board("Spire Mechcycle", "Bounding Felidar", "Spire Mechcycle")
    cycles = _named(scenario, "Spire Mechcycle")
    felidar = _named(scenario, "Bounding Felidar")[0]
    scenario.activate(cycles[0], tapping_for_cost=[cycles[1]], index=0)
    _settle(scenario)
    # the other Vehicle (tapped as the cost) and the Mount: two others
    assert cycles[0].counter_count(Counter.PLUS_ONE) == 2
    assert scenario.game.characteristics_of(cycles[0]).is_creature
    del felidar


def test_spire_mechcycle_exhaust_is_once_only():
    scenario = _main_board("Spire Mechcycle", "Bounding Felidar", "Bounding Felidar")
    cycle = _named(scenario, "Spire Mechcycle")[0]
    felidars = _named(scenario, "Bounding Felidar")
    scenario.activate(cycle, tapping_for_cost=[felidars[0]], index=0)
    _settle(scenario)
    assert cycle.counter_count(Counter.PLUS_ONE) == 2
    assert scenario.why_cannot_activate(cycle, 0, "alice")


# -- The Goose Mother: enters with X counters; half X Food, rounded up


def _goose(x):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["The Goose Mother"],
            battlefield=["Forest"] * 5 + ["Island"] * 2,
            library=["Forest"] * 8,
        )
        .player("bob", library=["Forest"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spell = scenario.find("The Goose Mother", Zone.HAND, "alice")
    scenario.game.cast(
        spell,
        "alice",
        x_value=x,
        mana_sources=scenario.untapped_sources(*(["Forest"] * (x + 1)), "Island"),
    )
    scenario.pass_until_resolved()
    _settle(scenario)
    return scenario


def _food(scenario):
    return [c for c in scenario.game.permanents_controlled_by("alice") if c.name.startswith("Food")]


def test_goose_mother_x_three_makes_two_food():
    scenario = _goose(3)
    (goose,) = _named(scenario, "The Goose Mother")
    assert goose.counter_count(Counter.PLUS_ONE) == 3
    assert len(_food(scenario)) == 2


def test_goose_mother_x_four_makes_two_food():
    scenario = _goose(4)
    assert len(_food(scenario)) == 2


def test_goose_mother_x_one_makes_one_food():
    scenario = _goose(1)
    assert len(_food(scenario)) == 1


# -- Contagion Engine: "Proliferate twice."


def _engine_board():
    scenario = _main_board(
        "Contagion Engine",
        "Plains",
        "Plains",
        "Plains",
        "Plains",
        "Grizzly Bears",
        "Savannah Lions",
    )
    return scenario


def test_contagion_engine_proliferates_twice_choosing_each_time():
    scenario = _engine_board()
    engine = _named(scenario, "Contagion Engine")[0]
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 1)
    scenario.will_choose_cards(bears, times=2)
    scenario.activate(engine, *scenario.untapped_sources("Plains", "Plains", "Plains", "Plains"))
    _settle(scenario)
    assert bears.counter_count(Counter.PLUS_ONE) == 3


def test_contagion_engine_proliferates_every_chosen_permanent_each_time():
    scenario = _engine_board()
    engine = _named(scenario, "Contagion Engine")[0]
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "alice")
    bears.add_counters(Counter.PLUS_ONE, 1)
    lions.add_counters(Counter.PLUS_ONE, 1)
    scenario.will_choose_cards(bears, lions, times=2)
    scenario.activate(engine, *scenario.untapped_sources("Plains", "Plains", "Plains", "Plains"))
    _settle(scenario)
    assert bears.counter_count(Counter.PLUS_ONE) == 3
    assert lions.counter_count(Counter.PLUS_ONE) == 3


def test_contagion_engine_enters_with_minus_counters_on_a_players_creatures():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Contagion Engine"], battlefield=["Plains"] * 6, library=["Forest"] * 8
        )
        .player("bob", battlefield=["Grizzly Bears", "Savannah Lions"], library=["Forest"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Contagion Engine", *scenario.untapped_sources(*["Plains"] * 6))
    scenario.game.put_triggers_on_stack()
    scenario.choose_trigger_targets("Contagion Engine", ["bob"])
    _settle(scenario)
    assert scenario.stack_names() == []


# -- Expand the Sphere: lands from the top six; proliferate for the shortfall


def _sphere(lands_on_top, *, creature_counters=1):
    top = ["Forest"] * lands_on_top + ["Grizzly Bears"] * (6 - lands_on_top)
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Expand the Sphere"],
            battlefield=["Forest"] * 4 + ["Savannah Lions"],
            library=top + ["Island"] * 4,
        )
        .player("bob", library=["Forest"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lions = scenario.creature("Savannah Lions", "alice")
    lions.add_counters(Counter.PLUS_ONE, creature_counters)
    return scenario, lions


def _cast_sphere(scenario, lands, then=None):
    """Answer the land pick first, then (when proliferating) the permanent pick."""
    if lands:
        scenario.will_choose_cards(*lands)
    if then is not None:
        scenario.will_choose_cards(then, times=None)
    scenario.cast_and_resolve("Expand the Sphere", *scenario.untapped_sources(*["Forest"] * 4))
    _settle(scenario)


def test_expand_the_sphere_two_lands_no_proliferate():
    scenario, lions = _sphere(3)
    forests = [c for c in scenario.player("alice").library[:6] if c.name == "Forest"]
    _cast_sphere(scenario, forests[:2])
    on_battlefield = _named(scenario, "Forest")
    assert len(on_battlefield) == 6
    assert sum(1 for f in on_battlefield if f.tapped) >= 2
    assert lions.counter_count(Counter.PLUS_ONE) == 1


def test_expand_the_sphere_one_land_proliferates_once():
    scenario, lions = _sphere(1)
    forest = [c for c in scenario.player("alice").library[:6] if c.name == "Forest"]
    _cast_sphere(scenario, forest, then=lions)
    assert lions.counter_count(Counter.PLUS_ONE) == 2


def test_expand_the_sphere_no_lands_proliferates_twice():
    scenario, lions = _sphere(0)
    _cast_sphere(scenario, [], then=lions)
    assert lions.counter_count(Counter.PLUS_ONE) == 3


def test_expand_the_sphere_rest_go_to_the_bottom_of_the_library():
    scenario, _ = _sphere(2)
    library_before = len(scenario.player("alice").library)
    forests = [c for c in scenario.player("alice").library[:6] if c.name == "Forest"]
    _cast_sphere(scenario, forests)
    library = scenario.player("alice").library
    assert len(library) == library_before - 2
    assert [c.name for c in library[:4]] == ["Island"] * 4
    assert [c.name for c in library[4:]] == ["Grizzly Bears"] * 4


# -- Lethal Exploit: -2/-2, an additional -1/-1 per modified creature you
# controlled as you cast it (CR 700.9, CR 601.2i)


def _exploit_board(*, modified=0, equipped=False):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lethal Exploit"],
            battlefield=["Swamp", "Swamp", "Grizzly Bears", "Savannah Lions", "Memnite"]
            + (["Bonesplitter"] if equipped else []),
            library=["Forest"] * 8,
        )
        .player("bob", battlefield=["Hill Giant"], library=["Forest"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for name in ["Grizzly Bears", "Savannah Lions", "Memnite"][:modified]:
        scenario.creature(name, "alice").add_counters(Counter.PLUS_ONE, 1)
    return scenario


def _giant(scenario):
    return scenario.creature("Hill Giant", "bob")


def test_lethal_exploit_with_no_modified_creature_is_just_minus_two():
    scenario = _exploit_board()
    giant = _giant(scenario)
    scenario.cast_and_resolve(
        "Lethal Exploit", *scenario.untapped_sources("Swamp", "Swamp"), targets=[giant]
    )
    assert scenario.game.power_of(giant) == 1
    assert giant.zone is Zone.BATTLEFIELD


def test_lethal_exploit_one_modified_creature_adds_minus_one():
    scenario = _exploit_board(modified=1)
    giant = _giant(scenario)
    scenario.cast_and_resolve(
        "Lethal Exploit", *scenario.untapped_sources("Swamp", "Swamp"), targets=[giant]
    )
    scenario.state_based_actions()
    assert giant.zone is Zone.GRAVEYARD


def test_lethal_exploit_counts_each_modified_creature_once():
    scenario = _exploit_board(modified=2)
    giant = _giant(scenario)
    giant.add_counters(Counter.PLUS_ONE, 2)  # 5/5, two modified creatures: -4/-4
    scenario.cast_and_resolve(
        "Lethal Exploit", *scenario.untapped_sources("Swamp", "Swamp"), targets=[giant]
    )
    assert scenario.game.power_of(giant) == 1
    assert giant.zone is Zone.BATTLEFIELD


def test_lethal_exploit_three_modified_creatures_kill_a_five_five():
    scenario = _exploit_board(modified=3)
    giant = _giant(scenario)
    giant.add_counters(Counter.PLUS_ONE, 2)
    scenario.cast_and_resolve(
        "Lethal Exploit", *scenario.untapped_sources("Swamp", "Swamp"), targets=[giant]
    )
    scenario.state_based_actions()
    assert giant.zone is Zone.GRAVEYARD


def test_lethal_exploit_counts_equipment_as_a_modification():
    scenario = _exploit_board(equipped=True)
    equipment = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    equipment.attach_to(scenario.creature("Grizzly Bears", "alice"))
    giant = _giant(scenario)
    scenario.cast_and_resolve(
        "Lethal Exploit", *scenario.untapped_sources("Swamp", "Swamp"), targets=[giant]
    )
    scenario.state_based_actions()
    assert giant.zone is Zone.GRAVEYARD


def test_lethal_exploit_count_is_fixed_as_it_is_cast():
    scenario = _exploit_board(modified=1)
    giant = _giant(scenario)
    scenario.cast_onto_stack(
        "Lethal Exploit", *scenario.untapped_sources("Swamp", "Swamp"), targets=[giant]
    )
    scenario.creature("Grizzly Bears", "alice").remove_counters(Counter.PLUS_ONE, 1)
    scenario.resolve_top()
    scenario.state_based_actions()
    assert giant.zone is Zone.GRAVEYARD


# -- Spell Contortion: "Draw a card for each time Spell Contortion was kicked"
# (multikicker, CR 702.33c/d)


def _kick_contortion(kicks):
    """Alice casts Shock, then Spell Contortion (kicked `kicks` times) on it,
    with no mana left to pay the {2}."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Shock", "Spell Contortion"],
            battlefield=["Mountain"] + ["Island"] * (3 + 2 * kicks),
            library=["Forest"] * 8,
        )
        .player("bob", library=["Forest"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    shock = scenario.cast_onto_stack(
        "Shock", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    spell = scenario.find("Spell Contortion", Zone.HAND, "alice")
    hand_before = len(scenario.player("alice").hand)
    scenario.game.cast(
        spell,
        "alice",
        kicker=kicks,
        targets=[shock],
        mana_sources=scenario.untapped_sources(*["Island"] * (3 + 2 * kicks)),
    )
    scenario.resolve_top()
    assert shock.zone is Zone.GRAVEYARD, "the Shock was countered"
    return scenario, hand_before


def test_spell_contortion_unkicked_draws_nothing():
    scenario, before = _kick_contortion(0)
    assert len(scenario.player("alice").hand) == before - 1


def test_spell_contortion_kicked_twice_draws_two():
    scenario, before = _kick_contortion(2)
    assert len(scenario.player("alice").hand) == before - 1 + 2


def test_spell_contortion_kicked_once_draws_one():
    scenario, before = _kick_contortion(1)
    assert len(scenario.player("alice").hand) == before - 1 + 1


# -- Goliath Hatchery: corrupted upkeep, "choose a creature you control, then draw
# cards equal to its total toxic value" (CR 702.164b)


def _hatchery_upkeep(poison, *, battlefield=("Goliath Hatchery", "Plague Nurse", "Grizzly Bears")):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=list(battlefield), library=["Forest"] * 8)
        .player("bob", library=["Forest"] * 8)
        .build()
    )
    scenario.player("bob").add_counters(Counter.POISON, poison)
    scenario.start_at(Step.UNTAP)
    scenario.advance()
    assert scenario.step is Step.UPKEEP
    scenario.game.put_triggers_on_stack()
    return scenario


def test_goliath_hatchery_draws_the_chosen_creatures_total_toxic_value():
    scenario = _hatchery_upkeep(3)
    nurse = scenario.creature("Plague Nurse", "alice")
    hand = len(scenario.player("alice").hand)
    scenario.will_choose_cards(nurse)
    _settle(scenario)
    assert len(scenario.player("alice").hand) == hand + 2


def test_goliath_hatchery_choosing_a_creature_without_toxic_draws_nothing():
    scenario = _hatchery_upkeep(3)
    bears = scenario.creature("Grizzly Bears", "alice")
    hand = len(scenario.player("alice").hand)
    scenario.will_choose_cards(bears)
    _settle(scenario)
    assert len(scenario.player("alice").hand) == hand


def test_goliath_hatchery_does_nothing_below_three_poison_counters():
    scenario = _hatchery_upkeep(2)
    hand = len(scenario.player("alice").hand)
    _settle(scenario)
    assert len(scenario.player("alice").hand) == hand
