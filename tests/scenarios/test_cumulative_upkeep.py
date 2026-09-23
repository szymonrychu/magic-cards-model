"""Cumulative upkeep - CR 702.24, one pay-or-sacrifice decision per upkeep.

Rules read in full with `mise run rules:find 702.24` this session (CR
effective September 25, 2026):

- **CR 702.24a** - "Cumulative upkeep is a triggered ability that imposes an
  increasing cost on a permanent. 'Cumulative upkeep [cost]' means 'At the
  beginning of your upkeep, if this permanent is on the battlefield, put an
  age counter on this permanent. Then you may pay [cost] for each age counter
  on it. If you don't, sacrifice it.' If [cost] has choices associated with
  it, each choice is made separately for each age counter, then either the
  entire set of costs is paid, or none of them is paid. Partial payments
  aren't allowed."
- **CR 702.24b** - "If a permanent has multiple instances of cumulative
  upkeep, each triggers separately. However, the age counters are not
  connected to any particular ability; each cumulative upkeep ability will
  count the total number of age counters on the permanent at the time that
  ability resolves."
- **CR 118.3** - "A player can't pay a cost without having the necessary
  resources to pay it fully." - an unaffordable total offers only the
  sacrifice.
- **CR 106.6** - Snowfall's "Spend this mana only to pay cumulative upkeep
  costs" is a spend restriction this payment now satisfies.

No card legal in Modern, Pioneer or Standard prints cumulative upkeep twice,
so CR 702.24b's first sentence has no real printing to prove it on; its
second sentence - the count is every age counter on the permanent, not the
ones one ability put there - is proven below with a counter no upkeep put on.

Kjeldoran Javelineer ("Cumulative upkeep {1}") and Vexing Sphinx
("Cumulative upkeep-Discard a card.", the reported card) are the space form
and the em-dash form of the keyword line; Arctic Nishoba ("Cumulative upkeep
{G} or {W}") is the off-pool printing whose cost carries a choice.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent, TriggerWord
from magic_cards_model.machines.decisions import DecisionKind, DecisionPending
from magic_cards_model.machines.keywords import executes, keyword_triggered_abilities
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario

AGE = "age"


def _upkeep(*battlefield: str, hand=(), library=None, bob_battlefield=()):
    """Alice's board at her untap step, one `advance()` short of her upkeep."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=list(battlefield),
            hand=list(hand),
            library=library if library is not None else ["Plains"] * 10,
        )
        .player("bob", battlefield=list(bob_battlefield), library=["Plains"] * 10)
        .build()
    )
    scenario.start_at(Step.UNTAP)
    return scenario


def _into_upkeep(scenario) -> None:
    scenario.advance()
    assert scenario.step is Step.UPKEEP


def _resolve_all(scenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def _next_upkeep_of_alice(scenario) -> None:
    """Walk the turn round to alice's next upkeep, resolving what triggers."""
    scenario.advance()
    _resolve_all(scenario)
    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == "alice"):
        scenario.advance()
        _resolve_all(scenario)


def _asked(scenario, kind, source):
    return [q for q in scenario.questions_asked() if q.kind is kind and q.source == source]


# -- the keyword line is the triggered ability CR 702.24a writes ---------------


def test_the_keyword_line_is_written_out_as_the_upkeep_trigger():
    (ability,) = keyword_triggered_abilities(card("Kjeldoran Javelineer"))
    assert ability.keyword == "cumulative upkeep"
    assert ability.word is TriggerWord.AT
    assert ability.event is TriggerEvent.BEGINNING_OF_STEP
    assert ability.condition == "the beginning of your upkeep"
    assert ability.intervening_if == "this permanent is on the battlefield"
    assert ability.effect == (
        "put an age counter on this permanent. Then you may pay {1} for each age counter "
        "on it. If you don't, sacrifice it"
    )
    assert executes("Cumulative upkeep")


def test_the_em_dash_form_carries_its_non_mana_cost():
    (ability,) = keyword_triggered_abilities(card("Vexing Sphinx"))
    assert ability.effect == (
        "put an age counter on this permanent. Then you may pay Discard a card for each "
        "age counter on it. If you don't, sacrifice it"
    )


def test_a_cost_with_a_choice_keeps_it():
    (ability,) = keyword_triggered_abilities(card("Arctic Nishoba"))
    assert "you may pay {G} or {W} for each age counter" in ability.effect


# -- Kjeldoran Javelineer: {1} per age counter -----------------------------------


def test_first_upkeep_puts_one_age_counter_on_and_pays_one():
    scenario = _upkeep("Kjeldoran Javelineer", "Plains", "Plains")
    javelineer = scenario.creature("Kjeldoran Javelineer")
    scenario.will_pay_the_mana_cost(True, username="alice", source="Kjeldoran Javelineer")

    _into_upkeep(scenario)
    assert scenario.stack_names() == ["Kjeldoran Javelineer's triggered ability"]
    _resolve_all(scenario)

    (question,) = _asked(scenario, DecisionKind.PAY_MANA, "Kjeldoran Javelineer")
    assert question.player == "alice"
    assert question.amount == 1
    assert question.affirmative_is_legal
    assert javelineer.zone is Zone.BATTLEFIELD
    assert javelineer.counter_count(AGE) == 1
    tapped = [p for p in scenario.game.battlefield if p.name == "Plains" and p.tapped]
    assert len(tapped) == 1, "{1} for one age counter"


def test_second_upkeep_pays_two():
    scenario = _upkeep("Kjeldoran Javelineer", "Plains", "Plains")
    javelineer = scenario.creature("Kjeldoran Javelineer")
    scenario.will_pay_the_mana_cost(True, username="alice", source="Kjeldoran Javelineer", times=2)

    _into_upkeep(scenario)
    _resolve_all(scenario)
    _next_upkeep_of_alice(scenario)
    _resolve_all(scenario)

    asks = _asked(scenario, DecisionKind.PAY_MANA, "Kjeldoran Javelineer")
    assert [q.amount for q in asks] == [1, 2]
    assert javelineer.zone is Zone.BATTLEFIELD
    assert javelineer.counter_count(AGE) == 2
    assert all(p.tapped for p in scenario.game.battlefield if p.name == "Plains")


def test_declining_sacrifices_it_with_the_new_age_counter_already_on():
    scenario = _upkeep("Kjeldoran Javelineer", "Plains", "Plains")
    javelineer = scenario.creature("Kjeldoran Javelineer")
    scenario.will_pay_the_mana_cost(False, username="alice", source="Kjeldoran Javelineer")

    _into_upkeep(scenario)
    _resolve_all(scenario)

    assert javelineer.zone is Zone.GRAVEYARD
    assert javelineer.last_known_counters[AGE] == 1, "the counter goes on before the payment"
    assert not any(p.tapped for p in scenario.game.battlefield if p.name == "Plains")


def test_insufficient_mana_can_only_sacrifice_and_pays_nothing():
    """{2} owed, one Plains: CR 118.3 makes paying illegal, and no partial
    payment taps the one Plains there is."""
    scenario = _upkeep("Kjeldoran Javelineer", "Plains")
    javelineer = scenario.creature("Kjeldoran Javelineer")
    scenario.game.add_counters(javelineer, AGE, 1)

    _into_upkeep(scenario)
    _resolve_all(scenario)

    (question,) = _asked(scenario, DecisionKind.PAY_MANA, "Kjeldoran Javelineer")
    assert question.amount == 2
    assert not question.affirmative_is_legal
    assert javelineer.zone is Zone.GRAVEYARD
    assert not any(p.tapped for p in scenario.game.battlefield if p.name == "Plains")


def test_a_scripted_yes_to_an_unaffordable_total_is_refused():
    scenario = _upkeep("Kjeldoran Javelineer", "Plains")
    javelineer = scenario.creature("Kjeldoran Javelineer")
    scenario.game.add_counters(javelineer, AGE, 1)
    scenario.will_pay_the_mana_cost(True, username="alice", source="Kjeldoran Javelineer")

    _into_upkeep(scenario)
    with pytest.raises(ValueError, match="608.2d"):
        scenario.resolve_top()


def test_each_upkeep_counts_every_age_counter_not_only_its_own():
    """CR 702.24b: "the age counters are not connected to any particular
    ability" - a counter no upkeep put on is counted too."""
    scenario = _upkeep("Kjeldoran Javelineer", "Plains", "Plains", "Plains")
    javelineer = scenario.creature("Kjeldoran Javelineer")
    scenario.game.add_counters(javelineer, AGE, 2)
    scenario.will_pay_the_mana_cost(True, username="alice", source="Kjeldoran Javelineer")

    _into_upkeep(scenario)
    _resolve_all(scenario)

    (question,) = _asked(scenario, DecisionKind.PAY_MANA, "Kjeldoran Javelineer")
    assert question.amount == 3
    assert javelineer.counter_count(AGE) == 3
    assert all(p.tapped for p in scenario.game.battlefield if p.name == "Plains")


def test_only_its_controllers_upkeep_triggers_it():
    scenario = (
        Scenario()
        .player("bob", library=["Plains"] * 10)
        .player("alice", battlefield=["Kjeldoran Javelineer"], library=["Plains"] * 10)
        .build()
    )
    scenario.start_at(Step.UNTAP)
    scenario.advance()
    assert scenario.step is Step.UPKEEP and scenario.turn.active_player == "bob"

    assert scenario.stack_names() == []
    assert scenario.creature("Kjeldoran Javelineer", "alice").counter_count(AGE) == 0


def test_a_paused_seat_is_asked_the_one_question():
    scenario = _upkeep("Kjeldoran Javelineer", "Plains")
    scenario.game.decisions.pause_when_unanswered = True

    _into_upkeep(scenario)
    with pytest.raises(DecisionPending) as excinfo:
        scenario.resolve_top()

    decision = excinfo.value.pending.decision
    assert decision.kind is DecisionKind.PAY_MANA
    assert decision.player == "alice"
    assert decision.amount == 1


def test_the_tap_ability_deals_damage_equal_to_its_age_counters():
    scenario = (
        Scenario()
        .player("bob", battlefield=["Grizzly Bears"], library=["Plains"] * 5)
        .player("alice", battlefield=["Kjeldoran Javelineer"], library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "bob")
    javelineer = scenario.creature("Kjeldoran Javelineer", "alice")
    javelineer.summoning_sick = False  # under alice's control since her last turn
    scenario.game.add_counters(javelineer, AGE, 2)
    scenario.attack_with(bears)
    scenario.pass_priority("bob")

    scenario.activate(javelineer, username="alice", targets=[bears])
    scenario.resolve_top()

    scenario.state_based_actions()
    assert bears.zone is Zone.GRAVEYARD, "2 damage to a 2/2"


def test_the_tap_ability_with_one_age_counter_deals_one():
    scenario = (
        Scenario()
        .player("bob", battlefield=["Grizzly Bears"], library=["Plains"] * 5)
        .player("alice", battlefield=["Kjeldoran Javelineer"], library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "bob")
    javelineer = scenario.creature("Kjeldoran Javelineer", "alice")
    javelineer.summoning_sick = False  # under alice's control since her last turn
    scenario.game.add_counters(javelineer, AGE, 1)
    scenario.attack_with(bears)
    scenario.pass_priority("bob")

    scenario.activate(javelineer, username="alice", targets=[bears])
    scenario.resolve_top()

    assert bears.damage == 1
    assert bears.zone is Zone.BATTLEFIELD


# -- Vexing Sphinx: discard N chosen cards on the Nth upkeep ---------------------


def test_sphinx_first_upkeep_discards_one_chosen_card():
    scenario = _upkeep("Vexing Sphinx", hand=["Grizzly Bears", "Shock"])
    sphinx = scenario.creature("Vexing Sphinx")
    shock = scenario.find("Shock", Zone.HAND, "alice")
    scenario.will_take_the_may(True, username="alice", source="Vexing Sphinx")
    scenario.will_choose_cards(shock, username="alice", source="Vexing Sphinx")

    _into_upkeep(scenario)
    _resolve_all(scenario)

    (choice,) = _asked(scenario, DecisionKind.CHOOSE_CARDS, "Vexing Sphinx")
    assert choice.amount == 1
    assert shock.zone is Zone.GRAVEYARD
    assert [c.name for c in scenario.player("alice").hand] == ["Grizzly Bears"]
    assert sphinx.zone is Zone.BATTLEFIELD
    assert sphinx.counter_count(AGE) == 1


def test_sphinx_second_upkeep_discards_two_chosen_cards():
    scenario = _upkeep(
        "Vexing Sphinx",
        hand=["Grizzly Bears", "Shock", "Lightning Bolt", "Plains"],
        library=[],
    )
    scenario.game.automatic_turn_based_actions = False
    sphinx = scenario.creature("Vexing Sphinx")
    scenario.game.add_counters(sphinx, AGE, 1)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    scenario.will_take_the_may(True, username="alice", source="Vexing Sphinx")
    scenario.will_choose_cards(bolt, bears, username="alice", source="Vexing Sphinx")

    _into_upkeep(scenario)
    _resolve_all(scenario)

    (choice,) = _asked(scenario, DecisionKind.CHOOSE_CARDS, "Vexing Sphinx")
    assert choice.amount == 2
    assert bolt.zone is Zone.GRAVEYARD and bears.zone is Zone.GRAVEYARD
    assert sorted(c.name for c in scenario.player("alice").hand) == ["Plains", "Shock"]
    assert sphinx.counter_count(AGE) == 2
    assert sphinx.zone is Zone.BATTLEFIELD


def test_sphinx_with_fewer_cards_than_counters_can_only_sacrifice_and_discards_none():
    """Three age counters, two cards: CR 118.3 - and no partial discard."""
    scenario = _upkeep(
        "Vexing Sphinx",
        hand=["Grizzly Bears", "Shock"],
        library=["Plains", "Island", "Swamp", "Mountain", "Forest"],
    )
    scenario.game.automatic_turn_based_actions = False
    sphinx = scenario.creature("Vexing Sphinx")
    scenario.game.add_counters(sphinx, AGE, 2)

    _into_upkeep(scenario)
    _resolve_all(scenario)

    (question,) = _asked(scenario, DecisionKind.MAY, "Vexing Sphinx")
    assert not question.affirmative_is_legal
    assert _asked(scenario, DecisionKind.CHOOSE_CARDS, "Vexing Sphinx") == []
    assert sphinx.zone is Zone.GRAVEYARD
    hand = sorted(c.name for c in scenario.player("alice").hand)
    # the two cards kept, plus one draw per age counter from the dies trigger
    assert hand == sorted(["Grizzly Bears", "Shock", "Plains", "Island", "Swamp"])


def test_sphinx_declined_is_sacrificed_and_draws_one_per_age_counter():
    scenario = _upkeep(
        "Vexing Sphinx",
        hand=["Grizzly Bears", "Shock", "Lightning Bolt"],
        library=["Plains", "Island", "Swamp", "Mountain"],
    )
    scenario.game.automatic_turn_based_actions = False
    sphinx = scenario.creature("Vexing Sphinx")
    scenario.game.add_counters(sphinx, AGE, 1)
    scenario.will_take_the_may(False, username="alice", source="Vexing Sphinx")

    _into_upkeep(scenario)
    _resolve_all(scenario)

    assert sphinx.zone is Zone.GRAVEYARD
    hand = [c.name for c in scenario.player("alice").hand]
    assert sorted(hand) == sorted(["Grizzly Bears", "Shock", "Lightning Bolt", "Plains", "Island"])


# -- Arctic Nishoba: {G} or {W}, chosen per age counter --------------------------


def test_each_counters_choice_is_made_separately_and_the_set_paid_together():
    """Two age counters, one Forest and one Plains: {G} for one counter and {W}
    for the other is a legal set (CR 702.24a), though neither {G}{G} nor
    {W}{W} is."""
    scenario = _upkeep("Arctic Nishoba", "Forest", "Plains")
    nishoba = scenario.creature("Arctic Nishoba")
    scenario.game.add_counters(nishoba, AGE, 1)
    scenario.will_pay_the_mana_cost(True, username="alice", source="Arctic Nishoba")

    _into_upkeep(scenario)
    _resolve_all(scenario)

    (question,) = _asked(scenario, DecisionKind.PAY_MANA, "Arctic Nishoba")
    assert question.affirmative_is_legal
    assert nishoba.zone is Zone.BATTLEFIELD
    assert nishoba.counter_count(AGE) == 2
    assert all(p.tapped for p in scenario.game.battlefield if p.name in ("Forest", "Plains"))


def test_a_choice_cost_the_lands_cannot_cover_sacrifices_and_the_dies_trigger_counts():
    scenario = _upkeep("Arctic Nishoba", "Island", "Island")
    nishoba = scenario.creature("Arctic Nishoba")

    _into_upkeep(scenario)
    _resolve_all(scenario)

    (question,) = _asked(scenario, DecisionKind.PAY_MANA, "Arctic Nishoba")
    assert not question.affirmative_is_legal
    assert nishoba.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 22, "2 life for its one age counter"


# -- Snowfall's restricted mana pays it (CR 106.6) -------------------------------


def test_mana_restricted_to_cumulative_upkeep_pays_it():
    """Bob's Snowfall adds a restricted {U} when alice's Island is tapped; that
    {U} plus the Island's own pays Javelineer's {2}, which one Island alone
    cannot."""
    scenario = _upkeep("Kjeldoran Javelineer", "Island", bob_battlefield=["Snowfall"])
    javelineer = scenario.creature("Kjeldoran Javelineer")
    scenario.game.add_counters(javelineer, AGE, 1)
    scenario.will_take_the_may(True, username="alice", source="Snowfall")

    _into_upkeep(scenario)
    (island,) = scenario.untapped_sources("Island")
    scenario.activate(island)
    pool = scenario.player("alice").mana_pool
    assert pool.total == 2 and len(pool.restricted) == 1
    scenario.will_pay_the_mana_cost(True, username="alice", source="Kjeldoran Javelineer")
    scenario.resolve_top()

    assert javelineer.zone is Zone.BATTLEFIELD
    assert javelineer.counter_count(AGE) == 2
    assert pool.total == 0


# -- the multiplied cost, read by the ordinary cost parser ------------------------


def test_the_cost_is_repeated_once_per_age_counter():
    from magic_cards_model.machines.cost import ComponentKind, cumulative_upkeep_cost

    assert str(cumulative_upkeep_cost("{1}", 3, "alice").mana) == "{3}"
    assert str(cumulative_upkeep_cost("{G} or {W}", 2, "alice").mana) == "{G/W}{G/W}"
    (discard,) = cumulative_upkeep_cost("Discard a card", 3, "alice").components
    assert discard.kind is ComponentKind.DISCARD and discard.required == 3
    (sacrifice,) = cumulative_upkeep_cost("Sacrifice a creature", 2, "alice").components
    assert sacrifice.kind is ComponentKind.SACRIFICE and sacrifice.required == 2
    assert sacrifice.requirement is not None, "each sacrificed permanent is still a creature"


def test_a_cost_this_engine_cannot_pay_mid_resolution_is_not_read():
    """Braid of Fire's "Add {R}." is no payable cost here, so the trigger
    fails closed with a notice instead of forcing a sacrifice."""
    from magic_cards_model.machines.cost import cumulative_upkeep_cost

    assert cumulative_upkeep_cost("Add {R}", 1, "alice") is None
