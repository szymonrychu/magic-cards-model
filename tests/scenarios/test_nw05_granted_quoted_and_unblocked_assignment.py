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
