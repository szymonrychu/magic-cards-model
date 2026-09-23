"""Hexproof and shroud on a *player* (CR 702.11c, CR 702.18a's "or player").

Verified this session with `mise run rules:find`:

- CR 702.11c: "'Hexproof' on a player means 'You can't be the target of spells
  or abilities your opponents control.'"
- CR 702.11d: "'Hexproof from [quality]' ... can't be the target of [quality]
  spells your opponents control or abilities your opponents control from
  [quality] sources."
- CR 702.11f: "'Hexproof from [quality A] and from [quality B]' is shorthand
  for 'hexproof from [quality A]' and 'hexproof from [quality B]'; it behaves
  as two separate hexproof abilities."
- CR 702.11h: "Multiple instances of the same hexproof ability on the same
  permanent or player are redundant."
- CR 702.18a: "'Shroud' means 'This permanent or player can't be the target of
  spells or abilities.'"
- CR 608.2b: a target that has become illegal is illegal at resolution, and a
  spell whose every target is illegal does not resolve.
- CR 611.2a: a continuous effect from a resolved spell "lasts as long as stated
  by the spell or ability creating it"; CR 514.2 ends "until end of turn"
  effects in cleanup, and "until your next turn" ends as that turn begins.
- CR 604.2 / CR 611.3a: a static ability's effect ("You have hexproof.") lasts
  only while its source is on the battlefield.

Two ways a player gets it, both real:

- **A static grant from a permanent they control** - Leyline of Sanctity and
  Aegis of the Gods ("You have hexproof."), True Believer and Ivory Mask ("You
  have shroud."). Read fresh from the battlefield on every check, the way
  `Game.player_protection_qualities` reads Runed Halo, so it ends with its
  permanent.
- **A resolved spell** - Blossoming Calm ("You gain hexproof until your next
  turn."), recorded on `Player.targeting_grants` with its duration and expired
  at CR 611.2a's stated boundary.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from magic_cards_model.machines.effects import effect_for, parse_clause_effect
from magic_cards_model.machines.layers import Duration
from magic_cards_model.machines.triggers import TargetingNoticeKind
from magic_cards_model.models import Zone
from magic_cards_model.models.game import Game
from tests.cards import card
from tests.scenarios.harness import Scenario

# -- "You have hexproof." (Leyline of Sanctity, Aegis of the Gods) -----------


@pytest.mark.parametrize("granter", ["Leyline of Sanctity", "Aegis of the Gods"])
def test_an_opponents_spell_cannot_target_a_player_with_hexproof(granter: str):
    """CR 702.11c: bob's Lightning Bolt cannot be aimed at alice."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[granter])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")

    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError, match="alice has hexproof"):
        casting.choose_targets(["alice"])
    assert scenario.find("Lightning Bolt", Zone.HAND, "bob").zone is Zone.HAND


def test_the_hexproof_players_own_spell_can_target_them():
    """CR 702.11c names *your opponents*: alice may Bolt herself."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Leyline of Sanctity", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["alice"]
    )
    assert scenario.player("alice").life == 17


def test_the_other_player_is_still_a_legal_target():
    """Leyline of Sanctity protects only its controller."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Leyline of Sanctity", "Mountain"])
        .player("bob", battlefield=["Leyline of Sanctity"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Lightning Bolt", username="alice")
    with pytest.raises(ValueError, match="bob has hexproof"):
        casting.choose_targets(["bob"])


def test_an_opponents_triggered_ability_cannot_choose_the_hexproof_player():
    """CR 702.11c covers abilities too. Sunscorched Desert's "When this land
    enters, it deals 1 damage to target player or planeswalker." under bob
    cannot name alice - the staged choice is refused through the same
    `TargetingProfile.check` a spell's announcement uses."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Aegis of the Gods"])
        .player("bob", hand=["Sunscorched Desert"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Sunscorched Desert", "bob")

    with pytest.raises(ValueError, match="alice has hexproof"):
        scenario.choose_trigger_targets("Sunscorched Desert", ["alice"])


def test_an_opponents_trigger_asked_live_is_not_offered_the_hexproof_player():
    """The live `CHOOSE_TARGETS` question offers only legal candidates: naming
    alice is refused, naming bob himself is accepted."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Leyline of Sanctity"])
        .player("bob", hand=["Sunscorched Desert"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Sunscorched Desert", "bob")
    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.CHOOSE_TARGETS, value=("alice",), player="bob")
    )
    with pytest.raises(ValueError):
        scenario.game.put_triggers_on_stack()


