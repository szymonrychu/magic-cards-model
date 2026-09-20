"""FRA stream S8 (outside the game): "You may reveal exactly two cards you
own with different names from outside the game. An opponent chooses one of
them. You put that card into your hand." - Extrapolate the Impossible's own
whole effect.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 400.11a/400.11c** - a sideboard is outside the game; cards there
  can't be affected except by spells and abilities that bring them in.
- **CR 108.3b** - only a card's own owner may bring it in.
- **CR 701.20a/701.20b** - revealing shows the card without moving it.
- **CR 608.2d** - the "you may" gates the whole instruction; the choice of
  *which* opponent makes the second choice is CR 102.2's - a single-
  opponent game (the only shape this engine plays) has exactly one to ask.

Extrapolate the Impossible is the reported card, and this stream's own
first read of the "an opponent chooses one of `<the candidates>`" idiom -
the choosing player is not the resolving spell's own controller, the same
general `_opponents`/`game.ask` shape `_EACH_OPPONENT_CHOOSE_ONE_OF_EACH_
TYPE_THEN_SACRIFICE_RE` already uses elsewhere in this file for a different
sentence, not new architecture. No other printing pairs "reveal ... from
outside the game" with "an opponent chooses one of them" (searched via the
Scryfall API in the session that wrote this file) - the nearest real
templates (Karn, Scion of Urza's own "+1", Burning-Rune Demon's own ETB)
read the identical "opponent chooses one of them" idiom off the *library*
rather than outside the game, a different search space this stream's own
scope does not reach into - so the off-set half of this file proves the
shared choosing idiom on a second, already-in-the-pool card instead of a
second full copy of this one sentence.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_extrapolate_the_impossible_lets_the_opponent_choose_which_card_alice_gets():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Extrapolate the Impossible"],
            battlefield=["Swamp", "Swamp"],
            sideboard=["Grafdigger's Cage", "Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Swamp", "Swamp")
    (cage,) = [state for state in alice.outside_the_game if state.name == "Grafdigger's Cage"]
    (bolt,) = [state for state in alice.outside_the_game if state.name == "Lightning Bolt"]

    scenario.will_take_the_may(True, source="Extrapolate the Impossible")
    scenario.will_choose_cards(cage, bolt, username="alice")
    scenario.will_choose_cards(bolt, username="bob")
    scenario.cast_and_resolve("Extrapolate the Impossible", *sources)

    assert bolt.zone is Zone.HAND, "bob's own choice is the one that reaches alice's hand"
    assert cage.zone is Zone.SIDEBOARD, "the other stays outside the game"
    (cage_reveal,) = [r for r in scenario.game.reveals if r.card_name == "Grafdigger's Cage"]
    (bolt_reveal,) = [r for r in scenario.game.reveals if r.card_name == "Lightning Bolt"]
    assert cage_reveal.zone is Zone.SIDEBOARD
    assert bolt_reveal.zone is Zone.SIDEBOARD


def test_declining_the_may_reveals_nothing():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Extrapolate the Impossible"],
            battlefield=["Swamp", "Swamp"],
            sideboard=["Grafdigger's Cage", "Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Swamp", "Swamp")

    scenario.will_take_the_may(False, source="Extrapolate the Impossible")
    scenario.cast_and_resolve("Extrapolate the Impossible", *sources)

    assert scenario.game.reveals == []
    assert len(alice.outside_the_game) == 2
