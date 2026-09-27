"""ecl-T1's neighbouring amount templates: a difference between two
characteristics of one object (Doran, Besieged by Time), a difference
between two different objects (Spry and Mighty), a summed pair of count
terms (Gloom Ripper), and the greatest of a characteristic among a creature
*subtype* rather than a card type (Pummeler for Hire) - widening
`machines/effects._GREATEST_CHARACTERISTIC_AMONG_RE`, which used to answer
only "among creatures/artifacts you control".

Doran's own trigger also needs a *group* "attacks or blocks" compound event
(`machines/triggers._GROUP_ATTACKS_OR_BLOCKS_RE`): `_trigger_event` reads the
first event word it recognises in a condition and stops, so "a creature you
control attacks or blocks" was read as ATTACKS alone and the "or blocks" half
silently dropped - the identical gap `_ATTACKS_OR_BLOCKS_RE` already closes
for the self-referential "this creature attacks or blocks", now closed for
the non-self group form too.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- CR 508.1 / CR 509.1: declaring attackers and declaring blockers are two
  separate turn-based actions/events.
- CR 608.2h: the amount is read once, when the ability resolves.
- CR 107.1b: a negative result is zero - the "difference" itself is always
  non-negative (the greater minus the lesser), never a signed subtraction.
- CR 608.2d: "choose exactly two creatures you control" is a resolution-time
  choice (CR 601.2c's targeting is not involved at all).
- CR 107.2: "the greatest ... among" an empty group is zero.
- CR 205.3m: creature types are a kind of subtype - "Giants" names one, not a
  CR 205.2a card type.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _pt(scenario: Scenario, state):
    return scenario.game.power_of(state), scenario.game.toughness_of(state)


def _to_attackers(scenario: Scenario) -> None:
    scenario.advance()  # beginning of combat
    if scenario.stack_names():
        scenario.pass_until_resolved()
    if scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
    assert scenario.step is Step.DECLARE_ATTACKERS


# -- Doran, Besieged by Time: attacks-or-blocks, power/toughness difference ----


def test_doran_pumps_an_attacking_creature_by_its_power_toughness_difference():
    """ "Whenever a creature you control attacks or blocks, it gets +X/+X
    until end of turn, where X is the difference between its power and
    toughness." Ornithopter is a printed 0/2 - a difference of 2.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Doran, Besieged by Time", "Ornithopter"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thopter = scenario.creature("Ornithopter", "alice")
    _to_attackers(scenario)
    scenario.attack_with(thopter)
    scenario.pass_until_resolved()  # Doran's own attacks-or-blocks trigger

    assert _pt(scenario, thopter) == (2, 4)


def test_doran_pumps_a_blocking_creature_too():
    """CR 509.1: the *block* half of the same compound trigger - the gap
    `_GROUP_ATTACKS_OR_BLOCKS_RE` closes. Bob's Ornithopter blocks Alice's
    attacking Grizzly Bears; Doran (Alice's) is not the one attacking or
    blocking here, so this also proves the trigger reads "a creature *you*
    control" against its own controller, not the attacker's.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Doran, Besieged by Time", "Ornithopter"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    thopter = scenario.creature("Ornithopter", "bob")
    _to_attackers(scenario)
    scenario.attack_with(bears, defending="bob")
    scenario.block(bears, thopter)
    scenario.pass_until_resolved()  # Doran's own attacks-or-blocks trigger, on bob's side

    assert _pt(scenario, thopter) == (2, 4)
    assert _pt(scenario, bears) == (2, 2)  # bears is not Doran's controller's own


def test_doran_creature_spell_cost_reduction_and_the_pump_are_independent():
    """Doran's *other* line ("Each creature spell you cast with toughness
    greater than its power costs {1} less to cast") is proven in
    `test_characteristic_cost_reductions.py`; this only confirms the two
    lines coexist without one clobbering the other's own trigger. Doran
    itself is a printed 0/5 Treefolk Druid - a difference of 5.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Doran, Besieged by Time"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    doran = scenario.creature("Doran, Besieged by Time", "alice")
    printed = (doran.printed_power, doran.printed_toughness)
    _to_attackers(scenario)
    scenario.attack_with(doran)
    scenario.pass_until_resolved()

    difference = abs(printed[0] - printed[1])
    assert _pt(scenario, doran) == (printed[0] + difference, printed[1] + difference)


# -- Spry and Mighty: choose exactly two, difference of their powers -----------


