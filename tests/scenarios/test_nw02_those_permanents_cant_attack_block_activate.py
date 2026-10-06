"""A spell's rider "Until your next turn, those permanents can't attack or
block and their activated abilities can't be activated." - detain's wording
written out - behind a mana-spent gate.

Rules verified with `mise run rules:find`:

- **CR 611.2a** - the effect lasts as long as stated; "until your next turn"
  ends as the spell controller's next turn begins.
- **CR 508.1c / 509.1b** - the attack and block restrictions.
- **CR 602.5** - "A player can't begin to activate an ability that's
  prohibited from being activated." The text exempts nothing, so a creature's
  mana ability is locked too (CR 605.1a keeps a mana ability an *activated*
  ability).
- **CR 601.2h** - the gate "if {W}{U} was spent to cast this spell" asks what
  mana actually paid: at least one white and at least one blue.
- **CR 608.2b** - a target that left the battlefield is not locked.
- **CR 701.35a** - detain, the keyword action with the same words.

Reported card: Mythos of Vadrok (divided damage, then the gated rider on "those
permanents"). Second printing: Edifice of Authority ("{1}, {T}: Until your next
turn, target creature can't attack or block and its activated abilities can't
be activated. Activate only if there are three or more brick counters on this
artifact."), the same words on a "target creature" subject in an activated
ability.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

LOCK = "Activated abilities of this permanent can't be activated."
NO_ATTACK = "This creature can't attack."
NO_BLOCK = "This creature can't block."


def _notices(scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _resolve_stack(scenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def _advance_until(scenario, predicate) -> None:
    while not predicate(scenario):
        scenario.advance()
        _resolve_stack(scenario)


def _board(lands: tuple[str, ...]) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mythos of Vadrok"],
            battlefield=[*lands, "Serra Angel"],
            library=["Forest"] * 5,
        )
        .player(
            "bob",
            battlefield=["Fanatic of Rhonas", "Shivan Dragon", "Hill Giant", "Merfolk Looter"],
            library=["Forest"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario, lands: tuple[str, ...], *, split=(3, 2)):
    fanatic = scenario.creature("Fanatic of Rhonas", "bob")
    dragon = scenario.creature("Shivan Dragon", "bob")
    sources = scenario.untapped_sources(*lands, username="alice")
    scenario.cast_and_resolve(
        "Mythos of Vadrok",
        *sources,
        username="alice",
        targets=[fanatic, dragon],
        division=list(split),
    )
    return fanatic, dragon


def _lines(scenario, creature) -> tuple[str, ...]:
    """The restriction lines the effect grants (never the printed ones)."""
    printed = scenario.game.characteristics_of(creature).abilities
    return tuple(line for line in printed if line in (NO_ATTACK, NO_BLOCK, LOCK))


WU = ("Mountain", "Mountain", "Plains", "Island")


def test_with_white_and_blue_spent_the_targets_are_locked_and_take_the_damage():
    scenario = _board(WU)
    fanatic, dragon = _cast(scenario, WU)

    assert fanatic.damage == 3 and dragon.damage == 2
    for locked in (fanatic, dragon):
        lines = _lines(scenario, locked)
        assert NO_ATTACK in lines and NO_BLOCK in lines and LOCK in lines
    assert _notices(scenario) == []


def test_a_permanent_that_was_not_a_target_is_untouched():
    scenario = _board(WU)
    _cast(scenario, WU)
    giant = scenario.creature("Hill Giant", "bob")

    assert _lines(scenario, giant) == ()


def test_the_locked_creature_cannot_attack_on_its_controllers_turn():
    scenario = _board(WU)
    fanatic, dragon = _cast(scenario, WU)
    giant = scenario.creature("Hill Giant", "bob")

    _advance_until(
        scenario, lambda s: s.turn.active_player == "bob" and s.step is Step.BEGINNING_OF_COMBAT
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert not scenario.can_attack(dragon)
    assert scenario.can_attack(giant)
    with pytest.raises(ValueError, match=r"CR 508\.1c"):
        scenario.attack_with(dragon)


def test_the_locked_creature_cannot_block():
    scenario = _board(WU)
    _, dragon = _cast(scenario, WU)
    angel = scenario.creature("Serra Angel", "alice")
    angel.summoning_sick = False

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(angel)
    scenario.pass_priority("alice")
    scenario.pass_priority("bob")
    assert scenario.step is Step.DECLARE_BLOCKERS
    with pytest.raises(ValueError):
        scenario.block(angel, dragon)


def test_the_activated_ability_cannot_be_activated():
    scenario = _board(WU)
    _, dragon = _cast(scenario, WU)

    reason = scenario.why_cannot_activate(dragon, 0, "bob")
    assert reason is not None
    assert "can't be activated" in reason


def test_a_mana_ability_is_locked_too():
    """CR 602.5: the printed words exempt nothing."""
    scenario = _board(WU)
    fanatic, _ = _cast(scenario, WU)

    reason = scenario.why_cannot_activate(fanatic, 0, "bob")
    assert reason is not None
    assert "can't be activated" in reason


def test_the_locked_mana_ability_cannot_actually_be_used_and_an_unlocked_one_can():
    scenario = _board(WU)
    fanatic, _ = _cast(scenario, WU)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _advance_until(
        scenario, lambda s: s.turn.active_player == "bob" and s.step is Step.PRECOMBAT_MAIN
    )

    with pytest.raises(ValueError, match="can't be activated"):
        scenario.activate(fanatic, username="bob")
    assert fanatic.untapped

    scenario.game.continuous_effects.effects.clear()
    scenario.activate(fanatic, username="bob")
    assert fanatic.tapped


def test_it_ends_when_alices_next_turn_begins_and_not_before():
    scenario = _board(WU)
    fanatic, dragon = _cast(scenario, WU)

    _advance_until(
        scenario, lambda s: s.turn.active_player == "bob" and s.step is Step.PRECOMBAT_MAIN
    )
    assert LOCK in _lines(scenario, fanatic)  # bob's own turn: still locked

    _advance_until(
        scenario, lambda s: s.turn.active_player == "alice" and s.step is Step.PRECOMBAT_MAIN
    )
    for creature in (fanatic, dragon):
        lines = _lines(scenario, creature)
        assert NO_ATTACK not in lines and NO_BLOCK not in lines and LOCK not in lines


def test_with_only_red_spent_the_damage_happens_and_nothing_is_locked():
    lands = ("Mountain",) * 4
    scenario = _board(lands)
    fanatic, dragon = _cast(scenario, lands)

    assert fanatic.damage == 3 and dragon.damage == 2
    assert _lines(scenario, fanatic) == () and _lines(scenario, dragon) == ()
    assert _notices(scenario) == []


@pytest.mark.parametrize("missing", ["Plains", "Island"])
def test_both_colours_are_needed_one_alone_does_not_lock(missing):
    present = "Island" if missing == "Plains" else "Plains"
    lands = ("Mountain", "Mountain", "Mountain", present)
    scenario = _board(lands)
    fanatic, _ = _cast(scenario, lands)

    assert _lines(scenario, fanatic) == ()


def test_a_target_that_died_to_the_damage_is_not_locked_and_the_survivor_is():
    scenario = _board(WU)
    looter = scenario.creature("Merfolk Looter", "bob")
    dragon = scenario.creature("Shivan Dragon", "bob")
    sources = scenario.untapped_sources(*WU, username="alice")
    scenario.cast_and_resolve(
        "Mythos of Vadrok", *sources, username="alice", targets=[looter, dragon], division=[1, 4]
    )
    scenario.state_based_actions()

    assert looter.zone is Zone.GRAVEYARD
    assert LOCK in _lines(scenario, dragon)
    assert _notices(scenario) == []


# -- second printing: Edifice of Authority ---------------------------------


def _edifice_board() -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Edifice of Authority", "Plains", "Plains", "Plains"],
            library=["Forest"] * 5,
        )
        .player("bob", battlefield=["Shivan Dragon"], library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_edifice_of_authority_second_ability_locks_its_target_until_your_next_turn():
    scenario = _edifice_board()
    edifice = scenario.find("Edifice of Authority", Zone.BATTLEFIELD, "alice")
    dragon = scenario.creature("Shivan Dragon", "bob")
    # The first ability puts a brick counter on the artifact each time; the
    # second is only legal with three of them.
    edifice.add_counters("brick", 3)
    (plains, other) = scenario.untapped_sources("Plains", "Plains", username="alice")
    scenario.activate(edifice, plains, index=1, username="alice", targets=[dragon])
    scenario.pass_until_resolved()

    lines = _lines(scenario, dragon)
    assert NO_ATTACK in lines and NO_BLOCK in lines and LOCK in lines
    assert _notices(scenario) == []

    _advance_until(scenario, lambda s: s.turn.active_player == "alice" and s.step is Step.UPKEEP)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert LOCK not in _lines(scenario, dragon)
