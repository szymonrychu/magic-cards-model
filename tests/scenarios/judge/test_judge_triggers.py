"""Judge scenarios: trigger conditions the engine cannot recognize at all.

Sourced from the DDR judge transcripts. Episodes covered:

- **DDR#886** - Captain Howler, Sea Scourge + Mind Rot (each cause of discard
  is its own trigger event, and a single "discard two cards" instruction is
  one event carrying a count of two, not two separate events)
- **DDR#983** - Kavaron Harrier + Gut, True Soul Zealot (a controller orders
  their own simultaneous triggers, and a "you may ... if you do" choice waits
  for resolution rather than being made when the ability goes on the stack)
- **DDR#981** - Lagrella, the Magpie + Panharmonicon (a *delayed* triggered
  ability set up by a resolving ability is not that ability, so doubling the
  ability does not double it)

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
from magic_cards_model.machines.effects import effect_for, trigger_effect_for
from magic_cards_model.machines.layers import LAYER_EFFECTS
from magic_cards_model.models import Zone
from magic_cards_model.models.token import TokenState
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
# DDR#983 - Kavaron Harrier + Gut, True Soul Zealot: ordering two of your own
# attack triggers, and which choices wait for resolution
# --------------------------------------------------------------------------


def test_both_attack_triggers_go_on_the_stack_under_one_controller():
    """DDR#983's setup, and the half the engine builds: two attack triggers.

    Kavaron Harrier (verified with `resolve_cards`): "Whenever this creature
    attacks, you may pay {2}. If you do, create a 2/2 colorless Robot artifact
    creature token that's tapped and attacking. Sacrifice that token at end of
    combat." Gut, True Soul Zealot: "Whenever you attack, you may sacrifice
    another creature or an artifact. If you do, create a 4/1 black Skeleton
    creature token with menace that's tapped and attacking."

    Both are `TriggerEvent.ATTACKS` conditions, both fire off one declaration,
    and alice controls both - CR 603.3: "once an ability has triggered, its
    controller puts it on the stack as an object that's not a card the next
    time a player would receive priority."
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Kavaron Harrier", "Gut, True Soul Zealot", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    harrier = scenario.creature("Kavaron Harrier", "alice")
    gut = scenario.creature("Gut, True Soul Zealot", "alice")
    scenario.attack_with(harrier, gut)

    assert [ability.controller for ability in scenario.game.abilities_on_stack] == [
        "alice",
        "alice",
    ]
    assert scenario.stack_names() == [
        "Kavaron Harrier's triggered ability",
        "Gut, True Soul Zealot's triggered ability",
    ]


