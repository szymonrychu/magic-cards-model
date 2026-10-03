"""Scenario: "exile up to X target creatures. For each of those cards, its
owner may play it for as long as it remains exiled" (Extraordinary Journey's
enters trigger), and its second ability.

    When this enchantment enters, exile up to X target creatures. For each of
    those cards, its owner may play it for as long as it remains exiled.
    Whenever one or more nontoken creatures enter, if one or more of them
    entered from exile or was cast from exile, you draw a card. This ability
    triggers only once each turn.

Rules read whole with `mise run rules:find` in the session that wrote this:

- **CR 107.3** - X on the stack is the announced value; **CR 107.3m** - an
  X in an enters trigger of a permanent reads the X it was cast with.
- **CR 601.3 / 305.1** - the permission lets the owner cast a spell or play
  a land from exile.
- **CR 400.7** - a card that leaves exile is a new object; the permission
  ends with the exile.
- **CR 111.7** - a token that leaves the battlefield ceases to exist, so no
  card remains to be played.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

JOURNEY_LANDS = ["Island"] * 2 + ["Plains"] * 6


def _board(
    *,
    alice=(),
    bob=(),
    x=2,
    bob_lands=("Forest", "Forest"),
    hand=("Extraordinary Journey",),
    bob_hand=(),
):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=list(hand),
            battlefield=[*JOURNEY_LANDS, *alice],
            library=["Plains"] * 8,
        )
        .player("bob", battlefield=[*bob_lands, *bob], hand=list(bob_hand), library=["Plains"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_journey(scenario, x, targets=()):
    """{X}{X}{U}{U}; the enters trigger's targets are queued before it fires."""
    if targets:
        scenario.will_choose_targets(*targets)
    casting = scenario.cast("Extraordinary Journey", "alice")
    payment = casting.determine_cost(x_value=x)
    scenario.pay_with(payment, *scenario.untapped_sources(*(["Island"] * 2 + ["Plains"] * (2 * x))))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()


def test_x_two_exiles_two_and_each_owner_gets_a_permission():
    scenario = _board(alice=["Grizzly Bears"], bob=["Hill Giant", "Runeclaw Bear"])
    mine = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    kept = scenario.creature("Runeclaw Bear", "bob")
    _cast_journey(scenario, 2, [mine, giant])
    assert mine.zone is Zone.EXILE and giant.zone is Zone.EXILE
    assert kept.zone is Zone.BATTLEFIELD
    assert scenario.game.play_permission_for(mine, "alice") is not None
    assert scenario.game.play_permission_for(giant, "bob") is not None
    assert scenario.game.play_permission_for(giant, "alice") is None


