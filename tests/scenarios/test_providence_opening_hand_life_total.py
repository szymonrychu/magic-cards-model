"""Providence: "You may reveal this card from your opening hand. If you do, at
the beginning of the first upkeep, your life total becomes 26.\nYour life total
becomes 26."

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 103.6b** - "If a card allows a player to reveal it from their opening
  hand, the player taking this action does so. The card remains revealed until
  the first turn begins. Each card may be revealed this way only once."
- **CR 603.7** / **CR 603.7b** - a delayed triggered ability fires once, the
  next time its event occurs.
- **CR 119.5** - "If an effect sets a player's life total to a specific
  number, the player gains or loses the necessary amount of life to end up
  with the new total." So a life total moving up to 26 is a *gain* (CR 119.9
  sees it, `Game.set_life_total` is the shared primitive).

Providence's own printed rider ("at the beginning of the first upkeep, your
life total becomes 26") is the same "the first upkeep" shape
`tests/scenarios/test_opening_hand_reveal_first_upkeep.py` already proves for
Chancellor of the Forge - read here by `machines/effects.life_total_becomes_
effect_for`, not by any card-specific code. The card's own second line ("Your
life total becomes 26.") is what a direct cast resolves into, proven by
casting the card outright.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from tests.scenarios.harness import PlayedScenario, Scenario

LIBRARY = ["Forest", "Island", "Swamp", "Mountain", "Plains"]


def will_reveal(scenario: PlayedScenario, player: str, source: str) -> None:
    scenario.game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.OPENING_HAND_ACTION,
            value=True,
            player=player,
            source=source,
        )
    )


def test_revealing_sets_life_to_26_at_the_first_upkeep() -> None:
    scenario = (
        Scenario()
        .player("alice", life=12, hand=["Providence"], library=list(LIBRARY))
        .player("bob", library=list(LIBRARY))
        .build()
    )
    will_reveal(scenario, "alice", "Providence")

    scenario.game.take_opening_hand_actions()
    scenario.advance()
    assert scenario.step is Step.UPKEEP
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 26
    assert scenario.game.delayed_triggers.triggers == []


def test_declining_the_reveal_leaves_life_untouched() -> None:
    scenario = (
        Scenario()
        .player("alice", life=12, hand=["Providence"], library=list(LIBRARY))
        .player("bob", library=list(LIBRARY))
        .build()
    )

    scenario.game.take_opening_hand_actions()

    assert scenario.player("alice").life == 12
    assert scenario.game.delayed_triggers.triggers == []


def test_casting_providence_directly_sets_life_to_26() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            life=8,
            hand=["Providence"],
            battlefield=["Plains"] * 7,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Providence", auto=True)

    assert scenario.player("alice").life == 26


def test_casting_providence_already_at_26_is_neither_a_gain_nor_a_loss() -> None:
    """CR 119.5: a life total already at the target sets nothing - CR 603.2g
    treats a zero-amount change as no event at all, so nothing must fire a
    gain or a loss trigger off an already-equal total."""
    scenario = (
        Scenario()
        .player(
            "alice",
            life=26,
            hand=["Providence"],
            battlefield=["Plains"] * 7,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    before_gained = set(scenario.game.life_gained_this_turn)

    scenario.cast_and_resolve("Providence", auto=True)

    assert scenario.player("alice").life == 26
    assert scenario.game.life_gained_this_turn == before_gained
