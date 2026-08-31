"""Vizier of Remedies' -1/-1 counter reducer (CR 614.1a, 614.16, 118.1, 118.11).

Filed from a real-play bug report: with Vizier of Remedies on the battlefield,
activating Devoted Druid's "Put a -1/-1 counter on this creature: Untap this
creature." still put a full -1/-1 counter on the Druid. Vizier's replacement
effect should have reduced it.

Every CR number here was looked up with `knowledge_search(type="rules")` in
the session that wrote the file, and 614.16's operative clause was confirmed
against the full CR text (`knowledge_search` truncates its excerpts, see
`docs/mcp-tools.md`) downloaded from the `source_url` `knowledge_search(type=
"cr_versions")` names as current, checksum `4381ad1b...423f` verified against
the `2026-08-19` release:

- **CR 614.1a** - "Effects that use the word 'instead' are replacement
  effects." Vizier's own line ("...that many -1/-1 counters minus one are put
  on it instead.") is one.
- **CR 614.16** - "Some replacement effects apply 'if an effect would put one
  or more counters on a permanent.' These replacement effects apply if the
  effect of a resolving spell or ability ... puts a counter on a permanent,
  and they also apply if another replacement or prevention effect does so,
  *even if the original event being modified wasn't itself an effect*." That
  last clause is the answer to the bug report's root cause: a counter placed
  as an *activation cost* (CR 118.1's "action or payment", not the effect of
  a resolving spell or ability) is still a counter-being-put-on event Vizier
  watches.
- **CR 118.1** - "A cost is an action or payment necessary to take another
  action ... To pay a cost, a player carries out the instructions specified
  by the spell, ability, or effect that contains that cost." The instruction
  Devoted Druid's cost specifies is "put a -1/-1 counter on this creature" -
  an ordinary counter-placing instruction, not exempt from 614.16 just for
  living in a cost.
- **CR 118.11** - "The actions performed when paying a cost may be modified
  by effects. Even if they are ... the cost has still been paid." Devoted
  Druid's activation is legal and its ability goes on the stack exactly as
  normal; only how many counters land is different.
- **CR 704.5f** - a creature with 0 or less toughness is put into its owner's
  graveyard as a state-based action, judged against fully computed toughness.

`tests/scenarios/test_counters_as_a_cost.py` covers the same activated
ability *without* Vizier - two activations kill the Druid on the second
counter. This file is the Vizier-present line: Vizier's reduction takes each
placed counter down to zero, so the Druid can loop the ability indefinitely
without ever taking a real -1/-1 counter or losing toughness.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def board(**kwargs) -> Scenario:
    """One player, no library, ready to build (see `test_counters.board`)."""
    return Scenario().manual_turn_based_actions().player("alice", **kwargs)


def test_vizier_reduces_the_druids_own_cost_counter_to_nothing():
    """The reported bug, reproduced and fixed: with Vizier of Remedies on the
    battlefield, Devoted Druid's activation cost puts *no* -1/-1 counter on
    itself (one minus one is zero), and the Druid still untaps - the ability
    the cost paid for goes on the stack and resolves normally (CR 118.11).
    """
    scenario = board(battlefield=["Devoted Druid", "Vizier of Remedies"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    druid = scenario.creature("Devoted Druid")
    druid.tap()
    assert druid.counter_count(Counter.MINUS_ONE) == 0

    on_stack = scenario.activate(druid, index=1)

    assert on_stack is not None  # still goes on the stack, unlike a mana ability
    assert druid.counter_count(Counter.MINUS_ONE) == 0
    assert (druid.power, druid.toughness) == (0, 2)

    scenario.pass_until_resolved()

    assert not druid.tapped


def test_the_druid_loops_indefinitely_with_vizier_present():
    """Without Vizier, `test_counters_as_a_cost.py`'s
    `test_a_second_activation_pays_the_cost_that_kills_it` shows the Druid
    dead by its second activation's counter (CR 704.5f). With Vizier reducing
    every placed counter to zero, ten activations in a row leave the Druid
    with no -1/-1 counters and full toughness - the well-known infinite-mana
    loop this bug silently broke.
    """
    scenario = board(battlefield=["Devoted Druid", "Vizier of Remedies"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    druid = scenario.creature("Devoted Druid")

    for _ in range(10):
        druid.tap()
        scenario.activate(druid, index=1)
        scenario.pass_until_resolved()

    assert druid.counter_count(Counter.MINUS_ONE) == 0
    assert (druid.power, druid.toughness) == (0, 2)
    assert druid.zone is Zone.BATTLEFIELD
    assert not druid.tapped


def test_vizier_does_not_touch_an_opponents_creature():
    """Vizier's own text is "a creature *you* control" - an opponent's Devoted
    Druid still takes the counter in full, so this is a controller check, not
    a blanket effect.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Vizier of Remedies"])
        .player("bob", battlefield=["Devoted Druid"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    druid = scenario.creature("Devoted Druid", username="bob")
    druid.tap()
    scenario.pass_priority()  # alice passes; bob (non-active) now holds priority

    scenario.activate(druid, index=1)

    assert druid.counter_count(Counter.MINUS_ONE) == 1
    assert (druid.power, druid.toughness) == (-1, 1)


def test_a_second_activation_still_kills_the_druid_without_vizier():
    """Unchanged control: `test_counters_as_a_cost.py`'s own no-Vizier line
    keeps its result - two activations, no Vizier, and the second cost's
    counter takes the Druid to 0 toughness (CR 704.5f). Written again here,
    against this fix, so a future change to the cost-payment path cannot
    silently break the ordinary case while only being checked against Vizier.
    """
    scenario = board(battlefield=["Devoted Druid"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    druid = scenario.creature("Devoted Druid")

    scenario.activate(druid, index=1)
    assert druid.zone is Zone.BATTLEFIELD
    assert (druid.power, druid.toughness) == (-1, 1)

    scenario.activate(druid, index=1)

    assert druid.zone is Zone.GRAVEYARD


def test_vizier_also_reduces_a_resolving_effects_counter_not_only_a_cost():
    """The non-cost path: a -1/-1 counter a *resolving* spell or ability puts
    on a creature you control is reduced the same way, since `Game.
    add_counters` already routes every counter placement - cost or effect -
    through the same replacement machinery (CR 614.16's "the effect of a
    resolving spell or ability ... puts a counter on a permanent" half).
    Driven directly through `Game.add_counters` rather than a specific card,
    since the effect-side call site is exercised by many cards already and
    this file's point is Vizier's own reduction, not any one of them.
    """
    scenario = board(battlefield=["Vizier of Remedies", "Devoted Druid"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    druid = scenario.creature("Devoted Druid")
    assert druid.counter_count(Counter.MINUS_ONE) == 0

    scenario.game.add_counters(druid, Counter.MINUS_ONE, 3)

    # "That many minus one": three requested becomes two placed.
    assert druid.counter_count(Counter.MINUS_ONE) == 2


def test_vizier_reduces_a_single_counter_to_zero_not_below():
    """The boundary the report also asked about: when only one counter would
    be placed, "that many minus one" is zero, not negative - no counter lands
    at all, and nothing about the permanent changes. `Game.add_counters`
    already treats a non-positive amount as nothing to add (mirroring how it
    treats a doubler's amount before it is ever positive), so this is the
    same code path as the loop test above, isolated to the single-counter
    case the bug report specifically named.
    """
    scenario = board(battlefield=["Vizier of Remedies", "Devoted Druid"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    druid = scenario.creature("Devoted Druid")

    scenario.game.add_counters(druid, Counter.MINUS_ONE, 1)

    assert druid.counter_count(Counter.MINUS_ONE) == 0
    assert (druid.power, druid.toughness) == (0, 2)
