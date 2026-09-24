"""Balin, Loremaster's wheel:

    Whenever Balin or another Dwarf you control enters, you may discard your
    hand. Draw X cards, where X is the number of cards discarded this way. If
    you have an enduring story, Balin deals X damage to each opponent.

No other printing legal in Modern, Pioneer or Standard carries "Draw X cards,
where X is the number of cards discarded this way" (the other "you may
discard your hand" cards draw a fixed number "if you do"), so the reader is
proved across Balin's own corner cases - see MEMORY.md.

Every rule cited here was read whole with `mise run rules:find` in the
session that wrote this file:

- **CR 701.9a** - "To discard a card, move it from its owner's hand to that
  player's graveyard." - discarding a hand is that, for every card in it.
- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written" - the discard is counted before the
  draw reads it, and the damage reads the same X.
- **CR 608.2d** - the "you may" is the controller's choice as the ability
  resolves.
- **CR 120.3a** - damage dealt to a player causes that player to lose that
  much life.
- **CR 702.195b** - the enduring story "If you have an enduring story" asks
  about, as the instruction is reached.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

STORY = ["Mox Amber", "Darksteel Relic"]
LIBRARY = ["Plains", "Island", "Mountain", "Plains", "Island"]


def _resolve_all(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()


def _board(hand: list[str], battlefield: list[str] = (), players: int = 2):
    scenario = Scenario().player(
        "alice",
        hand=["Balin, Loremaster", *hand],
        library=list(LIBRARY),
        battlefield=list(battlefield),
    )
    for name in ("bob", "carol")[: players - 1]:
        scenario = scenario.player(name, library=list(LIBRARY))
    return scenario.build()


def _enter_balin(scenario):
    scenario.game.check_state_based_actions()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario.put_onto_battlefield("Balin, Loremaster")


def test_discarding_the_hand_draws_that_many():
    scenario = _board(["Lightning Bolt", "Shock", "Opt"])
    _enter_balin(scenario)
    scenario.will_take_the_may(True)
    _resolve_all(scenario)
    alice = scenario.player("alice")
    assert sorted(card.name for card in alice.graveyard) == ["Lightning Bolt", "Opt", "Shock"]
    assert [card.name for card in alice.hand] == ["Plains", "Island", "Mountain"]
    assert scenario.player("bob").life == 20, "no enduring story, no damage"


def test_declining_keeps_the_hand_and_draws_nothing():
    """X is "the number of cards discarded this way" - none, so zero cards."""
    scenario = _board(["Lightning Bolt", "Shock"])
    _enter_balin(scenario)
    scenario.will_take_the_may(False)
    _resolve_all(scenario)
    alice = scenario.player("alice")
    assert sorted(card.name for card in alice.hand) == ["Lightning Bolt", "Shock"]
    assert alice.graveyard == []
    assert len(alice.library) == len(LIBRARY)


def test_an_empty_hand_discards_nothing_and_draws_nothing():
    scenario = _board([])
    _enter_balin(scenario)
    scenario.will_take_the_may(True)
    _resolve_all(scenario)
    alice = scenario.player("alice")
    assert alice.hand == []
    assert len(alice.library) == len(LIBRARY)


def test_with_a_story_balin_deals_x_to_each_opponent():
    """Balin plus two storied qualifiers: the story is already held when the
    trigger resolves, so the two discarded cards are two damage to each
    opponent - Bob and Carol both."""
    scenario = _board(["Lightning Bolt", "Shock"], battlefield=STORY, players=3)
    _enter_balin(scenario)
    assert scenario.player("alice").has_enduring_story
    scenario.will_take_the_may(True)
    _resolve_all(scenario)
    assert scenario.player("bob").life == 18
    assert scenario.player("carol").life == 18
    assert scenario.player("alice").life == 20, "each opponent - never its controller"
    assert len(scenario.player("alice").hand) == 2


def test_with_a_story_declining_deals_no_damage():
    scenario = _board(["Lightning Bolt", "Shock"], battlefield=STORY)
    _enter_balin(scenario)
    scenario.will_take_the_may(False)
    _resolve_all(scenario)
    assert scenario.player("bob").life == 20


def test_another_dwarf_entering_triggers_balin_too():
    """ "Balin or another Dwarf you control": Ori, Keeper of Songs is a Dwarf,
    and its arrival wheels Alice's hand a second time."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ori, Keeper of Songs", "Lightning Bolt"],
            library=list(LIBRARY),
            battlefield=["Balin, Loremaster"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Ori, Keeper of Songs")
    scenario.will_take_the_may(True)
    _resolve_all(scenario)
    alice = scenario.player("alice")
    assert [card.name for card in alice.graveyard] == ["Lightning Bolt"]
    assert [card.name for card in alice.hand] == ["Plains"]


def test_a_non_dwarf_entering_does_not_trigger_balin():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears", "Lightning Bolt"],
            library=list(LIBRARY),
            battlefield=["Balin, Loremaster"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Grizzly Bears")
    assert scenario.pending_triggers == []
    assert scenario.find("Lightning Bolt", Zone.HAND, "alice") is not None


def test_the_story_is_asked_when_the_damage_is_reached():
    """CR 608.2c: "If you have an enduring story" is checked as that
    instruction is reached, not when the ability triggered. Balin enters as
    the second qualifier (Mox Amber plus Balin) - no story - and the third
    arrives while the trigger waits on the stack, so the damage is dealt."""
    scenario = _board(["Lightning Bolt", "Darksteel Relic"], battlefield=["Mox Amber"])
    _enter_balin(scenario)
    assert not scenario.player("alice").has_enduring_story
    scenario.game.put_triggers_on_stack()
    scenario.put_onto_battlefield("Darksteel Relic")
    assert scenario.player("alice").has_enduring_story
    scenario.will_take_the_may(True)
    _resolve_all(scenario)
    assert scenario.player("bob").life == 19, "one card discarded: X is 1"
    assert [card.name for card in scenario.player("alice").hand] == ["Plains"]


def test_without_a_story_at_resolution_no_damage_is_dealt():
    scenario = _board(["Lightning Bolt"], battlefield=["Mox Amber"])
    _enter_balin(scenario)
    scenario.will_take_the_may(True)
    _resolve_all(scenario)
    assert scenario.player("bob").life == 20
