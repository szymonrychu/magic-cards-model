"""Suspend, CR 702.62, built from the defect it left behind.

A real game log (3cce87b1a72b4442a7c1faad8cd51ba0, seq 279-282) showed Living
End - a card with **no printed mana cost** - cast straight out of hand for an
empty cost, with no black source on the battlefield, and resolving into a full
board wipe nobody paid for. Every CR number below was looked up with
`knowledge_search(q="...", type="rules")` in the session that wrote this file,
and the full text of each was then read out of the `2026-08-19` Comprehensive
Rules release named by `knowledge_search(type="cr_versions")`.

**The root cause (CR 118.6):** "Some objects have no mana cost. This
represents an unpayable cost. ... Attempting to cast a spell ... that has an
unpayable cost is a legal action. However, attempting to pay an unpayable cost
is an illegal action." `Casting.base_cost` parsed Living End's blank
`mana_cost` field to a `ManaCost` with **zero symbols**, so its `total_cost`
came back "free" the same way a genuinely printed `{0}` would (CR 118.5a) -
the engine could not tell "no cost printed" apart from "a cost of nothing",
even though CR 118.6 says only the first of those is unpayable.
`Casting._refuse_unless_mana_cost_payable` (in `machines/casting.py`) is the
fix: a card whose printed mana cost has no symbols at all cannot be cast
unless an alternative cost was announced first (CR 118.6a) - covering *every*
card with no mana cost, not Living End by name.

**The fix's other half is building what CR 118.6a actually names as the way
out: suspend.** Living End's only route onto the stack is its own suspend
ability - without it, this whole deck's finisher is simply unplayable. CR
702.62a is the whole keyword:

    "Suspend is a keyword that represents three abilities. The first is a
    static ability that functions while the card with suspend is in a
    player's hand. The second and third are triggered abilities that function
    in the exile zone. 'Suspend N-[cost]' means 'If you could begin to cast
    this card by putting it onto the stack from your hand, you may pay [cost]
    and exile it with N time counters on it. This action doesn't use the
    stack,' and 'At the beginning of your upkeep, if this card is suspended,
    remove a time counter from it,' and 'When the last time counter is
    removed from this card, if it's exiled, you may play it without paying
    its mana cost if able. If you don't, it remains exiled. If you cast a
    creature spell this way, it gains haste until you lose control of the
    spell or the permanent it becomes.'"

Three functions in `machines/casting.py` carry the three abilities, general to
the keyword's own "Suspend N-[cost]" text (`KeywordAbility.count`/`.cost`, the
same parse `docs/engine-coverage.md` already credited before this wave), not
special-cased to Living End:

- `MarkedExile.suspend` - CR 116.2f's special action. Mirrors `MarkedExile.
  plot`/`.foretell`, the two special actions already modelled the same way.
  Gated by `why_cannot_cast_now`/`why_cannot_cast_restriction` (CR 702.62c's
  "take into consideration any effects that would prohibit that card from
  being cast") and deliberately **not** by CR 118.6 - CR 118.6 itself says
  attempting to *cast* an unpayable cost is legal, only *paying* it is not,
  which is exactly why a card with no mana cost can still be suspended.
- `remove_suspend_time_counter` - the upkeep trigger. Not driven
  automatically (this engine's turn machine does not dispatch per-card
  upkeep triggers any more than it dispatches combat's own declarations -
  see `docs/scenario-tests.md`), so a scenario calls it once per upkeep, the
  same hand-driven shape `exile_warped`'s delayed trigger already takes.
- `finish_suspend` - the last-counter trigger, handing out a `PlayPermission`
  (CR 601.3's dynamic grant, the same primitive Ugin, Eye of the Storms' -11
  and Ragavan's trigger already use) rather than a new decision kind: the
  "you may" is left to the caller exactly the way `cascade`'s own "you may
  cast it" already is - nobody here to ask (CR 608.2d), and the caller's
  choice **is** whether it ever calls `Casting.use_permission()`.
- `grant_suspend_haste` - the creature-spell haste clause, applied the same
  way Postmortem Lunge's own no-duration-stated haste already is
  (`Duration.INDEFINITE`, `only_this_incarnation`-scoped).

Two real printings prove the parse is general, not Living End-specific:
Living End (Sorcery, Suspend 3-{2}{B}{B}, no mana cost) and Greater Gargadon
(Creature, Suspend 10-{R}, mana cost {9}{R} - genuinely castable outright too,
unlike Living End), which also proves the haste grant against a real creature.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import (
    Casting,
    MarkedExile,
    finish_suspend,
    grant_suspend_haste,
    remove_suspend_time_counter,
    usable_play_permission,
)
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color, Type
from magic_cards_model.models.card_state import CardState, Counter, ExileAnnotation, ExileMarker
from tests.scenarios.harness import PlayedScenario, Scenario


def _advance_to_owners_next_upkeep(scenario: PlayedScenario, owner: str) -> None:
    """Walk the real turn machine forward to `owner`'s own next upkeep step -
    CR 702.62a says "at the beginning of *your* upkeep", so this steps clean
    through any other player's turn in between rather than firing on it.

    Whatever is on the stack is resolved on the way (CR 500.2 refuses to
    advance past a step with a non-empty stack), and whatever went on it *at*
    the upkeep reached is deliberately left there unresolved, so a test can
    assert on the triggers before choosing to resolve them.
    """
    scenario.advance()
    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == owner):
        _resolve_everything(scenario)
        scenario.advance()


def _resolve_everything(scenario: PlayedScenario) -> None:
    """Resolve the whole stack, top down."""
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def test_living_end_cannot_be_hardcast_from_hand_with_no_mana_cost():
    """The reported defect, reproduced and refused. Living End's `mana_cost`
    is the empty string (verified via `resolve_cards`) - CR 118.6's unpayable
    cost - and nothing here supplies an alternative cost, so CR 601.6 makes
    the whole cast illegal. The refusal names *why*, not just *that*.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Living End"], battlefield=["Swamp", "Swamp", "Swamp", "Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    living_end = scenario.find("Living End", Zone.HAND)

    with pytest.raises(ValueError, match="unpayable cost"):
        Casting(spell=living_end, caster="alice", game=scenario.game).begin_paying()

    # The card never moved: a refused announcement changes nothing (CR 601.6).
    assert living_end.zone is Zone.HAND


