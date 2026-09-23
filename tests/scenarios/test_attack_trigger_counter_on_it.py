"""Scenario: "Whenever `<X>` attacks, put a +1/+1 counter on it." - an attack
trigger whose "it" is the attacking creature its own condition named.

Reader under test: `machines/effects._parse_counter_on_it_trigger_subject_
clause` - "put N `<kind>` counter(s) on it" in a triggered ability with no
antecedent in its own effect text, so "it" is the object the trigger event
happened to (`GameEvent.subject_id`, CR 603.2) - the same referent "untap
it" (Amulet of Vigor) and "on that creature" (Jiang Yanggu) already read.

Cards: **Predator Ooze** (the listed card, "Whenever this creature attacks"
- the attacker is the source itself); **Gleam of Battle** (off-set,
Modern/Pioneer-legal, not in any deck: "Whenever a creature you control
attacks, put a +1/+1 counter on it." - the attacker is some *other*
creature, so a reader that meant "this creature" would put the counter on
the enchantment and be caught).

Rules, each read with `mise run rules:find` in the session that wrote this
file:

- **CR 508.1** - attackers are declared as a turn-based action; the attack
  triggers go on the stack afterwards.
- **CR 122.1a** - a +1/+1 counter adds 1 to power and toughness.
- **CR 702.12b** - "A permanent with indestructible can't be destroyed.
  Such permanents aren't destroyed by lethal damage" - Predator Ooze keeps
  its indestructible whatever its counters.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _ooze_board(alice_extra=(), bob_battlefield=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Predator Ooze", *alice_extra])
        .player("bob", battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario, scenario.creature("Predator Ooze", "alice")


def test_predator_ooze_gets_a_counter_when_it_attacks():
    scenario, ooze = _ooze_board()

    scenario.attack_with(ooze, defending="bob")
    scenario.pass_until_resolved()

    assert ooze.counter_count(Counter.PLUS_ONE) == 1
    assert scenario.game.characteristics_of(ooze).power_toughness == (2, 2)


def test_a_creature_that_does_not_attack_gets_nothing():
    scenario, ooze = _ooze_board(alice_extra=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.attack_with(bears, defending="bob")
    scenario.pass_until_resolved()

    assert ooze.counter_count(Counter.PLUS_ONE) == 0
    assert bears.counter_count(Counter.PLUS_ONE) == 0


def test_the_ooze_leaving_before_its_trigger_resolves_gets_no_counter_and_nothing_else_does():
    scenario, ooze = _ooze_board(alice_extra=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.attack_with(ooze, bears, defending="bob")
    scenario.game.return_to_hand(ooze)
    scenario.pass_until_resolved()

    assert ooze.zone is Zone.HAND
    assert ooze.counter_count(Counter.PLUS_ONE) == 0
    assert bears.counter_count(Counter.PLUS_ONE) == 0


def test_indestructible_stays_with_the_counter_destroy_does_not_kill_it():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Predator Ooze"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ooze = scenario.creature("Predator Ooze", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(ooze, defending="bob")
    scenario.pass_until_resolved()
    assert ooze.counter_count(Counter.PLUS_ONE) == 1

    scenario.game.destroy(ooze)
    scenario.game.destroy(bears)
    scenario.state_based_actions()

    assert ooze.zone is Zone.BATTLEFIELD, "CR 702.12b"
    assert bears.zone is Zone.GRAVEYARD
    assert has_keyword(ooze, "Indestructible", scenario.game)


def test_indestructible_stays_with_the_counter_lethal_damage_does_not_kill_it():
    scenario, ooze = _ooze_board()
    scenario.attack_with(ooze, defending="bob")
    scenario.pass_until_resolved()

    scenario.game.deal_damage(ooze, 5, source=None)
    scenario.state_based_actions()

    assert ooze.zone is Zone.BATTLEFIELD
    assert ooze.counter_count(Counter.PLUS_ONE) == 1


# --------------------------------------------------------------------------
# Gleam of Battle (off-set: "Whenever a creature you control attacks")
# --------------------------------------------------------------------------


def test_gleam_of_battle_puts_a_counter_on_each_attacker_not_on_itself():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Gleam of Battle", "Grizzly Bears", "Memnite", "Ornithopter"])
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    gleam = scenario.find("Gleam of Battle", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "alice")
    thopter = scenario.creature("Ornithopter", "alice")
    angel = scenario.creature("Serra Angel", "bob")

    scenario.attack_with(bears, memnite, defending="bob")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert bears.counter_count(Counter.PLUS_ONE) == 1
    assert memnite.counter_count(Counter.PLUS_ONE) == 1
    assert thopter.counter_count(Counter.PLUS_ONE) == 0, "did not attack"
    assert angel.counter_count(Counter.PLUS_ONE) == 0, "not alice's"
    assert gleam.counter_count(Counter.PLUS_ONE) == 0, "it is the attacker, not the source"


def test_gleam_and_the_oozes_own_trigger_both_land_on_the_ooze():
    scenario, ooze = _ooze_board(alice_extra=["Gleam of Battle"])

    scenario.attack_with(ooze, defending="bob")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert ooze.counter_count(Counter.PLUS_ONE) == 2
