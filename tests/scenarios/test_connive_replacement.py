"""The connive replacement: "If a creature you control would connive, instead
you draw a card, then that creature connives." (Leader, Super-Genius)

Every CR number below was read in full with `mise run rules:find` in the
session that wrote this file:

- **CR 614.1a** - an effect that uses "instead" is a replacement effect.
- **CR 614.5** - "A replacement effect doesn't invoke itself repeatedly; it
  gets only one opportunity to affect an event" - the replacement's own
  "then that creature connives" is not replaced a second time, so one Leader
  adds exactly one card, however the event is modified.
- **CR 701.50a** - the connive the replacement leaves in place: its
  controller draws, then discards, and a nonland discard is a +1/+1 counter.
- **CR 701.50b** - a conniver that has left the battlefield is judged by its
  last known information: it was still "a creature you control".
- **CR 613.1f** - layer 6: a Leader whose abilities an effect removed has no
  replacement left to apply.

The replacement is read off the battlefield on every connive by
`machines/connive._replacement_draws` (the quality and the draw count are
read, not fixed). Leader is the only printing of the template legal in any
target format (Scryfall full-text search, 2026-09-24); its proof of
generality is that it applies to every connive instruction shape, which this
file drives through a trigger, an activated ability and a spell, none of them
Leader's own.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _settle(scenario) -> None:
    for _ in range(20):
        if scenario.game.stack_is_empty and not scenario.pending_triggers:
            return
        scenario.pass_until_resolved()


def _board(alice_battlefield: list[str], alice_hand: list[str] | None = None, **bob):
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Lightning Bolt", "Island", "Lightning Bolt", "Island"],
            hand=alice_hand or [],
            battlefield=alice_battlefield,
        )
        .player(
            "bob",
            library=["Lightning Bolt", "Island", "Lightning Bolt"],
            battlefield=bob.get("battlefield", []),
            hand=bob.get("hand", []),
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_a_creature_you_control_conniving_draws_one_more_first():
    """Leader + an activated connive: two draws, one discard."""
    scenario = _board(["Leader, Super-Genius", "Hypnotic Grifter", "Island", "Island", "Island"])
    grifter = scenario.creature("Hypnotic Grifter", "alice")
    alice = scenario.player("alice")
    first_bolt = alice.library[0]
    scenario.will_discard(first_bolt)

    scenario.activate(grifter, auto=True)
    scenario.resolve_top()

    assert len(alice.hand) == 1
    assert [state.card.name for state in alice.graveyard] == ["Lightning Bolt"]
    assert [state.card.name for state in alice.library] == ["Lightning Bolt", "Island"]
    assert grifter.counter_count(Counter.PLUS_ONE) == 1


def test_the_draw_comes_before_the_connive_draw():
    """ "instead you draw a card, then that creature connives": the replacement's
    card is the top one, the connive's the next - both in hand when the discard
    is asked."""
    scenario = _board(["Leader, Super-Genius", "Hypnotic Grifter", "Island", "Island", "Island"])
    grifter = scenario.creature("Hypnotic Grifter", "alice")
    alice = scenario.player("alice")

    scenario.activate(grifter, auto=True)
    scenario.resolve_top()

    (discard,) = [q for q in scenario.questions_asked() if q.prompt.startswith("discard")]
    assert len(discard.cards) == 2
    assert len(alice.hand) + len(alice.graveyard) == 2


def test_an_opponents_creature_is_not_replaced():
    """ "A creature *you* control": bob's conniver ignores alice's Leader."""
    scenario = _board(
        ["Leader, Super-Genius"],
        battlefield=["Hypnotic Grifter", "Island", "Island", "Island"],
    )
    grifter = scenario.creature("Hypnotic Grifter", "bob")
    while scenario.game.active_player.username != "bob":
        scenario.advance()
        _settle(scenario)  # Leader's own combat trigger on alice's turn
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    alice = scenario.player("alice")
    hand_before = len(bob.hand)
    alice_library = len(alice.library)

    scenario.activate(grifter, auto=True, username="bob")
    scenario.resolve_top()

    assert len(bob.hand) + len(bob.graveyard) - hand_before == 1
    assert len(alice.library) == alice_library


def test_a_trigger_connive_is_replaced_too():
    """A.I.M. Scientists' enters trigger under Leader: two draws, one discard."""
    scenario = _board(
        ["Leader, Super-Genius", "Island", "Island", "Island", "Island"], ["A.I.M. Scientists"]
    )
    alice = scenario.player("alice")

    scenario.cast_and_resolve("A.I.M. Scientists", auto=True)
    _settle(scenario)

    assert len(alice.library) == 2
    assert len(alice.graveyard) == 1
    assert len(alice.hand) == 1


def test_a_spell_connive_is_replaced_too():
    """Trickster's Stratagem's "Then up to one target creature you control
    connives." under Leader."""
    scenario = _board(
        ["Leader, Super-Genius", "Island", "Island", "Island", "Island"],
        ["Trickster's Stratagem"],
        battlefield=["Llanowar Elves"],
    )
    elves = scenario.creature("Llanowar Elves", "bob")
    leader = scenario.creature("Leader, Super-Genius", "alice")
    alice = scenario.player("alice")

    scenario.cast_and_resolve("Trickster's Stratagem", auto=True, targets=[elves, leader])

    assert len(alice.library) == 2
    assert len(alice.hand) == 1


def test_a_conniver_gone_before_resolution_is_still_replaced():
    """CR 701.50b: by last known information it was a creature alice controlled."""
    scenario = _board(["Leader, Super-Genius", "Swamp", "Swamp"], ["Red Room Recruit"])
    alice = scenario.player("alice")
    scenario.cast_and_resolve("Red Room Recruit", auto=True)
    scenario.pass_priority()
    recruit = scenario.find("Red Room Recruit", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(recruit)

    scenario.resolve_top()

    assert len(alice.library) == 2
    assert len(alice.hand) == 1


def test_no_leader_no_extra_card():
    scenario = _board(["Hypnotic Grifter", "Island", "Island", "Island"])
    grifter = scenario.creature("Hypnotic Grifter", "alice")
    alice = scenario.player("alice")

    scenario.activate(grifter, auto=True)
    scenario.resolve_top()

    assert len(alice.library) == 3


def test_a_leader_that_lost_its_abilities_replaces_nothing():
    """CR 613.1f: Humility removes Leader's abilities, and the replacement with
    them. Unstable Experiment: alice draws one, then the Bears connive - two
    cards in all, not three."""
    scenario = _board(
        ["Leader, Super-Genius", "Humility", "Grizzly Bears", "Island", "Island"],
        ["Unstable Experiment"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    alice = scenario.player("alice")

    scenario.cast_and_resolve("Unstable Experiment", auto=True, targets=["alice", bears])

    assert len(alice.library) == 2


def test_without_humility_the_same_spell_is_replaced():
    """The control for the test above: the same spell, Leader intact, three cards."""
    scenario = _board(
        ["Leader, Super-Genius", "Grizzly Bears", "Island", "Island"],
        ["Unstable Experiment"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    alice = scenario.player("alice")

    scenario.cast_and_resolve("Unstable Experiment", auto=True, targets=["alice", bears])

    assert len(alice.library) == 1
