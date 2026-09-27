"""An activation cost that removes a counter from a creature the payer
chooses, not from the ability's own source: "{2}, Remove a +1/+1 counter from
a creature you control: Draw a card." (Ray Fillet, Man Ray) and "{2}, Remove a
+1/+1 counter from a creature you control: Target creature gets -1/-1 until
end of turn." (Korozda Gorgon, the second printing off the tmt list).

- **CR 118.3** - a player can't pay a cost without having the necessary
  resources to pay it fully: the chosen creature must carry the counter.
- **CR 122.1** - counters with the same name or description are
  interchangeable.
- **CR 602.2b** - an activated ability's cost is paid as CR 601.2h describes.

Every CR number above was read with `mise run rules:find` in the session that
wrote this file.
"""

import pytest

from magic_cards_model.machines import Step, legal_actions
from magic_cards_model.models import ActionKind, Affordability
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _resolve(scenario: Scenario) -> None:
    while scenario.game.stack:
        scenario.pass_until_resolved()


def test_the_counter_comes_off_the_chosen_other_creature():
    """Ray Fillet, Man Ray: the counter is removed from Grizzly Bears, a
    different creature the payer controls, and the card is drawn."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island", "Island"],
            battlefield=["Ray Fillet, Man Ray", "Island", "Island", "Grizzly Bears"],
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ray = scenario.creature("Ray Fillet, Man Ray", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 1)
    hand_before = len(scenario.player("alice").hand)

    scenario.will_choose_cards(bears, username="alice")
    scenario.activate(ray, *scenario.untapped_sources("Island", "Island"))
    _resolve(scenario)

    assert bears.counters[Counter.PLUS_ONE] == 0
    assert len(scenario.player("alice").hand) == hand_before + 1


def test_the_source_itself_may_pay_its_own_counter():
    """ "a creature you control" includes the ability's own source."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island", "Island"],
            battlefield=["Ray Fillet, Man Ray", "Island", "Island"],
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ray = scenario.creature("Ray Fillet, Man Ray", "alice")
    ray.add_counters(Counter.PLUS_ONE, 2)

    scenario.will_choose_cards(ray, username="alice")
    scenario.activate(ray, *scenario.untapped_sources("Island", "Island"))
    _resolve(scenario)

    assert ray.counters[Counter.PLUS_ONE] == 1


def test_a_creature_without_the_counter_cannot_pay():
    """CR 118.3: no +1/+1 counter on the chosen creature, no payment."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island", "Island"],
            battlefield=["Ray Fillet, Man Ray", "Island", "Island", "Grizzly Bears"],
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ray = scenario.creature("Ray Fillet, Man Ray", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    hand_before = len(scenario.player("alice").hand)

    scenario.will_choose_cards(bears, username="alice")
    with pytest.raises(ValueError):
        scenario.activate(ray, *scenario.untapped_sources("Island", "Island"))
    assert len(scenario.player("alice").hand) == hand_before


def test_an_opponents_creature_cannot_pay():
    """ "a creature *you control*": an opponent's countered creature is not a
    legal choice."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island", "Island"],
            battlefield=["Ray Fillet, Man Ray", "Island", "Island"],
        )
        .player("bob", library=["Island"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ray = scenario.creature("Ray Fillet, Man Ray", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.add_counters(Counter.PLUS_ONE, 1)

    scenario.will_choose_cards(bears, username="alice")
    with pytest.raises(ValueError):
        scenario.activate(ray, *scenario.untapped_sources("Island", "Island"))
    assert bears.counters[Counter.PLUS_ONE] == 1


def test_a_second_printing_korozda_gorgon():
    """Korozda Gorgon: the same cost template on a card off the tmt list,
    with a targeted effect after it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Swamp"],
            battlefield=["Korozda Gorgon", "Swamp", "Swamp", "Grizzly Bears"],
        )
        .player("bob", library=["Swamp"], battlefield=["Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gorgon = scenario.creature("Korozda Gorgon", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "bob")
    bears.add_counters(Counter.PLUS_ONE, 1)

    scenario.will_choose_cards(bears, username="alice")
    scenario.activate(gorgon, *scenario.untapped_sources("Swamp", "Swamp"), targets=[memnite])
    _resolve(scenario)

    assert bears.counters[Counter.PLUS_ONE] == 0
    assert memnite.zone.value == "graveyard"


def _activate_row(scenario: Scenario, card_id: str):
    (row,) = [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.card_id == card_id and action.kind is ActionKind.ACTIVATE
    ]
    return row


def _ray_board(bears_counters: int) -> tuple[Scenario, str]:
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island"],
            battlefield=["Ray Fillet, Man Ray", "Island", "Island", "Grizzly Bears"],
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    if bears_counters:
        scenario.creature("Grizzly Bears", "alice").add_counters(Counter.PLUS_ONE, bears_counters)
    return scenario, scenario.creature("Ray Fillet, Man Ray", "alice").id


def test_legal_actions_says_no_when_no_creature_carries_the_counter():
    """CR 118.3, judged before anything is chosen: nobody has a +1/+1
    counter, so the activation is enumerated but unaffordable."""
    scenario, ray_id = _ray_board(0)
    row = _activate_row(scenario, ray_id)
    assert row.affordable is Affordability.NO


def test_legal_actions_says_yes_when_a_creature_carries_the_counter():
    scenario, ray_id = _ray_board(1)
    row = _activate_row(scenario, ray_id)
    assert row.affordable is Affordability.YES
