"""A static debuff on every creature your opponents control, behind a
multi-word flavor word: M.O.D.O.K.'s "Designed Only for Killing - Creatures
your opponents control get -1/-1."

Every CR number below was read in full with `mise run rules:find` in the
session that wrote this file:

- **CR 207.2d** - flavor words "appear in italics at the beginning of some
  abilities" and have "no special rules meaning"; the ability is the text
  after the dash, however many words the label has.
- **CR 613.4c** - layer 7c, where an effect that modifies power and toughness
  without setting it applies.
- **CR 611.3a** - a static ability's continuous effect "applies at any given
  moment to whatever its text indicates" - a creature that changes hands, or
  the source leaving, is read fresh.
- **CR 704.5f** - a creature with toughness 0 or less is put into its owner's
  graveyard.

The layer reader for "Creatures your opponents control get -N/-N" already
existed; what was missing is the flavor-word strip for a label longer than two
words (`machines/layers._ABILITY_WORD_RE`). No other printing legal in a target
format carries a static layer line behind a label of three or more words
(Scryfall full-text search, 2026-09-24), so the reader's generality is shown
here on Waker of Waves (Modern, Pioneer; not in any deck under
`magic-cards-model-api/decks/`), the same "creatures your opponents control"
subject with a different modifier and no label at all.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(alice: list[str], bob: list[str]):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=alice)
        .player("bob", battlefield=bob)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_opposing_creatures_get_minus_one_minus_one():
    scenario = _board(["M.O.D.O.K."], ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")

    assert scenario.game.power_of(bears) == 1
    assert scenario.game.toughness_of(bears) == 1


def test_your_own_creatures_are_untouched():
    scenario = _board(["M.O.D.O.K.", "Grizzly Bears"], [])
    bears = scenario.creature("Grizzly Bears", "alice")
    modok = scenario.creature("M.O.D.O.K.", "alice")

    assert scenario.game.power_of(bears) == 2
    assert scenario.game.power_of(modok) == 2
    assert scenario.game.toughness_of(modok) == 2


def test_an_opposing_one_toughness_creature_dies():
    """CR 704.5f: Llanowar Elves at 0/0 goes to the graveyard."""
    scenario = _board(["M.O.D.O.K."], ["Llanowar Elves"])
    elves = scenario.creature("Llanowar Elves", "bob")

    scenario.state_based_actions()

    assert elves.zone is Zone.GRAVEYARD


def test_the_debuff_ends_when_modok_leaves():
    scenario = _board(["M.O.D.O.K."], ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.destroy(scenario.creature("M.O.D.O.K.", "alice"))

    assert scenario.game.power_of(bears) == 2
    assert scenario.game.toughness_of(bears) == 2


def test_the_debuff_is_read_from_modoks_controller_not_its_owner():
    """CR 611.3a: whose opponents is decided by who controls M.O.D.O.K. now.
    bob steals it with Act of Treason, so alice's creature shrinks and bob's
    does not."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["M.O.D.O.K.", "Grizzly Bears"])
        .player(
            "bob",
            battlefield=["Mountain", "Mountain", "Mountain", "Grizzly Bears"],
            hand=["Act of Treason"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while scenario.game.active_player.username != "bob":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    modok = scenario.creature("M.O.D.O.K.", "alice")
    alice_bears = scenario.creature("Grizzly Bears", "alice")
    bob_bears = scenario.creature("Grizzly Bears", "bob")
    assert scenario.game.power_of(bob_bears) == 1

    scenario.cast_and_resolve("Act of Treason", auto=True, username="bob", targets=[modok])

    assert scenario.game.controller_of(modok).username == "bob"
    assert scenario.game.power_of(alice_bears) == 1
    assert scenario.game.power_of(bob_bears) == 2


def test_proof_waker_of_waves_shrinks_power_only():
    """Waker of Waves: "Creatures your opponents control get -1/-0." """
    scenario = _board(["Waker of Waves"], ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")

    assert scenario.game.power_of(bears) == 1
    assert scenario.game.toughness_of(bears) == 2


def test_modok_without_its_abilities_debuffs_nothing():
    """CR 613.1f/613.6: Dress Down's "Creatures lose all abilities" removes the
    printed line, flavor word and all, before the debuff ever starts applying."""
    scenario = _board(["M.O.D.O.K.", "Dress Down"], ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")

    assert scenario.game.power_of(bears) == 2
    assert scenario.game.toughness_of(bears) == 2
