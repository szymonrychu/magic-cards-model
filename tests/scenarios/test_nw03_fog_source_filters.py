"""Scenario: the prevent-all fog's source filters - "by creatures" beside a
recipient, "that creatures would deal to players", "that `<colour>` sources
and `<colour>` sources would deal", "by non-`<subtype>` sources" and "that
other creatures would deal".

One reader family (`machines/effects/damage.py`'s `_FogSpec`), one persisted
filter (`ShieldSourceFilter`, now also reading noncreature sources:
`creatures`, `colors_any`, `colorless`, `not_controlled_by`), rechecked as each
damage event would be dealt.

Rules, each read in full with `mise run rules:find`:

- CR 615.1a - "Effects that use the word "prevent" are prevention effects."
- CR 609.7b - "When the source would deal damage, the "shield" rechecks the
  source's properties. If the properties no longer match, the damage isn't
  prevented or replaced."
- CR 615.6 - prevented damage never happens.
- CR 611.2a - the shield lasts as long as stated: "this turn".
- CR 105.2c - "A colorless object has no color."
- CR 400.7 - a Haze Frog that leaves and returns is a new object, no longer
  the "other" its shield spared.

Listed printings: Chameleon Blur, Luminesce, Repel the Abominable, Eerie
Interference (its recipient half is in `test_nw03_fog_recipient_groups.py`).

Proof printings (not listed, not in any api deck, legal in Modern or
Pioneer): Surge of Salvation ("that black and/or red sources would deal to
creatures you control", after a hexproof sentence), Haze Frog ("that other
creatures would deal", an enters trigger).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

LISTED = ("Chameleon Blur", "Luminesce", "Repel the Abominable", "Eerie Interference")
PROOF = ("Surge of Salvation", "Haze Frog")


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
                *["Forest"] * 5,
                *["Plains"] * 4,
                *["Mountain"] * 2,
                *["Swamp"] * 2,
                *alice_battlefield,
            ],
            library=["Forest"] * 8,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=[
                *["Mountain"] * 4,
                *["Swamp"] * 2,
                *["Plains"] * 2,
                *["Forest"] * 2,
                *bob_battlefield,
            ],
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


def _ping(scenario, ballista, target):
    if scenario.priority_holder != "bob":
        scenario.pass_priority(scenario.priority_holder)
    scenario.activate(ballista, index=1, username="bob", targets=[target])
    scenario.pass_until_resolved()


# -- "that creatures would deal to players" (Chameleon Blur) -------------------


def test_chameleon_blur_stops_creature_damage_to_players_only():
    scenario = _board(
        alice_hand=["Chameleon Blur"],
        alice_battlefield=["Hill Giant", "Grizzly Bears"],
        bob_battlefield=["Savannah Lions"],
    )
    _cast(scenario, "Chameleon Blur")
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "bob")

    scenario.attack_with(giant, bears, defending="bob")
    scenario.block(bears, lions)
    scenario.combat_damage()

    assert scenario.player("bob").life == 20
    assert lions.zone is Zone.GRAVEYARD and bears.zone is Zone.GRAVEYARD


def test_chameleon_blur_covers_a_creatures_noncombat_damage_to_a_player():
    scenario = _board(alice_hand=["Chameleon Blur"], bob_battlefield=["Walking Ballista"])
    ballista = scenario.creature("Walking Ballista", "bob")
    ballista.add_counters("+1/+1", 2)
    _cast(scenario, "Chameleon Blur")

    _ping(scenario, ballista, "alice")

    assert scenario.player("alice").life == 20


def test_chameleon_blur_does_not_cover_a_noncreature_source():
    scenario = _board(alice_hand=["Chameleon Blur"], bob_hand=["Lightning Bolt"])
    _cast(scenario, "Chameleon Blur")

    _cast(scenario, "Lightning Bolt", username="bob", targets=["alice"])

    assert scenario.player("alice").life == 17


# -- "by creatures" beside a recipient (Eerie Interference) ----------------------


def test_eerie_interference_lets_noncreature_damage_through():
    scenario = _board(
        alice_hand=["Eerie Interference"],
        alice_battlefield=["Grizzly Bears"],
        bob_hand=["Lightning Bolt"],
    )
    _cast(scenario, "Eerie Interference")
    bears = scenario.creature("Grizzly Bears", "alice")

    _cast(scenario, "Lightning Bolt", username="bob", targets=[bears])

    assert bears.zone is Zone.GRAVEYARD


def test_eerie_interference_does_not_shield_the_opponents_creatures():
    scenario = _board(
        alice_hand=["Eerie Interference"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Savannah Lions"],
    )
    _cast(scenario, "Eerie Interference")
    giant = scenario.creature("Hill Giant", "alice")
    lions = scenario.creature("Savannah Lions", "bob")

    scenario.attack_with(giant, defending="bob")
    scenario.block(giant, lions)
    scenario.combat_damage()

    assert giant.damage == 0  # creature damage to your creature
    assert lions.zone is Zone.GRAVEYARD  # creature damage to theirs is dealt


# -- "that black sources and red sources would deal" (Luminesce) ----------------


def test_luminesce_prevents_red_and_black_sources_of_any_kind():
    scenario = _board(
        alice_hand=["Luminesce", "Blightning"],
        alice_battlefield=["Grizzly Bears"],
        bob_hand=["Lightning Bolt"],
    )
    _cast(scenario, "Luminesce")
    bears = scenario.creature("Grizzly Bears", "alice")

    _cast(scenario, "Lightning Bolt", username="bob", targets=[bears])
    _cast(scenario, "Blightning", targets=["bob"])

    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0
    assert scenario.player("bob").life == 20  # black-and-red Blightning, its caster's own too


def test_luminesce_covers_a_black_creatures_combat_damage_but_not_a_green_ones():
    scenario = _board(
        alice_hand=["Luminesce"],
        alice_battlefield=["Vampire Nighthawk", "Grizzly Bears"],
        bob_battlefield=["Savannah Lions"],
    )
    _cast(scenario, "Luminesce")
    nighthawk = scenario.creature("Vampire Nighthawk", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.attack_with(nighthawk, bears, defending="bob")
    scenario.combat_damage()

    assert scenario.player("bob").life == 18  # only the green Bears' 2
    assert scenario.player("alice").life == 20  # no lifelink: nothing was dealt


def test_luminesce_covers_a_source_with_red_among_other_colours():
    scenario = _board(alice_hand=["Luminesce"], bob_hand=["Lightning Helix"])
    _cast(scenario, "Luminesce")

    _cast(scenario, "Lightning Helix", username="bob", targets=["alice"])

    assert scenario.player("alice").life == 20  # red and white: it is red
    assert scenario.player("bob").life == 23  # the life gain is not damage


# -- "by non-Human sources" (Repel the Abominable) --------------------------------


def test_repel_the_abominable_spares_humans_only():
    scenario = _board(
        alice_hand=["Repel the Abominable"],
        alice_battlefield=["Elite Vanguard", "Grizzly Bears"],
    )
    _cast(scenario, "Repel the Abominable")
    vanguard = scenario.creature("Elite Vanguard", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.attack_with(vanguard, bears, defending="bob")
    scenario.combat_damage()

    assert scenario.player("bob").life == 18  # the Human's 2 is dealt, the Bear's is not


def test_repel_the_abominable_covers_a_noncreature_source():
    scenario = _board(
        alice_hand=["Repel the Abominable"],
        alice_battlefield=["Elite Vanguard"],
        bob_hand=["Lightning Bolt"],
    )
    _cast(scenario, "Repel the Abominable")
    vanguard = scenario.creature("Elite Vanguard", "alice")

    _cast(scenario, "Lightning Bolt", username="bob", targets=[vanguard])

    assert vanguard.zone is Zone.BATTLEFIELD and vanguard.damage == 0


# -- Surge of Salvation: "black and/or red sources ... to creatures you control" ---


def test_surge_shields_your_creatures_from_red_sources():
    scenario = _board(
        alice_hand=["Surge of Salvation", "Shock"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Savannah Lions"],
        bob_hand=["Lightning Bolt"],
    )
    _cast(scenario, "Surge of Salvation")
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "bob")

    _cast(scenario, "Shock", targets=[lions])
    assert lions.zone is Zone.GRAVEYARD  # not a creature you control

    with pytest.raises(ValueError, match="hexproof"):
        scenario.pass_priority(scenario.priority_holder)
        scenario.cast_onto_stack("Lightning Bolt", username="bob", targets=[bears], auto=True)
    assert bears.damage == 0


def test_surge_spares_damage_from_a_green_creature():
    scenario = _board(
        alice_hand=["Surge of Salvation"],
        alice_battlefield=["Savannah Lions", "Elite Vanguard"],
        bob_battlefield=["Grizzly Bears", "Black Knight"],
    )
    lions = scenario.creature("Savannah Lions", "alice")
    vanguard = scenario.creature("Elite Vanguard", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    knight = scenario.creature("Black Knight", "bob")
    _cast(scenario, "Surge of Salvation")

    scenario.attack_with(lions, vanguard, defending="bob")
    scenario.block(lions, bears)
    scenario.block(vanguard, knight)
    scenario.combat_damage()

    assert lions.zone is Zone.GRAVEYARD  # the green Bears' damage is dealt
    assert vanguard.zone is Zone.BATTLEFIELD and vanguard.damage == 0  # black Knight's is not


# -- Haze Frog: "that other creatures would deal" ---------------------------------


def test_haze_frog_stops_every_other_creatures_combat_damage():
    scenario = _board(
        alice_hand=["Haze Frog"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Craw Wurm"],
    )
    _cast(scenario, "Haze Frog")
    scenario.pass_until_resolved()
    giant = scenario.creature("Hill Giant", "alice")
    wurm = scenario.creature("Craw Wurm", "bob")

    scenario.attack_with(giant, defending="bob")
    scenario.block(giant, wurm)
    scenario.combat_damage()

    assert giant.zone is Zone.BATTLEFIELD and giant.damage == 0
    assert wurm.damage == 0


def test_haze_frog_does_not_stop_its_own_combat_damage():
    scenario = _board(alice_battlefield=["Haze Frog"], bob_hand=["Haze Frog"])
    frog = scenario.creature("Haze Frog", "alice")
    _cast(scenario, "Haze Frog", username="bob")
    scenario.pass_until_resolved()

    scenario.attack_with(frog, defending="bob")
    scenario.combat_damage()

    assert scenario.player("bob").life == 20  # bob's Frog spares only itself


def test_haze_frog_prevents_combat_damage_only():
    scenario = _board(alice_hand=["Haze Frog"], bob_battlefield=["Walking Ballista"])
    ballista = scenario.creature("Walking Ballista", "bob")
    ballista.add_counters("+1/+1", 2)
    _cast(scenario, "Haze Frog")
    scenario.pass_until_resolved()

    _ping(scenario, ballista, "alice")

    assert scenario.player("alice").life == 19
