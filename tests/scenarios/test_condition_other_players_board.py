"""Conditions on other players' boards and on the whole battlefield -
"defending player controls no Walls", "a player controls no creatures", "your
opponents control no permanents with bounty counters on them", "no creatures
are on the battlefield", "all lands on the battlefield are Islands", "two or
more permanents you don't control have an aim counter on them".

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 506.2** - in a two-player game's combat the nonactive player is the
  defending player; **CR 508.5** - the defending player of one attack is the
  player attacked, or the controller of the planeswalker or battle attacked.
- **CR 603.4** / **CR 608.2a** - the intervening "if" is checked as the event
  occurs and again as the ability resolves.
- **CR 613.5** - every count reads the computed board.
- **CR 122.1** - counters are markers on an object; a bounty or aim counter
  is one like any other.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.triggers import (
    GameEvent,
    TriggerEvent,
    intervening_if_answer,
    triggered_abilities_of,
)
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(alice, bob=None, *, hand=None, bob_hand=None, step=Step.PRECOMBAT_MAIN):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=alice, hand=hand or [], library=["Plains"] * 6)
        .player("bob", battlefield=bob or [], hand=bob_hand or [], library=["Plains"] * 6)
        .build()
    )
    scenario.start_at(step)
    return scenario


def _holds(scenario, name: str, owner: str = "alice", event=None) -> bool | None:
    (ability,) = [a for a in triggered_abilities_of(card(name)) if a.intervening_if]
    return intervening_if_answer(scenario.game, ability, scenario.creature(name, owner), event)


def _end_step(scenario) -> None:
    scenario.start_at(Step.END_STEP)
    scenario.game.emit(
        GameEvent(event=TriggerEvent.BEGINNING_OF_STEP, step=Step.END_STEP, player="alice")
    )
    scenario.game.put_triggers_on_stack()


def _attack(scenario, name: str) -> None:
    attacker = scenario.creature(name)
    attacker.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacker)


# -- "defending player controls no <quality>" --------------------------------


def test_defending_player_with_a_glimmer_stops_the_trigger():
    """CR 603.4: Fear of the Dark - "Whenever this creature attacks, if
    defending player controls no Glimmer creatures, it gains menace and
    deathtouch until end of turn." Bob, attacked, controls Enduring Innocence."""
    scenario = _board(["Fear of the Dark"], ["Enduring Innocence"])
    _attack(scenario, "Fear of the Dark")
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


def test_defending_player_without_one_resolves():
    scenario = _board(["Fear of the Dark"], ["Grizzly Bears"])
    _attack(scenario, "Fear of the Dark")
    assert scenario.stack_names() == ["Fear of the Dark's triggered ability"]
    scenario.pass_until_resolved()
    from magic_cards_model.machines.combat import has_keyword

    fear = scenario.creature("Fear of the Dark")
    assert has_keyword(fear, "menace", scenario.game)
    assert has_keyword(fear, "deathtouch", scenario.game)


def test_the_attacking_players_own_glimmer_does_not_count():
    """Only the defending player's board is asked: alice's own Glimmer
    creature is not the defending player's."""
    scenario = _board(["Fear of the Dark", "Enduring Innocence"], ["Grizzly Bears"])
    _attack(scenario, "Fear of the Dark")
    assert scenario.stack_names() == ["Fear of the Dark's triggered ability"]


def test_defending_player_controls_no_walls_on_a_second_printing():
    """Siege Dragon: "if defending player controls no Walls" - read off the
    combat in progress."""
    scenario = _board(["Siege Dragon"], ["Wall of Omens"])
    attacker = scenario.creature("Siege Dragon")
    attacker.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacker)
    assert _holds(scenario, "Siege Dragon") is False
    scenario = _board(["Siege Dragon"], ["Grizzly Bears"])
    attacker = scenario.creature("Siege Dragon")
    attacker.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacker)
    assert _holds(scenario, "Siege Dragon") is True


def test_defending_player_controls_no_black_permanents():
    """Spectral Force's "if defending player controls no black permanents",
    read through the shared reader while Fear of the Dark attacks."""
    clause = "defending player controls no black permanents"
    scenario = _board(["Fear of the Dark"], ["Ophiomancer", "Enduring Innocence"])
    _attack(scenario, "Fear of the Dark")
    fear = scenario.creature("Fear of the Dark")
    assert scenario.game.condition_holds("alice", clause, fear) is False
    scenario = _board(["Fear of the Dark"], ["Grizzly Bears", "Enduring Innocence"])
    _attack(scenario, "Fear of the Dark")
    fear = scenario.creature("Fear of the Dark")
    assert scenario.game.condition_holds("alice", clause, fear) is True


