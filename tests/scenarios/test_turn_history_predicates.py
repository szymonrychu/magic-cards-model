"""This-turn/last-turn history predicates newly read by `intervening_if_
holds` and `Game.condition_holds` (CR 603.4, CR 602.5b): Kiora of Salt and
Sand's "if you've activated a loyalty ability this turn", Roiling Canopy's
"if you control at least five other Forests", Darklight Phoenix's "if two or
more creatures died this turn", Command the Stage's "if an opponent was dealt
noncombat damage last turn", and Grim Repriser's "Activate only if an
opponent has been dealt noncombat damage this turn" - plus `Player.
life_gained_this_turn_amount`, the amount twin of `Game.life_gained_this_
turn`'s bare yes/no, that Germinate Recruits and Enlightened Confidant both
need and that S3/S8 consume directly rather than through a condition string.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_kiora_untaps_an_attacker_only_after_activating_a_loyalty_ability_this_turn():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Kiora of Salt and Sand", "Ashiok, Dream Render"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    kiora = scenario.creature("Kiora of Salt and Sand", "alice")

    scenario.attack_with(kiora, defending="bob")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []  # no loyalty ability activated yet this turn


def test_kiora_untaps_an_attacker_after_activating_a_loyalty_ability_this_turn():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Kiora of Salt and Sand", "Ashiok, Dream Render"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    kiora = scenario.creature("Kiora of Salt and Sand", "alice")
    ashiok = scenario.find("Ashiok, Dream Render", Zone.BATTLEFIELD, username="alice")
    scenario.activate(ashiok, index=0, username="alice", targets=["alice"])
    scenario.pass_priority("alice")
    scenario.pass_priority("bob")  # resolve Ashiok's own -1

    scenario.attack_with(kiora, defending="bob")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Kiora of Salt and Sand's triggered ability"]


def test_roiling_canopy_pumps_a_creature_with_five_other_forests_out():
    """Roiling Canopy itself is a plain Land, not a Forest - its own trigger
    watches a *different* Forest entering, so Roiling Canopy has to already
    be on the battlefield and a sixth Forest is the one that enters."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Roiling Canopy"] + ["Forest"] * 5 + ["Grizzly Bears"],
            hand=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Roiling Canopy", [bears])

    scenario.put_onto_battlefield("Forest", "alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Roiling Canopy's triggered ability"]


def test_roiling_canopy_does_not_trigger_with_fewer_than_five_other_forests():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Roiling Canopy"] + ["Forest"] * 3 + ["Grizzly Bears"],
            hand=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Forest", "alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_darklight_phoenix_returns_after_two_creatures_died_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Darklight Phoenix"],
            battlefield=["Grizzly Bears", "Steppe Lynx"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    lynx = scenario.creature("Steppe Lynx", "alice")
    scenario.game.destroy(bears)
    scenario.game.destroy(lynx)
    assert scenario.game.creatures_died_this_turn == 2

    scenario.advance()  # into beginning of combat, the same turn the deaths happened

    assert scenario.stack_names() == ["Darklight Phoenix's triggered ability"]


def test_command_the_stage_returns_to_hand_after_an_opponent_took_noncombat_damage_last_turn():
    scenario = (
        Scenario()
        .player("alice", graveyard=["Command the Stage"], library=["Mountain"])
        .player("bob", life=20, library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")

    scenario.game.deal_damage(bob, 2)  # noncombat damage during alice's turn 1

    scenario.start_at(Step.CLEANUP)
    scenario.advance()  # into bob's turn 2, untap
    while scenario.step is not Step.UPKEEP:
        scenario.advance()

    assert scenario.stack_names() == ["Command the Stage's triggered ability"]


def test_command_the_stage_does_not_return_with_no_damage_dealt_last_turn():
    scenario = (
        Scenario()
        .player("alice", graveyard=["Command the Stage"], library=["Mountain"])
        .player("bob", life=20, library=["Forest"])
        .build()
    )
    scenario.start_at(Step.CLEANUP)
    scenario.advance()
    while scenario.step is not Step.UPKEEP:
        scenario.advance()

    assert scenario.stack_names() == []


def test_grim_repriser_activation_condition_reads_the_this_turn_ledger():
    """Grim Repriser's own graveyard-functioning ability goes through
    `machines/keywords.off_battlefield_activation`, which does not consult
    "Activate only if" restrictions at all yet (a pre-existing gap in that
    entry point, not specific to this restriction - see the report). What is
    this stream's own claim is that `Game.condition_holds` - the reader every
    "Activate only if" restriction is checked through, on or off the
    battlefield - now answers Grim Repriser's own clause correctly, which is
    what this asserts directly."""
    scenario = (
        Scenario().player("alice", graveyard=["Grim Repriser"]).player("bob", life=20).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    clause = "an opponent has been dealt noncombat damage this turn"

    assert scenario.game.condition_holds("alice", clause) is False

    scenario.game.deal_damage(bob, 1)

    assert scenario.game.condition_holds("alice", clause) is True


def test_life_gained_this_turn_amount_tracks_the_real_total_and_clears_next_turn():
    scenario = Scenario().player("alice", life=20).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")

    assert alice.life_gained_this_turn_amount == 0
    alice.gain_life(3)
    alice.gain_life(2)
    assert alice.life_gained_this_turn_amount == 5

    scenario.start_at(Step.CLEANUP)
    scenario.advance()  # into bob's turn
    assert alice.life_gained_this_turn_amount == 0
