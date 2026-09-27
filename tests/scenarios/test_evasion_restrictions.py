"""Scenario: a plain "can't be blocked" restriction, as opposed to
`test_evasion.py`'s flying/reach/menace/trample, which all have keyword names
`machines/combat.py`'s `Keyword` enumerates.

CR 509.1a: the defending player, declaring blockers, "announces which
attacking creature or which group of attacking creatures ... it's blocking"
for each chosen creature - a block that names a creature the attacker's own
text rules out is not a legal declaration. Unlike flying (CR 702.9b) or menace
(CR 702.111b), "can't be blocked [by ...]" carries no keyword of its own, so it
has to be read straight off the card's own oracle text rather than off
`Keyword`. `knowledge_search` could only return 509.1a's excerpt truncated at
its opening clause ("The defending player chooses which creatures they
control... For each of the chosen creatures, the defending player
announces..."); the full lettered text past that point was not readable this
session, so this file cites 509.1a for the general declare-blockers legality
check the way `combat.block_refusal`'s own docstring already does for the
base requirements, rather than a more specific sub-rule it could not confirm.

Two real shapes are read (`combat.evasion_restriction_refusal`):

- **The Mindskinner**: "The Mindskinner can't be blocked." - unconditional.
- **Questing Beast**: "Questing Beast can't be blocked by creatures with power
  2 or less." - qualified by the blocker's own power.

A third real shape - **April O'Neil, Kunoichi Trainee**'s "can't be blocked by
creatures with power 3 or greater" - is read too since 271-tmt. The
fail-closed path is exercised on a printing chosen by `gap_example`:
`combat.looks_like_unparsed_evasion_restriction` catches the sentence and
`block_refusal` records an `EvasionNotice` rather than silently leaving the
block legal *or* silently refusing it - either would be a guess this parser
has no business making.

Every CR number here was looked up with `knowledge_search(type="rules")` in
the session that wrote this file.
"""

import re

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import (
    EvasionNotice,
    looks_like_unparsed_evasion_restriction,
)
from magic_cards_model.models import Card, CardState, Type, Zone
from tests.cards import card, gap_example

from .harness import Scenario


def duel(attacker: str, *blockers: str) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[attacker])
        .player("bob", battlefield=list(blockers))
    )


# -- unconditional: The Mindskinner -----------------------------------------


def test_an_unconditional_restriction_refuses_any_legal_blocker():
    """Wurmcoil Engine is untapped, a creature, and controlled by the
    defending player - every base requirement CR 509.1a-b asks about is met,
    and the block is still refused."""
    scenario = duel("The Mindskinner", "Wurmcoil Engine").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    skinner = scenario.creature("The Mindskinner")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.attack_with(skinner)

    assert not scenario.game.can_block(wurm, skinner)
    with pytest.raises(ValueError, match="can't be blocked"):
        scenario.block(skinner, wurm)


def test_an_unblockable_attacker_deals_its_damage_with_a_blocker_on_the_board():
    """The Mindskinner gets through even though Wurmcoil Engine is sitting
    right there, untapped and able to block anything else - the defending
    player has no legal way to assign it as a blocker, so it declares none,
    and the damage is assigned straight at bob rather than at any creature.

    The assignment, not bob's life total, is what this asserts: The
    Mindskinner's own separate ability ("If a source you control would deal
    damage to an opponent, prevent that damage and each opponent mills that
    many cards") replaces the life loss with a mill, which is correct and has
    nothing to do with evasion - `combat_damage`'s return value is the
    pre-replacement assignment, so it still shows the unblocked 10 landing on
    bob rather than on Wurmcoil Engine.
    """
    scenario = duel("The Mindskinner", "Wurmcoil Engine").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    skinner = scenario.creature("The Mindskinner")
    bob = scenario.player("bob")
    scenario.attack_with(skinner)
    scenario.no_blocks()
    assignment = scenario.combat_damage()

    assert not scenario.game.is_blocked(skinner)
    assert (bob, int(card("The Mindskinner").power)) in assignment


# -- qualified by power: Questing Beast --------------------------------------


def test_a_low_power_blocker_is_refused():
    scenario = duel("Questing Beast", "Grizzly Bears").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    beast = scenario.creature("Questing Beast")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(beast)

    assert not scenario.game.can_block(bears, beast)
    with pytest.raises(ValueError, match="power 2 or less"):
        scenario.block(beast, bears)


def test_a_higher_power_blocker_is_permitted():
    scenario = duel("Questing Beast", "Wurmcoil Engine").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    beast = scenario.creature("Questing Beast")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.attack_with(beast)

    assert scenario.game.can_block(wurm, beast)
    scenario.block(beast, wurm)

    assert scenario.game.is_blocked(beast)


# -- fail-closed: a comparison this parser does not read ---------------------


def _unparsed_evasion_example() -> Card:
    """A real attacker whose "can't be blocked ..." sentence this parser does
    not read yet - chosen, never named (`gap_example`): April O'Neil,
    Kunoichi Trainee stood here until 271-tmt read her "power 3 or greater"."""
    return gap_example(
        "an unread static can't-be-blocked restriction",
        lambda printing: (
            Type.CREATURE in printing.types
            and any(
                _is_static_evasion_line(line) for line in (printing.oracle_text or "").split("\n")
            )
            and looks_like_unparsed_evasion_restriction(
                CardState(card=printing, zone=Zone.BATTLEFIELD)
            )
        ),
    )


