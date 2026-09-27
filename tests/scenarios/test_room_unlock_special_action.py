"""Scenario: a Room's unlock cost (CR 709.5e / CR 116.2m) and its locked-door
static abilities (CR 709.5).

CR 709.5e: "A player who controls a permanent that has one or more locked
halves may pay the mana cost of a locked half of that permanent to give that
permanent the appropriate unlocked designation. This cost is referred to as
an 'unlock cost.' This is a special action (see rule 116). A player can take
this action any time they have priority and the stack is empty during a main
phase of their turn."

CR 709.5: "A shared type line on such an object represents two static
abilities that function on the battlefield. These are 'As long as this
permanent doesn't have the "left half unlocked" designation, it doesn't have
the name, mana cost, or rules text of this object's left half' and [the same
for the right half]."

CR 709.5h: a "When you unlock this door" trigger fires "when that permanent is
given the appropriate unlocked designation, regardless of whether it was given
that designation while entering the battlefield or after entering the
battlefield" - so the special action fires it the same way casting that half
does (`test_room_unlock_triggers.py`).

A Room put onto the battlefield by the harness was not cast, so it enters
with neither unlocked designation (CR 709.5d); tests that need a door already
unlocked give it through `Game.unlock_door` (CR 709.5f's own route) before
the scenario starts.

Two different Rooms prove the mechanic is read off the card's own halves and
their printed mana costs, never a name: Unholy Annex // Ritual Chamber
({2}{B} // {3}{B}{B}) and Central Elevator // Promising Stairs ({3}{U} //
{2}{U}).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import CardState, Zone
from magic_cards_model.models.action import ActionKind, Affordability

from .harness import Scenario

UNHOLY_ANNEX = "Unholy Annex // Ritual Chamber"
CENTRAL_ELEVATOR = "Central Elevator // Promising Stairs"


def _room(scenario: Scenario, card_name: str, username: str = "alice") -> CardState:
    return next(
        state
        for state in scenario.game.permanents_controlled_by(username)
        if state.card.name == card_name
    )


def _unlock_actions(scenario: Scenario, username: str = "alice"):
    return [
        action
        for action in legal_actions(scenario.game, username)
        if action.kind is ActionKind.UNLOCK_DOOR
    ]


# ---------------------------------------------------------------------------
# The special action itself.
# ---------------------------------------------------------------------------


def test_paying_ritual_chambers_unlock_cost_fires_its_unlock_trigger():
    scenario = (
        Scenario()
        .player("alice", battlefield=[UNHOLY_ANNEX, *["Swamp"] * 5])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    room = _room(scenario, UNHOLY_ANNEX)
    scenario.game.unlock_door(room, "Unholy Annex")

    assert scenario.game.why_cannot_unlock_door_as("alice", room, "Ritual Chamber") is None
    swamps = scenario.untapped_sources(*["Swamp"] * 5)
    scenario.unlock_door(room, "Ritual Chamber", *swamps)

    assert room.unlocked_doors == ("Unholy Annex", "Ritual Chamber")
    assert all(swamp.tapped for swamp in swamps), "the unlock cost {3}{B}{B} was paid"
    # CR 116.1: the special action itself never uses the stack; only the
    # trigger it caused goes there (CR 603.3).
    assert scenario.stack_names() == []
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{UNHOLY_ANNEX}'s triggered ability"]
    scenario.resolve_top()

    demons = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Demon Token"
    ]
    assert len(demons) == 1


def test_paying_central_elevators_unlock_cost_fires_its_search_trigger():
    """A second Room, the other half (its left door), a different cost
    ({3}{U}) and a different trigger effect."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=[UNHOLY_ANNEX, "Forest"],
            battlefield=[CENTRAL_ELEVATOR, *["Island"] * 4],
        )
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    room = _room(scenario, CENTRAL_ELEVATOR)
    scenario.game.unlock_door(room, "Promising Stairs")

    islands = scenario.untapped_sources(*["Island"] * 4)
    scenario.will_choose_cards(scenario.find(UNHOLY_ANNEX, Zone.LIBRARY, "alice"))
    scenario.unlock_door(room, "Central Elevator", *islands)

    assert room.unlocked_doors == ("Promising Stairs", "Central Elevator")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{CENTRAL_ELEVATOR}'s triggered ability"]
    scenario.resolve_top()
    assert scenario.find(UNHOLY_ANNEX, Zone.HAND, "alice").zone is Zone.HAND


