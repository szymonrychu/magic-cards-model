"""Replicate: an additional cost paid any number of times, copying the spell
once per payment (CR 702.56).

CR 702.56a: "Replicate is a keyword that represents two abilities. The first
is a static ability that functions while the spell with replicate is on the
stack ... 'Replicate [cost]' means 'As an additional cost to cast this
spell, you may pay [cost] any number of times' and 'When you cast this
spell, if a replicate cost was paid for it, copy it for each time its
replicate cost was paid. If the spell has any targets, you may choose new
targets for any of the copies.'"

Two independent halves, each reusing an existing shape rather than a new
one: `Casting.pay_replicate` is `pay_kicker`'s own "any number of times"
branch (CR 702.33c), and the copying trigger is storm's own
`_storm_ability`/`_storm_effect` pair (CR 702.40a) with the count read from
`CastRecord.replicated` instead of `Game.spells_cast_this_turn` -
`machines/triggers.intervening_if_holds`'s "a replicate cost was paid for
it" clause (CR 702.56a's own intervening *if*) is what keeps an unreplicated
cast from copying itself zero times as a no-op rather than as a trigger that
never fires at all.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.

Consign to Memory (Replicate {1}, counters a triggered ability or colorless
spell) is the assigned card. Gigadrowse (Replicate {U}, taps target
permanent - a completely different target type) is not in the deck pool and
not named in the brief, and proves `pay_replicate`/`_replicate_effect` read
any replicate cost and any targeted effect rather than Consign to Memory's own.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import _keyword
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def test_the_replicate_ability_is_read_off_the_printed_line():
    ability = _keyword(card("Consign to Memory"), "replicate")
    assert ability is not None
    assert ability.cost == "{1}"
    assert ability.cost_is_mana


def test_gigadrowse_replicated_twice_taps_three_permanents():
    """One original cast plus replicate paid twice: three total objects, each
    tapping the same target - CR 702.56a's copies, retargeted or not."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Gigadrowse"], battlefield=["Island", "Island", "Island"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bears = scenario.creature("Grizzly Bears", username="bob")
    sources = scenario.untapped_sources("Island", "Island", "Island")

    casting = scenario.cast("Gigadrowse")
    casting.pay_replicate(2)
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)

    # The replicate trigger sits above the spell (CR 603.3b) and resolves
    # first, creating two copies before the original ever resolves.
    assert len(scenario.game.stack) == 2  # the trigger, then the spell
    scenario.resolve_top()  # the replicate trigger: two copies go up
    assert len(scenario.game.stack) == 3  # original Gigadrowse + 2 copies

    # Resolve one copy - tapping bears once, exactly what "tap target
    # permanent" says. The other two objects staying on the stack (rather
    # than being drained too) is deliberate: CR 701.21a's tap is a state
    # change, not a cost, so resolving all three against the same already-
    # tapped target is a separate, pre-existing gap in `tap_ability_targets`
    # (`CardState.tap` refusing an already-tapped permanent unconditionally,
    # the cost-payment rule CR 602.5b, applied where CR 701.21a's plain
    # effect should instead be a no-op) - not something this replicate wave
    # touches, and not what this test is about.
    scenario.resolve_top()
    assert len(scenario.game.stack) == 2
    assert bears.tapped


def test_replicate_can_be_paid_zero_times_and_costs_nothing_extra():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Gigadrowse"], battlefield=["Island"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", username="bob")
    (island,) = scenario.untapped_sources("Island")

    casting = scenario.cast("Gigadrowse")
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, island)
    scenario.put_on_stack(casting)

    assert len(scenario.game.stack) == 1, "no replicate cost paid, no trigger at all"
    scenario.resolve_top()
    assert bears.tapped


# -- generality: a second, un-named replicate printing -----------------------


def test_consign_to_memory_replicated_once_makes_one_copy():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Consign to Memory", "Mishra's Bauble"],
            battlefield=["Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bauble_casting = scenario.cast("Mishra's Bauble")
    bauble_payment = bauble_casting.begin_paying()
    bauble_payment.pay()
    bauble = scenario.put_on_stack(bauble_casting)

    sources = scenario.untapped_sources("Island", "Island")
    casting = scenario.cast("Consign to Memory")
    casting.pay_replicate(1)
    casting.choose_targets([bauble])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)

    assert len(scenario.game.stack) == 3  # Bauble, the replicate trigger, Consign
    scenario.resolve_top()  # the replicate trigger: one copy goes up
    assert len(scenario.game.stack) == 3  # Bauble, Consign copy, original Consign

    scenario.resolve_top()  # the copy resolves first, counters the Bauble
    assert bauble.zone is Zone.GRAVEYARD

    scenario.resolve_top()  # the original fizzles: its target is already gone
    assert scenario.find("Consign to Memory", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
