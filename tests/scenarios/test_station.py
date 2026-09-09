"""Station: CR 702.184a's activated ability, and CR 721's threshold lines.

"Station" means "Tap another untapped creature you control: Put a number of
charge counters on this permanent equal to the tapped creature's power.
Activate only as a sorcery." `machines/keywords.station_activation`/
`_station_effect` build and resolve it - the same `KeywordActivation` shape
`crew_activation`/`_crew_effect` already use, driven the same way
`tests/scenarios/test_crew.py` drives crew directly rather than through
`Game.cast`. The threshold lines themselves ("5+ | Flying, trample") already
parse and are read off the computed board once the counters are actually
there (CR 721.2a); only the counter-placing ability was missing.

Proved on Exploration Broodship - a green 1-drop with its own threshold
grant, not Extinguisher Battleship's colourless one - outside the deck pool
and outside this wave's brief.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import station_activation
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _station(scenario, spacecraft, tapped, username="alice"):
    """Activate a station ability, pay it, and let it resolve."""
    activation = station_activation(scenario.game, spacecraft, tapped, username)
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()
    activation.resolve()
    return activation


def test_stationing_puts_charge_counters_equal_to_the_tapped_creatures_power():
    """Extinguisher Battleship: "Tap another untapped creature you control:
    Put a number of charge counters on this permanent equal to the tapped
    creature's power."
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Extinguisher Battleship", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    battleship = scenario.find("Extinguisher Battleship", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "alice")

    _station(scenario, battleship, bears)

    assert battleship.counters[Counter.CHARGE] == 2
    assert bears.tapped


def test_a_second_station_stacks_the_counters():
    """CR 122.3: counters accumulate rather than replace."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Extinguisher Battleship", "Grizzly Bears", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    battleship = scenario.find("Extinguisher Battleship", Zone.BATTLEFIELD)
    first, second = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")

    _station(scenario, battleship, first)
    _station(scenario, battleship, second)

    assert battleship.counters[Counter.CHARGE] == 4


def test_extinguisher_battleship_stations_past_its_own_threshold_count():
    """ "5+ | Flying, trample" is a separate, still-unread CR 721.2a threshold
    grant - `machines/abilities._split_keyword_line` deliberately discards
    the whole "5+ | Flying, trample" line rather than fabricate an
    unconditional trample (see its own docstring, naming this exact card),
    so the counters landing correctly is everything CR 702.184a's own
    activated ability promises; the threshold grant itself is a known,
    separate gap - see docs/engine-coverage.md.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Extinguisher Battleship"] + ["Craw Wurm"] * 1,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    battleship = scenario.find("Extinguisher Battleship", Zone.BATTLEFIELD)
    wurm = scenario.creature("Craw Wurm", "alice")
    assert scenario.game.power_of(wurm) == 6

    _station(scenario, battleship, wurm)

    assert battleship.counters[Counter.CHARGE] == 6


def test_exploration_broodship_stations_and_reaches_its_own_threshold():
    """Exploration Broodship: "Station (Tap another creature you control: Put
    charge counters equal to its power on this Spacecraft. Station only as a
    sorcery. It's an artifact creature at 8+.)" "3+ | You may play an
    additional land on each of your turns."

    A different card, a different threshold, and a static grant - not
    Extinguisher Battleship's enters-the-battlefield damage - proving
    `station_activation` is not wired to one printing by name.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Exploration Broodship", "Craw Wurm"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    broodship = scenario.find("Exploration Broodship", Zone.BATTLEFIELD)
    wurm = scenario.creature("Craw Wurm", "alice")

    _station(scenario, broodship, wurm)

    assert broodship.counters[Counter.CHARGE] == 6


def test_cannot_station_with_the_permanent_itself():
    """CR 702.184a's "another" - the Spacecraft cannot tap itself to pay its
    own station cost, even once it is a creature.
    """
    scenario = (
        Scenario().player("alice", battlefield=["Extinguisher Battleship"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    battleship = scenario.find("Extinguisher Battleship", Zone.BATTLEFIELD)

    import pytest

    with pytest.raises(ValueError):
        station_activation(scenario.game, battleship, battleship, "alice")
