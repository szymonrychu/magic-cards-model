"""Reading targeting restrictions off real oracle text (CR 115).

Every profile here is parsed from the printing in tests/fixtures/cards, so a
case only holds if the real card really says what the test claims it says.
"""

import pytest

from magic_cards_model.machines.targeting import (
    ANY_TARGET_TYPES,
    ControllerRestriction,
    profile_for_modes,
    profile_for_text,
    targeting_profile,
)
from magic_cards_model.models import Type, Zone
from magic_cards_model.models.game import Game
from magic_cards_model.models.player import Player
from tests.cards import card, card_state


def profile(name: str):
    return targeting_profile(card(name))


def test_any_target_is_creature_player_planeswalker_and_battle():
    """CR 115.4: "any target" is the damage template, not a free-for-all."""
    (requirement,) = profile("Lightning Bolt").requirements

    assert requirement.card_types == ANY_TARGET_TYPES
    assert requirement.allows_players


def test_target_creature_takes_a_creature_and_nothing_else():
    (requirement,) = profile("Swords to Plowshares").requirements

    assert requirement.card_types == frozenset({Type.CREATURE})
    assert not requirement.allows_players


def test_target_spell_looks_on_the_stack():
    (requirement,) = profile("Counterspell").requirements

    assert requirement.zones == frozenset({Zone.STACK})
    assert not requirement.allows_players


def test_target_player_or_planeswalker_takes_either():
    (requirement,) = profile("Lava Spike").requirements

    assert requirement.allows_players
    assert requirement.card_types == frozenset({Type.PLANESWALKER})


def test_a_card_in_a_graveyard_is_not_a_permanent():
    """Raise Dead reaches a zone that is not the battlefield (CR 115.2)."""
    (requirement,) = profile("Raise Dead").requirements

    assert requirement.zones == frozenset({Zone.GRAVEYARD})
    assert requirement.controller is ControllerRestriction.YOU


def test_a_controller_restriction_is_read_off_the_text():
    (requirement,) = profile("Craterous Stomp").requirements

    assert requirement.controller is ControllerRestriction.OPPONENT


def test_a_spell_with_two_targets_has_two_requirements():
    """Fumarole destroys "target creature and target land" - two of them."""
    creature, land = profile("Fumarole").requirements

    assert creature.card_types == frozenset({Type.CREATURE})
    assert land.card_types == frozenset({Type.LAND})
    assert profile("Fumarole").max_targets == 2


def test_a_qualifier_on_the_target_is_kept():
    """Swallow Whole exiles "target tapped creature"."""
    (requirement,) = profile("Swallow Whole").requirements

    assert requirement.must_be_tapped is True


def test_a_spell_with_no_targeting_text_takes_none():
    assert profile("Grizzly Bears").max_targets == 0
    assert profile("Cathartic Reunion").max_targets == 0


def test_a_target_in_a_triggered_ability_is_not_a_target_of_the_spell():
    """Questing Beast's planeswalker damage is a trigger, not part of casting."""
    assert profile("Questing Beast").requirements == ()


# -- checking a chosen set of targets --------------------------------------


def test_a_creature_only_spell_rejects_a_player():
    with pytest.raises(ValueError, match="cannot target the player"):
        profile("Swords to Plowshares").check(["bob"], caster="alice")


def test_a_player_only_spell_rejects_a_creature():
    bears = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="bob")

    with pytest.raises(ValueError, match="needs a planeswalker"):
        profile("Lava Spike").check([bears], caster="alice")


def test_a_creature_in_the_wrong_zone_is_an_illegal_target():
    """CR 115.2: only permanents unless the spell says otherwise."""
    in_hand = card_state("Grizzly Bears", Zone.HAND, controller="bob")

    with pytest.raises(ValueError, match="needs a target in the battlefield"):
        profile("Swords to Plowshares").check([in_hand], caster="alice")


def test_a_graveyard_spell_cannot_reach_the_battlefield():
    on_battlefield = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="alice")

    with pytest.raises(ValueError, match="needs a target in the graveyard"):
        profile("Raise Dead").check([on_battlefield], caster="alice")


def test_your_own_creature_is_not_a_creature_an_opponent_controls():
    mine = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="alice")

    with pytest.raises(ValueError, match="which alice controls"):
        profile("Craterous Stomp").check([mine], caster="alice")


