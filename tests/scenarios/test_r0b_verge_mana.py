"""R0b T2: every Verge's conditional second mana ability, through the engine.

A Verge prints `{T}: Add <first>.` and `{T}: Add <second>. Activate only if
you control a <X> or a <Y>.` Rules verified with `mise run rules:find`:

- **CR 605.1a** - an activated ability with no target that could add mana is a
  mana ability, restriction or not.
- **CR 602.5b** - an activation restriction ("Activate only if ...") keeps
  applying to the object, so the second ability is refused while it is unmet.
- **CR 205.3i** - land subtypes (Island, Mountain, ...) are what the condition
  reads, so a nonbasic land carrying the subtype counts.
- **CR 106.12** - to tap for mana is to activate a mana ability with {T}.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario

W, U, B, R, G = Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN

# verge, first, second, (land a, land b), nonbasic typed land, a land of
# neither type, the one-mana spell of the second colour, its targets (bob's
# Llanowar Elves) and a qualifying basic that does not make the second colour.
VERGES = [
    (
        "Riverpyre Verge",
        R,
        U,
        ("Island", "Mountain"),
        "Steam Vents",
        "Forest",
        "Opt",
        False,
        "Mountain",
    ),
    (
        "Sunbillow Verge",
        W,
        R,
        ("Mountain", "Plains"),
        "Sacred Foundry",
        "Swamp",
        "Lightning Bolt",
        True,
        "Plains",
    ),
    (
        "Floodfarm Verge",
        W,
        U,
        ("Plains", "Island"),
        "Hallowed Fountain",
        "Swamp",
        "Opt",
        False,
        "Plains",
    ),
    (
        "Bleachbone Verge",
        B,
        W,
        ("Plains", "Swamp"),
        "Godless Shrine",
        "Forest",
        "Swords to Plowshares",
        True,
        "Swamp",
    ),
    (
        "Blazemire Verge",
        B,
        R,
        ("Swamp", "Mountain"),
        "Blood Crypt",
        "Plains",
        "Lightning Bolt",
        True,
        "Swamp",
    ),
    (
        "Wastewood Verge",
        G,
        B,
        ("Swamp", "Forest"),
        "Overgrown Tomb",
        "Plains",
        "Dark Ritual",
        False,
        "Forest",
    ),
]
IDS = [row[0] for row in VERGES]
TEXT = "{} requires {}"


def _board(alice, bob=None, hand=None):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=alice, hand=hand or [], library=["Plains"] * 6)
        .player("bob", battlefield=bob or [], library=["Plains"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _floating(scenario):
    return scenario.player("alice").mana_pool.floating


@pytest.mark.parametrize(
    "verge,first,second,pair,nonbasic,other,spell,targeted,filler", VERGES, ids=IDS
)
def test_the_first_colour_is_unconditional(
    verge, first, second, pair, nonbasic, other, spell, targeted, filler
):
    scenario = _board([verge])
    card = scenario.find(verge, Zone.BATTLEFIELD)
    assert scenario.why_cannot_activate(card, index=0) is None
    scenario.activate(card, index=0)
    assert _floating(scenario) == {first: 1}


@pytest.mark.parametrize(
    "verge,first,second,pair,nonbasic,other,spell,targeted,filler", VERGES, ids=IDS
)
def test_the_second_colour_is_refused_alone_and_with_a_land_of_neither_type(
    verge, first, second, pair, nonbasic, other, spell, targeted, filler
):
    for board in ([verge], [verge, other]):
        scenario = _board(board)
        card = scenario.find(verge, Zone.BATTLEFIELD)
        refusal = scenario.why_cannot_activate(card, index=1)
        assert refusal is not None and "activation restriction" in refusal
        with pytest.raises(ValueError):
            scenario.activate(card, index=1)
        assert _floating(scenario) == {}


@pytest.mark.parametrize(
    "verge,first,second,pair,nonbasic,other,spell,targeted,filler", VERGES, ids=IDS
)
@pytest.mark.parametrize("which", [0, 1])
def test_the_second_colour_works_with_either_named_land(
    verge, first, second, pair, nonbasic, other, spell, targeted, filler, which
):
    scenario = _board([verge, pair[which]])
    card = scenario.find(verge, Zone.BATTLEFIELD)
    assert scenario.why_cannot_activate(card, index=1) is None
    scenario.activate(card, index=1)
    assert _floating(scenario) == {second: 1}
    assert scenario.player("alice").life == 20, "a Verge has no damage rider"


@pytest.mark.parametrize(
    "verge,first,second,pair,nonbasic,other,spell,targeted,filler", VERGES, ids=IDS
)
def test_a_nonbasic_land_with_the_subtype_counts(
    verge, first, second, pair, nonbasic, other, spell, targeted, filler
):
    scenario = _board([verge, nonbasic])
    card = scenario.find(verge, Zone.BATTLEFIELD)
    assert scenario.why_cannot_activate(card, index=1) is None
    scenario.activate(card, index=1)
    assert _floating(scenario) == {second: 1}


@pytest.mark.parametrize(
    "verge,first,second,pair,nonbasic,other,spell,targeted,filler", VERGES, ids=IDS
)
def test_losing_the_land_mid_turn_turns_the_second_ability_off(
    verge, first, second, pair, nonbasic, other, spell, targeted, filler
):
    scenario = _board([verge, pair[0]])
    card = scenario.find(verge, Zone.BATTLEFIELD)
    assert scenario.why_cannot_activate(card, index=1) is None
    scenario.game.destroy(scenario.find(pair[0], Zone.BATTLEFIELD))
    assert scenario.why_cannot_activate(card, index=1) is not None
    with pytest.raises(ValueError):
        scenario.activate(card, index=1)
    scenario.activate(card, index=0)
    assert _floating(scenario) == {first: 1}


def _cast_with_auto(scenario, spell, targeted):
    targets = [scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "bob")] if targeted else None
    if spell == "Lightning Bolt":
        targets = ["bob"]
    return scenario.cast_onto_stack(spell, username="alice", targets=targets, auto=True)


@pytest.mark.parametrize(
    "verge,first,second,pair,nonbasic,other,spell,targeted,filler", VERGES, ids=IDS
)
def test_the_auto_payer_uses_the_second_colour_only_when_available(
    verge, first, second, pair, nonbasic, other, spell, targeted, filler
):
    bob = ["Llanowar Elves"]
    refused = _board([verge, other], bob=bob, hand=[spell])
    with pytest.raises(ValueError):
        _cast_with_auto(refused, spell, targeted)
    assert refused.find(verge, Zone.BATTLEFIELD).untapped

    paid = _board([verge, filler], bob=bob, hand=[spell])
    _cast_with_auto(paid, spell, targeted)
    assert paid.find(verge, Zone.BATTLEFIELD).tapped, "the Verge made the second colour"
    assert paid.find(filler, Zone.BATTLEFIELD).untapped
