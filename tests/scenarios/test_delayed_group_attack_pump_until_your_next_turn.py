""" "Until your next turn, whenever one or more creatures attack one of your
opponents, those creatures get `<power>`/`<toughness>`[ and gain
`<keywords>`] until end of turn." - Garruk, Curse Breaker's own `-4`. The
group-attack twin of `test_delayed_attack_pump_until_your_next_turn.py`'s
"attacks you or a planeswalker you control" shape: CR 603.2c's "one or more
`<description>` attack" condition in place of a singular attacker, and
`DelayedTrigger.defending_opponent_only` - the opposite half of `defending_
controller_only`'s own compound defender - in place of "you or a
planeswalker you control".

Every rule below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 603.7 / CR 603.7b** - a delayed triggered ability, with a stated
  duration ("until your next turn") firing more than once.
- **CR 603.2c** - "An ability triggers only once each time its trigger event
  occurs. However, it can trigger repeatedly if one event contains multiple
  occurrences" - the "one or more creatures attack" shape this pump watches.
- **CR 508.3a** - "attacks [a player, planeswalker, or battle]" - the
  defender named in the condition.
- **CR 611.2a** - each individual pump this grants is its own ordinary
  "until end of turn" continuous effect, independent of how long the
  delayed watch itself lasts.
- **CR 702.19a** - trample, the keyword this ability grants alongside the
  power/toughness pump.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.combat import has_keyword
from tests.scenarios.harness import Scenario


def _advance_until(scenario: Scenario, predicate) -> None:
    while not predicate(scenario):
        scenario.advance()


def _resolve_the_stack(scenario: Scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def _garruk_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Garruk, Curse Breaker", "Grizzly Bears"],
            library=["Forest"] * 5,
        )
        .player("bob", battlefield=["Watchwolf"], library=["Forest"] * 5)
    )


def _activate_garruks_minus_four(scenario: Scenario) -> None:
    garruk = scenario.creature("Garruk, Curse Breaker", "alice")
    scenario.activate(garruk, index=2, username="alice")
    _resolve_the_stack(scenario)


def test_activating_garruks_minus_four_creates_the_watch():
    scenario = _garruk_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _activate_garruks_minus_four(scenario)

    (trigger,) = scenario.game.delayed_triggers.triggers
    assert trigger.event is TriggerEvent.ATTACKS
    assert trigger.controller == "alice"
    assert trigger.defending_opponent_only is True
    assert trigger.expires_end_of_next_turn is True
    assert trigger.remaining is None, "a stated duration (CR 603.7b), not a one-shot"


def test_a_creature_attacking_an_opponent_gets_pumped_and_gains_trample():
    scenario = _garruk_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_garruks_minus_four(scenario)
    bears = scenario.creature("Grizzly Bears", "alice")
    assert not has_keyword(bears, "trample", scenario.game)

    scenario.attack_with(bears, defending="bob")
    _resolve_the_stack(scenario)

    characteristics = scenario.game.characteristics_of(bears)
    assert (characteristics.power, characteristics.toughness) == (2 + 2, 2 + 2)
    assert has_keyword(bears, "trample", scenario.game)


def test_a_creature_attacking_its_own_controller_does_not_get_pumped():
    """`defending_opponent_only` - bob attacking alice herself (his own
    opponent, not one of *his* opponents from Garruk's controller's
    perspective) is not this ability's business at all: alice controls
    Garruk, and alice is never her own opponent."""
    scenario = _garruk_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_garruks_minus_four(scenario)

    _advance_until(
        scenario,
        lambda s: s.turn.active_player == "bob" and s.step is Step.DECLARE_ATTACKERS,
    )
    wolf = scenario.creature("Watchwolf", "bob")
    scenario.attack_with(wolf, defending="alice")

    assert scenario.game.stack == [], "no ATTACKS-watching trigger should have matched"
    characteristics = scenario.game.characteristics_of(wolf)
    assert (characteristics.power, characteristics.toughness) == (3, 3)
    assert not has_keyword(wolf, "trample", scenario.game)


def test_the_trigger_fires_again_on_a_second_qualifying_attack():
    """CR 603.7b's stated duration: `remaining=None` lets the watch fire on
    every matching attack, not just the first."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Garruk, Curse Breaker", "Grizzly Bears", "Elite Vanguard"],
            library=["Forest"] * 5,
        )
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_garruks_minus_four(scenario)
    bears = scenario.creature("Grizzly Bears", "alice")
    vanguard = scenario.creature("Elite Vanguard", "alice")

    scenario.attack_with(bears, vanguard, defending="bob")
    _resolve_the_stack(scenario)

    bears_characteristics = scenario.game.characteristics_of(bears)
    vanguard_characteristics = scenario.game.characteristics_of(vanguard)
    assert (bears_characteristics.power, bears_characteristics.toughness) == (2 + 2, 2 + 2)
    assert (vanguard_characteristics.power, vanguard_characteristics.toughness) == (2 + 2, 1 + 2)
    assert has_keyword(bears, "trample", scenario.game)
    assert has_keyword(vanguard, "trample", scenario.game)


def test_each_pump_expires_at_the_ordinary_end_of_turn_even_though_the_watch_persists():
    scenario = _garruk_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_garruks_minus_four(scenario)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.attack_with(bears, defending="bob")
    _resolve_the_stack(scenario)
    assert scenario.game.characteristics_of(bears).power == 2 + 2

    _advance_until(scenario, lambda s: s.turn.active_player == "alice" and s.step is Step.CLEANUP)

    characteristics = scenario.game.characteristics_of(bears)
    assert (characteristics.power, characteristics.toughness) == (2, 2)
    assert not has_keyword(bears, "trample", scenario.game)
    # The watch itself is untouched by an ordinary cleanup - only alice's own
    # next turn beginning ends it.
    assert len(scenario.game.delayed_triggers.triggers) == 1


def test_the_watch_stops_firing_once_the_granting_players_own_next_turn_has_begun():
    scenario = _garruk_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_garruks_minus_four(scenario)
    turns_taken = scenario.turn.turns_taken

    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears, defending="bob")
    _resolve_the_stack(scenario)
    assert scenario.game.characteristics_of(bears).power == 2 + 2

    _advance_until(
        scenario,
        lambda s: s.turn.turns_taken > turns_taken and s.turn.active_player == "alice",
    )
    assert scenario.game.delayed_triggers.triggers == []

    scenario.attack_with(bears, defending="bob")

    assert scenario.game.stack == [], "the watch expired - nothing left to trigger"
    assert scenario.game.characteristics_of(bears).power == 2
