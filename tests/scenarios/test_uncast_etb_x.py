"""Scenario: an enters-the-battlefield trigger that refers to X, on a permanent
that was put onto the battlefield rather than cast (CR 107.3m, CR 107.3b).

CR 107.3m copies the cast spell's X into the ETB ability only when "the spell
that became that object as it resolved had a value of X chosen". With no such
spell, nothing chose an X for the object and CR 107.3b's "X is 0 everywhere
else" holds: the trigger resolves with X = 0. Ajani's Anguish ("it deals X
damage to any target") used to crash resolving with an unresolved amount
instead.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _put_onto_battlefield(card: str, **bob) -> tuple[Scenario, object]:
    scenario = (
        Scenario()
        .player("alice", hand=[card], battlefield=["Mountain"])
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.find(card, Zone.HAND, "alice")


def test_ajanis_anguish_put_onto_the_battlefield_deals_zero_damage():
    scenario, enchantment = _put_onto_battlefield("Ajani's Anguish")
    angel = scenario.creature("Serra Angel", "bob")
    scenario.choose_trigger_targets("Ajani's Anguish", [angel])

    scenario.game.put_onto_battlefield(enchantment, "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert angel.damage == 0, "CR 107.3b: no spell chose an X, so X is 0"
    assert enchantment.zone is Zone.BATTLEFIELD


def test_an_uncast_permanent_that_creates_x_tokens_makes_none():
    scenario, ooze = _put_onto_battlefield("Mutagen Man, Living Ooze")
    scenario.game.put_onto_battlefield(ooze, "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    tokens = [p for p in scenario.game.permanents_controlled_by("alice") if p.token]
    assert tokens == []
