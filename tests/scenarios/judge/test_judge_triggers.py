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


def test_both_pay_and_sacrifice_clauses_are_behaviour_rather_than_notices():
    """CR 118.12's "if you do" pair, on both cards, read and executed.

    CR 118.12 is the shape both print: "[A player] may [do something]. If
    [that player] [does, doesn't, or can't], [effect]." The episode's first
    important fact is that this choice is *not* on CR 603.3d's list of things
    settled when the ability goes on the stack (that list is CR 601.2c-d's
    targets and divisions), so it waits for resolution - which is why the Robot
    can exist by the time Gut asks.

    Both used to come back unread from `machines/effects.py` - the Harrier's as
    a notice-only stand-in and Gut's as `None`. Both are now
    `_parse_may_cost_then_attacking_token_clause`'s shape.

    Each is handed the *effect* half, not the whole printed line:
    `trigger_effect_for` is a fail-closed whole-clause dispatcher, and the
    "Whenever ... attacks," condition is split off by `machines/abilities.py`
    long before it gets there. `parse_abilities` is what does that split in the
    real game, so it is what supplies the text here rather than a hand-cut
    string.
    """
    for name in ("Kavaron Harrier", "Gut, True Soul Zealot"):
        (triggered,) = [
            found
            for found in parse_abilities(card(name))
            if found.kind is AbilityKind.TRIGGERED and found.event is TriggerEvent.ATTACKS
        ]
        effect = trigger_effect_for(name, TriggerEvent.ATTACKS, triggered.effect)
        assert effect is not None, name
        assert effect.__name__ != "delayed_notice_only", name


