"""FRA stream S8: the reveal-hand-choose-discard family's "a nonland
permanent card" quality (`_nonland_or_typed_card_matcher` in
`machines/effects.py`).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 701.20a** - revealing a hand. **CR 701.9a/701.9b** - discarding, with
  the chooser overridden to the resolving spell's controller.
- **CR 110.4a** - "permanent card" is CR 300.1's umbrella over the six
  permanent types (artifact, battle, creature, enchantment, land,
  planeswalker).
- **CR 109.2** - "non" negates one card type.

`_merge_reveal_hand_choose_discard_clauses` already reads Thoughtseize's bare
"a nonland card" and Inquisition of Kozilek's "a creature card with mana
value N or less", through `_nonland_or_typed_card_matcher`. That reader had
no notion of a **compound** quality - a negated type qualifying a *second*
type word, "a nonland permanent card" - because `Type("land permanent")` is
not a real card type and the whole two-word string never split. Solve for
Disappointment is the reported card. Auntie's Sentence (Edge of Eternities
Commander) prints the identical clause as one mode of a modal spell - a
genuinely different, non-FRA, non-pool card, in a genuinely different
composition (`parse_mode_effect` rather than a plain spell body) - proving
the fix from the shared dispatcher both kinds of ability call into.

Solve for Disappointment's own second clause, "Empower Jace 1.", is FRA
stream S1's own keyword action and is not built on this branch (S1 merges
into `int-engine-dsl` separately) - so casting the real two-clause card here
still fails closed as a whole, by the engine's own existing all-or-nothing
per-ability composition (`_parse_mixed_clauses`'s own docstring: "a card with
one clause nothing here reads still comes back `None` for the whole thing").
That composition function is S6's, out of this stream's own scope to
rearchitect. Once S1's clause lands the whole two-clause spell reads with no
further change here, the same "no ordering dependency" S1's own report
already established for its five other silent-until-sibling-lands cards.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_solve_for_disappointment_reads_the_nonland_permanent_quality_alone():
    """The clause reader itself, isolated from Empower Jace's own missing
    parser: `parse_mixed_effect_for_spell` on the reveal-choose-discard
    sentence alone builds a real effect now, instead of `None`."""
    from magic_cards_model.machines.effects import parse_mixed_effect_for_spell

    effect = parse_mixed_effect_for_spell(
        "Target opponent reveals their hand. You choose a nonland permanent "
        "card from it. That player discards that card."
    )
    assert effect is not None


def test_aunties_sentence_reveals_hand_and_discards_the_chosen_nonland_permanent():
    scenario = (
        Scenario()
        .player("alice", hand=["Auntie's Sentence"], battlefield=["Swamp", "Swamp"])
        .player("bob", hand=["Grizzly Bears", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    sources = scenario.untapped_sources("Swamp", "Swamp")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "bob")
    mountain = scenario.find("Mountain", Zone.HAND, "bob")

    casting = scenario.cast("Auntie's Sentence", username="alice")
    casting.choose_modes([1])
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.will_choose_cards(bears, username="alice")
    scenario.resolve_top()

    # The land in hand was never a legal choice (CR 608.2d: it is not a
    # permanent card CR 110.4a's own umbrella excludes land from once the
    # "non" is applied - it is excluded *because* it is a land - so only the
    # nonland permanent is ever offered).
    assert bears.zone is Zone.GRAVEYARD
    assert mountain.zone is Zone.HAND
    assert len(bob.hand) == 1
