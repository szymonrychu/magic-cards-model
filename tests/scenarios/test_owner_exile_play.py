"""Scenario: Suspend Aggression - owner-may-play exile (Secrets of Strixhaven,
T8).

    Exile target nonland permanent and the top card of your library. For
    each of those cards, its owner may play it until the end of their next
    turn.

Two objects are exiled in the same breath - a targeted permanent (any
player's) and the caster's own top library card - and CR 607.1's "those
cards" reaches back over both at once. What makes this a genuinely new shape,
not a second copy of the "exile ..., you may play it" family
(`test_exile_top_then_play_until_next_turn.py`, `test_play_from_exile.py`):
every one of *that* family's printings hands its own permission to the
*caster*, whoever exiled the card. Here the permission goes to each card's
own **owner** (CR 108.3) - the caster's own opponent, when the target was the
opponent's permanent - and each owner's "their next turn" is judged against
that owner's own turns, independently of the other.

Every rule cited here was read whole with `mise run rules:find` in the
session that wrote this file:

- **CR 601.3** - a rule or effect must allow a player to cast (or, CR
  701.18b, play) a card for them to begin.
- **CR 108.3** - the owner of a card is whoever started the game with it in
  their deck; legal control of a permanent is a separate question (CR
  108.4/110.2).
- **CR 611.2a** - "until the end of your next turn" - here read for whichever
  player "their" names in each grant, independently.
- **CR 400.7** - a card that leaves exile and returns is a new object; the
  permission does not follow it.
- **CR 406.2/701.13a** - exile reaches any object from any zone it is
  currently in, not only the battlefield.
- **CR 608.2f** - both objects this instruction exiles move as one action.
- **CR 514.1/514.2** - the cleanup step, where an "until end of turn"-scoped
  effect ends.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from


def _board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Suspend Aggression"],
            battlefield=["Mountain", "Plains", "Island"],
            library=["Forest", "Swamp"],
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Island", "Island"])
    )


def _end_turn(scenario) -> None:
    """Run cleanup (CR 514.1/514.2) and cross into the next player's turn -
    the same recipe `test_exile_top_then_play_until_next_turn.py` uses."""
    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()
    scenario.advance()


def test_both_cards_are_exiled_and_each_owner_gets_their_own_permission():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    forest = scenario.player("alice").library[0]
    sources = scenario.untapped_sources("Mountain", "Plains", "Island")

    scenario.cast_and_resolve("Suspend Aggression", *sources, targets=[bears])

    assert bears.zone is Zone.EXILE
    assert forest.zone is Zone.EXILE
    bears_permission = scenario.game.play_permission_for(bears, "bob")
    forest_permission = scenario.game.play_permission_for(forest, "alice")
    assert bears_permission is not None, "the owner of the exiled creature may play it"
    assert forest_permission is not None, "the caster owns the library card"
    assert scenario.game.play_permission_for(bears, "alice") is None, "never the caster"
    assert scenario.game.play_permission_for(forest, "bob") is None


def test_the_opponent_can_play_their_own_exiled_creature():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Suspend Aggression"],
            battlefield=["Mountain", "Plains", "Island"],
            library=["Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Mountain", "Plains", "Island")
    scenario.cast_and_resolve("Suspend Aggression", *sources, targets=[bears])
    assert bears.zone is Zone.EXILE

    # Grizzly Bears is sorcery-speed (CR 117.1a): the permission lifts the
    # "only from your own hand" restriction, but bob still needs his own
    # main phase with an empty stack to cast it, exactly as normal - nothing
    # here grants flash.
    _end_turn(scenario)  # alice's turn ends; bob's own next turn begins
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.turn.active_player == "bob"
    assert scenario.game.play_permission_for(bears, "bob") is not None

    casting = scenario.cast("Grizzly Bears", username="bob", from_zone=Zone.EXILE)
    casting.use_permission()
    payment = casting.begin_paying()
    for forest in scenario.untapped_sources("Forest", "Forest", username="bob"):
        payment.tap_for_mana(forest, mana_from(forest))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    returned = next(
        state for state in scenario.game.battlefield if state.card.name == "Grizzly Bears"
    )
    assert returned.controller == "bob"


def test_the_library_card_can_be_played_by_the_caster():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Suspend Aggression"],
            battlefield=["Mountain", "Plains", "Island", "Forest", "Forest"],
            library=["Grizzly Bears"],
        )
        .player("bob", battlefield=["Runeclaw Bear"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    runeclaw = scenario.creature("Runeclaw Bear", "bob")
    top = scenario.player("alice").library[0]
    assert top.name == "Grizzly Bears"
    sources = scenario.untapped_sources("Mountain", "Plains", "Island")
    scenario.cast_and_resolve("Suspend Aggression", *sources, targets=[runeclaw])
    assert top.zone is Zone.EXILE

    casting = scenario.cast("Grizzly Bears", username="alice", from_zone=Zone.EXILE)
    casting.use_permission()
    payment = casting.begin_paying()
    for forest in scenario.untapped_sources("Forest", "Forest"):
        payment.tap_for_mana(forest, mana_from(forest))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    bears_permanent = next(
        state for state in scenario.game.battlefield if state.card.name == "Grizzly Bears"
    )
    assert bears_permanent.controller == "alice"


def test_a_different_owner_and_controller_gives_the_owner_the_permission():
    """CR 108.3's owner, not the controller - staged directly the way every
    other scenario stages a continuous effect's own end state
    (`CardState.stored_controller` is the base control `Game.put_onto_
    battlefield` writes; a real control-change spell would write the same
    field through its own effect)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Suspend Aggression"],
            battlefield=["Mountain", "Plains", "Island"],
            library=["Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.stored_controller = "alice"
    assert bears.controller == "alice"
    assert bears.owner == "bob"
    sources = scenario.untapped_sources("Mountain", "Plains", "Island")
    scenario.cast_and_resolve("Suspend Aggression", *sources, targets=[bears])
    assert scenario.game.play_permission_for(bears, "bob") is not None
    assert scenario.game.play_permission_for(bears, "alice") is None


def test_bobs_permission_survives_until_the_cleanup_of_his_own_next_turn():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Mountain", "Plains", "Island")
    scenario.cast_and_resolve("Suspend Aggression", *sources, targets=[bears])

    _end_turn(scenario)  # alice's casting turn ends; bob's own next turn begins
    assert scenario.turn.active_player == "bob"
    assert scenario.game.play_permission_for(bears, "bob") is not None, (
        "bob's own next turn has arrived but not yet ended"
    )


def test_bobs_permission_expires_at_the_cleanup_of_his_own_next_turn():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    forest = scenario.player("alice").library[0]
    sources = scenario.untapped_sources("Mountain", "Plains", "Island")
    scenario.cast_and_resolve("Suspend Aggression", *sources, targets=[bears])

    _end_turn(scenario)  # alice's casting turn ends; bob's own next turn begins
    _end_turn(scenario)  # bob's own next turn ends: his own cleanup drops it
    assert scenario.turn.active_player == "alice"
    assert scenario.game.play_permission_for(bears, "bob") is None
    # Alice's own next turn has not arrived yet - hers still stands throughout.
    assert scenario.game.play_permission_for(forest, "alice") is not None


def test_targeting_ones_own_permanent_still_grants_a_permission():
    """Nothing about the reader requires the target to be an opponent's -
    "target nonland permanent" reaches the caster's own creatures too, and
    the owner-scoped grant is simply the caster's own, same as the library
    card's."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Suspend Aggression"],
            battlefield=["Mountain", "Plains", "Island", "Grizzly Bears"],
            library=["Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Mountain", "Plains", "Island")
    scenario.cast_and_resolve("Suspend Aggression", *sources, targets=[bears])
    assert bears.zone is Zone.EXILE
    assert scenario.game.play_permission_for(bears, "alice") is not None


def test_an_empty_library_still_exiles_and_grants_for_the_target_alone():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Suspend Aggression"], battlefield=["Mountain", "Plains", "Island"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Mountain", "Plains", "Island")
    scenario.cast_and_resolve("Suspend Aggression", *sources, targets=[bears])
    assert bears.zone is Zone.EXILE
    assert scenario.game.play_permission_for(bears, "bob") is not None
