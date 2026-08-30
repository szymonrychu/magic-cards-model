"""First strike and double strike, and the extra damage step (CR 702.7, 702.4, 510.4).

CR 702.7b: "If at least one attacking or blocking creature has first strike or
double strike (see rule 702.4) as the combat damage step begins, the only
creatures that assign combat damage in that step are those ..." with one of the
two abilities. Everything else assigns in a second combat damage step, along
with the double strikers again.

That ordering is the whole point: state-based actions run between the two
steps, so a creature killed by first strike never strikes back.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def duel(attacker: str, blocker: str, bob_life: int = 20) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=[attacker])
        .player("bob", life=bob_life, battlefield=[blocker])
    )


def test_one_damage_step_when_nothing_has_first_strike():
    """CR 510.4 only applies if something in combat has the ability."""
    scenario = duel("Grizzly Bears", "Watchwolf").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.attack_with(bears)
    scenario.block(bears, wolf)

    assert not scenario.game.needs_first_strike_damage_step
    scenario.combat_damage()
    assert scenario.game.combat.damage_steps_done == 1


def test_first_strike_creates_a_second_damage_step():
    """CR 510.4: one first striker anywhere in combat splits the step in two."""
    scenario = duel("Youthful Knight", "Watchwolf").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    knight = scenario.creature("Youthful Knight")
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.attack_with(knight)
    scenario.block(knight, wolf)

    assert scenario.game.needs_first_strike_damage_step
    scenario.combat_damage()
    assert scenario.game.combat.damage_steps_done == 2
    assert scenario.game.combat.first_strike_step_happened


def test_a_creature_killed_by_first_strike_never_strikes_back():
    """A 2/1 first striker beats a 2/2 blocker: the Bears die before assigning."""
    scenario = duel("Youthful Knight", "Grizzly Bears").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    knight = scenario.creature("Youthful Knight")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(knight)
    scenario.block(knight, bears)
    scenario.combat_damage()

    assert bears.zone is Zone.GRAVEYARD
    assert knight.zone is Zone.BATTLEFIELD
    assert knight.damage == 0


def test_the_same_trade_without_first_strike_kills_both():
    """The contrast case: a 2/1 with no first strike dies to the same Bears."""
    scenario = duel("Ragavan, Nimble Pilferer", "Grizzly Bears").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    ragavan = scenario.creature("Ragavan, Nimble Pilferer")
    bears = scenario.creature("Grizzly Bears", "bob")
    assert ragavan.power == 2 and ragavan.toughness == 1
    scenario.attack_with(ragavan)
    scenario.block(ragavan, bears)
    scenario.combat_damage()

    assert bears.zone is Zone.GRAVEYARD
    assert ragavan.zone is Zone.GRAVEYARD


def test_first_strike_damage_lands_in_the_first_step_only():
    """CR 702.7b: a first striker assigns in the first step and not again."""
    scenario = duel("Youthful Knight", "Watchwolf", bob_life=20).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    knight = scenario.creature("Youthful Knight")
    scenario.attack_with(knight)
    scenario.no_blocks()

    first = scenario.game.combat_damage_step()
    assert [(t.username, n) for t, n in first] == [("bob", 2)]
    second = scenario.game.combat_damage_step()
    assert second == []
    assert scenario.player("bob").life == 18


def test_double_strike_deals_damage_in_both_steps():
    """CR 702.4b: a 1/1 double striker takes two off an unblocked defender."""
    scenario = duel("Fencing Ace", "Watchwolf").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    ace = scenario.creature("Fencing Ace")
    scenario.attack_with(ace)
    scenario.no_blocks()
    assigned = scenario.combat_damage()

    assert len(assigned) == 2
    assert scenario.player("bob").life == 18
    assert scenario.game.combat.damage_steps_done == 2


def test_double_strike_kills_a_two_toughness_blocker_but_dies_with_it():
    """Two 1s add up on a 2/2, and the blocker's 2 lands in the second step.

    The second step is still simultaneous (CR 510.2): the Ace's second point is
    lethal for the Bears, and the Bears' 2 is lethal for the Ace.
    """
    scenario = duel("Fencing Ace", "Grizzly Bears").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    ace = scenario.creature("Fencing Ace")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(ace)
    scenario.block(ace, bears)
    scenario.combat_damage()

    assert bears.zone is Zone.GRAVEYARD
    assert ace.zone is Zone.GRAVEYARD


def test_a_first_striking_blocker_kills_the_attacker_before_it_hits_back():
    """CR 702.7b makes no distinction between an attacking and a blocking first striker."""
    scenario = duel("Grizzly Bears", "Youthful Knight").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    knight = scenario.creature("Youthful Knight", "bob")
    scenario.attack_with(bears)
    scenario.block(bears, knight)
    scenario.combat_damage()

    assert bears.zone is Zone.GRAVEYARD
    assert knight.zone is Zone.BATTLEFIELD


def test_first_strike_damage_counts_toward_lethal_in_the_second_step():
    """CR 510.1c reads marked damage, so 1 already on a 2/2 makes 1 more lethal.

    The Ace's first-strike point stays marked, so the second step needs only
    one more - which is exactly what it has.
    """
    scenario = duel("Fencing Ace", "Grizzly Bears").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    ace = scenario.creature("Fencing Ace")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(ace)
    scenario.block(ace, bears)

    scenario.game.combat_damage_step()
    assert bears.damage == 1
    assert bears.zone is Zone.BATTLEFIELD, "1 is not lethal for a 2/2 yet"

    scenario.game.combat_damage_step()
    assert bears.zone is Zone.GRAVEYARD
