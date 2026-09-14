"""Scenario: only a modal double-faced card is played as its land face (CR 712.12).

Rules read in full this session with `mise run rules:find`:

- **CR 712.12** - "A player playing a modal double-faced card or a copy of a
  modal double-faced card as a land chooses one of its faces that's a land
  before putting it onto the battlefield. It enters the battlefield with that
  face up." The permission names a *modal* double-faced card and nothing else.
- **CR 712.1** - there are "three kinds of double-faced cards: nonmodal
  double-faced cards (previously called "transforming double-faced cards"),
  modal double-faced cards, and meld cards." So a transform or meld card is a
  different kind, outside CR 712.12.
- **CR 712.8a** - "While a double-faced card is outside the game or in a zone
  other than the battlefield or stack, it has only the characteristics of its
  front face." Treasure Map in hand is an artifact card, not a land card, so
  CR 305.1's "play a land card from their hand" does not reach it either.
- **CR 712.14** - a double-faced card put onto the battlefield from a zone
  other than the stack enters front face up; Treasure Cove only ever appears by
  transforming (CR 712.2).

The defect: `Card.land_face` read any face whose type line says Land, whatever
the layout, so a transform card with a land back face (Treasure Map //
Treasure Cove) was offered as a land drop, played as one, and predicted as one.
The fix aims at the layout, not at the card: Search for Azcanta // Azcanta, the
Sunken Ruin (an enchantment front, a legendary land back) is the second,
non-reported printing proving it.
"""

import pytest

from magic_cards_model.machines import EntersState, Step, predict_enters
from magic_cards_model.models import Type, Zone
from magic_cards_model.models.action import ActionKind
from tests.scenarios.harness import Scenario

TRANSFORM_WITH_A_LAND_BACK = ["Treasure Map", "Search for Azcanta"]


def _board(hand: list[str]):
    scenario = (
        Scenario()
        .player("alice", hand=hand, library=["Plains"])
        .player("bob", library=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _land_plays(scenario, card_id):
    return [
        action
        for action in scenario.game.legal_actions("alice")
        if action.kind is ActionKind.PLAY_LAND and action.card_id == card_id
    ]


def test_a_modal_dfc_with_a_land_back_is_offered_and_played_as_that_land():
    scenario = _board(["Sink into Stupor"])
    stupor = scenario.find("Sink into Stupor", Zone.HAND, "alice")

    (offer,) = _land_plays(scenario, stupor.id)
    assert offer.land_face == "Soporific Springs"
    assert offer.rule == "CR 712.12"

    springs = scenario.play_land("Sink into Stupor")
    assert springs.zone is Zone.BATTLEFIELD
    assert springs.name == "Soporific Springs"
    assert springs.types == (Type.LAND,)


@pytest.mark.parametrize("name", TRANSFORM_WITH_A_LAND_BACK)
def test_a_transform_card_with_a_land_back_is_not_offered_as_a_land(name):
    scenario = _board([name])
    card = scenario.find(name, Zone.HAND, "alice")

    assert card.card.land_face is None
    assert _land_plays(scenario, card.id) == []


@pytest.mark.parametrize("name", TRANSFORM_WITH_A_LAND_BACK)
def test_a_transform_card_with_a_land_back_cannot_be_played_as_a_land(name):
    scenario = _board([name])
    card = scenario.find(name, Zone.HAND, "alice")

    with pytest.raises(ValueError, match="is not a land"):
        scenario.game.play_land(card, "alice")

    assert card.zone is Zone.HAND
    assert card.land_face_played is None
    assert scenario.game.lands_played.get("alice", 0) == 0


@pytest.mark.parametrize("name", TRANSFORM_WITH_A_LAND_BACK)
def test_predict_enters_refuses_a_transform_card_from_hand(name):
    scenario = _board([name])
    card = scenario.find(name, Zone.HAND, "alice")

    with pytest.raises(ValueError, match="is not a land"):
        predict_enters(scenario.game, "alice", card)


def test_predict_enters_still_accepts_the_modal_dfc_from_hand():
    scenario = _board(["Sink into Stupor"])
    stupor = scenario.find("Sink into Stupor", Zone.HAND, "alice")

    assert predict_enters(scenario.game, "alice", stupor).state is EntersState.UNTAPPED_IF_PAID
