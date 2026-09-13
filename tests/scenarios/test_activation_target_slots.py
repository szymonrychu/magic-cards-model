"""Scenario: an activation row says what it targets, and who it could target.

CR 602.2b: "The remainder of the process for activating an ability is
identical to the process for casting a spell listed in rules 601.2b-i." So
CR 601.2c's target announcement is part of activating, and CR 115.1c makes an
activated ability targeted when its own text says "target [something]". A
row describing that activation owes the same `target_slots` a cast row
carries. `legal_actions` built them for a cast and never for an activation:
Goblin Bombardment's "Sacrifice a creature: ... any target" read `[]`, which
is what a row says for an ability that targets nothing (battle 5, B5-10).

Each slot also names its legal candidates at this moment, so a seat never has
to reach into a private engine method to find out what it may point at.

- Equip (CR 702.6a, CR 115.1e: the target lives in the keyword's rule, not in
  printed text) has no entry in `Game.activated_abilities`, so it had no row
  at all; it gets one carrying "target creature you control".
- A loyalty ability (CR 606.3, CR 606.4) is an activated ability like any
  other for targeting.
- An off-battlefield ability (CR 113.6j) carries its slots too, and with a
  legal target on the board its cost is priced rather than left UNKNOWN.

Every CR number here was read with `mise run rules:find` in the session that
wrote this file (602.2b, 601.2c, 601.2h, 608.2b, 115.1, 115.5, 702.6a, 606.3,
606.4, 113.6j).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import Action, ActionKind, Affordability
from magic_cards_model.models.card_state import TargetRef
from magic_cards_model.models.game import Game
from tests.scenarios.harness import Scenario


def _row(
    game,
    player: str,
    card_id,
    *,
    kind: ActionKind = ActionKind.ACTIVATE,
    index: int | None = None,
    keyword: str | None = None,
) -> Action:
    rows = [
        action
        for action in legal_actions(game, player)
        if action.kind is kind
        and action.card_id == card_id
        and (index is None or action.ability_index == index)
        and (keyword is None or action.keyword == keyword)
    ]
    assert len(rows) == 1, rows
    return rows[0]


# -- Goblin Bombardment: a sacrifice cost, "any target" ---------------------


def _bombardment_board():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Goblin Bombardment", "Grizzly Bears"])
        .player("bob", battlefield=["Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_goblin_bombardment_row_carries_its_any_target_slot_and_candidates():
    scenario = _bombardment_board()
    bombardment = scenario.find("Goblin Bombardment", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    wolf = scenario.creature("Watchwolf", "bob")

    row = _row(scenario.game, "alice", bombardment.id, index=0)

    assert row.cost and "Sacrifice" in row.cost
    (slot,) = row.target_slots
    assert "any target" in slot.phrase
    assert (slot.minimum, slot.maximum) == (1, 1)
    assert set(slot.candidates) == {bears.id, wolf.id}, "an enchantment is not any target"
    assert set(slot.player_candidates) == {"alice", "bob"}


def test_goblin_bombardment_refuses_an_illegal_target_with_the_engines_reason():
    scenario = _bombardment_board()
    bombardment = scenario.find("Goblin Bombardment", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    with pytest.raises(ValueError, match="Goblin Bombardment"):
        scenario.activate(bombardment, sacrificing=[bears], targets=[bombardment])


def test_the_public_announcement_profile_is_what_the_row_reports():
    scenario = _bombardment_board()
    bombardment = scenario.find("Goblin Bombardment", Zone.BATTLEFIELD, "alice")

    profile = scenario.game.announcement_profile(bombardment, ability_index=0)
    row = _row(scenario.game, "alice", bombardment.id, index=0)

    assert profile.understood
    assert [r.phrase for r in profile.requirements] == [s.phrase for s in row.target_slots]
    assert Game._announcement_profile is Game.announcement_profile, "the old name stays an alias"


# -- a targeted loyalty ability ----------------------------------------------


def _tamiyo_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island"] * 5,
            battlefield=["Tamiyo, Compleated Sage", "Grizzly Bears"],
        )
        .player("bob", library=["Island"] * 5, battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_a_loyalty_ability_row_carries_its_up_to_one_slot():
    """Tamiyo, Compleated Sage's "+1: Tap up to one target artifact or
    creature." - CR 115.6's "up to one" is minimum 0."""
    scenario = _tamiyo_board()
    tamiyo = scenario.find("Tamiyo, Compleated Sage", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")

    row = _row(scenario.game, "alice", tamiyo.id, index=0)

    (slot,) = row.target_slots
    assert "artifact or creature" in slot.phrase
    assert (slot.minimum, slot.maximum) == (0, 1)
    assert set(slot.candidates) == {bears.id, ring.id}, "a planeswalker is neither"
    assert slot.player_candidates == ()


def test_a_loyalty_ability_refuses_an_illegal_target():
    scenario = _tamiyo_board()
    tamiyo = scenario.find("Tamiyo, Compleated Sage", Zone.BATTLEFIELD, "alice")

    with pytest.raises(ValueError, match="artifact or creature"):
        scenario.activate(tamiyo, targets=[tamiyo])


# -- equip -------------------------------------------------------------------


def _equip_board():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Cori-Steel Cutter", "Grizzly Bears", "Mountain", "Mountain"])
        .player("bob", battlefield=["Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_equip_has_a_row_with_its_creature_you_control_slot():
    """CR 702.6a: "Equip [cost]" means "[Cost]: Attach this permanent to
    target creature you control. Activate only as a sorcery." CR 115.1e puts
    that target in the keyword's rule rather than on the card."""
    scenario = _equip_board()
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    row = _row(scenario.game, "alice", cutter.id, keyword="Equip")

    assert row.ability_index is None
    assert row.rule == "CR 702.6a"
    assert row.mana_cost == "{1}{R}"
    assert row.affordable is Affordability.YES
    (slot,) = row.target_slots
    assert slot.phrase == "target creature", (
        "the parser's phrase; `you control` is in the candidates"
    )
    assert (slot.minimum, slot.maximum) == (1, 1)
    assert slot.candidates == (bears.id,), "bob's Watchwolf is not a creature alice controls"
    assert slot.player_candidates == ()


def test_equip_has_no_row_outside_sorcery_timing():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Cori-Steel Cutter", "Grizzly Bears", "Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")

    assert not [a for a in legal_actions(scenario.game, "alice") if a.card_id == cutter.id]


def test_equip_refuses_an_opponents_creature_at_announcement():
    """CR 601.2c via CR 602.2b: an illegal target is never announced."""
    scenario = _equip_board()
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    wolf = scenario.creature("Watchwolf", "bob")

    with pytest.raises(ValueError, match="Watchwolf"):
        equip_activation(scenario.game, cutter, wolf, "alice")


# -- off-pool: Vampire Hexmage, a sacrifice-this cost -------------------------


def _hexmage_board():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Vampire Hexmage"])
        .player("bob", battlefield=["Watchwolf", "Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_an_off_pool_sacrifice_ability_row_carries_its_target_permanent_slot():
    """Vampire Hexmage is in no deck list: "Sacrifice this creature: Remove
    all counters from target permanent." A different cost and a different
    phrase from Goblin Bombardment's."""
    scenario = _hexmage_board()
    hexmage = scenario.creature("Vampire Hexmage", "alice")
    wolf = scenario.creature("Watchwolf", "bob")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")

    row = _row(scenario.game, "alice", hexmage.id, index=0)

    (slot,) = row.target_slots
    assert slot.phrase == "target permanent"
    assert (slot.minimum, slot.maximum) == (1, 1)
    assert {wolf.id, ring.id} <= set(slot.candidates)
    assert slot.player_candidates == (), "a player is not a permanent"


def test_an_off_pool_sacrifice_ability_refuses_a_player_target():
    scenario = _hexmage_board()
    hexmage = scenario.creature("Vampire Hexmage", "alice")

    with pytest.raises(ValueError, match="target permanent"):
        scenario.activate(hexmage, targets=["bob"])

    assert hexmage.zone is Zone.BATTLEFIELD, (
        "CR 601.2c comes before CR 601.2h: an illegal target refuses the "
        "activation before the sacrifice is paid"
    )


# -- a target the cost itself makes illegal ------------------------------------
#
# CR 602.2b imports CR 601.2c-h in order: the target is announced (601.2c) and
# only then is the cost paid (601.2h). Nothing between the two rechecks the
# target, so a source sacrificing itself - or a creature sacrificed as the
# cost - is a legal target when announced. CR 608.2b is where it stops being
# one: "A target that's no longer in the zone it was in when it was targeted is
# illegal ... If all its targets ... are now illegal, the spell or ability
# doesn't resolve."


def test_hexmage_may_target_itself_and_fizzles_once_sacrificed():
    scenario = _hexmage_board()
    hexmage = scenario.creature("Vampire Hexmage", "alice")

    (slot,) = _row(scenario.game, "alice", hexmage.id, index=0).target_slots
    assert hexmage.id in slot.candidates

    ability = scenario.activate(hexmage, targets=[hexmage])

    assert ability is not None and scenario.game.stack[-1] is ability
    assert scenario.find("Vampire Hexmage", Zone.GRAVEYARD, "alice") is not None
    scenario.resolve_top()
    assert ability.id in scenario.game.fizzled


def test_hexmage_asked_for_its_target_is_offered_itself_before_paying():
    scenario = _hexmage_board()
    hexmage = scenario.creature("Vampire Hexmage", "alice")
    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.CHOOSE_TARGETS, value=(hexmage,), player="alice")
    )

    ability = scenario.activate(hexmage)

    (decision,) = [
        asked
        for asked in scenario.game.decisions.asked
        if asked.kind is DecisionKind.CHOOSE_TARGETS
    ]
    assert TargetRef.to_card(hexmage) in decision.targets
    assert ability is not None
    scenario.resolve_top()
    assert ability.id in scenario.game.fizzled


def test_an_off_pool_sacrifice_a_creature_ability_may_target_the_sacrificed_creature():
    """Phyrexian Plaguelord is in no deck list: "Sacrifice a creature: Target
    creature gets -1/-1 until end of turn." The creature chosen to pay the cost
    is also the target: legal when announced, gone by resolution."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Phyrexian Plaguelord", "Watchwolf"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plaguelord = scenario.creature("Phyrexian Plaguelord", "alice")
    wolf = scenario.creature("Watchwolf", "alice")

    (slot,) = _row(scenario.game, "alice", plaguelord.id, index=1).target_slots
    assert wolf.id in slot.candidates

    ability = scenario.activate(plaguelord, index=1, sacrificing=[wolf], targets=[wolf])

    assert ability is not None
    assert scenario.find("Watchwolf", Zone.GRAVEYARD, "alice") is not None
    scenario.resolve_top()
    assert ability.id in scenario.game.fizzled
    assert scenario.game.characteristics_of(plaguelord).toughness == 4


# -- an off-battlefield ability, and the cast row's candidates ---------------


def test_channel_row_carries_its_slot_and_is_priced_when_a_target_exists():
    """Boseiju, Who Endures's Channel (CR 113.6j). With a legal target on the
    board the activation builds, so its cost is judged instead of UNKNOWN."""
    scenario = (
        Scenario()
        .player("alice", hand=["Boseiju, Who Endures"], battlefield=["Forest", "Forest"])
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    boseiju = scenario.find("Boseiju, Who Endures", Zone.HAND, "alice")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")

    row = _row(scenario.game, "alice", boseiju.id, kind=ActionKind.ACTIVATE_OFF_ZONE)

    (slot,) = row.target_slots
    assert slot.phrase == "target artifact enchantment or nonbasic land"
    assert slot.candidates == (ring.id,)
    assert row.affordable is Affordability.YES, row.unaffordable_reason


def test_a_cast_row_names_its_candidates_in_the_same_shape():
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    wolf = scenario.creature("Watchwolf", "bob")

    row = _row(scenario.game, "alice", bolt.id, kind=ActionKind.CAST)

    (slot,) = row.target_slots
    assert slot.candidates == (wolf.id,)
    assert set(slot.player_candidates) == {"alice", "bob"}


def test_an_activation_that_targets_nothing_keeps_no_slots():
    scenario = (
        Scenario().player("alice", battlefield=["Claws of Gix", "Mountain"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    claws = scenario.find("Claws of Gix", Zone.BATTLEFIELD, "alice")

    assert _row(scenario.game, "alice", claws.id, index=0).target_slots == ()
