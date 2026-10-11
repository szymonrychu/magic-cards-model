"""Scenario: statics that change what colour mana counts as when spent
(CR 609.4b) - Celestial Dawn's "You may spend white mana as though it were
mana of any color. You may spend other mana only as though it were colorless
mana." (both sentences, every spell and ability of its controller) and
Quicksilver Elemental's "You may spend blue mana as though it were mana of any
color to pay the activation costs of this creature's abilities." (one colour,
one source's abilities).
"""

from magic_cards_model.machines import Step, payability
from magic_cards_model.models import Zone
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


def test_celestial_dawn_lets_white_mana_pay_a_red_symbol():
    scenario = _main(
        alice={"hand": ["Lightning Bolt"], "battlefield": ["Celestial Dawn", "Plains"]},
    )
    assert _can_pay(scenario, "Lightning Bolt")


def test_without_celestial_dawn_white_mana_cannot_pay_red():
    scenario = _main(alice={"hand": ["Lightning Bolt"], "battlefield": ["Plains"]})
    assert not _can_pay(scenario, "Lightning Bolt")


def test_celestial_dawn_makes_other_mana_colorless_only():
    """Two Llanowar Elves make {G}{G}: as colorless they pay {1} but never the
    {G} of Grizzly Bears."""
    scenario = _main(
        alice={
            "hand": ["Grizzly Bears"],
            "battlefield": ["Celestial Dawn", "Llanowar Elves", "Llanowar Elves"],
        },
    )
    assert not _can_pay(scenario, "Grizzly Bears")


def test_other_mana_still_pays_the_generic_part():
    """A Plains pays {G}, an Elf's {G} (as colorless) pays {1}."""
    scenario = _main(
        alice={
            "hand": ["Grizzly Bears"],
            "battlefield": ["Celestial Dawn", "Plains", "Llanowar Elves"],
        },
    )
    assert _can_pay(scenario, "Grizzly Bears")


def test_it_applies_to_its_controller_only():
    scenario = _main(
        alice={"battlefield": ["Celestial Dawn"]},
        bob={"hand": ["Lightning Bolt"], "battlefield": ["Mountain"]},
    )
    assert _can_pay(scenario, "Lightning Bolt", "bob")
