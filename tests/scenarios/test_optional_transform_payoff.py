""" "You may transform `<this>`. If you do, `<effects>`." - an optional
self-transform whose payoff happens only when the permanent actually turned
over.

CR 701.27a: "To transform a permanent, turn it over so that its other face is
up." CR 701.27f: "If an activated or triggered ability of a permanent that
isn't a delayed triggered ability of that permanent tries to transform it, the
permanent does so only if it hasn't transformed or converted since the ability
was put onto the stack. ... if the permanent has already transformed or
converted, an instruction to do either is ignored." CR 603.5: the "may" is
chosen as the ability resolves, and CR 608.2d: "The player can't choose an
option that's illegal or impossible" - so when the transform cannot happen,
nothing is asked and nothing follows.

Two printings, both legal in Modern, Pioneer and Standard or Modern:

- Aang, Master of Elements (Avatar Aang's back face): "At the beginning of each
  upkeep, you may transform Aang, Master of Elements. If you do, you gain 4
  life, draw four cards, put four +1/+1 counters on him, and he deals 4 damage
  to each opponent." - the self by name (CR 201.5), a serial list of four
  instructions, and a legend's own "him"/"he".
- Soul Seizer (the second printing, in no deck list here): "When this creature
  deals combat damage to a player, you may transform it. If you do, attach it to
  target creature that player controls." - the self as "it", a targeted
  payoff, and a target restricted by the trigger's own event ("that player" is
  the one dealt the damage). Its back face Ghastly Haunting is an Aura: "Enchant
  creature / You control enchanted creature."

Every CR number here was read whole with `mise run rules:find`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import transform_permanent
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

AANG = "Avatar Aang"
MASTER = "Aang, Master of Elements"


def _aang_at_upkeep(
    *, bob_battlefield: list[str] | None = None, alice_hand: list[str] | None = None
):
    """Alice controls Aang with his back face up, at the start of her own
    turn; advancing once enters her upkeep and fires the trigger."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Island"] * 10,
            hand=alice_hand or [],
            battlefield=[AANG, "Island", "Island"],
        )
        .player("bob", library=["Island"] * 10, battlefield=bob_battlefield or [])
        .build()
    )
    aang = scenario.creature(AANG, "alice")
    aang.transform()  # staging the back face up (CR 701.27a)
    assert aang.name == MASTER
    return scenario, aang


def _enter_upkeep(scenario) -> None:
    scenario.advance()
    assert scenario.step is Step.UPKEEP
    scenario.game.put_triggers_on_stack()


def _resolve_all(scenario) -> None:
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()


def test_taking_the_transform_does_all_four_things():
    scenario, aang = _aang_at_upkeep()
    scenario.will_take_the_may(True)
    hand_before = len(scenario.player("alice").hand)

    _enter_upkeep(scenario)
    _resolve_all(scenario)

    assert aang.name == AANG
    assert scenario.player("alice").life == 24
    assert len(scenario.player("alice").hand) == hand_before + 4
    # Four +1/+1 counters on him - now the 4/4 front face (CR 712.8d).
    assert (aang.power, aang.toughness) == (8, 8)
    assert scenario.player("bob").life == 16


def test_declining_does_nothing_at_all():
    scenario, aang = _aang_at_upkeep()
    scenario.will_take_the_may(False)
    hand_before = len(scenario.player("alice").hand)

    _enter_upkeep(scenario)
    _resolve_all(scenario)

    assert aang.name == MASTER
    assert scenario.player("alice").life == 20
    assert len(scenario.player("alice").hand) == hand_before
    assert (aang.power, aang.toughness) == (6, 6)
    assert scenario.player("bob").life == 20


def test_it_triggers_in_an_opponents_upkeep_too():
    """ "Each upkeep": bob's upkeep fires it as well, and "each opponent" is
    still alice's opponent, bob."""
    scenario, aang = _aang_at_upkeep()
    scenario.will_take_the_may(False)
    _enter_upkeep(scenario)
    _resolve_all(scenario)
    while not (scenario.turn.active_player == "bob" and scenario.step is Step.UNTAP):
        _resolve_all(scenario)
        scenario.advance()
    scenario.will_take_the_may(True)

    _enter_upkeep(scenario)
    _resolve_all(scenario)

    assert aang.name == AANG
    assert scenario.player("alice").life == 24
    assert scenario.player("bob").life == 16


def test_transformed_in_response_means_no_transform_and_no_payoff():
    """CR 701.27f: it transformed after the ability went on the stack, so the
    instruction is ignored - and CR 608.2d offers no impossible "yes"."""
    scenario, aang = _aang_at_upkeep()
    scenario.will_take_the_may(True)
    _enter_upkeep(scenario)
    assert scenario.game.stack

    transform_permanent(scenario.game, aang)  # an effect turns him over in response
    assert aang.name == AANG
    _resolve_all(scenario)

    assert aang.name == AANG
    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 20
    assert (aang.power, aang.toughness) == (4, 4)


def test_transformed_twice_in_response_is_still_ignored():
    """Back face up again is not "hasn't transformed": two transforms since
    the ability went on the stack still void it (CR 701.27f counts the
    transforms, not the face)."""
    scenario, aang = _aang_at_upkeep()
    scenario.will_take_the_may(True)
    _enter_upkeep(scenario)

    transform_permanent(scenario.game, aang)
    transform_permanent(scenario.game, aang)
    assert aang.name == MASTER
    _resolve_all(scenario)

    assert aang.name == MASTER
    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 20


