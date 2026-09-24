"""Scenario: removing counters - as a variable cost, and as "if you do".

Two templates, both about taking counters off:

- **"Remove any number of `<kind>` counters from `<this>`"** as an activation
  cost, and the "that many"/"that much" its effect counts back to (CR 107.3a:
  the number is announced as the ability is activated, CR 602.2b):
  - The Astonishing Ant-Man: "{2}{G}, {T}, Remove any number of +1/+1
    counters from The Astonishing Ant-Man: Create that many 1/1 green Insect
    creature tokens."
  - Geistflame Reservoir (MID, not listed, not in a deck): "{1}{R}, {T},
    Remove any number of charge counters from this artifact: It deals that
    much damage to any target."
- **"[You may] remove a counter from a `<description>` you control. If you
  do, `<effect>`."** (CR 118.12: the removal is a cost paid on resolution):
  - Mister Hyde, Monster Within's upkeep mode "Remove a counter from a
    creature you control. If you do, draw a card."
  - Sanctuary Warden (SNC, not listed, not in a deck): "Whenever this creature
    enters or attacks, you may remove a counter from a creature or
    planeswalker you control. If you do, draw a card and create a 1/1 green
    and white Citizen creature token."

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 107.3a** - an X (here, "any number") in an activation cost is chosen
  and announced as the ability is activated.
- **CR 118.3** - a cost can't be paid without the resources to pay it fully.
- **CR 118.12** - "[Do something]. If [a player] [does] ..." - the action is a
  cost paid on resolution, and "if you do" asks whether it was paid.
- **CR 602.2b** - activating follows CR 601.2b-i.
- **CR 603.3c** / **CR 700.2b** - a modal trigger's mode is chosen as it goes
  on the stack.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

ANT_MAN = "The Astonishing Ant-Man"


def _ant_man_board(counters: int) -> tuple:
    scenario = (
        Scenario()
        .player("alice", battlefield=[ANT_MAN, "Forest", "Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ant_man = scenario.creature(ANT_MAN, "alice")
    ant_man.summoning_sick = False
    ant_man.add_counters(Counter.PLUS_ONE, counters)
    return scenario, ant_man


def _insects(scenario) -> int:
    return sum(1 for p in scenario.game.battlefield if p.name == "Insect Token")


def test_ant_man_turns_the_counters_removed_into_insects():
    scenario, ant_man = _ant_man_board(3)
    forests = scenario.untapped_sources("Forest", "Forest", "Forest")

    scenario.activate(ant_man, *forests, x_value=2)
    assert ant_man.counter_count(Counter.PLUS_ONE) == 1, "CR 602.2b: paid as it is activated"
    scenario.resolve_top()

    assert _insects(scenario) == 2
    assert ant_man.tapped


def test_removing_every_counter_makes_that_many():
    scenario, ant_man = _ant_man_board(3)
    forests = scenario.untapped_sources("Forest", "Forest", "Forest")

    scenario.activate(ant_man, *forests, x_value=3)
    scenario.resolve_top()

    assert _insects(scenario) == 3
    assert ant_man.counter_count(Counter.PLUS_ONE) == 0


def test_removing_none_makes_none():
    """ "Any number" includes zero (CR 107.3a lets the X be 0)."""
    scenario, ant_man = _ant_man_board(2)
    forests = scenario.untapped_sources("Forest", "Forest", "Forest")

    scenario.activate(ant_man, *forests, x_value=0)
    scenario.resolve_top()

    assert _insects(scenario) == 0
    assert ant_man.counter_count(Counter.PLUS_ONE) == 2


def test_more_counters_than_it_has_cannot_be_removed():
    """CR 118.3: three counters can't be removed from a creature with two."""
    scenario, ant_man = _ant_man_board(2)
    forests = scenario.untapped_sources("Forest", "Forest", "Forest")

    try:
        scenario.activate(ant_man, *forests, x_value=3)
    except ValueError:
        pass
    else:
        raise AssertionError("an unpayable removal was accepted")
    assert ant_man.counter_count(Counter.PLUS_ONE) == 2
    assert _insects(scenario) == 0


