"""Riddles in the Dark: "Look at the top four cards of your library and
separate them into a face-down pile and a face-up pile. An opponent chooses
one of the piles. Put that pile into your hand and the other into your
graveyard."

CR 700.3's pile primitive already had a working implementation - Liliana of
the Veil's own `-6` (`_parse_separate_into_two_piles_then_consequence_
whole_text`, `_SEPARATE_INTO_TWO_PILES_RE`) - but that reader is scoped to
"separate all `<quality>` **target player** controls into two piles"
followed by a named consequence verb (sacrifice/destroy) applied to whatever
the *target* player picked. Riddles in the Dark is a different shape on the
same CR 700.3 primitive: the piled objects are cards looked at from the top
of a library, not battlefield permanents; there is no target at all, only
"an opponent"; the divider is the resolving spell's own controller, not a
named player; and the consequence is a fixed hand/graveyard split rather
than a printed verb. `_parse_look_top_separate_face_down_face_up_piles_
clause`, a new whole-text reader, reuses the identical two-question CR
700.3a/700.3d shape (`CHOOSE_CARDS` to divide, then `DecisionKind.
CHOOSE_PILE` to pick a whole pile) with those four differences threaded
through, plus a real information split the earlier reader had no reason to
model: a card sorted into the face-up pile is actually revealed (CR
701.20a) before the opponent chooses, and a face-down one is not.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 700.3a** - "Each of the affected objects must be put into exactly one
  of those piles."
- **CR 700.3d** - "A pile can contain zero or more objects."
- **CR 700.3c** worked example (Fact or Fiction) - the objects stay in their
  current zone while being divided into piles; here, the library.
- **CR 701.20a** - revealing a card does not move it or change its zone.
- **CR 102.2** - in a two-player game, "an opponent" is the only other
  player.

Proof printing: **Curator of Destinies** (real Scryfall data, added with
`scripts/add_card.py`, not a listed card, not in any `magic-cards-model-api/
decks/*.txt` list, Modern/Pioneer/Standard all `legal`) - the identical
template with a different count (five cards, not four) and a different
printed pronoun ("one of those piles" rather than "one of the piles"), which
is why the reader's own regex accepts both.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_opponent_takes_the_face_up_pile_the_rest_go_to_the_graveyard():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Riddles in the Dark"],
            battlefield=["Island"] * 3,
            library=["Grizzly Bears", "Opt", "Mountain", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears, opt, mountain, forest = alice.library
    sources = scenario.untapped_sources("Island", "Island", "Island")

    # alice, the divider, puts Grizzly Bears and Opt into the face-up pile;
    # Mountain and Forest fall into the face-down complement.
    scenario.will_choose_cards(bears, opt, username="alice", source="Riddles in the Dark")
    # bob, the chooser, takes the face-up pile.
    scenario.will_choose_pile(True, username="bob", source="Riddles in the Dark")
    scenario.cast_and_resolve("Riddles in the Dark", *sources)

    assert bears in alice.hand
    assert opt in alice.hand
    assert mountain.zone is Zone.GRAVEYARD
    assert forest.zone is Zone.GRAVEYARD
    assert alice.library == []


def test_opponent_takes_the_face_down_pile_instead():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Riddles in the Dark"],
            battlefield=["Island"] * 3,
            library=["Grizzly Bears", "Opt", "Mountain", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears, opt, mountain, forest = alice.library
    sources = scenario.untapped_sources("Island", "Island", "Island")

    scenario.will_choose_cards(bears, opt, username="alice", source="Riddles in the Dark")
    scenario.will_choose_pile(False, username="bob", source="Riddles in the Dark")
    scenario.cast_and_resolve("Riddles in the Dark", *sources)

    assert mountain.zone is Zone.HAND
    assert forest.zone is Zone.HAND
    assert bears.zone is Zone.GRAVEYARD
    assert opt.zone is Zone.GRAVEYARD


def test_curator_of_destinies_reads_the_same_template_with_a_different_pronoun():
    """Proof card: "look at the top five cards ... An opponent chooses one
    of *those* piles." - the wording `_LOOK_TOP_SEPARATE_FACE_DOWN_FACE_UP_
    PILES_RE` had to widen to accept."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Curator of Destinies"],
            battlefield=["Island"] * 6,
            library=["Grizzly Bears", "Opt", "Mountain", "Forest", "Elvish Mystic"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears, opt, mountain, forest, mystic = alice.library
    sources = scenario.untapped_sources(*(["Island"] * 6))

    scenario.will_choose_cards(bears, mystic, username="alice", source="Curator of Destinies")
    scenario.will_choose_pile(True, username="bob", source="Curator of Destinies")
    scenario.cast_and_resolve("Curator of Destinies", *sources)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    assert bears in alice.hand
    assert mystic in alice.hand
    for state in (opt, mountain, forest):
        assert state.zone is Zone.GRAVEYARD
