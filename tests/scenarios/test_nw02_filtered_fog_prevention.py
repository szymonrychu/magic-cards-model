"""Scenario: "Prevent all [combat] damage that would be dealt [to <who>] [by
<which sources>] this turn." - the filtered fog, and the Ferocious fog that
picks one of two such shields as it resolves.

One reader family (`machines/effects/damage.py`), one shield model
(`PreventionShield` with a persisted `ShieldSourceFilter` and a recipient
filter), every shape created on resolution and lasting "this turn".

Rules, each read in full with `mise run rules:find`:

- CR 615.1a - "Effects that use the word "prevent" are prevention effects.
  Prevention effects use "prevent" to indicate what damage will not be
  dealt."
- CR 609.7b - "Some effects from resolved spells and abilities prevent or
  replace damage from sources with certain properties, such as a creature or a
  source of a particular color. When the source would deal damage, the
  "shield" rechecks the source's properties. If the properties no longer
  match, the damage isn't prevented or replaced."
- CR 514.2 - the cleanup step ends every "this turn" effect.
- CR 207.2c - an ability word (Ferocious) has no rules meaning of its own.
- CR 614.1a - "Effects that use the word "instead" are replacement effects."
  Winds of Qal Sisma's "instead" replaces its first instruction with its
  second as the spell resolves, if the condition holds then.

Listed printings: Commencement of Festivities, Defend the Hearth, Azorius
Ploy, Harmless Assault, Hunter's Ambush, Hindervines, Tanglesap, Vine Snare,
Terrifying Presence, Encircling Fissure (its Awaken half is
`test_nw02_awaken.py`'s), Winds of Qal Sisma.

Proof printings (not listed, not in any api deck, legal in Modern/Pioneer):
Riot Control (recipient "you", after a life-gain sentence), Shielded Passage
(recipient "target creature", all damage), Fog of War (source power, a
different N, after a life-gain sentence), Thwart the Enemy (sources "your
opponents control", all damage, noncombat included).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

LISTED = (
    "Commencement of Festivities",
    "Defend the Hearth",
    "Azorius Ploy",
    "Harmless Assault",
    "Hunter's Ambush",
    "Hindervines",
    "Tanglesap",
    "Vine Snare",
    "Terrifying Presence",
    "Encircling Fissure",
    "Winds of Qal Sisma",
)
PROOF = ("Riot Control", "Shielded Passage", "Fog of War", "Thwart the Enemy")


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
            battlefield=[*["Forest"] * 5, *["Plains"] * 5, *["Island"] * 2, *alice_battlefield],
            library=["Forest"] * 8,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=[*["Mountain"] * 3, *["Plains"] * 3, *bob_battlefield],
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


def _mine(scenario, name, username="alice"):
    return [
        permanent
        for permanent in scenario.game.permanents_controlled_by(username)
        if permanent.name == name
    ]


# -- recipients: players, you, target creature --------------------------------


@pytest.mark.parametrize("fog", ["Commencement of Festivities", "Defend the Hearth"])
def test_combat_damage_to_players_is_prevented_but_creatures_still_take_it(fog):
    scenario = _board(
        alice_hand=[fog],
        alice_battlefield=["Hill Giant", "Grizzly Bears"],
        bob_battlefield=["Savannah Lions"],
    )
    _cast(scenario, fog)
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "bob")

    scenario.attack_with(giant, bears, defending="bob")
    scenario.block(bears, lions)
    scenario.combat_damage()

    assert scenario.player("bob").life == 20  # the unblocked Giant's 3 to a player
    assert lions.zone is Zone.GRAVEYARD  # creature-to-creature combat damage is dealt
    assert bears.zone is Zone.GRAVEYARD


def test_to_players_covers_combat_damage_only():
    scenario = _board(alice_hand=["Defend the Hearth"], bob_hand=["Lightning Bolt"])
    _cast(scenario, "Defend the Hearth")

    _cast(scenario, "Lightning Bolt", username="bob", targets=["alice"])

    assert scenario.player("alice").life == 17


def test_the_players_shield_ends_with_the_turn():
    scenario = _board(alice_hand=["Commencement of Festivities"], bob_battlefield=["Hill Giant"])
    _cast(scenario, "Commencement of Festivities")
    active = scenario.turn.active_player
    while scenario.turn.active_player == active:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")

    scenario.attack_with(giant, defending="alice")
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("alice").life == 17


def test_riot_control_gains_then_prevents_all_damage_to_you_only():
    scenario = _board(
        alice_hand=["Riot Control"],
        bob_hand=["Lightning Bolt", "Shock"],
        bob_battlefield=["Grizzly Bears", "Hill Giant"],
    )
    _cast(scenario, "Riot Control")
    assert scenario.player("alice").life == 22  # one life per opposing creature

    _cast(scenario, "Lightning Bolt", username="bob", targets=["alice"])
    _cast(scenario, "Shock", username="bob", targets=["bob"])

    assert scenario.player("alice").life == 22  # noncombat damage to "you" is prevented
    assert scenario.player("bob").life == 18  # the caster's opponent is not "you"


def test_azorius_ploy_shields_two_different_targets_one_way_each():
    scenario = _board(
        alice_hand=["Azorius Ploy"],
        alice_battlefield=["Hill Giant", "Grizzly Bears"],
        bob_battlefield=["Craw Wurm", "Savannah Lions"],
    )
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    lions = scenario.creature("Savannah Lions", "bob")
    # First target: the creature whose combat damage is prevented; second: the
    # creature combat damage to which is prevented (CR 601.2c's text order).
    _cast(scenario, "Azorius Ploy", targets=[wurm, giant])

    scenario.attack_with(giant, bears, defending="bob")
    scenario.block(giant, wurm)
    scenario.block(bears, lions)
    scenario.combat_damage()

    assert giant.zone is Zone.BATTLEFIELD and giant.damage == 0  # both halves on one fight
    assert wurm.damage == 3  # the Giant is neither the first target nor shielded from
    assert bears.zone is Zone.GRAVEYARD  # neither target: Lions' damage is dealt
    assert lions.zone is Zone.GRAVEYARD


def test_azorius_ploy_halves_are_independent():
    scenario = _board(
        alice_hand=["Azorius Ploy"],
        alice_battlefield=["Hill Giant", "Grizzly Bears"],
        bob_battlefield=["Craw Wurm", "Savannah Lions"],
    )
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    lions = scenario.creature("Savannah Lions", "bob")
    # The Lions deal no combat damage; nothing is dealt to the Bears.
    _cast(scenario, "Azorius Ploy", targets=[lions, bears])

    scenario.attack_with(giant, bears, defending="bob")
    scenario.block(giant, wurm)
    scenario.block(bears, lions)
    scenario.combat_damage()

    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0
    assert lions.zone is Zone.GRAVEYARD  # the Bears' 2 to the Lions is not prevented
    assert giant.zone is Zone.GRAVEYARD  # the Wurm is neither target
    assert wurm.damage == 3


def test_shielded_passage_prevents_noncombat_damage_to_its_target():
    scenario = _board(
        alice_hand=["Shielded Passage"],
        alice_battlefield=["Grizzly Bears", "Savannah Lions"],
        bob_hand=["Lightning Bolt", "Shock"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "alice")
    _cast(scenario, "Shielded Passage", targets=[bears])

    _cast(scenario, "Lightning Bolt", username="bob", targets=[bears])
    _cast(scenario, "Shock", username="bob", targets=[lions])

    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0
    assert lions.zone is Zone.GRAVEYARD


# -- source filters, rechecked as the damage would be dealt (CR 609.7b) ---------


def test_harmless_assault_stops_attackers_but_not_blockers():
    scenario = _board(
        alice_hand=["Harmless Assault"],
        alice_battlefield=["Hill Giant", "Grizzly Bears"],
        bob_battlefield=["Craw Wurm"],
    )
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    _cast(scenario, "Harmless Assault")

    scenario.attack_with(giant, bears, defending="bob")
    scenario.block(giant, wurm)
    scenario.combat_damage()

    assert scenario.player("bob").life == 20
    assert wurm.damage == 0
    assert giant.zone is Zone.GRAVEYARD  # the blocking Wurm is not attacking


def test_hunters_ambush_spares_green_sources_only():
    scenario = _board(
        alice_hand=["Hunter's Ambush"],
        alice_battlefield=["Grizzly Bears", "Hill Giant", "Savannah Lions"],
    )
    _cast(scenario, "Hunter's Ambush")
    attackers = [scenario.creature(name, "alice") for name in ("Grizzly Bears", "Hill Giant")]
    attackers.append(scenario.creature("Savannah Lions", "alice"))

    scenario.attack_with(*attackers, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 18  # only the green Bears' 2


def test_hunters_ambush_does_not_touch_noncombat_damage():
    scenario = _board(alice_hand=["Hunter's Ambush"], bob_hand=["Lightning Bolt"])
    _cast(scenario, "Hunter's Ambush")

    _cast(scenario, "Lightning Bolt", username="bob", targets=["alice"])

    assert scenario.player("alice").life == 17


def test_hindervines_rechecks_counters_as_damage_is_dealt():
    scenario = _board(
        alice_hand=["Hindervines"],
        alice_battlefield=["Grizzly Bears", "Hill Giant", "Savannah Lions"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    lions = scenario.creature("Savannah Lions", "alice")
    scenario.game.add_counters(bears, "+1/+1", 1)
    _cast(scenario, "Hindervines")
    # A counter put on after resolution still counts (CR 609.7b).
    scenario.game.add_counters(lions, "+1/+1", 1)

    scenario.attack_with(bears, giant, lions, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 20 - 3 - 3  # Bears 3, Lions 3, Giant prevented


def test_tanglesap_lets_trample_through():
    scenario = _board(
        alice_hand=["Tanglesap"],
        alice_battlefield=["Colossal Dreadmaw", "Hill Giant"],
    )
    _cast(scenario, "Tanglesap")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "alice")
    giant = scenario.creature("Hill Giant", "alice")

    scenario.attack_with(dreadmaw, giant, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 14  # the Dreadmaw's 6 only


def test_vine_snare_rechecks_power_as_damage_is_dealt():
    scenario = _board(
        alice_hand=["Vine Snare", "Giant Growth"],
        alice_battlefield=["Craw Wurm", "Hill Giant", "Grizzly Bears"],
    )
    _cast(scenario, "Vine Snare")
    wurm = scenario.creature("Craw Wurm", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    # The Giant grows to 6 after the shield exists: no longer power 4 or less.
    _cast(scenario, "Giant Growth", targets=[giant])

    scenario.attack_with(wurm, giant, bears, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 20 - 6 - 6


def test_fog_of_war_gains_then_prevents_by_power_three_or_less():
    scenario = _board(
        alice_hand=["Fog of War"],
        alice_battlefield=["Hill Giant", "Nessian Asp"],
        bob_battlefield=["Grizzly Bears"],
    )
    _cast(scenario, "Fog of War")
    assert scenario.player("alice").life == 23  # three creatures on the battlefield
    giant = scenario.creature("Hill Giant", "alice")
    asp = scenario.creature("Nessian Asp", "alice")

    scenario.attack_with(giant, asp, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 16  # the Asp's 4; the Giant's 3 prevented


def test_terrifying_presence_spares_only_its_target():
    scenario = _board(
        alice_hand=["Terrifying Presence"],
        alice_battlefield=["Hill Giant", "Grizzly Bears"],
        bob_battlefield=["Savannah Lions"],
    )
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "bob")
    _cast(scenario, "Terrifying Presence", targets=[giant])

    scenario.attack_with(giant, bears, defending="bob")
    scenario.block(bears, lions)
    scenario.combat_damage()

    assert scenario.player("bob").life == 17  # the target's own 3 is dealt
    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0
    assert lions.zone is Zone.BATTLEFIELD and lions.damage == 0


def test_encircling_fissure_shields_against_the_target_opponents_creatures():
    scenario = _board(
        bob_hand=["Encircling Fissure"],
        alice_battlefield=["Hill Giant", "Grizzly Bears"],
        bob_battlefield=["Craw Wurm"],
    )
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    wurm = scenario.creature("Craw Wurm", "bob")

    scenario.attack_with(giant, bears, defending="bob")
    scenario.block(giant, wurm)
    _cast(scenario, "Encircling Fissure", username="bob", targets=["alice"])
    scenario.combat_damage()

    assert scenario.player("bob").life == 20
    assert wurm.damage == 0
    assert giant.zone is Zone.GRAVEYARD  # bob's own Wurm is not covered


def test_thwart_the_enemy_prevents_noncombat_damage_from_opposing_creatures():
    scenario = _board(
        alice_hand=["Thwart the Enemy"],
        bob_battlefield=["Walking Ballista", "Grizzly Bears"],
        alice_battlefield=["Hill Giant"],
    )
    ballista = scenario.creature("Walking Ballista", "bob")
    scenario.game.add_counters(ballista, "+1/+1", 2)
    giant = scenario.creature("Hill Giant", "alice")
    _cast(scenario, "Thwart the Enemy")

    scenario.pass_priority("alice")
    scenario.activate(ballista, index=1, username="bob", targets=["alice"])
    scenario.resolve_top()

    assert scenario.player("alice").life == 20
    scenario.attack_with(giant, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    assert scenario.player("bob").life == 17  # alice's own creature is not an opponent's


# -- Winds of Qal Sisma: one shield or the other, chosen on resolution ---------


def test_winds_without_ferocious_prevents_all_combat_damage():
    scenario = _board(
        alice_hand=["Winds of Qal Sisma"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Savannah Lions"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "bob")
    _cast(scenario, "Winds of Qal Sisma")

    scenario.attack_with(bears, defending="bob")
    scenario.block(bears, lions)
    scenario.combat_damage()

    assert bears.damage == 0 and lions.damage == 0


def test_winds_with_ferocious_prevents_only_the_opponents_creatures_damage():
    scenario = _board(
        alice_hand=["Winds of Qal Sisma"],
        alice_battlefield=["Nessian Asp", "Grizzly Bears"],
        bob_battlefield=["Savannah Lions"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "bob")
    _cast(scenario, "Winds of Qal Sisma")

    scenario.attack_with(bears, defending="bob")
    scenario.block(bears, lions)
    scenario.combat_damage()

    assert bears.damage == 0  # the Lions are bob's
    assert lions.zone is Zone.GRAVEYARD  # alice's Bears are not covered


def test_winds_ferocious_is_checked_on_resolution_not_later():
    scenario = _board(
        alice_hand=["Winds of Qal Sisma", "Giant Growth"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Savannah Lions"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "bob")
    _cast(scenario, "Winds of Qal Sisma")  # no power-4 creature now: the plain fog
    _cast(scenario, "Giant Growth", targets=[bears])  # 5/5 afterwards changes nothing

    scenario.attack_with(bears, defending="bob")
    scenario.block(bears, lions)
    scenario.combat_damage()

    assert lions.zone is Zone.BATTLEFIELD and lions.damage == 0
