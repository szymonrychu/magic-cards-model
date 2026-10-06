"""Pump-then-fight with colour-qualified targets: "Target green creature you
control gets +2/+2 until end of turn. It fights target green creature an
opponent controls."

Rules verified with `mise run rules:find`:

- **CR 701.14a** - fight: "Each of those creatures deals damage equal to its
  power to the other creature."
- **CR 608.2c** - the pump happens first, in the order written, so the pumped
  power is what the fight deals.
- **CR 608.2b** - a target that is illegal on resolution is not affected: the
  spell still resolves for the legal one, and with only one creature left
  nothing fights.
- **CR 115.1 / 601.2c** - the colour words are part of each target's
  requirement, checked when the targets are chosen.

Reported card: Hunt the Hunter. No second printing carries a colour-qualified
pump-then-fight pair (Scryfall search over every Modern/Pioneer/Standard card,
2026-10-06), so the widened reader is proven on Hunt the Hunter's corner cases
and its unqualified template is pinned on two other printings
(Wild Instincts, Epic Confrontation) that go through the same pair reader.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _notices(scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _power_toughness(scenario, card) -> tuple[int | None, int | None]:
    return (
        scenario.game.continuous_effects.board(scenario.game.battlefield).of(card).power_toughness
    )


def _hunt_board(spell="Hunt the Hunter", lands=("Forest",)) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[spell],
            battlefield=[*lands, "Grizzly Bears", "Llanowar Elves", "Goblin Guide"],
        )
        .player("bob", battlefield=["Runeclaw Bear", "Gray Ogre", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_hunt_the_hunter_pumps_the_green_creature_then_it_fights_the_green_creature():
    scenario = _hunt_board()
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Runeclaw Bear", "bob")
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_and_resolve("Hunt the Hunter", forest, username="alice", targets=[mine, theirs])
    scenario.state_based_actions()

    assert _power_toughness(scenario, mine) == (4, 4)
    assert theirs.zone is Zone.GRAVEYARD
    assert mine.zone is Zone.BATTLEFIELD
    assert mine.damage == 2
    assert _notices(scenario) == []


def test_the_pump_lands_before_the_fight_so_the_extra_power_kills_a_bigger_creature():
    """CR 608.2c: a 1/1 Llanowar Elves is 3/3 when it fights, so it deals 3."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Hunt the Hunter"],
            battlefield=["Forest", "Llanowar Elves"],
        )
        .player("bob", battlefield=["Runeclaw Bear"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elves = scenario.creature("Llanowar Elves", "alice")
    bear = scenario.creature("Runeclaw Bear", "bob")
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_and_resolve("Hunt the Hunter", forest, username="alice", targets=[elves, bear])
    scenario.state_based_actions()

    assert bear.zone is Zone.GRAVEYARD
    assert elves.zone is Zone.BATTLEFIELD  # 3/3 took 2


def test_a_creature_that_is_not_green_is_not_a_legal_target_on_either_side():
    scenario = _hunt_board()
    goblin = scenario.creature("Goblin Guide", "alice")  # red
    mine = scenario.creature("Grizzly Bears", "alice")
    ogre = scenario.creature("Gray Ogre", "bob")  # red
    theirs = scenario.creature("Runeclaw Bear", "bob")

    with pytest.raises(ValueError):
        scenario.cast("Hunt the Hunter", username="alice", targets=[goblin, theirs])
    with pytest.raises(ValueError):
        scenario.cast("Hunt the Hunter", username="alice", targets=[mine, ogre])


def test_if_the_opposing_target_is_gone_the_pump_still_happens_but_nothing_fights():
    """CR 608.2b / 701.14b."""
    scenario = _hunt_board()
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Runeclaw Bear", "bob")
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_onto_stack("Hunt the Hunter", forest, username="alice", targets=[mine, theirs])
    scenario.game.return_to_hand(theirs)
    scenario.pass_until_resolved()

    assert _power_toughness(scenario, mine) == (4, 4)
    assert mine.damage == 0
    assert _notices(scenario) == []


def test_if_your_target_is_gone_nothing_is_pumped_and_nothing_fights():
    scenario = _hunt_board()
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Runeclaw Bear", "bob")
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_onto_stack("Hunt the Hunter", forest, username="alice", targets=[mine, theirs])
    scenario.game.return_to_hand(mine)
    scenario.pass_until_resolved()

    assert theirs.zone is Zone.BATTLEFIELD
    assert theirs.damage == 0


def test_the_pump_ends_at_end_of_turn():
    scenario = _hunt_board()
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Runeclaw Bear", "bob")
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_and_resolve("Hunt the Hunter", forest, username="alice", targets=[mine, theirs])
    scenario.game.continuous_effects.end_the_turn(scenario.game)

    assert _power_toughness(scenario, mine) == (2, 2)


# -- the unqualified template still reads through the same pair reader --------


@pytest.mark.parametrize(
    ("spell", "lands", "bonus"),
    [("Wild Instincts", ("Forest",) * 4, 2), ("Epic Confrontation", ("Forest",) * 2, 1)],
)
def test_the_unqualified_template_is_unchanged(spell, lands, bonus):
    scenario = _hunt_board(spell, lands)
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Gray Ogre", "bob")  # red: no colour word printed
    sources = scenario.untapped_sources(*lands, username="alice")
    scenario.cast_and_resolve(spell, *sources, username="alice", targets=[mine, theirs])
    scenario.state_based_actions()

    assert _power_toughness(scenario, mine)[0] == 2 + bonus
    assert theirs.zone is Zone.GRAVEYARD
    assert _notices(scenario) == []
