"""Greater Gargadon's own second ability: a suspend-only, exile-functioning
activated ability with a disjunctive sacrifice cost (CR 602.5b, CR 702.62b,
CR 113.6).

Real oracle text (`resolve_cards`, this session): "Suspend 10-{R}\\nSacrifice
an artifact, creature, or land: Remove a time counter from this card.
Activate only if this card is suspended." `tests/scenarios/test_suspend.py`
already proves CR 702.62a's own three abilities general to any printed
"Suspend N-[cost]" line, including Greater Gargadon's - upkeep removing one
counter at a time, and the last counter's removal handing out a
`PlayPermission`. This file is the card's *other* printed ability: the
sacrifice-to-strip-a-counter engine that makes Gargadon a combo piece, not
merely a slow suspend creature.

Three pieces this needed, none of them a card-name-keyed row:

- **Where the ability functions.** CR 113.6's default is the battlefield, but
  this ability's own "Activate only if this card is suspended" restriction
  can only ever be true while the card is exiled (CR 702.62b: "suspended"
  means, among other things, "in the exile zone") - so
  `machines.abilities._activated_ability_zone` reads that restriction the
  same way it already reads World Breaker's own graveyard self-reference,
  tagging the ability `Zone.EXILE`, `"CR 702.62b"`. `machines.keywords.
  off_battlefield_activation` (already built for Channel, World Breaker) then
  needed nothing new to *carry* an exile-functioning ability - only one more
  check in `KeywordActivation.why_not`, gated on that same `"CR 702.62b"` tag,
  confirming the card is not merely exiled but actually `is_suspended`
  (`models.card_state.CardState.is_suspended`, a new predicate CR 702.62b
  spells out precisely: exiled, the suspend marker, and at least one time
  counter) - a card exiled with its counters already gone, or exiled some
  other way entirely, does not qualify.
- **The disjunctive sacrifice cost.** "Sacrifice an artifact, creature, or
  land" is `machines.cost.CardRequirement.types` with three entries - already
  a disjunction ("at least one of these") by its own docstring - but reaching
  it needed two fixes: `machines.abilities._merge_disjunctive_sacrifice_cost`
  re-joins the comma-and-"or" list's own commas, which `_split_top_level`
  otherwise reads as three separate top-level costs; and `machines.cost.
  _requirement` now strips each word's own list punctuation and skips the
  bare connectors ("or", "and") instead of failing the whole phrase the
  moment it sees one.
- **The effect.** `machines.effects._parse_remove_time_counter_from_self_clause`
  reads "Remove a time counter from this card." off the ability's own text
  (no row), and calls `machines.casting.remove_suspend_time_counter` followed
  by `machines.casting.finish_suspend` - the same two functions the upkeep
  route already calls by hand, chained here because this ability's own
  resolution *is* the concrete "a time counter just came off" event, so there
  is nothing left for a caller to separately notice. `finish_suspend` is a
  no-op on every activation but the last; on the last it grants the same
  `PlayPermission` (`Game.play_permissions`) the upkeep route already does,
  which is what `test_removing_the_last_time_counter_this_way_reaches_the_
  free_cast_path` below actually casts the card off.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import (
    Casting,
    MarkedExile,
    finish_suspend,
    remove_suspend_time_counter,
)
from magic_cards_model.machines.keywords import off_battlefield_activation
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _suspend_gargadon(scenario, player="alice"):
    """Pay {R} and exile Greater Gargadon with 10 time counters (CR 116.2f)."""
    gargadon = scenario.find("Greater Gargadon", Zone.HAND, player)
    action = MarkedExile.suspend(scenario.game, gargadon, player)
    payment = action.begin_paying()
    (mountain,) = scenario.untapped_sources("Mountain", username=player)
    scenario.pay_with(payment, mountain)
    action.take()
    return scenario.find("Greater Gargadon", Zone.EXILE, player)


def _activate_sacrificing(scenario, gargadon, permanent, player="alice"):
    """Activate the sacrifice ability, paying by sacrificing `permanent`."""
    activation = off_battlefield_activation(
        scenario.game, gargadon, player, sacrificing=[permanent]
    )
    payment = activation.begin_paying()
    payment.pay()
    activation.activate()
    activation.resolve()
    return activation


def _new_game():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Greater Gargadon"],
            battlefield=[
                "Mountain",
                "Mountain",
                "Sol Ring",
                "Grizzly Bears",
                "Glorious Anthem",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_the_ability_functions_from_exile_once_suspended():
    """`_activated_ability_zone` tags the ability `Zone.EXILE`, `"CR
    702.62b"` off the card's own "Activate only if this card is suspended"
    restriction - proven directly against the real printing, no per-card row.
    """
    scenario = _new_game()
    gargadon = _suspend_gargadon(scenario)
    activation = off_battlefield_activation(scenario.game, gargadon, "alice")
    assert activation.zone is Zone.EXILE
    assert activation.rule == "CR 702.62b"


def test_sacrificing_an_artifact_removes_a_time_counter():
    scenario = _new_game()
    gargadon = _suspend_gargadon(scenario)
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    assert gargadon.counter_count(Counter.TIME) == 10

    _activate_sacrificing(scenario, gargadon, sol_ring)

    assert gargadon.counter_count(Counter.TIME) == 9
    assert sol_ring.zone is Zone.GRAVEYARD


def test_sacrificing_a_creature_removes_a_time_counter():
    """Proves the disjunction: a creature pays the same cost an artifact
    does (CR 118.3)."""
    scenario = _new_game()
    gargadon = _suspend_gargadon(scenario)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")

    _activate_sacrificing(scenario, gargadon, bears)

    assert gargadon.counter_count(Counter.TIME) == 9
    assert bears.zone is Zone.GRAVEYARD


def test_sacrificing_a_land_removes_a_time_counter():
    """The third disjunct: a land pays it too."""
    scenario = _new_game()
    gargadon = _suspend_gargadon(scenario)
    (extra_mountain,) = scenario.untapped_sources("Mountain")

    _activate_sacrificing(scenario, gargadon, extra_mountain)

    assert gargadon.counter_count(Counter.TIME) == 9
    assert extra_mountain.zone is Zone.GRAVEYARD


def test_sacrificing_an_enchantment_is_refused():
    """Glorious Anthem is none of "artifact, creature, or land" - the
    `CardRequirement` built from the disjunctive list refuses it (CR 118.3),
    rather than the cost silently accepting anything sacrificeable."""
    scenario = _new_game()
    gargadon = _suspend_gargadon(scenario)
    anthem = scenario.find("Glorious Anthem", Zone.BATTLEFIELD, "alice")

    activation = off_battlefield_activation(scenario.game, gargadon, "alice", sacrificing=[anthem])
    payment = activation.begin_paying()
    with pytest.raises(ValueError, match="Glorious Anthem"):
        payment.pay()

    assert gargadon.counter_count(Counter.TIME) == 10
    assert anthem.zone is Zone.BATTLEFIELD


def test_the_ability_is_refused_while_gargadon_is_still_in_hand():
    scenario = _new_game()
    gargadon = scenario.find("Greater Gargadon", Zone.HAND, "alice")
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    activation = off_battlefield_activation(
        scenario.game, gargadon, "alice", sacrificing=[sol_ring]
    )
    with pytest.raises(ValueError, match="functions in the exile"):
        activation.begin_paying()


def test_the_ability_is_refused_once_the_last_counter_is_already_gone():
    """The card is still exiled and still carries the suspend marker, but
    CR 702.62b's "suspended" also asks for at least one time counter -
    `CardState.is_suspended` is false the instant the last one comes off, so
    the ability refuses even though the zone check alone would let it
    through."""
    scenario = _new_game()
    gargadon = _suspend_gargadon(scenario)
    sources = [
        scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice"),
        scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice"),
    ]
    for source in sources:
        _activate_sacrificing(scenario, gargadon, source)
    assert gargadon.counter_count(Counter.TIME) == 8
    assert gargadon.is_suspended is True

    for _ in range(8):
        remove_suspend_time_counter(scenario.game, gargadon)
    assert gargadon.counter_count(Counter.TIME) == 0
    assert gargadon.is_suspended is False

    anthem = scenario.find("Glorious Anthem", Zone.BATTLEFIELD, "alice")
    activation = off_battlefield_activation(scenario.game, gargadon, "alice", sacrificing=[anthem])
    with pytest.raises(ValueError, match="can only be activated while it is suspended"):
        activation.begin_paying()


def test_removing_the_last_time_counter_this_way_reaches_the_free_cast_path():
    """The brief's own bar: removing the *last* counter through this
    ability, not the upkeep route, must still reach CR 702.62a's third
    ability, so the card is actually castable for free and actually comes
    down.

    It reaches it as a **trigger** rather than as a call chained out of this
    effect. CR 702.62a's third ability is written "When the last time counter
    is removed from this card, ..." - a trigger condition, so CR 603.3 puts
    it on the stack the next time a player would receive priority and CR
    702.62b's own counting is what decides whether it fired at all. The
    activated ability's resolution raises that condition; it does not carry
    out the other ability's instruction itself.
    """
    scenario = _new_game()
    gargadon = _suspend_gargadon(scenario)

    for _ in range(9):
        remove_suspend_time_counter(scenario.game, gargadon)
    assert gargadon.counter_count(Counter.TIME) == 1
    assert finish_suspend(scenario.game, gargadon) is None  # not yet - one counter left

    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    _activate_sacrificing(scenario, gargadon, sol_ring)

    assert gargadon.counter_count(Counter.TIME) == 0
    # CR 603.3: it triggered as the last counter came off, and goes on the
    # stack at the next priority. Resolving it is what grants the free cast.
    assert len(scenario.pending_triggers) + len(scenario.game.abilities_on_stack) == 1
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
    assert len(scenario.game.play_permissions) == 1

    casting = Casting(spell=gargadon, caster="alice", origin_zone=Zone.EXILE, game=scenario.game)
    casting.use_permission()
    assert casting.total_cost.mana.converted == 0
    payment = casting.begin_paying()
    payment.pay()
    spell = casting.cast()
    scenario.game.put_on_stack(spell, "alice")
    permanent = scenario.resolve_top()

    assert permanent.zone is Zone.BATTLEFIELD
