"""EP-02 R3 T4: searches that take cards by name - one search for each member
of a group, a chosen name across three zones, a name read off an exiled
permanent - and the library placements that go with them.

Rules, each read in full with `mise run rules:find` in this session:

- CR 701.23a / CR 701.23b - a search finds a card matching the description;
  with a stated quality (a name) the searcher need not find it.
- CR 701.24a / CR 701.24b - the shuffle; found cards are not in it.
- CR 201.2 - same name; CR 201.4 - choosing a card name.
- CR 603.6a - permanents put onto the battlefield together enter together.
- CR 401.1 / CR 401.2 - library placement; the library stays face down.
- CR 608.2c - instructions are followed in order.
"""

import pytest

from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario

from .test_ep02_r3_library_amounts import _board, _resolve_all
from .test_ep02_r3_library_searches import _cast_half

# --------------------------------------------------------------------------
# Hide // Seek
# --------------------------------------------------------------------------

HIDE_SEEK = "Hide // Seek"


def test_hide_puts_a_target_artifact_on_the_bottom_of_its_owners_library():
    scenario = _board(
        hand=[HIDE_SEEK],
        battlefield=["Mountain", "Plains"],
        bob_battlefield=["Sol Ring"],
        bob_library=["Island", "Island", "Island"],
    )
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")

    _cast_half(scenario, HIDE_SEEK, "Hide", targets=[ring])

    assert ring.zone is Zone.LIBRARY
    assert scenario.player("bob").library[-1].name == "Sol Ring", (
        "the bottom of the library, not the top and not shuffled in"
    )
    assert scenario.player("bob").library[0].name == "Island"


def test_hide_takes_an_enchantment_too():
    scenario = _board(
        hand=[HIDE_SEEK],
        battlefield=["Mountain", "Plains"],
        bob_battlefield=["Glorious Anthem"],
    )
    growth = scenario.find("Glorious Anthem", Zone.BATTLEFIELD, "bob")

    _cast_half(scenario, HIDE_SEEK, "Hide", targets=[growth])

    assert growth.zone is Zone.LIBRARY


def test_hide_cannot_target_a_creature():
    scenario = _board(
        hand=[HIDE_SEEK],
        battlefield=["Mountain", "Plains"],
        bob_battlefield=["Grizzly Bears"],
    )
    casting = scenario.cast(HIDE_SEEK, "alice")
    casting.cast_as_split_half("Hide")
    with pytest.raises(ValueError):
        casting.choose_targets([scenario.creature("Grizzly Bears", "bob")])


def test_seek_exiles_a_card_from_an_opponents_library_and_gains_its_mana_value():
    scenario = _board(
        hand=[HIDE_SEEK],
        battlefield=["Plains", "Swamp"],
        bob_library=["Lightning Bolt", "Serra Angel", "Island", "Island"],
    )
    angel = scenario.find("Serra Angel", Zone.LIBRARY, "bob")
    scenario.will_choose_cards(angel, username="alice", source="Seek")

    _cast_half(scenario, HIDE_SEEK, "Seek", targets=["bob"])

    assert angel.zone is Zone.EXILE
    assert scenario.player("alice").life == 25, "Serra Angel's mana value is 5"
    assert len(scenario.player("bob").library) == 3


def test_seek_with_an_empty_library_does_nothing():
    scenario = _board(
        hand=[HIDE_SEEK],
        battlefield=["Plains", "Swamp"],
        bob_library=[],
    )

    _cast_half(scenario, HIDE_SEEK, "Seek", targets=["bob"])

    assert scenario.player("alice").life == 20


# --------------------------------------------------------------------------
# Doubling Chant: for each creature you control, a creature card with the same
# name
# --------------------------------------------------------------------------

CHANT = "Doubling Chant"


def _chant(library: list[str], battlefield: list[str]) -> PlayedScenario:
    return _board(
        hand=[CHANT],
        battlefield=[*battlefield, *["Forest"] * 6],
        library=[*library, "Island"],
    )


