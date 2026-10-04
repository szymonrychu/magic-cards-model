""" "Activate only if there are twenty-five or more loyalty counters among
Jaces you control." - Jace, Reality Sculptor's own `0` ability.

`_CONDITION_LOYALTY_AMONG_NAMED` (`models/game.py`) sums `CardState.loyalty`
across every battlefield permanent the ability's controller controls that
shares one printed name, and is checked by `Game.condition_holds` /
`_activation_condition_holds`, which `why_cannot_activate` and
`begin_activating` both refuse an unmet CR 602.5b restriction through.

Here "Jaces" reads as CR 201.5's own plural of a printed name: the objects
this counts are permanents named exactly "Jace" - the token CR 701.71a's
Empower Jace keyword action creates (`models/token.py`'s `JACE` predefined
token, `name="Jace"`), not "Jace, Reality Sculptor" itself, whose own printed
name is longer. Jace, Reality Sculptor's own `+1` ("Empower Jace X, where X
is the number of Islands you control.") and cards like **Academic Ascent**
("Empower Jace 2.") are the intended way to build that total up over several
turns; this file skips the build-up and puts the loyalty on directly with
`Game.add_counters`, the same staging `test_counters.py` and
`test_loyalty_abilities.py` already use, to reach the 24/25 boundary without
several real activations.

`numbers.py` gained compound number words above twenty
(`_parse_compound_tens`/`_TENS`/`_ONES`) for this printing's own "twenty-five"
- not tested directly here, since this file is about the activation gate, not
the number reader, but its result is what `parse_count` hands the condition.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file: CR 602.5b, 306.5c, 704.5i.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario

JACE = "Jace, Reality Sculptor"
ACADEMIC_ASCENT = "Academic Ascent"


def _board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[JACE, "Plains", "Plains", "Llanowar Elves"],
            hand=[ACADEMIC_ASCENT],
        )
        .player("bob")
    )


def _make_jace_token(scenario):
    """Cast Academic Ascent ("Empower Jace 2.") to create the one Jace
    planeswalker token this file puts loyalty on."""
    elves = scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "alice")
    sources = scenario.untapped_sources("Plains", "Plains", username="alice")
    scenario.cast_and_resolve(ACADEMIC_ASCENT, *sources, targets=[elves], username="alice")
    return scenario.find("Jace", Zone.BATTLEFIELD, "alice")


def test_below_twenty_five_total_loyalty_refuses_the_activation():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jace_rs = scenario.find(JACE, Zone.BATTLEFIELD, "alice")
    token = _make_jace_token(scenario)
    assert token.counter_count(Counter.LOYALTY) == 2
    scenario.game.add_counters(token, Counter.LOYALTY, 17)  # 2 + 17 + the sculptor's 5 = 24

    reason = scenario.why_cannot_activate(jace_rs, index=2, username="alice")

    assert reason is not None
    assert "activation restriction" in reason

    with pytest.raises(ValueError):
        scenario.activate(jace_rs, index=2, username="alice")


def test_twenty_five_or_more_total_loyalty_makes_the_activation_legal():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jace_rs = scenario.find(JACE, Zone.BATTLEFIELD, "alice")
    token = _make_jace_token(scenario)
    scenario.game.add_counters(token, Counter.LOYALTY, 18)  # 2 + 18 + the sculptor's 5 = 25

    reason = scenario.why_cannot_activate(jace_rs, index=2, username="alice")
    assert reason is None

    ability = scenario.activate(jace_rs, index=2, username="alice")  # does not raise

    assert ability is not None
    assert ability in scenario.game.stack
    assert scenario.stack_names() == [f"{JACE}'s activated ability"]