def test_the_controller_is_not_asked_which_of_their_two_triggers_goes_on_first():
    """The gap the xfail below rests on, stated as its own fact.

    CR 603.3b: "First, each player, in APNAP order, puts each triggered
    ability they control on the stack in any order they choose." *In any order
    they choose* is the whole episode - Amy needs the Harrier's trigger to
    resolve **first**, so the Robot exists before Gut asks her to sacrifice
    something. `Game.put_triggers_on_stack` instead keeps one player's own
    abilities in the order they triggered, which is a fixed order nobody is
    asked about: the Harrier goes on lowest here and therefore resolves
    **last**, the opposite of what the trick needs.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Kavaron Harrier", "Gut, True Soul Zealot", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    harrier = scenario.creature("Kavaron Harrier", "alice")
    gut = scenario.creature("Gut, True Soul Zealot", "alice")
    scenario.attack_with(harrier, gut)

    # Bottom of the stack first, so Gut's is on top and resolves before the
    # Harrier's - and no `Decision` was raised asking alice about it.
    assert scenario.stack_names()[-1] == "Gut, True Soul Zealot's triggered ability"
    assert scenario.questions_asked() == []


def test_neither_attack_triggers_pay_or_sacrifice_clause_becomes_behaviour():
    """The other gap: CR 118.12's "if you do" pair is read, not executed.

    CR 118.12 is the shape both cards print: "[A player] may [do something].
    If [that player] [does, doesn't, or can't], [effect]." The episode's first
    important fact is that this choice is *not* on CR 603.3d's list of things
    settled when the ability goes on the stack (that list is CR 601.2c-d's
    targets and divisions), so it waits for resolution - which is why the
    Robot can exist by the time Gut asks.

    Here the Harrier's whole clause comes back as a notice-only effect and
    Gut's as `None`, so resolving both leaves the board exactly as it was: no
    Robot, no Skeleton, and no delayed "sacrifice that token at end of combat"
    registered either.
    """
    harrier_text = card("Kavaron Harrier").oracle_text
    effect = trigger_effect_for("Kavaron Harrier", TriggerEvent.ATTACKS, harrier_text)
    assert effect is not None
    assert effect.__name__ == "delayed_notice_only"

    gut_text = card("Gut, True Soul Zealot").oracle_text.split("\n")[0]
    assert trigger_effect_for("Gut, True Soul Zealot", TriggerEvent.ATTACKS, gut_text) is None

    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Kavaron Harrier", "Gut, True Soul Zealot", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    harrier = scenario.creature("Kavaron Harrier", "alice")
    gut = scenario.creature("Gut, True Soul Zealot", "alice")
    scenario.attack_with(harrier, gut)
    while scenario.game.stack:
        scenario.resolve_top()

    assert sorted(scenario.battlefield_names()) == sorted(
        ["Kavaron Harrier", "Gut, True Soul Zealot", "Mountain", "Mountain"]
    )
    assert scenario.game.delayed_triggers.triggers == []


@pytest.mark.xfail(
    strict=True,
    reason="two gaps, either of which alone sinks it: Game.put_triggers_on_stack never asks a "
    "controller for CR 603.3b's ordering of their own simultaneous triggers, and neither "
    "card's CR 118.12 'you may ... if you do' clause has a scripted effect (both proven above), "
    "so no Robot and no Skeleton token is created at all.",
)
def test_the_robot_is_sacrificed_for_a_skeleton_that_survives_end_of_combat():
    """DDR#983: pay {2}, feed the Robot to Gut, keep the Skeleton.

    Amy orders her two triggers so the Harrier's resolves first (CR 603.3b),
    pays {2}, and gets a 2/2 Robot attacking. Gut's trigger then resolves and
    she chooses - at resolution, because CR 603.3d settles only targets and
    divisions when an ability goes on the stack - to sacrifice that very
    Robot, turning it into a 4/1 Skeleton.

    The Harrier's own "sacrifice that token at end of combat" is a delayed
    triggered ability (CR 603.7a: "delayed triggered abilities are created
    during the resolution of spells or abilities"), and it names the *Robot*.
    The Robot is already gone when the end of combat step arrives, so that
    delayed trigger has nothing to sacrifice; nothing anywhere tells Amy to
    sacrifice the Skeleton, and she keeps it.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Kavaron Harrier", "Gut, True Soul Zealot", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    harrier = scenario.creature("Kavaron Harrier", "alice")
    gut = scenario.creature("Gut, True Soul Zealot", "alice")
    scenario.attack_with(harrier, gut)
    while scenario.game.stack:
        scenario.resolve_top()

    tokens = [
        state
        for state in scenario.game.battlefield
        if state.controller == "alice" and isinstance(state, TokenState)
    ]
    assert [token.name for token in tokens] == ["Skeleton"]

    scenario.start_at(Step.END_OF_COMBAT)
    while scenario.game.stack:
        scenario.resolve_top()
    survivors = [
        state
        for state in scenario.game.battlefield
        if state.controller == "alice" and isinstance(state, TokenState)
    ]
    assert [token.name for token in survivors] == ["Skeleton"]


# --------------------------------------------------------------------------
# DDR#981 - Lagrella, the Magpie + Panharmonicon: what Panharmonicon can and
# cannot double
# --------------------------------------------------------------------------


def test_lagrellas_enters_trigger_and_panharmonicon_are_both_unbuilt():
    """DDR#981, the provable half: neither side of the interaction exists yet.

    Lagrella, the Magpie (verified with `resolve_cards`): "When Lagrella
    enters, exile any number of other target creatures controlled by different
    players until Lagrella leaves the battlefield. When an exiled card enters
    under your control this way, put two +1/+1 counters on it." Panharmonicon:
    "If an artifact or creature entering causes a triggered ability of a
    permanent you control to trigger, that ability triggers an additional
    time."

    `trigger_effect_for` returns `None` for Lagrella's enters trigger, and
    Panharmonicon's own static ability has no entry in `machines/layers.
    LAYER_EFFECTS` and no trigger-multiplying machinery anywhere - nothing in
    this engine makes an ability "trigger an additional time".
    """
    lagrella = card("Lagrella, the Magpie")
    trigger_line = lagrella.oracle_text.split("\n")[0]
    assert (
        trigger_effect_for(
            "Lagrella, the Magpie", TriggerEvent.ENTERS_THE_BATTLEFIELD, trigger_line
        )
        is None
    )
    assert "Lagrella, the Magpie" not in LAYER_EFFECTS
    assert "Panharmonicon" not in LAYER_EFFECTS


def test_panharmonicon_does_not_make_lagrella_trigger_twice_here():
    """The consequence, played out: one trigger, and it does nothing.

    This is the *right answer for the wrong reason*, and worth pinning down so
    a later wave that feeds Panharmonicon into the engine can tell the two
    apart. The episode says Panharmonicon **does** double Lagrella's enters
    trigger - it is a genuine triggered ability of a permanent alice controls,
    caused by a creature entering - so alice should get two exile abilities.
    What she must not get is extra +1/+1 counters, and that is a different
    ability entirely.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lagrella, the Magpie"],
            battlefield=["Panharmonicon", "Forest", "Plains", "Island"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Plains", "Island", username="alice")
    scenario.cast_and_resolve("Lagrella, the Magpie", *sources, username="alice")

    assert scenario.stack_names() == ["Lagrella, the Magpie's triggered ability"]
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.resolve_top()
    assert bears.zone is Zone.BATTLEFIELD
    assert bears.counter_count("+1/+1") == 0


@pytest.mark.xfail(
    strict=True,
    reason="trigger_effect_for('Lagrella, the Magpie', ENTERS_THE_BATTLEFIELD, ...) is None and "
    "Panharmonicon has no LAYER_EFFECTS row or any trigger-multiplying machinery (both proven "
    "above), so nothing is exiled, nothing returns, and no +1/+1 counter is ever placed.",
)
def test_panharmonicon_doubles_the_exile_but_not_the_delayed_counter_trigger():
    """DDR#981: two exiles, still two counters.

    Panharmonicon doubles Lagrella's *enters* ability, so alice exiles a
    second set of creatures. It cannot touch the counters, though, because the
    "when an exiled card enters under your control this way" half is not an
    independent ability of Lagrella at all - it is a **delayed** triggered
    ability set up by that ability resolving. CR 603.7a: "delayed triggered
    abilities are created during the resolution of spells or abilities, as the
    result of a replacement effect being applied, or as a result of a static
    ability that allows a player to take an action", and CR 603.7d makes its
    source the spell or ability that created it. Doubling the ability that
    creates it is not doubling it.

    So alice's own returning Grizzly Bears gets exactly two +1/+1 counters -
    the number one resolution of that delayed trigger puts on - not four.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lagrella, the Magpie"],
            battlefield=["Panharmonicon", "Grizzly Bears", "Forest", "Plains", "Island"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Forest", "Plains", "Island", username="alice")
    lagrella = scenario.cast_and_resolve("Lagrella, the Magpie", *sources, username="alice")

    assert len(scenario.game.abilities_on_stack) == 2, "Panharmonicon doubled the enters trigger"
    scenario.choose_trigger_targets("Lagrella, the Magpie", [bears])
    while scenario.game.stack:
        scenario.resolve_top()
    assert bears.zone is Zone.EXILE

    # Lagrella leaving is what brings them back (CR 610.3's "until" pair).
    scenario.game.move_to_graveyard(lagrella)
    while scenario.game.stack:
        scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.counter_count("+1/+1") == 2
