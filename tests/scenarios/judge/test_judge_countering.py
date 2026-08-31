"""Judge scenarios: countering a spell, and what happens to it afterward.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#944** - Countering a Commander with Transcendent Dragon (a counter that
  also redirects the countered spell to exile so it can be recast)

Every CR number here was looked up with `knowledge_search(type="rules")`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.replacement import parse_replacement_effects
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# DDR#944 - Transcendent Dragon's whole ability is one trigger paragraph
# --------------------------------------------------------------------------


def test_transcendent_dragons_replacement_clause_is_never_even_read():
    """DDR#944, the provable half: `parse_replacement_effects` returns nothing.

    Transcendent Dragon's oracle text (confirmed with `resolve_cards`, one
    printed line): "When this creature enters, if you cast it, counter target
    spell. If that spell is countered this way, exile it instead of putting it
    into its owner's graveyard, then you may cast it without paying its mana
    cost."

    The second sentence reads exactly like a CR 614.1a replacement effect - "If
    [event] would ... exile it instead" is the shape `_try_if_would` claims
    everywhere else in this suite (DDR#830, DDR#403). It is never offered to
    that parser at all, because CR 603.1 templates a triggered ability as
    "[When/Whenever/At] [condition], [effect]. [Instructions (if any).]" and
    says the trailing instructions belong to the trigger - the whole paragraph,
    not just its first sentence. `machines/replacement.py`'s own boundary rule
    (`_TRIGGER_OPENER`) reads a paragraph starting with "When" and skips it
    entirely, replacement-shaped sentences and all, which is the same rule
    already documented there for Rest in Peace's enters-trigger. Transcendent
    Dragon's whole ability is one line of oracle text, so the "exile it
    instead" clause is discarded along with everything else in the paragraph.
    """
    assert parse_replacement_effects(card("Transcendent Dragon")) == []


def test_transcendent_dragon_counters_and_exiles_the_target_spell():
    """DDR#944: flashing in Transcendent Dragon in response to a spell counters
    it and exiles it instead of sending it to its owner's graveyard (CR 701.6,
    CR 701.13a), so its controller can cast it again for free.

    CR 701.6a: "To counter a spell or ability means to cancel it, removing it
    from the stack. It doesn't resolve." Countering alone would send the spell
    to its owner's graveyard by the normal rule for a spell leaving the stack
    without resolving; Transcendent Dragon's second sentence redirects that one
    zone change to exile.

    This was `xfail` (its trigger going on the stack with an empty target list,
    so "counter target spell" had nothing to counter) until the CR 601.2c/
    CR 603.3d fix for the mandatory-`CHOOSE_TARGETS` defect this suite is now
    named for (see `tests/scenarios/test_trigger_target_decisions.py`): a
    mandatory "target spell" now defaults to the one legal target on the stack
    - Lightning Bolt - instead of to none, exactly as CR 601.2c requires, so
    the trigger's own already-registered effect gets a target to act on and
    this now passes for the right reason.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Transcendent Dragon"], battlefield=["Island"] * 6)
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", auto=True, username="bob", targets=["alice"])
    scenario.pass_priority("bob")
    scenario.cast_onto_stack("Transcendent Dragon", auto=True, username="alice", targets=[])
    scenario.resolve_top()  # the Dragon itself enters the battlefield
    scenario.resolve_top()  # Lightning Bolt, uncountered, resolves normally
    assert bolt.zone is Zone.EXILE
