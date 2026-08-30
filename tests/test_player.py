import pytest

from magic_cards_model.models import CardState, Player, Zone
from tests.cards import card_state as _card_state


def card_state() -> CardState:
    return _card_state("Ragavan, Nimble Pilferer")


def player_with_library(size: int = 3) -> Player:
    player = Player(username="alice")
    for _ in range(size):
        player.add(card_state(), Zone.LIBRARY)
    return player


def test_a_new_player_has_the_four_per_player_zones():
    player = Player(username="alice")

    assert set(player.zones) == {Zone.LIBRARY, Zone.HAND, Zone.GRAVEYARD, Zone.SIDEBOARD}
    assert player.life == 20
    assert player.mana_pool.is_empty


def test_copies_of_a_card_are_separate_states_sharing_one_printing():
    player = player_with_library(4)
    first, second = player.library[0], player.library[1]

    assert first.id != second.id
    assert first.card is not second.card or first.card == second.card
    assert first.name == second.name


def test_drawing_moves_cards_from_library_to_hand():
    player = player_with_library(3)

    drawn = player.draw(2)

    assert len(player.hand) == 2
    assert len(player.library) == 1
    assert all(state.zone is Zone.HAND for state in drawn)


def test_drawing_more_than_the_library_holds_is_an_error():
    player = player_with_library(1)

    with pytest.raises(ValueError, match="cannot draw"):
        player.draw(2)


def test_moving_between_zones_keeps_one_copy_in_one_place():
    player = player_with_library(1)
    state = player.library[0]

    player.move(state, Zone.GRAVEYARD)

    assert player.library == []
    assert player.graveyard == [state]
    assert state.zone is Zone.GRAVEYARD


def test_a_card_leaving_the_battlefield_arrives_untapped_and_face_up():
    state = card_state()
    state.move_to(Zone.BATTLEFIELD)
    state.tap()
    state.turn_face_down()

    state.move_to(Zone.GRAVEYARD)

    assert state.untapped
    assert state.face_up


def test_only_battlefield_cards_tap():
    state = card_state()  # in the library

    with pytest.raises(ValueError, match="only battlefield cards tap"):
        state.tap()


def test_untapping_everything_the_player_controls():
    player = Player(username="alice")
    permanents = [card_state() for _ in range(3)]
    for state in permanents:
        state.move_to(Zone.BATTLEFIELD)
        state.tap()

    player.untap_all(permanents)

    assert all(state.untapped for state in permanents)
