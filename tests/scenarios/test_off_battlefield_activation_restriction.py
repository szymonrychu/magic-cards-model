"""`KeywordActivation.why_not` used to ignore a printed "Activate only if
<condition>" restriction (CR 602.5b) entirely for any off-battlefield
ability - Grim Repriser's own "{B}{R}: Return this card from your graveyard
to the battlefield with a finality counter on it. Activate only if an
opponent has been dealt noncombat damage this turn." could be activated
from the graveyard whether or not that condition held, because the
restriction check `Game.why_cannot_activate`'s battlefield path already
runs (`Game._activation_condition_holds`, itself built on `Game.
condition_holds` - the FRA "trigger events and per-turn history" stream's
own reader for this exact clause) was never reached by `why_not` at all.

The new check is skipped for `rule == "CR 702.62b"` - Greater Gargadon's own
"Activate only if this card is suspended" - which `why_not` already checks
more precisely and earlier in its own sequence (`CardState.is_suspended`,
not the generic condition-string reader); `test_suspend_sacrifice_
activation.py` is the regression guard that this file must not disturb.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import off_battlefield_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_grim_repriser_refuses_activation_with_the_restriction_unmet():
    scenario = (
        Scenario()
        .player("alice", graveyard=["Grim Repriser"], battlefield=["Swamp", "Mountain"])
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grim = scenario.find("Grim Repriser", Zone.GRAVEYARD, username="alice")

    activation = off_battlefield_activation(scenario.game, grim, "alice")
    assert "restriction" in activation.why_not()

    try:
        activation.begin_paying()
    except ValueError as error:
        assert "restriction" in str(error)
    else:
        raise AssertionError("expected the unmet restriction to refuse activation")


def test_grim_repriser_allows_activation_once_the_restriction_is_met():
    scenario = (
        Scenario()
        .player("alice", graveyard=["Grim Repriser"], battlefield=["Swamp", "Mountain"])
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grim = scenario.find("Grim Repriser", Zone.GRAVEYARD, username="alice")
    scenario.game.deal_damage(scenario.player("bob"), 1)

    activation = off_battlefield_activation(scenario.game, grim, "alice")
    assert activation.why_not() is None
    assert activation.zone is Zone.GRAVEYARD