def test_gone_from_the_battlefield_means_no_payoff():
    """Bounced in response: the permanent the ability would transform no
    longer exists (CR 400.7), so there is no transform and no payoff."""
    scenario, aang = _aang_at_upkeep(alice_hand=["Unsummon"])
    scenario.will_take_the_may(True)
    _enter_upkeep(scenario)

    scenario.cast_and_resolve("Unsummon", *scenario.untapped_sources("Island"), targets=[aang])
    assert aang.zone is Zone.HAND
    _resolve_all(scenario)

    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 20


def test_the_front_face_has_no_upkeep_trigger():
    """CR 712.8d: front face up, only the front face's abilities."""
    scenario, aang = _aang_at_upkeep()
    aang.transform()
    assert aang.name == AANG

    _enter_upkeep(scenario)

    assert scenario.game.stack == []


def test_the_damage_is_dealt_by_aang_to_every_opponent_only():
    """ "Each opponent" - never alice herself."""
    scenario, aang = _aang_at_upkeep()
    scenario.will_take_the_may(True)
    _enter_upkeep(scenario)
    _resolve_all(scenario)

    assert scenario.player("alice").life == 24  # gained 4, took nothing
    assert scenario.player("bob").life == 16


# --------------------------------------------------------------------------
# Soul Seizer // Ghastly Haunting
# --------------------------------------------------------------------------


def _seizer_hits(bob_battlefield: list[str]):
    """Alice's Soul Seizer attacks bob unblocked and deals combat damage."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Island"] * 5, battlefield=["Soul Seizer", "Grizzly Bears"])
        .player("bob", library=["Island"] * 5, battlefield=bob_battlefield)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    seizer = scenario.creature("Soul Seizer", "alice")
    scenario.attack_with(seizer)
    scenario.advance()  # declare blockers
    scenario.no_blocks()
    scenario.advance()  # combat damage
    assert scenario.step is Step.COMBAT_DAMAGE
    return scenario, seizer


def test_soul_seizer_becomes_an_aura_stealing_the_target():
    scenario, seizer = _seizer_hits(["Runeclaw Bear"])
    bear = scenario.creature("Runeclaw Bear", "bob")
    scenario.will_choose_targets(bear)
    scenario.will_take_the_may(True)
    scenario.combat_damage()
    _resolve_all(scenario)

    assert scenario.player("bob").life == 19
    assert seizer.name == "Ghastly Haunting"
    assert seizer.zone is Zone.BATTLEFIELD
    assert seizer.attached_to == bear.id
    # "You control enchanted creature." (CR 613.1b's control layer)
    assert scenario.game.controller_of(bear).username == "alice"


def test_declining_leaves_soul_seizer_a_creature_and_the_target_alone():
    scenario, seizer = _seizer_hits(["Runeclaw Bear"])
    bear = scenario.creature("Runeclaw Bear", "bob")
    scenario.will_choose_targets(bear)
    scenario.will_take_the_may(False)
    scenario.combat_damage()
    _resolve_all(scenario)

    assert seizer.name == "Soul Seizer"
    assert seizer.attached_to is None
    assert scenario.game.controller_of(bear).username == "bob"


def test_only_a_creature_the_damaged_player_controls_can_be_targeted():
    """ "That player" is the one dealt the damage: alice's own Grizzly Bears
    is never offered."""
    scenario, _ = _seizer_hits(["Runeclaw Bear"])
    own = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_targets(own)

    with pytest.raises(ValueError):
        scenario.combat_damage()
        _resolve_all(scenario)


def test_the_candidates_offered_are_the_damaged_players_creatures():
    scenario, _ = _seizer_hits(["Runeclaw Bear", "Memnite"])
    scenario.will_take_the_may(False)
    scenario.combat_damage()
    _resolve_all(scenario)

    (question,) = [
        decision
        for decision in scenario.questions_asked()
        if decision.kind.name == "CHOOSE_TARGETS" and decision.source == "Soul Seizer"
    ]
    offered = {ref.card_id for ref in question.targets}
    assert offered == {
        scenario.creature("Runeclaw Bear", "bob").id,
        scenario.creature("Memnite", "bob").id,
    }


def test_no_creature_to_target_means_no_trigger():
    """CR 603.3d: a mandatory target with no legal choice removes the ability."""
    scenario, seizer = _seizer_hits([])
    scenario.will_take_the_may(True)
    scenario.combat_damage()
    _resolve_all(scenario)

    assert seizer.name == "Soul Seizer"
    assert scenario.game.stack == []


def test_an_illegal_target_on_resolution_stops_the_whole_ability():
    """The Soul Seizer ruling: "If the creature is an illegal target by that
    time, the ability doesn't resolve and none of its effects happen. You
    can't have Soul Seizer transform." (CR 608.2b)"""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Island"] * 5, battlefield=["Soul Seizer"])
        .player(
            "bob",
            library=["Island"] * 5,
            hand=["Unsummon"],
            battlefield=["Runeclaw Bear", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    seizer = scenario.creature("Soul Seizer", "alice")
    bear = scenario.creature("Runeclaw Bear", "bob")
    scenario.attack_with(seizer)
    scenario.advance()
    scenario.no_blocks()
    scenario.advance()
    scenario.will_choose_targets(bear)
    scenario.will_take_the_may(True)
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    assert scenario.game.stack

    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Unsummon",
        *scenario.untapped_sources("Island", username="bob"),
        username="bob",
        targets=[bear],
    )
    _resolve_all(scenario)

    assert seizer.name == "Soul Seizer"
    assert seizer.attached_to is None
