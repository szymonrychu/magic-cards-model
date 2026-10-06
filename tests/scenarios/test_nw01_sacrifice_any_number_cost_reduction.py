"""An optional "sacrifice any number of creatures" additional cost that makes the
spell cheaper: "As an additional cost to cast this spell, you may sacrifice any
number of creatures. This spell costs {2} less to cast for each creature
sacrificed this way." (Extus, Oriq Overlord // Awaken the Blood Avatar).

The reduction sits on the *face being cast*. Awaken the Blood Avatar is the back
face of a modal double-faced card, so the card's front face prints neither the
cost nor the reduction, and reading the whole card (as the cast machine did
before) found no sacrifice cost at all to announce.

Rules verified with `mise run rules:find`:

- CR 118.8 / 118.8a / 118.8b - additional costs, announced as the spell is cast,
  some optional.
- CR 107.1c - "any number" may be zero.
- CR 601.2b / 601.2f - announcing the additional cost, then determining the
  total cost; the reduction applies to the total.
- CR 118.7a - a generic reduction affects only the generic component, so the
  coloured pips are never reduced.
- CR 701.21a - only a permanent you control can be sacrificed.
- CR 712.11b / 712.11c - casting the back face of a modal double-faced card.

Second printings: Rottenmouth Viper ("{1} less ... for each permanent sacrificed
this way") and Torgaar, Famine Incarnate ("{2} less ... for each creature
sacrificed this way") - the same sentence on a creature spell with a single
face, with a different amount and sacrificed quality.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.mana import ManaCost
from tests.scenarios.harness import Scenario

EXTUS = "Extus, Oriq Overlord"
AWAKEN = "Awaken the Blood Avatar"


def _board(*, swamps: int, mountains: int, alice: list[str], bob: list[str] | None = None):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[EXTUS],
            battlefield=["Swamp"] * swamps + ["Mountain"] * mountains + alice,
            library=["Swamp"] * 5,
        )
        .player("bob", battlefield=bob or ["Hill Giant"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _open_awaken(scenario, sacrificing=None):
    """Announce the Awaken half, and its optional sacrifice when one is named."""
    casting = scenario.cast(EXTUS, username="alice")
    casting.cast_as_split_half(AWAKEN)
    if sacrificing is not None:
        casting.sacrifice_for_cost_reduction(sacrificing)
    return casting


def _cast_awaken(scenario, sacrificing=None):
    casting = _open_awaken(scenario, sacrificing)
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def _avatars(scenario) -> list:
    return [s for s in scenario.game.battlefield if s.name == "Avatar Token"]


def test_awaken_with_no_sacrifice_costs_its_full_eight_mana():
    scenario = _board(swamps=7, mountains=1, alice=[])

    assert _open_awaken(scenario).total_cost.mana == ManaCost.parse("{6}{B}{R}")


def test_each_sacrificed_creature_makes_awaken_cost_two_less():
    scenario = _board(swamps=3, mountains=1, alice=["Grizzly Bears", "Savannah Lions"])
    bears, lions = scenario.creatures("Grizzly Bears", "Savannah Lions", username="alice")

    casting = _open_awaken(scenario, [bears, lions])

    assert casting.total_cost.mana == ManaCost.parse("{2}{B}{R}")


def test_one_sacrificed_creature_leaves_six_mana_to_pay():
    scenario = _board(swamps=4, mountains=1, alice=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")

    casting = _open_awaken(scenario, [bears])

    assert casting.total_cost.mana == ManaCost.parse("{4}{B}{R}")
    payment = casting.begin_paying()
    with pytest.raises(ValueError):
        scenario.auto_pay(payment, username="alice")  # five lands, six mana owed


def test_the_sacrificed_creatures_are_gone_and_the_cheaper_spell_resolves():
    scenario = _board(swamps=3, mountains=1, alice=["Grizzly Bears", "Savannah Lions"])
    bears, lions = scenario.creatures("Grizzly Bears", "Savannah Lions", username="alice")

    _cast_awaken(scenario, [bears, lions])

    assert bears.zone is Zone.GRAVEYARD
    assert lions.zone is Zone.GRAVEYARD
    assert len(_avatars(scenario)) == 1
    assert all(land.tapped for land in scenario.game.battlefield if land.card.is_land)


def test_the_reduction_never_touches_the_coloured_pips():
    """CR 118.7a: four creatures would be {8} less, but {B}{R} stays."""
    names = ["Grizzly Bears", "Savannah Lions", "Grizzly Bears", "Savannah Lions"]
    scenario = _board(swamps=1, mountains=1, alice=names)
    sacrificed = scenario.creatures(*names, username="alice")

    casting = _open_awaken(scenario, sacrificed)

    assert casting.total_cost.mana == ManaCost.parse("{B}{R}")


def test_four_sacrificed_creatures_cast_it_for_two_lands():
    names = ["Grizzly Bears", "Savannah Lions", "Grizzly Bears", "Savannah Lions"]
    scenario = _board(swamps=1, mountains=1, alice=names)
    sacrificed = scenario.creatures(*names, username="alice")

    _cast_awaken(scenario, sacrificed)

    assert len(_avatars(scenario)) == 1
    assert all(creature.zone is Zone.GRAVEYARD for creature in sacrificed)


def test_the_coloured_mana_it_still_costs_must_be_available():
    """Two Swamps cannot pay {B}{R}, however many creatures were sacrificed."""
    scenario = _board(swamps=2, mountains=0, alice=["Grizzly Bears", "Savannah Lions"])
    bears, lions = scenario.creatures("Grizzly Bears", "Savannah Lions", username="alice")
    casting = _open_awaken(scenario, [bears, lions])
    payment = casting.begin_paying()

    with pytest.raises(ValueError):
        scenario.auto_pay(payment, username="alice")


def test_sacrificing_zero_creatures_is_legal_and_reduces_nothing():
    """CR 107.1c: "any number" includes zero."""
    scenario = _board(swamps=7, mountains=1, alice=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")

    casting = _open_awaken(scenario, [])

    assert casting.total_cost.mana == ManaCost.parse("{6}{B}{R}")
    assert bears.zone is Zone.BATTLEFIELD


def test_a_creature_alice_does_not_control_cannot_be_sacrificed():
    """CR 701.21a."""
    scenario = _board(swamps=7, mountains=1, alice=[])
    giant = scenario.creature("Hill Giant", "bob")

    with pytest.raises(ValueError):
        _open_awaken(scenario, [giant])


def test_the_front_face_prints_no_sacrifice_cost():
    """Extus ({1}{W}{B}{B}) has nothing to sacrifice for: announcing the optional
    cost on the front face is refused, not silently read off the back face."""
    scenario = _board(swamps=2, mountains=0, alice=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    casting = scenario.cast(EXTUS, username="alice")

    with pytest.raises(ValueError):
        casting.sacrifice_for_cost_reduction([bears])


def test_awaken_makes_each_opponent_sacrifice_a_creature_of_their_choice():
    scenario = _board(swamps=7, mountains=1, alice=[], bob=["Hill Giant", "Grizzly Bears"])
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_cards(giant)

    _cast_awaken(scenario)

    assert giant.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD
    assert len(_avatars(scenario)) == 1


# --- second printings ---------------------------------------------------------


def _single_face_board(card: str, lands: list[str], others: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=[card],
            battlefield=lands + others,
            library=["Swamp"] * 5,
        )
        .player("bob", library=["Island"] * 5)
    )


def test_torgaar_costs_two_less_for_each_creature_sacrificed():
    """{6}{B}{B} with two creatures sacrificed is {2}{B}{B}."""
    scenario = _single_face_board(
        "Torgaar, Famine Incarnate", ["Swamp"] * 4, ["Grizzly Bears", "Savannah Lions"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears, lions = scenario.creatures("Grizzly Bears", "Savannah Lions", username="alice")

    casting = scenario.cast("Torgaar, Famine Incarnate", username="alice")
    casting.sacrifice_for_cost_reduction([bears, lions])

    assert casting.total_cost.mana == ManaCost.parse("{2}{B}{B}")


def test_rottenmouth_viper_costs_one_less_for_each_nonland_permanent_sacrificed():
    scenario = _single_face_board(
        "Rottenmouth Viper", ["Swamp"] * 4, ["Grizzly Bears", "Savannah Lions"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears, lions = scenario.creatures("Grizzly Bears", "Savannah Lions", username="alice")

    casting = scenario.cast("Rottenmouth Viper", username="alice")
    casting.sacrifice_for_cost_reduction([bears, lions])

    assert casting.total_cost.mana == ManaCost.parse("{3}{B}")
