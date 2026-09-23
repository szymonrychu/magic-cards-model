"""Scenario: "Put a `<kind>` counter on this `<noun>`. Then if there are N or
more `<kind>` counters on it, `<consequences>`." - a self counter that, once
it reaches a threshold, is spent to transform the permanent.

Reader under test: `machines/effects._parse_counter_threshold_whole_text`.
The consequence list is read item by item: "remove those counters" / "remove
all of them", "transform it" / "transform this `<noun>`", "untap it", and any
other clause the ordinary per-clause reader already knows ("create three
Treasure tokens").

Cards: **Treasure Map** (the listed card: "{1}, {T}: Scry 1. Put a landmark
counter on this artifact. Then if there are three or more landmark counters
on it, remove those counters, transform this artifact, and create three
Treasure tokens."); **Ludevic's Test Subject** (off-set, Modern-legal, not in
any deck: "{1}{U}: Put a hatchling counter on this creature. Then if there
are five or more hatchling counters on it, remove all of them and transform
it." - a different counter, threshold, noun, removal wording and no token).

Rules, each read with `mise run rules:find` in the session that wrote this
file:

- **CR 608.2c** - "Then if ..." is checked at that point of the resolution,
  after the counter has been put on.
- **CR 701.27a** - "To transform a permanent, turn it over so that its other
  face is up."
- **CR 111.10a** - a Treasure token's own mana ability.
- **CR 608.2h** - a source that has left the battlefield is read through
  its last known information. Treasure Map's own ruling (2017-09-29): with
  three landmark counters already on it when it left, "you'll get three
  Treasures"; and a third counter put on some other way does nothing until
  the ability next resolves.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

LANDMARK = "landmark"
HATCHLING = "hatchling"


def _map_board(library=("Island",) * 4):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Treasure Map"] + ["Wastes"] * 3, library=list(library))
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    treasure_map = scenario.find("Treasure Map", Zone.BATTLEFIELD, "alice")
    return scenario, treasure_map


def _activate_map(scenario, treasure_map):
    (wastes, *_) = scenario.untapped_sources("Wastes", username="alice")
    treasure_map.tapped = False
    scenario.scry_keeping_everything_on_top(username="alice")
    scenario.activate(treasure_map, wastes, index=0)
    scenario.pass_until_resolved()


def _treasures(scenario):
    return [
        permanent
        for permanent in scenario.game.battlefield
        if permanent.token and "Treasure" in scenario.game.characteristics_of(permanent).subtypes
    ]


def test_first_activation_scries_and_adds_one_landmark_counter():
    scenario, treasure_map = _map_board()

    _activate_map(scenario, treasure_map)

    assert treasure_map.counter_count(LANDMARK) == 1
    assert not treasure_map.transformed
    assert _treasures(scenario) == []


def test_third_activation_removes_the_counters_transforms_and_makes_three_treasures():
    scenario, treasure_map = _map_board()

    for _ in range(3):
        _activate_map(scenario, treasure_map)

    assert treasure_map.counter_count(LANDMARK) == 0
    assert treasure_map.transformed
    assert treasure_map.up_face_name == "Treasure Cove"
    assert len(_treasures(scenario)) == 3
    assert all(t.controller == "alice" for t in _treasures(scenario))


def test_two_counters_is_not_enough():
    scenario, treasure_map = _map_board()

    for _ in range(2):
        _activate_map(scenario, treasure_map)

    assert treasure_map.counter_count(LANDMARK) == 2
    assert not treasure_map.transformed
    assert _treasures(scenario) == []


def test_counters_from_elsewhere_do_nothing_until_the_ability_resolves():
    """The ruling: a third counter from some other source does not transform
    the Map by itself; the next activation finds four and spends them all."""
    scenario, treasure_map = _map_board()
    scenario.game.add_counters(treasure_map, LANDMARK, 3)

    assert not treasure_map.transformed
    _activate_map(scenario, treasure_map)

    assert treasure_map.counter_count(LANDMARK) == 0, "those counters - all four"
    assert treasure_map.transformed
    assert len(_treasures(scenario)) == 3


def test_the_map_leaving_with_two_counters_makes_nothing():
    scenario, treasure_map = _map_board()
    scenario.game.add_counters(treasure_map, LANDMARK, 2)
    (wastes, *_) = scenario.untapped_sources("Wastes", username="alice")
    scenario.scry_keeping_everything_on_top(username="alice")
    scenario.activate(treasure_map, wastes, index=0)
    scenario.game.return_to_hand(treasure_map)

    scenario.pass_until_resolved()

    assert treasure_map.zone is Zone.HAND
    assert _treasures(scenario) == []


def test_the_map_leaving_with_three_counters_still_makes_three_treasures():
    """The ruling's own case: last known information had three landmark
    counters, so the Treasures are still created (there is nothing left to
    remove counters from or transform)."""
    scenario, treasure_map = _map_board()
    scenario.game.add_counters(treasure_map, LANDMARK, 3)
    (wastes, *_) = scenario.untapped_sources("Wastes", username="alice")
    scenario.scry_keeping_everything_on_top(username="alice")
    scenario.activate(treasure_map, wastes, index=0)
    scenario.game.return_to_hand(treasure_map)

    scenario.pass_until_resolved()

    assert len(_treasures(scenario)) == 3


def test_treasure_cove_uses_the_treasures():
    """The back face works once the Map has turned: sacrifice a Treasure,
    draw a card."""
    scenario, treasure_map = _map_board()
    for _ in range(3):
        _activate_map(scenario, treasure_map)
    treasure_map.tapped = False
    hand_before = len(scenario.player("alice").hand)
    treasure = _treasures(scenario)[0]

    scenario.activate(treasure_map, index=1, sacrificing=[treasure])
    scenario.pass_until_resolved()

    assert treasure.zone is not Zone.BATTLEFIELD
    assert len(scenario.player("alice").hand) == hand_before + 1


# --------------------------------------------------------------------------
# Ludevic's Test Subject (off-set)
# --------------------------------------------------------------------------


def _subject_board():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ludevic's Test Subject"] + ["Island"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    subject = scenario.creature("Ludevic's Test Subject", "alice")
    return scenario, subject


def _feed(scenario, subject):
    islands = scenario.untapped_sources("Island", "Island", username="alice")
    scenario.activate(subject, *islands, index=0)
    scenario.pass_until_resolved()


def test_ludevics_fifth_counter_removes_them_all_and_transforms():
    scenario, subject = _subject_board()
    scenario.game.add_counters(subject, HATCHLING, 4)

    _feed(scenario, subject)

    assert subject.counter_count(HATCHLING) == 0
    assert subject.transformed
    assert scenario.game.characteristics_of(subject).power_toughness == (13, 13)


def test_ludevics_below_the_threshold_just_adds_a_counter():
    scenario, subject = _subject_board()
    scenario.game.add_counters(subject, HATCHLING, 2)

    _feed(scenario, subject)

    assert subject.counter_count(HATCHLING) == 3
    assert not subject.transformed
