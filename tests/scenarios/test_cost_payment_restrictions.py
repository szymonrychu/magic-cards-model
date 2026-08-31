"""A cost's own restrictions, enforced on the path that actually pays it.

Three restrictions live on a cost rather than on the spell it pays for, and
each of them was measured today being honoured by the legality check and
dropped by the payment itself - a wrong board state rather than an absent one:

- **CR 602.5** - "A player can't begin to activate an ability that's
  prohibited from being activated." Mox Opal's metalcraft restriction is read
  by `Game.why_cannot_activate`, and `CostPayment.auto_tap` never asked it, so
  the default payment path (the one the API and the UI take when no sources
  are named) tapped Mox Opal with one artifact on the battlefield.
- **CR 106.5** - "If an ability would produce one or more mana of an undefined
  type, it produces no mana instead", whose own example is Meteor Crater, the
  same "add one mana of any color among ... you control" shape Mox Amber
  prints. With no legendary creature or planeswalker there is no colour to
  choose among, so the ability produces nothing; the engine was making all
  five.
- **CR 118.3** - "A player can't pay a cost without having the necessary
  resources to pay it fully." Key to the Side-Door asks for a legendary card
  with the same name as a legendary permanent you control (CR 201.2a: two
  objects have the same name if they have at least one name in common); any
  card in hand was paying it.

Both directions are asserted for each: the restriction refusing, and the same
board with the restriction met still working, so a fix that simply says no is
not what passes here.

Every case drives `CostPayment` - `auto_tap` via the harness's `auto_pay`, and
`tap_for_mana` via a hand-picked source - because that is the path with the
defect. A test that only asked `Game.why_cannot_activate` passed while all
three bugs were live.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# CR 602.5: Mox Opal's metalcraft restriction, on the payment path
# --------------------------------------------------------------------------


def _bolt_payment(scenario):
    """Announce Lightning Bolt at bob and open its payment (CR 601.2f).

    The casting is handed back alongside the payment because CR 601.2a has
    already moved the Bolt to the stack by now - a refused payment is undone
    by rewinding the whole proposal (CR 601.6), which is `Casting.cancel`.
    """
    casting = scenario.cast("Lightning Bolt", targets=["bob"])
    return casting, casting.begin_paying()


def test_auto_tap_refuses_mox_opal_without_metalcraft():
    """CR 602.5: the payment path may not activate a prohibited ability.

    One artifact on the battlefield, so "Activate only if you control three or
    more artifacts" is not met. `why_cannot_activate` has always said so; this
    asserts `auto_tap` says the same, and that the refusal leaves Mox Opal
    untapped (CR 118.3: nothing is spent on a cost that cannot be paid).
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mox Opal"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    opal = scenario.find("Mox Opal", Zone.BATTLEFIELD)

    assert scenario.why_cannot_activate(opal) is not None

    casting, payment = _bolt_payment(scenario)
    with pytest.raises(ValueError):
        scenario.auto_pay(payment, "alice")

    assert not opal.tapped
    casting.cancel()  # CR 601.6: the proposal is rewound, so the Bolt goes back
    assert scenario.find("Lightning Bolt", Zone.HAND) is not None


def test_auto_tap_taps_mox_opal_once_metalcraft_is_on():
    """The same board with three artifacts: the restriction is met, so the
    Mox is a mana source again and the Bolt is paid for out of it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mox Opal", "Mox Diamond", "Key to the Side-Door"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    opal = scenario.find("Mox Opal", Zone.BATTLEFIELD)

    assert scenario.why_cannot_activate(opal) is None

    _, payment = _bolt_payment(scenario)
    scenario.auto_pay(payment, "alice")

    assert opal.tapped


def test_hand_picked_tap_refuses_mox_opal_without_metalcraft():
    """`tap_for_mana` is the other way into the pool - a scenario's `pay_with`,
    a player naming their own sources - and CR 602.5 does not care which path
    asked. Naming the Mox by hand is refused too."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mox Opal"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    opal = scenario.find("Mox Opal", Zone.BATTLEFIELD)

    _, payment = _bolt_payment(scenario)
    with pytest.raises(ValueError):
        payment.tap_for_mana(opal, [Color.RED])

    assert not opal.tapped


# --------------------------------------------------------------------------
# CR 106.5: Mox Amber's undefined mana type
# --------------------------------------------------------------------------


