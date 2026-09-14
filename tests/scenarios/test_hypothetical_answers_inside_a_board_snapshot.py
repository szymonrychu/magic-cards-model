"""Land-sequencing what-ifs asked from inside an open board snapshot.

A caller that serialises a game's state does it inside `Game.board_snapshot()`
(`snapshot.py`), and that is where a seat would also ask `predict_enters` and
`payability_matrix`. Both answer by decoding a copy of the game and playing
commands and `legal_actions` on the copy (`machines/hypothetical.py`). None
of that may touch the scope on the real game: the answers match the ones
asked outside any scope, the scope keeps serving its one cached board, no
`BoardSnapshotStale` is raised, and the game dump is unchanged.

The board is `test_payability_matrix.py`'s: a rigged deal of a registered
Dimir frog list (pilot SizzleSkeleton, 2026-08-30).
"""

from magic_cards_model.machines import legal_actions, payability_matrix, predict_enters
from magic_cards_model.models import Zone
from tests.scenarios.test_payability_matrix import _board, _lands, _shape


def _matrix_shape(matrix):
    return (
        [_shape(answer) for answer in matrix.now],
        [
            (column.prediction, [_shape(answer) for answer in column.cards])
            for column in matrix.lands
        ],
    )


def test_what_ifs_inside_a_board_snapshot_match_outside_and_keep_the_scope():
    scenario = _board()
    game = scenario.game
    cards = [scenario.find(name, Zone.HAND, "alice") for name in ("Psychic Frog", "Counterspell")]
    lands = _lands(scenario)
    grave = scenario.find("Watery Grave", Zone.HAND, "alice")
    dumped = game.model_dump(mode="json")

    outside_matrix = payability_matrix(game, "alice", cards, lands)
    outside_prediction = predict_enters(game, "alice", grave)
    outside_actions = legal_actions(game, "alice")

    with game.board_snapshot():
        board = game.computed_board()
        inside_matrix = payability_matrix(game, "alice", cards, lands)
        inside_prediction = predict_enters(game, "alice", grave)
        assert game.computed_board() is board
        inside_actions = legal_actions(game, "alice")
        assert game.computed_board() is board

    assert _matrix_shape(inside_matrix) == _matrix_shape(outside_matrix)
    assert inside_prediction == outside_prediction
    assert inside_actions == outside_actions
    assert game.model_dump(mode="json") == dumped
