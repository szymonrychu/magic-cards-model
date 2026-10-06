"""Scenario: "Excess damage is dealt to that creature's controller instead."

Flame Spill, Pigment Storm, Gandalf's Sanction (listed) and Ram Through (the
second printing, "If the creature you control has trample, excess damage is
dealt to that creature's controller instead").

Verified this session with `mise run rules:find`:

- **CR 120.4a** - the damage event is modified before it is dealt: for a
  creature, the excess is the amount above lethal damage, taking damage
  already marked into account, and "any amount of damage greater than 1 is
  excess damage if the source dealing that damage to a creature has
  deathtouch".
- **CR 120.3a** - damage to a player makes that player lose that much life.
- **CR 608.2b** - a spell whose only target is illegal on resolution does
  nothing at all.

Ram Through is the only other in-pool printing of this template (Scryfall
`o:"excess damage is dealt to that"` in Modern/Pioneer/Standard returns the
four cards used here).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _board(*, alice_hand, alice_battlefield, bob_battlefield, alice_graveyard=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=list(alice_battlefield),
            graveyard=list(alice_graveyard),
        )
        .player("bob", battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _bob_life(scenario):
    return scenario.player("bob").life


# -- Flame Spill ---------------------------------------------------------------


def test_flame_spill_sends_the_excess_over_a_2_toughness_creature_to_its_controller():
    scenario = _board(
        alice_hand=["Flame Spill"],
        alice_battlefield=["Mountain"] * 3,
        bob_battlefield=["Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_and_resolve(
        "Flame Spill",
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain"),
        targets=[bears],
    )
    assert bears.zone is Zone.GRAVEYARD
    assert _bob_life(scenario) == 18  # 4 damage, 2 lethal, 2 excess


def test_flame_spill_with_no_excess_deals_nothing_to_the_controller():
    scenario = _board(
        alice_hand=["Flame Spill"],
        alice_battlefield=["Mountain"] * 3,
        bob_battlefield=["Colossal Dreadmaw"],
    )
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.cast_and_resolve(
        "Flame Spill",
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain"),
        targets=[dreadmaw],
    )
    assert dreadmaw.zone is Zone.BATTLEFIELD
    assert dreadmaw.damage == 4
    assert _bob_life(scenario) == 20


def test_flame_spill_exactly_lethal_is_no_excess():
    scenario = _board(
        alice_hand=["Flame Spill"],
        alice_battlefield=["Mountain"] * 3,
        bob_battlefield=["Hill Giant"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    giant.damage = 0
    scenario.cast_and_resolve(
        "Flame Spill",
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain"),
        targets=[giant],
    )
    assert giant.zone is Zone.GRAVEYARD
    assert _bob_life(scenario) == 19  # 4 damage, 3 lethal, 1 excess


def test_flame_spill_counts_damage_already_marked_as_part_of_lethal():
    """CR 120.4a: lethal damage takes damage already marked into account, so
    a 2/2 with 1 damage marked has 1 left and 3 of the 4 is excess."""
    scenario = _board(
        alice_hand=["Flame Spill"],
        alice_battlefield=["Mountain"] * 3,
        bob_battlefield=["Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.damage = 1
    scenario.cast_and_resolve(
        "Flame Spill",
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain"),
        targets=[bears],
    )
    assert bears.zone is Zone.GRAVEYARD
    assert _bob_life(scenario) == 17


def test_flame_spill_with_an_illegal_target_does_nothing():
    """CR 608.2b: the only target is gone, so the spell is countered on
    resolution and its controller's opponent loses no life."""
    scenario = _board(
        alice_hand=["Flame Spill"],
        alice_battlefield=["Mountain"] * 3,
        bob_battlefield=["Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_onto_stack(
        "Flame Spill",
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain"),
        targets=[bears],
    )
    scenario.game.destroy(bears)
    scenario.resolve_top()
    assert _bob_life(scenario) == 20


def test_flame_spill_on_your_own_creature_hurts_you():
    scenario = _board(
        alice_hand=["Flame Spill"],
        alice_battlefield=["Mountain"] * 3 + ["Grizzly Bears"],
        bob_battlefield=[],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve(
        "Flame Spill",
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain"),
        targets=[bears],
    )
    assert scenario.player("alice").life == 18
    assert _bob_life(scenario) == 20


# -- Pigment Storm -------------------------------------------------------------


def test_pigment_storm_sends_four_excess_over_a_1_1_to_the_controller():
    scenario = _board(
        alice_hand=["Pigment Storm"],
        alice_battlefield=["Mountain"] * 5,
        bob_battlefield=["Elvish Mystic"],
    )
    mystic = scenario.creature("Elvish Mystic", "bob")
    scenario.cast_and_resolve(
        "Pigment Storm", *scenario.untapped_sources(*["Mountain"] * 5), targets=[mystic]
    )
    assert mystic.zone is Zone.GRAVEYARD
    assert _bob_life(scenario) == 16


def test_pigment_storm_on_an_exactly_5_toughness_creature_is_no_excess():
    scenario = _board(
        alice_hand=["Pigment Storm"],
        alice_battlefield=["Mountain"] * 5,
        bob_battlefield=["Colossal Dreadmaw"],
    )
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.cast_and_resolve(
        "Pigment Storm", *scenario.untapped_sources(*["Mountain"] * 5), targets=[dreadmaw]
    )
    assert dreadmaw.damage == 5
    assert _bob_life(scenario) == 20


# -- Gandalf's Sanction --------------------------------------------------------


def test_gandalfs_sanction_x_counts_instants_and_sorceries_in_your_graveyard():
    scenario = _board(
        alice_hand=["Gandalf's Sanction"],
        alice_battlefield=["Mountain", "Mountain", "Island"],
        bob_battlefield=["Grizzly Bears"],
        alice_graveyard=["Giant Growth", "Giant Growth", "Giant Growth", "Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_and_resolve(
        "Gandalf's Sanction",
        *scenario.untapped_sources("Mountain", "Mountain", "Island"),
        targets=[bears],
    )
    assert bears.zone is Zone.GRAVEYARD
    assert _bob_life(scenario) == 19  # X = 3 (the creature card does not count)


def test_gandalfs_sanction_with_an_empty_graveyard_deals_zero():
    scenario = _board(
        alice_hand=["Gandalf's Sanction"],
        alice_battlefield=["Mountain", "Mountain", "Island"],
        bob_battlefield=["Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_and_resolve(
        "Gandalf's Sanction",
        *scenario.untapped_sources("Mountain", "Mountain", "Island"),
        targets=[bears],
    )
    assert bears.zone is Zone.BATTLEFIELD
    assert bears.damage == 0
    assert _bob_life(scenario) == 20


# -- Ram Through (second printing) ---------------------------------------------


def _ram_through(*, biter, victim):
    scenario = _board(
        alice_hand=["Ram Through"],
        alice_battlefield=["Forest", "Forest", biter],
        bob_battlefield=[victim],
    )
    mine = scenario.creature(biter, "alice")
    theirs = scenario.creature(victim, "bob")
    scenario.cast_and_resolve(
        "Ram Through", *scenario.untapped_sources("Forest", "Forest"), targets=[mine, theirs]
    )
    return scenario, mine, theirs


def test_ram_through_with_a_trampler_sends_the_excess_to_the_controller():
    scenario, _, victim = _ram_through(biter="Colossal Dreadmaw", victim="Grizzly Bears")
    assert victim.zone is Zone.GRAVEYARD
    assert _bob_life(scenario) == 16  # 6 power, 2 lethal, 4 excess


def test_ram_through_without_trample_keeps_all_the_damage_on_the_creature():
    scenario, _, victim = _ram_through(biter="Hill Giant", victim="Elvish Mystic")
    assert victim.zone is Zone.GRAVEYARD
    assert _bob_life(scenario) == 20


def test_ram_through_trampler_with_no_excess_leaves_the_controller_alone():
    scenario, _, victim = _ram_through(biter="Colossal Dreadmaw", victim="Colossal Dreadmaw")
    assert victim.zone is Zone.GRAVEYARD  # 6 damage on a 6/6
    assert _bob_life(scenario) == 20


def test_ram_through_deathtouch_trampler_needs_only_one_lethal():
    """CR 120.4a: any amount greater than 1 is excess when the source has
    deathtouch. Rancor on Typhoid Rats is a 3/1 deathtouch trampler: 1 is
    lethal to the 2/2 Bears, the other 2 go to Bob."""
    scenario = _board(
        alice_hand=["Ram Through", "Rancor"],
        alice_battlefield=["Forest", "Forest", "Forest", "Typhoid Rats"],
        bob_battlefield=["Grizzly Bears"],
    )
    rats = scenario.creature("Typhoid Rats", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_and_resolve("Rancor", *scenario.untapped_sources("Forest"), targets=[rats])
    scenario.cast_and_resolve(
        "Ram Through", *scenario.untapped_sources("Forest", "Forest"), targets=[rats, bears]
    )
    assert bears.zone is Zone.GRAVEYARD
    assert _bob_life(scenario) == 18


def test_ram_through_with_the_biter_gone_does_nothing():
    scenario = _board(
        alice_hand=["Ram Through"],
        alice_battlefield=["Forest", "Forest", "Colossal Dreadmaw"],
        bob_battlefield=["Grizzly Bears"],
    )
    mine = scenario.creature("Colossal Dreadmaw", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_onto_stack(
        "Ram Through", *scenario.untapped_sources("Forest", "Forest"), targets=[mine, theirs]
    )
    scenario.game.destroy(mine)
    scenario.resolve_top()
    assert theirs.zone is Zone.BATTLEFIELD
    assert _bob_life(scenario) == 20
