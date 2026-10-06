"""Scenario: "Prevent all damage <a source of your choice | one or two target
creatures> would deal this turn." - a shield keyed to its source.

Rules, each read in full with `mise run rules:find`:

- CR 609.7a - "If an effect requires a player to choose a source of damage,
  they may choose a permanent; a spell on the stack (including a permanent
  spell); any object referred to by an object on the stack ... The source is
  chosen when the effect is created."
- CR 615.1a - "Effects that use the word "prevent" are prevention effects."
- CR 601.2c - "If the spell has a variable number of targets, the player
  announces how many targets they will choose before they announce those
  targets."
- CR 400.7 - a permanent that leaves and returns is a new object the shield
  never named.

Listed printings: Pay No Heed, Soul Parry. Proof printing: Prahv, Spires of
Order's activated "{4}{W}{U}, {T}: Prevent all damage a source of your choice
would deal this turn." (the same sentence on a land's activated ability, a
different cost shape and object kind; not listed, not in any api deck, legal
in Modern).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario


@pytest.mark.parametrize("name", ["Pay No Heed", "Soul Parry", "Prahv, Spires of Order"])
def test_every_listed_and_proof_card_reads_handled(name):
    outcomes = {clause.outcome for clause in card_support(card(name)).clauses}
    assert outcomes == {"handled"}, name


def _board(*, alice_battlefield=(), bob_battlefield=(), alice_hand=(), bob_hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=[*["Plains"] * 4, *["Island"] * 2, *alice_battlefield],
            library=["Plains"] * 8,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=[*["Mountain"] * 4, *bob_battlefield],
            library=["Mountain"] * 8,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario, name, *, username="alice", targets=None):
    if scenario.priority_holder != username:
        scenario.pass_priority(scenario.priority_holder)
    return scenario.cast_and_resolve(name, username=username, targets=targets, auto=True)


# -- a source of your choice ----------------------------------------------------


def test_pay_no_heed_prevents_all_damage_the_chosen_permanent_deals():
    scenario = _board(
        alice_hand=["Pay No Heed"],
        alice_battlefield=["Grizzly Bears", "Savannah Lions"],
        bob_battlefield=["Hill Giant", "Gray Ogre"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    ogre = scenario.creature("Gray Ogre", "bob")
    scenario.will_choose_cards(giant, username="alice")
    _cast(scenario, "Pay No Heed")

    scenario.attack_with(bears, lions, defending="bob")
    scenario.block(bears, giant)
    scenario.block(lions, ogre)
    scenario.combat_damage()

    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0  # the chosen Giant's
    assert lions.zone is Zone.GRAVEYARD  # the Ogre was not chosen
    assert giant.damage == 2  # the shield is on the Giant's damage, not damage to it


def test_pay_no_heed_covers_combat_and_noncombat_damage_from_the_source():
    scenario = _board(
        alice_hand=["Pay No Heed"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Walking Ballista"],
    )
    ballista = scenario.creature("Walking Ballista", "bob")
    scenario.game.add_counters(ballista, "+1/+1", 2)
    scenario.will_choose_cards(ballista, username="alice")
    _cast(scenario, "Pay No Heed")

    scenario.pass_priority("alice")
    scenario.activate(ballista, index=1, username="bob", targets=["alice"])
    scenario.resolve_top()

    assert scenario.player("alice").life == 20


def test_pay_no_heed_does_not_prevent_another_sources_damage():
    scenario = _board(alice_hand=["Pay No Heed"], bob_hand=["Lightning Bolt"])
    bob_land = scenario.untapped_sources("Mountain", username="bob")[0]
    scenario.will_choose_cards(bob_land, username="alice")
    _cast(scenario, "Pay No Heed")

    _cast(scenario, "Lightning Bolt", username="bob", targets=["alice"])

    assert scenario.player("alice").life == 17


def test_pay_no_heed_can_choose_a_spell_on_the_stack():
    scenario = _board(alice_hand=["Pay No Heed"], bob_hand=["Lightning Bolt"])
    scenario.pass_priority("alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", username="bob", targets=["alice"], auto=True)
    scenario.pass_priority("bob")
    scenario.will_choose_cards(bolt, username="alice")
    scenario.cast_and_resolve("Pay No Heed", username="alice", auto=True)

    scenario.resolve_top()

    assert scenario.player("alice").life == 20


def test_pay_no_heed_does_not_follow_the_source_to_a_new_object():
    scenario = _board(
        alice_hand=["Pay No Heed"],
        bob_battlefield=["Walking Ballista"],
    )
    ballista = scenario.creature("Walking Ballista", "bob")
    scenario.game.add_counters(ballista, "+1/+1", 1)
    scenario.will_choose_cards(ballista, username="alice")
    _cast(scenario, "Pay No Heed")
    # CR 400.7: the chosen permanent leaves and comes back - a new object.
    scenario.game.return_to_hand(ballista)
    returned = scenario.put_onto_battlefield("Walking Ballista", "bob", from_zone=Zone.HAND)
    scenario.game.add_counters(returned, "+1/+1", 1)

    scenario.pass_priority("alice")
    scenario.activate(returned, index=1, username="bob", targets=["alice"])
    scenario.resolve_top()

    assert scenario.player("alice").life == 19


def test_prahv_activated_ability_shields_against_a_chosen_attacker():
    scenario = _board(
        alice_battlefield=["Prahv, Spires of Order"],
        bob_battlefield=["Hill Giant"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    prahv = scenario.find("Prahv, Spires of Order", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_cards(giant, username="alice")
    scenario.activate(
        prahv,
        *scenario.untapped_sources(*["Plains"] * 4, "Island", "Island"),
        index=1,
        username="alice",
    )
    scenario.resolve_top()

    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
    # The shield is "this turn" - on bob's turn the Giant deals its damage.
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.attack_with(giant, defending="alice")
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("alice").life == 17


def test_prahv_prevents_the_chosen_sources_damage_this_turn():
    scenario = _board(
        alice_battlefield=["Prahv, Spires of Order", "Grizzly Bears"],
        bob_battlefield=["Hill Giant"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    prahv = scenario.find("Prahv, Spires of Order", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_cards(giant, username="alice")
    scenario.activate(
        prahv,
        *scenario.untapped_sources(*["Plains"] * 4, "Island", "Island"),
        index=1,
        username="alice",
    )
    scenario.resolve_top()

    scenario.attack_with(bears, defending="bob")
    scenario.block(bears, giant)
    scenario.combat_damage()

    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0
    assert giant.damage == 2


# -- one or two target creatures ------------------------------------------------


def test_soul_parry_with_two_targets_prevents_both():
    scenario = _board(
        alice_hand=["Soul Parry"],
        bob_battlefield=["Hill Giant", "Grizzly Bears", "Savannah Lions"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    lions = scenario.creature("Savannah Lions", "bob")
    scenario.pass_priority("alice")
    scenario.advance()
    while scenario.turn.active_player != "bob":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.attack_with(giant, bears, lions, defending="alice")
    scenario.no_blocks()
    _cast(scenario, "Soul Parry", targets=[giant, bears])
    scenario.combat_damage()

    assert scenario.player("alice").life == 18  # only the Lions' 2


def test_soul_parry_with_one_target():
    scenario = _board(alice_hand=["Soul Parry"], bob_battlefield=["Walking Ballista"])
    ballista = scenario.creature("Walking Ballista", "bob")
    scenario.game.add_counters(ballista, "+1/+1", 2)
    _cast(scenario, "Soul Parry", targets=[ballista])

    scenario.pass_priority("alice")
    scenario.activate(ballista, index=1, username="bob", targets=["alice"])
    scenario.resolve_top()

    assert scenario.player("alice").life == 20


def test_soul_parry_refuses_three_targets():
    scenario = _board(
        alice_hand=["Soul Parry"],
        bob_battlefield=["Hill Giant", "Grizzly Bears", "Savannah Lions"],
    )
    creatures = [
        scenario.creature(name, "bob") for name in ("Hill Giant", "Grizzly Bears", "Savannah Lions")
    ]

    with pytest.raises(ValueError):
        scenario.cast("Soul Parry", targets=creatures)
