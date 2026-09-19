"""Scenario: a "target" that is a range rather than a number.

Most targeting text asks for exactly one of something. Three shapes do not, and
all three are in the card pool:

- **"one or two target creatures"** - Abzan Charm's third mode. A floor and a
  ceiling. It comes with a division (CR 601.2d), which is *why* the floor is one:
  "each of these targets must receive at least one of whatever is being divided".
- **"any number of target players' graveyards"** - Thraben Charm's third mode.
  CR 107.1c: "if a rule or ability instructs a player to choose 'any number,'
  that player may choose any positive number or zero." No ceiling at all, and
  the targets are the *players* - the graveyards are what the effect reaches
  into afterwards.
- **"up to X target cards from graveyards"** - Kozilek's Command's fourth mode,
  where the ceiling is not known until the caster announces X (CR 107.3a).

CR 115.6 is what makes a floor of nought legal: "a spell or ability that
requires targets may allow zero targets to be chosen. Such a spell or ability is
still said to require targets, but that spell or ability is targeted only if one
or more targets are chosen for it." That last clause decides the fizzling cases
at the bottom of this file, because CR 608.2b only counters a spell "if the
spell or ability specifies targets".

Neither charm has an entry in `machines/effects.py`, so nothing here asserts on
what a mode *does* - see `docs/engine-coverage.md`. What is asserted is what the
rules put at announcement and at resolution: which targets may be chosen, how
many, and whether the spell still resolves once some of them are gone.

Every CR number here was looked up with `knowledge_search(type="rules")`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    """Alice with both charms and the mana for either; Bob with two creatures."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Abzan Charm", "Thraben Charm", "Lightning Bolt"],
            library=["Forest"],
            battlefield=["Plains", "Swamp", "Forest", "Mountain", "Grizzly Bears"],
        )
        .player("bob", library=["Island"], battlefield=["Grizzly Bears", "Watchwolf"])
    )


def abzan_charm(scenario, targets):
    """Announce Abzan Charm's counter mode at `targets` and leave it on the stack.

    Modal, so the modes come first (CR 601.2b, CR 700.2c) and the harness's
    `targets=` shortcut cannot be used.
    """
    casting = scenario.cast("Abzan Charm", "alice")
    casting.choose_modes([3])
    casting.choose_targets(targets)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains", "Swamp", "Forest"))
    return scenario.put_on_stack(casting)


def thraben_charm(scenario, targets):
    """Announce Thraben Charm's graveyard mode at `targets`, unresolved."""
    casting = scenario.cast("Thraben Charm", "alice")
    casting.choose_modes([3])
    casting.choose_targets(targets)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains", "Swamp"))
    return scenario.put_on_stack(casting)


# --------------------------------------------------------------------------
# "one or two target creatures": a floor and a ceiling
# --------------------------------------------------------------------------


def test_one_target_is_enough_for_one_or_two():
    """The floor: "Distribute two +1/+1 counters among one or two target creatures"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    spell = abzan_charm(scenario, [bears])

    assert spell.zone is Zone.STACK
    assert [str(target) for target in spell.targets] == [str(bears.id)]


def test_two_targets_are_the_ceiling():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears, wolf = scenario.creature("Grizzly Bears", "bob"), scenario.creature("Watchwolf", "bob")

    spell = abzan_charm(scenario, [bears, wolf])

    assert len(spell.targets) == 2


def test_three_targets_are_one_too_many():
    """CR 601.2c refuses the announcement rather than trimming it."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.creatures("Grizzly Bears", "Watchwolf", username="bob")
    mine = scenario.creature("Grizzly Bears", "alice")

    casting = scenario.cast("Abzan Charm", "alice")
    casting.choose_modes([3])

    with pytest.raises(ValueError, match="too many targets"):
        casting.choose_targets([*theirs, mine])


def test_no_target_is_one_too_few():
    """ "One or two" is not "up to two": the floor is one (CR 115.6 by contrast)."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Abzan Charm", "alice")
    casting.choose_modes([3])

    with pytest.raises(ValueError, match="too few targets"):
        casting.choose_targets([])


def test_the_same_creature_cannot_take_both_counters():
    """CR 115.3: one instance of "target", so one choice of each object.

    CR 601.2d is the reason it matters here - both counters going on one
    creature would be a division of two among one target, which is a legal
    announcement only if one target was chosen.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Abzan Charm", "alice")
    casting.choose_modes([3])

    with pytest.raises(ValueError, match="twice"):
        casting.choose_targets([bears, bears])


def test_a_range_of_creatures_still_means_creatures():
    """A land is not a creature, however many targets the mode allows."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    casting = scenario.cast("Abzan Charm", "alice")
    casting.choose_modes([3])

    with pytest.raises(ValueError, match="illegal target"):
        casting.choose_targets([mountain])


# --------------------------------------------------------------------------
# "any number of target players' graveyards": no ceiling at all
# --------------------------------------------------------------------------


def test_any_number_may_be_two_players():
    """CR 107.1c, and the targets are the players, not their graveyards."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spell = thraben_charm(scenario, ["alice", "bob"])

    assert [str(target) for target in spell.targets] == ["alice", "bob"]
    assert all(target.is_player for target in spell.targets)


def test_any_number_may_be_none():
    """CR 107.1c: "any positive number or zero"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spell = thraben_charm(scenario, [])

    assert spell.targets == []


def test_any_number_may_include_the_caster():
    """The mode says "players", not "opponents", so alice may exile her own."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spell = thraben_charm(scenario, ["alice"])

    assert [str(target) for target in spell.targets] == ["alice"]


