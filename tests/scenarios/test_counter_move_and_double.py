"""SOS's counter-move and counter-double family: moving +1/+1 counters
between creatures (CR 122.5), and CR 701.10e's doubling.

- **Tester of the Tangential** - "At the beginning of combat on your turn,
  you may pay {X}. When you do, move X +1/+1 counters from this creature
  onto another target creature." CR 118.9's variable-amount cost, paid one
  generic mana at a time until declined or unaffordable (the same shape
  `machines/effects._parse_reflexive_pay_up_to_n_times_choose_modes_clause`
  already uses for a *fixed* repeat count), then CR 603.12's reflexive
  triggered ability with the paid X substituted in as a literal count.
  `counter_effects._reflexive_may_pay_x_move_counters` reads it.
- **Scrounging Bandar** (off-pool, the generality proof for `machines/
  effects._MOVE_COUNTER_RE`'s "onto another target" widening, and for the
  "you may move any number of counters" reader) - "you may move any number
  of +1/+1 counters from this creature onto another target creature." CR
  608.2d's own open amount, taken at the maximum available (the same
  documented scoped simplification `_parse_remove_up_to_n_counters_from_
  target_clause` already takes; no `DecisionKind` exists yet for an
  open-ended amount unconnected to a cost).
- **Growth Curve** - "Put a +1/+1 counter on target creature you control,
  then double the number of +1/+1 counters on that creature." CR 122.1's
  placement immediately followed by CR 701.10e's doubling of what the same
  target now carries, the just-placed counter included.
- **Solidarity of Heroes** (off-pool, the generality proof for the doubling
  primitive over a *multi*-target choice) - "Choose any number of target
  creatures. Double the number of +1/+1 counters on each of them."

Every CR number below was looked up with `mise run rules:find` (on-disk CR
effective 2026-09-25) in the session that wrote this file:

- **CR 118.9** - a cost that includes a variable amount of mana (announced,
  here paid a piece at a time as the resolving ability asks each time).
- **CR 603.12** - a resolving ability may instruct a player to take an
  action and create a reflexive triggered ability off it.
- **CR 122.5** - "move" a counter: remove it from the first object and put
  it on the second; if either half is impossible, neither happens.
- **CR 115.1, 115.6** - "another target" (CR 115.1's ordinary exclusion) and
  a chosen count of targets ("any number of").
- **CR 701.10e** - to double a kind of counters on a permanent, give it as
  many more of that kind as it already has.
- **CR 608.2c** - the resolving order of a printed instruction's own clauses
  (the placed counter is already there when the doubling clause reads the
  target's count).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

TESTER = "Tester of the Tangential"
BANDAR = "Scrounging Bandar"


def _tester_board(*, islands: int = 3) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=[TESTER, "Grizzly Bears"] + ["Island"] * islands)
        .player("bob")
    )


def _to_combat(scenario) -> None:
    scenario.advance()  # beginning of combat
    if scenario.stack_names():
        scenario.pass_until_resolved()


def test_tester_moves_paid_x_counters_to_another_target_creature():
    scenario = _tester_board(islands=3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tester = scenario.creature(TESTER, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    tester.add_counters(Counter.PLUS_ONE, 5)
    scenario.will_pay_the_mana_cost(True, source=TESTER, times=3)
    scenario.will_choose_targets(bears, source=TESTER)

    scenario.advance()  # beginning of combat: the trigger goes on the stack
    scenario.resolve_top()  # the trigger: pays {X}=3, queues the reflexive
    scenario.resolve_top()  # the reflexive: moves 3 counters onto the Bears

    assert tester.counter_count(Counter.PLUS_ONE) == 2
    assert bears.counter_count(Counter.PLUS_ONE) == 3


def test_tester_paying_zero_moves_nothing_and_creates_no_reflexive_trigger():
    """CR 118.3: declining the very first payment is always legal, and CR
    603.12's reflexive ability is only created once something was actually
    paid - "when you do" never fires on a payment of zero."""
    scenario = _tester_board(islands=3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tester = scenario.creature(TESTER, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    tester.add_counters(Counter.PLUS_ONE, 5)
    scenario.will_pay_the_mana_cost(False, source=TESTER, times=1)

    scenario.advance()
    scenario.resolve_top()  # the trigger: declines the payment

    assert scenario.stack_names() == [], "no reflexive ability was created"
    assert tester.counter_count(Counter.PLUS_ONE) == 5
    assert bears.counter_count(Counter.PLUS_ONE) == 0


def test_tester_x_is_capped_by_available_mana_not_by_counters_on_it():
    """The payment loop stops the moment {1} is no longer payable (CR
    118.3), independent of how many counters the creature actually has to
    move - X here is 2 (two Islands), well under the five counters on it."""
    scenario = _tester_board(islands=2).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tester = scenario.creature(TESTER, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    tester.add_counters(Counter.PLUS_ONE, 5)
    scenario.will_pay_the_mana_cost(True, source=TESTER, times=2)
    scenario.will_choose_targets(bears, source=TESTER)

    scenario.advance()
    scenario.resolve_top()
    scenario.resolve_top()

    assert tester.counter_count(Counter.PLUS_ONE) == 3
    assert bears.counter_count(Counter.PLUS_ONE) == 2


def _bandar_board() -> Scenario:
    return Scenario().player("alice", battlefield=[BANDAR, "Grizzly Bears"]).player("bob")


def test_bandar_moves_every_counter_it_has_onto_another_target_creature():
    scenario = _bandar_board().build()
    bandar = scenario.creature(BANDAR, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    bandar.add_counters(Counter.PLUS_ONE, 2)  # CR 614.12c: the printed enters-with, set
    # by hand since the scenario places it straight onto the battlefield rather than
    # casting or otherwise "entering" it (`put_onto_battlefield`'s own replacement path).
    scenario.will_take_the_may(True, source=BANDAR)
    scenario.will_choose_targets(bears, source=BANDAR)

    scenario.advance()  # untap -> upkeep: the trigger goes on the stack
    scenario.pass_until_resolved()

    assert bandar.counter_count(Counter.PLUS_ONE) == 0
    assert bears.counter_count(Counter.PLUS_ONE) == 2


def test_bandar_declining_the_move_leaves_its_own_counters_alone():
    scenario = _bandar_board().build()
    bandar = scenario.creature(BANDAR, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    bandar.add_counters(Counter.PLUS_ONE, 2)
    scenario.will_take_the_may(False, source=BANDAR)

    scenario.advance()
    scenario.pass_until_resolved()

    assert bandar.counter_count(Counter.PLUS_ONE) == 2
    assert bears.counter_count(Counter.PLUS_ONE) == 0


GROWTH_CURVE = "Growth Curve"
SOLIDARITY = "Solidarity of Heroes"


def test_growth_curve_puts_then_doubles_on_the_same_target():
    scenario = (
        Scenario()
        .player("alice", hand=[GROWTH_CURVE], battlefield=["Forest", "Island", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 2)

    sources = scenario.untapped_sources("Forest", "Island")
    scenario.cast_and_resolve(GROWTH_CURVE, *sources, targets=[bears])

    # Put one (2 -> 3), then double (3 -> 6).
    assert bears.counter_count(Counter.PLUS_ONE) == 6
    assert (bears.power, bears.toughness) == (2 + 6, 2 + 6), "Grizzly Bears base 2/2"


def test_growth_curve_on_a_creature_with_no_counters_yet():
    """Doubling zero counters is a legal no-op (CR 701.10e): the placed
    counter is the only one there to double, one becoming two."""
    scenario = (
        Scenario()
        .player("alice", hand=[GROWTH_CURVE], battlefield=["Forest", "Island", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    sources = scenario.untapped_sources("Forest", "Island")
    scenario.cast_and_resolve(GROWTH_CURVE, *sources, targets=[bears])

    assert bears.counter_count(Counter.PLUS_ONE) == 2


def test_solidarity_of_heroes_doubles_each_of_several_chosen_targets():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[SOLIDARITY],
            battlefield=[
                "Forest",
                "Forest",
                "Forest",
                "Forest",
                "Grizzly Bears",
                "Elder Gargaroth",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    gargaroth = scenario.creature("Elder Gargaroth", "alice")
    bears.add_counters(Counter.PLUS_ONE, 1)
    gargaroth.add_counters(Counter.PLUS_ONE, 3)

    # Strive: {1}{G} base, plus {1}{G} for the second target - {2}{G}{G} total.
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    scenario.cast_and_resolve(SOLIDARITY, *sources, targets=[bears, gargaroth])

    assert bears.counter_count(Counter.PLUS_ONE) == 2
    assert gargaroth.counter_count(Counter.PLUS_ONE) == 6
