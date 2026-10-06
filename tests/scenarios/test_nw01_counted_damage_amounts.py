"""Scenario: damage whose amount is counted or computed rather than printed.

- "deals X damage to each creature, where X is the number of creatures on
  the battlefield" (Chain Reaction) - CR 107.3f's X defined by the text,
  counted once as the spell resolves, before any damage is dealt (CR 608.2h).
- "deals damage to target player equal to twice the number of white and/or
  blue permanents they control" (Chaotic Backlash) - counted on the targeted
  player's board, colours read per CR 105.1.
- "deals X damage to any target. Ferocious - deals X plus 2 damage instead if
  you control a creature with power 4 or greater" (Crater's Claws) - CR
  207.2c's ability word has no rules meaning; the condition is checked as the
  spell resolves and the alternative replaces the base (CR 614.1a).
- "deals five times X damage to each of up to X targets" (Crackle with
  Power) - CR 107.3a's X, announced before targets (CR 601.2b, 601.2c), bounds
  the target count; zero targets is legal (CR 115.6).

Proof printings for the same readers: War Report ("the number of creatures
on the battlefield plus the number of artifacts on the battlefield"), Sudden
Impact ("equal to the number of cards in that player's hand"), Kithkin Zealot
("for each black and/or red permanent target opponent controls"), and
Stonesplitter Bolt ("deals twice X damage ... instead").

Every CR number below was looked up with `mise run rules:find` this session:
CR 105.1, 107.3a, 107.3f, 115.6, 207.2c, 601.2b, 601.2c, 608.2b, 608.2h,
614.1a, 702.166a (bargain).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# Chain Reaction
# --------------------------------------------------------------------------


def _chain_board(alice, bob):
    scenario = (
        Scenario()
        .player("alice", hand=["Chain Reaction"], battlefield=[*alice, *["Mountain"] * 4])
        .player("bob", battlefield=bob)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_chain(scenario):
    scenario.cast_and_resolve("Chain Reaction", *scenario.untapped_sources(*["Mountain"] * 4))


def test_chain_reaction_counts_every_creature_on_both_sides():
    scenario = _chain_board(["Grizzly Bears"], ["Craw Wurm", "Hill Giant"])
    bears = scenario.creature("Grizzly Bears", "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    _cast_chain(scenario)

    assert bears.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.GRAVEYARD
    assert wurm.zone is Zone.BATTLEFIELD
    assert wurm.damage == 3, "three creatures were on the battlefield as it resolved"


def test_chain_reaction_counts_before_any_damage_is_dealt():
    """The count is taken once (CR 608.2h): creatures that die to this very
    damage still counted, so the survivor takes the full amount."""
    scenario = _chain_board(["Grizzly Bears", "Savannah Lions"], ["Craw Wurm", "Savannah Lions"])
    wurm = scenario.creature("Craw Wurm", "bob")

    _cast_chain(scenario)

    assert wurm.zone is Zone.GRAVEYARD, "4 damage to a 6/4"
    assert all(not state.is_creature for state in scenario.game.battlefield), (
        "every creature took 4"
    )


def test_chain_reaction_ignores_noncreature_permanents():
    scenario = _chain_board(["Glorious Anthem"], ["Craw Wurm"])
    wurm = scenario.creature("Craw Wurm", "bob")

    _cast_chain(scenario)

    assert wurm.damage == 1


def test_chain_reaction_with_no_creatures_does_nothing():
    scenario = _chain_board([], [])

    _cast_chain(scenario)

    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 20


# --------------------------------------------------------------------------
# Chaotic Backlash
# --------------------------------------------------------------------------


def _backlash_board(alice, bob):
    scenario = (
        Scenario()
        .player("alice", hand=["Chaotic Backlash"], battlefield=[*alice, *["Mountain"] * 5])
        .player("bob", battlefield=bob)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_chaotic_backlash_counts_the_targeted_players_white_and_blue_permanents():
    scenario = _backlash_board(
        ["Serra Angel", "Savannah Lions"],
        ["Savannah Lions", "Watchwolf", "Merfolk Looter", "Grizzly Bears", "Plains"],
    )

    scenario.cast_and_resolve(
        "Chaotic Backlash", *scenario.untapped_sources(*["Mountain"] * 5), targets=["bob"]
    )

    # Lions (W), Watchwolf (G/W), Looter (U): three; Bears is green, Plains
    # colourless. Alice's own white creatures do not count.
    assert scenario.player("bob").life == 20 - 6
    assert scenario.player("alice").life == 20


def test_chaotic_backlash_aimed_at_its_caster_counts_the_casters_permanents():
    scenario = _backlash_board(["Serra Angel", "Savannah Lions"], ["Merfolk Looter"])

    scenario.cast_and_resolve(
        "Chaotic Backlash", *scenario.untapped_sources(*["Mountain"] * 5), targets=["alice"]
    )

    assert scenario.player("alice").life == 20 - 4
    assert scenario.player("bob").life == 20


def test_chaotic_backlash_with_no_white_or_blue_permanents_deals_zero():
    scenario = _backlash_board(["Serra Angel"], ["Grizzly Bears", "Hill Giant"])

    scenario.cast_and_resolve(
        "Chaotic Backlash", *scenario.untapped_sources(*["Mountain"] * 5), targets=["bob"]
    )

    assert scenario.player("bob").life == 20


# --------------------------------------------------------------------------
# Crater's Claws
# --------------------------------------------------------------------------


def _claws_board(alice, bob=(), extra_hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Crater's Claws", *extra_hand],
            battlefield=[*alice, *["Mountain"] * 4],
        )
        .player("bob", battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_claws(scenario, x, target):
    casting = scenario.cast("Crater's Claws")
    casting.choose_modes([], x_value=x)
    casting.choose_targets([target])
    casting.determine_cost(x_value=x)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Mountain"] * (x + 1)))
    return scenario.put_on_stack(casting)


def test_craters_claws_deals_x_without_a_big_creature():
    scenario = _claws_board(["Grizzly Bears"])

    _cast_claws(scenario, 3, "bob")
    scenario.resolve_top()

    assert scenario.player("bob").life == 17


def test_craters_claws_deals_x_plus_two_with_a_power_four_creature():
    scenario = _claws_board(["Serra Angel"])

    _cast_claws(scenario, 3, "bob")
    scenario.resolve_top()

    assert scenario.player("bob").life == 15


def test_craters_claws_ignores_an_opponents_big_creature():
    """ "If you control": the opponent's 6/4 does not turn it on."""
    scenario = _claws_board(["Grizzly Bears"], bob=["Craw Wurm"])

    _cast_claws(scenario, 2, "bob")
    scenario.resolve_top()

    assert scenario.player("bob").life == 18


