"""Scenario: the stack, and a counterspell war on it.

The mechanic is CR 608 resolution order. The stack is last-in-first-out, so the
last counterspell cast is the first to resolve, and it protects the spell two
below it by countering the one in between.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def counter_war() -> Scenario:
    """Alice casts a creature, both players hold Counterspell.

    Alice has Forests for the Bears and two Islands for her own Counterspell.
    Bob has two Islands for his.
    """
    return (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears", "Counterspell"],
            battlefield=["Forest", "Forest", "Island", "Island"],
        )
        .player("bob", hand=["Counterspell"], battlefield=["Island", "Island"])
    )


def test_the_stack_resolves_last_in_first_out():
    scenario = counter_war().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    # 1. Alice casts Grizzly Bears.
    forests = scenario.untapped_sources("Forest", "Forest", username="alice")
    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="alice")

    # 2. Bob responds with Counterspell targeting the Bears.
    scenario.pass_priority("alice")
    bob_islands = scenario.untapped_sources("Island", "Island", username="bob")
    bob_counter = scenario.cast_onto_stack(
        "Counterspell", *bob_islands, username="bob", targets=[bears]
    )

    # 3. Alice counters Bob's Counterspell.
    scenario.pass_priority("bob")
    alice_islands = scenario.untapped_sources("Island", "Island", username="alice")
    alice_counter = scenario.cast_onto_stack(
        "Counterspell", *alice_islands, username="alice", targets=[bob_counter]
    )

    assert [state.name for state in scenario.game.stack] == [
        "Grizzly Bears",
        "Counterspell",
        "Counterspell",
    ]

    # Alice's Counterspell is on top, so it resolves first and counters Bob's.
    scenario.pass_priority("alice")
    scenario.pass_priority("bob")
    assert alice_counter.zone is Zone.GRAVEYARD
    assert bob_counter.zone is Zone.GRAVEYARD, "countered, so it never resolved"
    assert [state.name for state in scenario.game.stack] == ["Grizzly Bears"]

    # Nothing is left to stop the Bears.
    scenario.pass_priority("alice")
    scenario.pass_priority("bob")

    assert bears.zone is Zone.BATTLEFIELD
    assert "Grizzly Bears" in scenario.battlefield_names()


def test_an_uncontested_counterspell_kills_the_creature():
    """Without alice's answer, the Bears never reach the battlefield."""
    scenario = counter_war().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forests = scenario.untapped_sources("Forest", "Forest", username="alice")
    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="alice")

    scenario.pass_priority("alice")
    bob_islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Counterspell", *bob_islands, username="bob", targets=[bears])

    scenario.pass_priority("bob")
    scenario.pass_priority("alice")  # Counterspell resolves
    scenario.pass_priority("alice")
    scenario.pass_priority("bob")  # nothing left to resolve

    assert bears.zone is Zone.GRAVEYARD
    assert "Grizzly Bears" not in scenario.battlefield_names()


def test_a_countered_spell_goes_to_its_owners_graveyard():
    """Corner case: it is the caster's graveyard, not the countering player's."""
    scenario = counter_war().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forests = scenario.untapped_sources("Forest", "Forest", username="alice")
    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="alice")
    scenario.pass_priority("alice")
    bob_islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Counterspell", *bob_islands, username="bob", targets=[bears])
    scenario.pass_priority("bob")
    scenario.pass_priority("alice")

    assert [state.name for state in scenario.player("alice").graveyard] == ["Grizzly Bears"]
    assert "Grizzly Bears" not in [s.name for s in scenario.player("bob").graveyard]


