"""Remove a blocker from combat, unblock what only it blocked, then it blocks
an attacking creature of the ability controller's choice.

Balduvian Warlord: "{T}: Remove target blocking creature from combat.
Creatures it was blocking that hadn't become blocked by another creature this
combat become unblocked, then it blocks an attacking creature of your choice.
Activate only during the declare blockers step."

Rules (each looked up with `mise run rules:find`):

- CR 506.4: a creature an effect "specifically removes ... from combat" stops
  being "an attacking, blocking, blocked, and/or unblocked creature".
- CR 509.1h: an attacker stays blocked "even if all the creatures blocking it
  are removed from combat", and that "remains unchanged until ... an effect
  says that it becomes blocked or unblocked" - this card is such an effect,
  and its "hadn't become blocked by another creature this combat" asks about
  the combat's history, not about who is blocking right now.
- CR 608.2d: "an attacking creature of your choice" is announced while the
  effect is applied, by the ability's controller, and only among legal
  options.
- CR 509.1a/509.1b/509.1c: blocking restrictions and requirements are checked
  against "the declaration of blockers"; an effect that makes a creature block
  is not a declaration, so a flier is blockable by a creature without reach.
  CR 509.1a's "attacking that player, a planeswalker they control, or a
  battle they protect" still bounds which attacker it can be blocking.
- CR 509.3b/509.3d: "Whenever [a creature] blocks a creature" and "becomes
  blocked by a creature" trigger when "an effect causes that creature to
  block an attacking creature, but only if it wasn't already blocking that
  attacking creature at that time".
- CR 608.2b: a target that left combat is illegal, and an ability whose only
  target is illegal does nothing.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone

from .harness import Scenario


def board(*, alice=(), bob=(), carol=None) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Balduvian Warlord", "Grizzly Bears", "Hill Giant", *alice])
        .player("bob", battlefield=["Gray Ogre", *bob])
    )
    if carol is not None:
        scenario = scenario.player("carol", battlefield=list(carol))
    return scenario.build()


def to_blockers(scenario, *attackers, defending=None):
    scenario.start_at(Step.DECLARE_ATTACKERS)
    if defending is None:
        scenario.attack_with(*attackers)
    else:
        for attacker, defender in zip(attackers, defending, strict=True):
            scenario.game.declare_attackers([(attacker, defender)])
    scenario.start_at(Step.DECLARE_BLOCKERS)


def warlord_on(scenario, target, *, chosen, username="alice"):
    """Activate the Warlord at `target` and let it resolve, answering its
    CR 608.2d choice with `chosen` (None leaves it unanswered)."""
    warlord = scenario.creature("Balduvian Warlord", username)
    if chosen is not None:
        scenario.will_choose_cards(chosen, username=username, source="Balduvian Warlord")
    scenario.activate(warlord, targets=[target], username=username)
    scenario.pass_until_resolved()
    return warlord


def choice_questions(scenario):
    return [
        q
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.CHOOSE_CARDS and q.source == "Balduvian Warlord"
    ]


def test_an_attacker_blocked_only_by_the_target_becomes_unblocked_and_deals_damage():
    scenario = board()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    ogre = scenario.creature("Gray Ogre", "bob")
    to_blockers(scenario, bears, giant)
    scenario.block(giant, ogre)
    warlord_on(scenario, ogre, chosen=bears)
    assert scenario.game.is_blocked(giant) is False
    assert scenario.game.is_blocked(bears) is True
    assert scenario.blockers() == [ogre]
    assert scenario.game.combat.attack_by(bears.id).blockers == [ogre.id]
    scenario.combat_damage()
    assert scenario.player("bob").life == 20 - 3  # the unblocked Hill Giant
    assert bears.zone is Zone.GRAVEYARD  # 2/2 against the 2/2 Ogre
    assert ogre.zone is Zone.GRAVEYARD


def test_the_removed_creature_deals_and_receives_damage_with_its_new_attacker():
    scenario = board()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    ogre = scenario.creature("Gray Ogre", "bob")
    to_blockers(scenario, bears, giant)
    scenario.block(bears, ogre)
    warlord_on(scenario, ogre, chosen=giant)
    assert scenario.game.is_blocked(bears) is False
    scenario.combat_damage()
    assert ogre.zone is Zone.GRAVEYARD  # 3 from the Giant
    assert giant.damage == 2
    assert giant.zone is Zone.BATTLEFIELD
    assert scenario.player("bob").life == 20 - 2  # the unblocked Bears


def test_an_attacker_double_blocked_stays_blocked():
    scenario = board(bob=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    ogre = scenario.creature("Gray Ogre", "bob")
    bob_bears = scenario.creature("Grizzly Bears", "bob")
    to_blockers(scenario, bears, giant)
    scenario.block(giant, ogre, bob_bears)
    warlord_on(scenario, ogre, chosen=bears)
    assert scenario.game.is_blocked(giant) is True
    assert scenario.game.combat.attack_by(giant.id).blockers == [bob_bears.id]
    scenario.combat_damage()
    assert scenario.player("bob").life == 20  # nothing unblocked


def test_another_blocker_that_already_left_combat_still_keeps_the_attacker_blocked():
    """ "hadn't become blocked by another creature this combat" is history: a
    second blocker that has since left combat still counts (CR 509.1h)."""
    scenario = board(bob=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    ogre = scenario.creature("Gray Ogre", "bob")
    bob_bears = scenario.creature("Grizzly Bears", "bob")
    to_blockers(scenario, bears, giant)
    scenario.block(giant, ogre, bob_bears)
    scenario.game.combat.remove(bob_bears.id)
    warlord_on(scenario, ogre, chosen=bears)
    assert scenario.game.is_blocked(giant) is True
    assert scenario.game.combat.attack_by(giant.id).blockers == []
    scenario.combat_damage()
    assert scenario.player("bob").life == 20  # CR 509.1h: still blocked


def test_the_controller_may_choose_the_attacker_it_was_already_blocking():
    scenario = board()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    ogre = scenario.creature("Gray Ogre", "bob")
    to_blockers(scenario, bears, giant)
    scenario.block(giant, ogre)
    warlord_on(scenario, ogre, chosen=giant)
    (question,) = choice_questions(scenario)
    assert question.player == "alice"
    assert set(question.cards) == {bears.id, giant.id}
    assert question.amount == 1
    assert scenario.game.is_blocked(giant) is True
    assert scenario.game.is_blocked(bears) is False
    scenario.combat_damage()
    assert scenario.player("bob").life == 20 - 2


def test_the_choice_belongs_to_the_abilitys_controller_on_the_defending_side():
    """The Warlord on the defending side: alice moves her own blocker on bob's
    turn, and the question is hers (CR 608.2d's "you")."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Balduvian Warlord", "Gray Ogre"])
        .player("bob", battlefield=["Grizzly Bears", "Hill Giant"])
        .build()
    )
    for _ in range(3):  # alice's next turn ends the Warlord's sickness, then bob's
        scenario.turn.advance_to(Step.CLEANUP)
        scenario.advance()
    assert scenario.turn.active_player == "bob"
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    ogre = scenario.creature("Gray Ogre", "alice")
    to_blockers(scenario, bears, giant)
    scenario.block(bears, ogre)
    scenario.pass_priority("bob")
    warlord_on(scenario, ogre, chosen=giant, username="alice")
    (question,) = choice_questions(scenario)
    assert question.player == "alice"
    assert scenario.game.is_blocked(giant) is True
    assert scenario.game.is_blocked(bears) is False
    scenario.combat_damage()
    assert scenario.player("alice").life == 20 - 2


