"""Lost in the Maze: "When this enchantment enters, tap X target creatures.
Put a stun counter on each of those creatures you don't control." (EP-01 R2,
T2 residual clause).

CR numbers verified with `mise run rules:find`:

- CR 107.3m: the X of an enters-the-battlefield trigger is the X its spell was
  cast with, which is how many creatures get targeted.
- CR 122.1d: a stun counter replaces the next untap of its permanent.
- CR 608.2c: tap first, then count - "those creatures" is exactly the ones just
  tapped, and "you don't control" narrows them by the ability's controller.

The tail is the same "each of those creatures" anaphora Hapatra, the Desert
Frost reads for its own enters trigger, with a controller restriction on top.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

MAZE_LANDS = ["Island"] * 5


def _board(alice=(), bob=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lost in the Maze"],
            battlefield=[*MAZE_LANDS, *alice],
            library=["Plains"] * 4,
        )
        .player("bob", battlefield=list(bob), library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_maze(scenario, x, targets=()):
    if targets:
        scenario.will_choose_targets(*targets)
    casting = scenario.cast("Lost in the Maze", "alice")
    payment = casting.determine_cost(x_value=x)
    scenario.pay_with(payment, *scenario.untapped_sources(*(["Island"] * (x + 2))))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()


def test_taps_x_creatures_and_stuns_only_the_ones_you_dont_control():
    scenario = _board(alice=["Grizzly Bears"], bob=["Hill Giant"])
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Hill Giant", "bob")

    _cast_maze(scenario, 2, [mine, theirs])

    assert mine.tapped and theirs.tapped
    assert mine.counters[Counter.STUN] == 0
    assert theirs.counters[Counter.STUN] == 1


def test_x_one_taps_one_creature_and_leaves_the_rest_alone():
    scenario = _board(bob=["Hill Giant", "Runeclaw Bear"])
    giant = scenario.creature("Hill Giant", "bob")
    other = scenario.creature("Runeclaw Bear", "bob")

    _cast_maze(scenario, 1, [giant])

    assert giant.tapped and giant.counters[Counter.STUN] == 1
    assert other.untapped and other.counters[Counter.STUN] == 0


def test_the_stun_counter_eats_the_next_untap():
    scenario = _board(bob=["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")
    _cast_maze(scenario, 1, [giant])

    scenario.player("bob").untap_all(scenario.game.permanents_controlled_by("bob"))
    assert giant.tapped
    assert giant.counters[Counter.STUN] == 0
    scenario.player("bob").untap_all(scenario.game.permanents_controlled_by("bob"))
    assert giant.untapped


def test_x_zero_does_nothing():
    scenario = _board(bob=["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")
    _cast_maze(scenario, 0)
    assert giant.untapped
    assert giant.counters[Counter.STUN] == 0
    assert scenario.find("Lost in the Maze", Zone.BATTLEFIELD, "alice")
