"""Combat damage: assigning it, and dealing it all at once (CR 510).

CR 510.1a: "Each attacking creature and each blocking creature assigns combat
damage equal to its power. Creatures that would assign 0 or less damage this
way don't assign combat damage at all."

CR 510.2: "Second, all combat damage that's been assigned is dealt
simultaneously." Nothing dies part-way through a step, which is why a trade
kills both creatures rather than one.

First strike is what splits this into two steps; it has its own file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board(bob_life: int = 20) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Hill Giant", "Craw Wurm"])
        .player("bob", life=bob_life, battlefield=["Watchwolf", "Giant Spider"])
    )


def test_an_unblocked_attacker_damages_the_defending_player():
    """CR 510.1b: an unblocked creature assigns its damage to what it is attacking."""
    scenario = board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    scenario.attack_with(bears)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 18


def test_an_unblocked_attacker_can_win_the_game():
    """CR 104.2a: bob hits zero, loses to state-based actions, and alice is alone."""
    scenario = board(bob_life=2).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    scenario.attack_with(bears)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 0
    assert "bob" in scenario.game.losers
    assert scenario.game.winner == "alice"
    assert scenario.game.is_over


def test_a_blocked_attacker_and_its_blocker_both_die():
    """CR 510.2: damage is simultaneous, so neither one dies before dealing its own."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    attacker = scenario.creature("Grizzly Bears", "alice")
    blocker = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(attacker)
    scenario.block(attacker, blocker)
    scenario.combat_damage()

    assert attacker.zone is Zone.GRAVEYARD
    assert blocker.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 20, "a blocked attacker hits nothing else"


def test_a_blocker_that_survives_keeps_the_damage_marked():
    """CR 510.1a plus CR 704.5g: 3 damage on a 2/4 is marked and not lethal."""
    scenario = board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    giant = scenario.creature("Hill Giant")
    spider = scenario.creature("Giant Spider", "bob")
    scenario.attack_with(giant)
    scenario.block(giant, spider)
    scenario.combat_damage()

    assert spider.zone is Zone.BATTLEFIELD
    assert spider.damage == 3
    assert giant.damage == 2


def test_two_blockers_are_each_assigned_lethal_damage_in_order():
    """CR 510.1c: the Wurm's 6 covers the Wolf's 3 and then the Spider's 4 - partly.

    Declaration order is the order damage walks through, so the Watchwolf gets
    its lethal 3 first and the Giant Spider gets what is left.
    """
    scenario = board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    wurm = scenario.creature("Craw Wurm")
    wolf = scenario.creature("Watchwolf", "bob")
    spider = scenario.creature("Giant Spider", "bob")
    scenario.attack_with(wurm)
    scenario.block(wurm, wolf, spider)
    assigned = scenario.combat_damage()

    assert [(target.name, amount) for target, amount in assigned] == [
        ("Watchwolf", 3),
        ("Giant Spider", 3),
        ("Craw Wurm", 3),
        ("Craw Wurm", 2),
    ]
    assert wolf.zone is Zone.GRAVEYARD
    assert spider.zone is Zone.BATTLEFIELD, "3 is not lethal for a 2/4"


def test_blocking_first_puts_a_creature_first_in_line_for_damage():
    """The same two blockers the other way round: the Spider soaks its 4 first."""
    scenario = board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    wurm = scenario.creature("Craw Wurm")
    wolf = scenario.creature("Watchwolf", "bob")
    spider = scenario.creature("Giant Spider", "bob")
    scenario.attack_with(wurm)
    scenario.block(wurm, spider, wolf)
    scenario.combat_damage()

    assert spider.zone is Zone.GRAVEYARD
    assert wolf.damage == 2
    assert wolf.zone is Zone.BATTLEFIELD


