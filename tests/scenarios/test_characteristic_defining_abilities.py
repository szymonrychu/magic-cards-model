"""Scenario: characteristic-defining abilities that define power and toughness.

CR 604.3 and CR 604.3a: "A static ability is a characteristic-defining ability
if it meets the following criteria: (1) It defines an object's colors, subtypes,
power, or toughness; (2) it is printed on the card it affects ...". CR 208.2a is
the printed side of the same thing - a card whose power box reads `*` carries an
ability worded "[This creature's] [power or toughness] is equal to ...".

They are not ordinary power/toughness effects. CR 613.4a gives them a sublayer
of their own, *before* everything else in layer 7: "Layer 7a: Effects from
characteristic-defining abilities that define power and/or toughness are
applied." So a CDA always loses to a later 7b that sets a value and always
underlies a 7c that adds one, whatever the timestamps say (CR 613.7).

Two real printings carry one: Tarmogoyf counts card types in every graveyard
(CR 300.1), and Allosaurus Rider counts lands on the battlefield. The first
reads a zone the layer engine never sees, which is what `LayerContext` is for;
the second reads the board as layers 1-6 left it.

`Game` does not consult `machines/layers.py`, so these ask the layer engine
about a board the scenario harness built. Every CR number here was looked up
with `knowledge_search(type="rules")`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers import (
    LayerContext,
    compute_board,
    effects_for,
    printed_characteristics,
    static_effects,
)
from magic_cards_model.models import Zone
from tests.cards import card_state
from tests.scenarios.harness import Scenario


def permanent(name: str, controller: str = "alice"):
    return card_state(name, zone=Zone.BATTLEFIELD, controller=controller)


def graveyards_of(scenario) -> LayerContext:
    """Every card in every graveyard, which is the number Tarmogoyf counts."""
    return LayerContext(
        graveyards=tuple(card for player in scenario.game.players for card in player.graveyard)
    )


# --------------------------------------------------------------------------
# The number the ability names
# --------------------------------------------------------------------------


def test_a_star_power_has_no_value_until_the_ability_defines_it():
    """CR 208.2: "some creature cards have power and/or toughness that includes a star".

    Nothing is printed there to read, so the printed characteristics carry no
    number at all and layer 7a is the only thing that can supply one.
    """
    goyf = permanent("Tarmogoyf")

    assert goyf.card.power == "*"
    assert printed_characteristics(goyf).power_toughness == (None, None)


def test_tarmogoyf_with_every_graveyard_empty_is_a_zero_one():
    """Zero card types is still a number: 0 power and 0 plus 1 toughness.

    The CDA applies in 7a (CR 613.4a) whatever it counts, so the answer is a
    defined 0/1 rather than the undefined None a card with no CDA would have.
    """
    scenario = Scenario().player("alice", battlefield=["Tarmogoyf"]).build()
    goyf = scenario.creature("Tarmogoyf", "alice")

    board = compute_board(
        scenario.game.battlefield,
        static_effects(scenario.game.battlefield, graveyards_of(scenario)),
    )

    assert board.of(goyf).power_toughness == (0, 1)


def test_tarmogoyf_counts_card_types_and_not_cards():
    """CR 300.1 lists the card types; the ability counts *types*, not cards.

    Three instants in a graveyard are one card type between them, so the Goyf
    is a 1/2 - the mistake this test exists to catch is counting to three.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tarmogoyf"],
            graveyard=["Lightning Bolt", "Counterspell", "Twisted Image"],
        )
        .build()
    )
    goyf = scenario.creature("Tarmogoyf", "alice")

    board = compute_board(
        scenario.game.battlefield,
        static_effects(scenario.game.battlefield, graveyards_of(scenario)),
    )

    assert board.of(goyf).power_toughness == (1, 2)


