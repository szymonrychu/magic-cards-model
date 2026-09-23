"""Scenario: the blocker's own "can't block" restriction (CR 509.1b).

`test_evasion_restrictions.py` covers the *attacker's* own "can't be
blocked" text (CR 509.1a). This file is that rule's mirror image: CR 509.1b
says the defending player "checks each creature they control to see whether
it's affected by any restrictions (effects that say a creature can't block,
or that it can't block unless some condition is met). If any restrictions
are being disobeyed, the declaration of blockers is illegal." Unlike flying
or menace, this restriction carries no keyword of its own, so it has to be
read straight off the blocker's own oracle text, the same way
`evasion_restriction_refusal` already reads the attacker's.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file: 509.1a-b (`scripts/cr.sh 509.1`), 613.5, 506.4/506.4a.

Shapes read by the new `combat.self_block_restriction_refusal`:

- **Bloodghast**/**Carrion Feeder**: "This creature can't block." - unconditional.
- **Changeling Outcast**: "This creature can't block and can't be blocked." - a
  compound sentence that restricts both halves independently.
- **Realm of Koh**'s Spirit token: "This token can't block or be blocked by
  non-Spirit creatures." - a compound sharing one description across both
  halves; the "be blocked by" half feeds `evasion_restriction_refusal`.
- **Zurgo Bellstriker**: "Zurgo can't block creatures with power 2 or
  greater." - a qualified restriction, and the self-reference is the bare
  first word of a comma-less legendary name rather than the whole thing.
- **Hinterland Drake**: "This creature can't block artifact creatures." - a
  qualified restriction by card type instead of power.
- **Felhide Brawler**/**Marauding Boneslasher**/**Howlpack Wolf**: "This
  creature can't block unless you control another `<type>`." - a real,
  repeated template (three legal printings share it), and per the owner's
  2026-09-23 policy (every card legal in Modern, Pioneer, or Standard must be
  fully supported, never left on a notice) this is read and enforced, not
  recorded as a gap.
- **Craven Hulk**: "This creature can't block alone." - the one printing of a
  template that only makes sense against the finished block declaration
  (CR 509.1b), the same way menace only makes sense there - read by
  `declaration_refusal`, not by `block_refusal` itself, and also fully
  enforced under the same owner policy.
- **Branded Brawlers**: "This creature can't block if you control an
  untapped land." - a conditional shape neither of the two enforced templates
  above covers, and legal in none of standard, pioneer, or modern - the
  owner decision's own carve-out for a notice ("A notice is acceptable only
  for a shape printed exclusively on cards legal in none of the three
  formats"), read the same fail-closed way `evasion_restriction_refusal`'s
  own April O'Neil proof already establishes for the attacker side.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import EvasionNotice
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models.action import ActionKind
from tests.cards import card

from .harness import Scenario

# Every proof printing used to demonstrate an *enforced* shape must itself be
# legal somewhere this engine cares about (owner policy, 2026-09-23: "if a
# card is legal in Modern/Pioneer/Standard it can't be silent, broken - all
# legal cards must be fully supported in the system"), or it proves nothing
# this engine is on the hook for. Branded Brawlers, the one card this file
# uses to prove the fail-closed *notice* path, is deliberately excluded: it
# is legal nowhere, which is exactly why a notice is the right outcome for it.
_PROOF_PRINTINGS = [
    "Bloodghast",
    "Carrion Feeder",
    "Changeling Outcast",
    "Realm of Koh",
    "Bile Urchin",
    "Zurgo Bellstriker",
    "Hinterland Drake",
    "Wurmcoil Engine",
    "Grizzly Bears",
    "Felhide Brawler",
    "Canyon Minotaur",
    "Craven Hulk",
    "Voltaic Visionary",
    "Dress Down",
]


def test_every_proof_printing_is_legal_in_at_least_one_tracked_format():
    for name in _PROOF_PRINTINGS:
        if name is None:
            continue
        legalities = card(name).legalities
        assert "legal" in {legalities.standard, legalities.pioneer, legalities.modern}, (
            f"{name} is not legal in standard, pioneer, or modern"
        )


def duel(attacker: str, *blockers: str) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[attacker])
        .player("bob", battlefield=list(blockers))
    )


def _of_kind(actions, kind: ActionKind):
    return [action for action in actions if action.kind is kind]


# -- (a) unconditional: Bloodghast -------------------------------------------


def test_bloodghast_cannot_block_and_is_not_enumerated():
    """CR 509.1b names the restriction and `why_cannot_block` names the
    sentence plus CR 509.1b, the way `evasion_restriction_refusal` already
    cites CR 509.1a for the attacker's own mirror-image text.
    """
    scenario = duel("Grizzly Bears", "Bloodghast").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    ghast = scenario.creature("Bloodghast", "bob")
    scenario.attack_with(bears)
    scenario.advance("alice")  # into declare blockers

    assert not scenario.game.can_block(ghast, bears)
    reason = scenario.game.why_cannot_block(ghast, bears)
    assert reason is not None
    assert "can't block" in reason
    assert "CR 509.1b" in reason
    with pytest.raises(ValueError, match="can't block"):
        scenario.block(bears, ghast)

    blocker_actions = _of_kind(legal_actions(scenario.game, "bob"), ActionKind.DECLARE_BLOCKER)
    assert all(action.card_id != ghast.id for action in blocker_actions)


# -- (b) unconditional again: Carrion Feeder and Changeling Outcast ---------


def test_carrion_feeder_cannot_block():
    """Off the deck pool and off the reported card - Bloodghast - which
    proves the reader targets the "This creature can't block." template, not
    Bloodghast by name.
    """
    scenario = duel("Grizzly Bears", "Carrion Feeder").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    feeder = scenario.creature("Carrion Feeder", "bob")
    scenario.attack_with(bears)
    scenario.advance("alice")

    assert not scenario.game.can_block(feeder, bears)
    with pytest.raises(ValueError, match="can't block"):
        scenario.block(bears, feeder)


def test_changeling_outcast_cannot_block_the_compound_sentence():
    """ "This creature can't block and can't be blocked." restricts both
    halves of the one sentence independently: as a *blocker* it is refused
    here (CR 509.1b), and separately - unrelated to this test, proven already
    by the pre-existing `_CANT_BE_BLOCKED_RE` tail match - it could not be
    blocked either were it attacking.
    """
    scenario = duel("Grizzly Bears", "Changeling Outcast").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    outcast = scenario.creature("Changeling Outcast", "bob")
    scenario.attack_with(bears)
    scenario.advance("alice")

    assert not scenario.game.can_block(outcast, bears)
    with pytest.raises(ValueError, match="can't block"):
        scenario.block(bears, outcast)


# -- (c) a token: Realm of Koh's Spirit ---------------------------------------


def _spirit_token_scenario(*, koh_controller: str, other_creature: str):
    """alice is always added first - and so is always the active/attacking
    player, the convention every other scenario in this file relies on -
    regardless of which side controls Realm of Koh's Spirit token.
    """
    koh_battlefield = ["Realm of Koh", "Swamp", "Swamp", "Swamp", "Swamp"]
    builder = Scenario().manual_turn_based_actions()
    if koh_controller == "alice":
        builder = builder.player("alice", battlefield=koh_battlefield).player(
            "bob", battlefield=[other_creature]
        )
    else:
        builder = builder.player("alice", battlefield=[other_creature]).player(
            "bob", battlefield=koh_battlefield
        )
    scenario = builder.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    if koh_controller != "alice":
        scenario.pass_priority("alice")
    koh = scenario.creature("Realm of Koh", koh_controller)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", username=koh_controller)
    scenario.activate(koh, *sources, index=1, username=koh_controller)
    scenario.pass_until_resolved()
    token = scenario.creature("Spirit Token", koh_controller)
    # This token entered this turn (CR 302.6), so one sub-case here needs it
    # to attack - staging it as though it had been under its controller
    # since their most recent turn began is the same bypass `Scenario.build`
    # already gives every battlefield permanent set up at the start.
    token.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario, token


def test_spirit_token_cannot_block_a_non_spirit_attacker():
    scenario, spirit = _spirit_token_scenario(koh_controller="bob", other_creature="Grizzly Bears")

    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.advance("alice")

    assert not scenario.game.can_block(spirit, bears)
    with pytest.raises(ValueError, match="can't block"):
        scenario.block(bears, spirit)


def test_spirit_token_can_block_a_spirit_attacker():
    scenario, spirit = _spirit_token_scenario(koh_controller="bob", other_creature="Bile Urchin")

    urchin = scenario.creature("Bile Urchin", "alice")
    scenario.attack_with(urchin)
    scenario.advance("alice")

    assert scenario.game.can_block(spirit, urchin)
    scenario.block(urchin, spirit)
    assert scenario.game.is_blocked(urchin)


def test_a_non_spirit_creature_cannot_block_the_spirit_token_attacking():
    """The "or be blocked by" half feeds `evasion_restriction_refusal`: the
    token as *attacker* refuses a non-Spirit blocker, read off the same
    compound sentence the block-side half is read from.
    """
    scenario, spirit = _spirit_token_scenario(
        koh_controller="alice", other_creature="Grizzly Bears"
    )

    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(spirit)
    scenario.advance("alice")

    assert not scenario.game.can_block(bears, spirit)
    with pytest.raises(ValueError, match="can't be blocked"):
        scenario.block(spirit, bears)


# -- (d) qualified restrictions: Zurgo Bellstriker and Hinterland Drake ------


def test_zurgo_cannot_block_a_two_power_attacker():
    """Zurgo Bellstriker's own text names itself by the bare first word of
    its (comma-less) printed name - "Zurgo can't block ...", not "Zurgo
    Bellstriker can't block ..." nor "This creature can't block ...".
    """
    scenario = duel("Grizzly Bears", "Zurgo Bellstriker").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    zurgo = scenario.creature("Zurgo Bellstriker", "bob")
    scenario.attack_with(bears)
    scenario.advance("alice")

    assert not scenario.game.can_block(zurgo, bears)
    with pytest.raises(ValueError, match="can't block"):
        scenario.block(bears, zurgo)


def test_zurgo_can_block_a_one_power_attacker():
    scenario = duel("Bile Urchin", "Zurgo Bellstriker").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    urchin = scenario.creature("Bile Urchin")
    zurgo = scenario.creature("Zurgo Bellstriker", "bob")
    scenario.attack_with(urchin)
    scenario.advance("alice")

    assert scenario.game.can_block(zurgo, urchin)
    scenario.block(urchin, zurgo)
    assert scenario.game.is_blocked(urchin)


def test_hinterland_drake_cannot_block_an_artifact_creature():
    scenario = duel("Wurmcoil Engine", "Hinterland Drake").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    wurm = scenario.creature("Wurmcoil Engine")
    drake = scenario.creature("Hinterland Drake", "bob")
    scenario.attack_with(wurm)
    scenario.advance("alice")

    assert not scenario.game.can_block(drake, wurm)
    with pytest.raises(ValueError, match="can't block"):
        scenario.block(wurm, drake)


def test_hinterland_drake_can_block_a_non_artifact_creature():
    scenario = duel("Grizzly Bears", "Hinterland Drake").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    drake = scenario.creature("Hinterland Drake", "bob")
    scenario.attack_with(bears)
    scenario.advance("alice")

    assert scenario.game.can_block(drake, bears)
    scenario.block(bears, drake)
    assert scenario.game.is_blocked(bears)


# -- (e) CR 613.5 layer 6: Dress Down removes the restriction ---------------


def test_dress_down_takes_bloodghasts_restriction_away_and_the_block_is_legal():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears"])
        .player(
            "bob",
            hand=["Dress Down"],
            battlefield=["Island", "Island", "Bloodghast"],
            library=["Island"],
        )
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears")
    ghast = scenario.creature("Bloodghast", "bob")
    scenario.attack_with(bears)
    scenario.advance("alice")

    assert not scenario.game.can_block(ghast, bears), "printed, the restriction is there"

    scenario.pass_priority("alice")
    first, second = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_and_resolve("Dress Down", first, second, username="bob")

    assert list(scenario.game.characteristics_of(ghast).abilities) == []
    assert scenario.game.can_block(ghast, bears)
    scenario.block(bears, ghast)
    assert scenario.game.is_blocked(bears)


# -- (f) CR 506.4a: a blocker already declared is not removed by a later ----
# -- "can't block" ------------------------------------------------------------


def test_a_blocker_that_gains_cant_block_after_blocking_stays_in_combat():
    """Voltaic Visionary's front face carries no restriction; its back face,
    Volt-Charged Berserker, prints "This creature can't block." Declaring the
    front face as a legal blocker and then flipping it - the same direct
    `.transform()` technique `test_activated_ability_effects.py`'s Avatar
    Roku test already uses to reach a back face - proves CR 506.4a: "Once a
    creature has been declared as ... a blocking creature, spells or
    abilities that would have kept that creature from ... blocking don't
    remove the creature from combat."
    """
    scenario = duel("Grizzly Bears", "Voltaic Visionary").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    visionary = scenario.creature("Voltaic Visionary", "bob")
    scenario.attack_with(bears)
    scenario.advance("alice")

    assert scenario.game.can_block(visionary, bears)
    scenario.block(bears, visionary)
    assert scenario.game.is_blocking(visionary)

    visionary.transform()
    assert visionary.name == "Volt-Charged Berserker"
    assert not scenario.game.can_block(visionary, bears), "the restriction is there now"

    assert scenario.game.is_blocking(visionary), "CR 506.4a: already blocking, not removed"
    assert scenario.game.is_blocked(bears)


# -- OWNER DECISION: conditional shapes on legal cards are enforced, not ----
# -- left as a notice ----------------------------------------------------------


def test_felhide_brawler_cannot_block_without_another_minotaur():
    scenario = duel("Grizzly Bears", "Felhide Brawler").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    brawler = scenario.creature("Felhide Brawler", "bob")
    scenario.attack_with(bears)
    scenario.advance("alice")

    assert not scenario.game.can_block(brawler, bears)
    reason = scenario.game.why_cannot_block(brawler, bears)
    assert reason is not None and "CR 509.1b" in reason
    with pytest.raises(ValueError, match="can't block"):
        scenario.block(bears, brawler)


def test_felhide_brawler_can_block_with_another_minotaur():
    """Canyon Minotaur is off the deck pool and off the reported card,
    proving the "unless you control another `<type>`" reader targets the
    template - it is also shared by Howlpack Wolf and Marauding
    Boneslasher, real Modern/Pioneer-legal printings this reads for free.
    """
    scenario = duel("Grizzly Bears", "Felhide Brawler", "Canyon Minotaur").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    brawler = scenario.creature("Felhide Brawler", "bob")
    scenario.attack_with(bears)
    scenario.advance("alice")

    assert scenario.game.can_block(brawler, bears)
    scenario.block(bears, brawler)
    assert scenario.game.is_blocked(bears)


def test_craven_hulk_cannot_block_alone():
    """ "This creature can't block alone." only makes sense against the
    finished declaration (CR 509.1b), the same way menace only makes sense
    there - `declaration_refusal`, not `block_refusal`, is where it is read.
    """
    scenario = duel("Grizzly Bears", "Craven Hulk").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    hulk = scenario.creature("Craven Hulk", "bob")
    scenario.attack_with(bears)
    scenario.advance("alice")

    # Per-blocker legality does not see "alone" at all (menace's own
    # precedent) - it is refused only once the whole declaration is tried.
    assert scenario.game.can_block(hulk, bears)
    with pytest.raises(ValueError, match="can't block alone"):
        scenario.block(bears, hulk)


def test_craven_hulk_can_block_alongside_another_blocker():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears", "Wurmcoil Engine"])
        .player("bob", battlefield=["Craven Hulk", "Bile Urchin"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears, wurm = scenario.creatures("Grizzly Bears", "Wurmcoil Engine")
    hulk, urchin = scenario.creatures("Craven Hulk", "Bile Urchin", username="bob")
    scenario.attack_with(bears, wurm, defending="bob")
    scenario.advance("alice")

    scenario.game.declare_blockers([(hulk, bears), (urchin, wurm)])

    assert scenario.game.is_blocking(hulk)
    assert scenario.game.is_blocking(urchin)


# -- (g) an unparsed shape: fail closed with a notice ------------------------


def test_an_unparsed_self_block_restriction_fails_closed_and_records_a_notice():
    """Branded Brawlers prints "This creature can't block if you control an
    untapped land." - a conditional shape distinct from both templates the
    owner decision requires enforced ("unless you control another `<type>`"
    and "alone"), and legal in none of standard, pioneer, or modern - exactly
    the owner decision's own carve-out ("A notice is acceptable only for a
    shape printed exclusively on cards legal in none of the three formats").
    The block goes through *unrestricted* rather than the engine guessing
    which way an unread "if" condition should resolve, the same fail-closed
    choice `evasion_restriction_refusal`'s own April O'Neil proof makes in
    `test_evasion_restrictions.py`.
    """
    scenario = duel("Grizzly Bears", "Branded Brawlers").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    bears = scenario.creature("Grizzly Bears")
    brawlers = scenario.creature("Branded Brawlers", "bob")
    scenario.attack_with(bears)
    scenario.advance("alice")

    assert scenario.game.can_block(brawlers, bears), (
        "unenforced, not enforced backwards - the block is not silently refused either"
    )
    scenario.block(bears, brawlers)
    assert scenario.game.is_blocked(bears)
    assert scenario.game.evasion_notices == [
        EvasionNotice(
            source_id=brawlers.id,
            source_name="Branded Brawlers",
            text=card("Branded Brawlers").oracle_text,
        )
    ]
