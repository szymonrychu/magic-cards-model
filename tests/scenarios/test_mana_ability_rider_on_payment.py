"""CR 405.6c's "other effect" happens on every route a mana ability is activated.

Battle report B4-03: bob cast Dismember with `--sources <Urza's Mine>,<Talisman
of Resilience>` and his life fell by exactly the Phyrexian payment - the
Talisman's "This artifact deals 1 damage to you." never happened. Activated on
its own, the same Talisman did cost him 1 life. The rider was applied only by
`Game.activate_ability`; a source tapped while paying a cost
(`CostPayment.tap_for_mana`, which both a hand-picked source list and
`auto_tap` go through) added the mana and nothing else.

Rules read in full with `mise run rules:find` this session:

- **CR 405.6c** - "Mana abilities resolve immediately. If a mana ability both
  produces mana and has another effect, the mana is produced and the other
  effect happens immediately."
- **CR 118.3c** - "Activating mana abilities is not mandatory, even if paying a
  cost is." Tapping a source during payment *is* activating its mana ability;
  nothing about the payment route makes it a different ability.

So whoever chooses the source - the player, a hand-picked list, or the
engine's automatic payment - the ability that resolves is the same one, and its
second sentence happens. Both paths are proven below, on the reported Talisman
and on an off-pool land whose rider differs in amount, subject noun, and mana
(Tarnished Citadel: "{T}: Add one mana of any color. This land deals 3 damage
to you.").
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.cost import CostStep
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario


def _talisman_board(**alice):
    scenario = (
        Scenario().player("alice", **alice).player("bob", battlefield=["Grizzly Bears"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_a_talisman_hand_picked_to_pay_a_spell_deals_its_damage():
    """The reported route: the source is named for the payment, not activated."""
    scenario = _talisman_board(
        hand=["Inquisition of Kozilek"], battlefield=["Talisman of Resilience"]
    )
    talisman = scenario.find("Talisman of Resilience", Zone.BATTLEFIELD)
    bob_hand_before = len(scenario.player("bob").hand)

    casting = scenario.cast("Inquisition of Kozilek", targets=["bob"])
    payment = casting.begin_paying()
    payment.tap_for_mana(talisman, [Color.BLACK])
    payment.pay()
    scenario.put_on_stack(casting)

    assert talisman.tapped
    assert scenario.player("alice").life == 19, "CR 405.6c: the damage comes with the mana"
    assert len(scenario.player("bob").hand) == bob_hand_before


def test_a_talisman_the_engine_taps_automatically_deals_its_damage():
    """The automatic payment picks the Talisman as the only black source."""
    scenario = _talisman_board(
        hand=["Inquisition of Kozilek"], battlefield=["Talisman of Resilience"]
    )
    talisman = scenario.find("Talisman of Resilience", Zone.BATTLEFIELD)

    scenario.cast_onto_stack("Inquisition of Kozilek", targets=["bob"], auto=True)

    assert talisman.tapped
    assert scenario.player("alice").life == 19


def test_the_colorless_ability_chosen_for_payment_deals_no_damage():
    """The rider belongs to the colored ability only (CR 602.1: one paragraph,
    one ability), so tapping the Talisman for {C} to pay generic costs nothing."""
    scenario = _talisman_board(hand=["Ornithopter"], battlefield=["Talisman of Resilience"])
    talisman = scenario.find("Talisman of Resilience", Zone.BATTLEFIELD)

    casting = scenario.cast("Ornithopter")
    payment = casting.begin_paying()
    payment.tap_for_mana(talisman, [Color.COLORLESS])
    payment.pay()
    scenario.put_on_stack(casting)

    assert talisman.tapped
    assert scenario.player("alice").life == 20


def test_explicit_activation_and_payment_cost_the_same_life():
    """One funnel: the explicit activation and the payment route agree."""
    explicit = _talisman_board(battlefield=["Talisman of Resilience"])
    explicit.activate(
        explicit.find("Talisman of Resilience", Zone.BATTLEFIELD), index=1, color=Color.BLACK
    )

    paid = _talisman_board(hand=["Inquisition of Kozilek"], battlefield=["Talisman of Resilience"])
    paid.cast_onto_stack("Inquisition of Kozilek", targets=["bob"], auto=True)

    assert explicit.player("alice").life == paid.player("alice").life == 19


def test_an_off_pool_pain_land_with_a_different_rider_pays_it_on_the_payment_path():
    """Tarnished Citadel: any color, "This land deals 3 damage to you." - a
    different noun, amount and mana shape through the same parser and funnel."""
    scenario = _talisman_board(hand=["Inquisition of Kozilek"], battlefield=["Tarnished Citadel"])
    citadel = scenario.find("Tarnished Citadel", Zone.BATTLEFIELD)

    casting = scenario.cast("Inquisition of Kozilek", targets=["bob"])
    payment = casting.begin_paying()
    payment.tap_for_mana(citadel, [Color.BLACK])
    payment.pay()
    scenario.put_on_stack(casting)

    assert scenario.player("alice").life == 17


def test_the_off_pool_pain_land_activated_on_its_own_deals_the_same_damage():
    scenario = _talisman_board(battlefield=["Tarnished Citadel"])
    citadel = scenario.find("Tarnished Citadel", Zone.BATTLEFIELD)

    scenario.activate(citadel, index=1, color=Color.RED)

    assert scenario.player("alice").mana_pool.floating == {Color.RED: 1}
    assert scenario.player("alice").life == 17


def test_the_rider_on_the_payment_path_is_damage_a_shield_can_prevent():
    """Routed through `Game.deal_damage` on the payment path too (CR 615)."""
    from magic_cards_model.models.game import PreventionShield, ShieldKind

    scenario = _talisman_board(
        hand=["Inquisition of Kozilek"], battlefield=["Talisman of Resilience"]
    )
    scenario.game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.ALL,
            label="prevent all damage that would be dealt to alice this turn",
            controller="alice",
            player="alice",
        )
    )

    scenario.cast_onto_stack("Inquisition of Kozilek", targets=["bob"], auto=True)

    assert scenario.player("alice").life == 20


def test_a_rider_that_drops_life_below_zero_does_not_block_the_rest_of_the_payment():
    """CR 405.6c's damage happens mid-payment, and state-based actions are
    checked only afterwards - so the payment finishes at -1 life. CR 119.4b:
    "Players can always pay 0 life", so a cost with no life in it stays payable
    whatever the life total is. The loss comes after, from CR 704.5a."""
    scenario = _talisman_board(
        hand=["Inquisition of Kozilek", "Lightning Helix"],
        battlefield=["Tarnished Citadel", "Mountain"],
    )
    scenario.player("alice").life = 2
    citadel = scenario.find("Tarnished Citadel", Zone.BATTLEFIELD)
    (mountain,) = scenario.untapped_sources("Mountain")

    casting = scenario.cast("Lightning Helix", targets=["bob"])
    payment = casting.begin_paying()
    payment.tap_for_mana(citadel, [Color.WHITE])
    payment.tap_for_mana(mountain, [Color.RED])
    payment.pay()

    assert payment.step is CostStep.PAID
    assert citadel.tapped and mountain.tapped
    assert scenario.player("alice").life == -1

    scenario.game.check_state_based_actions()
    assert "alice" in scenario.game.losers  # CR 704.5a
