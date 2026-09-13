"""A card that moves from a public zone to its owner's hand is known to every
player until it leaves that hand.

This is **a knowledge policy, not a Comprehensive Rules rule**, and it extends
the one `test_known_card_drawn_stays_known.py` already documents. CR 400.2
makes the graveyard, battlefield, stack and exile public zones - "zones in
which all players can see the cards' faces" - so every player saw the card
there, and saw it go to the hand. CR 400.7 makes the card in hand a new object,
and CR 402.3 ("A player can't look at the cards in another player's hand") says
nothing about a player who watched it arrive. So the move itself records the
card as known to every player, and the record ends the way every record ends:
the card's next zone change.

A card exiled face down was never seen (CR 406.3), so it carries nothing.

Raise Dead (graveyard), Boomerang Basics (battlefield bounce) and Ragavan,
Nimble Pilferer's dash return (CR 702.109a) are the three moves covered here.

Every CR number above was read in full from `mise run rules:find` in the
session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Game, Zone

from .harness import Scenario


def known(game: Game, viewer: str) -> list[tuple[str, Zone, bool]]:
    return sorted((entry.card_name, entry.zone, entry.carried) for entry in game.known_to(viewer))


def test_a_creature_card_returned_from_the_graveyard_is_known_to_the_opponent():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Raise Dead"],
            battlefield=["Swamp"],
            graveyard=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    scenario.cast_and_resolve("Raise Dead", *scenario.untapped_sources("Swamp"), targets=[bears])

    assert bears.zone is Zone.HAND
    assert known(scenario.game, "bob") == [("Grizzly Bears", Zone.HAND, True)]


def test_the_returned_card_stops_being_known_once_it_is_cast():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Raise Dead"],
            battlefield=["Swamp", "Forest", "Forest"],
            graveyard=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.cast_and_resolve("Raise Dead", *scenario.untapped_sources("Swamp"), targets=[bears])

    scenario.cast_and_resolve("Grizzly Bears", *scenario.untapped_sources("Forest", "Forest"))

    assert known(scenario.game, "bob") == []


def test_a_bounced_permanent_is_known_in_its_owners_hand():
    scenario = (
        Scenario()
        .player("alice", hand=["Boomerang Basics"], battlefield=["Island"], library=["Island"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve(
        "Boomerang Basics", *scenario.untapped_sources("Island"), targets=[bears]
    )

    assert bears.zone is Zone.HAND
    assert ("Grizzly Bears", Zone.HAND, True) in known(scenario.game, "alice")


def test_a_dashed_creature_returned_at_end_step_is_known_to_the_opponent():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Ragavan, Nimble Pilferer"], battlefield=["Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Ragavan, Nimble Pilferer")
    casting.use_keyword("Dash")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    ragavan = scenario.resolve_top()

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert ragavan.zone is Zone.HAND
    assert known(scenario.game, "bob") == [("Ragavan, Nimble Pilferer", Zone.HAND, True)]


def test_a_card_drawn_from_the_library_is_still_not_known():
    """The control: a hidden-zone move with no live record carries nothing."""
    scenario = Scenario().player("alice", library=["Grizzly Bears"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.draw()

    assert known(scenario.game, "bob") == []
