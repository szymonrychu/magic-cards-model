"""Void's intervening *if* (CR 603.4): "if a nonland permanent left the
battlefield this turn or a spell was warped this turn".

Void is an ability word (CR 207.2c) with no rules meaning of its own; the
clause after it is two turn-history facts joined by "or":

- **"a nonland permanent left the battlefield this turn"** - any permanent,
  whoever controlled it, by any route off the battlefield (destroyed,
  exiled, bounced, sacrificed). Read off `Game.turn_history`'s
  `"left_battlefield"` entries, written at `Game._note_left_battlefield`
  (the one choke point every route reaches) with the permanent's
  characteristics as it last existed there (CR 603.10a), so "nonland" is
  the departed object's own type, not the card's afterwards.
- **"a spell was warped this turn"** - CR 702.185c: "This means that a
  spell was cast for its warp cost this turn." Recorded as the cast event
  is raised, off the spell's own `CastRecord` (warp keyword, cost paid).

Before this, every Void trigger recorded an `InterveningIfNotice` and never
triggered. Each card's effect is proved to resolve here as well. Both facts
only ever accumulate within a turn, so the CR 608.2a recheck on resolution
reads the same answer the trigger did; a turn that had neither fact never
triggers at all.

CR numbers verified with `mise run rules:find` in the session that wrote
this file: CR 603.4, CR 603.10a, CR 702.185a, CR 702.185c, CR 707.12.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import parse_abilities
from magic_cards_model.machines.triggers import TriggeredAbility, intervening_if_readable
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import PlayedScenario, Scenario

VOID_CARDS = (
    "Elegy Acolyte",
    "Hylderblade",
    "Insatiable Skittermaw",
    "Interceptor Mechan",
    "Kavaron Skywarden",
    "Roving Actuator",
    "Voidforged Titan",
)


def _scenario(*battlefield: str, hand=(), graveyard=(), bob=("Grizzly Bears",)) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=list(battlefield),
            hand=list(hand),
            graveyard=list(graveyard),
            library=["Swamp"] * 8,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _resolve_all(scenario: PlayedScenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def _to_end_step(scenario: PlayedScenario) -> None:
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # alice's end step begins
    _resolve_all(scenario)


def _counters(scenario: PlayedScenario, name: str) -> int:
    return scenario.find(name, Zone.BATTLEFIELD, "alice").counter_count("+1/+1")


def test_every_void_clause_is_read():
    for name in VOID_CARDS:
        void = [
            ability
            for ability in parse_abilities(card(name))
            if isinstance(ability, TriggeredAbility) and ability.intervening_if
        ]
        assert void, name
        for ability in void:
            assert intervening_if_readable(card(name), ability), name


def test_no_departure_and_no_warp_means_no_trigger_and_no_notice():
    scenario = _scenario("Kavaron Skywarden", "Swamp")

    _to_end_step(scenario)

    assert _counters(scenario, "Kavaron Skywarden") == 0
    assert scenario.game.intervening_if_notices == []


def test_an_exiled_opposing_creature_counts():
    """Exile is a route off the battlefield the graveyard/hand ledgers never
    saw - Path to Exile on bob's Bears."""
    scenario = _scenario("Insatiable Skittermaw", "Plains", hand=("Path to Exile",))
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_and_resolve("Path to Exile", *scenario.untapped_sources("Plains"), targets=[bears])

    _to_end_step(scenario)

    assert _counters(scenario, "Insatiable Skittermaw") == 1
    assert scenario.game.intervening_if_notices == []


def test_a_land_leaving_does_not_count():
    scenario = _scenario("Interceptor Mechan", "Swamp", "Mountain")
    scenario.game.return_to_hand(scenario.find("Mountain", Zone.BATTLEFIELD, "alice"))

    _to_end_step(scenario)

    assert _counters(scenario, "Interceptor Mechan") == 0
    assert scenario.game.intervening_if_notices == []


def test_a_nonland_departure_puts_the_counter_on_interceptor_mechan():
    scenario = _scenario("Interceptor Mechan", "Swamp")
    scenario.game.return_to_hand(scenario.creature("Grizzly Bears", "bob"))

    _to_end_step(scenario)

    assert _counters(scenario, "Interceptor Mechan") == 1


def test_a_warped_spell_makes_elegy_acolytes_robot():
    """CR 702.185c: a spell cast for its warp cost this turn - Bygone
    Colossus cast for Warp {3}, and nothing has left the battlefield yet
    when the end step begins (warp's own exile and Void share the step)."""
    scenario = _scenario(
        "Elegy Acolyte", "Island", "Island", "Island", hand=("Bygone Colossus",), bob=()
    )
    casting = scenario.cast("Bygone Colossus")
    casting.use_keyword("Warp")
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Island", "Island", "Island"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    _to_end_step(scenario)

    robots = [
        permanent
        for permanent in scenario.game.permanents_controlled_by("alice")
        if permanent.token and "Robot" in permanent.subtypes
    ]
    assert len(robots) == 1
    assert scenario.game.characteristics_of(robots[0]).power == 2
    assert scenario.game.intervening_if_notices == []


