"""Attack requirements: "attacks each combat if able" (CR 508.1d).

- **CR 508.1d** - "The active player checks each creature they control to see
  whether it's affected by any requirements (effects that say a creature
  attacks if able, or that it attacks if some condition is met). If the number
  of requirements that are being obeyed is fewer than the maximum possible
  number of requirements that could be obeyed without disobeying any
  restrictions, the declaration of attackers is illegal. If a creature can't
  attack unless a player pays a cost, that player is not required to pay that
  cost, even if attacking with that creature would increase the number of
  requirements being obeyed."
- **CR 508.1c** - restrictions are "effects that say a creature can't attack,
  or that it can't attack unless some condition is met"; CR 508.1a's untapped
  and summoning-sickness checks are what "able" is measured against.

Dragon's Rage Channeler is the deck-pool card (its delirium grants the
requirement only while four card types are in the graveyard, battle 7 B7-04).
Juggernaut ("This creature attacks each combat if able.") is in neither deck
pool and carries the requirement printed, unconditionally.

Every CR number above was read in full with `mise run rules:find` in the
session that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from tests.scenarios.harness import Scenario

DELIRIUM = ["Lightning Bolt", "Grizzly Bears", "Sol Ring", "Bojuka Bog"]


def _juggernaut(*, extra: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Juggernaut", *(extra or [])])
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_an_empty_declaration_is_refused_while_juggernaut_could_attack():
    scenario = _juggernaut().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    with pytest.raises(ValueError, match=r"CR 508\.1d") as refused:
        scenario.attack_with()

    assert "Juggernaut" in str(refused.value)
    assert scenario.attackers() == []


def test_declaring_juggernaut_obeys_the_requirement():
    scenario = _juggernaut().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    juggernaut = scenario.creature("Juggernaut")

    scenario.attack_with(juggernaut)

    assert scenario.attackers() == [juggernaut]


def test_attacking_with_another_creature_but_not_juggernaut_is_refused():
    scenario = _juggernaut(extra=["Hill Giant"]).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant")

    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with(giant)

    assert scenario.attackers() == []
    assert giant.untapped, "a refused declaration taps nothing"


def test_a_tapped_juggernaut_cannot_attack_so_nobody_attacking_is_legal():
    """CR 508.1d counts only requirements that could be obeyed: a tapped
    creature cannot attack (CR 508.1a), so no requirement is disobeyed."""
    scenario = _juggernaut().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.creature("Juggernaut").tap()

    scenario.attack_with()

    assert scenario.attackers() == []


def test_a_summoning_sick_juggernaut_is_not_required_to_attack():
    scenario = Scenario().player("alice", hand=["Juggernaut"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Juggernaut")
    scenario.start_at(Step.DECLARE_ATTACKERS)

    scenario.attack_with()

    assert scenario.attackers() == []


def test_the_declare_attackers_step_defaults_an_unscripted_seat_to_the_required_attack():
    """An unscripted seat declares the fewest attackers that obey every
    requirement it can - not nobody, which would be illegal here."""
    scenario = _juggernaut().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    juggernaut = scenario.creature("Juggernaut")

    scenario.game.declare_attackers_step()

    assert scenario.attackers() == [juggernaut]


def test_a_scripted_empty_declaration_is_refused_at_the_step():
    scenario = _juggernaut().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.DECLARE_ATTACKERS, value=(), player="alice")
    )

    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.game.declare_attackers_step()

    assert scenario.attackers() == []


def test_dragons_rage_channeler_with_delirium_must_attack():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Dragon's Rage Channeler"], graveyard=DELIRIUM)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    with pytest.raises(ValueError, match=r"CR 508\.1d") as refused:
        scenario.attack_with()

    assert "Dragon's Rage Channeler" in str(refused.value)


def test_dragons_rage_channeler_without_delirium_may_stay_home():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Dragon's Rage Channeler"], graveyard=DELIRIUM[:3])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    scenario.attack_with()

    assert scenario.attackers() == []
