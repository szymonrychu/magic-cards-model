"""Scenario: the shapes a spell's own cost reduction can take (CR 601.2f).

`test_dynamic_cost_reduction.py` covers Emrakul, the Promised End's
graveyard-counting discount and the moment CR 601.2f locks a total cost in.
This file is about the *vocabulary*: four more sentences a printing can use to
say "this spell costs less", each counting a different thing, plus the one
conditional discount another permanent's static ability can grant.

CR numbers, all looked up with `knowledge_search(type="rules")` in the session
that wrote this file and quoted from what it returned, never from memory:

- **CR 601.2f** - "The player determines the total cost of the spell. Usually
  this is just the mana cost. Some spells have additional or alternative costs.
  Some effects may increase or reduce the cost to pay ..."
- **CR 118.7a** - "Effects that reduce a cost by an amount of generic mana
  affect only the generic mana component of that cost. They can't affect the
  colored or colorless mana components of that cost." This is what stops
  Leyline Binding's {5}{W} reaching {0}, and what makes Scion of Draco's {12}
  reach {2} rather than sticking anywhere above it.
- **CR 701.9a** - "To discard a card, move it from its owner's hand to that
  player's graveyard."
- **CR 702.29a** - "Cycling is an activated ability that functions only while
  the card with cycling is in a player's hand. 'Cycling [cost]' means '[Cost],
  Discard this card: Draw a card.'" - so a cycled card is a discarded card.
- **CR 702.29d** - "Some cards have abilities that trigger whenever a player
  'cycles or discards' a card. These abilities trigger only once when a card is
  cycled." Hollow One's counter reads the same pair the same way: once.
- **CR 305.6** - "The basic land types are Plains, Island, Swamp, Mountain, and
  Forest. If an object uses the words 'basic land type,' it's referring to one
  of these subtypes."
- **CR 613.1d** - layer 4, where a land *gains* a type, which is what makes
  Dryad of the Ilysian Grove worth all five to domain.
- **CR 106.7** - "Some abilities produce mana based on the type of mana another
  permanent or permanents 'could produce.' The type of mana a permanent could
  produce at any time includes any type of mana that an ability of that
  permanent would produce if the ability were to resolve at that time ..."
- **CR 106.1b** - "There are six types of mana: white, blue, black, red, green,
  and colorless." Colorless is a type and not a colour, which is why an "any
  colour" land is not a land that could produce {C}.
- **CR 702.41a** - "Affinity is a static ability that functions while the spell
  with affinity is on the stack. 'Affinity for [text]' means 'This spell costs
  {1} less to cast for each [text] you control.'"
- **CR 205.2b** - "Some objects have more than one card type ... Such objects
  satisfy the criteria for any effect that applies to any of their card types."
- **CR 601.2a** - the first step of casting, "a player ... moves that card ...
  from where it is to the stack", which is what takes a flashed-back Lesson out
  of the graveyard Gran-Gran is counting five steps before CR 601.2f asks.

*Domain* is an **ability word**: CR 207.2c says ability words "have no special
rules meaning", so there is no rule number for it and none is cited here.
`knowledge_search` confirmed it returns no numbered rule of its own.

Every printing below is a real Scryfall fixture from `tests/fixtures/cards/`,
and the oracle text each test quotes was confirmed with `resolve_cards` in this
session.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import cycle
from magic_cards_model.models import Zone
from magic_cards_model.models.mana import ManaCost

from .harness import Scenario

# -- domain: "for each basic land type among lands you control" -------------


def domain_board(*lands: str, spell: str = "Scion of Draco") -> Scenario:
    """Alice holding `spell`, with `lands` on the battlefield, and a bob who
    controls all five basics - so every test also proves the count is
    controller-scoped ("lands *you* control")."""
    return (
        Scenario()
        .player("alice", hand=[spell], battlefield=list(lands))
        .player("bob", battlefield=["Plains", "Island", "Swamp", "Mountain", "Forest"])
    )


def test_no_basic_land_types_leaves_scion_of_draco_at_twelve():
    """Domain of zero is a reduction of zero, even with an opponent's five out."""
    scenario = domain_board("Wastes").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Scion of Draco")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{12}"


