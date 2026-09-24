""" "If a nontoken creature would enter and it wasn't cast, exile it instead"
(CR 614.1a, 111.1, 601.2).

Containment Priest prints it as a static ability. Mistcaller (the proof
printing - neither a listed card nor in any api deck) prints the same sentence
as the effect of an activated ability with a duration: "Sacrifice this
creature: Until end of turn, if a nontoken creature would enter and it wasn't
cast, exile it instead." - one reader, read once for the static form and once
for the created form (CR 611.2a gives the created effect its stated duration;
CR 514.2 ends "until end of turn" effects at cleanup). Hallowed Moonlight, a
second proof printing, drops "nontoken" ("if a creature would enter and it
wasn't cast") and follows the sentence with "Draw a card." (CR 608.2c: in the
order written).

Every CR number here was read in full with `mise run rules:find`:

- **CR 614.1a** - effects that use the word "instead" are replacement effects.
- **CR 111.1** - a token is a marker used to represent any permanent that
  isn't represented by a card.
- **CR 611.2a** - a continuous effect from a resolving spell or ability that
  doesn't change characteristics or controller lasts as long as stated.
- **CR 514.2** - "until end of turn" effects end at cleanup.
- **CR 601.2** - what casting a spell is; a permanent put onto the battlefield
  any other way "wasn't cast".
- **CR 608.2c** - a resolving spell's instructions are followed in order.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(alice_battlefield: list[str], *, hand=None, graveyard=None):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=alice_battlefield,
            hand=hand or [],
            graveyard=graveyard or [],
            library=["Swamp"] * 5,
        )
        .player("bob", library=["Swamp"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- Containment Priest -------------------------------------------------------


def test_priest_exiles_a_reanimated_creature():
    """Unearth returns Grizzly Bears without casting it."""
    scenario = _board(
        ["Containment Priest", "Swamp"], hand=["Unearth"], graveyard=["Grizzly Bears"]
    )
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD)

    scenario.cast_and_resolve("Unearth", auto=True, targets=[bears])

    assert bears.zone is Zone.EXILE
    assert "Grizzly Bears" not in scenario.battlefield_names()


def test_priest_lets_a_cast_creature_in():
    scenario = _board(["Containment Priest", "Forest", "Forest"], hand=["Grizzly Bears"])

    bears = scenario.cast_and_resolve("Grizzly Bears", auto=True)

    assert bears.zone is Zone.BATTLEFIELD


def test_priest_is_itself_cast_and_enters():
    """Flash-cast Priest was cast, so its own ability (which only works from
    the battlefield, CR 604.2) would not catch it anyway."""
    scenario = _board(["Plains", "Plains"], hand=["Containment Priest"])

    priest = scenario.cast_and_resolve("Containment Priest", auto=True)

    assert priest.zone is Zone.BATTLEFIELD


def test_priest_lets_creature_tokens_in():
    """ "Nontoken": Hangarback Walker's Thopters are created, not cast, and
    still enter (CR 111.1)."""
    scenario = _board(["Containment Priest", "Hangarback Walker"])
    walker = scenario.creature("Hangarback Walker", "alice")
    scenario.game.add_counters(walker, Counter.PLUS_ONE, 2)

    scenario.game.destroy(walker)
    scenario.pass_until_resolved()

    thopters = [p for p in scenario.game.battlefield if p.name.startswith("Thopter")]
    assert len(thopters) == 2


def test_priest_ignores_a_noncreature_permanent_put_onto_the_battlefield():
    scenario = _board(["Containment Priest"], hand=["Mind Stone"])

    stone = scenario.put_onto_battlefield("Mind Stone")

    assert stone.zone is Zone.BATTLEFIELD


def test_priest_catches_an_opponents_creature_too():
    """No "you control" in the text: bob's creature is exiled as well."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Containment Priest"])
        .player("bob", hand=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bears = scenario.put_onto_battlefield("Grizzly Bears", "bob")

    assert bears.zone is Zone.EXILE


# -- Mistcaller (the proof printing) ---------------------------------------------


def test_mistcaller_creates_the_same_replacement_until_end_of_turn():
    scenario = _board(["Mistcaller", "Swamp"], hand=["Unearth"], graveyard=["Grizzly Bears"])
    mistcaller = scenario.creature("Mistcaller", "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD)

    scenario.activate(mistcaller, sacrificing=[mistcaller])
    scenario.pass_until_resolved()
    assert mistcaller.zone is Zone.GRAVEYARD

    scenario.cast_and_resolve("Unearth", auto=True, targets=[bears])

    assert bears.zone is Zone.EXILE


def test_mistcallers_replacement_leaves_cast_creatures_and_tokens_alone():
    scenario = _board(
        ["Mistcaller", "Hangarback Walker", "Forest", "Forest"], hand=["Grizzly Bears"]
    )
    mistcaller = scenario.creature("Mistcaller", "alice")
    walker = scenario.creature("Hangarback Walker", "alice")
    scenario.game.add_counters(walker, Counter.PLUS_ONE, 1)
    scenario.activate(mistcaller, sacrificing=[mistcaller])
    scenario.pass_until_resolved()

    bears = scenario.cast_and_resolve("Grizzly Bears", auto=True)
    scenario.game.destroy(walker)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert [p.name for p in scenario.game.battlefield if p.name.startswith("Thopter")]


def test_mistcallers_replacement_ends_at_cleanup():
    """CR 514.2: on the next turn a reanimated creature enters normally."""
    scenario = _board(["Mistcaller", "Swamp"], hand=["Unearth"], graveyard=["Grizzly Bears"])
    mistcaller = scenario.creature("Mistcaller", "alice")
    scenario.activate(mistcaller, sacrificing=[mistcaller])
    scenario.pass_until_resolved()

    while scenario.turn.turn_number == 1 or scenario.turn.active_player != "alice":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD)
    scenario.cast_and_resolve("Unearth", auto=True, targets=[bears])

    assert bears.zone is Zone.BATTLEFIELD


# -- Hallowed Moonlight (a second proof printing, no "nontoken") ----------------


def test_hallowed_moonlight_exiles_uncast_creature_tokens_too():
    """ "A creature", not "a nontoken creature": Hangarback Walker's Thopters
    are created, not cast, and are exiled (then cease to exist)."""
    scenario = _board(["Hangarback Walker", "Plains", "Plains"], hand=["Hallowed Moonlight"])
    walker = scenario.creature("Hangarback Walker", "alice")
    scenario.game.add_counters(walker, Counter.PLUS_ONE, 2)
    hand_before = len(scenario.player("alice").hand)

    scenario.cast_and_resolve("Hallowed Moonlight", auto=True)
    scenario.game.destroy(walker)
    scenario.pass_until_resolved()

    assert not [p for p in scenario.game.battlefield if p.name.startswith("Thopter")]
    # The spell left the hand and its "Draw a card." drew one.
    assert len(scenario.player("alice").hand) == hand_before


def test_hallowed_moonlight_exiles_a_reanimated_creature():
    scenario = _board(
        ["Plains", "Plains", "Swamp"],
        hand=["Hallowed Moonlight", "Unearth"],
        graveyard=["Grizzly Bears"],
    )
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD)

    scenario.cast_and_resolve("Hallowed Moonlight", *scenario.untapped_sources("Plains", "Plains"))
    scenario.cast_and_resolve("Unearth", auto=True, targets=[bears])

    assert bears.zone is Zone.EXILE


# -- the audit ----------------------------------------------------------------


@pytest.mark.parametrize("name", ["Containment Priest", "Mistcaller", "Hallowed Moonlight"])
def test_every_clause_is_handled(name):
    outcomes = classify_clauses(card(name))
    assert outcomes
    assert {outcome.category for outcome in outcomes} == {HANDLED}, outcomes