def _is_static_evasion_line(line: str) -> bool:
    """A printed static "can't be blocked" line - not an activated ability's
    effect (a cost before ":"), a trigger's (CR 603.1's "when/whenever/at"),
    or a quoted grant, none of which restrict a block until they resolve."""
    return (
        "can't be blocked" in line
        and ":" not in line
        and '"' not in line
        and not re.match(r"^(?:.*— )?(?:when|whenever|at)\b", line, re.IGNORECASE)
    )


def test_april_oneils_power_3_or_greater_restriction_is_enforced():
    """April O'Neil, Kunoichi Trainee: "can't be blocked by creatures with
    power 3 or greater" - Wurmcoil Engine's power 6 rules the block out
    (CR 509.1a)."""
    scenario = duel("April O'Neil, Kunoichi Trainee", "Wurmcoil Engine").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    april = scenario.creature("April O'Neil, Kunoichi Trainee")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.attack_with(april)

    with pytest.raises(ValueError, match="power 3 or greater"):
        scenario.block(april, wurm)
    assert scenario.game.evasion_notices == []


def test_an_unsupported_qualifier_fails_closed_and_records_a_notice():
    """A restriction `evasion_restriction_refusal` does not read goes through
    *unrestricted* rather than the engine guessing which way it should have
    gone. Applying nothing is the fail-closed choice (CLAUDE.md): silently
    refusing every blocker would be just as wrong a guess as silently
    allowing everything, and only one of those leaves a record behind.
    """
    example = _unparsed_evasion_example()
    scenario = duel(example.name, "Wurmcoil Engine").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    attacker = scenario.creature(example.name)
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.attack_with(attacker)
    scenario.block(attacker, wurm)

    assert scenario.game.is_blocked(attacker), (
        "unenforced, not enforced backwards - the block is not silently refused either"
    )
    assert scenario.game.evasion_notices == [
        EvasionNotice(
            source_id=attacker.id,
            source_name=example.name,
            text=card(example.name).oracle_text,
        )
    ]


def test_the_notice_is_recorded_once_even_after_several_legality_checks():
    """`Game.can_block` and `block_refusal` both walk the same attacker's text
    every time they are asked - `docs/scenario-tests.md` has `block` recheck
    the whole declaration on every call - so the dedup in `block_refusal` is
    what keeps one unreadable card from flooding the log with one notice per
    check.
    """
    example = _unparsed_evasion_example()
    scenario = duel(example.name, "Wurmcoil Engine").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    attacker = scenario.creature(example.name)
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.attack_with(attacker)

    scenario.game.can_block(wurm, attacker)
    scenario.game.can_block(wurm, attacker)
    scenario.block(attacker, wurm)

    assert len(scenario.game.evasion_notices) == 1


# -- the restriction is read off the computed board, not the printing --------


def test_dress_down_takes_the_restriction_away_and_the_block_is_legal():
    """CR 613.5: "the application of continuous effects as described by the
    layer system is continually and automatically performed by the game", so
    which sentences an attacker has is the layer system's answer, not the
    printing's.

    Dress Down's "Creatures lose all abilities" is a layer 6 ability-removing
    effect (CR 613.1f). A Mindskinner with no abilities has no "can't be
    blocked" sentence, and CR 509.1a's declaration is legal again -
    `combat._evasion_restriction_sentences` reads `Game.characteristics_of`
    rather than `CardState.oracle_text` for exactly this.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["The Mindskinner"])
        .player(
            "bob",
            hand=["Dress Down"],
            battlefield=["Island", "Island", "Wurmcoil Engine"],
            library=["Island"],
        )
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    skinner = scenario.creature("The Mindskinner")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.attack_with(skinner)

    assert not scenario.game.can_block(wurm, skinner), "printed, the restriction is there"

    scenario.pass_priority("alice")
    first, second = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_and_resolve("Dress Down", first, second, username="bob")

    assert list(scenario.game.characteristics_of(skinner).abilities) == []
    assert scenario.game.can_block(wurm, skinner)
    scenario.block(skinner, wurm)
    assert scenario.game.is_blocked(skinner)


def test_dress_down_leaves_no_unparsed_evasion_notice_behind():
    """The fail-closed notice reads the same computed sentences (CR 613.5).

    April O'Neil's "can't be blocked by creatures with power 3 or greater" is
    the shape `evasion_restriction_refusal` deliberately does not read, so it
    normally records an `EvasionNotice`. With the ability removed there is no
    sentence to fail on, and recording a notice would claim the engine missed
    something that is not there.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["April O'Neil, Kunoichi Trainee"])
        .player(
            "bob",
            hand=["Dress Down"],
            battlefield=["Island", "Island", "Grizzly Bears"],
            library=["Island"],
        )
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    april = scenario.creature("April O'Neil, Kunoichi Trainee")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(april)

    scenario.pass_priority("alice")
    first, second = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_and_resolve("Dress Down", first, second, username="bob")

    assert scenario.game.can_block(bears, april)
    assert scenario.game.evasion_notices == []
