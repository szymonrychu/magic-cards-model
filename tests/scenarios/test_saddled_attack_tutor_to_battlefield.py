"""Scenario: "Whenever this creature attacks while saddled, search your library
for a nonland permanent card with mana value 3 or less, put it onto the
battlefield, then shuffle." (Guardian Sunmare).

Two readers meet here. "attacks while saddled" is the CR 702.171b designation
asked of the attacking Mount as an intervening "if" (CR 603.4; already read for
every OTJ Mount, see `test_saddle.py`). The search description "a nonland
permanent card with mana value 3 or less" is CR 701.23a's "find a card that
matches the given description": `_quality_matcher` stacked "nonland" on a
permanent umbrella already, but `_card_description_is_readable` - the
pre-check that sends an unreadable description to a notice - did not know the
prefix, so the whole search was refused instead of run.

Rules read whole with `mise run rules:find` in the session that wrote this:

- **CR 701.23a** - searching: find a card that matches the given description.
- **CR 701.23b** - a search for a stated quality may come up empty.
- **CR 701.24a** - shuffle after the search.
- **CR 702.171a/b** - saddle; saddled is a designation lasting to end of turn.
- **CR 603.4** - an intervening "if" is checked on trigger and on resolution.
- **CR 110.4a** - "permanent card" covers artifact, creature, enchantment,
  land, planeswalker and battle cards; "nonland" removes land cards.
- **CR 202.3** - mana value.

Generality: Grim Reminder ("a nonland card ... Then shuffle", a different
destination and no "permanent") and Ajani, Outland Chaperone share the
"nonland" description machinery; the cases below drive the description itself
across every permanent type, not the one printed sentence.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import saddle_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

_LIBRARY = ["Plains", "Serra Angel", "Sol Ring", "Memnite", "Ajani, Outland Chaperone"]


def _board(library=None, *, saddle_with=("Grizzly Bears", "Grizzly Bears")):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Guardian Sunmare", *saddle_with],
            library=list(library if library is not None else _LIBRARY),
        )
        .player("bob", library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _saddle(scenario):
    sunmare = scenario.creature("Guardian Sunmare", "alice")
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")
    activation = saddle_activation(scenario.game, sunmare, list(bears), "alice")
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()
    scenario.pass_until_resolved()
    assert sunmare.saddled
    return sunmare


def _attack(scenario, sunmare):
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(sunmare)
    scenario.game.put_triggers_on_stack()


def _names(zone_cards):
    return sorted(state.name for state in zone_cards)


def test_a_saddled_attack_finds_a_cheap_nonland_permanent_onto_the_battlefield():
    scenario = _board()
    sunmare = _saddle(scenario)
    memnite = scenario.find("Memnite", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(memnite, username="alice", source="Guardian Sunmare")
    _attack(scenario, sunmare)
    assert scenario.stack_names() == ["Guardian Sunmare's triggered ability"]
    scenario.pass_until_resolved()
    assert memnite.zone is Zone.BATTLEFIELD
    assert scenario.game.search_description_notices == []


def test_the_find_is_an_artifact_when_that_is_what_the_player_takes():
    scenario = _board()
    sunmare = _saddle(scenario)
    ring = scenario.find("Sol Ring", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(ring, username="alice", source="Guardian Sunmare")
    _attack(scenario, sunmare)
    scenario.pass_until_resolved()
    assert ring.zone is Zone.BATTLEFIELD


def test_lands_and_cards_above_mana_value_three_are_not_legal_finds():
    scenario = _board(["Plains", "Serra Angel"])
    sunmare = _saddle(scenario)
    _attack(scenario, sunmare)
    scenario.pass_until_resolved()
    alice = scenario.player("alice")
    assert _names(alice.library) == ["Plains", "Serra Angel"]
    assert _names(scenario.game.permanents_controlled_by("alice")) == [
        "Grizzly Bears",
        "Grizzly Bears",
        "Guardian Sunmare",
    ]
    assert scenario.game.search_description_notices == []


def test_mana_value_exactly_three_is_a_legal_find():
    scenario = _board(["Plains", "Ajani, Outland Chaperone"])
    ajani = scenario.find("Ajani, Outland Chaperone", Zone.LIBRARY, "alice")
    assert ajani.mana_value == 3
    sunmare = _saddle(scenario)
    scenario.will_choose_cards(ajani, username="alice", source="Guardian Sunmare")
    _attack(scenario, sunmare)
    scenario.pass_until_resolved()
    assert ajani.zone is Zone.BATTLEFIELD, "a planeswalker card at mana value 3 qualifies"


def test_an_empty_search_still_shuffles_and_changes_nothing_else():
    scenario = _board(["Plains", "Plains"])
    sunmare = _saddle(scenario)
    _attack(scenario, sunmare)
    scenario.pass_until_resolved()
    alice = scenario.player("alice")
    assert _names(alice.library) == ["Plains", "Plains"]
    assert len(scenario.game.permanents_controlled_by("alice")) == 3


def test_the_player_may_decline_to_find_a_legal_card():
    scenario = _board()
    sunmare = _saddle(scenario)
    scenario.will_choose_cards(username="alice", source="Guardian Sunmare")
    _attack(scenario, sunmare)
    scenario.pass_until_resolved()
    alice = scenario.player("alice")
    assert "Memnite" in _names(alice.library)
    assert "Sol Ring" in _names(alice.library)
    assert len(scenario.game.permanents_controlled_by("alice")) == 3


def test_attacking_without_being_saddled_does_not_trigger():
    scenario = _board()
    sunmare = scenario.creature("Guardian Sunmare", "alice")
    _attack(scenario, sunmare)
    assert scenario.stack_names() == []
    assert len(scenario.game.permanents_controlled_by("alice")) == 3