def test_x_zero_exiles_nothing():
    scenario = _board(bob=["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")
    _cast_journey(scenario, 0)
    assert giant.zone is Zone.BATTLEFIELD


def test_up_to_x_may_choose_fewer():
    scenario = _board(bob=["Hill Giant", "Runeclaw Bear"])
    giant = scenario.creature("Hill Giant", "bob")
    other = scenario.creature("Runeclaw Bear", "bob")
    _cast_journey(scenario, 2, [giant])
    assert giant.zone is Zone.EXILE and other.zone is Zone.BATTLEFIELD


def test_owner_not_controller_gets_the_permission():
    scenario = _board(bob=["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")
    giant.stored_controller = "alice"
    _cast_journey(scenario, 1, [giant])
    assert scenario.game.play_permission_for(giant, "bob") is not None
    assert scenario.game.play_permission_for(giant, "alice") is None


def test_permission_has_no_end_turn_expiry():
    scenario = _board(bob=["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")
    _cast_journey(scenario, 1, [giant])
    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()
    scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()
    scenario.advance()
    assert giant.zone is Zone.EXILE
    assert scenario.game.play_permission_for(giant, "bob") is not None


def _cast_from_exile(scenario, name, forests):
    casting = scenario.cast(name, username="bob", from_zone=Zone.EXILE)
    casting.use_permission()
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Forest"] * forests, username="bob"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()


def _bobs_turn(scenario):
    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()
    scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.turn.active_player == "bob"


def test_owner_casts_the_exiled_creature_and_the_enchantment_draws():
    scenario = _board(bob=["Grizzly Bears"], bob_lands=["Forest"] * 4)
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_journey(scenario, 1, [bears])
    _bobs_turn(scenario)
    before = len(scenario.player("alice").hand)
    _cast_from_exile(scenario, "Grizzly Bears", 2)
    assert scenario.creature("Grizzly Bears", "bob").zone is Zone.BATTLEFIELD
    assert len(scenario.player("alice").hand) == before + 1


def test_a_creature_cast_from_hand_does_not_draw():
    scenario = _board(bob=["Grizzly Bears"], bob_lands=["Forest"] * 4, bob_hand=["Runeclaw Bear"])
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_journey(scenario, 1, [bears])
    _bobs_turn(scenario)
    before = len(scenario.player("alice").hand)
    scenario.cast_and_resolve(
        "Runeclaw Bear",
        *scenario.untapped_sources("Forest", "Forest", username="bob"),
        username="bob",
    )
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == before


def test_draws_only_once_each_turn():
    scenario = _board(bob=["Grizzly Bears", "Runeclaw Bear"], bob_lands=["Forest"] * 4)
    one = scenario.creature("Grizzly Bears", "bob")
    two = scenario.creature("Runeclaw Bear", "bob")
    _cast_journey(scenario, 2, [one, two])
    _bobs_turn(scenario)
    before = len(scenario.player("alice").hand)
    _cast_from_exile(scenario, "Grizzly Bears", 2)
    _cast_from_exile(scenario, "Runeclaw Bear", 2)
    assert len(scenario.player("alice").hand) == before + 1


def test_a_land_creature_can_be_played_from_exile_as_a_land():
    scenario = _board(bob=["Dryad Arbor"])
    arbor = scenario.find("Dryad Arbor", Zone.BATTLEFIELD, "bob")
    _cast_journey(scenario, 1, [arbor])
    assert arbor.zone is Zone.EXILE
    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()
    scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.play_land("Dryad Arbor", "bob", from_zone=Zone.EXILE)
    assert scenario.find("Dryad Arbor", Zone.BATTLEFIELD, "bob") is not None
    assert scenario.game.lands_played["bob"] == 1


def test_permission_ends_when_the_card_leaves_exile():
    scenario = _board(bob=["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")
    _cast_journey(scenario, 1, [giant])
    assert scenario.game.play_permission_for(giant, "bob") is not None
    scenario.game.put_into_graveyard(giant)
    assert giant.zone is Zone.GRAVEYARD
    assert scenario.game.play_permission_for(giant, "bob") is None


def test_an_exiled_token_gets_no_permission():
    scenario = _board(hand=("Extraordinary Journey", "Raise the Alarm"), bob=["Grizzly Bears"])
    scenario.cast_and_resolve("Raise the Alarm", *scenario.untapped_sources("Plains", "Plains"))
    token = next(s for s in scenario.game.permanents_controlled_by("alice") if s.token)
    bears = scenario.creature("Grizzly Bears", "bob")
    casting = scenario.cast("Extraordinary Journey", "alice")
    scenario.will_choose_targets(token, bears)
    payment = casting.determine_cost(x_value=2)
    scenario.pay_with(payment, *scenario.untapped_sources("Island", "Island", *["Plains"] * 4))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert token not in scenario.game.battlefield
    assert scenario.game.play_permission_for(token, "alice") is None
    assert scenario.game.play_permission_for(bears, "bob") is not None


# -- second printings of the owner-may-play-while-exiled permission ---------------------
# Release to the Wind: "... its owner may cast it without paying its mana cost."
# Soul Partition: "... its owner may play it. A spell cast by an opponent this way
# costs {2} more to cast."


def _cast_exile_spell(scenario, name, target, mana):
    scenario.cast_and_resolve(name, *scenario.untapped_sources(*mana), targets=[target])


def test_release_to_the_wind_owner_casts_it_for_free():
    scenario = _board(hand=("Release to the Wind",), bob=["Grizzly Bears"], bob_lands=[])
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_exile_spell(scenario, "Release to the Wind", bears, ["Island", "Island", "Plains"])
    assert bears.zone is Zone.EXILE
    _bobs_turn(scenario)
    casting = scenario.cast("Grizzly Bears", username="bob", from_zone=Zone.EXILE)
    casting.use_permission()
    scenario.pay_with(casting.begin_paying())
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert scenario.creature("Grizzly Bears", "bob").zone is Zone.BATTLEFIELD


def test_soul_partition_opponents_spell_costs_two_more():
    scenario = _board(hand=("Soul Partition",), bob=["Grizzly Bears"], bob_lands=["Forest"] * 3)
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_exile_spell(scenario, "Soul Partition", bears, ["Plains", "Plains"])
    assert bears.zone is Zone.EXILE
    _bobs_turn(scenario)
    casting = scenario.cast("Grizzly Bears", username="bob", from_zone=Zone.EXILE)
    casting.use_permission()
    payment = casting.begin_paying()
    with pytest.raises(ValueError):
        scenario.pay_with(
            payment, *scenario.untapped_sources("Forest", "Forest", "Forest", username="bob")
        )


def test_soul_partition_opponent_pays_two_more_in_full():
    scenario = _board(hand=("Soul Partition",), bob=["Grizzly Bears"], bob_lands=["Forest"] * 4)
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_exile_spell(scenario, "Soul Partition", bears, ["Plains", "Plains"])
    _bobs_turn(scenario)
    _cast_from_exile(scenario, "Grizzly Bears", 4)
    assert scenario.creature("Grizzly Bears", "bob").zone is Zone.BATTLEFIELD


def test_soul_partition_on_your_own_permanent_costs_no_more():
    scenario = _board(hand=("Soul Partition",), alice=["Grizzly Bears", "Forest", "Forest"])
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_exile_spell(scenario, "Soul Partition", bears, ["Plains", "Plains"])
    assert bears.zone is Zone.EXILE
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Grizzly Bears", username="alice", from_zone=Zone.EXILE)
    casting.use_permission()
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Forest", "Forest"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD
