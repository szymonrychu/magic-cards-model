"""Scenario: "can't be blocked by more than one creature" (CR 509.1b) stated
about a *group* the source's controller controls, rather than about the
source itself the way Charging Rhino's plain, self-referential printing
already is (`test_blocked_by_at_most_one.py`).

CR 509.1b: "The defending player checks each creature they control to see
whether it's affected by any restrictions (effects that say a creature can't
block, or that it can't block unless some condition is met) ... A restriction
may be created by an evasion ability (a static ability an attacking creature
has that restricts what can block it)." Looked up this session with `mise
run rules:find 509.1`.

Two shapes, both read by `combat_statics.group_blocked_by_at_most_one_
refusal`:

- **Rocksteady, Crash Courser**: "Rocksteady can't be blocked by more than
  one creature. Boars you control can't be blocked by more than one
  creature." - the first sentence is Rocksteady's own self-referential
  restriction (already read by `combat.blocked_by_at_most_one_refusal`,
  proved here too since fixing `combat.is_blocked_by_at_most_one_line`'s own
  comma-shortened-name classifier bug is part of this task); the second names
  a *type* group its controller controls.
- **Michelangelo, Mutant BFF**: "Each creature you control with a counter on
  it can't be blocked by more than one creature." - a *predicate* group
  (CR 122.1's "any counter, any kind"). Proved general on Flopsie, Bumi's
  Buddy's differently-worded "Each creature you control with power 4 or
  greater can't be blocked by more than one creature." (Modern/Pioneer/
  Standard legal, not a listed card, not in any deck list - verified with
  `resolve_cards`/Scryfall this session, 2026-09-27).
"""

import pytest

from magic_cards_model.machines import Step

from .harness import Scenario


def test_rocksteady_itself_cannot_be_blocked_by_two_creatures():
    """Rocksteady's own self-referential clause - the comma-shortened-name
    classifier fix does not change this runtime behaviour (it already
    worked), only what `scripts/sweep_pool.py` reports for it."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Rocksteady, Crash Courser"])
        .player("bob", battlefield=["Watchwolf", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    rocksteady = scenario.creature("Rocksteady, Crash Courser")
    wolf = scenario.creature("Watchwolf", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.attack_with(rocksteady)

    with pytest.raises(ValueError, match="can't be blocked by more than one creature"):
        scenario.block(rocksteady, wolf, giant)
    assert scenario.blockers() == []


def test_rocksteady_grants_its_boars_the_same_cap():
    """ "Boars you control can't be blocked by more than one creature." -
    Rocksteady itself is a Rhino Mutant, so a second Boar it controls is the
    one this clause protects, not Rocksteady."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Rocksteady, Crash Courser", "Boar"],
        )
        .player("bob", battlefield=["Watchwolf", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    boar = scenario.creature("Boar")
    wolf = scenario.creature("Watchwolf", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.attack_with(boar)

    with pytest.raises(ValueError, match="can't be blocked by more than one creature"):
        scenario.block(boar, wolf, giant)
    assert scenario.blockers() == []


def test_a_non_boar_rocksteady_controls_has_no_such_cap():
    """The group grant only reaches Boars - an ordinary Grizzly Bears
    Rocksteady also controls is blocked by two creatures without issue."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Rocksteady, Crash Courser", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Watchwolf", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears")
    wolf = scenario.creature("Watchwolf", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.attack_with(bears)
    scenario.block(bears, wolf, giant)

    assert scenario.blockers() == [wolf, giant]


def test_michelangelo_grants_the_cap_to_a_creature_with_any_counter():
    """ "Each creature you control with a counter on it can't be blocked by
    more than one creature." - CR 122.1's "any counter, any kind": a single
    +1/+1 counter is enough, and Michelangelo need not carry the counter
    itself."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Michelangelo, Mutant BFF", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Watchwolf", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears")
    bears.counters.add("+1/+1", 1)
    wolf = scenario.creature("Watchwolf", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.attack_with(bears)

    with pytest.raises(ValueError, match="can't be blocked by more than one creature"):
        scenario.block(bears, wolf, giant)
    assert scenario.blockers() == []


def test_michelangelo_grants_nothing_to_a_creature_with_no_counter():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Michelangelo, Mutant BFF", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Watchwolf", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears")
    wolf = scenario.creature("Watchwolf", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.attack_with(bears)
    scenario.block(bears, wolf, giant)

    assert scenario.blockers() == [wolf, giant]


def test_flopsie_proves_the_power_qualified_group_template():
    """A second, differently-worded printing of "Each creature you control
    with `<description>` can't be blocked by more than one creature." - a
    power comparison rather than a counter, proving the "each creature you
    control with `<description>`" reader generalises beyond the one
    predicate Michelangelo happens to print."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Flopsie, Bumi's Buddy", "Colossal Dreadmaw"],
        )
        .player("bob", battlefield=["Watchwolf", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    dreadmaw = scenario.creature("Colossal Dreadmaw")
    assert dreadmaw.power == 6
    wolf = scenario.creature("Watchwolf", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.attack_with(dreadmaw)

    with pytest.raises(ValueError, match="can't be blocked by more than one creature"):
        scenario.block(dreadmaw, wolf, giant)
    assert scenario.blockers() == []
