"""Scenario: "If you would put one or more counters on a permanent you control,
put that many plus one of each of those kinds of counters on that permanent
instead." - Doc Samson, Super Psychiatrist.

The active-voice twin of Winding Constrictor's passive "that many plus one of
each of those kinds of counters are put on that permanent instead": the same
`CounterAmountReplacement` (`machines/replacement.py`), with `you_put` - the
event's own putter (CR 122.6a) has to be the replacement's controller. The
active voice with "of each of those kinds" is printed only on Doc Samson, so
Winding Constrictor and Hardened Scales (neither a listed card, neither in a
deck) prove the replacement it widens, and the CR 616.1 ordering against
Doubling Season is played both ways.

Doc Samson's second ability, "{T}: Add X mana of any one color, where X is Doc
Samson's power.", is the name-possessive of Woodland Weavemaster's "this
creature's power" (CR 201.5: a card naming itself means that object); Helga,
Skittish Seer (BLB, not listed, not in a deck) prints the identical shape
with a spend restriction.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 122.6** / **CR 122.6a** - counters put on an object, and who puts them.
- **CR 614.1a** - "Effects that use the word 'instead' are replacement
  effects."
- **CR 616.1** - the affected object's controller chooses the order of
  several replacement effects; **CR 616.1e** - any of them may be chosen;
  **CR 616.1f** - the process repeats until none is left to apply.
- **CR 201.5** - a card's own name in its text means that object.
- **CR 605.1a** / **CR 605.3b** - a mana ability, which resolves immediately.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.card import Color
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

SAMSON = "Doc Samson, Super Psychiatrist"


def _board(*alice: str, bob: tuple[str, ...] = ("Grizzly Bears",)) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=list(alice), hand=["Kalonian Hydra"])
        .player("bob", battlefield=list(bob))
    )


def test_one_counter_becomes_two():
    scenario = _board(SAMSON, "Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1, putter="alice")

    assert bears.counter_count(Counter.PLUS_ONE) == 2


def test_any_kind_on_any_permanent_you_control():
    """ "one or more counters on a permanent you control" - a charge counter on
    an artifact is one too, and gets one more of its own kind."""
    scenario = _board(SAMSON, "Geistflame Reservoir").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    reservoir = next(p for p in scenario.game.battlefield if p.name == "Geistflame Reservoir")

    scenario.game.add_counters(reservoir, Counter.CHARGE, 2, putter="alice")

    assert reservoir.counter_count(Counter.CHARGE) == 3


def test_doc_samson_counts_himself():
    scenario = _board(SAMSON).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    samson = scenario.creature(SAMSON, "alice")

    scenario.game.add_counters(samson, Counter.PLUS_ONE, 1, putter="alice")

    assert samson.counter_count(Counter.PLUS_ONE) == 2


def test_a_permanent_you_do_not_control_gets_no_extra():
    scenario = _board(SAMSON).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.creature("Grizzly Bears", "bob")

    scenario.game.add_counters(theirs, Counter.PLUS_ONE, 1, putter="alice")

    assert theirs.counter_count(Counter.PLUS_ONE) == 1


def test_counters_an_opponent_puts_get_no_extra():
    """ "If *you* would put" - bob putting a -1/-1 counter on alice's Bears is
    not alice putting it (CR 122.6a)."""
    scenario = _board(SAMSON, "Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(bears, Counter.MINUS_ONE, 1, putter="bob")

    assert bears.counter_count(Counter.MINUS_ONE) == 1


def test_a_player_getting_counters_is_not_a_permanent():
    scenario = _board(SAMSON).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.add_player_counters("alice", Counter.ENERGY, 2)

    assert scenario.player("alice").counter_count(Counter.ENERGY) == 2


def test_a_permanent_entering_with_counters_gets_one_more():
    """CR 122.6: a permanent given counters as it enters has them put on it -
    Kalonian Hydra's four become five."""
    scenario = _board(SAMSON).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    hydra = scenario.put_onto_battlefield("Kalonian Hydra", "alice")

    assert hydra.counter_count(Counter.PLUS_ONE) == 5


