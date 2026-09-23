"""Discover N: CR 701.57a-c, a keyword action reusing cascade's own machinery.

CR 701.57a: ""Discover N" means "Exile cards from the top of your library
until you exile a nonland card with mana value N or less. You may cast that
card without paying its mana cost if the resulting spell's mana value is less
than or equal to N. If you don't cast it, put that card into your hand. Put
the remaining exiled cards on the bottom of your library in a random order.""

Discover reads like cascade (CR 702.85a) with two differences that matter:

- **N or less** - cascade stops at a strictly cheaper card; discover stops at
  one whose mana value is `N` or less, so a card costing exactly `N` is a hit.
- **declining goes to hand, not the bottom** - cascade bottoms a declined hit
  along with the misses; discover's "if you don't cast it, put that card into
  your hand" gives the hit its own resting place. Only the misses - the cards
  exiled and passed over on the way - go to the bottom.

CR 701.57b: "A player has 'discovered' after the process described in rule
701.57a is complete, even if some or all of those actions were impossible" -
an empty library still discovers, having found nothing.

CR 701.57c: "If the final card exiled during the process described in rule
701.57a has mana value N or less, it is the 'discovered card'" - the same
card this module calls `result.hit`, regardless of whether it ends up cast or
in hand.

CR 107.3b: a spell with `{X}` in its cost, cast this way (without paying its
mana cost and with no alternative cost that fixes X), has X of 0.

`machines/keywords.discover` is the primitive - cascade's own exile-until,
free-cast, and random-bottom machinery, parameterised by `N` instead of the
cascading spell's own mana value. `machines/effects._parse_discover_clause`
reads "discover N" as one clause among however many a card's triggered,
activated, or spell text prints around it - Trumpeting Carnosaur's bare
enters-the-battlefield trigger, Geological Appraiser's "if you cast it"
intervening *if* (CR 603.4) in front of the identical clause, and Zoetic
Glyph's leaves-the-battlefield trigger all read the same "discover 3"/"discover
5" text without a card-specific parser.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.keywords import discover
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board(*library: str) -> Scenario:
    return (
        Scenario().manual_turn_based_actions().player("alice", library=list(library)).player("bob")
    )


# --------------------------------------------------------------------------
# The primitive itself (`machines.keywords.discover`), called directly - the
# same style `test_cascade.py` uses for the machinery it shares.
# --------------------------------------------------------------------------


def test_discover_stops_at_the_first_nonland_card_with_mana_value_n_or_less():
    """Lightning Bolt is mana value 1; discover 1 stops on it immediately."""
    scenario = board("Lightning Bolt", "Counterspell").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    result = discover(scenario.game, "alice", 1, source_name="Test", seed=0)

    assert result.hit is not None
    assert result.hit.name == "Lightning Bolt"


def test_lands_are_never_the_hit():
    """ "a nonland card" - a Forest has mana value 0 and is still skipped,
    however low `N` is."""
    scenario = board("Forest", "Forest", "Lightning Bolt").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    result = discover(scenario.game, "alice", 5, source_name="Test", seed=0)

    assert result.hit is not None
    assert result.hit.name == "Lightning Bolt"
    assert [state.name for state in result.exiled] == ["Forest", "Forest", "Lightning Bolt"]


def test_a_card_with_mana_value_above_n_is_skipped():
    """Counterspell is mana value 2; discover 1 passes over it and keeps going."""
    scenario = board("Counterspell", "Lightning Bolt").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    result = discover(scenario.game, "alice", 1, source_name="Test", seed=0)

    assert result.hit is not None
    assert result.hit.name == "Lightning Bolt"
    assert [state.name for state in result.exiled] == ["Counterspell", "Lightning Bolt"]


def test_a_card_with_mana_value_exactly_n_counts_as_a_hit():
    """ "N or less" is not strict, unlike cascade's own "less than": Kitchen
    Finks is mana value 3, and discover 3 stops right there."""
    scenario = board("Kitchen Finks", "Lightning Bolt").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    result = discover(scenario.game, "alice", 3, source_name="Test", seed=0)

    assert result.hit is not None
    assert result.hit.name == "Kitchen Finks"
    assert [state.name for state in result.exiled] == ["Kitchen Finks"]


def test_everything_passed_on_the_way_goes_to_the_bottom_when_the_hit_is_cast():
    """The misses go to the bottom; the cast hit leaves through the stack,
    not the library at all."""
    scenario = board("Forest", "Counterspell", "Lightning Bolt", "Island").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    result = discover(scenario.game, "alice", 1, source_name="Test", seed=1)

    library = scenario.player("alice").library
    assert result.hit is not None and result.hit.name == "Lightning Bolt"
    assert sorted(state.name for state in library) == ["Counterspell", "Forest", "Island"]
    assert scenario.game.exile == []
    assert result.hit.zone is Zone.STACK


def test_declining_puts_the_hit_into_hand_not_the_bottom():
    """CR 701.57a's own second sentence, and discover's real difference from
    cascade: "If you don't cast it, put that card into your hand." - not the
    bottom of the library the misses get."""
    scenario = board("Forest", "Lightning Bolt", "Island").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, source="Test")

    result = discover(scenario.game, "alice", 1, source_name="Test", seed=0)

    asked = scenario.questions_asked()
    assert any(
        question.kind is DecisionKind.MAY and question.source == "Test" for question in asked
    )
    assert result.hit is not None
    assert result.hit.name == "Lightning Bolt"
    assert result.hit.zone is Zone.HAND
    assert result.hit in scenario.player("alice").hand
    assert result.hit.exile_annotation is None
    # Island was never exiled at all - it sat below the top and was never
    # touched. Forest, the one miss, joins it at the bottom.
    library = scenario.player("alice").library
    assert [state.name for state in library] == ["Island", "Forest"]
    assert scenario.game.exile == []


def test_an_empty_library_finds_nothing_and_loses_nobody_the_game():
    """CR 701.57b: the process completes - and a player has discovered -
    even with nothing to find. Not a draw (CR 704.5b)."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    result = discover(scenario.game, "alice", 5, source_name="Test", seed=0)

    assert result.hit is None
    assert result.exiled == []
    assert not scenario.player("alice").tried_to_draw_from_empty_library


