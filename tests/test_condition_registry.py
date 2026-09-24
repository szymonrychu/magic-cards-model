"""The one condition reader (`machines/conditions`): its contract, and the
hooks every rules path that asks a printed condition goes through.

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 603.4** - an intervening "if" is checked as the trigger event occurs,
  and the ability triggers only if it is true; **CR 608.2a** checks it again
  as the ability resolves.
- **CR 602.1b** - activation instructions "may state which players can
  activate that ability, may restrict when a player can activate the
  ability ... It functions at all times."
- **CR 602.5b** - a restriction on an activated ability's use "continues to
  apply to that object even if its controller changes".

The contract under test: a reader that claims a clause always answers True or
False (False when the context it needs is missing, such as no event), and only
a clause nobody claims answers None - the one answer every caller turns into
a fail-closed notice.
"""

import pytest

from magic_cards_model.machines import Step, TriggerEvent, conditions
from magic_cards_model.machines.abilities import (
    ActivatedAbility,
    TriggeredAbility,
    parse_abilities,
)
from magic_cards_model.machines.conditions import ConditionContext, ConditionReader
from magic_cards_model.machines.triggers import (
    GameEvent,
    intervening_if_answer,
    intervening_if_holds,
    intervening_if_readable,
)
from magic_cards_model.models import Game, Player, Zone
from magic_cards_model.models.game import condition_is_readable
from tests.cards import card, card_state
from tests.scenarios.harness import Scenario


def _two_player_game() -> Game:
    game = Game(
        players=[Player(username="alice"), Player(username="bob")],
        schema_version=Game.CURRENT_SCHEMA_VERSION,
    )
    return game


def _on_battlefield(game: Game, name: str, controller: str = "alice"):
    state = card_state(name, Zone.BATTLEFIELD, controller=controller, owner=controller)
    state.bind_to_game(game)
    game.battlefield.append(state)
    return state


def _triggered(name: str) -> TriggeredAbility:
    (ability,) = [a for a in parse_abilities(card(name)) if isinstance(a, TriggeredAbility)]
    return ability


def _activated(name: str, index: int = 0) -> ActivatedAbility:
    return [a for a in parse_abilities(card(name)) if isinstance(a, ActivatedAbility)][index]


# -- the contract ----------------------------------------------------------


def test_every_family_module_exports_a_tuple_of_readers():
    for module in (
        conditions.timing,
        conditions.board,
        conditions.cast_record,
        conditions.history,
        conditions.player,
        conditions.objects,
    ):
        assert isinstance(module.READERS, tuple)
        assert all(isinstance(reader, ConditionReader) for reader in module.READERS)


def test_an_unclaimed_clause_answers_none_and_is_not_claimed():
    game = _two_player_game()
    context = ConditionContext(game=game, controller="alice")
    assert conditions.read_condition(context, "the moon is made of green cheese") is None
    assert not conditions.claims("the moon is made of green cheese")


def test_a_claimed_clause_always_answers_a_bool():
    scenario = Scenario().player("alice").player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    assert conditions.claims("it's your turn")
    assert conditions.read_condition(ConditionContext(game, "alice"), "it's your turn") is True
    assert conditions.read_condition(ConditionContext(game, "bob"), "it's your turn") is False
    assert conditions.read_condition(ConditionContext(game, "bob"), "it's not your turn") is True


def test_a_claimed_clause_with_its_context_missing_answers_false_not_none():
    """ "It's not their turn" names the event's player; with no event there is
    nobody to ask about, and the claimed reader says False rather than None."""
    game = _two_player_game()
    context = ConditionContext(game=game, controller="alice", event=None)
    assert conditions.claims("it's not their turn")
    assert conditions.read_condition(context, "it's not their turn") is False


def test_game_condition_holds_falls_back_to_the_registry():
    scenario = Scenario().player("alice").player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.game.condition_holds("alice", "it's your main phase") is True
    assert scenario.game.condition_holds("bob", "it's your main phase") is False
    assert condition_is_readable("it's your main phase")
    assert not condition_is_readable("the moon is made of green cheese")


# -- the compound combinator (C1) --------------------------------------------


def test_a_compound_is_claimed_only_when_every_half_is():
    assert conditions.claims("you attacked this turn and a creature died this turn")
    assert conditions.claims("it's your turn or a creature died this turn")
    assert not conditions.claims("you attacked this turn and the moon is made of green cheese")


def test_and_is_all_and_or_is_any():
    scenario = Scenario().player("alice").player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    alice = ConditionContext(game, "alice")
    assert conditions.read_condition(alice, "it's your turn and a creature died this turn") is False
    assert conditions.read_condition(alice, "it's your turn or a creature died this turn") is True
    game.creatures_died_this_turn = 1
    assert conditions.read_condition(alice, "it's your turn and a creature died this turn") is True
    bob = ConditionContext(game, "bob")
    assert conditions.read_condition(bob, "it's your turn or if a creature died this turn") is True
    assert (
        conditions.read_condition(bob, "it's your turn and the moon is made of green cheese")
        is None
    )


# -- the triggered hook: CR 603.4 / CR 608.2a -------------------------------


def test_intervening_if_answer_is_none_only_for_an_unclaimed_clause():
    game = _two_player_game()
    raptor = _on_battlefield(game, "Scytheclaw Raptor")
    ability = _triggered("Scytheclaw Raptor")
    # No event: "their" has nobody to name - claimed, so False, not None.
    assert intervening_if_answer(game, ability, raptor, None) is False
    unread = ability.model_copy(update={"intervening_if": "the moon is made of green cheese"})
    assert intervening_if_answer(game, unread, raptor, None) is None
    assert game.intervening_if_notices == []
    assert intervening_if_holds(game, unread, raptor, None) is False
    assert [notice.clause for notice in game.intervening_if_notices] == [
        "the moon is made of green cheese"
    ]


