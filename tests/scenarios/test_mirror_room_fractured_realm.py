"""Scenario: both doors of Mirror Room // Fractured Realm.

Oracle text (the pool printing, Modern-legal):

- Mirror Room: "When you unlock this door, create a token that's a copy of
  target creature you control, except it's a Reflection in addition to its
  other creature types."
- Fractured Realm: "If a triggered ability of a permanent you control
  triggers, that ability triggers an additional time."

Every rule cited here was read whole with `scripts/cr.sh` in the session
that wrote this file:

- **CR 707.9b** - "Some copy effects modify a characteristic as part of the
  copying process. The final set of values for that characteristic becomes
  part of the copiable values of the copy."
- **CR 205.1b** - "in addition to its other types": every prior type,
  supertype and subtype is retained. "Its other creature types" is the same
  exception worded for the one kind of subtype it adds.
- **CR 603.2d** - "An ability may state that a triggered ability triggers
  additional times. ... determine how many times it should trigger, then
  that ability triggers that many times."
- **CR 709.5** - a locked half's rules text is not on the permanent, so a
  locked Fractured Realm doubles nothing; **CR 709.5h** - "When you unlock
  this door" triggers when the designation is given.

Fractured Realm's "whose" is the widest one printed - "a permanent you
control" - read by the same `_TYPED_ADDITIONAL_TRIGGER_RE` that reads Harmonic
Prodigy's "a Shaman or another Wizard you control" and Katara's "an Ally you
control", with "permanent" now a word every permanent has.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import AbilityKind
from magic_cards_model.models import Zone

from .harness import Scenario

ROOM = "Mirror Room // Fractured Realm"


def _room(scenario: Scenario, username: str = "alice"):
    return next(
        state
        for state in scenario.game.permanents_controlled_by(username)
        if state.card.name == ROOM
    )


def _triggers_from(scenario: Scenario, source) -> list:
    return [
        item
        for item in [*scenario.pending_triggers, *scenario.game.stack]
        if getattr(item, "kind", None) is AbilityKind.TRIGGERED
        and getattr(item, "source_id", None) == source.id
    ]


def _reflections(scenario: Scenario, username: str = "alice") -> list:
    return [
        state
        for state in scenario.game.permanents_controlled_by(username)
        if state.token and "Reflection" in scenario.game.characteristics_of(state).subtypes
    ]


# --------------------------------------------------------------------------
# Mirror Room: a token copy, except it's a Reflection
# --------------------------------------------------------------------------


def test_unlocking_mirror_room_copies_the_target_as_a_reflection_bear():
    scenario = (
        Scenario()
        .player("alice", battlefield=[ROOM, "Grizzly Bears", *["Island"] * 3])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    room = _room(scenario)
    bears = scenario.creature("Grizzly Bears")

    scenario.will_choose_targets(bears)
    scenario.unlock_door(room, "Mirror Room", *scenario.untapped_sources(*["Island"] * 3))
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    (token,) = _reflections(scenario)
    chars = scenario.game.characteristics_of(token)
    assert token.card.name == "Grizzly Bears"
    # CR 205.1b: Bear is kept, Reflection is added.
    assert {"Bear", "Reflection"} <= set(chars.subtypes)
    assert (chars.power, chars.toughness) == (2, 2)
    assert "Reflection" not in scenario.game.characteristics_of(bears).subtypes


# --------------------------------------------------------------------------
# Fractured Realm: every triggered ability of a permanent you control, twice
# --------------------------------------------------------------------------


def test_unlocked_fractured_realm_doubles_an_enters_trigger():
    scenario = (
        Scenario()
        .player("alice", hand=["Wall of Omens"], library=["Island"] * 5, battlefield=[ROOM])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.unlock_door(_room(scenario), "Fractured Realm")

    wall = scenario.put_onto_battlefield("Wall of Omens")

    triggered = _triggers_from(scenario, wall)
    assert len(triggered) == 2
    assert len({item.id for item in triggered}) == 2, "each its own object on the stack"


def test_locked_fractured_realm_doubles_nothing():
    """CR 709.5: with only Mirror Room unlocked, Fractured Realm's rules text
    is not on the permanent."""
    scenario = (
        Scenario()
        .player("alice", hand=["Wall of Omens"], library=["Island"] * 5, battlefield=[ROOM])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.unlock_door(_room(scenario), "Mirror Room")
    scenario.game.put_triggers_on_stack()
    scenario.game.stack.clear()

    wall = scenario.put_onto_battlefield("Wall of Omens")

    assert len(_triggers_from(scenario, wall)) == 1


def test_an_opponents_trigger_is_not_doubled():
    scenario = (
        Scenario()
        .player("alice", battlefield=[ROOM])
        .player("bob", hand=["Wall of Omens"], library=["Island"] * 5, battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.unlock_door(_room(scenario), "Fractured Realm")

    wall = scenario.put_onto_battlefield("Wall of Omens", username="bob")

    assert len(_triggers_from(scenario, wall)) == 1


def test_fractured_realm_doubles_its_own_rooms_mirror_room_trigger():
    """Both doors together: unlocking Mirror Room with Fractured Realm already
    unlocked triggers the door-unlock ability twice - two Reflections."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[ROOM, "Grizzly Bears", *["Island"] * 3])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    room = _room(scenario)
    scenario.game.unlock_door(room, "Fractured Realm")
    bears = scenario.creature("Grizzly Bears")

    scenario.will_choose_targets(bears)
    scenario.will_choose_targets(bears)
    scenario.unlock_door(room, "Mirror Room", *scenario.untapped_sources(*["Island"] * 3))
    scenario.game.put_triggers_on_stack()
    assert len(_triggers_from(scenario, room)) == 2
    scenario.resolve_top()
    scenario.resolve_top()

    assert len(_reflections(scenario)) == 2
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice") is not None
