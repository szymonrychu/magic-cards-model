"""A keyword-ability line printed next to a spell's own sentence must not take
that sentence down with it.

`machines/effects.py` reads a spell's effect off its printed text. A keyword
ability (CR 702.1: "the object lists only the name of the ability as a
'keyword'") is never one of CR 608.2c's resolution instructions - it is a
separate ability of the object - so the dispatcher has always stripped keyword
lines before splitting the text into clauses. It did so from a *whitelist* of
one regex per keyword, which meant a card printing a keyword nobody had added
yet lost its whole effect:

- **Metallic Rebuke** - "Improvise (...)\\nCounter target spell unless its
  controller pays {3}." Improvise (CR 702.126a) is "a static ability that
  functions while the spell with improvise is on the stack", changing how the
  generic part of an already-determined cost is paid; it is not something the
  spell does on resolution. With no `_IMPROVISE_LINE_RE` in the whitelist the
  countered spell simply stayed on the stack.
- **Lórien Revealed** - "Draw three cards.\\nIslandcycling {1} (...)".
  Typecycling (CR 702.29e) is an activated ability of the card in *hand*, and
  the same whitelist gap silenced the draw.

The fix is structural, so this file asserts the *general* property - a
keyword-ability line does not change what the spell does - rather than the two
cards. The controls are the cards whose keyword lines already had a hand-written
regex (Consign to Memory's replicate, Censor's cycling): they must keep working,
which is what proves the generalisation replaced the whitelist rather than
disturbing it.

Every CR number here was looked up with `knowledge_search(q="...", type="rules")`
in the session that wrote this file:

- **CR 702.1** - "Most abilities describe exactly what they do in the card's
  rules text. Some, though, are very common or would require too much space to
  define on the card. In these cases, the object lists only the name of the
  ability as a 'keyword' ..."
- **CR 113.3** (via CR 113.3d, "Static abilities are written as statements") -
  the ability categories a printed line falls into; a keyword line is not a
  spell ability.
- **CR 702.126a** - improvise: "a static ability that functions while the spell
  with improvise is on the stack".
- **CR 702.126b** - improvise "isn't an additional or alternative cost and
  applies only after the total cost of the spell with improvise is determined".
- **CR 702.29e** - typecycling: "'[Type]cycling [cost]' means '[Cost], Discard
  this card: Search your library for a [type] card ...'".
- **CR 701.6a** - "To counter a spell or ability means to cancel it, removing it
  from the stack. It doesn't resolve and none of its effects occur. A countered
  spell is put into its owner's graveyard."
- **CR 118.12a** - "[Do something] unless [a player does something else]" means
  "[A player may do something else]. If [that player] doesn't, [do something]."
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import effect_for
from magic_cards_model.machines.objects_as_costs import improvise
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from tests.cards import card
from tests.scenarios.harness import Scenario

#: The junk artifacts `test_improvise.py` already uses: real printings off the
#: registered affinity list, none of which taps for mana.
ARTIFACTS = ["Mishra's Bauble", "Tormod's Crypt"]


def resolution_sentence(name: str, *, drop: int) -> str:
    """The card's printed text with line `drop` removed.

    Read off the real printing, never hand-written: the point of the assertion
    below is that the dispatcher reads the *printed* text as well as it reads
    this reduced version of it.
    """
    lines = (card(name).oracle_text or "").split("\n")
    return "\n".join(line for index, line in enumerate(lines) if index != drop)


# --------------------------------------------------------------------------
# The parser-level property: the keyword line changes nothing
# --------------------------------------------------------------------------


def test_improvise_line_does_not_silence_metallic_rebuke():
    """CR 702.126a's line is not a CR 608.2c instruction, so removing it must
    not be what makes the spell readable."""
    printed = card("Metallic Rebuke").oracle_text or ""

    assert printed.startswith("Improvise")
    assert effect_for("Metallic Rebuke", resolution_sentence("Metallic Rebuke", drop=0)) is not None
    assert effect_for("Metallic Rebuke", printed) is not None


def test_islandcycling_line_does_not_silence_lorien_revealed():
    """CR 702.29e's line is an activated ability of the card in hand."""
    printed = card("Lórien Revealed").oracle_text or ""

    assert "Islandcycling" in printed
    assert effect_for("Lórien Revealed", resolution_sentence("Lórien Revealed", drop=1)) is not None
    assert effect_for("Lórien Revealed", printed) is not None