def test_no_mana_source_needed_makes_no_difference_to_the_refusal():
    """Even with black sources untapped and ready, the plain hardcast is still
    refused - this is not a "not enough mana" failure, it is CR 118.6's "this
    cost cannot be paid at all" failure, and paying nothing towards it (the
    zero-symbol cost) does not change that.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Living End"], battlefield=["Swamp", "Swamp", "Swamp", "Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    with pytest.raises(ValueError, match="Living End has no mana cost"):
        scenario.cast_and_resolve("Living End")


def _suspend_living_end(scenario: PlayedScenario) -> "MarkedExile":
    living_end = scenario.find("Living End", Zone.HAND)
    action = MarkedExile.suspend(scenario.game, living_end, "alice")
    payment = action.begin_paying()
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp")
    scenario.pay_with(payment, *sources)
    action.take()
    return action


def test_suspending_living_end_exiles_it_with_three_time_counters():
    """CR 116.2f/702.62a: the special action pays the suspend cost
    ({2}{B}{B}) and exiles the card with N (3) time counters - not the card's
    absent mana cost, and not a discount on it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Living End"], battlefield=["Swamp", "Swamp", "Swamp", "Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _suspend_living_end(scenario)
    living_end = scenario.find("Living End", Zone.EXILE)

    assert living_end.zone is Zone.EXILE
    assert living_end.counter_count(Counter.TIME) == 3
    assert living_end.exile_annotation is not None
    assert living_end.exile_annotation.marker is ExileMarker.SUSPENDED
    assert all(source.tapped for source in scenario.game.battlefield)


