"""Scenario: conditional statics gated on whose turn it is, metalcraft, or a
spell's own cast-time condition (EP-01 round 2, task 3).

Snowmelt Stag ("During your turn, this creature has base power and toughness
5/2.") and Circle of the Moon Druid ("Bear Form - During your turn, this
creature is a Bear with base power and toughness 4/2.") for the turn gate;
Rusted Relic ("Metalcraft - This artifact is a 5/5 Golem artifact creature as
long as you control three or more artifacts.") and Puresteel Paladin
("Metalcraft - Equipment you control have equip {0} ...") with Ardent Recruit
for the artifact count; Supernatural Rescue ("This spell has flash as long as
you control a Spirit.") for a spell's own timing.

Verified with `mise run rules:find`: CR 611.3a (a static ability's effect is
not locked in), CR 604.2, CR 613.1d (type change), CR 613.4b (base P/T),
CR 207.2c (an ability word has no rules meaning), CR 702.6a (equip).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting.permissions import granted_cast_options
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(alice, bob=(), *, hand=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=list(alice), hand=list(hand), library=["Island"] * 5)
        .player("bob", battlefield=list(bob), library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _next_turn(scenario) -> None:
    """Run this turn out and begin the next player's upkeep."""
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.advance()


def _chars(scenario, name, username="alice"):
    return scenario.game.characteristics_of(scenario.find(name, Zone.BATTLEFIELD, username))


def _notices(scenario):
    return list(scenario.game.continuous_effects.layer_notices)


def _types(scenario, name, username="alice"):
    return {t.value for t in _chars(scenario, name, username).types}


def _has(chars, text):
    return any(line.lower() == text.lower() for line in chars.abilities)


# -- Snowmelt Stag: base P/T during your turn ----------------------------------


def test_snowmelt_stag_has_base_5_2_on_its_controllers_turn():
    scenario = _board(["Snowmelt Stag"])
    chars = _chars(scenario, "Snowmelt Stag")
    assert chars.power_toughness == (5, 2)
    assert _notices(scenario) == []


def test_snowmelt_stag_flips_back_when_the_turn_passes_to_the_opponent():
    scenario = _board(["Snowmelt Stag"])
    assert _chars(scenario, "Snowmelt Stag").power_toughness == (5, 2)
    _next_turn(scenario)
    assert scenario.game.active_player.username == "bob"
    assert _chars(scenario, "Snowmelt Stag").power_toughness == (2, 5)


def test_snowmelt_stag_keeps_the_vigilance_it_prints_in_both_turns():
    scenario = _board(["Snowmelt Stag"])
    assert _has(_chars(scenario, "Snowmelt Stag"), "Vigilance")
    _next_turn(scenario)
    assert _has(_chars(scenario, "Snowmelt Stag"), "Vigilance")


def test_an_opponents_snowmelt_stag_is_not_5_2_on_my_turn():
    scenario = _board(["Grizzly Bears"], ["Snowmelt Stag"])
    assert _chars(scenario, "Snowmelt Stag", "bob").power_toughness == (2, 5)


def test_snowmelt_stag_counters_still_apply_on_top_of_the_base():
    scenario = _board(["Snowmelt Stag"])
    scenario.find("Snowmelt Stag", Zone.BATTLEFIELD, "alice").add_counters("+1/+1")
    assert _chars(scenario, "Snowmelt Stag").power_toughness == (6, 3)


# -- Circle of the Moon Druid: becomes a Bear during your turn -------------------


def test_circle_of_the_moon_druid_is_a_4_2_bear_on_its_controllers_turn():
    scenario = _board(["Circle of the Moon Druid"])
    chars = _chars(scenario, "Circle of the Moon Druid")
    assert chars.power_toughness == (4, 2)
    assert set(chars.subtypes) == {"Bear"}
    assert _notices(scenario) == []


