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
