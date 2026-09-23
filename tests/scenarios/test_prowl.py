"""Prowl: an alternative cost unlocked by combat damage this turn (CR 702.76).

Read whole in this session with `mise run rules:find 702.76` (rules effective
September 25, 2026):

- **CR 702.76a** - "Prowl is a static ability that functions on the stack.
  'Prowl [cost]' means 'You may pay [cost] rather than pay this spell's mana
  cost if a player was dealt combat damage this turn by a source that, at the
  time it dealt that damage, was under your control and had any of this
  spell's creature types.' Casting a spell for its prowl cost follows the rules
  for paying alternative costs in rules 601.2b and 601.2f-h."

Every limit in that sentence is a corner case below: combat damage (not a
blocked creature's damage to a creature, not prevented damage), to a player,
this turn, a source under *your* control, and one of *this spell's* creature
types - all "at the time it dealt that damage", so a Rogue that died since
still counts (last known information) and a changeling counts as a Rogue
(CR 702.73a). `Game.combat_damage_to_players_this_turn` is the record
`machines/combat._deal_combat_damage` writes.

Morsel Theft (Kindred Sorcery - Rogue, Modern-legal) is the proof; Thieves'
Fortune (Kindred Instant - Rogue, off-pool, Modern-legal, a different
resolution entirely) proves the option is read off the keyword, not the card.
"""

import pytest
from scripts.sweep_pool import ignored_keywords

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import keyword_cast_options
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from magic_cards_model.models.game import Game
from magic_cards_model.models.mana import ManaCost
from tests.cards import card
from tests.scenarios.harness import PlayedScenario, Scenario

THEFT = "Morsel Theft"
FORTUNE = "Thieves' Fortune"
ROGUE = "Merfolk Looter"  # Creature - Merfolk Rogue, 1/1


def board(*alice: str, bob: tuple[str, ...] = (), hand=(THEFT,)) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[*alice, "Swamp", "Swamp", "Swamp", "Swamp", "Island"],
            hand=list(hand),
            library=["Island"] * 6,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 6)
        .build()
    )
    for name in alice:
        state = scenario.find(name, Zone.BATTLEFIELD, "alice")
        state.summoning_sick = False
    return scenario


def hit_bob_with(scenario: PlayedScenario, *attackers) -> None:
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*attackers)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.start_at(Step.POSTCOMBAT_MAIN)


def prowl_cast(scenario: PlayedScenario, count: int = 2):
    casting = scenario.cast(THEFT)
    casting.use_keyword("Prowl")
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Swamp"] * count))
    return casting


# -- the option itself -------------------------------------------------------


def test_prowl_hands_out_an_alternative_cost_from_hand():
    (option,) = [o for o in keyword_cast_options(card(THEFT)) if o.keyword == "Prowl"]
    assert option.zone is Zone.HAND
    assert option.rule == "CR 702.76a"
    assert not option.pays_mana_cost
    assert option.cost is not None and option.cost.mana == ManaCost.parse("{1}{B}")


def test_prowl_is_no_longer_an_ignored_keyword():
    assert "Prowl" not in ignored_keywords(card(THEFT))
    assert "Prowl" not in ignored_keywords(card(FORTUNE))


# -- available -----------------------------------------------------------------


def test_after_a_rogue_dealt_combat_damage_to_a_player_prowl_is_paid_and_draws():
    scenario = board(ROGUE)
    hit_bob_with(scenario, scenario.creature(ROGUE))
    assert scenario.player("bob").life == 19

    casting = prowl_cast(scenario)
    assert casting.total_cost.mana == ManaCost.parse("{1}{B}")
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.player("bob").life == 16
    assert scenario.player("alice").life == 23
    # The prowl cost was paid: "draw a card" happened.
    assert len(scenario.player("alice").hand) == 1
    assert scenario.find(THEFT, Zone.GRAVEYARD, "alice")


