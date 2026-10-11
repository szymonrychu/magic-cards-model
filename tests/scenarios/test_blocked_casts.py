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
from magic_cards_model.machines.casting import (
    exile_adventured,
    why_cannot_cast_now,
    why_cannot_cast_restriction,
)
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


def _silence_from_bob(scenario) -> None:
    """Bob casts and resolves Silence in alice's main phase, leaving the stack
    empty and alice's own sorcery timing open: a CR 611.1 prohibition on
    alice that applies while CR 117.1a would allow her cast."""
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Silence", *scenario.untapped_sources("Plains", username="bob"), username="bob"
    )
    assert scenario.game.can_cast_sorcery("alice")


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


# -- the keyword/granted cast-option loop also has to report its refusals --
#
# `why_cannot_cast_now` deliberately defers a keyword-cast-option's own
# timing to the option itself for any non-hand-zone card ("let
# `KeywordCastOption.why_not` answer instead of guessing over it" - its own
# docstring), and `KeywordCastOption.why_not` never actually asks CR 117.1a
# (only the option's own shape: zone, marker, discard). So a graveyard or
# exile keyword cast is never refused on CR 117.1a's timing through this
# path - a separate, pre-existing gap this task does not touch. What DOES
# still reach `_why_cannot_cast_face` for such a card is CR 611.1: a
# rules-modifying prohibition, asked by `why_cannot_cast_restriction`
# independently of zone or `option.why_not`. Grafdigger's Cage and Voice of
# Victory below are that half, proven on real printings.


def test_a_flashback_sorcery_blocked_by_a_prohibition_is_reported():
    """Faithless Looting's flashback (CR 702.34a) reaches the graveyard
    keyword-cast-option loop; Grafdigger's Cage's "Players can't cast
    spells from graveyards or libraries" is a CR 611.1 prohibition that
    still beats the flashback permission (CR 101.2, per
    `test_zone_cast_prohibitions.py`). The loop's `pays_mana_cost=False`
    branch computed this exact refusal and used to `continue` past it
    without recording it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            graveyard=["Faithless Looting"],
            battlefield=["Mountain", "Grafdigger's Cage"],
        )
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    looting = scenario.find("Faithless Looting", Zone.GRAVEYARD, "alice")

    expected_reason = why_cannot_cast_restriction(looting, "alice", scenario.game)
    assert expected_reason is not None
    assert "Grafdigger's Cage" in expected_reason

    (row,) = [b for b in _blocked(scenario, "alice") if b.card_id == looting.id]
    assert row.name == "Faithless Looting"
    assert row.zone is Zone.GRAVEYARD
    assert row.spell_face is None
    assert row.reason == expected_reason
    assert row.rule == "601.3"

    assert (looting.id, None) not in _cast_kinds(scenario, "alice")


def test_an_exiled_adventure_creature_blocked_by_a_prohibition_is_reported():
    """CR 715.3d: once Bonecrusher Giant's Adventure half (Stomp) resolves,
    the creature half is castable from exile through the same keyword-
    cast-option loop, `pays_mana_cost=True` this time (the creature's own
    `{2}{R}`). Silence, cast by bob in alice's own main phase ("Your
    opponents can't cast spells this turn"), is a CR 611.1 prohibition,
    computed by that branch and used to `continue` past without recording -
    and this card sits in exile, never hand, so no other loop in
    `_cast_actions` covers it either. (Voice of Victory's "during your turn"
    could never show it: on bob's turn the creature is refused on CR 117.1a
    timing first - CR 715.3d's permission changes the zone, not the timing.)

    CR 715.3d's permission covers the creature face only ("It can't be
    cast as an Adventure this way"), so that option enumerates no Stomp
    face at all and `blocked_casts`, walking the same loop, reports exactly
    one row - the creature's."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Bonecrusher Giant"], battlefield=["Mountain"] * 5)
        .player("bob", hand=["Silence"], battlefield=["Grizzly Bears", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain")
    casting = scenario.cast("Bonecrusher Giant")
    casting.cast_as_adventure()
    casting.choose_targets([scenario.creature("Grizzly Bears", "bob")])
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    stomp = scenario.resolve_top()
    exile_adventured(scenario.game, stomp, "alice")

    _silence_from_bob(scenario)
    giant = scenario.find("Bonecrusher Giant", Zone.EXILE, "alice")

    expected_reason = why_cannot_cast_restriction(giant, "alice", scenario.game)
    assert expected_reason is not None
    assert "Silence" in expected_reason

    rows = {b.spell_face: b for b in _blocked(scenario, "alice") if b.card_id == giant.id}
    assert set(rows) == {None}
    for row in rows.values():
        assert row.name == "Bonecrusher Giant"
        assert row.zone is Zone.EXILE
        assert row.reason == expected_reason
        assert row.rule == "611.1"

    assert (giant.id, None) not in _cast_kinds(scenario, "alice")
    assert (giant.id, "Stomp") not in _cast_kinds(scenario, "alice")


def test_the_stomp_face_of_an_exiled_adventure_card_is_never_a_legal_cast_not_merely_blocked():
    """Same board as the prohibition test above, but without Silence: in
    alice's own main phase with the stack empty nothing refuses the exiled
    Bonecrusher Giant's creature face or its Stomp face on CR 117.1a timing
    (Stomp is an instant) or a CR 611.1 prohibition, so neither is a
    `blocked_casts` row - but CR 715.3d still makes recasting Stomp from
    exile illegal, and `legal_actions` should not list it as a legal CAST
    either."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Bonecrusher Giant"], battlefield=["Mountain"] * 5)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain")
    casting = scenario.cast("Bonecrusher Giant")
    casting.cast_as_adventure()
    casting.choose_targets([scenario.creature("Grizzly Bears", "bob")])
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    stomp = scenario.resolve_top()
    exile_adventured(scenario.game, stomp, "alice")

    giant = scenario.find("Bonecrusher Giant", Zone.EXILE, "alice")

    rows = {b.spell_face: b for b in _blocked(scenario, "alice") if b.card_id == giant.id}
    assert "Stomp" not in rows
    assert (giant.id, "Stomp") not in _cast_kinds(scenario, "alice")
    assert (giant.id, None) in _cast_kinds(scenario, "alice")


def test_another_exiled_adventurers_sorcery_half_is_never_a_row_or_a_cast():
    """The same CR 715.3d limit on a different adventurer, Lovestruck Beast
    (Heart's Desire is a `Sorcery - Adventure` for {G}): a mechanic of the
    permission, not of Bonecrusher Giant. In alice's own main phase the
    creature is a legal cast from exile and Heart's Desire is not; once bob
    resolves Silence, its CR 611.1 prohibition refuses the creature, and
    that refusal is the only row - Heart's Desire is never offered this way,
    so it is never "blocked"."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lovestruck Beast"], battlefield=["Forest"] * 4)
        .player("bob", hand=["Silence"], battlefield=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Lovestruck Beast")
    casting.cast_as_adventure()
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Forest"))
    scenario.put_on_stack(casting)
    beast = scenario.resolve_top()
    assert beast.zone is Zone.EXILE

    kinds = _cast_kinds(scenario, "alice")
    assert (beast.id, None) in kinds
    assert (beast.id, "Heart's Desire") not in kinds

    _silence_from_bob(scenario)
    rows = {b.spell_face: b for b in _blocked(scenario, "alice") if b.card_id == beast.id}
    assert set(rows) == {None}
    assert rows[None].rule == "611.1"
    assert "Silence" in rows[None].reason


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
