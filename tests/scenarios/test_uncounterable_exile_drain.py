"""Scenario: "`<Exile/Destroy/Counter>` target X. Its controller loses N life
and you gain N life." - Inevitable Defeat, with its "This spell can't be
countered." line, and two other printings of the same drain: Certain Death
(destroy) and Punish Ignorance (counter).

"Its controller" is CR 400.7's anaphora back to the first sentence's own
target, read by `_parse_anaphoric_clause_pair` (permanent side) or
`_parse_counter_then_referent_pair` (stack side); "loses N life" is
`_parse_referent_clause`'s life-loss reader, and "you gain N life" is its own
clause, run against the spell's controller.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file.

- **CR 113.6g** - "An object's ability that states it can't be countered ...
  functions on the stack." A counterspell aimed at Inevitable Defeat resolves
  and does nothing to it.
- **CR 608.2h** - an effect that needs information from an object that has
  left the zone it was expected in uses the object's last known information:
  the player who *controlled* the exiled permanent loses the life, not its
  owner and not whoever controls nothing afterwards.
- **CR 119.3** - "If an effect causes a player to gain life or lose life,
  that player's life total is adjusted accordingly."
- **CR 608.2b** - a target that is gone makes the spell not resolve: Inevitable
  Defeat 2025-04-04, "No player will gain or lose life."
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

BOB_LANDS = [
    "Mountain",
    "Mountain",
    "Mountain",
    "Mountain",
    "Plains",
    "Plains",
    "Swamp",
    "Swamp",
    "Island",
    "Island",
]


def board(
    *, alice_hand: list[str], alice_battlefield: list[str], bob_hand: list[str]
) -> PlayedScenario:
    """Bob holds the drain spell; it is Bob's main phase."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", hand=bob_hand, battlefield=BOB_LANDS)
        .player(
            "alice",
            hand=alice_hand,
            battlefield=alice_battlefield + ["Island", "Island", "Mountain", "Swamp", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.turn.active_player == "bob"
    return scenario


def life(scenario: PlayedScenario) -> tuple[int, int]:
    return scenario.player("alice").life, scenario.player("bob").life


# -- Inevitable Defeat ---------------------------------------------------------


def test_inevitable_defeat_exiles_and_drains_the_permanents_controller():
    scenario = board(
        alice_hand=[], alice_battlefield=["Grizzly Bears"], bob_hand=["Inevitable Defeat"]
    )
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve("Inevitable Defeat", username="bob", auto=True, targets=[bears])

    assert bears.zone is Zone.EXILE
    assert life(scenario) == (17, 23)


def test_inevitable_defeat_hits_a_noncreature_permanent():
    """ "Nonland permanent" - an artifact is as good a target as a creature."""
    scenario = board(
        alice_hand=[], alice_battlefield=["Mind Stone"], bob_hand=["Inevitable Defeat"]
    )
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")

    scenario.cast_and_resolve("Inevitable Defeat", username="bob", auto=True, targets=[stone])

    assert stone.zone is Zone.EXILE
    assert life(scenario) == (17, 23)


def test_inevitable_defeat_cannot_target_a_land():
    scenario = board(alice_hand=[], alice_battlefield=[], bob_hand=["Inevitable Defeat"])
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")

    with pytest.raises(ValueError):
        scenario.cast("Inevitable Defeat", username="bob").choose_targets([forest])


def test_inevitable_defeat_cannot_be_countered():
    """CR 113.6g: Alice's Counterspell resolves and Inevitable Defeat stays on
    the stack, then resolves in full."""
    scenario = board(
        alice_hand=["Counterspell"],
        alice_battlefield=["Grizzly Bears"],
        bob_hand=["Inevitable Defeat"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    defeat = scenario.cast_onto_stack(
        "Inevitable Defeat", username="bob", auto=True, targets=[bears]
    )
    scenario.pass_priority("bob")

    scenario.cast_and_resolve("Counterspell", username="alice", auto=True, targets=[defeat])
    assert defeat.zone is Zone.STACK
    scenario.resolve_top()

    assert defeat.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.EXILE
    assert life(scenario) == (17, 23)


def test_the_life_loss_follows_the_controller_not_the_owner():
    """CR 608.2h: Bob has taken Alice's Grizzly Bears with Act of Treason, so
    *Bob* controlled the permanent Inevitable Defeat exiled - he loses 3 and
    gains 3, and Alice, its owner, is untouched even though the card is now
    in exile under nobody's control."""
    scenario = board(
        alice_hand=[],
        alice_battlefield=["Grizzly Bears"],
        bob_hand=["Act of Treason", "Inevitable Defeat"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    mountains = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="bob")
    scenario.cast_and_resolve("Act of Treason", *mountains, username="bob", targets=[bears])
    assert bears.controller == "bob"

    scenario.cast_and_resolve("Inevitable Defeat", username="bob", auto=True, targets=[bears])

    assert bears.zone is Zone.EXILE
    assert life(scenario) == (20, 20)


def test_a_target_gone_before_resolution_changes_nobodys_life():
    """Inevitable Defeat 2025-04-04: an illegal target means "none of its
    effects will happen. No player will gain or lose life." Alice bolts her
    own bears in response."""
    scenario = board(
        alice_hand=["Lightning Bolt"],
        alice_battlefield=["Grizzly Bears"],
        bob_hand=["Inevitable Defeat"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_onto_stack("Inevitable Defeat", username="bob", auto=True, targets=[bears])
    scenario.pass_priority("bob")
    scenario.cast_and_resolve("Lightning Bolt", username="alice", auto=True, targets=[bears])
    assert bears.zone is Zone.GRAVEYARD

    scenario.resolve_top()

    assert life(scenario) == (20, 20)


# -- Certain Death: the destroy printing of the same drain ------------------


def test_certain_death_destroys_and_drains():
    scenario = board(alice_hand=[], alice_battlefield=["Grizzly Bears"], bob_hand=["Certain Death"])
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve("Certain Death", username="bob", auto=True, targets=[bears])

    assert bears.zone is Zone.GRAVEYARD
    assert life(scenario) == (18, 22)


# -- Punish Ignorance: the counter printing, against an uncounterable spell -


def test_punish_ignorance_counters_and_drains_the_spells_controller():
    scenario = board(alice_hand=["Opt"], alice_battlefield=[], bob_hand=["Punish Ignorance"])
    scenario.pass_priority("bob")
    opt = scenario.cast_onto_stack("Opt", username="alice", auto=True)
    scenario.pass_priority("alice")

    scenario.cast_and_resolve("Punish Ignorance", username="bob", auto=True, targets=[opt])

    assert opt.zone is Zone.GRAVEYARD
    assert life(scenario) == (17, 23)


def test_punish_ignorance_on_inevitable_defeat_still_drains():
    """Punish Ignorance 2008-10-01: a spell that "can't be countered" is still
    a legal target - "the first part ... won't do anything, but the life-loss
    and life-gain effects will still work." Alice's Punish Ignorance meets
    Bob's Inevitable Defeat: Defeat stays, Bob loses 3 and Alice gains 3, then
    Defeat resolves and drains Alice right back."""
    scenario = board(
        alice_hand=["Punish Ignorance"],
        alice_battlefield=["Grizzly Bears", "Plains", "Plains"],
        bob_hand=["Inevitable Defeat"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    defeat = scenario.cast_onto_stack(
        "Inevitable Defeat", username="bob", auto=True, targets=[bears]
    )
    scenario.pass_priority("bob")

    scenario.cast_and_resolve("Punish Ignorance", username="alice", auto=True, targets=[defeat])
    assert defeat.zone is Zone.STACK
    assert life(scenario) == (23, 17)

    scenario.resolve_top()
    assert bears.zone is Zone.EXILE
    assert life(scenario) == (20, 20)
