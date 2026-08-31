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

Four real printings carry one: Tarmogoyf counts card types in every graveyard
(CR 300.1), Boneyard Wurm counts creature cards in its own controller's
graveyard only, Nighthawk Scavenger counts card types in every graveyard
*except* its own controller's, and Allosaurus Rider counts lands on the
battlefield. The first three read a zone the layer engine never sees, which is
what `LayerContext` is for; the last reads the board as layers 1-6 left it.

Most of this file asks the layer engine directly about a board the scenario
harness built. The section headed "`Game` threads the graveyards through" asks
`Game.power_of` / `Game.computed_board()` instead - that boundary is exactly
where this suite once went wrong: `Game.computed_board()` called
`continuous_effects.board(...)` with no `LayerContext` at all, so every
graveyard-reading CDA was built against an empty world and a Tarmogoyf over a
full graveyard still came back a static 0/1. Every CR number here was looked up
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
    """Every card in every graveyard, which is the number Tarmogoyf counts -
    and each player's own, which is the number Boneyard Wurm counts."""
    return LayerContext(
        graveyards=tuple(card for player in scenario.game.players for card in player.graveyard),
        graveyard_by_controller={
            player.username: tuple(player.graveyard) for player in scenario.game.players
        },
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
# `Game` threads the graveyards through
# --------------------------------------------------------------------------
#
# Everything above hands `LayerContext` to the layer engine by hand. These ask
# `Game.power_of` / `Game.toughness_of` / `Game.computed_board()` instead -
# the real path combat, state-based actions, and targeting all use - to prove
# `Game.computed_board()` itself builds the `LayerContext`, not just the
# harness. `Game` still does not consult the layer engine for
# `CardState.power`/`.toughness` themselves (see "Gaps" below); this is about
# the questions `Game` *does* answer through it.


def test_game_power_of_is_not_a_static_zero_one_over_a_real_graveyard():
    """The defect this section exists to catch, stated directly.

    `Game.computed_board()` used to call `continuous_effects.board(...)` with
    no `LayerContext`, so a Tarmogoyf's CDA was built against an empty
    graveyard whatever was actually in one - `game.power_of` came back 0 over
    a graveyard holding a Lightning Bolt, when CR 613.4a says it should be 1.
    """
    scenario = (
        Scenario().player("alice", battlefield=["Tarmogoyf"], graveyard=["Lightning Bolt"]).build()
    )
    goyf = scenario.creature("Tarmogoyf", "alice")

    assert scenario.game.power_of(goyf) == 1
    assert scenario.game.toughness_of(goyf) == 2


def test_game_power_of_over_an_empty_graveyard_is_still_zero_one():
    """The other end of the same check: no graveyard, no card types, 0/1 -
    not `None`, because the CDA still applies in 7a (CR 613.4a)."""
    scenario = Scenario().player("alice", battlefield=["Tarmogoyf"]).build()
    goyf = scenario.creature("Tarmogoyf", "alice")

    assert scenario.game.power_of(goyf) == 0
    assert scenario.game.toughness_of(goyf) == 1


def test_game_power_of_counts_both_players_graveyards():
    """`Game.computed_board()` gathers every graveyard in the game, not just
    the Goyf's controller's - the same "all graveyards" as the direct tests
    above, now asked through `Game`."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tarmogoyf"], graveyard=["Lightning Bolt"])
        .player("bob", graveyard=["Grizzly Bears", "Forest"])
        .build()
    )
    goyf = scenario.creature("Tarmogoyf", "alice")

    assert scenario.game.power_of(goyf) == 3


def test_a_goyf_growing_mid_game_changes_the_damage_it_deals_in_combat():
    """CR 613.5's "continually and automatically" through the real combat path.

    An empty-graveyard Goyf is a harmless 0/1 and could not profitably attack;
    once a Bolt and the creature it killed are both in a graveyard it is a
    2/3, and unblocked combat damage - which `machines/combat.py` computes by
    calling `Game.power_of` - takes bob from 20 to 18.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain", "Tarmogoyf"])
        .player("bob", life=20, battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goyf = scenario.creature("Tarmogoyf", "alice")
    assert scenario.game.power_of(goyf) == 0

    bears = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.game.power_of(goyf) == 2, "an instant and a creature, two card types"

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(goyf)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 18


def test_a_goyf_the_graveyards_grew_dies_to_dismember_through_state_based_actions():
    """The `compute_board`-only version of this earlier in the file, now
    played all the way through `Game` (CR 704.5f).

    Four card types make the Goyf a 4/5; Dismember's -5/-5 takes its computed
    toughness to 0, and `Game.check_state_based_actions` - which asks
    `Game.computed_board()` for that number, not `CardState.toughness` - puts
    it in the graveyard without anyone calling combat or a Dismember-specific
    check.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dismember"],
            battlefield=["Swamp", "Tarmogoyf"],
            graveyard=["Lightning Bolt", "Grizzly Bears", "Forest", "Sol Ring"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goyf = scenario.creature("Tarmogoyf", "alice")
    assert scenario.game.power_of(goyf) == 4

    (swamp,) = scenario.untapped_sources("Swamp", username="alice")
    scenario.cast_and_resolve("Dismember", swamp, username="alice", targets=[goyf])

    assert goyf.zone is Zone.GRAVEYARD


def test_lifelink_combat_damage_gains_life_equal_to_the_cdas_computed_power():
    """An effect that reads the CDA's *computed* power, not a cached one
    (CR 702.15b, CR 613.4a).

    Nighthawk Scavenger prints its own lifelink (CR 702.15a), so unblocked
    combat damage - `machines/combat.py` computes it by calling `Game.power_of`
    - both hits bob for the CDA's live answer and gains alice exactly that much
    life, proving the life total change tracks `Game.power_of` rather than the
    printed `1+*` on the card.
    """
    scenario = (
        Scenario()
        .player("alice", life=20, battlefield=["Nighthawk Scavenger"])
        .player("bob", life=20, graveyard=["Lightning Bolt", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    hawk = scenario.creature("Nighthawk Scavenger", "alice")
    assert scenario.game.power_of(hawk) == 3, "1 plus two card types in bob's own graveyard"

    scenario.attack_with(hawk)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 23


# --------------------------------------------------------------------------
# Boneyard Wurm: a CDA that counts only its own controller's graveyard
# --------------------------------------------------------------------------
#
# Tarmogoyf's graveyard count is the same number for every permanent that asks
# - it does not matter who controls the Goyf. Boneyard Wurm's is not: "your
# graveyard" is a different zone for every controller, which is exactly the
# shape `LayerContext.your_graveyard` cannot answer for a static ability
# shared across a whole battlefield (see its docstring) - that gap is what
# `LayerContext.graveyard_by_controller` and `graveyard_of` are for.


def test_boneyard_wurm_counts_creature_cards_not_card_types():
    """ "the number of creature cards in your graveyard" - a Bolt and a
    Counterspell in the bin are zero creature cards, whatever `count_card_types`
    would make of them."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Boneyard Wurm"],
            graveyard=["Lightning Bolt", "Counterspell", "Grizzly Bears"],
        )
        .build()
    )
    wurm = scenario.creature("Boneyard Wurm", "alice")

    assert scenario.game.power_of(wurm) == 1
    assert scenario.game.toughness_of(wurm) == 1


