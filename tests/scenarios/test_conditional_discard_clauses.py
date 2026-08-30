""" "You may discard a card. If you do, `<consequence>`." (CR 118.12's
discard-flavoured cousin of `_parse_conditional_sacrifice_clause`) -
`_merge_may_discard_if_you_do_clauses` in `machines/effects.py`.

Formidable Speaker is the vehicle: "When this creature enters, you may
discard a card. If you do, search your library for a creature card, reveal
it, put it into your hand, then shuffle." Before this file, nothing taught
the model this shape with a discard as the optional cost - only a sacrifice
(`test_conditional_sacrifice_clauses.py`) - so the trigger resolved doing
nothing at all.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 118.12** - "Some spells, activated abilities, and triggered abilities
  read ... '[A player] may [do something]. If [that player] [does, doesn't,
  or can't], [effect].' The action [do something] is a cost, paid when the
  spell or ability resolves. The 'If [a player] [does, doesn't, or can't]'
  clause checks whether the player chose to pay an optional cost ...
  regardless of what events actually occurred." The search consequence runs
  whenever the player says yes and actually discards, with no second check
  on the board afterward.
- **CR 701.9a** - "To discard a card, move it from its owner's hand to that
  player's graveyard."
- **CR 608.2d** - "The player can't choose an option that's illegal or
  impossible" - an empty hand has no legal card to discard, so the "you may"
  is never even offered.
- **CR 701.23b** - a search for a stated quality (a creature card) is never
  required to succeed; an empty or creature-less library just finds nothing.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

FORMIDABLE_SPEAKER = "Formidable Speaker"


def test_discarding_then_searches_the_library_for_a_creature_card():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Formidable Speaker", "Lightning Bolt"],
            battlefield=["Forest", "Forest", "Forest"],
            library=["Forest", "Grizzly Bears", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")

    scenario.will_take_the_may(True, source=FORMIDABLE_SPEAKER)
    scenario.will_discard(bolt, username="alice")

    scenario.cast_and_resolve("Formidable Speaker", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.HAND
    assert bears in alice.hand
    assert bears not in alice.library


def test_declining_the_discard_leaves_the_hand_and_library_untouched():
    """CR 608.2d: declining is always legal, and the search never runs
    without the discard that gates it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Formidable Speaker", "Lightning Bolt"],
            battlefield=["Forest", "Forest", "Forest"],
            library=["Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")

    scenario.will_take_the_may(False, source=FORMIDABLE_SPEAKER)

    scenario.cast_and_resolve("Formidable Speaker", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert bolt.zone is Zone.HAND
    assert bolt in alice.hand
    assert bears.zone is Zone.LIBRARY


def test_an_empty_hand_makes_the_discard_illegal_and_none_is_asked():
    """The creature itself is already on the battlefield when its ETB
    resolves, so an otherwise-empty hand genuinely has nothing to discard -
    CR 608.2d's impossible option, never even offered."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Formidable Speaker"],
            battlefield=["Forest", "Forest", "Forest"],
            library=["Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")

    scenario.cast_and_resolve("Formidable Speaker", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    from magic_cards_model.machines.decisions import DecisionKind

    may_questions = [d for d in scenario.questions_asked() if d.kind is DecisionKind.MAY]
    assert may_questions
    assert may_questions[-1].affirmative_is_legal is False
    assert bears.zone is Zone.LIBRARY
    assert alice.hand == []


def test_a_library_with_no_creature_card_finds_nothing():
    """CR 701.23b: searching for a stated quality never has to succeed."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Formidable Speaker", "Lightning Bolt"],
            battlefield=["Forest", "Forest", "Forest"],
            library=["Mountain", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")

    scenario.will_take_the_may(True, source=FORMIDABLE_SPEAKER)
    scenario.will_discard(bolt, username="alice")

    scenario.cast_and_resolve("Formidable Speaker", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert len(alice.library) == 2
    assert alice.hand == []
