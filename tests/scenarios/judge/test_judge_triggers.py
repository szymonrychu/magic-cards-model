"""Judge scenarios: trigger conditions the engine cannot recognize at all.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#886** - Captain Howler, Sea Scourge + Mind Rot (each cause of discard
  is its own trigger event, and a single "discard two cards" instruction is
  one event carrying a count of two, not two separate events)

Every CR number here was looked up with `knowledge_search(type="rules")`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import (
    AbilityKind,
    TriggeredAbility,
    TriggerEvent,
    parse_abilities,
)
from magic_cards_model.machines.effects import effect_for
from tests.cards import card
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# DDR#886 - "whenever you discard" has no TriggerEvent to match against
# --------------------------------------------------------------------------


def test_captain_howlers_discard_trigger_parses_with_a_discard_event():
    """DDR#886, W14 fix: the condition is now read as `TriggerEvent.
    DISCARDS_A_CARD`, so the trigger really can go on the stack.

    Captain Howler, Sea Scourge (confirmed with `resolve_cards`): "Whenever you
    discard one or more cards, target creature gets +2/+0 until end of turn for
    each card discarded this way. Whenever that creature deals combat damage to
    a player this turn, you draw a card." CR 701.9 is the discard rule the
    episode turns on: a single instruction to discard several cards is one
    event with a count, the same way CR 121.2 makes multiple card draws
    individual events but discard has no such rule - Mind Rot's "discards two
    cards" is one discard, not two. `Game.discard_cards` is the one place that
    now emits `TriggerEvent.DISCARDS_A_CARD`, once per discard *action* with
    `GameEvent.amount` carrying the count, not once per card.
    """
    (ability,) = [
        found
        for found in parse_abilities(card("Captain Howler, Sea Scourge"))
        if found.kind is AbilityKind.TRIGGERED
    ]
    assert isinstance(ability, TriggeredAbility)
    assert "discard" in ability.condition
    assert ability.event is TriggerEvent.DISCARDS_A_CARD


def test_mind_rots_own_discard_clause_now_has_a_scripted_effect():
    """The other half of the setup, now closed: Mind Rot's "Target player
    discards two cards" is exactly `_parse_target_player_discards_clause`'s
    shape in `machines/effects.py` (see `test_target_player_discards.py` for
    the full corner-case coverage of that parser), so `effect_for` no longer
    returns `None` for it, and (W14) that discard now routes through `Game.
    discard_cards`, so Captain Howler's own trigger sees it too.
    """
    assert effect_for("Mind Rot", card("Mind Rot").oracle_text) is not None


def test_mind_rot_causes_captain_howlers_discard_trigger_to_fire_once():
    """DDR#886: Mind Rot's single "discards two cards" instruction is one
    discard event carrying a count of two (CR 701.9), so Captain Howler's
    "Whenever you discard one or more cards" triggers exactly once and reads
    "for each card discarded this way" off that one event - a +4/+0 pump, not
    two separate +2/+0 triggers.

    Mind Rot targets **alice**, not bob: CR 109.5's "you"/"your" on an
    object's text refers to that object's controller - Captain Howler's own
    "whenever you discard" is alice's own discards, since alice controls
    Captain Howler. Aiming Mind Rot at bob instead would correctly leave
    Captain Howler's trigger silent, which is not what this scenario is
    testing.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mind Rot", "Mountain", "Mountain"],
            battlefield=["Swamp", "Swamp", "Swamp", "Captain Howler, Sea Scourge"],
        )
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Mind Rot", auto=True, username="alice", targets=["alice"])
    assert len(scenario.player("alice").hand) == 0
    # `Game.resolve_top` already promotes anything that triggered onto the
    # stack before the caster would next receive priority (CR 704.3, 603.3),
    # so the fired trigger is on `scenario.game.stack`, not still waiting in
    # `pending_triggers` - one entry, not two, confirming the "one or more
    # cards" count-carrying event fired once rather than once per card.
    assert scenario.stack_names() == ["Captain Howler, Sea Scourge's triggered ability"]
