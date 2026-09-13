"""The attacking player assigns a blocked creature's combat damage.

Battle report B4-06: Sire of Seven Deaths (7/7 first strike, trample, lifelink,
menace) was double-blocked; bob was never asked, and the engine divided the
damage itself. No assignment decision existed at all.

Rules read in full with `mise run rules:find` this session:

- **CR 703.4k** - "Immediately after the combat damage step begins, each player
  in APNAP order announces how each attacking or blocking creature they control
  assigns its combat damage."
- **CR 510.1a** - "Each attacking creature and each blocking creature assigns
  combat damage equal to its power."
- **CR 510.1c** - "If exactly one creature is blocking it, it assigns all its
  combat damage to that creature. If two or more creatures are blocking it, it
  assigns its combat damage to those creatures divided as its controller
  chooses among them." There is no damage assignment order in this rule: any
  division among the blockers is legal.
- **CR 702.19b** - "Once all those blocking creatures are assigned lethal
  damage, any excess damage is assigned as its controller chooses among those
  blocking creatures and the player ... the creature is attacking. When
  checking for assigned lethal damage, take into account damage already marked
  on the creature and damage from other creatures that's being assigned during
  the same combat damage step ... The attacking creature's controller need not
  assign lethal damage to all those blocking creatures but in that case can't
  assign any damage to the player".
- **CR 702.2c** - "Any nonzero amount of combat damage assigned to a creature by
  a source with deathtouch is considered to be lethal damage".
- **CR 510.1e** - the total assignment is checked; an illegal one is refused.

An unpaused, unscripted seat still gets the engine's documented default (lethal
to each blocker in declaration order, the rest through with trample); a paused
seat is asked.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import (
    Answer,
    DamageAssignment,
    DecisionKind,
    DecisionPending,
)
from magic_cards_model.models import Game, Zone
from tests.scenarios.harness import Scenario


def _combat(attacker: str, *blockers: str, alice_extra=(), bob_extra=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=[attacker, *alice_extra])
        .player("bob", battlefield=[*blockers, *bob_extra])
        .build()
    )
    return scenario


def _declare(scenario, attacker_name: str, *blocker_names: str):
    scenario.start_at(Step.DECLARE_ATTACKERS)
    attacker = scenario.creature(attacker_name, "alice")
    blockers = [scenario.creature(name, "bob") for name in blocker_names]
    scenario.attack_with(attacker)
    scenario.block(attacker, *blockers)
    return attacker, blockers


def _assignment_questions(scenario):
    return [d for d in scenario.questions_asked() if d.kind is DecisionKind.ASSIGN_COMBAT_DAMAGE]


def test_a_double_blocked_trampler_is_asked_and_may_put_everything_on_the_blockers():
    scenario = _combat("Colossal Dreadmaw", "Grizzly Bears", "Hill Giant")
    dreadmaw, (bears, giant) = _declare(
        scenario, "Colossal Dreadmaw", "Grizzly Bears", "Hill Giant"
    )
    scenario.will_assign_combat_damage((bears, 3), (giant, 3))

    scenario.combat_damage()

    (question,) = _assignment_questions(scenario)
    assert question.player == "alice"
    assert question.cards[0] == dreadmaw.id
    assert question.amount == 6
    assert {ref.card_id for ref in question.targets if ref.card_id} == {bears.id, giant.id}
    assert any(ref.username == "bob" for ref in question.targets), "trample may reach bob"
    assert bears.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 20


def test_the_lethal_amounts_travel_with_the_question():
    scenario = _combat("Colossal Dreadmaw", "Grizzly Bears", "Hill Giant")
    _dreadmaw, (bears, giant) = _declare(
        scenario, "Colossal Dreadmaw", "Grizzly Bears", "Hill Giant"
    )

    scenario.combat_damage()

    (question,) = _assignment_questions(scenario)
    lethal = dict(
        zip([ref.card_id for ref in question.targets], question.lethal_damage, strict=True)
    )
    assert lethal[bears.id] == 2
    assert lethal[giant.id] == 3


def test_trample_damage_to_the_player_needs_lethal_on_every_blocker_first():
    scenario = _combat("Colossal Dreadmaw", "Grizzly Bears", "Hill Giant")
    _dreadmaw, (bears, giant) = _declare(
        scenario, "Colossal Dreadmaw", "Grizzly Bears", "Hill Giant"
    )
    scenario.will_assign_combat_damage((bears, 1), (giant, 3), ("bob", 2))

    with pytest.raises(ValueError, match="702.19b"):
        scenario.combat_damage()


def test_the_unscripted_default_is_lethal_in_order_then_the_player():
    scenario = _combat("Colossal Dreadmaw", "Grizzly Bears", "Hill Giant")
    _dreadmaw, (bears, giant) = _declare(
        scenario, "Colossal Dreadmaw", "Grizzly Bears", "Hill Giant"
    )

    assigned = scenario.combat_damage()

    assert (bears, 2) in assigned
    assert (giant, 3) in assigned
    assert scenario.player("bob").life == 19


def test_a_non_trampler_divides_among_its_blockers_in_any_way():
    """CR 510.1c: all six on the Spider is legal; the Watchwolf takes nothing."""
    scenario = _combat("Craw Wurm", "Watchwolf", "Giant Spider")
    _wurm, (wolf, spider) = _declare(scenario, "Craw Wurm", "Watchwolf", "Giant Spider")
    scenario.will_assign_combat_damage((spider, 6))

    scenario.combat_damage()

    assert spider.zone is Zone.GRAVEYARD
    assert wolf.zone is Zone.BATTLEFIELD
    assert wolf.damage == 0


def test_a_non_trampler_cannot_assign_to_the_player():
    scenario = _combat("Craw Wurm", "Watchwolf", "Giant Spider")
    _wurm, (wolf, spider) = _declare(scenario, "Craw Wurm", "Watchwolf", "Giant Spider")
    scenario.will_assign_combat_damage((wolf, 3), (spider, 2), ("bob", 1))

    with pytest.raises(ValueError, match="510.1c"):
        scenario.combat_damage()


def test_the_assignment_must_total_the_creatures_power():
    scenario = _combat("Colossal Dreadmaw", "Grizzly Bears", "Hill Giant")
    _dreadmaw, (bears, giant) = _declare(
        scenario, "Colossal Dreadmaw", "Grizzly Bears", "Hill Giant"
    )
    scenario.will_assign_combat_damage((bears, 2), (giant, 2))

    with pytest.raises(ValueError, match="510.1a"):
        scenario.combat_damage()


def test_a_single_blocker_without_trample_is_not_asked():
    """CR 510.1c: exactly one blocker takes all of it - there is nothing to choose."""
    scenario = _combat("Craw Wurm", "Watchwolf")
    _declare(scenario, "Craw Wurm", "Watchwolf")

    scenario.combat_damage()

    assert _assignment_questions(scenario) == []


def test_a_trampler_with_one_blocker_is_asked_how_much_goes_through():
    """CR 702.19b: excess may stay on the blocker."""
    scenario = _combat("Colossal Dreadmaw", "Grizzly Bears")
    _dreadmaw, (bears,) = _declare(scenario, "Colossal Dreadmaw", "Grizzly Bears")
    scenario.will_assign_combat_damage((bears, 6))

    scenario.combat_damage()

    assert len(_assignment_questions(scenario)) == 1
    assert scenario.player("bob").life == 20


def test_deathtouch_makes_one_damage_lethal_before_trample():
    """CR 702.2c: Questing Beast with Monstrous Rage (7/5 deathtouch, trample)
    needs only 1 on each blocker before the rest reaches bob."""
    scenario = (
        Scenario()
        .player("alice", hand=["Monstrous Rage"], battlefield=["Questing Beast", "Mountain"])
        .player("bob", battlefield=["Watchwolf", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    beast = scenario.creature("Questing Beast", "alice")
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Monstrous Rage", mountain, targets=[beast])
    _beast, (wolf, giant) = _declare(scenario, "Questing Beast", "Watchwolf", "Hill Giant")
    scenario.will_assign_combat_damage((wolf, 1), (giant, 1), ("bob", 5))

    scenario.combat_damage()

    assert wolf.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 15


def test_a_deathtouch_blocker_still_needs_its_full_lethal_before_trample():
    """Sheoldred's deathtouch kills the Dreadmaw, but lethal *to Sheoldred* is
    still her toughness: 2 to the Bears and 3 to her is not enough to trample."""
    scenario = _combat("Colossal Dreadmaw", "Sheoldred, the Apocalypse", "Grizzly Bears")
    dreadmaw, (sheoldred, bears) = _declare(
        scenario, "Colossal Dreadmaw", "Sheoldred, the Apocalypse", "Grizzly Bears"
    )
    scenario.will_assign_combat_damage((bears, 2), (sheoldred, 3), ("bob", 1))

    with pytest.raises(ValueError, match="702.19b"):
        scenario.combat_damage()


def test_a_deathtouch_blocker_kills_the_trampler_that_assigned_everything_to_it():
    scenario = _combat("Colossal Dreadmaw", "Sheoldred, the Apocalypse", "Grizzly Bears")
    dreadmaw, (sheoldred, bears) = _declare(
        scenario, "Colossal Dreadmaw", "Sheoldred, the Apocalypse", "Grizzly Bears"
    )
    scenario.will_assign_combat_damage((sheoldred, 5), (bears, 1))

    scenario.combat_damage()

    assert sheoldred.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD
    assert dreadmaw.zone is Zone.GRAVEYARD


def test_damage_already_marked_counts_toward_lethal():
    """CR 702.19b: a Giant Spider already dealt 2 needs only 2 more."""
    scenario = (
        Scenario()
        .player("alice", hand=["Shock"], battlefield=["Colossal Dreadmaw", "Mountain"])
        .player("bob", battlefield=["Giant Spider", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spider = scenario.creature("Giant Spider", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Shock", mountain, targets=[spider])
    _dreadmaw, (spider, bears) = _declare(
        scenario, "Colossal Dreadmaw", "Giant Spider", "Grizzly Bears"
    )
    scenario.will_assign_combat_damage((spider, 2), (bears, 2), ("bob", 2))

    scenario.combat_damage()

    assert spider.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 18


def test_a_paused_seat_is_asked_and_the_tape_replays_its_assignment():
    scenario = _combat("Colossal Dreadmaw", "Grizzly Bears", "Hill Giant")
    _dreadmaw, (bears, giant) = _declare(
        scenario, "Colossal Dreadmaw", "Grizzly Bears", "Hill Giant"
    )
    scenario.game.decisions.begin_replay([])
    snapshot = scenario.game.model_dump(mode="json")
    scenario.game.decisions.pause_when_unanswered = True

    with pytest.raises(DecisionPending) as excinfo:
        scenario.combat_damage()

    pending = excinfo.value.pending
    assert pending.decision.kind is DecisionKind.ASSIGN_COMBAT_DAMAGE
    assert "510.1" in pending.rule

    restored = Game.model_validate(snapshot)
    restored.decisions.begin_replay(
        [
            Answer(
                seq=pending.seq,
                kind=DecisionKind.ASSIGN_COMBAT_DAMAGE,
                player="alice",
                damage=(
                    DamageAssignment(target_card=bears.id, amount=2),
                    DamageAssignment(target_card=giant.id, amount=4),
                ),
            )
        ]
    )
    restored.combat_damage()
    restored.decisions.finish_replay()

    assert restored.find_by_id(bears.id).zone is Zone.GRAVEYARD
    assert restored.find_by_id(giant.id).zone is Zone.GRAVEYARD
    assert restored.player("bob").life == 20


def test_the_reported_double_block_on_sire_of_seven_deaths():
    """B4-06 as played: bob's Sire (first strike, trample, lifelink, menace)
    double-blocked; bob keeps all seven on the blockers."""
    scenario = (
        Scenario()
        .player("bob", battlefield=["Sire of Seven Deaths"])
        .player("alice", battlefield=["Sowing Mycospawn", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    sire = scenario.creature("Sire of Seven Deaths", "bob")
    mycospawn = scenario.creature("Sowing Mycospawn", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(sire)
    scenario.block(sire, mycospawn, bears)
    scenario.will_assign_combat_damage((mycospawn, 5), (bears, 2), username="bob")

    scenario.combat_damage()

    (question,) = _assignment_questions(scenario)
    assert question.player == "bob"
    assert mycospawn.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 27
