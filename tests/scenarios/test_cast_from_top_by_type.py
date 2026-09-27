"""A permanent's static permission to play lands and cast spells of a named
quality from the top of its controller's library, with the "enters with an
additional +1/+1 counter" rider.

- **Mikey & Don, Party Planners** - "You may play lands and cast Mutant,
  Ninja, or Turtle spells from the top of your library. If you cast a
  creature spell this way, that creature enters with an additional +1/+1
  counter on it."
- **Traveling Chocobo** (second printing - legal in Modern, Pioneer and
  Standard, in no deck list) - "You may play lands and cast Bird spells from
  the top of your library." One subtype, no rider.
- **Elven Chorus** (third printing - Modern legal, in no deck list) - "You
  may cast creature spells from the top of your library." A card type and no
  land half. (The task named Vivien, Monsters' Advocate as the candidate; it
  carries the same line, but its two loyalty abilities are unread by this
  engine, so Elven Chorus - every line handled - stands in for it.)

Rules, each read with `mise run rules:find` in the session that wrote this file:

- **CR 601.3** - a spell can be cast only if a rule or effect allows it; the
  permission is the permanent's static ability (CR 611.3d).
- **CR 305.1** - the land half opens the land drop to the top of the library;
  it is still the one land drop of the turn.
- **CR 117.1a** - the permission changes where a spell is cast from, not when.
- **CR 614.1c** - "enters with" is a replacement effect.
- **CR 205.2b** - "Mutant, Ninja, or Turtle" is satisfied by any one of them.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

CAST_PERMISSION = "Cast permission"


def _resolve_everything(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _cast_top(scenario, caster="alice"):
    top = scenario.player(caster).library[0]
    return scenario.game.cast(
        top,
        caster,
        keyword=CAST_PERMISSION,
        mana_sources=scenario.game.permanents_controlled_by(caster),
    )


def _board(permanent, library, *, mana=("Plains", "Forest", "Forest"), bob_library=None):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[permanent, *mana],
            library=list(library),
        )
        .player("bob", library=list(bob_library or ["Island"] * 6))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _offered(scenario, card, kind=ActionKind.CAST):
    return any(
        action.kind is kind and getattr(action, "card_id", None) == card.id
        for action in legal_actions(scenario.game, "alice")
    )


# -- Mikey & Don: Mutant, Ninja, or Turtle, plus lands --------------------


def test_a_turtle_on_top_is_cast_and_enters_with_an_additional_counter():
    scenario = _board("Mikey & Don, Party Planners", ["Ambitious Augmenter", "Forest"])
    _cast_top(scenario)
    _resolve_everything(scenario)
    augmenter = scenario.find("Ambitious Augmenter", Zone.BATTLEFIELD, "alice")
    assert augmenter.counter_count(Counter.PLUS_ONE) == 1


def test_a_ninja_turtle_is_covered_by_any_one_of_the_three_words():
    scenario = _board("Mikey & Don, Party Planners", ["Leonardo, Leader in Blue", "Forest"])
    _cast_top(scenario)
    _resolve_everything(scenario)
    leonardo = scenario.find("Leonardo, Leader in Blue", Zone.BATTLEFIELD, "alice")
    assert leonardo.counter_count(Counter.PLUS_ONE) >= 1


def test_a_creature_of_another_type_on_top_is_not_covered():
    scenario = _board("Mikey & Don, Party Planners", ["Llanowar Elves", "Forest"])
    elves = scenario.player("alice").library[0]
    with pytest.raises(ValueError):
        _cast_top(scenario)
    assert elves.zone is Zone.LIBRARY
    assert scenario.player("alice").library[0] is elves


def test_only_the_top_card_is_reachable():
    scenario = _board("Mikey & Don, Party Planners", ["Forest", "Ambitious Augmenter"])
    second = scenario.player("alice").library[1]
    with pytest.raises(ValueError):
        scenario.game.cast(
            second,
            "alice",
            keyword=CAST_PERMISSION,
            mana_sources=scenario.game.permanents_controlled_by("alice"),
        )
    assert second.zone is Zone.LIBRARY


def test_a_land_on_top_is_played_as_the_land_drop():
    scenario = _board("Mikey & Don, Party Planners", ["Forest", "Forest"])
    first = scenario.player("alice").library[0]
    scenario.game.play_land(first, "alice")
    assert first.zone is Zone.BATTLEFIELD
    second = scenario.player("alice").library[0]
    with pytest.raises(ValueError):
        scenario.game.play_land(second, "alice")


def test_after_one_cast_the_new_top_card_is_available_too():
    scenario = _board(
        "Mikey & Don, Party Planners",
        ["Ambitious Augmenter", "Leonardo, Leader in Blue", "Forest"],
    )
    _cast_top(scenario)
    _resolve_everything(scenario)
    _cast_top(scenario)
    _resolve_everything(scenario)
    assert {"Ambitious Augmenter", "Leonardo, Leader in Blue"} <= set(scenario.battlefield_names())


def test_the_permission_keeps_the_spells_own_timing():
    scenario = _board("Mikey & Don, Party Planners", ["Ambitious Augmenter"])
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    with pytest.raises(ValueError):
        _cast_top(scenario)


def test_the_opponents_library_is_not_yours():
    scenario = _board(
        "Mikey & Don, Party Planners",
        ["Forest"],
        bob_library=["Ambitious Augmenter", "Island"],
    )
    theirs = scenario.player("bob").library[0]
    with pytest.raises(ValueError):
        scenario.game.cast(
            theirs,
            "alice",
            keyword=CAST_PERMISSION,
            mana_sources=scenario.game.permanents_controlled_by("alice"),
        )


def test_legal_actions_offer_the_top_card_and_a_land_on_top():
    scenario = _board("Mikey & Don, Party Planners", ["Ambitious Augmenter", "Forest"])
    assert _offered(scenario, scenario.player("alice").library[0])
    scenario = _board("Mikey & Don, Party Planners", ["Forest", "Ambitious Augmenter"])
    top = scenario.player("alice").library[0]
    assert _offered(scenario, top, ActionKind.PLAY_LAND)
    assert not _offered(scenario, scenario.player("alice").library[1])


def test_without_the_permission_the_top_card_is_not_offered():
    scenario = _board("Llanowar Elves", ["Ambitious Augmenter", "Forest"])
    assert not _offered(scenario, scenario.player("alice").library[0])
    with pytest.raises(ValueError):
        _cast_top(scenario)


def test_the_same_turtle_cast_from_hand_gets_no_extra_counter():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Mikey & Don, Party Planners", "Forest"],
            hand=["Ambitious Augmenter"],
            library=["Forest"] * 4,
        )
        .player("bob", library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    augmenter = scenario.find("Ambitious Augmenter", Zone.HAND, "alice")
    scenario.game.cast(
        augmenter, "alice", mana_sources=scenario.game.permanents_controlled_by("alice")
    )
    _resolve_everything(scenario)
    assert (
        scenario.find("Ambitious Augmenter", Zone.BATTLEFIELD, "alice").counter_count(
            Counter.PLUS_ONE
        )
        == 0
    )


# -- Traveling Chocobo: Bird spells and lands, no rider ----------------------


def test_chocobo_casts_a_bird_from_the_top_with_no_counter():
    scenario = _board("Traveling Chocobo", ["Birds of Paradise", "Forest"])
    _cast_top(scenario)
    _resolve_everything(scenario)
    birds = scenario.find("Birds of Paradise", Zone.BATTLEFIELD, "alice")
    assert birds.counter_count(Counter.PLUS_ONE) == 0


def test_chocobo_does_not_cover_a_non_bird():
    scenario = _board("Traveling Chocobo", ["Llanowar Elves", "Forest"])
    with pytest.raises(ValueError):
        _cast_top(scenario)


def test_chocobo_plays_a_land_from_the_top():
    scenario = _board("Traveling Chocobo", ["Forest", "Forest"])
    top = scenario.player("alice").library[0]
    scenario.game.play_land(top, "alice")
    assert top.zone is Zone.BATTLEFIELD


# -- Elven Chorus: creature spells, no lands --------------------------------


def test_elven_chorus_casts_a_creature_from_the_top():
    scenario = _board("Elven Chorus", ["Llanowar Elves", "Forest"])
    _cast_top(scenario)
    _resolve_everything(scenario)
    assert "Llanowar Elves" in scenario.battlefield_names()


def test_elven_chorus_does_not_cover_a_noncreature_spell():
    scenario = _board("Elven Chorus", ["Giant Growth", "Forest"])
    with pytest.raises(ValueError):
        _cast_top(scenario)


def test_elven_chorus_grants_no_land_drop_from_the_top():
    scenario = _board("Elven Chorus", ["Forest", "Llanowar Elves"])
    with pytest.raises(ValueError):
        scenario.game.play_land(scenario.player("alice").library[0], "alice")
