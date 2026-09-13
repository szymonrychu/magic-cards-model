"""A cost that reveals cards from the payer's hand (CR 118.1, CR 701.20a).

"{1}, Reveal X white cards from your hand, Sacrifice this creature: You gain
three times X life." (Martyr of Sands) and "As an additional cost to cast this
spell, reveal a creature card from your hand." (Living Destiny) are one
template: a count - a number, or CR 107.3a's X - of cards with a stated quality,
shown out of the hand as part of paying a cost.

- **CR 118.1** - "To pay a cost, a player carries out the instructions
  specified by the spell, ability, or effect that contains that cost." Showing
  the cards is the payment.
- **CR 118.3** - "A player can't pay a cost without having the necessary
  resources to pay it fully": a red card does not pay "reveal a white card",
  a card on the battlefield is not in the hand, and one card is one card
  (CR 109.1), so naming it twice reveals one.
- **CR 107.3a** - X in an activation cost that the text does not define is
  chosen and announced by the controller; "while an activated ability is on
  the stack, any X in its activation cost equals the announced value", which is
  the X the effect reads. The X a player announces here is how many cards they
  reveal.
- **CR 602.2b** - activating follows CR 601.2b-i, so CR 601.2h pays the reveal
  with the rest of the total cost.
- **CR 701.20a** - "To reveal a card, show that card to all players", and a
  card revealed as part of a cost stays revealed until the ability leaves the
  stack. The known-information model records it for every player and ends the
  record when the card leaves the hand (CR 400.7), the same record a
  Thoughtseize reveal leaves.

Martyr of Spores ("Target creature gets +X/+X") and Living Destiny (a fixed
count, on a spell) are not in any deck pool: they prove the template rather
than the reported card. Illuminated Folio's "Reveal two cards from your hand
that share a color" carries a rider this reader does not read, and fails
closed with a refusal naming the cost rather than paying for a wrong set.

Every CR number above was read in full from `mise run rules:find` in the
session that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Game, Zone
from magic_cards_model.models.action import ActionKind, Affordability

from .harness import Scenario


def known(game: Game, viewer: str) -> list[tuple[str, Zone]]:
    return sorted((entry.card_name, entry.zone) for entry in game.known_to(viewer))


def martyr_board(hand: list[str], battlefield: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=hand,
            battlefield=["Martyr of Sands", "Plains", *(battlefield or [])],
            library=["Plains"],
        )
        .player("bob", library=["Plains"], hand=["Ephemerate"])
        .build()
    )


def _martyr(scenario: Scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario.find("Martyr of Sands", Zone.BATTLEFIELD, "alice")


# -- paying it -----------------------------------------------------------------


def test_revealing_two_white_cards_gains_six_life():
    scenario = martyr_board(["Swords to Plowshares", "Ephemerate", "Lightning Bolt"])
    martyr = _martyr(scenario)
    swords = scenario.find("Swords to Plowshares", Zone.HAND, "alice")
    ephemerate = scenario.find("Ephemerate", Zone.HAND, "alice")
    (plains,) = scenario.untapped_sources("Plains")

    ability = scenario.activate(martyr, plains, revealing=[swords, ephemerate])

    assert ability is not None
    assert ability.x_value == 2
    assert martyr.zone is Zone.GRAVEYARD
    assert swords.zone is Zone.HAND and ephemerate.zone is Zone.HAND
    scenario.resolve_top()
    assert scenario.player("alice").life == 26


def test_the_revealed_cards_are_known_to_the_opponent():
    scenario = martyr_board(["Swords to Plowshares", "Ephemerate", "Lightning Bolt"])
    martyr = _martyr(scenario)
    swords = scenario.find("Swords to Plowshares", Zone.HAND, "alice")
    ephemerate = scenario.find("Ephemerate", Zone.HAND, "alice")
    (plains,) = scenario.untapped_sources("Plains")

    scenario.activate(martyr, plains, revealing=[swords, ephemerate])

    assert known(scenario.game, "bob") == [
        ("Ephemerate", Zone.HAND),
        ("Swords to Plowshares", Zone.HAND),
    ]


def test_a_revealed_card_stops_being_known_when_it_leaves_the_hand():
    scenario = martyr_board(["Swords to Plowshares", "Ocelot Pride"], battlefield=["Plains"])
    martyr = _martyr(scenario)
    swords = scenario.find("Swords to Plowshares", Zone.HAND, "alice")
    ocelot = scenario.find("Ocelot Pride", Zone.HAND, "alice")
    plains, other_plains = scenario.untapped_sources("Plains", "Plains")

    scenario.activate(martyr, plains, revealing=[swords, ocelot])
    scenario.resolve_top()
    scenario.cast_and_resolve("Ocelot Pride", other_plains)

    assert known(scenario.game, "bob") == [("Swords to Plowshares", Zone.HAND)]


def test_revealing_nothing_is_x_equal_to_zero():
    scenario = martyr_board(["Swords to Plowshares"])
    martyr = _martyr(scenario)
    (plains,) = scenario.untapped_sources("Plains")

    ability = scenario.activate(martyr, plains, revealing=[])
    scenario.resolve_top()

    assert ability is not None and ability.x_value == 0
    assert scenario.player("alice").life == 20
    assert known(scenario.game, "bob") == []


def test_an_unnamed_reveal_asks_the_player_which_qualifying_cards_to_reveal():
    """CR 601.2h pays the cost the player chose: the engine asks rather than
    guessing, offering only white cards in the payer's own hand, any number."""
    scenario = martyr_board(["Swords to Plowshares", "Ephemerate", "Lightning Bolt", "Plains"])
    martyr = _martyr(scenario)
    swords = scenario.find("Swords to Plowshares", Zone.HAND, "alice")
    ephemerate = scenario.find("Ephemerate", Zone.HAND, "alice")
    (plains,) = scenario.untapped_sources("Plains")
    scenario.will_choose_cards(swords, username="alice", source="Martyr of Sands")

    ability = scenario.activate(martyr, plains)
    scenario.resolve_top()

    (asked,) = [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_CARDS]
    assert set(asked.cards) == {swords.id, ephemerate.id}
    assert asked.exact is False
    assert ability is not None and ability.x_value == 1
    assert scenario.player("alice").life == 23


