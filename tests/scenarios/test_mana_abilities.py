"""CR 605: mana abilities - what makes one, and what happens when it resolves.

Every rule cited here was looked up with `knowledge_search(type="rules")` in the
session that wrote the file.

- **CR 605.1a** - "An activated ability is a mana ability if it meets all of the
  following criteria: it doesn't require a target, it could add mana to a
  player's mana pool when it resolves, it's not a loyalty ability, and its cost
  and effect don't move any card to or from a library."
- **CR 605.3b** - "An activated mana ability doesn't go on the stack, so it
  can't be targeted, countered, or otherwise responded to. Rather, it resolves
  immediately after it is activated."
- **CR 601.2g** - "Mana abilities must be activated before costs are paid" -
  which does not mean a mana ability pays no cost of its own; CR 602.2b routes
  activating an ability through the same process as casting a spell, so its own
  printed cost (a tap, a sacrifice, a life payment) is paid like any other.
- **CR 305.6** - a land with the land card type and a basic land type carries
  the matching mana ability without it being printed as rules text.
- **CR 305.5** - land subtypes are always a single word, which is why "Urza's
  Mine" is read off the board as the words "Urza's" and "Mine" rather than one
  two-word type - see `Game._controlled_land_types`.
- **CR 602.5b** - "If an activated ability has a restriction on its use ...
  the restriction continues to apply" - the umbrella "Activate only if"
  belongs under, which Fanatic of Rhonas's Ferocious and Mox Opal's Metalcraft
  both use.

This is the regression file for the bug where `_ADD`'s regex could not cross a
full stop: a conditional mana ability ("Add {C}. If you control ..., add {C}{C}
instead.") parsed to `mana=None`, missed the CR 605.3b fast path entirely, went
to the stack, and did nothing there because `ACTIVATED_EFFECTS` has no entry
for it - the permanent tapped and no mana appeared. Every Tron-shaped test
below asserts the stack stays empty *and* the pool is not empty, which is the
only way to catch a regression back to that silent failure.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import parse_mana_abilities
from magic_cards_model.models import Color, Zone
from tests.cards import card
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# Conditional "instead" mana abilities (defect 1: Urza's Tron, Gemstone Caverns)
# --------------------------------------------------------------------------


def test_all_three_tron_lands_tap_for_their_bonus_amount():
    """The exact reported bug: all three Tron pieces out, each taps for its
    higher amount, and none of the three ever touches the stack."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Urza's Tower", "Urza's Mine", "Urza's Power Plant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tower, mine, plant = scenario.untapped_sources(
        "Urza's Tower", "Urza's Mine", "Urza's Power Plant"
    )

    scenario.activate(tower)
    scenario.activate(mine)
    scenario.activate(plant)

    pool = scenario.player().mana_pool
    assert pool.floating.get(Color.COLORLESS) == 3 + 2 + 2
    assert tower.tapped and mine.tapped and plant.tapped
    assert scenario.stack_names() == [], "CR 605.3b: a mana ability never uses the stack"