def test_a_library_with_nothing_qualifying_bottoms_everything():
    """Every card exiled costs more than `N`, or is a land: the whole library
    comes back, none of it through a hand."""
    scenario = board("Forest", "Counterspell", "Kitchen Finks").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    result = discover(scenario.game, "alice", 1, source_name="Test", seed=2)

    assert result.hit is None
    assert len(result.exiled) == 3
    assert scenario.game.exile == []
    assert scenario.player("alice").hand == []
    assert len(scenario.player("alice").library) == 3


def test_the_discovered_card_is_the_final_card_exiled():
    """CR 701.57c: "the discovered card" is `result.hit` regardless of
    whether it is cast or (as here) declined into hand."""
    scenario = board("Counterspell", "Lightning Bolt").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, source="Test")

    result = discover(scenario.game, "alice", 1, source_name="Test", seed=0)

    assert result.hit is result.exiled[-1]
    assert result.hit.name == "Lightning Bolt"


def test_x_equals_zero_when_cast_this_way():
    """CR 107.3b: a spell with `{X}` in its cost, cast without paying its
    mana cost, has X of 0 - not the number the library happened to have room
    for, and not left undefined either. Walking Ballista prints "This
    creature enters with X +1/+1 counters on it" over a 0/0 body, so X = 0
    is not a quiet number to check for - it is the real-game consequence CR
    704.5f then sweeps away: "If a creature has toughness 0 or less, it's
    put into its owner's graveyard", the instant state-based actions are
    next checked.
    """
    scenario = board("Walking Ballista", "Lightning Bolt").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    result = discover(scenario.game, "alice", 3, source_name="Test", seed=0)
    scenario.resolve_top()  # Walking Ballista, cast during resolution, still has to resolve

    assert result.hit is not None
    assert result.hit.name == "Walking Ballista"
    assert result.hit.zone is Zone.GRAVEYARD, (
        "0/0 with X = 0: dead to CR 704.5g the instant it enters"
    )


def test_random_bottom_order_is_seeded_for_replay():
    """The same seed produces the same bottomed order every time - the
    reproducible-seed convention cascade, graveyard-bottom and hideaway all
    already use, and what makes a decoded replay of this game put the misses
    back in the order the original game really had."""
    scenario_a = board("Forest", "Island", "Swamp", "Plains", "Lightning Bolt").build()
    scenario_a.start_at(Step.PRECOMBAT_MAIN)
    result_a = discover(scenario_a.game, "alice", 1, source_name="Test", seed=7)

    scenario_b = board("Forest", "Island", "Swamp", "Plains", "Lightning Bolt").build()
    scenario_b.start_at(Step.PRECOMBAT_MAIN)
    result_b = discover(scenario_b.game, "alice", 1, source_name="Test", seed=7)

    order_a = [state.name for state in scenario_a.player("alice").library]
    order_b = [state.name for state in scenario_b.player("alice").library]
    assert order_a == order_b
    assert result_a.hit is not None and result_b.hit is not None


# --------------------------------------------------------------------------
# The clause parser (`machines.effects._parse_discover_clause`), proven on
# three real printings with three different trigger shapes.
# --------------------------------------------------------------------------


