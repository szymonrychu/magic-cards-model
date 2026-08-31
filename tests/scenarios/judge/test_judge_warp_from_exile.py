"""Judge scenarios: where a warp card's permission to be cast from exile comes
from, and what happens when it reaches exile some other way.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#963** - Warp vs. Syncopate. Amy casts a spell for its warp cost and
  Nick counters it with Syncopate, which exiles the countered spell. May Amy
  now cast it from exile because of warp?

The answer is no, and the reason is structural. CR 601.3: "A player can begin
to cast a spell only if a rule or effect allows that player to cast it". Warp
does allow it - but only through the delayed triggered ability warp creates
(CR 702.185a), and only for a card that trigger exiled (CR 702.185b: "A warped
card in exile is one that was exiled by the delayed triggered ability created
by a warp ability"). A card that reached exile any other way - Syncopate,
Solitude, dying and then being exiled from the graveyard - never had that
permission handed to it.

The engine already models this distinction: `exile_warped` stamps
`ExileMarker.WARPED` onto the card, and `Casting.use_keyword` refuses "Warp"
from exile without it. Syncopate drives the whole episode end to end, once its
X is actually announced (CR 107.3a).

Card text verified with `resolve_cards`; every CR number here was looked up
with `knowledge_search(type="rules")` in this session.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import exile_warped
from magic_cards_model.machines.effects import effect_for
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import ExileMarker
from tests.cards import card
from tests.scenarios.harness import Scenario


def _warp_bygone_colossus(scenario):
    """Cast Bygone Colossus for its Warp {3} and resolve it (CR 702.185a)."""
    casting = scenario.cast("Bygone Colossus")
    casting.use_keyword("Warp")
    scenario.pay_with(
        casting.begin_paying(), *scenario.untapped_sources("Island", "Island", "Island")
    )
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def test_the_warp_trigger_is_what_makes_the_card_castable_from_exile():
    """DDR#963's positive control: exiled *by warp*, so the permission exists.

    CR 702.185a makes warp two static abilities on the stack, one of which
    creates the delayed triggered ability that exiles the permanent; CR 702.185b
    then calls what that trigger exiled a warped card. `exile_warped` performs
    that delayed trigger by hand, the way `tests/scenarios/test_warp.py` does,
    and the card comes to rest in exile carrying `ExileMarker.WARPED`.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Bygone Colossus"], battlefield=["Island"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    colossus = _warp_bygone_colossus(scenario)
    exile_warped(scenario.game, colossus)

    assert colossus.zone is Zone.EXILE
    assert colossus.exile_annotation is not None
    assert colossus.exile_annotation.marker is ExileMarker.WARPED