def test_cast_for_its_mana_cost_it_does_not_draw():
    scenario = board(ROGUE)
    hit_bob_with(scenario, scenario.creature(ROGUE))

    casting = scenario.cast(THEFT, targets=["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.player("bob").life == 16
    assert scenario.player("alice").life == 23
    assert scenario.player("alice").hand == []


def test_a_rogue_that_died_after_dealing_the_damage_still_enables_prowl():
    """Last known information: "at the time it dealt that damage"."""
    scenario = board(ROGUE)
    looter = scenario.creature(ROGUE)
    hit_bob_with(scenario, looter)
    scenario.game.put_into_graveyard(looter)
    assert looter.zone is Zone.GRAVEYARD

    scenario.put_on_stack(prowl_cast(scenario))
    scenario.resolve_top()
    assert len(scenario.player("alice").hand) == 1


def test_a_changeling_that_dealt_combat_damage_is_a_rogue():
    """CR 702.73a: Changeling Outcast is every creature type."""
    scenario = board("Changeling Outcast")
    hit_bob_with(scenario, scenario.creature("Changeling Outcast"))

    scenario.put_on_stack(prowl_cast(scenario))
    scenario.resolve_top()
    assert len(scenario.player("alice").hand) == 1


def test_the_record_holds_controller_and_creature_types_at_the_time():
    scenario = board(ROGUE)
    looter = scenario.creature(ROGUE)
    hit_bob_with(scenario, looter)

    (record,) = scenario.game.combat_damage_to_players_this_turn
    assert record.player == "bob"
    assert record.controller == "alice"
    assert record.source_id == looter.id
    assert set(record.creature_types) == {"Merfolk", "Rogue"}


# -- refused -------------------------------------------------------------------


def test_refused_before_combat():
    scenario = board(ROGUE)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast(THEFT)
    with pytest.raises(ValueError, match=r"702\.76a"):
        casting.use_keyword("Prowl")


def test_refused_after_a_non_rogue_dealt_the_damage():
    scenario = board("Grizzly Bears")
    hit_bob_with(scenario, scenario.creature("Grizzly Bears"))
    assert scenario.player("bob").life == 18

    casting = scenario.cast(THEFT)
    with pytest.raises(ValueError, match=r"702\.76a"):
        casting.use_keyword("Prowl")


def test_refused_when_the_rogue_was_blocked_and_hit_only_a_creature():
    scenario = board(ROGUE, bob=("Grizzly Bears",))
    looter = scenario.creature(ROGUE)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(looter)
    scenario.block(looter, scenario.creature("Grizzly Bears", "bob"))
    scenario.combat_damage()
    scenario.start_at(Step.POSTCOMBAT_MAIN)

    casting = scenario.cast(THEFT)
    with pytest.raises(ValueError, match=r"702\.76a"):
        casting.use_keyword("Prowl")


def test_prevented_damage_does_not_enable_prowl():
    scenario = board(ROGUE, "Forest", hand=(THEFT, "Fog"))
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_and_resolve("Fog", forest)
    hit_bob_with(scenario, scenario.creature(ROGUE))
    assert scenario.player("bob").life == 20
    assert scenario.game.combat_damage_to_players_this_turn == []

    casting = scenario.cast(THEFT)
    with pytest.raises(ValueError, match=r"702\.76a"):
        casting.use_keyword("Prowl")


def _bobs_rogue_hits_alice(hand: tuple[str, ...]) -> PlayedScenario:
    scenario = board(bob=(ROGUE,), hand=hand)
    while scenario.turn.active_player != "bob":
        scenario.advance()
    scenario.creature(ROGUE, "bob").summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature(ROGUE, "bob"))
    scenario.no_blocks()
    scenario.combat_damage()
    assert scenario.player("alice").life == 19
    return scenario


def test_refused_when_an_opponents_rogue_dealt_the_damage():
    """ "Under **your** control": bob's Rogue hitting alice unlocks nothing for
    alice. Morsel Theft is a sorcery, so the option is asked directly on bob's
    turn - the prowl half is what refuses it."""
    scenario = _bobs_rogue_hits_alice((THEFT,))
    theft = scenario.find(THEFT, Zone.HAND, "alice")
    (option,) = [o for o in keyword_cast_options(theft.card) if o.keyword == "Prowl"]

    reason = option.why_not(theft, "alice", scenario.game)
    assert reason is not None and "702.76a" in reason
    # ...while bob, the Rogue's controller, would have been allowed.
    assert option.why_not(theft, "bob", scenario.game) is None


def test_an_opponents_rogue_does_not_enable_an_instant_either():
    """Thieves' Fortune (off-pool) is an instant, so alice can really try."""
    scenario = _bobs_rogue_hits_alice((FORTUNE,))
    scenario.pass_priority("bob")
    assert scenario.priority_holder == "alice"

    casting = scenario.cast(FORTUNE, username="alice")
    with pytest.raises(ValueError, match=r"702\.76a"):
        casting.use_keyword("Prowl")


def test_thieves_fortune_prowl_off_pool_generality():
    scenario = board(ROGUE, hand=(FORTUNE,))
    hit_bob_with(scenario, scenario.creature(ROGUE))

    casting = scenario.cast(FORTUNE)
    casting.use_keyword("Prowl")
    assert casting.total_cost.mana == ManaCost.parse("{U}")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Island"))
    spell = scenario.put_on_stack(casting)
    assert scenario.game.was_cast_with(spell, "Prowl")


def _prowl_casts(scenario: PlayedScenario) -> list:
    return [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.kind is ActionKind.CAST and action.keyword == "Prowl"
    ]


def test_legal_actions_offer_prowl_only_once_the_condition_holds():
    scenario = board(ROGUE)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert _prowl_casts(scenario) == []

    hit_bob_with(scenario, scenario.creature(ROGUE))
    assert len(_prowl_casts(scenario)) == 1


# -- per-turn, serialised ------------------------------------------------------


def test_the_record_is_cleared_when_the_turn_ends():
    scenario = board(ROGUE)
    hit_bob_with(scenario, scenario.creature(ROGUE))
    assert scenario.game.combat_damage_to_players_this_turn

    while scenario.turn.active_player == "alice":
        scenario.advance()
    assert scenario.game.combat_damage_to_players_this_turn == []


def test_the_record_round_trips_and_still_enables_prowl():
    scenario = board(ROGUE)
    hit_bob_with(scenario, scenario.creature(ROGUE))

    decoded = PlayedScenario(Game.model_validate(scenario.game.model_dump(mode="json")))
    assert (
        decoded.game.combat_damage_to_players_this_turn
        == scenario.game.combat_damage_to_players_this_turn
    )
    decoded.put_on_stack(prowl_cast(decoded))
    decoded.resolve_top()
    assert len(decoded.player("alice").hand) == 1