def test_a_spell_cast_for_its_mana_cost_is_not_warped():
    scenario = _scenario("Elegy Acolyte", *["Island"] * 9, hand=("Bygone Colossus",), bob=())
    scenario.cast_and_resolve("Bygone Colossus", auto=True)

    _to_end_step(scenario)

    assert not any(
        permanent.token for permanent in scenario.game.permanents_controlled_by("alice")
    )


def test_elegy_acolyte_without_either_fact_makes_nothing():
    scenario = _scenario("Elegy Acolyte", "Swamp")

    _to_end_step(scenario)

    assert not any(
        permanent.token for permanent in scenario.game.permanents_controlled_by("alice")
    )
    assert scenario.game.intervening_if_notices == []


def test_voidforged_titan_draws_and_loses_life_after_its_own_creature_died():
    scenario = _scenario("Voidforged Titan", "Grizzly Bears", bob=())
    scenario.game.destroy(scenario.creature("Grizzly Bears", "alice"))
    hand = len(scenario.player("alice").hand)
    life = scenario.player("alice").life

    _to_end_step(scenario)

    assert len(scenario.player("alice").hand) == hand + 1
    assert scenario.player("alice").life == life - 1


def test_voidforged_titan_does_nothing_without_the_condition():
    scenario = _scenario("Voidforged Titan", bob=())
    hand = len(scenario.player("alice").hand)

    _to_end_step(scenario)

    assert len(scenario.player("alice").hand) == hand
    assert scenario.game.intervening_if_notices == []


def test_hylderblade_attaches_itself_to_a_creature_you_control():
    scenario = _scenario("Hylderblade", "Llanowar Elves")
    scenario.game.sacrifice(scenario.creature("Grizzly Bears", "bob"))
    elves = scenario.creature("Llanowar Elves", "alice")
    scenario.choose_trigger_targets("Hylderblade", [elves])

    _to_end_step(scenario)

    blade = scenario.find("Hylderblade", Zone.BATTLEFIELD, "alice")
    assert blade.attached_to == elves.id
    assert scenario.game.characteristics_of(elves).power == 4
    assert scenario.game.characteristics_of(elves).toughness == 2


def test_hylderblade_stays_unattached_without_the_condition():
    scenario = _scenario("Hylderblade", "Llanowar Elves")

    _to_end_step(scenario)

    assert scenario.find("Hylderblade", Zone.BATTLEFIELD, "alice").attached_to is None


def test_kavaron_skywarden_gets_a_counter_after_a_departure():
    scenario = _scenario("Kavaron Skywarden")
    scenario.game.exile_permanent(scenario.creature("Grizzly Bears", "bob"))

    _to_end_step(scenario)

    assert _counters(scenario, "Kavaron Skywarden") == 1


def test_roving_actuator_casts_a_free_copy_of_a_cheap_instant():
    """The enters trigger with the condition true: Shock exiled from the
    graveyard, copied, and the copy cast for free at bob (CR 707.12)."""
    scenario = _scenario(
        *["Mountain"] * 4, hand=("Roving Actuator",), graveyard=("Shock",)
    )
    scenario.game.exile_permanent(scenario.creature("Grizzly Bears", "bob"))
    shock = scenario.find("Shock", Zone.GRAVEYARD, "alice")
    scenario.choose_trigger_targets("Roving Actuator", [shock])
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_targets("bob", username="alice")

    scenario.cast_and_resolve("Roving Actuator", *scenario.untapped_sources(*["Mountain"] * 4))
    _resolve_all(scenario)

    assert scenario.player("bob").life == 18
    assert shock.zone is Zone.EXILE
    assert scenario.game.intervening_if_notices == []


def test_roving_actuator_does_not_trigger_without_the_condition():
    scenario = _scenario(*["Mountain"] * 4, hand=("Roving Actuator",), graveyard=("Shock",), bob=())

    scenario.cast_and_resolve("Roving Actuator", *scenario.untapped_sources(*["Mountain"] * 4))
    _resolve_all(scenario)

    assert scenario.find("Shock", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 20
    assert scenario.game.intervening_if_notices == []


def test_roving_actuator_cannot_target_a_three_mana_sorcery():
    """"mana value 2 or less" - Divination (3) is not a legal target, so the
    "up to one" trigger exiles nothing."""
    scenario = _scenario(
        *["Mountain"] * 4, hand=("Roving Actuator",), graveyard=("Divination",)
    )
    scenario.game.exile_permanent(scenario.creature("Grizzly Bears", "bob"))

    scenario.cast_and_resolve("Roving Actuator", *scenario.untapped_sources(*["Mountain"] * 4))
    _resolve_all(scenario)

    assert scenario.find("Divination", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD


def test_the_condition_is_rechecked_on_resolution_and_still_holds():
    """CR 603.4's second check: the departure stays a fact of the turn, so
    the trigger waiting on the stack still resolves after the departed
    object has moved on again."""
    scenario = _scenario("Kavaron Skywarden")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.return_to_hand(bears)
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()
    scenario.game.put_triggers_on_stack()
    assert scenario.game.stack
    scenario.game.discard_cards("bob", [scenario.find("Grizzly Bears", Zone.HAND, "bob")])
    _resolve_all(scenario)

    assert _counters(scenario, "Kavaron Skywarden") == 1
