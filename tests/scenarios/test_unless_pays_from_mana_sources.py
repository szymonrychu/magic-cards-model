"""Paying an "unless ... pays {N}" by activating mana abilities during the payment.

Battle report B6-08: Metallic Rebuke's "Counter target spell unless its
controller pays {3}" could not be paid by a player with three untapped Urza
lands, and the refusal to tap one cited CR 608.2g - whose first sentence allows
exactly that.

Every CR number below was read in this session with `mise run rules:find`:

- **CR 608.2g** - "If an effect gives a player the option to pay mana, they may
  activate mana abilities before taking that action."
- **CR 605.3a** - "A player may activate an activated mana ability ... whenever
  a rule or effect asks for a mana payment, even if it's in the middle of
  casting or resolving a spell or activating or resolving an ability."
- **CR 117.1d** - the same permission, from the priority rules.
- **CR 118.12a** - "[Do something] unless [a player does something else]" means
  "[a player] may [do something else]. If [that player] doesn't, [effect]."
- **CR 118.3** - "A player can't pay a cost without having the necessary
  resources to pay it fully."
- **CR 118.3c** - "Activating mana abilities is not mandatory, even if paying a
  cost is."
- **CR 608.2d** - "The player can't choose an option that's illegal or
  impossible".

Mana Leak (outside the deck pool) is the counterspell; Summoner's Pact's
delayed "pay {2}{G}{G}. If you don't, you lose the game" is the second funnel.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import Answer, DecisionKind, DecisionPending
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from magic_cards_model.models.card import Color
from tests.scenarios.harness import Scenario
from tests.scenarios.test_pact_delayed_upkeep_cost import advance_to_next_upkeep_of


def leak_board(alice_battlefield: list[str]) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Opt"],
            battlefield=["Island", *alice_battlefield],
            library=["Island"] * 5,
        )
        .player("bob", hand=["Mana Leak"], battlefield=["Island", "Island"], library=["Island"] * 5)
    )


def cast_opt_into_mana_leak(scenario):
    """Alice casts Opt off her first Island; Bob answers with Mana Leak."""
    first_island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    opt = scenario.cast_onto_stack("Opt", first_island, username="alice")
    scenario.pass_priority("alice")
    bob_islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_and_resolve("Mana Leak", *bob_islands, username="bob", targets=[opt])
    return opt, first_island


def _pay_mana_question(scenario):
    (question,) = [q for q in scenario.questions_asked() if q.kind is DecisionKind.PAY_MANA]
    return question


def test_the_controller_pays_by_tapping_untapped_lands():
    scenario = leak_board(["Island", "Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice_lands = [s for s in scenario.game.battlefield if s.controller == "alice"]
    scenario.will_pay_the_mana_cost(True, username="alice", source="Mana Leak")

    opt, first_island = cast_opt_into_mana_leak(scenario)

    assert opt.zone is Zone.STACK, "paid, so Mana Leak did not counter it"
    assert all(land.tapped for land in alice_lands)
    assert scenario.player("alice").mana_pool.total == 0
    question = _pay_mana_question(scenario)
    assert question.affirmative_is_legal is True
    assert set(question.mana_sources) == {
        land.id for land in alice_lands if land.id != first_island.id
    }


def test_the_controller_names_which_sources_pay():
    scenario = leak_board(["Island", "Mountain", "Mountain", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountains = [
        s for s in scenario.game.battlefield if s.controller == "alice" and s.name == "Mountain"
    ]
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    spare_island = [
        s for s in scenario.game.battlefield if s.controller == "alice" and s.name == "Island"
    ][1]
    scenario.will_pay_the_mana_cost(
        True, username="alice", source="Mana Leak", sources=[*mountains, forest]
    )

    opt, _first_island = cast_opt_into_mana_leak(scenario)

    assert opt.zone is Zone.STACK
    assert all(land.tapped for land in [*mountains, forest])
    assert spare_island.untapped, "a source nobody named stays untapped (CR 118.3c)"


def test_floating_mana_and_lands_pay_together():
    scenario = leak_board(["Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_pay_the_mana_cost(True, username="alice", source="Mana Leak")
    first_island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    opt = scenario.cast_onto_stack("Opt", first_island, username="alice")
    scenario.player("alice").mana_pool.add(Color.COLORLESS, 1)
    scenario.pass_priority("alice")
    bob_islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_and_resolve("Mana Leak", *bob_islands, username="bob", targets=[opt])

    assert opt.zone is Zone.STACK
    assert scenario.player("alice").mana_pool.total == 0
    assert _pay_mana_question(scenario).affirmative_is_legal is True


def test_too_few_sources_leave_paying_illegal_and_the_spell_is_countered():
    scenario = leak_board(["Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    opt, _first_island = cast_opt_into_mana_leak(scenario)

    assert opt.zone is Zone.GRAVEYARD
    question = _pay_mana_question(scenario)
    assert question.affirmative_is_legal is False


def test_choosing_to_pay_without_the_resources_is_refused_with_the_rules_text():
    scenario = leak_board(["Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_pay_the_mana_cost(True, username="alice", source="Mana Leak")

    with pytest.raises(ValueError) as refused:
        cast_opt_into_mana_leak(scenario)

    message = str(refused.value)
    assert "CR 608.2d" in message
    assert "can't choose an option that's illegal or impossible" in message
    assert "CR 608.2g" not in message


def test_named_sources_that_cannot_cover_the_cost_are_refused():
    scenario = leak_board(["Island", "Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    two = [s for s in scenario.game.battlefield if s.controller == "alice"][1:3]
    scenario.will_pay_the_mana_cost(True, username="alice", source="Mana Leak", sources=two)

    with pytest.raises(ValueError, match=r"CR 118\.3"):
        cast_opt_into_mana_leak(scenario)


def test_a_source_that_was_not_offered_is_refused():
    scenario = leak_board(["Island", "Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bobs = [s for s in scenario.game.battlefield if s.controller == "bob"]
    alices = [s for s in scenario.game.battlefield if s.controller == "alice"][1:3]
    scenario.will_pay_the_mana_cost(
        True, username="alice", source="Mana Leak", sources=[*alices, bobs[0]]
    )

    with pytest.raises(ValueError, match="not one of"):
        cast_opt_into_mana_leak(scenario)


def test_the_paused_payment_enumerates_the_mana_sources():
    scenario = leak_board(["Island", "Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first_island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    opt = scenario.cast_onto_stack("Opt", first_island, username="alice")
    scenario.pass_priority("alice")
    bob_islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.game.decisions.pause_when_unanswered = True

    with pytest.raises(DecisionPending) as paused:
        scenario.cast_and_resolve("Mana Leak", *bob_islands, username="bob", targets=[opt])

    pending = paused.value.pending
    assert pending.decision.kind is DecisionKind.PAY_MANA
    untapped = {s.id for s in scenario.game.battlefield if s.controller == "alice" and s.untapped}
    answers = legal_actions(scenario.game, "alice", pending=pending)
    (pay,) = [
        action
        for action in answers
        if action.kind is ActionKind.ANSWER_DECISION and action.decision_option == "true"
    ]
    assert set(pay.decision_candidates) == untapped
    assert "CR 608.2g" in pending.rule


def test_an_answer_naming_sources_round_trips_through_the_tape():
    scenario = leak_board(["Island", "Island", "Island"]).build()
    ids = tuple(s.id for s in scenario.game.battlefield if s.controller == "alice")[1:]

    answer = Answer(seq=0, kind=DecisionKind.PAY_MANA, player="alice", accept=True, card_ids=ids)

    assert answer.to_engine() == ids
    assert Answer.model_validate_json(answer.model_dump_json()) == answer
    with pytest.raises(ValueError):
        Answer(seq=0, kind=DecisionKind.PAY_MANA, player="alice", accept=False, card_ids=ids)
    plain = Answer(seq=0, kind=DecisionKind.PAY_MANA, player="alice", accept=True)
    assert plain.to_engine() is True


def test_summoners_pact_is_paid_from_untapped_forests_at_upkeep():
    """The second funnel: "pay {2}{G}{G}. If you don't, you lose the game"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Summoner's Pact"],
            battlefield=["Forest", "Forest", "Forest", "Forest"],
            library=["Primeval Titan", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Summoner's Pact")
    scenario.will_pay_the_mana_cost(True, username="alice", source="Summoner's Pact")

    advance_to_next_upkeep_of(scenario, "alice")

    assert scenario.game.is_in_game("alice")
    assert scenario.game.winner is None
    forests = [s for s in scenario.game.battlefield if s.name == "Forest"]
    assert all(forest.tapped for forest in forests)