def test_craters_claws_checks_ferocious_as_it_resolves():
    """A creature pumped to power 4 in response counts: the condition is read
    on resolution, not on casting."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Crater's Claws", "Giant Growth"],
            battlefield=["Grizzly Bears", "Forest", *["Mountain"] * 3],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_claws(scenario, 2, "bob")
    scenario.cast_and_resolve("Giant Growth", *scenario.untapped_sources("Forest"), targets=[bears])

    scenario.resolve_top()

    assert scenario.player("bob").life == 20 - 4


def test_craters_claws_with_x_zero_and_ferocious_deals_two():
    scenario = _claws_board(["Serra Angel"])

    _cast_claws(scenario, 0, "bob")
    scenario.resolve_top()

    assert scenario.player("bob").life == 18


# --------------------------------------------------------------------------
# Crackle with Power
# --------------------------------------------------------------------------


def _crackle_board(bob=()):
    scenario = (
        Scenario()
        .player("alice", hand=["Crackle with Power"], battlefield=["Mountain"] * 8)
        .player("bob", battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_crackle(scenario, x, targets):
    casting = scenario.cast("Crackle with Power")
    casting.choose_modes([], x_value=x)
    casting.choose_targets(targets)
    casting.determine_cost(x_value=x)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Mountain"] * (3 * x + 2)))
    return scenario.put_on_stack(casting)


def test_crackle_with_power_deals_five_with_x_one():
    scenario = _crackle_board()

    _cast_crackle(scenario, 1, ["bob"])
    scenario.resolve_top()

    assert scenario.player("bob").life == 15


def test_crackle_with_power_deals_ten_to_each_of_two_targets():
    scenario = _crackle_board(bob=["Craw Wurm"])
    wurm = scenario.creature("Craw Wurm", "bob")

    _cast_crackle(scenario, 2, ["bob", wurm])
    scenario.resolve_top()

    assert scenario.player("bob").life == 10
    assert wurm.zone is Zone.GRAVEYARD


def test_crackle_with_power_cannot_take_more_targets_than_x():
    scenario = _crackle_board(bob=["Craw Wurm"])
    wurm = scenario.creature("Craw Wurm", "bob")

    with pytest.raises(ValueError):
        _cast_crackle(scenario, 1, ["bob", wurm])


def test_crackle_with_power_may_choose_no_targets():
    """CR 115.6: "up to X" allows zero targets; the spell still resolves."""
    scenario = _crackle_board()

    crackle = _cast_crackle(scenario, 1, [])
    scenario.resolve_top()

    assert crackle.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 20


def test_crackle_with_power_skips_a_target_that_became_illegal():
    """CR 608.2b: the creature that left is not dealt damage; the player
    still is."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Crackle with Power", "Lightning Bolt"],
            battlefield=["Mountain"] * 9,
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_crackle(scenario, 2, ["bob", bears])
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[bears]
    )

    scenario.resolve_top()

    assert scenario.player("bob").life == 10


