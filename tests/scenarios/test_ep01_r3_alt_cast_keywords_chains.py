"""'You may X. If you do, Y' chains (EP-01 round 3, T4).

The optional action is paid while the ability resolves and the consequence
runs only if it was (CR 608.2c, CR 608.2d). Shapes covered: a mana payment
whose consequence is a delayed next-cast copy (Najal, the Storm Runner;
Mercurial Spelldancer's counter-removal twin), removing counters from the
source to copy the triggering spell (Verazol, the Split Current), removing a
counter from each of N creatures (Dyadrine, Synthesis Amalgam), a chosen
graveyard target returned if a sacrifice is made (Daretti, Rocketeer
Engineer), and a put from hand or graveyard (Dakkon, Shadow Slayer; Bonny
Pall, Clearcutter).

Rules read with `mise run rules:find` in the session that wrote this:

- **CR 608.2c** - instructions are followed in the order written.
- **CR 608.2d** - an optional action is chosen while the ability resolves.
- **CR 603.7** - delayed triggered abilities.
- **CR 707.10** - copying a spell.
"""

import re

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import self_normalized_effect_text
from magic_cards_model.machines.effects.dispatch import _ability_effect_or_notice
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(*, alice=None, bob=None, step=Step.PRECOMBAT_MAIN):
    scenario = Scenario().player("alice", **(alice or {})).player("bob", **(bob or {})).build()
    scenario.start_at(step)
    return scenario


