"""Static and activated "protection from <quality>" grants (EP-01 R2, T2).

Verified this session with `mise run rules:find`:

- CR 702.16a: protection is "protection from [quality]"; a card type, subtype
  or supertype quality reaches sources that are permanents with it and sources
  not on the battlefield that have it.
- CR 702.16b: it can't be targeted by spells or abilities from a source with
  the quality (targeting is refused, in the engine's own words).
- CR 702.16c: it can't be enchanted by Auras with the quality (and 702.16n:
  "this effect doesn't remove this Aura" - Pentarch Ward stays on).
- CR 702.16e: damage from such sources is prevented.
- CR 702.16f: attacking creatures with protection can't be blocked by
  creatures with the quality.
- CR 702.16h: "protection from each color" is five protections; CR 702.16g:
  "from A and from B" is two.
- CR 702.16j: protection from everything is protection from each object.
- CR 702.16k: protection from a player (each of your opponents).
- CR 614.12a: the "chosen" quality is what the permanent chose as it entered.

Shape families (two printings of different wording each where the pool has
them):

- conditional self: Pristine Angel (untapped), Etched Champion (metalcraft),
  Diregraf Escort (paired - both creatures).
- player and group, chosen quality: Serra's Emissary (card type),
  Runed Halo (card name), Riders of Gavony (creature type), Pentarch Ward
  (colour, on the enchanted creature).
- player, whole-player quality: Absolute Virtue.
- group by characteristic: Favor of the Mighty (greatest mana value).
- keyword on its own: Progenitus (everything), Akki Lavarunner // Tok-Tok
  (flipped).
- activated: Thick-Skinned Goblin.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
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
    """Why protection stops an ability of permanent `source` targeting `target`
    (CR 702.16b: "abilities from a source with the stated quality") - the
    question `Game.legal_target` asks again as the ability resolves
    (CR 608.2b)."""
    return scenario.game.protection_refusal(
        target, source.card, source_controller=username, is_spell=False, source_state=source
    )


# -- Pristine Angel: as long as untapped, protection from artifacts and each color --


def _angel_board():
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Hill Giant", "Ornithopter"])
        .player(
            "bob",
            hand=["Lightning Bolt", "Fatal Push", "Giant Growth"],
            battlefield=["Pristine Angel", "Mountain", "Swamp", "Forest"],
        )
        .build()
    )


def test_the_untapped_angel_cannot_be_targeted_by_a_coloured_spell():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt", "Giant Growth"],
            battlefield=["Mountain", "Forest"],
        )
        .player("bob", battlefield=["Pristine Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Pristine Angel", "bob")
    assert "protection from red" in _refusal(scenario, "Lightning Bolt", angel, "alice")
    assert "protection from green" in _refusal(scenario, "Giant Growth", angel, "alice")


def test_the_tapped_angel_loses_the_protection():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Pristine Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Pristine Angel", "bob")
    angel.tapped = True
    assert _refusal(scenario, "Lightning Bolt", angel, "alice") is None


def test_an_attacking_angel_cannot_be_blocked_by_an_artifact_creature():
    """CR 702.16f: protection from artifacts. (An attacking Angel is tapped by
    attacking, so the protection is read before it taps: it has no vigilance,
    which is why this asserts the blocking rule on the declared block.)"""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Pristine Angel"])
        .player("bob", battlefield=["Ornithopter", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    angel = scenario.creature("Pristine Angel", "alice")
    scenario.attack_with(angel)
    angel.tapped = False  # untapped for the protection check: see docstring
    ornithopter = scenario.creature("Ornithopter", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    assert scenario.game.why_cannot_block(giant, angel) is not None
    assert "protection" in scenario.game.why_cannot_block(ornithopter, angel)


# -- Etched Champion: metalcraft ---------------------------------------------


def test_etched_champion_has_protection_from_each_color_with_three_artifacts():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt", "Fatal Push"], battlefield=["Mountain", "Swamp"])
        .player("bob", battlefield=["Etched Champion", "Sol Ring", "Ornithopter"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    champion = scenario.creature("Etched Champion", "bob")
    assert "protection from red" in _refusal(scenario, "Lightning Bolt", champion, "alice")
    assert "protection from black" in _refusal(scenario, "Fatal Push", champion, "alice")


def test_etched_champion_alone_is_unprotected_and_losing_an_artifact_ends_it():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt", "Lightning Bolt"], battlefield=["Mountain"] * 2)
        .player("bob", battlefield=["Etched Champion", "Sol Ring", "Ornithopter"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    champion = scenario.creature("Etched Champion", "bob")
    assert _refusal(scenario, "Lightning Bolt", champion, "alice") is not None
    scenario.game.put_into_graveyard(scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob"))
    assert _refusal(scenario, "Lightning Bolt", champion, "alice") is None


def test_colorless_artifact_source_is_not_stopped_by_protection_from_colors():
    """Protection from each color says nothing about colorless sources."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Sol Ring"])
        .player("bob", battlefield=["Etched Champion", "Ornithopter", "Mox Opal"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    champion = scenario.creature("Etched Champion", "bob")
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    assert scenario.game.protection_quality_against(champion, sol_ring) is None


# -- Diregraf Escort: paired, both creatures have protection from Zombies ----


def test_paired_creatures_both_have_protection_from_zombies():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Diregraf Escort", "Grizzly Bears", "Hill Giant"])
        .player("bob", battlefield=["Gleaming Overseer"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    escort = scenario.creature("Diregraf Escort", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    escort.paired_with = bears.id
    bears.paired_with = escort.id
    zombie = scenario.creature("Gleaming Overseer", "bob")
    scenario.attack_with(bears, giant)
    assert "protection" in scenario.game.why_cannot_block(zombie, bears)
    assert scenario.game.why_cannot_block(zombie, giant) is None


def test_an_unpaired_escort_has_no_protection():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Diregraf Escort", "Grizzly Bears"])
        .player("bob", battlefield=["Gleaming Overseer"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    zombie = scenario.creature("Gleaming Overseer", "bob")
    scenario.attack_with(bears)
    assert scenario.game.why_cannot_block(zombie, bears) is None


# -- Chosen quality: Serra's Emissary, Runed Halo, Riders of Gavony, Pentarch Ward ----


def _enter_choosing(scenario, card, owner, value):
    """Put `card` onto the battlefield for `owner`, answering its "as this
    enters, choose ..." with `value` (CR 614.12a)."""
    scenario.will_choose(value, source=card)
    return scenario.put_onto_battlefield(card, owner)


def test_serras_emissary_protects_its_creatures_from_the_chosen_card_type():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Ravenous Chupacabra"])
        .player("bob", hand=["Serra's Emissary"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emissary = _enter_choosing(scenario, "Serra's Emissary", "bob", "creature")
    bears = scenario.creature("Grizzly Bears", "bob")
    chupacabra = scenario.put_onto_battlefield("Ravenous Chupacabra", "alice")
    assert "protection from creature" in _ability_refusal(scenario, chupacabra, emissary, "alice")
    assert "protection from creature" in _ability_refusal(scenario, chupacabra, bears, "alice")


def test_serras_emissary_protects_the_player_from_the_chosen_card_type():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt", "Hill Giant"], battlefield=["Mountain"])
        .player("bob", hand=["Serra's Emissary"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emissary = _enter_choosing(scenario, "Serra's Emissary", "bob", "instant")
    assert "protection from instant" in _refusal(
        scenario, "Lightning Bolt", scenario.player("bob"), "alice"
    )
    assert "protection from instant" in _refusal(scenario, "Lightning Bolt", emissary, "alice")


def test_serras_emissary_protects_nothing_from_a_type_the_source_is_not():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", hand=["Serra's Emissary"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _enter_choosing(scenario, "Serra's Emissary", "bob", "creature")
    assert _refusal(scenario, "Lightning Bolt", scenario.player("bob"), "alice") is None


def test_runed_halo_protects_the_player_from_the_chosen_name():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt", "Shock"], battlefield=["Mountain", "Mountain"])
        .player("bob", hand=["Runed Halo"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _enter_choosing(scenario, "Runed Halo", "bob", "Lightning Bolt")
    assert "protection" in _refusal(scenario, "Lightning Bolt", scenario.player("bob"), "alice")
    assert _refusal(scenario, "Shock", scenario.player("bob"), "alice") is None


def test_riders_of_gavony_protect_humans_from_the_chosen_creature_type():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Vampire Hexmage"])
        .player("bob", hand=["Riders of Gavony"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    riders = _enter_choosing(scenario, "Riders of Gavony", "bob", "Vampire")
    bears = scenario.creature("Grizzly Bears", "bob")
    hexmage = scenario.creature("Vampire Hexmage", "alice")
    refusal = _ability_refusal(scenario, hexmage, riders, "alice")
    assert refusal is not None and "protection from vampire" in refusal
    assert _ability_refusal(scenario, hexmage, bears, "alice") is None


def test_pentarch_ward_gives_the_enchanted_creature_protection_from_the_chosen_colour():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", hand=["Pentarch Ward"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ward = _enter_choosing(scenario, "Pentarch Ward", "bob", "R")
    bears = scenario.creature("Grizzly Bears", "bob")
    ward.attach_to(bears)
    assert "protection from red" in _refusal(scenario, "Lightning Bolt", bears, "alice")


def test_pentarch_ward_does_not_remove_itself_when_white_is_chosen():
    """CR 702.16n: "this effect doesn't remove this Aura"."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice")
        .player("bob", hand=["Pentarch Ward"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ward = _enter_choosing(scenario, "Pentarch Ward", "bob", "W")
    bears = scenario.creature("Grizzly Bears", "bob")
    ward.attach_to(bears)
    scenario.state_based_actions()
    assert ward.zone is Zone.BATTLEFIELD
    assert ward.attached_to == bears.id


def test_a_second_white_protection_removes_the_other_pentarch_ward():
    """CR 702.16n: "If the creature has other instances of protection from the
    same quality, those instances affect Auras as normal." Two Wards choosing
    white each give the other an instance that is not their own."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice")
        .player("bob", hand=["Pentarch Ward", "Pentarch Ward"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first = _enter_choosing(scenario, "Pentarch Ward", "bob", "W")
    second = _enter_choosing(scenario, "Pentarch Ward", "bob", "W")
    bears = scenario.creature("Grizzly Bears", "bob")
    first.attach_to(bears)
    second.attach_to(bears)
    scenario.state_based_actions()
    assert first.zone is Zone.GRAVEYARD
    assert second.zone is Zone.GRAVEYARD


# -- Absolute Virtue: protection from each of your opponents ----------------


def test_absolute_virtue_protects_its_controller_from_each_opponent():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Absolute Virtue", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    reason = _refusal(scenario, "Lightning Bolt", scenario.player("bob"), "alice")
    assert reason is not None
    assert "protection" in reason


def test_absolute_virtues_controller_may_target_themself():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Absolute Virtue", "Mountain"], hand=["Lightning Bolt"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert _refusal(scenario, "Lightning Bolt", "alice", "alice") is None


def test_absolute_virtue_prevents_damage_from_an_opponents_source():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Hill Giant"])
        .player("bob", battlefield=["Absolute Virtue"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant", "alice")
    scenario.attack_with(giant)
    scenario.no_blocks()
    scenario.combat_damage()
    assert scenario.player("bob").life == 20


# -- Favor of the Mighty: the greatest mana value ----------------------------


def test_only_the_creature_with_the_greatest_mana_value_is_protected():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt", "Lightning Bolt"], battlefield=["Mountain"] * 2)
        .player("bob", battlefield=["Favor of the Mighty", "Grizzly Bears", "Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    angel = scenario.creature("Serra Angel", "bob")
    assert "protection" in _refusal(scenario, "Lightning Bolt", angel, "alice")
    assert _refusal(scenario, "Lightning Bolt", bears, "alice") is None


def test_the_greatest_mana_value_is_among_all_creatures_whoever_controls_them():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain", "Shivan Dragon"])
        .player("bob", battlefield=["Favor of the Mighty", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    # Bob's Bears is not the greatest: alice's Shivan Dragon is.
    assert _refusal(scenario, "Lightning Bolt", bears, "alice") is None


# -- Progenitus: protection from everything ----------------------------------


def test_progenitus_cannot_be_targeted_by_anything():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", hand=["Lightning Bolt", "Giant Growth"], battlefield=["Mountain", "Forest"]
        )
        .player("bob", battlefield=["Progenitus"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    progenitus = scenario.creature("Progenitus", "bob")
    assert "protection from everything" in _refusal(scenario, "Lightning Bolt", progenitus, "alice")
    assert "protection from everything" in _refusal(scenario, "Giant Growth", progenitus, "alice")


def test_progenitus_takes_no_damage_and_cannot_be_blocked():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Progenitus"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    progenitus = scenario.creature("Progenitus", "alice")
    scenario.attack_with(progenitus)
    giant = scenario.creature("Hill Giant", "bob")
    assert scenario.game.why_cannot_block(giant, progenitus) is not None


def test_progenitus_blocking_takes_no_damage():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Hill Giant"])
        .player("bob", battlefield=["Progenitus"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant", "alice")
    scenario.attack_with(giant)
    progenitus = scenario.creature("Progenitus", "bob")
    scenario.block(giant, progenitus)
    scenario.combat_damage()
    assert progenitus.damage == 0


# -- Akki Lavarunner // Tok-Tok: the flipped half --------------------------


def test_tok_tok_has_protection_from_red_only_once_flipped():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt", "Lightning Bolt"], battlefield=["Mountain"] * 2)
        .player("bob", battlefield=["Akki Lavarunner"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    akki = scenario.creature("Akki Lavarunner", "bob")
    assert _refusal(scenario, "Lightning Bolt", akki, "alice") is None
    akki.flip()
    assert "protection from red" in _refusal(scenario, "Lightning Bolt", akki, "alice")


# -- Thick-Skinned Goblin: {R}: gains protection from red until end of turn --


def test_thick_skinned_goblin_gains_protection_until_end_of_turn():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Thick-Skinned Goblin", "Mountain", "Mountain"])
        .player("bob", hand=["Lightning Bolt", "Lightning Bolt"], battlefield=["Mountain"] * 2)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goblin = scenario.creature("Thick-Skinned Goblin", "alice")
    scenario.activate(goblin, *scenario.untapped_sources("Mountain", username="alice")[:1])
    scenario.resolve_top()
    assert "protection from red" in _refusal(scenario, "Lightning Bolt", goblin, "bob")
    assert goblin.zone is Zone.BATTLEFIELD


def test_thick_skinned_goblin_is_unprotected_before_and_after():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Thick-Skinned Goblin", "Mountain"])
        .player("bob", hand=["Lightning Bolt", "Lightning Bolt"], battlefield=["Mountain"] * 2)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goblin = scenario.creature("Thick-Skinned Goblin", "alice")
    assert scenario.game.hexproof_abilities(goblin) == (False, [])
    scenario.activate(goblin, *scenario.untapped_sources("Mountain", username="alice")[:1])
    scenario.resolve_top()
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.turn_based_actions()  # the cleanup step ends "until end of turn" (CR 514.2)
    assert _refusal(scenario, "Lightning Bolt", goblin, "bob") is None


@pytest.mark.parametrize(
    "card",
    [
        "Pristine Angel",
        "Etched Champion",
        "Diregraf Escort",
        "Serra's Emissary",
        "Runed Halo",
        "Riders of Gavony",
        "Pentarch Ward",
        "Absolute Virtue",
        "Favor of the Mighty",
        "Progenitus",
        "Akki Lavarunner",
        "Thick-Skinned Goblin",
    ],
)
def test_the_support_oracle_reads_every_clause_of_the_card(card):
    from magic_cards_model.support import card_support
    from tests.scenarios.harness import card_state

    support = card_support(card_state(card).card)
    unread = [c.text for c in support.clauses if c.status != "handled"]
    assert unread == []
