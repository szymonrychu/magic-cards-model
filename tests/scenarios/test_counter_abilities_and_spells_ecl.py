"""Scenario: counter abilities and mass counters (ECL) - CR 701.6a.

Two printed shapes:

- **"Counter target `<qualifier>` spell. Its controller `<does something>`."
  as an ability**, not a spell - Glen Elendra Guardian's "{1}{U}, Remove a
  counter from this creature: Counter target noncreature spell. Its
  controller draws a card." and the proof printing Fear of Impostors' "When
  this creature enters, counter target spell. Its controller manifests
  dread." "Its controller" is the controller of the targeted spell, read
  before the spell is countered.
- **"Counter all spells `<scope>` and all abilities `<scope>`."** - Glen
  Elendra's Answer's "Counter all spells your opponents control and all
  abilities your opponents control. Create a 1/1 blue and black Faerie
  creature token with flying for each spell and ability countered this
  way.", and the proof printing Summary Dismissal's "Exile all other spells
  and counter all abilities." A spell or ability that can't be countered
  (CR 101.2) stays on the stack and is not "countered this way".

CR 701.6a: "To counter a spell or ability means to cancel it, removing it
from the stack. It doesn't resolve and none of its effects occur. A countered
spell is put into its owner's graveyard." CR 113.6g: an object's ability that
states it can't be countered functions on the stack.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file: CR 701.6a, CR 101.2, CR 113.6g, CR 608.2b.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _guardian_board(*, bob_hand=("Opt",), bob_battlefield=("Island",)):
    """Alice casts Glen Elendra Guardian so it really enters with its -1/-1
    counter."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Glen Elendra Guardian"],
            battlefield=["Island"] * 7,
            library=["Island"] * 5,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=list(bob_battlefield),
            library=["Mountain"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Glen Elendra Guardian", auto=True, username="alice")
    guardian = scenario.creature("Glen Elendra Guardian", "alice")
    return scenario, guardian


def _bob_casts(scenario, name, targets=None):
    scenario.pass_priority("alice")
    cast = scenario.cast_onto_stack(name, auto=True, username="bob", targets=targets)
    scenario.pass_priority("bob")
    return cast


def test_guardian_enters_with_its_counter_and_counters_a_noncreature_spell():
    scenario, guardian = _guardian_board()
    assert guardian.counters[Counter.MINUS_ONE] == 1
    opt = _bob_casts(scenario, "Opt")
    bob_hand = len(scenario.player("bob").hand)

    scenario.activate(guardian, auto=True, username="alice", targets=[opt])
    assert guardian.counters[Counter.MINUS_ONE] == 0, "the cost removed the counter"
    scenario.resolve_top()

    assert opt.zone is Zone.GRAVEYARD
    assert len(scenario.player("bob").hand) == bob_hand + 1, "its controller - Bob - drew"
    assert guardian.power == 3 and guardian.toughness == 4


def test_the_controller_draws_not_the_guardians_controller():
    scenario, guardian = _guardian_board()
    opt = _bob_casts(scenario, "Opt")
    alice_hand = len(scenario.player("alice").hand)

    scenario.activate(guardian, auto=True, username="alice", targets=[opt])
    scenario.resolve_top()

    assert len(scenario.player("alice").hand) == alice_hand


def test_without_a_counter_the_ability_cannot_be_activated():
    """CR 118.3: the counter the cost removes has to be there."""
    scenario, guardian = _guardian_board(
        bob_hand=("Opt", "Opt"), bob_battlefield=("Island", "Island")
    )
    opt = _bob_casts(scenario, "Opt")
    scenario.activate(guardian, auto=True, username="alice", targets=[opt])
    scenario.resolve_top()
    scenario.pass_priority("alice")
    second = scenario.cast_onto_stack("Opt", auto=True, username="bob")
    scenario.pass_priority("bob")

    with pytest.raises(ValueError, match="counter"):
        scenario.activate(guardian, auto=True, username="alice", targets=[second])


def test_any_kind_of_counter_pays_the_cost():
    """ "Remove a counter" names no kind - a +1/+1 counter pays it as well."""
    scenario, guardian = _guardian_board()
    scenario.game.add_counters(guardian, Counter.PLUS_ONE, 2)
    scenario.state_based_actions()
    assert guardian.counters[Counter.PLUS_ONE] == 1
    assert guardian.counters[Counter.MINUS_ONE] == 0, "the two annihilate (CR 704.5q)"
    opt = _bob_casts(scenario, "Opt")

    scenario.activate(guardian, auto=True, username="alice", targets=[opt])
    scenario.resolve_top()

    assert opt.zone is Zone.GRAVEYARD


def test_a_creature_spell_is_not_a_legal_target():
    scenario, guardian = _guardian_board(
        bob_hand=("Brazen Borrower",), bob_battlefield=("Island", "Island", "Island")
    )
    borrower = _bob_casts(scenario, "Brazen Borrower")

    with pytest.raises(ValueError):
        scenario.activate(guardian, auto=True, username="alice", targets=[borrower])


def test_an_uncounterable_target_stays_but_its_controller_still_draws():
    """CR 101.2 / CR 113.6g: Abrupt Decay can't be countered, so it stays on
    the stack - but the target is still legal, so the ability resolves and
    the second sentence still happens."""
    scenario, guardian = _guardian_board(
        bob_hand=("Abrupt Decay",), bob_battlefield=("Swamp", "Forest")
    )
    decay = _bob_casts(scenario, "Abrupt Decay", targets=[guardian])
    bob_hand = len(scenario.player("bob").hand)

    scenario.activate(guardian, auto=True, username="alice", targets=[decay])
    scenario.resolve_top()

    assert decay.zone is Zone.STACK
    assert len(scenario.player("bob").hand) == bob_hand + 1


def test_a_target_already_gone_draws_nobody_a_card():
    """CR 608.2b: the only target is illegal, so the ability does nothing."""
    scenario, guardian = _guardian_board()
    opt = _bob_casts(scenario, "Opt")
    scenario.activate(guardian, auto=True, username="alice", targets=[opt])
    scenario.game.stack.remove(opt)
    scenario.game.put_into_graveyard(opt)
    bob_hand = len(scenario.player("bob").hand)

    scenario.resolve_top()

    assert len(scenario.player("bob").hand) == bob_hand


def test_fear_of_impostors_counters_on_entering_and_its_controller_manifests_dread():
    """The proof printing: a *triggered* ability with the same "Counter
    target spell. Its controller ..." pair and a different second sentence."""
    scenario = (
        Scenario()
        .player("alice", hand=["Fear of Impostors"], battlefield=["Island"] * 4)
        .player("bob", hand=["Opt"], battlefield=["Island"], library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    opt = scenario.cast_onto_stack("Opt", auto=True, username="bob")
    scenario.pass_priority("bob")
    scenario.cast_onto_stack("Fear of Impostors", auto=True, username="alice")
    scenario.resolve_top()  # Fear of Impostors enters
    scenario.choose_trigger_targets("Fear of Impostors", [opt])
    bob_creatures_before = len(
        [c for c in scenario.game.battlefield if scenario.game.controller_of(c).username == "bob"]
    )

    scenario.resolve_top()  # the enters trigger

    assert opt.zone is Zone.GRAVEYARD
    bob_creatures_after = [
        c for c in scenario.game.battlefield if scenario.game.controller_of(c).username == "bob"
    ]
    assert len(bob_creatures_after) == bob_creatures_before + 1, "Bob manifested dread"


# -- counter all spells and abilities --------------------------------------


def _answer_board(*, bob_hand=("Opt",), bob_battlefield=("Island", "Mogg Fanatic")):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Glen Elendra's Answer", "Opt"],
            battlefield=["Island"] * 5,
            library=["Island"] * 5,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=list(bob_battlefield),
            library=["Mountain"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _faeries(scenario, username="alice"):
    return [
        c
        for c in scenario.game.battlefield
        if c.token
        and c.name == "Faerie Token"
        and scenario.game.controller_of(c).username == username
    ]


def test_answer_counters_every_opposing_spell_and_ability_and_makes_a_faerie_for_each():
    scenario = _answer_board()
    alice_opt = scenario.cast_onto_stack("Opt", auto=True, username="alice")
    scenario.pass_priority("alice")
    bob_opt = scenario.cast_onto_stack("Opt", auto=True, username="bob")
    fanatic = scenario.creature("Mogg Fanatic", "bob")
    looting = scenario.activate(
        fanatic, username="bob", sacrificing=[fanatic], targets=[scenario.player("alice")]
    )
    scenario.pass_priority("bob")
    answer = scenario.cast_onto_stack("Glen Elendra's Answer", auto=True, username="alice")

    scenario.resolve_top()

    assert answer.zone is Zone.GRAVEYARD
    assert bob_opt.zone is Zone.GRAVEYARD
    assert looting not in scenario.game.stack
    assert alice_opt.zone is Zone.STACK, "Alice's own spell is not an opponent's"
    faeries = _faeries(scenario)
    assert len(faeries) == 2
    assert all(f.power == 1 and f.toughness == 1 for f in faeries)


def test_an_uncounterable_opposing_spell_stays_and_makes_no_faerie():
    scenario = _answer_board(
        bob_hand=("Abrupt Decay",), bob_battlefield=("Swamp", "Forest", "Grizzly Bears")
    )
    scenario.pass_priority("alice")
    target = scenario.creature("Grizzly Bears", "bob")
    decay = scenario.cast_onto_stack("Abrupt Decay", auto=True, username="bob", targets=[target])
    scenario.pass_priority("bob")
    scenario.cast_onto_stack("Glen Elendra's Answer", auto=True, username="alice")

    scenario.resolve_top()

    assert decay.zone is Zone.STACK
    assert _faeries(scenario) == []


def test_answer_with_nothing_opposing_on_the_stack_makes_no_faeries():
    scenario = _answer_board(bob_hand=(), bob_battlefield=("Island",))
    scenario.cast_and_resolve("Glen Elendra's Answer", auto=True, username="alice")
    assert _faeries(scenario) == []


def test_answer_itself_cannot_be_countered():
    scenario = _answer_board(bob_hand=("Counterspell",), bob_battlefield=("Island", "Island"))
    answer = scenario.cast_onto_stack("Glen Elendra's Answer", auto=True, username="alice")
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Counterspell", auto=True, username="bob", targets=[answer])

    scenario.resolve_top()

    assert answer.zone is Zone.STACK


def test_summary_dismissal_exiles_other_spells_and_counters_every_ability():
    """The proof printing: "Exile all other spells and counter all
    abilities." - no controller scope, so Alice's own ability is countered
    too, and spells are exiled rather than countered."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Summary Dismissal"],
            battlefield=["Island"] * 4 + ["Mogg Fanatic"],
            library=["Island"] * 5,
        )
        .player("bob", hand=["Opt"], battlefield=["Island"], library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fanatic = scenario.creature("Mogg Fanatic", "alice")
    alice_looting = scenario.activate(
        fanatic, username="alice", sacrificing=[fanatic], targets=[scenario.player("bob")]
    )
    scenario.pass_priority("alice")
    bob_opt = scenario.cast_onto_stack("Opt", auto=True, username="bob")
    scenario.pass_priority("bob")
    dismissal = scenario.cast_onto_stack("Summary Dismissal", auto=True, username="alice")

    scenario.resolve_top()

    assert bob_opt.zone is Zone.EXILE
    assert alice_looting not in scenario.game.stack
    assert dismissal.zone is Zone.GRAVEYARD, '"other" spells - not itself'
    assert scenario.game.stack == []
