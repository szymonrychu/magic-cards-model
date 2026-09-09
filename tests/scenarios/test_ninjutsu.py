"""Ninjutsu: CR 702.49a, an activated ability that functions from hand.

"Ninjutsu [cost]" means "[Cost], Reveal this card from your hand, Return an
unblocked attacking creature you control to its owner's hand: Put this card
onto the battlefield from your hand tapped and attacking." Built the same
`KeywordActivation` way `crew_activation`/`station_activation` already are,
driven the same direct way `test_crew.py` drives crew - `ninjutsu_
activation`, `_ninjutsu_effect`, and a new `ComponentKind.RETURN_TO_HAND`
cost component (`return_to_hand_cost`/`_why_not_return_to_hand`) for the
"unblocked attacking creature" half nothing in `machines/cost.py` could pay
before.

Proved on Moon-Circuit Hacker, an ordinary creature - unlike Kaito, Bane of
Nightmares, a planeswalker card whose CR 506.3a exemption (a noncreature
object put onto the battlefield "attacking" never actually becomes an
attacker) is its own edge case, covered separately below.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import ninjutsu_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _ninjutsu(scenario, card, returning, username="alice"):
    """Activate a ninjutsu ability, pay it, and let it resolve."""
    activation = ninjutsu_activation(scenario.game, card, returning, username)
    activation.begin_paying()
    activation.payment.auto_tap(scenario.game.permanents_controlled_by(username))
    activation.payment.pay()
    activation.activate()
    activation.resolve()
    return activation


def test_moon_circuit_hacker_enters_tapped_and_attacking():
    """Moon-Circuit Hacker: "Ninjutsu {U} ({U}, Return an unblocked attacker
    you control to hand: Put this card onto the battlefield from your hand
    tapped and attacking.)"

    Not in the deck pool and not named in this wave's brief.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Moon-Circuit Hacker"],
            battlefield=["Grizzly Bears", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    hacker = scenario.find("Moon-Circuit Hacker", Zone.HAND, "alice")
    (island,) = scenario.untapped_sources("Island", username="alice")

    _ninjutsu(scenario, hacker, bears, username="alice")

    assert hacker.zone is Zone.BATTLEFIELD
    assert hacker.tapped
    assert bears.zone is Zone.HAND
    attack = scenario.game.combat.attack_by(hacker.id)
    assert attack is not None
    assert attack.defender.username == "bob"
    assert island.tapped, "the {U} cost was actually paid"


def test_a_blocked_attacker_cannot_pay_ninjutsu():
    """CR 702.49a's own "unblocked" restriction."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Moon-Circuit Hacker"],
            battlefield=["Grizzly Bears", "Island"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.block(bears, giant)
    hacker = scenario.find("Moon-Circuit Hacker", Zone.HAND, "alice")

    import pytest

    activation = ninjutsu_activation(scenario.game, hacker, bears, "alice")
    payment = activation.begin_paying()
    payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
    with pytest.raises(ValueError):
        payment.pay()


def test_kaito_enters_tapped_but_never_an_attacker():
    """Kaito, Bane of Nightmares is a planeswalker card, not a creature card
    - CR 506.3a's exemption applies exactly the way `_put_onto_the_
    battlefield_attacking`'s own guard already reads it for a token: it
    enters the battlefield, tapped, but "is never considered to be an
    attacking creature" because it is not a creature at all.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Kaito, Bane of Nightmares"],
            battlefield=["Grizzly Bears", "Island", "Swamp", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    kaito = scenario.find("Kaito, Bane of Nightmares", Zone.HAND, "alice")

    _ninjutsu(scenario, kaito, bears, username="alice")

    assert kaito.zone is Zone.BATTLEFIELD
    assert kaito.tapped
    assert scenario.game.combat.attack_by(kaito.id) is None
    assert bears.zone is Zone.HAND