def test_an_untapped_creature_cannot_be_a_tapped_target():
    untapped = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="alice")

    with pytest.raises(ValueError, match="needs a tapped permanent"):
        profile("Swallow Whole").check([untapped], caster="alice")


def test_too_many_targets_is_rejected():
    """CR 601.2c: one target per target the spell requires, not more."""
    first = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="bob")
    second = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="bob")

    with pytest.raises(ValueError, match="too many targets"):
        profile("Swords to Plowshares").check([first, second], caster="alice")


def test_two_targets_may_be_given_in_either_order():
    creature = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="bob")
    land = card_state("Mountain", Zone.BATTLEFIELD, controller="bob")

    profile("Fumarole").check([creature, land], caster="alice")
    profile("Fumarole").check([land, creature], caster="alice")


def test_two_creatures_cannot_fill_a_creature_and_a_land_slot():
    first = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="bob")
    second = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="bob")

    with pytest.raises(ValueError, match="illegal target"):
        profile("Fumarole").check([first, second], caster="alice")


def test_a_spell_with_no_targets_refuses_one():
    bears = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="bob")

    with pytest.raises(ValueError, match="too many targets"):
        profile("Memnite").check([bears], caster="alice")


def test_text_the_parser_cannot_read_is_not_checked():
    """Fail open: an unreadable restriction must not become a false rejection.

    "Nonblack" used to be this test's own example - `_negated_color` now
    reads it (see `tests/scenarios/test_excluded_color_adjectives.py`), so
    this needs an example that is still genuinely unread: a comparison
    attempted against something other than a plain number or X (CR 107.1a),
    which `_COMPARISON_CLAUSE` cannot finish reading and
    `_extract_comparison` returns `_COMPARISON_UNREADABLE` for.
    """
    from magic_cards_model.machines.targeting import _parse

    unreadable = _parse("Destroy target creature with power greater than its toughness.")

    assert not unreadable.understood
    unreadable.check(["bob"], caster="alice")  # no exception


# -- modal spells: the targets follow the modes (CR 700.2c) ----------------


def modes(name: str, chosen, x_value: int | None = None):
    return profile_for_modes(card(name), chosen, x_value)


def test_a_modal_card_has_no_card_wide_targeting_profile():
    """CR 700.2c: what it targets is not knowable until the modes are chosen."""
    assert not profile("Thraben Charm").understood
    assert not profile("Kozilek's Command").understood


def test_only_the_chosen_mode_contributes_its_target():
    """Abrade's two modes want different things (CR 700.2f, CR 115.8)."""
    (damage,) = modes("Abrade", [1]).requirements
    (destroy,) = modes("Abrade", [2]).requirements

    assert damage.card_types == frozenset({Type.CREATURE})
    assert destroy.card_types == frozenset({Type.ARTIFACT})


def test_the_modes_not_chosen_ask_for_nothing():
    """Thraben Charm's first mode targets a creature; nothing else is required."""
    chosen = modes("Thraben Charm", [1])

    assert chosen.max_targets == 1
    assert chosen.requirements[0].card_types == frozenset({Type.CREATURE})


def test_two_chosen_modes_want_one_target_each():
    """Kozilek's Command, choosing the scry mode and the exile mode."""
    player, creature = modes("Kozilek's Command", [2, 3]).requirements

    assert player.allows_players and not player.allows_cards
    assert creature.card_types == frozenset({Type.CREATURE})


def test_two_chosen_modes_of_different_kinds_reject_the_wrong_pairing():
    bears = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="bob")
    game = Game(
        players=[Player(username="alice"), Player(username="bob")],
        schema_version=Game.CURRENT_SCHEMA_VERSION,
    )
    game.battlefield.append(bears)
    # X has to reach Grizzly Bears' mana value (2): mode 3 is "Exile target
    # creature with mana value X or less", now actually enforced - and a
    # `game` has to be passed for `characteristics_of` to read it from
    # (CR 613.5), the same way "target attacking creature" already needs one.
    chosen = modes("Kozilek's Command", [2, 3], x_value=2)

    chosen.check([bears, "bob"], caster="alice", game=game)  # one creature, one player
    with pytest.raises(ValueError, match="illegal target"):
        chosen.check([bears, bears], caster="alice", game=game)


def test_a_mode_that_does_not_target_adds_no_requirement():
    """Cryptic Command's "Draw a card" mode takes no target at all."""
    assert modes("Cryptic Command", [4]).max_targets == 0

    (only,) = modes("Cryptic Command", [1, 4]).requirements

    assert only.zones == frozenset({Zone.STACK})  # counter target spell


