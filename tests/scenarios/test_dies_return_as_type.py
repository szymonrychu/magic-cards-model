"""Scenario: a permanent that dies and returns to the battlefield with its
card types set (CR 205.1a, CR 400.7), on a legendary creature whose printed
name and dies-trigger pronouns are plural.

Widens C00-T8's Enduring-cycle reader (`_RETURN_SELF_AS_TYPE_RE`/
`_parse_return_self_as_type_clause`) rather than duplicating it: the same
regex and effect function now also accept "them"/"they're" in place of
"it"/"it's", an absent "under ... control" clause (CR 110.2a's own default),
and a "no longer a `<type>`" reminder in place of "not a `<type>`".

Tom, Bert, and William: "When Tom, Bert, and William die, if they were a
creature, return them to the battlefield. They're an artifact. (They're no
longer a creature.)"

Verified this session with `mise run rules:find`:

- **CR 201.5** - a card's own printed name (here, one three-person legend)
  self-references anywhere on that same card.
- **CR 603.4** - "if they were a creature" is CR 603.4's own past-tense
  intervening *if*, checked as the event occurs and again at resolution.
- **CR 400.7** - the returned permanent is a new object with none of the old
  one's counters, damage, or other characteristics.
- **CR 205.1a** - setting card types replaces the existing ones and drops
  any subtype correlated only with a removed type.
- **CR 110.2a** - with no control clause printed, the effect's own default
  applies: under the resolving ability's controller.

Enduring Innocence and Enduring Curiosity (pre-existing pool cards) already
cover the singular "it"/"it's"/"under its owner's control" shape this reader
handled before this wave; this file is only about the widened plural,
no-control-clause and reminder-wording paths, so it exercises Tom, Bert, and
William directly rather than duplicating those two cards' own tests. No
Modern/Pioneer/Standard-legal printing of a plural-subject, multi-name
legendary creature with an identical dies-return-as-type trigger was found by
`card_search` (dated MEMORY.md line) - three named characters sharing one
card is itself a novel design this set introduces.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Type, Zone

from .harness import Scenario


def test_tom_bert_and_william_draws_off_the_sacrificed_creatures_power():
    """ "{1}, Sacrifice another creature: Draw cards equal to the sacrificed
    creature's power, then discard a card." - `AbilityOnStack.cost_
    sacrificed_card_ids`'s own printed power, read after the creature has
    already left the battlefield (CR 602.2b: costs are paid before the
    ability exists)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mountain", "Forest"],
            battlefield=["Tom, Bert, and William", "Grizzly Bears"] + ["Swamp"],
            library=["Island", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    trolls = scenario.creature("Tom, Bert, and William", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    hand_before = len(scenario.player("alice").hand)

    scenario.activate(trolls, *scenario.untapped_sources("Swamp"), sacrificing=[bears])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    # +2 drawn (Grizzly Bears is 2/2), -1 discarded, -1 for the Swamp already
    # tapped (irrelevant to hand size) - net the starting two cards + 2 - 1.
    assert len(scenario.player("alice").hand) == hand_before + 2 - 1


def test_greater_good_reads_the_same_sacrificed_power_channel():
    """Off-pool proof: Greater Good's own "Sacrifice a creature: Draw cards
    equal to the sacrificed creature's power, then discard three cards."
    shares `_parse_draw_equal_to_sacrificed_creature_power_then_discard_
    clause` with Tom, Bert, and William - a different discard count, the
    same `cost_sacrificed_card_ids` read."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mountain", "Forest", "Swamp", "Plains"],
            battlefield=["Greater Good", "Grizzly Bears"],
            library=["Island"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    good = scenario.creature("Greater Good", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    hand_before = len(scenario.player("alice").hand)

    scenario.activate(good, sacrificing=[bears])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == hand_before + 2 - 3


def test_tom_bert_and_william_returns_as_an_artifact_when_it_dies_a_creature():
    scenario = (
        Scenario().player("alice", battlefield=["Tom, Bert, and William"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    trolls = scenario.creature("Tom, Bert, and William", "alice")

    stamp_before = trolls.zone_change_stamp
    scenario.game.destroy(trolls)
    scenario.pass_until_resolved()

    returned = scenario.creature("Tom, Bert, and William", "alice")
    assert returned.zone_change_stamp != stamp_before  # CR 400.7: a new object
    assert returned.zone is Zone.BATTLEFIELD
    characteristics = scenario.game.characteristics_of(returned)
    assert characteristics.types == (Type.ARTIFACT,)
    assert Type.CREATURE not in characteristics.types
    assert "Troll" not in characteristics.subtypes


def test_it_enters_under_the_resolving_controller_with_no_printed_control_clause():
    """No "under its owner's/your control" phrase is printed at all - CR
    110.2a's default is the ability's own controller, which here is also the
    card's owner, so this alone does not distinguish the two; the point is
    only that the return does not silently fail for lacking that clause."""
    scenario = (
        Scenario().player("alice", battlefield=["Tom, Bert, and William"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    trolls = scenario.creature("Tom, Bert, and William", "alice")

    scenario.game.destroy(trolls)
    scenario.pass_until_resolved()

    returned = scenario.creature("Tom, Bert, and William", "alice")
    assert scenario.game.controller_of(returned).username == "alice"
