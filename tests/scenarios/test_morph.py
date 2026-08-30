"""Morph: casting a card face down as a 2/2 (CR 702.37).

CR 702.37a: "Morph is a static ability that functions in any zone from which you
could play the card it's on, and the morph effect works any time the card is
face down. 'Morph [cost]' means "You may cast this card as a 2/2 face-down
creature with no text, no name, no subtypes, and no mana cost **by paying {3}**
rather than paying its mana cost.""

That last clause is the trap this file exists to pin down: the printed morph
cost is *not* what it costs to cast the card face down. {3} is. The printed cost
is what CR 702.37e's special action pays to turn the permanent face up later.

CR 702.37c spells out what the object becomes and, crucially, what kind of thing
those characteristics are: "It becomes a 2/2 face-down creature card with no
text, no name, no subtypes, and no mana cost. ... **These values are the copiable
values of that object's characteristics.**" CR 708.2 says the same generally.
Being copiable values puts them in layer 1 (CR 613.2), which is where the layer
engine should eventually read them from - see `docs/engine-coverage.md`.

They live on `CardState.face_down_characteristics`, not on `Card`: `Card` is the
immutable Scryfall printing, and the same printing is a 3/5 Brine Elemental in
one game and a nameless 2/2 in another.

CR 702.37d: "You can't normally cast a card face down. A morph ability allows you
to do so." CR 702.37e is the way back: "Any time you have priority, you may turn
a face-down permanent you control with a morph ability face up. This is a
special action; it doesn't use the stack."
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import keyword_ability
from magic_cards_model.machines.keywords import (
    face_down_characteristics,
    turn_face_up_cost,
    why_cannot_turn_face_up,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from tests.cards import card
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Brine Elemental", "Aquamorph Entity"],
            battlefield=["Island"] * 8,
        )
        .player("bob")
    )


def cast_face_down(scenario, name: str):
    """Cast a card face down for {3} and resolve it (CR 702.37c)."""
    casting = scenario.cast(name)
    casting.use_keyword("Morph")
    assert str(casting.total_cost.mana) == "{3}"
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Island"] * 3))
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def test_the_morph_cost_is_printed_and_parsed():
    """CR 702.1a: the cost is there to read, whatever the engine does with it."""
    ability = keyword_ability(card("Brine Elemental"), "morph")
    assert ability is not None
    assert ability.cost == "{5}{U}{U}"


def test_the_printed_morph_cost_is_not_what_casting_it_face_down_costs():
    """CR 702.37a: "by paying {3} rather than paying its mana cost"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Brine Elemental")
    casting.use_keyword("Morph")

    assert str(casting.total_cost.mana) == "{3}"
    # And the printed {5}{U}{U} is what CR 702.37e would charge instead.
    cost = turn_face_up_cost(scenario.find("Brine Elemental", Zone.HAND, "alice"), "alice")
    assert cost is not None
    assert str(cost.mana) == "{5}{U}{U}"


def test_a_card_cast_face_down_is_a_nameless_two_by_two():
    """CR 702.37a, 702.37c: {3} buys a 2/2 with no text and no name."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    permanent = cast_face_down(scenario, "Brine Elemental")

    assert permanent.zone is Zone.BATTLEFIELD
    assert permanent.face_down
    assert (permanent.power, permanent.toughness) == (2, 2)
    assert permanent.name == ""
    assert permanent.subtypes == ()
    assert permanent.types == (Type.CREATURE,)
    assert permanent.mana_cost is None
    assert permanent.oracle_text == ""


def test_the_spell_is_already_face_down_on_the_stack():
    """CR 708.4: turned face down *before* it is put onto the stack.

    "Effects that care about the characteristics of a spell will see only the
    face-down spell's characteristics", so a counterspell that could only hit an
    Elemental sees a nameless 2/2 creature spell instead.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Brine Elemental")
    casting.use_keyword("Morph")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Island"] * 3))
    spell = scenario.put_on_stack(casting)

    assert spell.zone is Zone.STACK
    assert spell.face_down
    assert spell.name == ""
    assert (spell.power, spell.toughness) == (2, 2)


