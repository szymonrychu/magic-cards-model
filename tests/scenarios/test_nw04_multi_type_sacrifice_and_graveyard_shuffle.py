"""Scenario: "sacrifices an artifact and a land of their choice" and "shuffles
their graveyard into their library".

Two templates that sit outside the damage family but ride on damage spells and
their cousins:

- the multi-type edict (Structural Collapse: "Target player sacrifices an
  artifact and a land of their choice. ~ deals 2 damage to that player."):
  the sacrificing player chooses one permanent for each named type, a type
  they have no permanent for is skipped, and everything chosen is sacrificed
  together.
- the graveyard shuffle (Blessed Respite: "Target player shuffles their
  graveyard into their library."; Mnemonic Nexus: "Each player shuffles their
  graveyard into their library."): the whole graveyard moves to the library
  and the library is then randomised.

Rules, each read in full with `mise run rules:find`:

- CR 701.21a - to sacrifice a permanent, its controller moves it from the
  battlefield directly to its owner's graveyard; a player can only sacrifice
  a permanent they control.
- CR 701.24a - to shuffle a library, randomise the cards within it.
- CR 608.2c - instructions are followed in the order written.
- CR 608.2d - the player can't choose an option that's illegal or impossible,
  so a type with no permanent is skipped rather than asked.
- CR 101.4 - with several players choosing, they choose in APNAP order.

Decision recorded in MEMORY.md: one permanent that is both an artifact and a
land fills only one of the two slots (it is one object and can be sacrificed
once), but a player who could fill both slots with different permanents must.

Listed printings: Structural Collapse, Blessed Respite.

Proof printings (not listed, not in any api deck, legal in Modern, Pioneer or
Standard): To the Slaughter ("a creature and a planeswalker"), Reminisce,
Clear the Mind and Learn from the Past (target player, with a draw after),
Mnemonic Nexus (each player), Cranial Archive (an activated ability).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

LISTED = ("Structural Collapse", "Blessed Respite")
PROOF = (
    "To the Slaughter",
    "Reminisce",
    "Clear the Mind",
    "Learn from the Past",
    "Mnemonic Nexus",
    "Cranial Archive",
)


@pytest.mark.parametrize("name", LISTED + PROOF)
def test_every_listed_and_proof_card_reads_handled(name):
    outcomes = {clause.outcome for clause in card_support(card(name)).clauses}
    assert outcomes == {"handled"}, name


def _board(
    *,
    alice_hand=(),
    alice_battlefield=(),
    alice_graveyard=(),
    bob_battlefield=(),
    bob_graveyard=(),
    bob_library=("Mountain",) * 4,
    alice_library=("Forest",) * 4,
):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=[*["Mountain"] * 6, *["Island"] * 4, *["Swamp"] * 3, *alice_battlefield],
            graveyard=list(alice_graveyard),
            library=list(alice_library),
        )
        .player(
            "bob",
            battlefield=list(bob_battlefield),
            graveyard=list(bob_graveyard),
            library=list(bob_library),
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario, name, *, targets=None):
    return scenario.cast_and_resolve(name, username="alice", targets=targets, auto=True)


def _bob_battlefield(scenario):
    return sorted(state.name for state in scenario.game.permanents_controlled_by("bob"))


# -- Structural Collapse: "an artifact and a land" ----------------------------


def test_structural_collapse_sacrifices_one_of_each_type_the_player_chooses():
    scenario = _board(
        alice_hand=["Structural Collapse"],
        bob_battlefield=["Sol Ring", "Mind Stone", "Mountain", "Forest", "Grizzly Bears"],
    )
    mind_stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "bob")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    scenario.will_choose_cards(mind_stone, username="bob")
    scenario.will_choose_cards(forest, username="bob")

    _cast(scenario, "Structural Collapse", targets=["bob"])

    assert _bob_battlefield(scenario) == ["Grizzly Bears", "Mountain", "Sol Ring"]
    assert scenario.player("bob").life == 18
    assert {state.name for state in scenario.player("bob").graveyard} == {"Mind Stone", "Forest"}


def test_the_target_player_chooses_not_the_caster():
    scenario = _board(
        alice_hand=["Structural Collapse"],
        bob_battlefield=["Sol Ring", "Mind Stone", "Mountain", "Forest"],
    )
    scenario.will_choose_cards(scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob"), username="bob")
    scenario.will_choose_cards(scenario.find("Mountain", Zone.BATTLEFIELD, "bob"), username="bob")

    _cast(scenario, "Structural Collapse", targets=["bob"])

    assert _bob_battlefield(scenario) == ["Forest", "Mind Stone"]
    asked = [question for question in scenario.questions_asked() if question.player == "bob"]
    assert len(asked) == 2


def test_a_type_with_a_single_permanent_is_not_asked_about():
    scenario = _board(
        alice_hand=["Structural Collapse"],
        bob_battlefield=["Sol Ring", "Mountain", "Forest"],
    )
    scenario.will_choose_cards(scenario.find("Forest", Zone.BATTLEFIELD, "bob"), username="bob")

    _cast(scenario, "Structural Collapse", targets=["bob"])

    assert _bob_battlefield(scenario) == ["Mountain"]
    assert len([q for q in scenario.questions_asked() if q.player == "bob"]) == 1


def test_a_missing_type_is_skipped_and_the_damage_still_happens():
    scenario = _board(
        alice_hand=["Structural Collapse"],
        bob_battlefield=["Mountain", "Forest", "Grizzly Bears"],
    )
    scenario.will_choose_cards(scenario.find("Mountain", Zone.BATTLEFIELD, "bob"), username="bob")

    _cast(scenario, "Structural Collapse", targets=["bob"])

    assert _bob_battlefield(scenario) == ["Forest", "Grizzly Bears"]
    assert scenario.player("bob").life == 18


def test_no_artifact_and_no_land_sacrifices_nothing_and_still_damages():
    scenario = _board(alice_hand=["Structural Collapse"], bob_battlefield=["Grizzly Bears"])

    _cast(scenario, "Structural Collapse", targets=["bob"])

    assert _bob_battlefield(scenario) == ["Grizzly Bears"]
    assert scenario.player("bob").life == 18


def test_a_lone_artifact_land_is_sacrificed_once_for_one_slot():
    scenario = _board(
        alice_hand=["Structural Collapse"],
        bob_battlefield=["Great Furnace", "Grizzly Bears"],
    )

    _cast(scenario, "Structural Collapse", targets=["bob"])

    assert _bob_battlefield(scenario) == ["Grizzly Bears"]
    assert [state.name for state in scenario.player("bob").graveyard] == ["Great Furnace"]
    assert scenario.player("bob").life == 18


def test_an_artifact_land_and_a_plain_land_are_both_sacrificed():
    scenario = _board(
        alice_hand=["Structural Collapse"],
        bob_battlefield=["Great Furnace", "Mountain"],
    )

    _cast(scenario, "Structural Collapse", targets=["bob"])

    assert _bob_battlefield(scenario) == []


def test_an_artifact_land_cannot_fill_the_land_slot_when_it_blocks_the_artifact_slot():
    """With Great Furnace as the only artifact, the artifact slot must take it,
    so the land slot is chosen among the other lands only."""
    scenario = _board(
        alice_hand=["Structural Collapse"],
        bob_battlefield=["Great Furnace", "Mountain", "Forest"],
    )
    scenario.will_choose_cards(scenario.find("Forest", Zone.BATTLEFIELD, "bob"), username="bob")

    _cast(scenario, "Structural Collapse", targets=["bob"])

    assert _bob_battlefield(scenario) == ["Mountain"]
    land_question = [q for q in scenario.questions_asked() if q.player == "bob"][0]
    offered = {scenario.game.find_by_id(card_id).name for card_id in land_question.cards}
    assert offered == {"Mountain", "Forest"}


def test_the_caster_may_target_themselves():
    scenario = _board(alice_hand=["Structural Collapse"], alice_battlefield=["Sol Ring"])
    scenario.will_choose_cards(scenario.find("Island", Zone.BATTLEFIELD, "alice"), username="alice")

    _cast(scenario, "Structural Collapse", targets=["alice"])

    names = [state.name for state in scenario.game.permanents_controlled_by("alice")]
    assert "Sol Ring" not in names
    assert names.count("Island") == 3
    assert scenario.player("alice").life == 18


# -- To the Slaughter: "a creature and a planeswalker" -------------------------


def test_to_the_slaughter_with_delirium_sacrifices_a_creature_and_a_planeswalker():
    scenario = _board(
        alice_hand=["To the Slaughter"],
        alice_graveyard=["Lightning Bolt", "Grizzly Bears", "Sol Ring", "Forest", "Giant Growth"],
        bob_battlefield=["Grizzly Bears", "Hill Giant", "Jace Beleren"],
    )
    scenario.will_choose_cards(scenario.find("Hill Giant", Zone.BATTLEFIELD, "bob"), username="bob")

    _cast(scenario, "To the Slaughter", targets=["bob"])

    assert _bob_battlefield(scenario) == ["Grizzly Bears"]


def test_to_the_slaughter_without_delirium_is_the_ordinary_edict():
    scenario = _board(
        alice_hand=["To the Slaughter"],
        bob_battlefield=["Grizzly Bears", "Jace Beleren"],
    )
    scenario.will_choose_cards(
        scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob"), username="bob"
    )

    _cast(scenario, "To the Slaughter", targets=["bob"])

    assert _bob_battlefield(scenario) == ["Jace Beleren"]


# -- shuffling a graveyard into a library -------------------------------------


def test_reminisce_moves_the_whole_graveyard_into_the_library_and_shuffles():
    scenario = _board(
        alice_hand=["Reminisce"],
        bob_graveyard=["Lightning Bolt", "Grizzly Bears", "Forest"],
        bob_library=["Mountain"] * 3,
    )
    shuffles = scenario.game.shuffles_performed

    _cast(scenario, "Reminisce", targets=["bob"])

    bob = scenario.player("bob")
    assert bob.graveyard == []
    assert len(bob.library) == 6
    assert sorted(state.name for state in bob.library) == [
        "Forest",
        "Grizzly Bears",
        "Lightning Bolt",
        "Mountain",
        "Mountain",
        "Mountain",
    ]
    assert scenario.game.shuffles_performed == shuffles + 1


def test_the_target_player_is_the_one_whose_graveyard_moves():
    scenario = _board(
        alice_hand=["Reminisce"],
        alice_graveyard=["Forest"],
        bob_graveyard=["Mountain"],
    )

    _cast(scenario, "Reminisce", targets=["bob"])

    # Reminisce itself joins the graveyard only as it finishes resolving.
    assert [state.name for state in scenario.player("alice").graveyard] == ["Forest", "Reminisce"]
    assert scenario.player("bob").graveyard == []


def test_a_caster_may_shuffle_their_own_graveyard_with_the_spell_still_resolving():
    scenario = _board(alice_hand=["Reminisce"], alice_graveyard=["Forest", "Lightning Bolt"])

    _cast(scenario, "Reminisce", targets=["alice"])

    alice = scenario.player("alice")
    # The spell is put into the graveyard only as its resolution finishes
    # (CR 608.2n), after the instruction ran.
    assert [state.name for state in alice.graveyard] == ["Reminisce"]
    assert len(alice.library) == 6


def test_an_empty_graveyard_still_shuffles_the_library():
    scenario = _board(alice_hand=["Reminisce"], bob_library=["Mountain"] * 3)
    shuffles = scenario.game.shuffles_performed

    _cast(scenario, "Reminisce", targets=["bob"])

    assert len(scenario.player("bob").library) == 3
    assert scenario.game.shuffles_performed == shuffles + 1


def test_clear_the_mind_draws_a_card_after_the_shuffle():
    scenario = _board(
        alice_hand=["Clear the Mind"],
        alice_graveyard=["Forest"],
        alice_library=["Forest"] * 2,
    )

    _cast(scenario, "Clear the Mind", targets=["alice"])

    alice = scenario.player("alice")
    assert [state.name for state in alice.hand] == ["Forest"]
    assert len(alice.library) == 2  # 2 library + 1 graveyard - 1 drawn


def test_learn_from_the_past_shuffles_the_target_and_the_caster_draws():
    scenario = _board(
        alice_hand=["Learn from the Past"],
        bob_graveyard=["Mountain", "Forest"],
        alice_library=["Island"] * 3,
    )

    _cast(scenario, "Learn from the Past", targets=["bob"])

    assert scenario.player("bob").graveyard == []
    assert len(scenario.player("bob").library) == 6
    assert [state.name for state in scenario.player("alice").hand] == ["Island"]


def test_mnemonic_nexus_shuffles_every_players_graveyard_into_their_own_library():
    scenario = _board(
        alice_hand=["Mnemonic Nexus"],
        alice_graveyard=["Forest"],
        bob_graveyard=["Mountain", "Lightning Bolt"],
        bob_library=["Mountain"] * 2,
        alice_library=["Forest"] * 2,
    )
    shuffles = scenario.game.shuffles_performed

    _cast(scenario, "Mnemonic Nexus")

    alice, bob = scenario.player("alice"), scenario.player("bob")
    assert [state.name for state in alice.graveyard] == ["Mnemonic Nexus"]
    assert bob.graveyard == []
    assert len(alice.library) == 3
    assert len(bob.library) == 4
    assert scenario.game.shuffles_performed == shuffles + 2


def test_cranial_archive_shuffles_the_target_graveyard_and_draws():
    scenario = _board(
        alice_battlefield=["Cranial Archive"],
        bob_graveyard=["Mountain", "Forest", "Lightning Bolt"],
        alice_library=["Island"] * 2,
    )
    archive = scenario.find("Cranial Archive", Zone.BATTLEFIELD, "alice")

    scenario.activate(archive, *scenario.untapped_sources("Mountain", "Mountain"), targets=["bob"])
    scenario.resolve_top()

    assert scenario.player("bob").graveyard == []
    assert len(scenario.player("bob").library) == 7
    assert [state.name for state in scenario.player("alice").hand] == ["Island"]
    assert archive.zone is Zone.EXILE


# -- Blessed Respite: the shuffle and the fog ---------------------------------


def test_blessed_respite_shuffles_and_then_prevents_all_combat_damage():
    scenario = _board(
        alice_hand=["Blessed Respite"],
        alice_battlefield=["Forest", "Forest", "Hill Giant"],
        bob_graveyard=["Mountain", "Forest"],
    )
    giant = scenario.creature("Hill Giant", "alice")

    _cast(scenario, "Blessed Respite", targets=["bob"])

    assert scenario.player("bob").graveyard == []
    assert len(scenario.player("bob").library) == 6
    scenario.attack_with(giant, defending="bob")
    scenario.combat_damage()
    assert scenario.player("bob").life == 20


def test_blessed_respite_with_an_empty_graveyard_still_prevents_combat_damage():
    scenario = _board(
        alice_hand=["Blessed Respite"],
        alice_battlefield=["Forest", "Forest", "Hill Giant"],
    )
    giant = scenario.creature("Hill Giant", "alice")

    _cast(scenario, "Blessed Respite", targets=["alice"])

    scenario.attack_with(giant, defending="bob")
    scenario.combat_damage()
    assert scenario.player("bob").life == 20
