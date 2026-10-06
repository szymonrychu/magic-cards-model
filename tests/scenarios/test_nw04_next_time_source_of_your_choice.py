"""Scenario: "The next time a [red] source of your choice would deal damage to
<you | any target> this turn, prevent that damage." - CR 615.8's next-instance
shield keyed to a chosen source, with CR 615.5's payoffs.

Rules, each read in full with `mise run rules:find`:

- CR 609.7a - "If an effect requires a player to choose a source of damage,
  they may choose a permanent; a spell on the stack (including a permanent
  spell); ... The source is chosen when the effect is created."
- CR 609.7b - "Some effects from resolved spells and abilities prevent or
  replace damage from sources with certain properties, such as a creature or a
  source of a particular color. When the source would deal damage, the
  "shield" rechecks the source's properties."
- CR 615.8 - "... These effects prevent the next instance of damage from that
  source, regardless of how much damage that is. Once an instance of damage
  from that source has been prevented, any subsequent instances of damage that
  would be dealt by that source are dealt normally."
- CR 615.5 - "Some prevention effects also include an additional effect, which
  may refer to the amount of damage that was prevented. The prevention takes
  place at the time the original event would have happened; the rest of the
  effect takes place immediately afterward."
- CR 615.12 - "Existing damage prevention shields won't be reduced by damage
  that can't be prevented."
- CR 603.12 - a reflexive triggered ability ("When damage is prevented this
  way, ...") follows the rules for delayed triggered abilities: it uses the
  stack.
- CR 608.2h / 113.7a - a spell that has left the stack still deals the damage
  its text says it deals, as it last existed.

Listed printings: Deflecting Palm, Reverse Damage, Intervention Pact, New Way
Forward, Honorable Passage. Proof printings (not listed, in no api deck, legal
in Modern): Circle of Protection: Red's activated "The next time a red source
of your choice would deal damage to you this turn, prevent that damage." and
Sanctum Guardian's sacrifice-cost "... would deal damage to any target this
turn, prevent that damage."
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.effects import registries
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

LISTED = [
    "Deflecting Palm",
    "Reverse Damage",
    "Intervention Pact",
    "New Way Forward",
    "Honorable Passage",
]
PROOF = ["Circle of Protection: Red", "Sanctum Guardian"]


@pytest.mark.parametrize("name", LISTED + PROOF)
def test_every_listed_and_proof_card_reads_handled(name):
    outcomes = {clause.outcome for clause in card_support(card(name)).clauses}
    assert outcomes == {"handled"}, name


def test_a_next_n_shield_against_a_chosen_source_to_you_reads():
    """The same reader's CR 615.7 twin: "Prevent the next 3 damage that a
    source of your choice would deal to you this turn." (no printing in the
    target formats carries it alone; read by the same sentence reader)."""
    text = "Prevent the next 3 damage that a source of your choice would deal to you this turn."
    assert registries.effect_for("Probe", text) is not None


def _board(*, alice_hand=(), alice_battlefield=(), bob_hand=(), bob_battlefield=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=[*["Plains"] * 3, *["Mountain"] * 2, *["Island"] * 2, *alice_battlefield],
            library=["Plains"] * 10,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=[*["Mountain"] * 4, *bob_battlefield],
            library=["Mountain"] * 10,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _respond(scenario, name, *, chosen, username="alice", targets=None):
    """Cast `name` with `chosen` as the source of `username`'s choice."""
    if scenario.priority_holder != username:
        scenario.pass_priority(scenario.priority_holder)
    scenario.will_choose_cards(chosen, username=username)
    return scenario.cast_and_resolve(name, username=username, targets=targets, auto=True)


def _bolt_on_stack(scenario, target):
    scenario.pass_priority("alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", username="bob", targets=[target], auto=True)
    scenario.pass_priority("bob")
    return bolt


def _ping(scenario, ballista, target):
    if scenario.priority_holder != "bob":
        scenario.pass_priority(scenario.priority_holder)
    scenario.activate(ballista, index=1, username="bob", targets=[target])
    scenario.resolve_top()


