"""Scenario: "Whenever Adrestia attacks, if an Assassin crewed it this turn,
draw a card. Adrestia becomes an Assassin in addition to its other types until
end of turn."

Two readers meet here.

1. The intervening "if <a/an> <subtype> crewed it this turn" (CR 603.4) over the
   crew history `machines/conditions/history.py` already keeps: a creature
   "crews a Vehicle" when tapped to pay its crew cost (CR 702.122b), and the
   Vehicle is "crewed by" it (CR 702.122c). The creature's types are the ones
   it had when it was tapped, so an Assassin that has since left the
   battlefield still "crewed it".
2. The two-sentence effect. Both sentences belong to the one ability whose
   intervening "if" gated it (CR 603.4), so the "becomes an Assassin" half is
   as conditional as the draw. The type change is CR 205.1b's "in addition to
   its other types" and ends in the cleanup step (CR 514.2).

Rules read whole with `mise run rules:find` in the session that wrote this:
CR 603.4, CR 702.122b/c/e, CR 205.1b, CR 514.2, CR 121.1.

Generality: the subtype is read from the text, never named in the engine. No
other Modern/Pioneer/Standard printing names a subtype in this condition (the
other "crewed it this turn" cards - Getaway Car, Turtle Van, Subterranean
Schooner, Luxurious Locomotive, Golden Argosy - say "a creature that crewed
it", a different reader), so the last test drives the same condition reader
with other subtypes and a type word straight through `read_condition`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import crew_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(*creatures, hand_library=("Plains",) * 5):
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Adrestia", *creatures], library=list(hand_library))
        .player("bob", battlefield=["Island"], library=["Plains"] * 5)
        .build()
    )


def _crew(scenario, vehicle, *creatures):
    activation = crew_activation(scenario.game, vehicle, list(creatures), "alice")
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()
    activation.resolve()


def _hand(scenario):
    return len(scenario.player("alice").hand)


def _attack(scenario, adrestia):
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(adrestia)


def _subtypes(scenario, permanent):
    return scenario.game.characteristics_of(permanent).subtypes


def test_crewed_by_an_assassin_draws_and_becomes_an_assassin():
    scenario = _board("Hired Poisoner")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    adrestia = scenario.find("Adrestia", Zone.BATTLEFIELD)
    _crew(scenario, adrestia, scenario.creature("Hired Poisoner", "alice"))
    before = _hand(scenario)
    _attack(scenario, adrestia)
    assert scenario.stack_names() == ["Adrestia's triggered ability"]
    scenario.pass_until_resolved()
    assert _hand(scenario) == before + 1
    assert "Assassin" in _subtypes(scenario, adrestia)
    assert "Vehicle" in _subtypes(scenario, adrestia), "in addition to its other types"
    assert scenario.game.conditional_clause_notices == []


def test_crewed_by_a_non_assassin_does_not_trigger_at_all():
    scenario = _board("Grizzly Bears")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    adrestia = scenario.find("Adrestia", Zone.BATTLEFIELD)
    _crew(scenario, adrestia, scenario.creature("Grizzly Bears", "alice"))
    before = _hand(scenario)
    _attack(scenario, adrestia)
    assert scenario.stack_names() == []
    assert _hand(scenario) == before
    assert "Assassin" not in _subtypes(scenario, adrestia), "the type change is gated too"


def test_an_assassin_among_several_crewers_is_enough():
    scenario = _board("Hired Poisoner", "Grizzly Bears")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    adrestia = scenario.find("Adrestia", Zone.BATTLEFIELD)
    _crew(
        scenario,
        adrestia,
        scenario.creature("Hired Poisoner", "alice"),
        scenario.creature("Grizzly Bears", "alice"),
    )
    _attack(scenario, adrestia)
    assert scenario.stack_names() == ["Adrestia's triggered ability"]


def test_an_assassin_that_crewed_a_different_vehicle_does_not_count():
    """CR 702.122c: "crewed by" is Vehicle-specific."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Adrestia", "Getaway Car", "Hired Poisoner", "Grizzly Bears"],
            library=["Plains"] * 5,
        )
        .player("bob", battlefield=["Island"], library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    adrestia = scenario.find("Adrestia", Zone.BATTLEFIELD)
    car = scenario.find("Getaway Car", Zone.BATTLEFIELD)
    _crew(scenario, car, scenario.creature("Hired Poisoner", "alice"))
    _crew(scenario, adrestia, scenario.creature("Grizzly Bears", "alice"))
    _attack(scenario, adrestia)
    assert scenario.stack_names() == []


def test_an_assassin_that_crewed_in_an_earlier_turn_does_not_count():
    """CR 702.122c's "this turn": the ledger is per turn, so last turn's
    Assassin crew does not satisfy this turn's check once a bear crews."""
    scenario = _board("Hired Poisoner", "Grizzly Bears")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    adrestia = scenario.find("Adrestia", Zone.BATTLEFIELD)
    _crew(scenario, adrestia, scenario.creature("Hired Poisoner", "alice"))
    target_turn = scenario.turn.turns_taken + 2  # bob's turn, then alice's again
    while scenario.turn.turns_taken < target_turn:
        scenario.game.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _crew(scenario, adrestia, scenario.creature("Grizzly Bears", "alice"))
    _attack(scenario, adrestia)
    assert scenario.stack_names() == []


def test_the_assassin_leaving_before_resolution_still_crewed_it():
    """CR 603.4's recheck asks whether an Assassin crewed it this turn - a
    fact about the crew activation, not about the creature still being on the
    battlefield."""
    scenario = _board("Hired Poisoner")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    adrestia = scenario.find("Adrestia", Zone.BATTLEFIELD)
    poisoner = scenario.creature("Hired Poisoner", "alice")
    _crew(scenario, adrestia, poisoner)
    before = _hand(scenario)
    _attack(scenario, adrestia)
    scenario.game.destroy(poisoner)
    scenario.pass_until_resolved()
    assert _hand(scenario) == before + 1


def test_the_type_change_ends_in_the_cleanup_step():
    scenario = _board("Hired Poisoner")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    adrestia = scenario.find("Adrestia", Zone.BATTLEFIELD)
    _crew(scenario, adrestia, scenario.creature("Hired Poisoner", "alice"))
    _attack(scenario, adrestia)
    scenario.pass_until_resolved()
    assert "Assassin" in _subtypes(scenario, adrestia)
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.game.cleanup_step()
    assert "Assassin" not in _subtypes(scenario, adrestia)


def test_the_condition_reader_takes_any_subtype_not_just_assassin():
    from magic_cards_model.machines import conditions
    from magic_cards_model.machines.conditions import ConditionContext

    scenario = _board("Hired Poisoner")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    adrestia = scenario.find("Adrestia", Zone.BATTLEFIELD)
    _crew(scenario, adrestia, scenario.creature("Hired Poisoner", "alice"))

    def read(clause):
        context = ConditionContext(scenario.game, "alice", source=adrestia)
        return conditions.read_condition(context, clause)

    assert read("an Assassin crewed it this turn") is True
    assert read("a Human crewed it this turn") is True
    assert read("a Pirate crewed it this turn") is False
    assert read("an Elf crewed it this turn") is False
