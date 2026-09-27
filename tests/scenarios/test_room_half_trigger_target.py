"""Scenario: a Room half whose only "target" is in its own triggered ability
is cast as a spell with no targets (CR 115.1, CR 601.2c, CR 709.3a).

CR 709.3a: "Only the chosen half is evaluated to see if it can be cast." A
Room half is an enchantment spell, and a permanent spell is targeted only
when it is an Aura (CR 115.1b) - CR 115.1a's "(If an activated or triggered
ability of an instant or sorcery uses the word target, that ability is
targeted, but the spell is not.)" holds all the more for a permanent spell.
The door-unlock trigger (CR 709.5h) chooses its own targets when it is put
on the stack (CR 603.3d), after the Room has entered with that half unlocked
(CR 709.5d).

The engine used to read the chosen half's text whole, so the half's
triggered "target creature ..." became a target the *spell* required: the
cast refused for "too few targets" with none announced, and for "takes no
targets" with one announced - the half could not be cast at all, and
`legal_actions` advertised a target slot on its cast row.

Oracle text verified against the printings pool (Modern-legal):
- Glassworks // Shattered Yard - "Glassworks: When you unlock this door, this
  Room deals 4 damage to target creature an opponent controls."
- Mirror Room // Fractured Realm (not in the api deck pool) - "Mirror Room:
  When you unlock this door, create a token that's a copy of target creature
  you control, except it's a Reflection in addition to its other creature
  types." A second Room, a different color and a different target
  restriction ("you control"): the fix reads the half's type, never a name.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind

from .harness import Scenario

GLASSWORKS = "Glassworks // Shattered Yard"
MIRROR_ROOM = "Mirror Room // Fractured Realm"


def _cast_half(scenario: Scenario, card: str, half: str, *sources) -> None:
    casting = scenario.cast(card)
    casting.cast_as_split_half(half)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)


def _cast_rows(scenario: Scenario, half: str):
    return [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.kind is ActionKind.CAST and action.spell_face == half
    ]


def test_glassworks_is_cast_without_targets_and_its_unlock_trigger_targets():
    scenario = (
        Scenario()
        .player("alice", hand=[GLASSWORKS], battlefield=["Mountain"] * 3)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rows = _cast_rows(scenario, "Glassworks")
    assert rows and all(row.target_slots == () for row in rows)

    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    _cast_half(scenario, GLASSWORKS, "Glassworks", *scenario.untapped_sources(*["Mountain"] * 3))
    scenario.will_choose_targets(bears)
    room = scenario.resolve_top()
    assert room.unlocked_doors == ("Glassworks",)

    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Glassworks's triggered ability"]
    scenario.resolve_top()
    assert bears not in scenario.game.battlefield


def test_mirror_room_is_cast_without_targets():
    scenario = (
        Scenario()
        .player("alice", hand=[MIRROR_ROOM], battlefield=["Island"] * 3 + ["Grizzly Bears"])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rows = _cast_rows(scenario, "Mirror Room")
    assert rows and all(row.target_slots == () for row in rows)

    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    _cast_half(scenario, MIRROR_ROOM, "Mirror Room", *scenario.untapped_sources(*["Island"] * 3))
    scenario.will_choose_targets(bears)
    room = scenario.resolve_top()
    assert room.unlocked_doors == ("Mirror Room",)

    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Mirror Room's triggered ability"]
