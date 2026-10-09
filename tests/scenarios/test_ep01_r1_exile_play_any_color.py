"""Playing cards out of a permanent's own exile pile while spending mana as
though it were mana of any color (EP-01 round 1, task T7).

    Rogue Class (level 3) - "You may play cards exiled with this Class, and you
        may spend mana as though it were mana of any color to cast those
        spells."
    Evelyn, the Covetous - "Once each turn, you may play a card from exile with
        a collection counter on it if it was exiled by an ability you
        controlled, and you may spend mana as though it were mana of any color
        to cast it."

Both exile triggers (the face-down exile on combat damage, the collection
counter exile) are other epics' work; each test seeds the pile the trigger
would have made - a card in exile, annotated as exiled with the permanent
(CR 607.2a).

- CR 601.1a / CR 406.3a: playing a card is casting it or playing it as a land;
  a face-down exiled card is turned face up as it is played.
- CR 609.4b: the any-color permission changes how mana is spent, not the cost,
  and reaches only the spells the sentence names.
- CR 716.2a: a level paragraph is in effect only at that level.
"""

import pytest

from magic_cards_model.machines import Step, payability
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import ExileAnnotation, ExileMarker
from tests.scenarios.harness import Scenario


def _pile(scenario, permanent, name, *, face_up=True, counter=None):
    card = scenario.find(name, Zone.EXILE)
    card.exile_annotation = ExileAnnotation(
        marker=ExileMarker.LINKED,
        owner=card.owner,
        turn_exiled=1,
        linked_permanent_id=permanent.id,
        linked_permanent_stamp=permanent.zone_change_stamp,
    )
    card.face_up = face_up
    if counter is not None:
        card.add_counters(counter)
    return card


def _rogue(level, *, hand=(), exile=("Lightning Bolt",), face_up=False):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Rogue Class", "Island"],
            hand=list(hand),
            exile=list(exile),
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rogue = scenario.find("Rogue Class", Zone.BATTLEFIELD, "alice")
    rogue.class_level = level
    return scenario, rogue, [_pile(scenario, rogue, n, face_up=face_up) for n in exile]


def _can_pay(scenario, card, username="alice") -> bool:
    return payability(scenario.game, username, card).payable


def test_rogue_class_level_3_casts_a_face_down_exiled_card_with_any_mana():
    scenario, _rogue_class, (bolt,) = _rogue(3)
    assert _can_pay(scenario, bolt), "Island mana pays Lightning Bolt's {R} (CR 609.4b)"
    scenario.game.cast(
        bolt,
        "alice",
        keyword="Cast permission",
        targets=["bob"],
        mana_sources=scenario.game.permanents_controlled_by("alice"),
    )
    assert scenario.find("Lightning Bolt", Zone.STACK).face_up  # CR 406.3a
    assert scenario.find("Island", Zone.BATTLEFIELD, "alice").tapped


def test_rogue_class_below_level_3_grants_nothing():
    scenario, _rogue_class, (bolt,) = _rogue(2)
    assert not _can_pay(scenario, bolt)
    assert scenario.game.spends_mana_as_any_color_for_spell(bolt, "alice") is False


def test_rogue_class_any_color_does_not_reach_a_hand_spell():
    scenario, _rogue_class, _pile_cards = _rogue(3, hand=["Shock"])
    shock = scenario.find("Shock", Zone.HAND, "alice")
    assert not _can_pay(scenario, shock)


def test_rogue_class_only_reaches_cards_exiled_with_it():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Rogue Class", "Island"], exile=["Lightning Bolt"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.find("Rogue Class", Zone.BATTLEFIELD, "alice").class_level = 3
    bolt = scenario.find("Lightning Bolt", Zone.EXILE)
    assert not _can_pay(scenario, bolt)


def _evelyn(*, exile=("Lightning Bolt", "Shock"), lands=("Island",)):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Evelyn, the Covetous", *lands], exile=list(exile))
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    evelyn = scenario.find("Evelyn, the Covetous", Zone.BATTLEFIELD, "alice")
    return scenario, evelyn


def test_evelyn_plays_a_collection_counter_card_with_any_mana():
    scenario, evelyn = _evelyn()
    bolt = _pile(scenario, evelyn, "Lightning Bolt", counter="collection")
    assert _can_pay(scenario, bolt)
    scenario.game.cast(
        bolt,
        "alice",
        keyword="Cast permission",
        targets=["bob"],
        mana_sources=scenario.game.permanents_controlled_by("alice"),
    )
    assert scenario.find("Lightning Bolt", Zone.STACK)


def test_evelyn_ignores_a_card_without_a_collection_counter():
    scenario, evelyn = _evelyn()
    bolt = _pile(scenario, evelyn, "Lightning Bolt")
    assert not _can_pay(scenario, bolt)


def test_evelyn_ignores_a_card_exiled_by_an_opponents_ability():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Evelyn, the Covetous", "Island"])
        .player("bob", battlefield=["Evelyn, the Covetous"], exile=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.find("Evelyn, the Covetous", Zone.BATTLEFIELD, "bob")
    bolt = _pile(scenario, theirs, "Lightning Bolt", counter="collection")
    assert not _can_pay(scenario, bolt, "alice")


def test_evelyn_allows_only_one_play_each_turn():
    scenario, evelyn = _evelyn(lands=("Island", "Island"))
    bolt = _pile(scenario, evelyn, "Lightning Bolt", counter="collection")
    shock = _pile(scenario, evelyn, "Shock", counter="collection")
    scenario.game.cast(
        bolt,
        "alice",
        keyword="Cast permission",
        targets=["bob"],
        mana_sources=scenario.game.permanents_controlled_by("alice"),
    )
    assert not _can_pay(scenario, shock)


def test_evelyn_plays_a_land_from_the_pile_once_each_turn():
    scenario, evelyn = _evelyn(exile=("Forest", "Mountain"))
    forest = _pile(scenario, evelyn, "Forest", counter="collection")
    mountain = _pile(scenario, evelyn, "Mountain", counter="collection")
    scenario.game.play_land(forest, "alice")
    assert forest.zone is Zone.BATTLEFIELD
    scenario.game.lands_played["alice"] = 0
    with pytest.raises(ValueError, match="nothing allows"):
        scenario.game.play_land(mountain, "alice")
    assert mountain.zone is Zone.EXILE