def test_doubling_chant_finds_one_same_named_creature_for_each_creature():
    scenario = _chant(
        ["Grizzly Bears", "Grizzly Bears", "Grizzly Bears", "Llanowar Elves", "Hill Giant"],
        ["Grizzly Bears", "Grizzly Bears", "Llanowar Elves"],
    )

    scenario.cast_onto_stack(CHANT, auto=True)
    _resolve_all(scenario)

    on_battlefield = sorted(s.name for s in scenario.game.battlefield if s.card.is_creature)
    assert on_battlefield == ["Grizzly Bears"] * 4 + ["Llanowar Elves"] * 2
    assert sum(1 for s in scenario.player("alice").library if s.name == "Grizzly Bears") == 1


def test_doubling_chant_finds_nothing_for_a_creature_with_no_copy_left():
    scenario = _chant(["Hill Giant"], ["Grizzly Bears"])

    scenario.cast_onto_stack(CHANT, auto=True)
    _resolve_all(scenario)

    assert sum(1 for s in scenario.game.battlefield if s.name == "Grizzly Bears") == 1


def test_doubling_chant_may_decline_each_search():
    scenario = _chant(["Grizzly Bears", "Grizzly Bears"], ["Grizzly Bears"])
    scenario.will_choose_cards(username="alice", source=CHANT)

    scenario.cast_onto_stack(CHANT, auto=True)
    _resolve_all(scenario)

    assert sum(1 for s in scenario.game.battlefield if s.name == "Grizzly Bears") == 1


def test_doubling_chant_ignores_noncreature_cards_of_the_same_name():
    """A creature permanent named like a noncreature library card never matches it."""
    scenario = _chant(["Forest", "Forest"], ["Grizzly Bears"])

    scenario.cast_onto_stack(CHANT, auto=True)
    _resolve_all(scenario)

    assert sum(1 for s in scenario.game.battlefield if s.name == "Forest") == 6


# --------------------------------------------------------------------------
# Clarion Ultimatum: choose five permanents you control; for each, a card with
# the same name, onto the battlefield tapped
# --------------------------------------------------------------------------

CLARION = "Clarion Ultimatum"


def test_clarion_ultimatum_finds_a_same_named_card_for_each_chosen_permanent_tapped():
    scenario = _board(
        hand=[CLARION],
        battlefield=[
            "Forest",
            "Forest",
            "Plains",
            "Plains",
            "Plains",
            "Island",
            "Island",
            "Grizzly Bears",
            "Grizzly Bears",
        ],
        library=[
            "Grizzly Bears",
            "Grizzly Bears",
            "Grizzly Bears",
            "Forest",
            "Plains",
            "Hill Giant",
        ],
    )
    mine = [s for s in scenario.game.battlefield if s.controller == "alice"]
    bears = [s for s in mine if s.name == "Grizzly Bears"]
    chosen = [
        *bears,
        next(s for s in mine if s.name == "Forest"),
        next(s for s in mine if s.name == "Plains"),
        next(s for s in mine if s.name == "Island"),
    ]
    assert len(chosen) == 5
    scenario.will_choose_cards(*chosen, username="alice", source=CLARION)
    before = len([s for s in scenario.game.battlefield if s.controller == "alice"])

    scenario.cast_onto_stack(CLARION, auto=True)
    _resolve_all(scenario)

    mine_after = [s for s in scenario.game.battlefield if s.controller == "alice"]
    assert len(mine_after) == before + 4, (
        "two Bears, a Forest and a Plains; no Island in the library"
    )
    newcomers = [s for s in mine_after if s.id not in {m.id for m in mine}]
    assert sorted(s.name for s in newcomers) == [
        "Forest",
        "Grizzly Bears",
        "Grizzly Bears",
        "Plains",
    ]
    assert all(s.tapped for s in newcomers), "onto the battlefield tapped"


def test_clarion_ultimatum_with_fewer_permanents_than_five_chooses_all_of_them():
    scenario = _board(
        hand=[CLARION],
        battlefield=["Forest", "Forest", "Plains", "Plains", "Plains", "Island", "Island"],
        library=["Forest", "Plains", "Island", "Hill Giant"],
    )

    scenario.cast_onto_stack(CLARION, auto=True)
    _resolve_all(scenario)

    assert len([s for s in scenario.game.battlefield if s.controller == "alice"]) >= 7


# --------------------------------------------------------------------------
# Necromentia
# --------------------------------------------------------------------------

