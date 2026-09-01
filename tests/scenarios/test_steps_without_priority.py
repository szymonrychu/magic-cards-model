"""The steps in which nobody receives priority (CR 500.3, 502.4, 514.3, 514.3a).

Every rule cited here was looked up with `knowledge_search(type="rules")` in the
session that wrote the file:

- **CR 500.3** - "A step in which no players receive priority ends when all
  specified actions that take place during that step are completed. The only
  such steps are the untap step (see rule 502) and certain cleanup st[eps ...]".
  Two of the twelve, and the word that separates them is "certain".
- **CR 502.4** - "No player receives priority during the untap step, so no
  spells can be cast or resolve and no abilities can be activated or resolve.
  Any ability that triggers during this step will be held until the n[ext time a
  player would receive priority]." Unconditional, and with a second sentence
  that says what becomes of a trigger caught in it.
- **CR 514.3** - "Normally, no player receives priority during the cleanup step,
  so no spells can be cast and no abilities can be activated. However, this rule
  is subject to the following exception:".
- **CR 514.3a** - "At this point, the game checks to see if any state-based
  actions would be performed and/or any triggered abilities are waiting to be
  put onto the stack (including those that trigger 'at the beginnin[g of the
  next cleanup step]')." That is the exception CR 514.3 promises, and it is why
  a cleanup step is not simply a second untap step.
- **CR 117.3a** - "The active player receives priority at the beginning of most
  steps and phases, after any turn-based actions (such as drawing a card during
  the draw step; see rule 703) have been dealt with and abiliti[es ...]".
  "Most", not all: this file is about the rest.
- **CR 502.3** - "Third, the active player determines which permanents they
  control will untap. Then they untap them all simultaneously. This turn-based
  action doesn't use the stack." It is the event that lets a trigger fire inside
  a step that has no priority in it.
- **CR 701.26b** - only tapped permanents can be untapped, which is why the
  Hypnotist has to be turned sideways before the untap step means anything.

**Unverified, and therefore not tested**: `knowledge_search` in this session
returns CR 514.3a only as far as the sentence quoted above. What the rule says
happens *after* the game finds something waiting - in particular whether a
further cleanup step then begins - could not be confirmed, so it is neither
implemented nor asserted here. What is asserted is the half the excerpt states:
such a cleanup step is not one in which nobody receives priority.

The board is real printings throughout. Deepwater Hypnotist prints "Inspired -
Whenever this creature becomes untapped, target creature an opponent controls
gets -3/-0 until end of turn", which is the only shape of ability that can
trigger inside the untap step at all; Marauding Mako prints "Whenever you
discard one or more cards, put that many +1/+1 counters on this creature", which
is what CR 514.1's discard sets off inside the cleanup step.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

LIBRARY = ["Forest"] * 12
"""Enough cards that walking several turns never empties a library (CR 704.5b)."""


def two_players() -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Forest"], library=list(LIBRARY))
        .player("bob", battlefield=["Grizzly Bears"], library=list(LIBRARY))
    )


def walk_to_alices_untap_step(scenario) -> None:
    """Advance through bob's whole turn into alice's next untap step.

    Stepped rather than jumped: CR 500.6's beginning-of-step events and every
    turn-based action come from `Game.advance`, and the untap step's own
    CR 502.3 untapping is the event under test.
    """
    scenario.start_at(Step.END_STEP)
    while not (scenario.step is Step.UNTAP and scenario.turn.active_player == "alice"):
        scenario.advance()


# -- the untap step (CR 502.4) ----------------------------------------------


def test_nobody_receives_priority_during_the_untap_step():
    """CR 502.4's first clause, at the only moment a fresh game is ever in it.

    A `Scenario` builds a board with the turn pointer at `Step.UNTAP`, which is
    where CR 103.8's first turn starts. So this is not a contrived position: it
    is the state a client polls the instant a game exists, and the honest answer
    to "whose move is it" there is nobody's.
    """
    scenario = two_players().build()

    assert scenario.step is Step.UNTAP
    assert scenario.priority_holder is None


def test_passing_priority_in_the_untap_step_is_refused_with_the_rule():
    """CR 502.4, quoted back at the caller.

    The refusal matters more than it looks. A client that auto-passes will sit
    on an untap step forever if the engine hands it a priority it may not use;
    being told the rule is what tells it to advance the step instead.
    """
    scenario = two_players().build()

    with pytest.raises(ValueError, match="no player receives priority during the untap step"):
        scenario.pass_priority("alice")

    with pytest.raises(ValueError, match="CR 502.4"):
        scenario.pass_priority("bob")


def test_a_player_who_is_not_in_the_game_is_still_told_that_first():
    """ "carol is not at this table" outranks "nobody has priority".

    Both are true, but only one of them will still be true next turn, and
    quoting CR 502.4 at a name that does not exist sends the caller looking in
    the wrong place.
    """
    scenario = two_players().build()

    with pytest.raises(KeyError):
        scenario.pass_priority("carol")


def test_the_next_step_hands_priority_back_to_the_active_player():
    """CR 117.3a: upkeep is one of the "most steps" that do grant it.

    The pairing is the point - untap is not a game that has stopped, it is a
    step with nothing for a player to do, and the very next step proves it.
    """
    scenario = two_players().build()
    assert scenario.priority_holder is None

    scenario.advance()

    assert scenario.step is Step.UPKEEP
    assert scenario.priority_holder == "alice"


def test_the_untap_step_of_a_later_turn_grants_no_priority_either():
    """Not a first-turn quirk: every untap step is CR 502.4's."""
    scenario = two_players().build()
    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup
    scenario.advance()  # bob's untap step

    assert scenario.step is Step.UNTAP
    assert scenario.turn.active_player == "bob"
    assert scenario.priority_holder is None


