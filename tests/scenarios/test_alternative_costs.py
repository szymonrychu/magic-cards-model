"""CR 118.9: an alternative cost, found and announced.

"Some spells have alternative costs. An alternative cost is a cost listed in a
spell's text, or applied to it from another effect, that its controller may pay
rather than paying the spell's mana cost." (CR 118.9)

This file is about *reaching* one. `test_counterspells.py` already plays Force
of Will and Force of Negation through `use_pitch_cost`, which only ever works
if the seat already knows the card prints a pitch cost; the mechanic here is
`Casting.alternative_costs` listing every CR 118.9 option a spell has, and
`Casting.use_alternative_cost` announcing the one that was picked (CR 601.2b).

The rules this file leans on, every number looked up this session:

- CR 118.9, 118.9a (only one per spell), 118.9b (generally optional),
  118.9c (the mana cost itself is unchanged), 118.9d (increases apply on top)
- CR 604.6: the spell's own static ability functioning from the zone it is
  cast from, which is what makes the printed offer readable while in hand
- CR 604.2: an ordinary battlefield static ability, which is Omniscience
- CR 601.2b announcement, CR 601.2f the total cost, CR 601.2h paying it
- CR 118.3: a cost cannot be paid without the resources to pay it fully
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import AlternativeCostSource
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# Finding one at all
# --------------------------------------------------------------------------


def test_a_spell_with_no_alternative_cost_lists_none():
    """The listing is the discovery mechanism, so it has to be honest about
    the ordinary case: Lightning Bolt offers nothing (CR 118.9)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Lightning Bolt")

    assert casting.alternative_costs == []
    with pytest.raises(ValueError, match="alternative cost"):
        casting.use_alternative_cost()


def test_fireblasts_printed_offer_is_listed_with_what_it_would_cost():
    """Fireblast's "You may sacrifice two Mountains rather than pay this
    spell's mana cost." is read off its own text (CR 604.6), and the listing
    reports how many objects the announcement has to choose (CR 601.2b)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Fireblast"], battlefield=["Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Fireblast", targets=["bob"])

    (option,) = casting.alternative_costs
    assert option.source is AlternativeCostSource.PRINTED
    assert option.available
    assert option.requires == 2
    assert "sacrifice" in option.description


# --------------------------------------------------------------------------
# Paying one that is legal
# --------------------------------------------------------------------------


def test_fireblast_is_cast_for_two_mountains_instead_of_its_mana_cost():
    """CR 118.9 in full: the {4}{R} is never paid, the two Mountains are
    sacrificed as part of paying the total cost (CR 601.2h), and the spell
    still resolves and deals its 4 damage."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Fireblast"], battlefield=["Mountain", "Mountain"])
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountains = scenario.untapped_sources("Mountain", "Mountain")

    casting = scenario.cast("Fireblast")
    casting.use_alternative_cost(choosing=mountains)
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 16
    assert all(mountain.zone is Zone.GRAVEYARD for mountain in mountains)


def test_the_alternative_cost_may_be_named_by_index():
    """`use_alternative_cost` takes the option's own `index`, which is what a
    seat that listed the options first will have in hand."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Fireblast"], battlefield=["Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountains = scenario.untapped_sources("Mountain", "Mountain")

    casting = scenario.cast("Fireblast")
    (option,) = casting.alternative_costs
    casting.use_alternative_cost(option.index, choosing=mountains)
    casting.choose_targets(["bob"])

    assert casting.alternative_cost is not None


def test_allosaurus_rider_exiles_two_green_cards_from_hand():
    """The same machinery on a creature spell, whose cost moves cards out of
    the hand rather than sacrificing permanents (CR 601.2h)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Allosaurus Rider", "Force of Vigor", "Force of Vigor"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    greens = [
        scenario.find("Force of Vigor", Zone.HAND),
        [
            state
            for state in scenario.player("alice").zones[Zone.HAND]
            if state.name == "Force of Vigor"
        ][1],
    ]

    casting = scenario.cast("Allosaurus Rider")
    casting.use_alternative_cost(choosing=greens)
    payment = casting.begin_paying()
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    rider = scenario.find("Allosaurus Rider", Zone.BATTLEFIELD)
    assert rider.zone is Zone.BATTLEFIELD
    assert all(green.zone is Zone.EXILE for green in greens)


# --------------------------------------------------------------------------
# Refused when the condition is not met
# --------------------------------------------------------------------------


