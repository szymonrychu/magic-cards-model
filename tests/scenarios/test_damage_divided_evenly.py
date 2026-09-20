"""Scenario: damage "divided evenly, rounded down" among a spell's targets -
Fireball's own splitting method, distinct from Electrolyze's "divided as you
choose" (`test_damage_division.py`).

Fireball: "This spell costs {1} more to cast for each target beyond the
first.\\nFireball deals X damage divided evenly, rounded down, among any
number of targets." The division is not CR 601.2d's player-announced kind at
all: "If the spell requires the player to divide or distribute an effect ...
the player announces the division" (CR 601.2d) - and this one does not
require the player to do anything of the sort, since the card's own text
already says exactly how it splits. So the "each target must receive at
least one" floor CR 601.2d states for an *announced* division never applies
here, and a target can receive zero when X does not stretch across every
target chosen.

Dwarven Catapult ("Dwarven Catapult deals X damage divided evenly, rounded
down, among all creatures target opponent controls.") is the off-set
genericity proof, and it exercises a different part of the parser on
purpose: its only real CR 115.4 target is the single player named by "target
opponent", and "all creatures ... controls" is CR 611.2c's ordinary
computed-at-resolution recipient set - the identical grammar Settle the
Wreckage's "Exile all attacking creatures target player controls." already
uses - rather than a target list the caster chooses shares for. Left
unguarded, the generic "divided ... among <phrase>" reader would misread
"all creatures target opponent controls" as an ordinary CR 115.4 target
phrase (it contains "target opponent") and pay the whole total to the
*player* instead: this file's Dwarven Catapult tests are what pins that down.

Recipients here are Craw Wurm and Giant Spider (both toughness 4) rather than
a vanilla 2/2 or 3/3 - a share this file deals is never meant to be lethal
(CR 704.5g would destroy a creature and CR 120.3e's marked damage is not a
characteristic that survives the zone change, so a dead recipient reads back
`damage == 0` and would look exactly like the defect being tested for).

Every CR number here was verified with `mise run rules:find` in the session
that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _cast_x_spell(scenario, name, x_value, targets):
    casting = scenario.cast(name, targets=targets)
    casting.determine_cost(x_value=x_value)
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    return scenario.put_on_stack(casting)


def test_fireball_splits_x_evenly_with_no_remainder():
    """X=6 among 3 targets is 2 each, with nothing left over to drop."""
    scenario = (
        Scenario()
        .player("alice", hand=["Fireball"], battlefield=["Mountain"] * 9)
        .player("bob", battlefield=["Craw Wurm", "Giant Spider", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.creature("Craw Wurm", "bob")
    spider = scenario.creature("Giant Spider", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    resolved = _cast_x_spell(scenario, "Fireball", 6, [wurm, spider, giant])
    scenario.resolve_top()

    assert wurm.damage == 2
    assert spider.damage == 2
    assert giant.damage == 2
    assert resolved.zone is Zone.GRAVEYARD


def test_fireball_drops_the_remainder_rather_than_favouring_a_target():
    """X=7 among 3 targets is 2 each, with the leftover 1 simply gone -
    never handed to the first target the way an *un-announced* CR 601.2d
    "as you choose" division falls back to doing."""
    scenario = (
        Scenario()
        .player("alice", hand=["Fireball"], battlefield=["Mountain"] * 10)
        .player("bob", battlefield=["Craw Wurm", "Giant Spider", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.creature("Craw Wurm", "bob")
    spider = scenario.creature("Giant Spider", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    _cast_x_spell(scenario, "Fireball", 7, [wurm, spider, giant])
    scenario.resolve_top()

    assert wurm.damage == 2
    assert spider.damage == 2
    assert giant.damage == 2


def test_fireball_can_deal_zero_to_every_target_when_spread_too_thin():
    """X=2 spread across 3 targets floors to zero each - a legal cast that
    simply does nothing on resolution, not a refusal or an error."""
    scenario = (
        Scenario()
        .player("alice", hand=["Fireball"], battlefield=["Mountain"] * 5)
        .player("bob", battlefield=["Grizzly Bears", "Watchwolf", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    watchwolf = scenario.creature("Watchwolf", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    _cast_x_spell(scenario, "Fireball", 2, [bears, watchwolf, giant])
    scenario.resolve_top()

    assert bears.damage == 0
    assert watchwolf.damage == 0
    assert giant.damage == 0


def test_fireball_has_nothing_for_the_caster_to_announce():
    """CR 601.2d only applies when "the spell requires the player to divide"
    the effect - Fireball's own "evenly, rounded down" already says how, so
    `Casting.announce_division` correctly refuses: there is no division for
    the caster to make."""
    scenario = (
        Scenario()
        .player("alice", hand=["Fireball"], battlefield=["Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Fireball", targets=[bears])
    with pytest.raises(ValueError, match="does not divide anything to announce"):
        casting.announce_division([1])


# -- Dwarven Catapult: the off-set genericity proof -------------------------


def test_dwarven_catapult_splits_evenly_among_every_creature_the_target_opponent_controls():
    """A single CR 115.4 target (the opponent), with the recipients read off
    the computed board at resolution (CR 611.2c) rather than chosen - X=5
    among two creatures is 2 each, one dropped."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Dwarven Catapult"], battlefield=["Mountain"] * 7)
        .player("bob", battlefield=["Craw Wurm", "Giant Spider"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.creature("Craw Wurm", "bob")
    spider = scenario.creature("Giant Spider", "bob")

    _cast_x_spell(scenario, "Dwarven Catapult", 5, ["bob"])
    scenario.resolve_top()

    assert wurm.damage == 2
    assert spider.damage == 2


def test_dwarven_catapult_never_damages_the_targeted_player_directly():
    """The whole point this off-set card pins: the *player* is the target,
    but the damage lands on their creature, never on their life total."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Dwarven Catapult"], battlefield=["Mountain"] * 5)
        .player("bob", battlefield=["Craw Wurm"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.creature("Craw Wurm", "bob")

    _cast_x_spell(scenario, "Dwarven Catapult", 3, ["bob"])
    scenario.resolve_top()

    assert wurm.damage == 3
    assert scenario.player("bob").life == 20


def test_dwarven_catapult_leaves_the_casters_own_creatures_untouched():
    """ "All creatures target opponent controls" names only the target's
    board, so a creature the caster themselves controls takes none of it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Dwarven Catapult"],
            battlefield=["Craw Wurm", *(["Mountain"] * 5)],
        )
        .player("bob", battlefield=["Giant Spider"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    own_wurm = scenario.creature("Craw Wurm", "alice")
    spider = scenario.creature("Giant Spider", "bob")

    _cast_x_spell(scenario, "Dwarven Catapult", 3, ["bob"])
    scenario.resolve_top()

    assert spider.damage == 3
    assert own_wurm.damage == 0
