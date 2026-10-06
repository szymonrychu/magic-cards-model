"""Scenario: "Prevent the next N damage that [a source of your choice] would
deal to you and/or permanents you control this turn. If damage is prevented
this way, <this spell> deals that much damage to any target." - a counting
shield around a player and everything they control, with a damage rider -
and Refraction Trap's conditional alternative cost.

Rules, each read in full with `mise run rules:find`:

- CR 615.7 - a shield of N damage: "Each 1 damage that would be dealt to the
  "shielded" permanent or player is prevented. Preventing 1 damage reduces
  the remaining shield by 1 ... Once the shield has been reduced to 0, any
  remaining damage is dealt normally."
- CR 615.5 - "Some prevention effects also include an additional effect, which
  may refer to the amount of damage that was prevented. The prevention takes
  place at the time the original event would have happened; the rest of the
  effect takes place immediately afterward."
- CR 609.7a - "a source of your choice ... The source is chosen when the
  effect is created."
- CR 601.2c - the target of "any target" is chosen as the spell is cast, like
  every other target the spell requires; CR 608.2b rechecks it on resolution.
- CR 118.9 - "An alternative cost is a cost listed in a spell's text ... that
  its controller may pay rather than paying the spell's mana cost."
- CR 615.12 - "Existing damage prevention shields won't be reduced by damage
  that can't be prevented."

Listed printing: Refraction Trap. Proof printing: Divine Deflection ("the next
X damage that would be dealt to you and/or permanents you control", no source
choice, X from its own mana cost; not listed, not in any api deck, legal in
Modern).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import AlternativeCostSource
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario


@pytest.mark.parametrize("name", ["Refraction Trap", "Divine Deflection"])
def test_every_listed_and_proof_card_reads_handled(name):
    outcomes = {clause.outcome for clause in card_support(card(name)).clauses}
    assert outcomes == {"handled"}, name


def _board(*, alice_battlefield=(), bob_battlefield=(), alice_hand=(), bob_hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=[*["Plains"] * 4, *alice_battlefield],
            library=["Plains"] * 8,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=[*["Mountain"] * 3, "Island", *bob_battlefield],
            library=["Mountain"] * 8,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    return scenario


def _trap_offer(casting):
    return next(
        option
        for option in casting.alternative_costs
        if option.source is AlternativeCostSource.PRINTED
    )


def _bolt_on_the_stack(scenario, target):
    bolt = scenario.cast_onto_stack("Lightning Bolt", username="bob", targets=[target], auto=True)
    return bolt


def _trap(scenario, *, source, target, pitch=True):
    if scenario.priority_holder != "alice":
        scenario.pass_priority(scenario.priority_holder)
    scenario.will_choose_cards(source, username="alice")
    casting = scenario.cast("Refraction Trap", username="alice")
    if pitch:
        casting.use_pitch_cost()
    casting.choose_targets([target])
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


# -- the alternative cost ---------------------------------------------------------


def test_the_trap_cost_is_unavailable_before_a_red_instant_or_sorcery():
    scenario = _board(alice_hand=["Refraction Trap"])

    casting = scenario.cast("Refraction Trap", username="alice")

    assert not _trap_offer(casting).available


def test_a_red_instant_from_an_opponent_opens_the_trap_cost():
    scenario = _board(alice_hand=["Refraction Trap"], bob_hand=["Lightning Bolt"])
    _bolt_on_the_stack(scenario, "alice")
    scenario.pass_priority("bob")

    casting = scenario.cast("Refraction Trap", username="alice")

    assert _trap_offer(casting).available
    assert str(_trap_offer(casting).cost) == "{W}"


def test_a_blue_spell_from_an_opponent_does_not_open_the_trap_cost():
    scenario = _board(alice_hand=["Refraction Trap"], bob_hand=["Opt"])
    scenario.cast_onto_stack("Opt", username="bob", auto=True)
    scenario.pass_priority("bob")

    casting = scenario.cast("Refraction Trap", username="alice")

    assert not _trap_offer(casting).available


def test_alices_own_red_spell_does_not_open_the_trap_cost():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Refraction Trap", "Lightning Bolt"],
            battlefield=["Plains", "Mountain"],
            library=["Plains"] * 8,
        )
        .player("bob", library=["Mountain"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Lightning Bolt", username="alice", targets=["bob"], auto=True)

    casting = scenario.cast("Refraction Trap", username="alice")

    assert not _trap_offer(casting).available


def _ricochet_board():
    scenario = (
        Scenario()
        .player("alice", hand=["Ricochet Trap"], battlefield=["Mountain"], library=["Plains"] * 8)
        .player("bob", hand=["Opt"], battlefield=["Island"], library=["Island"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    return scenario


def test_ricochet_trap_cost_is_unavailable_before_a_blue_spell():
    """Proof printing for the same reader: "If an opponent cast a blue spell
    this turn, you may pay {R} rather than pay this spell's mana cost."."""
    scenario = _ricochet_board()
    scenario.pass_priority("bob")

    casting = scenario.cast("Ricochet Trap", username="alice")

    assert not _trap_offer(casting).available


