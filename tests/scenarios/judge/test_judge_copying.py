"""Judge scenarios: copying a spell (CR 707), which this engine does not do at all.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#951** - Frontline Heroism + Psychotic Fury (a triggered ability that
  creates a token and then copies the spell that triggered it, retargeting the
  copy onto that token)

CR 707.10 is what "copy a spell" means: "put a copy of it onto the stack; a
copy of a spell isn't cast". CR 707.2 is where the copy's values come from: "the
copy acquires the copiable values of the original object's characteristics
and, for an object on the stack, choices made when casting or activating it
(mode, targets, ...)". Nothing in this engine builds that second stack object.
`machines/effects._parse_token_clause` refuses outright the moment it sees
"copy of" in a clause (`return None  # CR 707.2 copying needs copiable values
this wave does not read`), and there is no equivalent clause parser for "copy
that spell"/"copy target spell" anywhere in `machines/effects.py` at all - the
whole vocabulary is simply not there, confirmed directly below rather than
assumed from the absence of a grep hit. Every CR number here was looked up with
`knowledge_search(type="rules")`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.effects import trigger_effect_for
from tests.cards import card
from tests.scenarios.harness import Scenario


def test_frontline_heroisms_copy_clause_produces_no_effect_at_all():
    """DDR#951, the provable half: the trigger's own text never becomes behaviour.

    Frontline Heroism's second ability is "Whenever you cast a spell that
    targets only a single creature you control, create a 1/1 red Soldier
    creature token with haste, then copy that spell. The copy targets that
    token." `trigger_effect_for` is a fail-closed, whole-clause dispatcher the
    same way `machines/effects.py`'s spell-effect parsers are (see
    `docs/scenario-tests.md`'s note on `_parse_targeted_clauses`): a single
    clause it cannot read - "then copy that spell" - throws away the whole
    trigger, token creation included, rather than only the copy.
    """
    heroism = card("Frontline Heroism")
    lines = heroism.oracle_text.split("\n")
    trigger_text = lines[1]
    assert trigger_text.startswith("Whenever you cast a spell")

    effect = trigger_effect_for("Frontline Heroism", TriggerEvent.CAST_SPELL, trigger_text)
    assert effect is None


@pytest.mark.xfail(
    strict=True,
    reason="trigger_effect_for('Frontline Heroism', CAST_SPELL, ...) returns None (proven "
    "above), so casting Psychotic Fury with Frontline Heroism out creates no Soldier token "
    "and casts no copy at all - CR 707.2/707.10 spell copying is not implemented anywhere in "
    "machines/effects.py, so there is nothing to retarget the copy onto in the first place.",
)
def test_frontline_heroism_should_copy_psychotic_fury_onto_a_fresh_token():
    """DDR#951: the copy should hand double strike to a token Kitchen Finks never asked for.

    Psychotic Fury reads "Target multicolored creature gains double strike
    until end of turn. Draw a card." - a legal single-creature target, so
    Frontline Heroism's trigger should fire (CR 603.2), making a 1/1 Soldier
    token and copying Psychotic Fury with its copy retargeted onto that token
    (CR 707.10c: the copy's controller may choose new targets for it). A
    multicolored creature is not itself required to be the *copy's* target,
    since CR 707.10e only forces the copy's target to match the *original's*
    target category when the effect does not specify a new one, and here it
    does; the token receiving double strike despite not being multicolored is
    exactly what tells this apart from Psychotic Fury resolving once, plainly.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Psychotic Fury"],
            battlefield=["Frontline Heroism", "Kitchen Finks", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    finks = scenario.creature("Kitchen Finks", "alice")

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Psychotic Fury", mountain, username="alice", targets=[finks])

    soldiers = [
        state
        for state in scenario.player("alice").battlefield
        if state.name != "Kitchen Finks" and state.name != "Frontline Heroism"
    ]
    assert len(soldiers) == 1, "the trigger should have made a 1/1 Soldier token"
    (token,) = soldiers
    assert token.has_keyword("Double strike"), "the copy should have targeted the token"