def test_suspend_cannot_be_taken_without_paying_its_full_cost():
    """CR 116.2f pays [cost] as part of the special action itself - one black
    source short, and the action's own payment never reaches PAID, so `take`
    refuses rather than exiling the card for less than it costs."""
    scenario = (
        Scenario()
        .player("alice", hand=["Living End"], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    living_end = scenario.find("Living End", Zone.HAND)

    action = MarkedExile.suspend(scenario.game, living_end, "alice")
    payment = action.begin_paying()
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    for source in sources:
        payment.tap_for_mana(source, [Color.BLACK])

    with pytest.raises(ValueError):
        action.take()
    assert living_end.zone is Zone.HAND


def test_suspend_is_refused_when_the_card_could_not_begin_to_be_cast():
    """CR 702.62c: "While determining if you could begin to cast a card with
    suspend, take into consideration any effects that would prohibit that
    card from being cast." Living End is a sorcery with no flash, so it
    cannot be suspended with something already on the stack (CR 117.1a) -
    the same timing gate `why_cannot_cast_now` gives an ordinary cast."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Living End", "Lightning Bolt"],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    living_end = scenario.find("Living End", Zone.HAND)

    with pytest.raises(ValueError, match="could not begin to be cast"):
        MarkedExile.suspend(scenario.game, living_end, "alice")
    assert living_end.zone is Zone.HAND


def test_time_counters_come_off_one_per_upkeep_and_the_free_cast_reanimates():
    """The whole pipeline, end to end, through the real engine: suspend,
    three real upkeeps each removing one time counter (CR 702.62a's second
    ability), the last one granting the free cast (its third), and Living
    End's own resolution - each player exiles their graveyard's creatures,
    sacrifices their board, and gets the exiled creatures back - actually
    happening, not mocked.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Living End"],
            graveyard=["Grizzly Bears"],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp", "Kitchen Finks"],
        )
        .player("bob", graveyard=["Colossal Dreadmaw"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _suspend_living_end(scenario)
    living_end = scenario.find("Living End", Zone.EXILE)

    for expected_remaining in (2, 1, 0):
        _advance_to_owners_next_upkeep(scenario, "alice")
        # Nothing is driven by hand any more: the upkeep trigger is a real
        # object on the stack (CR 500.6, 603.3) and resolving it is what takes
        # the counter off.
        _resolve_everything(scenario)
        assert living_end.counter_count(Counter.TIME) == expected_remaining

    # Resolving the third upkeep's trigger emptied the card, which triggered
    # CR 702.62a's *third* ability in turn - and `_resolve_everything` above
    # already resolved that too, granting the free cast without anybody
    # calling `finish_suspend`.
    permission = usable_play_permission(scenario.game, living_end, "alice")
    assert permission is not None
    assert permission.pays_mana_cost is False
    assert permission.immediate is True

    # Living End is a sorcery with no flash, but CR 117.1a never applies here:
    # CR 117.2e - "no player has priority while a spell or ability is
    # resolving" - the cast happens as this triggered ability's own
    # instruction, still during alice's upkeep, not through the ordinary
    # priority system that would otherwise gate a sorcery to a main phase.
    assert scenario.step is Step.UPKEEP
    casting = Casting(spell=living_end, caster="alice", origin_zone=Zone.EXILE, game=scenario.game)
    casting.use_permission()
    assert casting.total_cost.mana.converted == 0
    payment = casting.begin_paying()
    payment.pay()
    spell = casting.cast()
    scenario.game.put_on_stack(spell, "alice")
    living_end.targets = []

    scenario.resolve_top()

    creatures_by_owner = {
        (state.name, state.controller)
        for state in scenario.game.battlefield
        if Type.CREATURE in state.card.types
    }
    assert creatures_by_owner == {("Grizzly Bears", "alice"), ("Colossal Dreadmaw", "bob")}
    assert living_end.zone is Zone.GRAVEYARD


def test_declining_the_free_cast_leaves_the_card_exiled():
    """CR 702.62a: "If you don't, it remains exiled." Nobody here forces the
    caller to use the granted `PlayPermission` - declining is simply not
    calling `Casting.use_permission()`, the same "you may" cascade's own hit
    leaves to the caller."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Living End"], battlefield=["Swamp", "Swamp", "Swamp", "Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _suspend_living_end(scenario)
    living_end = scenario.find("Living End", Zone.EXILE)
    for _ in range(3):
        remove_suspend_time_counter(scenario.game, living_end)

    finish_suspend(scenario.game, living_end)
    # No `use_permission()` call at all: the card just sits there.

    assert living_end.zone is Zone.EXILE
    assert living_end.counter_count(Counter.TIME) == 0


def test_the_upkeep_trigger_does_nothing_once_the_card_has_already_left_exile():
    """CR 702.62b's intervening *if* - "if this card is suspended" - reads
    false for a card no longer in exile at all (say, the free cast already
    happened), and `remove_suspend_time_counter` is a no-op rather than
    raising, the same "if was false" shape `persist_return`'s own intervening
    *if* already returns quietly for."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Living End"], battlefield=["Swamp", "Swamp", "Swamp", "Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    living_end = scenario.find("Living End", Zone.HAND)

    # Never suspended - still in hand.
    remaining = remove_suspend_time_counter(scenario.game, living_end)
    assert remaining == 0
    assert living_end.zone is Zone.HAND


def test_the_free_cast_window_does_not_outlive_the_upkeep_trigger():
    """CR 702.62a's third ability prints no "until end of turn" - unlike
    Ugin, Eye of the Storms' "−11" or Ragavan, Nimble Pilferer's trigger,
    which both do. Its "you may play it... If you don't, it remains exiled"
    is CR 117.2e's own shape instead: "Resolving spells and abilities may
    instruct players to make choices or take actions... Even if a player is
    doing so, no player has priority while a spell or ability is resolving."
    The chance to cast exists only for as long as that instruction is being
    carried out - once the game has moved on to another step in the very
    same turn, the window CR 117.2e stood in for has already closed and CR
    702.62a's own fallback ("it remains exiled") has already taken effect.

    This is the point that tells the correct window apart from the wrong
    one: `until_end_of_turn=True` (the `grant_play_permission` default) would
    keep the permission alive for every step of alice's turn, including her
    precombat main phase reached here - which is exactly the bug a sibling
    repo's tests were built against. `PlayPermission.immediate` closes the
    window the moment the game leaves the upkeep step the trigger fired in,
    regardless of how much of the turn is still left.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Living End"], battlefield=["Swamp", "Swamp", "Swamp", "Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _suspend_living_end(scenario)
    living_end = scenario.find("Living End", Zone.EXILE)

    for _ in range(3):
        _advance_to_owners_next_upkeep(scenario, "alice")
        _resolve_everything(scenario)

    assert scenario.step is Step.UPKEEP
    assert living_end.counter_count(Counter.TIME) == 0
    # `granted_step` is the upkeep the third ability *resolved* in, which is
    # this one - the window is scoped to the resolution that opened it, not
    # to whichever step a caller later remembers to ask in.
    permission = usable_play_permission(scenario.game, living_end, "alice")
    assert permission is not None
    assert permission.immediate is True
    assert permission.granted_step is Step.UPKEEP

    # Still in the same upkeep step the trigger fired in: the window is open.
    # `usable_play_permission` is what `Casting.use_permission` itself checks
    # first - read directly rather than through a `Casting` object, so
    # nothing here exercises `Casting.cancel`'s own CR 733.1 "goes back where
    # it came from" `move_to`, which would mint this object a new CR 400.7
    # zone-change stamp of its own and invalidate the permission for an
    # unrelated reason.
    assert usable_play_permission(scenario.game, living_end, "alice") is permission
    assert permission.why_not(living_end, "alice", scenario.game) is None

    # Walk forward to alice's own precombat main, still the very same turn
    # (Step.DRAW is next, then PRECOMBAT_MAIN) - no cleanup step has run, so
    # `until_end_of_turn`'s own turns-taken check would still call this "this
    # turn" and let it through. CR 702.62a's own instruction already closed,
    # though: nobody used it while the ability was actually resolving.
    scenario.advance()
    assert scenario.step is Step.DRAW
    scenario.advance()
    assert scenario.step is Step.PRECOMBAT_MAIN
    assert scenario.turn.active_player == "alice"  # still alice's own turn

    assert usable_play_permission(scenario.game, living_end, "alice") is None
    refusal = permission.why_not(living_end, "alice", scenario.game)
    assert refusal is not None
    assert "resolution-instructed window" in refusal

    later_casting = Casting(
        spell=living_end, caster="alice", origin_zone=Zone.EXILE, game=scenario.game
    )
    with pytest.raises(ValueError, match="resolution-instructed window"):
        later_casting.use_permission()

    # CR 702.62a's own fallback: the card just sits there, still exiled.
    assert living_end.zone is Zone.EXILE


def test_greater_gargadon_a_second_real_suspend_card_proves_the_parse_is_general():
    """Greater Gargadon: "Suspend 10-{R}", a real Creature - Beast with its
    own printed mana cost ({9}{R}), unlike Living End. Proves
    `KeywordAbility.count`/`.cost` read *this* card's own "Suspend 10-{R}"
    line correctly (a different N, a different cost, read off the same
    general parse), and proves the creature-spell haste clause: a permanent
    that entered the battlefield this turn, cast for free off its own
    suspend, can still attack (CR 702.10b) because `grant_suspend_haste`
    actually reaches the layer engine - not a flag nobody reads.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Greater Gargadon"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gargadon = scenario.find("Greater Gargadon", Zone.HAND)

    action = MarkedExile.suspend(scenario.game, gargadon, "alice")
    payment = action.begin_paying()
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.pay_with(payment, mountain)
    action.take()
    gargadon = scenario.find("Greater Gargadon", Zone.EXILE)
    assert gargadon.counter_count(Counter.TIME) == 10

    # Ten counters off by hand - Greater Gargadon's own printed "Sacrifice an
    # artifact, creature, or land: Remove a time counter from this card" is an
    # activated ability, not the upkeep trigger, so this is the route
    # `machines/effects.py` takes for it. Taking the *last* one off raises CR
    # 702.62a's third trigger condition all the same, wherever the removal
    # came from, so the free cast is granted by that ability resolving rather
    # than by a `finish_suspend` call.
    for _ in range(10):
        remove_suspend_time_counter(scenario.game, gargadon)
    assert gargadon.counter_count(Counter.TIME) == 0

    # CR 603.3 puts it on the stack "the next time a player would receive
    # priority"; nothing here has passed priority since, so that moment is
    # asked for explicitly rather than waited for.
    assert len(scenario.pending_triggers) == 1
    scenario.game.put_triggers_on_stack()
    _resolve_everything(scenario)
    permission = usable_play_permission(scenario.game, gargadon, "alice")
    assert permission is not None

    casting = Casting(spell=gargadon, caster="alice", origin_zone=Zone.EXILE, game=scenario.game)
    casting.use_permission()
    assert casting.total_cost.mana.converted == 0
    payment = casting.begin_paying()
    payment.pay()
    spell = casting.cast()
    scenario.game.put_on_stack(spell, "alice")
    permanent = scenario.resolve_top()

    assert permanent.zone is Zone.BATTLEFIELD
    assert permanent.summoning_sick is True  # entered this turn, ordinarily sick

    grant_suspend_haste(scenario.game, permanent)

    assert scenario.can_attack(permanent) is True
    scenario.attack_with(permanent)
    assert permanent in scenario.attackers()


# --------------------------------------------------------------------------
# CR 702.62a's second ability, dispatched by the engine itself
#
# The defect this half of the file was written from: a seat suspended two
# Lotus Blooms and the time counters never came off. `Game.emit` never
# offered an exiled card as a source, so nothing was ever asked about
# `TriggerEvent.BEGINNING_OF_STEP`, and suspend's second ability - which CR
# 702.62a says "function[s] in the exile zone" - had no dispatcher at all.
# Every counter that ever came off in this engine came off because a caller
# reached in and called `remove_suspend_time_counter` by hand.
# --------------------------------------------------------------------------


def _suspend_from_hand(scenario: PlayedScenario, name: str, player: str) -> CardState:
    """Take the CR 116.2f special action on `name` in `player`'s hand.

    Lotus Bloom's suspend cost is `{0}`, so there is nothing to tap - the
    payment is opened and paid with no sources at all.
    """
    card = scenario.find(name, Zone.HAND, player)
    action = MarkedExile.suspend(scenario.game, card, player)
    action.begin_paying().pay()
    return action.take()


def _two_blooms() -> PlayedScenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lotus Bloom", "Lotus Bloom"], library=["Forest"] * 12)
        .player("bob", library=["Forest"] * 12)
        .build()
    )


def test_two_suspended_lotus_blooms_each_lose_exactly_one_time_counter():
    """The reported defect, reproduced and fixed, with nothing driven by hand.

    CR 702.62a's second ability: "At the beginning of your upkeep, if this
    card is suspended, remove a time counter from it." Two Lotus Blooms
    suspended for `{0}` (CR 116.2f's special action), then alice's own next
    upkeep - and the engine, not the test, takes exactly one counter off each.

    **Exactly one.** This is the assertion that catches the double tick: the
    api repo drives `remove_suspend_time_counter` itself once per upkeep
    (`engine_api.drive_suspend_upkeep`), so the moment the engine dispatches
    the trigger as well, both run and two counters come off per upkeep. That
    driver has to be deleted in the same landing as this fix.
    """
    scenario = _two_blooms()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first = _suspend_from_hand(scenario, "Lotus Bloom", "alice")
    second = _suspend_from_hand(scenario, "Lotus Bloom", "alice")
    assert [first.counter_count(Counter.TIME), second.counter_count(Counter.TIME)] == [3, 3]

    _advance_to_owners_next_upkeep(scenario, "alice")

    # CR 500.6/503.1a: both triggered at the beginning of the upkeep and are
    # already on the stack, waiting - they are real stack objects (CR 603.3),
    # not a state change the step performed.
    assert len(scenario.game.abilities_on_stack) == 2
    assert [first.counter_count(Counter.TIME), second.counter_count(Counter.TIME)] == [3, 3]

    _resolve_everything(scenario)

    assert [first.counter_count(Counter.TIME), second.counter_count(Counter.TIME)] == [2, 2]

    # And the next one, to prove it is per-upkeep rather than a one-shot.
    _advance_to_owners_next_upkeep(scenario, "alice")
    _resolve_everything(scenario)
    assert [first.counter_count(Counter.TIME), second.counter_count(Counter.TIME)] == [1, 1]


def test_two_simultaneous_suspend_triggers_are_ordered_by_their_controller():
    """CR 603.3b: "each player, in APNAP order, puts each triggered ability
    they control ... on the stack in any order they choose." Two suspended
    cards are two abilities alice controls, so the ordering choice is
    actually put to her - which only happens because these are triggered
    abilities going on the stack, and not a counter the upkeep step took off
    by itself.
    """
    scenario = _two_blooms()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _suspend_from_hand(scenario, "Lotus Bloom", "alice")
    _suspend_from_hand(scenario, "Lotus Bloom", "alice")

    _advance_to_owners_next_upkeep(scenario, "alice")

    ordering = [
        question
        for question in scenario.questions_asked()
        if question.kind is DecisionKind.ORDER_TRIGGERS
    ]
    assert len(ordering) == 1
    assert ordering[0].player == "alice"
    assert len(ordering[0].cards) == 2


def test_the_upkeep_belongs_to_the_owner_and_not_to_whoever_exiled_the_card():
    """CR 109.5 with CR 108.3/108.4a: "the words 'you' and 'your' on an object
    refer to the object's controller, its would-be controller ..., or its
    owner (if it has no controller)", and CR 108.4a - "if anything asks for
    the controller of a card that doesn't have one ... use its owner instead".
    A card in exile is neither a permanent nor a spell, so "your upkeep" is
    the **owner's** upkeep.

    Staged as the shape CR 702.62b actually describes and nothing in this
    engine can yet produce on its own: a card alice owns, sitting in exile
    with time counters on it, exiled by bob. (Suspended Sentence's own final
    clause - "Exile Suspended Sentence with three time counters on it" - is
    exactly this and has no `machines/effects.py` entry, so it cannot be used
    to stage it.) `ExileAnnotation.owner` is the player who took the exiling
    action, which is what the api repo's own driver filtered on; keying on
    that instead of `CardState.owner` ticks this card on the wrong player's
    turn.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", exile=["Lotus Bloom"], library=["Forest"] * 12)
        .player("bob", library=["Forest"] * 12)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bloom = scenario.find("Lotus Bloom", Zone.EXILE)
    bloom.exile_annotation = ExileAnnotation(marker=ExileMarker.SUSPENDED, owner="bob")
    # CR 108.4: a card in exile is neither a permanent nor a spell, so it has
    # no controller at all - and `CardState.move_to` does not clear the field,
    # so bob's name sitting there is exactly the stale value CR 108.4a says to
    # ignore in favour of the owner. Both wrong answers point at bob; only the
    # right one points at alice.
    bloom.controller = "bob"
    scenario.game.add_counters(bloom, Counter.TIME, 3)
    assert bloom.owner == "alice"

    # bob's whole turn, the exiler's own upkeep included: nothing comes off.
    _advance_to_owners_next_upkeep(scenario, "bob")
    _resolve_everything(scenario)
    assert bloom.counter_count(Counter.TIME) == 3

    _advance_to_owners_next_upkeep(scenario, "alice")
    _resolve_everything(scenario)
    assert bloom.counter_count(Counter.TIME) == 2


def test_nothing_ticks_anywhere_in_the_opponents_turn():
    """CR 702.62a says "your upkeep", not "each upkeep" - and the whole of an
    opponent's turn passes without a single counter moving, step by step, not
    merely at its upkeep."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lotus Bloom"], library=["Forest"] * 12)
        .player("bob", library=["Forest"] * 12)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bloom = _suspend_from_hand(scenario, "Lotus Bloom", "alice")

    # The rest of alice's own turn (her upkeep is already behind her) and then
    # the whole of bob's, every single step of both: nothing moves.
    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == "alice"):
        _resolve_everything(scenario)
        scenario.advance()
        assert bloom.counter_count(Counter.TIME) == 3

    # alice's own upkeep, reached at last: exactly one counter.
    _resolve_everything(scenario)
    assert bloom.counter_count(Counter.TIME) == 2


