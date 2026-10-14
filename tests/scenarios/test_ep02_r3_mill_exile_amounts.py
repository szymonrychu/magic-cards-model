"""Scenario: mill / exile-the-top-X amounts (EP-02 R3 T3).

Part 1 - the mill sentence: "<who> mills <amount>" where <who> is "target
player", "up to one target player" or "any number of target players each" and
<amount> is a number, "cards equal to <expr>" or "half their library, rounded
down".

CR numbers below were read with `mise run rules:find` in the session that
wrote this file:

- **CR 701.17a** - to mill is to put cards from the top of the library into
  the graveyard; with fewer cards, as many as possible.
- **CR 107.1c** - "any number of" targets is nought upwards.
- **CR 107.1a** - a "half" prints which way it rounds.
- **CR 608.2h** - the amount is taken once, as the instruction applies.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

SWAMP = "Swamp"


def _graveyard(scenario, name):
    return len(scenario.player(name).graveyard)


def test_space_time_anomaly_mills_cards_equal_to_the_casters_life_total():
    scenario = (
        Scenario()
        .player(
            "alice",
            life=7,
            hand=["Space-Time Anomaly"],
            battlefield=["Island", "Island", "Plains", "Plains"],
        )
        .player("bob", library=[SWAMP] * 12)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Space-Time Anomaly",
        *scenario.untapped_sources("Island", "Island", "Plains", "Plains"),
        targets=["bob"],
    )
    assert _graveyard(scenario, "bob") == 7
    assert len(scenario.player("bob").library) == 5


def test_a_life_total_larger_than_the_library_mills_the_whole_library():
    """CR 701.17a: as many as possible."""
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            hand=["Space-Time Anomaly"],
            battlefield=["Island", "Island", "Plains", "Plains"],
        )
        .player("bob", library=[SWAMP] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Space-Time Anomaly",
        *scenario.untapped_sources("Island", "Island", "Plains", "Plains"),
        targets=["bob"],
    )
    assert _graveyard(scenario, "bob") == 3


def test_singularity_rupture_destroys_creatures_then_mills_half_rounded_down():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Singularity Rupture"],
            battlefield=["Island", "Island", "Island", "Swamp", "Swamp", "Swamp", "Grizzly Bears"],
            library=[SWAMP] * 9,
        )
        .player("bob", library=[SWAMP] * 11, battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Singularity Rupture",
        *scenario.untapped_sources("Island", "Island", "Island", "Swamp", "Swamp", "Swamp"),
        targets=["alice", "bob"],
    )
    assert _graveyard(scenario, "bob") == 5 + 1  # half of 11 rounded down, plus the Bears
    assert _graveyard(scenario, "alice") == 4 + 1 + 1  # half of 9, Bears, the spell itself
    assert not scenario.game.battlefield or all(
        c.card.name != "Grizzly Bears" for c in scenario.game.battlefield
    )


def test_any_number_of_target_players_may_be_none():
    """CR 107.1c: nought targets is legal; nobody mills."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Singularity Rupture"],
            battlefield=["Island", "Island", "Island", "Swamp", "Swamp", "Swamp"],
            library=[SWAMP] * 9,
        )
        .player("bob", library=[SWAMP] * 11)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Singularity Rupture",
        *scenario.untapped_sources("Island", "Island", "Island", "Swamp", "Swamp", "Swamp"),
        targets=[],
    )
    assert _graveyard(scenario, "bob") == 0
    assert len(scenario.player("alice").library) == 9