def test_a_modes_illegal_target_is_rejected():
    """CR 700.2a: an illegal choice is refused as the spell is announced."""
    with pytest.raises(ValueError, match="cannot target the player"):
        modes("Kozilek's Command", [2, 3]).check(["bob", "bob"], caster="alice")


def test_x_inside_a_mode_leaves_the_count_open_until_it_is_announced():
    """Kozilek's Command's fourth mode exiles "up to X target cards".

    An unannounced X is not unreadable text (CR 107.3: X is "a placeholder for
    a number that needs to be determined"), so the phrase is read and only the
    *count* is left open - the kind of target is still known and still checked.
    CR 601.2b announces X one step before CR 601.2c announces the targets, so a
    real cast never sees this state.
    """
    profile = modes("Kozilek's Command", [3, 4])
    creature, cards = profile.requirements

    assert profile.understood
    assert cards.variable_count
    assert cards.unbounded and cards.minimum == 0
    assert profile.max_targets is None
    assert cards.zones == frozenset({Zone.GRAVEYARD})
    assert not creature.variable_count


def test_an_unannounced_x_still_checks_what_kind_of_target_it_is():
    """The loose count does not loosen CR 115.2: a graveyard card is not a permanent."""
    on_battlefield = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="bob")
    in_graveyard = card_state("Grizzly Bears", Zone.GRAVEYARD, controller="bob")

    with pytest.raises(ValueError, match="illegal target"):
        modes("Kozilek's Command", [4]).check([on_battlefield], caster="alice")
    modes("Kozilek's Command", [4]).check([in_graveyard], caster="alice")


def test_x_inside_a_mode_is_counted_once_the_caster_announces_it():
    """CR 107.3a: with X chosen, "up to X" is an ordinary optional count."""
    creature, cards = modes("Kozilek's Command", [3, 4], x_value=2).requirements

    assert creature.card_types == frozenset({Type.CREATURE})
    assert cards.count == 2
    assert cards.optional  # CR 115.6: "up to" may take fewer
    assert cards.zones == frozenset({Zone.GRAVEYARD})


def test_a_graveyard_mode_cannot_reach_the_battlefield():
    on_battlefield = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="bob")

    with pytest.raises(ValueError, match="needs a target in the graveyard"):
        modes("Kozilek's Command", [3, 4], x_value=2).check(
            [on_battlefield, on_battlefield], caster="alice"
        )


def test_a_mode_naming_players_graveyards_targets_the_players():
    """Thraben Charm's third mode exiles "any number of target players' graveyards".

    The players are the targets; their graveyards are what the effect then
    reaches into. CR 107.1c makes "any number" nought upwards, so the mode has
    no maximum and may legally be announced with no target at all (CR 115.6).
    """
    (requirement,) = modes("Thraben Charm", [3]).requirements

    assert requirement.allows_players and not requirement.allows_cards
    assert requirement.unbounded
    assert requirement.minimum == 0
    assert modes("Thraben Charm", [3]).max_targets is None


def test_any_number_of_targets_accepts_none_one_or_several():
    """CR 107.1c: "any positive number or zero"."""
    chosen = modes("Thraben Charm", [3])

    chosen.check([], caster="alice")
    chosen.check(["bob"], caster="alice")
    chosen.check(["bob", "carol", "dave"], caster="alice")


def test_any_number_of_target_players_still_refuses_a_creature():
    """Unbounded is not unchecked: a permanent is not a player."""
    bears = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="bob")

    with pytest.raises(ValueError, match="illegal target"):
        modes("Thraben Charm", [3]).check([bears], caster="alice")


def test_a_mode_asking_for_a_range_of_targets_reads_it_as_a_range():
    """Abzan Charm distributes counters "among one or two target creatures".

    A range is neither a fixed count nor an "up to": one target is required and
    two are allowed, which is what `minimum` and `count` say separately.
    """
    (requirement,) = modes("Abzan Charm", [3]).requirements

    assert (requirement.minimum, requirement.count) == (1, 2)
    assert not requirement.optional
    assert requirement.card_types == frozenset({Type.CREATURE})


