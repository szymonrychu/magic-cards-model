"""`AbilityOnStack.keyword_activation` and `.unless_payment`, round-tripped
through `Game.model_dump(mode="json")` / `Game.model_validate` while the
ability is still on the stack, unresolved - then resolved on the decoded copy.

Both fields were `Any = Field(exclude=True)` before this task, and both held a
real, already-structured pydantic model the whole time:

- `keyword_activation` is a `machines/keywords.KeywordActivation` - the object
  `machines/keywords.keyword_effect_for` reads to run a CR 702 keyword's own
  effect (cycling, equip, crew, ward, ...) instead of falling through to the
  card-name registries in `machines/effects.py`, which have no name to key a
  keyword ability under at all.
- `unless_payment` is a `machines/cost.CostPayment`, opened by
  `machines/keywords.WardTrigger.begin_paying` for CR 702.21a's "counter that
  spell or ability unless that player pays [cost]".

`exclude=True` meant a dumped-and-decoded ability lost both silently: no error,
just a `keyword_activation`/`unless_payment` that came back `None`. For
`keyword_activation` that sent every keyword ability's resolution past
`keyword_effect_for` to the ordinary card-name lookup, which has nothing for a
keyword and does nothing (`memory/silent-default-dispatch-tables.md`'s exact
shape). For `unless_payment` it was worse in the other direction: a *paid*
ward, once round-tripped, read back as unpaid and counted a spell it had
already been paid to let through.

Both are typed and included now. `keyword_activation` needed `KeywordActivation`
itself fixed first - see its own docstring in `machines/triggers.py` for the
three shapes inside it (`game`, `payment`, `on_stack`, `result`) and how each
is handled; `on_stack` in particular pointed straight back at this very
`AbilityOnStack`, which would recurse a dump forever if both sides serialised
the edge, so it is `exclude=True` on that side and `AbilityOnStack.model_post_
init` re-closes it from this side after a decode. `unless_payment` took the
"reduce it to data" option: `CostPayment` was already plain data once its own
`.game` is excluded, exactly like `KeywordActivation.payment` next door, which
carries the identical type with no special handling at all.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.cost import CostStep
from magic_cards_model.machines.keywords import (
    crew_activation,
    equip_activation,
    equipped_creature,
    ward_triggers,
)
from magic_cards_model.machines.triggers import AbilityOnStack
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import CardState
from magic_cards_model.models.game import Game
from tests.scenarios.harness import PlayedScenario, Scenario, mana_from


def _round_trip(game: Game) -> PlayedScenario:
    """Dump `game` to JSON and validate it back, wrapped for driving further.

    The whole point of every test here: whatever the ability on the stack was
    about to do must still happen once the decoded copy resolves it.
    """
    return PlayedScenario(Game.model_validate(game.model_dump(mode="json")))


# --------------------------------------------------------------------------
# keyword_activation - Cori-Steel Cutter's equip (CR 702.6a)
# --------------------------------------------------------------------------


def _equip_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Cori-Steel Cutter", "Grizzly Bears", "Mountain", "Mountain"],
        )
        .player("bob", battlefield=["Watchwolf"])
    )


def test_an_activated_keyword_ability_resolves_identically_after_a_round_trip():
    """Equip, put on the stack and round-tripped before it resolves.

    Before this task's fix this decoded as an ordinary `AbilityOnStack` with no
    `keyword_activation` at all - `keyword_effect_for` found nothing to run,
    and the decoded copy's `resolve_top` took the ability off the stack having
    attached nothing.
    """
    scenario = _equip_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    activation = equip_activation(scenario.game, cutter, bears, "alice")
    payment = activation.begin_paying()
    for source in scenario.untapped_sources("Mountain", "Mountain"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    on_stack = activation.activate()

    assert on_stack in scenario.game.stack
    assert on_stack.keyword_activation is activation
    assert not cutter.is_attached

    played = _round_trip(scenario.game)
    (decoded_ability,) = [item for item in played.game.stack if isinstance(item, AbilityOnStack)]

    # The link survived, typed and populated - not dropped to `None`.
    assert decoded_ability.keyword_activation is not None
    assert decoded_ability.keyword_activation.keyword == "Equip"
    assert not decoded_ability.keyword_activation.applied

    played.resolve_top()  # CR 608.2n, through `keyword_effect_for` alone

    decoded_cutter = played.game.find_by_id(cutter.id)
    decoded_bears = played.game.find_by_id(bears.id)
    assert isinstance(decoded_cutter, CardState)
    assert isinstance(decoded_bears, CardState)
    assert decoded_cutter.is_attached
    assert equipped_creature(played.game, decoded_cutter) is decoded_bears


# --------------------------------------------------------------------------
# unless_payment - Archive Dragon's ward (CR 702.21a)
# --------------------------------------------------------------------------


def _ward_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Mountain", "Mountain"],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Archive Dragon", "Mountain"])
    )


def test_a_paid_ward_still_lets_the_spell_through_after_a_round_trip():
    """A *paid* ward, round-tripped, must not read back as unpaid.

    This is the sharper of the two directions: before this fix, `unless_
    payment` was dropped by the dump regardless of `CostPayment.step`, so a
    ward that had already been paid came back looking unpaid and countered a
    spell that had bought its way through - a wrong game state that looks
    exactly as plausible as the right one.
    """
    scenario = _ward_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dragon = scenario.creature("Archive Dragon", "bob")

    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[dragon]
    )
    (trigger,) = ward_triggers(scenario.game, bolt)
    payment = trigger.begin_paying()
    for source in scenario.untapped_sources("Mountain", "Mountain"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    assert trigger.paid

    played = _round_trip(scenario.game)
    decoded_bolt = played.game.find_by_id(bolt.id)
    assert isinstance(decoded_bolt, CardState)
    (decoded_trigger,) = ward_triggers(played.game, decoded_bolt)

    # The payment survived as data, `step` included - not reset to `None`.
    assert decoded_trigger.ability.unless_payment is not None
    assert decoded_trigger.ability.unless_payment.step is CostStep.PAID
    assert decoded_trigger.paid

    played.resolve_top()  # the ward trigger, which must counter nothing
    assert decoded_bolt in played.game.stack

    played.resolve_top()  # the Bolt, now free to resolve
    decoded_dragon = played.game.find_by_id(dragon.id)
    assert isinstance(decoded_dragon, CardState)
    assert decoded_dragon.damage == 3


def test_an_unpaid_ward_still_counters_the_spell_after_a_round_trip():
    """The `None` case round-trips too, and still counters (CR 701.6a).

    Nothing pays the ward before the dump - `unless_payment` stays `None` the
    whole way through, exactly like a game where ward never entered the
    picture - and the caster declines when the decoded copy asks (CR 118.12a),
    so `_ward_effect` still counters on it.
    """
    scenario = _ward_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dragon = scenario.creature("Archive Dragon", "bob")

    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[dragon]
    )
    (trigger,) = ward_triggers(scenario.game, bolt)
    assert trigger.ability.unless_payment is None

    played = _round_trip(scenario.game)
    decoded_bolt = played.game.find_by_id(bolt.id)
    assert isinstance(decoded_bolt, CardState)

    played.will_pay_the_mana_cost(False)
    played.resolve_top()  # the ward trigger, unpaid

    assert decoded_bolt.zone is Zone.GRAVEYARD
    decoded_dragon = played.game.find_by_id(dragon.id)
    assert isinstance(decoded_dragon, CardState)
    assert decoded_dragon.damage == 0


def test_a_game_with_no_ward_payment_dumps_and_resolves_fine():
    """The baseline: nothing about ordinary abilities on the stack changed.

    An `AbilityOnStack` with neither field set (an ordinary triggered ability,
    here CR 702.21a's own trigger before anyone has even looked at paying it)
    dumps, decodes, and resolves exactly as it did before this task.
    """
    scenario = _ward_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dragon = scenario.creature("Archive Dragon", "bob")

    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[dragon]
    )
    (ability,) = [item for item in scenario.game.stack if isinstance(item, AbilityOnStack)]
    assert ability.keyword_activation is None
    assert ability.unless_payment is None

    played = _round_trip(scenario.game)  # must not raise
    decoded_bolt = played.game.find_by_id(bolt.id)
    assert isinstance(decoded_bolt, CardState)

    played.will_pay_the_mana_cost(False)  # CR 118.12a: the caster declines
    played.resolve_top()
    assert decoded_bolt.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# keyword_activation - Consulate Dreadnought's crew (CR 702.122a)
# --------------------------------------------------------------------------


def _crew_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[
                "Consulate Dreadnought",
                "Grizzly Bears",
                "Grizzly Bears",
                "Grizzly Bears",
            ],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_a_vehicle_destroyed_after_a_round_trip_gains_no_continuous_effects_from_crew():
    """Crew on the stack, dumped and decoded, then the real Vehicle destroyed
    on the *decoded* game before its own crew ability resolves.

    `_crew_effect` used to recheck `activation.card.zone` directly - a decoded
    copy, frozen at the moment the ability was activated - instead of asking
    `game` where the Vehicle actually is now (CR 608.2h). Crew uses the stack,
    so an opponent gets priority to respond before it resolves, and in the
    stateless-library world every priority pass is a dump/decode. Before the
    fix in `machines/keywords.py`, destroying the real Consulate Dreadnought on
    the decoded game and then resolving crew still created two live
    `ContinuousEffect`s (CR 613.1d: artifact, creature) for a permanent that is
    actually already in the graveyard - silently, with no error, and
    `CardState.move_to` keeps `id` stable enough that they would latch back on
    if the Vehicle ever returned to the battlefield before cleanup.
    """
    scenario = _crew_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vehicle = scenario.find("Consulate Dreadnought", Zone.BATTLEFIELD, "alice")
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", "Grizzly Bears", username="alice")

    activation = crew_activation(scenario.game, vehicle, list(bears), "alice")
    activation.begin_paying()
    activation.payment.pay()
    on_stack = activation.activate()

    assert on_stack in scenario.game.stack
    assert on_stack.keyword_activation is activation

    played = _round_trip(scenario.game)
    (decoded_ability,) = [item for item in played.game.stack if isinstance(item, AbilityOnStack)]
    assert decoded_ability.keyword_activation is not None
    assert not decoded_ability.keyword_activation.applied

    decoded_vehicle = played.game.find_by_id(vehicle.id)
    assert isinstance(decoded_vehicle, CardState)
    played.game.destroy(decoded_vehicle)
    assert decoded_vehicle.zone is Zone.GRAVEYARD

    played.resolve_top()  # CR 608.2n, through `keyword_effect_for` alone

    assert played.game.continuous_effects.effects == [], (
        "a destroyed Vehicle must gain no continuous effects when its own "
        "crew ability resolves after a round trip"
    )
