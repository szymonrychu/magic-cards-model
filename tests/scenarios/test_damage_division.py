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

**The record is real now.** `Casting.announce_division` checks the announcement
against the profile and carries it onto the spell as `CardState.division` at the
CR 601.2c/d moment its targets are set; `machines/effects.py` reads it back at
resolution. A caster who announces nothing still gets the old even-split
fallback, which for Electrolyze's two damage is right either way - so the second
half of this file is Arc Lightning, whose three damage among two targets gives
the caster a choice that the fallback cannot imitate.

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
# A division the caster actually chooses (CR 601.2d)
# --------------------------------------------------------------------------
#
# Electrolyze's two damage among two targets can only ever be 1 and 1, so it
# cannot show whether the caster's announcement was recorded or whether the
# even-split fallback happened to agree. Arc Lightning ("Arc Lightning deals 3
# damage divided as you choose among one, two, or three targets", verified with
# `resolve_cards`) has three to divide, so 2/1 and 1/2 are different boards.


def arc_board() -> Scenario:
    """Alice with Arc Lightning and the mana for it; Bob with two creatures."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Arc Lightning"],
            battlefield=["Mountain", "Mountain", "Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Watchwolf"])
    )


def cast_arc_lightning(scenario, targets, division):
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="alice")
    scenario.cast_onto_stack(
        "Arc Lightning", *sources, username="alice", targets=targets, division=division
    )
    return scenario.pass_until_resolved()


def test_the_caster_chooses_how_the_damage_is_divided():
    """CR 601.2d: "the player announces the division", and it is *that* division
    that is paid out.

    Two damage on the 2/2 and one on the 3/3 - the announcement, not an even
    split, which for three among two would have been 2 and 1 in whichever order
    the targets were named. The 2/2 Grizzly Bears dies (CR 704.5g) and the 3/3
    Watchwolf lives with one marked.
    """
    scenario = arc_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    wolf = scenario.creature("Watchwolf", "bob")

    cast_arc_lightning(scenario, [bears, wolf], [2, 1])

    assert bears.zone is Zone.GRAVEYARD
    assert (wolf.damage, wolf.zone) == (1, Zone.BATTLEFIELD)


def test_the_same_two_targets_the_other_way_round_kill_neither():
    """The mirror of the case above, and the reason it proves anything.

    One on the 2/2 and two on the 3/3 is an equally legal CR 601.2d
    announcement over the same two targets, and both creatures live. An engine
    that ignored the announcement and split evenly could not produce both
    boards.
    """
    scenario = arc_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    wolf = scenario.creature("Watchwolf", "bob")

    cast_arc_lightning(scenario, [bears, wolf], [1, 2])

    assert (bears.damage, bears.zone) == (1, Zone.BATTLEFIELD)
    assert (wolf.damage, wolf.zone) == (2, Zone.BATTLEFIELD)


def test_a_share_of_none_is_not_a_legal_division():
    """CR 601.2d: "Each of these targets must receive at least one of whatever
    is being divided."

    Three damage across two targets as 3 and 0 is refused at announcement, not
    silently corrected. The refusal leaves nothing announced behind it: the
    casting is still mid-CR 601.2 with no division recorded, so a caster cannot
    reach resolution having half-said an illegal one.
    """
    scenario = arc_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    wolf = scenario.creature("Watchwolf", "bob")

    casting = scenario.cast("Arc Lightning", "alice", targets=[bears, wolf])
    with pytest.raises(ValueError, match="at least one"):
        casting.announce_division([3, 0])

    assert casting.division is None


def test_a_division_that_does_not_use_the_whole_amount_is_refused():
    """The other half of CR 601.2d's arithmetic: the division is *of* the whole
    amount, so 1 and 1 out of three damage is not a legal announcement either.
    """
    scenario = arc_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    wolf = scenario.creature("Watchwolf", "bob")

    with pytest.raises(ValueError, match="must use all 3 damage"):
        scenario.cast("Arc Lightning", "alice", targets=[bears, wolf], division=[1, 1])


def test_an_announced_division_survives_a_target_leaving():
    """CR 115.7f and CR 608.2b together: the division is locked in at
    announcement, so a target that has become illegal loses its own share and
    the rest is *not* re-divided onto what is left.

    Arc Lightning announces 2 on the Bears and 1 on the Watchwolf; the Bears is
    Bolted away in response, and the Watchwolf still takes only its own 1
    rather than inheriting the two that had nowhere to go.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Arc Lightning", "Lightning Bolt"],
            battlefield=["Mountain"] * 4,
        )
        .player("bob", battlefield=["Grizzly Bears", "Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    wolf = scenario.creature("Watchwolf", "bob")

    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="alice")
    scenario.cast_onto_stack(
        "Arc Lightning", *sources, username="alice", targets=[bears, wolf], division=[2, 1]
    )
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])
    assert bears.zone is Zone.GRAVEYARD

    scenario.pass_until_resolved()

    assert wolf.damage == 1, "the two that had nowhere to go went nowhere"
    assert wolf.zone is Zone.BATTLEFIELD


