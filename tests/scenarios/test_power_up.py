"""Scenario: Power-up (CR 702.193), a keyword-modified activated ability.

Every rule below was read whole with `mise run rules:find` in the session
that wrote this file:

- **CR 702.193a** - "Power-up is a keyword that adds additional rules to the
  activated ability that follows it. 'Power-up — [Cost]: [Effect]' means
  '[Cost]: [Effect]. If this permanent entered this turn, this ability's
  cost is reduced by this permanent's mana cost. Activate this ability only
  once.'"
- **CR 702.193b** - "Generic mana in the permanent's mana cost reduces
  generic mana in the cost to activate its power-up ability. Colored and
  colorless mana in the permanent's mana cost reduces mana of the same type,
  and any excess reduces that much generic mana. (See rule 118.7.)"

Unlike outlast, a power-up line already parses as an ordinary printed
`ActivatedAbility` (CR 602.1's "[Cost]: [Effect]" shape, "Power-up" read as
the same em-dash prefix Exhaust's own line is) and its effect clause
("Put N +1/+1 counters on this creature.") already resolves through the
generic activated-ability path - proven by the sweep's own `--card` output
reading it `handled` before this file existed. What was missing is CR
702.193a's own "Activate this ability only once" (reusing exhaust's own
`Game.exhausted` bookkeeping, CR 702.177a) and CR 702.193b's cost
reduction - both are what this file proves.

Brave Brawler (Power-up {4}{W}, mana cost {1}{W}) and Pet Avengers (Power-up
{6}{G}, mana cost {3}{G}) are both Modern/Pioneer/Standard-legal and are
proven against their *own* mana costs, not against each other's or Aerial
Doombot's. Aerial Doombot (Power-up {5}{U}, mana cost {U}) is the reported
card and gets the full proof suite: reduced cost on the turn it enters, full
cost on a later turn, a second activation refused, and a new object (leaving
and returning) free to activate again.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.mana import ManaCost
from tests.scenarios.harness import PlayedScenario, Scenario


def cast_this_turn(name: str, extra_lands: list[str]) -> PlayedScenario:
    """`name` cast from hand this turn, with `extra_lands` left untapped for
    its power-up activation afterwards."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[name],
            battlefield=["Plains", "Island", "Mountain", "Forest", "Swamp"] + extra_lands,
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def already_on_the_battlefield(name: str, *extra: str) -> PlayedScenario:
    """`name` placed directly on the battlefield - never entered this turn
    (the same shape `test_entered_this_turn_targeting.py` relies on)."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[name, *extra])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# --------------------------------------------------------------------------
# CR 702.193b: the cost reduction, on the turn the permanent entered
# --------------------------------------------------------------------------


def test_brave_brawler_power_up_costs_generic_when_it_entered_this_turn():
    """Brave Brawler: Power-up {4}{W}, mana cost {1}{W}. {4}{W} - {1}{W}
    leaves {3} generic (CR 702.193b: colored reduces colored, generic
    reduces generic)."""
    scenario = cast_this_turn("Brave Brawler", ["Plains"])
    cast_sources = scenario.untapped_sources("Plains", "Plains")
    brawler = scenario.cast_and_resolve("Brave Brawler", *cast_sources)

    assert brawler.turn_entered == scenario.turn.turn_number
    cost = scenario.game.activation_cost(brawler)
    assert cost.mana == ManaCost.parse("{3}")


def test_pet_avengers_power_up_costs_generic_when_it_entered_this_turn():
    """Pet Avengers: Power-up {6}{G}, mana cost {3}{G}. {6}{G} - {3}{G}
    leaves {3} generic - proven against Pet Avengers' own mana cost, not
    Brave Brawler's."""
    scenario = cast_this_turn("Pet Avengers", ["Forest", "Forest"])
    cast_sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Plains")
    avengers = scenario.cast_and_resolve("Pet Avengers", *cast_sources)

    assert avengers.turn_entered == scenario.turn.turn_number
    cost = scenario.game.activation_cost(avengers)
    assert cost.mana == ManaCost.parse("{3}")


def test_aerial_doombot_power_up_costs_generic_when_it_entered_this_turn():
    """Aerial Doombot (reported): Power-up {5}{U}, mana cost {U}. The
    colored reduction removes the whole {U} component with nothing left to
    spill into generic (CR 118.7c is a no-op here since the reduction is
    exactly one {U}), leaving {5}."""
    scenario = cast_this_turn("Aerial Doombot", [])
    (island,) = scenario.untapped_sources("Island")
    doombot = scenario.cast_and_resolve("Aerial Doombot", island)

    assert doombot.turn_entered == scenario.turn.turn_number
    cost = scenario.game.activation_cost(doombot)
    assert cost.mana == ManaCost.parse("{5}")


# --------------------------------------------------------------------------
# CR 702.193a: full cost on a later turn
# --------------------------------------------------------------------------


def test_aerial_doombot_power_up_costs_full_on_a_later_turn():
    scenario = already_on_the_battlefield("Aerial Doombot")
    doombot = scenario.creature("Aerial Doombot")

    assert doombot.turn_entered != scenario.turn.turn_number
    cost = scenario.game.activation_cost(doombot)
    assert cost.mana == ManaCost.parse("{5}{U}")


