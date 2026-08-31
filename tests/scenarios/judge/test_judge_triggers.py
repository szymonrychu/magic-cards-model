"""Judge scenarios: trigger conditions the engine cannot recognize at all.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#886** - Captain Howler, Sea Scourge + Mind Rot (each cause of discard
  is its own trigger event, and a single "discard two cards" instruction is
  one event carrying a count of two, not two separate events)
- **DDR#993** - Fire Navy Trebuchet + Phoenix Fleet Airship (an intervening
  *if* clause checked at the moment the ability would trigger, which is before
  the other end-step trigger has had any chance to resolve)

Every CR number here was looked up with `knowledge_search(type="rules")`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import (
    AbilityKind,
    TriggeredAbility,
    TriggerEvent,
    parse_abilities,
)
from magic_cards_model.machines.effects import effect_for
from magic_cards_model.models import Zone
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


# --------------------------------------------------------------------------
# DDR#993 - an intervening *if* clause never lets the ability trigger at all
# --------------------------------------------------------------------------


def _trebuchet_and_airship() -> "Scenario":
    """Alice attacks with a bear while controlling both end-step permanents.

    Fire Navy Trebuchet is a 0/4 Wall with defender, so the attacker has to be
    something else; Grizzly Bears is the plainest creature in the pool.
    """
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Fire Navy Trebuchet", "Phoenix Fleet Airship", "Grizzly Bears"],
        )
        .player("bob")
    )


def _attack_and_reach_the_end_step(scenario) -> None:
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()
    while scenario.step is not Step.END_STEP:
        scenario.advance()


def test_phoenix_fleet_airship_does_not_trigger_when_nothing_was_sacrificed_yet():
    """DDR#993: the *if* is checked as the beginning of the end step arrives.

    Phoenix Fleet Airship (confirmed with `resolve_cards`): "At the beginning
    of your end step, if you sacrificed a permanent this turn, create a token
    that's a copy of this Vehicle." CR 603.4: "When the trigger event occurs,
    the ability checks whether the stated condition is true. The ability
    triggers only if it's true." Both abilities in this episode trigger at the
    beginning of the end step, and although CR 603.3b would let alice order the
    two however she likes, the Trebuchet's sacrifice cannot have happened yet
    when the Airship's condition is read - so the Airship never triggers, and
    the ordering question the episode raises is moot.

    The engine reaches the same answer, but by the fail-closed route rather
    than by evaluating the clause: "you sacrificed a permanent this turn" is a
    shape `machines/triggers.intervening_if_holds` does not read, so it refuses
    to trigger and records why. That notice is asserted here deliberately - it
    is what separates this passing test from one that would keep passing for
    the wrong reason once the clause *is* implemented (the xfail below is the
    other side of that pair).
    """
    scenario = _trebuchet_and_airship().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    _attack_and_reach_the_end_step(scenario)

    assert scenario.stack_names() == []
    assert scenario.pending_triggers == []
    assert [notice.source_name for notice in scenario.game.intervening_if_notices] == [
        "Phoenix Fleet Airship"
    ]


@pytest.mark.xfail(
    strict=True,
    reason="'you sacrificed a permanent this turn' is not a clause shape "
    "`machines/triggers.intervening_if_holds` reads, so CR 603.4 fails closed "
    "and the ability never triggers - even on the turn where the condition is "
    "genuinely true. Nothing tracks per-turn sacrifices for a trigger condition "
    "to read; the refusal is recorded as an `InterveningIfNotice` instead.",
)
def test_the_airship_does_trigger_once_a_permanent_really_was_sacrificed():
    """DDR#993's other side: the clause is a real condition, not a blanket no.

    Same CR 603.4 check, on a turn where alice sacrificed a Goblin to Skirk
    Prospector during her main phase. The condition is true when the beginning
    of the end step arrives, so the Airship triggers and CR 608.2a's second
    check on resolution finds it still true.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Phoenix Fleet Airship", "Skirk Prospector", "Raging Goblin"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goblin = scenario.creature("Raging Goblin", "alice")
    scenario.activate(scenario.creature("Skirk Prospector", "alice"), sacrificing=[goblin])
    assert goblin.zone is Zone.GRAVEYARD

    while scenario.step is not Step.END_STEP:
        scenario.advance()

    assert scenario.stack_names() == ["Phoenix Fleet Airship's triggered ability"]


@pytest.mark.xfail(
    strict=True,
    reason="Fire Navy Trebuchet's attack trigger resolves to nothing: its "
    "effect text is two sentences - create the token, then 'Sacrifice that "
    "token at the beginning of the next end step' - and `effect_for('Fire Navy "
    "Trebuchet', ...)` comes back as machines/effects.py's "
    "`delayed_notice_only`, the fail-closed stand-in for a delayed-trigger "
    "shape it cannot build. No Ballistic Boulder ever enters the battlefield, "
    "so the sacrifice this episode is about never happens either.",
)
def test_fire_navy_trebuchet_creates_the_ballistic_boulder_it_will_sacrifice():
    """DDR#993's setup: the token the Trebuchet later sacrifices.

    Fire Navy Trebuchet (confirmed with `resolve_cards`): "Whenever you attack,
    create a 2/1 colorless Construct artifact creature token with flying named
    Ballistic Boulder that's tapped and attacking. Sacrifice that token at the
    beginning of the next end step." The second sentence is a delayed triggered
    ability created on resolution (CR 603.7a), controlled by whoever controlled
    the ability that set it up (CR 603.7e), and CR 701.21a's sacrifice is what
    the Airship's condition would be looking for.
    """
    scenario = _trebuchet_and_airship().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    _attack_and_reach_the_end_step(scenario)

    assert "Ballistic Boulder" in scenario.battlefield_names()
