"""Echo - CR 702.30, and Volcano Hellion's own echo {X} and enters trigger.

Rules read in full with `mise run rules:find` this session:

- **CR 702.30a** - "Echo is a triggered ability. 'Echo [cost]' means 'At the
  beginning of your upkeep, if this permanent came under your control since
  the beginning of your last upkeep, sacrifice it unless you pay [cost].'"
- **CR 603.4** - the intervening "if" is checked as the upkeep begins and
  again as the ability resolves.
- **CR 107.3** - an X the text defines is not chosen; Volcano Hellion's
  "where X is your life total" is read as the cost is paid.
- **CR 615.12** - "Some effects state that damage 'can't be prevented.'"
- **CR 701.21a** - sacrificing moves the permanent to its owner's graveyard.

Flamecore Elemental ("Echo {2}{R}{R}", a vanilla 5/4) is the plain keyword
line, the proof printing for the echo machine that is not the reported card.
Volcano Hellion carries echo as a static sentence with a defined X. No other
printing legal in Modern, Pioneer or Standard prints "an amount of damage of
your choice" (searched over the oracle bulk), so its enters trigger is proven
on itself only.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent, TriggerWord
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.keywords import executes, keyword_triggered_abilities
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario

ECHO_IF = "this permanent came under your control since the beginning of your last upkeep"


def _at_untap(alice_battlefield=(), alice_hand=(), bob_battlefield=(), bob_hand=(), life=None):
    builder = Scenario().player(
        "alice",
        battlefield=list(alice_battlefield),
        hand=list(alice_hand),
        library=["Mountain"] * 10,
        **({"life": life} if life is not None else {}),
    )
    scenario = (
        builder.player(
            "bob", battlefield=list(bob_battlefield), hand=list(bob_hand), library=["Mountain"] * 10
        )
    ).build()
    scenario.start_at(Step.UNTAP)
    return scenario


def _resolve_all(scenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def _to_upkeep_of(scenario, who: str) -> None:
    """Advance, resolving whatever triggers, until `who`'s next upkeep begins."""
    scenario.advance()
    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == who):
        _resolve_all(scenario)
        scenario.advance()


def _echo_asks(scenario, source):
    return [
        q
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.PAY_MANA and q.source == source
    ]


# -- the keyword line, and the static sentence, are the upkeep trigger --------


def test_the_keyword_line_is_written_out_as_the_upkeep_trigger():
    (ability,) = keyword_triggered_abilities(card("Flamecore Elemental"))
    assert ability.keyword == "echo"
    assert ability.word is TriggerWord.AT
    assert ability.event is TriggerEvent.BEGINNING_OF_STEP
    assert ability.condition == "the beginning of your upkeep"
    assert ability.intervening_if == ECHO_IF
    assert ability.effect == "sacrifice it unless you pay {2}{R}{R}"
    assert executes("Echo")


def test_has_echo_x_static_line_is_the_same_trigger_with_its_x_kept():
    (echo,) = [
        a for a in keyword_triggered_abilities(card("Volcano Hellion")) if a.keyword == "echo"
    ]
    assert echo.intervening_if == ECHO_IF
    assert echo.effect == "sacrifice it unless you pay {X}, where X is your life total"


# -- Flamecore Elemental: plain echo ----------------------------------------------


def test_echo_triggers_on_the_first_upkeep_after_it_entered_and_paying_keeps_it():
    scenario = _at_untap(alice_battlefield=["Mountain"] * 4, alice_hand=["Flamecore Elemental"])
    flamecore = scenario.put_onto_battlefield("Flamecore Elemental")
    scenario.will_pay_the_mana_cost(True, username="alice", source="Flamecore Elemental")

    scenario.advance()
    assert scenario.step is Step.UPKEEP
    assert scenario.stack_names() == ["Flamecore Elemental's triggered ability"]
    _resolve_all(scenario)

    (asked,) = _echo_asks(scenario, "Flamecore Elemental")
    assert asked.player == "alice" and asked.amount == 4 and asked.affirmative_is_legal
    assert flamecore.zone is Zone.BATTLEFIELD
    assert all(p.tapped for p in scenario.game.battlefield if p.name == "Mountain")


