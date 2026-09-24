"""Scenario: `blocked_casts` - the enumeration of every cast CR 601.3
refuses on timing or a rules-modifying prohibition, reported with the
engine's own reason.

`machines.legal_actions._cast_actions` silently `continue`d past a face
`_why_cannot_cast_face` refused: CR 117.1a's timing
(`casting.why_cannot_cast_now`) and CR 611.1's prohibitions
(`casting.why_cannot_cast_restriction`) both go through that one function,
and a seat reading `legal_actions` alone could never tell "nothing is
legal" apart from "Ocelot Pride sat in hand the whole game, uncastable only
because the stack was never empty" - the exact defect `blocked_casts` and
`BlockedCast` (`models/action.py`) exist to fix.

`legal_actions` itself is untouched: a face `blocked_casts` reports is still
absent from it, because CR 601.3 makes a refused cast illegal, full stop.

Every CR number in this file was read in full off `.rules/MagicCompRules.txt`
with `mise run rules:find` in the session that wrote it:

- **CR 117.1a** - "A player may cast an instant spell any time they have
  priority. A player may cast a noninstant spell during their main phase any
  time they have priority and the stack is empty."
- **CR 702.8a** - "Flash is a static ability... 'You may play this card any
  time you could cast an instant.'"
- **CR 307.1** - "A player who has priority may cast a sorcery card from
  their hand during a main phase of their turn when the stack is empty."
- **CR 611.1** - "A continuous effect modifies characteristics of objects,
  modifies control of objects, or affects players or the rules of the game,
  for a fixed or indefinite period."
- **CR 601.3** - "A player can begin to cast a spell only if a rule or
  effect allows that player to cast it and no rule or effect prohibits that
  player from casting it."
- **CR 601.3e** - "Some rules and effects state that an alternative set of
  characteristics or a subset of characteristics are considered to determine
  if a card or copy of a card is legal to cast." (CR 709.3a's split-card
  choice is one instance.)
- **CR 305.1** - "Since the land doesn't go on the stack, it is never a
  spell..."
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import why_cannot_cast_now, why_cannot_cast_restriction
from magic_cards_model.machines.decisions import Decision, DecisionKind, DecisionPending
from magic_cards_model.machines.legal_actions import blocked_casts
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from tests.scenarios.harness import Scenario


def _cast_kinds(scenario, username: str) -> set[str]:
    return {
        (action.card_id, action.spell_face)
        for action in scenario.game.legal_actions(username)
        if action.kind is ActionKind.CAST
    }


def _blocked(scenario, username: str) -> list:
    return blocked_casts(scenario.game, username)


def _advance_to(scenario, username: str, step: Step) -> None:
    while scenario.turn.active_player != username or scenario.step is not step:
        scenario.advance()


# -- CR 117.1a timing: a non-flash noninstant with the stack non-empty ------


def test_a_blocked_creature_is_reported_with_the_engines_own_reason_and_rule():
    """Ocelot Pride, in its own controller's precombat main, with a spell on
    the stack: CR 117.1a refuses it, and `blocked_casts` reports that exact
    refusal - never a synthesized message."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", hand=["Ocelot Pride", "Lightning Bolt"], battlefield=["Plains", "Mountain"]
        )
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])
    ocelot = scenario.find("Ocelot Pride", Zone.HAND, "alice")

    expected_reason = why_cannot_cast_now(ocelot, "alice", scenario.game)
    assert expected_reason is not None, "the stack is non-empty - the cast must be refused"

    blocked = _blocked(scenario, "alice")
    (row,) = [b for b in blocked if b.card_id == ocelot.id]
    assert row.name == "Ocelot Pride"
    assert row.zone is Zone.HAND
    assert row.spell_face is None
    assert row.reason == expected_reason
    assert row.rule == "117.1a"

    assert (ocelot.id, None) not in _cast_kinds(scenario, "alice")


