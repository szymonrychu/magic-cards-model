"""Gardenize: "Whenever a creature you control dies, put a charge counter
on this enchantment. At the beginning of your first main phase, add {G}
for each charge counter on this enchantment."

The first sentence is an ordinary dies-trigger placing an ordinary counter -
already generic. The second is CR 505.1's "first main phase" trigger already
read the same way `test_crumbling_vestige.py`'s Sanctum of Fruitful Harvest
is (`_walk_to`, copied rather than imported, for the same reason that file's
own docstring gives), adding mana scaled by a count this wave adds:
`machines/abilities.self_counter_mana_count`, the self-referential sibling
of `parse_mana_count`'s two board-scan scopes - CR 122.1's counters on the
ability's own source, not a count of matching permanents on the board at
all. Threaded through `machines/triggers.triggered_mana_count`'s new
`source` parameter, read by both the resolution path
(`machines/effects._parse_mana_adding_trigger`) and the payment-search path
(`machines/cost.py`'s own mana-trigger scan) alike.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 700.4** - "dies" means "is put into a graveyard from the battlefield."
- **CR 122.1** - counters, and a permanent's own charge counters among them.
- **CR 505.1** - "the first main phase (also known as the precombat main
  phase)."
- **CR 608.2h** - a "for each" count is determined only once, as the mana
  is added.
- **CR 605.1b / CR 605.5** - Gardenize's mana trigger fires from a step
  beginning, not from another mana ability's own activation or resolution,
  so CR 605.1b's criteria are not met and it is an ordinary triggered
  ability, using the stack, not CR 605.3b's mana-ability fast path.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario


def _walk_to(scenario, step: Step) -> None:
    """Advance turn-by-turn - never jump - until `step`, resolving anything
    that fires along the way. Copied from `test_crumbling_vestige.py`'s
    identical helper rather than imported, so this file about one mechanic
    does not reach into another's test module for its plumbing."""
    while scenario.step is not step:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


def test_a_dying_creature_you_control_adds_a_charge_counter():
    scenario = (
        Scenario().player("alice", battlefield=["Gardenize", "Grizzly Bears"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gardenize = scenario.find("Gardenize", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert gardenize.counter_count("charge") == 1


def test_an_opponents_dying_creature_adds_nothing():
    """ "a creature **you** control" (CR 109.5) - bob's own creature dying
    is not alice's own board event."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Gardenize"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gardenize = scenario.find("Gardenize", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack_is_empty
    assert gardenize.counter_count("charge") == 0


def test_the_first_main_phase_adds_green_mana_for_each_charge_counter():
    """Two charge counters already on Gardenize when the turn's own first
    main phase arrives add {G}{G}, not a fixed one mana."""
    scenario = Scenario().player("alice", battlefield=["Gardenize"]).player("bob").build()
    scenario.start_at(Step.UPKEEP)
    gardenize = scenario.find("Gardenize", Zone.BATTLEFIELD, "alice")
    scenario.game.add_counters(gardenize, "charge", 2)

    _walk_to(scenario, Step.PRECOMBAT_MAIN)

    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 2}


def test_no_charge_counters_add_no_mana():
    scenario = Scenario().player("alice", battlefield=["Gardenize"]).player("bob").build()
    scenario.start_at(Step.UPKEEP)

    _walk_to(scenario, Step.PRECOMBAT_MAIN)

    assert scenario.player("alice").mana_pool.floating == {}