def test_declining_the_echo_cost_sacrifices_it():
    scenario = _at_untap(alice_battlefield=["Mountain"] * 4, alice_hand=["Flamecore Elemental"])
    flamecore = scenario.put_onto_battlefield("Flamecore Elemental")
    scenario.will_pay_the_mana_cost(False, username="alice", source="Flamecore Elemental")

    scenario.advance()
    _resolve_all(scenario)

    assert flamecore.zone is Zone.GRAVEYARD
    assert not any(p.tapped for p in scenario.game.battlefield if p.name == "Mountain")


def test_too_little_mana_can_only_sacrifice_and_taps_nothing():
    """CR 118.3: {2}{R}{R} with three Mountains cannot be paid in full."""
    scenario = _at_untap(alice_battlefield=["Mountain"] * 3, alice_hand=["Flamecore Elemental"])
    flamecore = scenario.put_onto_battlefield("Flamecore Elemental")

    scenario.advance()
    _resolve_all(scenario)

    (asked,) = _echo_asks(scenario, "Flamecore Elemental")
    assert not asked.affirmative_is_legal
    assert flamecore.zone is Zone.GRAVEYARD


def test_once_paid_it_does_not_trigger_again_at_the_next_upkeep():
    scenario = _at_untap(alice_battlefield=["Mountain"] * 4, alice_hand=["Flamecore Elemental"])
    flamecore = scenario.put_onto_battlefield("Flamecore Elemental")
    scenario.will_pay_the_mana_cost(True, username="alice", source="Flamecore Elemental")

    scenario.advance()
    _resolve_all(scenario)
    _to_upkeep_of(scenario, "alice")

    assert scenario.stack_names() == []
    assert len(_echo_asks(scenario, "Flamecore Elemental")) == 1
    assert flamecore.zone is Zone.BATTLEFIELD


def test_it_triggers_only_at_its_controllers_upkeep():
    """Entered during alice's turn; bob's upkeep is not "your upkeep"."""
    scenario = _at_untap(alice_battlefield=["Mountain"] * 4, alice_hand=["Flamecore Elemental"])
    scenario.advance()  # alice's upkeep, nothing on the battlefield yet
    scenario.put_onto_battlefield("Flamecore Elemental")
    _to_upkeep_of(scenario, "bob")

    assert scenario.stack_names() == []


def test_entering_during_its_controllers_upkeep_waits_for_the_next_one():
    """It came under alice's control after this upkeep began, so the next
    upkeep's "since the beginning of your last upkeep" still holds."""
    scenario = _at_untap(alice_battlefield=["Mountain"] * 4, alice_hand=["Flamecore Elemental"])
    scenario.advance()  # alice's upkeep begins with nothing to trigger
    assert scenario.stack_names() == []
    flamecore = scenario.put_onto_battlefield("Flamecore Elemental")
    scenario.will_pay_the_mana_cost(True, username="alice", source="Flamecore Elemental")

    _to_upkeep_of(scenario, "alice")
    assert scenario.stack_names() == ["Flamecore Elemental's triggered ability"]
    _resolve_all(scenario)
    assert flamecore.zone is Zone.BATTLEFIELD


def test_a_permanent_set_up_on_the_battlefield_owes_its_echo_at_the_first_upkeep():
    scenario = _at_untap(alice_battlefield=["Flamecore Elemental", *["Mountain"] * 4])
    scenario.advance()
    assert scenario.stack_names() == ["Flamecore Elemental's triggered ability"]


