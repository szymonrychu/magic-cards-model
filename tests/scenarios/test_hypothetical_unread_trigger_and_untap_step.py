"""Two questions the merge of e1-land-helpers and dressdown-self-sac raises
about `machines/hypothetical.py`'s read-only "what if" answers.

**Does the new `UnmodeledTriggerEffectNotice` leak into a hypothetical
answer?** `Game._note_unread_trigger` (`models/game.py`) now records a notice
on `Game.unmodeled_trigger_effect_notices` whenever a triggered ability
resolves with no reader for its effect text. `hypothetical._resolve_choice_free`
resolves every choice-free trigger on its decoded copy through the same
`Game.resolve_top`/`_resolve_ability` path, so an unread trigger set off by a
hypothetical land - Territorial Bruntar's landfall, unreadable per
`docs/engine-coverage.md`'s "Reading '[exile or choose some cards]. Until end
of turn ...'" row - resolves on that copy too, appending to *the copy's own*
`unmodeled_trigger_effect_notices`. It does not reach the caller: `_settle`
builds `EntersPrediction`/`Payability.notices` only from triggers left
unresolved for a real choice (`_resolve_choice_free`'s `skipped`) and the
settle-pass bound message, never from the copy's
`unmodeled_trigger_effect_notices` - and `predict_enters`/`payability` return
pure data (ids and strings, `EntersPrediction`/`Payability`), never the copy
itself, so there is no other channel back. A land whose own entering-tapped
line is unmodeled already fails closed through a different, existing
mechanism (`replacement.unread_self_enters_tapped_lines`,
`_evaluate_land`'s `unread` branch) - that one is deliberate and unrelated to
this notice. So the new notice does not make `predict_enters`/`payability`
fail closed for a land whose own entering is fully read but whose side
effects (someone else's landfall trigger) are not: the land's state is
reported correctly and unread text on triggers other than the land's own is
silently dropped on the copy, exactly as it always was before this notice
existed - `_resolve_choice_free` already treated a `None` effect as "resolved"
with no trace, before and after this merge.

**Does the untap-step count event fire inside a hypothetical copy?**
`ExtraTriggerEvent.UNTAPPED_DURING_UNTAP_STEP` (CR 502.3, `The Millennium
Calendar`) is raised from exactly one place, `Game._untap_step_impl`, which
only runs from `Game.untap_step` as part of the real turn structure.
`hypothetical.py` never calls either: a hypothetical land enters through
`Game.put_onto_battlefield`, not through an untap step, so nothing here can
ever raise that event. Confirmed below by predicting a land's entry on a copy
with The Millennium Calendar on the battlefield and an Amulet of Vigor that
untaps the entering land outside the untap step (CR 614.12a replacement,
CR 603.3 trigger) - a different untap than CR 502.3's - and checking no time
counters appear.

CR numbers read with `mise run rules:find` in the session that wrote this
file: 502.3, 603.3, 608.2, 614.12a.
"""

from magic_cards_model.machines import EntersState, Step, payability, predict_enters
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

CALENDAR = "The Millennium Calendar"


def _board(hand=(), battlefield=(), library=("Island",)):
    scenario = (
        Scenario()
        .player("alice", hand=list(hand), battlefield=list(battlefield), library=list(library))
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_an_unread_landfall_trigger_does_not_leak_into_the_prediction():
    scenario = _board(hand=["Island"], battlefield=["Territorial Bruntar"])
    before = scenario.game.model_dump_json()
    island = scenario.find("Island", Zone.HAND, "alice")

    prediction = predict_enters(scenario.game, "alice", island)

    assert prediction.state is EntersState.UNTAPPED
    assert not any("Territorial Bruntar" in notice for notice in prediction.notices)
    assert not any("exile cards from the top" in notice.lower() for notice in prediction.notices)
    assert scenario.game.model_dump_json() == before
    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_an_unread_landfall_trigger_does_not_leak_into_payability():
    scenario = _board(
        hand=["Psychic Frog", "Island"],
        battlefield=["Swamp", "Territorial Bruntar"],
    )
    island = scenario.find("Island", Zone.HAND, "alice")
    frog = scenario.find("Psychic Frog", Zone.HAND, "alice")

    report = payability(scenario.game, "alice", frog, assuming_land=island)

    assert not any("Territorial Bruntar" in notice for notice in report.notices)
    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_the_untap_step_count_event_does_not_fire_on_a_hypothetical_copy():
    scenario = _board(
        hand=["Undercity Sewers"],
        battlefield=[CALENDAR, "Amulet of Vigor"],
    )
    before = scenario.game.model_dump_json()
    calendar_before = scenario.find(CALENDAR, Zone.BATTLEFIELD, "alice").counter_count("time")
    assert calendar_before == 0
    sewers = scenario.find("Undercity Sewers", Zone.HAND, "alice")

    prediction = predict_enters(scenario.game, "alice", sewers)

    # Amulet of Vigor untaps the surveil land as it enters (CR 603.3), a
    # different untap than CR 502.3's untap step - the calendar's condition
    # ("during your untap step") is not met, so nothing is counted even
    # though the copy did resolve a real, choice-free untap trigger.
    assert prediction.state is EntersState.TAPPED
    assert any("Amulet of Vigor" in notice for notice in prediction.notices)
    assert not any(CALENDAR in notice for notice in prediction.notices)
    assert scenario.game.model_dump_json() == before
    assert (
        scenario.find(CALENDAR, Zone.BATTLEFIELD, "alice").counter_count("time") == calendar_before
    )
