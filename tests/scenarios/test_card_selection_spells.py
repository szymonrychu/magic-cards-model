"""Scenario: four instants/sorceries whose resolution effect was silently
doing nothing, none of them fixed by a table row - a mixed bag of a single
dispatcher bug and one genuinely new clause shape apiece.

**Opt** - "Scry 1. (...)\\nDraw a card." Both halves already had generic
readers (`_SCRY_RE`, `_DRAW_RE`), but Opt's own reminder text sits *inline*,
after "Scry 1." on the same line rather than on a line by itself - the
periods inside it (multi-sentence reminder text) were being read by
`_CLAUSE_SEPARATOR` as real sentence boundaries, producing garbage fragments
("(Look at the top card of your library", "You may put that card on the
bottom.)") that took the real "Scry 1"/"Draw a card" clauses down with them
(`_parse_mixed_clauses`'s fail-closed-per-clause-run rule). Fixed generally,
not for Opt by name: `_INLINE_REMINDER_RE` now strips reminder text wherever
it sits in the text, not only on its own line.

**Gitaxian Probe** - "Look at target player's hand.\\nDraw a card." The draw
half already read; "look at target player's hand" needed its own reader
(`_look_at_target_hand`, CR 701.20e), which records the look through
`Game.look` the same way `_look_at_top_card` does for Mishra's Bauble's own
library peek - see `test_revealed_hand_stays_known.py`.

**Faithless Looting** - "Draw two cards, then discard two cards.\\nFlashback
{2}{R} (...)" Its own printed Flashback line was never stripped before this
wave - `_strip_keyword_ability_lines` fixes that (the same class of bug already fixed
for Suspend, Cascade, Replicate, Cycling, Harmonize's own lines) - and the
draw-then-discard sentence was already generically readable once past it.

**Expressive Iteration** - "Look at the top three cards of your library. Put
one of them into your hand, put one of them on the bottom of your library,
and exile one of them. You may play the exiled card this turn." A genuinely
new three-way CR 608.2d split plus a CR 601.3 play permission over the third
group (`_merge_look_top_hand_bottom_exile_play_clauses`) - the spell-side
sibling of `_parse_exile_then_play_permission_pair`'s ability-only shape.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 701.22a** - scry.
- **CR 121.1/121.2** - drawing, one card at a time.
- **CR 701.20e** - "Looking at a card follows the same rules as revealing a
  card, except that the card is shown only to the specified player."
- **CR 702.34a** - flashback, two static abilities, neither a CR 608.2c
  resolution instruction.
- **CR 701.9a** - discarding, CR 701.9b's default chooser.
- **CR 608.2d** - a resolving effect's own choice, made by its controller.
- **CR 601.3** - "A player can begin to cast a spell only if a rule or effect
  allows that player to cast it."
- **CR 400.7** - the permission dies when the object changes zones again.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# Opt
# --------------------------------------------------------------------------


def test_opt_scries_then_draws():
    """Scry the Mountain to the bottom, then draw the Forest underneath it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Opt"],
            library=["Mountain", "Forest"],
            battlefield=["Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Island")
    mountain = scenario.find("Mountain", Zone.LIBRARY, "alice")

    scenario.scry_bottoming(mountain)
    scenario.cast_and_resolve("Opt", *sources)

    assert [state.name for state in alice.hand] == ["Forest"]
    assert [state.name for state in alice.library] == ["Mountain"]


# --------------------------------------------------------------------------
# Gitaxian Probe
# --------------------------------------------------------------------------


def test_gitaxian_probe_draws_a_card_and_resolves_its_look():
    """The look is a no-op on this engine's board state (CR 701.20e); the
    draw is the half with an observable effect."""
    scenario = (
        Scenario()
        .player("alice", hand=["Gitaxian Probe"], battlefield=["Island"], library=["Forest"])
        .player("bob", hand=["Lightning Bolt", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Island")

    scenario.cast_and_resolve("Gitaxian Probe", *sources, targets=["bob"])

    assert [state.name for state in alice.hand] == ["Forest"]


# --------------------------------------------------------------------------
# Faithless Looting
# --------------------------------------------------------------------------


def test_faithless_looting_draws_two_then_discards_two():
    """CR 608.2c order matters: the two cards discarded may be (and here are)
    among the two just drawn."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Faithless Looting"],
            library=["Plains", "Forest"],
            battlefield=["Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Mountain")
    plains = scenario.find("Plains", Zone.LIBRARY, "alice")
    forest = scenario.find("Forest", Zone.LIBRARY, "alice")

    scenario.will_discard(plains, forest, username="alice")
    scenario.cast_and_resolve("Faithless Looting", *sources)

    assert plains.zone is Zone.GRAVEYARD
    assert forest.zone is Zone.GRAVEYARD
    assert alice.hand == []
    assert alice.library == []


# --------------------------------------------------------------------------
# Expressive Iteration
# --------------------------------------------------------------------------


def test_expressive_iteration_splits_three_ways_and_grants_play_permission():
    """One to hand, one to the bottom, one exiled with a CR 601.3 permission
    to play it this turn - all three chosen from the harness's default
    answer, which takes cards in the order it offered them."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Expressive Iteration"],
            library=["Mountain", "Forest", "Lightning Bolt", "Island"],
            battlefield=["Island", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Island", "Mountain")
    mountain = scenario.find("Mountain", Zone.LIBRARY, "alice")
    forest = scenario.find("Forest", Zone.LIBRARY, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.LIBRARY, "alice")

    scenario.cast_and_resolve("Expressive Iteration", *sources)

    # Exactly one of the top three went to hand, one to the bottom, one to
    # exile - the fourth library card (Island) never entered the look at all.
    moved = [mountain, forest, bolt]
    in_hand = [state for state in moved if state.zone is Zone.HAND]
    in_exile = [state for state in moved if state.zone is Zone.EXILE]
    on_bottom = [state for state in moved if state.zone is Zone.LIBRARY]
    assert len(in_hand) == 1
    assert len(in_exile) == 1
    assert len(on_bottom) == 1
    assert alice.library[-1] is on_bottom[0], "put on the *bottom* of the library"

    exiled = in_exile[0]
    permission = scenario.game.play_permission_for(exiled, "alice", PlayAction.PLAY)
    assert permission is not None
    assert permission.action is PlayAction.PLAY, 'CR 601.1a: the card says "play", the wider word'
    assert permission.pays_mana_cost is True
