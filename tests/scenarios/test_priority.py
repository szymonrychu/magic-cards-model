"""Scenario: priority.

The mechanic is CR 117 - who may act, when the non-active player gets a window,
and what a round of passes causes.
"""

import pytest

from magic_cards_model.machines import PriorityOutcome, Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone

from .harness import Scenario


def board() -> Scenario:
    """Alice is active with a creature to cast; Bob holds an instant."""
    return (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
    )


def test_the_active_player_gets_priority_first():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert scenario.priority_holder == "alice"


def test_the_other_player_may_cast_an_instant_in_their_window():
    """The whole point of priority: bob acts on alice's turn."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.pass_priority("alice")
    assert scenario.priority_holder == "bob"

    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bears = None
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])

    assert bolt.zone is Zone.STACK
    assert bears is None
    assert scenario.priority_holder == "bob", "the caster keeps priority"


def test_casting_resets_the_round_of_passes():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")

    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])

    # Bob's own pass is now the first of a fresh round, not the second of the old one.
    assert scenario.pass_priority("bob") is PriorityOutcome.PASSED
    assert scenario.priority_holder == "alice"


def test_everyone_passing_on_a_full_stack_resolves_the_top():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])

    scenario.pass_priority("bob")
    outcome = scenario.pass_priority("alice")

    assert outcome is PriorityOutcome.RESOLVE_TOP
    assert scenario.game.stack_is_empty


def test_everyone_passing_on_an_empty_stack_ends_the_step():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.pass_priority("alice")
    outcome = scenario.pass_priority("bob")

    assert outcome is PriorityOutcome.END_STEP


def test_a_player_without_priority_cannot_pass_it():
    """Corner case: acting out of turn is an error, not a no-op."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    with pytest.raises(ValueError, match="bob does not have priority"):
        scenario.pass_priority("bob")


def test_priority_returns_to_the_active_player_after_something_resolves():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.pass_priority("bob")
    scenario.pass_priority("alice")

    assert scenario.priority_holder == "alice"


def test_an_unknown_player_is_rejected():
    scenario = board().build()

    with pytest.raises(KeyError):
        scenario.pass_priority("carol")


def test_everyone_passing_rolls_the_game_forward_on_its_own():
    """CR 117.4 and 405.5: when all players pass with the stack empty, the
    step or phase ends *and the next begins* - automatically. Nobody has to
    move the game on; passing is "I am done for now"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert scenario.pass_priority("alice") is PriorityOutcome.PASSED
    assert scenario.pass_priority("bob") is PriorityOutcome.END_STEP

    assert scenario.step is Step.BEGINNING_OF_COMBAT
    assert scenario.priority_holder == "alice", (
        "the new step's first priority round starts with the active player"
    )


def test_the_non_active_player_gets_priority_only_in_a_window():
    """The non-active player never holds priority unprompted: only once the
    active player passes (a response window, or the step ending)."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert scenario.priority_holder == "alice"
    with pytest.raises(ValueError, match="bob does not have priority"):
        scenario.pass_priority("bob")

    # Alice casts and keeps priority (CR 117.3c): still no window for bob.
    forests = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_onto_stack("Grizzly Bears", *forests)
    assert scenario.priority_holder == "alice"

    # Alice passes: now the window is bob's, with the Bears on the stack.
    scenario.pass_priority("alice")
    assert scenario.priority_holder == "bob"
    assert scenario.stack_names() == ["Grizzly Bears"]


def prowess_board() -> Scenario:
    """Alice is active; bob holds two prowess creatures and a Bolt (game
    891056b6's deadlock: two "whenever you cast a noncreature spell" triggers,
    both bob's, from a spell bob cast in alice's declare blockers step)."""
    return (
        Scenario()
        .player("alice", library=["Plains"] * 8, battlefield=["Plains"])
        .player(
            "bob",
            library=["Mountain"] * 8,
            hand=["Lightning Bolt"],
            battlefield=["Monastery Swiftspear", "Slickshot Show-Off", "Mountain"],
        )
    )


def test_game_cast_refuses_a_player_without_priority_before_announcing_anything():
    """CR 601.3: "A player can begin to cast a spell only if a rule or effect
    allows that player to cast it" - and CR 117.1a allows it only to the
    player holding priority, so `Game.cast` refuses at the proposal: the Bolt
    never leaves bob's hand (CR 601.2a's move never happens), the Mountain is
    not tapped, and nothing triggers. Refused only once the spell was on the
    stack (`retain_priority`), bob's two prowess triggers (CR 702.108a) were
    first put to him as a CR 603.3b ordering question - game 891056b6's
    deadlock: the api paused the cast on `order_triggers`, every answer
    replayed it into "bob does not have priority, alice does", and neither
    seat could move the game."""
    scenario = prowess_board().build()
    scenario.start_at(Step.DECLARE_BLOCKERS)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")

    with pytest.raises(ValueError, match="bob does not have priority, alice does"):
        scenario.game.cast(bolt, "bob", targets=["alice"], mana_sources=[mountain])

    assert bolt.zone is Zone.HAND
    assert not mountain.tapped
    assert scenario.stack_names() == []
    assert scenario.pending_triggers == []


def test_the_prowess_ordering_goes_to_its_controller_once_they_hold_priority():
    """The legal half of the same board: once alice passes, bob holds
    priority, casts, and is asked to order his own two prowess triggers
    (CR 603.3b), which go on the stack above the Bolt before he gets priority
    back (CR 117.3c)."""
    scenario = prowess_board().build()
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.pass_priority("alice")
    assert scenario.priority_holder == "bob"
    scenario.will_order_triggers("Slickshot Show-Off", "Monastery Swiftspear", username="bob")

    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])

    orders = [q for q in scenario.questions_asked() if q.kind is DecisionKind.ORDER_TRIGGERS]
    assert [q.player for q in orders] == ["bob"]
    assert scenario.stack_names() == [
        "Lightning Bolt",
        "Slickshot Show-Off's triggered ability",
        "Monastery Swiftspear's triggered ability",
    ]
    assert scenario.priority_holder == "bob"


def test_a_player_without_priority_cannot_begin_activating_an_ability():
    """CR 117.1b: "A player may activate an activated ability any time they
    have priority." CR 602.2's announcement is refused before any of its
    costs is chosen or paid - Mishra's Bauble's own "{T}, Sacrifice" is not
    spent - for the same reason a spell is refused at its proposal: nothing
    the activation asks or triggers may be put to anyone ahead of a refusal
    that was always coming."""
    scenario = (
        Scenario()
        .player("alice", library=["Plains"] * 8, battlefield=["Plains"])
        .player("bob", library=["Mountain"] * 8, battlefield=["Mishra's Bauble"])
        .build()
    )
    scenario.start_at(Step.DECLARE_BLOCKERS)
    assert scenario.priority_holder == "alice"
    bauble = scenario.find("Mishra's Bauble", Zone.BATTLEFIELD, "bob")

    with pytest.raises(ValueError, match="bob does not have priority, alice does"):
        scenario.activate(bauble, username="bob", targets=["alice"])

    assert bauble.zone is Zone.BATTLEFIELD
    assert not bauble.tapped
    assert scenario.stack_names() == []