def _resolve_the_trigger(scenario) -> None:
    """Put the pending discover trigger on the stack (CR 603.3) and resolve
    it - once, not a full drain: a cast hit lands *above* it (CR 608.2g) and
    a test that wants to see it there, mid-resolution, must not also resolve
    that spell out from under itself."""
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()


def test_trumpeting_carnosaur_etb_discovers_5_and_free_casts_the_hit():
    """Trumpeting Carnosaur: "When this creature enters, discover 5." - a
    bare enters-the-battlefield trigger, no intervening *if*."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Trumpeting Carnosaur"],
            library=["Lightning Bolt"],
            battlefield=["Mountain"] * 6,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Mountain"] * 6), username="alice")

    scenario.cast_and_resolve("Trumpeting Carnosaur", *sources, username="alice")
    _resolve_the_trigger(scenario)

    bolt = scenario.find("Lightning Bolt", Zone.STACK)
    assert bolt.zone is Zone.STACK
    assert scenario.game.exile == []


def test_trumpeting_carnosaur_declines_the_hit_goes_to_hand():
    """Declining Trumpeting Carnosaur's own discover puts the hit in hand,
    not back in the library with the misses."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Trumpeting Carnosaur"],
            library=["Lightning Bolt"],
            battlefield=["Mountain"] * 6,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Mountain"] * 6), username="alice")
    scenario.will_take_the_may(False, source="Trumpeting Carnosaur")

    scenario.cast_and_resolve("Trumpeting Carnosaur", *sources, username="alice")
    _resolve_the_trigger(scenario)

    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    assert bolt.zone is Zone.HAND
    assert scenario.game.exile == []


def test_trumpeting_carnosaur_skips_a_land_and_a_card_over_mana_value_5():
    """A land and an over-costed card are both passed over on the way to the
    real hit - "discover 5" stops at mana value 5 or less, never at a land
    however cheap, and never at a card costing 6 or more."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Trumpeting Carnosaur"],
            library=["Forest", "Wurmcoil Engine", "Kitchen Finks"],
            battlefield=["Mountain"] * 6,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Mountain"] * 6), username="alice")

    scenario.cast_and_resolve("Trumpeting Carnosaur", *sources, username="alice")
    _resolve_the_trigger(scenario)

    finks = scenario.find("Kitchen Finks", Zone.STACK)
    assert finks.zone is Zone.STACK
    assert scenario.game.exile == []


def test_geological_appraiser_cast_from_hand_triggers_discover():
    """Geological Appraiser: "When this creature enters, if you cast it,
    discover 3." - cast normally, the intervening *if* (CR 603.4) holds and
    the identical "discover 3" clause runs."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Geological Appraiser"],
            library=["Lightning Bolt"],
            battlefield=["Mountain"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Mountain"] * 4), username="alice")

    scenario.cast_and_resolve("Geological Appraiser", *sources, username="alice")
    _resolve_the_trigger(scenario)

    bolt = scenario.find("Lightning Bolt", Zone.STACK)
    assert bolt.zone is Zone.STACK


def test_geological_appraiser_put_onto_the_battlefield_without_casting_never_triggers():
    """CR 603.4: "the ability triggers only if it's true". A Geological
    Appraiser that arrives some other way - here straight from hand, standing
    in for reanimation - was never cast, so "if you cast it" is false and
    nothing goes on the stack. Discover never runs and the library is
    untouched.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Geological Appraiser"], library=["Lightning Bolt"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    appraiser = scenario.put_onto_battlefield("Geological Appraiser", "alice")
    scenario.game.put_triggers_on_stack()

    assert appraiser.zone is Zone.BATTLEFIELD
    assert scenario.stack_names() == [], "the intervening *if* stopped it triggering"
    assert [state.name for state in scenario.player("alice").library] == ["Lightning Bolt"]
    assert scenario.game.exile == []


def test_zoetic_glyph_discovers_3_when_put_into_the_graveyard_from_the_battlefield():
    """Zoetic Glyph: "When this Aura is put into a graveyard from the
    battlefield, discover 3." - a leaves-the-battlefield trigger, the third
    trigger shape this clause parser has to read identically."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Zoetic Glyph"],
            library=["Lightning Bolt"],
            battlefield=["Mind Stone", "Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mind_stone = scenario.find("Mind Stone", Zone.BATTLEFIELD)
    sources = scenario.untapped_sources("Island", "Island", "Island", username="alice")

    glyph = scenario.cast_and_resolve("Zoetic Glyph", *sources, targets=[mind_stone])
    assert glyph.zone is Zone.BATTLEFIELD

    scenario.game.destroy(glyph)
    scenario.game.check_state_based_actions()
    assert glyph.zone is Zone.GRAVEYARD
    _resolve_the_trigger(scenario)

    bolt = scenario.find("Lightning Bolt", Zone.STACK)
    assert bolt.zone is Zone.STACK
