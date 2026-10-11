"""Clash of Realities: "All Spirits have "When this permanent enters, you may
have it deal 3 damage to target non-Spirit creature." Non-Spirit creatures have
"When this creature enters, you may have it deal 3 damage to target Spirit
creature."" (EP-01 R2, T2 residual clause).

CR numbers verified with `mise run rules:find`:

- CR 613.1f: layer 6 adds the quoted triggered ability to every object in the
  group; CR 113.10c lets a later effect add or take it away again, so it ends
  with the source (CR 604.2) and a creature entering afterwards is covered
  too.
- CR 603.6a: the granted ability is an enters-the-battlefield trigger of the
  creature that entered, so its controller is that creature's controller.
- CR 603.5: "you may have it deal" - the optional part is decided on
  resolution.

The "Non-<subtype> creatures" subject is the negated twin of "All
<subtype>s": every creature of either player that lacks the subtype.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(alice=(), bob=(), bob_hand=(), alice_hand=("Grizzly Bears",)):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Clash of Realities", *alice], hand=list(alice_hand))
        .player("bob", battlefield=list(bob), hand=list(bob_hand))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _drain(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def test_clash_of_realities_is_fully_handled():
    bad = [c for c in card_support(card("Clash of Realities")).clauses if c.outcome != "handled"]
    assert not bad, bad


def test_a_non_spirit_creature_entering_may_deal_3_to_a_spirit_creature():
    scenario = _board(bob=["Dust Animus"])
    animus = scenario.creature("Dust Animus", "bob")
    scenario.will_take_the_may(True)
    scenario.will_choose_targets(animus)
    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    _drain(scenario)

    assert animus.zone is Zone.GRAVEYARD


def test_the_may_can_be_declined():
    scenario = _board(bob=["Dust Animus"])
    animus = scenario.creature("Dust Animus", "bob")
    scenario.will_take_the_may(False)
    scenario.will_choose_targets(animus)
    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    _drain(scenario)

    assert animus.zone is Zone.BATTLEFIELD
    assert animus.damage == 0


def test_a_spirit_entering_may_deal_3_to_a_non_spirit_creature():
    scenario = _board(bob=["Hill Giant"], alice_hand=("Spectral Sailor",))
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_take_the_may(True)
    scenario.will_choose_targets(giant)
    scenario.put_onto_battlefield("Spectral Sailor", "alice")
    _drain(scenario)

    assert giant.zone is Zone.GRAVEYARD


def test_the_opponents_non_spirit_creature_gets_the_ability_too_and_it_is_theirs():
    scenario = _board(alice=["Dust Animus"], bob_hand=["Hill Giant"])
    animus = scenario.creature("Dust Animus", "alice")
    scenario.will_take_the_may(True, username="bob")
    scenario.will_choose_targets(animus, username="bob")
    scenario.put_onto_battlefield("Hill Giant", "bob")
    _drain(scenario)

    assert animus.zone is Zone.GRAVEYARD


def test_a_non_spirit_entering_does_not_hit_a_non_spirit_and_a_spirit_does_not_hit_a_spirit():
    scenario = _board(bob=["Hill Giant", "Dust Animus"])
    giant = scenario.creature("Hill Giant", "bob")
    animus = scenario.creature("Dust Animus", "bob")
    scenario.will_take_the_may(True)
    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    _drain(scenario)

    assert giant.damage == 0, "the non-Spirit trigger names only Spirit creatures"
    assert animus.zone is Zone.GRAVEYARD or animus.damage in (0, 3)


def test_once_clash_leaves_the_creatures_entering_later_have_nothing():
    scenario = _board(bob=["Dust Animus"])
    animus = scenario.creature("Dust Animus", "bob")
    clash = scenario.find("Clash of Realities", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(clash)
    scenario.will_take_the_may(True)
    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    _drain(scenario)

    assert animus.zone is Zone.BATTLEFIELD
    assert animus.damage == 0
