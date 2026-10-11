"""Scenario: Ezio Auditore da Firenze - "Whenever Ezio deals combat damage to
a player, you may pay {W}{U}{B}{R}{G} if that player has 10 or less life. When
you do, that player loses the game."

CR 510.2 (combat damage), CR 603.12 (the reflexive trigger made by paying),
CR 118.3 (the cost is paid in full or not at all), CR 104.3 (a player who
loses the game). The "if that player has 10 or less life" gate is read when
the trigger resolves: a player above ten is never offered the payment.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario

EZIO = "Ezio Auditore da Firenze"


def board(bob_life):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[EZIO, "Plains", "Island", "Swamp", "Mountain", "Forest"],
            library=["Island"] * 4,
        )
        .player("bob", library=["Island"] * 4)
        .build()
    )
    scenario.game.player("bob").life = bob_life
    for state in scenario.game.battlefield:
        state.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature(EZIO), defending="bob")
    scenario.advance()
    scenario.no_blocks()
    return scenario


def hit(scenario):
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


def test_paying_wubrg_against_a_player_at_ten_or_less_makes_them_lose():
    scenario = board(bob_life=10)
    scenario.will_take_the_may(True)
    scenario.will_pay_the_mana_cost(True)

    hit(scenario)

    assert not scenario.game.is_in_game("bob")


def test_declining_the_payment_does_nothing_more():
    scenario = board(bob_life=10)
    scenario.will_take_the_may(True)
    scenario.will_pay_the_mana_cost(False)

    hit(scenario)

    assert scenario.game.is_in_game("bob")
    assert scenario.game.player("bob").life == 10 - 3


def test_above_ten_life_there_is_no_offer_to_pay():
    scenario = board(bob_life=15)
    scenario.will_take_the_may(True)
    scenario.will_pay_the_mana_cost(True)

    hit(scenario)

    assert scenario.game.is_in_game("bob")
    assert all(not source.tapped for source in scenario.game.battlefield if source.name == "Plains")
