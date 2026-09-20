"""Every hand card against every land, answered as one batch.

`payability_matrix(game, player, cards, lands)` answers the same question
`payability` does for each card now and for each `(card, land)` pair, and the
same `predict_enters` answer for each land, but works on one decoded copy for
"now" and one board per distinct land instead of copying the game for every
pair. A land in the library is the same question as every other copy of the
same printing there, so those are worked out once.

The board is a real registered list: Dimir frog, pilot SizzleSkeleton, event of
2026-08-30, source deck videre-58656338 (`test_dimir_frog_deck.py`). The hand
and library are a rigged deal of that sixty; the three basic lands on the
battlefield are staged on top of it (CR 100.2a puts no limit on basic lands).

Rules: the questions are the ones `test_payability_with_a_hypothetical_land.py`
and `test_predicting_how_a_land_enters.py` cite; batching them changes no
answer, which is what the first test here asserts.
"""

import time
from collections import Counter

from magic_cards_model.machines import Step, hypothetical, payability, payability_matrix
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario
from tests.scenarios.test_dimir_frog_deck import DIMIR_FROG_MAIN

HAND = [
    "Psychic Frog",
    "Thoughtseize",
    "Preordain",
    "Counterspell",
    "Watery Grave",
    "Undercity Sewers",
    "Polluted Delta",
]


def _library():
    left = Counter(DIMIR_FROG_MAIN)
    left.subtract(HAND)
    return [name for name, count in left.items() for _ in range(count)]


def _board():
    scenario = (
        Scenario()
        .player("alice", hand=HAND, battlefield=["Island", "Swamp", "Island"], library=_library())
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _lands(scenario):
    me = scenario.game.player("alice")
    return [card for card in (*me.hand, *me.library) if card.card.is_land]


def _shape(report):
    return (
        report.payable,
        [(o.kind, o.affordable, o.alternative_cost, o.keyword) for o in report.options],
        report.assumed_land,
        report.notices,
    )


def test_the_board_is_seven_in_hand_three_in_play_fifty_three_in_library():
    scenario = _board()
    me = scenario.game.player("alice")

    assert len(me.hand) == 7
    assert len(me.library) == 53
    assert len(scenario.game.battlefield) == 3


def test_the_matrix_agrees_with_one_question_at_a_time():
    scenario = _board()
    game = scenario.game
    cards = [scenario.find(name, Zone.HAND, "alice") for name in ("Psychic Frog", "Preordain")]
    lands = _lands(scenario)

    matrix = payability_matrix(game, "alice", cards, lands)

    for card in cards:
        assert _shape(matrix.get(card.id)) == _shape(payability(game, "alice", card))
        for land in lands:
            single = payability(game, "alice", card, assuming_land=land)
            assert _shape(matrix.get(card.id, land.id)) == _shape(single), (card.name, land.name)


def test_each_land_carries_its_own_prediction():
    scenario = _board()
    lands = _lands(scenario)

    matrix = payability_matrix(scenario.game, "alice", [], lands)

    assert [entry.land_id for entry in matrix.lands] == [land.id for land in lands]
    assert all(entry.prediction.card_id == entry.land_id for entry in matrix.lands)


def test_library_copies_of_one_printing_share_an_answer_but_keep_their_ids():
    scenario = _board()
    frog = scenario.find("Psychic Frog", Zone.HAND, "alice")
    graves = [card for card in scenario.game.player("alice").library if card.name == "Watery Grave"]
    assert len(graves) == 2

    matrix = payability_matrix(scenario.game, "alice", [frog], graves)

    first, second = (matrix.get(frog.id, grave.id) for grave in graves)
    assert first.assumed_land.card_id == graves[0].id
    assert second.assumed_land.card_id == graves[1].id
    assert first.payable == second.payable


def test_a_library_copy_on_top_is_evaluated_on_its_own(monkeypatch):
    """Two library copies of one printing are worked out once (the module
    docstring says so, and the test above proves it) - but they are only
    interchangeable because nothing in the pool reads *which* copy entered.
    A play-from-top effect would read exactly that, and could disagree about
    the copy currently on top. No such card is needed to prove the fix: the
    top copy must get its own evaluation rather than the shared one, which
    this proves by counting real calls to `_evaluate_land` (still the real
    implementation - only counted, never faked), and the matrix must still
    agree with a single call for both the top and the buried copy."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Psychic Frog"],
            battlefield=["Island", "Swamp"],
            library=["Watery Grave", "Island", "Watery Grave"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    frog = scenario.find("Psychic Frog", Zone.HAND, "alice")
    graves = [card for card in scenario.game.player("alice").library if card.name == "Watery Grave"]
    top, buried = graves
    assert scenario.game.player("alice").library[0].id == top.id

    calls: list = []
    real_evaluate_land = hypothetical._evaluate_land

    def counting_evaluate_land(game, player, land):
        calls.append(land.id)
        return real_evaluate_land(game, player, land)

    monkeypatch.setattr(hypothetical, "_evaluate_land", counting_evaluate_land)

    matrix = payability_matrix(scenario.game, "alice", [frog], [top, buried])

    # The top copy is never shared - one call for it, one for the buried
    # copy - rather than the one shared call two same-printing library
    # copies get when neither of them is on top.
    assert calls == [top.id, buried.id]
    assert _shape(matrix.get(frog.id, top.id)) == _shape(
        payability(scenario.game, "alice", frog, assuming_land=top)
    )
    assert _shape(matrix.get(frog.id, buried.id)) == _shape(
        payability(scenario.game, "alice", frog, assuming_land=buried)
    )


def test_a_land_in_hand_is_not_asked_about_itself():
    scenario = _board()
    grave = scenario.find("Watery Grave", Zone.HAND, "alice")

    matrix = payability_matrix(scenario.game, "alice", [grave], [grave])

    assert matrix.get(grave.id, grave.id) is None
    assert matrix.get(grave.id) is not None


def test_asking_mutates_nothing():
    scenario = _board()
    before = scenario.game.model_dump_json()
    me = scenario.game.player("alice")

    payability_matrix(scenario.game, "alice", list(me.hand), _lands(scenario))

    assert scenario.game.model_dump_json() == before


def test_the_whole_hand_against_every_land_is_fast():
    """A guard, not a benchmark: the target is well under 0.5 s, and 3 s keeps
    a slow or loaded CI machine from failing it for noise."""
    scenario = _board()
    me = scenario.game.player("alice")
    lands = _lands(scenario)

    started = time.perf_counter()
    matrix = payability_matrix(scenario.game, "alice", list(me.hand), lands)
    elapsed = time.perf_counter() - started

    assert len(matrix.now) == 7
    assert len(matrix.lands) == len(lands)
    assert elapsed < 3.0, f"payability_matrix took {elapsed:.2f} s"
