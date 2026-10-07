"""What "it devoured" counts - CR 702.82b, recorded as devour runs.

Rules read in full with `mise run rules:find` this session:

- **CR 702.82a** - "'Devour N' means 'As this object enters, you may
  sacrifice any number of creatures. This permanent enters with N +1/+1
  counters on it for each creature sacrificed this way.'"
- **CR 702.82b** - "Some objects have abilities that refer to the number of
  creatures the permanent devoured. 'It devoured' means 'sacrificed as a
  result of its devour ability as it entered the battlefield.'"
- **CR 614.12a** - the sacrifice is a choice made before it enters.
- **CR 608.2h** - each devoured creature is judged as it last existed: a
  Goblin it devoured is a Goblin it sacrificed, whatever the card is now.

Voracious Dragon ("twice the number of Goblins it devoured") is the reported
card; Skullmulcher ("draw a card for each creature it devoured") and Marrow
Chomper ("you gain 2 life for each creature it devoured") are the proof
printings for the count, read through the draw and life-gain clauses rather
than damage.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(hand, battlefield, bob_battlefield=()):
    scenario = (
        Scenario()
        .player("alice", hand=list(hand), battlefield=list(battlefield), library=["Mountain"] * 10)
        .player("bob", battlefield=list(bob_battlefield), library=["Mountain"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _enter_devouring(scenario, name, devoured, target=None):
    scenario.will_choose_cards(*devoured, username="alice", source=name)
    if target is not None:
        scenario.choose_trigger_targets(name, [target])
    entered = scenario.put_onto_battlefield(name)
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
    return entered


def test_voracious_dragon_deals_twice_the_goblins_it_devoured():
    scenario = _board(["Voracious Dragon"], ["Raging Goblin", "Mogg Fanatic", "Grizzly Bears"])
    bob = scenario.player("bob")
    devoured = [scenario.creature(n) for n in ("Raging Goblin", "Mogg Fanatic", "Grizzly Bears")]
    dragon = _enter_devouring(scenario, "Voracious Dragon", devoured, target=bob)

    assert dragon.counter_count("+1/+1") == 3, "devour 1: one counter per creature"
    assert sum("Goblin" in d.subtypes for d in dragon.devoured) == 2
    assert bob.life == 16, "two Goblins, twice that"


def test_devouring_no_goblins_deals_nothing():
    scenario = _board(["Voracious Dragon"], ["Grizzly Bears"])
    bob = scenario.player("bob")
    _enter_devouring(scenario, "Voracious Dragon", [scenario.creature("Grizzly Bears")], target=bob)
    assert bob.life == 20


def test_devouring_nothing_records_nothing():
    scenario = _board(["Voracious Dragon"], ["Raging Goblin"])
    bob = scenario.player("bob")
    dragon = _enter_devouring(scenario, "Voracious Dragon", [], target=bob)
    assert dragon.devoured == ()
    assert bob.life == 20
    assert scenario.creature("Raging Goblin").zone is Zone.BATTLEFIELD


def test_a_changeling_it_devoured_was_a_goblin_as_it_last_existed():
    scenario = _board(["Voracious Dragon"], ["Changeling Outcast"])
    bob = scenario.player("bob")
    _enter_devouring(
        scenario, "Voracious Dragon", [scenario.creature("Changeling Outcast")], target=bob
    )
    assert bob.life == 18


def test_the_count_reaches_a_creature_target_too():
    scenario = _board(
        ["Voracious Dragon"], ["Raging Goblin", "Mogg Fanatic"], bob_battlefield=["Craw Wurm"]
    )
    wurm = scenario.creature("Craw Wurm", "bob")
    devoured = [scenario.creature("Raging Goblin"), scenario.creature("Mogg Fanatic")]
    _enter_devouring(scenario, "Voracious Dragon", devoured, target=wurm)
    scenario.state_based_actions()
    assert wurm.zone is Zone.GRAVEYARD, "4 damage to a 6/4"


def test_a_dragon_that_comes_back_without_devouring_has_devoured_nothing():
    """CR 400.7: a new object; its devour ran again and sacrificed nothing."""
    scenario = _board(["Voracious Dragon"], ["Raging Goblin", "Mogg Fanatic"])
    bob = scenario.player("bob")
    devoured = [scenario.creature("Raging Goblin"), scenario.creature("Mogg Fanatic")]
    dragon = _enter_devouring(scenario, "Voracious Dragon", devoured, target=bob)
    assert bob.life == 16

    scenario.game.return_to_hand(dragon)
    again = _enter_devouring(scenario, "Voracious Dragon", [], target=bob)
    assert again.devoured == ()
    assert bob.life == 16


# -- proof printings: the same count read by a draw and by a life gain ---------------


def test_skullmulcher_draws_a_card_for_each_creature_it_devoured():
    scenario = _board(["Skullmulcher"], ["Raging Goblin", "Grizzly Bears"])
    hand_before = len(scenario.player("alice").hand)
    devoured = [scenario.creature("Raging Goblin"), scenario.creature("Grizzly Bears")]
    _enter_devouring(scenario, "Skullmulcher", devoured)

    assert len(scenario.player("alice").hand) == hand_before - 1 + 2


def test_skullmulcher_devouring_nothing_draws_nothing():
    scenario = _board(["Skullmulcher"], ["Raging Goblin"])
    hand_before = len(scenario.player("alice").hand)
    _enter_devouring(scenario, "Skullmulcher", [])
    assert len(scenario.player("alice").hand) == hand_before - 1


def test_marrow_chomper_gains_two_life_for_each_creature_it_devoured():
    scenario = _board(["Marrow Chomper"], ["Raging Goblin", "Mogg Fanatic", "Grizzly Bears"])
    devoured = [scenario.creature(n) for n in ("Raging Goblin", "Mogg Fanatic", "Grizzly Bears")]
    _enter_devouring(scenario, "Marrow Chomper", devoured)
    assert scenario.player("alice").life == 26
