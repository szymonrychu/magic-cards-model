"""CR 605.3a: "A player may activate an activated mana ability whenever they
have priority, whenever they are casting a spell or activating an ability
that requires a mana payment, or whenever a rule or effect asks for a mana
payment" - any mana ability, whatever its cost (CR 605.3: it follows CR
602.2's activation rules, cost included).

`CostPayment.tap_for_mana` pays only a bare `{T}` (CR 106.12). A mana
ability whose cost is anything else - Vivi Ornitier's `{0}`, Rakdos Signet's
`{1}, {T}`, Lotus Petal's `{T}, Sacrifice this artifact` - is activated in
full in the middle of the payment by `CostPayment.activate_mana_ability`:
its own cost is paid (out of the mana already in the pool, CR 601.2g), its
mana goes into the payment's pool, and the engine refuses it in its own
words when that cost cannot be paid. CR 733.1: rewinding the payment undoes
the activation too.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import NamedManaAbility
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario, mana_from


def _mana_ability_index(scenario, permanent) -> int:
    for index, ability in enumerate(scenario.game.activated_abilities(permanent)):
        if ability.mana is not None:
            return index
    raise AssertionError(f"{permanent.name} has no mana ability")


def _vivi_board():
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Vivi Ornitier"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vivi = scenario.find("Vivi Ornitier", Zone.BATTLEFIELD)
    scenario.game.add_counters(vivi, Counter.PLUS_ONE, 2)
    return scenario, vivi


def test_vivis_zero_cost_mana_ability_pays_for_a_spell_mid_payment():
    scenario, vivi = _vivi_board()
    casting = scenario.cast("Lightning Bolt", targets=["bob"])
    payment = casting.begin_paying()

    payment.activate_mana_ability(
        vivi, _mana_ability_index(scenario, vivi), color=[Color.RED, Color.BLUE]
    )
    payment.pay()
    bolt = scenario.put_on_stack(casting)

    assert bolt.zone is Zone.STACK
    assert scenario.game.player("alice").mana_pool.floating == {Color.BLUE: 1}
    assert not vivi.tapped


def test_the_abilitys_own_restriction_refuses_it_in_the_engines_words():
    """ "Activate only during your turn and only once each turn": a second
    activation inside the payment is refused, and the payment stays open."""
    scenario, vivi = _vivi_board()
    index = _mana_ability_index(scenario, vivi)
    scenario.activate(vivi, index=index, color=[Color.BLUE, Color.BLUE])
    casting = scenario.cast("Lightning Bolt", targets=["bob"])
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="already been activated this turn"):
        payment.activate_mana_ability(vivi, index, color=[Color.RED, Color.RED])

    assert payment.pool.floating == {Color.BLUE: 2}
    assert scenario.game.mana_pool_receiving("alice") is payment.pool


def test_rewinding_the_payment_undoes_the_activation():
    """CR 733.1: the activation is reversed with the payment - no mana left,
    and the once-each-turn activation is available again."""
    scenario, vivi = _vivi_board()
    index = _mana_ability_index(scenario, vivi)
    casting = scenario.cast("Lightning Bolt", targets=["bob"])
    payment = casting.begin_paying()
    payment.activate_mana_ability(vivi, index, color=[Color.RED, Color.RED])

    payment.rewind()

    assert scenario.game.player("alice").mana_pool.floating == {}
    assert scenario.game.why_cannot_activate(vivi, index) is None


def test_a_mana_cost_on_the_mana_ability_is_paid_from_the_pool():
    """Rakdos Signet's `{1}, {T}`: the Mountain's {R} pays the {1}, the Signet
    adds {B}{R}, and the {R} pays Lightning Bolt - {B} floats."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Rakdos Signet", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    signet = scenario.find("Rakdos Signet", Zone.BATTLEFIELD)
    (mountain,) = scenario.untapped_sources("Mountain")
    casting = scenario.cast("Lightning Bolt", targets=["bob"])
    payment = casting.begin_paying()

    payment.tap_for_mana(mountain, mana_from(mountain))
    payment.activate_mana_ability(signet, _mana_ability_index(scenario, signet))
    payment.pay()
    scenario.put_on_stack(casting)

    assert signet.tapped
    assert scenario.game.player("alice").mana_pool.floating == {Color.BLACK: 1}