def test_a_range_of_targets_refuses_none_and_refuses_three():
    """CR 601.2c: fewer than the range's floor, or more than its ceiling."""
    chosen = modes("Abzan Charm", [3])
    creatures = [card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="bob") for _ in range(3)]

    with pytest.raises(ValueError, match="too few targets"):
        chosen.check([], caster="alice")
    with pytest.raises(ValueError, match="too many targets"):
        chosen.check(creatures, caster="alice")
    chosen.check(creatures[:1], caster="alice")
    chosen.check(creatures[:2], caster="alice")


# -- dividing an effect among the targets (CR 601.2d) ----------------------


def test_a_card_that_divides_damage_says_what_it_divides():
    """Electrolyze "deals 2 damage divided as you choose among one or two targets"."""
    division = profile("Electrolyze").division

    assert division is not None
    assert (division.amount, division.what) == (2, "damage")


def test_a_card_that_distributes_counters_says_what_it_distributes():
    """Abzan Charm distributes "two +1/+1 counters" (CR 601.2d covers both)."""
    division = modes("Abzan Charm", [3]).division

    assert division is not None
    assert (division.amount, division.what) == (2, "+1/+1 counters")


def test_electrolyze_targets_are_cr_115_4_targets():
    """A bare "targets" with no noun is the damage template (CR 115.4)."""
    (requirement,) = profile("Electrolyze").requirements

    assert requirement.card_types == ANY_TARGET_TYPES
    assert requirement.allows_players
    assert (requirement.minimum, requirement.count) == (1, 2)


def test_a_division_must_give_every_target_at_least_one():
    """CR 601.2d: "each of these targets must receive at least one"."""
    electrolyze = profile("Electrolyze")

    electrolyze.check_division([1, 1], ["bob", "carol"])
    electrolyze.check_division([2], ["bob"])
    with pytest.raises(ValueError, match="at least one"):
        electrolyze.check_division([2, 0], ["bob", "carol"])


def test_a_division_must_use_the_whole_amount():
    """CR 107.1a rules out losing part of it: 2 damage is divided as 2."""
    with pytest.raises(ValueError, match="must use all 2 damage"):
        profile("Electrolyze").check_division([1], ["bob"])


def test_a_division_needs_one_share_per_target():
    with pytest.raises(ValueError, match="one share per target"):
        profile("Electrolyze").check_division([1, 1], ["bob"])


def test_a_spell_that_divides_nothing_has_no_division_to_announce():
    with pytest.raises(ValueError, match="divides nothing"):
        profile("Lightning Bolt").check_division([3], ["bob"])


def test_more_targets_than_there_is_to_divide_is_refused_at_announcement():
    """CR 601.2d again, from the targets' side rather than the division's.

    Two damage cannot reach three targets while each takes at least one, so the
    announcement is illegal before any division is proposed. Electrolyze's own
    "one or two" says the same thing, so this is asserted against a division of
    one - Abzan Charm's mode with a single counter would be the printed case.
    """
    from magic_cards_model.machines.targeting import _parse

    one_counter = _parse("Distribute one +1/+1 counter among one or two target creatures.")
    creatures = [card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="bob") for _ in range(2)]

    assert one_counter.division is not None and one_counter.division.amount == 1
    with pytest.raises(ValueError, match="each target must receive at least one"):
        one_counter.check(creatures, caster="alice")


# -- CR 115.3: the same target once per instance of "target" ---------------


def test_the_same_target_cannot_fill_one_requirement_twice():
    """CR 115.3: "the same target can't be chosen multiple times for any one
    instance of the word 'target'"."""
    bears = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="bob")

    with pytest.raises(ValueError, match="twice"):
        profile("Electrolyze").check([bears, bears], caster="alice")


def test_the_same_target_may_fill_two_different_requirements():
    """CR 115.3's second half: "the same object or player can be chosen once for
    each instance".

    Fumarole wants a creature and a land, and Dryad Arbor is both - so it can
    legally be chosen for each.
    """
    arbor = card_state("Dryad Arbor", Zone.BATTLEFIELD, controller="bob")

    profile("Fumarole").check([arbor, arbor], caster="alice")


# -- an ability on the stack as a target (CR 115.2, CR 113.1c) -------------


def test_target_activated_or_triggered_ability_is_read_off_the_ability_text():
    """Tishana's Tidebinder: "counter up to one target activated or triggered
    ability" (CR 113.9).

    The requirement lives in a triggered ability, so it is not part of the
    spell's own targeting - `profile_for_text` is the way in.
    """
    (requirement,) = profile_for_text(card("Tishana's Tidebinder").oracle_text).requirements

    assert requirement.allows_abilities
    assert not requirement.allows_cards and not requirement.allows_players
    assert requirement.zones == frozenset({Zone.STACK})
    assert (requirement.minimum, requirement.count) == (0, 1)


