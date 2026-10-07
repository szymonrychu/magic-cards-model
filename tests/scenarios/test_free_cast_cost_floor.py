"""A spell cast "without paying its mana cost" still pays cost increases and floors.

Owner's report (2026-10-07): "Ephemerate at upkeep is trying to be cast for
free from exile. With trinisphere it still should cost 3 mana."

Rules, each read whole with `mise run rules:find` in the session that wrote
this file:

- **CR 702.88a** - rebound: "... at the beginning of your next upkeep, you may
  cast this card from exile without paying its mana cost."
- **CR 702.88b** - "Casting a spell as an effect of its rebound ability
  follows the rules for paying alternative costs in rules 601.2b and
  601.2f-h."
- **CR 118.9d** - "If an alternative cost is being paid to cast a spell, any
  additional costs, cost increases, and cost reductions that affect that spell
  are applied to that alternative cost."
- **CR 601.2f** - "The total cost is the mana cost or alternative cost ...
  plus all additional costs and cost increases, and minus all cost
  reductions. ... Once the total cost is determined, any effects that
  directly affect the total cost are applied." Trinisphere's "each spell that
  would cost less than three mana to cast costs three mana to cast" is such
  an effect, so a free cast under an untapped Trinisphere costs {3}.

The cast itself already charged this (`Casting.total_cost` folds every board
modifier into the empty alternative cost, and the resolution cast asks a
`PAY_MANA` for it). What did not: the "you may cast" offer said only "without
paying its mana cost" - the free-cast claim the owner saw - so the player
deciding whether to take it was never told it costs {3}. One test per
free-cast path family: rebound, cascade, discover, suspend, a resolving
effect's "this turn" free-cast permission (Ral, Leyline Prodigy's -8), and a
static free-cast grant (Zaffai and the Tempests).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import MarkedExile, remove_suspend_time_counter
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from magic_cards_model.machines.keywords import discover
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import PlayedScenario, Scenario
from tests.scenarios.test_rebound import run_to_erins_next_upkeep


def asked_since(scenario: PlayedScenario, mark: int, kind: DecisionKind, source: str):
    return [
        question
        for question in scenario.game.decisions.asked[mark:]
        if question.kind is kind and question.source == source
    ]


def offers_since(scenario: PlayedScenario, mark: int, card_name: str):
    """The "you may cast <card>" questions asked since `mark` - sourced by the
    resolving ability, so matched on the card the prompt names."""
    return [
        question
        for question in scenario.game.decisions.asked[mark:]
        if question.kind is DecisionKind.MAY and f"cast {card_name}" in question.prompt
    ]


# -- rebound (CR 702.88a, 702.88b) --------------------------------------------


def ephemerate_rebounded(*erin_extra: str) -> tuple[PlayedScenario, object, object]:
    """Erin casts Ephemerate from hand under her own Trinisphere (three Plains
    pay the floored {2}{W}), it rebounds into exile, and the game walks to her
    next upkeep with the rebound trigger on the stack, unresolved."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "erin",
            hand=["Ephemerate"],
            battlefield=[
                "White Orchid Phantom",
                "Plains",
                "Plains",
                "Plains",
                "Trinisphere",
                *erin_extra,
            ],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phantom = scenario.creature("White Orchid Phantom")
    plains = scenario.untapped_sources("Plains", "Plains", "Plains", username="erin")
    ephemerate = scenario.cast_and_resolve("Ephemerate", *plains, targets=[phantom])
    assert ephemerate.zone is Zone.EXILE
    scenario.game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.CHOOSE_TARGETS,
            value=(phantom.id,),
            player="erin",
            source=None,
            uses=1,
        )
    )
    run_to_erins_next_upkeep(scenario)
    # The harness's manual turn-based actions skip CR 502.3's untap.
    for permanent in scenario.game.permanents_controlled_by("erin"):
        permanent.untap()
    return scenario, ephemerate, phantom