def test_riverchurn_monument_mills_two_each_for_every_chosen_player():
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Riverchurn Monument", "Island", "Island"], library=[SWAMP] * 5
        )
        .player("bob", library=[SWAMP] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    monument = scenario.find("Riverchurn Monument", Zone.BATTLEFIELD)
    scenario.activate(
        monument,
        *scenario.untapped_sources("Island", "Island"),
        index=0,
        targets=["alice", "bob"],
    )
    scenario.resolve_top()
    assert _graveyard(scenario, "alice") == 2
    assert _graveyard(scenario, "bob") == 2


def test_riverchurn_monument_exhaust_mills_each_players_own_graveyard_size():
    """Each chosen player's count is their own (CR 608.2h: taken once, before
    anything moves)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Riverchurn Monument", "Island", "Island", "Island", "Island"],
            library=[SWAMP] * 10,
            graveyard=[SWAMP] * 3,
        )
        .player("bob", library=[SWAMP] * 10, graveyard=[SWAMP] * 1)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    monument = scenario.find("Riverchurn Monument", Zone.BATTLEFIELD)
    scenario.activate(
        monument,
        *scenario.untapped_sources("Island", "Island", "Island", "Island"),
        index=1,
        targets=["alice", "bob"],
    )
    scenario.resolve_top()
    assert _graveyard(scenario, "alice") == 6
    assert _graveyard(scenario, "bob") == 2


def _settle(scenario):
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def test_veteran_ice_climber_mills_by_its_own_power_on_attack():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Veteran Ice Climber"])
        .player("bob", library=[SWAMP] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    climber = scenario.creature("Veteran Ice Climber", "alice")
    climber.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_choose_targets("bob", username="alice", source="Veteran Ice Climber")
    scenario.attack_with(climber)
    _settle(scenario)
    assert _graveyard(scenario, "bob") == 1


def test_veteran_ice_climber_with_no_target_chosen_mills_nobody():
    """ "Up to one" target player (CR 115.6 lets it be none)."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Veteran Ice Climber"])
        .player("bob", library=[SWAMP] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    climber = scenario.creature("Veteran Ice Climber", "alice")
    climber.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_choose_targets(username="alice", source="Veteran Ice Climber")
    scenario.attack_with(climber)
    _settle(scenario)
    assert _graveyard(scenario, "bob") == 0


# --------------------------------------------------------------------------
# Part 2 - "creature with total power and toughness 5 or less" (Cut Down)
#
# CR 208.1 power and toughness are two characteristics of a creature; the
# restriction sums the two as the layers leave them (CR 613.4c).
# --------------------------------------------------------------------------


def _cut_down_board(*bob_creatures):
    return (
        Scenario()
        .player("alice", hand=["Cut Down"], battlefield=[SWAMP])
        .player("bob", battlefield=list(bob_creatures))
        .build()
    )


def test_cut_down_destroys_a_creature_whose_stats_total_five_or_less():
    scenario = _cut_down_board("Grizzly Bears")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_and_resolve("Cut Down", *scenario.untapped_sources(SWAMP), targets=[bears])
    assert "Grizzly Bears" not in scenario.battlefield_names()


def test_cut_down_total_exactly_five_is_legal():
    scenario = _cut_down_board("Kird Ape", "Forest")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ape = scenario.creature("Kird Ape", "bob")
    scenario.cast_and_resolve("Cut Down", *scenario.untapped_sources(SWAMP), targets=[ape])
    assert "Kird Ape" not in scenario.battlefield_names()


def test_cut_down_cannot_target_a_creature_with_total_six():
    scenario = _cut_down_board("Hill Giant")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    with pytest.raises(ValueError, match="total power and toughness"):
        scenario.cast("Cut Down", targets=[giant])


# --------------------------------------------------------------------------
# Part 3 - "Destroy target artifact if its mana value is equal to the amount
# of unspent mana you have" (Glissa Sunseeker). The target is any artifact
# (CR 115.1); the condition is read as the ability resolves (CR 608.2c), off
# the mana pool (CR 106.4) and the artifact's mana value (CR 202.3).
# --------------------------------------------------------------------------


def _glissa_board(floating):
    from magic_cards_model.models import Color

    scenario = (
        Scenario()
        .player("alice", battlefield=["Glissa Sunseeker"])
        .player("bob", battlefield=["Sol Ring", "Mind Stone"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    glissa = scenario.creature("Glissa Sunseeker", "alice")
    glissa.summoning_sick = False
    if floating:
        scenario.player("alice").mana_pool.add(Color.COLORLESS, floating)
    return scenario, glissa


def test_glissa_destroys_an_artifact_whose_mana_value_equals_the_unspent_mana():
    scenario, glissa = _glissa_board(2)
    scenario.activate(glissa, index=0, targets=[scenario.find("Mind Stone", Zone.BATTLEFIELD)])
    scenario.resolve_top()
    assert "Mind Stone" not in scenario.battlefield_names()


def test_glissa_leaves_an_artifact_whose_mana_value_differs():
    scenario, glissa = _glissa_board(2)
    scenario.activate(glissa, index=0, targets=[scenario.find("Sol Ring", Zone.BATTLEFIELD)])
    scenario.resolve_top()
    assert "Sol Ring" in scenario.battlefield_names()


def test_glissa_with_no_unspent_mana_destroys_only_a_zero_mana_value_artifact():
    scenario, glissa = _glissa_board(0)
    scenario.activate(glissa, index=0, targets=[scenario.find("Mind Stone", Zone.BATTLEFIELD)])
    scenario.resolve_top()
    assert "Mind Stone" in scenario.battlefield_names()


def test_glissa_cannot_target_a_nonartifact():
    scenario, glissa = _glissa_board(2)
    with pytest.raises(ValueError):
        scenario.activate(glissa, index=0, targets=[scenario.creature("Glissa Sunseeker")])


# --------------------------------------------------------------------------
# Part 4 - "this creature's base power becomes <amount> until end of turn"
# (Belligerent Yearling, Arni Brokenbrow). CR 613.4b sets base power in layer
# 7b; the toughness stays as it is, and the amount is taken once as the
# ability resolves (CR 608.2h).
# --------------------------------------------------------------------------


def _pt(scenario, creature):
    return scenario.game.computed_board().of(creature).power_toughness


def test_belligerent_yearling_takes_the_entering_dinosaurs_power():
    scenario = (
        Scenario()
        .player("alice", hand=["Orazca Frillback"], battlefield=["Belligerent Yearling"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    yearling = scenario.creature("Belligerent Yearling", "alice")
    printed = _pt(scenario, yearling)
    scenario.will_take_the_may(True, source="Belligerent Yearling")
    scenario.put_onto_battlefield("Orazca Frillback", "alice")
    scenario.pass_until_resolved()
    assert _pt(scenario, yearling) == (4, printed[1])


def test_belligerent_yearling_declined_keeps_its_printed_power():
    scenario = (
        Scenario()
        .player("alice", hand=["Orazca Frillback"], battlefield=["Belligerent Yearling"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    yearling = scenario.creature("Belligerent Yearling", "alice")
    printed = _pt(scenario, yearling)
    scenario.will_take_the_may(False, source="Belligerent Yearling")
    scenario.put_onto_battlefield("Orazca Frillback", "alice")
    scenario.pass_until_resolved()
    assert _pt(scenario, yearling) == printed


def test_belligerent_yearling_ignores_a_non_dinosaur():
    scenario = (
        Scenario()
        .player("alice", hand=["Hill Giant"], battlefield=["Belligerent Yearling"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    yearling = scenario.creature("Belligerent Yearling", "alice")
    printed = _pt(scenario, yearling)
    scenario.put_onto_battlefield("Hill Giant", "alice")
    scenario.pass_until_resolved()
    assert scenario.pending_triggers == []
    assert _pt(scenario, yearling) == printed


def _arni_boast(*others):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Arni Brokenbrow", "Mountain", *others])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    arni = scenario.creature("Arni Brokenbrow", "alice")
    arni.summoning_sick = False
    scenario.attack_with(arni)
    return scenario, arni


def test_arni_boast_sets_base_power_to_one_plus_the_greatest_other_power():
    scenario, arni = _arni_boast("Hill Giant", "Grizzly Bears")
    scenario.will_take_the_may(True, source="Arni Brokenbrow")
    scenario.activate(arni, *scenario.untapped_sources("Mountain"), index=0)
    scenario.resolve_top()
    assert _pt(scenario, arni)[0] == 4  # 1 + Hill Giant's 3


def test_arni_boast_ignores_arnis_own_power():
    scenario, arni = _arni_boast()
    scenario.will_take_the_may(True, source="Arni Brokenbrow")
    scenario.activate(arni, *scenario.untapped_sources("Mountain"), index=0)
    scenario.resolve_top()
    assert _pt(scenario, arni)[0] == 1  # 1 plus nothing (CR 107.2: 0)


# --------------------------------------------------------------------------
# Part 5 - "return to your hand the creature card in your graveyard with the
# greatest power; if two or more are tied, you choose one" (Desecrator Hag).
# CR 208.1 power; the controller's choice among ties is CR 608.2d's.
# --------------------------------------------------------------------------


def _hag(graveyard):
    scenario = (
        Scenario()
        .player("alice", hand=["Desecrator Hag"], graveyard=graveyard)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_desecrator_hag_returns_the_unique_greatest_power_creature():
    scenario = _hag(["Grizzly Bears", "Hill Giant", "Memnite"])
    scenario.put_onto_battlefield("Desecrator Hag", "alice")
    scenario.pass_until_resolved()
    hand = [c.name for c in scenario.player("alice").hand]
    assert hand == ["Hill Giant"]


def test_desecrator_hag_lets_the_controller_choose_among_tied_creatures():
    scenario = _hag(["Grizzly Bears", "Gray Ogre", "Memnite"])
    ogre = scenario.find("Gray Ogre", Zone.GRAVEYARD, "alice")
    scenario.will_choose_cards(ogre, source="Desecrator Hag")
    scenario.put_onto_battlefield("Desecrator Hag", "alice")
    scenario.pass_until_resolved()
    assert [c.name for c in scenario.player("alice").hand] == ["Gray Ogre"]
    assert "Grizzly Bears" in [c.name for c in scenario.player("alice").graveyard]


def test_desecrator_hag_ignores_noncreature_cards_with_a_graveyard_of_none():
    scenario = _hag(["Island"])
    scenario.put_onto_battlefield("Desecrator Hag", "alice")
    scenario.pass_until_resolved()
    assert scenario.player("alice").hand == []


# --------------------------------------------------------------------------
# Part 6 - "add mana equal to enchanted permanent's mana cost" (Elemental
# Resonance). CR 202.1: a mana cost is the symbols; the mana added matches
# them - generic as colorless (CR 107.4b), coloured as that colour, and for a
# hybrid symbol "choose one" of its colours (the card's own reminder).
# --------------------------------------------------------------------------


def _resonance(host_name, host_owner="alice"):
    from magic_cards_model.models import Color  # noqa: F401

    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Elemental Resonance"] + ([host_name] if host_owner == "alice" else []),
        )
        .player("bob", battlefield=[host_name] if host_owner == "bob" else [])
        .build()
    )
    scenario.start_at(Step.DRAW)
    aura = scenario.find("Elemental Resonance", Zone.BATTLEFIELD, "alice")
    aura.attach_to(scenario.find(host_name, Zone.BATTLEFIELD, host_owner))
    return scenario


def _floating(scenario):
    return {c.value: n for c, n in scenario.player("alice").mana_pool.floating.items() if n}


def test_elemental_resonance_adds_the_enchanted_permanents_mana_cost():
    scenario = _resonance("Grizzly Bears")
    scenario.advance()
    assert scenario.step is Step.PRECOMBAT_MAIN
    scenario.pass_until_resolved()
    assert _floating(scenario) == {"C": 1, "G": 1}


def test_elemental_resonance_lets_the_controller_choose_for_a_hybrid_symbol():
    scenario = _resonance("Desecrator Hag", "bob")
    scenario.will_choose("G", source="Elemental Resonance", times=2)
    scenario.advance()
    scenario.pass_until_resolved()
    assert _floating(scenario) == {"C": 2, "G": 2}


def test_elemental_resonance_on_a_land_adds_nothing():
    scenario = _resonance("Forest")
    scenario.advance()
    scenario.pass_until_resolved()
    assert _floating(scenario) == {}


# --------------------------------------------------------------------------
# Part 7 - "exile the top X cards ... / exile cards equal to <amount> from the
# top of <whose> library, then you may play / cast those cards" (Memorial
# Vault, Loot, Laughing Jasper Flint, Rakdos, Dead Man's Chest). CR 406.2
# exile; CR 601.3 the permission; CR 609.4b "mana of any type".
# --------------------------------------------------------------------------


def _permissions(scenario, player="alice"):
    return [p for p in scenario.game.play_permissions if p.player == player]


def test_loot_exiles_one_card_per_card_type_among_other_nonland_permanents():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Loot, the Key to Everything", "Grizzly Bears", "Sol Ring", "Forest"],
            library=["Island"] * 6,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.UNTAP)
    scenario.advance()
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").library) == 4  # creature + artifact; Loot and land excluded
    assert len(_permissions(scenario)) == 2


def test_loot_with_no_other_nonland_permanents_exiles_nothing():
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Loot, the Key to Everything", "Forest"], library=["Island"] * 3
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.UNTAP)
    scenario.advance()
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").library) == 3
    assert _permissions(scenario) == []


def _vault(sacrificed):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Memorial Vault", sacrificed], library=["Island"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vault = scenario.find("Memorial Vault", Zone.BATTLEFIELD)
    vault.summoning_sick = False
    scenario.activate(vault, index=0, sacrificing=[scenario.find(sacrificed, Zone.BATTLEFIELD)])
    scenario.resolve_top()
    return scenario


def test_memorial_vault_exiles_one_plus_the_sacrificed_artifacts_mana_value():
    scenario = _vault("Mind Stone")
    assert len(scenario.player("alice").library) == 3  # 1 + 2
    assert len(_permissions(scenario)) == 3


def test_memorial_vault_with_a_mana_value_one_artifact_exiles_two():
    scenario = _vault("Sol Ring")
    assert len(scenario.player("alice").library) == 4
    assert len(_permissions(scenario)) == 2


def test_laughing_jasper_flint_exiles_from_the_target_opponents_library_per_outlaw():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Laughing Jasper Flint"])
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.UNTAP)
    scenario.choose_trigger_targets("Laughing Jasper Flint", ["bob"])
    scenario.advance()
    scenario.pass_until_resolved()
    assert len(scenario.player("bob").library) == 4  # Jasper is the one outlaw
    permissions = _permissions(scenario)
    assert len(permissions) == 1 and permissions[0].any_type_mana


def test_rakdos_the_muscle_exiles_cards_equal_to_the_sacrificed_creatures_mana_value():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Rakdos, the Muscle", "Grizzly Bears"])
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rakdos = scenario.creature("Rakdos, the Muscle", "alice")
    rakdos.summoning_sick = False
    scenario.choose_trigger_targets("Rakdos, the Muscle", ["bob"])
    scenario.activate(rakdos, index=0, sacrificing=[scenario.creature("Grizzly Bears", "alice")])
    scenario.pass_until_resolved()
    assert len(scenario.player("bob").library) == 3  # Bears have mana value 2
    permissions = _permissions(scenario)
    assert len(permissions) == 2 and all(p.any_type_mana for p in permissions)


def test_dead_man_chests_exiles_cards_equal_to_the_dead_creatures_power():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Go for the Throat"], battlefield=["Dead Man's Chest", "Swamp", "Swamp"]
        )
        .player("bob", battlefield=["Hill Giant"], library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chest = scenario.find("Dead Man's Chest", Zone.BATTLEFIELD, "alice")
    giant = scenario.creature("Hill Giant", "bob")
    chest.attach_to(giant)
    scenario.cast_and_resolve(
        "Go for the Throat", *scenario.untapped_sources("Swamp", "Swamp"), targets=[giant]
    )
    scenario.pass_until_resolved()
    assert len(scenario.player("bob").library) == 3  # Hill Giant's power is 3
    permissions = _permissions(scenario)
    assert len(permissions) == 3 and all(p.any_type_mana for p in permissions)


# --------------------------------------------------------------------------
# Part 8 - amounts read off the cards a mill just moved (Heretic's
# Punishment, Combustible Gearhulk). CR 701.17a mills; CR 608.2c carries
# "the milled cards" into the next instruction; CR 202.3 mana value.
# --------------------------------------------------------------------------


def test_heretics_punishment_deals_damage_equal_to_the_greatest_milled_mana_value():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Heretic's Punishment"] + ["Mountain"] * 4,
            library=["Island", "Hill Giant", "Lightning Bolt", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    punishment = scenario.find("Heretic's Punishment", Zone.BATTLEFIELD)
    scenario.activate(
        punishment, *scenario.untapped_sources(*["Mountain"] * 4), index=0, targets=["bob"]
    )
    scenario.resolve_top()
    assert _graveyard(scenario, "alice") == 3
    assert scenario.player("bob").life == 16  # Hill Giant, mana value 4


def test_heretics_punishment_with_only_lands_milled_deals_no_damage():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Heretic's Punishment"] + ["Mountain"] * 4,
            library=["Island"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    punishment = scenario.find("Heretic's Punishment", Zone.BATTLEFIELD)
    scenario.activate(
        punishment, *scenario.untapped_sources(*["Mountain"] * 4), index=0, targets=["bob"]
    )
    scenario.resolve_top()
    assert scenario.player("bob").life == 20


def _gearhulk():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Combustible Gearhulk"],
            library=["Hill Giant", "Grizzly Bears", "Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Combustible Gearhulk", ["bob"])
    return scenario


def test_combustible_gearhulk_opponent_declines_so_alice_mills_and_bob_takes_the_total():
    scenario = _gearhulk()
    scenario.will_take_the_may(False, username="bob", source="Combustible Gearhulk")
    scenario.put_onto_battlefield("Combustible Gearhulk", "alice")
    scenario.pass_until_resolved()
    assert _graveyard(scenario, "alice") == 3
    assert scenario.player("bob").life == 14  # 4 + 2 + 0


def test_combustible_gearhulk_opponent_accepts_so_alice_draws_three():
    scenario = _gearhulk()
    scenario.will_take_the_may(True, username="bob", source="Combustible Gearhulk")
    scenario.put_onto_battlefield("Combustible Gearhulk", "alice")
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == 3
    assert scenario.player("bob").life == 20


# --------------------------------------------------------------------------
# Part 9 - "Target player mills X cards. If this spell was cast from a
# graveyard, that player mills twice that many cards instead." (Increasing
# Confusion). CR 107.3a X; CR 702.34a flashback casts from the graveyard.
# --------------------------------------------------------------------------


def _confusion(zone, x):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Increasing Confusion"] if zone is Zone.HAND else [],
            graveyard=["Increasing Confusion"] if zone is Zone.GRAVEYARD else [],
            battlefield=["Island"] * 6,
        )
        .player("bob", library=[SWAMP] * 12)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spell = scenario.find("Increasing Confusion", zone, "alice")
    scenario.game.cast(
        spell,
        "alice",
        x_value=x,
        targets=["bob"],
        mana_sources=scenario.untapped_sources(*["Island"] * (x + 1)),
        keyword="Flashback" if zone is Zone.GRAVEYARD else None,
    )
    while scenario.game.stack:
        scenario.resolve_top()
    return scenario


def test_increasing_confusion_cast_from_hand_mills_x():
    scenario = _confusion(Zone.HAND, 3)
    assert _graveyard(scenario, "bob") == 3


def test_increasing_confusion_flashed_back_mills_twice_x():
    scenario = _confusion(Zone.GRAVEYARD, 3)
    assert _graveyard(scenario, "bob") == 6


# --------------------------------------------------------------------------
# Part 10 - "At the beginning of each end step, enchanted player mills X
# cards, where X is the number of cards put into their graveyard from
# anywhere this turn." (Fraying Sanity). CR 303.4m enchanted player; the
# graveyard-arrival ledger is CR 400.6's.
# --------------------------------------------------------------------------


def _fraying(active="alice"):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Fraying Sanity", "Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears"], library=[SWAMP] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.find("Fraying Sanity", Zone.BATTLEFIELD, "alice").attach_to("bob")
    return scenario


def test_fraying_sanity_mills_the_enchanted_player_per_card_put_into_their_graveyard():
    scenario = _fraying()
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain"),
        targets=[scenario.creature("Grizzly Bears", "bob")],
    )
    before = _graveyard(scenario, "bob")
    assert before == 1
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()
    scenario.pass_until_resolved()
    assert _graveyard(scenario, "bob") == before + 1  # X was 1 as the trigger resolved


def test_fraying_sanity_with_nothing_put_into_a_graveyard_mills_nothing():
    scenario = _fraying()
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()
    scenario.pass_until_resolved()
    assert _graveyard(scenario, "bob") == 0


# --------------------------------------------------------------------------
# Part 3 - exile loops and discover amounts.
#
# CR 701.57a-c (discover, the "discovered card"), CR 406.2 (exile), CR 608.2h
# (an amount from the game state is fixed as the instruction applies),
# CR 111.10 (predefined tokens), CR 701.24a (shuffle) - each read with
# `mise run rules:find` in the session that wrote this block.
# --------------------------------------------------------------------------

LIGHTNING_BOLT = "Lightning Bolt"
FOREST = "Forest"


def _names(cards):
    return [card.name for card in cards]


def _treasures(scenario, name):
    return [c for c in scenario.game.permanents_controlled_by(name) if c.name == "Treasure Token"]


def test_hit_the_mother_lode_makes_tapped_treasures_for_the_shortfall():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Hit the Mother Lode"],
            battlefield=["Mountain"] * 7,
            library=[FOREST, LIGHTNING_BOLT, SWAMP],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, source="Hit the Mother Lode")
    scenario.cast_and_resolve("Hit the Mother Lode", *scenario.untapped_sources(*["Mountain"] * 7))
    assert LIGHTNING_BOLT in _names(scenario.player("alice").hand)
    treasures = _treasures(scenario, "alice")
    assert len(treasures) == 9  # 10 minus the discovered card's mana value 1
    assert all(treasure.tapped for treasure in treasures)


def test_hit_the_mother_lode_with_a_card_of_mana_value_ten_makes_no_treasure():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Hit the Mother Lode"],
            battlefield=["Mountain"] * 7,
            library=["Ulamog, the Defiler"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, source="Hit the Mother Lode")
    scenario.cast_and_resolve("Hit the Mother Lode", *scenario.untapped_sources(*["Mountain"] * 7))
    assert _treasures(scenario, "alice") == []


def test_hit_the_mother_lode_with_nothing_to_discover_makes_no_treasure():
    """CR 701.57c: with no card of mana value 10 or less there is no
    discovered card, so no difference to count."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Hit the Mother Lode"],
            battlefield=["Mountain"] * 7,
            library=[FOREST, FOREST],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Hit the Mother Lode", *scenario.untapped_sources(*["Mountain"] * 7))
    assert _treasures(scenario, "alice") == []


def test_zoyowas_justice_shuffles_the_target_away_then_its_owner_discovers_its_mana_value():
    scenario = (
        Scenario()
        .player("alice", hand=["Zoyowa's Justice"], battlefield=["Mountain", "Mountain"])
        .player("bob", battlefield=["Kitchen Finks"], library=[FOREST, FOREST, FOREST])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    finks = scenario.creature("Kitchen Finks", "bob")
    scenario.will_take_the_may(False, username="bob", source="Zoyowa's Justice")
    scenario.cast_and_resolve(
        "Zoyowa's Justice",
        *scenario.untapped_sources("Mountain", "Mountain"),
        targets=[finks],
    )
    assert "Kitchen Finks" not in scenario.battlefield_names()
    # The only nonland card in bob's shuffled library is the Finks itself,
    # mana value 3 = X, so bob discovered it into their hand.
    assert _names(scenario.player("bob").hand) == ["Kitchen Finks"]
    assert len(scenario.player("bob").library) == 3


def test_zoyowas_justice_discover_amount_is_the_last_known_mana_value():
    """X is 3 (Kitchen Finks), so the Bolt (1) is a hit if it comes first and
    the Finks (3) is a hit otherwise: either way exactly one nonland card ends
    in bob's hand and nothing is left on the battlefield."""
    scenario = (
        Scenario()
        .player("alice", hand=["Zoyowa's Justice"], battlefield=["Mountain", "Mountain"])
        .player("bob", battlefield=["Kitchen Finks"], library=[LIGHTNING_BOLT, FOREST])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, username="bob", source="Zoyowa's Justice")
    scenario.cast_and_resolve(
        "Zoyowa's Justice",
        *scenario.untapped_sources("Mountain", "Mountain"),
        targets=[scenario.creature("Kitchen Finks", "bob")],
    )
    assert len(scenario.player("bob").hand) == 1
    assert "Kitchen Finks" not in scenario.battlefield_names()


def test_rally_the_horde_repeats_while_the_last_exiled_card_is_not_a_land():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Rally the Horde"],
            battlefield=["Mountain"] * 6,
            library=[
                LIGHTNING_BOLT, FOREST, LIGHTNING_BOLT,  # last is a nonland: repeat
                LIGHTNING_BOLT, LIGHTNING_BOLT, FOREST,  # last is a land: stop
                SWAMP,
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Rally the Horde", *scenario.untapped_sources(*["Mountain"] * 6))
    warriors = [c for c in scenario.game.permanents_controlled_by("alice") if c.name == "Warrior Token"]
    assert len(warriors) == 4  # four nonland cards exiled
    assert len(scenario.player("alice").library) == 1
    assert len(scenario.game.exile) == 6


def test_rally_the_horde_stops_when_the_library_runs_out():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Rally the Horde"],
            battlefield=["Mountain"] * 6,
            library=[LIGHTNING_BOLT, LIGHTNING_BOLT],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Rally the Horde", *scenario.untapped_sources(*["Mountain"] * 6))
    warriors = [c for c in scenario.game.permanents_controlled_by("alice") if c.name == "Warrior Token"]
    assert len(warriors) == 2


def test_demonlord_belzenlok_puts_nonland_cards_in_hand_and_repeats_on_mana_value_four():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Demonlord Belzenlok"],
            battlefield=["Swamp"] * 6,
            library=[FOREST, "Serra Angel", FOREST, LIGHTNING_BOLT, SWAMP],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Demonlord Belzenlok", *scenario.untapped_sources(*["Swamp"] * 6))
    _settle(scenario)
    assert sorted(_names(scenario.player("alice").hand)) == ["Lightning Bolt", "Serra Angel"]
    assert scenario.player("alice").life == 18  # one damage per card put into hand
    assert _names(scenario.game.exile) == [FOREST, FOREST]


def test_demonlord_belzenlok_stops_after_a_cheap_card():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Demonlord Belzenlok"],
            battlefield=["Swamp"] * 6,
            library=[LIGHTNING_BOLT, "Serra Angel"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Demonlord Belzenlok", *scenario.untapped_sources(*["Swamp"] * 6))
    _settle(scenario)
    assert _names(scenario.player("alice").hand) == ["Lightning Bolt"]
    assert scenario.player("alice").life == 19
