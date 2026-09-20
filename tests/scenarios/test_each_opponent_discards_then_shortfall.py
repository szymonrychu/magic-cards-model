""" "Each opponent discards N cards[, then| . For each opponent who didn't
discard N nonland cards this way, ]<consequence>." Two sibling whole-text
parsers sharing `_each_opponent_discards_and_count_shortfalls` (the shared
antecedent) in `machines/effects.py`:

- `_parse_each_opponent_discards_then_draw_per_shortfall_whole_text` - the
  ability's own controller draws one card per shortfall opponent. **Garruk,
  Veiled Butcher**'s own `-3`: "Each opponent discards two cards. For each
  opponent who didn't discard two nonland cards this way, you draw a card."
- `_parse_each_opponent_discards_then_shortfall_loses_life_whole_text` - each
  shortfall opponent loses life *themselves*. **Kroxa, Titan of Death's
  Hunger**'s own enters-or-attacks trigger: "each opponent discards a card,
  then each opponent who didn't discard a nonland card this way loses 3
  life."

CR 701.9b: by default the discarding player chooses which card(s) to
discard. CR 609.3: an effect that attempts something impossible does only as
much as possible, so a hand shorter than the printed count discards what it
has - which is exactly what makes "didn't discard N nonland cards" a real,
per-opponent shortfall rather than a fixed penalty: an opponent who discards
a land and a spell can still fall short of the nonland count, the same as an
opponent with too few cards to discard at all.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file: CR 701.9b, 609.3, 608.2c.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

GARRUK = "Garruk, Veiled Butcher"
KROXA = "Kroxa, Titan of Death's Hunger"


# -- Garruk, Veiled Butcher's own -3: a draw per shortfall opponent -----------


def _garruk_board(bob_hand: list[str]) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[GARRUK], library=["Mountain", "Mountain"])
        .player("bob", hand=bob_hand)
    )


def test_an_opponent_who_discards_two_nonland_cards_causes_no_draw():
    scenario = _garruk_board(["Lightning Bolt", "Llanowar Elves"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    garruk = scenario.find(GARRUK, Zone.BATTLEFIELD, "alice")
    bob = scenario.player("bob")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    elves = scenario.find("Llanowar Elves", Zone.HAND, "bob")
    alice_hand_before = len(scenario.player("alice").hand)
    scenario.will_choose_cards(bolt, elves, username="bob", source=GARRUK)

    scenario.activate(garruk, index=2, username="alice")  # -3
    scenario.pass_until_resolved()

    assert bob.hand == []
    assert bolt.zone is Zone.GRAVEYARD
    assert elves.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == alice_hand_before


def test_an_opponent_who_can_only_discard_a_land_causes_exactly_one_draw():
    scenario = _garruk_board(["Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    garruk = scenario.find(GARRUK, Zone.BATTLEFIELD, "alice")
    bob = scenario.player("bob")
    forest = scenario.find("Forest", Zone.HAND, "bob")
    alice_hand_before = len(scenario.player("alice").hand)
    scenario.will_choose_cards(forest, username="bob", source=GARRUK)

    scenario.activate(garruk, index=2, username="alice")  # -3
    scenario.pass_until_resolved()

    assert bob.hand == []
    assert forest.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == alice_hand_before + 1


def test_an_opponent_with_an_empty_hand_causes_exactly_one_draw():
    scenario = _garruk_board([]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    garruk = scenario.find(GARRUK, Zone.BATTLEFIELD, "alice")
    alice_hand_before = len(scenario.player("alice").hand)

    scenario.activate(garruk, index=2, username="alice")  # -3
    scenario.pass_until_resolved()

    assert len(scenario.player("alice").hand) == alice_hand_before + 1


# -- Kroxa, Titan of Death's Hunger: shortfall opponents lose life themselves -


def _kroxa_board(bob_hand: list[str]) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[KROXA], battlefield=["Swamp", "Mountain"], life=20)
        .player("bob", hand=bob_hand, life=20)
    )


def _resolve_stack(scenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def test_an_opponent_who_discards_a_nonland_card_takes_no_life_loss():
    """Kroxa's own "enters, sacrifice it unless it escaped" trigger fires
    alongside the enters-or-attacks trigger; it does not disturb the
    discard/life-loss half (CR 113.7a: each ability is independent once it
    exists on the stack)."""
    scenario = _kroxa_board(["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    scenario.will_choose_cards(bolt, username="bob", source=KROXA)

    scenario.cast_onto_stack(KROXA, *scenario.untapped_sources("Swamp", "Mountain"))
    _resolve_stack(scenario)

    assert bolt.zone is Zone.GRAVEYARD
    assert bob.life == 20


def test_an_opponent_who_can_only_discard_a_land_loses_exactly_three_life():
    scenario = _kroxa_board(["Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    forest = scenario.find("Forest", Zone.HAND, "bob")
    scenario.will_choose_cards(forest, username="bob", source=KROXA)

    scenario.cast_onto_stack(KROXA, *scenario.untapped_sources("Swamp", "Mountain"))
    _resolve_stack(scenario)

    assert forest.zone is Zone.GRAVEYARD
    assert bob.life == 17


def test_an_opponent_with_an_empty_hand_loses_exactly_three_life():
    scenario = _kroxa_board([]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")

    scenario.cast_onto_stack(KROXA, *scenario.untapped_sources("Swamp", "Mountain"))
    _resolve_stack(scenario)

    assert bob.life == 17
