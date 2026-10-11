"""Scenario: Party Thrasher - "At the beginning of your first main phase, you
may discard a card. If you do, exile the top two cards of your library, then
choose one of them. You may play that card this turn."

CR 505.1 (the first main phase is the precombat one), CR 118.12 (the optional
discard and "if you do"), CR 608.2d (the choice among the two exiled cards),
CR 601.3 and CR 611.2a (the permission lasts this turn). The card not chosen
stays in exile with no permission.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import play_permissions_on
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(hand=("Island",)):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Party Thrasher", "Mountain"],
            hand=list(hand),
            library=["Lightning Bolt", "Grizzly Bears", "Forest", "Forest"],
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.UPKEEP)
    while scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()
    return scenario


def test_discarding_exiles_two_and_lets_me_play_the_chosen_one_this_turn():
    scenario = _board()
    scenario.will_take_the_may(True)
    bolt = scenario.find("Lightning Bolt", Zone.LIBRARY, "alice")
    scenario.will_discard(scenario.find("Island", Zone.HAND, "alice"))
    scenario.will_choose_cards(bolt)

    scenario.pass_until_resolved()

    alice = scenario.player("alice")
    assert [c.name for c in alice.graveyard] == ["Island"]
    assert {c.name for c in scenario.game.exile if c.owner == "alice"} == {
        "Lightning Bolt",
        "Grizzly Bears",
    }
    bears = scenario.find("Grizzly Bears", Zone.EXILE, "alice")
    assert play_permissions_on(scenario.game, bolt)
    assert not play_permissions_on(scenario.game, bears)
    life = scenario.player("bob").life
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    casting = scenario.cast("Lightning Bolt", "alice", Zone.EXILE, targets=["bob"])
    scenario.pay_with(casting.begin_paying(), mountain)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert scenario.player("bob").life == life - 3


def test_declining_the_discard_exiles_nothing():
    scenario = _board()
    scenario.will_take_the_may(False)

    scenario.pass_until_resolved()

    assert [c.name for c in scenario.game.exile if c.owner == "alice"] == []
    assert len(scenario.player("alice").library) == 4