def test_circle_of_the_moon_druid_is_a_human_elf_druid_on_the_opponents_turn():
    scenario = _board(["Circle of the Moon Druid"])
    _next_turn(scenario)
    chars = _chars(scenario, "Circle of the Moon Druid")
    assert set(chars.subtypes) == {"Human", "Elf", "Druid"}
    assert chars.power_toughness == (2, 4)


# -- Blood Burglar: the keyword shape of the same turn gate ----------------------


def test_blood_burglar_has_lifelink_only_during_its_controllers_turn():
    scenario = _board(["Blood Burglar"])
    assert _has(_chars(scenario, "Blood Burglar"), "Lifelink")
    _next_turn(scenario)
    assert not _has(_chars(scenario, "Blood Burglar"), "Lifelink")


# -- Rusted Relic: metalcraft makes it a 5/5 Golem artifact creature ---------------


def test_rusted_relic_is_a_5_5_golem_creature_with_three_artifacts():
    scenario = _board(["Rusted Relic", "Ornithopter", "Sol Ring"])
    chars = _chars(scenario, "Rusted Relic")
    assert chars.power_toughness == (5, 5)
    assert "Golem" in chars.subtypes
    assert _types(scenario, "Rusted Relic") == {"artifact", "creature"}
    assert _notices(scenario) == []


def test_rusted_relic_is_only_an_artifact_with_two_artifacts():
    scenario = _board(["Rusted Relic", "Ornithopter"])
    assert _types(scenario, "Rusted Relic") == {"artifact"}


