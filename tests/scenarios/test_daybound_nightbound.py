"""Scenario: daybound and nightbound (CR 702.145) - the keyword pair on the
two faces of a day/night double-faced card, driven by the game's day/night
designation (CR 731).

Printings (Modern, Pioneer; none in an api deck):

- **Tavern Ruffian // Tavern Smasher** - vanilla 2/5 daybound, 6/5 nightbound:
  the keyword pair with nothing else on either face.
- **Brutal Cathar // Moonrage Brute** - "Whenever this creature enters or
  transforms into Brutal Cathar, exile target creature an opponent controls
  until this creature leaves the battlefield." / first strike, ward - pay 3
  life. The transform the day/night change performs is a real one (CR
  701.27e's "transforms into" fires on it).
- **Reckless Stormseeker // Storm-Charged Slasher** - a beginning-of-combat
  trigger on each face, so which face is up decides which one fires.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 702.145b** - daybound: "If it is night and this permanent is
  represented by a double-faced card, it enters transformed," "As it becomes
  night, if this permanent is front face up, transform it," and "This
  permanent can't transform except due to its daybound ability."
- **CR 702.145d** - "Any time a player controls a permanent with daybound, if
  it's neither day nor night, it becomes day."
- **CR 702.145e** - nightbound: "As it becomes day, if this permanent is back
  face up, transform it" and "This permanent can't transform except due to
  its nightbound ability."
- **CR 702.145g** - "Any time a player controls a permanent with nightbound,
  if it's neither day nor night and there are no permanents with daybound on
  the battlefield, it becomes night."
- **CR 701.27e** - "transforms into" triggers when the object transforms and
  has the characteristic immediately after.
- **CR 731.2a / CR 731.2b** - the untap step's check that changes the
  designation.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import transform_permanent
from magic_cards_model.models import Zone
from magic_cards_model.models.game import DayNight
from tests.scenarios.harness import PlayedScenario, Scenario

RUFFIAN = "Tavern Ruffian"
SMASHER = "Tavern Smasher"
CATHAR = "Brutal Cathar"
BRUTE = "Moonrage Brute"
STORMSEEKER = "Reckless Stormseeker"
SLASHER = "Storm-Charged Slasher"


def _resolve_everything(scenario: PlayedScenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.stack_names():
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def _to_next_upkeep(scenario: PlayedScenario) -> None:
    taken = scenario.game.turn.turns_taken
    while not (scenario.step is Step.UPKEEP and scenario.game.turn.turns_taken != taken):
        if scenario.game.step_grants_priority and (
            scenario.stack_names() or scenario.game.pending_triggers
        ):
            _resolve_everything(scenario)
            continue
        scenario.advance()


def _board(*, alice_hand=(), alice_battlefield=(), bob_battlefield=(), bob_hand=()):
    return (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Plains",
                *alice_battlefield,
            ],
            hand=list(alice_hand),
            library=["Mountain"] * 12,
        )
        .player(
            "bob",
            battlefield=["Plains", "Plains", *bob_battlefield],
            hand=list(bob_hand),
            library=["Plains"] * 12,
        )
        .build()
    )


def _mountains(scenario: PlayedScenario, count: int):
    return scenario.untapped_sources(*["Mountain"] * count, username="alice")


# -- entering (CR 702.145b, 702.145d, 702.145g) -----------------------------------


def test_a_daybound_permanent_entering_when_neither_makes_it_day():
    scenario = _board(alice_hand=[RUFFIAN])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ruffian = scenario.cast_and_resolve(RUFFIAN, *_mountains(scenario, 4))
    assert scenario.game.day_night is DayNight.DAY
    assert ruffian.name == RUFFIAN


def test_a_daybound_card_cast_at_night_enters_transformed():
    scenario = _board(alice_hand=[RUFFIAN])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.become_night()
    scenario.cast_and_resolve(RUFFIAN, *_mountains(scenario, 4))
    smasher = scenario.creature(SMASHER, "alice")
    assert smasher.transformed
    assert (smasher.power, smasher.toughness) == (6, 5)
    assert scenario.game.day_night is DayNight.NIGHT


def test_a_daybound_card_cast_by_day_enters_front_face_up():
    scenario = _board(alice_hand=[RUFFIAN])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.become_day()
    ruffian = scenario.cast_and_resolve(RUFFIAN, *_mountains(scenario, 4))
    assert not ruffian.transformed
    assert (ruffian.power, ruffian.toughness) == (2, 5)


def test_a_nightbound_permanent_alone_when_neither_makes_it_night():
    """CR 702.145g: nightbound with no daybound permanent around."""
    scenario = _board(alice_hand=[RUFFIAN])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ruffian = scenario.player("alice").hand[0]
    scenario.game.put_onto_battlefield(ruffian, "alice", transformed=True)
    assert ruffian.name == SMASHER
    assert scenario.game.day_night is DayNight.NIGHT


def test_a_nightbound_permanent_entering_beside_a_daybound_one_makes_it_day():
    """CR 702.145g's "no permanents with daybound" fails, and CR 702.145d then
    makes it day - which turns the nightbound one to its front face."""
    scenario = _board(alice_hand=[RUFFIAN, RUFFIAN])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.player("alice").hand[:2]
    with scenario.game.entering_together():
        scenario.game.put_onto_battlefield(first, "alice")
        scenario.game.put_onto_battlefield(second, "alice", transformed=True)
    assert scenario.game.day_night is DayNight.DAY
    assert first.name == RUFFIAN
    assert second.name == RUFFIAN


def test_a_brute_entering_at_night_does_not_fire_the_cathars_enters_trigger():
    """Cast at night, Brutal Cathar enters as Moonrage Brute (CR 702.145b), a
    face with no "enters" ability - nothing is exiled."""
    scenario = _board(alice_hand=[CATHAR], bob_battlefield=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.become_night()
    scenario.cast_and_resolve(
        CATHAR, *_mountains(scenario, 2), *scenario.untapped_sources("Plains", username="alice")
    )
    scenario.game.put_triggers_on_stack()
    assert scenario.creature(BRUTE, "alice").transformed
    assert scenario.stack_names() == []
    assert scenario.creature("Grizzly Bears", "bob").zone is Zone.BATTLEFIELD


# -- the change itself transforms (CR 702.145b, 702.145e) -----------------------


def test_day_becoming_night_transforms_a_front_face_daybound_permanent():
    scenario = _board(alice_hand=[RUFFIAN])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ruffian = scenario.player("alice").hand[0]
    scenario.game.put_onto_battlefield(ruffian, "alice")  # no spell cast
    _to_next_upkeep(scenario)
    assert scenario.game.day_night is DayNight.NIGHT
    assert ruffian.name == SMASHER
    assert (ruffian.power, ruffian.toughness) == (6, 5)


def test_night_becoming_day_transforms_it_back():
    scenario = _board(alice_hand=["Memnite", "Ornithopter"], alice_battlefield=[RUFFIAN])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.become_night()
    smasher = scenario.creature(SMASHER, "alice")
    scenario.cast_and_resolve("Memnite")
    scenario.cast_and_resolve("Ornithopter")
    _to_next_upkeep(scenario)
    assert scenario.game.day_night is DayNight.DAY
    assert smasher.name == RUFFIAN
    assert not smasher.transformed


def test_both_players_permanents_transform_on_the_change():
    scenario = _board(alice_battlefield=[RUFFIAN], bob_battlefield=[RUFFIAN])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.state_based_actions()  # CR 702.145d is checked "any time"
    assert scenario.game.day_night is DayNight.DAY
    _to_next_upkeep(scenario)
    assert scenario.creature(SMASHER, "alice").transformed
    assert scenario.creature(SMASHER, "bob").transformed


def test_turning_to_the_night_face_is_a_real_transform_that_counts():
    scenario = _board(alice_battlefield=[RUFFIAN])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ruffian = scenario.creature(RUFFIAN, "alice")
    before = ruffian.times_transformed
    _to_next_upkeep(scenario)
    assert ruffian.times_transformed == before + 1


def test_night_becoming_day_fires_the_cathars_transforms_into_trigger():
    """CR 701.27e: Moonrage Brute turning back into Brutal Cathar is a
    "transforms into Brutal Cathar" event."""
    scenario = _board(
        alice_hand=["Memnite", "Ornithopter", CATHAR], bob_battlefield=["Grizzly Bears"]
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.become_night()
    scenario.cast_and_resolve(
        CATHAR, *_mountains(scenario, 2), *scenario.untapped_sources("Plains", username="alice")
    )
    scenario.cast_and_resolve("Memnite")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_targets(bears, source=CATHAR)
    _to_next_upkeep(scenario)
    assert scenario.game.day_night is DayNight.DAY
    _resolve_everything(scenario)
    assert scenario.creature(CATHAR, "alice").name == CATHAR
    assert bears.zone is Zone.EXILE


def test_day_becoming_night_gives_the_brute_its_night_face_abilities():
    scenario = _board(alice_battlefield=[CATHAR])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _to_next_upkeep(scenario)
    brute = scenario.creature(BRUTE, "alice")
    assert "First strike" in brute.keywords
    assert (brute.power, brute.toughness) == (3, 3)


def test_stormseekers_night_face_trigger_fires_at_night():
    scenario = _board(alice_battlefield=[STORMSEEKER])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _to_next_upkeep(scenario)  # bob's turn: night
    _to_next_upkeep(scenario)  # alice's turn, still night (bob cast nothing -> stays night)
    assert scenario.game.day_night is DayNight.NIGHT
    slasher = scenario.creature(SLASHER, "alice")
    scenario.will_choose_targets(slasher, source=SLASHER)
    while scenario.step is not Step.BEGINNING_OF_COMBAT:
        scenario.advance()
    _resolve_everything(scenario)
    assert slasher.power == 3 + 2


# -- "can't transform except due to its daybound/nightbound ability" --------------


def test_another_transform_effect_does_nothing_to_a_daybound_permanent():
    scenario = _board(alice_battlefield=[RUFFIAN])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ruffian = scenario.creature(RUFFIAN, "alice")
    transform_permanent(scenario.game, ruffian)
    assert ruffian.name == RUFFIAN
    assert not ruffian.transformed


def test_another_transform_effect_does_nothing_to_a_nightbound_permanent():
    scenario = _board(alice_battlefield=[RUFFIAN])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.become_night()
    smasher = scenario.creature(SMASHER, "alice")
    transform_permanent(scenario.game, smasher)
    assert smasher.name == SMASHER


def test_moonmist_cannot_transform_a_daybound_human():
    """Moonmist: "Transform all Humans." Tavern Ruffian is a Human, but daybound
    lets only itself turn it over."""
    scenario = _board(alice_battlefield=[RUFFIAN, "Forest", "Forest"], alice_hand=["Moonmist"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ruffian = scenario.creature(RUFFIAN, "alice")
    scenario.cast_and_resolve("Moonmist", *scenario.untapped_sources("Forest", "Forest"))
    assert ruffian.name == RUFFIAN


# -- the designation outlives the permanents ---------------------------------------


def test_the_designation_stays_after_the_daybound_permanent_leaves():
    scenario = _board(alice_battlefield=[RUFFIAN])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.state_based_actions()  # CR 702.145d: day, while the Ruffian is here
    scenario.game.destroy(scenario.creature(RUFFIAN, "alice"))
    _to_next_upkeep(scenario)
    assert scenario.game.day_night is DayNight.NIGHT
