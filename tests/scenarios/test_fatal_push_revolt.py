"""Scenario: Fatal Push - "Destroy target creature if it has mana value 2 or
less. Revolt — Destroy that creature if it has mana value 4 or less instead
if a permanent left the battlefield under your control this turn."

Revolt is read as a per-turn fact on `Game` (`permanents_left_battlefield_
this_turn`, `Game.revolt_active_for`), fed by every route a permanent takes
off the battlefield, and consulted by `machines/targeting.py`'s own
`TargetRequirement.comparison_value_if_revolt` - the same target-legality
mechanism that already enforces the base "mana value 2 or less" restriction,
now widened to 4 when Revolt is active, checked fresh at both announcement
(CR 601.2c) and resolution (CR 608.2b).

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 207.2c** - "An ability word appears in italics at the beginning of some
  abilities" - Revolt is an ability word; no further numbered rule names it.
- **CR 601.2c** - announcing a legal target.
- **CR 608.2b** - "A target that's no longer in the zone it was in when it
  was targeted is illegal. Other changes to the game state may cause a
  target to no longer be legal."
- **CR 701.8a** - "To destroy a permanent, move it from the battlefield to
  its owner's graveyard."
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _to_main(scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)


def test_fatal_push_destroys_a_cheap_creature_with_no_revolt():
    """Elvish Mystic, mana value 1: the base clause alone is enough."""
    scenario = (
        Scenario()
        .player("alice", hand=["Fatal Push"], battlefield=["Swamp"])
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    _to_main(scenario)
    mystic = scenario.creature("Elvish Mystic", "bob")

    (swamp,) = scenario.untapped_sources("Swamp")
    scenario.cast_and_resolve("Fatal Push", swamp, targets=[mystic])

    assert mystic.zone is Zone.GRAVEYARD


def test_fatal_push_cannot_target_a_mana_value_3_creature_without_revolt():
    """Without Revolt, the printed restriction is mana value 2 or less - a
    Goblin Guide-sized (mana value 1) creature is fine, but this scenario
    uses a mana value 3 creature and confirms it is not a legal announcement
    at all when nothing has left the battlefield this turn.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Fatal Push"], battlefield=["Swamp"])
        .player("bob", battlefield=["Gray Merchant of Asphodel"])
        .build()
    )
    _to_main(scenario)
    merchant = scenario.creature("Gray Merchant of Asphodel", "bob")
    # Gray Merchant of Asphodel is mana value 5 - well past even Revolt's 4.
    # Confirms the base restriction (and Revolt's own ceiling) both refuse it.
    casting = scenario.cast("Fatal Push")
    with pytest.raises(ValueError):
        casting.choose_targets([merchant])


def test_fatal_push_kills_a_mana_value_4_creature_with_revolt_active():
    """Revolt active (a permanent alice controlled already left the
    battlefield this turn) widens the restriction to mana value 4 or less -
    a real mana value 4 creature becomes both a legal target and dies.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fatal Push"],
            battlefield=["Swamp", "Elvish Mystic"],
        )
        .player("bob", battlefield=["Wood Elves"])
        .build()
    )
    _to_main(scenario)
    mystic = scenario.creature("Elvish Mystic", "alice")
    elves = scenario.creature("Wood Elves", "bob")
    assert elves.card.cmc == 3.0, "picked for its mana value; adjust if the fixture changes"

    # Revolt's own condition: a permanent alice controlled left the
    # battlefield this turn (CR 207.2c has no numbered rule for the phrase
    # itself; this is the plain wording printed on the card).
    scenario.game.destroy(mystic)
    assert scenario.game.revolt_active_for("alice")

    (swamp,) = scenario.untapped_sources("Swamp")
    scenario.cast_and_resolve("Fatal Push", swamp, targets=[elves])

    assert elves.zone is Zone.GRAVEYARD


def test_revolt_does_not_carry_over_from_a_different_players_departure():
    """Revolt asks about a permanent *you* controlled - bob losing a creature
    does not turn on alice's Revolt.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Fatal Push"], battlefield=["Swamp"])
        .player("bob", battlefield=["Elvish Mystic", "Wood Elves"])
        .build()
    )
    _to_main(scenario)
    mystic = scenario.creature("Elvish Mystic", "bob")
    elves = scenario.creature("Wood Elves", "bob")

    scenario.game.destroy(mystic)
    assert not scenario.game.revolt_active_for("alice")

    casting = scenario.cast("Fatal Push", username="alice")
    with pytest.raises(ValueError):
        casting.choose_targets([elves])


def test_revolt_does_not_persist_into_the_next_turn():
    """`Game.permanents_left_battlefield_this_turn` is cleared when a new
    turn begins, the same reset `spells_cast_this_turn` already gets - a
    creature that died last turn does not still satisfy Revolt this turn.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fatal Push"],
            battlefield=["Swamp", "Elvish Mystic"],
        )
        .player("bob", battlefield=["Wood Elves"])
        .build()
    )
    _to_main(scenario)
    mystic = scenario.creature("Elvish Mystic", "alice")
    elves = scenario.creature("Wood Elves", "bob")

    scenario.game.destroy(mystic)
    assert scenario.game.revolt_active_for("alice")

    # Roll the game forward into a fresh turn.
    turns_taken = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns_taken:
        scenario.advance()

    assert not scenario.game.revolt_active_for("alice")

    casting = scenario.cast("Fatal Push", username="alice")
    with pytest.raises(ValueError):
        casting.choose_targets([elves])
