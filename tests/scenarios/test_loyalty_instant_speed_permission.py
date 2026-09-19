""" "[Until end of turn, ]you may activate loyalty abilities of `<subject>` on
any player's turn any time you could cast an instant." - CR 606.3's ordinary
sorcery-speed timing, loosened.

Two shapes on this branch, both read by `Game._loyalty_instant_speed_
permitted` inside `why_cannot_activate`'s own CR 606.3 timing check, ahead of
the ordinary `can_cast_sorcery` refusal:

- **A resolved grant**, recorded as a `LoyaltyInstantSpeedPermission`
  (`models/game.py`) by `machines/effects._parse_loyalty_instant_speed_
  clause` - Jace's Machinations' own "Until end of turn, ... Jace
  planeswalkers you control ...", subtype-scoped and bounded
  (`until_end_of_turn=True`, dropped by `Game.cleanup_step` the moment it
  actually runs - not by the turn pointer merely moving, since `start_at`
  never performs turn-based actions on its own).
- **A permanent static ability**, read straight off a battlefield permanent's
  own printed text by `_LOYALTY_INSTANT_SPEED_STATIC_RE` with no resolution
  record at all - Teferi, Master of Time's own self-reference ("... of
  Teferi ...", CR 201.5's own planeswalker self-reference by name).

CR numbers looked up with `knowledge_search(type="rules")` in this session:
CR 606.3, CR 604.2, CR 201.5, CR 514.2.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _jace_machinations_board() -> Scenario:
    """`manual_turn_based_actions()`: `advance()`'s CR 703.3 turn-based
    actions are on by default, and cleanup (CR 514.2) is one of them - a
    scenario that wants to see the "until end of turn" grant still active on
    a later turn has to drive the turn forward without letting an automatic
    cleanup drop it first. `test_the_permission_is_dropped_at_the_next_
    cleanup_step` below exercises that same cleanup deliberately instead."""
    return (
        Scenario()
        .player(
            "alice",
            hand=["Jace's Machinations"],
            library=["Forest"],
            battlefield=["Island", "Island", "Island"],
        )
        .player("bob")
        .manual_turn_based_actions()
    )


# -- without the permission, CR 606.3's ordinary timing holds ---------------


def test_without_the_permission_a_loyalty_ability_is_refused_on_the_opponents_turn():
    scenario = (
        Scenario().player("alice", battlefield=["Ugin, Eye of the Storms"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ugin = scenario.creature("Ugin, Eye of the Storms", "alice")

    while scenario.turn.active_player != "bob":
        scenario.advance()

    reason = scenario.why_cannot_activate(ugin)
    assert reason is not None
    assert "CR 606.3" in reason


# -- Jace's Machinations' resolved, subtype-scoped, bounded grant -----------


def test_jaces_machinations_permits_activation_on_the_opponents_turn():
    scenario = _jace_machinations_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Island", "Island", "Island")
    scenario.cast_and_resolve("Jace's Machinations", *sources)

    jace = scenario.find("Jace", Zone.BATTLEFIELD, "alice")
    assert jace.loyalty == 8

    while scenario.turn.active_player != "bob":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)  # bob's own main phase - still not alice's turn

    assert scenario.why_cannot_activate(jace) is None, "the grant loosens CR 606.3's timing"

    scenario.pass_priority("bob")  # alice needs priority in hand to act at all
    hand_before = len(scenario.player("alice").hand)
    scenario.activate(jace, index=1)  # "-3: Draw a card."
    while scenario.game.stack:
        scenario.resolve_top()

    assert jace.loyalty == 5
    assert len(scenario.player("alice").hand) == hand_before + 1


def test_a_different_planeswalker_is_still_refused_despite_jaces_machinations():
    """The grant is scoped to "Jace planeswalkers you control" - Ugin shares
    neither the subtype nor the id, so the plain CR 606.3 refusal still
    applies to him even while the Jace grant is active."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Jace's Machinations"],
            battlefield=["Island", "Island", "Island", "Ugin, Eye of the Storms"],
        )
        .player("bob")
        .manual_turn_based_actions()  # see `_jace_machinations_board`
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ugin = scenario.creature("Ugin, Eye of the Storms", "alice")

    sources = scenario.untapped_sources("Island", "Island", "Island")
    scenario.cast_and_resolve("Jace's Machinations", *sources)

    while scenario.turn.active_player != "bob":
        scenario.advance()

    reason = scenario.why_cannot_activate(ugin)
    assert reason is not None
    assert "CR 606.3" in reason


def test_the_permission_is_dropped_at_the_next_cleanup_step():
    """`until_end_of_turn=True` is dropped by `Game.cleanup_step` itself
    (CR 514.2), not by the turn pointer merely advancing - `start_at` never
    runs turn-based actions on its own, so this drives cleanup by hand
    (`Scenario.turn_based_actions`) to actually exercise CR 514.2 before
    checking the grant is gone."""
    scenario = _jace_machinations_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Island", "Island", "Island")
    scenario.cast_and_resolve("Jace's Machinations", *sources)
    assert scenario.game.loyalty_instant_speed_permissions != []

    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()

    assert scenario.game.loyalty_instant_speed_permissions == []

    while scenario.turn.active_player != "bob":
        scenario.advance()

    jace = scenario.find("Jace", Zone.BATTLEFIELD, "alice")
    reason = scenario.why_cannot_activate(jace)
    assert reason is not None
    assert "CR 606.3" in reason


# -- Teferi, Master of Time's own permanent, self-referential static --------


def test_teferis_own_static_permits_activating_his_own_ability_on_the_opponents_turn():
    scenario = (
        Scenario().player("alice", battlefield=["Teferi, Master of Time"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    teferi = scenario.creature("Teferi, Master of Time", "alice")
    assert teferi.loyalty == 3

    while scenario.turn.active_player != "bob":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)  # bob's own main phase - still not alice's turn

    assert scenario.why_cannot_activate(teferi) is None

    scenario.pass_priority("bob")  # alice needs priority in hand to act at all
    scenario.activate(teferi, index=0)  # "+1: Draw a card, then discard a card."
    while scenario.game.stack:
        scenario.resolve_top()

    assert teferi.loyalty == 4


def test_a_different_planeswalker_is_refused_despite_teferis_own_static():
    """Teferi's own text names only himself ("... of Teferi ...", CR 201.5) -
    not "planeswalkers you control" - so a second planeswalker alice controls
    gets no loosening from it at all."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Teferi, Master of Time", "Ugin, Eye of the Storms"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ugin = scenario.creature("Ugin, Eye of the Storms", "alice")

    while scenario.turn.active_player != "bob":
        scenario.advance()

    reason = scenario.why_cannot_activate(ugin)
    assert reason is not None
    assert "CR 606.3" in reason
