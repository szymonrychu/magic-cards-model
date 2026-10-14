"""EP-02 R3 T6: how many tokens a create-token sentence makes.

The token clause itself ("create a 1/1 Rat creature token") was already read;
what this file proves is the *count* the printed sentence asks for, taken once,
when the instruction is applied (CR 608.2h), and the board facts it counts:

- "a number of ... tokens equal to the number of opponents you have" (Chittering
  Witch, Gluttonous Troll);
- "for each <creature> that died this turn" (Gadrak, Dripping-Tongue Zubera,
  Silent-Chant Zubera, Floating-Dream Zubera, Deadly Embrace) - CR 700.4, read
  from what the creature was as it died (CR 603.10a);
- "for each Equipment / Aura and Equipment attached to <this creature>" (Kemba,
  Valduk, Kellan the Fae-Blooded) - CR 301.5;
- "for each time it was kicked" (Wolfbriar Elemental, Stronghold Arena) -
  CR 702.33d;
- "for each white mana symbol in the mana costs of permanents you control"
  (Springjack Shepherd) - CR 107.4;
- "one plus the number of opponents who control an artifact" (Journey On);
- "the number of differently named creature tokens you control" (Audience with
  Trostani).

Rules looked up this session with `mise run rules:find`: 608.2h, 700.4, 603.10a,
301.5, 702.33d, 107.4, 111.1, 107.3a, 122.1, 202.3.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color, Type
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

LISTED = (
    "Adeline, Resplendent Cathar",
    "Asinine Antics",
    "Audience with Trostani",
    "Become Brutes",
    "Chittering Witch",
    "Cloudspire Coordinator",
    "Cursecloth Wrappings",
    "Dripping-Tongue Zubera",
    "Edward Kenway",
    "Gadrak, the Crown-Scourge",
    "Gemini Engine",
    "Ghalta and Mavren",
    "Goblin Traprunner",
    "Kalitas, Bloodchief of Ghet",
    "Kellan, Daring Traveler",
    "Kemba, Kha Regent",
    "Leonardo da Vinci",
    "Manaform Hellkite",
    "Reckless Crew",
    "Smoky Lounge",
    "Springjack Shepherd",
    "Stone Idol Trap",
    "Twinflame",
    "Twisted Sewer-Witch",
    "Valduk, Keeper of the Flame",
    "Wolfbriar Elemental",
)

PROOFS = (
    "Gluttonous Troll",
    "Silent-Chant Zubera",
    "Floating-Dream Zubera",
    "Rampaging Soulrager",
    "Deadly Embrace",
    "Harried Dronesmith",
    "Stronghold Arena",
)


@pytest.mark.parametrize("name", LISTED + PROOFS)
def test_the_card_reads_handled(name):
    support = card_support(card(name))
    assert support.status == "handled", [
        (clause.kind, clause.status, clause.text[:90]) for clause in support.clauses
    ]


def reach(scenario, step):
    """Advance turn by turn so the step's "at the beginning of" triggers are put
    on the stack as the step begins (CR 603.2)."""
    while scenario.step is not step:
        scenario.advance()


def tokens(scenario, name, username="alice"):
    return [
        state for state in scenario.game.permanents_controlled_by(username) if state.name == name
    ]


# -- a number of tokens equal to the number of opponents you have -----------------


def test_chittering_witch_makes_one_rat_per_opponent():
    scenario = (
        Scenario()
        .player("alice", hand=["Chittering Witch"], battlefield=["Swamp"] * 4)
        .player("bob")
        .player("carol")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Chittering Witch", *scenario.untapped_sources(*(["Swamp"] * 4)))
    scenario.pass_until_resolved()

    assert len(tokens(scenario, "Rat Token")) == 2


def test_chittering_witch_in_a_two_player_game_makes_a_single_rat():
    scenario = (
        Scenario()
        .player("alice", hand=["Chittering Witch"], battlefield=["Swamp"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Chittering Witch", *scenario.untapped_sources(*(["Swamp"] * 4)))
    scenario.pass_until_resolved()

    rats = tokens(scenario, "Rat Token")
    assert len(rats) == 1
    assert scenario.game.power_of(rats[0]) == 1


def test_a_player_who_has_lost_is_not_an_opponent_you_have():
    scenario = (
        Scenario()
        .player("alice", hand=["Chittering Witch"], battlefield=["Swamp"] * 4)
        .player("bob")
        .player("carol")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.conceded.append("carol")
    scenario.cast_and_resolve("Chittering Witch", *scenario.untapped_sources(*(["Swamp"] * 4)))
    scenario.resolve_top()

    assert len(tokens(scenario, "Rat Token")) == 1


def test_gluttonous_troll_makes_a_food_per_opponent():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Gluttonous Troll"], battlefield=["Forest", "Forest", "Swamp", "Forest"]
        )
        .player("bob")
        .player("carol")
        .player("dave")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Gluttonous Troll", *scenario.untapped_sources("Forest", "Forest", "Swamp", "Forest")
    )
    scenario.pass_until_resolved()

    assert len(tokens(scenario, "Food Token")) == 3


# -- for each Equipment attached to this creature ---------------------------------


def test_kemba_makes_a_cat_per_equipment_attached_to_her_at_upkeep():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Kemba, Kha Regent", "Bonesplitter", "Lightning Greaves", "Bonesplitter"],
        )
        .player("bob")
        .build()
    )
    kemba = scenario.creature("Kemba, Kha Regent")
    loose = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    for equipment in scenario.game.permanents_controlled_by("alice"):
        if equipment.name in ("Bonesplitter", "Lightning Greaves") and equipment is not loose:
            equipment.attach_to(kemba)
    attached = [
        state for state in scenario.game.permanents_controlled_by("alice") if state.attached_to
    ]
    assert len(attached) == 2

    reach(scenario, Step.UPKEEP)
    scenario.resolve_top()

    cats = tokens(scenario, "Cat Token")
    assert len(cats) == 2
    assert all(scenario.game.power_of(cat) == 2 for cat in cats)


def test_kemba_with_nothing_attached_makes_no_cat():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Kemba, Kha Regent", "Bonesplitter"])
        .player("bob")
        .build()
    )
    reach(scenario, Step.UPKEEP)
    scenario.resolve_top()

    assert tokens(scenario, "Cat Token") == []


# -- for each creature that died this turn -----------------------------------------


def test_gadrak_makes_a_treasure_per_nontoken_creature_that_died_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Gadrak, the Crown-Scourge", "Grizzly Bears", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for bears in list(scenario.game.battlefield):
        if bears.name == "Grizzly Bears":
            scenario.game.destroy(bears)
    reach(scenario, Step.END_STEP)
    scenario.resolve_top()

    assert len(tokens(scenario, "Treasure Token")) == 3


# -- "Exile it at the beginning of your next end step" ------------------------------


def test_stone_idol_trap_costs_one_less_per_attacker_and_makes_a_6_12_that_leaves_at_end_step():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Stone Idol Trap"],
            battlefield=["Mountain"] * 3 + ["Grizzly Bears"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*scenario.creatures("Grizzly Bears", "Grizzly Bears", "Grizzly Bears"))
    # {5}{R} less {1} for each of the three attacking creatures is {2}{R}.
    scenario.cast_and_resolve(
        "Stone Idol Trap", *scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    )

    (construct,) = tokens(scenario, "Construct Token")
    assert (scenario.game.power_of(construct), scenario.game.toughness_of(construct)) == (6, 12)
    trigger = scenario.game.delayed_triggers.triggers[0]
    assert trigger.only_when_active == "alice"  # "your" next end step, not any end step

    reach(scenario, Step.END_STEP)
    scenario.resolve_top()
    assert construct.zone is Zone.EXILE


def test_a_construct_made_on_the_opponents_turn_waits_for_the_controllers_own_end_step():
    scenario = (
        Scenario()
        .player("bob", battlefield=["Grizzly Bears"], library=["Plains"] * 5)
        .player(
            "alice", hand=["Stone Idol Trap"], battlefield=["Mountain"] * 6, library=["Plains"] * 5
        )
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Grizzly Bears", "bob"), defending="alice")
    scenario.pass_priority("bob")
    scenario.cast_and_resolve(
        "Stone Idol Trap",
        *scenario.untapped_sources(*(["Mountain"] * 5), username="alice"),
        username="alice",
    )
    (construct,) = tokens(scenario, "Construct Token")

    reach(scenario, Step.END_STEP)  # bob's end step
    assert scenario.game.active_player.username == "bob"
    assert scenario.stack_names() == []
    assert construct.zone is Zone.BATTLEFIELD

    scenario.advance()
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    assert scenario.game.active_player.username == "alice"
    scenario.resolve_top()
    assert construct.zone is Zone.EXILE


def test_harried_dronesmith_sacrifices_its_thopter_at_its_controllers_next_end_step():
    scenario = Scenario().player("alice", battlefield=["Harried Dronesmith"]).player("bob").build()
    reach(scenario, Step.BEGINNING_OF_COMBAT)
    scenario.resolve_top()
    (thopter,) = tokens(scenario, "Thopter Token")
    reach(scenario, Step.END_STEP)
    scenario.resolve_top()
    assert thopter.zone is not Zone.BATTLEFIELD


# -- attack triggers that make tokens that are attacking ----------------------------


def attacking_tokens(scenario, name, username="alice"):
    return [token for token in tokens(scenario, name, username) if token in scenario.attackers()]


def test_adeline_makes_a_tapped_and_attacking_human_for_each_opponent_attacking_that_opponent():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Adeline, Resplendent Cathar"])
        .player("bob")
        .player("carol")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Adeline, Resplendent Cathar"), defending="bob")
    scenario.resolve_top()

    humans = tokens(scenario, "Human Token")
    assert len(humans) == 2
    assert all(human.tapped for human in humans)
    defenders = {scenario.game.combat.attack_by(human.id).defender for human in humans}
    assert {str(defender) for defender in defenders} == {"bob", "carol"}


def test_adeline_in_a_two_player_game_makes_one_human():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Adeline, Resplendent Cathar"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Adeline, Resplendent Cathar"))
    scenario.resolve_top()

    (human,) = tokens(scenario, "Human Token")
    assert human in scenario.attackers()


def expected_wins(game, flips=3):
    from random import Random

    start = game.coin_flips_performed
    return sum(Random(f"{game.shuffle_seed}:{start + n}:coin").random() < 0.5 for n in range(flips))


#: Seeds whose three flips are won 0, 1, 2 and 3 times (flip n is `Random(f"{seed}:{n}:coin")`).
@pytest.mark.parametrize("seed", [28, 0, 1, 12])
def test_goblin_traprunner_makes_a_goblin_for_each_coin_flip_won(seed):
    scenario = Scenario().player("alice", battlefield=["Goblin Traprunner"]).player("bob").build()
    scenario.game.shuffle_seed = seed
    wins = expected_wins(scenario.game)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Goblin Traprunner"))
    scenario.resolve_top()

    goblins = tokens(scenario, "Goblin Token")
    assert len(goblins) == wins
    assert scenario.game.coin_flips_performed >= 3
    assert all(goblin.tapped and goblin in scenario.attackers() for goblin in goblins)


def test_gemini_engine_attacks_with_a_twin_of_its_size_that_is_sacrificed_at_end_of_combat():
    scenario = Scenario().player("alice", battlefield=["Gemini Engine"]).player("bob").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    engine = scenario.creature("Gemini Engine")
    scenario.attack_with(engine)
    scenario.resolve_top()

    (twin,) = tokens(scenario, "Twin")
    assert twin in scenario.attackers()
    assert not twin.tapped
    assert (scenario.game.power_of(twin), scenario.game.toughness_of(twin)) == (3, 4)
    assert {Type.ARTIFACT, Type.CREATURE} <= set(scenario.game.computed_board().of(twin).types)

    reach(scenario, Step.END_OF_COMBAT)
    scenario.resolve_top()
    assert twin.zone is not Zone.BATTLEFIELD
    assert engine.zone is Zone.BATTLEFIELD


def test_ghalta_and_mavren_dinosaur_mode_is_as_big_as_the_biggest_other_attacker():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ghalta and Mavren", "Grizzly Bears", "Hill Giant"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_choose_mode(
        "Create a tapped and attacking X/X green Dinosaur creature token with trample, "
        "where X is the greatest power among other attacking creatures.",
        username="alice",
    )
    scenario.attack_with(*scenario.creatures("Ghalta and Mavren", "Grizzly Bears", "Hill Giant"))
    scenario.resolve_top()

    (dinosaur,) = tokens(scenario, "Dinosaur Token")
    assert (scenario.game.power_of(dinosaur), scenario.game.toughness_of(dinosaur)) == (3, 3)
    assert dinosaur.tapped and dinosaur in scenario.attackers()


def test_ghalta_and_mavren_vampire_mode_makes_one_per_other_attacker():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ghalta and Mavren", "Grizzly Bears", "Hill Giant"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_choose_mode(
        "Create X 1/1 white Vampire creature tokens with lifelink, "
        "where X is the number of other attacking creatures.",
        username="alice",
    )
    scenario.attack_with(*scenario.creatures("Ghalta and Mavren", "Grizzly Bears", "Hill Giant"))
    scenario.resolve_top()

    assert len(tokens(scenario, "Vampire Token")) == 2


# -- a Role token attached for each permanent ----------------------------------------


def roles_on(scenario, creature):
    return [
        state
        for state in scenario.game.battlefield
        if state.attached_to == creature.id
        and "Role" in scenario.game.computed_board().of(state).subtypes
    ]


def size(scenario, creature):
    return scenario.game.power_of(creature), scenario.game.toughness_of(creature)


def test_asinine_antics_cursed_roles_every_creature_the_opponents_control_and_only_theirs():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Asinine Antics"],
            battlefield=["Island"] * 4 + ["Grizzly Bears"],
        )
        .player("bob", battlefield=["Hill Giant", "Serra Angel"])
        .player("carol", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Asinine Antics", *scenario.untapped_sources(*(["Island"] * 4)))

    giants = [
        creature
        for username in ("bob", "carol")
        for creature in scenario.creatures("Hill Giant", username=username)
    ]
    for creature in [*giants, scenario.creature("Serra Angel", "bob")]:
        assert len(roles_on(scenario, creature)) == 1
        assert size(scenario, creature) == (1, 1)  # the Cursed Role sets base 1/1 (CR 111.10j)
    assert roles_on(scenario, scenario.creature("Grizzly Bears", "alice")) == []
    assert size(scenario, scenario.creature("Grizzly Bears", "alice")) == (2, 2)


def test_a_second_cursed_role_from_the_same_player_replaces_the_first():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Asinine Antics", "Asinine Antics"],
            battlefield=["Island"] * 8,
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for _ in range(2):
        scenario.cast_and_resolve("Asinine Antics", *scenario.untapped_sources(*(["Island"] * 4)))
        scenario.state_based_actions()

    assert len(roles_on(scenario, scenario.creature("Hill Giant", "bob"))) == 1  # CR 704.5z


def test_asinine_antics_with_no_creature_to_enchant_makes_no_role():
    scenario = (
        Scenario()
        .player("alice", hand=["Asinine Antics"], battlefield=["Island"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Asinine Antics", *scenario.untapped_sources(*(["Island"] * 4)))

    assert [s for s in scenario.game.battlefield if "Role" in s.name or s.attached_to] == []


def test_asinine_antics_can_be_cast_at_instant_speed_for_two_more():
    scenario = (
        Scenario()
        .player("bob", battlefield=["Hill Giant"])
        .player("alice", hand=["Asinine Antics"], battlefield=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert scenario.game.active_player.username == "bob"
    scenario.pass_priority("bob")

    scenario.cast_and_resolve(
        "Asinine Antics",
        *scenario.untapped_sources(*(["Island"] * 6), username="alice"),
        username="alice",
    )
    assert size(scenario, scenario.creature("Hill Giant", "bob")) == (1, 1)


def test_asinine_antics_at_instant_speed_costs_the_two_extra_mana():
    scenario = (
        Scenario()
        .player("bob", battlefield=["Hill Giant"])
        .player("alice", hand=["Asinine Antics"], battlefield=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.pass_priority("bob")

    casting = scenario.cast("Asinine Antics", username="alice")
    assert casting.total_cost.mana.converted == 6  # {2}{U}{U} and {2} more for flash


def test_asinine_antics_in_its_own_main_phase_costs_no_more():
    scenario = (
        Scenario()
        .player("alice", hand=["Asinine Antics"], battlefield=["Island"] * 6)
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert scenario.cast("Asinine Antics").total_cost.mana.converted == 4


def test_become_brutes_gives_haste_and_a_monster_role_to_each_of_two_targets():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Become Brutes"],
            battlefield=["Mountain", "Mountain", "Grizzly Bears", "Hill Giant"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears, giant = scenario.creatures("Grizzly Bears", "Hill Giant")
    scenario.cast_and_resolve(
        "Become Brutes",
        *scenario.untapped_sources("Mountain", "Mountain"),
        targets=[bears, giant],
    )

    assert size(scenario, bears) == (3, 3) and size(scenario, giant) == (4, 4)  # +1/+1
    assert len(roles_on(scenario, bears)) == 1 and len(roles_on(scenario, giant)) == 1
    assert scenario.can_attack(bears) and scenario.can_attack(giant)  # haste


def test_become_brutes_with_a_single_target_enchants_only_it():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Become Brutes"],
            battlefield=["Mountain", "Mountain", "Grizzly Bears", "Hill Giant"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears, giant = scenario.creatures("Grizzly Bears", "Hill Giant")
    scenario.cast_and_resolve(
        "Become Brutes", *scenario.untapped_sources("Mountain", "Mountain"), targets=[bears]
    )

    assert len(roles_on(scenario, bears)) == 1
    assert roles_on(scenario, giant) == []


def test_twisted_sewer_witch_wickeds_every_rat_you_control_including_the_new_one():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Twisted Sewer-Witch"],
            battlefield=["Swamp"] * 5 + ["Hellhole Rats", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Twisted Sewer-Witch", *scenario.untapped_sources(*(["Swamp"] * 5)))
    scenario.pass_until_resolved()

    (rat_token,) = tokens(scenario, "Rat Token")
    old_rat = scenario.creature("Hellhole Rats")
    assert size(scenario, rat_token) == (2, 2)  # 1/1 and the Wicked Role's +1/+1
    assert size(scenario, old_rat) == (3, 3)  # Hellhole Rats are 2/2
    assert len(roles_on(scenario, rat_token)) == 1 and len(roles_on(scenario, old_rat)) == 1
    assert roles_on(scenario, scenario.creature("Grizzly Bears")) == []
    assert roles_on(scenario, scenario.creature("Twisted Sewer-Witch")) == []


# -- "If that creature dies this way, create a token with its power and toughness" ----


def kalitas_scenario(*opponent_battlefield):
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Kalitas, Bloodchief of Ghet", "Swamp", "Swamp", "Swamp"],
        )
        .player("bob", battlefield=list(opponent_battlefield))
        .build()
    )


def test_kalitas_destroys_a_creature_and_makes_a_vampire_the_size_it_died_as():
    scenario = kalitas_scenario("Hill Giant", "Glorious Anthem")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    assert size(scenario, giant) == (4, 4)  # with Glorious Anthem
    scenario.activate(
        scenario.creature("Kalitas, Bloodchief of Ghet"),
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp"),
        targets=[giant],
    )
    scenario.resolve_top()

    assert giant.zone is Zone.GRAVEYARD
    (vampire,) = tokens(scenario, "Vampire Token")
    assert size(scenario, vampire) == (4, 4)  # the destroyed creature's last known size
    assert scenario.game.computed_board().of(vampire).colors == (Color.BLACK,)


def test_kalitas_makes_no_vampire_when_the_creature_does_not_die():
    scenario = kalitas_scenario("Darksteel Myr")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    myr = scenario.creature("Darksteel Myr", "bob")
    scenario.activate(
        scenario.creature("Kalitas, Bloodchief of Ghet"),
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp"),
        targets=[myr],
    )
    scenario.resolve_top()

    assert myr.zone is Zone.BATTLEFIELD  # indestructible (CR 702.12b)
    assert tokens(scenario, "Vampire Token") == []


# -- "For each of those tokens, you may attach an Equipment you control to it" ---------


def equipped_by(scenario, token):
    return [
        state
        for state in scenario.game.battlefield
        if state.attached_to == token.id and state.name in ("Bonesplitter", "Lightning Greaves")
    ]


def test_reckless_crew_makes_a_dwarf_per_vehicle_and_equipment_and_attaches_on_request():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Reckless Crew"],
            battlefield=["Mountain"] * 4
            + ["Smuggler's Copter", "Bonesplitter", "Lightning Greaves"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    greaves = scenario.find("Lightning Greaves", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(True, source="Reckless Crew", times=1)
    scenario.will_choose_cards(splitter, source="Reckless Crew")
    scenario.will_take_the_may(True, source="Reckless Crew", times=1)
    scenario.will_choose_cards(greaves, source="Reckless Crew")
    scenario.will_take_the_may(False, source="Reckless Crew", times=1)
    scenario.cast_and_resolve("Reckless Crew", *scenario.untapped_sources(*(["Mountain"] * 4)))

    dwarves = tokens(scenario, "Dwarf Berserker Token")
    assert len(dwarves) == 3  # one Vehicle plus two Equipment
    equipped = [dwarf for dwarf in dwarves if equipped_by(scenario, dwarf)]
    assert len(equipped) == 2  # the third token was declined
    assert sorted(len(equipped_by(scenario, dwarf)) for dwarf in dwarves) == [0, 1, 1]


def test_reckless_crew_with_nothing_to_count_makes_nothing():
    scenario = (
        Scenario()
        .player("alice", hand=["Reckless Crew"], battlefield=["Mountain"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Reckless Crew", *scenario.untapped_sources(*(["Mountain"] * 4)))

    assert tokens(scenario, "Dwarf Berserker Token") == []


# -- "For each of them, create a token that's a copy of that creature, except it has haste" --


def test_twinflame_copies_each_chosen_creature_with_haste_and_exiles_the_copies_at_end_step():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Twinflame"],
            battlefield=["Mountain"] * 5 + ["Grizzly Bears", "Hill Giant"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears, giant = scenario.creatures("Grizzly Bears", "Hill Giant")
    scenario.cast_and_resolve(
        "Twinflame", *scenario.untapped_sources(*(["Mountain"] * 5)), targets=[bears, giant]
    )

    (bears_copy,) = [c for c in tokens(scenario, "Grizzly Bears") if c is not bears]
    (giant_copy,) = [c for c in tokens(scenario, "Hill Giant") if c is not giant]
    assert size(scenario, bears_copy) == (2, 2) and size(scenario, giant_copy) == (3, 3)
    assert scenario.can_attack(bears_copy) and scenario.can_attack(giant_copy)  # haste

    reach(scenario, Step.END_STEP)
    scenario.resolve_top()
    assert bears_copy.zone is Zone.EXILE and giant_copy.zone is Zone.EXILE
    assert bears.zone is Zone.BATTLEFIELD and giant.zone is Zone.BATTLEFIELD


def test_twinflame_costs_two_red_and_one_more_for_each_target_beyond_the_first():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Twinflame"],
            battlefield=["Mountain"] * 8 + ["Grizzly Bears", "Hill Giant", "Serra Angel"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    one = scenario.cast("Twinflame", targets=[scenario.creature("Grizzly Bears")])
    assert one.total_cost.mana.converted == 2
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Twinflame"],
            battlefield=["Mountain"] * 8 + ["Grizzly Bears", "Hill Giant", "Serra Angel"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    three = scenario.cast(
        "Twinflame", targets=scenario.creatures("Grizzly Bears", "Hill Giant", "Serra Angel")
    )
    assert three.total_cost.mana.converted == 8  # {1}{R} plus two times {2}{R}


def test_twinflame_with_no_targets_makes_no_copies():
    scenario = (
        Scenario()
        .player("alice", hand=["Twinflame"], battlefield=["Mountain", "Mountain", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Twinflame", *scenario.untapped_sources("Mountain", "Mountain"), targets=[]
    )

    assert len(tokens(scenario, "Grizzly Bears")) == 1  # only the original


# -- loot, then exile the discarded artifact for a Thopter copy of it ---------------------


def leonardo_scenario(hand, library):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=hand,
            library=library,
            battlefield=["Leonardo da Vinci", "Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_leonardo_exiles_a_discarded_artifact_and_makes_a_thopter_copy_of_it():
    scenario = leonardo_scenario(["Bonesplitter"], ["Island"] * 3)
    bonesplitter = scenario.find("Bonesplitter", Zone.HAND, "alice")
    scenario.will_discard(bonesplitter)
    scenario.activate(
        scenario.creature("Leonardo da Vinci"),
        *scenario.untapped_sources("Island", "Island", "Island"),
        index=1,
    )
    scenario.resolve_top()

    assert bonesplitter.zone is Zone.EXILE
    (copy,) = tokens(scenario, "Bonesplitter")
    characteristics = scenario.game.computed_board().of(copy)
    assert {Type.ARTIFACT, Type.CREATURE} <= set(characteristics.types)
    assert "Thopter" in characteristics.subtypes and "Equipment" in characteristics.subtypes
    assert size(scenario, copy) == (0, 2)
    assert "Flying" in {ability.title() for ability in characteristics.abilities} or any(
        "flying" in ability.lower() for ability in characteristics.abilities
    )


def test_leonardo_discarding_a_nonartifact_just_loots():
    scenario = leonardo_scenario(["Grizzly Bears"], ["Island"] * 3)
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    scenario.will_discard(bears)
    scenario.activate(
        scenario.creature("Leonardo da Vinci"),
        *scenario.untapped_sources("Island", "Island", "Island"),
        index=1,
    )
    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert [s for s in scenario.game.battlefield if s.token] == []
    assert len(scenario.player("alice").hand) == 1  # drew a card, discarded a card


# -- tokens that "have" a quoted ability, X counted from what entered this turn ----------------


def test_cloudspire_coordinator_makes_a_pilot_per_vehicle_that_entered_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Smuggler's Copter", "Heart of Kiran"],
            battlefield=["Mountain"] * 4 + ["Cloudspire Coordinator"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Smuggler's Copter", *scenario.untapped_sources("Mountain", "Mountain")
    )
    scenario.cast_and_resolve("Heart of Kiran", *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.activate(scenario.creature("Cloudspire Coordinator"))
    scenario.resolve_top()

    pilots = tokens(scenario, "Pilot Token")
    assert len(pilots) == 2
    assert all(size(scenario, pilot) == (1, 1) for pilot in pilots)


def test_a_pilot_crews_as_though_its_power_were_two_greater():
    from magic_cards_model.machines import crew_saddle_statics

    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Heart of Kiran"],
            battlefield=["Mountain", "Mountain", "Cloudspire Coordinator"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Heart of Kiran", *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.activate(scenario.creature("Cloudspire Coordinator"))
    scenario.resolve_top()

    (pilot,) = tokens(scenario, "Pilot Token")
    assert crew_saddle_statics.contribution(scenario.game, pilot, "crew") == 3
    assert crew_saddle_statics.contribution(scenario.game, pilot, "saddle") == 3


def test_cloudspire_coordinator_with_nothing_entered_makes_no_pilot():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Smuggler's Copter", "Cloudspire Coordinator"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.activate(scenario.creature("Cloudspire Coordinator"))
    scenario.resolve_top()

    assert tokens(scenario, "Pilot Token") == []


# -- look at the top card, exile it face down, and play it while it stays exiled -----------


def edward_scenario(bob_library):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Edward Kenway", "Smuggler's Copter", "Grizzly Bears", "Mountain"],
        )
        .player("bob", library=bob_library)
        .build()
    )
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    return scenario


def hit_with_the_copter(scenario):
    from magic_cards_model.machines.keywords import crew_activation

    copter = scenario.find("Smuggler's Copter", Zone.BATTLEFIELD, "alice")
    activation = crew_activation(
        scenario.game, copter, [scenario.creature("Grizzly Bears", "alice")], "alice"
    )
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()
    scenario.pass_until_resolved()
    scenario.advance()
    assert scenario.step is Step.DECLARE_ATTACKERS
    scenario.will_take_the_may(False, source="Smuggler's Copter")
    scenario.attack_with(copter)
    scenario.resolve_top()  # the Copter's own loot trigger, declined
    scenario.advance()
    while scenario.step is not Step.COMBAT_DAMAGE:
        scenario.advance()
    return copter


def test_edward_kenway_exiles_the_top_card_of_the_damaged_players_library_face_down():
    scenario = edward_scenario(["Mountain", "Island", "Island"])
    top = scenario.player("bob").library[0]
    hit_with_the_copter(scenario)
    scenario.resolve_top()

    assert top.zone is Zone.EXILE and not top.face_up
    assert len(scenario.player("bob").library) == 2
    reach(scenario, Step.POSTCOMBAT_MAIN)
    land = scenario.play_land("Mountain", "alice", from_zone=Zone.EXILE)  # CR 305.2a via the grant
    assert land.zone is Zone.BATTLEFIELD


def test_the_exiled_card_cannot_be_played_by_its_owner():
    scenario = edward_scenario(["Mountain", "Island", "Island"])
    top = scenario.player("bob").library[0]
    hit_with_the_copter(scenario)
    scenario.resolve_top()

    assert top.zone is Zone.EXILE
    from magic_cards_model.machines.casting import PlayAction, usable_play_permission

    assert usable_play_permission(scenario.game, top, "bob", PlayAction.PLAY) is None
    assert usable_play_permission(scenario.game, top, "alice", PlayAction.PLAY) is not None


# -- Kellan, Daring Traveler // Journey On ------------------------------------------------


def test_journey_on_makes_a_map_for_one_plus_each_opponent_who_controls_an_artifact():
    scenario = (
        Scenario()
        .player("alice", hand=["Kellan, Daring Traveler"], battlefield=["Forest"])
        .player("bob", battlefield=["Mind Stone"])
        .player("carol", battlefield=["Mind Stone"])
        .player("dave", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Kellan, Daring Traveler")
    casting.cast_as_adventure()
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Forest"))
    adventure = scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert len(tokens(scenario, "Map Token")) == 3  # one plus two opponents with an artifact
    assert adventure.zone is Zone.EXILE  # CR 715.4: on an adventure, ready to cast the creature


def test_journey_on_with_no_opposing_artifact_makes_a_single_map():
    scenario = (
        Scenario()
        .player("alice", hand=["Kellan, Daring Traveler"], battlefield=["Forest"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Kellan, Daring Traveler")
    casting.cast_as_adventure()
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Forest"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert len(tokens(scenario, "Map Token")) == 1


def kellan_attacks(library):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Kellan, Daring Traveler"], library=library)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Kellan, Daring Traveler"))
    return scenario


def test_kellan_puts_a_revealed_cheap_creature_into_your_hand():
    scenario = kellan_attacks(["Grizzly Bears", "Island"])
    scenario.resolve_top()

    assert [s.name for s in scenario.player("alice").hand] == ["Grizzly Bears"]


def test_kellan_does_not_take_a_revealed_creature_with_mana_value_four():
    scenario = kellan_attacks(["Serra Angel", "Island"])
    scenario.will_take_the_may(False, source="Kellan, Daring Traveler")
    scenario.resolve_top()

    assert scenario.player("alice").hand == []
    assert scenario.player("alice").library[0].name == "Serra Angel"  # stays on top


def test_kellan_may_put_a_revealed_noncreature_into_the_graveyard():
    scenario = kellan_attacks(["Island", "Island"])
    scenario.will_take_the_may(True, source="Kellan, Daring Traveler")
    scenario.resolve_top()

    assert [s.name for s in scenario.player("alice").graveyard] == ["Island"]
    assert scenario.player("alice").hand == []


# -- "Target creature card in your graveyard gains embalm until end of turn" ----------------


def embalm_it(scenario, card, *sources):
    from magic_cards_model.machines.keywords import off_zone_activation

    from .harness import mana_from

    activation = off_zone_activation(scenario.game, card, "alice", 0)
    payment = activation.begin_paying()
    for source in sources:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    return activation


def cursecloth_scenario(graveyard):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            graveyard=graveyard,
            battlefield=["Cursecloth Wrappings", "Mountain", "Mountain", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_cursecloth_wrappings_gives_a_graveyard_creature_embalm_at_its_own_mana_cost():
    scenario = cursecloth_scenario(["Hill Giant"])
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    scenario.activate(
        scenario.find("Cursecloth Wrappings", Zone.BATTLEFIELD, "alice"), targets=[giant]
    )
    scenario.resolve_top()

    embalm_it(scenario, giant, *scenario.untapped_sources(*(["Mountain"] * 4))).resolve()

    assert giant.zone is Zone.EXILE  # exiled as the cost
    (zombie,) = tokens(scenario, "Hill Giant")
    characteristics = scenario.game.computed_board().of(zombie)
    assert "Zombie" in characteristics.subtypes and characteristics.colors == (Color.WHITE,)
    assert size(scenario, zombie) == (4, 4)  # Hill Giant 3/3 and Zombies get +1/+1


def test_without_the_grant_a_graveyard_creature_has_no_embalm():
    from magic_cards_model.machines.keywords import off_zone_activation

    scenario = cursecloth_scenario(["Hill Giant"])
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")

    with pytest.raises(ValueError, match="no activated ability functioning off the battlefield"):
        off_zone_activation(scenario.game, giant, "alice", 0)


def test_the_embalm_grant_ends_with_the_turn():
    from magic_cards_model.machines.keywords import off_zone_activation

    scenario = cursecloth_scenario(["Hill Giant"])
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    scenario.activate(
        scenario.find("Cursecloth Wrappings", Zone.BATTLEFIELD, "alice"), targets=[giant]
    )
    scenario.resolve_top()
    scenario.game.continuous_effects.end_the_turn()  # CR 514.2: "until end of turn" ends

    with pytest.raises(ValueError, match="no activated ability functioning off the battlefield"):
        off_zone_activation(scenario.game, giant, "alice", 0)


def test_the_grant_is_for_that_one_card_only():
    from magic_cards_model.machines.keywords import off_zone_activation

    scenario = cursecloth_scenario(["Hill Giant", "Grizzly Bears"])
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.activate(
        scenario.find("Cursecloth Wrappings", Zone.BATTLEFIELD, "alice"), targets=[giant]
    )
    scenario.resolve_top()

    off_zone_activation(scenario.game, giant, "alice", 0)  # the chosen card has embalm
    with pytest.raises(ValueError, match="no activated ability functioning off the battlefield"):
        off_zone_activation(scenario.game, bears, "alice", 0)


# -- the token-count readers already handled, played ----------------------------------------


def make_tokens(scenario, definition, count=1, username="alice"):
    from magic_cards_model.models.token import create_tokens

    return create_tokens(scenario.game, definition, username, count)


SOLDIER = None


def soldier_definition():
    from magic_cards_model.models.token import TokenDefinition

    return TokenDefinition(subtypes=("Soldier",), power=1, toughness=1)


def spirit_definition():
    from magic_cards_model.models.token import TokenDefinition

    return TokenDefinition(subtypes=("Spirit",), power=1, toughness=1)


def test_audience_with_trostani_draws_a_card_for_each_differently_named_creature_token():
    from magic_cards_model.models.token import TokenDefinition

    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Audience with Trostani"],
            library=["Island"] * 6,
            battlefield=["Forest"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    make_tokens(scenario, soldier_definition(), 2)  # same name: counts once
    make_tokens(scenario, spirit_definition())
    make_tokens(
        scenario, TokenDefinition(types=(Type.ARTIFACT,), name="Treasure")
    )  # not a creature
    scenario.cast_and_resolve(
        "Audience with Trostani", *scenario.untapped_sources("Forest", "Forest", "Forest")
    )

    assert len(tokens(scenario, "Plant Token")) == 1
    assert len(scenario.player("alice").hand) == 3  # Plant, Soldier, Spirit


def test_audience_with_trostani_with_no_other_tokens_draws_one_for_the_plant():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Audience with Trostani"],
            library=["Island"] * 6,
            battlefield=["Forest"] * 3,
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Audience with Trostani", *scenario.untapped_sources("Forest", "Forest", "Forest")
    )

    assert len(scenario.player("alice").hand) == 1


def test_valduk_makes_an_elemental_for_each_aura_and_equipment_attached_and_exiles_them():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Valduk, Keeper of the Flame", "Bonesplitter", "Rancor", "Bonesplitter"],
        )
        .player("bob")
        .build()
    )
    valduk = scenario.creature("Valduk, Keeper of the Flame")
    attached = 0
    for permanent in scenario.game.permanents_controlled_by("alice"):
        if permanent.name in ("Bonesplitter", "Rancor") and attached < 2:
            permanent.attach_to(valduk)
            attached += 1
    assert attached == 2

    reach(scenario, Step.BEGINNING_OF_COMBAT)
    scenario.resolve_top()

    elementals = tokens(scenario, "Elemental Token")
    assert len(elementals) == 2
    assert all(size(scenario, elemental) == (3, 1) for elemental in elementals)
    reach(scenario, Step.END_STEP)
    scenario.resolve_top()
    assert all(elemental.zone is Zone.EXILE for elemental in elementals)


def test_valduk_with_nothing_attached_makes_no_elemental():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Valduk, Keeper of the Flame", "Bonesplitter"])
        .player("bob")
        .build()
    )
    reach(scenario, Step.BEGINNING_OF_COMBAT)
    scenario.resolve_top()

    assert tokens(scenario, "Elemental Token") == []


def test_springjack_shepherd_makes_a_goat_for_each_white_symbol_among_your_permanents():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Springjack Shepherd"],
            battlefield=["Plains"] * 4 + ["Serra Angel", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Springjack Shepherd", *scenario.untapped_sources(*(["Plains"] * 4)))
    scenario.pass_until_resolved()

    # Serra Angel {3}{W}{W} and the Shepherd {3}{W} are yours; the opponent's angel is not.
    assert len(tokens(scenario, "Goat Token")) == 3


def test_springjack_shepherd_alone_counts_its_own_white_symbol():
    scenario = (
        Scenario()
        .player("alice", hand=["Springjack Shepherd"], battlefield=["Plains"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Springjack Shepherd", *scenario.untapped_sources(*(["Plains"] * 4)))
    scenario.pass_until_resolved()

    assert len(tokens(scenario, "Goat Token")) == 1


def die_together(scenario, *permanents):
    for permanent in permanents:
        scenario.game.destroy(permanent)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


def test_dripping_tongue_zubera_counts_every_zubera_that_died_this_turn_in_any_graveyard():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Dripping-Tongue Zubera", "Grizzly Bears"])
        .player("bob", battlefield=["Silent-Chant Zubera"], library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    die_together(
        scenario,
        scenario.creature("Dripping-Tongue Zubera"),
        scenario.creature("Silent-Chant Zubera", "bob"),
        scenario.creature("Grizzly Bears"),
    )

    assert len(tokens(scenario, "Spirit Token")) == 2  # the two Zubera, not the Bears


def test_dripping_tongue_zubera_alone_makes_one_spirit():
    scenario = (
        Scenario().player("alice", battlefield=["Dripping-Tongue Zubera"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    die_together(scenario, scenario.creature("Dripping-Tongue Zubera"))

    assert len(tokens(scenario, "Spirit Token")) == 1


def test_wolfbriar_elemental_makes_a_wolf_for_each_time_it_was_kicked():
    scenario = (
        Scenario()
        .player("alice", hand=["Wolfbriar Elemental"], battlefield=["Forest"] * 7)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Wolfbriar Elemental")
    casting.pay_kicker(3)
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*(["Forest"] * 7)))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.pass_until_resolved()

    wolves = tokens(scenario, "Wolf Token")
    assert len(wolves) == 3
    assert all(size(scenario, wolf) == (2, 2) for wolf in wolves)


def test_wolfbriar_elemental_unkicked_makes_no_wolf():
    scenario = (
        Scenario()
        .player("alice", hand=["Wolfbriar Elemental"], battlefield=["Forest"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Wolfbriar Elemental", *scenario.untapped_sources(*(["Forest"] * 4)))
    scenario.pass_until_resolved()

    assert tokens(scenario, "Wolf Token") == []


ROOM = "Smoky Lounge // Misty Salon"


def room_of(scenario):
    return next(
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.card.name == ROOM
    )


def test_unlocking_misty_salon_makes_a_spirit_as_big_as_the_unlocked_doors_you_have():
    scenario = Scenario().player("alice", battlefield=[ROOM, *["Island"] * 4]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.unlock_door(room_of(scenario), "Smoky Lounge")
    scenario.unlock_door(
        room_of(scenario), "Misty Salon", *scenario.untapped_sources(*(["Island"] * 4))
    )
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    (spirit,) = tokens(scenario, "Spirit Token")
    assert size(scenario, spirit) == (2, 2)  # both doors of the one Room are unlocked
    assert Type.CREATURE in scenario.game.computed_board().of(spirit).types


def test_a_lone_unlocked_misty_salon_makes_a_one_one_spirit():
    scenario = Scenario().player("alice", battlefield=[ROOM, *["Island"] * 4]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.unlock_door(
        room_of(scenario), "Misty Salon", *scenario.untapped_sources(*(["Island"] * 4))
    )
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    (spirit,) = tokens(scenario, "Spirit Token")
    assert size(scenario, spirit) == (1, 1)


def test_smoky_lounge_adds_two_red_at_the_beginning_of_your_first_main_phase():
    scenario = Scenario().player("alice", battlefield=[ROOM]).player("bob").build()
    scenario.game.unlock_door(room_of(scenario), "Smoky Lounge")
    reach(scenario, Step.PRECOMBAT_MAIN)
    scenario.resolve_top()

    assert scenario.player("alice").mana_pool.floating.get(Color.RED, 0) == 2


def test_manaform_hellkite_makes_a_dragon_as_big_as_the_mana_spent_and_exiles_it_at_end_step():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Flame Wave", "Grizzly Bears"],
            battlefield=["Manaform Hellkite", *["Mountain"] * 8],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack(
        "Flame Wave", *scenario.untapped_sources(*(["Mountain"] * 7)), targets=["bob"]
    )
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()  # Manaform Hellkite's trigger, above the spell

    (dragon,) = tokens(scenario, "Dragon Illusion Token")
    assert size(scenario, dragon) == (7, 7)  # {3}{R}{R}{R}{R} was spent
    assert scenario.can_attack(dragon)  # haste
    scenario.resolve_top()  # Flame Wave

    reach(scenario, Step.END_STEP)
    scenario.resolve_top()
    assert dragon.zone is Zone.EXILE


def test_manaform_hellkite_ignores_a_creature_spell():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Manaform Hellkite", *["Forest"] * 2],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack("Grizzly Bears", *scenario.untapped_sources("Forest", "Forest"))
    scenario.game.put_triggers_on_stack()

    assert tokens(scenario, "Dragon Illusion Token") == []


# -- proof printings: the same readers on other legal cards -----------------------------------


def test_silent_chant_zubera_gains_two_life_for_each_zubera_that_died_this_turn():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Silent-Chant Zubera", "Grizzly Bears"])
        .player("bob", battlefield=["Dripping-Tongue Zubera"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    die_together(
        scenario,
        scenario.creature("Silent-Chant Zubera"),
        scenario.creature("Dripping-Tongue Zubera", "bob"),
        scenario.creature("Grizzly Bears"),
    )

    assert scenario.player("alice").life == 24  # two Zubera died, 2 life each (CR 119.3)


def test_floating_dream_zubera_draws_a_card_for_each_zubera_that_died_this_turn():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Floating-Dream Zubera"], library=["Island"] * 5)
        .player("bob", battlefield=["Dripping-Tongue Zubera"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    die_together(
        scenario,
        scenario.creature("Floating-Dream Zubera"),
        scenario.creature("Dripping-Tongue Zubera", "bob"),
    )

    assert len(scenario.player("alice").hand) == 2


def test_deadly_embrace_draws_for_every_creature_that_died_this_turn_including_its_target():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Deadly Embrace"],
            library=["Island"] * 5,
            battlefield=["Swamp"] * 5 + ["Grizzly Bears"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.destroy(scenario.creature("Grizzly Bears"))  # died earlier this turn
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_and_resolve(
        "Deadly Embrace", *scenario.untapped_sources(*(["Swamp"] * 5)), targets=[giant]
    )

    assert giant.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == 2  # the Bears and the Giant


def test_stronghold_arena_gains_three_life_for_each_time_it_was_kicked():
    for kickers, gained in (((), 0), (("{G}",), 3), (("{G}", "{W}"), 6)):
        scenario = (
            Scenario()
            .player(
                "alice",
                hand=["Stronghold Arena"],
                battlefield=["Swamp", "Swamp", "Forest", "Plains"],
            )
            .player("bob")
            .build()
        )
        scenario.start_at(Step.PRECOMBAT_MAIN)
        casting = scenario.cast("Stronghold Arena")
        for which in kickers:
            casting.pay_kicker(1, which=which)
        scenario.pay_with(
            casting.begin_paying(),
            *scenario.untapped_sources(
                *(["Swamp", "Swamp", "Forest", "Plains"][: 2 + len(kickers)])
            ),
        )
        scenario.put_on_stack(casting)
        scenario.resolve_top()
        scenario.pass_until_resolved()

        assert scenario.player("alice").life == 20 + gained, kickers


def test_rampaging_soulrager_gets_plus_three_with_two_unlocked_doors_among_your_rooms():
    scenario = (
        Scenario().player("alice", battlefield=[ROOM, "Rampaging Soulrager"]).player("bob").build()
    )
    soulrager = scenario.creature("Rampaging Soulrager")
    assert size(scenario, soulrager) == (1, 4)

    scenario.game.unlock_door(room_of(scenario), "Smoky Lounge")
    assert size(scenario, soulrager) == (1, 4)  # one unlocked door

    scenario.game.unlock_door(room_of(scenario), "Misty Salon")
    assert size(scenario, soulrager) == (4, 4)  # two unlocked doors
