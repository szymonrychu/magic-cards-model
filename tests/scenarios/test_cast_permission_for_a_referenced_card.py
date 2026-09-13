"""A resolving effect that lets its controller cast one referenced card this turn.

Emry, Lurker of the Loch: "{T}: Choose target artifact card in your graveyard.
You may cast that card this turn. (You still pay its costs. Timing rules still
apply.)" Battle report B6-03: the ability resolved with `changed: false`, no
permission and no notice, and the graveyard cast was refused.

Every CR number below was read in this session with `mise run rules:find`:

- **CR 601.3** - "A player can begin to cast a spell only if a rule or effect
  allows that player to cast it and no rule or effect prohibits that player
  from casting it." The resolved ability is that effect.
- **CR 117.1a** - "A player may cast a noninstant spell during their main phase
  any time they have priority and the stack is empty." The permission changes
  where the card may be cast from, never when.
- **CR 514.2** - in the cleanup step "all 'until end of turn' and 'this turn'
  effects end".
- **CR 400.7** - an object that changes zones is a new object, so the grant
  names one object, not a card name.

Generality: Silas Renn, Seeker Adept (not in the deck pool) prints the same two
sentences on a *combat damage trigger* rather than a tap ability. Territorial
Bruntar (not in the deck pool) prints the permission after an antecedent this
engine cannot read ("exile cards from the top of your library until you exile a
nonland card"), and must fail closed with a notice rather than resolve silently.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction, why_cannot_cast_from
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from magic_cards_model.models.mana import ManaCost
from tests.scenarios.harness import Scenario

EMRY = "Emry, Lurker of the Loch"


def emry_board(graveyard: list[str], lands: int = 2) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[EMRY, *["Island"] * lands],
            graveyard=graveyard,
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
    )


def activate_emry(scenario, target):
    emry = scenario.find(EMRY, Zone.BATTLEFIELD)
    scenario.activate(emry, index=0, targets=[target])
    scenario.pass_until_resolved()


def test_emry_grants_permission_to_cast_the_targeted_card_this_turn():
    scenario = emry_board(["Mind Stone"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stone = scenario.find("Mind Stone", Zone.GRAVEYARD)

    activate_emry(scenario, stone)

    permission = scenario.game.play_permission_for(stone, "alice")
    assert permission is not None
    assert permission.zone is Zone.GRAVEYARD
    assert permission.pays_mana_cost is True
    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_the_graveyard_cast_is_offered_as_a_legal_action():
    scenario = emry_board(["Mind Stone"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stone = scenario.find("Mind Stone", Zone.GRAVEYARD)
    before = [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.kind is ActionKind.CAST and action.card_id == stone.id
    ]
    assert before == []

    activate_emry(scenario, stone)

    after = [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.kind is ActionKind.CAST and action.card_id == stone.id
    ]
    assert after, "the permission must be enumerated as a cast from the graveyard"


def test_the_card_is_cast_from_the_graveyard_paying_its_own_cost():
    """ "You still pay its costs": Mind Stone still costs {2} (CR 601.2f)."""
    scenario = emry_board(["Mind Stone"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stone = scenario.find("Mind Stone", Zone.GRAVEYARD)
    activate_emry(scenario, stone)

    casting = scenario.cast("Mind Stone", from_zone=Zone.GRAVEYARD)
    casting.use_permission()
    assert casting.total_cost.mana == ManaCost.parse("{2}")
    islands = scenario.untapped_sources("Island", "Island", username="alice")
    scenario.pay_with(casting.begin_paying(), *islands)
    scenario.put_on_stack(casting)
    resolved = scenario.resolve_top()

    assert resolved.zone is Zone.BATTLEFIELD
    assert resolved.name == "Mind Stone"


def test_timing_rules_still_apply():
    """ "Timing rules still apply" (CR 117.1a): an artifact is not cast in the
    end step just because the graveyard is now allowed."""
    scenario = emry_board(["Mind Stone"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stone = scenario.find("Mind Stone", Zone.GRAVEYARD)
    activate_emry(scenario, stone)

    scenario.start_at(Step.END_STEP)

    assert scenario.game.play_permission_for(stone, "alice") is not None
    with pytest.raises(ValueError):
        scenario.cast("Mind Stone", from_zone=Zone.GRAVEYARD)
    assert stone.zone is Zone.GRAVEYARD


def test_the_permission_covers_only_the_targeted_card():
    scenario = emry_board(["Mind Stone", "Ornithopter"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stone = scenario.find("Mind Stone", Zone.GRAVEYARD)
    ornithopter = scenario.find("Ornithopter", Zone.GRAVEYARD)

    activate_emry(scenario, stone)

    assert scenario.game.play_permission_for(ornithopter, "alice") is None
    refusal = why_cannot_cast_from(ornithopter, "alice", Zone.GRAVEYARD, scenario.game)
    assert refusal is not None and "CR 601.3" in refusal


def test_the_permission_ends_with_the_turn():
    """CR 514.2: a "this turn" effect ends in the cleanup step."""
    scenario = emry_board(["Mind Stone"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stone = scenario.find("Mind Stone", Zone.GRAVEYARD)
    activate_emry(scenario, stone)
    assert scenario.game.play_permission_for(stone, "alice") is not None

    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()

    assert stone.zone is Zone.GRAVEYARD
    assert scenario.game.play_permission_for(stone, "alice") is None
    refusal = why_cannot_cast_from(stone, "alice", Zone.GRAVEYARD, scenario.game)
    assert refusal is not None and "CR 601.3" in refusal


def test_silas_renn_grants_the_same_permission_from_a_combat_damage_trigger():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Silas Renn, Seeker Adept", "Island", "Island"],
            graveyard=["Mind Stone"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    silas = scenario.creature("Silas Renn, Seeker Adept", "alice")
    stone = scenario.find("Mind Stone", Zone.GRAVEYARD)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(silas, defending="bob")
    scenario.no_blocks()
    scenario.choose_trigger_targets("Silas Renn, Seeker Adept", [stone])
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    permission = scenario.game.play_permission_for(stone, "alice")
    assert permission is not None
    assert permission.zone is Zone.GRAVEYARD

    scenario.start_at(Step.POSTCOMBAT_MAIN)
    casting = scenario.cast("Mind Stone", from_zone=Zone.GRAVEYARD)
    casting.use_permission()
    islands = scenario.untapped_sources("Island", "Island", username="alice")
    scenario.pay_with(casting.begin_paying(), *islands)
    scenario.put_on_stack(casting)
    assert scenario.resolve_top().zone is Zone.BATTLEFIELD


def test_an_unreadable_permission_fails_closed_with_a_notice():
    """Territorial Bruntar's antecedent is not read, so no permission can name a
    card - and the ability says so instead of resolving to nothing."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Island"],
            battlefield=["Territorial Bruntar"],
            library=["Island", "Mind Stone", "Island"],
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.play_land("Island")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    notices = scenario.game.unmodeled_trigger_effect_notices
    assert [notice.source_name for notice in notices] == ["Territorial Bruntar"]
    assert "you may cast that card this turn" in notices[0].text.lower()
    assert scenario.game.play_permissions == []


def test_an_exiled_top_card_of_your_own_library_may_be_played_until_end_of_turn():
    """Experimental Synthesizer: "When this artifact enters or leaves the
    battlefield, exile the top card of your library. Until end of turn, you may
    play that card." The same exile-then-permission pair as Ragavan's, with the
    controller's own library as the antecedent and "play" (CR 601.1a) rather
    than "cast", so the land drop is reachable too."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Experimental Synthesizer"],
            battlefield=["Mountain"],
            library=["Island", "Mountain", "Mountain"],
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island = scenario.top_of_library(1, "alice")[0]

    scenario.cast_and_resolve("Experimental Synthesizer", auto=True)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert island.zone is Zone.EXILE
    permission = scenario.game.play_permission_for(island, "alice", PlayAction.PLAY)
    assert permission is not None
    assert scenario.game.unmodeled_trigger_effect_notices == []
    played = scenario.play_land("Island", from_zone=Zone.EXILE)
    assert played.zone is Zone.BATTLEFIELD
