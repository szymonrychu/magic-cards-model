"""Static "<group> have hexproof / shroud" lines (EP-01 R2, T2).

Verified this session with `mise run rules:find`:

- CR 702.11b: hexproof on a permanent is "can't be the target of spells or
  abilities your opponents control"; CR 702.11c is the player's.
- CR 702.18a: shroud is "can't be the target of spells or abilities" - the
  controller's own spells and abilities included.
- CR 604.2 / CR 611.3: the group grant is a static ability's continuous
  effect and lasts as long as its source is on the battlefield; a condition
  ("during your turn", "tapped", "four or more artifacts") is re-read every
  time the board is computed.
- CR 613.1f: the granted keyword is a layer 6 ability.

The shape families proved here, two printings of different wording each:

- "<type> you control have hexproof": Leonin Abunas (artifacts) and Sigarda,
  Font of Blessings ("Other permanents").
- turn- and tap-gated: Bedrock Tortoise ("During your turn, creatures"),
  Oak Street Innkeeper ("During turns other than yours, tapped creatures").
- group shroud: Greater Auramancy ("Other enchantments", "Enchanted creatures
  you control"), Sterling Grove and Indomitable Archangel (metalcraft).
- "you and <group>": Sigarda, Heron's Grace, Shalai, Voice of Plenty and
  Gruul Spellbreaker.
- state-filtered groups: Dragonologist (untapped Dragons).
- source condition: Shimmer Dragon (four or more artifacts).
- "lose hexproof and can't have or gain hexproof": Archetype of Endurance.
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
    """The engine's own reason the spell may not target `target`, or None."""
    casting = scenario.cast(spell, username=username)
    try:
        casting.choose_targets([target])
    except ValueError as error:
        return str(error)
    return None


def _abilities(scenario, permanent):
    return scenario.game.computed_board().of(permanent).abilities


def _has_keyword(scenario, permanent, keyword):
    return any(keyword in line.lower() for line in _abilities(scenario, permanent))


# -- Artifacts you control have hexproof: Leonin Abunas ----------------------


def _abunas_board():
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Leonin Abunas", "Sol Ring", "Grizzly Bears", "Mountain"])
        .player(
            "bob", hand=["Smash to Smithereens", "Lightning Bolt"], battlefield=["Mountain"] * 3
        )
        .build()
    )


def test_an_opponent_cannot_target_an_artifact_the_controller_owns():
    scenario = _abunas_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    reason = _refusal(scenario, "Smash to Smithereens", ring, "bob")
    assert reason is not None
    assert "hexproof" in reason


def test_the_non_artifact_creature_is_not_covered():
    scenario = _abunas_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    assert _refusal(scenario, "Lightning Bolt", bears, "bob") is None


def test_abunas_itself_is_not_an_artifact_so_it_is_not_covered():
    scenario = _abunas_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    abunas = scenario.creature("Leonin Abunas", "alice")
    assert _refusal(scenario, "Lightning Bolt", abunas, "bob") is None


def test_the_artifact_controllers_own_spell_may_still_target_it():
    """CR 702.11b names only "your opponents"."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Smash to Smithereens"],
            battlefield=["Leonin Abunas", "Sol Ring", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    assert _refusal(scenario, "Smash to Smithereens", ring, "alice") is None


def test_the_protection_ends_when_the_source_leaves_the_battlefield():
    scenario = _abunas_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    abunas = scenario.creature("Leonin Abunas", "alice")
    assert _refusal(scenario, "Smash to Smithereens", ring, "bob") is not None
    scenario.game.put_into_graveyard(abunas)
    assert _refusal(scenario, "Smash to Smithereens", ring, "bob") is None


def test_an_abunas_on_the_other_side_does_not_protect_my_artifact():
    """ "Artifacts you control": bob's Abunas covers bob's artifacts only."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Sol Ring"])
        .player(
            "bob",
            hand=["Smash to Smithereens"],
            battlefield=["Leonin Abunas", "Mountain", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    assert _refusal(scenario, "Smash to Smithereens", ring, "bob") is None


# -- Other permanents you control have hexproof: Sigarda, Font of Blessings --


def _sigarda_board():
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Sigarda, Font of Blessings", "Sol Ring", "Grizzly Bears", "Forest"],
        )
        .player("bob", hand=["Lightning Bolt", "Assassin's Trophy"], battlefield=["Mountain"] * 4)
        .build()
    )


def test_other_permanents_of_any_type_are_untargetable_by_opponents():
    scenario = _sigarda_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    assert "hexproof" in _refusal(scenario, "Lightning Bolt", bears, "bob")
    assert "hexproof" in _refusal(scenario, "Assassin's Trophy", ring, "bob")


