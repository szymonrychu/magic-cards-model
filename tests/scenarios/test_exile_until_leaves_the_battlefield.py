"""Exile "until this permanent leaves the battlefield" (Static Prison).

Static Prison's own ETB: "exile target nonland permanent an opponent controls
until this enchantment leaves the battlefield. You get {E}{E}." Two things
had to be built for this to do anything at all:

- **A targeted clause reader that keeps the duration instead of refusing it.**
  `machines/effects._TRAILING_DURATION_RE` fails closed on *any* "until ..."
  tail (see its own docstring) because most of them have no reversal built -
  correctly conservative for those, wrong for this one shape now that it has
  one. `_EXILE_UNTIL_THIS_LEAVES_BATTLEFIELD_RE` is read ahead of the general
  `_EXILE_TARGET_RE`, whose `.*target.+` phrase would otherwise swallow the
  "until ..." tail into its own restriction and get refused by that same
  guard - `test_static_prisons_enters_trigger_does_not_parse_as_a_whole`
  (`tests/test_effects.py`) is the old, now-superseded proof of that gap.
- **The rule for what the reversal actually is.** Verified this session with
  `knowledge_search(type="rules")`:

    - **CR 610.2** - "Some one-shot effects create a delayed triggered
      ability, which instructs a player to do something later in the game
      ... rather than as the spell or ability that's creating them doing it
      immediately." The return is a *second one-shot effect*, created the
      moment the enchantment's ETB resolves (CR 603.7a), not a
      `ContinuousEffects` duration this engine would have to notice has
      "expired". Modelling it as a duration would return the card at the
      wrong moment (never, in this engine, since nothing here expires a
      duration on a *different* object's zone change) - this is why the
      primitive is a `DelayedTrigger`, the same CR 603.7 machinery warp and
      earthbend already use.
    - **CR 603.7a/603.7b/603.7c** - created now; triggers once, the next time
      its event occurs; and refuses to affect an object that has moved on by
      the time it resolves (the round-trip-through-another-zone case).
    - **CR 701.8a, 701.21a, 701.13a, 701.19a** - destroy, sacrifice, exile,
      and return are four different verbs, but only three *events* an
      enchantment leaving the battlefield can raise in this engine: `DIES`
      covers both destruction and sacrifice (both are "the permanent moves to
      its owner's graveyard", CR 700.4), and `LEAVES_BATTLEFIELD_TO_EXILE`/
      `LEAVES_BATTLEFIELD_TO_HAND` cover the other two. "By any means" is not
      one event, so `_watch_for_departure_and_return_exiled_card` creates
      three sibling `DelayedTrigger`s the same way earthbend's own "dies or
      is put into exile" already creates two.
    - **CR 108.3** - the exiled card's *owner* is who it returns to, not
      whoever controlled it before (the general blink idiom's own default,
      CR 610.3c, unchanged by anything Static Prison's text overrides).

Corner cases are the point of this file, not the happy path alone: all three
departure routes, the fail-closed guard staying fail-closed for a duration
this wave still does not reverse, and the double-leave/`expected_stamp`
guard that stops a second, wrong return.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board() -> Scenario:
    return (
        Scenario()
        .player("alice", hand=["Static Prison"], battlefield=["Plains"])
        .player("bob", battlefield=["Grizzly Bears"])
    )


def _cast_static_prison(scenario, bears):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (plains,) = scenario.untapped_sources("Plains")
    scenario.choose_trigger_targets("Static Prison", [bears])
    prison = scenario.cast_and_resolve("Static Prison", plains)
    scenario.pass_until_resolved()  # the ETB trigger: exile Grizzly Bears
    return prison


def test_the_targeted_permanent_is_exiled_and_the_controller_gets_energy():
    scenario = _board().build()
    bears = scenario.creature("Grizzly Bears", "bob")

    _cast_static_prison(scenario, bears)

    assert bears.zone is Zone.EXILE
    assert scenario.player("alice").energy == 2


def test_destroying_static_prison_returns_the_exiled_creature():
    """CR 701.8a's destroy, one of the three departure routes."""
    scenario = _board().build()
    bears = scenario.creature("Grizzly Bears", "bob")
    prison = _cast_static_prison(scenario, bears)

    assert bears.zone is Zone.EXILE
    assert scenario.player("alice").energy == 2

    scenario.game.destroy(prison)
    scenario.pass_until_resolved()  # the delayed trigger: return Grizzly Bears

    assert prison.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(bears).username == "bob"


