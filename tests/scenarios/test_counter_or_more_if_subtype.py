"""'Put a +1/+1 counter on X. If X is a <subtype>, put N +1/+1 counters on it
instead.' - one counter, or more for a creature of the named subtype.

- **CR 614.1a** - "instead" makes the second sentence a replacement of the
  first placement, so the creature gets N counters, never 1 + N.
- **CR 301.5a** - "equipped creature" is the creature the Equipment is
  attached to.
- **CR 122.1** - counters on a permanent.

Blade of the Bloodchief is the pool card; Elder Cathar (off-pool: a target
rather than an equipped creature, "that creature", Human) proves the template.
Every CR number here was read with `mise run rules:find` in this session.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _resolve_stack(scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def _blade_board(wearer: str):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Blade of the Bloodchief", wearer, "Memnite"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    blade = scenario.find("Blade of the Bloodchief", Zone.BATTLEFIELD, "alice")
    creature = scenario.creature(wearer, "alice")
    blade.attach_to(creature)
    return scenario, creature


def test_blade_puts_one_counter_on_a_non_vampire():
    scenario, bears = _blade_board("Grizzly Bears")
    scenario.game.sacrifice(scenario.creature("Memnite", "alice"))
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)
    assert bears.counters[Counter.PLUS_ONE] == 1


def test_blade_puts_two_counters_on_a_vampire_instead():
    """Vampire Hexmage is a Vampire: two counters, not three (CR 614.1a)."""
    scenario, hexmage = _blade_board("Vampire Hexmage")
    scenario.game.sacrifice(scenario.creature("Memnite", "alice"))
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)
    assert hexmage.counters[Counter.PLUS_ONE] == 2


def test_an_unattached_blade_puts_nothing_anywhere():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Blade of the Bloodchief", "Grizzly Bears", "Memnite"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.sacrifice(scenario.creature("Memnite", "alice"))
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)
    assert bears.counters[Counter.PLUS_ONE] == 0


def _elder_cathar_dies(target: str):
    scenario = (
        Scenario().player("alice", battlefield=["Elder Cathar", target]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    creature = scenario.creature(target, "alice")
    scenario.choose_trigger_targets("Elder Cathar", [creature])
    scenario.game.sacrifice(scenario.creature("Elder Cathar", "alice"))
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)
    return creature


def test_elder_cathar_puts_two_counters_on_a_human():
    """Elder Cathar: "When this creature dies, put a +1/+1 counter on target
    creature you control. If that creature is a Human, put two +1/+1 counters
    on it instead." Youthful Knight is a Human."""
    assert _elder_cathar_dies("Youthful Knight").counters[Counter.PLUS_ONE] == 2


def test_elder_cathar_puts_one_counter_on_a_non_human():
    assert _elder_cathar_dies("Grizzly Bears").counters[Counter.PLUS_ONE] == 1
