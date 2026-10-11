"""Scenario: Overwhelming Splendor - "Enchant player. Creatures enchanted
player controls lose all abilities and have base power and toughness 1/1.
Enchanted player can't activate abilities that aren't mana abilities or
loyalty abilities."

CR 303.4m: an Aura attached to a player enchants that player. The creature
sentence is layer 6 (CR 613.1f) and layer 7b (CR 613.4b) over the enchanted
player's creatures only; the activation sentence is CR 602.5, spared for mana
abilities (CR 605.1a) and loyalty abilities (CR 606).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

SPLENDOR = "Overwhelming Splendor"


def _board():
    scenario = (
        Scenario()
        .player("alice", battlefield=[SPLENDOR, "Serra Angel", "Mind Stone"], library=["Island"] * 5)
        .player(
            "bob",
            battlefield=["Serra Angel", "Grizzly Bears", "Mind Stone", "Jace Beleren"],
            library=["Island"] * 5,
        )
        .build()
    )
    splendor = scenario.find(SPLENDOR, Zone.BATTLEFIELD, username="alice")
    splendor.attach_to(scenario.player("bob"))
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _characteristics(scenario, name, username):
    return scenario.game.characteristics_of(scenario.creature(name, username))


def test_the_enchanted_players_creatures_are_vanilla_one_one():
    scenario = _board()
    theirs = _characteristics(scenario, "Serra Angel", "bob")

    assert (theirs.power, theirs.toughness) == (1, 1)
    assert not has_keyword(scenario.creature("Serra Angel", "bob"), "flying", scenario.game)
    assert not has_keyword(scenario.creature("Serra Angel", "bob"), "vigilance", scenario.game)


def test_counters_still_apply_over_the_base_size():
    scenario = _board()
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.add_counters(Counter.PLUS_ONE, 2)

    chars = scenario.game.characteristics_of(bears)
    assert (chars.power, chars.toughness) == (3, 3)


def test_the_auras_controllers_creatures_are_untouched():
    scenario = _board()
    mine = _characteristics(scenario, "Serra Angel", "alice")

    assert (mine.power, mine.toughness) == (4, 4)
    assert has_keyword(scenario.creature("Serra Angel", "alice"), "flying", scenario.game)


def _bobs_turn(scenario):
    scenario.advance()
    while scenario.turn.active_player != "bob" or scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()


def test_the_enchanted_player_cannot_activate_a_non_mana_ability():
    scenario = _board()
    _bobs_turn(scenario)
    stone = scenario.creature("Mind Stone", "bob")

    reason = scenario.why_cannot_activate(stone, 1, "bob")
    assert reason is not None and SPLENDOR in reason


def test_mana_abilities_and_loyalty_abilities_stay_legal():
    scenario = _board()
    _bobs_turn(scenario)
    stone = scenario.creature("Mind Stone", "bob")
    jace = scenario.creature("Jace Beleren", "bob")

    assert scenario.why_cannot_activate(stone, 0, "bob") is None
    assert scenario.why_cannot_activate(jace, 0, "bob") is None


def test_the_auras_controller_may_still_activate_everything():
    scenario = _board()
    stone = scenario.creature("Mind Stone", "alice")

    assert scenario.why_cannot_activate(stone, 1, "alice") is None
