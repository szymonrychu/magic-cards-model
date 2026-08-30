from magic_cards_model.models.zone import Zone


def test_hidden_zones():
    assert Zone.LIBRARY.is_hidden
    assert Zone.HAND.is_hidden
    assert not Zone.GRAVEYARD.is_hidden
    assert not Zone.BATTLEFIELD.is_hidden


def test_shared_zones():
    assert Zone.STACK.is_shared
    assert Zone.BATTLEFIELD.is_shared
    # Every player has their own library, hand, and graveyard.
    assert not Zone.LIBRARY.is_shared
    assert not Zone.GRAVEYARD.is_shared


def test_ordered_zones():
    assert Zone.LIBRARY.is_ordered
    assert Zone.STACK.is_ordered
    assert not Zone.HAND.is_ordered


def test_zone_is_a_string():
    assert Zone.EXILE == "exile"