def test_regaining_control_after_an_act_of_treason_makes_echo_due_again():
    """Bob borrows the paid-for Elemental until end of turn; it comes back
    under alice's control in bob's cleanup step, which is after the beginning
    of her last upkeep - so echo triggers again (CR 702.30a)."""
    scenario = _at_untap(
        alice_battlefield=["Mountain"] * 4,
        alice_hand=["Flamecore Elemental"],
        bob_battlefield=["Mountain"] * 3,
        bob_hand=["Act of Treason"],
    )
    flamecore = scenario.put_onto_battlefield("Flamecore Elemental")
    scenario.will_pay_the_mana_cost(True, username="alice", source="Flamecore Elemental", times=2)
    scenario.advance()
    _resolve_all(scenario)
    assert len(_echo_asks(scenario, "Flamecore Elemental")) == 1

    _to_upkeep_of(scenario, "bob")
    while scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()
    mountains = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="bob")
    scenario.cast_and_resolve("Act of Treason", *mountains, username="bob", targets=[flamecore])
    assert flamecore.controller == "bob"
    assert scenario.stack_names() == []

    _to_upkeep_of(scenario, "alice")
    assert flamecore.controller == "alice"
    assert scenario.stack_names() == ["Flamecore Elemental's triggered ability"]
    _resolve_all(scenario)
    assert len(_echo_asks(scenario, "Flamecore Elemental")) == 2
    assert flamecore.zone is Zone.BATTLEFIELD


def test_a_permanent_that_left_and_came_back_owes_echo_again():
    """CR 400.7: the returned card is a new object that just came under
    alice's control."""
    scenario = _at_untap(alice_battlefield=["Mountain"] * 4, alice_hand=["Flamecore Elemental"])
    flamecore = scenario.put_onto_battlefield("Flamecore Elemental")
    scenario.will_pay_the_mana_cost(True, username="alice", source="Flamecore Elemental", times=2)
    scenario.advance()
    _resolve_all(scenario)

    scenario.game.return_to_hand(flamecore)
    scenario.put_onto_battlefield("Flamecore Elemental")
    _to_upkeep_of(scenario, "alice")
    assert scenario.stack_names() == ["Flamecore Elemental's triggered ability"]


# -- Volcano Hellion: echo {X}, where X is your life total -----------------------


def test_volcano_hellions_echo_costs_its_controllers_life_total_in_generic_mana():
    scenario = _at_untap(alice_battlefield=["Mountain"] * 3, alice_hand=["Volcano Hellion"], life=3)
    hellion = scenario.put_onto_battlefield("Volcano Hellion")
    _resolve_all(scenario)  # its own enters trigger, no target chosen
    scenario.will_pay_the_mana_cost(True, username="alice", source="Volcano Hellion")

    scenario.advance()
    _resolve_all(scenario)

    (asked,) = _echo_asks(scenario, "Volcano Hellion")
    assert asked.amount == 3 and asked.affirmative_is_legal
    assert hellion.zone is Zone.BATTLEFIELD
    assert all(p.tapped for p in scenario.game.battlefield if p.name == "Mountain")


def test_volcano_hellions_x_is_read_as_the_cost_is_paid_not_as_it_triggered():
    """The trigger goes on the stack at 20 life, and alice's life is 2 by the
    time it resolves: X is 2, not 20."""
    scenario = _at_untap(alice_battlefield=["Mountain"] * 3, alice_hand=["Volcano Hellion"])
    hellion = scenario.put_onto_battlefield("Volcano Hellion")
    _resolve_all(scenario)
    scenario.will_pay_the_mana_cost(True, username="alice", source="Volcano Hellion")

    scenario.advance()
    assert "Volcano Hellion's triggered ability" in scenario.stack_names()
    scenario.player("alice").life = 2
    _resolve_all(scenario)

    (asked,) = _echo_asks(scenario, "Volcano Hellion")
    assert asked.amount == 2
    assert hellion.zone is Zone.BATTLEFIELD
    assert len([p for p in scenario.game.battlefield if p.name == "Mountain" and p.tapped]) == 2


