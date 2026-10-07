"""Amount terms and hand history (NW-05, task T4).

- Zenith Flare: "X is the number of cards with a cycling ability in your
  graveyard" - typecycling counts (CR 702.29f); the count is fixed once as the
  spell resolves (CR 608.2h).

- Tangled Colony: "X is the amount of damage dealt to it this turn" - the
  damage ledger (CR 120.1) read by last-known information once the creature
  has died (CR 400.7, CR 608.2h), counting only the incarnation that died.

- Mindstorm Crown: "draw a card if you had no cards in hand at the beginning
  of this turn. If you had a card in hand, this artifact deals 1 damage to
  you." - the hand as the turn began is recorded once (CR 500.1), so the two
  sentences are complementary whatever happens to the hand during the upkeep.

CR numbers checked with `mise run rules:find` (rules effective 2026-09-25).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects.amounts import count_expression
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# -- Zenith Flare -----------------------------------------------------------


def _flare_board(graveyard: list[str], *, bob_battlefield=("Elder Gargaroth",), bob_life=20):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Zenith Flare"],
            battlefield=["Mountain", "Mountain", "Plains", "Plains"],
            graveyard=graveyard,
        )
        .player("bob", life=bob_life, battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_zenith_flare_counts_plain_and_typecycling_cards_in_the_graveyard():
    scenario = _flare_board(["Street Wraith", "Generous Ent", "Lightning Bolt"])
    scenario.cast_and_resolve("Zenith Flare", auto=True, targets=["bob"])
    assert scenario.player("bob").life == 18, "Street Wraith and Generous Ent count, Bolt does not"
    assert scenario.player("alice").life == 22


def test_zenith_flare_with_no_cycling_cards_does_nothing_and_does_not_count_itself():
    scenario = _flare_board(["Lightning Bolt"])
    scenario.cast_and_resolve("Zenith Flare", auto=True, targets=["bob"])
    assert scenario.player("bob").life == 20
    assert scenario.player("alice").life == 20


def test_zenith_flare_ignores_an_opponents_graveyard_and_other_zones():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Zenith Flare", "Street Wraith"],
            battlefield=["Mountain", "Mountain", "Plains", "Plains"],
        )
        .player("bob", graveyard=["Street Wraith", "Generous Ent"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Zenith Flare", auto=True, targets=["bob"])
    assert scenario.player("bob").life == 20, "only your own graveyard counts"


def test_zenith_flare_can_target_a_creature_and_still_gains_life():
    scenario = _flare_board(["Street Wraith", "Generous Ent", "Ash Barrens"])
    gargaroth = scenario.creature("Elder Gargaroth", "bob")
    scenario.cast_and_resolve("Zenith Flare", auto=True, targets=[gargaroth])
    assert gargaroth.damage == 3
    assert scenario.player("alice").life == 23
    assert scenario.player("bob").life == 20


def test_cycling_ability_count_phrase_reads_through_count_expression():
    counted = count_expression("the number of cards with a cycling ability in your graveyard")
    assert counted is not None
    scenario = _flare_board(["Street Wraith", "Lórien Revealed", "Lightning Bolt"])
    assert counted(scenario.game, "alice") == 2
    assert counted(scenario.game, "bob") == 0
    flare = scenario.cast_and_resolve("Zenith Flare", auto=True, targets=["bob"])
    assert flare.zone is Zone.GRAVEYARD
    assert counted(scenario.game, "alice") == 2, "the resolved spell has no cycling ability"
    assert scenario.player("bob").life == 18


# -- Tangled Colony: the amount of damage dealt to it this turn ---------------


def _rats(scenario, username="alice"):
    return [p for p in scenario.game.permanents_controlled_by(username) if p.name == "Rat Token"]


def _colony_board(*, hand=("Lightning Bolt",), mountains=2):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=["Tangled Colony", *["Mountain"] * mountains],
        )
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature("Tangled Colony", "alice")


def _bolt(scenario, target):
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[target]
    )
    scenario.state_based_actions()
    scenario.pass_until_resolved()


def test_tangled_colony_makes_one_rat_per_damage_dealt_to_it_this_turn():
    scenario, colony = _colony_board()
    _bolt(scenario, colony)
    assert colony.zone is Zone.GRAVEYARD
    assert len(_rats(scenario)) == 3


def test_damage_dealt_earlier_in_the_turn_counts_too():
    scenario, colony = _colony_board()
    scenario.game.deal_damage(colony, 1)
    assert colony.zone is Zone.BATTLEFIELD
    _bolt(scenario, colony)
    assert len(_rats(scenario)) == 4


def test_the_rats_cannot_block():
    scenario, colony = _colony_board()
    _bolt(scenario, colony)
    rats = _rats(scenario)
    assert rats
    assert all("This token can't block" in rat.oracle_text for rat in rats)


def test_a_creature_that_dies_to_a_sacrifice_with_no_damage_makes_no_rats():
    scenario, colony = _colony_board()
    scenario.game.sacrifice(colony)
    scenario.pass_until_resolved()
    assert colony.zone is Zone.GRAVEYARD
    assert _rats(scenario) == []


def test_only_the_incarnation_that_died_counts_after_a_return_this_turn():
    """CR 400.7: the colony that came back is a new object; the three damage
    the first one took is not damage dealt to it."""
    scenario, colony = _colony_board(hand=("Lightning Bolt", "Lightning Bolt"), mountains=2)
    _bolt(scenario, colony)
    assert len(_rats(scenario)) == 3
    again = scenario.put_onto_battlefield("Tangled Colony", from_zone=Zone.GRAVEYARD)
    scenario.game.deal_damage(again, 1)
    _bolt(scenario, again)
    assert again.zone is Zone.GRAVEYARD
    assert len(_rats(scenario)) == 3 + 4


def test_a_spell_dealing_damage_to_something_else_is_not_counted():
    scenario, colony = _colony_board(hand=("Lightning Bolt", "Lightning Bolt"))
    _bolt(scenario, "bob")
    _bolt(scenario, colony)
    assert len(_rats(scenario)) == 3


# -- Mindstorm Crown: the hand as the turn began --------------------------------


def _crown_board(hand=(), *, bob_hand=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=list(hand),
            battlefield=["Mindstorm Crown", "Mountain"],
            library=["Plains"] * 4,
        )
        .player("bob", hand=list(bob_hand), library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _next_upkeep(scenario)  # bob's
    _next_upkeep(scenario)  # alice's, with the Crown's trigger on the stack
    assert scenario.turn.active_player == "alice"
    assert scenario.stack_names() == ["Mindstorm Crown's triggered ability"]
    return scenario


def _next_upkeep(scenario) -> None:
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # the new turn's untap step
    scenario.advance()  # its upkeep


def test_an_empty_hand_at_the_start_of_the_turn_draws_a_card_and_costs_no_life():
    scenario = _crown_board()
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == 1
    assert scenario.player("alice").life == 20


def test_a_card_in_hand_at_the_start_of_the_turn_deals_one_damage_and_draws_nothing():
    scenario = _crown_board(hand=["Grizzly Bears"])
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == 1
    assert scenario.player("alice").life == 19


def test_several_cards_in_hand_still_deal_just_one_damage():
    scenario = _crown_board(hand=["Grizzly Bears", "Shock", "Giant Growth"])
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == 3
    assert scenario.player("alice").life == 19


def test_emptying_the_hand_in_response_does_not_earn_the_draw():
    """The hand is judged as the turn began, not as the ability resolves."""
    scenario = _crown_board(hand=["Lightning Bolt"])
    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    scenario.pass_until_resolved()  # the Bolt resolves
    scenario.pass_until_resolved()  # then the Crown's trigger
    assert scenario.player("alice").hand == []
    assert scenario.player("alice").life == 19
    assert scenario.player("bob").life == 17


def test_filling_the_hand_in_response_does_not_cost_the_draw():
    scenario = _crown_board()
    scenario.draw(2)
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == 3
    assert scenario.player("alice").life == 20


def test_the_opponents_hand_is_not_consulted():
    scenario = _crown_board(bob_hand=["Grizzly Bears"])
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == 1
    assert scenario.player("alice").life == 20


def test_the_record_is_per_turn_and_rolled_with_the_other_per_turn_ledgers():
    scenario = _crown_board(hand=["Grizzly Bears"])
    assert scenario.game.turn_count("hand_size_at_turn_start", "alice") == 1
    assert scenario.game.turn_count("hand_size_at_turn_start", "bob") == 0


# -- Generality proofs on other real printings -------------------------------
# No other legal printing words the damage-to-it or start-of-turn-hand template
# (Scryfall o: searches, 2026-10-07), so the readers are exercised directly
# through the phrase APIs against cards that do not print them.


def test_the_damage_dealt_to_it_term_reads_any_damaged_creature():
    from magic_cards_model.machines.effects.amounts import amount_expression

    reader = amount_expression("the amount of damage dealt to it this turn")
    assert reader is not None
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    assert reader(scenario.game, "alice", giant, 0) == 0
    scenario.game.deal_damage(giant, 2, source=giant)
    assert reader(scenario.game, "alice", giant, 0) == 2


def test_the_hand_at_the_start_of_the_turn_condition_reads_for_any_source():
    scenario = _crown_board(hand=["Grizzly Bears"])
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    scenario.game.discard_cards("alice", [bears], source="test")
    assert scenario.game.condition_holds("alice", "you had a card in hand", bears) is True
    assert (
        scenario.game.condition_holds(
            "alice", "you had no cards in hand at the beginning of this turn", bears
        )
        is False
    ), "emptying the hand since the turn began changes nothing"


# -- Guard narrowness (ratchet offenders) ------------------------------------


def test_the_if_guard_does_not_silence_gated_damage_to_each_opponent():
    """Only the `damage to you` reader refuses a leading "If <condition>, ":
    the printed "If ..., X deals 2 damage to each opponent." riders (Reckless
    Handling, Grab the Prize) still read as handled."""
    from magic_cards_model.machines.effects import effect_for
    from magic_cards_model.support import card_support
    from tests.cards import card

    assert card_support(card("Reckless Handling")).status == "handled"
    assert (
        effect_for(
            "If the discarded card wasn't a land card, Grab the Prize deals 2 damage to each opponent."
        )
        is not None
    )