def test_ricochet_trap_cost_opens_after_an_opponents_blue_spell():
    scenario = _ricochet_board()
    scenario.cast_onto_stack("Opt", username="bob", auto=True)
    scenario.pass_priority("bob")

    casting = scenario.cast("Ricochet Trap", username="alice")

    assert _trap_offer(casting).available
    assert str(_trap_offer(casting).cost) == "{R}"


# -- the counting shield and its rider ---------------------------------------------


def test_the_trap_prevents_the_bolt_and_deals_that_much_to_its_target():
    scenario = _board(
        alice_hand=["Refraction Trap"],
        bob_hand=["Lightning Bolt"],
        bob_battlefield=["Hill Giant"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    bolt = _bolt_on_the_stack(scenario, "alice")
    _trap(scenario, source=bolt, target=giant)

    scenario.resolve_top()  # the Bolt

    assert scenario.player("alice").life == 20
    assert giant.zone is Zone.GRAVEYARD  # 3 prevented, so the Trap deals 3


def test_the_trap_covers_permanents_alice_controls():
    scenario = _board(
        alice_hand=["Refraction Trap"],
        alice_battlefield=["Grizzly Bears"],
        bob_hand=["Lightning Bolt"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    bolt = _bolt_on_the_stack(scenario, bears)
    _trap(scenario, source=bolt, target="bob")

    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0
    assert scenario.player("bob").life == 17


def test_the_trap_prevents_only_three_and_the_rest_is_dealt():
    scenario = _board(alice_hand=["Refraction Trap"], bob_battlefield=["Craw Wurm"])
    wurm = scenario.creature("Craw Wurm", "bob")
    _trap(scenario, source=wurm, target="bob", pitch=False)
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
    # Bob's turn: the shield ended with alice's turn (CR 514.2).
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.attack_with(wurm, defending="alice")
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("alice").life == 14


def test_the_trap_spends_three_across_combat_and_reflects_each_time():
    scenario = _board(
        alice_hand=["Refraction Trap"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Craw Wurm"],
    )
    # Alice is attacked on her own turn's combat by nothing; build bob's turn.
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.pass_priority(scenario.priority_holder)
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.attack_with(wurm, defending="alice")
    scenario.no_blocks()
    if scenario.priority_holder != "alice":
        scenario.pass_priority(scenario.priority_holder)
    _trap(scenario, source=wurm, target=wurm, pitch=False)

    scenario.combat_damage()

    assert scenario.player("alice").life == 17  # 6 - 3 prevented
    assert wurm.damage == 3  # the Trap deals the 3 it prevented to the Wurm


def test_another_source_is_not_shielded():
    scenario = _board(
        alice_hand=["Refraction Trap"],
        bob_hand=["Lightning Bolt", "Shock"],
        bob_battlefield=["Hill Giant"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    bolt = _bolt_on_the_stack(scenario, "alice")
    _trap(scenario, source=bolt, target="bob")
    scenario.resolve_top()  # Bolt: prevented, 3 to bob
    if scenario.priority_holder != "bob":
        scenario.pass_priority(scenario.priority_holder)
    scenario.cast_and_resolve("Shock", username="bob", targets=["alice"], auto=True)

    assert scenario.player("alice").life == 18
    assert scenario.player("bob").life == 17
    assert giant.zone is Zone.BATTLEFIELD


def test_the_rider_does_nothing_if_the_target_is_gone():
    scenario = _board(
        alice_hand=["Refraction Trap"],
        bob_hand=["Lightning Bolt", "Shock"],
        bob_battlefield=["Grizzly Bears", "Hill Giant"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    bolt = _bolt_on_the_stack(scenario, "alice")
    _trap(scenario, source=bolt, target=bears)
    # The target leaves before any damage is prevented.
    scenario.game.destroy(bears)

    scenario.resolve_top()

    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 20


# -- Divine Deflection: the same shield with no source choice, X from its cost ---


def _deflect(scenario, x, target):
    scenario.game.cast(
        scenario.find("Divine Deflection", Zone.HAND, "alice"),
        "alice",
        x_value=x,
        targets=[target],
        mana_sources=scenario.untapped_sources(*["Plains"] * (x + 1)),
    )
    return scenario.resolve_top()


def test_divine_deflection_prevents_x_and_deals_that_much():
    scenario = _board(
        alice_hand=["Divine Deflection"],
        alice_battlefield=["Grizzly Bears"],
        bob_hand=["Lightning Bolt"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    bolt = _bolt_on_the_stack(scenario, "alice")
    scenario.pass_priority("bob")
    _deflect(scenario, 2, "bob")

    scenario.resolve_top()

    assert scenario.player("alice").life == 19  # 3 - 2 prevented
    assert scenario.player("bob").life == 18
    assert bears.damage == 0
    assert bolt.zone is Zone.GRAVEYARD