def test_brave_brawler_power_up_costs_full_on_a_later_turn():
    scenario = already_on_the_battlefield("Brave Brawler")
    brawler = scenario.creature("Brave Brawler")

    assert brawler.turn_entered != scenario.turn.turn_number
    cost = scenario.game.activation_cost(brawler)
    assert cost.mana == ManaCost.parse("{4}{W}")


# --------------------------------------------------------------------------
# CR 702.193a: puts the counters, and only once
# --------------------------------------------------------------------------


def test_aerial_doombot_power_up_puts_the_counters():
    scenario = already_on_the_battlefield(
        "Aerial Doombot", "Island", "Island", "Island", "Island", "Island", "Island"
    )
    doombot = scenario.creature("Aerial Doombot")
    sources = scenario.untapped_sources("Island", "Island", "Island", "Island", "Island", "Island")
    assert doombot.tapped is False

    scenario.activate(doombot, *sources)
    scenario.pass_until_resolved()

    assert doombot.counters[Counter.PLUS_ONE] == 3


def test_aerial_doombot_power_up_second_activation_is_refused():
    scenario = already_on_the_battlefield(
        "Aerial Doombot", "Island", "Island", "Island", "Island", "Island", "Island"
    )
    doombot = scenario.creature("Aerial Doombot")
    sources = scenario.untapped_sources("Island", "Island", "Island", "Island", "Island", "Island")

    scenario.activate(doombot, *sources)
    scenario.pass_until_resolved()

    reason = scenario.why_cannot_activate(doombot)
    assert reason is not None and "already been activated" in reason


def test_brave_brawler_power_up_second_activation_is_refused():
    scenario = already_on_the_battlefield(
        "Brave Brawler", "Plains", "Plains", "Plains", "Plains", "Plains"
    )
    brawler = scenario.creature("Brave Brawler")
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains", "Plains")

    scenario.activate(brawler, *sources)
    scenario.pass_until_resolved()

    reason = scenario.why_cannot_activate(brawler)
    assert reason is not None and "already been activated" in reason


def test_a_new_aerial_doombot_object_may_activate_again():
    """CR 400.7: the permanent that leaves and returns is a new object.
    `CardState.id` is stable across an ordinary zone change ("same id, new
    object"), so `Game._activation_key` folds in `zone_change_stamp` too -
    bouncing and recasting Aerial Doombot mints a fresh stamp, which clears
    its power-up activation the same way a fresh id would, unlike a per-turn
    limit that a new turn would clear instead."""
    scenario = already_on_the_battlefield("Aerial Doombot", *["Island"] * 12)
    first = scenario.creature("Aerial Doombot")
    first_sources = scenario.untapped_sources(
        "Island", "Island", "Island", "Island", "Island", "Island"
    )
    scenario.activate(first, *first_sources)
    scenario.pass_until_resolved()
    assert scenario.why_cannot_activate(first) is not None
    original_stamp = first.zone_change_stamp  # captured now: `first` is mutated in place below

    scenario.game.return_to_hand(first)
    assert first.zone is Zone.HAND

    cast_sources = scenario.untapped_sources("Island")
    second = scenario.cast_and_resolve("Aerial Doombot", *cast_sources)
    # CR 400.7: "same id, new object" (`CardState`'s own module docstring) -
    # `id` is stable across an ordinary zone change (this engine reuses the
    # one `CardState` object for a card's whole existence, mutating it in
    # place - `second` and `first` are the same object here), and
    # `zone_change_stamp` is the field that actually marks this as a new
    # incarnation.
    assert second is first
    assert second.zone_change_stamp != original_stamp, "CR 400.7: a new object"

    assert scenario.why_cannot_activate(second) is None
    second_sources = scenario.untapped_sources("Island", "Island", "Island", "Island", "Island")
    scenario.activate(second, *second_sources)
    scenario.pass_until_resolved()
    assert second.counters[Counter.PLUS_ONE] == 3


# --------------------------------------------------------------------------
# CR 702.193a's "only once" bookkeeping dumps the same way every time
# --------------------------------------------------------------------------


def test_power_up_bookkeeping_dumps_in_one_canonical_order():
    """`Game.exhausted` is a set of `id:stamp:index` strings, and a set of
    strings iterates in hash order - randomised per process by
    `PYTHONHASHSEED`. Dumped as a bare set, the same game could list its
    power-up activations in a different order after a decode and re-dump,
    which is what made `test_a_new_aerial_doombot_object_may_activate_again`
    (two entries) fail the round-trip invariant in roughly one process in
    fourteen. Six activated Doombots make an accidentally sorted order a
    1-in-720 event, so this is red for any hash-ordered dump."""
    doombots = ["Aerial Doombot"] * 6
    scenario = already_on_the_battlefield(*doombots, *["Island"] * 36)
    for doombot in [c for c in scenario.game.battlefield if c.name == "Aerial Doombot"]:
        sources = scenario.untapped_sources(*["Island"] * 6)
        scenario.activate(doombot, *sources)
        scenario.pass_until_resolved()
        assert scenario.why_cannot_activate(doombot) is not None

    dumped = scenario.game.model_dump(mode="json")["exhausted"]
    assert len(dumped) == 6
    assert dumped == sorted(dumped)