def test_volcano_hellion_at_twenty_life_with_three_lands_is_sacrificed():
    scenario = _at_untap(alice_battlefield=["Mountain"] * 3, alice_hand=["Volcano Hellion"])
    hellion = scenario.put_onto_battlefield("Volcano Hellion")
    _resolve_all(scenario)

    scenario.advance()
    _resolve_all(scenario)

    (asked,) = _echo_asks(scenario, "Volcano Hellion")
    assert asked.amount == 20 and not asked.affirmative_is_legal
    assert hellion.zone is Zone.GRAVEYARD


# -- Volcano Hellion's enters trigger: a chosen amount to you and target creature,
# -- the damage can't be prevented (CR 615.12) --------------------------------------


def _hellion_enters(bob_battlefield=("Grizzly Bears",), alice_hand=()):
    scenario = (
        Scenario()
        .player("alice", hand=["Volcano Hellion", *alice_hand], battlefield=["Plains"] * 2)
        .player("bob", battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _enter_targeting(scenario, target):
    scenario.choose_trigger_targets("Volcano Hellion", [target])
    scenario.put_onto_battlefield("Volcano Hellion")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Volcano Hellion's triggered ability"]


def test_the_chosen_amount_is_dealt_to_you_and_to_the_target_creature():
    scenario = _hellion_enters(bob_battlefield=["Craw Wurm"])
    wurm = scenario.creature("Craw Wurm", "bob")
    _enter_targeting(scenario, wurm)
    scenario.will_choose_an_amount(3, username="alice", source="Volcano Hellion")
    scenario.resolve_top()

    (asked,) = [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_AN_AMOUNT]
    assert asked.player == "alice"
    assert scenario.player("alice").life == 17
    assert wurm.damage == 3 and wurm.zone is Zone.BATTLEFIELD


def test_an_amount_beyond_the_creatures_toughness_kills_it_and_costs_that_much_life():
    scenario = _hellion_enters()
    bears = scenario.creature("Grizzly Bears", "bob")
    _enter_targeting(scenario, bears)
    scenario.will_choose_an_amount(7, username="alice", source="Volcano Hellion")
    scenario.resolve_top()
    scenario.state_based_actions()

    assert scenario.player("alice").life == 13
    assert bears.zone is Zone.GRAVEYARD


def test_choosing_zero_deals_no_damage_to_either():
    scenario = _hellion_enters()
    bears = scenario.creature("Grizzly Bears", "bob")
    _enter_targeting(scenario, bears)
    scenario.will_choose_an_amount(0, username="alice", source="Volcano Hellion")
    scenario.resolve_top()

    assert scenario.player("alice").life == 20
    assert bears.damage == 0


def test_the_damage_cant_be_prevented_and_the_shield_is_left_untouched():
    """Healing Salve's "prevent the next 3 damage" on alice: CR 615.12 - the
    Hellion's damage still lands in full, and the shield is not used up."""
    scenario = _hellion_enters(bob_battlefield=["Craw Wurm"], alice_hand=["Healing Salve"])
    wurm = scenario.creature("Craw Wurm", "bob")
    me = scenario.player("alice")
    _enter_targeting(scenario, wurm)
    salve = scenario.cast("Healing Salve", "alice")
    salve.choose_modes([2])
    salve.choose_targets([me])
    payment = salve.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains"))
    scenario.put_on_stack(salve)
    scenario.resolve_top()
    scenario.will_choose_an_amount(3, username="alice", source="Volcano Hellion")
    scenario.resolve_top()

    assert me.life == 17
    assert wurm.damage == 3
    shields = [s for s in scenario.game.prevention_shields if s.amount]
    assert [s.amount for s in shields] == [3]


def test_with_its_target_gone_it_does_not_resolve_and_you_take_nothing():
    """CR 608.2b: the only target is illegal, so the ability does nothing at
    all - "you" is not a target and is not dealt damage on its own."""
    scenario = _hellion_enters()
    bears = scenario.creature("Grizzly Bears", "bob")
    _enter_targeting(scenario, bears)
    scenario.will_choose_an_amount(3, username="alice", source="Volcano Hellion")
    scenario.game.return_to_hand(bears)
    scenario.resolve_top()

    assert scenario.player("alice").life == 20
