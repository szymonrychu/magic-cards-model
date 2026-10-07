"""Gimli, Mournful Avenger: a per-turn died count gating a self static, and a
reflexive trigger keyed on how many times its own ability resolved this turn.

Rules read in full with `mise run rules:find` this session:

- **CR 603.12** - a resolving ability may create a reflexive triggered
  ability that triggers "when [something happens] this way", following the
  delayed-trigger rules and checked as soon as it is created.
- **CR 701.14a** - "Each of those creatures deals damage equal to its power
  to the other creature."
- **CR 115.6** / "up to one target" - zero targets is a legal choice.
- **CR 700.4** - dies means put into a graveyard from the battlefield.
- **CR 400.7** - a permanent that leaves and returns is a new object, so its
  ability's resolution count starts again.

No other printing legal in Modern, Pioneer or Standard prints "as long as two
or more creatures died under your control this turn" on a static, or "When
this ability resolves for the <n> time this turn" (searched over the oracle
bulk), so both are proven on Gimli only.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

GIMLI = "Gimli, Mournful Avenger"
PLUS = "+1/+1"


def _board(alice=(), bob=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=[GIMLI, *alice], library=["Mountain"] * 10)
        .player("bob", battlefield=list(bob), library=["Mountain"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _resolve_all(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _kill(scenario, name, owner="alice"):
    victim = next(p for p in scenario.game.battlefield if p.name == name and p.controller == owner)
    scenario.game.destroy(victim)
    return victim


def _indestructible(scenario, permanent) -> bool:
    return has_keyword(permanent, "indestructible", scenario.game)


# -- "has indestructible as long as two or more creatures died under your control
# -- this turn" ---------------------------------------------------------------------


def test_no_deaths_no_indestructible():
    scenario = _board()
    assert not _indestructible(scenario, scenario.creature(GIMLI))


def test_one_death_is_not_enough():
    scenario = _board(alice=["Grizzly Bears"])
    _kill(scenario, "Grizzly Bears")
    _resolve_all(scenario)
    assert not _indestructible(scenario, scenario.creature(GIMLI))


def test_two_of_your_creatures_dying_makes_gimli_indestructible():
    scenario = _board(alice=["Grizzly Bears", "Raging Goblin"])
    gimli = scenario.creature(GIMLI)
    _kill(scenario, "Grizzly Bears")
    _kill(scenario, "Raging Goblin")
    _resolve_all(scenario)

    assert _indestructible(scenario, gimli)
    scenario.game.destroy(gimli)
    assert gimli.zone is Zone.BATTLEFIELD


def test_opponents_creatures_dying_do_not_count():
    scenario = _board(bob=["Grizzly Bears", "Raging Goblin"])
    _kill(scenario, "Grizzly Bears", owner="bob")
    _kill(scenario, "Raging Goblin", owner="bob")
    assert not _indestructible(scenario, scenario.creature(GIMLI))


def test_the_count_is_this_turn_only():
    scenario = _board(alice=["Grizzly Bears", "Raging Goblin"])
    gimli = scenario.creature(GIMLI)
    _kill(scenario, "Grizzly Bears")
    _kill(scenario, "Raging Goblin")
    _resolve_all(scenario)
    assert _indestructible(scenario, gimli)

    while scenario.turn.active_player == "alice":
        scenario.advance()
        _resolve_all(scenario)
    assert not _indestructible(scenario, gimli)


# -- "Whenever another creature you control dies, put a +1/+1 counter on Gimli.
# -- When this ability resolves for the third time this turn, Gimli fights up to one
# -- target creature you don't control." ---------------------------------------------


def test_each_resolution_puts_a_counter_and_the_first_two_do_not_fight():
    scenario = _board(alice=["Grizzly Bears", "Raging Goblin"], bob=["Craw Wurm"])
    gimli = scenario.creature(GIMLI)
    wurm = scenario.creature("Craw Wurm", "bob")
    _kill(scenario, "Grizzly Bears")
    _resolve_all(scenario)
    _kill(scenario, "Raging Goblin")
    _resolve_all(scenario)

    assert gimli.counter_count(PLUS) == 2
    assert wurm.damage == 0 and gimli.damage == 0


def test_the_third_resolution_this_turn_makes_gimli_fight():
    scenario = _board(
        alice=["Grizzly Bears", "Raging Goblin", "Mogg Fanatic"], bob=["Grizzly Bears"]
    )
    gimli = scenario.creature(GIMLI)
    bears = scenario.creature("Grizzly Bears", "bob")
    for name in ("Grizzly Bears", "Raging Goblin"):
        _kill(scenario, name)
        _resolve_all(scenario)
    _kill(scenario, "Mogg Fanatic")
    scenario.will_choose_targets(bears, username="alice", source=GIMLI)
    _resolve_all(scenario)

    assert gimli.counter_count(PLUS) == 3
    assert bears.zone is Zone.GRAVEYARD, "Gimli, 6/5 with three counters, fights it"
    assert gimli.damage == 2
    assert gimli.zone is Zone.BATTLEFIELD


def test_the_fight_is_up_to_one_target_so_none_is_legal():
    scenario = _board(alice=["Grizzly Bears", "Raging Goblin", "Mogg Fanatic"])
    gimli = scenario.creature(GIMLI)
    for name in ("Grizzly Bears", "Raging Goblin", "Mogg Fanatic"):
        _kill(scenario, name)
        _resolve_all(scenario)
    assert gimli.counter_count(PLUS) == 3
    assert gimli.damage == 0


def test_the_fourth_resolution_does_not_fight_again():
    scenario = _board(
        alice=["Grizzly Bears", "Raging Goblin", "Mogg Fanatic", "Goblin Guide"],
        bob=["Craw Wurm"],
    )
    gimli = scenario.creature(GIMLI)
    wurm = scenario.creature("Craw Wurm", "bob")
    for name in ("Grizzly Bears", "Raging Goblin", "Mogg Fanatic"):
        _kill(scenario, name)
        _resolve_all(scenario)
    assert wurm.damage == 0, "no target was chosen for the third"
    scenario.will_choose_targets(wurm, username="alice", source=GIMLI)
    _kill(scenario, "Goblin Guide")
    _resolve_all(scenario)

    assert gimli.counter_count(PLUS) == 4
    assert wurm.damage == 0, "only the third resolution creates the reflexive ability"


def test_the_resolution_count_starts_over_next_turn():
    scenario = _board(
        alice=["Grizzly Bears", "Raging Goblin", "Mogg Fanatic"], bob=["Grizzly Bears"]
    )
    gimli = scenario.creature(GIMLI)
    bears = scenario.creature("Grizzly Bears", "bob")
    for name in ("Grizzly Bears", "Raging Goblin"):
        _kill(scenario, name)
        _resolve_all(scenario)
    while scenario.turn.active_player == "alice":
        scenario.advance()
        _resolve_all(scenario)

    scenario.will_choose_targets(bears, username="alice", source=GIMLI)
    _kill(scenario, "Mogg Fanatic")
    _resolve_all(scenario)
    assert gimli.counter_count(PLUS) == 3
    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0


def test_an_opponents_creature_dying_does_not_trigger_it():
    scenario = _board(bob=["Grizzly Bears"])
    gimli = scenario.creature(GIMLI)
    _kill(scenario, "Grizzly Bears", owner="bob")
    _resolve_all(scenario)
    assert gimli.counter_count(PLUS) == 0
