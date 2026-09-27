"""Maelstrom Pulse / Echoing Truth: "Destroy/Return target nonland permanent
and all other permanents with the same name as that permanent[ to their
owners' hands]." - CR 201.2a's "same name" grouping, read whole
(`machines/spell_texts_r0a.py`'s `parse_destroy_target_and_same_name_
permanents_clause`/`parse_return_target_and_same_name_permanents_to_hands_
clause`) because `split_effect_clauses`'s bare "and" would otherwise cut the
sentence into a verbless "all other permanents ..." fragment next to a
verbed "destroy/return target nonland permanent" one.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 201.2a** - "Two or more objects have the same name if they have at
  least one name in common, even if one or more of those objects have
  additional names. An object with no name doesn't have the same name as any
  other object, including another object with no name."
- **CR 608.2b** - a target rechecked for legality (and last known
  information) the instant it would be affected.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_maelstrom_pulse_destroys_every_same_named_permanent():
    """Two Grizzly Bears under bob's control, one under alice's - only bob's
    two share a name with the targeted one and are swept; alice's own bear
    (an independent object with an identical name) is likewise caught,
    proving the group is board-wide, not per-controller."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Maelstrom Pulse"],
            battlefield=["Swamp", "Forest", "Forest", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Grizzly Bears", "Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob_bear_1 = scenario.creature("Grizzly Bears", "bob")
    bob_bear_2 = [
        state
        for state in scenario.game.battlefield
        if state.name == "Grizzly Bears" and state.id != bob_bear_1.id and state.owner == "bob"
    ][0]
    alice_bear = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")

    scenario.cast_and_resolve(
        "Maelstrom Pulse",
        *scenario.untapped_sources("Swamp", "Forest", "Forest"),
        targets=[bob_bear_1],
    )

    assert bob_bear_1.zone is Zone.GRAVEYARD
    assert bob_bear_2.zone is Zone.GRAVEYARD
    assert alice_bear.zone is Zone.GRAVEYARD, "same name, different controller - still swept"
    assert angel.zone is Zone.BATTLEFIELD, "a different name is never part of the group"


def test_maelstrom_pulse_leaves_a_nameless_face_down_permanent_alone():
    """CR 201.2a: "An object with no name doesn't have the same name as any
    other object, including another object with no name" - a face-down
    permanent (Ashcloud Phoenix's own morph, unrelated to the targeted
    Grizzly Bears' printed name) sits on the battlefield throughout and is
    never touched."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Maelstrom Pulse"],
            battlefield=["Swamp", "Forest", "Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve(
        "Maelstrom Pulse",
        *scenario.untapped_sources("Swamp", "Forest", "Forest"),
        targets=[bears],
    )

    assert bears.zone is Zone.GRAVEYARD


def test_echoing_truth_returns_every_same_named_permanent_to_hand():
    """Echoing Truth (Modern-legal proof printing, not this task's own card,
    not in the deck pool): "Return target nonland permanent and all other
    permanents with the same name as that permanent to their owners'
    hands." - the same CR 201.2a grouping, `return` in place of `destroy`,
    proving `_same_name_battlefield_group` generalises across verbs."""
    scenario = (
        Scenario()
        .player("alice", hand=["Echoing Truth"], battlefield=["Island", "Island"])
        .player("bob", battlefield=["Grizzly Bears", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears_1 = scenario.creature("Grizzly Bears", "bob")
    bears_2 = [
        state
        for state in scenario.game.battlefield
        if state.name == "Grizzly Bears" and state.id != bears_1.id
    ][0]

    scenario.cast_and_resolve(
        "Echoing Truth", *scenario.untapped_sources("Island", "Island"), targets=[bears_1]
    )

    assert bears_1.zone is Zone.HAND
    assert bears_2.zone is Zone.HAND
    bob = next(player for player in scenario.game.players if player.username == "bob")
    assert bears_1 in bob.hand
    assert bears_2 in bob.hand
