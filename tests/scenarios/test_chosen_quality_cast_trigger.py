"""Scenario: Gollum, Riddle Master - "As Gollum enters, choose odd or even.
(Zero is even.)" then "Whenever an opponent casts a spell with mana value of
the chosen quality, choose one that hasn't been chosen -".

Three engine pieces, read off one printing:

- **A fourth CR 614.12a "as [this] enters, choose ..." shape**
  (`ChoiceKind.ODD_OR_EVEN`), alongside color/card-name/creature-type -
  `machines/replacement._classify_choice` and `_quality_options`.
- **A trigger condition reading that choice back**: "mana value of the
  chosen quality" (CR 202.3) - odd or even, zero counting even - checked
  against the cast spell's own mana value (`GameEvent.amount`, the same
  CR 202.3e X-aware read Chalice of the Void's counter comparison already
  uses).
- **"Choose one that hasn't been chosen -" is CR 700.2's ordinary modal
  triggered ability (CR 603.3c) plus one more exclusion**: a mode already
  picked by *this permanent's own trigger* is not offered again
  (`CardState.chosen_modal_options`, "modes tracked per object") until
  every mode has been used, at which point the ability is removed from the
  stack with none chosen (CR 700.2b) rather than repeating one.

CR numbers verified this session with `mise run rules:find`: 614.12a
(existing code, re-verified), 700.2, 700.2a, 700.2b, 603.3c, 202.3e
(existing code).
"""

from magic_cards_model.machines import Step

from .harness import Scenario


def resolve_all(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def test_choosing_even_and_an_odd_spell_does_not_trigger():
    """Opt is mana value 1 (odd) - not the chosen quality."""
    scenario = (
        Scenario()
        .player("alice", hand=["Gollum, Riddle Master"], battlefield=["Swamp"] * 2)
        .player("bob", hand=["Opt"], battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("even", source="Gollum, Riddle Master")
    gollum = scenario.put_onto_battlefield("Gollum, Riddle Master")
    assert gollum.choice is not None and gollum.choice.value == "even"

    scenario.pass_priority("alice")
    scenario.cast_onto_stack(
        "Opt", *scenario.untapped_sources("Island", username="bob"), username="bob"
    )
    resolve_all(scenario)

    assert gollum.chosen_modal_options == ()


def test_an_opponent_casting_an_even_spell_triggers_and_a_mode_is_chosen():
    """Anticipate is mana value 2 (even, CR 107.1) - the chosen quality."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Gollum, Riddle Master"],
            library=["Forest"] * 3,
            battlefield=["Swamp"] * 2,
        )
        .player("bob", hand=["Anticipate"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("even", source="Gollum, Riddle Master")
    gollum = scenario.put_onto_battlefield("Gollum, Riddle Master")

    scenario.will_choose_mode("Draw a card.")
    scenario.pass_priority("alice")
    hand_before = len(scenario.player("alice").hand)
    islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Anticipate", *islands, username="bob")
    resolve_all(scenario)

    assert len(scenario.player("alice").hand) == hand_before + 1
    assert gollum.chosen_modal_options == ("Draw a card.",)


def test_a_mode_already_chosen_is_not_offered_again():
    """ "Choose one that hasn't been chosen -": with one mode already used,
    only the other two are offered - `will_choose_mode` fails loudly if the
    engine offers a mode it should have excluded, since the queued answer
    would not be among the real options `Game.ask` presents."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Gollum, Riddle Master"],
            library=["Forest"] * 3,
            battlefield=["Swamp"] * 2,
        )
        .player(
            "bob",
            hand=["Anticipate", "Anticipate"],
            battlefield=["Island"] * 4,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("even", source="Gollum, Riddle Master")
    gollum = scenario.put_onto_battlefield("Gollum, Riddle Master")

    scenario.will_choose_mode("Draw a card.")
    scenario.pass_priority("alice")
    islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Anticipate", *islands, username="bob")
    resolve_all(scenario)
    assert gollum.chosen_modal_options == ("Draw a card.",)

    # A second even spell triggers again - "Draw a card." is no longer
    # offered, so the engine must ask among the remaining two modes.
    scenario.will_choose_mode("Put a +1/+1 counter on Gollum.")
    scenario.pass_priority("alice")
    more_islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Anticipate", *more_islands, username="bob")
    resolve_all(scenario)

    assert gollum.chosen_modal_options == ("Draw a card.", "Put a +1/+1 counter on Gollum.")
    assert gollum.counter_count("+1/+1") == 1


def test_odd_chosen_ignores_an_even_spell_and_fires_on_an_odd_one():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Gollum, Riddle Master"],
            library=["Forest"] * 3,
            battlefield=["Swamp"] * 2,
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("odd", source="Gollum, Riddle Master")
    scenario.put_onto_battlefield("Gollum, Riddle Master")

    scenario.will_choose_mode("Draw a card.")
    scenario.pass_priority("alice")
    hand_before = len(scenario.player("alice").hand)
    bolt_sources = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack("Lightning Bolt", *bolt_sources, username="bob", targets=["alice"])
    resolve_all(scenario)

    assert len(scenario.player("alice").hand) == hand_before + 1  # mana value 1 is odd


def test_a_players_own_cast_never_triggers_gollum():
    """ "An opponent casts" - the ability's own controller casting an odd
    spell does nothing."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Gollum, Riddle Master", "Lightning Bolt"],
            battlefield=["Swamp"] * 2 + ["Mountain"],
        )
        .player("bob", battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("odd", source="Gollum, Riddle Master")
    gollum = scenario.put_onto_battlefield("Gollum, Riddle Master")

    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    resolve_all(scenario)

    assert gollum.chosen_modal_options == ()
