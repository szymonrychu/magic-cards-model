"""Sanctum Lurker: "Planeswalkers you control aren't put into their owners'
graveyards for having 0 loyalty." - a printed exemption from CR 704.5i's own
state-based action.

Every CR number here was looked up with `mise run rules:find <number>`
against the checksum-verified 2026-09-25 Comprehensive Rules release in the
session that wrote this file.

- **CR 704.5i** / **CR 306.9** - "If a planeswalker has loyalty 0, it's put
  into its owner's graveyard" - the rule Sanctum Lurker overrides.
- **CR 101.2** / **CR 101.2a** - "the 'can't' effect takes precedence" is
  about *preventing* something the rules allow, not about adding or removing
  abilities (**101.2a**) - the exact reason this exemption needs no special
  handling beyond CR 101.2's own general "the card overrides the rule": it is
  an ordinary printed ability, not a layer 6 grant.
- **CR 704.3** - state-based actions are "performed simultaneously as a
  single event" whenever a player would get priority, which is what
  `Game.check_state_based_actions()` drives once, on demand, in these tests.

`Game._zero_loyalty_exemption_controllers` reads Sanctum Lurker's own text off
the battlefield and scopes the exemption to *that permanent's controller*
only - CR 704.5i names no exception of its own, so this is CR 101.2's
ordinary "the card overrides the rule" applied per-controller, not a global
suspension of the state-based action.

**A harness pitfall, found while writing this file.** `PlayedScenario.
state_based_actions()` (`tests/scenarios/harness.py`) is the idiom
`docs/scenario-tests.md` and `test_counters.py` document for a planeswalker
at zero loyalty, but it is exemption-blind: it calls `machines.card_state.
counter_state_based_actions`, which returns *every* zero-loyalty planeswalker
unconditionally, and destroys each one directly - before
`Game.check_state_based_actions()`, where `_zero_loyalty_exemption_
controllers` actually lives, is ever consulted. Using that harness method
here would destroy an exempted planeswalker and silently fail to prove the
exemption at all (confirmed by probing it directly: it puts an exempted
Tamiyo into the graveyard just as readily as an unexempted one). Every test
below calls `scenario.game.check_state_based_actions()` directly instead,
which is where CR 704.5i and the exemption both actually live.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import PREDEFINED, create_tokens
from tests.scenarios.harness import Scenario


def test_a_zero_loyalty_planeswalker_stays_while_its_controller_also_controls_sanctum_lurker():
    """The happy path: Sanctum Lurker overrides CR 704.5i for alice's own
    planeswalkers."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Sanctum Lurker", "Tamiyo, Compleated Sage"])
        .player("bob")
        .build()
    )
    tamiyo = scenario.find("Tamiyo, Compleated Sage", Zone.BATTLEFIELD, "alice")
    tamiyo.remove_counters(Counter.LOYALTY, 5)

    assert tamiyo.has_zero_loyalty
    assert scenario.game.check_state_based_actions() == []
    assert tamiyo.zone is Zone.BATTLEFIELD


def test_a_second_planeswalker_at_zero_loyalty_is_also_exempt():
    """The exemption is not "the first one" or "one at a time" - it is every
    planeswalker the exempted controller controls, so a second one at zero
    loyalty stays too."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Sanctum Lurker", "Tamiyo, Compleated Sage", "Ugin, Eye of the Storms"],
        )
        .player("bob")
        .build()
    )
    tamiyo = scenario.find("Tamiyo, Compleated Sage", Zone.BATTLEFIELD, "alice")
    ugin = scenario.find("Ugin, Eye of the Storms", Zone.BATTLEFIELD, "alice")
    tamiyo.remove_counters(Counter.LOYALTY, 5)
    ugin.remove_counters(Counter.LOYALTY, 7)

    assert tamiyo.has_zero_loyalty
    assert ugin.has_zero_loyalty
    assert scenario.game.check_state_based_actions() == []
    assert tamiyo.zone is Zone.BATTLEFIELD
    assert ugin.zone is Zone.BATTLEFIELD


def test_without_sanctum_lurker_a_planeswalker_at_zero_loyalty_is_put_into_the_graveyard():
    """The negative case: the identical board, minus Sanctum Lurker, and
    CR 704.5i runs as printed - proving the first test passed because of the
    exemption, not because this state-based action is broken."""
    scenario = (
        Scenario().player("alice", battlefield=["Tamiyo, Compleated Sage"]).player("bob").build()
    )
    tamiyo = scenario.find("Tamiyo, Compleated Sage", Zone.BATTLEFIELD, "alice")
    tamiyo.remove_counters(Counter.LOYALTY, 5)

    assert tamiyo.has_zero_loyalty
    assert tamiyo in scenario.game.check_state_based_actions()
    assert tamiyo.zone is Zone.GRAVEYARD


def test_the_exemption_does_not_reach_a_different_controllers_planeswalker():
    """Scoped per controller, not global: alice's Sanctum Lurker says nothing
    about bob's planeswalkers, so CR 704.5i still claims his."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Sanctum Lurker"])
        .player("bob", battlefield=["Tamiyo, Compleated Sage"])
        .build()
    )
    tamiyo = scenario.find("Tamiyo, Compleated Sage", Zone.BATTLEFIELD, "bob")
    tamiyo.remove_counters(Counter.LOYALTY, 5)

    assert tamiyo.has_zero_loyalty
    assert tamiyo in scenario.game.check_state_based_actions()
    assert tamiyo.zone is Zone.GRAVEYARD


