"""Three CR 614.12 "as this permanent enters, ask the board" conditions in
`machines/replacement.py` read the *computed* board (CR 613.5), not the
printed subtype/type of each permanent already there:

- `_controls_a_subtype` ("unless you control a Mountain", Arena of Glory);
- `_controls_other_lands` ("if you control two or more other lands", Hall of
  Storm Giants);
- `_copy_candidates` ("any creature on the battlefield", Clone) - the
  *selection* of what may be copied, as distinct from the copiable values
  actually copied (CR 707.2), which stay printed.

`tests/scenarios/test_conditional_enters_tapped.py` and `tests/scenarios/
test_replacement_effects.py` already cover the ordinary, printed-agrees-with-
computed cases for all three cards. This file is the disagreement: Blood
Moon (CR 305.7, a real card already fully modelled) turning a nonbasic land
into a computed-only Mountain, a hand-built layer-4 "becomes a land" effect
(the same `add_type`/`ContinuousEffects.add` pattern the rest of this defect
class uses, since no real already-implemented card turns a creature into a
land in this pool), and earthbend (CR 701.66a) turning a land into a
computed-only creature.

CR numbers verified this session: CR 613.5, CR 613.1d, CR 305.7, CR 701.66a,
CR 205.1b. CR 614.12/614.12a/614.1d are quoted from `test_conditional_
enters_tapped.py`, which verified them in the session that wrote that file;
CR 707.2 is quoted from `test_replacement_effects.py`'s own Clone coverage
the same way.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers import (
    ContinuousEffect,
    Layer,
    add_type,
    only_this_incarnation,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# `_controls_a_subtype` - "unless you control a Mountain" (Arena of Glory)
# --------------------------------------------------------------------------


def test_arena_of_glory_enters_untapped_off_a_blood_mooned_nonbasic_land():
    """Misty Rainforest prints no subtype at all ("Land"), but Blood Moon
    (CR 305.7) already made it a Mountain on the computed board by the time
    Arena of Glory checks "you control a Mountain" - the printed reading
    would still see no Mountain and tap it.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Arena of Glory"],
            battlefield=["Blood Moon", "Misty Rainforest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rainforest = scenario.find("Misty Rainforest", Zone.BATTLEFIELD, "alice")
    assert "Mountain" not in rainforest.subtypes, "the printed line carries no subtype at all"
    assert "Mountain" in scenario.game.characteristics_of(rainforest).subtypes, "CR 305.7"

    arena = scenario.play_land("Arena of Glory")

    assert not arena.tapped, "the computed board already has a Mountain"


def test_arena_of_glory_enters_tapped_with_no_blood_moon():
    """The inverse and the control: without Blood Moon, the same nonbasic
    land carries no Mountain subtype either way, and Arena of Glory taps
    exactly as `test_arena_of_glory_enters_tapped_with_no_mountain` already
    proves for an empty board.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Arena of Glory"], battlefield=["Misty Rainforest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    arena = scenario.play_land("Arena of Glory")

    assert arena.tapped


# --------------------------------------------------------------------------
# `_controls_other_lands` - "if you control two or more other lands" (Hall
# of Storm Giants)
# --------------------------------------------------------------------------


def _grizzly_bears_becomes_a_land(scenario, bears) -> None:
    """A real layer-4 continuous effect (CR 613.1d) adding the land type "in
    addition to its other types" (CR 205.1b) - the same shape Liquimetal
    Coating's own generic parser (`_BECOMES_TYPE_IN_ADDITION_RE`) would
    produce for "becomes a land", built directly since no real card grants
    that specific type to an arbitrary creature in this pool.
    """
    store = scenario.game.continuous_effects
    with scenario.game._id_allocator_scope():  # noqa: SLF001
        store.add(
            ContinuousEffect(
                description="test: Grizzly Bears becomes a land",
                layer=Layer.TYPE,
                timestamp=store.tick(),
                selector=only_this_incarnation(bears, bears.zone_change_stamp),
                modification=add_type(Type.LAND),
            )
        )


def test_hall_of_storm_giants_counts_a_creature_the_computed_board_made_a_land():
    """One real Island plus a creature a layer-4 effect already made a land
    is two lands on the computed board - "two or more other lands" holds,
    and Hall of Storm Giants enters tapped.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Hall of Storm Giants"], battlefield=["Island", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    assert Type.LAND not in bears.types, "the printed type line is Creature only"
    _grizzly_bears_becomes_a_land(scenario, bears)

    hall = scenario.play_land("Hall of Storm Giants")

    assert hall.tapped, "the computed board already has two other lands"


def test_hall_of_storm_giants_does_not_count_an_ordinary_creature():
    """The inverse: without the type-adding effect, the same creature is not
    a land by any reading, and one Island plus an ordinary Grizzly Bears is
    only one other land - Hall of Storm Giants enters untapped.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Hall of Storm Giants"], battlefield=["Island", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    hall = scenario.play_land("Hall of Storm Giants")

    assert not hall.tapped, "a plain creature is not a land"


# --------------------------------------------------------------------------
# `_copy_candidates` - "any creature on the battlefield" (Clone)
# --------------------------------------------------------------------------


def test_clone_can_select_an_animated_land_as_a_creature_to_copy():
    """The *selection* of a copy candidate is a computed-characteristics
    question (CR 613.5) even though the values Clone actually copies are the
    copiable ones (CR 707.2) - the earthbent Forest is the only creature on
    bob's battlefield, and Clone must find it there at all, even though the
    copy it produces is an ordinary, non-animated Forest (the animation is a
    continuous effect, not a copiable characteristic).
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Clone"])
        .player("bob", hand=["Badgermole Cub"], battlefield=["Forest", "Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest", "Forest", username="bob")
    target_forest = forests[2]
    scenario.choose_trigger_targets("Badgermole Cub", [target_forest])
    # Put onto the battlefield rather than cast: it is bob's creature and
    # this is alice's turn, and CR 302.1's sorcery-speed timing would
    # otherwise refuse the cast outright (see `test_earthbend.py`'s
    # identical note). The enters-the-battlefield trigger and its earthbend
    # are the real ones either way.
    cub = scenario.put_onto_battlefield("Badgermole Cub", "bob")
    scenario.pass_until_resolved()
    assert scenario.game.characteristics_of(target_forest).is_creature
    # Removed so the animated Forest is the *only* creature on the board -
    # Badgermole Cub itself is also a creature, which would otherwise leave
    # Clone's "you may" with two candidates and an ambiguous default choice.
    scenario.game.exile_permanent(cub)

    clone = scenario.put_onto_battlefield("Clone", "alice")

    # `CardState.name` reads the printing rather than the computed
    # characteristics the way `.power`/`.toughness` do (a known, separate gap
    # `test_a_clone_enters_as_a_copy_of_something_already_there` already notes
    # - `clone.name` stays "Clone" on the board even for a *successful* copy),
    # so the copy is asserted through `characteristics_of` instead.
    computed = scenario.game.characteristics_of(clone)
    assert computed.name == "Forest", (
        "Clone found the earthbent land as its only creature candidate"
    )
    assert Type.LAND in computed.types
    assert Type.CREATURE not in computed.types, (
        "CR 707.2: the copiable values are the plain Forest's - the animation "
        "is a continuous effect, not a copiable characteristic"
    )


def test_clone_does_not_select_an_unanimated_land():
    """The inverse: with nothing animated, bob's board has no creature at
    all, and Clone has no legal option to take - the same "empty board"
    outcome `test_a_clone_with_nothing_to_copy_enters_as_itself` already
    proves.
    """
    scenario = (
        Scenario().player("alice", hand=["Clone"]).player("bob", battlefield=["Forest"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    clone = scenario.put_onto_battlefield("Clone", "alice")

    assert (clone.power, clone.toughness) == (0, 0)
