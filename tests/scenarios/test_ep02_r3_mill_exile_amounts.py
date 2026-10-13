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
    scenario.cast_and_resolve(
        "Cut Down", *scenario.untapped_sources(SWAMP), targets=[bears]
    )
    assert "Grizzly Bears" not in scenario.battlefield_names()


def test_cut_down_total_exactly_five_is_legal():
    scenario = _cut_down_board("Kird Ape", "Forest")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ape = scenario.creature("Kird Ape", "bob")
    scenario.cast_and_resolve(
        "Cut Down", *scenario.untapped_sources(SWAMP), targets=[ape]
    )
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
        .player("alice", battlefield=["Elemental Resonance"] + ([host_name] if host_owner == "alice" else []))
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
