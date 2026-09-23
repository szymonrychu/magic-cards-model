"""Triggered abilities a resolving spell or ability creates for the rest of
the turn: "Whenever `<condition>` this turn, `<effect>`" and "Until end of
turn, whenever `<condition>`, `<effect>`".

CR 603.7: "An effect may create a delayed triggered ability that can do
something at a later time. A delayed triggered ability will contain 'when,'
'whenever,' or 'at,' although that word won't usually begin the ability."
CR 603.7a: it is created during the resolution and "won't trigger until it has
actually been created, even if its trigger event occurred just beforehand."
CR 603.7b: it triggers only once "unless it has a stated duration, such as
'this turn'" - these all do, so each fires once per event for the rest of the
turn. CR 514.2 ends "this turn" effects in the cleanup step. CR 603.7d/e: its
source and controller are the creating spell's or ability's.

The created ability is stored as data (`machines/delayed.
CreatedTriggeredAbility`, the ability's own printed-shape text) and its
condition is matched by the same `machines/triggers.condition_matches` a
printed trigger uses, so it round-trips through `Game.model_dump` and fires on
a decoded game exactly as on the live one.

Listed cards: First Day of Class, Beck // Call, Dovin, Grand Arbiter. Proof
printings (legal, not listed, not in any api deck): Rite of Harmony (a
different subject - "a creature or enchantment you control" - and a different
effect, from an instant with flashback) and Mistway Spy (the "until end of
turn, whenever" form created by a *triggered* ability rather than a loyalty
ability, with a different effect, investigate).

Every CR number here was read with `mise run rules:find` in the session that
wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.game import Game
from tests.scenarios.harness import Scenario


def _resolve_everything(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _to_bobs_turn(scenario) -> None:
    while scenario.turn.active_player == "alice":
        scenario.advance()


# --------------------------------------------------------------------------
# First Day of Class - "Whenever a creature you control enters this turn,
# put a +1/+1 counter on it and it gains haste until end of turn."
# --------------------------------------------------------------------------


def _first_day_board(**alice) -> Scenario:
    alice.setdefault("hand", [])
    alice["hand"] = ["First Day of Class", *alice["hand"]]
    alice.setdefault("battlefield", [])
    alice["battlefield"] = ["Mountain", "Mountain", *alice["battlefield"]]
    alice.setdefault("library", ["Plains"] * 5)
    return (
        Scenario()
        .player("alice", **alice)
        .player("bob", hand=["Llanowar Elves"], library=["Forest"] * 5)
    )


def _cast_first_day(scenario, *, learn: bool = False) -> None:
    """Cast and resolve it; Learn's optional discard (CR 701.48a) declined
    unless `learn`."""
    scenario.will_take_the_may(learn)
    scenario.cast_and_resolve("First Day of Class", auto=True)


def test_first_day_of_class_counters_and_hastes_a_creature_entering_afterwards():
    scenario = _first_day_board(hand=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_first_day(scenario)
    bears = scenario.put_onto_battlefield("Grizzly Bears")
    _resolve_everything(scenario)

    assert bears.counter_count(Counter.PLUS_ONE) == 1
    assert has_keyword(bears, "Haste", scenario.game)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert scenario.can_attack(bears), "haste lets the new creature attack this turn"


def test_first_day_of_class_triggers_once_per_creature_entering():
    """CR 603.7b's stated duration - not one-shot."""
    scenario = _first_day_board(hand=["Grizzly Bears", "Llanowar Elves"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_first_day(scenario)
    bears = scenario.put_onto_battlefield("Grizzly Bears")
    _resolve_everything(scenario)
    elves = scenario.put_onto_battlefield("Llanowar Elves")
    _resolve_everything(scenario)

    assert bears.counter_count(Counter.PLUS_ONE) == 1
    assert elves.counter_count(Counter.PLUS_ONE) == 1


def test_first_day_of_class_ignores_a_creature_an_opponent_controls():
    scenario = _first_day_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_first_day(scenario)
    elves = scenario.put_onto_battlefield("Llanowar Elves", "bob")
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack == []
    assert elves.counter_count(Counter.PLUS_ONE) == 0


def test_first_day_of_class_ignores_a_noncreature_permanent_entering():
    scenario = _first_day_board(hand=["Hardened Scales"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_first_day(scenario)
    scenario.put_onto_battlefield("Hardened Scales")
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack == []


def test_a_creature_that_entered_before_resolution_is_not_affected():
    """CR 603.7a: nothing that happened before the ability existed counts."""
    scenario = _first_day_board(hand=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bears = scenario.put_onto_battlefield("Grizzly Bears")
    _cast_first_day(scenario)
    _resolve_everything(scenario)

    assert bears.counter_count(Counter.PLUS_ONE) == 0


def test_first_day_of_class_stops_at_the_cleanup_step():
    """CR 514.2: "this turn" ends in cleanup - next turn's creature gets nothing."""
    scenario = _first_day_board(hand=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_first_day(scenario)
    _to_bobs_turn(scenario)
    assert scenario.game.delayed_triggers.triggers == []

    bears = scenario.put_onto_battlefield("Grizzly Bears", "alice")
    scenario.game.put_triggers_on_stack()
    assert bears.counter_count(Counter.PLUS_ONE) == 0


def test_the_created_ability_survives_a_dump_and_decode_and_still_fires():
    """No callable on the model: the ability is a `kind`-tagged record."""
    from magic_cards_model.machines.delayed import CreatedTriggeredAbility

    scenario = _first_day_board(hand=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_first_day(scenario)

    dumped = scenario.game.model_dump(mode="json")
    (created,) = dumped["delayed_triggers"]["triggers"]
    assert created["effect"]["kind"] == "created_triggered_ability"

    decoded = Game.model_validate(dumped)
    (trigger,) = decoded.delayed_triggers.triggers
    assert isinstance(trigger.effect, CreatedTriggeredAbility)
    bears = next(state for state in decoded.player("alice").hand if state.name == "Grizzly Bears")
    decoded.put_onto_battlefield(bears, "alice")
    decoded.put_triggers_on_stack()
    while decoded.stack:
        decoded.resolve_top()
    assert bears.counter_count(Counter.PLUS_ONE) == 1


def test_first_day_of_class_still_learns():
    """The second paragraph is its own instruction - Learn is offered after
    the trigger is created (CR 701.48a); with a card in hand alice may
    discard it and draw."""
    scenario = _first_day_board(hand=["Grizzly Bears"], library=["Island"] * 3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")

    scenario.will_discard(bears)
    _cast_first_day(scenario, learn=True)

    assert bears.zone is Zone.GRAVEYARD
    assert [state.name for state in scenario.player("alice").hand] == ["Island"]
    assert len(scenario.game.delayed_triggers.triggers) == 1


# --------------------------------------------------------------------------
# Beck // Call - "Whenever a creature enters this turn, you may draw a card."
# --------------------------------------------------------------------------


def _beck_board(*alice_lands: str) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Beck // Call", "Grizzly Bears"],
            battlefield=list(alice_lands or ("Forest", "Island")),
            library=["Plains"] * 6,
        )
        .player("bob", hand=["Llanowar Elves"], library=["Swamp"] * 3)
    )


def test_beck_draws_for_any_creature_entering_including_an_opponents():
    """Ruling 2013-04-15: "no matter who controls it"."""
    scenario = _beck_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, times=None)

    scenario.cast_and_resolve("Beck", auto=True)
    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    _resolve_everything(scenario)
    scenario.put_onto_battlefield("Llanowar Elves", "bob")
    _resolve_everything(scenario)

    assert [state.name for state in scenario.player("alice").hand] == ["Plains", "Plains"]
    assert scenario.player("bob").hand == []


def test_beck_draw_is_optional():
    scenario = _beck_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, times=None)

    scenario.cast_and_resolve("Beck", auto=True)
    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    _resolve_everything(scenario)

    assert scenario.player("alice").hand == []


def test_beck_and_call_fused_draws_for_each_bird():
    """CR 702.102d resolves Beck first, so the ability exists when Call's four
    Birds enter - ruling 2013-04-15: "You'll draw up to four cards."."""
    scenario = _beck_board(
        "Forest", "Island", "Island", "Plains", "Plains", "Plains", "Forest", "Forest"
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, times=None)

    casting = scenario.cast("Beck")
    casting.cast_fused()
    payment = casting.begin_paying()
    scenario.auto_pay(payment)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    _resolve_everything(scenario)

    birds = [p for p in scenario.game.permanents_controlled_by("alice") if p.name == "Bird Token"]
    assert len(birds) == 4
    hand = [state.name for state in scenario.player("alice").hand]
    assert hand.count("Plains") == 4


def test_call_alone_creates_no_draw_ability():
    scenario = _beck_board(
        "Forest", "Island", "Island", "Plains", "Plains", "Plains", "Forest", "Forest"
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Beck")
    casting.cast_as_split_half("Call")
    payment = casting.begin_paying()
    scenario.auto_pay(payment)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    _resolve_everything(scenario)

    assert scenario.game.delayed_triggers.triggers == []
    assert "Plains" not in [state.name for state in scenario.player("alice").hand]


# --------------------------------------------------------------------------
# Rite of Harmony (proof printing) - "Whenever a creature or enchantment you
# control enters this turn, draw a card."
# --------------------------------------------------------------------------


def _rite_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Rite of Harmony", "Grizzly Bears", "Hardened Scales", "Forest"],
            battlefield=["Forest", "Plains"],
            library=["Island"] * 5,
        )
        .player("bob", hand=["Llanowar Elves"])
    )


def test_rite_of_harmony_draws_for_a_creature_and_for_an_enchantment():
    scenario = _rite_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Rite of Harmony", auto=True)
    scenario.put_onto_battlefield("Grizzly Bears")
    _resolve_everything(scenario)
    scenario.put_onto_battlefield("Hardened Scales")
    _resolve_everything(scenario)

    assert [s.name for s in scenario.player("alice").hand].count("Island") == 2


def test_rite_of_harmony_ignores_a_land_and_an_opponents_creature():
    scenario = _rite_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Rite of Harmony", auto=True)
    scenario.put_onto_battlefield("Forest")
    scenario.put_onto_battlefield("Llanowar Elves", "bob")
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack == []
    assert "Island" not in [s.name for s in scenario.player("alice").hand]


# --------------------------------------------------------------------------
# Dovin, Grand Arbiter's +1 - "Until end of turn, whenever a creature you
# control deals combat damage to a player, put a loyalty counter on Dovin."
# --------------------------------------------------------------------------


def _dovin_board(*bob: str) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Dovin, Grand Arbiter", "Grizzly Bears", "Llanowar Elves"])
        .player("bob", battlefield=list(bob))
    )


def _activate_plus_one(scenario):
    dovin = scenario.find("Dovin, Grand Arbiter", Zone.BATTLEFIELD, "alice")
    scenario.activate(dovin, index=0)
    scenario.pass_until_resolved()
    return dovin


def test_dovin_gains_a_loyalty_counter_per_creature_that_connects():
    """Ruling 2019-01-25: it triggers for each creature you control that
    deals combat damage to a player."""
    scenario = _dovin_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dovin = _activate_plus_one(scenario)
    assert dovin.counter_count(Counter.LOYALTY) == 4

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Grizzly Bears"), scenario.creature("Llanowar Elves"))
    scenario.no_blocks()
    scenario.combat_damage()
    _resolve_everything(scenario)

    assert scenario.player("bob").life == 17
    assert dovin.counter_count(Counter.LOYALTY) == 6


def test_dovin_ignores_combat_damage_dealt_to_a_creature():
    scenario = _dovin_board("Wall of Omens").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dovin = _activate_plus_one(scenario)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears")
    scenario.attack_with(bears)
    scenario.block(bears, scenario.creature("Wall of Omens", "bob"))
    scenario.combat_damage()
    _resolve_everything(scenario)

    assert dovin.counter_count(Counter.LOYALTY) == 4


def test_dovin_ignores_an_opponents_creature_connecting():
    """ "A creature you control" - bob's creature dealing combat damage to
    alice is not one of hers."""
    scenario = _dovin_board("Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dovin = _activate_plus_one(scenario)
    bobs_bears = scenario.creature("Grizzly Bears", "bob")

    scenario.game._dealing_combat_damage = True
    try:
        scenario.game.deal_damage(scenario.player("alice"), 2, source=bobs_bears)
    finally:
        scenario.game._dealing_combat_damage = False
    _resolve_everything(scenario)

    assert dovin.counter_count(Counter.LOYALTY) == 4


def test_dovin_ignores_noncombat_damage():
    scenario = _dovin_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dovin = _activate_plus_one(scenario)

    scenario.game.deal_damage(scenario.player("bob"), 2, source=scenario.creature("Grizzly Bears"))
    _resolve_everything(scenario)

    assert dovin.counter_count(Counter.LOYALTY) == 4


def test_dovin_ability_ends_with_the_turn():
    scenario = _dovin_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_plus_one(scenario)
    _to_bobs_turn(scenario)

    assert scenario.game.delayed_triggers.triggers == []


# --------------------------------------------------------------------------
# Mistway Spy (proof printing) - "When this creature is turned face up,
# until end of turn, whenever a creature you control deals combat damage to
# a player, investigate."
# --------------------------------------------------------------------------


def test_mistway_spy_investigates_for_each_creature_that_connects_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mistway Spy"],
            battlefield=["Island"] * 5 + ["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Mistway Spy")
    casting.use_keyword("Disguise")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Island"] * 3))
    scenario.put_on_stack(casting)
    spy = scenario.resolve_top()
    scenario.turn_face_up(spy, *scenario.untapped_sources("Island", "Island"))
    _resolve_everything(scenario)
    assert len(scenario.game.delayed_triggers.triggers) == 1

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Grizzly Bears"))
    scenario.no_blocks()
    scenario.combat_damage()
    _resolve_everything(scenario)

    clues = [p for p in scenario.game.permanents_controlled_by("alice") if p.name == "Clue Token"]
    assert len(clues) == 1


# --------------------------------------------------------------------------
# The created ability's effect reader, proven on a printed trigger: Wartime
# Protestors - "Whenever another Ally you control enters, put a +1/+1 counter
# on that creature and it gains haste until end of turn." ("that creature"
# where First Day of Class says "it"; a subtype-restricted condition.)
# --------------------------------------------------------------------------


def test_wartime_protestors_counters_and_hastes_the_entering_ally():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Wartime Protestors"], hand=["Wartime Protestors"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first = scenario.creature("Wartime Protestors")

    second = scenario.put_onto_battlefield("Wartime Protestors")
    _resolve_everything(scenario)

    assert second.counter_count(Counter.PLUS_ONE) == 1, "the entering Ally, not the source"
    assert first.counter_count(Counter.PLUS_ONE) == 0
    assert has_keyword(second, "Haste", scenario.game)


def test_wartime_protestors_ignores_a_non_ally():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Wartime Protestors"], hand=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bears = scenario.put_onto_battlefield("Grizzly Bears")
    _resolve_everything(scenario)

    assert bears.counter_count(Counter.PLUS_ONE) == 0
