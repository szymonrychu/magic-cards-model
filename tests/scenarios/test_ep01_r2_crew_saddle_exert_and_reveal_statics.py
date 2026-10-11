"""Crew, saddle and station contribution statics, exert as it attacks, and the
"play with ... revealed" / "look at face-down" statics (EP-01 round 2, T8).

Rules read whole with `mise run rules:find` in the session that wrote this:

- **CR 702.122a** - "Crew N" means "Tap any number of other untapped creatures
  you control with total power N or greater: This permanent becomes an artifact
  creature until end of turn."
- **CR 702.171a** - "Saddle N" is the same cost for "This permanent becomes
  saddled until end of turn. Activate only as a sorcery."
- **CR 702.184a** - Station puts charge counters equal to the tapped creature's
  power.
- **CR 701.43d / CR 508.1g** - "You may exert this creature as it attacks."
- **CR 400.2** - public zones; a revealed hand / top card is known to everyone.

"Cloudspire Captain", "Deathless Pilot", "Dynamite Diver" (power 2 greater for
saddle and crew), "Hotshot Mechanic" (crew only), "Interface Ace" (toughness for
both), "Giant Ox" (crew toughness) and "Tapestry Warden" (station toughness) are
the printings under test.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import (
    crew_activation,
    saddle_activation,
    station_activation,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _board(alice, *, bob=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=list(alice), library=["Plains"] * 5)
        .player("bob", battlefield=list(bob), library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _pay(activation):
    refusal = activation.why_not()
    if refusal is not None:
        raise ValueError(refusal)
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()


def _resolve_all(scenario):
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()


def _crew(scenario, vehicle, *creatures):
    _pay(crew_activation(scenario.game, vehicle, list(creatures), "alice"))
    _resolve_all(scenario)


def _saddle(scenario, mount, *creatures):
    _pay(saddle_activation(scenario.game, mount, list(creatures), "alice"))
    _resolve_all(scenario)


# ---- crew ------------------------------------------------------------------


def test_a_creature_that_crews_as_though_its_power_were_two_greater_counts_four():
    """Hotshot Mechanic is 2/1: power 2 + 2 = 4, so it plus a 2/2 crews Crew 6."""
    scenario = _board(["Consulate Dreadnought", "Hotshot Mechanic", "Grizzly Bears"])
    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD)
    _crew(
        scenario,
        vehicle,
        scenario.creature("Hotshot Mechanic", "alice"),
        scenario.creature("Grizzly Bears", "alice"),
    )
    assert "creature" in {t.value.lower() for t in scenario.game.characteristics_of(vehicle).types}


def test_the_two_greater_bonus_alone_still_falls_short_of_a_bigger_crew_number():
    scenario = _board(["Consulate Dreadnought", "Hotshot Mechanic"])
    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD)
    mechanic = scenario.creature("Hotshot Mechanic", "alice")
    with pytest.raises(ValueError, match="702.122a"):
        _crew(scenario, vehicle, mechanic)
    assert not mechanic.tapped


def test_using_its_toughness_rather_than_its_power_crews_with_toughness():
    """Giant Ox is 0/6: it alone crews Crew 6 and is not counted as power 0."""
    scenario = _board(["Consulate Dreadnought", "Giant Ox"])
    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD)
    _crew(scenario, vehicle, scenario.creature("Giant Ox", "alice"))
    assert "creature" in {t.value.lower() for t in scenario.game.characteristics_of(vehicle).types}


def test_interface_ace_crews_with_toughness_and_a_plain_creature_adds_its_power():
    """Interface Ace is 0/4: 4 + a Grizzly Bears' 2 = 6, and 4 alone is short."""
    scenario = _board(["Consulate Dreadnought", "Interface Ace", "Grizzly Bears"])
    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD)
    ace = scenario.creature("Interface Ace", "alice")
    with pytest.raises(ValueError, match="702.122a"):
        _crew(scenario, vehicle, ace)
    _crew(scenario, vehicle, ace, scenario.creature("Grizzly Bears", "alice"))
    assert "creature" in {t.value.lower() for t in scenario.game.characteristics_of(vehicle).types}


def test_a_creature_without_the_line_still_crews_with_its_plain_power():
    scenario = _board(["Consulate Dreadnought", "Grizzly Bears", "Grizzly Bears", "Grizzly Bears"])
    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD)
    bears = [c for c in scenario.game.battlefield if c.name == "Grizzly Bears"]
    assert len(bears) == 3
    with pytest.raises(ValueError, match="702.122a"):
        _crew(scenario, vehicle, *bears[:2])
    _crew(scenario, vehicle, *bears)