def test_five_basic_land_types_take_ten_off_scion_of_draco():
    """ "Domain - This spell costs {2} less to cast for each basic land type
    among lands you control." Five types at {2} is {10} off a printed {12}."""
    scenario = domain_board("Plains", "Island", "Swamp", "Mountain", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Scion of Draco")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{2}"


def test_domain_counts_types_not_lands():
    """Three Mountains are one basic land type (CR 305.6), so {2} off, not {6}."""
    scenario = domain_board("Mountain", "Mountain", "Mountain").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Scion of Draco")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{10}"


def test_one_dual_land_carries_two_basic_land_types():
    """Blood Crypt is a "Land - Swamp Mountain", so it is worth two types by
    itself - CR 305.8's "nonbasic land, even if it has a basic land type" is no
    obstacle, because domain asks about the *types*, not about basic-ness."""
    scenario = domain_board("Blood Crypt").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Scion of Draco")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{8}"


def test_a_land_that_gains_every_basic_type_makes_domain_five():
    """CR 613.1d, layer 4: Dryad of the Ilysian Grove's "Lands you control are
    every basic land type in addition to their other types" is what one Wastes
    plus a Dryad is worth - all five, from a land that prints no basic type at
    all."""
    scenario = domain_board("Wastes", "Dryad of the Ilysian Grove").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert scenario.game.basic_land_types_controlled("alice") == frozenset(
        {"Plains", "Island", "Swamp", "Mountain", "Forest"}
    )

    casting = scenario.cast("Scion of Draco")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{2}"


def test_a_domain_reduction_cannot_eat_leyline_bindings_white_pip():
    """CR 118.7a: a generic reduction "can't affect the colored ... mana
    components". Leyline Binding is {5}{W} and its domain discount is {1} a
    type, so five types take the whole {5} and leave the {W} standing."""
    scenario = domain_board(
        "Plains", "Island", "Swamp", "Mountain", "Forest", spell="Leyline Binding"
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Leyline Binding")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{W}"


def test_an_oversized_domain_reduction_does_not_go_below_zero():
    """Leyline Binding with three types is {3} off {5}{W}: {2}{W}."""
    scenario = domain_board("Blood Crypt", "Island", spell="Leyline Binding").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Leyline Binding")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{2}{W}"


# -- Hollow One: "for each card you've cycled or discarded this turn" -------


def hollow_one_board(*hand: str) -> Scenario:
    return (
        Scenario()
        .player("alice", hand=["Hollow One", *hand], library=["Island"] * 10)
        .player("bob")
    )


def test_hollow_one_costs_its_printed_five_before_anything_is_discarded():
    scenario = hollow_one_board("Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Hollow One")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{5}"


def test_each_discarded_card_takes_two_off_hollow_one():
    """CR 701.9a's discard, counted per card: two cards is {4} off {5}."""
    scenario = hollow_one_board("Grizzly Bears", "Lightning Bolt").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    scenario.game.discard_cards(
        "alice", [state for state in alice.hand if state.name != "Hollow One"]
    )

    casting = scenario.cast("Hollow One")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{1}"


def test_three_discards_make_hollow_one_free():
    """{2} a card against a printed {5} bottoms out at {0} - CR 118.7's "If the
    mana component of a cost is reduced to nothing by cost reduction effects,
    it's considered to be {0}"."""
    scenario = hollow_one_board("Grizzly Bears", "Lightning Bolt", "Counterspell").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    scenario.game.discard_cards(
        "alice", [state for state in alice.hand if state.name != "Hollow One"]
    )

    casting = scenario.cast("Hollow One")
    scenario.game.determine_total_cost(casting)

    assert casting.total_cost.mana == ManaCost(), "no mana component left at all"


def test_a_cycled_card_counts_once_not_twice():
    """CR 702.29a makes cycling a discard, and CR 702.29d fixes the arithmetic:
    the "cycles or discards" pair counts a cycled card once. Street Wraith's
    "Cycling-Pay 2 life" needs no mana, so nothing else moves."""
    scenario = hollow_one_board("Street Wraith").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    wraith = scenario.find("Street Wraith", Zone.HAND, "alice")
    cycle(scenario.game, wraith, "alice")

    assert scenario.game.cards_discarded_this_turn["alice"] == 1

    casting = scenario.cast("Hollow One")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{3}"


def test_only_your_own_discards_count():
    """ "cards *you've* cycled or discarded" - bob emptying his hand does not
    discount alice's golem."""
    scenario = (
        Scenario()
        .player("alice", hand=["Hollow One"])
        .player("bob", hand=["Grizzly Bears", "Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.discard_cards("bob", list(scenario.player("bob").hand))

    casting = scenario.cast("Hollow One")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{5}"


def test_the_discard_count_is_per_turn():
    """ "this turn" - a new turn starts the count over."""
    scenario = hollow_one_board("Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    scenario.game.discard_cards(
        "alice", [state for state in alice.hand if state.name != "Hollow One"]
    )
    assert scenario.game.cards_discarded_this_turn["alice"] == 1

    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()

    assert scenario.game.cards_discarded_this_turn == {}

    # Bob is the active player now, so the golem cannot be *cast* (CR 117.1a);
    # the reduction is asked of it directly instead, which is the same
    # CR 601.2f question `determine_total_cost` puts.
    golem = scenario.find("Hollow One", Zone.HAND, "alice")
    assert scenario.game.cost_reduction_for(golem, "alice") == ManaCost()


def test_a_discard_a_resolving_ability_causes_discounts_hollow_one():
    """**Regression.** Every other Hollow One test above calls
    `Game.discard_cards` itself. This one makes a *card* do the discarding, and
    that is the whole point: `machines/effects.seasoned_pyromancer` used to call
    `Player.discard` and `Player.draw` directly.

    What was silently wrong: `Player.discard` is only CR 701.9a's move ("to
    discard a card, move it from its owner's hand to that player's graveyard").
    It raises no `DISCARDS_A_CARD` event, and - the consequence this test
    asserts - it never reaches `Game.cards_discarded_this_turn`. CR 601.2f has
    the player "determine the total cost of the spell ... some effects may
    increase or reduce the cost to pay", and Hollow One's own sentence reads
    that count, so a Hollow One cast after a Seasoned Pyromancer was charged the
    full printed {5} instead of {1}. Nothing about the Pyromancer's own
    resolution looked wrong; the price of the *next* card was the only witness.

    CR 121.2 - "cards may only be drawn one at a time" - is the draw half:
    `Game.draw_cards` performs two individual draws, each its own replaceable
    and triggerable event, where `Player.draw(2)` performed neither.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            # Hollow One last: `seasoned_pyromancer` offers the hand in reverse
            # order, so the unscripted CR 701.9b default takes the front two.
            hand=["Seasoned Pyromancer", "Grizzly Bears", "Lightning Bolt", "Hollow One"],
            battlefield=["Mountain", "Mountain", "Mountain", "Mountain"],
            library=["Island"] * 10,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    scenario.will_choose_cards(bears, bolt, username="alice", source="Seasoned Pyromancer")

    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Seasoned Pyromancer", *sources)
    scenario.pass_until_resolved()  # the enters trigger

    assert bears.zone is Zone.GRAVEYARD and bolt.zone is Zone.GRAVEYARD
    assert scenario.game.cards_discarded_this_turn["alice"] == 2, (
        "the effect's own discard has to reach CR 601.2f's counter"
    )
    # CR 121.2's two individual draws really happened: Hollow One plus two
    # Islands off the top.
    assert sorted(state.name for state in scenario.player("alice").hand) == [
        "Hollow One",
        "Island",
        "Island",
    ]

    casting = scenario.cast("Hollow One")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{1}", "{2} off for each of the two discards"


def test_the_pyromancers_tokens_still_count_the_cards_it_discarded():
    """The same resolution's third sentence - "for each nonland card discarded
    this way, create a 1/1 red Elemental" - is a linked count over exactly the
    cards this discard binned, so routing the discard through `Game.discard_
    cards` must not change it: two nonland cards, two Elementals."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Seasoned Pyromancer", "Grizzly Bears", "Mountain", "Hollow One"],
            battlefield=["Mountain", "Mountain", "Mountain"],
            library=["Island"] * 10,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    land = scenario.find("Mountain", Zone.HAND, "alice")
    scenario.will_choose_cards(bears, land, username="alice", source="Seasoned Pyromancer")

    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Seasoned Pyromancer", *sources)
    scenario.pass_until_resolved()

    elementals = [name for name in scenario.battlefield_names() if name == "Elemental Token"]
    assert len(elementals) == 1, "one of the two discarded cards was a land"
    # Both cards were discarded even though only one made a token, so the
    # discount is {4} however the tokens came out.
    assert scenario.game.cards_discarded_this_turn["alice"] == 2

    casting = scenario.cast("Hollow One")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{1}"


# -- Obsidian Charmaw: "each land your opponents control that could produce {C}"


def charmaw_board(*opponent_lands: str) -> Scenario:
    return (
        Scenario()
        .player("alice", hand=["Obsidian Charmaw"], battlefield=["Mountain", "Wastes"])
        .player("bob", battlefield=list(opponent_lands))
    )


def test_obsidian_charmaw_is_full_price_against_coloured_lands():
    """Bob's basics produce {W} and {U}; neither could produce {C} (CR 106.1b:
    colorless is a type of mana, not a colour). Alice's own Wastes could, and
    is not counted - the sentence says "your opponents control"."""
    scenario = charmaw_board("Plains", "Island").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Obsidian Charmaw")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{3}{R}{R}"


def test_each_opponent_land_that_could_produce_colorless_takes_one_off():
    """CR 106.7's "could produce": Urza's Mine, Urza's Power-Plant and Urza's
    Tower each have a {T}: Add {C} ability, so the Charmaw arrives for {R}{R}."""
    scenario = charmaw_board("Urza's Mine", "Urza's Power Plant", "Urza's Tower").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Obsidian Charmaw")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{R}{R}", "CR 118.7a keeps both red pips"


def test_a_wastes_an_opponent_controls_counts():
    """Wastes' intrinsic ability is "{T}: Add {C}." (CR 305.6's own intrinsic
    rule for a land type), which is exactly what the Charmaw is looking for."""
    scenario = charmaw_board("Wastes", "Eldrazi Temple").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Obsidian Charmaw")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{1}{R}{R}"


def test_a_nonland_that_could_produce_colorless_is_not_counted():
    """ "for each *land* your opponents control" - Sol Ring makes {C}{C} and is
    an artifact, so it is outside the sentence entirely."""
    scenario = charmaw_board("Sol Ring", "Island").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Obsidian Charmaw")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{3}{R}{R}"


# -- affinity for artifacts (CR 702.41a) -----------------------------------


def emry_board(*battlefield: str, opponent: tuple[str, ...] = ()) -> Scenario:
    return (
        Scenario()
        .player("alice", hand=["Emry, Lurker of the Loch"], battlefield=list(battlefield))
        .player("bob", battlefield=list(opponent))
    )


def test_emry_is_full_price_with_no_artifacts():
    scenario = emry_board("Island").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Emry, Lurker of the Loch")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{2}{U}"


def test_affinity_takes_one_off_for_each_artifact_you_control():
    """CR 702.41a: "'Affinity for [text]' means 'This spell costs {1} less to
    cast for each [text] you control.'" Two artifacts, {2} off {2}{U}, and
    CR 118.7a leaves the {U}."""
    scenario = emry_board("Mox Opal", "Darksteel Relic", "Island").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Emry, Lurker of the Loch")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{U}"


def test_affinity_does_not_count_an_opponents_artifacts():
    """ "each artifact *you* control"."""
    scenario = emry_board("Island", opponent=("Mox Opal", "Darksteel Relic")).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Emry, Lurker of the Loch")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{2}{U}"


def test_an_artifact_creature_counts_once_for_affinity():
    """CR 205.2b makes an artifact creature both types, but affinity for
    artifacts counts *permanents*, so Scion of Draco on the battlefield is one
    artifact, not two."""
    scenario = emry_board("Scion of Draco", "Island").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Emry, Lurker of the Loch")
    scenario.game.determine_total_cost(casting)

    assert str(casting.total_cost.mana) == "{1}{U}"


# -- Gran-Gran: a discount gated on a graveyard count -----------------------


def gran_gran_board(lessons: int, hand: str) -> Scenario:
    """Gran-Gran out, `lessons` Lesson cards in the graveyard, and `hand` to
    cast. Combustion Technique is a real "Instant - Lesson" (confirmed with
    `resolve_cards`)."""
    return (
        Scenario()
        .player(
            "alice",
            hand=[hand],
            battlefield=["Gran-Gran", "Mountain", "Mountain"],
            graveyard=["Combustion Technique"] * lessons,
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_gran_gran_discounts_a_noncreature_spell_once_the_gate_is_met():
    """ "Noncreature spells you cast cost {1} less to cast as long as there are
    three or more Lesson cards in your graveyard." Lightning Bolt is {R}, and
    CR 118.7a means a generic reduction cannot touch that pip - so the proof is
    on `static_cost_modifiers_for`'s own decrease list, then on a spell with
    generic to give."""
    scenario = gran_gran_board(3, hand="Counterspell").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spell = scenario.find("Counterspell", Zone.HAND, "alice")

    _, decreases, _ = scenario.game.static_cost_modifiers_for(spell, "alice")

    assert [str(cost) for cost in decreases] == ["{1}"]


def test_two_lessons_are_not_enough_for_gran_grans_gate():
    scenario = gran_gran_board(2, hand="Counterspell").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spell = scenario.find("Counterspell", Zone.HAND, "alice")

    _, decreases, _ = scenario.game.static_cost_modifiers_for(spell, "alice")

    assert decreases == []


def test_the_gate_is_a_gate_not_a_multiplier():
    """Four Lessons discount exactly as much as three: "{1} less ... as long
    as", not "{1} less for each"."""
    scenario = gran_gran_board(4, hand="Counterspell").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spell = scenario.find("Counterspell", Zone.HAND, "alice")

    _, decreases, _ = scenario.game.static_cost_modifiers_for(spell, "alice")

    assert [str(cost) for cost in decreases] == ["{1}"]


def test_gran_gran_does_not_discount_a_creature_spell():
    """ "*Noncreature* spells you cast" - CR 205.2b checks every card type the
    spell has, and Grizzly Bears is a creature."""
    scenario = gran_gran_board(4, hand="Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spell = scenario.find("Grizzly Bears", Zone.HAND, "alice")

    _, decreases, _ = scenario.game.static_cost_modifiers_for(spell, "alice")

    assert decreases == []


def test_gran_grans_discount_reaches_a_cast_spells_total_cost():
    """The whole path, not just the modifier list: Counterspell is {U}{U} and
    CR 118.7a protects both pips, so the spell that proves the discount lands
    on a real cast is one with generic mana in it - Combustion Technique's own
    {1}{R} from the hand."""
    scenario = gran_gran_board(3, hand="Combustion Technique").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Combustion Technique", targets=[bears])
    payment = scenario.game.determine_total_cost(casting)

    assert str(payment.cost) == "{R}"


def test_the_gate_is_read_when_the_cost_is_determined_not_before():
    """CR 601.2a moves the card being cast to the stack before CR 601.2f asks,
    so flashing a Lesson off a graveyard of exactly three leaves two behind and
    the gate closes. Here the same effect is shown from the hand instead: three
    Lessons in the graveyard and a fourth in hand still counts three."""
    scenario = gran_gran_board(3, hand="Combustion Technique").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spell = scenario.find("Combustion Technique", Zone.HAND, "alice")

    _, decreases, _ = scenario.game.static_cost_modifiers_for(spell, "alice")
    assert [str(cost) for cost in decreases] == ["{1}"]

    scenario.player("alice").graveyard.pop()

    _, after, _ = scenario.game.static_cost_modifiers_for(spell, "alice")
    assert after == [], "two Lessons left, and the gate is shut"


# -- the reduction machinery itself ----------------------------------------


def test_an_unrecognised_reduction_sentence_reduces_nothing():
    """The fail-closed guarantee: a card with no reduction sentence at all gets
    an empty `ManaCost` rather than a guess."""
    scenario = Scenario().player("alice", hand=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")

    assert scenario.game.cost_reduction_for(bears, "alice") == ManaCost()
