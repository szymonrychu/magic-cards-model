"""Scenario: two independently targeted clauses in one instruction, bound to
the right target each (CR 601.2c, CR 608.2b).

Awaken the Inferno reads "Awaken the Inferno deals 6 damage to target
creature or planeswalker an opponent controls. Put a +1/+1 counter on up to
one target creature you control." `machines/effects.py`'s per-clause
fallback in `_parse_mixed_clauses` parsed each sentence into its own
callable, but every one of those callables reads the *whole*
`stack_object.targets` list through `Game.resolve_targets` - there was no
notion of "this clause's own target" at all. So the damage clause hit both
of CR 601.2c's targets (the opponent's creature it was meant for, and the
caster's own creature meant only for the counter), and the counter clause
raced it for the same list, putting a counter on the opponent's creature
too.

Fixed by `_parse_controller_split_target_clause_pair`, a new clause-pair
reader tried in `_parse_mixed_clauses`' merge chain alongside the existing
antecedent/rider pairs. It reads each clause's own controller restriction -
"an opponent controls" vs "you control" - the same way announcement already
told the two targets apart, and re-derives who controls each *resolved*
target at resolution (CR 608.2b) rather than trusting position in the list,
for the identical reason `_parse_pump_then_fight_clause_pair` already
gives: CR 608.2b can remove either target before resolution, so
`targets[0]`/`targets[1]` was never a safe way to tell them apart even when
the ordering happened to be right.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import _parse_mixed_clauses
from magic_cards_model.models import Zone

from .harness import Scenario


def test_awaken_the_infernos_two_clauses_are_read_as_one_bound_pair():
    clauses = _parse_mixed_clauses(
        "Awaken the Inferno deals 6 damage to target creature or planeswalker "
        "an opponent controls. Put a +1/+1 counter on up to one target "
        "creature you control.",
        for_spell=True,
    )
    assert clauses is not None
    assert len(clauses) == 1, "one bound pair, not two independent clauses"


def test_awaken_the_inferno_damages_only_the_opponents_creature():
    """The reported misread: the damage clause used to hit both targets."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Awaken the Inferno"],
            battlefield=["Mountain"] * 5 + ["Colossal Dreadmaw"],
        )
        .player("bob", battlefield=["Colossal Dreadmaw"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob_dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    alice_dreadmaw = scenario.creature("Colossal Dreadmaw", "alice")
    sources = scenario.untapped_sources(*["Mountain"] * 5)

    scenario.cast_and_resolve(
        "Awaken the Inferno", *sources, targets=[bob_dreadmaw, alice_dreadmaw]
    )

    assert bob_dreadmaw.zone is Zone.GRAVEYARD  # 6 toughness, took 6 damage
    assert alice_dreadmaw.damage == 0, "the caster's own creature took no damage"


def test_awaken_the_inferno_counters_only_the_casters_own_creature():
    """The other half of the reported misread: the counter clause used to
    race the damage clause for the same list and land on the opponent's
    creature too."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Awaken the Inferno"],
            battlefield=["Mountain"] * 5 + ["Colossal Dreadmaw"],
        )
        .player("bob", battlefield=["Colossal Dreadmaw"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob_dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    alice_dreadmaw = scenario.creature("Colossal Dreadmaw", "alice")
    sources = scenario.untapped_sources(*["Mountain"] * 5)

    scenario.cast_and_resolve(
        "Awaken the Inferno", *sources, targets=[bob_dreadmaw, alice_dreadmaw]
    )

    assert alice_dreadmaw.counters["+1/+1"] == 1
    assert bob_dreadmaw.counters["+1/+1"] == 0, "the opponent's creature got no counter"


def test_awaken_the_inferno_still_works_with_only_the_mandatory_target():
    """CR 115.6: "up to one" may choose none - the damage clause must still
    land on its own mandatory target with no second target announced at
    all."""
    scenario = (
        Scenario()
        .player("alice", hand=["Awaken the Inferno"], battlefield=["Mountain"] * 5)
        .player("bob", battlefield=["Colossal Dreadmaw"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob_dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    sources = scenario.untapped_sources(*["Mountain"] * 5)

    scenario.cast_and_resolve("Awaken the Inferno", *sources, targets=[bob_dreadmaw])

    assert bob_dreadmaw.zone is Zone.GRAVEYARD


# -- off-set proof: a different card, a different resolving verb (destroy, --
# -- not damage), and "you don't control" rather than "an opponent controls" -


def test_closing_statement_destroys_only_the_opponents_creature():
    """Closing Statement: "Destroy target creature or planeswalker you don't
    control. Put a +1/+1 counter on up to one target creature you control."
    The same two-clause shape as Awaken the Inferno, but with a different
    verb pair and `NOT_YOU` in place of `OPPONENT` - proving the fix reads
    controller-restriction *meaning*, not a hardcoded restriction value."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Closing Statement"],
            battlefield=["Swamp", "Plains"] * 3 + ["Colossal Dreadmaw"],
        )
        .player("bob", battlefield=["Colossal Dreadmaw"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob_dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    alice_dreadmaw = scenario.creature("Colossal Dreadmaw", "alice")
    sources = scenario.untapped_sources("Swamp", "Plains", "Swamp", "Plains", "Swamp")

    scenario.cast_and_resolve("Closing Statement", *sources, targets=[bob_dreadmaw, alice_dreadmaw])

    assert bob_dreadmaw.zone is Zone.GRAVEYARD
    assert alice_dreadmaw.zone is Zone.BATTLEFIELD, "the caster's own creature was not destroyed"
    assert alice_dreadmaw.counters["+1/+1"] == 1
    assert bob_dreadmaw.counters["+1/+1"] == 0


def test_closing_statement_cannot_bind_both_targets_to_its_own_creature():
    """Announcement itself still enforces each clause's own restriction -
    the binding fix is about resolution, not a relaxation of CR 601.2c."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Closing Statement"],
            battlefield=["Swamp", "Plains"] * 3 + ["Colossal Dreadmaw"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice_dreadmaw = scenario.creature("Colossal Dreadmaw", "alice")

    with pytest.raises(ValueError):
        scenario.cast(
            "Closing Statement", username="alice", targets=[alice_dreadmaw, alice_dreadmaw]
        )