def test_a_target_opponent_trigger_has_no_legal_target_against_a_hexproof_opponent():
    """Grief's "target opponent reveals their hand" under bob: alice, the only
    opponent, has hexproof, so CR 603.3d removes the trigger - never placed
    with an illegal target."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Leyline of Sanctity"])
        .player("bob", hand=["Grief"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Grief", "bob")
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack == []
    assert any(
        notice.kind is TargetingNoticeKind.NO_LEGAL_TARGET and notice.source_name == "Grief"
        for notice in scenario.game.targeting_notices
    )


def test_the_static_grant_ends_when_its_permanent_leaves():
    """CR 604.2: Aegis of the Gods' grant lasts only while it is on the
    battlefield - once it dies, bob's Bolt may target alice."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Aegis of the Gods"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    aegis = scenario.creature("Aegis of the Gods", "alice")
    scenario.game.put_into_graveyard(aegis)

    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=["alice"],
    )
    assert scenario.player("alice").life == 17


# -- "You have shroud." (True Believer, Ivory Mask) ------------------------


@pytest.mark.parametrize("granter", ["True Believer", "Ivory Mask"])
def test_shroud_refuses_even_the_players_own_spell(granter: str):
    """CR 702.18a has no controller exception: alice cannot Bolt herself."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=[granter, "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Lightning Bolt", username="alice")
    with pytest.raises(ValueError, match="alice has shroud"):
        casting.choose_targets(["alice"])


def test_shroud_refuses_an_opponents_spell():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Ivory Mask"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")

    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError, match="alice has shroud"):
        casting.choose_targets(["alice"])


def test_shroud_refuses_the_players_own_triggered_ability():
    """Sunscorched Desert under alice cannot name alice while True Believer
    is out - but may name bob."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Sunscorched Desert"], battlefield=["True Believer"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Sunscorched Desert", "alice")

    with pytest.raises(ValueError, match="alice has shroud"):
        scenario.choose_trigger_targets("Sunscorched Desert", ["alice"])
    scenario.choose_trigger_targets("Sunscorched Desert", ["bob"])


def test_the_shroud_grant_ends_when_true_believer_leaves():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["True Believer", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    believer = scenario.creature("True Believer", "alice")
    scenario.game.put_into_graveyard(believer)

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["alice"]
    )
    assert scenario.player("alice").life == 17


# -- Blossoming Calm: "You gain hexproof until your next turn." ------------


def test_blossoming_calm_parses_as_a_player_hexproof_grant():
    calm = card("Blossoming Calm")
    assert effect_for(calm.name, calm.oracle_text) is not None


def _calm_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Blossoming Calm"],
            battlefield=["Plains"],
            library=["Plains"] * 5,
        )
        .player(
            "bob",
            hand=["Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain"],
            library=["Mountain"] * 5,
        )
        .build()
    )


def _advance_until(scenario, predicate) -> None:
    for _ in range(60):
        if predicate(scenario):
            return
        scenario.advance()
    raise AssertionError("never reached the wanted step")


def test_blossoming_calm_grants_hexproof_that_survives_the_opponents_turn():
    """CR 611.2a: "until your next turn" outlasts alice's cleanup (CR 514.2
    ends only "until end of turn") and all of bob's turn."""
    scenario = _calm_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Blossoming Calm", *scenario.untapped_sources("Plains"))
    assert scenario.player("alice").life == 22

    _advance_until(
        scenario, lambda s: s.turn.active_player == "bob" and s.step is Step.PRECOMBAT_MAIN
    )
    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError, match="alice has hexproof"):
        casting.choose_targets(["alice"])


def test_blossoming_calms_hexproof_ends_as_alices_next_turn_begins():
    scenario = _calm_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Blossoming Calm", *scenario.untapped_sources("Plains"))
    alice = scenario.player("alice")
    assert alice.targeting_grants

    _advance_until(scenario, lambda s: s.turn.active_player == "bob" and s.step is Step.CLEANUP)
    assert alice.targeting_grants, "bob's cleanup does not end 'until your next turn'"

    _advance_until(scenario, lambda s: s.turn.active_player == "alice")
    assert alice.targeting_grants == []
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    assert scenario.game.hexproof_refusal(alice, "bob", bolt) is None


def test_blossoming_calm_in_response_makes_a_burn_spell_fizzle():
    """CR 608.2b: bob's Bolt was legally aimed at alice; alice answers with
    Blossoming Calm, so at resolution the Bolt's only target is illegal and it
    does not resolve."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Blossoming Calm"], battlefield=["Plains"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=["alice"],
    )
    scenario.pass_priority("bob")
    scenario.cast_onto_stack("Blossoming Calm", *scenario.untapped_sources("Plains"))

    scenario.resolve_top()  # Blossoming Calm
    bolt_on_stack = scenario.game.stack[-1]
    assert scenario.game.spell_fizzles(bolt_on_stack)
    scenario.resolve_top()  # Lightning Bolt, with no legal target left

    assert scenario.player("alice").life == 22
    assert scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob").zone is Zone.GRAVEYARD


# -- Effect-granted grants through the public Game API ---------------------


def _grant_board() -> Scenario:
    """alice, the active player, holds a black sorcery aimed at a player
    (Thoughtseize) and a red one (Lava Spike); bob is the one granted."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Thoughtseize", "Lava Spike"],
            battlefield=["Swamp", "Mountain"],
        )
        .player("bob", battlefield=["Mountain"])
        .build()
    )


