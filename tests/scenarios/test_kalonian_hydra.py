"""Kalonian Hydra's attack trigger (CR 701.10e): doubling +1/+1 counters on
*every* creature its controller controls, not only itself.

"Whenever this creature attacks, double the number of +1/+1 counters on each
creature you control." CR 701.10e (looked up with `knowledge_search(type=
"rules")` in this session): "To double the number of a kind of counters on a
player or permanent, give that player or permanent as many of those counters
as that player or permanent already has."

The bug class this file exists to catch: a doubling effect that only reads
the source's own counters, rather than every creature the controller
controls (CR 122.1a's counters, CR 613.5's "you control").
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    # A permanent already on a scenario's opening battlefield is under its
    # controller's control since the turn began (CR 302.6), so it can attack
    # with no haste needed - but it also never *entered* the battlefield
    # through `Game.put_onto_battlefield`, so CR 614.1c's "enters with four
    # +1/+1 counters" replacement never ran either. Each test adds the four
    # counters by hand instead, which is this file's business (doubling),
    # not `docs/engine-coverage.md`'s "enters with" replacement's.
    return Scenario().player("alice", battlefield=["Kalonian Hydra", "Grizzly Bears"]).player("bob")


def test_attacking_doubles_the_hydras_own_four_counters_to_eight():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hydra = scenario.creature("Kalonian Hydra", "alice")
    scenario.game.add_counters(hydra, "+1/+1", 4)

    scenario.attack_with(hydra)
    while scenario.game.stack:
        scenario.resolve_top()

    assert hydra.counters["+1/+1"] == 8
    assert (hydra.power, hydra.toughness) == (8, 8)


def test_it_also_doubles_counters_on_a_different_creature_you_control():
    """The corner case this file is for: Grizzly Bears never attacked and
    carries no counters of its own to begin with, but a +1/+1 counter placed
    on it before combat still doubles when the Hydra attacks - "each creature
    you control" is a group, not "this creature".
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hydra = scenario.creature("Kalonian Hydra", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(hydra, "+1/+1", 4)
    scenario.game.add_counters(bears, "+1/+1", 3)

    scenario.attack_with(hydra)
    while scenario.game.stack:
        scenario.resolve_top()

    assert hydra.counters["+1/+1"] == 8
    assert bears.counters["+1/+1"] == 6
    assert (bears.power, bears.toughness) == (8, 8)  # 2/2 base + 6 counters


def test_a_creature_with_no_counters_stays_at_zero():
    """CR 701.10e doubles zero into zero - a silent no-op, not an error."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hydra = scenario.creature("Kalonian Hydra", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.attack_with(hydra)
    while scenario.game.stack:
        scenario.resolve_top()

    assert bears.counters["+1/+1"] == 0
    assert (bears.power, bears.toughness) == (2, 2)


def test_an_opponents_creature_with_counters_is_not_doubled():
    """ "Each creature you control" is scoped by controller, not merely
    "every creature on the battlefield" - bob's own Grizzly Bears keeps its
    counter when alice's Hydra attacks.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Kalonian Hydra"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hydra = scenario.creature("Kalonian Hydra", "alice")
    bobs_bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.add_counters(hydra, "+1/+1", 4)
    scenario.game.add_counters(bobs_bears, "+1/+1", 2)

    scenario.attack_with(hydra)
    while scenario.game.stack:
        scenario.resolve_top()

    assert hydra.counters["+1/+1"] == 8
    assert bobs_bears.counters["+1/+1"] == 2
