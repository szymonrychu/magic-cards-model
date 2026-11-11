"""Scenario: cards exiled face down from a library, played by whoever the
effect names, with mana of any type (Vulcan Mind-Meld; Outrageous Robbery as
the differently-worded proof).

CR 406.3: a card exiled face down can be examined only as instructions allow -
each exiler looks at what it exiles; CR 406.3a: the effect may allow it to be
played, and it is turned face up just before; CR 601.3: the permission is the
effect's; CR 400.7: it lasts while the card stays in exile. "Mana of any type
can be spent" lets any mana pay the coloured symbols.

Vulcan Mind-Meld: "Target opponent looks at the top card of your library, then
exiles it face down. You look at the top two cards of their library, then
exile them face down. For each card exiled this way, the player who exiled it
may play it for as long as it remains exiled. Mana of any type can be spent to
cast spells this way."

CR rules cited here were looked up with `mise run rules:find` in the writing
session.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import Scenario


def mind_meld_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Vulcan Mind-Meld"],
            battlefield=["Island", "Island", "Island"],
            library=["Lightning Bolt", "Island"],
        )
        .player("bob", battlefield=["Forest"], library=["Forest", "Grizzly Bears", "Swamp"])
    )


def mind_meld(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice, bob = scenario.player("alice"), scenario.player("bob")
    bolt = alice.library[0]
    forest, bears, swamp = bob.library[:3]
    scenario.cast_and_resolve(
        "Vulcan Mind-Meld", *scenario.untapped_sources("Island"), targets=["bob"]
    )
    return bolt, forest, bears, swamp


def test_each_side_exiles_face_down_and_knows_only_its_own_cards():
    scenario = mind_meld_board().build()
    bolt, forest, bears, swamp = mind_meld(scenario)
    assert [card.zone for card in (bolt, forest, bears)] == [Zone.EXILE] * 3
    assert not any(card.face_up for card in (bolt, forest, bears))
    assert swamp.zone is Zone.LIBRARY, "only the top two of bob's library"
    assert scenario.game.play_permission_for(bolt, "bob") is not None
    assert scenario.game.play_permission_for(bolt, "alice") is None
    assert scenario.game.play_permission_for(bears, "alice") is not None
    assert scenario.game.play_permission_for(bears, "bob") is None


def test_alice_plays_bobs_land_and_casts_his_creature_with_blue_mana():
    scenario = mind_meld_board().build()
    _bolt, forest, bears, _swamp = mind_meld(scenario)
    land = scenario.game.play_land(forest, "alice")
    assert land.zone is Zone.BATTLEFIELD and land.controller == "alice"
    casting = scenario.cast("Grizzly Bears", from_zone=Zone.EXILE)
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Island", "Island"))
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()
    assert scenario.creature("Grizzly Bears", "alice").owner == "bob"


def test_bob_casts_alices_card_with_his_own_mana():
    scenario = mind_meld_board().build()
    bolt, *_ = mind_meld(scenario)
    while scenario.turn.active_player != "bob":
        scenario.advance()
    while scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()
    casting = scenario.cast("Lightning Bolt", "bob", from_zone=Zone.EXILE, targets=["alice"])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Forest", username="bob"))
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 17
    assert bolt.zone is Zone.GRAVEYARD and bolt.owner == "alice"


def test_outrageous_robbery_exiles_x_face_down_for_you_to_play():
    """The proof: the opponent exiles the top X cards of their own library;
    only the caster may look at and play them, spending mana as though it were
    of any type."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Outrageous Robbery"],
            battlefield=["Swamp"] * 4 + ["Island", "Island"],
        )
        .player("bob", library=["Grizzly Bears", "Forest", "Swamp"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears, forest, swamp = scenario.player("bob").library[:3]
    casting = scenario.cast("Outrageous Robbery", targets=["bob"])
    casting.x_value = 2
    casting.determine_cost(x_value=2)
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Swamp"] * 4))
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()
    assert [card.zone for card in (bears, forest, swamp)] == [Zone.EXILE, Zone.EXILE, Zone.LIBRARY]
    assert scenario.game.play_permission_for(bears, "bob") is None
    casting = scenario.cast("Grizzly Bears", from_zone=Zone.EXILE)
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Island", "Island"))
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()
    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD


def test_vulcan_mind_meld_with_an_empty_library_exiles_what_there_is():
    scenario = (
        Scenario()
        .player("alice", hand=["Vulcan Mind-Meld"], battlefield=["Island"], library=[])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.player("bob").library[0]
    scenario.cast_and_resolve(
        "Vulcan Mind-Meld", *scenario.untapped_sources("Island"), targets=["bob"]
    )
    assert forest.zone is Zone.EXILE
    assert scenario.game.play_permission_for(forest, "alice") is not None
