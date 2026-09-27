"""Scenario: a "can't be blocked" restriction granted to a *group* the
source's controller controls, rather than printed self-referentially on the
attacker itself.

CR 509.1b: "A restriction may be created by an evasion ability (a static
ability an attacking creature has that restricts what can block it)." Nothing
in `combat.py`'s own reader (`_evasion_restriction_sentences`) ever considered
this shape - its subject filter only ever accepts the attacker's own name or
"this creature" (CR 201.5 self-reference), so a group-subject line like
Deepchannel Mentor's "Blue creatures you control can't be blocked." was
invisible to it: not enforced, and - because the sentence was never even a
candidate - not recorded as an `EvasionNotice` either. Confirmed live before
this file existed: `can_block` returned unrefused and `Game.evasion_notices`
stayed empty for a printed Deepchannel Mentor attacking, which is a silent
rules bug, not a fail-closed gap - worse than the notice this whole module
otherwise leaves behind for a shape it cannot read.

The fix lives entirely in `machines/layers.py`
(`_GROUP_EVASION_GRANT_RE`/`_group_evasion_grant_dispatch`/`_group_evasion_
grant_builder`/`CreaturesControlledByQuality`): the group's own subject is
read by the identical `combat._parse_creature_description` grammar the
blocker's own quality already is - a bare CR 205.3m subtype, a colour, a card
type, a keyword, a power/toughness comparison, or a disjunction - and the
optional "by `<description>`"/"if"/"as long as" tail is granted *verbatim* as
the self-referential "This creature can't be blocked[`<tail>`]." line onto
every qualifying creature (CR 613.1f, CR 613.5). `machines/combat.py`'s own
evasion reader needs no change at all to pick it up: it does not care which
permanent's static ability put the line there, exactly as `layers._group_
power_or_toughness_unblockable_builder` (Tetsuko Umezawa, Fugitive) already
proved for its own single fixed shape.

Three real printings, three different quality kinds, checked exhaustively
against every printing in the pool carrying "you control can't be
blocked"/"can't block" (`grep`, this session) - nothing else in the pool needs
this reader:

- **Deepchannel Mentor**: "Blue creatures you control can't be blocked." - a
  colour, unconditional, no restriction on the blocker at all. Reported.
- **Graaz, Unstoppable Juggernaut**: "Juggernauts you control can't be
  blocked by Walls." - a bare subtype for the group itself, plus its own "by
  `<description>`" restriction on who may block. Reported.
- **Tanglewalker**: "Each creature you control can't be blocked as long as
  defending player controls an artifact land." - no quality filter at all
  ("each creature" is every creature controlled, the empty-adjective case
  `_parse_creature_description` already answers for the blocker's own side),
  gated by a condition rather than a blocker quality. Not in the deck pool
  before this task - added as the third, differently-shaped proof.

Every CR number here was looked up with `mise run rules:find 509.1` in the
session that wrote this file; `combat.py`'s own `evasion_restriction_refusal`
docstring already carries the same citation's full text.
"""

from magic_cards_model.machines import Step

from .harness import Scenario


