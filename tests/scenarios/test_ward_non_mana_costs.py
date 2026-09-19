"""Ward with a cost that is not mana: the targeting player is asked to pay it.

Battle report B4-07: alice targeted Sire of Seven Deaths ("Ward-Pay 7 life.")
with Ulamog's cast trigger; the ward trigger resolved with no decision, no life
was paid, and the trigger was countered. `WardTrigger.begin_paying` existed but
nothing in the game loop ever called it, so every ward whose cost was not
already paid by hand countered.

Rules read in full with `mise run rules:find` this session:

- **CR 702.21a** - "Ward [cost] means 'Whenever this permanent becomes the
  target of a spell or ability an opponent controls, counter that spell or
  ability unless that player pays [cost].'"
- **CR 118.12a** - "[Do something] unless [a player does something else]"
  means "[A player may do something else]. If [that player doesn't], [do
  something]." - so the ward trigger asks, as it resolves, whether the
  targeting spell's or ability's controller pays.
- **CR 118.3** - "A player can't pay a cost without having the necessary
  resources to pay it fully." - 6 life cannot pay 7, an empty hand cannot
  discard, a player with no creature cannot sacrifice one.
- **CR 119.4** - life can be paid only down to zero.
- **CR 701.9b** - the discarding player chooses which card.
- **CR 701.21a** - a player sacrifices a permanent they control.
- **CR 608.2g** - "If an effect gives a player the option to pay mana, they may
  activate mana abilities before taking that action." Mana ward costs keep
  paying from mana already in the pool.

Sire of Seven Deaths is the reported card. Sunset Saboteur ("Ward-Discard a
card.") and Vein Ripper ("Ward-Sacrifice a creature.") are off-pool, with
different non-mana costs; Captain Howler, Sea Scourge ("Ward-{2}, Pay 2 life.")
mixes mana and life in one cost.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind, DecisionPending
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario


def _bolt_at(warded: str, *, life: int = 20, hand=(), battlefield=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            life=life,
            hand=["Lightning Bolt", *hand],
            battlefield=["Mountain", "Mountain", "Mountain", *battlefield],
        )
        .player("bob", battlefield=[warded])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    target = scenario.creature(warded, "bob")
    (mountain,) = scenario.untapped_sources("Mountain")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[target])
    assert scenario.stack_names() == ["Lightning Bolt", f"{warded}'s triggered ability"]
    return scenario, target, bolt


def _asked(scenario, kind):
    return [d for d in scenario.questions_asked() if d.kind is kind]


def test_sires_ward_asks_the_bolts_controller_to_pay_7_life_and_paying_lets_it_through():
    scenario, sire, bolt = _bolt_at("Sire of Seven Deaths")
    scenario.will_pay_the_life(True, username="alice")

    scenario.resolve_top()  # the ward trigger

    (question,) = _asked(scenario, DecisionKind.PAY_LIFE)
    assert question.player == "alice"
    assert question.amount == 7
    assert question.source == "Sire of Seven Deaths"
    assert scenario.player("alice").life == 13
    assert bolt.zone is Zone.STACK

    scenario.resolve_top()  # the Bolt
    assert sire.damage == 3


def test_declining_to_pay_the_life_counters_the_spell():
    scenario, sire, bolt = _bolt_at("Sire of Seven Deaths")
    scenario.will_pay_the_life(False, username="alice")

    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 20
    assert sire.damage == 0


def test_a_player_below_the_life_cost_cannot_pay_and_the_spell_is_countered():
    """CR 118.3, CR 119.4: 6 life cannot pay 7."""
    scenario, _sire, bolt = _bolt_at("Sire of Seven Deaths", life=6)

    scenario.resolve_top()

    (question,) = _asked(scenario, DecisionKind.PAY_LIFE)
    assert not question.affirmative_is_legal
    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 6


def test_a_paused_seat_is_asked_rather_than_countered_silently():
    scenario, _sire, bolt = _bolt_at("Sire of Seven Deaths")
    scenario.game.decisions.pause_when_unanswered = True

    with pytest.raises(DecisionPending) as excinfo:
        scenario.resolve_top()

    pending = excinfo.value.pending
    assert pending.decision.kind is DecisionKind.PAY_LIFE
    assert pending.decision.player == "alice"
    assert pending.decision.amount == 7


def test_an_ability_targeting_a_warded_permanent_is_paid_for_by_its_controller():
    """CR 702.21a: "a spell **or ability** an opponent controls" - the reported
    case was a triggered ability; an activated one takes the same question."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Icy Manipulator", "Mountain"])
        .player("bob", battlefield=["Sire of Seven Deaths"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    icy = scenario.find("Icy Manipulator", Zone.BATTLEFIELD)
    sire = scenario.creature("Sire of Seven Deaths", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.activate(icy, mountain, targets=[sire])
    scenario.will_pay_the_life(True, username="alice")

    scenario.resolve_top()  # the ward trigger
    assert scenario.player("alice").life == 13

    scenario.resolve_top()  # Icy's ability, not countered
    assert sire.tapped


def test_ward_discard_a_card_lets_the_targeting_player_choose_the_discard():
    """Sunset Saboteur (off-pool): "Ward-Discard a card." CR 701.9b."""
    scenario, saboteur, bolt = _bolt_at("Sunset Saboteur", hand=["Grizzly Bears", "Shock"])
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    scenario.will_take_the_may(True, username="alice", source="Sunset Saboteur")
    scenario.will_choose_cards(bears, username="alice", source="Sunset Saboteur")

    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert [state.name for state in scenario.player("alice").hand] == ["Shock"]
    assert bolt.zone is Zone.STACK
    scenario.resolve_top()
    assert saboteur.zone is Zone.GRAVEYARD


def test_ward_discard_declined_counters_and_keeps_the_hand():
    scenario, _saboteur, bolt = _bolt_at("Sunset Saboteur", hand=["Grizzly Bears"])
    scenario.will_take_the_may(False, username="alice", source="Sunset Saboteur")

    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert [state.name for state in scenario.player("alice").hand] == ["Grizzly Bears"]


def test_ward_discard_with_an_empty_hand_cannot_be_paid():
    """CR 118.3: no card to discard, so the affirmative is not a legal answer."""
    scenario, _saboteur, bolt = _bolt_at("Sunset Saboteur")

    scenario.resolve_top()

    (question,) = [d for d in scenario.questions_asked() if d.source == "Sunset Saboteur"]
    assert not question.affirmative_is_legal
    assert bolt.zone is Zone.GRAVEYARD


def test_ward_sacrifice_a_creature_is_paid_with_a_chosen_creature():
    """Vein Ripper (off-pool): "Ward-Sacrifice a creature." CR 701.21a."""
    scenario, _ripper, bolt = _bolt_at("Vein Ripper", battlefield=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_take_the_may(True, username="alice", source="Vein Ripper")
    scenario.will_choose_cards(bears, username="alice", source="Vein Ripper")

    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert bolt.zone is Zone.STACK


def test_ward_sacrifice_with_no_creature_to_sacrifice_counters():
    scenario, _ripper, bolt = _bolt_at("Vein Ripper")

    scenario.resolve_top()

    (question,) = [d for d in scenario.questions_asked() if d.source == "Vein Ripper"]
    assert not question.affirmative_is_legal
    assert bolt.zone is Zone.GRAVEYARD


def test_a_mixed_mana_and_life_ward_is_one_payment():
    """Captain Howler, Sea Scourge: "Ward-{2}, Pay 2 life." Both parts or neither."""
    scenario, _howler, bolt = _bolt_at("Captain Howler, Sea Scourge")
    for mountain in scenario.untapped_sources("Mountain", "Mountain"):
        scenario.activate(mountain, color=Color.RED)
    scenario.will_take_the_may(True, username="alice", source="Captain Howler, Sea Scourge")

    scenario.resolve_top()

    assert scenario.player("alice").life == 18
    assert scenario.player("alice").mana_pool.total == 0
    assert bolt.zone is Zone.STACK


def test_a_mixed_ward_without_the_mana_cannot_be_paid_and_takes_no_life():
    scenario, _howler, bolt = _bolt_at("Captain Howler, Sea Scourge")

    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 20


def test_ward_sacrifice_three_permanents_is_paid_with_three_chosen_permanents():
    """Emrakul, the Exigent Doom: "Ward-Sacrifice three permanents." CR
    701.21a, with no type restriction at all - CR 110.1 already makes
    everything on the battlefield a permanent, so unlike Vein Ripper's
    creature-restricted single sacrifice above, "permanents" names no card
    type and a land pays exactly as well as a creature does."""
    scenario, _emrakul, bolt = _bolt_at(
        "Emrakul, the Exigent Doom",
        battlefield=["Grizzly Bears", "Llanowar Elves", "Forest"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(True, username="alice", source="Emrakul, the Exigent Doom")
    scenario.will_choose_cards(
        bears, elves, forest, username="alice", source="Emrakul, the Exigent Doom"
    )

    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert elves.zone is Zone.GRAVEYARD
    assert forest.zone is Zone.GRAVEYARD
    assert bolt.zone is Zone.STACK


def test_ward_sacrifice_three_permanents_with_only_two_cannot_be_paid():
    """CR 118.3: two permanents cannot pay a cost of three - built with a
    single Mountain rather than `_bolt_at`'s usual three, since "sacrifice
    three permanents" has no type restriction and the lands paying for the
    Bolt would themselves be enough to pay it otherwise."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain", "Llanowar Elves"])
        .player("bob", battlefield=["Emrakul, the Exigent Doom"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emrakul = scenario.creature("Emrakul, the Exigent Doom", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[emrakul])
    assert scenario.stack_names() == [
        "Lightning Bolt",
        "Emrakul, the Exigent Doom's triggered ability",
    ]

    scenario.resolve_top()

    (question,) = _asked(scenario, DecisionKind.MAY)
    assert question.source == "Emrakul, the Exigent Doom"
    assert not question.affirmative_is_legal
    assert bolt.zone is Zone.GRAVEYARD


def test_a_mana_ward_is_still_paid_from_floating_mana():
    """Archive Dragon's "Ward {2}", asked as the trigger resolves (CR 608.2g)."""
    scenario, _dragon, bolt = _bolt_at("Archive Dragon")
    for mountain in scenario.untapped_sources("Mountain", "Mountain"):
        scenario.activate(mountain, color=Color.RED)
    scenario.will_pay_the_mana_cost(True, username="alice")

    scenario.resolve_top()

    (question,) = _asked(scenario, DecisionKind.PAY_MANA)
    assert question.player == "alice"
    assert scenario.player("alice").mana_pool.total == 0
    assert bolt.zone is Zone.STACK
