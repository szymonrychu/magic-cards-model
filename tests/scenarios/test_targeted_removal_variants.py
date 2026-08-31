"""Scenario: three targeted-removal shapes that were silently doing nothing
on resolution, none of them fixed by a per-card table row.

**March of Otherworldly Light** - "Exile target artifact, creature, or
enchantment with mana value X or less." Its own preamble is *two* sentences
("As an additional cost ..., you may exile any number of white cards ...
This spell costs {2} less to cast for each card exiled this way."), and
`_ADDITIONAL_COST_LINE_RE` only ever stripped the first - the second,
unstripped, poisoned the clause split of the exile sentence after it, the
same class of bug fixed for Kicker's/Flashback's own printed lines
(`_PER_COUNT_COST_REDUCTION_LINE_RE`).

**Fumarole** - "Destroy target creature and target land." Two independent,
simultaneously-announced targets in one sentence, not two clauses:
`_CLAUSE_SEPARATOR`'s bare-"and" split cut it into "Destroy target creature"
and a bare "target land" fragment with no verb, which nothing read
(`_parse_destroy_two_targets_clause`, tried whole, ahead of the split).

**Craterous Stomp** - "... deals 3 damage to target creature an opponent
controls. Each other creature that player controls becomes a Coward ... and
gains \"This creature can't block Giants or Warriors.\"" Recognised now
(`_DAMAGE_THEN_GROUP_TYPE_ABILITY_GRANT_RE`), but still fails closed with an
`AnaphoricClauseNotice` rather than actually running: fixing it for real needs
two primitives this engine does not have anywhere else - a *group* continuous
type-and-ability grant fixed off an anaphoric referent embedded mid-clause,
and blocker-side "can't block `<creature type>`" enforcement in
`machines/combat.py` (which only reads a printed *attacker*-side "can't be
blocked by ..." restriction today). See `docs/engine-coverage.md`.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 118.8a** - additional costs, paid on the way to the stack, never part
  of what the spell does on resolution.
- **CR 701.13a** - "To exile a card, move it to the exile zone."
- **CR 701.8a** - "To destroy a permanent, move it from the battlefield to
  its owner's graveyard."
- **CR 608.2b** - a target checked again on resolution; an illegal one is
  simply skipped, the rest of the spell still happens.
- **CR 601.2c** - CR 115.6's multiple, independent targets on one spell, each
  announced and each rechecked on its own.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import AnaphoricClauseNotice
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# March of Otherworldly Light
# --------------------------------------------------------------------------


def test_march_of_otherworldly_light_exiles_a_creature_at_x():
    """X=1: Llanowar Elves (mana value 1) is a legal find; the cost is
    `{1}{W}`, not just `{W}` - CR 107.3a's X still has to be paid."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["March of Otherworldly Light"],
            battlefield=["Plains", "Plains"],
        )
        .player("bob", battlefield=["Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elves = scenario.creature("Llanowar Elves", "bob")

    casting = scenario.cast("March of Otherworldly Light")
    casting.x_value = 1
    casting.choose_targets([elves])
    assert str(casting.total_cost.mana) == "{1}{W}"
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains", "Plains"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert elves.zone is Zone.EXILE


def test_march_of_otherworldly_light_cannot_reach_a_costlier_permanent():
    """X=1 cannot legally target Grizzly Bears (mana value 2) - CR 601.2c
    refuses the announcement rather than silently exiling it anyway."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["March of Otherworldly Light"],
            battlefield=["Plains", "Plains"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("March of Otherworldly Light")
    casting.x_value = 1

    with pytest.raises(ValueError):
        casting.choose_targets([bears])


# --------------------------------------------------------------------------
# Fumarole
# --------------------------------------------------------------------------


def test_fumarole_destroys_both_the_creature_and_the_land():
    """Two targets, one spell, one additional cost (3 life) paid on the way
    to the stack rather than as part of resolving it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fumarole"],
            battlefield=["Swamp", "Mountain", "Forest", "Forest", "Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")

    casting = scenario.cast("Fumarole")
    casting.choose_targets([bears, forest])
    payment = casting.begin_paying()
    scenario.pay_with(
        payment, *scenario.untapped_sources("Swamp", "Mountain", "Forest", "Forest", "Forest")
    )
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert forest.zone is Zone.GRAVEYARD
    assert alice.life == 17


# --------------------------------------------------------------------------
# Craterous Stomp: recognised, but records a notice rather than half-running
# --------------------------------------------------------------------------


def test_craterous_stomp_fails_closed_with_a_notice_rather_than_silently():
    """Neither the damage nor the Coward conversion happens - CR 608.2c has
    no notion of running half an instruction - but the gap is now recorded
    (`AnaphoricClauseNotice`) instead of the card doing nothing with no
    trace at all.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Craterous Stomp"], battlefield=["Mountain", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears", "Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    elves = scenario.creature("Llanowar Elves", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.cast_and_resolve("Craterous Stomp", *sources, targets=[bears])

    assert bears.zone is Zone.BATTLEFIELD, "the whole paragraph failed closed, damage included"
    assert "Coward" not in elves.card.subtypes
    notices = scenario.game.anaphoric_clause_notices
    assert len(notices) == 1
    assert isinstance(notices[0], AnaphoricClauseNotice)
    assert notices[0].source_name == "Craterous Stomp"