def test_a_mana_cost_the_pool_cannot_pay_is_refused_and_nothing_moves():
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Rakdos Signet", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    signet = scenario.find("Rakdos Signet", Zone.BATTLEFIELD)
    casting = scenario.cast("Lightning Bolt", targets=["bob"])
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="Rakdos Signet"):
        payment.activate_mana_ability(signet, _mana_ability_index(scenario, signet))

    assert not signet.tapped
    assert payment.pool.floating == {}
    assert scenario.game.mana_pool_receiving("alice") is payment.pool


def test_a_sacrifice_cost_is_paid_and_rewound():
    """Lotus Petal's `{T}, Sacrifice this artifact`: sacrificed to pay, and
    back on the battlefield, untapped, when the payment is rewound."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Lotus Petal"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    petal = scenario.find("Lotus Petal", Zone.BATTLEFIELD)
    index = _mana_ability_index(scenario, petal)
    casting = scenario.cast("Lightning Bolt", targets=["bob"])
    payment = casting.begin_paying()

    payment.activate_mana_ability(petal, index, color=Color.RED)
    assert petal.zone is Zone.GRAVEYARD
    assert payment.pool.floating == {Color.RED: 1}

    payment.rewind()

    petal_now = scenario.find("Lotus Petal", Zone.BATTLEFIELD)
    assert not petal_now.tapped
    assert scenario.game.player("alice").mana_pool.floating == {}


def test_an_ability_that_is_not_a_mana_ability_is_refused():
    """CR 605.1a: a loyalty ability is never a mana ability, so Xenagos's
    `+1` cannot be activated in the middle of a payment."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Xenagos, the Reveler"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    xenagos = scenario.find("Xenagos, the Reveler", Zone.BATTLEFIELD)
    casting = scenario.cast("Lightning Bolt", targets=["bob"])
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="CR 605.1a"):
        payment.activate_mana_ability(xenagos, 0, color=[Color.RED])


# --------------------------------------------------------------------------
# CR 608.2g: "If an effect gives a player the option to pay mana, they may
# activate mana abilities before taking that action" - a ward cost asked as
# its trigger resolves is paid with Vivi's `{0}` the same way.
# --------------------------------------------------------------------------


def _ward_board():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Vivi Ornitier", "Mountain"])
        .player("bob", battlefield=["Archive Dragon"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vivi = scenario.find("Vivi Ornitier", Zone.BATTLEFIELD)
    scenario.game.add_counters(vivi, Counter.PLUS_ONE, 2)
    return scenario, vivi


def test_vivi_pays_a_ward_cost_while_the_trigger_resolves():
    scenario, vivi = _ward_board()
    dragon = scenario.creature("Archive Dragon", "bob")
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[dragon]
    )
    scenario.will_pay_the_mana_cost(
        username="alice",
        mana_abilities=[
            NamedManaAbility(
                card_id=vivi.id,
                ability_index=_mana_ability_index(scenario, vivi),
                colors=(Color.BLUE, Color.RED),
            )
        ],
    )

    scenario.resolve_top()  # the ward trigger, paid

    assert bolt in scenario.game.stack
    assert scenario.game.player("alice").mana_pool.floating == {}


def test_a_ward_payment_naming_an_unpayable_mana_ability_is_refused_in_the_engines_words():
    scenario, vivi = _ward_board()
    index = _mana_ability_index(scenario, vivi)
    scenario.activate(vivi, index=index, color=[Color.BLUE, Color.BLUE])
    dragon = scenario.creature("Archive Dragon", "bob")
    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[dragon]
    )
    scenario.will_pay_the_mana_cost(
        username="alice",
        mana_abilities=[
            NamedManaAbility(card_id=vivi.id, ability_index=index, colors=(Color.RED, Color.RED))
        ],
    )

    with pytest.raises(ValueError, match="already been activated this turn"):
        scenario.resolve_top()
