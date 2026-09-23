"""A group discard that punishes whoever could not discard: "Each player
discards a card. Each opponent who can't loses 3 life." and "each opponent
discards a card. For each opponent who can't, you `<effect>`."

Every CR number below was read whole with `mise run rules:find` in the session
that wrote this file:

- **CR 118.12** - "[Do something]. If [a player] [does, doesn't, or can't],
  [effect]." "Who can't" is the same check, asked of each member of the
  group: a player with no card in hand cannot discard one.
- **CR 701.9b** - each discarding player chooses their own card.
- **CR 608.2c** - the second sentence is read against what the first one
  actually did.

Liliana, Waker of the Dead's `+1` is the reported card: the controller
discards too, but only an opponent is punished. Cruel Grimnarch ("each
opponent discards a card. For each opponent who can't, you gain 4 life.") and
Refurbished Familiar ("... For each opponent who can't, you draw a card.") are
the proof printings - Pioneer/Modern and Modern legal, in no api deck, and the
consequence lands on the controller once per failing opponent rather than on
the opponent.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def liliana_board(alice_hand: list[str], bob_hand: list[str], carol_hand: list[str] | None = None):
    scenario = Scenario().player(
        "alice", hand=alice_hand, battlefield=["Liliana, Waker of the Dead"]
    )
    scenario = scenario.player("bob", hand=bob_hand)
    if carol_hand is not None:
        scenario = scenario.player("carol", hand=carol_hand)
    return scenario.build()


def plus_one(scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)
    liliana = scenario.find("Liliana, Waker of the Dead", Zone.BATTLEFIELD, "alice")
    scenario.activate(liliana, index=0)
    scenario.resolve_top()


def test_an_opponent_with_a_card_discards_it_and_loses_nothing():
    scenario = liliana_board(["Island"], ["Lightning Bolt"])
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")

    plus_one(scenario)

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 20


def test_an_opponent_with_an_empty_hand_loses_three():
    scenario = liliana_board(["Island"], [])

    plus_one(scenario)

    assert scenario.player("bob").life == 17


def test_the_controller_discards_too():
    scenario = liliana_board(["Island"], ["Lightning Bolt"])
    island = scenario.find("Island", Zone.HAND, "alice")

    plus_one(scenario)

    assert island.zone is Zone.GRAVEYARD


def test_the_controller_who_cant_discard_is_not_punished():
    """ "Each opponent who can't" - the controller is a player who discards,
    never an opponent who pays for failing to."""
    scenario = liliana_board([], [])

    plus_one(scenario)

    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 17


def test_each_opponent_is_judged_on_their_own_hand():
    scenario = liliana_board(["Island"], [], carol_hand=["Shock"])
    shock = scenario.find("Shock", Zone.HAND, "carol")

    plus_one(scenario)

    assert scenario.player("bob").life == 17
    assert scenario.player("carol").life == 20
    assert shock.zone is Zone.GRAVEYARD


def test_each_player_chooses_which_card_to_discard():
    scenario = liliana_board(["Island"], ["Lightning Bolt", "Shock"])
    shock = scenario.find("Shock", Zone.HAND, "bob")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    scenario.will_discard(shock, username="bob")

    plus_one(scenario)

    assert shock.zone is Zone.GRAVEYARD
    assert bolt.zone is Zone.HAND
    assert scenario.player("bob").life == 20


def test_the_plus_one_adds_a_loyalty_counter():
    scenario = liliana_board([], [])
    liliana = scenario.find("Liliana, Waker of the Dead", Zone.BATTLEFIELD, "alice")
    before = liliana.counters[Counter.LOYALTY]

    plus_one(scenario)

    assert liliana.counters[Counter.LOYALTY] == before + 1


# -- proof printings: Cruel Grimnarch, Refurbished Familiar -----------------


def enters(name: str, alice_hand: list[str], bob_hand: list[str], carol_hand=None):
    builder = Scenario().player(
        "alice", hand=alice_hand, battlefield=["Swamp"] * 6, library=["Island"] * 3
    )
    builder = builder.player("bob", hand=bob_hand)
    if carol_hand is not None:
        builder = builder.player("carol", hand=carol_hand)
    scenario = builder.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(name, auto=True)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
    return scenario


def test_cruel_grimnarch_gains_four_for_an_opponent_who_cant():
    scenario = enters("Cruel Grimnarch", ["Cruel Grimnarch"], [])

    assert scenario.player("alice").life == 24
    assert scenario.player("bob").life == 20


def test_cruel_grimnarch_gains_nothing_when_the_opponent_discards():
    scenario = enters("Cruel Grimnarch", ["Cruel Grimnarch"], ["Lightning Bolt"])

    assert scenario.player("alice").life == 20
    assert scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob").zone is Zone.GRAVEYARD


def test_cruel_grimnarch_counts_each_failing_opponent():
    scenario = enters("Cruel Grimnarch", ["Cruel Grimnarch"], [], carol_hand=[])

    assert scenario.player("alice").life == 28


def test_cruel_grimnarch_does_not_make_its_controller_discard():
    scenario = enters("Cruel Grimnarch", ["Cruel Grimnarch", "Island"], ["Shock"])

    assert scenario.find("Island", Zone.HAND, "alice").zone is Zone.HAND


def test_refurbished_familiar_draws_for_each_opponent_who_cant():
    scenario = enters("Refurbished Familiar", ["Refurbished Familiar"], [], carol_hand=["Shock"])

    alice = scenario.player("alice")
    assert len(alice.hand) == 1
    assert scenario.find("Shock", Zone.GRAVEYARD, "carol").zone is Zone.GRAVEYARD