def test_the_whitelisted_keyword_lines_still_strip():
    """The controls: replicate (Consign to Memory) and cycling (Censor) each
    had a hand-written regex before this generalisation and must keep working."""
    for name in ("Consign to Memory", "Censor"):
        assert effect_for(name, card(name).oracle_text) is not None


# --------------------------------------------------------------------------
# End to end: Metallic Rebuke, paid with improvise, actually counters
# --------------------------------------------------------------------------


def rebuke_board() -> Scenario:
    """Alice casts Opt into Bob's Metallic Rebuke.

    Bob's board is two junk artifacts and one Island: `{2}{U}` with the two
    generic symbols covered by improvise (CR 702.126a) and the `{U}` paid with
    mana, which is the whole point of the card.
    """
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Opt"], battlefield=["Island", "Island"], library=["Forest"] * 3)
        .player("bob", hand=["Metallic Rebuke"], battlefield=[*ARTIFACTS, "Island"])
    )


def test_metallic_rebuke_counters_the_spell_it_targets():
    """CR 701.6a: Alice has no floating mana, so the {3} of CR 118.12a's
    "unless" is not a legal choice and Opt is countered."""
    scenario = rebuke_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    opt = scenario.cast_onto_stack("Opt", username="alice", auto=True)
    scenario.pass_priority("alice")

    casting = scenario.cast("Metallic Rebuke", username="bob", targets=[opt])
    payment = casting.begin_paying()
    improvise(payment, casting.spell, *scenario.creatures(*ARTIFACTS, username="bob"))
    assert str(payment.mana_owed) == "{U}"
    scenario.pay_with(payment, *scenario.untapped_sources("Island", username="bob"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert opt.zone is Zone.GRAVEYARD, "CR 701.6a: a countered spell goes to its owner's graveyard"
    assert scenario.stack_names() == []


def test_metallic_rebuke_is_paid_off_and_the_spell_resolves():
    """The other half of CR 118.12a: Alice pays the {3} and Opt resolves."""
    scenario = rebuke_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    alice.mana_pool.add(Color.COLORLESS, 3)
    opt = scenario.cast_onto_stack("Opt", username="alice", auto=True)
    scenario.pass_priority("alice")

    scenario.will_pay_the_mana_cost(True, username="alice", source="Metallic Rebuke")
    casting = scenario.cast("Metallic Rebuke", username="bob", targets=[opt])
    payment = casting.begin_paying()
    improvise(payment, casting.spell, *scenario.creatures(*ARTIFACTS, username="bob"))
    scenario.pay_with(payment, *scenario.untapped_sources("Island", username="bob"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert opt.zone is Zone.STACK, "the {3} was paid, so nothing was countered"
    # Without the {3} actually being asked for, "nothing was countered" would
    # also be true of a Metallic Rebuke that did nothing at all - which is
    # exactly what it did before the keyword line came off.
    (decision,) = [q for q in scenario.game.decisions.asked if q.source == "Metallic Rebuke"]
    assert decision.amount == 3
    assert alice.mana_pool.total == 0


# --------------------------------------------------------------------------
# End to end: Lórien Revealed still draws three
# --------------------------------------------------------------------------


def test_lorien_revealed_draws_three_cards():
    """The Islandcycling line (CR 702.29e) is not part of resolving the spell."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lórien Revealed"],
            battlefield=["Island"] * 5,
            library=["Forest", "Mountain", "Swamp", "Plains"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    before = len(scenario.player("alice").hand)

    scenario.cast_and_resolve("Lórien Revealed", username="alice", auto=True)

    assert len(scenario.player("alice").hand) == before - 1 + 3