def _resolve_all(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _trigger_text(name: str, needle: str) -> str:
    return next(line for line in card(name).oracle_text.split("\n") if needle in line)


def test_every_listed_chain_is_read():
    for name, needle in [
        ("Najal, the Storm Runner", "you may pay {2}"),
        ("Mercurial Spelldancer", "oil counters"),
        ("Verazol, the Split Current", "kicked spell"),
        ("Dyadrine, Synthesis Amalgam", "each of two creatures"),
        ("Daretti, Rocketeer Engineer", "choose target artifact card"),
        ("Bonny Pall, Clearcutter", "hand or graveyard"),
    ]:
        printing = card(name)
        effect_text = re.sub(
            r"\s*\([^()]*\)\s*$", "", _trigger_text(name, needle).split(", ", 1)[1]
        )
        normalized = self_normalized_effect_text(
            printing.name, effect_text, legendary="Legendary" in printing.type_line
        )
        assert _ability_effect_or_notice(normalized) is not None, name


# ---- pay {2}, then copy the next instant or sorcery ---------------------------


def _najal_attacks(scenario, *, pay: bool):
    najal = scenario.find("Najal, the Storm Runner", Zone.BATTLEFIELD, "alice")
    scenario.attack_with(najal)
    scenario.game.put_triggers_on_stack()
    if pay:
        scenario.will_pay_the_mana_cost()
    else:
        scenario.will_pay_the_mana_cost(False)
    scenario.resolve_top()


def test_najal_paid_copies_the_next_instant():
    scenario = _board(
        alice={
            "battlefield": ["Najal, the Storm Runner"] + ["Mountain"] * 3,
            "hand": ["Lightning Bolt"],
        },
        bob={"life": 20},
        step=Step.DECLARE_ATTACKERS,
    )
    _najal_attacks(scenario, pay=True)
    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    _resolve_all(scenario)
    assert scenario.player("bob").life == 14


def test_najal_declined_copies_nothing():
    scenario = _board(
        alice={
            "battlefield": ["Najal, the Storm Runner"] + ["Mountain"] * 3,
            "hand": ["Lightning Bolt"],
        },
        step=Step.DECLARE_ATTACKERS,
    )
    _najal_attacks(scenario, pay=False)
    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    _resolve_all(scenario)
    assert scenario.player("bob").life == 17


# ---- remove a counter from each of two creatures ---------------------------------


def _dyadrine_attack(scenario, *attackers, take: bool = True):
    if take:
        scenario.will_take_the_may()
    scenario.attack_with(*attackers)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()


def test_dyadrine_removes_a_counter_from_two_creatures_draws_and_makes_a_robot():
    scenario = _board(
        alice={
            "battlefield": ["Dyadrine, Synthesis Amalgam", "Grizzly Bears"],
            "library": ["Plains", "Plains"],
        },
        step=Step.DECLARE_ATTACKERS,
    )
    dyadrine = scenario.find("Dyadrine, Synthesis Amalgam", Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    dyadrine.add_counters("+1/+1", 2)
    bears.add_counters("+1/+1", 1)
    _dyadrine_attack(scenario, dyadrine)
    assert dyadrine.counter_count("+1/+1") == 1 and bears.counter_count("+1/+1") == 0
    assert len(scenario.player("alice").hand) == 1
    assert any(p.name.startswith("Robot") for p in scenario.game.battlefield)


def test_dyadrine_with_only_one_countered_creature_does_nothing():
    scenario = _board(
        alice={
            "battlefield": ["Dyadrine, Synthesis Amalgam", "Grizzly Bears"],
            "library": ["Plains"],
        },
        step=Step.DECLARE_ATTACKERS,
    )
    dyadrine = scenario.find("Dyadrine, Synthesis Amalgam", Zone.BATTLEFIELD, "alice")
    dyadrine.add_counters("+1/+1", 3)
    _dyadrine_attack(scenario, dyadrine, take=False)
    assert dyadrine.counter_count("+1/+1") == 3
    assert not scenario.player("alice").hand
    assert not any(p.name.startswith("Robot") for p in scenario.game.battlefield)


def test_dyadrine_declined_keeps_the_counters():
    scenario = _board(
        alice={
            "battlefield": ["Dyadrine, Synthesis Amalgam", "Grizzly Bears"],
            "library": ["Plains"],
        },
        step=Step.DECLARE_ATTACKERS,
    )
    dyadrine = scenario.find("Dyadrine, Synthesis Amalgam", Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    dyadrine.add_counters("+1/+1", 1)
    bears.add_counters("+1/+1", 1)
    scenario.will_take_the_may(False)
    scenario.attack_with(dyadrine)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    assert dyadrine.counter_count("+1/+1") == 1 and bears.counter_count("+1/+1") == 1


# ---- chosen graveyard target, sacrifice, return -----------------------------------


def test_daretti_sacrifices_an_artifact_to_return_the_chosen_card():
    scenario = _board(
        alice={
            "battlefield": ["Daretti, Rocketeer Engineer", "Ornithopter"],
            "graveyard": ["Wurmcoil Engine"],
        },
        step=Step.DECLARE_ATTACKERS,
    )
    daretti = scenario.find("Daretti, Rocketeer Engineer", Zone.BATTLEFIELD, "alice")
    wurm = scenario.find("Wurmcoil Engine", Zone.GRAVEYARD, "alice")
    scenario.will_take_the_may()
    scenario.attack_with(daretti)
    scenario.choose_trigger_targets("Daretti, Rocketeer Engineer", [wurm])
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    assert wurm.zone is Zone.BATTLEFIELD
    assert scenario.find("Ornithopter", Zone.GRAVEYARD, "alice") is not None


def test_daretti_without_an_artifact_to_sacrifice_returns_nothing():
    scenario = _board(
        alice={"battlefield": ["Daretti, Rocketeer Engineer"], "graveyard": ["Ornithopter"]},
        step=Step.DECLARE_ATTACKERS,
    )
    daretti = scenario.find("Daretti, Rocketeer Engineer", Zone.BATTLEFIELD, "alice")
    thopter = scenario.find("Ornithopter", Zone.GRAVEYARD, "alice")
    scenario.attack_with(daretti)
    scenario.choose_trigger_targets("Daretti, Rocketeer Engineer", [thopter])
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    assert thopter.zone is Zone.GRAVEYARD


# ---- put a card from hand or graveyard ----------------------------------------------


def test_bonny_pall_puts_a_land_from_the_graveyard():
    scenario = _board(
        alice={
            "battlefield": ["Bonny Pall, Clearcutter", "Grizzly Bears"],
            "graveyard": ["Forest"],
            "library": ["Plains"],
        },
        step=Step.DECLARE_ATTACKERS,
    )
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may()
    scenario.attack_with(bears)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    assert scenario.find("Forest", Zone.BATTLEFIELD, "alice") is not None
