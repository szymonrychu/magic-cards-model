"""Satoru, the Infiltrator: "Whenever Satoru and/or one or more other nontoken
creatures you control enter, if none of them were cast or no mana was spent
to cast them, draw a card."

The intervening *if* (CR 603.4) is about "them" - every creature the one
enters event put onto the battlefield that the trigger condition names
(CR 603.6a, `GameEvent.entered_together`). Each of them has to have been
either not cast at all, or cast with no mana spent (CR 601.2h, read off the
permanent's own `CastRecord`, carried onto it by CR 400.7d). Before this the
clause recorded an `InterveningIfNotice` and never triggered.

Both facts are fixed when the creatures enter; CR 603.4's recheck on
resolution reads the same answer, including after one of them has left
(a creature that left has no cast record any more, so it is read through
the persisted event's own snapshot taken as it entered).

CR numbers verified with `mise run rules:find` in the session that wrote
this file: CR 603.4, CR 603.6a, CR 601.2h, CR 400.7d.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

SATORU = "Satoru, the Infiltrator"


def _scenario(
    *, battlefield=(SATORU,), hand=(), graveyard=(), lands=("Swamp",) * 4
) -> PlayedScenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[*battlefield, *lands],
            hand=list(hand),
            graveyard=list(graveyard),
            library=["Swamp"] * 8,
        )
        .player("bob", library=["Island"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _resolve_all(scenario: PlayedScenario) -> None:
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _hand(scenario: PlayedScenario) -> int:
    return len(scenario.player("alice").hand)


def test_a_reanimated_creature_was_not_cast():
    scenario = _scenario(hand=("Unearth",), graveyard=("Grizzly Bears",))
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.cast_and_resolve("Unearth", *scenario.untapped_sources("Swamp"), targets=[bears])
    before = _hand(scenario)

    _resolve_all(scenario)

    assert _hand(scenario) == before + 1
    assert scenario.game.intervening_if_notices == []


def test_a_creature_cast_with_mana_does_not_draw():
    scenario = _scenario(hand=("Grizzly Bears",), lands=("Forest", "Forest"))
    scenario.cast_and_resolve("Grizzly Bears", *scenario.untapped_sources("Forest", "Forest"))
    before = _hand(scenario)

    _resolve_all(scenario)

    assert _hand(scenario) == before
    assert scenario.game.intervening_if_notices == []


def test_a_creature_cast_for_zero_mana_draws():
    """Ornithopter costs {0}: it was cast, but no mana was spent on it."""
    scenario = _scenario(hand=("Ornithopter",))
    scenario.cast_and_resolve("Ornithopter")
    before = _hand(scenario)

    _resolve_all(scenario)

    assert _hand(scenario) == before + 1


def test_satoru_itself_put_onto_the_battlefield_draws():
    scenario = _scenario(battlefield=(), hand=(SATORU,))
    scenario.put_onto_battlefield(SATORU)
    before = _hand(scenario)

    _resolve_all(scenario)

    assert _hand(scenario) == before + 1


def test_satoru_cast_with_mana_does_not_draw():
    scenario = _scenario(battlefield=(), hand=(SATORU,), lands=("Island", "Swamp"))
    scenario.cast_and_resolve(SATORU, *scenario.untapped_sources("Island", "Swamp"))
    before = _hand(scenario)

    _resolve_all(scenario)

    assert _hand(scenario) == before


def test_a_token_entering_does_not_trigger_it():
    """ "nontoken creatures": Case of the Stashed Skeleton's Skeleton token
    (and the Case itself, not a creature) enter without triggering it."""
    scenario = _scenario(hand=("Case of the Stashed Skeleton",))
    scenario.cast_and_resolve(
        "Case of the Stashed Skeleton", *scenario.untapped_sources("Swamp", "Swamp")
    )
    before = _hand(scenario)

    _resolve_all(scenario)

    assert any(permanent.token for permanent in scenario.game.permanents_controlled_by("alice"))
    assert _hand(scenario) == before


def test_creatures_returned_together_trigger_once():
    """CR 603.6a: Fix What's Broken returns both at once - one event, one
    trigger, one card."""
    scenario = _scenario(
        hand=("Fix What's Broken",),
        graveyard=("Grizzly Bears", "Amoeboid Changeling"),
        lands=("Swamp", "Swamp", "Plains", "Plains"),
    )
    casting = scenario.cast("Fix What's Broken", username="alice")
    casting.determine_cost(x_value=2)
    scenario.pay_with(
        casting.begin_paying(), *scenario.untapped_sources("Swamp", "Swamp", "Plains", "Plains")
    )
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD
    before = _hand(scenario)

    _resolve_all(scenario)

    assert _hand(scenario) == before + 1


def test_the_recheck_still_holds_after_the_creature_is_gone():
    scenario = _scenario(
        hand=("Unearth", "Lightning Bolt"),
        graveyard=("Grizzly Bears",),
        lands=("Swamp", "Mountain"),
    )
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.cast_and_resolve("Unearth", *scenario.untapped_sources("Swamp"), targets=[bears])
    scenario.game.put_triggers_on_stack()
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[bears]
    )
    scenario.state_based_actions()
    before = _hand(scenario)

    _resolve_all(scenario)

    assert _hand(scenario) == before + 1
