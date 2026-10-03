"""R0b proofs: alternative and optional exile-from-hand costs.

Soul Spike and Nourishing Shoal print CR 118.9 alternative costs that exile
cards from the caster's hand; March of Wretched Sorrow prints a CR 118.8b
optional additional cost that exiles black cards to discount its generic
mana. All three were `handled` and untested.

Every CR number below was looked up with `mise run rules:find`:

- **CR 118.9** - an alternative cost is paid rather than the mana cost.
- **CR 118.8b** - an optional additional cost may be paid or not.
- **CR 601.2b** - the caster announces which costs, and X, as the spell is cast.
- **CR 118.7a** - a generic-mana cost reduction affects only the generic
  component of the cost, never the coloured mana.
- **CR 107.1c** - "any number" includes zero.
- **CR 107.3a** - X in an alternative cost is chosen as the spell is cast.
- **CR 202.3** - a card's mana value comes from its mana cost.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _start(scenario: Scenario):
    played = scenario.build()
    played.start_at(Step.PRECOMBAT_MAIN)
    return played


def _soul_spike_board(hand, *, battlefield=()):
    return _start(
        Scenario()
        .player("alice", hand=["Soul Spike", *hand], battlefield=list(battlefield))
        .player("bob", battlefield=["Blightsteel Colossus", "Grizzly Bears"])
    )


# -- Soul Spike ----------------------------------------------------------------------


def test_soul_spike_pitching_two_black_cards_costs_no_mana():
    scenario = _soul_spike_board(["Dark Ritual", "Duress"])
    ritual = scenario.find("Dark Ritual", Zone.HAND, "alice")
    duress = scenario.find("Duress", Zone.HAND, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Soul Spike")
    casting.use_pitch_cost(choosing=[ritual, duress])
    casting.choose_targets([bears])
    casting.begin_paying().pay()
    spike = scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert ritual.zone is Zone.EXILE
    assert duress.zone is Zone.EXILE
    assert bears.zone is Zone.GRAVEYARD
    assert spike.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 24


def test_soul_spike_deals_four_to_a_player_and_gains_four():
    scenario = _soul_spike_board(["Dark Ritual", "Duress"])
    ritual = scenario.find("Dark Ritual", Zone.HAND, "alice")
    duress = scenario.find("Duress", Zone.HAND, "alice")

    casting = scenario.cast("Soul Spike")
    casting.use_pitch_cost(choosing=[ritual, duress])
    casting.choose_targets(["bob"])
    casting.begin_paying().pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.player("bob").life == 16
    assert scenario.player("alice").life == 24


def test_soul_spike_cannot_pitch_itself_so_one_other_black_card_is_not_enough():
    """CR 601.2a moves the spell to the stack first, so the only black cards
    left in hand are the others; with a single one the alternative cost
    can't be paid (CR 118.3)."""
    scenario = _soul_spike_board(["Dark Ritual", "Lightning Bolt"])
    ritual = scenario.find("Dark Ritual", Zone.HAND, "alice")

    casting = scenario.cast("Soul Spike")
    with pytest.raises(ValueError):
        casting.use_pitch_cost(choosing=[ritual])
        casting.choose_targets(["bob"])
        casting.begin_paying().pay()
    assert ritual.zone is Zone.HAND


