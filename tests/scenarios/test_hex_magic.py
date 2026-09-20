"""Hex Magic: "Exile all the cards from your hand, then draw that many
cards. Until the end of your next turn, you may play cards exiled this way."

The duration is the reason this card needed a new primitive rather than
reusing Ugin, Eye of the Storms' or Ragavan, Nimble Pilferer's own "until end
of turn" `PlayPermission` grant: CR 611.2a's "until the end of your next
turn" (a continuous effect "lasts as long as stated by the spell or ability
creating it") outlives the turn it was granted on, so `PlayPermission.
until_next_turn_of` was added (mirroring `machines.layers.ContinuousEffect.
until_next_turn_of` and `machines.casting_restrictions.CastingRuleEffect.
until_next_turn_of`, both already built for Karn, the Great Creator's own
`+1` and Teferi, Time Raveler's own `+1`) and dropped from `Game.
begin_turn_for` at the same moment those two are, rather than from `Game.
cleanup_step`'s plain "until end of turn" sweep.

CR numbers looked up with `knowledge_search(q="...", type="rules")` in the
session that wrote this file: CR 601.3, CR 611.2a, CR 121.1 (draw).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from


def board() -> Scenario:
    return (
        Scenario()
        .automatic_turn_based_actions()
        .player(
            "alice",
            hand=["Hex Magic", "Lightning Bolt", "Grizzly Bears"],
            library=["Mountain"] * 20,
            battlefield=["Mountain"] * 5,
        )
        .player("bob", life=20, library=["Mountain"] * 20)
    )


def test_the_rest_of_the_hand_is_exiled_and_that_many_cards_are_drawn():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")

    scenario.cast_and_resolve("Hex Magic", *sources)

    bolt = scenario.find("Lightning Bolt", Zone.EXILE)
    bears = scenario.find("Grizzly Bears", Zone.EXILE)
    assert bolt.zone is Zone.EXILE
    assert bears.zone is Zone.EXILE
    # Two cards exiled (Lightning Bolt, Grizzly Bears - Hex Magic itself was
    # already on the stack, not in hand, when this counted), so two drawn.
    assert len(alice.hand) == 2
    assert all(card.name == "Mountain" for card in alice.hand)


def test_each_exiled_card_gets_a_permission_to_play_it():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")

    scenario.cast_and_resolve("Hex Magic", *sources)

    bolt = scenario.find("Lightning Bolt", Zone.EXILE)
    bears = scenario.find("Grizzly Bears", Zone.EXILE)
    for card in (bolt, bears):
        permission = scenario.game.play_permission_for(card, "alice", PlayAction.PLAY)
        assert permission is not None
        assert permission.pays_mana_cost is True
        assert permission.zone is Zone.EXILE
        assert permission.until_next_turn_of == "alice"


def test_an_exiled_card_can_actually_be_played():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Hex Magic", *sources)

    bolt = scenario.find("Lightning Bolt", Zone.EXILE)
    casting = scenario.cast("Lightning Bolt", from_zone=Zone.EXILE)
    casting.use_permission()
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    (source,) = scenario.untapped_sources("Mountain")
    payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)

    assert bolt.zone is Zone.STACK


def test_the_permission_survives_this_turns_cleanup():
    """Unlike a plain "until end of turn" grant, "until the end of your next
    turn" is still good after this turn's own cleanup step."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Hex Magic", *sources)
    bolt = scenario.find("Lightning Bolt", Zone.EXILE)

    while scenario.step is not Step.CLEANUP:
        scenario.advance()

    assert scenario.game.play_permission_for(bolt, "alice", PlayAction.PLAY) is not None


def test_the_permission_ends_when_alices_next_turn_begins():
    """CR 611.2a: the stated duration ends the moment alice's next turn
    starts, not before."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Hex Magic", *sources)
    bolt = scenario.find("Lightning Bolt", Zone.EXILE)

    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    scenario.advance()  # crosses into bob's turn
    assert scenario.turn.active_player == "bob"
    while scenario.turn.active_player != "alice":
        scenario.advance()

    assert scenario.game.play_permission_for(bolt, "alice", PlayAction.PLAY) is None
