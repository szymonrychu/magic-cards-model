"""Scenario: a plain "can't be blocked" restriction, as opposed to
`test_evasion.py`'s flying/reach/menace/trample, which all have keyword names
`machines/combat.py`'s `Keyword` enumerates.

CR 509.1b: "The defending player checks each creature they control to see
whether it's affected by any restrictions (effects that say a creature can't
block, or that it can't block unless some condition is met). If any
restrictions are being disobeyed, the declaration of blockers is illegal. A
restriction may be created by an evasion ability (a static ability an
attacking creature has that restricts what can block it)." - read in full
with `mise run rules:find 509.1` this session (`.rules/` pulled first with
`mise run rules:pull`); earlier waves of this file cited 509.1a - the
declare-blockers *action* itself - because `knowledge_search` only ever
returned 509.1a's excerpt truncated before the lettered text, and the primary
source had not yet been pulled. Unlike flying (CR 702.9b) or menace (CR
702.111b), "can't be blocked [by ...]" carries no keyword of its own, so it
has to be read straight off the card's own oracle text rather than off
`Keyword`.

Shapes read (`combat.evasion_restriction_refusal`):

- **The Mindskinner**: "The Mindskinner can't be blocked." - unconditional.
- **Questing Beast** / **April O'Neil, Kunoichi Trainee**: "... by creatures
  with power 2 or less" / "... or greater" - a power comparison.
- **Ghost of Ramirez DePietro**: "... by creatures with toughness 3 or
  greater" - the same comparison against toughness.
- **Juggernaut**: "This creature can't be blocked by Walls." - a bare
  creature type (CR 205.3m), no adjective in front of "creature(s)" at all.
- **Vine Mare**: "... by black creatures." - a colour (CR 105.1).
- **Audacious Infiltrator**: "... by artifact creatures." - a card type.
- **Skyscythe Engulfer**: "... by creatures with flying." - a keyword the
  blocker must have, off `Keyword`'s own closed vocabulary.
- **Field of Reality** / **Hedgewitch's Mask**: the identical "by
  `<description>`" grammar granted by an Aura/Equipment (`machines/layers.py`)
  rather than printed on the attacker itself - read the same way once granted
  (CR 613.1f), which is also this file's proof that two independent
  restrictions on one attacker are each enforced on their own.
- **Blazing Torch**: "... by Vampires or Zombies." - a disjunction of two
  bare creature types, each read by the identical single-description grammar
  and satisfied when either matches.
- **Arctic Foxes**: "... by creatures with power 2 or greater as long as
  defending player controls a snow land." - the quality comparison further
  gated by an external board condition, both read independently and both
  required.

Every printing in `src/magic_cards_model/data/printings` carrying "can't be
blocked by" now reads `handled` (`scripts/sweep_pool.py --card`) except
**Sacred Knight**'s "black and/or red creatures" - an elided-noun list ("black
[creatures] and/or red creatures") joined by "and/or" rather than a bare
"or", which is a different connective this task did not widen to; it is
`gap_example`'s own dynamically-chosen stand-in for the fail-closed path
below, never named directly by a test.

The fail-closed path is exercised on a printing chosen by `gap_example`:
`combat.looks_like_unparsed_evasion_restriction` catches a sentence outside
every shape above and `block_refusal` records an `EvasionNotice` rather than
silently leaving the block legal *or* silently refusing it - either would be a
guess this parser has no business making.

Every CR number here was looked up with `knowledge_search(type="rules")` or
`mise run rules:find` in the session that wrote this file.
"""

import re

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import (
    EvasionNotice,
    looks_like_unparsed_evasion_restriction,
)
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import Card, CardState, Type, Zone
from tests.cards import card, gap_example