def test_soul_spike_refuses_a_card_that_is_not_black():
    scenario = _soul_spike_board(["Dark Ritual", "Lightning Bolt"])
    ritual = scenario.find("Dark Ritual", Zone.HAND, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")

    casting = scenario.cast("Soul Spike")
    with pytest.raises(ValueError):
        casting.use_pitch_cost(choosing=[ritual, bolt])
        casting.choose_targets(["bob"])
        casting.begin_paying().pay()
    assert ritual.zone is Zone.HAND
    assert bolt.zone is Zone.HAND


def test_soul_spike_for_its_mana_cost_leaves_the_hand_alone():
    scenario = _soul_spike_board(["Dark Ritual", "Duress"], battlefield=["Swamp"] * 7)
    sources = scenario.untapped_sources(*(["Swamp"] * 7), username="alice")

    scenario.cast_and_resolve("Soul Spike", *sources, targets=["bob"])

    assert scenario.find("Dark Ritual", Zone.HAND, "alice").zone is Zone.HAND
    assert scenario.find("Duress", Zone.HAND, "alice").zone is Zone.HAND
    assert scenario.player("bob").life == 16
    assert scenario.player("alice").life == 24


# -- Nourishing Shoal ----------------------------------------------------------------


def _shoal_board(hand, *, battlefield=()):
    return _start(
        Scenario()
        .player("alice", hand=["Nourishing Shoal", *hand], battlefield=list(battlefield))
        .player("bob")
    )


def test_nourishing_shoal_exiling_a_two_mana_value_green_card_gains_two():
    scenario = _shoal_board(["Grizzly Bears"])
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")

    casting = scenario.cast("Nourishing Shoal")
    casting.use_pitch_cost(x_value=2, choosing=[bears])
    casting.begin_paying().pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.EXILE
    assert scenario.player("alice").life == 22


def test_nourishing_shoal_exiling_a_one_mana_value_green_card_gains_one():
    """X is that card's mana value, so a different card makes a different X."""
    scenario = _shoal_board(["Rancor"])
    rancor = scenario.find("Rancor", Zone.HAND, "alice")

    casting = scenario.cast("Nourishing Shoal")
    casting.use_pitch_cost(x_value=1, choosing=[rancor])
    casting.begin_paying().pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert rancor.zone is Zone.EXILE
    assert scenario.player("alice").life == 21


def test_nourishing_shoal_refuses_a_green_card_of_the_wrong_mana_value():
    scenario = _shoal_board(["Grizzly Bears"])
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")

    casting = scenario.cast("Nourishing Shoal")
    casting.use_pitch_cost(x_value=3, choosing=[bears])
    with pytest.raises(ValueError, match="mana value"):
        casting.begin_paying().pay()
    assert bears.zone is Zone.HAND


def test_nourishing_shoal_refuses_a_card_that_is_not_green():
    scenario = _shoal_board(["Lightning Bolt"])
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")

    casting = scenario.cast("Nourishing Shoal")
    casting.use_pitch_cost(x_value=1, choosing=[bolt])
    with pytest.raises(ValueError):
        casting.begin_paying().pay()
    assert bolt.zone is Zone.HAND


def test_nourishing_shoal_for_mana_gains_the_announced_x():
    scenario = _shoal_board([], battlefield=["Forest"] * 5)
    sources = scenario.untapped_sources(*(["Forest"] * 5), username="alice")

    casting = scenario.cast("Nourishing Shoal")
    casting.x_value = 3
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.player("alice").life == 23


# -- March of Wretched Sorrow --------------------------------------------------------


def _march_board(hand, *, battlefield):
    return _start(
        Scenario()
        .player("alice", hand=["March of Wretched Sorrow", *hand], battlefield=battlefield)
        .player("bob", battlefield=["Blightsteel Colossus", "Grizzly Bears"])
    )


def test_march_without_exiling_pays_full_cost_deals_x_and_gains_x():
    scenario = _march_board([], battlefield=["Swamp"] * 3)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*(["Swamp"] * 3), username="alice")

    casting = scenario.cast("March of Wretched Sorrow", targets=[bears])
    casting.x_value = 2
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 22
    assert all(source.tapped for source in sources)


def test_march_each_exiled_black_card_makes_it_cost_two_less():
    """X=4 is {4}{B}; exiling two black cards removes {4}, leaving {B}."""
    scenario = _march_board(["Dark Ritual", "Duress"], battlefield=["Swamp"])
    ritual = scenario.find("Dark Ritual", Zone.HAND, "alice")
    duress = scenario.find("Duress", Zone.HAND, "alice")
    colossus = scenario.creature("Blightsteel Colossus", "bob")
    (swamp,) = scenario.untapped_sources("Swamp", username="alice")
    scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("March of Wretched Sorrow")
    casting.exile_for_cost_reduction([ritual, duress])
    casting.choose_targets([colossus])
    casting.x_value = 4
    scenario.pay_with(casting.begin_paying(), swamp)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert ritual.zone is Zone.EXILE
    assert duress.zone is Zone.EXILE
    assert swamp.tapped
    assert colossus.damage == 4
    assert scenario.player("alice").life == 24


