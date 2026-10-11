"""Scenario: Satoru Umezawa - "Whenever you activate a ninjutsu ability, look
at the top three cards of your library. Put one of them into your hand and the
rest on the bottom of your library in any order. This ability triggers only
once each turn."

CR 602.2 (activating), CR 702.49a (ninjutsu is an activated ability, so the
activation raises the ability-activated event with the keyword it came from),
CR 603.2h (once each turn), CR 701.20 / CR 608.2d (look, then one to hand).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import CardSplit, DecisionKind
from magic_cards_model.machines.keywords import ninjutsu_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from

SATORU = "Satoru Umezawa"


def build(hand=("Llanowar Elves",), extra_attacker=False):
    battlefield = [SATORU, "Grizzly Bears", "Island", "Swamp", "Island", "Swamp"]
    if extra_attacker:
        battlefield.append("Savannah Lions")
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=battlefield,
            hand=list(hand),
            library=["Forest", "Mountain", "Plains", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    for creature in scenario.game.battlefield:
        creature.summoning_sick = False
    return scenario


def take(scenario, card, *bottom):
    """Script the look-at-three answer: `card` to hand, `bottom` ordered
    topmost first on the bottom of the library."""
    scenario._queue(DecisionKind.SCRY, CardSplit(moved=(card.id,)), None, None, 1)
    scenario.will_choose_cards(*bottom)


def swing(scenario, *names):
    for name in names:
        scenario.attack_with(scenario.creature(name), defending="bob")
    scenario.advance()
    scenario.no_blocks()


def ninjutsu(scenario, card_name, attacker_name):
    card = scenario.find(card_name, Zone.HAND, "alice")
    attacker = scenario.creature(attacker_name)
    activation = ninjutsu_activation(scenario.game, card, attacker, "alice")
    activation.begin_paying()
    activation.payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
    activation.payment.pay()
    activation.activate()
    return activation


def test_activating_ninjutsu_looks_at_three_and_takes_one():
    scenario = build()
    swing(scenario, "Grizzly Bears")
    mountain = scenario.find("Mountain", Zone.LIBRARY, "alice")
    forest = scenario.find("Forest", Zone.LIBRARY, "alice")
    plains = scenario.find("Plains", Zone.LIBRARY, "alice")
    take(scenario, mountain, plains, forest)

    activation = ninjutsu(scenario, "Llanowar Elves", "Grizzly Bears")
    while scenario.game.stack:
        scenario.resolve_top()

    alice = scenario.player("alice")
    assert mountain.zone is Zone.HAND
    assert activation.card.zone is Zone.BATTLEFIELD
    assert [c.name for c in alice.library] == ["Island", "Island", "Plains", "Forest"]


def test_it_triggers_only_once_each_turn():
    scenario = build(hand=("Llanowar Elves", "Llanowar Elves"), extra_attacker=True)
    swing(scenario, "Grizzly Bears", "Savannah Lions")
    take(
        scenario,
        scenario.find("Mountain", Zone.LIBRARY, "alice"),
        scenario.find("Plains", Zone.LIBRARY, "alice"),
        scenario.find("Forest", Zone.LIBRARY, "alice"),
    )

    ninjutsu(scenario, "Llanowar Elves", "Grizzly Bears")
    while scenario.game.stack:
        scenario.resolve_top()
    library_after_first = len(scenario.player("alice").library)
    assert library_after_first == 4, "the first activation looked at three and took one"
    for creature in scenario.game.battlefield:
        if creature.name.endswith("Island") or creature.name.endswith("Swamp"):
            creature.untap()
    ninjutsu(scenario, "Llanowar Elves", "Savannah Lions")
    while scenario.game.stack:
        scenario.resolve_top()

    assert len(scenario.player("alice").library) == library_after_first


def test_other_activations_do_not_trigger_it():
    scenario = build()
    swing(scenario, "Grizzly Bears")
    stone_islands = scenario.untapped_sources("Island", username="alice")
    scenario.activate(stone_islands[0], index=0, username="alice")

    assert len(scenario.player("alice").library) == 5
