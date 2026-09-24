"""Pack tactics (CR 207.2c's ability word): "Whenever this creature attacks,
if you attacked with creatures with total power 6 or greater this combat,
..." - an intervening if (CR 603.4) over the attack as it was declared.

"Attacked with" is the declaration (CR 508.1): the total is the power the
declared attackers had as they were declared, kept on `CombatMachine` for
the rest of the combat, so the ability both triggers and resolves off it -
a declared attacker that shrinks or leaves before the trigger resolves does
not undo that the attack was made with it.

Werewolf Pack Leader is the reported card; Gnoll Hunter is the second
printing of the template.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _resolve_all(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _attack(scenario, *names: str) -> None:
    scenario.start_at(Step.DECLARE_ATTACKERS)
    creatures = [scenario.creature(name, "alice") for name in names]
    scenario.attack_with(*creatures, defending="bob")


def test_six_total_power_draws_a_card():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Werewolf Pack Leader", "Hill Giant"], library=["Island"] * 5)
        .player("bob")
        .build()
    )
    _attack(scenario, "Werewolf Pack Leader", "Hill Giant")
    hand = len(scenario.player("alice").hand)
    _resolve_all(scenario)

    assert len(scenario.player("alice").hand) == hand + 1
    assert not scenario.game.intervening_if_notices


def test_five_total_power_does_not_trigger():
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Werewolf Pack Leader", "Grizzly Bears"], library=["Island"] * 5
        )
        .player("bob")
        .build()
    )
    _attack(scenario, "Werewolf Pack Leader", "Grizzly Bears")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert not scenario.game.intervening_if_notices


def test_a_lone_attacker_is_its_own_total():
    scenario = (
        Scenario().player("alice", battlefield=["Gnoll Hunter", "Craw Wurm"]).player("bob").build()
    )
    _attack(scenario, "Gnoll Hunter")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_the_declared_total_holds_after_an_attacker_leaves():
    """CR 603.4 asks again on resolution, and the attack was still made with
    six power: the Hill Giant dying first does not change what was declared."""
    scenario = (
        Scenario().player("alice", battlefield=["Gnoll Hunter", "Craw Wurm"]).player("bob").build()
    )
    _attack(scenario, "Gnoll Hunter", "Craw Wurm")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Gnoll Hunter's triggered ability"]
    scenario.game.destroy(scenario.creature("Craw Wurm", "alice"))
    _resolve_all(scenario)

    hunter = scenario.creature("Gnoll Hunter", "alice")
    assert hunter.counters.counts.get("+1/+1", 0) == 1
    assert scenario.find("Craw Wurm", Zone.GRAVEYARD, "alice") is not None


def test_the_total_is_this_combats_own():
    """A new combat starts from nothing (CR 511.3 clears the last one)."""
    scenario = (
        Scenario().player("alice", battlefield=["Gnoll Hunter", "Craw Wurm"]).player("bob").build()
    )
    _attack(scenario, "Gnoll Hunter", "Craw Wurm")
    assert scenario.game.combat.declared_attacking_power == 8
    scenario.game.combat.clear()
    assert scenario.game.combat.declared_attacking_power == 0