def test_all_three_among_three_targets_is_one_each():
    """ "one, two, or three targets" with three chosen leaves exactly one
    division (CR 601.2d), and a face may be one of them (CR 115.4).
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Arc Lightning"], battlefield=["Mountain"] * 3)
        .player("bob", battlefield=["Grizzly Bears", "Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    memnite = scenario.creature("Memnite", "bob")

    cast_arc_lightning(scenario, [bears, memnite, "bob"], [1, 1, 1])

    assert bears.damage == 1
    assert memnite.zone is Zone.GRAVEYARD, "a 1/1 dies to its share (CR 704.5g)"
    assert scenario.player("bob").life == 19


def test_one_target_is_enough_for_one_two_or_three():
    """ "one, two, or three targets" has a floor of *one*, not two.

    A word-list reader that only looked at the last three words of the
    prefix ("two, or three") used to drop "one" on the floor and read a
    minimum of two - Arc Lightning could not legally be cast at a single
    target even though CR 601.2d lists "one" first. All three damage lands
    on the lone target, exactly as an undivided 3-damage spell would.
    """
    scenario = arc_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    cast_arc_lightning(scenario, [bears], [3])

    assert bears.zone is Zone.GRAVEYARD


def inferno_titan_board() -> Scenario:
    """Alice with Inferno Titan and its six mana; Bob with one creature."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Inferno Titan"], battlefield=["Mountain"] * 6)
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_inferno_titans_etb_trigger_also_allows_a_single_target():
    """Inferno Titan (off-pool, verified with `resolve_cards`): "Whenever
    this creature enters or attacks, it deals 3 damage divided as you choose
    among one, two, or three targets." The identical "one, two, or three"
    shape as Arc Lightning, but off a *triggered ability* rather than a
    spell - proving the fix is the shared `targeting._read_count` reader,
    not something special-cased to Arc Lightning's own card.
    """
    scenario = inferno_titan_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Inferno Titan", [bears])

    sources = scenario.untapped_sources(*(["Mountain"] * 6), username="alice")
    scenario.cast_onto_stack("Inferno Titan", *sources, username="alice")
    scenario.pass_until_resolved()  # Inferno Titan resolves and enters
    scenario.pass_until_resolved()  # its own ETB trigger, at one target

    assert bears.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# "any number of targets" (CR 107.1c): the old regex only ever read a fixed
# list ("one or two", "one, two, or three") and was silent on this shape
# outright - Pyrotechnics, Rolling Thunder, and Ureni all print it.
# --------------------------------------------------------------------------


def test_pyrotechnics_divides_among_three_of_any_number_of_targets():
    """Pyrotechnics (off-pool, verified with `resolve_cards`): "deals 4
    damage divided as you choose among any number of targets." No printed
    ceiling at all (CR 107.1c), so three targets - more than any fixed-list
    card in the pool ever allows - is still a legal announcement.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Pyrotechnics"], battlefield=["Mountain"] * 5)
        .player("bob", battlefield=["Grizzly Bears", "Watchwolf", "Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears, wolf, memnite = (
        scenario.creature("Grizzly Bears", "bob"),
        scenario.creature("Watchwolf", "bob"),
        scenario.creature("Memnite", "bob"),
    )
    sources = scenario.untapped_sources(*(["Mountain"] * 5), username="alice")
    scenario.cast_onto_stack(
        "Pyrotechnics",
        *sources,
        username="alice",
        targets=[bears, wolf, memnite],
        division=[2, 1, 1],
    )
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD  # 2 damage kills the 2/2
    assert (wolf.damage, wolf.zone) == (1, Zone.BATTLEFIELD)
    assert memnite.zone is Zone.GRAVEYARD  # 1 damage kills the 1/1


def test_pyrotechnics_can_also_choose_zero_targets():
    """CR 107.1c: "any positive number or zero" - nothing to divide among
    nobody, and the spell still resolves without fizzling (CR 608.2b only
    fizzles a spell whose targets have all become illegal, not one that
    never had any)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Pyrotechnics"], battlefield=["Mountain"] * 5)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    sources = scenario.untapped_sources(*(["Mountain"] * 5), username="alice")
    spell = scenario.cast_onto_stack("Pyrotechnics", *sources, username="alice", targets=[])
    scenario.pass_until_resolved()

    assert bears.damage == 0
    assert spell.zone is Zone.GRAVEYARD


def ureni_board(*, opponent_battlefield: list[str]) -> Scenario:
    """Alice with Ureni and its {5}{G}{U}{R} - eight lands total, all of
    which also feed its own "number of lands you control" X; Bob with
    whatever creatures the test wants shot at."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Ureni, the Song Unending"],
            battlefield=["Forest"] * 6 + ["Island", "Mountain"],
        )
        .player("bob", battlefield=opponent_battlefield)
    )


def test_urenis_etb_divides_x_damage_among_any_number_of_opponents_creatures():
    """Ureni, the Song Unending (pool): "When Ureni enters, it deals X damage
    divided as you choose among any number of target creatures and/or
    planeswalkers your opponents control, where X is the number of lands you
    control." Both widenings at once - "any number of", a restricted target
    phrase rather than bare "targets", and X read off a "where X is" count
    expression rather than a fixed digit.
    """
    scenario = ureni_board(opponent_battlefield=["Grizzly Bears", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="bob")
    scenario.choose_trigger_targets("Ureni, the Song Unending", [first, second])

    sources = scenario.untapped_sources(
        *(["Forest"] * 6 + ["Island", "Mountain"]), username="alice"
    )
    scenario.cast_onto_stack("Ureni, the Song Unending", *sources, username="alice")
    scenario.pass_until_resolved()  # Ureni resolves and enters
    scenario.pass_until_resolved()  # its own ETB trigger: X = 8 lands, split 4/4

    assert first.zone is Zone.GRAVEYARD
    assert second.zone is Zone.GRAVEYARD