# ---- saddle ----------------------------------------------------------------


def test_cloudspire_captain_saddles_a_saddle_four_mount_alone():
    """Cloudspire Captain is 2/3: 2 + 2 = 4 reaches Guardian Sunmare's Saddle 4."""
    scenario = _board(["Guardian Sunmare", "Cloudspire Captain"])
    mount = scenario.find("Guardian Sunmare", Zone.BATTLEFIELD)
    _saddle(scenario, mount, scenario.creature("Cloudspire Captain", "alice"))
    assert mount.saddled


def test_deathless_pilot_and_dynamite_diver_add_two_to_their_power_for_saddle():
    scenario = _board(["Guardian Sunmare", "Dynamite Diver", "Deathless Pilot"])
    mount = scenario.find("Guardian Sunmare", Zone.BATTLEFIELD)
    diver = scenario.creature("Dynamite Diver", "alice")
    with pytest.raises(ValueError, match="702.171a"):
        _saddle(scenario, mount, diver)
    _saddle(scenario, mount, diver, scenario.creature("Deathless Pilot", "alice"))
    assert mount.saddled


def test_a_crew_only_bonus_does_not_count_for_saddle():
    """Hotshot Mechanic crews as though its power were 2 greater, but saddles with
    its plain 2: Saddle 4 is out of reach for it alone."""
    scenario = _board(["Guardian Sunmare", "Hotshot Mechanic"])
    mount = scenario.find("Guardian Sunmare", Zone.BATTLEFIELD)
    with pytest.raises(ValueError, match="702.171a"):
        _saddle(scenario, mount, scenario.creature("Hotshot Mechanic", "alice"))
    assert not mount.saddled


def test_interface_ace_saddles_using_its_toughness():
    scenario = _board(["Guardian Sunmare", "Interface Ace"])
    mount = scenario.find("Guardian Sunmare", Zone.BATTLEFIELD)
    _saddle(scenario, mount, scenario.creature("Interface Ace", "alice"))
    assert mount.saddled


def test_a_crew_only_toughness_line_does_not_count_for_saddle():
    scenario = _board(["Guardian Sunmare", "Giant Ox"])
    mount = scenario.find("Guardian Sunmare", Zone.BATTLEFIELD)
    with pytest.raises(ValueError, match="702.171a"):
        _saddle(scenario, mount, scenario.creature("Giant Ox", "alice"))


# ---- station ---------------------------------------------------------------


def _station(scenario, spacecraft, tapped):
    activation = station_activation(scenario.game, spacecraft, tapped, "alice")
    _pay(activation)
    scenario.pass_until_resolved()


def test_station_uses_toughness_for_a_creature_with_toughness_greater_than_power():
    """Tapestry Warden: Giant Ox (0/6) stations for 6, not 0."""
    scenario = _board(["Extinguisher Battleship", "Tapestry Warden", "Giant Ox"])
    ship = scenario.find("Extinguisher Battleship", Zone.BATTLEFIELD)
    _station(scenario, ship, scenario.creature("Giant Ox", "alice"))
    assert ship.counters[Counter.CHARGE] == 6


def test_station_keeps_power_when_toughness_is_not_greater():
    scenario = _board(["Extinguisher Battleship", "Tapestry Warden", "Grizzly Bears"])
    ship = scenario.find("Extinguisher Battleship", Zone.BATTLEFIELD)
    _station(scenario, ship, scenario.creature("Grizzly Bears", "alice"))
    assert ship.counters[Counter.CHARGE] == 2


def test_station_without_the_warden_uses_plain_power():
    scenario = _board(["Extinguisher Battleship", "Giant Ox"])
    ship = scenario.find("Extinguisher Battleship", Zone.BATTLEFIELD)
    _station(scenario, ship, scenario.creature("Giant Ox", "alice"))
    assert ship.counters[Counter.CHARGE] == 0


def test_an_opponents_warden_does_not_change_my_stationing():
    scenario = _board(["Extinguisher Battleship", "Giant Ox"], bob=["Tapestry Warden"])
    ship = scenario.find("Extinguisher Battleship", Zone.BATTLEFIELD)
    _station(scenario, ship, scenario.creature("Giant Ox", "alice"))
    assert ship.counters[Counter.CHARGE] == 0


# ---- revealed hands and top cards, face-down looks, surveil (CR 400.2, 701.20a) ----


