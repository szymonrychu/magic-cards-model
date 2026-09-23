"""Scenario: "Return target <card> ... to your hand. If it's a <quality>
card, <effect>." - a rider conditioned on what the first sentence returned.

- **Tamiyo, Seasoned Scholar's -3**: "Return target instant or sorcery card
  from your graveyard to your hand. If it's a green card, add one mana of any
  color." A colour quality and a mana rider, on a loyalty ability.
- **Cemetery Recruitment** (off-pool proof printing, a spell): "Return target
  creature card from your graveyard to your hand. If it's a Zombie card, draw
  a card." A creature-type quality and a draw rider.

"It" is the card the first sentence returned. That card is now in a hidden
zone (the hand), so its quality is read as it last existed in the graveyard.

Every CR number below was read with `mise run rules:find` in the session
that wrote this file:

- **CR 608.2h** - "... if it's no longer in that zone, or if the effect has
  moved it from a public zone to a hidden zone, the effect uses the object's
  last known information."
- **CR 608.2b** - a target gone from its zone is illegal; with every target
  illegal the ability does not resolve, so neither sentence happens.
- **CR 702.73a** - "Changeling ... means 'This object is every creature
  type.' This ability works everywhere".
- **CR 606.4** - a loyalty ability's cost.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

TAMIYO = "Tamiyo, Inquisitive Student"
SEASONED_SCHOLAR = "Tamiyo, Seasoned Scholar"


def _resolve_stack(scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def _tamiyo(graveyard: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[TAMIYO],
            graveyard=graveyard,
            library=["Island"] * 10,
        )
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.draw_cards("alice", 3)
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)
    tamiyo = scenario.find(SEASONED_SCHOLAR, Zone.BATTLEFIELD, "alice")
    scenario.game.add_counters(tamiyo, Counter.LOYALTY, 3)
    return scenario, tamiyo


def _floating(scenario, username: str = "alice") -> dict:
    return dict(scenario.player(username).mana_pool.floating)


# -- Tamiyo, Seasoned Scholar's -3 -----------------------------------------


def test_returning_a_green_sorcery_adds_one_mana_of_the_chosen_color():
    scenario, tamiyo = _tamiyo(["Ancient Stirrings"])
    stirrings = scenario.find("Ancient Stirrings", Zone.GRAVEYARD, "alice")
    scenario.will_choose(Color.RED.value, username="alice")

    scenario.activate(tamiyo, index=1, targets=[stirrings])
    scenario.resolve_top()

    assert stirrings.zone is Zone.HAND
    assert _floating(scenario) == {Color.RED: 1}
    assert tamiyo.loyalty == 2, "CR 606.4: 2 on entering, plus 3, minus 3"


def test_returning_a_nongreen_instant_adds_no_mana():
    scenario, tamiyo = _tamiyo(["Lightning Bolt"])
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")

    scenario.activate(tamiyo, index=1, targets=[bolt])
    scenario.resolve_top()

    assert bolt.zone is Zone.HAND
    assert _floating(scenario) == {}
    assert not [d for d in scenario.questions_asked() if d.source == SEASONED_SCHOLAR]


def test_a_multicolored_card_that_is_green_counts_as_green():
    """Abrupt Decay is black and green - it is a green card."""
    scenario, tamiyo = _tamiyo(["Abrupt Decay"])
    decay = scenario.find("Abrupt Decay", Zone.GRAVEYARD, "alice")
    scenario.will_choose(Color.BLUE.value, username="alice")

    scenario.activate(tamiyo, index=1, targets=[decay])
    scenario.resolve_top()

    assert decay.zone is Zone.HAND
    assert _floating(scenario) == {Color.BLUE: 1}


def test_a_target_gone_from_the_graveyard_returns_nothing_and_adds_no_mana():
    """CR 608.2b: the only target left the graveyard in response, so the
    ability does not resolve - no return, and no rider either."""
    scenario, tamiyo = _tamiyo(["Ancient Stirrings"])
    stirrings = scenario.find("Ancient Stirrings", Zone.GRAVEYARD, "alice")

    scenario.activate(tamiyo, index=1, targets=[stirrings])
    scenario.game.exile_cards([stirrings])
    scenario.resolve_top()

    assert stirrings.zone is Zone.EXILE
    assert _floating(scenario) == {}


# -- Cemetery Recruitment: the same template, a type quality and a draw ------


def _recruitment(graveyard: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cemetery Recruitment"],
            battlefield=["Swamp", "Swamp"],
            graveyard=graveyard,
            library=["Island"] * 5,
        )
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_recruitment(scenario, target) -> None:
    swamps = scenario.untapped_sources("Swamp", "Swamp", username="alice")
    scenario.cast_and_resolve("Cemetery Recruitment", *swamps, targets=[target])


def test_returning_a_zombie_draws_a_card():
    scenario = _recruitment(["Carrion Feeder"])
    feeder = scenario.find("Carrion Feeder", Zone.GRAVEYARD, "alice")

    _cast_recruitment(scenario, feeder)

    alice = scenario.player("alice")
    assert feeder.zone is Zone.HAND
    assert sorted(state.name for state in alice.hand) == ["Carrion Feeder", "Island"]
    assert len(alice.library) == 4


def test_returning_a_non_zombie_draws_nothing():
    scenario = _recruitment(["Grizzly Bears"])
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    _cast_recruitment(scenario, bears)

    alice = scenario.player("alice")
    assert [state.name for state in alice.hand] == ["Grizzly Bears"]
    assert len(alice.library) == 5


def test_a_changeling_is_a_zombie_card_in_the_graveyard():
    """CR 702.73a: changeling works everywhere, so Changeling Outcast is a
    Zombie card too."""
    scenario = _recruitment(["Changeling Outcast"])
    outcast = scenario.find("Changeling Outcast", Zone.GRAVEYARD, "alice")

    _cast_recruitment(scenario, outcast)

    assert len(scenario.player("alice").library) == 4


def test_a_fizzled_recruitment_draws_nothing():
    """CR 608.2b again, on a spell: the Zombie left the graveyard in response,
    so nothing is returned and nothing is drawn."""
    scenario = _recruitment(["Carrion Feeder"])
    feeder = scenario.find("Carrion Feeder", Zone.GRAVEYARD, "alice")
    swamps = scenario.untapped_sources("Swamp", "Swamp", username="alice")
    scenario.cast_onto_stack("Cemetery Recruitment", *swamps, targets=[feeder])

    scenario.game.exile_cards([feeder])
    scenario.resolve_top()

    assert feeder.zone is Zone.EXILE
    assert len(scenario.player("alice").library) == 5
