"""Scenario: "If this is the second time this ability has resolved this turn"
(Captain Michael Burnham's landfall).

"Landfall - Whenever a land you control enters, Captain Burnham deals 1 damage
to each opponent. If this is the second time this ability has resolved this
turn, put a +1/+1 counter on Captain Burnham." The count is per ability and
per turn: the first and third resolutions put no counter, and a new turn
starts again at one. "Captain Burnham" is her CR 201.5c short name.

CR rules cited here were looked up with `mise run rules:find` in the writing
session: 201.5c, 207.2c (landfall is an ability word).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

BURNHAM = "Captain Michael Burnham"


def board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Mountain", "Mountain", "Mountain", "Mountain"],
            battlefield=[BURNHAM],
            library=["Island"] * 6,
        )
        .player("bob", library=["Island"] * 6)
    )


def land_enters(scenario):
    scenario.put_onto_battlefield("Mountain", "alice")
    scenario.pass_until_resolved()


def test_captain_michael_burnham_counts_her_landfall_resolutions():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    burnham = scenario.creature(BURNHAM, "alice")
    land_enters(scenario)
    assert scenario.player("bob").life == 19
    assert burnham.counter_count(Counter.PLUS_ONE) == 0
    land_enters(scenario)
    assert scenario.player("bob").life == 18
    assert burnham.counter_count(Counter.PLUS_ONE) == 1, "the second time"
    land_enters(scenario)
    assert scenario.player("bob").life == 17
    assert burnham.counter_count(Counter.PLUS_ONE) == 1, "not the third"


def test_the_count_starts_again_next_turn():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    burnham = scenario.creature(BURNHAM, "alice")
    land_enters(scenario)
    while scenario.turn.active_player != "bob":
        scenario.advance()
    land_enters(scenario)
    assert burnham.counter_count(Counter.PLUS_ONE) == 0, "first this turn again"
    land_enters(scenario)
    assert burnham.counter_count(Counter.PLUS_ONE) == 1
