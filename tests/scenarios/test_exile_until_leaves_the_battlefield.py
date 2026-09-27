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


# -- R0a-T5: the mass form, "exile all <group> until this <type> leaves the
# battlefield" (CR 610.3), and the linked "put each card exiled with this
# <type> into its owner's graveyard" (CR 607.1) ------------------------------
#
# Pinnacle Starcage: "When this artifact enters, exile all artifacts and
# creatures with mana value 2 or less until this artifact leaves the
# battlefield." and "{6}{W}{W}: Put each card exiled with this artifact into
# its owner's graveyard, then create a 2/2 colorless Robot artifact creature
# token for each card put into a graveyard this way. Sacrifice this
# artifact." Aligned Hedron Network (a power comparison) and Consulate
# Crackdown (a controller qualifier, an enchantment) are the second and third
# printings, both Modern/Pioneer legal and in no deck.


def _starcage_board(extra_plains: int = 0):
    return (
        Scenario()
        .player(
            "alice",
            hand=["Pinnacle Starcage"],
            battlefield=["Plains"] * (3 + extra_plains) + ["Memnite"],
            library=["Plains"] * 5,
        )
        .player(
            "bob",
            battlefield=["Grizzly Bears", "Ornithopter", "Colossal Dreadmaw"],
            library=["Plains"] * 5,
        )
    )


def _cast_starcage(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    starcage = scenario.cast_and_resolve(
        "Pinnacle Starcage", *scenario.untapped_sources("Plains", "Plains", "Plains")
    )
    scenario.pass_until_resolved()  # the enters trigger
    return starcage


def test_starcage_exiles_every_small_artifact_and_creature_on_both_sides():
    scenario = _starcage_board().build()
    bears = scenario.creature("Grizzly Bears", "bob")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    memnite = scenario.creature("Memnite", "alice")
    thopter = scenario.creature("Ornithopter", "bob")

    starcage = _cast_starcage(scenario)

    assert bears.zone is Zone.EXILE
    assert memnite.zone is Zone.EXILE  # "all" - its controller's own too
    assert thopter.zone is Zone.EXILE
    assert dreadmaw.zone is Zone.BATTLEFIELD  # mana value 6
    assert starcage.zone is Zone.BATTLEFIELD  # mana value 3, and not itself small


def test_they_return_when_the_starcage_leaves():
    scenario = _starcage_board().build()
    bears = scenario.creature("Grizzly Bears", "bob")
    memnite = scenario.creature("Memnite", "alice")
    starcage = _cast_starcage(scenario)

    scenario.game.destroy(starcage)
    for _ in range(3):  # one return per exiled card: Bears, Ornithopter, Memnite
        scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(bears).username == "bob"  # CR 610.3c
    assert memnite.zone is Zone.BATTLEFIELD


def test_the_activated_ability_puts_them_in_graveyards_and_makes_robots():
    scenario = _starcage_board(extra_plains=8).build()
    bears = scenario.creature("Grizzly Bears", "bob")
    memnite = scenario.creature("Memnite", "alice")
    starcage = _cast_starcage(scenario)

    scenario.activate(starcage, *scenario.untapped_sources(*["Plains"] * 8))
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert bears in scenario.player("bob").graveyard
    assert memnite in scenario.player("alice").graveyard
    assert starcage.zone is Zone.GRAVEYARD  # "Sacrifice this artifact."
    robots = [p for p in scenario.game.battlefield if "Robot" in p.name]
    assert len(robots) == 3  # Bears, Ornithopter, Memnite
    assert all(scenario.game.controller_of(robot).username == "alice" for robot in robots)
    # Nothing comes back: the cards left exile before the Starcage left.
    assert bears.zone is Zone.GRAVEYARD


def test_aligned_hedron_network_exiles_by_power():
    scenario = (
        Scenario()
        .player("alice", hand=["Aligned Hedron Network"], battlefield=["Plains"] * 4)
        .player("bob", battlefield=["Colossal Dreadmaw", "Grizzly Bears"])
        .build()
    )
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    network = scenario.cast_and_resolve(
        "Aligned Hedron Network", *scenario.untapped_sources(*["Plains"] * 4)
    )
    scenario.pass_until_resolved()

    assert dreadmaw.zone is Zone.EXILE
    assert bears.zone is Zone.BATTLEFIELD

    scenario.game.return_to_hand(network)
    scenario.pass_until_resolved()
    assert dreadmaw.zone is Zone.BATTLEFIELD


def test_consulate_crackdown_exiles_only_opponents_artifacts():
    scenario = (
        Scenario()
        .player("alice", hand=["Consulate Crackdown"], battlefield=["Plains"] * 5 + ["Memnite"])
        .player("bob", battlefield=["Ornithopter", "Grizzly Bears"])
        .build()
    )
    memnite = scenario.creature("Memnite", "alice")
    thopter = scenario.creature("Ornithopter", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Consulate Crackdown", *scenario.untapped_sources(*["Plains"] * 5))
    scenario.pass_until_resolved()

    assert thopter.zone is Zone.EXILE
    assert memnite.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.BATTLEFIELD


def test_the_mass_exile_cards_are_credited():
    from magic_cards_model.support import card_support
    from tests.cards import card

    for name in ("Pinnacle Starcage", "Aligned Hedron Network", "Consulate Crackdown"):
        support = str(card_support(card(name)))
        assert "'silent'" not in support, name
        assert "'notice'" not in support, name
