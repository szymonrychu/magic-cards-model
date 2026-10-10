"""EP-01 round 1 integration: "target opponent/player loses the game" (CR 104.3e).

Mirrodin Besieged's Phyrexian mode: "At the beginning of your end step, draw a
card, then discard a card. Then if there are fifteen or more artifact cards in
your graveyard, target opponent loses the game." The conditional rider is read
as its own clause; the loss goes through `Game.player_loses_the_game`.

CR numbers (looked up with `mise run rules:find`): 104.3e, 603.2.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def _phyrexian_besieged(artifacts_in_graveyard):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mirrodin Besieged"],
            graveyard=["Sol Ring"] * artifacts_in_graveyard,
            library=["Forest"] * 5,
        )
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    scenario.will_choose("Phyrexian", source="Mirrodin Besieged")
    scenario.put_onto_battlefield("Mirrodin Besieged")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.choose_trigger_targets("Mirrodin Besieged", [scenario.player("bob")])
    while scenario.stack_names() or scenario.pending_triggers:
        scenario.game.put_triggers_on_stack()
        scenario.pass_until_resolved()
    return scenario


def test_fifteen_artifact_cards_in_the_graveyard_make_the_target_opponent_lose():
    scenario = _phyrexian_besieged(15)
    assert "bob" in scenario.game.losers


def test_fourteen_artifact_cards_do_not():
    scenario = _phyrexian_besieged(14)
    assert "bob" not in scenario.game.losers
    assert scenario.game.is_in_game("bob")
