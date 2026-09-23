"""Urabrask, Heretic Praetor's second triggered ability: "At the beginning
of each opponent's upkeep, the next time they would draw a card this turn,
instead they exile the top card of their library. They may play it this
turn."

CR 603.1's trigger fires at each opponent's upkeep (the same "each opponent's"
step-matching this pool already reads correctly, per `test_sheoldred_pair.py`).
Its own *effect*, when it resolves, is CR 614.1a's "the next time ... would
..., instead ..." shape - a one-shot replacement, installed for the rest of
that turn, that answers only that opponent's very next draw, however it
happens (a draw step, a spell, another ability), not every draw for the rest
of the turn the way Plagiarize's "skip that draw" redirection ("until end of
turn, if ... would draw ..., instead ...", `DrawSkipReplacement`) keeps firing.

Modelled the same way CR 615.8's "next time [a source] would deal damage"
shield already is (`PreventionShield`/`ShieldKind`): a small stored,
data-only record (`NextTimeDrawReplacement`/`DrawReplacementKind`) rather than
a callable, consumed at most once (CR 614.5) and cleared at end of turn
(CR 514.2) if never used.

Generality: Startling Corruption (not in the deck pool, not Urabrask) is
irrelevant here since no other pool card shares this exact template, but the
*play-permission* half is the same primitive Ragavan, Nimble Pilferer and
Emry, Lurker of the Loch already use (`Game.grant_play_permission`,
`_PLAY_PERMISSION_RE`) - only its pronoun vocabulary needed widening from a
literal "you may" to also read "they may"/"that player may", which a
third-person triggered ability's own permission sentence prints generally,
not only on this card.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import why_cannot_cast_from
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone

from .harness import Scenario

URABRASK = "Urabrask, Heretic Praetor"


def board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[URABRASK], library=["Mountain"] * 5)
        .player("bob", battlefield=["Forest"], library=["Elvish Mystic"] * 5)
    )


def test_alices_own_upkeep_installs_no_replacement_for_her():
    scenario = board().build()
    scenario.start_at(Step.UPKEEP)
    scenario.game.put_triggers_on_stack()
    assert scenario.game.stack == []
    assert scenario.game.next_time_draw_replacements == []


def _advance_to_bobs_upkeep(scenario):
    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == "bob"):
        scenario.advance()


def test_bobs_next_draw_this_turn_is_exiled_instead_and_he_may_play_it():
    scenario = board().build()
    scenario.start_at(Step.UPKEEP)
    _advance_to_bobs_upkeep(scenario)

    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Urabrask, Heretic Praetor's triggered ability"]
    scenario.pass_until_resolved()

    assert [r.affected for r in scenario.game.next_time_draw_replacements] == ["bob"]

    top = scenario.player("bob").library[0]
    library_before = len(scenario.player("bob").library)
    hand_before = len(scenario.player("bob").hand)

    scenario.draw(1, "bob")

    assert top.zone is Zone.EXILE
    assert len(scenario.player("bob").library) == library_before - 1
    assert len(scenario.player("bob").hand) == hand_before  # no card was drawn

    # The replacement is spent: it does not also apply to a second draw.
    second_top = scenario.player("bob").library[0]
    scenario.draw(1, "bob")
    assert second_top.zone is Zone.HAND

    # "They may play it this turn." - a real, usable permission (CR 601.3),
    # checked from bob's own main phase so the sorcery-speed timing rule
    # (CR 117.1a) that a creature spell is also subject to is satisfied.
    while not (scenario.step is Step.PRECOMBAT_MAIN and scenario.turn.active_player == "bob"):
        scenario.advance()

    verdict = why_cannot_cast_from(top, "bob", Zone.EXILE, scenario.game)
    assert verdict is None

    actions = legal_actions(scenario.game, "bob")
    assert any(action.card_id == top.id for action in actions)


def test_no_replacement_left_for_alice_when_only_bob_is_the_opponent_upkeep():
    scenario = board().build()
    scenario.start_at(Step.UPKEEP)
    _advance_to_bobs_upkeep(scenario)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert all(r.affected != "alice" for r in scenario.game.next_time_draw_replacements)