def test_a_player_hexproof_from_black_refuses_a_black_spell_and_allows_a_red_one():
    """CR 702.11d on a player, staged through `Game.grant_player_hexproof` -
    the same call the "you gain hexproof from ..." clause makes. Thoughtseize
    is black and is refused; Lava Spike is red and is allowed."""
    scenario = _grant_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.grant_player_hexproof(
        "bob", ("black",), duration=Duration.UNTIL_END_OF_TURN, source_name="a test grant"
    )

    casting = scenario.cast("Thoughtseize", username="alice")
    with pytest.raises(ValueError, match="bob has hexproof from black"):
        casting.choose_targets(["bob"])

    scenario.cast_and_resolve("Lava Spike", *scenario.untapped_sources("Mountain"), targets=["bob"])
    assert scenario.player("bob").life == 17


def test_hexproof_from_two_qualities_is_two_abilities():
    """CR 702.11f: "from blue and from black" refuses each quality on its own."""
    scenario = _grant_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.grant_player_hexproof(
        "bob",
        ("blue", "black"),
        duration=Duration.UNTIL_END_OF_TURN,
        source_name="a test grant",
    )
    bob = scenario.player("bob")
    thoughtseize = scenario.find("Thoughtseize", Zone.HAND, "alice")
    spike = scenario.find("Lava Spike", Zone.HAND, "alice")
    assert "hexproof from black" in scenario.game.hexproof_refusal(bob, "alice", thoughtseize)
    assert scenario.game.hexproof_refusal(bob, "alice", spike) is None


def test_the_same_grant_twice_is_redundant():
    """CR 702.11h: two instances of the same hexproof ability do nothing more
    than one."""
    scenario = _grant_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for _ in range(2):
        scenario.game.grant_player_hexproof(
            "bob", ("black",), duration=Duration.UNTIL_END_OF_TURN, source_name="grant"
        )
    bob = scenario.player("bob")
    thoughtseize = scenario.find("Thoughtseize", Zone.HAND, "alice")
    assert scenario.game.player_hexproof(bob) == (False, ["black"])
    assert "hexproof from black" in scenario.game.hexproof_refusal(bob, "alice", thoughtseize)


def test_an_until_end_of_turn_grant_ends_in_cleanup():
    """CR 514.2."""
    scenario = _grant_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.grant_player_hexproof(
        "alice", (), duration=Duration.UNTIL_END_OF_TURN, source_name="grant"
    )
    scenario.game.grant_player_shroud(
        "alice", duration=Duration.UNTIL_END_OF_TURN, source_name="grant"
    )
    alice = scenario.player("alice")
    assert scenario.game.shroud_refusal(alice) is not None

    scenario.game.cleanup_step()

    assert alice.targeting_grants == []
    assert scenario.game.shroud_refusal(alice) is None


def test_an_effect_granted_shroud_refuses_the_players_own_spell():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.grant_player_shroud(
        "alice", duration=Duration.UNTIL_END_OF_TURN, source_name="grant"
    )
    casting = scenario.cast("Lightning Bolt", username="alice")
    with pytest.raises(ValueError, match="alice has shroud"):
        casting.choose_targets(["alice"])


def test_player_grants_round_trip():
    scenario = _grant_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.grant_player_hexproof(
        "alice",
        ("black",),
        duration=Duration.UNTIL_YOUR_NEXT_TURN,
        source_name="grant",
    )
    decoded = Game.model_validate(scenario.game.model_dump())
    (grant,) = decoded.player("alice").targeting_grants
    assert grant.keyword == "hexproof"
    assert grant.quality == "black"
    assert grant.duration is Duration.UNTIL_YOUR_NEXT_TURN
    assert grant.until_next_turn_of == "alice"


# -- The player-subject clause parser -------------------------------------


def test_the_clause_parser_reads_hexproof_from_two_qualities_on_you():
    """Veil of Summer's real sentence with its subject narrowed to "You" -
    exactly the split flow 1 makes ("You and permanents you control") - reads
    as two CR 702.11f abilities with an "until end of turn" duration."""
    veil = card("Veil of Summer")
    (sentence,) = [s for s in veil.oracle_text.split(". ") if "hexproof" in s]
    clause = sentence.replace("You and permanents you control", "You")
    assert clause.startswith("You gain hexproof from blue and from black")

    effect = parse_clause_effect(clause)
    assert effect is not None

    scenario = _grant_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    effect(scenario.game, alice, "Veil of Summer", None)
    assert sorted(g.quality for g in alice.targeting_grants) == ["black", "blue"]
    assert all(g.duration is Duration.UNTIL_END_OF_TURN for g in alice.targeting_grants)


def test_a_subject_less_gains_hexproof_is_not_read_as_the_players():
    """Blossoming Defense's "... and gains hexproof until end of turn" is the
    creature's grant: its cut-off second clause must not be retried as "you
    gains hexproof" and handed to the caster."""
    assert parse_clause_effect("you gains hexproof until end of turn") is None
