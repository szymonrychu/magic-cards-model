"""Scenario: "Artifacts you control become artifact creatures with base power
and toughness 5/5 until end of turn." - Tezzeret the Seeker's -5 and The
Antiquities War's chapter III.

CR 205.1b ("artifact creature" adds both card types and keeps the rest), CR
613.1d (layer 4) and CR 613.4b (the base power and toughness, sublayer 7b), CR
611.2c (the group is the artifacts its controller has as the effect begins, so
an artifact that arrives later is not animated), CR 514.2 (until end of turn).
A card-type group ("Artifacts") is read by the same subject grammar as the
static anthems (`layers/group_grants.parse_group`).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def chars(scenario, name, owner):
    return scenario.game.characteristics_of(scenario.find(name, Zone.BATTLEFIELD, owner))


def resolve_everything(scenario):
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def test_tezzerets_minus_five_animates_only_the_controllers_artifacts():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tezzeret the Seeker", "Mind Stone", "Grizzly Bears"],
            library=["Island"] * 4,
        )
        .player("bob", battlefield=["Mind Stone"], library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tezzeret = scenario.creature("Tezzeret the Seeker", "alice")
    tezzeret.add_counters(Counter.LOYALTY, 2)
    abilities = scenario.game.activated_abilities(tezzeret)
    index = next(i for i, a in enumerate(abilities) if a.raw.startswith("−5:"))

    scenario.activate(tezzeret, index=index, username="alice")
    scenario.resolve_top()

    stone = chars(scenario, "Mind Stone", "alice")
    assert (stone.power, stone.toughness) == (5, 5)
    assert {Type.ARTIFACT, Type.CREATURE} <= set(stone.types)
    assert chars(scenario, "Mind Stone", "bob").power is None
    assert Type.CREATURE not in chars(scenario, "Mind Stone", "bob").types
    assert (chars(scenario, "Grizzly Bears", "alice").power) == 2


def test_an_artifact_that_arrives_afterwards_is_not_animated():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sol Ring"],
            battlefield=["Tezzeret the Seeker", "Mind Stone"],
            library=["Island"] * 4,
        )
        .player("bob", library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tezzeret = scenario.creature("Tezzeret the Seeker", "alice")
    tezzeret.add_counters(Counter.LOYALTY, 2)
    abilities = scenario.game.activated_abilities(tezzeret)
    index = next(i for i, a in enumerate(abilities) if a.raw.startswith("−5:"))
    scenario.activate(tezzeret, index=index, username="alice")
    scenario.resolve_top()

    scenario.put_onto_battlefield("Sol Ring", "alice")

    assert Type.CREATURE in chars(scenario, "Mind Stone", "alice").types
    assert Type.CREATURE not in chars(scenario, "Sol Ring", "alice").types


def test_the_animation_ends_with_the_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tezzeret the Seeker", "Mind Stone"],
            library=["Island"] * 6,
        )
        .player("bob", library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tezzeret = scenario.creature("Tezzeret the Seeker", "alice")
    tezzeret.add_counters(Counter.LOYALTY, 2)
    abilities = scenario.game.activated_abilities(tezzeret)
    index = next(i for i, a in enumerate(abilities) if a.raw.startswith("−5:"))
    scenario.activate(tezzeret, index=index, username="alice")
    scenario.resolve_top()
    assert Type.CREATURE in chars(scenario, "Mind Stone", "alice").types

    turn = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turn:
        scenario.advance()

    assert Type.CREATURE not in chars(scenario, "Mind Stone", "alice").types


def test_the_antiquities_war_chapter_three_animates_artifacts():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["The Antiquities War"],
            battlefield=["Mind Stone", "Sol Ring", "Grizzly Bears"],
            library=["Island"] * 6,
        )
        .player("bob", battlefield=["Mind Stone"], library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = scenario.put_onto_battlefield("The Antiquities War", "alice")
    resolve_everything(scenario)
    for _ in range(2):
        scenario.game.add_counters(saga, Counter.LORE, 1)
        resolve_everything(scenario)

    for name in ("Mind Stone", "Sol Ring"):
        animated = chars(scenario, name, "alice")
        assert (animated.power, animated.toughness) == (5, 5)
    assert Type.CREATURE not in chars(scenario, "Mind Stone", "bob").types
