"""A manland whose retention sentence names a subtype: "It's still a Cave land."

Cavernous Maw: "{2}: This land becomes a 3/3 Elemental creature until end of
turn. It's still a Cave land. Activate only if the number of other Caves you
control plus the number of Cave cards in your graveyard is three or greater."
The retention clause is the same CR 205.1b sentence as Celestial Colonnade's
"It's still a land." - only the noun phrase is longer, and it carries a
capitalised subtype, so a lowercase-only reader misses it.

Rules, each read with `mise run rules:find` in the session that wrote this:

- **CR 205.1b** - "still a [type, supertype, or subtype]" retains every prior
  card type and subtype.
- **CR 613.1d** - the animation is a layer 4 type change; **CR 613.4b** sets
  the P/T in layer 7b.
- **CR 514.2** - "until end of turn" effects end in the cleanup step.
- **CR 602.5b** - an "Activate only if" restriction is checked on activation.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers import is_retention_clause
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(*, battlefield=(), graveyard=()) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Cavernous Maw", "Forest", "Forest", *battlefield],
            graveyard=list(graveyard),
            library=["Forest"] * 5,
        )
        .player("bob", battlefield=["Mountain"], library=["Forest"] * 5)
    )


def _animate(scenario):
    maw = scenario.find("Cavernous Maw", Zone.BATTLEFIELD, "alice")
    scenario.activate(
        maw, *scenario.untapped_sources("Forest", "Forest", username="alice"), index=1
    )
    scenario.pass_until_resolved()
    return maw


def test_the_maw_becomes_a_three_three_elemental_that_is_still_a_cave_land():
    scenario = _board(battlefield=["Captivating Cave", "Echoing Deeps", "Sunken Citadel"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    maw = _animate(scenario)

    computed = scenario.game.computed_board().of(maw)
    assert computed.is_creature
    assert computed.is_land, "CR 205.1b: 'It's still a Cave land.'"
    assert "Cave" in computed.subtypes, "CR 205.1b: the Cave subtype is retained"
    assert "Elemental" in computed.subtypes
    assert (computed.power, computed.toughness) == (3, 3)


def test_the_animation_still_counts_as_a_cave_for_its_own_restriction():
    """Three other Caves on the battlefield: Maw animated, still a Cave, so the
    other Caves count stays three."""
    scenario = _board(battlefield=["Captivating Cave", "Echoing Deeps", "Sunken Citadel"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    maw = _animate(scenario)
    assert scenario.why_cannot_activate(maw, index=1) is None


def test_the_animation_ends_in_cleanup_and_the_maw_is_a_plain_cave_again():
    """CR 514.2."""
    scenario = _board(battlefield=["Captivating Cave", "Echoing Deeps", "Sunken Citadel"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    maw = _animate(scenario)
    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    computed = scenario.game.computed_board().of(maw)
    assert not computed.is_creature
    assert computed.is_land
    assert "Cave" in computed.subtypes
    assert "Elemental" not in computed.subtypes


@pytest.mark.parametrize(
    ("battlefield", "graveyard", "allowed"),
    [
        (["Captivating Cave", "Echoing Deeps"], ["Captivating Cave"], True),
        (["Captivating Cave", "Echoing Deeps"], [], False),
        ([], ["Captivating Cave", "Echoing Deeps", "Sunken Citadel"], True),
        ([], ["Captivating Cave", "Echoing Deeps"], False),
    ],
)
def test_exactly_two_versus_three_counting_the_graveyard(battlefield, graveyard, allowed):
    """Two Caves is one short; the graveyard's Cave cards count the same as
    the battlefield's other Caves."""
    scenario = _board(battlefield=battlefield, graveyard=graveyard).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    maw = scenario.find("Cavernous Maw", Zone.BATTLEFIELD, "alice")
    assert (scenario.why_cannot_activate(maw, index=1) is None) == allowed


def test_a_refused_activation_animates_nothing():
    scenario = _board(battlefield=["Captivating Cave"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    maw = scenario.find("Cavernous Maw", Zone.BATTLEFIELD, "alice")
    assert scenario.why_cannot_activate(maw, index=1) is not None
    assert not scenario.game.computed_board().of(maw).is_creature


@pytest.mark.parametrize(
    "sentence",
    [
        "It's still a land.",
        "It's still a Cave land.",
        "It's still an artifact.",
        "It's still a legendary Desert land.",
    ],
)
def test_the_retention_clause_reads_any_noun_phrase(sentence):
    assert is_retention_clause(sentence)


@pytest.mark.parametrize(
    "sentence", ["It still has flying.", "It's a land.", "It's still a creature until end of turn."]
)
def test_other_sentences_are_not_retention_clauses(sentence):
    assert not is_retention_clause(sentence)
