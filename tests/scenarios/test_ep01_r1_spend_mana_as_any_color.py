"""CR 609.4b: "You may spend mana as though it were mana of any color [to cast
<quality> spells]." read off a permanent on the battlefield (EP-01 round 1,
task T7).

    Chromatic Orrery   - You may spend mana as though it were mana of any color.
    Oath of Nissa      - ... to cast planeswalker spells.
    Case File Auditor  - ... to cast Case spells.
    Mycosynth Lattice  - Players may spend mana as though it were mana of any color.

The permission "affects only how the player may pay a cost. It doesn't change
that cost" - each case casts a real card through the engine and asserts what
was tapped; each has a spell or a player the line does NOT reach.
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


def test_chromatic_orrery_lets_any_mana_pay_any_colored_symbol():
    scenario = _main(
        alice={
            "hand": ["Lightning Bolt"],
            "battlefield": ["Chromatic Orrery", "Island"],
        },
        bob={},
    )
    assert _can_pay(scenario, "Lightning Bolt")
    casting = scenario.cast("Lightning Bolt", targets=["bob"])
    payment = casting.begin_paying()
    payment.tap_for_mana(scenario.find("Island", Zone.BATTLEFIELD, "alice"), [Color.BLUE])
    payment.pay()
    bolt = scenario.put_on_stack(casting)
    assert bolt.zone is Zone.STACK


def test_chromatic_orrery_does_not_help_the_opponent():
    scenario = _main(
        alice={"battlefield": ["Chromatic Orrery"]},
        bob={"hand": ["Lightning Bolt"], "battlefield": ["Island"]},
    )
    assert not _can_pay(scenario, "Lightning Bolt", "bob")


def test_chromatic_orrerys_own_colorless_mana_pays_for_red():
    """{T}: Add {C}{C}{C}{C}{C} plus the permission is the card's whole point:
    colorless mana pays the {R} of a Bolt."""
    scenario = _main(
        alice={"hand": ["Lightning Bolt"], "battlefield": ["Chromatic Orrery"]},
    )
    assert _can_pay(scenario, "Lightning Bolt")


def test_without_the_permission_an_island_cannot_pay_for_red():
    scenario = _main(alice={"hand": ["Lightning Bolt"], "battlefield": ["Island"]})
    assert not _can_pay(scenario, "Lightning Bolt")


def test_oath_of_nissa_reaches_planeswalker_spells_only():
    scenario = _main(
        alice={
            "hand": ["Jace Beleren", "Grizzly Bears"],
            "battlefield": ["Oath of Nissa", "Mountain", "Mountain", "Mountain"],
        },
    )
    assert _can_pay(scenario, "Jace Beleren")
    assert not _can_pay(scenario, "Grizzly Bears")

    casting = scenario.cast("Jace Beleren")
    payment = casting.begin_paying()
    for land in scenario.untapped_sources("Mountain", "Mountain", "Mountain"):
        payment.tap_for_mana(land, [Color.RED])
    payment.pay()
    assert scenario.put_on_stack(casting).zone is Zone.STACK


def test_case_file_auditor_reaches_case_spells_only():
    scenario = _main(
        alice={
            "hand": ["Case of the Crimson Pulse", "Lightning Bolt"],
            "battlefield": ["Case File Auditor", "Island", "Island", "Island"],
        },
    )
    assert _can_pay(scenario, "Case of the Crimson Pulse")
    assert not _can_pay(scenario, "Lightning Bolt")


def test_players_may_spend_applies_to_every_player():
    scenario = _main(
        alice={"battlefield": ["Mycosynth Lattice"]},
        bob={"hand": ["Lightning Bolt"], "battlefield": ["Island"]},
    )
    assert _can_pay(scenario, "Lightning Bolt", "bob")


def test_the_permission_reaches_activated_abilities_too_when_unscoped():
    """CR 609.4b: an unscoped sentence covers abilities as well as spells
    (the scoped ones read above are about spells only)."""
    scenario = _main(
        alice={
            "battlefield": ["Chromatic Orrery", "Island", "Island", "Island", "Island", "Island"]
        },
    )
    orrery = scenario.find("Chromatic Orrery", Zone.BATTLEFIELD, "alice")
    assert scenario.game.spends_mana_as_any_color(
        orrery, scenario.game.activated_abilities(orrery)[0], "alice"
    )
