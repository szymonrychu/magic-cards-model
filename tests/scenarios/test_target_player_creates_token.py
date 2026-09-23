"""A mode whose subject is the targeted player: "Target player creates <token>."

- **CR 111.2** - "The player who creates a token is its owner. The token
  enters the battlefield under that player's control." The sentence's subject
  is the targeted player, so the token is theirs, not the caster's.
- **CR 111.10a** - a Treasure token is a colorless Treasure artifact token with
  "{T}, Sacrifice this token: Add one mana of any color." A predefined token
  named by its bare name (no P/T, no colour, no creature type).
- **CR 700.2** - each chosen mode is carried out on its own, with its own
  targets: another chosen mode targeting a different player does not change
  who creates the token.

Prismari Command is the listed card ("Target player creates a Treasure
token."). Ashling's Command ("Target player creates two Treasure tokens." - a
count on a predefined token) and Verdant Command ("Target player creates two
tapped 1/1 green Squirrel creature tokens." - a tapped rider) are the second
printings proving the reader.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario


def _treasures(scenario, username: str) -> list:
    return [
        state
        for state in scenario.game.battlefield
        if state.name == "Treasure Token" and state.controller == username
    ]


def _board(hand: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=hand,
            library=["Island"] * 5,
            battlefield=["Island", "Island", "Mountain", "Mountain", "Forest", "Forest"],
        )
        .player(
            "bob",
            library=["Forest"] * 5,
            hand=["Grizzly Bears", "Grizzly Bears"],
            battlefield=["Grizzly Bears", "Sol Ring"],
        )
    )


def _cast_modal(scenario, name: str, modes: list[int], targets: list, *, x_value: int = 0):
    casting = scenario.cast(name, username="alice")
    casting.choose_modes(modes, x_value=x_value)
    casting.choose_targets(targets)
    payment = casting.determine_cost()
    scenario.auto_pay(payment, username="alice")
    casting.begin_paying()
    casting.cast()
    scenario.pass_until_resolved()


def test_prismari_command_treasure_goes_to_the_targeted_opponent():
    """Damage mode + Treasure mode, both aimed at bob: the Treasure is bob's."""
    scenario = _board(["Prismari Command"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    _cast_modal(scenario, "Prismari Command", [1, 3], [bears, "bob"])

    assert bears.zone is Zone.GRAVEYARD
    assert len(_treasures(scenario, "bob")) == 1
    assert _treasures(scenario, "alice") == []
    (treasure,) = _treasures(scenario, "bob")
    assert treasure.owner == "bob"


def test_prismari_command_treasure_to_the_caster_with_damage_to_the_opponent():
    """Damage mode targets bob the player, Treasure mode targets alice: each
    mode reads its own target, so bob takes 2 and alice gets the Treasure."""
    scenario = _board(["Prismari Command"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob_life = scenario.player("bob").life

    _cast_modal(scenario, "Prismari Command", [1, 3], ["bob", "alice"])

    assert scenario.player("bob").life == bob_life - 2
    assert len(_treasures(scenario, "alice")) == 1
    assert _treasures(scenario, "bob") == []


def test_prismari_command_loot_one_player_treasure_the_other():
    """Draw-two-discard-two targets alice, the Treasure targets bob (CR 700.2):
    the two "target player" modes do not share their target."""
    scenario = _board(["Prismari Command", "Lightning Bolt", "Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice_hand_before = len(scenario.player("alice").hand)

    bolts = [state for state in scenario.player("alice").hand if state.name == "Lightning Bolt"]
    scenario.will_discard(*bolts, username="alice")
    _cast_modal(scenario, "Prismari Command", [2, 3], ["alice", "bob"])

    # Cast Prismari (-1), drew two (+2), discarded two (-2).
    assert len(scenario.player("alice").hand) == alice_hand_before - 1
    assert all(bolt.zone is Zone.GRAVEYARD for bolt in bolts)
    assert len(_treasures(scenario, "bob")) == 1
    assert _treasures(scenario, "alice") == []


def test_prismari_command_treasure_and_destroy_artifact():
    """Treasure for the caster alongside the artifact-destruction mode."""
    scenario = _board(["Prismari Command"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")

    _cast_modal(scenario, "Prismari Command", [3, 4], ["alice", sol_ring])

    assert sol_ring.zone is Zone.GRAVEYARD
    (treasure,) = _treasures(scenario, "alice")
    assert treasure.card.colors == []


def test_the_targeted_players_treasure_makes_mana_for_that_player():
    """CR 111.10a's own ability works for whoever got the token: bob taps and
    sacrifices it for one mana of any color."""
    scenario = _board(["Prismari Command"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_modal(scenario, "Prismari Command", [1, 3], [bears, "bob"])
    (treasure,) = _treasures(scenario, "bob")
    scenario.pass_priority("alice")  # CR 605.3a: bob activates it with priority

    scenario.activate(treasure, username="bob", color=Color.GREEN)

    assert treasure.zone is not Zone.BATTLEFIELD
    assert scenario.player("bob").mana_pool.floating == {Color.GREEN: 1}


def test_ashlings_command_two_treasures_to_the_target_player():
    """A count on a predefined token: "creates two Treasure tokens", beside a
    draw mode aimed at the other player."""
    scenario = _board(["Ashling's Command"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice_hand = len(scenario.player("alice").hand)
    bob_hand = len(scenario.player("bob").hand)

    _cast_modal(scenario, "Ashling's Command", [2, 4], ["alice", "bob"])

    assert len(_treasures(scenario, "bob")) == 2
    assert _treasures(scenario, "alice") == []
    # Cast Ashling's Command (-1), drew two (+2); bob drew nothing.
    assert len(scenario.player("alice").hand) == alice_hand + 1
    assert len(scenario.player("bob").hand) == bob_hand


def test_verdant_command_squirrels_enter_tapped_under_the_target_player():
    """The tapped rider on a "target player creates" mode."""
    scenario = _board(["Verdant Command"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice_life = scenario.player("alice").life

    _cast_modal(scenario, "Verdant Command", [1, 4], ["bob", "alice"])

    squirrels = [state for state in scenario.game.battlefield if state.name == "Squirrel Token"]
    assert len(squirrels) == 2
    assert all(state.controller == "bob" and state.tapped for state in squirrels)
    assert all((state.power, state.toughness) == (1, 1) for state in squirrels)
    assert all(state.card.colors == [Color.GREEN] for state in squirrels)
    assert scenario.player("alice").life == alice_life + 3
