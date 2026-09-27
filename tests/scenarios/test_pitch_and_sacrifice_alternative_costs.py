"""CR 118.9's alternative cost family: an object-sacrifice alternative cost
read straight off a spell's own printed text, no keyword name involved.

Salvage Titan: "You may sacrifice three artifacts rather than pay this
spell's mana cost." already reads end to end through the machinery
`machines/cost.py::alternative_cost_offers`/`_ALTERNATIVE` already builds for
Force of Will's own pitch cost - `_PHRASE_SACRIFICE` (the same reader
Rottenmouth Viper's own additional cost, `test_sacrifice_any_number_cost_
reduction.py`, now widens for "any number of") already turns "sacrifice
three artifacts" into a payable `ComponentKind.SACRIFICE`. Nothing needed
fixing here; this file is the missing scenario proof `sweep_pool.py`'s own
`static_unaudited` bucket flagged as never checked either way.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 118.9** - "An alternative cost is a cost listed in a spell's text ...
  that its controller may pay rather than paying the spell's mana cost."
- **CR 118.9c** - the mana cost itself is unchanged; only what is paid
  differs.
- **CR 601.2b** - the alternative cost's own objects are announced as the
  spell is cast.
- **CR 701.21a** - to sacrifice a permanent, its controller moves it from
  the battlefield to its owner's graveyard.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(*, battlefield: list[str]) -> Scenario:
    return Scenario().player("alice", hand=["Salvage Titan"], battlefield=battlefield).player("bob")


def test_sacrificing_three_artifacts_casts_it_for_no_mana():
    scenario = _board(battlefield=["Memnite", "Ornithopter", "Ichor Wellspring"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.find("Memnite", Zone.BATTLEFIELD, "alice")
    ornithopter = scenario.find("Ornithopter", Zone.BATTLEFIELD, "alice")
    wellspring = scenario.find("Ichor Wellspring", Zone.BATTLEFIELD, "alice")

    casting = scenario.cast("Salvage Titan")
    casting.use_pitch_cost(choosing=[memnite, ornithopter, wellspring])
    payment = casting.begin_paying()
    payment.pay()
    titan = scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert memnite.zone is Zone.GRAVEYARD
    assert ornithopter.zone is Zone.GRAVEYARD
    assert wellspring.zone is Zone.GRAVEYARD
    assert titan.zone is Zone.BATTLEFIELD


def test_the_mana_cost_is_still_available_when_preferred():
    scenario = _board(battlefield=["Swamp"] * 6).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Swamp"] * 6))

    titan = scenario.cast_and_resolve("Salvage Titan", *sources)

    assert titan.zone is Zone.BATTLEFIELD


def test_fewer_than_three_artifacts_cannot_pay_the_alternative_cost():
    """CR 118.3: a cost cannot be paid without the resources for it."""
    scenario = _board(battlefield=["Memnite", "Ornithopter"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.find("Memnite", Zone.BATTLEFIELD, "alice")
    ornithopter = scenario.find("Ornithopter", Zone.BATTLEFIELD, "alice")

    casting = scenario.cast("Salvage Titan")
    casting.use_pitch_cost(choosing=[memnite, ornithopter])
    payment = casting.begin_paying()
    with pytest.raises(ValueError):
        payment.pay()


def test_exiling_three_artifact_cards_returns_it_from_the_graveyard_to_hand():
    """Salvage Titan's own second ability: "Exile three artifact cards from
    your graveyard: Return this card from your graveyard to your hand."
    Already `handled` by the generic template before this task - proved
    here so the whole card, not only its cost, is covered."""
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Salvage Titan", "Memnite", "Ornithopter", "Ichor Wellspring"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    titan = scenario.find("Salvage Titan", Zone.GRAVEYARD, "alice")
    memnite = scenario.find("Memnite", Zone.GRAVEYARD, "alice")
    ornithopter = scenario.find("Ornithopter", Zone.GRAVEYARD, "alice")
    wellspring = scenario.find("Ichor Wellspring", Zone.GRAVEYARD, "alice")

    scenario.activate(titan, index=0, username="alice", exiling=[memnite, ornithopter, wellspring])
    scenario.pass_until_resolved()

    assert titan.zone is Zone.HAND
    assert memnite.zone is Zone.EXILE
    assert ornithopter.zone is Zone.EXILE
    assert wellspring.zone is Zone.EXILE