def test_mox_amber_produces_no_mana_without_a_legendary_creature():
    """CR 106.5: "of any color among legendary creatures and planeswalkers you
    control" has nothing to name on an empty board, so the type is undefined
    and the ability produces no mana at all - not five colours to choose from.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mox Amber"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    amber = scenario.find("Mox Amber", Zone.BATTLEFIELD)

    _, payment = _bolt_payment(scenario)
    with pytest.raises(ValueError):
        scenario.auto_pay(payment, "alice")

    assert not amber.tapped


def test_mox_amber_makes_the_colour_of_the_legend_you_control():
    """Ragavan, Nimble Pilferer is red, so red is defined and the Bolt is
    payable out of the Mox."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mox Amber", "Ragavan, Nimble Pilferer"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    amber = scenario.find("Mox Amber", Zone.BATTLEFIELD)

    _, payment = _bolt_payment(scenario)
    scenario.auto_pay(payment, "alice")

    assert amber.tapped


def test_mox_amber_makes_only_the_colours_among_your_legends():
    """A white legend defines white and nothing else, so a red cost is still
    unpayable - the colour set is the one on the board, not WUBRG."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mox Amber", "Isamaru, Hound of Konda"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    amber = scenario.find("Mox Amber", Zone.BATTLEFIELD)

    _, payment = _bolt_payment(scenario)
    with pytest.raises(ValueError):
        scenario.auto_pay(payment, "alice")

    assert not amber.tapped


def test_hand_picked_tap_refuses_a_colour_no_legend_defines():
    """The hand-picked path again: naming red on a board whose only legendary
    creature is white is refused rather than granted (CR 106.5)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mox Amber", "Isamaru, Hound of Konda"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    amber = scenario.find("Mox Amber", Zone.BATTLEFIELD)

    _, payment = _bolt_payment(scenario)
    with pytest.raises(ValueError):
        payment.tap_for_mana(amber, [Color.RED])
    payment.tap_for_mana(amber, [Color.WHITE])

    assert amber.tapped


# --------------------------------------------------------------------------
# CR 118.3 / CR 201.2a: Key to the Side-Door's same-name discard
# --------------------------------------------------------------------------


def _key_scenario(hand: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=hand,
            library=["Forest", "Forest"],
            battlefield=["Key to the Side-Door", "Mox Amber", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_key_to_the_side_door_refuses_a_nonlegendary_discard():
    """CR 118.3: the cost is "Discard a legendary card with the same name as a
    legendary permanent you control", and Lightning Bolt is neither."""
    scenario = _key_scenario(["Lightning Bolt"])
    key = scenario.find("Key to the Side-Door", Zone.BATTLEFIELD)
    bolt = scenario.find("Lightning Bolt", Zone.HAND)
    (mountain,) = scenario.untapped_sources("Mountain")

    with pytest.raises(ValueError):
        scenario.activate(key, mountain, index=1, discarding=[bolt])

    assert bolt.zone is Zone.HAND
    assert not key.tapped


def test_key_to_the_side_door_refuses_a_legend_with_a_different_name():
    """CR 201.2a: objects have the same name only if they share one. Mox Opal
    is legendary, and is not the name of any legendary permanent on this
    board, so it does not pay."""
    scenario = _key_scenario(["Mox Opal"])
    key = scenario.find("Key to the Side-Door", Zone.BATTLEFIELD)
    opal = scenario.find("Mox Opal", Zone.HAND)
    (mountain,) = scenario.untapped_sources("Mountain")

    with pytest.raises(ValueError):
        scenario.activate(key, mountain, index=1, discarding=[opal])

    assert opal.zone is Zone.HAND
    assert not key.tapped


def test_key_to_the_side_door_accepts_the_matching_legendary_card():
    """The board it was printed for: a second Mox Amber in hand, with one on
    the battlefield, is a legendary card with the same name as a legendary
    permanent you control, so the cost is payable and the ability activates."""
    scenario = _key_scenario(["Mox Amber"])
    key = scenario.find("Key to the Side-Door", Zone.BATTLEFIELD)
    spare = scenario.find("Mox Amber", Zone.HAND)
    (mountain,) = scenario.untapped_sources("Mountain")

    ability = scenario.activate(key, mountain, index=1, discarding=[spare])

    assert ability is not None
    assert spare.zone is Zone.GRAVEYARD
    assert key.tapped
