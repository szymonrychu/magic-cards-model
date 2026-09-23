"""An activated ability that copies target instant or sorcery spell you control.

CR 707.10: "To copy a spell, activated ability, or triggered ability means to
put a copy of it onto the stack; a copy of a spell isn't cast ... A copy of a
spell or ability copies both the characteristics of the spell or ability and
all decisions made for it, including modes, targets, the value of X ..."

CR 707.10c: "Some effects copy a spell or ability and state that its
controller may choose new targets for the copy. The player may leave any number
of the targets unchanged ... If the player chooses to change some or all of the
targets, the new targets must be legal."

CR 115.1c: "An activated ability is targeted if it identifies something it will
affect by using the phrase 'target [something]' ... The target(s) are chosen as
the ability is activated; see rule 602.2b." So the ability's own target
restriction ("instant or sorcery spell you control") is enforced at
activation, and CR 608.2b refuses the ability on resolution when the targeted
spell has left the stack.

Mirrorpool ("{2}{C}, {T}, Sacrifice this land: Copy target instant or sorcery
spell you control. You may choose new targets for the copy.") is the listed
card. Nivix Guildmage ("{2}{U}{R}: Copy target instant or sorcery spell you
control. You may choose new targets for the copy.") is the second printing,
proving the reader is the template and not Mirrorpool's own ability.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file (CR 707.10, 707.10c, 115.1c, 602.2b, 608.2b, 113.7a).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import CardState
from tests.scenarios.harness import Scenario

_MIRRORPOOL_COPY = 1
_NIVIX_COPY = 1


def _board(copier: str, alice_hand: list[str], bob_hand: list[str] | None = None) -> Scenario:
    lands = (
        ["Wastes", "Wastes", "Mountain", "Mountain", "Mountain"]
        if copier == "Mirrorpool"
        else ["Island", "Island", "Mountain", "Mountain", "Mountain"]
    )
    return (
        Scenario()
        .player(
            "alice",
            hand=alice_hand,
            battlefield=[copier, *lands],
            library=["Mountain"] * 10,
        )
        .player(
            "bob",
            life=20,
            hand=bob_hand or [],
            battlefield=["Mountain", "Mountain", "Island", "Island", "Grizzly Bears"],
            library=["Mountain"] * 10,
        )
    )


def _copy_of(scenario, original: CardState) -> CardState:
    (copy,) = [
        item
        for item in scenario.game.stack
        if item.name == original.name and item.id != original.id
    ]
    return copy


def _activate_mirrorpool(scenario, target: CardState):
    mirrorpool = scenario.find("Mirrorpool", Zone.BATTLEFIELD, "alice")
    mana = scenario.untapped_sources("Wastes", "Mountain", "Mountain", username="alice")
    return mirrorpool, scenario.activate(
        mirrorpool, *mana, index=_MIRRORPOOL_COPY, username="alice", targets=[target]
    )


def _activate_nivix(scenario, target: CardState):
    nivix = scenario.find("Nivix Guildmage", Zone.BATTLEFIELD, "alice")
    mana = scenario.untapped_sources("Island", "Island", "Mountain", "Mountain", username="alice")
    return nivix, scenario.activate(
        nivix, *mana, index=_NIVIX_COPY, username="alice", targets=[target]
    )


_ACTIVATORS = {"Mirrorpool": _activate_mirrorpool, "Nivix Guildmage": _activate_nivix}


# --------------------------------------------------------------------------
# The copy keeps the original's target when new targets are declined
# --------------------------------------------------------------------------


@pytest.mark.parametrize("copier", ["Mirrorpool", "Nivix Guildmage"])
def test_copy_keeps_the_original_target_when_new_targets_are_declined(copier):
    """CR 707.10: the copy carries the original's targets. Bolt at bob plus
    its copy at bob is 6 damage."""
    scenario = _board(copier, ["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (red,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", red, username="alice", targets=["bob"])

    _ACTIVATORS[copier](scenario, bolt)
    scenario.will_take_the_may(False, source=copier)
    scenario.resolve_top()  # the copy ability

    copy = _copy_of(scenario, bolt)
    assert copy.is_copy
    assert [ref.username for ref in copy.targets] == ["bob"]
    scenario.resolve_top()  # the copy
    scenario.resolve_top()  # the original
    assert scenario.player("bob").life == 14


@pytest.mark.parametrize("copier", ["Mirrorpool", "Nivix Guildmage"])
def test_copy_may_be_given_a_new_legal_target(copier):
    """CR 707.10c: the controller may choose a new target for the copy. The
    copy is sent at bob's Grizzly Bears while the original still hits bob."""
    scenario = _board(copier, ["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (red,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", red, username="alice", targets=["bob"])
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")

    _ACTIVATORS[copier](scenario, bolt)
    scenario.will_take_the_may(True, source=copier)
    scenario.will_choose_targets(bears, source=copier)
    scenario.resolve_top()  # the copy ability

    copy = _copy_of(scenario, bolt)
    assert [ref.card_id for ref in copy.targets] == [bears.id]
    scenario.resolve_top()  # the copy kills the Bears
    scenario.state_based_actions()
    assert bears.zone is Zone.GRAVEYARD
    scenario.resolve_top()  # the original
    assert scenario.player("bob").life == 17


@pytest.mark.parametrize("copier", ["Mirrorpool", "Nivix Guildmage"])
def test_cannot_target_an_opponents_spell(copier):
    """ "Spell you control" (CR 115.1c: the target restriction is checked as
    the ability is activated, CR 602.2b): bob's Lightning Bolt is refused."""
    scenario = _board(copier, [], bob_hand=["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    (red,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", red, username="bob", targets=["alice"])
    scenario.pass_priority("bob")

    with pytest.raises(ValueError):
        _ACTIVATORS[copier](scenario, bolt)
    assert scenario.stack_names() == ["Lightning Bolt"]


@pytest.mark.parametrize("copier", ["Mirrorpool", "Nivix Guildmage"])
def test_cannot_target_a_creature_spell(copier):
    """ "Instant or sorcery spell": alice's own Memnite (an artifact creature
    spell) is the wrong type and is refused as a target."""
    scenario = _board(copier, ["Memnite"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.cast_onto_stack("Memnite", username="alice")

    with pytest.raises(ValueError):
        _ACTIVATORS[copier](scenario, memnite)
    assert scenario.stack_names() == ["Memnite"]


def test_mirrorpool_is_sacrificed_as_part_of_the_cost():
    """The ability's own cost sacrifices the land; the copy still happens
    because the ability exists independently of its source (CR 113.7a)."""
    scenario = _board("Mirrorpool", ["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (red,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", red, username="alice", targets=["bob"])

    mirrorpool, _ = _activate_mirrorpool(scenario, bolt)
    assert mirrorpool.zone is Zone.GRAVEYARD
    scenario.will_take_the_may(False, source="Mirrorpool")
    scenario.resolve_top()
    assert _copy_of(scenario, bolt).is_copy


@pytest.mark.parametrize("copier", ["Mirrorpool", "Nivix Guildmage"])
def test_ability_does_nothing_when_the_spell_left_the_stack(copier):
    """CR 608.2b: bob counters the Bolt in response, so the ability's only
    target is illegal and it is removed without making a copy."""
    scenario = _board(copier, ["Lightning Bolt"], bob_hand=["Counterspell"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (red,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", red, username="alice", targets=["bob"])
    _, ability = _ACTIVATORS[copier](scenario, bolt)

    scenario.pass_priority("alice")
    blue = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Counterspell", *blue, username="bob", targets=[bolt])
    scenario.resolve_top()  # Counterspell
    assert bolt.zone is Zone.GRAVEYARD

    scenario.resolve_top()  # the copy ability, target gone
    assert ability.id in scenario.game.fizzled
    assert scenario.stack_names() == []
    assert scenario.player("bob").life == 20


@pytest.mark.parametrize("copier", ["Mirrorpool", "Nivix Guildmage"])
def test_copy_is_not_cast(copier):
    """CR 707.10: "a copy of a spell isn't cast" - the copy is a copy, and
    the turn's cast count does not rise."""
    scenario = _board(copier, ["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (red,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", red, username="alice", targets=["bob"])
    cast_before = len(scenario.game.spells_cast_this_turn)

    _ACTIVATORS[copier](scenario, bolt)
    scenario.will_take_the_may(False, source=copier)
    scenario.resolve_top()

    copy = _copy_of(scenario, bolt)
    assert scenario.game.cast_record(copy).is_copy
    assert len(scenario.game.spells_cast_this_turn) == cast_before
