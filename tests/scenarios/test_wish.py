"""Wish: "You may play a card you own from outside the game this turn."

The printed "this turn" window rules out reusing Karn, the Great Creator's own
"−2" shape (`test_outside_the_game.py`), which puts the fetched card straight
into hand - CR 400.11b leaves a brought-in card "in the game" indefinitely
once it is an ordinary object of its new zone, and a card sitting in hand
needs no permission to cast at all (`why_cannot_cast_from`'s own `zone is
Zone.HAND` fast path), so "this turn" would silently become "forever" the
moment the turn ended. Wish instead brings the chosen card into **exile**
and hands out an ordinary CR 601.3 `PlayPermission` there, good only until
end of turn - the same "exile it, then permit it until end of turn" idiom
Ugin, Eye of the Storms' `−11` and Ragavan, Nimble Pilferer's trigger already
use, applied to a card that starts outside the game rather than in a library.

CR numbers looked up with `knowledge_search(q="...", type="rules")` in the
session that wrote this file: CR 400.11a, CR 400.11b, CR 400.11c, CR 108.3b,
CR 601.3, CR 608.2d, CR 701.20a.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from


def board(sideboard: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Wish"],
            battlefield=["Mountain", "Mountain", "Mountain"],
            sideboard=sideboard,
        )
        .player("bob", life=20)
    )


def test_wish_brings_the_chosen_card_into_exile_with_a_permission_to_play_it():
    scenario = board(sideboard=["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    (bolt,) = [state for state in alice.outside_the_game if state.name == "Lightning Bolt"]
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")

    scenario.will_choose_cards(bolt, username="alice", source="Wish")
    scenario.cast_and_resolve("Wish", *sources)

    assert bolt.zone is Zone.EXILE
    permission = scenario.game.play_permission_for(bolt, "alice", PlayAction.PLAY)
    assert permission is not None
    assert permission.pays_mana_cost is True
    assert permission.zone is Zone.EXILE


def test_the_wished_for_card_can_actually_be_cast():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Wish"],
            battlefield=["Mountain"] * 4,
            sideboard=["Lightning Bolt"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    (bolt,) = [state for state in alice.outside_the_game if state.name == "Lightning Bolt"]
    wish_sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")

    scenario.will_choose_cards(bolt, username="alice", source="Wish")
    scenario.cast_and_resolve("Wish", *wish_sources)

    casting = scenario.cast("Lightning Bolt", from_zone=Zone.EXILE)
    casting.use_permission()
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    (bolt_source,) = scenario.untapped_sources("Mountain")
    payment.tap_for_mana(bolt_source, mana_from(bolt_source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.player("bob").life == 17


def test_with_nothing_owned_outside_the_game_wish_does_nothing():
    """CR 608.2d: no legal option, so the whole instruction quietly has
    nothing to act on - no permission is created for anything."""
    scenario = board(sideboard=[]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")

    wish = scenario.cast_and_resolve("Wish", *sources)

    assert wish.zone is Zone.GRAVEYARD
    assert scenario.game.play_permissions == []


def test_declining_the_may_leaves_the_card_outside_the_game():
    scenario = board(sideboard=["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    (bolt,) = [state for state in alice.outside_the_game if state.name == "Lightning Bolt"]
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")

    scenario.will_take_the_may(False, source="Wish")
    scenario.cast_and_resolve("Wish", *sources)

    assert bolt.zone is Zone.SIDEBOARD
    assert scenario.game.play_permissions == []


def test_an_opponents_sideboard_card_cannot_be_wished_for():
    """CR 108.3b: "cards **they own**" - bob's own sideboard is not alice's
    to reach into, so Wish offers nothing when only an opponent's cards sit
    outside the game."""
    scenario = (
        Scenario()
        .player("alice", hand=["Wish"], battlefield=["Mountain", "Mountain", "Mountain"])
        .player("bob", life=20, sideboard=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")

    scenario.cast_and_resolve("Wish", *sources)

    assert scenario.game.play_permissions == []
    bob = scenario.player("bob")
    assert [state.name for state in bob.outside_the_game] == ["Lightning Bolt"]


def test_the_permission_expires_at_the_end_of_the_turn():
    """The permission is bounded by "this turn" (CR 514.2's own "until end
    of turn" sweep), unlike Karn's shape which never expires because it puts
    the card straight into hand."""
    scenario = board(sideboard=["Lightning Bolt"]).automatic_turn_based_actions().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    (bolt,) = [state for state in alice.outside_the_game if state.name == "Lightning Bolt"]
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")

    scenario.will_choose_cards(bolt, username="alice", source="Wish")
    scenario.cast_and_resolve("Wish", *sources)
    assert scenario.game.play_permission_for(bolt, "alice", PlayAction.PLAY) is not None

    while scenario.step is not Step.CLEANUP:
        scenario.advance()

    assert scenario.game.play_permission_for(bolt, "alice", PlayAction.PLAY) is None
    assert bolt.zone is Zone.EXILE, "unclaimed - CR 400.11b leaves it in the game"
