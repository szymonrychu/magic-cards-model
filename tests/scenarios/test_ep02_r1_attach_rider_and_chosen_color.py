"""Scenario: three gaps in one file - an optional attach with a rider, an
Aura that attaches itself to the creature that entered, and a state trigger
on "no permanents of the chosen color".

- **Magitek Scythe** - "When this Equipment enters, you may attach it to target
  creature you control. If you do, that creature gains first strike until end
  of turn and must be blocked this turn if able."
- **Lurebound Scarecrow** - "As this creature enters, choose a color. When you
  control no permanents of the chosen color, sacrifice this creature."
- **Illusory Gains** (second printing of "attach this Aura to that creature",
  next to Prison Term in `test_ep01_r3_attach_keywords.py`) - "Whenever a
  creature an opponent controls enters, attach this Aura to that creature."
- **Darksteel Garrison** (fortify, CR 702.67a) - the one Modern/Pioneer/
  Standard-legal Fortification; `test_ep01_r3_attach_keywords.py` proves the
  keyword on it. Scryfall `t:fortification` lists only it and C.A.M.P., which
  is Commander-only (2026-10-13), so there is no second printing to prove it
  on. See MEMORY.md.

Rules, each read with `mise run rules:find` in the session that wrote this:

- **CR 701.3a** - to attach; **CR 608.2c** - "if you do" depends on the
  earlier instruction having happened.
- **CR 509.1c** - "must be blocked if able" is a requirement on the defending
  player's declaration; **CR 611.2a** - a one-shot effect with a duration.
- **CR 603.8** - a state trigger fires as soon as the game state matches, and
  not again until it has left the stack.
- **CR 614.12a** - the choice made as the permanent enters is read back.
- **CR 105.2** - an object's colors; a colorless object is none of them.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario


def settle(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def test_every_card_here_is_fully_handled():
    for name in ("Magitek Scythe", "Lurebound Scarecrow", "Illusory Gains", "Darksteel Garrison"):
        bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
        assert not bad, (name, bad)


# -- Magitek Scythe ------------------------------------------------------------


def _scythe_board(*, bob_battlefield=("Hill Giant",), manual=False):
    scenario = Scenario()
    if manual:
        scenario = scenario.manual_turn_based_actions()
    scenario = (
        scenario.player(
            "alice",
            hand=["Magitek Scythe"],
            battlefield=["Mountain", "Mountain", "Mountain", "Mountain", "Grizzly Bears"],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob_battlefield), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature("Grizzly Bears", "alice")


def _cast_scythe(scenario, bears, *, accept: bool):
    scenario.choose_trigger_targets("Magitek Scythe", [bears])
    scenario.will_take_the_may(accept, source="Magitek Scythe")
    scythe = scenario.cast_and_resolve(
        "Magitek Scythe", *scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    )
    settle(scenario)
    return scythe


def test_magitek_scythe_attaches_and_gives_first_strike():
    scenario, bears = _scythe_board()

    scythe = _cast_scythe(scenario, bears, accept=True)

    assert scythe.attached_to == bears.id
    assert has_keyword(bears, "First strike", scenario.game)
    assert scenario.game.power_of(bears) == 4  # Equipped creature gets +2/+1


def test_magitek_scythe_makes_the_creature_must_be_blocked():
    scenario, bears = _scythe_board()
    _cast_scythe(scenario, bears, accept=True)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)

    with pytest.raises(ValueError, match="must be blocked"):
        scenario.no_blocks()


def test_must_be_blocked_is_satisfied_by_any_one_blocker():
    scenario, bears = _scythe_board(bob_battlefield=("Hill Giant", "Craw Wurm"))
    _cast_scythe(scenario, bears, accept=True)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)

    scenario.block(bears, scenario.creature("Hill Giant", "bob"))

    assert [blocker.name for blocker in scenario.blockers()] == ["Hill Giant"]


def test_must_be_blocked_does_not_bind_a_defender_with_no_creatures():
    scenario, bears = _scythe_board(bob_battlefield=())
    _cast_scythe(scenario, bears, accept=True)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)

    scenario.no_blocks()

    assert scenario.blockers() == []


def test_declining_the_attach_gives_nothing():
    scenario, bears = _scythe_board()

    scythe = _cast_scythe(scenario, bears, accept=False)

    assert scythe.zone is Zone.BATTLEFIELD
    assert scythe.attached_to is None
    assert not has_keyword(bears, "First strike", scenario.game)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.no_blocks()  # no block requirement was created


def test_the_rider_wears_off_at_end_of_turn_but_the_equipment_stays():
    scenario, bears = _scythe_board(manual=True)
    scythe = _cast_scythe(scenario, bears, accept=True)

    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    scenario.turn_based_actions()

    assert scythe.attached_to == bears.id
    assert not has_keyword(bears, "First strike", scenario.game)
    assert scenario.game.power_of(bears) == 4  # still equipped: +2/+1


def test_a_target_that_left_before_the_trigger_resolved_leaves_the_scythe_unattached():
    scenario, bears = _scythe_board()
    scenario.choose_trigger_targets("Magitek Scythe", [bears])
    scenario.will_take_the_may(True, source="Magitek Scythe")
    scythe = scenario.cast_and_resolve(
        "Magitek Scythe", *scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    )
    scenario.game.destroy(bears)
    settle(scenario)

    assert scythe.attached_to is None


# -- Illusory Gains: "attach this Aura to that creature" ------------------------


def _gains_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Hill Giant"],
            battlefield=["Illusory Gains", "Grizzly Bears"],
            library=["Island"] * 5,
        )
        .player("bob", hand=["Craw Wurm"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gains = scenario.find("Illusory Gains", Zone.BATTLEFIELD, "alice")
    gains.attach_to(scenario.creature("Grizzly Bears", "alice"))
    return scenario, gains


def test_illusory_gains_moves_to_a_creature_an_opponent_puts_onto_the_battlefield():
    scenario, gains = _gains_board()

    wurm = scenario.put_onto_battlefield("Craw Wurm", "bob")
    settle(scenario)

    assert gains.attached_to == wurm.id
    assert scenario.game.controller_of(wurm).username == "alice"  # You control enchanted creature


def test_illusory_gains_ignores_a_creature_its_controller_puts_onto_the_battlefield():
    scenario, gains = _gains_board()
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.put_onto_battlefield("Hill Giant", "alice")
    settle(scenario)

    assert gains.attached_to == bears.id


def test_illusory_gains_is_not_optional():
    """Unlike Prison Term, no "you may": no question is asked."""
    scenario, gains = _gains_board()

    scenario.put_onto_battlefield("Craw Wurm", "bob")
    settle(scenario)

    assert scenario.questions_asked() == []


# -- Lurebound Scarecrow ----------------------------------------------------------


def _scarecrow_board(chosen: Color, *, alice=("Grizzly Bears",), bob=("Hill Giant",)):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lurebound Scarecrow"],
            battlefield=list(alice),
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose(chosen.value, source="Lurebound Scarecrow")
    scarecrow = scenario.put_onto_battlefield("Lurebound Scarecrow", "alice")
    settle(scenario)
    return scenario, scarecrow


def test_the_scarecrow_stays_while_you_control_a_permanent_of_the_chosen_color():
    scenario, scarecrow = _scarecrow_board(Color.GREEN)

    assert scarecrow.zone is Zone.BATTLEFIELD


def test_the_scarecrow_is_sacrificed_at_once_when_you_control_none_of_that_color():
    scenario, scarecrow = _scarecrow_board(Color.RED)  # alice only has a green bear

    assert scarecrow.zone is Zone.GRAVEYARD


def test_an_opponents_permanent_of_the_chosen_color_does_not_count():
    scenario, scarecrow = _scarecrow_board(Color.RED, bob=("Hill Giant",))

    assert scarecrow.zone is Zone.GRAVEYARD  # bob's red Hill Giant is not yours


def test_the_scarecrow_itself_is_colorless_and_never_counts():
    scenario, scarecrow = _scarecrow_board(Color.GREEN, alice=())

    assert scarecrow.zone is Zone.GRAVEYARD


def test_losing_the_last_permanent_of_the_color_sacrifices_it_but_losing_one_of_two_does_not():
    scenario, scarecrow = _scarecrow_board(Color.GREEN, alice=("Grizzly Bears", "Elvish Mystic"))
    bears = scenario.creature("Grizzly Bears", "alice")
    mystic = scenario.creature("Elvish Mystic", "alice")

    scenario.game.destroy(bears)
    settle(scenario)
    assert scarecrow.zone is Zone.BATTLEFIELD  # the Mystic is still green

    scenario.game.destroy(mystic)
    settle(scenario)
    assert scarecrow.zone is Zone.GRAVEYARD


# -- The condition on a second source -------------------------------------------


def _hall_board(chosen: Color, *, alice=()):
    scenario = (
        Scenario()
        .player("alice", hand=["Hall of Triumph"], battlefield=list(alice), library=["Island"] * 5)
        .player("bob", battlefield=["Hill Giant"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose(chosen.value, source="Hall of Triumph")
    hall = scenario.put_onto_battlefield("Hall of Triumph", "alice")
    return scenario, hall


@pytest.mark.parametrize(
    ("condition", "chosen", "expected"),
    [
        ("you control no creatures of the chosen color", Color.GREEN, False),
        ("you control no creatures of the chosen color", Color.RED, True),
        ("you control a creature of the chosen color", Color.GREEN, True),
        ("you control a creature of the chosen color", Color.WHITE, False),
        ("you control two or more creatures of the chosen color", Color.GREEN, True),
        ("you control two or more creatures of the chosen color", Color.RED, False),
        ("you control no permanents of the chosen color", Color.GREEN, False),
    ],
)
def test_the_chosen_color_reads_as_a_board_quality_for_any_source(condition, chosen, expected):
    scenario, hall = _hall_board(chosen, alice=("Grizzly Bears", "Elvish Mystic"))

    assert scenario.game.condition_holds("alice", condition, hall) is expected


def test_a_source_that_chose_nothing_has_no_chosen_color():
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Grizzly Bears", "Darksteel Garrison"], library=["Island"] * 5
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    garrison = scenario.find("Darksteel Garrison", Zone.BATTLEFIELD, "alice")

    assert scenario.game.condition_holds(
        "alice", "you control no creatures of the chosen color", garrison
    )
