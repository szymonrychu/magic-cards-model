"""Judge scenarios: "one mana of any type that a land you control could produce".

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#1006** - How does Reflecting Pool Work?

CR 106.7 is the one rule this whole class of cards runs on: "The type of mana a
permanent could produce at any time includes any type of mana that an ability of
that permanent would produce if it were to resolve at that time." Whether the
ability could actually be *activated* is irrelevant - a tapped Vivid land, a
counterless one, a land under a Null Rod all still "could produce" what their
ability says.

Two real oracle texts, confirmed with `resolve_cards`:

- Reflecting Pool: "{T}: Add one mana of any type that a land you control could
  produce."
- Exotic Orchard: "{T}: Add one mana of any color that a land an opponent
  controls could produce."

The engine's mana parser (`machines/abilities.parse_mana_abilities`) used to
read "{T}: Add ..." and nothing about the sentence after it, which produced two
opposite failures - Reflecting Pool made no mana at all, and Exotic Orchard made
any colour unconditionally. Both clauses are now read (`ManaAbility.
could_produce`), and `ManaAbility.effective` runs the survey:

- **"a land you control"** is answered in full off the land types the ability's
  controller controls - the same `Game._controlled_land_types` answer every
  caller already passes - so Reflecting Pool works.
- **"a land an opponent controls"** has no caller running the survey yet
  (`effective`'s `could_produce_colors` is the one-value hook,
  `machines/cost._mana_context` is where it would be filled in, and
  `Game.could_produce_colorless` is the per-permanent survey to generalize).
  Until one does, the survey comes back empty and CR 106.5 makes the Orchard
  produce no mana at all - a refusal in place of the wrong colour it used to
  make.

The fallback survey reads *land types*, not the lands themselves, so it is
under-inclusive: a colour is only reported when some surveyed land carries the
basic land type that CR 305.6 grants the matching intrinsic ability for. An
Ancient Tomb's {C}, a Mana Confluence's any colour, and every "Add one mana of
any color" land are invisible - see
`machines/abilities.colors_land_types_could_produce`. Those cases are the
`xfail`s at the bottom of this file.

Every CR number here was looked up with `knowledge_search(type="rules")` in the
session that wrote or last changed the file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import CouldProduce, parse_mana_abilities
from magic_cards_model.models.mana import Color
from tests.cards import card
from tests.scenarios.harness import Scenario


def test_the_pool_is_read_as_a_survey_rather_than_as_a_flat_list_of_colors():
    """The shape of the answer, stated plainly.

    "Add one mana of any type that a land you control could produce" is a mana
    ability (CR 605.1a's shape: no target, not a loyalty ability, and it could
    add mana). `options` holds the whole universe the sentence could ever
    offer - CR 106.1b's six *types*, colorless included, because the card says
    "type" and not "color" - and `could_produce` records that CR 106.7 has to
    narrow it before any of those is real.

    With no board at all the survey finds nothing, and CR 106.5 - "If an
    ability would produce one or more mana of an undefined type, it produces no
    mana instead" - is what `effective` returns.
    """
    (pool,) = parse_mana_abilities(card("Reflecting Pool"))

    assert pool.could_produce is CouldProduce.LANDS_YOU_CONTROL
    assert {option[0] for option in pool.options} == set(Color)
    assert pool.effective() == ([], False)


def test_the_pool_taps_for_what_an_island_could_produce():
    """CR 106.7 at its simplest: alice controls an Island, so her Reflecting
    Pool could produce blue.

    Nothing subtler than that is asked here - not the Vivid land with no
    counters, not the mutual Exotic Orchard standoff the rule's own example
    settles. The Island is what CR 305.6 gives the intrinsic "{T}: Add {U}"
    to, and that is what the Pool copies; the Pool itself carries no basic
    land type and so contributes nothing to its own survey.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Counterspell"], battlefield=["Reflecting Pool", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pool, _island = scenario.untapped_sources("Reflecting Pool", "Island", username="alice")

    casting = scenario.cast("Counterspell", username="alice")
    payment = casting.begin_paying()
    payment.tap_for_mana(pool, [Color.BLUE])

    assert pool.tapped


