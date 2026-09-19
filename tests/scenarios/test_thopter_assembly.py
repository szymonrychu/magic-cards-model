"""Scenario: Thopter Assembly - "At the beginning of your upkeep, if you
control no Thopters other than this creature, return this creature to its
owner's hand and create five 1/1 colorless Thopter artifact creature tokens
with flying."

This is the reported card `_parse_return_self_then_create_tokens_clause`
generalizes (G14-2 of the number sweep): both halves of the trigger, in
printed order, off a whole-text parser rather than a `TRIGGER_EFFECTS` row
keyed to this card's name - no scenario test previously exercised the actual
resolution (return plus token creation) through a real board.

Every CR number here was already verified by the parser's own docstring:

- **CR 603.6a** - a permanent's own "at the beginning of" ability triggers
  when that step or phase begins.
- **CR 401** - CR 401.2's return to hand.
- **CR 111.9** - a spell or ability that creates a token puts it onto the
  battlefield already there, not through any zone it would otherwise pass
  through.
- **CR 608.2c** - the controller of the ability follows its instructions in
  the order written: the return, then the token creation.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def test_thopter_assembly_returns_to_hand_and_creates_five_thopters():
    scenario = Scenario().player("alice", battlefield=["Thopter Assembly", "Forest"]).build()
    # `start_at` teleports straight to a step without crossing into it, so a
    # "beginning of step" trigger already on the battlefield would never be
    # raised that way - advancing through the real turn machine from untap is
    # what actually crosses into upkeep and raises the trigger (CR 603.6a).
    assert scenario.step is Step.UNTAP
    scenario.advance()
    assert scenario.step is Step.UPKEEP
    scenario.pass_until_resolved()  # the upkeep trigger

    alice = scenario.player("alice")
    assert "Thopter Assembly" in [c.name for c in alice.hand], "CR 401.2: returned to hand"
    thopters = [
        state
        for state in scenario.game.battlefield
        if state.name == "Thopter Token" and state.controller == "alice"
    ]
    assert len(thopters) == 5, "five 1/1 colorless Thopter tokens, CR 111.9"
    for thopter in thopters:
        assert (thopter.power, thopter.toughness) == (1, 1)
        assert "Flying" in thopter.keywords
