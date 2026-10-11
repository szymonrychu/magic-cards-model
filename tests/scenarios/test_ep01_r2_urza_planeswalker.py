"""Scenario: Urza, Planeswalker - three clauses.

CR 606.3: a loyalty ability is activated "only if no player has previously
activated a loyalty ability of that permanent that turn"; Urza's static lets
its controller do that twice each turn instead (CR 604.2). The +2 is CR
601.2f's cost reduction for every artifact, instant and sorcery spell the
controller casts this turn (a comma list, one disjunction); the -10 gives
indestructible (CR 702.12) to the controller's artifacts and planeswalkers
until end of turn and then destroys every other nonland permanent (CR 701.8).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.mana import ManaCost
from tests.scenarios.harness import Scenario

URZA = "Urza, Planeswalker"


def _board(*alice, bob=(), hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[URZA, *alice],
            hand=list(hand),
            library=["Island"] * 8,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _names(scenario, username):
    return [s.name for s in scenario.game.battlefield if s.controller == username]


def _cost_of(scenario, name, username="alice"):
    casting = scenario.cast(name, username=username)
    cost = casting.total_cost.mana
    casting.cancel()
    return cost


def test_urza_may_activate_loyalty_abilities_twice_each_turn():
    scenario = _board()
    urza = scenario.creature(URZA)

    scenario.activate(urza, index=2, username="alice")
    scenario.resolve_top()
    assert scenario.why_cannot_activate(urza, 2, "alice") is None
    scenario.activate(urza, index=2, username="alice")
    scenario.resolve_top()

    assert urza.loyalty == 7
    assert scenario.why_cannot_activate(urza, 2, "alice") is not None


def test_another_planeswalker_is_still_held_to_once():
    scenario = _board("Jace Beleren")
    jace = scenario.creature("Jace Beleren")

    scenario.activate(jace, index=0, username="alice")
    scenario.resolve_top()

    assert scenario.why_cannot_activate(jace, 0, "alice") is not None


def test_the_second_activation_is_gone_next_turn():
    scenario = _board()
    urza = scenario.creature(URZA)
    scenario.activate(urza, index=2, username="alice")
    scenario.resolve_top()
    scenario.activate(urza, index=2, username="alice")
    scenario.resolve_top()
    assert scenario.why_cannot_activate(urza, 2, "alice") is not None


def test_plus_two_discounts_artifact_instant_and_sorcery_spells_and_gains_two_life():
    scenario = _board(hand=["Mind Stone", "Lightning Bolt", "Divination", "Grizzly Bears"])
    life = scenario.player("alice").life
    urza = scenario.creature(URZA)

    scenario.activate(urza, index=0, username="alice")
    scenario.resolve_top()

    assert scenario.player("alice").life == life + 2
    assert urza.loyalty == 9
    assert _cost_of(scenario, "Mind Stone") == ManaCost.parse("")
    assert _cost_of(scenario, "Lightning Bolt") == ManaCost.parse("{R}")
    assert _cost_of(scenario, "Divination") == ManaCost.parse("{U}")
    assert _cost_of(scenario, "Grizzly Bears") == ManaCost.parse("{1}{G}")


def test_minus_ten_destroys_nonland_permanents_but_not_artifacts_and_planeswalkers():
    scenario = _board(
        "Mind Stone", "Grizzly Bears", "Forest", "Jace Beleren",
        bob=["Mind Stone", "Wind Drake", "Island"],
    )
    urza = scenario.creature(URZA)
    urza.add_counters(Counter.LOYALTY, 6)

    scenario.activate(urza, index=4, username="alice")
    scenario.resolve_top()

    mine = _names(scenario, "alice")
    theirs = _names(scenario, "bob")
    assert URZA in mine and "Mind Stone" in mine and "Jace Beleren" in mine
    assert "Forest" in mine and "Grizzly Bears" not in mine
    assert "Mind Stone" not in theirs and "Wind Drake" not in theirs and "Island" in theirs