def _known_names(scenario, viewer):
    return sorted(k.card_name for k in scenario.game.known_to(viewer))


def _reveal_board(alice=(), bob=(), alice_hand=("Lightning Bolt",), bob_hand=("Shock",)):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=list(alice),
            hand=list(alice_hand),
            library=["Plains", "Island", "Swamp", "Forest", "Mountain"],
        )
        .player(
            "bob",
            battlefield=list(bob),
            hand=list(bob_hand),
            library=["Forest", "Swamp", "Island", "Plains", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_telepathy_reveals_only_my_opponents_hands():
    scenario = _reveal_board(alice=["Telepathy"])
    assert "Shock" in _known_names(scenario, "alice")
    assert "Lightning Bolt" not in _known_names(scenario, "bob")


def test_zurs_weirding_reveals_both_hands_to_both_players():
    scenario = _reveal_board(alice=["Zur's Weirding"])
    assert {"Shock", "Lightning Bolt"} <= set(_known_names(scenario, "alice"))
    assert {"Shock", "Lightning Bolt"} <= set(_known_names(scenario, "bob"))


def test_a_hand_stays_hidden_without_the_static():
    scenario = _reveal_board()
    assert "Shock" not in _known_names(scenario, "alice")


def test_telepathy_stops_revealing_when_it_leaves_play():
    scenario = _reveal_board(alice=["Telepathy"])
    telepathy = scenario.find("Telepathy", Zone.BATTLEFIELD)
    scenario.game.put_into_graveyard(telepathy)
    assert "Shock" not in _known_names(scenario, "alice")


def test_lantern_of_insight_reveals_every_players_top_card():
    scenario = _reveal_board(alice=["Lantern of Insight"])
    for viewer in ("alice", "bob"):
        names = _known_names(scenario, viewer)
        assert scenario.game.player("alice").library[0].name in names
        assert scenario.game.player("bob").library[0].name in names


def test_wizened_snitches_reveals_the_tops_too_and_it_tracks_the_draw():
    scenario = _reveal_board(alice=["Wizened Snitches"])
    bob_top = scenario.game.player("bob").library[0]
    assert any(k.card_id == bob_top.id for k in scenario.game.known_to("alice"))
    scenario.game.draw_cards("bob", 1)
    assert not any(
        k.card_id == bob_top.id and k.zone is Zone.LIBRARY for k in scenario.game.known_to("alice")
    )
    assert any(
        k.card_id == scenario.game.player("bob").library[0].id
        for k in scenario.game.known_to("alice")
    )


def test_the_top_card_is_hidden_without_the_static():
    scenario = _reveal_board()
    top = scenario.game.player("bob").library[0]
    assert not any(k.card_id == top.id for k in scenario.game.known_to("alice"))


def test_found_footage_lets_me_look_at_an_opponents_face_down_creature():
    scenario = _reveal_board(alice=["Found Footage"], bob=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.turn_face_down()
    assert any(k.card_id == bears.id for k in scenario.game.known_to("alice"))
    assert not any(
        k.card_id == bears.id
        for k in scenario.game.known_to("bob")
        if k.source and "face-down" in k.source
    )


def test_keeper_of_the_lens_reads_the_same_and_ignores_face_up_creatures():
    scenario = _reveal_board(alice=["Keeper of the Lens"], bob=["Grizzly Bears", "Memnite"])
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.turn_face_down()
    known = {k.card_id for k in scenario.game.known_to("alice")}
    assert bears.id in known
    assert scenario.creature("Memnite", "bob").id not in known


def test_my_own_face_down_creature_is_not_opened_by_the_look():
    scenario = _reveal_board(alice=["Found Footage", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.turn_face_down()
    assert not any(
        k.card_id == bears.id and k.source and "face-down" in k.source
        for k in scenario.game.known_to("alice")
    )


def test_enhanced_surveillance_shows_two_more_cards_when_surveilling():
    scenario = _reveal_board(alice=["Enhanced Surveillance"])
    scenario.surveil_keeping_everything_on_top()
    scenario.game.surveil("alice", 1)
    asked = [d for d in scenario.questions_asked() if d.kind.value == "surveil"]
    assert len(asked[-1].cards) == 3


def test_surveil_shows_only_n_cards_without_it():
    scenario = _reveal_board()
    scenario.surveil_keeping_everything_on_top()
    scenario.game.surveil("alice", 1)
    asked = [d for d in scenario.questions_asked() if d.kind.value == "surveil"]
    assert len(asked[-1].cards) == 1
