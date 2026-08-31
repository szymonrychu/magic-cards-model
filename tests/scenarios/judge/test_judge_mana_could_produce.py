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

The engine's mana parser (`machines/abilities.parse_mana_abilities`) reads
"{T}: Add ..." and nothing about the sentence after it, which produces two
opposite failures - Reflecting Pool makes no mana at all, and Exotic Orchard
makes any colour unconditionally. Both are `xfail` below. Every CR number here
was looked up with `knowledge_search(type="rules")` in the session that wrote
the file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import parse_mana_abilities
from magic_cards_model.models.mana import Color
from tests.cards import card
from tests.scenarios.harness import Scenario


def test_the_pool_is_read_as_a_land_with_no_mana_ability_at_all():
    """The gap, stated plainly, and the reason the scenarios below are `xfail`.

    "Add one mana of any type that a land you control could produce" is a mana
    ability (CR 605.1a's shape: no target, not a loyalty ability, and it could
    add mana), but the parser has no way to answer CR 106.7's question, so it
    produces nothing rather than guessing a colour.
    """
    assert parse_mana_abilities(card("Reflecting Pool")) == []


@pytest.mark.xfail(
    strict=True,
    reason="`parse_mana_abilities` returns nothing for Reflecting Pool - CR 106.7's "
    "'could produce' needs a survey of the other lands, which the parser does not "
    "do - so `tap_for_mana` refuses it as a land with no {T} mana ability.",
)
def test_the_pool_taps_for_what_an_island_could_produce():
    """CR 106.7 at its simplest: alice controls an Island, so her Reflecting
    Pool could produce blue.

    Nothing subtler than that is asked here - not the Vivid land with no
    counters, not the mutual Exotic Orchard standoff the rule's own example
    settles - because the engine does not get as far as the simple case.
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


@pytest.mark.xfail(
    strict=True,
    reason="`parse_mana_abilities` reads Exotic Orchard's 'Add one mana of any "
    "color ...' as an unconditional any-colour ability: the 'that a land an "
    "opponent controls could produce' clause (CR 106.7) is dropped, so it makes "
    "red off an opponent whose only land is a Plains.",
)
def test_the_orchard_makes_nothing_an_opponents_lands_could_not():
    """CR 106.7 read the other way round, and the failure that matters more.

    bob's only land is a Plains, so the only colour alice's Exotic Orchard could
    produce is white - CR 106.5 then makes an ability that would produce an
    undefined type produce no mana at all. The engine instead lets the Orchard
    pay for a red spell, which is the episode's mutual-standoff case (an Orchard
    and a Pool facing each other make *nothing*) getting the opposite answer.
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
