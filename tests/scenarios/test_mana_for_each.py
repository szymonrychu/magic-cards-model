"""A mana ability that adds one printed symbol "for each" thing a count
reads (CR 605.1a, CR 605.3b: read as it resolves) - `ManaAbility.
for_each_expression`. The Planets' "Add {G} for each creature you control"
is covered in `test_station.py`; this is the self-counter count."""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_everflowing_chalice_adds_one_colorless_per_charge_counter():
    """Everflowing Chalice: "{T}: Add {C} for each charge counter on this
    artifact." - two counters, two mana."""
    scenario = Scenario().player("alice", battlefield=["Everflowing Chalice"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chalice = scenario.find("Everflowing Chalice", Zone.BATTLEFIELD)
    scenario.game.add_counters(chalice, Counter.CHARGE, 2)

    scenario.activate(chalice, index=0)

    assert scenario.game.player("alice").mana_pool.total == 2


def test_everflowing_chalice_with_no_counters_adds_nothing():
    """CR 605.2: a mana ability is still one when the game state lets it
    produce no mana - zero counters, zero mana."""
    scenario = Scenario().player("alice", battlefield=["Everflowing Chalice"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chalice = scenario.find("Everflowing Chalice", Zone.BATTLEFIELD)

    scenario.activate(chalice, index=0)

    assert scenario.game.player("alice").mana_pool.total == 0
