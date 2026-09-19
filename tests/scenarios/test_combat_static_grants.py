"""Scenario: FRA S9's combat statics - group and self grants that change
whether a creature can attack, how much damage it assigns, or whether it can
be blocked.

`machines/layers.py`/`machines/combat.py` had no reader for any of these four
shapes before this file:

- **Ghalta the Immovable** (Reality Fracture), "Creatures you control can
  attack as though they didn't have defender." - a group override of
  CR 702.3b, granting `machines/combat.py`'s own
  `ATTACK_WITHOUT_DEFENDER_TEXT` rather than a bare keyword. **Felothar the
  Steadfast** (off-set, the identical printed sentence on a different real
  card) proves the shape is read off the sentence, not the FRA card's name.
- **Ghalta the Immovable**'s second line, "Each creature you control with
  toughness greater than its power assigns combat damage equal to its
  toughness rather than its power." **Ancient Lumberknot** (off-set, the
  identical sentence on a different real creature) proves the same thing for
  the damage-assignment grant.
- **Loot, the Anomaly** (Reality Fracture), "If Loot's power is negative, he
  assigns combat damage as though his power were positive." - the self-only
  twin of Ghalta's group grant, gated on the object's own live power
  (`SelfIfPowerNegative`) rather than a team-wide comparison.
- **Tetsuko Umezawa, Fugitive** (Reality Fracture), "Creatures you control
  with power or toughness 1 or less can't be blocked." - granted as
  `machines/combat.py`'s own self-referential "This creature can't be
  blocked." line, which `_evasion_restriction_sentences` already reads off a
  computed ability (CR 613.5) regardless of which permanent's static put it
  there - no change to that reader was needed.

The rules these four rest on:

- **CR 702.3b** - "A creature with defender can't attack" - what Ghalta's
  first grant overrides.
- **CR 510.1a** - "Each attacking creature and each blocking creature assigns
  combat damage equal to its power. Creatures that would assign 0 or less
  damage this way don't assign combat damage at all." - the baseline both
  damage-assignment grants replace "its power" inside.
- **CR 509.1a** - a block "announces which attacking creature(s) ... it's
  blocking"; an attacker whose own text rules a creature out makes that
  announcement illegal - Tetsuko's grant makes every block on the qualifying
  creature illegal.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote it, and every card's text with
`resolve_cards` or straight off its fixture.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers import compute_board, static_effects
from magic_cards_model.models import Zone
from tests.cards import card_state
from tests.scenarios.harness import Scenario


def permanent(name: str, controller: str = "alice", **kwargs):
    return card_state(
        name, zone=Zone.BATTLEFIELD, controller=controller, owner=controller, **kwargs
    )


def board_of(*permanents):
    cards = list(permanents)
    return compute_board(cards, static_effects(cards))


ATTACK_WITHOUT_DEFENDER = "Can attack as though it didn't have defender."
ASSIGNS_AS_TOUGHNESS = "Assigns combat damage equal to its toughness rather than its power."


# --------------------------------------------------------------------------
# "Creatures you control can attack as though they didn't have defender."
# (Ghalta the Immovable)
# --------------------------------------------------------------------------


def test_ghalta_immovable_lets_a_defender_creature_attack():
    ghalta = permanent("Ghalta the Immovable")
    wall = permanent("Wall of Omens")

    assert board_of(ghalta, wall).of(wall).has_ability(ATTACK_WITHOUT_DEFENDER)


def test_ghalta_immovable_does_not_grant_it_to_an_opponents_wall():
    ghalta = permanent("Ghalta the Immovable")
    theirs = permanent("Wall of Omens", controller="bob")

    assert not board_of(ghalta, theirs).of(theirs).has_ability(ATTACK_WITHOUT_DEFENDER)


def test_felothar_grants_the_identical_attack_override_off_set():
    """Off-set proof: Felothar the Steadfast prints the exact same sentence
    on a different real card."""
    felothar = permanent("Felothar the Steadfast")
    wall = permanent("Wall of Omens")

    assert board_of(felothar, wall).of(wall).has_ability(ATTACK_WITHOUT_DEFENDER)


def test_ghalta_immovable_actually_lets_a_wall_attack_end_to_end():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ghalta the Immovable", "Wall of Omens"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wall = scenario.creature("Wall of Omens", "alice")

    assert scenario.can_attack(wall)


# --------------------------------------------------------------------------
# "Each creature you control with toughness greater than its power assigns
# combat damage equal to its toughness rather than its power." (Ghalta the
# Immovable)
# --------------------------------------------------------------------------


def test_ghalta_immovable_grants_toughness_assignment_to_a_creature_with_toughness_over_power():
    ghalta = permanent("Ghalta the Immovable")
    wall = permanent("Wall of Omens")  # 0/4: toughness (4) > power (0)

    assert board_of(ghalta, wall).of(wall).has_ability(ASSIGNS_AS_TOUGHNESS)


def test_ghalta_immovable_withholds_it_from_a_creature_whose_power_is_not_lower():
    ghalta = permanent("Ghalta the Immovable")
    bears = permanent("Grizzly Bears")  # 2/2: toughness is not greater than power

    assert not board_of(ghalta, bears).of(bears).has_ability(ASSIGNS_AS_TOUGHNESS)


def test_ancient_lumberknot_grants_the_identical_assignment_override_off_set():
    """Off-set proof: Ancient Lumberknot prints the exact same sentence on a
    different real creature."""
    lumberknot = permanent("Ancient Lumberknot")
    wall = permanent("Wall of Omens")

    assert board_of(lumberknot, wall).of(wall).has_ability(ASSIGNS_AS_TOUGHNESS)


def test_ghalta_immovable_wall_deals_toughness_damage_when_attacking_end_to_end():
    """A 0-power Wall of Omens would assign zero damage under CR 510.1a and
    the Wall's own damage never actually happens - the override is only
    provable by watching the number itself change.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ghalta the Immovable", "Wall of Omens"])
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wall = scenario.creature("Wall of Omens", "alice")

    scenario.attack_with(wall, defending="bob")
    scenario.no_blocks()
    dealt = scenario.combat_damage()

    bob = scenario.player("bob")
    assert (bob, 4) in dealt, "assigns equal to toughness (4), not power (0)"


