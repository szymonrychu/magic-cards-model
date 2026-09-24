"""A self-referential, conditional loyalty-timing permission: "As long as
<this> entered this turn, you may activate her loyalty abilities any time you
could cast an instant." (The Wandering Emperor).

Rules, looked up with `mise run rules:find`:

- **CR 606.3** - "A player may activate a loyalty ability of a permanent they
  control any time they have priority and the stack is empty during a main
  phase of their turn, but only if no player has previously activated a
  loyalty ability of that permanent that turn."
- **CR 604.2** - a static ability's effect is active while its permanent is on
  the battlefield and has the ability; the "as long as" condition is read on
  every call rather than locked in (CR 611.3a).

The permission loosens only CR 606.3's timing half. Its once-per-turn half
stays: The Wandering Emperor flashed in on an opponent's turn activates once
there, not twice. On a later turn the condition is false and the ordinary
sorcery-speed timing is back.

The same reader carries Teferi, Master of Time's unconditional "You may
activate loyalty abilities of Teferi on any player's turn any time you could
cast an instant." - the proof printing for the widened reader (no other
Modern/Pioneer/Standard printing carries the conditional form; recorded in
MEMORY.md).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models.action import ActionKind
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import PlayedScenario, Scenario

EMPEROR = "The Wandering Emperor"
TEFERI = "Teferi, Master of Time"
PLUS_ONE, MINUS_ONE, MINUS_TWO = 0, 1, 2


def board(*, alice_battlefield: list[str] | None = None, alice_hand: list[str] | None = None):
    return (
        Scenario()
        .player(
            "alice",
            library=["Plains"] * 8,
            hand=alice_hand if alice_hand is not None else [EMPEROR],
            battlefield=alice_battlefield or ["Plains"] * 4,
        )
        .player(
            "bob",
            library=["Forest"] * 8,
            hand=["Giant Growth"],
            battlefield=["Grizzly Bears", "Forest"],
        )
        .build()
    )


def to_bobs(scenario: PlayedScenario, step: Step) -> None:
    scenario.advance()
    while scenario.turn.active_player != "bob" or scenario.step is not step:
        scenario.advance()


def flash_in_emperor(scenario: PlayedScenario, *, hand_back: bool = True):
    """Alice flashes the Emperor in while holding priority on bob's turn; once
    it resolves bob, the active player, receives priority (CR 117.3b) and
    passes it back to her."""
    plains = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains", username="alice")
    emperor = scenario.cast_and_resolve(EMPEROR, *plains, username="alice")
    if hand_back and scenario.priority_holder == "bob":
        scenario.pass_priority("bob")
    return emperor


def emperor_actions(scenario: PlayedScenario, emperor) -> set[int | None]:
    return {
        action.ability_index
        for action in legal_actions(scenario.game, "alice")
        if action.kind is ActionKind.ACTIVATE and action.card_id == emperor.id
    }


def test_flashed_in_on_bobs_turn_she_activates_right_away():
    scenario = board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    to_bobs(scenario, Step.UPKEEP)
    scenario.pass_priority("bob")
    emperor = flash_in_emperor(scenario)

    assert scenario.why_cannot_activate(emperor, MINUS_ONE, "alice") is None
    scenario.activate(emperor, index=MINUS_ONE, username="alice")
    scenario.resolve_top()

    assert emperor.loyalty == 2, "printed 3, minus 1"
    assert any("Samurai" in state.subtypes for state in scenario.game.battlefield)


def test_legal_actions_offer_her_abilities_on_bobs_turn():
    scenario = board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    to_bobs(scenario, Step.UPKEEP)
    scenario.pass_priority("bob")
    emperor = flash_in_emperor(scenario)

    assert emperor_actions(scenario, emperor) == {PLUS_ONE, MINUS_ONE, MINUS_TWO}


def test_she_activates_with_a_spell_on_the_stack():
    """Instant timing replaces CR 606.3's "stack is empty": bob's Giant Growth
    is on the stack and she answers it by exiling the tapped Bears."""
    scenario = board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    to_bobs(scenario, Step.UPKEEP)
    scenario.pass_priority("bob")
    emperor = flash_in_emperor(scenario, hand_back=False)
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.tapped = True
    (forest,) = scenario.untapped_sources("Forest", username="bob")
    scenario.cast_onto_stack("Giant Growth", forest, username="bob", targets=[bears])
    scenario.pass_priority("bob")

    assert scenario.why_cannot_activate(emperor, MINUS_TWO, "alice") is None
    scenario.activate(emperor, index=MINUS_TWO, username="alice", targets=[bears])
    scenario.resolve_top()

    assert bears.zone.value == "exile"
    assert scenario.player("alice").life == 22


def test_the_once_per_turn_half_still_holds():
    scenario = board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    to_bobs(scenario, Step.UPKEEP)
    scenario.pass_priority("bob")
    emperor = flash_in_emperor(scenario)
    scenario.activate(emperor, index=PLUS_ONE, username="alice", targets=[])
    scenario.resolve_top()

    refusal = scenario.why_cannot_activate(emperor, MINUS_ONE, "alice")
    assert refusal is not None and "already been activated this turn" in refusal
    assert emperor_actions(scenario, emperor) == set()


def test_on_a_later_turn_the_condition_is_false():
    """She entered on bob's turn; on bob's *next* turn she did not enter that
    turn, so a loyalty ability on his turn is refused with CR 606.3's reason."""
    scenario = board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    to_bobs(scenario, Step.UPKEEP)
    scenario.pass_priority("bob")
    emperor = flash_in_emperor(scenario)
    to_bobs(scenario, Step.END_STEP)
    to_bobs(scenario, Step.UPKEEP)
    scenario.pass_priority("bob")

    refusal = scenario.why_cannot_activate(emperor, PLUS_ONE, "alice")
    assert refusal == (
        "The Wandering Emperor's loyalty ability can only be activated during "
        "alice's main phase, with the stack empty (CR 606.3)"
    )
    assert emperor_actions(scenario, emperor) == set()


def test_already_on_the_battlefield_she_is_sorcery_speed():
    """Put there before the game's first main phase, she did not enter this
    turn: in alice's upkeep she may not activate."""
    scenario = board(alice_battlefield=[EMPEROR], alice_hand=[])
    scenario.start_at(Step.UPKEEP)
    emperor = scenario.creature(EMPEROR, "alice")
    emperor.turn_entered = None

    assert scenario.why_cannot_activate(emperor, PLUS_ONE, "alice") is not None


def test_the_permission_does_not_reach_another_planeswalker():
    """ "her loyalty abilities" - only the Emperor's own."""
    scenario = board(alice_battlefield=["Plains"] * 4 + ["Liliana of the Veil"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    to_bobs(scenario, Step.UPKEEP)
    scenario.pass_priority("bob")
    flash_in_emperor(scenario)
    liliana = scenario.creature("Liliana of the Veil", "alice")

    assert scenario.why_cannot_activate(liliana, 0, "alice") is not None


def test_teferi_proof_printing_still_reads_through_the_same_reader():
    scenario = (
        Scenario()
        .player("alice", library=["Island"] * 8, battlefield=[TEFERI])
        .player("bob", library=["Forest"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    to_bobs(scenario, Step.UPKEEP)
    scenario.pass_priority("bob")

    assert scenario.why_cannot_activate(scenario.creature(TEFERI, "alice"), 0, "alice") is None


def test_every_clause_is_handled():
    for name in (EMPEROR, TEFERI):
        for clause in card_support(card(name)).clauses:
            assert clause.outcome == "handled", (name, clause.text, clause.outcome)
