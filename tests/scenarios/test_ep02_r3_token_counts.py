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
        state
        for state in scenario.game.permanents_controlled_by(username)
        if state.name == name
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
        .player("alice", hand=["Gluttonous Troll"], battlefield=["Forest", "Forest", "Swamp", "Forest"])
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
    scenario.cast_and_resolve("Stone Idol Trap", *scenario.untapped_sources("Mountain", "Mountain", "Mountain"))

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
    scenario = (
        Scenario()
        .player("alice", battlefield=["Harried Dronesmith"])
        .player("bob")
        .build()
    )
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
        Scenario().player("alice", battlefield=["Adeline, Resplendent Cathar"]).player("bob").build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Adeline, Resplendent Cathar"))
    scenario.resolve_top()

    (human,) = tokens(scenario, "Human Token")
    assert human in scenario.attackers()


def expected_wins(game, flips=3):
    from random import Random

    start = game.coin_flips_performed
    return sum(
        Random(f"{game.shuffle_seed}:{start + n}:coin").random() < 0.5 for n in range(flips)
    )


#: Seeds whose three flips are won 0, 1, 2 and 3 times (flip n is `Random(f"{seed}:{n}:coin")`).
@pytest.mark.parametrize("seed", [28, 0, 1, 12])
def test_goblin_traprunner_makes_a_goblin_for_each_coin_flip_won(seed):
    scenario = (
        Scenario().player("alice", battlefield=["Goblin Traprunner"]).player("bob").build()
    )
    scenario.game.shuffle_seed = seed
    wins = expected_wins(scenario.game)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Goblin Traprunner"))
    scenario.resolve_top()

    goblins = tokens(scenario, "Goblin Token")
    assert len(goblins) == wins
    assert scenario.game.coin_flips_performed >= 3
    assert all(goblin.tapped and goblin in scenario.attackers() for goblin in goblins)


def test_gemini_engine_attacks_with_a_twin_that_copies_its_size_and_is_sacrificed_at_end_of_combat():
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
    scenario.attack_with(
        *scenario.creatures("Ghalta and Mavren", "Grizzly Bears", "Hill Giant")
    )
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
    scenario.attack_with(
        *scenario.creatures("Ghalta and Mavren", "Grizzly Bears", "Hill Giant")
    )
    scenario.resolve_top()

    assert len(tokens(scenario, "Vampire Token")) == 2


# -- a Role token attached for each permanent ----------------------------------------


def roles_on(scenario, creature):
    return [
        state
        for state in scenario.game.battlefield
        if state.attached_to == creature.id and "Role" in scenario.game.computed_board().of(state).subtypes
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
        scenario.cast_and_resolve(
            "Asinine Antics", *scenario.untapped_sources(*(["Island"] * 4))
        )
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
        "Asinine Antics", *scenario.untapped_sources(*(["Island"] * 6), username="alice"),
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
            battlefield=["Mountain"] * 4 + ["Smuggler's Copter", "Bonesplitter", "Lightning Greaves"],
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
    scenario.cast_and_resolve("Twinflame", *scenario.untapped_sources("Mountain", "Mountain"), targets=[])

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
    scenario.cast_and_resolve("Smuggler's Copter", *scenario.untapped_sources("Mountain", "Mountain"))
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
