"""Scenario: continuous effects that change who may cast what, not any object's
characteristics (CR 611.1).

Two cards, both from this session's card pool:

- **Ranger-Captain of Eos** - "Sacrifice this creature: Your opponents can't
  cast noncreature spells this turn." The sacrifice is the ability's own cost
  (CR 602.1a), so by the time the restriction exists the source has already
  left the battlefield - a check that re-reads a live permanent would find
  nothing and silently do nothing. The restriction is recorded instead, on
  `Game.casting_rule_effects`, and read by
  `machines.casting.why_cannot_cast_restriction`.
- **Teferi, Time Raveler** - two effects on the same card that read alike and
  point in opposite directions:
    - His static, "Each opponent can cast spells only any time they could
      cast a sorcery," *restricts* his opponents, read live off the
      battlefield by `machines.casting_restrictions.
      sorcery_speed_restriction_source` (CR 604.2, CR 611.3b) exactly the way
      `Game._activation_prohibition` already reads Karn, the Great Creator's
      activation-locking static.
    - His `+1`, "Until your next turn, you may cast sorcery spells as though
      they had flash," *loosens* things for his own controller only, and
      outlives Teferi leaving the battlefield the same way a temporary grant
      always does (CR 611.2a).

Every test below checks both players against both halves, because a
single-player scenario cannot tell a restriction that reads the wrong
controller from one that reads the right one - swapping who is caught is the
bug this file exists to catch.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import Casting
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from tests.scenarios.harness import Scenario


def _board(
    alice_battlefield: list[str],
    bob_battlefield: list[str],
    *,
    alice_hand: list[str] | None = None,
    bob_hand: list[str] | None = None,
) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=alice_hand or [],
            battlefield=alice_battlefield,
            library=["Mountain"] * 5,
        )
        .player(
            "bob",
            hand=bob_hand or [],
            battlefield=bob_battlefield,
            library=["Mountain"] * 5,
        )
        .build()
    )


def _advance_to_bobs_precombat_main(scenario: Scenario) -> None:
    while scenario.turn.active_player != "bob" or scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()


# --------------------------------------------------------------------------
# Ranger-Captain of Eos: "Your opponents can't cast noncreature spells this
# turn." (CR 602.1a's cost pays away the source before the effect exists)
# --------------------------------------------------------------------------


def _sacrifice_ranger_captain(scenario: Scenario) -> None:
    """Alice activates and resolves the sacrifice ability.

    Passes priority to alice first if she does not already hold it - the
    ability carries no timing restriction of its own (CR 602.1a, no "activate
    only as a sorcery"), so it is legal on bob's turn too, and several of this
    file's tests stage it there on purpose.
    """
    if scenario.priority_holder != "alice":
        scenario.pass_priority(scenario.priority_holder)
    captain = scenario.creature("Ranger-Captain of Eos", "alice")
    scenario.activate(captain)
    assert captain.zone is Zone.GRAVEYARD, "the sacrifice is the cost, paid before resolution"
    scenario.resolve_top()


def test_an_opponent_cannot_cast_a_noncreature_spell_after_the_sacrifice():
    scenario = _board(
        alice_battlefield=["Ranger-Captain of Eos", "Mountain"],
        bob_battlefield=["Mountain"],
        bob_hand=["Lightning Bolt"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _sacrifice_ranger_captain(scenario)

    with pytest.raises(ValueError, match="can't cast noncreature spells"):
        scenario.cast("Lightning Bolt", username="bob")


def test_an_opponent_can_still_cast_a_creature_spell():
    """ "Noncreature" is the whole restriction - a creature spell is untouched.

    Staged in bob's own main phase so that sorcery-speed timing (CR 117.1a,
    unrelated to this restriction) is not what is being tested - the
    restriction can be activated from either side of a turn, since Ranger-
    Captain of Eos's sacrifice ability carries no timing restriction of its
    own.
    """
    scenario = _board(
        alice_battlefield=["Ranger-Captain of Eos"],
        bob_battlefield=["Mountain", "Mountain"],
        bob_hand=["Grizzly Bears"],
    )
    _advance_to_bobs_precombat_main(scenario)
    _sacrifice_ranger_captain(scenario)

    casting = scenario.cast("Grizzly Bears", username="bob")
    assert casting is not None


def test_the_controllers_own_casting_is_untouched():
    """ "Your opponents can't cast" - never "you can't cast". Alice activated
    it, so alice is exempt, the same "your"/"opponents" split
    `Game._activation_prohibition` already reads for Karn's own static."""
    scenario = _board(
        alice_battlefield=["Ranger-Captain of Eos", "Mountain"],
        bob_battlefield=["Mountain"],
        alice_hand=["Lightning Bolt"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _sacrifice_ranger_captain(scenario)

    casting = scenario.cast("Lightning Bolt", username="alice")
    assert casting is not None


def test_a_spell_already_on_the_stack_is_not_retroactively_refused():
    """CR 601.6: casting is only illegal to complete while it is being
    announced. A restriction created *after* a spell has already finished
    being cast (and is sitting on the stack) does not reach back and unmake
    that cast - `why_cannot_cast_restriction` is only ever asked as a new
    `Casting` is created, never re-asked of one already on the stack."""
    scenario = _board(
        alice_battlefield=["Ranger-Captain of Eos", "Mountain"],
        bob_battlefield=["Mountain"],
        bob_hand=["Lightning Bolt"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    assert bolt.zone is Zone.STACK

    _sacrifice_ranger_captain(scenario)

    scenario.pass_until_resolved()
    assert bolt.zone is Zone.GRAVEYARD, "the Bolt still resolved and dealt its damage"
    assert scenario.player("alice").life == 17


def test_the_restriction_ends_at_cleanup_not_before():
    """CR 500.5b / CR 514.2: "this turn" ends in the cleanup step, not the end
    step - the restriction is still live through the rest of alice's turn."""
    scenario = _board(
        alice_battlefield=["Ranger-Captain of Eos", "Mountain"],
        bob_battlefield=["Mountain"],
        bob_hand=["Lightning Bolt"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _sacrifice_ranger_captain(scenario)

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    with pytest.raises(ValueError, match="can't cast noncreature spells"):
        scenario.cast("Lightning Bolt", username="bob")

    scenario.advance()  # cleanup: CR 514.2 ends "this turn" effects
    assert scenario.game.casting_rule_effects == []
    _advance_to_bobs_precombat_main(scenario)
    casting = scenario.cast("Lightning Bolt", username="bob")
    assert casting is not None


# --------------------------------------------------------------------------
# Teferi, Time Raveler's static: "Each opponent can cast spells only any time
# they could cast a sorcery." (a live read, CR 604.2 / CR 611.3b)
# --------------------------------------------------------------------------


def test_teferis_static_refuses_an_opponents_instant_off_sorcery_timing():
    scenario = _board(
        alice_battlefield=["Teferi, Time Raveler"],
        bob_battlefield=[],
        bob_hand=["Lightning Bolt", "Mountain"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)  # alice's own main phase, not bob's

    with pytest.raises(ValueError, match="restricts bob to casting spells only"):
        scenario.cast("Lightning Bolt", username="bob")


def test_teferis_static_permits_an_opponents_spell_at_sorcery_speed():
    """The restriction is about *timing*, not identity: bob's own main phase
    with an empty stack already satisfies it."""
    scenario = _board(
        alice_battlefield=["Teferi, Time Raveler"],
        bob_battlefield=["Mountain"],
        bob_hand=["Lightning Bolt"],
    )
    _advance_to_bobs_precombat_main(scenario)

    casting = scenario.cast("Lightning Bolt", username="bob")
    assert casting is not None


def test_teferis_static_does_not_restrict_its_own_controller():
    """ "Each opponent" - alice, who controls Teferi, is untouched and may
    still cast an instant on bob's turn."""
    scenario = _board(
        alice_battlefield=["Teferi, Time Raveler"],
        bob_battlefield=[],
        alice_hand=["Lightning Bolt", "Mountain"],
    )
    _advance_to_bobs_precombat_main(scenario)

    casting = scenario.cast("Lightning Bolt", username="alice")
    assert casting is not None


def test_the_static_restriction_stops_the_moment_teferi_leaves():
    """CR 611.3b: read fresh off the battlefield, so it dies instantly with no
    record to clean up - the same choice `Game._activation_prohibition`
    already makes for Karn, the Great Creator."""
    scenario = _board(
        alice_battlefield=["Teferi, Time Raveler"],
        bob_battlefield=[],
        bob_hand=["Lightning Bolt", "Mountain"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    teferi = scenario.creature("Teferi, Time Raveler", "alice")

    with pytest.raises(ValueError, match="restricts bob"):
        scenario.cast("Lightning Bolt", username="bob")

    scenario.game.destroy(teferi)
    assert teferi.zone is Zone.GRAVEYARD

    casting = scenario.cast("Lightning Bolt", username="bob")
    assert casting is not None


# --------------------------------------------------------------------------
# Teferi, Time Raveler's +1: "Until your next turn, you may cast sorcery
# spells as though they had flash." (a temporary grant, CR 611.2a)
# --------------------------------------------------------------------------


def _activate_teferis_plus_one(scenario: Scenario, username: str = "alice") -> None:
    teferi = scenario.creature("Teferi, Time Raveler", username)
    scenario.activate(teferi, index=0, username=username)
    scenario.pass_until_resolved()


def test_the_plus_one_lets_its_controller_cast_a_sorcery_off_sorcery_timing():
    scenario = _board(
        alice_battlefield=["Teferi, Time Raveler"],
        bob_battlefield=[],
        alice_hand=["Preordain"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_teferis_plus_one(scenario)

    scenario.advance()  # begin combat: no longer alice's main phase
    casting = scenario.cast("Preordain", username="alice")
    assert casting is not None


def test_without_the_plus_one_a_sorcery_still_needs_sorcery_timing():
    """The contrast: nothing grants this for free."""
    scenario = _board(
        alice_battlefield=["Teferi, Time Raveler"],
        bob_battlefield=[],
        alice_hand=["Preordain"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.advance()  # begin combat, no +1 activated

    with pytest.raises(ValueError, match="during their own main phase"):
        scenario.cast("Preordain", username="alice")


def test_the_plus_one_does_not_loosen_anything_for_the_opponent():
    """The `+1` says "you may" - bob is not "you". Swapping this with the
    static's restriction is the exact mistake this file is written against.

    Bob is also caught by Teferi's *static* here (he is an opponent, and it
    is alice's main phase) - the point is only that the `+1`'s grant does
    nothing extra for him on top of that, so the assertion is just that the
    cast still fails, whichever of the two reasons the message gives."""
    scenario = _board(
        alice_battlefield=["Teferi, Time Raveler"],
        bob_battlefield=[],
        bob_hand=["Preordain"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_teferis_plus_one(scenario)

    with pytest.raises(ValueError):
        scenario.cast("Preordain", username="bob")


def test_the_plus_one_grant_survives_teferi_leaving_the_battlefield():
    """A temporary grant, not a live-read static: it does not die with its
    source (contrast with the static half, above)."""
    scenario = _board(
        alice_battlefield=["Teferi, Time Raveler"],
        bob_battlefield=[],
        alice_hand=["Preordain"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    teferi = scenario.creature("Teferi, Time Raveler", "alice")
    _activate_teferis_plus_one(scenario)

    scenario.game.destroy(teferi)
    assert teferi.zone is Zone.GRAVEYARD

    scenario.advance()  # begin combat
    casting = scenario.cast("Preordain", username="alice")
    assert casting is not None


def test_the_plus_one_grant_lasts_through_an_intervening_opponents_turn():
    """CR 611.2a: "until your next turn" outlasts the rest of this turn and
    bob's turn in between - it ends only when alice's own next turn begins."""
    scenario = _board(
        alice_battlefield=["Teferi, Time Raveler"],
        bob_battlefield=[],
        alice_hand=["Preordain"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_teferis_plus_one(scenario)

    while scenario.turn.active_player != "bob":
        scenario.advance()
    assert scenario.turn.active_player == "bob"

    casting = scenario.cast("Preordain", username="alice")
    assert casting is not None


def test_the_plus_one_grant_ends_at_the_controllers_own_next_turn():
    """The other edge: once alice's own next turn actually begins, the grant
    is gone (CR 611.2a) and ordinary sorcery timing applies again - which, in
    alice's own main phase with an empty stack, is legal anyway, so the
    boundary is checked earlier, in the same turn's combat phase where it
    would otherwise still be needed."""
    scenario = _board(
        alice_battlefield=["Teferi, Time Raveler"],
        bob_battlefield=[],
        alice_hand=["Preordain"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_teferis_plus_one(scenario)

    while scenario.turn.turn_number == 1 or scenario.turn.active_player != "alice":
        scenario.advance()
    assert scenario.game.casting_rule_effects == []

    scenario.advance()  # begin combat: past alice's new main phase, no grant left
    with pytest.raises(ValueError, match="during their own main phase"):
        scenario.cast("Preordain", username="alice")


# --------------------------------------------------------------------------
# CR 611.1's restriction judged against the *chosen* face (CR 601.3e, 715.3a)
# --------------------------------------------------------------------------
#
# `why_cannot_cast_restriction` asked `spell.card.types`, which reads
# `Card.front_type_line` - the front half's type line. For an adventurer card
# that is the creature, so the Adventure half inherited "is a creature spell"
# from a face nobody was casting: **Stomp, an `Instant - Adventure`, was cast
# freely under "your opponents can't cast noncreature spells this turn"**, and
# so was Petty Theft.
#
# CR 601.3e is the rule this is an instance of, and it says what the
# substitution means: "Some rules and effects state that an alternative set of
# characteristics or a subset of characteristics are considered to determine if
# a card or copy of a card is legal to cast. These alternative characteristics
# replace the object's characteristics for this determination." CR 715.3a is
# one such rule ("only the alternative characteristics are evaluated to see if
# it can be cast") and CR 709.3a is the other. Read in full off
# `.rules/MagicCompRules.txt` (effective August 7, 2026) with `mise run
# rules:find` in the session that wrote this block, along with CR 611.1
# ("A continuous effect ... affects players or the rules of the game"),
# CR 101.2 ("the 'can't' effect takes precedence"), CR 302.1 and CR 304.1.


def test_an_adventure_half_is_a_noncreature_spell_and_is_refused():
    """CR 715.3a with CR 611.1: Stomp is an Instant, so the restriction
    catches it - even though the card it is printed on is a creature.

    Staged in bob's own main phase so that CR 117.1a's timing, which is the
    *other* per-face CR 601.3 question and unrelated to this one, leaves both
    halves legal - the restriction is then the only thing that can refuse
    Stomp, and it has to refuse Stomp alone.
    """
    scenario = _board(
        alice_battlefield=["Ranger-Captain of Eos"],
        bob_battlefield=["Mountain", "Mountain", "Mountain"],
        bob_hand=["Bonecrusher Giant"],
    )
    _advance_to_bobs_precombat_main(scenario)
    _sacrifice_ranger_captain(scenario)

    casting = scenario.cast("Bonecrusher Giant", username="bob")

    with pytest.raises(ValueError, match="can't cast noncreature spells"):
        casting.cast_as_adventure()


def test_the_creature_half_of_the_same_card_is_still_castable():
    """The other side of the same printing, and the reason this cannot be
    fixed by refusing the whole card: Bonecrusher Giant itself is a creature
    spell (CR 302.1) and the restriction does not reach it.
    """
    scenario = _board(
        alice_battlefield=["Ranger-Captain of Eos"],
        bob_battlefield=["Mountain", "Mountain", "Mountain"],
        bob_hand=["Bonecrusher Giant"],
    )
    _advance_to_bobs_precombat_main(scenario)
    _sacrifice_ranger_captain(scenario)

    casting = scenario.cast("Bonecrusher Giant", username="bob")

    assert casting is not None
    assert casting.face is None, "no face named is the creature half"


def test_an_adventure_half_named_at_the_proposal_is_refused_too():
    """CR 709.3/715.3 put the choice before CR 601.2a's move, which is the
    order `Casting`'s constructor takes - the restriction has to read a face
    handed in there as well as one named afterwards.
    """
    scenario = _board(
        alice_battlefield=["Ranger-Captain of Eos"],
        bob_battlefield=["Mountain", "Mountain", "Mountain"],
        bob_hand=["Bonecrusher Giant"],
    )
    _advance_to_bobs_precombat_main(scenario)
    _sacrifice_ranger_captain(scenario)
    giant = scenario.find("Bonecrusher Giant", Zone.HAND, "bob")

    with pytest.raises(ValueError, match="can't cast noncreature spells"):
        Casting(
            spell=giant,
            caster="bob",
            origin_zone=Zone.HAND,
            game=scenario.game,
            face="Stomp",
        )

    assert giant.zone is Zone.HAND, "CR 601.3: a refused proposal moves nothing"


def test_the_enumeration_drops_the_adventure_row_under_the_restriction():
    """`legal_actions` asked `why_cannot_cast_restriction` once per card,
    above its own loop over the faces, so it offered `CAST spell_face=Stomp`
    while the restriction was live - the same hoisting shape the timing check
    had.
    """
    scenario = _board(
        alice_battlefield=["Ranger-Captain of Eos"],
        bob_battlefield=["Mountain", "Mountain", "Mountain"],
        bob_hand=["Bonecrusher Giant"],
    )
    _advance_to_bobs_precombat_main(scenario)
    _sacrifice_ranger_captain(scenario)
    if scenario.priority_holder != "bob":
        scenario.pass_priority(scenario.priority_holder)
    giant = scenario.find("Bonecrusher Giant", Zone.HAND, "bob")

    faces = {
        action.spell_face
        for action in scenario.game.legal_actions("bob")
        if action.kind is ActionKind.CAST and action.card_id == giant.id
    }

    assert faces == {None}, "the creature half only - Stomp is a noncreature spell"


def test_another_adventurer_cards_adventure_half_is_refused_as_well():
    """Generality, on a printing this defect was not found on and no decklist
    here uses: Brazen Borrower // Petty Theft. Different colour, different
    cost shape (`{1}{U}{U} // {1}{U}`), and its creature half carries flash,
    so neither half depends on sorcery-speed timing to reach the restriction.
    """
    scenario = _board(
        alice_battlefield=["Ranger-Captain of Eos"],
        bob_battlefield=["Island", "Island", "Island"],
        bob_hand=["Brazen Borrower"],
    )
    _advance_to_bobs_precombat_main(scenario)
    _sacrifice_ranger_captain(scenario)

    casting = scenario.cast("Brazen Borrower", username="bob")
    with pytest.raises(ValueError, match="can't cast noncreature spells"):
        casting.cast_as_adventure()
    casting.cancel()

    # The creature half still goes through, flash and all (CR 702.8a).
    assert scenario.cast("Brazen Borrower", username="bob") is not None


# --------------------------------------------------------------------------
# Spell-count caps: "<who> can't cast more than N [quality] spell(s) each
# turn" and "<who> can cast no more than N spells each turn" (CR 601.3,
# CR 101.2). The count, the subject, and the quality are all read off the
# sentence, not pinned to High Noon's "each player ... one spell".
# --------------------------------------------------------------------------


def _bolt(scenario: Scenario, username: str, at: str):
    if scenario.priority_holder != username:
        scenario.pass_priority(scenario.priority_holder)
    (mountain,) = scenario.untapped_sources("Mountain", username=username)[:1]
    return scenario.cast_and_resolve("Lightning Bolt", mountain, username=username, targets=[at])


def _cap_board(alice_battlefield: list[str], *, alice_hand: list[str], bob_hand: list[str]):
    return (
        Scenario()
        .player(
            "alice",
            hand=alice_hand,
            battlefield=alice_battlefield + ["Mountain"] * 4 + ["Forest"],
            library=["Mountain"] * 5,
        )
        .player(
            "bob",
            hand=bob_hand,
            battlefield=["Mountain"] * 4,
            library=["Mountain"] * 5,
        )
        .build()
    )


def test_curse_of_exhaustion_caps_the_enchanted_player():
    """ "Enchanted player can't cast more than one spell each turn." - bob is
    enchanted, so bob's second spell is refused."""
    scenario = _cap_board(
        ["Curse of Exhaustion"],
        alice_hand=[],
        bob_hand=["Lightning Bolt", "Lightning Bolt"],
    )
    curse = scenario.find("Curse of Exhaustion", Zone.BATTLEFIELD, username="alice")
    curse.attach_to(scenario.player("bob"))
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _advance_to_bobs_precombat_main(scenario)

    _bolt(scenario, "bob", "alice")
    with pytest.raises(ValueError, match="Curse of Exhaustion"):
        scenario.cast("Lightning Bolt", username="bob", targets=["alice"])
    assert scenario.player("alice").life == 17


def test_curse_of_exhaustion_leaves_the_unenchanted_player_alone():
    """The curse's own controller is not the enchanted player: two spells."""
    scenario = _cap_board(
        ["Curse of Exhaustion"],
        alice_hand=["Lightning Bolt", "Lightning Bolt"],
        bob_hand=[],
    )
    curse = scenario.find("Curse of Exhaustion", Zone.BATTLEFIELD, username="alice")
    curse.attach_to(scenario.player("bob"))
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _bolt(scenario, "alice", "bob")
    _bolt(scenario, "alice", "bob")

    assert scenario.player("bob").life == 14


def test_fires_of_invention_allows_two_spells_and_refuses_the_third():
    scenario = _cap_board(
        ["Fires of Invention"],
        alice_hand=["Lightning Bolt"] * 3,
        bob_hand=[],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _bolt(scenario, "alice", "bob")
    _bolt(scenario, "alice", "bob")
    with pytest.raises(ValueError, match="Fires of Invention"):
        scenario.cast("Lightning Bolt", username="alice", targets=["bob"])
    assert scenario.player("bob").life == 14


def test_fires_of_invention_refuses_its_controller_on_another_players_turn():
    """ "You can cast spells only during your turn" - the first half of the
    same sentence, which the count cap must not swallow."""
    scenario = _cap_board(
        ["Fires of Invention"],
        alice_hand=["Lightning Bolt"],
        bob_hand=["Lightning Bolt", "Lightning Bolt", "Lightning Bolt"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _advance_to_bobs_precombat_main(scenario)

    with pytest.raises(ValueError, match="Fires of Invention"):
        if scenario.priority_holder != "alice":
            scenario.pass_priority(scenario.priority_holder)
        scenario.cast("Lightning Bolt", username="alice", targets=["bob"])

    _bolt(scenario, "bob", "alice")
    _bolt(scenario, "bob", "alice")
    _bolt(scenario, "bob", "alice")
    assert scenario.player("alice").life == 11, "bob is not the one Fires restricts"


def test_deafening_silence_caps_noncreature_spells_only():
    """ "Each player can't cast more than one noncreature spell each turn." A
    second noncreature spell is refused; a creature spell after it is not."""
    scenario = _cap_board(
        ["Deafening Silence"],
        alice_hand=["Lightning Bolt", "Lightning Bolt", "Grizzly Bears"],
        bob_hand=[],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _bolt(scenario, "alice", "bob")
    with pytest.raises(ValueError, match="Deafening Silence"):
        scenario.cast("Lightning Bolt", username="alice", targets=["bob"])

    mountain = scenario.untapped_sources("Mountain", username="alice")[0]
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    bears = scenario.cast_and_resolve("Grizzly Bears", mountain, forest, username="alice")
    assert bears.zone is Zone.BATTLEFIELD
