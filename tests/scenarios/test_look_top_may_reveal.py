"""CR 401.2 / CR 701.20: "Look at the top card of your library. You may
reveal that card [if <condition>][ and put it into your hand]. If you do,
<effect>[ and put it into your hand]. [If you don't reveal it, put it into
your hand.]"

The look is private (CR 701.20e), the reveal public (CR 701.20a), and the
"if you do" effect reads the revealed card back through "its" (its colors,
its mana value). Two printings with different conditions, effects and put
positions:

- Omnath, Locus of All's first-main-phase trigger: the reveal is allowed
  only "if it has three or more colored mana symbols in its mana cost" (a
  hybrid symbol is one colored symbol - the printing's ruling counts
  {R/G}{G}{G/W} as three); revealing adds three mana in any combination of
  its colors; the card goes to hand either way.
- Sorin the Mirthless's `+1`: no condition; the put is part of the reveal
  ("You may reveal that card and put it into your hand"), and "if you do,
  you lose life equal to its mana value". Declined, the card stays on top.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _to_first_main(scenario) -> None:
    scenario.advance()  # untap -> upkeep
    scenario.advance()  # upkeep -> precombat main (CR 103.8a: no draw on turn 1)


def test_omnath_reveals_a_three_symbol_card_adds_three_of_its_colours_and_draws_it():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Omnath, Locus of All"],
            library=["Omnath, Locus of Creation", "Forest"],
        )
        .player("bob")
        .build()
    )
    (creation,) = scenario.top_of_library(1, username="alice")
    scenario.will_take_the_may(True, username="alice", source="Omnath, Locus of All")
    scenario.will_choose(Color.RED.value, username="alice", source="Omnath, Locus of All")
    scenario.will_choose(Color.GREEN.value, username="alice", source="Omnath, Locus of All")
    scenario.will_choose(Color.BLUE.value, username="alice", source="Omnath, Locus of All")

    _to_first_main(scenario)
    scenario.pass_until_resolved()

    assert creation.zone is Zone.HAND
    assert scenario.game.player("alice").mana_pool.floating == {
        Color.RED: 1,
        Color.GREEN: 1,
        Color.BLUE: 1,
    }


def test_omnath_counts_a_hybrid_symbol_as_one_colored_symbol():
    """Boros Reckoner's {R/W}{R/W}{R/W} is three colored symbols, and its
    colors are red and white."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Omnath, Locus of All"],
            library=["Boros Reckoner", "Forest"],
        )
        .player("bob")
        .build()
    )
    (reckoner,) = scenario.top_of_library(1, username="alice")
    scenario.will_take_the_may(True, username="alice", source="Omnath, Locus of All")
    scenario.will_choose(Color.WHITE.value, username="alice", source="Omnath, Locus of All")
    scenario.will_choose(Color.WHITE.value, username="alice", source="Omnath, Locus of All")
    scenario.will_choose(Color.RED.value, username="alice", source="Omnath, Locus of All")

    _to_first_main(scenario)
    scenario.pass_until_resolved()

    assert reckoner.zone is Zone.HAND
    assert scenario.game.player("alice").mana_pool.floating == {Color.WHITE: 2, Color.RED: 1}


def test_omnath_cannot_reveal_a_two_symbol_card_and_still_puts_it_into_hand():
    """Lightning Helix has two colored symbols: no reveal, no mana, and "If
    you don't reveal it, put it into your hand." - no question either."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Omnath, Locus of All"],
            library=["Lightning Helix", "Forest"],
        )
        .player("bob")
        .build()
    )
    (helix,) = scenario.top_of_library(1, username="alice")

    _to_first_main(scenario)
    scenario.pass_until_resolved()

    assert helix.zone is Zone.HAND
    assert scenario.game.player("alice").mana_pool.floating == {}
    assert not [
        decision
        for decision in scenario.questions_asked()
        if decision.source == "Omnath, Locus of All"
    ]


def test_omnath_declining_the_reveal_still_puts_the_card_into_hand():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Omnath, Locus of All"],
            library=["Cryptic Command", "Forest"],
        )
        .player("bob")
        .build()
    )
    (command,) = scenario.top_of_library(1, username="alice")
    scenario.will_take_the_may(False, username="alice", source="Omnath, Locus of All")

    _to_first_main(scenario)
    scenario.pass_until_resolved()

    assert command.zone is Zone.HAND
    assert scenario.game.player("alice").mana_pool.floating == {}


def test_omnaths_mana_turns_black_as_the_main_phase_ends():
    """The two abilities of the card together: Cryptic Command's {U}{U}{U}
    is not lost at the end of the main phase, it becomes black."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Omnath, Locus of All"],
            library=["Cryptic Command", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.will_take_the_may(True, username="alice", source="Omnath, Locus of All")

    _to_first_main(scenario)
    scenario.pass_until_resolved()
    assert scenario.game.player("alice").mana_pool.floating == {Color.BLUE: 3}
    scenario.advance()

    assert scenario.game.player("alice").mana_pool.floating == {Color.BLACK: 3}


def test_omnath_with_an_empty_library_does_nothing():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Omnath, Locus of All"], library=[])
        .player("bob")
        .build()
    )

    _to_first_main(scenario)
    scenario.pass_until_resolved()

    assert scenario.game.player("alice").mana_pool.floating == {}
    assert scenario.game.player("alice").hand == []


def test_sorin_reveals_puts_into_hand_and_loses_life_equal_to_its_mana_value():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Sorin the Mirthless"],
            library=["Cryptic Command", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sorin = scenario.find("Sorin the Mirthless", Zone.BATTLEFIELD)
    (command,) = scenario.top_of_library(1, username="alice")
    index = next(
        index
        for index, ability in enumerate(scenario.game.activated_abilities(sorin))
        if ability.effect.startswith("Look at the top card")
    )
    scenario.will_take_the_may(True, username="alice", source="Sorin the Mirthless")
    loyalty = sorin.counter_count(Counter.LOYALTY)

    scenario.activate(sorin, index=index)
    scenario.pass_until_resolved()

    assert command.zone is Zone.HAND
    assert scenario.game.player("alice").life == 16
    assert sorin.counter_count(Counter.LOYALTY) == loyalty + 1


def test_sorin_declined_leaves_the_card_on_top_and_costs_no_life():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Sorin the Mirthless"],
            library=["Cryptic Command", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sorin = scenario.find("Sorin the Mirthless", Zone.BATTLEFIELD)
    (command,) = scenario.top_of_library(1, username="alice")
    index = next(
        index
        for index, ability in enumerate(scenario.game.activated_abilities(sorin))
        if ability.effect.startswith("Look at the top card")
    )
    scenario.will_take_the_may(False, username="alice", source="Sorin the Mirthless")

    scenario.activate(sorin, index=index)
    scenario.pass_until_resolved()

    assert command.zone is Zone.LIBRARY
    assert scenario.game.player("alice").library[0] is command
    assert scenario.game.player("alice").life == 20
