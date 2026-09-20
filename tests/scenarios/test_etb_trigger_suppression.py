"""Scenario: FRA S9's ETB trigger suppression - Torpor Orb's own shape,
which had no reader at all before this file despite being in the fixture
pool.

- **Karn, Argent Defender** (Reality Fracture), "Artifacts and creatures
  entering the battlefield don't cause abilities to trigger." - CR 603.2's
  automatic trigger check never fires for either card type's own arrival, for
  *any* watching ability, not only the entering permanent's. **Torpor Orb**
  (off-set, a real and well-known card with the identical mechanic for
  creatures alone, worded without "the battlefield" at all) proves the shape
  is read off the sentence rather than off Karn's name, and that the reader
  copes with the shorter real-world wording too.

The rule this rests on:

- **CR 603.2** - "Whenever a game event or game state matches a triggered
  ability's trigger event, that ability automatically triggers." Read the
  other way round: an event this static rules out never matches anything,
  so the check that would otherwise queue a triggered ability for CR 603.3's
  stack step simply never runs for it.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote it, and every card's text with
`resolve_cards` or straight off its fixture.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def test_karn_argent_defender_suppresses_a_creatures_etb_trigger():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Karn, Argent Defender"],
            hand=["Solemn Simulacrum"],
            library=["Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Solemn Simulacrum", "alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_karn_argent_defender_suppresses_an_artifacts_etb_trigger():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Karn, Argent Defender"], hand=["Prophetic Prism"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Prophetic Prism", "alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_a_creature_still_triggers_normally_without_the_suppression():
    """Control: with no suppression in play, Solemn Simulacrum's own ETB
    trigger fires exactly as it should."""
    scenario = (
        Scenario()
        .player("alice", hand=["Solemn Simulacrum"], library=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Solemn Simulacrum", "alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Solemn Simulacrum's triggered ability"]


def test_torpor_orb_suppresses_a_creatures_etb_trigger_off_set():
    """Off-set proof: a real, well-known card with the shorter Oracle
    wording ("Creatures entering don't cause abilities to trigger." - no
    "the battlefield") and no artifact half at all."""
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Torpor Orb"], hand=["Solemn Simulacrum"], library=["Mountain"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Solemn Simulacrum", "alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_torpor_orb_does_not_suppress_an_artifacts_etb_trigger():
    """Torpor Orb names only creatures - an artifact's own ETB trigger
    still fires."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Torpor Orb"], hand=["Prophetic Prism"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Prophetic Prism", "alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Prophetic Prism's triggered ability"]


def test_the_suppression_reaches_a_watching_permanent_not_only_the_entering_one():
    """Karn's own sentence names no controller and no "its own" - Soul
    Warden's "Whenever another creature enters, you gain 1 life." watches
    every arrival, not only its own, and is suppressed too."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Karn, Argent Defender", "Soul Warden"],
            hand=["Grizzly Bears"],
            life=20,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    life_before = alice.life

    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert alice.life == life_before
