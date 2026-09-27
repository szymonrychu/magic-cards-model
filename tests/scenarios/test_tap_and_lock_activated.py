"""Braided Net // Braided Quipu's two activated abilities (R0a T8).

Every CR number here was looked up with `mise run rules:find <number>` against
the 2026-09-25 Comprehensive Rules release in the session that wrote this file.

**Braided Net**: "{T}, Remove a net counter from this artifact: Tap another
target nonland permanent. Its activated abilities can't be activated for as
long as it remains tapped."

- **CR 701.26a** taps the target.
- **CR 611.2b** - "It doesn't start and immediately stop again, and it doesn't
  last forever": the lock's own duration is a `RemainsTapped` condition
  (`machines/layers.py`), a one-shot resolved effect distinct from
  `Game._activation_prohibition`'s static, printed-text-only scan (Karn, the
  Great Creator's "Activated abilities of artifacts your opponents control
  can't be activated.") - this reads a layer-6 grant off the *computed* board
  instead (CR 613.5), the same way `DOESNT_UNTAP_TEXT` already does.
- **CR 602.5** - "A player can't begin to activate an ability that's
  prohibited from being activated": `Game.why_cannot_activate` reads the
  grant.
- Once the target untaps, the lock has ended for good: `RemainsTapped.
  can_restart = True` tells `ContinuousEffects.active` to drop it the moment
  it first reads false, so tapping the same permanent again later does not
  revive it.

Proof-of-generality note: this exact duration ("for as long as it remains
tapped") and this exact rider ("activated abilities can't be activated") each
generalise machinery four other real, differently-worded printings already
prove in this test suite - `_TAP_THEN_LOCK_RE`'s own docstring names The
Wondrous Wasp, Spider-Woman Secret Agent, Dungeon Geists and Icefall Regent -
but a Scryfall text search for "for as long as it remains tapped" (run in the
session that wrote this file) returns Braided Net alone: nobody else has ever
printed this exact combination. Recorded as a dated line in `MEMORY.md`
rather than substituted with an unrelated card, per the acceptance note that
a substitution is only owed when one exists.

**Braided Quipu**: "{3}{U}, {T}: Draw a card for each artifact you control,
then put this artifact into its owner's library third from the top." Reuses
`machines/effects.py`'s existing "draw a card for each `<expr>`" reader
(`_DRAW_RE`) and its existing self-referential "put `<self>` into its
owner's library `<ordinal>` from the top" reader
(`_parse_dead_object_to_library_clause`/`_DEAD_OBJECT_TO_LIBRARY_RE`, used
by Bookwurm and Borborygmos and Fblthp) - widened here to recognise "this
artifact" alongside "this permanent/creature/card" (CR 201.5/CR 607.1
self-reference, generalised to a fourth noun, not gated on this card's name).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

NET = "Braided Net"


def _board(**kwargs) -> Scenario:
    return Scenario().player("alice", **kwargs)


def test_tap_and_lock_taps_target_and_removes_a_net_counter():
    """CR 701.26a taps the target; the printed cost removes one net counter
    (CR 122.3)."""
    scenario = _board(battlefield=[NET, "Wrenn and Six"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    net = scenario.find(NET, Zone.BATTLEFIELD, "alice")
    wrenn = scenario.find("Wrenn and Six", Zone.BATTLEFIELD, "alice")
    net.add_counters("net", 3)

    scenario.activate(net, targets=[wrenn])
    scenario.resolve_top()

    assert net.counters.root.get("net") == 2
    assert wrenn.tapped is True


def test_tap_and_lock_prohibits_activation_while_tapped():
    """The rider: a locked permanent's activated abilities can't be
    activated (CR 602.5) even when the ability's own cost carries no `{T}`
    at all - Wrenn and Six's loyalty abilities pay only loyalty, never a
    tap, so the refusal proves the *lock*, not CR 602.5a's ordinary
    summoning-sickness tap gate.
    """
    scenario = _board(battlefield=[NET, "Wrenn and Six"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    net = scenario.find(NET, Zone.BATTLEFIELD, "alice")
    wrenn = scenario.find("Wrenn and Six", Zone.BATTLEFIELD, "alice")
    net.add_counters("net", 3)
    # Loyalty index 1 is "-1: Wrenn and Six deals 1 damage to any target." -
    # activatable before the lock (only the printed loyalty cost applies).
    assert scenario.why_cannot_activate(wrenn, 1) is None

    scenario.activate(net, targets=[wrenn])
    scenario.resolve_top()

    refusal = scenario.why_cannot_activate(wrenn, 1)
    assert refusal is not None
    assert "can't be activated" in refusal


def test_tap_and_lock_does_not_restart_once_untapped():
    """CR 611.2b: the duration doesn't start and immediately stop again, and
    once it has ended it does not begin again - untapping the target ends
    the lock for good, and tapping it again later (by any means) does not
    revive it.
    """
    scenario = _board(battlefield=[NET, "Wrenn and Six"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    net = scenario.find(NET, Zone.BATTLEFIELD, "alice")
    wrenn = scenario.find("Wrenn and Six", Zone.BATTLEFIELD, "alice")
    net.add_counters("net", 3)

    scenario.activate(net, targets=[wrenn])
    scenario.resolve_top()
    assert scenario.why_cannot_activate(wrenn, 1) is not None

    wrenn.untap()
    assert scenario.why_cannot_activate(wrenn, 1) is None

    wrenn.tap()
    refusal = scenario.why_cannot_activate(wrenn, 1)
    assert refusal is None or "can't be activated" not in refusal


def test_tap_and_lock_refuses_targeting_itself():
    """ "Tap **another** target nonland permanent" (CR 601.2c/602.2b's
    "appropriate object") - Braided Net has no legal target with only
    itself on the battlefield, so the activation is refused outright
    (CR 601.2e, imported by 602.2b).
    """
    scenario = _board(battlefield=[NET]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    net = scenario.find(NET, Zone.BATTLEFIELD, "alice")
    net.add_counters("net", 3)

    with pytest.raises(ValueError):
        scenario.activate(net, index=0)


def test_braided_quipu_draws_then_reshuffles_itself_third_from_top():
    """The back face's "{3}{U}, {T}: Draw a card for each artifact you
    control, then put this artifact into its owner's library third from the
    top." (CR 400.7/CR 712.8a: the *back* face's own text applies once
    `transformed`)."""
    scenario = _board(
        battlefield=[NET, "Sol Ring", "Island", "Island", "Island", "Island"],
        library=["Forest", "Forest", "Mountain", "Plains", "Swamp"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    net = scenario.find(NET, Zone.BATTLEFIELD, "alice")
    net.transformed = True
    assert net.name == "Braided Quipu"

    scenario.activate(net, index=0, auto=True)
    scenario.resolve_top()

    alice = scenario.player("alice")
    # Two artifacts controlled (the Quipu itself plus Sol Ring) -> two cards.
    assert [c.name for c in alice.hand] == ["Forest", "Forest"]
    library_names = [c.name for c in alice.library]
    assert library_names == ["Mountain", "Plains", "Braided Net", "Swamp"]
    # CR 712.8a: off the battlefield, the front face's name applies again.
    assert library_names[2] == "Braided Net"


def test_braided_quipu_draws_zero_with_no_artifacts_and_still_moves_itself():
    """ "Draw a card for each artifact you control" with only the Quipu
    itself on the battlefield draws one card (CR 107.3), still followed by
    the unconditional self-placement."""
    scenario = _board(
        battlefield=[NET, "Island", "Island", "Island", "Island"],
        library=["Forest"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    net = scenario.find(NET, Zone.BATTLEFIELD, "alice")
    net.transformed = True

    scenario.activate(net, index=0, auto=True)
    scenario.resolve_top()

    alice = scenario.player("alice")
    assert [c.name for c in alice.hand] == ["Forest"]
    assert [c.name for c in alice.library] == ["Braided Net"]