def test_a_warp_permanent_exiled_by_solitude_carries_no_warp_permission():
    """DDR#963's ruling, on one of the transcript's own examples: "if the warp
    card gets exiled in any other way, for example, via a Solitude ... you
    would not be able to cast it from exile".

    Alice casts Bygone Colossus for Warp {3}; it resolves onto the battlefield,
    where it is an ordinary permanent. Before the end step's delayed trigger
    can fire, Bob flashes in Solitude and exiles it. CR 601.3 now has nothing
    to point at: warp's grant was attached to the trigger that never ran, and
    the exile Solitude performed hands out no permission of its own.

    Solitude (verified with `resolve_cards`) has an enters trigger that exiles
    a creature, so its target is chosen for the trigger (CR 603.3d) rather than
    for the spell.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Bygone Colossus"], battlefield=["Island"] * 3)
        .player("bob", hand=["Solitude"], battlefield=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    colossus = _warp_bygone_colossus(scenario)
    scenario.pass_priority("alice")

    scenario.choose_trigger_targets("Solitude", [colossus])
    scenario.cast_and_resolve(
        "Solitude",
        *scenario.untapped_sources(*["Plains"] * 5, username="bob"),
        username="bob",
    )
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert colossus.zone is Zone.EXILE
    assert colossus.exile_annotation is None, "Solitude marked nothing"

    again = scenario.cast("Bygone Colossus", from_zone=Zone.EXILE)
    with pytest.raises(ValueError, match="not warped"):
        again.use_keyword("Warp")


def test_syncopates_counter_clause_needs_the_announced_x_to_be_readable():
    """DDR#963's counterspell, and the one thing its text needs before it reads.

    Syncopate (verified with `resolve_cards`): "Counter target spell unless its
    controller pays {X}. If that spell is countered this way, exile it instead
    of putting it into its owner's graveyard."

    `_COUNTER_UNLESS_PAYS_RE` reads CR 118.12a's "unless" rider with a literal
    digit, so the printed `{X}` matches nothing on its own - which is correct
    and not a gap: CR 107.3a says that when a spell's cost has an `{X}` whose
    value "isn't defined by the text of that spell", "the player casting the
    spell ... chooses and announces its value", and CR 107.3h/202.3e both make
    that announced value the one the spell has "while [it] is on the stack". So
    there is no effect to build until an X exists. `effect_for` takes the
    announced value as `x_value` and substitutes it, and `Game.resolve_top`
    reads it off `Game.cast_record` - which is why the assertion below is a
    pair, not a bare `is None`.

    This test used to assert only the `None`, and its docstring read it as a
    gap. It was not one: the card resolves correctly and
    `tests/scenarios/test_counterspells.py` has driven it through both branches
    of the payment for as long as the row has existed.
    """
    text = card("Syncopate").oracle_text or ""
    assert effect_for("Syncopate", text) is None, "no X announced yet, nothing to read"
    assert effect_for("Syncopate", text, x_value=2) is not None, "CR 107.3a's announced X"


def test_syncopate_exiles_the_countered_warp_spell_without_granting_a_recast():
    """DDR#963's actual question, written the way it would read if Syncopate
    worked.

    CR 701.6a: "To counter a spell or ability means to cancel it, removing it
    from the stack. It doesn't resolve and none of its effects occur. A
    countered spell is put into its owner's graveyard." Syncopate's second
    sentence replaces that graveyard trip with exile.

    Bob leaves {X}=1 unpaid, so Bygone Colossus is countered and exiled. Warp's
    delayed trigger was created while the spell was on the stack (CR 702.185a),
    but it exiles "the permanent this spell becomes" - and the spell never
    became a permanent, so nothing marks the card as warped. CR 601.3 then
    refuses the recast.

    Bob announces X = 1 himself (CR 107.3a) and pays `{X}{U}` with his two
    Islands. The earlier version of this test cast Syncopate through the
    harness's `auto=True` path, which never announces an X at all and so left
    it at the CR 107.1a default of 0 - alice was then asked for `{0}`, which
    she can always pay, and the Colossus was never countered. That was a test
    that never announced the value its own docstring described, not an engine
    gap.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Bygone Colossus"], battlefield=["Island"] * 3)
        .player("bob", hand=["Syncopate"], battlefield=["Island"] * 2)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Bygone Colossus")
    casting.use_keyword("Warp")
    scenario.pay_with(
        casting.begin_paying(), *scenario.untapped_sources("Island", "Island", "Island")
    )
    colossus = scenario.put_on_stack(casting)

    scenario.pass_priority("alice")
    syncopate = scenario.cast("Syncopate", username="bob", targets=[colossus])
    syncopate.determine_cost(x_value=1)
    scenario.pay_with(
        syncopate.begin_paying(), *scenario.untapped_sources("Island", "Island", username="bob")
    )
    scenario.put_on_stack(syncopate)
    scenario.resolve_top()

    assert colossus.zone is Zone.EXILE, "countered, then exiled instead"

    again = scenario.cast("Bygone Colossus", from_zone=Zone.EXILE)
    with pytest.raises(ValueError, match="not warped"):
        again.use_keyword("Warp")
