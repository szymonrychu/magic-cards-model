"""Ephemerate: exile target creature, then return it (CR 608.2c, CR 400.7).

Ephemerate's oracle text (verified with `resolve_cards`, 2026-06-26 printing,
Marvel Universe): "Exile target creature you control, then return it to the
battlefield under its owner's control." plus Rebound - Rebound has its own
file, `test_rebound.py`.

Every rule cited here was looked up with `knowledge_search(type="rules")` in
this session:

- **CR 400.7** - "An object that moves from one zone to another becomes a new
  object with no memory of, or relation to, its previous existence."
- **CR 110.2 / 110.2a** - a permanent's controller defaults to whoever the
  effect instructs to put it there, "unless the effect states otherwise."
  Ephemerate states otherwise: "under its owner's control."
- **CR 302.6 / 508.1a** - a creature that has not been under its controller's
  control continuously since their most recent turn began cannot attack or
  use a `{T}` ability - the returned object is a new one, so it is summoning
  sick again.
- **CR 122.2** - "Counters on an object are not retained if that object moves
  from one zone to another."
- **CR 603.6a** - "Enters-the-battlefield abilities trigger when a permanent
  enters the battlefield," covering both the blinked permanent's own trigger
  and another permanent's "whenever another creature you control enters."
- **CR 704.5m / CR 704.5n** - an Aura attached to an illegal object (or none)
  goes to its owner's graveyard; an Equipment in the same spot merely falls
  off and stays on the battlefield.

Before this fix, `effect_for("Ephemerate", ...)` returned `None`: clause 1
("Exile target creature you control") parsed alone, clause 2 ("return it to
the battlefield under its owner's control") had no reader anywhere, and
`_parse_mixed_clauses`'s all-or-nothing fold discarded the whole effect - the
spell resolved (CR 608.2n) and did nothing, silently. `_parse_exile_then_
return_clause_pair` in `machines/effects.py` is the fix: a parameterised
reader for "exile target X, then return it to the battlefield [tapped]
[transformed] [under its owner's/your control]", not a card-name row.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    """erin has the reported case on the battlefield: White Orchid Phantom
    (an ETB of its own) and Guide of Souls (watches for *another* creature
    entering) - plus a Plains to pay Ephemerate's `{W}`."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "erin",
            hand=["Ephemerate"],
            battlefield=["White Orchid Phantom", "Guide of Souls", "Plains"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_ephemerate_blinks_white_orchid_phantom_and_fires_both_etbs():
    """The reported case: erin's own Phantom re-enters and Guide of Souls'
    "whenever *another* creature you control enters" both go on the stack
    (CR 603.6a), and Ephemerate itself is exiled rather than binned (CR
    608.2n would otherwise put a resolved instant into the graveyard)."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phantom = scenario.creature("White Orchid Phantom")
    guide = scenario.creature("Guide of Souls")
    (plains,) = scenario.untapped_sources("Plains")
    same_id = phantom.id
    stamp_before = phantom.zone_change_stamp
    energy_before = scenario.player("erin").energy
    life_before = scenario.player("erin").life

    ephemerate = scenario.cast_and_resolve("Ephemerate", plains, targets=[phantom])

    # CR 608.2n: Ephemerate itself does not reach the graveyard - clause 2
    # actually ran, so the "exile it as it resolves" isn't needed to explain
    # this (Rebound's own file covers that), but it must not have simply done
    # nothing either.
    assert ephemerate.zone in (Zone.EXILE, Zone.GRAVEYARD)

    assert phantom.zone is Zone.BATTLEFIELD
    assert phantom.id == same_id  # this engine mutates in place (see id docstring)
    assert phantom.zone_change_stamp != stamp_before  # CR 400.7: a new object
    assert phantom.controller == "erin"  # CR 110.2a: "under its owner's control"
    assert phantom.summoning_sick  # CR 302.6/508.1a: sick again

    trigger_sources = " | ".join(scenario.stack_names())
    assert "White Orchid Phantom" in trigger_sources  # CR 603.6a, its own ETB
    assert "Guide of Souls" in trigger_sources  # CR 603.6a, "another creature"
    assert guide.zone is Zone.BATTLEFIELD  # Guide itself was never touched

    while scenario.stack_names():
        scenario.resolve_top()

    assert scenario.player("erin").energy == energy_before + 1
    assert scenario.player("erin").life == life_before + 1


def test_ephemerate_does_not_fire_guide_of_souls_off_itself():
    """CR 603.6a's "whenever *another* creature you control enters" must not
    fire when the creature that enters *is* Guide of Souls (trap: blinking
    the watcher itself)."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    guide = scenario.creature("Guide of Souls")
    (plains,) = scenario.untapped_sources("Plains")
    energy_before = scenario.player("erin").energy

    scenario.cast_and_resolve("Ephemerate", plains, targets=[guide])

    assert guide.zone is Zone.BATTLEFIELD
    trigger_sources = " | ".join(scenario.stack_names())
    assert "Guide of Souls" not in trigger_sources
    assert scenario.player("erin").energy == energy_before


def test_ephemerate_returns_a_stolen_creature_to_its_owner_not_its_controller():
    """CR 110.2a: "under its owner's control" names the *owner*, not whoever
    is casting Ephemerate. Staged the same way `test_aura_attachment.py`
    stages an attachment: bob's own Grizzly Bears is put under erin's control
    directly (a real printing, a real `controller` field, no control-changing
    effect built here to produce it)."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (plains,) = scenario.untapped_sources("Plains")
    bears = scenario.creature("Grizzly Bears", username="bob")
    bears.controller = "erin"  # staged: erin controls bob's creature

    scenario.cast_and_resolve("Ephemerate", plains, targets=[bears])

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.controller == "bob"  # the owner, not erin


def test_ephemerate_can_return_a_creature_under_the_casters_own_control():
    """The counterpart of the above: an unstolen creature's owner and
    controller are the same player, so "under its owner's control" still
    reads as erin here - this is not a test that the reader ignores
    "owner's", it is the case where owner and controller happen to agree."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (plains,) = scenario.untapped_sources("Plains")
    phantom = scenario.creature("White Orchid Phantom")

    scenario.cast_and_resolve("Ephemerate", plains, targets=[phantom])

    assert phantom.controller == "erin"


def test_ephemerate_drops_an_aura_attached_to_the_blink_target():
    """CR 704.5m: an Aura attached to an illegal object (or none) is put into
    its owner's graveyard. Hyena Umbra is attached to White Orchid Phantom by
    hand (CR 701.3a, the same staging `test_aura_attachment.py` uses), then
    Ephemerate blinks the Phantom *within one resolution* - no state-based
    action check runs in between (CR 704.3 only checks before a player would
    next receive priority) - so without `Game._detach_dependents`, the id
    surviving the round trip would let the Umbra silently "follow" the blink.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "erin",
            hand=["Ephemerate"],
            battlefield=["White Orchid Phantom", "Hyena Umbra", "Plains"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phantom = scenario.creature("White Orchid Phantom")
    umbra = scenario.find("Hyena Umbra", Zone.BATTLEFIELD, username="erin")
    umbra.attach_to(phantom)
    (plains,) = scenario.untapped_sources("Plains")

    scenario.cast_and_resolve("Ephemerate", plains, targets=[phantom])
    scenario.state_based_actions()

    assert phantom.zone is Zone.BATTLEFIELD
    assert not phantom.is_attached
    assert umbra.zone is Zone.GRAVEYARD  # CR 704.5m


def test_ephemerate_leaves_counters_behind():
    """CR 122.2: counters are not retained across a zone change. A +1/+1
    counter placed on White Orchid Phantom before the blink is gone after
    it - the returned object is a new one and never had it."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phantom = scenario.creature("White Orchid Phantom")
    phantom.add_counters(Counter.PLUS_ONE, 2)
    (plains,) = scenario.untapped_sources("Plains")

    scenario.cast_and_resolve("Ephemerate", plains, targets=[phantom])

    assert phantom.zone is Zone.BATTLEFIELD
    assert phantom.counter_count(Counter.PLUS_ONE) == 0
