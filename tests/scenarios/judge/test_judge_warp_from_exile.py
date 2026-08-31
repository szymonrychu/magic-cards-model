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
from exile without it. What it cannot do is Syncopate itself - see the `xfail`.

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


def test_syncopates_counter_clause_is_not_read_at_all():
    """DDR#963's counterspell, and why the episode cannot be built around it.

    Syncopate (verified with `resolve_cards`): "Counter target spell unless its
    controller pays {X}. If that spell is countered this way, exile it instead
    of putting it into its owner's graveyard."

    `machines/effects.py` has a regex for exactly the first sentence's shape -
    `_COUNTER_UNLESS_PAYS_RE`, CR 118.12a's "unless" rider, which Censor and
    Mystical Dispute go through - but it accepts a literal digit only, so
    Syncopate's `{X}` never matches. Nothing else reaches the sentence either,
    and `effect_for` fails closed on the whole card rather than guessing.

    This is the same family of gap the ledger already records for DDR#984 and
    DDR#940: an announced X never reaches the code that would need it.
    Asserted directly, so the gap is a fact in the suite rather than a note.
    """
    assert effect_for("Syncopate", card("Syncopate").oracle_text or "") is None


@pytest.mark.xfail(
    reason="Syncopate has no effect_for row (its {X} counter-unless-pays clause "
    "and its exile rider are both unread), so it resolves and counters "
    "nothing - the warp spell resolves onto the battlefield instead",
    strict=True,
)
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

    Not runnable: with no effect, Syncopate leaves the Colossus alone and it
    resolves onto the battlefield, so the first assertion below fails.
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
    scenario.cast_onto_stack("Syncopate", auto=True, username="bob", targets=[colossus])
    scenario.resolve_top()

    assert colossus.zone is Zone.EXILE, "countered, then exiled instead"

    again = scenario.cast("Bygone Colossus", from_zone=Zone.EXILE)
    with pytest.raises(ValueError, match="not warped"):
        again.use_keyword("Warp")
