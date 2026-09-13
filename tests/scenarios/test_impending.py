"""Impending: cast it cheap, wait for it to wake up (CR 702.176).

CR 702.176a (read whole with `mise run rules:find 702.176`, CR effective
2026-08-07): "Impending is a keyword that represents four abilities. The first
is a static ability that functions while the spell with impending is on the
stack. The second is static ability that creates a replacement effect that may
apply to the permanent with impending as it enters the battlefield from the
stack. The third is a static ability that functions on the battlefield. The
fourth is a triggered ability that functions on the battlefield. 'Impending
N-[cost]' means 'You may choose to pay [cost] rather than pay this spell's mana
cost,' 'If you chose to pay this permanent's impending cost, it enters with N
time counters on it,' 'As long as this permanent's impending cost was paid and
it has a time counter on it, it's not a creature,' and 'At the beginning of
your end step, if this permanent's impending cost was paid and it has a time
counter on it, remove a time counter from it.' Casting a spell for its
impending cost follows the rules for paying alternative costs in rules 601.2b
and 601.2f-h."

So the four pieces are tested one at a time below: the alternative cost
(CR 118.9), the enters-with replacement (CR 614.1c), the layer 4 "not a
creature" (CR 613.1d, CR 205.1a), and the end step trigger with its intervening
*if* (CR 603.4). CR 400.7 and CR 122.2 are why a blinked Overlord is a creature
with no counters: it is a new object nobody cast for its impending cost.

Overlord of the Balemurk is the reported card (battle-test D01). Overlord of the
Mistmoors is in neither deck pool and has a different N (4) and cost shape
({2}{W}{W}), which is the proof the keyword is parsed rather than the card.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import keyword_cast_options
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from magic_cards_model.models.card import Type
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.mana import ManaCost
from tests.cards import card
from tests.scenarios.harness import Scenario

BALEMURK = "Overlord of the Balemurk"
MISTMOORS = "Overlord of the Mistmoors"


def board(
    *,
    hand: list[str] | None = None,
    battlefield: list[str] | None = None,
    graveyard: list[str] | None = None,
) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=hand if hand is not None else [BALEMURK],
            battlefield=battlefield if battlefield is not None else ["Swamp"] * 5,
            graveyard=graveyard,
            library=["Swamp"] * 20,
        )
        .player("bob", battlefield=["Forest"], library=["Forest"] * 20)
    )


def is_creature_now(scenario, permanent) -> bool:
    """The layer-computed answer (CR 613), not the printed type line."""
    return Type.CREATURE in scenario.game.characteristics_of(permanent).types


def cast_for_impending(scenario, name: str, *lands: str):
    sources = scenario.untapped_sources(*lands)
    casting = scenario.cast(name)
    casting.use_keyword("Impending")
    scenario.pay_with(casting.begin_paying(), *sources)
    return casting, scenario.put_on_stack(casting)


def resolve_everything(scenario) -> None:
    for _ in range(40):
        if not scenario.stack_names():
            return
        scenario.pass_until_resolved()
    raise AssertionError(f"the stack never emptied: {scenario.stack_names()}")


def advance_to(scenario, player: str, step: Step) -> None:
    """Walk the real turn structure to `player`'s `step`, resolving whatever
    triggers on the way (CR 500.2: a step does not end with a non-empty stack)."""
    for _ in range(80):
        if scenario.stack_names():
            resolve_everything(scenario)
            continue
        scenario.advance()
        if scenario.step is Step.UNTAP:
            scenario.game.untap_step()
        if scenario.turn.active_player == player and scenario.step is step:
            return
    raise AssertionError(f"never reached {player}'s {step}")


def impending_overlord_on_battlefield(scenario, name: str = BALEMURK, *lands: str):
    lands = lands or ("Swamp", "Swamp")
    _, spell = cast_for_impending(scenario, name, *lands)
    overlord = scenario.resolve_top()
    assert overlord.zone is Zone.BATTLEFIELD
    return overlord


# -- the alternative cost (the first ability) --------------------------------


def test_impending_is_an_alternative_cost_cast_from_hand():
    """CR 702.176a's first ability, CR 118.9: paid rather than the mana cost."""
    options = [o for o in keyword_cast_options(card(BALEMURK)) if o.keyword == "Impending"]

    assert len(options) == 1
    (option,) = options
    assert option.zone is Zone.HAND
    assert option.pays_mana_cost is False
    assert str(option.cost) == "{1}{B}"
    assert option.rule == "CR 702.176a"


def test_casting_for_impending_costs_the_impending_cost():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast(BALEMURK)
    casting.use_keyword("Impending")

    assert casting.total_cost.mana == ManaCost.parse("{1}{B}")


