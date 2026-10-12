"""Exile a card with time counters on it, then it gains suspend (EP-01 round 3, T4).

Two printed shapes of the same instruction, read as one CR 608.2c sentence:

- Epochrasite: "When this creature dies, exile it with three time counters on
  it and it gains suspend." - "it" is the dead creature's graveyard
  incarnation (CR 603.10a look-back, CR 400.7e).
- Taigam, Master Opportunist: "Flurry - Whenever you cast your second spell
  each turn, copy it, then exile the spell you cast with four time counters on
  it. If it doesn't have suspend, it gains suspend." - "the spell you cast" is
  the triggering spell, exiled off the stack after the copy is made.

Rules read with `mise run rules:find` in the session that wrote this:

- **CR 702.62a** - suspend's two exile-zone triggers: the owner's upkeep
  removes a time counter, and the last one lets its owner cast it without
  paying its mana cost; a creature cast this way gains haste.
- **CR 702.62b** - a card is suspended if it is in exile, has suspend, and
  has a time counter on it.
- **CR 400.7** - a card that leaves the graveyard in response is a new
  object; the dies trigger can no longer find it.
- **CR 707.10** - a copy of a spell is put on the stack; the original is a
  separate object.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import PlayedScenario, Scenario

LIBRARY = ["Island"] * 12


def _board(*, alice_battlefield, alice_hand=(), bob_battlefield=()) -> PlayedScenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=list(alice_battlefield),
            library=LIBRARY,
        )
        .player("bob", battlefield=list(bob_battlefield), library=LIBRARY)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _advance_to_upkeep_of(scenario: PlayedScenario, owner: str) -> None:
    scenario.advance()
    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == owner):
        _resolve_everything(scenario)
        scenario.advance()


def _resolve_everything(scenario: PlayedScenario) -> None:
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


# -- Epochrasite: dies trigger -------------------------------------------------


def test_epochrasite_dies_and_is_exiled_suspended_with_three_time_counters():
    scenario = _board(alice_battlefield=["Epochrasite"])
    epochrasite = scenario.creature("Epochrasite", "alice")

    scenario.game.destroy(epochrasite)
    _resolve_everything(scenario)

    assert epochrasite.zone is Zone.EXILE
    assert epochrasite.counter_count(Counter.TIME) == 3
    assert epochrasite.is_suspended, "CR 702.62b: in exile, has suspend, has a time counter"


def test_epochrasite_returns_free_with_haste_and_three_counters_after_three_upkeeps():
    """The free cast is not a cast from hand, so its own "enters with three
    +1/+1 counters on it if you didn't cast it from your hand" applies."""
    scenario = _board(alice_battlefield=["Epochrasite"])
    epochrasite = scenario.creature("Epochrasite", "alice")
    scenario.game.destroy(epochrasite)
    _resolve_everything(scenario)

    for remaining in (2, 1):
        _advance_to_upkeep_of(scenario, "alice")
        _resolve_everything(scenario)
        assert epochrasite.counter_count(Counter.TIME) == remaining
        assert epochrasite.zone is Zone.EXILE

    _advance_to_upkeep_of(scenario, "alice")
    _resolve_everything(scenario)

    assert epochrasite.zone is Zone.BATTLEFIELD
    assert epochrasite.counter_count(Counter.PLUS_ONE) == 3
    assert scenario.can_attack(epochrasite), "CR 702.62a: it has haste"


def test_epochrasite_exiled_from_the_graveyard_in_response_gets_no_counters():
    """CR 400.7: Tormod's Crypt exiles Alice's graveyard while the dies
    trigger waits; the exiled card is a new object the trigger cannot find."""
    scenario = _board(alice_battlefield=["Epochrasite"], bob_battlefield=["Tormod's Crypt"])
    epochrasite = scenario.creature("Epochrasite", "alice")

    scenario.game.destroy(epochrasite)
    scenario.game.put_triggers_on_stack()
    scenario.pass_priority("alice")
    crypt = scenario.find("Tormod's Crypt", Zone.BATTLEFIELD, "bob")
    scenario.activate(crypt, username="bob", targets=["alice"])
    scenario.resolve_top()
    scenario.resolve_top()

    assert epochrasite.zone is Zone.EXILE
    assert epochrasite.counter_count(Counter.TIME) == 0
    assert not epochrasite.is_suspended


# -- Taigam: the spell you cast ------------------------------------------------


def _taigam_board(hand):
    return _board(
        alice_battlefield=[
            "Taigam, Master Opportunist",
            "Island",
            "Island",
            "Mountain",
            "Mountain",
            "Mountain",
        ],
        alice_hand=hand,
    )


def test_taigam_copies_the_second_spell_and_suspends_the_original():
    scenario = _taigam_board(["Opt", "Opt"])
    library_before = len(scenario.player("alice").library)
    first = scenario.cast_onto_stack("Opt", username="alice", auto=True)
    _resolve_everything(scenario)
    assert first.zone is Zone.GRAVEYARD

    second = scenario.cast_onto_stack("Opt", username="alice", auto=True)
    _resolve_everything(scenario)

    assert second.zone is Zone.EXILE
    assert second.counter_count(Counter.TIME) == 4
    assert second.is_suspended
    assert len(scenario.player("alice").library) == library_before - 2, (
        "the first Opt and the copy each drew a card; the exiled original did not"
    )


def test_taigam_first_spell_is_not_copied_or_exiled():
    scenario = _taigam_board(["Opt"])
    first = scenario.cast_onto_stack("Opt", username="alice", auto=True)
    _resolve_everything(scenario)

    assert first.zone is Zone.GRAVEYARD
    assert first.counter_count(Counter.TIME) == 0


def test_taigam_a_spell_that_already_has_suspend_keeps_just_the_one():
    """Rift Bolt prints Suspend: "If it doesn't have suspend" is false, so
    nothing is granted; it is still suspended, with Taigam's four counters."""
    scenario = _taigam_board(["Opt", "Rift Bolt"])
    scenario.cast_onto_stack("Opt", username="alice", auto=True)
    _resolve_everything(scenario)

    bolt = scenario.cast_onto_stack("Rift Bolt", username="alice", auto=True, targets=["bob"])
    _resolve_everything(scenario)

    assert bolt.zone is Zone.EXILE
    assert bolt.counter_count(Counter.TIME) == 4
    assert bolt.is_suspended
    assert not any(line.lower() == "suspend" for line in bolt.granted_ability_texts)
    assert scenario.player("bob").life == 17, "the copy dealt 3"
