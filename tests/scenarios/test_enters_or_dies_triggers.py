"""Scenario: one printed condition that names two trigger events, enters and
dies (CR 603.6a, CR 700.4, 603.10a).

Apex Witchstalker: "When this creature enters or dies, you gain 2 life."
Aerid Konstrari: "When Aerid Konstrari enters or dies, create a Heartwood
token." `machines/abilities._trigger_event` reads the first event word it
recognises and stops, so both conditions parsed as an enters-the-battlefield
trigger alone and the death half was silently dropped - the same defect
`test_enters_or_leaves_triggers.py` already documents for "enters or leaves",
here for "enters or dies" instead.

The fix, `machines/triggers._expand_enters_or_dies`: the same split
`_expand_attacks_or_blocks`/`_expand_enters_or_attacks`/`_expand_enters_or_
leaves` already perform for their own compound conditions, generalised to
read the self half against CR 700.7's "this `<noun>`" *or* the source's own
CR 201.5/201.5c short/full name (`machines/abilities.self_reference_names`) -
Apex Witchstalker's "this creature" and Aerid Konstrari's own bare name are
the same shape, read the same way.

Card text verified with `resolve_cards`. CR numbers looked up with
`knowledge_search(type="rules")` in the session that wrote this file:

- **CR 603.1b** - "A triggered ability may have more than one trigger
  condition."
- **CR 603.6a** - enters-the-battlefield abilities "trigger when a permanent
  enters the battlefield".
- **CR 700.4** - "dies" means "is put into a graveyard from the battlefield".
"""

from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.triggers import triggered_abilities_of
from magic_cards_model.models.zone import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def test_the_one_printed_line_is_two_triggered_abilities_this_creature():
    """CR 603.1b, Apex Witchstalker's own "this creature" self-reference."""
    abilities = triggered_abilities_of(card("Apex Witchstalker"))

    assert [a.event for a in abilities] == [
        TriggerEvent.ENTERS_THE_BATTLEFIELD,
        TriggerEvent.DIES,
    ]
    assert all("gain 2 life" in a.effect for a in abilities)


def test_the_one_printed_line_is_two_triggered_abilities_own_name():
    """CR 603.1b, Aerid Konstrari's own bare-name self-reference (CR 201.5)."""
    abilities = triggered_abilities_of(card("Aerid Konstrari"))

    assert [a.event for a in abilities] == [
        TriggerEvent.ENTERS_THE_BATTLEFIELD,
        TriggerEvent.DIES,
    ]
    assert all("Heartwood token" in a.effect for a in abilities)


def test_apex_witchstalker_triggers_on_entry():
    """CR 603.6a's half, which already worked - the regression guard that
    splitting the line did not cost the entering trigger."""
    scenario = Scenario().player("alice", hand=["Apex Witchstalker"]).player("bob").build()

    scenario.put_onto_battlefield("Apex Witchstalker")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Apex Witchstalker's triggered ability"]


def test_apex_witchstalker_triggers_on_death():
    """CR 700.4/603.10a's half, which used to be dropped on the floor."""
    scenario = Scenario().player("alice", battlefield=["Apex Witchstalker"]).player("bob").build()
    witchstalker = scenario.creature("Apex Witchstalker", "alice")

    scenario.game.put_into_graveyard(witchstalker)
    scenario.game.put_triggers_on_stack()

    assert witchstalker.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == ["Apex Witchstalker's triggered ability"]


def test_aerid_konstrari_triggers_on_entry():
    """The off-set-from-"this creature" proof: Aerid Konstrari's own entry."""
    scenario = Scenario().player("alice", hand=["Aerid Konstrari"]).player("bob").build()

    scenario.put_onto_battlefield("Aerid Konstrari")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Aerid Konstrari's triggered ability"]


def test_aerid_konstrari_triggers_on_death():
    """The half CR 201.5's bare-name self-reference used to lose."""
    scenario = Scenario().player("alice", battlefield=["Aerid Konstrari"]).player("bob").build()
    konstrari = scenario.creature("Aerid Konstrari", "alice")

    scenario.game.put_into_graveyard(konstrari)
    scenario.game.put_triggers_on_stack()

    assert konstrari.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == ["Aerid Konstrari's triggered ability"]


def test_another_creatures_death_does_not_trigger_aerid_konstrari():
    """The negative: the condition is self-referential, so a *different*
    creature dying next to Aerid Konstrari is not his own death."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Aerid Konstrari", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.put_into_graveyard(bears)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
