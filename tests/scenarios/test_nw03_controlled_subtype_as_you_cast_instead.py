"""'... instead if you controlled a <subtype> as you cast this spell'.

Steer Clear ({W}): "Steer Clear deals 2 damage to target attacking or
blocking creature. Steer Clear deals 4 damage to that creature instead if you
controlled a Mount as you cast this spell."

CR 601.2i: the spell becomes cast, and "as you cast this spell" fixes the
question at that moment - it is a fact recorded on the cast
(`CastRecord.controlled_subtypes_as_cast`), not a board check on resolution,
so a Mount that arrives afterwards does not count and one that leaves
afterwards does not un-count. CR 614.1a: "instead" replaces the base
instruction. CR 109.5: "you controlled" - the caster's own
permanents, never the opponent's.

Steer Clear is the only printing in Modern, Pioneer or Standard whose
"you controlled a <subtype> as you cast this spell" gates a replacement: Faerie
Fencing carries the clause on a continuous effect (a layers reader, not this
one), so the reader is also proven here with a second subtype.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(hand, lands, alice_battlefield=(), bob_battlefield=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=list(lands) + ["Serra Angel"] + list(alice_battlefield),
        )
        .player("bob", battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "alice")
    angel.summoning_sick = False
    scenario.advance()
    scenario.advance()
    scenario.attack_with(angel)
    return scenario, angel


def test_without_a_mount_it_deals_two():
    scenario, angel = _board(["Steer Clear"], ["Plains"])
    scenario.cast_and_resolve("Steer Clear", *scenario.untapped_sources("Plains"), targets=[angel])
    assert angel.zone is Zone.BATTLEFIELD
    assert angel.damage == 2


def test_a_mount_you_controlled_as_you_cast_makes_it_four():
    scenario, angel = _board(["Steer Clear"], ["Plains"], alice_battlefield=["Bulwark Ox"])
    scenario.cast_and_resolve("Steer Clear", *scenario.untapped_sources("Plains"), targets=[angel])
    assert angel.zone is Zone.GRAVEYARD  # 4 damage on a 4/4


def test_an_opponents_mount_does_not_count():
    scenario, angel = _board(["Steer Clear"], ["Plains"], bob_battlefield=["Bulwark Ox"])
    scenario.cast_and_resolve("Steer Clear", *scenario.untapped_sources("Plains"), targets=[angel])
    assert angel.damage == 2


def test_a_mount_that_leaves_before_resolution_still_counts():
    """CR 601.2i: the fact was fixed as the spell was cast."""
    scenario, angel = _board(["Steer Clear"], ["Plains"], alice_battlefield=["Bulwark Ox"])
    ox = scenario.find("Bulwark Ox", Zone.BATTLEFIELD, "alice")
    scenario.cast_onto_stack("Steer Clear", *scenario.untapped_sources("Plains"), targets=[angel])
    scenario.game.destroy(ox)
    assert ox.zone is Zone.GRAVEYARD
    scenario.resolve_top()
    assert angel.zone is Zone.GRAVEYARD


def test_a_mount_that_arrives_after_casting_does_not_count():
    scenario, angel = _board(["Steer Clear", "Bulwark Ox"], ["Plains"])
    scenario.cast_onto_stack("Steer Clear", *scenario.untapped_sources("Plains"), targets=[angel])
    scenario.put_onto_battlefield("Bulwark Ox", "alice", from_zone=Zone.HAND)
    scenario.resolve_top()
    assert angel.zone is Zone.BATTLEFIELD
    assert angel.damage == 2


# -- The same reader for another subtype ------------------------------------------


def test_the_reader_is_not_pinned_to_mounts():
    """A Faerie controlled as the spell was cast answers a "controlled a Faerie
    as you cast this spell" clause; one that arrives later does not."""
    clause = "you controlled a Faerie as you cast this spell"
    scenario, angel = _board(["Steer Clear"], ["Plains"], alice_battlefield=["Spellstutter Sprite"])
    spell = scenario.cast_onto_stack(
        "Steer Clear", *scenario.untapped_sources("Plains"), targets=[angel]
    )
    assert scenario.game.condition_holds("alice", clause, spell) is True
    assert (
        scenario.game.condition_holds(
            "alice", "you controlled a Mount as you cast this spell", spell
        )
        is False
    )

    scenario, angel = _board(["Steer Clear", "Spellstutter Sprite"], ["Plains"])
    spell = scenario.cast_onto_stack(
        "Steer Clear", *scenario.untapped_sources("Plains"), targets=[angel]
    )
    scenario.put_onto_battlefield("Spellstutter Sprite", "alice", from_zone=Zone.HAND)
    assert scenario.game.condition_holds("alice", clause, spell) is False
