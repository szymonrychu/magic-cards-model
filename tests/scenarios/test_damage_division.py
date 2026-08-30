"""Scenario: damage divided among more than one target (CR 601.2d).

"If the spell requires the player to divide or distribute an effect (such as
damage or counters) among one or more targets, the player announces the
division. Each of these targets must receive at least one of whatever is being
divided." The division is announced as part of casting, not on resolution, and
CR 115.7f keeps it fixed if the targets are ever changed.

Electrolyze is the card: "Electrolyze deals 2 damage divided as you choose among
one or two targets. Draw a card."

`machines/targeting.py` now reads the template: Electrolyze asks for one or two
CR 115.4 targets, and `TargetingProfile.division` says what is being divided, so
the spell can be announced at its targets like any other. `check_division`
enforces the rule that every target chosen receives at least one - and, from the
targets' side, that no more targets are chosen than there is to go round.

**What is still missing is the record.** Nothing on the casting or on the spell
holds the announced division, so `machines/effects.py` splits the amount as
evenly as it goes with the remainder on the first target - which for two damage
means all of it on one target, or one each on two, and is right by luck. A card
dividing three or more has choices this model cannot store. The xfail at the
bottom of this file is that gap.

Every CR number here was looked up with `knowledge_search(type="rules")`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.targeting import targeting_profile
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    """Alice with Electrolyze and the mana for it; Bob with two small creatures."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Electrolyze"],
            library=["Forest"],
            battlefield=["Island", "Island", "Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Memnite", "Watchwolf"])
    )


def electrolyze_onto_stack(scenario, targets):
    """Cast Electrolyze at `targets` and leave it on the stack (CR 601.2c)."""
    sources = scenario.untapped_sources("Island", "Island", "Mountain", username="alice")
    return scenario.cast_onto_stack("Electrolyze", *sources, username="alice", targets=targets)


def cast_electrolyze(scenario, targets):
    electrolyze_onto_stack(scenario, targets)
    return scenario.pass_until_resolved()


# --------------------------------------------------------------------------
# The division itself
# --------------------------------------------------------------------------


def test_one_target_takes_the_whole_two_damage():
    """ "one or two targets" - with one chosen, the division is the whole amount.

    A 3/3 Watchwolf survives it, so the two damage is still marked and can be
    read (CR 120.6: it "remains until the cleanup step").
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolf = scenario.creature("Watchwolf", "bob")

    cast_electrolyze(scenario, [wolf])

    assert wolf.damage == 2
    assert wolf.zone is Zone.BATTLEFIELD


def test_two_targets_take_one_each():
    """CR 601.2d: "Each of these targets must receive at least one".

    Two damage among two targets can only be 1 and 1, so this is the one
    division the rules leave no choice about - and the one this model gets right
    for the right reason.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    wolf = scenario.creature("Watchwolf", "bob")

    cast_electrolyze(scenario, [bears, wolf])

    assert (bears.damage, wolf.damage) == (1, 1)


def test_one_damage_is_not_lethal_to_a_two_two_and_is_to_a_one_one():
    """CR 704.5g decides what the division was worth.

    "If a creature has toughness greater than 0, it has damage marked on it, and
    the total damage marked on it is greater than or equal to its toughness,
    that creature has been dealt lethal damage and is destroyed." Memnite is a
    1/1 and dies to its half; the Bears survives with one damage marked.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    memnite = scenario.creature("Memnite", "bob")

    cast_electrolyze(scenario, [bears, memnite])

    assert memnite.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 1


def test_all_of_it_on_one_creature_kills_a_two_two():
    """The same two damage, undivided, is lethal to the same Bears (CR 704.5g)."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    cast_electrolyze(scenario, [bears])

    assert bears.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# The targets it is divided among
# --------------------------------------------------------------------------


def test_a_player_can_be_one_of_the_targets():
    """Electrolyze says "targets", not "target creatures" - a face counts.

    One damage to a creature and one to Bob, whose life goes to 19 (CR 119.2, 120.3a).
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    cast_electrolyze(scenario, [bears, "bob"])

    assert bears.damage == 1
    assert scenario.player("bob").life == 19


def test_both_halves_can_go_to_players():
    """Two targets, both faces, one damage each."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Electrolyze"],
            library=["Forest"],
            battlefield=["Island", "Island", "Mountain"],
        )
        .player("bob")
        .player("carol")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    cast_electrolyze(scenario, ["bob", "carol"])

    assert scenario.player("bob").life == 19
    assert scenario.player("carol").life == 19