def test_march_one_exiled_card_reduces_by_exactly_two():
    scenario = _march_board(["Dark Ritual"], battlefield=["Swamp", "Swamp"])
    ritual = scenario.find("Dark Ritual", Zone.HAND, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Swamp", "Swamp", username="alice")

    casting = scenario.cast("March of Wretched Sorrow")
    casting.exile_for_cost_reduction([ritual])
    casting.choose_targets([bears])
    casting.x_value = 3  # {3}{B} less {2} is {1}{B}
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 23


def test_march_reduction_is_generic_only_never_the_black_mana():
    """X=1 is {1}{B}; two exiled cards would reduce by {4}, but only the
    generic {1} can be removed, so the {B} is still owed."""
    scenario = _march_board(["Dark Ritual", "Duress"], battlefield=["Island"])
    ritual = scenario.find("Dark Ritual", Zone.HAND, "alice")
    duress = scenario.find("Duress", Zone.HAND, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    (island,) = scenario.untapped_sources("Island", username="alice")

    casting = scenario.cast("March of Wretched Sorrow")
    casting.exile_for_cost_reduction([ritual, duress])
    casting.choose_targets([bears])
    casting.x_value = 1
    payment = casting.begin_paying()
    with pytest.raises(ValueError):
        scenario.pay_with(payment, island)
        payment.pay()
    assert bears.zone is Zone.BATTLEFIELD


def test_march_exiling_cards_that_are_not_black_is_refused():
    scenario = _march_board(["Lightning Bolt"], battlefield=["Swamp"])
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("March of Wretched Sorrow", targets=[bears])
    with pytest.raises(ValueError):
        casting.exile_for_cost_reduction([bolt])
    assert bolt.zone is Zone.HAND


def test_march_cannot_target_a_player():
    scenario = _march_board([], battlefield=["Swamp"])
    with pytest.raises(ValueError):
        scenario.cast("March of Wretched Sorrow", targets=["bob"])


def test_march_through_the_seats_atomic_cast_announces_the_exile():
    """`Game.cast(exile_for_cost_reduction=...)` is the seat's own path to
    CR 601.2b's optional exile - the Casting machine alone is not enough."""
    scenario = _march_board(["Dark Ritual", "Duress"], battlefield=["Swamp"])
    ritual = scenario.find("Dark Ritual", Zone.HAND, "alice")
    duress = scenario.find("Duress", Zone.HAND, "alice")
    colossus = scenario.creature("Blightsteel Colossus", "bob")
    (swamp,) = scenario.untapped_sources("Swamp", username="alice")

    scenario.game.cast(
        scenario.find("March of Wretched Sorrow", Zone.HAND, "alice"),
        "alice",
        targets=[colossus],
        x_value=4,
        exile_for_cost_reduction=[ritual, duress],
        mana_sources=[swamp],
    )
    scenario.resolve_top()

    assert ritual.zone is Zone.EXILE and duress.zone is Zone.EXILE
    assert colossus.damage == 4


# -- Second printing: March of Swirling Mist (generality of the reader) --------------
#
# Same "exile any number of <colour> cards from your hand, {2} less for each"
# template as March of Wretched Sorrow, a different colour and a different
# effect ("Up to X target creatures phase out." - CR 702.26b), legal in Modern
# and Pioneer and in no deck.


def _mist_board(hand, *, battlefield):
    return _start(
        Scenario()
        .player("alice", hand=["March of Swirling Mist", *hand], battlefield=battlefield)
        .player("bob", battlefield=["Grizzly Bears", "Memnite", "Ornithopter"])
    )


def test_swirling_mist_exiling_two_blue_cards_phases_out_x_creatures_for_one_blue():
    """X=2 is {2}{U}; two exiled blue cards remove {4}, floored at the {2} of
    generic mana, leaving {U}."""
    scenario = _mist_board(["Opt", "Ponder"], battlefield=["Island"])
    opt = scenario.find("Opt", Zone.HAND, "alice")
    ponder = scenario.find("Ponder", Zone.HAND, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    memnite = scenario.creature("Memnite", "bob")
    (island,) = scenario.untapped_sources("Island", username="alice")

    casting = scenario.cast("March of Swirling Mist")
    casting.x_value = 2  # CR 601.2b: X is announced before CR 601.2c's targets
    casting.exile_for_cost_reduction([opt, ponder])
    casting.choose_targets([bears, memnite])
    scenario.pay_with(casting.begin_paying(), island)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert opt.zone is Zone.EXILE and ponder.zone is Zone.EXILE
    assert bears.phased_out and memnite.phased_out


def test_swirling_mist_more_targets_than_x_is_refused():
    scenario = _mist_board([], battlefield=["Island", "Island"])
    bears = scenario.creature("Grizzly Bears", "bob")
    memnite = scenario.creature("Memnite", "bob")
    thopter = scenario.creature("Ornithopter", "bob")
    casting = scenario.cast("March of Swirling Mist")
    casting.x_value = 2
    with pytest.raises(ValueError, match="at most 2"):
        casting.choose_targets([bears, memnite, thopter])


def test_swirling_mist_with_no_cards_exiled_pays_full_cost():
    scenario = _mist_board([], battlefield=["Island", "Island"])
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Island", "Island", username="alice")

    casting = scenario.cast("March of Swirling Mist")
    casting.x_value = 1
    casting.choose_targets([bears])
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.phased_out
    assert all(source.tapped for source in sources)


def test_the_exile_reduction_line_reader_credits_the_template_and_not_a_near_miss():
    from magic_cards_model.machines.casting import reads_optional_exile_reduction_line

    march = (
        "As an additional cost to cast this spell, you may exile any number of black "
        "cards from your hand. This spell costs {2} less to cast for each card exiled "
        "this way."
    )
    assert reads_optional_exile_reduction_line(march)
    assert reads_optional_exile_reduction_line(march.replace("black", "blue"))
    # No linked reduction: `exile_for_cost_reduction` would refuse to apply it.
    assert not reads_optional_exile_reduction_line(march.split(". This spell")[0] + ".")
    # A coloured amount CR 118.7a's generic-only reduction cannot apply.
    assert not reads_optional_exile_reduction_line(march.replace("{2}", "{B}"))
    # The sacrifice twin is read by its own reader, never this one.
    assert not reads_optional_exile_reduction_line(
        "As an additional cost to cast this spell, you may sacrifice any number of "
        "nonland permanents. This spell costs {1} less to cast for each permanent "
        "sacrificed this way."
    )
