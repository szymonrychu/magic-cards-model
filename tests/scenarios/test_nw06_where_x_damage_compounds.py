"""One "where X is <count>" shared by every instruction of a compound that uses
X (NW-06, task T2).

- Arabella, Abandoned Doll: "it deals X damage to each opponent and you gain X
  life, where X is the number of creatures you control with power 2 or less."
  The definition closes the second instruction but gives X that value on the
  whole object (CR 107.3c), so both instructions read the one
  count, fixed once as the ability resolves (CR 608.2h).
- Niv-Mizzet, Guildpact: "it deals X damage to any target, target player draws
  X cards, and you gain X life, where X is the number of different color
  pairs among permanents you control that are exactly two colors." Three
  instructions, one definition, and a count of distinct two-colour
  combinations (CR 105.1: a permanent's colours; a permanent that is exactly
  two colours has one pair).

CR numbers checked with `mise run rules:find` (rules effective 2026-09-25).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.effects import trigger_effect_for
from magic_cards_model.machines.effects.amounts import count_expression
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

NIV = "Niv-Mizzet, Guildpact"


def _resolve_everything(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _life(scenario: Scenario, username: str) -> int:
    return scenario.player(username).life


# -- Arabella: damage and life from one X --------------------------------------------


def _arabella(*, alice=(), bob=(), carol=None):
    scenario = Scenario().player("alice", battlefield=["Arabella, Abandoned Doll", *alice])
    scenario = scenario.player("bob", battlefield=list(bob))
    if carol is not None:
        scenario = scenario.player("carol", battlefield=list(carol))
    built = scenario.build()
    built.start_at(Step.DECLARE_ATTACKERS)
    built.attack_with(built.creature("Arabella, Abandoned Doll", "alice"), defending="bob")
    _resolve_everything(built)
    return built


def test_arabella_damages_each_opponent_and_gains_the_same_amount():
    scenario = _arabella(alice=["Llanowar Elves", "Grizzly Bears", "Hill Giant"])
    # Arabella (power 1), Elves (1) and Bears (2) have power 2 or less; the Giant has 3.
    assert _life(scenario, "bob") == 17
    assert _life(scenario, "alice") == 23


def test_arabella_counts_power_after_counters_and_ignores_opposing_creatures():
    scenario = Scenario().player(
        "alice", battlefield=["Arabella, Abandoned Doll", "Llanowar Elves", "Grizzly Bears"]
    )
    built = scenario.player("bob", battlefield=["Llanowar Elves"] * 3).build()
    built.start_at(Step.PRECOMBAT_MAIN)
    built.creature("Grizzly Bears", "alice").add_counters("+1/+1", 1)
    built.start_at(Step.DECLARE_ATTACKERS)
    built.attack_with(built.creature("Arabella, Abandoned Doll", "alice"))
    _resolve_everything(built)
    assert _life(built, "bob") == 18  # Arabella and Elves only
    assert _life(built, "alice") == 22


def test_every_opponent_loses_the_one_fixed_amount():
    scenario = _arabella(alice=["Llanowar Elves"], carol=["Hill Giant"])
    assert _life(scenario, "bob") == 18
    assert _life(scenario, "carol") == 18
    assert _life(scenario, "alice") == 22


def test_arabella_counts_herself_even_when_pumped_out_of_the_bound_it_does_not_count_her():
    scenario = Scenario().player("alice", battlefield=["Arabella, Abandoned Doll", "Hill Giant"])
    built = scenario.player("bob").build()
    built.start_at(Step.PRECOMBAT_MAIN)
    built.creature("Arabella, Abandoned Doll", "alice").add_counters("+1/+1", 2)  # power 3
    built.start_at(Step.DECLARE_ATTACKERS)
    built.attack_with(built.creature("Arabella, Abandoned Doll", "alice"))
    _resolve_everything(built)
    assert _life(built, "bob") == 20
    assert _life(built, "alice") == 20


def test_the_compound_reads_with_its_count_as_a_plain_ability_effect():
    effect = trigger_effect_for(
        "Arabella, Abandoned Doll",
        TriggerEvent.ATTACKS,
        "it deals X damage to each opponent and you gain X life, where X is the number of "
        "creatures you control with power 2 or less.",
    )
    assert effect is not None


# -- Niv-Mizzet, Guildpact: three instructions, one X -----------------------------------


def _niv_board(*, alice=(), bob=(), library=("Mountain",) * 6):
    scenario = (
        Scenario()
        .player("alice", battlefield=[NIV, *alice], library=list(library))
        .player("bob", battlefield=list(bob), library=["Mountain"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _connect(scenario, *, damage_to="bob", draws="alice"):
    scenario.choose_trigger_targets(NIV, [damage_to, draws])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature(NIV, "alice"))
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    scenario.combat_damage()
    _resolve_everything(scenario)


def test_niv_mizzet_damages_draws_and_gains_the_count_of_color_pairs():
    scenario = _niv_board(alice=["Boros Reckoner", "Kitchen Finks", "Goblin Guide"])
    hand_before = len(scenario.player("alice").hand)
    _connect(scenario)
    # Reckoner is red-white, Finks is green-white: two pairs. Goblin Guide is mono-red.
    # Niv-Mizzet's own combat damage (6) is dealt first.
    assert _life(scenario, "bob") == 20 - 6 - 2
    assert _life(scenario, "alice") == 22
    assert len(scenario.player("alice").hand) == hand_before + 2


def test_two_permanents_of_the_same_pair_count_once():
    scenario = _niv_board(alice=["Boros Reckoner", "Boros Reckoner"])
    _connect(scenario)
    assert _life(scenario, "bob") == 20 - 6 - 1
    assert _life(scenario, "alice") == 21


def test_only_permanents_that_are_exactly_two_colors_count():
    scenario = _niv_board(alice=["Goblin Guide", "Kitchen Finks"], bob=["Boros Reckoner"])
    _connect(scenario)
    # Niv-Mizzet is five colours, Goblin Guide one; Finks is the one pair. Bob's Reckoner is his.
    assert _life(scenario, "bob") == 20 - 6 - 1
    assert _life(scenario, "alice") == 21


def test_with_no_two_color_permanents_x_is_zero():
    scenario = _niv_board(alice=["Goblin Guide"])
    hand_before = len(scenario.player("alice").hand)
    _connect(scenario)
    assert _life(scenario, "bob") == 20 - 6
    assert _life(scenario, "alice") == 20
    assert len(scenario.player("alice").hand) == hand_before


def test_the_draw_goes_to_the_chosen_player_and_the_damage_to_the_chosen_target():
    scenario = _niv_board(alice=["Boros Reckoner"], bob=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    bob_hand = len(scenario.player("bob").hand)
    _connect(scenario, damage_to=bears, draws="bob")
    assert bears.damage == 1
    assert len(scenario.player("bob").hand) == bob_hand + 1
    assert _life(scenario, "alice") == 21


def test_color_pair_phrase_reads_through_count_expression():
    counted = count_expression(
        "the number of different color pairs among permanents you control "
        "that are exactly two colors"
    )
    assert counted is not None
    scenario = _niv_board(alice=["Boros Reckoner", "Kitchen Finks"], bob=["Boros Reckoner"])
    assert counted(scenario.game, "alice") == 2
    assert counted(scenario.game, "bob") == 1
    reckoner = scenario.find("Boros Reckoner", Zone.BATTLEFIELD, "alice")
    assert reckoner is not None
