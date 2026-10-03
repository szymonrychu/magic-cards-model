"""Enduring Angel (front face): "If your life total would be reduced to 0 or
less, instead transform this creature and your life total becomes 3. Then if
this creature didn't transform this way, you lose the game."

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 614.1a** - "instead" replacement effects.
- **CR 119.2/119.3** - damage to a player is life loss, and any life loss is
  its own event - `Game.deal_damage_to_player` ends by calling `Game.
  lose_life`, so combat damage reaches this replacement exactly the same way
  a plain "you lose N life" spell would.
- **CR 701.27a** - transform: "turn it over so that its other face is up."
- **CR 104.3e** - "An effect may state that a player loses the game" - the
  fallback the second sentence states.

Only the front face's own replacement is this file's scope; Angelic
Enforcer's own CDA power/toughness and attack trigger are a different task's
own assignment (see the shared brief) and are not exercised here.
"""

from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_a_lethal_reduction_transforms_instead_of_losing() -> None:
    scenario = (
        Scenario()
        .player("alice", life=5, battlefield=["Enduring Angel"])
        .player("bob", life=20)
        .build()
    )
    angel = scenario.find("Enduring Angel", Zone.BATTLEFIELD, "alice")
    assert angel.transformed is False

    scenario.game.lose_life(scenario.player("alice"), 10)  # would take 5 -> -5

    assert scenario.game.is_in_game("alice")
    assert angel.transformed is True
    assert scenario.player("alice").life == 3
    assert angel.zone is Zone.BATTLEFIELD


def test_a_non_lethal_reduction_is_untouched() -> None:
    scenario = (
        Scenario()
        .player("alice", life=10, battlefield=["Enduring Angel"])
        .player("bob", life=20)
        .build()
    )
    angel = scenario.find("Enduring Angel", Zone.BATTLEFIELD, "alice")

    scenario.game.lose_life(scenario.player("alice"), 3)  # 10 -> 7, not lethal

    assert scenario.player("alice").life == 7
    assert angel.transformed is False


def test_after_transforming_a_second_lethal_reduction_loses_normally() -> None:
    """Angelic Enforcer (the back face) prints no such replacement, so a
    second lethal reduction is an ordinary state-based loss (CR 704.5a)."""
    scenario = (
        Scenario()
        .player("alice", life=5, battlefield=["Enduring Angel"])
        .player("bob", life=20)
        .build()
    )
    angel = scenario.find("Enduring Angel", Zone.BATTLEFIELD, "alice")
    scenario.game.lose_life(scenario.player("alice"), 10)  # transforms, life -> 3
    assert angel.transformed is True

    scenario.game.lose_life(scenario.player("alice"), 10)  # 3 -> -7, no protection now
    scenario.game.check_state_based_actions()

    assert not scenario.game.is_in_game("alice")
    assert "alice" in scenario.game.losers
