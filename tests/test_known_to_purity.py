"""`Game.known_to` is a query: it mutates nothing and answers the same twice.

The same shape as `tests/scenarios/test_legal_actions.py::test_legal_actions_
mutates_nothing`: dump the game, ask, dump again. A reader that "tidied" an
expired record out of `Game.reveals` while answering would make the second
call disagree with a decode of the first game, which is exactly what a
consumer holding a persisted `Game` cannot afford.

Also here, because it is a property of the reader rather than of a mechanic:
a record whose shape the reader does not recognise is not returned
(fail closed). CR 701.20a/701.20e, CR 400.7 and CR 701.20d were read in full
with `mise run rules:find` in the session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Game, Zone
from magic_cards_model.models.game import KnownCard, Reveal
from tests.scenarios.harness import Scenario


def _a_game_with_a_reveal_a_look_and_a_carry() -> Game:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Goblin Guide", "Mishra's Bauble"])
        .player("bob", library=["Forest", "Lightning Bolt", "Island"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Goblin Guide", "alice"))
    scenario.resolve_top()  # Forest revealed and put into bob's hand
    bauble = scenario.find("Mishra's Bauble", Zone.BATTLEFIELD)
    scenario.activate(bauble, username="alice", targets=["bob"])
    scenario.pass_until_resolved()  # alice looks at the Bolt
    return scenario.game


def test_known_to_mutates_nothing_and_answers_the_same_twice():
    game = _a_game_with_a_reveal_a_look_and_a_carry()
    before = game.model_dump_json()

    first_alice = game.known_to("alice")
    first_bob = game.known_to("bob")
    second_alice = game.known_to("alice")
    second_bob = game.known_to("bob")

    assert game.model_dump_json() == before
    assert first_alice == second_alice
    assert first_bob == second_bob
    assert [entry.card_name for entry in first_alice] == ["Forest", "Lightning Bolt"]
    assert [entry.card_name for entry in first_bob] == ["Forest"]
    assert all(isinstance(entry, KnownCard) for entry in first_alice)


def test_known_card_is_frozen_data():
    game = _a_game_with_a_reveal_a_look_and_a_carry()
    (forest, bolt) = game.known_to("alice")
    assert KnownCard.model_config.get("frozen") is True
    assert Reveal.model_config.get("frozen") is True
    assert forest.carried is True and bolt.carried is False
    assert KnownCard.model_validate(bolt.model_dump(mode="json")) == bolt


def test_a_record_of_an_unrecognised_shape_is_not_returned():
    """A library record with no epoch, a record with no stamp, and a record
    that names a zone the card is not in are all refused rather than guessed
    at."""
    game = _a_game_with_a_reveal_a_look_and_a_carry()
    bob = game.player("bob")
    bolt = bob.library[0]
    island = bob.library[1]
    game.reveals.append(
        Reveal(
            card_id=island.id,
            card_name=island.name,
            revealed_by="bob",
            zone=Zone.LIBRARY,
            viewers=None,
            zone_change_stamp=island.zone_change_stamp,
            turn=game.turn.turns_taken,
            library_epoch=None,
        )
    )
    game.reveals.append(
        Reveal(
            card_id=island.id,
            card_name=island.name,
            revealed_by="bob",
            zone=Zone.LIBRARY,
            viewers=None,
            zone_change_stamp=None,
            turn=game.turn.turns_taken,
            library_epoch=bob.library_epoch,
        )
    )
    game.reveals.append(
        Reveal(
            card_id=island.id,
            card_name=island.name,
            revealed_by="bob",
            zone=Zone.HAND,
            viewers=None,
            zone_change_stamp=island.zone_change_stamp,
            turn=game.turn.turns_taken,
            library_epoch=None,
        )
    )

    assert [entry.card_id for entry in game.known_to("bob")] == [bob.hand[0].id]
    assert [entry.card_id for entry in game.known_to("alice")] == [bob.hand[0].id, bolt.id]
