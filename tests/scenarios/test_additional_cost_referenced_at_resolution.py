"""Scenario: a resolving spell's own text pointing back at *which* card paid
its additional cost (CR 118.8a) - Fling's "deals damage equal to the
sacrificed creature's power" and Swallow Whole's "Put a +1/+1 counter on the
creature tapped to pay this spell's additional cost."

Neither of these is a target (CR 115.1): the card paying the additional cost
is chosen and moved (or tapped) on the way to the stack, before the spell is
even announced as having targets, let alone before it resolves. Reading it
back at resolution needed a new primitive - `CastRecord.additional_cost_cards`
(`models/game.py`), a list of every card id consumed paying one of
`Casting.additional_costs`' components, filled in by `Casting.cast` (CR
601.2h: the cost is paid, then the spell is put on the stack) and read by
`Game.cast_record(spell).additional_cost_cards` at resolution -
`Game.find_by_id` still finds the card wherever paying the cost left it (the
graveyard for a sacrifice, still on the battlefield tapped for a tap cost).

Neither `Fling` nor `Swallow Whole` gets any help wiring the additional cost
itself onto the casting - `Casting.add_additional_cost` is a general CR 118.8a
hook (already used by kicker and escalate), not something that reads "As an
additional cost to cast this spell, ..." automatically, so these tests build
the cost component directly the way a UI layer would and hand it in, exactly
as `test_kicker.py`'s own `pay_kicker` calls do for kicker's cost.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 118.8a** - "An additional cost is a cost listed in a spell's rules
  text ... that its controller must pay."
- **CR 701.21a** - "To sacrifice a permanent, its controller moves it from
  the battlefield directly to its owner's graveyard."
- **CR 107.5** - the tap symbol; a permanent already tapped cannot pay a tap
  cost, and paying one does not target it.
- **CR 601.2h** - the total cost, additional costs included, is paid before
  the spell is put on the stack (CR 601.2i).
- **CR 119.3** - "If a source would deal damage to a permanent, that
  permanent's controller loses that much life" / damage to a player reduces
  their life total.
- **CR 122.1a** - a +1/+1 counter adds one to power and toughness.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_fling_deals_damage_equal_to_the_sacrificed_creatures_power():
    """Grizzly Bears is a 2/2, so Fling deals 2 - not 0, not a guessed value -
    and the Bears end up in the graveyard, sacrificed rather than destroyed
    (CR 701.21a: straight to the graveyard, no state-based action involved).
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Fling"], battlefield=["Grizzly Bears", "Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    bears = scenario.creature("Grizzly Bears", "alice")

    casting = scenario.cast("Fling", sacrificing=[bears])
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert bob.life == 18


def test_swallow_whole_exiles_a_tapped_creature_and_counters_the_tapper():
    """Bob's Grizzly Bears is already tapped (a legal target); alice's own
    Llanowar Elves pays the additional cost and is the one that grows, not
    the exiled creature.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Swallow Whole"], battlefield=["Llanowar Elves", "Plains"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elves = scenario.creature("Llanowar Elves", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.tap()

    casting = scenario.cast("Swallow Whole", tapping=[elves])
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.EXILE
    assert elves.tapped
    assert elves.counters[Counter.PLUS_ONE] == 1
    assert elves.power == 2, "1/1 base plus the +1/+1 counter"
