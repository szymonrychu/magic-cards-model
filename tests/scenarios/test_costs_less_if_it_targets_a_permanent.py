"""Scenario: "This spell costs `<mana>` less to cast if it targets a
`<permanent description>`." - CR 601.2f's self reduction conditioned on the
spell's own announced target, where the target is a permanent rather than a
spell (Mystical Dispute's "a blue spell" shape is
`test_cost_reduction_if_targets_spell`'s).

- **Bouncer's Beatdown** - "{2} less ... if it targets a black permanent." (a
  colour, and "permanent" covering both a creature and a planeswalker).
- **Ajani's Response** - "{3} less ... if it targets a tapped creature." (a
  state rather than a characteristic, a different amount and noun).

Rules, each read with `mise run rules:find` in the session that wrote this:

- **CR 601.2c** - targets are announced before the total cost is determined.
- **CR 601.2f** - the total cost is the mana cost "minus all cost reductions",
  then locked in; a generic reduction cannot go below {0}.
- **CR 118.7a** - a generic reduction touches only the generic component, so
  the coloured pip survives.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.mana import ManaCost
from tests.scenarios.harness import Scenario

BEATDOWN = "Bouncer's Beatdown"
RESPONSE = "Ajani's Response"


def _beatdown(*bob: str) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=[BEATDOWN],
            battlefield=["Forest", "Forest", "Forest", "Craw Wurm"],
        )
        .player("bob", library=["Swamp"], battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_a_black_creature_target_makes_it_cost_only_the_green_pip():
    scenario = _beatdown("Dark Confidant")
    bob_creature = scenario.creature("Dark Confidant", "bob")

    casting = scenario.cast(BEATDOWN, targets=[bob_creature])

    assert casting.total_cost.mana == ManaCost.parse("{G}")


def test_a_black_planeswalker_target_is_a_black_permanent_too():
    scenario = _beatdown("Liliana of the Veil")
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")

    casting = scenario.cast(BEATDOWN, targets=[liliana])

    assert casting.total_cost.mana == ManaCost.parse("{G}")


def test_a_nonblack_target_pays_the_full_cost():
    scenario = _beatdown("Grizzly Bears")
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast(BEATDOWN, targets=[bears])

    assert casting.total_cost.mana == ManaCost.parse("{2}{G}")


def test_one_forest_is_not_enough_against_a_nonblack_target():
    scenario = _beatdown("Grizzly Bears")
    bears = scenario.creature("Grizzly Bears", "bob")
    casting = scenario.cast(BEATDOWN, targets=[bears])
    payment = casting.begin_paying()
    (forest, *_) = scenario.untapped_sources("Forest", "Forest", "Forest")

    with pytest.raises(ValueError, match="cannot pay"):
        scenario.pay_with(payment, forest)
    casting.cancel()


def test_one_forest_casts_it_at_a_black_target_and_it_resolves():
    scenario = _beatdown("Dark Confidant")
    confidant = scenario.creature("Dark Confidant", "bob")
    (forest, *_) = scenario.untapped_sources("Forest", "Forest", "Forest")

    scenario.cast_and_resolve(BEATDOWN, forest, targets=[confidant])

    assert confidant.zone is Zone.EXILE
    assert len(scenario.untapped_sources("Forest", "Forest")) == 2


# -- second printing: Ajani's Response, a tapped creature ---------------------


def _response() -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Plains"],
            hand=[RESPONSE],
            battlefield=["Plains"] * 5,
        )
        .player("bob", library=["Plains"], battlefield=["Grizzly Bears", "Savannah Lions"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_response_at_a_tapped_creature_costs_three_less():
    scenario = _response()
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.tap()

    casting = scenario.cast(RESPONSE, targets=[bears])

    assert casting.total_cost.mana == ManaCost.parse("{1}{W}")


def test_response_at_an_untapped_creature_pays_the_full_cost():
    scenario = _response()
    lions = scenario.creature("Savannah Lions", "bob")

    casting = scenario.cast(RESPONSE, targets=[lions])

    assert casting.total_cost.mana == ManaCost.parse("{4}{W}")


def test_response_at_a_tapped_creature_resolves_for_two_mana():
    scenario = _response()
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.tap()
    plains = scenario.untapped_sources("Plains", "Plains", username="alice")

    scenario.cast_and_resolve(RESPONSE, *plains, targets=[bears])

    assert bears.zone is Zone.GRAVEYARD
