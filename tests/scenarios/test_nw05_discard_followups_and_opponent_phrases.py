"""Damage follow-ups, discard-then-draw and "each of your opponents" (NW-05, T4).

- Sonic Shrieker: "it deals 2 damage to any target and you gain 2 life. If a
  player is dealt damage this way, they discard a card." - the discard follows
  damage that was actually dealt to a player (CR 120.3a; prevented damage is
  never dealt, CR 615.6), never a creature or planeswalker target.

- Aurelia, the Law Above: "deals 3 damage to each of your opponents" is the
  same instruction as "each opponent" (CR 102.2), and the three-or-more
  sibling trigger keeps reading.

CR numbers checked with `mise run rules:find` (rules effective 2026-09-25).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# -- Sonic Shrieker -----------------------------------------------------------


def _shrieker_board(*, bob_hand=(), bob_battlefield=("Plains",), alice_hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sonic Shrieker", *alice_hand],
            battlefield=["Mountain", "Plains", "Swamp", "Mountain", "Swamp"],
        )
        .player("bob", hand=list(bob_hand), battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _shrieker_trigger_on_stack(scenario, target):
    scenario.cast_onto_stack("Sonic Shrieker", auto=True)
    scenario.choose_trigger_targets("Sonic Shrieker", [target])
    scenario.resolve_top()  # the creature spell


def _cast_shrieker(scenario, target):
    _shrieker_trigger_on_stack(scenario, target)
    scenario.pass_until_resolved()


def test_a_player_dealt_damage_discards_a_card_and_alice_gains_life():
    scenario = _shrieker_board(bob_hand=["Grizzly Bears"])
    _cast_shrieker(scenario, "bob")
    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 22
    assert scenario.player("bob").hand == []


def test_the_damaged_player_chooses_what_to_discard():
    scenario = _shrieker_board(bob_hand=["Grizzly Bears", "Shock"])
    shock = scenario.find("Shock", Zone.HAND, "bob")
    scenario.will_discard(shock, username="bob")
    _cast_shrieker(scenario, "bob")
    assert [c.name for c in scenario.player("bob").hand] == ["Grizzly Bears"]
    assert shock.zone is Zone.GRAVEYARD


def test_a_creature_target_takes_the_damage_and_nobody_discards():
    scenario = _shrieker_board(bob_hand=["Shock"], bob_battlefield=["Plains", "Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")
    _cast_shrieker(scenario, giant)
    assert giant.damage == 2
    assert scenario.player("alice").life == 22
    assert [c.name for c in scenario.player("bob").hand] == ["Shock"]
    assert scenario.player("alice").hand == []


def test_an_empty_hand_discards_nothing_and_still_takes_the_damage():
    scenario = _shrieker_board()
    _cast_shrieker(scenario, "bob")
    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 22


def test_alice_may_target_herself_and_then_she_is_the_one_discarding():
    scenario = _shrieker_board(alice_hand=["Shock"])
    _cast_shrieker(scenario, "alice")
    assert scenario.player("alice").life == 20  # -2 then +2
    assert scenario.player("alice").hand == []


def test_fully_prevented_damage_is_not_dealt_so_nobody_discards_but_the_life_is_gained():
    """CR 615.6: Healing Salve stops all of the 2 damage - no discard - while
    "you gain 2 life" is its own instruction and still happens."""
    scenario = _shrieker_board(bob_hand=["Healing Salve", "Grizzly Bears"])
    _shrieker_trigger_on_stack(scenario, "bob")
    scenario.pass_priority("alice")
    salve = scenario.cast("Healing Salve", "bob")
    salve.choose_modes([2])
    salve.choose_targets(["bob"])
    payment = salve.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains", username="bob"))
    scenario.put_on_stack(salve)
    scenario.resolve_top()
    scenario.resolve_top()
    assert scenario.player("bob").life == 20
    assert scenario.player("alice").life == 22
    assert [c.name for c in scenario.player("bob").hand] == ["Grizzly Bears"]


# -- Aurelia, the Law Above: "each of your opponents" --------------------------


def _aurelia_board(*, attackers_alice=5, third_player=False):
    creatures = ["Grizzly Bears"] * attackers_alice
    builder = (
        Scenario()
        .player("alice", battlefield=["Aurelia, the Law Above", *creatures], library=["Plains"] * 5)
        .player("bob", library=["Plains"] * 5)
    )
    if third_player:
        builder = builder.player("carol", library=["Plains"] * 5)
    scenario = builder.build()
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    return scenario


def _attack_with_the_bears(scenario, count, defending=None):
    bears = scenario.creatures(*["Grizzly Bears"] * count, username="alice")
    for creature in bears:
        creature.summoning_sick = False
    scenario.advance()  # declare attackers step
    scenario.attack_with(*bears, defending=defending)
    return bears


def test_five_attackers_drain_each_of_your_opponents_for_three():
    scenario = _aurelia_board()
    _attack_with_the_bears(scenario, 5)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 23


def test_three_attackers_only_draw_a_card_and_do_not_drain():
    scenario = _aurelia_board(attackers_alice=3)
    _attack_with_the_bears(scenario, 3)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 20
    assert scenario.player("alice").life == 20
    assert len(scenario.player("alice").hand) == 1


def test_fewer_than_three_attackers_trigger_neither_ability():
    """The count is part of the trigger event (CR 508.3d), not decoration."""
    scenario = _aurelia_board(attackers_alice=2)
    _attack_with_the_bears(scenario, 2)
    assert scenario.stack_names() == []
    assert scenario.player("bob").life == 20


def test_five_attackers_trigger_each_ability_once_not_once_per_attacker():
    scenario = _aurelia_board()
    _attack_with_the_bears(scenario, 5)
    assert len(scenario.stack_names()) == 2
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 23
    assert len(scenario.player("alice").hand) == 1


def test_it_drains_every_opponent_not_just_one():
    scenario = _aurelia_board(third_player=True)
    _attack_with_the_bears(scenario, 5, defending="bob")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 17
    assert scenario.player("carol").life == 17
    assert scenario.player("alice").life == 23


def test_everything_pizza_still_makes_every_opponent_discard_with_the_phrase_normalised():
    """Regression for the one other pool printing carrying "each of your
    opponents" (CR 102.2): its discard sentence already read before the
    normaliser, and rewriting the phrase must leave it reading, for every
    opponent."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Everything Pizza", "Grizzly Bears"]
            + ["Plains", "Island", "Swamp", "Mountain", "Forest", "Plains", "Plains"],
            library=["Forest"] * 10,
        )
        .player("bob", hand=["Counterspell"], library=["Island"] * 10)
        .player("carol", hand=["Counterspell"], library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pizza = scenario.find("Everything Pizza", Zone.BATTLEFIELD, "alice")
    sources = scenario.untapped_sources(
        "Plains", "Island", "Swamp", "Mountain", "Forest", "Plains", "Plains"
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.activate(pizza, *sources, sacrificing=[pizza], targets=[bears, "alice", bears])
    scenario.pass_until_resolved()
    assert scenario.player("bob").hand == []
    assert scenario.player("carol").hand == []


# -- Mishra's Command: "They may discard up to X cards. Then they draw a card ---
# -- for each card discarded this way." -----------------------------------------
#
# CR 107.3a (X comes from the cast), CR 107.1c ("up to" is zero or more),
# CR 701.9b (the discarding player chooses), CR 608.2c ("this way" counts what
# was actually discarded). No other legal printing carries this template
# (Scryfall o: searches, 2026-10-07); Cathartic Pyre's "Discard up to two
# cards, then draw that many cards." proves the shared discard-and-count path.

from magic_cards_model.support import card_support  # noqa: E402
from tests.cards import card  # noqa: E402

MISHRAS_COMMAND = "Mishra's Command"


def _command_board(*, bob_hand=("Shock", "Grizzly Bears", "Opt"), bob_battlefield=("Hill Giant",)):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[MISHRAS_COMMAND],
            battlefield=["Mountain"] * 6,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=list(bob_battlefield),
            library=["Plains"] * 6,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _discard_mode(scenario, player, x_value):
    """Mode 1 on `player`, paired with mode 4 on Hill Giant (a command needs two modes)."""
    giant = scenario.creature("Hill Giant", "bob")
    _cast_command(scenario, [1, 4], [player, giant], x_value)
    return giant


def _cast_command(scenario, modes, targets, x_value):
    casting = scenario.cast(MISHRAS_COMMAND)
    casting.choose_modes(modes, x_value=x_value)
    casting.choose_targets(targets)
    casting.determine_cost(x_value=x_value)
    sources = scenario.untapped_sources(*["Mountain"] * (x_value + 1))
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def test_mishras_command_is_fully_handled():
    bad = [c for c in card_support(card(MISHRAS_COMMAND)).clauses if c.outcome != "handled"]
    assert not bad, bad


def test_the_target_discards_what_they_choose_and_draws_that_many():
    scenario = _command_board()
    shock = scenario.find("Shock", Zone.HAND, "bob")
    opt = scenario.find("Opt", Zone.HAND, "bob")
    scenario.will_discard(shock, opt, username="bob")
    _discard_mode(scenario, "bob", 3)
    assert shock.zone is Zone.GRAVEYARD and opt.zone is Zone.GRAVEYARD
    # one card left in hand plus two drawn
    assert len(scenario.player("bob").hand) == 3


def test_discarding_zero_cards_draws_nothing():
    scenario = _command_board()
    scenario.will_discard(username="bob")
    _discard_mode(scenario, "bob", 2)
    assert [c.name for c in scenario.player("bob").hand] == ["Shock", "Grizzly Bears", "Opt"]


def test_the_ceiling_is_x_even_when_the_hand_is_bigger():
    scenario = _command_board()
    shock = scenario.find("Shock", Zone.HAND, "bob")
    scenario.will_discard(shock, username="bob")
    _discard_mode(scenario, "bob", 1)
    assert shock.zone is Zone.GRAVEYARD
    assert len(scenario.player("bob").hand) == 3  # 3 - 1 + 1


def test_a_hand_smaller_than_x_discards_what_it_has_and_draws_that_many():
    scenario = _command_board(bob_hand=("Shock",))
    shock = scenario.find("Shock", Zone.HAND, "bob")
    scenario.will_discard(shock, username="bob")
    _discard_mode(scenario, "bob", 4)
    assert shock.zone is Zone.GRAVEYARD
    assert len(scenario.player("bob").hand) == 1


def test_an_empty_hand_does_nothing():
    scenario = _command_board(bob_hand=())
    _discard_mode(scenario, "bob", 2)
    assert scenario.player("bob").hand == []


def test_alice_can_target_herself_and_an_empty_hand_does_nothing():
    scenario = _command_board()
    _discard_mode(scenario, "alice", 2)  # the cast left alice with no hand
    assert scenario.player("alice").hand == []
    assert len(scenario.player("bob").hand) == 3


def test_the_damage_and_pump_modes_still_read_and_resolve():
    scenario = _command_board()
    giant = scenario.creature("Hill Giant", "bob")
    _cast_command(scenario, [2, 4], [giant, giant], 2)
    assert giant.power == 5, "+2/+0 from mode 4 on a 3/3"
    assert giant.damage == 2, "2 damage from mode 2"


def test_the_planeswalker_damage_mode_pairs_with_the_discard_mode():
    scenario = _command_board(bob_battlefield=("Jace Beleren",))
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")
    loyalty_before = jace.loyalty
    shock = scenario.find("Shock", Zone.HAND, "bob")
    scenario.will_discard(shock, username="bob")
    _cast_command(scenario, [1, 3], ["bob", jace], 1)
    assert jace.loyalty == loyalty_before - 1
    assert shock.zone is Zone.GRAVEYARD
