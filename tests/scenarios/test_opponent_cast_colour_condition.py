"""Scenario: "an opponent (has )?cast a `<colour>`[ (and/)?or `<colour>`]* spell
this turn" - `Game.condition_holds`'s own board-condition reader (CR 105.1's
five colours), asked from two differently-worded cards.

Veil of Summer's trailing "Draw a card if an opponent has cast a blue or
black spell this turn." (`_parse_condition_clause`'s own trailing-if shape,
already wired) needs `condition_holds` to learn what "an opponent has cast a
`<colour>`" means at all - it did not, before this file. Sandstalker
Moloch's ETB carries the identical board fact as an *intervening if* (CR
603.4), worded differently ("if an opponent cast a blue and/or black spell
this turn") - proof that the reader is general across both wordings, and
that Moloch's own trigger check (`machines/triggers.intervening_if_holds`)
now asks the exact same `Game.condition_holds` branch rather than a second,
independent copy of it.

`Game.spells_cast_this_turn` is the underlying record (CR 601.2h's "cast" is
a defined action), already kept per player and already emptied at the start
of each new turn - this file only proves the *colour* and *opponent* reading
over it, not the record-keeping itself (`test_turn_cycle.py` and the
trigger-condition suite already cover that it resets).
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def _veil_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Veil of Summer"],
            battlefield=["Forest", "Island"],
            library=["Forest", "Forest"],
        )
        .player(
            "bob",
            hand=["Opt", "Fatal Push", "Lightning Bolt"],
            battlefield=["Island", "Island", "Swamp", "Mountain", "Grizzly Bears"],
            library=["Island"] * 3,
        )
        .build()
    )


def _bob_casts(scenario: Scenario, name: str, *sources, targets=None) -> None:
    """Start the turn and hand Bob priority so he can cast first - the
    ordinary CR 117.3c dance a scenario has to drive by hand whenever the
    *non*-active player acts first. Resolving a spell with an empty stack
    behind it gives priority back to the active player (CR 117.3b), so
    Alice already holds it again once this returns."""
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(name, *sources, username="bob", targets=targets)


def _cast_veil(scenario: Scenario):
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    return scenario.cast_and_resolve("Veil of Summer", forest, username="alice")


# -- Veil of Summer's own trailing "if" --------------------------------------


def test_veil_draws_when_an_opponent_cast_a_blue_spell_this_turn():
    scenario = _veil_board()
    (island,) = scenario.untapped_sources("Island", username="bob")
    _bob_casts(scenario, "Opt", island)

    _cast_veil(scenario)
    # Veil itself leaves the hand (cast) and a card is drawn (the trailing
    # "if"): the library is what shows the extra draw happened.
    assert len(scenario.player("alice").library) == 1


def test_veil_draws_when_an_opponent_cast_a_black_spell_this_turn():
    scenario = _veil_board()
    (swamp,) = scenario.untapped_sources("Swamp", username="bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    _bob_casts(scenario, "Fatal Push", swamp, targets=[bears])

    _cast_veil(scenario)
    assert len(scenario.player("alice").library) == 1


def test_veil_does_not_draw_when_an_opponent_cast_only_a_red_spell_this_turn():
    """Lightning Bolt is neither blue nor black - the condition stays false,
    and CR 608.2c's "if `<condition>`" instruction does nothing at all."""
    scenario = _veil_board()
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    _bob_casts(scenario, "Lightning Bolt", mountain, targets=["alice"])

    _cast_veil(scenario)
    assert len(scenario.player("alice").library) == 2


def test_veil_does_not_draw_when_you_cast_the_blue_spell_yourself():
    """ "An opponent" (CR 102.2) excludes Veil's own controller - Alice
    casting a blue spell herself is not an *opponent's* blue spell."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Veil of Summer", "Opt"],
            battlefield=["Forest", "Island"],
            library=["Forest", "Forest"],
        )
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island", username="alice")
    scenario.cast_and_resolve("Opt", island, username="alice")

    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_and_resolve("Veil of Summer", forest, username="alice")
    # Opt itself drew and scried; Veil's own trailing "if" did not fire, so
    # exactly one card left the library (Opt's), not two.
    assert len(scenario.player("alice").library) == 1


# -- Sandstalker Moloch's differently-worded intervening if ------------------


def _moloch_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Sandstalker Moloch"],
            battlefield=["Forest", "Forest", "Forest"],
            library=["Forest"] * 6,
        )
        .player(
            "bob",
            hand=["Opt", "Lightning Bolt"],
            battlefield=["Island", "Mountain"],
            library=["Island"] * 3,
        )
        .build()
    )


def _cast_moloch(scenario: Scenario):
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", username="alice")
    scenario.cast_and_resolve("Sandstalker Moloch", *sources, username="alice")


def test_moloch_triggers_when_an_opponent_cast_a_qualifying_spell_this_turn():
    """ "An opponent cast a blue and/or black spell this turn" - the CR 603.4
    intervening if is checked as the trigger fires; read true here, so it
    goes on the stack (`cast_and_resolve` already runs Moloch's own ETB
    resolution and the trigger check that follows it, so the ability is on
    the stack, not merely pending, by the time this looks)."""
    scenario = _moloch_board()
    (island,) = scenario.untapped_sources("Island", username="bob")
    _bob_casts(scenario, "Opt", island)

    _cast_moloch(scenario)
    assert scenario.stack_names() == ["Sandstalker Moloch's triggered ability"]


def test_moloch_does_not_trigger_when_the_opponents_spell_was_only_red():
    """CR 603.4: "The ability triggers only if [the condition is] true" - a
    false intervening if means the ability never triggers at all, not that
    it triggers and then does nothing."""
    scenario = _moloch_board()
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    _bob_casts(scenario, "Lightning Bolt", mountain, targets=["alice"])

    _cast_moloch(scenario)
    assert scenario.pending_triggers == []
    assert scenario.stack_names() == []