def test_spry_and_mighty_draws_and_pumps_by_the_difference_of_chosen_powers():
    """ "Choose exactly two creatures you control. You draw X cards and the
    chosen creatures get +X/+X and gain trample until end of turn, where X
    is the difference between the chosen creatures' powers." Wall of Omens
    (0 power) and Hill Giant (3 power) is a difference of 3.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Spry and Mighty"],
            library=["Forest", "Forest", "Forest"],
            battlefield=["Wall of Omens", "Hill Giant"] + ["Forest"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 5)
    wall = scenario.creature("Wall of Omens", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    wall_pt, giant_pt = _pt(scenario, wall), _pt(scenario, giant)
    hand_before = len(scenario.player("alice").hand)
    scenario.will_choose_cards(wall, giant, username="alice", source="Spry and Mighty")

    scenario.cast_and_resolve("Spry and Mighty", *sources)

    difference = abs(wall_pt[0] - giant_pt[0])
    assert _pt(scenario, wall) == (wall_pt[0] + difference, wall_pt[1] + difference)
    assert _pt(scenario, giant) == (giant_pt[0] + difference, giant_pt[1] + difference)
    assert len(scenario.player("alice").hand) == hand_before - 1 + difference
    from magic_cards_model.machines.combat import has_keyword

    assert has_keyword(wall, "trample", scenario.game)
    assert has_keyword(giant, "trample", scenario.game)


def test_spry_and_mighty_with_equal_powers_still_grants_trample():
    """A difference of zero is still a legal amount (CR 107.1b never applies
    to a non-negative difference) - no cards drawn, no pump, but trample is
    granted unconditionally by the printed sentence.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Spry and Mighty"],
            library=["Forest"],
            battlefield=["Grizzly Bears", "Grizzly Bears"] + ["Forest"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 5)
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")
    hand_before = len(scenario.player("alice").hand)
    scenario.will_choose_cards(*bears, username="alice", source="Spry and Mighty")

    scenario.cast_and_resolve("Spry and Mighty", *sources)

    from magic_cards_model.machines.combat import has_keyword

    for bear in bears:
        assert _pt(scenario, bear) == (2, 2)
        assert has_keyword(bear, "trample", scenario.game)
    assert len(scenario.player("alice").hand) == hand_before - 1


# -- Pummeler for Hire: greatest power among a creature *subtype* --------------


def test_pummeler_for_hire_gains_life_equal_to_the_greatest_power_among_giants():
    """ "When this creature enters, you gain X life, where X is the greatest
    power among Giants you control." Hill Giant (3 power) and Pummeler for
    Hire itself (a Giant, 4 power) - the greatest is 4.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Pummeler for Hire"], battlefield=["Hill Giant"] + ["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 5)

    scenario.cast_and_resolve("Pummeler for Hire", *sources)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 24


def test_pummeler_for_hire_with_no_giants_gains_nothing():
    """CR 107.2: "the greatest ... among" an empty group is zero - no other
    Giants (Pummeler for Hire has not entered yet when its own trigger's
    amount would be computed against an empty board), so the amount is at
    least Pummeler for Hire's own power once it exists.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Pummeler for Hire"], battlefield=["Grizzly Bears"] + ["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 5)

    scenario.cast_and_resolve("Pummeler for Hire", *sources)
    scenario.pass_until_resolved()

    # Pummeler for Hire itself (a Giant, printed power 4) is on the
    # battlefield by the time its own ETB trigger resolves (CR 603.6a), so
    # it is its own greatest Giant even with no other Giants around.
    assert scenario.player("alice").life == 24


# -- Gloom Ripper: a summed pair of count terms, on two different targets ------


def test_gloom_ripper_pumps_and_debuffs_by_elves_controlled_plus_elves_in_graveyard():
    """ "target creature you control gets +X/+0 until end of turn and up to
    one target creature an opponent controls gets -0/-X until end of turn,
    where X is the number of Elves you control plus the number of Elf cards
    in your graveyard." Llanowar Elves and Gloom Ripper itself (an Elf
    Assassin, CR 603.6a counting itself once it has entered) controlled,
    plus an Elf card in the graveyard, is three - lethal to the 3-toughness
    Hill Giant (CR 704.5g).
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Gloom Ripper"],
            battlefield=["Llanowar Elves", "Grizzly Bears"] + ["Swamp"] * 5,
            graveyard=["Elvish Mystic"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Swamp"] * 5)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")

    scenario.cast_onto_stack("Gloom Ripper", *sources)
    scenario.choose_trigger_targets("Gloom Ripper", [bears, giant])
    scenario.pass_until_resolved()  # the creature spell itself
    scenario.pass_until_resolved()  # its own ETB trigger

    assert _pt(scenario, bears) == (5, 2)
    assert giant.zone is Zone.GRAVEYARD


def test_gloom_ripper_up_to_one_opponent_target_may_be_skipped():
    """CR 115.6: the second target is "up to one" - choosing none is legal,
    and the mandatory first target still gets the full pump. Gloom Ripper
    itself (an Elf) plus Llanowar Elves, with no Elf card in any graveyard,
    is two.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Gloom Ripper"],
            battlefield=["Llanowar Elves", "Grizzly Bears"] + ["Swamp"] * 5,
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Swamp"] * 5)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")

    scenario.cast_onto_stack("Gloom Ripper", *sources)
    scenario.choose_trigger_targets("Gloom Ripper", [bears])
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert _pt(scenario, bears) == (4, 2)
    assert _pt(scenario, giant) == (3, 3)