def test_unlocking_a_fully_locked_room_gives_only_the_paid_door():
    """CR 709.5e unlocks one half per action - a Room that entered with
    neither designation (CR 709.5d) still has the other door locked."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[UNHOLY_ANNEX, *["Swamp"] * 3])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    room = _room(scenario, UNHOLY_ANNEX)
    assert room.unlocked_doors == ()

    scenario.unlock_door(room, "Unholy Annex", *scenario.untapped_sources(*["Swamp"] * 3))

    assert room.unlocked_doors == ("Unholy Annex",)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [], "Unholy Annex's own door has no unlock trigger"


def test_legal_actions_offers_each_locked_door_with_its_own_mana_cost():
    scenario = (
        Scenario()
        .player("alice", battlefield=[CENTRAL_ELEVATOR, *["Island"] * 4])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    room = _room(scenario, CENTRAL_ELEVATOR)

    offered = {action.door: action for action in _unlock_actions(scenario)}

    assert set(offered) == {"Central Elevator", "Promising Stairs"}
    assert offered["Central Elevator"].mana_cost == "{3}{U}"
    assert offered["Promising Stairs"].mana_cost == "{2}{U}"
    assert all(action.card_id == room.id for action in offered.values())
    assert all(action.rule == "CR 709.5e" for action in offered.values())
    assert all(action.affordable is Affordability.YES for action in offered.values())

    scenario.game.unlock_door(room, "Promising Stairs")
    assert [action.door for action in _unlock_actions(scenario)] == ["Central Elevator"]


def test_legal_actions_reports_an_unaffordable_unlock_cost_rather_than_dropping_it():
    """CR 118.6's split: the special action is still legal to attempt; only
    its affordability says it cannot be paid."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[UNHOLY_ANNEX, "Swamp", "Swamp"])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    room = _room(scenario, UNHOLY_ANNEX)
    scenario.game.unlock_door(room, "Unholy Annex")

    (action,) = _unlock_actions(scenario)

    assert action.door == "Ritual Chamber"
    assert action.affordable is Affordability.NO
    refusal = scenario.game.why_cannot_unlock_door_as("alice", room, "Ritual Chamber")
    assert refusal is not None
    assert "cannot pay {3}{B}{B}" in refusal
    assert "CR 118.3" in refusal


# ---------------------------------------------------------------------------
# Refusals, in the engine's own words.
# ---------------------------------------------------------------------------


