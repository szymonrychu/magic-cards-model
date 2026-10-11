"""Scenario: Boom Scholar's exhaust ability - "Creatures and Vehicles you
control gain trample until end of turn. Put two +1/+1 counters on this
creature." (CR 702.177a: exhaust is an activated ability usable once).

The group is a card type joined to a subtype by "and" (CR 205.2a, CR 205.3g):
a creature or a Vehicle, whichever it is, fixed as the effect begins (CR
611.2c), and only the controller's own.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

SCHOLAR = "Boom Scholar"


def _board():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[SCHOLAR, "Grizzly Bears", "Smuggler's Copter", "Mind Stone"]
            + ["Mountain", "Forest", "Forest", "Forest", "Forest", "Forest"],
            library=["Island"] * 6,
        )
        .player("bob", battlefield=["Wind Drake"], library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_exhaust_grants_trample_to_creatures_and_vehicles_and_grows_the_scholar():
    scenario = _board()
    scholar = scenario.creature(SCHOLAR)
    bears = scenario.creature("Grizzly Bears")
    copter = scenario.creature("Smuggler's Copter")
    stone = scenario.creature("Mind Stone")
    drake = scenario.creature("Wind Drake", "bob")

    scenario.activate(scholar, index=0, username="alice", auto=True)
    scenario.resolve_top()

    game = scenario.game
    assert has_keyword(bears, "trample", game)
    assert has_keyword(copter, "trample", game)
    assert has_keyword(scholar, "trample", game)
    assert not has_keyword(stone, "trample", game)
    assert not has_keyword(drake, "trample", game)
    assert scholar.counter_count(Counter.PLUS_ONE) == 2


def test_exhaust_can_only_be_activated_once():
    scenario = _board()
    scholar = scenario.creature(SCHOLAR)
    scenario.activate(scholar, index=0, username="alice", auto=True)
    scenario.resolve_top()

    assert scenario.why_cannot_activate(scholar, 0, "alice") is not None
