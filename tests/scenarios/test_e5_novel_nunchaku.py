"""Novel Nunchaku: "When this Equipment enters, attach it to target creature you
control. When you do, equipped creature fights up to one target creature an
opponent controls."

CR 603.12: "When you do" is a reflexive trigger, created only once the attach
has actually happened and given its own targets as it goes on the stack
(CR 603.3d). CR 701.14: a fight has each creature deal damage equal to its
power to the other, so the equipment's +1/+1 and trample are already counted.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def board(*, alice_creatures=("Grizzly Bears",), bob_creatures=("Grizzly Bears",)) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Novel Nunchaku"],
            battlefield=["Forest", "Forest", "Forest", *alice_creatures],
        )
        .player("bob", battlefield=list(bob_creatures))
    )


def cast_nunchaku(scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.cast_and_resolve("Novel Nunchaku", *sources)


def test_attaches_then_the_equipped_creature_fights_the_chosen_opponent_creature():
    scenario = board().build()
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_targets(mine, source="Novel Nunchaku")
    scenario.will_choose_targets(theirs, source="Novel Nunchaku")
    cast_nunchaku(scenario)
    scenario.pass_until_resolved()  # the enters trigger: attach
    nunchaku = scenario.find("Novel Nunchaku", Zone.BATTLEFIELD, "alice")
    assert nunchaku.attached_to == mine.id
    scenario.pass_until_resolved()  # CR 603.12's reflexive "when you do"
    assert theirs.zone is Zone.GRAVEYARD, "3 damage from the +1/+1 Bears kills a 2/2"
    assert mine.zone is Zone.BATTLEFIELD
    assert mine.damage == 2, "the fight is mutual: the 2/2 deals 2 back"
    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_up_to_one_means_the_fight_can_be_skipped_with_no_target():
    scenario = board().build()
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_targets(mine, source="Novel Nunchaku")
    scenario.will_choose_targets(source="Novel Nunchaku")
    cast_nunchaku(scenario)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    nunchaku = scenario.find("Novel Nunchaku", Zone.BATTLEFIELD, "alice")
    assert nunchaku.attached_to == mine.id
    assert theirs.zone is Zone.BATTLEFIELD and theirs.damage == 0
    assert mine.damage == 0


def test_with_no_opposing_creature_it_still_attaches_and_nothing_fights():
    scenario = board(bob_creatures=()).build()
    mine = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_targets(mine, source="Novel Nunchaku")
    cast_nunchaku(scenario)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    nunchaku = scenario.find("Novel Nunchaku", Zone.BATTLEFIELD, "alice")
    assert nunchaku.attached_to == mine.id
    assert mine.damage == 0


def test_with_no_creature_of_your_own_the_trigger_has_no_target_and_nothing_happens():
    scenario = board(alice_creatures=()).build()
    theirs = scenario.creature("Grizzly Bears", "bob")
    cast_nunchaku(scenario)
    scenario.pass_until_resolved()
    nunchaku = scenario.find("Novel Nunchaku", Zone.BATTLEFIELD, "alice")
    assert nunchaku.attached_to is None
    assert theirs.damage == 0


def test_the_fight_uses_the_equipped_creature_not_a_creature_chosen_by_name():
    """With two creatures of mine, the one the Nunchaku attached to fights."""
    scenario = board(alice_creatures=("Grizzly Bears", "Hill Giant")).build()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_targets(giant, source="Novel Nunchaku")
    scenario.will_choose_targets(theirs, source="Novel Nunchaku")
    cast_nunchaku(scenario)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert theirs.zone is Zone.GRAVEYARD
    assert giant.damage == 2
    assert bears.damage == 0
