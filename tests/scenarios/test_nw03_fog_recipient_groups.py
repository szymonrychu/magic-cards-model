"""Scenario: the prevent-all fog's recipient groups - "to creatures", "to
artifact creatures", "to creatures you control", "to you and permanents you
control", "to you and creatures you control", "to up to two target
creatures" and "to target <qualified> creature".

One reader family (`machines/effects/damage.py`'s `_FogSpec`), one shield
model (`PreventionShield` with `recipient_types`/`recipient_controller` beside
the older `and_permanents_of`), every shape created on resolution and lasting
"this turn".

Rules, each read in full with `mise run rules:find`:

- CR 615.1a - "Effects that use the word "prevent" are prevention effects.
  Prevention effects use "prevent" to indicate what damage will not be
  dealt."
- CR 615.6 - "If damage that would be dealt is prevented, it never happens."
- CR 615.5 - a prevention effect's additional effect (Channel Harm's "deal
  that much damage") "takes place immediately afterward".
- CR 615.12 - unpreventable damage still meets the shield, which prevents
  nothing.
- CR 611.2a - the stated duration ("this turn") is how long the shield lasts.
- CR 120.1 - damage is dealt to battles, creatures, planeswalkers and players:
  "permanents you control" reaches a planeswalker, "creatures you control"
  does not.
- CR 601.2c - "up to two" announces how many targets; CR 608.2b - an illegal
  target is not affected, the legal one still is.
- CR 608.2d - Channel Harm's "you may" is chosen as the damage is prevented.
- CR 702.11b - Blinding Fog's second sentence (hexproof) keeps working.

Listed printings: Forfend, Blinding Fog, Endure, Safe Passage, Redeem (and
Eerie Interference's recipient half; its source half is in
`test_nw03_fog_source_filters.py`).

Proof printings (not listed, not in any api deck, legal in Modern or
Pioneer): Ethersworn Shieldmage ("to artifact creatures", an enters
trigger), Channel Harm ("to you and permanents you control ... by sources you
don't control" with its CR 615.5 rider), Godtoucher and Kitsune Healer
("to target <qualified> creature", activated abilities).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

LISTED = ("Forfend", "Blinding Fog", "Endure", "Safe Passage", "Redeem", "Eerie Interference")
PROOF = ("Ethersworn Shieldmage", "Channel Harm", "Godtoucher", "Kitsune Healer")


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
            battlefield=[
                *["Forest"] * 4,
                *["Plains"] * 6,
                *["Island"] * 2,
                *["Mountain"] * 2,
                *alice_battlefield,
            ],
            library=["Forest"] * 8,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=[*["Mountain"] * 4, *["Plains"] * 3, *bob_battlefield],
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


# -- "to creatures" (Forfend, Blinding Fog) -------------------------------------


@pytest.mark.parametrize("fog", ["Forfend", "Blinding Fog"])
def test_to_creatures_covers_every_creature_but_no_player(fog):
    scenario = _board(
        alice_hand=[fog],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Savannah Lions"],
        bob_hand=["Lightning Bolt", "Shock"],
    )
    _cast(scenario, fog)
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "bob")

    _cast(scenario, "Lightning Bolt", username="bob", targets=[lions])
    _cast(scenario, "Shock", username="bob", targets=["alice"])

    assert lions.zone is Zone.BATTLEFIELD and lions.damage == 0
    assert scenario.player("alice").life == 18  # players are not "creatures"

    scenario.attack_with(bears, defending="bob")
    scenario.block(bears, lions)
    scenario.combat_damage()
    assert bears.damage == 0 and lions.damage == 0  # the opponent's creatures too


def test_to_creatures_lets_combat_damage_to_a_player_through():
    scenario = _board(alice_hand=["Forfend"], alice_battlefield=["Hill Giant"])
    _cast(scenario, "Forfend")
    giant = scenario.creature("Hill Giant", "alice")

    scenario.attack_with(giant, defending="bob")
    scenario.combat_damage()

    assert scenario.player("bob").life == 17


def test_to_creatures_covers_a_creature_that_arrives_after_resolution():
    scenario = _board(alice_hand=["Forfend", "Grizzly Bears"], bob_hand=["Lightning Bolt"])
    _cast(scenario, "Forfend")
    _cast(scenario, "Grizzly Bears")
    bears = scenario.creature("Grizzly Bears", "alice")

    _cast(scenario, "Lightning Bolt", username="bob", targets=[bears])

    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0


def test_to_creatures_does_not_undo_damage_already_dealt():
    scenario = _board(alice_hand=["Forfend"], alice_battlefield=["Hill Giant"], bob_hand=["Shock"])
    giant = scenario.creature("Hill Giant", "alice")
    _cast(scenario, "Shock", username="bob", targets=[giant])
    assert giant.damage == 2

    _cast(scenario, "Forfend")

    assert giant.damage == 2  # CR 615.6: a shield never reaches back


def test_to_creatures_ends_with_the_turn():
    scenario = _board(alice_hand=["Forfend"], bob_battlefield=["Hill Giant"])
    _cast(scenario, "Forfend")
    assert scenario.game.active_prevention_shields()
    active = scenario.turn.active_player
    while scenario.turn.active_player == active:
        scenario.advance()

    assert not scenario.game.active_prevention_shields()


def test_blinding_fog_also_grants_your_creatures_hexproof():
    scenario = _board(
        alice_hand=["Blinding Fog"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Savannah Lions"],
        bob_hand=["Lightning Bolt"],
    )
    _cast(scenario, "Blinding Fog")
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "bob")

    with pytest.raises(ValueError, match="hexproof"):
        _cast(scenario, "Lightning Bolt", username="bob", targets=[bears])
    _cast(scenario, "Lightning Bolt", username="bob", targets=[lions])  # not hexproof
    assert lions.zone is Zone.BATTLEFIELD and lions.damage == 0


# -- "to artifact creatures" (Ethersworn Shieldmage, an enters trigger) ----------


def test_shieldmage_shields_artifact_creatures_only():
    scenario = _board(
        alice_hand=["Ethersworn Shieldmage"],
        alice_battlefield=["Frogmite", "Grizzly Bears"],
        bob_hand=["Lightning Bolt", "Shock"],
    )
    _cast(scenario, "Ethersworn Shieldmage")
    scenario.pass_until_resolved()
    frogmite = scenario.creature("Frogmite", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    _cast(scenario, "Lightning Bolt", username="bob", targets=[frogmite])
    _cast(scenario, "Shock", username="bob", targets=[bears])

    assert frogmite.zone is Zone.BATTLEFIELD and frogmite.damage == 0
    assert bears.zone is Zone.GRAVEYARD  # a nonartifact creature is not covered


def test_shieldmage_shields_itself_and_not_its_controller():
    scenario = _board(alice_hand=["Ethersworn Shieldmage"], bob_hand=["Lightning Bolt", "Shock"])
    _cast(scenario, "Ethersworn Shieldmage")
    scenario.pass_until_resolved()
    mage = scenario.creature("Ethersworn Shieldmage", "alice")

    _cast(scenario, "Lightning Bolt", username="bob", targets=[mage])
    _cast(scenario, "Shock", username="bob", targets=["alice"])

    assert mage.zone is Zone.BATTLEFIELD and mage.damage == 0
    assert scenario.player("alice").life == 18


# -- "to you and permanents you control" / "to you and creatures you control" ----


def test_endure_covers_you_your_creatures_and_your_planeswalkers():
    scenario = _board(
        alice_hand=["Endure"],
        alice_battlefield=["Grizzly Bears", "Jace Beleren"],
        bob_battlefield=["Savannah Lions"],
        bob_hand=["Lightning Bolt", "Shock", "Incinerate"],
    )
    _cast(scenario, "Endure")
    bears = scenario.creature("Grizzly Bears", "alice")
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "alice")
    loyalty = jace.loyalty

    _cast(scenario, "Lightning Bolt", username="bob", targets=["alice"])
    _cast(scenario, "Shock", username="bob", targets=[bears])
    _cast(scenario, "Incinerate", username="bob", targets=[jace])

    assert scenario.player("alice").life == 20
    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0
    assert jace.zone is Zone.BATTLEFIELD and jace.loyalty == loyalty


def test_endure_does_not_cover_the_opponent_or_their_permanents():
    scenario = _board(
        alice_hand=["Endure", "Lightning Bolt"],
        bob_battlefield=["Savannah Lions"],
        bob_hand=["Shock"],
    )
    _cast(scenario, "Endure")
    lions = scenario.creature("Savannah Lions", "bob")

    _cast(scenario, "Lightning Bolt", targets=[lions])
    _cast(scenario, "Shock", username="bob", targets=["bob"])

    assert lions.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 18


def test_endure_reads_control_as_the_damage_is_dealt():
    scenario = _board(
        alice_hand=["Endure", "Act of Treason"],
        bob_battlefield=["Savannah Lions"],
        bob_hand=["Lightning Bolt"],
    )
    lions = scenario.creature("Savannah Lions", "bob")
    _cast(scenario, "Endure")
    _cast(scenario, "Act of Treason", targets=[lions])
    assert scenario.game.controller_of(lions).username == "alice"

    _cast(scenario, "Lightning Bolt", username="bob", targets=[lions])

    assert lions.zone is Zone.BATTLEFIELD and lions.damage == 0  # alice's now


def test_safe_passage_covers_you_and_your_creatures_but_not_your_planeswalkers():
    scenario = _board(
        alice_hand=["Safe Passage"],
        alice_battlefield=["Grizzly Bears", "Jace Beleren"],
        bob_hand=["Lightning Bolt", "Shock", "Incinerate"],
    )
    _cast(scenario, "Safe Passage")
    bears = scenario.creature("Grizzly Bears", "alice")
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "alice")

    _cast(scenario, "Lightning Bolt", username="bob", targets=["alice"])
    _cast(scenario, "Shock", username="bob", targets=[bears])
    _cast(scenario, "Incinerate", username="bob", targets=[jace])

    assert scenario.player("alice").life == 20
    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0
    assert jace.zone is Zone.GRAVEYARD  # a planeswalker is not a creature


def test_safe_passage_stops_combat_damage_to_you_and_your_blockers():
    scenario = _board(
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Hill Giant", "Craw Wurm"],
        alice_hand=["Safe Passage"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    wurm = scenario.creature("Craw Wurm", "bob")
    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    while scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()
    _cast(scenario, "Safe Passage")

    scenario.attack_with(giant, wurm, defending="alice")
    scenario.block(wurm, bears)
    scenario.combat_damage()

    assert scenario.player("alice").life == 20
    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0
    assert wurm.damage == 2  # the Bears' own damage to the attacker is dealt


def test_eerie_interference_covers_you_and_your_creatures_from_creatures():
    scenario = _board(
        alice_hand=["Eerie Interference"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Walking Ballista"],
        bob_hand=["Shock"],
    )
    ballista = scenario.creature("Walking Ballista", "bob")
    ballista.add_counters("+1/+1", 3)  # survives both activations
    _cast(scenario, "Eerie Interference")
    bears = scenario.creature("Grizzly Bears", "alice")

    for target in (bears, "alice"):
        if scenario.priority_holder != "bob":
            scenario.pass_priority(scenario.priority_holder)
        scenario.activate(ballista, index=1, username="bob", targets=[target])
        scenario.pass_until_resolved()
    _cast(scenario, "Shock", username="bob", targets=["alice"])

    assert bears.damage == 0  # a creature's noncombat damage, prevented
    assert scenario.player("alice").life == 18  # only the Shock (not a creature) lands


# -- "to up to two target creatures" (Redeem) -----------------------------------


def test_redeem_shields_both_of_its_targets_and_nothing_else():
    scenario = _board(
        alice_hand=["Redeem"],
        alice_battlefield=["Grizzly Bears", "Savannah Lions", "Elite Vanguard"],
        bob_hand=["Lightning Bolt", "Shock", "Incinerate"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "alice")
    vanguard = scenario.creature("Elite Vanguard", "alice")
    _cast(scenario, "Redeem", targets=[bears, lions])

    _cast(scenario, "Lightning Bolt", username="bob", targets=[bears])
    _cast(scenario, "Shock", username="bob", targets=[lions])
    _cast(scenario, "Incinerate", username="bob", targets=[vanguard])

    assert bears.zone is Zone.BATTLEFIELD and lions.zone is Zone.BATTLEFIELD
    assert vanguard.zone is Zone.GRAVEYARD


def test_redeem_with_one_target_shields_that_one():
    scenario = _board(
        alice_hand=["Redeem"],
        alice_battlefield=["Grizzly Bears", "Savannah Lions"],
        bob_hand=["Lightning Bolt", "Shock"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "alice")
    _cast(scenario, "Redeem", targets=[bears])

    _cast(scenario, "Lightning Bolt", username="bob", targets=[bears])
    _cast(scenario, "Shock", username="bob", targets=[lions])

    assert bears.zone is Zone.BATTLEFIELD
    assert lions.zone is Zone.GRAVEYARD


def test_redeem_with_no_targets_resolves_and_shields_nothing():
    scenario = _board(
        alice_hand=["Redeem"], alice_battlefield=["Grizzly Bears"], bob_hand=["Shock"]
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast(scenario, "Redeem", targets=[])
    assert scenario.find("Redeem", Zone.GRAVEYARD, "alice") is not None

    _cast(scenario, "Shock", username="bob", targets=[bears])

    assert bears.zone is Zone.GRAVEYARD


def test_redeem_skips_a_target_that_became_illegal():
    scenario = _board(
        alice_hand=["Redeem"],
        alice_battlefield=["Grizzly Bears", "Savannah Lions"],
        bob_hand=["Lightning Bolt", "Shock"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "alice")
    scenario.cast_onto_stack("Redeem", username="alice", targets=[bears, lions], auto=True)
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Lightning Bolt", username="bob", targets=[lions], auto=True)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert lions.zone is Zone.GRAVEYARD
    assert scenario.game.active_prevention_shields()

    _cast(scenario, "Shock", username="bob", targets=[bears])

    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0


# -- "to target <qualified> creature" (Godtoucher, Kitsune Healer) ----------------


def test_godtoucher_shields_its_power_five_target():
    scenario = _board(alice_battlefield=["Godtoucher", "Craw Wurm"], bob_hand=["Lightning Bolt"])
    godtoucher = scenario.creature("Godtoucher", "alice")
    wurm = scenario.creature("Craw Wurm", "alice")
    scenario.activate(godtoucher, targets=[wurm], auto=True)
    scenario.pass_until_resolved()

    _cast(scenario, "Lightning Bolt", username="bob", targets=[wurm])
    scenario.attack_with(wurm, defending="bob")
    scenario.combat_damage()

    assert wurm.damage == 0
    assert scenario.player("bob").life == 14  # the shield covers damage to it, not by it


def test_kitsune_healer_shields_a_legendary_creature():
    scenario = _board(
        alice_battlefield=["Kitsune Healer", "Isamaru, Hound of Konda"],
        bob_hand=["Lightning Bolt", "Shock"],
    )
    healer = scenario.creature("Kitsune Healer", "alice")
    isamaru = scenario.creature("Isamaru, Hound of Konda", "alice")
    scenario.activate(healer, index=1, targets=[isamaru], auto=True)
    scenario.pass_until_resolved()

    _cast(scenario, "Lightning Bolt", username="bob", targets=[isamaru])
    _cast(scenario, "Shock", username="bob", targets=[healer])

    assert isamaru.zone is Zone.BATTLEFIELD and isamaru.damage == 0
    assert healer.zone is Zone.GRAVEYARD


# -- Channel Harm: you and permanents you control, by sources you don't control ---


def test_channel_harm_prevents_and_may_redirect_the_amount_to_its_target():
    scenario = _board(
        alice_hand=["Channel Harm"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Craw Wurm"],
        bob_hand=["Lightning Bolt", "Shock"],
    )
    wurm = scenario.creature("Craw Wurm", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast(scenario, "Channel Harm", targets=[wurm])
    scenario.will_take_the_may(times=None, username="alice")

    _cast(scenario, "Lightning Bolt", username="bob", targets=["alice"])
    assert scenario.player("alice").life == 20
    assert wurm.damage == 3  # CR 615.5: that much, immediately afterward

    _cast(scenario, "Shock", username="bob", targets=[bears])
    assert bears.damage == 0
    assert wurm.zone is Zone.GRAVEYARD  # 3 + 2 on a 6/4


def test_channel_harm_declined_prevents_without_redirecting():
    scenario = _board(
        alice_hand=["Channel Harm"],
        bob_battlefield=["Craw Wurm"],
        bob_hand=["Lightning Bolt"],
    )
    wurm = scenario.creature("Craw Wurm", "bob")
    _cast(scenario, "Channel Harm", targets=[wurm])
    scenario.will_take_the_may(False, username="alice")

    _cast(scenario, "Lightning Bolt", username="bob", targets=["alice"])

    assert scenario.player("alice").life == 20
    assert wurm.damage == 0


def test_channel_harm_does_not_cover_damage_from_your_own_sources():
    scenario = _board(
        alice_hand=["Channel Harm", "Shock"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Craw Wurm"],
    )
    wurm = scenario.creature("Craw Wurm", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast(scenario, "Channel Harm", targets=[wurm])

    _cast(scenario, "Shock", targets=[bears])

    assert bears.zone is Zone.GRAVEYARD
    assert wurm.damage == 0
