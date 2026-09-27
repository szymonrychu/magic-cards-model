"""Enlist (CR 702.154a-d) off Guardian of New Benalia's own keyword and its
"Whenever this creature enlists a creature, scry 2." linked trigger (R0a T8).

Every CR number here was looked up with `mise run rules:find <number>` against
the 2026-09-25 Comprehensive Rules release in the session that wrote this
file.

- **CR 702.154a** - "Enlist means 'As this creature attacks, you may tap up
  to one untapped creature you control that you didn't choose to attack with
  and that either has haste or has been under your control continuously
  since this turn began. When you do, this creature gets +X/+0 until end of
  turn, where X is the tapped creature's power.'"
- **CR 702.154b** - the static half is CR 508.1g's optional attack cost; the
  triggered half is linked to it (CR 607.2h).
- **CR 702.154c** - "it isn't possible for a creature to enlist itself."
- **CR 508.1a** - the same haste-or-controlled-since-turn-began test that
  gates an ordinary attacker gates the tapped creature here too.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

GUARDIAN = "Guardian of New Benalia"


def test_enlisting_taps_the_chosen_creature_and_pumps_the_attacker():
    """CR 702.154a: the tapped creature's own power (2, Grizzly Bears)
    becomes the attacker's +X/+0 until end of turn."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[GUARDIAN, "Grizzly Bears"])
        .player("bob", battlefield=["Runeclaw Bear"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    guardian = scenario.find(GUARDIAN, Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    assert guardian.power == 2

    scenario.game.declare_attackers([(guardian, "bob")], enlist_choices={guardian.id: bears})

    assert guardian.power == 4
    assert bears.tapped is True


def test_enlists_trigger_fires_scry_two():
    """CR 702.154b's linked trigger: Guardian of New Benalia's own
    "Whenever this creature enlists a creature, scry 2." (CR 701.22a)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[GUARDIAN, "Grizzly Bears"],
            library=["Forest", "Mountain", "Island"],
        )
        .player("bob", battlefield=["Runeclaw Bear"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    guardian = scenario.find(GUARDIAN, Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")

    scenario.game.declare_attackers([(guardian, "bob")], enlist_choices={guardian.id: bears})
    scenario.game.put_triggers_on_stack()
    assert "Guardian of New Benalia's triggered ability" in scenario.stack_names()

    scenario.resolve_top()

    alice = scenario.player("alice")
    # Whatever the scry answered, the library still has all three cards -
    # scry never draws (CR 701.22a).
    assert len(alice.library) == 3


def test_enlist_is_optional_and_declines_cleanly():
    """CR 508.1g: "the active player chooses which, if any, they will pay" -
    attacking without enlisting is legal and leaves the enlist candidate
    untouched."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[GUARDIAN, "Grizzly Bears"])
        .player("bob", battlefield=["Runeclaw Bear"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    guardian = scenario.find(GUARDIAN, Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")

    scenario.game.declare_attackers([(guardian, "bob")])

    assert guardian.power == 2
    assert bears.tapped is False
    assert scenario.game.pending_triggers == []


def test_a_creature_cannot_enlist_itself():
    """CR 702.154c: "it isn't possible for a creature to enlist itself."""
    scenario = Scenario().player("alice", battlefield=[GUARDIAN]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    guardian = scenario.find(GUARDIAN, Zone.BATTLEFIELD, "alice")

    import pytest

    with pytest.raises(ValueError, match="itself"):
        scenario.game.declare_attackers([(guardian, "bob")], enlist_choices={guardian.id: guardian})


def test_a_tapped_creature_cannot_be_enlisted():
    """CR 702.154a's own "untapped creature" requirement."""
    scenario = (
        Scenario().player("alice", battlefield=[GUARDIAN, "Grizzly Bears"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    guardian = scenario.find(GUARDIAN, Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    bears.tap()

    import pytest

    with pytest.raises(ValueError):
        scenario.game.declare_attackers([(guardian, "bob")], enlist_choices={guardian.id: bears})


def test_a_creature_chosen_to_attack_cannot_also_be_enlisted():
    """CR 702.154a's own "that you didn't choose to attack with"."""
    scenario = (
        Scenario().player("alice", battlefield=[GUARDIAN, "Grizzly Bears"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    guardian = scenario.find(GUARDIAN, Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")

    import pytest

    with pytest.raises(ValueError):
        scenario.game.declare_attackers(
            [(guardian, "bob"), (bears, "bob")], enlist_choices={guardian.id: bears}
        )


def test_a_summoning_sick_creature_without_haste_cannot_be_enlisted():
    """CR 702.154a's own "has haste or has been under your control
    continuously since this turn began" - the identical CR 508.1a test."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[GUARDIAN, "Forest", "Forest"],
            hand=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    guardian = scenario.find(GUARDIAN, Zone.BATTLEFIELD, "alice")
    sources = scenario.untapped_sources("Forest", "Forest", username="alice")
    bears = scenario.cast_and_resolve("Grizzly Bears", *sources, username="alice")
    assert bears.summoning_sick is True

    import pytest

    with pytest.raises(ValueError):
        scenario.game.declare_attackers([(guardian, "bob")], enlist_choices={guardian.id: bears})


def test_argivian_cavalier_proves_enlist_generalises_past_guardian_of_new_benalia():
    """Proof of generality: Argivian Cavalier (legal Modern/Pioneer, not in
    `code/magic-cards-model-api/decks/*.txt`) carries plain Enlist with no
    "enlists a creature" trigger riding on it at all - proof the keyword
    itself, not Guardian of New Benalia's own linked trigger, is what
    generalises. Effie, Fast Learner - the planner's own named candidate -
    is not legal in Modern, Pioneer or Standard; this substitution is
    recorded as a dated line in `MEMORY.md`.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Argivian Cavalier", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cavalier = scenario.find("Argivian Cavalier", Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    assert cavalier.power == 2

    scenario.game.declare_attackers([(cavalier, "bob")], enlist_choices={cavalier.id: bears})

    assert cavalier.power == 4
    assert bears.tapped is True


def test_enlisted_creatures_pump_does_not_survive_end_of_turn():
    """CR 611.2a: "until end of turn" - cleanup removes it (CR 514.2)."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[GUARDIAN, "Grizzly Bears"])
        .player("bob", battlefield=["Runeclaw Bear"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    guardian = scenario.find(GUARDIAN, Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")

    scenario.game.declare_attackers([(guardian, "bob")], enlist_choices={guardian.id: bears})
    assert guardian.power == 4

    scenario.game.continuous_effects.end_the_turn(scenario.game)

    assert guardian.power == 2