def test_without_trample_the_leftover_damage_stays_on_the_blockers():
    """CR 702.19a: a creature with no trample has nowhere to put its excess."""
    scenario = board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    wurm = scenario.creature("Craw Wurm")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.attack_with(wurm)
    scenario.block(wurm, wolf)
    assigned = scenario.combat_damage()

    assert (scenario.player("bob"), 3) not in assigned
    assert scenario.player("bob").life == 20
    assert wolf.zone is Zone.GRAVEYARD


def test_a_zero_power_creature_assigns_no_combat_damage():
    """CR 510.1a: creatures that would assign 0 or less don't assign at all."""
    scenario = Scenario().player("alice", battlefield=["Birds of Paradise"]).player("bob").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    birds = scenario.creature("Birds of Paradise")
    scenario.attack_with(birds)
    scenario.no_blocks()

    assert scenario.combat_damage() == []
    assert scenario.player("bob").life == 20


def test_several_attackers_add_up_on_the_defending_player():
    scenario = board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears, giant, wurm = scenario.creatures("Grizzly Bears", "Hill Giant", "Craw Wurm")
    scenario.attack_with(bears, giant, wurm)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 20 - (2 + 3 + 6)


def test_only_the_unblocked_attackers_reach_the_player():
    scenario = board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears, giant = scenario.creatures("Grizzly Bears", "Hill Giant")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.attack_with(bears, giant)
    scenario.block(giant, wolf)
    scenario.combat_damage()

    assert scenario.player("bob").life == 18, "only the Bears got through"


def test_marked_damage_is_gone_once_the_creature_changes_zones():
    """CR 120.6 and the zone-change rule: a card in the graveyard is a new object."""
    scenario = board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    giant = scenario.creature("Hill Giant")
    spider = scenario.creature("Giant Spider", "bob")
    scenario.attack_with(giant)
    scenario.block(giant, spider)
    scenario.combat_damage()

    assert spider.damage == 3
    scenario.game.destroy(spider)
    assert spider.damage == 0


# -- CR 510.3a: what triggered on the damage reaches the stack ---------------


def test_a_damage_trigger_is_on_the_stack_when_the_step_ends():
    """CR 510.3a: "Any abilities that triggered on damage being dealt or while
    state-based actions are performed afterward are put onto the stack before
    the active player gets priority."

    The combat damage step is the one place in combat that emits events, and
    before this it left them sitting in `pending_triggers` (CR 603.3's queue)
    with nothing in the step to move them - so a "whenever this deals combat
    damage" ability only reached the stack if some later part of the engine
    happened to flush the queue. `Game.declare_attackers` and
    `Game.declare_blockers` already do the same thing for CR 508.2b and
    CR 509.2a.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ragavan, Nimble Pilferer"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ragavan = scenario.creature("Ragavan, Nimble Pilferer", "alice")
    ragavan.summoning_sick = False

    scenario.attack_with(ragavan, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.stack_names() == ["Ragavan, Nimble Pilferer's triggered ability"]
    assert scenario.pending_triggers == [], "nothing was left on the CR 603.3 queue"


def test_a_death_from_the_damage_triggers_into_the_same_batch():
    """CR 510.3a's second clause: "or while state-based actions are performed
    afterward".

    The state-based action is CR 704.5g - a creature with lethal damage marked
    on it is destroyed - and the dies trigger it causes belongs to this batch,
    not to some later one. Footlight Fiend's "When this creature dies, it deals
    1 damage to any target" is the trigger; the step runs the state-based
    actions first (CR 117.5) and only then puts what triggered on the stack, so
    the death is already known by the time the batch is assembled.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Footlight Fiend"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    fiend = scenario.creature("Footlight Fiend", "bob")

    scenario.attack_with(bears)
    scenario.block(bears, fiend)
    scenario.combat_damage()

    assert fiend.zone is Zone.GRAVEYARD, "CR 704.5g destroyed it in the step"
    assert scenario.stack_names() == ["Footlight Fiend's triggered ability"]
