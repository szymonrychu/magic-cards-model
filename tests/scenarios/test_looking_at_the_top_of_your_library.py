"""Looking at the top N cards, taking some of them, bottoming the rest.

Two printings share the shape, and neither is a scry: nothing is put back on
*top*, and the leftovers are randomised rather than ordered. Both oracle texts
were verified with `resolve_cards` in the session that wrote this file, against
`tests/fixtures/cards/consult_the_star_charts.json` and
`.../michelangelo_s_technique.json`:

- **Consult the Star Charts** - "Kicker {1}{U} (You may pay an additional
  {1}{U} as you cast this spell.)\\nLook at the top X cards of your library,
  where X is the number of lands you control. Put one of those cards into your
  hand. If this spell was kicked, put two of those cards into your hand
  instead. Put the rest on the bottom of your library in a random order."
- **Michelangelo's Technique** - "Sneak {3}{G} ...\\nLook at the top eight
  cards of your library. Put up to two creature cards with total mana value 6
  or less from among them onto the battlefield and the rest on the bottom of
  your library in a random order."

Every rule cited here was looked up with `knowledge_search(type="rules")` in
the session that wrote this file:

- **CR 701.20e** - "Some effects instruct a player to look at one or more
  cards. Looking at a card follows the same rules as revealing a card, except
  that the card is shown only to the specified player."
- **CR 701.24a** - "To shuffle a library ... randomize the cards within it" -
  the word neither card prints. Only the cards looked at and not taken are
  randomised, and they go to the *bottom*, so the rest of the library keeps
  its order.
- **CR 401.4** - "If an effect puts two or more cards in a specific position in
  a library at the same time, the owner of those cards may arrange them in any
  order" - here the arrangement is taken away and made random instead.
- **CR 107.3f** - "Sometimes X appears in the text of a spell or ability but
  not in a mana cost" - Consult the Star Charts' X, counted at resolution.
- **CR 702.33a / CR 702.33d** - kicker is "You may pay an additional [cost] as
  you cast this spell", and declaring the intention to pay it is what makes the
  spell "kicked".
- **CR 607.2i** - the kicker ability and the "if this spell was kicked"
  sentence are linked abilities.
- **CR 608.2d** - a resolving spell's choices are made by its controller as it
  resolves; an illegal answer is not a choice.
- **CR 107.1c** - "any number" runs from zero, which is what makes "up to two"
  satisfiable with none.
- **CR 202.3** - "The mana value of an object is a number equal to the total
  amount of mana in its mana cost, regardless of color."
- **CR 112.1** - "A spell is a card on the stack. As the first step of being
  cast ... the card becomes a spell and is moved to the top of the stack" - a
  card put straight onto the battlefield never became a spell, so nothing that
  triggers on casting can see it.
- **CR 701.17a** - mill, for contrast: nothing here goes to a graveyard.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario, mana_from

# -- Consult the Star Charts ------------------------------------------------

#: Five distinct cards, so a test can tell which of them moved where.
_FIVE = ["Lightning Bolt", "Grizzly Bears", "Llanowar Elves", "Hill Giant", "Giant Spider"]


def _consult_board(*, lands: int = 3, library: list[str] | None = None) -> Scenario:
    """Alice holding Consult the Star Charts, with `lands` Islands out.

    The Islands are both the mana and the X: they are still controlled after
    being tapped to pay, so CR 107.3f's count at resolution is unaffected by
    the payment.
    """
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Consult the Star Charts"],
            battlefield=["Island"] * lands,
            library=list(library if library is not None else _FIVE),
        )
        .player("bob", library=["Island"])
    )


def _cast_consult(scenario, *, kicked: bool = False):
    """Cast Consult the Star Charts, kicked or not, and leave it on the stack."""
    casting = scenario.cast("Consult the Star Charts")
    if kicked:
        casting.pay_kicker()
    payment = casting.begin_paying()
    needed = 4 if kicked else 2
    for source in scenario.untapped_sources(*["Island"] * needed):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    return scenario.put_on_stack(casting)


def test_the_unkicked_spell_looks_at_one_card_per_land_and_takes_one():
    """The happy path: three Islands, three cards looked at, one to hand.

    CR 107.3f's X is the number of lands controlled as this resolves, and the
    two Islands tapped to pay for it are still lands alice controls.
    """
    scenario = _consult_board(lands=3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    looked = scenario.top_of_library(3)
    scenario.will_choose_cards(looked[1], source="Consult the Star Charts")
    spell = _cast_consult(scenario)
    scenario.resolve_top()

    assert spell.zone is Zone.GRAVEYARD
    assert [state.name for state in scenario.player("alice").hand] == ["Grizzly Bears"]
    assert len(scenario.player("alice").library) == 4
    scenario.assert_in_exactly_one_zone(*looked)


def test_kicking_it_takes_two_of_the_cards_into_hand_instead():
    """CR 702.33d, CR 607.2i: the linked "if this spell was kicked" sentence
    replaces the count, so one becomes two - not one *and* two."""
    scenario = _consult_board(lands=5).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    looked = scenario.top_of_library(5)
    scenario.will_choose_cards(looked[0], looked[4], source="Consult the Star Charts")
    spell = _cast_consult(scenario, kicked=True)

    assert scenario.game.cast_record(spell).kicked
    scenario.resolve_top()

    assert sorted(state.name for state in scenario.player("alice").hand) == [
        "Giant Spider",
        "Lightning Bolt",
    ]
    assert len(scenario.player("alice").library) == 3


def test_controlling_no_lands_looks_at_zero_cards_and_does_nothing():
    """X is 0, so there is nothing to look at and no question to ask.

    Two Chromatic Lanterns pay for the spell without being lands, which is the
    only way to reach zero lands and still cast a {1}{U} spell. The effect
    returns before `Game.ask` is reached at all - "put one of those cards into
    your hand" has no *those* to speak of.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Consult the Star Charts"],
            battlefield=["Chromatic Lantern", "Chromatic Lantern"],
            library=list(_FIVE),
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Consult the Star Charts")
    payment = casting.begin_paying()
    for lantern in scenario.untapped_sources("Chromatic Lantern", "Chromatic Lantern"):
        payment.tap_for_mana(lantern, [Color.BLUE])
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.player("alice").hand == []
    assert [state.name for state in scenario.player("alice").library] == _FIVE
    assert not [
        question
        for question in scenario.questions_asked()
        if question.source == "Consult the Star Charts"
    ]