def test_an_announced_x_is_how_many_cards_are_asked_for():
    scenario = martyr_board(["Swords to Plowshares", "Ephemerate", "Lightning Bolt"])
    martyr = _martyr(scenario)
    swords = scenario.find("Swords to Plowshares", Zone.HAND, "alice")
    ephemerate = scenario.find("Ephemerate", Zone.HAND, "alice")
    (plains,) = scenario.untapped_sources("Plains")
    scenario.will_choose_cards(swords, ephemerate, username="alice", source="Martyr of Sands")

    ability = scenario.activate(martyr, plains, x_value=2)

    (asked,) = [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_CARDS]
    assert asked.exact is True and asked.amount == 2
    assert ability is not None and ability.x_value == 2


# -- refusing an illegal selection (CR 118.3) -----------------------------------


def _refused(scenario: Scenario, martyr, plains, match: str, **kwargs) -> None:
    with pytest.raises(ValueError, match=match):
        scenario.activate(martyr, plains, **kwargs)
    assert martyr.zone is Zone.BATTLEFIELD
    assert not plains.tapped
    assert scenario.game.stack_is_empty


def test_a_card_of_the_wrong_color_is_refused():
    scenario = martyr_board(["Lightning Bolt"])
    martyr = _martyr(scenario)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    (plains,) = scenario.untapped_sources("Plains")

    _refused(scenario, martyr, plains, "Lightning Bolt is not", revealing=[bolt])
    assert known(scenario.game, "bob") == []


def test_a_white_card_that_is_not_in_hand_is_refused():
    scenario = martyr_board([], battlefield=["Ocelot Pride"])
    martyr = _martyr(scenario)
    ocelot = scenario.find("Ocelot Pride", Zone.BATTLEFIELD, "alice")
    (plains,) = scenario.untapped_sources("Plains")

    _refused(scenario, martyr, plains, "not the hand", revealing=[ocelot])


def test_a_card_in_another_players_hand_is_refused():
    scenario = martyr_board([])
    martyr = _martyr(scenario)
    bobs = scenario.find("Ephemerate", Zone.HAND, "bob")
    (plains,) = scenario.untapped_sources("Plains")

    _refused(scenario, martyr, plains, "not in alice's hand", revealing=[bobs])


def test_the_same_card_named_twice_is_refused():
    scenario = martyr_board(["Swords to Plowshares"])
    martyr = _martyr(scenario)
    swords = scenario.find("Swords to Plowshares", Zone.HAND, "alice")
    (plains,) = scenario.untapped_sources("Plains")

    _refused(scenario, martyr, plains, "more than once", revealing=[swords, swords])