def _ballista(scenario, counters):
    ballista = scenario.creature("Walking Ballista", "bob")
    scenario.game.add_counters(ballista, "+1/+1", counters)
    return ballista


# -- Reverse Damage: the next instance, and life equal to it ------------------


def test_reverse_damage_prevents_the_chosen_spells_damage_and_gains_that_much():
    scenario = _board(alice_hand=["Reverse Damage"], bob_hand=["Lightning Bolt"])
    bolt = _bolt_on_stack(scenario, "alice")
    _respond(scenario, "Reverse Damage", chosen=bolt)

    scenario.resolve_top()

    assert scenario.player("alice").life == 23


def test_reverse_damage_is_used_up_by_one_instance():
    """CR 615.8: the first instance is prevented, the second is dealt."""
    scenario = _board(alice_hand=["Reverse Damage"], bob_battlefield=["Walking Ballista"])
    ballista = _ballista(scenario, 2)
    _respond(scenario, "Reverse Damage", chosen=ballista)

    _ping(scenario, ballista, "alice")
    assert scenario.player("alice").life == 21  # prevented, 1 life gained
    _ping(scenario, ballista, "alice")
    assert scenario.player("alice").life == 20  # dealt normally


def test_reverse_damage_ignores_another_sources_damage():
    scenario = _board(
        alice_hand=["Reverse Damage"],
        bob_hand=["Lightning Bolt"],
        bob_battlefield=["Walking Ballista"],
    )
    ballista = _ballista(scenario, 1)
    _respond(scenario, "Reverse Damage", chosen=ballista)

    bolt = _bolt_on_stack(scenario, "alice")
    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 17
    _ping(scenario, ballista, "alice")
    assert scenario.player("alice").life == 18  # the chosen source's instance


def test_reverse_damage_protects_only_you_not_your_creatures():
    scenario = _board(
        alice_hand=["Reverse Damage"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Walking Ballista"],
    )
    giant = scenario.creature("Hill Giant", "alice")
    ballista = _ballista(scenario, 2)
    _respond(scenario, "Reverse Damage", chosen=ballista)

    _ping(scenario, ballista, giant)
    assert giant.damage == 1
    assert scenario.player("alice").life == 20
    _ping(scenario, ballista, "alice")
    assert scenario.player("alice").life == 21  # the shield was still waiting


def test_unpreventable_damage_does_not_use_up_the_shield():
    """CR 615.12: Skullcrack's damage can't be prevented, so the shield
    prevents nothing, gains nothing, and is not reduced."""
    scenario = _board(
        alice_hand=["Reverse Damage"],
        bob_hand=["Skullcrack"],
        bob_battlefield=["Walking Ballista"],
    )
    ballista = _ballista(scenario, 2)
    _respond(scenario, "Reverse Damage", chosen=ballista)
    scenario.pass_priority("alice")
    scenario.cast_and_resolve("Skullcrack", username="bob", targets=["alice"], auto=True)
    assert scenario.player("alice").life == 17

    _ping(scenario, ballista, "alice")

    assert scenario.player("alice").life == 16  # still unpreventable this turn
    (shield,) = scenario.game.prevention_shields
    assert not shield.spent and shield.prevented == 0


# -- Intervention Pact: the same shield beside a pact upkeep ------------------


def test_intervention_pact_gains_the_prevented_life_and_keeps_its_upkeep_cost():
    scenario = _board(alice_hand=["Intervention Pact"], bob_hand=["Lightning Bolt"])
    bolt = _bolt_on_stack(scenario, "alice")
    _respond(scenario, "Intervention Pact", chosen=bolt)
    scenario.resolve_top()
    assert scenario.player("alice").life == 23

    scenario.will_pay_the_mana_cost(False, username="alice", source="Intervention Pact")
    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == "alice"):
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()

    assert not scenario.game.is_in_game("alice"), "CR 104.3e: unpaid, alice loses"


# -- Deflecting Palm: that much damage to the source's controller -------------


