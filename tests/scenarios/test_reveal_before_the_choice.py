"""A revealed card is shown before the player decides anything about it.

Battle report B4-04: casting Malevolent Rumble paused on its "you may put a
permanent card from among them into your hand" with `cards: []`, and neither
seat had any record of the four cards while the question waited. The player was
asked blind, and the opponent never saw what was revealed.

Rules read in full with `mise run rules:find` this session:

- **CR 701.20a** - "To reveal a card, show that card to all players for a brief
  time. If an effect causes a card to be revealed, it remains revealed for as
  long as necessary to complete the parts of the effect that card is relevant
  to."
- **CR 608.2c** - the instructions are followed in the order written: the
  reveal is the first sentence, the choice the second.
- **CR 608.2d** - the choice is made while the effect applies.

What is asserted here is the *order* and the *decision fields*: at the moment
each question is put (a paused seat sees exactly that moment), the cards are
already recorded as publicly revealed, and the question names the cards it is
about. The records themselves, the hand carry, and the template reader are the
battle-3 reveal-to-hand work (`test_reveal_top_n_put_one_into_hand.py`).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import Answer, DecisionKind, DecisionPending
from magic_cards_model.models import Game, Zone
from tests.scenarios.harness import Scenario


def _rumble(library: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Malevolent Rumble"], battlefield=["Forest", "Forest"], library=library
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.cast_onto_stack("Malevolent Rumble", *forests)
    return scenario


def _known_ids(game: Game, viewer: str) -> set:
    return {entry.card_id for entry in game.known_to(viewer) if entry.zone is Zone.LIBRARY}


def _public_reveal_ids(game: Game) -> list:
    return [
        r.card_id for r in game.reveals if r.source == "Malevolent Rumble" and r.viewers is None
    ]


LIBRARY = ["Eldrazi Temple", "Lightning Bolt", "Forest", "Mishra's Bauble", "Island"]


def test_the_cards_are_revealed_before_the_may_is_asked():
    scenario = _rumble(LIBRARY)
    temple, bolt, forest, bauble = scenario.top_of_library(4)
    scenario.game.decisions.pause_when_unanswered = True

    with pytest.raises(DecisionPending) as excinfo:
        scenario.resolve_top()

    decision = excinfo.value.pending.decision
    assert decision.kind is DecisionKind.MAY
    assert decision.player == "alice"
    assert set(decision.cards) == {temple.id, forest.id, bauble.id}
    assert set(decision.card_labels) == {"Eldrazi Temple", "Forest", "Mishra's Bauble"}
    # The half-applied game a paused seat is served: all four already shown.
    four = {temple.id, bolt.id, forest.id, bauble.id}
    assert set(_public_reveal_ids(scenario.game)) == four
    assert _known_ids(scenario.game, "bob") >= four
    assert _known_ids(scenario.game, "alice") >= four


def test_the_card_choice_is_asked_with_the_cards_still_revealed():
    scenario = _rumble(LIBRARY)
    temple, bolt, forest, bauble = scenario.top_of_library(4)
    scenario.game.decisions.begin_replay([])
    snapshot = scenario.game.model_dump(mode="json")
    scenario.game.decisions.pause_when_unanswered = True
    with pytest.raises(DecisionPending) as first:
        scenario.resolve_top()

    restored = Game.model_validate(snapshot)
    restored.decisions.begin_replay(
        [Answer(seq=first.value.pending.seq, kind=DecisionKind.MAY, player="alice", accept=True)]
    )
    restored.decisions.pause_when_unanswered = True
    with pytest.raises(DecisionPending) as second:
        restored.resolve_top()

    choice = second.value.pending.decision
    assert choice.kind is DecisionKind.CHOOSE_CARDS
    assert set(choice.cards) == {temple.id, forest.id, bauble.id}
    assert choice.amount == 1
    assert _known_ids(restored, "bob") >= {temple.id, bolt.id, forest.id, bauble.id}


def test_with_no_permanent_card_revealed_nothing_is_asked_and_all_four_are_still_shown():
    scenario = _rumble(["Lightning Bolt", "Shock", "Opt", "Brainstorm", "Island"])
    four = {state.id for state in scenario.top_of_library(4)}

    scenario.resolve_top()

    assert set(_public_reveal_ids(scenario.game)) == four
    assert not [d for d in scenario.questions_asked() if d.source == "Malevolent Rumble"], (
        "no permanent card to take: CR 608.2d has no choice to put"
    )


def test_an_off_pool_card_with_the_same_template_reveals_before_it_asks():
    """Commune with the Gods prints the same three sentences with a different
    count and quality ("Reveal the top five cards of your library. You may put
    a creature or enchantment card from among them into your hand. Put the rest
    into your graveyard."), so it is read by the same template and shows every
    card before the question, which names only the qualifying ones."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Commune with the Gods"],
            battlefield=["Forest", "Forest"],
            library=["Lightning Bolt", "Satyr Wayfinder", "Forest", "Opt", "Island", "Shock"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.cast_onto_stack("Commune with the Gods", *forests)
    top_five = scenario.top_of_library(5)
    wayfinder = top_five[1]
    scenario.game.decisions.pause_when_unanswered = True

    with pytest.raises(DecisionPending) as excinfo:
        scenario.resolve_top()

    decision = excinfo.value.pending.decision
    assert decision.kind is DecisionKind.MAY
    assert decision.cards == (wayfinder.id,)
    five = {state.id for state in top_five}
    public = {
        r.card_id
        for r in scenario.game.reveals
        if r.source == "Commune with the Gods" and r.viewers is None
    }
    assert public == five
    assert _known_ids(scenario.game, "bob") >= five
