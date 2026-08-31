"""Scenario: "whenever [something] becomes the target of a spell or ability".

`machines/triggers.condition_matches` used to read only the self-referential
form of this condition - the one ward prints (CR 702.21a) and the one
Bonecrusher Giant prints - so Loki, God of Mischief's "Whenever a player or
permanent becomes the target of **an ability you control**, draw a card"
matched nothing and never fired. The matcher now reads the general form too,
and tells a targeting *spell* from a targeting *ability* by looking for the
targeting object among the abilities on the stack (CR 113.1c makes an ability
on the stack an object with an id of its own).

That is the matcher half. The **emit half is missing for abilities**:
`machines/casting.Casting._emit_becomes_target` raises the event for a spell's
targets, and `Game.activate_ability` (`models/game.py`, Task 1.5's file) - which
announces an activated ability's targets under CR 602.2b - raises nothing. So
Loki still draws no cards, and the strict `xfail` at the end says exactly that.

Card text verified with `resolve_cards`. CR numbers looked up with
`knowledge_search(type="rules")` in the session that wrote this file:

- **CR 115.1** - "Some spells and abilities require their controller to choose
  one or more targets for them ... These targets are declared as part of the
  process of putting the spell or ability on the stack."
- **CR 601.2c** - the targets of a spell are announced as it is cast.
- **CR 602.2b** - "The remainder of the process for activating an ability is
  identical to the process for casting a spell listed in rules 601.2b-i."
- **CR 702.21a** - ward, the self-referential form of the same condition.
- **CR 603.2h** - "Do this only once each turn", which Loki's own line prints.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.triggers import triggered_abilities_of
from tests.cards import card
from tests.scenarios.harness import Scenario


def loki_board(*extra: str) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            library=["Grizzly Bears", "Grizzly Bears"],
            battlefield=[
                "Loki, God of Mischief",
                "Grizzly Bears",
                "Mountain",
                "Mountain",
                *extra,
            ],
        )
        .player("bob")
    )


def test_lokis_condition_is_recognised_as_a_becomes_target_trigger():
    """The parse, stated as its own fact: the ability is a becomes-target
    trigger (CR 115.1's event), and CR 603.2h's once-each-turn instruction is
    read off the same line."""
    (loki,) = triggered_abilities_of(card("Loki, God of Mischief"))

    assert loki.event is TriggerEvent.BECOMES_TARGET
    assert loki.condition == "a player or permanent becomes the target of an ability you control"
    assert loki.once_per_turn is True


def test_a_spell_targeting_a_permanent_does_not_fire_loki():
    """The negative that keeps the widened matcher honest.

    Loki watches an *ability* (CR 113.1c's object on the stack), not a spell.
    Alice bolting her own Bears is a real CR 601.2c target announcement, and
    the engine does emit the event for it - the trigger still must not fire.
    """
    scenario = loki_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")[:1]

    scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=[bears])

    assert scenario.stack_names() == ["Lightning Bolt"]
    assert scenario.pending_triggers == []


def test_bonecrusher_giant_still_fires_on_a_spell_that_targets_it():
    """The regression guard for the self-referential form the matcher already
    read: "Whenever this creature becomes the target of a spell" (Bonecrusher
    Giant), which names a spell and gets one."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Bonecrusher Giant", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Bonecrusher Giant", "alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=[giant])

    assert scenario.stack_names() == [
        "Lightning Bolt",
        "Bonecrusher Giant's triggered ability",
    ]


def test_a_spell_targeting_a_permanent_does_not_fire_loki_for_the_opponent_either():
    """The other side of the same negative: Loki's "you control" is about who
    controls the *targeting* object, so nothing about an opponent's spell can
    make it fire either."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Loki, God of Mischief", "Grizzly Bears"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")

    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=[bears])

    assert scenario.pending_triggers == []


@pytest.mark.xfail(
    strict=True,
    reason="the matcher reads Loki's condition now, but nothing emits a BECOMES_TARGET event "
    "for an *ability's* targets: `Game.activate_ability` in models/game.py - Task 1.5's file - "
    "announces them under CR 602.2b and raises no event, and machines/casting.py's emitter only "
    "ever runs for a spell. So Loki sees no event and draws no card.",
)
def test_an_ability_that_targets_a_permanent_fires_loki():
    """The card as printed: an ability alice controls targets something, and
    Loki draws a card (once that turn, CR 603.2h).

    Undercity Sewers' "{2}{U}, {T}: Draw a card" targets nothing; the ability
    used here is Sewer-veillance Cam's own "you may tap or untap target
    creature", which is a *triggered* ability with a target - CR 115.1 does not
    care which kind of ability targeted, only that one did.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sewer-veillance Cam"],
            library=["Grizzly Bears"],
            battlefield=["Loki, God of Mischief", "Grizzly Bears", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (island,) = scenario.untapped_sources("Island", username="alice")

    scenario.cast_and_resolve("Sewer-veillance Cam", island)
    scenario.choose_trigger_targets("Sewer-veillance Cam", [bears])
    scenario.game.put_triggers_on_stack()

    assert "Loki, God of Mischief's triggered ability" in scenario.stack_names()