def test_deflecting_palm_deals_the_prevented_amount_to_the_sources_controller():
    scenario = _board(alice_hand=["Deflecting Palm"], bob_hand=["Lightning Bolt"])
    bolt = _bolt_on_stack(scenario, "alice")
    palm = _respond(scenario, "Deflecting Palm", chosen=bolt)

    scenario.resolve_top()

    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 17
    # CR 608.2h: Deflecting Palm deals it from the graveyard, as it last was.
    assert palm.zone is Zone.GRAVEYARD


def test_deflecting_palm_reflects_each_time_only_once():
    scenario = _board(alice_hand=["Deflecting Palm"], bob_battlefield=["Walking Ballista"])
    ballista = _ballista(scenario, 2)
    _respond(scenario, "Deflecting Palm", chosen=ballista)

    _ping(scenario, ballista, "alice")
    _ping(scenario, ballista, "alice")

    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 19


def test_deflecting_palm_reflects_nothing_when_nothing_was_prevented():
    scenario = _board(
        alice_hand=["Deflecting Palm"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Walking Ballista"],
    )
    giant = scenario.creature("Hill Giant", "alice")
    ballista = _ballista(scenario, 1)
    _respond(scenario, "Deflecting Palm", chosen=ballista)

    _ping(scenario, ballista, giant)

    assert giant.damage == 1
    assert scenario.player("bob").life == 20


def test_deflecting_palm_hits_whoever_controls_the_source_as_it_is_prevented():
    """Alice chooses her own Walking Ballista: "that source's controller" is
    alice herself, so the reflected damage comes back to her."""
    scenario = _board(alice_hand=["Deflecting Palm"], alice_battlefield=["Walking Ballista"])
    ballista = scenario.creature("Walking Ballista", "alice")
    scenario.game.add_counters(ballista, "+1/+1", 1)
    _respond(scenario, "Deflecting Palm", chosen=ballista)

    scenario.activate(ballista, index=1, username="alice", targets=["alice"])
    scenario.resolve_top()

    assert scenario.player("alice").life == 19  # 1 prevented, then 1 from Palm
    assert scenario.player("bob").life == 20


# -- Honorable Passage: any target, reflect only from a red source ------------


def test_honorable_passage_protects_a_creature_and_reflects_a_red_sources_damage():
    scenario = _board(
        alice_hand=["Honorable Passage"],
        alice_battlefield=["Hill Giant"],
        bob_hand=["Lightning Bolt"],
    )
    giant = scenario.creature("Hill Giant", "alice")
    bolt = _bolt_on_stack(scenario, giant)
    _respond(scenario, "Honorable Passage", chosen=bolt, targets=[giant])

    scenario.resolve_top()

    assert giant.zone is Zone.BATTLEFIELD and giant.damage == 0
    assert scenario.player("bob").life == 17


def test_honorable_passage_does_not_reflect_a_nonred_sources_damage():
    """The payoff asks "from a red source" of the source as the damage would
    be dealt (CR 609.7b); a colorless Walking Ballista's damage is prevented
    and reflects nothing."""
    scenario = _board(alice_hand=["Honorable Passage"], bob_battlefield=["Walking Ballista"])
    ballista = _ballista(scenario, 2)
    _respond(scenario, "Honorable Passage", chosen=ballista, targets=["bob"])
    (shield,) = scenario.game.prevention_shields
    assert shield.reflects is not None and shield.reflects.source_quality == "red"

    _ping(scenario, ballista, "bob")  # any target: bob himself may be the one protected

    assert scenario.player("bob").life == 20
    _ping(scenario, ballista, "bob")
    assert scenario.player("bob").life == 19  # used up by the first instance


def test_honorable_passage_protects_only_its_target():
    scenario = _board(
        alice_hand=["Honorable Passage"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Walking Ballista"],
    )
    giant = scenario.creature("Hill Giant", "alice")
    ballista = _ballista(scenario, 2)
    _respond(scenario, "Honorable Passage", chosen=ballista, targets=[giant])

    _ping(scenario, ballista, "alice")
    assert scenario.player("alice").life == 19
    _ping(scenario, ballista, giant)
    assert giant.damage == 0


# -- New Way Forward: a reflexive trigger on the stack ------------------------


def test_new_way_forward_reflexive_trigger_damages_and_draws():
    scenario = _board(alice_hand=["New Way Forward"], bob_hand=["Lightning Bolt"])
    alice = scenario.player("alice")
    bolt = _bolt_on_stack(scenario, "alice")
    _respond(scenario, "New Way Forward", chosen=bolt)
    hand_before = len(alice.hand)

    scenario.resolve_top()  # the Bolt: prevented
    assert alice.life == 20
    # CR 603.12: the payoff is a triggered ability that goes on the stack.
    assert scenario.player("bob").life == 20
    assert len(alice.hand) == hand_before
    scenario.game.put_triggers_on_stack()
    assert len(scenario.game.stack) == 1
    scenario.resolve_top()

    assert scenario.player("bob").life == 17
    assert len(alice.hand) == hand_before + 3


def test_new_way_forward_does_not_trigger_when_nothing_is_prevented():
    scenario = _board(
        alice_hand=["New Way Forward"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Walking Ballista"],
    )
    giant = scenario.creature("Hill Giant", "alice")
    ballista = _ballista(scenario, 1)
    _respond(scenario, "New Way Forward", chosen=ballista)

    _ping(scenario, ballista, giant)
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack_is_empty
    assert scenario.player("bob").life == 20


# -- proof printings: Circle of Protection: Red, Sanctum Guardian -------------


def test_circle_of_protection_red_offers_only_red_sources():
    scenario = _board(
        alice_battlefield=["Circle of Protection: Red"],
        bob_hand=["Lightning Bolt"],
        bob_battlefield=["Walking Ballista"],
    )
    ballista = _ballista(scenario, 1)
    circle = scenario.find("Circle of Protection: Red", Zone.BATTLEFIELD, "alice")
    bolt = _bolt_on_stack(scenario, "alice")
    scenario.will_choose_cards(bolt, username="alice")
    scenario.activate(circle, *scenario.untapped_sources("Plains"), index=0, username="alice")
    scenario.resolve_top()

    choices = [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_CARDS]
    assert choices and bolt.id in choices[-1].cards and ballista.id not in choices[-1].cards
    scenario.resolve_top()
    assert scenario.player("alice").life == 20


def test_circle_of_protection_red_leaves_other_damage_alone():
    scenario = _board(
        alice_battlefield=["Circle of Protection: Red"],
        bob_hand=["Lightning Bolt"],
        bob_battlefield=["Walking Ballista"],
    )
    ballista = _ballista(scenario, 1)
    circle = scenario.find("Circle of Protection: Red", Zone.BATTLEFIELD, "alice")
    bolt = _bolt_on_stack(scenario, "alice")
    scenario.will_choose_cards(bolt, username="alice")
    scenario.activate(circle, *scenario.untapped_sources("Plains"), index=0, username="alice")
    scenario.resolve_top()

    _ping(scenario, ballista, "alice")
    assert scenario.player("alice").life == 19
    scenario.resolve_top()
    assert scenario.player("alice").life == 19  # the Bolt's instance prevented


def test_sanctum_guardian_shields_any_target_from_the_chosen_source():
    scenario = _board(
        alice_battlefield=["Sanctum Guardian", "Hill Giant"],
        bob_hand=["Lightning Bolt"],
    )
    giant = scenario.creature("Hill Giant", "alice")
    guardian = scenario.find("Sanctum Guardian", Zone.BATTLEFIELD, "alice")
    bolt = _bolt_on_stack(scenario, giant)
    scenario.will_choose_cards(bolt, username="alice")
    scenario.activate(guardian, index=0, username="alice", targets=[giant])
    scenario.resolve_top()
    assert guardian.zone is Zone.GRAVEYARD

    scenario.resolve_top()

    assert giant.zone is Zone.BATTLEFIELD and giant.damage == 0
