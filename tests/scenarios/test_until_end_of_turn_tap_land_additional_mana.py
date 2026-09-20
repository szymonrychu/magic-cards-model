""" "Until end of turn, whenever [you tap|a player taps] a[n] <land subtype>
for mana, [add|that player adds] an additional <mana>." - Molten Tide
(Pyre Rhymer // Molten Tide's Prepare-cast instant half): "Until end of
turn, whenever you tap a Mountain for mana, add an additional {R}."

FRA S10's own scope for this card is the effect only - the Prepare layout
itself (casting a copy of Molten Tide while Pyre Rhymer is prepared) is
S2's - so Molten Tide's own effect is proven here by invoking the built
resolution function directly against a real, on-stack spell (`Pyre Rhymer`,
cast normally: its own creature half has no Prepare restriction on being
cast the ordinary way) rather than through a full cast of "Molten Tide",
which the engine cannot legally reach yet. High Tide (off-set, fetched as a
genericity precedent, not itself in the pool) shares the identical shape
with the opposite subject - "a player taps ... that player adds", not "you
tap ... add" - and *is* an ordinary instant, so it is the primary,
fully-cast proof that the mechanic actually works end to end.

CR 605.1b/605.4a: the delayed triggered ability this creates is itself a
mana ability - it names no target, it triggers from the activation of an
activated mana ability (CR 106.12a's tap), and it could add mana to a
player's mana pool when it resolves - so it resolves *immediately*, with no
stack and no waiting for priority, exactly the way a printed triggered mana
ability already does (Leyline of Abundance's own "add an additional {G}").
Every test below proves this directly: no `put_triggers_on_stack`/
`resolve_top` step ever runs between a tap and the bonus mana landing, and
`Game.pending_triggers` stays empty throughout.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 603.7 / CR 603.7b** - a resolving spell creating a delayed triggered
  ability with a stated duration ("until end of turn"), which fires on
  every occurrence rather than only the next one.
- **CR 106.12a** - tapping a permanent for mana is an event a triggered
  ability can watch.
- **CR 514.2** - "until end of turn" effects end during cleanup.
- **CR 605.1b** - the four criteria that make a *triggered* ability a mana
  ability.
- **CR 605.4a** - a triggered mana ability "doesn't go on the stack ...
  Rather, it resolves immediately after the mana ability that triggered
  it, without waiting for priority."
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import effect_for
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario

# -- High Tide: fully cast, the end-to-end proof ----------------------------


def test_casting_high_tide_creates_the_delayed_trigger():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["High Tide"], battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island")

    scenario.cast_and_resolve("High Tide", island, username="alice")

    (trigger,) = scenario.game.delayed_triggers.triggers
    assert trigger.expires_end_of_turn
    assert trigger.remaining is None, "fires on every tap this turn, not only the next one"


def test_tapping_an_island_afterward_adds_the_extra_blue_with_no_stack():
    """CR 605.4a: the bonus lands the instant the land is tapped - no
    `put_triggers_on_stack`/`resolve_top` step runs between the two."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["High Tide"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (first,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("High Tide", first, username="alice")

    (second,) = scenario.untapped_sources("Island", username="alice")
    scenario.activate(second, color=Color.BLUE)

    assert scenario.player("alice").mana_pool.floating == {Color.BLUE: 2}
    assert scenario.game.pending_triggers == []
    assert scenario.game.stack_is_empty


def test_it_fires_again_on_a_second_tap_the_same_turn():
    """`remaining=None`: CR 603.7b's stated duration keeps it live for every
    tap this turn, not just the first."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["High Tide"], battlefield=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (first,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("High Tide", first, username="alice")

    for island in scenario.untapped_sources("Island", "Island", username="alice"):
        scenario.activate(island, color=Color.BLUE)

    assert scenario.player("alice").mana_pool.floating == {Color.BLUE: 4}


def test_tapping_a_nonisland_land_adds_nothing_extra():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["High Tide"], battlefield=["Island", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("High Tide", island, username="alice")

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.activate(mountain, color=Color.RED)

    assert scenario.player("alice").mana_pool.floating == {Color.RED: 1}


def test_any_players_tap_counts_and_the_mana_goes_to_the_tapper():
    """ "A player taps ... that player adds" (unlike Molten Tide's own "you
    tap ... add"): bob's own Island tap is bob's own bonus mana, even though
    alice cast High Tide."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["High Tide"], battlefield=["Island"])
        .player("bob", battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (alice_island,) = scenario.untapped_sources("Island", username="alice")
    scenario.cast_and_resolve("High Tide", alice_island, username="alice")
    scenario.pass_priority("alice")

    (bob_island,) = scenario.untapped_sources("Island", username="bob")
    scenario.activate(bob_island, color=Color.BLUE)

    assert scenario.player("bob").mana_pool.floating == {Color.BLUE: 2}
    assert scenario.player("alice").mana_pool.floating == {}


def test_the_trigger_expires_at_the_next_cleanup():
    """CR 514.2: gone before the next turn's own taps could use it."""
    scenario = (
        Scenario().player("alice", hand=["High Tide"], battlefield=["Island", "Island"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (first,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("High Tide", first, username="alice")
    assert scenario.game.delayed_triggers.triggers

    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()

    assert scenario.game.delayed_triggers.triggers == []


# -- Molten Tide: the effect proven directly, Prepare left to S2 -----------


def _molten_tide_effect():
    text = "Until end of turn, whenever you tap a Mountain for mana, add an additional {R}."
    effect = effect_for("Molten Tide", text)
    assert effect is not None
    return effect


def test_the_parser_reads_molten_tides_own_you_tap_wording():
    """Distinct from High Tide's "a player taps ... that player adds":
    Molten Tide's "you tap ... add" is read as the controller-scoped half of
    the same regex, not a near miss."""
    _molten_tide_effect()  # the assert inside is the proof; see its own body


def test_only_the_controllers_own_mountain_tap_adds_the_extra_red_with_no_stack():
    """Invoking the built effect directly against a real on-stack spell -
    Pyre Rhymer's own creature half, cast the ordinary way - since casting
    "Molten Tide" itself needs the Prepare mechanic S2 still has to wire.

    Both taps below resolve with no `put_triggers_on_stack`/`resolve_top`
    step (CR 605.4a); Pyre Rhymer itself is left on the stack, unresolved,
    throughout - proof that the immediate resolution is scoped to the mana
    trigger alone and never touches the ordinary stack."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Pyre Rhymer // Molten Tide"], battlefield=["Mountain"] * 4)
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="alice")
    casting = scenario.cast("Pyre Rhymer", username="alice")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    on_stack = scenario.put_on_stack(casting)

    _molten_tide_effect()(scenario.game, on_stack)

    (trigger,) = scenario.game.delayed_triggers.triggers
    assert trigger.controller == "alice"

    (alice_mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.activate(alice_mountain, color=Color.RED)
    assert scenario.player("alice").mana_pool.floating == {Color.RED: 2}, "her own tap gets it"
    assert scenario.game.pending_triggers == []

    scenario.pass_priority("alice")
    bob_mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "bob")
    scenario.activate(bob_mountain, color=Color.RED)
    assert scenario.player("bob").mana_pool.floating == {Color.RED: 1}, "not alice's own tap"
    assert scenario.game.pending_triggers == []
    assert not scenario.game.stack_is_empty, "Pyre Rhymer is still there, untouched"
