"""EP-01 R1 T4: costs to attack or block (CR 508.1h, 509.1d, 508.1d) and the
Aura tax on activated abilities (CR 602.2b).

- "Creatures can't attack you or planeswalkers you control unless their
  controller pays {1} for each of those creatures." (Archon of Absolution,
  Baird, Steward of Argive), with {W/P} (Norn's Annex) and "{X} ..., where X is
  the number of enchantments you control" (Sphere of Safety)
- Archangel of Tithes: the attack cost only "as long as this creature is
  untapped", and "As long as this creature is attacking, creatures can't block
  unless their controller pays {1} for each of those creatures."
- "This creature can't attack or block unless you pay {2}." (Qal Sisma
  Behemoth), "... {1} for each +1/+1 counter on it" (Myr Prototype)
- "Enchanted creature can't attack or block unless its controller pays {3}."
  (Oppressive Rays), "... {1} for each card in your hand" (Cowed by Wisdom)
- "This creature can't attack unless you return an enchantment you control to
  its owner's hand." (Floodtide Serpent)
- "Activated abilities of enchanted creature cost {3} more to activate."
  (Oppressive Rays)

CR 508.1d: a player "is not required to pay" a cost to attack. CR 508.1j:
partial payments are not allowed, so an unaffordable declaration is refused
and nothing taps.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _tapped(scenario, name: str, username: str) -> int:
    return sum(
        1
        for permanent in scenario.game.permanents_controlled_by(username)
        if permanent.name == name and permanent.tapped
    )


def _attack_scenario(defender_cards, *, lands: int = 4, attackers=("Grizzly Bears", "Hill Giant")):
    scenario = (
        Scenario()
        .player("alice", battlefield=[*attackers, *["Mountain"] * lands])
        .player("bob", battlefield=list(defender_cards))
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def _both(scenario):
    return (scenario.creature("Grizzly Bears", "alice"), scenario.creature("Hill Giant", "alice"))


# -- "Creatures can't attack you or planeswalkers you control unless ..." ----


@pytest.mark.parametrize("tax", ["Archon of Absolution", "Baird, Steward of Argive"])
def test_one_mana_per_attacker(tax: str) -> None:
    scenario = _attack_scenario([tax])
    scenario.attack_with(*_both(scenario))
    assert _tapped(scenario, "Mountain", "alice") == 2


@pytest.mark.parametrize("tax", ["Archon of Absolution", "Baird, Steward of Argive"])
def test_the_tax_may_be_unaffordable(tax: str) -> None:
    scenario = _attack_scenario([tax], lands=1)
    bears, giant = _both(scenario)
    with pytest.raises(ValueError, match=r"CR 508\.1h"):
        scenario.attack_with(bears, giant)
    assert not bears.tapped and not giant.tapped
    assert _tapped(scenario, "Mountain", "alice") == 0
    scenario.attack_with(bears)
    assert _tapped(scenario, "Mountain", "alice") == 1


def test_the_tax_reaches_attacks_on_planeswalkers() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Mountain"])
        .player("bob", battlefield=["Baird, Steward of Argive", "Kaito, Bane of Nightmares"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    walker = scenario.find("Kaito, Bane of Nightmares", Zone.BATTLEFIELD, "bob")
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"), defending=walker)
    assert _tapped(scenario, "Mountain", "alice") == 1


def test_the_tax_leaves_the_controllers_own_attacks_alone() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Baird, Steward of Argive", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))


def test_norns_annex_is_paid_with_white_mana() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Hill Giant", "Plains", "Plains"])
        .player("bob", battlefield=["Norn's Annex"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*_both(scenario))
    # {W/P} twice: each is a Plains tapped or 2 life, and nothing else.
    life_paid = 20 - scenario.player("alice").life
    assert _tapped(scenario, "Plains", "alice") + life_paid // 2 == 2
    assert life_paid % 2 == 0


def test_norns_annex_is_paid_with_life_when_no_white_is_available() -> None:
    scenario = _attack_scenario(["Norn's Annex"], lands=0)
    scenario.attack_with(*_both(scenario))
    assert scenario.player("alice").life == 16


def test_sphere_of_safety_charges_the_number_of_enchantments() -> None:
    scenario = _attack_scenario(["Sphere of Safety", "Ghostly Prison", "Glorious Anthem"], lands=10)
    scenario.attack_with(*_both(scenario))
    # Three enchantments: Sphere of Safety charges {3} each, Ghostly Prison {2} each.
    assert _tapped(scenario, "Mountain", "alice") == 2 * (3 + 2)


def test_sphere_of_safety_alone_charges_one_per_attacker() -> None:
    scenario = _attack_scenario(["Sphere of Safety"], lands=4)
    scenario.attack_with(*_both(scenario))
    assert _tapped(scenario, "Mountain", "alice") == 2


# -- Archangel of Tithes ------------------------------------------------------


def test_archangel_of_tithes_taxes_attacks_while_untapped() -> None:
    scenario = _attack_scenario(["Archangel of Tithes"])
    scenario.attack_with(*_both(scenario))
    assert _tapped(scenario, "Mountain", "alice") == 2


def test_a_tapped_archangel_of_tithes_taxes_nothing() -> None:
    scenario = _attack_scenario(["Archangel of Tithes"], lands=0)
    scenario.creature("Archangel of Tithes", "bob").tap()
    scenario.attack_with(*_both(scenario))


def test_archangel_of_tithes_taxes_blockers_while_it_attacks() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Archangel of Tithes", "Hill Giant"])
        .player("bob", battlefield=["Grizzly Bears", "Serra Angel", "Plains", "Plains"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    archangel = scenario.creature("Archangel of Tithes", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    scenario.attack_with(archangel, giant, defending="bob")
    scenario.block(giant, scenario.creature("Grizzly Bears", "bob"))
    scenario.block(archangel, scenario.creature("Serra Angel", "bob"))
    assert _tapped(scenario, "Plains", "bob") == 2


def test_an_unaffordable_block_cost_makes_the_block_illegal() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Archangel of Tithes"])
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    archangel = scenario.creature("Archangel of Tithes", "alice")
    scenario.attack_with(archangel, defending="bob")
    with pytest.raises(ValueError, match=r"CR 509\.1d"):
        scenario.block(archangel, scenario.creature("Serra Angel", "bob"))
    assert scenario.blockers() == []


def test_archangel_of_tithes_does_not_tax_blocks_when_not_attacking() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hill Giant"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant", "alice")
    scenario.attack_with(giant, defending="bob")
    scenario.block(giant, scenario.creature("Grizzly Bears", "bob"))


# -- a creature's own cost ----------------------------------------------------


def test_qal_sisma_behemoth_attack_costs_two() -> None:
    scenario = _attack_scenario([], lands=2, attackers=("Qal Sisma Behemoth",))
    scenario.attack_with(scenario.creature("Qal Sisma Behemoth", "alice"))
    assert _tapped(scenario, "Mountain", "alice") == 2


def test_qal_sisma_behemoth_unpaid_cannot_attack_but_nothing_forces_the_payment() -> None:
    scenario = _attack_scenario([], lands=1, attackers=("Qal Sisma Behemoth", "Grizzly Bears"))
    with pytest.raises(ValueError, match=r"CR 508\.1h"):
        scenario.attack_with(scenario.creature("Qal Sisma Behemoth", "alice"))
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))


def test_qal_sisma_behemoth_block_costs_two() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hill Giant"])
        .player("bob", battlefield=["Qal Sisma Behemoth", "Plains", "Plains"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant", "alice")
    scenario.attack_with(giant, defending="bob")
    scenario.block(giant, scenario.creature("Qal Sisma Behemoth", "bob"))
    assert _tapped(scenario, "Plains", "bob") == 2


def test_qal_sisma_behemoth_cannot_block_without_the_mana() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hill Giant"])
        .player("bob", battlefield=["Qal Sisma Behemoth", "Plains"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant", "alice")
    scenario.attack_with(giant, defending="bob")
    with pytest.raises(ValueError, match=r"CR 509\.1d"):
        scenario.block(giant, scenario.creature("Qal Sisma Behemoth", "bob"))


@pytest.mark.parametrize("counters", [1, 3])
def test_myr_prototype_costs_one_per_counter(counters: int) -> None:
    scenario = _attack_scenario([], lands=4, attackers=("Myr Prototype",))
    prototype = scenario.creature("Myr Prototype", "alice")
    prototype.add_counters("+1/+1", counters)
    prototype.summoning_sick = False
    scenario.attack_with(prototype)
    assert _tapped(scenario, "Mountain", "alice") == counters


def test_myr_prototype_with_no_counters_attacks_free() -> None:
    scenario = _attack_scenario([], lands=0, attackers=("Myr Prototype",))
    prototype = scenario.creature("Myr Prototype", "alice")
    prototype.summoning_sick = False
    scenario.attack_with(prototype)


# -- Auras ----------------------------------------------------------------------


def _enchant(scenario, aura: str, victim: str, aura_owner: str, victim_owner: str) -> None:
    scenario.find(aura, Zone.BATTLEFIELD, aura_owner).attach_to(
        scenario.creature(victim, victim_owner)
    )


def test_oppressive_rays_charges_three_to_attack() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Hill Giant", *["Mountain"] * 3])
        .player("bob", battlefield=["Oppressive Rays"])
        .build()
    )
    _enchant(scenario, "Oppressive Rays", "Grizzly Bears", "bob", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))
    assert _tapped(scenario, "Mountain", "alice") == 3


def test_oppressive_rays_leaves_other_creatures_free_and_can_go_unpaid() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Hill Giant", "Mountain"])
        .player("bob", battlefield=["Oppressive Rays"])
        .build()
    )
    _enchant(scenario, "Oppressive Rays", "Grizzly Bears", "bob", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    with pytest.raises(ValueError, match=r"CR 508\.1h"):
        scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))
    scenario.attack_with(scenario.creature("Hill Giant", "alice"))
    assert _tapped(scenario, "Mountain", "alice") == 0


def test_oppressive_rays_charges_three_to_block() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hill Giant"])
        .player("bob", battlefield=["Grizzly Bears", "Oppressive Rays", *["Plains"] * 3])
        .build()
    )
    _enchant(scenario, "Oppressive Rays", "Grizzly Bears", "bob", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant", "alice")
    scenario.attack_with(giant, defending="bob")
    scenario.block(giant, scenario.creature("Grizzly Bears", "bob"))
    assert _tapped(scenario, "Plains", "bob") == 3


def test_cowed_by_wisdom_counts_the_auras_controllers_hand() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", *["Mountain"] * 4])
        .player("bob", battlefield=["Cowed by Wisdom"], hand=["Island", "Island"])
        .build()
    )
    _enchant(scenario, "Cowed by Wisdom", "Grizzly Bears", "bob", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))
    assert _tapped(scenario, "Mountain", "alice") == 2


def test_cowed_by_wisdom_with_an_empty_hand_is_free() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Cowed by Wisdom"])
        .build()
    )
    _enchant(scenario, "Cowed by Wisdom", "Grizzly Bears", "bob", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))


def test_oppressive_rays_adds_three_to_activated_abilities() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Shivan Dragon", "Oppressive Rays", *["Mountain"] * 4])
        .player("bob")
        .build()
    )
    dragon = scenario.creature("Shivan Dragon", "alice")
    scenario.find("Oppressive Rays", Zone.BATTLEFIELD, "alice").attach_to(dragon)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cost = scenario.game.activation_cost(dragon, 0)
    assert cost.mana.converted == 4


def test_an_unenchanted_creature_pays_the_printed_activation_cost() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Shivan Dragon", "Oppressive Rays", *["Mountain"] * 4])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert (
        scenario.game.activation_cost(scenario.creature("Shivan Dragon", "alice"), 0).mana.converted
        == 1
    )


# -- Floodtide Serpent --------------------------------------------------------


def test_floodtide_serpent_returns_an_enchantment_to_attack() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Floodtide Serpent", "Ghostly Prison"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    serpent = scenario.creature("Floodtide Serpent", "alice")
    serpent.summoning_sick = False
    prison = scenario.find("Ghostly Prison", Zone.BATTLEFIELD, "alice")
    scenario.attack_with(serpent)
    assert prison.zone is Zone.HAND
    assert scenario.attackers() == [serpent]


def test_floodtide_serpent_without_an_enchantment_cannot_attack() -> None:
    scenario = Scenario().player("alice", battlefield=["Floodtide Serpent"]).player("bob").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    serpent = scenario.creature("Floodtide Serpent", "alice")
    serpent.summoning_sick = False
    assert scenario.can_attack(serpent) is False
    with pytest.raises(ValueError, match=r"CR 508\.1c"):
        scenario.attack_with(serpent)


def test_floodtide_serpent_lets_its_controller_choose_the_enchantment() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Floodtide Serpent", "Glorious Anthem", "Ghostly Prison"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    serpent = scenario.creature("Floodtide Serpent", "alice")
    serpent.summoning_sick = False
    prison = scenario.find("Ghostly Prison", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_cards(prison, username="alice")
    scenario.attack_with(serpent)
    assert prison.zone is Zone.HAND
    assert scenario.find("Glorious Anthem", Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD
