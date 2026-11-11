"""Scenario: "If a creature you control would enter while you control an
attacking creature, instead it enters tapped and attacking." (Kira Nerys,
Firebrand).

CR 614.1c makes how a permanent enters a replacement; CR 508.4 puts a creature
onto the battlefield attacking - it joins the attack its controller is making,
and it never "attacked" (no attack trigger). No other legal printing carries a
group "enters tapped and attacking" replacement (Scryfall, in the writing
session); the corner cases vary the condition and whose creature enters.

CR rules cited here were looked up with `mise run rules:find` in the writing
session.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import Scenario


def board(*, hand=("Ambush Viper",)) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=["Kira Nerys, Firebrand", "Grizzly Bears", "Forest", "Forest"],
        )
        .player("bob", hand=["Ambush Viper"], battlefield=["Forest", "Forest"])
    )


def to_attack(scenario, *attackers):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
    scenario.attack_with(*attackers)


def test_a_creature_entering_during_your_attack_enters_tapped_and_attacking():
    scenario = board().build()
    bears = scenario.creature("Grizzly Bears", "alice")
    to_attack(scenario, bears)
    viper = scenario.cast_and_resolve(
        "Ambush Viper", *scenario.untapped_sources("Forest", "Forest")
    )
    assert viper.zone is Zone.BATTLEFIELD
    assert viper.tapped
    assert scenario.game.is_attacking(viper)
    defender = scenario.game.combat.attack_by(bears.id).defender
    assert scenario.game.combat.attack_by(viper.id).defender == defender


def test_without_an_attacking_creature_it_enters_untapped():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    viper = scenario.cast_and_resolve(
        "Ambush Viper", *scenario.untapped_sources("Forest", "Forest")
    )
    assert not viper.tapped
    assert not scenario.game.is_attacking(viper)


def test_an_opponents_creature_is_not_put_into_the_attack():
    scenario = board().build()
    bears = scenario.creature("Grizzly Bears", "alice")
    to_attack(scenario, bears)
    scenario.pass_priority("alice")
    casting = scenario.cast("Ambush Viper", "bob")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Forest", "Forest", username="bob"))
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()
    viper = scenario.creature("Ambush Viper", "bob")
    assert not viper.tapped
    assert not scenario.game.is_attacking(viper)


def test_kira_nerys_firebrand_pumps_the_creature_that_joined_the_attack():
    """ "Whenever another creature you control enters, it gets +1/+1 until end
    of turn." - the creature that entered attacking is a 2/2 Ambush Viper,
    now a 3/3, and it deals that combat damage."""
    scenario = board().build()
    bears = scenario.creature("Grizzly Bears", "alice")
    to_attack(scenario, bears)
    viper = scenario.cast_and_resolve(
        "Ambush Viper", *scenario.untapped_sources("Forest", "Forest")
    )
    assert scenario.stack_names() == ["Kira Nerys, Firebrand's triggered ability"]
    scenario.pass_until_resolved()
    assert scenario.game.power_of(viper) == 3
    while scenario.step is not Step.DECLARE_BLOCKERS:
        scenario.advance()
    scenario.no_blocks()
    scenario.combat_damage()
    assert scenario.player("bob").life == 20 - 2 - 3
