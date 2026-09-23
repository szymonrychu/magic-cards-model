"""Scenario: an activated ability "<self> gains <keyword> until end of turn.
Tap it." - the grant, then the anaphoric "Tap it." tapping the same object.

- **CR 602.2** - activating puts the ability on the stack and pays its costs;
  the cost ("Tap another untapped creature you control", "Sacrifice another
  creature or artifact") is paid then, on the other creature, not on the
  source.
- **CR 608.2c** - the instructions in the order written: the grant, then the
  tap; "it" is the object the first sentence named - the source itself.
- **CR 613.1f** - the keyword is a layer 6 grant.
- **CR 701.26a** - to tap a permanent is to turn it sideways; only an
  untapped permanent can be tapped.
- **CR 702.12b** - indestructible: can't be destroyed, and lethal damage does
  not destroy it.

Tyvar, the Pummeler is the reported card (named self-reference, a tap cost).
Vanguard of the Rose is the second printing: "This creature" rather than the
name, and a mana-plus-sacrifice cost rather than a tap cost.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import is_indestructible
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def notices(scenario: Scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _tyvar() -> Scenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tyvar, the Pummeler", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _activate_tyvar(scenario: Scenario):
    tyvar = scenario.creature("Tyvar, the Pummeler", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.activate(tyvar, index=0, tapping_for_cost=[bears])
    return tyvar, bears


def test_tyvar_taps_another_creature_to_gain_indestructible_then_taps_itself():
    scenario = _tyvar()
    tyvar, bears = _activate_tyvar(scenario)
    assert bears.tapped, "the cost is paid on activation (CR 602.2)"
    assert not tyvar.tapped, "Tyvar is not part of the cost"

    scenario.pass_until_resolved()

    assert is_indestructible(tyvar, scenario.game)
    assert tyvar.tapped, "Tap it. - it is Tyvar"
    assert not is_indestructible(bears, scenario.game)
    assert notices(scenario) == []


def test_tyvar_cannot_tap_itself_for_the_cost():
    """ "another" untapped creature (CR 602.2's cost is paid by the
    activator, on something other than the source)."""
    scenario = _tyvar()
    tyvar = scenario.creature("Tyvar, the Pummeler", "alice")

    with pytest.raises(ValueError):
        scenario.activate(tyvar, index=0, tapping_for_cost=[tyvar])
    assert not tyvar.tapped


def test_an_already_tapped_tyvar_still_gains_indestructible():
    """CR 701.26a: tapping an already-tapped permanent does nothing, and the
    grant before it still happens."""
    scenario = _tyvar()
    tyvar = scenario.creature("Tyvar, the Pummeler", "alice")
    tyvar.tap()
    _, bears = _activate_tyvar(scenario)
    scenario.pass_until_resolved()

    assert tyvar.tapped
    assert is_indestructible(tyvar, scenario.game)


def test_tyvar_gone_before_resolution_grants_nothing():
    """The ability names no target: with its source gone there is nothing for
    "Tyvar" or "it" to mean (CR 400.7)."""
    scenario = _tyvar()
    tyvar, _ = _activate_tyvar(scenario)
    scenario.game.return_to_hand(tyvar)
    scenario.pass_until_resolved()

    assert tyvar.zone is Zone.HAND
    assert scenario.game.continuous_effects.effects == []


def test_the_indestructible_ends_in_the_cleanup_step_and_tyvar_stays_tapped():
    scenario = _tyvar()
    tyvar, _ = _activate_tyvar(scenario)
    scenario.pass_until_resolved()

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup

    assert not is_indestructible(tyvar, scenario.game)
    assert tyvar.tapped


# -- second printing: Vanguard of the Rose ---------------------------------


def test_vanguard_of_the_rose_sacrifices_gains_indestructible_and_taps():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Plains", "Vanguard of the Rose", "Memnite"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vanguard = scenario.creature("Vanguard of the Rose", "alice")
    memnite = scenario.creature("Memnite", "alice")
    (plains,) = scenario.untapped_sources("Plains", username="alice")

    scenario.activate(vanguard, plains, index=0, sacrificing=[memnite])
    assert memnite.zone is Zone.GRAVEYARD
    scenario.pass_until_resolved()

    assert is_indestructible(vanguard, scenario.game)
    assert vanguard.tapped
    assert notices(scenario) == []


def test_vanguard_cannot_sacrifice_itself_for_the_cost():
    """ "another" creature or artifact - never the source."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Plains", "Vanguard of the Rose"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vanguard = scenario.creature("Vanguard of the Rose", "alice")
    (plains,) = scenario.untapped_sources("Plains", username="alice")

    with pytest.raises(ValueError):
        scenario.activate(vanguard, plains, index=0, sacrificing=[vanguard])
    assert vanguard.zone is Zone.BATTLEFIELD
