"""Scenario: "[You may] put a card you own from outside the game into your
hand" - the unrevealed, any-card wish (CR 108.3b, CR 400.11b).

The reveal-a-quality wishes (Burning Wish, Karn's -2) were read; this plainer
shape was not, so North Wind Avatar's enters trigger failed closed with a
notice. Found by the behavioural sweep. Mastermind's Acquisition (not in any
deck) prints the same instruction as a spell mode and proves it generally.

Rules verified with `mise run rules:find`: CR 108.3b ("allow a player to take
cards they own from outside the game"), CR 400.11a (the sideboard is outside
the game), CR 400.11b, CR 603.4 ("if you cast it").
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(hand: str, lands: list[str]):
    scenario = (
        Scenario()
        .player("alice", hand=[hand], battlefield=lands, sideboard=["Lightning Bolt"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_north_wind_avatar_cast_puts_a_sideboard_card_into_hand():
    scenario = _board("North Wind Avatar", ["Island", "Island", "Mountain", "Wastes", "Wastes"])

    scenario.cast_and_resolve("North Wind Avatar", auto=True)
    assert "North Wind Avatar's triggered ability" in scenario.stack_names()
    scenario.pass_until_resolved()

    alice = scenario.player("alice")
    assert [card.name for card in alice.hand] == ["Lightning Bolt"]
    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_north_wind_avatar_put_onto_the_battlefield_does_not_trigger():
    scenario = _board("North Wind Avatar", [])

    scenario.put_onto_battlefield("North Wind Avatar")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_masterminds_acquisition_mode_puts_a_sideboard_card_into_hand():
    scenario = _board("Mastermind's Acquisition", ["Swamp", "Swamp", "Swamp", "Wastes"])
    casting = scenario.cast("Mastermind's Acquisition")
    casting.choose_modes([2])
    scenario.auto_pay(casting.begin_paying())
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    alice = scenario.player("alice")
    assert [card.name for card in alice.hand] == ["Lightning Bolt"]
    assert alice.cards_in(Zone.GRAVEYARD)[0].name == "Mastermind's Acquisition"