def test_the_same_card_with_an_empty_stack_is_legal_and_not_blocked():
    """The other side of the same check: nothing on the stack, alice's own
    main phase - CR 117.1a's second sentence is satisfied outright."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Ocelot Pride"], battlefield=["Plains"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ocelot = scenario.find("Ocelot Pride", Zone.HAND, "alice")

    assert (ocelot.id, None) in _cast_kinds(scenario, "alice")
    assert all(b.card_id != ocelot.id for b in _blocked(scenario, "alice"))


def test_a_sorcery_in_hand_during_the_opponents_turn_is_blocked():
    """CR 307.1: a sorcery may only be cast during its controller's own main
    phase - alice holding Act of Treason during bob's precombat main is
    refused, even though a stack-emptiness check alone would pass."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Act of Treason"], battlefield=["Mountain"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    _advance_to(scenario, "bob", Step.PRECOMBAT_MAIN)
    act_of_treason = scenario.find("Act of Treason", Zone.HAND, "alice")

    expected_reason = why_cannot_cast_now(act_of_treason, "alice", scenario.game)
    assert expected_reason is not None

    (row,) = [b for b in _blocked(scenario, "alice") if b.card_id == act_of_treason.id]
    assert row.reason == expected_reason
    assert row.rule == "117.1a"
    assert (act_of_treason.id, None) not in _cast_kinds(scenario, "alice")


# -- an instant, and a real flash creature, are never blocked at instant speed


def test_an_instant_is_never_blocked_regardless_of_timing():
    """CR 304.1/117.1a's first sentence: an instant may be cast any time its
    controller has priority - proven during the opponent's own main phase,
    the timing window a noninstant would be refused in."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    _advance_to(scenario, "bob", Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")

    assert all(b.card_id != bolt.id for b in _blocked(scenario, "alice"))
    assert (bolt.id, None) in _cast_kinds(scenario, "alice")


def test_a_real_flash_creature_is_never_blocked_at_instant_speed():
    """CR 702.8a: Ambush Viper prints Flash, so it is cast on CR 117.1a's
    instant-speed side of the rule - a real printing, not in this repo's
    deck pool, proving the check generalizes past Ocelot Pride."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Ambush Viper"], battlefield=["Forest"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    _advance_to(scenario, "bob", Step.PRECOMBAT_MAIN)
    viper = scenario.find("Ambush Viper", Zone.HAND, "alice")

    assert all(b.card_id != viper.id for b in _blocked(scenario, "alice"))
    assert (viper.id, None) in _cast_kinds(scenario, "alice")


# -- CR 709.3a: a split card's two halves are judged separately -------------


def test_split_card_blocks_only_the_sorcery_half():
    """Repudiate // Replicate is Instant // Sorcery. Off its controller's
    main phase, only Replicate (the Sorcery half) is refused; Repudiate (the
    Instant half) is never blocked. CR 709.3a: "Only the chosen half is
    evaluated to see if it can be cast.\""""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Repudiate // Replicate"], battlefield=["Forest", "Island"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.UPKEEP)
    card = scenario.find("Repudiate", Zone.HAND, "alice")

    expected_reason = why_cannot_cast_now(card, "alice", scenario.game, face="Replicate")
    assert expected_reason is not None
    assert why_cannot_cast_now(card, "alice", scenario.game, face="Repudiate") is None

    blocked = _blocked(scenario, "alice")
    faces = {b.spell_face for b in blocked if b.card_id == card.id}
    assert faces == {"Replicate"}
    (row,) = [b for b in blocked if b.card_id == card.id]
    assert row.reason == expected_reason
    assert row.rule == "117.1a"

    kinds = _cast_kinds(scenario, "alice")
    assert (card.id, "Repudiate") in kinds
    assert (card.id, "Replicate") not in kinds


# -- CR 611.1: a rules-modifying prohibition, not a timing question ---------


def test_a_cr_611_1_prohibition_is_reported_with_its_own_text():
    """Voice of Victory: "Your opponents can't cast spells during your
    turn." During bob's turn, alice's Lightning Bolt passes CR 117.1a's
    instant-speed timing outright and is refused only by this CR 611.1
    prohibition - proving `blocked_casts` reports the restriction's own
    reason, not a timing message."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Mountain", "Voice of Victory"])
        .build()
    )
    _advance_to(scenario, "bob", Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")

    assert why_cannot_cast_now(bolt, "alice", scenario.game) is None, (
        "an instant's own timing is fine - only the prohibition refuses this"
    )
    expected_reason = why_cannot_cast_restriction(bolt, "alice", scenario.game)
    assert expected_reason is not None
    assert "Voice of Victory" in expected_reason

    (row,) = [b for b in _blocked(scenario, "alice") if b.card_id == bolt.id]
    assert row.reason == expected_reason
    assert row.rule == "611.1"
    assert (bolt.id, None) not in _cast_kinds(scenario, "alice")


# -- CR 305.1: a land is never a spell, never a blocked_casts candidate -----


def test_a_land_is_never_listed_even_when_it_would_read_as_blocked():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Mountain"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    _advance_to(scenario, "bob", Step.PRECOMBAT_MAIN)
    mountain = scenario.find("Mountain", Zone.HAND, "alice")

    assert all(b.card_id != mountain.id for b in _blocked(scenario, "alice"))


# -- blocked_casts is timing/prohibition only, never a zone-permission gap --


def test_a_graveyard_card_with_no_cast_permission_is_neither_legal_nor_blocked():
    """A card sitting in the graveyard with no flashback, no dredge, no
    granted `PlayPermission` fails `why_cannot_cast_from` outright - that is
    CR 601.3's *other* half ("a rule or effect allows... to cast it"), which
    `blocked_casts` does not report at all, the same way `legal_actions`
    offers no `CAST` action for it either."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", graveyard=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")

    assert all(b.card_id != bolt.id for b in _blocked(scenario, "alice"))
    assert (bolt.id, None) not in _cast_kinds(scenario, "alice")


# -- a pending decision suspends blocked_casts, same as legal_actions -------


def test_blocked_casts_is_empty_while_a_decision_is_pending():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", hand=["Ocelot Pride", "Lightning Bolt"], battlefield=["Plains", "Mountain"]
        )
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])
    # Ocelot Pride is genuinely blocked right now - confirm the ordinary case
    # first so the pending check below is proven against a real positive.
    assert _blocked(scenario, "alice")

    scenario.game.decisions.pause_when_unanswered = True
    decision = Decision(kind=DecisionKind.MAY, player="alice", prompt="do the thing")
    try:
        scenario.game.ask(decision)
    except DecisionPending as excinfo:
        pending = excinfo.pending
    else:  # pragma: no cover - `pause_when_unanswered` always raises here
        raise AssertionError("expected DecisionPending")

    assert blocked_casts(scenario.game, "alice", pending) == []


# -- hidden information: only the asked player's own cards are ever listed --


def test_only_the_asked_players_own_cards_are_listed():
    """bob's Ocelot Pride is blocked by his own spell on the stack; asking
    `blocked_casts` for alice - who holds nothing blocked - must never
    surface bob's hidden hand."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Mountain"])
        .player("bob", hand=["Ocelot Pride", "Lightning Bolt"], battlefield=["Plains", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    ocelot = scenario.find("Ocelot Pride", Zone.HAND, "bob")

    assert any(b.card_id == ocelot.id for b in _blocked(scenario, "bob"))
    assert _blocked(scenario, "alice") == []
