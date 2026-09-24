"""Board conditions: what is on the battlefield, who controls it, and how much
of it there is (CR 613.5: every count reads the computed board).

Each reader here is a `ConditionReader` registered through `READERS`; see
`machines/conditions/__init__.py` for the contract every reader keeps. Counts go
through `magic_cards_model.numbers`; qualities through `models/game.py`'s own
`_characteristic_word`.

Rules verified with `mise run rules:find`:

- CR 613.5: "The application of continuous effects as described by the layer
  system is continually and automatically performed by the game."
- CR 111.1: a token is a marker used to represent a permanent that isn't
  represented by a card - "token"/"nontoken" is asked of the object itself,
  not of its characteristics.
"""

import re
from collections import Counter
from typing import TYPE_CHECKING

from ...numbers import COUNT, parse_count
from . import ConditionReader

if TYPE_CHECKING:
    from ...models.card_state import CardState
    from . import ConditionContext


def _same_name_as_one_another(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you control N or more <quality> with the same name as one another"
    (Chrome Replicator's "two or more nonland, nontoken permanents",
    Mechanized Production's "eight or more artifacts"): some one name is
    shared by at least N of the permanents you control that have the quality.
    A quality word the characteristic reader cannot read makes the whole
    clause false rather than guessed."""
    from ...models.game import _characteristic_word

    needed = parse_count(match.group("count"))
    if needed is None:
        return False
    words = [word for word in re.split(r"[,\s]+", match.group("quality")) if word]
    if not words:
        return False
    *qualifiers, noun = words
    object_tests: list = []
    characteristic_tests: list = []
    for word in qualifiers + ([] if noun in ("permanent", "permanents") else [noun]):
        if word in ("token", "tokens", "nontoken"):
            wanted = word != "nontoken"
            object_tests.append(lambda state, wanted=wanted: bool(state.token) == wanted)
            continue
        test = _characteristic_word(word)
        if test is None:
            return False
        characteristic_tests.append(test)
    game = context.game
    board = game.computed_board()

    def has_quality(state: "CardState") -> bool:
        chars = board.of(state)
        return all(test(state) for test in object_tests) and all(
            test(chars) for test in characteristic_tests
        )

    names = Counter(
        board.of(state).name
        for state in game.permanents_controlled_by(context.controller)
        if has_quality(state)
    )
    return any(count >= needed for count in names.values())


READERS: tuple[ConditionReader, ...] = (
    ConditionReader(
        re.compile(
            rf"you control (?P<count>{COUNT}) or more (?P<quality>[a-z, -]+?) "
            r"with the same name as one another"
        ),
        _same_name_as_one_another,
    ),
)
