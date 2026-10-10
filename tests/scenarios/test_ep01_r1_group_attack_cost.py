"""EP-01 R1 T4: group attack and block restrictions and requirements, stated
by a permanent about creatures other than itself (CR 508.1c, 509.1b, 508.1d).

- "Creatures without flying can't attack." (Magus of the Moat), "... without
  flying or islandwalk ..." (Stormtide Leviathan)
- "Non-Eye creatures you control can't attack." (Evil Eye of Urborg)
- "Creatures of the chosen color without flying can't attack you." (Teferi's
  Moat)
- "Creatures with bribery counters on them can't attack or block." (Gwafa
  Hazid), "Creatures your opponents control with counters on them can't
  attack or block." (Kulrath Knight)
- "Each creature that's enchanted by an Aura you control can't attack you or
  planeswalkers you control." (Eriette of the Charmed Apple)
- "Creatures your opponents control attack each combat if able." (Angler
  Turtle, Fumiko the Lowblood), "Creatures enchanted player controls attack
  each combat if able." (Curse of the Nightly Hunt), "Goblin creatures attack
  each combat if able." (Goblin Assault), "Other Goblin creatures you control
  ..." (Goblin Rabblemaster), "Juggernauts you control ..." (Graaz)
- "No more than one creature can attack/block each combat." (Silent Arbiter)

Each is proven both ways: an affected creature is refused (or required), an
unaffected one is not. CR 508.1c and 509.1b: restrictions; CR 508.1d:
requirements, counted only when they can be obeyed without disobeying a
restriction.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Choice, ChoiceKind, Counter

from .harness import Scenario


def _declare(scenario: Scenario):
    built = scenario.build()
    built.start_at(Step.DECLARE_ATTACKERS)
    return built


# -- group "can't attack" ----------------------------------------------------


def test_magus_of_the_moat_stops_creatures_without_flying() -> None:
    scenario = _declare(
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Serra Angel"])
        .player("bob", battlefield=["Magus of the Moat"])
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "alice")
    assert scenario.can_attack(bears) is False
    assert scenario.can_attack(angel) is True
    with pytest.raises(ValueError, match=r"CR 508\.1c"):
        scenario.attack_with(bears)
    scenario.attack_with(angel)


def test_magus_of_the_moat_binds_its_own_controller_too() -> None:
    scenario = _declare(
        Scenario().player("alice", battlefield=["Magus of the Moat", "Grizzly Bears"]).player("bob")
    )
    assert scenario.can_attack(scenario.creature("Grizzly Bears", "alice")) is False


def test_stormtide_leviathan_lets_flying_and_islandwalk_through() -> None:
    scenario = _declare(
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Serra Angel", "Harbor Serpent"])
        .player("bob", battlefield=["Stormtide Leviathan", *["Island"] * 5])
    )
    assert scenario.can_attack(scenario.creature("Grizzly Bears", "alice")) is False
    assert scenario.can_attack(scenario.creature("Serra Angel", "alice")) is True
    assert scenario.can_attack(scenario.creature("Harbor Serpent", "alice")) is True


def test_stormtide_leviathan_itself_may_attack() -> None:
    scenario = _declare(
        Scenario()
        .player("alice", battlefield=["Stormtide Leviathan", "Grizzly Bears"])
        .player("bob")
    )
    assert scenario.can_attack(scenario.creature("Stormtide Leviathan", "alice")) is True
    assert scenario.can_attack(scenario.creature("Grizzly Bears", "alice")) is False


@pytest.mark.parametrize("eye", ["Evil Eye of Urborg", "Evil Eye of Orms-by-Gore"])
def test_evil_eye_stops_its_controllers_non_eyes_only(eye: str) -> None:
    scenario = _declare(
        Scenario().player("alice", battlefield=[eye, "Grizzly Bears"]).player("bob")
    )
    assert scenario.can_attack(scenario.creature("Grizzly Bears", "alice")) is False
    assert scenario.can_attack(scenario.creature(eye, "alice")) is True


@pytest.mark.parametrize("eye", ["Evil Eye of Urborg", "Evil Eye of Orms-by-Gore"])
def test_evil_eye_leaves_the_opponents_creatures_alone(eye: str) -> None:
    scenario = _declare(
        Scenario().player("alice", battlefield=["Grizzly Bears"]).player("bob", battlefield=[eye])
    )
    assert scenario.can_attack(scenario.creature("Grizzly Bears", "alice")) is True


def test_teferis_moat_stops_the_chosen_color_without_flying() -> None:
    scenario = Scenario().player(
        "alice", battlefield=["Savannah Lions", "Serra Angel", "Grizzly Bears"]
    )
    scenario = scenario.player("bob", battlefield=["Teferi's Moat"]).build()
    moat = scenario.find("Teferi's Moat", Zone.BATTLEFIELD, "bob")
    moat.choice = Choice(kind=ChoiceKind.COLOR, value="W")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert scenario.can_attack(scenario.creature("Savannah Lions", "alice")) is False
    assert scenario.can_attack(scenario.creature("Serra Angel", "alice")) is True
    assert scenario.can_attack(scenario.creature("Grizzly Bears", "alice")) is True


def test_teferis_moat_with_no_color_chosen_stops_nothing() -> None:
    scenario = _declare(
        Scenario()
        .player("alice", battlefield=["Savannah Lions"])
        .player("bob", battlefield=["Teferi's Moat"])
    )
    assert scenario.can_attack(scenario.creature("Savannah Lions", "alice")) is True


def test_gwafa_hazid_stops_creatures_with_bribery_counters_attacking_and_blocking() -> None:
    scenario = _declare(
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Hill Giant"])
        .player("bob", battlefield=["Gwafa Hazid, Profiteer", "Serra Angel"])
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters("bribery", 1)
    assert scenario.can_attack(bears) is False
    assert scenario.can_attack(scenario.creature("Hill Giant", "alice")) is True
    scenario.creature("Serra Angel", "bob").add_counters("bribery", 1)
    giant = scenario.creature("Hill Giant", "alice")
    scenario.attack_with(giant, defending="bob")
    with pytest.raises(ValueError, match=r"CR 509\.1b"):
        scenario.block(giant, scenario.creature("Serra Angel", "bob"))


def test_gwafa_hazid_ignores_other_counters() -> None:
    scenario = _declare(
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Gwafa Hazid, Profiteer"])
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 1)
    assert scenario.can_attack(bears) is True


def test_kulrath_knight_stops_opposing_creatures_with_counters() -> None:
    scenario = _declare(
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Hill Giant", "Serra Angel"])
        .player("bob", battlefield=["Kulrath Knight", "Savannah Lions"])
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 1)
    assert scenario.can_attack(bears) is False
    assert scenario.can_attack(scenario.creature("Hill Giant", "alice")) is True
    # Its own controller's creatures are not "opponents control".
    scenario.creature("Savannah Lions", "bob").add_counters(Counter.PLUS_ONE, 1)
    giant = scenario.creature("Hill Giant", "alice")
    scenario.attack_with(giant, defending="bob")
    scenario.block(giant, scenario.creature("Savannah Lions", "bob"))


def test_kulrath_knight_stops_opposing_blockers_with_counters() -> None:
    scenario = _declare(
        Scenario()
        .player("alice", battlefield=["Kulrath Knight", "Hill Giant"])
        .player("bob", battlefield=["Grizzly Bears", "Savannah Lions"])
    )
    scenario.creature("Grizzly Bears", "bob").add_counters(Counter.PLUS_ONE, 1)
    giant = scenario.creature("Hill Giant", "alice")
    scenario.attack_with(giant, defending="bob")
    with pytest.raises(ValueError, match=r"CR 509\.1b"):
        scenario.block(giant, scenario.creature("Grizzly Bears", "bob"))
    scenario.block(giant, scenario.creature("Savannah Lions", "bob"))


def test_eriette_stops_creatures_enchanted_by_its_controllers_aura() -> None:
    scenario = Scenario().player("alice", battlefield=["Grizzly Bears", "Hill Giant", "Rancor"])
    scenario = scenario.player(
        "bob", battlefield=["Eriette of the Charmed Apple", "Rancor"]
    ).build()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.find("Rancor", Zone.BATTLEFIELD, "bob").attach_to(bears)
    scenario.find("Rancor", Zone.BATTLEFIELD, "alice").attach_to(
        scenario.creature("Hill Giant", "alice")
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert scenario.can_attack(bears) is False
    assert scenario.can_attack(scenario.creature("Hill Giant", "alice")) is True


# -- group "attacks each combat if able" -------------------------------------


@pytest.mark.parametrize("source", ["Angler Turtle", "Fumiko the Lowblood"])
def test_opponents_creatures_attack_each_combat(source: str) -> None:
    scenario = _declare(
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Hill Giant"])
        .player("bob", battlefield=[source])
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with(bears)
    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with()
    scenario.attack_with(bears, scenario.creature("Hill Giant", "alice"))


def test_the_requirement_is_only_the_sources_opponents() -> None:
    scenario = _declare(
        Scenario().player("alice", battlefield=["Angler Turtle", "Grizzly Bears"]).player("bob")
    )
    scenario.attack_with()


def test_a_tapped_creature_is_not_required_to_attack() -> None:
    scenario = _declare(
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Hill Giant"])
        .player("bob", battlefield=["Angler Turtle"])
    )
    scenario.creature("Hill Giant", "alice").tap()
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))


def test_curse_of_the_nightly_hunt_requires_the_enchanted_players_creatures() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Hill Giant"])
        .player("bob", battlefield=["Curse of the Nightly Hunt"])
        .build()
    )
    scenario.find("Curse of the Nightly Hunt", Zone.BATTLEFIELD, "bob").attach_to(
        scenario.player("alice")
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))
    scenario.attack_with(
        scenario.creature("Grizzly Bears", "alice"), scenario.creature("Hill Giant", "alice")
    )


def test_curse_of_the_nightly_hunt_leaves_other_players_free() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Curse of the Nightly Hunt"])
        .build()
    )
    scenario.find("Curse of the Nightly Hunt", Zone.BATTLEFIELD, "bob").attach_to(
        scenario.player("bob")
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with()


def test_goblin_assault_requires_goblins_of_either_player() -> None:
    scenario = _declare(
        Scenario()
        .player("alice", battlefield=["Goblin Guide", "Grizzly Bears"])
        .player("bob", battlefield=["Goblin Assault"])
    )
    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))
    scenario.attack_with(scenario.creature("Goblin Guide", "alice"))


def test_goblin_rabblemaster_requires_its_other_goblins_not_itself() -> None:
    scenario = _declare(
        Scenario()
        .player("alice", battlefield=["Goblin Rabblemaster", "Goblin Guide", "Grizzly Bears"])
        .player("bob")
    )
    guide = scenario.creature("Goblin Guide", "alice")
    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with(scenario.creature("Goblin Rabblemaster", "alice"))
    scenario.attack_with(guide)


def test_graaz_requires_every_juggernaut_you_control() -> None:
    """Graaz makes its controller's other creatures Juggernauts (layer 4), so
    the group is read off the computed board: Graaz and Bears are both
    required, and a creature of the opponent's is not."""
    scenario = _declare(
        Scenario()
        .player("alice", battlefield=["Graaz, Unstoppable Juggernaut", "Grizzly Bears"])
        .player("bob")
    )
    graaz = scenario.creature("Graaz, Unstoppable Juggernaut", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with(bears)
    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with(graaz)
    scenario.attack_with(graaz, bears)


def test_graaz_leaves_the_opponents_creatures_free() -> None:
    scenario = _declare(
        Scenario()
        .player("alice", battlefield=["Hill Giant"])
        .player("bob", battlefield=["Graaz, Unstoppable Juggernaut"])
    )
    scenario.attack_with()


# -- Silent Arbiter ----------------------------------------------------------


def test_silent_arbiter_allows_one_attacker() -> None:
    scenario = _declare(
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Hill Giant"])
        .player("bob", battlefield=["Silent Arbiter"])
    )
    with pytest.raises(ValueError, match=r"CR 508\.1c"):
        scenario.attack_with(
            scenario.creature("Grizzly Bears", "alice"), scenario.creature("Hill Giant", "alice")
        )
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))