from .harness import Scenario, mana_from


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
    not read yet - chosen, never named (`gap_example`). Past waves closed
    this gap for whichever printing stood here before: April O'Neil, Kunoichi
    Trainee ("power 3 or greater", 271-tmt), then every plain subtype/colour/
    type/keyword/toughness quality plus a disjunction and a condition-gated
    quality (Juggernaut's "Walls", Blazing Torch's "Vampires or Zombies",
    Arctic Foxes' condition-gated power comparison, fix-cant-be-blocked-by).
    Sacred Knight's "black and/or red creatures" - an "and/or" elided-noun
    list, a different connective from the plain "or" disjunction above -
    stands here now; read it too and something else will stand here next.
    """
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
    (CR 509.1b)."""
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


# -- a bare creature type: Juggernaut ----------------------------------------


def test_juggernaut_is_refused_by_a_wall():
    """Juggernaut: "This creature can't be blocked by Walls." - a bare CR
    205.3m creature type with no "creature(s)" noun at all, unlike every
    adjective-plus-noun shape above."""
    scenario = duel("Juggernaut", "Wall of Omens").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    juggernaut = scenario.creature("Juggernaut")
    wall = scenario.creature("Wall of Omens", "bob")
    scenario.attack_with(juggernaut)

    assert not scenario.game.can_block(wall, juggernaut)
    with pytest.raises(ValueError, match="Walls"):
        scenario.block(juggernaut, wall)
    assert scenario.game.evasion_notices == []


def test_juggernaut_is_blockable_by_a_non_wall():
    scenario = duel("Juggernaut", "Grizzly Bears").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    juggernaut = scenario.creature("Juggernaut")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(juggernaut)

    assert scenario.game.can_block(bears, juggernaut)
    scenario.block(juggernaut, bears)
    assert scenario.game.is_blocked(juggernaut)


# -- a colour: Vine Mare ------------------------------------------------------


def test_vine_mare_is_refused_by_a_black_creature():
    """Vine Mare: "This creature can't be blocked by black creatures." (CR
    105.1) - a card not in the deck pool before this task."""
    scenario = duel("Vine Mare", "Carrion Feeder").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    mare = scenario.creature("Vine Mare")
    feeder = scenario.creature("Carrion Feeder", "bob")
    scenario.attack_with(mare)

    assert not scenario.game.can_block(feeder, mare)
    with pytest.raises(ValueError, match="black creatures"):
        scenario.block(mare, feeder)


def test_vine_mare_is_blockable_by_a_non_black_creature():
    scenario = duel("Vine Mare", "Grizzly Bears").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    mare = scenario.creature("Vine Mare")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(mare)

    assert scenario.game.can_block(bears, mare)
    scenario.block(mare, bears)
    assert scenario.game.is_blocked(mare)


# -- a card type: Audacious Infiltrator --------------------------------------


def test_audacious_infiltrator_is_refused_by_an_artifact_creature():
    """Audacious Infiltrator: "This creature can't be blocked by artifact
    creatures." - the same card-type adjective `_CREATURE_DESCRIPTION_RE`
    already reads for the self-block half (Hinterland Drake), now proved on
    the attacker's own evasion half too."""
    scenario = duel("Audacious Infiltrator", "Ornithopter").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    infiltrator = scenario.creature("Audacious Infiltrator")
    thopter = scenario.creature("Ornithopter", "bob")
    scenario.attack_with(infiltrator)

    assert not scenario.game.can_block(thopter, infiltrator)
    with pytest.raises(ValueError, match="artifact creatures"):
        scenario.block(infiltrator, thopter)


def test_audacious_infiltrator_is_blockable_by_a_non_artifact_creature():
    scenario = duel("Audacious Infiltrator", "Grizzly Bears").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    infiltrator = scenario.creature("Audacious Infiltrator")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(infiltrator)

    assert scenario.game.can_block(bears, infiltrator)
    scenario.block(infiltrator, bears)
    assert scenario.game.is_blocked(infiltrator)


# -- a keyword the blocker must have: Skyscythe Engulfer ---------------------


def test_skyscythe_engulfer_is_refused_by_a_flier():
    """Skyscythe Engulfer: "This creature can't be blocked by creatures with
    flying." - the blocker's own keyword (CR 702), off `Keyword`'s closed
    vocabulary, read the same way `_CANT_BE_BLOCKED_EXCEPT_BY_KEYWORD_RE`
    already reads "except by creatures with `<keyword>`"."""
    scenario = duel("Skyscythe Engulfer", "Ornithopter").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    engulfer = scenario.creature("Skyscythe Engulfer")
    thopter = scenario.creature("Ornithopter", "bob")
    scenario.attack_with(engulfer)

    assert not scenario.game.can_block(thopter, engulfer)
    with pytest.raises(ValueError, match="creatures with flying"):
        scenario.block(engulfer, thopter)


def test_skyscythe_engulfer_is_blockable_by_a_non_flier():
    scenario = duel("Skyscythe Engulfer", "Wurmcoil Engine").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    engulfer = scenario.creature("Skyscythe Engulfer")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.attack_with(engulfer)

    assert scenario.game.can_block(wurm, engulfer)
    scenario.block(engulfer, wurm)
    assert scenario.game.is_blocked(engulfer)


# -- a toughness comparison: Ghost of Ramirez DePietro -----------------------


def test_ghost_of_ramirez_depietros_toughness_restriction_is_enforced():
    """Ghost of Ramirez DePietro: "can't be blocked by creatures with
    toughness 3 or greater." - the mirror of Questing Beast's power
    comparison, against the blocker's toughness instead."""
    scenario = duel("Ghost of Ramirez DePietro", "Wall of Omens").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    ghost = scenario.creature("Ghost of Ramirez DePietro")
    wall = scenario.creature("Wall of Omens", "bob")
    scenario.attack_with(ghost)

    assert not scenario.game.can_block(wall, ghost)
    with pytest.raises(ValueError, match="toughness 3 or greater"):
        scenario.block(ghost, wall)


def test_ghost_of_ramirez_depietro_is_blockable_by_low_toughness():
    scenario = duel("Ghost of Ramirez DePietro", "Memnite").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    ghost = scenario.creature("Ghost of Ramirez DePietro")
    memnite = scenario.creature("Memnite", "bob")
    scenario.attack_with(ghost)

    assert scenario.game.can_block(memnite, ghost)
    scenario.block(ghost, memnite)
    assert scenario.game.is_blocked(ghost)


# -- granted, not printed: Field of Reality / Hedgewitch's Mask --------------


def test_field_of_reality_grants_the_restriction_through_an_aura():
    """Field of Reality: "Enchanted creature can't be blocked by Spirits." -
    the identical "by `<description>`" grammar arriving as an Aura's own
    layer 6 grant (CR 613.1f, `layers._ATTACHED_CREATURE_CANT_BE_BLOCKED_RE`)
    rather than printed on the attacker, proving the reader is not keyed to
    where the sentence came from."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Field of Reality"],
            battlefield=["Grizzly Bears", "Island", "Island", "Island"],
        )
        .player("bob", battlefield=["Dark Revenant", "Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    islands = scenario.untapped_sources("Island", "Island", "Island", username="alice")
    scenario.cast_and_resolve("Field of Reality", *islands, targets=[bears])

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    revenant = scenario.creature("Dark Revenant", "bob")
    elves = scenario.creature("Llanowar Elves", "bob")

    assert not scenario.game.can_block(revenant, bears)
    with pytest.raises(ValueError, match="Spirits"):
        scenario.block(bears, revenant)
    assert scenario.game.can_block(elves, bears), "Llanowar Elves is not a Spirit"
    scenario.block(bears, elves)
    assert scenario.game.is_blocked(bears)


def test_hedgewitchs_mask_grants_a_power_qualified_restriction_through_an_equipment():
    """Hedgewitch's Mask: "Equipped creature can't be blocked by creatures
    with power 4 or greater." - the power-qualified shape granted through an
    Equipment instead of printed."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears", "Hedgewitch's Mask", "Plains", "Plains"])
        .player("bob", battlefield=["Wurmcoil Engine", "Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    mask = scenario.find("Hedgewitch's Mask", Zone.BATTLEFIELD, "alice")
    plains_1, plains_2 = scenario.untapped_sources("Plains", "Plains", username="alice")

    activation = equip_activation(scenario.game, mask, bears, "alice")
    payment = activation.begin_paying()
    payment.tap_for_mana(plains_1, mana_from(plains_1))
    payment.tap_for_mana(plains_2, mana_from(plains_2))
    payment.pay()
    activation.activate()
    scenario.pass_until_resolved()

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    memnite = scenario.creature("Memnite", "bob")

    assert not scenario.game.can_block(wurm, bears)
    with pytest.raises(ValueError, match="power 4 or greater"):
        scenario.block(bears, wurm)
    scenario.block(bears, memnite)
    assert scenario.game.is_blocked(bears)


# -- corner case: a changeling blocker already has every creature type ------


def test_a_changeling_blocker_is_refused_the_same_as_a_printed_wall():
    """CR 702.73a: "Changeling ... means 'This object is every creature
    type.'" Amoeboid Changeling's own changeling keyword makes it a Wall the
    same way a printed Wall creature is one - Juggernaut's restriction
    reaches it exactly the same way."""
    scenario = duel("Juggernaut", "Amoeboid Changeling").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    juggernaut = scenario.creature("Juggernaut")
    changeling = scenario.creature("Amoeboid Changeling", "bob")
    scenario.attack_with(juggernaut)

    assert "Wall" in scenario.game.characteristics_of(changeling).subtypes
    assert not scenario.game.can_block(changeling, juggernaut)
    with pytest.raises(ValueError, match="Walls"):
        scenario.block(juggernaut, changeling)


# -- corner case: a creature that becomes a Wall mid-turn --------------------


def test_a_creature_that_gains_every_type_mid_turn_is_refused_too():
    """CR 613.5: the restriction reads whatever the layer system leaves the
    blocker with *right now*, not what was true when the turn started.
    Amoeboid Changeling's own "Target creature gains all creature types
    until end of turn." reaching Grizzly Bears mid-turn makes it a Wall too,
    the same way Dress Down's removal is read live for the unconditional
    shape."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Juggernaut"])
        .player("bob", battlefield=["Amoeboid Changeling", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    juggernaut = scenario.creature("Juggernaut", "alice")
    changeling = scenario.creature("Amoeboid Changeling", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    changeling.summoning_sick = False

    assert "Wall" not in scenario.game.characteristics_of(bears).subtypes

    scenario.pass_priority("alice")
    scenario.activate(changeling, index=0, targets=[bears])
    scenario.resolve_top()

    assert "Wall" in scenario.game.characteristics_of(bears).subtypes

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(juggernaut)

    assert not scenario.game.can_block(bears, juggernaut)
    with pytest.raises(ValueError, match="Walls"):
        scenario.block(juggernaut, bears)


# -- corner case: two independent restrictions on one attacker --------------


def test_two_independent_restrictions_are_each_enforced_on_their_own():
    """Juggernaut's own printed "can't be blocked by Walls." plus Hedgewitch's
    Mask's granted "can't be blocked by creatures with power 4 or greater."
    on the same attacker (CR 509.1b: "Different evasion abilities are
    cumulative.", looked up this session): a Wall is refused by the first, a
    high-power non-Wall by the second, and a low-power non-Wall is let
    through by both.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Juggernaut", "Hedgewitch's Mask", "Plains", "Plains"])
        .player("bob", battlefield=["Wall of Omens", "Wurmcoil Engine", "Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    juggernaut = scenario.creature("Juggernaut", "alice")
    mask = scenario.find("Hedgewitch's Mask", Zone.BATTLEFIELD, "alice")
    plains_1, plains_2 = scenario.untapped_sources("Plains", "Plains", username="alice")

    activation = equip_activation(scenario.game, mask, juggernaut, "alice")
    payment = activation.begin_paying()
    payment.tap_for_mana(plains_1, mana_from(plains_1))
    payment.tap_for_mana(plains_2, mana_from(plains_2))
    payment.pay()
    activation.activate()
    scenario.pass_until_resolved()

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(juggernaut)
    wall = scenario.creature("Wall of Omens", "bob")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    memnite = scenario.creature("Memnite", "bob")

    with pytest.raises(ValueError, match="Walls"):
        scenario.block(juggernaut, wall)
    with pytest.raises(ValueError, match="power 4 or greater"):
        scenario.block(juggernaut, wurm)
    scenario.block(juggernaut, memnite)
    assert scenario.game.is_blocked(juggernaut)
    assert scenario.game.evasion_notices == []


# -- a disjunction of two qualities: Blazing Torch ---------------------------


def test_blazing_torch_grants_a_disjunctive_restriction_through_an_equipment():
    """Blazing Torch: "Equipped creature can't be blocked by Vampires or
    Zombies." - a disjunction of two bare creature types (CR 205.3m), each
    read by the identical single-description grammar and satisfied when
    either alternative matches."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears", "Blazing Torch", "Mountain"])
        .player("bob", battlefield=["Carrion Feeder", "Falkenrath Pit Fighter", "Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    torch = scenario.find("Blazing Torch", Zone.BATTLEFIELD, "alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    activation = equip_activation(scenario.game, torch, bears, "alice")
    payment = activation.begin_paying()
    payment.tap_for_mana(mountain, mana_from(mountain))
    payment.pay()
    activation.activate()
    scenario.pass_until_resolved()

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    zombie = scenario.creature("Carrion Feeder", "bob")
    vampire = scenario.creature("Falkenrath Pit Fighter", "bob")
    elves = scenario.creature("Llanowar Elves", "bob")

    assert not scenario.game.can_block(zombie, bears)
    with pytest.raises(ValueError, match="Vampires or Zombies"):
        scenario.block(bears, zombie)
    assert not scenario.game.can_block(vampire, bears)
    with pytest.raises(ValueError, match="Vampires or Zombies"):
        scenario.block(bears, vampire)
    scenario.block(bears, elves)
    assert scenario.game.is_blocked(bears)
    assert scenario.game.evasion_notices == []


# -- a quality further gated by a board condition: Arctic Foxes -------------


def test_arctic_foxes_condition_gated_quality_is_enforced():
    """Arctic Foxes: "can't be blocked by creatures with power 2 or greater
    as long as defending player controls a snow land." - both the blocker's
    power and the board condition are read, and both are required (CR
    509.1b; "defending player controls a snow land" is read through the
    pre-existing `Game.condition_holds`/`condition_is_readable` registry,
    not a new condition reader)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Arctic Foxes"])
        .player("bob", battlefield=["Snow-Covered Forest", "Wurmcoil Engine", "Memnite"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    foxes = scenario.creature("Arctic Foxes")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    memnite = scenario.creature("Memnite", "bob")
    scenario.attack_with(foxes)

    assert not scenario.game.can_block(wurm, foxes)
    with pytest.raises(ValueError, match="power 2 or greater"):
        scenario.block(foxes, wurm)
    scenario.block(foxes, memnite)
    assert scenario.game.is_blocked(foxes)
    assert scenario.game.evasion_notices == []


def test_arctic_foxes_restriction_is_lifted_without_a_snow_land():
    """The same quality comparison, with the board condition false: CR
    509.1b's restriction never applies, so every blocker is legal and no
    `EvasionNotice` is recorded either - the condition is read, not merely
    assumed true."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Arctic Foxes"])
        .player("bob", battlefield=["Forest", "Wurmcoil Engine"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    foxes = scenario.creature("Arctic Foxes")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.attack_with(foxes)

    assert scenario.game.can_block(wurm, foxes)
    scenario.block(foxes, wurm)
    assert scenario.game.is_blocked(foxes)
    assert scenario.game.evasion_notices == []
