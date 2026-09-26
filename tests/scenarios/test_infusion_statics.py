"""Infusion (CR 207.2c) static shapes: "as long as you gained life this
turn" self and group pumps, and "unless you gained life this turn" - plus a
second real printing of each (Ulna Alley Shopkeep alongside Tenured
Concocter's identical self-pump; Instill Furor's own differently-conditioned
"unless" alongside Tragedy Feaster's), proving the shape is not fitted to one
card's exact sentence.

Rules verified with `mise run rules:find` in the session that wrote this
file:

- **CR 207.2c** - Infusion is a printed ability word with no rules meaning.
- **CR 604.2** / **CR 611.3a** - a static ability's continuous effect is
  active only while its condition holds, re-checked on every computation.
- **CR 613.4c** - a pump is sublayer 7c; **CR 613.1f** - a keyword grant is
  layer 6.
- **CR 118.12** - "[Do something] unless [...]" - the something happens
  unless the other thing already holds when the instruction is performed.
- **CR 701.21a** - sacrifice: the permanent's own controller chooses which.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def computed(scenario):
    return scenario.game.computed_board()


def _board(alice: dict | None = None, bob: dict | None = None):
    alice_kwargs = {"library": ["Plains"] * 8, **(alice or {})}
    bob_kwargs = {"library": ["Plains"] * 8, **(bob or {})}
    scenario = Scenario().player("alice", **alice_kwargs).player("bob", **bob_kwargs).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- self pump: "This creature gets +2/+0 as long as you gained life this
# -- turn." (Tenured Concocter, and Ulna Alley Shopkeep's identical line)


def test_tenured_concocter_no_pump_without_life_gained():
    scenario = _board({"battlefield": ["Tenured Concocter"]})
    creature = scenario.creature("Tenured Concocter", "alice")
    board = computed(scenario)
    assert board.of(creature).power == creature.power


def test_tenured_concocter_pumps_while_you_gained_life_this_turn():
    scenario = _board({"battlefield": ["Tenured Concocter"]})
    creature = scenario.creature("Tenured Concocter", "alice")
    base_power = creature.power
    scenario.game.gain_life("alice", 1)
    board = computed(scenario)
    assert board.of(creature).power == base_power + 2
    assert board.of(creature).toughness == creature.toughness


def test_ulna_alley_shopkeep_pumps_while_you_gained_life_this_turn():
    """Second real printing of the identical "as long as you gained life
    this turn" self-pump (`card_search o:"as long as you gained life this
    turn"`) - not the reported card, proving the reader is not fitted to
    Tenured Concocter's line specifically."""
    scenario = _board({"battlefield": ["Ulna Alley Shopkeep"]})
    creature = scenario.creature("Ulna Alley Shopkeep", "alice")
    base_power = creature.power
    scenario.game.gain_life("alice", 1)
    board = computed(scenario)
    assert board.of(creature).power == base_power + 2


def test_tenured_concocter_pump_switches_off_once_the_turn_ends():
    """CR 611.3a: the effect isn't "locked in" - it stops applying the
    moment the fact stops holding, which for a per-turn fact is the next
    turn's own untap step."""
    scenario = _board({"battlefield": ["Tenured Concocter"]})
    creature = scenario.creature("Tenured Concocter", "alice")
    base_power = creature.power
    scenario.game.gain_life("alice", 1)
    assert computed(scenario).of(creature).power == base_power + 2
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # bob's untap step - a new turn, "this turn" resets
    assert computed(scenario).of(creature).power == base_power


# -- group pump + keyword: "Creatures you control get +1/+0 and have
# -- trample as long as you gained life this turn." (Thornfist Striker)