# --------------------------------------------------------------------------
# "If Loot's power is negative, he assigns combat damage as though his power
# were positive." (Loot, the Anomaly)
# --------------------------------------------------------------------------


def test_loot_the_anomaly_deals_damage_as_though_its_power_were_positive():
    """Loot is a printed -2/4: under plain CR 510.1a it would assign zero
    damage and never actually deal any - the override is only provable by
    watching the number itself change, the same way Ghalta's Wall is above.
    """
    scenario = (
        Scenario().player("alice", battlefield=["Loot, the Anomaly"]).player("bob", life=20).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    loot = scenario.creature("Loot, the Anomaly", "alice")
    assert scenario.game.characteristics_of(loot).power_toughness == (-2, 4)

    scenario.attack_with(loot, defending="bob")
    scenario.no_blocks()
    dealt = scenario.combat_damage()

    bob = scenario.player("bob")
    assert (bob, 2) in dealt, "assigns as though power (-2) were positive (2)"


def test_loot_the_anomalys_grant_is_self_only_not_team_wide():
    """The condition is Loot's *own* power (`SelfIfPowerNegative`), not "any
    creature you control" - a positive-power creature next to Loot on the
    same battlefield must not pick up the grant."""
    from magic_cards_model.machines.combat import ASSIGNS_DAMAGE_AS_THOUGH_POSITIVE_TEXT

    loot = permanent("Loot, the Anomaly")
    bears = permanent("Grizzly Bears")

    board = board_of(loot, bears)
    assert board.of(loot).has_ability(ASSIGNS_DAMAGE_AS_THOUGH_POSITIVE_TEXT)
    assert not board.of(bears).has_ability(ASSIGNS_DAMAGE_AS_THOUGH_POSITIVE_TEXT)


# --------------------------------------------------------------------------
# "Creatures you control with power or toughness 1 or less can't be
# blocked." (Tetsuko Umezawa, Fugitive)
# --------------------------------------------------------------------------


def test_tetsuko_umezawa_makes_a_one_power_creature_unblockable():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tetsuko Umezawa, Fugitive", "Ornithopter"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ornithopter = scenario.creature("Ornithopter", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.attack_with(ornithopter, defending="bob")

    assert not scenario.game.can_block(bears, ornithopter)


def test_tetsuko_umezawa_leaves_a_bigger_creature_blockable():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tetsuko Umezawa, Fugitive", "Grizzly Bears"])
        .player("bob", battlefield=["Runeclaw Bear"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    attacker = scenario.creature("Grizzly Bears", "alice")
    blocker = scenario.creature("Runeclaw Bear", "bob")

    scenario.attack_with(attacker, defending="bob")

    assert scenario.game.can_block(blocker, attacker)


def test_tetsuko_umezawa_threshold_is_regex_general_not_hardcoded_to_one():
    """The parser reads whatever number is printed - proven here by matching
    a different threshold directly, since no second real Magic card prints
    this exact shape to add as an off-set example (`resolve_cards` turned up
    only Tetsuko herself)."""
    from magic_cards_model.machines.layers import _parse_layer_sentence

    two_or_less = _parse_layer_sentence(
        "Creatures you control with power or toughness 2 or less can't be blocked."
    )
    assert two_or_less is not None
