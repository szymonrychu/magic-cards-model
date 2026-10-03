"""Breathless Knight: "Whenever this creature or another creature you control
enters, if that creature entered from a graveyard or you cast it from a
graveyard, put a +1/+1 counter on this creature."

The intervening *if* (CR 603.4) asks two facts about the entering object
itself: the zone the enters event moved it from (`GameEvent.origin_zone`),
and the zone its own spell was cast from (`CastRecord.origin_zone`, carried
onto the permanent by CR 400.7d). "That creature" is the trigger event's
subject - the same anaphor Prized Amalgam's "it" already named - and both
facts are fixed at the event, so CR 603.4's recheck on resolution reads the
same answer even after the creature has gone.

CR numbers verified with `mise run rules:find` in the session that wrote
this file: CR 603.4, CR 400.7d, CR 702.138a (escape casts from a
graveyard).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

KNIGHT = "Breathless Knight"
URO = "Uro, Titan of Nature's Wrath"


def _scenario(
    *,
    battlefield=(KNIGHT,),
    hand=("Unearth",),
    graveyard=("Grizzly Bears",),
    lands=("Swamp",) * 4,
    bob_graveyard=(),
):
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
        .player("bob", library=["Island"] * 8, graveyard=list(bob_graveyard))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _resolve_all(scenario: PlayedScenario) -> None:
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _counters(scenario: PlayedScenario) -> int:
    return scenario.find(KNIGHT, Zone.BATTLEFIELD, "alice").counter_count("+1/+1")


def test_a_reanimated_creature_grows_the_knight():
    scenario = _scenario()
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.cast_and_resolve("Unearth", *scenario.untapped_sources("Swamp"), targets=[bears])
    _resolve_all(scenario)

    assert _counters(scenario) == 1
    assert scenario.game.intervening_if_notices == []


def test_a_creature_cast_from_hand_does_not():
    scenario = _scenario(hand=("Grizzly Bears",), graveyard=(), lands=("Forest", "Forest"))
    scenario.cast_and_resolve("Grizzly Bears", *scenario.untapped_sources("Forest", "Forest"))
    _resolve_all(scenario)

    assert _counters(scenario) == 0
    assert scenario.game.intervening_if_notices == []


def test_the_knight_itself_returning_from_a_graveyard_counts():
    """ "this creature ... enters" - the Knight reanimated is "that creature"."""
    scenario = _scenario(battlefield=(), graveyard=(KNIGHT,))
    knight = scenario.find(KNIGHT, Zone.GRAVEYARD, "alice")
    scenario.cast_and_resolve("Unearth", *scenario.untapped_sources("Swamp"), targets=[knight])
    _resolve_all(scenario)

    assert _counters(scenario) == 1


def test_a_creature_cast_from_a_graveyard_counts():
    """Uro cast with escape is cast from a graveyard; it entered from the
    stack, so only the "you cast it from a graveyard" half is true."""
    scenario = _scenario(
        hand=(),
        graveyard=(URO, *["Mishra's Bauble"] * 5),
        lands=("Forest", "Forest", "Island", "Island"),
    )
    fuel = [state for state in scenario.player("alice").graveyard if state.name != URO]
    casting = scenario.cast(URO, from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Escape", choosing=fuel[:5])
    scenario.pay_with(
        casting.begin_paying(),
        *scenario.untapped_sources("Forest", "Forest", "Island", "Island"),
    )
    scenario.put_on_stack(casting)
    _resolve_all(scenario)

    assert scenario.find(URO, Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD
    assert _counters(scenario) == 1


def test_an_opponents_reanimated_creature_does_not_trigger_it():
    scenario = _scenario(graveyard=(), bob_graveyard=("Grizzly Bears",))
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")
    scenario.game.put_onto_battlefield(bears, "bob")
    _resolve_all(scenario)

    assert _counters(scenario) == 0


def test_the_recheck_still_holds_after_the_creature_is_gone():
    """CR 603.4's second check reads the enters event's own facts: Lightning
    Bolt on the reanimated Bears in response does not stop the counter."""
    scenario = _scenario(hand=("Unearth", "Lightning Bolt"), lands=("Swamp", "Mountain"))
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.cast_and_resolve("Unearth", *scenario.untapped_sources("Swamp"), targets=[bears])
    scenario.game.put_triggers_on_stack()
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[bears]
    )
    scenario.state_based_actions()
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD

    _resolve_all(scenario)

    assert _counters(scenario) == 1