def test_a_target_that_has_left_loses_its_share_and_nothing_is_re_divided():
    """CR 608.2b: an illegal target is skipped and the rest still happens.

    The division was announced when Electrolyze was cast, so the damage the dead
    creature would have taken is simply not dealt - it does not move onto the
    surviving target. Bob's Memnite is Bolted in response, and the Bears still
    takes only its own 1.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Electrolyze", "Lightning Bolt"],
            library=["Forest"],
            battlefield=["Island", "Island", "Mountain", "Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    memnite = scenario.creature("Memnite", "bob")

    electrolyze_onto_stack(scenario, [bears, memnite])
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[memnite])
    assert memnite.zone is Zone.GRAVEYARD

    scenario.pass_until_resolved()

    assert bears.damage == 1, "the other half went nowhere"
    assert bears.zone is Zone.BATTLEFIELD


# --------------------------------------------------------------------------
# The rest of the card
# --------------------------------------------------------------------------


def test_the_draw_happens_after_the_damage():
    """CR 608.2c: the effects happen "in the order written on the card".

    Electrolyze draws whether or not anything died, and the draw is the second
    sentence, so a scenario asserting on the hand asserts after the damage.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    cast_electrolyze(scenario, [bears])

    assert [card.name for card in scenario.player("alice").hand] == ["Forest"]


def test_a_countered_electrolyze_neither_damages_nor_draws():
    """CR 701.6: a countered spell never resolves, so neither sentence happens."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Electrolyze"],
            library=["Forest"],
            battlefield=["Island", "Island", "Mountain"],
        )
        .player("bob", hand=["Counterspell"], battlefield=["Island", "Island", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    electrolyze = electrolyze_onto_stack(scenario, [bears])
    scenario.pass_priority("alice")
    bobs_islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_and_resolve("Counterspell", *bobs_islands, username="bob", targets=[electrolyze])

    assert electrolyze.zone is Zone.GRAVEYARD
    assert bears.damage == 0
    assert scenario.player("alice").hand == []


# --------------------------------------------------------------------------
# Announcing it (CR 601.2c, CR 601.2d)
# --------------------------------------------------------------------------


def test_electrolyze_announces_its_targets_like_any_other_spell():
    """CR 601.2c: "the player announces their choice of an appropriate object or
    player for each target the spell requires".

    "One or two targets" is CR 115.4's damage wording, so the choice may be a
    creature or a face, and the spell reaches the stack carrying it.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    spell = electrolyze_onto_stack(scenario, [bears, "bob"])

    assert spell.zone is Zone.STACK
    assert [str(target) for target in spell.targets] == [str(bears.id), "bob"]


def test_a_third_target_is_one_too_many():
    """ "One or two" is a ceiling as well as a floor (CR 601.2c)."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears, wolf, memnite = (
        scenario.creature("Grizzly Bears", "bob"),
        scenario.creature("Watchwolf", "bob"),
        scenario.creature("Memnite", "bob"),
    )

    with pytest.raises(ValueError, match="too many targets"):
        scenario.cast("Electrolyze", "alice", targets=[bears, wolf, memnite])


def test_no_target_at_all_is_too_few():
    """ "One or two" has a floor of one, unlike "up to two" (CR 115.6)."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    with pytest.raises(ValueError, match="too few targets"):
        scenario.cast("Electrolyze", "alice", targets=[])


def test_the_same_creature_cannot_be_chosen_for_both_halves():
    """CR 115.3: "the same target can't be chosen multiple times for any one
    instance of the word 'target'".

    Which is also what makes CR 601.2d's "each of these targets must receive at
    least one" mean something - two shares have to go two places.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    with pytest.raises(ValueError, match="twice"):
        scenario.cast("Electrolyze", "alice", targets=[bears, bears])


def test_a_land_is_not_one_of_electrolyzes_targets():
    """CR 115.4 lists creature, player, planeswalker and battle - not land."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island", username="alice")

    with pytest.raises(ValueError, match="illegal target"):
        scenario.cast("Electrolyze", "alice", targets=[island])


def test_the_division_is_two_damage_and_each_target_takes_at_least_one():
    """CR 601.2d, checked against the real printing's own profile.

    The rule is announced-with-the-spell arithmetic: one share per target, none
    of them nought, adding to exactly what the card divides.
    """
    profile = targeting_profile(card("Electrolyze"))

    assert profile.division is not None
    assert (profile.division.amount, profile.division.what) == (2, "damage")
    profile.check_division([1, 1], ["bob", "carol"])
    profile.check_division([2], ["bob"])
    with pytest.raises(ValueError, match="at least one"):
        profile.check_division([2, 0], ["bob", "carol"])
    with pytest.raises(ValueError, match="must use all 2 damage"):
        profile.check_division([1], ["bob"])


# --------------------------------------------------------------------------
# Gaps
# --------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="the announced division has nowhere to live (CR 601.2d): "
    "machines/targeting.py can check a division but Casting and CardState hold no field "
    "for one, so machines/effects.py divides the amount as evenly as it goes",
)
def test_the_caster_chooses_how_the_damage_is_divided():
    """CR 601.2d, the half of it that is not modelled.

    "The player announces the division. Each of these targets must receive at
    least one of whatever is being divided." Two damage among two targets can
    only be 1 and 1, so the gap shows only when there is a choice - and there is
    nowhere to record one. This asks for 2 and 0, which CR 601.2d would refuse
    anyway; the point is that nothing was asked at all.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    memnite = scenario.creature("Memnite", "bob")

    cast_electrolyze(scenario, [bears, memnite])

    assert (bears.damage, memnite.zone) == (2, Zone.BATTLEFIELD)
