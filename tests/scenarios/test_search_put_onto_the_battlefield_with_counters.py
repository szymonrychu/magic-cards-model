"""A library search whose find is put onto the battlefield "with N `<kind>`
counters on it".

"Tap seven untapped Officers you control: Search your library for a Spacecraft
card, put it onto the battlefield with seven charge counters on it, then
shuffle." (Captain Jean-Luc Picard) and "Search your library for a creature card
with mana value equal to 1 plus the sacrificed creature's mana value, put that
card onto the battlefield with an additional +1/+1 counter on it, then
shuffle." (Neoform) share one counters tail: a count (a word, "a", "an", with or
without "additional") and a counter kind, riding on the find as it arrives.

- **CR 701.23a** - to search, look at the zone and find a card matching the
  description.
- **CR 701.23b** - a stated quality (a Spacecraft, a creature) never has to be
  found, so finding nothing is legal.
- **CR 614.1c** - effects reading "enters with ..." are replacement effects:
  the counters are on the permanent as it arrives, so a threshold that reads
  them (CR 702.184a's station lines, "It's an artifact creature at 4+") is met
  the moment the permanent exists, and its enters trigger sees the counters.
- **CR 122.1** / **CR 122.1a** - counters are markers; a +1/+1 counter adds to
  power and toughness.
- **CR 602.2b** - the cost (tapping seven Officers) is paid as the ability is
  activated, whatever the search then finds.
- **CR 701.26a** - only untapped permanents can be tapped.
- **CR 701.23e** - no "reveal" in the text, so nothing is revealed.

Neoform is the differently worded proof: a different cost shape (a spell's
sacrifice), a different find (a creature by mana value), a different counter
kind and an "additional" in the tail, on the same reader. Every CR number above
was read in full from `mise run rules:find` in the session that wrote this
file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Color, Type, Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import TokenDefinition, create_tokens
from tests.scenarios.harness import PlayedScenario, Scenario

#: Picard's own "1/1 red Officer creature token".
OFFICER = TokenDefinition(subtypes=("Officer",), colors=(Color.RED,), power=1, toughness=1)
SPACECRAFT_LIBRARY = [
    "Wurmwall Sweeper",
    "Fell Gravship",
    "Lumen-Class Frigate",
    "Plains",
    "Grizzly Bears",
]
PICARD = "Captain Jean-Luc Picard"


def _picard_board(library=None, *, operatives=3, tokens=3, bob=None) -> PlayedScenario:
    """Picard is himself an Officer, so he and six more make seven."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[PICARD] + ["Obsidian Order Operative"] * operatives,
            library=library or SPACECRAFT_LIBRARY,
        )
        .player("bob", library=bob or ["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for _ in range(tokens):
        create_tokens(scenario.game, OFFICER, "alice")
    return scenario


def _officers(scenario: PlayedScenario):
    return [
        card
        for card in scenario.game.battlefield
        if "Officer" in card.subtypes and card.controller == "alice"
    ]


def _chargers(scenario: PlayedScenario):
    return [card for card in scenario.game.battlefield if Counter.CHARGE in card.counters]


def _fetch(scenario: PlayedScenario, *, chosen=None):
    scenario.will_choose_cards(
        *([chosen] if chosen is not None else []), username="alice", source=PICARD
    )
    picard = scenario.find(PICARD, Zone.BATTLEFIELD, "alice")
    officers = _officers(scenario)
    scenario.activate(picard, index=0, tapping_for_cost=officers)
    scenario.pass_until_resolved()
    return officers


def _types(scenario: PlayedScenario, permanent):
    return scenario.game.characteristics_of(permanent).types


def test_the_chosen_spacecraft_arrives_with_seven_charge_counters():
    scenario = _picard_board()
    sweeper = scenario.find("Wurmwall Sweeper", Zone.LIBRARY, "alice")

    _fetch(scenario, chosen=sweeper)

    assert sweeper.zone is Zone.BATTLEFIELD
    assert sweeper.counters[Counter.CHARGE] == 7
    assert _chargers(scenario) == [sweeper], "only the find carries counters"


def test_the_counters_are_there_when_it_arrives_so_a_threshold_is_already_met():
    """Wurmwall Sweeper is an artifact creature with flying at 4+ charge
    counters; seven on arrival make it one at once (CR 614.1c)."""
    scenario = _picard_board()
    sweeper = scenario.find("Wurmwall Sweeper", Zone.LIBRARY, "alice")

    _fetch(scenario, chosen=sweeper)

    assert Type.CREATURE in _types(scenario, sweeper)


def test_a_higher_threshold_is_not_met_by_seven():
    """Fell Gravship becomes a creature at 8+ charge counters: seven is one
    short, so it stays a plain artifact."""
    scenario = _picard_board()
    gravship = scenario.find("Fell Gravship", Zone.LIBRARY, "alice")

    _fetch(scenario, chosen=gravship)

    assert gravship.counters[Counter.CHARGE] == 7
    assert Type.CREATURE not in _types(scenario, gravship)


def test_the_cost_taps_all_seven_officers_cards_and_tokens_alike():
    scenario = _picard_board()
    sweeper = scenario.find("Wurmwall Sweeper", Zone.LIBRARY, "alice")

    officers = _fetch(scenario, chosen=sweeper)

    assert len(officers) == 7
    assert all(officer.tapped for officer in officers)


def test_the_enters_trigger_of_the_find_fires():
    """CR 603.6a: the Spacecraft entered, so its own enters trigger fires.
    Wurmwall Sweeper surveils 2."""
    scenario = _picard_board()
    sweeper = scenario.find("Wurmwall Sweeper", Zone.LIBRARY, "alice")

    _fetch(scenario, chosen=sweeper)
    scenario.pass_until_resolved()  # the trigger the arrival put on the stack

    assert [
        question
        for question in scenario.questions_asked()
        if question.kind is DecisionKind.SURVEIL and question.source == "Wurmwall Sweeper"
    ]


def test_only_a_spacecraft_qualifies():
    scenario = _picard_board(library=["Plains", "Grizzly Bears", "Fell Gravship"])
    gravship = scenario.find("Fell Gravship", Zone.LIBRARY, "alice")

    _fetch(scenario, chosen=gravship)

    (question,) = [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_CARDS]
    assert [scenario.game.find_by_id(card_id).name for card_id in question.cards] == [
        "Fell Gravship"
    ]


def test_finding_nothing_is_legal_and_the_cost_is_still_paid():
    """CR 701.23b: a stated quality need not be found, and CR 602.2b's cost was
    paid on activation regardless."""
    scenario = _picard_board()

    officers = _fetch(scenario)

    assert all(officer.tapped for officer in officers)
    assert _chargers(scenario) == []
    assert len(scenario.player("alice").library) == len(SPACECRAFT_LIBRARY)


def test_a_library_without_a_spacecraft_finds_nothing():
    scenario = _picard_board(library=["Plains", "Grizzly Bears"])

    _fetch(scenario)

    assert _chargers(scenario) == []
    assert sorted(c.name for c in scenario.player("alice").library) == ["Grizzly Bears", "Plains"]


def test_six_untapped_officers_cannot_pay_the_cost():
    """CR 701.26a: only untapped permanents can be tapped - with one Officer
    already tapped there are six, one short of the seven required."""
    scenario = _picard_board()
    officers = _officers(scenario)
    officers[3].tapped = True
    picard = scenario.find(PICARD, Zone.BATTLEFIELD, "alice")

    with pytest.raises(ValueError):
        scenario.activate(picard, index=0, tapping_for_cost=officers)

    assert _chargers(scenario) == []


def test_the_opponents_library_is_not_searched():
    scenario = _picard_board(bob=["Wurmwall Sweeper", "Plains"])

    _fetch(scenario)

    assert scenario.find("Wurmwall Sweeper", Zone.LIBRARY, "bob")


def test_the_find_is_not_revealed():
    """CR 701.23e: Picard's text has no "reveal", so nothing is shown."""
    scenario = _picard_board()
    sweeper = scenario.find("Wurmwall Sweeper", Zone.LIBRARY, "alice")

    _fetch(scenario, chosen=sweeper)

    assert scenario.game.reveals == []


# -- Neoform: the same tail, written differently ---------------------------------


def _neoform(*library: str) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Neoform"],
            battlefield=["Island", "Forest", "Grizzly Bears"],
            library=list(library),
        )
        .player("bob", library=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_neoform_s_additional_plus_one_counter_rides_the_same_tail():
    """Grizzly Bears is mana value 2, so the find has mana value 3: Gray Ogre
    (2/2) arrives with its additional +1/+1 counter, a 3/3 (CR 122.1a)."""
    scenario = _neoform("Hill Giant", "Gray Ogre", "Plains")
    bears = scenario.creature("Grizzly Bears", "alice")
    ogre = scenario.find("Gray Ogre", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(ogre, username="alice", source="Neoform")

    scenario.cast_and_resolve(
        "Neoform", *scenario.untapped_sources("Island", "Forest"), sacrificing=[bears]
    )

    assert ogre.zone is Zone.BATTLEFIELD
    assert ogre.counters[Counter.PLUS_ONE] == 1
    assert (ogre.power, ogre.toughness) == (3, 3)


def test_neoform_finding_nothing_leaves_no_counters_anywhere():
    scenario = _neoform("Hill Giant", "Plains")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_cards(username="alice", source="Neoform")

    scenario.cast_and_resolve(
        "Neoform", *scenario.untapped_sources("Island", "Forest"), sacrificing=[bears]
    )

    assert not [c for c in scenario.game.battlefield if Counter.PLUS_ONE in c.counters]