def test_the_spell_profile_of_a_card_does_not_see_its_ability_s_targets():
    """The Tidebinder is cast as a creature; nothing is targeted by casting it."""
    assert profile("Tishana's Tidebinder").requirements == ()


def test_deriving_modes_for_a_card_that_has_none_is_an_error():
    with pytest.raises(ValueError, match="not a modal card"):
        modes("Lightning Bolt", [1])


# -- the profile cache must not leak one game's Card into another ----------


def test_mutating_a_card_in_one_game_is_not_observed_through_another_games_profile():
    """`targeting._CACHE` memoises by oracle text (fast: text never changes),
    but `TargetingProfile.source_card` must be *this call's* `Card`, never
    whichever `Card` instance happened to populate the cache first.

    Before this fix the cache was keyed on `(card.name, text)` and stamped
    `source_card` into the cached entry itself, so the first game to ask for
    a "Lightning Bolt" profile handed its own `Card` to every later game that
    asked - and at the time `Card` was not frozen, so a caller mutating one
    game's `Card` (a copy effect, a Humility-style characteristic-defining
    rewrite) would have been visible through a second, unrelated game's
    cached profile.

    `Card` is `frozen=True` now (see `models/card.py`, and
    `test_card_immutability.py` for the guarantee itself), which forecloses
    that particular mutation - but the cache leak this guards against was
    about *object identity*, not mutability: two distinct `Card` objects with
    identical oracle text stand in for "the same printing, loaded
    independently by two different games' decks", and each game's profile
    must hold its own reference, never one shared with another game's.
    """
    first_game_card = card("Lightning Bolt")
    second_game_card = first_game_card.model_copy(deep=True)
    assert second_game_card is not first_game_card

    first_profile = targeting_profile(first_game_card)
    second_profile = targeting_profile(second_game_card)

    assert first_profile.source_card is first_game_card
    assert second_profile.source_card is second_game_card
    assert second_profile.source_card is not first_profile.source_card


def test_too_few_targets_is_rejected():
    """CR 601.2c: every target the spell requires needs a legal choice.

    The optional half of this (CR 115.6 "up to one target", which may legally
    be nothing) is implemented in `TargetingProfile.min_targets` but no card in
    the fixture pool has an optional target, so it is untested. Add a card with
    one and write that test rather than trusting the code path.
    """
    with pytest.raises(ValueError, match="too few targets"):
        profile("Swords to Plowshares").check([], caster="alice")


# --------------------------------------------------------------------------
# Into the Flood Maw: a conditional replacement clause is one target, not two
# (CR 601.2c, CR 702.174k, CR 702.174m). `tests/scenarios/test_gift_targeting.py`
# covers the full cast/resolve path; these are the parser-level claims that
# back it, verified directly against `TargetingProfile` with no `Game` at all.
# --------------------------------------------------------------------------


def test_into_the_flood_maw_reads_one_requirement_not_two():
    """CR 601.2c: "a spell may require alternative targets only if an
    alternative or additional cost ... was chosen for it" - so with no gift
    promised, Into the Flood Maw requires exactly the one target its first
    sentence names, not a second one for the gift-conditional replacement
    clause. This is the direct regression test for the reported defect: the
    engine used to read this as two requirements and refuse a legal
    single-target cast with "too few targets: 1 chosen where the spell
    requires 2".
    """
    the_profile = profile("Into the Flood Maw")

    assert the_profile.understood
    (requirement,) = the_profile.requirements
    assert requirement.phrase == "target creature"
    assert requirement.card_types == frozenset({Type.CREATURE})
    assert requirement.controller is ControllerRestriction.OPPONENT
    assert the_profile.min_targets == 1
    assert the_profile.max_targets == 1


def test_into_the_flood_maw_carries_the_promised_branch_as_data():
    """Trap: deleting the "If the gift was promised, instead ..." sentence
    instead of reading it would fix today's symptom and permanently hardcode
    the not-promised answer - so implementing gift later would silently keep
    bouncing only creatures. The requirement's `if_gift_promised` is the
    parsed alternate, kept rather than discarded, even though nothing calls
    `for_gift_promise(True)` from a real cast yet (gift is not wired up as a
    payable additional cost - see `docs/engine-coverage.md`).
    """
    (requirement,) = profile("Into the Flood Maw").requirements

    assert requirement.if_gift_promised is not None
    assert requirement.if_gift_promised.phrase == "target nonland permanent"