def test_silent_arbiter_allows_one_blocker() -> None:
    scenario = _declare(
        Scenario()
        .player("alice", battlefield=["Hill Giant"])
        .player("bob", battlefield=["Silent Arbiter", "Grizzly Bears"])
    )
    giant = scenario.creature("Hill Giant", "alice")
    scenario.attack_with(giant, defending="bob")
    with pytest.raises(ValueError, match=r"CR 509\.1b"):
        scenario.block(
            giant,
            scenario.creature("Silent Arbiter", "bob"),
            scenario.creature("Grizzly Bears", "bob"),
        )
    scenario.block(giant, scenario.creature("Grizzly Bears", "bob"))


# -- Alexios, Deimos of Kosmos: "attacks each combat if able, can't be
#    sacrificed, and can't attack its owner." ----------------------------------


def _alexios_board(controller: str):
    owner = "bob"
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Alexios, Deimos of Kosmos"])
        .build()
    )
    alexios = scenario.creature("Alexios, Deimos of Kosmos", owner)
    alexios.controller = controller
    alexios.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario, alexios


def test_alexios_cant_attack_its_owner() -> None:
    scenario, alexios = _alexios_board("alice")
    assert scenario.can_attack(alexios, "bob") is False
    with pytest.raises(ValueError, match=r"CR 508\.1c"):
        scenario.attack_with(alexios, defending="bob")