def test_an_announced_x_that_disagrees_with_the_cards_revealed_is_refused():
    scenario = martyr_board(["Swords to Plowshares", "Ephemerate"])
    martyr = _martyr(scenario)
    swords = scenario.find("Swords to Plowshares", Zone.HAND, "alice")
    (plains,) = scenario.untapped_sources("Plains")

    _refused(scenario, martyr, plains, "X", revealing=[swords], x_value=2)


# -- the action row -------------------------------------------------------------


def test_the_ability_is_listed_with_a_priced_cost():
    scenario = martyr_board(["Swords to Plowshares"])
    martyr = _martyr(scenario)

    (row,) = [
        action
        for action in scenario.game.legal_actions("alice")
        if action.kind is ActionKind.ACTIVATE and action.card_id == martyr.id
    ]

    assert row.cost is not None and "Reveal X white cards from your hand" in row.cost
    assert row.affordable is Affordability.YES
    assert row.unaffordable_reason is None


# -- the template, not the card ------------------------------------------------


def test_martyr_of_ashes_reveals_red_cards_and_deals_that_much_damage():
    """{2}, Reveal X red cards from your hand, Sacrifice this creature: This
    creature deals X damage to each creature without flying. A different
    color, a different mana cost and an effect that is not life gain."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Goblin Guide", "Swords to Plowshares"],
            battlefield=["Martyr of Ashes", "Mountain", "Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Birds of Paradise"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    martyr = scenario.find("Martyr of Ashes", Zone.BATTLEFIELD, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    guide = scenario.find("Goblin Guide", Zone.HAND, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    birds = scenario.creature("Birds of Paradise", "bob")

    ability = scenario.activate(
        martyr, *scenario.untapped_sources("Mountain", "Mountain"), revealing=[bolt, guide]
    )
    scenario.resolve_top()
    scenario.state_based_actions()

    assert ability is not None and ability.x_value == 2
    assert bears.zone is Zone.GRAVEYARD
    assert birds.zone is Zone.BATTLEFIELD
    assert known(scenario.game, "bob") == [
        ("Goblin Guide", Zone.HAND),
        ("Lightning Bolt", Zone.HAND),
    ]


def _destiny_board(hand: list[str]) -> Scenario:
    return (
        Scenario()
        .player("alice", hand=["Living Destiny", *hand], battlefield=["Forest"] * 4)
        .player("bob")
        .build()
    )


def test_living_destiny_reveals_one_creature_card_and_gains_its_mana_value():
    scenario = _destiny_board(["Elder Gargaroth", "Forest"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gargaroth = scenario.find("Elder Gargaroth", Zone.HAND, "alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")

    scenario.cast_and_resolve("Living Destiny", *sources, revealing=[gargaroth])

    assert scenario.player("alice").life == 25
    assert gargaroth.zone is Zone.HAND
    assert known(scenario.game, "bob") == [("Elder Gargaroth", Zone.HAND)]


def test_living_destiny_refuses_a_noncreature_card():
    scenario = _destiny_board(["Forest"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest_card = scenario.find("Forest", Zone.HAND, "alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")

    with pytest.raises(ValueError, match="Forest is not a creature"):
        scenario.cast_and_resolve("Living Destiny", *sources, revealing=[forest_card])


def test_living_destiny_asks_for_exactly_one_creature_card_when_none_is_named():
    scenario = _destiny_board(["Elder Gargaroth", "Grizzly Bears", "Forest"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gargaroth = scenario.find("Elder Gargaroth", Zone.HAND, "alice")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    scenario.will_choose_cards(bears, username="alice", source="Living Destiny")

    scenario.cast_and_resolve("Living Destiny", *sources)

    (asked,) = [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_CARDS]
    assert set(asked.cards) == {gargaroth.id, bears.id}
    assert asked.exact is True and asked.amount == 1
    assert scenario.player("alice").life == 22


def test_a_reveal_cost_with_an_unread_rider_fails_closed_naming_the_cost():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Swords to Plowshares", "Ephemerate"],
            battlefield=["Illuminated Folio", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    folio = scenario.find("Illuminated Folio", Zone.BATTLEFIELD, "alice")

    (row,) = [
        action
        for action in scenario.game.legal_actions("alice")
        if action.kind is ActionKind.ACTIVATE and action.card_id == folio.id
    ]
    assert row.affordable is Affordability.UNKNOWN
    assert "Reveal two cards from your hand that share a color" in (row.unaffordable_reason or "")
    with pytest.raises(ValueError, match="share a color"):
        scenario.game.begin_activating(folio, 0, "alice")