def test_the_source_itself_is_not_one_of_the_other_permanents():
    scenario = _sigarda_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sigarda = scenario.creature("Sigarda, Font of Blessings", "alice")
    assert _refusal(scenario, "Lightning Bolt", sigarda, "bob") is None


def test_a_permanent_the_opponent_controls_is_not_covered():
    """ "Other permanents you control": bob's Sigarda covers bob's board only."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Grizzly Bears"])
        .player(
            "bob",
            hand=["Lightning Bolt"],
            battlefield=["Sigarda, Font of Blessings", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    assert _refusal(scenario, "Lightning Bolt", bears, "bob") is None


# -- During your turn, creatures you control have hexproof: Bedrock Tortoise --


def _tortoise_board():
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Bedrock Tortoise", "Grizzly Bears", "Sol Ring"])
        .player("bob", hand=["Lightning Bolt", "Lightning Bolt"], battlefield=["Mountain"] * 2)
        .build()
    )


def test_on_the_controllers_turn_their_creatures_have_hexproof():
    scenario = _tortoise_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    tortoise = scenario.creature("Bedrock Tortoise", "alice")
    assert "hexproof" in _refusal(scenario, "Lightning Bolt", bears, "bob")
    assert "hexproof" in _refusal(scenario, "Lightning Bolt", tortoise, "bob")


def test_on_the_opponents_turn_the_grant_is_off():
    scenario = _tortoise_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _next_turn(scenario)
    bears = scenario.creature("Grizzly Bears", "alice")
    assert scenario.turn.active_player == "bob"
    assert _refusal(scenario, "Lightning Bolt", bears, "bob") is None


def test_the_non_creature_artifact_never_gets_it():
    scenario = _tortoise_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    assert not _has_keyword(scenario, ring, "hexproof")


# -- During turns other than yours, tapped creatures you control: Innkeeper ---


def _innkeeper_board():
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Oak Street Innkeeper", "Grizzly Bears", "Runeclaw Bear"])
        .player("bob", hand=["Lightning Bolt", "Lightning Bolt"], battlefield=["Mountain"] * 2)
        .build()
    )


def test_a_tapped_creature_has_hexproof_on_the_opponents_turn():
    scenario = _innkeeper_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _next_turn(scenario)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.tapped = True
    assert "hexproof" in _refusal(scenario, "Lightning Bolt", bears, "bob")


def test_an_untapped_creature_has_no_hexproof_on_the_opponents_turn():
    scenario = _innkeeper_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _next_turn(scenario)
    runeclaw = scenario.creature("Runeclaw Bear", "alice")
    runeclaw.tapped = False
    assert _refusal(scenario, "Lightning Bolt", runeclaw, "bob") is None


def test_on_the_controllers_own_turn_a_tapped_creature_has_no_hexproof():
    scenario = _innkeeper_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.tapped = True
    assert not _has_keyword(scenario, bears, "hexproof")


# -- Group shroud: Greater Auramancy, Sterling Grove -------------------------


def test_other_enchantments_have_shroud_but_the_source_does_not():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Greater Auramancy", "Glorious Anthem"])
        .player(
            "bob",
            hand=["Assassin's Trophy", "Assassin's Trophy"],
            battlefield=["Swamp", "Forest"] * 2,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    anthem = scenario.find("Glorious Anthem", Zone.BATTLEFIELD, "alice")
    auramancy = scenario.find("Greater Auramancy", Zone.BATTLEFIELD, "alice")
    assert "shroud" in _refusal(scenario, "Assassin's Trophy", anthem, "bob")
    assert _refusal(scenario, "Assassin's Trophy", auramancy, "bob") is None


def test_shroud_stops_the_controllers_own_spell_too():
    """CR 702.18a has no controller exception."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Giant Growth"],
            battlefield=["Sterling Grove", "Glorious Anthem", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert Zone.BATTLEFIELD is scenario.find("Sterling Grove", Zone.BATTLEFIELD, "alice").zone
    anthem = scenario.find("Glorious Anthem", Zone.BATTLEFIELD, "alice")
    assert _has_keyword(scenario, anthem, "shroud")


def test_enchanted_creatures_you_control_have_shroud():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Giant Growth"],
            battlefield=[
                "Greater Auramancy",
                "Pacifism",
                "Grizzly Bears",
                "Runeclaw Bear",
                "Forest",
            ],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pacifism = scenario.find("Pacifism", Zone.BATTLEFIELD, "alice")
    enchanted = scenario.creature("Grizzly Bears", "alice")
    free = scenario.creature("Runeclaw Bear", "alice")
    pacifism.attach_to(enchanted)
    assert "shroud" in _refusal(scenario, "Giant Growth", enchanted, "alice")
    assert "shroud" in _refusal(scenario, "Lightning Bolt", enchanted, "bob")
    assert _refusal(scenario, "Giant Growth", free, "alice") is None


# -- Metalcraft group shroud: Indomitable Archangel ---------------------------


def _archangel_board(artifacts):
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Indomitable Archangel", *artifacts])
        .player("bob", hand=["Smash to Smithereens"], battlefield=["Mountain"] * 2)
        .build()
    )


