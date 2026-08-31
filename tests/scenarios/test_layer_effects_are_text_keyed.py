"""Scenario: a continuous effect comes from the printed sentence, not the name.

CR 604.2 - "Static abilities create continuous effects ... These effects are
active as long as the permanent with the ability remains on the battlefield and
has the ability" - and CR 611.3b - "The effect applies at all times that the
permanent generating it is on the battlefield" - both key a static ability's
effect to *the ability*. Neither mentions the card's name.

`machines/layers.py` used to key several of them by name anyway, and the cost
was not theoretical: two pairs of cards print the identical sentence, and in
each pair the card without the registry row generated nothing at all - not even
a `LayerNotice`, because a board-wide sentence does not open the way the
pump/anthem shapes `_LOOKS_LIKE_LAYER_EFFECT_RE` watches for do.

- Blood Moon's "Nonbasic lands are Mountains." was a row; **Harbinger of the
  Seas**' "Nonbasic lands are Islands." was nothing.
- Dryad of the Ilysian Grove's "Lands you control are every basic land type in
  addition to their other types." was a row; **Leyline of the Guildpact**
  prints it verbatim and was nothing.
- Urborg, Tomb of Yawgmoth's "Each land is a Swamp in addition to its other
  land types." was a row; **Yavimaya, Cradle of Growth** says Forest and was
  nothing.

This file pins both halves of each pair - the card that used to work still
does, and the one that did not now does - and then covers the vocabulary that
the same "read the sentence" move opened up: a subtype-filtered anthem, a
board-wide card-type grant, a *domain* characteristic-defining ability, an
equipped-creature static, a delirium-gated self-static, per-colour keyword
grants, and a Class level's grant.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote it, and every card's text with
`resolve_cards`.
"""

