"""A land that enters tapped unless its controller reveals a card from hand.

"As this land enters, you may reveal a Plains or Island card from your hand.
If you don't, this land enters tapped." is one CR 614.12a choice printed over
two sentences, the same shape as a shockland's "you may pay 2 life", with a
reveal where the life payment was. The quality named - two basic land types, a
creature type - is whatever the sentence prints.

Rules, each read in full with `mise run rules:find` in the session that wrote
this file:

- **CR 614.1c** - "As [this permanent] enters . . ." is a replacement effect.
- **CR 614.12a** - its choice "is made before the permanent enters the
  battlefield".
- **CR 118.3** - a player cannot pay a cost without the resources to pay it,
  so with no qualifying card in hand there is nothing to choose and the land
  enters tapped.
- **CR 701.20a / 701.20b** - revealing shows the card to all players and does
  not move it out of the hand.
"""

from magic_cards_model.machines import EntersState, Step, predict_enters
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.replacement import unread_self_enters_tapped_lines
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(hand):
    scenario = Scenario().player("alice", hand=list(hand)).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _reveal_questions(scenario):
    return [
        decision
        for decision in scenario.questions_asked()
        if decision.kind is DecisionKind.MAY and "reveal" in decision.prompt
    ]


def test_revealing_an_island_lets_port_town_enter_untapped():
    scenario = _board(["Port Town", "Island"])
    island = scenario.find("Island", Zone.HAND, "alice")

    port_town = scenario.play_land("Port Town")

    assert port_town.tapped is False
    assert [(shown.card_name, shown.revealed_by) for shown in scenario.game.reveals] == [
        ("Island", "alice")
    ]
    assert island.zone is Zone.HAND


def test_declining_the_reveal_enters_tapped():
    scenario = _board(["Port Town", "Island"])
    scenario.will_take_the_may(False)

    port_town = scenario.play_land("Port Town")

    assert port_town.tapped is True
    assert scenario.game.reveals == []
    assert len(_reveal_questions(scenario)) == 1


def test_no_qualifying_card_enters_tapped_and_asks_nothing():
    scenario = _board(["Port Town", "Mountain"])

    port_town = scenario.play_land("Port Town")

    assert port_town.tapped is True
    assert _reveal_questions(scenario) == []
    assert scenario.game.reveals == []


def test_the_card_revealed_is_the_one_chosen():
    scenario = _board(["Port Town", "Island", "Plains"])
    plains = scenario.find("Plains", Zone.HAND, "alice")
    scenario.will_choose_cards(plains)

    port_town = scenario.play_land("Port Town")

    assert port_town.tapped is False
    assert [shown.card_id for shown in scenario.game.reveals] == [plains.id]


def test_another_printing_of_the_template_off_pool_reads_a_creature_type():
    """Gilt-Leaf Palace asks for "an Elf card" rather than basic land types."""
    elf = _board(["Gilt-Leaf Palace", "Llanowar Elves"])
    no_elf = _board(["Gilt-Leaf Palace", "Island"])

    assert elf.play_land("Gilt-Leaf Palace").tapped is False
    assert no_elf.play_land("Gilt-Leaf Palace").tapped is True


def test_the_prediction_offers_the_reveal_as_the_optional_cost():
    scenario = _board(["Port Town", "Island"])

    prediction = predict_enters(
        scenario.game, "alice", scenario.find("Port Town", Zone.HAND, "alice")
    )

    assert prediction.state is EntersState.UNTAPPED_IF_PAID
    assert prediction.optional_costs == ("reveal a Plains or Island card from your hand",)
    assert prediction.notices == ()


def test_the_prediction_with_nothing_to_reveal_is_tapped():
    scenario = _board(["Port Town", "Mountain"])

    prediction = predict_enters(
        scenario.game, "alice", scenario.find("Port Town", Zone.HAND, "alice")
    )

    assert prediction.state is EntersState.TAPPED
    assert prediction.notices == ()


def test_the_line_is_read_so_nothing_is_reported_unread():
    scenario = _board(["Port Town"])

    assert unread_self_enters_tapped_lines(scenario.find("Port Town", Zone.HAND, "alice")) == []


def test_predicting_reveals_nothing_in_the_real_game():
    scenario = _board(["Port Town", "Island"])
    before = scenario.game.model_dump_json()

    predict_enters(scenario.game, "alice", scenario.find("Port Town", Zone.HAND, "alice"))

    assert scenario.game.model_dump_json() == before
    assert scenario.game.reveals == []
