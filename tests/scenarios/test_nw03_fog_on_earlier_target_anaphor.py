"""Scenario: a spell's prevent-all fog bound to its own earlier target by an
anaphor - "Prevent all [combat] damage that would be dealt to it / that
creature this turn [by `<sources>`]." after a gets/gains/counter/untap rider,
and Enshrouding Mist's trailing "If it's renowned, untap it."

Readers: `machines/effects/damage.py`'s
`_parse_prevent_all_damage_to_spell_anaphor_clause` (one clause, read only
on a spell) and `_parse_fog_on_spell_anaphor_then_state_rider_clauses`.

Rules, each read in full with `mise run rules:find`:

- CR 608.2c - the controller "follows its instructions in the order written
  ... read the whole text and apply the rules of English to the text": "it"
  and "that creature" are the spell's target.
- CR 608.2b - a target that is no longer legal is not affected; a spell
  whose every target is illegal does not resolve.
- CR 615.1a - prevention effects; CR 615.6 - prevented damage never happens.
- CR 609.7b - "by colorless sources" is rechecked as the damage is dealt.
- CR 105.2c - "A colorless object has no color."
- CR 510.2 / "combat damage" - Fleeting Flight's shield leaves noncombat
  damage alone.
- CR 702.112b - renowned is a designation of the permanent, read on
  resolution.
- CR 702.9a - flying (Leap of Faith's and Fleeting Flight's grant).
- CR 400.7 - the shield names the object, not a later one.

Listed printings: Leap of Faith, Lithomancer's Focus, Enshrouding Mist,
Fleeting Flight.

Proof printing (not listed, not in any api deck, legal in Modern and
Pioneer): Djeru's Resolve ("Untap target creature." before the anaphor fog).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

LISTED = ("Leap of Faith", "Lithomancer's Focus", "Enshrouding Mist", "Fleeting Flight")
PROOF = ("Djeru's Resolve",)


@pytest.mark.parametrize("name", LISTED + PROOF)
def test_every_listed_and_proof_card_reads_handled(name):
    outcomes = {clause.outcome for clause in card_support(card(name)).clauses}
    assert outcomes == {"handled"}, name


def _board(*, alice_battlefield=(), bob_battlefield=(), alice_hand=(), bob_hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=[*["Plains"] * 6, *alice_battlefield],
            library=["Plains"] * 8,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=[*["Mountain"] * 6, *bob_battlefield],
            library=["Mountain"] * 8,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario, name, *, username="alice", targets=None):
    if scenario.priority_holder != username:
        scenario.pass_priority(scenario.priority_holder)
    return scenario.cast_and_resolve(name, username=username, targets=targets, auto=True)


# -- Leap of Faith: "that creature" after a gains rider --------------------------


def test_leap_of_faith_gives_flying_and_shields_only_its_target():
    scenario = _board(
        alice_hand=["Leap of Faith"],
        alice_battlefield=["Grizzly Bears", "Savannah Lions"],
        bob_hand=["Lightning Bolt", "Shock"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "alice")
    _cast(scenario, "Leap of Faith", targets=[bears])
    assert has_keyword(bears, "flying", scenario.game)

    _cast(scenario, "Lightning Bolt", username="bob", targets=[bears])
    _cast(scenario, "Shock", username="bob", targets=[lions])

    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0
    assert lions.zone is Zone.GRAVEYARD


def test_leap_of_faith_shield_covers_combat_damage_to_its_target():
    scenario = _board(
        alice_hand=["Leap of Faith"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Serra Angel"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    _cast(scenario, "Leap of Faith", targets=[bears])

    scenario.attack_with(bears, defending="bob")
    scenario.block(bears, angel)  # the flying Angel can block the flying Bears
    scenario.combat_damage()

    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0
    assert angel.damage == 2  # damage *by* the target is not prevented


def test_leap_of_faith_shield_names_its_target_object():
    scenario = _board(alice_hand=["Leap of Faith"], alice_battlefield=["Savannah Lions"])
    lions = scenario.creature("Savannah Lions", "alice")
    _cast(scenario, "Leap of Faith", targets=[lions])
    shields = scenario.game.active_prevention_shields()
    assert [shield.card_id for shield in shields] == [lions.id]


# -- Lithomancer's Focus: "that creature ... by colorless sources" -----------------


def test_lithomancers_focus_prevents_colorless_damage_to_its_target_only():
    scenario = _board(
        alice_hand=["Lithomancer's Focus"],
        alice_battlefield=["Grizzly Bears", "Savannah Lions"],
        bob_battlefield=["Walking Ballista"],
    )
    ballista = scenario.creature("Walking Ballista", "bob")
    ballista.add_counters("+1/+1", 3)
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "alice")
    _cast(scenario, "Lithomancer's Focus", targets=[bears])
    assert scenario.game.power_of(bears) == 4

    for target in (bears, lions):
        if scenario.priority_holder != "bob":
            scenario.pass_priority(scenario.priority_holder)
        scenario.activate(ballista, index=1, username="bob", targets=[target])
        scenario.pass_until_resolved()

    assert bears.damage == 0
    assert lions.zone is Zone.GRAVEYARD  # 1 colorless damage to the 2/1 is dealt


def test_lithomancers_focus_lets_colored_damage_through():
    scenario = _board(
        alice_hand=["Lithomancer's Focus"],
        alice_battlefield=["Grizzly Bears"],
        bob_hand=["Lightning Bolt"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast(scenario, "Lithomancer's Focus", targets=[bears])

    _cast(scenario, "Lightning Bolt", username="bob", targets=[bears])

    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 3  # a 4/4 now


def test_lithomancers_focus_covers_a_colorless_creatures_combat_damage():
    scenario = _board(
        alice_hand=["Lithomancer's Focus"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Frogmite"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    frogmite = scenario.creature("Frogmite", "bob")
    _cast(scenario, "Lithomancer's Focus", targets=[bears])

    scenario.attack_with(bears, defending="bob")
    scenario.block(bears, frogmite)
    scenario.combat_damage()

    assert bears.damage == 0
    assert frogmite.zone is Zone.GRAVEYARD


# -- Enshrouding Mist: "to it", then "If it's renowned, untap it." -----------------


def _tapped_bears(scenario):
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.tapped = True
    return bears


def test_enshrouding_mist_pumps_and_shields_and_leaves_an_unrenowned_target_tapped():
    scenario = _board(
        alice_hand=["Enshrouding Mist"],
        alice_battlefield=["Grizzly Bears"],
        bob_hand=["Lightning Bolt"],
    )
    bears = _tapped_bears(scenario)
    _cast(scenario, "Enshrouding Mist", targets=[bears])
    assert scenario.game.power_of(bears) == 3
    assert bears.tapped

    _cast(scenario, "Lightning Bolt", username="bob", targets=[bears])

    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0


def test_enshrouding_mist_untaps_a_renowned_target():
    scenario = _board(alice_hand=["Enshrouding Mist"], alice_battlefield=["Grizzly Bears"])
    bears = _tapped_bears(scenario)
    bears.renowned = True
    _cast(scenario, "Enshrouding Mist", targets=[bears])

    assert not bears.tapped
    assert scenario.game.active_prevention_shields()


def test_enshrouding_mist_checks_renown_of_its_target_not_another_creature():
    scenario = _board(
        alice_hand=["Enshrouding Mist"],
        alice_battlefield=["Grizzly Bears", "Savannah Lions"],
    )
    bears = _tapped_bears(scenario)
    lions = scenario.creature("Savannah Lions", "alice")
    lions.renowned = True
    lions.tapped = True
    _cast(scenario, "Enshrouding Mist", targets=[bears])

    assert bears.tapped and lions.tapped


# -- Fleeting Flight: counter, flying, combat-only "to it" -------------------------


def test_fleeting_flight_counter_flying_and_combat_shield():
    scenario = _board(
        alice_hand=["Fleeting Flight"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Serra Angel"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    _cast(scenario, "Fleeting Flight", targets=[bears])
    assert bears.counters["+1/+1"] == 1
    assert has_keyword(bears, "flying", scenario.game)

    scenario.attack_with(bears, defending="bob")
    scenario.block(bears, angel)
    scenario.combat_damage()

    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0
    assert angel.damage == 3


def test_fleeting_flight_does_not_prevent_noncombat_damage():
    scenario = _board(
        alice_hand=["Fleeting Flight"],
        alice_battlefield=["Grizzly Bears"],
        bob_hand=["Lightning Bolt"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast(scenario, "Fleeting Flight", targets=[bears])

    _cast(scenario, "Lightning Bolt", username="bob", targets=[bears])

    assert bears.zone is Zone.GRAVEYARD  # 3 to a 3/3


# -- Djeru's Resolve: "to it" after an untap ---------------------------------------


def test_djerus_resolve_untaps_and_shields_its_target():
    scenario = _board(
        alice_hand=["Djeru's Resolve"],
        alice_battlefield=["Grizzly Bears", "Savannah Lions"],
        bob_hand=["Lightning Bolt", "Shock"],
    )
    bears = _tapped_bears(scenario)
    lions = scenario.creature("Savannah Lions", "alice")
    _cast(scenario, "Djeru's Resolve", targets=[bears])
    assert not bears.tapped

    _cast(scenario, "Lightning Bolt", username="bob", targets=[bears])
    _cast(scenario, "Shock", username="bob", targets=[lions])

    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0
    assert lions.zone is Zone.GRAVEYARD


def test_djerus_resolve_on_an_opponents_creature_shields_it_too():
    scenario = _board(
        alice_hand=["Djeru's Resolve"],
        bob_battlefield=["Savannah Lions"],
        bob_hand=["Lightning Bolt"],
    )
    lions = scenario.creature("Savannah Lions", "bob")
    _cast(scenario, "Djeru's Resolve", targets=[lions])

    _cast(scenario, "Lightning Bolt", username="bob", targets=[lions])

    assert lions.zone is Zone.BATTLEFIELD and lions.damage == 0


def test_djerus_resolve_whose_target_left_does_nothing():
    scenario = _board(
        alice_hand=["Djeru's Resolve"],
        alice_battlefield=["Grizzly Bears"],
        bob_hand=["Lightning Bolt"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_onto_stack("Djeru's Resolve", username="alice", targets=[bears], auto=True)
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Lightning Bolt", username="bob", targets=[bears], auto=True)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert not scenario.game.active_prevention_shields()  # CR 608.2b
