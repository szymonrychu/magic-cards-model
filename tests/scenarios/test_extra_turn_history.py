"""Scenario: "haven't begun an extra turn this game" (H.M.S. Bounty,
Unlikely Timeship).

"Whenever H.M.S. Bounty deals combat damage to a player, draw a card. If you
control a Whale and haven't begun an extra turn this game, take an extra turn
after this one." CR 500.7 adds the extra turn directly after this one; the
game record is the player's extra turns *begun* (`TurnMachine.
extra_turns_begun_by`), not merely granted - a second hit before the first
extra turn begins still finds none begun. No other legal printing reads this
history (Scryfall, in the writing session).

CR rules cited here were looked up with `mise run rules:find` in the writing
session: 500.7, 510.2 (combat damage), 722 (station: stationed to 8+ it is a
creature with flying).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import Scenario

BOUNTY = "H.M.S. Bounty, Unlikely Timeship"


def board(*, whale: bool = True) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=[BOUNTY] + (["Pursued Whale"] if whale else []),
            library=["Island"] * 10,
        )
        .player("bob", library=["Island"] * 10)
    )


def stationed(scenario):
    bounty = scenario.find(BOUNTY, Zone.BATTLEFIELD, "alice")
    scenario.game.add_counters(bounty, Counter.CHARGE, 8, putter="alice")
    assert scenario.game.characteristics_of(bounty).is_creature
    return bounty


def hit(scenario, bounty):
    while scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
    scenario.attack_with(bounty)
    while scenario.step is not Step.DECLARE_BLOCKERS:
        scenario.advance()
    scenario.no_blocks()
    scenario.combat_damage()
    assert scenario.stack_names() == [f"{BOUNTY}'s triggered ability"]
    scenario.pass_until_resolved()


def test_the_first_hit_with_a_whale_takes_an_extra_turn():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bounty = stationed(scenario)
    hand = len(scenario.player("alice").hand)
    hit(scenario, bounty)
    assert len(scenario.player("alice").hand) == hand + 1
    assert scenario.turn.extra_turns == ["alice"]


def test_without_a_whale_there_is_no_extra_turn():
    scenario = board(whale=False).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bounty = stationed(scenario)
    hit(scenario, bounty)
    assert scenario.turn.extra_turns == []


def test_after_beginning_an_extra_turn_there_is_no_second_one():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bounty = stationed(scenario)
    hit(scenario, bounty)
    while not scenario.turn.taking_extra_turn:
        scenario.advance()
    assert scenario.turn.active_player == "alice"
    assert scenario.turn.extra_turns_begun_by == {"alice": 1}
    hit(scenario, bounty)
    assert scenario.turn.extra_turns == []


def test_an_extra_turn_granted_but_not_yet_begun_is_not_begun():
    """After the first hit the extra turn is only queued (CR 500.7): the
    condition reads extra turns begun, of which there are still none."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bounty = stationed(scenario)
    hit(scenario, bounty)
    assert scenario.turn.extra_turns == ["alice"]
    assert scenario.game.condition_holds("alice", "you haven't begun an extra turn this game")
    assert not scenario.game.condition_holds("alice", "you've begun an extra turn this game")


def test_h_m_s_bounty_unlikely_timeship_finds_a_whale_as_it_enters():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[BOUNTY],
            battlefield=["Island"] * 5,
            library=["Island", "Pursued Whale", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    whale = scenario.find("Pursued Whale", Zone.LIBRARY, "alice")
    scenario.will_take_the_may(True)
    scenario.will_choose_cards(whale)
    scenario.cast_and_resolve(BOUNTY, *scenario.untapped_sources(*["Island"] * 5))
    scenario.pass_until_resolved()
    assert whale.zone is Zone.HAND
