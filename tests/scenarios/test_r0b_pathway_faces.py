"""R0b T2: Pathways - a modal double-faced land plays as either land face.

Rules verified with `mise run rules:find`:

- **CR 712.12** - a player playing a modal double-faced card as a land chooses
  one of its faces that's a land before putting it onto the battlefield, and it
  enters with that face up. A Pathway's front is *also* a land, so the choice
  is real: the back face must be reachable (`play_land(..., face=...)`).
- **CR 712.8f** - an MDFC on the battlefield has only the characteristics of
  the face that's up, so only that face's mana ability exists.
- **CR 712.8d** - a double-faced permanent with its front face up has only the
  front face's characteristics; the chosen face stays up (nothing here
  transforms it).
- **CR 305.2** - playing either face uses the one land drop.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.action import ActionKind
from tests.scenarios.harness import Scenario

W, U, B, R, G = Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN

# card name, front face, its colour, back face, its colour
PATHWAYS = [
    ("Riverglide Pathway", "Riverglide Pathway", U, "Lavaglide Pathway", R),
    ("Brightclimb Pathway", "Brightclimb Pathway", W, "Grimclimb Pathway", B),
    ("Branchloft Pathway", "Branchloft Pathway", G, "Boulderloft Pathway", W),
    ("Darkbore Pathway", "Darkbore Pathway", B, "Slitherbore Pathway", G),
]
IDS = [row[0] for row in PATHWAYS]
ALL = (W, U, B, R, G)


def _board(hand, battlefield=()):
    scenario = (
        Scenario()
        .player("alice", hand=list(hand), battlefield=list(battlefield), library=["Plains"] * 6)
        .player("bob", library=["Plains"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _floating(scenario):
    return scenario.player("alice").mana_pool.floating


def _only_colour_is(scenario, land, colour):
    for other in ALL:
        if other is colour:
            continue
        with pytest.raises(ValueError):
            scenario.activate(land, index=0, color=other)
        land.tapped = False  # a refused colour still went through the tap cost
    assert _floating(scenario) == {}
    scenario.activate(land, index=0)
    assert _floating(scenario) == {colour: 1}


@pytest.mark.parametrize("card,front,front_colour,back,back_colour", PATHWAYS, ids=IDS)
def test_the_default_play_is_the_front_face(card, front, front_colour, back, back_colour):
    scenario = _board([card])
    land = scenario.play_land(card)
    assert land.zone is Zone.BATTLEFIELD
    assert land.name == front
    assert land.up_face_name == front
    assert len(scenario.game.activated_abilities(land)) == 1
    _only_colour_is(scenario, land, front_colour)


@pytest.mark.parametrize("card,front,front_colour,back,back_colour", PATHWAYS, ids=IDS)
def test_the_player_may_choose_the_back_face(card, front, front_colour, back, back_colour):
    scenario = _board([card])
    land = scenario.play_land(card, face=back)
    assert land.name == back
    assert land.up_face_name == back
    assert len(scenario.game.activated_abilities(land)) == 1
    _only_colour_is(scenario, land, back_colour)
    assert not scenario.game.can_play_land("alice"), "one land drop either way (CR 305.2)"


@pytest.mark.parametrize("card,front,front_colour,back,back_colour", PATHWAYS, ids=IDS)
def test_the_chosen_face_stays_across_turns(card, front, front_colour, back, back_colour):
    scenario = _board([card])
    land = scenario.play_land(card, face=back)
    scenario.advance()
    assert land.zone is Zone.BATTLEFIELD
    assert land.name == back


@pytest.mark.parametrize("card,front,front_colour,back,back_colour", PATHWAYS, ids=IDS)
def test_both_faces_are_offered_as_land_plays(card, front, front_colour, back, back_colour):
    scenario = _board([card])
    pathway = scenario.find(card, Zone.HAND, "alice")
    offers = [
        action
        for action in scenario.game.legal_actions("alice")
        if action.kind is ActionKind.PLAY_LAND and action.card_id == pathway.id
    ]
    assert {offer.land_face for offer in offers} == {None, back}


@pytest.mark.parametrize("card,front,front_colour,back,back_colour", PATHWAYS, ids=IDS)
def test_a_name_that_is_not_a_land_face_is_refused(card, front, front_colour, back, back_colour):
    scenario = _board([card])
    with pytest.raises(ValueError, match="CR 712.12"):
        scenario.play_land(card, face="Island")
    assert scenario.game.can_play_land("alice"), "a refused play uses no land drop"
    assert scenario.find(card, Zone.HAND, "alice").zone is Zone.HAND


def test_a_single_faced_land_has_no_face_to_choose():
    scenario = _board(["Island"])
    with pytest.raises(ValueError, match="CR 712.12"):
        scenario.play_land("Island", face="Island")


SPELLS = {
    U: "Opt",
    R: "Lightning Bolt",
    B: "Dark Ritual",
    W: "Swords to Plowshares",
    G: "Giant Growth",
}


def _cast_auto(scenario, colour):
    spell = SPELLS[colour]
    if spell == "Lightning Bolt":
        targets = ["bob"]
    elif spell in ("Swords to Plowshares", "Giant Growth"):
        targets = [scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "bob")]
    else:
        targets = None
    return scenario.cast_onto_stack(spell, username="alice", targets=targets, auto=True)


def _with_elves(card, colour):
    scenario = (
        Scenario()
        .player("alice", hand=[card, SPELLS[colour]], library=["Plains"] * 6)
        .player("bob", battlefield=["Llanowar Elves"], library=["Plains"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


@pytest.mark.parametrize("card,front,front_colour,back,back_colour", PATHWAYS, ids=IDS)
@pytest.mark.parametrize("use_back", [False, True])
def test_the_auto_payer_follows_the_face_that_is_up(
    card, front, front_colour, back, back_colour, use_back
):
    up, down = (back_colour, front_colour) if use_back else (front_colour, back_colour)
    face = back if use_back else None

    scenario = _with_elves(card, up)
    land = scenario.play_land(card, face=face)
    _cast_auto(scenario, up)
    assert land.tapped

    scenario = _with_elves(card, down)
    land = scenario.play_land(card, face=face)
    with pytest.raises(ValueError):
        _cast_auto(scenario, down)
    assert land.untapped


def test_a_second_printing_of_the_template_chooses_its_back_face_too():
    """Clearwater Pathway // Murkwater Pathway (not a listed card): same
    mechanism, no card-specific code."""
    scenario = _board(["Clearwater Pathway"])
    land = scenario.play_land("Clearwater Pathway", face="Murkwater Pathway")
    assert land.name == "Murkwater Pathway"
    _only_colour_is(scenario, land, B)