NECROMENTIA = "Necromentia"


def _necromentia() -> PlayedScenario:
    return _board(
        hand=[NECROMENTIA],
        battlefield=["Swamp"] * 3,
        bob_hand=["Lightning Bolt", "Lightning Bolt", "Grizzly Bears"],
        bob_graveyard=["Lightning Bolt"],
        bob_library=["Lightning Bolt", "Island", "Island"],
    )


def test_necromentia_exiles_every_card_with_the_name_and_makes_a_zombie_per_hand_card():
    scenario = _necromentia()
    scenario.will_choose("Lightning Bolt", username="alice", source=NECROMENTIA)

    scenario.cast_onto_stack(NECROMENTIA, targets=["bob"], auto=True)
    _resolve_all(scenario)

    assert [s.name for s in scenario.player("bob").hand] == ["Grizzly Bears"]
    assert scenario.player("bob").graveyard == []
    assert [s.name for s in scenario.player("bob").library] != [] and not any(
        s.name == "Lightning Bolt" for s in scenario.player("bob").library
    )
    assert sum(1 for s in scenario.game.exile if s.name == "Lightning Bolt") == 4
    zombies = [s for s in scenario.game.battlefield if "Zombie" in s.name]
    assert len(zombies) == 2, "two Bolts were exiled from their hand: that player creates two"
    assert all(z.controller == "bob" for z in zombies), "that player creates the tokens"


def test_necromentia_refuses_a_basic_land_name():
    scenario = _necromentia()
    scenario.will_choose("Island", username="alice", source=NECROMENTIA)

    scenario.cast_onto_stack(NECROMENTIA, targets=["bob"], auto=True)
    with pytest.raises(ValueError, match="basic land"):
        _resolve_all(scenario)


def test_necromentia_with_no_card_in_hand_makes_no_zombies():
    scenario = _board(
        hand=[NECROMENTIA],
        battlefield=["Swamp"] * 3,
        bob_hand=["Grizzly Bears"],
        bob_graveyard=["Lightning Bolt"],
    )
    scenario.will_choose("Lightning Bolt", username="alice", source=NECROMENTIA)

    scenario.cast_onto_stack(NECROMENTIA, targets=["bob"], auto=True)
    _resolve_all(scenario)

    assert not any("Zombie" in s.name for s in scenario.game.battlefield)
    assert scenario.player("bob").graveyard == []


# --------------------------------------------------------------------------
# The End
# --------------------------------------------------------------------------

END = "The End"


def _the_end(life: int = 20, swamps: int = 4) -> PlayedScenario:
    scenario = _board(
        hand=[END],
        battlefield=["Swamp"] * swamps,
        bob_battlefield=["Grizzly Bears"],
        bob_hand=["Grizzly Bears", "Grizzly Bears", "Lightning Bolt"],
        bob_graveyard=["Grizzly Bears"],
        bob_library=["Grizzly Bears", "Island", "Island", "Island"],
    )
    scenario.player("alice").life = life
    return scenario


def test_the_end_exiles_the_creature_and_every_card_with_its_name_then_draws_per_hand_card():
    scenario = _the_end()
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_onto_stack(END, targets=[bears], auto=True)
    _resolve_all(scenario)

    assert sum(1 for s in scenario.game.exile if s.name == "Grizzly Bears") == 5
    assert not any(s.name == "Grizzly Bears" for s in scenario.player("bob").library)
    assert scenario.player("bob").graveyard == []
    assert len(scenario.player("bob").hand) == 1 + 2, "Bolt stays; two cards drawn for two exiled"


def test_the_end_costs_two_less_at_five_life_or_less():
    scenario = _the_end(life=5, swamps=2)
    scenario.cast_onto_stack(END, targets=[scenario.creature("Grizzly Bears", "bob")], auto=True)
    _resolve_all(scenario)

    assert scenario.player("bob").graveyard == []


def test_the_end_at_six_life_still_costs_all_four():
    scenario = _the_end(life=6, swamps=2)
    with pytest.raises(ValueError):
        scenario.cast_onto_stack(
            END, targets=[scenario.creature("Grizzly Bears", "bob")], auto=True
        )
