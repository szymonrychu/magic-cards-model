"""Scenario: "<n> damage to target attacking or blocking creature. You gain
life equal to the excess damage dealt this way." (Razor Rings.)

Razor Rings is the only in-pool printing of the template (Scryfall
`o:"excess damage"` in Modern/Pioneer/Standard returns it, the NW-02 token and
controller-damage spells, Nahiri's Warcrafting and Unleash the Inferno, none of
which gains life), so the reader is proven on that card alone, across the
whole range of excess: some, none, exactly lethal, damage already marked,
prevented, illegal target.

Verified this session with `mise run rules:find`:

- **CR 120.10** - excess damage dealt to a creature is the amount dealt greater
  than lethal damage; lethal accounts for damage already marked.
- **CR 120.6** - a creature with marked damage at or above its toughness has
  been dealt lethal damage; marked damage counts toward it.
- **CR 615.6** - prevented damage is never dealt, so it is never excess.
- **CR 608.2b** - an illegal sole target means the spell does nothing.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _attack(alice_creatures, bob_creatures=(), *, block=False, hand=("Razor Rings",)):
    """Alice attacks bob with her first creature; bob blocks with his first if
    `block`. Returns (scenario, attacker, blocker)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=["Plains"] * 4 + list(alice_creatures),
        )
        .player("bob", battlefield=list(bob_creatures))
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    attacker = scenario.creature(alice_creatures[0], "alice")
    blocker = scenario.creature(bob_creatures[0], "bob") if bob_creatures else None
    scenario.attack_with(attacker)
    if block:
        scenario.block(attacker, blocker)
    return scenario, attacker, blocker


def _rings(scenario, target):
    scenario.cast_and_resolve(
        "Razor Rings", *scenario.untapped_sources("Plains", "Plains"), targets=[target]
    )


def test_razor_rings_gains_life_equal_to_the_excess_over_an_attacker():
    scenario, bears, _ = _attack(["Grizzly Bears"])
    _rings(scenario, bears)
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 22  # 4 damage, 2 lethal


def test_razor_rings_gains_life_for_the_excess_over_a_blocker():
    scenario, _, blocker = _attack(["Hill Giant"], ["Savannah Lions"], block=True)
    _rings(scenario, blocker)
    assert blocker.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 23  # 4 damage, 1 lethal


def test_razor_rings_kills_a_three_toughness_attacker_and_gains_one():
    scenario, giant, _ = _attack(["Hill Giant"])
    _rings(scenario, giant)
    assert giant.zone is Zone.GRAVEYARD  # 4 damage on a 3/3: 3 lethal, 1 excess
    assert scenario.player("alice").life == 21


def test_razor_rings_on_a_creature_that_absorbs_it_all_gains_nothing():
    scenario, dreadmaw, _ = _attack(["Colossal Dreadmaw"])
    _rings(scenario, dreadmaw)
    assert dreadmaw.zone is Zone.BATTLEFIELD
    assert dreadmaw.damage == 4
    assert scenario.player("alice").life == 20  # 0 excess gains 0


def test_razor_rings_on_a_creature_with_exactly_lethal_toughness_gains_nothing():
    scenario, spider, _ = _attack(["Giant Spider"])
    _rings(scenario, spider)
    assert spider.zone is Zone.GRAVEYARD  # 4 damage on a 2/4
    assert scenario.player("alice").life == 20


def test_razor_rings_counts_damage_already_marked():
    scenario, giant, _ = _attack(["Hill Giant"])
    giant.damage = 2  # 1 toughness left
    _rings(scenario, giant)
    assert giant.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 23  # 4 damage, 1 lethal


def test_razor_rings_gains_nothing_when_the_damage_is_prevented():
    scenario, bears, _ = _attack(["Grizzly Bears"], hand=("Razor Rings", "Shielded Passage"))
    scenario.cast_and_resolve(
        "Shielded Passage", *scenario.untapped_sources("Plains"), targets=[bears]
    )
    _rings(scenario, bears)
    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 20  # CR 615.6: never dealt, never excess


def test_razor_rings_with_an_illegal_target_gains_nothing():
    scenario, bears, _ = _attack(["Grizzly Bears"])
    scenario.game.cast(
        scenario.find("Razor Rings", Zone.HAND, "alice"),
        "alice",
        targets=[bears],
        mana_sources=scenario.untapped_sources("Plains", "Plains"),
    )
    scenario.game.destroy(bears)
    scenario.resolve_top()
    assert scenario.player("alice").life == 20


def test_razor_rings_cannot_target_a_creature_that_is_not_in_combat():
    scenario, _, _ = _attack(["Grizzly Bears"], ["Hill Giant"])
    idle = scenario.creature("Hill Giant", "bob")
    with pytest.raises(ValueError):
        scenario.game.cast(
            scenario.find("Razor Rings", Zone.HAND, "alice"),
            "alice",
            targets=[idle],
            mana_sources=scenario.untapped_sources("Plains", "Plains"),
        )
