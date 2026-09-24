"""Scenario: "Whenever you activate an ability of <a quality>, <effect>.[ This
ability triggers only once each turn.]"

CR 602.2 is activating an ability; a mana ability is activated too (CR 605.3a
- it just doesn't use the stack, CR 605.3b), so a condition that does not say
"that isn't a mana ability" is met by one: tapping Llanowar Elves for mana,
by hand or while paying a cost, is activating an ability of a creature.
"An ability of a creature" is a creature on the battlefield (CR 109.2). The
quality may be a card type or a subtype (CR 205.3). The triggered ability
is not a mana ability itself, so it goes on the stack the next time a player
would receive priority (CR 603.3). "This ability triggers only once each
turn" lets it trigger the first time only (the engine reads it through its
CR 603.2h once-each-turn budget).

Printings: Elrond, Moon-Reader ("of a creature", draw, once each turn),
off-set Ceaseless Searblades ("of an Elemental", a pump, every time).

CR numbers verified with `mise run rules:find`: 602.2, 605.3a, 605.3b,
109.2, 205.3, 603.3, 603.2h.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

ELROND = "Elrond, Moon-Reader"
SEARBLADES = "Ceaseless Searblades"


def test_both_printings_are_handled():
    for name in (ELROND, SEARBLADES):
        triggered = [c for c in card_support(card(name)).clauses if c.kind == "triggered"]
        assert [c.outcome for c in triggered] == ["handled"], name


def _board(alice, *, bob=(), hand=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=list(alice), hand=list(hand), library=["Island"] * 8)
        .player("bob", battlefield=list(bob), library=["Island"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _settle(scenario):
    scenario.game.put_triggers_on_stack()
    while scenario.stack_names():
        scenario.pass_until_resolved()


def test_a_non_mana_ability_of_a_creature_draws_a_card():
    scenario = _board([ELROND, "Devoted Druid"])
    alice = scenario.player("alice")
    druid = scenario.creature("Devoted Druid")
    druid.tapped = True
    before = len(alice.hand)
    scenario.activate(druid, index=1)  # put a -1/-1 counter: untap
    _settle(scenario)
    assert len(alice.hand) == before + 1


def test_it_triggers_only_once_each_turn():
    scenario = _board([ELROND, "Devoted Druid"])
    alice = scenario.player("alice")
    druid = scenario.creature("Devoted Druid")
    before = len(alice.hand)
    scenario.activate(druid, index=0)  # {T}: Add {G} - a mana ability
    _settle(scenario)
    scenario.activate(druid, index=1)  # untap
    _settle(scenario)
    assert len(alice.hand) == before + 1


def test_a_mana_ability_of_a_creature_triggers_it():
    scenario = _board([ELROND, "Llanowar Elves"])
    alice = scenario.player("alice")
    before = len(alice.hand)
    scenario.activate(scenario.creature("Llanowar Elves"))
    assert alice.mana_pool.floating.get(Color.GREEN) == 1
    _settle(scenario)
    assert len(alice.hand) == before + 1


def test_tapping_a_creature_for_mana_while_paying_triggers_it():
    scenario = _board([ELROND, "Llanowar Elves"], hand=["Giant Growth"])
    alice = scenario.player("alice")
    elves = scenario.creature("Llanowar Elves")
    scenario.cast_onto_stack("Giant Growth", elves, targets=[elves])
    _settle(scenario)
    assert len(alice.hand) == 1  # Giant Growth left, Elrond's card arrived


def test_an_artifacts_ability_does_not_trigger_it():
    scenario = _board([ELROND, "Mind Stone"])
    alice = scenario.player("alice")
    before = len(alice.hand)
    scenario.activate(scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice"))
    _settle(scenario)
    assert len(alice.hand) == before


def test_an_opponent_activating_does_not_trigger_it():
    scenario = _board([ELROND], bob=["Devoted Druid"])
    alice = scenario.player("alice")
    before = len(alice.hand)
    scenario.pass_priority("alice")
    scenario.activate(scenario.creature("Devoted Druid", "bob"), index=1, username="bob")
    _settle(scenario)
    assert len(alice.hand) == before


# -- Ceaseless Searblades: "of an Elemental", every time ---------------------


def test_searblades_pumps_for_each_elemental_activation():
    scenario = _board([SEARBLADES, "Thornling", "Forest", "Forest"])
    blades = scenario.creature(SEARBLADES)
    thornling = scenario.creature("Thornling")
    base = scenario.game.characteristics_of(blades).power
    for forest in scenario.untapped_sources("Forest", "Forest"):
        scenario.activate(thornling, forest, index=0)
        _settle(scenario)
    assert scenario.game.characteristics_of(blades).power == base + 2


def test_searblades_ignores_a_non_elemental():
    scenario = _board([SEARBLADES, "Devoted Druid"])
    blades = scenario.creature(SEARBLADES)
    base = scenario.game.characteristics_of(blades).power
    scenario.activate(scenario.creature("Devoted Druid"), index=0)
    _settle(scenario)
    assert scenario.game.characteristics_of(blades).power == base
