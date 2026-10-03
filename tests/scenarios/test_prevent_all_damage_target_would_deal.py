"""Preventing all damage a targeted permanent would deal, in the word order
"prevent all damage target permanent would deal", with a duration.

- Gideon of the Trials: "+1: Until your next turn, prevent all damage target
  permanent would deal." - CR 615.1a's prevention effect keyed to one source,
  lasting CR 611.2a's stated "until your next turn".

The "dealt by target creature this turn" word order (Old Fat Spider Can't See
Me, Boros Fury-Shield) is `test_saga_duration_effects.py`'s and the same
reader's.

Rules, each looked up this session with `mise run rules:find`:

- **CR 615.1a** - "Effects that use the word 'prevent' are prevention
  effects."
- **CR 611.2a** - a continuous effect from a resolving ability "lasts as long
  as stated by the spell or ability creating it".
- **CR 400.7** - a permanent that leaves and returns is a new object the
  shield never named.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

GIDEON = "Gideon of the Trials"
PLUS_ONE = 0
BALLISTA = "Walking Ballista"
PING = 1  # "Remove a +1/+1 counter from this creature: It deals 1 damage to any target."


def _board(*, bob_extra=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=[GIDEON], library=["Plains"] * 8)
        .player("bob", battlefield=[BALLISTA, *bob_extra], library=["Forest"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ballista = scenario.creature(BALLISTA, "bob")
    scenario.game.add_counters(ballista, "+1/+1", 3)
    return scenario, ballista


def _gideon_plus_one(scenario, target):
    gideon = scenario.find(GIDEON, Zone.BATTLEFIELD, "alice")
    scenario.activate(gideon, index=PLUS_ONE, targets=[target])
    scenario.resolve_top()
    return gideon


def _ping(scenario, ballista, target):
    if scenario.priority_holder != "bob":
        scenario.pass_priority(scenario.priority_holder)
    scenario.activate(ballista, index=PING, username="bob", targets=[target])
    scenario.resolve_top()


def _next_turn(scenario):
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
    scenario.start_at(Step.PRECOMBAT_MAIN)


def test_damage_the_target_would_deal_is_prevented():
    scenario, ballista = _board()
    _gideon_plus_one(scenario, ballista)

    _ping(scenario, ballista, "alice")

    assert scenario.player("alice").life == 20


def test_the_shield_lasts_through_the_opponents_turn():
    scenario, ballista = _board()
    gideon = _gideon_plus_one(scenario, ballista)

    _next_turn(scenario)  # bob's turn
    _ping(scenario, ballista, gideon)

    assert gideon.counters["loyalty"] == 4  # 3 printed, +1


def test_the_shield_ends_when_its_controllers_next_turn_begins():
    scenario, ballista = _board()
    _gideon_plus_one(scenario, ballista)

    _next_turn(scenario)  # bob's
    _next_turn(scenario)  # alice's: the duration is over
    _ping(scenario, ballista, "alice")

    assert scenario.player("alice").life == 19


def test_damage_from_another_source_is_not_prevented():
    scenario, ballista = _board(bob_extra=[BALLISTA])
    other = next(
        permanent
        for permanent in scenario.game.permanents_controlled_by("bob")
        if permanent.name == BALLISTA and permanent.id != ballista.id
    )
    scenario.game.add_counters(other, "+1/+1", 1)
    _gideon_plus_one(scenario, ballista)

    _ping(scenario, other, "alice")

    assert scenario.player("alice").life == 19
