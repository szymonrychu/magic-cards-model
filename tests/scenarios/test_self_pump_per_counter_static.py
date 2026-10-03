"""Scenario: a creature's own "+X/+Y for each `<kind>` counter on it" static.

- **Evolving Adaptive**, "This creature gets +1/+1 for each oil counter on
  it." (the shape is generic over the counter kind).
- Second printing, a different box and a different keyword around it:
  **Exuberant Fuseling**, "This creature gets +1/+0 for each oil counter on
  it." (power only).

CR 122.1 (counters on an object) and CR 613.4c (sublayer 7c: modifications
from non-characteristic-defining effects and counters): the count is re-read
on every board computation (CR 611.3a), so adding and removing counters moves
the stats immediately. Only the source's own counters of that one kind count.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def _scenario(name: str):
    scenario = Scenario().player("alice", battlefield=[name]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature(name, "alice")


def _pt(scenario, creature):
    chars = scenario.game.characteristics_of(creature)
    return chars.power, chars.toughness


def test_evolving_adaptive_scales_with_oil_counters_added_and_removed():
    scenario, adaptive = _scenario("Evolving Adaptive")
    base = (int(adaptive.card.power), int(adaptive.card.toughness))
    assert _pt(scenario, adaptive) == base

    adaptive.add_counters("oil", 1)
    assert _pt(scenario, adaptive) == (base[0] + 1, base[1] + 1)

    adaptive.add_counters("oil", 2)
    assert _pt(scenario, adaptive) == (base[0] + 3, base[1] + 3)

    adaptive.remove_counters("oil", 3)
    assert _pt(scenario, adaptive) == base


def test_evolving_adaptive_ignores_other_counter_kinds():
    scenario, adaptive = _scenario("Evolving Adaptive")
    base = (int(adaptive.card.power), int(adaptive.card.toughness))
    adaptive.add_counters("charge", 4)
    assert _pt(scenario, adaptive) == base


def test_exuberant_fuseling_power_only_per_oil_counter():
    scenario, fuseling = _scenario("Exuberant Fuseling")
    base = (int(fuseling.card.power), int(fuseling.card.toughness))
    fuseling.add_counters("oil", 2)
    assert _pt(scenario, fuseling) == (base[0] + 2, base[1])
    fuseling.remove_counters("oil", 2)
    assert _pt(scenario, fuseling) == base
