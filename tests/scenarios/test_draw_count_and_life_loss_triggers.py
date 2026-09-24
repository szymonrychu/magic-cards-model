"""Scenario: life-loss triggers and second-draw-each-turn triggers.

CR 119.3: "If an effect causes a player to gain life or lose life, that
player's life total is adjusted accordingly." Every life loss - combat
damage, a burn spell, an exchange of life totals - is one and the same event
a trigger watching "a player loses life" reads (`TriggerEvent.LOSES_LIFE`,
wired into `machines/triggers.py`'s condition matcher for the first time
here), carrying how much was lost (`GameEvent.amount`) for "that many" to
read (`that_many`, CR 607.1's anaphora onto the triggering event).

The Master of Lake-town: "Whenever a player loses life, that player mills
that many cards." (CR 701.17a's mill) and "When The Master of Lake-town
dies, draw a card for each graveyard with seven or more cards in it." (CR
700.4's dies, CR 400.1's every player's own graveyard).

Gleaming Splendor: "Whenever an opponent draws their second card each turn,
you create a Treasure token." (the same "an opponent"/"their" widening of
`_NTH_DRAW_CONDITION` `test_recruit.py`'s Queen of Dale exercises for
casting, here for drawing) and "{2}{W}: Two target players each draw a
card." (CR 115.6's exact-count target profile, repeated once per legal
target - `_parse_n_target_players_each_draw_clause`).

Off-pool proofs: Mindcrank ("Whenever an opponent loses life, that player
mills that many cards.") for the life-loss mill template, and Faerie
Mastermind ("Whenever an opponent draws their second card each turn, you
draw a card.") for the second-draw template - both real Modern-legal
printings outside the deck pool.
"""

from magic_cards_model.machines import Step

from .harness import Scenario


def resolve_all(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


# -- The Master of Lake-town -------------------------------------------------


def test_a_player_losing_life_mills_that_many_cards():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Master of Lake-town"],
            library=["Island"] * 10,
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=["alice"],
    )
    resolve_all(scenario)

    assert len(scenario.player("alice").graveyard) == 3, "3 damage lost 3 life, mills 3 cards"


def test_the_opponent_who_lost_life_is_the_one_who_mills_not_the_controller():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Master of Lake-town"],
            library=["Island"] * 10,
        )
        .player("bob", library=["Forest"] * 10, battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.deal_damage_to_player("bob", 2)
    resolve_all(scenario)

    assert len(scenario.player("bob").graveyard) == 2
    assert len(scenario.player("alice").graveyard) == 0


def test_the_master_of_lake_towns_death_draws_a_card_per_full_graveyard():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Master of Lake-town"],
            graveyard=["Island"] * 7,
            library=["Forest"] * 3,
        )
        .player("bob", graveyard=["Mountain"] * 8, library=["Swamp"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    master = scenario.creature("The Master of Lake-town", "alice")
    hand_before = len(scenario.player("alice").hand)

    scenario.game.destroy(master)
    resolve_all(scenario)

    # Both graveyards have seven or more cards - alice draws two.
    assert len(scenario.player("alice").hand) == hand_before + 2


def test_the_master_of_lake_towns_death_draws_nothing_with_no_full_graveyard():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Master of Lake-town"],
            graveyard=["Island"] * 3,
            library=["Forest"] * 3,
        )
        .player("bob", library=["Swamp"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    master = scenario.creature("The Master of Lake-town", "alice")
    hand_before = len(scenario.player("alice").hand)

    scenario.game.destroy(master)
    resolve_all(scenario)

    assert len(scenario.player("alice").hand) == hand_before


def test_mindcrank_reads_the_identical_life_loss_mill_template():
    """Off-pool proof: Mindcrank's own "Whenever an opponent loses life,
    that player mills that many cards." - the "an opponent" form rather
    than The Master of Lake-town's plain "a player"."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mindcrank"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"], library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=["alice"],
    )
    resolve_all(scenario)

    # bob is the *caster* here, not who lost life - the event's own subject
    # is alice, so alice mills, proving "an opponent" reads relative to
    # Mindcrank's own controller.
    assert len(scenario.player("alice").graveyard) == 0
    graveyard_before = len(scenario.player("bob").graveyard)  # Lightning Bolt is already there
    scenario.game.deal_damage_to_player("bob", 3)
    resolve_all(scenario)
    assert len(scenario.player("bob").graveyard) == graveyard_before + 3


# -- Gleaming Splendor --------------------------------------------------------


def test_an_opponents_second_draw_each_turn_creates_a_treasure():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Gleaming Splendor"])
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.draw(1, username="bob")
    resolve_all(scenario)
    assert not any(state.name == "Treasure Token" for state in scenario.game.battlefield)

    scenario.draw(1, username="bob")
    resolve_all(scenario)

    treasure = [state for state in scenario.game.battlefield if state.name == "Treasure Token"]
    assert len(treasure) == 1
    assert treasure[0].controller == "alice"


def test_the_controllers_own_second_draw_does_not_trigger_it():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Gleaming Splendor"], library=["Island"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.draw(1)
    scenario.draw(1)
    resolve_all(scenario)

    assert not any(state.name == "Treasure Token" for state in scenario.game.battlefield)


def test_two_target_players_each_draw_a_card():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Gleaming Splendor", "Plains", "Plains", "Plains"],
            library=["Island"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    splendor = scenario.creature("Gleaming Splendor", "alice")
    hand_before_alice = len(scenario.player("alice").hand)
    hand_before_bob = len(scenario.player("bob").hand)

    scenario.activate(
        splendor, *scenario.untapped_sources("Plains", "Plains", "Plains"), targets=["alice", "bob"]
    )
    resolve_all(scenario)

    assert len(scenario.player("alice").hand) == hand_before_alice + 1
    assert len(scenario.player("bob").hand) == hand_before_bob + 1


def test_faerie_mastermind_reads_the_identical_second_draw_template():
    """Off-pool proof: Faerie Mastermind's own "Whenever an opponent draws
    their second card each turn, you draw a card." - the identical ordinal
    reader, a different effect (draw, not create a Treasure)."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Faerie Mastermind"], library=["Forest"] * 5)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hand_before = len(scenario.player("alice").hand)

    scenario.draw(1, username="bob")
    resolve_all(scenario)
    assert len(scenario.player("alice").hand) == hand_before

    scenario.draw(1, username="bob")
    resolve_all(scenario)

    assert len(scenario.player("alice").hand) == hand_before + 1


# -- life loss that is not damage (CR 119.3, CR 119.4) ------------------------


def test_life_lost_to_an_effect_triggers_the_life_loss_mill():
    """CR 119.3: an effect that makes a player lose life is life loss as much
    as damage is - Sign in Blood's "loses 2 life" mills two."""
    scenario = (
        Scenario()
        .player("alice", hand=["Sign in Blood"], battlefield=["Mindcrank", "Swamp", "Swamp"])
        .player("bob", library=["Forest"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack(
        "Sign in Blood",
        *scenario.untapped_sources("Swamp", "Swamp"),
        targets=["bob"],
    )
    resolve_all(scenario)

    graveyard = [card.name for card in scenario.player("bob").graveyard]
    assert graveyard.count("Forest") == 2, graveyard


def test_paid_life_triggers_the_life_loss_mill():
    """CR 119.4: "If a player pays life, the payment is subtracted from their
    life total; in other words, the player loses that much life.\""""
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Master of Lake-town"], library=["Island"] * 10)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_pay_the_life(username="alice")
    assert scenario.game.may_pay_life("alice", 2, source="a test payment")
    resolve_all(scenario)

    assert len(scenario.player("alice").graveyard) == 2