def test_no_defending_player_outside_combat_is_false():
    """Asked with no combat at all, there is no defending player to ask about:
    the clause is read, and false."""
    scenario = _board(["Siege Dragon"], ["Grizzly Bears"])
    assert _holds(scenario, "Siege Dragon") is False


# -- "no creatures are on the battlefield" -----------------------------------


def _grave_board(alice, bob=None, hand=None):
    return _board(["Call to the Grave", *alice], bob, hand=hand)


def test_no_creatures_on_the_battlefield_is_false_with_any_creature():
    """CR 603.4: Call to the Grave - "At the beginning of the end step, if no
    creatures are on the battlefield, sacrifice this enchantment." Bob's
    creature counts too."""
    scenario = _grave_board([], ["Grizzly Bears"])
    _end_step(scenario)
    assert scenario.stack_names() == []


def test_no_creatures_true_then_false_by_resolution_keeps_it():
    """CR 608.2a: none as the end step begins; Ambush Viper flashed in with
    the trigger on the stack - the enchantment is not sacrificed."""
    scenario = _grave_board(["Forest", "Forest"], hand=["Ambush Viper"])
    _end_step(scenario)
    assert scenario.stack_names() == ["Call to the Grave's triggered ability"]
    scenario.cast_and_resolve("Ambush Viper", *scenario.untapped_sources("Forest", "Forest"))
    scenario.pass_until_resolved()
    assert scenario.game.stack_is_empty
    assert scenario.creature("Call to the Grave") is not None


def test_no_creatures_true_at_both_times_sacrifices_it():
    scenario = _grave_board([])
    _end_step(scenario)
    scenario.pass_until_resolved()
    assert "Call to the Grave" not in [
        state.name for state in scenario.game.permanents_controlled_by("alice")
    ]


def test_no_creatures_on_a_second_printing():
    """Pyrohemia prints the same clause."""
    scenario = _board(["Pyrohemia"])
    assert _holds(scenario, "Pyrohemia") is True
    scenario = _board(["Pyrohemia"], ["Llanowar Elves"])
    assert _holds(scenario, "Pyrohemia") is False


# -- "a player controls no creatures" ----------------------------------------


def test_a_player_controls_no_creatures_is_any_player():
    """Sothera, the Supervoid: "if a player controls no creatures" - alice
    herself counts."""
    scenario = _board(["Sothera, the Supervoid", "Grizzly Bears"], ["Llanowar Elves"])
    assert _holds(scenario, "Sothera, the Supervoid") is False
    scenario = _board(["Sothera, the Supervoid"], ["Llanowar Elves"])
    assert _holds(scenario, "Sothera, the Supervoid") is True
    scenario = _board(["Sothera, the Supervoid", "Grizzly Bears"])
    assert _holds(scenario, "Sothera, the Supervoid") is True


# -- counters on permanents others control ------------------------------------


def test_your_opponents_control_no_permanents_with_bounty_counters():
    """Chevill, Bane of Monsters: "if your opponents control no permanents
    with bounty counters on them" - a bounty counter on alice's own creature
    is not an opponent's."""
    scenario = _board(["Chevill, Bane of Monsters", "Grizzly Bears"], ["Llanowar Elves"])
    assert _holds(scenario, "Chevill, Bane of Monsters") is True
    scenario.game.add_counters(scenario.creature("Grizzly Bears", "alice"), "bounty", 1)
    assert _holds(scenario, "Chevill, Bane of Monsters") is True
    scenario.game.add_counters(scenario.creature("Llanowar Elves", "bob"), "bounty", 1)
    assert _holds(scenario, "Chevill, Bane of Monsters") is False


def test_two_or_more_permanents_you_dont_control_have_an_aim_counter():
    """Haphazard Bombardment: "if two or more permanents you don't control
    have an aim counter on them"."""
    scenario = _board(["Haphazard Bombardment"], ["Grizzly Bears", "Llanowar Elves", "Forest"])
    bears, elves = (
        scenario.creature("Grizzly Bears", "bob"),
        scenario.creature("Llanowar Elves", "bob"),
    )
    scenario.game.add_counters(bears, "aim", 1)
    assert _holds(scenario, "Haphazard Bombardment") is False
    scenario.game.add_counters(elves, "aim", 1)
    assert _holds(scenario, "Haphazard Bombardment") is True


# -- "all lands on the battlefield are Islands" ------------------------------


def test_all_lands_on_the_battlefield_are_islands():
    """Quicksilver Fountain: every land on either side must be an Island."""
    scenario = _board(["Quicksilver Fountain", "Island"], ["Island"])
    assert _holds(scenario, "Quicksilver Fountain") is True
    scenario = _board(["Quicksilver Fountain", "Island"], ["Forest"])
    assert _holds(scenario, "Quicksilver Fountain") is False