def test_the_rebound_offer_names_trinispheres_three():
    """The "you may cast" question is where the seat decides, so it has to
    say what the cast will actually cost - not only "without paying its mana
    cost", which under an untapped Trinisphere is not free (CR 118.9d)."""
    scenario, _, _ = ephemerate_rebounded()
    mark = len(scenario.game.decisions.asked)
    scenario.will_pay_the_mana_cost(True, username="erin")

    scenario.resolve_top()  # rebound's delayed trigger

    (offer,) = offers_since(scenario, mark, "Ephemerate")
    assert "{3}" in offer.prompt


def test_the_rebound_recast_under_trinisphere_pays_three():
    """CR 702.88b + CR 601.2f: the empty alternative cost is floored to {3},
    paid from erin's three untapped Plains."""
    scenario, ephemerate, _ = ephemerate_rebounded()
    mark = len(scenario.game.decisions.asked)
    scenario.will_pay_the_mana_cost(True, username="erin")

    scenario.resolve_top()

    (payment,) = asked_since(scenario, mark, DecisionKind.PAY_MANA, "Ephemerate")
    assert payment.amount == 3
    assert ephemerate.zone is Zone.STACK
    assert not [
        land
        for land in scenario.game.permanents_controlled_by("erin")
        if land.name == "Plains" and land.untapped
    ]


def test_the_rebound_recast_is_free_while_trinisphere_is_tapped():
    """Trinisphere's "As long as this artifact is untapped" (CR 611.3b): a
    tapped Trinisphere sets no floor, and the rebound cast costs nothing."""
    scenario, ephemerate, _ = ephemerate_rebounded()
    (trinisphere,) = scenario.untapped_sources("Trinisphere", username="erin")
    trinisphere.tap()
    mark = len(scenario.game.decisions.asked)

    scenario.resolve_top()

    (offer,) = offers_since(scenario, mark, "Ephemerate")
    assert "{3}" not in offer.prompt
    assert not asked_since(scenario, mark, DecisionKind.PAY_MANA, "Ephemerate")
    assert ephemerate.zone is Zone.STACK
    assert len(scenario.untapped_sources("Plains", "Plains", "Plains", username="erin")) == 3


def test_a_rebound_recast_that_cannot_pay_three_stays_in_exile():
    """CR 601.2h / CR 118.3: with no untapped mana the {3} cannot be paid, so
    the payment question cannot be accepted and Ephemerate stays exiled."""
    scenario, ephemerate, _ = ephemerate_rebounded()
    for land in scenario.untapped_sources("Plains", "Plains", "Plains", username="erin"):
        land.tap()
    mark = len(scenario.game.decisions.asked)

    scenario.resolve_top()

    (payment,) = asked_since(scenario, mark, DecisionKind.PAY_MANA, "Ephemerate")
    assert payment.affirmative_is_legal is False
    assert ephemerate.zone is Zone.EXILE


# -- cascade (CR 702.85a) -------------------------------------------------------


