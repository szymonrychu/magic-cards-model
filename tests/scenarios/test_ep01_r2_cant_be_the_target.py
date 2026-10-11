"""Static "can't be the target of ..." lines and the static grants an Aura or
a condition hands out (EP-01 R2, T2).

Verified this session with `mise run rules:find`:

- CR 115.2: only permanents are legal targets unless the spell or ability says
  otherwise - which is why a static "Cards in graveyards can't be the targets
  of spells or abilities" (Ground Seal) is a restriction on top of a card
  that is not a permanent at all.
- CR 702.11b / CR 702.18a: hexproof and shroud; CR 702.11d's "from [quality]"
  is the same restriction narrowed to sources with the quality.
- CR 604.2 / CR 611.3: the restriction is a static ability and ends with its
  source; an Aura's "enchanted creature" is whatever it is attached to now.
- CR 101.2 is why "can't" beats a spell's "may target": there is no
  controller exception unless the line says "your opponents".

Shape families (two printings of different wording each):

- self, by spell quality: Fiendslayer Paladin ("black or red spells your
  opponents control"), Karplusan Strider ("blue or black spells"),
  Gaea's Revenge ("nongreen spells or abilities from nongreen sources").
- self, by kind of source: Shanna ("abilities your opponents control"),
  Thrun ("nongreen spells your opponents control or abilities from nongreen
  sources your opponents control").
- attached: Canopy Cover, Shielding Plax; and the keyword form (Curator's
  Ward hexproof, Trace of Abundance shroud, Shardmage's Rescue).
- zone: Ground Seal (cards in graveyards) and Tomik (lands on the
  battlefield and land cards in graveyards, your opponents).
- the spell-side rule: Enthralling Hold / Dream Leash.
- conditional self hexproof: Thrasta (entered this turn), Tom Bombadil (lore
  counters among Sagas).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _next_turn(scenario) -> None:
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.advance()


def _refusal(scenario, spell, target, username):
    casting = scenario.cast(spell, username=username)
    try:
        casting.choose_targets([target])
    except ValueError as error:
        return str(error)
    return None


def _ability_refusal(scenario, source, target, username):
    try:
        scenario.activate(source, sacrificing=[source], targets=[target], username=username)
    except ValueError as error:
        return str(error)
    return None


def _board(alice_battlefield, bob_hand=None, bob_battlefield=None, alice_hand=None):
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=alice_hand or [], battlefield=alice_battlefield)
        .player(
            "bob",
            hand=bob_hand or [],
            battlefield=bob_battlefield or ["Mountain", "Mountain", "Swamp", "Swamp", "Forest"],
        )
        .build()
    )


# -- Fiendslayer Paladin: black or red spells your opponents control ---------


def test_an_opponents_black_spell_cannot_target_the_paladin():
    scenario = _board(["Fiendslayer Paladin"], bob_hand=["Fatal Push"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    paladin = scenario.creature("Fiendslayer Paladin", "alice")
    reason = _refusal(scenario, "Fatal Push", paladin, "bob")
    assert reason is not None
    assert "can't be the target" in reason


def test_an_opponents_red_spell_cannot_target_the_paladin():
    scenario = _board(["Fiendslayer Paladin"], bob_hand=["Lightning Bolt"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    paladin = scenario.creature("Fiendslayer Paladin", "alice")
    assert "can't be the target" in _refusal(scenario, "Lightning Bolt", paladin, "bob")


def test_an_opponents_green_or_white_spell_may_target_the_paladin():
    scenario = _board(["Fiendslayer Paladin"], bob_hand=["Giant Growth", "Swords to Plowshares"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    paladin = scenario.creature("Fiendslayer Paladin", "alice")
    assert _refusal(scenario, "Giant Growth", paladin, "bob") is None
    assert _refusal(scenario, "Swords to Plowshares", paladin, "bob") is None


def test_the_paladins_controller_may_target_it_with_a_red_spell():
    """ "Your opponents control": alice's own Bolt is not refused."""
    scenario = _board(["Fiendslayer Paladin", "Mountain"], alice_hand=["Lightning Bolt"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    paladin = scenario.creature("Fiendslayer Paladin", "alice")
    assert _refusal(scenario, "Lightning Bolt", paladin, "alice") is None


def test_an_opponents_black_ability_may_target_the_paladin():
    """Only spells are named: Vampire Hexmage's ability is not."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Vampire Hexmage"])
        .player("bob", battlefield=["Fiendslayer Paladin"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    paladin = scenario.creature("Fiendslayer Paladin", "bob")
    hexmage = scenario.creature("Vampire Hexmage", "alice")
    assert _ability_refusal(scenario, hexmage, paladin, "alice") is None


# -- Karplusan Strider: blue or black spells (anyone's) ----------------------


def test_the_striders_own_controller_cannot_target_it_with_a_blue_spell_either():
    scenario = _board(["Karplusan Strider", "Island"], alice_hand=["Unsummon"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    strider = scenario.creature("Karplusan Strider", "alice")
    assert "can't be the target" in _refusal(scenario, "Unsummon", strider, "alice")


def test_a_red_spell_may_target_the_strider():
    scenario = _board(["Karplusan Strider"], bob_hand=["Lightning Bolt"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    strider = scenario.creature("Karplusan Strider", "alice")
    assert _refusal(scenario, "Lightning Bolt", strider, "bob") is None


# -- Gaea's Revenge: nongreen spells or abilities from nongreen sources ------


def test_a_nongreen_spell_cannot_target_gaeas_revenge_whoever_casts_it():
    scenario = _board(
        ["Gaea's Revenge", "Mountain"], alice_hand=["Lightning Bolt"], bob_hand=["Lightning Bolt"]
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    revenge = scenario.creature("Gaea's Revenge", "alice")
    assert "can't be the target" in _refusal(scenario, "Lightning Bolt", revenge, "bob")
    assert "can't be the target" in _refusal(scenario, "Lightning Bolt", revenge, "alice")


def test_a_green_spell_may_target_gaeas_revenge():
    scenario = _board(["Gaea's Revenge", "Forest"], alice_hand=["Giant Growth"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    revenge = scenario.creature("Gaea's Revenge", "alice")
    assert _refusal(scenario, "Giant Growth", revenge, "alice") is None


def test_a_nongreen_sources_ability_cannot_target_gaeas_revenge():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Vampire Hexmage"])
        .player("bob", battlefield=["Gaea's Revenge"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    revenge = scenario.creature("Gaea's Revenge", "bob")
    hexmage = scenario.creature("Vampire Hexmage", "alice")
    reason = _ability_refusal(scenario, hexmage, revenge, "alice")
    assert reason is not None
    assert "can't be the target" in reason
    assert hexmage.zone is Zone.BATTLEFIELD


def test_an_opponents_ability_cannot_target_shanna_but_their_spell_can():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Vampire Hexmage", "Mountain"])
        .player("bob", battlefield=["Shanna, Sisay's Legacy"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    shanna = scenario.creature("Shanna, Sisay's Legacy", "bob")
    hexmage = scenario.creature("Vampire Hexmage", "alice")
    assert "can't be the target" in _ability_refusal(scenario, hexmage, shanna, "alice")
    assert _refusal(scenario, "Lightning Bolt", shanna, "alice") is None


def test_shannas_controller_may_target_her_with_their_own_ability():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Shanna, Sisay's Legacy", "Vampire Hexmage"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    shanna = scenario.creature("Shanna, Sisay's Legacy", "alice")
    hexmage = scenario.creature("Vampire Hexmage", "alice")
    assert _ability_refusal(scenario, hexmage, shanna, "alice") is None


# -- Thrun: nongreen spells / nongreen sources, your opponents ---------------


def test_thrun_refuses_an_opponents_nongreen_spell_but_not_a_green_one():
    scenario = _board(["Thrun, Breaker of Silence"], bob_hand=["Lightning Bolt", "Giant Growth"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thrun = scenario.creature("Thrun, Breaker of Silence", "alice")
    assert "can't be the target" in _refusal(scenario, "Lightning Bolt", thrun, "bob")
    assert _refusal(scenario, "Giant Growth", thrun, "bob") is None


def test_thrun_refuses_an_opponents_nongreen_ability():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Vampire Hexmage"])
        .player("bob", battlefield=["Thrun, Breaker of Silence"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thrun = scenario.creature("Thrun, Breaker of Silence", "bob")
    hexmage = scenario.creature("Vampire Hexmage", "alice")
    assert "can't be the target" in _ability_refusal(scenario, hexmage, thrun, "alice")


def test_thruns_controller_is_not_refused_for_their_own_nongreen_spell():
    scenario = _board(["Thrun, Breaker of Silence", "Mountain"], alice_hand=["Lightning Bolt"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thrun = scenario.creature("Thrun, Breaker of Silence", "alice")
    assert _refusal(scenario, "Lightning Bolt", thrun, "alice") is None


# -- Enchanted creature can't be the target: Canopy Cover, Shielding Plax ----


@pytest.mark.parametrize("aura", ["Canopy Cover", "Shielding Plax"])
def test_the_enchanted_creature_refuses_the_auras_opponents(aura):
    scenario = _board(["Grizzly Bears", aura], bob_hand=["Lightning Bolt"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.find(aura, Zone.BATTLEFIELD, "alice").attach_to(bears)
    assert "can't be the target" in _refusal(scenario, "Lightning Bolt", bears, "bob")


@pytest.mark.parametrize("aura", ["Canopy Cover", "Shielding Plax"])
def test_the_auras_controller_may_still_target_the_creature(aura):
    scenario = _board(["Grizzly Bears", aura, "Mountain"], alice_hand=["Lightning Bolt"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.find(aura, Zone.BATTLEFIELD, "alice").attach_to(bears)
    assert _refusal(scenario, "Lightning Bolt", bears, "alice") is None


def test_an_aura_on_an_opponents_creature_refuses_that_creatures_controller():
    """ "Your opponents" is the Aura's controller's: alice's Canopy Cover on
    bob's creature keeps bob's own spells off it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Canopy Cover", "Mountain"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Grizzly Bears", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.find("Canopy Cover", Zone.BATTLEFIELD, "alice").attach_to(bears)
    assert "can't be the target" in _refusal(scenario, "Lightning Bolt", bears, "bob")
    assert _refusal(scenario, "Lightning Bolt", bears, "alice") is None


def test_an_unattached_creature_is_not_covered_and_the_aura_leaving_ends_it():
    scenario = _board(
        ["Grizzly Bears", "Runeclaw Bear", "Canopy Cover"], bob_hand=["Lightning Bolt"] * 3
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    other = scenario.creature("Runeclaw Bear", "alice")
    aura = scenario.find("Canopy Cover", Zone.BATTLEFIELD, "alice")
    aura.attach_to(bears)
    assert _refusal(scenario, "Lightning Bolt", other, "bob") is None
    assert _refusal(scenario, "Lightning Bolt", bears, "bob") is not None
    scenario.game.put_into_graveyard(aura)
    assert _refusal(scenario, "Lightning Bolt", bears, "bob") is None


# -- Enchanted <permanent> has hexproof / shroud ---------------------------


def test_curators_ward_gives_the_enchanted_permanent_hexproof():
    scenario = _board(
        ["Sol Ring", "Curator's Ward", "Runeclaw Bear"],
        bob_hand=["Smash to Smithereens", "Lightning Bolt"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    scenario.find("Curator's Ward", Zone.BATTLEFIELD, "alice").attach_to(ring)
    assert "hexproof" in _refusal(scenario, "Smash to Smithereens", ring, "bob")
    bear = scenario.creature("Runeclaw Bear", "alice")
    assert _refusal(scenario, "Lightning Bolt", bear, "bob") is None


def test_trace_of_abundance_gives_the_enchanted_land_shroud_even_against_its_controller():
    scenario = _board(
        ["Forest", "Trace of Abundance", "Giant Growth"], bob_hand=["Assassin's Trophy"]
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    scenario.find("Trace of Abundance", Zone.BATTLEFIELD, "alice").attach_to(forest)
    assert "shroud" in _refusal(scenario, "Assassin's Trophy", forest, "bob")
    ward = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Forest", "Trace of Abundance"])
        .player("bob")
        .build()
    )
    ward.start_at(Step.PRECOMBAT_MAIN)
    land = ward.find("Forest", Zone.BATTLEFIELD, "alice")
    ward.find("Trace of Abundance", Zone.BATTLEFIELD, "alice").attach_to(land)
    assert ward.game.shroud_refusal(land) is not None


def test_shardmages_rescue_grants_hexproof_only_the_turn_it_entered():
    scenario = _board(["Grizzly Bears", "Shardmage's Rescue"], bob_hand=["Lightning Bolt"] * 3)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    rescue = scenario.find("Shardmage's Rescue", Zone.BATTLEFIELD, "alice")
    rescue.attach_to(bears)
    rescue.turn_entered = scenario.game.turn.turns_taken
    assert "hexproof" in _refusal(scenario, "Lightning Bolt", bears, "bob")
    assert scenario.game.hexproof_abilities(bears) == (True, [])


def test_shardmages_rescue_is_spent_on_a_later_turn():
    scenario = _board(["Grizzly Bears", "Shardmage's Rescue"], bob_hand=["Lightning Bolt"] * 3)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    rescue = scenario.find("Shardmage's Rescue", Zone.BATTLEFIELD, "alice")
    rescue.attach_to(bears)
    rescue.turn_entered = scenario.game.turn.turns_taken
    _next_turn(scenario)
    assert _refusal(scenario, "Lightning Bolt", bears, "bob") is None


# -- Ground Seal / Tomik: graveyard cards ------------------------------------


def _graveyard_board(alice_battlefield, graveyard):
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Raise Dead"],
            battlefield=[*alice_battlefield, "Swamp"],
            graveyard=graveyard,
        )
        .player("bob", hand=["Raise Dead"], battlefield=["Swamp"])
        .build()
    )


def test_without_ground_seal_a_graveyard_card_is_a_legal_target():
    scenario = _graveyard_board([], ["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    assert _refusal(scenario, "Raise Dead", bears, "alice") is None


def test_ground_seal_stops_every_spell_from_targeting_a_graveyard_card():
    scenario = _graveyard_board(["Ground Seal"], ["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    reason = _refusal(scenario, "Raise Dead", bears, "alice")
    assert reason is not None
    assert "can't be the target" in reason


def test_ground_seal_stops_the_card_whoever_owns_the_graveyard_and_ends_with_the_seal():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Raise Dead"], battlefield=["Swamp"], graveyard=["Grizzly Bears"])
        .player("bob", battlefield=["Ground Seal"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    assert _refusal(scenario, "Raise Dead", bears, "alice") is not None
    scenario.game.put_into_graveyard(scenario.find("Ground Seal", Zone.BATTLEFIELD, "bob"))
    assert _refusal(scenario, "Raise Dead", bears, "alice") is None


def test_ground_seal_does_not_touch_a_creature_on_the_battlefield():
    scenario = _board(["Ground Seal", "Grizzly Bears"], bob_hand=["Lightning Bolt"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    assert _refusal(scenario, "Lightning Bolt", bears, "bob") is None


def test_a_triggered_ability_cannot_target_a_graveyard_card_under_ground_seal():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Ground Seal"],
            graveyard=["Grizzly Bears"],
            hand=["Eternal Witness"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Eternal Witness", "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    with pytest.raises(ValueError, match="can't be the target"):
        scenario.choose_trigger_targets("Eternal Witness", [bears])


def test_tomik_refuses_the_opponents_spell_on_any_land_and_any_graveyard_land():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", battlefield=["Tomik, Distinguished Advokist", "Forest"], graveyard=["Mountain"]
        )
        .player(
            "bob",
            hand=["Assassin's Trophy", "Raise Dead"],
            battlefield=["Swamp", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    assert "can't be the target" in _refusal(scenario, "Assassin's Trophy", forest, "bob")


def test_tomik_does_not_cover_a_nonland_permanent():
    scenario = _board(
        ["Tomik, Distinguished Advokist", "Grizzly Bears"], bob_hand=["Lightning Bolt"]
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    assert _refusal(scenario, "Lightning Bolt", bears, "bob") is None


def test_an_ability_cannot_target_a_land_card_in_a_graveyard_under_tomik():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Tomik, Distinguished Advokist"], graveyard=["Mountain"])
        .player("bob", hand=["Eternal Witness"], graveyard=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Eternal Witness", "bob")
    forest = scenario.find("Forest", Zone.GRAVEYARD, "bob")
    with pytest.raises(ValueError, match="can't be the target"):
        scenario.choose_trigger_targets("Eternal Witness", [forest])


# -- You can't choose an untapped creature as this spell's target ------------


def test_enthralling_hold_cannot_be_cast_on_an_untapped_creature():
    scenario = _board(
        ["Mountain"], alice_hand=["Enthralling Hold"], bob_battlefield=["Grizzly Bears"]
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    reason = _refusal(scenario, "Enthralling Hold", bears, "alice")
    assert reason is not None
    assert "tapped" in reason


def test_enthralling_hold_may_enchant_a_tapped_creature():
    scenario = _board(
        ["Mountain"], alice_hand=["Enthralling Hold"], bob_battlefield=["Grizzly Bears"]
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.tapped = True
    assert _refusal(scenario, "Enthralling Hold", bears, "alice") is None


def test_dream_leash_refuses_an_untapped_permanent_of_any_type_and_takes_a_tapped_one():
    scenario = _board(
        ["Mountain"],
        alice_hand=["Dream Leash", "Dream Leash"],
        bob_battlefield=["Sol Ring", "Forest"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    forest.tapped = True
    assert "tapped" in _refusal(scenario, "Dream Leash", ring, "alice")
    assert _refusal(scenario, "Dream Leash", forest, "alice") is None


# -- Thrasta: hexproof as long as it entered this turn -----------------------


def test_thrasta_has_hexproof_the_turn_it_entered_and_not_after():
    scenario = _board(["Mountain"], bob_hand=["Lightning Bolt"] * 3)
    alice_hand = scenario.player("alice").hand
    assert alice_hand == []
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Thrasta, Tempest's Roar"])
        .player("bob", hand=["Lightning Bolt"] * 3, battlefield=["Mountain"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thrasta = scenario.put_onto_battlefield("Thrasta, Tempest's Roar", "alice")
    assert "hexproof" in _refusal(scenario, "Lightning Bolt", thrasta, "bob")
    _next_turn(scenario)
    assert _refusal(scenario, "Lightning Bolt", thrasta, "bob") is None


# -- Tom Bombadil: four or more lore counters among Sagas you control --------


def test_tom_bombadil_has_hexproof_with_four_lore_counters_among_sagas():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Tom Bombadil", "History of Benalia", "Fable of the Mirror-Breaker"],
        )
        .player("bob", hand=["Lightning Bolt"] * 3, battlefield=["Mountain"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bombadil = scenario.creature("Tom Bombadil", "alice")
    first = scenario.find("History of Benalia", Zone.BATTLEFIELD, "alice")
    second = scenario.find("Fable of the Mirror-Breaker", Zone.BATTLEFIELD, "alice")
    first.add_counters(Counter.LORE, 1)  # 2 + 1 = three lore counters in all
    assert _refusal(scenario, "Lightning Bolt", bombadil, "bob") is None
    second.add_counters(Counter.LORE, 1)  # four
    assert "hexproof" in _refusal(scenario, "Lightning Bolt", bombadil, "bob")


@pytest.mark.parametrize(
    "card",
    [
        "Fiendslayer Paladin",
        "Karplusan Strider",
        "Gaea's Revenge",
        "Shanna, Sisay's Legacy",
        "Thrun, Breaker of Silence",
        "Canopy Cover",
        "Shielding Plax",
        "Curator's Ward",
        "Trace of Abundance",
        "Shardmage's Rescue",
        "Ground Seal",
        "Tomik, Distinguished Advokist",
        "Enthralling Hold",
        "Dream Leash",
        "Thrasta, Tempest's Roar",
        "Tom Bombadil",
    ],
)
def test_the_support_oracle_reads_every_clause_of_the_card(card):
    from magic_cards_model.support import card_support
    from tests.scenarios.harness import card_state

    support = card_support(card_state(card).card)
    others = ("Whenever the final chapter ability",)
    unread = [
        c.text for c in support.clauses if c.status != "handled" and not c.text.startswith(others)
    ]
    assert unread == []


def test_silent_gravestone_carries_the_ground_seal_static_line():
    scenario = _graveyard_board(["Silent Gravestone"], ["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    reason = _refusal(scenario, "Raise Dead", bears, "alice")
    assert reason is not None
    assert "can't be the target" in reason


# -- Shadrix Silverquill: its "* Target player ..." mode bullets ---------------


def test_shadrix_mode_bullets_are_each_read_by_the_production_effect_reader():
    from magic_cards_model.support import card_support
    from tests.cards import card

    support = card_support(card("Shadrix Silverquill"))
    bullets = [clause for clause in support.clauses if clause.text.startswith("•")]
    assert len(bullets) == 3
    assert [clause.status for clause in bullets] == ["handled"] * 3
