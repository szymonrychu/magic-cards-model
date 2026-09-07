"""`could_pay_mana_cost` - the pure "could this cost be paid" predicate.

Legal-action enumeration needs a fast, pure answer to "could this cost be
paid from this player's currently available resources", asked many times per
priority window with its answers recorded in an append-only training log.
`could_pay_mana_cost` (`machines/cost.py`) is `auto_tap`'s own search
(`_solve_auto_tap`) with the executing half removed - the same argument
`TargetRequirement.rejects` already makes for `affordances.candidates`
(magic-cards-model-api): a predicate and the action it predicts share one
implementation, so the two can never disagree.

This file checks exactly that: the predicate agrees with `auto_tap` on real
boards it can and cannot pay from, and that asking the question changes
nothing - no permanent taps, no field of the game changes, and no dead pool
is published into `Game.open_payment_pools` (the leak a predicate that built
a real `CostPayment` would cause - see `could_pay_mana_cost`'s own
docstring).
"""

import pytest

from magic_cards_model.machines import CostPayment, Step, TotalCost, could_pay_mana_cost
from magic_cards_model.models.mana import ManaCost
from tests.scenarios.harness import Scenario


def test_predicate_agrees_with_auto_tap_on_a_one_source_cost():
    """A plain `{R}` off a single Mountain: both say yes, and `auto_tap`
    actually pays it."""
    scenario = Scenario().player("alice", battlefield=["Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    sources = game.permanents_controlled_by("alice")
    cost = ManaCost.parse("{R}")

    assert could_pay_mana_cost(cost, sources, game=game, payer="alice") is True

    payment = CostPayment.for_total(TotalCost(mana=cost), game=game, payer="alice")
    tapped = payment.auto_tap(sources)
    assert len(tapped) == 1
    payment.pay()


def test_predicate_agrees_with_auto_tap_on_a_cost_needing_dual_colour_choices():
    """`{1}{G}{U}` off a Breeding Pool, a Forest, and an Island - the dual has
    to commit to one colour to make the cost work, the same choice `auto_tap`
    makes on the player's behalf."""
    scenario = Scenario().player("alice", battlefield=["Breeding Pool", "Forest", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    sources = game.permanents_controlled_by("alice")
    cost = ManaCost.parse("{1}{G}{U}")

    assert could_pay_mana_cost(cost, sources, game=game, payer="alice") is True

    payment = CostPayment.for_total(TotalCost(mana=cost), game=game, payer="alice")
    tapped = payment.auto_tap(sources)
    assert len(tapped) == 3
    payment.pay()


def test_predicate_agrees_with_auto_tap_on_a_cost_it_cannot_pay():
    """`{5}{B}{B}` off one Mountain: neither the predicate nor `auto_tap` can
    make that work, and `auto_tap` raises naming the cost."""
    scenario = Scenario().player("alice", battlefield=["Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    sources = game.permanents_controlled_by("alice")
    cost = ManaCost.parse("{5}{B}{B}")

    assert could_pay_mana_cost(cost, sources, game=game, payer="alice") is False

    payment = CostPayment.for_total(TotalCost(mana=cost), game=game, payer="alice")
    with pytest.raises(ValueError, match="no combination"):
        payment.auto_tap(sources)
    payment.cancel()

    assert all(source.untapped for source in sources)


def test_predicate_mutates_nothing():
    """Asking the question, on the real 18-source board the feasibility study
    measured, leaves the game exactly as it found it: no permanent taps, no
    field of `Game` changes, and `open_payment_pools` stays empty throughout -
    even though this is the expensive `{3}{W}{W}` question the study used to
    profile the search.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Steam Vents",
                "Breeding Pool",
                "Hallowed Fountain",
                "Godless Shrine",
                "Watery Grave",
                "Sacred Foundry",
                "Overgrown Tomb",
                "Exotic Orchard",
                "Reflecting Pool",
                "Karplusan Forest",
                "Forest",
                "Island",
                "Swamp",
                "Mountain",
                "Plains",
                "Birds of Paradise",
                "Llanowar Elves",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    sources = game.permanents_controlled_by("alice")
    cost = ManaCost.parse("{3}{W}{W}")

    # One warm-up call first: the layer engine stamps each permanent's CR
    # 613.7a timestamp (`Game.continuous_effects.clock`/`.entered`) the first
    # time anything asks for its computed characteristics, which board-reading
    # code the search calls into (summoning sickness, controlled land types)
    # does regardless of whether the search ever taps anything. That stamping
    # is idempotent and has nothing to do with mana - legal-action enumeration
    # calling this "many times per priority window" only ever pays that cost
    # once per permanent, on whichever call sees it first. What this test
    # holds `could_pay_mana_cost` to is every call *after* that: no permanent
    # tap, no field of `Game` changes, and `open_payment_pools` stays empty.
    could_pay_mana_cost(cost, sources, game=game, payer="alice")

    assert game.open_payment_pools == {}
    before_dump = game.model_dump_json()
    before_created = game.objects_created

    result = could_pay_mana_cost(cost, sources, game=game, payer="alice")

    assert result is True
    assert game.open_payment_pools == {}
    assert game.objects_created == before_created
    assert game.model_dump_json() == before_dump
    assert all(source.untapped for source in sources)


def test_predicate_with_no_game_or_payer_asks_only_about_the_sources_given():
    """`game`/`payer` are both optional, the same freedom `CostPayment` gives a
    gameless payment: omitted, the question is "can `sources` alone pay this",
    with no floating mana and no life on the table for a Phyrexian symbol."""
    scenario = Scenario().player("alice", battlefield=["Mountain", "Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.game.permanents_controlled_by("alice")

    assert could_pay_mana_cost(ManaCost.parse("{R}{R}"), sources) is True
    assert could_pay_mana_cost(ManaCost.parse("{R}{R}{R}"), sources) is False