def test_legal_actions_offer_the_impending_cast_beside_the_normal_cast():
    """The enumeration a seat reads (D01): both casts, the impending one naming
    its keyword and rule the way evoke and warp already do."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    overlord = scenario.find(BALEMURK, Zone.HAND)

    casts = [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.kind is ActionKind.CAST and action.card_id == overlord.id
    ]
    keywords = sorted((action.keyword or "", action.rule) for action in casts)

    assert ("", "CR 601.2") in keywords
    assert ("Impending", "CR 702.176a") in keywords
    (impending,) = [action for action in casts if action.keyword == "Impending"]
    assert impending.alternative_cost == "Impending"


def test_impending_does_not_cast_from_the_graveyard_and_says_which_rule():
    """The refusal names CR 702.176a rather than failing silently."""
    scenario = board(hand=[], graveyard=[BALEMURK]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    overlord = scenario.find(BALEMURK, Zone.GRAVEYARD)
    (option,) = [o for o in keyword_cast_options(overlord.card) if o.keyword == "Impending"]

    reason = option.why_not(overlord, "alice", scenario.game)

    assert reason is not None
    assert "CR 702.176a" in reason


def test_a_card_without_impending_cannot_be_cast_for_impending():
    scenario = board(hand=["Grizzly Bears"], battlefield=["Forest"] * 2).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Grizzly Bears")

    with pytest.raises(ValueError, match="no Impending ability"):
        casting.use_keyword("Impending")


# -- entering with time counters, and not being a creature ------------------


def test_the_impending_spell_is_still_a_creature_spell_on_the_stack():
    """The "not a creature" ability functions on the battlefield only."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _, spell = cast_for_impending(scenario, BALEMURK, "Swamp", "Swamp")

    assert spell.zone is Zone.STACK
    assert spell.is_creature


def test_cast_for_impending_it_enters_with_five_time_counters_and_is_not_a_creature():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    overlord = impending_overlord_on_battlefield(scenario)

    assert overlord.counter_count(Counter.TIME) == 5
    assert not is_creature_now(scenario, overlord)
    chars = scenario.game.characteristics_of(overlord)
    assert Type.ENCHANTMENT in chars.types
    # CR 205.1a: the creature types go with the creature type.
    assert "Avatar" not in chars.subtypes
    assert "Horror" not in chars.subtypes


