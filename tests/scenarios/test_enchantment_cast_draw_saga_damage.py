"""Scenario: "Whenever you cast an enchantment spell, draw a card. If it's a Saga
spell, <source> deals 2 damage to each opponent." - a cast trigger whose second
sentence is conditioned on the spell that triggered it.

Printings (oracle text read from the pool this session):

- Dathon, His Heart Open (TRK): "Whenever you cast an enchantment spell, draw a
  card. If it's a Saga spell, Dathon deals 2 damage to each opponent."
- Glorious Anthem (a non-Saga enchantment), History of Benalia (a Saga, an
  enchantment), Savannah Lions (not an enchantment).

Rules, looked up with `mise run rules:find` this session:

- **CR 603.2 / CR 601.2i** - the trigger fires on casting, before the spell
  resolves, so the spell is on the stack when the condition is judged.
- **CR 608.2c** - the controller follows the instructions in order; "if it's a
  Saga spell" is checked as the ability resolves (the spell is still on the
  stack, CR 608.2).
- **CR 205.3i** - Saga is an enchantment subtype.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

DATHON = "Dathon, His Heart Open"


def _board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Forest"] * 5,
            hand=["Glorious Anthem", "History of Benalia", "Savannah Lions"],
            battlefield=[DATHON, "Plains", "Plains", "Plains", "Plains", "Plains"],
        )
        .player("bob", library=["Forest"] * 3)
        .build()
    )


def _cast_and_resolve_trigger(scenario, name, lands):
    """Cast `name`, then resolve only Dathon's trigger: the spell stays on the
    stack, which is where "If it's a Saga spell" looks at it (CR 608.2)."""
    scenario.cast_onto_stack(name, *scenario.untapped_sources(*(["Plains"] * lands)))
    scenario.resolve_top()


def test_a_saga_spell_draws_a_card_and_deals_two_damage_to_each_opponent():
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hand_before = len(scenario.player("alice").hand)

    _cast_and_resolve_trigger(scenario, "History of Benalia", 3)

    # The Saga left the hand (-1) and a card was drawn (+1).
    assert len(scenario.player("alice").hand) == hand_before
    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 20


def test_a_non_saga_enchantment_draws_and_deals_no_damage():
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hand_before = len(scenario.player("alice").hand)

    _cast_and_resolve_trigger(scenario, "Glorious Anthem", 3)

    assert len(scenario.player("alice").hand) == hand_before
    assert scenario.player("bob").life == 20


def test_a_creature_spell_does_not_trigger_it():
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hand_before = len(scenario.player("alice").hand)

    scenario.cast_onto_stack("Savannah Lions", *scenario.untapped_sources("Plains"))

    assert [state.name for state in scenario.game.stack] == ["Savannah Lions"]
    assert len(scenario.player("alice").hand) == hand_before - 1
    assert scenario.player("bob").life == 20


def test_the_damage_goes_to_every_opponent():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"] * 5,
            hand=["History of Benalia"],
            battlefield=[DATHON, "Plains", "Plains", "Plains"],
        )
        .player("bob", library=["Forest"] * 3)
        .player("carol", library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_and_resolve_trigger(scenario, "History of Benalia", 3)

    assert scenario.player("bob").life == 18
    assert scenario.player("carol").life == 18


def _holds(scenario, condition):
    """`condition` asked about the cast event the top trigger carries."""
    trigger = scenario.game.stack[-1]
    dathon = scenario.creature(DATHON, "alice")
    return scenario.game.condition_holds(
        "alice", condition, dathon, ability=trigger, event=trigger.event
    )


def test_the_spell_noun_is_read_off_the_spell_whatever_its_quality():
    """The reader is `it's a <quality> spell`, not Saga: other qualities and
    negations answer from the same cast event."""
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack(
        "Glorious Anthem", *scenario.untapped_sources("Plains", "Plains", "Plains")
    )

    assert _holds(scenario, "it's an enchantment spell") is True
    assert _holds(scenario, "it's a white spell") is True
    assert _holds(scenario, "it's a Saga spell") is False
    assert _holds(scenario, "it isn't a Saga spell") is True
    assert _holds(scenario, "it's a creature spell") is False


def test_a_permanent_that_is_a_saga_is_no_saga_spell():
    """CR 112.1: a Saga on the battlefield is not a spell, so the spell noun
    is false for it even though it is a Saga."""
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack(
        "History of Benalia", *scenario.untapped_sources("Plains", "Plains", "Plains")
    )
    assert _holds(scenario, "it's a Saga spell") is True
    scenario.resolve_top()  # Dathon's trigger
    scenario.resolve_top()  # the Saga resolves onto the battlefield
    saga = scenario.find("History of Benalia", Zone.BATTLEFIELD, "alice")

    assert saga.zone is Zone.BATTLEFIELD
    assert scenario.game.condition_holds("alice", "this permanent is a Saga", saga) is True
    assert scenario.game.condition_holds("alice", "this permanent is a Saga spell", saga) is False
