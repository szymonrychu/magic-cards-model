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