def test_force_of_vigors_offer_is_listed_but_unavailable_on_your_own_turn():
    """CR 118.9b makes an alternative cost a *choice*, so "there is no option"
    and "there is an option you may decline" are different answers. On your
    own turn Force of Vigor's gate closes, and the listing says why rather
    than hiding the option."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Force of Vigor", "Lightning Bolt"])
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)  # alice's own turn
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    casting = scenario.cast("Force of Vigor", targets=[ring])

    (option,) = casting.alternative_costs
    assert not option.available
    assert "opponent's turn" in (option.unavailable or "")

    with pytest.raises(ValueError, match="opponent's turn"):
        casting.use_alternative_cost(choosing=[scenario.find("Lightning Bolt", Zone.HAND)])


def test_force_of_vigor_becomes_available_on_the_opponents_turn():
    """The same board one turn over: the gate is the turn, nothing else."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Sol Ring"])
        .player("bob", hand=["Force of Vigor", "Allosaurus Rider"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)  # alice is active, bob is not
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    green = scenario.find("Allosaurus Rider", Zone.HAND, "bob")  # the green card pitched
    scenario.pass_priority("alice")
    casting = scenario.cast("Force of Vigor", username="bob")

    (option,) = casting.alternative_costs
    assert option.available

    casting.use_alternative_cost(choosing=[green])
    casting.choose_targets([ring])
    payment = casting.begin_paying()
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert ring.zone is Zone.GRAVEYARD
    assert green.zone is Zone.EXILE


def test_the_alternative_cost_still_has_to_be_payable():
    """CR 118.3: announcing the alternative cost is not paying it. With only
    one Mountain on the battlefield, Fireblast's "sacrifice two Mountains"
    cannot be paid, and the payment - not the announcement - is what refuses."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Fireblast"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")

    casting = scenario.cast("Fireblast")
    casting.use_alternative_cost(choosing=[mountain])
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    with pytest.raises(ValueError):
        payment.pay()


# --------------------------------------------------------------------------
# What still applies on top of it
# --------------------------------------------------------------------------


def test_a_cost_increase_applies_on_top_of_the_alternative_cost():
    """CR 118.9d: "If an alternative cost is being paid to cast a spell, any
    additional costs, cost increases, and cost reductions that affect that
    spell are applied to that alternative cost."

    Sphere of Resistance's "Spells cost {1} more to cast" is a board-wide
    increase, so Fireblast pitched for two Mountains still owes {1} - not
    {4}{R} plus one, and not nothing.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Fireblast"],
            battlefield=["Mountain", "Mountain", "Mountain", "Sphere of Resistance"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sacrificed = scenario.untapped_sources("Mountain", "Mountain")
    (paying,) = [
        state
        for state in scenario.untapped_sources("Mountain", "Mountain", "Mountain")
        if state not in sacrificed
    ]

    casting = scenario.cast("Fireblast")
    casting.use_alternative_cost(choosing=sacrificed)
    casting.choose_targets(["bob"])
    payment = casting.determine_cost()

    assert casting.total_cost.mana.generic == 1, "Sphere's {1}, on top of the pitch"

    scenario.pay_with(payment, paying)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 16


def test_the_alternative_cost_does_not_change_the_spells_mana_cost():
    """CR 118.9c: "An alternative cost doesn't change a spell's mana cost,
    only what its controller has to pay to cast it." Fireblast's mana value
    stays 5 while it is being cast for two Mountains."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Fireblast"], battlefield=["Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountains = scenario.untapped_sources("Mountain", "Mountain")

    casting = scenario.cast("Fireblast")
    casting.use_alternative_cost(choosing=mountains)
    casting.choose_targets(["bob"])

    assert casting.spell.card.cmc == 6, "Fireblast is {4}{R}{R} whatever is paid"
    assert casting.total_cost.mana.generic == 0


def test_only_one_alternative_cost_may_be_applied():
    """CR 118.9a: "Only one alternative cost can be applied to any one spell
    as it's being cast." """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Fireblast"], battlefield=["Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountains = scenario.untapped_sources("Mountain", "Mountain")

    casting = scenario.cast("Fireblast")
    casting.use_alternative_cost(choosing=mountains)
    with pytest.raises(ValueError, match="only one alternative cost"):
        casting.use_alternative_cost(choosing=mountains)


# --------------------------------------------------------------------------
# Declining it: the printed mana cost is still there
# --------------------------------------------------------------------------


def test_fireblast_may_still_be_hardcast_for_its_printed_mana_cost():
    """CR 118.9b: "Alternative costs are generally optional." Nothing about
    printing one takes the ordinary cast away, and the Mountains survive."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Fireblast"],
            battlefield=["Mountain"] * 6,
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources(*["Mountain"] * 6)

    fireblast = scenario.cast_and_resolve("Fireblast", *lands, targets=["bob"])

    assert fireblast.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 16
    assert all(land.zone is Zone.BATTLEFIELD for land in lands), "nothing was sacrificed"


# --------------------------------------------------------------------------
# CR 118.9's other half: a cost applied from another effect
# --------------------------------------------------------------------------


def test_omniscience_applies_an_alternative_cost_to_a_spell_that_prints_none():
    """CR 118.9's "or applied to it from another effect", as an ordinary
    battlefield static ability (CR 604.2). Lightning Bolt's own text says
    nothing about alternative costs; Omniscience is what puts one on it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Omniscience"])
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Lightning Bolt")

    (option,) = casting.alternative_costs
    assert option.source is AlternativeCostSource.STATIC
    assert option.source_name == "Omniscience"
    assert option.available

    casting.use_alternative_cost()
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 17
    assert casting.free_cast_source == "Omniscience"


def test_omniscience_does_not_reach_an_opponents_spell():
    """ "You may cast spells from *your* hand" - CR 604.2's static ability is
    its controller's, and bob's hand is not alice's."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Omniscience"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Lightning Bolt", username="bob", targets=["alice"])

    assert casting.alternative_costs == []


def test_omniscience_does_not_reach_a_spell_cast_from_the_graveyard():
    """The grant names the hand, and CR 118.9's cost is applied to the spell
    being cast, not to the card in general - a flashbacked spell is being
    cast from the graveyard and Omniscience has nothing to say about it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            graveyard=["Past in Flames"],
            battlefield=["Omniscience"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Past in Flames", from_zone=Zone.GRAVEYARD)

    static = [
        option
        for option in casting.alternative_costs
        if option.source is AlternativeCostSource.STATIC
    ]
    assert static and not static[0].available
    assert "hand" in (static[0].unavailable or "")


# -- Omnipresence: the same grant, capped by a live mana-value count --------


def test_omnipresence_makes_a_cheap_spell_free_when_enough_creatures_are_out():
    """Omnipresence: "You may cast spells with mana value less than or equal
    to the number of creatures you control from your hand without paying
    their mana costs." Two creatures out, casting Lightning Bolt (mana value
    1): within the live cap, so the grant is available."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Omnipresence", "Grizzly Bears", "Hill Giant"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Lightning Bolt")

    (option,) = casting.alternative_costs
    assert option.source is AlternativeCostSource.STATIC
    assert option.source_name == "Omnipresence"
    assert option.available

    casting.use_alternative_cost()
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 17
    assert casting.free_cast_source == "Omnipresence"


def test_omnipresence_is_unavailable_with_no_creatures_to_count():
    """No creatures controlled: the live cap is 0, so even Lightning Bolt's
    mana value of 1 is over it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Omnipresence"])
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Lightning Bolt")

    (option,) = casting.alternative_costs
    assert not option.available
    assert "mana value 0 or less" in (option.unavailable or "")


def test_omnipresence_is_unavailable_when_the_spell_is_still_too_expensive():
    """One creature out (cap 1), Counterspell's mana value is 2 - over the
    cap, so the grant does not reach it even though it is a real hand card."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Counterspell"], battlefield=["Omnipresence", "Grizzly Bears"])
        .player("bob", hand=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Counterspell")

    (option,) = casting.alternative_costs
    assert not option.available
    assert "mana value 1 or less" in (option.unavailable or "")


def test_omnipresence_does_not_reach_an_opponents_spell():
    """ "You may cast spells ... from *your* hand" - the same controller
    scoping Omniscience's own grant already has."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Omnipresence", "Grizzly Bears", "Hill Giant"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Lightning Bolt", username="bob", targets=["alice"])

    assert casting.alternative_costs == []


def test_delraich_is_cast_for_three_black_creatures():
    """A colour requirement rather than a subtype one, and three objects
    rather than two - the announcement chooses them all (CR 601.2b) and the
    payment sacrifices them (CR 601.2h)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Delraich"],
            battlefield=["Relentless Rats", "Relentless Rats", "Relentless Rats"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rats = scenario.untapped_sources("Relentless Rats", "Relentless Rats", "Relentless Rats")

    casting = scenario.cast("Delraich")
    casting.use_alternative_cost(choosing=rats)
    payment = casting.begin_paying()
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert scenario.find("Delraich", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD
    assert all(rat.zone is Zone.GRAVEYARD for rat in rats)


def test_two_force_of_negations_are_both_pitched_in_the_same_turn():
    """The gap this file was written for: in a real game a seat wanted to pay
    Force of Negation's alternative cost twice and could not reach it at all.
    Nothing in CR 118.9a stops a *second* spell paying its own alternative
    cost - the rule is one alternative cost per spell, not per turn.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Opt", "Opt"], battlefield=["Island", "Island"])
        .player(
            "bob",
            hand=["Force of Negation", "Force of Negation", "Opt", "Opt"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)  # alice is active; bob is not
    blue_cards = [state for state in scenario.player("bob").zones[Zone.HAND] if state.name == "Opt"]
    negations = [
        state
        for state in scenario.player("bob").zones[Zone.HAND]
        if state.name == "Force of Negation"
    ]

    for spell, pitched in zip(negations, blue_cards, strict=True):
        (island,) = scenario.untapped_sources("Island", username="alice")
        target = scenario.cast_onto_stack("Opt", island, username="alice", auto=True)
        scenario.pass_priority("alice")

        casting = scenario.cast("Force of Negation", username="bob")
        assert casting.spell is spell
        (option,) = [found for found in casting.alternative_costs if found.available]
        casting.use_alternative_cost(option.index, choosing=[pitched])
        casting.choose_targets([target])
        payment = casting.begin_paying()
        payment.pay()
        scenario.put_on_stack(casting)
        scenario.pass_until_resolved()

        assert target.zone is Zone.EXILE

    assert all(pitched.zone is Zone.EXILE for pitched in blue_cards)
    assert all(spell.zone is Zone.GRAVEYARD for spell in negations)