def test_a_foretold_and_a_plotted_card_in_exile_trigger_nothing_all_turn():
    """The line `Game.emit`'s own comment draws: widening what is *asked*
    must never widen what triggers.

    Exile is one shared pile (`Game.shared_zones`), so an unqualified
    widening would start asking every foretold, plotted, madness, cascade and
    hideaway card in it about every event in the game. Only a card CR 702.62b
    calls *suspended* - "in the exile zone, has suspend, and has a time
    counter on it" - is offered as a source, and a full turn cycle with a
    foretold card and a plotted card sitting in exile produces no pending
    trigger at all.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lupine Harbingers", "Slickshot Show-Off"],
            battlefield=["Mountain", "Mountain", "Forest", "Forest"],
            library=["Forest"] * 12,
        )
        .player("bob", library=["Forest"] * 12)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    harbingers = scenario.find("Lupine Harbingers", Zone.HAND, "alice")
    foretell = MarkedExile.foretell(scenario.game, harbingers, "alice")
    scenario.pay_with(
        foretell.begin_paying(), *scenario.untapped_sources("Forest", "Forest", username="alice")
    )
    foretell.take()

    showoff = scenario.find("Slickshot Show-Off", Zone.HAND, "alice")
    plot = MarkedExile.plot(scenario.game, showoff, "alice")
    scenario.pay_with(
        plot.begin_paying(), *scenario.untapped_sources("Mountain", "Mountain", username="alice")
    )
    plot.take()

    assert len(scenario.game.exile) == 2

    # A whole turn cycle, back around to alice's own upkeep.
    _advance_to_owners_next_upkeep(scenario, "alice")
    assert scenario.pending_triggers == []
    assert scenario.game.abilities_on_stack == []


def test_an_exiled_death_trigger_does_not_fire_from_the_exile_pile():
    """The half of the previous test that a too-wide widening actually
    breaks, and the reason the filter is CR 702.62b and not "exile".

    `zones_ability_functions_in` answers `{BATTLEFIELD, source.zone}` for CR
    603.10a's look-back events - "Some zone-change triggers look back in
    time. These are leaves-the-battlefield abilities, abilities that trigger
    when a player sacrifices a permanent, abilities that trigger when a card
    leaves a graveyard, and abilities that trigger when an object that all
    players can see is put into a hand or library" - so a card sitting in
    exile *would* function for a dies trigger the moment it were offered as a
    source. Blood Artist's "Whenever this creature or another creature dies"
    names no particular creature, so it is not the self-referential form
    `condition_matches` refuses either: offering the whole exile pile fires it
    from exile, off a creature dying somewhere else entirely.

    CR 113.6 is what says it must not: "Abilities of all other objects
    usually function only while that object is on the battlefield." A Blood
    Artist card in exile is not on the battlefield and has no ability in play
    at all.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            exile=["Blood Artist"],
            hand=["Lightning Bolt"],
            battlefield=["Grizzly Bears", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[bears])

    assert bears.zone is Zone.GRAVEYARD  # it really died (CR 700.4)
    assert scenario.pending_triggers == []
    assert scenario.game.abilities_on_stack == []
    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 20