def test_fewer_cards_in_library_than_lands_looks_at_what_is_there():
    """Five Islands but a two-card library: X is 5, the look is 2.

    Nothing in the sentence requires the library to be that deep, and the take
    is clamped to what was actually looked at rather than failing.
    """
    scenario = _consult_board(lands=5, library=["Lightning Bolt", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    looked = scenario.top_of_library(2)
    scenario.will_choose_cards(looked[0], source="Consult the Star Charts")
    _cast_consult(scenario)
    scenario.resolve_top()

    assert [state.name for state in scenario.player("alice").hand] == ["Lightning Bolt"]
    assert [state.name for state in scenario.player("alice").library] == ["Grizzly Bears"]


def test_the_cards_not_taken_go_to_the_bottom_and_none_is_lost():
    """CR 701.24a's word is never printed: the cards below the ones looked at
    keep their order, and only the two leftovers are randomised - underneath
    them, not on top of them."""
    scenario = _consult_board(lands=3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    looked = scenario.top_of_library(3)
    scenario.will_choose_cards(looked[0], source="Consult the Star Charts")
    _cast_consult(scenario)
    scenario.resolve_top()

    library = [state.name for state in scenario.player("alice").library]
    assert library[:2] == ["Hill Giant", "Giant Spider"], "the untouched cards keep their order"
    assert sorted(library[2:]) == ["Grizzly Bears", "Llanowar Elves"], "the rest went to the bottom"
    assert len(library) == 4
    scenario.assert_in_exactly_one_zone(*looked)


# -- Michelangelo's Technique ----------------------------------------------

#: Eight distinct cards: five creatures of known mana value (CR 202.3), a land
#: and two instants that can never be chosen.
_EIGHT = [
    "Llanowar Elves",  # creature, mv 1
    "Lightning Bolt",  # instant
    "Grizzly Bears",  # creature, mv 2
    "Forest",  # land
    "Shardless Agent",  # creature, mv 3, with a cast trigger
    "Hill Giant",  # creature, mv 4
    "Lightning Bolt",  # instant
    "Giant Spider",  # creature, mv 4
]


def _technique_board(library: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Michelangelo's Technique"],
            battlefield=["Forest"] * 5,
            library=list(library if library is not None else _EIGHT),
        )
        .player("bob", library=["Island"])
    )


def _cast_technique(scenario):
    forests = scenario.untapped_sources(*["Forest"] * 5)
    return scenario.cast_and_resolve("Michelangelo's Technique", *forests)


def test_choosing_no_creatures_is_legal_and_bottoms_all_eight():
    """CR 107.1c: "up to two" reaches zero, and zero is a real answer rather
    than a refusal to answer. Everything looked at goes to the bottom."""
    scenario = _technique_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    looked = scenario.top_of_library(8)
    scenario.will_choose_cards(source="Michelangelo's Technique")
    spell = _cast_technique(scenario)

    assert spell.zone is Zone.GRAVEYARD
    assert scenario.battlefield_names() == ["Forest"] * 5
    library = scenario.player("alice").library
    assert len(library) == 8
    assert sorted(state.name for state in library) == sorted(_EIGHT)
    scenario.assert_in_exactly_one_zone(*looked)


def test_a_chosen_pair_over_total_mana_value_six_is_refused():
    """CR 202.3, CR 608.2d: Hill Giant and Giant Spider are 4 and 4, and
    "total mana value 6 or less" is a bound on the pair, not on each card.
    An answer breaking it raises rather than being quietly trimmed."""
    scenario = _technique_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    looked = scenario.top_of_library(8)
    giant = next(state for state in looked if state.name == "Hill Giant")
    spider = next(state for state in looked if state.name == "Giant Spider")
    scenario.will_choose_cards(giant, spider, source="Michelangelo's Technique")

    with pytest.raises(ValueError, match="total mana value 6 or less"):
        _cast_technique(scenario)


def test_choosing_more_than_two_cards_is_refused():
    """CR 107.1c: "up to two" is a ceiling. Three creature cards, all of them
    legal candidates individually, is still not a legal answer - `Game.ask`
    refuses it before the effect's own mana-value bound is even reached."""
    scenario = _technique_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    looked = scenario.top_of_library(8)
    chosen = [state for state in looked if state.name in {"Llanowar Elves", "Grizzly Bears"}] + [
        next(state for state in looked if state.name == "Shardless Agent")
    ]
    scenario.will_choose_cards(*chosen, source="Michelangelo's Technique")

    with pytest.raises(ValueError, match="at most 2 card"):
        _cast_technique(scenario)


def test_noncreature_cards_among_the_eight_are_never_candidates():
    """The Forest and both Lightning Bolts are looked at and bottomed, but the
    question is only ever put over the creature cards - a noncreature is not an
    illegal answer, it is not an answer at all (CR 608.2d)."""
    scenario = _technique_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    looked = scenario.top_of_library(8)
    scenario.will_choose_cards(source="Michelangelo's Technique")
    _cast_technique(scenario)

    (question,) = [
        asked
        for asked in scenario.questions_asked()
        if asked.kind is DecisionKind.CHOOSE_CARDS and asked.source == "Michelangelo's Technique"
    ]
    offered = {state.name for state in looked if state.id in question.cards}
    assert offered == {
        "Llanowar Elves",
        "Grizzly Bears",
        "Shardless Agent",
        "Hill Giant",
        "Giant Spider",
    }


def test_the_creatures_arrive_without_ever_being_cast():
    """CR 112.1: a card only becomes a spell by being cast, and these were
    put onto the battlefield instead. Shardless Agent's cascade is a "when you
    cast this spell" trigger (CR 702.85a's own wording, printed in its reminder
    text), so its silence here is the proof - nothing triggered, nothing went
    on the stack, and nothing was exiled off the top of the library.
    """
    scenario = _technique_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    looked = scenario.top_of_library(8)
    agent = next(state for state in looked if state.name == "Shardless Agent")
    elves = next(state for state in looked if state.name == "Llanowar Elves")
    scenario.will_choose_cards(agent, elves, source="Michelangelo's Technique")

    _cast_technique(scenario)

    assert agent.zone is Zone.BATTLEFIELD
    assert elves.zone is Zone.BATTLEFIELD
    assert scenario.pending_triggers == []
    assert scenario.stack_names() == []
    assert scenario.game.exile == []
    assert len(scenario.player("alice").library) == 6
