"""Scenario: a variable additional cost paid while casting, read back on
resolution as "this way" / "the sacrificed ..." / "the discarded ...".

Three printed shapes of CR 118.8's additional cost whose size is not fixed
by the text:

- "tap any number of untapped creatures you control" (Burn at the Stake) -
  CR 107.1c's "any number", zero included;
- "sacrifice all creatures you control" (Soulblast) - every one, chosen by
  nobody;
- "discard X cards" (Nahiri's Wrath) - CR 107.3a's X, announced while
  casting (CR 601.2b) and equal to the cards discarded.

Each is paid as part of the total cost (CR 601.2f, 601.2h) and the spell
then reads what was paid when it resolves: "three times the number of
creatures tapped this way", "the total power of the sacrificed creatures"
(CR 608.2h's last known information - the creatures are gone), "the total
mana value of the discarded cards" (CR 202.3). The proof printings exercise
the same readers on other templates: Corpse Cobble ("sacrifice any number of
creatures" / "the total power of the sacrificed creatures" as a token's
size), Vicious Betrayal ("for each creature sacrificed this way") and Tomb of
Urami ("Sacrifice all lands you control" inside an activation cost).

Every CR number below was looked up with `mise run rules:find` this session:

- CR 107.1c - "any number" may be zero.
- CR 107.3a - X in an additional cost is announced as part of casting.
- CR 118.3 - a cost cannot be paid without the resources; a tapped
  permanent cannot be tapped to pay one.
- CR 118.8 - additional costs.
- CR 601.2b/601.2c/601.2f/601.2h - announcing costs and X, then targets,
  then determining and paying the total cost.
- CR 608.2h - information from an object that has left its zone is its last
  known information.
- CR 701.21a - only a permanent you control can be sacrificed.
- CR 704.5d - a token outside the battlefield ceases to exist.
- CR 707.10 - a copy of a spell copies its additional costs.
- CR 115.6 - a spell may allow zero targets.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# Burn at the Stake: "tap any number of untapped creatures you control" /
# "three times the number of creatures tapped this way"
# --------------------------------------------------------------------------


def _burn_board(creatures: list[str], bob_creatures: list[str] | None = None):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Burn at the Stake", "Lightning Bolt"],
            battlefield=[*creatures, *["Mountain"] * 6],
        )
        .player("bob", battlefield=bob_creatures or [])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_burn(scenario, tapping, target):
    casting = scenario.cast("Burn at the Stake", tapping=tapping)
    casting.choose_targets([target])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Mountain"] * 5))
    return scenario.put_on_stack(casting)


def test_burn_at_the_stake_deals_three_per_creature_tapped():
    scenario = _burn_board(["Grizzly Bears", "Savannah Lions", "Hill Giant"])
    creatures = scenario.creatures("Grizzly Bears", "Savannah Lions", "Hill Giant")

    _cast_burn(scenario, creatures, "bob")
    scenario.resolve_top()

    assert all(creature.tapped for creature in creatures)
    assert scenario.player("bob").life == 20 - 9


def test_burn_at_the_stake_counts_only_the_creatures_chosen_not_every_creature():
    scenario = _burn_board(["Grizzly Bears", "Savannah Lions", "Hill Giant"])
    bears, lions, giant = scenario.creatures("Grizzly Bears", "Savannah Lions", "Hill Giant")

    _cast_burn(scenario, [bears, giant], "bob")
    scenario.resolve_top()

    assert bears.tapped and giant.tapped
    assert not lions.tapped, "a creature nobody nominated is not tapped"
    assert scenario.player("bob").life == 20 - 6


def test_burn_at_the_stake_may_tap_no_creatures_and_deals_zero():
    """CR 107.1c: "any number" includes zero, so the cast is legal."""
    scenario = _burn_board(["Grizzly Bears"])

    _cast_burn(scenario, [], "bob")
    scenario.resolve_top()

    assert scenario.player("bob").life == 20
    assert not scenario.creature("Grizzly Bears", "alice").tapped


def test_burn_at_the_stake_cannot_tap_an_already_tapped_creature():
    """CR 118.3: a permanent that's already tapped can't pay a tap cost."""
    scenario = _burn_board(["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.tap()

    with pytest.raises(ValueError, match="already tapped"):
        _cast_burn(scenario, [bears], "bob")


def test_burn_at_the_stake_cannot_tap_an_opponents_creature():
    """ "Creatures you control": an opponent's creature cannot pay it."""
    scenario = _burn_board(["Grizzly Bears"], bob_creatures=["Savannah Lions"])
    lions = scenario.creature("Savannah Lions", "bob")

    with pytest.raises(ValueError, match="does not control"):
        _cast_burn(scenario, [lions], "bob")


