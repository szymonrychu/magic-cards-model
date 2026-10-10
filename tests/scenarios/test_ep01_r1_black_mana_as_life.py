"""CR 107.4f / 118.7f-style Phyrexian payment from a static ability:

    K'rrik, Son of Yawgmoth - For each {B} in a cost, you may pay 2 life
    rather than pay that mana.

Every {B} in a cost its controller pays - a spell's or an activated ability's -
becomes payable with 2 life, as a Phyrexian {B/P} symbol is (CR 107.4f). The
cost itself is unchanged (CR 118.9c-style: only the way it is paid), so the
spell's mana value stays what it printed.
"""

from magic_cards_model.machines import Step, payability
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario


def _main(**players) -> Scenario:
    builder = Scenario().manual_turn_based_actions()
    for username, kwargs in players.items():
        builder = builder.player(username, **kwargs)
    scenario = builder.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _can_pay(scenario, name, username="alice") -> bool:
    return payability(scenario.game, username, scenario.find(name, Zone.HAND, username)).payable


def test_each_black_symbol_may_be_paid_with_two_life():
    scenario = _main(
        alice={
            "hand": ["Vampire Nighthawk"],
            "battlefield": ["K'rrik, Son of Yawgmoth", "Island"],
        },
        bob={},
    )
    assert _can_pay(scenario, "Vampire Nighthawk")
    casting = scenario.cast("Vampire Nighthawk")
    payment = casting.begin_paying()
    payment.tap_for_mana(scenario.find("Island", Zone.BATTLEFIELD, "alice"), [Color.BLUE])
    payment.pay()
    scenario.put_on_stack(casting)
    assert scenario.game.player("alice").life == 16
    assert scenario.find("Vampire Nighthawk", Zone.STACK, "alice").mana_value == 3


def test_without_krrik_the_black_symbols_need_black_mana():
    scenario = _main(
        alice={"hand": ["Vampire Nighthawk"], "battlefield": ["Island"]},
        bob={},
    )
    assert not _can_pay(scenario, "Vampire Nighthawk")


def test_black_mana_still_pays_when_the_player_has_it():
    scenario = _main(
        alice={
            "hand": ["Fatal Push"],
            "battlefield": ["K'rrik, Son of Yawgmoth", "Swamp"],
        },
        bob={"battlefield": ["Grizzly Bears"]},
    )
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    casting = scenario.cast("Fatal Push", targets=[bears])
    payment = casting.begin_paying()
    payment.tap_for_mana(scenario.find("Swamp", Zone.BATTLEFIELD, "alice"), [Color.BLACK])
    payment.pay()
    scenario.put_on_stack(casting)
    assert scenario.game.player("alice").life == 20


def test_krriks_controller_only():
    scenario = _main(
        alice={"battlefield": ["K'rrik, Son of Yawgmoth"]},
        bob={"hand": ["Fatal Push"]},
    )
    assert not _can_pay(scenario, "Fatal Push", "bob")


def test_the_life_must_be_there_to_pay():
    scenario = _main(
        alice={"hand": ["Vampire Nighthawk"], "battlefield": ["K'rrik, Son of Yawgmoth", "Island"]},
        bob={},
    )
    scenario.game.player("alice").life = 3
    assert not _can_pay(scenario, "Vampire Nighthawk")


def test_an_activated_abilitys_black_symbol_is_payable_with_life_too():
    scenario = _main(
        alice={"battlefield": ["K'rrik, Son of Yawgmoth", "Pestilence Demon"]},
        bob={},
    )
    demon = scenario.find("Pestilence Demon", Zone.BATTLEFIELD, "alice")
    scenario.activate(demon)
    scenario.pass_until_resolved()
    assert scenario.game.player("alice").life == 17  # 2 for the cost, 1 from the ability