def test_removing_the_card_from_exile_in_response_stops_the_tick():
    """CR 603.4's intervening *if* is checked twice - once when the ability
    triggers, and again by CR 608.2a as it resolves: "if the condition isn't
    true at that time, the ability is removed from the stack and does
    nothing."

    Two Lotus Blooms so the point is visible rather than merely absent: both
    triggers go on the stack, one card leaves exile before they resolve, and
    the other one still ticks. The one that left is untouched by its own
    ability - which is the only way to see this, since CR 400.7 makes a card
    that changes zones a new object and CR 122.2 takes its counters off on the
    way out regardless of what the ability would have done.
    """
    scenario = _two_blooms()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    leaving = _suspend_from_hand(scenario, "Lotus Bloom", "alice")
    staying = _suspend_from_hand(scenario, "Lotus Bloom", "alice")

    _advance_to_owners_next_upkeep(scenario, "alice")
    assert len(scenario.game.abilities_on_stack) == 2
    assert leaving.counter_count(Counter.TIME) == 3

    # One leaves exile while both abilities are still on the stack - the card
    # goes to its owner's graveyard, which is a zone CR 702.62b's "in the
    # exile zone" is simply not true of.
    scenario.game.put_into_graveyard(leaving)

    _resolve_everything(scenario)

    assert scenario.game.stack_is_empty
    assert leaving.zone is Zone.GRAVEYARD
    # Its own ability was removed from the stack and did nothing: no free-cast
    # permission was ever granted, which is what CR 702.62a's third ability
    # would have handed out had the second one been allowed to take its last
    # counter off.
    assert usable_play_permission(scenario.game, leaving, "alice") is None
    # And the batch resolved perfectly normally around it.
    assert staying.counter_count(Counter.TIME) == 2


def test_a_card_at_zero_time_counters_is_no_longer_suspended_and_never_ticks_again():
    """CR 702.62b: "A card is 'suspended' if it's in the exile zone, has
    suspend, **and has a time counter on it**." A card sitting in exile at
    zero counters fails the last clause, so the second ability does not
    trigger at all on any later upkeep - it does not go on the stack, and
    there is nothing to remove.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", exile=["Lotus Bloom"], library=["Forest"] * 12)
        .player("bob", library=["Forest"] * 12)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bloom = scenario.find("Lotus Bloom", Zone.EXILE)
    bloom.exile_annotation = ExileAnnotation(marker=ExileMarker.SUSPENDED, owner="alice")
    assert bloom.counter_count(Counter.TIME) == 0
    assert bloom.is_suspended is False

    _advance_to_owners_next_upkeep(scenario, "alice")

    assert scenario.pending_triggers == []
    assert scenario.game.abilities_on_stack == []
    assert bloom.counter_count(Counter.TIME) == 0
