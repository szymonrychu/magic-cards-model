"""A resolving ability that makes a target creature attack if able for a
stated duration - Nahiri, the Unforgiving's +1 ("Until your next turn, up to
one target creature attacks a player each combat if able.") and Heckling
Fiends' "Target creature attacks this turn if able."

Every CR number here was read in full with `mise run rules:find` in the
session that wrote this file:

- **CR 508.1d** - requirements are counted when attackers are declared; the
  declaration must obey as many as can be obeyed without breaking a
  restriction. "Attacks a player" is obeyed only by attacking a player, not
  a planeswalker.
- **CR 611.2a** - a continuous effect from a resolving ability lasts as long
  as it says: "until your next turn" ends as its controller's next turn
  begins, "this turn" at end of turn.
- **CR 115.6** - "up to one target" may choose no target at all.

Heckling Fiends is the proof printing: legal in Modern (Scryfall legalities,
2026-09-23), in no deck under `magic-cards-model-api/decks/`, a creature's
activated ability with "this turn" rather than "until your next turn" and no
"a player" restriction.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _resolve_stack(scenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def _advance_until(scenario, predicate) -> None:
    while not predicate(scenario):
        scenario.advance()
        _resolve_stack(scenario)


def _to_attack(scenario, player: str) -> None:
    """Walk to `player`'s beginning of combat, then stand in the declare
    attackers step without running its turn-based action - an unscripted
    seat's default declaration already obeys every requirement (CR 508.1d),
    and these tests make the declaration themselves."""
    _advance_until(
        scenario,
        lambda s: s.turn.active_player == player and s.step is Step.BEGINNING_OF_COMBAT,
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)


def _to_bobs_attack(scenario) -> None:
    _to_attack(scenario, "bob")


def _nahiri_board():
    scenario = (
        Scenario()
        .player("alice", hand=["Nahiri, the Unforgiving"], library=["Plains"] * 10)
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nahiri = scenario.put_onto_battlefield("Nahiri, the Unforgiving")
    bears = scenario.creature("Grizzly Bears", "bob")
    return scenario, nahiri, bears


def _plus_one(scenario, nahiri, targets) -> None:
    scenario.activate(nahiri, index=0, targets=targets)
    _resolve_stack(scenario)


def test_the_target_must_attack_on_its_controllers_turn():
    scenario, nahiri, bears = _nahiri_board()
    _plus_one(scenario, nahiri, [bears])
    _to_bobs_attack(scenario)

    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with()

    scenario.attack_with(bears, defending="alice")
    assert scenario.attackers() == [bears]


def test_attacking_nahiri_instead_of_a_player_is_refused():
    """ "Attacks a player": attacking the planeswalker obeys none of it while
    attacking alice obeys it, so CR 508.1d refuses the planeswalker attack."""
    scenario, nahiri, bears = _nahiri_board()
    _plus_one(scenario, nahiri, [bears])
    _to_bobs_attack(scenario)

    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with(bears, defending=nahiri)


def test_the_requirement_ends_when_alices_next_turn_begins():
    scenario, nahiri, bears = _nahiri_board()
    _plus_one(scenario, nahiri, [bears])
    _to_bobs_attack(scenario)
    scenario.attack_with(bears, defending="alice")
    _advance_until(scenario, lambda s: s.turn.active_player == "alice")
    _to_bobs_attack(scenario)

    scenario.attack_with()

    assert scenario.attackers() == []


def test_up_to_one_target_may_choose_nothing():
    scenario, nahiri, bears = _nahiri_board()

    _plus_one(scenario, nahiri, [])
    assert nahiri.loyalty == 6
    _to_bobs_attack(scenario)

    scenario.attack_with()
    assert scenario.attackers() == []


def test_a_tapped_target_cannot_attack_so_no_requirement_is_broken():
    scenario, nahiri, bears = _nahiri_board()
    _plus_one(scenario, nahiri, [bears])
    _advance_until(
        scenario,
        lambda s: s.turn.active_player == "bob" and s.step is Step.PRECOMBAT_MAIN,
    )
    bears.tap()
    _to_bobs_attack(scenario)

    scenario.attack_with()
    assert scenario.attackers() == []


# --------------------------------------------------------------------------
# Heckling Fiends - the proof printing
# --------------------------------------------------------------------------


def _fiends_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Heckling Fiends", "Hill Giant", "Mountain", "Mountain", "Mountain"],
            library=["Mountain"] * 10,
        )
        .player("bob", library=["Forest"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature("Heckling Fiends"), scenario.creature("Hill Giant")


def test_heckling_fiends_makes_the_target_attack_this_turn():
    scenario, fiends, giant = _fiends_board()
    giant.summoning_sick = False

    scenario.activate(fiends, *scenario.untapped_sources(*["Mountain"] * 3), targets=[giant])
    _resolve_stack(scenario)
    _to_attack(scenario, "alice")

    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with()
    scenario.attack_with(giant)
    assert scenario.attackers() == [giant]


def test_heckling_fiends_requirement_is_gone_next_turn():
    scenario, fiends, giant = _fiends_board()
    giant.summoning_sick = False
    scenario.activate(fiends, *scenario.untapped_sources(*["Mountain"] * 3), targets=[giant])
    _resolve_stack(scenario)
    _advance_until(scenario, lambda s: s.turn.active_player == "bob")
    _to_attack(scenario, "alice")

    scenario.attack_with()
    assert scenario.attackers() == []
    assert giant.zone is Zone.BATTLEFIELD


def test_every_listed_clause_is_handled_by_the_sweep():
    from magic_cards_model.support import HANDLED, card_support
    from tests.cards import card

    for name in ("Nahiri, the Unforgiving", "Heckling Fiends"):
        for clause in card_support(card(name)).clauses:
            if clause.kind == "keyword":
                continue
            assert clause.outcome == HANDLED, (name, clause.text, clause.outcome)
