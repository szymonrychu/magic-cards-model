"""Leaves-the-battlefield triggers, across every route off the battlefield.

Adjudicated in `docs/2026-09-08-trigger-findings.md` ("A third defect, found
while listing the traps"): a printed "when this leaves the battlefield"
ability fired for a graveyard departure but not for exile, hand, or any other
destination. Measured with Thought-Knot Seer ("When this creature leaves the
battlefield, target opponent draws a card.").

Root cause, verified in this session rather than trusted from the summary:
`Game.emit` (`models/game.py`) synchronously calls `triggers_for`
(`machines/triggers.py`), which gates every candidate on
`source.zone in zones_ability_functions_in(ability, source)`. For an ordinary
ability that answers is just `{Zone.BATTLEFIELD}` - CR 113.6's default. A
**look-back** event (`_LOOK_BACK_EVENTS`) instead answers
`{Zone.BATTLEFIELD, source.zone}`, so the check passes regardless of whether
`source.zone` still reads BATTLEFIELD (the event was emitted before the move)
or already reads wherever the card actually went (emitted after).

`Game.put_into_graveyard` emits `LEAVES_THE_BATTLEFIELD` *before* moving the
card, so the departure "accidentally" passed the plain-battlefield default -
`source.zone` was still BATTLEFIELD at the moment `triggers_for` ran.
`Game.exile_permanent`/`_exile_move`, `Game.return_to_hand`,
`Game.put_cards_into_library`, and `Game.ante` all emit it *after* the move,
so `source.zone` was already EXILE/HAND/LIBRARY/ANTE and the plain-battlefield
default refused every one of them. `_LOOK_BACK_EVENTS`
(`machines/triggers.py`) is `(DIES, IS_SACRIFICED, SPELL_IS_COUNTERED)` and
does not include `LEAVES_THE_BATTLEFIELD` - CR 603.10a says it should.

Two existing tests looked like coverage and are not:
`test_trigger_events.py::test_leaving_the_battlefield_to_{exile,hand}_fires_
the_generic_departure_event` prove only that `Game.emit` raises the event with
the right subject - the watcher they use is a `DelayedTrigger`
(`Game.create_delayed_trigger`), a completely different mechanism from a
printed ability's `condition_matches`/`zones_ability_functions_in` path, and
delayed triggers are never zone-gated at all. `test_dies_trigger_scope.py::
test_a_leaves_the_battlefield_condition_fires_on_death_too` exercises the one
real printed ability in the pool (Thought-Knot Seer) but only through
`destroy` - the graveyard route, the one that already worked. No test
anywhere sent a *printed* leaves-the-battlefield ability through exile, hand,
or any other destination before this file.

CR numbers, looked up this session with `mise run rules:find <number>`
(`knowledge_search` was unavailable in this worktree - no spellslinger MCP
server is configured for it):

- **CR 603.6c** - "Leaves-the-battlefield abilities trigger when a permanent
  moves from the battlefield to another zone" - no destination named, so
  every one of graveyard/exile/hand/library/ante counts.
- **CR 603.10** / **603.10a** - "the game 'looks back in time' ... Some
  zone-change triggers look back in time. These are leaves-the-battlefield
  abilities, abilities that trigger when a player sacrifices a permanent,
  abilities that trigger when a card leaves a graveyard, and abilities that
  trigger when an object that all players can see is put into a hand or
  library." Leaves-the-battlefield is named as its own case, independent of
  `DIES`/`IS_SACRIFICED`/`SPELL_IS_COUNTERED`.
- **CR 111.7** - a token that changes zones still fires "applicable triggered
  abilities" before it ceases to exist (used by `test_tokens.py` already;
  re-verified here for the token-copy test below).
- **CR 111.8** - "A token that has left the battlefield can't move to another
  zone or come back onto the battlefield." A second departure attempt must
  not raise a second trigger.
- **CR 603.6** - "An ability that attempts to do something to the card that
  left the battlefield checks for it only in the first zone that it went to"
  - not load-bearing for this file (Thought-Knot Seer's effect never looks at
  itself), noted because it is the same rule number as 603.6c and worth not
  conflating.

Every departure route this engine can raise a permanent through is exercised:
`put_into_graveyard` (direct, and through `destroy`/`sacrifice`),
`exile_permanent`, `return_to_hand`, `put_cards_into_library` (the tuck
route), and `ante`. Control changing (a continuous layer effect,
`machines/layers.py` - never a zone-change function) and phasing (CR 603.10b's
own, separate look-back category, never a zone-change function either) are
covered negatively: neither goes through `put_into_graveyard`/`exile_
permanent`/`return_to_hand`/`put_cards_into_library`/`ante` in this engine at
all, so there is no code path by which either could raise
`LEAVES_THE_BATTLEFIELD` - Threaten's control-change is exercised directly to
confirm that in practice, not just by reading the source.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.models.token import TokenDefinition, create_tokens
from tests.scenarios.harness import Scenario


def _board(battlefield: list[str] | None = None, **alice_kwargs) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=battlefield if battlefield is not None else ["Thought-Knot Seer"],
            **alice_kwargs,
        )
        .player("bob", library=["Island", "Island", "Island"])
    )


def _seer_and_target(scenario: Scenario) -> None:
    """Declare Thought-Knot Seer's "target opponent" as bob before the
    departure that triggers it - `choose_trigger_targets` is read when the
    ability actually goes on the stack, the same pattern
    `test_dies_trigger_scope.py` already uses for this exact card."""
    scenario.choose_trigger_targets("Thought-Knot Seer", ["bob"])


def _fire_and_resolve(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()


# -- the graveyard route: already worked, kept as a regression guard --------


def test_graveyard_departure_via_destroy_fires_and_resolves():
    """CR 701.8a's destroy - the route that already worked, by accident of
    `put_into_graveyard` emitting before the move rather than by
    `_LOOK_BACK_EVENTS` actually naming this event. Kept so the fix cannot
    silently regress the one route that was fine."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    seer = scenario.creature("Thought-Knot Seer", "alice")
    bob_library_before = len(scenario.player("bob").library)
    _seer_and_target(scenario)

    scenario.game.destroy(seer)

    assert len(scenario.pending_triggers) == 1
    _fire_and_resolve(scenario)
    assert seer.zone is Zone.GRAVEYARD
    assert len(scenario.player("bob").library) == bob_library_before - 1


