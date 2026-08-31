"""Judge scenarios: the layer system, from episodes that argue about it at length.

Sourced from the DDR judge transcripts. Episodes covered:

- **DDR#366** - 2 Opalescence + Humility (the one-Opalescence board is already
  covered by `tests/test_layers.py`; this file adds the second copy, which is
  what the episode is actually about)
- **DDR#319** - Dryad of the Ilysian Grove + Dress Down (layer 4 lands before
  layer 6 ability removal)
- **DDR#497** - Wandering Fumarole + Spatial Contortion (damage already marked,
  against a toughness that changed afterwards)
- **DDR#1016** - Grist, the Hunger Tide + Dress Down (a static ability that only
  functions while its own permanent is *not* on the battlefield never gives
  Dress Down anything to strip)
- **DDR#982** - Double Innkeeper's Talent (two static abilities granting the
  same keyword make two independent instances of it - not modelled)
- **DDR#994** - Toph, the First Metalbender + Blood Moon (two layer 4 effects
  where one changes the set of objects the other applies to - CR 613.8's
  dependency, which overrides timestamps)

`Game` does not consult `machines/layers.py` at all, so the cases that need the
board and the layer engine to agree are written through the harness and xfail on
that integration. The pure-layer cases call `compute_board` the way
`tests/test_layers.py` does. Every CR number here was looked up with
`knowledge_search(type="rules")`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers import compute_board, effects_for, static_effects
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from tests.cards import card_state
from tests.scenarios.harness import Scenario


def permanent(name: str, controller: str = "alice"):
    return card_state(name, zone=Zone.BATTLEFIELD, controller=controller)


# --------------------------------------------------------------------------
# DDR#366 - the second Opalescence
# --------------------------------------------------------------------------


def two_opalescence_and_humility(humility_first: bool):
    """Two Opalescences and a Humility, in a chosen timestamp order.

    CR 613.7a gives a static ability's effect the timestamp of the permanent it
    is on, so passing the permanents to `static_effects` in the order they
    entered the battlefield is the whole of the setup.
    """
    humility = permanent("Humility")
    first = permanent("Opalescence")
    second = permanent("Opalescence")

    order = [humility, first, second] if humility_first else [first, second, humility]
    board = compute_board([humility, first, second], static_effects(order))
    return humility, first, second, board


def test_two_opalescences_make_each_other_creatures():
    """DDR#366: "each *other* non-Aura enchantment" stops being a limit with two.

    A single Opalescence excludes itself, so it never becomes a creature. Two of
    them each catch the other in layer 4 (CR 613.1d), so both are creatures -
    which is the only reason this board differs from the classic one.
    """
    _, first, second, board = two_opalescence_and_humility(humility_first=True)

    assert board.of(first).is_creature
    assert board.of(second).is_creature


def test_humility_last_flattens_the_whole_board_to_one_one():
    """DDR#366: Humility's 7b lands on top when it has the latest timestamp.

    Layer 4 (CR 613.1d) makes all three enchantments creatures. Layer 6
    (CR 613.1f) has Humility strip every creature's abilities, itself and both
    Opalescences included - and CR 613.6 keeps the rest of each effect applying,
    since they all started applying back in layer 4. Sublayer 7b (CR 613.4b) is
    then read in timestamp order (CR 613.7): both Opalescences set mana value
    first, and Humility's base 1/1 overwrites them last.
    """
    humility, first, second, board = two_opalescence_and_humility(humility_first=False)

    assert board.of(humility).power_toughness == (1, 1)
    assert board.of(first).power_toughness == (1, 1)
    assert board.of(second).power_toughness == (1, 1)


def test_humility_first_leaves_every_enchantment_a_four_four():
    """DDR#366: flip the timestamps and both Opalescences survive as 4/4s.

    Sublayer 7b in timestamp order again (CR 613.4b, CR 613.7): Humility sets
    everything to a base 1/1 first, then each Opalescence overwrites the *other*
    enchantments with their mana value. Every one of the three costs {2}{W}{W},
    so all three end up 4/4 - where a single Opalescence would have left itself
    a non-creature with no power or toughness at all.
    """
    humility, first, second, board = two_opalescence_and_humility(humility_first=True)

    assert board.of(humility).power_toughness == (4, 4)
    assert board.of(first).power_toughness == (4, 4)
    assert board.of(second).power_toughness == (4, 4)
    assert board.of(first).abilities == (), "Humility stripped them in layer 6"


# --------------------------------------------------------------------------
# DDR#319 - layer 4 before layer 6
# --------------------------------------------------------------------------


def test_dress_down_does_not_take_back_the_land_types_dryad_already_gave():
    """DDR#319: layer 4 has already happened by the time layer 6 runs.

    Dryad of the Ilysian Grove makes lands every basic land type, which is a
    type-changing effect and so applies in layer 4 (CR 613.1d). Dress Down makes
    creatures lose all abilities, which is layer 6 (CR 613.1f). Layers are
    applied in order, and CR 613.8's dependency system only reorders effects
    "within a layer or sublayer", so nothing can pull the ability removal in
    front of the type change. The lands keep the basic types.
    """
    dryad = permanent("Dryad of the Ilysian Grove")
    dress_down = permanent("Dress Down")
    forest = permanent("Forest")

    board = compute_board(
        [dryad, dress_down, forest],
        static_effects([dryad, dress_down]),
    )

    assert "Swamp" in board.of(forest).subtypes
    assert board.of(dryad).abilities == (), "Dress Down still strips the Dryad itself"


def test_the_dryads_own_land_keeps_every_basic_type_it_already_had():
    """DDR#319, the control: "in addition to" is not CR 305.7's replacement.

    A Forest is already a Forest, so the type it gains from the Dryad is added
    to what is there rather than replacing it (CR 613.1d), and it keeps its own
    green mana ability alongside the four it picks up (CR 305.6).
    """
    dryad = permanent("Dryad of the Ilysian Grove")
    forest = permanent("Forest")

    board = compute_board([dryad, forest], static_effects([dryad]))

    assert board.of(forest).subtypes[0] == "Forest"
    assert set(board.of(forest).subtypes) == {"Plains", "Island", "Swamp", "Mountain", "Forest"}
    assert board.of(forest).has_ability("{T}: Add {G}.")
    assert board.of(forest).has_ability("{T}: Add {W}.")


# --------------------------------------------------------------------------
# DDR#497 - marked damage against a toughness that moved
# --------------------------------------------------------------------------


def test_switching_power_and_toughness_is_computed_after_the_pump():
    """DDR#497, at the layer engine rather than at the board (CR 613.4d).

    Layer 7d takes power and toughness as they stand after 7a-7c and swaps
    them, so Giant Spider's printed 2/4 becomes a 4/2. Nothing here touches the
    damage already marked on the card - that is the next test's problem.
    """
    spider = permanent("Giant Spider")
    image = card_state("Twisted Image", zone=Zone.STACK, controller="alice")

    board = compute_board([spider], effects_for(image, timestamp=1, targets=[spider]))

    assert board.of(spider).power_toughness == (4, 2)


def test_twisted_image_draws_its_card_even_though_the_switch_does_not_reach_the_board():
    """Half of Twisted Image resolves through `machines/effects.py` and half does not.

    "Switch target creature's power and toughness until end of turn. Draw a
    card." The draw (CR 121.1) is an ordinary one-shot effect and happens; the
    switch is a continuous effect in sublayer 7d (CR 613.4d) with a duration,
    and there is nowhere on `Game` to record one. This test pins the half that
    works so the other half's absence stays visible rather than being mistaken
    for a card with no effect entry at all.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Twisted Image"], library=["Forest"], battlefield=["Island"])
        .player("bob", battlefield=["Giant Spider"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spider = scenario.creature("Giant Spider", "bob")

    (island,) = scenario.untapped_sources("Island", username="alice")
    scenario.cast_and_resolve("Twisted Image", island, username="alice", targets=[spider])

    assert [card.name for card in scenario.player("alice").hand] == ["Forest"]
    assert spider.power == 2 and spider.toughness == 4, "the switch never reaches CardState"


def test_damage_that_was_survivable_becomes_lethal_when_toughness_drops():
    """DDR#497: marked damage stays, and is rechecked against the new toughness.

    CR 120.6: "Damage marked on a creature remains until the cleanup step ...
    If the total damage marked on a creature is greater than or equal to its
    toughness, that creature has been dealt lethal damage." Three damage on a
    2/4 Giant Spider is survivable; the moment layer 7d (CR 613.4d) makes it a
    4/2, the same three damage is lethal and CR 704.5g destroys it.

    The whole path is real now: Twisted Image is cast, its entry in
    `machines/effects.py` records the switch in `Game.continuous_effects`
    (CR 611.2, CR 613.7b), and the state-based action check that follows the
    resolution reads the computed board (CR 613.5) and finds the damage lethal.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Lightning Bolt", "Twisted Image"],
            battlefield=["Mountain", "Island"],
        )
        .player("bob", battlefield=["Giant Spider"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spider = scenario.creature("Giant Spider", "bob")

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[spider])
    assert spider.damage == 3 and spider.zone is Zone.BATTLEFIELD, "2/4 survives three damage"

    (island,) = scenario.untapped_sources("Island", username="alice")
    scenario.cast_and_resolve("Twisted Image", island, username="alice", targets=[spider])

    # It is already gone by the time the resolution hands priority back: the
    # state-based action check runs then (CR 704.3) and finds a 4/2 with three
    # damage marked on it.
    assert spider.zone is Zone.GRAVEYARD, "three damage is lethal to a 4/2 (CR 704.5g)"


# --------------------------------------------------------------------------
# DDR#1016 - a static ability that only functions off the battlefield
# --------------------------------------------------------------------------


def test_grist_on_the_battlefield_is_not_a_creature_and_dress_down_has_nothing_to_strip():
    """DDR#1016: "As long as Grist isn't on the battlefield, it's a ... creature".

    Grist, the Hunger Tide's own printed text only grants itself the creature
    type while the card is somewhere other than the battlefield (CR 611.3b:
    "The effect applies at all times that the permanent generating it is on the
    battlefield **or the object generating it is in the appropriate zone**" -
    here the appropriate zone is everywhere *except* the battlefield). Once
    Grist actually enters the battlefield, that condition is false, so Grist is
    a plain planeswalker there and Dress Down's "creatures lose all abilities"
    (layer 6, CR 613.1f) never finds a creature to touch.

    `machines/layers.py` has no registry entry for Grist at all - correctly:
    an entry would only ever need to fire while Grist is off the battlefield,
    which is outside what `compute_board` computes in the first place, so the
    printed type line (`Legendary Planeswalker — Grist`) is already the right
    answer without any special-casing. This pins that the omission is
    deliberate, not an oversight.
    """
    grist = permanent("Grist, the Hunger Tide")
    dress_down = permanent("Dress Down")

    board = compute_board([grist, dress_down], static_effects([grist, dress_down]))

    assert not board.of(grist).is_creature, "off-battlefield-only text does not apply here"
    assert board.of(grist).abilities != (), "Dress Down has no creature here to strip"


def test_dress_down_still_strips_an_actual_creature_alongside_grist():
    """DDR#1016's control: Dress Down is not disarmed, only Grist is spared.

    Same board, but with a real creature on it too - Dress Down's layer 6
    effect (CR 613.1f) still finds and empties *that* permanent's abilities,
    which is what tells the two cases apart rather than Dress Down doing
    nothing at all.
    """
    grist = permanent("Grist, the Hunger Tide")
    dress_down = permanent("Dress Down")
    bears = permanent("Grizzly Bears")

    board = compute_board([grist, dress_down, bears], static_effects([grist, dress_down, bears]))

    assert not board.of(grist).is_creature
    assert board.of(bears).is_creature
    assert board.of(bears).abilities == (), "Grizzly Bears is a creature, so it is stripped"


# --------------------------------------------------------------------------
# DDR#982 - two static abilities granting the same keyword
# --------------------------------------------------------------------------


def test_two_innkeepers_talents_grant_two_separate_ward_instances():
    """DDR#982: multiple static grants of the same keyword do not merge into one.

    Two copies of Innkeeper's Talent, both leveled to 2, each independently
    grant ward {1} to permanents with counters on them (CR 613.1f, CR 604.2).
    A spell targeting such a creature should trigger ward twice (CR 702.21a
    fires "whenever this permanent becomes the target"), needing {1} paid
    twice or the spell is countered - not once.

    The level is set explicitly: CR 716.2a makes a class level bar's abilities
    read "As long as this Class is level N or greater, it has [Abilities]", so
    a level-1 Talent does not have this ability at all and grants nothing -
    which is what `machines/layers.py::effects_for` now enforces by reading
    `CardState.class_ability_text` rather than raw `oracle_text`.
    """
    bear = permanent("Grizzly Bears")
    bear.add_counters("+1/+1", 1)
    talent_one = permanent("Innkeeper's Talent")
    talent_one.class_level = 2
    talent_two = permanent("Innkeeper's Talent")
    talent_two.class_level = 2

    board = compute_board(
        [bear, talent_one, talent_two],
        static_effects([talent_one, talent_two, bear]),
    )

    # Ward is a triggered ability (CR 702.21a) with no redundancy clause of its
    # own - compare CR 702.3c for defender - so two grants are two abilities
    # (CR 113.2c), not one.
    assert board.of(bear).abilities.count("Ward {1}") == 2


def test_a_level_one_innkeepers_talent_grants_no_ward():
    """The control for the case above: CR 716.2a's level gate.

    "[Cost]: Level N — [Abilities]" means, among other things, "As long as this
    Class is level N or greater, it has [Abilities]" - so the ward paragraph is
    printed on a level-1 Talent and is not one of its abilities.
    """
    bear = permanent("Grizzly Bears")
    bear.add_counters("+1/+1", 1)
    talent = permanent("Innkeeper's Talent")

    board = compute_board([bear, talent], static_effects([talent, bear]))

    assert board.of(bear).abilities.count("Ward {1}") == 0


# --------------------------------------------------------------------------
# DDR#994 - Toph + Blood Moon: a dependency inside layer 4
# --------------------------------------------------------------------------


def test_blood_moon_alone_leaves_an_artifact_alone():
    """The control for the episode: without Toph, Sol Ring is not a land, so
    Blood Moon has nothing to say about it.

    Blood Moon ("Nonbasic lands are Mountains", confirmed with `resolve_cards`)
    is one of the layer 4 effects (CR 613.1d: "Type-changing effects are
    applied. These include effects that change an object's card type, subtype,
    and/or supertype"), and it already works on a real nonbasic land. This test
    pins the half that does work, so the xfail below is unambiguously about the
    dependency and not about Blood Moon.
    """
    scenario = (
        Scenario().player("alice", battlefield=["Blood Moon", "Urza's Tower", "Sol Ring"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tower = scenario.find("Urza's Tower", Zone.BATTLEFIELD, "alice")
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")

    assert scenario.game.characteristics_of(tower).subtypes == ("Mountain",)
    assert scenario.game.characteristics_of(sol_ring).subtypes == ()


def test_toph_makes_artifacts_lands_and_blood_moon_then_makes_them_mountains():
    """DDR#994: Blood Moon depends on Toph, so it waits for it (CR 613.8).

    Both effects are layer 4 (CR 613.1d). CR 613.8: "Within a layer or
    sublayer, determining which order effects are applied in is sometimes done
    using a dependency system. If a dependency exists, it will override the
    timestamp system" - and CR 613.8b: "An effect dependent on one or more
    other effects waits to apply until just after all of those effects have
    been applied."

    Applying Toph first turns Sol Ring into a land, which changes the set of
    objects Blood Moon's effect applies to; applying Blood Moon first changes
    nothing about what Toph applies to. So Blood Moon is the dependent one and
    goes second, and Sol Ring ends up an artifact land named for the Mountain
    subtype - keeping its artifact card type, since Toph's effect is worded "in
    addition to their other types". The episode is explicit that this outcome
    does not depend on who controls Blood Moon, whose turn it is, or the order
    the permanents entered.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Toph, the First Metalbender", "Blood Moon", "Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    characteristics = scenario.game.characteristics_of(sol_ring)

    assert Type.ARTIFACT in characteristics.types
    assert Type.LAND in characteristics.types
    assert characteristics.subtypes == ("Mountain",)