def test_ant_man_grows_when_you_draw():
    """His other ability, the source of the counters: "Whenever you draw a
    card, put a +1/+1 counter on The Astonishing Ant-Man." """
    scenario = (
        Scenario()
        .player("alice", battlefield=[ANT_MAN], library=["Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ant_man = scenario.creature(ANT_MAN, "alice")

    scenario.draw(1, "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert ant_man.counter_count(Counter.PLUS_ONE) == 1


def test_geistflame_reservoir_deals_that_much_damage():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Geistflame Reservoir", "Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    reservoir = next(p for p in scenario.game.battlefield if p.name == "Geistflame Reservoir")
    reservoir.add_counters(Counter.CHARGE, 3)
    mountains = scenario.untapped_sources("Mountain", "Mountain")

    scenario.activate(reservoir, *mountains, x_value=2, targets=[scenario.player("bob")])
    scenario.resolve_top()

    assert scenario.player("bob").life == 18
    assert reservoir.counter_count(Counter.CHARGE) == 1


# -- "Remove a counter from a <description> you control. If you do, ..." ------

HYDE = "Mister Hyde, Monster Within"
GROW = "Put a +1/+1 counter on Mister Hyde."
TRADE = "Remove a counter from a creature you control. If you do, draw a card."


def _hyde_board(*others: str, bob: tuple[str, ...] = ()) -> tuple:
    scenario = (
        Scenario()
        .player("alice", battlefield=[HYDE, *others], library=["Forest"] * 5)
        .player("bob", battlefield=list(bob), library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.UNTAP)
    return scenario, scenario.creature(HYDE, "alice")


def _to_upkeep_and_resolve(scenario) -> None:
    scenario.advance()
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


def test_hyde_grows_in_the_first_mode():
    scenario, hyde = _hyde_board()
    scenario.will_choose_mode(GROW, username="alice")

    _to_upkeep_and_resolve(scenario)

    assert hyde.counter_count(Counter.PLUS_ONE) == 1


def test_hyde_trades_a_counter_for_a_card():
    scenario, hyde = _hyde_board("Grizzly Bears")
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 2)
    hand = len(scenario.player("alice").hand)
    scenario.will_choose_mode(TRADE, username="alice")
    scenario.will_choose_cards(bears, username="alice")

    _to_upkeep_and_resolve(scenario)

    assert bears.counter_count(Counter.PLUS_ONE) == 1
    assert len(scenario.player("alice").hand) == hand + 1


def test_any_kind_of_counter_pays_it():
    """ "a counter" - any kind; a shield counter is one."""
    scenario, hyde = _hyde_board()
    hyde.add_counters("shield", 1)
    hand = len(scenario.player("alice").hand)
    scenario.will_choose_mode(TRADE, username="alice")
    scenario.will_choose_cards(hyde, username="alice")

    _to_upkeep_and_resolve(scenario)

    assert hyde.counter_count("shield") == 0
    assert len(scenario.player("alice").hand) == hand + 1


def test_the_kind_is_chosen_when_there_are_several():
    scenario, hyde = _hyde_board()
    hyde.add_counters("shield", 1)
    hyde.add_counters(Counter.PLUS_ONE, 1)
    scenario.will_choose_mode(TRADE, username="alice")
    scenario.will_choose_cards(hyde, username="alice")
    scenario.will_choose_mode("shield", username="alice")

    _to_upkeep_and_resolve(scenario)

    assert hyde.counter_count("shield") == 0
    assert hyde.counter_count(Counter.PLUS_ONE) == 1


def test_no_counter_to_remove_draws_nothing():
    """CR 118.12: the removal could not be paid, so "if you do" is false."""
    scenario, hyde = _hyde_board("Grizzly Bears")
    hand = len(scenario.player("alice").hand)
    scenario.will_choose_mode(TRADE, username="alice")

    _to_upkeep_and_resolve(scenario)

    assert len(scenario.player("alice").hand) == hand


def test_an_opponents_creature_is_not_yours_to_remove_from():
    scenario, hyde = _hyde_board(bob=("Grizzly Bears",))
    theirs = scenario.creature("Grizzly Bears", "bob")
    theirs.add_counters("oil", 1)
    hand = len(scenario.player("alice").hand)
    scenario.will_choose_mode(TRADE, username="alice")

    _to_upkeep_and_resolve(scenario)

    assert theirs.counter_count("oil") == 1
    assert len(scenario.player("alice").hand) == hand


def test_sanctuary_warden_may_remove_a_shield_counter_for_a_card_and_a_citizen():
    scenario = (
        Scenario()
        .player("alice", hand=["Sanctuary Warden"], library=["Forest"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hand = len(scenario.player("alice").hand)
    scenario.will_take_the_may(True, username="alice")

    warden = scenario.put_onto_battlefield("Sanctuary Warden", "alice")
    assert warden.counter_count("shield") == 2
    scenario.will_choose_cards(warden, username="alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert warden.counter_count("shield") == 1
    assert len(scenario.player("alice").hand) == hand  # the Warden left, a card came
    assert sum(1 for p in scenario.game.battlefield if p.name == "Citizen Token") == 1


def test_sanctuary_warden_declined_does_nothing():
    scenario = (
        Scenario()
        .player("alice", hand=["Sanctuary Warden"], library=["Forest"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, username="alice")

    warden = scenario.put_onto_battlefield("Sanctuary Warden", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert warden.counter_count("shield") == 2
    assert not [p for p in scenario.game.battlefield if p.name == "Citizen Token"]
    assert not [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_CARDS]