# --------------------------------------------------------------------------
# Proof printings
# --------------------------------------------------------------------------


def test_war_report_counts_creatures_and_artifacts_on_the_battlefield():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["War Report"],
            battlefield=["Grizzly Bears", "Ornithopter", *["Plains"] * 4],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("War Report", *scenario.untapped_sources(*["Plains"] * 4))

    # Creatures: Bears, Ornithopter, Giant (3); artifacts: Ornithopter (1).
    assert scenario.player("alice").life == 24


def test_sudden_impact_counts_the_targeted_players_hand():
    scenario = (
        Scenario()
        .player("alice", hand=["Sudden Impact", "Mountain"], battlefield=["Mountain"] * 4)
        .player("bob", hand=["Grizzly Bears", "Hill Giant", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve(
        "Sudden Impact", *scenario.untapped_sources(*["Mountain"] * 4), targets=["bob"]
    )

    assert scenario.player("bob").life == 17, "bob's three cards, not alice's one"


def test_kithkin_zealot_counts_the_target_opponents_black_and_red_permanents():
    scenario = (
        Scenario()
        .player("alice", hand=["Kithkin Zealot"], battlefield=["Plains", "Plains", "Hill Giant"])
        .player("bob", battlefield=["Hill Giant", "Walking Corpse", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack("Kithkin Zealot", *scenario.untapped_sources("Plains", "Plains"))
    scenario.resolve_top()
    scenario.choose_trigger_targets("Kithkin Zealot", ["bob"])
    scenario.resolve_top()

    # Bob's red Giant and black Corpse count; his green Bears does not; alice's red
    # Giant does not.
    assert scenario.player("alice").life == 22


def test_stonesplitter_bolt_bargained_deals_twice_x():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Stonesplitter Bolt"],
            battlefield=["Ornithopter", *["Mountain"] * 3],
        )
        .player("bob", battlefield=["Craw Wurm"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.creature("Craw Wurm", "bob")
    thopter = scenario.creature("Ornithopter", "alice")

    casting = scenario.cast("Stonesplitter Bolt")
    casting.choose_modes([], x_value=2)
    casting.pay_bargain(thopter)
    casting.choose_targets([wurm])
    casting.determine_cost(x_value=2)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Mountain"] * 3))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert thopter.zone is Zone.GRAVEYARD
    assert wurm.zone is Zone.GRAVEYARD, "twice 2 is 4 damage to a 6/4"
