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
from magic_cards_model.models import CardState, Zone
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


def _cast_face_down(scenario, name: str, *mana_sources: CardState) -> CardState:
    """Cast `name` face down for {3} and resolve it (CR 702.37c), the same
    minimal helper `test_morph.py` uses."""
    casting = scenario.cast(name)
    casting.use_keyword("Morph")
    assert str(casting.total_cost.mana) == "{3}"
    payment = casting.begin_paying()
    scenario.pay_with(payment, *mana_sources)
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def test_maelstrom_pulse_leaves_a_second_nameless_face_down_permanent_alone():
    """CR 201.2a: "An object with no name doesn't have the same name as any
    other object, including another object with no name." Two face-down
    morph creatures (Brine Elemental, Aquamorph Entity) sit on the
    battlefield, each a nameless 2/2 (`CardState.face_down_characteristics`
    - see `test_morph.py`); Maelstrom Pulse targets one of them. Its own
    empty `name` skips `_same_name_battlefield_group`'s board scan
    entirely, so the group is the target alone - the second face-down
    permanent, whose name is equally empty, is never swept alongside it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Maelstrom Pulse", "Brine Elemental", "Aquamorph Entity"],
            battlefield=["Swamp", "Forest", "Forest"] + ["Island"] * 6,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    brine = _cast_face_down(
        scenario, "Brine Elemental", *scenario.untapped_sources(*["Island"] * 3)
    )
    aquamorph = _cast_face_down(
        scenario, "Aquamorph Entity", *scenario.untapped_sources(*["Island"] * 3)
    )
    assert brine.face_down and brine.name == ""
    assert aquamorph.face_down and aquamorph.name == ""

    scenario.cast_and_resolve(
        "Maelstrom Pulse",
        *scenario.untapped_sources("Swamp", "Forest", "Forest"),
        targets=[brine],
    )

    assert brine.zone is Zone.GRAVEYARD
    assert aquamorph.zone is Zone.BATTLEFIELD, (
        "a nameless permanent never shares a name with another nameless one - CR 201.2a"
    )


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
