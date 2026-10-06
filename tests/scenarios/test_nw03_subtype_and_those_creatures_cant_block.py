"""Group "can't block this turn" restrictions that name their group by a
creature type, or by "those creatures" after a multi-target damage clause.

Pyrophobia: "Pyrophobia deals 3 damage to target creature. Cowards can't block
this turn."
Sparkmage's Gambit: "Sparkmage's Gambit deals 1 damage to each of up to two
target creatures. Those creatures can't block this turn."
Second printings of the second shape: Wrap in Flames (up to three targets) and
Rowan, Fearless Sparkmage's -2 (an ability, Modern/Pioneer, in no api deck).

No second Modern/Pioneer/Standard printing carries a creature-type group
restriction in this shape (Scryfall search over the format pool, 2026-10-06:
the only "<Plural noun> can't block this turn" line is Pyrophobia's), so the
subtype reader is proven on Pyrophobia with changelings and a late-arriving
Coward as the corner cases.

Rules verified with `mise run rules:find`:

- **CR 509.1b** - a restriction on blocking is checked as blockers are
  declared.
- **CR 205.3m** - creature types; **CR 702.73a** - changeling: the object is
  every creature type, so it is a Coward.
- **CR 611.2c** - only a continuous effect that changes characteristics or
  controllers locks in its set when it begins. "Can't block" changes none, so
  a creature that becomes a Coward later this turn is restricted as well.
- **CR 608.2b** - "those creatures" are the spell's targets still legal on
  resolution.
- **CR 120.3** - the damage is dealt, then the restriction applies.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _cant_block(scenario, state) -> bool:
    board = scenario.game.continuous_effects.board(scenario.game.battlefield)
    return "This creature can't block." in board.of(state).abilities


def _notices(scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _attack_and_try_to_block(scenario, attacker_name, blocker):
    scenario.start_at(Step.DECLARE_ATTACKERS)
    attacker = scenario.creature(attacker_name, "alice")
    attacker.summoning_sick = False
    scenario.attack_with(attacker)
    scenario.block(attacker, blocker)


def _board(hand, alice, bob, lands) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=list(hand), battlefield=[*lands, *alice])
        .player("bob", battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- Pyrophobia: "Cowards can't block this turn" -------------------------------

PYRO_LANDS = ("Mountain", "Mountain")


def _pyrophobia(bob, *, alice=("Grizzly Bears",), target="Gray Ogre"):
    scenario = _board(["Pyrophobia"], alice, bob, PYRO_LANDS)
    victim = scenario.creature(target, "bob")
    sources = scenario.untapped_sources(*PYRO_LANDS, username="alice")
    scenario.cast_and_resolve("Pyrophobia", *sources, username="alice", targets=[victim])
    scenario.state_based_actions()
    return scenario, victim


def test_pyrophobia_deals_its_damage_and_stops_a_coward_blocking():
    scenario, ogre = _pyrophobia(["Gray Ogre", "Craven Hulk", "Hill Giant"])
    hulk = scenario.creature("Craven Hulk", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    assert ogre.zone is Zone.GRAVEYARD
    assert _cant_block(scenario, hulk)
    assert not _cant_block(scenario, giant)
    assert _notices(scenario) == []


def test_a_coward_really_cannot_be_declared_as_a_blocker():
    scenario, _ogre = _pyrophobia(["Gray Ogre", "Craven Hulk", "Hill Giant"])
    hulk = scenario.creature("Craven Hulk", "bob")

    with pytest.raises(ValueError, match=r"can't block"):
        _attack_and_try_to_block(scenario, "Grizzly Bears", hulk)


def test_a_creature_that_is_not_a_coward_still_blocks():
    scenario, _ogre = _pyrophobia(["Gray Ogre", "Craven Hulk", "Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")

    _attack_and_try_to_block(scenario, "Grizzly Bears", giant)

    assert scenario.blockers() == [giant]


def test_a_changeling_is_a_coward_because_it_is_every_creature_type():
    """CR 702.73a."""
    scenario, _ogre = _pyrophobia(["Gray Ogre", "Fire-Belly Changeling"])
    changeling = scenario.creature("Fire-Belly Changeling", "bob")

    assert _cant_block(scenario, changeling)


def test_the_restriction_covers_the_casters_own_cowards_too():
    scenario, _ogre = _pyrophobia(["Gray Ogre"], alice=("Craven Hulk",))
    mine = scenario.creature("Craven Hulk", "alice")

    assert _cant_block(scenario, mine)


def test_a_creature_that_becomes_a_coward_later_this_turn_cannot_block_either():
    """CR 611.2c: a can't-block restriction does not fix its set when it
    begins, so Amoeboid Changeling granting a creature all creature types
    afterwards brings it under the restriction."""
    scenario, _ogre = _pyrophobia(
        ["Gray Ogre", "Hill Giant", "Amoeboid Changeling"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    amoeboid = scenario.creature("Amoeboid Changeling", "bob")
    assert not _cant_block(scenario, giant)
    amoeboid.summoning_sick = False
    scenario.pass_priority("alice")
    scenario.activate(amoeboid, username="bob", targets=[giant])
    scenario.resolve_top()

    assert _cant_block(scenario, giant)


def test_a_coward_that_enters_later_this_turn_cannot_block():
    scenario = (
        Scenario()
        .player("alice", hand=["Pyrophobia"], battlefield=[*PYRO_LANDS, "Grizzly Bears"])
        .player("bob", hand=["Craven Hulk"], battlefield=["Gray Ogre"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ogre = scenario.creature("Gray Ogre", "bob")
    sources = scenario.untapped_sources(*PYRO_LANDS, username="alice")
    scenario.cast_and_resolve("Pyrophobia", *sources, username="alice", targets=[ogre])
    late = scenario.put_onto_battlefield("Craven Hulk", "bob")

    assert _cant_block(scenario, late)


def test_the_restriction_ends_with_the_turn():
    scenario, _ogre = _pyrophobia(["Gray Ogre", "Craven Hulk"])
    hulk = scenario.creature("Craven Hulk", "bob")
    scenario.game.continuous_effects.end_the_turn(scenario.game)

    assert not _cant_block(scenario, hulk)


def test_pyrophobia_can_target_a_coward_and_still_restricts_the_survivors():
    scenario = _board(
        ["Pyrophobia"], ("Grizzly Bears",), ["Craven Hulk", "Fire-Belly Changeling"], PYRO_LANDS
    )
    hulk = scenario.creature("Craven Hulk", "bob")
    survivor = scenario.creature("Fire-Belly Changeling", "bob")
    sources = scenario.untapped_sources(*PYRO_LANDS, username="alice")
    scenario.cast_and_resolve("Pyrophobia", *sources, username="alice", targets=[hulk])

    assert hulk.damage == 3
    assert _cant_block(scenario, survivor)


# -- Sparkmage's Gambit and Wrap in Flames: "Those creatures can't block" -------

GAMBIT_LANDS = ("Mountain", "Mountain")


def _gambit_board(spell="Sparkmage's Gambit", lands=GAMBIT_LANDS, bob=("Hill Giant", "Watchwolf")):
    return _board([spell], ("Grizzly Bears",), bob, lands)


def _cast(scenario, spell, lands, targets):
    sources = scenario.untapped_sources(*lands, username="alice")
    scenario.cast_and_resolve(spell, *sources, username="alice", targets=targets)


def test_sparkmages_gambit_damages_both_targets_and_neither_can_block():
    scenario = _gambit_board(bob=("Hill Giant", "Watchwolf", "Grizzly Bears"))
    giant = scenario.creature("Hill Giant", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast(scenario, "Sparkmage's Gambit", GAMBIT_LANDS, [giant, wolf])

    assert (giant.damage, wolf.damage) == (1, 1)
    assert _cant_block(scenario, giant) and _cant_block(scenario, wolf)
    assert not _cant_block(scenario, bears)
    assert _notices(scenario) == []
    with pytest.raises(ValueError, match=r"can't block"):
        _attack_and_try_to_block(scenario, "Grizzly Bears", giant)


def test_sparkmages_gambit_with_one_target_restricts_just_that_one():
    scenario = _gambit_board()
    giant = scenario.creature("Hill Giant", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    _cast(scenario, "Sparkmage's Gambit", GAMBIT_LANDS, [giant])

    assert _cant_block(scenario, giant)
    assert not _cant_block(scenario, wolf)


def test_sparkmages_gambit_with_no_targets_restricts_nobody():
    """ "Up to two" includes zero (CR 115.6)."""
    scenario = _gambit_board()
    giant = scenario.creature("Hill Giant", "bob")
    _cast(scenario, "Sparkmage's Gambit", GAMBIT_LANDS, [])

    assert not _cant_block(scenario, giant)
    assert giant.damage == 0


def test_sparkmages_gambit_a_target_that_left_is_not_restricted_but_the_other_is():
    """CR 608.2b: only the targets still legal are damaged and restricted."""
    scenario = _gambit_board()
    giant = scenario.creature("Hill Giant", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    sources = scenario.untapped_sources(*GAMBIT_LANDS, username="alice")
    scenario.cast_onto_stack(
        "Sparkmage's Gambit", *sources, username="alice", targets=[giant, wolf]
    )
    scenario.game.return_to_hand(giant)
    scenario.pass_until_resolved()

    assert wolf.damage == 1
    assert _cant_block(scenario, wolf)


def test_a_creature_that_dies_to_the_damage_is_simply_gone():
    scenario = _gambit_board(bob=("Memnite", "Watchwolf"))
    memnite = scenario.creature("Memnite", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    _cast(scenario, "Sparkmage's Gambit", GAMBIT_LANDS, [memnite, wolf])
    scenario.state_based_actions()

    assert memnite.zone is Zone.GRAVEYARD
    assert _cant_block(scenario, wolf)


def test_the_restriction_ends_at_end_of_turn_for_those_creatures():
    scenario = _gambit_board()
    giant = scenario.creature("Hill Giant", "bob")
    _cast(scenario, "Sparkmage's Gambit", GAMBIT_LANDS, [giant])
    scenario.game.continuous_effects.end_the_turn(scenario.game)

    assert not _cant_block(scenario, giant)


def test_wrap_in_flames_restricts_up_to_three_targets():
    lands = ("Mountain",) * 4
    scenario = _gambit_board(
        "Wrap in Flames", lands, ("Hill Giant", "Watchwolf", "Gray Ogre", "Memnite")
    )
    giant = scenario.creature("Hill Giant", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    ogre = scenario.creature("Gray Ogre", "bob")
    memnite = scenario.creature("Memnite", "bob")
    _cast(scenario, "Wrap in Flames", lands, [giant, wolf, ogre])

    assert all(_cant_block(scenario, creature) for creature in (giant, wolf, ogre))
    assert not _cant_block(scenario, memnite)
    assert _notices(scenario) == []


def test_rowans_minus_two_restricts_the_creatures_it_damaged():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Rowan, Fearless Sparkmage", "Grizzly Bears"])
        .player("bob", battlefield=["Hill Giant", "Watchwolf", "Gray Ogre"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rowan = scenario.find("Rowan, Fearless Sparkmage", Zone.BATTLEFIELD, "alice")
    giant = scenario.creature("Hill Giant", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    ogre = scenario.creature("Gray Ogre", "bob")
    scenario.activate(rowan, index=1, username="alice", targets=[giant, wolf])
    scenario.resolve_top()

    assert (giant.damage, wolf.damage) == (1, 1)
    assert _cant_block(scenario, giant) and _cant_block(scenario, wolf)
    assert not _cant_block(scenario, ogre)
    assert _notices(scenario) == []
