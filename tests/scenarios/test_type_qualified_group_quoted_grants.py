"""Scenario: a static ability that hands a card-type-qualified group a quoted
ability - Antagonist Incorporator's and Hive Mind Coprocessor's "Artifact
creatures you control have "Whenever this creature deals combat damage to a
player, ..."", with Ghired, Mirror of the Wilds' "Nontoken creatures you control
have "{T}: ..."" as the differently worded printing (a "nontoken" qualifier in
place of a card type, an activated ability in place of a trigger).

Rules, looked up with `mise run rules:find` in the session that wrote this:

- CR 113.10 / 113.10a: an effect that adds an ability may carry the ability's
  own activation instructions; the quoted ability is the ability itself.
- CR 613.1f: the grant is a layer 6 effect, applied after layer 4's type changes
  (CR 613.1d), so an object that is an artifact creature only because of a type
  effect is still in the group.
- CR 611.3a: the group is not locked in; an object that stops matching stops
  having the ability, and one that starts matching gets it.
- CR 611.3b: the effect applies only while the source is on the battlefield.
- CR 111.1: a token is a marker for a permanent not represented by a card, which
  is what "nontoken" tells apart.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.token import create_predefined_tokens
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario

BORG_TRIGGER = (
    "Whenever this creature deals combat damage to a player, you may pay {1}. If you do, "
    "create a 1/1 colorless Borg artifact creature token."
)
DRAW_TRIGGER = (
    "Whenever this creature deals combat damage to a player, you may pay 1 life. "
    "If you do, draw a card."
)


def _board(alice=(), bob=(), *, alice_library=("Forest",) * 5, step=Step.PRECOMBAT_MAIN):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=list(alice), library=list(alice_library))
        .player("bob", battlefield=list(bob), library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(step)
    return scenario


def _abilities(scenario, permanent) -> tuple[str, ...]:
    return scenario.game.characteristics_of(permanent).abilities


def _hit_face(scenario, attacker) -> None:
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacker, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()


def _tokens(scenario, username="alice"):
    return [s for s in scenario.game.battlefield if s.token and s.controller == username]


@pytest.mark.parametrize(
    "name", ["Antagonist Incorporator", "Hive Mind Coprocessor", "Ghired, Mirror of the Wilds"]
)
def test_the_whole_card_is_handled(name):
    bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
    assert not bad, bad


# --------------------------------------------------------------------------
# Who is in the group
# --------------------------------------------------------------------------


def test_every_artifact_creature_you_control_has_the_trigger_including_the_source():
    scenario = _board(["Antagonist Incorporator", "Memnite", "Grizzly Bears"], ["Sliver Construct"])
    incorporator = scenario.creature("Antagonist Incorporator", "alice")
    memnite = scenario.creature("Memnite", "alice")
    assert BORG_TRIGGER in _abilities(scenario, incorporator)
    assert BORG_TRIGGER in _abilities(scenario, memnite)


def test_a_nonartifact_creature_and_an_opponents_artifact_creature_get_nothing():
    scenario = _board(["Antagonist Incorporator", "Grizzly Bears"], ["Sliver Construct"])
    bears = scenario.creature("Grizzly Bears", "alice")
    construct = scenario.creature("Sliver Construct", "bob")
    assert BORG_TRIGGER not in _abilities(scenario, bears)
    assert BORG_TRIGGER not in _abilities(scenario, construct)


def test_a_noncreature_artifact_is_not_in_the_group():
    """ "Artifact creatures" needs both types (CR 205.2a lists them separately,
    an object satisfies the group only with both)."""
    scenario = _board(["Antagonist Incorporator", "Sol Ring"])
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    assert BORG_TRIGGER not in _abilities(scenario, ring)


def test_a_noncreature_artifact_token_is_not_in_the_group():
    scenario = _board(["Antagonist Incorporator", "Grizzly Bears"])
    (treasure,) = create_predefined_tokens(scenario.game, "Treasure", "alice")
    assert BORG_TRIGGER not in _abilities(scenario, treasure)


def test_the_group_follows_the_layers_a_creature_made_an_artifact_joins_it():
    """CR 613.1d runs before CR 613.1f: Mycosynth Lattice makes Grizzly Bears an
    artifact in layer 4, so layer 6 hands it the trigger; without the Lattice
    it has nothing."""
    plain = _board(["Antagonist Incorporator", "Grizzly Bears"])
    assert BORG_TRIGGER not in _abilities(plain, plain.creature("Grizzly Bears", "alice"))
    latticed = _board(["Antagonist Incorporator", "Grizzly Bears", "Mycosynth Lattice"])
    assert BORG_TRIGGER in _abilities(latticed, latticed.creature("Grizzly Bears", "alice"))


def test_the_grant_goes_when_the_source_leaves():
    scenario = _board(["Antagonist Incorporator", "Memnite"])
    memnite = scenario.creature("Memnite", "alice")
    assert BORG_TRIGGER in _abilities(scenario, memnite)
    scenario.game.destroy(scenario.find("Antagonist Incorporator", Zone.BATTLEFIELD, "alice"))
    assert BORG_TRIGGER not in _abilities(scenario, memnite)


def test_two_different_sources_stack_two_grants_on_one_creature():
    scenario = _board(["Antagonist Incorporator", "Hive Mind Coprocessor", "Memnite"])
    memnite = scenario.creature("Memnite", "alice")
    assert BORG_TRIGGER in _abilities(scenario, memnite)
    assert DRAW_TRIGGER in _abilities(scenario, memnite)


# --------------------------------------------------------------------------
# The granted triggers really trigger and resolve
# --------------------------------------------------------------------------


def test_paying_one_mana_after_combat_damage_makes_a_borg_token():
    scenario = _board(["Antagonist Incorporator", "Memnite", "Plains"])
    memnite = scenario.creature("Memnite", "alice")
    scenario.will_pay_the_mana_cost(True)
    _hit_face(scenario, memnite)
    (borg,) = _tokens(scenario)
    chars = scenario.game.characteristics_of(borg)
    assert borg.name == "Borg Token" or "Borg" in chars.subtypes
    assert (chars.power, chars.toughness) == (1, 1)
    assert scenario.player("bob").life == 19


def test_declining_the_payment_makes_no_token():
    scenario = _board(["Antagonist Incorporator", "Memnite", "Plains"])
    memnite = scenario.creature("Memnite", "alice")
    scenario.will_pay_the_mana_cost(False)
    _hit_face(scenario, memnite)
    assert _tokens(scenario) == []


def test_no_mana_to_pay_makes_no_token():
    scenario = _board(["Antagonist Incorporator", "Memnite"])
    memnite = scenario.creature("Memnite", "alice")
    _hit_face(scenario, memnite)
    assert _tokens(scenario) == []


def test_a_blocked_artifact_creature_does_not_trigger():
    """The trigger is combat damage to a *player* (CR 510.2 assigns it to the
    blocker instead)."""
    scenario = _board(["Antagonist Incorporator", "Memnite", "Plains"], ["Sliver Construct"])
    memnite = scenario.creature("Memnite", "alice")
    construct = scenario.creature("Sliver Construct", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(memnite, defending="bob")
    scenario.block(memnite, construct)
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    assert scenario.game.stack_is_empty
    assert _tokens(scenario) == []


def test_the_borg_token_is_itself_an_artifact_creature_with_the_trigger():
    scenario = _board(["Antagonist Incorporator", "Memnite", "Plains"])
    memnite = scenario.creature("Memnite", "alice")
    scenario.will_pay_the_mana_cost(True)
    _hit_face(scenario, memnite)
    (borg,) = _tokens(scenario)
    assert BORG_TRIGGER in _abilities(scenario, borg)


def test_hive_mind_pays_a_life_to_draw():
    scenario = _board(
        ["Hive Mind Coprocessor", "Memnite"], alice_library=("Forest", "Island", "Swamp")
    )
    memnite = scenario.creature("Memnite", "alice")
    hand_before = len(scenario.player("alice").hand)
    scenario.will_pay_the_life(True)
    _hit_face(scenario, memnite)
    assert len(scenario.player("alice").hand) == hand_before + 1
    assert scenario.player("alice").life == 19


def test_hive_mind_declined_draws_nothing_and_keeps_the_life():
    scenario = _board(["Hive Mind Coprocessor", "Memnite"])
    memnite = scenario.creature("Memnite", "alice")
    hand_before = len(scenario.player("alice").hand)
    scenario.will_pay_the_life(False)
    _hit_face(scenario, memnite)
    assert len(scenario.player("alice").hand) == hand_before
    assert scenario.player("alice").life == 20


# --------------------------------------------------------------------------
# Second printing: a "nontoken" qualifier and an activated ability (Ghired)
# --------------------------------------------------------------------------

GHIRED_ABILITY = (
    "{T}: Create a token that's a copy of target token you control that entered this turn."
)


def test_ghired_gives_every_nontoken_creature_you_control_the_ability():
    scenario = _board(["Ghired, Mirror of the Wilds", "Grizzly Bears"], ["Hill Giant"])
    assert GHIRED_ABILITY in _abilities(scenario, scenario.creature("Grizzly Bears", "alice"))
    assert GHIRED_ABILITY in _abilities(
        scenario, scenario.creature("Ghired, Mirror of the Wilds", "alice")
    )
    assert GHIRED_ABILITY not in _abilities(scenario, scenario.creature("Hill Giant", "bob"))


def test_ghired_gives_a_creature_token_nothing():
    scenario = _board(
        ["Ghired, Mirror of the Wilds", "Antagonist Incorporator", "Memnite", "Plains"]
    )
    memnite = scenario.creature("Memnite", "alice")
    scenario.will_pay_the_mana_cost(True)
    _hit_face(scenario, memnite)
    (borg,) = _tokens(scenario)
    assert GHIRED_ABILITY not in _abilities(scenario, borg)
    assert GHIRED_ABILITY in _abilities(scenario, memnite)


def test_a_granted_copy_ability_copies_a_token_that_entered_this_turn():
    scenario = _board(["Ghired, Mirror of the Wilds", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    (treasure,) = create_predefined_tokens(scenario.game, "Treasure", "alice")
    ability = [
        i
        for i, a in enumerate(scenario.game.activated_abilities(bears))
        if a.effect.startswith("Create a token that's a copy")
    ]
    assert ability, [a.effect for a in scenario.game.activated_abilities(bears)]
    scenario.activate(bears, index=ability[0], targets=[treasure])
    scenario.pass_until_resolved()
    treasures = [s for s in _tokens(scenario) if s.name == treasure.name]
    assert len(treasures) == 2
