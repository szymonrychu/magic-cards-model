"""Scenario: "Counter target loyalty ability of a planeswalker." - Verdant
Command's second mode, and the rest of its "Choose two" pairs.

A loyalty ability is one kind of activated ability, so the target is narrower
than "target activated ability" (Azorius Guildmage, Defabricate's "activated
or triggered"): an ordinary activated ability on the stack is not a legal
target. "Of a planeswalker" restricts the ability's source the same way "from
an artifact source" does (Brown Ouphe). No other Modern/Pioneer/Standard
printing counters a *loyalty* ability (Scryfall search, 2026-10-03), so the
generality is the target grammar's: "loyalty" joins "activated"/"triggered"
as a category word in the one ability-target reader, and "of a `<type>`" is
read by the same source-type check.

Rules, each read with `mise run rules:find` in the session that wrote this:

- **CR 606.1 / 606.2** - some activated abilities are loyalty abilities: an
  activated ability with a loyalty symbol in its cost is one.
- **CR 606.3** - only one loyalty ability of a permanent per turn; a countered
  one was still activated.
- **CR 606.4** - the cost is putting on or removing loyalty counters.
- **CR 701.6a** - a countered ability is removed from the stack and none of its
  effects occur; **CR 701.6b** - no refund of costs that were paid.
- **CR 700.2** - a modal spell; the modes are chosen as it is cast.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario

COMMAND = "Verdant Command"
LILIANA = "Liliana of the Veil"


def test_verdant_command_is_fully_handled():
    bad = [c for c in card_support(card(COMMAND)).clauses if c.outcome != "handled"]
    assert not bad, bad


def _board(alice_battlefield=(LILIANA, "Swamp"), bob_graveyard=()) -> Scenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Swamp"] * 3,
            hand=["Mountain"],
            battlefield=list(alice_battlefield),
            graveyard=["Lightning Bolt"],
        )
        .player(
            "bob",
            library=["Forest"] * 3,
            hand=[COMMAND, "Forest"],
            battlefield=["Forest", "Forest"],
            graveyard=list(bob_graveyard),
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _activate_liliana_plus(scenario: Scenario):
    liliana = scenario.find(LILIANA, Zone.BATTLEFIELD, "alice")
    ability = scenario.activate(liliana, index=0, username="alice")
    scenario.pass_priority("alice")
    return liliana, ability


def _cast_command(scenario: Scenario, modes: list[int], targets: list) -> None:
    if scenario.priority_holder == "alice":
        scenario.pass_priority("alice")
    casting = scenario.cast(COMMAND, username="bob")
    casting.choose_modes(modes)
    casting.choose_targets(targets)
    forests = scenario.untapped_sources("Forest", "Forest", username="bob")
    scenario.pay_with(casting.begin_paying(), *forests)
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def _squirrels(scenario: Scenario, username: str):
    return [
        state
        for state in scenario.game.battlefield
        if "Squirrel" in state.name and state.controller == username
    ]


# -- countering the loyalty ability -------------------------------------------


def test_the_loyalty_ability_is_countered_and_its_cost_stays_paid():
    scenario = _board()
    liliana, _ability = _activate_liliana_plus(scenario)
    assert liliana.loyalty == 4, "the +1 is paid on activation"

    _cast_command(scenario, [2, 4], [_ability, "bob"])

    assert scenario.stack_names() == []
    assert liliana.loyalty == 4, "CR 701.6b: no refund"
    assert len(scenario.player("alice").hand) == 1, "nobody discarded"
    assert len(scenario.player("bob").hand) == 1, "only the Command left bob's hand"
    assert scenario.player("bob").life == 23


def test_a_countered_loyalty_ability_still_used_the_turns_activation():
    """CR 606.3 counts the activation, not the resolution."""
    scenario = _board()
    liliana, ability = _activate_liliana_plus(scenario)
    _cast_command(scenario, [2, 4], [ability, "bob"])

    assert scenario.why_cannot_activate(liliana, 0, "alice") is not None


def test_an_ordinary_activated_ability_is_not_a_legal_target():
    scenario = _board(
        alice_battlefield=(LILIANA, "Vampiric Rites", "Swamp", "Swamp", "Grizzly Bears")
    )
    rites = scenario.find("Vampiric Rites", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    swamps = scenario.untapped_sources("Swamp", "Swamp", username="alice")
    ability = scenario.activate(rites, *swamps, username="alice", sacrificing=[bears])
    scenario.pass_priority("alice")

    casting = scenario.cast(COMMAND, username="bob")
    casting.choose_modes([2, 4])
    with pytest.raises(ValueError, match="loyalty"):
        casting.choose_targets([ability, "bob"])


def test_a_spell_is_not_a_legal_target():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Mountain"], hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", library=["Forest"], hand=[COMMAND], battlefield=["Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    scenario.pass_priority("alice")

    casting = scenario.cast(COMMAND, username="bob")
    casting.choose_modes([2, 4])
    with pytest.raises(ValueError):
        casting.choose_targets([bolt, "bob"])


# -- every other pair of modes -------------------------------------------------


def test_squirrels_and_exile_a_card_from_a_graveyard():
    scenario = _board(bob_graveyard=["Grizzly Bears"])
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")

    _cast_command(scenario, [1, 3], ["alice", bears])

    squirrels = _squirrels(scenario, "alice")
    assert len(squirrels) == 2
    assert all(token.tapped for token in squirrels)
    assert bears.zone is Zone.EXILE


def test_squirrels_for_one_player_and_life_for_another():
    scenario = _board()

    _cast_command(scenario, [1, 4], ["bob", "alice"])

    assert len(_squirrels(scenario, "bob")) == 2
    assert _squirrels(scenario, "alice") == []
    assert scenario.player("alice").life == 23
    assert scenario.player("bob").life == 20


def test_exile_a_card_and_gain_life():
    scenario = _board()
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")

    _cast_command(scenario, [3, 4], [bolt, "bob"])

    assert bolt.zone is Zone.EXILE
    assert scenario.player("bob").life == 23


def test_counter_the_loyalty_ability_and_make_squirrels():
    scenario = _board()
    liliana, ability = _activate_liliana_plus(scenario)

    _cast_command(scenario, [1, 2], ["bob", ability])

    assert scenario.stack_names() == []
    assert len(_squirrels(scenario, "bob")) == 2
    assert len(scenario.player("alice").hand) == 1
    assert liliana.loyalty == 4


def test_counter_the_loyalty_ability_and_exile_a_card():
    scenario = _board()
    _liliana, ability = _activate_liliana_plus(scenario)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")

    _cast_command(scenario, [2, 3], [ability, bolt])

    assert scenario.stack_names() == []
    assert bolt.zone is Zone.EXILE
    assert len(scenario.player("alice").hand) == 1


def test_an_uncountered_loyalty_ability_resolves():
    """The control: without the Command, Liliana's +1 makes each player discard."""
    scenario = _board()
    _activate_liliana_plus(scenario)
    scenario.pass_until_resolved()

    assert scenario.player("alice").hand == []