def test_a_cascaded_spell_under_trinisphere_pays_three():
    """Living End has no mana cost at all; cascade casts it for nothing, and
    Trinisphere floors that nothing to {3} (CR 118.9d, CR 601.2f)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "bob",
            hand=["Shardless Agent"],
            library=["Island", "Forest", "Living End"],
            graveyard=["Grizzly Bears"],
            battlefield=["Island", "Island", "Forest", "Island", "Island", "Forest", "Trinisphere"],
        )
        .player("alice")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mark = len(scenario.game.decisions.asked)
    scenario.will_pay_the_mana_cost(True, username="bob")
    scenario.cast_onto_stack(
        "Shardless Agent",
        *scenario.untapped_sources("Island", "Island", "Forest", username="bob"),
        username="bob",
    )

    scenario.resolve_top()  # the cascade trigger

    (offer,) = offers_since(scenario, mark, "Living End")
    assert "{3}" in offer.prompt
    (payment,) = asked_since(scenario, mark, DecisionKind.PAY_MANA, "Living End")
    assert payment.amount == 3
    assert scenario.stack_names()[-1] == "Living End"


# -- discover (CR 701.57a) ------------------------------------------------------


def test_a_discovered_noncreature_spell_pays_thalias_tax():
    """Thalia, Guardian of Thraben: "Noncreature spells cost {1} more to
    cast." - a cost increase, applied to discover's free cast (CR 118.9d)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Lightning Bolt"],
            battlefield=["Thalia, Guardian of Thraben", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mark = len(scenario.game.decisions.asked)
    scenario.will_pay_the_mana_cost(True, username="alice")

    result = discover(scenario.game, "alice", 3, source_name="Test", seed=0)

    assert result.hit is not None and result.hit.zone is Zone.STACK
    (offer,) = offers_since(scenario, mark, "Lightning Bolt")
    assert "{1}" in offer.prompt
    (payment,) = asked_since(scenario, mark, DecisionKind.PAY_MANA, "Lightning Bolt")
    assert payment.amount == 1
    assert not scenario.game.find_by_id(
        next(s.id for s in scenario.game.battlefield if s.name == "Mountain")
    ).untapped


# -- suspend (CR 702.62a) -------------------------------------------------------


def test_a_suspended_spell_pays_sphere_of_resistances_tax():
    """Sphere of Resistance: "Spells cost {1} more to cast." - suspend's
    last-counter cast is free, so the whole cost is the {1}."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Living End"],
            graveyard=["Grizzly Bears"],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp", "Swamp"],
        )
        .player("bob", battlefield=["Sphere of Resistance"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    living_end = scenario.find("Living End", Zone.HAND)
    action = MarkedExile.suspend(scenario.game, living_end, "alice")
    payment = action.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp"))
    action.take()
    living_end = scenario.find("Living End", Zone.EXILE)
    for _ in range(3):
        remove_suspend_time_counter(scenario.game, living_end)
    scenario.game.put_triggers_on_stack()
    mark = len(scenario.game.decisions.asked)
    scenario.will_pay_the_mana_cost(True, username="alice")

    scenario.resolve_top()  # the last-counter trigger

    (offer,) = offers_since(scenario, mark, "Living End")
    assert "{1}" in offer.prompt
    (paid,) = asked_since(scenario, mark, DecisionKind.PAY_MANA, "Living End")
    assert paid.amount == 1
    assert living_end.zone is Zone.STACK
    assert not [
        land
        for land in scenario.game.permanents_controlled_by("alice")
        if land.name == "Swamp" and land.untapped
    ], "four Swamps suspended it, the fifth paid the {1}"


# -- a resolving effect's free-cast permission (CR 118.9) ----------------------


def test_a_free_cast_permission_under_trinisphere_costs_three():
    """Ral, Leyline Prodigy's -8 lets alice cast Lightning Bolt from exile
    without paying its mana cost; her Trinisphere floors that at {3}, and two
    Mountains cannot pay it (CR 601.2h)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Lightning Bolt", "Forest"],
            battlefield=["Ral, Monsoon Mage", "Mountain", "Mountain", "Trinisphere"],
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ral = scenario.find("Ral, Monsoon Mage", Zone.BATTLEFIELD)
    ral.transform()
    ral.add_counters(Counter.LOYALTY, 8)  # CR 606.6: the -8 needs eight
    scenario.activate(ral, index=2)
    scenario.pass_until_resolved()
    assert (
        scenario.game.play_permission_for(
            scenario.find("Lightning Bolt", Zone.EXILE), "alice"
        ).pays_mana_cost
        is False
    )

    casting = scenario.cast("Lightning Bolt", from_zone=Zone.EXILE)
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()

    assert str(casting.total_cost.mana) == "{3}"
    with pytest.raises(ValueError):
        scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain"))


# -- a static free-cast grant (CR 118.9, CR 604.2) ------------------------------


def test_a_static_free_cast_grant_under_trinisphere_costs_three():
    """Zaffai and the Tempests: "Once during each of your turns, you may cast
    an instant or sorcery spell from your hand without paying its mana cost."
    Under Trinisphere that free cast costs {3}, paid from three Mountains."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=[
                "Zaffai and the Tempests",
                "Trinisphere",
                "Mountain",
                "Mountain",
                "Mountain",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Lightning Bolt")
    casting.use_alternative_cost("Zaffai and the Tempests")
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()

    assert str(casting.total_cost.mana) == "{3}"
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert scenario.player("bob").life == 17
