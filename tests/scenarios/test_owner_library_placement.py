"""The owner of a target puts it into their library second from the top or
on the bottom, their choice - Trickster's Stratagem's first sentence:

    The owner of target creature an opponent controls puts it into their
    library second from the top or on the bottom. Then up to one target
    creature you control connives.

Every CR number below was read in full with `mise run rules:find` in the
session that wrote this file:

- **CR 108.3** - "The owner of a card in the game is the player who started
  the game with it in their deck" - the choice is the owner's, not the
  caster's.
- **CR 608.2d** - a choice an effect offers during resolution is made by the
  player the effect names.
- **CR 608.2b** - a target that has become illegal is not affected, but the
  spell still does what it can to its legal targets: the connive half still
  happens with the creature half gone.
- **CR 115.6** - "up to one" allows zero targets.

The reader is `machines/effects._parse_owner_puts_it_into_library_clause`
(already on main, shared with Lost Days); this file pins Trickster's
Stratagem's own target phrase, "target creature an opponent controls", and
its second sentence. The proof printing is Temporal Cleansing (Modern,
Pioneer, Standard; in no deck under `magic-cards-model-api/decks/`): "The
owner of target nonland permanent puts it into their library second from the
top or on the bottom." - a different target phrase, no second sentence.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _board(bob_library: list[str], spell: str = "Trickster's Stratagem"):
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Lightning Bolt", "Island"],
            hand=[spell],
            battlefield=["Island"] * 4 + ["Grizzly Bears"],
        )
        .player("bob", battlefield=["Llanowar Elves"], library=bob_library)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _bob_library(scenario) -> list[str]:
    return [state.card.name for state in scenario.player("bob").library]


def test_the_owner_puts_it_second_from_the_top():
    scenario = _board(["Forest", "Mountain", "Swamp"])
    elves = scenario.creature("Llanowar Elves", "bob")
    scenario.will_choose_top(True, username="bob")

    scenario.cast_and_resolve("Trickster's Stratagem", auto=True, targets=[elves])

    assert _bob_library(scenario) == ["Forest", "Llanowar Elves", "Mountain", "Swamp"]


def test_the_owner_may_put_it_on_the_bottom():
    scenario = _board(["Forest", "Mountain", "Swamp"])
    elves = scenario.creature("Llanowar Elves", "bob")
    scenario.will_choose_top(False, username="bob")

    scenario.cast_and_resolve("Trickster's Stratagem", auto=True, targets=[elves])

    assert _bob_library(scenario) == ["Forest", "Mountain", "Swamp", "Llanowar Elves"]


def test_the_choice_is_the_owners_not_the_casters():
    """CR 108.3/608.2d: the question is put to bob, who owns the Elves."""
    scenario = _board(["Forest", "Mountain"])
    elves = scenario.creature("Llanowar Elves", "bob")

    scenario.cast_and_resolve("Trickster's Stratagem", auto=True, targets=[elves])

    (question,) = [
        q for q in scenario.questions_asked() if q.kind is DecisionKind.PUT_ON_TOP_OR_BOTTOM
    ]
    assert question.player == "bob"


def test_second_from_the_top_of_a_one_card_library_is_the_bottom():
    scenario = _board(["Forest"])
    elves = scenario.creature("Llanowar Elves", "bob")
    scenario.will_choose_top(True, username="bob")

    scenario.cast_and_resolve("Trickster's Stratagem", auto=True, targets=[elves])

    assert _bob_library(scenario) == ["Forest", "Llanowar Elves"]


def test_an_empty_library_just_holds_the_card():
    scenario = _board([])
    elves = scenario.creature("Llanowar Elves", "bob")
    scenario.will_choose_top(True, username="bob")

    scenario.cast_and_resolve("Trickster's Stratagem", auto=True, targets=[elves])

    assert _bob_library(scenario) == ["Llanowar Elves"]


def test_your_own_creature_is_not_a_legal_first_target():
    """ "target creature an opponent controls": with alice's Bears named for
    the second target, her own Llanowar Elves is refused for the first."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Trickster's Stratagem"],
            battlefield=["Island"] * 4 + ["Grizzly Bears", "Llanowar Elves"],
        )
        .player("bob", battlefield=["Llanowar Elves"], library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    own_elves = scenario.creature("Llanowar Elves", "alice")

    with pytest.raises(ValueError, match="cannot target"):
        scenario.cast("Trickster's Stratagem", targets=[bears, own_elves])


def test_the_connive_still_happens_when_the_first_target_is_gone():
    """CR 608.2b: the Elves left before resolution; the Bears still connive."""
    scenario = _board(["Forest"])
    elves = scenario.creature("Llanowar Elves", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    bolt = scenario.top_of_library(1, "alice")[0]
    scenario.will_discard(bolt)
    scenario.cast_onto_stack("Trickster's Stratagem", auto=True, targets=[elves, bears])
    scenario.game.destroy(elves)

    scenario.resolve_top()

    assert elves.zone is Zone.GRAVEYARD
    assert _bob_library(scenario) == ["Forest"]
    assert bears.counter_count(Counter.PLUS_ONE) == 1


def test_proof_temporal_cleansing_puts_a_nonland_permanent_in_its_owners_library():
    scenario = _board(["Forest", "Mountain"], spell="Temporal Cleansing")
    elves = scenario.creature("Llanowar Elves", "bob")
    scenario.will_choose_top(True, username="bob")

    scenario.cast_and_resolve("Temporal Cleansing", auto=True, targets=[elves])

    assert _bob_library(scenario) == ["Forest", "Llanowar Elves", "Mountain"]
    (question,) = [
        q for q in scenario.questions_asked() if q.kind is DecisionKind.PUT_ON_TOP_OR_BOTTOM
    ]
    assert question.player == "bob"