def test_a_counterspell_whose_target_is_already_gone_does_nothing():
    """Corner case: countering a spell that was itself countered first."""
    scenario = counter_war().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forests = scenario.untapped_sources("Forest", "Forest", username="alice")
    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="alice")
    scenario.pass_priority("alice")
    bob_islands = scenario.untapped_sources("Island", "Island", username="bob")
    bob_counter = scenario.cast_onto_stack(
        "Counterspell", *bob_islands, username="bob", targets=[bears]
    )
    scenario.pass_priority("bob")
    alice_islands = scenario.untapped_sources("Island", "Island", username="alice")
    scenario.cast_onto_stack(
        "Counterspell", *alice_islands, username="alice", targets=[bob_counter]
    )

    # Alice's resolves and counters Bob's. Bob's never resolves, so the Bears live.
    scenario.pass_priority("alice")
    scenario.pass_priority("bob")
    scenario.pass_priority("alice")
    scenario.pass_priority("bob")

    assert bears.zone is Zone.BATTLEFIELD


def test_a_spell_with_no_legal_targets_left_does_not_resolve():
    """CR 608.2b: every target illegal means the spell does not resolve at all.

    The assertion has to be on something a resolving-but-finding-nothing spell
    would still do, or it proves nothing. Lightning Helix is the case that
    tells them apart: "deal 3 damage to any target *and you gain 3 life*". The
    life gain is untargeted, so a Helix that resolved would gain the life even
    with its damage target gone. A Helix that fizzled gains nothing.

    Bob answers by exiling his own creature (CR 701.13), which is what makes the
    target no longer in the zone it was targeted in.
    """
    scenario = (
        Scenario()
        .player("alice", life=15, hand=["Lightning Helix"], battlefield=["Mountain", "Plains"])
        .player(
            "bob",
            hand=["Swords to Plowshares"],
            battlefield=["Grizzly Bears", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", username="bob")

    alice_sources = scenario.untapped_sources("Mountain", "Plains", username="alice")
    helix = scenario.cast_onto_stack(
        "Lightning Helix", *alice_sources, username="alice", targets=[bears]
    )
    scenario.pass_priority("alice")

    (bob_plains,) = scenario.untapped_sources("Plains", username="bob")
    scenario.cast_onto_stack("Swords to Plowshares", bob_plains, username="bob", targets=[bears])
    scenario.pass_until_resolved()  # Swords resolves; the Bears are exiled

    assert bears.zone is Zone.EXILE
    assert scenario.game.spell_fizzles(helix), "the Helix has no legal target left"

    scenario.pass_until_resolved()  # the Helix is removed from the stack unresolved

    assert helix.zone is Zone.GRAVEYARD
    assert helix.id in scenario.game.fizzled
    assert scenario.player("alice").life == 15, "a spell that fizzles gains no life either"


def test_a_spell_with_one_legal_target_left_still_resolves():
    """CR 608.2b: only *all* targets being illegal stops a spell resolving.

    The counterpart to the case above: Helix keeps its single legal target, so
    it resolves normally and the untargeted half happens too.
    """
    scenario = (
        Scenario()
        .player("alice", life=15, hand=["Lightning Helix"], battlefield=["Mountain", "Plains"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", username="bob")

    sources = scenario.untapped_sources("Mountain", "Plains", username="alice")
    helix = scenario.cast_onto_stack("Lightning Helix", *sources, username="alice", targets=[bears])

    assert not scenario.game.spell_fizzles(helix)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD, "3 damage kills a 2/2 (CR 704.5g)"
    assert scenario.player("alice").life == 18
    assert helix.id not in scenario.game.fizzled


def test_a_spell_that_chose_no_targets_never_fizzles():
    """CR 608.2b applies only "if the spell or ability specifies targets".

    A Bolt cast with no target chosen is not a spell whose targets are all
    illegal - it has none - so it resolves, finds nothing, and goes to the
    graveyard the ordinary way.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    bolt = scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=["bob"])

    assert bolt.zone is Zone.GRAVEYARD
    assert bolt.id not in scenario.game.fizzled


def test_resolving_an_empty_stack_is_an_error():
    scenario = counter_war().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    with pytest.raises(ValueError, match="stack is empty"):
        scenario.resolve_top()
