"""Scenario: a permanent that has the activated abilities of other objects -
"Sharkey has all activated abilities of lands your opponents control except
mana abilities." and "This artifact has all activated abilities of the exiled
card." (Territory Forge) - CR 613.1f, CR 602.1, CR 605.1a (mana abilities are
the exception Sharkey names), CR 607.2a (the exiled card is the linked one).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def duel(alice, bob, alice_hand=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=list(alice), hand=list(alice_hand))
        .player("bob", battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def abilities(scenario, state):
    return scenario.game.characteristics_of(state).abilities


def test_sharkey_gains_the_non_mana_abilities_of_opponents_lands():
    scenario = duel(["Sharkey, Tyrant of the Shire"], ["Mutavault"])
    sharkey = scenario.creature("Sharkey, Tyrant of the Shire")
    lines = abilities(scenario, sharkey)
    assert any(line.startswith("{1}: This") and "2/2" in line for line in lines)
    assert not any(line.startswith("{T}: Add") for line in lines)


def test_sharkey_gains_nothing_from_his_own_lands():
    scenario = duel(["Sharkey, Tyrant of the Shire", "Mutavault"], [])
    sharkey = scenario.creature("Sharkey, Tyrant of the Shire")
    assert not any("2/2" in line for line in abilities(scenario, sharkey))


def test_sharkey_gains_only_lands_not_other_permanents():
    scenario = duel(["Sharkey, Tyrant of the Shire"], ["Mind Stone"])
    sharkey = scenario.creature("Sharkey, Tyrant of the Shire")
    assert not any("Draw a card" in line for line in abilities(scenario, sharkey))


def test_territory_forge_has_the_abilities_of_the_card_it_exiled():
    scenario = duel(
        ["Mountain"] * 5,
        ["Mutavault"],
        alice_hand=["Territory Forge"],
    )
    mutavault = scenario.find("Mutavault", Zone.BATTLEFIELD, "bob")
    scenario.choose_trigger_targets("Territory Forge", [mutavault])
    scenario.cast_and_resolve("Territory Forge", *scenario.untapped_sources(*["Mountain"] * 5))
    scenario.pass_until_resolved()
    forge = scenario.find("Territory Forge", Zone.BATTLEFIELD, "alice")
    assert mutavault.zone is Zone.EXILE
    lines = abilities(scenario, forge)
    assert any(line.startswith("{1}: This") and "2/2" in line for line in lines)


def test_territory_forge_without_an_exiled_card_has_nothing_extra():
    scenario = duel(["Territory Forge"], ["Mutavault"])
    forge = scenario.find("Territory Forge", Zone.BATTLEFIELD, "alice")
    assert not any("2/2" in line for line in abilities(scenario, forge))