def test_a_creature_is_not_a_player_however_many_are_allowed():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Thraben Charm", "alice")
    casting.choose_modes([3])

    with pytest.raises(ValueError, match="illegal target"):
        casting.choose_targets([bears])


def test_the_same_player_cannot_be_chosen_twice():
    """CR 115.3 holds for an unbounded count too."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Thraben Charm", "alice")
    casting.choose_modes([3])

    with pytest.raises(ValueError, match="twice"):
        casting.choose_targets(["bob", "bob"])


# --------------------------------------------------------------------------
# What the range means on resolution (CR 608.2b)
# --------------------------------------------------------------------------


def test_a_spell_whose_only_target_has_gone_does_not_resolve():
    """CR 608.2b: "if all its targets ... are now illegal, the spell ... doesn't
    resolve"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    charm = abzan_charm(scenario, [bears])
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])
    assert bears.zone is Zone.GRAVEYARD

    scenario.pass_until_resolved()

    assert charm.id in scenario.game.fizzled


def test_one_illegal_target_out_of_two_does_not_counter_the_spell():
    """CR 608.2b again: it is *all* of them or none of them.

    Asserted while the charm is still on the stack, because a resolved spell has
    already dropped its targets on the way to the graveyard. This case holds
    whether or not the dead creature is judged illegal, which is the difference
    between it and the xfail above.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears, wolf = scenario.creature("Grizzly Bears", "bob"), scenario.creature("Watchwolf", "bob")

    charm = abzan_charm(scenario, [bears, wolf])
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])
    assert bears.zone is Zone.GRAVEYARD

    assert not scenario.game.spell_fizzles(charm)
    assert wolf in scenario.game.resolve_card_targets(charm)

    scenario.pass_until_resolved()

    assert charm.id not in scenario.game.fizzled


def test_a_spell_that_chose_no_targets_never_fizzles():
    """CR 115.6: it "is targeted only if one or more targets are chosen for it",
    and CR 608.2b only checks a spell that "specifies targets".

    Thraben Charm's graveyard mode with nobody chosen resolves whatever happens
    to anybody's graveyard.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    charm = thraben_charm(scenario, [])
    scenario.pass_until_resolved()

    assert charm.id not in scenario.game.fizzled
    assert charm.zone is Zone.GRAVEYARD


def test_a_player_who_is_still_here_is_still_a_legal_target():
    """The control for the two fizzles above: nothing changed, nothing is illegal."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    charm = thraben_charm(scenario, ["bob"])
    scenario.pass_until_resolved()

    assert charm.id not in scenario.game.fizzled


# --------------------------------------------------------------------------
# Damage "to up to one target" / "to each of up to two targets": CR 601.2d's
# division never applies here (the card never says "divided as you choose"),
# so this is CR 115.6's ordinary "up to N" ceiling and each target chosen
# takes the *whole* printed amount, not a share of it.
#
# - Mjolnir, Hammer of Thor (pool, verified with `resolve_cards`): "When
#   Mjolnir enters, it deals 4 damage to up to one target creature."
# - Dual Shot (off-pool, verified with `resolve_cards`): "Dual Shot deals 1
#   damage to each of up to two target creatures."
#
# CR 601.2d was looked up with `knowledge_search(type="rules")`: "If the
# spell requires the player to divide or distribute an effect ... among one
# or more targets" - neither card's text triggers this, so `deal_damage`'s
# ordinary per-target loop is the correct reading, not `deal_divided_damage`.
# --------------------------------------------------------------------------


def test_mjolnir_can_choose_zero_targets_and_deal_no_damage():
    """CR 115.6: "up to one" allows zero, and a trigger with no target still
    resolves cleanly rather than fizzling (CR 608.2b only counters/fizzles a
    spell or ability that specifies targets and has none left)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mjölnir, Hammer of Thor"], battlefield=["Mountain"] * 4)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Mjölnir, Hammer of Thor", [])

    sources = scenario.untapped_sources(*(["Mountain"] * 4), username="alice")
    scenario.cast_onto_stack("Mjölnir, Hammer of Thor", *sources, username="alice")
    scenario.pass_until_resolved()  # Mjolnir resolves and enters
    scenario.pass_until_resolved()  # its own ETB trigger, at no target

    assert bears.damage == 0
    assert bears.zone is Zone.BATTLEFIELD


def test_mjolnir_deals_its_whole_four_damage_to_the_one_target_chosen():
    """The single chosen target takes the full printed amount - not a share,
    since the card never says "divided"."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mjölnir, Hammer of Thor"], battlefield=["Mountain"] * 4)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Mjölnir, Hammer of Thor", [bears])

    sources = scenario.untapped_sources(*(["Mountain"] * 4), username="alice")
    scenario.cast_onto_stack("Mjölnir, Hammer of Thor", *sources, username="alice")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD  # 4 damage kills a 2/2


def test_dual_shot_deals_the_whole_amount_to_each_of_two_targets():
    """ "each of up to two target creatures" is not division: both targets
    take the full 1 damage, not a divided half each."""
    scenario = (
        Scenario()
        .player("alice", hand=["Dual Shot"], battlefield=["Mountain"])
        .player("bob", battlefield=["Memnite", "Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.creatures("Memnite", "Memnite", username="bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Dual Shot", mountain, username="alice", targets=[first, second])

    assert first.zone is Zone.GRAVEYARD
    assert second.zone is Zone.GRAVEYARD


def test_dual_shot_can_choose_only_one_of_its_up_to_two_targets():
    scenario = (
        Scenario()
        .player("alice", hand=["Dual Shot"], battlefield=["Mountain"])
        .player("bob", battlefield=["Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.creature("Memnite", "bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Dual Shot", mountain, username="alice", targets=[memnite])

    assert memnite.zone is Zone.GRAVEYARD