def test_deepchannel_mentor_makes_blue_creatures_unblockable():
    """Deepchannel Mentor is itself blue and controls itself, so its own
    grant reaches it too, not only other blue creatures it controls."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Deepchannel Mentor"])
        .player("bob", battlefield=["Wurmcoil Engine"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    mentor = scenario.creature("Deepchannel Mentor", "alice")
    wurm = scenario.creature("Wurmcoil Engine", "bob")

    assert "This creature can't be blocked." in scenario.game.characteristics_of(mentor).abilities

    scenario.attack_with(mentor)
    assert not scenario.game.can_block(wurm, mentor)
    scenario.no_blocks()
    scenario.combat_damage()
    assert scenario.game.evasion_notices == [], (
        "invisible before this fix - the group subject was never a self-referential "
        "candidate at all, so nothing was ever recorded for it either"
    )


def test_deepchannel_mentors_grant_does_not_reach_a_colourless_creature():
    """Memnite is colourless, controlled by the same player as Deepchannel
    Mentor - the grant is scoped to blue creatures, not every creature the
    controller has."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Deepchannel Mentor", "Memnite"])
        .player("bob", battlefield=["Wurmcoil Engine"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    memnite = scenario.creature("Memnite", "alice")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.attack_with(memnite)

    assert scenario.game.can_block(wurm, memnite)
    scenario.block(memnite, wurm)
    assert scenario.game.is_blocked(memnite)


def test_deepchannel_mentors_grant_is_read_off_the_computed_board():
    """CR 613.5: Dress Down's layer 6 "Creatures lose all abilities" removes
    Deepchannel Mentor's own granting ability, so the grant it would
    otherwise be producing this computation disappears with it - the same
    live-board proof `test_evasion_restrictions.py`'s own Dress Down test
    already gives the self-referential shapes."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Deepchannel Mentor"])
        .player(
            "bob",
            hand=["Dress Down"],
            battlefield=["Island", "Island", "Wurmcoil Engine"],
            library=["Island"],
        )
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    mentor = scenario.creature("Deepchannel Mentor", "alice")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.attack_with(mentor)
    assert not scenario.game.can_block(wurm, mentor), "printed, the grant is there"

    scenario.pass_priority("alice")
    first, second = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_and_resolve("Dress Down", first, second, username="bob")

    assert list(scenario.game.characteristics_of(mentor).abilities) == []
    assert scenario.game.can_block(wurm, mentor)
    scenario.block(mentor, wurm)
    assert scenario.game.is_blocked(mentor)
    assert scenario.game.evasion_notices == []


def test_graaz_makes_juggernauts_unblockable_by_walls():
    """Graaz, Unstoppable Juggernaut is itself a Juggernaut and controls
    itself, so its own "by Walls" restriction reaches it: refused by a Wall,
    permitted by a non-Wall of any power."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Graaz, Unstoppable Juggernaut"])
        .player("bob", battlefield=["Wall of Omens", "Wurmcoil Engine"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    graaz = scenario.creature("Graaz, Unstoppable Juggernaut")
    wall = scenario.creature("Wall of Omens", "bob")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.attack_with(graaz)

    assert not scenario.game.can_block(wall, graaz)
    scenario.block(graaz, wurm)
    assert scenario.game.is_blocked(graaz)
    assert scenario.game.evasion_notices == []


def test_tanglewalker_makes_every_creature_unblockable_while_defender_has_an_artifact_land():
    """ "Each creature you control" names no quality at all - Tanglewalker's
    own Grizzly Bears is unblockable exactly when defending player controls
    an artifact land, and blockable again the moment that stops being true,
    proving the group grant's own optional tail is a *condition*
    (`Game.condition_holds`/`condition_is_readable`), not a blocker quality,
    read correctly either way."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Tanglewalker", "Grizzly Bears"])
        .player("bob", battlefield=["Great Furnace", "Wurmcoil Engine"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.attack_with(bears)

    assert not scenario.game.can_block(wurm, bears)
    assert scenario.game.evasion_notices == []


def test_tanglewalkers_grant_does_not_apply_without_an_artifact_land():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Tanglewalker", "Grizzly Bears"])
        .player("bob", battlefield=["Forest", "Wurmcoil Engine"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.attack_with(bears)

    assert scenario.game.can_block(wurm, bears)
    scenario.block(bears, wurm)
    assert scenario.game.is_blocked(bears)
    assert scenario.game.evasion_notices == []


_GRANTED = "This creature can't be blocked."


def _granted(scenario, creature) -> bool:
    return _GRANTED in scenario.game.characteristics_of(creature).abilities


def test_deepchannel_mentors_grant_reaches_another_blue_creature_its_controller_controls():
    """ "Blue creatures you control": Spectral Sailor, a different blue
    creature alice controls, is unblockable too, not only the Mentor."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Deepchannel Mentor", "Spectral Sailor"])
        .player("bob", battlefield=["Wurmcoil Engine"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    sailor = scenario.creature("Spectral Sailor", "alice")
    wurm = scenario.creature("Wurmcoil Engine", "bob")

    assert _granted(scenario, sailor)
    scenario.attack_with(sailor)
    assert not scenario.game.can_block(wurm, sailor)


def test_deepchannel_mentors_grant_does_not_reach_an_opponents_blue_creature():
    """ "you control" scopes the group to the source's controller: bob's blue
    Merfolk Observer gets nothing from alice's Mentor."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Deepchannel Mentor"])
        .player("bob", battlefield=["Merfolk Observer"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert not _granted(scenario, scenario.creature("Merfolk Observer", "bob"))


def test_deepchannel_mentors_grant_reaches_a_creature_that_enters_later_and_ends_with_the_source():
    """CR 613.5: the grant is continually re-applied, so a blue creature that
    enters afterwards has it at once, and once the Mentor is destroyed no
    creature has it any more."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Merfolk Looter"],
            battlefield=["Deepchannel Mentor", "Spectral Sailor"],
        )
        .player("bob", battlefield=["Wurmcoil Engine"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mentor = scenario.creature("Deepchannel Mentor", "alice")
    sailor = scenario.creature("Spectral Sailor", "alice")
    looter = scenario.put_onto_battlefield("Merfolk Looter", "alice")

    assert _granted(scenario, looter)
    scenario.game.destroy(mentor)
    assert not _granted(scenario, looter)
    assert not _granted(scenario, sailor)


def test_deepchannel_mentors_grant_follows_its_controller():
    """Act of Treason takes bob's Mentor: "you" is now alice, so alice's blue
    Spectral Sailor gains the grant and bob's blue Merfolk Observer loses it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", hand=["Act of Treason"], battlefield=["Mountain"] * 3 + ["Spectral Sailor"]
        )
        .player("bob", battlefield=["Deepchannel Mentor", "Merfolk Observer"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mentor = scenario.creature("Deepchannel Mentor", "bob")
    sailor = scenario.creature("Spectral Sailor", "alice")
    observer = scenario.creature("Merfolk Observer", "bob")
    assert _granted(scenario, observer)
    assert not _granted(scenario, sailor)

    mountains = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Act of Treason", *mountains, targets=[mentor])

    assert _granted(scenario, sailor)
    assert not _granted(scenario, observer)
