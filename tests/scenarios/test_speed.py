"""Speed (CR 702.179a-f) and Max speed (CR 702.178a), off Perilous Snare's own
"Start your engines!" and its "Max speed —" activated ability (R0a T8).

Every CR number here was looked up with `mise run rules:find <number>` against
the 2026-09-25 Comprehensive Rules release in the session that wrote this
file.

- **CR 702.179a** - "If a player controls a permanent with start your
  engines! and that player has no speed, their speed becomes 1. This is a
  state-based action."
- **CR 702.179b** - a player has no speed until set.
- **CR 702.179c** - a player with no speed instructed to increase it becomes
  that value outright.
- **CR 702.179d** - the inherent triggered ability: "Whenever one or more
  opponents lose life during your turn, if your speed is less than 4, your
  speed increases by 1. This ability triggers only once each turn."
- **CR 702.179e** - max speed is speed 4.
- **CR 702.178a** - "Max speed — [Ability]" means "As long as your speed is
  4, this object has '[Ability].'"
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.speed import effective_speed, has_max_speed
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario

SNARE = "Perilous Snare"


def test_a_player_has_no_speed_until_a_start_your_engines_permanent_is_controlled():
    """CR 702.179b: no speed at all until CR 702.179a's own condition is met."""
    scenario = Scenario().player("alice").player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")

    assert alice.speed is None
    assert effective_speed(alice) == 0  # CR 702.179f
    scenario.game.check_state_based_actions()
    assert alice.speed is None


def test_start_your_engines_sets_speed_to_one_as_a_state_based_action():
    """CR 702.179a: controlling the permanent sets speed to 1, checked as an
    ordinary state-based action - no explicit call needed beyond whatever
    already checks state-based actions."""
    scenario = Scenario().player("alice", battlefield=[SNARE]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    assert alice.speed is None

    scenario.game.check_state_based_actions()

    assert alice.speed == 1
    assert not has_max_speed(alice)


def test_speed_increases_once_per_turn_when_an_opponent_loses_life():
    """CR 702.179d: the drain-watching inherent ability, and its own "only
    once each turn" cap - a second loss the same turn does not increase it
    twice."""
    scenario = Scenario().player("alice", battlefield=[SNARE]).player("bob", life=20).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.check_state_based_actions()
    alice = scenario.player("alice")
    assert alice.speed == 1

    scenario.game.lose_life("bob", 3)
    assert alice.speed == 2
    assert alice.speed_increased_on_turn == scenario.turn.turns_taken

    scenario.game.lose_life("bob", 2)
    assert alice.speed == 2  # unchanged: already triggered this turn


def test_speed_does_not_increase_when_the_watching_player_loses_their_own_life():
    """CR 702.179d's own "opponents" - the watching player's own life loss
    does not count."""
    scenario = Scenario().player("alice", battlefield=[SNARE], life=20).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.check_state_based_actions()
    alice = scenario.player("alice")
    assert alice.speed == 1

    scenario.game.lose_life("alice", 3)

    assert alice.speed == 1


def test_speed_caps_at_four_and_stops_increasing():
    """CR 702.179d's own "if your speed is less than 4" guard - max speed
    does not overshoot."""
    scenario = Scenario().player("alice", battlefield=[SNARE]).player("bob", life=20).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    alice.speed = 4

    scenario.game.lose_life("bob", 1)

    assert alice.speed == 4
    assert has_max_speed(alice)


def test_max_speed_ability_cannot_be_activated_below_max_speed():
    """CR 702.178a: the whole ability is unavailable until speed 4 - refused
    the same way any other activation-timing rule refuses, before any cost
    is paid."""
    scenario = (
        Scenario().player("alice", battlefield=[SNARE, "Grizzly Bears"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    snare = scenario.find(SNARE, Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    alice = scenario.player("alice")
    alice.speed = 1

    refusal = scenario.why_cannot_activate(snare, 0)
    assert refusal is not None and "speed" in refusal

    alice.speed = 4
    scenario.activate(snare, targets=[bears])
    scenario.resolve_top()
    assert bears.counter_count("+1/+1") == 1


def test_endrider_catalyzer_proves_max_speed_generalises_to_a_mana_ability():
    """Proof of generality: Endrider Catalyzer (legal Modern/Pioneer, not in
    `code/magic-cards-model-api/decks/*.txt`) carries "Max speed — {T}: Add
    {R}{R}." - a mana ability, not Perilous Snare's own counter-placement
    one, gated by the identical `ability_word` check."""
    scenario = Scenario().player("alice", battlefield=["Endrider Catalyzer"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    catalyzer = scenario.find("Endrider Catalyzer", Zone.BATTLEFIELD, "alice")
    alice = scenario.player("alice")

    refusal = scenario.why_cannot_activate(catalyzer, 0)
    assert refusal is not None and "speed" in refusal

    alice.speed = 4
    scenario.activate(catalyzer, index=0)

    assert alice.mana_pool.floating.get(Color.RED) == 2


def test_max_speed_ability_stops_working_the_moment_speed_drops_back():
    """CR 611.3a: a static ability's effect "isn't locked in" - read fresh
    each time, not cached from the moment speed last reached 4."""
    scenario = (
        Scenario().player("alice", battlefield=[SNARE, "Grizzly Bears"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    snare = scenario.find(SNARE, Zone.BATTLEFIELD, "alice")
    alice = scenario.player("alice")
    alice.speed = 4
    assert scenario.why_cannot_activate(snare, 0) is None

    alice.speed = 3

    refusal = scenario.why_cannot_activate(snare, 0)
    assert refusal is not None and "speed" in refusal
