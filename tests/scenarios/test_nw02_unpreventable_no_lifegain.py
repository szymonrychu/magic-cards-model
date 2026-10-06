"""Scenario: "<this spell> deals N damage to <target>. The damage can't be
prevented. [If that player or that planeswalker's controller would gain life
this turn, that player gains no life instead.]"

Rules, each read in full with `mise run rules:find`:

- CR 615.12 - "Some effects state that damage "can't be prevented." If
  unpreventable damage would be dealt, any applicable prevention effects are
  still applied to it. Those effects won't prevent any damage ... Existing
  damage prevention shields won't be reduced by damage that can't be
  prevented." "The damage" is this spell's own damage only - not every
  damage this turn.
- CR 614.1a - "Effects that use the word "instead" are replacement effects."
- CR 119.10 - "Some replacement effects are written, "If [a player] would
  gain life, . . . ." Such abilities are treated as though they are written,
  "If a source would cause [a player] to gain life, . . . ." If a player gains
  0 life, no life gain event would occur".
- CR 514.2 - "this turn" ends in the cleanup step.

Listed printing: Flames of the Blood Hand. Proof printing: Combust ("Combust
deals 5 damage to target white or blue creature. The damage can't be
prevented." - a creature target and no life rider; not listed, not in any api
deck, legal in Modern).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario


@pytest.mark.parametrize("name", ["Flames of the Blood Hand", "Combust"])
def test_every_listed_and_proof_card_reads_handled(name):
    outcomes = {clause.outcome for clause in card_support(card(name)).clauses}
    assert outcomes == {"handled"}, name


def _board(*, alice_hand=(), bob_hand=(), bob_battlefield=(), alice_battlefield=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Flames of the Blood Hand", *alice_hand],
            battlefield=[*["Mountain"] * 4, *["Plains"] * 2, *alice_battlefield],
            library=["Mountain"] * 8,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=[*["Mountain"] * 2, *["Plains"] * 3, *bob_battlefield],
            library=["Plains"] * 8,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario, name, *, username="alice", targets=None):
    if scenario.priority_holder != username:
        scenario.pass_priority(scenario.priority_holder)
    return scenario.cast_and_resolve(name, username=username, targets=targets, auto=True)


def test_flames_damage_ignores_a_prevention_shield():
    scenario = _board(bob_hand=["Riot Control"], bob_battlefield=["Grizzly Bears"])
    _cast(scenario, "Riot Control", username="bob")  # prevent all damage to bob
    assert scenario.player("bob").life == 20  # alice controls no creature

    _cast(scenario, "Flames of the Blood Hand", targets=["bob"])

    assert scenario.player("bob").life == 16


def test_only_the_flames_damage_is_unpreventable():
    scenario = _board(alice_hand=["Lightning Bolt"], bob_hand=["Riot Control"])
    _cast(scenario, "Riot Control", username="bob")
    _cast(scenario, "Flames of the Blood Hand", targets=["bob"])

    _cast(scenario, "Lightning Bolt", targets=["bob"])

    assert scenario.player("bob").life == 16  # the Bolt is prevented as usual


def test_the_damaged_player_gains_no_life_this_turn():
    scenario = _board(bob_hand=["Lightning Helix"], alice_battlefield=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast(scenario, "Flames of the Blood Hand", targets=["bob"])

    _cast(scenario, "Lightning Helix", username="bob", targets=[bears])

    assert scenario.player("bob").life == 16  # the Helix's 3 life is not gained
    assert bears.zone is Zone.GRAVEYARD  # the rest of the Helix happens


def test_the_caster_still_gains_life():
    scenario = _board(alice_hand=["Lightning Helix"])
    _cast(scenario, "Flames of the Blood Hand", targets=["bob"])

    _cast(scenario, "Lightning Helix", targets=["bob"])

    assert scenario.player("alice").life == 23
    assert scenario.player("bob").life == 13


def test_the_ban_ends_with_the_turn():
    scenario = _board(bob_hand=["Lightning Helix"])
    _cast(scenario, "Flames of the Blood Hand", targets=["bob"])
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast(scenario, "Lightning Helix", username="bob", targets=["alice"])

    assert scenario.player("bob").life == 19


def test_a_planeswalker_target_bans_its_controllers_life_gain():
    scenario = _board(bob_hand=["Lightning Helix"], bob_battlefield=["Jace Beleren"])
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")
    scenario.game.add_counters(jace, "loyalty", 6 - jace.counters["loyalty"])
    _cast(scenario, "Flames of the Blood Hand", targets=[jace])
    assert jace.counters["loyalty"] == 2

    _cast(scenario, "Lightning Helix", username="bob", targets=["alice"])

    assert scenario.player("bob").life == 20
    assert scenario.player("alice").life == 17


def test_combust_kills_through_a_shield_and_the_shield_is_not_reduced():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Combust", "Lightning Bolt"],
            battlefield=["Mountain"] * 3,
            library=["Mountain"] * 8,
        )
        .player(
            "bob",
            hand=["Shielded Passage"],
            battlefield=["Plains", "Serra Angel", "Savannah Lions"],
            library=["Plains"] * 8,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    _cast(scenario, "Shielded Passage", username="bob", targets=[angel])

    _cast(scenario, "Combust", targets=[angel])

    assert angel.zone is Zone.GRAVEYARD


def test_combust_damage_to_an_unshielded_target_is_ordinary():
    scenario = (
        Scenario()
        .player("alice", hand=["Combust"], battlefield=["Mountain"] * 2, library=["Mountain"] * 8)
        .player("bob", battlefield=["Savannah Lions"], library=["Plains"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lions = scenario.creature("Savannah Lions", "bob")

    _cast(scenario, "Combust", targets=[lions])

    assert lions.zone is Zone.GRAVEYARD
    assert scenario.game.casting_rule_effects == []  # no turn-wide "can't be prevented"
