"""Rebound (CR 702.88): exile instead of the graveyard, then an optional recast.

Ephemerate's second line (verified with `resolve_cards`, 2026-06-26 printing,
Marvel Universe): "Rebound (If you cast this spell from your hand, exile it as
it resolves. At the beginning of your next upkeep, you may cast this card from
exile without paying its mana cost.)" - Ephemerate's own blink is
`test_ephemerate.py`'s mechanic; this file is Rebound alone.

Before this fix, `grep -rn "rebound" src/magic_cards_model/` returned zero
hits: the keyword did not exist anywhere in the engine, so a resolved
Ephemerate went straight to the graveyard like any other instant and nothing
ever offered the next-upkeep recast.

Every rule cited here was looked up with `knowledge_search(type="rules")` in
this session:

- **CR 702.88a** - "Rebound appears on some instants and sorceries. It
  represents a static ability that functions while the spell is on the stack
  and may create a delayed triggered ability. 'Rebound' means 'If this spell
  was cast from your hand, instead of putting it into your graveyard as it
  resolves, exile it and, at the beginning of your next upkeep, you may cast
  this card from exile without paying its mana cost.'"
- **CR 702.88b** - "Casting a spell as an effect of its rebound ability
  follows the rules for paying alternative costs in rules 601.2b and
  601.2f-h."
- **CR 603.7c** - a delayed triggered ability that finds its object has left
  the zone it expected (or is a new incarnation of it, by `zone_change_stamp`)
  does not affect it.

The replacement hangs off the same hook flashback and Adventure already use
(`Game.put_into_graveyard`'s own `ReplaceableEvent(kind=ZONE_CHANGE,
destination=GRAVEYARD)`, applied in `machines/replacement._stack_replacements`)
and reads `Game.cast_records[spell.id]` *before* `resolve_top` pops it - a
card cast from anywhere but hand (the graveyard, or a previous rebound's own
exile) never triggers it a second time, which is what CR 702.88a's own "if
this spell was cast from your hand" is guarding against: an unconditional
exile-on-resolve would let a recast Ephemerate rebound forever.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("erin", hand=["Ephemerate"], battlefield=["White Orchid Phantom", "Plains"])
        .player("bob", battlefield=["Grizzly Bears"])
    )


def run_to_erins_next_upkeep(scenario) -> None:
    """Walk the turn forward - through the rest of erin's turn and all of
    bob's - until erin's own next upkeep begins, resolving whatever is on the
    stack as it goes (CR 603.3's "the next time a player would receive
    priority"). `advance` is what actually emits CR 500.6's "a step began"
    event; jumping with `start_at` fires nothing.
    """
    turns = scenario.turn.turns_taken
    while not (
        scenario.turn.turns_taken > turns
        and scenario.step is Step.UPKEEP
        and scenario.game.active_player.username == "erin"
    ):
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
        scenario.advance()
    # `advance` has already put whatever triggered at the beginning of this
    # step on the stack (CR 603.3), including rebound's own delayed trigger -
    # left there, unresolved, so a test can assert on it before choosing to
    # resolve it.


def test_a_resolved_ephemerate_is_exiled_not_binned():
    """CR 702.88a's own first half: cast from hand, it goes to exile as it
    resolves rather than to erin's graveyard."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phantom = scenario.creature("White Orchid Phantom")
    (plains,) = scenario.untapped_sources("Plains")

    ephemerate = scenario.cast_and_resolve("Ephemerate", plains, targets=[phantom])

    assert ephemerate.zone is Zone.EXILE
    assert ephemerate not in scenario.player("erin").graveyard


def test_rebound_offers_the_recast_at_erins_next_upkeep():
    """CR 702.88a's delayed trigger: it fires once, at the beginning of
    erin's *next* upkeep (not bob's, in between), and the "you may" default
    (`Game.may`'s own CR 608.2d default is to take an offered "may") actually
    puts the card back on the stack."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phantom = scenario.creature("White Orchid Phantom")
    (plains,) = scenario.untapped_sources("Plains")
    ephemerate = scenario.cast_and_resolve("Ephemerate", plains, targets=[phantom])
    assert ephemerate.zone is Zone.EXILE

    # The card needs a fresh target for its own recast (CR 601.2c); script it
    # onto the stack the same way `test_delayed_triggered_abilities.py`
    # scripts a `CHOOSE_TARGETS` answer for a triggered ability.
    scenario.game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.CHOOSE_TARGETS,
            value=(phantom.id,),
            player="erin",
            source=None,
            uses=1,
        )
    )

    run_to_erins_next_upkeep(scenario)
    scenario.resolve_top()  # the delayed trigger itself: "you may cast ..."

    assert ephemerate.zone is Zone.STACK
    assert scenario.game.controller_of(ephemerate).username == "erin"


def test_rebound_recast_is_not_cast_from_hand_and_does_not_rebound_again():
    """CR 702.88a's own "if this spell was cast from your hand" - the recast
    itself was cast from exile, so it goes to the graveyard normally once it
    resolves rather than exiling itself over and over."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phantom = scenario.creature("White Orchid Phantom")
    (plains,) = scenario.untapped_sources("Plains")
    ephemerate = scenario.cast_and_resolve("Ephemerate", plains, targets=[phantom])

    scenario.game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.CHOOSE_TARGETS,
            value=(phantom.id,),
            player="erin",
            source=None,
            uses=1,
        )
    )
    run_to_erins_next_upkeep(scenario)
    scenario.resolve_top()  # the delayed trigger itself
    assert ephemerate.zone is Zone.STACK

    scenario.resolve_top()  # the recast Ephemerate

    assert ephemerate.zone is Zone.GRAVEYARD


def test_declining_the_may_leaves_the_card_in_exile():
    """CR 608.2d: refusing an offered "may" is always legal, and CR 603.7b's
    one-shot trigger has already spent itself either way - a declined
    Ephemerate simply stays in exile forever."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phantom = scenario.creature("White Orchid Phantom")
    (plains,) = scenario.untapped_sources("Plains")
    ephemerate = scenario.cast_and_resolve("Ephemerate", plains, targets=[phantom])

    scenario.will_take_the_may(False, username="erin")

    run_to_erins_next_upkeep(scenario)
    scenario.resolve_top()  # the delayed trigger itself: declines the "may"

    assert ephemerate.zone is Zone.EXILE


def test_a_countered_ephemerate_is_not_exiled_by_rebound():
    """CR 702.88a reads "instead of putting it into your graveyard **as it
    resolves**" - a countered spell never resolves at all (CR 701.6), so it
    goes to the graveyard the ordinary way and rebound never applies."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phantom = scenario.creature("White Orchid Phantom")
    (plains,) = scenario.untapped_sources("Plains")
    ephemerate = scenario.cast_onto_stack("Ephemerate", plains, targets=[phantom])

    scenario.game.counter(ephemerate)

    assert ephemerate.zone is Zone.GRAVEYARD


def test_a_fizzled_ephemerate_is_not_exiled_by_rebound():
    """CR 608.2b: every target illegal by the time Ephemerate would resolve
    means it "doesn't resolve" at all - also not "as it resolves" (CR
    702.88a), so rebound does not apply here either."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phantom = scenario.creature("White Orchid Phantom")
    (plains,) = scenario.untapped_sources("Plains")
    ephemerate = scenario.cast_onto_stack("Ephemerate", plains, targets=[phantom])
    scenario.game.exile_permanent(phantom)  # the only target is now illegal

    scenario.resolve_top()

    assert ephemerate.zone is Zone.GRAVEYARD