def test_intervening_if_answer_reads_the_event_player():
    game = _two_player_game()
    game.turn.step = Step.PRECOMBAT_MAIN
    raptor = _on_battlefield(game, "Scytheclaw Raptor")
    ability = _triggered("Scytheclaw Raptor")
    on_their_turn = GameEvent(event=TriggerEvent.CAST_SPELL, player="alice")
    off_their_turn = GameEvent(event=TriggerEvent.CAST_SPELL, player="bob")
    assert game.turn.active_player == "alice"
    assert intervening_if_answer(game, ability, raptor, on_their_turn) is False
    assert intervening_if_answer(game, ability, raptor, off_their_turn) is True


def test_a_builtin_board_condition_now_reads_as_an_intervening_if():
    """`Game.condition_holds` already read "you attacked this turn"; the
    intervening-if path never asked it. It does now, through the registry's
    fallback, so a half read today is a whole clause read too."""
    game = _two_player_game()
    hellion = _on_battlefield(game, "Scytheclaw Raptor")
    clause = _triggered("Scytheclaw Raptor").model_copy(
        update={"intervening_if": "you attacked this turn"}
    )
    assert intervening_if_answer(game, clause, hellion, None) is False
    game.record_turn_fact("attacked", "alice")
    assert intervening_if_answer(game, clause, hellion, None) is True


def test_intervening_if_readable_probes_a_printing():
    assert intervening_if_readable(card("Scytheclaw Raptor"), _triggered("Scytheclaw Raptor"))
    unread = _triggered("Scytheclaw Raptor").model_copy(
        update={"intervening_if": "the moon is made of green cheese"}
    )
    assert not intervening_if_readable(card("Scytheclaw Raptor"), unread)
    # A trigger with no intervening if at all has nothing to be unread.
    no_if = _triggered("Scytheclaw Raptor").model_copy(update={"intervening_if": None})
    assert intervening_if_readable(card("Scytheclaw Raptor"), no_if)


# -- the activated hook: CR 602.1b ------------------------------------------


def test_unread_activation_restrictions_is_empty_when_every_sentence_is_read():
    game = _two_player_game()
    sundial = _on_battlefield(game, "Sundial of the Infinite")
    assert game.unread_activation_restrictions(_activated("Sundial of the Infinite"), sundial) == []
    vortex = _on_battlefield(game, "Detention Vortex")
    assert game.unread_activation_restrictions(_activated("Detention Vortex"), vortex) == []


def test_unread_activation_restrictions_names_each_unread_sentence():
    game = _two_player_game()
    sundial = _on_battlefield(game, "Sundial of the Infinite")
    ability = _activated("Sundial of the Infinite").model_copy(
        update={"instructions": "Activate only during a full moon."}
    )
    assert game.unread_activation_restrictions(ability, sundial) == [
        "Activate only during a full moon"
    ]
    unread_if = _activated("Sundial of the Infinite").model_copy(
        update={"instructions": "Activate only if the moon is made of green cheese."}
    )
    assert game.unread_activation_restrictions(unread_if, sundial) == [
        "Activate only if the moon is made of green cheese"
    ]


def test_an_unread_instruction_refuses_the_activation_with_the_engines_reason():
    scenario = (
        Scenario().player("alice", battlefield=["Sundial of the Infinite", "Plains"]).player("bob")
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sundial = scenario.creature("Sundial of the Infinite", "alice")
    game = scenario.game
    ability = _activated("Sundial of the Infinite").model_copy(
        update={"instructions": "Activate only during a full moon."}
    )
    refusal = game.activation_instruction_refusal(ability, sundial, "alice", index=0)
    assert refusal is not None
    assert "Activate only during a full moon" in refusal
    assert "CR 602.1b" in refusal


# -- the per-turn count ledger ------------------------------------------------


def test_the_turn_count_ledger_counts_and_rolls_over_with_the_turn():
    scenario = Scenario().player("alice").player("bob").manual_turn_based_actions().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    assert game.turn_count("combat_phases", "alice") == 0
    game.note_turn_count("widgets", "alice")
    game.note_turn_count("widgets", "alice", 2)
    assert game.turn_count("widgets", "alice") == 3
    assert game.turn_count("widgets", "bob") == 0

    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # bob's untap step: a new turn
    assert game.turn_count("widgets", "alice") == 0
    assert game.turn_count("widgets", "alice", last_turn=True) == 3


def test_the_ledger_survives_a_round_trip():
    scenario = Scenario().player("alice").player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.note_turn_count("widgets", "alice", 2)
    decoded = Game.model_validate(scenario.game.model_dump(mode="json"))
    assert decoded.turn_count("widgets", "alice") == 2


def test_beginning_a_combat_phase_is_counted():
    scenario = Scenario().player("alice").player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.advance()  # beginning of combat
    assert scenario.step is Step.BEGINNING_OF_COMBAT
    assert scenario.game.turn_count("combat_phases", "alice") == 1


def test_every_emitted_event_reaches_the_history_hook(monkeypatch: pytest.MonkeyPatch):
    seen: list[GameEvent] = []
    monkeypatch.setattr(conditions.history, "record", lambda game, event: seen.append(event))
    scenario = Scenario().player("alice").player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.advance()
    assert any(event.event is TriggerEvent.BEGINNING_OF_STEP for event in seen)