def test_with_hardened_scales_either_order_is_three():
    """CR 616.1: both add one, so the order the controller picks does not
    matter - one counter becomes three."""
    scenario = _board(SAMSON, "Hardened Scales", "Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1, putter="alice")

    assert bears.counter_count(Counter.PLUS_ONE) == 3


def test_with_doubling_season_samson_first_is_four():
    """CR 616.1e: alice applies Doc Samson first (1 + 1), then Doubling
    Season doubles the two (CR 616.1f)."""
    scenario = _board(SAMSON, "Doubling Season", "Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_mode(_option_naming(scenario, bears, SAMSON))

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1, putter="alice")

    assert bears.counter_count(Counter.PLUS_ONE) == 4


def test_with_doubling_season_doubling_first_is_three():
    scenario = _board(SAMSON, "Doubling Season", "Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_mode(_option_naming(scenario, bears, "Doubling Season"))

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1, putter="alice")

    assert bears.counter_count(Counter.PLUS_ONE) == 3


def _option_naming(scenario, permanent, name: str) -> str:
    """The CR 616.1 option label `choose_effect` gives the effect from `name`,
    read off the real applicable effects rather than guessed."""
    from magic_cards_model.machines.replacement import (
        EventKind,
        ReplaceableEvent,
        _effect_options,
        applicable_effects,
        order_effects,
    )

    event = ReplaceableEvent(
        kind=EventKind.ADD_COUNTERS,
        card=permanent,
        counter_kind=str(Counter.PLUS_ONE),
        amount=1,
        putter="alice",
    )
    tier = order_effects(scenario.game, event, applicable_effects(scenario.game, event))
    options = _effect_options(tier)
    return next(
        option for option, effect in zip(options, tier, strict=True) if effect.name.startswith(name)
    )


def test_winding_constrictor_the_passive_twin_stacks_with_samson():
    """Winding Constrictor: "... that many plus one of each of those kinds of
    counters are put on that permanent instead." - both apply once (CR
    616.1f): 1 + 1 + 1."""
    scenario = _board(SAMSON, "Winding Constrictor", "Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1, putter="alice")

    assert bears.counter_count(Counter.PLUS_ONE) == 3


# -- "{T}: Add X mana of any one color, where X is <Name>'s power." -----------


def test_doc_samson_taps_for_mana_equal_to_his_power():
    scenario = _board(SAMSON).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (samson,) = scenario.untapped_sources(SAMSON)

    scenario.activate(samson, color=Color.GREEN)

    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 3}
    assert scenario.stack_names() == [], "CR 605.3b: a mana ability never uses the stack"


def test_doc_samson_mana_follows_his_computed_power():
    """A +1/+1 counter put on him becomes two (his own replacement), so a 3/6
    taps for five."""
    scenario = _board(SAMSON).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (samson,) = scenario.untapped_sources(SAMSON)
    scenario.game.add_counters(samson, Counter.PLUS_ONE, 1, putter="alice")

    scenario.activate(samson, color=Color.BLUE)

    assert scenario.player("alice").mana_pool.floating == {Color.BLUE: 5}


def test_helga_taps_for_mana_equal_to_her_power():
    """Helga, Skittish Seer: "{T}: Add X mana of any one color, where X is
    Helga's power. Spend this mana only to cast creature spells with mana
    value 4 or greater or creature spells with {X} in their mana costs." -
    the short name of a legendary (CR 201.5c)."""
    scenario = Scenario().player("alice", battlefield=["Helga, Skittish Seer"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (helga,) = scenario.untapped_sources("Helga, Skittish Seer")
    helga.add_counters(Counter.PLUS_ONE, 2)

    scenario.activate(helga, color=Color.WHITE)

    assert sum(scenario.player("alice").mana_pool.floating.values()) == 3
