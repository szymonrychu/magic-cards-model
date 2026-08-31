"""Judge scenario: APNAP order, from DDR#976 "How does APNAP work?".

The episode's setup is a Show and Tell that puts a second Isamaru, Hound of
Konda onto the battlefield under *each* of two players who already had one, and
asks who chooses which copy to keep, and whose copy hits the graveyard first.
The answer has two halves, and this file separates them because the engine gets
one right and does not model the other at all:

- **Both extras are binned at the same moment.** CR 704.3: "Whenever a player
  would get priority ... the game checks for any of the listed conditions for
  state-based actions, then performs all applicable state-based actions
  simultaneously as a single event." CR 117.5 says the same from priority's
  side. So there is no "first" - one check moves alice's spare Isamaru and
  bob's spare Isamaru together.

- **Choices that would be made at the same time are made in APNAP order.**
  CR 101.4: "If multiple players would make choices and/or take actions at the
  same time, the active player (the player whose turn it is) makes any choices
  required, then the next player in turn order ..." CR 704.5j's legend rule is
  a choice ("that player chooses one of them"), and `Game._legend_rule_losers`
  keeps the first copy on the battlefield without asking anyone - so the
  ordering the episode is *about* has nothing to order. That half is `xfail`.

The engine does implement CR 101.4's ordering where it shows: CR 603.3b puts
simultaneously triggered abilities on the stack in APNAP order, and the episode
walks that too ("Pat's Shocker ability will resolve first, then Leellia, and
then finally Amy's gas" - active player lowest, so last). `test_triggered_
abilities.py` already covers the two-player case; the three-player case, which
is what makes "then the next player in turn order" observable at all, is here.

Every CR number in this file was verified with `knowledge_search(q="...",
type="rules")` in the session that wrote it: CR 101.4, CR 101.4d, CR 102.1,
CR 117.5, CR 205.4d, CR 603.3b, CR 704.2, CR 704.3, CR 704.5j.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# CR 704.3: one check, both players' extras, one event
# --------------------------------------------------------------------------


def two_players_two_isamarus() -> Scenario:
    """The episode's board: each player controls two Isamaru, Hound of Konda.

    Isamaru is a vanilla legendary 2/2 with no oracle text at all, so nothing
    on the card can confuse the state-based action being measured.
    """
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Isamaru, Hound of Konda", "Isamaru, Hound of Konda"],
        )
        .player(
            "bob",
            battlefield=["Isamaru, Hound of Konda", "Isamaru, Hound of Konda"],
        )
    )


def test_both_players_extra_legends_are_binned_by_the_same_check():
    """DDR#976: "all state-based actions are performed simultaneously as part
    of a single game event", so neither player's Isamaru goes first.

    CR 704.3 performs every applicable state-based action "simultaneously as a
    single event"; CR 704.5j is one of them. One call returns both losers, and
    neither player had to wait for the other.
    """
    scenario = two_players_two_isamarus().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    moved = scenario.state_based_actions()

    assert [(state.name, state.controller) for state in moved] == [
        ("Isamaru, Hound of Konda", "alice"),
        ("Isamaru, Hound of Konda", "bob"),
    ]
    assert all(state.zone is Zone.GRAVEYARD for state in moved)
    assert scenario.battlefield_names() == [
        "Isamaru, Hound of Konda",
        "Isamaru, Hound of Konda",
    ]


def test_the_legend_rule_leaves_each_player_exactly_one():
    """CR 704.5j is per controller (CR 205.4d), so both players keep one.

    This is the shape DDR#775 already established for a single player; the
    point here is only that a second player's copies are judged against *his*
    battlefield, not against the four permanents in play.
    """
    scenario = two_players_two_isamarus().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.state_based_actions()

    for username in ("alice", "bob"):
        kept = [
            state
            for state in scenario.game.battlefield
            if state.controller == username and state.name == "Isamaru, Hound of Konda"
        ]
        assert len(kept) == 1
        assert len(scenario.player(username).graveyard) == 1


@pytest.mark.xfail(
    reason=(
        "CR 704.5j's choice is not asked. `Game._legend_rule_losers` keeps the "
        "first copy on the battlefield rather than asking its controller which "
        "to keep, so there is no simultaneous choice for CR 101.4's APNAP "
        "order to order - the whole point of DDR#976's first half."
    ),
    strict=True,
)
def test_each_controller_is_asked_which_legend_to_keep():
    """DDR#976: "the active player makes that decision first and then the other
    players go in turn order" (CR 101.4).

    For that to be observable the legend rule has to *ask*. It does not: the
    check runs to completion with no question put to anybody.
    """
    scenario = two_players_two_isamarus().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.state_based_actions()

    assert scenario.questions_asked() != []


# --------------------------------------------------------------------------
# CR 603.3b: the ordering the engine does implement, with three players
# --------------------------------------------------------------------------


def three_blood_artists() -> Scenario:
    """Three players, one Blood Artist each, and a legend-rule death to feed
    all three triggers at the same moment.

    Blood Artist: "Whenever this creature or another creature dies, target
    player loses 1 life and you gain 1 life." One creature dying triggers every
    copy, so all three abilities are waiting when priority would next be
    received - CR 603.3b's precondition, word for word.
    """
    return (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Blood Artist",
                "Isamaru, Hound of Konda",
                "Isamaru, Hound of Konda",
            ],
        )
        .player("bob", battlefield=["Blood Artist"])
        .player("carol", battlefield=["Blood Artist"])
    )


def _trigger_order(scenario) -> list[str]:
    scenario.state_based_actions()
    scenario.choose_trigger_targets("Blood Artist", ["alice"])
    return [ability.controller for ability in scenario.game.put_triggers_on_stack()]


def test_three_simultaneous_triggers_go_on_the_stack_in_turn_order():
    """CR 603.3b: "each player, in APNAP order, puts each triggered ability
    they control on the stack".

    The active player's goes on lowest, so it resolves last - the episode's
    "Pat's Shocker ability will resolve first ... and then finally Amy's gas".
    Three players is what makes CR 101.4's "then the next player in turn order"
    distinguishable from a plain two-player swap.
    """
    scenario = three_blood_artists().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert _trigger_order(scenario) == ["alice", "bob", "carol"]


def test_apnap_starts_at_whoever_is_active_not_at_the_first_seat():
    """CR 102.1: "The active player is the player whose turn it is."

    APNAP is not seating order - it is seating order *rotated to start at the
    active player*. Passing the turn to bob moves alice to the back of the
    queue, which is the only assertion that tells CR 101.4 apart from a fixed
    list of usernames.
    """
    scenario = three_blood_artists().build()
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    assert scenario.turn.active_player == "bob"
    scenario.turn.advance_to(Step.PRECOMBAT_MAIN)

    assert _trigger_order(scenario) == ["bob", "carol", "alice"]