def test_its_enters_trigger_still_fires_when_cast_for_impending():
    """It still enters (CR 603.6a) - only its creature-ness is switched off."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    library_before = len(scenario.player("alice").library)

    impending_overlord_on_battlefield(scenario)

    assert any(BALEMURK in name for name in scenario.stack_names())
    scenario.will_take_the_may(False, times=None)
    resolve_everything(scenario)
    assert len(scenario.player("alice").library) == library_before - 4


def test_a_full_cost_cast_is_a_creature_with_no_time_counters():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, times=None)

    overlord = scenario.cast_and_resolve(BALEMURK, *scenario.untapped_sources(*["Swamp"] * 5))

    assert overlord.zone is Zone.BATTLEFIELD
    assert overlord.counter_count(Counter.TIME) == 0
    assert is_creature_now(scenario, overlord)

    resolve_everything(scenario)
    advance_to(scenario, "alice", Step.END_STEP)
    assert not any(BALEMURK in name for name in scenario.stack_names())


# -- the end step trigger ----------------------------------------------------


def test_a_time_counter_comes_off_at_its_controllers_end_step_and_not_the_opponents():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, times=None)
    overlord = impending_overlord_on_battlefield(scenario)
    resolve_everything(scenario)

    advance_to(scenario, "alice", Step.END_STEP)
    assert any(BALEMURK in name for name in scenario.stack_names())  # on the stack, CR 603.3
    resolve_everything(scenario)
    assert overlord.counter_count(Counter.TIME) == 4
    assert not is_creature_now(scenario, overlord)

    advance_to(scenario, "bob", Step.END_STEP)
    assert not any(BALEMURK in name for name in scenario.stack_names())
    assert overlord.counter_count(Counter.TIME) == 4


def test_it_becomes_a_creature_when_the_last_time_counter_is_removed():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, times=None)
    overlord = impending_overlord_on_battlefield(scenario)
    resolve_everything(scenario)

    for remaining in (4, 3, 2, 1):
        advance_to(scenario, "alice", Step.END_STEP)
        resolve_everything(scenario)
        assert overlord.counter_count(Counter.TIME) == remaining
        assert not is_creature_now(scenario, overlord)

    advance_to(scenario, "alice", Step.END_STEP)
    resolve_everything(scenario)
    assert overlord.counter_count(Counter.TIME) == 0
    assert is_creature_now(scenario, overlord)
    chars = scenario.game.characteristics_of(overlord)
    assert (chars.power, chars.toughness) == (5, 5)

    # CR 603.4: with no time counter on it the intervening *if* is false, so
    # the next end step has nothing to trigger.
    advance_to(scenario, "alice", Step.END_STEP)
    assert not any(BALEMURK in name for name in scenario.stack_names())


# -- counters removed some other way, and a blink ----------------------------


def test_removing_all_its_counters_makes_it_a_creature_and_stops_the_tick():
    """Vampire Hexmage: "Sacrifice this creature: Remove all counters from
    target permanent." With no time counter the third ability's condition is
    false (a creature now) and the fourth's intervening *if* is too."""
    scenario = board(battlefield=["Swamp"] * 5 + ["Vampire Hexmage"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, times=None)
    overlord = impending_overlord_on_battlefield(scenario)
    resolve_everything(scenario)
    hexmage = scenario.creature("Vampire Hexmage")

    scenario.activate(hexmage, sacrificing=[hexmage], targets=[overlord])
    resolve_everything(scenario)

    assert hexmage.zone is Zone.GRAVEYARD
    assert overlord.counter_count(Counter.TIME) == 0
    assert is_creature_now(scenario, overlord)

    advance_to(scenario, "alice", Step.END_STEP)
    assert not any(BALEMURK in name for name in scenario.stack_names())


def test_ephemerate_cannot_target_it_while_it_is_not_a_creature():
    """CR 115.1 targeting reads what it is now: not a creature."""
    scenario = board(hand=[BALEMURK, "Ephemerate"], battlefield=["Swamp"] * 2 + ["Plains"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, times=None)
    overlord = impending_overlord_on_battlefield(scenario)
    resolve_everything(scenario)

    with pytest.raises(ValueError):
        scenario.cast("Ephemerate", targets=[overlord])


def test_a_blinked_impending_overlord_returns_as_a_creature_with_no_counters():
    """Flicker of Fate: "Exile target creature or enchantment, then return it to
    the battlefield under its owner's control." CR 400.7 and CR 122.2: the
    returning object is new, its counters ceased to exist, and nobody cast it
    for its impending cost - so no counters are put on it and it is a creature.
    Its enters trigger fires again (CR 603.6a)."""
    scenario = board(
        hand=[BALEMURK, "Flicker of Fate"], battlefield=["Swamp"] * 2 + ["Plains"] * 2
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, times=None)
    overlord = impending_overlord_on_battlefield(scenario)
    resolve_everything(scenario)
    stamp_before = overlord.zone_change_stamp

    scenario.cast_and_resolve(
        "Flicker of Fate", *scenario.untapped_sources("Plains", "Plains"), targets=[overlord]
    )

    assert overlord.zone is Zone.BATTLEFIELD
    assert overlord.zone_change_stamp != stamp_before
    assert overlord.counter_count(Counter.TIME) == 0
    assert is_creature_now(scenario, overlord)
    assert any(BALEMURK in name for name in scenario.stack_names())
    resolve_everything(scenario)

    advance_to(scenario, "alice", Step.END_STEP)
    assert not any(BALEMURK in name for name in scenario.stack_names())


# -- generality: a second impending card in neither deck pool ----------------


def test_overlord_of_the_mistmoors_reads_its_own_n_and_cost():
    """A different N (4) and cost ({2}{W}{W}) off the same keyword line."""
    scenario = board(hand=[MISTMOORS], battlefield=["Plains"] * 4).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    overlord = scenario.find(MISTMOORS, Zone.HAND)
    casts = {
        action.keyword
        for action in legal_actions(scenario.game, "alice")
        if action.kind is ActionKind.CAST and action.card_id == overlord.id
    }
    assert "Impending" in casts

    casting, _ = cast_for_impending(scenario, MISTMOORS, *["Plains"] * 4)
    assert casting.total_cost.mana == ManaCost.parse("{2}{W}{W}")
    overlord = scenario.resolve_top()

    assert overlord.counter_count(Counter.TIME) == 4
    assert not is_creature_now(scenario, overlord)

    resolve_everything(scenario)
    insects = [p for p in scenario.game.battlefield if p.name != MISTMOORS and p.token]
    assert len(insects) == 2
    assert all(is_creature_now(scenario, insect) for insect in insects)

    advance_to(scenario, "alice", Step.END_STEP)
    resolve_everything(scenario)
    assert overlord.counter_count(Counter.TIME) == 3
    assert not is_creature_now(scenario, overlord)
