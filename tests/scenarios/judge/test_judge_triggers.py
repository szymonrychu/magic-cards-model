"""Judge scenarios: trigger conditions the engine cannot recognize at all.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#886** - Captain Howler, Sea Scourge + Mind Rot (each cause of discard
  is its own trigger event, and a single "discard two cards" instruction is
  one event carrying a count of two, not two separate events)

Every CR number here was looked up with `knowledge_search(type="rules")`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import AbilityKind, TriggeredAbility, parse_abilities
from magic_cards_model.machines.effects import effect_for
from tests.cards import card
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# DDR#886 - "whenever you discard" has no TriggerEvent to match against
# --------------------------------------------------------------------------


def test_captain_howlers_discard_trigger_parses_with_no_event():
    """DDR#886, the provable half: the condition is read as a trigger, but as
    one that can never fire.

    Captain Howler, Sea Scourge (confirmed with `resolve_cards`): "Whenever you
    discard one or more cards, target creature gets +2/+0 until end of turn for
    each card discarded this way. Whenever that creature deals combat damage to
    a player this turn, you draw a card." CR 701.9 is the discard rule the
    episode turns on: a single instruction to discard several cards is one
    event with a count, the same way CR 121.2 makes multiple card draws
    individual events but discard has no such rule - Mind Rot's "discards two
    cards" is one discard, not two.

    `parse_abilities` correctly reads the first sentence as a `TriggeredAbility`
    (CR 603.1's "[When/Whenever/At] [condition], [effect]" shape), but
    `_trigger_event` has no branch for "discard" among the conditions it reads -
    enters, dies, attacks, blocks, beginning-of-step, cast, draw, sacrifice,
    gain life, deal damage, becomes tapped/untapped - so it returns `None` for
    the condition here. An ability with `event=None` is never matched against
    any `GameEvent` `condition_matches` is asked about, which means this
    trigger can never go on the stack no matter how many cards anyone discards.
    """
    (ability,) = [
        found
        for found in parse_abilities(card("Captain Howler, Sea Scourge"))
        if found.kind is AbilityKind.TRIGGERED
    ]
    assert isinstance(ability, TriggeredAbility)
    assert "discard" in ability.condition
    assert ability.event is None


def test_mind_rots_own_discard_clause_now_has_a_scripted_effect():
    """The other half of the setup, now closed: Mind Rot's "Target player
    discards two cards" is exactly `_parse_target_player_discards_clause`'s
    shape in `machines/effects.py` (see `test_target_player_discards.py` for
    the full corner-case coverage of that parser), so `effect_for` no longer
    returns `None` for it. That does not resolve DDR#886 on its own -
    Captain Howler's own "whenever you discard" trigger still parses with no
    event (`test_captain_howlers_discard_trigger_parses_with_no_event`
    above), which is why the scenario below still `xfail`s.
    """
    assert effect_for("Mind Rot", card("Mind Rot").oracle_text) is not None


@pytest.mark.xfail(
    strict=True,
    reason="Mind Rot's own discard now runs (bob's hand empties), but Captain "
    "Howler's own 'whenever you discard' trigger still parses with event=None "
    "(see test_captain_howlers_discard_trigger_parses_with_no_event above), so "
    "no trigger ever goes on the stack and no creature is pumped.",
)
def test_mind_rot_causes_captain_howlers_discard_trigger_to_fire_once():
    """DDR#886: Mind Rot's single "discards two cards" instruction is one
    discard event carrying a count of two (CR 701.9), so Captain Howler's
    "Whenever you discard one or more cards" triggers exactly once and reads
    "for each card discarded this way" off that one event - a +4/+0 pump, not
    two separate +2/+0 triggers.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mind Rot"],
            battlefield=["Swamp", "Swamp", "Swamp", "Captain Howler, Sea Scourge"],
        )
        .player("bob", hand=["Mountain", "Mountain"], battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Mind Rot", auto=True, username="alice", targets=["bob"])
    assert len(scenario.player("bob").hand) == 0
    assert len(scenario.pending_triggers) == 1