def test_boneyard_wurm_does_not_count_the_opponents_graveyard():
    """ "your graveyard" - unlike Tarmogoyf, the opponent's creature cards are
    not the Wurm's to count."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Boneyard Wurm"])
        .player("bob", graveyard=["Grizzly Bears"])
        .build()
    )
    wurm = scenario.creature("Boneyard Wurm", "alice")

    assert scenario.game.power_of(wurm) == 0


def test_boneyard_wurm_and_tarmogoyf_read_different_graveyards_on_one_board():
    """Both CDAs share sublayer 7a on the same battlefield, one counting every
    graveyard and the other counting only its own controller's - proof
    `Game.computed_board()`'s single `LayerContext` answers both questions at
    once rather than picking one meaning of "graveyard" for everybody."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tarmogoyf", "Boneyard Wurm"],
            graveyard=["Grizzly Bears"],
        )
        .player("bob", graveyard=["Lightning Bolt", "Forest"])
        .build()
    )
    goyf = scenario.creature("Tarmogoyf", "alice")
    wurm = scenario.creature("Boneyard Wurm", "alice")

    assert scenario.game.power_of(goyf) == 3, "creature, instant, land - three types, both bins"
    assert scenario.game.power_of(wurm) == 1, "one creature card, alice's bin only"


