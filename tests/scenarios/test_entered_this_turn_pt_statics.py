"""Two static P/T abilities gated on how many creatures entered the
battlefield under their controller's control this turn (CR 611.3a: neither is
"locked in" - both are re-asked on every computation).

- **Bristlebane Outrider** - "As long as another creature entered the
  battlefield under your control this turn, this creature gets +2/+0." The
  plain per-player `turn_facts` ledger this project already has for "did a
  creature enter" cannot answer this on its own: it stays true on the one
  turn Bristlebane Outrider itself is the *only* creature that entered, which
  is exactly the case "another" excludes. `LayerContext.entered_this_turn_ids`
  (`Game._compute_board`'s read of `CardState.turn_entered` against the
  current turn number) is the per-object identity check that closes the gap:
  the condition holds when two or more creatures entered this turn, or when
  exactly one did and it was not this object.
- **Kinbinding** - "Creatures you control get +X/+X, where X is the number of
  creatures that entered the battlefield under your control this turn." A
  group pump whose magnitude is `Game.turn_counts`'s own running total for
  `entered_type:creature` (the counting twin `Game._announce_entry` now
  writes alongside the boolean `turn_facts` entry), fixed at build time the
  same way every other turn-count-gated static in `machines/layers.py` is.

CR numbers verified this session with `mise run rules:find`:

- **CR 611.3a** - a static ability's effect "isn't 'locked in'; it applies at
  any given moment to whatever its text indicates, and lasts as long as the
  ability continues to apply to that object."
- **CR 208.2a** - printed characteristics, the baseline these pumps add to.
"""

from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _pt(scenario, state):
    return scenario.game.power_of(state), scenario.game.toughness_of(state)


# -- Bristlebane Outrider ------------------------------------------------------


def test_bristlebane_outrider_is_unpumped_with_nothing_entered_this_turn():
    scenario = (
        Scenario().player("alice", battlefield=["Bristlebane Outrider"]).player("bob").build()
    )
    outrider = scenario.creature("Bristlebane Outrider", "alice")
    assert _pt(scenario, outrider) == (3, 5)


def test_bristlebane_outrider_pumps_once_another_creature_enters_this_turn():
    scenario = (
        Scenario()
        .player("alice", hand=["Llanowar Elves"], battlefield=["Bristlebane Outrider"])
        .player("bob")
        .build()
    )
    outrider = scenario.creature("Bristlebane Outrider", "alice")
    assert _pt(scenario, outrider) == (3, 5)

    scenario.put_onto_battlefield("Llanowar Elves", "alice")

    assert _pt(scenario, outrider) == (5, 5), "+2/+0: another creature entered this turn"


def test_bristlebane_outrider_does_not_pump_itself_off_its_own_entry():
    """The one case a plain boolean "did a creature enter" ledger gets wrong:
    Bristlebane Outrider is the *only* creature that entered this turn, so
    "another" is false even though "a creature entered" is true."""
    scenario = Scenario().player("alice", hand=["Bristlebane Outrider"]).player("bob").build()
    outrider = scenario.put_onto_battlefield("Bristlebane Outrider", "alice")

    assert _pt(scenario, outrider) == (3, 5), 'no "other" creature entered - only itself'


def test_bristlebane_outrider_pumps_once_a_second_creature_also_enters():
    scenario = (
        Scenario()
        .player("alice", hand=["Bristlebane Outrider", "Llanowar Elves"])
        .player("bob")
        .build()
    )
    outrider = scenario.put_onto_battlefield("Bristlebane Outrider", "alice")
    assert _pt(scenario, outrider) == (3, 5)

    scenario.put_onto_battlefield("Llanowar Elves", "alice")

    assert _pt(scenario, outrider) == (5, 5), "now two creatures entered - it is no longer alone"


def test_bristlebane_outriders_own_entry_this_turn_never_helps_a_teammates_copy():
    """A second Bristlebane Outrider entering counts as "another creature"
    for the first one, and vice versa - "another" excludes only the object
    asking, not every creature of that name (CR 201.2a's copiable name is not
    in play here at all)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Bristlebane Outrider"], battlefield=["Bristlebane Outrider"])
        .player("bob")
        .build()
    )
    first = scenario.creature("Bristlebane Outrider", "alice")
    assert _pt(scenario, first) == (3, 5)

    second = scenario.put_onto_battlefield("Bristlebane Outrider", "alice")

    assert _pt(scenario, first) == (5, 5), "the second Outrider is 'another creature' for the first"
    assert _pt(scenario, second) == (3, 5), "but the first Outrider entered on an earlier turn"


# -- Kinbinding -----------------------------------------------------------


def test_kinbinding_pumps_by_the_number_of_creatures_that_entered_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Llanowar Elves", "Hill Giant"],
            battlefield=["Kinbinding", "Goldmeadow Dodger"],
        )
        .player("bob")
        .build()
    )
    dodger = scenario.creature("Goldmeadow Dodger", "alice")
    assert _pt(scenario, dodger) == (1, 1), "nothing entered this turn yet - X is 0"

    scenario.put_onto_battlefield("Llanowar Elves", "alice")
    elves = scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "alice")
    assert _pt(scenario, dodger) == (2, 2), "one creature entered - X is 1"
    assert _pt(scenario, elves) == (2, 2), "the entering creature is itself a creature you control"

    scenario.put_onto_battlefield("Hill Giant", "alice")

    assert _pt(scenario, dodger) == (3, 3), "two creatures entered - X is 2"


def test_kinbinding_does_not_pump_creatures_from_a_different_controller():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Kinbinding", "Goldmeadow Dodger"])
        .player("bob", hand=["Llanowar Elves"])
        .build()
    )
    dodger = scenario.creature("Goldmeadow Dodger", "alice")
    scenario.put_onto_battlefield("Llanowar Elves", "bob")

    assert _pt(scenario, dodger) == (1, 1), "bob's own entry does not count for alice's Kinbinding"