@pytest.mark.parametrize("land", ["Urza's Tower", "Urza's Mine", "Urza's Power Plant"])
def test_a_lone_tron_land_taps_for_its_base_amount(land: str):
    """Condition not met: each Tron land alone still makes mana - the old bug
    made it silently make none at all."""
    scenario = Scenario().player("alice", battlefield=[land]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (source,) = scenario.untapped_sources(land)

    scenario.activate(source)

    assert scenario.player().mana_pool.floating == {Color.COLORLESS: 1}
    assert source.tapped
    assert scenario.stack_names() == []


def test_two_of_three_tron_pieces_is_still_not_enough():
    """Partial Tron: the condition names *both* other pieces, so two out of
    three still only makes the base amount."""
    scenario = Scenario().player("alice", battlefield=["Urza's Tower", "Urza's Mine"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tower, mine = scenario.untapped_sources("Urza's Tower", "Urza's Mine")

    scenario.activate(tower)
    scenario.activate(mine)

    assert scenario.player().mana_pool.floating == {Color.COLORLESS: 2}
    assert scenario.stack_names() == []


def test_gemstone_caverns_conditional_clause_is_not_special_cased_to_tron():
    """The same conditional shape on a card whose condition is a counter on
    itself, not a land type, proving `ManaAbility.resolve` is general."""
    scenario = Scenario().player("alice", battlefield=["Gemstone Caverns"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (caverns,) = scenario.untapped_sources("Gemstone Caverns")

    scenario.activate(caverns)

    assert scenario.player().mana_pool.floating == {Color.COLORLESS: 1}, "no luck counter yet"
    assert scenario.stack_names() == []


def test_gemstone_caverns_with_its_luck_counter_adds_any_colour_instead():
    scenario = Scenario().player("alice", battlefield=["Gemstone Caverns"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (caverns,) = scenario.untapped_sources("Gemstone Caverns")
    caverns.counters.add("luck")

    scenario.activate(caverns, color=Color.BLUE)

    assert scenario.player().mana_pool.floating == {Color.BLUE: 1}
    assert scenario.stack_names() == []


def test_ugins_labyrinth_taps_for_its_base_amount_with_nothing_imprinted():
    """Ugin's Labyrinth's condition is "if a card is exiled with this land" -
    a permanent-to-exiled-card link (`Game.card_imprinted_on`,
    `ExileMarker.IMPRINTED`), not a land type or a counter. With nothing
    imprinted the condition is false, same as a lone Tron piece above.

    The full imprint shape - the enters-the-battlefield choice that links a
    card here in the first place, and the "return the exiled card" ability -
    is `scenarios/test_imprint.py`'s job; this file only proves the
    conditional mana clause itself is general enough to read a third kind of
    condition alongside land types and counters.
    """
    scenario = Scenario().player("alice", battlefield=["Ugin's Labyrinth"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (land,) = scenario.untapped_sources("Ugin's Labyrinth")

    scenario.activate(land)

    assert scenario.player().mana_pool.floating == {Color.COLORLESS: 1}
    assert scenario.stack_names() == []


# --------------------------------------------------------------------------
# Basic land types and their intrinsic ability (defect 2)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("land", "color"),
    [
        ("Plains", Color.WHITE),
        ("Island", Color.BLUE),
        ("Swamp", Color.BLACK),
        ("Mountain", Color.RED),
        ("Forest", Color.GREEN),
    ],
)
def test_every_basic_land_type_taps_for_its_colour(land: str, color: Color):
    """CR 305.6: the mana ability is intrinsic - Forest's whole oracle text is
    reminder text, `({T}: Add {G}.)`, so this only works if the fast path can
    find an ability to activate at all."""
    scenario = Scenario().player("alice", battlefield=[land]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (source,) = scenario.untapped_sources(land)

    scenario.activate(source)

    assert scenario.player().mana_pool.floating == {color: 1}
    assert source.tapped
    assert scenario.stack_names() == []


def test_wastes_taps_for_colourless_off_its_own_printed_ability():
    """Wastes' type line is plain `Basic Land`, with none of CR 305.6's five
    basic land types (Plains, Island, Swamp, Mountain, Forest) - the type its
    `intrinsic_land_ability` fallback keys off. Unlike Forest, Wastes prints
    `{T}: Add {C}.` as real rules text rather than as `({T}: Add {C}.)`
    reminder text, so `parse_abilities`/`activated_abilities_of` read an
    ordinary printed activated ability and never need the fallback at all.

    A reviewer claimed this would tap for nothing; it does not. Pinned here so
    a future change to the intrinsic-land path cannot silently break it.
    """
    scenario = Scenario().player("alice", battlefield=["Wastes"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (source,) = scenario.untapped_sources("Wastes")

    scenario.activate(source)

    assert scenario.player().mana_pool.floating == {Color.COLORLESS: 1}
    assert source.tapped
    assert scenario.stack_names() == []


def test_a_shockland_taps_for_either_of_its_colours():
    """Steam Vents (Island Mountain) prints `({T}: Add {U} or {R}.)` as
    reminder text, same as a basic land - its whole mana ability is
    `intrinsic_land_ability`'s synthesis off its two basic land types
    (CR 305.6), not anything read from its own oracle text. This is here to
    prove the choice plumbing works on a card with two basic land types and a
    non-mana rules line of its own (the pay-2-life-or-enters-tapped clause),
    not only on the single-type basic case above."""
    scenario = Scenario().player("alice", battlefield=["Steam Vents", "Steam Vents"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.untapped_sources("Steam Vents", "Steam Vents")

    scenario.activate(first, color=Color.BLUE)
    scenario.activate(second, color=Color.RED)

    assert scenario.player().mana_pool.floating == {Color.BLUE: 1, Color.RED: 1}
    assert scenario.stack_names() == []


def test_a_ravnica_dual_taps_for_either_of_its_colours():
    scenario = Scenario().player("alice", battlefield=["Breeding Pool", "Breeding Pool"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.untapped_sources("Breeding Pool", "Breeding Pool")

    scenario.activate(first, color=Color.GREEN)
    scenario.activate(second, color=Color.BLUE)

    assert scenario.player().mana_pool.floating == {Color.GREEN: 1, Color.BLUE: 1}


# --------------------------------------------------------------------------
# Colour choices (defect 3)
# --------------------------------------------------------------------------


def test_a_colour_choice_is_made_and_produced():
    """Birds of Paradise: `{T}: Add one mana of any color.` Before the fix,
    the fast path called `ability.mana.produces()` with no colour at all,
    which raised from deep inside the mana model on every "any color" or
    dual-land activation."""
    scenario = Scenario().player("alice", battlefield=["Birds of Paradise"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (bird,) = scenario.untapped_sources("Birds of Paradise")

    scenario.activate(bird, color=Color.BLACK)

    assert scenario.player().mana_pool.floating == {Color.BLACK: 1}
    assert scenario.stack_names() == []


def test_activating_a_choice_ability_with_no_colour_raises_clearly():
    """Regression guard: this must fail with a message naming what is needed,
    not a bare `produces()` `ValueError` with no context about which ability."""
    scenario = Scenario().player("alice", battlefield=["Birds of Paradise"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (bird,) = scenario.untapped_sources("Birds of Paradise")

    with pytest.raises(ValueError, match="pass the colour chosen"):
        scenario.activate(bird)


def test_activating_a_dual_for_a_colour_it_cannot_make_is_refused():
    scenario = Scenario().player("alice", battlefield=["Steam Vents"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (vents,) = scenario.untapped_sources("Steam Vents")

    with pytest.raises(ValueError, match="not one of this ability's options"):
        scenario.activate(vents, color=Color.GREEN)


# --------------------------------------------------------------------------
# How many mana the printed word says
# --------------------------------------------------------------------------


def test_a_count_word_past_three_is_still_a_count():
    """Cascading Cataracts, added to the pool for this: "Indestructible /
    {T}: Add {C}. / {5}, {T}: Add five mana in any combination of colors."
    - read off Scryfall this session.

    The number is printed as a word, and the vocabulary that read it stopped
    at "three", so a printing that says "five" was not recognised as a mana
    ability **at all**: the land tapped for `{C}` and its second ability did
    not exist. Magic prints these counts as far as ten, and none of them is a
    different mechanic from "two" - so the vocabulary is the numbers, not the
    two of them the first cards needed.
    """
    abilities = parse_mana_abilities(card("Cascading Cataracts"))

    assert len(abilities) == 2
    colorless, combination = abilities
    assert colorless.amount == 1
    assert combination.any_color_mixed is True
    assert combination.any_color_count == 5


def test_five_mana_in_any_combination_is_five_colours_of_the_players_choosing():
    """And it is played, not only parsed: the `{5}` half is a real cost
    (CR 602.1a), paid here with five Forests, and the five mana that come back
    are five different colours because "in any combination of colors" lets each
    of them choose its own."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Cascading Cataracts", "Forest", "Forest", "Forest", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (cataracts,) = scenario.untapped_sources("Cascading Cataracts")
    forests = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", "Forest")

    scenario.activate(
        cataracts,
        *forests,
        index=1,
        color=[Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN],
    )

    assert scenario.player().mana_pool.floating == {
        Color.WHITE: 1,
        Color.BLUE: 1,
        Color.BLACK: 1,
        Color.RED: 1,
        Color.GREEN: 1,
    }
    assert scenario.stack_names() == []


# --------------------------------------------------------------------------
# One colour, named as a sequence
# --------------------------------------------------------------------------
#
# `Action.color_options` says which colours an ability offers and
# `Action.color_choice_count` how many of them to name - one per mana whose
# colour is chosen separately, which is 1 for every ability except "N mana in
# any combination of colors". A caller driving the engine through
# `legal_actions` alone reads those two fields together and names a *list* of
# that length, so the one-element list has to mean exactly what the bare
# colour means, everywhere, rather than only on the branch that was written
# with a list in mind.


def test_a_one_element_colour_sequence_is_the_colour_it_names():
    """Steam Vents reports `color_options=(U, R)` and `color_choice_count=1`.
    A caller that honours those two fields together hands back `[U]`, and it
    means the same choice `Color.BLUE` does."""
    scenario = Scenario().player("alice", battlefield=["Steam Vents"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (vents,) = scenario.untapped_sources("Steam Vents")

    scenario.activate(vents, color=[Color.BLUE])

    assert scenario.player().mana_pool.floating == {Color.BLUE: 1}
    assert scenario.stack_names() == []


def test_a_one_element_colour_sequence_reaches_an_any_colour_ability_too():
    """The same on the other branch, so the two cannot drift apart: Birds of
    Paradise's `{T}: Add one mana of any color.`"""
    scenario = Scenario().player("alice", battlefield=["Birds of Paradise"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (bird,) = scenario.untapped_sources("Birds of Paradise")

    scenario.activate(bird, color=[Color.BLACK])

    assert scenario.player().mana_pool.floating == {Color.BLACK: 1}


def test_naming_two_colours_for_one_mana_is_refused_in_the_engines_own_words():
    """The wrong-length sequence is a refusal, not a crash. Steam Vents adds
    one mana, so two colours is a caller mistake the engine has to name - it
    used to reach `color.value` on a list and raise `AttributeError` from
    inside the mana model, which tells a seat nothing about what it did."""
    scenario = Scenario().player("alice", battlefield=["Steam Vents"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (vents,) = scenario.untapped_sources("Steam Vents")

    with pytest.raises(ValueError, match="chooses one colour"):
        scenario.activate(vents, color=[Color.BLUE, Color.RED])


def test_a_bare_string_is_not_a_sequence_of_colours():
    """`Color` is a `StrEnum`, so a plain `str` satisfies `Sequence[Color]` and
    "WU" iterates into the characters "W" and "U" - which are not `Color`
    members, and which used to be added to the pool as raw strings. It is
    refused by name instead."""
    scenario = Scenario().player("alice", battlefield=["Birds of Paradise"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (bird,) = scenario.untapped_sources("Birds of Paradise")

    with pytest.raises(ValueError, match="not a string"):
        scenario.activate(bird, color="WU")


# --------------------------------------------------------------------------
# The ability's own cost is actually paid (defect 4)
# --------------------------------------------------------------------------


def test_tinder_farms_sacrifice_cost_is_actually_paid():
    """Tinder Farm's second ability: `{T}, Sacrifice this land: Add {R}{W}.`"""
    scenario = Scenario().player("alice", battlefield=["Tinder Farm"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (farm,) = scenario.untapped_sources("Tinder Farm")

    scenario.activate(farm, index=1, sacrificing=[farm])

    assert farm.zone is Zone.GRAVEYARD, "the sacrifice cost was actually paid"
    assert scenario.player().mana_pool.floating == {Color.RED: 1, Color.WHITE: 1}
    assert scenario.stack_names() == []


def test_sunbaked_canyons_life_cost_is_actually_paid():
    """`{T}, Pay 1 life: Add {R} or {W}.`"""
    scenario = Scenario().player("alice", battlefield=["Sunbaked Canyon"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (canyon,) = scenario.untapped_sources("Sunbaked Canyon")
    life_before = scenario.player().life

    scenario.activate(canyon, color=Color.RED)

    assert scenario.player().life == life_before - 1, "the life cost was actually paid"
    assert scenario.player().mana_pool.floating == {Color.RED: 1}
    assert scenario.stack_names() == []


# --------------------------------------------------------------------------
# Activation restrictions on the fast path (defect 5)
# --------------------------------------------------------------------------


def test_fanatic_of_rhonas_ferocious_is_refused_without_a_big_creature():
    scenario = (
        Scenario().player("alice", battlefield=["Fanatic of Rhonas", "Grizzly Bears"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fanatic = scenario.creature("Fanatic of Rhonas")

    refusal = scenario.why_cannot_activate(fanatic, index=1)

    assert refusal is not None and "Ferocious" not in refusal  # instructions text, not the word
    assert "activation restriction is not met" in refusal


def test_fanatic_of_rhonas_ferocious_works_with_a_big_creature():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Fanatic of Rhonas", "Sheoldred, the Apocalypse"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fanatic = scenario.creature("Fanatic of Rhonas")

    assert scenario.why_cannot_activate(fanatic, index=1) is None
    scenario.activate(fanatic, index=1)

    assert scenario.player().mana_pool.floating == {Color.GREEN: 4}
    assert scenario.stack_names() == []


def test_mox_opal_metalcraft_is_refused_below_three_artifacts():
    scenario = Scenario().player("alice", battlefield=["Mox Opal"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    opal = scenario.creature("Mox Opal")

    refusal = scenario.why_cannot_activate(opal)

    assert refusal is not None
    assert "activation restriction is not met" in refusal


def test_mox_opal_metalcraft_works_with_three_artifacts():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mox Opal", "Sol Ring", "Chromatic Lantern"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    opal = scenario.creature("Mox Opal")

    assert scenario.why_cannot_activate(opal) is None
    scenario.activate(opal, color=Color.WHITE)

    assert scenario.player().mana_pool.floating == {Color.WHITE: 1}
    assert scenario.stack_names() == []


# --------------------------------------------------------------------------
# Spend restrictions (CR 106.6) - the *production* half.
#
# What the restricted mana may then pay for, and what it refuses, is a mechanic
# of its own and lives in `tests/scenarios/test_mana_spend_restrictions.py`.
# These two only check that activating the restricted ability still produces
# the mana and that the tag arrives on it.
# --------------------------------------------------------------------------


def test_eldrazi_temples_restricted_ability_produces_tagged_mana():
    """`{T}: Add {C}{C}. Spend this mana only to cast colorless Eldrazi spells
    or activate abilities of colorless Eldrazi.` - two colourless mana, both
    carrying the restriction (CR 106.6)."""
    scenario = Scenario().player("alice", battlefield=["Eldrazi Temple"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (temple,) = scenario.untapped_sources("Eldrazi Temple")

    scenario.activate(temple, index=1)
    pool = scenario.player().mana_pool

    assert pool.floating == {Color.COLORLESS: 2}
    assert pool.restricted_total == 2
    assert pool.restrictions()[0].understood is True


def test_cavern_of_souls_restricted_ability_produces_tagged_mana():
    """Cavern of Souls's any-colour ability, with no creature type chosen: the
    mana is still produced and still announced (CR 106.4a), and its restriction
    is present but unreadable, so it pays for nothing at all."""
    scenario = Scenario().player("alice", battlefield=["Cavern of Souls"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (cavern,) = scenario.untapped_sources("Cavern of Souls")

    scenario.activate(cavern, index=1, color=Color.BLUE)
    pool = scenario.player().mana_pool

    assert pool.floating == {Color.BLUE: 1}
    assert pool.restrictions()[0].understood is False
