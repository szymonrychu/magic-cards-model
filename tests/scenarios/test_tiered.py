"""Tiered: a mode with its own additional cost (CR 700.2h, CR 702.183a).

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 700.2h** - "Some modal spells have one or more modes with a cost
  listed before the effect of that mode. This indicates that the mode has an
  additional cost that must be paid as the spell is cast if that mode is
  chosen. If more than one such mode is chosen, all additional costs must be
  paid to cast that spell. Paying these costs follows the rules for paying
  additional costs in rules 601.2b and 601.2f-h."
- **CR 702.183a** - "Tiered is a static ability found on some modal spells
  (see rule 700.2) that applies while the spell is on the stack. Tiered means
  'Choose one. As an additional cost to cast this spell, pay the cost
  associated with that mode.'"

Fire Magic (real Scryfall printing, `scripts/add_card.py`) is the only Tiered
card in the pool:

    Tiered (Choose one additional cost.)
    * Fire -- {0} -- Fire Magic deals 1 damage to each creature.
    * Fira -- {2} -- Fire Magic deals 2 damage to each creature.
    * Firaga -- {5} -- Fire Magic deals 3 damage to each creature.

CR 700.2h is a general modal shape, not a Tiered-only one (Spree, CR 702.172a,
prints the same "cost before effect" shape with no tier label and a `+`
bullet) - the parser this file pins reads the shape, not the card name.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.modes import modal_profile
from magic_cards_model.models import Zone
from magic_cards_model.models.mana import ManaCost
from tests.cards import card
from tests.scenarios.harness import Scenario


def board(**kwargs) -> Scenario:
    return Scenario().manual_turn_based_actions().player("alice", **kwargs).player("bob")


FIRE_MAGIC_BOARD = {
    "hand": ["Fire Magic"],
    "battlefield": ["Mountain"] * 6,
}


# -- reading the modes off the card -----------------------------------------


def test_the_three_tiers_are_read_as_understood_modes_with_their_own_cost():
    profile = modal_profile(card("Fire Magic"))

    assert profile.understood, "Tiered's own cost-before-effect modes must parse (CR 700.2h)"
    assert len(profile.modes) == 3
    assert [mode.cost for mode in profile.modes] == ["{0}", "{2}", "{5}"]
    assert profile.minimum == 1 and profile.maximum == 1


def test_an_ordinary_choose_one_modal_card_is_unaffected():
    """Kozilek's Command has no per-mode cost - CR 700.2h's regex must not
    fire on it, and it must keep reading exactly as it always has."""
    profile = modal_profile(card("Kozilek's Command"))

    assert profile.understood
    assert len(profile.modes) == 4
    assert all(mode.cost is None for mode in profile.modes)


# -- the additional cost is genuinely charged (CR 700.2h, CR 601.2f-h) ------


def test_the_fire_mode_adds_nothing_to_the_printed_mana_cost():
    scenario = board(**FIRE_MAGIC_BOARD).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Fire Magic")
    casting.choose_modes([1])

    assert casting.total_cost.mana == ManaCost.parse("{R}")


def test_the_firaga_mode_adds_five_generic_mana():
    scenario = board(**FIRE_MAGIC_BOARD).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Fire Magic")
    casting.choose_modes([3])

    assert casting.total_cost.mana == ManaCost.parse("{5}{R}")


def test_firaga_cannot_be_paid_with_only_the_printed_mana_cost():
    scenario = board(**FIRE_MAGIC_BOARD).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Fire Magic")
    casting.choose_modes([3])
    (mountain,) = scenario.untapped_sources("Mountain")

    with pytest.raises(ValueError):
        scenario.pay_with(casting.begin_paying(), mountain)


# -- resolution: the chosen tier's own effect, nothing else's ---------------


def test_fire_deals_one_damage_to_each_creature():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Fire Magic"],
            battlefield=["Mountain"] * 6 + ["Elvish Mystic"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    mystic = scenario.find("Elvish Mystic", Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")

    casting = scenario.cast("Fire Magic")
    casting.choose_modes([1])
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.pay_with(casting.begin_paying(), mountain)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.state_based_actions()

    assert mystic.zone is Zone.GRAVEYARD, "1 damage kills a 1-toughness Elvish Mystic"
    assert bears.zone is Zone.BATTLEFIELD, "1 damage does not kill a 2-toughness Grizzly Bears"
    assert bears.damage == 1


def test_firaga_deals_three_damage_to_each_creature():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Fire Magic"],
            battlefield=["Mountain"] * 6 + ["Elvish Mystic"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    mystic = scenario.find("Elvish Mystic", Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")

    casting = scenario.cast("Fire Magic")
    casting.choose_modes([3])
    mountains = scenario.untapped_sources(*(["Mountain"] * 6))
    scenario.pay_with(casting.begin_paying(), *mountains)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.state_based_actions()

    assert mystic.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD, "3 damage kills a 2-toughness Grizzly Bears too"
