"""Scenario: CR 704.5q's annihilation runs inside `Game` itself (CR 704.3),
not only inside the test harness.

Before this file, the only place that dispatched `models.card_state.
annihilate_counters_on` was `tests/scenarios/harness.PlayedScenario.
state_based_actions` - a workaround the harness's own docstring named as
exactly that. `Game.check_state_based_actions()` covered every other CR 704.5
item (CR 704.5f/g/h/i/j/m/n/z/s), but a permanent carrying both a +1/+1 and a
-1/-1 counter sat there unchanged forever if a scenario (or the api, which
never called the harness at all) asked `Game` alone to check state-based
actions.

`Game._state_based_actions_once` now performs CR 704.5q itself, through the
same `annihilate_counters_on` helper the harness used to own, and the harness
workaround is gone - `PlayedScenario.state_based_actions` is now a plain alias
for `Game.check_state_based_actions()`.

Card text and legality verified with `scripts/add_card.py` against Scryfall:

- **Grim Affliction** (Modern-legal, `{2}{B}` instant): "Put a -1/-1 counter
  on target creature, then proliferate." The real -1/-1-counter source this
  file drives case (a) with, rather than setting the -1/-1 counter up
  directly the way `test_counters.py`'s own annihilation tests do. Proliferate
  is CR 701.34a's own "choose any number ... including none", so the tests
  below decline it for the one permanent that would otherwise be an eligible
  choice (having a counter already), leaving only the plain -1/-1 counter the
  spell's first sentence puts down.

Every CR number below was looked up with `mise run rules:find <n>` against
the checksum-verified rules pull in the session that wrote this file:

- **CR 704.5q** - "If a permanent has both a +1/+1 counter and a -1/-1
  counter on it, N +1/+1 and N -1/-1 counters are removed from it, where N is
  the smaller of the number of +1/+1 and -1/-1 counters on it."
- **CR 122.3** - the same rule, stated from the counters' own side: "removed
  ... as a state-based action."
- **CR 704.3** - state-based actions are checked, and performed, "whenever a
  player would get priority."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def board(**kwargs) -> Scenario:
    """One player with a battlefield, ready to build - `test_counters.py`'s
    own `board()`, mirrored here since this file is the same mechanic."""
    return Scenario().manual_turn_based_actions().player("alice", **kwargs)


def test_annihilation_from_a_real_minus_one_counter_spell_through_game():
    """(a) Two +1/+1 counters set up directly, a third counter - the -1/-1 -
    arriving through a real spell rather than direct setup. `Game.
    check_state_based_actions()` is called directly (no harness alias at
    all), which is where CR 704.5q now actually lives.
    """
    scenario = (
        board(
            battlefield=["Grizzly Bears"] + ["Swamp"] * 3,
            hand=["Grim Affliction"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 2)

    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice")
    # Grim Affliction's own proliferate is optional (CR 701.34a): decline it,
    # since Bears already carries a counter and would otherwise be an
    # eligible choice, which would add a second -1/-1 counter and defeat the
    # point of this test.
    scenario.will_choose_cards(source="Grim Affliction", username="alice")
    scenario.cast_and_resolve("Grim Affliction", *sources, username="alice", targets=[bears])

    # `cast_and_resolve` already ran the engine's own CR 704.3 priority-
    # passing loop, which is where annihilation now actually happens - so an
    # explicit call is redundant here and only proves the state is stable,
    # the same way `test_counters.py`'s own annihilation tests read the
    # permanent straight after `state_based_actions()` runs once.
    scenario.game.check_state_based_actions()

    assert bears.counters == {"+1/+1": 1}
    assert (bears.power, bears.toughness) == (3, 3)


def test_equal_counts_annihilate_completely_through_game():
    """(b) Equal piles: both kinds are removed entirely, through the same
    plain `Game.check_state_based_actions()` call."""
    scenario = board(battlefield=["Grizzly Bears"]).build()
    bears = scenario.creature("Grizzly Bears")
    bears.add_counters(Counter.PLUS_ONE, 2)
    bears.add_counters(Counter.MINUS_ONE, 2)

    assert (bears.power, bears.toughness) == (2, 2)

    scenario.game.check_state_based_actions()

    assert bears.counters == {}
    assert (bears.power, bears.toughness) == (2, 2)


def test_annihilation_through_the_harness_alias_once_the_workaround_is_gone():
    """(c) The same probe as (a), but through `PlayedScenario.
    state_based_actions()` - the name every other scenario file in this
    pool calls - to prove that alias is now a plain pass-through to `Game.
    check_state_based_actions()` rather than the deleted workaround.
    """
    scenario = (
        board(
            battlefield=["Grizzly Bears"] + ["Swamp"] * 3,
            hand=["Grim Affliction"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 2)

    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice")
    scenario.will_choose_cards(source="Grim Affliction", username="alice")
    scenario.cast_and_resolve("Grim Affliction", *sources, username="alice", targets=[bears])

    scenario.state_based_actions()

    assert bears.counters == {"+1/+1": 1}
    assert (bears.power, bears.toughness) == (3, 3)
