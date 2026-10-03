"""Lands whose mana is filtered, taxed or restricted: Grove of the Burnwillows,
Flooded Grove and Castle Doom.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file.

- **CR 605.1a / CR 605.3b** - each `{T}: Add ...` is a mana ability: it never
  uses the stack, so its extra sentence ("Each opponent gains 1 life.") happens
  as part of activating it.
- **CR 106.1b** - the six types of mana; Grove's coloured ability offers {R} or
  {G}, never another.
- **CR 106.6** - mana "restrict[ed] [in] how that mana can be spent" is still
  mana of its type. Castle Doom's any-colour mana is spendable only on an
  artifact spell, and the engine says why it refuses anything else.
- **CR 602.5d / CR 307.5** - "Activate only as a sorcery": main phase of the
  controller's turn with an empty stack.
- **CR 701.21a** - sacrificing is a cost, paid on activation.
- **CR 111.1** - Doombot is a token, not a card.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.card import Type
from magic_cards_model.models.token import is_token
from tests.scenarios.harness import Scenario

# -- Grove of the Burnwillows -------------------------------------------------


def _grove_board(*, extra_players: bool = False) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grove of the Burnwillows"], library=["Forest"])
        .player("bob", life=20, library=["Forest"])
    )
    if extra_players:
        scenario.player("carol", life=20, library=["Forest"])
    return scenario


def _ready(scenario, name: str, username: str = "alice"):
    permanent = scenario.find(name, Zone.BATTLEFIELD, username)
    permanent.summoning_sick = False
    return permanent


def test_grove_coloured_mana_adds_red_and_the_opponent_gains_one_life():
    scenario = _grove_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grove = _ready(scenario, "Grove of the Burnwillows")

    ability = scenario.activate(grove, index=1, color=Color.RED)

    assert ability is None, "CR 605.3b: a mana ability never uses the stack"
    assert scenario.player("alice").mana_pool.floating == {Color.RED: 1}
    assert grove.tapped
    assert scenario.player("bob").life == 21
    assert scenario.player("alice").life == 20


def test_grove_coloured_mana_can_be_green_instead():
    scenario = _grove_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grove = _ready(scenario, "Grove of the Burnwillows")

    scenario.activate(grove, index=1, color=Color.GREEN)

    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 1}
    assert scenario.player("bob").life == 21


def test_grove_colourless_ability_gives_nobody_life():
    scenario = _grove_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grove = _ready(scenario, "Grove of the Burnwillows")

    scenario.activate(grove, index=0)

    assert scenario.player("alice").mana_pool.floating == {Color.COLORLESS: 1}
    assert scenario.player("bob").life == 20


def test_grove_gives_each_opponent_a_life_in_a_three_player_game():
    scenario = _grove_board(extra_players=True).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grove = _ready(scenario, "Grove of the Burnwillows")

    scenario.activate(grove, index=1, color=Color.RED)

    assert scenario.player("bob").life == 21
    assert scenario.player("carol").life == 21
    assert scenario.player("alice").life == 20


def test_grove_refuses_a_colour_it_does_not_offer():
    """CR 106.1b: the ability names {R} or {G}; blue is not on offer."""
    scenario = _grove_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grove = _ready(scenario, "Grove of the Burnwillows")

    with pytest.raises(ValueError):
        scenario.activate(grove, index=1, color=Color.BLUE)

    assert scenario.player("bob").life == 20
    assert scenario.player("alice").mana_pool.floating == {}


def test_a_tapped_grove_cannot_gain_the_opponent_life_again():
    scenario = _grove_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grove = _ready(scenario, "Grove of the Burnwillows")
    scenario.activate(grove, index=1, color=Color.RED)

    with pytest.raises(ValueError):
        scenario.activate(grove, index=1, color=Color.RED)

    assert scenario.player("bob").life == 21


# -- Flooded Grove ------------------------------------------------------------


def _flooded_board(*, extra: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Flooded Grove", *(extra if extra is not None else ["Forest"])],
            library=["Forest"],
        )
        .player("bob", library=["Forest"])
    )


@pytest.mark.parametrize(
    "pair",
    [
        (Color.GREEN, Color.GREEN),
        (Color.GREEN, Color.BLUE),
        (Color.BLUE, Color.BLUE),
    ],
)
def test_flooded_grove_filters_one_hybrid_mana_into_exactly_the_chosen_pair(pair):
    scenario = _flooded_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grove = _ready(scenario, "Flooded Grove")
    (forest,) = scenario.untapped_sources("Forest")

    scenario.activate(grove, forest, index=1, color=pair)

    floating = scenario.player("alice").mana_pool.floating
    expected: dict[Color, int] = {}
    for colour in pair:
        expected[colour] = expected.get(colour, 0) + 1
    assert floating == expected
    assert grove.tapped
    assert forest.tapped, "the {G/U} was paid by tapping the Forest, a net +1 mana"


def test_flooded_grove_can_be_paid_with_an_island_too():
    scenario = _flooded_board(extra=["Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grove = _ready(scenario, "Flooded Grove")
    (island,) = scenario.untapped_sources("Island")

    scenario.activate(grove, island, index=1, color=(Color.GREEN, Color.BLUE))

    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 1, Color.BLUE: 1}


def test_flooded_grove_refuses_a_pair_outside_green_and_blue():
    scenario = _flooded_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grove = _ready(scenario, "Flooded Grove")
    (forest,) = scenario.untapped_sources("Forest")

    with pytest.raises(ValueError):
        scenario.activate(grove, forest, index=1, color=(Color.RED, Color.GREEN))

    assert scenario.player("alice").mana_pool.floating == {}


def test_flooded_grove_filter_cannot_be_paid_by_a_source_of_the_wrong_colour():
    """{G/U} is paid with green or blue mana; a Mountain cannot pay it."""
    scenario = _flooded_board(extra=["Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grove = _ready(scenario, "Flooded Grove")
    (mountain,) = scenario.untapped_sources("Mountain")

    with pytest.raises(ValueError):
        scenario.activate(grove, mountain, index=1, color=(Color.GREEN, Color.GREEN))

    assert scenario.player("alice").mana_pool.floating == {}


def test_flooded_grove_filter_needs_its_hybrid_payment_at_all():
    scenario = _flooded_board(extra=[]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grove = _ready(scenario, "Flooded Grove")

    with pytest.raises(ValueError):
        scenario.activate(grove, index=1, color=(Color.GREEN, Color.GREEN))

    assert scenario.player("alice").mana_pool.floating == {}


def test_flooded_grove_colourless_ability_needs_no_payment():
    scenario = _flooded_board(extra=[]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grove = _ready(scenario, "Flooded Grove")

    scenario.activate(grove, index=0)

    assert scenario.player("alice").mana_pool.floating == {Color.COLORLESS: 1}


# -- Castle Doom --------------------------------------------------------------


def _castle_board(*, hand: list[str], battlefield: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=hand,
            battlefield=["Castle Doom", *(battlefield or [])],
            library=["Forest"],
        )
        .player("bob", library=["Forest"])
    )


def test_castle_doom_mana_pays_for_an_artifact_spell():
    scenario = _castle_board(hand=["Sol Ring"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    castle = _ready(scenario, "Castle Doom")
    scenario.activate(castle, index=1, color=Color.BLUE)

    scenario.cast("Sol Ring", "alice").begin_paying().pay()

    assert scenario.player("alice").mana_pool.floating == {}
    assert scenario.stack_names() == ["Sol Ring"]


def test_castle_doom_mana_is_refused_for_a_non_artifact_spell_with_the_reason():
    scenario = _castle_board(hand=["Opt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    castle = _ready(scenario, "Castle Doom")
    scenario.activate(castle, index=1, color=Color.BLUE)

    with pytest.raises(ValueError, match="Spend this mana only to cast an artifact spell"):
        scenario.cast("Opt", "alice").begin_paying().pay()


def test_castle_doom_mana_is_still_a_colour_of_mana_in_the_pool():
    """CR 106.6: the restriction "doesn't affect the mana's type"."""
    scenario = _castle_board(hand=[]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    castle = _ready(scenario, "Castle Doom")
    scenario.activate(castle, index=1, color=Color.GREEN)

    pool = scenario.player("alice").mana_pool
    assert pool.restricted[0].amounts == {Color.GREEN: 1}
    assert [entry.restriction.text for entry in pool.restricted] == [
        "Spend this mana only to cast an artifact spell."
    ]


def test_castle_doom_colourless_ability_is_unrestricted():
    scenario = _castle_board(hand=["Opt"], battlefield=["Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    castle = _ready(scenario, "Castle Doom")
    scenario.activate(castle, index=0)

    assert scenario.player("alice").mana_pool.floating == {Color.COLORLESS: 1}
    assert scenario.player("alice").mana_pool.restricted == []


def _doombot_board(*, battlefield: list[str] | None = None) -> Scenario:
    return _castle_board(
        hand=[],
        battlefield=battlefield if battlefield is not None else ["Sol Ring", *["Forest"] * 3],
    )


def _make_doombot(scenario):
    castle = _ready(scenario, "Castle Doom")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    forests = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.activate(castle, *forests, index=2, sacrificing=[ring])
    scenario.pass_until_resolved()
    return castle, ring


def test_castle_doom_makes_a_three_three_colourless_robot_villain_artifact_creature_token():
    scenario = _doombot_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    castle, ring = _make_doombot(scenario)

    assert castle.tapped
    assert ring.zone is Zone.GRAVEYARD, "CR 701.21a: the artifact was sacrificed as a cost"
    (doombot,) = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.card.name == "Doombot"
    ]
    assert is_token(doombot), "CR 111.1"
    computed = scenario.game.computed_board().of(doombot)
    assert (computed.power, computed.toughness) == (3, 3)
    assert computed.colors == ()
    assert Type.ARTIFACT in computed.types and Type.CREATURE in computed.types
    assert {"Robot", "Villain"} <= set(computed.subtypes)


def test_castle_doom_ability_is_sorcery_speed_only():
    """CR 602.5d / 307.5: not on the opponent's turn, not in combat."""
    scenario = _doombot_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    castle = _ready(scenario, "Castle Doom")
    assert scenario.why_cannot_activate(castle, 2) is None

    scenario.advance()  # beginning of combat
    assert scenario.why_cannot_activate(castle, 2) is not None