def test_burn_at_the_stake_keeps_the_count_when_a_tapped_creature_dies_in_response():
    """The number tapped is a fact about the payment, not the board: killing
    one of the tapped creatures before the spell resolves changes nothing."""
    scenario = _burn_board(["Grizzly Bears", "Savannah Lions"])
    bears, lions = scenario.creatures("Grizzly Bears", "Savannah Lions")
    _cast_burn(scenario, [bears, lions], "bob")

    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[lions])
    assert lions.zone is Zone.GRAVEYARD
    scenario.resolve_top()

    assert scenario.player("bob").life == 20 - 6


def test_burn_at_the_stake_can_hit_a_creature():
    scenario = _burn_board(["Grizzly Bears", "Savannah Lions"], bob_creatures=["Craw Wurm"])
    wurm = scenario.creature("Craw Wurm", "bob")

    _cast_burn(scenario, scenario.creatures("Grizzly Bears", "Savannah Lions"), wurm)
    scenario.resolve_top()

    assert wurm.zone is Zone.GRAVEYARD, "6 damage to a 6/4"


# --------------------------------------------------------------------------
# Soulblast: "sacrifice all creatures you control" / "the total power of
# the sacrificed creatures"
# --------------------------------------------------------------------------


def _soulblast_board(creatures, *, bob=None):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Soulblast"],
            battlefield=[*creatures, *["Mountain"] * 6],
        )
        .player("bob", battlefield=bob or [])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_soulblast(scenario, target):
    casting = scenario.cast("Soulblast")
    casting.choose_targets([target])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Mountain"] * 6))
    return scenario.put_on_stack(casting)


def test_soulblast_sacrifices_every_creature_and_deals_their_total_power():
    scenario = _soulblast_board(["Grizzly Bears", "Hill Giant", "Craw Wurm"])
    creatures = scenario.creatures("Grizzly Bears", "Hill Giant", "Craw Wurm")

    _cast_soulblast(scenario, "bob")
    assert all(creature.zone is Zone.GRAVEYARD for creature in creatures), (
        "the cost is paid before the spell is on the stack (CR 601.2h)"
    )
    scenario.resolve_top()

    assert scenario.player("bob").life == 20 - (2 + 3 + 6)


def test_soulblast_never_sacrifices_lands_or_an_opponents_creatures():
    scenario = _soulblast_board(["Grizzly Bears"], bob=["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")

    _cast_soulblast(scenario, "bob")
    scenario.resolve_top()

    assert giant.zone is Zone.BATTLEFIELD
    assert len(scenario.game.permanents_controlled_by("alice")) == 6, "the Mountains stay"
    assert scenario.player("bob").life == 18


def test_soulblast_with_no_creatures_is_castable_and_deals_zero():
    scenario = _soulblast_board([])

    _cast_soulblast(scenario, "bob")
    scenario.resolve_top()

    assert scenario.player("bob").life == 20


def test_soulblast_reads_the_pumped_power_the_creature_left_with():
    """CR 608.2h: last known information - Giant Growth's +3/+3 counts."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Soulblast", "Giant Growth"],
            battlefield=["Grizzly Bears", "Forest", *["Mountain"] * 6],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Giant Growth", *scenario.untapped_sources("Forest"), targets=[bears])

    _cast_soulblast(scenario, "bob")
    scenario.resolve_top()

    assert scenario.player("bob").life == 20 - 5


def test_soulblast_counts_a_sacrificed_token_that_has_ceased_to_exist():
    """CR 704.5d: the token is gone by resolution; its power was recorded as
    the cost was paid, so it still counts."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Soulblast", "Raise the Alarm"],
            battlefield=["Grizzly Bears", "Plains", "Plains", *["Mountain"] * 6],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Raise the Alarm", *scenario.untapped_sources("Plains", "Plains"))
    assert len(scenario.game.permanents_controlled_by("alice")) == 1 + 2 + 2 + 6

    _cast_soulblast(scenario, "bob")
    scenario.state_based_actions()
    scenario.resolve_top()

    assert scenario.player("bob").life == 20 - (2 + 1 + 1)


