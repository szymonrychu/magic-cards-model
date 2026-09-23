"""A resolving ability that makes a target creature block its source this
turn if able - Sisters of Stone Death's "{G}: Target creature blocks Sisters
of Stone Death this turn if able." and Tangle Angler's "{G}: Target creature
blocks this creature this turn if able."

Every CR number here was read in full with `mise run rules:find` in the
session that wrote this file:

- **CR 509.1c** - requirements are counted when blockers are declared; the
  declaration must obey as many as can be obeyed without breaking a
  restriction, and a "blocks if able during a certain turn" requirement
  applies at each declare blockers step of that turn.
- **CR 611.2a** - a continuous effect from a resolving ability lasts as long
  as it says: "this turn" ends with the turn.

Tangle Angler is the proof printing: legal in Modern (Scryfall legalities,
2026-09-23), in no deck under `magic-cards-model-api/decks/`, and printed
with "this creature" rather than its own name.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind, DecisionPending
from magic_cards_model.machines.legal_actions import ActionKind, legal_actions
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _resolve_stack(scenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def _sisters_board(*, bob=("Grizzly Bears",), alice_extra=(), manual=False):
    builder = Scenario()
    if manual:
        builder = builder.manual_turn_based_actions()
    scenario = (
        builder.player(
            "alice",
            battlefield=["Sisters of Stone Death", *alice_extra, "Forest", "Forest"],
            library=["Forest"] * 10,
        )
        .player("bob", battlefield=list(bob), library=["Forest"] * 10)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    sisters = scenario.creature("Sisters of Stone Death")
    sisters.summoning_sick = False
    return scenario, sisters


def _lure(scenario, source, target) -> None:
    forest, *_ = scenario.untapped_sources("Forest")
    scenario.activate(source, forest, index=0, targets=[target])
    _resolve_stack(scenario)


def test_declaring_no_blockers_is_refused_when_the_target_can_block():
    scenario, sisters = _sisters_board()
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(sisters)
    _lure(scenario, sisters, bears)

    with pytest.raises(ValueError, match=r"CR 509\.1c"):
        scenario.no_blocks()

    scenario.block(sisters, bears)
    assert scenario.blockers() == [bears]


def test_blocking_a_different_attacker_instead_is_refused():
    scenario, sisters = _sisters_board(alice_extra=("Hill Giant",))
    giant = scenario.creature("Hill Giant")
    giant.summoning_sick = False
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(sisters, giant)
    _lure(scenario, sisters, bears)

    with pytest.raises(ValueError, match=r"CR 509\.1c"):
        scenario.block(giant, bears)


def test_other_creatures_remain_free_to_block_anything():
    scenario, sisters = _sisters_board(
        bob=("Grizzly Bears", "Hill Giant"), alice_extra=("Hill Giant",)
    )
    alice_giant = scenario.creature("Hill Giant", "alice")
    alice_giant.summoning_sick = False
    bears = scenario.creature("Grizzly Bears", "bob")
    bob_giant = scenario.creature("Hill Giant", "bob")
    scenario.attack_with(sisters, alice_giant)
    _lure(scenario, sisters, bears)

    scenario.game.declare_blockers([(bears, sisters), (bob_giant, alice_giant)])

    assert {c.id for c in scenario.blockers()} == {bears.id, bob_giant.id}


def test_a_tapped_target_cannot_block_so_no_requirement_is_broken():
    scenario, sisters = _sisters_board()
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(sisters)
    _lure(scenario, sisters, bears)
    bears.tap()

    scenario.no_blocks()
    assert scenario.blockers() == []


def test_the_requirement_does_nothing_when_its_source_is_not_attacking():
    scenario, sisters = _sisters_board(alice_extra=("Hill Giant",))
    giant = scenario.creature("Hill Giant")
    giant.summoning_sick = False
    bears = scenario.creature("Grizzly Bears", "bob")
    _lure(scenario, sisters, bears)
    scenario.attack_with(giant)

    scenario.no_blocks()
    assert scenario.blockers() == []


def test_the_requirement_ends_with_the_turn():
    scenario, sisters = _sisters_board()
    bears = scenario.creature("Grizzly Bears", "bob")
    _lure(scenario, sisters, bears)
    while not (scenario.turn.active_player == "alice" and scenario.turn.turns_taken > 1):
        scenario.advance()
        _resolve_stack(scenario)
    while scenario.step is not Step.BEGINNING_OF_COMBAT:
        scenario.advance()
        _resolve_stack(scenario)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(sisters)

    scenario.no_blocks()
    assert scenario.blockers() == []


def test_an_unscripted_defender_blocks_with_the_target():
    scenario, sisters = _sisters_board()
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(sisters)
    _lure(scenario, sisters, bears)

    while scenario.step is not Step.DECLARE_BLOCKERS:
        scenario.advance()

    assert scenario.blockers() == [bears]
    assert scenario.game.combat.attack_by(sisters.id).blockers == [bears.id]


def test_declare_nobody_is_not_offered_while_the_requirement_can_be_obeyed():
    scenario, sisters = _sisters_board(manual=True)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(sisters)
    _lure(scenario, sisters, bears)
    scenario.game.turn.step = Step.DECLARE_BLOCKERS
    scenario.game.decisions.pause_when_unanswered = True

    with pytest.raises(DecisionPending) as excinfo:
        scenario.turn_based_actions()
    pending = excinfo.value.pending
    assert pending.decision.kind is DecisionKind.DECLARE_BLOCKERS

    actions = legal_actions(scenario.game, "bob", pending=pending)
    assert [a for a in actions if a.decision_option == "declare_nobody"] == []
    assert [a.card_id for a in actions if a.kind is ActionKind.DECLARE_BLOCKER] == [bears.id]


# --------------------------------------------------------------------------
# Tangle Angler - the proof printing
# --------------------------------------------------------------------------


def test_tangle_angler_makes_the_target_block_it():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tangle Angler", "Forest"], library=["Forest"] * 10)
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest"] * 10)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    angler = scenario.creature("Tangle Angler")
    angler.summoning_sick = False
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(angler)
    _lure(scenario, angler, bears)

    with pytest.raises(ValueError, match=r"CR 509\.1c"):
        scenario.no_blocks()
    scenario.block(angler, bears)
    assert scenario.blockers() == [bears]
    assert bears.zone is Zone.BATTLEFIELD


def test_every_clause_is_handled_by_the_sweep():
    from magic_cards_model.support import HANDLED, card_support
    from tests.cards import card

    for name in ("Sisters of Stone Death", "Tangle Angler"):
        for clause in card_support(card(name)).clauses:
            if clause.kind == "keyword":
                continue
            assert clause.outcome == HANDLED, (name, clause.text, clause.outcome)