def test_into_the_flood_maw_promised_branch_targets_a_nonland_noncreature_permanent():
    """CR 702.174m's promised branch has its own, wider candidate set: "target
    nonland permanent an opponent controls" takes any nonland permanent - an
    artifact, an enchantment, a planeswalker - not only a creature. Wrong
    candidate set on this branch (accepting only what the not-promised branch
    already accepts) would silently narrow gift's whole point the day it is
    wired up.
    """
    promised = profile("Into the Flood Maw").for_gift_promise(True)

    (requirement,) = promised.requirements
    assert requirement.phrase == "target nonland permanent"
    assert requirement.card_types == frozenset()
    assert requirement.excluded_card_types == frozenset({Type.LAND})
    assert requirement.controller is ControllerRestriction.OPPONENT


def test_into_the_flood_maw_not_promised_is_the_default():
    """`for_gift_promise(False)` - and the profile `targeting_profile` hands
    back before anyone asks at all - is the not-promised branch: gift cannot
    currently be promised through a real cast (`machines/casting.py`'s
    `ADDITIONAL_COST_KEYWORDS` has no "gift" entry), so this is also the only
    branch a live game can ever actually reach today.
    """
    not_promised = profile("Into the Flood Maw").for_gift_promise(False)

    assert not_promised == profile("Into the Flood Maw")


@pytest.mark.parametrize(
    "name", ["Fumarole", "Prey Upon", "Jeskai Revelation", "Practiced Offense"]
)
def test_a_genuine_second_target_is_not_collapsed_by_the_gift_reading(name: str):
    """The trap the gift fix has to avoid: none of these four print "gift" at
    all, but each prints the word "target" twice for two real, independent
    requirements (CR 115.1), and each must keep demanding both - the
    gift-promised clause detector must never fire on an ordinary second
    "target" that just happens to share a sentence with the first.
    """
    the_profile = profile(name)

    assert the_profile.understood
    assert len(the_profile.requirements) == 2
    assert the_profile.min_targets == 2


# --------------------------------------------------------------------------
# A loyalty or activation cost's own number is not a target count (CR 118,
# CR 601.2b/602.2b) - `Game._activation_target_text` hands `profile_for_text`
# the ability's whole printed text, cost prefix included, so a "target"
# phrase that opens the very first sentence after the cost's colon used to
# have that colon's own preceding number read as its count instead of the
# default "exactly one" CR 115.1 gives an unmarked "target creature"/"target
# player". Liliana of the Veil's own "-2: Target player sacrifices a
# creature." is the reported case; Teferi, Master of Time's "-3: Target
# creature you don't control phases out." is the off-set proof - a
# different card, a different magnitude, and a different effect, sharing
# only the shape that exposed the bug.
# --------------------------------------------------------------------------


def test_a_loyalty_costs_own_number_is_not_read_as_a_target_count():
    """Liliana of the Veil's "-2:" used to leave `_read_count` reading the
    "2" off the cost as though the ability read "2 target players" -
    `TargetRequirement.count`/`minimum` came back 2 for a plainly singular
    "target player", and the too-few-targets check then refused a legal
    single-target activation outright."""
    the_profile = profile_for_text("−2: Target player sacrifices a creature.")

    (requirement,) = the_profile.requirements
    assert requirement.phrase == "target player"
    assert requirement.count == 1
    assert requirement.minimum == 1
    assert the_profile.min_targets == 1


def test_a_larger_loyalty_cost_is_not_read_as_a_target_count_either():
    """Teferi, Master of Time's own "-3:" - a different magnitude, a
    different card, and a different effect than Liliana's "-2:", to prove
    this is `_read_count`'s own general fix and not one pinned to "2"."""
    the_profile = profile_for_text("−3: Target creature you don't control phases out.")

    (requirement,) = the_profile.requirements
    assert requirement.phrase == "target creature"
    assert requirement.count == 1
    assert requirement.minimum == 1


def test_a_generic_mana_activation_costs_number_is_not_read_as_a_target_count():
    """The identical bug, off a `{N}:` mana cost rather than a loyalty one -
    both tokenize to a bare digit immediately before "target" once the cost's
    own colon is crossed, so both need the same fix."""
    the_profile = profile_for_text("{3}: Target creature gets -2/-2 until end of turn.")

    (requirement,) = the_profile.requirements
    assert requirement.count == 1
    assert requirement.minimum == 1
    assert all(requirement.if_gift_promised is None for requirement in the_profile.requirements)