def test_a_face_down_creature_has_no_keywords_to_read():
    """CR 702.37c's "no text": a face-down permanent has no abilities at all.

    Asked of the *object*, not of the card. `permanent.card.keywords` is still
    the printing's, and has to be - CR 708.9 makes the owner reveal it as it
    leaves the battlefield.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    permanent = cast_face_down(scenario, "Brine Elemental")

    assert permanent.keywords == ()
    assert permanent.card.keywords == ["Morph"]


def test_turning_it_face_up_is_a_special_action_that_restores_the_card():
    """CR 702.37e: no stack, any time you have priority, and its text comes back."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    permanent = cast_face_down(scenario, "Aquamorph Entity")
    assert (permanent.power, permanent.toughness) == (2, 2)

    assert why_cannot_turn_face_up(permanent) is None
    permanent.turn_face_up()

    assert scenario.game.stack_is_empty  # CR 702.37e: it does not use the stack
    assert permanent.name == "Aquamorph Entity"
    assert permanent.face_up
    assert permanent.oracle_text.startswith("As this creature enters")


def test_a_permanent_with_no_morph_cost_cannot_be_turned_face_up():
    """CR 702.37e's parenthesis, which is the whole check.

    "(If the permanent wouldn't have a morph cost if it were face up, it can't
    be turned face up this way.)" The question is about the card underneath,
    because the face-down object has no text of its own to read (CR 708.2).
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    bears.turn_face_down()

    refusal = why_cannot_turn_face_up(bears)
    assert refusal is not None
    assert "no morph cost" in refusal


def test_a_face_down_permanent_cannot_be_turned_face_down_again():
    """CR 708.2b: "nothing happens and that effect doesn't change any of its
    characteristics or their copiable values"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    permanent = cast_face_down(scenario, "Aquamorph Entity")
    before = permanent.face_down_characteristics

    permanent.turn_face_down()

    assert permanent.face_down_characteristics is before


def test_leaving_the_battlefield_reveals_it_and_gives_the_card_back():
    """CR 708.9 and CR 400.7: it is revealed as it goes, and is a new object."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    permanent = cast_face_down(scenario, "Brine Elemental")
    scenario.game.destroy(permanent)

    assert permanent.zone is Zone.GRAVEYARD
    assert permanent.face_up
    assert permanent.face_down_characteristics is None
    assert permanent.name == "Brine Elemental"


def test_a_card_in_hand_reports_the_characteristics_it_would_have_face_down():
    """CR 702.37c for morph against CR 702.168b for disguise.

    Disguise's set is not the same set: "a 2/2 face-down creature card with
    **ward {2}**, no name, no subtypes, and no mana cost". No printing in this
    pool has disguise, so only morph's is asserted against a real card.
    """
    listed = face_down_characteristics(card("Brine Elemental"))
    assert listed is not None
    assert (listed.power, listed.toughness) == (2, 2)
    assert listed.name == ""
    assert listed.keywords == ()
    assert face_down_characteristics(card("Grizzly Bears")) is None


def test_the_layer_engine_sees_the_face_down_characteristics_too():
    """CR 613.2: the listed characteristics are copiable values, so layer 1.

    This is the half `CardState` cannot cover on its own. Combat assigns damage
    equal to `Game.power_of` (CR 510.1a, CR 613.5) and state-based actions read
    `Game.toughness_of` (CR 704.5f), and both come off the computed board.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    permanent = cast_face_down(scenario, "Brine Elemental")

    assert scenario.game.power_of(permanent) == 2
    assert scenario.game.toughness_of(permanent) == 2
    assert scenario.game.characteristics_of(permanent).name == ""
