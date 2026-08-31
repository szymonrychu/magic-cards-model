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
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color, Type
from magic_cards_model.models.card_state import Counter, ExileMarker
from tests.scenarios.harness import PlayedScenario, Scenario


def _advance_to_owners_next_upkeep(scenario: PlayedScenario, owner: str) -> None:
    """Walk the real turn machine forward to `owner`'s own next upkeep step -
    CR 702.62a says "at the beginning of *your* upkeep", so this steps clean
    through any other player's turn in between rather than firing on it.
    """
    scenario.advance()
    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == owner):
        scenario.advance()


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
        remaining = remove_suspend_time_counter(scenario.game, living_end)
        assert remaining == expected_remaining

    permission = finish_suspend(scenario.game, living_end)
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
        remove_suspend_time_counter(scenario.game, living_end)

    assert scenario.step is Step.UPKEEP
    permission = finish_suspend(scenario.game, living_end)
    assert permission is not None
    assert permission.immediate is True

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

    for _ in range(10):
        remove_suspend_time_counter(scenario.game, gargadon)
    assert gargadon.counter_count(Counter.TIME) == 0

    permission = finish_suspend(scenario.game, gargadon)
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
