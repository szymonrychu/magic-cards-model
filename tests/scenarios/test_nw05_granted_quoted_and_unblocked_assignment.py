"""Granted quoted abilities on a put permanent, and unblocked damage
assignment (NW-05, T4).

- Terminal Velocity: "You may put an artifact or creature card from your hand
  onto the battlefield. That permanent gains haste, "When this permanent
  leaves the battlefield, it deals damage equal to its mana value to each
  creature," and "At the beginning of your end step, sacrifice this
  permanent."" - the object the first instruction put is the one that gains
  the abilities (CR 608.2c, CR 400.7j), quoted abilities are granted text
  (CR 113.10), and the leaves-the-battlefield trigger looks back in time
  (CR 603.10a) to the permanent's last-known mana value.

CR numbers checked with `mise run rules:find` (rules effective 2026-09-25).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario

TERMINAL_VELOCITY = "Terminal Velocity"


def _board(*, hand=("Hill Giant",), bob_battlefield=("Grizzly Bears",), bob_hand=(), mountains=6):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[TERMINAL_VELOCITY, *hand],
            battlefield=["Mountain"] * mountains,
        )
        .player("bob", battlefield=list(bob_battlefield), hand=list(bob_hand))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_velocity(scenario, *, put=None):
    if put is not None:
        scenario.will_choose_cards(put, username="alice")
    scenario.cast_onto_stack(TERMINAL_VELOCITY, auto=True)
    scenario.resolve_top()


def test_terminal_velocity_reads_every_clause():
    bad = [c for c in card_support(card(TERMINAL_VELOCITY)).clauses if c.outcome != "handled"]
    assert not bad, bad


def test_the_put_creature_gains_haste_and_both_quoted_abilities():
    scenario = _board()
    giant = scenario.find("Hill Giant", Zone.HAND, "alice")
    _cast_velocity(scenario, put=giant)
    assert giant.zone is Zone.BATTLEFIELD
    assert has_keyword(giant, "haste", scenario.game)
    assert len(giant.granted_ability_texts) == 3


def test_a_creature_that_enters_later_is_untouched():
    scenario = _board(hand=("Hill Giant", "Grizzly Bears"))
    giant = scenario.find("Hill Giant", Zone.HAND, "alice")
    _cast_velocity(scenario, put=giant)
    scenario.game.put_onto_battlefield(
        scenario.find("Grizzly Bears", Zone.HAND, "alice"), "alice"
    )
    bears = [s for s in scenario.game.battlefield if s.name == "Grizzly Bears" and s.controller == "alice"]
    assert bears and not bears[0].granted_ability_texts


def test_at_the_end_step_it_is_sacrificed_and_its_last_known_mana_value_hits_every_creature():
    scenario = _board()
    giant = scenario.find("Hill Giant", Zone.HAND, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_velocity(scenario, put=giant)
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.pass_until_resolved()  # the sacrifice trigger
    scenario.pass_until_resolved()  # the leaves-the-battlefield trigger
    assert giant.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD, "3 damage (Hill Giant's mana value) kills a 2/2"


def test_an_artifact_is_put_too_and_deals_damage_equal_to_its_own_mana_value():
    scenario = _board(hand=("Mind Stone",), bob_battlefield=("Hill Giant",))
    stone = scenario.find("Mind Stone", Zone.HAND, "alice")
    giant = scenario.creature("Hill Giant", "bob")
    _cast_velocity(scenario, put=stone)
    assert stone.zone is Zone.BATTLEFIELD
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert stone.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.BATTLEFIELD
    assert giant.damage == 2, "Mind Stone's mana value is 2, not Hill Giant's 3"


def test_declining_the_may_puts_nothing_and_grants_nothing():
    scenario = _board()
    scenario.will_take_the_may(False, username="alice")
    scenario.cast_onto_stack(TERMINAL_VELOCITY, auto=True)
    scenario.resolve_top()
    giant = scenario.find("Hill Giant", Zone.HAND, "alice")
    assert giant.zone is Zone.HAND


def test_only_artifact_and_creature_cards_are_offered():
    scenario = _board(hand=("Forest", "Lightning Bolt"))
    scenario.cast_onto_stack(TERMINAL_VELOCITY, auto=True)
    scenario.resolve_top()
    assert scenario.find("Forest", Zone.HAND, "alice").zone is Zone.HAND
    assert scenario.find("Lightning Bolt", Zone.HAND, "alice").zone is Zone.HAND


def test_it_dying_early_still_pays_out_its_last_known_mana_value():
    """The leaves trigger is not tied to the end step (CR 603.10a)."""
    scenario = _board(hand=("Hill Giant", "Lightning Bolt"), mountains=7)
    giant = scenario.find("Hill Giant", Zone.HAND, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_velocity(scenario, put=giant)
    scenario.cast_onto_stack("Lightning Bolt", targets=[giant], auto=True)
    scenario.pass_until_resolved()  # the Bolt kills it
    scenario.pass_until_resolved()  # its leaves-the-battlefield trigger
    assert giant.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD




# -- Carnage, Crimson Chaos: the same "It gains "<quoted>" and "<quoted>"" ----
# after a return, on a triggered ability instead of a spell. Proof printing for
# the put-then-gains reader (Scryfall, Modern/Pioneer legal, in no deck list).

CARNAGE = "Carnage, Crimson Chaos"
CARNAGE_GRANTS = (
    "This creature attacks each combat if able",
    "When this creature deals combat damage to a player, sacrifice it.",
)


def _carnage_board(*, graveyard=("Grizzly Bears",)):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[CARNAGE],
            graveyard=list(graveyard),
            battlefield=["Swamp", "Mountain", "Swamp", "Mountain"],
        )
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _enter_carnage(scenario, target):
    scenario.cast_onto_stack(CARNAGE, auto=True)
    scenario.choose_trigger_targets(CARNAGE, [target])
    scenario.resolve_top()  # the creature spell
    scenario.pass_until_resolved()  # the enters trigger


def test_carnage_is_fully_handled():
    bad = [c for c in card_support(card(CARNAGE)).clauses if c.outcome != "handled"]
    assert not bad, bad


def test_the_returned_creature_gains_both_quoted_abilities():
    scenario = _carnage_board()
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    _enter_carnage(scenario, bears)
    assert bears.zone is Zone.BATTLEFIELD
    assert bears.granted_ability_texts == CARNAGE_GRANTS


def test_a_creature_with_mana_value_over_three_is_not_a_legal_target():
    scenario = _carnage_board(graveyard=("Serra Angel",))
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")
    scenario.cast_onto_stack(CARNAGE, auto=True)
    scenario.resolve_top()
    assert angel.zone is Zone.GRAVEYARD


def test_the_granted_trigger_sacrifices_it_after_combat_damage_to_a_player():
    scenario = _carnage_board()
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    _enter_carnage(scenario, bears)
    bears.summoning_sick = False
    while scenario.step is not Step.BEGINNING_OF_COMBAT:
        scenario.advance()
    scenario.advance()  # declare attackers
    scenario.attack_with(bears)
    while scenario.step is not Step.COMBAT_DAMAGE:
        scenario.advance()
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 18
    assert bears.zone is Zone.GRAVEYARD, "sacrificed by its own granted trigger"


# -- Vessel of the All-Consuming: "...if it has dealt 10 or more damage to that
# player this turn, they lose the game." (CR 104.3e's effect-stated loss; the
# "if" is an intervening if, CR 603.4, checked as the trigger fires and again as
# it resolves). "They" is the damaged player. No other legal printing says
# "they lose the game" (Scryfall o: search, 2026-10-07), so the plural subject is
# proven on this card alone and the "that player loses the game" siblings'
# existing tests keep proving the singular.

HIDETSUGU = "Hidetsugu Consumes All // Vessel of the All-Consuming"


def _vessel_board(*, bob_battlefield=()):
    scenario = (
        Scenario()
        .player("alice", hand=[HIDETSUGU], library=["Plains"] * 5)
        .player("bob", battlefield=list(bob_battlefield), library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card = scenario.find(HIDETSUGU, Zone.HAND, "alice")
    vessel = scenario.game.put_onto_battlefield(card, "alice", transformed=True)
    return scenario, vessel


def _hit(scenario, vessel, target, amount):
    scenario.game.deal_damage(target, amount, source=vessel)
    scenario.game.announce_batched_events()
    scenario.pass_until_resolved()  # puts the damage triggers on the stack
    while not scenario.game.stack_is_empty and not scenario.game.is_over:
        scenario.pass_until_resolved()


def test_hidetsugu_reads_every_clause():
    bad = [c for c in card_support(card(HIDETSUGU)).clauses if c.outcome != "handled"]
    assert not bad, bad


def test_ten_damage_to_a_player_in_one_hit_makes_them_lose():
    scenario, vessel = _vessel_board()
    _hit(scenario, vessel, scenario.player("bob"), 10)
    assert scenario.game.is_over
    assert scenario.game.winner == "alice"


def test_nine_damage_is_not_enough_at_trigger_time_or_resolution():
    scenario, vessel = _vessel_board()
    _hit(scenario, vessel, scenario.player("bob"), 9)
    assert not scenario.game.is_over
    assert scenario.player("bob").life == 11


def test_the_ten_damage_adds_up_across_hits_in_the_same_turn():
    scenario, vessel = _vessel_board()
    _hit(scenario, vessel, scenario.player("bob"), 6)
    assert not scenario.game.is_over
    _hit(scenario, vessel, scenario.player("bob"), 4)
    assert scenario.game.is_over


def test_damage_to_a_creature_does_not_count_toward_the_player_total():
    scenario, vessel = _vessel_board(bob_battlefield=("Hill Giant",))
    giant = scenario.creature("Hill Giant", "bob")
    _hit(scenario, vessel, giant, 3)
    _hit(scenario, vessel, scenario.player("bob"), 9)
    assert not scenario.game.is_over
    assert scenario.player("bob").life == 11


def test_the_count_starts_over_each_turn():
    scenario, vessel = _vessel_board()
    _hit(scenario, vessel, scenario.player("bob"), 9)
    for player in ("bob", "alice"):
        while scenario.turn.active_player != player or scenario.step is not Step.PRECOMBAT_MAIN:
            scenario.advance()
    _hit(scenario, vessel, scenario.player("bob"), 1)
    assert not scenario.game.is_over


# -- Predatory Focus: "You may have creatures you control assign their combat
# damage this turn as though they weren't blocked." - the printed permission
# of Rhox and its siblings (CR 510.1b over CR 510.1c), granted to every creature
# its controller has as the spell resolves (CR 611.2c) until end of turn
# (CR 514.2), and still asked of its controller creature by creature (CR 608.2d).
# No other legal printing words it "they weren't blocked" (Scryfall o: search,
# 2026-10-07); Rhox's printed line is the existing-path regression and
# Garruk, Savage Herald's -7 grants the identical quoted line.

PREDATORY_FOCUS = "Predatory Focus"

from magic_cards_model.machines.combat import may_assign_as_though_unblocked  # noqa: E402


def _focus_board(*, alice_creatures=("Grizzly Bears",), bob_creatures=("Hill Giant",)):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[PREDATORY_FOCUS, "Hill Giant"],
            battlefield=["Forest"] * 5 + list(alice_creatures),
        )
        .player("bob", battlefield=list(bob_creatures), life=20, library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack(PREDATORY_FOCUS, auto=True)
    scenario.resolve_top()
    return scenario


def _attack_and_block(scenario, attacker, blocker):
    attacker.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacker)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.block(attacker, blocker)


def test_predatory_focus_reads_every_clause():
    bad = [c for c in card_support(card(PREDATORY_FOCUS)).clauses if c.outcome != "handled"]
    assert not bad, bad


def test_a_blocked_creature_may_assign_all_its_damage_to_the_player():
    scenario = _focus_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    _attack_and_block(scenario, bears, giant)
    scenario.will_take_the_may(True, username="alice", source="Grizzly Bears")
    scenario.combat_damage()
    assert scenario.player("bob").life == 18
    assert giant.damage == 0, "the blocker took none of it"
    assert bears.zone is Zone.GRAVEYARD, "CR 510.1d: the blocker still deals its own damage"


def test_declining_keeps_the_ordinary_blocked_assignment():
    scenario = _focus_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    _attack_and_block(scenario, bears, giant)
    scenario.will_take_the_may(False, username="alice", source="Grizzly Bears")
    scenario.combat_damage()
    assert scenario.player("bob").life == 20
    assert giant.damage == 2


def test_each_creature_is_asked_separately():
    scenario = _focus_board(alice_creatures=("Grizzly Bears", "Hill Giant"))
    alice_giant, bears = None, scenario.creature("Grizzly Bears", "alice")
    alice_giant = next(
        s for s in scenario.game.battlefield if s.name == "Hill Giant" and s.controller == "alice"
    )
    bob_giant = next(
        s for s in scenario.game.battlefield if s.name == "Hill Giant" and s.controller == "bob"
    )
    bears.summoning_sick = False
    alice_giant.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, alice_giant, defending="bob")
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.block(bears, bob_giant)
    scenario.will_take_the_may(True, username="alice", source="Grizzly Bears")
    scenario.combat_damage()
    # the unblocked Hill Giant hits for 3 as always, the blocked Bears chose the player
    assert scenario.player("bob").life == 20 - 3 - 2
    assert bob_giant.damage == 0


def test_an_unblocked_creature_is_not_asked_anything():
    scenario = _focus_board(bob_creatures=())
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.combat_damage()
    assert scenario.player("bob").life == 18


def test_a_creature_that_arrives_after_the_spell_resolved_has_no_permission():
    """CR 611.2c: only the creatures it could affect as it resolved."""
    scenario = _focus_board()
    late = scenario.put_onto_battlefield("Hill Giant", "alice")
    assert not may_assign_as_though_unblocked(scenario.game, late)
    assert may_assign_as_though_unblocked(scenario.game, scenario.creature("Grizzly Bears", "alice"))


def test_an_opponents_creature_has_no_permission():
    scenario = _focus_board()
    assert not may_assign_as_though_unblocked(scenario.game, scenario.creature("Hill Giant", "bob"))


def test_the_permission_ends_with_the_turn():
    scenario = _focus_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    while scenario.turn.active_player != "bob":
        scenario.advance()
    assert not may_assign_as_though_unblocked(scenario.game, bears)
