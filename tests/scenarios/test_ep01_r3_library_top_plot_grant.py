"""Plot granted to the top card of the library (EP-01 round 3, T4).

Fblthp, Lost on the Range: "The top card of your library has plot. The plot
cost is equal to its mana cost." and "You may plot nonland cards from the top
of your library." Together they let the plot special action exile the top
card of its owner's library (CR 702.170f) for a plot cost equal to its mana
cost; a card plotted this way is cast from exile on a later turn without
paying its mana cost like any plotted card (CR 702.170d). No other printing
legal in Modern, Pioneer or Standard carries the grant (MEMORY.md,
2026-10-12).

Rules read with `mise run rules:find` in the session that wrote this:

- **CR 702.170a** - plot's special action: main phase, stack empty.
- **CR 702.170d** - a plotted card is cast from exile on a later turn without
  paying its mana cost, even if it has no plot ability in exile.
- **CR 702.170f** - an effect may let a card's plot ability function from a
  zone other than the hand; the card is exiled from that zone.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import MarkedExile
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from magic_cards_model.models.card_state import ExileMarker
from magic_cards_model.models.mana import ManaCost
from tests.scenarios.harness import PlayedScenario, Scenario

FBLTHP = "Fblthp, Lost on the Range"


def _board(*, library, fblthp: bool = True, step: Step = Step.PRECOMBAT_MAIN) -> PlayedScenario:
    battlefield = ["Mountain", "Mountain", "Island"]
    if fblthp:
        battlefield.insert(0, FBLTHP)
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=battlefield, library=list(library))
        .player("bob", library=["Island"] * 10)
        .build()
    )
    scenario.start_at(step)
    return scenario


def _top(scenario: PlayedScenario):
    return scenario.player("alice").library[0]


def _plot_top(scenario: PlayedScenario):
    top = _top(scenario)
    action = MarkedExile.plot(scenario.game, top, "alice")
    scenario.auto_pay(action.begin_paying(), username="alice")
    action.take()
    return top, action


def _alices_next_main(scenario: PlayedScenario) -> None:
    scenario.advance()
    while not (scenario.turn.active_player == "alice" and scenario.step is Step.PRECOMBAT_MAIN):
        scenario.advance()


def test_the_top_card_is_plotted_for_its_mana_cost():
    scenario = _board(library=["Lightning Bolt", "Island", "Island"])
    top, action = _plot_top(scenario)

    assert action.cost.mana == ManaCost.parse("{R}")
    assert top.zone is Zone.EXILE
    assert top.exile_annotation is not None
    assert top.exile_annotation.marker is ExileMarker.PLOTTED
    assert [card.name for card in scenario.player("alice").library] == ["Island", "Island"]


def test_the_plot_action_is_listed_for_the_top_card():
    scenario = _board(library=["Lightning Bolt", "Island"])
    top = _top(scenario)

    plots = [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.kind is ActionKind.PLOT and action.card_id == top.id
    ]
    assert len(plots) == 1
    assert plots[0].from_zone is Zone.LIBRARY


def test_a_land_on_top_cannot_be_plotted():
    scenario = _board(library=["Island", "Lightning Bolt"])

    with pytest.raises(ValueError, match="plot"):
        MarkedExile.plot(scenario.game, _top(scenario), "alice")


def test_a_card_below_the_top_cannot_be_plotted():
    scenario = _board(library=["Island", "Lightning Bolt"])
    second = scenario.player("alice").library[1]

    with pytest.raises(ValueError, match="plot"):
        MarkedExile.plot(scenario.game, second, "alice")


def test_without_the_grant_the_top_card_cannot_be_plotted():
    scenario = _board(library=["Lightning Bolt", "Island"], fblthp=False)

    with pytest.raises(ValueError, match="plot"):
        MarkedExile.plot(scenario.game, _top(scenario), "alice")


def test_plotting_from_the_library_is_refused_outside_a_main_phase():
    scenario = _board(library=["Lightning Bolt", "Island"], step=Step.UPKEEP)

    with pytest.raises(ValueError, match="main phase"):
        MarkedExile.plot(scenario.game, _top(scenario), "alice")


def test_the_plotted_card_is_cast_free_on_a_later_turn():
    scenario = _board(library=["Lightning Bolt", "Island", "Island", "Island", "Island"])
    _plot_top(scenario)
    _alices_next_main(scenario)

    casting = scenario.cast("Lightning Bolt", from_zone=Zone.EXILE)
    casting.use_keyword("Plot")
    casting.choose_targets(["bob"])
    assert casting.total_cost.mana == ManaCost()
    casting.begin_paying().pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.player("bob").life == 17
