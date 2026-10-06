"""Scenario: Awaken N - [cost] (CR 702.113).

Rules, each read in full with `mise run rules:find`:

- CR 702.113a - "Awaken appears on some instants and sorceries. It represents
  two abilities: a static ability that functions while the spell with awaken
  is on the stack and a spell ability. "Awaken N-[cost]" means "You may pay
  [cost] rather than pay this spell's mana cost as you cast this spell" and
  "If this spell's awaken cost was paid, put N +1/+1 counters on target land
  you control. That land becomes a 0/0 Elemental creature with haste. It's
  still a land." Casting a spell using its awaken ability follows the rules
  for paying alternative costs in rules 601.2b and 601.2f-h."
- CR 702.113b - "The controller of a spell with awaken chooses the target of
  the awaken spell ability only if that player chose to pay the spell's awaken
  cost. Otherwise the spell is cast as if it didn't have that target."
- CR 608.2b - a target that is no longer legal is skipped; the rest of the
  spell still happens.
- CR 611.2a - the land animation states no duration, so it lasts
  indefinitely.

Listed printing: Encircling Fissure (Awaken 2). Proof printing: Clutch of
Currents (Awaken 3 on a bounce spell: its own target must not be confused with
the awaken target; not listed, not in any api deck, legal in Modern/Pioneer).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario


@pytest.mark.parametrize("name", ["Encircling Fissure", "Clutch of Currents"])
def test_every_listed_and_proof_card_reads_handled(name):
    outcomes = {clause.outcome for clause in card_support(card(name)).clauses}
    assert outcomes == {"handled"}, name


def _board(hand, *, lands=("Plains",) * 6, bob_battlefield=()):
    scenario = (
        Scenario()
        .player("alice", hand=[hand], battlefield=list(lands), library=["Plains"] * 8)
        .player("bob", battlefield=list(bob_battlefield), library=["Mountain"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _awaken(scenario, name, targets):
    casting = scenario.cast(name, username="alice")
    casting.use_keyword("Awaken")
    casting.choose_targets(targets)
    payment = casting.begin_paying()
    lands = [
        permanent
        for permanent in scenario.game.permanents_controlled_by("alice")
        if not permanent.tapped and permanent not in targets
    ]
    scenario.pay_with(payment, *lands[:5])
    scenario.put_on_stack(casting)
    return casting


def test_awaken_is_offered_as_an_alternative_cost():
    scenario = _board("Encircling Fissure")

    casting = scenario.cast("Encircling Fissure", username="alice")

    (option,) = [option for option in casting.cast_options if option.keyword == "Awaken"]
    assert str(option.cost) == "{4}{W}"
    assert not option.pays_mana_cost


def test_awakened_fissure_animates_the_land_and_still_shields():
    scenario = _board("Encircling Fissure", bob_battlefield=["Grizzly Bears"])
    land = scenario.untapped_sources("Plains")[0]
    _awaken(scenario, "Encircling Fissure", ["bob", land])
    scenario.resolve_top()

    chars = scenario.game.characteristics_of(land)
    assert Type.CREATURE in chars.types and Type.LAND in chars.types
    assert "Elemental" in chars.subtypes and "Plains" in chars.subtypes
    assert (scenario.game.power_of(land), scenario.game.toughness_of(land)) == (2, 2)
    assert land.counters["+1/+1"] == 2
    assert "Haste" in chars.abilities or any(a.lower() == "haste" for a in chars.abilities)
    assert any(shield.combat_only for shield in scenario.game.prevention_shields)


def test_the_awakened_land_has_haste_and_attacks_at_once():
    scenario = _board("Encircling Fissure", lands=("Plains",) * 6)
    land = scenario.untapped_sources("Plains")[0]
    _awaken(scenario, "Encircling Fissure", ["bob", land])
    scenario.resolve_top()

    scenario.attack_with(land, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 18


def test_without_awaken_there_is_no_land_target():
    scenario = _board("Encircling Fissure", lands=("Plains",) * 3)
    land = scenario.untapped_sources("Plains")[0]

    with pytest.raises(ValueError):
        scenario.cast("Encircling Fissure", username="alice", targets=["bob", land])

    scenario.cast_and_resolve("Encircling Fissure", username="alice", targets=["bob"], auto=True)
    assert Type.CREATURE not in scenario.game.characteristics_of(land).types


def test_the_animation_lasts_beyond_the_turn():
    scenario = _board("Encircling Fissure")
    land = scenario.untapped_sources("Plains")[0]
    _awaken(scenario, "Encircling Fissure", ["bob", land])
    scenario.resolve_top()

    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()

    assert Type.CREATURE in scenario.game.characteristics_of(land).types
    assert not any(not shield.spent for shield in scenario.game.prevention_shields)


def test_clutch_of_currents_bounces_its_target_and_awakens_a_different_land():
    scenario = _board(
        "Clutch of Currents",
        lands=("Island",) * 6,
        bob_battlefield=["Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    land = scenario.untapped_sources("Island")[0]
    _awaken(scenario, "Clutch of Currents", [bears, land])
    scenario.resolve_top()

    assert bears.zone is Zone.HAND
    assert land.zone is Zone.BATTLEFIELD  # the awaken target is not bounced
    assert land.counters["+1/+1"] == 3
    assert (scenario.game.power_of(land), scenario.game.toughness_of(land)) == (3, 3)


def test_an_illegal_awaken_target_skips_only_the_awaken_half():
    scenario = _board(
        "Clutch of Currents",
        lands=("Island",) * 6,
        bob_battlefield=["Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    lands = scenario.untapped_sources(*["Island"] * 6)
    land = lands[-1]
    casting = scenario.cast("Clutch of Currents", username="alice")
    casting.use_keyword("Awaken")
    casting.choose_targets([bears, land])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *lands[:5])
    scenario.put_on_stack(casting)
    scenario.game.destroy(land)

    scenario.resolve_top()

    assert bears.zone is Zone.HAND
    assert land.zone is Zone.GRAVEYARD


def test_an_unpaid_awaken_leaves_the_bounce_alone():
    scenario = _board(
        "Clutch of Currents", lands=("Island",) * 2, bob_battlefield=["Grizzly Bears"]
    )
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve("Clutch of Currents", username="alice", targets=[bears], auto=True)

    assert bears.zone is Zone.HAND
    for land in scenario.game.permanents_controlled_by("alice"):
        assert Type.CREATURE not in scenario.game.characteristics_of(land).types
