"""Scenario: "You may activate loyalty abilities of <self> on any player's turn
any time you could cast an instant." (Teferi, Master of Time).

CR 606.3, read whole with `mise run rules:find 606.3` this session: "A player
may activate a loyalty ability of a permanent they control any time they have
priority and the stack is empty during a main phase of their turn, but only if
no player has previously activated a loyalty ability of that permanent that
turn."

Teferi's static loosens only the timing half - "any time you could cast an
instant" is CR 117.1a's any-time-with-priority - never the once-per-turn half,
which is counted per turn, so he activates once on each player's turn.
`tests/scenarios/test_loyalty_instant_speed_permission.py` owns the resolved
grant (Jace's Machinations) and the refusal of a second planeswalker; this
file is the static's corner cases.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models.action import ActionKind

from .harness import Scenario

TEFERI = "Teferi, Master of Time"


def _board(**bob) -> Scenario:
    return (
        Scenario()
        .player("alice", library=["Island"] * 8, battlefield=[TEFERI, "Mountain"])
        .player("bob", library=["Forest"] * 8, **bob)
    )


def _to_bobs(scenario, step: Step) -> None:
    scenario.advance()
    while scenario.turn.active_player != "bob" or scenario.step is not step:
        scenario.advance()


def _teferi_activations(scenario) -> list:
    teferi = scenario.creature(TEFERI, "alice")
    return [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.kind is ActionKind.ACTIVATE and action.card_id == teferi.id
    ]


def test_teferi_activates_in_bobs_upkeep():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _to_bobs(scenario, Step.UPKEEP)
    teferi = scenario.creature(TEFERI, "alice")
    scenario.pass_priority("bob")

    assert scenario.why_cannot_activate(teferi, 0, "alice") is None
    scenario.activate(teferi, index=0, username="alice")
    scenario.resolve_top()

    assert teferi.loyalty == 4


def test_teferi_activates_with_a_spell_on_the_stack():
    """Instant timing: the stack need not be empty (CR 606.3's "stack is
    empty" is the half the static replaces)."""
    scenario = _board(hand=["Giant Growth"], battlefield=["Grizzly Bears", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _to_bobs(scenario, Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    (forest,) = scenario.untapped_sources("Forest", username="bob")
    scenario.cast_onto_stack("Giant Growth", forest, username="bob", targets=[bears])
    scenario.pass_priority("bob")
    teferi = scenario.creature(TEFERI, "alice")

    scenario.activate(teferi, index=1, username="alice", targets=[bears])
    scenario.resolve_top()  # Teferi's -3 resolves first, over Giant Growth

    assert bears.phased_out
    scenario.resolve_top()  # Giant Growth: its only target is gone (CR 608.2b)
    assert bears.phased_out


def test_teferi_activates_only_once_on_bobs_turn():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _to_bobs(scenario, Step.UPKEEP)
    teferi = scenario.creature(TEFERI, "alice")
    scenario.pass_priority("bob")
    scenario.activate(teferi, index=0, username="alice")
    scenario.resolve_top()

    reason = scenario.why_cannot_activate(teferi, 0, "alice")
    assert reason is not None
    assert "CR 606.3" in reason
    assert _teferi_activations(scenario) == []


def test_teferi_activates_on_his_own_turn_and_again_on_bobs():
    """Once per *turn*: an activation on alice's turn leaves bob's turn free."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    teferi = scenario.creature(TEFERI, "alice")
    scenario.activate(teferi, index=0, username="alice")
    scenario.resolve_top()
    assert scenario.why_cannot_activate(teferi, 0, "alice") is not None

    _to_bobs(scenario, Step.END_STEP)
    scenario.pass_priority("bob")
    assert scenario.why_cannot_activate(teferi, 0, "alice") is None
    scenario.activate(teferi, index=0, username="alice")
    scenario.resolve_top()

    assert teferi.loyalty == 5


def test_teferi_activates_outside_a_main_phase_of_his_own_turn():
    """The static reaches his controller's own turn too: "on any player's
    turn" includes alice's, and "any time you could cast an instant" includes
    her upkeep."""
    scenario = _board().build()
    scenario.start_at(Step.UPKEEP)
    teferi = scenario.creature(TEFERI, "alice")

    assert scenario.why_cannot_activate(teferi, 0, "alice") is None


def test_legal_actions_offer_teferi_on_bobs_turn():
    """The action surface agrees with the refusal check: while alice holds
    priority on bob's turn, every one of Teferi's loyalty abilities he has the
    loyalty for is on offer."""
    scenario = _board(battlefield=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _to_bobs(scenario, Step.UPKEEP)
    scenario.pass_priority("bob")

    offered = _teferi_activations(scenario)

    assert {action.ability_index for action in offered} == {0, 1}
