"""A conditional "enters tapped" line, with its condition actually evaluated.

**CR 614.1d** - "Continuous effects that read '[This permanent] enters . . .'
or '[Objects] enter [the battlefield] . . .' are replacement effects." That is
the bare wording every land in this file prints, and it is *not* CR 614.1c:
verified with `knowledge_search(q="...", type="rules")` in the session that
wrote this file, CR 614.1c covers the other three shapes only - "[This
permanent] enters with . . . ," "As [this permanent] enters . . . ," and "[This
permanent] enters as . . ." So Breeding Pool's "As this land enters, you may pay
2 life" is 614.1c and "This land enters tapped unless you control a Mountain" is
614.1d, and `machines/replacement.py` cited the wrong one of the two until this
change.

**CR 614.12** - "Some replacement effects modify how a permanent enters the
battlefield. (See rules 614.1c-d.) Such effects may come from the permanent
itself if they affect only that permanent" - which is why the condition is read
off the entering card while it is still on its way in.

The gap this file closes: the condition was *parsed* into
`ReplacementEffect.condition` and then ignored, so Arena of Glory entered
untapped on an empty board. A wrong board state, not a missing one.

The shocklands are exercised at the bottom on purpose. Their "If you don't, it
enters tapped" is a back-reference to a CR 614.12a choice rather than a
condition about the board, and it must keep meaning exactly that.

Every CR number here was verified with `knowledge_search(q="...", type="rules")`
in this session: CR 614.1c, CR 614.1d, CR 614.12, CR 614.12a.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# "unless you control a <land subtype>"
# --------------------------------------------------------------------------


def test_arena_of_glory_enters_tapped_with_no_mountain():
    """The measured defect, stated plainly: an empty board has no Mountain."""
    scenario = Scenario().player("alice", hand=["Arena of Glory"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    arena = scenario.play_land("Arena of Glory")

    assert arena.tapped


def test_arena_of_glory_enters_untapped_with_a_mountain():
    """The other branch of the same condition."""
    scenario = (
        Scenario()
        .player("alice", hand=["Arena of Glory"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    arena = scenario.play_land("Arena of Glory")

    assert not arena.tapped


def test_a_mountain_an_opponent_controls_is_not_yours():
    """ "unless **you** control a Mountain" - the subtype has to be on your side."""
    scenario = (
        Scenario()
        .player("alice", hand=["Arena of Glory"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    arena = scenario.play_land("Arena of Glory")

    assert arena.tapped


def test_a_dual_land_counts_for_its_subtype():
    """The condition is about a land *subtype* (CR 205.3i), not a card name.

    Steam Vents is a Land - Island Mountain, so it satisfies "you control a
    Mountain" without being one.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Arena of Glory"], battlefield=["Steam Vents"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    arena = scenario.play_land("Arena of Glory")

    assert not arena.tapped


def test_cori_mountain_monastery_reads_either_half_of_its_disjunction():
    """ "unless you control a Plains **or an Island**" - either one is enough."""
    with_island = (
        Scenario()
        .player("alice", hand=["Cori Mountain Monastery"], battlefield=["Island"])
        .player("bob")
        .build()
    )
    with_island.start_at(Step.PRECOMBAT_MAIN)
    assert not with_island.play_land("Cori Mountain Monastery").tapped

    with_neither = (
        Scenario()
        .player("alice", hand=["Cori Mountain Monastery"], battlefield=["Forest"])
        .player("bob")
        .build()
    )
    with_neither.start_at(Step.PRECOMBAT_MAIN)
    assert with_neither.play_land("Cori Mountain Monastery").tapped


# --------------------------------------------------------------------------
# Counting other lands, in both polarities
# --------------------------------------------------------------------------


def test_hall_of_storm_giants_taps_when_the_leading_if_holds():
    """ "If you control two or more other lands, this land enters tapped."

    The leading-"if" polarity: the condition holding is what *taps* it, the
    opposite of the "unless" lands above.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Hall of Storm Giants"], battlefield=["Island", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    hall = scenario.play_land("Hall of Storm Giants")

    assert hall.tapped


def test_hall_of_storm_giants_enters_untapped_off_one_other_land():
    scenario = (
        Scenario()
        .player("alice", hand=["Hall of Storm Giants"], battlefield=["Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    hall = scenario.play_land("Hall of Storm Giants")

    assert not hall.tapped


def test_darkslick_shores_is_untapped_early_and_tapped_late():
    """The fastland shape: "unless you control two or fewer other lands"."""
    early = (
        Scenario()
        .player("alice", hand=["Darkslick Shores"], battlefield=["Island", "Swamp"])
        .player("bob")
        .build()
    )
    early.start_at(Step.PRECOMBAT_MAIN)
    assert not early.play_land("Darkslick Shores").tapped

    late = (
        Scenario()
        .player("alice", hand=["Darkslick Shores"], battlefield=["Island", "Swamp", "Island"])
        .player("bob")
        .build()
    )
    late.start_at(Step.PRECOMBAT_MAIN)
    assert late.play_land("Darkslick Shores").tapped


def test_only_the_controllers_own_lands_are_counted():
    """ "you control ... other lands" - bob's three lands are not alice's."""
    scenario = (
        Scenario()
        .player("alice", hand=["Darkslick Shores"])
        .player("bob", battlefield=["Island", "Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    shores = scenario.play_land("Darkslick Shores")

    assert not shores.tapped


# --------------------------------------------------------------------------
# A condition about a life total
# --------------------------------------------------------------------------


def test_lakeside_shack_enters_tapped_when_everybody_is_healthy():
    """ "unless **a player** has 13 or less life" - any player at the table."""
    scenario = (
        Scenario().player("alice", life=14, hand=["Lakeside Shack"]).player("bob", life=20).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    shack = scenario.play_land("Lakeside Shack")

    assert shack.tapped


def test_lakeside_shack_enters_untapped_off_an_opponents_low_life():
    """The condition names "a player", not "you", so bob's 12 is enough."""
    scenario = (
        Scenario().player("alice", life=20, hand=["Lakeside Shack"]).player("bob", life=12).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    shack = scenario.play_land("Lakeside Shack")

    assert not shack.tapped


# --------------------------------------------------------------------------
# The shocklands must not be swept into any of this (regression guard)
# --------------------------------------------------------------------------


def test_a_shockland_paying_the_life_still_enters_untapped():
    """ "If you don't, it enters tapped" is CR 614.12a's choice, not a board
    condition, and the board-condition reader must not claim it."""
    scenario = Scenario().player("alice", hand=["Steam Vents"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_pay_the_life(True)

    vents = scenario.play_land("Steam Vents")

    assert not vents.tapped
    assert scenario.player("alice").life == 18


def test_a_shockland_declining_the_life_still_enters_tapped():
    scenario = Scenario().player("alice", hand=["Steam Vents"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_pay_the_life(False)

    vents = scenario.play_land("Steam Vents")

    assert vents.tapped
    assert scenario.player("alice").life == 20


def test_an_unconditional_tapland_is_untouched():
    """No condition at all, so nothing here changes it."""
    scenario = Scenario().player("alice", hand=["Dakmor Salvage"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    salvage = scenario.play_land("Dakmor Salvage")

    assert salvage.tapped


# --------------------------------------------------------------------------
# "unless you control <N> or more other <land subtype>s"
# --------------------------------------------------------------------------
#
# The same count reader as "two or more other lands", with a land subtype for
# the noun (CR 205.3i: Mountain and Plains are land types). A permanent's
# computed subtypes decide it, so a nonbasic Mountain counts. "Plains" is its
# own plural.


def _subtype_land_board(land: str, battlefield=(), bob_battlefield=()):
    scenario = (
        Scenario()
        .player("alice", hand=[land], battlefield=list(battlefield))
        .player("bob", battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_dwarven_mine_enters_untapped_with_three_other_mountains():
    scenario = _subtype_land_board("Dwarven Mine", ["Mountain"] * 3)

    assert not scenario.play_land("Dwarven Mine").tapped


def test_dwarven_mine_enters_tapped_with_two_other_mountains():
    scenario = _subtype_land_board("Dwarven Mine", ["Mountain"] * 2)

    assert scenario.play_land("Dwarven Mine").tapped


def test_idyllic_grange_counts_plains_whose_plural_is_plains():
    untapped = _subtype_land_board("Idyllic Grange", ["Plains"] * 3)
    tapped = _subtype_land_board("Idyllic Grange", ["Plains"] * 2)

    assert not untapped.play_land("Idyllic Grange").tapped
    assert tapped.play_land("Idyllic Grange").tapped


def test_a_nonbasic_mountain_counts_toward_dwarven_mine():
    """CR 205.3i: Sacred Foundry is a Mountain; "basic" is not asked."""
    scenario = _subtype_land_board("Dwarven Mine", ["Mountain", "Mountain", "Sacred Foundry"])

    assert not scenario.play_land("Dwarven Mine").tapped


def test_the_wrong_subtype_does_not_count():
    scenario = _subtype_land_board("Dwarven Mine", ["Plains"] * 3)

    assert scenario.play_land("Dwarven Mine").tapped


def test_an_opponents_mountains_do_not_count_toward_dwarven_mine():
    scenario = _subtype_land_board("Dwarven Mine", ["Mountain"], bob_battlefield=["Mountain"] * 3)

    assert scenario.play_land("Dwarven Mine").tapped


# --------------------------------------------------------------------------
# "if it's not your turn" / "unless it's your turn" (CR 614.1d, CR 102.1)
# --------------------------------------------------------------------------
#
# Eddymurk Crab's own trailing "if <condition>" (no comma, no "unless") is a
# third `_ENTERS_TAPPED` polarity alongside the leading "If <cond>," and
# trailing "unless <cond>" forms above: it taps when the condition *holds*,
# the identical polarity the leading form already has. Horned Loch-Whale
# prints the same fact the other way round, "unless it's your turn" -
# `_ENTERS_TAPPED`'s pre-existing trailing-"unless" branch, negated the same
# way every other "unless" condition in this file already is.


def _next_turn(scenario) -> None:
    """Run the rest of this turn out and begin the next one's precombat
    main phase - `test_activation_timing_instructions.py`'s own "next turn's
    upkeep" helper, carried one step further so a land can still be played
    (CR 305.1) once there."""
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # the new turn's untap step
    scenario.start_at(Step.PRECOMBAT_MAIN)


def test_eddymurk_crab_enters_tapped_on_an_opponents_turn():
    """Eddymurk Crab: "This creature enters tapped if it's not your turn."
    Its own printed Flash is what makes casting it on bob's turn legal at
    all (CR 702.8a)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Eddymurk Crab"], battlefield=["Island"] * 7)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _next_turn(scenario)  # bob's turn is now active
    scenario.pass_priority()  # bob passes; alice may act with Flash (CR 702.8a)

    crab = scenario.cast_and_resolve("Eddymurk Crab", username="alice", auto=True)

    assert crab.tapped


def test_eddymurk_crab_enters_untapped_on_its_casters_own_turn():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Eddymurk Crab"], battlefield=["Island"] * 7)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    crab = scenario.cast_and_resolve("Eddymurk Crab", auto=True)

    assert not crab.tapped


def test_horned_loch_whale_enters_tapped_on_an_opponents_turn():
    """The same fact, the other printed polarity: "This creature enters
    tapped unless it's your turn." """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Horned Loch-Whale"], battlefield=["Island"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _next_turn(scenario)
    scenario.pass_priority()  # bob passes; alice may act with Flash (CR 702.8a)

    whale = scenario.cast_and_resolve("Horned Loch-Whale", username="alice", auto=True)

    assert whale.tapped


def test_horned_loch_whale_enters_untapped_on_its_casters_own_turn():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Horned Loch-Whale"], battlefield=["Island"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    whale = scenario.cast_and_resolve("Horned Loch-Whale", auto=True)

    assert not whale.tapped


# --------------------------------------------------------------------------
# "unless it's your first, second, or third turn of the game" (CR 500.7)
# --------------------------------------------------------------------------
#
# Starting Town counts its own controller's turns (`TurnMachine.turns_taken_
# by`/`own_turns_taken`), not the game's absolute turn number - so alice's
# fourth own turn is the game's seventh (three of hers, three of bob's,
# alternating), not its fourth.


def _played_on_alices_nth_own_turn(n: int):
    """A fresh two-player game, played manually to alice's `n`th own turn
    (1-indexed), with Starting Town still in her hand to play there."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Starting Town"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for _ in range(n - 1):
        _next_turn(scenario)  # bob's turn
        _next_turn(scenario)  # alice's next own turn
    return scenario


def test_starting_town_enters_untapped_on_the_first_turn_of_the_game():
    scenario = _played_on_alices_nth_own_turn(1)

    assert not scenario.play_land("Starting Town").tapped


def test_starting_town_enters_untapped_on_the_third_turn():
    scenario = _played_on_alices_nth_own_turn(3)

    assert not scenario.play_land("Starting Town").tapped


def test_starting_town_enters_tapped_on_the_fourth_turn():
    scenario = _played_on_alices_nth_own_turn(4)

    assert scenario.play_land("Starting Town").tapped


def test_starting_town_counts_the_controllers_own_turns_not_the_opponents():
    """Five turns into the game (alice, bob, alice, bob, bob's second) is
    alice's own *second* turn, not her fifth - `own_turns_taken` is per
    player, and this is what `_your_turn_ordinal_or_earlier` reads."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Starting Town"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _next_turn(scenario)  # bob's first
    _next_turn(scenario)  # alice's second
    _next_turn(scenario)  # bob's second

    assert scenario.game.turn.own_turns_taken("alice") == 2