def test_the_unordered_default_lets_gut_eat_the_harrier_before_it_pays():
    """What DDR#983's board does with nobody asked for CR 603.3b's order.

    The Harrier's trigger goes on the stack lowest and so resolves last. Gut's
    resolves first, with no Robot in existence yet, and takes the only other
    thing alice controls that its restriction reaches - the Harrier itself
    (CR 701.21a). The Harrier's own trigger still resolves afterwards, from the
    graveyard (CR 113.7a: an ability on the stack exists independently of its
    source), but alice has no mana floating and `Game.may_pay_mana_cost` only
    spends the pool - CR 608.2g's mid-resolution "chance to activate mana
    abilities" is not modelled - so the {2} goes unpaid and CR 118.12's "if you
    do" branch does not run.

    One Skeleton, no Robot, and no delayed sacrifice registered: the *right*
    board for the wrong reason, which is why the episode's own test below is
    still `xfail`. CR 111.4 names the token: the ability states no name, so it
    is "its subtype(s) plus the word 'token'".
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

    assert harrier.zone is Zone.GRAVEYARD
    assert sorted(scenario.battlefield_names()) == sorted(
        ["Gut, True Soul Zealot", "Mountain", "Mountain", "Skeleton Token"]
    )
    assert scenario.game.delayed_triggers.triggers == []


@pytest.mark.xfail(
    strict=True,
    reason="ONE gap, and it is in models/game.py: Game._put_pending_triggers_on_stack never "
    "asks a controller for CR 603.3b's 'in any order they choose'. It calls "
    "machines/triggers.apnap_order, which sorts by seat only, and then appends each of one "
    "player's abilities in the order they triggered - so the Harrier's goes on lowest and "
    "resolves last, the opposite of what the episode needs. Everything else is built: "
    "machines/decisions.DecisionKind.ORDER_TRIGGERS and ask_trigger_order put and validate "
    "the question, Scenario.will_order_triggers scripts the answer (both used below), and "
    "machines/effects._parse_may_cost_then_attacking_token_clause reads both cards' CR 118.12 "
    "clauses (proven above). What game.py needs, between `ordered = apnap_order(...)` and the "
    "loop that appends: group `ordered` by controller, call "
    "`ask_trigger_order(self.decisions, controller, tuple((a.id, a.source_name) for a in "
    "block))` per controller, and re-lay each block in the returned order.",
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
    delayed trigger has nothing to sacrifice (CR 603.7c); nothing anywhere
    tells Amy to sacrifice the Skeleton, and she keeps it.

    The two Mountains are tapped for mana *before* the triggers resolve, and
    that is not staging around a gap: CR 605.3a lets a mana ability be
    activated whenever its controller has priority, and alice has priority
    after her own triggers go on the stack. `Game.may_pay_mana_cost` spends
    only the floating pool, so this is how the {2} is actually payable.

    Both token names are CR 111.4's default - neither ability states a name, so
    each is "its subtype(s) plus the word 'token'".
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
    # CR 603.3b: alice's own two triggers, bottom of the stack first - so Gut's
    # goes on lowest and the Harrier's resolves first, which is the whole trick.
    scenario.will_order_triggers("Gut, True Soul Zealot", "Kavaron Harrier", username="alice")
    scenario.attack_with(harrier, gut)

    # CR 605.3a: mana abilities, activated with priority, for the Harrier's {2}.
    for mountain in scenario.untapped_sources("Mountain", "Mountain", username="alice"):
        scenario.activate(mountain)

    scenario.resolve_top()  # the Harrier's: pay {2}, get the Robot
    robot = scenario.creature("Robot Token", "alice")
    scenario.will_choose_cards(robot, username="alice")
    scenario.resolve_top()  # Gut's: feed the Robot to it

    tokens = [
        state
        for state in scenario.game.battlefield
        if state.controller == "alice" and isinstance(state, TokenState)
    ]
    assert [token.name for token in tokens] == ["Skeleton Token"]

    scenario.start_at(Step.END_OF_COMBAT)
    while scenario.game.stack:
        scenario.resolve_top()
    survivors = [
        state
        for state in scenario.game.battlefield
        if state.controller == "alice" and isinstance(state, TokenState)
    ]
    assert [token.name for token in survivors] == ["Skeleton Token"]


# --------------------------------------------------------------------------
# DDR#981 - Lagrella, the Magpie + Panharmonicon: what Panharmonicon can and
# cannot double
# --------------------------------------------------------------------------


def test_lagrellas_enters_trigger_has_a_scripted_effect_and_panharmonicon_is_not_a_layer():
    """DDR#981, both halves, at the level of what is registered where.

    Lagrella, the Magpie (verified with `resolve_cards`): "When Lagrella
    enters, exile any number of other target creatures controlled by different
    players until Lagrella leaves the battlefield. When an exiled card enters
    under your control this way, put two +1/+1 counters on it." Panharmonicon:
    "If an artifact or creature entering causes a triggered ability of a
    permanent you control to trigger, that ability triggers an additional
    time."

    Panharmonicon's half is CR 603.2d, which lives in
    `machines/triggers.additional_trigger_times`, read off the printed sentence
    rather than through `machines/layers.LAYER_EFFECTS`, because CR 603.2d is
    about how many times an ability triggers and not about any object's
    characteristics. Lagrella's half is read off her own effect text by
    `machines/effects._parse_exile_targets_until_leaves_then_counters` - both
    sentences together, since the second is the delayed triggered ability
    (CR 603.7a) the first one creates - with no card-name row of her own.

    `trigger_effect_for` is asked with the ability's *effect*, which is what
    `Game._effect_of` passes it: the "When Lagrella enters," condition in front
    of it belongs to `machines/triggers.py`, not here.
    """
    (trigger,) = [
        found
        for found in parse_abilities(card("Lagrella, the Magpie"))
        if found.kind is AbilityKind.TRIGGERED
    ]
    assert isinstance(trigger, TriggeredAbility)
    assert (
        trigger_effect_for(
            "Lagrella, the Magpie", TriggerEvent.ENTERS_THE_BATTLEFIELD, trigger.effect
        )
        is not None
    )
    assert "Lagrella, the Magpie" not in LAYER_EFFECTS
    assert "Panharmonicon" not in LAYER_EFFECTS, "CR 603.2d is not a continuous effect"


def test_panharmonicon_makes_lagrellas_enters_trigger_twice():
    """CR 603.2d, played out: two abilities on the stack off one entry.

    "An ability may state that a triggered ability triggers additional times.
    In this case, rather than simply determining that such an ability has
    triggered, determine how many times it should trigger, then trigger it that
    many times." Lagrella's enters ability is a triggered ability of a permanent
    alice controls, and a creature entering is what caused it, so it triggers
    Both resolve, and both find nothing to do: no `choose_trigger_targets`
    answer was queued, so each went on the stack targeting nothing at all -
    "any number of other target creatures" allows zero (CR 107.1c). The bear
    is bob's and untouched either way; the exile that *does* happen is the
    test further down, which queues an answer first.
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

    assert scenario.stack_names() == ["Lagrella, the Magpie's triggered ability"] * 2
    bears = scenario.creature("Grizzly Bears", "bob")
    while scenario.game.stack:
        scenario.resolve_top()
    assert bears.zone is Zone.BATTLEFIELD
    assert bears.counter_count("+1/+1") == 0


