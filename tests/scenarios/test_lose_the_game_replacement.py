"""A general "If you would lose the game, instead <effects>." replacement (CR
614.1a) on top of CR 104.3's ways to lose: 0 or less life, an empty-library
draw, ten-plus poison counters, and CR 104.3e's "an effect may state that a
player loses the game."

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 104.3b** - "If a player's life total is 0 or less, that player loses
  the game the next time a player would receive priority. (This is a
  state-based action. See rule 704.)"
- **CR 104.3c** - the empty-library-draw loss, same "state-based action" shape.
- **CR 104.3d** - the ten-poison loss, same shape.
- **CR 104.3e** - "An effect may state that a player loses the game."
- **CR 104.4a** - "If all the players remaining in a game lose simultaneously,
  the game is a draw."
- **CR 704.5a/b/c** - the state-based actions `_losing_players` reads.
- **CR 614.1a** - "instead" replacement effects.
- **CR 119.5** - setting a life total is a gain or a loss.

Exquisite Archangel's "exile this creature and your life total becomes equal
to your starting life total" and Lich's Mirror's "shuffle your hand, your
graveyard, and all permanents you own into your library, then draw seven
cards and your life total becomes 20" are both read by `machines/replacement.
_compile_exile_self_and_life_total_becomes`/`_compile_shuffle_hand_graveyard_
permanents_then_draw_and_life_total` - general compilers keyed on the
sentence shape, not the card name - and applied through `Game._apply_lose_
the_game_replacements`, the one choke point both the state-based sweep
(`Game._check_state_based_actions_impl`) and a direct "loses the game" effect
(`Game.player_loses_the_game`) raise the loss through.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_exquisite_archangel_replaces_a_zero_life_loss() -> None:
    scenario = (
        Scenario()
        .player("alice", life=20, battlefield=["Exquisite Archangel"])
        .player("bob", life=20)
        .build()
    )
    archangel = scenario.find("Exquisite Archangel", Zone.BATTLEFIELD, "alice")

    scenario.game.lose_life(scenario.player("alice"), 25)  # 20 -> -5

    assert scenario.game.check_state_based_actions() == []
    assert archangel.zone is Zone.EXILE
    assert scenario.player("alice").life == 20  # starting_life, CR 119.5
    assert scenario.game.is_in_game("alice")
    assert "alice" not in scenario.game.losers


def test_exquisite_archangel_only_saves_its_own_controller() -> None:
    """Bob has no Archangel; his own 0-life loss is untouched."""
    scenario = (
        Scenario()
        .player("alice", life=20, battlefield=["Exquisite Archangel"])
        .player("bob", life=20)
        .player("carol", life=20)
        .build()
    )

    scenario.game.lose_life(scenario.player("bob"), 25)

    scenario.game.check_state_based_actions()

    assert not scenario.game.is_in_game("bob")
    assert "bob" in scenario.game.losers
    assert scenario.game.is_in_game("alice")


def test_exquisite_archangel_turns_a_simultaneous_loss_into_a_win_not_a_draw() -> None:
    """CR 104.4a's draw only fires when everyone still in the game loses at
    once - an Archangel replacing its own controller's loss means alice is
    the only one left, so she wins outright rather than the game drawing."""
    scenario = (
        Scenario()
        .player("alice", life=20, battlefield=["Exquisite Archangel"])
        .player("bob", life=20)
        .build()
    )

    scenario.game.lose_life(scenario.player("alice"), 25)
    scenario.game.lose_life(scenario.player("bob"), 25)

    scenario.game.check_state_based_actions()

    assert scenario.game.drawn is False
    assert scenario.game.winner == "alice"
    assert "bob" in scenario.game.losers
    assert "alice" not in scenario.game.losers


def test_exquisite_archangel_replaces_a_direct_lose_the_game_effect() -> None:
    """CR 104.3e's own shape - `Game.player_loses_the_game` - not only the
    three state-based losses."""
    scenario = (
        Scenario()
        .player("alice", life=20, battlefield=["Exquisite Archangel"])
        .player("bob", life=20)
        .build()
    )
    archangel = scenario.find("Exquisite Archangel", Zone.BATTLEFIELD, "alice")

    scenario.game.player_loses_the_game("alice")

    assert scenario.game.is_in_game("alice")
    assert archangel.zone is Zone.EXILE
    assert scenario.player("alice").life == 20


def test_lichs_mirror_shuffles_hand_graveyard_and_permanents_then_draws_and_resets_life() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            hand=["Forest", "Island"],
            graveyard=["Swamp"],
            library=["Mountain", "Plains", "Forest", "Island", "Swamp", "Mountain", "Plains"],
            battlefield=["Lich's Mirror"],
        )
        .player("bob", life=20)
        .build()
    )

    scenario.game.lose_life(scenario.player("alice"), 25)

    scenario.game.check_state_based_actions()

    alice = scenario.player("alice")
    assert scenario.game.is_in_game("alice")
    # 4 shuffled in (2 hand + 1 graveyard + Lich's Mirror itself) on top of the
    # 7-card library, then 7 drawn: 4 left in library, 7 fresh cards in hand,
    # nothing left behind in the graveyard.
    assert len(alice.hand) == 7
    assert alice.graveyard == []
    assert len(alice.library) == 4
    assert alice.life == 20
    assert not any(state.name == "Lich's Mirror" for state in scenario.game.battlefield)
    assert not scenario.game.is_over


def test_declining_a_loss_replacement_still_loses_the_game() -> None:
    """A control: nothing here saves bob, who has no such effect."""
    scenario = Scenario().player("alice", life=1).player("bob", life=0).build()
    scenario.start_at(Step.UPKEEP)

    scenario.game.check_state_based_actions()

    assert not scenario.game.is_in_game("bob")
    assert "bob" in scenario.game.losers
