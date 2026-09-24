"""A static self-pump counted per *graveyard*, not per card: "This creature
gets +2/+0 for each graveyard with seven or more cards in it." (Master's
Councillors).

CR 613.4c puts the bonus in sublayer 7c - it modifies the printed 1/3, it
never sets it. CR 404.1: each player has a graveyard of their own, so the
count is how many players' graveyards currently hold seven or more cards -
the controller's own and every opponent's, each counted at most once however
far past seven it is. A static ability's effect is not locked in (CR 611.3a),
so the bonus is re-read every time the board is computed (CR 613.5).

No other Modern/Pioneer/Standard printing carries the "for each graveyard
with N or more cards" count on a pump: The Master of Lake-town prints it on
a dies trigger beside a "Whenever a player loses life" trigger the engine
has no event for (see MEMORY.md), so the corner cases here are the proof.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

SEVEN = ["Forest"] * 7
SIX = ["Forest"] * 6


def test_no_graveyard_at_seven_leaves_the_printed_stats():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Master's Councillors"], graveyard=SIX)
        .player("bob", graveyard=SIX)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    councillors = scenario.creature("Master's Councillors", "alice")

    chars = scenario.game.computed_board().of(councillors)
    assert (chars.power, chars.toughness) == (1, 3)


def test_the_controllers_own_graveyard_counts():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Master's Councillors"], graveyard=SEVEN)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    councillors = scenario.creature("Master's Councillors", "alice")

    chars = scenario.game.computed_board().of(councillors)
    assert (chars.power, chars.toughness) == (3, 3)


def test_an_opponents_graveyard_counts_too():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Master's Councillors"])
        .player("bob", graveyard=SEVEN)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    councillors = scenario.creature("Master's Councillors", "alice")

    assert scenario.game.computed_board().of(councillors).power == 3


def test_each_qualifying_graveyard_adds_its_own_bonus():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Master's Councillors"], graveyard=SEVEN)
        .player("bob", graveyard=SEVEN)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    councillors = scenario.creature("Master's Councillors", "alice")

    chars = scenario.game.computed_board().of(councillors)
    assert (chars.power, chars.toughness) == (5, 3)


def test_a_graveyard_far_past_seven_still_counts_once():
    """ "for each graveyard" - fourteen cards in one graveyard is one
    graveyard, not two batches of seven."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Master's Councillors"], graveyard=SEVEN + SEVEN)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    councillors = scenario.creature("Master's Councillors", "alice")

    assert scenario.game.computed_board().of(councillors).power == 3


def test_the_bonus_is_not_locked_in_as_a_graveyard_shrinks():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Master's Councillors"])
        .player("bob", graveyard=SEVEN)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    councillors = scenario.creature("Master's Councillors", "alice")
    assert scenario.game.computed_board().of(councillors).power == 3

    card = scenario.player("bob").graveyard[0]
    scenario.game.exile_cards([card])
    assert card.zone is Zone.EXILE

    assert scenario.game.computed_board().of(councillors).power == 1


def test_its_own_mill_trigger_can_push_a_graveyard_over_the_line():
    """The Councillors' own second-card-drawn trigger mills three - a four-card
    graveyard becomes a seven-card one and the pump turns on."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Master's Councillors"], library=["Island"] * 5)
        .player("bob", graveyard=["Forest"] * 4, library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    councillors = scenario.creature("Master's Councillors", "alice")
    assert scenario.game.computed_board().of(councillors).power == 1

    scenario.draw(2, "alice")
    scenario.choose_trigger_targets("Master's Councillors", [scenario.player("bob")])
    scenario.pass_until_resolved()

    assert len(scenario.player("bob").graveyard) == 7
    assert scenario.game.computed_board().of(councillors).power == 3