def test_alexios_may_attack_when_its_owner_controls_it() -> None:
    scenario = (
        Scenario().player("alice", battlefield=["Alexios, Deimos of Kosmos"]).player("bob").build()
    )
    alexios = scenario.creature("Alexios, Deimos of Kosmos", "alice")
    alexios.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert scenario.can_attack(alexios) is True


def test_alexios_attacks_each_combat_if_able() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Alexios, Deimos of Kosmos", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    alexios = scenario.creature("Alexios, Deimos of Kosmos", "alice")
    alexios.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))
    scenario.attack_with(alexios)


def test_alexios_cant_be_sacrificed() -> None:
    scenario = (
        Scenario().player("alice", battlefield=["Alexios, Deimos of Kosmos"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alexios = scenario.creature("Alexios, Deimos of Kosmos", "alice")
    scenario.game.sacrifice(alexios)
    assert alexios.zone is Zone.BATTLEFIELD


def test_other_creatures_can_still_be_sacrificed() -> None:
    scenario = Scenario().player("alice", battlefield=["Grizzly Bears"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.sacrifice(bears)
    assert bears.zone is Zone.GRAVEYARD


def test_alexios_cannot_be_sacrificed_to_pay_a_cost() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Goblin Bombardment", "Alexios, Deimos of Kosmos"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alexios = scenario.creature("Alexios, Deimos of Kosmos", "alice")
    bombardment = scenario.find("Goblin Bombardment", Zone.BATTLEFIELD, "alice")
    with pytest.raises(ValueError, match="can't be sacrificed"):
        scenario.activate(
            bombardment,
            sacrificing=[alexios],
            targets=[scenario.player("bob")],
            username="alice",
        )
    assert alexios.zone is Zone.BATTLEFIELD