def test_an_effect_block_ignores_blocking_restrictions():
    """Serra Angel flies, and Gray Ogre could never be declared as its
    blocker (CR 509.1b); the Warlord's block is not a declaration."""
    scenario = board(alice=["Serra Angel"])
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "alice")
    ogre = scenario.creature("Gray Ogre", "bob")
    to_blockers(scenario, bears, angel)
    with pytest.raises(ValueError):
        scenario.block(angel, ogre)
    scenario.block(bears, ogre)
    warlord_on(scenario, ogre, chosen=angel)
    assert scenario.game.is_blocked(angel) is True
    assert scenario.game.combat.attack_by(angel.id).blockers == [ogre.id]
    scenario.combat_damage()
    assert scenario.player("bob").life == 20 - 2  # the Bears, now unblocked
    assert ogre.zone is Zone.GRAVEYARD


def test_only_attackers_attacking_the_blockers_controller_are_offered():
    """CR 509.1a: a creature only ever blocks a creature attacking its
    controller (or what they control or protect) - in a three-player game the
    attacker aimed at carol is not an option for bob's Ogre."""
    scenario = board(carol=[])
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    ogre = scenario.creature("Gray Ogre", "bob")
    to_blockers(scenario, bears, giant, defending=["bob", "carol"])
    scenario.game.declare_blockers([(ogre, bears)])
    warlord_on(scenario, ogre, chosen=bears)
    (question,) = choice_questions(scenario)
    assert question.cards == (bears.id,)


def test_an_effect_block_triggers_blocks_a_creature_abilities():
    """CR 509.3b: Ashmouth Hound's "Whenever this creature blocks ... a
    creature" triggers again when the effect makes it block a new attacker."""
    scenario = board(bob=["Ashmouth Hound"])
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    hound = scenario.creature("Ashmouth Hound", "bob")
    to_blockers(scenario, bears, giant)
    scenario.block(giant, hound)
    scenario.pass_until_resolved()  # the declaration's own trigger at the Giant
    assert giant.damage == 1
    warlord_on(scenario, hound, chosen=bears)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert bears.damage == 1


def test_it_cannot_be_activated_outside_the_declare_blockers_step():
    scenario = board()
    bears = scenario.creature("Grizzly Bears", "alice")
    warlord = scenario.creature("Balduvian Warlord", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    refusal = scenario.why_cannot_activate(warlord)
    assert refusal is not None and "declare blockers step" in refusal
    with pytest.raises(ValueError):
        scenario.activate(warlord, targets=[bears])
    assert warlord.tapped is False


def test_a_target_that_left_combat_fizzles_and_nobody_is_asked():
    scenario = board()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    ogre = scenario.creature("Gray Ogre", "bob")
    warlord = scenario.creature("Balduvian Warlord", "alice")
    to_blockers(scenario, bears, giant)
    scenario.block(giant, ogre)
    scenario.activate(warlord, targets=[ogre])
    scenario.game.combat.remove(ogre.id)  # removed in response
    scenario.pass_until_resolved()
    assert choice_questions(scenario) == []
    assert scenario.game.is_blocked(giant) is True  # CR 509.1h, no unblocking
    assert scenario.blockers() == []
    scenario.combat_damage()
    assert scenario.player("bob").life == 20 - 2