def test_graveyard_departure_via_direct_move_fires_and_resolves():
    """`Game.put_into_graveyard` called directly, with no destroy/sacrifice
    wrapper in between."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    seer = scenario.creature("Thought-Knot Seer", "alice")
    bob_library_before = len(scenario.player("bob").library)
    _seer_and_target(scenario)

    scenario.game.put_into_graveyard(seer)

    assert len(scenario.pending_triggers) == 1
    _fire_and_resolve(scenario)
    assert seer.zone is Zone.GRAVEYARD
    assert len(scenario.player("bob").library) == bob_library_before - 1


def test_graveyard_departure_via_sacrifice_fires_and_resolves():
    """CR 701.21a's sacrifice - a second way to reach the same `DIES`-plus-
    `LEAVES_THE_BATTLEFIELD` pair `destroy` reaches, not a fourth event."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    seer = scenario.creature("Thought-Knot Seer", "alice")
    bob_library_before = len(scenario.player("bob").library)
    _seer_and_target(scenario)

    scenario.game.sacrifice(seer)

    assert len(scenario.pending_triggers) == 1
    _fire_and_resolve(scenario)
    assert seer.zone is Zone.GRAVEYARD
    assert len(scenario.player("bob").library) == bob_library_before - 1


# -- the three routes measured broken, plus the two the adjudicator didn't --


def test_exile_departure_fires_and_resolves():
    """CR 701.13a's exile. Measured broken: `Game.exile_permanent` emits
    `LEAVES_THE_BATTLEFIELD` after the move, so `source.zone` already read
    EXILE by the time `zones_ability_functions_in`'s plain-battlefield
    default was checked."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    seer = scenario.creature("Thought-Knot Seer", "alice")
    bob_library_before = len(scenario.player("bob").library)
    _seer_and_target(scenario)

    scenario.game.exile_permanent(seer)

    assert len(scenario.pending_triggers) == 1
    _fire_and_resolve(scenario)
    assert seer.zone is Zone.EXILE
    assert len(scenario.player("bob").library) == bob_library_before - 1


def test_hand_departure_fires_and_resolves():
    """CR 701.19a's return. Measured broken, the same way as exile:
    `Game.return_to_hand` emits after the move."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    seer = scenario.creature("Thought-Knot Seer", "alice")
    bob_library_before = len(scenario.player("bob").library)
    _seer_and_target(scenario)

    scenario.game.return_to_hand(seer)

    assert len(scenario.pending_triggers) == 1
    _fire_and_resolve(scenario)
    assert seer.zone is Zone.HAND
    assert len(scenario.player("bob").library) == bob_library_before - 1