def test_an_already_unlocked_door_refuses():
    scenario = (
        Scenario()
        .player("alice", battlefield=[UNHOLY_ANNEX, *["Swamp"] * 3])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    room = _room(scenario, UNHOLY_ANNEX)
    scenario.game.unlock_door(room, "Unholy Annex")

    refusal = scenario.game.why_cannot_unlock_door("alice", room, "Unholy Annex")

    assert refusal is not None
    assert "already unlocked" in refusal
    assert "CR 709.5e" in refusal


def test_a_permanent_you_do_not_control_refuses():
    scenario = (
        Scenario()
        .player("alice", battlefield=[*["Swamp"] * 5])
        .player("bob", battlefield=[UNHOLY_ANNEX])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    room = _room(scenario, UNHOLY_ANNEX, "bob")

    refusal = scenario.game.why_cannot_unlock_door("alice", room, "Ritual Chamber")

    assert refusal is not None
    assert "does not control" in refusal
    assert _unlock_actions(scenario) == []


def test_outside_a_main_phase_refuses():
    scenario = (
        Scenario()
        .player("alice", battlefield=[UNHOLY_ANNEX, *["Swamp"] * 5])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    room = _room(scenario, UNHOLY_ANNEX)

    refusal = scenario.game.why_cannot_unlock_door("alice", room, "Ritual Chamber")

    assert refusal is not None
    assert "main phase" in refusal
    assert _unlock_actions(scenario) == []


def test_on_an_opponents_turn_refuses():
    scenario = (
        Scenario()
        .player("alice", battlefield=[])
        .player("bob", battlefield=[UNHOLY_ANNEX, *["Swamp"] * 5])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    room = _room(scenario, UNHOLY_ANNEX, "bob")

    refusal = scenario.game.why_cannot_unlock_door("bob", room, "Ritual Chamber")

    assert refusal is not None
    assert "their own turn" in refusal
    assert _unlock_actions(scenario, "bob") == []


def test_with_a_nonempty_stack_refuses():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=[UNHOLY_ANNEX, "Mountain", *["Swamp"] * 5],
        )
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    room = _room(scenario, UNHOLY_ANNEX)
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast("Lightning Bolt", tapping=[mountain])

    refusal = scenario.game.why_cannot_unlock_door("alice", room, "Ritual Chamber")

    assert refusal is not None
    assert "stack" in refusal
    assert _unlock_actions(scenario) == []


def test_a_name_that_is_not_one_of_its_doors_refuses():
    scenario = (
        Scenario()
        .player("alice", battlefield=[UNHOLY_ANNEX, CENTRAL_ELEVATOR])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    room = _room(scenario, UNHOLY_ANNEX)

    refusal = scenario.game.why_cannot_unlock_door("alice", room, "Central Elevator")

    assert refusal is not None
    assert "not a door" in refusal


def test_a_permanent_that_is_not_a_room_refuses():
    scenario = (
        Scenario().player("alice", battlefield=["Swamp"]).player("bob", battlefield=[]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (swamp,) = scenario.untapped_sources("Swamp")

    refusal = scenario.game.why_cannot_unlock_door("alice", swamp, "Swamp")

    assert refusal is not None
    assert "locked half" in refusal


def test_begin_unlocking_raises_the_same_refusal_before_anything_is_spent():
    scenario = (
        Scenario()
        .player("alice", battlefield=[UNHOLY_ANNEX, *["Swamp"] * 5])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    room = _room(scenario, UNHOLY_ANNEX)

    try:
        scenario.game.begin_unlocking_door("alice", room, "Ritual Chamber")
    except ValueError as exc:
        assert "main phase" in str(exc)
    else:
        raise AssertionError("begin_unlocking_door took a refused special action")
    assert all(swamp.untapped for swamp in scenario.untapped_sources(*["Swamp"] * 5))
    assert room.unlocked_doors == ()


# ---------------------------------------------------------------------------
# CR 709.5's locked-door static abilities.
# ---------------------------------------------------------------------------


def test_a_room_with_one_door_unlocked_has_only_that_doors_name_and_mana_cost():
    scenario = (
        Scenario()
        .player("alice", battlefield=[UNHOLY_ANNEX, CENTRAL_ELEVATOR])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    annex = _room(scenario, UNHOLY_ANNEX)
    elevator = _room(scenario, CENTRAL_ELEVATOR)
    scenario.game.unlock_door(annex, "Ritual Chamber")
    scenario.game.unlock_door(elevator, "Promising Stairs")

    assert annex.name == "Ritual Chamber"
    assert annex.mana_cost == "{3}{B}{B}"
    assert "end step" not in annex.oracle_text
    assert elevator.name == "Promising Stairs"
    assert elevator.mana_cost == "{2}{U}"
    assert "search your library" not in elevator.oracle_text


def test_a_fully_locked_room_has_no_name_mana_cost_or_rules_text():
    """CR 709.5d's "enters with neither unlocked designation" - both of CR
    709.5's statics apply, so it keeps only its shared type line (CR 709.5a)."""
    scenario = (
        Scenario().player("alice", battlefield=[UNHOLY_ANNEX]).player("bob", battlefield=[]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    room = _room(scenario, UNHOLY_ANNEX)

    assert room.name == ""
    assert room.mana_cost is None
    assert room.oracle_text == ""
    assert "Room" in room.subtypes


def test_both_doors_unlocked_has_both_names():
    scenario = (
        Scenario().player("alice", battlefield=[UNHOLY_ANNEX]).player("bob", battlefield=[]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    room = _room(scenario, UNHOLY_ANNEX)
    scenario.game.unlock_door(room, "Ritual Chamber")
    scenario.game.unlock_door(room, "Unholy Annex")

    assert room.name == UNHOLY_ANNEX
    assert "end step" in room.oracle_text


def test_a_locked_unholy_annex_does_not_trigger_at_end_step():
    """Only Ritual Chamber unlocked: the end-step trigger printed on the
    locked Unholy Annex door is text this permanent does not have."""
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=[UNHOLY_ANNEX])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    room = _room(scenario, UNHOLY_ANNEX)
    scenario.game.unlock_door(room, "Ritual Chamber")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()  # the Demon from Ritual Chamber's own unlock

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_unlocking_unholy_annex_by_the_special_action_turns_its_end_step_trigger_on():
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=[UNHOLY_ANNEX, *["Swamp"] * 3])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    room = _room(scenario, UNHOLY_ANNEX)
    scenario.unlock_door(room, "Unholy Annex", *scenario.untapped_sources(*["Swamp"] * 3))

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Unholy Annex's triggered ability"]


def test_a_locked_central_elevator_door_does_not_trigger_when_the_other_door_unlocks():
    """Promising Stairs unlocking is not Central Elevator unlocking, and a
    fully locked Room's own "When you unlock this door" (Central Elevator)
    fires only for the door named."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[CENTRAL_ELEVATOR, *["Island"] * 3])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    room = _room(scenario, CENTRAL_ELEVATOR)

    scenario.unlock_door(room, "Promising Stairs", *scenario.untapped_sources(*["Island"] * 3))
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_a_fully_locked_room_shares_no_name_with_a_searched_room_card():
    """CR 201.2a: "An object with no name doesn't have the same name as any
    other object" - Central Elevator's "a Room card that doesn't have the
    same name as a Room you control" does not exclude Unholy Annex while the
    Unholy Annex alice controls is fully locked (CR 709.5)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[CENTRAL_ELEVATOR],
            library=[UNHOLY_ANNEX],
            battlefield=[UNHOLY_ANNEX, *["Island"] * 4],
        )
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_cards(scenario.find(UNHOLY_ANNEX, Zone.LIBRARY, "alice"))
    casting = scenario.cast("Central Elevator")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Island"] * 4))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert scenario.find(UNHOLY_ANNEX, Zone.HAND, "alice").zone is Zone.HAND