# -- CR 502.4's second sentence: a trigger caught in the untap step ----------


def test_a_trigger_during_the_untap_step_is_held_until_priority_exists():
    """CR 502.4: "Any ability that triggers during this step will be held".

    Deepwater Hypnotist is tapped on bob's turn, so CR 502.3 untaps it in
    alice's untap step and its Inspired ability triggers there. CR 502.4 holds
    it: it must not be on the stack while the step that has no priority in it is
    still running, because CR 603.3 puts a triggered ability on the stack "the
    next time a player would receive priority" and that moment has not come.

    Held, not dropped - the two failure modes look identical from the stack, and
    only reading the waiting queue tells them apart.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Deepwater Hypnotist", "Forest"], library=list(LIBRARY))
        .player("bob", battlefield=["Grizzly Bears"], library=list(LIBRARY))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hypnotist = scenario.creature("Deepwater Hypnotist", "alice")
    hypnotist.tap()

    walk_to_alices_untap_step(scenario)

    assert hypnotist.untapped, "CR 502.3 untapped it"
    assert scenario.priority_holder is None
    assert scenario.stack_names() == [], "CR 502.4: nothing goes on the stack here"
    assert [item.source_name for item in scenario.pending_triggers] == ["Deepwater Hypnotist"]


def test_the_held_trigger_goes_on_the_stack_when_priority_next_exists():
    """The other half of CR 502.4's second sentence, and CR 603.3's "next time".

    Upkeep is that next time. The ability is on the stack before alice acts, and
    the waiting queue is empty - so nothing was lost on the way through a step
    that could not hold it.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Deepwater Hypnotist", "Forest"], library=list(LIBRARY))
        .player("bob", battlefield=["Grizzly Bears"], library=list(LIBRARY))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.creature("Deepwater Hypnotist", "alice").tap()
    walk_to_alices_untap_step(scenario)

    scenario.advance()  # upkeep

    assert scenario.step is Step.UPKEEP
    assert scenario.priority_holder == "alice"
    assert scenario.stack_names() == ["Deepwater Hypnotist's triggered ability"]
    assert scenario.pending_triggers == []


# -- the cleanup step (CR 514.3, 514.3a) ------------------------------------


def test_an_ordinary_cleanup_step_grants_nobody_priority():
    """CR 514.3's ordinary case: nothing triggered, so nobody acts.

    alice is at seven cards, so CR 514.1's discard does nothing and nothing
    triggers off it - which is exactly the cleanup step CR 514.3 describes.
    """
    scenario = two_players().build()
    scenario.start_at(Step.END_STEP)

    scenario.advance()

    assert scenario.step is Step.CLEANUP
    assert scenario.priority_holder is None
    with pytest.raises(ValueError, match="CR 514.3"):
        scenario.pass_priority("alice")


def test_a_cleanup_step_with_a_waiting_trigger_does_grant_priority():
    """CR 514.3a is why cleanup is not a second untap step.

    alice holds eight cards, so CR 514.1 discards one, and Marauding Mako's
    "Whenever you discard one or more cards" triggers on it. CR 514.3a has the
    game check for exactly that - "any triggered abilities are waiting to be put
    onto the stack" - and this cleanup step is therefore not one in which no
    player receives priority. The ability is on the stack and somebody may
    respond to it.

    Contrast `test_a_trigger_during_the_untap_step_is_held_until_priority_exists`:
    the same waiting trigger, in the step CR 502.4 gives no exception to, stays
    off the stack.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Marauding Mako"],
            hand=["Grizzly Bears"] * 8,
            library=list(LIBRARY),
        )
        .player("bob", library=list(LIBRARY))
        .build()
    )
    scenario.start_at(Step.END_STEP)
    assert len(scenario.player("alice").hand) == 8

    scenario.advance()

    assert scenario.step is Step.CLEANUP
    assert len(scenario.player("alice").hand) == 7, "CR 514.1's discard happened"
    assert scenario.stack_names() == ["Marauding Mako's triggered ability"]
    assert scenario.priority_holder == "alice", "CR 514.3a's exception"


def test_the_discarded_card_is_in_the_graveyard_not_lost_to_the_exception():
    """CR 514.1 still happened, exception or no.

    Guards against the obvious way to implement CR 514.3a wrongly: granting
    priority *instead of* running the step's turn-based action, rather than
    after it.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Marauding Mako"],
            hand=["Grizzly Bears"] * 8,
            library=list(LIBRARY),
        )
        .player("bob", library=list(LIBRARY))
        .build()
    )
    scenario.start_at(Step.END_STEP)

    scenario.advance()

    assert len(scenario.player("alice").graveyard) == 1
    assert scenario.player("alice").graveyard[0].zone is Zone.GRAVEYARD


def test_the_engine_refuses_to_advance_past_a_cleanup_that_has_a_stack():
    """CR 500.2: a step that grants priority ends only on an empty stack.

    An ordinary cleanup step may be advanced past with anything on the stack,
    because CR 500.3 ends it on its own actions completing rather than on a
    round of passes. A CR 514.3a cleanup step is not ordinary, and must not
    strand the ability it just put there.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Marauding Mako"],
            hand=["Grizzly Bears"] * 8,
            library=list(LIBRARY),
        )
        .player("bob", library=list(LIBRARY))
        .build()
    )
    scenario.start_at(Step.END_STEP)
    scenario.advance()

    assert scenario.stack_names() == ["Marauding Mako's triggered ability"]
    with pytest.raises(ValueError, match="pass priority instead"):
        scenario.advance()
