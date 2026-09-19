"""Vorinclex, Voice of Hunger's second triggered ability: "Whenever an
opponent taps a land for mana, that land doesn't untap during its
controller's next untap step."

Two gaps, both read generally rather than for this one printing:

- **The condition.** `machines/triggers._controller_clause_holds` only ever
  recognised "an opponent **controls**"/"your opponents **control**"
  (CR 613.5's board-control question), never a different verb such as
  "taps" - the same class of bug `test_jin_gitaxias.py`
  (`TriggerEvent.CAST_SPELL`) and `test_sheoldred_pair.py`
  (`_step_matches`) already fixed for their own event branches. This file
  closes the `TriggerEvent.TAPPED_FOR_MANA` branch the same way: an "an
  opponent" fallback ahead of the shared helper, checked with CR 106.12a's
  own subject id (`event.subject_controller`) rather than `_controller_
  clause_holds`'s narrower vocabulary.
- **The effect.** "That land" is CR 607.1's own anaphora back to the very
  land `TriggerEvent.TAPPED_FOR_MANA` just named (`GameEvent.subject_id`),
  not a target (CR 601.2c never validates it - there is no "target" word in
  the sentence). "Doesn't untap during its controller's next untap step" is
  CR 701.43a's own exert wording, applied here by another permanent's
  ability instead of paid as the tapped permanent's own activation cost -
  `CardState.exerted`/`.untap` already carries exactly this meaning for
  `_parse_tap_target_then_no_untap_clause` (Tamiyo, Compleated Sage's `+1`),
  reused rather than duplicated.

Generality: nothing else in the pool prints "whenever an opponent taps a
land for mana" (or "creature"/a subtype), so this wave proves the fix on
Vorinclex, Voice of Hunger itself, played against a plain land rather than
one of that trigger's own two other printings.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

VOICE_OF_HUNGER = "Vorinclex, Voice of Hunger"


def board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[VOICE_OF_HUNGER])
        .player("bob", battlefield=["Forest"])
    )


def test_an_opponents_tapped_land_does_not_untap_next_untap_step():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while not (scenario.step is Step.PRECOMBAT_MAIN and scenario.turn.active_player == "bob"):
        scenario.advance()
    (forest,) = scenario.untapped_sources("Forest", username="bob")

    scenario.activate(forest)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Vorinclex, Voice of Hunger's triggered ability"]
    scenario.pass_until_resolved()

    assert forest.exerted is True
    assert forest.tapped is True

    while not (scenario.step is Step.UNTAP and scenario.turn.active_player == "bob"):
        scenario.advance()
    scenario.game.untap_step()  # manual_turn_based_actions(): run it explicitly

    assert forest.tapped is True  # exert kept it from untapping
    assert forest.exerted is False  # CR 701.43b: spent, not carried further


def test_alices_own_tapped_land_is_unaffected():
    """Vorinclex names "an opponent", never its own controller's taps."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[VOICE_OF_HUNGER, "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.untapped_sources("Forest", username="alice")

    scenario.activate(forest)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert forest.exerted is False
    assert forest.zone is Zone.BATTLEFIELD
