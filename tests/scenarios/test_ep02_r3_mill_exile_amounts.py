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
