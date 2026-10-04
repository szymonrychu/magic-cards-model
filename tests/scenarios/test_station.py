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
from magic_cards_model.machines.combat import has_keyword
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
    """CR 702.184a puts on the tapped creature's whole power, not just enough
    to reach the threshold; what "5+ | Flying, trample" then grants is
    covered by the CR 721.2 tests below.
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


# --------------------------------------------------------------------------
# CR 721.2: the station symbols themselves - "{N+}[abilities]" and
# "{N+}[abilities][P/T]" - read off the printed striation and gated on the
# permanent's own charge counters.
# --------------------------------------------------------------------------


def _types(scenario, permanent):
    return {t.value for t in scenario.game.characteristics_of(permanent).types}


def test_extinguisher_battleship_is_not_a_creature_below_its_threshold():
    """CR 721.2b: "As long as this permanent has N or more charge counters on
    it, it has [abilities] and is a creature" - four counters are not five."""
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
    assert not scenario.game.characteristics_of(battleship).is_creature
    assert not has_keyword(battleship, "flying", scenario.game)
    assert not has_keyword(battleship, "trample", scenario.game)


def test_extinguisher_battleship_is_a_ten_ten_flying_trampler_at_five():
    """The reported bug: "5+ | Flying, trample" with the 10/10 box in the same
    striation (CR 721.2b) - stationed past five, the Battleship is an artifact
    creature with base power and toughness 10/10, flying and trample, and the
    line is read rather than recorded as unreadable."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Extinguisher Battleship", "Craw Wurm"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    battleship = scenario.find("Extinguisher Battleship", Zone.BATTLEFIELD)
    wurm = scenario.creature("Craw Wurm", "alice")

    _station(scenario, battleship, wurm)

    chars = scenario.game.characteristics_of(battleship)
    assert chars.is_creature
    assert {"artifact", "creature"} <= _types(scenario, battleship)
    assert (scenario.game.power_of(battleship), scenario.game.toughness_of(battleship)) == (10, 10)
    assert has_keyword(battleship, "flying", scenario.game)
    assert has_keyword(battleship, "trample", scenario.game)
    assert not scenario.game.keyword_line_notices


def test_fell_gravship_reaches_its_eight_plus_striation_only_at_eight():
    """Fell Gravship: "8+ | Flying, lifelink" over a 3/2 box - a different
    threshold, different keywords, a different P/T, and a Scryfall keyword
    list that names neither flying nor lifelink."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Fell Gravship", "Craw Wurm", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gravship = scenario.find("Fell Gravship", Zone.BATTLEFIELD)
    wurm = scenario.creature("Craw Wurm", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    _station(scenario, gravship, wurm)
    assert gravship.counters[Counter.CHARGE] == 6
    assert not scenario.game.characteristics_of(gravship).is_creature
    assert not has_keyword(gravship, "lifelink", scenario.game)

    _station(scenario, gravship, bears)
    assert gravship.counters[Counter.CHARGE] == 8
    assert scenario.game.characteristics_of(gravship).is_creature
    assert (scenario.game.power_of(gravship), scenario.game.toughness_of(gravship)) == (3, 2)
    assert has_keyword(gravship, "flying", scenario.game)
    assert has_keyword(gravship, "lifelink", scenario.game)


def test_exploration_broodship_grants_its_land_drop_at_three_and_is_a_creature_at_eight():
    """Exploration Broodship's two striations: "3+ | You may play an
    additional land on each of your turns." is a CR 721.2a symbol with no
    P/T box (CR 611.3d's rule-changing grant, not a creature), and
    "8+ | Flying" carries the 4/4 box (CR 721.2b)."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Exploration Broodship", "Craw Wurm", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    broodship = scenario.find("Exploration Broodship", Zone.BATTLEFIELD)
    wurm = scenario.creature("Craw Wurm", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    assert scenario.game.land_allowance("alice") == 1

    _station(scenario, broodship, bears)
    assert broodship.counters[Counter.CHARGE] == 2
    assert scenario.game.land_allowance("alice") == 1

    _station(scenario, broodship, wurm)
    assert broodship.counters[Counter.CHARGE] == 8
    assert scenario.game.land_allowance("alice") == 2
    assert scenario.game.characteristics_of(broodship).is_creature
    assert (scenario.game.power_of(broodship), scenario.game.toughness_of(broodship)) == (4, 4)
    assert has_keyword(broodship, "flying", scenario.game)


def test_exploration_broodship_land_drop_without_the_creature_striation():
    """Three to seven counters: the 3+ grant is on, the 8+ striation (and its
    P/T box) is not - each symbol is its own static ability (CR 721.2)."""
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
    assert scenario.game.land_allowance("alice") == 2
    assert not scenario.game.characteristics_of(broodship).is_creature
    assert not has_keyword(broodship, "flying", scenario.game)


def test_a_planets_twelve_plus_mana_ability_needs_twelve_counters():
    """Evendo, Waking Haven: "12+ | {G}, {T}: Add {G} for each creature you
    control." - a land with no P/T box (a Planet never becomes a creature),
    whose striation holds an activated ability. Below twelve the land has
    only its own "{T}: Add {G}"; at twelve it has the second ability too."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Evendo, Waking Haven", "Craw Wurm", "Craw Wurm", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    evendo = scenario.find("Evendo, Waking Haven", Zone.BATTLEFIELD)
    first, second = scenario.creatures("Craw Wurm", "Craw Wurm", username="alice")
    game = scenario.game

    def station_line():
        return [
            index
            for index, ability in enumerate(game.activated_abilities(evendo))
            if "for each creature you control" in ability.text
        ]

    _station(scenario, evendo, first)
    assert evendo.counters[Counter.CHARGE] == 6
    assert station_line() == []

    _station(scenario, evendo, second)
    assert evendo.counters[Counter.CHARGE] == 12
    (index,) = station_line()
    ability = game.activated_abilities(evendo)[index]
    assert "12+" not in ability.raw
    assert not scenario.game.characteristics_of(evendo).is_creature

    (forest,) = scenario.untapped_sources("Forest")
    scenario.activate(evendo, forest, index=index)
    assert evendo.tapped
    assert game.player("alice").mana_pool.total == 2, "one {G} per creature (two Wurms)"


def test_the_seriemas_seven_plus_striation_carries_its_second_line():
    """The Seriema: "7+ | Flying" then "Other tapped legendary creatures you
    control have indestructible." - CR 721.2: every ability printed within
    the striation is part of the symbol's static ability, so the second line
    is off below seven and on at seven."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Seriema", "Craw Wurm", "Isamaru, Hound of Konda"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    seriema = scenario.find("The Seriema", Zone.BATTLEFIELD)
    wurm = scenario.creature("Craw Wurm", "alice")
    isamaru = scenario.creature("Isamaru, Hound of Konda", "alice")
    isamaru.tap()

    _station(scenario, seriema, wurm)
    assert seriema.counters[Counter.CHARGE] == 6
    assert not has_keyword(isamaru, "indestructible", scenario.game)
    assert not has_keyword(seriema, "flying", scenario.game)

    scenario.game.add_counters(seriema, Counter.CHARGE, 1)
    assert seriema.counters[Counter.CHARGE] == 7
    assert has_keyword(isamaru, "indestructible", scenario.game)
    assert wurm.tapped
    assert not has_keyword(wurm, "indestructible", scenario.game), "CR 205.4a: not legendary"
    assert has_keyword(seriema, "flying", scenario.game)
    assert scenario.game.characteristics_of(seriema).is_creature


def test_station_is_offered_with_the_creatures_that_can_pay_it():
    """CR 702.184a's cost, "Tap another untapped creature you control": the
    engine names the candidates the way it names crew's, so a seat can be
    shown the ability at all - excluding the Spacecraft itself, a tapped
    creature, and an opponent's creature."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Extinguisher Battleship", "Grizzly Bears", "Craw Wurm"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    battleship = scenario.find("Extinguisher Battleship", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "alice")
    wurm = scenario.creature("Craw Wurm", "alice")
    wurm.tap()

    offers = scenario.game.object_cost_offers(battleship, "alice")

    assert offers["station"].rule == "CR 702.184a"
    assert [card.id for card in offers["station"].candidates] == [bears.id]


def test_station_only_as_a_sorcery():
    """CR 702.184a: "Activate only as a sorcery." - refused in combat."""
    import pytest

    scenario = (
        Scenario()
        .player("alice", battlefield=["Extinguisher Battleship", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    battleship = scenario.find("Extinguisher Battleship", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "alice")

    activation = station_activation(scenario.game, battleship, bears, "alice")
    with pytest.raises(ValueError, match="sorcery"):
        activation.begin_paying()
        activation.payment.pay()
        activation.activate()


def test_uthros_adds_one_blue_per_artifact_at_twelve():
    """Uthros, Titanic Godcore: "12+ | {U}, {T}: Add {U} for each artifact you
    control." - the other Planet, a different colour and a different count,
    read by the same "Add {symbol} for each ..." mana shape."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Uthros, Titanic Godcore",
                "Craw Wurm",
                "Craw Wurm",
                "Island",
                "Extinguisher Battleship",
                "Fell Gravship",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    uthros = scenario.find("Uthros, Titanic Godcore", Zone.BATTLEFIELD)
    first, second = scenario.creatures("Craw Wurm", "Craw Wurm", username="alice")
    game = scenario.game

    _station(scenario, uthros, first)
    _station(scenario, uthros, second)
    assert uthros.counters[Counter.CHARGE] == 12

    (index,) = [
        index
        for index, ability in enumerate(game.activated_abilities(uthros))
        if "for each artifact you control" in ability.text
    ]
    (island,) = scenario.untapped_sources("Island")
    scenario.activate(uthros, island, index=index)
    assert game.player("alice").mana_pool.total == 2, "two artifacts: two {U}"
