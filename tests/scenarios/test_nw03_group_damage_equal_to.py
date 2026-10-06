"""Scenario: group damage whose amount is "equal to" something - "<self>
deals damage to each <group> equal to <amount>" - and the group bite "each
<group> you control deals damage equal to its power to <target>".

Rules, each read in full with `mise run rules:find`:

- CR 608.2h - "If an effect requires information from the game (such as the
  number of creatures on the battlefield), the answer is determined only once,
  when the effect is applied." - the amount is read once, before any damage.
- CR 700.5 - "A player's devotion to [color] is equal to the number of mana
  symbols of that color among the mana costs of permanents that player
  controls."
- CR 120.1 - "An object that deals damage is the source of that damage." -
  each biting creature is its own source.
- CR 700.9 - "A permanent is modified if it has one or more counters on it
  ..., if it is equipped ..., or if it is enchanted by an Aura that is
  controlled by that permanent's controller."
- CR 608.2c - "The controller of the spell or ability follows its
  instructions in the order written." - the counter goes on first, so the
  countered creature is modified when the damage is dealt.
- CR 608.2b - an illegal target is not affected; the other parts still happen.

Listed printings: Skyreaping, Signature Slam. Proof printings, neither listed,
neither in an api deck, both legal in Modern: Structural Assault ("Destroy all
artifacts, then Structural Assault deals damage to each creature equal to the
number of artifacts that were put into graveyards from the battlefield this
turn."), Bartz and Boko (an enters trigger, "each other Bird you control deals
damage equal to its power to target creature an opponent controls").
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario


@pytest.mark.parametrize(
    "name", ["Skyreaping", "Signature Slam", "Structural Assault", "Bartz and Boko"]
)
def test_every_listed_and_proof_card_reads_handled(name):
    outcomes = {clause.outcome for clause in card_support(card(name)).clauses}
    assert outcomes == {"handled"}, name


def _board(*, alice_battlefield=(), bob_battlefield=(), alice_hand=(), bob_hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=[*["Forest"] * 3, *["Mountain"] * 5, *alice_battlefield],
            library=["Forest"] * 8,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=[*["Plains"] * 4, *bob_battlefield],
            library=["Plains"] * 8,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _alice_casts(scenario, name, targets=None):
    if scenario.priority_holder != "alice":
        scenario.pass_priority(scenario.priority_holder)
    return scenario.cast_and_resolve(name, username="alice", targets=targets, auto=True)


# -- Skyreaping: each creature with flying, equal to your devotion to green -----


def test_skyreaping_deals_your_devotion_to_each_flier():
    # Llanowar Elves {G} and Grizzly Bears {1}{G}: devotion to green 2.
    scenario = _board(
        alice_hand=["Skyreaping"],
        alice_battlefield=["Llanowar Elves", "Grizzly Bears", "Wind Drake"],
        bob_battlefield=["Serra Angel", "Hill Giant"],
    )
    drake = scenario.creature("Wind Drake", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    _alice_casts(scenario, "Skyreaping")

    assert drake.zone is Zone.GRAVEYARD  # its own controller's flier too
    assert angel.damage == 2
    assert giant.damage == 0


def test_skyreaping_with_no_devotion_deals_nothing():
    scenario = _board(alice_hand=["Skyreaping"], bob_battlefield=["Serra Angel"])
    angel = scenario.creature("Serra Angel", "bob")

    _alice_casts(scenario, "Skyreaping")

    assert angel.damage == 0


def test_skyreaping_amount_is_read_once_before_the_damage():
    # Birds of Paradise {G} is itself a flier: it dies to the damage, but the
    # devotion it gave was already counted (CR 608.2h).
    scenario = _board(
        alice_hand=["Skyreaping"],
        alice_battlefield=["Birds of Paradise", "Grizzly Bears", "Llanowar Elves"],
        bob_battlefield=["Serra Angel"],
    )
    birds = scenario.creature("Birds of Paradise", "alice")
    angel = scenario.creature("Serra Angel", "bob")

    _alice_casts(scenario, "Skyreaping")

    assert birds.zone is Zone.GRAVEYARD
    assert angel.damage == 3


def test_skyreaping_does_not_hit_players():
    scenario = _board(alice_hand=["Skyreaping"], alice_battlefield=["Llanowar Elves"])

    _alice_casts(scenario, "Skyreaping")

    assert scenario.player("bob").life == 20
    assert scenario.player("alice").life == 20


# -- Structural Assault: artifacts put into graveyards this turn ---------------


def test_structural_assault_counts_the_artifacts_it_destroyed():
    scenario = _board(
        alice_hand=["Structural Assault"],
        alice_battlefield=["Ornithopter", "Bonesplitter"],
        bob_battlefield=["Grizzly Bears", "Hill Giant"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    _alice_casts(scenario, "Structural Assault")

    assert scenario.find("Ornithopter", Zone.GRAVEYARD, "alice")
    assert bears.zone is Zone.GRAVEYARD
    assert giant.damage == 2


def test_structural_assault_counts_artifacts_that_died_earlier_this_turn():
    scenario = _board(
        alice_hand=["Structural Assault", "Shock"],
        alice_battlefield=["Ornithopter"],
        bob_battlefield=["Hill Giant", "Ornithopter"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    bobs_thopter = scenario.creature("Ornithopter", "bob")
    _alice_casts(scenario, "Shock", [bobs_thopter])

    _alice_casts(scenario, "Structural Assault")

    # Bob's Ornithopter earlier this turn + Alice's destroyed now = 2.
    assert giant.damage == 2
    assert scenario.player("bob").life == 20


def test_structural_assault_with_no_artifacts_deals_nothing():
    scenario = _board(alice_hand=["Structural Assault"], bob_battlefield=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")

    _alice_casts(scenario, "Structural Assault")

    assert bears.damage == 0


# -- Signature Slam: each modified creature you control bites ------------------


def test_signature_slam_countered_creature_and_other_modified_ones_bite():
    scenario = _board(
        alice_hand=["Signature Slam"],
        alice_battlefield=["Grizzly Bears", "Llanowar Elves", "Hill Giant"],
        bob_battlefield=["Serra Angel"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    scenario.game.add_counters(elves, "+1/+1", 1)

    _alice_casts(scenario, "Signature Slam", [bears, angel])

    assert bears.counters["+1/+1"] == 1
    # Bears 3 + Elves 2 = 5 (the Giant is unmodified and deals nothing).
    assert angel.zone is Zone.GRAVEYARD
    assert giant.damage == 0


def test_signature_slam_an_equipped_creature_is_modified():
    scenario = _board(
        alice_hand=["Signature Slam"],
        alice_battlefield=["Grizzly Bears", "Hill Giant", "Bonesplitter"],
        bob_battlefield=["Eagle of the Great Shelf"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    eagle = scenario.creature("Eagle of the Great Shelf", "bob")
    scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice").attach_to(giant)

    _alice_casts(scenario, "Signature Slam", [bears, eagle])

    # Bears 3 + equipped Giant 5 = 8 to the 2/5 Eagle.
    assert eagle.zone is Zone.GRAVEYARD


def test_signature_slam_opponents_modified_creatures_do_not_bite():
    scenario = _board(
        alice_hand=["Signature Slam"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Eagle of the Great Shelf", "Hill Giant"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    eagle = scenario.creature("Eagle of the Great Shelf", "bob")
    bobs_giant = scenario.creature("Hill Giant", "bob")
    scenario.game.add_counters(bobs_giant, "+1/+1", 2)

    _alice_casts(scenario, "Signature Slam", [bears, eagle])

    assert eagle.damage == 3


def test_signature_slam_with_its_victim_gone_still_puts_the_counter():
    scenario = _board(
        alice_hand=["Signature Slam"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Serra Angel"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    casting = scenario.cast("Signature Slam", username="alice")
    casting.choose_targets([bears, angel])
    scenario.auto_pay(casting.begin_paying(), username="alice")
    scenario.put_on_stack(casting)
    scenario.game.return_to_hand(angel)
    scenario.resolve_top()

    assert bears.counters["+1/+1"] == 1


def test_signature_slam_with_its_counter_target_gone_others_still_bite():
    scenario = _board(
        alice_hand=["Signature Slam"],
        alice_battlefield=["Grizzly Bears", "Llanowar Elves"],
        bob_battlefield=["Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    bob_bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.add_counters(elves, "+1/+1", 1)
    casting = scenario.cast("Signature Slam", username="alice")
    casting.choose_targets([bears, bob_bears])
    scenario.auto_pay(casting.begin_paying(), username="alice")
    scenario.put_on_stack(casting)
    scenario.game.return_to_hand(bears)
    scenario.resolve_top()

    assert bob_bears.zone is Zone.GRAVEYARD  # the Elves' 2


# -- Bartz and Boko: each other Bird you control, on an enters trigger -------


def test_bartz_and_boko_other_birds_bite_the_target():
    scenario = _board(
        alice_hand=["Bartz and Boko"],
        alice_battlefield=["Jackdaw Savior", "Birds of Paradise"],
        bob_battlefield=["Eagle of the Great Shelf"],
    )
    eagle = scenario.creature("Eagle of the Great Shelf", "bob")

    bartz = scenario.find("Bartz and Boko", Zone.HAND, "alice")
    scenario.game.put_onto_battlefield(bartz, "alice")
    scenario.choose_trigger_targets("Bartz and Boko", [eagle])
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    # Jackdaw Savior 3 + Birds 0; Bartz and Boko itself ("other") 4 is not dealt.
    assert bartz.zone is Zone.BATTLEFIELD
    assert eagle.damage == 3
