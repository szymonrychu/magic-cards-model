""" "When you cast this spell, exile up to one target noncreature, nonland
permanent an opponent controls with mana value 4 or less. If you do, Thief of
Existence gains "When this creature leaves the battlefield, target opponent
draws a card."" - a cast trigger's exile with a self-grant rider.

CR 601.2i / CR 603.2: "When you cast this spell" triggers once the spell
becomes cast, so the ability goes on the stack above the spell and resolves
first (the ruling: "Thief of Existence's triggered ability will resolve
before Thief of Existence does.").

CR 113.10: "An effect that adds an ability will state that the object
"gains" or "has" that ability". CR 400.7a: "Effects from spells, activated
abilities, and triggered abilities that change the characteristics or
controller of a permanent spell on the stack continue to apply to the
permanent that spell becomes." - so the ability granted to the spell is had
by the creature it becomes. A spell that has already left the stack is a new
object (CR 400.7) and gains nothing.

CR 608.2b: an ability whose only target is illegal as it resolves does
nothing at all - no exile, and so no "If you do" (the ruling: "If the target
... is illegal as the ability tries to resolve, it won't resolve and none of
its effects will happen. Thief of Existence won't gain another ability.").
"up to one" lets the caster choose no target (CR 601.2c); nothing is exiled
then either.

CR 603.10a: the granted ability is a leaves-the-battlefield trigger, so it
looks back at the creature as it left - which had the ability.

Thief of Existence is the listed card and, verified with an oracle search of
every Modern/Pioneer/Standard legal card on 2026-09-24, the only printing of
this rider; the exile half is the same targeted clause every other cast
trigger's exile reads.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario

THIEF = "Thief of Existence"
GRANTED = "When this creature leaves the battlefield, target opponent draws a card."


def _board(bob_battlefield: list[str], alice_extra: list[str] | None = None):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[THIEF],
            battlefield=["Wastes", "Forest", "Forest", *(alice_extra or [])],
        )
        .player("bob", library=["Island", "Island"], battlefield=bob_battlefield)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_thief(scenario):
    return scenario.cast_onto_stack(THIEF, *scenario.untapped_sources("Wastes", "Forest", "Forest"))


def test_thief_is_fully_supported() -> None:
    statuses = {clause.status for clause in card_support(card(THIEF)).clauses}
    assert statuses == {"handled"}, card_support(card(THIEF)).clauses


def test_the_trigger_exiles_before_thief_resolves_and_thief_gains_the_ability() -> None:
    scenario = _board(["Sol Ring"])
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    scenario.choose_trigger_targets(THIEF, [ring])

    thief = _cast_thief(scenario)
    assert scenario.stack_names() == [THIEF, f"{THIEF}'s triggered ability"]
    scenario.resolve_top()

    assert ring.zone is Zone.EXILE
    assert thief.zone is Zone.STACK
    scenario.resolve_top()
    assert thief.zone is Zone.BATTLEFIELD
    assert GRANTED in thief.granted_ability_texts


def test_the_granted_ability_makes_an_opponent_draw_when_thief_leaves() -> None:
    """CR 400.7a carries the grant onto the permanent, and CR 603.10a's
    look-back finds it as Thief dies."""
    scenario = _board(["Sol Ring"])
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    scenario.choose_trigger_targets(THIEF, [ring])
    thief = _cast_thief(scenario)
    scenario.resolve_top()
    scenario.resolve_top()
    bob_hand = len(scenario.player("bob").hand)

    scenario.game.destroy(thief)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{THIEF}'s triggered ability"]
    scenario.resolve_top()

    assert len(scenario.player("bob").hand) == bob_hand + 1


def test_choosing_no_target_exiles_nothing_and_grants_nothing() -> None:
    """ "up to one": zero targets is a legal choice, and with nothing exiled
    there is no "If you do"."""
    scenario = _board(["Sol Ring"])
    scenario.choose_trigger_targets(THIEF, [])
    thief = _cast_thief(scenario)
    scenario.resolve_top()
    scenario.resolve_top()

    assert scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob").zone is Zone.BATTLEFIELD
    assert thief.granted_ability_texts == ()

    scenario.game.destroy(thief)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []


def test_an_illegal_target_on_resolution_grants_nothing() -> None:
    """CR 608.2b: the Sol Ring left before the trigger resolved, so the
    trigger does nothing - and Thief gains nothing."""
    scenario = _board(["Sol Ring"])
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    scenario.choose_trigger_targets(THIEF, [ring])
    thief = _cast_thief(scenario)

    scenario.game.destroy(ring)
    scenario.resolve_top()
    scenario.resolve_top()

    assert ring.zone is Zone.GRAVEYARD
    assert thief.zone is Zone.BATTLEFIELD
    assert thief.granted_ability_texts == ()


def test_thief_countered_in_response_still_exiles_but_gains_nothing() -> None:
    """The ruling: "If Thief of Existence is countered or otherwise leaves the
    stack in response to that triggered ability, the triggered ability will
    still resolve as normal." The card in the graveyard is a new object
    (CR 400.7) and gains nothing."""
    scenario = _board(["Sol Ring"])
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    scenario.choose_trigger_targets(THIEF, [ring])
    thief = _cast_thief(scenario)

    scenario.game.counter(thief)
    scenario.resolve_top()

    assert ring.zone is Zone.EXILE
    assert thief.zone is Zone.GRAVEYARD
    assert thief.granted_ability_texts == ()


def test_the_target_must_be_a_noncreature_nonland_opposing_permanent_of_mv_4_or_less() -> None:
    """CR 115.1 / CR 601.2c: every word of the target phrase is a
    restriction - an opponent's Sol Ring (mana value 1) and Damping Sphere
    (2) qualify; bob's creature, bob's land, alice's own Sol Ring and a
    mana value 7 planeswalker do not."""
    scenario = _board(
        ["Sol Ring", "Damping Sphere", "Grizzly Bears", "Island", "Ugin, Eye of the Storms"],
        alice_extra=["Sol Ring"],
    )
    game = scenario.game
    bob_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    alice_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")

    assert game.why_cannot_target_with_trigger(THIEF, [bob_ring]) is None
    sphere = scenario.find("Damping Sphere", Zone.BATTLEFIELD, "bob")
    assert game.why_cannot_target_with_trigger(THIEF, [sphere]) is None
    for illegal in (
        scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob"),
        scenario.find("Island", Zone.BATTLEFIELD, "bob"),
        scenario.find("Ugin, Eye of the Storms", Zone.BATTLEFIELD, "bob"),
        alice_ring,
    ):
        assert game.why_cannot_target_with_trigger(THIEF, [illegal]) is not None, illegal.name


def test_putting_thief_onto_the_battlefield_is_not_casting_it() -> None:
    """CR 603.2g: an event that did not happen triggers nothing - put onto
    the battlefield, Thief was never cast, so nothing is exiled."""
    scenario = _board(["Sol Ring"])
    thief = scenario.find(THIEF, Zone.HAND, "alice")

    scenario.game.put_onto_battlefield(thief, "alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert thief.granted_ability_texts == ()


def _thief_with_the_grant(scenario):
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    scenario.choose_trigger_targets(THIEF, [ring])
    thief = _cast_thief(scenario)
    scenario.resolve_top()
    scenario.resolve_top()
    assert GRANTED in thief.granted_ability_texts
    return thief


def test_a_bounced_thief_is_a_new_object_without_the_grant() -> None:
    """CR 400.7: the card returned to hand is a new object with no memory of
    its previous existence, so the grant does not come back with it - put
    back onto the battlefield (not cast), it has no leaves trigger. Its
    leaving the battlefield the first time still triggered (CR 603.10a)."""
    scenario = _board(["Sol Ring"])
    thief = _thief_with_the_grant(scenario)

    scenario.game.return_to_hand(thief)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{THIEF}'s triggered ability"]
    scenario.resolve_top()
    assert thief.zone is Zone.HAND
    assert thief.granted_ability_texts == ()

    scenario.game.put_onto_battlefield(thief, "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []
    scenario.game.destroy(thief)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []


def test_a_blinked_thief_returns_without_the_grant() -> None:
    """CR 400.7 on an exile-and-return: the permanent that comes back is a
    new object, and the grant was given to the old one."""
    scenario = _board(["Sol Ring"])
    thief = _thief_with_the_grant(scenario)

    scenario.game.exile_permanent(thief)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    scenario.game.put_onto_battlefield(thief, "alice")
    assert thief.zone is Zone.BATTLEFIELD
    assert thief.granted_ability_texts == ()

    scenario.game.destroy(thief)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []
