"""EP-01 round 2, task T7: a static ability granting a castability keyword to
the cards in a zone or to the spells its controller casts (CR 611.3d, CR 610.5,
CR 400.7g), the cost computed from each card's own mana cost.

    Underworld Breach - each nonland card in your graveyard has escape (CR 702.138a)
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import ExileMarker
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def _handled(name: str) -> None:
    outcomes = classify_clauses(card(name))
    assert {o.category for o in outcomes} == {HANDLED}, outcomes


def _board(**kwargs) -> Scenario:
    return Scenario().manual_turn_based_actions().player("alice", **kwargs).player("bob")


# -- Underworld Breach: escape for every nonland card in the graveyard -------


def test_underworld_breach_clauses_are_handled():
    _handled("Underworld Breach")


def test_breach_gives_a_graveyard_card_escape_at_its_own_mana_cost_plus_three_exiled():
    scenario = _board(
        battlefield=["Underworld Breach", "Mountain"],
        graveyard=["Lightning Bolt", "Mountain", "Mountain", "Mountain"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fuel = [c for c in scenario.player("alice").graveyard if c.name == "Mountain"]
    assert len(fuel) == 3

    casting = scenario.cast("Lightning Bolt", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Escape", choosing=fuel)
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    assert str(payment.cost).startswith("{R}")
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.pay_with(payment, mountain)
    bolt = scenario.put_on_stack(casting)

    assert bolt.zone is Zone.STACK
    for exiled in fuel:
        assert exiled.zone is Zone.EXILE


def test_breach_reads_each_cards_own_mana_cost():
    scenario = _board(
        battlefield=["Underworld Breach", "Mountain", "Mountain"],
        graveyard=["Fireblast", "Mountain", "Mountain", "Mountain"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fuel = [c for c in scenario.player("alice").graveyard if c.name == "Mountain"]

    casting = scenario.cast("Fireblast", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Escape", choosing=fuel)
    casting.choose_targets(["bob"])

    assert str(casting.begin_paying().cost).startswith("{4}{R}{R}")


def test_breach_needs_three_other_graveyard_cards():
    scenario = _board(
        battlefield=["Underworld Breach", "Mountain"],
        graveyard=["Lightning Bolt", "Mountain", "Mountain"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fuel = [c for c in scenario.player("alice").graveyard if c.name == "Mountain"]

    casting = scenario.cast("Lightning Bolt", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Escape", choosing=fuel)
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    with pytest.raises(ValueError):
        payment.pay()


def test_breach_does_not_cover_a_land_card():
    scenario = _board(
        battlefield=["Underworld Breach"],
        graveyard=["Mountain", "Mountain", "Mountain", "Mountain"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    with pytest.raises(ValueError):
        casting = scenario.cast("Mountain", from_zone=Zone.GRAVEYARD)
        casting.use_keyword("Escape")


def test_without_breach_the_graveyard_card_has_no_escape():
    scenario = _board(
        battlefield=["Mountain"],
        graveyard=["Lightning Bolt", "Mountain", "Mountain", "Mountain"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    with pytest.raises(ValueError):
        casting = scenario.cast("Lightning Bolt", from_zone=Zone.GRAVEYARD)
        casting.use_keyword("Escape")


# -- Djinn Illuminatus: replicate for every instant and sorcery spell --------


def _djinn(hand: list[str], lands: list[str]) -> Scenario:
    return _board(hand=hand, battlefield=["Djinn Illuminatus", *lands])


def test_djinn_illuminatus_clauses_are_handled():
    _handled("Djinn Illuminatus")


def test_djinn_gives_an_instant_replicate_at_its_own_mana_cost():
    scenario = _djinn(["Lightning Bolt"], ["Mountain", "Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain")

    casting = scenario.cast("Lightning Bolt")
    casting.pay_replicate(1)
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    assert str(payment.cost) == "{R}{R}", "the mana cost plus the replicate cost equal to it"
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)

    assert len(scenario.game.stack) == 2, "the replicate trigger above the spell"
    scenario.resolve_top()
    assert len(scenario.game.stack) == 2, "the original and one copy"
    scenario.resolve_top()
    scenario.resolve_top()
    assert scenario.player("bob").life == 14


def test_djinn_replicate_can_be_paid_twice():
    scenario = _djinn(["Lightning Bolt"], ["Mountain"] * 3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")

    casting = scenario.cast("Lightning Bolt")
    casting.pay_replicate(2)
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    assert str(payment.cost) == "{R}{R}{R}"
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert len(scenario.game.stack) == 3


def test_djinn_reads_each_spells_own_mana_cost():
    scenario = _djinn(["Counterspell"], ["Island", "Island", "Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Counterspell")
    casting.pay_replicate(1)
    assert str(casting.begin_paying().cost) == "{U}{U}{U}{U}"


def test_djinn_does_not_cover_a_creature_spell():
    scenario = _djinn(["Grizzly Bears"], ["Forest"] * 4).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Grizzly Bears")
    with pytest.raises(ValueError, match="replicate"):
        casting.pay_replicate(1)


def test_without_djinn_an_instant_has_no_replicate():
    scenario = _board(hand=["Lightning Bolt"], battlefield=["Mountain", "Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Lightning Bolt")
    with pytest.raises(ValueError, match="replicate"):
        casting.pay_replicate(1)


# -- Falkenrath Gorger: madness for the Vampire cards you own off the battlefield


def _gorger(hand: list[str], bob_hand: list[str] | None = None, gorger: bool = True) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=hand,
            battlefield=[*(["Falkenrath Gorger"] if gorger else []), "Wild Mongrel", "Swamp"]
            + ["Swamp", "Swamp", "Swamp"],
        )
        .player("bob", hand=bob_hand or [])
    )


def _discard_to_mongrel(scenario, name: str, owner: str = "alice"):
    target = scenario.find(name, Zone.HAND, owner)
    scenario.activate(scenario.creature("Wild Mongrel"), discarding=[target])
    return target


def test_falkenrath_gorger_clauses_are_handled():
    _handled("Falkenrath Gorger")


def test_gorger_makes_a_discarded_vampire_card_go_to_exile():
    scenario = _gorger(["Nighthawk Scavenger"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    vampire = _discard_to_mongrel(scenario, "Nighthawk Scavenger")

    assert vampire.zone is Zone.EXILE
    assert vampire.exile_annotation is not None
    assert vampire.exile_annotation.marker is ExileMarker.MADNESS
    assert "Nighthawk Scavenger's triggered ability" in scenario.stack_names()


def test_the_granted_madness_casts_the_card_for_its_own_mana_cost():
    scenario = _gorger(["Nighthawk Scavenger"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vampire = _discard_to_mongrel(scenario, "Nighthawk Scavenger")

    casting = scenario.cast("Nighthawk Scavenger", from_zone=Zone.EXILE)
    casting.use_keyword("Madness")
    assert str(casting.total_cost.mana) == "{1}{B}{B}"
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Swamp", "Swamp", "Swamp"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert vampire.zone is Zone.BATTLEFIELD


def test_declining_the_granted_madness_puts_the_card_into_the_graveyard():
    scenario = _gorger(["Nighthawk Scavenger"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vampire = _discard_to_mongrel(scenario, "Nighthawk Scavenger")

    scenario.resolve_top()  # the madness trigger: the owner does not cast it

    assert vampire.zone is Zone.GRAVEYARD


def test_gorger_does_not_cover_a_non_vampire_card():
    scenario = _gorger(["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert _discard_to_mongrel(scenario, "Grizzly Bears").zone is Zone.GRAVEYARD


def test_without_gorger_a_vampire_card_is_discarded_to_the_graveyard():
    scenario = _gorger(["Nighthawk Scavenger"], gorger=False).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert _discard_to_mongrel(scenario, "Nighthawk Scavenger").zone is Zone.GRAVEYARD


def test_gorger_only_covers_cards_its_controller_owns():
    scenario = (_gorger([], bob_hand=["Nighthawk Scavenger"])).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bobs = scenario.find("Nighthawk Scavenger", Zone.HAND, "bob")
    from magic_cards_model.machines.keywords import discard

    discard(scenario.game, bobs, "bob")

    assert bobs.zone is Zone.GRAVEYARD


# -- Varolz, the Scar-Striped: scavenge for every creature card in the graveyard


def _varolz(graveyard: list[str], lands: list[str]) -> Scenario:
    return _board(
        battlefield=["Varolz, the Scar-Striped", "Grizzly Bears", *lands], graveyard=graveyard
    )


def _scavenge(scenario, name: str, target, username: str = "alice"):
    from magic_cards_model.machines.keywords import off_zone_abilities, off_zone_activation
    from tests.scenarios.harness import mana_from

    state = scenario.find(name, Zone.GRAVEYARD, username)
    pool = off_zone_abilities(state.card, state=state, game=scenario.game)
    (index,) = [i for i, entry in enumerate(pool) if entry.family == "scavenge"]
    activation = off_zone_activation(
        scenario.game, state, username, index, targets=[target] if target is not None else None
    )
    return state, activation, mana_from


def test_varolz_clauses_are_handled():
    _handled("Varolz, the Scar-Striped")


def test_varolz_gives_a_graveyard_creature_scavenge_at_its_own_mana_cost():
    scenario = _varolz(["Hill Giant"], ["Mountain", "Mountain", "Mountain", "Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")

    giant, activation, mana_from = _scavenge(scenario, "Hill Giant", bears)
    assert str(activation.cost.mana) == "{3}{R}"
    payment = activation.begin_paying()
    for source in scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()

    assert giant.zone is Zone.EXILE, "scavenge exiles the card as a cost"
    scenario.resolve_top()
    assert bears.counter_count("+1/+1") == 3, "counters equal to the exiled card's power"


def test_scavenge_is_sorcery_speed():
    scenario = _varolz(["Hill Giant"], ["Mountain"] * 4).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    _giant, activation, _ = _scavenge(scenario, "Hill Giant", bears)
    assert activation.why_not() is None
    scenario.advance()
    while scenario.step is not Step.BEGINNING_OF_COMBAT:
        scenario.advance()
    assert activation.why_not() is not None


def test_varolz_does_not_cover_a_noncreature_card():
    scenario = _varolz(["Lightning Bolt"], ["Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    from magic_cards_model.machines.keywords import off_zone_abilities

    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    assert not [
        e
        for e in off_zone_abilities(bolt.card, state=bolt, game=scenario.game)
        if e.family == "scavenge"
    ]


def test_without_varolz_a_graveyard_creature_has_no_scavenge():
    scenario = _board(graveyard=["Hill Giant"], battlefield=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    from magic_cards_model.machines.keywords import off_zone_abilities

    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    assert not [
        e
        for e in off_zone_abilities(giant.card, state=giant, game=scenario.game)
        if e.family == "scavenge"
    ]


def test_varolz_scavenge_is_offered_as_a_legal_action_with_a_target():
    from magic_cards_model.machines.legal_actions import legal_actions
    from magic_cards_model.models.action import ActionKind

    scenario = _varolz(["Hill Giant"], ["Mountain"] * 4).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")

    offered = [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.kind is ActionKind.ACTIVATE_OFF_ZONE and action.card_id == giant.id
    ]
    assert [action.keyword for action in offered] == ["Scavenge"]
    assert offered[0].mana_cost == "{3}{R}"
    assert offered[0].target_slots


# -- Dream Devourer: foretell for every nonland card in your hand ------------


def _devourer(hand: list[str], lands: list[str]) -> Scenario:
    return _board(hand=hand, battlefield=["Dream Devourer", *lands])


def _foretell(scenario, name: str, sources: int = 2):
    from magic_cards_model.machines.casting import MarkedExile

    card_state = scenario.find(name, Zone.HAND, "alice")
    action = MarkedExile.foretell(scenario.game, card_state, "alice")
    scenario.pay_with(
        action.begin_paying(), *scenario.untapped_sources(*["Mountain"] * sources, username="alice")
    )
    action.take()
    return card_state


def _next_main_of_alice(scenario) -> None:
    for _ in range(60):
        scenario.advance()
        if scenario.step is Step.UNTAP:
            scenario.game.untap_step()
        if scenario.turn.active_player == "alice" and scenario.step is Step.PRECOMBAT_MAIN:
            return
    raise AssertionError("never got back to alice's main phase")


def test_dream_devourer_clauses_are_handled():
    _handled("Dream Devourer")


def test_devourer_lets_a_card_without_foretell_be_foretold():
    scenario = _devourer(["Hill Giant"], ["Mountain"] * 6).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    giant = _foretell(scenario, "Hill Giant")

    assert giant.zone is Zone.EXILE
    assert giant.exile_annotation is not None
    assert giant.exile_annotation.marker is ExileMarker.FORETOLD


def test_the_granted_foretell_cost_is_the_mana_cost_reduced_by_two():
    scenario = _devourer(["Hill Giant"], ["Mountain"] * 6).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _foretell(scenario, "Hill Giant")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    _next_main_of_alice(scenario)

    casting = scenario.cast("Hill Giant", from_zone=Zone.EXILE)
    casting.use_keyword("Foretell")
    assert str(casting.total_cost.mana) == "{1}{R}", "{3}{R} reduced by {2}"
    scenario.pay_with(
        casting.begin_paying(), *scenario.untapped_sources("Mountain", "Mountain", username="alice")
    )
    scenario.put_on_stack(casting)
    giant = scenario.resolve_top()

    assert giant.zone is Zone.BATTLEFIELD


def test_foretelling_pumps_the_devourer_until_end_of_turn():
    scenario = _devourer(["Hill Giant"], ["Mountain"] * 4).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    devourer = scenario.creature("Dream Devourer")
    assert scenario.game.power_of(devourer) == 0

    _foretell(scenario, "Hill Giant")
    scenario.game.put_triggers_on_stack()
    assert "Dream Devourer's triggered ability" in scenario.stack_names()
    scenario.resolve_top()

    assert scenario.game.power_of(devourer) == 2


def test_devourer_does_not_cover_a_land_card():
    scenario = _devourer(["Mountain"], ["Mountain"] * 3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    from magic_cards_model.machines.casting import MarkedExile

    land = scenario.find("Mountain", Zone.HAND, "alice")
    with pytest.raises(ValueError, match="foretell"):
        MarkedExile.foretell(scenario.game, land, "alice")


def test_a_card_that_already_has_foretell_keeps_its_own_cost():
    scenario = _devourer(["Lupine Harbingers"], ["Mountain"] * 3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    from magic_cards_model.machines.spell_grants import granted_zone_keyword_lines

    harbingers = scenario.find("Lupine Harbingers", Zone.HAND, "alice")
    assert granted_zone_keyword_lines(scenario.game, harbingers, "foretell") == []


def test_without_devourer_a_card_cannot_be_foretold():
    scenario = _board(hand=["Hill Giant"], battlefield=["Mountain"] * 3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    from magic_cards_model.machines.casting import MarkedExile

    giant = scenario.find("Hill Giant", Zone.HAND, "alice")
    with pytest.raises(ValueError, match="foretell"):
        MarkedExile.foretell(scenario.game, giant, "alice")


# -- Suspend X: the count is chosen as the card is suspended (CR 702.62a) -----


def _suspend_x(scenario, name: str, x: int, sources: list[str], player: str = "alice"):
    from magic_cards_model.machines.casting import MarkedExile

    card_state = scenario.find(name, Zone.HAND, player)
    action = MarkedExile.suspend(scenario.game, card_state, player, x_value=x)
    scenario.pay_with(action.begin_paying(), *scenario.untapped_sources(*sources, username=player))
    action.take()
    return card_state


def _suspend_scenario(card_name: str, land: str, lands: int) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[card_name], battlefield=[land] * lands, library=["Forest"] * 12)
        .player("bob", library=["Forest"] * 12)
    )


def _upkeep_of(scenario, owner: str = "alice") -> None:
    scenario.advance()
    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == owner):
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
        scenario.advance()


def test_suspend_x_lines_are_read_as_keywords():
    from magic_cards_model.machines.abilities import keyword_ability

    for name in ("Aeon Chronicler", "Roiling Horror"):
        ability = keyword_ability(card(name), "suspend")
        assert ability is not None, name
        assert ability.count is None and ability.count_is_x and ability.count_minimum == 1


@pytest.mark.parametrize(
    ("name", "land", "lands", "x", "cost"),
    [
        ("Aeon Chronicler", "Island", 6, 2, "{5}{U}"),
        ("Roiling Horror", "Swamp", 6, 3, "{3}{B}{B}{B}"),
    ],
)
def test_suspend_x_exiles_the_card_with_x_time_counters_for_the_x_cost(name, land, lands, x, cost):
    from magic_cards_model.machines.casting import MarkedExile
    from magic_cards_model.models.card_state import Counter

    scenario = _suspend_scenario(name, land, lands).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card_state = scenario.find(name, Zone.HAND, "alice")
    action = MarkedExile.suspend(scenario.game, card_state, "alice", x_value=x)
    assert str(action.cost.mana) == cost
    scenario.pay_with(action.begin_paying(), *scenario.untapped_sources(*[land] * lands))
    action.take()

    assert card_state.zone is Zone.EXILE
    assert card_state.counter_count(Counter.TIME) == x
    assert card_state.exile_annotation.marker is ExileMarker.SUSPENDED


def test_suspend_x_cannot_be_zero():
    from magic_cards_model.machines.casting import MarkedExile

    scenario = _suspend_scenario("Aeon Chronicler", "Island", 4).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card_state = scenario.find("Aeon Chronicler", Zone.HAND, "alice")
    with pytest.raises(ValueError, match="can't be 0"):
        MarkedExile.suspend(scenario.game, card_state, "alice", x_value=0)


def test_suspend_x_must_be_announced():
    from magic_cards_model.machines.casting import MarkedExile

    scenario = _suspend_scenario("Aeon Chronicler", "Island", 4).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card_state = scenario.find("Aeon Chronicler", Zone.HAND, "alice")
    with pytest.raises(ValueError, match="X"):
        MarkedExile.suspend(scenario.game, card_state, "alice")


def test_aeon_chroniclers_removed_time_counter_draws_a_card():
    scenario = _suspend_scenario("Aeon Chronicler", "Island", 6).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _suspend_x(scenario, "Aeon Chronicler", 2, ["Island"] * 6)
    hand_before = len(scenario.player("alice").hand)

    _upkeep_of(scenario)
    scenario.resolve_top()  # the upkeep trigger: remove a time counter
    scenario.resolve_top()  # the removed-counter trigger it raised

    # Upkeep's own removal: one counter off, and the trigger drew a card.
    assert len(scenario.player("alice").hand) == hand_before + 1


def test_roiling_horrors_removed_time_counter_drains_a_player():
    scenario = _suspend_scenario("Roiling Horror", "Swamp", 6).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _suspend_x(scenario, "Roiling Horror", 2, ["Swamp"] * 6)
    alice_life, bob_life = scenario.player("alice").life, scenario.player("bob").life

    _upkeep_of(scenario)
    scenario.choose_trigger_targets("Roiling Horror", [scenario.player("bob")])
    scenario.resolve_top()  # the upkeep trigger: remove a time counter
    scenario.resolve_top()  # the removed-counter trigger it raised

    assert scenario.player("alice").life == alice_life + 1
    assert scenario.player("bob").life == bob_life - 1


def test_the_removed_counter_trigger_only_works_in_exile():
    from magic_cards_model.machines.triggers.collect import (
        triggered_abilities_of,
        zones_ability_functions_in,
    )

    scenario = _suspend_scenario("Aeon Chronicler", "Island", 1).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chronicler = scenario.find("Aeon Chronicler", Zone.HAND, "alice")
    (ability,) = [
        a
        for a in triggered_abilities_of(chronicler.card)
        if a.condition == "a time counter is removed from this card"
    ]
    assert zones_ability_functions_in(ability, chronicler, scenario.game) == frozenset({Zone.EXILE})


def test_suspend_x_is_listed_as_a_legal_action_at_its_least_x():
    from magic_cards_model.machines.legal_actions import legal_actions
    from magic_cards_model.models.action import ActionKind

    scenario = _suspend_scenario("Aeon Chronicler", "Island", 5).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (suspend,) = [a for a in legal_actions(scenario.game, "alice") if a.kind is ActionKind.SUSPEND]
    assert suspend.mana_cost == "{4}{U}", "X=1 in {X}{3}{U}"
