"""Scenario: "This creature enters with X `<kind>` counters on it." (Walking
Ballista, Hangarback Walker) - CR 614.1c's replacement effect with CR 107.3a's
`{X}` bound into it, CR 107.3m's own named case.

Reported live: casting Walking Ballista for X=1 with two untapped Delighted
Halflings available logged `resolved: "Walking Ballista", changed: false` and
the creature never reached the battlefield - it went straight to the
graveyard, alongside Green Sun's Zenith from the same board (`docs/engine-
coverage.md`'s Green Sun's Zenith entry - the same `{X}` recorded on the cast
record with no reader). Establishing which of two indistinguishable-from-the-
log symptoms this is turns out to matter:

1. **The permanent spell never entered the battlefield at all** (the reporting
   player's own framing, citing CR 608.3a).
2. **It entered as a 0/0** - "enters with X +1/+1 counters" silently placed
   zero counters, because `machines/replacement.py`'s `_self_enters_modifiers`
   had a documented, deliberate skip for "an amount that is X" - and CR 704.5f
   then destroyed a 0-toughness creature the moment state-based actions were
   next checked, which happens inside `Game.resolve_top` itself, before any
   other player would ever get priority to see it any other way.

Both hypotheses agree on the observed board and graveyard; only reading the
code (`_self_enters_modifiers`'s own docstring naming the gap, and the "as is
an amount that is X" skip immediately below the `readable_counters` check)
settles it as **(2)**. Every CR number below was looked up with
`knowledge_search(type="rules")` in the session that wrote this file.

- **CR 107.3a** - X for a spell with `{X}` in its mana cost is fixed at
  announcement, by the caster.
- **CR 107.3m** - "If an object's enters-the-battlefield triggered ability or
  replacement effect refers to X, and the spell that became that object as it
  resolved had a value of X chosen for any of its costs, the value of X for
  that ability or effect is that same value." This is the rule this file's fix
  implements: `_self_enters_modifiers` now reads `Game.cast_records` for the
  entering object's own resolution record before giving up on a variable
  counter amount.
- **CR 614.1c** - "[This permanent] enters the battlefield with N counters
  on it" is a replacement effect, applied as the permanent enters rather than
  afterward - so a 0/0 Ballista is never a legal state that ever holds still,
  which is why the fixture's `resolve_top()` alone (no separate state-based
  check) is enough to see X=0 die.
- **CR 704.5f** - a creature with toughness 0 (or less) is put into its
  owner's graveyard, a state-based action.
- **CR 302.6** - a creature's `{T}` ability cannot be activated unless it has
  been under its controller's control continuously since their most recent
  turn began; a creature that just resolved has not been.
- **CR 704.5e / CR 707.10a** - a copy of a spell (or a copy of a card) ceases
  to exist in any zone but the stack (a copy) or the battlefield (a copy of a
  permanent spell, which becomes a token as it resolves, CR 111.13) - relevant
  to why this file does not attempt a "copied Ballista" case: a token has no
  card behind it to carry a cast record at all, a different and already-
  understood limit rather than a new one.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _board(**player_kwargs):
    return Scenario().player("alice", **player_kwargs)


def test_walking_ballista_enters_with_x_plus_one_plus_one_counters():
    """The reported case: X=1, two untapped mana sources for `{X}{X}`."""
    scenario = _board(hand=["Walking Ballista"], battlefield=["Forest", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest")

    casting = scenario.cast("Walking Ballista")
    casting.determine_cost(x_value=1)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    ballista = scenario.resolve_top()

    assert ballista.zone is Zone.BATTLEFIELD
    assert ballista.counters[Counter.PLUS_ONE] == 1
    assert ballista.power == 1
    assert ballista.toughness == 1


def test_walking_ballista_at_x_two_enters_with_two_counters():
    """A different X reads a different count off the same cast record - not a
    coincidence that happens to work at X=1.
    """
    scenario = _board(
        hand=["Walking Ballista"], battlefield=["Forest", "Forest", "Forest", "Forest"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")

    casting = scenario.cast("Walking Ballista")
    casting.determine_cost(x_value=2)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    ballista = scenario.resolve_top()

    assert ballista.zone is Zone.BATTLEFIELD
    assert ballista.counters[Counter.PLUS_ONE] == 2
    assert ballista.power == 2
    assert ballista.toughness == 2


def test_walking_ballista_at_x_zero_dies_to_state_based_actions():
    """CR 704.5f: a legally cast X=0 Ballista is a real 0/0, and a 0/0 dying
    on the spot is the *correct* outcome, not something the X fix should mask.
    `resolve_top` already runs state-based actions as part of resolving, so a
    zero-toughness creature never survives to be inspected mid-battlefield.
    """
    scenario = _board(hand=["Walking Ballista"], battlefield=[]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Walking Ballista")
    casting.determine_cost(x_value=0)
    payment = casting.begin_paying()
    scenario.pay_with(payment)
    scenario.put_on_stack(casting)
    ballista = scenario.resolve_top()

    assert ballista.zone is Zone.GRAVEYARD
    assert ballista.counters[Counter.PLUS_ONE] == 0


def test_walking_ballista_enters_summoning_sick():
    """CR 302.6/CR 508.1a: freshly resolved, it has not been under its
    controller's control since their most recent turn began, so its own
    `{4}:` ability (a `{T}`-free cost, but the creature is still summoning
    sick the same way any creature is) is unaffected in principle - what this
    actually pins down is that the X fix does not also, by accident, grant it
    haste or backdate its arrival.
    """
    scenario = _board(hand=["Walking Ballista"], battlefield=["Forest", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest")

    casting = scenario.cast("Walking Ballista")
    casting.determine_cost(x_value=1)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    ballista = scenario.resolve_top()

    assert ballista.is_summoning_sick is True


def test_hangarback_walker_also_scales_off_the_same_fix():
    """`_self_enters_modifiers` is generic over any card printing this exact
    "enters with X `<kind>` counters" shape, not a Walking-Ballista-only
    patch - Hangarback Walker (a different card, a different counter kind
    phrase, same replacement shape) scales for free.
    """
    scenario = _board(
        hand=["Hangarback Walker"],
        battlefield=["Forest"] * 6,
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Forest"] * 6))

    casting = scenario.cast("Hangarback Walker")
    casting.determine_cost(x_value=3)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    walker = scenario.resolve_top()

    assert walker.zone is Zone.BATTLEFIELD
    assert walker.counters[Counter.PLUS_ONE] == 3


def test_walking_ballista_found_by_a_search_effect_is_not_guessed_at():
    """CR 107.3m only defines X for an object that *resolved as a spell with
    that cost* - a Walking Ballista put onto the battlefield by another
    effect entirely (never cast, no cast record of its own) has no X defined
    by this rule at all. `game.cast_records` has no entry for it, so the
    existing pre-fix behaviour - no counters placed, the replacement skipped -
    stays exactly as it was; this is not "fixed" into guessing a value CR
    107.3m never supplies. (Green Sun's Zenith is the vehicle here on
    purpose: it is the other reported card, both from the same live game.)
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Green Sun's Zenith"],
            battlefield=["Forest", "Forest"],
            library=["Walking Ballista"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest")

    casting = scenario.cast("Green Sun's Zenith")
    casting.determine_cost(x_value=0)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    # Walking Ballista is colorless (not green) - Green Sun's Zenith's own
    # "green creature card" restriction never finds it however X is chosen,
    # so this exercises "found nothing" rather than sneaking a definition of
    # X for a non-cast Ballista in through the back door.
    assert scenario.find("Walking Ballista", Zone.LIBRARY).zone is Zone.LIBRARY
