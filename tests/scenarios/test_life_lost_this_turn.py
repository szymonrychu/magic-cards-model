"""How much life a player has lost this turn, counted gross.

Children of Korlis (verified with `resolve_cards`): "Sacrifice this creature:
You gain life equal to the life you've lost this turn. (Damage causes loss of
life.)" The reminder text names damage only; every route by which a life total
goes down feeds the same number.

- **CR 119.3** - "If an effect causes a player to gain life or lose life, that
  player's life total is adjusted accordingly." One rule, and `Player.
  lose_life` is the one place in this engine that implements it.
- **CR 119.2** - "Damage dealt to a player normally causes that player to lose
  that much life", so damage is a life loss and is counted here.
- **CR 118.3b** - "Paying life is done by subtracting the indicated amount of
  life from a player's life total", so a life *cost* is a life loss too. That
  is DDR#958's whole point.
- **CR 701.12c** - an exchange of life totals is implemented as gains and
  losses, so the losing half counts as well.

Gross, not net: a player who loses 4 and gains 4 has still lost 4 this turn.
Nothing in the rules subtracts the gain back out.

The counter is per turn and clears itself when the turn changes, the way
`Game.spells_cast_this_turn` and `Game.life_gained_this_turn` are cleared at
the turn boundary. It hangs off `TurnMachine.turns_taken` rather than the turn
number because CR 500.7's extra turn moves neither the seat nor the number -
the same signal `Game.advance` and `PlayPermission.expired` already use.

Every CR number in this file was verified with `knowledge_search(q="...",
type="rules")` in the session that wrote it: CR 118.3b, CR 119.2, CR 119.3,
CR 500.7, CR 701.12c.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.mana import Color
from magic_cards_model.models.player import Player
from tests.scenarios.harness import Scenario


def bolt_and_confluence() -> Scenario:
    """DDR#958's board: alice can be Bolted and can pay life to a land."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mana Confluence"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_nothing_lost_is_zero_lost():
    """The baseline, so a later non-zero is not just an uninitialised field."""
    scenario = bolt_and_confluence()

    assert scenario.player("alice").life_lost_this_turn == 0


def test_damage_to_a_player_is_life_lost():
    """CR 119.2: three damage is three life lost."""
    scenario = bolt_and_confluence()
    alice = scenario.player("alice")
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=["alice"],
    )

    assert alice.life == 17
    assert alice.life_lost_this_turn == 3


def test_paying_life_as_a_cost_is_life_lost_too():
    """CR 118.3b, and DDR#958's ruling: 3 damage plus 1 paid is 4 lost.

    Mana Confluence prints "{T}, Pay 1 life: Add one mana of any color.", and
    the payment goes through `Player.lose_life` like everything else.
    """
    scenario = bolt_and_confluence()
    alice = scenario.player("alice")
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=["alice"],
    )
    confluence = scenario.find("Mana Confluence", Zone.BATTLEFIELD, "alice")
    scenario.activate(confluence, username="alice", color=Color.GREEN)

    assert alice.life == 16
    assert alice.life_lost_this_turn == 4


def test_the_count_is_gross_rather_than_net():
    """A gain does not pay the loss back off.

    Losing 5 and gaining 5 leaves the life total where it started and the
    life *lost* this turn at 5 - "the life you've lost this turn" is not
    "how far down you are".
    """
    scenario = bolt_and_confluence()
    alice = scenario.player("alice")

    alice.lose_life(5)
    alice.gain_life(5)

    assert alice.life == 20
    assert alice.life_lost_this_turn == 5


def test_losses_accumulate_within_the_turn():
    """Several separate losses add up rather than replacing each other."""
    scenario = bolt_and_confluence()
    alice = scenario.player("alice")

    alice.lose_life(2)
    alice.lose_life(3)

    assert alice.life_lost_this_turn == 5


def test_losing_zero_life_counts_nothing():
    """`lose_life(0)` is a legal no-op (CR 118.3b permits paying 0), and it
    must not register as a loss."""
    scenario = bolt_and_confluence()
    alice = scenario.player("alice")

    alice.lose_life(0)

    assert alice.life_lost_this_turn == 0


def test_the_count_clears_when_the_turn_changes():
    """ "This turn" means this one. The counter is stamped with
    `TurnMachine.turns_taken` and reads as zero once that moves on."""
    scenario = bolt_and_confluence()
    alice = scenario.player("alice")
    alice.lose_life(4)

    assert alice.life_lost_this_turn == 4

    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()

    assert alice.life_lost_this_turn == 0


def test_a_loss_after_the_turn_changes_starts_the_count_again():
    """The clear is not a one-way latch: the new turn counts its own losses."""
    scenario = bolt_and_confluence()
    alice = scenario.player("alice")
    alice.lose_life(4)

    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()

    alice.lose_life(1)

    assert alice.life_lost_this_turn == 1


def test_it_is_counted_per_player():
    """One player's losses are not the other's."""
    scenario = bolt_and_confluence()
    alice, bob = scenario.player("alice"), scenario.player("bob")

    alice.lose_life(3)

    assert alice.life_lost_this_turn == 3
    assert bob.life_lost_this_turn == 0


def test_a_player_outside_a_game_still_counts_its_losses():
    """A `Player` built on its own has no turn to be stamped against, so
    nothing ever clears the count - which is the honest answer for an object
    with no turn structure around it, and keeps the field readable in the unit
    tests that build a player directly."""
    player = Player(username="solo")

    player.lose_life(6)

    assert player.life_lost_this_turn == 6


def test_children_of_korlis_reads_the_ledger():
    """DDR#958 end to end: 4 lost, 4 gained back."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mana Confluence", "Children of Korlis"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=["alice"],
    )
    confluence = scenario.find("Mana Confluence", Zone.BATTLEFIELD, "alice")
    scenario.activate(confluence, username="alice", color=Color.GREEN)

    children = scenario.find("Children of Korlis", Zone.BATTLEFIELD, "alice")
    scenario.activate(children, username="alice", sacrificing=[children])
    scenario.resolve_top()

    assert alice.life == 20
