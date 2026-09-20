"""Scenario: a no-comma "of"-epithet legend's own short-name self-reference
(CR 201.5, 201.5c).

Kiora of Fire and Ashes: "When Kiora enters, create a 5/5 red Dragon creature
token with flying." Before this fix, `machines/triggers._self_referential`
read a condition's self-reference off `machines/abilities.self_reference_
names`'s predecessor, which only ever shortened a "`<Name>` **the**
`<Epithet>`" legend (Liliana the Repentant) down to its first word - never
"`<Name>` **of** `<Epithet>`". "Kiora enters" therefore read as naming no
particular object at all, the same as a plain "Whenever a creature enters"
would, so Kiora's own trigger fired on *every* creature entering under her
controller - including each Dragon token her own trigger had just created,
which re-triggered her, which created another Dragon, forever (CR 603.2c: an
ability triggers once per matching event, and each Dragon's own entry is a
genuine, distinct one).

The fix, `machines/abilities.self_reference_names`: "of" joins "the" as an
epithet-boundary word, so "Kiora" is read as Kiora of Fire and Ashes's own
CR 201.5c short form, the same way "Liliana" already was for Liliana the
Repentant. `_self_referential` then reads "Kiora enters" as self-referential,
and `condition_matches`'s ENTERS_THE_BATTLEFIELD branch narrows a
self-referential condition with no "another"/"other" wording to the source's
own entry alone (CR 603.6a) - never a different permanent's, Dragon tokens
included.

Card text verified with `resolve_cards`. CR numbers looked up with
`knowledge_search(type="rules")` in the session that wrote this file:

- **CR 201.5c** - "Text printed on some cards refers to that card by a
  shortened version of its name."
- **CR 603.6a** - enters-the-battlefield abilities trigger when a permanent
  enters the battlefield.
- **CR 603.2c** - "An ability triggers only once each time its trigger event
  occurs."
"""

from tests.scenarios.harness import Scenario


def test_kiora_triggers_once_on_her_own_entry():
    scenario = Scenario().player("alice", hand=["Kiora of Fire and Ashes"]).player("bob").build()

    scenario.put_onto_battlefield("Kiora of Fire and Ashes")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Kiora of Fire and Ashes's triggered ability"]


def test_kiora_does_not_trigger_on_a_different_creature_entering():
    """The condition names no "another"/"other" - only Kiora's own entry
    satisfies "When Kiora enters", the same way "When this creature enters"
    never fires for a different permanent."""
    scenario = (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], battlefield=["Kiora of Fire and Ashes"])
        .player("bob")
        .build()
    )

    scenario.put_onto_battlefield("Grizzly Bears")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_her_own_dragon_token_does_not_retrigger_her_no_infinite_loop():
    """The proof this fix set out to give: Kiora's trigger resolves, its own
    Dragon token enters as a real, distinct ENTERS_THE_BATTLEFIELD event
    (CR 603.6a) - and nothing re-triggers her from it."""
    scenario = Scenario().player("alice", hand=["Kiora of Fire and Ashes"]).player("bob").build()

    scenario.put_onto_battlefield("Kiora of Fire and Ashes")
    scenario.game.put_triggers_on_stack()
    (ability,) = scenario.game.abilities_on_stack
    scenario.resolve_top()

    dragons = [
        state for state in scenario.game.battlefield if state.token and "Dragon" in state.subtypes
    ]
    assert len(dragons) == 1

    # The Dragon's own entry has already run through `Game.emit` inside
    # `resolve_top` above (CR 603.3) - if Kiora's trigger fired again, it
    # would be sitting on the stack or waiting in `pending_triggers` now.
    scenario.game.put_triggers_on_stack()
    assert scenario.game.stack == []
    assert scenario.pending_triggers == []
