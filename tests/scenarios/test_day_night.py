"""Scenario: day and night (CR 731) - the game's own designation, the untap
step's turn-based check that flips it, "If it's neither day nor night, it
becomes day as this creature enters", and "Whenever day becomes night or
night becomes day".

Gavony Dawnguard is the listed card: "Ward {1} / If it's neither day nor
night, it becomes day as this creature enters. / Whenever day becomes night
or night becomes day, look at the top four cards of your library. You may
reveal a creature card with mana value 3 or less from among them and put it
into your hand. Put the rest on the bottom of your library in any order."

Brimstone Vandal is the second printing (Modern, Pioneer; not in any api
deck): the same "neither day nor night" static and the same trigger
condition, with a different effect ("this creature deals 1 damage to each
opponent") - so the condition reader is proven apart from Dawnguard's dig.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 731.1** - "The game starts with neither designation ... Once it has
  become day or night, the game will have exactly one of those designations
  from that point forward."
- **CR 731.1a** - "'day becomes night' and 'night becomes day' refer to the
  game losing the first designation and gaining the second one" - so
  neither-to-day is not "night becomes day" and triggers nothing.
- **CR 731.2 / CR 502.2** - the untap step's second turn-based action checks
  the previous turn: day and the previous turn's active player cast no spells
  (CR 731.2a) makes it night; night and that player cast two or more
  (CR 731.2b) makes it day; neither is not checked at all (CR 731.2c).
- **CR 614.10** - a skipped untap step does not happen, so its day/night
  check does not either.
- **CR 702.21a** - ward counters a spell an opponent aims at it unless that
  player pays the cost.
- **CR 608.2d** - the "may reveal" choice is the controller's, and a card
  that fails "creature card with mana value 3 or less" is an illegal choice.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import CardSplit, DecisionKind, ScriptedAnswer
from magic_cards_model.models import Zone
from magic_cards_model.models.game import DayNight, Game
from tests.scenarios.harness import PlayedScenario, Scenario

DAWNGUARD = "Gavony Dawnguard"
VANDAL = "Brimstone Vandal"


def _resolve_everything(scenario: PlayedScenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.stack_names():
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def _to_next_upkeep(scenario: PlayedScenario) -> None:
    """Walk the turn forward, turn-based actions and all, to the next turn's
    upkeep - past CR 502.2's check in that turn's untap step."""
    taken = scenario.game.turn.turns_taken
    while not (scenario.step is Step.UPKEEP and scenario.game.turn.turns_taken != taken):
        if scenario.game.step_grants_priority and (
            scenario.stack_names() or scenario.game.pending_triggers
        ):
            _resolve_everything(scenario)
            continue
        scenario.advance()


def _script_dig(scenario: PlayedScenario, *, username: str, taken) -> None:
    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.SCRY, value=CardSplit(moved=tuple(taken)), player=username)
    )


def _board(*, alice_battlefield=(), alice_hand=(), alice_library=None, bob_hand=()):
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Plains", "Plains", "Plains", "Mountain", *alice_battlefield],
            hand=list(alice_hand),
            library=list(alice_library or ["Plains"] * 12),
        )
        .player(
            "bob",
            battlefield=["Mountain", "Mountain"],
            hand=list(bob_hand),
            library=["Mountain"] * 12,
        )
        .build()
    )


# -- the designation itself (CR 731.1, CR 731.2c) ------------------------------


def test_a_game_starts_neither_day_nor_night():
    scenario = _board()
    assert scenario.game.day_night is None


def test_neither_is_never_checked_so_a_spell_less_turn_leaves_it_neither():
    """CR 731.2c: with neither designation the untap check does not happen."""
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _to_next_upkeep(scenario)
    _to_next_upkeep(scenario)
    assert scenario.game.day_night is None


def test_casting_dawnguard_makes_it_day_as_it_enters():
    scenario = _board(alice_hand=[DAWNGUARD])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(DAWNGUARD, *scenario.untapped_sources("Plains", "Plains", "Plains"))
    assert scenario.game.day_night is DayNight.DAY


def test_becoming_day_from_neither_is_not_night_becoming_day():
    """CR 731.1a: neither-to-day loses no designation, so Dawnguard's own
    trigger does not fire as it makes it day."""
    scenario = _board(alice_hand=[DAWNGUARD])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(DAWNGUARD, *scenario.untapped_sources("Plains", "Plains", "Plains"))
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []
    assert scenario.player("alice").hand == []


def test_put_onto_the_battlefield_without_casting_still_makes_it_day():
    """The static is an "as this creature enters" one, not a cast trigger."""
    scenario = _board(alice_hand=[DAWNGUARD])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield(DAWNGUARD, "alice")
    assert scenario.game.day_night is DayNight.DAY


def test_dawnguard_entering_at_night_leaves_it_night():
    scenario = _board(alice_hand=[DAWNGUARD])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.become_night()
    scenario.put_onto_battlefield(DAWNGUARD, "alice")
    assert scenario.game.day_night is DayNight.NIGHT


def test_a_second_dawnguard_entering_by_day_changes_nothing():
    scenario = _board(alice_hand=[DAWNGUARD, DAWNGUARD])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield(DAWNGUARD, "alice")
    scenario.put_onto_battlefield(DAWNGUARD, "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.game.day_night is DayNight.DAY
    assert scenario.stack_names() == []


# -- the untap step's check (CR 502.2, CR 731.2a, CR 731.2b) ---------------------


def test_day_becomes_night_when_the_previous_active_player_cast_no_spells():
    scenario = _board(alice_hand=[DAWNGUARD])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield(DAWNGUARD, "alice")  # no spell cast this turn
    _to_next_upkeep(scenario)
    assert scenario.game.turn.active_player == "bob"
    assert scenario.game.day_night is DayNight.NIGHT


def test_day_stays_day_when_the_previous_active_player_cast_one_spell():
    scenario = _board(alice_hand=[DAWNGUARD])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(DAWNGUARD, *scenario.untapped_sources("Plains", "Plains", "Plains"))
    _to_next_upkeep(scenario)
    assert scenario.game.day_night is DayNight.DAY


def test_only_the_previous_active_players_own_spells_count():
    """CR 731.2a names "the previous turn's active player": bob's instant cast
    during alice's turn does not keep it day."""
    scenario = _board(alice_hand=[DAWNGUARD], bob_hand=["Shock"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield(DAWNGUARD, "alice")
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Shock",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=["alice"],
    )
    _to_next_upkeep(scenario)
    assert scenario.game.day_night is DayNight.NIGHT


def test_night_becomes_day_when_the_previous_active_player_cast_two_spells():
    scenario = _board(alice_hand=["Memnite", "Ornithopter"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.become_night()
    scenario.cast_and_resolve("Memnite")
    scenario.cast_and_resolve("Ornithopter")
    _to_next_upkeep(scenario)
    assert scenario.game.day_night is DayNight.DAY


def test_night_stays_night_after_only_one_spell():
    scenario = _board(alice_hand=["Memnite"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.become_night()
    scenario.cast_and_resolve("Memnite")
    _to_next_upkeep(scenario)
    assert scenario.game.day_night is DayNight.NIGHT


def test_night_ignores_two_spells_cast_by_the_non_active_player():
    scenario = _board(bob_hand=["Shock", "Shock"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.become_night()
    for mountain in scenario.untapped_sources("Mountain", "Mountain", username="bob"):
        scenario.pass_priority("alice")
        scenario.cast_and_resolve("Shock", mountain, username="bob", targets=["alice"])
    _to_next_upkeep(scenario)
    assert scenario.game.day_night is DayNight.NIGHT


def test_once_set_it_never_returns_to_neither():
    """CR 731.1: night, then day again - never neither - across several turns."""
    scenario = _board(alice_hand=[DAWNGUARD])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield(DAWNGUARD, "alice")
    seen = []
    for _ in range(4):
        _to_next_upkeep(scenario)
        _resolve_everything(scenario)
        seen.append(scenario.game.day_night)
    assert None not in seen
    assert seen[0] is DayNight.NIGHT


def test_a_skipped_untap_step_skips_the_day_night_check():
    """CR 614.10: the skipped step does not happen, so neither does CR 502.2."""
    scenario = _board(alice_hand=[DAWNGUARD])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield(DAWNGUARD, "alice")
    scenario.game.players_skipping_next_untap["bob"] = 1
    _to_next_upkeep(scenario)
    assert scenario.game.turn.active_player == "bob"
    assert scenario.game.day_night is DayNight.DAY


def test_the_designation_survives_a_round_trip():
    scenario = _board(alice_hand=[DAWNGUARD])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield(DAWNGUARD, "alice")
    _to_next_upkeep(scenario)
    decoded = Game.model_validate(scenario.game.model_dump(mode="json"))
    assert decoded.day_night is DayNight.NIGHT
    assert decoded.previous_turn_active_player == "alice"


# -- Dawnguard's trigger ---------------------------------------------------------


def test_day_becoming_night_digs_a_small_creature_into_hand():
    scenario = _board(
        alice_hand=[DAWNGUARD],
        alice_library=["Craw Wurm", "Grizzly Bears", "Plains", "Savannah Lions", *["Plains"] * 8],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    scenario.put_onto_battlefield(DAWNGUARD, "alice")
    wurm, bears, plains, lions = alice.library[:4]
    fifth = alice.library[4]
    _script_dig(scenario, username="alice", taken=[bears.id])

    _to_next_upkeep(scenario)
    assert scenario.game.day_night is DayNight.NIGHT
    _resolve_everything(scenario)

    assert bears.zone is Zone.HAND
    assert alice.library[0] is fifth
    assert {c.id for c in alice.library[-3:]} == {wurm.id, plains.id, lions.id}


def test_night_becoming_day_triggers_it_too():
    scenario = _board(
        alice_hand=["Memnite", "Ornithopter"],
        alice_battlefield=[DAWNGUARD],
        alice_library=["Grizzly Bears", *["Plains"] * 11],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.become_night()
    bears = scenario.player("alice").library[0]
    scenario.cast_and_resolve("Memnite")
    scenario.cast_and_resolve("Ornithopter")
    _script_dig(scenario, username="alice", taken=[bears.id])

    _to_next_upkeep(scenario)
    assert scenario.game.day_night is DayNight.DAY
    _resolve_everything(scenario)
    assert bears.zone is Zone.HAND


def test_declining_the_reveal_puts_all_four_on_the_bottom():
    scenario = _board(
        alice_hand=[DAWNGUARD],
        alice_library=["Grizzly Bears", "Plains", "Plains", "Plains", "Mountain", *["Plains"] * 7],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    scenario.put_onto_battlefield(DAWNGUARD, "alice")
    top_four = alice.library[:4]
    fifth = alice.library[4]

    _to_next_upkeep(scenario)
    _resolve_everything(scenario)

    assert alice.hand == []
    assert alice.library[0] is fifth
    assert {c.id for c in alice.library[-4:]} == {c.id for c in top_four}


def test_a_creature_with_mana_value_four_is_an_illegal_choice():
    scenario = _board(
        alice_hand=[DAWNGUARD],
        alice_library=["Hill Giant", "Plains", "Plains", "Plains", *["Plains"] * 8],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield(DAWNGUARD, "alice")
    giant = scenario.player("alice").library[0]
    _script_dig(scenario, username="alice", taken=[giant.id])

    _to_next_upkeep(scenario)
    scenario.game.put_triggers_on_stack()
    with pytest.raises(ValueError, match="CR 608.2d"):
        scenario.pass_until_resolved()


def test_the_trigger_belongs_to_dawnguards_controller_on_the_other_players_turn():
    """It becomes night in bob's untap step; alice's Dawnguard still digs
    alice's library, not the active player's."""
    scenario = _board(
        alice_hand=[DAWNGUARD],
        alice_library=["Savannah Lions", *["Plains"] * 11],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield(DAWNGUARD, "alice")
    lions = scenario.player("alice").library[0]
    _script_dig(scenario, username="alice", taken=[lions.id])

    _to_next_upkeep(scenario)
    assert scenario.game.turn.active_player == "bob"
    _resolve_everything(scenario)
    assert lions.zone is Zone.HAND
    assert lions in scenario.player("alice").hand


def test_no_change_no_trigger():
    scenario = _board(alice_hand=[DAWNGUARD])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(DAWNGUARD, *scenario.untapped_sources("Plains", "Plains", "Plains"))
    _to_next_upkeep(scenario)
    scenario.game.put_triggers_on_stack()
    assert scenario.game.day_night is DayNight.DAY
    assert scenario.stack_names() == []


def test_ward_one_still_counters_an_unpaid_opponents_spell():
    scenario = _board(alice_battlefield=[DAWNGUARD], bob_hand=["Shock"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dawnguard = scenario.creature(DAWNGUARD, "alice")
    bob_mountains = scenario.untapped_sources("Mountain", "Mountain", username="bob")
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Shock", bob_mountains[0], username="bob", targets=[dawnguard])
    scenario.game.put_triggers_on_stack()
    assert any("Gavony Dawnguard" in name for name in scenario.stack_names())
    scenario.will_pay_the_mana_cost(False)  # bob declines ward's {1}
    _resolve_everything(scenario)
    assert dawnguard.damage == 0
    assert scenario.find("Shock", Zone.GRAVEYARD, "bob").zone is Zone.GRAVEYARD


# -- Brimstone Vandal: the same two readers on another printing ------------------


def test_vandal_makes_it_day_as_it_enters():
    scenario = _board(alice_hand=[VANDAL])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(VANDAL, *scenario.untapped_sources("Mountain", "Plains", "Plains"))
    assert scenario.game.day_night is DayNight.DAY


def test_vandal_pings_each_opponent_when_day_becomes_night():
    scenario = _board(alice_hand=[VANDAL])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield(VANDAL, "alice")
    alice_life = scenario.player("alice").life
    bob_life = scenario.player("bob").life

    _to_next_upkeep(scenario)
    _resolve_everything(scenario)

    assert scenario.game.day_night is DayNight.NIGHT
    assert scenario.player("bob").life == bob_life - 1
    assert scenario.player("alice").life == alice_life


def test_vandal_and_dawnguard_both_trigger_on_one_change():
    scenario = _board(
        alice_hand=[VANDAL, DAWNGUARD],
        alice_library=["Savannah Lions", *["Plains"] * 11],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield(VANDAL, "alice")
    scenario.put_onto_battlefield(DAWNGUARD, "alice")
    lions = scenario.player("alice").library[0]
    _script_dig(scenario, username="alice", taken=[lions.id])
    bob_life = scenario.player("bob").life

    _to_next_upkeep(scenario)
    _resolve_everything(scenario)

    assert scenario.player("bob").life == bob_life - 1
    assert lions.zone is Zone.HAND


# -- the dig's "creature card with mana value 3 or less" on another printing -------


def test_recruitment_officer_reveals_a_creature_with_mana_value_three_or_less():
    """Recruitment Officer's {3}{W}: "Look at the top four cards of your
    library. You may reveal a creature card with mana value 3 or less from
    among them and put it into your hand. Put the rest on the bottom of your
    library in a random order." - the same bounded reveal as Dawnguard's
    trigger, with the random-order tail and on an activated ability."""
    scenario = _board(
        alice_battlefield=["Recruitment Officer"],
        alice_library=["Craw Wurm", "Savannah Lions", "Plains", "Plains", "Mountain"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    officer = scenario.creature("Recruitment Officer", "alice")
    wurm, lions, plains_a, plains_b, mountain = alice.library[:5]
    _script_dig(scenario, username="alice", taken=[lions.id])

    scenario.activate(officer, *scenario.untapped_sources("Plains", "Plains", "Plains", "Mountain"))
    scenario.resolve_top()

    assert lions.zone is Zone.HAND
    assert alice.library[0] is mountain
    assert {c.id for c in alice.library[1:]} == {wurm.id, plains_a.id, plains_b.id}


def test_recruitment_officer_refuses_a_creature_with_mana_value_six():
    scenario = _board(
        alice_battlefield=["Recruitment Officer"],
        alice_library=["Craw Wurm", "Savannah Lions", "Plains", "Plains", "Mountain"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    officer = scenario.creature("Recruitment Officer", "alice")
    wurm = scenario.player("alice").library[0]
    _script_dig(scenario, username="alice", taken=[wurm.id])

    scenario.activate(officer, *scenario.untapped_sources("Plains", "Plains", "Plains", "Mountain"))
    with pytest.raises(ValueError, match="CR 608.2d"):
        scenario.resolve_top()
