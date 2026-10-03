"""A token copy of a target that "enters tapped and attacking" (CR 508.4).

Thousand-Faced Shadow: "When this creature enters from your hand, if it's
attacking, create a token that's a copy of another target attacking
creature. The token enters tapped and attacking."

The token is a copy (CR 707.2) put onto the battlefield attacking (CR
508.4): its controller picks what it attacks - here the only defending
player - and, entering during the declare blockers step, it is unblocked (CR
508.4d). The trigger's "if it's attacking" is an intervening if (CR 603.4).
No other Modern, Pioneer or Standard printing carries "The token enters
tapped and attacking" after a target copy, so this card is its own proof.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import ninjutsu_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board():
    return (
        Scenario()
        .player(
            "alice",
            hand=["Thousand-Faced Shadow"],
            battlefield=["Grizzly Bears", "Hill Giant", "Island", "Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )


def _ninjutsu(scenario, card, returning):
    activation = ninjutsu_activation(scenario.game, card, returning, "alice")
    activation.begin_paying()
    activation.payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
    activation.payment.pay()
    activation.activate()
    activation.resolve()


def _attack_and_ninjutsu(scenario):
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, giant)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    shadow = scenario.find("Thousand-Faced Shadow", Zone.HAND, "alice")
    scenario.choose_trigger_targets("Thousand-Faced Shadow", [giant])
    _ninjutsu(scenario, shadow, bears)
    return shadow, giant


def test_the_copy_of_another_attacker_enters_tapped_and_attacking():
    scenario = _board()
    shadow, giant = _attack_and_ninjutsu(scenario)
    assert shadow.zone is Zone.BATTLEFIELD

    scenario.pass_until_resolved()  # the enters trigger

    copies = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Hill Giant" and state is not giant
    ]
    assert len(copies) == 1
    (token,) = copies
    assert token.tapped
    attack = scenario.game.combat.attack_by(token.id)
    assert attack is not None and attack.defender.username == "bob"


def test_the_copy_deals_combat_damage_as_an_unblocked_attacker():
    scenario = _board()
    _attack_and_ninjutsu(scenario)
    scenario.pass_until_resolved()  # the enters trigger
    assert scenario.game.player("bob").life == 20

    scenario.combat_damage()

    # Hill Giant 3 + its copy 3 + Thousand-Faced Shadow 1 (CR 508.4d: unblocked).
    assert scenario.game.player("bob").life == 20 - 7


def test_a_creature_that_is_not_attacking_is_never_copied():
    """ "another target attacking creature": Hill Giant stayed home and the
    only other attacker went back to hand for ninjutsu, so there is no legal
    target (CR 603.3d) and nothing is copied."""
    scenario = _board()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    shadow = scenario.find("Thousand-Faced Shadow", Zone.HAND, "alice")
    _ninjutsu(scenario, shadow, bears)
    scenario.pass_until_resolved()

    names = [state.name for state in scenario.game.permanents_controlled_by("alice")]
    assert names.count("Hill Giant") == 1
    assert scenario.game.combat.attack_by(giant.id) is None