def test_the_count_is_across_all_graveyards_not_just_your_own():
    """ "among cards in all graveyards" - the opponent's bin counts too.

    Alice's graveyard has an instant, Bob's has a creature and a land. Three
    types, so a 3/4.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tarmogoyf"], graveyard=["Lightning Bolt"])
        .player("bob", graveyard=["Grizzly Bears", "Forest"])
        .build()
    )
    goyf = scenario.creature("Tarmogoyf", "alice")

    board = compute_board(
        scenario.game.battlefield,
        static_effects(scenario.game.battlefield, graveyards_of(scenario)),
    )

    assert board.of(goyf).power_toughness == (3, 4)


def test_one_card_with_two_types_counts_for_both():
    """CR 300.2: an object with more than one card type "combines the aspects of
    each of those card types".

    Dryad Arbor is a Land Creature, so on its own in a graveyard it is two of
    Tarmogoyf's card types and makes it a 2/3.
    """
    scenario = (
        Scenario().player("alice", battlefield=["Tarmogoyf"], graveyard=["Dryad Arbor"]).build()
    )
    goyf = scenario.creature("Tarmogoyf", "alice")

    board = compute_board(
        scenario.game.battlefield,
        static_effects(scenario.game.battlefield, graveyards_of(scenario)),
    )

    assert board.of(goyf).power_toughness == (2, 3)


def test_a_card_reaching_the_graveyard_moves_the_number():
    """CR 613.5: "continually and automatically performed by the game".

    Nothing is cached, so the Goyf grows the moment a Bolt that killed something
    lands in a graveyard - and the same board recomputed before and after gives
    two different answers off the same `CardState`.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain", "Tarmogoyf"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goyf = scenario.creature("Tarmogoyf", "alice")

    before = compute_board(
        scenario.game.battlefield,
        static_effects(scenario.game.battlefield, graveyards_of(scenario)),
    )
    assert before.of(goyf).power_toughness == (0, 1)

    bears = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])
    assert bears.zone is Zone.GRAVEYARD

    after = compute_board(
        scenario.game.battlefield,
        static_effects(scenario.game.battlefield, graveyards_of(scenario)),
    )
    assert after.of(goyf).power_toughness == (2, 3), "an instant and a creature"


# --------------------------------------------------------------------------
# Where 7a sits among the other sublayers
# --------------------------------------------------------------------------


def test_a_counter_adds_on_top_of_the_defined_value():
    """7a before 7c (CR 613.4a, CR 613.4c).

    The CDA defines a 1/2 and the +1/+1 counter then modifies it to a 2/3.
    Reverse the two and the counter would be overwritten instead of added.
    """
    scenario = (
        Scenario().player("alice", battlefield=["Tarmogoyf"], graveyard=["Lightning Bolt"]).build()
    )
    goyf = scenario.creature("Tarmogoyf", "alice")
    goyf.add_counters("+1/+1", 1)

    board = compute_board(
        scenario.game.battlefield,
        static_effects(scenario.game.battlefield, graveyards_of(scenario)),
    )

    assert board.of(goyf).power_toughness == (2, 3)


def test_humility_overwrites_a_characteristic_defining_ability():
    """7a before 7b (CR 613.4a, CR 613.4b), and layer 6 does not come into it.

    Humility strips every creature's abilities in layer 6, so by 7a Tarmogoyf's
    CDA no longer exists and is skipped (CR 613.6, read the other way: an effect
    that has *not* started applying and whose ability has gone never applies).
    Humility's own base 1/1 then lands in 7b. Either route gives 1/1 here, which
    is why the journal is the assertion that matters.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tarmogoyf", "Humility"],
            graveyard=["Lightning Bolt", "Grizzly Bears"],
        )
        .build()
    )
    goyf = scenario.creature("Tarmogoyf", "alice")

    board = compute_board(
        scenario.game.battlefield,
        static_effects(scenario.game.battlefield, graveyards_of(scenario)),
    )

    assert board.of(goyf).power_toughness == (1, 1)
    assert any("Tarmogoyf" in skipped for skipped in board.journal.skipped)


def test_dress_down_leaves_tarmogoyf_with_no_value_at_all():
    """Layer 6 before layer 7 (CR 613.1f, CR 613.1g), then CR 208.5.

    Dress Down removes the CDA in layer 6, so nothing defines either half in 7a
    and Tarmogoyf has *no value* for power or toughness. CR 208.5: "If a
    creature somehow has no value for its power, its power is 0. The same is
    true for toughness." A 0/0 - not the 0/1 an empty graveyard would give,
    because the "plus 1" was part of the ability that is gone.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tarmogoyf", "Dress Down"],
            graveyard=["Lightning Bolt", "Grizzly Bears", "Forest"],
        )
        .build()
    )
    goyf = scenario.creature("Tarmogoyf", "alice")

    board = compute_board(
        scenario.game.battlefield,
        static_effects(scenario.game.battlefield, graveyards_of(scenario)),
    )

    assert board.of(goyf).power_toughness == (None, None)
    assert board.of(goyf).numeric_power_toughness == (0, 0)


