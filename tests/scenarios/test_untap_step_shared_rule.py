"""Scenario: the untap step's "what untaps" rule, asked as a question.

`Game.untap_step_rule` is the one place the rule lives. The untap step reads
it and then does the untapping; anything else that needs to know what the next
untap step would do - a mana hypothetical looking a turn ahead - reads the same
function rather than a second copy of the filter. This file proves the two
agree on one board, so a later reader cannot drift from the step.

The rule it answers, in the order the untap step applies it:

- **CR 614.10** - "An effect that causes a player to skip an event, step,
  phase, or turn is a replacement effect. 'Skip [something]' is the same as
  'Instead of doing [something], do nothing.'" A skipped untap step untaps
  nothing at all, so the verdict comes first and the permanent list is empty.
- **CR 502.3** - "the active player determines which permanents they control
  will untap. Then they untap them all simultaneously. ... Normally, all of a
  player's permanents untap, but effects can keep one or more of a player's
  permanents from untapping." Only permanents that player controls, and the
  "doesn't untap" grant is one of those effects.
- **CR 613.5** - "The application of continuous effects as described by the
  layer system is continually and automatically performed by the game", so the
  grant is read off the computed board and not off printed text.
- **CR 122.1d** - "One or more stun counters on a permanent create a single
  replacement effect that stops the permanent from untapping." That one is
  deliberately *not* in the filter: it is a replacement on the untap itself,
  spent inside `CardState.untap`, so the shared rule over-reports a stunned
  permanent as untapping and says so in its own docstring. The last test here
  is that documented gap, asserted rather than described.
- **CR 502.4** - "No player receives priority during the untap step", which is
  why a skipped step leaves nothing waiting in `pending_triggers` either.

Every CR number above was read in full from the primary source with
`mise run rules:find` in the session that wrote this file: 614.10, 502.3,
502.4, 613.5, 122.1d.

Cards: Traxos, Scourge Eternal prints the self-only "doesn't untap during your
untap step" and Basalt Monolith the same sentence on a noncreature artifact
from a different set, so nothing here rides on one printing. Neither card is
named by the rule itself - it reads the canonical granted line off the board.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import PlayedScenario, Scenario

TRAXOS = "Traxos, Scourge Eternal"
MONOLITH = "Basalt Monolith"


def board(*, skips: int = 0) -> PlayedScenario:
    """Alice controls a "doesn't untap" permanent, two ordinary ones, and one
    permanent that is already untapped. Bob controls one of his own."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[TRAXOS, MONOLITH, "Forest", "Grizzly Bears"])
        .player("bob", battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for name in (TRAXOS, MONOLITH, "Forest"):
        scenario.find(name, Zone.BATTLEFIELD, "alice").tapped = True
    scenario.find("Island", Zone.BATTLEFIELD, "bob").tapped = True
    if skips:
        scenario.game.players_skipping_next_untap["alice"] = skips
    return scenario


def names(states) -> list[str]:
    return sorted(state.name for state in states)


def test_the_rule_names_exactly_the_permanents_the_step_untaps():
    """CR 502.3: this player's permanents, less the ones an effect keeps from
    untapping."""
    scenario = board()

    verdict = scenario.game.untap_step_rule("alice")

    assert verdict.skipped is False
    assert names(verdict.permanents) == ["Forest", "Grizzly Bears"]

    was_tapped = {state.id for state in verdict.permanents if state.tapped}
    scenario.game.untap_step()
    untapped_now = {
        state.id
        for state in scenario.game.battlefield
        if not state.tapped and state.controller == "alice"
    }

    assert was_tapped == {scenario.find("Forest", Zone.BATTLEFIELD, "alice").id}
    assert scenario.find(TRAXOS, Zone.BATTLEFIELD, "alice").tapped, "CR 502.3's exception"
    assert scenario.find(MONOLITH, Zone.BATTLEFIELD, "alice").tapped
    assert untapped_now == {state.id for state in verdict.permanents}


def test_the_rule_answers_for_the_player_it_is_asked_about():
    """CR 502.3 is "permanents they control" - bob's Island is never in
    alice's answer, and asking about bob gets his own board."""
    scenario = board()

    assert "Island" not in names(scenario.game.untap_step_rule("alice").permanents)
    assert names(scenario.game.untap_step_rule("bob").permanents) == ["Island"]


def test_a_skipped_step_is_the_rules_own_verdict_and_untaps_nothing():
    """CR 614.10's "instead of doing [something], do nothing" - the board here
    carries a "doesn't untap" permanent as well, so the skip has to win over
    the whole batch rather than merely over the filter."""
    scenario = board(skips=1)

    verdict = scenario.game.untap_step_rule("alice")

    assert verdict.skipped is True
    assert verdict.permanents == []

    scenario.game.untap_step()

    assert names(
        state for state in scenario.game.battlefield if state.controller == "alice" and state.tapped
    ) == [MONOLITH, "Forest", TRAXOS]
    assert "alice" not in scenario.game.players_skipping_next_untap, "one skip, one step"
    assert scenario.pending_triggers == [], "CR 502.4: nothing untapped, so nothing triggered"


def test_two_skips_are_two_steps_and_the_rule_still_says_skipped():
    """CR 614.10a: "If two effects each cause a player to skip their next
    occurrence, that player must skip the next two"."""
    scenario = board(skips=2)

    assert scenario.game.untap_step_rule("alice").skipped is True
    scenario.game.untap_step()
    assert scenario.game.players_skipping_next_untap["alice"] == 1
    assert scenario.game.untap_step_rule("alice").skipped is True
    assert scenario.find("Forest", Zone.BATTLEFIELD, "alice").tapped


def test_asking_the_rule_changes_nothing():
    """It is a question. It does not spend the skip, untap anything, or emit
    the CR 502.3 untap event - the step does all three, afterwards."""
    scenario = board(skips=1)
    before = scenario.game.model_dump(mode="json")

    for _ in range(3):
        scenario.game.untap_step_rule("alice")
        scenario.game.untap_step_rule("bob")

    assert scenario.game.model_dump(mode="json") == before
    assert scenario.game.players_skipping_next_untap["alice"] == 1


def test_a_stun_counter_is_not_part_of_the_shared_filter():
    """The documented gap (CR 122.1d). The counter is a replacement on the
    untap itself, spent inside `CardState.untap`, so the rule reports the
    permanent as untapping and the step still leaves it tapped."""
    scenario = board()
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    bears.tapped = True
    bears.add_counters(Counter.STUN, 1)

    verdict = scenario.game.untap_step_rule("alice")
    assert "Grizzly Bears" in names(verdict.permanents), "the filter does not read stun counters"

    scenario.game.untap_step()

    assert bears.tapped, "CR 122.1d replaced the untap"
    assert bears.counter_count(Counter.STUN) == 0, "and spent one counter doing it"