def test_panharmonicon_does_not_double_a_trigger_an_opponent_controls():
    """ "a triggered ability of a permanent **you** control" - bob's
    Panharmonicon does nothing for alice's Lagrella, however plainly a creature
    entered."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lagrella, the Magpie"],
            battlefield=["Forest", "Plains", "Island"],
        )
        .player("bob", battlefield=["Panharmonicon"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Plains", "Island", username="alice")
    scenario.cast_and_resolve("Lagrella, the Magpie", *sources, username="alice")

    assert scenario.stack_names() == ["Lagrella, the Magpie's triggered ability"]


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
    # CR 603.3d: a trigger's targets are chosen as it is put on the stack, so
    # the answer has to be waiting before Lagrella ever enters.
    scenario.choose_trigger_targets("Lagrella, the Magpie", [bears])
    sources = scenario.untapped_sources("Forest", "Plains", "Island", username="alice")
    lagrella = scenario.cast_and_resolve("Lagrella, the Magpie", *sources, username="alice")

    assert len(scenario.game.abilities_on_stack) == 2, "Panharmonicon doubled the enters trigger"
    while scenario.game.stack:
        scenario.resolve_top()
    assert bears.zone is Zone.EXILE

    # Lagrella leaving is what brings them back (CR 610.3's "until" pair).
    scenario.game.destroy(lagrella)
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.counter_count("+1/+1") == 2


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

    The engine reaches the same answer by evaluating the clause, not by
    refusing it: `machines/triggers._sacrificed_this_turn_holds` reads
    `Game.permanents_sacrificed_this_turn`, which `Game.sacrifice` fills in as
    CR 701.21a's move happens, and finds nothing there. The empty
    `intervening_if_notices` is asserted deliberately - a notice would mean the
    clause was unreadable and the ability declined for that reason instead,
    which is the same visible outcome for the wrong reason. The test below is
    the other side of the pair: the same clause, on a turn where it is true.

    The Trebuchet's *own* delayed sacrifice ability (CR 603.7a, CR 603.7e) is
    on the stack at this point and is expected to be - it is the sacrifice the
    Airship is waiting for and has not seen yet. This assertion used to read
    `stack_names() == []`, which was only true while the Trebuchet's attack
    trigger did nothing at all; asserting the Airship's absence by name is what
    the test is actually about.
    """
    scenario = _trebuchet_and_airship().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    _attack_and_reach_the_end_step(scenario)

    assert scenario.stack_names() == ["Fire Navy Trebuchet's triggered ability"], (
        "only the Trebuchet's own delayed sacrifice, never the Airship's copy trigger"
    )
    assert scenario.pending_triggers == []
    assert scenario.game.intervening_if_notices == []


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
