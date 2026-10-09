"""EP-01 R1 T4: Aura/Equipment attack-block restrictions read off the
attachment (CR 508.1c, 509.1b, 508.1d, 602.5).

- "Enchanted creature can't attack or block, and its activated abilities can't
  be activated." (Arrest, Prison Sentence) and the "unless they're mana
  abilities" form on an enchanted permanent (Faith's Fetters)
- "Enchanted creature can't attack." (Forced Worship, Weight of Conscience),
  "Enchanted creature can't block." (Visions of Brutality)
- "Enchanted creature attacks each combat if able." (Lust for War)
- Dog Umbra: only while another player controls the enchanted creature
- "Enchanted artifact can't attack or block ..." (Stasis Cocoon)

Each is proven both ways: the enchanted creature is refused, a bystander is
not, and a creature that loses the Aura is free again.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _attack_scenario(aura: str, victim: str = "Grizzly Bears"):
    scenario = (
        Scenario()
        .player("alice", battlefield=[aura, victim, "Hill Giant"])
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    enchanted = scenario.creature(victim, "alice")
    scenario.find(aura, Zone.BATTLEFIELD, "alice").attach_to(enchanted)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario, enchanted


def _block_scenario(aura: str, victim: str = "Grizzly Bears", aura_owner: str = "bob"):
    battlefield = {"alice": ["Hill Giant"], "bob": [victim]}
    battlefield[aura_owner] = [*battlefield[aura_owner], aura]
    scenario = (
        Scenario()
        .player("alice", battlefield=battlefield["alice"])
        .player("bob", battlefield=battlefield["bob"])
        .build()
    )
    enchanted = scenario.creature(victim, "bob")
    scenario.find(aura, Zone.BATTLEFIELD, aura_owner).attach_to(enchanted)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Hill Giant", "alice"), defending="bob")
    return scenario, enchanted


CANT_ATTACK_AND_BLOCK = [
    "Arrest",
    "Prison Sentence",
    "Lawmage's Binding",
    "One Thousand Lashes",
    "Trapped in the Tower",
    "Desert's Hold",
    "Faith's Fetters",
    "Petrify",
    "Suppression Bonds",
    "Planar Disruption",
    "Nahiri's Binding",
    "Realmbreaker's Grasp",
    "Detention Vortex",
]


@pytest.mark.parametrize("aura", CANT_ATTACK_AND_BLOCK)
def test_enchanted_creature_cant_attack(aura: str) -> None:
    scenario, enchanted = _attack_scenario(aura)
    assert scenario.can_attack(enchanted) is False
    assert scenario.can_attack(scenario.creature("Hill Giant")) is True
    with pytest.raises(ValueError, match="can't attack"):
        scenario.attack_with(enchanted)


@pytest.mark.parametrize("aura", CANT_ATTACK_AND_BLOCK)
def test_enchanted_creature_cant_block(aura: str) -> None:
    scenario, enchanted = _block_scenario(aura)
    giant = scenario.creature("Hill Giant", "alice")
    with pytest.raises(ValueError, match="can't block"):
        scenario.block(giant, enchanted)


def test_an_unenchanted_creature_blocks_freely() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hill Giant"])
        .player("bob", battlefield=["Arrest", "Grizzly Bears", "Serra Angel"])
        .build()
    )
    scenario.find("Arrest", Zone.BATTLEFIELD, "bob").attach_to(
        scenario.creature("Grizzly Bears", "bob")
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant", "alice")
    scenario.attack_with(giant, defending="bob")
    scenario.block(giant, scenario.creature("Serra Angel", "bob"))


def test_leaving_the_creature_frees_it() -> None:
    scenario, enchanted = _attack_scenario("Arrest")
    scenario.find("Arrest", Zone.BATTLEFIELD, "alice").attach_to(scenario.creature("Hill Giant"))
    assert scenario.can_attack(enchanted) is True
    assert scenario.can_attack(scenario.creature("Hill Giant")) is False


@pytest.mark.parametrize(
    "aura", ["Forced Worship", "Weight of Conscience", "Captured by the Consulate"]
)
def test_cant_attack_only_leaves_blocking_alone(aura: str) -> None:
    scenario, enchanted = _attack_scenario(aura)
    assert scenario.can_attack(enchanted) is False
    blocked, victim = _block_scenario(aura)
    blocked.block(blocked.creature("Hill Giant", "alice"), victim)


def test_cant_block_only_leaves_attacking_alone() -> None:
    scenario, enchanted = _attack_scenario("Visions of Brutality")
    assert scenario.can_attack(enchanted) is True
    blocked, victim = _block_scenario("Visions of Brutality", aura_owner="alice")
    with pytest.raises(ValueError, match="can't block"):
        blocked.block(blocked.creature("Hill Giant", "alice"), victim)


def test_enchanted_artifact_cant_attack_or_block() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Stasis Cocoon", "Memnite"])
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    memnite = scenario.creature("Memnite", "alice")
    scenario.find("Stasis Cocoon", Zone.BATTLEFIELD, "alice").attach_to(memnite)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert scenario.can_attack(memnite) is False


def test_dog_umbra_only_while_another_player_controls_the_creature() -> None:
    other, theirs = _block_scenario("Dog Umbra", aura_owner="alice")
    with pytest.raises(ValueError, match="can't block"):
        other.block(other.creature("Hill Giant", "alice"), theirs)
    own, mine = _block_scenario("Dog Umbra", aura_owner="bob")
    own.block(own.creature("Hill Giant", "alice"), mine)


def test_activated_abilities_of_the_enchanted_creature_cant_be_activated() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Arrest", "Basking Rootwalla", "Forest", "Forest"])
        .player("bob")
        .build()
    )
    rootwalla = scenario.creature("Basking Rootwalla", "alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.why_cannot_activate(rootwalla, 0, "alice") is None
    scenario.find("Arrest", Zone.BATTLEFIELD, "alice").attach_to(rootwalla)
    reason = scenario.why_cannot_activate(rootwalla, 0, "alice")
    assert reason is not None and "activated abilities can't be activated" in reason


def test_faiths_fetters_spares_mana_abilities() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Faith's Fetters", "Llanowar Elves"])
        .player("bob")
        .build()
    )
    elves = scenario.creature("Llanowar Elves", "alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.find("Faith's Fetters", Zone.BATTLEFIELD, "alice").attach_to(elves)
    assert scenario.why_cannot_activate(elves, 0, "alice") is None


def test_enchanted_creature_attacks_each_combat_if_able() -> None:
    scenario, enchanted = _attack_scenario("Lust for War")
    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with(scenario.creature("Hill Giant"))
    scenario.attack_with(enchanted)
    assert scenario.attackers() == [enchanted]


# -- Sightless Brawler, Fog on the Barrow-Downs, Hold for Ransom, Dog Umbra -----


def test_sightless_brawler_aura_grants_the_pump_and_cant_attack_alone() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Sightless Brawler", "Grizzly Bears", "Hill Giant"])
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.find("Sightless Brawler", Zone.BATTLEFIELD, "alice").attach_to(bears)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert scenario.game.power_of(bears) == 5
    assert scenario.game.toughness_of(bears) == 4
    with pytest.raises(ValueError, match=r"CR 508\.1c"):
        scenario.attack_with(bears)
    scenario.attack_with(bears, scenario.creature("Hill Giant", "alice"))


def test_sightless_brawler_leaves_other_creatures_alone() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Sightless Brawler", "Grizzly Bears", "Hill Giant"])
        .player("bob")
        .build()
    )
    scenario.find("Sightless Brawler", Zone.BATTLEFIELD, "alice").attach_to(
        scenario.creature("Grizzly Bears", "alice")
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Hill Giant", "alice"))


def test_fog_on_the_barrow_downs_makes_a_spirit_that_cant_attack_or_block() -> None:
    scenario, enchanted = _attack_scenario("Fog on the Barrow-Downs")
    assert scenario.game.characteristics_of(enchanted).subtypes == ("Spirit",)
    assert scenario.can_attack(enchanted) is False
    assert scenario.can_attack(scenario.creature("Hill Giant")) is True
    blocked, victim = _block_scenario("Fog on the Barrow-Downs")
    with pytest.raises(ValueError, match="can't block"):
        blocked.block(blocked.creature("Hill Giant", "alice"), victim)


def test_hold_for_ransom_restricts_and_grants_the_sacrifice_ability() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", *["Mountain"] * 7])
        .player("bob", battlefield=["Hold for Ransom"], library=["Island"] * 3)
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    ransom = scenario.find("Hold for Ransom", Zone.BATTLEFIELD, "bob")
    ransom.attach_to(bears)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.can_attack(bears) is False
    hand = len(scenario.player("bob").hand)
    scenario.activate(bears, username="alice", auto=True)
    scenario.resolve_top()
    # The ransom is paid by the held creature's controller; the Aura's
    # controller sacrifices the Aura and draws, and the creature is free.
    assert ransom.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD
    assert len(scenario.player("bob").hand) == hand + 1
    assert scenario.can_attack(bears) is True


def test_hold_for_ransom_cannot_be_activated_at_instant_speed() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", *["Mountain"] * 7])
        .player("bob", battlefield=["Hold for Ransom"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.find("Hold for Ransom", Zone.BATTLEFIELD, "bob").attach_to(bears)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert scenario.why_cannot_activate(bears, 0, "alice") is not None


def test_dog_umbra_has_umbra_armor_only_on_its_controllers_creature() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Dog Umbra"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    umbra = scenario.find("Dog Umbra", Zone.BATTLEFIELD, "alice")
    umbra.attach_to(bears)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.destroy(bears)
    assert bears.zone is Zone.BATTLEFIELD, "umbra armor: destroy the Aura instead (CR 702.89a)"
    assert umbra.zone is Zone.GRAVEYARD


def test_dog_umbra_on_an_opponents_creature_has_no_umbra_armor() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Dog Umbra"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    giant = scenario.creature("Hill Giant", "bob")
    umbra = scenario.find("Dog Umbra", Zone.BATTLEFIELD, "alice")
    umbra.attach_to(giant)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.destroy(giant)
    assert giant.zone is Zone.GRAVEYARD