def test_a_copy_of_soulblast_deals_the_same_total():
    """CR 707.10: the copy copies the additional cost paid for the original."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Soulblast", "Reverberate"],
            battlefield=["Hill Giant", *["Mountain"] * 8],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    soulblast = _cast_soulblast(scenario, "bob")
    scenario.cast_onto_stack(
        "Reverberate", *scenario.untapped_sources("Mountain", "Mountain"), targets=[soulblast]
    )
    scenario.resolve_top()  # Reverberate puts the copy on the stack
    scenario.resolve_top()  # the copy
    scenario.resolve_top()  # Soulblast

    assert scenario.player("bob").life == 20 - 3 - 3


# --------------------------------------------------------------------------
# Nahiri's Wrath: "discard X cards" / "the total mana value of the discarded
# cards to each of up to X target creatures and/or planeswalkers"
# --------------------------------------------------------------------------


def _wrath_board(hand, bob):
    scenario = (
        Scenario()
        .player("alice", hand=["Nahiri's Wrath", *hand], battlefield=["Mountain"] * 3)
        .player("bob", battlefield=bob)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_wrath(scenario, x, discarding, targets):
    casting = scenario.cast("Nahiri's Wrath", discarding=discarding)
    casting.choose_modes([], x_value=x)
    casting.choose_targets(targets)
    casting.determine_cost(x_value=x)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain", "Mountain"))
    return scenario.put_on_stack(casting)


def test_nahiris_wrath_deals_the_discarded_mana_value_to_each_target():
    scenario = _wrath_board(["Lightning Bolt", "Hill Giant"], ["Craw Wurm", "Serra Angel"])
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    giant = scenario.find("Hill Giant", Zone.HAND, "alice")
    wurm, angel = scenario.creatures("Craw Wurm", "Serra Angel", username="bob")

    _cast_wrath(scenario, 2, [bolt, giant], [wurm, angel])
    assert bolt.zone is Zone.GRAVEYARD and giant.zone is Zone.GRAVEYARD
    scenario.resolve_top()

    # 1 + 4 = 5 to each: the 6/4 and the 4/4 both die.
    assert wurm.zone is Zone.GRAVEYARD
    assert angel.zone is Zone.GRAVEYARD


def test_nahiris_wrath_may_take_fewer_targets_than_x():
    """ "Up to X": one target is enough (CR 115.6)."""
    scenario = _wrath_board(["Lightning Bolt", "Hill Giant"], ["Craw Wurm", "Serra Angel"])
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    giant = scenario.find("Hill Giant", Zone.HAND, "alice")
    wurm, angel = scenario.creatures("Craw Wurm", "Serra Angel", username="bob")

    _cast_wrath(scenario, 2, [bolt, giant], [angel])
    scenario.resolve_top()

    assert angel.zone is Zone.GRAVEYARD
    assert wurm.zone is Zone.BATTLEFIELD
    assert wurm.damage == 0


def test_nahiris_wrath_cannot_take_more_targets_than_x():
    """CR 601.2c with X announced first (CR 601.2b): at most X targets."""
    scenario = _wrath_board(["Lightning Bolt"], ["Craw Wurm", "Serra Angel"])
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    wurm, angel = scenario.creatures("Craw Wurm", "Serra Angel", username="bob")

    with pytest.raises(ValueError):
        _cast_wrath(scenario, 1, [bolt], [wurm, angel])


def test_nahiris_wrath_needs_exactly_x_cards_discarded():
    """CR 118.3: X of 2 with one card nominated cannot be paid."""
    scenario = _wrath_board(["Lightning Bolt", "Hill Giant"], ["Craw Wurm"])
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    wurm = scenario.creature("Craw Wurm", "bob")

    with pytest.raises(ValueError):
        _cast_wrath(scenario, 2, [bolt], [wurm])


def test_nahiris_wrath_with_x_zero_discards_nothing_and_targets_nothing():
    scenario = _wrath_board(["Lightning Bolt"], ["Craw Wurm"])
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    wurm = scenario.creature("Craw Wurm", "bob")

    wrath = _cast_wrath(scenario, 0, [], [])
    scenario.resolve_top()

    assert bolt.zone is Zone.HAND
    assert wurm.damage == 0
    assert wrath.zone is Zone.GRAVEYARD


def test_nahiris_wrath_discarding_lands_deals_zero():
    """CR 202.3a: a land has no mana cost, so mana value 0."""
    scenario = _wrath_board(["Mountain"], ["Savannah Lions"])
    land = scenario.find("Mountain", Zone.HAND, "alice")
    lions = scenario.creature("Savannah Lions", "bob")

    _cast_wrath(scenario, 1, [land], [lions])
    scenario.resolve_top()

    assert lions.zone is Zone.BATTLEFIELD
    assert lions.damage == 0


# --------------------------------------------------------------------------
# Proof printings
# --------------------------------------------------------------------------


def test_corpse_cobble_makes_a_token_the_size_of_the_sacrificed_total_power():
    """ "Sacrifice any number of creatures" filled with what was nominated,
    and "the total power of the sacrificed creatures" read back."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Corpse Cobble"],
            battlefield=["Grizzly Bears", "Hill Giant", "Savannah Lions", "Island", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears, giant, lions = scenario.creatures("Grizzly Bears", "Hill Giant", "Savannah Lions")

    scenario.cast_and_resolve(
        "Corpse Cobble", *scenario.untapped_sources("Island", "Swamp"), sacrificing=[bears, giant]
    )

    assert bears.zone is Zone.GRAVEYARD and giant.zone is Zone.GRAVEYARD
    assert lions.zone is Zone.BATTLEFIELD
    (zombie,) = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if "Zombie" in state.subtypes
    ]
    assert scenario.game.power_of(zombie) == 5
    assert scenario.game.toughness_of(zombie) == 5


