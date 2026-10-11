"""Scenario: "At the beginning of combat on your turn, target creature gains your
choice of first strike or vigilance until end of turn. If that creature is
equipped, it gains first strike and vigilance until end of turn instead."
(CR 608.2d the controller's choice at resolution, CR 611.2a the duration,
CR 613.1f the keyword grant, CR 301.5 equipped.)
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from tests.scenarios.harness import Scenario


def _board(*, equipped):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Éowyn, Lady of Rohan", "Grizzly Bears", "Bonesplitter"],
            library=["Island"] * 10,
        )
        .player("bob", library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.UPKEEP)
    bears = scenario.creature("Grizzly Bears", "alice")
    if equipped:
        next(s for s in scenario.game.battlefield if s.name == "Bonesplitter").attach_to(bears)
    return scenario, bears


def _begin_combat(scenario, bears):
    scenario.choose_trigger_targets("Éowyn, Lady of Rohan", [bears])
    for _ in range(10):
        scenario.advance()
        if scenario.step is Step.BEGINNING_OF_COMBAT:
            break
    while scenario.game.stack:
        scenario.resolve_top()


def test_an_unequipped_creature_gets_the_chosen_keyword_only():
    scenario, bears = _board(equipped=False)
    scenario.will_choose("Vigilance", source="Éowyn, Lady of Rohan")
    _begin_combat(scenario, bears)
    assert has_keyword(bears, "vigilance", scenario.game)
    assert not has_keyword(bears, "first strike", scenario.game)


def test_the_other_choice_gives_the_other_keyword():
    scenario, bears = _board(equipped=False)
    scenario.will_choose("First strike", source="Éowyn, Lady of Rohan")
    _begin_combat(scenario, bears)
    assert has_keyword(bears, "first strike", scenario.game)
    assert not has_keyword(bears, "vigilance", scenario.game)


def test_an_equipped_creature_gets_both_and_is_not_asked():
    scenario, bears = _board(equipped=True)
    _begin_combat(scenario, bears)
    assert has_keyword(bears, "first strike", scenario.game)
    assert has_keyword(bears, "vigilance", scenario.game)
    assert not [q for q in scenario.questions_asked() if q.source == "Éowyn, Lady of Rohan"]


def test_the_grant_ends_at_end_of_turn():
    scenario, bears = _board(equipped=True)
    _begin_combat(scenario, bears)
    for _ in range(20):
        scenario.advance()
        if scenario.turn.active_player == "bob":
            break
    assert not has_keyword(bears, "vigilance", scenario.game)