# --------------------------------------------------------------------------
# Nighthawk Scavenger: a third graveyard-reading CDA, and one that defines
# only power
# --------------------------------------------------------------------------
#
# Tarmogoyf reads every graveyard; Boneyard Wurm reads only its own
# controller's. Nighthawk Scavenger reads the third possible answer -
# everyone's graveyard *except* its own controller's - which
# `LayerContext.opponents_graveyard_of` derives from the other two rather than
# needing a fourth stored field. Its toughness is a plain printed `3`, not a
# `*` (CR 208.1), so this is also the only card in the pool whose CDA defines
# power alone (`define_power`) rather than both halves at once.


def test_nighthawk_scavengers_toughness_is_the_printed_number_not_a_cda():
    """CR 208.2a's ability is worded about power only - "Nighthawk Scavenger's
    *power* is equal to ..." - so toughness never enters 7a at all and stays
    the printed 3 whatever the graveyards hold."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Nighthawk Scavenger"])
        .player("bob", graveyard=["Lightning Bolt", "Grizzly Bears", "Forest", "Sol Ring"])
        .build()
    )
    hawk = scenario.creature("Nighthawk Scavenger", "alice")

    assert scenario.game.toughness_of(hawk) == 3


def test_nighthawk_scavenger_does_not_count_its_own_controllers_graveyard():
    """ "your opponents' graveyards" - the reverse of Boneyard Wurm's "your
    graveyard": alice's own bin is exactly the one bin that does not count."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Nighthawk Scavenger"],
            graveyard=["Lightning Bolt", "Grizzly Bears", "Forest"],
        )
        .build()
    )
    hawk = scenario.creature("Nighthawk Scavenger", "alice")

    assert scenario.game.power_of(hawk) == 1, "1 plus zero - alice's own graveyard doesn't count"


def test_nighthawk_scavenger_counts_every_opponent_in_a_multiplayer_game():
    """ "your opponents' graveyards", plural - in a three-player game that is
    two bins, not one."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Nighthawk Scavenger"])
        .player("bob", graveyard=["Lightning Bolt"])
        .player("carol", graveyard=["Grizzly Bears", "Forest"])
        .build()
    )
    hawk = scenario.creature("Nighthawk Scavenger", "alice")

    assert scenario.game.power_of(hawk) == 4, "1 plus three types across bob's and carol's bins"


def test_all_three_graveyard_reading_cdas_coexist_on_one_board():
    """Tarmogoyf (every graveyard), Boneyard Wurm (your own), and Nighthawk
    Scavenger (your opponents') all in sublayer 7a at once, each computed off
    the one `LayerContext` `Game.computed_board()` built - proof the three
    derived views (`graveyards`, `graveyard_of`, `opponents_graveyard_of`)
    disagree with each other exactly where the cards themselves do."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tarmogoyf", "Boneyard Wurm", "Nighthawk Scavenger"],
            graveyard=["Grizzly Bears"],
        )
        .player("bob", graveyard=["Lightning Bolt", "Forest"])
        .build()
    )
    goyf = scenario.creature("Tarmogoyf", "alice")
    wurm = scenario.creature("Boneyard Wurm", "alice")
    hawk = scenario.creature("Nighthawk Scavenger", "alice")

    assert scenario.game.power_of(goyf) == 3, "creature, instant, land - both bins"
    assert scenario.game.power_of(wurm) == 1, "one creature card - alice's bin only"
    assert scenario.game.power_of(hawk) == 3, "1 plus two types - bob's bin only"


# --------------------------------------------------------------------------
# Gaps
# --------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="measured: models/card_state.py has the hook now - `CardState.bind_to_game` "
    "makes `.power`/`.toughness` answer with `Game.characteristics_of` for a permanent on "
    "the battlefield, and a bound Goyf reads 2/3 off layer 7a (see "
    "tests/scenarios/test_card_state_computed_characteristics.py). Nothing calls it: "
    "models/game.py never binds a CardState to the game it is in, so every object in a "
    "real game is unbound and falls back to the printed value plus counters, and a "
    "printed `*` is not a number. One `state.bind_to_game(self)` in Game's own "
    "battlefield-entry path (`Game.enter_the_battlefield`) is the whole remainder.",
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
