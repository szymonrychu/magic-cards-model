"""Veil of Summer's player-hexproof clause (flow 1 T12): "You ... gain
hexproof from blue and from black until end of turn" (CR 702.11c crossed
with CR 702.11d's "hexproof from [quality]" and CR 702.11f's "from A and
from B" split into two abilities).

This sits on top of two pieces of prior work, both already on `main`:

- Flow 2 built the generic player-hexproof/shroud machinery:
  `Player.targeting_grants` (a list of `PlayerTargetingGrant`, each with an
  optional `quality`), `Game.grant_player_hexproof`/`grant_player_shroud`,
  `Game.player_hexproof`, and the enforcement itself -
  `Game.hexproof_refusal`, asked by `TargetingProfile.check` at
  announcement, by the live-candidate filters, and by `legal_target`'s own
  CR 608.2b resolution recheck. `tests/scenarios/test_player_hexproof_
  shroud.py` covers all of that generically (Blossoming Calm, and direct
  calls to `Game.grant_player_hexproof`), including
  `test_the_clause_parser_reads_hexproof_from_two_qualities_on_you`, which
  proves the clause reader (`_player_gains_hexproof_clause`,
  `_PLAYER_GAINS_HEXPROOF_RE`) already reads Veil's exact sentence once its
  subject is narrowed to "You" alone.
- Flow 1 T5/G2b split Veil's compound "You and permanents you control gain
  hexproof from blue and from black until end of turn" into two
  instructions with the same predicate (CR 608.2c) -
  `_parse_you_and_group_gain_clause`. It wired the *permanents* half
  straight into the existing mass-grant reader, but the *player* half was
  deliberately left as a recorded `PlayerSubjectSplitNotice` rather than a
  grant - out of scope for that task on purpose (see that model's own
  docstring). `tests/scenarios/test_veil_of_summer.py`'s own
  `test_the_player_half_is_neither_granted_nor_silently_dropped` is the
  record of that gap.

This file is what closes the gap: the player half is now handed to the
identical `parse_clause_effect` reader flow 2 already proved reads it,
rather than only being recorded.

Proof exemption (D2): CR 702.11d's "hexproof from [quality]" granted to a
*player* (not a permanent) is vanishingly rare print-to-print, and a search
of every local fixture printing under `src/magic_cards_model/data/
printings/` for "hexproof from" on a "you"/"you have hexproof" subject
turns up nothing besides Veil of Summer. No other Modern-, Pioneer- or
Standard-legal printing grants a player hexproof from a quality, so this
file proves the mechanism on Veil itself rather than on a second printing -
see `docs/engine-coverage.md`'s own Veil row for the fuller argument. The
*mechanism* being wired here (routing a compound "You and `<group>`"
player-half clause through the ordinary player-clause reader) is still
general: a future card with a different player-half predicate the reader
cannot read still falls back to `PlayerSubjectSplitNotice`, unchanged.

Every CR number here was looked up with `mise run rules:find` in the
session that wrote this file: CR 702.11c, CR 702.11d, CR 702.11f, CR 608.2b,
CR 514.2.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers import Duration
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# -- (a)/(b)/(c): board with real pool printings in all three of Veil's
# relevant colours, plus abilities from permanents of each colour ----------


def _board() -> Scenario:
    """`bob` is registered first, so it is *his* turn (CR 103.8's starting
    player is `players[0]`) - Mind Rot and Lava Spike are sorceries with no
    flash, and a tap-cost ability needs its controller's own turn to have
    begun (CR 302.6), so every "bob can/cannot" assertion below needs him to
    be the active player, not merely a second player in the game."""
    return (
        Scenario()
        .player(
            "bob",
            hand=["Mind Rot", "Peek", "Lava Spike"],
            battlefield=[
                "Swamp",
                "Island",
                "Mountain",
                "Persistent Petitioners",  # blue activated ability, targets a player
                "Bile Urchin",  # black activated ability, targets a player
                "Orcish Spy",  # red activated ability, targets a player
            ],
        )
        .player(
            "alice",
            hand=["Veil of Summer"],
            battlefield=["Forest"],
        )
        .build()
    )


def _cast_veil(scenario: Scenario) -> None:
    """Bob's own precombat main, stack empty: he opens with priority
    (CR 117.3a), passes without acting, and alice - the *non*-active player -
    casts Veil (an instant, legal any time she has priority). Once it
    resolves, priority returns to bob (CR 117.3b), still in his own main
    phase with an empty stack, so his own sorcery-speed spells and tap
    abilities below are legal to attempt."""
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("bob")
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_and_resolve("Veil of Summer", forest, username="alice")


# -- (a) an opponent's blue or black spell cannot target the Veil caster ---


def test_a_blue_spell_from_an_opponent_cannot_target_the_veil_caster():
    """CR 702.11d: Peek is blue, and bob is an opponent of alice's, the
    player who cast Veil."""
    scenario = _board()
    _cast_veil(scenario)

    (island,) = scenario.untapped_sources("Island", username="bob")
    with pytest.raises(ValueError, match="hexproof from blue"):
        scenario.cast_onto_stack("Peek", island, username="bob", targets=["alice"])


def test_a_black_spell_from_an_opponent_cannot_target_the_veil_caster():
    """CR 702.11d: Mind Rot is black."""
    scenario = _board()
    _cast_veil(scenario)

    sources = scenario.untapped_sources("Swamp", "Island", "Mountain", username="bob")
    with pytest.raises(ValueError, match="hexproof from black"):
        scenario.cast_onto_stack("Mind Rot", *sources, username="bob", targets=["alice"])


def test_a_red_spell_from_an_opponent_can_still_target_the_veil_caster():
    """Veil grants hexproof from blue *and* from black (CR 702.11f: two
    separate abilities) - never from red, so Lava Spike is unaffected."""
    scenario = _board()
    _cast_veil(scenario)

    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lava Spike", mountain, username="bob", targets=["alice"])
    assert scenario.player("alice").life == 17, "3 damage - the Spike was not refused"


# -- (b) the Veil caster's own blue spell can still target them (CR
# 702.11b/CR 702.11d's "your opponents" exception, not "anyone") -----------


def test_the_veil_casters_own_blue_spell_can_still_target_them():
    scenario = (
        Scenario()
        .player("alice", hand=["Veil of Summer", "Peek"], battlefield=["Forest", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_and_resolve("Veil of Summer", forest, username="alice")

    (island,) = scenario.untapped_sources("Island", username="alice")
    # Would raise if alice's own hexproof-from-blue refused her own spell.
    scenario.cast_and_resolve("Peek", island, username="alice", targets=["alice"])


# -- (c) an ability bob controls from a blue or black source cannot target
# alice, one from a red source can (CR 702.11d speaks of "sources", not
# just spells) ---------------------------------------------------------


def test_a_blue_ability_from_an_opponent_cannot_target_the_veil_caster():
    scenario = _board()
    _cast_veil(scenario)

    petitioners = scenario.creature("Persistent Petitioners", "bob")
    (island,) = scenario.untapped_sources("Island", username="bob")
    with pytest.raises(ValueError, match="hexproof from blue"):
        scenario.activate(petitioners, island, username="bob", targets=["alice"])


def test_a_black_ability_from_an_opponent_cannot_target_the_veil_caster():
    scenario = _board()
    _cast_veil(scenario)

    urchin = scenario.creature("Bile Urchin", "bob")
    with pytest.raises(ValueError, match="hexproof from black"):
        scenario.activate(urchin, username="bob", sacrificing=[urchin], targets=["alice"])


def test_a_red_ability_from_an_opponent_can_still_target_the_veil_caster():
    scenario = _board()
    _cast_veil(scenario)

    spy = scenario.creature("Orcish Spy", "bob")
    scenario.activate(spy, username="bob", targets=["alice"])  # would raise if refused


# -- (d) Veil cast in response makes an already-announced black spell
# fizzle (CR 608.2b: a target that becomes illegal is illegal at
# resolution) -----------------------------------------------------------


def test_veil_cast_in_response_makes_a_black_discard_spell_fizzle():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", hand=["Mind Rot"], battlefield=["Swamp", "Island", "Mountain"])
        .player(
            "alice",
            hand=["Veil of Summer"],
            battlefield=["Forest"],
            # Bob's Mind Rot is black, so Veil's own first sentence ("Draw a
            # card if an opponent has cast a blue or black spell this turn")
            # fires too - a non-empty library keeps that draw from being a
            # CR 104.3c loss, which is not what this test is about.
            library=["Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)  # bob's own turn (players[0])
    mind_rot_sources = scenario.untapped_sources("Swamp", "Island", "Mountain", username="bob")
    scenario.cast_onto_stack("Mind Rot", *mind_rot_sources, username="bob", targets=["alice"])
    scenario.pass_priority("bob")
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_onto_stack("Veil of Summer", forest, username="alice")

    scenario.resolve_top()  # Veil of Summer resolves, grants alice hexproof from black
    # Measured *after* Veil (whose own first sentence draws alice a card,
    # since bob cast a black spell this turn) and *before* Mind Rot would
    # discard - isolating "Mind Rot did nothing" from Veil's own draw.
    hand_before = len(scenario.player("alice").hand)
    mind_rot_on_stack = scenario.game.stack[-1]
    assert scenario.game.spell_fizzles(mind_rot_on_stack)
    scenario.resolve_top()  # Mind Rot, with no legal target left - CR 608.2b

    assert scenario.find("Mind Rot", Zone.GRAVEYARD, "bob").zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == hand_before, "nothing was discarded"


# -- (e) the grant ends at cleanup (CR 514.2), and next turn the caster is
# targetable again -------------------------------------------------------


def test_the_grant_ends_at_cleanup_and_the_caster_is_targetable_next_turn():
    scenario = _board()
    _cast_veil(scenario)
    alice = scenario.player("alice")
    assert alice.targeting_grants, "Veil did not grant anything to alice"

    scenario.game.cleanup_step()

    assert alice.targeting_grants == []
    bolt_source_spell = scenario.find("Mind Rot", Zone.HAND, "bob")
    assert scenario.game.hexproof_refusal(alice, "bob", bolt_source_spell) is None


# -- (f) CR 702.11f: "from blue and from black" is two abilities, proven on
# the real, unmodified card text - the full spell now resolves every
# clause, not just the permanents half -----------------------------------


def test_the_full_card_grants_both_qualities_as_two_abilities():
    scenario = _board()
    _cast_veil(scenario)
    alice = scenario.player("alice")

    grants = [g for g in alice.targeting_grants if g.keyword == "hexproof"]
    assert sorted(g.quality for g in grants) == ["black", "blue"]
    assert all(g.duration is Duration.UNTIL_END_OF_TURN for g in grants)
    # The old recorded-gap notice is retired now that the player half is
    # actually granted - it must not also show up as an unread gap.
    assert scenario.game.player_subject_split_notices == []

    mind_rot = scenario.find("Mind Rot", Zone.HAND, "bob")
    peek = scenario.find("Peek", Zone.HAND, "bob")
    lava_spike = scenario.find("Lava Spike", Zone.HAND, "bob")
    assert "hexproof from black" in scenario.game.hexproof_refusal(alice, "bob", mind_rot)
    assert "hexproof from blue" in scenario.game.hexproof_refusal(alice, "bob", peek)
    assert scenario.game.hexproof_refusal(alice, "bob", lava_spike) is None
