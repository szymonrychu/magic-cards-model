"""'Draw a card at the beginning of the next turn's upkeep' on a spell.

Swift Maneuver ({1}{W}): "Prevent the next 2 damage that would be dealt to any
target this turn. Draw a card at the beginning of the next turn's upkeep."

CR 603.7a: a delayed triggered ability is created by a spell's resolution and
waits for its event; CR 603.7d: its controller is the controller of the spell
that created it. CR 513.2's rule for the end step holds for the upkeep too: if
the spell resolves during an upkeep, the delayed trigger waits for the *next*
turn's upkeep. CR 608.2b: a spell with every target illegal does not resolve,
so it creates no delayed trigger.

Proof printing on the same reader: Mystic Melting ({3}{G}): "Destroy target
artifact or enchantment. Draw a card at the beginning of the next turn's
upkeep."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def walk_to(scenario, step):
    while scenario.step is not step:
        scenario.advance()
        while not scenario.game.stack_is_empty and scenario.step is not step:
            scenario.resolve_top()


def _hand(scenario):
    return len(scenario.player("alice").hand)


def _swift(
    start=Step.PRECOMBAT_MAIN, bob_hand=(), bob_battlefield=(), alice_hand=(), alice_extra=()
):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Swift Maneuver", *alice_hand],
            library=["Forest"] * 4,
            battlefield=["Plains", "Plains", "Grizzly Bears", *alice_extra],
        )
        .player(
            "bob",
            hand=list(bob_hand),
            library=["Island"] * 4,
            battlefield=["Hill Giant", *bob_battlefield],
        )
        .build()
    )
    scenario.start_at(start)
    return scenario


def _cast_swift(scenario, target):
    scenario.cast_and_resolve(
        "Swift Maneuver", *scenario.untapped_sources("Plains", "Plains"), targets=[target]
    )


def _drain(scenario):
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def test_the_card_is_drawn_at_the_next_upkeep_and_not_before():
    scenario = _swift()
    before = _hand(scenario)
    _cast_swift(scenario, "alice")
    assert _hand(scenario) == before - 1, "Swift Maneuver left the hand; nothing drawn yet"
    walk_to(scenario, Step.UPKEEP)
    _drain(scenario)
    assert _hand(scenario) == before


def test_the_spells_controller_draws_even_in_the_opponents_upkeep():
    scenario = _swift()
    _cast_swift(scenario, "alice")
    bob_before = len(scenario.player("bob").hand)
    walk_to(scenario, Step.UPKEEP)
    _drain(scenario)
    assert scenario.turn.active_player == "bob"
    assert len(scenario.player("bob").hand) == bob_before
    assert len(scenario.player("alice").hand) == 1


def test_it_draws_only_once():
    scenario = _swift()
    _cast_swift(scenario, "alice")
    walk_to(scenario, Step.UPKEEP)
    _drain(scenario)
    after_first = _hand(scenario)
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
        _drain(scenario)
    walk_to(scenario, Step.UPKEEP)
    _drain(scenario)
    assert _hand(scenario) == after_first


def test_cast_during_an_upkeep_waits_for_the_next_turns_upkeep():
    """CR 513.2 by analogy: this upkeep has already begun."""
    scenario = _swift(start=Step.UPKEEP)
    before = _hand(scenario)
    _cast_swift(scenario, "alice")
    scenario.advance()
    _drain(scenario)
    assert _hand(scenario) == before - 1
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
        _drain(scenario)
    walk_to(scenario, Step.UPKEEP)
    _drain(scenario)
    assert _hand(scenario) == before


def test_the_prevention_half_still_works():
    scenario = _swift(alice_hand=["Lightning Bolt"], alice_extra=["Mountain"])
    _cast_swift(scenario, "alice")
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["alice"]
    )
    assert scenario.player("alice").life == 19, "3 damage minus the 2 prevented"


def test_a_fizzled_swift_maneuver_draws_nothing():
    """CR 608.2b: its only target is gone, so nothing happens - no prevention
    shield and no delayed draw."""
    scenario = _swift(bob_hand=["Unsummon"], bob_battlefield=["Island"])
    giant = scenario.creature("Hill Giant", "bob")
    before = _hand(scenario)
    spell = scenario.cast_onto_stack(
        "Swift Maneuver", *scenario.untapped_sources("Plains", "Plains"), targets=[giant]
    )
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Unsummon",
        *scenario.untapped_sources("Island", username="bob"),
        username="bob",
        targets=[giant],
    )
    scenario.resolve_top()
    assert spell.zone is Zone.GRAVEYARD
    walk_to(scenario, Step.UPKEEP)
    _drain(scenario)
    assert _hand(scenario) == before - 1


# -- Mystic Melting ------------------------------------------------------------------


def _melting():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mystic Melting"],
            library=["Forest"] * 4,
            battlefield=["Forest"] * 4,
        )
        .player("bob", library=["Island"] * 4, battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_mystic_melting_destroys_then_draws_next_upkeep():
    scenario = _melting()
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    before = _hand(scenario)
    scenario.cast_and_resolve(
        "Mystic Melting", *scenario.untapped_sources(*["Forest"] * 4), targets=[ring]
    )
    assert ring.zone is Zone.GRAVEYARD
    assert _hand(scenario) == before - 1
    walk_to(scenario, Step.UPKEEP)
    _drain(scenario)
    assert _hand(scenario) == before