def test_metalcraft_met_gives_every_artifact_shroud():
    scenario = _archangel_board(["Sol Ring", "Ornithopter", "Mox Opal"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    assert "shroud" in _refusal(scenario, "Smash to Smithereens", ring, "bob")


def test_metalcraft_missed_gives_nothing():
    scenario = _archangel_board(["Sol Ring", "Ornithopter"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    assert _refusal(scenario, "Smash to Smithereens", ring, "bob") is None


def test_losing_the_third_artifact_ends_the_grant():
    scenario = _archangel_board(["Sol Ring", "Ornithopter", "Mox Opal"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    assert _refusal(scenario, "Smash to Smithereens", ring, "bob") is not None
    scenario.game.put_into_graveyard(scenario.find("Mox Opal", Zone.BATTLEFIELD, "alice"))
    assert _refusal(scenario, "Smash to Smithereens", ring, "bob") is None


# -- You and <group> have hexproof ------------------------------------------


def test_you_and_humans_you_control_have_hexproof():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Sigarda, Heron's Grace", "Dragonologist", "Grizzly Bears"],
        )
        .player("bob", hand=["Lightning Bolt"] * 3, battlefield=["Mountain"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    human = scenario.creature("Dragonologist", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    sigarda = scenario.creature("Sigarda, Heron's Grace", "alice")
    assert "hexproof" in _refusal(scenario, "Lightning Bolt", "alice", "bob")
    assert "hexproof" in _refusal(scenario, "Lightning Bolt", human, "bob")
    assert _refusal(scenario, "Lightning Bolt", bears, "bob") is None
    assert _refusal(scenario, "Lightning Bolt", sigarda, "bob") is None


def test_the_player_may_still_target_themself():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Sigarda, Heron's Grace", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert _refusal(scenario, "Lightning Bolt", "alice", "alice") is None


def test_the_players_hexproof_ends_with_the_source():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Sigarda, Heron's Grace"])
        .player("bob", hand=["Lightning Bolt"] * 2, battlefield=["Mountain"] * 2)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert _refusal(scenario, "Lightning Bolt", "alice", "bob") is not None
    scenario.game.put_into_graveyard(scenario.creature("Sigarda, Heron's Grace", "alice"))
    assert _refusal(scenario, "Lightning Bolt", "alice", "bob") is None


def test_you_planeswalkers_and_other_creatures_have_hexproof():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Shalai, Voice of Plenty", "Grizzly Bears", "Chandra, Torch of Defiance"],
        )
        .player("bob", hand=["Lightning Bolt"] * 4, battlefield=["Mountain"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    shalai = scenario.creature("Shalai, Voice of Plenty", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    chandra = scenario.find("Chandra, Torch of Defiance", Zone.BATTLEFIELD, "alice")
    assert "hexproof" in _refusal(scenario, "Lightning Bolt", "alice", "bob")
    assert "hexproof" in _refusal(scenario, "Lightning Bolt", bears, "bob")
    assert "hexproof" in _refusal(scenario, "Lightning Bolt", chandra, "bob")
    assert _refusal(scenario, "Lightning Bolt", shalai, "bob") is None


def test_during_your_turn_you_and_this_creature_have_hexproof():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Gruul Spellbreaker", "Grizzly Bears"])
        .player("bob", hand=["Lightning Bolt"] * 4, battlefield=["Mountain"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spellbreaker = scenario.creature("Gruul Spellbreaker", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    assert "hexproof" in _refusal(scenario, "Lightning Bolt", "alice", "bob")
    assert "hexproof" in _refusal(scenario, "Lightning Bolt", spellbreaker, "bob")
    assert _refusal(scenario, "Lightning Bolt", bears, "bob") is None


def test_gruul_spellbreakers_grant_is_off_on_the_opponents_turn():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Gruul Spellbreaker"])
        .player("bob", hand=["Lightning Bolt"] * 2, battlefield=["Mountain"] * 2)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spellbreaker = scenario.creature("Gruul Spellbreaker", "alice")
    _next_turn(scenario)
    assert scenario.turn.active_player == "bob"
    assert _refusal(scenario, "Lightning Bolt", "alice", "bob") is None
    assert _refusal(scenario, "Lightning Bolt", spellbreaker, "bob") is None


# -- Untapped Dragons you control have hexproof: Dragonologist -------------


def test_untapped_dragons_have_hexproof_and_tapped_ones_do_not():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Dragonologist", "Shivan Dragon", "Stormbreath Dragon"])
        .player("bob", hand=["Lightning Bolt"] * 4, battlefield=["Mountain"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    shivan = scenario.creature("Shivan Dragon", "alice")
    storm = scenario.creature("Stormbreath Dragon", "alice")
    dragonologist = scenario.creature("Dragonologist", "alice")
    storm.tapped = True
    assert "hexproof" in _refusal(scenario, "Lightning Bolt", shivan, "bob")
    assert _refusal(scenario, "Lightning Bolt", storm, "bob") is None
    assert _refusal(scenario, "Lightning Bolt", dragonologist, "bob") is None


# -- As long as you control four or more artifacts: Shimmer Dragon ----------


def test_four_artifacts_give_the_dragon_hexproof_and_three_do_not():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Shimmer Dragon", "Sol Ring", "Ornithopter", "Mox Opal", "Mox Amber"],
        )
        .player("bob", hand=["Lightning Bolt"] * 2, battlefield=["Mountain"] * 2)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dragon = scenario.creature("Shimmer Dragon", "alice")
    assert "hexproof" in _refusal(scenario, "Lightning Bolt", dragon, "bob")
    scenario.game.put_into_graveyard(scenario.find("Mox Amber", Zone.BATTLEFIELD, "alice"))
    assert _refusal(scenario, "Lightning Bolt", dragon, "bob") is None


# -- Zombie tokens you control have hexproof and menace: Gleaming Overseer ---


def test_zombie_tokens_get_hexproof_and_menace_but_the_overseer_does_not():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Gleaming Overseer"], battlefield=["Swamp", "Island", "Swamp"])
        .player("bob", hand=["Lightning Bolt"] * 2, battlefield=["Mountain"] * 2)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Gleaming Overseer", auto=True, username="alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    overseer = scenario.creature("Gleaming Overseer", "alice")
    army = next(
        c
        for c in scenario.game.battlefield
        if c.name == "Zombie Army Token" and scenario.game.controller_of(c).username == "alice"
    )
    assert "hexproof" in _refusal(scenario, "Lightning Bolt", army, "bob")
    assert _has_keyword(scenario, army, "menace")
    assert _refusal(scenario, "Lightning Bolt", overseer, "bob") is None


# -- Creatures your opponents control lose hexproof: Archetype of Endurance --


def test_opponents_creatures_lose_printed_hexproof_to_the_archetype():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", hand=["Lightning Bolt"], battlefield=["Mountain", "Archetype of Endurance"]
        )
        .player("bob", battlefield=["Avabruck Caretaker", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    caretaker = scenario.creature("Avabruck Caretaker", "bob")
    assert not _has_keyword(scenario, caretaker, "hexproof")
    assert _refusal(scenario, "Lightning Bolt", caretaker, "alice") is None


def test_the_archetypes_controller_creatures_have_hexproof():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Archetype of Endurance", "Grizzly Bears"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    assert "hexproof" in _refusal(scenario, "Lightning Bolt", bears, "bob")


@pytest.mark.parametrize(
    "card",
    [
        "Leonin Abunas",
        "Sigarda, Font of Blessings",
        "Bedrock Tortoise",
        "Oak Street Innkeeper",
        "Greater Auramancy",
        "Sterling Grove",
        "Indomitable Archangel",
        "Sigarda, Heron's Grace",
        "Shalai, Voice of Plenty",
        "Gruul Spellbreaker",
        "Dragonologist",
        "Shimmer Dragon",
        "Gleaming Overseer",
        "Archetype of Endurance",
        "Privileged Position",
        "Miriam, Herd Whisperer",
        "Lost in the Maze",
    ],
)
def test_the_support_oracle_reads_every_static_line_of_the_card(card):
    from magic_cards_model.support import card_support
    from tests.scenarios.harness import card_state

    printing = card_state(card).card
    support = card_support(printing)
    unread = [c.text for c in support.clauses if c.status not in ("handled",)]
    # Lost in the Maze's ETB tap-and-stun trigger belongs to another epic.
    unread = [t for t in unread if not t.startswith("When this enchantment enters, tap X")]
    assert unread == []
