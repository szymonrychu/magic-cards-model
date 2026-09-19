"""Vizier of Remedies' -1/-1 counter reducer (`_counter_amount_applies`,
`machines/replacement.py`) gates on "a creature you control" by reading the
computed board (CR 613.5), not the printed type line.

`tests/scenarios/test_vizier_of_remedies.py` already covers the ordinary case
- Devoted Druid, a printed creature, is one either way. This file is about
the disagreement: a permanent earthbend (CR 701.66a) already made a creature
"in addition to its other types" (CR 205.1b) is a creature you control for
Vizier's own "if one or more -1/-1 counters would be put on a creature you
control" (CR 614.16), whatever its printed type line says.

CR numbers already verified this session: CR 613.5, CR 613.1d, CR 205.1b,
CR 701.66a. CR 614.16's own wording is quoted from `test_vizier_of_remedies.py`,
which verified it in the session that wrote that file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _board_with_vizier_and_an_animated_land():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Badgermole Cub"],
            battlefield=["Vizier of Remedies", "Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest", "Forest", username="alice")
    pay_sources, target_forest = forests[:2], forests[2]
    scenario.choose_trigger_targets("Badgermole Cub", [target_forest])
    scenario.cast_and_resolve("Badgermole Cub", *pay_sources, username="alice")
    scenario.pass_until_resolved()
    return scenario, target_forest


def test_vizier_reduces_a_minus_one_counter_placed_on_an_animated_land():
    """The positive case: the animated Forest is a creature on the computed
    board only (printed type line is still just Land), and Vizier's own
    replacement still has to see it.
    """
    scenario, animated = _board_with_vizier_and_an_animated_land()
    assert scenario.game.characteristics_of(animated).is_creature
    assert not animated.is_creature, "the printed type line is still just Land"

    scenario.game.add_counters(animated, Counter.MINUS_ONE, 1)

    assert animated.counters[Counter.MINUS_ONE] == 0, "CR 614.16: minus one is zero"


def test_vizier_does_not_touch_a_minus_one_counter_on_a_plain_land():
    """The inverse: an ordinary, unanimated land you control is not a
    creature by any reading, and Vizier's "creature you control" gate must
    still refuse it - the fix must not turn every permanent into a creature.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Vizier of Remedies", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    assert not scenario.game.characteristics_of(forest).is_creature

    scenario.game.add_counters(forest, Counter.MINUS_ONE, 1)

    assert forest.counters[Counter.MINUS_ONE] == 1, "not a creature, so Vizier is silent"
