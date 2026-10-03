"""Legion Angel: "When this creature enters, you may reveal a card you own named
Legion Angel from outside the game and put it into your hand."

Outside the game is the player's sideboard (CR 400.11a); CR 108.3b limits the
reach to cards the player owns, CR 701.20a makes the reveal public, CR 608.2d
makes the "you may" a choice made as the ability resolves. "Named Legion Angel"
is read off the sentence, so only a card with that name qualifies.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def board(sideboard: list[str] | None = None, bobs_sideboard: list[str] | None = None):
    return (
        Scenario()
        .player(
            "alice",
            hand=["Legion Angel"],
            battlefield=["Plains"] * 4,
            sideboard=sideboard,
        )
        .player("bob", sideboard=bobs_sideboard)
        .build()
    )


def cast_angel(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")
    scenario.cast_and_resolve("Legion Angel", *sources)
    scenario.pass_until_resolved()


def test_the_enters_trigger_brings_a_second_angel_in_from_the_sideboard():
    scenario = board(sideboard=["Legion Angel", "Lightning Bolt"])
    alice = scenario.player("alice")
    (spare,) = [s for s in alice.outside_the_game if s.name == "Legion Angel"]
    scenario.will_take_the_may(True, source="Legion Angel")
    cast_angel(scenario)
    assert spare.zone is Zone.HAND
    (reveal,) = scenario.game.reveals
    assert reveal.zone is Zone.SIDEBOARD
    assert [s.name for s in alice.outside_the_game] == ["Lightning Bolt"]


def test_declining_leaves_the_card_outside_the_game():
    scenario = board(sideboard=["Legion Angel"])
    alice = scenario.player("alice")
    (spare,) = list(alice.outside_the_game)
    scenario.will_take_the_may(False, source="Legion Angel")
    cast_angel(scenario)
    assert spare.zone is Zone.SIDEBOARD
    assert scenario.game.reveals == []


def test_without_a_sideboard_nothing_happens_and_no_question_is_asked():
    scenario = board()
    cast_angel(scenario)
    assert scenario.game.reveals == []
    assert scenario.questions_asked() == []
    assert [s.name for s in scenario.player("alice").hand] == []


def test_a_sideboard_without_the_named_card_gives_nothing_to_take():
    scenario = board(sideboard=["Lightning Bolt", "Grizzly Bears"])
    cast_angel(scenario)
    assert scenario.game.reveals == []
    assert scenario.player("alice").hand == []


def test_an_opponents_sideboard_copy_is_not_yours_to_take():
    scenario = board(bobs_sideboard=["Legion Angel"])
    cast_angel(scenario)
    assert scenario.player("alice").hand == []
    assert [s.zone for s in scenario.player("bob").outside_the_game] == [Zone.SIDEBOARD]