def test_rusted_relic_flips_when_the_third_artifact_arrives_and_leaves():
    scenario = _board(["Rusted Relic", "Ornithopter", "Sol Ring"])
    assert "creature" in _types(scenario, "Rusted Relic")
    scenario.game.destroy(scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice"))
    assert "creature" not in _types(scenario, "Rusted Relic")


def test_rusted_relic_ignores_the_opponents_artifacts():
    scenario = _board(["Rusted Relic", "Ornithopter"], ["Sol Ring", "Ornithopter"])
    assert "creature" not in _types(scenario, "Rusted Relic")


# -- Ardent Recruit: the same ability word, a pump ---------------------------------


def test_ardent_recruit_gets_plus_two_with_three_artifacts_only():
    with_three = _board(["Ardent Recruit", "Ornithopter", "Sol Ring", "Bonesplitter"])
    assert _chars(with_three, "Ardent Recruit").power_toughness == (3, 3)
    with_two = _board(["Ardent Recruit", "Ornithopter", "Sol Ring"])
    assert _chars(with_two, "Ardent Recruit").power_toughness == (1, 1)
    assert _notices(with_three) == []


def test_ardent_recruit_flips_when_an_artifact_leaves():
    scenario = _board(["Ardent Recruit", "Ornithopter", "Sol Ring", "Bonesplitter"])
    assert _chars(scenario, "Ardent Recruit").power_toughness == (3, 3)
    scenario.game.destroy(scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice"))
    assert _chars(scenario, "Ardent Recruit").power_toughness == (1, 1)


# -- Puresteel Paladin: metalcraft gives Equipment equip {0} ------------------------


def _equip_cost(scenario, equipment, creature):
    activation = equip_activation(
        scenario.game,
        scenario.find(equipment, Zone.BATTLEFIELD, "alice"),
        scenario.find(creature, Zone.BATTLEFIELD, "alice"),
        "alice",
    )
    return str(activation.cost.mana)


def test_puresteel_paladin_makes_equip_free_with_three_artifacts():
    scenario = _board(["Puresteel Paladin", "Bonesplitter", "Ornithopter", "Sol Ring"])
    assert _equip_cost(scenario, "Bonesplitter", "Puresteel Paladin") in ("{0}", "")
    assert _notices(scenario) == []


def test_puresteel_paladin_without_metalcraft_leaves_the_printed_equip_cost():
    scenario = _board(["Puresteel Paladin", "Bonesplitter", "Ornithopter"])
    assert _equip_cost(scenario, "Bonesplitter", "Puresteel Paladin") == "{1}"


def test_puresteel_paladin_equip_cost_flips_when_an_artifact_leaves():
    scenario = _board(["Puresteel Paladin", "Bonesplitter", "Ornithopter", "Sol Ring"])
    assert _equip_cost(scenario, "Bonesplitter", "Puresteel Paladin") in ("{0}", "")
    scenario.game.destroy(scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice"))
    assert _equip_cost(scenario, "Bonesplitter", "Puresteel Paladin") == "{1}"


def test_puresteel_paladin_does_not_discount_an_opponents_equipment():
    scenario = _board(
        ["Puresteel Paladin", "Ornithopter", "Sol Ring"], ["Bonesplitter", "Grizzly Bears"]
    )
    activation = equip_activation(
        scenario.game,
        scenario.find("Bonesplitter", Zone.BATTLEFIELD, "bob"),
        scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob"),
        "bob",
    )
    assert str(activation.cost.mana) == "{1}"


def test_puresteel_paladin_free_equip_actually_attaches():
    scenario = _board(["Puresteel Paladin", "Bonesplitter", "Ornithopter", "Sol Ring"])
    bonesplitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    paladin = scenario.find("Puresteel Paladin", Zone.BATTLEFIELD, "alice")
    activation = equip_activation(scenario.game, bonesplitter, paladin, "alice")
    payment = activation.begin_paying()
    payment.pay()
    activation.activate()
    scenario.resolve_top()
    assert scenario.game.characteristics_of(paladin).power_toughness == (4, 2)


# -- Supernatural Rescue: "This spell has flash as long as you control a Spirit." ------


def _rescue(alice_board, *, step=Step.DECLARE_ATTACKERS):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Supernatural Rescue"],
            battlefield=["Plains", "Plains", "Plains", "Plains", *alice_board],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(step)
    return scenario


def test_supernatural_rescue_has_flash_while_you_control_a_spirit():
    scenario = _rescue(["Enemy of the Guildpact"])
    spirit = scenario.find("Enemy of the Guildpact", Zone.BATTLEFIELD, "alice")
    plains = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")
    rescue = scenario.cast_onto_stack("Supernatural Rescue", *plains, targets=[spirit])
    assert rescue.zone is Zone.STACK


def test_supernatural_rescue_without_a_spirit_is_sorcery_speed():
    scenario = _rescue(["Grizzly Bears"])
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    with pytest.raises(ValueError, match="only cast it during their own main phase"):
        scenario.cast("Supernatural Rescue", targets=[bears])


def test_supernatural_rescue_is_castable_in_a_main_phase_without_a_spirit():
    scenario = _rescue(["Grizzly Bears"], step=Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    plains = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")
    assert scenario.cast_onto_stack(
        "Supernatural Rescue", *plains, targets=[bears]
    ).zone is Zone.STACK


def test_a_spirit_the_opponent_controls_grants_no_flash():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Supernatural Rescue"],
            battlefield=["Plains", "Plains", "Plains", "Plains", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Enemy of the Guildpact"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    with pytest.raises(ValueError, match="only cast it during their own main phase"):
        scenario.cast("Supernatural Rescue", targets=[bears])


def test_supernatural_rescue_loses_flash_once_the_spirit_leaves():
    scenario = _rescue(["Enemy of the Guildpact", "Grizzly Bears"])
    scenario.game.destroy(scenario.find("Enemy of the Guildpact", Zone.BATTLEFIELD, "alice"))
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    with pytest.raises(ValueError, match="only cast it during their own main phase"):
        scenario.cast("Supernatural Rescue", targets=[bears])


# -- Bloodbraid Marauder: "Delirium - This spell has cascade as long as ..." -----------

FOUR_TYPES = ["Island", "Lightning Bolt", "Grizzly Bears", "Sol Ring"]


def _marauder(graveyard, library=("Mountain", "Opt", "Island")):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Bloodbraid Marauder"],
            graveyard=list(graveyard),
            library=list(library),
            battlefield=["Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_marauder_cascades_with_four_card_types_in_the_graveyard():
    scenario = _marauder(FOUR_TYPES)
    scenario.will_take_the_may(True, source="Bloodbraid Marauder")
    scenario.cast_onto_stack("Bloodbraid Marauder", *scenario.untapped_sources("Mountain", "Mountain"))
    assert len(scenario.game.stack) == 2, "the spell and its cascade trigger"
    scenario.resolve_top()
    assert scenario.find("Opt", Zone.STACK).zone is Zone.STACK, "the cascade hit was cast"


def test_marauder_does_not_cascade_with_only_three_card_types():
    scenario = _marauder(FOUR_TYPES[:3])
    scenario.cast_onto_stack("Bloodbraid Marauder", *scenario.untapped_sources("Mountain", "Mountain"))
    assert len(scenario.game.stack) == 1


def test_marauder_counts_types_not_cards():
    scenario = _marauder(["Island", "Island", "Island", "Island", "Lightning Bolt"])
    scenario.cast_onto_stack("Bloodbraid Marauder", *scenario.untapped_sources("Mountain", "Mountain"))
    assert len(scenario.game.stack) == 1


# -- Forge Anew: "During your turn, you may activate equip abilities any time you ------
# could cast an instant." (CR 702.6a's sorcery timing, lifted on its controller's turn)


def _forge(forge_player="alice", step=Step.DECLARE_ATTACKERS):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Bonesplitter", "Grizzly Bears", "Plains", *(["Forge Anew"] if forge_player == "alice" else [])],
        )
        .player("bob", battlefield=["Forest"] + (["Forge Anew"] if forge_player == "bob" else []))
        .build()
    )
    scenario.start_at(step)
    return scenario


def _equip_refusal(scenario):
    activation = equip_activation(
        scenario.game,
        scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice"),
        scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice"),
        "alice",
    )
    return activation.why_not()


def test_forge_anew_lets_its_controller_equip_outside_a_main_phase_on_their_turn():
    scenario = _forge()
    assert _equip_refusal(scenario) is None


def test_forge_anew_equip_at_instant_speed_resolves():
    scenario = _forge()
    bonesplitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    activation = equip_activation(scenario.game, bonesplitter, bears, "alice")
    activation.begin_paying().pay()
    activation.activate()
    scenario.resolve_top()
    assert scenario.game.characteristics_of(bears).power_toughness == (4, 2)


def test_without_forge_anew_equip_is_still_sorcery_speed():
    scenario = _forge(forge_player="nobody")
    assert "sorcery" in (_equip_refusal(scenario) or "")


def test_an_opponents_forge_anew_does_not_unlock_my_equip():
    scenario = _forge(forge_player="bob")
    assert "sorcery" in (_equip_refusal(scenario) or "")


def test_forge_anew_only_applies_during_its_controllers_own_turn():
    scenario = _forge()
    _next_turn(scenario)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert scenario.game.active_player.username == "bob"
    assert "sorcery" in (_equip_refusal(scenario) or "")


# -- Zurgo, Thunder's Decree: Warrior tokens can't be sacrificed in your end step --------

ZURGO_TOKEN_LINE = "This token can't be sacrificed."


def _zurgo(opposing=()):
    from tests.scenarios.test_mobilize import board

    return board("Zurgo, Thunder's Decree", opposing=opposing).build()


def _zurgo_mobilize(scenario):
    from tests.scenarios.test_mobilize import attack_and_resolve

    return attack_and_resolve(scenario, "Zurgo, Thunder's Decree")


def _warriors(scenario, username="alice"):
    from tests.scenarios.test_mobilize import warriors

    return warriors(scenario, username)


def test_zurgos_warrior_tokens_are_not_sacrificed_at_the_end_step():
    scenario = _zurgo()
    _zurgo_mobilize(scenario)
    assert len(_warriors(scenario)) == 2
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()
    assert scenario.step is Step.END_STEP
    while scenario.game.stack:
        scenario.resolve_top()
    assert len(_warriors(scenario)) == 2, "CR 101.2: 'can't be sacrificed' beats the sacrifice"
    assert _notices(scenario) == []


def test_warrior_tokens_are_sacrificed_normally_without_zurgo():
    from tests.scenarios.test_mobilize import attack_and_resolve, board

    scenario = board("Voice of Victory").build()
    attack_and_resolve(scenario)
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()
    while scenario.game.stack:
        scenario.resolve_top()
    assert _warriors(scenario) == []


def test_zurgos_grant_exists_only_during_its_controllers_end_step():
    scenario = _zurgo()
    _zurgo_mobilize(scenario)
    (token, _other) = _warriors(scenario)
    assert not _has(scenario.game.characteristics_of(token), ZURGO_TOKEN_LINE)
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()
    assert _has(scenario.game.characteristics_of(token), ZURGO_TOKEN_LINE)


def test_zurgo_does_not_protect_non_warrior_tokens_or_opponents_warriors():
    scenario = _zurgo()
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()
    assert scenario.step is Step.END_STEP
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    assert not _has(scenario.game.characteristics_of(bears), ZURGO_TOKEN_LINE)


# -- Six: "During your turn, nonland permanent cards in your graveyard have retrace." ----


def _six(
    *,
    alice_board=("Six", "Forest", "Forest"),
    graveyard=("Grizzly Bears", "Lightning Bolt"),
    hand=("Island", "Mountain"),
):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=list(alice_board),
            hand=list(hand),
            graveyard=list(graveyard),
            library=["Island"] * 5,
        )
        .player("bob", battlefield=["Forest"], graveyard=["Llanowar Elves"], library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _retrace(scenario, name, land="Island", username="alice"):
    discard = scenario.find(land, Zone.HAND, username)
    casting = scenario.cast(name, username=username, from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Retrace", choosing=[discard])
    return casting, discard


def test_six_lets_a_nonland_permanent_card_be_cast_from_the_graveyard_by_discarding_a_land():
    scenario = _six()
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    casting, island = _retrace(scenario, "Grizzly Bears")
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Forest", "Forest"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert bears.zone is Zone.BATTLEFIELD
    assert island.zone is Zone.GRAVEYARD, "the land card was discarded as an additional cost"


def test_six_gives_an_instant_no_retrace():
    scenario = _six()
    casting = scenario.cast("Lightning Bolt", from_zone=Zone.GRAVEYARD)
    with pytest.raises(ValueError, match="Retrace"):
        casting.use_keyword("Retrace")


def test_six_gives_retrace_only_on_its_controllers_turn():
    scenario = _six()
    _next_turn(scenario)
    assert scenario.game.active_player.username == "bob"
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    assert not granted_cast_options(scenario.game, bears, "alice", Zone.GRAVEYARD)


def test_six_grants_retrace_to_its_controllers_cards_only():
    scenario = _six()
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "bob")
    assert not granted_cast_options(scenario.game, elves, "alice", Zone.GRAVEYARD)


def test_without_six_a_graveyard_permanent_has_no_retrace():
    scenario = _six(alice_board=("Forest", "Forest"))
    casting = scenario.cast("Grizzly Bears", from_zone=Zone.GRAVEYARD)
    with pytest.raises(ValueError, match="Retrace"):
        casting.use_keyword("Retrace")


def test_retrace_needs_a_land_card_to_discard():
    scenario = _six(hand=())
    casting = scenario.cast("Grizzly Bears", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Retrace")
    with pytest.raises(ValueError, match="discard"):
        scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Forest", "Forest"))


def test_retrace_refuses_a_nonland_card_as_the_discard():
    scenario = _six(hand=("Opt",))
    opt = scenario.find("Opt", Zone.HAND, "alice")
    casting = scenario.cast("Grizzly Bears", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Retrace", choosing=[opt])
    with pytest.raises(ValueError, match="land|discard"):
        scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Forest", "Forest"))
