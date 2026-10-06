"""Scenario: "The next N damage that a source of your choice would deal to you
and/or <permanents | creatures> you control this turn is dealt to any target
instead." - a CR 614.9 redirection shield, counted like CR 615.7's.

Rules, each read in full with `mise run rules:find`:

- CR 614.9 - "Some effects replace damage dealt to one battle, creature,
  planeswalker, or player with the same damage dealt to another battle,
  creature, planeswalker, or player; such effects are called redirection
  effects. If one of those permanents is no longer on the battlefield when the
  damage would be redirected, or is no longer a battle, creature, or
  planeswalker when the damage would be redirected, the effect does nothing.
  If damage would be redirected to or from a player who has left the game, the
  effect does nothing."
- CR 615.7 - "... Such effects count only the amount of damage; the number of
  events or sources dealing it doesn't matter." - the shield accounting the
  "next N damage" wording shares.
- CR 609.7a - the source is chosen as the effect is created (a permanent, or a
  spell on the stack).
- CR 115.4 - "any target" is a creature, player, planeswalker or battle,
  chosen as the spell is cast.
- CR 608.2b - a spell whose only target is illegal on resolution does nothing.

Listed printing: Harm's Way. Proof printing (not listed, in no api deck, legal
in Modern): Shining Shoal - "The next X damage that a source of your choice
would deal to you and/or creatures you control this turn is dealt to any
target instead." (CR 107.3a's X, and creatures rather than permanents).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario


@pytest.mark.parametrize("name", ["Harm's Way", "Shining Shoal"])
def test_every_listed_and_proof_card_reads_handled(name):
    outcomes = {clause.outcome for clause in card_support(card(name)).clauses}
    assert outcomes == {"handled"}, name


def _board(*, alice_hand=(), alice_battlefield=(), bob_hand=(), bob_battlefield=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=[*["Plains"] * 4, *alice_battlefield],
            library=["Plains"] * 10,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=[*["Mountain"] * 4, *bob_battlefield],
            library=["Mountain"] * 10,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _ballista(scenario, counters):
    ballista = scenario.creature("Walking Ballista", "bob")
    scenario.game.add_counters(ballista, "+1/+1", counters)
    return ballista


def _ping(scenario, ballista, target):
    if scenario.priority_holder != "bob":
        scenario.pass_priority(scenario.priority_holder)
    scenario.activate(ballista, index=1, username="bob", targets=[target])
    scenario.resolve_top()


def _harms_way(scenario, *, chosen, target, name="Harm's Way", x=None):
    if scenario.priority_holder != "alice":
        scenario.pass_priority(scenario.priority_holder)
    scenario.will_choose_cards(chosen, username="alice")
    if x is None:
        return scenario.cast_and_resolve(name, username="alice", targets=[target], auto=True)
    scenario.game.cast(
        scenario.find(name, Zone.HAND, "alice"),
        "alice",
        x_value=x,
        targets=[scenario.player(target) if isinstance(target, str) else target],
        mana_sources=scenario.untapped_sources(*["Plains"] * (x + 2), username="alice"),
    )
    return scenario.resolve_top()


# -- Harm's Way ---------------------------------------------------------------


def test_the_next_two_damage_to_you_go_to_the_target_instead():
    scenario = _board(alice_hand=["Harm's Way"], bob_battlefield=["Walking Ballista"])
    ballista = _ballista(scenario, 4)
    _harms_way(scenario, chosen=ballista, target="bob")

    _ping(scenario, ballista, "alice")
    _ping(scenario, ballista, "alice")
    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 18
    _ping(scenario, ballista, "alice")  # the 2 are spent: dealt normally

    assert scenario.player("alice").life == 19
    assert scenario.player("bob").life == 18


def test_one_bigger_event_is_split_two_redirected_the_rest_dealt():
    scenario = _board(
        alice_hand=["Harm's Way"],
        bob_hand=["Lightning Bolt"],
        bob_battlefield=["Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.pass_priority("alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", username="bob", targets=["alice"], auto=True)
    scenario.pass_priority("bob")
    _harms_way(scenario, chosen=bolt, target=bears)

    scenario.resolve_top()

    assert scenario.player("alice").life == 19
    assert bears.zone is Zone.GRAVEYARD  # 2 damage, from the Bolt


def test_damage_to_a_permanent_you_control_is_redirected_too():
    scenario = _board(
        alice_hand=["Harm's Way"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Walking Ballista"],
    )
    giant = scenario.creature("Hill Giant", "alice")
    ballista = _ballista(scenario, 3)
    _harms_way(scenario, chosen=ballista, target="bob")

    _ping(scenario, ballista, giant)
    _ping(scenario, ballista, "alice")
    _ping(scenario, ballista, giant)

    assert giant.damage == 1
    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 18


def test_another_sources_damage_is_not_redirected():
    scenario = _board(
        alice_hand=["Harm's Way"],
        bob_hand=["Lightning Bolt"],
        bob_battlefield=["Walking Ballista"],
    )
    ballista = _ballista(scenario, 2)
    _harms_way(scenario, chosen=ballista, target="bob")

    scenario.pass_priority("alice")
    scenario.cast_and_resolve("Lightning Bolt", username="bob", targets=["alice"], auto=True)

    assert scenario.player("alice").life == 17
    assert scenario.player("bob").life == 20


def test_damage_to_an_opponents_permanent_is_not_redirected():
    scenario = _board(
        alice_hand=["Harm's Way"],
        bob_battlefield=["Walking Ballista", "Hill Giant"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    ballista = _ballista(scenario, 2)
    _harms_way(scenario, chosen=ballista, target="bob")

    _ping(scenario, ballista, giant)

    assert giant.damage == 1
    assert scenario.player("bob").life == 20


def test_a_redirect_target_gone_when_the_damage_comes_does_nothing():
    """CR 614.9: the creature it would be redirected to has left the
    battlefield, so the damage is dealt where it was going."""
    scenario = _board(
        alice_hand=["Harm's Way"],
        bob_hand=["Lightning Bolt"],
        bob_battlefield=["Walking Ballista", "Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    ballista = _ballista(scenario, 2)
    _harms_way(scenario, chosen=ballista, target=bears)
    scenario.game.destroy(bears)

    _ping(scenario, ballista, "alice")

    assert scenario.player("alice").life == 19


def test_an_illegal_target_on_resolution_means_no_redirection():
    """CR 608.2b: Harm's Way's only target is gone, so it does nothing."""
    scenario = _board(
        alice_hand=["Harm's Way"],
        bob_battlefield=["Walking Ballista", "Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    ballista = _ballista(scenario, 2)
    scenario.will_choose_cards(ballista, username="alice")
    scenario.cast_onto_stack("Harm's Way", username="alice", targets=[bears], auto=True)
    scenario.game.destroy(bears)
    scenario.resolve_top()

    _ping(scenario, ballista, "alice")

    assert scenario.player("alice").life == 19
    assert not scenario.game.created_replacements


def test_the_chosen_source_may_be_a_spell_on_the_stack():
    scenario = _board(alice_hand=["Harm's Way"], bob_hand=["Shock"])
    scenario.pass_priority("alice")
    shock = scenario.cast_onto_stack("Shock", username="bob", targets=["alice"], auto=True)
    scenario.pass_priority("bob")
    _harms_way(scenario, chosen=shock, target="bob")

    scenario.resolve_top()

    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 18


# -- Shining Shoal: the X twin, creatures only --------------------------------


def test_shining_shoal_redirects_the_next_x_damage():
    scenario = _board(alice_hand=["Shining Shoal"], bob_battlefield=["Walking Ballista"])
    ballista = _ballista(scenario, 4)
    _harms_way(scenario, chosen=ballista, target="bob", name="Shining Shoal", x=1)

    _ping(scenario, ballista, "alice")
    _ping(scenario, ballista, "alice")

    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 19


def test_shining_shoal_covers_your_creatures():
    scenario = _board(
        alice_hand=["Shining Shoal"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Walking Ballista", "Grizzly Bears"],
    )
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    ballista = _ballista(scenario, 3)
    _harms_way(scenario, chosen=ballista, target=bears, name="Shining Shoal", x=2)

    _ping(scenario, ballista, giant)
    _ping(scenario, ballista, giant)

    assert giant.damage == 0
    assert bears.zone is Zone.GRAVEYARD