def test_library_tuck_departure_fires_and_resolves():
    """CR 401's tuck. Not measured by the adjudicator, but the same emit-
    after-the-move shape as exile and hand: `Game.put_cards_into_library`
    moves every card in the batch first, then emits `LEAVES_THE_BATTLEFIELD`
    once per departure in a second pass."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    seer = scenario.creature("Thought-Knot Seer", "alice")
    bob_library_before = len(scenario.player("bob").library)
    _seer_and_target(scenario)

    scenario.game.put_cards_into_library([seer])

    assert len(scenario.pending_triggers) == 1
    _fire_and_resolve(scenario)
    assert seer.zone is Zone.LIBRARY
    # The seer is tucked into its *owner's* (alice's) library, CR 401.1 - only
    # bob's own draw off the trigger touches bob's library.
    assert len(scenario.player("bob").library) == bob_library_before - 1


def test_ante_departure_fires_and_resolves():
    """CR 407.4's ante - the fifth and last zone-change function in this
    engine that can move a permanent off the battlefield. Not measured by the
    adjudicator and not watched by anything in the card pool (per `Game.
    ante`'s own docstring), but it shares the same emit-after-the-move shape
    and the same `zones_ability_functions_in` gate, so it was equally broken
    and is equally fixed by the same change."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    seer = scenario.creature("Thought-Knot Seer", "alice")
    bob_library_before = len(scenario.player("bob").library)
    _seer_and_target(scenario)

    moved = scenario.game.ante(seer)

    assert moved
    assert len(scenario.pending_triggers) == 1
    _fire_and_resolve(scenario)
    assert seer.zone is Zone.ANTE
    assert len(scenario.player("bob").library) == bob_library_before - 1


# -- the traps: over-correction guards ---------------------------------------


def test_another_permanent_leaving_by_exile_does_not_trigger_the_seer():
    """The self-referential form only ("this pool" per `condition_matches`'s
    own `LEAVES_THE_BATTLEFIELD` branch) - widening the zone gate to fix
    exile/hand/library/ante must not turn some *other* permanent's departure
    by one of those routes into a Thought-Knot Seer trigger too."""
    scenario = _board(battlefield=["Thought-Knot Seer", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.exile_permanent(bears)

    assert scenario.pending_triggers == []


def test_a_permanent_that_leaves_twice_fires_twice():
    """Two genuinely separate departures must fire the ability twice, once
    per event - not zero (the defect) and not more than twice.

    Gollum, Patient Plotter ("When Gollum leaves the battlefield, the Ring
    tempts you.") rather than Thought-Knot Seer here on purpose: Thought-Knot
    Seer also has an enters-the-battlefield ability, which would fire when it
    is put back onto the battlefield between the two departures and make a
    passing `pending_triggers` count ambiguous about *which* ability fired.
    Gollum has no enters trigger at all, so any pending trigger in this test
    can only be the leaves-the-battlefield one.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Gollum, Patient Plotter"])
        .player("bob", library=["Island", "Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gollum = scenario.creature("Gollum, Patient Plotter", "alice")

    scenario.game.exile_permanent(gollum)
    assert len(scenario.pending_triggers) == 1
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert scenario.pending_triggers == []

    scenario.game.put_onto_battlefield(gollum, "alice")
    assert scenario.pending_triggers == []  # entering is not leaving, and Gollum has no ETB

    scenario.game.return_to_hand(gollum)
    assert len(scenario.pending_triggers) == 1
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert gollum.zone is Zone.HAND
    assert scenario.pending_triggers == []


def test_a_token_that_already_left_cannot_fire_its_leaves_trigger_a_second_time():
    """CR 111.7 (the first departure fires) and CR 111.8 (a second one
    cannot happen at all, so it cannot fire a second trigger either) together.
    A hand-written `TokenDefinition` is the sanctioned way to give a test
    token a printed ability (`docs/2026-09-08-trigger-findings.md`'s own note
    on the trap - not hand-written *card* data, which stays banned; a token
    has no printing to begin with, CR 111.3), mirroring the self-referential
    shape `condition_matches`'s `LEAVES_THE_BATTLEFIELD` branch reads."""
    scenario = Scenario().player("alice").player("bob", library=["Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    watcher_definition = TokenDefinition(
        subtypes=("Spirit",),
        colors=(Color.WHITE,),
        power=1,
        toughness=1,
        rules_text="When this creature leaves the battlefield, target opponent draws a card.",
    )
    (token,) = create_tokens(scenario.game, watcher_definition, "alice")
    scenario.choose_trigger_targets(token.name, ["bob"])

    scenario.game.destroy(token)
    assert len(scenario.pending_triggers) == 1
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert scenario.pending_triggers == []
    assert token.zone is Zone.GRAVEYARD
    assert token.left_the_battlefield

    # CR 111.8: a second attempt to move the same token is refused outright,
    # so nothing is emitted and nothing triggers a second time.
    scenario.game.exile_permanent(token)

    assert token.zone is Zone.GRAVEYARD  # unmoved - CR 111.8 refused it
    assert scenario.pending_triggers == []


def test_gaining_control_does_not_fire_a_leaves_trigger():
    """Control changing is CR 603.10d's *own* look-back category, distinct
    from CR 603.10a's leaves-the-battlefield - and, in this engine, not a
    zone change at all: `machines/layers.py` reapplies a continuous
    "gain control" modification without the permanent ever passing through
    `put_into_graveyard`/`exile_permanent`/`return_to_hand`/`put_cards_into_
    library`/`ante`. Threaten targeting an opponent's own Thought-Knot Seer
    proves that in practice, not just by reading the source: stealing it must
    not fire its own leaves-the-battlefield ability."""
    scenario = (
        Scenario()
        .player("alice", hand=["Threaten"], battlefield=["Mountain"] * 3)
        .player("bob", battlefield=["Thought-Knot Seer"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    seer = scenario.creature("Thought-Knot Seer", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="alice")
    scenario.choose_trigger_targets("Thought-Knot Seer", ["alice"])

    scenario.cast_and_resolve("Threaten", *sources, targets=[seer])

    assert scenario.game.controller_of(seer).username == "alice"
    assert seer.zone is Zone.BATTLEFIELD
    assert scenario.pending_triggers == []