from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.layers import (
    Layer,
    LayerContext,
    Sublayer,
    compute_board,
    effects_for,
    is_resolution_layer_effect_text,
    static_effects,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from magic_cards_model.models.token import TREASURE, create_tokens
from tests.cards import card, card_state
from tests.scenarios.harness import Scenario


def permanent(name: str, controller: str = "alice"):
    return card_state(name, zone=Zone.BATTLEFIELD, controller=controller)


def board_of(*permanents):
    """Every permanent's characteristics with only the static abilities on the
    battlefield applied (CR 613.7a's timestamp order is the argument order)."""
    cards = list(permanents)
    return compute_board(cards, static_effects(cards))


# --------------------------------------------------------------------------
# "Nonbasic lands are <basic land type>s."
# --------------------------------------------------------------------------


def test_blood_moon_still_turns_a_nonbasic_land_into_a_mountain():
    """The half that already worked, pinned before the shape moved off its name.

    CR 305.7: "If an effect sets a land's subtype to one or more of the basic
    land types, the land no longer has its old land type. It loses all
    abilities generated from its rules text, its old land types, and any copy
    effects", and CR 305.6 hands back the intrinsic mana ability of the type it
    gained.
    """
    moon = permanent("Blood Moon")
    bog = permanent("Bojuka Bog")

    board = board_of(moon, bog)

    assert board.of(bog).subtypes == ("Mountain",)
    assert board.of(bog).abilities == ("{T}: Add {R}.",)


def test_harbinger_of_the_seas_turns_a_nonbasic_land_into_an_island():
    """The half that used to be silent: Harbinger of the Seas prints "Nonbasic
    lands are Islands." (verified with `resolve_cards`), the same sentence with
    a different basic land type in it (CR 305.6's five).

    Keyed by name it generated nothing whatsoever - the card sat on the
    battlefield doing exactly as much as a vanilla 2/2.
    """
    harbinger = permanent("Harbinger of the Seas")
    bog = permanent("Bojuka Bog")

    board = board_of(harbinger, bog)

    assert board.of(bog).subtypes == ("Island",)
    assert board.of(bog).abilities == ("{T}: Add {U}.",)


def test_neither_of_them_touches_a_basic_land():
    """CR 205.4c: "Any land that doesn't have this supertype is a nonbasic
    land" - so a basic Mountain is outside both effects' selector, whichever
    card generated it.
    """
    harbinger = permanent("Harbinger of the Seas")
    mountain = permanent("Mountain")

    board = board_of(harbinger, mountain)

    assert board.of(mountain).is_basic
    assert board.of(mountain).subtypes == ("Mountain",)


# --------------------------------------------------------------------------
# "Lands you control are every basic land type in addition to their other types."
# --------------------------------------------------------------------------


def test_the_dryad_still_makes_your_lands_every_basic_land_type():
    """CR 613.1d with CR 205.1b's "in addition to": nothing is lost, and each
    basic type gained carries its intrinsic mana ability (CR 305.6).
    """
    dryad = permanent("Dryad of the Ilysian Grove")
    bog = permanent("Bojuka Bog")

    board = board_of(dryad, bog)

    assert {"Plains", "Island", "Swamp", "Mountain", "Forest"} <= set(board.of(bog).subtypes)
    assert "{T}: Add {W}." in board.of(bog).abilities


def test_leyline_of_the_guildpact_makes_the_same_lands_every_basic_land_type():
    """Leyline of the Guildpact prints the Dryad's sentence verbatim (verified
    with `resolve_cards`), and now generates the same layer 4 effect.

    Its other two lines are outside this shape: the opening-hand line is a
    CR 103.6-style start-of-game action and "Each nonland permanent you control
    is all colors" is a layer 5 effect (CR 613.1e) no shape here reads yet.
    """
    leyline = permanent("Leyline of the Guildpact")
    bog = permanent("Bojuka Bog")

    board = board_of(leyline, bog)

    assert {"Plains", "Island", "Swamp", "Mountain", "Forest"} <= set(board.of(bog).subtypes)
    assert "{T}: Add {G}." in board.of(bog).abilities


def test_the_grant_only_reaches_lands_its_own_controller_has():
    """ "Lands **you control**" - CR 611.3a's "applies at any given moment to
    whatever its text indicates", read against the controller on the board.
    """
    leyline = permanent("Leyline of the Guildpact", "alice")
    theirs = permanent("Bojuka Bog", "bob")

    board = board_of(leyline, theirs)

    assert board.of(theirs).subtypes == (), "Bojuka Bog prints no land type of its own"


# --------------------------------------------------------------------------
# "Each land is a <basic land type> in addition to its other land types."
# --------------------------------------------------------------------------


def test_urborg_still_makes_each_land_a_swamp():
    urborg = permanent("Urborg, Tomb of Yawgmoth")
    mountain = permanent("Mountain")

    board = board_of(urborg, mountain)

    assert set(board.of(mountain).subtypes) == {"Mountain", "Swamp"}
    assert "{T}: Add {B}." in board.of(mountain).abilities


def test_yavimaya_makes_each_land_a_forest():
    """Yavimaya, Cradle of Growth: "Each land is a Forest in addition to its
    other land types." (verified with `resolve_cards`) - Urborg's sentence with
    the other subtype, and silent until the shape stopped being keyed by name.
    """
    yavimaya = permanent("Yavimaya, Cradle of Growth")
    mountain = permanent("Mountain", "bob")

    board = board_of(yavimaya, mountain)

    assert set(board.of(mountain).subtypes) == {"Mountain", "Forest"}
    assert "{T}: Add {G}." in board.of(mountain).abilities, "including an opponent's (CR 613.1d)"


# --------------------------------------------------------------------------
# The board-wide card-type grant
# --------------------------------------------------------------------------


def test_toph_makes_your_nontoken_artifacts_lands():
    """Toph, the First Metalbender: "Nontoken artifacts you control are lands
    in addition to their other types."

    CR 205.1b: the artifact keeps every type it already had. The parenthetical
    the card prints is reminder text (CR 207.2a) and states no rule: CR 305.6
    grants an intrinsic mana ability for a *basic land type*, and this grants
    the land card type with no subtype at all.
    """
    toph = permanent("Toph, the First Metalbender")
    sol_ring = permanent("Sol Ring")

    board = board_of(toph, sol_ring)

    assert Type.ARTIFACT in board.of(sol_ring).types
    assert Type.LAND in board.of(sol_ring).types
    assert board.of(sol_ring).subtypes == ()


def test_toph_leaves_an_artifact_token_alone():
    """The "nontoken" half of the same sentence, against a real Treasure token
    (CR 111.10a) created by the game rather than a hand-written stand-in.
    """
    scenario = Scenario().player("alice", battlefield=["Toph, the First Metalbender"]).build()
    (treasure,) = create_tokens(scenario.game, TREASURE, "alice")

    characteristics = scenario.game.characteristics_of(treasure)

    assert Type.ARTIFACT in characteristics.types
    assert Type.LAND not in characteristics.types


# --------------------------------------------------------------------------
# An anthem over a filtered subset of the team
# --------------------------------------------------------------------------


def test_stormscale_scion_pumps_other_dragons_only():
    """Stormscale Scion: "Other Dragons you control get +1/+1." (verified with
    `resolve_cards`) - CR 205.3m's bare creature-type plural standing in for
    "creatures", in sublayer 7c (CR 613.4c).
    """
    scion = permanent("Stormscale Scion")
    dragon = permanent("Archive Dragon")
    bear = permanent("Grizzly Bears")

    board = board_of(scion, dragon, bear)

    assert board.of(dragon).power_toughness == (5, 7)
    assert board.of(bear).power_toughness == (2, 2), "a Bear is not a Dragon"
    assert board.of(scion).power_toughness == (4, 4), '"other" excludes the source'


def test_kaheera_pumps_and_grants_over_a_list_of_subtypes():
    """Kaheera, the Orphanguard: "Each other creature you control that's a Cat,
    Elemental, Nightmare, Dinosaur, or Beast gets +1/+1 and has vigilance."
    (verified with `resolve_cards`) - one ability applying in sublayer 7c and
    layer 6 at once (CR 613.6).
    """
    kaheera = permanent("Kaheera, the Orphanguard")
    lions = permanent("Savannah Lions")
    bear = permanent("Grizzly Bears")

    board = board_of(kaheera, lions, bear)

    assert board.of(lions).power_toughness == (3, 2)  # a printed 2/1
    assert board.of(lions).has_ability("Vigilance")
    assert board.of(bear).power_toughness == (2, 2), "a Bear is on none of the five lists"
    assert not board.of(bear).has_ability("Vigilance")


# --------------------------------------------------------------------------
# A characteristic-defining ability counting the board
# --------------------------------------------------------------------------


def test_territorial_kavu_has_power_and_toughness_equal_to_its_domain():
    """Territorial Kavu: "Domain — Territorial Kavu's power and toughness are
    each equal to the number of basic land types among lands you control."

    A characteristic-defining ability (CR 604.3a: "(1) It defines an object's
    colors, subtypes, power, or toughness; (2) it is printed on the card it
    affects"), so it applies in sublayer 7a (CR 613.4a) - and *domain* is only
    an ability word (CR 207.2c), with the counting spelled out on the card.
    """
    kavu = permanent("Territorial Kavu")
    lands = [permanent("Mountain"), permanent("Plains"), permanent("Blood Crypt")]

    board = board_of(kavu, *lands)

    # Mountain, Plains, and Blood Crypt's Swamp Mountain: three basic land types.
    assert board.of(kavu).power_toughness == (3, 3)


def test_the_domain_count_reads_the_board_after_layer_4():
    """CR 613.5 recomputes continually, and sublayer 7a runs after layer 4
    (CR 613.1d), so a land that only has a basic land type because of a
    continuous effect still counts. A Dryad next to the Kavu is the whole
    five-colour deck's engine.
    """
    kavu = permanent("Territorial Kavu")
    dryad = permanent("Dryad of the Ilysian Grove")
    mountain = permanent("Mountain")

    board = board_of(kavu, dryad, mountain)

    assert board.of(kavu).power_toughness == (5, 5)


# --------------------------------------------------------------------------
# Per-object conditions, the equipped creature, and a gated self-static
# --------------------------------------------------------------------------


def test_scion_of_draco_grants_a_different_keyword_to_each_colour():
    """Scion of Draco: "Each creature you control has vigilance if it's white,
    hexproof if it's blue, lifelink if it's black, first strike if it's red,
    and trample if it's green." (verified with `resolve_cards`)

    Five layer 6 grants (CR 613.1f), each with its own per-object condition.
    The condition is part of what the effect applies to, not a duration:
    CR 611.3a, "a continuous effect generated by a static ability isn't 'locked
    in'; it applies at any given moment to whatever its text indicates".
    """
    scion = permanent("Scion of Draco")
    lions = permanent("Savannah Lions")  # white
    bear = permanent("Grizzly Bears")  # green

    board = board_of(scion, lions, bear)

    assert board.of(lions).has_ability("Vigilance")
    assert not board.of(lions).has_ability("Trample")
    assert board.of(bear).has_ability("Trample")
    assert not board.of(bear).has_ability("Vigilance")


def test_cori_steel_cutter_only_pumps_the_creature_it_is_attached_to():
    """Cori-Steel Cutter: "Equipped creature gets +1/+1 and has trample and
    haste." (verified with `resolve_cards`)

    CR 301.5a: "The creature an Equipment is attached to is called the
    'equipped creature'". Attachment is not a characteristic and never reaches
    the layer engine's board, so the subject is read off the Equipment's own
    attachment - and an unattached one has no equipped creature to talk about.
    """
    cutter = permanent("Cori-Steel Cutter")
    bear = permanent("Grizzly Bears")
    other = permanent("Savannah Lions")

    unattached = board_of(cutter, bear, other)
    assert unattached.of(bear).power_toughness == (2, 2)

    cutter.attach_to(bear)
    attached = board_of(cutter, bear, other)

    assert attached.of(bear).power_toughness == (3, 3)
    assert attached.of(bear).has_ability("Trample")
    assert attached.of(bear).has_ability("Haste")
    assert attached.of(other).power_toughness == (2, 1), "Savannah Lions is a printed 2/1"


def test_dragons_rage_channeler_only_grows_while_it_is_delirious():
    """Dragon's Rage Channeler: "Delirium — As long as there are four or more
    card types among cards in your graveyard, this creature gets +2/+2, has
    flying, and attacks each combat if able." (verified with `resolve_cards`)

    CR 604.2 keeps a static ability's effect active only while its condition
    holds, and CR 613.5 recomputes the board continually, so the effect is
    simply not generated when the graveyard is not delirious. The card types
    are CR 300.1's.
    """
    channeler = permanent("Dragon's Rage Channeler")

    empty = compute_board([channeler], static_effects([channeler]))
    assert empty.of(channeler).power_toughness == (1, 1)
    assert not empty.of(channeler).has_ability("Flying")

    graveyard = tuple(
        card_state(name, zone=Zone.GRAVEYARD, controller="alice")
        for name in ("Lightning Bolt", "Grizzly Bears", "Sol Ring", "Bojuka Bog")
    )
    context = LayerContext(graveyards=graveyard, graveyard_by_controller={"alice": graveyard})
    delirious = compute_board([channeler], static_effects([channeler], context))

    # Instant, creature, artifact, land: four card types (CR 300.1).
    assert delirious.of(channeler).power_toughness == (3, 3)
    assert delirious.of(channeler).has_ability("Flying")


# --------------------------------------------------------------------------
# Keywords no combat rule reads, and a Class level's grant
# --------------------------------------------------------------------------


def test_a_granted_keyword_outside_the_combat_vocabulary_reaches_the_board():
    """CR 702.11a: "Hexproof is a static ability." No combat rule reads it, so
    it is not in `machines/combat.py`'s `Keyword` - but `machines/casting.py`
    reads it off the computed board when it checks target legality, so a layer
    6 grant of it is a real one and refusing to parse the sentence was the bug.
    """
    asceticism = permanent("Asceticism")
    bear = permanent("Grizzly Bears")

    board = board_of(asceticism, bear)

    assert board.of(bear).has_ability("Hexproof")


def test_a_class_grants_nothing_from_a_level_it_has_not_reached():
    """CR 716.2a: "[Cost]: Level N — [Abilities]" means, among other things,
    "As long as this Class is level N or greater, it has [Abilities]" - so
    Innkeeper's Talent's ward paragraph is printed on a level-1 Talent and is
    not one of its abilities. CR 303.6 is what makes it a Class at all.
    """
    talent = permanent("Innkeeper's Talent")
    bear = permanent("Grizzly Bears")
    bear.add_counters("+1/+1", 1)

    at_level_one = board_of(talent, bear)
    assert not at_level_one.of(bear).has_ability("Ward {1}")

    talent.class_level = 2
    at_level_two = board_of(talent, bear)
    assert at_level_two.of(bear).has_ability("Ward {1}")


# --------------------------------------------------------------------------
# The shapes stay static: a permanent spell does not apply its own anthem twice
# --------------------------------------------------------------------------


def test_a_static_shape_never_routes_as_a_resolving_spells_own_effect():
    """CR 611.3b makes a static ability's effect a property of the permanent on
    the battlefield, rebuilt by the battlefield sweep every time the board is
    computed (CR 613.5). A resolving *permanent spell* must not also create a
    stored copy of the same effect, or an anthem would apply twice and would
    outlive the source CR 611.3b ties it to.

    `is_resolution_layer_effect_text` is the routing decision
    `machines/effects.py` asks this module for, and it answers no for every one
    of these shapes - the same exclusion it already made for the plain anthem.
    """
    for name in (
        "Stormscale Scion",
        "Kaheera, the Orphanguard",
        "Blood Moon",
        "Harbinger of the Seas",
        "Leyline of the Guildpact",
        "Toph, the First Metalbender",
        "Cori-Steel Cutter",
        "Dragon's Rage Channeler",
    ):
        assert not is_resolution_layer_effect_text(card(name).oracle_text), name


def test_a_resolution_shape_does_still_route():
    """The control: Mishra's Factory's "{1}: This land becomes a 2/2
    Assembly-Worker artifact creature until end of turn. It's still a land." is
    a CR 611.2 one-shot from a resolving ability, so it *must* route - which is
    what tells the exclusion above apart from switching the routing off.
    """
    assert is_resolution_layer_effect_text(card("Mishra's Factory").oracle_text)


def test_a_permanent_that_leaves_takes_its_effect_with_it():
    """CR 604.2: a static ability's effect is active "as long as the permanent
    with the ability remains on the battlefield". Nothing is stored, so there is
    nothing to expire - the sweep simply stops producing it.
    """
    harbinger = permanent("Harbinger of the Seas")
    bog = permanent("Bojuka Bog")

    assert board_of(harbinger, bog).of(bog).subtypes == ("Island",)
    assert board_of(bog).of(bog).subtypes == (), "Bojuka Bog prints no land type of its own"


def test_the_effect_names_the_printed_line_so_layer_six_can_switch_it_off():
    """CR 613.6: an effect that has not started applying and whose ability has
    been removed never applies. `_still_exists` matches
    `ContinuousEffect.source_ability` against the permanent's own ability lines,
    so a parsed sentence has to carry the *printed* line - reminder text,
    ability word, and printed name included - not the normalised form the
    parser read.
    """
    kavu = permanent("Territorial Kavu")

    (effect,) = effects_for(kavu, 1, static_only=True)

    assert effect.layer is Layer.POWER_TOUGHNESS
    assert effect.sublayer is Sublayer.CHARACTERISTIC_DEFINING
    assert effect.source_ability in kavu.oracle_text.splitlines()


def test_an_equipment_grant_is_a_real_keyword_on_the_computed_board():
    """The layer 6 half of the equipped-creature shape, read the way
    `machines/combat.py` reads it rather than as a text line: CR 613.5 has the
    board recomputed continually, and `has_keyword` asks it.
    """
    scenario = (
        Scenario().player("alice", battlefield=["Cori-Steel Cutter", "Grizzly Bears"]).build()
    )
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    bear = scenario.creature("Grizzly Bears", "alice")
    cutter.attach_to(bear)

    assert has_keyword(bear, Keyword.HASTE, scenario.game)
    assert has_keyword(bear, Keyword.TRAMPLE, scenario.game)