def test_thornfist_striker_no_team_pump_without_life_gained():
    scenario = _board({"battlefield": ["Thornfist Striker", "Grizzly Bears"]})
    scenario.creature("Thornfist Striker", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    board = computed(scenario)
    assert board.of(bears).power == bears.power
    assert "Trample" not in board.of(bears).abilities


def test_thornfist_striker_pumps_and_grants_trample_to_every_creature_you_control():
    scenario = _board(
        {"battlefield": ["Thornfist Striker", "Grizzly Bears"]},
        {"battlefield": ["Runeclaw Bear"]},
    )
    striker = scenario.creature("Thornfist Striker", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    opponent_bear = scenario.creature("Runeclaw Bear", "bob")
    base_striker_power = striker.power
    base_bears_power = bears.power
    scenario.game.gain_life("alice", 1)
    board = computed(scenario)
    assert board.of(striker).power == base_striker_power + 1
    assert "Trample" in board.of(striker).abilities
    assert board.of(bears).power == base_bears_power + 1
    assert "Trample" in board.of(bears).abilities
    # "Creatures you control" - never the opponent's.
    assert board.of(opponent_bear).power == opponent_bear.power
    assert "Trample" not in board.of(opponent_bear).abilities


# -- "sacrifice a permanent unless you gained life this turn." (Tragedy
# -- Feaster's own end step trigger)


def test_tragedy_feaster_sacrifices_a_permanent_without_life_gained():
    scenario = _board({"battlefield": ["Tragedy Feaster", "Grizzly Bears"]})
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
    scenario.turn.advance_to(Step.POSTCOMBAT_MAIN)
    scenario.game.sync_priority_with_step()
    scenario.advance()  # the end step begins (CR 513.1)
    feaster = scenario.creature("Tragedy Feaster", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.will_choose_cards(feaster, username="alice")
    scenario.pass_until_resolved()
    assert (feaster.zone is Zone.GRAVEYARD) != (bears.zone is Zone.GRAVEYARD)


def test_tragedy_feaster_sacrifices_nothing_when_life_gained_this_turn():
    scenario = _board({"battlefield": ["Tragedy Feaster", "Grizzly Bears"]})
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
    scenario.turn.advance_to(Step.POSTCOMBAT_MAIN)
    scenario.game.sync_priority_with_step()
    scenario.advance()  # the end step begins (CR 513.1)
    scenario.game.gain_life("alice", 1)
    feaster = scenario.creature("Tragedy Feaster", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert feaster.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.BATTLEFIELD


def test_instill_furor_sacrifices_unless_it_attacked_this_turn():
    """Instill Furor's own "unless" condition ("it attacked this turn"
    instead of "you gained life this turn") - a second real printing found
    via `card_search o:"sacrifice" o:"unless" o:"this turn"`, proving the
    "sacrifice `<description>` unless `<condition>`" reader is not read off
    Tragedy Feaster's own fact."""
    scenario = _board(
        {"battlefield": ["Runeclaw Bear", "Mountain", "Mountain"], "hand": ["Instill Furor"]}
    )
    bear = scenario.creature("Runeclaw Bear", "alice")
    bear.summoning_sick = False
    scenario.cast_and_resolve("Instill Furor", auto=True, targets=[bear])
    scenario.turn.advance_to(Step.POSTCOMBAT_MAIN)
    scenario.game.sync_priority_with_step()
    scenario.advance()  # the end step begins
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert bear.zone is Zone.GRAVEYARD


def test_instill_furor_does_not_sacrifice_after_attacking_this_turn():
    scenario = _board(
        {"battlefield": ["Runeclaw Bear", "Mountain", "Mountain"], "hand": ["Instill Furor"]}
    )
    bear = scenario.creature("Runeclaw Bear", "alice")
    bear.summoning_sick = False
    scenario.cast_and_resolve("Instill Furor", auto=True, targets=[bear])
    scenario.turn.advance_to(Step.DECLARE_ATTACKERS)
    scenario.game.sync_priority_with_step()
    scenario.attack_with(bear)
    scenario.no_blocks()
    scenario.turn.advance_to(Step.POSTCOMBAT_MAIN)
    scenario.game.sync_priority_with_step()
    scenario.advance()  # the end step begins
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert bear.zone is Zone.BATTLEFIELD