def test_a_pump_still_lands_on_a_goyf_whose_ability_was_removed():
    """CR 208.5 again, from the other side: 0 is a number a 7c effect can add to.

    Dress Down takes the CDA away, so 7a writes nothing, and Giant Growth's
    +3/+3 in 7c (CR 613.4c) finds no value and treats it as 0 - a 3/3.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tarmogoyf", "Dress Down"], graveyard=["Lightning Bolt"])
        .build()
    )
    goyf = scenario.creature("Tarmogoyf", "alice")
    growth = card_state("Giant Growth", zone=Zone.STACK, controller="alice")

    effects = static_effects(scenario.game.battlefield, graveyards_of(scenario))
    effects += effects_for(growth, timestamp=9, targets=[goyf])
    board = compute_board(scenario.game.battlefield, effects)

    assert board.of(goyf).power_toughness == (3, 3)


def test_dismember_can_kill_a_goyf_the_graveyards_had_grown():
    """7a then 7c, with the arithmetic that decides whether it dies (CR 704.5f).

    Four card types make a 4/5; Dismember's -5/-5 in 7c takes it to -1/0, and a
    creature with toughness 0 or less is put into its owner's graveyard.
    `Game` does not consult the layer engine, so the state-based action itself
    is out of reach here - the assertion is the toughness the rule would read.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tarmogoyf"],
            graveyard=["Lightning Bolt", "Grizzly Bears", "Forest", "Sol Ring"],
        )
        .build()
    )
    goyf = scenario.creature("Tarmogoyf", "alice")
    dismember = card_state("Dismember", zone=Zone.STACK, controller="alice")

    effects = static_effects(scenario.game.battlefield, graveyards_of(scenario))
    effects += effects_for(dismember, timestamp=9, targets=[goyf])
    board = compute_board(scenario.game.battlefield, effects)

    assert board.of(goyf).power_toughness == (-1, 0)


# --------------------------------------------------------------------------
# A CDA that reads the board
# --------------------------------------------------------------------------


def test_allosaurus_rider_counts_the_lands_on_the_battlefield():
    """The other CDA in the pool, and the one 7a computes from the board.

    "Allosaurus Rider's power and toughness are each equal to 1 plus the number
    of lands you control." Three lands makes a 4/4.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Allosaurus Rider", "Forest", "Forest", "Mountain"])
        .build()
    )
    rider = scenario.creature("Allosaurus Rider", "alice")

    board = compute_board(scenario.game.battlefield, static_effects(scenario.game.battlefield))

    assert board.of(rider).power_toughness == (4, 4)


def test_only_the_lands_you_control_count():
    """ "lands you control" - the opponent's four Forests are not the Rider's."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Allosaurus Rider", "Forest"])
        .player("bob", battlefield=["Forest", "Forest", "Forest", "Forest"])
        .build()
    )
    rider = scenario.creature("Allosaurus Rider", "alice")

    board = compute_board(scenario.game.battlefield, static_effects(scenario.game.battlefield))

    assert board.of(rider).power_toughness == (2, 2)


def test_a_land_creature_is_counted_by_both_abilities_at_once():
    """Dryad Arbor is a Land Creature, so it is one of the Rider's lands.

    It is also a creature, which is the reason this is worth a test: the
    selector asks whether it is a land (CR 613.1d types, as layers 1-6 left
    them), not whether it is *only* a land.
    """
    scenario = Scenario().player("alice", battlefield=["Allosaurus Rider", "Dryad Arbor"]).build()
    rider = scenario.creature("Allosaurus Rider", "alice")

    board = compute_board(scenario.game.battlefield, static_effects(scenario.game.battlefield))

    assert board.of(rider).power_toughness == (2, 2)


def test_two_characteristic_defining_abilities_do_not_interfere():
    """Both sit in 7a and neither reads the other's number (CR 613.4a).

    They share a sublayer, so CR 613.8a would ask about dependency - but clause
    (c) refuses to pair two effects unless both or neither are characteristic-
    defining, and even here, where both are, neither changes what the other
    counts. Timestamp order decides and the answers are independent.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tarmogoyf", "Allosaurus Rider", "Forest"],
            graveyard=["Lightning Bolt"],
        )
        .build()
    )
    goyf = scenario.creature("Tarmogoyf", "alice")
    rider = scenario.creature("Allosaurus Rider", "alice")

    board = compute_board(
        scenario.game.battlefield,
        static_effects(scenario.game.battlefield, graveyards_of(scenario)),
    )

    assert board.of(goyf).power_toughness == (1, 2)
    assert board.of(rider).power_toughness == (2, 2)
    assert board.journal.cycles == []


# --------------------------------------------------------------------------
# Gaps
# --------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="Game.power_of / Game.toughness_of ask machines/layers.py now, so the game can "
    "see a Goyf's power. This asserts on CardState.power/.toughness, which are still the "
    "printed value plus counters, and a printed `*` is not a number - models/card_state.py "
    "is where that would change.",
)
def test_the_game_agrees_with_the_layer_engine_about_a_goyfs_power():
    """The integration this file works around, stated as a test.

    Combat and the state-based actions read `CardState.power`/`.toughness`,
    which know about counters (CR 122.1a) and nothing else. Until `Game` asks
    the layer engine, a Tarmogoyf on a real board has no power the game can see.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tarmogoyf"], graveyard=["Lightning Bolt", "Forest"])
        .build()
    )
    goyf = scenario.creature("Tarmogoyf", "alice")

    assert (goyf.power, goyf.toughness) == (2, 3)
