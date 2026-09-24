"""The per-turn "choose one that hasn't been chosen this turn" reset (task
C02-T7): **The Vision** - "Whenever you cast a noncreature spell, choose one
that hasn't been chosen this turn - Solar Beam / Density Control /
Technopathy."

C01-T6 already read the *shape* of this trigger (`Game._announce_trigger_
modes`'s `exclusive` filter, `CardState.chosen_modal_options`), built against
Gollum, Riddle Master's own unqualified "choose one that hasn't been chosen -"
- a *permanent*, once-per-game-per-mode exclusion with no reset at all. The
Vision's own instruction adds "this turn", which is a different rule (CR
514.2's "this turn" effects end at cleanup): re-using the permanent memory
unmodified means Vision would never re-offer a used mode on a later turn
either, silently over-restricting it forever after its first three castings
this game - a real bug, not a verified-clean shape. This task widens the
reader with a second, per-turn field (`CardState.chosen_modal_options_this_
turn`), populated only for a "this turn"-qualified instruction and cleared
every cleanup step (`Game.cleanup_step`), leaving Gollum's own unqualified
field, and its behaviour, untouched.

Every rule cited here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 700.2b/603.3c** - a modal ability's modes are chosen as it goes on the
  stack; an option "illegal or impossible" (here: already used this turn)
  can't be chosen.
- **CR 514.1/514.2** - the cleanup step's turn-based actions, including "all
  ... 'this turn' effects end".
- **CR 608.2d** - the player announces choices an effect offers as it is
  applied; a scripted answer naming an option not offered is refused (this
  file proves the exclusion by relying on that refusal).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from tests.scenarios.harness import Scenario

_SOLAR_BEAM = "Solar Beam — The Vision gains double strike until end of turn."
_TECHNOPATHY = "Technopathy — Draw a card."


def _cast_bolt(scenario: Scenario, mountain) -> None:
    casting = scenario.cast("Lightning Bolt")
    casting.choose_targets(["bob"])
    scenario.pay_with(casting.begin_paying(), mountain)
    scenario.put_on_stack(casting)
    while scenario.game.stack:
        scenario.resolve_top()


def _cast_giant_growth(scenario: Scenario, forest, target) -> None:
    casting = scenario.cast("Giant Growth")
    casting.choose_targets([target])
    scenario.pay_with(casting.begin_paying(), forest)
    scenario.put_on_stack(casting)
    while scenario.game.stack:
        scenario.resolve_top()


def test_a_mode_already_chosen_this_turn_is_not_offered_again():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Vision", "Mountain", "Forest"],
            hand=["Lightning Bolt", "Giant Growth"],
            library=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vision = scenario.creature("The Vision", "alice")
    (mountain,) = scenario.untapped_sources("Mountain")
    (forest,) = scenario.untapped_sources("Forest")

    scenario.will_choose_mode(_TECHNOPATHY)
    _cast_bolt(scenario, mountain)
    assert [state.name for state in scenario.player("alice").hand] == ["Giant Growth", "Forest"]
    assert vision.chosen_modal_options_this_turn == (_TECHNOPATHY,)

    # Technopathy was already chosen this turn; scripting it again is refused
    # (CR 608.2d: "can't choose an option that's illegal or impossible"),
    # proving it is genuinely excluded from the second offer rather than
    # merely un-picked.
    scenario.will_choose_mode(_TECHNOPATHY)
    with pytest.raises(ValueError):
        _cast_giant_growth(scenario, forest, vision)


def test_a_mode_chosen_last_turn_is_offered_again_after_cleanup():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Vision", "Mountain", "Mountain"],
            hand=["Lightning Bolt", "Lightning Bolt"],
            library=["Forest", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vision = scenario.creature("The Vision", "alice")
    mountains = scenario.untapped_sources("Mountain", "Mountain")

    scenario.will_choose_mode(_TECHNOPATHY)
    _cast_bolt(scenario, mountains[0])
    assert vision.chosen_modal_options_this_turn == (_TECHNOPATHY,)

    scenario.game.cleanup_step()  # CR 514.2: "this turn" effects end
    assert vision.chosen_modal_options_this_turn == ()

    scenario.will_choose_mode(_TECHNOPATHY)
    _cast_bolt(scenario, mountains[1])
    drawn = [state.name for state in scenario.player("alice").hand]
    assert drawn == ["Forest", "Island"] or drawn == ["Island", "Forest"]
    assert vision.chosen_modal_options_this_turn == (_TECHNOPATHY,)


def test_a_different_mode_is_still_offered_in_the_same_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Vision", "Mountain", "Forest"],
            hand=["Lightning Bolt", "Giant Growth"],
            library=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vision = scenario.creature("The Vision", "alice")
    (mountain,) = scenario.untapped_sources("Mountain")
    (forest,) = scenario.untapped_sources("Forest")

    scenario.will_choose_mode(_TECHNOPATHY)
    _cast_bolt(scenario, mountain)

    scenario.will_choose_mode(_SOLAR_BEAM)
    _cast_giant_growth(scenario, forest, vision)

    assert vision.chosen_modal_options_this_turn == (_TECHNOPATHY, _SOLAR_BEAM)
    assert has_keyword(vision, Keyword.DOUBLE_STRIKE, scenario.game)
