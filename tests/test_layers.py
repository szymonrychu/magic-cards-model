"""The layer system against real cards (CR 613).

Every card here is a real Scryfall printing out of `tests/fixtures/cards`. What
each one *does* comes from `LAYER_EFFECTS` in `machines/layers.py`, a scripted
registry keyed by card name - nothing parses static abilities yet - but the
names, types, mana values and printed power/toughness the engine reasons over
are the real ones.

The interesting tests are the ones where two effects fight, because that is the
only thing the layer system is for. Each names the rule it is checking; every CR
number in this file was looked up with `knowledge_search`.
"""

import pytest

from magic_cards_model.machines.layers import (
    ContinuousEffect,
    ContinuousEffects,
    Duration,
    Layer,
    LayerContext,
    Sublayer,
    compute_board,
    effects_for,
    every_creature,
    lose_all_abilities,
    modify_power_toughness,
    printed_characteristics,
    static_effects,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Supertype, Type
from tests.cards import card_state


def permanent(name: str, controller: str = "alice"):
    """One real printing on the battlefield, under someone's control."""
    return card_state(name, zone=Zone.BATTLEFIELD, controller=controller)


# --------------------------------------------------------------------------
# The starting point
# --------------------------------------------------------------------------


def test_a_permanent_with_no_effects_keeps_its_printed_characteristics():
    """With nothing to apply, layers 1-7 are the identity (CR 613.1a-613.1g)."""
    bears = permanent("Grizzly Bears")

    board = compute_board([bears])

    assert board.of(bears).power_toughness == (2, 2)
    assert Type.CREATURE in board.of(bears).types
    assert board.of(bears).subtypes == ("Bear",)
    assert board.journal.applied == []


def test_computing_the_board_does_not_touch_the_card_state():
    """CR 613.5: the game recomputes; it does not write the answer down.

    The engine is pure so there is no cached power to go stale. Asking twice
    with different effects gives different answers off the same `CardState`.
    """
    bears = permanent("Grizzly Bears")
    anthem = permanent("Glorious Anthem")

    plain = compute_board([bears])
    pumped = compute_board([bears, anthem], static_effects([bears, anthem]))

    assert plain.of(bears).power_toughness == (2, 2)
    assert pumped.of(bears).power_toughness == (3, 3)
    assert bears.card.power == "2"
    assert printed_characteristics(bears).power_toughness == (2, 2)


# --------------------------------------------------------------------------
# Layer 4: type-changing
# --------------------------------------------------------------------------


def test_blood_moon_makes_a_nonbasic_land_a_mountain_and_strips_its_abilities():
    """CR 613.1d plus CR 305.7.

    Layer 4 sets the land's subtype to a basic land type, and CR 305.7 says
    that when that happens "the land no longer has its old land type. It loses
    all abilities generated from its rules text, its old land types, and any
    copy effects". So Tinder Farm's own two mana abilities go away and it taps
    for red instead.
    """
    blood_moon = permanent("Blood Moon")
    farm = permanent("Tinder Farm")

    board = compute_board([farm, blood_moon], static_effects([farm, blood_moon]))
    moon_farm = board.of(farm)

    assert moon_farm.subtypes == ("Mountain",)
    assert moon_farm.abilities == ("{T}: Add {R}.",)
    assert not moon_farm.has_ability("{T}: Add {G}.")
    assert moon_farm.is_land


def test_blood_moon_leaves_basic_lands_alone():
    """ "Nonbasic" is the supertype, not the land type (CR 205.4c, CR 305.8)."""
    blood_moon = permanent("Blood Moon")
    forest = permanent("Forest")

    board = compute_board([forest, blood_moon], static_effects([forest, blood_moon]))

    assert Supertype.BASIC in board.of(forest).supertypes
    assert board.of(forest).subtypes == ("Forest",)


def test_urborg_adds_swamp_without_removing_the_other_land_types():
    """CR 205.1b: "in addition to" keeps every prior type."""
    urborg = permanent("Urborg, Tomb of Yawgmoth")
    mountain = permanent("Mountain")

    board = compute_board([mountain, urborg], static_effects([mountain, urborg]))

    assert board.of(mountain).subtypes == ("Mountain", "Swamp")
    assert board.of(mountain).has_ability("{T}: Add {B}.")


# --------------------------------------------------------------------------
# Layer 7: sublayer order
# --------------------------------------------------------------------------


def test_a_lord_and_counters_both_land_in_7c():
    """CR 613.4c: "Effects **and counters** that modify power and/or toughness".

    Folklore splits these into 7c for effects and 7d for counters. The current
    rules do not - 613.4c names both, 613.4d is the switch, and there is no
    613.4e. It makes no difference to the arithmetic here, which is why the
    split survived so long: 7c is addition and addition commutes.
    """
    bears = permanent("Grizzly Bears")
    anthem = permanent("Glorious Anthem")

    board = compute_board(
        [bears, anthem],
        static_effects([bears, anthem]),
        counters={bears.id: {"+1/+1": 2}},
    )

    assert board.of(bears).power_toughness == (5, 5)
    assert board.of(bears).counters == {"+1/+1": 2}


def test_minus_counters_come_off_in_the_same_sublayer():
    """CR 613.4c again: -1/-1 counters modify without setting."""
    beast = permanent("Questing Beast")

    board = compute_board([beast], counters={beast.id: {"-1/-1": 3}})

    assert board.of(beast).power_toughness == (1, 1)


def test_setting_power_beats_a_pump_with_an_earlier_timestamp():
    """CR 613.4b before CR 613.4c, whatever the timestamps say.

    Giant Growth resolves first (+3/+3, 7c, timestamp 1), then Humility hits
    the battlefield (base 1/1, 7b, timestamp 2). Timestamp order alone would
    say "2/2, then 5/5, then set to 1/1". The sublayers say otherwise: 7b runs
    first and sets the base to 1/1, and only then does the older 7c effect add
    its +3/+3.
    """
    bears = permanent("Grizzly Bears")
    growth = card_state("Giant Growth", zone=Zone.STACK, controller="alice")
    humility = permanent("Humility")

    effects = effects_for(growth, timestamp=1, targets=[bears])
    effects += effects_for(humility, timestamp=2)

    board = compute_board([bears, humility], effects)

    assert board.of(bears).power_toughness == (4, 4)


def test_switching_power_and_toughness_happens_after_the_pump():
    """CR 613.4d: the switch takes the values as they stand after 7a-7c.

    Ragavan is a printed 2/1. Glorious Anthem's 7c makes it a 3/2, and only
    then does Twisted Image's 7d swap the two, giving a 2/3 - not the 1/2 you
    would get by switching first and pumping afterwards.
    """
    ragavan = permanent("Ragavan, Nimble Pilferer")
    anthem = permanent("Glorious Anthem")
    image = card_state("Twisted Image", zone=Zone.STACK, controller="alice")

    effects = static_effects([ragavan, anthem])
    effects += effects_for(image, timestamp=3, targets=[ragavan])

    board = compute_board([ragavan, anthem], effects)

    assert board.of(ragavan).power_toughness == (2, 3)


def test_a_switch_with_an_earlier_timestamp_still_applies_last():
    """CR 613.4: sublayer order is not timestamp order.

    Same board, but Twisted Image resolved before Glorious Anthem entered. 7d
    is still after 7c, so the answer does not move.
    """
    ragavan = permanent("Ragavan, Nimble Pilferer")
    anthem = permanent("Glorious Anthem")
    image = card_state("Twisted Image", zone=Zone.STACK, controller="alice")

    effects = effects_for(image, timestamp=1, targets=[ragavan])
    effects += effects_for(anthem, timestamp=2)

    board = compute_board([ragavan, anthem], effects)

    assert board.of(ragavan).power_toughness == (2, 3)


# --------------------------------------------------------------------------
# Timestamp order
# --------------------------------------------------------------------------


def test_within_a_sublayer_the_oldest_effect_applies_first():
    """CR 613.7: an earlier timestamp applies before a later one."""
    bears = permanent("Grizzly Bears")
    first = ContinuousEffect(
        description="first",
        layer=Layer.POWER_TOUGHNESS,
        sublayer=Sublayer.SET,
        timestamp=1,
        selector=lambda chars, board: chars.is_creature,
        modification=lambda chars, board: chars.with_(power=7, toughness=7),
    )
    second = ContinuousEffect(
        description="second",
        layer=Layer.POWER_TOUGHNESS,
        sublayer=Sublayer.SET,
        timestamp=2,
        selector=lambda chars, board: chars.is_creature,
        modification=lambda chars, board: chars.with_(power=3, toughness=3),
    )

    board = compute_board([bears], [second, first])

    assert board.journal.applied == ["first", "second"]
    assert board.of(bears).power_toughness == (3, 3)


# --------------------------------------------------------------------------
# Humility and Opalescence
# --------------------------------------------------------------------------


def humility_and_opalescence(humility_first: bool):
    """The famous board, with the two enchantments in a chosen timestamp order.

    CR 613.7a: a static ability's effect has the timestamp of the permanent it
    is on, so "which entered first" is the whole question.
    """
    humility = permanent("Humility")
    opalescence = permanent("Opalescence")
    bears = permanent("Grizzly Bears")

    order = [humility, opalescence] if humility_first else [opalescence, humility]
    effects = static_effects(order)
    return humility, opalescence, bears, compute_board([humility, opalescence, bears], effects)


def test_humility_before_opalescence_leaves_humility_a_4_4():
    """The classic answer, and every step of it is forced by CR 613.

    Layer 4 (CR 613.1d): Opalescence makes each *other* non-Aura enchantment a
    creature, so Humility becomes one and Opalescence does not.

    Layer 6 (CR 613.1f): Humility removes all abilities from all creatures -
    itself included, since layer 4 already made it a creature. Opalescence is
    not a creature, so it keeps its ability. Humility's own effect has now
    started applying, so CR 613.6 keeps the rest of it alive: "if an effect
    starts to apply in one layer and/or sublayer, it will continue to apply".

    Sublayer 7b (CR 613.4b), in timestamp order (CR 613.7): Humility sets every
    creature's base P/T to 1/1, then Opalescence - later - overwrites the
    enchantments' P/T with their mana value. Humility costs {2}{W}{W}, so it
    ends up a 4/4 while the Bears stay a 1/1.
    """
    humility, opalescence, bears, board = humility_and_opalescence(humility_first=True)

    assert board.of(humility).is_creature
    assert board.of(humility).power_toughness == (4, 4)
    assert board.of(humility).abilities == ()
    assert board.of(bears).power_toughness == (1, 1)
    assert not board.of(opalescence).is_creature
    assert board.of(opalescence).abilities != ()


def test_opalescence_before_humility_makes_everything_a_1_1():
    """Swap the timestamps and the answer flips (CR 613.7).

    Layers 4 and 6 play out identically - Humility is still a creature, still
    strips every creature's abilities including its own. Only 7b changes:
    Opalescence is now the older effect, so it sets Humility to 4/4 first and
    Humility's base 1/1 lands on top of it afterwards.
    """
    humility, opalescence, bears, board = humility_and_opalescence(humility_first=False)

    assert board.of(humility).power_toughness == (1, 1)
    assert board.of(bears).power_toughness == (1, 1)
    assert board.of(humility).abilities == ()


def test_humility_keeps_setting_power_after_removing_its_own_ability():
    """CR 613.6, which is the only reason the pair has an answer at all.

    Humility's layer 6 effect removes Humility's own ability, because
    Opalescence made Humility a creature back in layer 4. If that killed the
    rest of the ability, the 7b half would never apply and the board would
    depend on which half you looked at first. CR 613.6 says an effect that has
    started applying keeps applying, so both halves run and nothing is skipped.
    """
    humility, opalescence, bears, board = humility_and_opalescence(humility_first=True)

    assert board.journal.skipped == []
    assert "Humility: creatures have base P/T 1/1" in board.journal.applied
    assert board.of(bears).abilities == ()


def test_opalescence_alone_does_not_make_itself_a_creature():
    """ "Each *other* non-Aura enchantment" - CR 613.1d applied to the right set.

    Glorious Anthem is {1}{W}{W}, so Opalescence's 7b (CR 613.4b) sets it to a
    base 3/3 - and then, being a creature its controller controls, it catches
    its own +1/+1 in 7c (CR 613.4c) and ends up a 4/4. Opalescence excludes
    itself, so it is not a creature and the Anthem does not pump it.
    """
    opalescence = permanent("Opalescence")
    anthem = permanent("Glorious Anthem")

    board = compute_board([opalescence, anthem], static_effects([opalescence, anthem]))

    assert not board.of(opalescence).is_creature
    assert board.of(anthem).is_creature
    assert board.of(anthem).power_toughness == (4, 4)
    assert board.of(opalescence).power_toughness == (None, None)


# --------------------------------------------------------------------------
# Dependency
# --------------------------------------------------------------------------


def test_blood_moon_applies_before_urborg_however_the_timestamps_fall():
    """CR 613.8a/613.8b: dependency beats timestamp order.

    Urborg entered first, so timestamp order (CR 613.7) would make every land a
    Swamp and only then turn the nonbasic ones into Mountains - leaving the
    basic Mountain a Swamp as well.

    But Urborg is itself a nonbasic land, so applying Blood Moon strips its
    abilities (CR 305.7) and Urborg's effect stops existing. That is clause (b)
    of CR 613.8a: "applying the other would change the text or the existence
    of" the first effect. Urborg therefore waits for Blood Moon (CR 613.8b),
    and by the time it would apply there is nothing left to apply.

    The reverse is not true: Urborg adding a Swamp type to things changes
    neither which lands are nonbasic nor what Blood Moon does to them, so Blood
    Moon does not depend on Urborg.
    """
    urborg = permanent("Urborg, Tomb of Yawgmoth")
    blood_moon = permanent("Blood Moon")
    mountain = permanent("Mountain")

    effects = static_effects([urborg, blood_moon, mountain])
    board = compute_board([urborg, blood_moon, mountain], effects)

    assert board.journal.applied == ["Blood Moon: nonbasic lands are Mountains"]
    # The description names the source permanent in full: both effects are
    # built from the printed sentence now rather than from a name-keyed row, so
    # nothing abbreviates "Urborg, Tomb of Yawgmoth" to "Urborg" any more.
    assert board.journal.skipped == ["Urborg, Tomb of Yawgmoth: each land is a Swamp"]
    assert board.journal.cycles == []
    assert board.of(urborg).subtypes == ("Mountain",)
    assert board.of(mountain).subtypes == ("Mountain",)
    assert not board.of(mountain).has_ability("{T}: Add {B}.")


def test_without_blood_moon_urborg_applies_normally():
    """The control for the case above: no dependency, so timestamps decide."""
    urborg = permanent("Urborg, Tomb of Yawgmoth")
    mountain = permanent("Mountain")

    board = compute_board([urborg, mountain], static_effects([urborg, mountain]))

    assert board.journal.skipped == []
    assert board.of(mountain).subtypes == ("Mountain", "Swamp")


def test_two_effects_in_different_layers_are_never_dependent():
    """CR 613.8a clause (a): dependency needs the same layer and sublayer.

    Humility's ability-removal is layer 6 and Opalescence's type change is
    layer 4. They interact enormously - one is the reason the other applies to
    Humility at all - but that is layer order, not dependency, and the engine
    must not report a dependency loop for it.
    """
    _, _, _, board = humility_and_opalescence(humility_first=True)

    assert board.journal.cycles == []


def test_a_dependency_loop_falls_back_to_timestamp_order():
    """CR 613.8b: a loop is broken and the effects apply in timestamp order.

    Two Humilities under an Opalescence. Layer 4 makes both of them creatures,
    so in layer 6 each one's ability-removal would delete the other's ability -
    each depends on the other by CR 613.8a, and neither can go first.

    CR 613.8b is the escape hatch, and CR 613.8's "if a dependency exists, it
    will override the timestamp system" stops applying: the loop is ignored and
    the older Humility applies first. The engine has to notice the loop rather
    than spin on it.
    """
    first = permanent("Humility")
    second = permanent("Humility")
    opalescence = permanent("Opalescence")
    bears = permanent("Grizzly Bears")

    effects = static_effects([first, second, opalescence])
    board = compute_board([first, second, opalescence, bears], effects)

    assert len(board.journal.cycles) == 1
    assert board.journal.cycles[0] == [
        "Humility: creatures lose all abilities",
        "Humility: creatures lose all abilities",
    ]
    assert board.of(bears).abilities == ()
    assert board.of(bears).power_toughness == (1, 1)


def test_one_humility_alone_is_not_a_loop():
    """The control: a single Humility has nothing to be circular with."""
    humility = permanent("Humility")
    opalescence = permanent("Opalescence")

    board = compute_board([humility, opalescence], static_effects([humility, opalescence]))

    assert board.journal.cycles == []


def test_a_characteristic_defining_ability_never_depends_on_a_normal_effect():
    """CR 613.8a clause (c), and CR 613.3/613.4a on where CDAs go.

    Layer 7a is the CDA sublayer, so a CDA that defines P/T can never share a
    sublayer with a 7b/7c/7d effect and the question does not arise there. It
    does arise in layers 2-6, where CR 613.3 puts CDAs first and CR 613.8a
    refuses to pair a CDA with a non-CDA. Here a CDA colour effect and a plain
    colour effect sit in layer 5 together; the CDA goes first regardless of the
    later timestamp, and no dependency is reported.
    """
    bears = permanent("Grizzly Bears")
    defined = ContinuousEffect(
        description="cda",
        layer=Layer.COLOR,
        timestamp=99,
        characteristic_defining=True,
        selector=lambda chars, board: chars.is_creature,
        modification=lambda chars, board: chars.with_(colors=()),
    )
    granted = ContinuousEffect(
        description="effect",
        layer=Layer.COLOR,
        timestamp=1,
        selector=lambda chars, board: chars.is_creature,
        modification=lambda chars, board: chars.with_(colors=("U",)),
    )

    board = compute_board([bears], [granted, defined])

    assert board.journal.applied == ["cda", "effect"]
    assert board.journal.cycles == []
    assert board.of(bears).colors == ("U",)


# --------------------------------------------------------------------------
# Gaps
# --------------------------------------------------------------------------


def test_a_copy_effect_replaces_the_copiable_values():
    """CR 613.1a: "Layer 1: Rules and effects that modify copiable values are
    applied." CR 613.2a puts copy effects in that layer's first sublayer:
    "Layer 1a: Copiable effects are applied. This includes copy effects (see
    rule 707, 'Copying Objects')".

    What a copy effect replaces is CR 707.2's list: "the copy acquires the
    copiable values of the original object's characteristics" - name, types,
    subtypes, colors, abilities, mana value and printed power/toughness - and
    *not* the copying permanent's own board identity, which is why `card_id`
    is left alone here and every selector in `machines/layers.py` keeps
    keying off it.

    `printed_characteristics(beast)` is exactly where the real
    `_become_a_copy_builder` reads those values from, so this is the same
    substitution `test_becomes_a_copy.py` drives through real cards, stated
    directly against `compute_board` to show layer 1 runs first and the
    layers above it start from the copied values rather than the printed ones.
    """
    bears = permanent("Grizzly Bears")
    beast = permanent("Questing Beast")
    copied = printed_characteristics(beast)

    copy = ContinuousEffect(
        description="copy",
        layer=Layer.COPY,
        timestamp=1,
        selector=lambda chars, board: chars.card_id == bears.id,
        modification=lambda chars, board: chars.with_(
            name=copied.name,
            mana_value=copied.mana_value,
            supertypes=copied.supertypes,
            types=copied.types,
            subtypes=copied.subtypes,
            colors=copied.colors,
            abilities=copied.abilities,
            power=copied.power,
            toughness=copied.toughness,
        ),
    )
    board = compute_board([bears, beast], [copy])

    assert board.journal.applied == ["copy"]
    assert board.of(bears).name == "Questing Beast"
    assert board.of(bears).power_toughness == (4, 4)
    assert board.of(bears).subtypes == ("Beast",)
    # CR 707.2's copiable values stop short of board identity: this is still
    # the same permanent, which is what every selector keys off.
    assert board.of(bears).card_id == bears.id
    # And the original is untouched (CR 707.2b works the other way too).
    assert board.of(beast).name == "Questing Beast"


@pytest.mark.xfail(
    strict=True,
    reason="CR 613.2 splits layer 1 into sublayers - CR 613.2a's 1a for copy effects and "
    "CR 613.2b's 1b for face-down objects - and machines/layers.py does not: _SUBLAYERED is "
    "(Layer.POWER_TOUGHNESS,) alone, so every layer 1 effect is ordered by timestamp against "
    "every other one. A face-down modification with an earlier timestamp than a copy effect "
    "therefore applies first, where CR 613.2a/613.2b put it strictly after.",
)
def test_layer_1_applies_copy_effects_before_face_down_ones():
    """CR 613.2a then CR 613.2b, regardless of timestamp.

    CR 613.2: "Within layer 1, apply effects in a series of sublayers in the
    order described below. Within each sublayer, apply effects in timestamp
    order." So the sublayer decides first and the timestamp only breaks ties
    *inside* one sublayer. Here the 1b-shaped effect carries the earlier
    timestamp and the 1a copy effect the later one; CR 613.2a still puts the
    copy first, so the face-down 2/2 is what the board ends up reporting.

    The engine has no sublayer for layer 1, so timestamp order alone wins and
    the copy lands last instead.
    """
    bears = permanent("Grizzly Bears")
    beast = permanent("Questing Beast")
    copied = printed_characteristics(beast)

    face_down = ContinuousEffect(
        description="1b: face down",  # CR 613.2b / CR 708.2
        layer=Layer.COPY,
        timestamp=1,
        selector=lambda chars, board: chars.card_id == bears.id,
        modification=lambda chars, board: chars.with_(
            name="", subtypes=(), abilities=(), power=2, toughness=2
        ),
    )
    copy = ContinuousEffect(
        description="1a: copy",  # CR 613.2a
        layer=Layer.COPY,
        timestamp=2,
        selector=lambda chars, board: chars.card_id == bears.id,
        modification=lambda chars, board: chars.with_(
            name=copied.name,
            types=copied.types,
            subtypes=copied.subtypes,
            power=copied.power,
            toughness=copied.toughness,
        ),
    )

    board = compute_board([bears, beast], [copy, face_down])

    assert board.journal.applied == ["1a: copy", "1b: face down"]
    assert board.of(bears).power_toughness == (2, 2)


def test_a_star_power_is_defined_in_7a():
    """CR 613.4a: "Effects from characteristic-defining abilities that define
    power and/or toughness are applied."

    Tarmogoyf's printed power is `*` (CR 208.2), which is no number at all, so
    the printed characteristics carry None and the CDA in sublayer 7a is the
    only thing that puts a value there. `tests/scenarios/` has the interactions;
    this is the bare fact that 7a runs.
    """
    goyf = permanent("Tarmogoyf")
    bolt = card_state("Lightning Bolt", zone=Zone.GRAVEYARD, controller="alice")

    assert printed_characteristics(goyf).power_toughness == (None, None)

    context = LayerContext(graveyards=(bolt,))
    board = compute_board([goyf], static_effects([goyf], context))

    assert board.of(goyf).power_toughness == (1, 2)


def test_a_creature_with_no_value_for_its_power_has_power_zero():
    """CR 208.5: "If a creature somehow has no value for its power, its power is 0."

    Tarmogoyf with no CDA - nothing built one here - has no value for either
    half. `power_toughness` reports the honest None, so a caller can tell "no
    value" from "zero", and `numeric_power_toughness` applies the rule.
    """
    goyf = permanent("Tarmogoyf")

    board = compute_board([goyf])

    assert board.of(goyf).power_toughness == (None, None)
    assert board.of(goyf).numeric_power_toughness == (0, 0)


def test_an_effect_that_modifies_a_creature_with_no_printed_power_reads_it_as_zero():
    """CR 208.5 from the other side: 0 is a number a 7c effect can add to.

    `modify_power_toughness` treats a missing value as 0, so a pump on a
    permanent with no power at all lands on 0 rather than exploding.
    """
    lantern = permanent("Chromatic Lantern")
    pump = ContinuousEffect(
        description="pump",
        layer=Layer.POWER_TOUGHNESS,
        sublayer=Sublayer.MODIFY,
        timestamp=1,
        selector=lambda chars, board: chars.card_id == lantern.id,
        modification=modify_power_toughness(2, 2),
    )

    board = compute_board([lantern], [pump])

    assert board.of(lantern).power_toughness == (2, 2)


def test_two_effects_setting_the_same_value_do_not_depend_on_each_other():
    """CR 613.8a asks what an effect *does*, not what its delta happens to be.

    Regression, found by DDR#366 with two Opalescences: once the first has set a
    permanent to 4/4, the second writes the same 4/4 and so changes nothing.
    Comparing changed-field sets read that collapse as a dependency, which made
    neither Opalescence "ready" and let Humility's later 7b jump the queue
    against CR 613.7. Comparing the values written keeps them independent.
    """
    humility = permanent("Humility")
    first, second = permanent("Opalescence"), permanent("Opalescence")

    board = compute_board([humility, first, second], static_effects([first, second, humility]))

    # Humility has the latest timestamp, so its base 1/1 is written last.
    assert board.of(humility).power_toughness == (1, 1)
    assert board.of(first).power_toughness == (1, 1)
    assert board.of(second).power_toughness == (1, 1)
    assert board.journal.cycles == [], "the two Opalescences are not a dependency loop"


# --------------------------------------------------------------------------
# Durations, and the store that keeps them (CR 611.2)
# --------------------------------------------------------------------------


def test_a_for_as_long_as_effect_needs_a_condition():
    """CR 611.2b: the duration *is* the condition, so there is no effect without it."""
    with pytest.raises(ValueError, match="for as long as"):
        ContinuousEffect(
            description="loses all abilities",
            layer=Layer.ABILITY,
            duration=Duration.FOR_AS_LONG_AS,
            selector=every_creature,
            modification=lose_all_abilities,
        )


def test_a_condition_on_an_effect_with_no_such_duration_is_refused():
    """The other way round: nothing would ever check it, so it is a defect."""
    with pytest.raises(ValueError, match="no condition"):
        ContinuousEffect(
            description="pump",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.MODIFY,
            duration=Duration.UNTIL_END_OF_TURN,
            condition=lambda: True,
            selector=every_creature,
            modification=modify_power_toughness(1, 1),
        )


def test_an_effect_whose_duration_has_stopped_is_not_applied():
    """CR 611.2b: the effect only applies while the duration is running.

    This is not CR 613.6's "already started applying" carve-out - that one is
    about layer 6 taking away the ability that generates a *static* effect.
    A duration that has run out takes its effect away outright.
    """
    bears = permanent("Grizzly Bears")
    running = [True]
    pump = ContinuousEffect(
        description="pump",
        layer=Layer.POWER_TOUGHNESS,
        sublayer=Sublayer.MODIFY,
        duration=Duration.FOR_AS_LONG_AS,
        condition=lambda: running[0],
        selector=every_creature,
        modification=modify_power_toughness(2, 2),
    )

    assert compute_board([bears], [pump]).of(bears).power_toughness == (4, 4)
    running[0] = False
    assert compute_board([bears], [pump]).of(bears).power_toughness == (2, 2)


def test_the_store_stamps_a_permanent_when_it_first_sees_it():
    """CR 613.7a: a static ability's effect is as old as the object it is on.

    The store keeps one clock for both kinds of effect (CR 613.7a, CR 613.7b),
    so a permanent it has already seen keeps its stamp when the board is asked
    again and a newcomer gets a later one.
    """
    anthem = permanent("Glorious Anthem")
    bears = permanent("Grizzly Bears")
    store = ContinuousEffects()

    store.note([anthem])
    first = store.entered[anthem.id]
    store.note([anthem, bears])

    assert store.entered[anthem.id] == first
    assert store.entered[bears.id] > first


def test_the_store_drops_an_effect_whose_duration_never_started():
    """CR 611.2b: "If the 'for as long as' duration never starts, the effect does
    nothing." Not stored, so it cannot start later either."""
    bears = permanent("Grizzly Bears")
    store = ContinuousEffects()

    store.add(
        ContinuousEffect(
            description="never starts",
            layer=Layer.ABILITY,
            duration=Duration.FOR_AS_LONG_AS,
            condition=lambda: False,
            selector=every_creature,
            modification=lose_all_abilities,
        )
    )

    assert store.effects == []
    assert store.board([bears]).of(bears).abilities == ()


def test_end_of_turn_removes_only_the_until_end_of_turn_effects():
    """CR 514.2 and CR 703.4p end "until end of turn" and "this turn" effects.

    An effect with no stated duration is not one of them (CR 611.2a), so it
    survives the cleanup step.
    """
    bears = permanent("Grizzly Bears")
    store = ContinuousEffects()
    store.add(
        ContinuousEffect(
            description="until end of turn",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.MODIFY,
            duration=Duration.UNTIL_END_OF_TURN,
            selector=every_creature,
            modification=modify_power_toughness(3, 3),
        )
    )
    store.add(
        ContinuousEffect(
            description="indefinite",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.MODIFY,
            selector=every_creature,
            modification=modify_power_toughness(1, 1),
        )
    )

    assert store.board([bears]).of(bears).power_toughness == (6, 6)
    ended = store.end_the_turn()

    assert [effect.description for effect in ended] == ["until end of turn"]
    assert store.board([bears]).of(bears).power_toughness == (3, 3)


def test_the_registry_builds_nothing_for_a_spell_with_no_targets():
    """`static_effects` calls every builder with no targets at all.

    Giant Growth and Basking Rootwalla are in `LAYER_EFFECTS` alongside the
    static abilities, so an untargeted call has to come back empty - otherwise
    a Rootwalla standing on the battlefield would be permanently pumped.
    """
    rootwalla = permanent("Basking Rootwalla")

    assert effects_for(rootwalla, 1) == []
    assert static_effects([rootwalla]) == []
    assert compute_board([rootwalla], static_effects([rootwalla])).of(
        rootwalla
    ).power_toughness == (1, 1)