def test_castle_doom_ability_is_refused_with_a_non_empty_stack():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Opt"],
            battlefield=["Castle Doom", "Sol Ring", "Island"],
            library=["Forest"] * 3,
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    castle = _ready(scenario, "Castle Doom")
    scenario.cast_onto_stack("Opt", *scenario.untapped_sources("Island"))

    assert scenario.why_cannot_activate(castle, 2) is not None


def test_castle_doom_ability_needs_an_artifact_to_sacrifice():
    scenario = _doombot_board(battlefield=["Forest", "Forest", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    castle = _ready(scenario, "Castle Doom")
    forests = scenario.untapped_sources("Forest", "Forest", "Forest")

    with pytest.raises(ValueError):
        scenario.activate(castle, *forests, index=2)

    assert not castle.tapped
    assert scenario.stack_names() == []


def test_castle_doom_cannot_sacrifice_a_non_artifact():
    scenario = _doombot_board(battlefield=["Forest", "Forest", "Forest", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    castle = _ready(scenario, "Castle Doom")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")

    with pytest.raises(ValueError):
        scenario.activate(castle, index=2, sacrificing=[forest])

    assert forest.zone is Zone.BATTLEFIELD


# -- The readers widened here, on a second printing / the bare template -------


def test_sunken_ruins_filters_through_the_same_multi_mana_choice():
    """Second printing of the filter-land template (`{U/B}, {T}: Add {U}{U},
    {U}{B}, or {B}{B}.`): the pair is spelled out by the caller, order free."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Sunken Ruins", "Swamp"], library=["Forest"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ruins = _ready(scenario, "Sunken Ruins")
    (swamp,) = scenario.untapped_sources("Swamp")

    scenario.activate(ruins, swamp, index=1, color=(Color.BLACK, Color.BLUE))

    assert scenario.player("alice").mana_pool.floating == {Color.BLUE: 1, Color.BLACK: 1}


def test_each_opponent_rider_reads_the_lose_variant_too():
    """No legal printing carries "Each opponent loses N life." after an Add
    (Grove of the Burnwillows is the only card with the opponents template at
    all), so the reader's second verb is proven on the bare sentence."""
    from magic_cards_model.machines.abilities import _parse_mana_rider

    rider, unparsed, _spend = _parse_mana_rider("Each opponent loses 2 life.")
    assert unparsed is None
    assert (rider.kind, rider.amount) == ("opponents_lose_life", 2)
    rider, unparsed, _spend = _parse_mana_rider("Each opponent gains 1 life.")
    assert (rider.kind, rider.amount) == ("opponents_gain_life", 1)