def test_vicious_betrayal_pumps_for_each_creature_sacrificed_this_way():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Vicious Betrayal"],
            battlefield=["Grizzly Bears", "Savannah Lions", "Hill Giant", *["Swamp"] * 5],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears, lions, giant = scenario.creatures("Grizzly Bears", "Savannah Lions", "Hill Giant")

    scenario.cast_and_resolve(
        "Vicious Betrayal",
        *scenario.untapped_sources(*["Swamp"] * 5),
        targets=[giant],
        sacrificing=[bears, lions],
    )

    assert scenario.game.power_of(giant) == 3 + 4
    assert scenario.game.toughness_of(giant) == 3 + 4


def test_tomb_of_urami_sacrifices_every_land_its_controller_controls():
    """ "Sacrifice all lands you control" inside an activation cost: every
    land goes, the Tomb itself and the Swamps that paid the mana included."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tomb of Urami", *["Swamp"] * 4, "Grizzly Bears"])
        .player("bob", battlefield=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tomb = scenario.find("Tomb of Urami", Zone.BATTLEFIELD, "alice")

    scenario.activate(tomb, *scenario.untapped_sources(*["Swamp"] * 4), index=1)
    scenario.resolve_top()

    alice_permanents = scenario.game.permanents_controlled_by("alice")
    assert {state.name for state in alice_permanents} == {"Grizzly Bears", "Urami"}
    assert scenario.find("Plains", Zone.BATTLEFIELD, "bob").zone is Zone.BATTLEFIELD


def test_might_of_the_masses_counts_once_as_it_resolves():
    """The same "for each" pump on a board count rather than a cost: read
    once (CR 608.2h), so the pump does not grow with a later creature."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Might of the Masses"],
            battlefield=["Grizzly Bears", "Savannah Lions", "Forest"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve(
        "Might of the Masses", *scenario.untapped_sources("Forest"), targets=[bears]
    )

    assert scenario.game.power_of(bears) == 2 + 2, "two creatures alice controls"
    assert scenario.game.toughness_of(bears) == 2 + 2