# --------------------------------------------------------------------------
# "target X with mana value less than `<source>`'s loyalty" (Nahiri, the
# Unforgiving's 0 ability): a strict, self-referential comparison mixed with
# a "creature or `<closed-list subtype>` card" compound noun list.
# --------------------------------------------------------------------------


def _nahiri_zero_ability_text() -> str:
    """The exact text `scripts/sweep_pool.py`'s own `targeting_gaps` reads -
    `ability.effect` when parsing filled it (the cost-stripped line),
    `ability.text` otherwise."""
    from magic_cards_model.machines import parse_abilities

    for ability in parse_abilities(card("Nahiri, the Unforgiving")):
        text = getattr(ability, "effect", None) or ability.text
        if "Exile target creature" in text:
            return text
    raise AssertionError("Nahiri, the Unforgiving's 0 ability text was not found")


def test_nahiris_loyalty_comparison_is_understood():
    """Nahiri, the Unforgiving's 0 ability used to be `sweep_pool.py
    --targeting`'s one unreadable phrase in the whole pool:
    `_COMPARISON_CLAUSE` only read "... or equal to ..." comparisons, never a
    bare "less than", so "mana value less than Nahiri's loyalty" hit
    `_COMPARISON_UNREADABLE` and failed the whole phrase closed.
    """
    from magic_cards_model.machines.targeting import (
        ComparisonAttribute,
        ComparisonCount,
        ComparisonOperator,
    )

    the_profile = profile_for_text(_nahiri_zero_ability_text())

    assert the_profile.understood
    (requirement,) = the_profile.requirements
    assert requirement.comparison_attribute is ComparisonAttribute.MANA_VALUE
    assert requirement.comparison_operator is ComparisonOperator.LESS_THAN
    assert requirement.comparison_count is ComparisonCount.SOURCE_LOYALTY
    assert requirement.zones == frozenset({Zone.GRAVEYARD})
    assert requirement.card_types == frozenset({Type.CREATURE})


def test_nahiris_equipment_half_is_read_as_a_disjunction_not_a_merge():
    """ "creature or Equipment card": CR 115.1's target is satisfied by
    *either* half, and Equipment is an artifact subtype (CR 301.5), never a
    creature one - merging the two halves into one `card_types`/
    `required_subtypes` pair would wrongly demand every legal target
    (including a plain creature) also carry the "equipment" subtype, since
    `TargetRequirement._rejects_card`'s subtype check is an "any of these"
    gate applied *on top of* the type check, not instead of it. Only
    `TargetRequirement.alternatives` expresses the real disjunction.
    """
    the_profile = profile_for_text(_nahiri_zero_ability_text())

    (requirement,) = the_profile.requirements
    (alternative,) = requirement.alternatives
    assert alternative.card_types == frozenset({Type.ARTIFACT})
    assert alternative.required_subtypes == frozenset({"equipment"})
    assert alternative.zones == frozenset({Zone.GRAVEYARD})
    assert alternative.comparison_operator is requirement.comparison_operator
    assert alternative.comparison_count is requirement.comparison_count


def test_a_different_planeswalkers_own_loyalty_comparison_also_parses():
    """Proof this is a general reading of CR 201.5's self-reference and of
    CR 205.3g's closed artifact-type list, not a string match against
    "Nahiri" or "Equipment": a different name, a different closed-list
    subtype (Vehicle, not Equipment), and "greater than" instead of "less
    than" all still parse."""
    from magic_cards_model.machines.targeting import ComparisonCount, ComparisonOperator

    the_profile = profile_for_text(
        "0: Exile target creature or Vehicle card with mana value "
        "greater than Squee's loyalty from your graveyard."
    )

    assert the_profile.understood
    (requirement,) = the_profile.requirements
    assert requirement.comparison_operator is ComparisonOperator.GREATER_THAN
    assert requirement.comparison_count is ComparisonCount.SOURCE_LOYALTY
    assert requirement.card_types == frozenset({Type.CREATURE})
    (alternative,) = requirement.alternatives
    assert alternative.card_types == frozenset({Type.ARTIFACT})
    assert alternative.required_subtypes == frozenset({"vehicle"})