def test_the_orchard_makes_nothing_an_opponents_lands_could_not():
    """CR 106.7 read the other way round, and the failure that mattered more.

    bob's only land is a Plains, so the only colour alice's Exotic Orchard could
    produce is white - CR 106.5 then makes an ability that would produce an
    undefined type produce no mana at all. The engine used to let the Orchard
    pay for a red spell, which is the episode's mutual-standoff case (an Orchard
    and a Pool facing each other make *nothing*) getting the opposite answer.

    The red refusal is now correct, and correct for the right half of the
    reason: the clause is read, and `could_produce` narrows the ability's
    universe. What it is *not* yet correct about is the white half - see
    `test_the_orchard_taps_for_the_color_an_opponents_plains_could_produce`
    below - because no caller passes the opponent's land types in, so the
    survey comes back empty for every colour rather than just for red.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Exotic Orchard"])
        .player("bob", battlefield=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (orchard,) = scenario.untapped_sources("Exotic Orchard", username="alice")

    casting = scenario.cast("Lightning Bolt", username="alice", targets=["bob"])
    payment = casting.begin_paying()

    with pytest.raises(ValueError):
        payment.tap_for_mana(orchard, [Color.RED])


def test_the_orchard_narrows_to_exactly_what_the_survey_came_back_with():
    """The Orchard's half of CR 106.7, asked of the parser directly.

    Handed a survey answer, `effective` offers those colours and nothing else,
    and an empty survey is CR 106.5's no mana at all. The narrowing is
    implemented; what is missing is only the caller that runs the survey over
    the opponent's lands - `machines/cost._mana_context` builds `effective`'s
    arguments and has a `payment.game` to ask, and `Game.could_produce_
    colorless` is the per-permanent survey to generalize, so wiring
    `could_produce_colors` is a change in those files rather than in the
    parser.
    """
    (orchard,) = parse_mana_abilities(card("Exotic Orchard"))

    assert orchard.could_produce is CouldProduce.LANDS_AN_OPPONENT_CONTROLS
    assert orchard.effective(could_produce_colors=frozenset({Color.WHITE})) == (
        [[Color.WHITE]],
        False,
    )
    assert orchard.effective(could_produce_colors=frozenset()) == ([], False)
    # The land-type fallback the Pool runs on is not offered to the Orchard:
    # the types `effective` is handed are the *controller's*, and reading them
    # for a clause about an opponent's lands would be a confident wrong answer.
    assert orchard.effective(frozenset({"Plains"})) == ([], False)


@pytest.mark.xfail(
    strict=True,
    reason="nothing passes `ManaAbility.effective`'s `could_produce_colors` yet - "
    "`machines/cost._mana_context` builds those arguments and knows only the "
    "ability's own controller - so the Orchard's CR 106.7 survey comes back empty "
    "and CR 106.5 leaves it producing no mana at all, white included.",
)
def test_the_orchard_taps_for_the_color_an_opponents_plains_could_produce():
    """The other half of the standoff: white *is* a colour bob's Plains could
    produce (CR 305.6), so alice's Orchard makes it."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Helix"], battlefield=["Exotic Orchard", "Mountain"])
        .player("bob", battlefield=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (orchard,) = scenario.untapped_sources("Exotic Orchard", username="alice")

    casting = scenario.cast("Lightning Helix", username="alice", targets=["bob"])
    payment = casting.begin_paying()
    payment.tap_for_mana(orchard, [Color.WHITE])

    assert orchard.tapped


@pytest.mark.xfail(
    strict=True,
    reason="the survey reads land *types*, not the lands themselves: "
    "`colors_land_types_could_produce` maps CR 305.6's five basic land types to "
    "their colours and knows nothing about a nonbasic land's printed ability, so "
    "Ancient Tomb's {C} is invisible to a Reflecting Pool beside it.",
)
def test_the_pool_taps_for_colorless_beside_a_land_with_no_basic_land_type():
    """CR 106.1b's sixth type, and the limit of a type-only survey.

    Reflecting Pool says "any **type**", so colorless is a legal answer where
    Exotic Orchard's "any **color**" could never reach it (CR 106.1a). Ancient
    Tomb's "{T}: Add {C}{C}." is what would license it here - and Ancient Tomb
    carries no basic land type at all, which is exactly what the survey cannot
    see.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Mind Stone"], battlefield=["Reflecting Pool", "Ancient Tomb"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (pool, _tomb) = scenario.untapped_sources("Reflecting Pool", "Ancient Tomb", username="alice")

    casting = scenario.cast("Mind Stone", username="alice")
    payment = casting.begin_paying()
    payment.tap_for_mana(pool, [Color.COLORLESS])

    assert pool.tapped


def test_the_engine_has_one_enum_for_colors_and_types_alike():
    """The episode's opening distinction, and the model does not draw it.

    CR 106.1a: "There are five colors of mana: white, blue, black, red, and
    green." CR 106.1b: "There are six types of mana: white, blue, black, red,
    green, and colorless." `models/mana.Color` is all six, colorless included,
    so nothing in the engine can tell a card that says "any **color**" (Exotic
    Orchard, which therefore cannot see a Wastes) from one that says "any
    **type**" (Reflecting Pool, which can).

    Recorded as an assertion rather than an `xfail` because it is not a
    scenario that fails - it is the shape of the data the two `xfail`s above
    would have to be built on.
    """
    assert {color.value for color in Color} == {"W", "U", "B", "R", "G", "C"}