def test_exiling_static_prison_returns_the_exiled_creature():
    """CR 701.13a's exile, the second departure route."""
    scenario = _board().build()
    bears = scenario.creature("Grizzly Bears", "bob")
    prison = _cast_static_prison(scenario, bears)

    scenario.game.exile_permanent(prison)
    scenario.pass_until_resolved()

    assert prison.zone is Zone.EXILE
    assert bears.zone is Zone.BATTLEFIELD


def test_bouncing_static_prison_returns_the_exiled_creature():
    """CR 701.19a's return, the third departure route - the one this wave
    had to teach `Game.return_to_hand` to emit at all (it emitted nothing
    before this fix).
    """
    scenario = _board().build()
    bears = scenario.creature("Grizzly Bears", "bob")
    prison = _cast_static_prison(scenario, bears)

    scenario.game.return_to_hand(prison)
    scenario.pass_until_resolved()

    assert prison.zone is Zone.HAND
    assert bears.zone is Zone.BATTLEFIELD


def test_sacrificing_static_prison_returns_the_exiled_creature():
    """CR 701.21a's sacrifice - the same `DIES` event as a plain destroy, so
    this is not a fourth event to watch, only a second way to reach one of
    the three already covered.
    """
    scenario = _board().build()
    bears = scenario.creature("Grizzly Bears", "bob")
    prison = _cast_static_prison(scenario, bears)

    scenario.game.sacrifice(prison)
    scenario.pass_until_resolved()

    assert prison.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD


def test_the_return_does_not_fire_twice_for_the_same_departure():
    """The three sibling triggers all watch the same one-shot ability
    (CR 603.7b): once destruction fires the `DIES` sibling, the other two
    are dropped rather than left to spend themselves uselessly or, worse,
    fire again if Grizzly Bears is somehow exiled or bounced afterward.
    """
    scenario = _board().build()
    bears = scenario.creature("Grizzly Bears", "bob")
    prison = _cast_static_prison(scenario, bears)

    scenario.game.destroy(prison)
    scenario.pass_until_resolved()
    assert bears.zone is Zone.BATTLEFIELD

    assert scenario.game.delayed_triggers.triggers == []


def test_a_creature_that_left_and_returned_before_the_prison_does_is_not_pulled_back():
    """CR 603.7c's parenthetical: "if that object left that zone and then
    returned, it's a new object". If Grizzly Bears is somehow returned to
    the battlefield some *other* way while still exiled-by-Static-Prison in
    this engine's bookkeeping, and then Static Prison leaves, the delayed
    trigger must not reach for whatever now has that id - `expected_stamp`
    is what tells the two incarnations apart. Simulated here by manually
    reincarnating Grizzly Bears through the battlefield and back to exile
    before Static Prison leaves, which changes its `zone_change_stamp` out
    from under the trigger's `still_affects`-shaped check.
    """
    scenario = _board().build()
    bears = scenario.creature("Grizzly Bears", "bob")
    prison = _cast_static_prison(scenario, bears)
    assert bears.zone is Zone.EXILE

    # A second, unrelated zone round-trip: some other effect returns Grizzly
    # Bears to the battlefield and then it leaves again - the exiled object
    # this trigger was watching is gone; a new one has taken its `id`.
    scenario.game.put_onto_battlefield(bears, "bob", tapped=False)
    scenario.game.exile_permanent(bears)

    scenario.game.destroy(prison)
    scenario.pass_until_resolved()

    # The trigger fired (Static Prison is gone), but `still_affects` refused
    # the new incarnation - Grizzly Bears stays in exile rather than being
    # silently pulled back for a departure it was never exiled for.
    assert bears.zone is Zone.EXILE


def test_a_duration_this_wave_still_cannot_reverse_stays_fail_closed():
    """`_TRAILING_DURATION_RE`'s blanket refusal is still exactly that for
    every *other* trailing duration - only the one specific "until this
    `<type>` leaves the battlefield" shape now has a real reversal. A
    hypothetical "... until end of turn" clause on the same verb must still
    come back unread rather than quietly exiling forever, which is exactly
    what `_targets_understood`'s guard already tested at the unit level
    (`tests/test_effects.py`); this is the scenario-level half of the same
    proof, confirming the new regex is narrow rather than swallowing
    durations it has no reversal for.
    """
    from magic_cards_model.machines.effects import (
        _EXILE_UNTIL_THIS_LEAVES_BATTLEFIELD_RE,
        _parse_exile_until_leaves_battlefield_clause,
        _parse_targeted_clause,
    )

    hypothetical = "exile target creature until end of turn"
    assert _EXILE_UNTIL_THIS_LEAVES_BATTLEFIELD_RE.fullmatch(hypothetical) is None
    assert _parse_exile_until_leaves_battlefield_clause(hypothetical, for_spell=False) is None
    assert _parse_targeted_clause(hypothetical, for_spell=False) is None
