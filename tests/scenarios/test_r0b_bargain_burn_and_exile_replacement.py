"""R0b proofs: Torch the Tower's bargain and exile-instead replacement, and
Mana Tithe's "counter unless its controller pays {1}".

Torch the Tower ("Bargain. Torch the Tower deals 2 damage to target creature
or planeswalker. If this spell was bargained, instead it deals 3 damage to
that permanent and you scry 1. If a permanent dealt damage by Torch the Tower
would die this turn, exile it instead.") and Mana Tithe were `handled` and
untested; each ability is proved through the engine here.

Every CR number below was looked up with `mise run rules:find`:

- **CR 702.166a / 702.166b** - bargain: sacrifice an artifact, enchantment, or
  token as an additional cost; paying it makes the spell "bargained".
- **CR 701.22a** - scry.
- **CR 120.3c** - damage to a planeswalker removes that many loyalty counters.
- **CR 614.1a** - "instead" effects that replace an event are replacement
  effects (the exile in place of dying).
- **CR 118.12a** - "[do something] unless [a player does something else]"
  means that player may do the something else; if they don't, the first happens.
- **CR 608.2g** - a player may activate mana abilities while paying a cost
  asked for during resolution.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from tests.scenarios.harness import Scenario


def _torch_board(*, alice_battlefield=(), bob_battlefield=("Grizzly Bears",), library=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Torch the Tower", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain", *alice_battlefield],
            library=list(library),
        )
        .player("bob", battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_torch(scenario, target, *, bargain=None):
    torch = scenario.find("Torch the Tower", Zone.HAND, "alice")
    (mountain, _) = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.game.cast(torch, "alice", targets=[target], bargain=bargain, mana_sources=[mountain])
    scenario.resolve_top()
    return torch


# -- Torch the Tower -----------------------------------------------------------------


def test_unbargained_torch_deals_two_and_exiles_the_creature_it_kills():
    scenario = _torch_board()
    bears = scenario.creature("Grizzly Bears", "bob")

    _cast_torch(scenario, bears)

    assert bears.zone is Zone.EXILE, "dealt damage by Torch and would die: exiled instead"


def test_unbargained_torch_does_not_kill_a_three_toughness_creature():
    scenario = _torch_board(bob_battlefield=["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")

    _cast_torch(scenario, giant)

    assert giant.zone is Zone.BATTLEFIELD
    assert giant.damage == 2


def test_bargained_torch_deals_three_to_the_same_creature():
    scenario = _torch_board(alice_battlefield=["Mind Stone"], bob_battlefield=["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")

    _cast_torch(scenario, giant, bargain=stone)

    assert stone.zone is Zone.GRAVEYARD, "bargain sacrificed the artifact (CR 702.166a)"
    assert giant.zone is Zone.EXILE, "3 damage kills the 3/3 Hill Giant: exiled instead"


def test_bargained_torch_scries_one_and_unbargained_does_not():
    scenario = _torch_board(
        alice_battlefield=["Mind Stone"],
        bob_battlefield=["Hill Giant"],
        library=["Forest", "Island", "Swamp"],
    )
    (top,) = scenario.top_of_library(1, "alice")
    giant = scenario.creature("Hill Giant", "bob")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    scenario.scry_bottoming(top, username="alice")

    _cast_torch(scenario, giant, bargain=stone)

    assert scenario.top_of_library(1, "alice")[0] is not top, "the scried card went to the bottom"


def test_unbargained_torch_asks_no_scry():
    scenario = _torch_board(library=["Forest", "Island"])
    bears = scenario.creature("Grizzly Bears", "bob")

    _cast_torch(scenario, bears)

    assert not [q for q in scenario.questions_asked() if q.kind is DecisionKind.SCRY]


def test_torch_bargain_accepts_an_enchantment():
    scenario = _torch_board(alice_battlefield=["Ghostly Prison"], bob_battlefield=["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")
    prison = scenario.find("Ghostly Prison", Zone.BATTLEFIELD, "alice")

    _cast_torch(scenario, giant, bargain=prison)

    assert prison.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.EXILE


def test_torch_bargain_refuses_a_nontoken_creature():
    """CR 702.166a: Grizzly Bears is neither an artifact, an enchantment nor a token."""
    scenario = _torch_board(alice_battlefield=["Grizzly Bears"])
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")
    casting = scenario.cast("Torch the Tower")

    with pytest.raises(ValueError, match="artifact, enchantment, or token"):
        casting.pay_bargain(mine)
    assert theirs.zone is Zone.BATTLEFIELD


def test_torch_damage_a_creature_survives_still_exiles_it_if_it_dies_later_this_turn():
    """The replacement lasts the turn: Torch (2 damage) leaves Hill Giant
    alive, a later Lightning Bolt kills it, and it is exiled, not buried."""
    scenario = _torch_board(bob_battlefield=["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")
    _cast_torch(scenario, giant)
    assert giant.zone is Zone.BATTLEFIELD

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[giant])

    assert giant.zone is Zone.EXILE


def test_a_creature_torch_never_damaged_still_dies_normally():
    scenario = _torch_board(bob_battlefield=["Grizzly Bears", "Memnite"])
    memnite = scenario.creature("Memnite", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_torch(scenario, bears)

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[memnite])

    assert bears.zone is Zone.EXILE
    assert memnite.zone is Zone.GRAVEYARD, "never dealt damage by Torch: not exiled"


def test_torch_removes_loyalty_from_a_planeswalker_and_exiles_it_if_it_dies():
    """CR 120.3c: Liliana of the Veil (3 loyalty) takes 3 from a bargained Torch."""
    scenario = _torch_board(
        alice_battlefield=["Mind Stone"], bob_battlefield=["Liliana of the Veil"]
    )
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")

    _cast_torch(scenario, liliana, bargain=stone)

    assert liliana.zone is Zone.EXILE


def test_unbargained_torch_leaves_a_planeswalker_at_one_loyalty():
    scenario = _torch_board(bob_battlefield=["Liliana of the Veil"])
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")

    _cast_torch(scenario, liliana)

    assert liliana.zone is Zone.BATTLEFIELD
    assert liliana.loyalty == 1


def test_torch_cannot_target_a_player():
    scenario = _torch_board()
    with pytest.raises(ValueError):
        scenario.cast("Torch the Tower", targets=["bob"])


# -- Mana Tithe ----------------------------------------------------------------------


def _tithe_board() -> Scenario:
    return (
        Scenario()
        .player("alice", hand=["Opt"], battlefield=["Island"])
        .player("bob", hand=["Mana Tithe"], battlefield=["Plains"])
    )


def _alice_casts_opt(scenario):
    opt = scenario.cast_onto_stack("Opt", username="alice", auto=True)
    scenario.pass_priority("alice")
    return opt


def _bob_tithes(scenario, opt):
    (plains,) = scenario.untapped_sources("Plains", username="bob")
    scenario.cast_and_resolve("Mana Tithe", plains, username="bob", targets=[opt])


def test_mana_tithe_counters_a_spell_whose_controller_cannot_pay():
    scenario = _tithe_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    opt = _alice_casts_opt(scenario)

    _bob_tithes(scenario, opt)

    assert opt.zone is Zone.GRAVEYARD
    (decision,) = [q for q in scenario.questions_asked() if q.kind is DecisionKind.PAY_MANA]
    assert decision.affirmative_is_legal is False
    assert decision.amount == 1


def test_mana_tithe_lets_the_spell_through_when_its_controller_pays_the_one():
    scenario = _tithe_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    alice.mana_pool.add(Color.COLORLESS, 1)
    opt = _alice_casts_opt(scenario)
    scenario.will_pay_the_mana_cost(True, username="alice", source="Mana Tithe")

    _bob_tithes(scenario, opt)

    assert opt.zone is Zone.STACK
    assert alice.mana_pool.total == 0


def test_mana_tithe_counters_when_the_controller_could_pay_but_declines():
    scenario = _tithe_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    alice.mana_pool.add(Color.COLORLESS, 1)
    opt = _alice_casts_opt(scenario)
    scenario.will_pay_the_mana_cost(False, username="alice", source="Mana Tithe")

    _bob_tithes(scenario, opt)

    assert opt.zone is Zone.GRAVEYARD
    assert alice.mana_pool.total == 1


def test_mana_tithe_can_be_paid_by_tapping_an_untapped_land():
    """CR 608.2g: alice's second Island can be tapped to pay the {1}."""
    scenario = (
        Scenario()
        .player("alice", hand=["Opt"], battlefield=["Island", "Island"])
        .player("bob", hand=["Mana Tithe"], battlefield=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island, _) = scenario.untapped_sources("Island", "Island", username="alice")
    opt = scenario.cast_onto_stack("Opt", island, username="alice")
    scenario.pass_priority("alice")
    scenario.will_pay_the_mana_cost(True, username="alice", source="Mana Tithe")

    _bob_tithes(scenario, opt)

    assert opt.zone is Zone.STACK


def test_mana_tithe_cannot_target_a_permanent():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Island"])
        .player("bob", hand=["Mana Tithe"], battlefield=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    scenario.pass_priority("alice")

    with pytest.raises(ValueError):
        scenario.cast("Mana Tithe", username="bob", targets=[island])