def test_a_planeswalker_above_zero_loyalty_is_untouched_either_way():
    """Corner case: the exemption is about the *destination*, not a blanket
    "leave every planeswalker alone" - one still above zero loyalty was never
    going anywhere, exemption or not."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Sanctum Lurker", "Tamiyo, Compleated Sage"])
        .player("bob")
        .build()
    )
    tamiyo = scenario.find("Tamiyo, Compleated Sage", Zone.BATTLEFIELD, "alice")

    assert not tamiyo.has_zero_loyalty
    assert scenario.game.check_state_based_actions() == []
    assert tamiyo.zone is Zone.BATTLEFIELD


def test_sanctum_lurker_itself_is_not_a_planeswalker_and_is_unaffected():
    """A sanity check that the exemption reads "planeswalkers", not "every
    permanent alice controls": Sanctum Lurker is a creature, so nothing about
    loyalty applies to it at all."""
    scenario = Scenario().player("alice", battlefield=["Sanctum Lurker"]).player("bob").build()
    lurker = scenario.find("Sanctum Lurker", Zone.BATTLEFIELD, "alice")

    assert lurker.loyalty is None
    assert not lurker.has_zero_loyalty


# --------------------------------------------------------------------------
# Round 293-fra T3 corner cases, on the refreshed Sanctum Lurker printing.
# CR 704.5i, CR 704.3 and CR 701.71a looked up this session with
# `mise run rules:find`.
# --------------------------------------------------------------------------


JACE_TOKEN_MINUS_ONE = 0  # "[-1]: Surveil 1." - the token's first printed ability


def _jace_tokens(scenario, username: str = "alice") -> list:
    return [
        permanent
        for permanent in scenario.game.battlefield
        if permanent.name == "Jace" and permanent.controller == username
    ]


def test_a_freshly_created_zero_loyalty_jace_token_stays_under_sanctum_lurker():
    """CR 701.71a creates the token "with 0 loyalty"; a token created that
    way with no counters yet would be claimed by CR 704.5i, but Sanctum
    Lurker keeps it."""
    scenario = Scenario().player("alice", battlefield=["Sanctum Lurker"]).player("bob").build()
    (token,) = create_tokens(scenario.game, PREDEFINED["Jace"], "alice", count=1)

    assert token.has_zero_loyalty
    assert scenario.game.check_state_based_actions() == []
    assert token.zone is Zone.BATTLEFIELD


def test_without_sanctum_lurker_a_freshly_created_zero_loyalty_jace_token_dies():
    scenario = Scenario().player("alice").player("bob").build()
    (token,) = create_tokens(scenario.game, PREDEFINED["Jace"], "alice", count=1)

    assert token.has_zero_loyalty
    assert token in scenario.game.check_state_based_actions()
    assert _jace_tokens(scenario) == []


def test_a_jace_token_that_pays_its_last_counter_to_a_minus_ability_stays():
    """Sanctum Lurker's own ETB empower 1 makes a 1-loyalty token; its
    [-1] Surveil 1 takes it to 0 (CR 606.4), and the exemption keeps it on
    the battlefield through every state-based action check of the
    activation and its resolution."""
    scenario = (
        Scenario()
        .player("alice", hand=["Sanctum Lurker"], library=["Forest"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Sanctum Lurker")
    scenario.pass_until_resolved()
    (token,) = _jace_tokens(scenario)
    assert token.loyalty == 1

    scenario.surveil_keeping_everything_on_top()
    scenario.activate(token, index=JACE_TOKEN_MINUS_ONE)
    scenario.pass_until_resolved()

    assert token.has_zero_loyalty
    assert scenario.game.check_state_based_actions() == []
    assert _jace_tokens(scenario) == [token]


def test_when_sanctum_lurker_leaves_the_next_check_puts_zero_loyalty_walkers_away():
    """CR 704.3: the exemption lasts only while Lurker is on the battlefield;
    once it is gone, the very next state-based action check applies CR
    704.5i to the planeswalker that had been kept at 0."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Sanctum Lurker", "Tamiyo, Compleated Sage"])
        .player("bob")
        .build()
    )
    lurker = scenario.find("Sanctum Lurker", Zone.BATTLEFIELD, "alice")
    tamiyo = scenario.find("Tamiyo, Compleated Sage", Zone.BATTLEFIELD, "alice")
    tamiyo.remove_counters(Counter.LOYALTY, 5)
    assert scenario.game.check_state_based_actions() == []

    scenario.game.destroy(lurker)

    assert tamiyo in scenario.game.check_state_based_actions()
    assert tamiyo.zone is Zone.GRAVEYARD


def test_an_opponents_zero_loyalty_jace_token_is_not_exempt():
    """Scoped per controller: alice's Lurker does not keep bob's token."""
    scenario = Scenario().player("alice", battlefield=["Sanctum Lurker"]).player("bob").build()
    (token,) = create_tokens(scenario.game, PREDEFINED["Jace"], "bob", count=1)

    assert token in scenario.game.check_state_based_actions()
    assert _jace_tokens(scenario, "bob") == []
